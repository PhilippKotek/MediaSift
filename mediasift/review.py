from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .core import _IMAGE_EXTENSIONS, _VIDEO_EXTENSIONS
from .models import ScanCancelled, ScanIssue


@dataclass
class ReviewItem:
    path: Path
    kind: str
    decision: str | None
    size: int
    mtime_ns: int


@dataclass
class ExportResult:
    folder: Path | None
    issues: list[ScanIssue]


def _default_db_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / ".local" / "share")
    return Path(base) / "MediaSift" / "review.sqlite3"


def _sort_key(path: Path) -> tuple[str, str]:
    value = str(path)
    return value.casefold(), value


def _discover(root: Path, progress, cancelled) -> list[tuple[Path, str, int, int]]:
    paths: list[Path] = []
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        if cancelled and cancelled():
            raise ScanCancelled()
        here = Path(current)
        dirs[:] = sorted((d for d in dirs if not (here / d).is_symlink()), key=str.casefold)
        for name in files:
            path = here / name
            if path.is_symlink():
                continue
            ext = path.suffix.casefold()
            if ext in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS:
                paths.append(path)
    paths.sort(key=lambda p: (str(p.relative_to(root)).casefold(), str(p.relative_to(root))))
    items = []
    total = len(paths)
    for index, path in enumerate(paths, 1):
        if cancelled and cancelled():
            raise ScanCancelled()
        try:
            stat = path.stat(follow_symlinks=False)
            kind = "video" if path.suffix.casefold() in _VIDEO_EXTENSIONS else "image"
            items.append((path, kind, stat.st_size, stat.st_mtime_ns))
        except OSError:
            # A file disappearing during the scan is equivalent to a missing file.
            pass
        if progress:
            progress(index, total, str(path))
    return items


class ReviewSession:
    def __init__(self, root: Path, db_path: Path, connection: sqlite3.Connection, items: list[ReviewItem]):
        self.root = root
        self.db_path = db_path
        self._connection = connection
        self._db_lock = threading.RLock()
        self.items = items

    @classmethod
    def open(cls, root: Path, db_path: Path | None = None, progress=None, cancelled=None) -> ReviewSession:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Review source is unavailable: {root}")
        records = _discover(root, progress, cancelled)
        database = Path(db_path) if db_path is not None else _default_db_path()
        database = database.expanduser().absolute()
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database, check_same_thread=False)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("""CREATE TABLE IF NOT EXISTS decisions (
                root TEXT NOT NULL, relpath TEXT NOT NULL, kind TEXT NOT NULL,
                size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                decision TEXT CHECK(decision IN ('keep','discard') OR decision IS NULL),
                PRIMARY KEY(root, relpath))""")
            root_text = str(root)
            # Missing files are omitted from this session's items but their decisions remain resumable.
            items: list[ReviewItem] = []
            for path, kind, size, mtime_ns in records:
                relative = str(path.relative_to(root))
                row = connection.execute(
                    "SELECT kind,size,mtime_ns,decision FROM decisions WHERE root=? AND relpath=?",
                    (root_text, relative),
                ).fetchone()
                decision = row[3] if row and row[:3] == (kind, size, mtime_ns) else None
                connection.execute(
                    "INSERT INTO decisions(root,relpath,kind,size,mtime_ns,decision) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(root,relpath) DO UPDATE SET kind=excluded.kind,size=excluded.size,"
                    "mtime_ns=excluded.mtime_ns,decision=excluded.decision",
                    (root_text, relative, kind, size, mtime_ns, decision),
                )
                items.append(ReviewItem(path, kind, decision, size, mtime_ns))
            connection.execute(
                "INSERT INTO settings(key,value) VALUES('last_root',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (root_text,),
            )
            connection.commit()
            return cls(root, database, connection, items)
        except Exception:
            connection.close()
            raise

    @classmethod
    def last_root(cls, db_path: Path | None = None) -> Path | None:
        database = Path(db_path) if db_path is not None else _default_db_path()
        if not database.exists():
            return None
        try:
            with sqlite3.connect(database) as connection:
                row = connection.execute("SELECT value FROM settings WHERE key='last_root'").fetchone()
            return Path(row[0]) if row else None
        except sqlite3.Error:
            return None

    @property
    def counts(self) -> dict[str, int]:
        result = {"keep": 0, "discard": 0, "unreviewed": 0}
        for item in self.items:
            result[item.decision or "unreviewed"] += 1
        return result

    def set_decision(self, item: ReviewItem, decision: str | None) -> None:
        if decision not in {None, "keep", "discard"}:
            raise ValueError("Decision must be 'keep', 'discard', or None.")
        if item not in self.items:
            raise ValueError("Item does not belong to this review session.")
        relative = str(item.path.relative_to(self.root))
        with self._db_lock:
            self._connection.execute(
                "UPDATE decisions SET decision=? WHERE root=? AND relpath=?",
                (decision, str(self.root), relative),
            )
            self._connection.commit()
        item.decision = decision

    def export_kept(self, destination: Path, progress=None, cancelled=None) -> ExportResult:
        destination = Path(destination).expanduser().resolve()
        try:
            destination.relative_to(self.root)
        except ValueError:
            pass
        else:
            raise ValueError("Export destination must be outside the source folder.")
        kept = [item for item in self.items if item.decision == "keep"]
        issues: list[ScanIssue] = []
        if not kept:
            return ExportResult(None, issues)
        destination.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = destination / f"MediaSift_Review_{stamp}"
        folder = base
        suffix = 1
        while folder.exists():
            folder = destination / f"{base.name}_{suffix}"
            suffix += 1
        folder.mkdir()
        reserved: dict[str, set[str]] = {"Images": set(), "Videos": set()}
        total = len(kept)
        for index, item in enumerate(kept, 1):
            if cancelled and cancelled():
                raise ScanCancelled()
            subfolder = "Videos" if item.kind == "video" else "Images"
            target_dir = folder / subfolder
            target_dir.mkdir(exist_ok=True)
            stem, suffix_ext = item.path.stem, item.path.suffix
            candidate = f"{stem}{suffix_ext}"
            number = 2
            while candidate.casefold() in reserved[subfolder]:
                candidate = f"{stem}_{number}{suffix_ext}"
                number += 1
            reserved[subfolder].add(candidate.casefold())
            target = target_dir / candidate
            try:
                current = item.path.stat(follow_symlinks=False)
                if item.path.is_symlink() or (current.st_size, current.st_mtime_ns) != (item.size, item.mtime_ns):
                    raise OSError("Source changed since it was reviewed.")
                with tempfile.NamedTemporaryFile(dir=target_dir, prefix=".mediasift-", delete=False) as temporary:
                    temp_path = Path(temporary.name)
                try:
                    shutil.copyfile(item.path, temp_path)
                    after = item.path.stat(follow_symlinks=False)
                    if (after.st_size, after.st_mtime_ns) != (item.size, item.mtime_ns):
                        raise OSError("Source changed while it was being copied.")
                    os.replace(temp_path, target)
                finally:
                    if temp_path.exists():
                        temp_path.unlink()
            except OSError as exc:
                issues.append(ScanIssue(item.path, str(exc)))
            if progress:
                progress(index, total, str(item.path))
        return ExportResult(folder, issues)

    def close(self) -> None:
        with self._db_lock:
            self._connection.close()

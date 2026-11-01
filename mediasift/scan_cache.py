"""Persistent fingerprints for unchanged files."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Iterable

ALGORITHM_VERSION = "1"


def canonical_path_key(path: Path) -> str:
    value = Path(path)
    # Scan paths are already resolved absolute paths. Keep callers of ScanCache
    # with relative paths safe without repeating resolution on the hot path.
    return os.path.normcase(str(value if value.is_absolute() else value.resolve()))


def cache_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "MediaSift" / "scan_cache.sqlite3"
    return Path.home() / ".local" / "share" / "MediaSift" / "scan_cache.sqlite3"


class ScanCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connect_recover()

    def _connect_recover(self) -> None:
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                check = db.execute("PRAGMA quick_check").fetchone()
                if check and check[0] != "ok":
                    raise sqlite3.DatabaseError(str(check[0]))
                columns = db.execute("PRAGMA table_info(fingerprints)").fetchall()
                if columns and [row[1] for row in columns] != ["path", "kind", "size", "mtime_ns", "algorithm", "digest"]:
                    db.execute("DROP TABLE fingerprints")
                primary_key = [row[1] for row in db.execute("PRAGMA table_info(fingerprints)").fetchall() if row[5]]
                if primary_key and primary_key != ["path", "kind", "algorithm"]:
                    db.execute("DROP TABLE fingerprints")
                db.execute("CREATE TABLE IF NOT EXISTS fingerprints (path TEXT NOT NULL, kind TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, algorithm TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(path, kind, algorithm))")
        except sqlite3.DatabaseError:
            try:
                self.path.unlink(missing_ok=True)
                Path(str(self.path) + "-wal").unlink(missing_ok=True)
                Path(str(self.path) + "-shm").unlink(missing_ok=True)
            except OSError:
                pass
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS fingerprints (path TEXT NOT NULL, kind TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, algorithm TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(path, kind, algorithm))")

    def get_many(self, entries: Iterable[tuple[Path, str, int, int]], *, full_rescan: bool = False) -> dict[tuple[str, str, int, int], str]:
        if full_rescan:
            return {}
        keys = [(canonical_path_key(path), kind, size, mtime) for path, kind, size, mtime in entries]
        key_set = set(keys)
        found: dict[tuple[str, str, int, int], str] = {}
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                for start in range(0, len(keys), 100):
                    batch = keys[start:start + 100]
                    if not batch:
                        continue
                    clauses = " OR ".join("(path=? AND kind=? AND algorithm=?)" for _ in batch)
                    params = [value for key in batch for value in (key[0], key[1], ALGORITHM_VERSION)]
                    for row in db.execute(f"SELECT path,kind,size,mtime_ns,digest FROM fingerprints WHERE {clauses}", params):
                        key = (row[0], row[1], row[2], row[3])
                        if key in key_set:
                            found[key] = row[4]
        except sqlite3.DatabaseError:
            self._connect_recover()
        return found

    def put_many(self, entries: Iterable[tuple[Path, str, int, int, str]]) -> None:
        rows = [(canonical_path_key(path), kind, size, mtime, ALGORITHM_VERSION, digest)
                for path, kind, size, mtime, digest in entries]
        if not rows:
            return
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.executemany("INSERT INTO fingerprints(path,kind,size,mtime_ns,algorithm,digest) VALUES (?,?,?,?,?,?) ON CONFLICT(path,kind,algorithm) DO UPDATE SET size=excluded.size,mtime_ns=excluded.mtime_ns,digest=excluded.digest", rows)
        except sqlite3.DatabaseError:
            self._connect_recover()
            with closing(sqlite3.connect(self.path)) as db, db:
                db.executemany("INSERT INTO fingerprints(path,kind,size,mtime_ns,algorithm,digest) VALUES (?,?,?,?,?,?) ON CONFLICT(path,kind,algorithm) DO UPDATE SET size=excluded.size,mtime_ns=excluded.mtime_ns,digest=excluded.digest", rows)

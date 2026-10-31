from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps, UnidentifiedImageError

from .models import FileRecord, ImageGroup, ScanCancelled, ScanIssue, ScanResult

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".wmv"}
_REJECTED_IMAGE_EXTENSIONS = {".gif"}


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _walk_sources(
    sources: list[Path],
    issues: list[ScanIssue],
    cancelled: Callable[[], bool] | None,
) -> tuple[list[Path], int]:
    candidates: set[Path] = set()
    ignored = 0
    visited_dirs: set[Path] = set()

    def visit(path: Path) -> None:
        nonlocal ignored
        if cancelled is not None and cancelled():
            raise ScanCancelled()
        try:
            if path.is_symlink():
                ignored += 1
                return
            if path.is_dir():
                resolved = path.resolve()
                if resolved in visited_dirs:
                    return
                visited_dirs.add(resolved)
                with os.scandir(path) as entries:
                    for entry in entries:
                        if cancelled is not None and cancelled():
                            raise ScanCancelled()
                        child = Path(entry.path)
                        if entry.is_symlink():
                            ignored += 1
                        elif entry.is_dir(follow_symlinks=False):
                            visit(child)
                        elif entry.is_file(follow_symlinks=False):
                            ext = child.suffix.casefold()
                            if ext in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS | _REJECTED_IMAGE_EXTENSIONS:
                                candidates.add(child.resolve())
                            else:
                                ignored += 1
                return
            if path.is_file():
                ext = path.suffix.casefold()
                if ext in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS | _REJECTED_IMAGE_EXTENSIONS:
                    candidates.add(path.resolve())
                else:
                    ignored += 1
            else:
                issues.append(ScanIssue(path.resolve(), "Source does not exist or is not a regular file or directory."))
        except OSError as exc:
            issues.append(ScanIssue(path.resolve(), str(exc)))

    for source in sources:
        visit(Path(source).absolute())
    return sorted(candidates, key=lambda p: (str(p).casefold(), str(p))), ignored


def _record(path: Path) -> FileRecord:
    stat = path.stat()
    return FileRecord(path=path.resolve(), size=stat.st_size, mtime_ns=stat.st_mtime_ns)


def _fingerprint(path: Path) -> str:
    with Image.open(path) as source:
        if getattr(source, "n_frames", 1) != 1:
            raise ValueError("Animated or multi-frame images are not supported.")
        image = ImageOps.exif_transpose(source)
        digest = hashlib.sha256()
        digest.update(struct.pack(">II", image.width, image.height))
        if image.mode.startswith("I;16") or image.mode in {"I", "F"}:
            # Converting high-bit-depth images to RGBA would discard pixel detail.
            digest.update(image.mode.encode("ascii"))
        else:
            image = image.convert("RGBA")
            digest.update(b"RGBA")
        digest.update(image.tobytes())
        return digest.hexdigest()


def scan_sources(
    sources: list[Path],
    destination_root: Path,
    progress: Callable[[int, int, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ScanResult:
    """Scan source trees for static images and videos without changing them."""
    resolved_sources = [Path(source).resolve() for source in sources]
    destination = Path(destination_root).resolve()
    for source in resolved_sources:
        if _is_within(destination, source):
            raise ValueError(f"Destination {destination} is within source {source}.")

    issues: list[ScanIssue] = []
    paths, ignored = _walk_sources(sources, issues, cancelled)
    total = len(paths)
    grouped: dict[str, list[FileRecord]] = {}
    videos: list[FileRecord] = []

    for index, path in enumerate(paths, start=1):
        if cancelled is not None and cancelled():
            raise ScanCancelled()
        ext = path.suffix.casefold()
        try:
            if ext in _VIDEO_EXTENSIONS:
                videos.append(_record(path))
            elif ext in _REJECTED_IMAGE_EXTENSIONS:
                issues.append(ScanIssue(path, "GIF images are not supported."))
            else:
                fingerprint = _fingerprint(path)
                grouped.setdefault(fingerprint, []).append(_record(path))
        except (OSError, ValueError, EOFError, SyntaxError, Image.DecompressionBombError, UnidentifiedImageError) as exc:
            issues.append(ScanIssue(path, str(exc) or "Unable to read image."))
        if progress is not None:
            progress(index, total, str(path))

    groups = [ImageGroup(key, files) for key, files in grouped.items()]
    groups.sort(key=lambda group: (str(group.files[0].path).casefold(), str(group.files[0].path)))
    videos.sort(key=lambda record: (str(record.path).casefold(), str(record.path)))
    return ScanResult(groups=groups, videos=videos, issues=issues, ignored=ignored, total=total)

from __future__ import annotations

import hashlib
import os
import struct
import time
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps, UnidentifiedImageError

from .models import BinaryGroup, FileRecord, ImageGroup, ScanCancelled, ScanIssue, ScanResult
from .scan_cache import ScanCache, canonical_path_key

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".wmv"}
_PDF_EXTENSIONS = {".pdf"}
_REJECTED_IMAGE_EXTENSIONS = {".gif"}
_PIXEL_HASH_THRESHOLD = 32 * 1024 * 1024
_PIXEL_HASH_CHUNK = 4 * 1024 * 1024


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
                            if ext in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS | _PDF_EXTENSIONS | _REJECTED_IMAGE_EXTENSIONS:
                                candidates.add(child)
                            else:
                                ignored += 1
                return
            if path.is_file():
                ext = path.suffix.casefold()
                if ext in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS | _PDF_EXTENSIONS | _REJECTED_IMAGE_EXTENSIONS:
                    candidates.add(path)
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
    return FileRecord(path=path, size=stat.st_size, mtime_ns=stat.st_mtime_ns)


def _fingerprint(path: Path, cancelled: Callable[[], bool] | None = None) -> str:
    with Image.open(path) as source:
        if getattr(source, "n_frames", 1) != 1:
            raise ValueError("Animated or multi-frame images are not supported.")
        oriented = ImageOps.exif_transpose(source)
        converted = None
        try:
            image = oriented
            digest = hashlib.sha256()
            digest.update(struct.pack(">II", image.width, image.height))
            if image.mode.startswith("I;16") or image.mode in {"I", "F"}:
                # Converting high-bit-depth images to RGBA would discard pixel detail.
                digest.update(image.mode.encode("ascii"))
                bytes_per_pixel = 2 if image.mode.startswith("I;16") else 4
            else:
                converted = image.convert("RGBA")
                image = converted
                digest.update(b"RGBA")
                bytes_per_pixel = 4

            row_bytes = image.width * bytes_per_pixel
            if row_bytes * image.height <= _PIXEL_HASH_THRESHOLD:
                digest.update(image.tobytes())
            else:
                # Keep only one bounded strip's pixel bytes resident at a time.
                rows_per_chunk = max(1, _PIXEL_HASH_CHUNK // max(1, row_bytes))
                for top in range(0, image.height, rows_per_chunk):
                    if cancelled is not None and cancelled():
                        raise ScanCancelled()
                    strip = image.crop((0, top, image.width, min(image.height, top + rows_per_chunk)))
                    try:
                        digest.update(strip.tobytes())
                    finally:
                        strip.close()
            return digest.hexdigest()
        finally:
            if converted is not None:
                converted.close()
            if oriented is not source:
                oriented.close()


def _binary_fingerprint(path: Path, expected_size: int, expected_mtime: int,
                        cancelled: Callable[[], bool] | None) -> str:
    before = path.stat()
    if (before.st_size, before.st_mtime_ns) != (expected_size, expected_mtime):
        raise OSError("File changed while scanning; retry the scan.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            if cancelled is not None and cancelled():
                raise ScanCancelled()
            chunk = stream.read(4 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    after = path.stat()
    if (after.st_size, after.st_mtime_ns) != (expected_size, expected_mtime):
        raise OSError("File changed while scanning; retry the scan.")
    return digest.hexdigest()


def scan_sources(
    sources: list[Path],
    destination_root: Path,
    progress: Callable[[int, int, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    full_rescan: bool = False,
) -> ScanResult:
    """Scan source trees for static images, videos, and PDFs without changing them."""
    scan_started = time.perf_counter()
    image_cache_hits = binary_cache_hits = image_hashes = binary_hashes = 0
    resolved_sources = [Path(source).resolve() for source in sources]
    destination = Path(destination_root).resolve()
    for source in resolved_sources:
        if _is_within(destination, source):
            raise ValueError(f"Destination {destination} is within source {source}.")

    issues: list[ScanIssue] = []
    paths, ignored = _walk_sources(sources, issues, cancelled)
    total = len(paths)
    grouped: dict[str, list[FileRecord]] = {}
    binary_records: dict[str, list[FileRecord]] = {"video": [], "pdf": []}
    pending_cache: list[tuple[Path, str, int, int, str]] = []
    cache = ScanCache()
    records: dict[Path, FileRecord] = {}
    for path in paths:
        if path.suffix.casefold() not in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS | _PDF_EXTENSIONS:
            continue
        try:
            records[path] = _record(path)
        except OSError as exc:
            issues.append(ScanIssue(path, str(exc)))
    cache_entries = [(record.path, "image", record.size, record.mtime_ns) for path, record in records.items() if path.suffix.casefold() in _IMAGE_EXTENSIONS]
    cache_entries += [(record.path, "pdf" if path.suffix.casefold() in _PDF_EXTENSIONS else "video", record.size, record.mtime_ns) for path, record in records.items() if path.suffix.casefold() in _VIDEO_EXTENSIONS | _PDF_EXTENSIONS]
    cached = cache.get_many(cache_entries, full_rescan=full_rescan)

    for index, path in enumerate(paths, start=1):
        if cancelled is not None and cancelled():
            raise ScanCancelled()
        ext = path.suffix.casefold()
        try:
            if ext in _VIDEO_EXTENSIONS or ext in _PDF_EXTENSIONS:
                record = records.get(path)
                if record is None:
                    continue
                kind = "video" if ext in _VIDEO_EXTENSIONS else "pdf"
                binary_records[kind].append(record)
            elif ext in _REJECTED_IMAGE_EXTENSIONS:
                issues.append(ScanIssue(path, "GIF images are not supported."))
            else:
                record = records.get(path)
                if record is None:
                    continue
                key = (canonical_path_key(record.path), "image", record.size, record.mtime_ns)
                fingerprint = None if full_rescan else cached.get(key)
                if fingerprint is None:
                    fingerprint = _fingerprint(path, cancelled)
                    image_hashes += 1
                    pending_cache.append((record.path, "image", record.size, record.mtime_ns, fingerprint))
                else:
                    image_cache_hits += 1
                after = path.stat()
                if (after.st_size, after.st_mtime_ns) != (record.size, record.mtime_ns):
                    raise OSError("File changed while scanning; retry the scan.")
                grouped.setdefault(fingerprint, []).append(record)
        except MemoryError:
            issues.append(ScanIssue(path, "Insufficient memory to hash image."))
        except (OSError, ValueError, EOFError, SyntaxError, Image.DecompressionBombError, UnidentifiedImageError) as exc:
            issues.append(ScanIssue(path, str(exc) or "Unable to read image."))
        if progress is not None:
            progress(index, total, str(path))

    for kind, file_records in binary_records.items():
        by_size: dict[int, list[FileRecord]] = {}
        for record in file_records:
            by_size.setdefault(record.size, []).append(record)
        fingerprints: dict[str, list[FileRecord]] = {}
        failed_paths: set[Path] = set()
        for size, same_size in by_size.items():
            if len(same_size) < 2:
                continue
            for record in same_size:
                # Versioned binary digests are shared across video extensions; kind separates PDFs.
                cache_kind = "pdf" if kind == "pdf" else "video"
                cache_key = (canonical_path_key(record.path), cache_kind, record.size, record.mtime_ns)
                digest = None if full_rescan else cached.get(cache_key)
                try:
                    current = record.path.stat()
                    if (current.st_size, current.st_mtime_ns) != (record.size, record.mtime_ns):
                        raise OSError("File changed while scanning; retry the scan.")
                except OSError as exc:
                    issues.append(ScanIssue(record.path, str(exc)))
                    failed_paths.add(record.path)
                    continue
                if digest is None:
                    try:
                        digest = _binary_fingerprint(record.path, record.size, record.mtime_ns, cancelled)
                    except ScanCancelled:
                        raise
                    except OSError as exc:
                        issues.append(ScanIssue(record.path, str(exc)))
                        failed_paths.add(record.path)
                        continue
                    pending_cache.append((record.path, cache_kind, record.size, record.mtime_ns, digest))
                    binary_hashes += 1
                else:
                    binary_cache_hits += 1
                fingerprints.setdefault(digest, []).append(record)
        binary_groups = [BinaryGroup(digest, sorted(files, key=lambda item: (str(item.path).casefold(), str(item.path))))
                         for digest, files in fingerprints.items() if len(files) > 1]
        grouped_or_failed = {record.path for group in binary_groups for record in group.files}
        binary_groups.extend(BinaryGroup(None, [record]) for record in file_records
                             if record.path not in grouped_or_failed and record.path not in failed_paths)
        binary_groups.sort(key=lambda group: (str(group.files[0].path).casefold(), str(group.files[0].path)))
        binary_records[kind] = binary_groups
    cache.put_many(pending_cache)
    groups = [ImageGroup(key, files) for key, files in grouped.items()]
    groups.sort(key=lambda group: (str(group.files[0].path).casefold(), str(group.files[0].path)))
    return ScanResult(groups=groups, video_groups=binary_records["video"], pdf_groups=binary_records["pdf"], issues=issues, ignored=ignored, total=total,
                      diagnostics={"image_cache_hits": image_cache_hits, "binary_cache_hits": binary_cache_hits,
                                   "image_hashes_computed": image_hashes, "binary_hashes_computed": binary_hashes,
                                   "elapsed_seconds": time.perf_counter() - scan_started})

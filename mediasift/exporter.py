"""Copy the selected media into a new, isolated export directory."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .models import FileRecord, ScanIssue, ScanResult


@dataclass
class ExportResult:
    run_dir: Path
    images_copied: int = 0
    videos_copied: int = 0
    issues: list[ScanIssue] = field(default_factory=list)
    cancelled: bool = False


def _unchanged(record: FileRecord) -> bool:
    stat = record.path.stat()
    return stat.st_size == record.size and stat.st_mtime_ns == record.mtime_ns


def _free_name(directory: Path, original: str, reserved: set[str]) -> Path:
    name = Path(original)
    candidate = name.name
    number = 2
    while candidate.casefold() in reserved or (directory / candidate).exists():
        candidate = f"{name.stem}_{number}{name.suffix}"
        number += 1
    reserved.add(candidate.casefold())
    return directory / candidate


def _copy_one(record: FileRecord, directory: Path, reserved: set[str]) -> None:
    if not _unchanged(record):
        raise RuntimeError("File changed since the scan")
    target = _free_name(directory, record.path.name, reserved)
    temporary = target.with_name(f".{target.name}.part")
    try:
        shutil.copy2(record.path, temporary)
        if not _unchanged(record):
            raise RuntimeError("File changed while it was being copied")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def export_scan(
    result: ScanResult,
    destination_root: Path,
    progress: Optional[Callable[[int, int, str], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> ExportResult:
    """Copy one image per group and every video; never touch the source files."""
    destination_root = Path(destination_root).expanduser().resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = destination_root / f"MediaSift_{stamp}"
    suffix = 2
    while run_dir.exists():
        run_dir = destination_root / f"MediaSift_{stamp}_{suffix}"
        suffix += 1
    run_dir.mkdir()
    images_dir = run_dir / "Images"
    videos_dir = run_dir / "Videos"
    images_dir.mkdir()
    videos_dir.mkdir()

    exported = ExportResult(run_dir=run_dir)
    image_names: set[str] = set()
    video_names: set[str] = set()
    jobs = [(group.files[0], images_dir, image_names, "image") for group in result.groups]
    jobs.extend((record, videos_dir, video_names, "video") for record in result.videos)
    total = len(jobs)
    for index, (record, directory, reserved, kind) in enumerate(jobs, 1):
        if cancelled and cancelled():
            exported.cancelled = True
            break
        try:
            _copy_one(record, directory, reserved)
            if kind == "image":
                exported.images_copied += 1
            else:
                exported.videos_copied += 1
        except (OSError, RuntimeError) as exc:
            exported.issues.append(ScanIssue(record.path, f"Copy failed: {exc}"))
        if progress:
            progress(index, total, str(record.path))
    return exported

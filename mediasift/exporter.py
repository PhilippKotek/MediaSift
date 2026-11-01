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
    copied_files: list[tuple[Path, Path]] = field(default_factory=list)


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


def _copy_one(record: FileRecord, directory: Path, reserved: set[str]) -> Path:
    if not _unchanged(record):
        raise RuntimeError("File changed since the scan")
    target = _free_name(directory, record.path.name, reserved)
    temporary = target.with_name(f".{target.name}.part")
    try:
        shutil.copy2(record.path, temporary)
        if not _unchanged(record):
            raise RuntimeError("File changed while it was being copied")
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def export_scan(
    result: ScanResult,
    destination_root: Path,
    progress: Optional[Callable[[int, int, str], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
    sources: Optional[list[Path]] = None,
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
            target = _copy_one(record, directory, reserved)
            exported.copied_files.append((target.relative_to(run_dir), record.path))
            if kind == "image":
                exported.images_copied += 1
            else:
                exported.videos_copied += 1
        except (OSError, RuntimeError) as exc:
            exported.issues.append(ScanIssue(record.path, f"Copy failed: {exc}"))
        if progress:
            progress(index, total, str(record.path))
    _write_manifest(exported, sources or [], total)
    return exported


def _write_manifest(exported: ExportResult, sources: list[Path], total: int) -> None:
    status = "Cancelled" if exported.cancelled else ("Partial" if exported.issues else "Complete")
    lines = [
        "MediaSift duplicate export",
        f"Status: {status}",
        f"Images copied (one per duplicate group): {exported.images_copied}",
        f"Videos copied (all scanned videos): {exported.videos_copied}",
        f"Jobs attempted or stopped out of: {total}",
        "",
        "Selected source folders:",
    ]
    lines.extend(f"  {source}" for source in sources)
    lines.extend(["", "Copied files (export path -> original source path):"])
    lines.extend(f"  {output.as_posix()} -> {source}" for output, source in exported.copied_files)
    if exported.issues:
        lines.extend(["", "Copy issues:"])
        lines.extend(f"  {issue.path}: {issue.message}" for issue in exported.issues)
    target = exported.run_dir / "Manifest.txt"
    temporary = exported.run_dir / ".Manifest.txt.part"
    try:
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)

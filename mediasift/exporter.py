"""Copy one representative from each duplicate group into an isolated export."""

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
    pdfs_copied: int = 0
    issues: list[ScanIssue] = field(default_factory=list)
    cancelled: bool = False
    copied_files: list[tuple[Path, Path]] = field(default_factory=list)
    omitted_files: list[tuple[str, Path, Path]] = field(default_factory=list)


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
    """Copy one file per image, video, and PDF group; source files are untouched."""
    destination_root = Path(destination_root).expanduser().resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = destination_root / f"MediaSift_{stamp}"
    suffix = 2
    while run_dir.exists():
        run_dir = destination_root / f"MediaSift_{stamp}_{suffix}"
        suffix += 1
    run_dir.mkdir()
    directories = {kind: run_dir / folder for kind, folder in (
        ("image", "Images"), ("video", "Videos"), ("pdf", "PDFs"),
    )}
    for directory in directories.values():
        directory.mkdir()

    exported = ExportResult(run_dir=run_dir)
    reserved = {kind: set() for kind in directories}
    jobs: list[tuple[FileRecord, str, list[FileRecord]]] = []
    for kind, groups in (("image", result.groups), ("video", result.video_groups), ("pdf", result.pdf_groups)):
        for group in groups:
            if group.files:
                representative = group.files[0]
                jobs.append((representative, kind, group.files[1:]))
    # Existing scanner warnings are useful context in the export report.
    exported.issues.extend(result.issues)
    total = len(jobs)
    completed = 0
    for index, (record, kind, duplicates) in enumerate(jobs, 1):
        if cancelled and cancelled():
            exported.cancelled = True
            break
        try:
            target = _copy_one(record, directories[kind], reserved[kind])
            exported.copied_files.append((target.relative_to(run_dir), record.path))
            for duplicate in duplicates:
                exported.omitted_files.append((kind, duplicate.path, record.path))
            if kind == "image":
                exported.images_copied += 1
            elif kind == "video":
                exported.videos_copied += 1
            else:
                exported.pdfs_copied += 1
        except (OSError, RuntimeError) as exc:
            exported.issues.append(ScanIssue(record.path, f"Copy failed: {exc}"))
        completed = index
        if progress:
            progress(index, total, str(record.path))
    _write_manifest(exported, sources or [], total, completed)
    return exported


def _write_manifest(exported: ExportResult, sources: list[Path], total: int, completed: int) -> None:
    status = "Cancelled" if exported.cancelled else ("Partial" if exported.issues else "Complete")
    lines = [
        "MediaSift duplicate export",
        f"Status: {status}",
        f"Images copied (one per duplicate group): {exported.images_copied}",
        f"Videos copied (one per duplicate group): {exported.videos_copied}",
        f"PDFs copied (one per duplicate group): {exported.pdfs_copied}",
        f"Jobs completed: {completed} of {total}",
        f"Issues: {len(exported.issues)}",
        f"Duplicate members omitted: {len(exported.omitted_files)}",
        "",
        "Selected source folders:",
    ]
    lines.extend(f"  {source}" for source in sources)
    lines.extend(["", "Copied files (export path -> original source path):"])
    lines.extend(f"  {output.as_posix()} -> {source}" for output, source in exported.copied_files)
    if exported.omitted_files:
        lines.extend(["", "Omitted duplicate members (source -> kept representative):"])
        lines.extend(f"  {kind}: {source} -> {kept}" for kind, source, kept in exported.omitted_files)
    if exported.issues:
        lines.extend(["", "Issues:"])
        lines.extend(f"  {issue.path}: {issue.message}" for issue in exported.issues)
    target = exported.run_dir / "Manifest.txt"
    temporary = exported.run_dir / ".Manifest.txt.part"
    try:
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)

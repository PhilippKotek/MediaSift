from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileRecord:
    path: Path
    size: int
    mtime_ns: int


@dataclass
class ImageGroup:
    fingerprint: str
    files: list[FileRecord]


@dataclass
class ScanIssue:
    path: Path
    message: str


@dataclass
class ScanResult:
    groups: list[ImageGroup]
    videos: list[FileRecord]
    issues: list[ScanIssue]
    ignored: int
    total: int


class ScanCancelled(Exception):
    """Raised when a scan is cancelled by its caller."""

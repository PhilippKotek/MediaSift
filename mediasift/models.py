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
class BinaryGroup:
    fingerprint: str | None
    files: list[FileRecord]


@dataclass
class ScanIssue:
    path: Path
    message: str


@dataclass
class ScanResult:
    groups: list[ImageGroup]
    video_groups: list[BinaryGroup]
    pdf_groups: list[BinaryGroup]
    issues: list[ScanIssue]
    ignored: int
    total: int
    diagnostics: dict[str, int | float] | None = None

    @property
    def videos(self) -> list[FileRecord]:
        return [record for group in self.video_groups for record in group.files]

    @property
    def pdfs(self) -> list[FileRecord]:
        return [record for group in self.pdf_groups for record in group.files]


class ScanCancelled(Exception):
    """Raised when a scan is cancelled by its caller."""

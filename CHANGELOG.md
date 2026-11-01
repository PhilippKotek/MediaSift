# Changelog

Notable changes to MediaSift are documented here. Versioned release notes describe user-facing changes; unreleased work is listed under `Unreleased`.

## [0.2.1] - 2026-11-01

### Added

- Added the **Review** workflow for stepping through images, videos, and PDFs, with Keep, Discard, and Skip decisions, keyboard shortcuts, and export of kept files.
- Saved review decisions and the last opened folder locally. Decisions are restored while file identity metadata remains unchanged.
- Added PDF duplicate detection and PDF previews with page navigation.
- Added video duplicate detection and video playback in Review, with an option to open media in the system's default app if playback fails.
- Added scan fingerprint caching, plus **Full rescan** to rebuild fingerprints from file contents.
- Added **Copy paths**, `Ctrl+C`, and a context menu action for copying selected file paths from duplicate results.
- Added contextual tooltips, refreshed the interface and application icon, and packaged a versioned Windows x64 ZIP with third-party notices and PDFium licenses.

### Changed

- Reduced temporary memory use when hashing large images and throttled progress updates during scanning.
- Duplicate export now retains the scan results and restores the export action after the operation completes or fails.
- Export manifests include source roots, output-to-source mappings, omitted duplicate members, counts, issues, and cancellation status.

### Matching behavior and limits

- Images are duplicates only when their decoded pixels and dimensions match after EXIF orientation. Metadata and filenames do not affect matching.
- Videos and PDFs are duplicates only when their file bytes match exactly. Visually identical or re-encoded files may remain separate.
- GIF files are excluded. Animated or multi-frame images can be reported as scan issues.
- Exports copy files; Review's Discard decision does not delete or modify the source.

## [Unreleased]

_No unreleased changes documented._

# Development

## Windows executable build

The Windows onefile build uses Python 3.11. From PowerShell at the repository root, run:

```powershell
.\build.ps1
```

The script installs the pinned project and build dependencies into `.venv-build`, then creates `dist/MediaSift.exe`. The bundle includes Qt Multimedia's FFmpeg backend for video playback and PDFium for PDF rendering. It also places `THIRD_PARTY_NOTICES.md` and the complete `PDFium_Licenses/` directory next to the executable. Keep both alongside the executable when redistributing a build.

The build spec filters Poppler ICU DLLs that can conflict with the ICU APIs Qt expects. Qt's multimedia plugins and FFmpeg runtime binaries remain included.

Python 3.10 through 3.15 is supported for running MediaSift. The packaging script builds with Python 3.11.

## Scan and cache behavior

Image equality uses decoded pixels and dimensions after EXIF orientation. Video and PDF duplicate groups use exact byte equality. Scan fingerprints are cached to speed up later scans; **Full rescan** recomputes fingerprints from file contents. Review decisions are keyed to file identity metadata (path, size, and modification time).

## Review keyboard flow

Keyboard shortcuts are active whenever the Review tab is selected, including when a preview control has focus. They are ignored while typing in a text field. Use **A** or **Left Arrow** to discard, **D** or **Right Arrow** to keep, **S** to skip, **Backspace** to revisit the previous item, **PageUp** and **PageDown** to navigate, and **Space** to play or pause a video.

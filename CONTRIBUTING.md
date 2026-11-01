# Development

## Windows executable build

The Windows onefile build uses Python 3.11. From PowerShell at the repository root, run:

```powershell
.\build.ps1
```

The script installs the pinned project and build dependencies into `.venv-build`, regenerates the PNG/ICO app icon from `docs/assets/mediasift.svg`, then creates `dist/MediaSift-v<version>/MediaSift.exe` and `dist/MediaSift-v<version>-windows-x64.zip`. The versioned output folder contains `LICENSE`, `THIRD_PARTY_NOTICES.md`, and the complete `PDFium_Licenses/` directory alongside the executable. The ZIP includes the executable and all three license/notice items. This keeps builds separate from older `dist/MediaSift.exe` files. The bundle includes Qt Multimedia's FFmpeg backend for video playback and PDFium for PDF rendering. Share the ZIP when redistributing a build.

The build spec filters Poppler ICU DLLs that can conflict with the ICU APIs Qt expects. Qt's multimedia plugins and FFmpeg runtime binaries remain included.

Python 3.10 through 3.15 is supported for running MediaSift. The packaging script builds with Python 3.11.

## Scan and cache behavior

Image equality uses decoded pixels and dimensions after EXIF orientation. Video and PDF duplicate groups use exact byte equality. Scanning uses a lower-memory pipeline, and scan fingerprints are cached to speed up later scans; **Full rescan** recomputes fingerprints from file contents. Hover over controls for contextual help. **Copy paths** copies the selected file path or all paths in a selected duplicate group. Review decisions are keyed to file identity metadata (path, size, and modification time).

## Review keyboard flow

Keyboard shortcuts are active whenever the Review tab is selected, including when a preview control has focus. They are ignored while typing in a text field. Use **A** or **Left Arrow** to discard, **D** or **Right Arrow** to keep, **S** to skip, **Backspace** to revisit the previous item, **PageUp** and **PageDown** to move between PDF pages, and **Space** to play or pause a video.

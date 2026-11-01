# Development

## Windows executable build

The reproducible Windows onefile build uses Python 3.11. From PowerShell at
the repository root, run:

```powershell
.\build.ps1
```

The script installs the pinned project and build dependencies into
`.venv-build`, then creates `dist/MediaSift.exe`. The bundle includes Qt
Multimedia's FFmpeg backend and runtime binaries for video playback. It also
places `THIRD_PARTY_NOTICES.md` next to the executable; review those notices
and their linked license terms when redistributing a build.

Python 3.10 through 3.15 is supported for running MediaSift. The Windows
packaging script deliberately builds with Python 3.11.

## Review keyboard flow

Keyboard shortcuts are active whenever the Review tab is selected, including
when a preview control has focus. They are ignored while typing in a text
field. Use **A** or **Left Arrow** to discard the current item, **D** or
**Right Arrow** to keep it, **S** to skip it without making a decision,
**Backspace** to revisit the previous item, and **Space** to play or pause a
video. Skipped items remain unreviewed and can be revisited with **Backspace**.

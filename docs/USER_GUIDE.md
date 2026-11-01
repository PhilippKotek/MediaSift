# MediaSift User Guide

MediaSift v0.2.1 runs on Windows and copies files to export folders. It never changes or deletes source files. Scans skip symbolic links and unsupported file types.

## Install

1. Download `MediaSift-v0.2.1-windows-x64.zip` from [GitHub Releases](https://github.com/PhilippKotek/MediaSift/releases).
2. Extract the ZIP to a writable folder.
3. Run `MediaSift.exe`. Python is not required.

Keep `LICENSE`, `THIRD_PARTY_NOTICES.md`, and `PDFium_Licenses/` with the executable if you move or share the extracted application.

## Find duplicates

1. In **Find duplicates**, click **Add folder…**. In the Windows picker, Ctrl-click or Shift-click to select several folders in the same location. Add folders from another location by opening the picker again.
2. Select a destination folder outside all source folders. Remove an incorrect source with **Remove selected**.
3. Click **Start scan**. Results appear in separate tabs for duplicate images, videos, PDFs, and issues. Use **Full rescan** to recompute cached fingerprints from the files.
4. Click **Export results** to copy a representative of every unique file into the destination. A duplicate set contributes one file; a file with no duplicate also contributes one file.

The representative is the member with the alphabetically first full path, ignoring case first and using case-sensitive order to break ties. Select a file or group and use **Copy paths**, Ctrl+C, or the right-click menu to copy the source path(s).

### Matching rules

- Supported images are JPG/JPEG, PNG, WebP, BMP, TIF, and TIFF. MediaSift compares decoded pixels and dimensions after applying EXIF orientation. Filenames and metadata are ignored. Animated or multi-frame images are not supported and appear in Issues.
- Supported videos are MP4, MOV, M4V, AVI, MKV, WebM, and WMV. Video files match only when their bytes are identical.
- PDFs match only when their bytes are identical. Files that look the same but have different metadata or encoding are treated as different.
- GIF files are excluded from both Find duplicates and Review.

Image fingerprints and video/PDF hashes are cached to speed up later scans. The cache is stored separately from the source files. A normal scan reuses entries when file size and modification time have not changed; **Full rescan** rebuilds fingerprints from file contents.

### Duplicate export and manifest

Each export creates a new `MediaSift_YYYYMMDD_HHMMSS` folder (a suffix is added if that name already exists), containing `Images`, `Videos`, `PDFs`, and `Manifest.txt`. Conflicting filenames in a media folder get suffixes such as `_2`.

The manifest records completion status, item counts, completed jobs, issues, selected source folders, each output-to-original path mapping, and duplicate members omitted in favor of a representative. If an export is canceled, completed copies remain and the manifest says `Cancelled`. Issues may include unreadable files or files that changed after the scan; those copies are skipped.

## Review media

1. Open **Review** and click **Choose folder…**. MediaSift finds supported images, videos, and PDFs in that folder and its subfolders, then shows one item at a time.
2. Choose **Keep**, **Discard**, or **Skip**. Keep and Discard save a decision; Skip leaves the item undecided. Discard never deletes the source. A PDF decision applies to the whole PDF; use the page buttons or PageUp/PageDown to inspect pages.
3. Click **Export kept…** and choose a destination outside the reviewed folder. Kept files are copied to a timestamped `MediaSift_Review_…` folder, with `Images`, `Videos`, and `PDFs` subfolders. Name conflicts receive numeric suffixes.

Keyboard shortcuts work while the Review tab is active, including when preview controls have focus. They are ignored while typing in a text field.

| Key | Action |
| --- | --- |
| `A` or `←` | Mark current item Discard and advance |
| `D` or `→` | Mark current item Keep and advance |
| `S` | Skip without a decision and advance |
| `Backspace` | Go to the previous item |
| `PageUp` / `PageDown` | Show previous / next page of the current PDF |
| `Space` | Play or pause the current video |

Review decisions and the last reviewed folder are stored in `%LOCALAPPDATA%\MediaSift\review.sqlite3` (or `~/.local/share/MediaSift/review.sqlite3` if `LOCALAPPDATA` is unavailable). On startup, MediaSift automatically reopens the last folder if it still exists. Decisions resume when the relative path, file type, size, and modification time still match. If one of these changes, that file returns to Unreviewed.

## Source safety

MediaSift reads source files and writes copies to the destination. It requires destinations outside the source folder tree. It does not follow symbolic links while discovering files. During export, it checks that a source file has not changed since scanning or review; changed files are skipped and reported. Keep the source files until you have checked the export and its manifest.

## Troubleshooting

- **A file is missing from results:** Check that its extension is supported and it is not a GIF. Look in the **Issues** tab for unreadable images, access errors, or files that changed during scanning.
- **Two files that look alike are not duplicates:** Image matching compares pixels and dimensions; video and PDF matching compares exact bytes. Re-encoding, cropping, resizing, changed metadata, or different PDF encoding can make files distinct.
- **Video preview does not play:** Playback depends on the format and codec available to Qt Multimedia. Click **Open in default app** to use the system's media player.
- **A PDF cannot be previewed:** Use **Open in default app** to open it in a PDF viewer. Page navigation changes the preview page; the review decision is for the whole document.
- **A kept or duplicate file was not exported:** Check the destination's `Manifest.txt` (Find duplicates) or the export summary (Review). The source may have changed or become unavailable; choose a new destination outside the source tree and try again.
- **The review starts at the beginning:** Confirm you opened the same folder and that its files have the same relative paths, sizes, and modification times. Changed files need a new decision.

For build instructions, see [CONTRIBUTING.md](../CONTRIBUTING.md).

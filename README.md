# MediaSift

MediaSift is a completely vibe-coded Windows desktop tool for finding exact duplicate images and reviewing media before you export it. It never deletes or edits source files.

Choose either workflow from the tabs: **Find duplicates** compares selected backup folders; **Review** lets you decide which files from one folder to keep. Exports are copies in a new destination folder.

![MediaSift workflows: find duplicate images across backups or review files individually, then export copies](docs/workflow.svg)

## Download for Windows

The latest published Windows x64 release is [v0.1.0](https://github.com/PhilippKotek/MediaSift/releases/tag/v0.1.0). It does not include the Review workflow described below. Review is available from the `develop` branch and will be included in a future release. Open the release's `MediaSift.exe`; no Python installation is needed.

## Find duplicates across backups

1. Click **Add folder…** and select the backups to combine. Ctrl- or Shift-click to choose several folders in the same location; open the picker again for folders elsewhere. For example, add `Backup A` and `Backup B` to gather media from both.
2. Choose a destination folder outside the backups, then click **Start scan**.
3. Review duplicate image groups and click **Export results**.
4. Open the new `MediaSift_YYYYMMDD_HHMMSS` folder in your destination. It contains `Images` and `Videos` subfolders, plus `Manifest.txt` with the export status, selected source folders, copied file mappings, and any copy issues.

This workflow exports one representative of each distinct supported image and every supported video. Exact image matches are grouped; visually similar images are not.

## Review a folder

1. Open the **Review** tab and choose a folder. MediaSift scans it and its subfolders, and restores earlier decisions when the same files are still present.
2. Mark each image or video **Keep**, **Discard**, or **Skip**. Discard is only a review decision; it never removes a file.
3. Click **Export kept…**, choose a destination outside the source folder, and MediaSift copies kept files into a timestamped `MediaSift_Review_…` folder with `Images` and `Videos` subfolders.

Keyboard shortcuts work while the Review tab is active, except while typing in a text field:

| Key | Action |
| --- | --- |
| `A` or `←` | Discard current item |
| `D` or `→` | Keep current item |
| `S` | Skip to next item |
| `Backspace` | Previous item |
| `Space` | Play or pause video |

Decisions and the last reviewed folder are stored in `%LOCALAPPDATA%\MediaSift\review.sqlite3` on Windows. A decision is reset if a file's size or modification time changes.
Video preview uses Qt Multimedia. If playback fails because the format or codec is unavailable, use **Open in default player** to launch the file with Windows' associated app.

![MediaSift window showing its media review workflow](docs/screenshot.jpg)

## What MediaSift matches

- **Images:** JPG/JPEG, PNG, WebP, BMP, TIF, and TIFF. Images match only when their decoded pixels and dimensions are equal, after applying EXIF orientation. This is not perceptual matching: resized, recompressed, or otherwise visually similar images can remain separate. Metadata and filenames do not affect the match. One representative is exported per group: the file with the alphabetically first full path (case-insensitive, with a case-sensitive tie-break).
- **Videos:** MP4, MOV, M4V, AVI, MKV, WebM, and WMV. Every supported video is copied; videos are not deduplicated.
- **Not supported in Find duplicates:** GIF files are reported as unsupported, and animated or multi-frame files in a supported image format (such as multi-page TIFF) are reported as issues. The Review workflow can preview the first frame of supported animated or multi-frame images and can export the original file unchanged. GIF files are excluded from both workflows.

## Safe output

MediaSift uses copy-only exports. It creates a new timestamped export folder and never deletes or edits originals. The destination must be outside the source folder(s). If output files have the same name, MediaSift adds a number such as `_2` to avoid overwriting. In Find duplicates, scans and exports can be canceled; canceling an export leaves its partial results in the new export folder. Files changed after scanning or review are skipped and reported.

## License

[MIT](LICENSE)

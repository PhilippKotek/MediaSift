# MediaSift

MediaSift is a completely vibe-coded tool for removing duplicate images from multiple backups—without deleting anything from the originals.

Choose backup folders, scan them together, review the matches, then export one copy of each unique image and every video into a new folder. Videos are copied unchanged and are not checked for duplicates. Your source files are never modified.

![MediaSift workflow: Backup A and Backup B are scanned into separate Images and Videos output folders](docs/workflow.svg)

## Download for Windows

[Download the latest Windows x64 release](https://github.com/PhilippKotek/MediaSift/releases/latest). Open `MediaSift.exe`; no Python installation is needed.

## Quick start

1. Click **Add folder…** and select the backups to combine. Ctrl- or Shift-click to choose several folders in the same location; open the picker again for folders elsewhere. For example, add `Backup A` and `Backup B` to gather media from both.
2. Choose a destination folder outside the backups, then click **Start scan**.
3. Review the duplicate image groups and click **Export results**.
4. Open the new `MediaSift_YYYYMMDD_HHMMSS` folder in your destination. It contains `Images` and `Videos` subfolders.

![MediaSift window showing a scan and duplicate image results](docs/screenshot.jpg)

## What MediaSift matches

- **Images:** JPG/JPEG, PNG, WebP, BMP, and single-page TIFF. Images match only when their decoded pixels and dimensions are equal, after applying EXIF orientation. This is not perceptual matching: resized, recompressed, or otherwise visually similar images can remain separate. Metadata and filenames do not affect the match. One representative is exported per group: the file with the alphabetically first full path (case-insensitive, with a case-sensitive tie-break).
- **Videos:** MP4, MOV, M4V, AVI, MKV, WebM, and WMV. Every supported video is copied; videos are not deduplicated.
- **Not supported:** GIF, animated images, and multi-frame images such as multi-page TIFFs are skipped or reported as issues.

## Safe output

MediaSift creates a new timestamped export folder and never deletes or edits originals. The destination cannot be inside a selected source folder. If output files have the same name, MediaSift adds a number such as `_2` to avoid overwriting. You can cancel a scan or export; canceling an export leaves its partial results in the new export folder. Files changed after scanning are skipped and reported.

## License

[MIT](LICENSE)

# MediaSift v0.2.1

MediaSift v0.2.1 adds Review, video and PDF duplicate detection, scan caching, and a refreshed Windows desktop experience. This release is substantially newer than v0.1.0.

![MediaSift Review window](https://raw.githubusercontent.com/PhilippKotek/MediaSift/v0.2.1/docs/screenshot.jpg)

## What's new

- **Review media before export.** Open a folder to browse supported images, videos, and PDFs. Mark items Keep or Discard, or Skip them for later. Review decisions are saved locally and restored while the file's size and modification time stay the same. Export kept files to a new destination folder; Discard never deletes a source file.
- **Find duplicate videos and PDFs.** Duplicate scanning now covers videos and PDFs in addition to images. PDF pages can be previewed in Review, and videos can be played when the available codec supports them.
- **Scan faster on repeat runs.** Fingerprints are cached between scans. Use **Full rescan** to recompute them from file contents. Large image hashing uses a bounded temporary pixel buffer to reduce additional memory use.
- **Copy source paths.** Select a file or duplicate group and use **Copy paths**, `Ctrl+C`, or the context menu.
- **More reliable exports and clearer controls.** The duplicate results remain available after export completes or reports an error. The UI includes contextual tooltips, a refreshed appearance, and a new application icon.
- **Windows x64 package.** The build produces a versioned ZIP with the executable, MIT license, third-party notices, and PDFium license files. The executable does not require a separate Python installation.

## Duplicate matching

Matching is exact. Images are compared by decoded pixel values and dimensions after EXIF orientation, so metadata and filenames do not matter. Videos and PDFs are compared by exact file bytes. Visually similar images, re-encoded videos, or PDFs with different bytes are not grouped as duplicates. GIF files are excluded; animated or multi-frame images may be reported as issues.

Duplicate export copies one representative from each group. It chooses the alphabetically first full path, ignoring case first and using a case-sensitive tie-break. The export creates a timestamped folder with media subfolders and a `Manifest.txt` recording source roots, file mappings, omitted duplicate members, counts, issues, and cancellation status.

## Known limitations

- Video preview depends on the codecs available through Qt Multimedia on the computer. If playback fails, use **Open in default app**.
- PDFs with different bytes are treated as different even when their pages look alike. Password-protected or damaged PDFs may fail to preview.
- A review decision is reset if a file's size or modification time changes.
- GIF files are not included in either workflow.

See [README.md](../README.md) for setup and full workflow details.

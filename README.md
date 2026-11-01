# MediaSift

MediaSift is a completely vibe-coded Windows tool for finding exact duplicate images, videos, and PDFs, and for reviewing media one item at a time. It copies selected files into new export folders; it does not edit or delete the originals.

For example, if you have several phone and cloud backups with overlapping photos and videos, MediaSift can collect one copy of each unique file into a fresh folder.

![MediaSift workflows: find duplicate images, videos, and PDFs across folders or review media individually, then export copies](docs/workflow.svg)

## Download and install

Download **MediaSift-v0.2.1-windows-x64.zip** from the [GitHub Releases page](https://github.com/PhilippKotek/MediaSift/releases). Extract the ZIP to a folder you can write to, then run `MediaSift.exe`. No Python installation is required. Keep `LICENSE`, `THIRD_PARTY_NOTICES.md`, and the `PDFium_Licenses` folder with the executable when moving or redistributing the package.

## Choose a workflow

- **Find duplicates** scans one or more source folders, including their subfolders. It groups exact duplicate images, videos, and PDFs, then exports a clean copy of every unique file.
- **Review** previews files in one folder tree so you can mark each item Keep, Discard, or Skip, then export the files marked Keep.

See the [User Guide](docs/USER_GUIDE.md) for matching rules, keyboard controls, resume behavior, export details, and troubleshooting.

![MediaSift window showing the Review workflow](docs/screenshot.jpg)

## What matches

- **Images:** JPG/JPEG, PNG, WebP, BMP, TIF, and TIFF. Images match when decoded pixels and dimensions match after EXIF orientation is applied. Names and metadata do not affect matching. Animated or multi-frame images are reported as issues.
- **Videos:** MP4, MOV, M4V, AVI, MKV, WebM, and WMV. Matching uses exact file bytes; re-encoded files do not match.
- **PDFs:** matching uses exact file bytes; metadata or encoding differences mean files remain separate.
- **GIF:** excluded from both workflows.

## Safe exports

Choose an output folder outside the source tree. Find duplicates creates a timestamped `MediaSift_YYYYMMDD_HHMMSS` folder with `Images`, `Videos`, `PDFs`, and `Manifest.txt`. Review creates a timestamped `MediaSift_Review_…` folder with the same media subfolders. Name collisions receive a numeric suffix. If a source changes during scanning or before it is copied, MediaSift reports an issue and skips that copy. A canceled duplicate export keeps completed copies and records its status in the manifest.

## License

[MIT](LICENSE). Bundled components and license references are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

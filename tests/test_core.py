from pathlib import Path
import hashlib
import struct

import pytest
from PIL import Image, ImageOps

from mediasift import scan_sources


@pytest.mark.parametrize("mode,color", [("RGB", (12, 34, 56)), ("L", 127), ("I;16", 1024)])
def test_large_striped_hash_matches_original_pixel_hash(tmp_path: Path, mode: str, color) -> None:
    import mediasift.core as core

    path = tmp_path / "large.png"
    size = (4200, 4200)
    Image.new(mode, size, color).save(path)
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        digest = hashlib.sha256()
        digest.update(struct.pack(">II", image.width, image.height))
        if image.mode.startswith("I;16") or image.mode in {"I", "F"}:
            digest.update(image.mode.encode("ascii"))
        else:
            image = image.convert("RGBA")
            digest.update(b"RGBA")
        digest.update(image.tobytes())

    assert size[0] * size[1] * (2 if mode == "I;16" else 4) > core._PIXEL_HASH_THRESHOLD
    assert core._fingerprint(path) == digest.hexdigest()


def test_large_striped_hash_checks_cancellation(tmp_path: Path) -> None:
    import mediasift.core as core
    from mediasift.models import ScanCancelled

    path = tmp_path / "large.png"
    Image.new("RGB", (3000, 3000), "purple").save(path)
    with pytest.raises(ScanCancelled):
        core._fingerprint(path, lambda: True)


def test_groups_decoded_pixels_and_deduplicates_overlapping_roots(tmp_path: Path) -> None:
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)
    first = source / "a.png"
    second = nested / "b.bmp"
    Image.new("RGB", (2, 1), (20, 40, 60)).save(first)
    Image.new("RGB", (2, 1), (20, 40, 60)).save(second)

    result = scan_sources([source, nested], tmp_path / "out")

    assert result.total == 2
    assert result.ignored == 0
    assert len(result.groups) == 1
    assert [record.path for record in result.groups[0].files] == [first.resolve(), second.resolve()]


def test_reports_gif_and_lists_video_without_hashing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    gif = source / "reject.gif"
    Image.new("RGB", (1, 1), "red").save(gif)
    video = source / "clip.mp4"
    video.write_bytes(b"video placeholder")

    result = scan_sources([source], tmp_path / "destination")

    assert result.total == 2
    assert [record.path for record in result.videos] == [video.resolve()]
    assert result.video_groups[0].fingerprint is None
    assert len(result.issues) == 1
    assert "GIF" in result.issues[0].message


def test_hashes_same_size_video_and_pdf_files_and_keeps_different_files_separate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))
    source = tmp_path / "source"
    source.mkdir()
    files = [source / "a.mp4", source / "b.mkv", source / "c.pdf", source / "d.pdf"]
    files[0].write_bytes(b"video")
    files[1].write_bytes(b"video")
    files[2].write_bytes(b"pdf1")
    files[3].write_bytes(b"pdf2")

    result = scan_sources([source], tmp_path / "out")

    assert len(result.video_groups) == 1
    assert result.video_groups[0].fingerprint is not None
    assert len(result.video_groups[0].files) == 2
    assert len(result.pdf_groups) == 2
    assert all(group.fingerprint is None and len(group.files) == 1 for group in result.pdf_groups)


def test_scan_cache_hits_changed_files_and_full_rescan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))
    source = tmp_path / "source"
    source.mkdir()
    a, b = source / "a.png", source / "b.png"
    Image.new("RGB", (3, 3), "green").save(a)
    Image.new("RGB", (3, 3), "green").save(b)
    first = scan_sources([source], tmp_path / "out")
    assert first.diagnostics["image_hashes_computed"] == 2
    warm = scan_sources([source], tmp_path / "out")
    assert warm.diagnostics["image_cache_hits"] == 2
    assert warm.diagnostics["image_hashes_computed"] == 0
    full = scan_sources([source], tmp_path / "out", full_rescan=True)
    assert full.diagnostics["image_hashes_computed"] == 2
    Image.new("RGB", (3, 3), "blue").save(a)
    changed = scan_sources([source], tmp_path / "out")
    assert changed.diagnostics["image_hashes_computed"] == 1
    assert changed.diagnostics["image_cache_hits"] == 1


def test_file_disappearing_during_recording_becomes_issue(tmp_path: Path, monkeypatch) -> None:
    import mediasift.core as core

    source = tmp_path / "source"
    source.mkdir()
    image = source / "a.png"
    Image.new("RGB", (2, 2), "red").save(image)
    original_record = core._record

    def missing_record(path: Path):
        if path == image.resolve():
            raise FileNotFoundError("gone during scan")
        return original_record(path)

    monkeypatch.setattr(core, "_record", missing_record)
    result = scan_sources([source], tmp_path / "out")

    assert result.groups == []
    assert any(issue.path == image.resolve() and "gone during scan" in issue.message for issue in result.issues)


def test_rejects_destination_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(ValueError):
        scan_sources([source], source / "output")


def test_16_bit_tiff_values_are_not_reduced_to_8_bit(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    Image.new("I;16", (1, 1), 1000).save(source / "first.tiff")
    Image.new("I;16", (1, 1), 1001).save(source / "second.tiff")

    result = scan_sources([source], tmp_path / "out")

    assert len(result.groups) == 2


def test_multi_page_tiff_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    first = Image.new("RGB", (2, 2), "red")
    second = Image.new("RGB", (2, 2), "blue")
    first.save(source / "pages.tiff", save_all=True, append_images=[second])

    result = scan_sources([source], tmp_path / "out")

    assert result.groups == []
    assert len(result.issues) == 1
    assert "multi-frame" in result.issues[0].message

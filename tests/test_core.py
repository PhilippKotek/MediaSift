from pathlib import Path

import pytest
from PIL import Image

from mediasift import scan_sources


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
    assert len(result.issues) == 1
    assert "GIF" in result.issues[0].message


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

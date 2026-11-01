from pathlib import Path

from PIL import Image

from mediasift.core import scan_sources
from mediasift.exporter import export_scan


def test_export_copies_unique_images_and_every_video_without_touching_sources(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    destination = tmp_path / "destination"
    Image.new("RGB", (2, 2), "red").save(source / "a.png")
    Image.new("RGB", (2, 2), "red").save(source / "nested" / "same.bmp")
    Image.new("RGB", (2, 2), "blue").save(source / "nested" / "a.png")
    (source / "clip.mp4").write_bytes(b"same video")
    (source / "nested" / "clip.mp4").write_bytes(b"same video")
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}

    scan = scan_sources([source], destination)
    first = export_scan(scan, destination)
    second = export_scan(scan, destination)

    assert first.run_dir != second.run_dir
    assert first.images_copied == 2
    assert first.videos_copied == 2
    assert len(list((first.run_dir / "Images").iterdir())) == 2
    assert sorted(p.name for p in (first.run_dir / "Videos").iterdir()) == ["clip.mp4", "clip_2.mp4"]
    assert {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()} == before


def test_changed_source_is_reported_and_not_copied(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    video = source / "clip.mp4"
    video.write_bytes(b"original")
    destination = tmp_path / "destination"
    scan = scan_sources([source], destination)
    video.write_bytes(b"changed content")

    exported = export_scan(scan, destination)

    assert exported.videos_copied == 0
    assert len(exported.issues) == 1
    assert list((exported.run_dir / "Videos").iterdir()) == []


def test_manifest_lists_selected_roots_and_collision_output_mapping(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "clip.mp4").write_bytes(b"one")
    (second / "clip.mp4").write_bytes(b"two")
    destination = tmp_path / "out"
    roots = [first, second]

    exported = export_scan(scan_sources(roots, destination), destination, sources=roots)

    manifest = (exported.run_dir / "Manifest.txt").read_text(encoding="utf-8")
    assert "Status: Complete" in manifest
    assert f"  {first}" in manifest and f"  {second}" in manifest
    assert f"Videos/clip.mp4 -> {first / 'clip.mp4'}" in manifest
    assert f"Videos/clip_2.mp4 -> {second / 'clip.mp4'}" in manifest


def test_manifest_records_cancelled_partial_export(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.mp4").write_bytes(b"a")
    (source / "b.mp4").write_bytes(b"b")
    destination = tmp_path / "out"
    calls = 0

    def cancel_after_first() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1

    exported = export_scan(
        scan_sources([source], destination), destination,
        cancelled=cancel_after_first, sources=[source],
    )

    manifest = (exported.run_dir / "Manifest.txt").read_text(encoding="utf-8")
    assert exported.cancelled
    assert "Status: Cancelled" in manifest
    assert "Videos/" in manifest and " -> " in manifest

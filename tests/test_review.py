from __future__ import annotations

import os
from pathlib import Path

import pytest

from mediasift.review import ReviewSession


def _touch(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_discovery_order_and_symlink_skip(tmp_path: Path) -> None:
    root = tmp_path / "source"
    _touch(root / "z" / "B.MP4")
    _touch(root / "a.jpg")
    _touch(root / "z" / "a.gif")
    _touch(root / "z" / "A.png")
    target = _touch(tmp_path / "external.jpg")
    try:
        (root / "linked.jpg").symlink_to(target)
    except OSError:
        pass
    session = ReviewSession.open(root, tmp_path / "review.db")
    assert [item.path.relative_to(root).as_posix() for item in session.items] == ["a.jpg", "z/A.png", "z/B.MP4"]
    assert [item.kind for item in session.items] == ["image", "image", "video"]
    session.close()


def test_decisions_resume_and_changed_metadata_resets(tmp_path: Path) -> None:
    root = tmp_path / "source"
    photo = _touch(root / "photo.jpg", b"first")
    movie = _touch(root / "movie.mp4")
    db = tmp_path / "review.db"
    first = ReviewSession.open(root, db)
    first.set_decision(next(item for item in first.items if item.path == photo), "keep")
    first.set_decision(next(item for item in first.items if item.path == movie), "discard")
    first.close()
    assert ReviewSession.last_root(db) == root.resolve()

    second = ReviewSession.open(root, db)
    assert second.counts == {"keep": 1, "discard": 1, "unreviewed": 0}
    second.close()
    photo.write_bytes(b"changed size")
    third = ReviewSession.open(root, db)
    assert next(item for item in third.items if item.path == photo).decision is None
    assert next(item for item in third.items if item.path == movie).decision == "discard"
    third.close()


def test_missing_root_does_not_destroy_database_or_last_root(tmp_path: Path) -> None:
    root = tmp_path / "source"
    _touch(root / "a.png")
    db = tmp_path / "review.db"
    session = ReviewSession.open(root, db)
    session.set_decision(session.items[0], "keep")
    session.close()
    before = db.read_bytes()
    with pytest.raises(FileNotFoundError):
        ReviewSession.open(tmp_path / "gone", db)
    assert db.read_bytes() == before
    assert ReviewSession.last_root(db) == root.resolve()


def test_missing_file_is_hidden_but_its_decision_survives_reappearance(tmp_path: Path) -> None:
    root = tmp_path / "source"
    photo = _touch(root / "a.jpg", b"same")
    original_stat = photo.stat()
    db = tmp_path / "review.db"
    session = ReviewSession.open(root, db)
    session.set_decision(session.items[0], "keep")
    session.close()
    parked = tmp_path / "parked.jpg"
    photo.rename(parked)
    missing = ReviewSession.open(root, db)
    assert missing.items == []
    missing.close()
    parked.rename(photo)
    os.utime(photo, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    restored = ReviewSession.open(root, db)
    assert len(restored.items) == 1 and restored.items[0].decision == "keep"
    restored.close()


def test_export_kept_flat_collision_safe_and_source_safe(tmp_path: Path) -> None:
    root = tmp_path / "source"
    a = _touch(root / "one" / "same.jpg", b"one")
    b = _touch(root / "two" / "same.jpg", b"two")
    video = _touch(root / "clip.mp4", b"video")
    db = tmp_path / "review.db"
    session = ReviewSession.open(root, db)
    session.set_decision(next(item for item in session.items if item.path == a), "keep")
    session.set_decision(next(item for item in session.items if item.path == b), "discard")
    session.set_decision(next(item for item in session.items if item.path == video), "keep")
    result = session.export_kept(tmp_path / "out")
    assert result.folder is not None
    assert (result.folder / "Images" / "same.jpg").read_bytes() == b"one"
    assert (result.folder / "Videos" / "clip.mp4").read_bytes() == b"video"
    with pytest.raises(ValueError):
        session.export_kept(root / "inside")
    # Export copied; it did not alter any source.
    assert a.read_bytes() == b"one" and b.read_bytes() == b"two" and video.read_bytes() == b"video"
    session.close()


def test_export_changed_source_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "source"
    source = _touch(root / "a.jpg", b"old")
    session = ReviewSession.open(root, tmp_path / "review.db")
    session.set_decision(session.items[0], "keep")
    source.write_bytes(b"now changed")
    result = session.export_kept(tmp_path / "out")
    assert result.folder is not None
    assert result.issues and "changed" in result.issues[0].message
    assert not list(result.folder.rglob("a.jpg"))
    session.close()

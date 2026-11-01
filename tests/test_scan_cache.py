from pathlib import Path
import os
import sqlite3

import pytest

from mediasift import ScanCancelled, scan_sources


def test_binary_cache_warm_scan_and_full_rescan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.mp4").write_bytes(b"same bytes")
    (source / "b.mov").write_bytes(b"same bytes")

    cold = scan_sources([source], tmp_path / "out")
    warm = scan_sources([source], tmp_path / "out")
    assert cold.diagnostics["binary_hashes_computed"] == 2
    assert warm.diagnostics["binary_cache_hits"] == 2
    assert warm.diagnostics["binary_hashes_computed"] == 0
    forced = scan_sources([source], tmp_path / "out", full_rescan=True)
    assert forced.diagnostics["binary_hashes_computed"] == 2


def test_binary_hash_cancellation_is_checked_during_chunks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.pdf").write_bytes(b"x" * (9 * 1024 * 1024))
    (source / "b.pdf").write_bytes(b"x" * (9 * 1024 * 1024))
    calls = 0

    def cancelled() -> bool:
        nonlocal calls
        calls += 1
        return calls > 5

    with pytest.raises(ScanCancelled):
        scan_sources([source], tmp_path / "out", cancelled=cancelled)


def test_overlapping_roots_count_a_file_once(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    source = tmp_path / "source"
    child = source / "nested"
    child.mkdir(parents=True)
    (child / "a.pdf").write_bytes(b"pdf")

    result = scan_sources([source, child], tmp_path / "out")

    assert result.total == 1
    assert result.pdfs[0].path == (child / "a.pdf").resolve()


def test_corrupt_cache_is_recreated(tmp_path: Path, monkeypatch) -> None:
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    cache = local / "MediaSift" / "scan_cache.sqlite3"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"not a sqlite database")
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.pdf").write_bytes(b"one")
    (source / "b.pdf").write_bytes(b"one")

    result = scan_sources([source], tmp_path / "out")

    assert result.diagnostics["binary_hashes_computed"] == 2
    assert cache.read_bytes().startswith(b"SQLite format 3")


def test_cached_binary_metadata_is_rechecked_before_grouping(tmp_path: Path, monkeypatch) -> None:
    import mediasift.core as core

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    source = tmp_path / "source"
    source.mkdir()
    a, b = source / "a.pdf", source / "b.pdf"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    scan_sources([source], tmp_path / "out")
    original_get_many = core.ScanCache.get_many

    def mutate_after_lookup(cache, entries, *, full_rescan=False):
        found = original_get_many(cache, entries, full_rescan=full_rescan)
        a.write_bytes(b"diff")
        os.utime(a, ns=(a.stat().st_atime_ns, a.stat().st_mtime_ns + 2_000_000_000))
        return found

    monkeypatch.setattr(core.ScanCache, "get_many", mutate_after_lookup)
    result = scan_sources([source], tmp_path / "out")

    assert not any(a.resolve() == record.path for group in result.pdf_groups for record in group.files)
    assert any(issue.path == a.resolve() and "changed while scanning" in issue.message for issue in result.issues)


def test_failed_binary_hash_is_not_returned_as_a_file_group(tmp_path: Path, monkeypatch) -> None:
    import mediasift.core as core

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    source = tmp_path / "source"
    source.mkdir()
    a, b = source / "a.pdf", source / "b.pdf"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    original_hash = core._binary_fingerprint

    def fail_one(path, size, mtime, cancelled):
        if path == a.resolve():
            raise OSError("changed during hash")
        return original_hash(path, size, mtime, cancelled)

    monkeypatch.setattr(core, "_binary_fingerprint", fail_one)
    result = scan_sources([source], tmp_path / "out", full_rescan=True)

    assert all(record.path != a.resolve() for record in result.pdfs)
    assert any(issue.path == a.resolve() and "changed during hash" in issue.message for issue in result.issues)


def test_cache_replaces_stale_metadata_row(tmp_path: Path) -> None:
    from mediasift.scan_cache import ScanCache

    cache_file = tmp_path / "cache.sqlite3"
    item = tmp_path / "item.pdf"
    item.write_bytes(b"one")
    cache = ScanCache(cache_file)
    stat = item.stat()
    cache.put_many([(item.resolve(), "pdf", stat.st_size, stat.st_mtime_ns, "first")])
    cache.put_many([(item.resolve(), "pdf", stat.st_size + 1, stat.st_mtime_ns + 1, "second")])
    with sqlite3.connect(cache_file) as db:
        count = db.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
    assert count == 1

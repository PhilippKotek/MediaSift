import os
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTreeWidgetItem
from PIL import Image

from mediasift.ui import MediaSiftApp


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    widget = MediaSiftApp()
    yield widget
    widget.close()
    app.processEvents()


def test_scan_success_keeps_result_and_enables_export(window, monkeypatch):
    result = object()
    window.busy = True
    window.export_button.setEnabled(False)
    monkeypatch.setattr(window, "_render_result", lambda value: None)

    window._job_done(result, "Scan")

    assert window.result is result
    assert not window.busy
    assert window.export_button.isEnabled()
    assert "current scan" in window.export_button.toolTip()


def test_export_success_retains_scan_and_reenables_export(window, monkeypatch):
    original = object()
    window.result = original
    window.busy = True
    window.export_button.setEnabled(False)
    monkeypatch.setattr(window, "_render_result", lambda value: None)
    monkeypatch.setattr("mediasift.ui.QMessageBox.information", lambda *args: None)
    outcome = SimpleNamespace(cancelled=False, issues=[], run_dir="export", images_copied=1,
                              videos_copied=0, pdfs_copied=0)

    window._job_done(outcome, "Export")

    assert window.result is original
    assert not window.busy
    assert window.export_button.isEnabled()


def test_export_failure_retains_scan_and_reenables_export(window, monkeypatch):
    original = object()
    window.result = original
    window.busy = True
    window.export_button.setEnabled(False)
    monkeypatch.setattr("mediasift.ui.QMessageBox.critical", lambda *args: None)

    window._job_failed("disk full", "Export")

    assert window.result is original
    assert not window.busy
    assert window.export_button.isEnabled()
    assert window.status.text() == "Error"


def test_copy_paths_for_selected_group_and_file_deduplicates_in_tree_order(window):
    group = QTreeWidgetItem(["Group 1 · abc", "2"])
    window.group_tree.addTopLevelItem(group)
    first = QTreeWidgetItem(["C:/photos/a.png", "1 KB"])
    second = QTreeWidgetItem(["C:/photos/b.png", "1 KB"])
    group.addChildren([first, second])
    group.setSelected(True)
    second.setSelected(True)

    window._copy_selected_paths()

    assert QApplication.clipboard().text() == "C:/photos/a.png\nC:/photos/b.png"
    assert window.status.text() == "Copied 2 paths"


def test_buttons_have_english_tooltips_and_export_explains_disabled_state(window):
    assert all(button.toolTip().strip() for button in window.findChildren(type(window.scan_button)))
    assert not window.export_button.isEnabled()
    assert "Run a scan" in window.export_button.toolTip()


def test_ctrl_c_copies_selected_file_path(window):
    group = QTreeWidgetItem(["Group 1 · abc", "2"])
    window.group_tree.addTopLevelItem(group)
    file_item = QTreeWidgetItem(["C:/photos/a.png", "1 KB"])
    group.addChild(file_item)
    file_item.setSelected(True)
    window.group_tree.setFocus()

    QTest.keyClick(window.group_tree, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)

    assert QApplication.clipboard().text() == "C:/photos/a.png"


def test_copy_paths_uses_only_the_visible_result_tab(window):
    image_group = QTreeWidgetItem(["Group 1 · image", "1"])
    image_group.addChild(QTreeWidgetItem(["C:/photos/image.png", "1 KB"]))
    window.group_tree.addTopLevelItem(image_group)
    image_group.setSelected(True)

    video_group = QTreeWidgetItem(["Group 1 · video", "1"])
    video_group.addChild(QTreeWidgetItem(["C:/videos/clip.mp4", "1 KB"]))
    window.video_tree.addTopLevelItem(video_group)
    video_group.setSelected(True)
    window.results_tabs.setCurrentWidget(window.video_tree)

    window._copy_selected_paths()

    assert QApplication.clipboard().text() == "C:/videos/clip.mp4"


def test_scan_then_export_from_gui_creates_manifest(window, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr("mediasift.ui.QMessageBox.information", lambda *args: None)
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (8, 8), "teal").save(source / "a.png")
    Image.new("RGB", (8, 8), "teal").save(source / "b.png")
    window.sources = [source]
    window.destination = tmp_path / "output"

    def wait_for(predicate):
        deadline = monotonic() + 8
        while not predicate() and monotonic() < deadline:
            QApplication.processEvents()
            QTest.qWait(10)
        assert predicate()

    window._start_scan()
    wait_for(lambda: window.status.text() == "Scan complete" and not window.busy)
    assert window.export_button.isEnabled()
    window._start_export()
    wait_for(lambda: window.status.text() == "Export complete" and not window.busy)
    wait_for(lambda: not window._threads)

    run_dir = next(window.destination.iterdir())
    assert [path.name for path in (run_dir / "Images").iterdir()] == ["a.png"]
    manifest = (run_dir / "Manifest.txt").read_text(encoding="utf-8")
    assert str(source) in manifest and "b.png" in manifest
    assert window.export_button.isEnabled()

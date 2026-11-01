"""PySide6 user interface for MediaSift."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from functools import partial
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from PySide6.QtCore import QObject, QRunnable, Qt, QThread, QThreadPool, QUrl, QEvent, Signal, Slot
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut, QIcon
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QSlider, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QListWidget,
    QStackedWidget,
    QMenu,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

from .core import scan_sources
from .exporter import export_scan
from .folder_picker import pick_folders
from .models import ScanCancelled, ScanResult
from .review import ReviewSession
from .resources import resource_path


class WorkerSignals(QObject):
    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class Job(QThread):
    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = WorkerSignals()
        self.cancel_flag = threading.Event()
        self._last_report_at = 0.0
        self._last_report = None

    def run(self):
        try:
            result = self.fn(*self.args, progress=self.report, cancelled=self.cancel_flag.is_set)
            self._flush_report()
            self.signals.done.emit(result)
        except ScanCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:
            self.signals.failed.emit(str(exc))

    def report(self, done, total, label):
        self._last_report = (done, total, Path(label).name)
        if time.monotonic() - self._last_report_at >= 0.1:
            self._flush_report()

    def _flush_report(self):
        if self._last_report is not None:
            self.signals.progress.emit(*self._last_report)
            self._last_report_at = time.monotonic()


class PreviewSignals(QObject):
    ready = Signal(int, object, int, str)


class ImagePreview(QRunnable):
    def __init__(self, generation: int, path: Path, max_size: tuple[int, int]):
        super().__init__()
        self.generation, self.path, self.max_size = generation, path, max_size
        self.signals = PreviewSignals()

    @Slot()
    def run(self):
        try:
            with Image.open(self.path) as source:
                source = ImageOps.exif_transpose(source)
                source.thumbnail(self.max_size, Image.Resampling.LANCZOS)
                image = source.convert("RGBA")
                data = image.tobytes("raw", "RGBA")
                qimage = QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()
            error = ""
        except Exception as exc:
            qimage, error = None, str(exc)
        try:
            self.signals.ready.emit(self.generation, qimage, 0, error)
        except RuntimeError:
            # The window may have closed while a preview was being decoded.
            pass


class PdfPreview(QRunnable):
    def __init__(self, generation: int, path: Path, page: int, max_size: tuple[int, int]):
        super().__init__()
        self.generation, self.path, self.page, self.max_size = generation, path, page, max_size
        self.signals = PreviewSignals()

    @Slot()
    def run(self):
        try:
            import pypdfium2 as pdfium
            document = pdfium.PdfDocument(str(self.path))
            try:
                count = len(document)
                page = document[self.page]
                width, height = page.get_size()
                scale = min(self.max_size[0] / max(width, 1), self.max_size[1] / max(height, 1), 1.5)
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil().convert("RGBA")
                data = image.tobytes("raw", "RGBA")
                qimage = QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()
            finally:
                document.close()
            error = ""
        except Exception as exc:
            qimage, count, error = None, 0, str(exc)
        try:
            self.signals.ready.emit(self.generation, qimage, count, error)
        except RuntimeError:
            pass


class MediaSiftApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MediaSift")
        self.setWindowIcon(QIcon(resource_path("assets/mediasift.png")))
        self.resize(1040, 760)
        self.setMinimumSize(760, 560)
        self.sources: list[Path] = []
        self.destination: Path | None = None
        self.result: ScanResult | None = None
        self.busy = False
        self.job: Job | None = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._preview_generation = 0
        self._threads: set[Job] = set()
        self.session = None
        self.review_items = []
        self.review_index = 0
        self._review_skipped: set[int] = set()
        self._review_history: list[int] = []
        self._review_root: Path | None = None
        self._pdf_page = 0
        self._pdf_page_count = 0
        self._pdf_current_path: Path | None = None
        self._setup_media()
        self._build()
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f4f7fa; color: #172b42; font-family: 'Segoe UI'; font-size: 10pt; }
            QTabWidget::pane { border: 1px solid #d8e2eb; background: #ffffff; border-radius: 8px; }
            QTabBar::tab { background: #e8eef4; color: #40556b; padding: 9px 16px; margin-right: 4px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #ffffff; color: #087f83; font-weight: 600; }
            QTreeWidget, QListWidget { background: #ffffff; border: 1px solid #d8e2eb; border-radius: 6px; alternate-background-color: #f6f9fb; }
            QHeaderView::section { background: #eaf1f5; color: #29445e; padding: 7px; border: 0; font-weight: 600; }
            QPushButton { background: #e7eef3; color: #203a54; border: 1px solid #cbd8e2; border-radius: 6px; padding: 8px 13px; }
            QPushButton:hover:enabled { background: #dce9ef; }
            QPushButton:disabled { color: #8797a5; background: #eef2f5; }
            QProgressBar { background: #e5edf2; border: 0; border-radius: 5px; height: 12px; text-align: center; }
            QProgressBar::chunk { background: #15989a; border-radius: 5px; }
            QToolTip { background: #17334d; color: white; border: 0; padding: 6px; }
        """)

    def _setup_media(self):
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player.setAudioOutput(self.audio)
        self.player.errorOccurred.connect(self._media_error)

    def _build(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.scan_page = QWidget()
        self.review_page = QWidget()
        self.tabs.addTab(self.scan_page, "Find duplicates")
        self.tabs.addTab(self.review_page, "Review")
        self._build_scan()
        self._build_review()

    def _build_scan(self):
        root = QVBoxLayout(self.scan_page)
        root.setContentsMargins(20, 18, 20, 16); root.setSpacing(12)
        row = QHBoxLayout()
        root.addWidget(QLabel("Source folders (Ctrl/Shift-click to select multiple)"))
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        row.addWidget(self.source_list, 1)
        side = QVBoxLayout()
        self.add_button = QPushButton("Add folder…", clicked=self._add_source)
        self.remove_button = QPushButton("Remove selected", clicked=self._remove_sources)
        side.addWidget(self.add_button); side.addWidget(self.remove_button); side.addStretch()
        row.addLayout(side)
        root.addLayout(row)
        destrow = QHBoxLayout(); destrow.addWidget(QLabel("Destination folder:"))
        self.dest_label = QLabel("Not selected"); self.dest_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        destrow.addWidget(self.dest_label, 1)
        self.dest_button = QPushButton("Choose…", clicked=self._choose_destination); destrow.addWidget(self.dest_button)
        root.addLayout(destrow)
        self.summary = QLabel("Choose source and destination folders, then start the scan."); self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.results_tabs = QTabWidget(); root.addWidget(self.results_tabs, 1)
        self.group_tree = QTreeWidget(); self.group_tree.setHeaderLabels(["Group / file", "Files / size"])
        self.group_tree.setColumnWidth(0, 650); self.results_tabs.addTab(self.group_tree, "Duplicate images")
        self.video_tree = QTreeWidget(); self.video_tree.setHeaderLabels(["Group / file", "Files / size"]); self.results_tabs.addTab(self.video_tree, "Duplicate videos")
        self.pdf_tree = QTreeWidget(); self.pdf_tree.setHeaderLabels(["Group / file", "Files / size"]); self.results_tabs.addTab(self.pdf_tree, "Duplicate PDFs")
        self.issue_tree = QTreeWidget(); self.issue_tree.setHeaderLabels(["Path", "Message"])
        self.results_tabs.addTab(self.issue_tree, "Issues")
        for tree in (self.group_tree, self.video_tree, self.pdf_tree):
            tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tree.customContextMenuRequested.connect(lambda point, tree=tree: self._result_context_menu(tree, point))
            tree.installEventFilter(self)
        controls = QHBoxLayout(); self.progress = QProgressBar(); controls.addWidget(self.progress, 1)
        self.status = QLabel("Ready"); controls.addWidget(self.status); root.addLayout(controls)
        actions = QHBoxLayout()
        self.copy_paths_button = QPushButton("Copy paths", clicked=self._copy_selected_paths)
        self.copy_paths_button.setToolTip("Copy selected file paths. Select a file or group; Ctrl+C also works.")
        actions.addWidget(self.copy_paths_button); actions.addStretch()
        self.cancel_button = QPushButton("Cancel", clicked=self._cancel); self.cancel_button.setEnabled(False)
        self.scan_button = QPushButton("Start scan", clicked=self._start_scan)
        self.full_rescan_button = QPushButton("Full rescan", clicked=self._start_full_rescan)
        self.export_button = QPushButton("Export results", clicked=self._start_export); self.export_button.setEnabled(False)
        self._update_export_tooltip()
        actions.addWidget(self.cancel_button); actions.addWidget(self.scan_button); actions.addWidget(self.full_rescan_button); actions.addWidget(self.export_button); root.addLayout(actions)

    def _build_review(self):
        root = QVBoxLayout(self.review_page)
        top = QHBoxLayout(); top.addWidget(QLabel("Source folder:"))
        self.review_root_label = QLabel("No folder selected"); self.review_root_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(self.review_root_label, 1)
        self.review_choose = QPushButton("Choose folder…", clicked=self._choose_review_root); top.addWidget(self.review_choose)
        root.addLayout(top)
        self.preview_stack = QStackedWidget()
        self.review_preview = QLabel("Choose a folder to review images, videos, and PDFs.")
        self.review_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.review_preview.setMinimumSize(300, 300); self.review_preview.setStyleSheet("background:#171717;color:#ddd")
        self.video = QVideoWidget()
        self.video.setMinimumSize(300, 300)
        self.video.setStyleSheet("background:#171717")
        self.preview_stack.addWidget(self.review_preview)
        self.preview_stack.addWidget(self.video)
        root.addWidget(self.preview_stack, 1)
        pdf_navigation = QHBoxLayout()
        self.pdf_previous_button = QPushButton("Previous page", clicked=lambda: self._change_pdf_page(-1))
        self.pdf_next_button = QPushButton("Next page", clicked=lambda: self._change_pdf_page(1))
        self.pdf_previous_button.setEnabled(False); self.pdf_next_button.setEnabled(False)
        pdf_navigation.addStretch(); pdf_navigation.addWidget(self.pdf_previous_button); pdf_navigation.addWidget(self.pdf_next_button); pdf_navigation.addStretch()
        root.addLayout(pdf_navigation)
        self.review_path = QLabel(""); self.review_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.review_path)
        playback = QHBoxLayout()
        self.play_button = QPushButton("Play", clicked=self._toggle_play); self.play_button.setEnabled(False)
        self.seek = QSlider(Qt.Orientation.Horizontal); self.seek.setRange(0, 0); self.seek.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.seek.sliderMoved.connect(self.player.setPosition)
        self.player.positionChanged.connect(self.seek.setValue); self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.volume = QSlider(Qt.Orientation.Horizontal); self.volume.setRange(0, 100); self.volume.setValue(70); self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        playback.addWidget(self.play_button); playback.addWidget(self.seek, 1); playback.addWidget(QLabel("Volume")); playback.addWidget(self.volume)
        root.addLayout(playback)
        self.player.setVideoOutput(self.video)
        self.media_error_label = QLabel(""); root.addWidget(self.media_error_label)
        self.open_player = QPushButton("Open in default app", clicked=self._open_default); self.open_player.hide(); root.addWidget(self.open_player)
        self.review_counts = QLabel("Kept: 0   Discarded: 0   Unreviewed: 0"); root.addWidget(self.review_counts)
        self.review_position = QLabel("No items"); root.addWidget(self.review_position)
        buttons = QHBoxLayout()
        self.previous_button = QPushButton("Previous (Backspace)", clicked=self._previous)
        self.skip_button = QPushButton("Skip (S)", clicked=self._skip)
        self.discard_button = QPushButton("Discard  (A / ←)", clicked=lambda: self._decide("discard"))
        self.keep_button = QPushButton("Keep  (D / →)", clicked=lambda: self._decide("keep"))
        for button in (self.previous_button, self.skip_button, self.discard_button, self.keep_button):
            button.setMinimumHeight(46)
        self.discard_button.setToolTip("Mark this file as discarded. The original stays untouched.")
        self.keep_button.setToolTip("Mark this file to include in a kept-files export.")
        self.discard_button.setStyleSheet("QPushButton { background: #865260; color: white; font-weight: bold; border-radius: 5px; } QPushButton:hover { background: #704250; }")
        self.keep_button.setStyleSheet("QPushButton { background: #248574; color: white; font-weight: bold; border-radius: 5px; } QPushButton:hover { background: #1b6b5d; }")
        buttons.addWidget(self.previous_button, 1)
        buttons.addWidget(self.skip_button, 1)
        buttons.addWidget(self.discard_button, 2)
        buttons.addWidget(self.keep_button, 2)
        root.addLayout(buttons)
        self.export_kept_button = QPushButton("Export kept…", clicked=self._export_kept); root.addWidget(self.export_kept_button)
        self.review_hints = QLabel("A / ← Discard    D / → Keep    S Skip    Backspace Previous    Space Play/Pause    PageUp / PageDown PDF pages")
        self.review_hints.setStyleSheet("font-weight: 600; color: #444")
        root.addWidget(self.review_hints)
        self._make_shortcut("A", lambda: self._decide("discard")); self._make_shortcut("Left", lambda: self._decide("discard"))
        self._make_shortcut("D", lambda: self._decide("keep")); self._make_shortcut("Right", lambda: self._decide("keep"))
        self._make_shortcut("S", self._skip); self._make_shortcut("Backspace", self._previous); self._make_shortcut("Space", self._toggle_play)
        self._make_shortcut("PgUp", lambda: self._change_pdf_page(-1)); self._make_shortcut("PgDown", lambda: self._change_pdf_page(1))
        # Every button has a short English explanation, including controls whose
        # action is temporarily unavailable.
        for button in self.findChildren(QPushButton):
            if not button.toolTip():
                button.setToolTip(f"{button.text()} — perform this action.")
        for button, tip in ((self.add_button, "Add one or more source folders to scan."),
                            (self.remove_button, "Remove the selected source folders."),
                            (self.dest_button, "Choose where duplicate files will be exported."),
                            (self.scan_button, "Scan the selected folders for duplicate images, videos, and PDFs."),
                            (self.full_rescan_button, "Scan again and rebuild the saved scan data."),
                            (self.cancel_button, "Cancel the current scan or export operation."),
                            (self.review_choose, "Choose a folder containing images, videos, and PDFs to review."),
                            (self.pdf_previous_button, "Show the previous page of the current PDF."),
                            (self.pdf_next_button, "Show the next page of the current PDF."),
                            (self.play_button, "Play or pause the current video."),
                            (self.previous_button, "Return to the previous review item (Backspace)."),
                            (self.skip_button, "Leave this item undecided and move to another (S)."),
                            (self.export_kept_button, "Copy kept files to a destination folder."),
                            (self.open_player, "Open this file in your system's default media app.")):
            button.setToolTip(tip)
        self._update_export_tooltip()

    def _make_shortcut(self, key, callback):
        shortcut = QShortcut(QKeySequence(key), self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(lambda: self._review_shortcut(callback))

    def _review_shortcut(self, callback):
        widget = QApplication.focusWidget()
        if widget and widget.inherits("QLineEdit"):
            return
        if self.tabs.currentWidget() is self.review_page:
            callback()

    def _add_source(self):
        try:
            if os.name == "nt": paths = pick_folders(int(self.winId()), "Select source folders")
            else:
                path = QFileDialog.getExistingDirectory(self, "Select source folder")
                paths = [Path(path)] if path else []
        except OSError as exc:
            QMessageBox.critical(self, "Folder selection failed", str(exc)); return
        known = {os.path.normcase(str(p.resolve())) for p in self.sources}
        for path in paths:
            path = path.resolve()
            if path.is_dir() and os.path.normcase(str(path)) not in known:
                known.add(os.path.normcase(str(path))); self.sources.append(path); self.source_list.addItem(str(path))
        self._invalidate_scan()

    def _remove_sources(self):
        for item in self.source_list.selectedItems():
            index = self.source_list.row(item); self.source_list.takeItem(index); del self.sources[index]
        self._invalidate_scan()

    def _choose_destination(self):
        path = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if path: self.destination = Path(path); self.dest_label.setText(path); self._invalidate_scan()

    def _invalidate_scan(self):
        self.result = None; self.export_button.setEnabled(False); self._clear_results()
        self._update_export_tooltip()
        self.summary.setText("Settings changed. Start the scan again.")

    def _clear_results(self): self.group_tree.clear(); self.video_tree.clear(); self.pdf_tree.clear(); self.issue_tree.clear()

    def _start_scan(self):
        if self.busy: return
        if not self.sources:
            QMessageBox.warning(self, "No source folders", "Please add at least one source folder."); return
        if self.destination is None:
            QMessageBox.warning(self, "No destination folder", "Please choose a destination folder."); return
        self.result = None; self.export_button.setEnabled(False); self._update_export_tooltip(); self._clear_results(); self.summary.setText("Preparing scan…")
        self._start_job(scan_sources, list(self.sources), self.destination, "Scan")

    def _start_full_rescan(self):
        if self.busy or not self.sources or self.destination is None: return
        self.result = None; self.export_button.setEnabled(False); self._update_export_tooltip(); self._clear_results(); self.summary.setText("Preparing full rescan…")
        self._start_job(partial(scan_sources, full_rescan=True), list(self.sources), self.destination, "Full rescan")

    def _start_export(self):
        if self.busy:
            return
        if self.result is not None and self.destination is not None:
            self._start_job(partial(export_scan, sources=list(self.sources)), self.result, self.destination, "Export")

    def _start_job(self, fn, *args):
        title = args[-1]; args = args[:-1]
        self.busy = True; self.progress.setValue(0); self.status.setText(f"Preparing {title.lower()}…")
        for button in (self.add_button, self.remove_button, self.dest_button, self.scan_button, self.full_rescan_button): button.setEnabled(False)
        self.cancel_button.setEnabled(True); self.export_button.setEnabled(False)
        self._update_export_tooltip()
        self.job = Job(fn, *args); self.job.signals.progress.connect(self._progress); self.job.signals.done.connect(lambda r: self._job_done(r, title))
        self.job.signals.failed.connect(lambda e: self._job_failed(e, title)); self.job.signals.cancelled.connect(lambda: self._job_cancelled(title)); self._launch_job(self.job)

    def _launch_job(self, job):
        self._threads.add(job)
        job.finished.connect(lambda job=job: self._thread_finished(job))
        job.start()

    def _thread_finished(self, job):
        self._threads.discard(job)
        job.deleteLater()

    def _progress(self, done, total, label):
        self.progress.setMaximum(max(total, 1)); self.progress.setValue(done); self.status.setText(label)

    def _finish_job(self):
        self.busy = False
        for button in (self.add_button, self.remove_button, self.dest_button, self.scan_button, self.full_rescan_button): button.setEnabled(True)
        self.cancel_button.setEnabled(False); self.export_button.setEnabled(self.result is not None)
        self._update_export_tooltip()

    def _job_done(self, outcome, title):
        if title in {"Scan", "Full rescan"}:
            self.result = outcome
            self._finish_job()
            self._render_result(outcome); self.status.setText("Scan complete")
        else:
            self._finish_job()
            self.status.setText("Export complete" if not outcome.cancelled else "Export cancelled")
            self._render_result(self.result)
            for issue in outcome.issues: self._add_issue(issue.path, issue.message)
            QMessageBox.information(self, "Export", f"Export folder:\n{outcome.run_dir}\n\nImages: {outcome.images_copied}\nVideos: {outcome.videos_copied}\nPDFs: {outcome.pdfs_copied}\nIssues: {len(outcome.issues)}")

    def _job_failed(self, error, title):
        self._finish_job(); self.status.setText("Error"); QMessageBox.critical(self, f"{title} failed", error)

    def _job_cancelled(self, title): self._finish_job(); self.status.setText(f"{title} cancelled")

    def _update_export_tooltip(self):
        if self.busy:
            self.export_button.setToolTip("Export is unavailable while another operation is running.")
        elif getattr(self, "result", None) is None:
            self.export_button.setToolTip("Run a scan to enable exporting duplicate results.")
        else:
            self.export_button.setToolTip("Export the current scan results to the destination folder.")

    def _copy_selected_paths(self):
        paths = []
        seen = set()
        tree = self.results_tabs.currentWidget()
        if tree in (self.group_tree, self.video_tree, self.pdf_tree):
            selected_set = set(tree.selectedItems())
            def visit(item, covered=False):
                covered = covered or item in selected_set
                if item.childCount() == 0 and covered:
                    path = item.text(0)
                    if path and not path.startswith("Group ") and path not in seen:
                        seen.add(path); paths.append(path)
                for index in range(item.childCount()):
                    visit(item.child(index), covered)
            for index in range(tree.topLevelItemCount()):
                visit(tree.topLevelItem(index))
        clipboard = QApplication.clipboard()
        if paths:
            clipboard.setText("\n".join(paths))
            self.status.setText(f"Copied {len(paths)} path{'s' if len(paths) != 1 else ''}")
        else:
            self.status.setText("Select a file or duplicate group to copy paths")

    def _result_context_menu(self, tree, point):
        item = tree.itemAt(point)
        if item and not item.isSelected():
            tree.clearSelection(); item.setSelected(True)
        menu = QMenu(tree)
        action = menu.addAction("Copy paths")
        action.triggered.connect(self._copy_selected_paths)
        menu.exec(tree.viewport().mapToGlobal(point))

    def eventFilter(self, watched, event):
        if watched in (getattr(self, "group_tree", None), getattr(self, "video_tree", None), getattr(self, "pdf_tree", None)) and event.type() == QEvent.Type.KeyPress:
            if event.matches(QKeySequence.StandardKey.Copy):
                self._copy_selected_paths()
                return True
        return super().eventFilter(watched, event)
    def _cancel(self):
        if self.job: self.job.cancel_flag.set(); self.cancel_button.setEnabled(False); self.status.setText("Cancelling…")

    def _render_result(self, result):
        self._clear_results()
        def render_groups(tree, groups):
            duplicates = [g for g in groups if len(g.files) > 1]
            count = 0
            for index, group in enumerate(duplicates, 1):
                fingerprint = group.fingerprint or "unavailable"
                node = QTreeWidgetItem([f"Group {index} · {fingerprint[:12]}", str(len(group.files))]); tree.addTopLevelItem(node)
                count += len(group.files)
                for record in group.files: node.addChild(QTreeWidgetItem([str(record.path), self._format_size(record.size)]))
            return duplicates, count
        groups, count = render_groups(self.group_tree, result.groups)
        video_groups, video_count = render_groups(self.video_tree, result.video_groups)
        pdf_groups, pdf_count = render_groups(self.pdf_tree, result.pdf_groups)
        for issue in result.issues: self._add_issue(issue.path, issue.message)
        self.summary.setText(f"Images: {len(result.groups)} groups / {len(groups)} duplicate groups ({count} files)   |   Videos: {len(result.video_groups)} groups / {len(video_groups)} duplicate groups ({video_count} files)   |   PDFs: {len(result.pdf_groups)} groups / {len(pdf_groups)} duplicate groups ({pdf_count} files)   |   Ignored: {result.ignored}   |   Issues: {len(result.issues)}   |   Files scanned: {result.total}")

    def _add_issue(self, path, message): self.issue_tree.addTopLevelItem(QTreeWidgetItem([str(path), message]))
    @staticmethod
    def _format_size(size):
        if size < 1024: return f"{size} B"
        if size < 1024 * 1024: return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def _choose_review_root(self):
        path = QFileDialog.getExistingDirectory(self, "Select review source folder")
        if path: self._open_review(Path(path))

    def _open_review(self, root):
        self.player.stop()
        self._preview_generation += 1
        self.pool.clear()
        self.review_root_label.setText(str(root)); self.review_preview.setText("Preparing review…"); self.review_preview.setPixmap(QPixmap())
        self.review_choose.setEnabled(False)
        worker = Job(ReviewSession.open, root)
        worker.signals.done.connect(lambda session: self._review_loaded(session, root))
        worker.signals.failed.connect(lambda error: (self.review_choose.setEnabled(True), QMessageBox.critical(self, "Review failed", error)))
        self._review_open_job = worker; self._launch_job(worker)

    def _review_loaded(self, session, root):
        if self.session: self.session.close()
        self.session = session; self._review_root = root; self.review_items = session.items
        self._review_skipped.clear()
        self._review_history.clear()
        self.review_index = next((i for i, item in enumerate(self.review_items) if item.decision is None), -1)
        self._pdf_page = 0; self._pdf_page_count = 0; self._pdf_current_path = None
        self.review_choose.setEnabled(True); self._update_review()

    def _update_review(self):
        self._preview_generation += 1
        generation = self._preview_generation
        self.pool.clear()
        self.player.stop(); self.play_button.setText("Play"); self.media_error_label.clear(); self.open_player.hide()
        self.pdf_previous_button.setEnabled(False); self.pdf_next_button.setEnabled(False)
        counts = self.session.counts if self.session else {"keep": 0, "discard": 0, "unreviewed": 0}
        self.review_counts.setText(f"Kept: {counts['keep']}   Discarded: {counts['discard']}   Unreviewed: {counts['unreviewed']}")
        if not self.review_items:
            self.review_index = -1
            self.review_path.clear(); self.review_position.setText("No media found"); self.review_preview.setText("No supported media in this folder."); self.preview_stack.setCurrentWidget(self.review_preview); self.play_button.setEnabled(False); return
        if self.review_index < 0:
            self.review_path.clear()
            unreviewed = counts["unreviewed"]
            if unreviewed:
                self.review_position.setText("No other unreviewed items")
                self.review_preview.setText(f"{unreviewed} unreviewed item(s) were skipped. Press Backspace to revisit the last item.")
            else:
                self.review_position.setText("Review complete")
                self.review_preview.setText("All items have a Keep or Discard decision. You can use Backspace to revisit your last decision.")
            self.preview_stack.setCurrentWidget(self.review_preview); self.play_button.setEnabled(False); self.seek.setEnabled(False); return
        self.review_index = min(self.review_index, len(self.review_items)-1); item = self.review_items[self.review_index]
        if item.kind == "pdf" and self._pdf_current_path != item.path:
            self._pdf_current_path = item.path; self._pdf_page = 0; self._pdf_page_count = 0
        self.seek.setEnabled(item.kind == "video")
        self.review_position.setText(f"Item {self.review_index+1} of {len(self.review_items)}")
        state = "Skipped · still unreviewed" if self.review_index in self._review_skipped and item.decision is None else (item.decision or "Unreviewed")
        self.review_path.setText(f"{item.path}  ·  {state}")
        if item.kind == "video":
            self.preview_stack.setCurrentWidget(self.video); self.play_button.setEnabled(True); self.player.setSource(QUrl.fromLocalFile(str(item.path)))
        elif item.kind == "pdf":
            self.preview_stack.setCurrentWidget(self.review_preview)
            self.review_preview.setText("Loading PDF page…"); self.review_preview.setPixmap(QPixmap()); self.play_button.setEnabled(False)
            task = PdfPreview(generation, item.path, self._pdf_page, (max(300, self.review_preview.width()), max(300, self.review_preview.height())))
            task.signals.ready.connect(self._preview_ready); self.pool.start(task)
        else:
            self.preview_stack.setCurrentWidget(self.review_preview)
            self.review_preview.setText("Loading preview…"); self.play_button.setEnabled(False)
            task = ImagePreview(generation, item.path, (max(300,self.review_preview.width()), max(300,self.review_preview.height())))
            task.signals.ready.connect(self._preview_ready); self.pool.start(task)

    def _preview_ready(self, generation, image, page_count, error):
        if generation != self._preview_generation or not 0 <= self.review_index < len(self.review_items) or self.review_items[self.review_index].kind not in {"image", "pdf"}: return
        item = self.review_items[self.review_index]
        if item.kind == "pdf" and image is None:
            self.review_preview.setText(f"Unable to display PDF: {error}\nUse Open in default app to view it.")
            self.media_error_label.setText("PDF preview failed. The file may be password protected or damaged.")
            self.pdf_previous_button.setEnabled(False); self.pdf_next_button.setEnabled(False)
            self.open_player.show(); return
        if image is None: self.review_preview.setText(f"Unable to display image: {error}"); return
        if item.kind == "pdf":
            self._pdf_page_count = page_count
            self.review_position.setText(f"Item {self.review_index+1} of {len(self.review_items)} · Page {self._pdf_page+1} of {self._pdf_page_count}")
            self.pdf_previous_button.setEnabled(self._pdf_page > 0)
            self.pdf_next_button.setEnabled(self._pdf_page + 1 < self._pdf_page_count)
        pixmap = QPixmap.fromImage(image).scaled(self.review_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.review_preview.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if 0 <= self.review_index < len(self.review_items) and self.review_items[self.review_index].kind in {"image", "pdf"}: self._update_review()

    def _change_pdf_page(self, delta):
        if not (0 <= self.review_index < len(self.review_items)) or self.review_items[self.review_index].kind != "pdf" or not self._pdf_page_count:
            return
        page = min(max(self._pdf_page + delta, 0), self._pdf_page_count - 1)
        if page != self._pdf_page:
            self._pdf_page = page
            self._update_review()

    def _next_undecided(self, start):
        if not self.review_items:
            return -1
        count = len(self.review_items)
        for offset in range(count):
            index = (start + offset) % count
            if self.review_items[index].decision is None:
                return index
        return -1

    def _decide(self, decision):
        if not self.session or not 0 <= self.review_index < len(self.review_items): return
        current = self.review_index
        self.session.set_decision(self.review_items[current], decision)
        self._review_history.append(current)
        self._review_skipped.discard(current)
        self.review_index = self._next_undecided((current + 1) % len(self.review_items))
        self._update_review()
    def _skip(self):
        if not 0 <= self.review_index < len(self.review_items):
            return
        current = self.review_index
        self._review_history.append(current)
        self._review_skipped.add(current)
        # Move to another undecided item, wrapping once. If this is the only
        # undecided item, leave it marked as skipped and show a clear end state.
        next_index = -1
        for offset in range(1, len(self.review_items)):
            candidate = (current + offset) % len(self.review_items)
            if self.review_items[candidate].decision is None and candidate not in self._review_skipped:
                next_index = candidate
                break
        self.review_index = next_index
        self._update_review()
    def _previous(self):
        if not self.review_items:
            return
        if self._review_history:
            self.review_index = self._review_history.pop()
        elif self.review_index < 0:
            self.review_index = len(self.review_items) - 1
        else:
            self.review_index = (self.review_index - 1) % len(self.review_items)
        self._update_review()
    def _toggle_play(self):
        if not (0 <= self.review_index < len(self.review_items)) or self.review_items[self.review_index].kind != "video":
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.player.pause(); self.play_button.setText("Play")
        else: self.player.play(); self.play_button.setText("Pause")
    def _media_error(self, error, text):
        if (error != QMediaPlayer.Error.NoError and 0 <= self.review_index < len(self.review_items)
                and self.review_items[self.review_index].kind == "video"
                and self.player.source() == QUrl.fromLocalFile(str(self.review_items[self.review_index].path))):
            self.media_error_label.setText(f"Playback failed: {text or 'unknown media error'}"); self.open_player.show()
    def _open_default(self):
        if 0 <= self.review_index < len(self.review_items):
            path = str(self.review_items[self.review_index].path)
            try:
                if os.name == "nt": os.startfile(path)
                elif sys.platform == "darwin": subprocess.Popen(["open", path])
                else: subprocess.Popen(["xdg-open", path])
            except OSError as exc: QMessageBox.critical(self, "Unable to open media", str(exc))
    def _export_kept(self):
        if not self.session: return
        if self.session.counts["keep"] == 0:
            QMessageBox.information(self, "Export kept", "There are no kept items to export yet.")
            return
        destination = QFileDialog.getExistingDirectory(self, "Choose export destination")
        if not destination: return
        if Path(destination).resolve() == self._review_root.resolve() or self._review_root.resolve() in Path(destination).resolve().parents:
            QMessageBox.warning(self, "Invalid destination", "Choose a destination outside the review source folder."); return
        self.review_choose.setEnabled(False); self.export_kept_button.setEnabled(False)
        job = Job(self.session.export_kept, Path(destination)); job.signals.progress.connect(self._progress)
        job.signals.done.connect(self._review_export_done); job.signals.failed.connect(lambda e: QMessageBox.critical(self, "Export failed", e))
        job.finished.connect(lambda: (self.review_choose.setEnabled(True), self.export_kept_button.setEnabled(True)))
        self._review_export_job = job; self._launch_job(job)
    def _review_export_done(self, result):
        pdf_count = sum(1 for item in self.session.items if item.decision == "keep" and item.kind == "pdf")
        self._update_review(); QMessageBox.information(self, "Export kept", f"Export folder:\n{result.folder}\nPDFs copied: {pdf_count}\nIssues: {len(result.issues)}")

    def closeEvent(self, event):
        running = [job for job in self._threads if job.isRunning()]
        if running:
            QMessageBox.information(self, "MediaSift is busy", "Wait for the current operation to finish before closing MediaSift.")
            event.ignore()
            return
        self.player.stop()
        if self.session: self.session.close()
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = MediaSiftApp()
    window.show()
    # Resume the last available review session asynchronously at startup.
    last = ReviewSession.last_root()
    if last and Path(last).is_dir(): window._open_review(Path(last))
    return app.exec()

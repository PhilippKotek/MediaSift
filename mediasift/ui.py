"""Tkinter user interface for MediaSift."""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .core import scan_sources
from .exporter import export_scan
from .folder_picker import pick_folders
from .models import ScanCancelled, ScanResult


class MediaSiftApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MediaSift – Find Duplicates")
        self.root.geometry("900x650")
        self.root.minsize(700, 500)
        self.sources: list[Path] = []
        self.destination: Path | None = None
        self.result: ScanResult | None = None
        self.events: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.busy = False
        self._build()
        self.root.after(100, self._drain_events)

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer = ttk.Frame(self.root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)

        ttk.Label(outer, text="Source folders (Ctrl/Shift-click to select multiple)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        source_row = ttk.Frame(outer)
        source_row.grid(row=1, column=0, sticky="ew", pady=(5, 10))
        source_row.columnconfigure(0, weight=1)
        self.source_list = tk.Listbox(source_row, height=4, selectmode=tk.EXTENDED, activestyle="dotbox")
        self.source_list.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sb = ttk.Scrollbar(source_row, orient="vertical", command=self.source_list.yview)
        sb.grid(row=0, column=1, rowspan=2, sticky="ns")
        self.source_list.configure(yscrollcommand=sb.set)
        self.add_button = ttk.Button(source_row, text="Add folder…", command=self._add_source)
        self.add_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        self.remove_button = ttk.Button(source_row, text="Remove selected", command=self._remove_sources)
        self.remove_button.grid(row=1, column=2, sticky="ew", padx=(8, 0), pady=(5, 0))

        dest = ttk.Frame(outer)
        dest.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        dest.columnconfigure(1, weight=1)
        ttk.Label(dest, text="Destination folder:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.destination_var = tk.StringVar(value="Not selected")
        ttk.Label(dest, textvariable=self.destination_var).grid(row=0, column=1, sticky="ew")
        self.destination_button = ttk.Button(dest, text="Choose…", command=self._choose_destination)
        self.destination_button.grid(row=0, column=2, padx=(8, 0))

        results = ttk.LabelFrame(outer, text="Scan results", padding=8)
        results.grid(row=3, column=0, sticky="nsew")
        outer.rowconfigure(3, weight=1)
        results.columnconfigure(0, weight=1)
        results.rowconfigure(1, weight=1)
        self.summary_var = tk.StringVar(value="Choose source and destination folders, then start the scan.")
        ttk.Label(results, textvariable=self.summary_var, wraplength=820).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.tabs = ttk.Notebook(results)
        self.tabs.grid(row=1, column=0, sticky="nsew")
        duplicates = ttk.Frame(self.tabs, padding=5)
        issues = ttk.Frame(self.tabs, padding=5)
        self.tabs.add(duplicates, text="Duplicate images")
        self.tabs.add(issues, text="Issues")
        duplicates.columnconfigure(0, weight=1)
        duplicates.rowconfigure(0, weight=1)
        issues.columnconfigure(0, weight=1)
        issues.rowconfigure(0, weight=1)
        self.group_tree = ttk.Treeview(duplicates, columns=("count",), show="tree headings")
        self.group_tree.heading("#0", text="Group / file")
        self.group_tree.heading("count", text="Files")
        self.group_tree.column("#0", width=650, stretch=True)
        self.group_tree.column("count", width=90, anchor="center", stretch=False)
        self.group_tree.grid(row=0, column=0, sticky="nsew")
        group_scroll = ttk.Scrollbar(duplicates, orient="vertical", command=self.group_tree.yview)
        group_scroll.grid(row=0, column=1, sticky="ns")
        self.group_tree.configure(yscrollcommand=group_scroll.set)
        self.issue_tree = ttk.Treeview(issues, columns=("message",), show="headings")
        self.issue_tree.heading("#0", text="Path")
        self.issue_tree["show"] = "tree headings"
        self.issue_tree.heading("#0", text="Path")
        self.issue_tree.heading("message", text="Message")
        self.issue_tree.column("#0", width=400, stretch=True)
        self.issue_tree.column("message", width=430, stretch=True)
        self.issue_tree.grid(row=0, column=0, sticky="nsew")
        issue_scroll = ttk.Scrollbar(issues, orient="vertical", command=self.issue_tree.yview)
        issue_scroll.grid(row=0, column=1, sticky="ns")
        self.issue_tree.configure(yscrollcommand=issue_scroll.set)

        controls = ttk.Frame(outer)
        controls.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        controls.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(controls, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(controls, textvariable=self.status_var, width=28).grid(row=0, column=1, sticky="e")
        actions = ttk.Frame(outer)
        actions.grid(row=5, column=0, sticky="e", pady=(10, 0))
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(0, 8))
        self.scan_button = ttk.Button(actions, text="Start scan", command=self._start_scan)
        self.scan_button.pack(side="left", padx=(0, 8))
        self.export_button = ttk.Button(actions, text="Export results", command=self._start_export, state="disabled")
        self.export_button.pack(side="left")

    def _add_source(self) -> None:
        try:
            if os.name == "nt":
                paths = pick_folders(self.root.winfo_id(), "Select source folders")
            else:
                path = filedialog.askdirectory(title="Select source folders", parent=self.root)
                paths = [Path(path)] if path else []
        except OSError as exc:
            messagebox.showerror("Folder selection failed", str(exc), parent=self.root)
            return
        known = {os.path.normcase(str(source.resolve())) for source in self.sources}
        added = False
        for path in paths:
            source = path.resolve()
            key = os.path.normcase(str(source))
            if source.is_dir() and key not in known:
                known.add(key)
                self.sources.append(source)
                self.source_list.insert(tk.END, str(source))
                added = True
        if added:
            self._invalidate_scan()

    def _remove_sources(self) -> None:
        indexes = list(self.source_list.curselection())
        for index in reversed(indexes):
            self.source_list.delete(index)
            del self.sources[index]
        if indexes:
            self._invalidate_scan()

    def _choose_destination(self) -> None:
        path = filedialog.askdirectory(title="Select destination folder", parent=self.root)
        if path:
            self.destination = Path(path)
            self.destination_var.set(str(self.destination))
            self._invalidate_scan()

    def _invalidate_scan(self) -> None:
        self.result = None
        self.export_button.configure(state="disabled")
        self._clear_results()
        self.summary_var.set("Settings changed. Start the scan again.")

    def _clear_results(self) -> None:
        for tree in (self.group_tree, self.issue_tree):
            for item in tree.get_children(""):
                tree.delete(item)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in (self.add_button, self.remove_button, self.destination_button, self.scan_button):
            widget.configure(state=state)
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self.export_button.configure(state="disabled" if busy or self.result is None else "normal")

    def _start_scan(self) -> None:
        if self.busy:
            return
        if not self.sources:
            messagebox.showwarning("No source folders", "Please add at least one source folder.", parent=self.root)
            return
        if self.destination is None:
            messagebox.showwarning("No destination folder", "Please choose a destination folder.", parent=self.root)
            return
        self.result = None
        self.export_button.configure(state="disabled")
        self._clear_results()
        self.summary_var.set("Preparing scan…")
        self.progress.configure(value=0)
        self.cancel_event.clear()
        self._set_busy(True)
        sources, destination = list(self.sources), self.destination
        threading.Thread(target=self._scan_worker, args=(sources, destination), daemon=True).start()

    def _scan_worker(self, sources: list[Path], destination: Path) -> None:
        try:
            result = scan_sources(sources, destination, progress=self._throttled_progress(), cancelled=self.cancel_event.is_set)
            self.events.put(("scan_done", result))
        except ScanCancelled:
            self.events.put(("cancelled", "Scan"))
        except Exception as exc:
            self.events.put(("error", "Scan failed", str(exc)))

    def _start_export(self) -> None:
        if self.busy or self.result is None or self.destination is None:
            return
        result, destination = self.result, self.destination
        self.cancel_event.clear()
        self.progress.configure(value=0)
        self.status_var.set("Preparing export…")
        self._set_busy(True)
        threading.Thread(target=self._export_worker, args=(result, destination), daemon=True).start()

    def _export_worker(self, result: ScanResult, destination: Path) -> None:
        try:
            outcome = export_scan(result, destination, progress=self._throttled_progress(), cancelled=self.cancel_event.is_set)
            self.events.put(("export_done", outcome))
        except ScanCancelled:
            self.events.put(("cancelled", "Export"))
        except Exception as exc:
            self.events.put(("error", "Export failed", str(exc)))

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Cancelling…")

    def _throttled_progress(self):
        last_update = 0.0

        def report(done: int, total: int, label: str) -> None:
            nonlocal last_update
            now = time.monotonic()
            if done == total or now - last_update >= 0.1:
                last_update = now
                self.events.put(("progress", done, total, Path(label).name))

        return report

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    _, done, total, label = event
                    self.progress.configure(maximum=max(total, 1), value=done)
                    self.status_var.set(str(label))
                elif kind == "scan_done":
                    self.result = event[1]
                    self._render_result(self.result)
                    self._set_busy(False)
                    self.status_var.set("Scan complete")
                    self.progress.configure(value=self.progress["maximum"])
                elif kind == "export_done":
                    outcome = event[1]
                    self._set_busy(False)
                    self.status_var.set("Export complete" if not outcome.cancelled else "Export cancelled")
                    if self.result is not None:
                        self._render_result(self.result)
                    for issue in outcome.issues:
                        self.issue_tree.insert("", "end", text=str(issue.path), values=(issue.message,))
                    if outcome.issues:
                        self.summary_var.set(f"{self.summary_var.get()}   |   Export issues: {len(outcome.issues)}")
                    messagebox.showinfo("Export", f"Export folder:\n{outcome.run_dir}\n\nImages: {outcome.images_copied}\nVideos: {outcome.videos_copied}\nIssues: {len(outcome.issues)}", parent=self.root)
                elif kind == "cancelled":
                    self._set_busy(False)
                    self.status_var.set(f"{event[1]} cancelled")
                elif kind == "error":
                    self._set_busy(False)
                    self.status_var.set("Error")
                    messagebox.showerror(event[1], event[2], parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _render_result(self, result: ScanResult) -> None:
        self._clear_results()
        duplicate_groups = [group for group in result.groups if len(group.files) > 1]
        dup_files = 0
        for index, group in enumerate(duplicate_groups, 1):
            iid = self.group_tree.insert("", "end", text=f"Group {index} · {group.fingerprint[:12]}", values=(len(group.files),), open=False)
            dup_files += len(group.files)
            for file in group.files:
                self.group_tree.insert(iid, "end", text=str(file.path), values=(self._format_size(file.size),))
        for issue in result.issues:
            self.issue_tree.insert("", "end", text=str(issue.path), values=(issue.message,))
        self.summary_var.set(f"Unique images: {len(result.groups)}   |   Duplicate groups: {len(duplicate_groups)}   |   Files in duplicate groups: {dup_files}   |   Videos: {len(result.videos)}   |   Ignored: {result.ignored}   |   Issues: {len(result.issues)}   |   Files scanned: {result.total}")

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"


def main() -> None:
    root = tk.Tk()
    MediaSiftApp(root)
    root.mainloop()

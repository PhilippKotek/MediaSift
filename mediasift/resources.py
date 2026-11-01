"""Helpers for locating bundled application resources."""

from pathlib import Path
import sys


def resource_path(relative_path: str) -> str:
    """Return the absolute path to a packaged resource or source asset.

    PyInstaller extracts onefile resources under ``sys._MEIPASS``. During
    normal source execution, assets live alongside this module.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if getattr(sys, "frozen", False):
        base /= "mediasift"
    return str(base / relative_path)

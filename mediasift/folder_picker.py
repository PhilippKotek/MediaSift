"""Native Windows folder picker with Ctrl/Shift multi-selection."""

from __future__ import annotations

import ctypes
import os
import uuid
from ctypes import wintypes
from pathlib import Path


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, value: str) -> None:
        super().__init__()
        ctypes.memmove(ctypes.byref(self), uuid.UUID(value).bytes_le, ctypes.sizeof(self))


def _check(hr: int) -> None:
    if hr < 0:
        raise OSError(f"Windows-Ordnerauswahl fehlgeschlagen (0x{hr & 0xFFFFFFFF:08X})")


def _method(pointer: ctypes.c_void_p, index: int, result_type: object, *arg_types: object):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *arg_types)(table[index])


def _release(pointer: ctypes.c_void_p) -> None:
    if pointer.value:
        _method(pointer, 2, ctypes.c_ulong)(pointer)


def pick_folders(owner_hwnd: int, title: str = "Quellordner auswählen") -> list[Path]:
    """Return selected folders, or an empty list when the dialog is cancelled."""
    if os.name != "nt":
        raise OSError("Die Mehrfachauswahl benötigt Windows.")

    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_uint32,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None

    initialized = False
    dialog = ctypes.c_void_p()
    items = ctypes.c_void_p()
    try:
        hr = ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        _check(hr)
        initialized = True
        _check(ole32.CoCreateInstance(
            ctypes.byref(_GUID("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")),
            None, 0x1,  # CLSCTX_INPROC_SERVER
            ctypes.byref(_GUID("D57C7288-D4AD-4768-BE02-9D969532D960")),
            ctypes.byref(dialog),
        ))

        options = ctypes.c_uint32()
        _check(_method(dialog, 10, ctypes.c_long, ctypes.POINTER(ctypes.c_uint32))(
            dialog, ctypes.byref(options)))
        # FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_ALLOWMULTISELECT
        _check(_method(dialog, 9, ctypes.c_long, ctypes.c_uint32)(
            dialog, options.value | 0x20 | 0x40 | 0x200))
        _check(_method(dialog, 17, ctypes.c_long, ctypes.c_wchar_p)(dialog, title))

        hr = _method(dialog, 3, ctypes.c_long, wintypes.HWND)(dialog, owner_hwnd)
        if hr & 0xFFFFFFFF == 0x800704C7:  # HRESULT_FROM_WIN32(ERROR_CANCELLED)
            return []
        _check(hr)
        _check(_method(dialog, 27, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))(
            dialog, ctypes.byref(items)))
        count = ctypes.c_uint32()
        _check(_method(items, 7, ctypes.c_long, ctypes.POINTER(ctypes.c_uint32))(
            items, ctypes.byref(count)))

        selected: list[Path] = []
        for index in range(count.value):
            item = ctypes.c_void_p()
            name = ctypes.c_void_p()
            try:
                _check(_method(items, 8, ctypes.c_long, ctypes.c_uint32,
                               ctypes.POINTER(ctypes.c_void_p))(
                    items, index, ctypes.byref(item)))
                # SIGDN_FILESYSPATH
                _check(_method(item, 5, ctypes.c_long, ctypes.c_uint32,
                               ctypes.POINTER(ctypes.c_void_p))(
                    item, 0x80058000, ctypes.byref(name)))
                selected.append(Path(ctypes.wstring_at(name)))
            finally:
                if name.value:
                    ole32.CoTaskMemFree(name)
                _release(item)
        return selected
    finally:
        _release(items)
        _release(dialog)
        if initialized:
            ole32.CoUninitialize()

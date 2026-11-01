"""Named Windows mutex shared by the desktop app and EDMC plugin."""

from __future__ import annotations

import ctypes
import os
from contextlib import contextmanager
from ctypes import wintypes


_WAIT_OBJECT_0 = 0
_WAIT_ABANDONED = 0x80
_WAIT_TIMEOUT = 0x102
_MUTEX_NAME = "Local\\HotspotsFinder.RhinoSpotterSyncState.v1"


@contextmanager
def sync_state_mutex(timeout_ms: int = 30_000):
    if os.name != "nt":
        raise OSError("The shared RhinoSpotter sync-state mutex requires Windows.")
    kernel = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    owned = False
    try:
        result = kernel.WaitForSingleObject(handle, max(0, int(timeout_ms)))
        if result == _WAIT_TIMEOUT:
            raise TimeoutError("Timed out waiting for RhinoSpotter sync state lock.")
        if result not in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            raise ctypes.WinError(ctypes.get_last_error())
        owned = True
        yield
    finally:
        try:
            if owned and not kernel.ReleaseMutex(handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if not kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())

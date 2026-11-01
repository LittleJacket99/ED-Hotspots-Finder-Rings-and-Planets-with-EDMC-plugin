"""Windows Credential Manager storage shared by Finder and its EDMC plugin."""

from __future__ import annotations

import ctypes
import hashlib
import os
from ctypes import wintypes


_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _advapi32():
    if os.name != "nt":
        raise OSError("Windows Credential Manager is available only on Windows.")
    return ctypes.WinDLL("Advapi32.dll", use_last_error=True)


def _target(commander: str) -> str:
    """Return the shared read/write target for a commander profile."""
    # Match the Worker profile comparison (trim, then locale-independent lower
    # case for ASCII commander names) without Unicode casefold expansions.
    normalized = str(commander or "").strip().lower()
    if not normalized:
        raise ValueError("Commander is required to select an API credential.")
    identity = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"EDHF:CommunityDeposits:v1:{identity}"


def store_api_key(commander: str, secret: str) -> None:
    """Store a user-provided API key; the secret is never returned or logged."""
    target = _target(commander)
    secret = str(secret or "").strip()
    if not secret:
        raise ValueError("API key cannot be empty.")
    if len(secret) > 200:
        raise ValueError("API key exceeds the API's 200-character limit.")
    encoded = bytearray(secret, "utf-8")
    buffer = None
    try:
        buffer = ctypes.create_string_buffer(len(encoded))
        encoded_view = (ctypes.c_ubyte * len(encoded)).from_buffer(encoded)
        ctypes.memmove(buffer, encoded_view, len(encoded))
        credential = _CREDENTIALW()
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(encoded)
        credential.CredentialBlob = ctypes.cast(
            buffer, ctypes.POINTER(ctypes.c_ubyte)
        )
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = "ED Hotspots Finder"
        api = _advapi32()
        api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        if not api.CredWriteW(ctypes.byref(credential), 0):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if buffer is not None:
            ctypes.memset(buffer, 0, len(buffer))
        for index in range(len(encoded)):
            encoded[index] = 0


def get_api_key(commander: str) -> str | None:
    """Read the shared read/write key without exposing it in settings."""
    api = _advapi32()
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    api.CredReadW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    pointer = ctypes.POINTER(_CREDENTIALW)()
    if not api.CredReadW(_target(commander), _CRED_TYPE_GENERIC, 0,
                         ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == _ERROR_NOT_FOUND:
            return None
        raise ctypes.WinError(error)
    try:
        if not pointer:
            raise OSError("Windows returned an invalid API credential record.")
        item = pointer.contents
        if not item.CredentialBlobSize:
            return None
        if not item.CredentialBlob:
            raise OSError("Windows returned an invalid API credential blob.")
        data_view = (ctypes.c_ubyte * item.CredentialBlobSize).from_address(
            ctypes.addressof(item.CredentialBlob.contents)
        )
        data = bytearray(data_view)
        try:
            return data.decode("utf-8")
        finally:
            for index in range(len(data)):
                data[index] = 0
    finally:
        if pointer:
            try:
                item = pointer.contents
                if item.CredentialBlob and item.CredentialBlobSize:
                    ctypes.memset(item.CredentialBlob, 0, item.CredentialBlobSize)
            finally:
                api.CredFree(pointer)


def credential_configured(commander: str) -> bool:
    return get_api_key(commander) is not None

from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes


DPAPI_PREFIX = "dpapi:v1:"


class DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def is_protected_secret(value: str) -> bool:
    return str(value or "").startswith(DPAPI_PREFIX)


def protect_secret(secret: str) -> str:
    value = str(secret or "")
    if not value:
        return ""
    if is_protected_secret(value):
        return value
    encrypted = _crypt_protect(value.encode("utf-8"))
    return DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")


def unprotect_secret(value: str) -> str:
    stored = str(value or "")
    if not stored:
        return ""
    if not is_protected_secret(stored):
        return stored
    encrypted = base64.b64decode(stored[len(DPAPI_PREFIX):].encode("ascii"))
    return _crypt_unprotect(encrypted).decode("utf-8")


def _require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("Credential password encryption requires Windows DPAPI.")


def _blob_from_bytes(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    blob = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _crypt_protect(data: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    input_blob, input_buffer = _blob_from_bytes(data)
    output_blob = DataBlob()
    try:
        ok = crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "SAS credential password",
            None,
            None,
            None,
            0x01,  # CRYPTPROTECT_UI_FORBIDDEN
            ctypes.byref(output_blob),
        )
        if not ok:
            raise ctypes.WinError()
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        _ = input_buffer
        if output_blob.pbData:
            kernel32.LocalFree(output_blob.pbData)


def _crypt_unprotect(data: bytes) -> bytes:
    _require_windows()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob),
        ctypes.c_void_p,
        ctypes.POINTER(DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    input_blob, input_buffer = _blob_from_bytes(data)
    output_blob = DataBlob()
    try:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            0x01,  # CRYPTPROTECT_UI_FORBIDDEN
            ctypes.byref(output_blob),
        )
        if not ok:
            raise ctypes.WinError()
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        _ = input_buffer
        if output_blob.pbData:
            kernel32.LocalFree(output_blob.pbData)

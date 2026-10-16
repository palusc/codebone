"""Encrypt Windows provider credentials for the current user with Windows DPAPI."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]


def _crypt(value: bytes, decrypt=False) -> bytes:
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    result = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    # UI_FORBIDDEN: background launches must never open a credential dialog.
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), 'codebone', None, None, None, 1, ctypes.byref(result))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(result.data)


def write_secret(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not value:
        path.unlink(missing_ok=True)
        return
    encrypted = _crypt(value.encode('utf-8'))
    temp = path.with_suffix('.tmp')
    temp.write_bytes(encrypted)
    os.replace(temp, path)


def read_secret(path: Path) -> str:
    return _crypt(path.read_bytes(), decrypt=True).decode('utf-8') if path.exists() else ''

"""Windows DPAPI (CurrentUser) wrapper via ctypes. Off Windows it falls back to a clearly marked plain copy.

Honest limit: malware running as the same Windows user can call DPAPI too; this only stops
copying the files to another machine/user.
"""
from __future__ import annotations

import sys

_MAGIC_DPAPI = b"TDP1"
_MAGIC_PLAIN = b"TDX0"


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
                                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    _crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                                            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    def _call(protect_mode: bool, data: bytes) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))
        inb = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        out = _Blob()
        if protect_mode:
            ok = _crypt32.CryptProtectData(ctypes.byref(inb), "turbo-hub", None, None, None, 0, ctypes.byref(out))
        else:
            ok = _crypt32.CryptUnprotectData(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(out))
        if not ok:
            raise OSError(f"DPAPI call failed (error {ctypes.GetLastError()})")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            _kernel32.LocalFree(out.pbData)

    def protect(data: bytes) -> bytes:
        return _MAGIC_DPAPI + _call(True, data)

    def unprotect(blob: bytes) -> bytes:
        if blob.startswith(_MAGIC_DPAPI):
            return _call(False, blob[len(_MAGIC_DPAPI):])
        raise ValueError("not a DPAPI blob")
else:  # pragma: no cover - non-Windows dev fallback
    def protect(data: bytes) -> bytes:
        return _MAGIC_PLAIN + data

    def unprotect(blob: bytes) -> bytes:
        if blob.startswith(_MAGIC_PLAIN):
            return blob[len(_MAGIC_PLAIN):]
        raise ValueError("not a plain blob")

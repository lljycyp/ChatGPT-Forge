import ctypes
import os
from ctypes import wintypes


MAGIC = b"CODEX-FORGE-DPAPI\x00"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def protect_bytes(value):
    """使用当前 Windows 用户的 DPAPI 加密数据。"""
    _require_windows()
    source, source_buffer = _to_blob(value)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source),
        "Codex Forge backup",
        None,
        None,
        None,
        0x1,
        ctypes.byref(target),
    ):
        raise ctypes.WinError()
    try:
        return MAGIC + ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def unprotect_bytes(value):
    """解密由当前 Windows 用户创建的 DPAPI 数据。"""
    _require_windows()
    if not bytes(value).startswith(MAGIC):
        raise ValueError("不是有效的加密账号备份")
    source, source_buffer = _to_blob(bytes(value)[len(MAGIC):])
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(target)
    ):
        raise ValueError("无法解密备份；加密备份只能由创建它的 Windows 用户恢复")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _to_blob(value):
    buffer = ctypes.create_string_buffer(bytes(value))
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _require_windows():
    if os.name != "nt":
        raise RuntimeError("加密账号备份仅支持 Windows")

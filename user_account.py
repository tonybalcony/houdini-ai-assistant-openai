"""Per-Windows-user onboarding preferences and DPAPI-protected API credentials."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path


def user_dir():
    from access_policy import plugin_path
    return plugin_path('.state/account')


def preferences():
    try:
        value = json.loads((user_dir() / 'preferences.json').read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def remember_backend(backend):
    if backend not in ('subscription', 'api'):
        raise ValueError('Unknown sign-in choice.')
    directory = user_dir()
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / 'preferences.tmp'
    temporary.write_text(json.dumps({'backend': backend, 'onboarding_complete': True}), encoding='utf-8')
    temporary.replace(directory / 'preferences.json')


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _protect(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Remembering API keys requires Windows credential protection.')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    source_buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError('Windows could not protect/read the saved API key. Enter it again in Account setup.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def save_api_key(value):
    value = value.strip()
    if not value or len(value) > 4096 or any(c.isspace() for c in value):
        raise ValueError('Enter a valid API key without spaces.')
    encrypted = _protect(value.encode('utf-8'))
    directory = user_dir()
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / 'api-key.tmp'
    temporary.write_bytes(encrypted)
    temporary.replace(directory / 'api-key.dpapi')


def load_api_key():
    path = user_dir() / 'api-key.dpapi'
    return _protect(path.read_bytes(), decrypt=True).decode('utf-8') if path.is_file() else ''


def forget_api_key():
    (user_dir() / 'api-key.dpapi').unlink(missing_ok=True)

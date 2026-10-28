"""Optional Windows user-bound storage. Never persist an OTP passcode."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import threading
import time

from ckps.config import runtime_root

_lock = threading.RLock()


def _crypt(value, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Ghi nhớ kết nối cần Windows mã hóa cho người dùng hiện tại.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ValueError('Windows chưa mã hóa/đọc được kết nối đã lưu.')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32.LocalFree(result.data)


def _path():
    return runtime_root() / 'connection.dpapi'


def _read():
    try:
        value = json.loads(_crypt(_path().read_bytes(), decrypt=True))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write(value):
    encrypted = _crypt(json.dumps(value, allow_nan=False).encode('utf-8'))
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encrypted)
    os.replace(temporary, path)


def _identity(credentials):
    return hashlib.sha256(json.dumps([credentials.get('key', ''), credentials.get('secret', '')]).encode()).hexdigest()


def load_connection():
    with _lock:
        values = _read()
        if not all(isinstance(values.get(key), str) and values[key] for key in ('key', 'secret')):
            return {}
        return {key: values[key] for key in ('key', 'secret')}


def remember_connection(credentials):
    if not all(credentials.get(key) for key in ('key', 'secret')):
        raise ValueError('Nhập đủ API key và API secret trước khi ghi nhớ.')
    with _lock:
        old = _read()
        sessions = old.get('sessions', {}) if _identity(old) == _identity(credentials) else {}
        if not isinstance(sessions, dict):sessions = {}
        _write({**{key: credentials[key] for key in ('key', 'secret')}, 'sessions': sessions})


def forget_connection():
    with _lock:
        _path().unlink(missing_ok=True)


def save_trading_session(account, credentials, token, until):
    with _lock:
        value = _read()
        if not value or _identity(value) != _identity(credentials):
            return
        if not isinstance(value.get('sessions'), dict):value['sessions'] = {}
        value['sessions'][str(account)] = {'token': token, 'until': until}
        _write(value)


def trading_session(account, credentials, *, now=None):
    with _lock:
        value = _read()
        if _identity(value) != _identity(credentials):
            return '', 0.
        sessions = value.get('sessions', {})
        session = sessions.get(str(account), {}) if isinstance(sessions, dict) else {}
        if not isinstance(session, dict):return '', 0.
        try:
            until = float(session.get('until', 0))
            token = session.get('token', '')
            if isinstance(token, str) and token and 0 < until-(time.time() if now is None else now) <= 8*3600:
                return token, until
        except (ValueError, TypeError):
            pass
        return '', 0.

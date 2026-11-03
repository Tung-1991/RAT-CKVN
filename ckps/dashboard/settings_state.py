"""One settings source for the PAPER/REAL app and read-only signal service."""
import time
from ckps.services.signal_config import read_signal_settings, write_signal_settings


def telegram_token(app):
    """An explicitly cleared in-memory token must not restore an older secret."""
    credentials=getattr(app,'signal_credentials',{})
    if 'telegram_token' in credentials:return credentials['telegram_token']
    from ckps.connections.secure_session import load_telegram_token
    import os
    return load_telegram_token() or os.environ.get('CKPS_TELEGRAM_TOKEN','')


def signal_settings(app):
    if not hasattr(app, '_signal_settings'):
        app._signal_settings = read_signal_settings()
    return app._signal_settings


def save_signal_settings(app, settings):
    settings.validate()
    write_signal_settings(settings)
    app._signal_settings = settings
    session = getattr(app, 'signal_session', None)
    if session and session.running:
        session.configure(settings, getattr(app, 'signal_credentials', {}).get('telegram_token', ''))
    preview = getattr(app, 'preview_session', None)
    if preview and preview.running:
        from ckps.services.signal_config import preview_settings
        preview.configure(preview_settings(settings), '')


def ensure_preview_backend(app):
    """Start read-only analysis automatically; replace an API only after exit."""
    if (not getattr(app, 'preview_analysis_enabled', False) or app.closing
            or app.runtime is None):return
    credentials = app._mode_credentials()
    session = getattr(app, 'preview_session', None)
    identity = tuple(credentials.get(key, '') for key in ('key', 'secret'))
    if session and session.running:
        if identity != getattr(app, '_preview_identity', None) and not getattr(app, '_preview_stopping', False):
            session.close()
            app._preview_stopping = True
        return
    if not all(identity) or time.monotonic() < getattr(app, '_preview_retry_at', 0):return
    from ckps.services.signal_process import SignalProcess
    from ckps.services.signal_config import preview_settings
    app._preview_retry_at = time.monotonic() + 30
    app._preview_identity, app._preview_stopping = identity, False
    try:
        app.preview_session = SignalProcess(preview_settings(signal_settings(app)), credentials, preview_only=True)
    except (OSError, ValueError):
        app.preview_session = None


def start_signal_backend(app, settings, credentials):
    if not credentials.get('key') or not credentials.get('secret'):
        raise ValueError('Nhập API key/secret ở DNSE trước khi chạy tín hiệu.')
    if settings.telegram_enabled and not (credentials.get('telegram_token') and settings.telegram_chat):
        raise ValueError('Nhập Bot token và Chat ID trước khi bật thông báo.')
    session = getattr(app, 'signal_session', None)
    if session and session.running:
        raise ValueError('Backend đang chạy; dùng LƯU để cập nhật cấu hình.')
    from ckps.connections.secure_session import remember_telegram_token
    remember_telegram_token(credentials.get('telegram_token',''))
    from ckps.services.signal_process import SignalProcess
    app.signal_session = SignalProcess(settings, credentials)
    app.signal_credentials = {key: credentials.get(key, '') for key in ('key', 'secret', 'telegram_token')}
    save_signal_settings(app, settings)

"""One settings source for RULE/connection; the demo keeps all edits in RAM."""
from ckps.models import Settings
from ckps.services.signal_config import read_signal_settings, write_signal_settings


def signal_settings(app):
    if not hasattr(app, '_signal_settings'):
        app._signal_settings = Settings() if getattr(app, 'preview_only', False) else read_signal_settings()
    return app._signal_settings


def save_signal_settings(app, settings):
    settings.validate()
    if not getattr(app, 'preview_only', False):
        write_signal_settings(settings)
    app._signal_settings = settings
    session = getattr(app, 'signal_session', None)
    if session and session.running:
        session.configure(settings, getattr(app, 'signal_credentials', {}).get('telegram_token', ''))


def start_signal_backend(app, settings, credentials):
    if getattr(app, 'preview_only', False):
        raise ValueError('Mẫu offline chỉ lưu cấu hình trong phiên; không kết nối hoặc gửi Telegram.')
    if not credentials.get('key') or not credentials.get('secret'):
        raise ValueError('Nhập API key/secret ở DNSE trước khi chạy tín hiệu.')
    if settings.telegram_enabled and not (credentials.get('telegram_token') and settings.telegram_chat):
        raise ValueError('Nhập Bot token và Chat ID trước khi bật thông báo.')
    session = getattr(app, 'signal_session', None)
    if session and session.running:
        raise ValueError('Backend đang chạy; dùng LƯU để cập nhật cấu hình.')
    from ckps.services.signal_process import SignalProcess
    app.signal_session = SignalProcess(settings, credentials)
    app.signal_credentials = {key: credentials.get(key, '') for key in ('key', 'secret', 'telegram_token')}
    save_signal_settings(app, settings)

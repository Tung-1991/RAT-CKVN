"""Offline persistence and expiry must never create live trading permission."""
from dataclasses import asdict
import json
from types import SimpleNamespace
import time

import pytest

from ckps.config import runtime_root
from ckps.models import Quote
from ckps.connections import secure_session as vault
from ckps.services.quote_cache import QuoteCache
from ckps.dashboard.mayin.connection_status import otp_status
from ckps.dashboard.mayin.signal_preview import signal_preview


def test_windows_store_is_encrypted_bound_to_api_account_and_expiry():
    credentials = {'key': 'offline-api-key', 'secret': 'offline-api-secret', 'otp': 'never-persist-otp'}
    now = time.time()
    vault.save_trading_session('123', credentials, 'not-opted-in', now+300)
    assert not vault.load_connection() and not (runtime_root()/'connection.dpapi').exists()
    vault.remember_connection(credentials)
    vault.save_trading_session('123', credentials, 'offline-trading-token', now+300)
    raw = (runtime_root()/'connection.dpapi').read_bytes()
    assert all(value.encode() not in raw for value in (*credentials.values(), 'offline-trading-token'))
    assert vault.load_connection() == {'key': credentials['key'], 'secret': credentials['secret']}
    assert vault.trading_session('123', credentials, now=now) == ('offline-trading-token', now+300)
    assert vault.trading_session('124', credentials, now=now) == ('', 0.)
    assert vault.trading_session('123', credentials, now=now+301) == ('', 0.)
    assert vault.trading_session('123', {**credentials, 'secret': 'different'}, now=now) == ('', 0.)
    assert 'otp' not in json.loads(vault._crypt(raw, decrypt=True))
    vault.remember_connection({'key': 'new-key', 'secret': 'new-secret'})
    assert not vault._read()['sessions']
    vault.forget_connection()
    assert not (runtime_root()/'connection.dpapi').exists()


def test_unreadable_saved_connection_is_not_reused():
    runtime_root().mkdir(parents=True)
    (runtime_root()/'connection.dpapi').write_bytes(b'damaged')
    assert vault.load_connection() == {}
    assert vault.trading_session('123', {'key': 'k', 'secret': 's'}) == ('', 0.)


def test_quote_cache_preserves_source_time_and_stays_outside_live_quote_map():
    now = time.time()
    quote = Quote('41I1GB000', 2007, at=now-3600, source='DNSE WS')
    cache = QuoteCache()
    cache.observe(SimpleNamespace(contract=quote.symbol, quotes={quote.symbol: quote}))
    restored = QuoteCache().value
    assert restored['quote'] == asdict(quote) and restored['contract'] == quote.symbol
    view = {'contract': quote.symbol, 'quotes': {}, 'market_cache': restored,
        'market_context': {'state': 'ABOVE', 'ma': 1985, 'observed_at': now,
            'entry': {'state': 'READY', 'price': 2007, 'observed_at': now}}}
    assert all(result[0] == 'CHỜ' for result in signal_preview(view, now=now))
    assert not view['quotes']
    cache.observe(SimpleNamespace(contract='VN30F1M', quotes={'VN30F1M': Quote('VN30F1M', 9999, source='MẪU')}))
    assert QuoteCache().value == restored
    (runtime_root()/'last-market.json').write_text('{broken', encoding='utf-8')
    assert QuoteCache().value == {}


def test_quote_cache_throttles_writes_without_losing_the_last_update(monkeypatch):
    now = time.time()
    clock = [100.]
    monkeypatch.setattr('ckps.services.quote_cache.time.monotonic', lambda: clock[0])
    quote = Quote('41I1GB000', 2007, at=now-10, source='DNSE')
    snapshot = SimpleNamespace(contract=quote.symbol, quotes={quote.symbol: quote})
    cache = QuoteCache()
    cache.observe(snapshot)
    quote.last, quote.at = 2008, now
    clock[0] = 102.
    cache.observe(snapshot)
    assert cache.value['quote']['last'] == 2008 and QuoteCache().value['quote']['last'] == 2007
    clock[0] = 106.
    cache.observe(snapshot)
    assert QuoteCache().value['quote']['last'] == 2008
    quote.last, quote.at = 1999, now-30
    cache.observe(snapshot)
    assert cache.value['quote']['last'] == 2008
    snapshot.contract = 'VN30F1M'
    snapshot.quotes = {'VN30F1M': quote}
    cache.observe(snapshot)
    assert cache.value['contract'] == '41I1GB000'


def test_preview_missing_stale_and_wrong_contract_data_have_no_signal():
    view = {'contract': '41I1GB000', 'quotes': {}}
    assert 'Chưa kết nối' in signal_preview(view, now=1000)[0][1]
    view['quotes'] = {'41I1GB000': asdict(Quote('41I1GB000', 2007, at=900))}
    assert 'Giá cũ' in signal_preview(view, now=1000)[0][1]
    view['quotes']['41I1GB000']['at'] = None
    assert 'thời gian hợp lệ' in signal_preview(view, now=1000)[0][1]
    view['quotes']['41I1GB000'] = asdict(Quote('VN30F1M', 2007, at=1000))
    view['market_context'] = {'state': 'ABOVE', 'ma': 1985, 'observed_at': 1000}
    assert all(result[0] == 'CHỜ' for result in signal_preview(view, now=1000))


def test_otp_metadata_is_required_only_for_real_and_counts_down_without_token():
    view = {'trading_auth': {'valid': True, 'until': 1000+3660}}
    assert '1h01' in otp_status(view, 'REAL', now=1000)[0]
    assert otp_status(view, 'REAL', now=4661)[1] == 'amber'
    assert 'HẾT HẠN' in otp_status(view, 'REAL', now=4661)[0]
    assert 'không cần' in otp_status(view, 'PAPER', now=1000)[0]
    assert 'CHƯA XÁC THỰC' in otp_status({}, 'REAL', now=1000)[0]


def test_rejected_trading_auth_clears_memory_and_remembered_session(monkeypatch):
    from ckps.connections.dnse.client import DNSEBroker
    from ckps.connections.dnse.protocol import BrokerError
    credentials = {'key': 'offline-key', 'secret': 'offline-secret'}
    vault.remember_connection(credentials)
    vault.save_trading_session('123', credentials, 'offline-token', time.time()+300)
    response = SimpleNamespace(ok=False, status_code=401, headers={})
    broker = DNSEBroker(**credentials, account_no='123', session=SimpleNamespace(request=lambda *a, **k: response))
    broker.token, broker.token_until = vault.trading_session('123', credentials)
    with pytest.raises(BrokerError):
        broker.request('GET', '/offline-auth-check', trading=True)
    assert not broker.token and not broker.token_until
    assert vault.trading_session('123', credentials) == ('', 0.)


def test_runtime_restores_only_bound_session_and_publishes_no_secrets(monkeypatch):
    from ckps.models import Settings, Snapshot
    from ckps.services.runtime import Runtime
    credentials = {'key': 'offline-key', 'secret': 'offline-secret'}
    vault.remember_connection(credentials)
    class Broker:
        mode = 'REAL'
        feed = None
        def __init__(self, key, secret, account_no, loan_package_id):
            self.key, self.secret, self.account_no = key, secret, account_no
            self.token, self.token_until = '', 0.
        def snapshot(self):
            quote = Quote('41I1GB000', 2007, source='DNSE')
            return Snapshot(quote.symbol, [], [], {quote.symbol: quote}, 100_000_000, 0,
                40_000_000, 2, 2, 100_000_000, pending_margin=0)
        def verify_otp(self, code):
            if code == 'invalid-code':raise ValueError('OTP không hợp lệ.')
            assert code == 'one-time-code'
            self.token, self.token_until = 'private-trading-token', time.time()+300
        def close(self):pass
    monkeypatch.setattr('ckps.services.runtime.DNSEBroker', Broker)
    settings = Settings(mode='REAL', account_no='123')
    runtime = Runtime(settings, credentials, offline=True)
    try:
        runtime.command('verify_otp', 'invalid-code')
        while True:
            kind, value = runtime.events.get(timeout=3)
            if kind == 'auth_error':
                assert value == 'OTP không hợp lệ.'
                assert not vault.trading_session('123', credentials)[0]
                break
        runtime.command('verify_otp', 'one-time-code')
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            kind, value = runtime.events.get(timeout=3)
            if kind == 'snapshot' and value['trading_auth']['valid']:
                assert not runtime.engine.enabled.is_set()
                assert not any(secret in json.dumps(value) for secret in (*credentials.values(), 'private-trading-token', 'one-time-code'))
                break
        else:pytest.fail('OTP status was not published.')
    finally:
        runtime.close();runtime.thread.join(3)
    assert not runtime.thread.is_alive()
    restored = Runtime(settings, credentials, offline=True)
    try:
        assert restored.engine.broker.token == 'private-trading-token'
        assert not restored.engine.enabled.is_set()
    finally:
        restored.close();restored.thread.join(3)
    assert not restored.thread.is_alive()


def test_otp_form_guards_and_clears_passcode_before_worker_result():
    from ckps.dashboard.mayin.connection_window import ConnectionWindow
    class Variable:
        def __init__(self, value):self.value = value
        def get(self):return self.value
        def set(self, value):self.value = value
    sent, note = [], {}
    app = SimpleNamespace(settings=SimpleNamespace(mode='PAPER', account_no='123', loan_package_id='456'),
        credentials={'key': 'offline-key', 'secret': 'offline-secret'}, runtime=object(), preview_only=False,
        mode_requested=None, switch_pending=None, send=lambda *args: sent.append(args))
    form = SimpleNamespace(app=app, note=SimpleNamespace(configure=lambda **values: note.update(values)),
        variables={'connection.mode': Variable('PAPER'), 'connection.otp': Variable('offline-code'),
            'connection.otp_type': Variable('EMAIL'), 'connection.account': Variable('123'),
            'connection.loan': Variable('456'), 'connection.key': Variable('offline-key'),
            'connection.secret': Variable('offline-secret')})
    form.otp_ready = lambda: ConnectionWindow.otp_ready(form)
    form.otp_matches_active = lambda: ConnectionWindow.otp_matches_active(form)
    ConnectionWindow.verify_otp(form)
    assert not sent and 'REAL' in note['text']
    app.settings.mode = 'REAL'
    ConnectionWindow.verify_otp(form)
    assert not sent  # Requested PAPER cannot authenticate the active REAL book.
    form.variables['connection.mode'].set('REAL')
    app.switch_pending = ('new-book', {})
    ConnectionWindow.verify_otp(form)
    assert not sent
    app.switch_pending = None
    for key in ('account', 'loan', 'key', 'secret'):
        variable = form.variables['connection.'+key]
        previous = variable.get()
        variable.set('changed')
        ConnectionWindow.verify_otp(form)
        assert not sent and 'đã đổi' in note['text']
        variable.set(previous)
    ConnectionWindow.verify_otp(form)
    assert sent == [('verify_otp', 'offline-code', 'email_otp')]
    assert not form.variables['connection.otp'].get()
    form.variables['connection.otp_type'].set('SMART')
    ConnectionWindow.send_otp(form)
    assert len(sent) == 1 and 'ứng dụng DNSE' in note['text']

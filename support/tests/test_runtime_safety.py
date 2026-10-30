"""Deterministic slow-account I/O test; no DNSE/Telegram connection."""
from dataclasses import asdict
import queue
import threading
import time

from ckps.models import ExitSettings, Settings
from ckps.services.runtime import Runtime


def snapshot_matching(runtime, predicate):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        try:
            kind, payload = runtime.events.get(timeout=.2)
        except queue.Empty:
            continue
        assert kind != 'error', payload
        if kind == 'snapshot' and predicate(payload):
            return payload
    raise AssertionError('Runtime did not publish the expected state.')


def test_bot_off_is_immediate_during_slow_account_poll_and_prevents_late_stop(monkeypatch):
    runtime = Runtime(Settings(exit=asdict(ExitSettings(sl_enabled=True, sl_distance=.5))), offline=True)
    entered, release = threading.Event(), threading.Event()
    try:
        runtime.command('open_manual', 'LONG', 1, 'MOK')
        snapshot_matching(runtime, lambda view: bool(view['positions']))
        runtime.command('arm', True)
        snapshot_matching(runtime, lambda view: view['armed'])
        original = runtime.engine.broker.snapshot
        def slow_snapshot():
            entered.set()
            assert release.wait(3)
            return original()
        monkeypatch.setattr(runtime.engine.broker, 'snapshot', slow_snapshot)
        runtime.command('refresh')
        assert entered.wait(2)
        runtime.engine.broker.set_price(1989)
        # The serialized worker cannot handle this stop while account I/O is
        # pending. Disarming must still take effect without waiting for I/O.
        assert len(runtime.store.orders()) == 1
        runtime.command('arm', False)
        assert not runtime.engine.enabled.is_set()
        release.set()
        view = snapshot_matching(runtime, lambda value: value['quotes']['VN30F1M']['last'] == 1989)
        assert not view['armed'] and len(runtime.store.orders()) == 1
    finally:
        release.set()
        runtime.close()
        runtime.thread.join(5)
    assert not runtime.thread.is_alive()

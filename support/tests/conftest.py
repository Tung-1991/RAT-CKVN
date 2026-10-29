from dataclasses import asdict, replace
import os
import socket
from datetime import datetime

import pytest
import requests

from ckps.connections.dnse.paper import PaperBroker
from ckps.models import ExitSettings, Settings
from ckps.trading.execution import Engine
from ckps.storage import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("CKPS_RUNTIME_DIR", str(tmp_path / "runtime"))
    # Financial fixtures use a known continuous weekday session. Calendar tests
    # supply their own date explicitly or override this clock for exclusion days.
    from ckps.rules.p2.market import VN_TZ
    monkeypatch.setattr('ckps.services.calendar.local_now',lambda:datetime(2026,10,27,10,0,tzinfo=VN_TZ))
    for key in list(os.environ):
        if key.startswith("CKPS_") and key != "CKPS_RUNTIME_DIR":
            monkeypatch.delenv(key, raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline tests must never contact DNSE/Telegram.")
    monkeypatch.setattr(requests.Session, "request", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def system(tmp_path):
    store = Store(tmp_path / "ledger.sqlite3")
    # Unit scenarios opt into individual branches themselves. The shipped
    # ready-to-use preset has dedicated startup/execution tests.
    settings = Settings(exit=asdict(ExitSettings()))
    broker = PaperBroker(store, settings, offline=True)
    engine = Engine(store, broker, settings)
    engine.poll()
    yield engine, broker, store
    store.close()

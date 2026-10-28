"""One-way entry receipts. The backend never reads account books or accepts commands."""
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time

from ckps.config import runtime_root
from ckps.models import is_vn30


def notice_path():
    return runtime_root() / "signals" / "entry-receipts.sqlite3"


class EntryRelay:
    """Export committed entry receipts on a separate local worker, without credentials."""
    def __init__(self, store):
        self.store = store
        self.stop = threading.Event()
        self.book = hashlib.sha256(str(store.path).encode()).hexdigest()[:20]
        self.thread = threading.Thread(target=self._run, name="ckps-entry-receipts", daemon=True)
        self.thread.start()

    def flush(self):
        with self.store.lock:
            records = self.store.db.execute("SELECT id,data FROM records WHERE kind='entry_notice'").fetchall()
        pending = [(key, raw) for key, raw in records if not self.store.get("entry_notice_exported", key)]
        if not pending:
            return
        path = notice_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=.5) as db:
            db.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, at REAL, data TEXT NOT NULL)")
            for key, raw in pending:
                value = json.loads(raw)
                db.execute("INSERT OR IGNORE INTO receipts VALUES (?,?,?)", (self.book + ":" + key, value['at'], raw))
        for key, _ in pending:
            self.store.put("entry_notice_exported", key, True)

    def _run(self):
        while not self.stop.wait(.3):
            try:
                self.flush()
            except (OSError, sqlite3.Error):
                pass  # Receipts remain durable in the account transaction for the next attempt.

    def close(self):
        self.stop.set()
        self.thread.join()
        try:
            self.flush()
        except (OSError, sqlite3.Error):
            pass


class EntryNotices:
    def __init__(self, store):
        self.store = store
        self.started_at = time.time()

    def observe(self, *, enabled, chat, now=None):
        now = time.time() if now is None else now
        path = notice_path()
        if not path.exists():
            return
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=.2) as db:
            cursor = self.store.get("entry_receipts", "cursor", 0)
            rows = db.execute("SELECT rowid,id,at,data FROM receipts WHERE rowid>? ORDER BY rowid LIMIT 100", (cursor,)).fetchall()
        labels = {"WORKING": "ĐÃ GỬI", "PARTIAL": "KHỚP MỘT PHẦN", "FILLED": "ĐÃ KHỚP",
                  "UNKNOWN": "CHỜ ĐỐI SOÁT", "CANCELLED": "ĐÃ HỦY", "REJECTED": "TỪ CHỐI", "FAILED": "LỖI"}
        with self.store.transaction():
            for rowid, key, at, raw in rows:
                self.store.put("entry_receipts", "cursor", rowid)
                if at < self.started_at or not 0 <= now - at <= 120:
                    continue
                value = json.loads(raw)
                if not is_vn30(value.get("symbol")) or value.get("side") not in {"LONG", "SHORT"}:
                    continue
                status = labels.get(value.get("status"), "CHỜ XÁC NHẬN")
                text = (f"{value['symbol']} · ENTRY · {value['mode']}\n"
                        f"{value['side']} · {status} · {value['filled']}/{value['quantity']} HĐ"
                        + (f" @ {value['price']:g}" if value.get('price') else ""))
                self.store.put("signal_history", key, dict(id=key, symbol=value['symbol'], kind="VÀO LỆNH", reason=text, at=at))
                if enabled and chat:
                    self.store.notify("owner:" + chat, text, key=key)

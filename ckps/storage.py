from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from ckps.models import Order, Position, load_record


class Store:
    """One SQLite ledger per account/book; fill, quantity and queue commit together."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, data TEXT NOT NULL,
                PRIMARY KEY(kind, id));
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at REAL, kind TEXT, text TEXT);
            CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, target TEXT, text TEXT, sent INTEGER DEFAULT 0);
        """)
        self.depth = 0

    @contextmanager
    def transaction(self):
        with self.lock:
            outer = self.depth == 0
            if outer:
                self.db.execute("BEGIN IMMEDIATE")
            self.depth += 1
            try:
                yield self
                if outer:
                    self.db.execute("COMMIT")
            except BaseException:
                if outer:
                    self.db.execute("ROLLBACK")
                raise
            finally:
                self.depth -= 1

    def put(self, kind, key, data):
        with self.lock:
            self.db.execute("INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data",
                            (kind, key, json.dumps(data, ensure_ascii=False, allow_nan=False)))

    def get(self, kind, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row else default

    def all(self, kind):
        with self.lock:
            rows = self.db.execute("SELECT data FROM records WHERE kind=? ORDER BY rowid", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_position(self, position):
        self.put("position", position.id, asdict(position))

    def positions(self, closed=False):
        return [load_record(Position, row) for row in self.all("position")
                if bool(row.get("closed_at")) == closed]

    def position(self, key):
        raw = self.get("position", key)
        if not raw:
            raise ValueError("Không tìm thấy vị thế.")
        return load_record(Position, raw)

    def save_order(self, order):
        order.updated_at = time.time()
        self.put("order", order.id, asdict(order))

    def orders(self, pending=False):
        rows = [load_record(Order, row) for row in self.all("order")]
        return [row for row in rows if row.pending] if pending else rows

    def order(self, key):
        raw = self.get("order", key)
        if not raw:
            raise ValueError("Không tìm thấy lệnh.")
        return load_record(Order, raw)

    def event(self, kind, text):
        with self.lock:
            self.db.execute("INSERT INTO events(at,kind,text) VALUES (?,?,?)", (time.time(), kind, str(text)))

    def events(self, limit=300):
        with self.lock:
            return self.db.execute("SELECT at,kind,text FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def notify(self, target, text, key=None):
        if not target:
            return
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO outbox(id,target,text) VALUES (?,?,?)",
                            (key or uuid.uuid4().hex, target, text))

    def close(self):
        with self.lock:
            self.db.close()


class AccountLease:
    """An OS lock prevents two processes trading the same local ledger."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        self.file.seek(0)
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)
        try:
            import msvcrt
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError("Tài khoản này đang được một phiên app khác sử dụng.") from exc

    def close(self):
        if not self.file.closed:
            self.file.close()

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

from ckps.models import Settings, load_record

APP_NAME = "RAT · VN30"
ROOT = Path(__file__).resolve().parent.parent


def runtime_root():
    return Path(os.environ.get("CKPS_RUNTIME_DIR", str(ROOT / "runtime" / "ckps"))).resolve()


def read_settings():
    path = runtime_root() / "settings.json"
    if not path.exists():
        return Settings()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        # An empty section contains no saved strategy. A fully saved OFF rule
        # is an explicit user choice and must survive every restart.
        if values.get('exit') == {}:
            values.pop('exit')
        return load_record(Settings, values).validate()
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError("Cấu hình CKPS không hợp lệ; giữ nguyên file để kiểm tra.") from exc


def write_settings(settings):
    settings.validate()
    folder = runtime_root()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "settings.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def book_path(settings):
    account = settings.account_no or "LOCAL"
    if not account.isdigit() and account != "LOCAL":
        raise ValueError("Tài khoản không hợp lệ.")
    return runtime_root() / "accounts" / account / settings.mode.lower()

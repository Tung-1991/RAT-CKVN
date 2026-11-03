"""Independent backend parameters; credentials belong to the Windows vault."""
from dataclasses import asdict, replace
import json
import os

from ckps.config import runtime_root, read_settings
from ckps.models import Settings, load_record

FIELDS = ('signals','market_alerts','telegram_enabled','telegram_chat','poll_seconds','max_quote_age','entry_notifications')


def signal_folder():
    return runtime_root() / 'signals'


def preview_settings(settings):
    """Automatic analysis has no authority to enable notifications."""
    return replace(settings, telegram_enabled=False, telegram_chat='', entry_notifications=False).validate()


def read_signal_settings():
    path=signal_folder()/'settings.json'
    if path.exists():
        raw=json.loads(path.read_text(encoding='utf-8'))
    else:
        raw=asdict(read_settings())  # One-time migration of existing indicator parameters.
    return load_record(Settings,{key:raw[key] for key in FIELDS if key in raw}).validate()


def write_signal_settings(settings):
    settings.validate()
    folder=signal_folder()
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'settings.json'
    temporary=path.with_suffix('.tmp')
    values=asdict(settings)
    temporary.write_text(json.dumps({key:values[key] for key in FIELDS},ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(temporary,path)

"""Portable strategy presets; account, connection and notification state stay local."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict, fields
import json
import os
from pathlib import Path
import tempfile
import uuid

from ckps.config import runtime_root, read_settings, book_path
from ckps.models import ExitSettings, Settings, load_record
from ckps.rules.defaults import shared_exit_settings
from ckps.rules.distances import price_rule_values
from ckps.rules.signal_settings import SignalSettings
from ckps.rules.market_alerts import MarketAlertSettings
from ckps.services.signal_config import read_signal_settings
from ckps.storage import AccountLease

SCHEMA='rat-vn30-preset/v1'
MARKET_FIELDS=set(MarketAlertSettings.__dataclass_fields__)-{'trend_enabled','movement_enabled'}


def validate_preset(raw):
    if not isinstance(raw,dict) or raw.get('schema')!=SCHEMA:
        raise ValueError('File không đúng định dạng preset RAT VN30 v1.')
    if set(raw)-{'schema','name','exit','signals','market_alerts'}:
        raise ValueError('Preset chỉ chứa RULE; không nhận tài khoản hoặc kết nối.')
    result={'schema':SCHEMA,'name':str(raw.get('name') or 'Preset')}
    for key,cls in (('exit',ExitSettings),('signals',SignalSettings),('market_alerts',MarketAlertSettings)):
        if key not in raw:continue
        values=raw[key]
        allowed=MARKET_FIELDS if key=='market_alerts' else {f.name for f in fields(cls)}
        if not isinstance(values,dict) or not values or set(values)-allowed:
            raise ValueError(f'{key}: chỉ chấp nhận tham số RULE hợp lệ.')
        defaults=asdict(cls())
        for name,value in values.items():
            if isinstance(defaults[name],bool) and not isinstance(value,bool):
                raise ValueError(f'{name}: cần công tắc bật/tắt.')
        if key=='exit':
            normalized=price_rule_values(shared_exit_settings(values))
        else:
            normalized=cls.from_dict(values).to_dict()
            if key=='market_alerts':normalized={name:normalized[name] for name in sorted(MARKET_FIELDS)}
        result[key]=normalized
    if not {'exit','signals','market_alerts'} & result.keys():
        raise ValueError('Preset chưa có RULE để nạp.')
    return result


def current_preset(name='Kaiser'):
    main,signals=read_settings(),read_signal_settings()
    return validate_preset({'schema':SCHEMA,'name':name,'exit':main.exit,
        'signals':signals.signals,
        'market_alerts':{key:signals.market_alerts[key] for key in sorted(MARKET_FIELDS)}})


def _read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _atomic_write(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as stream:
        temporary=Path(stream.name)
        stream.write(content)
    try:os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()


def load_preset(path):
    """Validate first, then replace strategy sections with rollback and a backup."""
    path=Path(path)
    preset=validate_preset(_read_json(path))
    folder=runtime_root()
    main_path=folder/'settings.json'
    signal_path=folder/'signals'/'settings.json'
    with ExitStack() as stack:
        # Hold the relevant book locks throughout the write. Loading a preset
        # must not race an open trading app, Blackbox or signal process.
        settings=read_settings()
        locks=set(folder.rglob('session.lock'))
        locks.add(book_path(settings)/'session.lock')
        locks.add(folder/'presets'/'session.lock')
        try:
            for lock in sorted(locks):
                lease=AccountLease(lock)
                stack.callback(lease.close)
        except (OSError,RuntimeError) as exc:
            raise ValueError('Đóng app và Blackbox trước khi nạp preset.') from exc
        originals={target:target.read_bytes() if target.exists() else None for target in (main_path,signal_path)}
        main=_read_json(main_path) if originals[main_path] is not None else asdict(settings)
        signals=_read_json(signal_path) if originals[signal_path] is not None else {
            key:deepcopy(main[key]) for key in ('signals','market_alerts','telegram_enabled','telegram_chat','entry_notifications','poll_seconds','max_quote_age')}
        if 'exit' in preset:main['exit']=deepcopy(preset['exit'])
        for key in ('signals','market_alerts'):
            if key not in preset:continue
            for target in (main,signals):
                if key=='signals':target[key]=deepcopy(preset[key])
                else:target[key]={**target.get(key,{}),**preset[key]}
        load_record(Settings,deepcopy(main)).validate()
        load_record(Settings,deepcopy(signals)).validate()
        updates={main_path:main}
        if {'signals','market_alerts'} & preset.keys():updates[signal_path]=signals
        encoded={target:json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8') for target,value in updates.items()}
        backup=folder/'presets'/'backups'/uuid.uuid4().hex
        backup.mkdir(parents=True)
        for index,(target,content) in enumerate(originals.items()):
            if content is not None:(backup/('settings.json' if index==0 else 'signals.json')).write_bytes(content)
        applied=[]
        try:
            for target,content in encoded.items():
                applied.append(target)
                _atomic_write(target,content)
        except Exception:
            for target in applied:
                content=originals[target]
                if content is None:
                    if target.exists():target.unlink()
                else:_atomic_write(target,content)
            raise
    return preset['name'],backup

"""DNSE derivative package fees. These are not an all-in tax/fee quote."""
from .account import amount


def package_fees(package):
    raw = (package or {}).get('tradingFee')
    raw = raw if isinstance(raw, dict) else {}
    schema = raw.get('schemaType', '')
    normal = amount(raw.get('fixedTradingFee')) if schema == 'FIXED' else None
    daily = amount(raw.get('fixedDailyCloseTradingFee')) if schema == 'FIXED' else None
    close = max(normal, daily) if normal is not None and daily is not None else None
    if normal is not None:
        text = f'Phí gói {normal:,.0f} đ/HĐ'
        if daily is not None:text += f' · đóng trong ngày {daily:,.0f} đ/HĐ'
    elif schema == 'PROGRESSIVE':
        text = 'Phí gói theo bậc thang · chờ mức áp dụng'
    else:
        text = 'Phí gói · CHỜ DNSE'
    return {'open': normal, 'close': close, 'daily_close': daily, 'schema': schema,
        'text': text, 'source': 'DNSE · GÓI KÝ QUỸ'}


def fee_pair(settings, snapshot):
    """Risk uses the package's conservative close fee, never a stock fee rate."""
    values = snapshot.package_fees
    if values.get('open') is not None and values.get('close') is not None:
        return values['open'], values['close']
    if settings.mode == 'PAPER' and not values:
        return settings.estimated_fee_per_contract, settings.estimated_fee_per_contract
    return None, None

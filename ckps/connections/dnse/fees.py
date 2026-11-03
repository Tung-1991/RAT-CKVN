"""DNSE derivative package fees. These are not an all-in tax/fee quote."""
from .account import amount


def _tier_bounds(rows):
    """Validate the complete returned schedule before estimating its upper rate."""
    if not isinstance(rows,list) or not rows:return None
    tiers=[]
    for row in rows:
        if not isinstance(row,dict):return None
        low,high,fee=(amount(row.get(key)) for key in ('fromQuantity','toQuantity','fee'))
        if low is None or high is None or fee is None or not low.is_integer() or not high.is_integer() or low<1 or high<low:
            return None
        tiers.append((int(low),int(high),fee))
    tiers.sort()
    next_quantity=1
    for low,high,_ in tiers:
        if low!=next_quantity:return None
        next_quantity=high+1
    rates=[fee for _,_,fee in tiers]
    return min(rates),max(rates)


def package_fees(package):
    raw = (package or {}).get('tradingFee')
    raw = raw if isinstance(raw, dict) else {}
    schema = raw.get('schemaType', '')
    normal = amount(raw.get('fixedTradingFee')) if schema == 'FIXED' else None
    daily = amount(raw.get('fixedDailyCloseTradingFee')) if schema == 'FIXED' else None
    close = max(normal, daily) if normal is not None and daily is not None else None
    estimated_open=estimated_close=None
    if normal is not None:
        text = f'Phí gói {normal:,.0f} đ/HĐ'
        if daily is not None:text += f' · đóng trong ngày {daily:,.0f} đ/HĐ'
    elif schema == 'PROGRESSIVE':
        opening=_tier_bounds(raw.get('progressTradingFee'))
        closing=_tier_bounds(raw.get('progressDailyCloseTradingFee'))
        if opening:
            estimated_open=opening[1]
            if closing:estimated_close=max(opening[1],closing[1])
            text=f'Phí gói bậc thang {opening[0]:,.0f}–{opening[1]:,.0f} đ/HĐ · ước mở ≤ {estimated_open:,.0f} đ/HĐ'
            if estimated_close is not None:text+=f' · ước đóng ≤ {estimated_close:,.0f} đ/HĐ'
            text+=' · chưa xác định bậc thực tế'
        else:text = 'Phí gói theo bậc thang · chờ biểu phí hợp lệ'
    else:
        text = 'Phí gói · CHỜ DNSE'
    return {'open': normal, 'close': close, 'daily_close': daily, 'schema': schema,
        'estimated_open':estimated_open,'estimated_close':estimated_close,
        'text': text, 'source': 'DNSE · GÓI KÝ QUỸ'}


def fee_pair(settings, snapshot):
    """Risk uses the package's conservative close fee, never a stock fee rate."""
    values = snapshot.package_fees
    if values.get('open') is not None and values.get('close') is not None:
        return values['open'], values['close']
    if values.get('estimated_open') is not None and values.get('estimated_close') is not None:
        return values['estimated_open'],values['estimated_close']
    if settings.mode == 'PAPER' and not values:
        return settings.estimated_fee_per_contract, settings.estimated_fee_per_contract
    return None, None

"""Read-only ARM thresholds using the execution margin basis."""
from dataclasses import dataclass
from math import isfinite

from ckps.models import ExitSettings, Quote, load_record
from ckps.rules.distances import pnl_trailing_rules, reference_margin
from ..formatting import money, price
from ckps.services.session_preview import closing_quote
import time


@dataclass(frozen=True)
class ProtectionReference:
    entry: float | None = None
    margin: float | None = None
    quantity: int | None = None
    source: str = ''


def protection_reference(view, max_age=10, *, entry=None, quantity=None):
    symbol=view.get('contract')
    positions=[p for p in view.get('positions',[]) if p.get('symbol')==symbol and p.get('quantity',0)>0]
    if len(positions)==1:
        p=positions[0]
        return ProtectionReference(p.get('entry'),p.get('margin_per_contract'),p['quantity'],'VỊ THẾ')
    if positions:return ProtectionReference()
    quote=view.get('quotes',{}).get(symbol,{})
    closed=bool(quote and closing_quote(symbol,quote,now=time.time()))
    if not quote or quote.get('symbol')!=symbol or not (load_record(Quote,quote).fresh(max_age) or closed):
        return ProtectionReference()
    account=view.get('account',{})
    entry=entry if entry is not None else quote.get('last')
    margin=reference_margin(account.get('margin_per_contract'),account.get('margin_reference_price') or quote.get('last'),entry)
    if quantity is None:
        long,short=view.get('LONG',{}).get('maximum'),view.get('SHORT',{}).get('maximum')
        if long is not None and long==short:quantity=long
    return ProtectionReference(entry,margin,quantity,'ĐÓNG PHIÊN' if closed else 'VÉ MỚI')


def pnl_preview(values, reference, *, compact=False):
    """Amounts describe the remaining holding, not accumulated realized profit."""
    if reference.entry is None or not isfinite(reference.entry) or reference.entry<=0:
        return ('CHỜ GIÁ VỐN / GIÁ VÉ', 'Chưa có dữ liệu giá hợp lệ để xem trước ARM')
    margin=reference.margin
    if margin is None or not isfinite(margin) or margin<=0:
        return ('CHỜ KÝ QUỸ CƠ SỞ/HĐ', 'ARM: CHỜ · SL/TP vẫn theo % giá vốn')
    try:rules=pnl_trailing_rules(values,reference.entry,margin)
    except ValueError:
        return ('CHỜ QUY ĐỔI RULE', 'Giữ nguyên RULE đã lưu và mốc bảo vệ đang chạy')
    qty=reference.quantity
    known_qty=isinstance(qty,int) and not isinstance(qty,bool) and qty>0
    base=f'{reference.source} · Cơ sở {money(margin)}/HĐ'
    base+=f' · {qty} HĐ = {money(margin*qty)}' if known_qty else ' · CHỜ HĐ'
    lines=[]
    for key,label in (('arm_gain','ARM'),('trail_gap','Lùi'),('repeat_gap','LẶP')):
        if key=='repeat_gap' and rules['arm_close_pct']==rules['dynamic_close_pct']==100:continue
        value=rules[key]
        cash=margin*value/100
        unit='% PNL' if key=='arm_gain' else 'điểm % PNL'
        enabled=rules['arm_enabled'] if key!='repeat_gap' else (
            rules['arm_enabled'] and rules['arm_repeat'] or rules['dynamic_enabled'] and rules['dynamic_repeat'])
        if not enabled:label+=' OFF ·'
        line=f'{label} {value:g} {unit} = {price(cash/100_000)}đ · {money(cash)}/HĐ'
        if known_qty:line+=f' · {money(cash*qty)}/{qty} HĐ'
        lines.append(line)
    if compact:
        if not known_qty:base=base.removesuffix(' · CHỜ HĐ')
        short=[]
        for key,label in (('arm_gain','ARM'),('trail_gap','Lùi'),('repeat_gap','LẶP')):
            if key=='repeat_gap' and rules['arm_close_pct']==rules['dynamic_close_pct']==100:continue
            value=rules[key];cash=margin*value/100
            amount=money(cash*qty)+f'/{qty} HĐ' if known_qty else money(cash)+'/HĐ'
            unit='%' if key=='arm_gain' else ' điểm %'
            enabled=rules['arm_enabled'] if key!='repeat_gap' else (
                rules['arm_enabled'] and rules['arm_repeat'] or rules['dynamic_enabled'] and rules['dynamic_repeat'])
            if not enabled:label+=' OFF'
            short.append(f'{label} {value:g}{unit} PNL · {price(cash/100_000)}đ · {amount}')
        return base,'\n'.join(short)
    return base, '\n'.join(lines)+'\nTrước phí · mốc kích hoạt, không bảo đảm giá khớp'


def dynamic_pnl_preview(view, values, reference, atr_pct):
    """Show the ATR components in ROI units without changing their price formulas."""
    entry,margin=reference.entry,reference.margin
    if any(v is None or not isfinite(v) or v<=0 for v in (entry,margin,atr_pct)):return None
    rules=load_record(ExitSettings,values).validate()
    if not rules.dynamic_enabled:return 'DYNAMIC OFF','Nhánh DYNAMIC đang tắt.'
    positions=[p for p in view.get('positions',[]) if p.get('symbol')==view.get('contract') and p.get('quantity',0)>0]
    peak=entry
    if len(positions)==1 and reference.source=='VỊ THẾ':
        p=positions[0]
        best=p.get('best') or entry
        if isfinite(best) and best>0:peak=max(entry,best) if p['side']=='LONG' else min(entry,best)
    number=lambda value:f'{value:.2f}'.replace('.',',')
    qty=reference.quantity
    known_qty=isinstance(qty,int) and not isinstance(qty,bool) and qty>0
    summaries,details=[],[]
    for enabled,label,points,unit in (
        (rules.atr_start_enabled,'START',entry*atr_pct/100*rules.atr_start_multiplier,'% PNL'),
        (rules.atr_trail_enabled,'Lùi ATR',peak*atr_pct/100*rules.atr_trail_multiplier,'điểm % PNL')):
        if not enabled:
            if label=='START':summaries.append('START khi có lãi')
            continue
        cash=points*100_000
        value=cash/margin*100
        summaries.append(f'{label} {number(value)} {unit}')
        line=f'{label} {number(value)} {unit} · {price(points)} điểm · {money(cash)}/HĐ'
        if known_qty:line+=f' · {money(cash*qty)}/{qty} HĐ'
        details.append(line)
    if rules.retention_enabled:
        summaries.append(f'giữ {rules.retention_pct:g}% lãi')
        details.append(f'Giữ {rules.retention_pct:g}% lãi đỉnh; kết hợp mốc ATR chặt hơn.')
    return ' · '.join(summaries),'\n'.join(details)+'\nCác số tiền trước phí; mốc thực thi vẫn theo giá hợp đồng.'

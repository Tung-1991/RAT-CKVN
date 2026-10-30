"""Read-only status badges; permission and fresh data are separate signals."""
from ckps.models import FINAL, Quote, load_record


TONES = {
    'green': ('#123E2B', '#22C55E', '#86EFAC'),
    'amber': ('#4A3214', '#F59E0B', '#FDE68A'),
    'red': ('#481F28', '#EF4444', '#FCA5A5'),
    'blue': ('#183858', '#60A5FA', '#BFDBFE'),
}


def preview_state(view, max_age, position=None, rules=None, *, changing_book=False, demo=False):
    bot = ('BOT ON', 'green') if view.get('armed') else ('BOT OFF', 'amber')
    symbol = position.symbol if position else view.get('contract', 'VN30F1M')
    quote = view.get('quotes', {}).get(symbol, {})
    try:
        fresh = bool(quote and quote.get('symbol') == symbol and load_record(Quote, quote).fresh(max_age))
    except (ValueError, TypeError):
        fresh = False
    synced = bool(view.get('healthy') and view.get('consistent'))
    if changing_book:
        data = ('SỔ · ĐANG ĐỔI', 'amber')
    elif not synced and (quote or view.get('error')):
        data = ('SỔ · ĐỐI SOÁT', 'red')
    elif not fresh:
        data = ('GIÁ · CŨ' if quote else 'GIÁ · CHỜ', 'amber')
    else:
        data = ('GIÁ MẪU', 'blue') if demo else ('GIÁ · MỚI', 'green')
    if position is None:
        management = ('VÉ · CHỈ XEM', 'blue')
    elif not position.managed:
        management = ('QL · CHƯA NHẬN', 'amber')
    elif not view.get('armed'):
        management = ('QL · TẠM DỪNG', 'amber')
    elif rules and rules.distance_unit=='PNL_PERCENT' and not position.margin_per_contract:
        management = ('QL · CHỜ KÝ QUỸ', 'amber')
    elif changing_book or not fresh or not synced:
        management = ('QL · CHỜ DỮ LIỆU', 'red')
    elif any(o.get('position_id') == position.id and o.get('action') == 'CLOSE'
             and o.get('status') not in FINAL for o in view.get('orders', [])):
        management = ('QL · CHỜ KHỚP', 'amber')
    elif rules and rules.ema_exit_enabled and not any((rules.sl_enabled, rules.tp_enabled, rules.arm_enabled, rules.dynamic_enabled)) and not view.get('ema_exit',{}).get('ready'):
        management = ('QL · CHỜ EMA 1D', 'amber')
    elif rules and not any((rules.sl_enabled, rules.tp_enabled, rules.arm_enabled, rules.dynamic_enabled, rules.ema_exit_enabled)):
        management = ('QL · RULE OFF', 'amber')
    elif rules and not (rules.sl_enabled or rules.tp_enabled or rules.ema_exit_enabled or
                       rules.arm_enabled and rules.arm_policy == 'AUTO' or
                       rules.dynamic_enabled and rules.dynamic_policy == 'AUTO'):
        management = ('QL · CHỈ BÁO', 'blue')
    else:
        management = ('QUẢN LÝ ON', 'green')
    return bot, management, data

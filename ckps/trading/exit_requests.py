"""Durable full-exit intent; pending cancellations never release contracts."""
from ckps.models import Decision, number

FULL_EXITS = frozenset({'SL', 'TP', 'E'})


def requested_exit(position, rules):
    request = position.metrics.get('full_exit', {})
    reason = request.get('reason')
    enabled = {'SL': rules.sl_enabled, 'TP': rules.tp_enabled, 'E': rules.ema_exit_enabled}
    if reason not in enabled or not enabled[reason]:
        position.metrics.pop('full_exit', None)
        return None
    price = number(request.get('price'))
    return Decision(reason, price, position.quantity) if price > 0 else None


def request_exit(position, decision):
    request = position.metrics.get('full_exit', {})
    # A stop-loss takes precedence over an existing EMA exit.
    if not request or (decision.reason == 'SL' and request.get('reason') != 'SL'):
        position.metrics['full_exit'] = dict(reason=decision.reason, price=decision.price,
                                             cancel_requested=[])
    position.metrics['closing_all'] = True
    position.metrics['auto_full_exit'] = True

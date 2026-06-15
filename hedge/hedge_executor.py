# -*- coding: utf-8 -*-
"""HEDGE Dual order executor."""

import MetaTrader5 as mt5

from .hedge_config import HEDGE_BUY_COMMENT, HEDGE_SELL_COMMENT


class HedgeExecutor:
    def __init__(self, connector=None, log_callback=None):
        self.connector = connector
        self.log_callback = log_callback

    def log(self, message: str, error: bool = False):
        if self.log_callback:
            self.log_callback(f"[HEDGE] {message}", error=error, target="hedge")

    def place_hedge_leg(self, symbol, direction, lot_size, hedge_magic, session_id=None, sl_price=0.0, tp_price=0.0):
        if not self.connector or not getattr(self.connector, "_is_connected", False):
            return "HEDGE_FAIL|NO_CONNECTION"

        direction = str(direction or "").upper()
        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        comment = HEDGE_BUY_COMMENT if direction == "BUY" else HEDGE_SELL_COMMENT

        if hasattr(self.connector, "validate_order_before_placement"):
            is_valid, reason = self.connector.validate_order_before_placement(
                symbol=symbol,
                order_type=order_type,
                lot_size=lot_size,
                sl_price=sl_price,
                tp_price=tp_price,
            )
            if not is_valid:
                safe_reason = str(reason).replace("|", "/")[:120]
                self.log(f"ORDER BLOCKED {direction} {symbol} lot={lot_size:.2f} reason={safe_reason}", error=True)
                return f"HEDGE_FAIL|VALIDATION|{safe_reason}"

        result = self.connector.place_order(
            symbol=symbol,
            order_type=order_type,
            lot_size=lot_size,
            sl_price=sl_price,
            tp_price=tp_price,
            magic_number=hedge_magic,
            comment=comment[:20],
        )
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log(f"OPEN {direction} {symbol} #{result.order} lot={lot_size:.2f} session={session_id or '-'}")
            return f"SUCCESS|{result.order}"

        retcode = getattr(result, "retcode", "NONE") if result else "NONE"
        server_comment = getattr(result, "comment", "") if result else ""
        last_error = mt5.last_error()
        detail = f"retcode={retcode}; comment={server_comment}; last_error={last_error}"
        safe_detail = detail.replace("|", "/")[:160]
        self.log(f"ORDER REJECTED {direction} {symbol} lot={lot_size:.2f} {safe_detail}", error=True)
        return f"HEDGE_FAIL|MT5_ORDER_REJECTED|{safe_detail}"

    def close_position(self, position, reason="HEDGE_CLOSE"):
        if not self.connector or not position:
            return "HEDGE_FAIL|NO_CONNECTION"
        comment = f"HEDGE_{str(reason or 'CLOSE')}"[:20]
        try:
            result = self.connector.close_position(position, comment=comment)
        except TypeError:
            result = self.connector.close_position(position)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log(f"CLOSE #{getattr(position, 'ticket', '?')} {getattr(position, 'symbol', '')} reason={reason}")
            return f"SUCCESS|{getattr(position, 'ticket', '')}"
        retcode = getattr(result, "retcode", "NONE") if result else "NONE"
        self.log(f"CLOSE FAILED #{getattr(position, 'ticket', '?')} reason={reason} retcode={retcode}", error=True)
        return f"HEDGE_FAIL|CLOSE_REJECTED|{retcode}"

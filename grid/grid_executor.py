# -*- coding: utf-8 -*-
"""GRID market-order executor."""

import MetaTrader5 as mt5


class GridExecutor:
    def __init__(self, connector=None, log_callback=None):
        self.connector = connector
        self.log_callback = log_callback

    def log(self, message: str, error: bool = False):
        if self.log_callback:
            self.log_callback(f"[GRID] {message}", error=error, target="grid")

    def place_grid_order(self, symbol, direction, lot_size, tp_price, grid_magic, level_id, session_id):
        if not self.connector or not getattr(self.connector, "_is_connected", False):
            return "GRID_FAIL|NO_CONNECTION"

        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        # MT5 may reject special chars in comments on some servers.
        safe_level = "".join(ch for ch in str(level_id) if ch.isalnum() or ch == "_")[:12]
        comment = f"GRID_{safe_level}"[:20]
        if hasattr(self.connector, "validate_order_before_placement"):
            is_valid, reason = self.connector.validate_order_before_placement(
                symbol=symbol,
                order_type=order_type,
                lot_size=lot_size,
                sl_price=0.0,
                tp_price=tp_price,
            )
            if not is_valid:
                safe_reason = str(reason).replace("|", "/")[:120]
                self.log(f"ORDER BLOCKED {direction} {symbol} lot={lot_size:.2f} tp={tp_price:.5f} reason={safe_reason}", error=True)
                return f"GRID_FAIL|VALIDATION|{safe_reason}"

        result = self.connector.place_order(
            symbol=symbol,
            order_type=order_type,
            lot_size=lot_size,
            sl_price=0.0,
            tp_price=tp_price,
            magic_number=grid_magic,
            comment=comment,
        )
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log(f"ORDER {direction} {symbol} #{result.order} lot={lot_size:.2f} tp={tp_price:.5f} level={level_id}")
            return f"SUCCESS|{result.order}"
        retcode = getattr(result, "retcode", "NONE") if result else "NONE"
        server_comment = getattr(result, "comment", "") if result else ""
        last_error = mt5.last_error()
        detail = f"retcode={retcode}; comment={server_comment}; last_error={last_error}"
        safe_detail = detail.replace("|", "/")[:160]
        self.log(f"ORDER REJECTED {direction} {symbol} lot={lot_size:.2f} tp={tp_price:.5f} {safe_detail}", error=True)
        return f"GRID_FAIL|MT5_ORDER_REJECTED|{safe_detail}"

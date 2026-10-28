"""Dedicated signed GET connection for analysis, never a trading session."""
from .client import DNSEBroker
from .protocol import BrokerError, unwrap


class ReadOnlyHistory(DNSEBroker):
    requires_account = False

    def request(self, method, path, **kwargs):
        if method != "GET" or kwargs.get("trading") or path.startswith(("/accounts", "/positions", "/registration")):
            raise BrokerError("Kết nối phân tích chỉ cho phép GET.")
        if getattr(self, "stopping", None) and self.stopping.is_set():
            raise BrokerError("Đã dừng tải lịch sử.")
        return super().request(method, path, **kwargs)

    def get_ohlc(self, symbol, resolution, start, end):
        # Continuous front-month history is the chart seed; memory is keyed by
        # actual contract so rolling cannot consume the previous contract's cross.
        body = unwrap(self.request("GET", "/price/ohlc", params={
            "symbol": "VN30F1M", "type": "DERIVATIVE", "resolution": resolution,
            "from": str(int(start)), "to": str(int(end))}))
        if not isinstance(body, dict):
            raise BrokerError("Chưa có lịch sử VN30F1M hợp lệ.")
        return body

    def working_dates(self):
        raw = unwrap(self.request("GET", "/market/working-dates"))
        values = raw if isinstance(raw, list) else raw.get("workingDates", raw.get("dates", [])) if isinstance(raw, dict) else []
        dates = [str(v.get("date", v.get("workingDate", "")) if isinstance(v, dict) else v)[:10] for v in values]
        return sorted(v for v in dates if len(v) == 10 and v[4] == "-") or None


class NoHistory:
    def get_ohlc(self, *args):
        raise BrokerError("Chưa kết nối lịch sử DNSE.")

    def close(self):
        pass

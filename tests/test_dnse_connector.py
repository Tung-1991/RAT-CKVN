# -*- coding: utf-8 -*-
import time
from types import SimpleNamespace
import pytest

import config
from core.dnse_connector import DNSEConnector, BrokerOrderResult, BrokerTick
from core import settlement_ledger


def test_trading_token_seconds_left():
    conn = DNSEConnector(api_key="k", api_secret="s", account_no="ACC1", base_url="https://x.test", session=None)
    assert conn.trading_token_seconds_left() == 0.0  # chưa có token
    conn.trading_token = "tok"
    conn.trading_token_expires_at = time.time() + 3600
    assert 3500 < conn.trading_token_seconds_left() <= 3600
    conn.trading_token_expires_at = time.time() - 10  # đã hết hạn
    assert conn.trading_token_seconds_left() == 0.0


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "headers": headers or {},
                "timeout": timeout,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        pass


def _connector(session):
    conn = DNSEConnector(
        api_key="key",
        api_secret="secret",
        account_no="ACC1",
        base_url="https://example.test",
        session=session,
    )
    assert conn.connect()
    return conn


def test_verify_otp_sets_token_and_expiry():
    session = FakeSession([FakeResponse(200, {"trading-token": "tok"})])
    conn = _connector(session)

    assert conn.verify_otp("email_otp", "123456") is True

    assert conn.trading_token == "tok"
    assert conn.has_trading_token() is True
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/registration/trading-token")
    assert call["json"] == {"otpType": "email_otp", "passcode": "123456"}
    assert "X-Signature" in call["headers"]


def test_trading_token_ttl_by_otp_type(monkeypatch):
    monkeypatch.setattr(config, "DNSE_TOKEN_TTL_HOURS", {"email_otp": 8.0, "smart_otp": 8.0})
    # email OTP -> ~8h theo tài liệu DNSE
    conn = _connector(FakeSession([FakeResponse(200, {"trading-token": "tok"})]))
    conn.otp_type = "email_otp"
    assert conn.verify_otp("email_otp", "123456") is True
    assert conn.trading_token_persistent is False
    assert 7.5 * 3600 < conn.trading_token_seconds_left() <= 8 * 3600
    # smart OTP -> ~8h
    conn2 = _connector(FakeSession([FakeResponse(200, {"trading-token": "tok2"})]))
    conn2.otp_type = "smart_otp"
    assert conn2.verify_otp("smart_otp", "123456") is True
    assert conn2.trading_token_persistent is False
    assert 7.5 * 3600 < conn2.trading_token_seconds_left() <= 8 * 3600


def test_401_invalid_token_clears_cached_token(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    session = FakeSession([FakeResponse(401, {"message": "Token is invalid"})])
    conn = _connector(session)
    conn.trading_token = "stale"
    conn.trading_token_expires_at = time.time() + 3600

    assert conn.get_orders(symbol="VN30F1M") == []
    assert conn.trading_token is None
    assert conn.trading_token_seconds_left() == 0.0


def test_send_order_builds_derivative_payload_and_uses_trading_token(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    session = FakeSession([FakeResponse(200, {"orderId": "O1", "status": "NEW"})])
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999
    # Pre-seed map alias->mã thật để khỏi gọi /instruments trong test.
    conn._symbol_map = {"VN30F1M": "41I1G6000"}
    conn._symbol_map_ts = 9999999999

    result = conn.send_order("VN30F1M", "BUY", 1.2, sl=1200, tp=1220, comment="[BOT]", magic=77)

    assert isinstance(result, BrokerOrderResult)
    assert result.ok is True
    assert result.order_id == "O1"
    call = session.calls[0]
    assert call["params"] == {"marketType": "DERIVATIVE", "orderCategory": "NORMAL"}
    assert call["json"]["symbol"] == "41I1G6000"
    assert call["json"]["side"] == "NB"
    assert call["json"]["quantity"] == 1
    assert call["json"]["stopLoss"] == 1200
    assert call["json"]["takeProfit"] == 1220
    assert call["headers"]["trading-token"] == "tok"


def test_positions_are_mapped_to_broker_position(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "positions": [
                        {
                            "positionId": "P1",
                            "orderId": "O1",
                            "symbol": "VN30F1M",
                            "side": "LONG",
                            "quantity": 2,
                            "avgPrice": 1200.5,
                            "currentPrice": 1202.0,
                            "unrealizedPnl": 300000,
                        }
                    ]
                },
            )
            ,
            FakeResponse(200, {"positions": []}),
        ]
    )
    conn = _connector(session)

    positions = conn.get_positions()

    assert len(positions) == 1
    pos = positions[0]
    assert pos.ticket == "P1"
    assert pos.symbol == "VN30F1M"
    assert pos.type == 0
    assert pos.volume == 2
    assert pos.price_open == 1200.5
    assert pos.profit == 300000


def test_stock_symbol_uses_stock_profile_account_and_fee_rate(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "DNSE_STOCK_PRICE_VALUE", 1000.0)
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "marketType": "STOCK",
                    "loanPackages": [
                        {
                            "id": 1036,
                            "type": "N",
                            "brokerFirmBuyingFeeRate": 0.00045,
                            "brokerFirmSellingFeeRate": 0.00045,
                        }
                    ],
                },
            )
        ]
    )
    conn = _connector(session)

    profile = conn.get_fee_profile("FPT")

    assert conn.market_type_for_symbol("FPT") == "STOCK"
    assert conn.account_no_for_symbol("FPT") == "ACC1"
    assert profile.market_type == "STOCK"
    assert profile.quantity_unit == "CP"
    assert profile.exchange_fee_per_contract == 0
    assert profile.clearing_fee_per_contract == 0
    assert profile.broker_fee_rate == 0.00045
    assert profile.estimate_fee(73.3, 10) == 73.3 * 10 * 1000 * 0.00045


def test_stock_symbol_info_and_profit_do_not_use_derivative_multiplier(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "DNSE_STOCK_PRICE_VALUE", 1000.0)
    session = FakeSession([])
    conn = _connector(session)
    conn.get_tick = lambda symbol: SimpleNamespace(symbol=symbol, bid=73.2, ask=73.3, last=73.25, spread=0.1, raw={})

    info = conn.get_symbol_info("FPT")

    assert info.market_type == "STOCK"
    assert info.quantity_unit == "CP"
    assert info.trade_contract_size == 1000.0
    assert conn.calculate_profit("FPT", "BUY", 10, 73.3, 73.4) == pytest.approx(1000.0)


def test_close_position_posts_to_position_close_endpoint(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    session = FakeSession([FakeResponse(200, {"orderId": "CLOSE1"})])
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999

    result = conn.close_position(SimpleNamespace(position_id="P1", ticket="P1"), comment="manual")

    assert result.ok is True
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["url"].endswith("/accounts/positions/P1/close")
    assert session.calls[0]["json"] == {"comment": "manual"}


def test_failed_request_returns_failed_order_result(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    session = FakeSession([FakeResponse(400, {"message": "bad order"})])
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999
    conn._symbol_map = {"VN30F1M": "41I1G6000"}
    conn._symbol_map_ts = 9999999999

    result = conn.send_order("VN30F1M", "SELL", 1)

    assert result.ok is False
    assert result.status_code == 400
    assert "bad order" in result.error


def test_send_order_refuses_when_auto_trade_disabled(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", False)
    session = FakeSession([])
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999

    result = conn.send_order("VN30F1M", "BUY", 1)

    assert result.ok is False
    assert result.error == "AUTO_TRADE_DISABLED"
    assert session.calls == []


def test_real_stock_buy_records_settlement_ledger(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    session = FakeSession(
        [
            FakeResponse(200, {"orderId": "O-FPT-1", "status": "NEW"}),
            FakeResponse(200, {"workingDates": ["2026-06-18", "2026-06-19", "2026-06-22"]}),
        ]
    )
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999

    result = conn.send_order("FPT", "BUY", 100)

    assert result.ok is True
    ledger_rows = settlement_ledger.enrich_positions(
        "ACC1",
        [SimpleNamespace(ticket="P1", position_id="P1", order_id="O-FPT-1", symbol="FPT", type=0, volume=100, raw={"orderId": "O-FPT-1"})],
    )
    assert ledger_rows[0]["settle_date"]
    assert session.calls[0]["json"]["symbol"] == "FPT"


def test_real_stock_sell_blocks_when_not_settled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    settlement_ledger.record_buy("ACC1", "O-FPT-1", "FPT", 100, "2999-01-01", "2999-01-03")
    session = FakeSession(
        [
            FakeResponse(200, {"positions": []}),
            FakeResponse(
                200,
                {
                    "positions": [
                        {
                            "positionId": "P1",
                            "orderId": "O-FPT-1",
                            "symbol": "FPT",
                            "side": "LONG",
                            "quantity": 100,
                            "avgPrice": 73.0,
                            "currentPrice": 73.5,
                        }
                    ]
                },
            ),
        ]
    )
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999

    result = conn.send_order("FPT", "SELL", 100)

    assert result.ok is False
    assert result.error == "STOCK_NOT_SETTLED_T2"
    assert all(not call["url"].endswith("/accounts/orders") for call in session.calls)


def test_real_derivative_sell_is_not_blocked_by_t2(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    session = FakeSession([FakeResponse(200, {"orderId": "O1", "status": "NEW"})])
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999
    conn._symbol_map = {"VN30F1M": "41I1G6000"}
    conn._symbol_map_ts = 9999999999

    result = conn.send_order("VN30F1M", "SELL", 1)

    assert result.ok is True
    assert session.calls[0]["json"]["symbol"] == "41I1G6000"


def test_paper_mode_uses_real_fee_profile_without_account_or_order_endpoints(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PAPER_TRADING", True)
    monkeypatch.setattr(config, "PAPER_INITIAL_BALANCE", 100000000.0)
    monkeypatch.chdir(tmp_path)
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "loanPackages": [
                        {
                            "tradingFee": {
                                "fixedTradingFee": 2000,
                            }
                        }
                    ]
                },
            )
        ]
    )
    conn = _connector(session)
    conn.get_tick = lambda symbol: SimpleNamespace(symbol=symbol, bid=1000.0, ask=1000.5, last=1000.2, spread=0.5)

    account = conn.get_account_info()
    result = conn.send_order("VN30F1M", "BUY", 2, sl=995, tp=1010)
    positions = conn.get_positions()

    assert account["server"] == "DNSE_API_PAPER"
    assert result.ok is True
    assert result.order_id.startswith("PAPER-")
    assert len(positions) == 1
    assert len(session.calls) == 1
    assert session.calls[0]["url"].endswith("/accounts/ACC1/loan-packages")
    assert "/balances" not in session.calls[0]["url"]
    assert "/orders" not in session.calls[0]["url"]
    assert "/positions" not in session.calls[0]["url"]


def test_paper_mode_stock_rounds_odd_lot_like_real(monkeypatch, tmp_path):
    # Paper phải áp luật giống thật: mua 150 CP -> khớp 100 (bội số lô).
    monkeypatch.setattr(config, "PAPER_TRADING", True)
    monkeypatch.setattr(config, "PAPER_INITIAL_BALANCE", 100000000.0)
    monkeypatch.chdir(tmp_path)
    session = FakeSession([FakeResponse(200, {"loanPackages": [{"tradingFee": {"fixedTradingFee": 2000}}]})])
    conn = _connector(session)
    conn.get_tick = lambda symbol: BrokerTick(symbol=symbol, bid=73.0, ask=73.1, last=73.0, reference=73.0, ceiling=78.0, floor=68.0)

    result = conn.send_order("FPT", "BUY", 150)
    positions = conn.get_positions()

    assert result.ok is True
    assert len(positions) == 1
    assert positions[0].volume == 100  # 150 -> bội 100 ngay ở paper


def test_paper_mode_stock_blocks_price_out_of_band_like_real(monkeypatch, tmp_path):
    # Paper phải chặn giá ngoài biên giống thật.
    monkeypatch.setattr(config, "PAPER_TRADING", True)
    monkeypatch.setattr(config, "PAPER_INITIAL_BALANCE", 100000000.0)
    monkeypatch.chdir(tmp_path)
    session = FakeSession([])
    conn = _connector(session)
    conn.get_tick = lambda symbol: BrokerTick(symbol=symbol, bid=73.0, ask=73.1, last=73.0, reference=73.0, ceiling=78.0, floor=68.0)

    result = conn.send_order("FPT", "BUY", 100, price=120.0)

    assert result.ok is False
    assert result.error == "PRICE_OUT_OF_BAND"
    assert conn.get_positions() == []  # không mở vị thế paper nào


def test_fee_profile_maps_dnse_loan_package(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "loanPackages": [
                        {
                            "id": 2279,
                            "tradingFee": {
                                "fixedTradingFee": 2000,
                            },
                        }
                    ]
                },
            )
        ]
    )
    conn = _connector(session)

    profile = conn.get_fee_profile("VN30F1M")

    assert profile.broker_fee_per_contract == 2000
    assert profile.exchange_fee_per_contract == config.DNSE_EXCHANGE_FEE_PER_CONTRACT
    assert profile.source == "dnse_loan_package"


def test_real_403_returns_account_pending_and_mutes(monkeypatch, caplog):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    DNSEConnector._balances_403_muted = False
    session = FakeSession(
        [
            FakeResponse(403, {"message": "You do not have access to this account."}),
            FakeResponse(403, {"message": "You do not have access to this account."}),
        ]
    )
    conn = _connector(session)

    first = conn.get_account_info()
    second = conn.get_account_info()

    assert first["status"] == "ACCOUNT_PENDING"
    assert second["status"] == "ACCOUNT_PENDING"
    assert caplog.text.count("DNSE balances failed [403]") <= 1


def test_account_info_exposes_margin_fields(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "data": {
                        "nav": 100_000_000,
                        "cashAvailable": 90_000_000,
                        "margin": {"buyingPower": 150_000_000, "rtt": 112.5, "debtValue": 10_000_000},
                    }
                },
            )
        ]
    )
    conn = _connector(session)

    info = conn.get_account_info()

    assert info["equity"] == 100_000_000
    assert info["cash_available"] == 90_000_000
    assert info["buying_power"] == 150_000_000
    assert info["margin_debt"] == 10_000_000
    assert info["rtt"] == 112.5


# --- T+2 nâng cao: lô 100 CP + biên độ trần/sàn (CKCS) ---

def test_stock_buy_rounds_odd_lot_down(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    session = FakeSession(
        [
            FakeResponse(200, {"orderId": "O-FPT-150", "status": "NEW"}),
            FakeResponse(200, {"workingDates": ["2026-06-18", "2026-06-19", "2026-06-22"]}),
        ]
    )
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999

    result = conn.send_order("FPT", "BUY", 150)

    assert result.ok is True
    assert session.calls[0]["json"]["quantity"] == 100  # 150 -> bội 100


def test_stock_buy_blocks_below_one_lot(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    session = FakeSession([])
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999

    result = conn.send_order("FPT", "BUY", 90)

    assert result.ok is False
    assert result.error == "STOCK_ODD_LOT"
    assert session.calls == []  # không gửi lệnh lên DNSE


def test_stock_lo_rejects_price_out_of_band(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    session = FakeSession([])
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999
    conn.get_tick = lambda symbol: BrokerTick(symbol=symbol, last=100.0, reference=100.0, ceiling=107.0, floor=93.0)

    result = conn.send_order("FPT", "BUY", 100, price=120.0)

    assert result.ok is False
    assert result.error == "PRICE_OUT_OF_BAND"
    assert session.calls == []


def test_stock_lo_accepts_price_in_band(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    session = FakeSession(
        [
            FakeResponse(200, {"orderId": "O-FPT-LO", "status": "NEW"}),
            FakeResponse(200, {"workingDates": ["2026-06-18", "2026-06-19", "2026-06-22"]}),
        ]
    )
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999
    conn.get_tick = lambda symbol: BrokerTick(symbol=symbol, last=100.0, reference=100.0, ceiling=107.0, floor=93.0)

    result = conn.send_order("FPT", "BUY", 100, price=100.0)

    assert result.ok is True
    assert session.calls[0]["json"]["orderType"] == "LO"
    assert session.calls[0]["json"]["price"] == 100.0


def test_derivative_qty_not_forced_to_round_lot(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING", False)
    monkeypatch.setattr(config, "AUTO_TRADE_ENABLED", True)
    session = FakeSession([FakeResponse(200, {"orderId": "O1", "status": "NEW"})])
    conn = _connector(session)
    conn.trading_token = "tok"
    conn.trading_token_expires_at = 9999999999
    conn._symbol_map = {"VN30F1M": "41I1G6000"}
    conn._symbol_map_ts = 9999999999

    result = conn.send_order("VN30F1M", "BUY", 1, price=1200.0)

    assert result.ok is True
    assert session.calls[0]["json"]["quantity"] == 1  # phái sinh không bị ép bội 100

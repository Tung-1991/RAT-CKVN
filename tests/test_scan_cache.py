# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

import pandas as pd
import pytest

import config
from ai_advisor import paths, scan_cache


NOW = datetime(2026, 7, 7, 10, 30)  # thứ Ba, trong phiên sáng


def make_daily_df(days=30, last_is_today=True, base_price=28.0, base_vol=1_000_000):
    """DF khung ngày synthetic: giá tăng dần, volume tăng dần, nến cuối = hôm nay."""
    end = NOW.date() if last_is_today else NOW.date() - timedelta(days=1)
    times = pd.to_datetime([end - timedelta(days=days - 1 - i) for i in range(days)])
    closes = [base_price + i * 0.1 for i in range(days)]
    vols = [base_vol + i * 10_000 for i in range(days)]
    df = pd.DataFrame({
        "time": times,
        "open": [c - 0.05 for c in closes],
        "high": [c + 0.2 for c in closes],
        "low": [c - 0.2 for c in closes],
        "close": closes,
        "volume": vols,
    })
    return df


def make_intraday_df(bars=50):
    times = pd.to_datetime([NOW - timedelta(minutes=15 * (bars - i)) for i in range(bars)])
    closes = [30.0 + i * 0.01 for i in range(bars)]
    return pd.DataFrame({
        "time": times,
        "open": closes, "high": [c + 0.1 for c in closes],
        "low": [c - 0.1 for c in closes], "close": closes,
        "volume": [10_000] * bars,
    })


def make_context(market_open=True, price=31.0):
    return {
        "symbol": "HPG", "current_price": price, "market_open": market_open,
        "trend_G0": "UP", "trend_G1": "UP", "trend_G2": "NONE", "trend_G3": "NONE",
        "market_mode": "TRENDING", "mode_source": "G0", "block_reason": "OK / Ready",
        "group_signals": {"G0": 1, "G1": 1, "G2": 0, "G3": 0},
        "ema20_G0": 30.0,
    }


@pytest.fixture
def dfs():
    return {"G0": make_daily_df(), "G1": make_intraday_df(), "G2": make_intraday_df(), "G3": make_intraday_df()}


# ---------------------------------------------------------------- hàm thuần
def test_session_elapsed_fraction():
    assert scan_cache.session_elapsed_fraction(datetime(2026, 7, 7, 8, 0)) == 0.0
    assert scan_cache.session_elapsed_fraction(datetime(2026, 7, 7, 15, 0)) == 1.0
    mid = scan_cache.session_elapsed_fraction(datetime(2026, 7, 7, 10, 15))
    assert 0.25 < mid < 0.35  # 75/255 phút


def test_pick_daily_df(dfs):
    grp, df = scan_cache.pick_daily_df(dfs)
    assert grp == "G0"
    assert df is dfs["G0"]


def test_price_block_partial_bar(dfs):
    snap = scan_cache.compute_snapshot(dfs, make_context(), 0, now=NOW)
    price = snap["price"]
    assert price["daily_bar_is_today"] is True
    # pct_1d so current (31.0) với close hôm QUA (nến -2), không phải nến đang hình thành
    prev_close = dfs["G0"]["close"].iloc[-2]
    assert price["pct_1d"] == round((31.0 - prev_close) / prev_close * 100, 2)
    assert price["pct_1w"] is not None
    assert price["high_1w"] >= price["low_1w"]


def test_volume_block_partial_excludes_forming_bar(dfs):
    snap = scan_cache.compute_snapshot(dfs, make_context(market_open=True), 0, now=NOW)
    vol = snap["volume"]
    assert vol["is_partial_bar"] is True
    # avg20 tính trên nến ĐÃ ĐÓNG (loại nến hôm nay)
    expected_avg = dfs["G0"]["volume"].iloc[:-1].tail(20).mean()
    assert vol["avg20"] == round(float(expected_avg), 0)
    assert vol["ratio"] is not None
    assert vol["projected_ratio"] > vol["ratio"]  # pro-rate phiên mới trôi ~30%
    assert vol["trend_5d"] == "đi ngang"  # volume tăng ~5%/tuần < ngưỡng 10%


def test_volume_block_closed_market(dfs):
    now_closed = NOW.replace(hour=15, minute=0)
    snap = scan_cache.compute_snapshot(dfs, make_context(market_open=False), 0, now=now_closed)
    assert snap["volume"]["is_partial_bar"] is False
    assert snap["volume"]["projected_ratio"] is None


def test_indicator_extraction(dfs):
    dfs["G0"]["RSI_14"] = 61.2
    dfs["G0"]["MACD_12_26_9"] = 0.15
    dfs["G0"]["MACDh_12_26_9"] = 0.03
    dfs["G0"]["EMA_50"] = 29.5
    dfs["G0"]["BBL_20_2.0"] = 29.0
    dfs["G0"]["BBU_20_2.0"] = 33.0
    snap = scan_cache.compute_snapshot(dfs, make_context(), 1, now=NOW)
    g0 = snap["indicators"]["G0"]
    assert g0["rsi"] == 61.2
    assert g0["macd"] == 0.15
    assert g0["ema"]["EMA_50"] == 29.5
    assert 0 <= g0["bb_pos_pct"] <= 100
    assert g0["close_vs_ema20_pct"] is not None
    assert snap["bot"]["latest_signal"] == 1
    assert snap["bot"]["market_mode"] == "TRENDING"


def test_merge_sample_and_signal_dedup(dfs):
    cache = scan_cache.empty_cache()
    snap = scan_cache.compute_snapshot(dfs, make_context(), 0, now=NOW)
    entry = scan_cache.merge_sample(cache, "HPG", snap, now=NOW)
    assert entry["samples"] == 1 and entry["first_scan"] == "10:30"
    scan_cache.merge_sample(cache, "HPG", snap, now=NOW + timedelta(minutes=20))
    assert entry["samples"] == 2 and entry["last_scan"] == "10:50"

    ctx = make_context()
    assert scan_cache.record_signal_event(cache, "HPG", "BUY", ctx, now=NOW) is True
    # Cùng chiều trong 30 phút -> dedup
    assert scan_cache.record_signal_event(cache, "HPG", "BUY", ctx, now=NOW + timedelta(minutes=10)) is False
    # Khác chiều -> ghi
    assert scan_cache.record_signal_event(cache, "HPG", "SELL", ctx, now=NOW + timedelta(minutes=10)) is True
    # Cùng chiều sau 30 phút -> ghi
    assert scan_cache.record_signal_event(cache, "HPG", "BUY", ctx, now=NOW + timedelta(minutes=40)) is True
    day = NOW.strftime("%Y-%m-%d")
    assert len(cache["symbols"]["HPG"]["days"][day]["signals"]) == 3
    assert scan_cache.derive_weekly(cache["symbols"]["HPG"]) == {"buy": 2, "sell": 1}


def test_prune_retention(dfs):
    cache = scan_cache.empty_cache()
    snap = scan_cache.compute_snapshot(dfs, make_context(), 0, now=NOW)
    for i in range(15):
        scan_cache.merge_sample(cache, "HPG", snap, now=NOW - timedelta(days=14 - i))
    scan_cache.prune(cache, retention_days=10)
    assert len(cache["symbols"]["HPG"]["days"]) == 10
    assert min(cache["symbols"]["HPG"]["days"]) == (NOW - timedelta(days=9)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- I/O + recorder
@pytest.fixture
def tmp_account(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "account_dir", lambda: str(tmp_path))
    return tmp_path


def test_save_load_round_trip(tmp_account, dfs):
    cache = scan_cache.empty_cache()
    snap = scan_cache.compute_snapshot(dfs, make_context(), 1, now=NOW)
    scan_cache.merge_sample(cache, "HPG", snap, now=NOW)
    assert scan_cache.save_cache(cache) is True
    loaded = scan_cache.load_cache()
    assert loaded["symbols"]["HPG"]["days"][NOW.strftime("%Y-%m-%d")]["samples"] == 1


def test_load_corrupt_file_recovers(tmp_account, tmp_path):
    (tmp_path / "scan_snapshot_cache.json").write_text("{hỏng json", encoding="utf-8")
    loaded = scan_cache.load_cache()
    assert loaded == scan_cache.empty_cache()


def test_recorder_throttle_and_signal(tmp_account, monkeypatch, dfs):
    monkeypatch.setattr(config, "SCAN_SNAPSHOT_INTERVAL_MINUTES", 15, raising=False)
    rec = scan_cache.ScanSnapshotRecorder()
    ctx = make_context()
    rec.maybe_record("HPG", dfs, ctx, 0, now=NOW)
    rec.maybe_record("HPG", dfs, ctx, 0, now=NOW + timedelta(minutes=1))  # trong interval -> bỏ qua
    rec.flush()
    day = NOW.strftime("%Y-%m-%d")
    saved = scan_cache.load_cache()
    assert saved["symbols"]["HPG"]["days"][day]["samples"] == 1

    # Tín hiệu BUY ghi NGAY bất chấp throttle
    rec.maybe_record("HPG", dfs, ctx, 1, now=NOW + timedelta(minutes=2))
    rec.flush()
    saved = scan_cache.load_cache()
    assert saved["symbols"]["HPG"]["days"][day]["signals"][0]["side"] == "BUY"


def test_recorder_eod_final(tmp_account, monkeypatch, dfs):
    monkeypatch.setattr(config, "SCAN_SNAPSHOT_INTERVAL_MINUTES", 15, raising=False)
    rec = scan_cache.ScanSnapshotRecorder()
    now_closed = NOW.replace(hour=15, minute=5)
    ctx = make_context(market_open=False)
    rec.maybe_record("HPG", dfs, ctx, 0, now=now_closed)
    rec.flush()
    day = NOW.strftime("%Y-%m-%d")
    saved = scan_cache.load_cache()
    entry = saved["symbols"]["HPG"]["days"][day]
    assert entry["eod_final"] is True
    # Đã final -> lần quét sau ngoài giờ không ghi thêm
    rec.maybe_record("HPG", dfs, ctx, 0, now=now_closed + timedelta(minutes=30))
    rec.flush()
    assert scan_cache.load_cache()["symbols"]["HPG"]["days"][day]["samples"] == entry["samples"]


# ---------------------------------------------------------------- renderer + API section
def _build_populated_cache(dfs):
    cache = scan_cache.empty_cache()
    snap = scan_cache.compute_snapshot(dfs, make_context(), 1, now=NOW)
    scan_cache.merge_sample(cache, "HPG", snap, now=NOW - timedelta(days=1))
    scan_cache.merge_sample(cache, "HPG", snap, now=NOW)
    scan_cache.record_signal_event(cache, "HPG", "BUY", make_context(), now=NOW)
    return cache


def test_compact_summary_render(dfs):
    from ai_advisor import scan_report

    cache = _build_populated_cache(dfs)
    text = scan_report.build_compact_summary(cache)
    assert "CHỈ DẪN CHO AI" in text
    assert "MUA MỚI / TRÁNH / CHỐT LỜI" in text
    assert "### HPG" in text
    assert "BUY 10:30" in text
    # Kho trống -> chuỗi rỗng (để build_api_sections bỏ qua)
    assert scan_report.build_compact_summary(scan_cache.empty_cache()) == ""


def test_full_report_render(dfs):
    from ai_advisor import scan_report

    cache = _build_populated_cache(dfs)
    text = scan_report.render_full_report(cache)
    assert "## Bảng tổng hợp" in text
    assert "## HPG — lịch sử 2 ngày" in text
    assert "Tín hiệu đã bắn:" in text


def test_export_scan_files_and_api_section(tmp_account, dfs):
    from ai_advisor import api_client, scan_report

    # Kho trống -> không sinh file, section không được thêm
    assert scan_report.export_scan_files() is None
    sections = dict(api_client.build_api_sections())
    assert "scan_summary.md" not in sections

    cache = _build_populated_cache(dfs)
    scan_cache.save_cache(cache)
    result = scan_report.export_scan_files()
    assert result is not None and result["symbols"] == 1
    import os
    assert os.path.exists(paths.scan_summary_path())
    assert os.path.exists(paths.scan_report_path())

    sections = dict(api_client.build_api_sections())
    assert "scan_summary.md" in sections
    assert "### HPG" in sections["scan_summary.md"]


def test_recorder_skips_non_trading_day(tmp_account, monkeypatch):
    """Cuối tuần: nến ngày cuối KHÔNG phải hôm nay -> không tạo entry rác."""
    monkeypatch.setattr(config, "SCAN_SNAPSHOT_INTERVAL_MINUTES", 15, raising=False)
    dfs_stale = {"G0": make_daily_df(last_is_today=False), "G1": make_intraday_df(),
                 "G2": make_intraday_df(), "G3": make_intraday_df()}
    rec = scan_cache.ScanSnapshotRecorder()
    rec.maybe_record("HPG", dfs_stale, make_context(market_open=False), 0, now=NOW)
    rec.flush()
    assert "HPG" not in scan_cache.load_cache()["symbols"]

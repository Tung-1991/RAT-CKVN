# -*- coding: utf-8 -*-
"""Render kho scan snapshot thành 2 file Markdown cho AI Advisor.

- scan_summary.md : bản NÉN đi kèm payload API (mỗi mã vài dòng).
- scan_report.md  : bản ĐẦY ĐỦ (lịch sử 10 ngày + log tín hiệu) để copy
  manual lên web AI khi muốn phân tích sâu.

Chỉ dẫn cho AI được nhúng thẳng vào file (không dựa vào advisor_prompt.md
per-account vì template chỉ seed khi file chưa tồn tại).
"""
import logging
import os

from ai_advisor import paths, scan_cache

logger = logging.getLogger(__name__)

AI_INSTRUCTIONS = """> **CHỈ DẪN CHO AI (bắt buộc đọc trước khi phân tích):**
> Dưới đây là dữ liệu quét tích lũy của các mã đang theo dõi (indicator thuần, CHƯA có bối cảnh).
> 1. Với TỪNG mã, hãy dùng web_search tra cứu bối cảnh mới nhất: thuộc ngành nào (ngân hàng /
>    dầu khí / BĐS / thép / bán lẻ...), diễn biến khối ngoại mua/bán ròng, tin tức doanh nghiệp,
>    và trạng thái dòng tiền vào ngành đó.
> 2. **Volume là trọng số CAO NHẤT** — thị trường VN cực nhạy volume. Ưu tiên mã có volume
>    đột biến so với trung bình 20 phiên kèm giá tăng; cảnh giác giá tăng volume cạn.
> 3. Cổ phiếu cơ sở giao dịch T+2 (mua xong ~2.5 ngày mới bán được), nhiều người giữ tới T+10.
>    Đánh giá theo tầm nhìn NẮM GIỮ 3-10 PHIÊN, không phải lướt trong ngày.
> 4. Tín hiệu mean-reversion (RSI thấp, chạm band dưới) ở cổ phiếu cơ sở phải đối chiếu
>    thanh khoản + nguy cơ sàn nhiều phiên trước khi khuyến nghị (không short được cơ sở).
> 5. Dòng nào ghi `(intraday)` là số ước tính giữa phiên (nến ngày chưa đóng); `(EOD)` là số
>    chốt phiên chính thức.
> 6. KẾT LUẬN bắt buộc: xếp các mã vào 3 nhóm **MUA MỚI / TRÁNH / CHỐT LỜI (nếu đang giữ)**,
>    mỗi mã kèm 1-2 câu lý do tổng hợp cả indicator lẫn bối cảnh web_search.
>
> **Chú giải field (dữ liệu do bot Python sinh tự động, không phải người viết):**
> - G0..G3 = 4 khung nến bot phân tích, G0 lớn nhất (thường khung ngày) → G3 nhỏ nhất.
> - "trend UP/DOWN/NONE" theo thứ tự G0/G1/G2/G3 = xu hướng bot tính trên từng khung.
> - "mode" = chế độ thị trường bot nhận diện (TRENDING / SIDEWAY...) để chọn bộ indicator.
> - "x2.4 avg20" = volume hôm nay gấp 2.4 lần trung bình 20 phiên. "pro-rate" = volume quy đổi
>   cả phiên khi phiên chưa kết thúc (nến ngày chưa đóng — số tham khảo, không phải final).
> - "3 BUY / 0 SELL" = số tín hiệu kỹ thuật bot đã bắn trong các ngày lưu; bot có thể KHÔNG
>   vào lệnh thật — tín hiệu ≠ giao dịch. Giao dịch thật/paper nằm trong advisor_export.xlsx.
> - Indicator nào không hiện = operator không bật indicator đó, không phải lỗi dữ liệu.
>
> Đơn vị giá: cổ phiếu cơ sở = nghìn VND; phái sinh = điểm chỉ số."""


def _fmt(value, suffix="", nd=None):
    if value is None:
        return "—"
    try:
        if nd is not None:
            value = round(float(value), nd)
        if isinstance(value, float) and value == int(value):
            value = int(value)
        return f"{value:,}{suffix}" if isinstance(value, (int, float)) else f"{value}{suffix}"
    except Exception:
        return str(value)


def _pct(value):
    if value is None:
        return "—"
    return f"{value:+.2f}%"


def _latest_day(sym_node):
    days = sym_node.get("days", {})
    if not days:
        return None, None
    day = max(days)
    return day, days[day]


def _daily_indicators(entry):
    inds = entry.get("indicators") or {}
    grp = entry.get("daily_group") or "G0"
    return inds.get(grp) or next(iter(inds.values()), {})


def _ind_line(entry):
    ind = _daily_indicators(entry)
    parts = []
    if ind.get("rsi") is not None:
        parts.append(f"RSI {ind['rsi']:.1f}")
    if ind.get("macd") is not None:
        hist = ind.get("macd_hist")
        parts.append(f"MACD {ind['macd']:.2f}" + (f" (hist {hist:+.2f})" if hist is not None else ""))
    if ind.get("bb_pos_pct") is not None:
        parts.append(f"BB {ind['bb_pos_pct']:.0f}%")
    if ind.get("close_vs_ema20_pct") is not None:
        parts.append(f"vs EMA20 {ind['close_vs_ema20_pct']:+.1f}%")
    if ind.get("adx") is not None:
        parts.append(f"ADX {ind['adx']:.0f}")
    if ind.get("supertrend_dir") is not None:
        parts.append("SuperTrend " + ("UP" if ind["supertrend_dir"] > 0 else "DOWN"))
    return " | ".join(parts) if parts else "—"


def _freshness(entry):
    return "EOD" if entry.get("eod_final") else f"intraday ~{entry.get('last_scan', '?')}"


def _symbol_block_compact(sym, sym_node):
    day, entry = _latest_day(sym_node)
    if not entry:
        return None
    price, vol, bot = entry.get("price", {}), entry.get("volume", {}), entry.get("bot", {})
    weekly = scan_cache.derive_weekly(sym_node)

    vol_bits = f"{_fmt(vol.get('today'))} (x{_fmt(vol.get('ratio'))} avg20"
    if vol.get("projected_ratio") is not None:
        vol_bits += f", pro-rate x{_fmt(vol.get('projected_ratio'))}"
    vol_bits += f"; 5 ngày: {vol.get('trend_5d') or '—'})"

    trends = "/".join(str(bot.get(f"trend_{g}") or "-") for g in ("G0", "G1", "G2", "G3"))
    today_signals = ", ".join(
        f"{ev['side']} {ev['time']}" for ev in entry.get("signals", [])
    ) or "không có"

    lines = [
        f"### {sym} — {day} ({_freshness(entry)})",
        f"- Giá: {_fmt(price.get('current'), nd=2)} ({_pct(price.get('pct_1d'))} ngày, {_pct(price.get('pct_1w'))} tuần; H/L tuần {_fmt(price.get('high_1w'), nd=2)}/{_fmt(price.get('low_1w'), nd=2)})",
        f"- Volume: {vol_bits}",
        f"- Indicator ngày: {_ind_line(entry)}",
        f"- Bot: trend {trends} | mode {bot.get('market_mode') or '—'} | {bot.get('block_reason') or '—'}",
        f"- Tín hiệu hôm nay: {today_signals}. Cộng dồn {len(sym_node.get('days', {}))} ngày gần nhất: {weekly['buy']} BUY / {weekly['sell']} SELL",
    ]
    return "\n".join(lines)


def build_compact_summary(cache=None):
    cache = cache or scan_cache.load_cache()
    symbols = cache.get("symbols", {})
    if not symbols:
        return ""
    parts = [
        "# SCAN WATCHLIST — DỮ LIỆU QUÉT TÍCH LŨY",
        "",
        AI_INSTRUCTIONS,
        "",
        f"Cập nhật: {cache.get('updated_at') or '—'} | Số mã: {len(symbols)}",
        "",
    ]
    for sym in sorted(symbols):
        block = _symbol_block_compact(sym, symbols[sym])
        if block:
            parts.append(block)
            parts.append("")
    return "\n".join(parts).strip() + "\n"


def render_full_report(cache=None):
    cache = cache or scan_cache.load_cache()
    symbols = cache.get("symbols", {})
    if not symbols:
        return ""
    parts = [
        "# BÁO CÁO WATCHLIST ĐẦY ĐỦ (copy nguyên văn cho AI phân tích)",
        "",
        AI_INSTRUCTIONS,
        "",
        f"Cập nhật: {cache.get('updated_at') or '—'} | Số mã: {len(symbols)}",
        "",
        "## Bảng tổng hợp (ngày gần nhất)",
        "",
        "| Mã | Giá | %1D | %1W | Vol x avg20 | Vol 5d | RSI | Mode | Tín hiệu (kho) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for sym in sorted(symbols):
        day, entry = _latest_day(symbols[sym])
        if not entry:
            continue
        price, vol = entry.get("price", {}), entry.get("volume", {})
        ind = _daily_indicators(entry)
        weekly = scan_cache.derive_weekly(symbols[sym])
        rsi = f"{ind['rsi']:.1f}" if ind.get("rsi") is not None else "—"
        parts.append(
            f"| {sym} | {_fmt(price.get('current'), nd=2)} | {_pct(price.get('pct_1d'))} | {_pct(price.get('pct_1w'))} "
            f"| x{_fmt(vol.get('ratio'))} | {vol.get('trend_5d') or '—'} | {rsi} "
            f"| {(entry.get('bot') or {}).get('market_mode') or '—'} | {weekly['buy']}B/{weekly['sell']}S |"
        )
    parts.append("")

    for sym in sorted(symbols):
        days = symbols[sym].get("days", {})
        if not days:
            continue
        parts.append(f"## {sym} — lịch sử {len(days)} ngày")
        parts.append("")
        parts.append("| Ngày | Giá | %1D | Vol | x avg20 | RSI | Mode | Nguồn |")
        parts.append("|---|---|---|---|---|---|---|---|")
        for day in sorted(days, reverse=True):
            e = days[day]
            p, v = e.get("price", {}), e.get("volume", {})
            ind = _daily_indicators(e)
            rsi = f"{ind['rsi']:.1f}" if ind.get("rsi") is not None else "—"
            parts.append(
                f"| {day} | {_fmt(p.get('current'), nd=2)} | {_pct(p.get('pct_1d'))} | {_fmt(v.get('today'))} "
                f"| x{_fmt(v.get('ratio'))} | {rsi} | {(e.get('bot') or {}).get('market_mode') or '—'} | {_freshness(e)} |"
            )
        events = [
            (day, ev) for day in sorted(days, reverse=True) for ev in days[day].get("signals", [])
        ]
        if events:
            parts.append("")
            parts.append("Tín hiệu đã bắn:")
            for day, ev in events:
                parts.append(f"- {day} {ev.get('time')} **{ev.get('side')}** (mode {ev.get('mode') or '—'}; {ev.get('note') or '—'})")
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def export_scan_files():
    """Sinh scan_summary.md + scan_report.md vào folder advisor package.

    Trả về dict {summary, report, symbols} hoặc None nếu kho trống/chưa bật.
    """
    cache = scan_cache.load_cache()
    if not cache.get("symbols"):
        return None
    paths.ensure_advisor_dirs()
    summary_text = build_compact_summary(cache)
    report_text = render_full_report(cache)
    summary_path = paths.scan_summary_path()
    report_path = paths.scan_report_path()
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    return {
        "summary": os.path.abspath(summary_path),
        "report": os.path.abspath(report_path),
        "symbols": len(cache["symbols"]),
    }

# -*- coding: utf-8 -*-
"""Xuất báo cáo động từ kho tổng hợp ngày của nhánh CHECK."""
import json
import logging
import os
import threading
import uuid

from ai_advisor import paths, scan_cache

logger = logging.getLogger(__name__)

AI_INSTRUCTIONS = """> **CÁCH ĐỌC DỮ LIỆU**
> - CHECK là dữ liệu kỹ thuật phục vụ báo cáo; không phải lệnh và không tác động BOT TRADE.
> - Chỉ phân tích những module CHECK thực sự xuất hiện. Không giả định RSI, MACD, Bollinger Bands hoặc bất kỳ module nào luôn tồn tại.
> - `BOT signal` là tín hiệu của nhánh TRADE. `CHECK view` chỉ là BUY/SELL/WAIT tham khảo của module báo cáo.
> - Nếu một ngày có nhiều `CHECK segment`, operator đã đổi cấu hình giữa phiên; không trộn số liệu giữa các segment.
> - Có thể dùng web search để bổ sung tin tức/bối cảnh mới, nhưng phải tách rõ dữ liệu nội bộ và thông tin tìm trên web.
> - Đơn vị giá: CKCS thường là nghìn VND; CKPS là điểm chỉ số. Operator tự quyết định khung nắm giữ."""


def _fmt(value, nd=None):
    if value is None:
        return "—"
    try:
        if nd is not None:
            value = round(float(value), nd)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return f"{value:,}" if isinstance(value, (int, float)) else str(value)
    except Exception:
        return str(value)


def _pct(value):
    return "—" if value is None else f"{float(value):+.2f}%"


def _slice_days(sym_node, report_days=None):
    days = sym_node.get("days", {})
    names = sorted(days)
    if report_days is not None:
        names = names[-max(1, int(report_days)):]
    return [(day, days[day]) for day in names]


def _signal_label(value):
    try:
        value = int(value)
    except Exception:
        value = 0
    return "BUY" if value > 0 else ("SELL" if value < 0 else "WAIT")


def _metric_text(metric):
    if not isinstance(metric, dict):
        return _fmt(metric)
    if metric.get("kind") == "number":
        return (f"đầu {_fmt(metric.get('first'), 4)}; thấp {_fmt(metric.get('min'), 4)}; "
                f"cao {_fmt(metric.get('max'), 4)}; TB {_fmt(metric.get('avg'), 4)}; "
                f"cuối {_fmt(metric.get('last'), 4)}")
    if metric.get("kind") == "state":
        return (f"đầu {metric.get('first', '—')}; cuối {metric.get('last', '—')}; "
                f"đổi {metric.get('changes', 0)} lần")
    return json.dumps(metric, ensure_ascii=False, default=str)


def _module_line(group, name, module):
    params = json.dumps(module.get("params", {}), ensure_ascii=False, sort_keys=True, default=str)
    counts = module.get("signal_counts", {})
    views = "/".join(f"{key}:{counts[key]}" for key in ("BUY", "SELL", "WAIT") if key in counts) or "—"
    head = f"- CHECK `{group}.{name}` params `{params}` | view cuối {_signal_label(module.get('latest_signal'))} | đếm {views}"
    if module.get("error"):
        head += f" | lỗi `{module['error']}`"
    lines = [head]
    for metric_name, metric in sorted((module.get("metrics") or {}).items()):
        lines.append(f"  - `{metric_name}`: {_metric_text(metric)}")
    return lines


def _segments_lines(entry):
    segments = entry.get("check_segments") or []
    if not segments:
        return ["- CHECK: không bật module hoặc chưa có kết quả."]
    lines = []
    for index, segment in enumerate(segments, 1):
        lines.append(
            f"- CHECK segment {index}: config `{segment.get('config_id', '—')}`, "
            f"{segment.get('first_scan', '—')}–{segment.get('last_scan', '—')}, "
            f"{segment.get('samples', 0)} lần cập nhật"
        )
        for group, modules in sorted((segment.get("groups") or {}).items()):
            for name, module in sorted((modules or {}).items()):
                lines.extend(_module_line(group, name, module))
    return lines


def _bot_line(entry):
    bot = entry.get("bot") or {}
    trends = "/".join(str(bot.get(f"trend_{group}") or "-") for group in ("G0", "G1", "G2", "G3"))
    events = ", ".join(f"{event.get('side')} {event.get('time')}" for event in entry.get("signals", [])) or "không có"
    counts = entry.get("bot_signal_counts") or {}
    count_text = "/".join(f"{name}:{counts.get(name, 0)}" for name in ("BUY", "SELL", "WAIT"))
    return (f"BOT signal cuối {_signal_label(bot.get('latest_signal'))}; trend {trends}; "
            f"mode {bot.get('market_mode') or '—'}; đếm lần quét {count_text}; sự kiện trong ngày: {events}")


def _daily_header(day, entry):
    price, volume = entry.get("price") or {}, entry.get("volume") or {}
    status = str(entry.get("day_status") or ("EOD" if entry.get("eod_final") else "INTRADAY")).upper()
    freshness = "EOD" if status == "EOD" else (
        f"incomplete, lần cuối {entry.get('last_scan', '—')}"
        if status == "INCOMPLETE"
        else f"intraday {entry.get('last_scan', '—')}"
    )
    return [
        f"### {day} ({freshness}; cập nhật {entry.get('samples', 0)} lần)",
        (f"- Giá O/H/L/C: {_fmt(price.get('open'), 2)}/{_fmt(price.get('high'), 2)}/"
         f"{_fmt(price.get('low'), 2)}/{_fmt(price.get('close'), 2)}; hiện tại {_fmt(price.get('current'), 2)}; "
         f"1D {_pct(price.get('pct_1d'))}; 1W {_pct(price.get('pct_1w'))}"),
        (f"- Khối lượng: {_fmt(volume.get('today'))}; TB20 {_fmt(volume.get('avg20'))}; "
         f"tỷ lệ x{_fmt(volume.get('ratio'), 2)}; xu hướng 5 ngày {volume.get('trend_5d') or '—'}"),
        f"- {_bot_line(entry)}",
    ]


def _range_summary(days):
    """Tổng hợp giá trị cuối ngày theo tên module/metric trong toàn khoảng N ngày."""
    values = {}
    for day, entry in days:
        for segment in entry.get("check_segments") or []:
            for group, modules in (segment.get("groups") or {}).items():
                for name, module in (modules or {}).items():
                    for metric_name, metric in (module.get("metrics") or {}).items():
                        key = (group, name, metric_name)
                        value = metric.get("last") if isinstance(metric, dict) else metric
                        values.setdefault(key, []).append((day, value))
    lines = []
    for (group, name, metric_name), observations in sorted(values.items()):
        numeric = [float(value) for _, value in observations if isinstance(value, (int, float)) and not isinstance(value, bool)]
        first_day, first = observations[0]
        last_day, last = observations[-1]
        if numeric:
            text = (f"đầu {first_day}={_fmt(first, 4)}; thấp {_fmt(min(numeric), 4)}; "
                    f"cao {_fmt(max(numeric), 4)}; TB {_fmt(sum(numeric) / len(numeric), 4)}; "
                    f"cuối {last_day}={_fmt(last, 4)}")
        else:
            changes = sum(observations[i][1] != observations[i - 1][1] for i in range(1, len(observations)))
            text = f"đầu {first_day}={first}; cuối {last_day}={last}; đổi {changes} lần"
        lines.append(f"- `{group}.{name}.{metric_name}`: {text}")
    return lines or ["- Không có số liệu CHECK trong khoảng đã chọn."]


def build_compact_summary(cache=None, report_days=None):
    cache = cache or scan_cache.load_cache()
    symbols = cache.get("symbols", {})
    if not symbols:
        return ""
    parts = ["# SCAN SUMMARY — CHECK ĐỘNG", "", AI_INSTRUCTIONS, "",
             f"Cập nhật: {cache.get('updated_at') or '—'} | Số mã: {len(symbols)}", ""]
    for symbol in sorted(symbols):
        days = _slice_days(symbols[symbol], report_days)
        if not days:
            continue
        day, entry = days[-1]
        parts.extend([f"## {symbol}", *_daily_header(day, entry)])
        parts.extend(_segments_lines(entry))
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def render_full_report(cache=None, report_days=None):
    cache = cache or scan_cache.load_cache()
    symbols = cache.get("symbols", {})
    if not symbols:
        return ""
    parts = ["# SCAN REPORT — DỮ LIỆU NGÀY VÀ CHECK ĐỘNG", "", AI_INSTRUCTIONS, "",
             f"Cập nhật: {cache.get('updated_at') or '—'} | Số mã: {len(symbols)}", ""]
    for symbol in sorted(symbols):
        days = _slice_days(symbols[symbol], report_days)
        if not days:
            continue
        parts.extend([f"## {symbol} — {len(days)} ngày giao dịch", "", "### Biến động toàn khoảng"])
        parts.extend(_range_summary(days))
        parts.append("")
        for day, entry in reversed(days):
            parts.extend(_daily_header(day, entry))
            parts.extend(_segments_lines(entry))
            parts.append("")
    return "\n".join(parts).strip() + "\n"


def export_ckcs_report(report_days=None):
    """Tạo đúng một file MD đầy đủ để người dùng tự gửi LLM."""
    cache = scan_cache.load_cache()
    selected = set(scan_cache.selected_research_symbols())
    cache = dict(cache)
    cache["symbols"] = {
        symbol: node
        for symbol, node in (cache.get("symbols", {}) or {}).items()
        if str(symbol).upper() in selected
    }
    if not cache.get("symbols"):
        return None
    paths.ensure_ckcs_research_dir()
    report_text = render_full_report(cache, report_days=report_days)
    report_path = paths.scan_report_path()
    tmp_path = f"{report_path}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(report_text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, report_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    requested_days = max(1, int(report_days or 1))
    included_days = {
        day
        for node in cache["symbols"].values()
        for day, _entry in _slice_days(node, requested_days)
    }
    return {
        "report": os.path.abspath(report_path),
        "symbols": len(cache["symbols"]),
        "days": len(included_days),
        "requested_days": requested_days,
    }

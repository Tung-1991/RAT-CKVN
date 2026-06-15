# -*- coding: utf-8 -*-
"""Per-symbol HEDGE override popup."""

from tkinter import messagebox

import customtkinter as ctk

import config
from hedge.hedge_storage import load_hedge_settings, save_hedge_settings

COL_WARN = "#FFB300"


def _symbols():
    return list(getattr(config, "COIN_LIST", []) or [getattr(config, "DEFAULT_SYMBOL", "ETHUSD")])


def _base_cfg():
    cfg = load_hedge_settings()
    cfg.setdefault("SYMBOL_OVERRIDES", {})
    return cfg


def _effective_cfg(symbol):
    cfg = _base_cfg()
    eff = dict(cfg)
    override = cfg.get("SYMBOL_OVERRIDES", {}).get(symbol, {})
    if isinstance(override, dict):
        eff.update(override)
    return eff


def _has_override(symbol):
    return bool((_base_cfg().get("SYMBOL_OVERRIDES") or {}).get(symbol))


def open_hedge_override_popup(app, symbol=None, on_close=None):
    if not symbol:
        cbo = getattr(app, "cbo_symbol", None)
        symbol = cbo.get() if cbo else getattr(config, "DEFAULT_SYMBOL", "ETHUSD")

    top = ctk.CTkToplevel(app)
    top.title("HEDGE Symbol Override")
    top.geometry("1080x700")
    top.minsize(980, 620)
    top.attributes("-topmost", True)
    top.focus_force()
    top.grab_set()

    selected = ctk.StringVar(value=symbol)

    header = ctk.CTkFrame(top, fg_color="#202020", corner_radius=8)
    header.pack(fill="x", padx=12, pady=(12, 8))
    lbl_title = ctk.CTkLabel(header, text="", font=("Roboto", 16, "bold"), text_color="#CE93D8")
    lbl_title.pack(anchor="w", padx=12, pady=(10, 4))
    ctk.CTkLabel(
        header,
        text="Override riêng cho từng symbol. HEDGE chỉ bật/tắt filter có sẵn và giữ state/log riêng.",
        font=("Arial", 12, "italic"),
        text_color="#F8BBD0",
        wraplength=980,
        justify="left",
    ).pack(anchor="w", padx=12, pady=(0, 10))

    body = ctk.CTkFrame(top, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    body.grid_columnconfigure(1, weight=1)
    body.grid_rowconfigure(0, weight=1)

    list_frame = ctk.CTkScrollableFrame(body, width=220, fg_color="#1E1E1E", corner_radius=8)
    list_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
    edit = ctk.CTkScrollableFrame(body, fg_color="#242424", corner_radius=8)
    edit.grid(row=0, column=1, sticky="nsew")
    edit.grid_columnconfigure((0, 1), weight=1)

    checks = {
        "USE_SIGNAL_FILTER": ctk.BooleanVar(value=False),
        "USE_ENTRY_EXIT_FILTER": ctk.BooleanVar(value=False),
        "USE_HEDGE_SLTP": ctk.BooleanVar(value=True),
        "USE_TSL": ctk.BooleanVar(value=True),
    }
    fields = {}

    def section(parent, title, row, col, color="#CE93D8", columnspan=1):
        frame = ctk.CTkFrame(parent, fg_color="#202020", corner_radius=8, border_width=1, border_color="#3A3A3A")
        frame.grid(row=row, column=col, columnspan=columnspan, sticky="new", padx=10, pady=8)
        frame.grid_columnconfigure((1, 3, 5, 7), weight=1)
        ctk.CTkLabel(frame, text=title, font=("Roboto", 12, "bold"), text_color=color).grid(
            row=0, column=0, columnspan=8, sticky="w", padx=10, pady=(8, 4)
        )
        return frame

    def entry(parent, label, key, row, col, width=100):
        label_widget = ctk.CTkLabel(parent, text=label)
        label_widget.grid(row=row, column=col, sticky="w", padx=10, pady=5)
        widget = ctk.CTkEntry(parent, width=width, justify="center")
        widget.grid(row=row, column=col + 1, sticky="w", padx=10, pady=5)
        widget._label_widget = label_widget
        fields[key] = widget
        return widget

    def zone(parent, title, row, color="#90CAF9"):
        ctk.CTkLabel(
            parent,
            text=title,
            font=("Roboto", 11, "bold"),
            text_color=color,
        ).grid(row=row, column=0, columnspan=8, sticky="w", padx=10, pady=(10, 2))

    def set_entry(key, value):
        fields[key].delete(0, "end")
        fields[key].insert(0, str(value))

    edit_header = ctk.CTkFrame(edit, fg_color="transparent")
    edit_header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
    edit_header.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(edit_header, text="HEDGE Dual Override", font=("Roboto", 14, "bold"), text_color="#CE93D8").grid(
        row=0, column=0, sticky="w"
    )
    btn_save_override = ctk.CTkButton(
        edit_header,
        text="SAVE SYMBOL SETTINGS",
        fg_color="#7B1FA2",
        hover_color="#4A148C",
        width=180,
        height=30,
        state="disabled",
    )
    btn_save_override.grid(row=0, column=1, sticky="e", padx=(8, 0))
    btn_reset_override = ctk.CTkButton(
        edit_header,
        text="RESET OVERRIDE",
        fg_color="#B71C1C",
        hover_color="#7F0000",
        width=145,
        height=30,
        state="disabled",
    )
    btn_reset_override.grid(row=0, column=2, sticky="e", padx=(8, 0))

    f_risk = section(edit, "1) Risk & SL/TP", 1, 0, "#CE93D8")
    f_filters = section(edit, "2) Filters", 1, 1, "#29B6F6")
    f_safety = section(edit, "3) Safety", 2, 0, "#FFB300", columnspan=2)

    ctk.CTkCheckBox(f_filters, text="Use Signal Filter", variable=checks["USE_SIGNAL_FILTER"]).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=6)
    ctk.CTkCheckBox(f_filters, text="Use Entry/Exit Filter", variable=checks["USE_ENTRY_EXIT_FILTER"]).grid(row=1, column=2, columnspan=2, sticky="w", padx=10, pady=6)
    ctk.CTkLabel(f_filters, text="Signal rule").grid(row=2, column=0, sticky="w", padx=10, pady=5)
    cbo_signal_rule = ctk.CTkOptionMenu(f_filters, values=["SANDBOX_SIGNAL"], width=170)
    cbo_signal_rule.grid(row=2, column=1, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_filters, text="Entry rule").grid(row=2, column=2, sticky="w", padx=10, pady=5)
    cbo_entry_rule = ctk.CTkOptionMenu(f_filters, values=["SWING_REJECTION", "SWING_STRUCTURE", "FIB_RETRACE", "PULLBACK_ZONE", "FALLBACK_R"], width=190)
    cbo_entry_rule.grid(row=2, column=3, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_filters, text="Entry SL").grid(row=3, column=0, sticky="w", padx=10, pady=5)
    cbo_ee_sl_rule = ctk.CTkOptionMenu(f_filters, values=["MATCH_ENTRY", "SWING_REJECTION", "SWING_STRUCTURE", "FIB_RETRACE", "PULLBACK_ZONE", "SANDBOX"], width=170)
    cbo_ee_sl_rule.grid(row=3, column=1, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_filters, text="Entry TP").grid(row=3, column=2, sticky="w", padx=10, pady=5)
    cbo_ee_tp_rule = ctk.CTkOptionMenu(f_filters, values=["MATCH_ENTRY", "RR", "SWING_REJECTION", "SWING_STRUCTURE", "FIB_RETRACE", "PULLBACK_ZONE", "NO_TP"], width=190)
    cbo_ee_tp_rule.grid(row=3, column=3, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(
        f_filters,
        text="Signal chạy trước; Entry/Exit là bộ lọc điểm vào nếu được bật.",
        font=("Arial", 11, "italic"),
        text_color="#B0BEC5",
        wraplength=520,
        justify="left",
    ).grid(row=4, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 8))

    ctk.CTkCheckBox(f_risk, text="HEDGE SL/TP Rule", variable=checks["USE_HEDGE_SLTP"]).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=6)
    ctk.CTkCheckBox(f_risk, text="Use TSL", variable=checks["USE_TSL"]).grid(row=1, column=2, columnspan=2, sticky="w", padx=10, pady=6)
    ctk.CTkLabel(f_risk, text="HEDGE SL rule").grid(row=2, column=0, sticky="w", padx=10, pady=5)
    cbo_sl_rule = ctk.CTkOptionMenu(f_risk, values=["BASE_SL_ATR", "SWING_REJECTION", "SWING_STRUCTURE", "FIB_RETRACE", "PULLBACK_ZONE"], width=190)
    cbo_sl_rule.grid(row=2, column=1, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_risk, text="HEDGE TP rule").grid(row=2, column=2, sticky="w", padx=10, pady=5)
    cbo_tp_rule = ctk.CTkOptionMenu(f_risk, values=["RR", "SWING", "NO_TP"], width=130)
    cbo_tp_rule.grid(row=2, column=3, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_risk, text="Lot mode").grid(row=3, column=0, sticky="w", padx=10, pady=5)
    cbo_lot_mode = ctk.CTkOptionMenu(f_risk, values=["FIXED", "ACCOUNT_RISK"], width=140)
    cbo_lot_mode.grid(row=3, column=1, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_risk, text="Survivor protect").grid(row=3, column=2, sticky="w", padx=10, pady=5)
    cbo_survivor = ctk.CTkOptionMenu(f_risk, values=["BE_FEE", "BE_ONLY", "OFF"], width=130)
    cbo_survivor.grid(row=3, column=3, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_risk, text="TSL tactics", text_color="#00E676", font=("Roboto", 12, "bold")).grid(
        row=4, column=0, sticky="w", padx=10, pady=(8, 4)
    )
    tsl_vars = {
        "BE": ctk.BooleanVar(value=True),
        "PNL": ctk.BooleanVar(value=False),
        "STEP_R": ctk.BooleanVar(value=True),
        "SWING": ctk.BooleanVar(value=True),
        "BE_CASH": ctk.BooleanVar(value=False),
        "PSAR_TRAIL": ctk.BooleanVar(value=False),
    }
    for idx, (label, var) in enumerate(tsl_vars.items()):
        ctk.CTkCheckBox(f_risk, text=label, variable=var).grid(
            row=5 + idx // 3, column=idx % 3, sticky="w", padx=10, pady=5
        )
    entry(f_risk, "Lot per leg", "FIXED_LOT", 7, 0)
    entry(f_risk, "Account risk %", "RISK_PERCENT_PER_PAIR", 7, 2)
    entry(f_risk, "Max lot cap", "MAX_LOT_CAP", 8, 0)
    entry(f_risk, "Max pairs/symbol", "MAX_PAIRS_PER_SYMBOL", 8, 2)
    ctk.CTkLabel(
        f_risk,
        text="Hint: HEDGE SL/TP Rule dùng cùng công thức base SL/TP của sandbox/bot, nhưng toggle/rule/state là riêng của HEDGE.",
        text_color="#F8BBD0",
        font=("Arial", 11, "italic"),
        wraplength=520,
        justify="left",
    ).grid(row=9, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 8))

    def compose_tsl_mode():
        if not checks["USE_TSL"].get():
            return "OFF"
        selected = [label for label, var in tsl_vars.items() if var.get()]
        if "BE_CASH" in selected and "BE" in selected:
            selected.remove("BE")
        return "+".join(selected) if selected else "OFF"

    def set_tsl_mode(mode):
        parts = set(str(mode or "BE+STEP_R+SWING").upper().replace(",", "+").split("+"))
        if "BE_CASH" in parts:
            parts.discard("BE")
        for label, var in tsl_vars.items():
            var.set(label in parts)

    def set_entry_active(key, active=True):
        widget = fields.get(key)
        if not widget:
            return
        label_widget = getattr(widget, "_label_widget", None)
        if active:
            if label_widget:
                label_widget.grid()
                label_widget.configure(text_color="#FFFFFF")
            widget.grid()
            widget.configure(state="normal")
        else:
            if label_widget:
                label_widget.grid_remove()
            widget.grid_remove()

    def refresh_risk_fields(_value=None):
        lot_mode = str(cbo_lot_mode.get() or "FIXED").upper()
        use_tsl = bool(checks["USE_TSL"].get())
        set_entry_active("FIXED_LOT", lot_mode == "FIXED")
        set_entry_active("RISK_PERCENT_PER_PAIR", lot_mode == "ACCOUNT_RISK")

    cbo_lot_mode.configure(command=refresh_risk_fields)
    checks["USE_TSL"].trace_add("write", lambda *_: refresh_risk_fields())

    zone(f_safety, "Runtime / cooldown", 1)
    entry(f_safety, "Log cooldown sec", "HEDGE_LOG_COOLDOWN_SECONDS", 2, 0, width=72)
    entry(f_safety, "Close cooldown sec", "COOLDOWN_AFTER_CLOSE_SECONDS", 2, 2, width=72)
    entry(f_safety, "Loss cooldown sec", "COOLDOWN_AFTER_LOSS_SECONDS", 2, 4, width=72)
    zone(f_safety, "Daily loss brake", 3, "#FFB300")
    entry(f_safety, "Consecutive losses", "MAX_CONSECUTIVE_LOSSES", 4, 0, width=72)
    entry(f_safety, "Global cooldown sec", "GLOBAL_COOLDOWN_SECONDS", 4, 2, width=72)
    entry(f_safety, "Daily loss HEDGE", "HEDGE_MAX_DAILY_LOSS", 4, 4, width=72)
    entry(f_safety, "Max sessions/day", "MAX_SESSIONS_PER_DAY", 4, 6, width=72)
    zone(f_safety, "Session brake", 5, "#FFB300")
    entry(f_safety, "Session TP USD", "HEDGE_SESSION_TP_USD", 6, 0, width=72)
    entry(f_safety, "Session SL USD", "HEDGE_SESSION_SL_USD", 6, 2, width=72)
    entry(f_safety, "Max hold min", "HEDGE_MAX_HOLD_MINUTES", 6, 4, width=72)
    zone(f_safety, "Execution checks", 7)
    checks["CHECK_SPREAD"] = ctk.BooleanVar(value=True)
    checks["CHECK_PING"] = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(f_safety, text="Check spread", variable=checks["CHECK_SPREAD"]).grid(row=8, column=0, columnspan=2, sticky="w", padx=10, pady=5)
    ctk.CTkCheckBox(f_safety, text="Check ping", variable=checks["CHECK_PING"]).grid(row=8, column=2, columnspan=2, sticky="w", padx=10, pady=5)
    entry(f_safety, "Max spread points", "MAX_SPREAD_POINTS", 8, 4, width=72)
    entry(f_safety, "Max ping ms", "MAX_PING_MS", 8, 6, width=72)
    ctk.CTkLabel(
        f_safety,
        text="Safety/cooldown override chỉ áp dụng cho symbol đang chọn, không reset BOT/GRID.",
        text_color="#B0BEC5",
        font=("Arial", 11, "italic"),
        wraplength=520,
        justify="left",
    ).grid(row=9, column=0, columnspan=8, sticky="w", padx=10, pady=(4, 8))

    status_label = ctk.CTkLabel(edit_header, text="", text_color="#F8BBD0", font=("Arial", 12, "italic"), wraplength=520, justify="left")
    status_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def refresh_symbol_list():
        for child in list_frame.winfo_children():
            child.destroy()
        ctk.CTkLabel(list_frame, text="Symbols", font=("Roboto", 12, "bold"), text_color="#CE93D8").pack(anchor="w", padx=8, pady=(8, 4))
        for sym in _symbols():
            active = sym == selected.get()
            has = _has_override(sym)
            label = f"{sym} *" if has else sym
            ctk.CTkButton(
                list_frame,
                text=label,
                height=30,
                fg_color=COL_WARN if has else ("#1f538d" if active else "#424242"),
                hover_color="#FFB300" if has else "#616161",
                text_color="#212121" if has else "#FFFFFF",
                command=lambda s=sym: load_symbol(s),
            ).pack(fill="x", padx=6, pady=4)

    def load_symbol(sym):
        selected.set(sym)
        cfg = _effective_cfg(sym)
        lbl_title.configure(text=f"HEDGE override: {sym} {'*' if _has_override(sym) else ''}")
        for key, var in checks.items():
            if key == "USE_HEDGE_SLTP":
                var.set(bool(cfg.get("USE_HEDGE_SLTP", cfg.get("USE_SANDBOX_SLTP", True))))
            else:
                var.set(bool(cfg.get(key, False if key in {"USE_SIGNAL_FILTER", "USE_ENTRY_EXIT_FILTER"} else True)))
        cbo_signal_rule.set(str(cfg.get("HEDGE_SIGNAL_RULE", "SANDBOX_SIGNAL")).upper())
        cbo_entry_rule.set(str(cfg.get("HEDGE_ENTRY_RULE", "SWING_REJECTION")).upper())
        cbo_ee_sl_rule.set(str(cfg.get("HEDGE_EE_SL_RULE", "MATCH_ENTRY")).upper().replace("AUTO", "MATCH_ENTRY"))
        cbo_ee_tp_rule.set(str(cfg.get("HEDGE_EE_TP_RULE", "MATCH_ENTRY")).upper().replace("AUTO", "MATCH_ENTRY"))
        cbo_sl_rule.set(str(cfg.get("HEDGE_SL_RULE", "BASE_SL_ATR")).upper())
        cbo_tp_rule.set(str(cfg.get("HEDGE_TP_RULE", "RR")).upper())
        lot_mode_value = str(cfg.get("LOT_MODE", "FIXED")).upper()
        cbo_lot_mode.set("ACCOUNT_RISK" if lot_mode_value == "RISK_PERCENT" else lot_mode_value)
        set_tsl_mode(cfg.get("HEDGE_TSL_MODE", "BE+STEP_R+SWING"))
        cbo_survivor.set(str(cfg.get("SURVIVOR_PROTECT", "BE_FEE")).upper())
        for key in fields:
            set_entry(key, cfg.get(key, ""))
        refresh_risk_fields()
        status_label.configure(
            text="Đang dùng override riêng cho symbol này." if _has_override(sym)
            else "Chưa có override, đang hiển thị cấu hình HEDGE mặc định để làm mẫu."
        )
        refresh_symbol_list()

    def values_from_form():
        return {
            "USE_SIGNAL_FILTER": checks["USE_SIGNAL_FILTER"].get(),
            "HEDGE_SIGNAL_RULE": cbo_signal_rule.get(),
            "USE_ENTRY_EXIT_FILTER": checks["USE_ENTRY_EXIT_FILTER"].get(),
            "HEDGE_ENTRY_RULE": cbo_entry_rule.get(),
            "HEDGE_EE_SL_RULE": cbo_ee_sl_rule.get(),
            "HEDGE_EE_TP_RULE": cbo_ee_tp_rule.get(),
            "USE_HEDGE_SLTP": checks["USE_HEDGE_SLTP"].get(),
            "HEDGE_SL_RULE": cbo_sl_rule.get(),
            "HEDGE_TP_RULE": cbo_tp_rule.get(),
            "USE_TSL": checks["USE_TSL"].get(),
            "HEDGE_TSL_MODE": compose_tsl_mode(),
            "SURVIVOR_PROTECT": cbo_survivor.get(),
            "LOT_MODE": cbo_lot_mode.get(),
            "FIXED_LOT": float(fields["FIXED_LOT"].get() or 0.1),
            "RISK_PERCENT_PER_PAIR": float(fields["RISK_PERCENT_PER_PAIR"].get() or 0.0),
            "MAX_LOT_CAP": float(fields["MAX_LOT_CAP"].get() or 0.0),
            "MAX_PAIRS_PER_SYMBOL": int(float(fields["MAX_PAIRS_PER_SYMBOL"].get() or 1)),
            "COOLDOWN_AFTER_CLOSE_SECONDS": int(float(fields["COOLDOWN_AFTER_CLOSE_SECONDS"].get() or 0)),
            "COOLDOWN_AFTER_LOSS_SECONDS": int(float(fields["COOLDOWN_AFTER_LOSS_SECONDS"].get() or 0)),
            "MAX_CONSECUTIVE_LOSSES": int(float(fields["MAX_CONSECUTIVE_LOSSES"].get() or 0)),
            "GLOBAL_COOLDOWN_SECONDS": int(float(fields["GLOBAL_COOLDOWN_SECONDS"].get() or 0)),
            "HEDGE_LOG_COOLDOWN_SECONDS": max(0, int(float(fields["HEDGE_LOG_COOLDOWN_SECONDS"].get() or 300))),
            "CHECK_SPREAD": checks["CHECK_SPREAD"].get(),
            "MAX_SPREAD_POINTS": int(float(fields["MAX_SPREAD_POINTS"].get() or 150)),
            "CHECK_PING": checks["CHECK_PING"].get(),
            "MAX_PING_MS": int(float(fields["MAX_PING_MS"].get() or 150)),
            "HEDGE_MAX_DAILY_LOSS": float(fields["HEDGE_MAX_DAILY_LOSS"].get() or 0.0),
            "MAX_SESSIONS_PER_DAY": int(float(fields["MAX_SESSIONS_PER_DAY"].get() or 0)),
            "HEDGE_SESSION_TP_USD": float(fields["HEDGE_SESSION_TP_USD"].get() or 0.0),
            "HEDGE_SESSION_SL_USD": float(fields["HEDGE_SESSION_SL_USD"].get() or 0.0),
            "HEDGE_MAX_HOLD_MINUTES": int(float(fields["HEDGE_MAX_HOLD_MINUTES"].get() or 0)),
        }

    def save_override():
        try:
            cfg = _base_cfg()
            sym = selected.get()
            cfg.setdefault("SYMBOL_OVERRIDES", {})[sym] = values_from_form()
            for old_key in (
                "TACTIC", "USE_SWING_FILTER", "SWING_GROUP", "SWING_TIMEFRAME", "SWING_TOLERANCE_ATR",
                "USE_SANDBOX_SLTP", "SL_TP_MODE", "SL_ATR_BUFFER", "TP_ATR_BUFFER", "BASKET_EXIT_MODE", "PAIR_TP_USD",
                "PAIR_SL_USD", "BASKET_TP_R", "BASKET_SL_R", "BASKET_BUFFER_R",
                "BASKET_TRAIL_START_R", "BASKET_TRAIL_GIVEBACK_R", "LOSING_LEG_SL_USD",
                "RECOVERY_MODE", "RECOVERY_TARGET_USD", "RECOVERY_BUFFER_R", "RECOVERY_GIVEBACK_USD",
                "RECOVERY_FAIL_GUARD", "RECOVERY_FAIL_PULLBACK_USD", "RECOVERY_TSL_MODE",
                "RECOVERY_TSL_ENABLED", "RECOVERY_TSL_START_R", "RECOVERY_TSL_GIVEBACK_R",
                "NO_MOVE_TIMEOUT_SECONDS", "NO_MOVE_MIN_MFE_USD", "MAX_HOLD_SECONDS",
            ):
                cfg["SYMBOL_OVERRIDES"][sym].pop(old_key, None)
            save_hedge_settings(cfg)
            if hasattr(app, "log_message"):
                app.log_message(f"[HEDGE] Override saved for {sym}.", target="hedge")
            load_symbol(sym)
            if on_close:
                on_close()
        except ValueError:
            messagebox.showerror("HEDGE", "HEDGE override nhập sai kiểu số.", parent=top)

    def reset_override():
        cfg = _base_cfg()
        sym = selected.get()
        cfg.setdefault("SYMBOL_OVERRIDES", {}).pop(sym, None)
        save_hedge_settings(cfg)
        if hasattr(app, "log_message"):
            app.log_message(f"[HEDGE] Override reset for {sym}.", target="hedge")
        load_symbol(sym)
        if on_close:
            on_close()

    btn_save_override.configure(command=save_override, state="normal")
    btn_reset_override.configure(command=reset_override, state="normal")

    load_symbol(symbol)

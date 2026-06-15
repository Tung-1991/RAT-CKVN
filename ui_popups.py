# -*- coding: utf-8 -*-

# FILE: ui_popups.py

# V3.8: SUPREME FINAL - TRANSIENT LOCK & TACTIC PREVIEW (KAISER EDITION)


import customtkinter as ctk

import tkinter as tk

from tkinter import ttk, messagebox

import config
import csv
import os
import json


def _bring_popup_to_front(window, delay_ms=150):
    try:
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()
        window.after(delay_ms, lambda: (window.lift(), window.focus_force(), window.attributes("-topmost", True)))
    except Exception:
        pass
    return window


def _speed_up_scroll(frame, factor=5):
    canvas = getattr(frame, "_parent_canvas", None)
    if canvas is None:
        return frame

    def on_mousewheel(event):
        step = int(-1 * (event.delta / 120) * factor) if getattr(event, "delta", 0) else 0
        if step:
            canvas.yview_scroll(step, "units")
        return "break"

    def on_button4(_event):
        canvas.yview_scroll(-factor, "units")
        return "break"

    def on_button5(_event):
        canvas.yview_scroll(factor, "units")
        return "break"

    def activate(_event):
        frame.bind_all("<MouseWheel>", on_mousewheel)
        frame.bind_all("<Button-4>", on_button4)
        frame.bind_all("<Button-5>", on_button5)

    def deactivate(_event):
        frame.unbind_all("<MouseWheel>")
        frame.unbind_all("<Button-4>")
        frame.unbind_all("<Button-5>")

    frame.bind("<Enter>", activate, add="+")
    frame.bind("<Leave>", deactivate, add="+")
    return frame


def open_advisor_popup(app):
    top = ctk.CTkToplevel(app)
    top.title("AI Advisor")
    top.geometry("660x760")
    top.minsize(600, 640)
    _bring_popup_to_front(top)

    root = ctk.CTkFrame(top, fg_color="#1E1E1E", corner_radius=0)
    root.pack(fill="both", expand=True, padx=10, pady=10)

    ctk.CTkLabel(root, text="AI ADVISOR", font=("Roboto", 18, "bold"), text_color="#80DEEA").pack(anchor="w", padx=10, pady=(8, 4))

    tabs = ctk.CTkTabview(root)
    tabs.pack(fill="both", expand=True, padx=6, pady=(2, 6))
    tab_run = tabs.add("Run")
    tab_edit = tabs.add("Edit")
    tab_telegram = tabs.add("Telegram")
    edit_body = _speed_up_scroll(ctk.CTkScrollableFrame(tab_edit, fg_color="transparent"))
    edit_body.pack(fill="both", expand=True, padx=0, pady=0)

    status_row = ctk.CTkFrame(tab_run, fg_color="#252526", corner_radius=6)
    status_row.pack(fill="x", padx=10, pady=(2, 8))
    ctk.CTkLabel(status_row, text="Status", font=("Roboto", 12, "bold"), text_color="gray").pack(side="left", padx=10, pady=8)
    app.lbl_advisor_status = ctk.CTkLabel(
        status_row,
        text=getattr(app, "advisor_last_export_status", "Never"),
        font=("Roboto", 12, "bold"),
        text_color="#00C853" if "OK" in getattr(app, "advisor_last_export_status", "") else "gray",
        anchor="e",
    )
    app.lbl_advisor_status.pack(side="right", fill="x", expand=True, padx=10, pady=8)

    settings = ctk.CTkFrame(tab_run, fg_color="transparent")
    settings.pack(fill="x", padx=10, pady=4)
    settings.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(settings, text="Số ngày export", font=("Roboto", 12, "bold"), text_color="#D7DCE2").grid(row=0, column=0, sticky="w", pady=6)
    ctk.CTkOptionMenu(settings, values=["1", "3", "7", "14", "30"], variable=app.var_advisor_export_days, width=110, height=28).grid(row=0, column=1, sticky="e", pady=6)

    ctk.CTkLabel(settings, text="Chế độ", font=("Roboto", 12, "bold"), text_color="#D7DCE2").grid(row=1, column=0, sticky="w", pady=6)
    ctk.CTkOptionMenu(settings, values=["Manual Only", "API Trigger"], variable=app.var_advisor_mode, width=160, height=28).grid(row=1, column=1, sticky="e", pady=6)

    ctk.CTkLabel(settings, text="Giờ cố định", font=("Roboto", 12, "bold"), text_color="#D7DCE2").grid(row=2, column=0, sticky="w", pady=6)
    ctk.CTkEntry(settings, textvariable=app.var_advisor_fixed_time, width=110, height=28, placeholder_text="HH:MM").grid(row=2, column=1, sticky="e", pady=6)

    ctk.CTkCheckBox(
        settings,
        text="Cảnh báo khi bot bị global cooldown",
        variable=app.var_advisor_global_emergency,
        font=("Roboto", 12, "bold"),
        checkbox_width=18,
        checkbox_height=18,
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

    ctk.CTkCheckBox(
        settings,
        text="Gửi kèm advisor_response.md khi gọi API",
        variable=app.var_advisor_send_response_file,
        font=("Roboto", 12, "bold"),
        checkbox_width=18,
        checkbox_height=18,
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 4))

    api_hint = ctk.CTkFrame(tab_run, fg_color="#252526", corner_radius=6)
    api_hint.pack(fill="x", padx=10, pady=(8, 2))
    ctk.CTkLabel(
        api_hint,
        text="API key chỉ đọc từ PowerShell hiện tại, không lưu xuống file.",
        font=("Roboto", 10, "bold"),
        text_color="#FBC02D",
    ).pack(anchor="w", padx=10, pady=(7, 2))
    api_cmd_row = ctk.CTkFrame(api_hint, fg_color="transparent")
    api_cmd_row.pack(fill="x", padx=10, pady=(0, 8))
    api_cmd = '$env:OPENAI_API_KEY="TOKEN"'
    ctk.CTkLabel(
        api_cmd_row,
        text=api_cmd,
        font=("Consolas", 11, "bold"),
        text_color="#D7DCE2",
        anchor="w",
    ).pack(side="left", fill="x", expand=True)

    def copy_api_cmd():
        try:
            top.clipboard_clear()
            top.clipboard_append(api_cmd)
            top.update()
            if hasattr(app, "_set_advisor_status"):
                app._set_advisor_status("API env command copied")
        except Exception:
            pass

    ctk.CTkButton(
        api_cmd_row,
        text="Copy",
        width=70,
        height=26,
        fg_color="#424242",
        hover_color="#616161",
        command=copy_api_cmd,
    ).pack(side="right", padx=(8, 0))

    buttons = ctk.CTkFrame(tab_run, fg_color="transparent")
    buttons.pack(fill="x", padx=10, pady=(10, 8))
    ctk.CTkButton(buttons, text="Generate Advisor Package", height=34, fg_color="#00695C", hover_color="#004D40", command=app.generate_advisor_package_ui).pack(side="left", fill="x", expand=True, padx=(0, 5))
    ctk.CTkButton(buttons, text="Open Folder", width=105, height=34, fg_color="#424242", hover_color="#616161", command=app.open_advisor_folder).pack(side="left", padx=5)
    ctk.CTkButton(buttons, text="Send API", width=100, height=34, fg_color="#1f538d", hover_color="#14375e", command=app.send_advisor_api_now).pack(side="left", padx=(5, 0))

    from ai_advisor import api_client
    from ai_advisor.exporter import ensure_advisor_flow, ensure_advisor_response_template, ensure_user_context

    api_client.ensure_advisor_prompt()
    ensure_advisor_flow()
    ensure_user_context()
    ensure_advisor_response_template()
    if not os.path.exists(api_client.paths.advisor_api_settings_path()):
        api_client.save_api_settings(api_client.DEFAULT_API_SETTINGS)
    api_settings = api_client.load_api_settings()

    from telegram_notify import reporter as telegram_reporter
    from telegram_notify import settings as telegram_settings
    from telegram_notify.control import CONTROL_HELP_TEXT

    tg_settings = telegram_settings.load_settings()
    var_tg_enabled = tk.BooleanVar(value=bool(tg_settings.get("enabled")))
    var_tg_control_enabled = tk.BooleanVar(value=bool(tg_settings.get("control_enabled")))
    var_tg_signal_enabled = tk.BooleanVar(value=bool(tg_settings.get("signal_proposals_enabled")))
    var_tg_env = tk.StringVar(value=str(tg_settings.get("bot_token_env", "TELE_BOT_KEY")))
    var_tg_report_chat = tk.StringVar(value=str(tg_settings.get("report_chat_id", "1003772881044")))
    var_tg_control_chat = tk.StringVar(value=str(tg_settings.get("control_chat_id", "1003941549878")))
    var_tg_owner_id = tk.StringVar(value=str(tg_settings.get("owner_user_id", "")))
    var_tg_operator_ids = tk.StringVar(value=str(tg_settings.get("operator_user_ids", "")))
    var_tg_poll_interval = tk.StringVar(value=str(tg_settings.get("control_poll_interval_seconds", 2.0)))
    var_tg_signal_cooldown = tk.StringVar(value=str(tg_settings.get("signal_proposal_cooldown_minutes", 15.0)))
    var_tg_chunk = tk.StringVar(value=str(tg_settings.get("chunk_size", 3500)))
    var_tg_env_cmd = tk.StringVar()

    def refresh_telegram_env_cmd(*_args):
        env_name = (var_tg_env.get() or "TELE_BOT_KEY").strip() or "TELE_BOT_KEY"
        var_tg_env_cmd.set(
            f'$env:{env_name}="key"; '
            f'[Environment]::SetEnvironmentVariable("{env_name}", $env:{env_name}, "User")'
        )

    var_tg_env.trace_add("write", refresh_telegram_env_cmd)
    refresh_telegram_env_cmd()

    tg_body = _speed_up_scroll(ctk.CTkScrollableFrame(tab_telegram, fg_color="transparent"), factor=12)
    tg_body.pack(fill="both", expand=True, padx=10, pady=10)
    tg_body.grid_columnconfigure((0, 1), weight=1, uniform="telegram_cols")

    tg_status = ctk.CTkFrame(tg_body, fg_color="#252526", corner_radius=6)
    tg_status.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    ctk.CTkLabel(
        tg_status,
        text="Telegram",
        font=("Roboto", 12, "bold"),
        text_color="#80DEEA",
    ).pack(anchor="w", padx=10, pady=(8, 2))
    ctk.CTkLabel(
        tg_status,
        text="Token doc tu ENV, khong luu file. Set ENV xong can restart app.",
        font=("Roboto", 11, "bold"),
        text_color="#FBC02D",
        anchor="w",
    ).pack(anchor="w", padx=10, pady=(0, 6))

    tg_env_row = ctk.CTkFrame(tg_status, fg_color="transparent")
    tg_env_row.pack(fill="x", padx=10, pady=(0, 10))
    ctk.CTkEntry(
        tg_env_row,
        textvariable=var_tg_env_cmd,
        height=28,
        font=("Consolas", 11, "bold"),
    ).pack(side="left", fill="x", expand=True)

    tg_settings_col = ctk.CTkFrame(tg_body, fg_color="#252526", corner_radius=6)
    tg_settings_col.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=(0, 10))
    tg_settings_col.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(
        tg_settings_col,
        text="Telegram Settings",
        font=("Roboto", 12, "bold"),
        text_color="#80DEEA",
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 6))

    tg_rules_col = ctk.CTkFrame(tg_body, fg_color="#252526", corner_radius=6)
    tg_rules_col.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=(0, 10))
    tg_rules_col.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(
        tg_rules_col,
        text="Rules / Cooldown",
        font=("Roboto", 12, "bold"),
        text_color="#80DEEA",
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 6))

    def _tg_row(parent, label, variable, row):
        ctk.CTkLabel(parent, text=label, font=("Roboto", 11, "bold"), text_color="#D7DCE2").grid(
            row=row, column=0, sticky="w", padx=(10, 0), pady=5
        )
        ctk.CTkEntry(parent, textvariable=variable, height=28).grid(
            row=row, column=1, sticky="ew", padx=10, pady=5
        )

    def _tg_check(parent, label, variable, row):
        ctk.CTkCheckBox(
            parent,
            text=label,
            variable=variable,
            font=("Roboto", 12, "bold"),
            checkbox_width=18,
            checkbox_height=18,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=6)

    _tg_row(tg_settings_col, "Token ENV", var_tg_env, 1)
    _tg_row(tg_settings_col, "RAT-report chat ID", var_tg_report_chat, 2)
    _tg_row(tg_settings_col, "RAT-control chat ID", var_tg_control_chat, 3)
    _tg_row(tg_settings_col, "Owner user ID", var_tg_owner_id, 4)
    _tg_row(tg_settings_col, "Chunk report", var_tg_chunk, 5)

    _tg_check(tg_rules_col, "Gui AI report", var_tg_enabled, 1)
    _tg_check(tg_rules_col, "Nghe RAT-control", var_tg_control_enabled, 2)
    _tg_check(tg_rules_col, "Ban signal khi bot OFF", var_tg_signal_enabled, 3)
    _tg_row(tg_rules_col, "Poll giay", var_tg_poll_interval, 4)
    _tg_row(tg_rules_col, "Cooldown signal phut", var_tg_signal_cooldown, 5)

    tg_buttons = ctk.CTkFrame(tg_body, fg_color="transparent")
    tg_buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0))
    tg_buttons.grid_columnconfigure((0, 1), weight=1)

    def save_telegram_settings():
        try:
            saved = telegram_settings.save_settings(
                {
                    "enabled": var_tg_enabled.get(),
                    "control_enabled": var_tg_control_enabled.get(),
                    "signal_proposals_enabled": var_tg_signal_enabled.get(),
                    "bot_token_env": var_tg_env.get(),
                    "report_chat_id": var_tg_report_chat.get(),
                    "control_chat_id": var_tg_control_chat.get(),
                    "owner_user_id": var_tg_owner_id.get(),
                    "operator_user_ids": "",
                    "control_poll_interval_seconds": var_tg_poll_interval.get(),
                    "signal_proposal_cooldown_minutes": var_tg_signal_cooldown.get(),
                    "chunk_size": var_tg_chunk.get(),
                }
            )
            var_tg_enabled.set(bool(saved.get("enabled")))
            var_tg_control_enabled.set(bool(saved.get("control_enabled")))
            var_tg_signal_enabled.set(bool(saved.get("signal_proposals_enabled")))
            var_tg_env.set(str(saved.get("bot_token_env", "TELE_BOT_KEY")))
            var_tg_report_chat.set(str(saved.get("report_chat_id", "")))
            var_tg_control_chat.set(str(saved.get("control_chat_id", "")))
            var_tg_owner_id.set(str(saved.get("owner_user_id", "")))
            var_tg_operator_ids.set("")
            var_tg_poll_interval.set(str(saved.get("control_poll_interval_seconds", 2.0)))
            var_tg_signal_cooldown.set(str(saved.get("signal_proposal_cooldown_minutes", 15.0)))
            var_tg_chunk.set(str(saved.get("chunk_size", 3500)))
            refresh_telegram_env_cmd()
            app._set_advisor_status("Telegram settings saved")
            return saved
        except Exception as exc:
            app._set_advisor_status("Telegram settings ERR", str(exc))
            return None

    def copy_telegram_env():
        try:
            top.clipboard_clear()
            top.clipboard_append(var_tg_env_cmd.get())
            top.update()
            app._set_advisor_status("Telegram env command copied")
        except Exception:
            pass

    def open_telegram_report_sender():
        saved = save_telegram_settings()
        if not saved:
            return

        sender = ctk.CTkToplevel(top)
        sender.title("RAT-report Sender")
        sender.geometry("820x620")
        sender.minsize(640, 460)
        _bring_popup_to_front(sender)

        body = ctk.CTkFrame(sender, fg_color="#1E1E1E", corner_radius=0)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            body,
            text="SEND TO RAT-REPORT",
            font=("Roboto", 16, "bold"),
            text_color="#80DEEA",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            body,
            text="Paste -> Send. Noi dung dai tu chia chunk.",
            font=("Roboto", 11, "bold"),
            text_color="gray",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        txt_report = ctk.CTkTextbox(body, font=("Consolas", 12))
        txt_report.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        txt_report.focus_set()

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        actions.grid_columnconfigure((0, 1), weight=1)

        def send_report():
            text = txt_report.get("1.0", "end").strip()
            if not text:
                app._set_advisor_status("Telegram report empty")
                return
            diag = telegram_reporter.report_diagnostics()
            app.log_message(
                "[TELEGRAM] Report diagnostics: "
                f"settings={diag.get('settings_path')} "
                f"env={diag.get('token_env')} "
                f"token_present={diag.get('token_present')} "
                f"token_len={diag.get('token_length')} "
                f"insecure_ssl={diag.get('insecure_ssl')} "
                f"chat={diag.get('report_chat_id')}",
                target="manual",
            )
            result = telegram_reporter.send_text_report(
                text,
                title="RAT6 Advisor Report",
                require_enabled=False,
            )
            if result.get("ok"):
                app._set_advisor_status("Telegram report sent")
                app.log_message(
                    f"[TELEGRAM] Report sent ({result.get('sent', 0)} parts).",
                    target="manual",
                )
            else:
                err = result.get("error", "Telegram report failed")
                result_diag = result.get("diagnostics") or diag
                detail = (
                    f"{err}\n\n"
                    f"Settings: {result_diag.get('settings_path')}\n"
                    f"ENV: {result_diag.get('token_env')} "
                    f"(present={result_diag.get('token_present')}, len={result_diag.get('token_length')})\n"
                    f"Insecure SSL: {result_diag.get('insecure_ssl')}\n"
                    f"Chat ID: {result_diag.get('report_chat_id')}"
                )
                app._set_advisor_status("Telegram report ERR", err)
                app.log_message(f"[TELEGRAM] Report failed: {detail}", error=True, target="manual")
                messagebox.showerror("Telegram report", detail, parent=sender)

        def clear_report():
            txt_report.delete("1.0", "end")
            app._set_advisor_status("Telegram report cleared")

        ctk.CTkButton(
            actions,
            text="Send RAT-report",
            height=34,
            fg_color="#1f538d",
            hover_color="#14375e",
            command=send_report,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(
            actions,
            text="Xoa",
            height=34,
            fg_color="#424242",
            hover_color="#616161",
            command=clear_report,
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def open_telegram_help():
        helper = ctk.CTkToplevel(top)
        helper.title("RAT-control Help")
        helper.geometry("760x560")
        helper.minsize(620, 460)
        _bring_popup_to_front(helper)

        body = ctk.CTkFrame(helper, fg_color="#1E1E1E", corner_radius=0)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            body,
            text="RAT-CONTROL HELP",
            font=("Roboto", 16, "bold"),
            text_color="#80DEEA",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            body,
            text="Sample lenh. Owner approve bang button.",
            font=("Roboto", 11, "bold"),
            text_color="#FBC02D",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        txt_help = ctk.CTkTextbox(body, font=("Consolas", 12), wrap="word")
        txt_help.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        txt_help.insert("1.0", CONTROL_HELP_TEXT)
        txt_help.configure(state="disabled")

        def copy_help():
            try:
                helper.clipboard_clear()
                helper.clipboard_append(CONTROL_HELP_TEXT)
                helper.update()
                app._set_advisor_status("Telegram help copied")
            except Exception:
                pass

        ctk.CTkButton(
            body,
            text="Copy",
            height=34,
            fg_color="#424242",
            hover_color="#616161",
            command=copy_help,
        ).grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

    ctk.CTkButton(
        tg_env_row,
        text="Copy ENV",
        width=120,
        height=28,
        fg_color="#424242",
        hover_color="#616161",
        command=copy_telegram_env,
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        tg_env_row,
        text="Help",
        width=130,
        height=28,
        fg_color="#1f538d",
        hover_color="#14375e",
        command=open_telegram_help,
    ).pack(side="right", padx=(8, 0))

    ctk.CTkButton(
        tg_buttons,
        text="Luu Telegram",
        height=30,
        fg_color="#00695C",
        hover_color="#004D40",
        command=save_telegram_settings,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
    ctk.CTkButton(
        tg_buttons,
        text="Gui report tay",
        height=30,
        fg_color="#1f538d",
        hover_color="#14375e",
        command=open_telegram_report_sender,
    ).grid(row=0, column=1, sticky="ew", padx=5)

    files_box = ctk.CTkFrame(edit_body, fg_color="#252526", corner_radius=6)
    files_box.pack(fill="x", padx=10, pady=(10, 8))
    ctk.CTkLabel(
        files_box,
        text="Editable package files",
        font=("Roboto", 12, "bold"),
        text_color="#80DEEA",
    ).pack(anchor="w", padx=10, pady=(8, 2))
    ctk.CTkLabel(
        files_box,
        text="Only these four files are hand-editable. technical_settings.json and advisor_export.xlsx are generated.",
        font=("Roboto", 10, "bold"),
        text_color="gray",
    ).pack(anchor="w", padx=10, pady=(0, 8))
    file_buttons = ctk.CTkFrame(files_box, fg_color="transparent")
    file_buttons.pack(fill="x", padx=10, pady=(0, 10))
    for idx in range(4):
        file_buttons.grid_columnconfigure(idx, weight=1)

    ctk.CTkButton(
        file_buttons,
        text="Edit Prompt",
        height=30,
        fg_color="#424242",
        hover_color="#616161",
        command=lambda: open_advisor_file_editor(app, api_client.paths.advisor_prompt_path(), "advisor_prompt.md"),
    ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
    ctk.CTkButton(
        file_buttons,
        text="Edit Flow",
        height=30,
        fg_color="#424242",
        hover_color="#616161",
        command=lambda: open_advisor_file_editor(app, api_client.paths.advisor_flow_path(), "advisor_flow.md"),
    ).grid(row=0, column=1, sticky="ew", padx=4)
    ctk.CTkButton(
        file_buttons,
        text="Edit User Context",
        height=30,
        fg_color="#424242",
        hover_color="#616161",
        command=lambda: open_advisor_file_editor(app, api_client.paths.user_context_path(), "user_context.md"),
    ).grid(row=0, column=2, sticky="ew", padx=4)
    ctk.CTkButton(
        file_buttons,
        text="Edit Response",
        height=30,
        fg_color="#424242",
        hover_color="#616161",
        command=lambda: open_advisor_file_editor(app, api_client.paths.advisor_response_path(), "advisor_response.md"),
    ).grid(row=0, column=3, sticky="ew", padx=(4, 0))

    edit_top = ctk.CTkFrame(edit_body, fg_color="#252526", corner_radius=6)
    edit_top.pack(fill="x", padx=10, pady=(0, 8))
    edit_top.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(
        edit_top,
        text="API Limits",
        font=("Roboto", 12, "bold"),
        text_color="#80DEEA",
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 2))
    ctk.CTkLabel(
        edit_top,
        text="Internal send limits. This JSON is not part of the manual web-upload package.",
        font=("Roboto", 10, "bold"),
        text_color="gray",
    ).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 6))

    var_model = tk.StringVar(value=str(api_settings.get("model", api_client.DEFAULT_MODEL)))
    var_prompt_limit = tk.StringVar(value=str(api_settings.get("advisor_prompt_limit", 200000)))
    var_flow_limit = tk.StringVar(value=str(api_settings.get("advisor_flow_limit", 200000)))
    var_context_limit = tk.StringVar(value=str(api_settings.get("user_context_limit", 100000)))
    var_tech_limit = tk.StringVar(value=str(api_settings.get("technical_settings_limit", 1000000)))
    var_workbook_rows = tk.StringVar(value=str(api_settings.get("workbook_limit_rows", 80)))
    var_response_limit = tk.StringVar(value=str(api_settings.get("previous_response_limit", 60000)))
    var_max_output = tk.StringVar(value=str(api_settings.get("max_output_tokens", api_client.DEFAULT_MAX_OUTPUT_TOKENS)))
    var_web_search = tk.BooleanVar(value=bool(api_settings.get("web_search_enabled", True)))

    def _edit_row(label, variable, row, values=None):
        ctk.CTkLabel(edit_top, text=label, font=("Roboto", 11, "bold"), text_color="#D7DCE2").grid(row=row, column=0, sticky="w", padx=10, pady=4)
        if values:
            ctk.CTkOptionMenu(edit_top, values=values, variable=variable, width=150, height=28).grid(row=row, column=1, sticky="e", padx=10, pady=4)
        else:
            ctk.CTkEntry(edit_top, textvariable=variable, width=150, height=28).grid(row=row, column=1, sticky="e", padx=10, pady=4)

    _edit_row("model", var_model, 2, values=api_client.SUPPORTED_MODELS)
    _edit_row("technical_settings.json limit (CHAR)", var_tech_limit, 3)
    _edit_row("advisor_export.xlsx rows/sheet", var_workbook_rows, 4)
    _edit_row("max output tokens", var_max_output, 5)

    ctk.CTkCheckBox(
        edit_top,
        text="Enable web search",
        variable=var_web_search,
        font=("Roboto", 11, "bold"),
        checkbox_width=18,
        checkbox_height=18,
    ).grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 4))

    limit_buttons = ctk.CTkFrame(edit_top, fg_color="transparent")
    limit_buttons.grid(row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=(6, 10))

    def save_api_edit():
        try:
            saved = api_client.save_api_settings(
                {
                    "model": var_model.get(),
                    "advisor_prompt_limit": var_prompt_limit.get(),
                    "advisor_flow_limit": var_flow_limit.get(),
                    "user_context_limit": var_context_limit.get(),
                    "technical_settings_limit": var_tech_limit.get(),
                    "workbook_limit_rows": var_workbook_rows.get(),
                    "previous_response_limit": var_response_limit.get(),
                    "max_output_tokens": var_max_output.get(),
                    "web_search_enabled": var_web_search.get(),
                }
            )
            var_model.set(str(saved.get("model", api_client.DEFAULT_MODEL)))
            var_prompt_limit.set(str(saved.get("advisor_prompt_limit")))
            var_flow_limit.set(str(saved.get("advisor_flow_limit")))
            var_context_limit.set(str(saved.get("user_context_limit")))
            var_tech_limit.set(str(saved.get("technical_settings_limit")))
            var_workbook_rows.set(str(saved.get("workbook_limit_rows")))
            var_response_limit.set(str(saved.get("previous_response_limit")))
            var_max_output.set(str(saved.get("max_output_tokens")))
            var_web_search.set(bool(saved.get("web_search_enabled", True)))
            app.preview_advisor_api_payload()
            app._set_advisor_status("API settings saved")
        except Exception as exc:
            app._set_advisor_status("API settings ERR", str(exc))

    ctk.CTkButton(limit_buttons, text="Save Limits", height=30, fg_color="#00695C", hover_color="#004D40", command=save_api_edit).pack(side="left", fill="x", expand=True, padx=(0, 6))
    ctk.CTkButton(limit_buttons, text="Preview Token/Cost", width=160, height=30, fg_color="#1f538d", hover_color="#14375e", command=app.preview_advisor_api_payload).pack(side="right")

    preview_box = ctk.CTkFrame(edit_body, fg_color="#252526", corner_radius=6)
    preview_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    app.lbl_advisor_api_preview = ctk.CTkLabel(
        preview_box,
        text=getattr(app, "advisor_api_preview_text", "API payload: not estimated"),
        font=("Roboto", 12, "bold"),
        text_color="#E3F2FD",
        anchor="w",
        justify="left",
    )
    app.lbl_advisor_api_preview.pack(fill="x", padx=10, pady=(8, 4))
    app.lbl_advisor_api_preview_detail = ctk.CTkLabel(
        preview_box,
        text=getattr(app, "advisor_api_preview_detail_text", ""),
        font=("Consolas", 11, "bold"),
        text_color="#B3E5FC",
        anchor="w",
        justify="left",
        wraplength=560,
    )
    app.lbl_advisor_api_preview_detail.pack(fill="both", expand=True, padx=10, pady=(0, 10))

# --- BẢNG MÀU & FONT CHUẨN ---

def open_advisor_file_editor(app, path, title):
    top = ctk.CTkToplevel(app)
    top.title(f"Edit {title}")
    top.geometry("760x620")
    top.minsize(620, 460)
    _bring_popup_to_front(top)

    root = ctk.CTkFrame(top, fg_color="#1E1E1E", corner_radius=0)
    root.pack(fill="both", expand=True, padx=10, pady=10)
    ctk.CTkLabel(
        root,
        text=title,
        font=("Roboto", 16, "bold"),
        text_color="#80DEEA",
    ).pack(anchor="w", padx=8, pady=(6, 2))
    ctk.CTkLabel(
        root,
        text=path,
        font=("Consolas", 10),
        text_color="gray",
    ).pack(anchor="w", padx=8, pady=(0, 8))

    text = ctk.CTkTextbox(root, font=("Consolas", 12), wrap="word")
    text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text.insert("1.0", f.read())
    except Exception as exc:
        text.insert("1.0", f"# Failed to read file\n\n{exc}")

    footer = ctk.CTkFrame(root, fg_color="transparent")
    footer.pack(fill="x", padx=8, pady=(0, 6))
    status = ctk.CTkLabel(footer, text="", font=("Roboto", 11, "bold"), text_color="gray")
    status.pack(side="left", fill="x", expand=True)

    def reload_file():
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            text.delete("1.0", "end")
            text.insert("1.0", content)
            status.configure(text="Reloaded", text_color="#00C853")
        except Exception as exc:
            status.configure(text=f"Reload failed: {exc}", text_color="#D50000")

    def save_file():
        try:
            content = text.get("1.0", "end-1c")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            status.configure(text="Saved", text_color="#00C853")
            if hasattr(app, "_set_advisor_status"):
                app._set_advisor_status(f"{title} saved")
        except Exception as exc:
            status.configure(text=f"Save failed: {exc}", text_color="#D50000")

    def open_folder():
        try:
            os.startfile(os.path.dirname(path))
        except Exception as exc:
            status.configure(text=f"Open folder failed: {exc}", text_color="#D50000")

    ctk.CTkButton(
        footer,
        text="Open Folder",
        width=115,
        height=32,
        fg_color="#424242",
        hover_color="#616161",
        command=open_folder,
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        footer,
        text="Reload",
        width=90,
        height=32,
        fg_color="#424242",
        hover_color="#616161",
        command=reload_file,
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        footer,
        text="Save",
        width=100,
        height=32,
        fg_color="#00695C",
        hover_color="#004D40",
        command=save_file,
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        footer,
        text="Close",
        width=90,
        height=32,
        fg_color="#424242",
        hover_color="#616161",
        command=top.destroy,
    ).pack(side="right")


def open_advisor_context_editor(app):
    from ai_advisor.exporter import ensure_user_context

    open_advisor_file_editor(app, ensure_user_context(), "user_context.md")


FONT_BOLD = ("Roboto", 13, "bold")

COL_GREEN = "#00C853"

COL_RED = "#D50000"

COL_BLUE_ACCENT = "#1565C0"

COL_GRAY_BTN = "#424242"

COL_WARN = "#FFAB00"

COL_BOT_TAG = "#E040FB"


def _add_popup_hint(parent, text, padx=15, pady=(5, 10), wraplength=900):
    import customtkinter as ctk
    hint_f = ctk.CTkFrame(
        parent,
        fg_color="#332B00",
        corner_radius=6,
        border_width=1,
        border_color="#FFD600",
    )
    hint_f.pack(fill="x", padx=padx, pady=pady)
    ctk.CTkLabel(
        hint_f,
        text=text,
        font=("Arial", 12, "italic"),
        text_color="#FFD600",
        justify="left",
        anchor="w",
        wraplength=wraplength,
    ).pack(fill="x", padx=10, pady=6)
    return hint_f

# ==============================================================================

# 1. POPUP CẤU HÌNH TỪNG CẶP GIAO DỊCH (SYMBOL CONFIG)

# ==============================================================================


def open_symbol_config_popup(app, symbol, on_change=None):
    import json
    import core.storage_manager as storage_manager
    cfg_path = storage_manager.BRAIN_FILE
    existing_data = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except:
            pass
    symbol_configs = existing_data.get("symbol_configs", {})
    sym_cfg = symbol_configs.get(symbol, {})
    has_symbol_override = symbol in symbol_configs and bool(sym_cfg)
    top = ctk.CTkToplevel(app)
    top.title(f"Cấu hình riêng: {symbol}")
    top.geometry("720x720")
    top.minsize(620, 520)
    _bring_popup_to_front(top)
    body = _speed_up_scroll(ctk.CTkScrollableFrame(top, fg_color="transparent"))
    body.pack(fill="both", expand=True, padx=12, pady=(10, 4))
    top.grab_set()  # Khóa (Block) cửa sổ mẹ, bắt buộc người dùng thao tác trên popup này
    ctk.CTkLabel(
        body,
        text=f"THIẾT LẬP SAFEGUARD: {symbol}",
        font=FONT_BOLD,
        text_color="#2196F3",
    ).pack(pady=10)
    ctk.CTkLabel(
        body,
        text="ĐANG GHI ĐÈ SYMBOL"
        if has_symbol_override
        else "ĐANG DÙNG GLOBAL DEFAULT",
        font=("Roboto", 12, "bold"),
        text_color=COL_WARN if has_symbol_override else "#9E9E9E",
    ).pack(pady=(0, 6))
    _add_popup_hint(
        body,
        "- Cấu hình này chỉ áp dụng cho symbol đang chọn.\n"
        "- Max lệnh tối đa là tổng số ENTRY gốc của symbol.\n"
        "- Max lệnh cùng chiều chặn stack quá nhiều BUY hoặc SELL; 0 = tắt, chỉ dùng tổng.\n"
        "- Fixed Lot > 0 sẽ bỏ qua risk %, dùng lot cố định.\n"
        "- Watermark/Basket/Max Lot là hàng rào riêng trước khi bot vào hoặc giữ lệnh.",
        padx=20,
        pady=(0, 5),
        wraplength=620,
    )
    f_grid = ctk.CTkFrame(body, fg_color="transparent")
    f_grid.pack(fill="x", padx=20, pady=10)
    f_grid.grid_columnconfigure(0, weight=1)
    # Max Orders
    ctk.CTkLabel(f_grid, text="Max Lệnh Tối Đa:").grid(
        row=0, column=0, sticky="w", pady=10
    )
    e_max_orders = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_max_orders.insert(0, str(sym_cfg.get("max_orders", 1)))
    e_max_orders.grid(row=0, column=1, sticky="e", pady=10)
    ctk.CTkLabel(f_grid, text="Max Lệnh Cùng Chiều (0=Tắt):").grid(
        row=1, column=0, sticky="w", pady=10
    )
    e_max_same_direction = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_max_same_direction.insert(0, str(sym_cfg.get("max_same_direction_orders", 0)))
    e_max_same_direction.grid(row=1, column=1, sticky="e", pady=10)
    # Max Spread
    ctk.CTkLabel(f_grid, text="Max Spread (points):").grid(
        row=2, column=0, sticky="w", pady=10
    )
    e_max_spread = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_max_spread.insert(0, str(sym_cfg.get("max_spread", 150)))
    e_max_spread.grid(row=2, column=1, sticky="e", pady=10)
    # Max Ping
    ctk.CTkLabel(f_grid, text="Max Ping (ms):").grid(
        row=3, column=0, sticky="w", pady=10
    )
    e_max_ping = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_max_ping.insert(0, str(sym_cfg.get("max_ping", 150)))
    e_max_ping.grid(row=3, column=1, sticky="e", pady=10)

    # [NEW V4.4] Fixed Lot Mode
    ctk.CTkLabel(
        f_grid,
        text="Fixed Lot (0 = Tắt):",
        text_color="#FFB300",
        font=("Roboto", 12, "bold"),
    ).grid(row=4, column=0, sticky="w", pady=10)
    e_fixed_lot = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_fixed_lot.insert(0, str(sym_cfg.get("fixed_lot", 0.0)))
    e_fixed_lot.grid(row=4, column=1, sticky="e", pady=10)

    # [NEW V4.4] Max Lot Cap
    ctk.CTkLabel(
        f_grid,
        text="Max Lot Cap (0=Tắt):",
        text_color="#FFB300",
        font=("Roboto", 12, "bold"),
    ).grid(row=5, column=0, sticky="w", pady=10)
    e_max_lot_cap = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_max_lot_cap.insert(0, str(sym_cfg.get("max_lot_cap", 0.0)))
    e_max_lot_cap.grid(row=5, column=1, sticky="e", pady=10)

    # [NEW V5] Watermark & Options
    ctk.CTkLabel(f_grid, text="Watermark Trigger:", text_color="#00C853").grid(
        row=6, column=0, sticky="w", pady=10
    )
    e_wm_trigger = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_wm_trigger.insert(0, str(sym_cfg.get("watermark_trigger", 0.0)))
    e_wm_trigger.grid(row=6, column=1, sticky="e", pady=10)
    cbo_wm_trigger_unit = ctk.CTkOptionMenu(f_grid, values=["USD", "%Equity"], width=90)
    cbo_wm_trigger_unit.set(sym_cfg.get("watermark_trigger_unit", "USD"))
    cbo_wm_trigger_unit.grid(row=6, column=2, sticky="w", padx=(8, 0), pady=10)
    ctk.CTkLabel(f_grid, text="Watermark Sụt giảm:", text_color="#00C853").grid(
        row=7, column=0, sticky="w", pady=10
    )
    e_wm_drawdown = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_wm_drawdown.insert(0, str(sym_cfg.get("watermark_drawdown", 0.0)))
    e_wm_drawdown.grid(row=7, column=1, sticky="e", pady=10)
    cbo_wm_drawdown_unit = ctk.CTkOptionMenu(
        f_grid, values=["USD", "%Equity"], width=90
    )
    cbo_wm_drawdown_unit.set(sym_cfg.get("watermark_drawdown_unit", "USD"))
    cbo_wm_drawdown_unit.grid(row=7, column=2, sticky="w", padx=(8, 0), pady=10)
    ctk.CTkLabel(f_grid, text="SL Tối thiểu (Points):").grid(
        row=8, column=0, sticky="w", pady=10
    )
    e_min_sl = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_min_sl.insert(0, str(sym_cfg.get("min_sl_points", 0)))
    e_min_sl.grid(row=8, column=1, sticky="e", pady=10)
    ctk.CTkLabel(f_grid, text="Max Basket Drawdown (DCA/PCA):").grid(
        row=9, column=0, sticky="w", pady=10
    )
    e_basket_dd = ctk.CTkEntry(f_grid, width=100, justify="center")
    e_basket_dd.insert(0, str(sym_cfg.get("max_basket_drawdown", 0.0)))
    e_basket_dd.grid(row=9, column=1, sticky="e", pady=10)
    cbo_basket_dd_unit = ctk.CTkOptionMenu(f_grid, values=["USD", "%Equity"], width=90)
    cbo_basket_dd_unit.set(sym_cfg.get("max_basket_drawdown_unit", "USD"))
    cbo_basket_dd_unit.grid(row=9, column=2, sticky="w", padx=(8, 0), pady=10)
    var_reject_lot = ctk.BooleanVar(value=sym_cfg.get("reject_on_max_lot", False))
    ctk.CTkCheckBox(
        f_grid,
        text="Hủy lệnh nếu vượt Max Lot (Tắt = Ép bằng Max Lot)",
        variable=var_reject_lot,
        font=("Roboto", 11),
    ).grid(row=10, column=0, columnspan=2, sticky="w", pady=10)

    def save_sym():
        try:
            mo = int(e_max_orders.get())
            msd = int(e_max_same_direction.get())
            ms = int(e_max_spread.get())
            mp = int(e_max_ping.get())
            if "symbol_configs" not in existing_data:
                existing_data["symbol_configs"] = {}
            existing_data["symbol_configs"][symbol] = {
                "max_orders": mo,
                "max_same_direction_orders": max(0, msd),
                "max_spread": ms,
                "max_ping": mp,
                "fixed_lot": float(e_fixed_lot.get()),
                "max_lot_cap": float(e_max_lot_cap.get()),
                "watermark_trigger": float(e_wm_trigger.get()),
                "watermark_trigger_unit": cbo_wm_trigger_unit.get(),
                "watermark_drawdown": float(e_wm_drawdown.get()),
                "watermark_drawdown_unit": cbo_wm_drawdown_unit.get(),
                "min_sl_points": int(e_min_sl.get()),
                "max_basket_drawdown": float(e_basket_dd.get()),
                "max_basket_drawdown_unit": cbo_basket_dd_unit.get(),
                "reject_on_max_lot": var_reject_lot.get(),
            }
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=4)
            from core.storage_manager import invalidate_settings_cache
            invalidate_settings_cache()
            app.log_message(f"✅ Đã lưu cấu hình riêng cho {symbol}.", target="bot")
            if callable(on_change):
                on_change()
            top.destroy()
        except ValueError:
            messagebox.showerror(
                "Lỗi", "Dữ liệu nhập sai, vui lòng nhập số nguyên!", parent=top
            )

    def reset_sym():
        if (
            "symbol_configs" in existing_data
            and symbol in existing_data["symbol_configs"]
        ):
            existing_data["symbol_configs"].pop(symbol, None)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=4, ensure_ascii=False)
            from core.storage_manager import invalidate_settings_cache
            invalidate_settings_cache()
            app.log_message(
                f"↩ Đã reset cấu hình riêng cho {symbol}; dùng Global default.",
                target="bot",
            )
            if callable(on_change):
                on_change()
        top.destroy()
    f_actions = ctk.CTkFrame(top, fg_color="transparent")
    f_actions.pack(pady=15, fill="x", padx=30)
    ctk.CTkButton(
        f_actions,
        text="LƯU CẤU HÌNH",
        fg_color=COL_GREEN,
        font=FONT_BOLD,
        height=40,
        command=save_sym,
    ).pack(side="left", expand=True, fill="x", padx=(0, 8))
    ctk.CTkButton(
        f_actions,
        text="RESET VỀ GLOBAL",
        fg_color="#5D4037" if has_symbol_override else "#424242",
        hover_color="#795548",
        font=FONT_BOLD,
        height=40,
        state="normal" if has_symbol_override else "disabled",
        command=reset_sym,
    ).pack(side="left", expand=True, fill="x", padx=(8, 0))

# ==============================================================================

# 2. POPUP CẤU HÌNH LÕI (CHỈ CÒN SAFETY & WATCHLIST)

# ==============================================================================


def open_bot_setting_popup(app):

    top = ctk.CTkToplevel(app)
    top.title("Cấu hình Lõi Hệ Thống (Core Settings)")
    top.geometry("1050x720")
    top.minsize(860, 560)
    _bring_popup_to_front(top)
    # top.transient(app) # Khóa Z-index, luôn nổi trên App chính
    tab_core = _speed_up_scroll(ctk.CTkScrollableFrame(top, fg_color="transparent"))
    tab_core.pack(fill="both", expand=True, padx=15, pady=15)
    # Switch Auto Trade
    f_auto = ctk.CTkFrame(tab_core, fg_color="transparent")
    f_auto.pack(fill="x", pady=10)
    ctk.CTkLabel(
        f_auto, text="Tự động bóp cò khi Brain có tín hiệu:", text_color="gray"
    ).pack()
    sw_auto = ctk.CTkSwitch(
        f_auto,
        text="AUTO-TRADING DAEMON",
        variable=app.var_auto_trade,
        font=("Roboto", 14, "bold"),
        progress_color=COL_GREEN,
        fg_color=COL_RED,
        command=app.on_auto_trade_toggle,
    )
    sw_auto.pack(pady=5)
    try:
        from grid.grid_storage import load_grid_settings
        _grid_cfg = load_grid_settings()
    except Exception:
        _grid_cfg = {"ENABLED": False}
    f_adv_lights = ctk.CTkFrame(f_auto, fg_color="transparent")
    f_adv_lights.pack(pady=(6, 0))
    grid_on = bool(_grid_cfg.get("ENABLED", False))
    app.ind_grid_light = ctk.CTkFrame(
        f_adv_lights,
        width=12,
        height=12,
        corner_radius=6,
        fg_color=COL_GREEN if grid_on else COL_RED,
    )
    app.ind_grid_light.pack(side="left", padx=(0, 5))
    ctk.CTkLabel(
        f_adv_lights,
        text="GRID",
        font=("Roboto", 11, "bold"),
        text_color="#00B8D4" if grid_on else "gray",
    ).pack(side="left", padx=(0, 18))
    app.ind_hedge_light = ctk.CTkFrame(
        f_adv_lights,
        width=12,
        height=12,
        corner_radius=6,
        fg_color=COL_RED,
    )
    app.ind_hedge_light.pack(side="left", padx=(0, 5))
    ctk.CTkLabel(
        f_adv_lights,
        text="HEDGE",
        font=("Roboto", 11, "bold"),
        text_color="gray",
    ).pack(side="left")
    ctk.CTkFrame(tab_core, height=2, fg_color="#333").pack(fill="x", padx=30, pady=5)
    # Watchlist (Đã chuyển lên đầu)
    ctk.CTkLabel(
        tab_core,
        text="WATCHLIST - BOT CHỈ QUÉT CÁC COIN SAU:",
        font=FONT_BOLD,
        text_color="#2196F3",
    ).pack(pady=(5, 5))
    _add_popup_hint(
        tab_core,
        "- Watchlist quyết định symbol bot được quét; nút bánh răng là safeguard riêng từng symbol.\n"
        "- AUTO-TRADING bật/tắt bóp cò thật, nhưng preview/context vẫn có thể chạy để quan sát.\n"
        "- Cấu hình Global là mặc định; cấu hình riêng theo symbol sẽ ghi đè.",
        padx=30,
        pady=(0, 10),
    )
    f_coins = ctk.CTkFrame(tab_core, fg_color="transparent")
    f_coins.pack(fill="x", padx=30, pady=(0, 10))
    app.bot_coin_vars = {}
    allowed_list = getattr(config, "BOT_ACTIVE_SYMBOLS", config.COIN_LIST)
    symbol_cfg_buttons = {}

    def _symbol_has_override(symbol_name):
        try:
            import json
            import core.storage_manager as storage_manager
            cfg_path = storage_manager.BRAIN_FILE
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return bool(data.get("symbol_configs", {}).get(symbol_name))
        except Exception:
            pass
        return False

    def refresh_symbol_cfg_buttons():
        for symbol_name, btn in symbol_cfg_buttons.items():
            has_override = _symbol_has_override(symbol_name)
            btn.configure(
                text="⚙*" if has_override else "⚙",
                fg_color=COL_WARN if has_override else "#444",
                hover_color="#FFB300" if has_override else "#666",
                text_color="#212121" if has_override else "#FFFFFF",
            )
    # Tạo layout lưới cho các cặp tiền
    row_idx = 0
    col_idx = 0
    for coin in config.COIN_LIST:
        var = tk.BooleanVar(value=(coin in allowed_list))
        app.bot_coin_vars[coin] = var
        f_single_coin = ctk.CTkFrame(f_coins, fg_color="transparent")
        f_single_coin.grid(row=row_idx, column=col_idx, sticky="w", pady=5, padx=10)
        chk = ctk.CTkCheckBox(
            f_single_coin, text=coin, variable=var, font=("Consolas", 13), width=80
        )
        chk.pack(side="left")
        has_override = _symbol_has_override(coin)
        btn_cfg = ctk.CTkButton(
            f_single_coin,
            text="⚙*" if has_override else "⚙",
            width=25,
            height=20,
            fg_color=COL_WARN if has_override else "#444",
            hover_color="#FFB300" if has_override else "#666",
            text_color="#212121" if has_override else "#FFFFFF",
            command=lambda c=coin: open_symbol_config_popup(
                app, c, on_change=refresh_symbol_cfg_buttons
            ),
        )
        btn_cfg.pack(side="left", padx=(5, 0))
        symbol_cfg_buttons[coin] = btn_cfg
        col_idx += 1
        if col_idx > 1:
            col_idx = 0
            row_idx += 1
    ctk.CTkFrame(tab_core, height=2, fg_color="#333").pack(fill="x", padx=30, pady=5)
    # Safety Guard (Bot ONLY - Độc lập hoàn toàn với Manual)
    ctk.CTkLabel(
        tab_core,
        text="HÀNG RÀO BẢO VỆ BOT (BOT SAFEGUARD)",
        font=FONT_BOLD,
        text_color="#FFB300",
    ).pack(pady=(5, 5))
    _add_popup_hint(
        tab_core,
        "- Global Brake chặn toàn bot khi chạm ngưỡng lỗ/streak/cooldown.\n"
        "- Safeguard bảo vệ lợi nhuận, rổ DCA/PCA, SL tối thiểu và điều kiện TP.\n"
        "- TP R/Swing ở đây là TP bot cũ; Entry/Exit Mode có thể override TP sau này theo tp_policy.\n"
        "- Giá trị 0 thường là tắt giới hạn tương ứng.",
        padx=30,
        pady=(0, 10),
    )

    # --- [NEW] LIVE PREVIEW ---
    from core.storage_manager import load_state, save_state
    import time
    st = load_state()
    start_bal = st.get("starting_balance", 0)
    pnl = st.get("bot_pnl_today", 0.0)
    loss_pct = (pnl / start_bal * 100) if start_bal > 0 else 0
    trades = st.get("bot_trades_today", 0)
    losses = st.get("bot_daily_loss_count", 0)
    cooldown_until = st.get("cooldown_until", 0.0)
    f_preview = ctk.CTkFrame(tab_core, fg_color="#1E1E1E", corner_radius=8)
    f_preview.pack(fill="x", padx=15, pady=(0, 10))
    cooldown_str = "Sẵn sàng"
    now = time.time()
    if now < cooldown_until:
        rem = int((cooldown_until - now) / 60)
        cooldown_str = f"BỊ CHẶN ({rem} phút)"
    pnl_color = COL_GREEN if loss_pct >= 0 else COL_RED
    preview_text = f"PNL Today: {loss_pct:+.2f}% | Lệnh: {trades} | Thua: {losses} | Cooldown: {cooldown_str}"
    ctk.CTkLabel(
        f_preview,
        text="LIVE PREVIEW:",
        font=("Roboto", 12, "bold"),
        text_color="#00E676",
    ).pack(side="left", padx=10, pady=8)
    lbl_preview = ctk.CTkLabel(
        f_preview,
        text=preview_text,
        font=("Consolas", 12, "bold"),
        text_color=pnl_color,
    )
    lbl_preview.pack(side="left", padx=10, pady=8)
    f_iso = ctk.CTkFrame(tab_core, fg_color="#171717", corner_radius=8)
    f_iso.pack(fill="x", padx=15, pady=(0, 10))

    def render_isolation_preview():
        for child in f_iso.winfo_children():
            child.destroy()
        latest_state = load_state()
        now_ts = time.time()
        active_iso = []
        for sym, deadline in latest_state.get("bot_last_fail_times", {}).items():
            try:
                deadline = float(deadline)
            except (TypeError, ValueError):
                continue
            if deadline > now_ts:
                rem = int(deadline - now_ts)
                active_iso.append((sym, rem))
        ctk.CTkLabel(
            f_iso,
            text="Isolation:",
            font=("Roboto", 11, "bold"),
            text_color="#FFB300" if active_iso else "#757575",
        ).pack(side="left", padx=(10, 6), pady=6)
        if not active_iso:
            ctk.CTkLabel(
                f_iso,
                text="Không có",
                font=("Consolas", 11),
                text_color="#757575",
            ).pack(side="left", padx=4, pady=6)
            return

        def reset_symbol(sym):
            latest = load_state()
            latest.get("bot_last_fail_times", {}).pop(sym, None)
            latest.get("bot_symbol_losing_streak", {}).pop(sym, None)
            save_state(latest)
            if hasattr(app, "trade_mgr"):
                app.trade_mgr.state = latest
            if hasattr(app, "log_message"):
                app.log_message(f"✅ Đã reset isolation cho {sym}.", target="bot")
            render_isolation_preview()
        for sym, rem in active_iso:
            time_str = (
                f"{rem // 3600}h{(rem % 3600) // 60}m"
                if rem >= 3600
                else f"{rem // 60}m"
            )
            ctk.CTkLabel(
                f_iso,
                text=f"{sym} {time_str}",
                font=("Consolas", 11, "bold"),
                text_color="#FF5252",
            ).pack(side="left", padx=(8, 3), pady=6)
            ctk.CTkButton(
                f_iso,
                text="Reset",
                width=54,
                height=24,
                fg_color="#424242",
                hover_color="#616161",
                command=lambda s=sym: reset_symbol(s),
            ).pack(side="left", padx=(0, 6), pady=6)
    render_isolation_preview()
    f_safety = ctk.CTkFrame(tab_core, fg_color="#2b2b2b", corner_radius=8)
    f_safety.pack(fill="x", padx=15, pady=5)
    f_safety.columnconfigure((0, 2), weight=1)

    # [FIX] Đọc safeguard từ brain_settings.json TRƯỚC, fallback về config.py
    safe_cfg = {}
    try:
        import json as _json
        import core.storage_manager as storage_manager
        _cfg_path = storage_manager.BRAIN_FILE
        if os.path.exists(_cfg_path):
            with open(_cfg_path, "r", encoding="utf-8") as _f:
                safe_cfg = _json.load(_f).get("bot_safeguard", {})
    except Exception:
        pass

    # --- [GROUP 1: ⚠️ PHANH KHẨN CẤP GLOBAL (EMERGENCY)] ---
    f_global = ctk.CTkFrame(f_safety, border_width=1, border_color="#F44336")
    f_global.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=5, pady=8)
    ctk.CTkLabel(
        f_global,
        text="⚠️ PHANH KHẨN CẤP (GLOBAL BRAKE)",
        text_color="#F44336",
        font=("Roboto", 13, "bold"),
    ).pack(pady=5)
    f_gl_content = ctk.CTkFrame(f_global, fg_color="transparent")
    f_gl_content.pack(fill="x", padx=10, pady=5)
    ctk.CTkLabel(f_gl_content, text="Bot Max Loss/Ngày (%):").grid(
        row=0, column=0, sticky="w", padx=10, pady=5
    )
    e_max_loss = ctk.CTkEntry(f_gl_content, width=70, justify="center")
    e_max_loss.insert(0, str(safe_cfg.get("MAX_DAILY_LOSS_PERCENT", 2.5)))
    e_max_loss.grid(row=0, column=1, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_gl_content, text="Bot Max Thua (Streak):").grid(
        row=0, column=2, sticky="w", padx=10, pady=5
    )
    e_max_streak = ctk.CTkEntry(f_gl_content, width=70, justify="center")
    e_max_streak.insert(0, str(safe_cfg.get("MAX_LOSING_STREAK", 3)))
    e_max_streak.grid(row=0, column=3, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(
        f_gl_content, text="Global Cooldown (Giờ):", font=("Roboto", 12, "bold")
    ).grid(row=1, column=0, sticky="w", padx=10, pady=5)
    e_global_cooldown = ctk.CTkEntry(
        f_gl_content, width=70, justify="center", fg_color="#311B92"
    )
    e_global_cooldown.insert(0, str(safe_cfg.get("GLOBAL_COOLDOWN_HOURS", 4.0)))
    e_global_cooldown.grid(row=1, column=1, sticky="w", padx=10, pady=5)
    var_gl_on_sg = ctk.BooleanVar(
        value=safe_cfg.get("APPLY_GLOBAL_COOLDOWN_ON_SAFEGUARD", False)
    )
    chk_gl_on_sg = ctk.CTkCheckBox(
        f_gl_content,
        text="Dính Basket/Watermark -> Chặn Global luôn",
        variable=var_gl_on_sg,
        text_color="#FF5252",
        font=("Arial", 11, "italic"),
    )
    chk_gl_on_sg.grid(row=1, column=2, columnspan=2, sticky="w", padx=10, pady=5)

    # --- [GROUP 2: 📉 SAFEGUARD & PROFIT (PROTECTION)] ---
    f_sg = ctk.CTkFrame(f_safety, border_width=1, border_color="#00C853")
    f_sg.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=5, pady=8)
    ctk.CTkLabel(
        f_sg,
        text="📉 BẢO VỆ LỢI NHUẬN & RỔ LỆNH (SAFEGUARD)",
        text_color="#00C853",
        font=("Roboto", 13, "bold"),
    ).pack(pady=5)
    f_sg_content = ctk.CTkFrame(f_sg, fg_color="transparent")
    f_sg_content.pack(fill="x", padx=10, pady=5)
    ctk.CTkLabel(f_sg_content, text="Watermark Global:").grid(
        row=0, column=0, sticky="w", padx=10, pady=5
    )
    e_gl_wm_trigger = ctk.CTkEntry(f_sg_content, width=60, justify="center")
    e_gl_wm_trigger.insert(0, str(safe_cfg.get("WATERMARK_TRIGGER", 0.0)))
    e_gl_wm_trigger.grid(row=0, column=1, sticky="w", padx=5, pady=5)
    cbo_gl_wm_trigger_unit = ctk.CTkOptionMenu(
        f_sg_content, values=["USD", "%Equity"], width=90
    )
    cbo_gl_wm_trigger_unit.set(safe_cfg.get("WATERMARK_TRIGGER_UNIT", "USD"))
    cbo_gl_wm_trigger_unit.grid(row=0, column=2, sticky="w", padx=(0, 10), pady=5)
    ctk.CTkLabel(f_sg_content, text="Drawdown:").grid(
        row=0, column=3, sticky="w", padx=10, pady=5
    )
    e_gl_wm_drawdown = ctk.CTkEntry(f_sg_content, width=60, justify="center")
    e_gl_wm_drawdown.insert(0, str(safe_cfg.get("WATERMARK_DRAWDOWN", 0.0)))
    e_gl_wm_drawdown.grid(row=0, column=4, sticky="w", padx=5, pady=5)
    cbo_gl_wm_drawdown_unit = ctk.CTkOptionMenu(
        f_sg_content, values=["USD", "%Equity"], width=90
    )
    cbo_gl_wm_drawdown_unit.set(safe_cfg.get("WATERMARK_DRAWDOWN_UNIT", "USD"))
    cbo_gl_wm_drawdown_unit.grid(row=0, column=5, sticky="w", padx=(0, 10), pady=5)
    ctk.CTkLabel(f_sg_content, text="Max Basket Loss (DCA/PCA):").grid(
        row=1, column=0, sticky="w", padx=10, pady=5
    )
    e_gl_basket_dd = ctk.CTkEntry(f_sg_content, width=60, justify="center")
    e_gl_basket_dd.insert(0, str(safe_cfg.get("MAX_BASKET_DRAWDOWN_USD", 0.0)))
    e_gl_basket_dd.grid(row=1, column=1, sticky="w", padx=5, pady=5)
    cbo_gl_basket_dd_unit = ctk.CTkOptionMenu(
        f_sg_content, values=["USD", "%Equity"], width=90
    )
    cbo_gl_basket_dd_unit.set(safe_cfg.get("MAX_BASKET_DRAWDOWN_UNIT", "USD"))
    cbo_gl_basket_dd_unit.grid(row=1, column=2, sticky="w", padx=(0, 10), pady=5)
    ctk.CTkLabel(f_sg_content, text="SL Tối thiểu (pts):").grid(
        row=1, column=3, sticky="w", padx=10, pady=5
    )
    e_gl_min_sl = ctk.CTkEntry(f_sg_content, width=60, justify="center")
    e_gl_min_sl.insert(0, str(safe_cfg.get("MIN_SL_POINTS", 0)))
    e_gl_min_sl.grid(row=1, column=4, sticky="w", padx=5, pady=5)
    # Dòng TP & Safeguard bổ sung
    var_bot_use_swing_tp = ctk.BooleanVar(value=safe_cfg.get("BOT_USE_SWING_TP", False))
    var_bot_use_rr_tp = ctk.BooleanVar(value=safe_cfg.get("BOT_USE_RR_TP", True))

    class _HiddenValue:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value
    e_bot_tp_rr = _HiddenValue(str(safe_cfg.get("BOT_TP_RR_RATIO", 1.5)))
    var_strict_min_lot = ctk.BooleanVar(value=safe_cfg.get("STRICT_MIN_LOT", False))
    ctk.CTkCheckBox(
        f_sg_content,
        text="Strict Min Lot",
        variable=var_strict_min_lot,
        text_color="#F44336",
        font=("Roboto", 11, "bold"),
    ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=2)
    var_gl_reject_lot = ctk.BooleanVar(value=safe_cfg.get("REJECT_ON_MAX_LOT", False))
    ctk.CTkCheckBox(
        f_sg_content,
        text="Hủy lệnh vượt Max Lot",
        variable=var_gl_reject_lot,
        font=("Roboto", 11),
    ).grid(row=2, column=2, columnspan=2, sticky="w", padx=10, pady=2)

    # --- [NEW V5.2] GLOBAL BRAKE MODE ---
    ctk.CTkLabel(f_sg_content, text="Global Brake Mode:").grid(
        row=3, column=0, sticky="w", padx=10, pady=(10, 0)
    )
    current_brake_mode = safe_cfg.get("GLOBAL_BRAKE_MODE", "Mode 1: Total Freeze")
    cbo_brake_mode = ctk.CTkOptionMenu(
        f_sg_content,
        values=["Mode 1: Total Freeze", "Mode 2: Symbol Isolation"],
        width=200,
    )
    cbo_brake_mode.set(current_brake_mode)
    cbo_brake_mode.grid(
        row=3, column=1, columnspan=3, sticky="w", padx=10, pady=(10, 0)
    )

    # --- [GROUP 3: 🛡️ ĐIỀU KIỆN VẬN HÀNH (OPERATIONAL)] ---
    f_op = ctk.CTkFrame(f_safety, border_width=1, border_color="#2196F3")
    f_op.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=5, pady=8)
    ctk.CTkLabel(
        f_op,
        text="🛡️ ĐIỀU KIỆN VẬN HÀNH (OPERATIONAL)",
        text_color="#2196F3",
        font=("Roboto", 13, "bold"),
    ).pack(pady=5)
    f_op_content = ctk.CTkFrame(f_op, fg_color="transparent")
    f_op_content.pack(fill="x", padx=10, pady=5)
    ctk.CTkLabel(f_op_content, text="Max Lệnh Mở:").grid(
        row=0, column=0, sticky="w", padx=10, pady=5
    )
    e_max_open = ctk.CTkEntry(f_op_content, width=60, justify="center")
    e_max_open.insert(0, str(safe_cfg.get("MAX_OPEN_POSITIONS", 3)))
    e_max_open.grid(row=0, column=1, sticky="w", padx=5, pady=5)
    ctk.CTkLabel(f_op_content, text="Bot Cooldown (M):").grid(
        row=0, column=2, sticky="w", padx=10, pady=5
    )
    e_cooldown = ctk.CTkEntry(f_op_content, width=60, justify="center")
    e_cooldown.insert(0, str(safe_cfg.get("COOLDOWN_MINUTES", 1)))
    e_cooldown.grid(row=0, column=3, sticky="w", padx=5, pady=5)
    ctk.CTkLabel(f_op_content, text="Tổng Lệnh/Ngày:").grid(
        row=1, column=0, sticky="w", padx=10, pady=5
    )
    e_max_trades = ctk.CTkEntry(f_op_content, width=60, justify="center")
    e_max_trades.insert(0, str(safe_cfg.get("MAX_TRADES_PER_DAY", 30)))
    e_max_trades.grid(row=1, column=1, sticky="w", padx=5, pady=5)
    ctk.CTkLabel(f_op_content, text="Chế độ tính Loss:").grid(
        row=1, column=2, sticky="w", padx=10, pady=5
    )
    cbo_loss_mode = ctk.CTkOptionMenu(
        f_op_content, values=["TOTAL", "STREAK"], width=80, height=24
    )
    cbo_loss_mode.set(safe_cfg.get("LOSS_COUNT_MODE", "TOTAL"))
    cbo_loss_mode.grid(row=1, column=3, sticky="w", padx=5, pady=5)
    var_check_ping = ctk.BooleanVar(value=safe_cfg.get("CHECK_PING", True))
    ctk.CTkCheckBox(
        f_op_content, text="Ping (ms):", variable=var_check_ping, font=("Roboto", 11)
    ).grid(row=2, column=0, sticky="w", padx=10, pady=5)
    e_max_ping = ctk.CTkEntry(f_op_content, width=60, justify="center")
    e_max_ping.insert(0, str(safe_cfg.get("MAX_PING_MS", 150)))
    e_max_ping.grid(row=2, column=1, sticky="w", padx=5, pady=5)
    var_check_spread = ctk.BooleanVar(value=safe_cfg.get("CHECK_SPREAD", True))
    ctk.CTkCheckBox(
        f_op_content,
        text="Spread (pts):",
        variable=var_check_spread,
        font=("Roboto", 11),
    ).grid(row=2, column=2, sticky="w", padx=10, pady=5)
    e_max_spread = ctk.CTkEntry(f_op_content, width=60, justify="center")
    e_max_spread.insert(0, str(safe_cfg.get("MAX_SPREAD_POINTS", 50)))
    e_max_spread.grid(row=2, column=3, sticky="w", padx=5, pady=5)
    ctk.CTkLabel(f_op_content, text="Nghỉ sau đóng (s):", text_color="#FFB300").grid(
        row=3, column=0, sticky="w", padx=10, pady=5
    )
    e_post_close = ctk.CTkEntry(f_op_content, width=60, justify="center")
    e_post_close.insert(0, str(safe_cfg.get("POST_CLOSE_COOLDOWN", 0)))
    e_post_close.grid(row=3, column=1, sticky="w", padx=5, pady=5)

    # --- [GROUP 4: ⚙️ HỆ THỐNG & TẦN SUẤT (SYSTEM)] ---
    f_sys = ctk.CTkFrame(f_safety, border_width=1, border_color="#757575")
    f_sys.grid(row=3, column=0, columnspan=4, sticky="nsew", padx=5, pady=8)
    ctk.CTkLabel(
        f_sys,
        text="⚙️ HỆ THỐNG & TẦN SUẤT (SYSTEM)",
        text_color="#757575",
        font=("Roboto", 13, "bold"),
    ).pack(pady=5)
    f_sys_content = ctk.CTkFrame(f_sys, fg_color="transparent")
    f_sys_content.pack(fill="x", padx=10, pady=5)
    ctk.CTkLabel(f_sys_content, text="Loop (s):").grid(
        row=0, column=0, sticky="w", padx=10, pady=5
    )
    e_daemon_loop = ctk.CTkEntry(f_sys_content, width=50, justify="center")
    e_daemon_loop.insert(0, str(safe_cfg.get("DAEMON_LOOP_DELAY", 15)))
    e_daemon_loop.grid(row=0, column=1, sticky="w", padx=5, pady=5)
    ctk.CTkLabel(f_sys_content, text="Nhồi (s):").grid(
        row=0, column=2, sticky="w", padx=10, pady=5
    )
    e_scan_delay = ctk.CTkEntry(f_sys_content, width=50, justify="center")
    e_scan_delay.insert(0, str(safe_cfg.get("DCA_PCA_SCAN_INTERVAL", 2)))
    e_scan_delay.grid(row=0, column=3, sticky="w", padx=5, pady=5)
    ctk.CTkLabel(f_sys_content, text="Nến Trend:").grid(
        row=1, column=0, sticky="w", padx=10, pady=5
    )
    e_num_h1 = ctk.CTkEntry(f_sys_content, width=50, justify="center")
    e_num_h1.insert(0, str(safe_cfg.get("NUM_H1_BARS", 70)))
    e_num_h1.grid(row=1, column=1, sticky="w", padx=5, pady=5)
    ctk.CTkLabel(f_sys_content, text="Nến Entry:").grid(
        row=1, column=2, sticky="w", padx=10, pady=5
    )
    e_num_m15 = ctk.CTkEntry(f_sys_content, width=50, justify="center")
    e_num_m15.insert(0, str(safe_cfg.get("NUM_M15_BARS", 70)))
    e_num_m15.grid(row=1, column=3, sticky="w", padx=5, pady=5)
    ctk.CTkLabel(f_sys_content, text="Log Spam (M):").grid(
        row=2, column=0, sticky="w", padx=10, pady=5
    )
    e_log_cooldown = ctk.CTkEntry(f_sys_content, width=50, justify="center")
    e_log_cooldown.insert(0, str(safe_cfg.get("LOG_COOLDOWN_MINUTES", 60)))
    e_log_cooldown.grid(row=2, column=1, sticky="w", padx=5, pady=5)

    # [HINT / LEGEND AT BOTTOM]
    f_hint = ctk.CTkFrame(f_safety, fg_color="#212121")
    f_hint.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=5, pady=5)
    for text, color in [
        ("Phanh Global", "#F44336"),
        ("Bảo vệ", "#00C853"),
        ("Điều kiện", "#2196F3"),
        ("Hệ thống", "#BDBDBD"),
    ]:
        ctk.CTkLabel(
            f_hint,
            text=f"● {text}",
            font=("Arial", 10, "italic"),
            text_color=color,
        ).pack(side="left", padx=(10, 2), pady=2)

    def save():
        try:
            import json, os
            import core.storage_manager as storage_manager
            cfg_path = storage_manager.BRAIN_FILE
            existing_data = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            if "bot_safeguard" not in existing_data:
                existing_data["bot_safeguard"] = {}
            existing_data["bot_safeguard"].update(
                {
                    "MAX_DAILY_LOSS_PERCENT": float(e_max_loss.get()),
                    "MAX_OPEN_POSITIONS": int(e_max_open.get()),
                    "MAX_TRADES_PER_DAY": int(e_max_trades.get()),
                    "MAX_LOSING_STREAK": int(e_max_streak.get()),
                    "LOSS_COUNT_MODE": cbo_loss_mode.get(),
                    "COOLDOWN_MINUTES": int(e_cooldown.get()),
                    "NUM_H1_BARS": int(e_num_h1.get()),
                    "NUM_M15_BARS": int(e_num_m15.get()),
                    "CHECK_PING": var_check_ping.get(),
                    "MAX_PING_MS": int(e_max_ping.get()),
                    "CHECK_SPREAD": var_check_spread.get(),
                    "MAX_SPREAD_POINTS": int(e_max_spread.get()),
                    "DAEMON_LOOP_DELAY": float(e_daemon_loop.get()),
                    "DCA_PCA_SCAN_INTERVAL": float(e_scan_delay.get()),
                    "LOG_COOLDOWN_MINUTES": float(e_log_cooldown.get()),
                    "BOT_USE_SWING_TP": var_bot_use_swing_tp.get(),
                    "BOT_USE_RR_TP": var_bot_use_rr_tp.get(),
                    "BOT_TP_RR_RATIO": float(e_bot_tp_rr.get()),
                    "STRICT_MIN_LOT": var_strict_min_lot.get(),
                    "POST_CLOSE_COOLDOWN": int(e_post_close.get()),
                    "GLOBAL_COOLDOWN_HOURS": float(e_global_cooldown.get()),
                    "APPLY_GLOBAL_COOLDOWN_ON_SAFEGUARD": var_gl_on_sg.get(),
                    "WATERMARK_TRIGGER": float(e_gl_wm_trigger.get()),
                    "WATERMARK_TRIGGER_UNIT": cbo_gl_wm_trigger_unit.get(),
                    "WATERMARK_DRAWDOWN": float(e_gl_wm_drawdown.get()),
                    "WATERMARK_DRAWDOWN_UNIT": cbo_gl_wm_drawdown_unit.get(),
                    "MIN_SL_POINTS": int(e_gl_min_sl.get()),
                    "MAX_BASKET_DRAWDOWN_USD": float(e_gl_basket_dd.get()),
                    "MAX_BASKET_DRAWDOWN_UNIT": cbo_gl_basket_dd_unit.get(),
                    "REJECT_ON_MAX_LOT": var_gl_reject_lot.get(),
                    "GLOBAL_BRAKE_MODE": cbo_brake_mode.get(),
                }
            )
            existing_data["BOT_ACTIVE_SYMBOLS"] = [
                coin for coin, var in app.bot_coin_vars.items() if var.get()
            ]
            config.BOT_ACTIVE_SYMBOLS = existing_data["BOT_ACTIVE_SYMBOLS"]
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=4)
            from core.storage_manager import invalidate_settings_cache
            invalidate_settings_cache()
            if hasattr(app, "reload_config_from_json"):
                app.reload_config_from_json()
            app.log_message("✅ Đã cập nhật đầy đủ Bot Settings.", target="bot")
            top.destroy()
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Lỗi", f"Lỗi lưu cấu hình: {e}", parent=top)
    ctk.CTkButton(
        top,
        text="LƯU CẤU HÌNH BOT SETTINGS",
        fg_color=COL_BLUE_ACCENT,
        height=45,
        font=("Roboto", 13, "bold"),
        command=save,
    ).pack(pady=15, fill="x", padx=40)

# ==============================================================================

# 2. POPUP PRESET (CÓ LIVE PREVIEW ĐẦY ĐỦ)

# ==============================================================================


def open_advanced_tools_popup(app):

    top = ctk.CTkToplevel(app)
    top.title("Advanced Tools")
    top.geometry("1080x720")
    top.minsize(980, 620)
    top.resizable(True, True)
    try:
        top.transient(app)
    except Exception:
        pass
    _bring_popup_to_front(top, delay_ms=100)
    top._advanced_tools_zoomed = False

    def _toggle_advanced_tools_fullscreen():
        try:
            if getattr(top, "_advanced_tools_zoomed", False):
                top.state("normal")
                top.geometry("1080x720")
                top._advanced_tools_zoomed = False
                btn_fullscreen.configure(text="FULLSCREEN")
            else:
                top.state("zoomed")
                top._advanced_tools_zoomed = True
                btn_fullscreen.configure(text="RESTORE")
        except Exception:
            try:
                top.attributes("-fullscreen", not bool(top.attributes("-fullscreen")))
            except Exception:
                pass

    toolbar = ctk.CTkFrame(top, fg_color="transparent")
    toolbar.pack(fill="x", padx=12, pady=(8, 0))
    btn_fullscreen = ctk.CTkButton(
        toolbar,
        text="FULLSCREEN",
        width=120,
        fg_color="#455A64",
        command=_toggle_advanced_tools_fullscreen,
    )
    btn_fullscreen.pack(side="right")
    tabs = ctk.CTkTabview(top)
    tabs.pack(fill="both", expand=True, padx=12, pady=(8, 12))
    tab_grid = tabs.add("GRID")
    tab_hedge = tabs.add("HEDGE")
    tab_backtest = tabs.add("BACKTEST")
    grid_body = _speed_up_scroll(ctk.CTkScrollableFrame(tab_grid, fg_color="transparent"))
    grid_body.pack(fill="both", expand=True)
    ctk.CTkLabel(
        grid_body, text="GRID Control", font=("Roboto", 16, "bold"), text_color="#00B8D4"
    ).pack(anchor="w", padx=14, pady=(14, 6))
    ctk.CTkLabel(
        grid_body,
        text="Auto GRID cho daemon. Manual GRID tren panel trade van start duoc khi Auto GRID OFF.",
        font=("Arial", 12, "italic"),
        text_color="#80DEEA",
        anchor="w",
        wraplength=680,
    ).pack(fill="x", padx=14, pady=(0, 12))
    try:
        from grid.grid_storage import load_grid_settings, save_grid_settings
        grid_cfg = load_grid_settings()
    except Exception:
        grid_cfg = {"ENABLED": False}
    var_grid_enabled = ctk.BooleanVar(value=grid_cfg.get("ENABLED", False))

    def _set_status_lights(is_on):
        color = COL_GREEN if is_on else COL_RED
        for attr in ("ind_grid_light", "ind_ad_grid_light"):
            light = getattr(app, attr, None)
            if light and light.winfo_exists():
                light.configure(fg_color=color)

    def _toggle_grid_enabled():
        try:
            from grid.grid_storage import load_grid_settings, save_grid_settings
            if var_grid_enabled.get() and hasattr(app, "set_auto_trade_enabled"):
                app.set_auto_trade_enabled(False, reason="GRID_ON")
            next_cfg = load_grid_settings()
            next_cfg["ENABLED"] = var_grid_enabled.get()
            save_grid_settings(next_cfg)
            _set_status_lights(var_grid_enabled.get())
            lbl_grid_state.configure(
                text=f"Auto GRID: {'ON' if var_grid_enabled.get() else 'OFF'}",
                text_color="#00B8D4" if var_grid_enabled.get() else "gray",
            )
            try:
                lbl_grid_summary.configure(text=_grid_control_summary())
            except Exception:
                pass
            if hasattr(app, "log_message"):
                state = "ON" if var_grid_enabled.get() else "OFF"
                app.log_message(f"[GRID] AUTO GRID ENABLED = {state}", target="grid")
        except Exception as e:
            messagebox.showerror("GRID", f"Khong the luu GRID switch: {e}", parent=top)
    f_grid_switch = ctk.CTkFrame(grid_body, fg_color="#242424", corner_radius=8)
    f_grid_switch.pack(fill="x", padx=14, pady=(0, 12))
    lbl_grid_state = ctk.CTkLabel(
        f_grid_switch,
        text=f"Auto GRID: {'ON' if var_grid_enabled.get() else 'OFF'}",
        font=("Roboto", 12, "bold"),
        text_color="#00B8D4" if var_grid_enabled.get() else "gray",
    )
    ctk.CTkSwitch(
        f_grid_switch,
        text="AUTO GRID ENABLED",
        variable=var_grid_enabled,
        progress_color="#00B8D4",
        fg_color=COL_RED,
        font=("Roboto", 13, "bold"),
        command=_toggle_grid_enabled,
    ).pack(side="left", padx=12, pady=12)
    lbl_grid_state.pack(side="left", padx=12)

    def _grid_control_summary():
        try:
            from grid.grid_storage import load_grid_settings, load_grid_state
            cfg = load_grid_settings()
            st = load_grid_state()
            last = (st.get("last_decision") or {})
            last_txt = "No decision yet"
            range_txt = "Range: ---"
            next_txt = "Next: ---"
            if last:
                sym, data = list(last.items())[-1]
                last_txt = f"{sym}: {data.get('status')} / {data.get('reason')}"
                boundary = data.get("boundary") or (st.get("active_sessions", {}).get(sym, {}) or {}).get("boundary")
                if isinstance(boundary, dict):
                    range_txt = f"Range: {float(boundary.get('lower', 0.0)):.2f} -> {float(boundary.get('upper', 0.0)):.2f} ({boundary.get('source', '---')})"
                if data.get("reason") == "PRICE_OUT_OF_BOUNDARY":
                    policy = cfg.get("OUT_OF_RANGE_POLICY", "STOP")
                    next_txt = "Next: stop new orders" if policy == "STOP" else "Next: auto rebuild range"
                elif data.get("status") in ("READY", "OPEN"):
                    next_txt = f"Next: {data.get('direction', 'ORDER')}"
                else:
                    next_txt = f"Next: {data.get('reason', 'WAIT')}"
            return (
                f"Type: {cfg.get('GRID_TYPE', 'ATR_DYNAMIC')} | "
                f"Signal: {cfg.get('GRID_SIGNAL_SOURCE', 'OFF')} | "
                f"OutRange: {cfg.get('OUT_OF_RANGE_POLICY', 'STOP')} | "
                f"Scan: {cfg.get('GRID_SCAN_INTERVAL_SECONDS', 5)}s | "
                f"Mode auto: {'ON' if cfg.get('DYNAMIC_MODE_ENABLED', True) else 'OFF'} | "
                f"Lot: {cfg.get('FIXED_LOT', 0.01)} | "
                f"Max orders: {cfg.get('MAX_GRID_ORDERS', 0)} | "
                f"Max DD: {cfg.get('MAX_BASKET_DRAWDOWN', 0.0)}\n"
                f"{range_txt} | {next_txt}\n"
                f"Today PnL: {float(st.get('grid_pnl_today', 0.0) or 0.0):+.2f} | "
                f"Trades: {int(st.get('grid_trades_today', 0) or 0)} | "
                f"Last: {last_txt}"
            )
        except Exception as e:
            return f"GRID summary error: {e}"

    lbl_grid_summary = ctk.CTkLabel(
        grid_body,
        text=_grid_control_summary(),
        font=("Consolas", 13),
        text_color="#80DEEA",
        justify="left",
        anchor="w",
    )
    lbl_grid_summary.pack(fill="x", padx=14, pady=(0, 10))

    quick = ctk.CTkFrame(grid_body, fg_color="#242424", corner_radius=8)
    quick.pack(fill="x", padx=14, pady=(0, 12))
    ctk.CTkLabel(quick, text="Safety Quick", font=("Roboto", 13, "bold"), text_color="#00B8D4").grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(8, 4))

    def _quick_entry(label, value, row, col):
        ctk.CTkLabel(quick, text=label).grid(row=row, column=col, sticky="w", padx=10, pady=5)
        entry = ctk.CTkEntry(quick, width=90, justify="center")
        entry.insert(0, str(value))
        entry.grid(row=row, column=col + 1, sticky="w", padx=10, pady=5)
        return entry

    e_q_max_orders = _quick_entry("Max Orders", grid_cfg.get("MAX_GRID_ORDERS", 0), 1, 0)
    e_q_max_lot = _quick_entry("Max Lot", grid_cfg.get("MAX_TOTAL_LOT", 0.0), 1, 2)
    e_q_max_dd = _quick_entry("Basket DD", grid_cfg.get("MAX_BASKET_DRAWDOWN", 0.0), 2, 0)
    e_q_daily_loss = _quick_entry("Daily Loss", grid_cfg.get("GRID_MAX_DAILY_LOSS", 0.0), 2, 2)

    def _save_quick_safety():
        try:
            from grid.grid_storage import load_grid_settings, save_grid_settings
            next_cfg = load_grid_settings()
            next_cfg["MAX_GRID_ORDERS"] = int(e_q_max_orders.get() or 0)
            next_cfg["MAX_TOTAL_LOT"] = float(e_q_max_lot.get() or 0.0)
            next_cfg["MAX_BASKET_DRAWDOWN"] = float(e_q_max_dd.get() or 0.0)
            next_cfg["GRID_MAX_DAILY_LOSS"] = float(e_q_daily_loss.get() or 0.0)
            save_grid_settings(next_cfg)
            lbl_grid_summary.configure(text=_grid_control_summary())
            if hasattr(app, "log_message"):
                app.log_message("[GRID] Quick safety saved.", target="grid")
        except ValueError:
            messagebox.showerror("GRID", "Safety quick nhap sai kieu so.", parent=top)

    def _clear_grid_block():
        try:
            mgr = getattr(app, "grid_mgr", None)
            if mgr:
                mgr.clear_session_block()
            lbl_grid_summary.configure(text=_grid_control_summary())
            if hasattr(app, "log_message"):
                app.log_message("[GRID] Clear GRID block done.", target="grid")
        except Exception as e:
            messagebox.showerror("GRID", f"Khong the clear GRID block: {e}", parent=top)

    def _current_grid_symbol():
        try:
            return app.cbo_symbol.get()
        except Exception:
            return getattr(config, "DEFAULT_SYMBOL", "ETHUSD")

    def _rebuild_grid_range():
        try:
            sym = _current_grid_symbol()
            ctx = getattr(app, "latest_market_context", {}).get(sym, {})
            mgr = getattr(app, "grid_mgr", None)
            result = mgr.rebuild_session_range(sym, ctx) if mgr else "FAILED|NO_GRID_MANAGER"
            lbl_grid_summary.configure(text=_grid_control_summary())
            if hasattr(app, "log_message"):
                app.log_message(f"[GRID] Rebuild range {sym}: {result}", target="grid")
        except Exception as e:
            messagebox.showerror("GRID", f"Khong the rebuild GRID range: {e}", parent=top)

    def _stop_grid_session():
        try:
            sym = _current_grid_symbol()
            mgr = getattr(app, "grid_mgr", None)
            result = mgr.stop_session(sym) if mgr else "FAILED|NO_GRID_MANAGER"
            lbl_grid_summary.configure(text=_grid_control_summary())
            if hasattr(app, "log_message"):
                app.log_message(f"[GRID] Stop session {sym}: {result}", target="grid")
        except Exception as e:
            messagebox.showerror("GRID", f"Khong the stop GRID session: {e}", parent=top)

    ctk.CTkButton(
        quick,
        text="SAVE QUICK SAFETY",
        fg_color="#00838F",
        hover_color="#006064",
        command=_save_quick_safety,
    ).grid(row=3, column=0, columnspan=4, sticky="ew", padx=10, pady=(8, 10))
    ctk.CTkButton(
        quick,
        text="CLEAR GRID BLOCK",
        fg_color="#455A64",
        hover_color="#37474F",
        command=_clear_grid_block,
    ).grid(row=4, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))
    ctk.CTkButton(
        quick,
        text="REBUILD GRID RANGE",
        fg_color="#1565C0",
        hover_color="#0D47A1",
        command=_rebuild_grid_range,
    ).grid(row=5, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))
    ctk.CTkButton(
        quick,
        text="STOP GRID SESSION",
        fg_color="#6D4C41",
        hover_color="#4E342E",
        command=_stop_grid_session,
    ).grid(row=6, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))

    def _open_grid_settings():
        from grid.grid_ui import open_grid_settings_popup
        open_grid_settings_popup(app)
    ctk.CTkButton(
        grid_body,
        text="OPEN GRID SETTINGS",
        fg_color="#00838F",
        hover_color="#006064",
        font=("Roboto", 13, "bold"),
        command=_open_grid_settings,
    ).pack(anchor="w", padx=14, pady=8)
    hedge_body = _speed_up_scroll(ctk.CTkScrollableFrame(tab_hedge, fg_color="transparent"))
    hedge_body.pack(fill="both", expand=True)
    ctk.CTkLabel(
        hedge_body, text="HEDGE Dual Control", font=("Roboto", 16, "bold"), text_color="#CE93D8"
    ).pack(anchor="w", padx=14, pady=(14, 6))
    ctk.CTkLabel(
        hedge_body,
        text="Auto HEDGE quét watchlist riêng theo chu kỳ riêng. Signal và Entry/Exit chỉ là bộ lọc entry; safety/daily loss là state riêng của HEDGE.",
        font=("Arial", 12, "italic"),
        text_color="#E1BEE7",
        anchor="w",
        wraplength=680,
    ).pack(fill="x", padx=14, pady=(0, 12))
    try:
        from hedge.hedge_storage import load_hedge_settings, load_hedge_state, save_hedge_settings
        hedge_cfg = load_hedge_settings()
        hedge_state = load_hedge_state()
    except Exception:
        hedge_cfg = {"ENABLED": False}
        hedge_state = {}

    var_hedge_enabled = ctk.BooleanVar(value=hedge_cfg.get("ENABLED", False))
    var_hedge_signal = ctk.BooleanVar(value=hedge_cfg.get("USE_SIGNAL_FILTER", False))
    var_hedge_override = ctk.BooleanVar(value=False)

    def _current_hedge_symbol():
        try:
            return app.cbo_symbol.get()
        except Exception:
            return getattr(config, "DEFAULT_SYMBOL", "ETHUSD")

    def _hedge_timeframe_for_group(group):
        try:
            cfg = _effective_hedge_cfg(_current_hedge_symbol())
        except Exception:
            cfg = hedge_cfg
        return cfg.get("SWING_TIMEFRAME", hedge_cfg.get("SWING_TIMEFRAME", "15m"))

    def _save_hedge_timeframe_for_group(group, timeframe):
        return None

    def _effective_hedge_cfg(symbol=None):
        symbol = symbol or _current_hedge_symbol()
        try:
            mgr = getattr(app, "hedge_mgr", None)
            return mgr.settings_for_symbol(symbol, load_hedge_settings()) if mgr else load_hedge_settings()
        except Exception:
            return hedge_cfg

    hedge_preview_form_getter = None

    def _hedge_preview_text():
        try:
            from hedge.hedge_storage import load_hedge_settings as _load_hs
            base_cfg = _load_hs()
        except Exception:
            base_cfg = {}
        symbols = list(base_cfg.get("WATCHLIST") or [])
        try:
            live_symbols = [sym for sym, var in hedge_watchlist_vars.items() if var.get()]
            if live_symbols:
                symbols = live_symbols
        except Exception:
            pass
        current_symbol = _current_hedge_symbol()
        if current_symbol not in symbols:
            symbols.insert(0, current_symbol)
        if not symbols:
            symbols = list(getattr(config, "COIN_LIST", []) or [current_symbol])
        contexts = getattr(app, "latest_market_context", {}) or {}
        lines = [f"{'Symbol':<8} {'Price':>10}  {'Gate':<8} {'Signal':<8} {'Entry':<8} Reason"]
        for symbol in symbols[:8]:
            cfg = _effective_hedge_cfg(symbol)
            if symbol == current_symbol and callable(hedge_preview_form_getter):
                try:
                    cfg = {**cfg, **hedge_preview_form_getter()}
                except Exception:
                    pass
            ctx = contexts.get(symbol, {}) if isinstance(contexts, dict) else {}
            gate = {"status": "WAIT", "reason": "No context", "signal_status": "---", "entry_status": "---"}
            try:
                gate = app.hedge_mgr.evaluate_entry_gate(symbol, ctx, cfg)
            except Exception as exc:
                gate["reason"] = f"ERR:{exc}"
            price = ctx.get("current_price") or ctx.get("price") or ctx.get("bid") or ctx.get("ask")
            if price is None and hasattr(app, "connector"):
                try:
                    tick = app.connector.get_market_status(symbol)
                    if isinstance(tick, dict):
                        price = tick.get("last") or tick.get("bid") or tick.get("ask") or tick.get("price")
                except Exception:
                    price = None
            price_txt = f"{float(price):,.2f}" if isinstance(price, (int, float)) else "---"
            reason = str(gate.get("reason", "---"))[:28]
            lines.append(
                f"{symbol:<8} {price_txt:>10}  {str(gate.get('status', '---')):<8} "
                f"{str(gate.get('signal_status', '---')):<8} {str(gate.get('entry_status', '---')):<8} {reason}"
            )
        if len(symbols) > 8:
            lines.append(f"... +{len(symbols) - 8} symbols")
        return "\n".join(lines)

    def _set_hedge_lights(is_on):
        color = COL_GREEN if is_on else COL_RED
        for attr in ("ind_hedge_light", "ind_ad_hedge_light", "ind_hedge_ready_light"):
            light = getattr(app, attr, None)
            if light and light.winfo_exists():
                light.configure(fg_color=color)

    def _hedge_summary():
        try:
            from hedge.hedge_storage import load_hedge_settings, load_hedge_state
            cfg = load_hedge_settings()
            st = load_hedge_state()
            last = st.get("last_decision") or {}
            last_txt = "No decision yet"
            if last:
                sym, data = list(last.items())[-1]
                last_txt = f"{sym}: {data.get('status')} / {data.get('reason')}"
            return (
                f"Auto scan: {'ON' if cfg.get('ENABLED') else 'OFF'} | "
                f"Watchlist: {', '.join(cfg.get('WATCHLIST') or []) or 'trống'} | "
                f"Scan: {cfg.get('HEDGE_SCAN_INTERVAL_SECONDS', 2)}s | Log cooldown: {cfg.get('HEDGE_LOG_COOLDOWN_SECONDS', 300)}s\n"
                f"Mode: DUAL | "
                f"Signal filter: {'ON' if cfg.get('USE_SIGNAL_FILTER') else 'OFF'} | "
                f"Entry/Exit filter: {'ON' if cfg.get('USE_ENTRY_EXIT_FILTER') else 'OFF'} | "
                f"HEDGE SL/TP: {'ON' if cfg.get('USE_HEDGE_SLTP', cfg.get('USE_SANDBOX_SLTP', True)) else 'OFF'} | "
                f"TSL: {cfg.get('HEDGE_TSL_MODE', 'BE+STEP_R+SWING') if cfg.get('USE_TSL', True) else 'OFF'} | "
                f"Survivor: {cfg.get('SURVIVOR_PROTECT', 'BE_FEE')} | "
                f"Lot mode: {cfg.get('LOT_MODE', 'FIXED')} | Base lot: {cfg.get('FIXED_LOT', 0.1)} | "
                f"Account risk: {cfg.get('RISK_PERCENT_PER_PAIR', 0.5)}% | Max lot cap: {cfg.get('MAX_LOT_CAP', 1.0)} | "
                f"Max pairs/symbol: {cfg.get('MAX_PAIRS_PER_SYMBOL', 1)}\n"
                f"Daily loss: {cfg.get('HEDGE_MAX_DAILY_LOSS', 0.0)} | "
                f"Session TP/SL: {cfg.get('HEDGE_SESSION_TP_USD', 0.0)}/{cfg.get('HEDGE_SESSION_SL_USD', 0.0)} | "
                f"Timeout: {cfg.get('HEDGE_MAX_HOLD_MINUTES', 0)}m | "
                f"Cooldown close: {cfg.get('COOLDOWN_AFTER_CLOSE_SECONDS', 900)}s | "
                f"Cooldown loss: {cfg.get('COOLDOWN_AFTER_LOSS_SECONDS', 1800)}s | "
                f"Spread: {'ON' if cfg.get('CHECK_SPREAD', True) else 'OFF'}<= {cfg.get('MAX_SPREAD_POINTS', 150)} | "
                f"Ping: {'ON' if cfg.get('CHECK_PING', True) else 'OFF'}<= {cfg.get('MAX_PING_MS', 150)}ms\n"
                f"Today PnL: {float(st.get('hedge_pnl_today', 0.0) or 0.0):+.2f} | "
                f"Sessions: {int(st.get('hedge_sessions_today', 0) or 0)} | Last: {last_txt}"
            )
        except Exception as e:
            return f"HEDGE summary error: {e}"

    def _toggle_hedge_enabled():
        try:
            from hedge.hedge_storage import load_hedge_settings, save_hedge_settings
            cfg = load_hedge_settings()
            cfg["ENABLED"] = var_hedge_enabled.get()
            save_hedge_settings(cfg)
            _set_hedge_lights(var_hedge_enabled.get())
            if hasattr(app, "refresh_hedge_runtime_light"):
                app.refresh_hedge_runtime_light()
            lbl_hedge_state.configure(
                text=f"Auto scan: {'ON' if var_hedge_enabled.get() else 'OFF'}",
                text_color="#CE93D8" if var_hedge_enabled.get() else "gray",
            )
            if preview_frame.winfo_exists():
                preview_frame.configure(border_color=COL_GREEN if var_hedge_enabled.get() else "#6A1B9A")
            if lbl_preview_live.winfo_exists():
                lbl_preview_live.configure(
                    text="LIVE" if var_hedge_enabled.get() else "STANDBY",
                    text_color=COL_GREEN if var_hedge_enabled.get() else "#B0BEC5",
                )
            lbl_hedge_summary.configure(text=_hedge_summary())
            if hasattr(app, "log_message"):
                app.log_message(f"[HEDGE] AUTO HEDGE ENABLED = {'ON' if var_hedge_enabled.get() else 'OFF'}", target="hedge")
        except Exception as e:
            messagebox.showerror("HEDGE", f"Khong the luu HEDGE switch: {e}", parent=top)

    f_hedge_switch = ctk.CTkFrame(hedge_body, fg_color="#242424", corner_radius=8)
    f_hedge_switch.pack(fill="x", padx=14, pady=(0, 12))
    lbl_hedge_state = ctk.CTkLabel(
        f_hedge_switch,
        text=f"Auto scan: {'ON' if var_hedge_enabled.get() else 'OFF'}",
        font=("Roboto", 12, "bold"),
        text_color="#CE93D8" if var_hedge_enabled.get() else "gray",
    )
    ctk.CTkSwitch(
        f_hedge_switch,
        text="AUTO HEDGE BOT",
        variable=var_hedge_enabled,
        progress_color="#8E24AA",
        fg_color=COL_RED,
        font=("Roboto", 13, "bold"),
        command=_toggle_hedge_enabled,
    ).pack(side="left", padx=12, pady=12)
    lbl_hedge_state.pack(side="left", padx=12)
    _set_hedge_lights(var_hedge_enabled.get())

    lbl_hedge_summary = ctk.CTkLabel(
        hedge_body,
        text=_hedge_summary(),
        font=("Roboto", 12),
        text_color="#E1BEE7",
        justify="left",
        anchor="w",
    )

    preview_frame = ctk.CTkFrame(
        hedge_body,
        fg_color="#171F1C" if var_hedge_enabled.get() else "#211628",
        corner_radius=8,
        border_width=2,
        border_color=COL_GREEN if var_hedge_enabled.get() else "#6A1B9A",
    )
    preview_frame.pack(fill="x", padx=14, pady=(0, 10))
    preview_head = ctk.CTkFrame(preview_frame, fg_color="transparent")
    preview_head.pack(fill="x", padx=12, pady=(10, 2))
    ctk.CTkLabel(
        preview_head,
        text="HEDGE Gate Monitor",
        font=("Roboto", 13, "bold"),
        text_color=COL_GREEN if var_hedge_enabled.get() else "#CE93D8",
    ).pack(side="left")
    lbl_preview_live = ctk.CTkLabel(
        preview_head,
        text="LIVE" if var_hedge_enabled.get() else "STANDBY",
        font=("Roboto", 12, "bold"),
        text_color=COL_GREEN if var_hedge_enabled.get() else "#B0BEC5",
    )
    lbl_preview_live.pack(side="right")
    lbl_hedge_preview = ctk.CTkLabel(
        preview_frame,
        text=_hedge_preview_text(),
        font=("Consolas", 12),
        text_color="#FFFFFF",
        justify="left",
        anchor="w",
        wraplength=920,
    )
    lbl_hedge_preview.pack(fill="x", padx=12, pady=(0, 8))

    ctk.CTkLabel(
        preview_frame,
        text=(
            "Monitor hiển thị Symbol, Price, Signal gate, Entry gate và lý do block/pass theo watchlist."
        ),
        font=("Arial", 11, "italic"),
        text_color="#F8BBD0",
        anchor="w",
        justify="left",
        wraplength=920,
    ).pack(fill="x", padx=12, pady=(0, 10))

    hsimple = ctk.CTkFrame(
        hedge_body,
        fg_color="#242424",
        corner_radius=8,
        border_width=1,
        border_color="#6A1B9A",
    )
    hsimple.pack(fill="x", padx=14, pady=(0, 12))
    hsimple.grid_columnconfigure((0, 1), weight=1, uniform="hedge_cfg")
    cfg_header = ctk.CTkFrame(hsimple, fg_color="transparent")
    cfg_header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 4))
    cfg_header.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        cfg_header,
        text="HEDGE Dual Config",
        font=("Roboto", 13, "bold"),
        text_color="#CE93D8",
    ).grid(row=0, column=0, sticky="w")
    btn_open_hedge_override = ctk.CTkButton(
        cfg_header,
        text="OPEN OVERRIDE",
        fg_color="#7B1FA2",
        hover_color="#4A148C",
        width=150,
        height=30,
        state="disabled",
    )
    btn_open_hedge_override.grid(row=0, column=1, sticky="e", padx=(8, 0))
    btn_save_hedge_settings = ctk.CTkButton(
        cfg_header,
        text="SAVE SETTINGS",
        fg_color="#6A1B9A",
        hover_color="#4A148C",
        width=140,
        height=30,
        state="disabled",
    )
    btn_save_hedge_settings.grid(row=0, column=2, sticky="e", padx=(8, 0))
    btn_clear_hedge_cooldown = ctk.CTkButton(
        cfg_header,
        text="CLEAR BLOCK/CD",
        fg_color="#455A64",
        hover_color="#37474F",
        width=145,
        height=30,
        state="disabled",
    )
    btn_clear_hedge_cooldown.grid(row=0, column=3, sticky="e", padx=(8, 0))
    var_h_entry_filter = ctk.BooleanVar(value=bool(hedge_cfg.get("USE_ENTRY_EXIT_FILTER", False)))
    var_h_hedge_sltp = ctk.BooleanVar(value=bool(hedge_cfg.get("USE_HEDGE_SLTP", hedge_cfg.get("USE_SANDBOX_SLTP", True))))
    var_h_tsl = ctk.BooleanVar(value=bool(hedge_cfg.get("USE_TSL", True)))
    def _h_section(parent, title, row, col, color="#CE93D8", columnspan=1):
        frame = ctk.CTkFrame(parent, fg_color="#202020", corner_radius=8, border_width=1, border_color=color)
        frame.grid(row=row, column=col, columnspan=columnspan, sticky="new", padx=10, pady=8)
        frame.grid_columnconfigure((1, 3, 5, 7), weight=1)
        ctk.CTkLabel(frame, text=title, font=("Roboto", 12, "bold"), text_color=color).grid(
            row=0, column=0, columnspan=8, sticky="w", padx=10, pady=(8, 4)
        )
        return frame

    right_stack = ctk.CTkFrame(hsimple, fg_color="transparent")
    right_stack.grid(row=1, column=1, sticky="new", padx=0, pady=0)
    right_stack.grid_columnconfigure(0, weight=1)
    f_risk = _h_section(hsimple, "1) Risk & SL/TP", 1, 0, "#CE93D8")
    f_filters = _h_section(right_stack, "2) Filters", 0, 0, "#29B6F6")
    f_watch_actions = _h_section(right_stack, "3) Watchlist", 1, 0, "#7E57C2")
    f_safety = _h_section(hsimple, "4) Safety", 2, 0, "#FFB300", columnspan=2)
    f_safety.configure(fg_color="#211F17")

    ctk.CTkCheckBox(f_filters, text="Use Signal Filter", variable=var_hedge_signal).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=6)
    ctk.CTkCheckBox(f_filters, text="Use Entry/Exit Filter", variable=var_h_entry_filter).grid(row=1, column=2, columnspan=2, sticky="w", padx=10, pady=6)
    ctk.CTkLabel(f_filters, text="Signal rule").grid(row=2, column=0, sticky="w", padx=10, pady=5)
    cbo_h2_signal_rule = ctk.CTkOptionMenu(f_filters, values=["SANDBOX_SIGNAL"], width=170)
    cbo_h2_signal_rule.set(str(hedge_cfg.get("HEDGE_SIGNAL_RULE", "SANDBOX_SIGNAL")).upper())
    cbo_h2_signal_rule.grid(row=2, column=1, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_filters, text="Entry rule").grid(row=2, column=2, sticky="w", padx=10, pady=5)
    cbo_h2_entry_rule = ctk.CTkOptionMenu(
        f_filters,
        values=["SWING_REJECTION", "SWING_STRUCTURE", "FIB_RETRACE", "PULLBACK_ZONE", "FALLBACK_R"],
        width=190,
    )
    cbo_h2_entry_rule.set(str(hedge_cfg.get("HEDGE_ENTRY_RULE", "SWING_REJECTION")).upper())
    cbo_h2_entry_rule.grid(row=2, column=3, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_filters, text="Entry SL").grid(row=3, column=0, sticky="w", padx=10, pady=5)
    cbo_h2_ee_sl_rule = ctk.CTkOptionMenu(
        f_filters,
        values=["MATCH_ENTRY", "SWING_REJECTION", "SWING_STRUCTURE", "FIB_RETRACE", "PULLBACK_ZONE", "SANDBOX"],
        width=170,
    )
    cbo_h2_ee_sl_rule.set(str(hedge_cfg.get("HEDGE_EE_SL_RULE", "MATCH_ENTRY")).upper().replace("AUTO", "MATCH_ENTRY"))
    cbo_h2_ee_sl_rule.grid(row=3, column=1, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_filters, text="Entry TP").grid(row=3, column=2, sticky="w", padx=10, pady=5)
    cbo_h2_ee_tp_rule = ctk.CTkOptionMenu(
        f_filters,
        values=["MATCH_ENTRY", "RR", "SWING_REJECTION", "SWING_STRUCTURE", "FIB_RETRACE", "PULLBACK_ZONE", "NO_TP"],
        width=190,
    )
    cbo_h2_ee_tp_rule.set(str(hedge_cfg.get("HEDGE_EE_TP_RULE", "MATCH_ENTRY")).upper().replace("AUTO", "MATCH_ENTRY"))
    cbo_h2_ee_tp_rule.grid(row=3, column=3, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(
        f_filters,
        text="Signal chạy trước; Entry/Exit là bộ lọc điểm vào nếu được bật. Rule chọn ở đây là riêng của HEDGE.",
        font=("Arial", 11, "italic"),
        text_color="#B0BEC5",
        wraplength=520,
        justify="left",
    ).grid(row=4, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 8))

    def _h2_entry(parent, label, value, row, col, width=90):
        label_widget = ctk.CTkLabel(parent, text=label)
        label_widget.grid(row=row, column=col, sticky="w", padx=10, pady=5)
        entry = ctk.CTkEntry(parent, width=width, justify="center")
        entry.insert(0, str(value))
        entry.grid(row=row, column=col + 1, sticky="w", padx=10, pady=5)
        entry._label_widget = label_widget
        return entry

    def _h_zone(parent, title, row, color="#90CAF9"):
        ctk.CTkLabel(
            parent,
            text=title,
            font=("Roboto", 11, "bold"),
            text_color=color,
        ).grid(row=row, column=0, columnspan=8, sticky="w", padx=10, pady=(10, 2))

    ctk.CTkCheckBox(f_risk, text="HEDGE SL/TP Rule", variable=var_h_hedge_sltp).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=6)
    ctk.CTkCheckBox(f_risk, text="Use TSL", variable=var_h_tsl).grid(row=1, column=2, columnspan=2, sticky="w", padx=10, pady=6)
    ctk.CTkLabel(f_risk, text="HEDGE SL rule").grid(row=2, column=0, sticky="w", padx=10, pady=5)
    cbo_h2_sl_rule = ctk.CTkOptionMenu(
        f_risk,
        values=["BASE_SL_ATR", "SWING_REJECTION", "SWING_STRUCTURE", "FIB_RETRACE", "PULLBACK_ZONE"],
        width=190,
    )
    cbo_h2_sl_rule.set(str(hedge_cfg.get("HEDGE_SL_RULE", "BASE_SL_ATR")).upper())
    cbo_h2_sl_rule.grid(row=2, column=1, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_risk, text="HEDGE TP rule").grid(row=2, column=2, sticky="w", padx=10, pady=5)
    cbo_h2_tp_rule = ctk.CTkOptionMenu(
        f_risk,
        values=["RR", "SWING", "NO_TP"],
        width=130,
    )
    cbo_h2_tp_rule.set(str(hedge_cfg.get("HEDGE_TP_RULE", "RR")).upper())
    cbo_h2_tp_rule.grid(row=2, column=3, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_risk, text="Lot mode").grid(row=3, column=0, sticky="w", padx=10, pady=5)
    cbo_h2_lot_mode = ctk.CTkOptionMenu(f_risk, values=["FIXED", "ACCOUNT_RISK"], width=140)
    _h2_lot_mode_value = str(hedge_cfg.get("LOT_MODE", "FIXED")).upper()
    cbo_h2_lot_mode.set("ACCOUNT_RISK" if _h2_lot_mode_value == "RISK_PERCENT" else _h2_lot_mode_value)
    cbo_h2_lot_mode.grid(row=3, column=1, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_risk, text="Survivor protect").grid(row=3, column=2, sticky="w", padx=10, pady=5)
    cbo_h2_survivor = ctk.CTkOptionMenu(f_risk, values=["BE_FEE", "BE_ONLY", "OFF"], width=130)
    cbo_h2_survivor.set(str(hedge_cfg.get("SURVIVOR_PROTECT", "BE_FEE")).upper())
    cbo_h2_survivor.grid(row=3, column=3, sticky="w", padx=10, pady=5)
    ctk.CTkLabel(f_risk, text="TSL tactics", text_color="#00E676", font=("Roboto", 12, "bold")).grid(
        row=4, column=0, sticky="w", padx=10, pady=(8, 4)
    )
    _h2_tsl_modes = set(str(hedge_cfg.get("HEDGE_TSL_MODE", "BE+STEP_R+SWING") or "").upper().replace(",", "+").split("+"))
    var_h2_tsl_be = ctk.BooleanVar(value="BE" in _h2_tsl_modes)
    var_h2_tsl_pnl = ctk.BooleanVar(value="PNL" in _h2_tsl_modes)
    var_h2_tsl_step = ctk.BooleanVar(value="STEP_R" in _h2_tsl_modes)
    var_h2_tsl_swing = ctk.BooleanVar(value="SWING" in _h2_tsl_modes)
    var_h2_tsl_cash = ctk.BooleanVar(value="BE_CASH" in _h2_tsl_modes)
    var_h2_tsl_psar = ctk.BooleanVar(value="PSAR_TRAIL" in _h2_tsl_modes)
    _h2_tsl_checks = [
        ("BE", var_h2_tsl_be, 0),
        ("PNL", var_h2_tsl_pnl, 1),
        ("STEP_R", var_h2_tsl_step, 2),
        ("SWING", var_h2_tsl_swing, 3),
        ("BE_CASH", var_h2_tsl_cash, 4),
        ("PSAR_TRAIL", var_h2_tsl_psar, 5),
    ]
    for label, var, idx in _h2_tsl_checks:
        ctk.CTkCheckBox(f_risk, text=label, variable=var, command=lambda: _refresh_hedge_preview()).grid(
            row=5 + idx // 3, column=(idx % 3), columnspan=1, sticky="w", padx=10, pady=5
        )
    e_h2_lot = _h2_entry(f_risk, "Lot per leg", hedge_cfg.get("FIXED_LOT", 0.1), 7, 0)
    e_h2_risk_pct = _h2_entry(f_risk, "Account risk %", hedge_cfg.get("RISK_PERCENT_PER_PAIR", 0.5), 7, 2)
    e_h2_max_lot_cap = _h2_entry(f_risk, "Max lot cap", hedge_cfg.get("MAX_LOT_CAP", 1.0), 8, 0)
    e_h2_max_pairs = _h2_entry(f_risk, "Max pairs/symbol", hedge_cfg.get("MAX_PAIRS_PER_SYMBOL", 1), 8, 2)
    ctk.CTkLabel(
        f_risk,
        text="Hint: HEDGE SL/TP Rule dùng cùng công thức base SL/TP của sandbox/bot (swingpoint + ATR, swing TP hoặc RR TP), nhưng bật/tắt và state là riêng của HEDGE.",
        font=("Arial", 11, "italic"),
        text_color="#F8BBD0",
        wraplength=520,
        justify="left",
    ).grid(row=9, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 8))

    def _compose_h2_tsl_mode():
        if not var_h_tsl.get():
            return "OFF"
        modes = [label for label, var, _idx in _h2_tsl_checks if var.get()]
        return "+".join(modes) if modes else "OFF"

    def _set_entry_active(entry, active=True):
        label_widget = getattr(entry, "_label_widget", None)
        if active:
            if label_widget:
                label_widget.grid()
                label_widget.configure(text_color="#FFFFFF")
            entry.grid()
            entry.configure(state="normal")
        else:
            if label_widget:
                label_widget.grid_remove()
            entry.grid_remove()

    def _refresh_hedge_risk_fields(_value=None):
        lot_mode = str(cbo_h2_lot_mode.get() or "FIXED").upper()
        use_tsl = bool(var_h_tsl.get())
        _set_entry_active(e_h2_lot, lot_mode == "FIXED")
        _set_entry_active(e_h2_risk_pct, lot_mode == "ACCOUNT_RISK")
        try:
            _refresh_hedge_preview()
        except Exception:
            pass

    cbo_h2_lot_mode.configure(command=_refresh_hedge_risk_fields)
    var_h_tsl.trace_add("write", lambda *_: _refresh_hedge_risk_fields())
    _refresh_hedge_risk_fields()

    e_h2_scan_interval = _h2_entry(f_safety, "Auto scan sec", hedge_cfg.get("HEDGE_SCAN_INTERVAL_SECONDS", 2), 1, 0, width=72)
    e_h2_log_cd = _h2_entry(f_safety, "Log cooldown sec", hedge_cfg.get("HEDGE_LOG_COOLDOWN_SECONDS", 300), 1, 2, width=72)
    e_h2_cooldown = _h2_entry(f_safety, "Close cooldown sec", hedge_cfg.get("COOLDOWN_AFTER_CLOSE_SECONDS", 900), 1, 4, width=72)
    e_h2_loss_cooldown = _h2_entry(f_safety, "Loss cooldown sec", hedge_cfg.get("COOLDOWN_AFTER_LOSS_SECONDS", 1800), 1, 6, width=72)
    e_h2_max_losses = _h2_entry(f_safety, "Consecutive losses", hedge_cfg.get("MAX_CONSECUTIVE_LOSSES", 3), 2, 0, width=72)
    e_h2_global_cd = _h2_entry(f_safety, "Global cooldown sec", hedge_cfg.get("GLOBAL_COOLDOWN_SECONDS", 3600), 2, 2, width=72)
    e_h2_daily_loss = _h2_entry(f_safety, "Daily loss HEDGE", hedge_cfg.get("HEDGE_MAX_DAILY_LOSS", 0.0), 2, 4, width=72)
    e_h2_max_day = _h2_entry(f_safety, "Max sessions/day", hedge_cfg.get("MAX_SESSIONS_PER_DAY", 0), 2, 6, width=72)
    e_h2_session_tp = _h2_entry(f_safety, "Session TP USD", hedge_cfg.get("HEDGE_SESSION_TP_USD", 0.0), 3, 0, width=72)
    e_h2_session_sl = _h2_entry(f_safety, "Session SL USD", hedge_cfg.get("HEDGE_SESSION_SL_USD", 0.0), 3, 2, width=72)
    e_h2_max_hold = _h2_entry(f_safety, "Max hold min", hedge_cfg.get("HEDGE_MAX_HOLD_MINUTES", 0), 3, 4, width=72)
    var_h2_check_spread = ctk.BooleanVar(value=bool(hedge_cfg.get("CHECK_SPREAD", True)))
    var_h2_check_ping = ctk.BooleanVar(value=bool(hedge_cfg.get("CHECK_PING", True)))
    ctk.CTkCheckBox(f_safety, text="Check spread", variable=var_h2_check_spread).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=5)
    ctk.CTkCheckBox(f_safety, text="Check ping", variable=var_h2_check_ping).grid(row=4, column=2, columnspan=2, sticky="w", padx=10, pady=5)
    e_h2_max_spread = _h2_entry(f_safety, "Max spread points", hedge_cfg.get("MAX_SPREAD_POINTS", 150), 4, 4, width=72)
    e_h2_max_ping = _h2_entry(f_safety, "Max ping ms", hedge_cfg.get("MAX_PING_MS", 150), 4, 6, width=72)

    def _paint_safety(entry, color):
        label_widget = getattr(entry, "_label_widget", None)
        if label_widget:
            label_widget.configure(text_color=color)
        entry.configure(border_color=color)

    for _entry in (e_h2_scan_interval, e_h2_log_cd, e_h2_cooldown, e_h2_loss_cooldown):
        _paint_safety(_entry, "#64B5F6")
    for _entry in (e_h2_max_losses, e_h2_global_cd, e_h2_daily_loss, e_h2_max_day):
        _paint_safety(_entry, "#FFB300")
    for _entry in (e_h2_session_tp, e_h2_session_sl, e_h2_max_hold):
        _paint_safety(_entry, "#CE93D8")
    for _entry in (e_h2_max_spread, e_h2_max_ping):
        _paint_safety(_entry, "#4DD0E1")
    ctk.CTkLabel(
        f_safety,
        text="Hint: Xanh=runtime/cooldown, vàng=daily brake, tím=session brake, cyan=execution check. Chỉ ghi HEDGE state riêng, không reset BOT/GRID.",
        font=("Arial", 11, "italic"),
        text_color="#FFD54F",
        wraplength=760,
        justify="left",
    ).grid(row=5, column=0, columnspan=8, sticky="w", padx=10, pady=(4, 8))

    watchlist_frame = f_watch_actions
    ctk.CTkLabel(
        watchlist_frame,
        text="Tick symbol Auto HEDGE scan. Manual HEDGE vẫn theo symbol đang chọn.",
        text_color="#F8BBD0",
        font=("Arial", 11, "italic"),
        wraplength=520,
        justify="left",
    ).grid(row=1, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 6))
    hedge_watchlist_vars = {}
    selected_watchlist = set(hedge_cfg.get("WATCHLIST") or [])
    hedge_watchlist_symbols = getattr(config, "COIN_LIST", []) or [getattr(config, "DEFAULT_SYMBOL", "ETHUSD")]
    hedge_action_row = 2 + ((len(hedge_watchlist_symbols) + 3) // 4)
    for idx, sym in enumerate(hedge_watchlist_symbols):
        var = ctk.BooleanVar(value=sym in selected_watchlist)
        hedge_watchlist_vars[sym] = var
        ctk.CTkCheckBox(watchlist_frame, text=sym, variable=var, command=lambda: _refresh_hedge_preview()).grid(
            row=2 + idx // 4,
            column=idx % 4,
            sticky="w",
            padx=10,
            pady=4,
        )

    def _refresh_hedge_preview():
        lbl_hedge_summary.configure(text=_hedge_summary())
        lbl_hedge_preview.configure(text=_hedge_preview_text())

    for _var in (var_hedge_signal, var_h_entry_filter, var_h_hedge_sltp):
        _var.trace_add("write", lambda *_: _refresh_hedge_preview())

    def _hedge_override_has(symbol):
        try:
            from hedge.hedge_storage import load_hedge_settings
            return bool((load_hedge_settings().get("SYMBOL_OVERRIDES") or {}).get(symbol))
        except Exception:
            return False

    def _refresh_hedge_override_button():
        sym = _current_hedge_symbol()
        mark = " *" if _hedge_override_has(sym) else ""
        if hasattr(btn_open_hedge_override, "configure"):
            btn_open_hedge_override.configure(text=f"OVERRIDE {sym}{mark}")

    def _open_hedge_override_popup():
        from ui_hedge_override_popup import open_hedge_override_popup
        open_hedge_override_popup(app, _current_hedge_symbol(), on_close=lambda: (_refresh_hedge_preview(), _refresh_hedge_override_button()))

    def _save_hedge_quick():
        try:
            from hedge.hedge_storage import load_hedge_settings, save_hedge_settings
            cfg = load_hedge_settings()
            cfg["USE_SIGNAL_FILTER"] = var_hedge_signal.get()
            cfg["HEDGE_SIGNAL_RULE"] = cbo_h2_signal_rule.get()
            cfg["USE_ENTRY_EXIT_FILTER"] = var_h_entry_filter.get()
            cfg["HEDGE_ENTRY_RULE"] = cbo_h2_entry_rule.get()
            cfg["HEDGE_EE_SL_RULE"] = cbo_h2_ee_sl_rule.get()
            cfg["HEDGE_EE_TP_RULE"] = cbo_h2_ee_tp_rule.get()
            cfg["USE_HEDGE_SLTP"] = var_h_hedge_sltp.get()
            cfg["HEDGE_SL_RULE"] = cbo_h2_sl_rule.get()
            cfg["HEDGE_TP_RULE"] = cbo_h2_tp_rule.get()
            cfg.pop("USE_SANDBOX_SLTP", None)
            cfg["USE_TSL"] = var_h_tsl.get()
            cfg["HEDGE_TSL_MODE"] = _compose_h2_tsl_mode()
            cfg["SURVIVOR_PROTECT"] = cbo_h2_survivor.get()
            cfg["LOT_MODE"] = cbo_h2_lot_mode.get()
            cfg["FIXED_LOT"] = float(e_h2_lot.get() or 0.1)
            cfg["RISK_PERCENT_PER_PAIR"] = float(e_h2_risk_pct.get() or 0.0)
            cfg["MAX_LOT_CAP"] = float(e_h2_max_lot_cap.get() or 0.0)
            cfg["MAX_PAIRS_PER_SYMBOL"] = int(float(e_h2_max_pairs.get() or 1))
            cfg["COOLDOWN_AFTER_CLOSE_SECONDS"] = int(float(e_h2_cooldown.get() or 0))
            cfg["COOLDOWN_AFTER_LOSS_SECONDS"] = int(float(e_h2_loss_cooldown.get() or 0))
            cfg["MAX_CONSECUTIVE_LOSSES"] = int(float(e_h2_max_losses.get() or 0))
            cfg["GLOBAL_COOLDOWN_SECONDS"] = int(float(e_h2_global_cd.get() or 0))
            cfg["HEDGE_SCAN_INTERVAL_SECONDS"] = max(1, int(float(e_h2_scan_interval.get() or 2)))
            cfg["HEDGE_LOG_COOLDOWN_SECONDS"] = max(0, int(float(e_h2_log_cd.get() or 300)))
            cfg["CHECK_SPREAD"] = var_h2_check_spread.get()
            cfg["MAX_SPREAD_POINTS"] = int(float(e_h2_max_spread.get() or 150))
            cfg["CHECK_PING"] = var_h2_check_ping.get()
            cfg["MAX_PING_MS"] = int(float(e_h2_max_ping.get() or 150))
            cfg["HEDGE_MAX_DAILY_LOSS"] = float(e_h2_daily_loss.get() or 0.0)
            cfg["MAX_SESSIONS_PER_DAY"] = int(float(e_h2_max_day.get() or 0))
            cfg["HEDGE_SESSION_TP_USD"] = float(e_h2_session_tp.get() or 0.0)
            cfg["HEDGE_SESSION_SL_USD"] = float(e_h2_session_sl.get() or 0.0)
            cfg["HEDGE_MAX_HOLD_MINUTES"] = int(float(e_h2_max_hold.get() or 0))
            cfg["WATCHLIST"] = [sym for sym, var in hedge_watchlist_vars.items() if var.get()]
            for old_key in (
                "TACTIC", "USE_SWING_FILTER", "USE_SANDBOX_SLTP", "SWING_GROUP", "SWING_TIMEFRAME", "SWING_TOLERANCE_ATR",
                "SL_TP_MODE", "SL_ATR_BUFFER", "TP_ATR_BUFFER", "BASKET_EXIT_MODE", "PAIR_TP_USD",
                "PAIR_SL_USD", "BASKET_TP_R", "BASKET_SL_R", "BASKET_BUFFER_R",
                "BASKET_TRAIL_START_R", "BASKET_TRAIL_GIVEBACK_R", "LOSING_LEG_SL_USD",
                "RECOVERY_MODE", "RECOVERY_TARGET_USD", "RECOVERY_BUFFER_R", "RECOVERY_GIVEBACK_USD",
                "RECOVERY_FAIL_GUARD", "RECOVERY_FAIL_PULLBACK_USD", "RECOVERY_TSL_MODE",
                "RECOVERY_TSL_ENABLED", "RECOVERY_TSL_START_R", "RECOVERY_TSL_GIVEBACK_R",
                "NO_MOVE_TIMEOUT_SECONDS", "NO_MOVE_MIN_MFE_USD", "MAX_HOLD_SECONDS",
            ):
                cfg.pop(old_key, None)
            save_hedge_settings(cfg)
            _refresh_hedge_preview()
            if hasattr(app, "update_hedge_manual_preview"):
                app.update_hedge_manual_preview()
            if hasattr(app, "log_message"):
                app.log_message("[HEDGE] Quick settings saved.", target="hedge")
        except ValueError:
            messagebox.showerror("HEDGE", "HEDGE quick nhap sai kieu so.", parent=top)

    def _clear_hedge_block():
        mgr = getattr(app, "hedge_mgr", None)
        result = mgr.clear_session_block() if mgr else "FAILED|NO_HEDGE_MANAGER"
        _refresh_hedge_preview()
        if hasattr(app, "log_message"):
            app.log_message(f"[HEDGE] Clear block: {result}", target="hedge")

    def _collect_hedge_quick_values():
        return {
            "USE_SIGNAL_FILTER": var_hedge_signal.get(),
            "HEDGE_SIGNAL_RULE": cbo_h2_signal_rule.get(),
            "USE_ENTRY_EXIT_FILTER": var_h_entry_filter.get(),
            "HEDGE_ENTRY_RULE": cbo_h2_entry_rule.get(),
            "HEDGE_EE_SL_RULE": cbo_h2_ee_sl_rule.get(),
            "HEDGE_EE_TP_RULE": cbo_h2_ee_tp_rule.get(),
            "USE_HEDGE_SLTP": var_h_hedge_sltp.get(),
            "HEDGE_SL_RULE": cbo_h2_sl_rule.get(),
            "HEDGE_TP_RULE": cbo_h2_tp_rule.get(),
            "USE_TSL": var_h_tsl.get(),
            "HEDGE_TSL_MODE": _compose_h2_tsl_mode(),
            "SURVIVOR_PROTECT": cbo_h2_survivor.get(),
            "LOT_MODE": cbo_h2_lot_mode.get(),
            "FIXED_LOT": float(e_h2_lot.get() or 0.1),
            "RISK_PERCENT_PER_PAIR": float(e_h2_risk_pct.get() or 0.0),
            "MAX_LOT_CAP": float(e_h2_max_lot_cap.get() or 0.0),
            "MAX_PAIRS_PER_SYMBOL": int(float(e_h2_max_pairs.get() or 1)),
            "COOLDOWN_AFTER_CLOSE_SECONDS": int(float(e_h2_cooldown.get() or 0)),
            "COOLDOWN_AFTER_LOSS_SECONDS": int(float(e_h2_loss_cooldown.get() or 0)),
            "MAX_CONSECUTIVE_LOSSES": int(float(e_h2_max_losses.get() or 0)),
            "GLOBAL_COOLDOWN_SECONDS": int(float(e_h2_global_cd.get() or 0)),
            "HEDGE_SCAN_INTERVAL_SECONDS": max(1, int(float(e_h2_scan_interval.get() or 2))),
            "HEDGE_LOG_COOLDOWN_SECONDS": max(0, int(float(e_h2_log_cd.get() or 300))),
            "CHECK_SPREAD": var_h2_check_spread.get(),
            "MAX_SPREAD_POINTS": int(float(e_h2_max_spread.get() or 150)),
            "CHECK_PING": var_h2_check_ping.get(),
            "MAX_PING_MS": int(float(e_h2_max_ping.get() or 150)),
            "HEDGE_MAX_DAILY_LOSS": float(e_h2_daily_loss.get() or 0.0),
            "MAX_SESSIONS_PER_DAY": int(float(e_h2_max_day.get() or 0)),
            "HEDGE_SESSION_TP_USD": float(e_h2_session_tp.get() or 0.0),
            "HEDGE_SESSION_SL_USD": float(e_h2_session_sl.get() or 0.0),
            "HEDGE_MAX_HOLD_MINUTES": int(float(e_h2_max_hold.get() or 0)),
        }

    hedge_preview_form_getter = _collect_hedge_quick_values

    def _save_hedge_override():
        try:
            from hedge.hedge_storage import load_hedge_settings, save_hedge_settings

            sym = _current_hedge_symbol()
            cfg = load_hedge_settings()
            cfg.setdefault("SYMBOL_OVERRIDES", {})[sym] = _collect_hedge_quick_values()
            save_hedge_settings(cfg)
            var_hedge_override.set(True)
            _refresh_hedge_preview()
            if hasattr(app, "log_message"):
                app.log_message(f"[HEDGE] Override saved for {sym}.", target="hedge")
        except ValueError:
            messagebox.showerror("HEDGE", "Override nhap sai kieu so.", parent=top)

    def _clear_hedge_override():
        from hedge.hedge_storage import load_hedge_settings, save_hedge_settings

        sym = _current_hedge_symbol()
        cfg = load_hedge_settings()
        cfg.setdefault("SYMBOL_OVERRIDES", {}).pop(sym, None)
        save_hedge_settings(cfg)
        var_hedge_override.set(False)
        _refresh_hedge_preview()
        if hasattr(app, "log_message"):
            app.log_message(f"[HEDGE] Override cleared for {sym}.", target="hedge")

    btn_open_hedge_override.configure(command=_open_hedge_override_popup, state="normal")
    btn_save_hedge_settings.configure(command=_save_hedge_quick, state="normal")
    btn_clear_hedge_cooldown.configure(command=_clear_hedge_block, state="normal")
    _refresh_hedge_override_button()
    ctk.CTkLabel(
        tab_backtest,
        text="BACKTEST module placeholder. This tab is reserved for historical GRID simulation.",
        font=("Arial", 13, "italic"),
        text_color="#BDBDBD",
        wraplength=680,
    ).pack(fill="x", padx=14, pady=18)

def open_preset_config_popup(app):

    p_name = app.cbo_preset.get()
    data = config.PRESETS.get(p_name, {})
    top = ctk.CTkToplevel(app)
    top.title(f"Preset: {p_name}")
    top.geometry("540x780")
    top.minsize(500, 520)
    _bring_popup_to_front(top)
    # top.transient(app)
    body = _speed_up_scroll(ctk.CTkScrollableFrame(top, fg_color="transparent"))
    body.pack(fill="both", expand=True, padx=10, pady=(10, 4))
    acc = app.connector.get_account_info()
    eq = acc["equity"] if acc else 1000.0
    tick = app.connector.get_market_status(app.cbo_symbol.get())
    cp = tick.get("ask", 1000.0) if isinstance(tick, dict) else 1000.0
    ctk.CTkLabel(body, text=f"PRESET: {p_name}", font=FONT_BOLD).pack(pady=10)
    _add_popup_hint(
        body,
        "- Preset này dùng cho lệnh manual theo preset đang chọn.\n"
        "- Manual input ngoài panel luôn ưu tiên hơn preset.\n"
        "- Preset chỉ định rule riêng cho SL và TP manual: Percent/RR hoặc SwingPoint.",
        padx=20,
        pady=(0, 10),
        wraplength=470,
    )
    ctk.CTkLabel(body, text="Risk Per Trade (%):").pack()
    e_risk = ctk.CTkEntry(body, justify="center")
    e_risk.insert(0, str(data.get("RISK_PERCENT", 0.3)))
    e_risk.pack()
    lbl_h_risk = ctk.CTkLabel(
        body, text="~ -$0.00", text_color="#CFD8DC", font=("Roboto", 11)
    )
    lbl_h_risk.pack(pady=(0, 5))
    ctk.CTkLabel(body, text="Stop Loss (%):").pack()
    e_sl = ctk.CTkEntry(body, justify="center")
    e_sl.insert(0, str(data.get("SL_PERCENT", 0.5)))
    e_sl.pack()
    lbl_h_sl = ctk.CTkLabel(
        body, text="~ Price: 0.00", text_color="#CFD8DC", font=("Roboto", 11)
    )
    lbl_h_sl.pack(pady=(0, 5))
    ctk.CTkLabel(body, text="Take Profit (RR):").pack()
    e_tp = ctk.CTkEntry(body, justify="center")
    e_tp.insert(0, str(data.get("TP_RR_RATIO", 2.0)))
    e_tp.pack()
    lbl_h_tp = ctk.CTkLabel(
        body, text="~ +$0.00", text_color="#CFD8DC", font=("Roboto", 11)
    )
    lbl_h_tp.pack(pady=(0, 10))

    # [NEW] Thêm Checkbox Strict Risk (Tính phí Spread/Comm)
    var_strict = ctk.BooleanVar(value=data.get("STRICT_RISK", False))
    chk_strict = ctk.CTkCheckBox(
        body,
        text="Strict Risk: lot đã trừ spread/comm",
        variable=var_strict,
        text_color="#FF6E66",
        font=("Roboto", 12, "bold"),
    )
    chk_strict.pack(pady=(5, 10))

    # --- Manual SL/TP rules ---
    sl_mode_default = str(data.get("MANUAL_SL_MODE") or ("SWING" if data.get("USE_SWING_SL", False) else "PERCENT")).upper()
    tp_mode_default = str(data.get("MANUAL_TP_MODE") or ("SWING" if data.get("USE_SWING_TP", False) else "RR")).upper()
    _manual_mode_display = {
        "PERCENT": "Percent",
        "SANDBOX": "SL Sandbox",
        "RR": "RR",
        "OFF": "OFF",
        "NO_TP": "OFF",
        "SWING": "Swing Retest",
        "SWING_REJECTION": "Swing Retest",
        "SWING_RETEST": "Swing Retest",
        "SWING_STRUCTURE": "Swing Struct",
        "SWING_STRUCT": "Swing Struct",
        "FIB": "FIB",
        "PULLBACK": "Pullback",
        "PULLBACK_ZONE": "Pullback",
    }
    var_manual_sl_mode = tk.StringVar(value=_manual_mode_display.get(sl_mode_default, "Percent"))
    var_manual_tp_mode = tk.StringVar(value=_manual_mode_display.get(tp_mode_default, "RR"))
    var_swing_sl = ctk.BooleanVar(value="SWING" in sl_mode_default)
    var_manual_sl_group = tk.StringVar(value=data.get("MANUAL_SL_GROUP", data.get("MANUAL_SWING_SL_GROUP", "G2")))
    var_manual_sl_buffer = tk.StringVar(value=str(data.get("MANUAL_SWING_SL_ATR_MULT", getattr(config, "sl_atr_multiplier", 0.2))))
    var_swing_tp = ctk.BooleanVar(value="SWING" in tp_mode_default)
    var_manual_tp_group = tk.StringVar(value=data.get("MANUAL_TP_GROUP", data.get("MANUAL_SWING_TP_GROUP", data.get("MANUAL_SWING_SL_GROUP", "G2"))))

    f_sl_rule = ctk.CTkFrame(
        body,
        fg_color="#142124",
        corner_radius=8,
        border_width=1,
        border_color="#37565C",
    )
    f_sl_rule.pack(fill="x", padx=20, pady=(0, 10))
    ctk.CTkLabel(
        f_sl_rule,
        text="Manual SL Rule",
        font=("Roboto", 13, "bold"),
        text_color="#FFB3AD",
    ).pack(anchor="w", padx=14, pady=(10, 4))
    f_manual_sl_group = ctk.CTkFrame(f_sl_rule, fg_color="transparent")
    f_manual_sl_group.pack(fill="x", padx=14, pady=(0, 12))
    ctk.CTkLabel(
        f_manual_sl_group,
        text="Mode:",
        width=82,
        anchor="w",
        text_color="#D9EEF2",
    ).pack(side="left")
    ctk.CTkOptionMenu(
        f_manual_sl_group,
        values=["Percent", "SL Sandbox", "Swing Retest", "Swing Struct", "FIB", "Pullback"],
        variable=var_manual_sl_mode,
        width=140,
        command=lambda v: var_swing_sl.set("Swing" in v),
    ).pack(side="left", padx=(0, 8))
    ctk.CTkLabel(
        f_manual_sl_group,
        text="Group:",
        width=54,
        anchor="w",
        text_color="#D9EEF2",
    ).pack(side="left")
    ctk.CTkOptionMenu(
        f_manual_sl_group,
        values=["G0", "G1", "G2", "G3", "DYNAMIC"],
        variable=var_manual_sl_group,
        width=90,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkLabel(
        f_manual_sl_group,
        text="Buffer:",
        width=58,
        anchor="w",
        text_color="#D9EEF2",
    ).pack(side="left")
    ctk.CTkEntry(f_manual_sl_group, textvariable=var_manual_sl_buffer, width=58, justify="center").pack(side="left")

    f_tp_rule = ctk.CTkFrame(
        body,
        fg_color="#142124",
        corner_radius=8,
        border_width=1,
        border_color="#37565C",
    )
    f_tp_rule.pack(fill="x", padx=20, pady=(0, 12))
    ctk.CTkLabel(
        f_tp_rule,
        text="Manual Exit Target Rule",
        font=("Roboto", 13, "bold"),
        text_color="#9AFFC4",
    ).pack(anchor="w", padx=14, pady=(10, 4))
    f_manual_tp_group = ctk.CTkFrame(f_tp_rule, fg_color="transparent")
    f_manual_tp_group.pack(fill="x", padx=14, pady=(0, 12))
    ctk.CTkLabel(
        f_manual_tp_group,
        text="Mode:",
        width=82,
        anchor="w",
        text_color="#D9EEF2",
    ).pack(side="left")
    ctk.CTkOptionMenu(
        f_manual_tp_group,
        values=["OFF", "RR", "Swing Retest", "Swing Struct", "FIB", "Pullback"],
        variable=var_manual_tp_mode,
        width=140,
        command=lambda v: var_swing_tp.set("Swing" in v),
    ).pack(side="left", padx=(0, 8))
    ctk.CTkLabel(
        f_manual_tp_group,
        text="Group:",
        width=54,
        anchor="w",
        text_color="#D9EEF2",
    ).pack(side="left")
    ctk.CTkOptionMenu(
        f_manual_tp_group,
        values=["G0", "G1", "G2", "G3", "DYNAMIC"],
        variable=var_manual_tp_group,
        width=90,
    ).pack(side="left", padx=(0, 8))
    def live(*args):
        try:
            r, s, t = (
                float(e_risk.get() or 0),
                float(e_sl.get() or 0),
                float(e_tp.get() or 0),
            )
            risk_usd = eq * (r / 100)
            lbl_h_risk.configure(
                text=f"(~ Mất ${risk_usd:.2f} nếu dính SL)", text_color="#EF5350"
            )
            lbl_h_sl.configure(
                text=f"(~ Đặt SL quanh {cp * (1 - s / 100):.2f} cho BUY)",
                text_color="#CFD8DC",
            )
            lbl_h_tp.configure(
                text=f"(~ Lãi ${risk_usd * t:.2f} nếu chạm TP)", text_color="#66BB6A"
            )
        except ValueError:
            pass
    e_risk.bind("<KeyRelease>", live)
    e_sl.bind("<KeyRelease>", live)
    e_tp.bind("<KeyRelease>", live)
    live()

    def save_preset():
        sl_raw = str(var_manual_sl_mode.get() or "Percent").upper()
        tp_raw = str(var_manual_tp_mode.get() or "RR").upper()
        sl_mode = (
            "SWING_STRUCTURE" if "STRUCT" in sl_raw
            else "SWING_REJECTION" if "RETEST" in sl_raw
            else "SANDBOX" if "SANDBOX" in sl_raw
            else "FIB" if "FIB" in sl_raw
            else "PULLBACK" if "PULL" in sl_raw
            else "PERCENT"
        )
        tp_mode = (
            "OFF" if "OFF" in tp_raw
            else "SWING_STRUCTURE" if "STRUCT" in tp_raw
            else "SWING_REJECTION" if "RETEST" in tp_raw
            else "FIB" if "FIB" in tp_raw
            else "PULLBACK" if "PULL" in tp_raw
            else "RR"
        )
        config.PRESETS[p_name].update(
            {
                "RISK_PERCENT": float(e_risk.get()),
                "SL_PERCENT": float(e_sl.get()),
                "TP_RR_RATIO": float(e_tp.get()),
                "STRICT_RISK": var_strict.get(),
                "MANUAL_SL_MODE": sl_mode,
                "MANUAL_TP_MODE": tp_mode,
                "USE_SWING_SL": sl_mode in ("SWING_REJECTION", "SWING_STRUCTURE"),
                "USE_SWING_TP": tp_mode in ("SWING_REJECTION", "SWING_STRUCTURE"),
                "MANUAL_SL_GROUP": var_manual_sl_group.get() or "G2",
                "MANUAL_TP_GROUP": var_manual_tp_group.get() or "G2",
                "MANUAL_SWING_SL_GROUP": var_manual_sl_group.get() or "G2",
                "MANUAL_SWING_TP_GROUP": var_manual_tp_group.get() or "G2",
                "MANUAL_SWING_SL_ATR_MULT": float(var_manual_sl_buffer.get() or 0.2),
            }
        )
        app.save_settings()
        if hasattr(app, "var_preview_sl_group"):
            display = var_manual_sl_group.get() or "G2"
            app.var_preview_sl_group.set(display)
        if hasattr(app, "var_preview_tp_group"):
            display = var_manual_tp_group.get() or "G2"
            app.var_preview_tp_group.set(display)
        if hasattr(app, "var_preview_sl_mode"):
            app.var_preview_sl_mode.set(_manual_mode_display.get(sl_mode, "Percent"))
        if hasattr(app, "var_preview_tp_mode"):
            app.var_preview_tp_mode.set(_manual_mode_display.get(tp_mode, "RR"))
        app.refresh_manual_preview_tab()
        top.destroy()
    ctk.CTkButton(top, text="LƯU PRESET", command=save_preset, fg_color=COL_GREEN).pack(
        pady=20, fill="x", padx=30
    )

# ==============================================================================

# 3. POPUP TSL (CÓ BE SOFT/SMART, PNL LEVELS +, STEP R)

# ==============================================================================


def open_tsl_popup(app, override_symbol=None):

    top = ctk.CTkToplevel(app)
    title = "TSL Logic Configuration"
    if override_symbol:
        title += f" - CẤU HÌNH CON: {override_symbol}"
    top.title(title)
    top.geometry("980x780")
    top.minsize(860, 600)
    _bring_popup_to_front(top)
    top.resizable(True, True)  # Khôi phục tính năng co giãn/phóng to
    if override_symbol:
        top.grab_set()  # Modal: Không cho chạm vào UI mẹ khi đang chỉnh UI con
    tsl_cfg = config.TSL_CONFIG.copy()
    tsl_logic_mode = getattr(config, "TSL_LOGIC_MODE", "STATIC")
    if override_symbol:
        from core.storage_manager import get_brain_settings_for_symbol
        brain = get_brain_settings_for_symbol(override_symbol)
        if "TSL_CONFIG" in brain:
            tsl_cfg.update(brain["TSL_CONFIG"])
        tsl_logic_mode = brain.get("TSL_LOGIC_MODE", tsl_logic_mode)

    # [FIX V4.4] CHIA LÀM 2 TAB GỌN GÀNG THEO YÊU CẦU CỦA BOSS
    tabview = ctk.CTkTabview(top, height=620)
    try:
        tabview.configure(
            fg_color="#181818",
            border_width=1,
            border_color="#7B1FA2",
            segmented_button_fg_color="#2A2A2A",
            segmented_button_selected_color="#1f538d",
            segmented_button_selected_hover_color="#14375e",
            segmented_button_unselected_color="#3A3A3A",
            segmented_button_unselected_hover_color="#4A4A4A",
            text_color="#F3E5F5",
        )
    except Exception:
        pass
    tabview.pack(fill="both", expand=True, padx=10, pady=5)
    tab_basic_root = tabview.add("Basic (BE, PNL, STEP)")
    tab_adv_root = tabview.add("Advanced (CASH, PSAR)")
    tab_basic = _speed_up_scroll(ctk.CTkScrollableFrame(tab_basic_root, fg_color="transparent"))
    tab_basic.pack(fill="both", expand=True, padx=4, pady=4)
    tab_adv = _speed_up_scroll(ctk.CTkScrollableFrame(tab_adv_root, fg_color="transparent"))
    tab_adv.pack(fill="both", expand=True, padx=4, pady=4)
    if not override_symbol:
        tab_ow = tabview.add("Overwrite (Mẹ-Con)")
        # OVERRIDE OVERVIEW
        f_overview = ctk.CTkFrame(tab_ow, fg_color="#2b2b2b", corner_radius=8)
        f_overview.pack(fill="x", padx=15, pady=8)
        ctk.CTkLabel(
            f_overview,
            text="OVERRIDE OVERVIEW",
            font=("Roboto", 13, "bold"),
            text_color="#00B8D4",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(8, 6))
        ctk.CTkLabel(
            f_overview, text="Symbol", font=("Roboto", 11, "bold"), text_color="#D7DCE2"
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))
        ctk.CTkLabel(
            f_overview, text="Status", font=("Roboto", 11, "bold"), text_color="#D7DCE2"
        ).grid(row=1, column=1, sticky="w", padx=12, pady=(0, 4))
        f_overview_rows = ctk.CTkFrame(f_overview, fg_color="transparent")
        f_overview_rows.grid(
            row=2, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 8)
        )

        def load_tsl_for_sym(sym):
            open_tsl_popup(app, override_symbol=sym)

        def reset_tsl_for_sym(sym):
            from core.storage_manager import (
                load_symbol_overrides,
                save_symbol_overrides,
            )
            overrides = load_symbol_overrides()
            if sym in overrides and "tsl" in overrides[sym]:
                del overrides[sym]["tsl"]
                save_symbol_overrides(overrides)
                if hasattr(app, "log_message"):
                    app.log_message(
                        f"✅ Đã reset TSL Override cho {sym}.", target="bot"
                    )
                refresh_tsl_override_overview()

    def sec(parent, t):
        color = "#03A9F4"
        upper_t = str(t).upper()
        if "BREAK" in upper_t or "BE_" in upper_t:
            color = "#00E676"
        elif "PNL" in upper_t:
            color = "#FFD600"
        elif "STEP" in upper_t:
            color = "#29B6F6"
        elif "CASH" in upper_t:
            color = "#AB47BC"
        elif "PSAR" in upper_t or "MFE" in upper_t or "HARD" in upper_t:
            color = "#FFB300"
        frame = ctk.CTkFrame(parent, fg_color="#202020", corner_radius=8, border_width=1, border_color=color)
        ctk.CTkLabel(
            frame,
            text=t,
            font=("Roboto", 12, "bold"),
            text_color=color,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(8, 6))
        return frame

    def compact_entry(entry):
        try:
            entry.configure(fg_color="#2F3336", border_color="#56616A", justify="center")
        except Exception:
            pass
        return entry

    def compact_menu(menu):
        try:
            menu.configure(
                fg_color="#1f538d",
                button_color="#14375e",
                button_hover_color="#0D47A1",
                text_color="#FFFFFF",
            )
        except Exception:
            pass
        return menu

    def field(parent, row, col, label, widget, label_color="#FFFFFF"):
        parent.grid_columnconfigure(col * 2, weight=0)
        parent.grid_columnconfigure(col * 2 + 1, weight=1)
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=label_color,
            anchor="w",
        ).grid(row=row, column=col * 2, sticky="w", padx=(12, 6), pady=6)
        widget.grid(row=row, column=col * 2 + 1, sticky="w", padx=(0, 16), pady=6)
        return widget

    def hint_label(parent, text, wrap=820):
        ctk.CTkLabel(
            parent,
            text=text,
            text_color="#B0BEC5",
            font=("Arial", 11, "italic"),
            wraplength=wrap,
            justify="left",
            anchor="w",
        ).grid(
            row=99, column=0, columnspan=8, sticky="ew", padx=12, pady=(4, 10)
        )

    # ================= TAB 1: BASIC =================
    _add_popup_hint(
        tab_basic,
        "- BE_SL là loss-side guard: âm tới trigger R thì kéo SL sát giá theo step R.\n"
        "- PNL Levels khóa lãi theo % win; STEP R bám theo từng bậc R.\n"
        "- Chỉ tactic được bật ở lệnh/Bot TSL mới dùng các tham số này.",
        padx=15,
        pady=(10, 5),
        wraplength=820,
    )
    f_be = sec(tab_basic, "1. BREAK-EVEN SL (BE_SL)")
    f_be.pack(fill="x", padx=15, pady=(8, 8))
    f_be_r1 = ctk.CTkFrame(f_be, fg_color="transparent")
    f_be_r1.pack(fill="x")
    f_be_r2 = ctk.CTkFrame(f_be, fg_color="transparent")
    f_be_r2.pack(fill="x", pady=(5, 0))
    f_be_r3 = ctk.CTkFrame(f_be, fg_color="transparent")
    f_be_r3.pack(fill="x", pady=(5, 0))
    ctk.CTkLabel(
        f_be_r1, text="BE Loss Guard", text_color="#00B8D4", font=("Roboto", 12, "bold")
    ).pack(side="left", padx=5)
    cbo_be_sl_unit = ctk.CTkOptionMenu(
        f_be_r1, values=["R", "USD", "PERCENT", "POINT"], width=90
    )
    cbo_be_sl_unit.set(tsl_cfg.get("BE_SL_LOSS_UNIT", "R"))
    cbo_be_sl_unit.pack(side="left", padx=5)
    ctk.CTkLabel(f_be_r1, text="Loss Trig:").pack(side="left", padx=(8, 2))
    e_be_sl_loss_trigger = ctk.CTkEntry(f_be_r1, width=55)
    e_be_sl_loss_trigger.insert(0, str(tsl_cfg.get("BE_SL_LOSS_TRIGGER", 0.5)))
    e_be_sl_loss_trigger.pack(side="left", padx=(5, 10))
    ctk.CTkLabel(f_be_r1, text="Step:").pack(side="left", padx=(8, 2))
    e_be_sl_loss_step = ctk.CTkEntry(f_be_r1, width=55)
    e_be_sl_loss_step.insert(0, str(tsl_cfg.get("BE_SL_LOSS_STEP", 0.15)))
    e_be_sl_loss_step.pack(side="left", padx=(5, 10))
    ctk.CTkLabel(f_be_r1, text="Guard Buf:").pack(side="left", padx=(8, 2))
    e_be_sl_guard_buffer = ctk.CTkEntry(f_be_r1, width=55)
    e_be_sl_guard_buffer.insert(0, str(tsl_cfg.get("BE_SL_GUARD_BUFFER", 0.075)))
    e_be_sl_guard_buffer.pack(side="left", padx=(5, 10))
    ctk.CTkLabel(f_be_r2, text="Re-entry Lock(s):").pack(side="left", padx=(8, 2))
    e_be_sl_reentry_lock = ctk.CTkEntry(f_be_r2, width=80)
    e_be_sl_reentry_lock.insert(0, str(tsl_cfg.get("BE_SL_REENTRY_LOCK_SEC", 1800)))
    e_be_sl_reentry_lock.pack(side="left", padx=(5, 10))
    ctk.CTkLabel(
        f_be_r3,
        text="RECOVERY_GUARD: âm tới Loss Trig thì arm; hồi lên đủ Step thì đặt virtual guard dưới mức hồi tốt nhất theo Guard Buf. Hồi tiếp thì guard nâng lên; thủng guard thì bot close và khóa vào lại.",
        text_color="#B0BEC5",
        font=("Arial", 11, "italic"),
        wraplength=620,
    ).pack(side="left", padx=5)
    try:
        for row_frame in (f_be_r1, f_be_r2, f_be_r3):
            row_frame.pack_forget()
            for child in row_frame.winfo_children():
                child.pack_forget()
        f_be_r1.pack(fill="x", padx=8)
        f_be_r2.pack(fill="x", padx=8)
        f_be_r3.pack(fill="x", padx=12, pady=(0, 10))
        compact_menu(cbo_be_sl_unit)
        compact_entry(e_be_sl_loss_trigger)
        compact_entry(e_be_sl_loss_step)
        compact_entry(e_be_sl_guard_buffer)
        compact_entry(e_be_sl_reentry_lock)
        field(f_be_r1, 0, 0, "BE Loss Guard", cbo_be_sl_unit, "#00B8D4")
        field(f_be_r1, 0, 1, "Loss Trig", e_be_sl_loss_trigger)
        field(f_be_r1, 0, 2, "Step", e_be_sl_loss_step)
        field(f_be_r1, 0, 3, "Guard Buf", e_be_sl_guard_buffer)
        field(f_be_r2, 0, 0, "Re-entry Lock(s)", e_be_sl_reentry_lock)
        ctk.CTkLabel(
            f_be_r3,
            text="RECOVERY_GUARD: âm tới Loss Trig thì arm; hồi lên đủ Step thì đặt virtual guard dưới mức hồi tốt nhất theo Guard Buf. Hồi tiếp thì guard nâng lên; thủng guard thì bot close và khóa vào lại.",
            text_color="#B0BEC5",
            font=("Arial", 11, "italic"),
            wraplength=820,
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
    except Exception:
        pass
    f_pnl = sec(tab_basic, "2. KHÓA LÃI PNL (LEVELS)")
    f_pnl.pack(fill="x", padx=15, pady=(0, 8))
    scroll_pnl = _speed_up_scroll(ctk.CTkScrollableFrame(f_pnl, height=125, fg_color="#181818"))
    scroll_pnl.pack(fill="x", padx=10, pady=(0, 6))
    scroll_pnl.grid_columnconfigure(0, weight=1)
    pnl_entries = []

    def add_p(v1=0.0, v2=0.0):
        r = ctk.CTkFrame(scroll_pnl, fg_color="transparent")
        r.pack(fill="x", pady=2)
        e1, e2 = compact_entry(ctk.CTkEntry(r, width=70)), compact_entry(ctk.CTkEntry(r, width=70))
        e1.insert(0, str(v1))
        e1.pack(side="left", padx=(6, 8), pady=3)
        ctk.CTkLabel(r, text="% Win -> Lock %", width=130, anchor="w").pack(side="left", padx=5)
        e2.insert(0, str(v2))
        e2.pack(side="left", padx=(8, 6), pady=3)
        pnl_entries.append((r, e1, e2))
    for lvl in tsl_cfg.get("PNL_LEVELS", []):
        add_p(lvl[0], lvl[1])
    f_pbtns = ctk.CTkFrame(f_pnl, fg_color="transparent")
    f_pbtns.pack(fill="x", padx=10, pady=(0, 10))
    ctk.CTkButton(f_pbtns, text="+", width=44, height=28, command=lambda: add_p(0.0, 0.0)).pack(
        side="left", padx=5
    )
    ctk.CTkButton(
        f_pbtns,
        text="-",
        width=40,
        height=28,
        command=lambda: pnl_entries.pop()[0].destroy() if pnl_entries else None,
    ).pack(side="left", padx=5)
    f_step = sec(tab_basic, "3. STEP R (TRAIL)")
    f_step.pack(fill="x", padx=15, pady=(0, 8))
    f_step_row = ctk.CTkFrame(f_step, fg_color="transparent")
    f_step_row.pack(fill="x", padx=8, pady=(0, 10))
    e_sz = compact_entry(ctk.CTkEntry(f_step_row, width=70))
    e_sz.insert(0, str(tsl_cfg.get("STEP_R_SIZE", 1.0)))
    field(f_step_row, 0, 0, "Size(R)", e_sz)
    e_rt = compact_entry(ctk.CTkEntry(f_step_row, width=70))
    e_rt.insert(0, str(tsl_cfg.get("STEP_R_RATIO", 0.8)))
    field(f_step_row, 0, 1, "Lock(0-1)", e_rt)

    # ================= TAB 2: ADVANCED =================
    _add_popup_hint(
        tab_adv,
        "- Swing/PSAR dùng group được chọn để bám cấu trúc giá.\n"
        "- CASH trail khóa lãi theo USD/Percent/Point; One-Time chỉ khóa một lần.\n"
        "- ANTI CASH giữ tên cũ nhưng có thêm MAE/MFE theo từng ticket.\n"
        "- MAE = âm sâu nhất của ticket; MFE = lời cao nhất của ticket.\n"
        "- Hard Stop là cầu dao lỗ; MFE Giveback chống trả lại lợi nhuận.",
        padx=15,
        pady=(10, 5),
        wraplength=820,
    )
    f_swing_man = sec(tab_adv, "4. MANUAL SWING (Bám nến)")
    f_swing_man.pack(fill="x", padx=15)
    cbo_swing_grp = ctk.CTkOptionMenu(
        f_swing_man, values=["G0", "G1", "G2", "G3", "DYNAMIC-G1/G2"], width=100
    )
    cbo_swing_grp.set(tsl_cfg.get("SWING_GROUP", "G2"))
    cbo_swing_grp.pack(side="right")
    ctk.CTkLabel(f_swing_man, text="Group Theo Dõi:").pack(side="left")
    f_swing_logic = ctk.CTkFrame(f_swing_man, fg_color="transparent")
    f_swing_logic.pack(fill="x", pady=(8, 4))
    ctk.CTkLabel(f_swing_logic, text="Swing TSL Logic Mode:").pack(side="left", padx=5)
    cbo_tsl_logic_mode = ctk.CTkOptionMenu(
        f_swing_logic,
        values=["STATIC", "DYNAMIC", "AGGRESSIVE"],
        width=140,
    )
    cbo_tsl_logic_mode.set(tsl_logic_mode)
    cbo_tsl_logic_mode.pack(side="left", padx=8)
    ctk.CTkLabel(
        f_swing_man,
        text=(
            "Chỉ dùng cho TSL tactic SWING sau khi lệnh đã mở. "
            "Không liên quan tới SL ban đầu của bot/manual theo Swing + ATR buffer. "
            "STATIC giữ mốc swing, DYNAMIC/AGGRESSIVE bám đuôi chủ động hơn."
        ),
        text_color="#B0BEC5",
        font=("Arial", 11, "italic"),
        wraplength=620,
        justify="left",
    ).pack(anchor="w", padx=5, pady=(0, 5))
    f_cash = sec(tab_adv, "5. BE HARD CASH (Thang cuốn USD/Point/%/R)")
    f_cash.pack(fill="x", padx=15, pady=(0, 8))
    f_cash_r1 = ctk.CTkFrame(f_cash, fg_color="transparent")
    f_cash_r1.pack(fill="x")
    f_cash_r2 = ctk.CTkFrame(f_cash, fg_color="transparent")
    f_cash_r2.pack(fill="x", pady=(5, 0))
    f_cash_r3 = ctk.CTkFrame(f_cash, fg_color="transparent")
    f_cash_r3.pack(fill="x", pady=(5, 0))
    cbo_cash_type = ctk.CTkOptionMenu(
        f_cash_r1, values=["USD", "PERCENT", "POINT", "R"], width=80
    )
    cbo_cash_type.set(tsl_cfg.get("BE_CASH_TYPE", "USD"))
    cbo_cash_type.pack(side="left", padx=5)
    lbl_cash_trig = ctk.CTkLabel(f_cash_r1, text="Trig:")
    lbl_cash_trig.pack(side="left", padx=2)
    e_cash_trig = ctk.CTkEntry(f_cash_r1, width=50)
    e_cash_trig.insert(0, str(tsl_cfg.get("BE_TRIGGER", 10.0)))
    e_cash_trig.pack(side="left", padx=2)
    lbl_cash_step = ctk.CTkLabel(f_cash_r1, text="Step:")
    lbl_cash_step.pack(side="left", padx=2)
    e_cash_val = ctk.CTkEntry(f_cash_r1, width=50)
    e_cash_val.insert(0, str(tsl_cfg.get("BE_VALUE", 20.0)))
    e_cash_val.pack(side="left", padx=2)
    cbo_cash_strat = ctk.CTkOptionMenu(
        f_cash_r1,
        values=["TRAILING (Gap)", "LOCK (Tight)", "SOFT LOCK (Buffer)"],
        width=145,
    )
    cbo_cash_strat.set(tsl_cfg.get("BE_CASH_STRAT", "TRAILING (Gap)"))
    cbo_cash_strat.pack(side="left", padx=5)
    var_cash_fee_protect = ctk.BooleanVar(
        value=tsl_cfg.get("BE_CASH_FEE_PROTECT", True)
    )
    chk_cash_fee = ctk.CTkCheckBox(
        f_cash_r2, text="Fee Protect", variable=var_cash_fee_protect, width=60
    )
    chk_cash_fee.pack(side="left", padx=5)
    var_be_one_time = ctk.BooleanVar(value=tsl_cfg.get("ONE_TIME_BE", False))
    chk_be_one_time = ctk.CTkCheckBox(
        f_cash_r2, text="One-Time (Chỉ khóa mốc 1)", variable=var_be_one_time, width=60
    )
    chk_be_one_time.pack(side="left", padx=5)
    lbl_cash_buffer = ctk.CTkLabel(f_cash_r3, text="Buffer:")
    lbl_cash_buffer.pack(side="left", padx=2)
    cbo_cash_buffer_type = ctk.CTkOptionMenu(
        f_cash_r3, values=["USD", "PERCENT", "POINT", "ATR", "R"], width=90
    )
    cbo_cash_buffer_type.set(tsl_cfg.get("BE_CASH_SOFT_BUFFER_TYPE", "USD"))
    cbo_cash_buffer_type.pack(side="left", padx=2)
    e_cash_buffer = ctk.CTkEntry(f_cash_r3, width=55)
    e_cash_buffer.insert(0, str(tsl_cfg.get("BE_CASH_SOFT_BUFFER", 3.0)))
    e_cash_buffer.pack(side="left", padx=2)
    lbl_cash_min_lock = ctk.CTkLabel(f_cash_r3, text="Min Lock:")
    lbl_cash_min_lock.pack(side="left", padx=(10, 2))
    e_cash_min_lock = ctk.CTkEntry(f_cash_r3, width=55)
    e_cash_min_lock.insert(0, str(tsl_cfg.get("BE_CASH_MIN_LOCK", 0.0)))
    e_cash_min_lock.pack(side="left", padx=2)
    lbl_cash_help = ctk.CTkLabel(
        f_cash,
        text="SOFT LOCK: khóa = target - buffer; Min Lock là sàn khóa tối thiểu nếu kết quả còn dương.",
        text_color="#B0BEC5",
        font=("Arial", 11, "italic"),
        wraplength=820,
    )
    lbl_cash_help.pack(anchor="w", padx=8, pady=(4, 0))
    try:
        for row_frame in (f_cash_r1, f_cash_r2, f_cash_r3):
            for child in row_frame.winfo_children():
                child.pack_forget()
            row_frame.grid_columnconfigure(9, weight=1)
        lbl_cash_help.pack_forget()
        compact_menu(cbo_cash_type)
        compact_menu(cbo_cash_strat)
        compact_menu(cbo_cash_buffer_type)
        compact_entry(e_cash_trig)
        compact_entry(e_cash_val)
        compact_entry(e_cash_buffer)
        compact_entry(e_cash_min_lock)
        ctk.CTkLabel(f_cash_r1, text="Unit:", text_color="#B0BEC5").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=5)
        cbo_cash_type.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=5)
        lbl_cash_trig.grid(row=0, column=2, sticky="w", padx=(0, 4), pady=5)
        e_cash_trig.grid(row=0, column=3, sticky="w", padx=(0, 12), pady=5)
        lbl_cash_step.grid(row=0, column=4, sticky="w", padx=(0, 4), pady=5)
        e_cash_val.grid(row=0, column=5, sticky="w", padx=(0, 12), pady=5)
        ctk.CTkLabel(f_cash_r1, text="Strategy:", text_color="#B0BEC5").grid(row=0, column=6, sticky="w", padx=(0, 4), pady=5)
        cbo_cash_strat.grid(row=0, column=7, sticky="w", padx=(0, 8), pady=5)
        chk_cash_fee.grid(row=0, column=0, sticky="w", padx=(8, 16), pady=5)
        chk_be_one_time.grid(row=0, column=1, columnspan=4, sticky="w", padx=(0, 8), pady=5)
        lbl_cash_buffer.grid(row=0, column=0, sticky="w", padx=(8, 4), pady=5)
        cbo_cash_buffer_type.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=5)
        e_cash_buffer.grid(row=0, column=2, sticky="w", padx=(0, 16), pady=5)
        lbl_cash_min_lock.grid(row=0, column=3, sticky="w", padx=(0, 4), pady=5)
        e_cash_min_lock.grid(row=0, column=4, sticky="w", padx=(0, 8), pady=5)
        lbl_cash_help.configure(wraplength=820, justify="left", anchor="w")
        lbl_cash_help.pack(fill="x", padx=12, pady=(4, 10))
    except Exception:
        pass
    f_psar = sec(tab_adv, "6. PSAR TRAILING (Đuổi chấm)")
    f_psar.pack(fill="x", padx=15, pady=(0, 8))
    f_psar_row1 = ctk.CTkFrame(f_psar, fg_color="transparent")
    f_psar_row1.pack(fill="x", padx=8, pady=2)
    f_psar_row1.grid_columnconfigure(1, weight=1)
    cbo_psar_grp = ctk.CTkOptionMenu(
        f_psar_row1, values=["G0", "G1", "G2", "G3", "DYNAMIC-G1/G2"], width=80
    )
    cbo_psar_grp.set(tsl_cfg.get("PSAR_GROUP", "G2"))
    compact_menu(cbo_psar_grp)
    ctk.CTkLabel(f_psar_row1, text="Group:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
    cbo_psar_grp.grid(row=0, column=1, sticky="w", pady=4)
    f_psar_row2 = ctk.CTkFrame(f_psar, fg_color="transparent")
    f_psar_row2.pack(fill="x", padx=8, pady=2)
    f_psar_row2.grid_columnconfigure(4, weight=1)
    e_psar_step = ctk.CTkEntry(f_psar_row2, width=60)
    e_psar_step.insert(0, str(tsl_cfg.get("PSAR_STEP", 0.02)))
    compact_entry(e_psar_step)
    e_psar_max = ctk.CTkEntry(f_psar_row2, width=60)
    e_psar_max.insert(0, str(tsl_cfg.get("PSAR_MAX", 0.2)))
    compact_entry(e_psar_max)
    ctk.CTkLabel(f_psar_row2, text="Step:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
    e_psar_step.grid(row=0, column=1, sticky="w", padx=(0, 18), pady=4)
    ctk.CTkLabel(f_psar_row2, text="Max:").grid(row=0, column=2, sticky="w", padx=(0, 8), pady=4)
    e_psar_max.grid(row=0, column=3, sticky="w", padx=(0, 18), pady=4)
    f_psar_row3 = ctk.CTkFrame(f_psar, fg_color="transparent")
    f_psar_row3.pack(fill="x", padx=8, pady=2)
    e_psar_min_rr = ctk.CTkEntry(f_psar_row3, width=60)
    e_psar_min_rr.insert(0, str(tsl_cfg.get("PSAR_MIN_RR", 0.0)))
    compact_entry(e_psar_min_rr)
    ctk.CTkLabel(f_psar_row3, text="Min RR kích hoạt:").pack(side="left")
    e_psar_min_rr.pack(side="left", padx=(0, 18))
    ctk.CTkLabel(
        f_psar,
        text="Min RR dung cash-R: 0.5R = loi 50% so tien risk ban dau cua lenh. Neu thieu risk USD thi fallback theo khoang gia SL.",
        text_color="#B0BEC5",
        font=("Arial", 11, "italic"),
        wraplength=760,
    ).pack(anchor="w", padx=8, pady=(0, 4))
    f_psar_row4 = ctk.CTkFrame(f_psar, fg_color="transparent")
    f_psar_row4.pack(fill="x", padx=8, pady=2)
    var_psar_profit_only = ctk.BooleanVar(value=tsl_cfg.get("PSAR_PROFIT_ONLY", True))
    ctk.CTkCheckBox(
        f_psar_row4,
        text="PSAR chi keo SL khi da hoa von",
        variable=var_psar_profit_only,
        width=220,
    ).pack(side="left", padx=5)
    f_psar_row5 = ctk.CTkFrame(f_psar, fg_color="transparent")
    f_psar_row5.pack(fill="x", padx=8, pady=(2, 8))
    e_psar_profit_buffer = ctk.CTkEntry(f_psar_row5, width=60)
    e_psar_profit_buffer.insert(0, str(tsl_cfg.get("PSAR_PROFIT_BUFFER_POINTS", 0)))
    compact_entry(e_psar_profit_buffer)
    ctk.CTkLabel(f_psar_row5, text="BE Buffer Points:").pack(side="left", padx=(0, 8))
    e_psar_profit_buffer.pack(side="left", padx=(0, 18))
    f_anti = sec(tab_adv, "7. ANTI CASH")
    f_anti.pack(fill="x", padx=15, pady=(0, 8))
    _add_popup_hint(
        f_anti,
        "- Hard Stop: cắt lỗ cứng theo ngưỡng đã chọn.\n"
        "- MAE Guard: chỉ cắt khi lệnh âm đủ sâu, giữ đủ lâu và MFE cao nhất vẫn thấp hơn Low MFE.\n"
        "- MFE Guard: bảo vệ lãi nổi, cắt khi lệnh trả lại quá nhiều hoặc tụt về Floor.",
        padx=8,
        pady=(4, 8),
        wraplength=820,
    )

    def anti_row(parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", fill="x", pady=4)
        return row

    def anti_field(parent, label, value, width=82):
        group = ctk.CTkFrame(parent, fg_color="transparent")
        group.pack(side="left", padx=(8, 18))
        ctk.CTkLabel(group, text=label).pack(side="left", padx=(0, 6))
        entry = ctk.CTkEntry(group, width=width)
        entry.insert(0, str(value))
        entry.pack(side="left")
        return entry

    def anti_money_field(parent, label, value, unit):
        group = ctk.CTkFrame(parent, fg_color="transparent")
        group.pack(side="left", padx=(8, 18))
        ctk.CTkLabel(group, text=label).pack(side="left", padx=(0, 6))
        entry = ctk.CTkEntry(group, width=74)
        if unit in ("%R", "PERCENT_R"):
            try:
                value = float(value or 0.0) / 100.0
            except (TypeError, ValueError):
                value = 0.0
        entry.insert(0, str(value))
        entry.pack(side="left", padx=(0, 6))
        unit_menu = ctk.CTkOptionMenu(group, values=["USD", "R", "%Equity"], width=92)
        unit_menu.set("R" if unit in ("%R", "PERCENT_R") else (unit or "USD"))
        unit_menu.pack(side="left")
        return entry, unit_menu
    f_anti_grid = ctk.CTkFrame(f_anti, fg_color="transparent")
    f_anti_grid.pack(anchor="center", pady=(4, 2))
    row_hard = anti_row(f_anti_grid)
    e_anti_usd, cbo_anti_usd_unit = anti_money_field(
        row_hard,
        "Hard Stop:",
        tsl_cfg.get("ANTI_CASH_USD", 10.0),
        tsl_cfg.get("ANTI_CASH_HARD_STOP_UNIT", "USD"),
    )
    e_anti_time = anti_field(
        row_hard, "Time Cut (s):", tsl_cfg.get("ANTI_CASH_TIME", 60), width=86
    )
    var_anti_time_en = ctk.BooleanVar(value=tsl_cfg.get("ANTI_CASH_TIME_ENABLE", True))
    ctk.CTkCheckBox(
        row_hard, text="Dùng Time Cut", variable=var_anti_time_en, width=130
    ).pack(side="left", padx=(8, 18))
    row_mae = anti_row(f_anti_grid)
    var_anti_mae_en = ctk.BooleanVar(value=tsl_cfg.get("ANTI_CASH_MAE_ENABLE", True))
    ctk.CTkCheckBox(
        row_mae, text="MAE Guard", variable=var_anti_mae_en, width=120
    ).pack(side="left", padx=(8, 18))
    e_anti_mae_loss, cbo_anti_mae_loss_unit = anti_money_field(
        row_mae,
        "Max Loss:",
        tsl_cfg.get("ANTI_CASH_MAE_MAX_LOSS_USD", 25.0),
        tsl_cfg.get("ANTI_CASH_MAE_MAX_LOSS_UNIT", "USD"),
    )
    e_anti_mae_hold = anti_field(
        row_mae, "Hold(s):", tsl_cfg.get("ANTI_CASH_MAE_MIN_HOLD_SEC", 300), width=86
    )
    e_anti_mae_low_mfe, cbo_anti_mae_low_mfe_unit = anti_money_field(
        row_mae,
        "Low MFE:",
        tsl_cfg.get("ANTI_CASH_MAE_LOW_MFE_USD", 5.0),
        tsl_cfg.get("ANTI_CASH_MAE_LOW_MFE_UNIT", "USD"),
    )
    row_mfe = anti_row(f_anti_grid)
    var_anti_mfe_en = ctk.BooleanVar(value=tsl_cfg.get("ANTI_CASH_MFE_ENABLE", True))
    ctk.CTkCheckBox(
        row_mfe, text="MFE Guard", variable=var_anti_mfe_en, width=120
    ).pack(side="left", padx=(8, 18))
    e_anti_mfe_trig, cbo_anti_mfe_trig_unit = anti_money_field(
        row_mfe,
        "Trigger:",
        tsl_cfg.get("ANTI_CASH_MFE_TRIGGER_USD", 30.0),
        tsl_cfg.get("ANTI_CASH_MFE_TRIGGER_UNIT", "USD"),
    )
    e_anti_mfe_giveback, cbo_anti_mfe_giveback_unit = anti_money_field(
        row_mfe,
        "Giveback:",
        tsl_cfg.get("ANTI_CASH_MFE_GIVEBACK_USD", 20.0),
        tsl_cfg.get("ANTI_CASH_MFE_GIVEBACK_UNIT", "USD"),
    )
    e_anti_mfe_floor, cbo_anti_mfe_floor_unit = anti_money_field(
        row_mfe,
        "Floor:",
        tsl_cfg.get("ANTI_CASH_MFE_FLOOR_USD", 0.0),
        tsl_cfg.get("ANTI_CASH_MFE_FLOOR_UNIT", "USD"),
    )
    row_reentry = anti_row(f_anti_grid)
    e_anti_reentry = anti_field(
        row_reentry,
        "Re-entry Lock(s):",
        tsl_cfg.get("ANTI_CASH_REENTRY_LOCK_SEC", 900),
        width=86,
    )
    ctk.CTkLabel(
        row_reentry,
        text="sau khi ANTI CASH cắt cùng chiều",
        text_color="#BDBDBD",
    ).pack(side="left", padx=(0, 10))

    def save():
        try:
            output_tsl = {
                "BE_CASH_TYPE": cbo_cash_type.get(),
                "BE_TRIGGER": float(e_cash_trig.get()),
                "BE_VALUE": float(e_cash_val.get()),
                "BE_CASH_STRAT": cbo_cash_strat.get(),
                "BE_CASH_FEE_PROTECT": var_cash_fee_protect.get(),
                "BE_CASH_SOFT_BUFFER_TYPE": cbo_cash_buffer_type.get(),
                "BE_CASH_SOFT_BUFFER": float(e_cash_buffer.get()),
                "BE_CASH_MIN_LOCK": float(e_cash_min_lock.get()),
                "BE_MODE": "LOSS_GUARD",
                "BE_OFFSET_RR": 0.0,
                "BE_SL_LOSS_ENABLE": True,
                "BE_SL_LOSS_UNIT": cbo_be_sl_unit.get(),
                "BE_SL_LOSS_TRIGGER": float(e_be_sl_loss_trigger.get()),
                "BE_SL_LOSS_STEP": float(e_be_sl_loss_step.get()),
                "BE_SL_GUARD_BUFFER": float(e_be_sl_guard_buffer.get()),
                "BE_SL_LOSS_ACTION": "RECOVERY_GUARD",
                "BE_SL_REENTRY_LOCK_SEC": int(e_be_sl_reentry_lock.get()),
                "ONE_TIME_BE": var_be_one_time.get(),
                "PNL_LEVELS": sorted(
                    [
                        [float(e1.get()), float(e2.get())]
                        for r, e1, e2 in pnl_entries
                        if e1.get()
                    ],
                    key=lambda x: x[0],
                ),
                "STEP_R_SIZE": float(e_sz.get()),
                "STEP_R_RATIO": float(e_rt.get()),
                "SWING_GROUP": cbo_swing_grp.get(),
                "PSAR_GROUP": cbo_psar_grp.get(),
                "PSAR_STEP": float(e_psar_step.get()),
                "PSAR_MAX": float(e_psar_max.get()),
                "PSAR_MIN_RR": float(e_psar_min_rr.get()),
                "PSAR_PROFIT_ONLY": var_psar_profit_only.get(),
                "PSAR_PROFIT_BUFFER_POINTS": float(e_psar_profit_buffer.get()),
                "ANTI_CASH_USD": float(e_anti_usd.get()),
                "ANTI_CASH_HARD_STOP_UNIT": cbo_anti_usd_unit.get(),
                "ANTI_CASH_TIME": int(e_anti_time.get()),
                "ANTI_CASH_TIME_ENABLE": var_anti_time_en.get(),
                "ANTI_CASH_MAE_ENABLE": var_anti_mae_en.get(),
                "ANTI_CASH_MAE_MAX_LOSS_USD": float(e_anti_mae_loss.get()),
                "ANTI_CASH_MAE_MAX_LOSS_UNIT": cbo_anti_mae_loss_unit.get(),
                "ANTI_CASH_MAE_MIN_HOLD_SEC": int(e_anti_mae_hold.get()),
                "ANTI_CASH_MAE_LOW_MFE_USD": float(e_anti_mae_low_mfe.get()),
                "ANTI_CASH_MAE_LOW_MFE_UNIT": cbo_anti_mae_low_mfe_unit.get(),
                "ANTI_CASH_MFE_ENABLE": var_anti_mfe_en.get(),
                "ANTI_CASH_MFE_TRIGGER_USD": float(e_anti_mfe_trig.get()),
                "ANTI_CASH_MFE_TRIGGER_UNIT": cbo_anti_mfe_trig_unit.get(),
                "ANTI_CASH_MFE_GIVEBACK_USD": float(e_anti_mfe_giveback.get()),
                "ANTI_CASH_MFE_GIVEBACK_UNIT": cbo_anti_mfe_giveback_unit.get(),
                "ANTI_CASH_MFE_FLOOR_USD": float(e_anti_mfe_floor.get()),
                "ANTI_CASH_MFE_FLOOR_UNIT": cbo_anti_mfe_floor_unit.get(),
                "ANTI_CASH_REENTRY_LOCK_SEC": int(e_anti_reentry.get()),
            }
            new_tsl_logic_mode = cbo_tsl_logic_mode.get()
            if override_symbol:
                from core.storage_manager import (
                    load_symbol_overrides,
                    save_symbol_overrides,
                )
                overrides = load_symbol_overrides()
                if override_symbol not in overrides:
                    overrides[override_symbol] = {}
                if "tsl" not in overrides[override_symbol]:
                    overrides[override_symbol]["tsl"] = {}
                overrides[override_symbol]["tsl"]["TSL_CONFIG"] = output_tsl
                overrides[override_symbol]["tsl"]["TSL_LOGIC_MODE"] = new_tsl_logic_mode
                save_symbol_overrides(overrides)
                app.log_message(
                    f"✅ TSL Override Saved for {override_symbol}.", target="bot"
                )
                top.destroy()
                return
            config.TSL_CONFIG.update(output_tsl)
            config.TSL_LOGIC_MODE = new_tsl_logic_mode
            app.save_settings()
            app.log_message("✅ TSL Saved.", target="bot")
            top.destroy()
        except:
            messagebox.showerror("Lỗi", "Cấu hình sai!", parent=top)

    def refresh_tsl_override_overview():
        for child in f_overview_rows.winfo_children():
            child.destroy()
        try:
            from core.storage_manager import load_symbol_overrides
            overrides = load_symbol_overrides()
        except:
            overrides = {}
        symbol_values = list(
            getattr(config, "COIN_LIST", [])
            or [getattr(config, "DEFAULT_SYMBOL", "ETHUSD")]
        )
        for row, sym in enumerate(symbol_values):
            has_override = bool(overrides.get(sym, {}).get("tsl"))
            row_frame = ctk.CTkFrame(
                f_overview_rows,
                fg_color="#2F2A12" if has_override else "#242424",
                corner_radius=6,
            )
            row_frame.grid(row=row, column=0, sticky="ew", padx=2, pady=2)
            row_frame.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row_frame,
                text=sym,
                width=110,
                anchor="w",
                font=("Roboto", 12, "bold"),
                text_color="#FFFFFF",
            ).grid(row=0, column=0, sticky="w", padx=10, pady=6)
            ctk.CTkLabel(
                row_frame,
                text="OVERRIDE" if has_override else "GLOBAL",
                anchor="w",
                font=("Roboto", 11, "bold"),
                text_color="#FFAB00" if has_override else "#B0BEC5",
            ).grid(row=0, column=1, sticky="w", padx=8, pady=6)
            ctk.CTkButton(
                row_frame,
                text="EDIT" if has_override else "SELECT",
                width=76,
                height=24,
                fg_color="#1f538d" if has_override else "#424242",
                hover_color="#14375e" if has_override else "#616161",
                command=lambda s=sym: load_tsl_for_sym(s),
            ).grid(row=0, column=2, sticky="e", padx=(4, 6), pady=5)
            ctk.CTkButton(
                row_frame,
                text="RESET",
                width=70,
                height=24,
                fg_color="#B71C1C" if has_override else "#303030",
                hover_color="#7F0000" if has_override else "#303030",
                state="normal" if has_override else "disabled",
                command=lambda s=sym: reset_tsl_for_sym(s),
            ).grid(row=0, column=3, sticky="e", padx=(0, 6), pady=5)
    if not override_symbol:
        refresh_tsl_override_overview()
    ctk.CTkButton(
        top,
        text="SAVE TSL LOGIC",
        fg_color="#7B1FA2",
        hover_color="#4A148C",
        height=40,
        font=("Roboto", 13, "bold"),
        command=save,
    ).pack(pady=(6, 14), fill="x", padx=70)
    if override_symbol:

        def reset_tsl_override():
            from core.storage_manager import (
                load_symbol_overrides,
                save_symbol_overrides,
            )
            overrides = load_symbol_overrides()
            if override_symbol in overrides and "tsl" in overrides[override_symbol]:
                del overrides[override_symbol]["tsl"]
                save_symbol_overrides(overrides)
                app.log_message(
                    f"✅ TSL Override Reset for {override_symbol}.", target="bot"
                )
                top.destroy()
        ctk.CTkButton(
            top,
            text="🗑️ RESET (VỀ MẶC ĐỊNH)",
            fg_color="#D50000",
            hover_color="#B71C1C",
            height=40,
            font=FONT_BOLD,
            command=reset_tsl_override,
        ).pack(pady=(0, 15), fill="x", padx=40)
    if not override_symbol:

        def build_overwrite_tab():
            f = _speed_up_scroll(ctk.CTkScrollableFrame(tab_ow))
            f.pack(fill="both", expand=True, padx=5, pady=5)
            ctk.CTkLabel(
                f,
                text="CẤU HÌNH GHI ĐÈ (PER-SYMBOL OVERRIDE)",
                font=("Roboto", 14, "bold"),
            ).pack(pady=10)
            _add_popup_hint(
                f,
                "- Symbol có override sẽ dùng TSL riêng thay cho Global.\n"
                "- Reset override = xóa TSL con, quay về TSL mẹ.\n"
                "- Override chỉ áp dụng cho symbol được chọn.",
                padx=10,
                pady=(0, 10),
                wraplength=400,
            )
            grid_frame = ctk.CTkFrame(f, fg_color="transparent")
            grid_frame.pack(pady=10)
            from core.storage_manager import get_brain_settings_for_symbol
            from core.storage_manager import load_symbol_overrides
            brain = get_brain_settings_for_symbol()
            symbols = getattr(config, "COIN_LIST", [])
            overrides = load_symbol_overrides()
            row, col = 0, 0
            for sym in symbols:
                has_override = sym in overrides and "tsl" in overrides[sym]
                color = "#00C853" if has_override else "#424242"
                btn = ctk.CTkButton(
                    grid_frame,
                    text=f"{sym} {'(Có)' if has_override else ''}",
                    fg_color=color,
                    command=lambda s=sym: open_tsl_popup(app, s),
                )
                btn.grid(row=row, column=col, padx=5, pady=5)
                col += 1
                if col > 3:
                    col = 0
                    row += 1
        build_overwrite_tab()

# ==============================================================================

# 4. POPUP EDIT ORDER (FULL FEATURES: MATH SL, PRESET TP, DCA/PCA, TACTIC TOGGLES)

# ==============================================================================


def open_edit_popup(app, ticket):

    pos = next(
        (p for p in app.connector.get_all_open_positions() if p.ticket == ticket), None
    )
    if not pos:
        return
    top = ctk.CTkToplevel(app)
    top.title(f"Sửa lệnh #{ticket}")
    top.geometry("450x830")
    _bring_popup_to_front(top)
    # top.transient(app)
    is_buy = pos.type == 0
    bal = (
        app.connector.get_account_info()["balance"]
        if app.connector.get_account_info()
        else 1000.0
    )
    ctk.CTkLabel(top, text="NEW SL:", font=FONT_BOLD).pack(pady=(10, 2))
    e_sl = ctk.CTkEntry(top, justify="center")
    e_sl.insert(0, str(pos.sl))
    e_sl.pack()
    lbl_h_sl = ctk.CTkLabel(
        top, text="~ -$0.00", text_color="gray", font=("Roboto", 11)
    )
    lbl_h_sl.pack(pady=(0, 5))
    ctk.CTkLabel(top, text="NEW TP:", font=FONT_BOLD).pack(pady=(5, 2))
    e_tp = ctk.CTkEntry(top, justify="center")
    e_tp.insert(0, str(pos.tp))
    e_tp.pack()
    lbl_h_tp = ctk.CTkLabel(
        top, text="~ +$0.00", text_color="gray", font=("Roboto", 11)
    )
    lbl_h_tp.pack(pady=(0, 5))
    # Khung chứa Live Tactic Preview
    f_tactic_preview = ctk.CTkFrame(top, fg_color="#1a1a1a", corner_radius=6)
    f_tactic_preview.pack(fill="x", padx=20, pady=5)
    lbl_tactic_preview = ctk.CTkLabel(
        f_tactic_preview,
        text="TSL Preview",
        text_color="#29B6F6",
        font=("Consolas", 12),
    )
    lbl_tactic_preview.pack(pady=5)
    cur_t = app.trade_mgr.get_trade_tactic(ticket)
    cur_modes = cur_t.split("+")
    states = {
        "BE": "BE" in cur_modes,
        "PNL": "PNL" in cur_modes,
        "STEP": "STEP_R" in cur_modes,
        "SWING": "SWING" in cur_modes,
        "CASH": "BE_CASH" in cur_modes,
        "PSAR": "PSAR_TRAIL" in cur_modes,
        "REV": "REV_C" in cur_modes,
        "A.CUT": "ANTI_CASH" in cur_modes,
    }
    if states["CASH"]:
        states["BE"] = False

    def live_edit(*args):
        try:
            nsl, ntp = float(e_sl.get() or 0), float(e_tp.get() or 0)
            if nsl > 0:
                dist = abs(pos.price_open - nsl)
                loss = dist * pos.volume * 1.0  # Simple Contract Size
                lbl_h_sl.configure(
                    text=f"~ -${loss:.2f} ({loss / bal * 100:.2f}%)",
                    text_color="#EF5350",
                )
            if ntp > 0:
                p_dist = abs(pos.price_open - ntp)
                prof = p_dist * pos.volume * 1.0
                lbl_h_tp.configure(text=f"~ +${prof:.2f}", text_color="#66BB6A")
            else:
                lbl_h_tp.configure(text="~ Thả rông (Vô cực)", text_color="#29B6F6")
            # Cập nhật Live Trigger Price Preview
            if nsl > 0:
                r_dist = abs(pos.price_open - nsl)
                if r_dist > 0:
                    preview_txts = []
                    if states["BE"]:
                        trig_r = config.TSL_CONFIG.get("BE_SL_LOSS_TRIGGER", 0.5)
                        trig_p = (
                            pos.price_open - (trig_r * r_dist)
                            if is_buy
                            else pos.price_open + (trig_r * r_dist)
                        )
                        preview_txts.append(f"BE_SL Loss @ {trig_p:.2f}")
                    if states["STEP"]:
                        sz = config.TSL_CONFIG.get("STEP_R_SIZE", 1.0)
                        trig_p = (
                            pos.price_open + (sz * r_dist)
                            if is_buy
                            else pos.price_open - (sz * r_dist)
                        )
                        preview_txts.append(f"Step 1 @ {trig_p:.2f}")
                    if states["PNL"] and config.TSL_CONFIG.get("PNL_LEVELS"):
                        lvl = config.TSL_CONFIG["PNL_LEVELS"][0]
                        preview_txts.append(f"PNL @ Lãi {lvl[0]}%")
                    if states["SWING"]:
                        preview_txts.append("SWING (Đuổi theo nến H1/M15)")
                    if states["CASH"]:
                        preview_txts.append(
                            f"CASH TRAIL Bậc thang (Step: {config.TSL_CONFIG.get('BE_VALUE', 5)})"
                        )
                    if states["PSAR"]:
                        preview_txts.append("PSAR TRAIL")
                    if states["REV"]:
                        preview_txts.append("Close on Reverse")
                    if states["A.CUT"]:
                        preview_txts.append("Anti-Cash")
                    if preview_txts:
                        lbl_tactic_preview.configure(
                            text="Dự kiến Trigger TSL:\n" + " | ".join(preview_txts)
                        )
                    else:
                        lbl_tactic_preview.configure(text="TSL: OFF")
        except:
            pass
    e_sl.bind("<KeyRelease>", live_edit)
    e_tp.bind("<KeyRelease>", live_edit)

    # [UPGRADED] Math SL với dropdown chọn Group
    f_math = ctk.CTkFrame(top, fg_color="#1a1a1a", corner_radius=6)
    f_math.pack(fill="x", padx=20, pady=(5, 0))
    ctk.CTkLabel(
        f_math, text="TREND/RANGE Group:", font=("Roboto", 11), text_color="gray"
    ).pack(side="left", padx=(8, 4))
    var_sl_group = ctk.StringVar(value="G2")
    cbo_sl_group = ctk.CTkOptionMenu(
        f_math,
        values=["G0", "G1", "G2", "G3", "DYNAMIC-G1/G2"],
        variable=var_sl_group,
        width=130,
        height=26,
        fg_color="#2b2b2b",
        button_color="#1565C0",
        command=lambda _: do_math(),
    )
    cbo_sl_group.pack(side="left", padx=4)

    def do_math():
        ctx = app.latest_market_context.get(pos.symbol, {})
        group = var_sl_group.get()
        # Xử lý DYNAMIC: tự chọn group dựa trên Market Mode
        if "DYNAMIC" in group:
            mode = ctx.get("market_mode", "ANY")
            group = "G1" if mode in ["TREND", "BREAKOUT"] else "G2"
            var_sl_group.set(f"→{group}")  # Hiển thị group thực tế đã chọn
        val = ctx.get(f"swing_low_{group}" if is_buy else f"swing_high_{group}")
        atr_val = ctx.get(f"atr_{group}")
        if val and str(val) != "--" and atr_val:
            brain = app.trade_mgr._get_brain_settings()
            mult = float(
                brain.get("risk_tsl", {}).get(
                    "sl_atr_multiplier", getattr(config, "sl_atr_multiplier", 0.2)
                )
            )
            calc_sl = (
                float(val) - (float(atr_val) * mult)
                if is_buy
                else float(val) + (float(atr_val) * mult)
            )
            e_sl.delete(0, "end")
            e_sl.insert(0, f"{calc_sl:.5f}")
            do_tp()  # Tự động cập nhật TP theo SL mới
            live_edit()
        else:
            messagebox.showwarning(
                "Không có dữ liệu",
                f"Không tìm thấy Swing/ATR của {group} cho {pos.symbol}.\nThử chọn Group khác.",
                parent=top,
            )
    ctk.CTkButton(
        f_math,
        text="Lấy Math SL",
        height=26,
        fg_color="#1565C0",
        hover_color="#0D47A1",
        font=("Roboto", 12, "bold"),
        command=do_math,
    ).pack(side="left", padx=8, pady=4)
    f_ast = ctk.CTkFrame(top, fg_color="transparent")
    f_ast.pack(pady=(6, 0))

    def do_tp():
        try:
            rr = config.PRESETS.get(app.cbo_preset.get(), {}).get("TP_RR_RATIO", 1.5)
            tp = pos.price_open + (
                abs(pos.price_open - float(e_sl.get())) * rr
                if is_buy
                else -abs(pos.price_open - float(e_sl.get())) * rr
            )
            e_tp.delete(0, "end")
            e_tp.insert(0, f"{tp:.5f}")
            live_edit()
        except:
            pass

    def do_clear_tp():
        e_tp.delete(0, "end")
        e_tp.insert(0, "0.0")
        live_edit()

    def do_swing_tp():
        ctx = app.latest_market_context.get(pos.symbol, {})
        group = var_sl_group.get()
        if "DYNAMIC" in group:
            mode = ctx.get("market_mode", "ANY")
            group = "G1" if mode in ["TREND", "BREAKOUT"] else "G2"
        val = ctx.get(f"swing_high_{group}" if is_buy else f"swing_low_{group}")
        atr_val = ctx.get(f"atr_{group}")
        if val and str(val) != "--" and atr_val:
            brain = app.trade_mgr._get_brain_settings()
            mult = float(brain.get("risk_tsl", {}).get("sl_atr_multiplier", 0.2))
            calc_tp = (
                float(val) - (float(atr_val) * mult)
                if is_buy
                else float(val) + (float(atr_val) * mult)
            )
            e_tp.delete(0, "end")
            e_tp.insert(0, f"{calc_tp:.5f}")
            live_edit()
        else:
            messagebox.showwarning("Lỗi", "Không có dữ liệu Swing TP", parent=top)
    ctk.CTkButton(
        f_ast, text="Lấy Preset TP", width=105, fg_color="#2E7D32", command=do_tp
    ).pack(side="left", padx=2)
    ctk.CTkButton(
        f_ast, text="Lấy Swing TP", width=105, fg_color="#66BB6A", command=do_swing_tp
    ).pack(side="left", padx=2)
    ctk.CTkButton(
        f_ast, text="Bỏ TP (Vô cực)", width=105, fg_color="#455A64", command=do_clear_tp
    ).pack(side="right", padx=2)
    f_tactic_row = ctk.CTkFrame(top, fg_color="transparent")
    f_tactic_row.pack(pady=(10, 2))
    ctk.CTkLabel(
        f_tactic_row, text="TACTIC:", font=("Roboto", 11, "bold"), text_color="gray"
    ).pack(side="left", padx=(0, 5))
    btns = {}

    def tog(k):
        states[k] = not states[k]
        if k == "CASH" and states[k]:
            states["BE"] = False
        elif k == "BE" and states[k]:
            states["CASH"] = False
        for key in ("BE", "CASH", k):
            if key in btns:
                btns[key].configure(
                    fg_color=COL_BLUE_ACCENT if states[key] else COL_GRAY_BTN
                )
        live_edit()
    # Dòng 1: TACTIC (6 nút giống hệt Panel)
    tactic_widths = {
        "BE": 32,
        "PNL": 28,
        "STEP": 32,
        "SWING": 38,
        "CASH": 38,
        "PSAR": 38,
    }
    for k in ["BE", "PNL", "STEP", "SWING", "CASH", "PSAR"]:
        btns[k] = ctk.CTkButton(
            f_tactic_row,
            text=k,
            width=tactic_widths[k],
            fg_color=COL_BLUE_ACCENT if states[k] else COL_GRAY_BTN,
            command=lambda x=k: tog(x),
        )
        btns[k].pack(side="left", padx=1)
    f_def_row = ctk.CTkFrame(top, fg_color="transparent")
    f_def_row.pack(pady=(2, 10))
    ctk.CTkLabel(
        f_def_row, text="DEF:", font=("Roboto", 11, "bold"), text_color="gray"
    ).pack(side="left", padx=(0, 5))
    # Dòng 2: DEF (DCA, PCA checkboxes + REV, A.CUT buttons)
    chk_dca = ctk.CTkCheckBox(f_def_row, text="DCA", font=("Roboto", 11), width=45)
    chk_dca.pack(side="left", padx=4)
    chk_pca = ctk.CTkCheckBox(f_def_row, text="PCA", font=("Roboto", 11), width=45)
    chk_pca.pack(side="left", padx=4)
    if "AUTO_DCA" in cur_t:
        chk_dca.select()
    if "AUTO_PCA" in cur_t:
        chk_pca.select()
    def_widths = {"REV": 34, "A.CUT": 38}
    for k in ["REV", "A.CUT"]:
        btns[k] = ctk.CTkButton(
            f_def_row,
            text=k,
            width=def_widths[k],
            fg_color=COL_BLUE_ACCENT if states[k] else COL_GRAY_BTN,
            command=lambda x=k: tog(x),
        )
        btns[k].pack(side="left", padx=1)

    # --- Entry/Exit Mode Row ---
    f_ee_row = ctk.CTkFrame(top, fg_color="#1a1a1a", corner_radius=6)
    f_ee_row.pack(fill="x", padx=20, pady=(4, 6))
    ctk.CTkLabel(
        f_ee_row, text="E/E Mode:", font=("Roboto", 11, "bold"), text_color="#B0BEC5"
    ).pack(side="left", padx=(8, 4), pady=6)
    ee_options_map = {
        "OFF": "OFF",
        "R": "FALLBACK_R",
        "RETEST": "SWING_REJECTION",
        "STRUCT": "SWING_STRUCTURE",
        "FIB": "FIB_RETRACE",
        "PULL": "PULLBACK_ZONE",
    }
    current_ee = app.trade_mgr.get_trade_entry_exit_tactic(ticket)
    var_ee = ctk.StringVar(value=current_ee if current_ee else "OFF")
    ee_btns = {}

    def set_ee(label):
        var_ee.set(label)
        for lb, btn in ee_btns.items():
            is_active = (lb == label)
            btn.configure(
                fg_color="#E65100" if is_active else COL_GRAY_BTN,
                text_color="white",
            )
    for lb in ee_options_map:
        # Xác định nút nào đang active dựa trên giá trị hiện tại
        val = ee_options_map[lb]
        is_active = (current_ee == val) or (lb == "OFF" and (not current_ee or current_ee == "OFF"))
        b = ctk.CTkButton(
            f_ee_row,
            text=lb,
            width=46 if lb in ("RETEST", "STRUCT") else 36,
            height=26,
            fg_color="#E65100" if is_active else COL_GRAY_BTN,
            hover_color="#BF360C" if is_active else "#616161",
            font=("Roboto", 11, "bold"),
            command=lambda x=lb: set_ee(x),
        )
        b.pack(side="left", padx=2, pady=4)
        ee_btns[lb] = b
    live_edit()  # Lần gọi đầu tiên khi mở popup

    def save_e():
        try:
            app.connector.modify_position(ticket, float(e_sl.get()), float(e_tp.get()))
            act = []
            for k, v in states.items():
                if v:
                    if k == "STEP":
                        act.append("STEP_R")
                    elif k == "CASH":
                        act.append("BE_CASH")
                    elif k == "PSAR":
                        act.append("PSAR_TRAIL")
                    elif k == "REV":
                        act.append("REV_C")
                    elif k == "A.CUT":
                        act.append("ANTI_CASH")
                    else:
                        act.append(k)
            final_t = "+".join(act) if act else "OFF"
            if chk_dca.get():
                final_t += "+AUTO_DCA"
            if chk_pca.get():
                final_t += "+AUTO_PCA"
            app.trade_mgr.update_trade_tactic(ticket, final_t)
            # Lưu Entry/Exit Mode
            selected_ee_label = var_ee.get()
            new_ee_tactic = ee_options_map.get(selected_ee_label, "OFF")
            app.trade_mgr.update_trade_entry_exit_tactic(ticket, new_ee_tactic)
            app.log_message(f"Update Entry/Exit #{ticket}: {new_ee_tactic}")
            top.destroy()
        except Exception as e:
            messagebox.showerror("Lỗi", str(e), parent=top)
    ctk.CTkButton(
        top,
        text="CẬP NHẬT LỆNH",
        height=45,
        fg_color="#2e7d32",
        font=FONT_BOLD,
        command=save_e,
    ).pack(pady=20, fill="x", padx=40)

def show_history_popup(app):

    top = ctk.CTkToplevel(app)
    top.title("Lịch sử giao dịch theo chiến thuật")
    top.geometry("1400x650")
    top.minsize(1100, 550)
    _bring_popup_to_front(top)

    history_tabs = ctk.CTkTabview(top)
    history_tabs.pack(fill="both", expand=True)
    tab_bot_history = history_tabs.add("BOT")
    tab_grid_history = history_tabs.add("GRID")
    tab_hedge_history = history_tabs.add("HEDGE")

    cols = (
        "Time", "Ticket", "Symbol", "Type", "Vol", "Entry", "SL", "TP",
        "Fee", "PnL ($)", "MAE", "MFE", "Trigger", "Reason",
    )
    widths = [300, 150, 130, 130, 130, 145, 145, 145, 110, 120, 120, 120, 330, 360]

    style = ttk.Style()
    style.configure(
        "History.Treeview",
        background="#242424",
        foreground="white",
        fieldbackground="#242424",
        rowheight=50,
        font=("Consolas", 18),
    )
    style.configure(
        "History.Treeview.Heading",
        background="#1f1f1f",
        foreground="#e0e0e0",
        font=("Roboto", 20, "bold"),
        relief="flat",
    )

    def make_tree(parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=6, pady=6)
        tree = ttk.Treeview(frame, columns=cols, show="tree headings", style="History.Treeview")
        yscrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xscrollbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscrollbar.set, xscrollcommand=xscrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscrollbar.grid(row=0, column=1, sticky="ns")
        xscrollbar.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        tree.column("#0", width=325, minwidth=325, anchor="w", stretch=False)
        tree.heading("#0", text="Session")
        for col, width in zip(cols, widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, minwidth=width, anchor="center", stretch=False)
        return tree

    trees = {
        "BOT": make_tree(tab_bot_history),
        "GRID": make_tree(tab_grid_history),
        "HEDGE": make_tree(tab_hedge_history),
    }

    from core.storage_manager import MASTER_LOG_FILE
    csv_path = MASTER_LOG_FILE

    def to_float(val, default=0.0):
        try:
            return float(str(val).replace("$", "").replace(",", "").strip())
        except (TypeError, ValueError):
            return default

    def row_scope(row):
        market_mode = str(row[11] if len(row) > 11 else "").upper()
        trigger = str(row[12] if len(row) > 12 else "").upper()
        session_id = str(row[13] if len(row) > 13 else "").upper()
        text = f"{market_mode}|{trigger}|{session_id}"
        if "HEDGE" in text:
            return "HEDGE"
        if "GRID" in text:
            return "GRID"
        return "BOT"

    def clear_trees():
        for tree in trees.values():
            if tree.winfo_exists():
                for item in tree.get_children():
                    tree.delete(item)

    def fmt_money(val):
        return f"-${abs(val):.2f}" if val < 0 else f"${val:.2f}"

    def insert_sessions(tree, sessions, current_balance):
        sorted_sessions = sorted(sessions.keys(), reverse=True)
        balance_map = {}
        if current_balance is not None:
            running_end = current_balance
            for sid in sorted_sessions:
                net = sum(to_float(r[9]) + to_float(r[8]) for r in sessions[sid] if len(r) >= 14)
                start = running_end - net
                balance_map[sid] = (start, running_end)
                running_end = start

        for sid in sorted_sessions:
            rows = sessions[sid]
            wins = buys = sells = total = 0
            total_pnl = total_fee = total_mae = total_mfe = 0.0
            for row in rows:
                pnl = to_float(row[9])
                fee = to_float(row[8])
                mae = to_float(row[14]) if len(row) > 14 else 0.0
                mfe = to_float(row[15]) if len(row) > 15 else 0.0
                total_pnl += pnl
                total_fee += fee
                total_mae += mae
                total_mfe += mfe
                wins += 1 if pnl > 0 else 0
                total += 1
                buys += 1 if row[3] == "BUY" else 0
                sells += 1 if row[3] == "SELL" else 0

            winrate = (wins / total * 100) if total else 0.0
            if sid in balance_map:
                start, end = balance_map[sid]
                arrow = "▲" if end - start >= 0 else "▼"
                balance_text = f"${start:,.0f} {arrow} ${end:,.0f}"
            else:
                balance_text = ""

            parent_id = tree.insert(
                "", "end", text=(f"Phiên: {sid}" if sid != "LEGACY" else "Phiên cũ (Legacy)"),
                values=(
                    balance_text, "", "", f"B:{buys} | S:{sells}", f"W: {winrate:.1f}%", "", "", "",
                    fmt_money(total_fee), fmt_money(total_pnl), fmt_money(total_mae), fmt_money(total_mfe), "", "",
                ),
            )
            for row in reversed(rows):
                reason = row[10]
                if reason == "Basket_TP" and to_float(row[9]) < 0:
                    reason = "Basket_TP_Order_Loss"
                tree.insert(
                    parent_id, "end", text="",
                    values=(
                        row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9],
                        row[14] if len(row) > 14 else "",
                        row[15] if len(row) > 15 else "",
                        row[12] if len(row) > 12 else "",
                        reason,
                    ),
                )
            if sid == sorted_sessions[0]:
                tree.item(parent_id, open=True)

    def load_data():
        try:
            acc = app.connector.get_account_info()
            current_balance = acc["balance"] if acc else None
        except Exception:
            current_balance = None
        clear_trees()
        if not os.path.exists(csv_path):
            return
        try:
            scope_sessions = {"BOT": {}, "GRID": {}, "HEDGE": {}}
            with open(csv_path, mode="r", encoding="utf-8") as file_obj:
                reader = csv.reader(file_obj)
                header = next(reader, None)
                if not header:
                    return
                records_by_ticket = {}
                for row in reader:
                    if len(row) >= 14:
                        records_by_ticket[row[1]] = row
                for row in records_by_ticket.values():
                    scope = row_scope(row)
                    session_id = row[13] or "LEGACY"
                    scope_sessions[scope].setdefault(session_id, []).append(row)
            for scope, tree in trees.items():
                insert_sessions(tree, scope_sessions[scope], current_balance)
        except Exception as exc:
            if hasattr(app, "log_message"):
                app.log_message(f"[HISTORY] Load failed: {exc}", target="manual")

    def delete_session(session_id):
        if messagebox.askyesno(
            "Cảnh báo",
            f"Bạn có chắc muốn xóa vĩnh viễn toàn bộ nhật ký của phiên [{session_id}] không?",
            parent=top,
        ):
            from core.storage_manager import delete_session_log
            delete_session_log(session_id)
            if hasattr(app, "log_message"):
                app.log_message(f"Đã dọn dẹp log của phiên {session_id}.", target="manual")
            load_data()

    def bind_tree_menu(tree):
        def on_right_click(event):
            row_id = tree.identify_row(event.y)
            if not row_id:
                return
            tree.selection_set(row_id)
            if tree.parent(row_id) != "":
                return
            session_text = tree.item(row_id, "text")
            session_id = session_text.replace("Phiên: ", "").replace("Phiên cũ (Legacy)", "LEGACY")
            menu = tk.Menu(top, tearoff=0, font=("Roboto", 11))
            menu.add_command(label=f"Xóa log phiên [{session_id}]", command=lambda: delete_session(session_id))
            menu.post(event.x_root, event.y_root)
        tree.bind("<Button-3>", on_right_click)

    for tree in trees.values():
        bind_tree_menu(tree)
    load_data()
def open_minibrain_popup(app, title, mb_cfg, on_save_callback):
    """
    [NEW V5.1] Popup cài đặt Mini-Brain 1-Group độc lập cho DCA/PCA
    """
    from tkinter import messagebox
    import customtkinter as ctk
    import config as _cfg
    top = ctk.CTkToplevel()
    top.title(title)
    top.geometry("700x520")
    _bring_popup_to_front(top)
    top.grab_set()
    f_top = ctk.CTkFrame(top)
    f_top.pack(fill="x", padx=10, pady=10)
    var_active = ctk.BooleanVar(value=mb_cfg.get("active", False))
    ctk.CTkCheckBox(
        f_top, text="Bật Mini-Brain", variable=var_active, font=("Roboto", 13, "bold")
    ).pack(side="left", padx=10)
    ctk.CTkLabel(f_top, text="Timeframe:").pack(side="left", padx=(20, 5))
    cbo_tf = ctk.CTkComboBox(
        f_top, values=["1m", "5m", "15m", "30m", "1h", "4h"], width=80
    )
    cbo_tf.set(mb_cfg.get("timeframe", "15m"))
    cbo_tf.pack(side="left", padx=5)
    f_rules = ctk.CTkFrame(top)
    f_rules.pack(fill="x", padx=10, pady=5)
    ctk.CTkLabel(f_rules, text="Max Opposite (Phiếu ngược tối đa):").pack(
        side="left", padx=10, pady=5
    )
    e_max_opp = ctk.CTkEntry(f_rules, width=60, justify="center")
    e_max_opp.insert(0, str(mb_cfg.get("max_opposite", 0)))
    e_max_opp.pack(side="left", padx=5)
    ctk.CTkLabel(f_rules, text="Max None (Phiếu trắng tối đa):").pack(
        side="left", padx=20, pady=5
    )
    e_max_none = ctk.CTkEntry(f_rules, width=60, justify="center")
    e_max_none.insert(0, str(mb_cfg.get("max_none", 0)))
    e_max_none.pack(side="left", padx=5)
    f_inds = ctk.CTkFrame(top)
    f_inds.pack(fill="both", expand=True, padx=10, pady=10)
    ctk.CTkLabel(f_inds, text="CHỌN CHỈ BÁO", font=("Roboto", 12, "bold")).pack(pady=5)
    inds_cfg = mb_cfg.get("indicators", {})
    vars_dict = {}
    # Dùng SANDBOX_CONFIG["indicators"] làm nguồn danh sách indicator (không dùng INDICATOR_DEFINITIONS không tồn tại)
    all_indicators = _cfg.SANDBOX_CONFIG.get("indicators", {})
    LABEL_MAP = {
        "adx": "ADX",
        "ema": "EMA",
        "swing_point": "Swing Point",
        "atr": "ATR",
        "pivot_points": "Pivot Points",
        "ema_cross": "EMA Cross",
        "volume": "Volume",
        "supertrend": "SuperTrend",
        "psar": "PSAR",
        "bollinger_bands": "Bollinger Bands",
        "fibonacci": "Fibonacci",
        "rsi": "RSI",
        "stochastic": "Stochastic",
        "macd": "MACD",
        "multi_candle": "Multi-Candle",
        "candle": "Candle",
        "simple_breakout": "Simple Breakout",
    }
    grid_f = ctk.CTkFrame(f_inds, fg_color="transparent")
    grid_f.pack(fill="both", expand=True, padx=5, pady=5)
    r, c = 0, 0
    for key in all_indicators.keys():
        is_on = inds_cfg.get(key, {}).get("active", False)
        var = ctk.BooleanVar(value=is_on)
        vars_dict[key] = var
        label = LABEL_MAP.get(key, key.upper())
        ctk.CTkCheckBox(grid_f, text=label, variable=var).grid(
            row=r, column=c, sticky="w", padx=10, pady=5
        )
        c += 1
        if c > 2:
            c = 0
            r += 1

    def save_mb():
        try:
            new_cfg = {
                "active": var_active.get(),
                "timeframe": cbo_tf.get(),
                "max_opposite": int(e_max_opp.get()),
                "max_none": int(e_max_none.get()),
                "indicators": {},
            }
            for k, v in vars_dict.items():
                if v.get():
                    # Chỉ lưu trạng thái active, không lưu cứng params để Mini-Brain tự mượn params từ Sandbox
                    new_cfg["indicators"][k] = {"active": True}
            on_save_callback(new_cfg)
            top.destroy()
        except ValueError as e:
            messagebox.showerror("Lỗi", f"Vui lòng nhập số hợp lệ: {e}", parent=top)
    ctk.CTkButton(
        top,
        text="LƯU MINI-BRAIN",
        fg_color="#FBC02D",
        text_color="#212121",
        font=("Roboto", 13, "bold"),
        command=save_mb,
    ).pack(pady=10)




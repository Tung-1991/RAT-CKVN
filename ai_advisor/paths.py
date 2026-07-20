# -*- coding: utf-8 -*-
import os
from datetime import datetime


def account_dir():
    try:
        import core.storage_manager as storage_manager

        return storage_manager._active_account_dir
    except Exception:
        return "data"


def account_id():
    try:
        import core.storage_manager as storage_manager

        return storage_manager._active_account_id
    except Exception:
        return None


def advisor_root():
    return os.path.join(account_dir(), "advisor")


def external_package_root():
    return os.path.join(advisor_root(), "external_package")


def account_api_settings_path():
    return os.path.join(account_dir(), "advisor_api_settings.json")


def template_root():
    return os.path.join("data", "templates", "ai-advisor")


def advisor_template_path(filename):
    return os.path.join(template_root(), filename)


def history_root():
    return os.path.join(account_dir(), "history")


def history_path():
    return os.path.join(history_root(), "advisor_history.xlsx")


def legacy_history_path():
    return os.path.join(advisor_root(), "advisor_history.xlsx")


def legacy_account_history_path():
    return os.path.join(account_dir(), "advisor_history.xlsx")


def export_path():
    return os.path.join(advisor_root(), "advisor_export.xlsx")


def technical_settings_path():
    return os.path.join(advisor_root(), "technical_settings.json")


def user_context_path():
    return os.path.join(advisor_root(), "user_context.md")


def expert_context_path():
    return os.path.join(advisor_root(), "expert_context.md")


def advisor_flow_path():
    return os.path.join(advisor_root(), "advisor_flow.md")


def advisor_prompt_path():
    return os.path.join(advisor_root(), "advisor_prompt.md")


def advisor_api_settings_path():
    return account_api_settings_path()


def legacy_advisor_api_settings_path():
    return os.path.join(advisor_root(), "advisor_api_settings.json")


def advisor_response_path():
    return os.path.join(advisor_root(), "advisor_response.md")


def advisor_response_history_path():
    return os.path.join(history_root(), f"advisor_response_{timestamp_name()}.md")


def user_context_history_path():
    return os.path.join(history_root(), f"user_context_{timestamp_name()}.md")


def scan_cache_path():
    return os.path.join(account_dir(), "scan_snapshot_cache.json")


def scan_summary_path():
    return os.path.join(advisor_root(), "scan_summary.md")


def scan_report_path():
    return os.path.join(advisor_root(), "scan_report.md")


def ensure_advisor_dirs():
    os.makedirs(advisor_root(), exist_ok=True)
    os.makedirs(external_package_root(), exist_ok=True)
    os.makedirs(history_root(), exist_ok=True)
    return advisor_root()


def timestamp_name():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

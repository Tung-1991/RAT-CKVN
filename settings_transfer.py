# -*- coding: utf-8 -*-
"""Xuất/nhập setting RAT-CKVN giữa các máy, không đụng .env hay runtime."""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data"
COPY_ROOT = DATA_ROOT / "copy"

ROOT_SETTING_FILES = (
    "brain_settings.json",
    "symbol_overrides.json",
    "tsl_settings.json",
    "presets_config.json",
    "advisor_api_settings.json",
    "telegram_settings.json",
)

CONTEXT_FILES = {
    "advisor": (
        "user_context.md",
        "expert_context.md",
        "advisor_prompt.md",
        "advisor_flow.md",
        "advisor_response.md",
    ),
    "ckcs_research": ("private_context.md",),
}

IGNORED_ACCOUNT_DIRS = {"copy", "logs", "paper", "templates"}


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_relative(path: Path) -> Path:
    if path.is_absolute() or ".." in path.parts or path.name == ".env":
        raise ValueError(f"Đường dẫn không hợp lệ: {path}")
    return path


def _allowed_relative(path: Path) -> bool:
    path = _safe_relative(path)
    if len(path.parts) == 1:
        return path.name in ROOT_SETTING_FILES
    if len(path.parts) == 2 and path.parts[0] in CONTEXT_FILES:
        return path.parts[1] in CONTEXT_FILES[path.parts[0]]
    return path.parts[0] == "templates"


def discover_accounts(data_root: Path = DATA_ROOT) -> list[Path]:
    if not data_root.exists():
        return []
    accounts = []
    for child in data_root.iterdir():
        if not child.is_dir() or child.name.lower() in IGNORED_ACCOUNT_DIRS:
            continue
        has_settings = any((child / name).is_file() for name in ROOT_SETTING_FILES)
        if child.name.isdigit() or child.name.upper() == "PAPER" or has_settings:
            accounts.append(child)
    return sorted(accounts, key=lambda item: item.name)


def collect_setting_files(account_dir: Path) -> list[Path]:
    found: list[Path] = []
    for name in ROOT_SETTING_FILES:
        path = account_dir / name
        if path.is_file():
            found.append(Path(name))
    for folder, names in CONTEXT_FILES.items():
        for name in names:
            path = account_dir / folder / name
            if path.is_file():
                found.append(Path(folder) / name)
    template_root = account_dir / "templates"
    if template_root.is_dir():
        for path in sorted(template_root.rglob("*")):
            if path.is_file() and path.name != ".env":
                found.append(path.relative_to(account_dir))
    return sorted(dict.fromkeys(found), key=lambda item: item.as_posix())


def export_settings(
    account_dir: Path,
    copy_root: Path = COPY_ROOT,
    stamp: str | None = None,
) -> Path:
    account_dir = account_dir.resolve()
    files = collect_setting_files(account_dir)
    if not files:
        raise RuntimeError(f"Tài khoản {account_dir.name} chưa có setting để xuất.")

    stamp = stamp or _timestamp()
    package_dir = copy_root / f"{account_dir.name}_{stamp}"
    package_dir.mkdir(parents=True, exist_ok=False)
    for relative in files:
        if not _allowed_relative(relative):
            continue
        source = account_dir / relative
        target = package_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    manifest = {
        "version": 1,
        "source_account": account_dir.name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": [item.as_posix() for item in files if _allowed_relative(item)],
        "excluded": [
            ".env/API key",
            "trading token/OTP",
            "bot state, lệnh, PNL, PAPER, lịch sử, cache và RAW DATA",
        ],
    }
    manifest_path = package_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
    return package_dir


def discover_packages(copy_root: Path = COPY_ROOT) -> list[Path]:
    if not copy_root.exists():
        return []
    packages = [
        path
        for path in copy_root.iterdir()
        if path.is_dir() and (path / "manifest.json").is_file()
    ]
    return sorted(packages, key=lambda item: item.name, reverse=True)


def load_manifest(package_dir: Path) -> dict:
    with (package_dir / "manifest.json").open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("Gói copy không có manifest hợp lệ.")
    return manifest


def import_settings(
    package_dir: Path,
    target_account_dir: Path,
    copy_root: Path = COPY_ROOT,
    stamp: str | None = None,
) -> dict:
    package_dir = package_dir.resolve()
    target_account_dir = target_account_dir.resolve()
    manifest = load_manifest(package_dir)
    stamp = stamp or _timestamp()
    backup_dir = copy_root / "_backups" / f"{target_account_dir.name}_{stamp}"
    restored: list[str] = []
    backed_up: list[str] = []

    for raw in manifest["files"]:
        relative = _safe_relative(Path(str(raw)))
        if not _allowed_relative(relative):
            continue
        source = (package_dir / relative).resolve()
        try:
            source.relative_to(package_dir)
        except ValueError as exc:
            raise ValueError(f"File nằm ngoài gói copy: {relative}") from exc
        if not source.is_file():
            raise FileNotFoundError(f"Thiếu file trong gói: {relative}")

        target = target_account_dir / relative
        if target.is_file():
            backup = backup_dir / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            backed_up.append(relative.as_posix())

        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.import.tmp")
        shutil.copy2(source, temp)
        os.replace(temp, target)
        restored.append(relative.as_posix())

    return {
        "restored": restored,
        "backed_up": backed_up,
        "backup_dir": str(backup_dir) if backed_up else "",
        "source_account": manifest.get("source_account", ""),
        "target_account": target_account_dir.name,
    }


def _choose(title: str, items: list[Path]) -> Path | None:
    if not items:
        print("Không có dữ liệu phù hợp.")
        return None
    print(f"\n{title}")
    for index, item in enumerate(items, 1):
        print(f"  {index}. {item.name}")
    print("  0. Quay lại")
    while True:
        raw = input("Chọn: ").strip()
        if raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("Lựa chọn không hợp lệ.")


def _menu_export() -> None:
    account = _choose("CHỌN TÀI KHOẢN NGUỒN", discover_accounts())
    if account is None:
        return
    package = export_settings(account)
    files = load_manifest(package)["files"]
    print(f"\nĐã tạo: {package}")
    print(f"Đã lưu {len(files)} file setting:")
    for name in files:
        print(f"  - {name}")


def _menu_import() -> None:
    package = _choose("CHỌN GÓI SETTING", discover_packages())
    if package is None:
        return
    manifest = load_manifest(package)
    print("\nFILE TRONG GÓI:")
    for name in manifest["files"]:
        print(f"  - {name}")
    print("\nLƯU Ý: Hãy đóng app/START_SYSTEM.bat trước khi nhập để app không ghi đè setting vừa chép.")
    target = _choose("CHỌN TÀI KHOẢN ĐÍCH", discover_accounts())
    if target is None:
        return
    confirm = input(f"\nGhi setting vào tài khoản {target.name}? Gõ YES để tiếp tục: ").strip().upper()
    if confirm != "YES":
        print("Đã hủy.")
        return
    result = import_settings(package, target)
    print(f"\nĐã nhập {len(result['restored'])} file vào {target.name}.")
    if result["backed_up"]:
        print(f"Setting cũ đã backup tại: {result['backup_dir']}")
    print("Hãy khởi động lại app để áp dụng đầy đủ.")


def main() -> int:
    if os.name == "nt":
        os.system("chcp 65001 >nul")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    COPY_ROOT.mkdir(parents=True, exist_ok=True)
    while True:
        print("\n=== RAT-CKVN COPY SETTING ===")
        print("1. Xuất setting")
        print("2. Nhập setting")
        print("0. Thoát")
        choice = input("Chọn: ").strip()
        try:
            if choice == "1":
                _menu_export()
            elif choice == "2":
                _menu_import()
            elif choice == "0":
                return 0
            else:
                print("Lựa chọn không hợp lệ.")
        except Exception as exc:  # noqa: BLE001
            print(f"LỖI: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())

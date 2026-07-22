# -*- coding: utf-8 -*-
"""Sao lưu setting RAT-CKVN theo hai vùng PUBLIC/PRIVATE.

PUBLIC có thể đưa lên GitHub. PRIVATE phải tự sao chép giữa các máy.
API key, token, tài khoản DNSE, Telegram và .env không bao giờ được xuất.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data"
COPY_ROOT = DATA_ROOT / "copy"
PUBLIC_COPY_ROOT = COPY_ROOT / "public"
PRIVATE_COPY_ROOT = COPY_ROOT / "private"
BACKUP_ROOT = COPY_ROOT / "_backups"

# Rule, risk, watchlist, indicator, setting riêng từng mã và preset chiến thuật.
PUBLIC_ROOT_FILES = (
    "brain_settings.json",
    "symbol_overrides.json",
    "tsl_settings.json",
    "presets_config.json",
)
PUBLIC_ADVISOR_FILES = (
    "advisor_prompt.md",
    "advisor_flow.md",
)
PUBLIC_PORTABLE_FILE = "portable_settings.json"
PUBLIC_ENV_KEYS = (
    "DNSE_CKPS_WATCHLIST",
    "DNSE_CKCS_WATCHLIST",
    "DNSE_DERIVATIVE_REAL_SYMBOLS",
    "SCAN_SNAPSHOT_ENABLED",
    "SCAN_SNAPSHOT_INTERVAL_MINUTES",
    "SCAN_SNAPSHOT_RETENTION_DAYS",
    "PAPER_TRADING",
    "MONEY_DISPLAY_ZERO_TRIM",
    "DNSE_WS_ENABLED",
    "DNSE_WS_MODE",
    "DNSE_WS_URL",
    "DNSE_WS_ENCODING",
    "DNSE_WS_BOARD_ID",
    "DNSE_WS_RECONCILE_SECONDS",
    "MARKET_PREOPEN_MINUTES",
    "MARKET_HOLIDAYS",
    "DNSE_TICK_CACHE_TTL_SECONDS",
    "DNSE_OHLC_CACHE_TTL_SECONDS",
    "DNSE_OHLC_CACHE_TTL_CLOSED_SECONDS",
    "DNSE_ACCOUNT_CACHE_TTL_SECONDS",
    "DNSE_POSITIONS_CACHE_TTL_SECONDS",
    "DNSE_RATE_LIMIT_RETRIES",
    "DNSE_OHLC_WINDOW_FACTOR_INTRADAY",
    "DNSE_OHLC_WINDOW_FACTOR_DAILY",
    "ADVISOR_API_TIMEOUT_SECONDS",
    "ADVISOR_API_RETRIES",
    "DNSE_DERIVATIVE_TAX_RATE",
    "DNSE_STOCK_TAX_RATE",
    "DNSE_DERIVATIVE_INITIAL_MARGIN_RATE",
)

# Nội dung do người dùng/chuyên gia nhập và kết quả AI; không đưa lên GitHub.
PRIVATE_FILES = {
    "advisor": (
        "user_context.md",
        "expert_context.md",
        "advisor_response.md",
    ),
    "ckcs_research": ("private_context.md",),
}

# Không thuộc cả hai vùng. Người dùng tự nhập lại bằng UI trên máy đích.
NEVER_EXPORT = (
    ".env và mọi API key/token/OTP",
    "advisor_api_settings.json",
    "telegram_settings.json và Telegram Chat ID",
    "DNSE account/token",
    "lệnh, vị thế, PNL, PAPER, lịch sử, log, cache và CKCS RAW DATA",
)

IGNORED_ACCOUNT_DIRS = {"copy", "logs", "paper", "templates"}
SENSITIVE_KEY_PARTS = (
    "api_key",
    "api_secret",
    "access_token",
    "refresh_token",
    "trading_token",
    "bot_token",
    "password",
    "passcode",
    "otp",
    "chat_id",
    "account_no",
    "custody",
)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(path: Path) -> Path:
    if path.is_absolute() or ".." in path.parts or path.name.lower() == ".env":
        raise ValueError(f"Đường dẫn không hợp lệ: {path}")
    return path


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key or "").strip().lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _sanitize_public_json(value: Any) -> Any:
    """Phòng trường hợp một secret bị thêm nhầm vào JSON public sau này."""
    if isinstance(value, dict):
        return {
            key: _sanitize_public_json(item)
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_public_json(item) for item in value]
    return value


def _allowed_relative(path: Path, category: str) -> bool:
    path = _safe_relative(path)
    if category == "public":
        if len(path.parts) == 1:
            return path.name in PUBLIC_ROOT_FILES or path.name == PUBLIC_PORTABLE_FILE
        if len(path.parts) == 2 and path.parts[0] == "advisor":
            return path.parts[1] in PUBLIC_ADVISOR_FILES
        return path.parts[0] == "templates" and path.suffix.lower() == ".json"
    if category == "private":
        return (
            len(path.parts) == 2
            and path.parts[0] in PRIVATE_FILES
            and path.parts[1] in PRIVATE_FILES[path.parts[0]]
        )
    return False


def discover_accounts(data_root: Path = DATA_ROOT) -> list[Path]:
    if not data_root.exists():
        return []
    accounts: list[Path] = []
    for child in data_root.iterdir():
        if not child.is_dir() or child.name.lower() in IGNORED_ACCOUNT_DIRS:
            continue
        has_settings = any((child / name).is_file() for name in PUBLIC_ROOT_FILES)
        if child.name.isdigit() or child.name.upper() == "PAPER" or has_settings:
            accounts.append(child)
    return sorted(accounts, key=lambda item: item.name)


def collect_setting_files(account_dir: Path, category: str) -> list[Path]:
    found: list[Path] = []
    if category == "public":
        for name in PUBLIC_ROOT_FILES:
            if (account_dir / name).is_file():
                found.append(Path(name))
        for name in PUBLIC_ADVISOR_FILES:
            relative = Path("advisor") / name
            if (account_dir / relative).is_file():
                found.append(relative)
        template_root = account_dir / "templates"
        if template_root.is_dir():
            for path in sorted(template_root.rglob("*.json")):
                if path.is_file():
                    found.append(path.relative_to(account_dir))
    elif category == "private":
        for folder, names in PRIVATE_FILES.items():
            for name in names:
                relative = Path(folder) / name
                if (account_dir / relative).is_file():
                    found.append(relative)
    else:
        raise ValueError("Loại gói phải là public hoặc private.")
    return sorted(dict.fromkeys(found), key=lambda item: item.as_posix())


def _copy_export_file(source: Path, target: Path, category: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if category == "public" and source.suffix.lower() == ".json":
        with source.open("r", encoding="utf-8-sig") as handle:
            clean = _sanitize_public_json(json.load(handle))
        with target.open("w", encoding="utf-8") as handle:
            json.dump(clean, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        return
    shutil.copy2(source, target)


def _read_env_values(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _write_safe_env_values(env_path: Path, values: dict[str, object]) -> None:
    """Chỉ cập nhật whitelist vô hại, giữ nguyên secret đang có trên máy đích."""
    clean = {
        str(key): str(value)
        for key, value in values.items()
        if key in PUBLIC_ENV_KEYS and not _is_sensitive_key(key)
    }
    if not clean:
        return
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.is_file() else []
    output: list[str] = []
    applied: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in clean:
                if key not in applied:
                    output.append(f"{key}={clean[key]}")
                    applied.add(key)
                continue
        output.append(line)
    for key in PUBLIC_ENV_KEYS:
        if key in clean and key not in applied:
            output.append(f"{key}={clean[key]}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    temp = env_path.with_name(f".{env_path.name}.settings.tmp")
    temp.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.replace(temp, env_path)


def _next_package_id(public_root: Path, private_root: Path, stamp: str | None) -> str:
    base = f"settings_{stamp or _timestamp()}"
    candidate = base
    index = 2
    while (public_root / candidate).exists() or (private_root / candidate).exists():
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def ensure_copy_layout(copy_root: Path = COPY_ROOT) -> None:
    """Chỉ bảo đảm hai thư mục PUBLIC/PRIVATE tồn tại."""
    copy_root = Path(copy_root)
    (copy_root / "public").mkdir(parents=True, exist_ok=True)
    (copy_root / "private").mkdir(parents=True, exist_ok=True)


def _export_category(
    account_dir: Path,
    category: str,
    package_id: str,
    destination_root: Path,
    env_path: Path,
) -> Path:
    files = collect_setting_files(account_dir, category)
    package_dir = destination_root / package_id
    package_dir.mkdir(parents=True, exist_ok=False)
    hashes: dict[str, str] = {}
    for relative in files:
        if not _allowed_relative(relative, category):
            continue
        source = account_dir / relative
        target = package_dir / relative
        _copy_export_file(source, target, category)
        hashes[relative.as_posix()] = _sha256(target)

    if category == "public":
        portable = {
            key: value
            for key, value in _read_env_values(env_path).items()
            if key in PUBLIC_ENV_KEYS and not _is_sensitive_key(key)
        }
        portable_target = package_dir / PUBLIC_PORTABLE_FILE
        with portable_target.open("w", encoding="utf-8") as handle:
            json.dump(portable, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        hashes[PUBLIC_PORTABLE_FILE] = _sha256(portable_target)

    manifest = {
        "version": 2,
        "package_id": package_id,
        "category": category,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # Không ghi account nguồn để gói PUBLIC không lộ số tài khoản.
        "files": list(hashes),
        "sha256": hashes,
        "never_exported": list(NEVER_EXPORT),
    }
    with (package_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return package_dir


def export_split_settings(
    account_dir: Path,
    copy_root: Path = COPY_ROOT,
    stamp: str | None = None,
    env_path: Path | None = None,
) -> dict[str, Any]:
    """Tạo một cặp gói PUBLIC/PRIVATE có cùng package_id."""
    account_dir = Path(account_dir).resolve()
    if not account_dir.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục tài khoản: {account_dir}")
    ensure_copy_layout(copy_root)
    public_root = Path(copy_root) / "public"
    private_root = Path(copy_root) / "private"
    public_root.mkdir(parents=True, exist_ok=True)
    private_root.mkdir(parents=True, exist_ok=True)
    env_path = Path(env_path) if env_path is not None else PROJECT_ROOT / ".env"
    package_id = _next_package_id(public_root, private_root, stamp)
    public_dir = _export_category(account_dir, "public", package_id, public_root, env_path)
    try:
        private_dir = _export_category(account_dir, "private", package_id, private_root, env_path)
    except Exception:
        shutil.rmtree(public_dir, ignore_errors=True)
        raise
    return {
        "package_id": package_id,
        "public_dir": public_dir,
        "private_dir": private_dir,
        "public_files": load_manifest(public_dir)["files"],
        "private_files": load_manifest(private_dir)["files"],
    }


# Tương thích lệnh/test cũ: export_settings trả về phần PUBLIC.
def export_settings(
    account_dir: Path,
    copy_root: Path = COPY_ROOT,
    stamp: str | None = None,
    env_path: Path | None = None,
) -> Path:
    return Path(export_split_settings(account_dir, copy_root, stamp, env_path)["public_dir"])


def discover_packages(copy_root: Path = COPY_ROOT, category: str = "public") -> list[Path]:
    root = Path(copy_root) / category
    if not root.exists():
        return []
    packages = [path for path in root.iterdir() if path.is_dir() and (path / "manifest.json").is_file()]
    return sorted(packages, key=lambda item: item.name, reverse=True)


def load_manifest(package_dir: Path) -> dict[str, Any]:
    manifest_path = Path(package_dir) / "manifest.json"
    with manifest_path.open("r", encoding="utf-8-sig") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("Gói setting không có manifest hợp lệ.")
    if manifest.get("category") not in {"public", "private"}:
        raise ValueError("Manifest không ghi đúng loại public/private.")
    return manifest


def validate_package(package_dir: Path) -> dict[str, Any]:
    package_dir = Path(package_dir).resolve()
    manifest = load_manifest(package_dir)
    category = str(manifest["category"])
    expected_hashes = manifest.get("sha256", {})
    if not isinstance(expected_hashes, dict):
        raise ValueError("Manifest thiếu bảng kiểm tra file.")
    checked: list[str] = []
    for raw in manifest["files"]:
        relative = _safe_relative(Path(str(raw)))
        if not _allowed_relative(relative, category):
            raise ValueError(f"File không được phép trong gói {category}: {relative}")
        source = (package_dir / relative).resolve()
        try:
            source.relative_to(package_dir)
        except ValueError as exc:
            raise ValueError(f"File nằm ngoài gói: {relative}") from exc
        if not source.is_file():
            raise FileNotFoundError(f"Thiếu file: {relative}")
        if source.suffix.lower() == ".json":
            with source.open("r", encoding="utf-8-sig") as handle:
                json.load(handle)
        expected = str(expected_hashes.get(relative.as_posix(), ""))
        if not expected or _sha256(source) != expected:
            raise ValueError(f"File đã bị sửa hoặc hỏng: {relative}")
        checked.append(relative.as_posix())
    return {
        "valid": True,
        "category": category,
        "package_id": str(manifest.get("package_id") or package_dir.name),
        "files": checked,
    }


def import_settings(
    package_dir: Path,
    target_account_dir: Path,
    copy_root: Path = COPY_ROOT,
    stamp: str | None = None,
    env_path: Path | None = None,
) -> dict[str, Any]:
    package_dir = Path(package_dir).resolve()
    target_account_dir = Path(target_account_dir).resolve()
    check = validate_package(package_dir)
    manifest = load_manifest(package_dir)
    category = check["category"]
    stamp = stamp or _timestamp()
    env_path = Path(env_path) if env_path is not None else PROJECT_ROOT / ".env"
    backup_dir = Path(copy_root) / "_backups" / f"{target_account_dir.name}_{stamp}"
    restored: list[str] = []
    backed_up: list[str] = []

    for raw in manifest["files"]:
        relative = _safe_relative(Path(str(raw)))
        if not _allowed_relative(relative, category):
            continue
        source = package_dir / relative
        if category == "public" and relative.as_posix() == PUBLIC_PORTABLE_FILE:
            if env_path.is_file():
                backup = backup_dir / category / ".env"
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(env_path, backup)
                backed_up.append(".env (chỉ backup cục bộ)")
            with source.open("r", encoding="utf-8-sig") as handle:
                portable = json.load(handle)
            if not isinstance(portable, dict):
                raise ValueError("portable_settings.json không hợp lệ.")
            _write_safe_env_values(env_path, portable)
            restored.append("watchlist/cấu hình chung")
            continue
        target = target_account_dir / relative
        if target.is_file():
            backup = backup_dir / category / relative
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
        "category": category,
        "package_id": check["package_id"],
        "target_account": target_account_dir.name,
    }


def import_split_settings(
    public_package_dir: Path,
    target_account_dir: Path,
    copy_root: Path = COPY_ROOT,
    include_private: bool = True,
    env_path: Path | None = None,
) -> dict[str, Any]:
    public_check = validate_package(public_package_dir)
    if public_check["category"] != "public":
        raise ValueError("Hãy chọn manifest trong thư mục public.")
    stamp = _timestamp()
    public_result = import_settings(public_package_dir, target_account_dir, copy_root, stamp, env_path)
    private_result = None
    private_dir = Path(copy_root) / "private" / public_check["package_id"]
    if include_private and (private_dir / "manifest.json").is_file():
        private_result = import_settings(private_dir, target_account_dir, copy_root, stamp, env_path)
    return {
        "package_id": public_check["package_id"],
        "public": public_result,
        "private": private_result,
        "restored": len(public_result["restored"]) + (len(private_result["restored"]) if private_result else 0),
    }


def delete_package(package_dir: Path, copy_root: Path = COPY_ROOT, delete_pair: bool = True) -> list[str]:
    """Chỉ xóa gói dưới data/copy; không bao giờ đụng dữ liệu tài khoản."""
    package_dir = Path(package_dir).resolve()
    copy_root = Path(copy_root).resolve()
    check = validate_package(package_dir)
    try:
        package_dir.relative_to(copy_root)
    except ValueError as exc:
        raise ValueError("Chỉ được xóa gói nằm trong data/copy.") from exc
    targets = [package_dir]
    if delete_pair:
        other = "private" if check["category"] == "public" else "public"
        pair = copy_root / other / check["package_id"]
        if (pair / "manifest.json").is_file():
            validate_package(pair)
            targets.append(pair)
    removed: list[str] = []
    for target in targets:
        shutil.rmtree(target)
        removed.append(str(target))
    return removed


def open_copy_folder(copy_root: Path = COPY_ROOT) -> None:
    root = Path(copy_root)
    ensure_copy_layout(root)
    if os.name == "nt":
        os.startfile(str(root.resolve()))  # type: ignore[attr-defined]
    else:
        raise OSError("Nút mở thư mục hiện chỉ hỗ trợ Windows.")


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
    result = export_split_settings(account)
    print(f"Đã tạo {result['package_id']}.")
    print(f"PUBLIC: {len(result['public_files'])} file — có thể đưa GitHub.")
    print(f"PRIVATE: {len(result['private_files'])} file — tự sao chép, không đưa GitHub.")


def _menu_import() -> None:
    package = _choose("CHỌN GÓI PUBLIC", discover_packages())
    if package is None:
        return
    target = _choose("CHỌN TÀI KHOẢN ĐÍCH", discover_accounts())
    if target is None:
        return
    if input(f"Khôi phục vào {target.name}? Gõ YES: ").strip().upper() != "YES":
        print("Đã hủy.")
        return
    result = import_split_settings(package, target)
    print(f"Đã khôi phục {result['restored']} file. Hãy mở lại app.")


def _menu_check() -> None:
    package = _choose("CHỌN GÓI PUBLIC", discover_packages())
    if package is None:
        return
    public = validate_package(package)
    private_dir = PRIVATE_COPY_ROOT / public["package_id"]
    private_count = 0
    if (private_dir / "manifest.json").is_file():
        private_count = len(validate_package(private_dir)["files"])
    print(f"Gói hợp lệ: PUBLIC {len(public['files'])} file, PRIVATE {private_count} file.")


def _menu_delete() -> None:
    package = _choose("CHỌN GÓI CẦN XÓA", discover_packages())
    if package is None:
        return
    if input("Xóa cả cặp PUBLIC/PRIVATE? Gõ DELETE: ").strip().upper() != "DELETE":
        print("Đã hủy.")
        return
    delete_package(package)
    print("Đã xóa gói.")


def main() -> int:
    if os.name == "nt":
        os.system("chcp 65001 >nul")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ensure_copy_layout()
    while True:
        print("\n=== RAT-CKVN COPY SETTING ===")
        print("1. Tạo bản sao PUBLIC + PRIVATE")
        print("2. Khôi phục vào tài khoản")
        print("3. Kiểm tra gói")
        print("4. Xóa gói")
        print("5. Mở thư mục")
        print("0. Thoát")
        choice = input("Chọn: ").strip()
        try:
            if choice == "1":
                _menu_export()
            elif choice == "2":
                _menu_import()
            elif choice == "3":
                _menu_check()
            elif choice == "4":
                _menu_delete()
            elif choice == "5":
                open_copy_folder()
            elif choice == "0":
                return 0
            else:
                print("Lựa chọn không hợp lệ.")
        except Exception as exc:  # noqa: BLE001
            print(f"LỖI: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())

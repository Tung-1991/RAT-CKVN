from pathlib import Path

import settings_transfer


def _write(path: Path, text="{}"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_export_only_copies_settings_and_context(tmp_path):
    data_root = tmp_path / "data"
    account = data_root / "123456"
    _write(account / "brain_settings.json", '{"BOT": true}')
    _write(account / "tsl_settings.json")
    _write(account / "advisor" / "expert_context.md", "expert")
    _write(account / "ckcs_research" / "private_context.md", "private")
    _write(account / "templates" / "custom.json", '{"x": 1}')
    _write(account / ".env", "DNSE_API_KEY=secret")
    _write(account / "bot_state.json", '{"position": 1}')
    _write(account / "ckcs_research" / "scan_snapshot_cache.json", '{"raw": true}')

    package = settings_transfer.export_settings(
        account,
        copy_root=data_root / "copy",
        stamp="20260722_120000",
    )

    assert (package / "brain_settings.json").is_file()
    assert (package / "advisor" / "expert_context.md").is_file()
    assert (package / "ckcs_research" / "private_context.md").is_file()
    assert (package / "templates" / "custom.json").is_file()
    assert not (package / ".env").exists()
    assert not (package / "bot_state.json").exists()
    assert not (package / "ckcs_research" / "scan_snapshot_cache.json").exists()


def test_import_lists_target_and_backs_up_existing_setting(tmp_path):
    data_root = tmp_path / "data"
    source = data_root / "111"
    target = data_root / "222"
    _write(source / "brain_settings.json", '{"source": true}')
    _write(target / "brain_settings.json", '{"target": true}')
    package = settings_transfer.export_settings(
        source,
        copy_root=data_root / "copy",
        stamp="20260722_120000",
    )

    result = settings_transfer.import_settings(
        package,
        target,
        copy_root=data_root / "copy",
        stamp="20260722_120100",
    )

    assert (target / "brain_settings.json").read_text(encoding="utf-8") == '{"source": true}'
    backup = Path(result["backup_dir"]) / "brain_settings.json"
    assert backup.read_text(encoding="utf-8") == '{"target": true}'
    assert result["target_account"] == "222"


def test_discover_accounts_excludes_runtime_directories(tmp_path):
    data_root = tmp_path / "data"
    _write(data_root / "123" / "brain_settings.json")
    _write(data_root / "named-account" / "brain_settings.json")
    _write(data_root / "copy" / "pkg" / "manifest.json")
    _write(data_root / "paper" / "123_state.json")

    assert [item.name for item in settings_transfer.discover_accounts(data_root)] == [
        "123",
        "named-account",
    ]

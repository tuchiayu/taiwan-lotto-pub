from __future__ import annotations

from datetime import date

import pytest

import taiwan_lotto.main as main_module
from taiwan_lotto.main import cli, get_version, main, run_sync, run_web_command
from taiwan_lotto.models import LOTTO_649, SUPER_LOTTO_638, GameSyncResult, SyncCounts
from taiwan_lotto.storage.sqlite import StorageError


def test_version_prefers_app_version(monkeypatch) -> None:
    monkeypatch.setenv("APP_VERSION", "v1.2.3")

    assert get_version() == "v1.2.3"


def test_no_command_prints_help(capsys) -> None:
    exit_code = main([])

    assert exit_code == 0
    assert "usage:" in capsys.readouterr().out


def test_help_flag_prints_usage(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert "usage: taiwan-lotto" in output
    assert "--version" in output
    assert "sync" in output
    assert "web" in output


def test_sync_command_dispatches_to_sync_runner(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "run_sync", lambda: 7)

    assert main(["sync"]) == 7


def test_web_command_uses_representative_default_port(monkeypatch) -> None:
    received = {}
    events = []

    def fake_run_web(database_path, *, port, open_browser) -> int:
        events.append("web")
        received.update(
            database_path=database_path,
            port=port,
            open_browser=open_browser,
        )
        return 0

    def fake_run_sync(_database_path) -> int:
        events.append("sync")
        return 0

    monkeypatch.setattr(main_module, "run_web", fake_run_web)
    monkeypatch.setattr(main_module, "run_sync", fake_run_sync)

    assert main(["web"]) == 0
    assert events == ["sync", "web"]
    assert received == {
        "database_path": main_module.DEFAULT_DATABASE_PATH,
        "port": 4938,
        "open_browser": True,
    }


def test_web_command_accepts_port_and_no_browser(monkeypatch) -> None:
    received = {}

    def fake_run_web(database_path, *, port, open_browser) -> int:
        received.update(port=port, open_browser=open_browser)
        return 0

    monkeypatch.setattr(main_module, "run_web", fake_run_web)
    monkeypatch.setattr(main_module, "run_sync", lambda _database_path: 0)

    assert main(["web", "--port", "5049", "--no-browser"]) == 0
    assert received == {"port": 5049, "open_browser": False}


def test_web_command_no_sync_skips_sync_runner(monkeypatch) -> None:
    sync_called = False

    def fake_run_sync(_database_path) -> int:
        nonlocal sync_called
        sync_called = True
        return 0

    monkeypatch.setattr(main_module, "run_sync", fake_run_sync)
    monkeypatch.setattr(main_module, "run_web", lambda *_args, **_kwargs: 0)

    assert main(["web", "--no-sync"]) == 0
    assert sync_called is False


@pytest.mark.parametrize("port", ["0", "65536", "word"])
def test_web_command_rejects_invalid_port(port) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["web", "--port", port])

    assert exit_info.value.code == 2


def test_web_command_reports_startup_error(monkeypatch, capsys) -> None:
    def fail(*_args, **_kwargs):
        raise main_module.WebServerError("port unavailable")

    monkeypatch.setattr(main_module, "run_web", fail)
    monkeypatch.setattr(main_module, "run_sync", lambda _database_path: 0)

    assert main(["web"]) == 1
    assert "port unavailable" in capsys.readouterr().err


def test_run_web_command_starts_with_existing_database_after_sync_failure(
    monkeypatch, tmp_path, capsys
) -> None:
    database_path = tmp_path / "taiwan_lotto.db"
    database_path.touch()
    web_started = False

    def fake_run_web(*_args, **_kwargs) -> int:
        nonlocal web_started
        web_started = True
        return 0

    monkeypatch.setattr(main_module, "run_sync", lambda _database_path: 1)
    monkeypatch.setattr(main_module, "run_web", fake_run_web)

    assert run_web_command(database_path) == 0
    assert web_started is True
    assert "existing local database" in capsys.readouterr().err


def test_run_web_command_stops_without_database_after_sync_failure(
    monkeypatch, tmp_path, capsys
) -> None:
    database_path = tmp_path / "taiwan_lotto.db"
    web_started = False

    def fake_run_web(*_args, **_kwargs) -> int:
        nonlocal web_started
        web_started = True
        return 0

    monkeypatch.setattr(main_module, "run_sync", lambda _database_path: 1)
    monkeypatch.setattr(main_module, "run_web", fake_run_web)

    assert run_web_command(database_path) == 1
    assert web_started is False
    assert "no local database is available" in capsys.readouterr().err


def test_run_web_command_no_sync_allows_missing_database(monkeypatch, tmp_path) -> None:
    database_path = tmp_path / "taiwan_lotto.db"
    received = {}

    def fake_run_web(path, *, port, open_browser) -> int:
        received.update(path=path, port=port, open_browser=open_browser)
        return 0

    monkeypatch.setattr(main_module, "run_sync", pytest.fail)
    monkeypatch.setattr(main_module, "run_web", fake_run_web)

    assert run_web_command(database_path, sync_before_start=False) == 0
    assert received["path"] == database_path


def test_run_sync_prints_results_and_returns_failure(monkeypatch, capsys) -> None:
    results = [
        GameSyncResult(
            game=LOTTO_649,
            mode="incremental",
            start_month=date(2026, 1, 1),
            end_month=date(2026, 3, 1),
            counts=SyncCounts(added=1, skipped=2, corrected=3, missing=4),
            success=True,
        ),
        GameSyncResult(
            game=SUPER_LOTTO_638,
            mode="history",
            start_month=date(2008, 1, 1),
            end_month=date(2026, 3, 1),
            counts=SyncCounts(),
            success=False,
            error="source unavailable",
        ),
    ]

    class FakeSyncService:
        def __init__(self, *_args) -> None:
            pass

        def run(self) -> list[GameSyncResult]:
            return results

    monkeypatch.setattr(main_module, "SyncService", FakeSyncService)

    assert run_sync() == 1
    captured = capsys.readouterr()
    assert "大樂透: status=ok mode=incremental" in captured.out
    assert "added=1 skipped=2 corrected=3 missing=4" in captured.out
    assert "威力彩: status=failed mode=history" in captured.out
    assert "威力彩: source unavailable" in captured.err


def test_run_sync_returns_success_when_every_game_succeeds(monkeypatch) -> None:
    result = GameSyncResult(
        game=LOTTO_649,
        mode="incremental",
        start_month=date(2026, 1, 1),
        end_month=date(2026, 3, 1),
        counts=SyncCounts(),
        success=True,
    )

    class FakeSyncService:
        def __init__(self, *_args) -> None:
            pass

        def run(self) -> list[GameSyncResult]:
            return [result]

    monkeypatch.setattr(main_module, "SyncService", FakeSyncService)

    assert run_sync() == 0


def test_run_sync_reports_storage_initialization_error(monkeypatch, capsys) -> None:
    class FailingSyncService:
        def __init__(self, *_args) -> None:
            pass

        def run(self) -> list[GameSyncResult]:
            raise StorageError("database is locked")

    monkeypatch.setattr(main_module, "SyncService", FailingSyncService)

    assert run_sync() == 1
    assert "Synchronization failed: database is locked" in capsys.readouterr().err


def test_cli_configures_console_and_exits_with_main_result(monkeypatch) -> None:
    configured = False

    def configure() -> None:
        nonlocal configured
        configured = True

    monkeypatch.setattr(main_module, "_configure_console_encoding", configure)
    monkeypatch.setattr(main_module, "main", lambda: 7)

    with pytest.raises(SystemExit) as exit_info:
        cli()

    assert configured is True
    assert exit_info.value.code == 7

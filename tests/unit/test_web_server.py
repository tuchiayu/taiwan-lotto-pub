from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import taiwan_lotto.web.server as server_module
from taiwan_lotto.web.server import WebServerError, run_web


def test_run_web_configures_loopback_and_opens_browser_after_startup(
    monkeypatch, tmp_path
) -> None:
    opened = []
    received = {}

    class ImmediateTimer:
        def __init__(self, _delay, callback, args) -> None:
            self.callback = callback
            self.args = args
            self.daemon = False

        def start(self) -> None:
            self.callback(*self.args)

    def fake_runner(app, **settings) -> None:
        received.update(settings)
        with TestClient(app) as client:
            assert client.get("/").status_code == 200

    monkeypatch.setattr(server_module, "_ensure_port_available", lambda _port: None)
    monkeypatch.setattr(server_module.threading, "Timer", ImmediateTimer)

    assert (
        run_web(
            tmp_path / "missing.db",
            server_runner=fake_runner,
            browser_opener=opened.append,
        )
        == 0
    )
    assert received == {"host": "127.0.0.1", "port": 4938, "log_level": "warning"}
    assert opened == ["http://127.0.0.1:4938"]


def test_run_web_can_skip_browser(monkeypatch, tmp_path) -> None:
    opened = []
    monkeypatch.setattr(server_module, "_ensure_port_available", lambda _port: None)

    run_web(
        tmp_path / "missing.db",
        open_browser=False,
        server_runner=lambda *_args, **_kwargs: None,
        browser_opener=opened.append,
    )

    assert opened == []


def test_port_probe_reports_friendly_conflict(monkeypatch, tmp_path) -> None:
    def unavailable(_port) -> None:
        raise WebServerError("choose another port with --port")

    monkeypatch.setattr(server_module, "_ensure_port_available", unavailable)

    with pytest.raises(WebServerError, match="--port"):
        run_web(tmp_path / "missing.db")

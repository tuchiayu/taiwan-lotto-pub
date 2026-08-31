"""Programmatic Uvicorn startup for the local draw browser."""

from __future__ import annotations

import socket
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

import uvicorn

from taiwan_lotto.web.app import create_app

HOST = "127.0.0.1"
DEFAULT_PORT = 4938


class WebServerError(RuntimeError):
    """Report a user-correctable local server startup problem."""


def run_web(
    database_path: Path,
    *,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    server_runner: Callable[..., Any] = uvicorn.run,
    browser_opener: Callable[[str], Any] = webbrowser.open,
) -> int:
    """Run the local Web interface until the user stops it."""
    if not 1 <= port <= 65535:
        raise WebServerError("port must be between 1 and 65535")
    _ensure_port_available(port)
    url = f"http://{HOST}:{port}"

    def open_after_startup() -> None:
        if open_browser:
            timer = threading.Timer(0.25, browser_opener, args=(url,))
            timer.daemon = True
            timer.start()

    app = create_app(database_path, on_started=open_after_startup)
    print(f"Taiwan Lotto Lab is available at {url}")
    print("Press Ctrl+C to stop the server.")
    server_runner(app, host=HOST, port=port, log_level="warning")
    return 0


def _ensure_port_available(port: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((HOST, port))
    except OSError as error:
        raise WebServerError(
            f"{HOST}:{port} is unavailable; choose another port with --port"
        ) from error
    finally:
        probe.close()

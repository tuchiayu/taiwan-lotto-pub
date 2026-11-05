"""Serve isolated fixture data to real browsers without running synchronization."""

from collections.abc import Iterator
from datetime import date
from socket import AF_INET, SOCK_STREAM, socket
from threading import Event, Thread

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from taiwan_lotto.models import LOTTO_649, Draw
from taiwan_lotto.storage.sqlite import SQLiteStorage
from taiwan_lotto.web.app import create_app


@pytest.fixture(scope="session")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    database = tmp_path_factory.mktemp("browser-db") / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    numbers = [
        ((1, 2, 3, 4, 5, 6), 7),
        ((1, 2, 3, 8, 9, 10), 11),
        ((1, 2, 4, 8, 12, 13), 7),
        ((1, 3, 4, 9, 12, 14), 15),
    ]
    storage.save_draws(
        [
            Draw(
                game_code=LOTTO_649.code,
                draw_term=f"11500000{day}",
                draw_date=date(2026, 1, day),
                main_numbers=main,
                special_number=special,
            )
            for day, (main, special) in enumerate(numbers, start=1)
        ]
    )

    ready = Event()
    failures: list[BaseException] = []

    class TestServer(uvicorn.Server):
        async def startup(self, sockets=None) -> None:
            await super().startup(sockets=sockets)
            ready.set()

    # Keep the allocated socket open until Uvicorn takes ownership of it.
    with socket(AF_INET, SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        server = TestServer(
            uvicorn.Config(
                create_app(database),
                host="127.0.0.1",
                log_level="warning",
                timeout_graceful_shutdown=3,
            )
        )
        port = listener.getsockname()[1]

        def serve() -> None:
            try:
                server.run(sockets=[listener])
            except BaseException as error:
                failures.append(error)
            finally:
                ready.set()

        thread = Thread(target=serve, name="browser-test-server", daemon=True)
        thread.start()
        try:
            if not ready.wait(timeout=10) or not server.started or failures:
                pytest.fail(f"Browser test server failed to start: {failures}")
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            if thread.is_alive():
                server.force_exit = True
                thread.join(timeout=5)
            assert not thread.is_alive(), "Browser test server did not stop"
            assert not failures, f"Browser test server failed: {failures}"


@pytest.fixture
def stats_page(page: Page, live_server: str) -> Page:
    response = page.goto(f"{live_server}/stats?game=lotto649&table=main")
    assert response is not None and response.status == 200
    expect(page.locator("[data-range-form]")).to_have_attribute("data-enhanced", "")
    # A full-page fallback would lose this marker and could conceal broken JS.
    page.evaluate("window.__browserTestDocument = true")
    return page


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Iterator[None]:
    yield
    page = item.funcargs.get("stats_page")
    if page is not None:
        # Fail during the call phase so Playwright retains diagnostic artifacts.
        errors = page.page_errors()
        assert errors == [], f"Unhandled JavaScript errors: {errors}"
        assert page.evaluate("window.__browserTestDocument === true"), (
            "Interaction unexpectedly reloaded the document"
        )

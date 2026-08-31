from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date

from fastapi.testclient import TestClient

from taiwan_lotto.models import LOTTO_649, SUPER_LOTTO_638, Draw
from taiwan_lotto.storage.sqlite import SQLiteStorage
from taiwan_lotto.web.app import create_app


def _client(database) -> TestClient:
    return TestClient(create_app(database))


def test_missing_database_shows_action_without_creating_file(tmp_path) -> None:
    database = tmp_path / "missing.db"

    response = _client(database).get("/")

    assert response.status_code == 200
    assert "尚未找到本機開獎資料" in response.text
    assert "taiwan-lotto sync" in response.text
    assert not database.exists()


def test_empty_database_has_distinct_status(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    SQLiteStorage(database).initialize()

    response = _client(database).get("/")

    assert response.status_code == 200
    assert "大樂透目前沒有開獎紀錄" in response.text


def test_selected_game_without_draws_has_empty_status(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=SUPER_LOTTO_638.code,
                draw_term="115000001",
                draw_date=date(2026, 1, 2),
                main_numbers=(7, 14, 22, 23, 31, 35),
                special_number=7,
            )
        ]
    )

    response = _client(database).get("/", params={"game": LOTTO_649.code})

    assert response.status_code == 200
    assert "大樂透目前沒有開獎紀錄" in response.text


def test_browser_renders_draws_filters_pagination_and_security_headers(
    tmp_path,
) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=SUPER_LOTTO_638.code,
                draw_term=f"115000{term:03d}",
                draw_date=date(2026, 1, term),
                main_numbers=(35, 7, 31, 14, 23, 22),
                special_number=7,
            )
            for term in range(1, 22)
        ]
    )

    response = _client(database).get(
        "/",
        params={
            "game": SUPER_LOTTO_638.code,
            "start": "2026-01-01",
            "end": "2026-01-31",
        },
    )

    assert response.status_code == 200
    assert "威力彩開獎紀錄" in response.text
    assert "共 21 筆" in response.text
    assert "第 115000021 期" in response.text
    assert "第二區" in response.text
    assert response.text.index(">07<") < response.text.index(">14<")
    assert response.text.index(">14<") < response.text.index(">22<")
    assert response.text.index(">22<") < response.text.index(">23<")
    assert response.text.index(">23<") < response.text.index(">31<")
    assert response.text.index(">31<") < response.text.index(">35<")
    stored_draw = storage.query_draws(SUPER_LOTTO_638.code, limit=1, offset=0)[0]
    assert stored_draw.main_numbers == (35, 7, 31, 14, 23, 22)
    assert "page=2" in response.text
    assert "#results" in response.text
    assert 'id="page-jump" name="page" type="number" value="1"' in response.text
    assert 'max="2" step="1"' in response.text
    assert "開獎結果以台灣彩券官方公告為準。" in response.text
    assert "資料保存在本機" not in response.text
    assert 'name="start" type="date" value="2026-01-01"' in response.text
    assert 'min="2008-01-01"' in response.text
    assert "static/browser.js?v=" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_browser_renders_lotto_special_number(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=LOTTO_649.code,
                draw_term="115000001",
                draw_date=date(2026, 1, 2),
                main_numbers=(3, 7, 16, 19, 40, 42),
                special_number=12,
            )
        ]
    )

    response = _client(database).get("/")

    assert "特別號" in response.text
    assert ">03<" in response.text
    assert ">12<" in response.text


def test_invalid_filter_is_html_escaped(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    SQLiteStorage(database).initialize()
    unsafe = '"><script>alert("x")</script>'

    response = _client(database).get("/", params={"start": unsafe})

    assert response.status_code == 200
    assert "查詢條件有誤" in response.text
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_no_matching_results_preserve_filters(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=LOTTO_649.code,
                draw_term="115000001",
                draw_date=date(2026, 1, 2),
                main_numbers=(3, 7, 16, 19, 40, 42),
                special_number=12,
            )
        ]
    )

    response = _client(database).get(
        "/", params={"start": "2025-01-01", "end": "2025-01-31"}
    )

    assert "查無資料" in response.text
    assert 'value="2025-01-01"' in response.text
    assert 'value="2025-01-31"' in response.text


def test_page_beyond_total_pages_shows_invalid_state(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=LOTTO_649.code,
                draw_term="115000001",
                draw_date=date(2026, 1, 2),
                main_numbers=(3, 7, 16, 19, 40, 42),
                special_number=12,
            )
        ]
    )

    response = _client(database).get("/", params={"page": "2"})

    assert response.status_code == 200
    assert "查詢條件有誤" in response.text
    assert "超出範圍" in response.text


def test_extremely_large_page_does_not_crash(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    SQLiteStorage(database).initialize()

    response = _client(database).get("/", params={"page": "9" * 30})

    assert response.status_code == 200
    assert "查詢條件有誤" in response.text


def test_broken_schema_returns_safe_service_error(tmp_path) -> None:
    database = tmp_path / "broken.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE private_data (value TEXT)")

    response = _client(database).get("/")

    assert response.status_code == 503
    assert "無法讀取本機資料" in response.text
    assert str(database) not in response.text
    assert "traceback" not in response.text.lower()


def test_packaged_static_asset_is_served(tmp_path) -> None:
    response = _client(tmp_path / "missing.db").get("/static/app.css")

    assert response.status_code == 200
    assert "--brand:" in response.text


def test_nav_marks_active_page(tmp_path) -> None:
    client = _client(tmp_path / "missing.db")

    draws_response = client.get("/")
    stats_response = client.get("/stats")

    assert '<a href="/?game=lotto649" aria-current="page">' in draws_response.text
    assert '<a href="/stats?game=lotto649" aria-current="page">' in stats_response.text


def test_stats_missing_database_shows_action_without_creating_file(tmp_path) -> None:
    database = tmp_path / "missing.db"

    response = _client(database).get("/stats")

    assert response.status_code == 200
    assert "尚未找到本機開獎資料" in response.text
    assert not database.exists()


def test_stats_empty_database_has_distinct_status(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    SQLiteStorage(database).initialize()

    response = _client(database).get("/stats")

    assert response.status_code == 200
    assert "大樂透目前沒有開獎紀錄" in response.text


def test_stats_selected_game_without_draws_has_empty_status(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=SUPER_LOTTO_638.code,
                draw_term="115000001",
                draw_date=date(2026, 1, 2),
                main_numbers=(7, 14, 22, 23, 31, 35),
                special_number=7,
            )
        ]
    )

    response = _client(database).get("/stats", params={"game": LOTTO_649.code})

    assert response.status_code == 200
    assert "大樂透目前沒有開獎紀錄" in response.text


def test_stats_renders_frequencies_and_total_draws(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=SUPER_LOTTO_638.code,
                draw_term="115000001",
                draw_date=date(2026, 1, 2),
                main_numbers=(7, 14, 22, 23, 31, 35),
                special_number=7,
            ),
            Draw(
                game_code=SUPER_LOTTO_638.code,
                draw_term="115000002",
                draw_date=date(2026, 1, 9),
                main_numbers=(7, 14, 22, 23, 31, 36),
                special_number=8,
            ),
        ]
    )

    response = _client(database).get(
        "/stats",
        params={
            "game": SUPER_LOTTO_638.code,
            "range": "date",
            "start": "2026-01-01",
            "end": "2026-01-09",
        },
    )

    assert response.status_code == 200
    assert "威力彩統計資料" in response.text
    assert "共 2 期" in response.text
    assert "第二區" in response.text
    assert 'name="start" type="date" value="2026-01-01"' in response.text
    assert "與理論差異" in response.text
    assert "連續未開" in response.text
    assert "統計資料僅供參考，不代表未來開獎結果" in response.text
    numbers_shown = response.text.count('class="number-ball')
    assert numbers_shown == (
        SUPER_LOTTO_638.main_number_max + SUPER_LOTTO_638.special_number_max
    )

    special = _client(database).get(
        "/stats", params={"game": SUPER_LOTTO_638.code, "table": "special"}
    )
    assert 'aria-label="第二區統計"' in special.text
    assert special.text.count('class="number-ball') == (
        SUPER_LOTTO_638.main_number_max + SUPER_LOTTO_638.special_number_max
    )


def test_stats_invalid_filter_is_html_escaped(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    SQLiteStorage(database).initialize()
    unsafe = '"><script>alert("x")</script>'

    response = _client(database).get(
        "/stats", params={"range": "date", "start": unsafe}
    )

    assert response.status_code == 200
    assert "查詢條件有誤" in response.text
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_stats_no_matching_results_preserve_filters(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=LOTTO_649.code,
                draw_term="115000001",
                draw_date=date(2026, 1, 2),
                main_numbers=(3, 7, 16, 19, 40, 42),
                special_number=12,
            )
        ]
    )

    response = _client(database).get(
        "/stats",
        params={
            "range": "date",
            "start": "2025-01-01",
            "end": "2025-01-31",
        },
    )

    assert "查無資料" in response.text
    assert 'value="2025-01-01"' in response.text
    assert 'value="2025-01-31"' in response.text


def test_stats_recent_range_and_short_history_notice(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=LOTTO_649.code,
                draw_term=f"11500000{term}",
                draw_date=date(2026, 1, term),
                main_numbers=(1, 2, 3, 4, 5, term + 6),
                special_number=term + 10,
            )
            for term in range(1, 4)
        ]
    )

    recent = _client(database).get("/stats", params={"range": "recent", "draws": "2"})
    assert "共 2 期" in recent.text
    assert 'value="recent" checked' in recent.text
    assert 'name="draws" type="number" value="2"' in recent.text

    oversized = _client(database).get(
        "/stats", params={"range": "recent", "draws": "100"}
    )
    assert "要求最近 100 期，目前只有 3 期" in oversized.text
    assert "因此顯示全部 3 期" in oversized.text


def test_stats_range_controls_and_sort_links_are_defensive(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=LOTTO_649.code,
                draw_term="115000001",
                draw_date=date(2026, 1, 2),
                main_numbers=(3, 7, 16, 19, 40, 42),
                special_number=12,
            )
        ]
    )

    response = _client(database).get("/stats")

    assert 'value="all" checked' in response.text
    assert 'min="1" max="1000000" step="1"' in response.text
    assert 'aria-sort="descending"' in response.text
    assert "main_sort=count" in response.text
    assert "main_order=asc" in response.text
    assert "table=main" in response.text
    assert "special_sort=count" in response.text
    assert "table=special" in response.text
    assert 'role="tablist" aria-label="統計號碼類型"' in response.text
    assert 'id="main-tab" role="tab" tabindex="0" aria-selected="true"' in response.text
    assert (
        'id="special-tab" role="tab" tabindex="-1" aria-selected="false"'
        in response.text
    )
    assert 'id="main-panel" role="tabpanel" aria-labelledby="main-tab"' in response.text
    assert 'id="special-panel" role="tabpanel"' in response.text
    assert 'data-table-panel="special"' in response.text
    assert "統計資料僅供參考，不代表未來開獎結果" in response.text
    assert "修改條件" in response.text
    assert "static/stats.js?v=" in response.text
    assert "static/app.css?v=" in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]

    special = _client(database).get("/stats", params={"table": "special"})
    assert 'name="table" value="special"' in special.text
    assert (
        'id="main-tab" role="tab" tabindex="-1" aria-selected="false"' in special.text
    )
    assert (
        'id="special-tab" role="tab" tabindex="0" aria-selected="true"' in special.text
    )
    assert 'id="main-panel" role="tabpanel"' in special.text
    assert 'id="special-panel" role="tabpanel" aria-labelledby="special-tab"' in (
        special.text
    )
    assert 'data-table-panel="main"' in special.text

    invalid = _client(database).get("/stats", params={"table": "unknown"})
    assert 'name="table" value="main"' in invalid.text
    assert 'id="main-tab" role="tab" tabindex="0" aria-selected="true"' in invalid.text


def test_stats_rejects_invalid_recent_count_and_sort(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    SQLiteStorage(database).initialize()

    invalid_count = _client(database).get(
        "/stats", params={"range": "recent", "draws": "-1"}
    )
    assert "查詢條件有誤" in invalid_count.text
    assert "正整數" in invalid_count.text

    invalid_sort = _client(database).get("/stats", params={"main_sort": "drop table"})
    assert "查詢條件有誤" in invalid_sort.text
    assert "排序方式" in invalid_sort.text


def test_stats_broken_schema_returns_safe_service_error(tmp_path) -> None:
    database = tmp_path / "broken.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE private_data (value TEXT)")

    response = _client(database).get("/stats")

    assert response.status_code == 503
    assert "無法讀取本機資料" in response.text
    assert str(database) not in response.text
    assert "traceback" not in response.text.lower()

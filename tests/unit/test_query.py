from __future__ import annotations

from datetime import date
from unittest.mock import Mock, call

import pytest

from taiwan_lotto.models import LOTTO_649, SUPPORTED_GAMES, Draw
from taiwan_lotto.query import (
    MAX_PAGE_NUMBER,
    MAX_RECENT_DRAWS,
    DrawQueryService,
    NumberFrequency,
    QueryValidationError,
    StatsQueryService,
)


class FakeStorage:
    def __init__(self, *, count: int = 1) -> None:
        self.count = count
        self.query_args = None
        self.latest_date_game_code = None
        self.draws: list[Draw] = []

    def count_draws(self, game_code, start_date=None, end_date=None) -> int:
        return self.count

    def query_draws(
        self, game_code, start_date=None, end_date=None, *, limit, offset
    ) -> list[Draw]:
        self.query_args = (game_code, start_date, end_date, limit, offset)
        return self.draws[offset : offset + limit]

    def latest_available_draw_date(self, game_code: str) -> date:
        self.latest_date_game_code = game_code
        return date(2026, 8, 25)


def _stats_draw(
    term: int,
    *,
    main_numbers: tuple[int, int, int, int, int, int],
    special_number: int,
) -> Draw:
    return Draw(
        game_code=LOTTO_649.code,
        draw_term=f"115000{term:03d}",
        draw_date=date(2026, 1, term),
        main_numbers=main_numbers,
        special_number=special_number,
    )


def test_query_service_parses_filters_and_pagination() -> None:
    storage = FakeStorage(count=41)
    service = DrawQueryService(storage)

    result = service.search(
        game_code=LOTTO_649.code,
        start="2026-01-01",
        end="2026-08-25",
        page="2",
    )

    assert result.total_pages == 3
    assert result.page == 2
    assert storage.query_args == (
        LOTTO_649.code,
        date(2026, 1, 1),
        date(2026, 8, 25),
        20,
        20,
    )
    assert storage.latest_date_game_code == LOTTO_649.code


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"game_code": "unknown"}, "有效的彩券種類"),
        ({"start": "not-a-date"}, "YYYY-MM-DD"),
        ({"start": "2026-02-01", "end": "2026-01-01"}, "不可晚於"),
        ({"page": "zero"}, "正整數"),
        ({"page": "0"}, "正整數"),
        ({"page": str(MAX_PAGE_NUMBER + 1)}, "正整數"),
    ],
)
def test_query_service_rejects_invalid_browser_input(arguments, message) -> None:
    with pytest.raises(QueryValidationError, match=message):
        DrawQueryService(FakeStorage()).search(**arguments)


def test_query_service_rejects_page_beyond_total_pages() -> None:
    storage = FakeStorage(count=41)

    with pytest.raises(QueryValidationError, match="超出範圍"):
        DrawQueryService(storage).search(page="4")

    assert storage.query_args is None


def test_query_service_represents_empty_results() -> None:
    result = DrawQueryService(FakeStorage(count=0)).search()

    assert result.items == ()
    assert result.total_pages == 0
    assert result.latest_draw_date == date(2026, 8, 25)


def test_stats_service_calculates_frequency_expectation_and_missing_runs() -> None:
    storage = FakeStorage(count=4)
    storage.draws = [
        _stats_draw(4, main_numbers=(2, 3, 4, 5, 6, 7), special_number=8),
        _stats_draw(3, main_numbers=(1, 3, 4, 5, 6, 7), special_number=7),
        _stats_draw(2, main_numbers=(2, 3, 4, 5, 6, 7), special_number=8),
        _stats_draw(1, main_numbers=(1, 3, 4, 5, 6, 7), special_number=7),
    ]

    result = StatsQueryService(storage).search(game_code=LOTTO_649.code)

    assert result.total_draws == 4
    assert len(result.main_frequencies) == LOTTO_649.main_number_max
    number_one = next(item for item in result.main_frequencies if item.number == 1)
    assert number_one == NumberFrequency(
        number=1,
        count=2,
        rate=0.5,
        expected_difference=2 - (4 * 6 / 49),
        last_seen_date=date(2026, 1, 3),
        current_missing_draws=1,
        longest_missing_draws=1,
    )
    number_49 = next(item for item in result.main_frequencies if item.number == 49)
    assert number_49.current_missing_draws == 4
    assert number_49.longest_missing_draws == 4
    assert number_49.last_seen_date is None
    assert len(result.special_frequencies) == LOTTO_649.special_number_max
    assert result.main_theoretical_rate == 6 / 49
    assert result.special_theoretical_rate == 1 / 49
    assert storage.latest_date_game_code == LOTTO_649.code
    assert storage.query_args == (LOTTO_649.code, None, None, 4, 0)


def test_stats_service_uses_recent_draw_limit_and_reports_short_history() -> None:
    storage = FakeStorage(count=2)
    storage.draws = [
        _stats_draw(2, main_numbers=(1, 2, 3, 4, 5, 6), special_number=7),
        _stats_draw(1, main_numbers=(7, 8, 9, 10, 11, 12), special_number=13),
    ]

    result = StatsQueryService(storage).search(range_mode="recent", draws="100")

    assert result.total_draws == 2
    assert result.requested_draws == 100
    assert result.range_notice == (
        "要求最近 100 期，目前只有 2 期，因此顯示全部 2 期。"
    )
    assert storage.query_args == (LOTTO_649.code, None, None, 2, 0)


def test_stats_service_date_mode_and_empty_dates() -> None:
    storage = FakeStorage(count=3)

    result = StatsQueryService(storage).search(
        range_mode="date", start="2026-01-01", end="2026-08-25"
    )

    assert result.range_mode == "date"
    assert storage.query_args == (
        LOTTO_649.code,
        date(2026, 1, 1),
        date(2026, 8, 25),
        3,
        0,
    )
    assert (
        StatsQueryService(FakeStorage(count=0)).search(range_mode="date").range_mode
        == "all"
    )


def test_stats_service_ignores_inactive_range_parameters() -> None:
    result = StatsQueryService(FakeStorage(count=0)).search(
        range_mode="all", start="not-a-date", end="not-a-date", draws="invalid"
    )
    assert result.range_mode == "all"

    result = StatsQueryService(FakeStorage(count=0)).search(
        range_mode="recent", draws="10", start="not-a-date", end="not-a-date"
    )
    assert result.range_mode == "recent"


def test_stats_service_sorts_tables_independently() -> None:
    storage = FakeStorage(count=1)
    storage.draws = [_stats_draw(1, main_numbers=(1, 2, 3, 4, 5, 6), special_number=7)]

    result = StatsQueryService(storage).search(
        main_sort="current_missing_draws",
        main_order="desc",
        special_sort="number",
        special_order="asc",
    )

    assert result.main_frequencies[0].number == 7
    assert result.special_frequencies[0].number == 1


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"game_code": "unknown"}, "有效的彩券種類"),
        ({"range_mode": "unknown"}, "有效的統計範圍"),
        ({"range_mode": "date", "start": "not-a-date"}, "YYYY-MM-DD"),
        (
            {
                "range_mode": "date",
                "start": "2026-02-01",
                "end": "2026-01-01",
            },
            "不可晚於",
        ),
        ({"range_mode": "recent", "draws": "text"}, "正整數"),
        ({"range_mode": "recent", "draws": "-1"}, "正整數"),
        ({"range_mode": "recent", "draws": "0"}, "介於"),
        (
            {"range_mode": "recent", "draws": str(MAX_RECENT_DRAWS + 1)},
            "介於",
        ),
        ({"main_sort": "unknown"}, "排序方式"),
        ({"special_order": "unknown"}, "排序方式"),
    ],
)
def test_stats_service_rejects_invalid_browser_input(arguments, message) -> None:
    with pytest.raises(QueryValidationError, match=message):
        StatsQueryService(FakeStorage()).search(**arguments)


def test_stats_service_represents_empty_database() -> None:
    result = StatsQueryService(FakeStorage(count=0)).search()

    assert result.total_draws == 0
    assert result.latest_draw_date == date(2026, 8, 25)


@pytest.mark.parametrize("game", SUPPORTED_GAMES, ids=lambda game: game.code)
@pytest.mark.parametrize("bounds", ["both", "start", "end", "empty"])
def test_stats_date_boundaries_and_storage_calls(game, bounds) -> None:
    storage = Mock(wraps=FakeStorage(count=3))
    start = game.history_start if bounds in ("both", "start") else None
    end = date(2026, 8, 25) if bounds in ("both", "end") else None

    result = StatsQueryService(storage).search(
        game_code=game.code,
        range_mode="date",
        start=start.isoformat() if start else "",
        end=end.isoformat() if end else "",
        draws="ignored",
    )

    assert (result.start_date, result.end_date) == (start, end)
    assert result.range_mode == ("all" if bounds == "empty" else "date")
    assert result.requested_draws == 100
    assert result.available_draws == result.total_draws == 3
    assert result.range_notice is None
    expected_calls = [
        call.latest_available_draw_date(game.code),
        call.count_draws(game.code),
    ]
    if bounds != "empty":
        expected_calls.append(
            call.count_draws(game.code, start_date=start, end_date=end)
        )
    expected_calls.append(
        call.query_draws(game.code, start_date=start, end_date=end, limit=3, offset=0)
    )
    assert storage.method_calls == expected_calls


@pytest.mark.parametrize(
    ("arguments", "message", "reads_metadata"),
    [
        ({"game_code": "bad", "range_mode": "bad"}, "請選擇有效的彩券種類。", False),
        ({"range_mode": "bad", "main_sort": "bad"}, "請選擇有效的統計範圍。", False),
        (
            {"range_mode": "date", "start": "bad", "special_order": "bad"},
            "請選擇有效的排序方式。",
            False,
        ),
        (
            {"range_mode": "date", "start": "bad", "end": "bad"},
            "開始日期必須是 YYYY-MM-DD 格式。",
            True,
        ),
        (
            {"range_mode": "date", "start": "2006-12-31", "end": "bad"},
            "結束日期必須是 YYYY-MM-DD 格式。",
            True,
        ),
        (
            {"range_mode": "date", "start": "2006-12-31", "end": "2006-12-30"},
            "開始日期不可早於 2007-01-01。",
            True,
        ),
        (
            {"range_mode": "date", "start": "2026-08-26", "end": "2006-12-31"},
            "結束日期不可早於 2007-01-01。",
            True,
        ),
        (
            {"range_mode": "date", "start": "2026-08-27", "end": "2026-08-26"},
            "開始日期不可晚於最新資料 2026-08-25。",
            True,
        ),
        (
            {"range_mode": "date", "end": "2026-08-26"},
            "結束日期不可晚於最新資料 2026-08-25。",
            True,
        ),
        (
            {"range_mode": "date", "start": "2026-08-25", "end": "2026-08-24"},
            "開始日期不可晚於結束日期。",
            True,
        ),
        (
            {"range_mode": "recent", "draws": "10000000"},
            "最近期數不可超過 1,000,000。",
            True,
        ),
    ],
)
def test_stats_validation_priority_and_exact_messages(
    arguments, message, reads_metadata
):
    storage = Mock(wraps=FakeStorage())
    with pytest.raises(QueryValidationError) as error:
        StatsQueryService(storage).search(**arguments)
    assert str(error.value) == message
    assert storage.method_calls == (
        [
            call.latest_available_draw_date(LOTTO_649.code),
            call.count_draws(LOTTO_649.code),
        ]
        if reads_metadata
        else []
    )


@pytest.mark.parametrize("requested", [1, 3, 100, MAX_RECENT_DRAWS])
def test_stats_recent_limit_and_query_count(requested) -> None:
    storage = Mock(wraps=FakeStorage(count=3))
    result = StatsQueryService(storage).search(
        range_mode="recent", draws=str(requested)
    )
    assert result.requested_draws == requested
    assert result.available_draws == 3
    assert result.total_draws == min(requested, 3)
    assert result.range_notice == (
        f"要求最近 {requested} 期，目前只有 3 期，因此顯示全部 3 期。"
        if requested > 3
        else None
    )
    assert storage.method_calls == [
        call.latest_available_draw_date(LOTTO_649.code),
        call.count_draws(LOTTO_649.code),
        call.query_draws(
            LOTTO_649.code,
            start_date=None,
            end_date=None,
            limit=min(requested, 3),
            offset=0,
        ),
    ]


@pytest.mark.parametrize("mode", ["all", "date", "recent"])
def test_stats_zero_results_skip_draw_query(mode) -> None:
    storage = Mock(wraps=FakeStorage(count=0))
    storage.latest_available_draw_date.return_value = None
    result = StatsQueryService(storage).search(
        range_mode=mode, start="2026-01-01", end="2026-01-02"
    )
    assert result.latest_draw_date is None
    assert result.total_draws == result.available_draws == 0
    storage.query_draws.assert_not_called()
    assert storage.count_draws.call_count == (2 if mode == "date" else 1)
    assert result.range_notice == (
        "要求最近 100 期，目前只有 0 期，因此顯示全部 0 期。"
        if mode == "recent"
        else None
    )
    for rows in (result.main_frequencies, result.special_frequencies):
        assert all(
            row.count == row.current_missing_draws == row.longest_missing_draws == 0
            for row in rows
        )
        assert all(
            row.rate == row.expected_difference == 0 and row.last_seen_date is None
            for row in rows
        )


@pytest.mark.parametrize("game", SUPPORTED_GAMES, ids=lambda game: game.code)
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_stats_game_rates_chronology_and_date_sort(game, order) -> None:
    storage = FakeStorage(count=3)
    storage.draws = [
        Draw(
            game.code, f"11500000{day}", date(2026, 1, day), (1, 2, 3, 4, 5, 6), special
        )
        for day, special in [(3, 7), (2, 8), (1, 7)]
    ]
    result = StatsQueryService(storage).search(
        game_code=game.code,
        main_sort="number",
        main_order="desc",
        special_sort="last_seen_date",
        special_order=order,
    )
    assert [row.number for row in result.main_frequencies] == list(
        range(game.main_number_max, 0, -1)
    )
    assert [row.number for row in result.special_frequencies] == (
        ([8, 7] if order == "asc" else [7, 8])
        + [
            number
            for number in range(1, game.special_number_max + 1)
            if number not in (7, 8)
        ]
    )
    assert result.main_theoretical_rate == 6 / game.main_number_max
    assert result.special_theoretical_rate == 1 / game.special_number_max
    assert result.main_expected_count == 3 * result.main_theoretical_rate
    assert result.special_expected_count == 3 * result.special_theoretical_rate
    seven = next(row for row in result.special_frequencies if row.number == 7)
    assert seven == NumberFrequency(
        7, 2, 2 / 3, 2 - result.special_expected_count, date(2026, 1, 3), 0, 1
    )
    eight = next(row for row in result.special_frequencies if row.number == 8)
    assert (
        eight.last_seen_date,
        eight.current_missing_draws,
        eight.longest_missing_draws,
    ) == (date(2026, 1, 2), 1, 1)

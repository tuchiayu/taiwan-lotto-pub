"""Validated application queries for browsing stored lottery draws."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from math import ceil

from taiwan_lotto.models import SUPPORTED_GAMES, Draw, GameSpec
from taiwan_lotto.storage.sqlite import SQLiteStorage

PAGE_SIZE = 20
MAX_PAGE_NUMBER = 1_000_000
DEFAULT_RECENT_DRAWS = 100
MAX_RECENT_DRAWS = 1_000_000
GAMES_BY_CODE = {game.code: game for game in SUPPORTED_GAMES}
RANGE_MODES = {"all", "date", "recent"}
SORT_FIELDS = {
    "number",
    "count",
    "rate",
    "expected_difference",
    "last_seen_date",
    "current_missing_draws",
    "longest_missing_draws",
}
SORT_ORDERS = {"asc", "desc"}


class QueryValidationError(ValueError):
    """Report a user-correctable draw query error."""


@dataclass(frozen=True, slots=True)
class DrawPage:
    """Represent a validated page of stored draw results."""

    game: GameSpec
    items: tuple[Draw, ...]
    total_items: int
    page: int
    page_size: int
    total_pages: int
    latest_draw_date: date | None
    start_date: date | None
    end_date: date | None


class DrawQueryService:
    """Validate browser filters and coordinate read-only storage queries."""

    def __init__(self, storage: SQLiteStorage) -> None:
        self._storage = storage

    def search(
        self,
        *,
        game_code: str = "lotto649",
        start: str = "",
        end: str = "",
        page: str = "1",
    ) -> DrawPage:
        """Parse browser query strings and return a single result page."""
        game = GAMES_BY_CODE.get(game_code)
        if game is None:
            raise QueryValidationError("請選擇有效的彩券種類。")
        start_date = _parse_date(start, "開始日期")
        end_date = _parse_date(end, "結束日期")
        if start_date and end_date and start_date > end_date:
            raise QueryValidationError("開始日期不可晚於結束日期。")
        try:
            page_number = int(page)
        except ValueError as error:
            raise QueryValidationError("頁碼必須是正整數。") from error
        if page_number < 1 or page_number > MAX_PAGE_NUMBER:
            raise QueryValidationError("頁碼必須是正整數。")

        total_items = self._storage.count_draws(
            game.code, start_date=start_date, end_date=end_date
        )
        total_pages = ceil(total_items / PAGE_SIZE) if total_items else 0
        if total_pages and page_number > total_pages:
            raise QueryValidationError(f"頁碼超出範圍，此查詢共 {total_pages} 頁。")

        items = self._storage.query_draws(
            game.code,
            start_date=start_date,
            end_date=end_date,
            limit=PAGE_SIZE,
            offset=(page_number - 1) * PAGE_SIZE,
        )
        return DrawPage(
            game=game,
            items=tuple(items),
            total_items=total_items,
            page=page_number,
            page_size=PAGE_SIZE,
            total_pages=total_pages,
            latest_draw_date=self._storage.latest_available_draw_date(game.code),
            start_date=start_date,
            end_date=end_date,
        )


def _parse_date(value: str, label: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise QueryValidationError(f"{label}必須是 YYYY-MM-DD 格式。") from error


@dataclass(frozen=True, slots=True)
class NumberFrequency:
    """Represent one number's occurrence statistics in the selected draws."""

    number: int
    count: int
    rate: float
    expected_difference: float
    last_seen_date: date | None
    current_missing_draws: int
    longest_missing_draws: int


@dataclass(frozen=True, slots=True)
class FrequencyPage:
    """Represent a validated number-frequency statistics result."""

    game: GameSpec
    main_frequencies: tuple[NumberFrequency, ...]
    special_frequencies: tuple[NumberFrequency, ...]
    total_draws: int
    start_date: date | None
    end_date: date | None
    latest_draw_date: date | None
    range_mode: str
    requested_draws: int
    available_draws: int
    range_notice: str | None
    main_theoretical_rate: float
    main_expected_count: float
    special_theoretical_rate: float
    special_expected_count: float
    main_sort: str
    main_order: str
    special_sort: str
    special_order: str


class StatsQueryService:
    """Validate browser filters and coordinate read-only frequency queries."""

    def __init__(self, storage: SQLiteStorage) -> None:
        self._storage = storage

    def search(
        self,
        *,
        game_code: str = "lotto649",
        start: str = "",
        end: str = "",
        range_mode: str = "all",
        draws: str = str(DEFAULT_RECENT_DRAWS),
        main_sort: str = "count",
        main_order: str = "desc",
        special_sort: str = "count",
        special_order: str = "desc",
    ) -> FrequencyPage:
        """Validate a range and return sortable number statistics."""
        game = GAMES_BY_CODE.get(game_code)
        if game is None:
            raise QueryValidationError("請選擇有效的彩券種類。")
        if range_mode not in RANGE_MODES:
            raise QueryValidationError("請選擇有效的統計範圍。")
        main_sort, main_order = _validate_sort(main_sort, main_order)
        special_sort, special_order = _validate_sort(special_sort, special_order)

        latest_date = self._storage.latest_available_draw_date(game.code)
        available_draws = self._storage.count_draws(game.code)
        start_date = None
        end_date = None
        requested_draws = DEFAULT_RECENT_DRAWS
        range_notice = None

        if range_mode == "date":
            start_date = _parse_date(start, "開始日期")
            end_date = _parse_date(end, "結束日期")
            if start_date and start_date < game.history_start:
                raise QueryValidationError(
                    f"開始日期不可早於 {game.history_start:%Y-%m-%d}。"
                )
            if end_date and end_date < game.history_start:
                raise QueryValidationError(
                    f"結束日期不可早於 {game.history_start:%Y-%m-%d}。"
                )
            if latest_date and start_date and start_date > latest_date:
                raise QueryValidationError(
                    f"開始日期不可晚於最新資料 {latest_date:%Y-%m-%d}。"
                )
            if latest_date and end_date and end_date > latest_date:
                raise QueryValidationError(
                    f"結束日期不可晚於最新資料 {latest_date:%Y-%m-%d}。"
                )
            if start_date and end_date and start_date > end_date:
                raise QueryValidationError("開始日期不可晚於結束日期。")
            if start_date is None and end_date is None:
                range_mode = "all"
        elif range_mode == "recent":
            requested_draws = _parse_recent_draws(draws)

        if range_mode == "date":
            total_draws = self._storage.count_draws(
                game.code, start_date=start_date, end_date=end_date
            )
        elif range_mode == "recent":
            total_draws = min(requested_draws, available_draws)
        else:
            total_draws = available_draws
        if range_mode == "recent" and requested_draws > available_draws:
            range_notice = (
                f"要求最近 {requested_draws} 期，目前只有 {available_draws} 期，"
                f"因此顯示全部 {available_draws} 期。"
            )

        selected_draws = (
            self._storage.query_draws(
                game.code,
                start_date=start_date,
                end_date=end_date,
                limit=total_draws,
                offset=0,
            )
            if total_draws
            else []
        )
        selected_draws.reverse()
        main_rate = 6 / game.main_number_max
        special_rate = 1 / game.special_number_max
        main_frequencies = _number_statistics(
            selected_draws,
            max_number=game.main_number_max,
            expected_count=total_draws * main_rate,
            special=False,
        )
        special_frequencies = _number_statistics(
            selected_draws,
            max_number=game.special_number_max,
            expected_count=total_draws * special_rate,
            special=True,
        )
        return FrequencyPage(
            game=game,
            main_frequencies=_sort_frequencies(main_frequencies, main_sort, main_order),
            special_frequencies=_sort_frequencies(
                special_frequencies, special_sort, special_order
            ),
            total_draws=total_draws,
            start_date=start_date,
            end_date=end_date,
            latest_draw_date=latest_date,
            range_mode=range_mode,
            requested_draws=requested_draws,
            available_draws=available_draws,
            range_notice=range_notice,
            main_theoretical_rate=main_rate,
            main_expected_count=total_draws * main_rate,
            special_theoretical_rate=special_rate,
            special_expected_count=total_draws * special_rate,
            main_sort=main_sort,
            main_order=main_order,
            special_sort=special_sort,
            special_order=special_order,
        )


def _parse_recent_draws(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise QueryValidationError("最近期數必須是正整數。")
    if len(value) > 7:
        raise QueryValidationError(f"最近期數不可超過 {MAX_RECENT_DRAWS:,}。")
    result = int(value)
    if result < 1 or result > MAX_RECENT_DRAWS:
        raise QueryValidationError(f"最近期數必須介於 1 與 {MAX_RECENT_DRAWS:,} 之間。")
    return result


def _validate_sort(field: str, order: str) -> tuple[str, str]:
    if field not in SORT_FIELDS or order not in SORT_ORDERS:
        raise QueryValidationError("請選擇有效的排序方式。")
    return field, order


def _number_statistics(
    draws: list[Draw],
    *,
    max_number: int,
    expected_count: float,
    special: bool,
) -> tuple[NumberFrequency, ...]:
    results = []
    total_draws = len(draws)
    for number in range(1, max_number + 1):
        count = 0
        current_missing = 0
        longest_missing = 0
        last_seen = None
        for draw in draws:
            present = (
                draw.special_number == number
                if special
                else number in draw.main_numbers
            )
            if present:
                count += 1
                current_missing = 0
                last_seen = draw.draw_date
            else:
                current_missing += 1
                longest_missing = max(longest_missing, current_missing)
        results.append(
            NumberFrequency(
                number=number,
                count=count,
                rate=count / total_draws if total_draws else 0.0,
                expected_difference=count - expected_count,
                last_seen_date=last_seen,
                current_missing_draws=current_missing,
                longest_missing_draws=longest_missing,
            )
        )
    return tuple(results)


def _sort_frequencies(
    frequencies: tuple[NumberFrequency, ...], field: str, order: str
) -> tuple[NumberFrequency, ...]:
    if field == "number":
        return tuple(
            sorted(frequencies, key=lambda item: item.number, reverse=order == "desc")
        )

    present = list(frequencies)
    if field == "last_seen_date":
        absent = [item for item in present if item.last_seen_date is None]
        present = [item for item in present if item.last_seen_date is not None]
    else:
        absent = []
    present.sort(key=lambda item: item.number)
    present.sort(key=lambda item: getattr(item, field), reverse=order == "desc")
    return tuple([*present, *sorted(absent, key=lambda item: item.number)])

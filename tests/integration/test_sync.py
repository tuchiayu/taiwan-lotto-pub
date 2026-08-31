from __future__ import annotations

from datetime import date

from taiwan_lotto.models import LOTTO_649, SUPER_LOTTO_638, Draw, GameSpec
from taiwan_lotto.sources.taiwan_lottery import SourceError
from taiwan_lotto.storage.sqlite import SQLiteStorage
from taiwan_lotto.sync import SyncService


class FakeSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date]] = []
        self.fail_game: str | None = None

    def fetch_draws(
        self, game: GameSpec, start_month: date, end_month: date
    ) -> list[Draw]:
        self.calls.append((game.code, start_month, end_month))
        if game.code == self.fail_game:
            raise SourceError("planned source failure")
        roc_year = end_month.year - 1911
        term = f"{roc_year}000001"
        day = 24 if game is SUPER_LOTTO_638 else 2
        numbers = (
            (7, 14, 22, 23, 31, 35)
            if game is SUPER_LOTTO_638
            else (3, 7, 16, 19, 40, 42)
        )
        special = 7 if game is SUPER_LOTTO_638 else 12
        return [
            Draw(
                game_code=game.code,
                draw_term=term,
                draw_date=date(end_month.year, end_month.month, min(day, 28)),
                main_numbers=numbers,
                special_number=special,
            )
        ]


def test_first_run_imports_by_year_then_next_run_uses_incremental_range(
    tmp_path,
) -> None:
    source = FakeSource()
    storage = SQLiteStorage(tmp_path / "lotto.db")
    service = SyncService(source, storage, today_provider=lambda: date(2008, 2, 15))

    first_results = service.run()

    assert all(result.success and result.mode == "history" for result in first_results)
    assert source.calls == [
        (LOTTO_649.code, date(2007, 1, 1), date(2007, 12, 1)),
        (LOTTO_649.code, date(2008, 1, 1), date(2008, 2, 1)),
        (SUPER_LOTTO_638.code, date(2008, 1, 1), date(2008, 2, 1)),
    ]

    source.calls.clear()
    second_results = service.run()

    assert all(
        result.success and result.mode == "incremental" for result in second_results
    )
    assert source.calls == [
        (LOTTO_649.code, date(2007, 12, 1), date(2008, 2, 1)),
        (SUPER_LOTTO_638.code, date(2007, 12, 1), date(2008, 2, 1)),
    ]


def test_one_game_failure_does_not_block_the_other(tmp_path) -> None:
    source = FakeSource()
    source.fail_game = LOTTO_649.code
    service = SyncService(
        source,
        SQLiteStorage(tmp_path / "lotto.db"),
        today_provider=lambda: date(2008, 2, 15),
    )

    results = service.run()

    assert not results[0].success
    assert "planned source failure" in results[0].error
    assert results[1].success


def test_failed_history_is_not_marked_complete(tmp_path) -> None:
    source = FakeSource()
    source.fail_game = LOTTO_649.code
    storage = SQLiteStorage(tmp_path / "lotto.db")
    service = SyncService(source, storage, today_provider=lambda: date(2008, 2, 15))

    service.run()

    assert not storage.is_history_complete(LOTTO_649.code)
    assert storage.is_history_complete(SUPER_LOTTO_638.code)

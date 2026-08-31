"""Historical and incremental lottery synchronization orchestration."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from taiwan_lotto.models import SUPPORTED_GAMES, GameSpec, GameSyncResult, SyncCounts
from taiwan_lotto.sources.taiwan_lottery import SourceError, TaiwanLotterySource
from taiwan_lotto.storage.sqlite import SQLiteStorage, StorageError


class SyncError(RuntimeError):
    """Report an invalid or incomplete synchronization result."""


TAIPEI_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Taipei")


def taipei_today() -> date:
    """Return the business date in the configured lottery timezone."""
    return datetime.now(TAIPEI_TIMEZONE).date()


class SyncService:
    """Coordinate source reads and transactional local persistence."""

    def __init__(
        self,
        source: TaiwanLotterySource,
        storage: SQLiteStorage,
        *,
        today_provider: Callable[[], date] = taipei_today,
    ) -> None:
        self._source = source
        self._storage = storage
        self._today_provider = today_provider

    def run(self) -> list[GameSyncResult]:
        """Initialize storage and synchronize every supported game."""
        self._storage.initialize()
        current_month = _month_start(self._today_provider())
        return [self._sync_game(game, current_month) for game in SUPPORTED_GAMES]

    def _sync_game(self, game: GameSpec, current_month: date) -> GameSyncResult:
        counts = SyncCounts()
        history_complete = self._storage.is_history_complete(game.code)
        latest_date = self._storage.latest_draw_date(game.code)
        mode = "incremental" if history_complete and latest_date else "history"
        start_month = (
            _add_months(_month_start(latest_date), -2)
            if mode == "incremental" and latest_date
            else _month_start(game.history_start)
        )

        try:
            if mode == "history":
                for year in range(start_month.year, current_month.year + 1):
                    batch_start = (
                        start_month if year == start_month.year else date(year, 1, 1)
                    )
                    batch_end = (
                        current_month
                        if year == current_month.year
                        else date(year, 12, 1)
                    )
                    counts.add(self._sync_range(game, batch_start, batch_end))
                self._storage.mark_history_complete(game.code)
            else:
                counts.add(self._sync_range(game, start_month, current_month))
                self._storage.mark_sync_success(game.code)
        except (SourceError, StorageError, SyncError, ValueError) as error:
            return GameSyncResult(
                game=game,
                mode=mode,
                start_month=start_month,
                end_month=current_month,
                counts=counts,
                success=False,
                error=str(error),
            )

        return GameSyncResult(
            game=game,
            mode=mode,
            start_month=start_month,
            end_month=current_month,
            counts=counts,
            success=True,
        )

    def _sync_range(
        self,
        game: GameSpec,
        start_month: date,
        end_month: date,
    ) -> SyncCounts:
        draws = self._source.fetch_draws(game, start_month, end_month)
        if not draws:
            raise SyncError(
                f"{game.name}: no official draws for "
                f"{start_month:%Y-%m}..{end_month:%Y-%m}"
            )

        local_terms = self._storage.draw_terms_between(
            game.code,
            start_month,
            _month_end(end_month),
        )
        official_terms = {draw.draw_term for draw in draws}
        counts = self._storage.save_draws(draws)
        counts.missing = len(local_terms - official_terms)
        return counts


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _month_end(value: date) -> date:
    return value.replace(day=monthrange(value.year, value.month)[1])


def _add_months(value: date, months: int) -> date:
    absolute_month = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(absolute_month, 12)
    return date(year, zero_based_month + 1, 1)

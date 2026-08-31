"""Domain models and validation rules for lottery draw data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class GameSpec:
    """Describe one supported lottery game and its source contract."""

    code: str
    name: str
    endpoint: str
    collection_key: str
    history_start: date
    main_number_max: int
    special_number_max: int
    special_may_repeat_main: bool


LOTTO_649 = GameSpec(
    code="lotto649",
    name="大樂透",
    endpoint="/Lottery/Lotto649Result",
    collection_key="lotto649Res",
    history_start=date(2007, 1, 1),
    main_number_max=49,
    special_number_max=49,
    special_may_repeat_main=False,
)

SUPER_LOTTO_638 = GameSpec(
    code="super_lotto638",
    name="威力彩",
    endpoint="/Lottery/SuperLotto638Result",
    collection_key="superLotto638Res",
    history_start=date(2008, 1, 1),
    main_number_max=38,
    special_number_max=8,
    special_may_repeat_main=True,
)

SUPPORTED_GAMES = (LOTTO_649, SUPER_LOTTO_638)


@dataclass(frozen=True, slots=True)
class Draw:
    """Represent one validated lottery draw in actual draw order."""

    game_code: str
    draw_term: str
    draw_date: date
    main_numbers: tuple[int, int, int, int, int, int]
    special_number: int
    source: str = "taiwan_lottery_api"


def validate_draw(draw: Draw, game: GameSpec) -> None:
    """Raise ValueError when a draw violates the supported game rules."""
    if draw.game_code != game.code:
        raise ValueError(f"game code mismatch: {draw.game_code}")
    if not draw.draw_term.isdigit() or len(draw.draw_term) not in (8, 9):
        raise ValueError(f"invalid draw term: {draw.draw_term}")
    if len(draw.main_numbers) != 6:
        raise ValueError("a draw must contain exactly six main numbers")
    if len(set(draw.main_numbers)) != 6:
        raise ValueError("main numbers must not repeat")
    if any(number < 1 or number > game.main_number_max for number in draw.main_numbers):
        raise ValueError(f"main number outside 1-{game.main_number_max}")
    if not 1 <= draw.special_number <= game.special_number_max:
        raise ValueError(f"special number outside 1-{game.special_number_max}")
    if not game.special_may_repeat_main and draw.special_number in draw.main_numbers:
        raise ValueError("special number must not repeat a main number")


@dataclass(slots=True)
class SyncCounts:
    """Count storage outcomes for one synchronization operation."""

    added: int = 0
    skipped: int = 0
    corrected: int = 0
    missing: int = 0

    def add(self, other: SyncCounts) -> None:
        """Accumulate another set of counts."""
        self.added += other.added
        self.skipped += other.skipped
        self.corrected += other.corrected
        self.missing += other.missing


@dataclass(frozen=True, slots=True)
class GameSyncResult:
    """Describe the result of synchronizing one game."""

    game: GameSpec
    mode: str
    start_month: date
    end_month: date
    counts: SyncCounts
    success: bool
    error: str | None = None

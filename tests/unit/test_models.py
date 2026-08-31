from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from taiwan_lotto.models import LOTTO_649, SUPER_LOTTO_638, Draw, validate_draw


def _draw(**changes) -> Draw:
    draw = Draw(
        game_code=LOTTO_649.code,
        draw_term="96000001",
        draw_date=date(2007, 1, 2),
        main_numbers=(22, 20, 23, 2, 16, 27),
        special_number=46,
    )
    return replace(draw, **changes)


def test_validate_draw_accepts_early_eight_digit_term() -> None:
    validate_draw(_draw(), LOTTO_649)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"draw_term": "123"}, "invalid draw term"),
        ({"main_numbers": (1, 1, 2, 3, 4, 5)}, "must not repeat"),
        ({"main_numbers": (1, 2, 3, 4, 5, 50)}, "outside 1-49"),
        ({"special_number": 22}, "must not repeat"),
    ],
)
def test_validate_draw_rejects_invalid_lotto_draw(changes, message) -> None:
    with pytest.raises(ValueError, match=message):
        validate_draw(_draw(**changes), LOTTO_649)


def test_super_lotto_second_area_may_repeat_first_area() -> None:
    draw = Draw(
        game_code=SUPER_LOTTO_638.code,
        draw_term="115000001",
        draw_date=date(2026, 1, 1),
        main_numbers=(7, 14, 22, 23, 31, 35),
        special_number=7,
    )

    validate_draw(draw, SUPER_LOTTO_638)

from __future__ import annotations

import json
from datetime import date
from urllib.error import HTTPError, URLError

import pytest

from taiwan_lotto.models import LOTTO_649
from taiwan_lotto.sources.taiwan_lottery import SourceError, TaiwanLotterySource


def _row(period: int = 115000001) -> dict:
    return {
        "period": period,
        "lotteryDate": "2026-01-02T00:00:00",
        "drawNumberAppear": [3, 7, 16, 19, 40, 42, 12],
        "drawNumberSize": [3, 7, 16, 19, 40, 42, 12],
    }


def _payload(rows: list[dict], total: int | None = None) -> bytes:
    return json.dumps(
        {
            "rtCode": 0,
            "rtMsg": None,
            "content": {
                "totalSize": len(rows) if total is None else total,
                "lotto649Res": rows,
            },
        }
    ).encode()


def test_fetch_draws_paginates_and_preserves_actual_order() -> None:
    urls: list[str] = []
    timeouts: list[float] = []

    def transport(url: str, timeout: float) -> bytes:
        urls.append(url)
        timeouts.append(timeout)
        return _payload(
            [_row(115000001 if "pageNum=1" in url else 115000002)],
            total=2,
        )

    source = TaiwanLotterySource(transport=transport, sleeper=lambda _: None)
    draws = source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))

    assert [draw.draw_term for draw in draws] == ["115000001", "115000002"]
    assert draws[0].main_numbers == (3, 7, 16, 19, 40, 42)
    assert draws[0].special_number == 12
    assert "month=2026-01" in urls[0]
    assert "endMonth=2026-01" in urls[0]
    assert "pageNum=2" in urls[1]
    assert timeouts == [10.0, 10.0]


def test_fetch_draws_retries_transient_network_error() -> None:
    attempts = 0
    sleeps: list[float] = []

    def transport(url: str, timeout: float) -> bytes:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise URLError("temporary")
        return _payload([_row()])

    source = TaiwanLotterySource(transport=transport, sleeper=sleeps.append)

    assert len(source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))) == 1
    assert attempts == 3
    assert sleeps == [1.0, 2.0]


def test_fetch_draws_rejects_disagreeing_sorted_numbers() -> None:
    row = _row()
    row["drawNumberSize"] = [1, 7, 16, 19, 40, 42, 12]
    source = TaiwanLotterySource(transport=lambda *_: _payload([row]))

    with pytest.raises(SourceError, match="disagree"):
        source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))


def test_fetch_draws_rejects_invalid_envelope() -> None:
    source = TaiwanLotterySource(
        transport=lambda *_: json.dumps({"rtCode": 9, "content": {}}).encode()
    )

    with pytest.raises(SourceError, match="rtCode=9"):
        source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (b"not-json", "invalid JSON"),
        (json.dumps([]).encode(), "not a JSON object"),
        (json.dumps({"rtCode": 0, "content": None}).encode(), "missing API content"),
    ],
)
def test_fetch_draws_rejects_invalid_response_contract(
    response: bytes,
    message: str,
) -> None:
    source = TaiwanLotterySource(transport=lambda *_: response)

    with pytest.raises(SourceError, match=message):
        source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))


def test_fetch_draws_does_not_retry_non_transient_http_error() -> None:
    attempts = 0

    def transport(url: str, timeout: float) -> bytes:
        nonlocal attempts
        attempts += 1
        raise HTTPError(url, 404, "not found", None, None)

    source = TaiwanLotterySource(transport=transport, sleeper=lambda _: None)

    with pytest.raises(SourceError, match="HTTP 404"):
        source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))

    assert attempts == 1


def test_fetch_draws_reports_exhausted_network_retries() -> None:
    sleeps: list[float] = []
    source = TaiwanLotterySource(
        max_attempts=2,
        transport=lambda *_: (_ for _ in ()).throw(URLError("temporary")),
        sleeper=sleeps.append,
    )

    with pytest.raises(SourceError, match="request failed"):
        source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))

    assert sleeps == [1.0]


@pytest.mark.parametrize("max_attempts", [0, -1])
def test_source_rejects_invalid_max_attempts(max_attempts: int) -> None:
    with pytest.raises(ValueError, match="max_attempts must be at least 1"):
        TaiwanLotterySource(max_attempts=max_attempts)


def test_fetch_draws_rejects_changed_pagination_total() -> None:
    def transport(url: str, timeout: float) -> bytes:
        if "pageNum=1" in url:
            return _payload([_row(115000001)], total=2)
        return _payload([_row(115000002)], total=3)

    source = TaiwanLotterySource(transport=transport)

    with pytest.raises(SourceError, match="totalSize changed"):
        source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))


def test_fetch_draws_rejects_duplicate_term_across_pages() -> None:
    source = TaiwanLotterySource(
        transport=lambda *_: _payload([_row()], total=2),
    )

    with pytest.raises(SourceError, match="duplicate term"):
        source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))


def test_fetch_draws_rejects_incomplete_pagination() -> None:
    calls = 0

    def transport(url: str, timeout: float) -> bytes:
        nonlocal calls
        calls += 1
        return _payload([_row()] if calls == 1 else [], total=2)

    source = TaiwanLotterySource(transport=transport)

    with pytest.raises(SourceError, match="expected 2 rows, received 1"):
        source.fetch_draws(LOTTO_649, date(2026, 1, 1), date(2026, 1, 1))

"""Client for the data endpoints used by the Taiwan Lottery website."""

from __future__ import annotations

import json
import socket
import ssl
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime
from http.client import HTTPResponse
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from taiwan_lotto.models import Draw, GameSpec, validate_draw

BASE_URL = "https://api.taiwanlottery.com/TLCAPIWeB"
PAGE_SIZE = 200


class SourceError(RuntimeError):
    """Report a network or source-contract failure."""


Transport = Callable[[str, float], bytes]


def _default_transport(url: str, timeout: float) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": "taiwan-lotto/0.1 (+https://github.com/tuchiayu)"},
    )
    response: HTTPResponse
    context = ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    with urlopen(request, timeout=timeout, context=context) as response:  # noqa: S310
        return response.read()


class TaiwanLotterySource:
    """Fetch and validate paginated official draw results."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout: float = 10.0,
        max_attempts: int = 3,
        transport: Transport = _default_transport,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._transport = transport
        self._sleeper = sleeper

    def fetch_draws(
        self,
        game: GameSpec,
        start_month: date,
        end_month: date,
    ) -> list[Draw]:
        """Fetch all pages for an inclusive month range."""
        if start_month > end_month:
            raise ValueError("start month must not be after end month")

        page_number = 1
        total_size: int | None = None
        draws: list[Draw] = []
        seen_terms: set[str] = set()

        while total_size is None or len(draws) < total_size:
            payload = self._request_page(game, start_month, end_month, page_number)
            page_total = payload.get("totalSize")
            rows = payload.get(game.collection_key)
            if not isinstance(page_total, int) or isinstance(page_total, bool):
                raise SourceError(f"{game.name}: invalid totalSize")
            if rows is None:
                rows = []
            if not isinstance(rows, list):
                raise SourceError(f"{game.name}: invalid result collection")
            if total_size is None:
                total_size = page_total
            elif total_size != page_total:
                raise SourceError(f"{game.name}: totalSize changed during pagination")

            for row in rows:
                draw = self._parse_draw(game, row)
                if draw.draw_term in seen_terms:
                    raise SourceError(f"{game.name}: duplicate term {draw.draw_term}")
                seen_terms.add(draw.draw_term)
                draws.append(draw)

            if not rows:
                break
            page_number += 1

        if total_size is None or len(draws) != total_size:
            raise SourceError(
                f"{game.name}: expected {total_size or 0} rows, received {len(draws)}"
            )
        return draws

    def _request_page(
        self,
        game: GameSpec,
        start_month: date,
        end_month: date,
        page_number: int,
    ) -> Mapping[str, Any]:
        query = urlencode(
            {
                "month": start_month.strftime("%Y-%m"),
                "endMonth": end_month.strftime("%Y-%m"),
                "pageNum": page_number,
                "pageSize": PAGE_SIZE,
            }
        )
        url = f"{self._base_url}{game.endpoint}?{query}"
        envelope = self._request_json(url)
        if envelope.get("rtCode") != 0:
            raise SourceError(
                f"{game.name}: API returned rtCode={envelope.get('rtCode')}"
            )
        content = envelope.get("content")
        if not isinstance(content, Mapping):
            raise SourceError(f"{game.name}: missing API content")
        return content

    def _request_json(self, url: str) -> Mapping[str, Any]:
        for attempt in range(1, self._max_attempts + 1):
            try:
                raw = self._transport(url, self._timeout)
                payload = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(payload, Mapping):
                    raise SourceError("API response is not a JSON object")
                return payload
            except HTTPError as error:
                retryable = error.code == 429 or 500 <= error.code < 600
                if not retryable or attempt == self._max_attempts:
                    raise SourceError(
                        f"HTTP {error.code} from Taiwan Lottery"
                    ) from error
            except (URLError, TimeoutError, socket.timeout) as error:
                if attempt == self._max_attempts:
                    raise SourceError("Taiwan Lottery request failed") from error
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise SourceError("Taiwan Lottery returned invalid JSON") from error

            self._sleeper(float(2 ** (attempt - 1)))

        raise AssertionError("retry loop exited unexpectedly")

    @staticmethod
    def _parse_draw(game: GameSpec, row: object) -> Draw:
        if not isinstance(row, Mapping):
            raise SourceError(f"{game.name}: draw row is not an object")
        try:
            period_value = row["period"]
            lottery_date = row["lotteryDate"]
            actual_values = row["drawNumberAppear"]
            sorted_values = row["drawNumberSize"]
        except KeyError as error:
            raise SourceError(f"{game.name}: missing field {error.args[0]}") from error

        draw_term = str(period_value)
        if not isinstance(lottery_date, str):
            raise SourceError(f"{game.name}: invalid lotteryDate")
        if not _is_int_list(actual_values, length=7):
            raise SourceError(f"{game.name}: invalid drawNumberAppear")
        if not _is_int_list(sorted_values, length=7):
            raise SourceError(f"{game.name}: invalid drawNumberSize")

        try:
            parsed_date = datetime.fromisoformat(
                lottery_date.replace("Z", "+00:00")
            ).date()
        except ValueError as error:
            raise SourceError(f"{game.name}: invalid lotteryDate") from error

        actual_main = tuple(actual_values[:6])
        special_number = actual_values[6]
        if (
            sorted(actual_main) != sorted_values[:6]
            or special_number != sorted_values[6]
        ):
            raise SourceError(f"{game.name}: ordered and sorted numbers disagree")

        draw = Draw(
            game_code=game.code,
            draw_term=draw_term,
            draw_date=parsed_date,
            main_numbers=actual_main,
            special_number=special_number,
        )
        try:
            validate_draw(draw, game)
        except ValueError as error:
            raise SourceError(f"{game.name} {draw_term}: {error}") from error
        return draw


def _is_int_list(value: object, *, length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == length
        and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    )

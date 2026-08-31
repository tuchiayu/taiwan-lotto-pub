"""FastAPI application for the local draw browser."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from taiwan_lotto.models import SUPPORTED_GAMES
from taiwan_lotto.query import (
    DrawPage,
    DrawQueryService,
    FrequencyPage,
    QueryValidationError,
    StatsQueryService,
)
from taiwan_lotto.storage.sqlite import (
    DatabaseNotFoundError,
    SQLiteStorage,
    StorageError,
)

LOGGER = logging.getLogger(__name__)
WEB_ROOT = Path(__file__).parent
STATIC_VERSION = str(
    max(path.stat().st_mtime_ns for path in (WEB_ROOT / "static").iterdir())
)


def create_app(
    database_path: Path,
    *,
    on_started: Callable[[], None] | None = None,
) -> FastAPI:
    """Create a local-only HTML application for one database path."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if on_started is not None:
            on_started()
        yield

    app = FastAPI(
        title="Taiwan Lotto Lab",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    templates = _templates()
    query_service = DrawQueryService(SQLiteStorage(database_path))
    stats_service = StatsQueryService(SQLiteStorage(database_path))
    app.mount(
        "/static",
        StaticFiles(directory=WEB_ROOT / "static"),
        name="static",
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/", response_class=HTMLResponse)
    def draw_browser(request: Request) -> HTMLResponse:
        game_code = request.query_params.get("game", "lotto649")
        start = request.query_params.get("start", "")
        end = request.query_params.get("end", "")
        page_value = request.query_params.get("page", "1")
        context = _base_context(request, game_code, start, end)
        status_code = 200
        try:
            result = query_service.search(
                game_code=game_code,
                start=start,
                end=end,
                page=page_value,
            )
            context.update(_result_context(result))
        except QueryValidationError as error:
            context.update(state="invalid", message=str(error))
        except DatabaseNotFoundError:
            context.update(state="missing", message=None)
        except StorageError:
            LOGGER.exception("Unable to read the local lottery database")
            context.update(state="error", message=None)
            status_code = 503
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=context,
            status_code=status_code,
        )

    @app.get("/stats", response_class=HTMLResponse)
    def number_stats(request: Request) -> HTMLResponse:
        game_code = request.query_params.get("game", "lotto649")
        start = request.query_params.get("start", "")
        end = request.query_params.get("end", "")
        range_mode = request.query_params.get("range", "all")
        draws = request.query_params.get("draws", "100")
        main_sort = request.query_params.get("main_sort", "count")
        main_order = request.query_params.get("main_order", "desc")
        special_sort = request.query_params.get("special_sort", "count")
        special_order = request.query_params.get("special_order", "desc")
        active_stats_tab = request.query_params.get("table", "main")
        if active_stats_tab not in {"main", "special"}:
            active_stats_tab = "main"
        context = _stats_base_context(
            request,
            game_code,
            start,
            end,
            range_mode,
            draws,
            main_sort,
            main_order,
            special_sort,
            special_order,
            active_stats_tab,
        )
        status_code = 200
        try:
            result = stats_service.search(
                game_code=game_code,
                start=start,
                end=end,
                range_mode=range_mode,
                draws=draws,
                main_sort=main_sort,
                main_order=main_order,
                special_sort=special_sort,
                special_order=special_order,
            )
            context.update(_stats_result_context(result))
        except QueryValidationError as error:
            context.update(state="invalid", message=str(error))
        except DatabaseNotFoundError:
            context.update(state="missing", message=None)
        except StorageError:
            LOGGER.exception("Unable to read the local lottery database")
            context.update(state="error", message=None)
            status_code = 503
        return templates.TemplateResponse(
            request=request,
            name="stats.html",
            context=context,
            status_code=status_code,
        )

    return app


def _templates() -> Jinja2Templates:
    environment = Environment(
        loader=FileSystemLoader(WEB_ROOT / "templates"),
        autoescape=select_autoescape(
            enabled_extensions=("html", "htm", "xml"),
            default_for_string=True,
            default=True,
        ),
        undefined=StrictUndefined,
    )
    return Jinja2Templates(env=environment)


def _base_context(
    request: Request,
    game_code: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    navigation = _navigation_urls(game_code, start=start, end=end)
    return {
        "request": request,
        "static_version": STATIC_VERSION,
        "games": SUPPORTED_GAMES,
        "selected_game": game_code,
        "start_value": start,
        "end_value": end,
        "state": "initial",
        "message": None,
        "result": None,
        "previous_url": None,
        "next_url": None,
        "first_url": None,
        "last_url": None,
        "selected_history_start": _history_start(game_code),
        **navigation,
        "active_page": "draws",
    }


def _stats_base_context(
    request: Request,
    game_code: str,
    start: str,
    end: str,
    range_mode: str,
    draws: str,
    main_sort: str,
    main_order: str,
    special_sort: str,
    special_order: str,
    active_stats_tab: str,
) -> dict[str, Any]:
    navigation = _navigation_urls(
        game_code,
        start=start if range_mode == "date" else "",
        end=end if range_mode == "date" else "",
    )
    return {
        "request": request,
        "static_version": STATIC_VERSION,
        "games": SUPPORTED_GAMES,
        "selected_game": game_code,
        "start_value": start,
        "end_value": end,
        "range_mode": range_mode,
        "draws_value": draws,
        "main_sort": main_sort,
        "main_order": main_order,
        "special_sort": special_sort,
        "special_order": special_order,
        "active_stats_tab": active_stats_tab,
        "selected_history_start": _history_start(game_code),
        **navigation,
        "state": "initial",
        "message": None,
        "result": None,
        "active_page": "stats",
    }


def _stats_result_context(result: FrequencyPage) -> dict[str, Any]:
    if result.latest_draw_date is None:
        state = "empty_database"
    elif result.total_draws == 0:
        state = "no_results"
    else:
        state = "results"
    return {
        "state": state,
        "result": result,
        "range_mode": result.range_mode,
        "draws_value": str(result.requested_draws),
        "main_sort": result.main_sort,
        "main_order": result.main_order,
        "special_sort": result.special_sort,
        "special_order": result.special_order,
        "main_sort_urls": _stats_sort_urls(result, "main"),
        "special_sort_urls": _stats_sort_urls(result, "special"),
        "stats_tab_urls": _stats_tab_urls(result),
        "applied_range_label": _applied_range_label(result),
        "main_sort_label": _sort_label(result.main_sort, result.main_order),
        "special_sort_label": _sort_label(result.special_sort, result.special_order),
    }


def _stats_parameters(result: FrequencyPage) -> dict[str, str]:
    parameters = {
        "game": result.game.code,
        "range": result.range_mode,
        "main_sort": result.main_sort,
        "main_order": result.main_order,
        "special_sort": result.special_sort,
        "special_order": result.special_order,
    }
    if result.range_mode == "date":
        parameters["start"] = result.start_date.isoformat() if result.start_date else ""
        parameters["end"] = result.end_date.isoformat() if result.end_date else ""
    elif result.range_mode == "recent":
        parameters["draws"] = str(result.requested_draws)
    return parameters


def _stats_tab_urls(result: FrequencyPage) -> dict[str, str]:
    parameters = _stats_parameters(result)
    return {
        table: f"/stats?{urlencode({**parameters, 'table': table})}"
        for table in ("main", "special")
    }


def _stats_sort_urls(result: FrequencyPage, table: str) -> dict[str, str]:
    fields = (
        "number",
        "count",
        "rate",
        "expected_difference",
        "last_seen_date",
        "current_missing_draws",
        "longest_missing_draws",
    )
    parameters = {**_stats_parameters(result), "table": table}

    current_field = result.main_sort if table == "main" else result.special_sort
    current_order = result.main_order if table == "main" else result.special_order
    urls = {}
    for field in fields:
        default_order = "asc" if field == "number" else "desc"
        next_order = (
            ("desc" if current_order == "asc" else "asc")
            if field == current_field
            else default_order
        )
        updated = {
            **parameters,
            f"{table}_sort": field,
            f"{table}_order": next_order,
        }
        urls[field] = f"/stats?{urlencode(updated)}"
    return urls


def _result_context(result: DrawPage) -> dict[str, Any]:
    if result.latest_draw_date is None:
        state = "empty_database"
    elif result.total_items == 0:
        state = "no_results"
    else:
        state = "results"
    filters = {
        "game": result.game.code,
        "start": result.start_date.isoformat() if result.start_date else "",
        "end": result.end_date.isoformat() if result.end_date else "",
    }
    previous_url = None
    next_url = None
    first_url = None
    last_url = None
    if result.page > 1:
        previous_url = _draw_page_url(filters, result.page - 1)
        first_url = _draw_page_url(filters, 1)
    if result.page < result.total_pages:
        next_url = _draw_page_url(filters, result.page + 1)
        last_url = _draw_page_url(filters, result.total_pages)
    return {
        "state": state,
        "result": result,
        "previous_url": previous_url,
        "next_url": next_url,
        "first_url": first_url,
        "last_url": last_url,
    }


def _draw_page_url(filters: dict[str, str], page: int) -> str:
    return f"/?{urlencode({**filters, 'page': page})}#results"


def _history_start(game_code: str) -> str:
    game = next((game for game in SUPPORTED_GAMES if game.code == game_code), None)
    return game.history_start.isoformat() if game else ""


def _navigation_urls(
    game_code: str,
    *,
    start: str = "",
    end: str = "",
) -> dict[str, str]:
    parameters = {"game": game_code}
    if start and end:
        parameters.update(start=start, end=end)
    draws_url = f"/?{urlencode(parameters)}"
    stats_parameters = {"game": game_code}
    if start and end:
        stats_parameters.update(range="date", start=start, end=end)
    stats_url = f"/stats?{urlencode(stats_parameters)}"
    return {"draws_url": draws_url, "stats_url": stats_url}


def _applied_range_label(result: FrequencyPage) -> str:
    if result.range_mode == "recent":
        return f"最近 {result.requested_draws} 期"
    if result.range_mode == "date":
        start = result.start_date.isoformat() if result.start_date else "最早資料"
        end = result.end_date.isoformat() if result.end_date else "最新資料"
        return f"{start} 至 {end}"
    return "全部資料"


def _sort_label(field: str, order: str) -> str:
    labels = {
        "number": "號碼",
        "count": "開出次數",
        "rate": "開出率",
        "expected_difference": "與理論差異",
        "last_seen_date": "最近開出",
        "current_missing_draws": "連續未開",
        "longest_missing_draws": "最長未開",
    }
    direction = "由小到大" if order == "asc" else "由大到小"
    return f"{labels[field]}，{direction}"

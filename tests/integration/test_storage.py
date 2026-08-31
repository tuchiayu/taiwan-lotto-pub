from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import date

import pytest

from taiwan_lotto.main import run_sync
from taiwan_lotto.models import LOTTO_649, SUPER_LOTTO_638, Draw
from taiwan_lotto.storage.sqlite import (
    DatabaseNotFoundError,
    SQLiteStorage,
    StorageError,
)


def _draw(**changes) -> Draw:
    draw = Draw(
        game_code=LOTTO_649.code,
        draw_term="96000001",
        draw_date=date(2007, 1, 2),
        main_numbers=(22, 20, 23, 2, 16, 27),
        special_number=46,
    )
    return replace(draw, **changes)


def test_initial_migration_creates_four_tables_and_is_reversible(tmp_path) -> None:
    database = tmp_path / "nested" / "lotto.db"
    storage = SQLiteStorage(database)

    storage.initialize()
    assert _tables(database) == {"draw_numbers", "draws", "games", "sync_state"}
    assert _user_version(database) == 1

    storage.rollback_initial_for_test()
    assert _tables(database) == set()
    assert _user_version(database) == 0

    storage.initialize()
    assert _tables(database) == {"draw_numbers", "draws", "games", "sync_state"}


def test_save_draws_inserts_skips_and_corrects_atomically(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()

    assert storage.save_draws([_draw()]).added == 1
    assert storage.save_draws([_draw()]).skipped == 1

    corrected = _draw(main_numbers=(1, 2, 3, 4, 5, 6), special_number=7)
    assert storage.save_draws([corrected]).corrected == 1
    assert storage.latest_draw_date(LOTTO_649.code) == date(2007, 1, 2)

    with closing(sqlite3.connect(database)) as connection:
        numbers = connection.execute(
            """
            SELECT number FROM draw_numbers
            WHERE game_code = ? AND draw_term = ? ORDER BY position
            """,
            (LOTTO_649.code, corrected.draw_term),
        ).fetchall()
    assert numbers == [(1,), (2,), (3,), (4,), (5,), (6,)]


def test_save_draws_rolls_back_whole_batch_on_constraint_error(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()
    invalid = _draw(
        draw_term="96000002",
        main_numbers=(1, 1, 2, 3, 4, 5),
        special_number=6,
    )

    with pytest.raises(StorageError, match="SQLite write failed"):
        storage.save_draws([_draw(), invalid])

    assert storage.latest_draw_date(LOTTO_649.code) is None


def test_migration_triggers_enforce_game_number_ranges(tmp_path) -> None:
    database = tmp_path / "lotto.db"
    storage = SQLiteStorage(database)
    storage.initialize()

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(
            sqlite3.IntegrityError, match="special number outside game range"
        ):
            connection.execute(
                """
                INSERT INTO draws (
                    game_code, draw_term, draw_date, special_number, source,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    LOTTO_649.code,
                    "96000001",
                    "2007-01-02",
                    50,
                    "test",
                    "2007-01-02T00:00:00+00:00",
                    "2007-01-02T00:00:00+00:00",
                ),
            )

        connection.execute(
            """
            INSERT INTO draws (
                game_code, draw_term, draw_date, special_number, source,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                LOTTO_649.code,
                "96000001",
                "2007-01-02",
                46,
                "test",
                "2007-01-02T00:00:00+00:00",
                "2007-01-02T00:00:00+00:00",
            ),
        )
        with pytest.raises(
            sqlite3.IntegrityError, match="main number outside game range"
        ):
            connection.execute(
                """
                INSERT INTO draw_numbers (game_code, draw_term, position, number)
                VALUES (?, ?, ?, ?)
                """,
                (LOTTO_649.code, "96000001", 1, 50),
            )


def test_sync_state_and_date_range_queries(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "lotto.db")
    storage.initialize()
    storage.save_draws([_draw()])

    assert not storage.is_history_complete(LOTTO_649.code)
    storage.mark_history_complete(LOTTO_649.code)
    assert storage.is_history_complete(LOTTO_649.code)
    assert storage.draw_terms_between(
        LOTTO_649.code, date(2007, 1, 1), date(2007, 1, 31)
    ) == {"96000001"}


@pytest.mark.parametrize(
    "operation",
    [
        lambda storage: storage.is_history_complete(LOTTO_649.code),
        lambda storage: storage.latest_draw_date(LOTTO_649.code),
        lambda storage: storage.draw_terms_between(
            LOTTO_649.code, date(2007, 1, 1), date(2007, 1, 31)
        ),
    ],
)
def test_sync_reads_normalize_broken_schema_errors(tmp_path, operation) -> None:
    database = tmp_path / "broken.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA user_version = 1")

    with pytest.raises(StorageError, match="SQLite read failed: no such table"):
        operation(SQLiteStorage(database))


def test_sync_command_reports_broken_schema_without_traceback(tmp_path, capsys) -> None:
    database = tmp_path / "broken.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA user_version = 1")

    assert run_sync(database) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Synchronization failed: SQLite read failed" in captured.err
    assert "Traceback" not in captured.err


def test_read_only_draw_query_filters_orders_and_pages(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "lotto.db")
    storage.initialize()
    draws = [
        _draw(draw_term=f"960000{term:02d}", draw_date=date(2007, 1, term))
        for term in range(1, 23)
    ]
    storage.save_draws(draws)

    assert (
        storage.count_draws(LOTTO_649.code, date(2007, 1, 2), date(2007, 1, 21)) == 20
    )
    page = storage.query_draws(
        LOTTO_649.code,
        date(2007, 1, 1),
        date(2007, 1, 22),
        limit=2,
        offset=1,
    )

    assert [draw.draw_term for draw in page] == ["96000021", "96000020"]
    assert page[0].main_numbers == (22, 20, 23, 2, 16, 27)
    assert storage.latest_available_draw_date(LOTTO_649.code) == date(2007, 1, 22)
    assert storage.latest_available_draw_date(SUPER_LOTTO_638.code) is None


def test_read_only_query_supports_second_game(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "lotto.db")
    storage.initialize()
    storage.save_draws(
        [
            Draw(
                game_code=SUPER_LOTTO_638.code,
                draw_term="97000001",
                draw_date=date(2008, 1, 24),
                main_numbers=(7, 14, 22, 23, 31, 35),
                special_number=7,
            )
        ]
    )

    page = storage.query_draws(SUPER_LOTTO_638.code, limit=20, offset=0)

    assert len(page) == 1
    assert page[0].special_number == 7


def test_number_frequencies_count_occurrences_and_respect_date_range(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "lotto.db")
    storage.initialize()
    storage.save_draws(
        [
            _draw(draw_term="96000001", draw_date=date(2007, 1, 2)),
            _draw(
                draw_term="96000002",
                draw_date=date(2007, 1, 9),
                main_numbers=(1, 2, 3, 4, 5, 6),
                special_number=7,
            ),
            _draw(
                draw_term="96000003",
                draw_date=date(2007, 2, 1),
                main_numbers=(1, 2, 3, 4, 5, 6),
                special_number=7,
            ),
        ]
    )

    main_frequencies = storage.main_number_frequencies(
        LOTTO_649.code, date(2007, 1, 1), date(2007, 1, 31)
    )
    assert main_frequencies == {
        22: 1,
        20: 1,
        23: 1,
        2: 2,
        16: 1,
        27: 1,
        1: 1,
        3: 1,
        4: 1,
        5: 1,
        6: 1,
    }
    special_frequencies = storage.special_number_frequencies(
        LOTTO_649.code, date(2007, 1, 1), date(2007, 1, 31)
    )
    assert special_frequencies == {46: 1, 7: 1}

    assert storage.special_number_frequencies(LOTTO_649.code) == {46: 1, 7: 2}


def test_read_only_query_does_not_create_missing_database(tmp_path) -> None:
    database = tmp_path / "missing.db"
    storage = SQLiteStorage(database)

    with pytest.raises(DatabaseNotFoundError, match="does not exist"):
        storage.count_draws(LOTTO_649.code)

    assert not database.exists()


def test_read_only_connection_rejects_writes(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "lotto.db")
    storage.initialize()

    with closing(storage._connect_read_only()) as connection:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM games")


def _tables(database) -> set[str]:
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def _user_version(database) -> int:
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]

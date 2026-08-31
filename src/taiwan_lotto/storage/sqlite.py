"""SQLite persistence for validated lottery draws and sync state."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from taiwan_lotto.models import Draw, SyncCounts

SCHEMA_VERSION = 1


class StorageError(RuntimeError):
    """Report an unsupported schema or SQLite write failure."""


class DatabaseNotFoundError(StorageError):
    """Report that a read-only query database does not exist."""


class SQLiteStorage:
    """Store lottery draws in a local, versioned SQLite database."""

    def __init__(self, path: Path, *, busy_timeout_ms: int = 1000) -> None:
        self.path = path
        self._busy_timeout_ms = busy_timeout_ms

    def initialize(self) -> None:
        """Create the parent directory and apply the initial migration."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise StorageError(
                        "database schema "
                        f"{version} is newer than supported {SCHEMA_VERSION}"
                    )
                if version == 0:
                    connection.executescript(_migration_text("001_initial.sql"))
        except OSError as error:
            raise StorageError(
                f"unable to create database directory: {error}"
            ) from error
        except sqlite3.Error as error:
            raise StorageError(f"SQLite migration failed: {error}") from error

    def rollback_initial_for_test(self) -> None:
        """Apply the reversible initial down migration for verification."""
        with closing(self._connect()) as connection:
            connection.executescript(_migration_text("001_initial_down.sql"))

    def is_history_complete(self, game_code: str) -> bool:
        """Return whether a game completed its full historical import."""
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT history_complete FROM sync_state WHERE game_code = ?",
                    (game_code,),
                ).fetchone()
        except sqlite3.Error as error:
            raise StorageError(f"SQLite read failed: {error}") from error
        return bool(row and row[0])

    def latest_draw_date(self, game_code: str) -> date | None:
        """Return the latest stored draw date for a game."""
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT MAX(draw_date) FROM draws WHERE game_code = ?",
                    (game_code,),
                ).fetchone()
        except sqlite3.Error as error:
            raise StorageError(f"SQLite read failed: {error}") from error
        return date.fromisoformat(row[0]) if row and row[0] else None

    def count_draws(
        self,
        game_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Count stored draws matching an inclusive read-only query."""
        where, parameters = _draw_filters(game_code, start_date, end_date)
        try:
            with closing(self._connect_read_only()) as connection:
                row = connection.execute(
                    f"SELECT COUNT(*) FROM draws WHERE {where}",  # noqa: S608
                    parameters,
                ).fetchone()
        except sqlite3.Error as error:
            raise StorageError(f"SQLite read failed: {error}") from error
        return int(row[0]) if row else 0

    def query_draws(
        self,
        game_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        limit: int,
        offset: int,
    ) -> list[Draw]:
        """Return one page of draws in newest-first order without writing."""
        if limit < 1 or offset < 0:
            raise ValueError("limit must be positive and offset cannot be negative")
        where, parameters = _draw_filters(game_code, start_date, end_date)
        try:
            with closing(self._connect_read_only()) as connection:
                rows = connection.execute(
                    f"""
                    WITH selected_draws AS (
                        SELECT game_code, draw_term, draw_date,
                               special_number, source
                        FROM draws
                        WHERE {where}
                        ORDER BY draw_date DESC, draw_term DESC
                        LIMIT ? OFFSET ?
                    )
                    SELECT selected_draws.game_code,
                           selected_draws.draw_term,
                           selected_draws.draw_date,
                           selected_draws.special_number,
                           selected_draws.source,
                           draw_numbers.position,
                           draw_numbers.number
                    FROM selected_draws
                    JOIN draw_numbers USING (game_code, draw_term)
                    ORDER BY selected_draws.draw_date DESC,
                             selected_draws.draw_term DESC,
                             draw_numbers.position
                    """,  # noqa: S608
                    (*parameters, limit, offset),
                ).fetchall()
        except sqlite3.Error as error:
            raise StorageError(f"SQLite read failed: {error}") from error
        return _rows_to_draws(rows)

    def main_number_frequencies(
        self,
        game_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[int, int]:
        """Count how many times each main number appeared, using a read-only query."""
        where, parameters = _draw_filters(game_code, start_date, end_date)
        try:
            with closing(self._connect_read_only()) as connection:
                rows = connection.execute(
                    f"""
                    WITH filtered_draws AS (
                        SELECT game_code, draw_term
                        FROM draws
                        WHERE {where}
                    )
                    SELECT draw_numbers.number, COUNT(*)
                    FROM filtered_draws
                    JOIN draw_numbers USING (game_code, draw_term)
                    GROUP BY draw_numbers.number
                    """,  # noqa: S608
                    parameters,
                ).fetchall()
        except sqlite3.Error as error:
            raise StorageError(f"SQLite read failed: {error}") from error
        return dict(rows)

    def special_number_frequencies(
        self,
        game_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[int, int]:
        """Count how many times each special number appeared, in a read-only query."""
        where, parameters = _draw_filters(game_code, start_date, end_date)
        try:
            with closing(self._connect_read_only()) as connection:
                rows = connection.execute(
                    f"""
                    SELECT special_number, COUNT(*)
                    FROM draws
                    WHERE {where}
                    GROUP BY special_number
                    """,  # noqa: S608
                    parameters,
                ).fetchall()
        except sqlite3.Error as error:
            raise StorageError(f"SQLite read failed: {error}") from error
        return dict(rows)

    def latest_available_draw_date(self, game_code: str) -> date | None:
        """Return the latest date for one game using a read-only connection."""
        try:
            with closing(self._connect_read_only()) as connection:
                row = connection.execute(
                    "SELECT MAX(draw_date) FROM draws WHERE game_code = ?",
                    (game_code,),
                ).fetchone()
        except sqlite3.Error as error:
            raise StorageError(f"SQLite read failed: {error}") from error
        return date.fromisoformat(row[0]) if row and row[0] else None

    def draw_terms_between(
        self,
        game_code: str,
        start_date: date,
        end_date: date,
    ) -> set[str]:
        """Return locally stored terms inside an inclusive date range."""
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT draw_term
                    FROM draws
                    WHERE game_code = ? AND draw_date BETWEEN ? AND ?
                    """,
                    (game_code, start_date.isoformat(), end_date.isoformat()),
                ).fetchall()
        except sqlite3.Error as error:
            raise StorageError(f"SQLite read failed: {error}") from error
        return {row[0] for row in rows}

    def save_draws(self, draws: list[Draw]) -> SyncCounts:
        """Insert, skip, or correct draws atomically."""
        counts = SyncCounts()
        timestamp = datetime.now(UTC).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for draw in draws:
                existing = self._read_draw(connection, draw.game_code, draw.draw_term)
                if existing is None:
                    self._insert_draw(connection, draw, timestamp)
                    counts.added += 1
                elif _same_draw(existing, draw):
                    counts.skipped += 1
                else:
                    self._update_draw(connection, draw, timestamp)
                    counts.corrected += 1
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise StorageError(f"SQLite write failed: {error}") from error
        finally:
            connection.close()
        return counts

    def mark_history_complete(self, game_code: str) -> None:
        """Mark a game's historical import and latest sync as successful."""
        timestamp = datetime.now(UTC).isoformat()
        self._update_sync_state(game_code, True, timestamp)

    def mark_sync_success(self, game_code: str) -> None:
        """Record the latest successful incremental synchronization."""
        timestamp = datetime.now(UTC).isoformat()
        self._update_sync_state(game_code, None, timestamp)

    def _update_sync_state(
        self,
        game_code: str,
        history_complete: bool | None,
        timestamp: str,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if history_complete:
                connection.execute(
                    """
                    INSERT INTO sync_state (
                        game_code,
                        history_complete,
                        history_completed_at,
                        last_success_at
                    ) VALUES (?, 1, ?, ?)
                    ON CONFLICT(game_code) DO UPDATE SET
                        history_complete = 1,
                        history_completed_at = excluded.history_completed_at,
                        last_success_at = excluded.last_success_at
                    """,
                    (game_code, timestamp, timestamp),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO sync_state (
                        game_code, history_complete, last_success_at
                    )
                    VALUES (?, 0, ?)
                    ON CONFLICT(game_code) DO UPDATE SET
                        last_success_at = excluded.last_success_at
                    """,
                    (game_code, timestamp),
                )
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            raise StorageError(f"SQLite sync-state update failed: {error}") from error
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self.path,
                timeout=self._busy_timeout_ms / 1000,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            return connection
        except sqlite3.Error as error:
            raise StorageError(f"unable to open SQLite database: {error}") from error

    def _connect_read_only(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise DatabaseNotFoundError("lottery database does not exist")
        try:
            database_uri = f"{self.path.resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(
                database_uri,
                uri=True,
                timeout=self._busy_timeout_ms / 1000,
                isolation_level=None,
            )
            connection.execute("PRAGMA query_only = ON")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                connection.close()
                raise StorageError(
                    f"unsupported database schema {version}; expected {SCHEMA_VERSION}"
                )
            return connection
        except StorageError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise StorageError(f"unable to open SQLite database: {error}") from error

    @staticmethod
    def _read_draw(
        connection: sqlite3.Connection,
        game_code: str,
        draw_term: str,
    ) -> tuple[Any, ...] | None:
        draw_row = connection.execute(
            """
            SELECT draw_date, special_number, source
            FROM draws
            WHERE game_code = ? AND draw_term = ?
            """,
            (game_code, draw_term),
        ).fetchone()
        if draw_row is None:
            return None
        number_rows = connection.execute(
            """
            SELECT number
            FROM draw_numbers
            WHERE game_code = ? AND draw_term = ?
            ORDER BY position
            """,
            (game_code, draw_term),
        ).fetchall()
        return (*draw_row, tuple(row[0] for row in number_rows))

    @staticmethod
    def _insert_draw(
        connection: sqlite3.Connection,
        draw: Draw,
        timestamp: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO draws (
                game_code, draw_term, draw_date, special_number,
                source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draw.game_code,
                draw.draw_term,
                draw.draw_date.isoformat(),
                draw.special_number,
                draw.source,
                timestamp,
                timestamp,
            ),
        )
        SQLiteStorage._insert_numbers(connection, draw)

    @staticmethod
    def _update_draw(
        connection: sqlite3.Connection,
        draw: Draw,
        timestamp: str,
    ) -> None:
        connection.execute(
            """
            UPDATE draws
            SET draw_date = ?, special_number = ?, source = ?, updated_at = ?
            WHERE game_code = ? AND draw_term = ?
            """,
            (
                draw.draw_date.isoformat(),
                draw.special_number,
                draw.source,
                timestamp,
                draw.game_code,
                draw.draw_term,
            ),
        )
        connection.execute(
            "DELETE FROM draw_numbers WHERE game_code = ? AND draw_term = ?",
            (draw.game_code, draw.draw_term),
        )
        SQLiteStorage._insert_numbers(connection, draw)

    @staticmethod
    def _insert_numbers(connection: sqlite3.Connection, draw: Draw) -> None:
        connection.executemany(
            """
            INSERT INTO draw_numbers (game_code, draw_term, position, number)
            VALUES (?, ?, ?, ?)
            """,
            [
                (draw.game_code, draw.draw_term, position, number)
                for position, number in enumerate(draw.main_numbers, start=1)
            ],
        )


def _same_draw(existing: tuple[Any, ...], draw: Draw) -> bool:
    draw_date_value, special_number, source, numbers = existing
    return (
        draw_date_value == draw.draw_date.isoformat()
        and special_number == draw.special_number
        and source == draw.source
        and numbers == draw.main_numbers
    )


def _migration_text(name: str) -> str:
    return files("taiwan_lotto.migrations").joinpath(name).read_text(encoding="utf-8")


def _draw_filters(
    game_code: str,
    start_date: date | None,
    end_date: date | None,
) -> tuple[str, tuple[str, ...]]:
    clauses = ["game_code = ?"]
    parameters = [game_code]
    if start_date is not None:
        clauses.append("draw_date >= ?")
        parameters.append(start_date.isoformat())
    if end_date is not None:
        clauses.append("draw_date <= ?")
        parameters.append(end_date.isoformat())
    return " AND ".join(clauses), tuple(parameters)


def _rows_to_draws(rows: list[tuple[Any, ...]]) -> list[Draw]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for (
        game_code,
        draw_term,
        draw_date_value,
        special,
        source,
        _position,
        number,
    ) in rows:
        key = (game_code, draw_term)
        entry = grouped.setdefault(
            key,
            {
                "draw_date": draw_date_value,
                "special": special,
                "source": source,
                "numbers": [],
            },
        )
        entry["numbers"].append(number)

    draws = []
    for (game_code, draw_term), entry in grouped.items():
        numbers = tuple(entry["numbers"])
        if len(numbers) != 6:
            raise StorageError(
                f"draw {game_code}/{draw_term} has {len(numbers)} main numbers"
            )
        draws.append(
            Draw(
                game_code=game_code,
                draw_term=draw_term,
                draw_date=date.fromisoformat(entry["draw_date"]),
                main_numbers=numbers,
                special_number=entry["special"],
                source=entry["source"],
            )
        )
    return draws

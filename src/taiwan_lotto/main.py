"""Command-line entry point for Taiwan Lotto."""

from __future__ import annotations

import argparse
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from taiwan_lotto.sources.taiwan_lottery import TaiwanLotterySource
from taiwan_lotto.storage.sqlite import SQLiteStorage, StorageError
from taiwan_lotto.sync import SyncService
from taiwan_lotto.web.server import DEFAULT_PORT, WebServerError, run_web

DEFAULT_DATABASE_PATH = Path("data/taiwan_lotto.db")


def get_version() -> str:
    """Return the injected or installed application version."""
    app_version = os.environ.get("APP_VERSION")
    if app_version:
        return app_version

    try:
        return version("taiwan-lotto")
    except PackageNotFoundError:
        return "0.0.0"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="taiwan-lotto",
        description="Taiwan Lotto data collection and analysis tools.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=get_version(),
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "sync",
        help="Synchronize Lotto 6/49 and Super Lotto draw results.",
    )
    web_parser = subparsers.add_parser(
        "web",
        help="Browse stored draw results in a local Web interface.",
    )
    web_parser.add_argument(
        "--port",
        type=_port_number,
        default=DEFAULT_PORT,
        help=f"Local port to use (default: {DEFAULT_PORT}).",
    )
    web_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the default browser automatically.",
    )
    web_parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip synchronization before starting the Web interface.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line application."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "sync":
        return run_sync()
    if args.command == "web":
        return run_web_command(
            DEFAULT_DATABASE_PATH,
            port=args.port,
            open_browser=not args.no_browser,
            sync_before_start=not args.no_sync,
        )
    parser.print_help()
    return 0


def run_sync(database_path: Path = DEFAULT_DATABASE_PATH) -> int:
    """Synchronize supported games and print a concise result summary."""
    try:
        results = SyncService(
            TaiwanLotterySource(),
            SQLiteStorage(database_path),
        ).run()
    except StorageError as error:
        print(f"Synchronization failed: {error}", file=sys.stderr)
        return 1

    for result in results:
        status = "ok" if result.success else "failed"
        print(
            f"{result.game.name}: status={status} mode={result.mode} "
            f"range={result.start_month:%Y-%m}..{result.end_month:%Y-%m} "
            f"added={result.counts.added} skipped={result.counts.skipped} "
            f"corrected={result.counts.corrected} missing={result.counts.missing}"
        )
        if result.error:
            print(f"{result.game.name}: {result.error}", file=sys.stderr)

    return 0 if all(result.success for result in results) else 1


def run_web_command(
    database_path: Path = DEFAULT_DATABASE_PATH,
    *,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    sync_before_start: bool = True,
) -> int:
    """Synchronize when requested, then start the local Web interface."""
    if sync_before_start:
        print("Synchronizing draw results before starting the Web interface...")
        sync_exit_code = run_sync(database_path)
        if sync_exit_code != 0:
            if not database_path.is_file():
                print(
                    "Synchronization failed and no local database is available; "
                    "the Web interface was not started. Retry when the data source "
                    "is available, or run taiwan-lotto sync first.",
                    file=sys.stderr,
                )
                return sync_exit_code
            print(
                "Warning: synchronization did not complete; starting the Web "
                "interface with the existing local database.",
                file=sys.stderr,
            )

    try:
        return run_web(
            database_path,
            port=port,
            open_browser=open_browser,
        )
    except WebServerError as error:
        print(f"Unable to start Web interface: {error}", file=sys.stderr)
        return 1


def _configure_console_encoding() -> None:
    """Use UTF-8 for Windows console output when reconfiguration is supported."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def cli() -> None:
    """Run the installed console entry point."""
    _configure_console_encoding()
    raise SystemExit(main())


if __name__ == "__main__":
    cli()

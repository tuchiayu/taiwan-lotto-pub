"""Where the draw database lives (design 008).

The first of: `--data-dir`, the `TLL_DATA_DIR` environment variable, a source
checkout's `dev-data/` (marked by its committed README), or a fixed per-user
folder. Never the current working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

DATABASE_FILENAME = "taiwan_lotto.db"
ENV_VAR = "TLL_DATA_DIR"
# src/taiwan_lotto/paths.py -> the repository root in a source checkout; an
# installed wheel has no dev-data/ marker there.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEV_DATA_MARKER = Path("dev-data") / "README.md"


def resolve_data_dir(cli_value: str | Path | None = None) -> Path:
    """Return the data folder, highest-priority source first."""
    if cli_value is not None:
        return Path(cli_value).expanduser().resolve()
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return Path(env_value).expanduser().resolve()
    return dev_data_dir() or default_data_dir()


def dev_data_dir() -> Path | None:
    """A source checkout's `dev-data/`, so development never touches the
    installed program's data."""
    marker = _PROJECT_ROOT / DEV_DATA_MARKER
    return marker.parent if marker.is_file() else None


def default_data_dir() -> Path:
    """The per-user folder an installed copy uses."""
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / "AppData" / "Local"
        )
        return base / "TaiwanLotto" / "data"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "taiwan-lotto"


def database_path(cli_value: str | Path | None = None) -> Path:
    return resolve_data_dir(cli_value) / DATABASE_FILENAME

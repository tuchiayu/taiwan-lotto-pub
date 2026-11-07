"""Design 008: where the draw database lives."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from taiwan_lotto import paths


@pytest.fixture
def no_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.delenv(paths.ENV_VAR, raising=False)
    return monkeypatch


@pytest.fixture
def checkout(tmp_path: Path, no_env: pytest.MonkeyPatch) -> Path:
    """A fake repository root with the committed dev-data marker."""
    (tmp_path / "dev-data").mkdir()
    (tmp_path / "dev-data" / "README.md").write_text("marker\n")
    no_env.setattr(paths, "_PROJECT_ROOT", tmp_path)
    return tmp_path


def test_cli_value_wins_over_everything(
    checkout: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(paths.ENV_VAR, str(tmp_path / "env"))

    assert paths.resolve_data_dir(tmp_path / "cli") == (tmp_path / "cli").resolve()


def test_environment_variable_wins_over_dev_data(
    checkout: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(paths.ENV_VAR, str(tmp_path / "env"))

    assert paths.resolve_data_dir() == (tmp_path / "env").resolve()


def test_an_empty_environment_variable_is_ignored(checkout: Path, monkeypatch) -> None:
    monkeypatch.setenv(paths.ENV_VAR, "")

    assert paths.resolve_data_dir() == checkout / "dev-data"


def test_a_source_checkout_uses_its_dev_data(checkout: Path) -> None:
    assert paths.dev_data_dir() == checkout / "dev-data"
    assert paths.database_path() == checkout / "dev-data" / "taiwan_lotto.db"


def test_without_the_marker_the_per_user_folder_is_used(tmp_path: Path, no_env) -> None:
    (tmp_path / "dev-data").mkdir()  # A folder alone is not the marker.
    no_env.setattr(paths, "_PROJECT_ROOT", tmp_path)

    assert paths.dev_data_dir() is None
    assert paths.resolve_data_dir() == paths.default_data_dir()


def test_cli_value_expands_home(no_env, tmp_path: Path) -> None:
    no_env.setenv("HOME", str(tmp_path))
    no_env.setenv("USERPROFILE", str(tmp_path))

    assert paths.resolve_data_dir("~/lotto") == (tmp_path / "lotto").resolve()


def as_system(monkeypatch, name: str, environ: dict[str, str], home: Path) -> None:
    """Swap only the `os` paths.py sees; pathlib itself must keep the real one."""
    monkeypatch.setattr(paths, "os", SimpleNamespace(name=name, environ=environ))
    monkeypatch.setattr(paths.Path, "home", lambda: home)


@pytest.mark.parametrize(
    ("name", "environ", "expected"),
    [
        ("nt", {"LOCALAPPDATA": "{tmp}"}, ("TaiwanLotto", "data")),
        ("nt", {}, ("{home}", "AppData", "Local", "TaiwanLotto", "data")),
        ("posix", {"XDG_DATA_HOME": "{tmp}"}, ("taiwan-lotto",)),
        ("posix", {}, ("{home}", ".local", "share", "taiwan-lotto")),
    ],
)
def test_per_user_default_folder(
    monkeypatch, tmp_path: Path, name, environ, expected
) -> None:
    home = tmp_path / "home"
    env = {k: v.format(tmp=tmp_path) for k, v in environ.items()}
    as_system(monkeypatch, name, env, home)

    start = home if expected[0] == "{home}" else tmp_path
    parts = expected[1:] if expected[0] == "{home}" else expected
    assert paths.default_data_dir() == start.joinpath(*parts)


def test_this_checkout_carries_the_marker() -> None:
    """The committed marker is what makes a source run use dev-data/."""
    assert (paths._PROJECT_ROOT / paths.DEV_DATA_MARKER).is_file()

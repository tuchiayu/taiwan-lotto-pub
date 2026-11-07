"""Shared test isolation."""

from __future__ import annotations

import pytest

from taiwan_lotto.paths import ENV_VAR


@pytest.fixture(autouse=True)
def _isolated_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path_factory) -> None:
    """Design 008: a CLI test never reads or writes the checkout's dev-data/
    or the user's real data folder; tests of the resolution order unset it."""
    monkeypatch.setenv(ENV_VAR, str(tmp_path_factory.mktemp("lotto-data")))

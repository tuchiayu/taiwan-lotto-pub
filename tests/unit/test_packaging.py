"""The installed package declares the runtime pins from requirements.txt."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def requirement_lines(text: str) -> set[str]:
    return {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def test_package_declares_the_pinned_runtime_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set(project["project"]["dependencies"])
    pinned = requirement_lines((ROOT / "requirements.txt").read_text(encoding="utf-8"))

    assert pinned
    assert declared == pinned


def test_requirement_lines_skip_comments_and_blanks() -> None:
    lines = requirement_lines("fastapi==1\n# note\n\n  uvicorn==2  \n")

    assert lines == {"fastapi==1", "uvicorn==2"}

# this_file: tests/test_main_module.py
"""``python -m fontlab_glyport`` starts the CLI without native host imports."""

from __future__ import annotations

import runpy
import subprocess
import sys

import pytest


def test_main_module_when_help_then_subprocess_exits_zero_with_usage() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "fontlab_glyport", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage: glyport"), result.stdout


def test_main_module_when_help_then_runpy_exits_zero_with_usage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """In-process twin so the per-module coverage gate sees ``__main__.py`` execute."""
    monkeypatch.setattr(sys, "argv", ["fontlab_glyport", "--help"])
    with pytest.raises(SystemExit) as raised:
        runpy.run_module("fontlab_glyport", run_name="__main__")
    assert raised.value.code == 0
    assert capsys.readouterr().out.startswith("usage: glyport")

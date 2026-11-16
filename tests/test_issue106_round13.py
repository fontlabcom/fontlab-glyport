# this_file: tests/test_issue106_round13.py
"""Execution cleanup failures must not produce successful execution receipts."""

import os
import sys
from pathlib import Path

import pytest

from fontlab_glyport import run_script
from fontlab_glyport.entrypoints import ExecutionHost
from fontlab_glyport.receipt import ReceiptEnvironment, validate_receipt


@pytest.mark.parametrize("phase", ["path collection", "cwd restoration"])
def test_cleanup_failure_marks_execution_failed_and_names_phase_in_receipt(
    tmp_path, monkeypatch, phase
):
    caller, scripts = tmp_path / "caller", tmp_path / "scripts"
    caller.mkdir()
    scripts.mkdir()
    monkeypatch.chdir(caller)
    path = scripts / "main.py"
    path.write_text(
        "import sys\nprint('body finished')\nsys.path = None\n"
        if phase == "path collection"
        else "print('body finished')\n"
    )
    output = []
    host = ExecutionHost(
        lambda operation: operation(),
        ReceiptEnvironment("fixture", "1", "3.11", "5.15", "test", "test"),
        sink=output.append,
    )
    original_chdir, original_path = os.chdir, sys.path

    def refuse_restore(directory):
        if Path(directory) == caller:
            raise OSError("injected cwd restore failure")
        original_chdir(directory)

    if phase == "cwd restoration":
        monkeypatch.setattr(os, "chdir", refuse_restore)
    try:
        with pytest.raises((TypeError, OSError)) as caught:
            run_script(path, profile="glyphs4", host=host)
        handle = caught.value.handle
        assert "body finished" in "".join(output)
        assert handle.state == "failed"
        stages = [(stage.name, stage.status) for stage in handle.receipt.stages]
        assert stages == [("execution", "failed"), ("close", "passed")]
        diagnostics = [
            d
            for d in handle.receipt.diagnostics
            if d.code == "EXECUTION_CLEANUP_FAILED"
        ]
        assert len(diagnostics) == 1
        assert diagnostics[0].severity == "error"
        assert diagnostics[0].capability == "execution:cleanup"
        assert phase in diagnostics[0].message
        assert type(caught.value).__name__ in diagnostics[0].message
        assert diagnostics[0].message in handle.receipt.stages[0].evidence
        assert validate_receipt(handle.receipt.to_dict(), public=False) == []
        assert sys.path == original_path
        if phase == "path collection":
            assert Path.cwd() == caller
    finally:
        monkeypatch.setattr(os, "chdir", original_chdir)
        original_chdir(caller)
        sys.path = original_path

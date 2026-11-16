# this_file: tests/test_native_verifier.py
"""Host-side native verification transports only owned fixtures and emits R018."""

import json
import os
from types import SimpleNamespace

import pytest

from fontlab_glyport.cli import main, verify_manifest
from fontlab_glyport.receipt import validate_receipt
from fontlab_glyport.receipt_native import NativeRunner


def matrix(tmp_path):
    path = tmp_path / "matrix.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "regression_targets": [
                    {
                        "id": f"case-{i:02}",
                        "path": f"never-read/repo/{i}.py",
                        "sha256": "a" * 64,
                        "repository_head": "b" * 40,
                        "categories": ["glyphs_model"],
                        "acceptance": "full corpus acceptance remains separate",
                    }
                    for i in range(32)
                ],
            }
        )
    )
    return path


class RemopyDouble:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def run(self, code, **variables):
        self.calls.append((code, variables))
        return SimpleNamespace(
            value={
                "status": "passed",
                "evidence": ["owned-fixture:42"],
                "environment": {
                    "host": "FontLab",
                    "host_build": None,
                    "python": "3.11.6",
                    "qt": None,
                    "os": "Darwin",
                    "arch": "arm64",
                },
            }
        )


def test_native_runner_receipt_and_no_corpus_execution():
    client = RemopyDouble()
    with NativeRunner(client_factory=lambda: client) as runner:
        outcome = runner(
            {
                "id": "owned",
                "path": "never-read/corpus.py",
                "sha256": "a" * 64,
                "categories": ["glyphs_model"],
            }
        )
    assert outcome["status"] == "passed"
    assert validate_receipt(outcome["receipt"], public=False) == []
    assert outcome["receipt"]["source"]["sha256"] != "a" * 64
    assert outcome["receipt"]["stages"][0]["name"] == "initial-regression"
    assert all("purge" in code or "sys.modules" in code for code, _ in client.calls)
    assert all(
        "never-read" not in json.dumps(variables) for _, variables in client.calls
    )


def test_native_cli_writes_one_validated_receipt_per_case(tmp_path, monkeypatch):
    import fontlab_glyport.receipt_native as native

    monkeypatch.setattr(native, "_fontlab_client", lambda: RemopyDouble())
    output = tmp_path / "report.json"
    assert (
        main(
            [
                "verify",
                "--manifest",
                str(matrix(tmp_path)),
                "--native",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text())
    assert report["scope"] == "initial-regression"
    assert report["summary"]["passed"] == 32
    receipts = list((tmp_path / "report.receipts").glob("*.json"))
    assert len(receipts) == 32
    for row in report["targets"]:
        assert row["corpus_acceptance"] == "unexecuted"
        data = json.loads((output.parent / row["receipt"]).read_text())
        assert validate_receipt(data, public=False) == []
        assert all(c["status"] == "unexecuted" for c in data["capabilities"])


def test_native_cli_default_output_and_transport_failures(tmp_path, monkeypatch):
    import fontlab_glyport.receipt_native as native

    class Broken(RemopyDouble):
        def run(self, code, **variables):
            raise TimeoutError("outcome unknown; no retry")

    monkeypatch.setattr(native, "_fontlab_client", lambda: Broken())
    monkeypatch.chdir(tmp_path)
    assert main(["verify", "--manifest", str(matrix(tmp_path)), "--native"]) == 1
    report = json.loads(
        (tmp_path / "glyport-initial-regression/report.json").read_text()
    )
    assert report["summary"]["failed"] == 32
    assert (
        len(list((tmp_path / "glyport-initial-regression/receipts").glob("*.json")))
        == 32
    )


def test_attempted_custom_cases_emit_valid_receipts_even_on_failure(tmp_path):
    def fail(row):
        raise RuntimeError("fixture failed")

    report = verify_manifest(matrix(tmp_path), runner=fail)
    for row in report["targets"]:
        assert validate_receipt(row["receipt"], public=False) == []
        assert row["receipt"]["stages"][0]["status"] == "failed"


def test_custom_exemption_receipts_require_typed_role_reasons(tmp_path):
    path = matrix(tmp_path)
    outcome = {
        "status": "not_applicable",
        "evidence": ["fixture:role"],
        "requested": False,
        "role": "packaging-helper",
        "reason": "Runtime stage was not requested for this role.",
    }
    report = verify_manifest(path, runner=lambda row: outcome)
    assert report["summary"]["not_applicable"] == 32
    assert all(
        validate_receipt(row["receipt"], public=False) == []
        for row in report["targets"]
    )
    outcome["role"] = ["invalid-type"]
    assert verify_manifest(path, runner=lambda row: outcome)["summary"]["failed"] == 32


def test_missing_remopy_dependency_is_precise(monkeypatch):
    import sys

    from fontlab_glyport.errors import DependencyUnavailable

    monkeypatch.setitem(sys.modules, "fontlab_remopy", None)
    with pytest.raises(DependencyUnavailable, match="fontlab-remopy"), NativeRunner():
        pass


@pytest.mark.parametrize(
    "probe",
    [
        "modern",
        "vanilla",
        "archive",
        "legacy",
        "process",
        "service",
        "dependencies",
        "bytecode",
    ],
)
def test_embedded_native_fixture_in_isolated_harness(probe, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    if probe == "bytecode" and sys.version_info[:2] != (3, 11):
        pytest.skip("native bytecode probe requires Python 3.11")
    root = Path(__file__).resolve().parents[1]
    code = """
import json,sys,types
from ui_doubles import make_qt
qt=make_qt()
qt.QtGui.QApplication.instance=staticmethod(lambda: object())
sys.modules['PythonQt']=qt
sys.modules['fontlab']=types.ModuleType('fontlab')
from fontlab_glyport.receipt_native import NATIVE_FIXTURE
namespace={'package_path':sys.argv[1], 'probe':sys.argv[2], 'process_python':sys.executable}
exec(compile(NATIVE_FIXTURE,'<initial-regression>','exec'),namespace)
print(json.dumps(namespace['result']))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(root / "src"), probe],
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                filter(
                    None,
                    (
                        str(root / "tests"),
                        str(root / "src"),
                        os.environ.get("PYTHONPATH"),
                    ),
                )
            ),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    # Legacy intentionally writes to the context Output; JSON remains the last line.
    outcome = json.loads(result.stdout.splitlines()[-1])
    assert outcome["status"] == "passed", outcome


def test_native_client_when_remopy_absent_then_install_hint(monkeypatch):
    """R046: fontlab-remopy is the optional `native` extra and is not on PyPI;
    without it, --native fails with an install hint, not a bare ImportError."""
    import sys

    from fontlab_glyport import receipt_native
    from fontlab_glyport.errors import DependencyUnavailable

    monkeypatch.setitem(sys.modules, "fontlab_remopy", None)  # import raises
    with pytest.raises(DependencyUnavailable) as caught:
        receipt_native._fontlab_client()
    message = str(caught.value)
    assert caught.value.capability == "verification:remopy"
    assert "fontlab-glyport[native]" in message and "not on PyPI" in message
    assert "fontlab-remopy" in message and "wheel" in message

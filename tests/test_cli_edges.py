# this_file: tests/test_cli_edges.py
"""CLI boundary behaviour: malformed manifests, runner contract, inspect output, module entry."""

import json
import subprocess
import sys

import pytest
from test_verify_runtime import manifest

from fontlab_glyport.cli import main, verify_manifest


def _edit(tmp_path, mutate):
    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    data = mutate(data) or data
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: [d], "Manifest must be a JSON object"),
        (
            lambda d: d["regression_targets"].__setitem__(0, "x"),
            "Each regression target must be an object",
        ),
        (
            lambda d: d["regression_targets"][0].update(sha256="A" * 64),
            "sha256 must be lowercase hexadecimal or null",
        ),
        (
            lambda d: d["regression_targets"][0].update(sha256="a" * 63),
            "sha256 must be lowercase hexadecimal or null",
        ),
    ],
)
def test_verify_manifest_when_malformed_then_value_error(tmp_path, mutate, message):
    path = _edit(tmp_path, mutate)
    with pytest.raises(ValueError, match=message):
        verify_manifest(path)


@pytest.mark.parametrize("evidence", [[], "x", [""], [1]])
def test_verify_manifest_when_runner_evidence_invalid_then_target_failed(
    tmp_path, evidence
):
    report = verify_manifest(
        manifest(tmp_path),
        runner=lambda row: {"status": "passed", "evidence": evidence},
    )
    assert report["summary"]["failed"] == 32
    assert any(
        "nonempty evidence" in d["message"] for d in report["targets"][0]["diagnostics"]
    )


def test_verify_manifest_when_native_receipt_invalid_then_target_failed(tmp_path):
    report = verify_manifest(
        manifest(tmp_path),
        runner=lambda row: {
            "status": "passed",
            "evidence": ["ok"],
            "receipt": {"stages": []},
        },
    )
    first = report["targets"][0]
    assert first["status"] == "failed"
    assert [d["code"] for d in first["diagnostics"]] == ["INVALID_NATIVE_RECEIPT"]


def test_cli_when_runner_has_no_colon_then_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "verify",
                "--manifest",
                str(manifest(tmp_path)),
                "--output",
                str(tmp_path / "r.json"),
                "--runner",
                "nocolon",
            ]
        )
    assert raised.value.code == 2
    assert "--runner must be module:function" in capsys.readouterr().err


def test_cli_when_runner_not_callable_then_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "verify",
                "--manifest",
                str(manifest(tmp_path)),
                "--output",
                str(tmp_path / "r.json"),
                "--runner",
                "json:__name__",
            ]
        )
    assert raised.value.code == 2
    assert "must resolve to a callable" in capsys.readouterr().err


def test_cli_when_runner_passes_everything_then_exit_0(tmp_path, monkeypatch):
    (tmp_path / "okrunner.py").write_text(
        "def run(row):\n"
        "    return {'status': 'passed', 'evidence': ['fixture ' + row['id']]}\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    out = tmp_path / "r.json"
    code = main(
        [
            "verify",
            "--manifest",
            str(manifest(tmp_path)),
            "--output",
            str(out),
            "--runner",
            "okrunner:run",
        ]
    )
    assert code == 0
    assert json.loads(out.read_text())["summary"]["failed"] == 0


def test_cli_when_verify_has_no_output_or_native_then_exit_2(tmp_path, capsys):
    with pytest.raises(SystemExit) as raised:
        main(["verify", "--manifest", str(manifest(tmp_path))])
    assert raised.value.code == 2
    assert "--output is required without --native" in capsys.readouterr().err


def _source(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n")
    return src


def test_cli_inspect_when_output_inside_source_then_refused(tmp_path, capsys):
    src = _source(tmp_path)
    with pytest.raises(SystemExit) as raised:
        main(["inspect", str(src), "--json", str(src / "out.json")])
    assert raised.value.code == 2
    assert "outside the original source" in capsys.readouterr().err
    assert not (src / "out.json").exists()


def test_cli_inspect_when_output_is_the_source_file_then_refused(tmp_path):
    src = _source(tmp_path) / "a.py"
    with pytest.raises(SystemExit) as raised:
        main(["inspect", str(src), "--json", str(src)])
    assert raised.value.code == 2
    assert src.read_text() == "x = 1\n"


def test_cli_inspect_when_output_outside_then_writes_once(tmp_path, capsys):
    src = tmp_path / "Original.py"
    src.write_text("from GlyphsApp import Glyphs\n")
    out = tmp_path / "assessment.json"
    code = main(["inspect", str(src), "--json", str(out)])
    assert code == 0
    first = out.read_bytes()
    assert isinstance(json.loads(first), dict)
    with pytest.raises(SystemExit) as refused:
        main(["inspect", str(src), "--json", str(out)])
    assert refused.value.code == 2
    assert "exists" in capsys.readouterr().err.lower()
    assert out.read_bytes() == first


def test_module_entry_when_run_as_subprocess_then_reports_exit_code(tmp_path):
    path = manifest(tmp_path)
    out = tmp_path / "r.json"
    run = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "fontlab_glyport",
            "verify",
            "--manifest",
            str(path),
            "--output",
            str(out),
        ],
        capture_output=True,
        check=False,
        text=True,
        cwd=tmp_path,
        timeout=60,
    )
    assert run.returncode == 2, run.stderr
    assert json.loads(out.read_text())["summary"]["blocked"] == 32
    bad = subprocess.run(
        [sys.executable, "-B", "-m", "fontlab_glyport"],
        capture_output=True,
        check=False,
        text=True,
        cwd=tmp_path,
        timeout=60,
    )
    assert bad.returncode == 2
    assert "usage: glyport" in bad.stderr

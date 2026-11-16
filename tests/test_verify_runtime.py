# this_file: tests/test_verify_runtime.py
"""Matrix reports never execute source; native assertions are explicit plugins."""

import json

import pytest

from fontlab_glyport.cli import main, verify_manifest


def manifest(tmp_path):
    path = tmp_path / "matrix.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "regression_targets": [
                    {
                        "id": f"target-{i:02}",
                        "path": f"repo/script-{i}.py",
                        "sha256": "a" * 64,
                        "repository_head": "b" * 40,
                        "categories": ["glyphs_model"],
                        "acceptance": "Verify fixture",
                        "state": "unexecuted",
                        "gate": "native-fontlab-required",
                    }
                    for i in reversed(range(32))
                ],
            }
        )
    )
    return path


def test_report_deterministic_and_default_blocked(tmp_path):
    path = manifest(tmp_path)
    a = verify_manifest(path)
    assert a == verify_manifest(path)
    assert len(a["targets"]) == 32
    assert a["targets"][0]["id"] == "target-00"
    assert {r["status"] for r in a["targets"]} == {"blocked"}
    assert a["summary"]["passed"] == 0


def test_native_runner_evidence_and_failures(tmp_path):
    def runner(target):
        if target["id"] == "target-00":
            raise RuntimeError("fixture error")
        return {"status": "passed", "evidence": ["native:fixture"]}

    result = verify_manifest(manifest(tmp_path), runner=runner)
    assert result["summary"]["passed"] == 31
    assert result["summary"]["failed"] == 1
    assert (
        result["targets"][0]["diagnostics"][0]["code"] == "NATIVE_VERIFICATION_FAILED"
    )


def test_invalid_runner_cannot_claim_pass_or_exemption(tmp_path):
    path = manifest(tmp_path)
    for value in (
        {"status": "passed"},
        {"status": "not_applicable", "evidence": ["x"]},
    ):
        assert (
            verify_manifest(path, runner=lambda row, value=value: value)["summary"][
                "failed"
            ]
            == 32
        )


def test_cli_writes_report_and_does_not_overwrite(tmp_path):
    path = manifest(tmp_path)
    output = tmp_path / "report.json"
    assert (
        main(
            [
                "verify",
                "--manifest",
                str(path),
                "--host",
                "fontlab",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert len(json.loads(output.read_text())["targets"]) == 32
    with pytest.raises(SystemExit):
        main(["verify", "--manifest", str(path), "--output", str(output)])


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "traversal"])
def test_bad_manifest_rejected(tmp_path, mutation):
    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    if mutation == "duplicate":
        data["regression_targets"][0]["id"] = data["regression_targets"][1]["id"]
    elif mutation == "missing":
        data["regression_targets"].pop()
    else:
        data["regression_targets"][0]["path"] = "../private.py"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        verify_manifest(path)

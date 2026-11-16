# this_file: tests/test_realuse_archive.py
"""Portable realuse closure retains the frozen matrix and exact fixture bytes."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_portable_manifest_when_loaded_then_preserves_frozen_behavior():
    portable = json.loads((ROOT / "realuse/manifest-portable.json").read_text())
    provenance = json.loads((ROOT / "realuse/provenance.json").read_text())
    assert provenance["original_manifest_sha256"] == "2f67f8b0c6ddc0f1251c0aae448ec02b195f95eacdeae9ecedc256a93c3e405a"
    assert provenance["targets_sha256"] == "591a32e48ac92a305959e082abc4a796ab6584e6ae85ec35543b057403d11f55"
    assert len(portable["targets"]) == 67
    assert (
        hashlib.sha256(
            json.dumps(portable["targets"], sort_keys=True).encode()
        ).hexdigest()
        == provenance["targets_sha256"]
    )
    assert len(list((ROOT / "realuse/oracles").glob("*.py"))) == 67
    original = ROOT / "realuse/manifest.json"
    if original.exists():
        assert (
            hashlib.sha256(original.read_bytes()).hexdigest()
            == provenance["scrubbed_manifest_sha256"]
        ), "manifest.json changed beyond the recorded machine-path scrub"
        frozen = json.loads(original.read_text())
        assert frozen["corpus"] == "$GLYPORT_ORIGINAL_CORPUS"
        assert frozen["selection_parameters"]["vocabulary"] == "$GLYPORT_GLYPHS_VOCABULARY"
        frozen["corpus"] = portable["corpus"]
        frozen["selection_parameters"]["vocabulary"] = portable["selection_parameters"][
            "vocabulary"
        ]
        assert frozen == portable


def test_getgo_when_packaged_then_matches_upstream_bytes():
    root = ROOT / "realuse/fixtures/getgo"
    inventory = json.loads((root / "provenance.json").read_text())
    assert {
        name: digest
        for name, digest in inventory["files"].items()
        if name.endswith(".vfj")
    } == {
        "apache/cafe/cafe.vfj": "1917b74b17496999b6d71bfb6b212d10d8777bf26e35948cd10de3f2b00abc51",
        "apache/zotosans/zotosans-gurmukhi.vfj": "da231530b0283f039bbfa1fcfbba327aa8aeb65e6301269c655b80b45268c8a3",
        "cc0/plum/plum-var.vfj": "f4ab33f1ebe1325fd945090fb9867a95f8adde11a79aa8237faccae32b4be4a9",
    }
    for name, digest in inventory["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name


def test_native_entry_when_workspace_missing_then_refuses(monkeypatch):
    from test_realuse_harness import load

    common = load("realuse_common")
    monkeypatch.setattr(common, "WORKSPACE", None)
    import pytest

    with pytest.raises(RuntimeError, match="requires the FontLab scripting workspace"):
        common.require_workspace()


def test_revision_when_source_archive_then_reports_archive_metadata(
    tmp_path, monkeypatch
):
    from test_realuse_harness import load

    common = load("realuse_common")
    monkeypatch.setattr(common, "REPO", tmp_path)
    monkeypatch.setattr(common, "WORKSPACE", None)
    (tmp_path / "PKG-INFO").write_text("Metadata-Version: 2.4\nVersion: 1.2.3\n")
    assert common.revision() == "archive:1.2.3"


def test_revision_when_archive_nested_under_workspace_then_reports_archive_metadata(
    tmp_path, monkeypatch
):
    from test_realuse_harness import load

    common = load("realuse_common")
    monkeypatch.setattr(common, "REPO", tmp_path)
    # Simulate the discovered ancestor value without making a fake workspace marker.
    monkeypatch.setattr(common, "WORKSPACE", tmp_path.parent)
    (tmp_path / "PKG-INFO").write_text("Metadata-Version: 2.4\nVersion: 1.2.3\n")
    assert common.revision() == "archive:1.2.3"


def test_native_entrypoints_when_workspace_missing_then_refuse_before_transport(
    tmp_path, monkeypatch
):
    import pytest
    from test_realuse_harness import load

    common = load("realuse_common")
    driver = load("run_realuse")
    monkeypatch.setattr(common, "WORKSPACE", None)
    import sys
    from types import SimpleNamespace

    attempts = []

    def forbidden_native(*args, **kwargs):
        attempts.append(args)
        raise AssertionError("Native client or run attempted without a workspace")

    monkeypatch.setattr(driver, "Run", forbidden_native)
    monkeypatch.setitem(sys.modules, "fontlab_remopy", SimpleNamespace(FontLab=forbidden_native))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"targets": [{"id": "owned", "path": "owned/test.py"}]}))
    with pytest.raises(RuntimeError, match="requires the FontLab scripting workspace"):
        driver.main(["--manifest", str(manifest), "--out", str(tmp_path), "owned"])
    with pytest.raises(RuntimeError, match="requires the FontLab scripting workspace"), common.Run.__new__(common.Run).fontlab():
        pytest.fail("Native transport must not start without a workspace")

    assert not attempts, "Neither native entrypoint may attempt transport without a workspace"

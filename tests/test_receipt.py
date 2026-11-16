# this_file: tests/test_receipt.py
"""Receipt persistence must publish complete UTF-8 JSON without clobbering files."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier

import pytest

from fontlab_glyport import ReceiptSource, validate_receipt, write_receipt


def test_receipt_when_written_then_round_trips_as_utf8_json(receipt, tmp_path):
    output = tmp_path / "receipt.json"
    write_receipt(receipt, output)
    raw = output.read_bytes()
    assert "café".encode() in raw, "Unicode must be persisted as UTF-8"
    data = json.loads(raw)
    assert data == receipt.to_dict()
    assert validate_receipt(data) == []
    assert isinstance(data["source"]["dirty_files"], dict)
    assert all(
        isinstance(data[key], list)
        for key in ("adaptations", "capabilities", "stages", "artifacts", "diagnostics")
    )
    assert isinstance(data["stages"][0]["evidence"], list)
    assert list(tmp_path.iterdir()) == [output], "temporary files must be removed"


def test_receipt_when_inputs_or_export_mutate_then_records_stay_frozen(receipt):
    dirty = {"script.py": "a" * 64}
    source = ReceiptSource("repo", "rev", "script.py", "a" * 64, dirty)
    capabilities = list(receipt.capabilities)
    frozen = replace(receipt, source=source, capabilities=capabilities)
    dirty.clear()
    capabilities.clear()
    exported = frozen.to_dict()
    exported["source"]["dirty_files"].clear()
    exported["capabilities"][0]["evidence"].clear()
    assert frozen.source.dirty_files == {"script.py": "a" * 64}
    assert frozen.capabilities[0].evidence == ("fixture:model",)
    with pytest.raises(FrozenInstanceError):
        frozen.run_id = "changed"
    with pytest.raises(TypeError):
        frozen.source.dirty_files["other.py"] = "b" * 64


@pytest.mark.parametrize(
    "kind", ["file", "directory", "symlink", "dangling", "hardlink"]
)
def test_write_when_destination_exists_then_refuses_and_preserves_it(
    receipt, tmp_path, kind
):
    original = tmp_path / "original"
    original.write_bytes(b"original")
    output = tmp_path / "receipt.json"
    if kind == "directory":
        output.mkdir()
    elif kind in ("symlink", "dangling"):
        output.symlink_to(original if kind == "symlink" else tmp_path / "missing")
    elif kind == "hardlink":
        os.link(original, output)
    else:
        output.write_bytes(b"existing")
    before = output.lstat()
    with pytest.raises(FileExistsError):
        write_receipt(receipt, output)
    assert output.lstat() == before, "existing output was altered"
    assert original.read_bytes() == b"original"
    assert len(list(tmp_path.iterdir())) == 2, "failed write leaked staging files"


def test_write_when_two_writers_race_then_exactly_one_publishes(
    receipt, tmp_path, monkeypatch
):
    output = tmp_path / "receipt.json"
    ready = Barrier(2, timeout=5)
    link = os.link

    def publish(source, destination):
        assert validate_receipt(json.loads(source.read_text())) == []
        assert not output.exists(), "publication exposed an empty reservation file"
        ready.wait()
        link(source, destination)

    monkeypatch.setattr(os, "link", publish)

    def write(index):
        try:
            write_receipt(replace(receipt, run_id=str(index)), output)
            return index
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (1, 2)))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1, "concurrent writes must not overwrite each other"
    assert json.loads(output.read_text())["run_id"] == str(winners[0])
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("error_type", [OSError, SystemExit, KeyboardInterrupt])
def test_write_when_replace_fails_then_cleans_up_and_propagates(
    receipt, tmp_path, monkeypatch, error_type
):
    def fail(*args):
        raise error_type("replace interrupted")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(error_type, match="replace interrupted"):
        write_receipt(receipt, tmp_path / "receipt.json")
    assert not list(tmp_path.iterdir()), "incomplete receipt must never be published"


@pytest.mark.parametrize("operation", ["dump", "fsync", "link"])
def test_write_when_io_fails_then_no_partial_file_is_published(
    receipt, tmp_path, monkeypatch, operation
):
    def fail(*args, **kwargs):
        raise OSError("injected I/O failure")

    monkeypatch.setattr(json if operation == "dump" else os, operation, fail)
    with pytest.raises(OSError, match="injected I/O failure"):
        write_receipt(receipt, tmp_path / "receipt.json")
    assert not list(tmp_path.iterdir()), "I/O failure leaked an output or staging file"


def test_write_when_invalid_then_rejects_before_creating_output(receipt, tmp_path):
    with pytest.raises(ValueError, match="run_id"):
        write_receipt(replace(receipt, run_id=""), tmp_path / "receipt.json")
    assert not list(tmp_path.iterdir())


def test_write_when_parent_missing_then_propagates_filesystem_error(receipt, tmp_path):
    with pytest.raises(FileNotFoundError):
        write_receipt(receipt, tmp_path / "missing" / "receipt.json")


def test_write_when_private_mode_explicit_then_allows_private_artifacts(
    receipt, tmp_path
):
    artifact = replace(receipt.artifacts[0], path="/private/output.otf")
    private = replace(receipt, artifacts=(artifact,))
    with pytest.raises(ValueError, match="public"):
        write_receipt(private, tmp_path / "public.json")
    write_receipt(private, tmp_path / "private.json", public=False)
    assert (
        validate_receipt(
            json.loads((tmp_path / "private.json").read_text()), public=False
        )
        == []
    )

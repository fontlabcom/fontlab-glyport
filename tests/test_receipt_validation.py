# this_file: tests/test_receipt_validation.py
"""Malformed receipts report field-specific errors instead of asserting behavior."""

from copy import deepcopy

import pytest

from fontlab_glyport import validate_receipt


def record_paths(data, prefix=()):
    """Visit fixture records to exercise required fields at every nesting level."""
    if isinstance(data, dict):
        yield prefix
        for key, value in data.items():
            yield from record_paths(value, (*prefix, key))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from record_paths(value, (*prefix, index))


def at(data, path):
    for part in path:
        data = data[part]
    return data


def test_required_fields_when_missing_then_all_nested_records_rejected(receipt):
    valid = receipt.to_dict()
    for path in record_paths(valid):
        if path == ("source", "dirty_files"):
            continue
        for key in at(valid, path):
            if key in ("requested", "reason", "field"):
                continue
            data = deepcopy(valid)
            del at(data, path)[key]
            assert any(
                key in error and "required" in error for error in validate_receipt(data)
            ), (path, key)


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        (("schema_version",), True),
        (("schema_version",), "1"),
        (("schema_version",), 2),
        (("run_id",), 3),
        (("run_id",), " "),
        (("source",), []),
        (("environment",), None),
        (("adapter",), "adapter"),
        (("adaptations",), {}),
        (("capabilities",), ()),
        (("stages",), "stages"),
        (("artifacts",), None),
        (("diagnostics",), {}),
        (("stages", 0), 1),
        (("source", "dirty_files"), []),
        (("source", "dirty_files"), {1: "a" * 64}),
        (("source", "dirty_files"), {"foo.py": 1}),
        (("capabilities", 0, "evidence"), "proof"),
        (("stages", 0, "evidence"), [1]),
        (("capabilities", 0, "requested"), "false"),
        (("adaptations", 0, "source_map"), "maps/a.json"),
        (("diagnostics", 0, "severity"), "fatal"),
        (("diagnostics", 0, "code"), "not stable!"),
        (("diagnostics", 0, "location", "line"), True),
        (("diagnostics", 0, "location", "line"), 0),
        (("diagnostics", 0, "location", "column"), -1),
        (("diagnostics", 0, "location", "column"), "1"),
        (("diagnostics", 0, "capability"), 12),
        (("diagnostics", 0, "recovery_action"), []),
    ],
)
def test_structure_when_field_type_or_value_invalid_then_reports_path(
    receipt, path, bad
):
    data = receipt.to_dict()
    at(data, path[:-1])[path[-1]] = bad
    errors = validate_receipt(data)
    assert errors, f"accepted invalid field {path}={bad!r}"
    assert any(str(path[-1]) in error for error in errors), errors


@pytest.mark.parametrize("bad", [None, [], "receipt", 1])
def test_structure_when_root_not_object_then_returns_errors(bad):
    assert validate_receipt(bad), "validation must not crash on malformed input"


@pytest.mark.parametrize(
    "bad", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, "a" * 64 + "\n", 123]
)
def test_hashes_when_invalid_then_all_hash_fields_rejected(receipt, bad):
    paths = [
        ("source", "sha256"),
        ("source", "dirty_files", "src/café.py"),
        ("adaptations", 0, "input_sha256"),
        ("adaptations", 0, "output_sha256"),
        ("adaptations", 0, "source_map", "sha256"),
        ("artifacts", 0, "sha256"),
    ]
    for path in paths:
        data = receipt.to_dict()
        at(data, path[:-1])[path[-1]] = bad
        assert validate_receipt(data), f"invalid hash accepted at {path}"


@pytest.mark.parametrize(
    "bad",
    [
        "2026-10-14",
        "2026-10-14T10:00:00",
        "2026-10-14T10:00:00+00:00",
        "2026-10-14T10:00:00+01:00",
        "2026-02-30T10:00:00Z",
        "2026-10-14T25:00:00Z",
        "2026-10-14 10:00:00Z",
        "2026-10-14T10:00:00z",
        123,
    ],
)
def test_timestamps_when_invalid_then_both_stage_fields_rejected(receipt, bad):
    for key in ("started_at", "finished_at"):
        data = receipt.to_dict()
        data["stages"][0][key] = bad
        assert any(key in error for error in validate_receipt(data))


@pytest.mark.parametrize("collection", ["capabilities", "stages"])
def test_status_when_not_applicable_then_requires_role_reason_and_not_requested(
    receipt, collection
):
    data = receipt.to_dict()
    item = data[collection][0]
    item["status"] = "not_applicable"
    assert validate_receipt(data)
    item["reason"] = "unsupported"
    assert validate_receipt(data), "free text is not a role-based reason"
    item["reason"] = {"role": "helper", "reason": "Imported by the entry point"}
    assert validate_receipt(data), "requested behavior cannot be not_applicable"
    item["requested"] = False
    assert validate_receipt(data) == []
    item["reason"]["role"] = ""
    assert validate_receipt(data)


@pytest.mark.parametrize(
    "status", ["unexecuted", "passed", "failed", "blocked", "unknown", None, []]
)
def test_status_when_supplied_then_checks_enum_for_capabilities_and_stages(
    receipt, status
):
    for collection in ("capabilities", "stages"):
        data = receipt.to_dict()
        data[collection][0]["status"] = status
        assert bool(validate_receipt(data)) == (
            status not in ("unexecuted", "passed", "failed", "blocked")
        )


def test_optional_fact_when_null_then_requires_diagnostic_pointing_to_field(receipt):
    data = receipt.to_dict()
    data["environment"]["qt"] = None
    assert any("environment.qt" in error for error in validate_receipt(data))
    data["diagnostics"][0]["field"] = "environment.qt"
    assert validate_receipt(data) == []
    data["stages"][0]["started_at"] = None
    assert any("stages[0].started_at" in error for error in validate_receipt(data))
    diagnostic = deepcopy(data["diagnostics"][0])
    diagnostic.update(
        field="stages[0].started_at",
        location=None,
        capability=None,
        recovery_action=None,
    )
    data["diagnostics"].append(diagnostic)
    assert validate_receipt(data) == [], (
        "absent diagnostic context must not require recursive diagnostics"
    )


def test_structure_when_unknown_field_then_rejects_typo(receipt):
    data = receipt.to_dict()
    data["source"]["revison"] = "typo"
    assert any("revison" in error for error in validate_receipt(data))

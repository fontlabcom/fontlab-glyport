# this_file: native-drivers/native_05_manifest_verification.py
"""Only matrix metadata enters FontLab. This never executes corpus scripts."""

import json

from driver_common import Driver

with Driver(
    "32-target verifier, deterministic JSON and pluggable native stage"
) as driver:
    if driver.args.manifest is None:
        raise ValueError("--manifest must name corpus-regression-matrix.json")
    original = json.loads(driver.args.manifest.read_text(encoding="utf-8"))
    metadata = {
        "schema_version": original["schema_version"],
        "regression_targets": original["regression_targets"],
    }
    assert len(metadata["regression_targets"]) == 32
    driver.call(
        "metadata-only matrix report and CLI",
        """
import json
from fly.gp.cli import main, verify_manifest
from fly.gp.receipt import validate_receipt
manifest = state.root / "matrix.json"
manifest.write_text(json.dumps(metadata))
a = verify_manifest(manifest)
assert a == verify_manifest(manifest)
assert a["summary"]["blocked"] == 32
assert a["scope"] == "initial-regression"
output = state.root / "report.json"
assert main(["verify", "--manifest", str(manifest), "--host", "fontlab", "--output", str(output)]) == 2
assert json.loads(output.read_text()) == a
state.calls = []
def acceptance_stage(target):
    state.calls.append(target["id"])
    return {"status": "blocked", "evidence": ["native:metadata-routing-only; target acceptance pending"]}
routed = verify_manifest(manifest, runner=acceptance_stage)
assert len(state.calls) == 32
assert routed["summary"]["blocked"] == 32
assert routed["summary"]["passed"] == 0
assert all(validate_receipt(row["receipt"], public=False) == [] for row in routed["targets"])
result = {"targets": 32, "deterministic": True, "runner_calls": len(state.calls), "corpus_native_acceptance": "pending"}
""",
        metadata=metadata,
    )

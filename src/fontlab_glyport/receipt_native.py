# this_file: src/fontlab_glyport/receipt_native.py
"""Host-side Remopy initial regression and R018 receipts for attempted cases.

Only owned, embedded fixtures run in FontLab. Matrix source paths are metadata;
passing this initial regression never establishes corpus-target acceptance.
"""

import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .errors import DependencyUnavailable
from .receipt import (
    Capability,
    Receipt,
    ReceiptAdapter,
    ReceiptDiagnostic,
    ReceiptEnvironment,
    ReceiptSource,
    RoleReason,
    Stage,
    validate_receipt,
)

SCOPE = "initial-regression"

# Fixed, bounded code only: never interpolate source or execute a corpus path.
NATIVE_FIXTURE = """
import sys, time, tempfile, platform
from pathlib import Path
_started = time.monotonic()
_paths = list(sys.path)
sys.path.insert(0, package_path)
try:
    # purge stale lane modules only after previous owned handles were closed
    for name in tuple(sys.modules):
        if name == "fontlab_glyport" or name.startswith("fontlab_glyport."):
            del sys.modules[name]
    from fontlab_glyport import run_script
    from fontlab_glyport.errors import GlyportError, Cancelled, UnsupportedCapability
    status, evidence = "passed", []
    try:
        with tempfile.TemporaryDirectory(prefix="glyport-initial-") as scratch:
            root = Path(scratch)
            if probe == "unsupported":
                raise UnsupportedCapability("This target needs a native protocol/backend outside the owned runtime fixture.")
            if probe == "bytecode":
                import marshal, importlib.util
                from fontlab_glyport import ExecutionContext
                from fontlab_glyport.adaptation_entries import check_pyc
                assert sys.version_info[:2] == (3, 11)
                source = root / "owned.pyc"
                source.write_bytes(importlib.util.MAGIC_NUMBER + bytes(12) + marshal.dumps(compile("value=42", "owned.py", "exec")))
                context = ExecutionContext(root, "glyphs3")
                try:
                    context.run(source)
                    assert context.globals["value"] == 42
                finally:
                    context.close()
                evidence.append("owned fixture: CPython 3.11 bytecode execution")
            elif probe == "archive":
                import zipfile
                from fontlab_glyport.adaptation_entries import unpack_archive
                archive = root / "misleading313.zip"
                with zipfile.ZipFile(archive, "w") as stream:
                    stream.writestr("owned.py", "value=42")
                unpacked = unpack_archive(archive, root / "unpacked")
                assert (unpacked / "owned.py").read_text() == "value=42"
                evidence.append("owned fixture: ZIP members, independent of archive filename")
            elif probe == "process":
                from fontlab_glyport.dependencies import run_process
                completed = run_process([process_python, "-c", "print(42)"], timeout=.6)
                assert completed.stdout.strip() == "42"
                evidence.append("owned fixture: bounded external process output")
            elif probe == "service":
                from fontlab_glyport.dependencies import request_service
                try:
                    request_service("http://127.0.0.1/", timeout=.1, cancelled=lambda: True)
                except Cancelled:
                    pass
                else:
                    raise AssertionError("service cancellation lost")
                evidence.append("owned fixture: service cancellation before I/O; no remote endpoint contacted")
            elif probe == "dependencies":
                from fontlab_glyport.dependencies import dependency_route
                assert dependency_route("fontTools.ttLib").route == "python"
                assert dependency_route("fontParts.world").route == "python"
                assert dependency_route("drawBot").route == "adapter-required"
                evidence.append("owned fixture: dependency route detection only; installed backends unverified")
            else:
                source = root / "owned.py"
                if probe == "legacy":
                    source.write_text("print 'owned regression'\\n")
                    profile = "glyphs2"
                elif probe == "vanilla":
                    source.write_text("from vanilla import Window, Button\\nhits=[]\\ndef click(sender):\\n from AppKit import NSMakePoint\\n hits.append(NSMakePoint(4,5).x)\\nw=Window((180,80), 'Glyport owned regression')\\nw.b=Button((10,10,80,20), 'Go', callback=click)\\nw.open()\\n")
                    profile = "glyphs3"
                else:
                    source.write_text("def callback():\\n from Cocoa import NSMakePoint\\n return NSMakePoint(4,5).x\\n")
                    profile = "glyphs4"
                handle = run_script(source, profile=profile)
                try:
                    if probe == "vanilla":
                        window = handle.context.globals["w"]
                        window.b.getNSView().click()
                        assert handle.context.globals["hits"] == [4]
                        assert window in handle.windows
                    elif probe != "legacy":
                        assert handle.wrap(handle.context.globals["callback"])() == 4
                finally:
                    handle.close()
                assert handle.state == "closed"
                evidence.append("owned fixture: " + probe + " execution, callbacks and teardown")
    except GlyportError as error:
        status, evidence = "blocked", [type(error).__name__ + ": " + str(error)]
    except Exception as error:
        status, evidence = "failed", [type(error).__name__ + ": " + str(error)]
    if time.monotonic() - _started >= 2:
        status, evidence = "failed", ["Owned native check exceeded the two-second budget."]
    result = {"status": status, "evidence": evidence,
              "environment": {"host":"FontLab", "host_build":None, "python":platform.python_version(),
                              "qt":None, "os":platform.system(), "arch":platform.machine()}}
finally:
    sys.path[:] = _paths
"""


def case_receipt(
    target: dict,
    status: str,
    evidence: list,
    *,
    diagnostics: list = (),
    environment: dict | None = None,
    fixture_hash: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    run_id: str | None = None,
    profile: str = "auto",
    role: str | None = None,
    reason: str | None = None,
) -> dict:
    """Build validated facts; omitted times/facts have explicit field diagnostics."""
    identity = hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()
    source = ReceiptSource(
        "fontlabcom/fontlab-glyport" if fixture_hash else None,
        None,
        f"initial-regression/{identity[:16]}.py" if fixture_hash else target["path"],
        fixture_hash or target.get("sha256"),
        {},
    )
    env = ReceiptEnvironment(
        **(
            environment
            or dict.fromkeys(("host", "host_build", "python", "qt", "os", "arch"))
        )
    )
    issues = [
        ReceiptDiagnostic(item["code"], "error", item["message"])
        for item in diagnostics
    ]
    issues.append(
        ReceiptDiagnostic(
            "CORPUS_ACCEPTANCE_UNEXECUTED",
            "info",
            "initial-regression covers owned runtime fixtures only. Pinned corpus source was not read or executed.",
        )
    )
    for prefix, record in (("source", source), ("environment", env)):
        for name, value in record.to_dict().items():
            if value is None:
                issues.append(
                    ReceiptDiagnostic(
                        "FACT_UNAVAILABLE",
                        "info",
                        "Fact was not observed by this initial regression.",
                        field=prefix + "." + name,
                    )
                )
    for name, value in (("started_at", started_at), ("finished_at", finished_at)):
        if value is None:
            issues.append(
                ReceiptDiagnostic(
                    "FACT_UNAVAILABLE",
                    "info",
                    "Timestamp omitted from deterministic embedded receipt.",
                    field="stages[0]." + name,
                )
            )
    receipt = Receipt(
        run_id or f"initial-{identity[:24]}",
        source,
        env,
        ReceiptAdapter("runtime", profile, "initial-regression-1"),
        (),
        (
            Capability(
                "matrix-target-acceptance",
                "unexecuted",
                ("Original target acceptance remains unexecuted.",),
            ),
        ),
        (
            Stage(
                SCOPE,
                status,
                started_at,
                finished_at,
                tuple(evidence),
                requested=status != "not_applicable",
                reason=RoleReason(role, reason) if status == "not_applicable" else None,
            ),
        ),
        (),
        tuple(issues),
    ).to_dict()
    errors = validate_receipt(receipt, public=False)
    if errors:
        raise ValueError("Invalid initial regression receipt: " + "; ".join(errors))
    return receipt


def _fontlab_client():
    try:
        from fontlab_remopy import FontLab
    except ImportError as error:
        raise DependencyUnavailable(
            "--native requires fontlab-remopy in the host-side Python environment "
            "(the optional extra fontlab-glyport[native]). fontlab-remopy is not on "
            "PyPI: install its wheel from the workspace, e.g. "
            "`uv pip install <workspace>/fontlab-remopy/dist/fontlab_remopy-*.whl` "
            "or `uv pip install -e <workspace>/fontlab-remopy`.",
            capability="verification:remopy",
        ) from error
    return FontLab()


def _probe(target: dict) -> str:
    categories = set(target.get("categories", ()))
    routes = (
        (
            {
                "macho_binary",
                "compiled_only",
                "compiled_extension",
                "objective_c_source",
                "wx_other_gui",
                "applescript_dependency",
            },
            "unsupported",
        ),
        ({"python_bytecode"}, "bytecode"),
        ({"archive"}, "archive"),
        ({"process_execution"}, "process"),
        ({"web_remote", "javascript_service", "typescript_service"}, "service"),
        ({"drawbot", "fonttools_robofab"}, "dependencies"),
        ({"python_legacy_signals", "python_parse_error"}, "legacy"),
        ({"vanilla"}, "vanilla"),
    )
    if "archive" in categories:
        return "archive"
    return next((probe for keys, probe in routes if keys & categories), "modern")


class NativeRunner:
    """One Remopy call per owned case; no retries after unknown transport outcomes."""

    def __init__(self, *, client_factory=None, package_path: Path | None = None):
        self.factory = client_factory or _fontlab_client
        self.package_path = str(package_path or Path(__file__).resolve().parent.parent)
        self.run_id = uuid.uuid4().hex

    def __enter__(self):
        self.manager = self.factory()
        self.client = self.manager.__enter__()
        return self

    def __exit__(self, *args):
        return self.manager.__exit__(*args)

    def __call__(self, target: dict) -> dict:
        started = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        diagnostics, environment = [], None
        try:
            outcome = self.client.run(
                NATIVE_FIXTURE,
                package_path=self.package_path,
                probe=_probe(target),
                process_python=sys.executable,
            ).value
            if outcome.get("status") not in {"passed", "blocked", "failed"}:
                raise ValueError("Invalid native fixture status")
            status, evidence, environment = (
                outcome["status"],
                outcome["evidence"],
                outcome["environment"],
            )
        except Exception as error:  # noqa: BLE001 - each transport failure needs its own receipt
            status, evidence = "failed", [f"{type(error).__name__}: {error}"]
            diagnostics.append(
                {"code": "NATIVE_VERIFICATION_FAILED", "message": evidence[0]}
            )
        finished = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        receipt = case_receipt(
            target,
            status,
            evidence,
            diagnostics=diagnostics,
            environment=environment,
            fixture_hash=hashlib.sha256(NATIVE_FIXTURE.encode()).hexdigest(),
            started_at=started,
            finished_at=finished,
            run_id=self.run_id
            + "-"
            + hashlib.sha256(target["id"].encode()).hexdigest()[:16],
            profile={"modern": "glyphs4", "legacy": "glyphs2"}.get(
                _probe(target), "glyphs3"
            ),
        )
        return {"status": status, "evidence": evidence, "receipt": receipt}

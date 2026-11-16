# this_file: src/fontlab_glyport/cli.py
"""Source-only inspection command; never execute a discovered entry point."""

import argparse
import hashlib
import importlib
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from .errors import Cancelled, GlyportError
from .inspection import inspect_source


def verify_manifest(
    path: str | Path,
    *,
    host: str = "fontlab",
    runner: Callable | None = None,
    receipt_dir: Path | None = None,
) -> dict:
    """Verify matrix metadata and invoke only an explicitly supplied native runner.

    Does not open corpus paths, import entry points, or treat lexical inspection
    as acceptance. Runner receives one metadata record and returns status and
    evidence. Its assertions, not this manifest reader, establish native facts.
    """
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be a JSON object")  # noqa: TRY004 - malformed JSON input
    targets = manifest.get("regression_targets")
    if (
        manifest.get("schema_version") != 1
        or not isinstance(targets, list)
        or len(targets) != 32
    ):
        raise ValueError("Expected schema_version 1 and exactly 32 regression_targets")
    seen = set()
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("Each regression target must be an object")  # noqa: TRY004 - malformed JSON input
        identifier, source = target.get("id"), target.get("path")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("Regression target IDs must be nonempty and unique")
        seen.add(identifier)
        if (
            not isinstance(source, str)
            or not source
            or Path(source).is_absolute()
            or ".." in Path(source).parts
            or "\\" in source
        ):
            raise ValueError("Target paths must be relative without traversal")
        digest = target.get("sha256")
        if digest is not None and (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("Target sha256 must be lowercase hexadecimal or null")
    ordered = sorted(targets, key=lambda row: row["id"])
    identity = hashlib.sha256(
        json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    results, cancelled = [], False
    for target in ordered:
        attempted = runner is not None and not cancelled
        outcome = None
        result = {
            "id": target["id"],
            "path": target["path"],
            "sha256": target.get("sha256"),
            "repository_head": target.get("repository_head"),
            "categories": target.get("categories", []),
            "acceptance": target.get("acceptance"),
            "gate": target.get("gate"),
            "status": "blocked",
            "evidence": [],
            "diagnostics": [],
        }
        if runner is None or cancelled:
            result["diagnostics"].append(
                {
                    "code": "VERIFICATION_CANCELLED"
                    if cancelled
                    else "NATIVE_RUNNER_REQUIRED",
                    "message": "Native execution requires an explicit acceptance runner.",
                }
            )
        else:
            try:
                outcome = runner(json.loads(json.dumps(target)))
                if not isinstance(outcome, dict) or outcome.get("status") not in {
                    "passed",
                    "failed",
                    "blocked",
                    "unexecuted",
                    "not_applicable",
                }:
                    raise ValueError("Runner must return a valid status")
                evidence = outcome.get("evidence")
                if (
                    not isinstance(evidence, list)
                    or not evidence
                    or any(not isinstance(item, str) or not item for item in evidence)
                ):
                    raise ValueError("Runner must supply nonempty evidence strings")
                if outcome["status"] == "not_applicable" and not (
                    outcome.get("requested") is False
                    and all(
                        isinstance(outcome.get(key), str) and outcome[key].strip()
                        for key in ("role", "reason")
                    )
                ):
                    raise ValueError(
                        "Non-applicability requires an explicit unrequested role and reason"
                    )
                result.update(status=outcome["status"], evidence=list(evidence))
                for key in ("role", "reason", "requested"):
                    if key in outcome:
                        result[key] = outcome[key]
            except Cancelled as error:
                cancelled = True
                result["diagnostics"].append(
                    {"code": "VERIFICATION_CANCELLED", "message": str(error)}
                )
            except Exception as error:  # noqa: BLE001 - isolate independent native acceptance failures
                result["status"] = "failed"
                result["diagnostics"].append(
                    {
                        "code": "NATIVE_VERIFICATION_FAILED",
                        "message": f"{type(error).__name__}: {error}",
                    }
                )
        if attempted:
            from .receipt import validate_receipt, write_receipt
            from .receipt_native import case_receipt

            receipt = outcome.get("receipt") if isinstance(outcome, dict) else None
            if receipt is not None:
                errors = validate_receipt(receipt, public=False)
                if errors or not any(
                    stage["name"] == "initial-regression"
                    and stage["status"] == result["status"]
                    for stage in receipt.get("stages", [])
                ):
                    result["status"] = "failed"
                    result["diagnostics"].append(
                        {
                            "code": "INVALID_NATIVE_RECEIPT",
                            "message": "; ".join(errors)
                            or "Receipt does not match the case status/scope",
                        }
                    )
                    receipt = None
            if receipt is None:
                receipt = case_receipt(
                    target,
                    result["status"],
                    result["evidence"],
                    diagnostics=result["diagnostics"],
                    role=result.get("role"),
                    reason=result.get("reason"),
                )
            result["corpus_acceptance"] = "unexecuted"
            if receipt_dir is None:
                result["receipt"] = receipt
            else:
                name = hashlib.sha256(target["id"].encode()).hexdigest()[:24] + ".json"
                write_receipt(receipt, receipt_dir / name, public=False)
                result["receipt"] = (Path(receipt_dir.name) / name).as_posix()
        results.append(result)
    counts = Counter(row["status"] for row in results)
    return {
        "schema_version": 1,
        "manifest_sha256": identity,
        "host": host,
        "scope": "initial-regression",
        "targets": results,
        "summary": {
            status: counts[status]
            for status in (
                "passed",
                "failed",
                "blocked",
                "unexecuted",
                "not_applicable",
            )
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Write an assessment and return nonzero for malformed source or input."""
    parser = argparse.ArgumentParser(prog="glyport")
    subcommands = parser.add_subparsers(dest="command", required=True)
    inspect = subcommands.add_parser(
        "inspect", help="Inspect original source without running it"
    )
    inspect.add_argument("path", type=Path)
    inspect.add_argument(
        "--profile", choices=("auto", "glyphs2", "glyphs3", "glyphs4"), default="auto"
    )
    inspect.add_argument("--json", type=Path, dest="output")
    verify = subcommands.add_parser(
        "verify", help="Report the 32-target native acceptance matrix"
    )
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--host", choices=("fontlab",), default="fontlab")
    verify.add_argument("--output", type=Path)
    execution = verify.add_mutually_exclusive_group()
    execution.add_argument(
        "--native",
        action="store_true",
        help="Run owned initial-regression fixtures through Remopy; write R018 receipts",
    )
    execution.add_argument(
        "--runner", help="Explicit native acceptance callable module:function"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            runner = None
            if args.runner:
                module, separator, name = args.runner.partition(":")
                if not separator:
                    raise ValueError("--runner must be module:function")
                runner = getattr(importlib.import_module(module), name)
                if not callable(runner):
                    raise ValueError("--runner must resolve to a callable")
            if args.native:
                from .receipt_native import NativeRunner

                verify_manifest(
                    args.manifest
                )  # reject malformed metadata before connecting
                output = args.output or Path("glyport-initial-regression")
                if output.suffix != ".json":
                    output = output / "report.json"
                    receipt_dir = output.parent / "receipts"
                else:
                    receipt_dir = output.with_suffix(".receipts")
                if output.exists() or output.is_symlink():
                    raise FileExistsError(output)
                receipt_dir.mkdir(parents=True, exist_ok=False)
                with NativeRunner() as native:
                    report = verify_manifest(
                        args.manifest,
                        host=args.host,
                        runner=native,
                        receipt_dir=receipt_dir,
                    )
            else:
                if args.output is None:
                    parser.error("--output is required without --native")
                output = args.output
                report = verify_manifest(args.manifest, host=args.host, runner=runner)
            with output.open("x", encoding="utf-8") as stream:
                json.dump(
                    report,
                    stream,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                stream.write("\n")
            return (
                1
                if report["summary"]["failed"]
                else 2
                if report["summary"]["blocked"] or report["summary"]["unexecuted"]
                else 0
            )
        source = args.path.expanduser().resolve()
        if args.output:
            output = args.output.expanduser().resolve()
            if output == source or (source.is_dir() and output.is_relative_to(source)):
                parser.error("Assessment output must be outside the original source.")
        assessment = inspect_source(args.path, profile=args.profile)
        text = json.dumps(assessment.to_dict(), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(text)
        else:
            print(text, end="")
    except (OSError, ValueError, ImportError, AttributeError, GlyportError) as error:
        parser.error(str(error))
    return int(
        any(diagnostic.severity == "error" for diagnostic in assessment.diagnostics)
    )

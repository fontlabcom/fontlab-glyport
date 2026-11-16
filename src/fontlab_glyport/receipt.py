# this_file: src/fontlab_glyport/receipt.py
"""Version-one execution receipts record evidence without importing a host."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from ._receipt_records import (
    Adaptation,
    Artifact,
    Capability,
    ReceiptAdapter,
    ReceiptDiagnostic,
    ReceiptEnvironment,
    ReceiptSource,
    RoleReason,
    Severity,
    SourceLocation,
    SourceMap,
    Stage,
    Status,
    _Record,
)

__all__ = [
    "Adaptation",
    "Artifact",
    "Capability",
    "Receipt",
    "ReceiptAdapter",
    "ReceiptDiagnostic",
    "ReceiptEnvironment",
    "ReceiptSource",
    "RoleReason",
    "Severity",
    "SourceLocation",
    "SourceMap",
    "Stage",
    "Status",
    "validate_receipt",
    "write_receipt",
]


@dataclass(frozen=True)
class Receipt(_Record):
    """Collect execution facts; structural validity alone never proves behavior."""

    run_id: str
    source: ReceiptSource
    environment: ReceiptEnvironment
    adapter: ReceiptAdapter
    adaptations: tuple[Adaptation, ...]
    capabilities: tuple[Capability, ...]
    stages: tuple[Stage, ...]
    artifacts: tuple[Artifact, ...]
    diagnostics: tuple[ReceiptDiagnostic, ...]
    schema_version: Literal[1] = 1


def validate_receipt(data: dict, *, public: bool = True) -> list[str]:
    """Return structural errors, rejecting private paths by default.

    Public producers must supply pseudonymous identifiers and source-relative
    paths. Arbitrary private names cannot be inferred from their spelling.
    No artifacts, source maps or native outcomes are inspected by validation.
    """
    from ._receipt_validation import validate

    return validate(data, Receipt, public=public)


def write_receipt(
    receipt: Receipt | dict, path: str | os.PathLike[str], *, public: bool = True
) -> None:
    """Publish validated UTF-8 JSON atomically, refusing every existing path.

    Replace finalizes a file in a sibling staging directory; an exclusive hard
    link publishes the complete file without a check/replace overwrite race.
    Filesystems without hard links fail explicitly. Cleanup never wraps errors
    or intercepts SystemExit/KeyboardInterrupt.
    """
    data = receipt if isinstance(receipt, dict) else receipt.to_dict()
    errors = validate_receipt(data, public=public)
    if errors:
        raise ValueError("Invalid receipt: " + "; ".join(errors))
    output = Path(path)
    with TemporaryDirectory(prefix=".glyport-receipt-", dir=output.parent) as staging:
        temporary = Path(staging) / "pending.json"
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        complete = Path(staging) / "complete.json"
        os.replace(temporary, complete)
        os.link(complete, output)

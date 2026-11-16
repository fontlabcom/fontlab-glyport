# this_file: src/fontlab_glyport/adaptation.py
"""Pure source adaptation with owned, content-addressed cache artifacts."""

import hashlib
import json
import os
import shutil
import tempfile
import tokenize
from dataclasses import dataclass
from pathlib import Path
from types import CodeType

from fissix import __version__ as FISSIX_VERSION
from fissix.pgen2.parse import ParseError
from fissix.pgen2.tokenize import TokenError as FissixTokenError

from ._adaptation_pipeline import _pipeline
from .errors import AdaptationError
from .profiles import select_profile
from .receipt import Adaptation, ReceiptDiagnostic, SourceLocation, SourceMap

PIPELINE_VERSION = "6-legacy-methods-fissix-" + FISSIX_VERSION
PROFILES = {"auto", "glyphs2", "glyphs3", "glyphs4"}


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class AdaptedSource:
    """A cached artifact, ordered receipt records and original-source provenance."""

    original_path: Path
    path: Path
    original_sha256: str
    profile: str
    adaptations: tuple[Adaptation, ...]
    diagnostics: tuple[ReceiptDiagnostic, ...]
    source_map: SourceMap
    cache_hit: bool

    def compile(self) -> CodeType:
        """Compile without executing, retaining the original traceback filename."""
        return compile(self.path.read_bytes(), str(self.original_path), "exec")

    def translate(self, line: int, column: int = 1) -> SourceLocation:
        """Translate a generated character location using the persisted span map."""
        mapping = json.loads(Path(self.source_map.path).read_text(encoding="utf-8"))
        for span in mapping["spans"]:
            if span["generated_start"] <= [line, column] < span["generated_end"]:
                a, b = span["original_start"]
                return SourceLocation(str(self.original_path), a, b)
        raise ValueError("generated location is outside the source map")


def _load(
    root: Path, original: Path, key_hash: str, profile: str, hit: bool
) -> AdaptedSource:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    expected = {"source.py", "map.json"} | {
        f"stage-{i}.json" for i in range(len(manifest["adaptations"]))
    }
    if set(manifest["hashes"]) != expected:
        raise ValueError("cache manifest has missing or unexpected artifacts")
    for name, digest in manifest["hashes"].items():
        if _hash((root / name).read_bytes()) != digest:
            raise ValueError("cache artifact integrity mismatch: " + name)

    def map_record(name: str) -> SourceMap:
        return SourceMap(str(root / name), manifest["hashes"][name])

    records = tuple(
        Adaptation(**record, source_map=map_record(f"stage-{i}.json"))
        for i, record in enumerate(manifest["adaptations"])
    )
    diagnostics = tuple(
        ReceiptDiagnostic(
            d["code"],
            d["severity"],
            d["message"],
            SourceLocation(str(original), d["line"], d["column"]),
        )
        for d in manifest["diagnostics"]
    )
    return AdaptedSource(
        original,
        root / "source.py",
        key_hash,
        profile,
        records,
        diagnostics,
        map_record("map.json"),
        hit,
    )


def adapt_source(
    path: str | Path, *, profile: str, cache_dir: str | Path
) -> AdaptedSource:
    """Read original bytes; publish/reuse versioned artifacts without executing code."""
    original = Path(path).absolute()
    staging = None
    try:
        if profile not in PROFILES:
            raise ValueError("unknown adaptation profile: " + str(profile))
        raw = original.read_bytes()
        requested_profile = profile
        selection = select_profile(sources={original.name: raw}, override=profile)
        if profile == "auto":
            profile = selection.profile
        digest = _hash(raw)
        key = _hash(
            json.dumps([digest, profile, requested_profile, PIPELINE_VERSION]).encode()
        )
        owner = Path(cache_dir).absolute() / "fontlab-glyport"
        if original.resolve().is_relative_to(owner.resolve()):
            raise ValueError(
                "original source must be outside the owned cache directory"
            )
        root = owner / key
        if (root / "manifest.json").is_file():
            return _load(root, original, digest, profile, True)
        # A published entry always has its manifest; a key directory without one
        # was emptied by temp cleaning (or never completed), so rebuild it.
        shutil.rmtree(root, ignore_errors=True)
        data, records, diagnostics, maps = _pipeline(raw, owner, legacy_methods=profile == "glyphs2")
        if selection.profile == "auto":
            diagnostics.extend(
                {
                    "code": item.code,
                    "severity": item.severity,
                    "message": item.message,
                    "line": 1,
                    "column": 1,
                }
                for item in selection.diagnostics
            )
        owner.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=owner))
        (staging / "source.py").write_bytes(data)
        for i, mapping in enumerate(maps[:-1]):
            (staging / f"stage-{i}.json").write_text(
                json.dumps(mapping), encoding="utf-8"
            )
        (staging / "map.json").write_text(json.dumps(maps[-1]), encoding="utf-8")
        hashes = {p.name: _hash(p.read_bytes()) for p in staging.iterdir()}
        (staging / "manifest.json").write_text(
            json.dumps(
                {"adaptations": records, "diagnostics": diagnostics, "hashes": hashes}
            ),
            encoding="utf-8",
        )
        try:
            os.rename(staging, root)
        except OSError:
            if not root.is_dir():
                raise
        return _load(root, original, digest, profile, False)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        SyntaxError,
        UnicodeError,
        tokenize.TokenError,
        ParseError,
        FissixTokenError,
    ) as error:
        line, column = getattr(error, "lineno", None), getattr(error, "offset", None)
        if isinstance(error, ParseError) and error.context:
            line, zero_column = error.context[1]
            column = zero_column + 1
        raise AdaptationError(
            (
                "Cannot parse Python 2 source under its declared __future__ features: "
                + str(error)
            )
            if isinstance(error, ParseError)
            else str(error),
            capability="source:python2.parse"
            if isinstance(error, ParseError)
            else None,
            location=SourceLocation(str(original), line or 1, column or 1),
        ) from error
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)

# this_file: src/fontlab_glyport/adaptation_modern.py
"""Identity source artifacts for Glyphs 3/4; imports adapt at context boundaries.

Modern Python needs no fissix import. Source accepted by Python 3.11 retains
bytes, coordinates and semantics; unsupported newer syntax fails explicitly.
"""

import ast
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ._source_map import serialize
from .receipt import SourceLocation, SourceMap

PIPELINE_VERSION = "modern-1-python311-scoped-imports"


@dataclass(frozen=True)
class ModernSource:
    original_path: Path
    path: Path
    original_sha256: str
    profile: str
    source_map: SourceMap
    cache_hit: bool
    adaptations: tuple = ()
    diagnostics: tuple = ()

    def compile(self):
        return compile(self.path.read_bytes(), str(self.original_path), "exec")

    def translate(self, line: int, column: int = 1) -> SourceLocation:
        return SourceLocation(str(self.original_path), line, column)


def adapt_modern(path: Path, *, profile: str, cache_dir: Path) -> ModernSource:
    """Publish byte-identical source and identity map; verify every cache hit."""
    import io
    import tokenize

    raw = path.read_bytes()
    ast.parse(raw, filename=str(path), feature_version=(3, 11))
    digest = hashlib.sha256(raw).hexdigest()
    key = hashlib.sha256(
        json.dumps([digest, profile, PIPELINE_VERSION]).encode()
    ).hexdigest()
    owner = Path(cache_dir).absolute() / "fontlab-glyport"
    if path.resolve().is_relative_to(owner.resolve()):
        raise ValueError("original source must be outside the owned cache directory")
    root = owner / key
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    text = raw.decode(encoding)
    mapping = json.dumps(
        serialize(text, text, [(i, i + 1) for i in range(len(text))])
    ).encode()
    map_hash = hashlib.sha256(mapping).hexdigest()
    hit = (root / "source.py").is_file() and (root / "map.json").is_file()
    if not hit:
        # A key directory missing either artifact was emptied by temp cleaning.
        shutil.rmtree(root, ignore_errors=True)
        owner.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".modern-", dir=owner) as directory:
            staging = Path(directory) / "entry"
            staging.mkdir()
            (staging / "source.py").write_bytes(raw)
            (staging / "map.json").write_bytes(mapping)
            try:
                os.rename(staging, root)
            except OSError:
                if not root.is_dir():
                    raise
    if (root / "source.py").read_bytes() != raw or (
        root / "map.json"
    ).read_bytes() != mapping:
        raise ValueError("modern adaptation cache integrity mismatch")
    return ModernSource(
        path,
        root / "source.py",
        digest,
        profile,
        SourceMap(str(root / "map.json"), map_hash),
        hit,
    )

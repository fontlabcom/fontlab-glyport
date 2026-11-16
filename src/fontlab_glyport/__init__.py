# this_file: src/fontlab_glyport/__init__.py
"""Glyphs compatibility facts and errors; importing never loads a native host."""

from os.path import dirname, join

from .assessment import Assessment, Dependency, Diagnostic, SourceFile
from .errors import (
    AdaptationError,
    Cancelled,
    DependencyUnavailable,
    GlyportError,
    HostUnavailable,
    NativeOperationError,
    PartialFailure,
    StaleNativeObject,
    UnsupportedAttribute,
    UnsupportedCapability,
)
from .execution import ExecutionContext, Output, placeholder
from .inspection import inspect_source
from .receipt import (
    Adaptation,
    Artifact,
    Capability,
    Receipt,
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
    validate_receipt,
    write_receipt,
)

# A separate search root lets GlyphsApp coexist with glyphsapp on macOS
# volumes whose filenames ignore case. Existing module paths stay unchanged.
__path__.append(join(dirname(__file__), "_public"))

__all__ = [
    "Adaptation",
    "AdaptationError",
    "AdaptedSource",
    "Artifact",
    "Assessment",
    "Cancelled",
    "Capability",
    "Dependency",
    "DependencyUnavailable",
    "Diagnostic",
    "ExecutionContext",
    "GlyphsApp",
    "GlyportError",
    "HostUnavailable",
    "NativeOperationError",
    "Output",
    "PartialFailure",
    "Receipt",
    "ReceiptAdapter",
    "ReceiptDiagnostic",
    "ReceiptEnvironment",
    "ReceiptSource",
    "RoleReason",
    "Severity",
    "SourceFile",
    "SourceLocation",
    "SourceMap",
    "Stage",
    "StaleNativeObject",
    "Status",
    "UnsupportedAttribute",
    "UnsupportedCapability",
    "activate",
    "adapt_source",
    "deactivate",
    "inspect_source",
    "install_plugin",
    "placeholder",
    "run_script",
    "validate_receipt",
    "write_receipt",
]


def __getattr__(name: str):
    """Load source adaptation (and its fissix dependency) only when requested."""
    if name == "GlyphsApp":
        from importlib import import_module

        return import_module(".GlyphsApp", __name__)
    if name in {"activate", "deactivate"}:
        from . import bootstrap

        return getattr(bootstrap, name)
    if name in {"run_script", "install_plugin"}:
        from . import entrypoints

        return getattr(entrypoints, name)
    if name in {"AdaptedSource", "adapt_source"}:
        from . import adaptation

        return getattr(adaptation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

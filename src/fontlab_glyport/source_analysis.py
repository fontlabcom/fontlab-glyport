# this_file: src/fontlab_glyport/source_analysis.py
"""Conservative AST discovery; no imported third-party code is executed."""

import ast
import io
import tokenize
import warnings

from .assessment import Dependency, Diagnostic

PROTOCOLS = frozenset(
    {
        "ReporterPlugin",
        "GeneralPlugin",
        "FilterWithDialog",
        "PalettePlugin",
        "FilterWithoutDialog",
        "SelectTool",
        "FileFormatPlugin",
    }
)
IMPORT_CAPABILITIES = {
    "GlyphsApp": "glyphs:model",
    "vanilla": "ui:vanilla",
    "AppKit": "ui:appkit",
    "Foundation": "ui:foundation",
    "Cocoa": "ui:cocoa",
    "objc": "ui:objc",
    "PySide2": "ui:pyside2",
    "wx": "ui:wx",  # wxPython: a separate GUI backend, never Qt or vanilla
    "drawBot": "drawing:drawbot",
    "drawbot": "drawing:drawbot",
    "fontTools": "dependency:fonttools",
    "robofab": "dependency:robofab",
    "fontParts": "dependency:fontparts",
    "subprocess": "process:external",
    "requests": "service:external",
    "urllib": "service:external",
    "http": "service:external",
    "socket": "service:external",
}


def qualified_name(node: ast.AST) -> str:
    """Resolve lexical dotted names; computed bases remain unknown."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return qualified_name(node.value) + "." + node.attr
    return ""


def analyze_python(data: bytes, path: str) -> tuple:
    """Return imports, requirements, diagnostics and direct protocol classes."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            tree = ast.parse(data.decode(encoding), filename=path)
    except (SyntaxError, UnicodeError, LookupError) as error:
        diagnostic = Diagnostic(
            "PYTHON_PARSE_ERROR",
            "error",
            str(error),
            path,
            getattr(error, "lineno", None),
            getattr(error, "offset", None),
        )
        return [], set(), [diagnostic], set()
    diagnostics = [
        Diagnostic("PYTHON_PARSE_WARNING", "warning", str(w.message), path, w.lineno)
        for w in captured
    ]
    imports, aliases, capabilities, classes = [], {}, set(), set()
    nodes = list(ast.walk(tree))
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(Dependency(alias.name, path, node.lineno))
                aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        if isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            imports.append(Dependency(module, path, node.lineno))
            for alias in node.names:
                aliases[alias.asname or alias.name] = module + "." + alias.name
                if module == "GlyphsApp.plugins" and alias.name == "*":
                    aliases.update(
                        {protocol: module + "." + protocol for protocol in PROTOCOLS}
                    )
    for dependency in imports:
        capability = IMPORT_CAPABILITIES.get(dependency.module.split(".")[0])
        if capability:
            capabilities.add(capability)
    for node in nodes:
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = qualified_name(base)
                head, _, tail = name.partition(".")
                resolved = aliases.get(head, head) + ("." + tail if tail else "")
                protocol = resolved.rsplit(".", 1)[-1]
                if protocol in PROTOCOLS and resolved.startswith("GlyphsApp.plugins."):
                    capabilities.add("glyphs:" + protocol)
                    classes.add(node.name)
        if isinstance(node, ast.Call) and qualified_name(node.func).rsplit(".", 1)[
            -1
        ] in {"__import__", "import_module"}:
            diagnostics.append(
                Diagnostic(
                    "DYNAMIC_IMPORT",
                    "warning",
                    "Runtime import requires execution-context dependency resolution.",
                    path,
                    node.lineno,
                )
            )
    return imports, capabilities, diagnostics, classes

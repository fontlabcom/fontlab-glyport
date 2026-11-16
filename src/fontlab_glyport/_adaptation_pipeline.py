# this_file: src/fontlab_glyport/_adaptation_pipeline.py
"""Ordered, host-independent source transformations and provenance."""

import ast
import hashlib
import io
import tokenize
from pathlib import Path

from ._source_map import compose, position, serialize


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _original_error(
    error: SyntaxError, generated: str, origins: list[tuple[int, int]], original: str
) -> SyntaxError:
    """Translate syntax failures after rewriting into original character positions."""
    lines = generated.splitlines(keepends=True)
    index = sum(map(len, lines[: (error.lineno or 1) - 1])) + (error.offset or 1) - 1
    offset = origins[min(index, len(origins) - 1)][0] if origins else 0
    line, column = position(original, offset)
    return SyntaxError(error.msg, ("<original>", line, column, ""))


def _runtime_import(source: str) -> str:
    tree = ast.parse(source, feature_version=(3, 11))
    # Never silently change a script's own binding of the reserved helper.
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names = [node.id]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.asname or alias.name.split(".")[0] for alias in node.names]
        if "_glyport_div" in names:
            raise SyntaxError(
                "reserved helper name _glyport_div is bound by source",
                ("<source>", node.lineno, node.col_offset + 1, ""),
            )
    lines = source.splitlines(keepends=True)
    for index, node in enumerate(tree.body):
        if (
            index == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ) or (isinstance(node, ast.ImportFrom) and node.module == "__future__"):
            continue
        else:
            # AST columns are UTF-8 byte offsets; maps use Unicode characters.
            column = len(
                lines[node.lineno - 1]
                .encode("utf-8")[: node.col_offset]
                .decode("utf-8")
            )
            offset = sum(map(len, lines[: node.lineno - 1])) + column
            return (
                source[:offset]
                + "from fontlab_glyport.runtime import _glyport_div; "
                + source[offset:]
            )
    return source + "\nfrom fontlab_glyport.runtime import _glyport_div\n"


def _pipeline(
    raw: bytes, owner: Path, *, legacy_methods: bool = False
) -> tuple[bytes, list[dict], list[dict], list[dict]]:
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    original = raw.decode(encoding)
    origins = [(i, i + 1) for i in range(len(original))]
    try:
        ast.parse(raw, feature_version=(3, 11))
    except SyntaxError:
        pass
    else:
        if not legacy_methods:
            return raw, [], [], [serialize(original, original, origins)]
        from ._legacy_attributes import rewrite

        output = rewrite(original)
        if output == original:
            return raw, [], [], [serialize(original, original, origins)]
        data = output.encode(encoding)
        origins = compose(original, output, origins)
        mapping = serialize(original, output, origins)
        return data, [{"id": "py2.legacy_methods", "reason": "Preserve existing attributes; emulate missing dictionary legacy methods", "input_sha256": _hash(raw), "output_sha256": _hash(data)}], [], [mapping, mapping]
    # fissix otherwise writes grammar pickles to the user's global cache on import.
    import fissix

    fissix.CACHE_DIR = owner / "grammar"
    from fissix.refactor import RefactoringTool

    from . import _py2

    source = original
    data = raw
    records, maps, diagnostics = [], [], []

    def stage(identifier: str, reason: str, output: str) -> None:
        nonlocal source, data, origins
        if output == source:
            return
        origins = compose(source, output, origins)
        next_data = output.encode(encoding)
        records.append(
            {
                "id": "py2." + identifier,
                "reason": reason,
                "input_sha256": _hash(data),
                "output_sha256": _hash(next_data),
            }
        )
        maps.append(serialize(original, output, origins))
        source, data = output, next_data

    # Parse once before any change so malformed input reports original coordinates.
    tree = _py2.parse(source)
    for leaf in tree.leaves():
        if leaf.type == _py2.token.STRING and leaf.value[:2].lower() == "ur":
            diagnostics.append(
                {
                    "code": "PY2_RAW_UNICODE_REVIEW",
                    "severity": "warning",
                    "message": "Raw-unicode literals become raw text; Python 2 Unicode escape behavior requires review.",
                    "line": leaf.lineno,
                    "column": leaf.column + 1,
                }
            )
        if leaf.value in ("print", "exec", "except"):
            diagnostics.append(
                {
                    "code": "PY2_SEMANTIC_REVIEW",
                    "severity": "warning",
                    "message": "Review print softspace, implicit exec locals, and exception-target lifetime when relevant.",
                    "line": leaf.lineno,
                    "column": leaf.column + 1,
                }
            )
    for identifier, fixer in _py2.FIXERS:
        for node in tree.pre_order():
            node.was_checked = False
        RefactoringTool(["fissix.fixes.fix_" + fixer]).refactor_tree(tree, "<source>")
        stage(
            identifier,
            "Convert Python 2 " + identifier.replace("_", " ") + " with fissix",
            str(tree),
        )
    for identifier in (
        "long_literal",
        "octal_literal",
        "unicode_literals",
        "unicode_builtin",
    ):
        stage(
            identifier,
            "Preserve Python 2 " + identifier.replace("_", " ") + " in Python 3",
            _py2.lexical(tree, identifier),
        )
    output = _py2.division(tree)
    if output != source:
        try:
            output = _runtime_import(output)
        except SyntaxError as error:
            raise _original_error(
                error, output, compose(source, output, origins), original
            ) from error
    stage(
        "integer_division",
        "Dispatch classic division by operand types; respect future division",
        output,
    )
    try:
        ast.parse(data, feature_version=(3, 11))
    except SyntaxError as error:
        raise _original_error(error, source, origins, original) from error
    # Locate strings in the Python 2 parse tree: the stdlib tokenizer of the
    # running Python rejects Python 2 literals such as ur'' on 3.14.
    for leaf in tree.leaves():
        if leaf.type == _py2.token.STRING:
            diagnostics.append(
                {
                    "code": "PY2_STRING_AMBIGUITY",
                    "severity": "warning",
                    "message": "Python 2 strings remain text; byte-oriented operations require review.",
                    "line": leaf.lineno,
                    "column": leaf.column + 1,
                }
            )
    # final map also exists for a syntax-changing source with no recorded fixer.
    maps.append(serialize(original, source, origins))
    return data, records, diagnostics, maps

# this_file: src/fontlab_glyport/_legacy_attributes.py
"""Rewrite legacy attribute loads, preserving original text outside expressions.

Only the selected Glyphs2 route uses this pass. Store/delete targets and modern
profiles remain untouched. Receiver text is evaluated once; the runtime keeps
real custom/native attributes before providing a missing dictionary operation.
"""

import ast
import io
import tokenize

HELPER = "_glyport_legacy_attrs"
METHODS = {"iteritems", "iterkeys", "itervalues", "has_key"}


def _reserved(tree: ast.AST, source: str) -> None:
    """Refuse source references/bindings that the generated import would mask."""
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names = node.names
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [item.asname or item.name.split(".")[0] for item in node.names]
        if HELPER in names:
            line = source.splitlines()[node.lineno - 1]
            column = len(line.encode("utf-8")[: node.col_offset].decode("utf-8")) + 1
            raise SyntaxError(
                f"reserved helper name {HELPER} is used by source",
                ("<source>", node.lineno, column, ""),
            )


def _offset(source: str, line: int, column: int) -> int:
    """Convert CPython AST UTF8 byte columns to source character positions."""
    lines = source.splitlines(keepends=True)
    return sum(map(len, lines[: line - 1])) + len(
        lines[line - 1].encode("utf-8")[:column].decode("utf-8")
    )


def _dot(expression: str) -> int:
    """Locate the final attribute dot, ignoring dots inside comments/literals."""
    wrapped = "(" + expression + ")"
    ignored = {tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.ENDMARKER}
    tokens = [
        item
        for item in tokenize.generate_tokens(io.StringIO(wrapped).readline)
        if item.type not in ignored
    ]
    dot = tokens[-3]
    assert dot.string == ".", "An Attribute AST must end in a dot and name"
    line, column = dot.start
    return sum(map(len, wrapped.splitlines(keepends=True)[: line - 1])) + column - 1


def rewrite(source: str) -> str:
    """Patch nested attribute expressions and add one import after doc/futures."""
    tree = ast.parse(source, feature_version=(3, 11))
    targets = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and node.attr in METHODS
    ]
    if not targets:
        return source
    _reserved(tree, source)
    spans = []
    for node in targets:
        start = _offset(source, node.lineno, node.col_offset)
        end = _offset(source, node.end_lineno, node.end_col_offset)
        spans.append((start, end, start + _dot(source[start:end]), node.attr))
    spans.sort(key=lambda item: (item[0], -item[1]))

    def render(start: int, end: int) -> str:
        position, result = start, []
        for left, right, dot, name in spans:
            if left < position or right > end:
                continue
            result.extend(
                (
                    source[position:left],
                    f"{HELPER}.{name}(("
                    + render(left, dot)
                    + source[dot + 1 : right - len(name)]
                    + "))",
                )
            )
            position = right
        return "".join(result) + source[position:end]

    insertion = 0
    for index, node in enumerate(tree.body):
        if (
            index == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ) or (isinstance(node, ast.ImportFrom) and node.module == "__future__"):
            continue
        insertion = _offset(source, node.lineno, node.col_offset)
        break
    # Insertion precedes every changed expression, so original offsets stay valid.
    generated = render(0, len(source))
    separator = "\n" if node.col_offset == 0 else "; "
    output = (
        generated[:insertion]
        + f"from fontlab_glyport.runtime import {HELPER}"
        + separator
        + generated[insertion:]
    )
    ast.parse(output, feature_version=(3, 11))
    return output

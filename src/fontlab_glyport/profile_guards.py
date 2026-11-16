# this_file: src/fontlab_glyport/profile_guards.py
"""Recognize simple top-level version rejection guards without executing source."""

import ast
import operator

from .profile_versions import PROFILE_VERSIONS

_COMPARISONS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


def _value(node, major, constants):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float, bool):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.Attribute) and node.attr == "versionNumber":
        return PROFILE_VERSIONS[f"glyphs{major}"].number
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        value = _value(node.operand, major, constants)
        return None if value is None else not value
    if isinstance(node, ast.Compare):
        values = [_value(n, major, constants) for n in (node.left, *node.comparators)]
        if None in values or any(type(op) not in _COMPARISONS for op in node.ops):
            return None
        return all(
            _COMPARISONS[type(op)](a, b)
            for op, a, b in zip(node.ops, values, values[1:])
        )
    return None


def guard_versions(tree):
    """Return majors not rejected by simple module-level ``if ...: raise``.

    Numeric module constants and reversed/chained comparisons are understood.
    Unknown expressions impose no constraint; this is evidence, not a Python
    control-flow interpreter. In particular a version-dependent API branch
    without a direct raise does not reject either generation.
    """
    allowed, constants = {2, 3, 4}, {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    value = (
                        node.value.value
                        if isinstance(node.value, ast.Constant)
                        else None
                    )
                    constants[target.id] = (
                        value if type(value) in (int, float) else None
                    )
        if not isinstance(node, ast.If) or not any(
            isinstance(n, ast.Attribute) and n.attr == "versionNumber"
            for n in ast.walk(node.test)
        ):
            continue
        rejects_true = any(isinstance(n, ast.Raise) for n in node.body)
        rejects_false = any(isinstance(n, ast.Raise) for n in node.orelse)
        for major in tuple(allowed):
            condition = _value(node.test, major, constants)
            if condition is not None and (rejects_true if condition else rejects_false):
                allowed.remove(major)
    return allowed

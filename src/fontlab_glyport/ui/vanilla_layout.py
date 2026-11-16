# this_file: src/fontlab_glyport/ui/vanilla_layout.py
"""Vanilla auto positioning for required linear equalities.

Supports VFL chains, numeric/metric gaps, equal view sizes, and dictionary
equalities. Native intrinsic sizes are weak preferences. Inequalities,
priorities and baseline constraints fail explicitly rather than being ignored.
All equations are checked before applying any geometry; no Qt binding imports.
"""

import math
import re

import fontlabapp.qt.layouts.linear as _linear_layout

from .application_windows import qt_value
from .cocoa import unsupported

_VIEW = re.compile(r"\[(\w+)(?:\(([^()]*)\))?\]|\|")
_ATTRS = {
    "left": (1, 0, 0, 0),
    "leading": (1, 0, 0, 0),
    "top": (0, 1, 0, 0),
    "width": (0, 0, 1, 0),
    "height": (0, 0, 0, 1),
    "right": (1, 0, 1, 0),
    "trailing": (1, 0, 1, 0),
    "bottom": (0, 1, 0, 1),
    "centerX": (1, 0, 0.5, 0),
    "centerY": (0, 1, 0, 0.5),
}
_EPSILON = 1e-8


def _number(value, metrics):
    if isinstance(value, str):
        value = metrics.get(value, value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise unsupported("vanilla.addAutoPosSizeRules.metric") from None
    if not math.isfinite(number):
        raise ValueError("Layout numbers must be finite")
    return number


def _view_name(container, value):
    if value is container or value is None:
        return None
    for name, view in container._children.items():
        if value is view or (isinstance(value, str) and value == name):
            return name
    raise unsupported("vanilla.addAutoPosSizeRules.view")


def _attribute(name, attr):
    if attr not in _ATTRS:
        raise unsupported(f"vanilla.addAutoPosSizeRules.attribute.{attr}")
    return {(name, i): v for i, v in enumerate(_ATTRS[attr]) if v}


def _equation(left, right, constant=0, multiplier=1):
    row = dict(left)
    for key, value in right.items():
        row[key] = row.get(key, 0) - value * multiplier
    return row, constant


def _dictionary(container, rule, metrics):
    allowed = {
        "view1",
        "attribute1",
        "relation",
        "view2",
        "attribute2",
        "multiplier",
        "constant",
    }
    if set(rule) - allowed or rule.get("relation", "==") != "==":
        raise unsupported("vanilla.addAutoPosSizeRules.relation")
    left = _attribute(_view_name(container, rule["view1"]), rule["attribute1"])
    right = (
        {}
        if rule.get("view2") is None
        else _attribute(_view_name(container, rule["view2"]), rule["attribute2"])
    )
    return _equation(
        left,
        right,
        _number(rule.get("constant", 0), metrics),
        _number(rule.get("multiplier", 1), metrics),
    )


def _gap(text, metrics):
    if not text:
        return 0
    if text == "-":
        return 8.0
    if not (text.startswith("-") and text.endswith("-")):
        raise unsupported("vanilla.addAutoPosSizeRules.VFL")
    value = text[1:-1]
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    return _number(value.removeprefix("=="), metrics)


def _vfl(container, rule, metrics):
    rule = rule.replace(" ", "")
    axis, text = (rule[:1], rule[2:]) if rule.startswith(("H:", "V:")) else ("H", rule)
    position, dimension = ("left", "width") if axis == "H" else ("top", "height")
    end = "right" if axis == "H" else "bottom"
    matches = list(_VIEW.finditer(text))
    if (
        not matches
        or not any(m[1] is not None for m in matches)
        or matches[0].start() != 0
        or matches[-1].end() != len(text)
    ):
        raise unsupported("vanilla.addAutoPosSizeRules.VFL")
    rows, previous, cursor = [], None, 0
    for index, match in enumerate(matches):
        name, predicate = match.groups()
        if name is not None:
            _view_name(container, name)
            if predicate is not None:
                value = predicate.removeprefix("==")
                if any(token in value for token in ("<", ">", "@", ",")):
                    raise unsupported("vanilla.addAutoPosSizeRules.predicate")
                other = (
                    _attribute(value, dimension) if value in container._children else {}
                )
                constant = 0 if other else _number(value, metrics)
                rows.append(_equation(_attribute(name, dimension), other, constant))
        elif index not in (0, len(matches) - 1):
            raise unsupported("vanilla.addAutoPosSizeRules.VFL")
        if index:
            gap = _gap(text[cursor : match.start()], metrics)
            left = _attribute(name, end if name is None else position)
            right = _attribute(previous, position if previous is None else end)
            rows.append(_equation(left, right, gap))
        previous, cursor = name, match.end()
    return rows


def prepare_rules(container, rules, metrics):
    rows = []
    for rule in rules:
        if isinstance(rule, str):
            rows.extend(_vfl(container, rule, metrics))
        elif isinstance(rule, dict):
            rows.append(_dictionary(container, rule, metrics))
        else:
            raise TypeError("Layout rules must be VFL strings or dictionaries")
    return rows


def _solve(required, hints, count):
    """Keep Vanilla's public compatibility error around the shared UI solver."""
    try:
        return _linear_layout.solve(required, hints, count, epsilon=_EPSILON)
    except _linear_layout.InconsistentEquations:
        raise unsupported("vanilla.addAutoPosSizeRules.unsatisfiable") from None


def apply_rules(container, rules):
    referenced = {
        name for equation, _ in rules for name, _ in equation if name is not None
    }
    names = [name for name in container._children if name in referenced]
    indices = {(name, i): n * 4 + i for n, name in enumerate(names) for i in range(4)}
    count = len(indices)
    parent = (0, 0, *container._size)
    required = []
    for equation, value in rules:
        row = [0.0] * count
        for (name, i), coefficient in equation.items():
            if name is None:
                value -= coefficient * parent[i]
            else:
                row[indices[name, i]] += coefficient
        required.append((row, value))
    hints = []
    for name in names:
        hint = qt_value(container._children[name]._view, "sizeHint")
        for i, value in (
            (2, max(0, hint.width())),
            (3, max(0, hint.height())),
            (0, 0),
            (1, 0),
        ):
            row = [0.0] * count
            row[indices[name, i]] = 1
            hints.append((row, value))
    # Native controls have nonnegative extents. Drop weak intrinsic preferences
    # as necessary when a small container cannot fit all natural sizes.
    for _ in range(count + 1):
        values = _solve(required, hints, count)
        negative = [
            i for i, value in enumerate(values) if i % 4 >= 2 and value < -_EPSILON
        ]
        if not negative:
            break
        for i in negative:
            row = [0.0] * count
            row[i] = 1
            required.append((row, 0))
    for name in names:
        view = container._children[name]
        x, y, width, height = (values[indices[name, i]] for i in range(4))
        view._view.setGeometry(round(x), round(y), round(width), round(height))
        view._size = (width, height)
        if callable(getattr(view, "_relayout", None)):
            view._relayout()
        if callable(getattr(view, "_refresh_image", None)):
            view._refresh_image()

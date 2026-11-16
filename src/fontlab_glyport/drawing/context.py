# this_file: src/fontlab_glyport/drawing/context.py
"""The current Cocoa graphics state over a QPainter (R032).

Cocoa draws through an implicit current context with a transform (CTM), a
fill and stroke colour, and a save/restore stack. Here that state lives in
Python: affine transforms are 6-tuples ``(m11, m12, m21, m22, tx, ty)``
composed with plain arithmetic, and a ``QTransform`` is built only when a
shape is painted (no arithmetic on PythonQt wrappers; unary minus on them
crashes FontLab). The base transform maps the drawing space (glyph units, or
a view's y-up coordinates) to widget pixels.

A context exists only inside a scope (``paint_scope`` for editor painters,
``view_scope`` for ``NSView.drawRect_``). State operations outside one raise
``RuntimeError``; path painting with no destination is a no-op, as in Cocoa.
A retained painter cannot paint after its callback.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any

from fontlabapp.contours.affine import (  # noqa: F401 - re-exported for Glyport callers
    IDENTITY,
    Affine,
    apply,
    concat,
    from_qtransform,
    invert,
    rotation,
)


@dataclass
class GraphicsState:
    ctm: Affine = IDENTITY
    fill: Any = None  # NSColor
    stroke: Any = None  # NSColor
    antialias: bool = True


@dataclass
class GraphicsContext:
    """One painter plus Cocoa state; ``base`` maps drawing space to pixels."""

    qt: Any
    painter: Any
    base: Affine
    flipped: bool = False  # True: y grows downward (a flipped NSView)
    state: GraphicsState = field(default_factory=GraphicsState)
    stack: list[GraphicsState] = field(default_factory=list)
    active: bool = True
    glyph_base: Affine | None = None

    def save(self) -> None:
        self.stack.append(replace(self.state))

    def restore(self) -> None:
        if self.stack:
            self.state = self.stack.pop()

    def device(self) -> Affine:
        """Drawing space -> pixels: the CTM, then the base transform."""
        return concat(self.state.ctm, self.base)

    def qtransform(self, t: Affine | None = None) -> Any:
        return self.qt.QtGui.QTransform(*(self.device() if t is None else t))


_STACK: list[GraphicsContext] = []


def optional_current() -> GraphicsContext | None:
    """A nil Cocoa context: geometry works, painting has no destination."""
    return _STACK[-1] if _STACK and _STACK[-1].active else None


def current() -> GraphicsContext:
    """The active context; outside a scope there is none (RuntimeError)."""
    if not _STACK or not _STACK[-1].active:
        raise RuntimeError(
            "no current graphics context (drawing outside a paint callback)"
        )
    return _STACK[-1]


@contextmanager
def scope(
    qt: Any, painter: Any, base: Affine, *, flipped: bool = False
) -> Iterator[GraphicsContext]:
    """Make a context current around ``painter`` (saved and restored)."""
    context = GraphicsContext(qt, painter, base, flipped)
    painter.save()
    _STACK.append(context)
    try:
        yield context
    finally:
        context.active = False
        _STACK.remove(context)
        painter.restore()


def paint_scope(qt: Any):
    """Factory for ``PluginEnv.paint_scope``: glyph units -> widget pixels."""

    def enter(paint_context) -> Any:
        base = concat(
            from_qtransform(paint_context.glyph_to_canvas),
            from_qtransform(paint_context.canvas_to_view),
        )
        return scope(qt, paint_context.painter, base)

    return enter


def view_scope(qt: Any, painter: Any, height: float, *, flipped: bool):
    """``NSView.drawRect_``: y-up bounds unless the view is flipped."""
    base = IDENTITY if flipped else (1.0, 0.0, 0.0, -1.0, 0.0, float(height))
    return scope(qt, painter, base, flipped=flipped)


@contextmanager
def reporter_view_scope(scale: float):
    """View hooks use the widget bounds in Cocoa points, independent of glyph origin."""
    parent = optional_current()
    if parent is None:
        yield
        return
    if scale <= 0:
        raise ValueError("Reporter scale must be positive")
    height = float(parent.painter.device().height())
    base = (1, 0, 0, -1, 0, height)
    with scope(parent.qt, parent.painter, base, flipped=parent.flipped) as context:
        context.glyph_base = parent.glyph_base or parent.base
        yield

# this_file: src/fontlab_glyport/drawing/editor.py
"""Glyphs-facing glyph-editor painters over App's shared registry (R032).

``fontlabapp.qt.painting.editor`` owns the overlays, polling, paint maths and
teardown. Glyport adds only the Glyphs rule: the before-native phase raises
``UnsupportedCapability`` (a loader diagnostic), not ``ValueError``. The base
class also takes ``layer_resolver`` for reporter model layers.
"""

from collections.abc import Callable
from typing import Any

from fontlabapp.qt.painting.editor import EditorPainters as _AppEditorPainters

from ..errors import UnsupportedCapability
from ..plugins.host import BEFORE_NATIVE_LAYER


class EditorPainters(_AppEditorPainters):
    """App's ``EditorPainters`` with Glyphs' before-native-layer refusal."""

    def register(
        self,
        phase: str,
        callback: Callable,
        layer_filter: str = "active",
        *,
        document_id: Any = None,
    ) -> int:
        """Refuse the before phase (R054); else register as App does."""
        if phase == BEFORE_NATIVE_LAYER:
            capability = "FontLab.painter.before_native_layer"
            raise UnsupportedCapability(
                f"Unsupported capability: {capability} (the native canvas paints "
                "opaquely after any Python pre-paint; a host hook is needed, R054)",
                capability=capability,
            )
        return super().register(
            phase, callback, layer_filter, document_id=document_id
        )

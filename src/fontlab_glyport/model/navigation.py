# this_file: src/fontlab_glyport/model/navigation.py
"""Keep Glyphs navigation policy on App's shared native tab mechanics."""

from collections.abc import Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import fontlabapp.core.native_tabs as _tabs

from ..errors import NativeOperationError, UnsupportedCapability


def preserve_shape_activation(
    package: Any, names: Iterable[str]
) -> AbstractContextManager[None]:
    """Use the original shared active-flag context without changing caller policy."""
    return _tabs.preserve_shape_activation(package, names)


def preserve_rendered_activation(workspace: Any) -> AbstractContextManager[None]:
    """Preserve the old renderer through App's existing block/shape protocol."""
    return _tabs.preserve_rendered_activation(workspace)


@contextmanager
def empty_tab_emitter(qtgui: Any, main: Any) -> Iterator[Any]:
    """Keep Glyphs empty-text bootstrap and native capability/error policy.

    App owns the hidden sender, exact native connection and disconnect/delete
    lifecycle. The caller still selects the source font and emits empty text.
    """
    with _tabs.text_tab_sender(
        qtgui,
        main,
        bootstrap_text="glyport-before-connect",
        connection_error=UnsupportedCapability(
            "FontLab's empty tab slot connection is unavailable",
            capability="GSFont.newTab",
        ),
        disconnection_error=NativeOperationError(
            "FontLab's empty tab slot disconnect failed",
            capability="GSFont.newTab",
        ),
    ) as emitter:
        yield emitter

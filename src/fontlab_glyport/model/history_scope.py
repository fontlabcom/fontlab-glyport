# this_file: src/fontlab_glyport/model/history_scope.py
"""Resolve Glyport's retained native owners before shared App history checks."""

from collections.abc import Iterable
from threading import current_thread, main_thread
from typing import Any

from ..errors import StaleNativeObject


def _entry_token(backend: Any, kind: str, obj: Any) -> str:
    """Find an already registered native identity, never guess its glyph owner."""
    candidates = [
        (token, backend._objects.get(token))
        for token, key in tuple(backend._object_keys.items())
        if key[1] == kind
    ]
    tokens = [token for token, value in candidates if value is obj]
    if not tokens:
        tokens = [
            token
            for token, value in candidates
            if value is not None
            and getattr(value, "id", None) == getattr(obj, "id", object())
        ]
    if len(tokens) == 1:
        live = backend._object(tokens[0])
        if live is obj or getattr(live, "id", None) == getattr(obj, "id", object()):
            return tokens[0]
    raise StaleNativeObject(f"{kind}:{getattr(obj, 'id', None)}")


def require_scope(
    backend: Any,
    entries: Iterable[tuple[str, Any]] = (),
    *,
    tokens: Iterable[str] = (),
    creates: bool = False,
) -> None:
    """Check retained plus prospective owners before each forward native write.

    Package history conservatively requires the matching current regular Font
    window. Component-history tuples retain native dependencies, not glyphs.
    Recovery calls this only after restoring and recording its pending changes.
    """
    from fontlabapp.core.edit_guards import (
        require_history_scope,
        require_selection_window,
    )

    native = backend._native()
    if current_thread() is not main_thread():
        require_history_scope((), native=native)  # shared GUI-thread refusal
    scope = list(tokens) + list(backend._pending_layer_updates)
    records = list(backend._changed.items()) + list(backend._prepared.items())
    records += [((kind, None), obj) for kind, obj in entries]
    for key, obj in records:
        if key[0] == "component_history":
            scope.append(key[1])
        else:
            scope.append(_entry_token(backend, key[0], obj))
    glyphs, packages = {}, {}
    for token in dict.fromkeys(scope):
        obj = backend._object(token)
        kind = backend._object_keys[token][1]
        if kind in {"font", "master"}:
            packages[obj.id] = obj
            continue
        while kind != "glyph":
            token = backend._parents[token]
            obj = backend._object(token)
            kind = backend._object_keys[token][1]
            if kind == "font":
                raise ValueError(
                    "Native history has no known glyph owner; refresh the font."
                )
        # Validate the parent package through the existing lifetime map too.
        package = backend._object(backend._parents[token])
        glyphs[package.id, obj.id] = obj
    require_history_scope(tuple(glyphs.values()), creates=creates, native=native)
    for package in packages.values():
        try:
            require_selection_window(package.id)
        except ValueError as error:
            raise ValueError(
                "Activate the matching Font window before changing font metadata, "
                "masters or glyph identities; Undo these edits there."
            ) from error


def disclose_pending(backend: Any) -> None:
    """Read and disclose the App queue caveat once per prospective edit batch."""
    from fontlabapp.core.edit_guards import disclose, pending_note, pending_updates

    if backend._history_disclosure is None:
        ids = pending_updates(backend._native())
        backend._history_disclosure = {
            "pending_updates": ids,
            "pending_note": pending_note(ids),
        }
        disclose(backend._history_disclosure)

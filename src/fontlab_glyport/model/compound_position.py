# this_file: src/fontlab_glyport/model/compound_position.py
"""Apply the retained positional component mutation with supplied name data."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Literal


def apply_positions(
    components: list[SimpleNamespace],
    position: Literal["init", "medi", "fina"] | None,
    lookup: Callable[[str], SimpleNamespace | None],
    connection_type: Callable[[str], str],
) -> None:
    """Mutate ordered records using raw alternates and an injected name classifier.

    Mirrors applyPositionalSuffixes:suffix:force: at 000c512c. The retained
    body has no force-dependent branch. Empty input safely does nothing here;
    this does not qualify the native body's pre-loop empty-array access.
    """
    if not components:
        return
    preceding = [True] * (len(components) + 1)
    following = [True] * len(components)
    preceding[0] = position in {"fina", "medi"}
    following[-1] = position in {"init", "medi"}
    for index, component in enumerate(components):
        name = component.name
        if ".init" in name or ".medi" in name:
            continue
        if name.endswith(".fina"):
            if index < len(components) - 1:
                preceding[index + 1] = False
            continue
        suffix = ".medi" if following[index] else ".fina"
        if not preceding[index]:
            suffix = ".init" if following[index] else None
        if connection_type(name) == "R":
            preceding[index + 1] = False
            if suffix == ".medi":
                suffix = ".fina"
            if suffix == ".init":
                continue
        if suffix is not None:
            alternate = lookup(name + suffix)
            if alternate is not None:
                components[index] = alternate
                continue
            if component._locked:
                from .compound_metadata import copy_record

                component = copy_record(component)
                components[index] = component
            component.name = name + suffix
            component.unicharString = None
            component.unicode = None
            component.unicodeLegacy = None


POSITION_SUFFIXES = {"init", "medi", "fina"}


def positional_alternate(
    name: str, lookup: Callable[[str], SimpleNamespace | None]
) -> SimpleNamespace | None:
    """Copy a component recipe only when its first raw component alternate exists."""
    base, dot, tail = name.partition(".")
    if not dot:
        return None
    record = lookup(base)
    if record is None:
        return None
    if "components" in getattr(record, "_unavailable_fields", ()):
        from ..errors import UnsupportedCapability

        raise UnsupportedCapability(
            "The source does not establish metadata recipes",
            capability="GSGlyphInfo.components.source",
        )
    components = getattr(record, "_component_records", None)
    if components is None:
        names = getattr(record, "_component_names", None)
        components = [lookup(key) for key in names or ()]
    if not components or components[0] is None:
        return None
    alternate = lookup(components[0].name + dot + tail)
    if alternate is None:
        return None
    from .compound_fields import copy_record

    result = copy_record(record)
    result.name, result.unicode = name, None
    if result._production_state.value is not None:
        result._production_state.value += dot + tail
    result._component_records = [alternate, *components[1:]]
    result._component_names = ()
    return result


def _position_state(
    slots: list[str], globals: list[str]
) -> tuple[str | None, list[str], list[str]]:
    if globals and globals[0] in POSITION_SUFFIXES:
        return globals[0], slots, globals[1:]
    if (
        len(slots) > 1
        and slots[0] in {"init", "medi"}
        and all(not token or token == "medi" for token in slots[1:-1])
    ):
        positions = {
            ("init", "fina"): None,
            ("init", "medi"): "init",
            ("medi", "fina"): "fina",
            ("medi", "medi"): "medi",
        }
        key = slots[0], slots[-1]
        if key in positions:
            return positions[key], [], globals
    return None, slots, globals

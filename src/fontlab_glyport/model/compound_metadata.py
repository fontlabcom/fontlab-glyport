# this_file: src/fontlab_glyport/model/compound_metadata.py
"""Compose decoded names while preserving ordered raw/shared/copy state.

Exceptional script/resource routes need their separate retained contracts.
This module never substitutes Unicode joining properties for a native name map.
"""

from types import SimpleNamespace

from .compound_fields import _base_text, _sort_metadata, _sub_category, copy_record
from .compound_position import _position_state, apply_positions
from .compound_production import (
    compound_production,
    is_number,
    join_names,
    language_suffix,
)
from .compound_resolution import resolve_components, resolve_seed
from .compound_scripts import INDIC_SCRIPTS, filter_halant, script_for_tag
from .production_metadata import StoredProduction
from .public_joining import positional_kind

SILENT_SUFFIXES = {"liga", "hlig", "dlig", "rlig"}


def compose_names(
    names: list[str], suffixes: list[str] | None = None
) -> SimpleNamespace | None:
    """Resolve names again, independently retaining raw and final components."""
    split = [name.partition(".") for name in names]
    slots = [parts[2] for parts in split] if any(parts[1] for parts in split) else []
    return _compose_parts([parts[0] for parts in split], slots, suffixes)


def _compose_parts(
    base_names: list[str], slots: list[str], suffixes: list[str] | None
) -> SimpleNamespace | None:
    """Keep separate surviving base names, complete suffix slots and global state."""
    from .glyph_metadata import _direct, name_info

    bases, component_suffixes = list(base_names), list(slots)
    if not bases:
        return None
    global_suffixes = list(suffixes or [])
    seed = resolve_seed(bases, component_suffixes, global_suffixes)
    if seed is None:
        return None
    silent = (
        global_suffixes.pop()
        if global_suffixes and global_suffixes[-1] in SILENT_SUFFIXES
        else None
    )
    position, component_suffixes, global_suffixes = _position_state(
        component_suffixes, global_suffixes
    )
    global_text = "." + ".".join(global_suffixes) if global_suffixes else None
    if seed.script in INDIC_SCRIPTS:
        bases = filter_halant(bases)
        if seed.subCategory == "Halfform":
            for base in bases:
                donor = name_info(base, fill_production=True)
                if (
                    donor
                    and donor.category == "Letter"
                    and donor.subCategory != "Halfform"
                ):
                    seed = (
                        copy_record(donor) if getattr(donor, "_locked", True) else donor
                    )
    seed_language = language_suffix(seed.name)
    if global_text in {".subs", ".sups", ".sinf"}:
        seed.case = 4
    if set(global_suffixes) & {"sc", "smcp", "c2sc"}:
        seed.case = 3
    raw, components, canonical, helpers, sorts = resolve_components(
        bases, component_suffixes, seed
    )
    _sub_category(seed, components)
    if (
        seed.category == "Mark"
        and len(component_suffixes) > 1
        and len(set(component_suffixes)) == 1
    ):
        global_text = "." + component_suffixes[0] if component_suffixes[0] else None
        component_suffixes = []
    if global_suffixes and not is_number(global_text):
        nested = _compose_parts(
            bases, component_suffixes, [position] if position else None
        )
        if nested is not None:
            components = [nested]
    component_text = (
        "." + "_".join(component_suffixes) if any(component_suffixes) else ""
    )
    suffix = component_text + ("." + position if position else "") + (global_text or "")
    suffix += "." + silent if silent else ""
    seed.name = join_names(canonical) + suffix
    seed._component_records = components
    seed._unavailable_fields = frozenset(getattr(seed, "_unavailable_fields", ())) - {
        "components"
    }
    seed._component_names = ()
    if (
        len(bases) > 1
        and getattr(seed, "anchors", None)
        and seed.anchors[0] == "_nukta"
    ):
        donor = name_info(bases[1], fill_production=True)
        if donor is not None:
            seed.anchors = list(donor.anchors) if donor.anchors is not None else None
            seed.marks = list(donor.marks) if donor.marks is not None else None
    _sort_metadata(seed, sorts, position, global_text)
    if position or seed.script == "arabic":
        apply_positions(components, position, _direct, positional_kind)
    text = "".join(
        _base_text(component) + ("\u200d" if seed.script == "runic" else "")
        for component in components
    )
    if text:
        if seed.script == "runic" and text.endswith("\u200d"):
            text = text[:-1]
        seed.unicharString = None
        seed.unicodeLegacy = None
        seed.baseString = text.replace("\u094d\u094d\u0930", "\u094d\u0930\u094d")
    seed._production_state = StoredProduction(
        compound_production(
            raw, helpers, component_text, global_text, silent, position, global_suffixes
        )
    )
    seed.unicode = None
    mapped_script = script_for_tag(seed_language)
    if mapped_script:
        seed.script = mapped_script
    return copy_record(seed)

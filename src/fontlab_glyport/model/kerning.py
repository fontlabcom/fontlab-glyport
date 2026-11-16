# this_file: src/fontlab_glyport/model/kerning.py
"""LTR kerning mapping boundaries and lossless class-membership plans."""

from collections.abc import Mapping, MutableMapping
from dataclasses import replace
from math import isfinite

from ..errors import UnsupportedCapability
from .backend import KerningClassInfo, KerningPair, ModelBackend

PREFIX = {"left": "@MMK_L_", "right": "@MMK_R_"}


def group_name(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError("Kerning group must be a string or None")
    if value != value.strip() or value.startswith("@") or "\x00" in value:
        raise ValueError("Kerning group must be a plain nonblank class name")
    return value


def available_group_name(
    backend: ModelBackend, font_id: str, value: str | None
) -> None:
    if value is not None and any(g.name == value for g in backend.classes(font_id)):
        raise UnsupportedCapability(
            "Kerning group name conflicts with an OpenType class",
            capability="GSGlyph.kerningGroups",
        )


def master_id(font, key: object) -> str:
    font._check()
    if not isinstance(key, str):
        raise TypeError("Master id must be a string")
    if key not in {m.id for m in font._data().masters}:
        raise ValueError("Master does not belong to this font")
    return key


def references(pairs: tuple[KerningPair, ...], name: str) -> bool:
    return any(
        p.left == PREFIX["left"] + name or p.right == PREFIX["right"] + name
        for p in pairs
    )


def membership_plan(
    groups: tuple[KerningClassInfo, ...],
    pairs: tuple[KerningPair, ...],
    glyph: str,
    side: str,
    value: str | None,
) -> tuple[KerningClassInfo, ...]:
    """Keep pair keys and opposite-side memberships; refuse unsplittable classes."""
    target = next((g for g in groups if g.name == value), None)
    if target is not None and not getattr(target, side):
        raise UnsupportedCapability(
            "Class name is already used by the opposite side",
            capability="GSGlyph.kerningGroups",
        )
    result = []
    for group in groups:
        if group.name == value:
            members = group.glyphs if glyph in group.glyphs else (*group.glyphs, glyph)
        elif getattr(group, side):
            members = tuple(n for n in group.glyphs if n != glyph)
        else:
            members = group.glyphs
        if members != group.glyphs and group.left and group.right:
            raise UnsupportedCapability(
                "Independent membership of a two-sided FontLab class cannot be represented",
                capability="GSGlyph.kerningGroups",
            )
        if members or references(pairs, group.name):
            result.append(replace(group, glyphs=members))
        elif members == group.glyphs:
            result.append(group)  # unrelated pre-existing empty class
    if value is not None and target is None:
        result.append(
            KerningClassInfo(
                value, (glyph,), left=side == "left", right=side == "right"
            )
        )
    return tuple(result)


def replacement_pairs(font, master: str, value: object) -> tuple[KerningPair, ...]:
    if not isinstance(value, Mapping):
        raise TypeError(
            "Master kerning must be a mapping of left keys to right-key mappings"
        )
    if not value:
        return ()
    backend = font._model._backend
    glyphs = {g.id: g.name for g in font._glyph_data()}
    groups = {g.name: g for g in backend.kerning_classes(font.id, master)}

    def key_name(key, side):
        if not isinstance(key, str) or not key:
            raise TypeError("Kerning keys must be nonempty glyph ids or class keys")
        if key.startswith(PREFIX[side]):
            group = groups.get(key[len(PREFIX[side]) :])
            if group is not None and getattr(group, side):
                return key
        elif key in glyphs:
            return glyphs[key]
        raise ValueError(f"Unknown or wrong-side kerning key: {key!r}")

    pairs = []
    for left, rights in value.items():
        left = key_name(left, "left")
        if not isinstance(rights, Mapping):
            raise TypeError("Each left kerning key needs a mapping")
        for right, number in rights.items():
            right = key_name(right, "right")
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise TypeError("Kerning values must be finite numbers")
            number = float(number)
            if not isfinite(number):
                raise ValueError("Kerning values must be finite numbers")
            pairs.append(KerningPair(left, right, number))
    return tuple(pairs)


class ReadOnlyKerning(Mapping):
    """Explicitly refuse nested writes instead of returning a mutable snapshot."""

    def __init__(self, values):
        self._values = values

    def __getitem__(self, key):
        value = self._values[key]
        return ReadOnlyKerning(value) if isinstance(value, dict) else value

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __setitem__(self, key, value):
        raise UnsupportedCapability(
            "Assign font.kerning[masterId] or use setKerningForPair; nested kerning writes are unsupported",
            capability="GSFont.kerning.nested",
        )

    def __delitem__(self, key):
        self.__setitem__(key, None)


class KerningMapping(MutableMapping):
    """Live master assignment; nested values are read-only snapshots, LTR only."""

    def __init__(self, font):
        self._font = font

    def _snapshot(self):
        font = self._font
        font._check()
        ids = font._glyph_ids()
        result = {}
        for master in font._data().masters:
            for pair in font._model._backend.kerning(font.id, master.id):
                left, right = (
                    ids.get(pair.left, pair.left),
                    ids.get(pair.right, pair.right),
                )
                result.setdefault(master.id, {}).setdefault(left, {})[right] = (
                    pair.value
                )
        return result

    def __getitem__(self, key):
        return ReadOnlyKerning(self._snapshot()[key])

    def __setitem__(self, key, value):
        font = self._font
        key = master_id(font, key)
        pairs = replacement_pairs(font, key, value)
        font._model._backend.replace_kerning(font.id, key, pairs)

    def __delitem__(self, key):
        raise UnsupportedCapability(
            "Use font.kerning[masterId] = {} to clear a master",
            capability="GSFont.kerning.delete",
        )

    def __iter__(self):
        return iter(self._snapshot())

    def __len__(self):
        return len(self._snapshot())

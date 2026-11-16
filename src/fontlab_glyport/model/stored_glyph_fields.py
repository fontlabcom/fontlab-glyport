# this_file: src/fontlab_glyport/model/stored_glyph_fields.py
"""Raw group/direction fields and their distinct store/reset contracts.

Owned scalar types are intentionally bounded; arbitrary PyObjC coercions and
native undo/event delivery are not emulated here.
"""

from ..errors import UnsupportedCapability

PREFIX = "com.schriftgestaltung.Glyphs."
GROUP_KEY = PREFIX + "group"
GROUP_IDX_KEY = PREFIX + "groupIdx"
DIRECTION_KEY = PREFIX + "direction"
STORE_GROUP_KEY = PREFIX + "storeGroup"
STORE_DIRECTION_KEY = PREFIX + "storeDirection"


def record_value(record, field):
    if field in getattr(record, "_unavailable_fields", ()) or not hasattr(
        record, field
    ):
        raise UnsupportedCapability(
            f"The selected source does not establish {field}",
            capability=f"GSGlyphInfo.{field}.source",
        )
    return getattr(record, field)


def raw_value(glyph, field):
    key, default = {
        "group": (GROUP_KEY, None),
        "groupIdx": (GROUP_IDX_KEY, 0),
        "direction": (DIRECTION_KEY, 0),
    }[field]
    return glyph._case_state().get(key, default)


def set_raw_value(glyph, field, value):
    if field == "group":
        if value is not None and type(value) is not str:
            raise TypeError("Group must be a string or None")
        key = GROUP_KEY
    else:
        if type(value) is not int:
            raise TypeError(f"{field} requires an owned integer value")
        low, high = (-32768, 32767) if field == "groupIdx" else (0, 255)
        if not low <= value <= high:
            raise ValueError(f"{field} must fit {low}..{high}")
        key = GROUP_IDX_KEY if field == "groupIdx" else DIRECTION_KEY
    state = glyph._case_state()
    if raw_value(glyph, field) != value:
        state[key] = value
        glyph._set_case_state(state)


def set_store(glyph, field, value):
    flag = STORE_GROUP_KEY if field == "group" else STORE_DIRECTION_KEY
    value = bool(value)
    state = glyph._case_state()
    if bool(state.get(flag, False)) == value:
        return
    state[flag] = value
    if field == "direction" and not value:
        if "_draft" in glyph.__dict__:
            raise UnsupportedCapability(
                "No parent manager for detached reset",
                capability="GSGlyph.storeDirection.detachedReset",
            )
        from .glyph_metadata import resolve

        record = resolve(glyph, state=state)
        state[DIRECTION_KEY] = record_value(record, "direction")
    # No source lookup, snapshot, or reset occurs for a group flag transition.
    glyph._set_case_state(state)

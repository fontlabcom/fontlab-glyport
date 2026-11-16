# this_file: src/fontlab_glyport/model/fontlab_kerning.py
"""FontLab tool-backed kerning writes; native tools own their Undo history."""

from ..errors import UnsupportedCapability
from .kerning import available_group_name, group_name, membership_plan, references

CAPABILITY = "GSGlyph.kerningGroups"
SHARED_CLASSES = "com.fontlab.kerningClassesInMainMaster"


def snapshot(backend, font_id):
    """Revision cache survives our known edits, never an external history change."""
    cache = backend.__dict__.setdefault("_kerning_snapshots", {})
    cached = cache.get(font_id)
    masters = backend.font_info(font_id).masters
    shared = bool(backend.lib(font_id).get(SHARED_CLASSES, False))
    master_ids = tuple(m.id for m in masters)
    containers = (
        cached[1]["containers"]
        if cached is not None
        and tuple(cached[1]["classes"]) == master_ids
        and cached[1]["shared"] == shared
        else None
    )
    try:
        revision, containers = backend.kerning_write_revision(
            font_id, master_ids, containers
        )
    except Exception:
        # A failed/stale retained handle must not survive into a later retry.
        cache.pop(font_id, None)
        raise
    if (
        cached is not None
        and cached[0] == revision
        and tuple(cached[1]["classes"]) == tuple(m.id for m in masters)
        and cached[1]["shared"] == shared
    ):
        return cached[1]
    state = {
        "classes": {m.id: backend.kerning_classes(font_id, m.id) for m in masters},
        "pairs": {m.id: backend.kerning(font_id, m.id) for m in masters},
        "shared": shared,
        "containers": containers,
    }
    cache[font_id] = revision, state
    return state


def class_operations(before, after, master):
    old, new = {g.name: g for g in before}, {g.name: g for g in after}
    operations = []
    for name in old.keys() - new.keys():
        operations.append(
            ("delete_kerning_class", {"master_name": master, "class_name": name})
        )
    for group in after:
        if old.get(group.name) == group:
            continue
        arguments = {
            "master_name": master,
            "class_name": group.name,
            "glyph_names": list(group.glyphs),
        }
        if group.name not in old:
            arguments.update(left=group.left, right=group.right)
        operations.append(("set_kerning_class", arguments))
    return operations


def execute(backend, font_id, state, operations, capability):
    """Resolve all dependencies before writing; errors retain native history."""
    # Shared native class commands copy complete groups across all masters.
    # The host reader omits raw mainGlyphName, so reduced record equality cannot
    # establish metadata preservation. Pair-only commands do not synchronize.
    if state["shared"] and any(
        name.endswith("kerning_class") for name, _ in operations
    ):
        raise UnsupportedCapability(
            "Shared FontLab class edits require complete native metadata access; "
            "the host cannot expose raw per-master main-glyph references",
            capability="GSGlyph.kerningGroups.sharedMetadata",
        )
    fid = backend._tool_font(font_id, capability)
    tools = {name: backend._resolve_tool(name, capability) for name, _ in operations}
    if not operations:
        return
    cache = backend._kerning_snapshots
    cache.pop(font_id, None)
    try:
        for name, arguments in operations:
            tools[name](font_id=fid, **arguments)
    finally:
        # Even an error may follow a native mutation. Never reuse its old cache.
        backend._kerning_changed()
    revision, state["containers"] = backend.kerning_write_revision(
        font_id, tuple(state["classes"]), state["containers"]
    )
    cache[font_id] = revision, state


def set_group(backend, font_id, glyph_id, side, value):
    backend._tool_font(font_id, CAPABILITY)
    value = group_name(value)
    available_group_name(backend, font_id, value)
    if side not in {"left", "right"}:
        raise ValueError("Unknown kerning side")
    glyph = backend.glyph_info(glyph_id)
    if backend._parents[glyph_id] != font_id:
        raise ValueError("Glyph does not belong to this font")
    state = snapshot(backend, font_id)
    all_pairs = tuple(p for pairs in state["pairs"].values() for p in pairs)
    plans = {
        master: membership_plan(
            groups,
            all_pairs if state["shared"] else state["pairs"][master],
            glyph.name,
            side,
            value,
        )
        for master, groups in state["classes"].items()
    }
    operations = []
    for master, groups in plans.items():
        operations.extend(
            class_operations(
                state["classes"][master], groups, backend._master_names[master]
            )
        )
    execute(backend, font_id, {**state, "classes": plans}, operations, CAPABILITY)


def replace_pairs(backend, font_id, master_id, pairs):
    capability = "GSFont.kerning"
    backend._tool_font(font_id, capability)
    master = backend._kerning_master(font_id, master_id)
    state = snapshot(backend, font_id)
    old = {(p.left, p.right): p.value for p in state["pairs"][master_id]}
    new = {(p.left, p.right): p.value for p in pairs}
    operations = []
    if old and not new:
        operations.append(("delete_all_kerning_pairs", {"master_name": master}))
    else:
        from .fontlab_backend import _fontlab_key

        for (left, right), value in new.items():
            if old.get((left, right)) != value:
                operations.append(
                    (
                        "set_kerning_pair",
                        {
                            "master_name": master,
                            "left": _fontlab_key(left, "left"),
                            "right": _fontlab_key(right, "right"),
                            "value": value,
                        },
                    )
                )
        for left, right in old.keys() - new.keys():
            operations.append(
                (
                    "delete_kerning_pair",
                    {
                        "master_name": master,
                        "left": _fontlab_key(left, "left"),
                        "right": _fontlab_key(right, "right"),
                    },
                )
            )
    updated_pairs = {**state["pairs"], master_id: pairs}
    used = (
        tuple(p for rows in updated_pairs.values() for p in rows)
        if state["shared"]
        else pairs
    )
    groups = state["classes"][master_id]
    kept = tuple(g for g in groups if g.glyphs or references(used, g.name))
    operations.extend(class_operations(groups, kept, master))
    classes = (
        state["classes"] if state["shared"] else {**state["classes"], master_id: kept}
    )
    execute(
        backend,
        font_id,
        {**state, "pairs": updated_pairs, "classes": classes},
        operations,
        capability,
    )

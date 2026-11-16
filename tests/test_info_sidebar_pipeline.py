# this_file: tests/test_info_sidebar_pipeline.py
"""Owned source oracles; no proprietary resource or framework execution."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.info_runtime import InfoNativeException
from fontlab_glyport.glyphsapp.info_sidebar import (
    SidebarItem,
    load_subcategories,
    merge_groups,
    process_groups,
)


class Provider:
    def __init__(self):
        self.events = []
        self.images = {}
        self.symbols = {}
        self.failure = None

    def localize(self, text):
        self.events.append(("localize", text))
        return "Localized K" if text == "Raw K" else text

    def compile_predicate(self, text, *args):
        self.events.append(("compile", text, args))
        if text == "bad":
            raise self.failure or InfoNativeException("owned invalid format")
        return ("predicate", text, args)

    def present_error(self, error):
        self.events.append(("error", error))

    def register_defaults(self, value):
        self.events.append(("register", value))

    def compare(self, left, right):
        self.events.append(("compare", left, right))
        return (left > right) - (left < right)

    def image_named(self, name):
        self.events.append(("image", name))
        return self.images.get(name)

    def system_symbol(self, name, description):
        self.events.append(("symbol", name, description))
        return self.symbols.get(name)

    def schedule_count_update(self, item, delay):
        self.events.append(("schedule", item, delay))


def state():
    return SimpleNamespace(
        name2Group={},
        sidebarCategories=[],
        categories=[],
        subCategories=[],
        scriptIDs=[],
        categoriesGroup=None,
        subCategoryOrder=None,
    )


def test_plain_and_dictionary_item_defaults_and_raw_identity():
    plain = SidebarItem()
    assert (plain.count, plain.shallHaveCount, plain.cell) == (-1, -1, "HeaderCell")
    assert plain.name is plain.identifier is plain.subItems is plain.parent is None
    assert plain.itemType == 0 and plain.editable is False
    provider = Provider()
    raw, codes = ["invented.a"], {"owned": 1}
    item = SidebarItem.from_dict(
        {"name": "Raw K", "list": raw, "codes": codes}, provider
    )
    assert (item.name, item.displayName, item.identifier) == (
        "Localized K",
        "Localized K",
        "Raw K",
    )
    assert item.coverage is raw and item.codes is codes
    assert item.predicate is item.predicateFormat is None
    assert item.cell == "ImageTextCell"
    assert provider.events == [("localize", "Raw K")]


@pytest.mark.parametrize(
    "attributes,icon",
    [
        ({"id": "", "icon": "", "list": []}, ""),
        ({"list": [], "predicate": "valid"}, "text.alignleft"),
        ({"predicate": "valid"}, "gearshape"),
        ({}, "folder"),
    ],
)
def test_filter_icon_uses_nil_checks(attributes, icon):
    manager = state()
    item = process_groups(
        manager, [{"name": "Owned", **attributes}], None, 3, Provider()
    )[0]
    assert item.iconName == icon and item.itemType == 3
    assert manager.name2Group[item.identifier] is item
    assert manager.sidebarCategories == [item.identifier]


def test_predicate_recovery_keeps_later_fields_and_event_order():
    provider, coverage, codes = Provider(), ["invented.a"], [42]
    item = SidebarItem.from_dict(
        {
            "name": "Owned",
            "predicate": "bad",
            "list": coverage,
            "codes": codes,
            "default": True,
            "suppressCount": "NO",
        },
        provider,
    )
    assert item.predicate == ("predicate", "name == %@", ("A",))
    assert (item.count, item.shallHaveCount, item.badgeString) == (-2, -2, "🛑")
    assert item.coverage is coverage and item.codes is codes and item.default is True
    assert item.suppressCount is False and item.cell == "ImageTextCell"
    assert [event[0] for event in provider.events] == [
        "localize",
        "compile",
        "localize",
        "compile",
        "error",
    ]
    error = provider.events[-1][1]
    assert (error.domain(), error.code(), error.localizedDescription()) == (
        "GSGlyphsDomain",
        991,
        "Invalid filter in sidebar: Owned",
    )


@pytest.mark.parametrize(
    "failure", [RuntimeError("bug"), UnsupportedCapability("held")]
)
def test_nonmatching_predicate_errors_propagate(failure):
    provider = Provider()
    provider.failure = failure
    with pytest.raises(type(failure)) as raised:
        SidebarItem.from_dict({"name": "Owned", "predicate": "bad"}, provider)
    assert raised.value is failure
    assert provider.events == [("localize", "Owned"), ("compile", "bad", ())]


def test_raw_coverage_assignment_and_explicit_setter_are_distinct():
    provider = Provider()
    item = SidebarItem.from_dict({"name": "Owned", "list": "not-array"}, provider)
    item.setCoverage_(None)
    item.setCoverage_("ignored")
    assert item.coverage == "not-array" and len(provider.events) == 1
    coverage = []
    item.setCoverage_(coverage)
    assert item.coverage is coverage
    assert provider.events[-1] == ("schedule", item, 10_000_000)
    item.setCoverage_([])
    assert sum(event[0] == "schedule" for event in provider.events) == 1


def test_top_level_language_visibility_only_registers_defaults():
    provider, manager = Provider(), state()
    process_groups(
        manager,
        [
            {"name": "P", "subGroup": [{"name": "child"}]},
            {"name": "Q", "visible": True},
        ],
        None,
        2,
        provider,
    )
    assert [e for e in provider.events if e[0] == "register"] == [
        ("register", {"GSSidebarItemHidden_P": True})
    ]
    assert manager.sidebarCategories == ["P", "Q"]
    assert set(manager.name2Group) == {"P", "P/child", "Q"}


def test_duplicate_leaf_retains_return_order_and_first_lookup_identity():
    manager, provider = state(), Provider()
    first = process_groups(manager, [{"name": "First", "id": "X"}], None, 1, provider)[
        0
    ]
    second = process_groups(
        manager, [{"name": "Second", "id": "X"}], None, 2, provider
    )[0]
    assert first is not second and (first.name, second.name) == ("First", "Second")
    assert manager.name2Group == {"X": first} and manager.sidebarCategories == ["X"]


@pytest.mark.parametrize(
    "original_children,new_children",
    [(None, []), (None, [{"name": "B"}]), ([{"name": "A"}], [{"name": "B"}])],
)
def test_collision_group_merge_preserves_nil_and_parent_asymmetry(
    original_children, new_children
):
    manager, provider = state(), Provider()
    attributes = {"name": "First", "id": "X"}
    if original_children is not None:
        attributes["subGroup"] = original_children
    first = process_groups(manager, [attributes], None, 1, provider)[0]
    previous = first.subItems
    result = process_groups(
        manager,
        [
            {
                "name": "Second",
                "id": "X",
                "subGroup": new_children,
                "category": "OwnedCategory",
            }
        ],
        None,
        1,
        provider,
    )
    assert result == [] and manager.name2Group["X"] is first
    assert manager.categories == ["OwnedCategory"]
    assert first.subItems is not None
    if previous is not None:
        assert first.subItems is previous and first.subItems[-1].parent is None
    elif first.subItems:
        assert first.subItems[0].parent is first


def test_filter_collisions_keep_each_group_and_their_parent_links():
    manager = state()
    rows = process_groups(
        manager,
        [
            {"name": "X", "subGroup": [{"name": "A"}]},
            {"name": "X", "subGroup": [{"name": "A"}]},
        ],
        None,
        3,
        Provider(),
    )
    assert len(rows) == 2 and rows[0] is manager.name2Group["X"]
    assert manager.name2Group["X/A"] is rows[0].subItems[0]
    assert rows[1].subItems[0] is not rows[0].subItems[0]
    assert all(row.subItems[0].parent is row for row in rows)


@pytest.mark.parametrize("arrays", [None, []])
def test_categories_preserve_nil_arrays_and_script_length(arrays):
    manager = state()
    for name in ("categories", "subCategories", "scriptIDs"):
        setattr(manager, name, None if arrays is None else [])
    groups = [
        {"name": "Owned", "category": "Cat", "subCategory": "Sub", "script": script}
        for script in ("x", "xy", "xy")
    ]
    rows = process_groups(manager, groups, None, 0, Provider())
    assert all(row.itemType == 0 for row in rows)
    assert (manager.categories, manager.subCategories, manager.scriptIDs) == (
        (None, None, None) if arrays is None else (["Cat"], ["Sub"], ["xy"])
    )


def test_custom_groups_sort_entire_destination_without_reparenting():
    provider, manager = Provider(), state()
    destination = process_groups(
        manager,
        [{"name": "Middle", "subGroup": [{"name": "Zulu"}, {"name": "Alpha"}]}],
        None,
        1,
        provider,
    )
    header = SidebarItem()
    header.setSubItems_(destination)
    assert (
        merge_groups(
            manager, [{"name": "Zulu"}, {"name": "Alpha"}], destination, provider
        )
        is True
    )
    assert [row.name for row in destination] == ["Alpha", "Middle", "Zulu"]
    assert destination[0].parent is destination[2].parent is None
    assert destination[1].parent is header
    assert [row.name for row in destination[1].subItems] == ["Zulu", "Alpha"]
    snapshot = list(provider.events)
    assert merge_groups(manager, None, destination, provider) is True
    assert provider.events == snapshot


def test_setters_retain_array_recurse_and_notify_changed_display_name():
    parent, child, grandchild = SidebarItem(), SidebarItem(), SidebarItem()
    descendants = [child]
    parent.setSubItems_(descendants)
    child.setSubItems_([grandchild])
    assert (
        parent.subItems is descendants
        and child.parent is parent
        and grandchild.parent is child
    )
    parent.setEditable_(True)
    assert parent.editable is child.editable is grandchild.editable is True
    events = []
    child.parent = SimpleNamespace(
        didChangeSidebarItem_=lambda value: events.append(value)
    )
    child.name = "Old"
    child.displayName = "Old"
    child.displayName = "New"
    assert child.name == "New" and events == [child]


def test_subcategory_ranks_duplicate_and_number_overrides_and_rebuild():
    manager = state()
    manager.categoriesGroup = SidebarItem()
    categories = process_groups(
        manager,
        [
            {
                "name": "Number",
                "subGroup": [
                    {"name": "Q"},
                    {"name": "Q"},
                    {"name": "R"},
                    {"name": "Decimal Digit_LF"},
                ],
            },
            {"name": "Missing"},
            {"name": "Empty", "subGroup": []},
        ],
        None,
        1,
        Provider(),
    )
    manager.categoriesGroup.setSubItems_(categories)
    ranks = load_subcategories(manager)
    assert ranks is manager.subCategoryOrder
    assert ranks == {
        "Number": {
            "Q": 10,
            "R": 20,
            "Decimal Digit_LF": 2,
            "Decimal Digit_OST": 3,
            "Decimal Digit_TF": 4,
            "Decimal Digit_TOST": 5,
        },
        "Empty": {},
    }
    categories[0].subItems.append(SidebarItem.from_dict({"name": "S"}, Provider()))
    assert "S" not in ranks["Number"]
    assert load_subcategories(manager)["Number"]["S"] == 40


@pytest.mark.parametrize(
    "children,expected",
    [
        (None, {}),
        (
            [],
            {
                "Number": {
                    "Decimal Digit_LF": 2,
                    "Decimal Digit_OST": 3,
                    "Decimal Digit_TF": 4,
                    "Decimal Digit_TOST": 5,
                }
            },
        ),
    ],
)
def test_number_nil_and_empty_subitems_differ(children, expected):
    manager = state()
    row = SidebarItem.from_dict({"name": "Number"}, Provider())
    row.setSubItems_(children)
    manager.categoriesGroup = SidebarItem()
    manager.categoriesGroup.setSubItems_([row])
    assert load_subcategories(manager) == expected


def test_icon_search_order_cache_and_name_change():
    provider = Provider()
    token = provider.images["OwnedMarkTemplate"] = object()
    item = SidebarItem.from_dict({"name": "Owned", "icon": "Owned Mark"}, provider)
    provider.events.clear()
    assert item.icon is token
    assert provider.events == [
        ("image", name)
        for name in (
            "Owned Mark",
            "OwnedMark",
            "Owned MarkTemplate",
            "OwnedMarkTemplate",
        )
    ]
    item.setIconName_("Other")
    assert item.icon is token and len(provider.events) == 4


def test_icon_failed_search_clears_name_and_symbol_description_is_original():
    provider = Provider()
    item = SidebarItem.from_dict({"name": "Owned", "icon": "Owned Mark"}, provider)
    provider.events.clear()
    assert item.icon is None and item.iconName is None
    assert provider.events[-2:] == [
        ("symbol", "owned.mark", "Owned Mark"),
        ("symbol", "questionmark.circle", "Owned Mark"),
    ]
    snapshot = list(provider.events)
    assert item.icon is None and provider.events == snapshot


def test_display_change_bubbles_containing_rows_rather_than_original_leaf():
    root, parent, child = SidebarItem(), SidebarItem(), SidebarItem()
    root.setSubItems_([parent])
    parent.setSubItems_([child])
    events = []
    root.parent = SimpleNamespace(didChangeSidebarItem_=lambda row: events.append(row))
    child.displayName = "Changed"
    assert events == [root]


@pytest.mark.parametrize("guard", ["calculating", "error", "suppressed"])
def test_count_guards_precede_missing_scheduler(guard):
    item = SidebarItem()
    item.badgeString = "prior"
    if guard == "calculating":
        item.calculating = True
    elif guard == "error":
        item.count = -2
    else:
        item.suppressCount = True
    item.setCoverage_([])
    assert item.badgeString == (None if guard == "suppressed" else "prior")


def test_missing_scheduler_is_explicit_and_keeps_prior_assignment():
    item, coverage = SidebarItem(), []
    with pytest.raises(UnsupportedCapability, match="scheduler"):
        item.setCoverage_(coverage)
    assert item.coverage is coverage and item.calculating is True


def test_fallback_compilation_error_propagates_without_presenting_error():
    provider = Provider()
    original = provider.compile_predicate
    failure = InfoNativeException("secondary")

    def compile_(text, *args):
        if args:
            raise failure
        return original(text, *args)

    provider.compile_predicate = compile_
    with pytest.raises(InfoNativeException) as raised:
        SidebarItem.from_dict({"name": "Owned", "predicate": "bad"}, provider)
    assert raised.value is failure
    assert not any(event[0] == "error" for event in provider.events)


def test_empty_names_and_ids_remain_explicit_in_nested_paths():
    manager = state()
    root = process_groups(
        manager,
        [{"name": "X", "subGroup": [{"name": "", "id": ""}]}],
        None,
        1,
        Provider(),
    )[0]
    assert manager.name2Group["X"] is root
    assert set(manager.name2Group) == {"X"}
    assert root.subItems[0].identifier == root.subItems[0].name == ""
    assert root.subItems[0].parent is root


def test_nontrivial_path_components_require_explicit_provider():
    manager = state()
    with pytest.raises(UnsupportedCapability, match="path"):
        process_groups(
            manager,
            [{"name": "X", "subGroup": [{"name": "/complex"}]}],
            None,
            1,
            Provider(),
        )
    provider = Provider()
    provider.append_path_component = lambda parent, child: parent + "/owned:" + child
    rows = process_groups(
        state(), [{"name": "X", "subGroup": [{"name": "/complex"}]}], None, 1, provider
    )
    assert rows[0].subItems[0].name == "/complex"


def test_icon_system_symbol_reuses_calibrated_foundation_casing():
    provider = Provider()
    token = provider.symbols["'ς"] = object()
    item = SidebarItem.from_dict({"name": "Owned", "icon": "'Σ"}, provider)
    assert item.icon is token
    assert provider.events[-1] == ("symbol", "'ς", "'Σ")


def test_icon_nil_and_plain_missing_provider_are_distinct():
    item = SidebarItem()
    assert item.icon is None
    item.iconName = "Owned"
    with pytest.raises(UnsupportedCapability, match="image provider"):
        _ = item.icon


def test_explicit_boolvalue_protocol_and_unsupported_input():
    provider = Provider()
    yes = SimpleNamespace(boolValue=lambda: True)
    item = SidebarItem.from_dict({"name": "Owned", "default": yes}, provider)
    assert item.default is True
    with pytest.raises(UnsupportedCapability, match="boolValue"):
        SidebarItem.from_dict({"name": "Owned", "default": []}, provider)
    with pytest.raises(UnsupportedCapability, match="name"):
        SidebarItem.from_dict({}, provider)

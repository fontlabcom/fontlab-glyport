# this_file: tests/test_info_dynamic_sidebar.py
"""Independent C/ARM branch, identity and mutation oracles; owned inputs only."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.info_manager import GSGlyphsInfo
from fontlab_glyport.glyphsapp.info_runtime import (
    InfoNativeException,
    InfoState,
    using_info_provider,
)
from fontlab_glyport.glyphsapp.info_sidebar import SidebarItem


class Provider:
    def __init__(self):
        self.events, self.pending, self.defaults = [], [], {}
        self.mapping, self.categories = {"Existing": "kept"}, []

    def set_from_array(self, values):
        self.events.append(("set", tuple(values)))
        if None in values:
            raise ValueError("owned set policy rejects nil")
        return set(values)

    def localize(self, value):
        self.events.append(("localize", value))
        return "localized:" + value

    def compile_predicate(self, pattern, *args):
        result = SimpleNamespace(predicateFormat=pattern, arguments=args)
        self.events.append(("compile", pattern, args))
        return result

    def compare(self, a, b):
        # Explicit legal comparator; deliberately unlike Python's ascending order.
        self.events.append(("compare", a, b))
        return (b > a) - (b < a)

    def schedule_count_update(self, item, delay):
        self.pending.append((item, delay))

    def resource_url(self, name, extension):
        self.events.append(("resource", name, extension))
        return "owned:" + name

    def load_dictionary(self, url):
        self.events.append(("dictionary", url))
        return self.mapping

    def array_add_objects(self, destination, values):
        assert values is None
        self.events.append("owned-nil-array-policy:no-op")

    def defaults_bool_for_key(self, key):
        self.events.append(("defaults-read", key))
        return self.defaults.get(key, False)


class Glyphs(list):
    def __init__(self, events, scripts=(), counts=None, rows=()):
        super().__init__(rows)
        self.events, self.scripts, self.counts = events, scripts, counts or {}

    def valueForKey_(self, name):
        self.events.append(("kvc", name))
        return self.scripts

    def countOfObjectsWithOptions_matchingPredicate_(self, options, predicate):
        self.events.append(("count", options, predicate))
        return self.counts[predicate.predicateFormat]


class Font:
    def __init__(
        self, provider, scripts=(), counts=None, rows=(), types=(0, 0), tags=((),)
    ):
        self.events = provider.events
        self.glyphs = Glyphs(self.events, scripts, counts, rows)
        self.types, self.tags = iter(types), iter(tags)

    def lockReadGlyphs(self):
        self.events.append("lock")

    def unlockReadGlyphs(self):
        self.events.append("unlock")

    def fontType(self):
        value = next(self.types)
        self.events.append(("type", value))
        return value

    @property
    def allTags(self):
        value = next(self.tags)
        self.events.append(("tags", value))
        return value


def manager(provider, cls=GSGlyphsInfo):
    value = object.__new__(cls)
    value._lifecycle = InfoState(provider, None)
    return value


def group(children):
    return SimpleNamespace(subItems=children)


def child(hidden, pattern=None):
    class Child(SimpleNamespace):
        def setParent_(self, parent):
            self.parent = parent

    return Child(
        hidden=hidden,
        predicate=None if pattern is None else SimpleNamespace(predicateFormat=pattern),
    )


def test_projection_reads_scripts_even_for_nil_or_empty_group():
    for value in (None, group(None), group([])):
        provider = Provider()
        assert manager(provider).filterGroup_forFont_(value, Font(provider)) is None
        assert provider.events == ["lock", ("kvc", "script"), ("set", ()), "unlock"]


def test_projection_visible_child_never_reads_predicate():
    class Visible:
        hidden = False

        @property
        def predicate(self):
            pytest.fail("visible predicate was touched")

    provider = Provider()
    original = group([Visible()])
    assert manager(provider).filterGroup_forFont_(original, Font(provider)) is original


@pytest.mark.parametrize(
    "pattern,scripts,counts,kept,general",
    [
        ('script == "latin"', ["latin"], {}, True, False),
        ('script == "greek"', ["latin"], {}, False, False),
        ('script == "😀"', ["😀"], {}, True, False),
        (
            'script == "latin" OR name == "A"',
            [],
            {'script == "latin" OR name == "A"': 2},
            True,
            True,
        ),
        ('script == "latin" or name == "A"', ["latin"], {}, False, False),
        ('script == "latin"OR name == "A"', ["latin"], {}, False, False),
        ('name == "A"', [], {'name == "A"': 0}, False, True),
        ('name == "A"', [], {'name == "A"': 3}, True, True),
        (None, [], {None: 1}, True, True),
    ],
)
def test_projection_exact_shortcut_or_general_count(
    pattern, scripts, counts, kept, general
):
    provider = Provider()
    row = child(True, pattern)
    if pattern is None:
        row.predicate = SimpleNamespace(predicateFormat=None)
    # Item's stored format is unrelated to the predicate's current format.
    row.predicateFormat = 'script == "WRONG"'
    original = group([row])
    actual = manager(provider).filterGroup_forFont_(
        original, Font(provider, scripts, counts)
    )
    assert actual is (original if kept else None)
    assert provider.events[:4] == [
        "lock",
        ("kvc", "script"),
        ("set", tuple(scripts)),
        "unlock",
    ]
    assert provider.events[4:] == (
        ["lock", ("count", 1, row.predicate), "unlock"] if general else []
    )


def test_projection_hidden_nil_and_malformed_range_are_not_normalized():
    provider = Provider()
    assert (
        manager(provider).filterGroup_forFont_(group([child(True)]), Font(provider))
        is None
    )
    with pytest.raises(ValueError, match="range"):
        manager(provider).filterGroup_forFont_(
            group([child(True, "script == ")]), Font(provider)
        )


def test_projection_nil_script_policy_is_provider_owned_before_group_access():
    provider = Provider()
    with pytest.raises(ValueError, match="nil"):
        manager(provider).filterGroup_forFont_(None, Font(provider, [None]))
    # Retained C has no cleanup-unlock in this exception branch.
    assert provider.events == ["lock", ("kvc", "script"), ("set", (None,))]


def test_projection_partial_fixed_base_setter_order_and_original_reparenting(
    monkeypatch,
):
    provider = Provider()

    class Derived(SidebarItem):
        pass

    old = Derived()
    old._provider = provider
    kept, removed = child(False), child(True)
    old.setSubItems_([kept, removed])
    old.name, old.identifier, old.coverage = "name", "id", ["A"]
    old.iconName, old.predicate, old.preset, old.itemType = "icon", object(), True, 7
    old.codes, old.badgeString, old.editable, old.count = (
        ["0041"],
        "unrelated",
        True,
        27,
    )
    events = []
    methods = [
        "setName_",
        "setIdentifier_",
        "setCoverage_",
        "setIconName_",
        "setPredicate_",
        "setPreset_",
        "setItemType_",
        "setSubItems_",
    ]
    for method in methods:
        real = getattr(SidebarItem, method)

        def capture(self, value, method=method, real=real):
            events.append(method)
            return real(self, value)

        monkeypatch.setattr(SidebarItem, method, capture)
    result = manager(provider).filterGroup_forFont_(old, Font(provider))
    assert type(result) is SidebarItem
    assert events == methods
    assert result.subItems == [kept] and result.subItems[0] is kept
    assert kept.parent is result and removed.parent is old
    assert result.coverage is old.coverage and result.preset is old.preset
    assert (result.codes, result.badgeString, result.editable, result.count) == (
        None,
        None,
        False,
        -1,
    )
    assert provider.pending == [(result, 10_000_000)]


def test_categories_preserve_encounter_order_formats_reverse_compare_and_parents():
    provider = Provider()
    rows = [
        SimpleNamespace(category=None, subCategory="z"),
        SimpleNamespace(category="A", subCategory="a"),
        SimpleNamespace(category="", subCategory="x"),
        SimpleNamespace(category="B", subCategory=None),
        SimpleNamespace(category="A", subCategory="z"),
        SimpleNamespace(category="A", subCategory="a"),
        SimpleNamespace(category="B", subCategory=""),
    ]
    result = manager(provider).categoriesFromFont_categoryToIconMapping_(
        Font(provider, rows=rows), {"Other": None, "A": "", "B": "bee"}
    )
    assert [item.name for item in result] == ["Other", "A", "B"]
    assert [item.identifier for item in result] == ["Other", "A", "B"]
    assert [item.iconName for item in result] == ["Other", "", "bee"]
    assert [item.cellType for item in result] == ["ImageTextCell"] * 3
    assert [(i.predicate.predicateFormat, i.predicate.arguments) for i in result] == [
        ("category == NULL", ()),
        ("category == %@", ("A",)),
        ("category == %@", ("B",)),
    ]
    assert [
        [c.name for c in i.subItems] if i.subItems is not None else None for i in result
    ] == [["z", "x"], ["z", "a"], None]
    assert [
        (c.predicate.predicateFormat, c.predicate.arguments) for c in result[0].subItems
    ] == [
        ("category == NULL AND subCategory == %@", ("z",)),
        ("category == NULL AND subCategory == %@", ("x",)),
    ]
    assert [
        (c.predicate.predicateFormat, c.predicate.arguments) for c in result[1].subItems
    ] == [
        ("category == %@ AND subCategory == %@", ("A", "z")),
        ("category == %@ AND subCategory == %@", ("A", "a")),
    ]
    assert all(c.parent is i for i in result for c in i.subItems or ())
    assert not any(e == "lock" for e in provider.events)
    assert provider.pending == []


def test_categories_empty_font_returns_fresh_mutable_array_without_dependencies():
    value = manager(object())
    a = value.categoriesFromFont_categoryToIconMapping_(
        SimpleNamespace(glyphs=[]), None
    )
    b = value.categoriesFromFont_categoryToIconMapping_(
        SimpleNamespace(glyphs=[]), None
    )
    assert a == b == [] and a is not b


@pytest.mark.parametrize("mapping", [None, {}])
def test_category_mapping_once_captures_first_receiver_and_preserves_nil(
    mapping, monkeypatch
):
    from fontlab_glyport.glyphsapp import info_sidebar_dynamic as dynamic

    monkeypatch.setattr(dynamic, "_mapping_ready", False)
    monkeypatch.setattr(dynamic, "_category_mapping", None)
    provider = Provider()
    provider.mapping = mapping
    icon = "owned icon"

    class First(GSGlyphsInfo):
        @classmethod
        def defaultCategoriesDicts(cls):
            provider.events.append(("categories", cls))
            return [
                {"id": "WRONG", "name": "A", "icon": "old"},
                {"name": "A", "icon": icon},
                {"name": "", "icon": "ignored"},
                {"name": "B", "icon": ""},
            ]

    class Later(GSGlyphsInfo):
        @classmethod
        def defaultCategoriesDicts(cls):
            pytest.fail("once receiver changed")

    with using_info_provider(provider):
        actual = First.categoryToIconMapping()
    with using_info_provider(object()):
        assert Later.categoryToIconMapping() is actual
    assert actual is mapping
    if actual is not None:
        assert actual == {"A": icon} and actual["A"] is icon
    assert provider.events == [
        ("resource", "category2Icon", "plist"),
        ("dictionary", "owned:category2Icon"),
        ("categories", First),
    ]


@pytest.mark.parametrize("first,second", [(0, 0), (3, 3), (3, 0), (0, 3)])
@pytest.mark.parametrize(
    "nil_all,nil_category", [(False, False), (True, False), (False, True), (True, True)]
)
def test_tree_two_font_reads_nil_prefix_dynamic_dispatch_and_duplicates(
    first, second, nil_all, nil_category
):
    provider = Provider()
    dynamic_rows, language = [], object()

    class Manager(GSGlyphsInfo):
        @classmethod
        def categoryToIconMapping(cls):
            provider.events.append("mapping")
            return provider.mapping

        def categoriesFromFont_categoryToIconMapping_(self, font, mapping):
            assert mapping is provider.mapping
            provider.events.append("dynamic")
            return dynamic_rows

        def filterGroup_forFont_(self, group, font):
            assert group is self._lifecycle.languagesGroup
            provider.events.append("filter")
            return language

    value = manager(provider, Manager)
    state = value._lifecycle
    old_category = None if nil_category else object()
    state.allItem, state.categoriesGroup, state.languagesGroup = (
        None if nil_all else object(),
        old_category,
        object(),
    )
    duplicate = object()
    state.filterGroups = [duplicate, duplicate]
    second_tags = ["then-current"]
    result = value.glyphGroupsTreeForFont_(
        Font(provider, types=(first, second), tags=(["probe"], second_tags))
    )
    category = state.categoriesGroup
    expected = (
        [] if nil_all else [state.allItem] + ([] if category is None else [category])
    )
    if second != 3:
        expected += [language]
    assert result[: len(expected)] == expected
    tags = result[len(expected)]
    assert (tags.identifier, tags.name, tags.cellType) == (
        "TAGS",
        "localized:Tags",
        "TagsCell",
    )
    assert tags.coverage is second_tags and provider.pending == [(tags, 10_000_000)]
    assert result[len(expected) + 1 :] == [duplicate, duplicate]
    if first == 3:
        assert type(category) is SidebarItem and category is not old_category
        assert (
            category.identifier == "CATEGORIES"
            and category.name == "localized:Categories"
        )
        assert category.subItems is dynamic_rows
    else:
        assert category is old_category
    assert [e for e in provider.events if isinstance(e, tuple) and e[0] == "type"] == [
        ("type", first),
        ("type", second),
    ]


def test_tree_nil_language_no_tags_nil_filters():
    provider = Provider()

    class Manager(GSGlyphsInfo):
        def filterGroup_forFont_(self, group, font):
            return None

    assert manager(provider, Manager).glyphGroupsTreeForFont_(Font(provider)) == []


@pytest.mark.parametrize("returned", [None, []])
def test_reload_preserves_return_identity_and_only_changes_filter_field(returned):
    class Manager(GSGlyphsInfo):
        def loadCustomFilterGroups(self):
            return returned

    value = manager(object(), Manager)
    state = value._lifecycle
    old = object()
    state.filterGroups, state.categoriesGroup = object(), old
    assert value.reloadCustomFilterGroup() is None
    assert state.filterGroups is returned and state.categoriesGroup is old


def test_reload_exception_preserves_old_field_and_deprecated_dispatch_is_direct():
    class Manager(GSGlyphsInfo):
        def loadCustomFilterGroups(self):
            raise RuntimeError("loading failed")

        def loadSidebarInfoForDocument_(self, document):
            assert document is None
            return "owned dispatch"

    value = manager(object(), Manager)
    old = value._lifecycle.filterGroups = object()
    with pytest.raises(RuntimeError, match="loading failed"):
        value.reloadCustomFilterGroup()
    assert value._lifecycle.filterGroups is old
    assert value.loadSidebarInfo() is None


def test_missing_set_primitive_refuses_instead_of_discarding_nil():
    provider = Provider()
    with pytest.raises(UnsupportedCapability, match="set_from_array"):
        manager(object()).filterGroup_forFont_(None, Font(provider))


def test_nil_resolved_icon_folder_does_not_enumerate():
    provider = SimpleNamespace(resolve_path=lambda path: None)
    assert manager(provider).loadCustomIcons_("owned-folder") is None


def test_projection_final_count_reads_current_group_children_again():
    provider = Provider()
    kept, hidden = child(False), child(True)

    class ChangingGroup:
        reads = 0

        @property
        def subItems(self):
            self.reads += 1
            return [kept, hidden] if self.reads == 1 else [kept]

    original = ChangingGroup()
    assert manager(provider).filterGroup_forFont_(original, Font(provider)) is original
    assert original.reads == 2


def test_projection_predicate_selector_and_unqualified_string_refusal():
    provider = Provider()
    row = child(True)
    row.predicate = SimpleNamespace(predicateFormat=lambda: 'script == "latin"')
    original = group([row])
    assert (
        manager(provider).filterGroup_forFont_(original, Font(provider, ["latin"]))
        is original
    )
    row.predicate = SimpleNamespace(predicateFormat=object())
    with pytest.raises(UnsupportedCapability, match="format string"):
        manager(provider).filterGroup_forFont_(original, Font(provider))


def test_general_count_failure_retains_source_lock_state():
    provider = Provider()
    font = Font(provider)

    def fail(options, predicate):
        provider.events.append(("failing-count", options))
        raise RuntimeError("count rejected")

    font.glyphs.countOfObjectsWithOptions_matchingPredicate_ = fail
    with pytest.raises(RuntimeError, match="count rejected"):
        manager(provider).filterGroup_forFont_(
            group([child(True, "name == 'X'")]), font
        )
    assert provider.events[-2:] == ["lock", ("failing-count", 1)]


def test_categories_nil_glyph_collection_and_nil_icon_mapping():
    provider = Provider()
    value = manager(provider)
    assert (
        value.categoriesFromFont_categoryToIconMapping_(
            SimpleNamespace(glyphs=None), None
        )
        == []
    )
    rows = [SimpleNamespace(category="Owned", subCategory=None)]
    result = value.categoriesFromFont_categoryToIconMapping_(
        Font(provider, rows=rows), None
    )
    assert result[0].iconName == "Owned" and result[0].subItems is None


def test_category_map_missing_url_nil_rows_and_missing_primitive(monkeypatch):
    from fontlab_glyport.glyphsapp import info_sidebar_dynamic as dynamic

    monkeypatch.setattr(dynamic, "_mapping_ready", False)
    monkeypatch.setattr(dynamic, "_category_mapping", None)

    class Receiver(GSGlyphsInfo):
        @classmethod
        def defaultCategoriesDicts(cls):
            return None

    with (
        using_info_provider(object()),
        pytest.raises(UnsupportedCapability, match="resource_url"),
    ):
        Receiver.categoryToIconMapping()
    events = []
    provider = SimpleNamespace(
        resource_url=lambda *args: None, load_dictionary=lambda url: events.append(url)
    )
    with using_info_provider(provider):
        assert Receiver.categoryToIconMapping() is None
    assert events == [None]
    # A nil result is still a completed once operation: no provider is needed later.
    assert Receiver.categoryToIconMapping() is None


def test_category_map_skips_nil_name_and_icon_without_inventing_values(monkeypatch):
    from fontlab_glyport.glyphsapp import info_sidebar_dynamic as dynamic

    monkeypatch.setattr(dynamic, "_mapping_ready", False)
    monkeypatch.setattr(dynamic, "_category_mapping", None)
    provider = Provider()

    class Receiver(GSGlyphsInfo):
        @classmethod
        def defaultCategoriesDicts(cls):
            return [{"name": None, "icon": "x"}, {"name": "x", "icon": None}, {}]

    with using_info_provider(provider):
        assert Receiver.categoryToIconMapping() is provider.mapping
    assert provider.mapping == {"Existing": "kept"}


def test_tree_failed_header_localization_keeps_already_replaced_category():
    provider = Provider()

    def fail(title):
        raise RuntimeError("missing translation")

    provider.localize = fail
    value = manager(provider)
    old = value._lifecycle.categoriesGroup = object()
    with pytest.raises(RuntimeError, match="missing translation"):
        value.glyphGroupsTreeForFont_(Font(provider, types=(3,)))
    changed = value._lifecycle.categoriesGroup
    assert type(changed) is SidebarItem and changed is not old
    assert changed.identifier == "CATEGORIES" and changed.name is None


def test_tree_nil_second_tags_preserves_header_and_does_not_schedule_count():
    provider = Provider()

    class Manager(GSGlyphsInfo):
        def filterGroup_forFont_(self, group, font):
            return None

    result = manager(provider, Manager).glyphGroupsTreeForFont_(
        Font(provider, tags=(["first"], None))
    )
    assert len(result) == 1 and result[0].identifier == "TAGS"
    assert result[0].coverage is None and provider.pending == []


def test_tree_nil_filters_requires_explicit_array_primitive_policy():
    provider = Provider()
    provider.array_add_objects = None

    class Manager(GSGlyphsInfo):
        def filterGroup_forFont_(self, group, font):
            return None

    with pytest.raises(UnsupportedCapability, match="array_add_objects"):
        manager(provider, Manager).glyphGroupsTreeForFont_(Font(provider))


def test_connected_tree_projects_real_defaults_backed_items_and_preserves_graph():
    provider = Provider()
    value = manager(provider)
    state = value._lifecycle
    languages = SidebarItem.from_dict(
        {"name": "Languages", "id": "LANGUAGES"}, provider
    )
    latin = SidebarItem.from_dict({"name": "Latin", "id": "latin"}, provider)
    greek = SidebarItem.from_dict({"name": "Greek", "id": "greek"}, provider)
    greek.setPredicate_(SimpleNamespace(predicateFormat='script == "greek"'))
    provider.defaults["GSSidebarItemHidden_greek"] = True
    languages.setSubItems_([latin, greek])
    state.allItem, state.categoriesGroup, state.languagesGroup = (
        SidebarItem(),
        SidebarItem(),
        languages,
    )
    custom = SidebarItem()
    state.filterGroups = [custom, custom]
    result = value.glyphGroupsTreeForFont_(Font(provider, scripts=["latin"]))
    assert result[:2] == [state.allItem, state.categoriesGroup]
    projected = result[2]
    assert type(projected) is SidebarItem and projected is not languages
    assert projected.identifier == "LANGUAGES" and projected.subItems == [latin]
    assert latin.parent is projected and greek.parent is languages
    assert languages.subItems == [latin, greek]
    assert result[3:] == [custom, custom] and provider.pending == []
    reads = [
        e for e in provider.events if isinstance(e, tuple) and e[0] == "defaults-read"
    ]
    assert reads == [
        ("defaults-read", "GSSidebarItemHidden_latin"),
        ("defaults-read", "GSSidebarItemHidden_greek"),
    ]


def test_expansion_nil_new_record_preserves_old_infos_and_does_not_append_nil():
    item = SidebarItem()
    assignments = []
    item._provider = SimpleNamespace(
        sidebar_new_info=lambda: None,
        sidebar_set_info_name=lambda record, name: assignments.append((record, name)),
    )
    item.coverage = ["OwnedUnknown"]
    old = item.infos = [object()]
    with pytest.raises(InfoNativeException, match="nil"):
        item.expandNameList_(SimpleNamespace(glyphInfoForName_=lambda name: None))
    assert item.infos is old and item.coverage == ["OwnedUnknown"]
    assert assignments == [(None, "OwnedUnknown")]

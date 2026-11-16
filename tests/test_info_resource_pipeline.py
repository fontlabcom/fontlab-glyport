# this_file: tests/test_info_resource_pipeline.py
"""Lawful invented resources exercise connected sidebar/file/icon control paths."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.glyphsapp import info_sidebar_resources as resources
from fontlab_glyport.glyphsapp.info_manager import GSGlyphsInfo
from fontlab_glyport.glyphsapp.info_runtime import InfoState, using_info_provider


class Provider:
    def __init__(self):
        self.events = []
        self.arrays = {
            "defaultCategories": [],
            "defaultLanguages": [],
            "StandardFilter": [],
        }
        self.paths = {}
        self.files = {}
        self.user = "user"
        self.supports = ["system", "user"]

    def localize(self, text):
        return text

    def compare(self, a, b):
        return (a > b) - (a < b)

    def trim_whitespace(self, value):
        """Owned ASCII filenames only; not the Foundation character set."""
        return value.strip(" \t")

    def register_defaults(self, data):
        self.events.append(("defaults", data))

    def resource_url(self, name, extension):
        self.events.append(("resource", name))
        return name

    def load_array(self, url):
        self.events.append(("array", url))
        return self.arrays.get(url)

    def application_support_paths(self):
        return self.supports

    def user_support_path(self):
        return self.user

    def directory_entries(self, path):
        self.events.append(("directory", path))
        return self.paths.get(path, [])

    def resolve_path(self, path):
        self.events.append(("resolve", path))
        return path

    def load_property_list(self, path):
        self.events.append(("plist", path))
        return self.files.get(path, (None, None))

    def schedule(self, delay, callback):
        self.events.append(("scheduled", delay, callback))

    def present_error(self, error):
        self.events.append(("error", error))

    def log(self, value):
        self.events.append(("log", value))


@pytest.fixture(autouse=True)
def reset_resource_once(monkeypatch):
    monkeypatch.setattr(resources, "_once_arrays", {})


def manager(provider):
    value = GSGlyphsInfo.alloc()
    value._lifecycle = InfoState(provider, None)
    value._fixed_index = value._lifecycle.index
    value._lifecycle.name2Group = {}
    value._lifecycle.sidebarCategories = []
    value._lifecycle.categories = []
    value._lifecycle.subCategories = []
    value._lifecycle.scriptIDs = []
    return value


def test_real_sidebar_callback_processes_owned_groups_languages_ranks_and_filters():
    provider = Provider()
    provider.arrays.update(
        defaultCategories=[
            {
                "name": "Numbers",
                "id": "Number",
                "subGroup": [{"name": "Owned", "id": "Fleet"}],
            }
        ],
        defaultLanguages=[
            {"name": "Zulu", "id": "Z"},
            {"name": "Alpha", "id": "A", "visible": True},
        ],
    )
    value = manager(provider)
    jobs = []
    value._lifecycle.queue = SimpleNamespace(addOperationWithBlock_=jobs.append)
    resources.initialize_sidebar(value)
    state = value._lifecycle
    assert len(jobs) == 1 and state.categoriesGroup is None
    assert state.allItem.identifier == "All"
    assert state.allItem.iconName == "LibraryTemplate"
    jobs.pop()()
    assert [row.identifier for row in state.languagesGroup.subItems] == ["A", "Z"]
    assert state.subCategoryOrder["Number"]["Fleet"] == 0
    assert state.subCategoryOrder["Number"]["Decimal Digit_TOST"] == 5
    assert state.sidebarCategories == ["Number", "Z", "A", "Corner", "SmartGlyph"]
    assert state.name2Group["Number/Fleet"].parent is state.name2Group["Number"]
    assert ("defaults", {"GSSidebarItemHidden_Z": True}) in provider.events
    assert state.filterGroups[0].identifier == "FILTERS"


def test_process_once_keeps_nil_and_does_not_reload_through_another_provider():
    provider = Provider()
    provider.arrays["defaultCategories"] = None
    assert resources.default_array(provider, "defaultCategories") is None
    provider.arrays["defaultCategories"] = [{"name": "late"}]
    another = Provider()
    assert resources.default_array(another, "defaultCategories") is None
    assert provider.events == [
        ("resource", "defaultCategories"),
        ("array", "defaultCategories"),
    ]
    assert another.events == []


def test_broken_groups_preserves_prior_mutations_and_stops_folder_only():
    provider = Provider()
    provider.paths = {
        "first": ["GroupsA.plist", "GroupsBad.plist", "GroupsLater.plist"],
        "second": ["GroupsNext.plist"],
    }
    provider.files = {
        "first/GroupsA.plist": ({"categories": [{"name": "A"}]}, None),
        "first/GroupsBad.plist": (None, "owned-error"),
        "first/GroupsLater.plist": ({"categories": [{"name": "Skipped"}]}, None),
        "second/GroupsNext.plist": ({"languages": [{"name": "B"}]}, None),
    }
    value = manager(provider)
    from fontlab_glyport.glyphsapp.info_sidebar import SidebarItem

    value._lifecycle.categoriesGroup = SidebarItem()
    value._lifecycle.categoriesGroup.subItems = []
    value._lifecycle.languagesGroup = SidebarItem()
    value._lifecycle.languagesGroup.subItems = []
    value.loadCustomGroupsFromFolder_("first")
    value.loadCustomGroupsFromFolder_("second")
    assert "A" in value._lifecycle.name2Group and "B" in value._lifecycle.name2Group
    assert "Skipped" not in value._lifecycle.name2Group
    scheduled = [e for e in provider.events if e[0] == "scheduled"]
    assert len(scheduled) == 1 and scheduled[0][1] == 0.1
    scheduled[0][2]()
    assert provider.events[-1] == ("error", "owned-error")


@pytest.mark.parametrize(
    "primary,standard_url,expected_names",
    [
        ([], None, ["FILTERS"]),
        (None, None, None),
        (None, "StandardFilter", ["FILTERS"]),
    ],
)
def test_primary_empty_suppresses_fallback_and_missing_resource_url_stops_extras(
    primary, standard_url, expected_names
):
    from fontlab_glyport.glyphsapp.info_filters import load_filters

    provider = Provider()
    provider.files["user/CustomFilter.plist"] = (primary, None)
    provider.resource_url = lambda name, extension: standard_url
    value = manager(provider)
    result = load_filters(value)
    assert (
        None if result is None else [x.identifier for x in result]
    ) == expected_names
    if expected_names is None:
        assert not any(e[0] == "directory" for e in provider.events)
    else:
        assert [e[1] for e in provider.events if e[0] == "directory"] == [
            "system",
            "system/Filters",
            "user",
            "user/Filters",
        ]


def test_extra_filters_retain_order_empty_headers_source_paths_and_editable_tree():
    from fontlab_glyport.glyphsapp.info_filters import load_filters

    provider = Provider()
    provider.files["user/CustomFilter.plist"] = ([], None)
    provider.paths["system"] = [
        "CustomFilter Z.plist",
        "CustomFilter.plist",
        "CustomFilterBad.plist",
    ]
    provider.paths["user"] = ["CustomFilter.plist"]
    provider.paths["local"] = ["CustomFilter A.plist"]
    provider.files.update(
        {
            "system/CustomFilter Z.plist": ([], None),
            "system/CustomFilter.plist": (
                [{"name": "Child", "subGroup": [{"name": "Grandchild"}]}],
                None,
            ),
            "local/CustomFilter A.plist": ([], None),
        }
    )
    value = manager(provider)
    value._lifecycle.localURL = SimpleNamespace(path=lambda: "local")
    result = load_filters(value)
    assert [x.name for x in result] == ["Filters", "Z", "Custom", "A"]
    assert (
        result[1].subItems == [] and result[1].filePath == "system/CustomFilter Z.plist"
    )
    assert result[2].subItems[0].editable and result[2].subItems[0].subItems[0].editable
    assert [
        e for e in provider.events if e[:2] == ("plist", "user/CustomFilter.plist")
    ] == [("plist", "user/CustomFilter.plist")]


def test_icons_use_original_filename_resolved_type_and_skip_2x_registration():
    from fontlab_glyport.glyphsapp.info_images import load_icons

    provider = Provider()
    provider.paths["resolved"] = [
        "FleetTemplate.png",
        "Fleet@2x.png",
        "Text.txt",
        "Broken.png",
    ]
    provider.resolve_path = lambda p: (
        "resolved" if p == "alias" else "target/" + p.rsplit("/", 1)[-1]
    )
    provider.is_image = lambda p: p.endswith(".png")
    events = []
    image = SimpleNamespace(
        setName_=lambda n: events.append(("name", n)),
        setTemplate_=lambda v: events.append(("template", v)),
    )
    provider.load_image = lambda p: (
        events.append(("image", p)) or (None if p.endswith("Broken.png") else image)
    )
    load_icons(manager(provider), "alias")
    assert events == [
        ("image", "target/FleetTemplate.png"),
        ("name", "FleetTemplate"),
        ("template", True),
        ("image", "target/Broken.png"),
    ]


def test_global_icon_helper_requires_drawn_image_provider_and_registers_real_handle():
    from fontlab_glyport.glyphsapp.info_images import load_global_icons

    provider = Provider()
    events = []
    provider.draw_emoji_icon = lambda w, h, flipped: (
        events.append((w, h, flipped))
        or SimpleNamespace(setName_=lambda n: events.append(n))
    )
    provider.is_image = lambda p: False
    value = manager(provider)
    assert load_global_icons(value) is True
    assert events == [(17, 17, True), "GSEmojiIcon"]
    assert ("directory", "user/Info/Icons") in provider.events


def test_actual_local_constructor_transitively_initializes_shared_parser_sidebar_and_resources(
    monkeypatch, tmp_path
):
    """No preseeded shared manager; both constructors use their real call chains."""
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    base = tmp_path / "base.xml"
    base.write_text(
        '<glyph name="owned.base" unicode="0041" script="owned" subCategory="Base"/>'
    )
    folder = tmp_path / "font"
    folder.mkdir()
    (folder / "GlyphData.xml").write_text(
        '<glyph name="owned.local" unicode="0042" script="fleet" subCategory="Local"/>'
    )
    provider = Provider()
    provider.supports = []
    provider.arrays["defaultCategories"] = [{"name": "Owned category", "id": "Owned"}]
    queues, observers = [], []

    class Queue:
        def __init__(self):
            self.pending = []

        def setMaxConcurrentOperationCount_(self, count):
            self.maxConcurrentOperationCount = count

        def addOperationWithBlock_(self, action):
            self.pending.append(action)

        def waitUntilAllOperationsAreFinished(self):
            provider.events.append(("wait", self))
            while self.pending:
                self.pending.pop(0)()

    def queue():
        value = Queue()
        queues.append(value)
        return value

    def resource(name, extension):
        if name == "GlyphData":
            return SimpleNamespace(path=lambda: str(base))
        return name

    provider.new_queue = queue
    provider.active_processor_count = lambda: 2
    provider.resource_url = resource
    provider.load_dictionary = lambda url: {"owned": "matra"}
    provider.is_image = lambda path: False
    provider.draw_emoji_icon = lambda w, h, f: SimpleNamespace(
        setName_=lambda n: provider.events.append(("registered", n))
    )
    provider.notify = lambda obj, phase, key: provider.events.append((phase, key))
    provider.add_observer = lambda *args: observers.append(args)

    # All real generation jobs execute. Only their four private-bank inputs are
    # replaced with these explicit invented Unicode lists; no job is a no-op.
    banks = (("2FF0",), ("20000",), ("20001",), ("20002",))
    provider.chinese_codes = lambda slot: banks[slot]
    provider.distinct_values = lambda rows, field: list(
        dict.fromkeys(
            getattr(row, field) for row in rows if getattr(row, field) is not None
        )
    )
    url = SimpleNamespace(path=lambda: str(folder))
    with using_info_provider(provider):
        local = GSGlyphsInfo.alloc().initWithLocalFile_(url)
    shared = GSGlyphsInfo._shared
    assert shared is not local and shared._lifecycle.shared
    assert not local._lifecycle.shared and local._lifecycle.localURL is url
    assert shared._index.raw_name("owned.base").unicode == "0041"
    assert local._index.raw_name("owned.local").unicode == "0042"
    assert local._index.raw_name("owned.base") is shared._index.raw_name("owned.base")
    assert local._lifecycle.categoriesGroup.identifier == "CATEGORIES"
    assert local._lifecycle.filterGroups[0].identifier == "FILTERS"
    assert (
        local._lifecycle.iMatraCombinations
        == shared._lifecycle.iMatraCombinations
        == {"owned": "matra"}
    )
    assert local._lifecycle.name2Group["Owned"].name == "Owned category"
    assert (
        "owned" in local._lifecycle.scriptIDs and "fleet" in local._lifecycle.scriptIDs
    )
    assert [row.index for row in local._index.records] == [0]
    assert observers == [(shared, "values.GSScriptToPlaceholderFontPath", 0, None)]
    assert len(queues) == 2 and not any(q.pending for q in queues)


def test_extra_filename_title_does_not_request_localization():
    from fontlab_glyport.glyphsapp.info_filters import extra_filters

    provider = Provider()
    provider.paths["owned"] = ["CustomFilter Fleet.plist"]
    provider.files["owned/CustomFilter Fleet.plist"] = ([], None)
    provider.localize = lambda text: pytest.fail(
        "Filename title must remain unlocalized"
    )
    assert extra_filters(manager(provider), "owned")[0].name == "Fleet"


def test_sidebar_uses_dynamic_class_defaults_and_self_rank_rebuild():
    provider = Provider()
    supplied = [{"name": "Subtype defaults", "id": "Subtype"}]
    calls = []

    class Subtype(GSGlyphsInfo):
        @classmethod
        def defaultCategoriesDicts(cls):
            calls.append(("default", cls))
            return supplied

        def _loadSubcategories(self):
            calls.append(("rank", self))
            self._lifecycle.subCategoryOrder = {"owned": "subtype"}

    value = Subtype.alloc()
    value._lifecycle = manager(provider)._lifecycle
    jobs = []
    value._lifecycle.queue = SimpleNamespace(addOperationWithBlock_=jobs.append)
    resources.initialize_sidebar(value)
    jobs.pop()()
    assert calls == [("default", Subtype), ("rank", value)]
    assert value._lifecycle.categoriesGroup.subItems[0].identifier == "Subtype"
    assert value._lifecycle.subCategoryOrder == {"owned": "subtype"}
    resources.build_sidebar(value)
    assert calls == [("default", Subtype), ("rank", value), ("default", Subtype)]


def test_reinitializing_legacy_shared_retains_shared_flag(monkeypatch):
    """A local initializer does not clear an existing shared receiver's flag."""
    from test_info_local_pipeline import URL, Local
    from test_info_local_pipeline import Provider as LocalProvider

    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    shared = Local.alloc().init()
    assert shared is GSGlyphsInfo._shared
    provider = LocalProvider()
    with using_info_provider(provider):
        assert shared.initWithLocalFile_(URL(None)) is shared
    assert shared._lifecycle.shared

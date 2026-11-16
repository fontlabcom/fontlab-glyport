# this_file: src/fontlab_glyport/glyphsapp/info_manager.py
"""Document-selected Glyph Info services over owned public/custom record graphs.

Automatic resource discovery/local initialization remains a separate capability.
This manager makes no FontLab/Glyphs or native-framework requests.
"""

from ..errors import UnsupportedCapability
from ..model.info_source import selected_index
from ..model.proxies import _Explicit
from .info_loading import _url_path
from .info_manager_accessors import ManagerAccessors
from .info_manager_observation import ManagerObservation
from .info_shared import initialize_shared as _initialize_shared
from .info_shared import shared_manager as _shared_manager


class GSGlyphsInfo(ManagerAccessors, ManagerObservation, _Explicit):
    _shared = None

    def __new__(cls):
        return cls.alloc().init()

    @classmethod
    def alloc(cls):
        """Allocate only; the retained plain initializer returns the singleton."""
        return object.__new__(cls)

    def init(self):
        return _initialize_shared(self)

    def initDebug(self):
        from .info_debug import initialize_debug

        return initialize_debug(self)

    def initWithLocalFile_(self, url):
        return self.initWithLocalFile_forFont_(url, None)

    def initWithLocalFile_forFont_(self, url, document):
        from .info_lifecycle import initialize_local

        return initialize_local(self, url, document)

    def loadGlyphInfo(self):
        from .info_lifecycle import load_info

        return load_info(self)

    def loadGlyphDataError_(self, error):
        from .info_lifecycle import load_data

        return load_data(self, error)

    def loadGlyphDataFromURL_error_(self, url, error):
        from .info_lifecycle import load_base

        return load_base(self, url, error)

    def loadSidebarInfoForDocument_(self, document):
        if document is not None and document.fontType() == 3:
            return self.loadSidebarInfoForIconSet_(document)
        return self.loadSidebarInfoForFont_(document)

    def loadSidebarInfoForIconSet_(self, document):
        """Icon sets have no sidebar info: this does nothing."""

    def loadSidebarInfoForFont_(self, document):
        from .info_sidebar_resources import initialize_sidebar

        return initialize_sidebar(self)

    @classmethod
    def defaultCategoriesDicts(cls):
        from .info_runtime import require_provider
        from .info_sidebar_resources import default_array

        return default_array(require_provider(), "defaultCategories")

    def _loadSubcategories(self):
        from .info_runtime import state_for
        from .info_sidebar import load_subcategories

        return load_subcategories(state_for(self))

    def loadCustomGroupsFromFolder_(self, path):
        from .info_sidebar_resources import load_groups_folder

        return load_groups_folder(self, path)

    def loadCustomFilterGroups(self):
        from .info_filters import load_filters

        return load_filters(self)

    def loadSidebarInfo(self):
        self.loadSidebarInfoForDocument_(None)

    def reloadCustomFilterGroup(self):
        self.setFilterGroups_(self.loadCustomFilterGroups())

    def filterGroup_forFont_(self, group, font):
        from .info_sidebar_dynamic import filter_group

        return filter_group(self, group, font)

    def categoriesFromFont_categoryToIconMapping_(self, font, mapping):
        from .info_sidebar_dynamic import categories_from_font

        return categories_from_font(self, font, mapping)

    @classmethod
    def categoryToIconMapping(cls):
        from .info_sidebar_dynamic import category_mapping

        return category_mapping(cls)

    def glyphGroupsTreeForFont_(self, font):
        from .info_sidebar_dynamic import groups_tree

        return groups_tree(self, font)

    def _loadCustomFilterGroupForPath_(self, path):
        from .info_filters import extra_filters

        return extra_filters(self, path)

    def loadCustomIcons_(self, path):
        from .info_images import load_icons

        return load_icons(self, path)

    def loadCustomIcons(self):
        from .info_images import load_global_icons

        return load_global_icons(self)

    def _addChineseGlyphInfos(self):
        from .info_chinese import add_chinese

        return add_chinese(self)

    def _addChinese_end_subCategory_sortPrefix_infos_unicode2Info_(
        self, start, end, sub_category, sort_prefix, infos, unicode_index
    ):
        from .info_chinese import add_range

        return add_range(start, end, sub_category, sort_prefix, infos, unicode_index)

    def _addChinese_subCategory_sortPrefix_infos_unicode2Info_(
        self, codes, sub_category, sort_prefix, infos, unicode_index
    ):
        from .info_chinese import add_codes

        return add_codes(codes, sub_category, sort_prefix, infos, unicode_index)

    def _addHangulGlyphInfos(self):
        from .info_generated import add_hangul

        return add_hangul(self)

    def willChangeValueForKey_(self, key):
        from .info_runtime import provider_method, state_for

        provider_method(state_for(self).provider, "notify")(self, "will", key)

    def didChangeValueForKey_(self, key):
        from .info_runtime import provider_method, state_for

        provider_method(state_for(self).provider, "notify")(self, "did", key)

    @classmethod
    def new(cls):
        return cls.alloc().init()

    @classmethod
    def sharedManager(cls):
        return _shared_manager()

    @classmethod
    def _from_index(cls, index):
        """Owned source fixture seam; not a claimed upstream manager setter."""
        result = object.__new__(cls)
        result._fixed_index = index
        return result

    @property
    def _index(self):
        if "_fixed_index" not in vars(self):
            raise UnsupportedCapability(
                "Glyph Info manager has not been initialized",
                capability="GSGlyphsInfo.initialization",
            )
        if self._fixed_index is not None:
            return self._fixed_index
        from .glyph_info import glyph_categories

        glyph_categories("", [])  # Preserve the typed dependency boundary.
        from glyphsLib import glyphdata

        from ..model.public_info_index import PublicInfoIndex

        data = glyphdata.GLYPHDATA
        if data not in self._public_indexes:
            self._public_indexes[data] = PublicInfoIndex(data)
        return self._public_indexes[data]

    def _scope(self):
        return selected_index(self._index)

    @staticmethod
    def applicationSupportPath():
        from .defaults import default_defaults_path

        return str(default_defaults_path().parent)

    @staticmethod
    def _view(record):
        from .glyph_info import GSGlyphInfo

        return None if record is None else GSGlyphInfo.from_record(record)

    def infoFromDataForName_(self, name):
        return self._view(self._index.raw_name(name))

    def infoFromDataForUnicode_(self, code):
        return self._view(self._index.raw_unicode(code))

    def infoFromDataForUnicodes_(self, codes):
        return self._view(self._index.raw_unicodes(codes))

    def glyphInfoForName_(self, name):
        if name is None or name == "":
            return None
        if type(name) is not str:
            raise UnsupportedCapability(
                "Unqualified name bridge input",
                capability="GSGlyphsInfo.name.inputType",
            )
        from ..model.glyph_metadata import name_info

        with self._scope():
            return self._view(name_info(name, fill_production=True))

    def glyphInfoForUnicode_(self, code):
        # Preserve existing UTF16/type checks without re-entering a global lookup.
        from .glyph_info import checked_unicode_code

        code = checked_unicode_code(code)
        if code is None:
            return None
        from ..model.glyph_metadata import unicode_info

        with self._scope():
            return self._view(unicode_info(code))

    def glyphInfoForUnicodes_(self, codes):
        for code in codes:
            result = self.glyphInfoForUnicode_(code)
            if result is not None:
                return result
        return None

    def glyphInfoForGlyph_(self, glyph):
        if "_draft" not in glyph.__dict__:
            glyph._check()
        from ..model.glyph_metadata import resolve

        with self._scope():
            return self._view(resolve(glyph))

    def loadCustomGlyphDataFromURL_error_(self, url, error):
        """Load one qualified regular file; raw ^@ null input returns bool only.

        This source-supported default profile does not establish effective native
        metadata overrides, arbitrary pointer wrappers or NSError output slots.
        The internal owned error record is not presented as a native NSError.
        """
        from ..model.custom_info_loading import load_custom_file
        from .info_runtime import error_slot

        slot = error_slot(error)
        path = _url_path(url)
        failure = load_custom_file(self._index, path)
        if failure is not None and slot is not None:
            slot.value = failure
        return failure is None

    def loadLocalGlyphInfoFiles_error_(self, urls, error):
        """Preserve input order/duplicates, completed rows and first-failure stop."""
        from .info_runtime import error_slot

        error_slot(error)
        if urls is None:
            return True
        for url in urls:
            if not self.loadCustomGlyphDataFromURL_error_(url, error):
                return False
        return True

    def updateComponentsInfos(self):
        """Finalize this graph; private resource-derived fields stay unavailable."""
        from ..model.info_finalize import finalize_info

        def lookup(name):
            info = self.glyphInfoForName_(name)
            return None if info is None else info._resolved_record

        index = self._index
        index.prepare_custom_merge()  # Lazy public rows must retain source order.
        with selected_index(index):
            finalize_info(index, lookup)

    @classmethod
    def foldersForCustomInfoForFolder_(cls, folder):
        """Compose canonical POSIX candidates, keeping file inputs and repeats."""
        from os.path import expanduser

        from ..model.custom_info_discovery import candidate_folders

        return candidate_folders(folder, home=expanduser("~"))

    @classmethod
    def findCustomGlyphDataInFolder_(cls, folder):
        """Qualified macOS provider; Foundation order/alias parity stays held."""
        from ..model.custom_info_discovery import discover_folder
        from ..model.custom_info_filesystem import directory_entries, resolve_symlinks
        from ..ui.cocoa_controls import NSURL

        with directory_entries(folder) as entries:
            return discover_folder(
                folder,
                entries=lambda path: entries,
                resolve=resolve_symlinks,
                make_url=NSURL.fileURLWithPath_,
            )

    @classmethod
    def findLocalGlyphInfoFolders_(cls, folders):
        """Find URLs in a supplied folder array, preserving receiver dispatch."""
        from ..model.custom_info_discovery import discover_local

        return discover_local(folders, find_in_folder=cls.findCustomGlyphDataInFolder_)

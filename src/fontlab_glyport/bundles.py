# this_file: src/fontlab_glyport/bundles.py
"""Read-only NSBundle resource lookup for source plugins, without Cocoa.

Referenced by glyphsapp.fontlab_session: each context gets its own bundle
registry. Native application/framework loading remains an explicit capability
error; no FontLab application bundle is presented as Glyphs' application.
Resource lookup is exact and unlocalized: language selection and .lproj
fallbacks are not emulated. Localized selectors remain unsupported.
"""

import plistlib
import sys
from pathlib import Path
from typing import Any
from xml.parsers.expat import ExpatError

from ._strict import caller_location
from .errors import NativeOperationError, UnsupportedAttribute
from .ui.cocoa import NSObject, unsupported

_SUFFIXES = {
    ".bundle",
    ".app",
    ".framework",
    ".glyphsPlugin",
    ".glyphsReporter",
    ".glyphsFilter",
    ".glyphsPalette",
    ".glyphsTool",
    ".glyphsFileFormat",
}
_SUFFIXES = {suffix.casefold() for suffix in _SUFFIXES}


def _containing_bundle(path: Path) -> Path | None:
    """Find a source plugin's bundle, starting at a module or source root."""
    for parent in (path, *path.parents):
        if parent.suffix.casefold() in _SUFFIXES and parent.is_dir():
            return parent
    return None


class _InfoDictionary(dict):
    def objectForKey_(self, key: str) -> Any:
        return self.get(key)


class _BundleType(type):
    def __getattr__(cls, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        raise _missing(name)


def _missing(name: str) -> UnsupportedAttribute:
    return UnsupportedAttribute(
        f"Unsupported capability: NSBundle.{name}",
        capability=f"NSBundle.{name}",
        location=caller_location(),
    )


def bundle_class(source_root: str | Path | None) -> type:
    """Bind NSBundle's source-plugin lookup and registry to one context."""
    root = None if source_root is None else Path(source_root).absolute()
    bundles: dict[Path, Any] = {}

    class NSBundle(NSObject, metaclass=_BundleType):
        @classmethod
        def bundleWithPath_(cls, path: str | Path):
            path = Path(path).absolute()
            if not path.is_dir():
                return None
            if path not in bundles:
                bundle = cls.alloc()
                bundle._path = path
                bundles[path] = bundle
            return bundles[path]

        @classmethod
        def bundleForClass_(cls, target: type):
            # ExecutionContext runs its entry point as __main__ in owned
            # globals, without replacing the host's sys.modules["__main__"].
            module = sys.modules.get(target.__module__)
            filename = (
                root
                if target.__module__ == "__main__"
                else getattr(module, "__file__", None)
            )
            path = None if filename is None else _containing_bundle(Path(filename))
            if path is None:
                raise unsupported("NSBundle.bundleForClass_")
            return cls.bundleWithPath_(path)

        @classmethod
        def bundleWithIdentifier_(cls, identifier: str):
            path = None if root is None else _containing_bundle(root)
            if path is not None:
                cls.bundleWithPath_(path)
            return next(
                (b for b in bundles.values() if b.bundleIdentifier() == identifier),
                None,
            )

        @classmethod
        def mainBundle(cls):
            """No Glyphs executable bundle exists in this source-bundle adapter.

            Returning the plugin's source bundle would misidentify the host and
            expose incorrect executable/resources metadata.
            """
            raise unsupported("NSBundle.mainBundle")

        def bundlePath(self) -> str:
            return str(self._path)

        def resourcePath(self) -> str:
            for relative in ("Contents/Resources", "Resources"):
                path = self._path / relative
                if path.is_dir():
                    return str(path)
            return str(self._path)

        def infoDictionary(self) -> dict | None:
            for relative in ("Contents/Info.plist", "Info.plist"):
                path = self._path / relative
                if not path.is_file():
                    continue
                try:
                    with path.open("rb") as stream:
                        info = plistlib.load(stream)
                    if not isinstance(info, dict):
                        raise TypeError("Bundle Info.plist must contain a dictionary")
                except (OSError, TypeError, ValueError, ExpatError) as error:
                    raise NativeOperationError(
                        f"Cannot read bundle Info.plist: {error}",
                        capability="NSBundle.infoDictionary",
                    ) from error
                return _InfoDictionary(info)
            return None

        def bundleIdentifier(self) -> str | None:
            info = self.infoDictionary()
            return None if info is None else info.get("CFBundleIdentifier")

        def objectForInfoDictionaryKey_(self, key: str) -> Any:
            """Unlocalized Info.plist value; .lproj selection is unsupported."""
            info = self.infoDictionary()
            return None if info is None else info.get(key)

        def pathForResource_ofType_(self, name: str, extension: str | None):
            return self.pathForResource_ofType_inDirectory_(name, extension, None)

        def pathForResource_ofType_inDirectory_(
            self, name: str, extension: str | None, directory: str | None
        ) -> str | None:
            if not name:
                raise unsupported("NSBundle.pathForResource.emptyName")
            filename = str(name) + (f".{extension}" if extension else "")
            if Path(directory or "").is_absolute() or Path(filename).is_absolute():
                raise ValueError("Bundle resource paths must be relative")
            path = (Path(self.resourcePath()) / (directory or "") / filename).resolve()
            if not path.is_relative_to(self._path.resolve()):
                raise ValueError("Resource path escapes the bundle")
            return str(path) if path.exists() else None

        def __getattr__(self, name: str) -> Any:
            if name.startswith("__"):
                raise AttributeError(name)
            raise _missing(name)

    return NSBundle

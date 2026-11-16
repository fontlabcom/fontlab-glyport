# this_file: src/fontlab_glyport/model/custom_info_discovery.py
"""Pure, ordered custom-info discovery over explicit provider boundaries.

Qualified paths are canonical absolute POSIX strings. Providers supply platform
enumeration (skipping hidden files, package contents and subfolders),
alias/symlink resolution and URL construction;
this module does not claim Foundation filesystem or arbitrary NSString parity.
"""

from collections.abc import Callable, Iterable
from posixpath import dirname, join, normpath
from typing import TypeVar

from ..errors import UnsupportedCapability

URL = TypeVar("URL")


def _qualified_path(path: str) -> str:
    """Refuse paths requiring normalization or platform-specific conversion."""
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or path.startswith("//")
        or "\0" in path
        or any(0xD800 <= ord(char) <= 0xDFFF for char in path)
        or normpath(path) != path
    ):
        raise UnsupportedCapability(
            "Custom-info discovery requires canonical absolute POSIX path strings",
            capability="GSGlyphsInfo.discovery.path",
        )
    return path


def candidate_folders(path: str, *, home: str) -> list[str]:
    """The folder, its Info folder, the parent and its Info folder, in that
    order and without deduplication (the parent pair is omitted at home).

    POSIX root has itself as parent; repeated root candidates remain present.
    Home is supplied explicitly, already expanded, without reading process state.
    """
    _qualified_path(path)
    _qualified_path(home)
    parent = dirname(path)
    folders = [path, join(path, "Info")]
    if parent != home:
        folders.extend([parent, join(parent, "Info")])
    return folders


def is_glyph_data_name(name: str) -> bool:
    """``GlyphData.xml``, or ``GlyphData_*.xml`` (case-sensitive)."""
    if not isinstance(name, str):
        raise UnsupportedCapability(
            "Custom-info entry names require strings",
            capability="GSGlyphsInfo.discovery.name",
        )
    return name == "GlyphData.xml" or (
        name.startswith("GlyphData_") and name.endswith(".xml")
    )


def discover_folder(
    path: str,
    *,
    entries: Callable[[str], Iterable[str] | None],
    resolve: Callable[[str], str | None],
    make_url: Callable[[str], URL | None],
) -> list[URL] | None:
    """Filter before resolution, preserving nil, order and duplicate URLs.

    Provider exceptions escape immediately; earlier provider effects remain.
    """
    enumerator = entries(_qualified_path(path))
    if enumerator is None:
        return None
    urls = []
    for entry in enumerator:
        _qualified_path(entry)
        if not is_glyph_data_name(entry.rsplit("/", 1)[-1]):
            continue
        resolved = resolve(entry)
        if resolved is not None:
            url = make_url(_qualified_path(resolved))
            if url is not None:
                urls.append(url)
    return urls


def discover_local(
    folders: Iterable[str] | None,
    *,
    find_in_folder: Callable[[str], list[URL] | None],
) -> list[URL]:
    """Concatenate the matches of each supplied folder; candidate creation is separate."""
    if folders is None:
        return []
    if isinstance(folders, (str, bytes)) or not isinstance(folders, Iterable):
        raise UnsupportedCapability(
            "Local custom-info discovery requires an iterable of folder paths",
            capability="GSGlyphsInfo.discovery.folders",
        )
    urls = []
    for folder in folders:
        found = find_in_folder(_qualified_path(folder))
        if found:
            urls.extend(found)
    return urls

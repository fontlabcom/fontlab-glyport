# this_file: src/fontlab_glyport/model/custom_info_filesystem.py
"""Qualified macOS discovery provider, without loading Foundation.

Shallow scandir order is preserved; equality with Foundation's enumeration order
is unmeasured. Dot/BSD/Finder-hidden entries are omitted. Finder alias resolution,
directory symlinks, broken/looping links and unknown filesystem metadata refuse.
SDK NSFileManager.h options7 and Finder.h FileInfo/finderFlags define the masks.
"""

import ctypes
import errno
import os
import stat
import sys
from contextlib import contextmanager
from pathlib import Path

from ..errors import UnsupportedCapability
from .custom_info_discovery import _qualified_path

_FINDER_INFO = "com.apple.FinderInfo"
_INVISIBLE = 0x4000
_ALIAS = 0x8000
_ABSENT_ATTRIBUTE = {errno.ENODATA, getattr(errno, "ENOATTR", errno.ENODATA)}


def _refuse(field, error=None):
    raise UnsupportedCapability(
        f"Unqualified custom-info filesystem operation: {field}",
        capability=f"GSGlyphsInfo.discovery.{field}",
    ) from error


def _require_macos():
    if sys.platform != "darwin":
        _refuse("filesystem.platform")


def _read_finder_info(path: str, *, follow_symlinks: bool = True) -> bytes:
    """SDK sys/xattr.h's getxattr; OS metadata only, no framework library load."""
    _require_macos()
    getxattr = ctypes.CDLL(None, use_errno=True).getxattr
    getxattr.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    getxattr.restype = ctypes.c_ssize_t
    buffer = ctypes.create_string_buffer(32)
    count = getxattr(
        os.fsencode(path),
        _FINDER_INFO.encode(),
        buffer,
        len(buffer),
        0,
        0 if follow_symlinks else 1,  # XATTR_NOFOLLOW=0x0001.
    )
    if count < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), path)
    return buffer.raw[:count]


def _finder_flags(path: str, *, follow_symlinks: bool = True) -> int:
    """Read the owned filesystem's 32-byte FinderInfo, not alias file contents."""
    _require_macos()
    try:
        data = _read_finder_info(path, follow_symlinks=follow_symlinks)
    except OSError as error:
        if error.errno in _ABSENT_ATTRIBUTE:
            return 0
        _refuse("finderInfo", error)
    if len(data) != 32:
        _refuse("finderInfo")
    return int.from_bytes(data[8:10], "big")


def _visible_entry(entry) -> bool:
    if entry.name.startswith("."):
        return False
    try:
        flags = entry.stat(follow_symlinks=False).st_flags
    except OSError as error:
        _refuse("stat", error)
    return not flags & stat.UF_HIDDEN and not (
        _finder_flags(entry.path, follow_symlinks=False) & _INVISIBLE
    )


@contextmanager
def directory_entries(folder: str):
    """Own enumeration lifetime through caller failures; yield None or entries.

    The SDK specifies an empty enumerator for an existing regular-file URL.
    Missing paths use this backend's nil-enumerator profile. Permission/metadata
    failures are outside the qualified domain and never become empty success.
    """
    _require_macos()
    folder = _qualified_path(folder)
    if Path(folder).is_symlink():
        _refuse("directorySymlink")
    try:
        scan = os.scandir(folder)
    except FileNotFoundError:
        yield None
        return
    except NotADirectoryError:
        yield [] if Path(folder).is_file() else None
        return
    except OSError as error:
        _refuse("enumeration", error)
    with scan as entries:
        yield (entry.path for entry in entries if _visible_entry(entry))


def resolve_symlinks(path: str) -> str:
    """Resolve existing symlinks; refuse Finder aliases before loading any bytes."""
    _require_macos()
    _qualified_path(path)
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        _refuse("resolution", error)
    for item in (resolved, *resolved.parents):
        if _finder_flags(str(item)) & _ALIAS:
            _refuse("alias")
    return str(resolved)

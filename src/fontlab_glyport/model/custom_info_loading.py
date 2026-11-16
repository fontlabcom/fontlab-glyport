# this_file: src/fontlab_glyport/model/custom_info_loading.py
"""Ordered filesystem core for custom GlyphData, without a native out-ABI claim.

An owned error record is returned on a qualified file/parser failure. Unsupported
conversion edges propagate explicitly. Native NSURL/NSError/None/NULL bridging,
UI error presentation, discovery and high-level finalization are separate gates.
"""

from collections.abc import Iterable
from os import PathLike
from pathlib import Path
from stat import S_ISREG

from ..errors import UnsupportedCapability
from .custom_info_errors import GlyphDataLoadError, GlyphDataParseError
from .custom_info_parser import parse_into
from .info_records import GlyphInfoIndex


def load_custom_file(
    index: GlyphInfoIndex, path: str | PathLike[str]
) -> GlyphDataLoadError | None:
    """Missing files succeed; later read/parse errors retain completed mutations."""
    path = Path(path)
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    except OSError as error:
        return GlyphDataLoadError(str(error), path=str(path), cause=error)
    if not S_ISREG(info.st_mode):
        raise UnsupportedCapability(
            "Custom GlyphData requires a qualified regular file",
            capability="GSGlyphsInfo.customData.fileType",
        )
    if info.st_size <= 2:
        return GlyphDataLoadError(
            "Custom GlyphData file is too short", path=str(path), offset=0
        )
    try:
        with path.open("rb") as stream:
            data = stream.read(info.st_size)
    except OSError as error:
        return GlyphDataLoadError(str(error), path=str(path), cause=error)
    if len(data) <= 2:
        return GlyphDataLoadError(
            "Custom GlyphData file is too short", path=str(path), offset=0
        )
    try:
        parse_into(index, data)
    except GlyphDataParseError as error:
        return GlyphDataLoadError(
            str(error), path=str(path), offset=error.offset, cause=error
        )
    except GlyphDataLoadError as error:
        error.path = str(path)
        return error
    return None


def load_custom_files(
    index: GlyphInfoIndex, paths: Iterable[str | PathLike[str]]
) -> GlyphDataLoadError | None:
    """Keep supplied order/duplicates and stop before consuming any later file."""
    for path in paths:
        error = load_custom_file(index, path)
        if error is not None:
            return error
    return None

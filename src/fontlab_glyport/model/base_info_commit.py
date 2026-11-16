# this_file: src/fontlab_glyport/model/base_info_commit.py
"""Owned base results and ordered commits; two narrow monitors, no transaction."""

from dataclasses import dataclass
from threading import RLock

from .info_records import GlyphInfoIndex

_NAME_LOCK = RLock()
_GROUP_LOCK = RLock()


@dataclass(frozen=True)
class BaseParseError:
    """Owned source-position error; native/localized CFError fields are not ABI."""

    message: str
    offset: int


@dataclass
class BaseParseResult:
    """One private parser's exact containers, including rows before a failure."""

    success: bool
    index: GlyphInfoIndex
    groups: dict
    error: BaseParseError | None = None


def commit_base(
    target: GlyphInfoIndex, groups: dict | None, result: BaseParseResult
) -> bool:
    """Adopt exact empty-target containers; merge nonempty ones in source order.

    Unicode and records commit outside both locks. The group monitor protects
    only that final merge; these Python monitors do not establish native monitor
    object identity or general concurrent parity. Caller error slots are external.
    """
    if not result.success:
        return False
    with _NAME_LOCK:
        if target.names:
            target.names.update(result.index.names)
        else:
            target.names = result.index.names
    if target.unicodes:
        target.unicodes.update(result.index.unicodes)
    else:
        target.unicodes = result.index.unicodes
    if target.records:
        target.records.extend(result.index.records)
    else:
        target.records = result.index.records
    if groups is not None:
        with _GROUP_LOCK:
            groups.update(result.groups)
    return True

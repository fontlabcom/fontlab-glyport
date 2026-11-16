# this_file: src/fontlab_glyport/glyphsapp/info_chinese.py
"""Ten-job Chinese glyph-info generator over four explicitly supplied lists.

Owned schedulers and supplied lists do not establish native/private-bank parity.
"""

from collections.abc import Iterable, Sequence
from threading import Lock
from types import SimpleNamespace
from typing import Any

from ..errors import UnsupportedCapability
from ..model.info_hex import hex_u32
from ..model.info_records import add_unicode, new_record
from ..model.production_metadata import _utf16_length
from .info_runtime import InfoNativeException, provider_method, state_for

_RANGE_SELECTOR = "_addChinese_end_subCategory_sortPrefix_infos_unicode2Info_"
_LIST_SELECTOR = "_addChinese_subCategory_sortPrefix_infos_unicode2Info_"
_JOBS = (
    (
        (0x2E80, 0x2E99, "Radical", "uni0"),
        (0x2E9B, 0x2EF3, "Radical", "uni0"),
        (0x2F00, 0x2FD5, "Radical", "uni0"),
    ),
    ((0x3400, 0x57EE, None, "uni0"),),
    ((0x57EF, 0x7BDC, None, "uni0"),),
    ((0x7BDD, 0x9FFF, None, "uni0"),),
    ((0xF900, 0xFAD9, "Compatibility", "uni0"),),
    ((0, "Compatibility", "uni0"), (1, "Compatibility", "unj"), (2, None, "unj")),
    ((3, None, "unj"),),
    ((0x30000, 0x3134A, None, "unj"),),
    ((0x31350, 0x323AF, None, "unj"),),
    ((0x2EBF0, 0x2EE5F, None, "unj"),),
)


def _generate(
    codes: Iterable[str],
    prefix: str,
    sub_category: str | None,
    sort_prefix: str | None,
    infos: list | None,
    unicode_index: dict | None,
) -> None:
    """Create fresh rows without changing the map used by any other job."""
    for code in codes:
        if unicode_index is not None and unicode_index.get(code) is not None:
            continue
        row = new_record(prefix + code)
        add_unicode(row, code)
        row.sortName = None if sort_prefix is None else sort_prefix + code
        row.script, row.category, row.subCategory = "han", "Letter", sub_category
        row._locked, row.index = True, 0
        if infos is not None:
            infos.append(row)


def add_range(
    start: int,
    end: int,
    sub_category: str | None,
    sort_prefix: str | None,
    infos: list | None,
    unicode_index: dict | None,
) -> None:
    """Select the naming prefix once from the range's signed start operand."""
    prefix = "u" if start > 0xFFFE else "uni"
    _generate(
        (hex_u32(code) for code in range(start, end + 1)),
        prefix,
        sub_category,
        sort_prefix,
        infos,
        unicode_index,
    )


def add_codes(
    codes: Sequence[str] | None,
    sub_category: str | None,
    sort_prefix: str | None,
    infos: list | None,
    unicode_index: dict | None,
) -> None:
    """Retain list order/repeats and select the prefix by the first UTF16 length."""
    if codes is None:
        return
    first = codes[0] if codes else None
    prefix = "uni" if first is not None and _utf16_length(first) == 4 else "u"
    _generate(codes, prefix, sub_category, sort_prefix, infos, unicode_index)


def _bank_codes(provider: Any, slot: int) -> list[str] | tuple[str, ...]:
    """Require each lawful bank explicitly; primitive nil-list semantics differ."""
    codes = provider_method(provider, "chinese_codes")(slot)
    if not isinstance(codes, (list, tuple)) or any(
        not isinstance(code, str) for code in codes
    ):
        raise UnsupportedCapability(
            f"Chinese bank {slot} requires an explicit lawful list/tuple of strings",
            capability="GSGlyphsInfo.provider.chinese_codes",
        )
    return codes


def _job(
    manager: Any,
    calls: tuple,
    provider: Any,
    unicode_index: dict | None,
    collected: list,
    lock: Any,
) -> None:
    """Publish one whole chunk only after its complete callback succeeds."""
    rows = []
    for call in calls:
        if len(call) == 4:
            getattr(manager, _RANGE_SELECTOR)(*call, rows, unicode_index)
        else:
            slot, sub_category, sort_prefix = call
            codes = _bank_codes(provider, slot)
            getattr(manager, _LIST_SELECTOR)(
                codes, sub_category, sort_prefix, rows, unicode_index
            )
    with lock:
        collected.extend(rows)


def _set_key(mapping: dict | None, key: str | None, row: SimpleNamespace) -> None:
    """NSDictionary nil receivers are inert; concrete maps reject nil keys."""
    if mapping is not None:
        if key is None:
            raise InfoNativeException("Chinese Glyph Info dictionary key is nil")
        mapping[key] = row


def add_chinese(manager: Any) -> None:
    """Wait for all ten jobs, append current rows, then commit captured maps."""
    state = state_for(manager)
    names, unicodes, provider = state.index.names, state.index.unicodes, state.provider
    collected, lock = [], Lock()
    for calls in _JOBS:
        if state.queue is not None:
            state.queue.addOperationWithBlock_(
                lambda calls=calls: _job(
                    manager, calls, provider, unicodes, collected, lock
                )
            )
    if state.queue is not None:
        state.queue.waitUntilAllOperationsAreFinished()
    if state.index.records is not None:
        state.index.records.extend(collected)
    for row in collected:
        _set_key(names, row.name, row)
        _set_key(unicodes, row.unicode, row)

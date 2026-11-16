# this_file: src/fontlab_glyport/model/compound_fields.py
"""Owned compound field, copy, text-cache and sorting stages."""

from types import SimpleNamespace


def copy_record(record: SimpleNamespace) -> SimpleNamespace:
    from .glyph_metadata import _copy_production

    values = _copy_production(vars(record).copy())
    return SimpleNamespace(**values)


def _sub_category(seed: SimpleNamespace, components: list[SimpleNamespace]) -> None:
    if seed.category == "Mark" or seed.subCategory == "Matra":
        return
    count = sum(c.category not in {"Mark", "Separator"} for c in components)
    halves = sum(c.subCategory == "Halfform" for c in components)
    if (count - halves) & ((1 << 64) - 1) >= 2:
        seed.subCategory = "Ligature"
        if getattr(seed, "anchors", None):
            seed.anchors = [
                f"{base}_{index + 1}" + ("@" + tail if separator else "")
                for anchor in seed.anchors
                for base, separator, tail in [anchor.partition("@")]
                for index in range(len(components))
            ]
    elif halves:
        seed.subCategory = "Conjunct"
    elif seed.script not in {"latin", "cyrillic", "greek"}:
        seed.subCategory = "Composition"


def _base_text(record: SimpleNamespace) -> str:
    text = getattr(record, "unicharString", None)
    if text is None:
        from .glyph_metadata import _hex_value

        if record.unicode:
            value = _hex_value(record.unicode)
            if 0 < value <= 0x10FFFE:
                text = chr(value)
        if record.script == "arabic" and record.unicodeLegacy:
            value = _hex_value(record.unicodeLegacy)
            if 0 < value <= 0x10FFFE:
                text = chr(value)
        record.unicharString = text
    if text:
        return text
    return getattr(record, "baseString", "") or ""


def _dot_append(value: str, suffix: str | None) -> str:
    return value + (("" if suffix.startswith(".") else ".") + suffix if suffix else "")


def _sort_metadata(
    seed: SimpleNamespace,
    sorts: list[str],
    position: str | None,
    global_text: str | None,
) -> None:
    base = "_".join(sorts)
    suffix = _dot_append(position, global_text) if position else global_text
    seed.sortNameKeep = _dot_append(base, suffix)
    if suffix:
        if seed.script == "arabic":
            seed.sortName = _dot_append(
                base,
                suffix.replace("fina", "1").replace("medi", "2").replace("init", "3"),
            )
        else:
            seed.sortName = _dot_append(suffix.removeprefix("."), base)
    else:
        seed.sortName = base
    if seed.name.startswith("lam_alef") and not seed.name.startswith("lam_alefMaksura"):
        raw = seed.sortName.encode("utf-16-le", errors="surrogatepass")
        if len(raw) < 12:
            raise ValueError("Lam-alef sort replacement exceeds UTF16 string length")
        seed.sortName = "ar0010" + raw[12:].decode("utf-16-le", errors="surrogatepass")

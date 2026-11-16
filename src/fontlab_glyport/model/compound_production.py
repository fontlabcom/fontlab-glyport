# this_file: src/fontlab_glyport/model/compound_production.py
"""Retained compound production rules keep raw records separate from helpers."""

from types import SimpleNamespace

from .production_metadata import _utf16_length


def is_number(value: str | None) -> bool:
    """Retained NSString category predicate: only the ASCII set 0..9,+,-,dot."""
    return value is not None and all(
        character in "0123456789+-." for character in value
    )


def language_suffix(name: str) -> str | None:
    """Read the last hyphen token, excluding a numeric suffix."""
    if "-" not in name:
        return None
    value = name.rsplit("-", 1)[1].split(".", 1)[0]
    return None if is_number(value) else value


def join_names(names: list[str]) -> str:
    """Join canonical base names and component suffixes without database lookup."""
    language = language_suffix(names[0])
    for name in names:
        other = language_suffix(name)
        if language is not None and other is not None and language != other:
            language = None
    parts = [name.partition(".") for name in names]
    value = "_".join(part[0] for part in parts)
    if language is not None and len(parts) > 1:
        value = value.replace("-" + language, "") + "-" + language
    if any(part[1] for part in parts):
        value += "." + "_".join(part[2] for part in parts)
    if len(parts) > 1:
        if language not in {"malayalam", "kannada"} and value.startswith("ra_halant"):
            value = _replace_initial_window(value, "ra_halant", "rakar")
        if "a_halant" in value:
            value = _replace_initial_window(value, "a_halant", "")
        if language == "kannada" and value.startswith("halant_"):
            value = value[7:] + ".below"
    return value


def _replace_initial_window(value: str, old: str, new: str) -> str:
    raw = value.encode("utf-16-le", errors="surrogatepass")
    if len(raw) < 22:
        raise ValueError("Compound name replacement range exceeds UTF16 string length")
    prefix = raw[:22].decode("utf-16-le", errors="surrogatepass")
    changed = prefix.replace(old, new).encode("utf-16-le", errors="surrogatepass")
    return (changed + raw[22:]).decode("utf-16-le", errors="surrogatepass")


def make_uni_legacies(records: list[SimpleNamespace]) -> list[str] | None:
    """Convert the complete raw list or refuse the whole conversion."""
    values = []
    for record in records:
        stored = record._production_state.value
        if stored and stored.startswith("uni"):
            values.append(stored)
        elif record.unicode and _utf16_length(record.unicode) == 4:
            values.append("uni" + record.unicode)
        else:
            return None
    return values


def compound_production(
    records: list[SimpleNamespace],
    helpers: list[str],
    component_suffix: str = "",
    global_suffix: str | None = None,
    silent: str | None = None,
    position: str | None = None,
    global_tokens: list[str] | None = None,
) -> str:
    """Build production from helper outputs, with raw-list mixed/long fallback."""
    values, accumulated = [], global_suffix or ""
    for helper in helpers:
        base, dot, remainder = (
            helper.partition(".") if helper.find(".") > 0 else (helper, "", "")
        )
        values.append(base)
        if dot:
            accumulated = "." + remainder + accumulated
    has_uni = any(value.startswith("uni") for value in values)
    all_uni = all(value.startswith("uni") for value in values)
    if has_uni and not all_uni:
        replacement = make_uni_legacies(records)
        if replacement is not None:
            values, all_uni = replacement, True
    value = join_names(values) + component_suffix + ("." + position if position else "")
    if all_uni:
        value = value.replace("_uni", "")
    if global_tokens and set(global_tokens) & {"init", "medi", "fina"}:
        value = value.replace("_" + accumulated, "") + accumulated
    elif _utf16_length(accumulated) > 1 and accumulated.removeprefix(".") not in {
        "init",
        "medi",
        "fina",
    }:
        value += accumulated
    if silent:
        value += "." + silent
    if _utf16_length(value) >= 62:
        replacement = make_uni_legacies(records)
        if replacement is not None:
            value = "_".join(replacement)
            if value.startswith("uni"):
                value = value.replace("_uni", "")
    return value.replace("094D094D0930", "094D0930094D")

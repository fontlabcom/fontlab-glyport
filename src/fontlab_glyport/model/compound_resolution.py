# this_file: src/fontlab_glyport/model/compound_resolution.py
"""Resolve seed and component records before names or positions change."""

from types import SimpleNamespace

from .compound_fields import copy_record
from .compound_position import positional_alternate
from .compound_production import language_suffix
from .production_metadata import production_name


def resolve_seed(
    bases: list[str], component_suffixes: list[str], global_suffixes: list[str]
) -> SimpleNamespace | None:
    from .glyph_metadata import _direct, _fill_production, name_info

    first = (
        component_suffixes[0]
        if component_suffixes
        else next(iter(global_suffixes), None)
    )
    seed = _direct(bases[0] + "." + first) if first else None
    if seed is not None:
        seed = copy_record(seed)
    else:
        seed = _direct(bases[0])
        if seed is not None and first in {"case", "cap"}:
            seed = copy_record(seed)
            seed.case = 1
        seed = (
            _fill_production(seed)
            if seed is not None
            else name_info(bases[0], fill_production=True)
        )
    if seed is None:
        language = language_suffix(bases[0])
        if not language:
            return None
        stripped = bases[0][: -len(language) - 1]
        seed = _direct(stripped + "-ar") if language == "farsi" else None
        seed = seed or name_info(stripped, fill_production=True)
        if seed is None:
            return None
        bases[0] = seed.name
    if getattr(seed, "_locked", True):
        seed = copy_record(seed)
    return seed


def resolve_components(
    bases: list[str], component_suffixes: list[str], seed: SimpleNamespace
) -> tuple[
    list[SimpleNamespace], list[SimpleNamespace], list[str], list[str], list[str]
]:
    from ..ui.cocoa import unsupported
    from .glyph_metadata import _direct, _record, name_info

    raw, components, canonical, helpers, sorts = [], [], [], [], []
    cache, canonical_cache = {}, {}
    language = language_suffix(seed.name)
    for index, base in enumerate(bases):
        local = component_suffixes[index] if component_suffixes else ""
        component = (
            _direct(base + "." + local)
            if local and local not in {"sc", "smcp"}
            else None
        )
        if component is not None:
            component_suffixes[index] = ""
        else:
            if base not in cache:
                record = (
                    _direct(base)
                    or positional_alternate(base, _direct)
                    or name_info(base, fill_production=True)
                )
                if record is None and language and base.endswith("-" + language):
                    record = _direct(base[: -len(language) - 1])
                cache[base] = record or _record(base, production=None)
            component = cache[base]
        if (
            getattr(component, "_locked", False)
            and component._production_state is not None
        ):
            component = canonical_cache.setdefault(
                id(component._production_state), component
            )
        if local in {"sc", "smcp"}:
            seed.case = 3
        if component._production_state is None:
            raise unsupported("GSGlyphInfo.compound.production.source")
        if seed.script is None and component.script:
            seed.script = component.script
        canonical.append(component.name)
        raw.append(component)
        sorts.append(
            component.sortName
            if getattr(component, "sortName", None) is not None
            else component.name
        )
        helpers.append(
            production_name(
                component.name,
                component._production_state.value,
                component.unicode,
                component.script,
            )
            or component.name
        )
        if local and not component.name.endswith(local):
            if getattr(component, "_locked", True):
                component = copy_record(component)
            component.name = base + "." + local
        components.append(component)
    return raw, components, canonical, helpers, sorts

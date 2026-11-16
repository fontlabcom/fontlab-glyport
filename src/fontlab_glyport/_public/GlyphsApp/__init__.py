# this_file: src/fontlab_glyport/_public/GlyphsApp/__init__.py
# ruff: noqa: N999 -- public spelling mirrors GlyphsApp.
"""Lazy, directly importable Glyphs API; no host is loaded by this import."""


def use_backend(backend, *, profile: str = "glyphs4") -> None:
    """Bind the default facade to an explicit ModelBackend before first access.

    Repeating the same backend/profile is harmless. Rebinding a live session or
    mixing an independent session with activate() is refused.
    """
    from ._binding import use_backend as bind

    bind(backend, profile=profile)


def unbind() -> None:
    """Close and forget this package's default binding; leave activation alone."""
    from ._binding import unbind as release

    release()


def __getattr__(name: str):
    """Forward every facade export to the single retained session."""
    if name.startswith("_") and name != "__all__":
        raise AttributeError(name)
    from ._binding import facade

    return getattr(facade(), name)


def __dir__():
    """List facade exports without constructing a host session."""
    from ._exports import PUBLIC_NAMES

    return sorted(set(globals()) | set(PUBLIC_NAMES))

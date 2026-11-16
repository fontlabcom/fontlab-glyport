# this_file: src/fontlab_glyport/_public/GlyphsApp/plugins.py
"""SDK plugin bases import without a host; active sessions retain identities."""

# F822: exports are provided lazily by __getattr__.
__all__ = [  # noqa: F822
    "FileFormatPlugin",
    "FilterWithDialog",
    "FilterWithoutDialog",
    "GeneralPlugin",
    "PalettePlugin",
    "ReporterPlugin",
    "SelectTool",
]


def __getattr__(name: str):
    """Use activated plugin identities or the original SDK base classes."""
    if name not in __all__:
        raise AttributeError(name)
    from ._binding import _active

    active = _active()
    if active is not None:
        return getattr(active.modules["GlyphsApp.plugins"], name)
    from . import _binding

    if _binding._context is not None:
        context = _binding._context
        if not hasattr(context, "_public_plugins"):
            context._public_plugins = context.fontlab_session._plugins_module()
        return getattr(context._public_plugins, name)
    from ..plugins import base

    return getattr(base, name)

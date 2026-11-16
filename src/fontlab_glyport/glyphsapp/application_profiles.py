# this_file: src/fontlab_glyport/glyphsapp/application_profiles.py
"""Explicit legacy wrapper signatures; direct GSApplication remains Glyphs 4.

The public GlyphsSDK wrappers at 1c5a8639 (2) and 569244a7 (3) differ in
exact-type checks, argument names, integer formatting and font forwarding.
Keep their methods separate so Python binding and user overrides stay intact.
"""

from .application import GSApplication
from .info_manager import GSGlyphsInfo


def _manager(font):
    return GSGlyphsInfo.sharedManager() if font is None else font.glyphsInfo()


class _Glyphs2Application(GSApplication):
    def glyphInfoForName(self, String, font=None):
        if type(String) is int:
            return self.glyphInfoForUnicode(String)
        return _manager(font).glyphInfoForName_(String)

    def glyphInfoForUnicode(self, String, font=None):
        if type(String) is int:
            String = f"{int.__index__(String):04X}"
        return _manager(font).glyphInfoForUnicode_(String)


class _Glyphs3Application(GSApplication):
    def glyphInfoForName(self, name, font=None):
        if isinstance(name, int):
            return self.glyphInfoForUnicode(name)
        return _manager(font).glyphInfoForName_(name)

    def glyphInfoForUnicode(self, String, font=None):
        if isinstance(String, int):
            String = f"{int.__index__(String):04X}"
        return _manager(font).glyphInfoForUnicode_(String)


def application_class(profile: str) -> type[GSApplication]:
    """Select only a resolved explicit profile without consulting host state."""
    classes = {
        "glyphs2": _Glyphs2Application,
        "glyphs3": _Glyphs3Application,
        "glyphs4": GSApplication,
    }
    if not isinstance(profile, str) or profile not in classes:
        raise ValueError(f"Unsupported application profile: {profile!r}")
    return classes[profile]

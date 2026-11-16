# this_file: src/fontlab_glyport/model/custom_info_errors.py
"""Owned error records for the qualified custom GlyphData parser/loader.

These expose the source error domain/code without constructing Cocoa NSError or
claiming its localized text, object identity or arbitrary bridge conversions.
"""


class GlyphDataParseError(ValueError):
    """A completed prior entry stays merged when a later parse step fails."""

    def __init__(self, message: str, offset: int = 0) -> None:
        super().__init__(message)
        self.offset = offset


class GlyphDataLoadError(Exception):
    """NSError-shaped read-only source error fields; not a native NSError."""

    def __init__(
        self,
        message: str,
        *,
        code: int = 0x2AE2,
        path: str | None = None,
        offset: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self._native_code = code
        self.path, self.offset, self.cause = path, offset, cause

    def domain(self) -> str:
        return "GSGlyphsDomain"

    def code(self) -> int:
        return self._native_code

    def localizedDescription(self) -> str:
        """Owned English message; application-localized wording is unqualified."""
        return str(self)

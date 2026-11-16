# this_file: src/fontlab_glyport/model/parameter_numbers.py
"""Numeric validation for the audited Arabic presentation BOOL parameter.

macOS strings use real Foundation parsing through the Objective-C runtime.
Default decimal formatting is process-cached, as in the audited helper. Explicit
locales own temporary formatters and never change process preferences. No host
application, Qt, PyObjC import or general-purpose locale parser is required.
"""

import ctypes
import sys
from functools import lru_cache
from typing import Any

from ..errors import UnsupportedCapability

KEY = "Use Arabic Presentation Form Unicodes"
_FAILED_DECIMAL = float(2**63)
_ID = ctypes.c_void_p


class _Foundation:
    def __init__(self) -> None:
        self.library = ctypes.CDLL(
            "/System/Library/Frameworks/Foundation.framework/Foundation"
        )
        self.objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        self.objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self.objc.objc_getClass.restype = _ID
        self.objc.sel_registerName.argtypes = [ctypes.c_char_p]
        self.objc.sel_registerName.restype = _ID
        self.default_formatter = None

    def klass(self, name: str) -> int:
        return self.objc.objc_getClass(name.encode("ascii"))

    def send(
        self,
        receiver: int,
        selector: str,
        *arguments: Any,
        result: Any = _ID,
        types: tuple[Any, ...] = (),
    ) -> Any:
        call = ctypes.CFUNCTYPE(result, _ID, _ID, *types)(("objc_msgSend", self.objc))
        return call(
            receiver, self.objc.sel_registerName(selector.encode("ascii")), *arguments
        )

    def string(self, text: str) -> int:
        raw = text.encode("utf-16-le", errors="surrogatepass")
        characters = ctypes.create_string_buffer(raw)
        return self.send(
            self.klass("NSString"),
            "stringWithCharacters:length:",
            characters,
            len(raw) // 2,
            types=(_ID, ctypes.c_size_t),
        )

    def locale(self, name: str | None) -> int:
        if name is None:
            return self.send(self.klass("NSLocale"), "currentLocale")
        locale = self.send(self.klass("NSLocale"), "alloc")
        locale = self.send(
            locale, "initWithLocaleIdentifier:", self.string(name), types=(_ID,)
        )
        return self.send(locale, "autorelease")

    def formatter(self, locale: int, temporary: bool) -> int:
        if not temporary and self.default_formatter is not None:
            return self.default_formatter
        formatter = self.send(self.klass("NSNumberFormatter"), "new")
        self.send(
            formatter, "setNumberStyle:", 1, result=None, types=(ctypes.c_size_t,)
        )
        self.send(formatter, "setLocale:", locale, result=None, types=(_ID,))
        if temporary:
            return self.send(formatter, "autorelease")
        self.default_formatter = formatter
        return formatter


@lru_cache(maxsize=1)
def _foundation() -> _Foundation:
    try:
        return _Foundation()
    except (OSError, AttributeError) as error:
        raise UnsupportedCapability(
            f"Typed parameter conversion requires macOS Foundation: {error}",
            capability="GSCustomParameter.numeric.Foundation",
        ) from error


def _string_number(value: str, locale_name: str | None) -> int | float:
    runtime = _foundation()
    pool = runtime.send(runtime.klass("NSAutoreleasePool"), "new")
    try:
        text, locale = runtime.string(value), runtime.locale(locale_name)
        separator = runtime.send(locale, "decimalSeparator")
        separator = runtime.send(separator, "UTF8String", result=ctypes.c_char_p)
        decimal = separator.decode("utf-8") if separator else "."
        if decimal not in value:
            return runtime.send(text, "integerValue", result=ctypes.c_ssize_t)
        formatter = runtime.formatter(locale, locale_name is not None)
        number = runtime.send(formatter, "numberFromString:", text, types=(_ID,))
        return (
            runtime.send(number, "floatValue", result=ctypes.c_float)
            if number
            else _FAILED_DECIMAL
        )
    finally:
        runtime.send(pool, "drain", result=None)


def normalize(value: object, *, locale_name: str | None = None) -> bool | int | float:
    """Return this BOOL schema's numeric value without Python truth coercion.

    Existing bool/int/float values retain their type/precision. Nil normalizes to
    false. Strings use NSString.integerValue unless they contain the current
    decimal separator; decimal parsing rounds through float32. A failed decimal
    parse uses the upstream nonzero2^63 sentinel. Other object conversions and
    non-macOS string parsing remain explicitly unqualified.
    """
    if value is None:
        return False
    if type(value) in (bool, int, float):
        return value
    if not isinstance(value, str):
        raise UnsupportedCapability(
            "Typed parameter conversion of this object is unqualified",
            capability="GSCustomParameter.numeric.object",
        )
    if sys.platform != "darwin":
        raise UnsupportedCapability(
            "Typed parameter string conversion requires calibrated Foundation parsing",
            capability="GSCustomParameter.numeric.Foundation",
        )
    if locale_name is not None and not isinstance(locale_name, str):
        raise TypeError("locale_name must be a string or None")
    return _string_number(value, locale_name)

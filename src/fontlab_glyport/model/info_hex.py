# this_file: src/fontlab_glyport/model/info_hex.py
"""Hex formatting for qualified internal unsigned scalars.

Values above 0xfffffffe saturate; at most four leading hex zeroes are trimmed.
This does not establish arbitrary Python-to-NSUInteger bridge conversion.
"""


def hex_u32(value: int) -> str:
    """Format a known unsigned 64-bit value as 4..8 uppercase hexadecimal digits."""
    if type(value) is not int:
        raise TypeError("Expected a qualified internal unsigned integer")
    if not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("Expected a qualified internal unsigned 64-bit value")
    return format(min(value, 0xFFFFFFFF), "04X")

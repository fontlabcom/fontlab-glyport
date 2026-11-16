# this_file: src/fontlab_glyport/cocoa_logging.py
"""NSLog's common string/object/numeric formats through the script's stdout."""

import re

from .ui.cocoa import unsupported

_FORMAT = re.compile(
    r"%(?:(?P<position>\d+)\$)?"
    r"(?P<flags>[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?)"
    r"(?:hh|ll|[hlLzqtj])?(?P<kind>[@a-zA-Z%])"
)


def NSLog(format: str, *args) -> None:
    """Use stdout with Cocoa's %% escape, %@ objects and printf scalar formats.

    Surplus varargs are ignored. Missing operands raise TypeError instead of
    reading undefined native memory. A trailing literal percent is preserved.
    """
    operands = iter(args)

    def substitute(match):
        kind = match["kind"]
        if kind == "%":
            return "%"
        if kind not in "@diuoxXfFeEgGcs":
            raise unsupported(f"NSLog.format.%{kind}")
        try:
            position = match["position"]
            if position is not None:
                if int(position) < 1 or "*" in match["flags"]:
                    raise unsupported("NSLog.format.position")
                values, value = [], args[int(position) - 1]
            else:
                values = [next(operands) for _ in range(match["flags"].count("*"))]
                value = next(operands)
        except (StopIteration, IndexError):
            raise TypeError("Not enough arguments for NSLog format") from None
        if kind == "@":
            value = "(null)" if value is None else str(value)
            kind = "s"
        return ("%" + match["flags"] + kind) % (*values, value)

    print(_FORMAT.sub(substitute, str(format)))

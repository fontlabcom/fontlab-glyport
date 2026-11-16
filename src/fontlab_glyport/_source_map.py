# this_file: src/fontlab_glyport/_source_map.py
"""Compose conservative character-span provenance across ordered edits."""

from bisect import bisect_right
from difflib import SequenceMatcher


def compose(
    before: str, after: str, origins: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Unchanged characters retain identity; replacements inherit the edited span."""
    result = []
    for tag, a, b, c, d in SequenceMatcher(
        None, before, after, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            result.extend(origins[a:b])
        elif c != d:
            touched = origins[a:b] or origins[a : a + 1] or origins[-1:]
            span = (
                (min(x[0] for x in touched), max(x[1] for x in touched))
                if touched
                else (0, 0)
            )
            result.extend([span] * (d - c))
    return result


def position(text: str, offset: int) -> list[int]:
    """Return one-based Unicode character coordinates, with exclusive span ends."""
    starts = [0] + [i + 1 for i, char in enumerate(text) if char == "\n"]
    line = bisect_right(starts, offset)
    return [line, offset - starts[line - 1] + 1]


def serialize(original: str, generated: str, origins: list[tuple[int, int]]) -> dict:
    """Export exhaustive generated character spans mapped to original spans."""

    def locator(text: str):
        starts = [0] + [i + 1 for i, char in enumerate(text) if char == "\n"]

        def locate(offset: int) -> list[int]:
            line = bisect_right(starts, offset)
            return [line, offset - starts[line - 1] + 1]

        return locate

    gen, orig = locator(generated), locator(original)
    return {
        "coordinate_system": "one-based Unicode characters; exclusive ends",
        "spans": [
            {
                "generated_start": gen(i),
                "generated_end": gen(i + 1),
                "original_start": orig(a),
                "original_end": orig(b),
            }
            for i, (a, b) in enumerate(origins)
        ],
    }

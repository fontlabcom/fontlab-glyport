# this_file: src/fontlab_glyport/foundation_predicate.py
"""A deliberately bounded Cocoa predicate grammar for Python collections."""

import ast
import re
from collections.abc import Mapping

from .ui.cocoa import NSObject, unsupported


class NSPredicate(NSObject):
    @classmethod
    def predicateWithFormat_(cls, format, *arguments):
        match = re.fullmatch(
            r"\s*(%K|[A-Za-z_]\w*(?:\.\w+)*)\s*(==|!=|CONTAINS)\s*(.*?)\s*",
            str(format),
        )
        if match is None:
            raise unsupported("NSPredicate.predicateWithFormat_")
        field, operator, literal = match.groups()
        values = iter(arguments)
        try:
            field = str(next(values)) if field == "%K" else field
            if literal == "%@":
                expected = next(values)
            elif literal in ("YES", "NO", "nil", "NULL"):
                expected = {"YES": True, "NO": False, "nil": None, "NULL": None}[
                    literal
                ]
            else:
                expected = ast.literal_eval(literal)
        except (StopIteration, ValueError, SyntaxError) as error:
            raise unsupported("NSPredicate.predicateWithFormat_") from error
        if tuple(values):
            raise TypeError("More predicate arguments than placeholders")
        predicate = cls.alloc().init()
        predicate._field, predicate._operator, predicate._expected = (
            field,
            operator,
            expected,
        )
        return predicate

    def evaluateWithObject_(self, value):
        for key in self._field.split("."):
            value = (
                value.get(key) if isinstance(value, Mapping) else getattr(value, key)
            )
        if self._operator == "CONTAINS":
            return value is not None and self._expected in value
        equal = value == self._expected
        return equal if self._operator == "==" else not equal

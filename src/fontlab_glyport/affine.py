# this_file: src/fontlab_glyport/affine.py
"""Mutable Cocoa affine values, shared by Foundation and drawing adapters.

PyObjC structs support named fields and sequence access; constructors default
to zero, whereas NSAffineTransform.init() creates an identity matrix.
"""

from collections.abc import Iterator, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import ClassVar


@dataclass(slots=True, eq=False)
class NSAffineTransformStruct(Sequence):
    m11: float = 0.0
    m12: float = 0.0
    m21: float = 0.0
    m22: float = 0.0
    tX: float = 0.0
    tY: float = 0.0
    _fields: ClassVar[tuple[str, ...]] = ("m11", "m12", "m21", "m22", "tX", "tY")

    def __iter__(self) -> Iterator[float]:
        return (getattr(self, field) for field in self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    def __getitem__(self, index: int | slice) -> float | tuple:
        return tuple(self)[index]

    def __setitem__(self, index: int | slice, value) -> None:
        if isinstance(index, slice):
            fields, values = self._fields[index], tuple(value)
            if len(fields) != len(values):
                raise ValueError("Struct slice assignment cannot change its length")
            for field, item in zip(fields, values, strict=True):
                setattr(self, field, item)
        else:
            setattr(self, self._fields[index], value)

    def _asdict(self) -> dict[str, float]:
        return dict(zip(self._fields, self, strict=True))

    def copy(self) -> "NSAffineTransformStruct":
        return deepcopy(self)

    __pyobjc_copy__ = copy

    def _replace(self, **values: float) -> "NSAffineTransformStruct":
        return replace(self.copy(), **values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (NSAffineTransformStruct, tuple, list)):
            return tuple(self) == tuple(other)
        return NotImplemented

    __hash__ = None

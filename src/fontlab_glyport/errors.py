# this_file: src/fontlab_glyport/errors.py
"""Typed execution failures preserve context without intercepting process exits."""

from typing import ClassVar

from ._receipt_records import ReceiptDiagnostic, SourceLocation


class GlyportError(Exception):
    """Base execution failure; ordinary exception handlers can distinguish intent."""

    code: ClassVar[str] = "GLYPORT_ERROR"

    def __init__(
        self,
        message: str,
        *,
        location: SourceLocation | None = None,
        capability: str | None = None,
        recovery_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.location = location
        self.capability = capability
        self.recovery_action = recovery_action

    def to_diagnostic(self) -> ReceiptDiagnostic:
        """Render original context as a receipt record without fabricating facts."""
        return ReceiptDiagnostic(
            code=self.code,
            severity="error",
            message=str(self),
            location=self.location,
            capability=self.capability,
            recovery_action=self.recovery_action,
        )


class HostUnavailable(GlyportError):
    """The required host cannot be reached or used for execution."""

    code = "HOST_UNAVAILABLE"


class UnsupportedCapability(GlyportError):
    """Requested behavior is unsupported and must not become not_applicable."""

    code = "UNSUPPORTED_CAPABILITY"


class UnsupportedAttribute(UnsupportedCapability, AttributeError):
    """Unsupported attribute read; ``hasattr``/``getattr(obj, name, default)`` probe it.

    Raise it only from ``__getattr__``. Raised inside a plain property body it
    would be re-dispatched to ``__getattr__`` under the property's name; on
    classes whose properties ``_strict.guard_properties`` wraps (model proxies,
    ``Glyphs``) it surfaces as ``UnsupportedCapability`` keeping the inner
    capability and location.
    """


class AdaptationError(GlyportError):
    """An automatic source transformation could not be completed faithfully."""

    code = "ADAPTATION_ERROR"


class DependencyUnavailable(GlyportError):
    """A dependency required for execution could not be resolved."""

    code = "DEPENDENCY_UNAVAILABLE"


class StaleNativeObject(GlyportError):
    """An object's native lifetime ended before the requested operation."""

    code = "STALE_NATIVE_OBJECT"


class NativeOperationError(GlyportError):
    """A host operation failed without being disguised as a supported result."""

    code = "NATIVE_OPERATION_ERROR"


class Cancelled(GlyportError):
    """An owned operation was cancelled; this does not wrap process interrupts."""

    code = "CANCELLED"


class PartialFailure(GlyportError):
    """Some work completed while the operation as a whole failed.

    ``errors`` holds the individual failures in order (``()`` when none were
    attached).
    """

    code = "PARTIAL_FAILURE"
    errors: tuple[BaseException, ...] = ()

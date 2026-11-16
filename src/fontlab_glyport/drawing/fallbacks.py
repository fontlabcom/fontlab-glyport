# this_file: src/fontlab_glyport/drawing/fallbacks.py
"""Controller-approved drawing differences recorded in execution receipts."""

from ..receipt import ReceiptDiagnostic

BACKGROUND_AS_OVERLAY = ReceiptDiagnostic(
    "REPORTER_BACKGROUND_AS_OVERLAY",
    "warning",
    "background drawn as overlay (host refuses before-native phase, R054)",
)

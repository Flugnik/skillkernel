"""CLI adapter for converting terminal input to runtime events."""

from __future__ import annotations

from runtime.contract import CoreEvent, CoreResult
from runtime.handler import handle


def process_text(text: str) -> CoreResult:
    """Convert raw terminal text into a runtime result."""

    return handle(CoreEvent(text=text, meta={"source": "cli"}))


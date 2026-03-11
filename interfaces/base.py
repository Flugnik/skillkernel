"""
Abstract base for all interface adapters (CLI, future: API, bot, etc.).

An adapter is responsible for:
- Receiving raw user input from a specific channel
- Converting it to IncomingEvent
- Passing it to the Dispatcher
- Presenting the DispatchOutcome back to the user
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.dispatcher import Dispatcher


class BaseAdapter(ABC):
    """Contract for all interface adapters."""

    def __init__(self, dispatcher: Dispatcher) -> None:
        self._dispatcher = dispatcher

    @abstractmethod
    def run(self) -> None:
        """Start the adapter's main loop or server."""

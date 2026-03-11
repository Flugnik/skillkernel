"""
ExecutorRegistry — maps action type strings to callable executor functions.

An executor function has the signature:
    def execute(action: Action) -> None

Executors are registered explicitly. No auto-discovery.
"""

from __future__ import annotations

import logging
from typing import Callable

from core.exceptions import ExecutorNotFoundError
from core.models import Action

logger = logging.getLogger(__name__)

ExecutorFn = Callable[[Action], None]


class ExecutorRegistry:
    """Registry mapping action_type strings to executor callables."""

    def __init__(self) -> None:
        self._executors: dict[str, ExecutorFn] = {}

    def register(self, action_type: str, fn: ExecutorFn) -> None:
        """Register an executor function for a given action type.

        Args:
            action_type: The string key matching ActionType enum values.
            fn: Callable that accepts an Action and performs the side effect.
        """
        self._executors[action_type] = fn
        logger.debug("Registered executor for action_type='%s'", action_type)

    def get(self, action_type: str) -> ExecutorFn:
        """Return the executor for the given action type.

        Raises:
            ExecutorNotFoundError: if no executor is registered for this type.
        """
        if action_type not in self._executors:
            raise ExecutorNotFoundError(action_type)
        return self._executors[action_type]

    def list_types(self) -> list[str]:
        """Return all registered action type keys."""
        return list(self._executors.keys())

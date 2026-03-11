"""
EventLogger — appends structured JSONL entries to daily log files.

Log files are written to: <log_dir>/YYYY-MM-DD.jsonl
Each line is a valid JSON object with a 'kind' field and a UTC timestamp.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EventLogger:
    """Writes structured event records to rotating daily JSONL files."""

    def __init__(self, log_dir: str = "memory/event_log") -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------

    def log_incoming_event(self, event_data: dict[str, Any]) -> None:
        self._write("incoming_event", event_data)

    def log_routing_decision(self, decision_data: dict[str, Any]) -> None:
        self._write("routing_decision", decision_data)

    def log_skill_result(self, result_data: dict[str, Any]) -> None:
        self._write("skill_result", result_data)

    def log_execution_result(self, result_data: dict[str, Any]) -> None:
        self._write("execution_result", result_data)

    def log_error(self, error_data: dict[str, Any]) -> None:
        self._write("error", error_data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write(self, kind: str, payload: dict[str, Any]) -> None:
        now = datetime.now(tz=timezone.utc)
        record = {
            "kind": kind,
            "ts": now.isoformat(),
            **payload,
        }
        log_path = self._log_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"
        try:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.error("EventLogger failed to write '%s': %s", log_path, exc)

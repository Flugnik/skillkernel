"""
FileExecutor — implements write_markdown, write_json, ensure_json_file, and noop.

write_markdown:
  - Creates parent directories if they don't exist.
  - Appends content to the target file with a timestamp header.

write_json:
  - Writes (overwrites) a JSON file with the given data dict.
  - Creates parent directories if they don't exist.

ensure_json_file:
  - Creates a JSON file with default_data only if it does not already exist.
  - Creates parent directories if they don't exist.

noop:
  - Does nothing. Useful for testing and dry-run scenarios.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.models import Action

logger = logging.getLogger(__name__)


def execute_write_markdown(action: Action) -> None:
    """Append markdown content to a file, creating parent dirs as needed.

    Expected params:
        path (str): Target file path.
        content (str): Text to append.
    """
    params = action.params
    raw_path = params.get("path")
    content = params.get("content", "")

    if not raw_path:
        raise ValueError("write_markdown action requires 'path' param.")

    target = Path(raw_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = f"\n---\n[{timestamp}]\n{content}\n"

    with target.open("a", encoding="utf-8") as fh:
        fh.write(entry)

    logger.info("write_markdown → '%s' (%d chars)", target, len(content))


def execute_write_json(action: Action) -> None:
    """Write (overwrite) a JSON file with the provided data.

    Expected params:
        path (str): Target file path.
        data (dict | list): JSON-serialisable payload.
    """
    params = action.params
    raw_path = params.get("path")
    data: Any = params.get("data")

    if not raw_path:
        raise ValueError("write_json action requires 'path' param.")
    if data is None:
        raise ValueError("write_json action requires 'data' param.")

    target = Path(raw_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

    logger.info("write_json → '%s'", target)


def execute_ensure_json_file(action: Action) -> None:
    """Create a JSON file with default_data only if it does not already exist.

    Expected params:
        path (str): Target file path.
        default_data (dict | list): Data to write if file is absent.
    """
    params = action.params
    raw_path = params.get("path")
    default_data: Any = params.get("default_data")

    if not raw_path:
        raise ValueError("ensure_json_file action requires 'path' param.")
    if default_data is None:
        raise ValueError("ensure_json_file action requires 'default_data' param.")

    target = Path(raw_path)
    if target.exists():
        logger.debug("ensure_json_file: '%s' already exists, skipping.", target)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(default_data, fh, ensure_ascii=False, indent=2)

    logger.info("ensure_json_file → created '%s'", target)


def execute_noop(action: Action) -> None:
    """No-operation executor. Logs and returns immediately."""
    logger.debug("noop action executed (params=%s)", action.params)


def execute_write_xlsx_export(action: Action) -> None:
    """Build and write an xlsx export file for a given delivery date.

    Expected params:
        path (str):           Target file path.
        delivery_date (str):  ISO-format date string (YYYY-MM-DD).

    Domain reads (products, production day, orders) and xlsx generation
    happen here at execution time so that Action.params stays JSON-serialisable
    and model_dump(mode="json") on SkillResult never encounters raw bytes.
    """
    from datetime import date as _date
    from skills.limiter import repository
    from skills.limiter.exporter import build_export_bytes

    params = action.params
    raw_path = params.get("path")
    delivery_date_str: str | None = params.get("delivery_date")

    if not raw_path:
        raise ValueError("write_xlsx_export action requires 'path' param.")
    if not delivery_date_str:
        raise ValueError("write_xlsx_export action requires 'delivery_date' param.")

    delivery_date = _date.fromisoformat(delivery_date_str)

    products = repository.load_products()
    day = repository.load_production_day(delivery_date)
    orders = repository.load_orders_by_date(delivery_date)

    data_bytes = build_export_bytes(
        delivery_date=delivery_date,
        products=[p for p in products if p.active],
        day=day,
        orders=orders,
    )

    target = Path(raw_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("wb") as fh:
        fh.write(data_bytes)

    logger.info("write_xlsx_export → '%s' (%d bytes)", target, len(data_bytes))

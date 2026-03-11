"""
Platform configuration loader.

Reads config/platform.yaml and exposes a typed PlatformConfig dataclass.
Falls back to sensible defaults if the file is missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path("config/platform.yaml")


@dataclass
class PlatformConfig:
    """Typed representation of platform.yaml settings."""

    threshold_unknown: float = 0.2
    threshold_ambiguous_gap: float = 0.15
    confirmation_ttl_seconds: int = 300
    log_dir: str = "memory/event_log"
    pending_store_path: str = "memory/runtime/pending_plans.json"
    extra: dict = field(default_factory=dict)


def load_config(path: Path = _DEFAULT_CONFIG_PATH) -> PlatformConfig:
    """Load PlatformConfig from a YAML file.

    If the file does not exist, returns a config with default values and
    logs a warning.
    """
    if not path.exists():
        logger.warning("Config file not found at '%s'. Using defaults.", path)
        return PlatformConfig()

    with path.open("r", encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh) or {}

    cfg = PlatformConfig(
        threshold_unknown=float(raw.get("threshold_unknown", 0.2)),
        threshold_ambiguous_gap=float(raw.get("threshold_ambiguous_gap", 0.15)),
        confirmation_ttl_seconds=int(raw.get("confirmation_ttl_seconds", 300)),
        log_dir=str(raw.get("log_dir", "memory/event_log")),
        pending_store_path=str(raw.get("pending_store_path", "memory/runtime/pending_plans.json")),
        extra={k: v for k, v in raw.items() if k not in {
            "threshold_unknown", "threshold_ambiguous_gap",
            "confirmation_ttl_seconds", "log_dir", "pending_store_path",
        }},
    )
    logger.debug("Loaded config from '%s': %s", path, cfg)
    return cfg

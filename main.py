"""
SkillKernel v0.1 — entry point.

Wires up all components explicitly:
  - Loads config
  - Creates SkillRegistry and registers skills
  - Creates ExecutorRegistry and registers executors
  - Builds Dispatcher
  - Starts CLIAdapter

Run with:
    python main.py
"""

import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup — must happen before any module imports that use logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)

# Suppress noisy debug output from sub-modules unless DEBUG env var is set
import os
if os.environ.get("SK_DEBUG"):
    logging.getLogger().setLevel(logging.DEBUG)

logger = logging.getLogger("skillkernel.main")

# ---------------------------------------------------------------------------
# Core imports
# ---------------------------------------------------------------------------

from core.config import load_config
from core.confirm_manager import ConfirmManager
from core.event_log import EventLogger
from core.executor import ActionExecutor
from core.registry import SkillRegistry
from core.router import SkillRouter
from core.dispatcher import Dispatcher

# ---------------------------------------------------------------------------
# Executor imports
# ---------------------------------------------------------------------------

from executors.registry import ExecutorRegistry
from executors.file_executor import (
    execute_write_markdown,
    execute_write_json,
    execute_ensure_json_file,
    execute_noop,
    execute_write_xlsx_export,
)

# ---------------------------------------------------------------------------
# Skill imports
# ---------------------------------------------------------------------------

from skills.farm_guardian.plugin import FarmGuardianSkill
from skills.limiter.plugin import LimiterSkill

# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

from interfaces.cli_adapter import CLIAdapter


def build_app() -> CLIAdapter:
    """Assemble all components and return a ready-to-run CLIAdapter."""

    # 1. Config
    config = load_config(Path("config/platform.yaml"))
    logger.info(
        "Config loaded: threshold_unknown=%.2f threshold_ambiguous_gap=%.2f ttl=%ds",
        config.threshold_unknown,
        config.threshold_ambiguous_gap,
        config.confirmation_ttl_seconds,
    )

    # 2. Skill registry
    skill_registry = SkillRegistry()
    skill_registry.register(FarmGuardianSkill())
    skill_registry.register(LimiterSkill())
    logger.info("Registered %d skill(s): %s", len(skill_registry),
                [s.name for s in skill_registry.list_skills()])

    # 3. Executor registry
    executor_registry = ExecutorRegistry()
    executor_registry.register("write_markdown", execute_write_markdown)
    executor_registry.register("write_json", execute_write_json)
    executor_registry.register("ensure_json_file", execute_ensure_json_file)
    executor_registry.register("noop", execute_noop)
    executor_registry.register("write_xlsx_export", execute_write_xlsx_export)
    logger.info("Registered executor types: %s", executor_registry.list_types())

    # 4. Core components
    event_logger = EventLogger(log_dir=config.log_dir)
    confirm_manager = ConfirmManager(store_path=config.pending_store_path)
    confirm_manager.cleanup_expired()  # clean stale plans on startup

    router = SkillRouter(registry=skill_registry, config=config)
    action_executor = ActionExecutor(executor_registry=executor_registry)

    dispatcher = Dispatcher(
        registry=skill_registry,
        router=router,
        confirm_manager=confirm_manager,
        executor=action_executor,
        event_logger=event_logger,
    )

    # 5. CLI adapter
    return CLIAdapter(dispatcher=dispatcher)


def main() -> None:
    app = build_app()
    app.run()


if __name__ == "__main__":
    main()

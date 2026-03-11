"""
CLIAdapter — interactive terminal interface for SkillKernel.

Supported commands:
  <any text>           → dispatch as IncomingEvent
  confirm <plan_id>    → confirm a pending plan and execute it
  reject <plan_id>     → reject and discard a pending plan
  help                 → show usage
  exit / quit          → exit the loop
"""

from __future__ import annotations

import logging
import sys

from core.dispatcher import Dispatcher, DispatchOutcome
from core.exceptions import PlanExpiredError, PlanNotFoundError
from core.models import IncomingEvent, RoutingStatus
from interfaces.base import BaseAdapter

logger = logging.getLogger(__name__)

_SEPARATOR = "─" * 60
_BANNER = """\
╔══════════════════════════════════════════╗
║        SkillKernel  v0.1  CLI            ║
║  Type text to dispatch, 'help' for cmds  ║
╚══════════════════════════════════════════╝"""


class CLIAdapter(BaseAdapter):
    """Interactive CLI adapter for manual testing and operation."""

    def __init__(self, dispatcher: Dispatcher) -> None:
        super().__init__(dispatcher)

    def run(self) -> None:
        """Start the interactive REPL loop."""
        print(_BANNER)
        print()

        while True:
            try:
                raw = input(">> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                sys.exit(0)

            if not raw:
                continue

            lower = raw.lower()

            if lower in ("exit", "quit"):
                print("Goodbye.")
                sys.exit(0)

            if lower == "help":
                self._print_help()
                continue

            if lower.startswith("confirm "):
                plan_id = raw[len("confirm "):].strip()
                self._handle_confirm(plan_id)
                continue

            if lower.startswith("reject "):
                plan_id = raw[len("reject "):].strip()
                self._handle_reject(plan_id)
                continue

            # Regular dispatch
            self._handle_dispatch(raw)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _handle_dispatch(self, text: str) -> None:
        event = IncomingEvent(text=text, source="cli")
        logger.debug("CLI dispatching event_id=%s", event.event_id)

        outcome = self._dispatcher.dispatch(event)
        self._print_outcome(outcome)

    def _print_outcome(self, outcome: DispatchOutcome) -> None:
        print(_SEPARATOR)
        status = outcome.decision.status

        if status == RoutingStatus.unknown:
            print(f"[UNKNOWN]  {outcome.message}")

        elif status == RoutingStatus.ambiguous:
            print(f"[AMBIGUOUS]  {outcome.message}")
            scores = outcome.decision.scores
            if scores:
                print("  Scores:")
                for name, score in sorted(scores.items(), key=lambda kv: -kv[1]):
                    print(f"    {name}: {score:.3f}")

        elif status == RoutingStatus.matched:
            skill = outcome.decision.matched_skill
            print(f"[MATCHED]  skill={skill}")

            if outcome.requires_confirmation:
                print(f"\n[ЧЕРНОВИК — ожидает подтверждения]")
                print()
                # Indent each line of the preview for readability
                for line in outcome.preview_text.splitlines():
                    print(f"  {line}")
                pid = outcome.plan_id
                print()
                print(f"  Подтвердить:  confirm {pid}")
                print(f"  Отменить:     reject {pid}")

            elif outcome.is_executed:
                er = outcome.execution_result
                if er.success:
                    print(f"[EXECUTED]  plan_id={er.plan_id}")
                    for act in er.executed_actions:
                        print(f"  ✓ {act}")
                else:
                    print(f"[PARTIAL/FAILED]  plan_id={er.plan_id}")
                    for act in er.executed_actions:
                        print(f"  ✓ {act}")
                    for err in er.errors:
                        print(f"  ✗ {err}")
            else:
                print(f"  {outcome.message}")

        print(_SEPARATOR)

    # ------------------------------------------------------------------
    # Confirm / reject
    # ------------------------------------------------------------------

    def _handle_confirm(self, plan_id: str) -> None:
        if not plan_id:
            print("[ERROR]  Usage: confirm <plan_id>")
            return
        try:
            outcome = self._dispatcher.confirm_plan(plan_id)
            print(_SEPARATOR)
            er = outcome.execution_result
            if er and er.success:
                print(f"[CONFIRMED & EXECUTED]  plan_id={er.plan_id}")
                for act in er.executed_actions:
                    print(f"  ✓ {act}")
            elif er:
                print(f"[CONFIRMED — PARTIAL/FAILED]  plan_id={er.plan_id}")
                for act in er.executed_actions:
                    print(f"  ✓ {act}")
                for err in er.errors:
                    print(f"  ✗ {err}")
            else:
                print(f"  {outcome.message}")
            print(_SEPARATOR)
        except PlanNotFoundError as exc:
            print(f"[ERROR]  {exc}")
        except PlanExpiredError as exc:
            print(f"[ERROR]  {exc}")

    def _handle_reject(self, plan_id: str) -> None:
        if not plan_id:
            print("[ERROR]  Usage: reject <plan_id>")
            return
        try:
            msg = self._dispatcher.reject_plan(plan_id)
            print(f"[REJECTED]  {msg}")
        except PlanNotFoundError as exc:
            print(f"[ERROR]  {exc}")

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    @staticmethod
    def _print_help() -> None:
        print(_SEPARATOR)
        print("Commands:")
        print("  <text>              Dispatch text as an event")
        print("  confirm <plan_id>   Confirm and execute a pending plan")
        print("  reject  <plan_id>   Reject and discard a pending plan")
        print("  help                Show this message")
        print("  exit / quit         Exit the CLI")
        print(_SEPARATOR)

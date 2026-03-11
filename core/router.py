"""
SkillRouter — scores all registered skills and produces a DispatchDecision.

Routing rules:
- best score < threshold_unknown  → unknown
- gap between 1st and 2nd score < threshold_ambiguous_gap → ambiguous
- otherwise → matched
"""

from __future__ import annotations

import logging

from core.config import PlatformConfig
from core.models import DispatchDecision, IncomingEvent, RoutingStatus
from core.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillRouter:
    """Routes an IncomingEvent to the best-matching skill."""

    def __init__(self, registry: SkillRegistry, config: PlatformConfig) -> None:
        self._registry = registry
        self._config = config

    def route(self, event: IncomingEvent) -> DispatchDecision:
        """Score all skills and return a DispatchDecision.

        Does NOT execute any skill — pure routing only.
        """
        skills = self._registry.list_skills()

        if not skills:
            logger.warning("No skills registered; returning unknown decision.")
            return DispatchDecision(
                event_id=event.event_id,
                status=RoutingStatus.unknown,
                message="No skills are registered.",
            )

        scores: dict[str, float] = {}
        for skill in skills:
            try:
                s = skill.score(event)
            except Exception as exc:  # noqa: BLE001
                logger.error("Skill '%s' raised during score(): %s", skill.name, exc)
                s = 0.0
            scores[skill.name] = round(float(s), 4)

        sorted_scores = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best_name, best_score = sorted_scores[0]

        logger.debug("Routing scores: %s", sorted_scores)

        # Unknown — best score is too low
        if best_score < self._config.threshold_unknown:
            logger.info(
                "event_id=%s → unknown (best_score=%.4f < threshold=%.4f)",
                event.event_id, best_score, self._config.threshold_unknown,
            )
            return DispatchDecision(
                event_id=event.event_id,
                status=RoutingStatus.unknown,
                scores=scores,
                message=(
                    f"No skill matched (best score {best_score:.2f} "
                    f"< threshold {self._config.threshold_unknown:.2f})."
                ),
            )

        # Ambiguous — top two scores are too close
        if len(sorted_scores) >= 2:
            second_score = sorted_scores[1][1]
            gap = best_score - second_score
            if gap < self._config.threshold_ambiguous_gap:
                logger.info(
                    "event_id=%s → ambiguous (gap=%.4f < threshold=%.4f)",
                    event.event_id, gap, self._config.threshold_ambiguous_gap,
                )
                return DispatchDecision(
                    event_id=event.event_id,
                    status=RoutingStatus.ambiguous,
                    scores=scores,
                    message=(
                        f"Multiple skills matched with similar confidence "
                        f"(gap {gap:.2f} < threshold {self._config.threshold_ambiguous_gap:.2f}). "
                        f"Please be more specific."
                    ),
                )

        # Matched
        logger.info(
            "event_id=%s → matched skill='%s' score=%.4f",
            event.event_id, best_name, best_score,
        )
        return DispatchDecision(
            event_id=event.event_id,
            status=RoutingStatus.matched,
            matched_skill=best_name,
            scores=scores,
            message=f"Matched skill '{best_name}' with score {best_score:.2f}.",
        )

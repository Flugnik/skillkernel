"""
Tests for SkillRouter routing logic.
"""

import pytest

from core.config import PlatformConfig
from core.models import IncomingEvent, RoutingStatus
from core.registry import SkillRegistry
from core.router import SkillRouter
from skills.farm_guardian.plugin import FarmGuardianSkill
from skills.limiter.plugin import LimiterSkill


@pytest.fixture()
def config() -> PlatformConfig:
    return PlatformConfig(
        threshold_unknown=0.2,
        threshold_ambiguous_gap=0.15,
    )


@pytest.fixture()
def registry_with_both(config) -> SkillRegistry:
    reg = SkillRegistry()
    reg.register(FarmGuardianSkill())
    reg.register(LimiterSkill())
    return reg


@pytest.fixture()
def router(registry_with_both, config) -> SkillRouter:
    return SkillRouter(registry=registry_with_both, config=config)


class TestSkillRouterMatched:
    def test_farm_guardian_matched(self, router):
        event = IncomingEvent(text="Маша сегодня хорошо поела, записать в журнал")
        decision = router.route(event)
        assert decision.status == RoutingStatus.matched
        assert decision.matched_skill == "farm_guardian"
        assert decision.scores["farm_guardian"] > 0

    def test_limiter_matched(self, router):
        event = IncomingEvent(text="/summary 2026-03-15")
        decision = router.route(event)
        assert decision.status == RoutingStatus.matched
        assert decision.matched_skill == "limiter"

    def test_scores_present_for_all_skills(self, router):
        event = IncomingEvent(text="Маша корова журнал")
        decision = router.route(event)
        assert "farm_guardian" in decision.scores
        assert "limiter" in decision.scores


class TestSkillRouterUnknown:
    def test_unknown_on_irrelevant_text(self, router):
        event = IncomingEvent(text="Привет, как дела?")
        decision = router.route(event)
        assert decision.status == RoutingStatus.unknown
        assert decision.matched_skill is None

    def test_unknown_on_empty_text(self, router):
        event = IncomingEvent(text="   ")
        decision = router.route(event)
        assert decision.status == RoutingStatus.unknown

    def test_unknown_when_no_skills_registered(self, config):
        empty_registry = SkillRegistry()
        router = SkillRouter(registry=empty_registry, config=config)
        event = IncomingEvent(text="Маша корова")
        decision = router.route(event)
        assert decision.status == RoutingStatus.unknown


class TestSkillRouterAmbiguous:
    def test_ambiguous_when_scores_close(self, config):
        """Use a very high ambiguous gap threshold to force ambiguous result."""
        cfg = PlatformConfig(
            threshold_unknown=0.0,
            threshold_ambiguous_gap=1.0,  # any gap < 1.0 is ambiguous
        )
        reg = SkillRegistry()
        reg.register(FarmGuardianSkill())
        reg.register(LimiterSkill())
        router = SkillRouter(registry=reg, config=cfg)

        # Text that hits both skills
        event = IncomingEvent(text="Маша корова кг корм лимит журнал")
        decision = router.route(event)
        assert decision.status == RoutingStatus.ambiguous

    def test_not_ambiguous_with_clear_winner(self, router):
        event = IncomingEvent(text="Маша плюша корова теленок журнал протокол наблюдение")
        decision = router.route(event)
        # farm_guardian should win clearly
        assert decision.status == RoutingStatus.matched
        assert decision.matched_skill == "farm_guardian"


class TestSkillRouterScores:
    def test_scores_are_floats_in_range(self, router):
        event = IncomingEvent(text="Маша корова журнал")
        decision = router.route(event)
        for name, score in decision.scores.items():
            assert isinstance(score, float), f"Score for {name} is not float"
            assert 0.0 <= score <= 1.0, f"Score for {name} out of range: {score}"

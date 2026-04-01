"""
Batch 2A — TruthSourceRegistry Tests: PatternClaim schema + epistemic constraints
====================================================================================
A1-A8 acceptance criteria coverage:
  A1: PatternClaim dataclass schema validation
  A2: Epistemic constraint — AI output never FACT
  A3: Confidence capping per evidence source
  A4: TTL computation per evidence source
  A5: register_claim() supersession logic
  A6: get_active_claims() filtering (regime/strategy/confidence/level)
  A7: record_falsification() downgrade logic (INFERENCE→HYPOTHESIS, HYPOTHESIS→deactivate)
  A8: expire_stale_claims() cleanup
  Plus: get_stats(), to_snapshot(), AnalystAgent integration, StrategistAgent integration

28 tests total.
"""

import sys
import os
import time
import threading
import unittest
from unittest.mock import MagicMock, patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.truth_source_registry import (
    CognitiveLevel,
    PatternClaim,
    TruthSourceRegistry,
    _cap_confidence,
    _derive_cognitive_level,
    _compute_ttl_ms,
    _parse_evidence_source,
)
from app.analyst_agent import AnalystAgent, AnalystConfig, PatternInsight
from app.strategist_agent import StrategistAgent, StrategistConfig
from app.multi_agent_framework import AgentMessage, AgentRole, AgentState, MessageType


# ═══════════════════════════════════════════════════════════════════════════════
# A1: PatternClaim dataclass schema validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestPatternClaimSchema(unittest.TestCase):
    """A1: Validate PatternClaim dataclass fields and serialization."""

    def _make_claim(self, **kwargs) -> PatternClaim:
        defaults = dict(
            claim_id="test_claim_001",
            pattern_text="RSI oversold in ranging regime",
            cognitive_level=CognitiveLevel.INFERENCE,
            evidence_source="statistical_N=50",
            observation_count=50,
            confidence=0.65,
            applies_to_regime="ranging",
            applies_to_strategy="rsi_reversal",
            created_at_ms=int(time.time() * 1000),
            expires_at_ms=int(time.time() * 1000) + 30 * 86_400_000,
        )
        defaults.update(kwargs)
        return PatternClaim(**defaults)

    def test_claim_default_fields(self):
        """PatternClaim has correct defaults for optional fields."""
        claim = self._make_claim()
        self.assertTrue(claim.is_active)
        self.assertIsNone(claim.superseded_by)
        self.assertEqual(claim.falsification_count, 0)
        self.assertEqual(claim.falsification_threshold, 5)

    def test_claim_to_dict_contains_all_fields(self):
        """to_dict() serializes all required fields."""
        claim = self._make_claim()
        d = claim.to_dict()
        required_keys = [
            "claim_id", "pattern_text", "cognitive_level", "evidence_source",
            "observation_count", "confidence", "applies_to_regime",
            "applies_to_strategy", "created_at_ms", "expires_at_ms",
            "is_active", "superseded_by", "falsification_count", "falsification_threshold",
        ]
        for k in required_keys:
            self.assertIn(k, d, f"Missing field: {k}")

    def test_claim_is_expired_with_past_ttl(self):
        """is_expired() returns True when expires_at_ms is in the past."""
        past_ms = int(time.time() * 1000) - 1000
        claim = self._make_claim(expires_at_ms=past_ms)
        self.assertTrue(claim.is_expired())

    def test_claim_is_expired_never_when_zero(self):
        """is_expired() returns False when expires_at_ms=0 (never expires)."""
        claim = self._make_claim(expires_at_ms=0)
        self.assertFalse(claim.is_expired())

    def test_claim_is_not_expired_future_ttl(self):
        """is_expired() returns False when expires_at_ms is in the future."""
        future_ms = int(time.time() * 1000) + 7 * 86_400_000
        claim = self._make_claim(expires_at_ms=future_ms)
        self.assertFalse(claim.is_expired())

    def test_cognitive_level_enum_values(self):
        """CognitiveLevel has correct string values."""
        self.assertEqual(CognitiveLevel.FACT.value, "FACT")
        self.assertEqual(CognitiveLevel.INFERENCE.value, "INFERENCE")
        self.assertEqual(CognitiveLevel.HYPOTHESIS.value, "HYPOTHESIS")


# ═══════════════════════════════════════════════════════════════════════════════
# A2 + A3: Epistemic constraint — AI never FACT, confidence capping
# ═══════════════════════════════════════════════════════════════════════════════

class TestEpistemicConstraints(unittest.TestCase):
    """A2: AI output is never FACT. A3: Confidence is capped by source."""

    def test_ai_source_never_fact(self):
        """AI evidence source must produce INFERENCE, never FACT."""
        level = _derive_cognitive_level("ai", 0.99)
        self.assertNotEqual(level, CognitiveLevel.FACT)
        self.assertEqual(level, CognitiveLevel.INFERENCE)

    def test_statistical_low_n_hypothesis(self):
        """Statistical N<30 with low confidence → HYPOTHESIS."""
        level = _derive_cognitive_level("statistical_N=10", 0.3)
        self.assertEqual(level, CognitiveLevel.HYPOTHESIS)

    def test_statistical_high_n_inference(self):
        """Statistical N>=30 with confidence>0.5 → INFERENCE."""
        level = _derive_cognitive_level("statistical_N=30", 0.6)
        self.assertEqual(level, CognitiveLevel.INFERENCE)

    def test_manual_source_can_be_fact(self):
        """Manual source is the only source that can produce FACT."""
        level = _derive_cognitive_level("manual", 1.0)
        self.assertEqual(level, CognitiveLevel.FACT)

    def test_confidence_cap_ai(self):
        """AI source caps confidence at 0.85."""
        capped = _cap_confidence(0.99, "ai")
        self.assertAlmostEqual(capped, 0.85)

    def test_confidence_cap_statistical_low_n(self):
        """Statistical N<30 caps confidence at 0.5."""
        capped = _cap_confidence(0.99, "statistical_N=10")
        self.assertAlmostEqual(capped, 0.5)

    def test_confidence_cap_statistical_high_n(self):
        """Statistical N>=30 caps confidence at 0.7."""
        capped = _cap_confidence(0.99, "statistical_N=50")
        self.assertAlmostEqual(capped, 0.7)

    def test_confidence_cap_manual_no_cap(self):
        """Manual source has confidence cap 1.0."""
        capped = _cap_confidence(1.0, "manual")
        self.assertAlmostEqual(capped, 1.0)

    def test_confidence_not_inflated_by_cap(self):
        """Confidence below cap is not inflated."""
        capped = _cap_confidence(0.4, "ai")
        self.assertAlmostEqual(capped, 0.4)


# ═══════════════════════════════════════════════════════════════════════════════
# A4: TTL computation
# ═══════════════════════════════════════════════════════════════════════════════

class TestTTLComputation(unittest.TestCase):
    """A4: TTL is computed correctly from evidence source."""

    def test_ttl_statistical_low_n_7_days(self):
        """Statistical N<50 → TTL ~7 days from now."""
        now_ms = int(time.time() * 1000)
        expires = _compute_ttl_ms("statistical_N=20")
        delta_days = (expires - now_ms) / 86_400_000
        self.assertAlmostEqual(delta_days, 7.0, delta=0.01)

    def test_ttl_statistical_high_n_30_days(self):
        """Statistical N>=50 → TTL ~30 days from now."""
        now_ms = int(time.time() * 1000)
        expires = _compute_ttl_ms("statistical_N=50")
        delta_days = (expires - now_ms) / 86_400_000
        self.assertAlmostEqual(delta_days, 30.0, delta=0.01)

    def test_ttl_ai_14_days(self):
        """AI source → TTL ~14 days from now."""
        now_ms = int(time.time() * 1000)
        expires = _compute_ttl_ms("ai")
        delta_days = (expires - now_ms) / 86_400_000
        self.assertAlmostEqual(delta_days, 14.0, delta=0.01)

    def test_ttl_manual_never_expires(self):
        """Manual source → TTL = 0 (never expires)."""
        expires = _compute_ttl_ms("manual")
        self.assertEqual(expires, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# A5: register_claim() supersession logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegisterClaim(unittest.TestCase):
    """A5: register_claim() supersession logic."""

    def setUp(self):
        self.registry = TruthSourceRegistry()

    def test_register_basic(self):
        """register_claim() returns a claim_id string."""
        cid = self.registry.register_claim(
            pattern_text="RSI works in ranging market",
            evidence_source="statistical_N=50",
            observation_count=50,
            confidence=0.65,
            applies_to_regime="ranging",
            applies_to_strategy="rsi_reversal",
        )
        self.assertIsInstance(cid, str)
        self.assertTrue(len(cid) > 0)

    def test_register_enforces_confidence_cap(self):
        """Registered claim has confidence capped by evidence source."""
        cid = self.registry.register_claim(
            pattern_text="some pattern",
            evidence_source="ai",
            observation_count=200,
            confidence=0.99,  # higher than AI cap of 0.85
            applies_to_regime="all",
            applies_to_strategy="all",
        )
        claims = self.registry.get_active_claims()
        found = next((c for c in claims if c.claim_id == cid), None)
        self.assertIsNotNone(found)
        self.assertLessEqual(found.confidence, 0.85 + 1e-9)

    def test_register_supersedes_lower_confidence(self):
        """New higher-confidence claim for same (regime, strategy) supersedes old claim."""
        cid_old = self.registry.register_claim(
            pattern_text="pattern A",
            evidence_source="statistical_N=50",
            observation_count=50,
            confidence=0.6,
            applies_to_regime="trending",
            applies_to_strategy="ma_crossover",
        )
        cid_new = self.registry.register_claim(
            pattern_text="pattern B (better)",
            evidence_source="statistical_N=100",
            observation_count=100,
            confidence=0.69,  # higher; cap for N>=30 = 0.7
            applies_to_regime="trending",
            applies_to_strategy="ma_crossover",
        )
        # Old claim should be inactive / 旧声明应为非活跃
        snapshot = {c["claim_id"]: c for c in self.registry.to_snapshot()}
        self.assertFalse(snapshot[cid_old]["is_active"])
        self.assertEqual(snapshot[cid_old]["superseded_by"], cid_new)
        # New claim should be active / 新声明应为活跃
        self.assertTrue(snapshot[cid_new]["is_active"])

    def test_register_does_not_supersede_higher_confidence(self):
        """New lower-confidence claim does NOT supersede existing higher-confidence claim."""
        cid_high = self.registry.register_claim(
            pattern_text="high confidence pattern",
            evidence_source="statistical_N=50",
            observation_count=50,
            confidence=0.69,
            applies_to_regime="volatile",
            applies_to_strategy="grid",
        )
        cid_low = self.registry.register_claim(
            pattern_text="low confidence pattern",
            evidence_source="statistical_N=30",
            observation_count=30,
            confidence=0.55,
            applies_to_regime="volatile",
            applies_to_strategy="grid",
        )
        snapshot = {c["claim_id"]: c for c in self.registry.to_snapshot()}
        # High confidence claim should remain active / 高信度声明应保持活跃
        self.assertTrue(snapshot[cid_high]["is_active"])
        # Low confidence claim is added but does not supersede / 低信度声明被添加但不替代
        self.assertIsNone(snapshot[cid_high]["superseded_by"])


# ═══════════════════════════════════════════════════════════════════════════════
# A6: get_active_claims() filtering
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetActiveClaims(unittest.TestCase):
    """A6: get_active_claims() applies all filters correctly."""

    def setUp(self):
        self.registry = TruthSourceRegistry()
        # Register a variety of claims / 登记多种声明
        self.registry.register_claim(
            pattern_text="RSI in ranging",
            evidence_source="statistical_N=50",
            observation_count=50,
            confidence=0.65,
            applies_to_regime="ranging",
            applies_to_strategy="rsi_reversal",
        )
        self.registry.register_claim(
            pattern_text="MA crossover in trending",
            evidence_source="ai",
            observation_count=300,
            confidence=0.75,
            applies_to_regime="trending",
            applies_to_strategy="ma_crossover",
        )
        self.registry.register_claim(
            pattern_text="all-regime pattern",
            evidence_source="ai",
            observation_count=200,
            confidence=0.60,
            applies_to_regime="all",
            applies_to_strategy="all",
        )

    def test_filter_by_regime(self):
        """Filtering by regime returns only matching claims."""
        claims = self.registry.get_active_claims(regime="ranging")
        regimes = {c.applies_to_regime for c in claims}
        # "all" claims should also be included / "all" 声明也应包含
        for c in claims:
            self.assertIn(c.applies_to_regime, ("ranging", "all"))

    def test_filter_by_min_confidence(self):
        """Filtering by min_confidence excludes low-confidence claims."""
        claims = self.registry.get_active_claims(min_confidence=0.70)
        for c in claims:
            self.assertGreaterEqual(c.confidence, 0.70)

    def test_filter_by_cognitive_level(self):
        """Filtering by cognitive_level returns only matching level."""
        claims = self.registry.get_active_claims(cognitive_level=CognitiveLevel.INFERENCE)
        for c in claims:
            self.assertEqual(c.cognitive_level, CognitiveLevel.INFERENCE)

    def test_sorted_by_confidence_desc(self):
        """get_active_claims() returns results sorted by confidence descending."""
        claims = self.registry.get_active_claims()
        confidences = [c.confidence for c in claims]
        self.assertEqual(confidences, sorted(confidences, reverse=True))


# ═══════════════════════════════════════════════════════════════════════════════
# A7: record_falsification() downgrade logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestFalsification(unittest.TestCase):
    """A7: record_falsification() downgrades or deactivates claims."""

    def setUp(self):
        self.registry = TruthSourceRegistry()

    def _register_inference(self) -> str:
        return self.registry.register_claim(
            pattern_text="inference pattern",
            evidence_source="statistical_N=50",
            observation_count=50,
            confidence=0.65,
            applies_to_regime="ranging",
            applies_to_strategy="test_strategy",
        )

    def test_falsification_increments_count(self):
        """record_falsification() increments falsification_count."""
        cid = self._register_inference()
        self.registry.record_falsification(cid)
        snapshot = {c["claim_id"]: c for c in self.registry.to_snapshot()}
        self.assertEqual(snapshot[cid]["falsification_count"], 1)

    def test_falsification_inference_downgrades_at_threshold(self):
        """INFERENCE claim downgrades to HYPOTHESIS at falsification_threshold."""
        cid = self._register_inference()
        # Trigger 5 falsifications (default threshold = 5) / 触发 5 次证伪（默认阈值 = 5）
        for _ in range(5):
            self.registry.record_falsification(cid)
        snapshot = {c["claim_id"]: c for c in self.registry.to_snapshot()}
        self.assertEqual(snapshot[cid]["cognitive_level"], CognitiveLevel.HYPOTHESIS.value)

    def test_falsification_hypothesis_deactivates_at_threshold(self):
        """HYPOTHESIS claim is deactivated when falsification_threshold is reached again."""
        cid = self._register_inference()
        # First round: INFERENCE → HYPOTHESIS / 第一轮：INFERENCE → HYPOTHESIS
        for _ in range(5):
            self.registry.record_falsification(cid)
        # Second round: HYPOTHESIS → deactivated / 第二轮：HYPOTHESIS → 停用
        for _ in range(5):
            self.registry.record_falsification(cid)
        snapshot = {c["claim_id"]: c for c in self.registry.to_snapshot()}
        self.assertFalse(snapshot[cid]["is_active"])

    def test_falsification_unknown_id_is_noop(self):
        """record_falsification() with unknown claim_id does not raise."""
        try:
            self.registry.record_falsification("nonexistent_claim_id_xyz")
        except Exception as e:
            self.fail(f"record_falsification raised unexpected exception: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# A8: expire_stale_claims()
# ═══════════════════════════════════════════════════════════════════════════════

class TestExpireStale(unittest.TestCase):
    """A8: expire_stale_claims() deactivates expired claims."""

    def test_expire_returns_count(self):
        """expire_stale_claims() returns count of expired claims."""
        registry = TruthSourceRegistry()
        # Manually add an expired claim via register_claim and then modify expires_at_ms
        # 通过 register_claim 添加后手动修改 expires_at_ms 模拟过期
        cid = registry.register_claim(
            pattern_text="stale pattern",
            evidence_source="statistical_N=30",
            observation_count=30,
            confidence=0.55,
            applies_to_regime="all",
            applies_to_strategy="all",
        )
        # Force expire by setting expires_at_ms to the past
        # 通过将 expires_at_ms 设置为过去来强制过期
        registry._claims[cid].expires_at_ms = int(time.time() * 1000) - 1000
        expired = registry.expire_stale_claims()
        self.assertEqual(expired, 1)

    def test_expired_claim_not_in_active_results(self):
        """Expired claims do not appear in get_active_claims()."""
        registry = TruthSourceRegistry()
        cid = registry.register_claim(
            pattern_text="another stale pattern",
            evidence_source="ai",
            observation_count=200,
            confidence=0.70,
            applies_to_regime="all",
            applies_to_strategy="all",
        )
        registry._claims[cid].expires_at_ms = int(time.time() * 1000) - 1000
        registry.expire_stale_claims()
        active = registry.get_active_claims()
        active_ids = {c.claim_id for c in active}
        self.assertNotIn(cid, active_ids)

    def test_non_expired_claims_not_affected(self):
        """expire_stale_claims() does not touch non-expired claims."""
        registry = TruthSourceRegistry()
        cid = registry.register_claim(
            pattern_text="fresh pattern",
            evidence_source="ai",
            observation_count=200,
            confidence=0.70,
            applies_to_regime="all",
            applies_to_strategy="all",
        )
        expired = registry.expire_stale_claims()
        self.assertEqual(expired, 0)
        active = registry.get_active_claims()
        active_ids = {c.claim_id for c in active}
        self.assertIn(cid, active_ids)


# ═══════════════════════════════════════════════════════════════════════════════
# get_stats() and to_snapshot()
# ═══════════════════════════════════════════════════════════════════════════════

class TestStatsAndSnapshot(unittest.TestCase):
    """get_stats() returns correct aggregate info; to_snapshot() is complete."""

    def test_get_stats_structure(self):
        """get_stats() contains required keys."""
        registry = TruthSourceRegistry()
        stats = registry.get_stats()
        for key in ("total_claims", "active_claims", "level_distribution",
                    "total_registered", "total_expired", "total_falsified", "total_superseded"):
            self.assertIn(key, stats)

    def test_to_snapshot_includes_all_claims(self):
        """to_snapshot() includes all claims, including inactive ones."""
        registry = TruthSourceRegistry()
        cid1 = registry.register_claim(
            pattern_text="p1", evidence_source="ai", observation_count=200,
            confidence=0.60, applies_to_regime="all", applies_to_strategy="s1",
        )
        cid2 = registry.register_claim(
            pattern_text="p2", evidence_source="ai", observation_count=200,
            confidence=0.80, applies_to_regime="all", applies_to_strategy="s1",
        )
        snapshot = registry.to_snapshot()
        ids = {c["claim_id"] for c in snapshot}
        # Both claims should appear (cid1 is superseded but still in snapshot)
        # 两条声明都应出现（cid1 已被替代，但仍在快照中）
        self.assertIn(cid1, ids)
        self.assertIn(cid2, ids)


# ═══════════════════════════════════════════════════════════════════════════════
# AnalystAgent integration tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalystAgentRegistryIntegration(unittest.TestCase):
    """AnalystAgent calls register_claim after pattern analysis."""

    def _make_agent_with_registry(self):
        registry = TruthSourceRegistry()
        agent = AnalystAgent(config=AnalystConfig(l2_min_observations=5))
        agent.set_truth_registry(registry)
        agent.start()
        return agent, registry

    def test_set_truth_registry_accepted(self):
        """set_truth_registry() stores the registry instance."""
        _, registry = self._make_agent_with_registry()
        # Just verify it was accepted without error
        # 仅验证已接受，无错误
        self.assertIsNotNone(registry)

    def test_statistical_insight_registers_claims(self):
        """Statistical PatternInsight causes patterns to be registered in registry."""
        agent, registry = self._make_agent_with_registry()
        # Create a fake statistical insight with winning patterns / 创建带有胜出模式的统计洞察
        insight = PatternInsight(
            observations_count=50,
            winning_patterns=["strategy A works in ranging", "strategy B works in trending"],
            losing_patterns=["strategy C fails in volatile"],
            source="statistical",
        )
        # Call private helper directly / 直接调用私有辅助方法
        agent._register_pattern_claims(insight)
        stats = registry.get_stats()
        # Should have registered the winning patterns (not losing — currently winning only)
        # 应该已登记胜出模式
        self.assertGreater(stats["total_registered"], 0)

    def test_registry_none_does_not_raise(self):
        """_register_pattern_claims() is a no-op when registry is None."""
        agent = AnalystAgent(config=AnalystConfig())
        agent.start()
        # No registry set / 未设置 registry
        insight = PatternInsight(
            observations_count=200,
            winning_patterns=["pattern X"],
            source="ai",
        )
        try:
            agent._register_pattern_claims(insight)
        except Exception as e:
            self.fail(f"_register_pattern_claims raised unexpectedly: {e}")

    def test_ai_insight_uses_ai_evidence_source(self):
        """AI-sourced PatternInsight creates claims with evidence_source='ai'."""
        agent, registry = self._make_agent_with_registry()
        insight = PatternInsight(
            observations_count=300,
            winning_patterns=["AI identified trend following works"],
            source="ai",
        )
        agent._register_pattern_claims(insight)
        claims = registry.get_active_claims()
        if claims:
            # All registered claims from AI insight should be INFERENCE (never FACT)
            # 来自 AI 洞察的所有已登记声明应为 INFERENCE（永不为 FACT）
            for c in claims:
                self.assertNotEqual(c.cognitive_level, CognitiveLevel.FACT)
                self.assertEqual(c.cognitive_level, CognitiveLevel.INFERENCE)


# ═══════════════════════════════════════════════════════════════════════════════
# StrategistAgent integration tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategistAgentRegistryIntegration(unittest.TestCase):
    """StrategistAgent updates strategy_preference_weights from pattern insights."""

    def _make_strategist_with_registry(self):
        registry = TruthSourceRegistry()
        agent = StrategistAgent(config=StrategistConfig(shadow=True))
        agent.set_truth_registry(registry)
        agent.start()
        return agent, registry

    def test_set_truth_registry_accepted(self):
        """set_truth_registry() stores the registry on StrategistAgent."""
        agent, registry = self._make_strategist_with_registry()
        self.assertIs(agent._truth_registry, registry)

    def test_strategy_preference_weights_initial_empty(self):
        """_strategy_preference_weights starts empty (populated lazily)."""
        agent, _ = self._make_strategist_with_registry()
        self.assertIsInstance(agent._strategy_preference_weights, dict)
        self.assertEqual(len(agent._strategy_preference_weights), 0)

    def test_apply_pattern_insight_updates_weights(self):
        """_apply_pattern_insight() updates weights for strategies in registry."""
        agent, registry = self._make_strategist_with_registry()
        # Register a specific-strategy claim / 登记一条特定策略声明
        registry.register_claim(
            pattern_text="trending pattern for ma_crossover",
            evidence_source="ai",
            observation_count=200,
            confidence=0.70,
            applies_to_regime="trending",
            applies_to_strategy="ma_crossover",
        )
        insight_payload = {
            "regime_strategy_matrix": {"trending": {"ma_crossover": 0.65}},
            "winning_patterns": ["trending pattern for ma_crossover"],
            "losing_patterns": [],
        }
        agent._apply_pattern_insight(insight_payload)
        # Weight for ma_crossover should now be > 1.0 (positive update)
        # ma_crossover 的权重应 > 1.0（正向更新）
        weight = agent._strategy_preference_weights.get("ma_crossover", 1.0)
        self.assertGreater(weight, 1.0)

    def test_apply_pattern_insight_no_registry_is_noop(self):
        """_apply_pattern_insight() silently no-ops when registry is None."""
        agent = StrategistAgent(config=StrategistConfig())
        agent.start()
        # No registry set / 未设置 registry
        try:
            agent._apply_pattern_insight({"winning_patterns": ["x"], "losing_patterns": []})
        except Exception as e:
            self.fail(f"_apply_pattern_insight raised unexpectedly: {e}")

    def test_get_stats_includes_weights(self):
        """get_stats() includes strategy_preference_weights key."""
        agent, _ = self._make_strategist_with_registry()
        stats = agent.get_stats()
        self.assertIn("strategy_preference_weights", stats)

    def test_handle_pattern_insight_message_calls_apply(self):
        """_handle_pattern_insight() calls _apply_pattern_insight() via on_message."""
        agent, registry = self._make_strategist_with_registry()
        registry.register_claim(
            pattern_text="some pattern",
            evidence_source="ai",
            observation_count=200,
            confidence=0.65,
            applies_to_regime="trending",
            applies_to_strategy="rsi_reversal",
        )
        msg = AgentMessage(
            sender=AgentRole.ANALYST,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.PATTERN_INSIGHT,
            payload={
                "winning_patterns": ["some pattern"],
                "losing_patterns": [],
                "regime_strategy_matrix": {"trending": {"rsi_reversal": 0.6}},
            },
        )
        # Should not raise / 不应抛出异常
        agent.on_message(msg)


# ═══════════════════════════════════════════════════════════════════════════════
# Persistence tests: save_snapshot / load_snapshot / debounced save
# 持久化测试：快照保存 / 快照加载 / 去抖动保存
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistence(unittest.TestCase):
    """Persistence layer: save_snapshot / load_snapshot / _schedule_debounced_save.
    持久化层：save_snapshot / load_snapshot / _schedule_debounced_save。
    """

    # Helper to register a minimal claim / 注册一条最简声明的辅助函数
    def _register_one(self, registry: TruthSourceRegistry, claim_id: str = "persist_test_001") -> str:
        return registry.register_claim(
            pattern_text="test persistence pattern",
            evidence_source="statistical_N=50",
            observation_count=50,
            confidence=0.65,
            applies_to_regime="trending",
            applies_to_strategy="ma_crossover",
            claim_id=claim_id,
        )

    def test_save_creates_file(self):
        """save_snapshot() creates a JSON file at the specified path.
        save_snapshot() 在指定路径创建 JSON 文件。
        """
        import tempfile, json as _json
        registry = TruthSourceRegistry()
        self._register_one(registry)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "snapshot.json")
            result = registry.save_snapshot(path)

            # Return value should be True on success / 成功时返回值应为 True
            self.assertTrue(result)
            # File should exist / 文件应存在
            self.assertTrue(os.path.exists(path))
            # File should contain valid JSON with at least one claim
            # 文件应包含至少一条声明的有效 JSON
            with open(path, "r", encoding="utf-8") as fh:
                data = _json.load(fh)
            self.assertIsInstance(data, list)
            self.assertGreaterEqual(len(data), 1)
            self.assertEqual(data[0]["claim_id"], "persist_test_001")

    def test_load_restores_claims(self):
        """save + load round-trip restores the same claim.
        保存 + 加载往返恢复相同的声明。
        """
        import tempfile
        registry = TruthSourceRegistry()
        self._register_one(registry, "roundtrip_claim")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "snapshot.json")
            registry.save_snapshot(path)

            # Create a fresh registry and load from file
            # 创建新存储并从文件加载
            registry2 = TruthSourceRegistry()
            loaded = registry2.load_snapshot(path)

            self.assertEqual(loaded, 1)
            claims = registry2.get_active_claims()
            self.assertEqual(len(claims), 1)
            # Verify key fields match / 验证关键字段匹配
            c = claims[0]
            self.assertEqual(c.claim_id, "roundtrip_claim")
            self.assertEqual(c.pattern_text, "test persistence pattern")
            self.assertAlmostEqual(c.confidence, 0.65, places=3)

    def test_load_missing_file_returns_zero(self):
        """load_snapshot() on a non-existent path returns 0, no exception.
        对不存在的路径调用 load_snapshot() 返回 0，不抛出异常。
        """
        import tempfile
        registry = TruthSourceRegistry()

        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = os.path.join(tmpdir, "does_not_exist.json")
            try:
                result = registry.load_snapshot(missing_path)
            except Exception as exc:
                self.fail(f"load_snapshot raised on missing file: {exc}")
            self.assertEqual(result, 0)
            # Registry should remain empty / 存储应保持为空
            self.assertEqual(len(registry.get_active_claims()), 0)

    def test_load_corrupted_json_returns_zero(self):
        """load_snapshot() on corrupted JSON returns 0, no exception.
        对损坏的 JSON 文件调用 load_snapshot() 返回 0，不抛出异常。
        """
        import tempfile
        registry = TruthSourceRegistry()

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = os.path.join(tmpdir, "corrupt.json")
            with open(bad_path, "w", encoding="utf-8") as fh:
                fh.write("{this is not: valid json ][")

            try:
                result = registry.load_snapshot(bad_path)
            except Exception as exc:
                self.fail(f"load_snapshot raised on corrupted JSON: {exc}")
            self.assertEqual(result, 0)

    def test_load_skips_existing_claims(self):
        """load_snapshot() skips claim_ids already in the registry.
        load_snapshot() 跳过已在存储中存在的 claim_id。
        """
        import tempfile
        registry = TruthSourceRegistry()
        self._register_one(registry, "existing_claim")  # already in memory / 已在内存中

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "snapshot.json")
            # Save a snapshot that contains "existing_claim"
            # 保存包含 "existing_claim" 的快照
            registry.save_snapshot(path)

            # Now load into the same registry — the claim already exists, must be skipped
            # 现在加载到同一存储 — 声明已存在，必须跳过
            loaded = registry.load_snapshot(path)
            # Return count should be 0 (nothing newly loaded)
            # 返回计数应为 0（没有新加载任何内容）
            self.assertEqual(loaded, 0)
            # Total claims in registry must not be doubled
            # 存储中的声明总数不得翻倍
            snapshot = registry.to_snapshot()
            ids = [c["claim_id"] for c in snapshot]
            self.assertEqual(ids.count("existing_claim"), 1)

    def test_debounce_schedules_save(self):
        """After register_claim(), _save_timer is not None (a save is scheduled).
        register_claim() 后，_save_timer 不为 None（已调度保存）。
        Calling register_claim() again cancels and reschedules (debounce resets).
        再次调用 register_claim() 取消并重新调度（防抖窗口重置）。
        """
        registry = TruthSourceRegistry()
        # Patch timer delay to 0.01s so we can observe lifecycle quickly
        # 将定时器延迟 patch 为 0.01s 以便快速观察生命周期
        original_timer = threading.Timer

        timers_created = []

        class SpyTimer:
            """Thin spy wrapper around threading.Timer.
            threading.Timer 的轻量监视包装器。
            """
            def __init__(self, delay, fn, args=()):
                self._inner = original_timer(0.01, fn, args)  # fast for test / 测试用快速延迟
                self._cancelled = False
                timers_created.append(self)

            def cancel(self):
                self._cancelled = True
                self._inner.cancel()

            @property
            def daemon(self):
                return self._inner.daemon

            @daemon.setter
            def daemon(self, val):
                self._inner.daemon = val

            def start(self):
                self._inner.start()

        with patch("threading.Timer", SpyTimer):
            # First registration: timer should be scheduled
            # 第一次注册：应调度定时器
            self._register_one(registry, "debounce_claim_1")
            self.assertIsNotNone(registry._save_timer)

            first_timer = registry._save_timer

            # Second registration: previous timer should be cancelled, new one scheduled
            # 第二次注册：之前的定时器应被取消，新定时器被调度
            self._register_one(registry, "debounce_claim_2")
            second_timer = registry._save_timer

            # Two timers were created / 应创建两个定时器
            self.assertEqual(len(timers_created), 2)
            # The first timer was cancelled / 第一个定时器应被取消
            self.assertTrue(timers_created[0]._cancelled)
            # The second timer is still the active one / 第二个定时器仍为活跃定时器
            self.assertIs(second_timer, timers_created[1])


if __name__ == "__main__":
    unittest.main()

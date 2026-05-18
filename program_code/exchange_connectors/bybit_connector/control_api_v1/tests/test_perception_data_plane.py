"""
Tests for T2.11 — Perception Data Plane: Fact/Inference Marking (GAP-M2)
=========================================================================
Governance refs: EX-07 §1-§8, DOC-01 §5.10

P2-PERCEPTION-DEPRECATE-1 (2026-05-18)：`validate_for_decision` 已 deprecated；
本檔保留為 governance regression baseline，整檔過濾 DeprecationWarning 噪音。
"""

import time
import threading
import pytest

pytestmark = pytest.mark.filterwarnings(
    "ignore::DeprecationWarning:app.perception_data_plane"
)

from app.perception_data_plane import (
    AccessLevel,
    AGENT_DATA_ACCESS,
    CognitiveLevel,
    DATA_CATEGORIES,
    DataQuality,
    DataSourceType,
    DegradationAction,
    Freshness,
    FRESHNESS_THRESHOLDS,
    PerceptionDataObject,
    PerceptionPlane,
    SOURCE_COGNITIVE_DEFAULTS,
    calculate_freshness,
    check_data_access,
)


# ─────────────────────────────────────────────
# 1. Cognitive Level Constants
# ─────────────────────────────────────────────

class TestCognitiveLevel:
    """EX-07 §1 / DOC-01 §5.10 — three cognitive levels."""

    def test_three_levels(self):
        assert len(CognitiveLevel) == 3

    def test_values(self):
        assert CognitiveLevel.FACT.value == "fact"
        assert CognitiveLevel.INFERENCE.value == "inference"
        assert CognitiveLevel.HYPOTHESIS.value == "hypothesis"

    def test_exchange_data_is_fact(self):
        """EX-07 §1: exchange API data = fact."""
        assert SOURCE_COGNITIVE_DEFAULTS[DataSourceType.EXCHANGE_REST] == CognitiveLevel.FACT
        assert SOURCE_COGNITIVE_DEFAULTS[DataSourceType.EXCHANGE_WS] == CognitiveLevel.FACT

    def test_search_data_is_inference(self):
        """EX-07 §1: AI/search data = inference."""
        assert SOURCE_COGNITIVE_DEFAULTS[DataSourceType.SEARCH_PERPLEXITY] == CognitiveLevel.INFERENCE
        assert SOURCE_COGNITIVE_DEFAULTS[DataSourceType.SEARCH_WEB] == CognitiveLevel.INFERENCE
        assert SOURCE_COGNITIVE_DEFAULTS[DataSourceType.LOCAL_OLLAMA] == CognitiveLevel.INFERENCE

    def test_local_indicator_is_fact(self):
        """EX-07 TABLE 1: local computed indicators = fact."""
        assert SOURCE_COGNITIVE_DEFAULTS[DataSourceType.LOCAL_INDICATOR] == CognitiveLevel.FACT


# ─────────────────────────────────────────────
# 2. Freshness
# ─────────────────────────────────────────────

class TestFreshness:
    """EX-07 §2.1 TABLE 2."""

    def test_four_levels(self):
        assert len(Freshness) == 4

    def test_fresh_data(self):
        now_ms = int(time.time() * 1000)
        assert calculate_freshness(now_ms) == Freshness.FRESH

    def test_recent_data(self):
        ten_min_ago = int(time.time() * 1000) - 600_000  # 10 min
        assert calculate_freshness(ten_min_ago) == Freshness.RECENT

    def test_stale_data(self):
        one_hour_ago = int(time.time() * 1000) - 3_600_000  # 60 min
        assert calculate_freshness(one_hour_ago) == Freshness.STALE

    def test_expired_data(self):
        three_hours_ago = int(time.time() * 1000) - 10_800_000  # 3 hours
        assert calculate_freshness(three_hours_ago) == Freshness.EXPIRED

    def test_thresholds(self):
        assert FRESHNESS_THRESHOLDS[Freshness.FRESH] == 300
        assert FRESHNESS_THRESHOLDS[Freshness.RECENT] == 1800
        assert FRESHNESS_THRESHOLDS[Freshness.STALE] == 7200


# ─────────────────────────────────────────────
# 3. Data Quality
# ─────────────────────────────────────────────

class TestDataQuality:

    def test_perfect_quality(self):
        dq = DataQuality(completeness=1.0, consistency=1.0, latency_ms=0, source_reliability=1.0)
        assert dq.overall_score == 1.0

    def test_low_quality(self):
        dq = DataQuality(completeness=0.0, consistency=0.0, latency_ms=10000, source_reliability=0.0)
        assert dq.overall_score == 0.0

    def test_mixed_quality(self):
        dq = DataQuality(completeness=0.8, consistency=0.9, latency_ms=500, source_reliability=0.7)
        score = dq.overall_score
        assert 0.5 < score < 1.0

    def test_serialization(self):
        dq = DataQuality(completeness=0.95, consistency=0.9, latency_ms=100, source_reliability=1.0)
        d = dq.to_dict()
        assert "overall_score" in d
        assert d["completeness"] == 0.95


# ─────────────────────────────────────────────
# 4. Perception Data Object
# ─────────────────────────────────────────────

class TestPerceptionDataObject:

    def test_creation(self):
        pdo = PerceptionDataObject(
            source_type=DataSourceType.EXCHANGE_REST,
            cognitive_level=CognitiveLevel.FACT,
            content={"price": 60000},
            symbols=["BTC"],
        )
        assert pdo.data_id.startswith("pdo_")
        assert pdo.cognitive_level == CognitiveLevel.FACT

    def test_decision_eligible_fact_fresh(self):
        pdo = PerceptionDataObject(
            cognitive_level=CognitiveLevel.FACT,
            freshness=Freshness.FRESH,
        )
        assert pdo.is_decision_eligible() is True

    def test_decision_eligible_inference_fresh(self):
        """Inference is eligible IF marked and not expired."""
        pdo = PerceptionDataObject(
            cognitive_level=CognitiveLevel.INFERENCE,
            freshness=Freshness.RECENT,
        )
        assert pdo.is_decision_eligible() is True

    def test_expired_not_eligible(self):
        """EX-07 §2.1: EXPIRED data cannot enter decision chain."""
        pdo = PerceptionDataObject(
            cognitive_level=CognitiveLevel.FACT,
            freshness=Freshness.EXPIRED,
        )
        assert pdo.is_decision_eligible() is False

    def test_refresh_freshness(self):
        pdo = PerceptionDataObject(
            fetched_at_ms=int(time.time() * 1000),
        )
        result = pdo.refresh_freshness()
        assert result == Freshness.FRESH

    def test_serialization(self):
        pdo = PerceptionDataObject(
            source_type=DataSourceType.SEARCH_PERPLEXITY,
            cognitive_level=CognitiveLevel.INFERENCE,
            symbols=["ETH"],
            marked_by="scout",
            marking_reason="Search result",
        )
        d = pdo.to_dict()
        assert d["cognitive_level"] == "inference"
        assert d["source_type"] == "search_perplexity"
        assert d["marked_by"] == "scout"
        assert "is_decision_eligible" in d


# ─────────────────────────────────────────────
# 5. Agent Data Access (EX-07 §6)
# ─────────────────────────────────────────────

class TestAgentDataAccess:

    def test_scout_no_account_access(self):
        """EX-07 §6: Scout cannot access account/position data."""
        assert check_data_access("scout", "exchange_account") is False

    def test_scout_can_read_search(self):
        assert check_data_access("scout", "search_results") is True

    def test_scout_can_write_search(self):
        assert check_data_access("scout", "search_results", write=True) is True

    def test_executor_no_search_access(self):
        """EX-07 §6: Executor cannot access search results."""
        assert check_data_access("executor", "search_results") is False

    def test_guardian_can_write_p2(self):
        """Guardian has read-write on P2 risk params."""
        assert check_data_access("guardian", "risk_params_p2", write=True) is True

    def test_guardian_cannot_write_p0p1(self):
        """P0/P1 are read-only for all agents."""
        assert check_data_access("guardian", "risk_params_p0p1", write=True) is False

    def test_strategist_read_all_except_none(self):
        """Strategist has read access to most categories."""
        for cat in DATA_CATEGORIES:
            # Strategist can at least read everything
            assert check_data_access("strategist", cat) is True

    def test_analyst_can_write_learning(self):
        assert check_data_access("analyst", "learning_records", write=True) is True

    def test_all_agents_covered(self):
        """All 5 agents x 8 categories = 40 entries."""
        assert len(AGENT_DATA_ACCESS) == 40


# ─────────────────────────────────────────────
# 6. Perception Plane Engine
# ─────────────────────────────────────────────

class TestPerceptionPlaneRegistration:

    def test_register_fact(self):
        pp = PerceptionPlane()
        pdo = pp.register_data(
            DataSourceType.EXCHANGE_REST,
            {"price": 60000},
            symbols=["BTC"],
            source_detail="/v5/market/tickers",
        )
        assert pdo is not None
        assert pdo.cognitive_level == CognitiveLevel.FACT
        stats = pp.get_stats()
        assert stats["facts"] == 1

    def test_register_inference(self):
        pp = PerceptionPlane()
        pdo = pp.register_data(
            DataSourceType.SEARCH_PERPLEXITY,
            {"headline": "BTC may rally"},
            symbols=["BTC"],
        )
        assert pdo.cognitive_level == CognitiveLevel.INFERENCE
        stats = pp.get_stats()
        assert stats["inferences"] == 1

    def test_auto_default_cognitive_level(self):
        """If no level specified, uses source default."""
        pp = PerceptionPlane()
        pdo = pp.register_data(DataSourceType.EXCHANGE_WS, {"price": 60001})
        assert pdo.cognitive_level == CognitiveLevel.FACT

    def test_drift_search_as_fact_corrected(self):
        """EX-07 §7: search data marked as fact triggers drift warning + override."""
        pp = PerceptionPlane()
        pdo = pp.register_data(
            DataSourceType.SEARCH_WEB,
            {"headline": "test"},
            cognitive_level=CognitiveLevel.FACT,  # WRONG — should be inference
        )
        # Should be corrected to INFERENCE
        assert pdo.cognitive_level == CognitiveLevel.INFERENCE
        # Drift warning recorded
        warnings = pp.check_drift()
        assert len(warnings) == 1
        assert warnings[0].drift_type == "inference_as_fact"
        assert warnings[0].severity == "critical"

    def test_audit_callback(self):
        audited = []
        pp = PerceptionPlane(audit_callback=lambda a, d: audited.append((a, d)))
        pp.register_data(DataSourceType.EXCHANGE_REST, {"price": 50000})
        assert len(audited) == 1
        assert audited[0][0] == "data_registered"


class TestPerceptionPlaneRetrieval:

    def test_get_data(self):
        pp = PerceptionPlane()
        pdo = pp.register_data(DataSourceType.EXCHANGE_REST, {"price": 60000})
        retrieved = pp.get_data(pdo.data_id)
        assert retrieved is not None
        assert retrieved.data_id == pdo.data_id

    def test_get_data_not_found(self):
        pp = PerceptionPlane()
        assert pp.get_data("nonexistent") is None

    def test_get_data_agent_access_denied(self):
        """Scout cannot access exchange_account data."""
        pp = PerceptionPlane()
        pdo = pp.register_data(
            DataSourceType.EXCHANGE_REST,
            {"balance": 100000},
            source_detail="/v5/account/wallet-balance",
        )
        # Scout should be denied (exchange_account maps to NONE for scout)
        result = pp.get_data(pdo.data_id, agent_role="scout")
        assert result is None
        stats = pp.get_stats()
        assert stats["access_denied"] == 1

    def test_get_decision_eligible(self):
        pp = PerceptionPlane()
        pp.register_data(DataSourceType.EXCHANGE_REST, {"price": 60000}, symbols=["BTC"])
        pp.register_data(DataSourceType.SEARCH_PERPLEXITY, {"headline": "test"}, symbols=["BTC"])
        eligible = pp.get_decision_eligible_data(symbols=["BTC"])
        assert len(eligible) == 2  # Both are marked and fresh


class TestPerceptionPlaneValidation:

    def test_validate_eligible(self):
        pp = PerceptionPlane()
        pdo = pp.register_data(DataSourceType.EXCHANGE_REST, {"price": 60000})
        ok, reason = pp.validate_for_decision(pdo.data_id)
        assert ok is True

    def test_validate_not_found(self):
        pp = PerceptionPlane()
        ok, reason = pp.validate_for_decision("missing")
        assert ok is False
        assert "not found" in reason.lower()

    def test_validate_expired(self):
        pp = PerceptionPlane()
        pdo = pp.register_data(DataSourceType.EXCHANGE_REST, {"price": 60000})
        # Force to expired
        pdo.fetched_at_ms = int(time.time() * 1000) - 10_800_000  # 3 hours ago
        ok, reason = pp.validate_for_decision(pdo.data_id)
        assert ok is False
        assert "expired" in reason.lower()

    def test_validate_low_quality(self):
        pp = PerceptionPlane()
        pdo = pp.register_data(
            DataSourceType.EXCHANGE_REST,
            {"price": 60000},
            data_quality=DataQuality(
                completeness=0.0, consistency=0.0, latency_ms=10000, source_reliability=0.0
            ),
        )
        ok, reason = pp.validate_for_decision(pdo.data_id)
        assert ok is False
        assert "quality" in reason.lower()


class TestDegradation:
    """EX-07 §2.3 — data quality driven risk degradation."""

    def test_normal(self):
        pp = PerceptionPlane()
        assert pp.assess_degradation() == DegradationAction.NONE

    def test_rest_failures(self):
        pp = PerceptionPlane()
        assert pp.assess_degradation(rest_consecutive_failures=3) == DegradationAction.DEFENSIVE

    def test_ws_disconnect_5min(self):
        pp = PerceptionPlane()
        assert pp.assess_degradation(ws_disconnect_seconds=301) == DegradationAction.REDUCED

    def test_ws_disconnect_30sec(self):
        pp = PerceptionPlane()
        assert pp.assess_degradation(ws_disconnect_seconds=31) == DegradationAction.NO_NEW_ENTRY

    def test_stale_price_data(self):
        pp = PerceptionPlane()
        # Register stale price data
        pdo = pp.register_data(
            DataSourceType.EXCHANGE_REST,
            {"price": 60000},
            metadata={"data_type": "price"},
        )
        pdo.fetched_at_ms = int(time.time() * 1000) - 3_600_000  # 1 hour ago
        assert pp.assess_degradation("price") == DegradationAction.NO_NEW_ENTRY

    def test_expired_price_data(self):
        pp = PerceptionPlane()
        pdo = pp.register_data(
            DataSourceType.EXCHANGE_REST,
            {"price": 60000},
            metadata={"data_type": "price"},
        )
        pdo.fetched_at_ms = int(time.time() * 1000) - 10_800_000  # 3 hours
        assert pp.assess_degradation("price") == DegradationAction.CAUTIOUS


# ─────────────────────────────────────────────
# 7. Drift Protection (EX-07 §7)
# ─────────────────────────────────────────────

class TestDriftProtection:

    def test_inference_as_fact_drift(self):
        pp = PerceptionPlane()
        pp.register_data(
            DataSourceType.LOCAL_OLLAMA,
            {"sentiment": "positive"},
            cognitive_level=CognitiveLevel.FACT,
        )
        warnings = pp.check_drift()
        assert len(warnings) == 1
        assert "inference_as_fact" in warnings[0].drift_type

    def test_no_drift_for_exchange_fact(self):
        pp = PerceptionPlane()
        pp.register_data(
            DataSourceType.EXCHANGE_REST,
            {"price": 60000},
            cognitive_level=CognitiveLevel.FACT,
        )
        warnings = pp.check_drift()
        assert len(warnings) == 0

    def test_perplexity_fact_corrected(self):
        """Perplexity search marked as fact → corrected + warning."""
        pp = PerceptionPlane()
        pdo = pp.register_data(
            DataSourceType.SEARCH_PERPLEXITY,
            {"news": "BTC rally"},
            cognitive_level=CognitiveLevel.FACT,
        )
        assert pdo.cognitive_level == CognitiveLevel.INFERENCE
        assert pp.get_stats()["drift_warnings"] == 1


# ─────────────────────────────────────────────
# 8. Thread Safety
# ─────────────────────────────────────────────

class TestThreadSafety:

    def test_concurrent_registration(self):
        pp = PerceptionPlane()
        errors = []

        def register_batch(n):
            try:
                for i in range(n):
                    pp.register_data(
                        DataSourceType.EXCHANGE_WS,
                        {"price": 60000 + i},
                        symbols=["BTC"],
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_batch, args=(20,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = pp.get_stats()
        assert stats["total_objects"] == 100


# ─────────────────────────────────────────────
# 9. Edge Cases
# ─────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_perception_plane(self):
        pp = PerceptionPlane()
        assert pp.get_decision_eligible_data() == []
        stats = pp.get_stats()
        assert stats["total_objects"] == 0

    def test_unknown_agent_role_denied(self):
        assert check_data_access("unknown_agent", "exchange_price") is False

    def test_hypothesis_level(self):
        pp = PerceptionPlane()
        pdo = pp.register_data(
            DataSourceType.LEARNING_HISTORY,
            {"pattern": "squeeze tends to break up"},
            cognitive_level=CognitiveLevel.HYPOTHESIS,
            marked_by="analyst",
            marking_reason="Limited data support",
        )
        assert pdo.cognitive_level == CognitiveLevel.HYPOTHESIS
        stats = pp.get_stats()
        assert stats["hypotheses"] == 1

    def test_data_quality_serialization(self):
        dq = DataQuality()
        d = dq.to_dict()
        assert isinstance(d["overall_score"], float)


# ─────────────────────────────────────────────
# T2.02: Integration Tests — Perception Plane + Intent Pipeline
# ─────────────────────────────────────────────

class TestPerceptionPlaneIntegration:
    """T2.02: Test PerceptionPlane integration with intent processing"""

    def test_perception_plane_validates_unmarked_data(self):
        """T2.02: Unmarked inference cannot enter decision chain (EX-07 §1)"""
        pp = PerceptionPlane()

        # Register data without explicit cognitive level (search data without explicit marking)
        pdo = pp.register_data(
            source_type=DataSourceType.SEARCH_PERPLEXITY,
            content={"signal": "bullish"},
            cognitive_level=None,  # Will auto-default to INFERENCE
        )
        assert pdo is not None

        # Since it defaults to INFERENCE for search data, it will pass validation
        # (marked by default). Let's test with a PDO that has no cognitive level
        data_id = pdo.data_id
        pdo.cognitive_level = None  # Manually unmark it

        # Validation should fail
        eligible, reason = pp.validate_for_decision(data_id)
        assert not eligible
        assert "No cognitive level marking" in reason

    def test_perception_plane_validates_marked_fact_data(self):
        """T2.02: Marked FACT data passes validation"""
        pp = PerceptionPlane()

        # Register marked FACT data (exchange)
        pdo = pp.register_data(
            source_type=DataSourceType.EXCHANGE_REST,
            content={"price": 50000},
            cognitive_level=CognitiveLevel.FACT,
        )
        assert pdo is not None
        data_id = pdo.data_id

        # Validation should pass
        eligible, reason = pp.validate_for_decision(data_id)
        assert eligible
        assert "fact" in reason.lower()

    def test_perception_plane_validates_marked_inference_data(self):
        """T2.02: Marked INFERENCE data passes validation"""
        pp = PerceptionPlane()

        # Register marked INFERENCE data
        pdo = pp.register_data(
            source_type=DataSourceType.SEARCH_PERPLEXITY,
            content={"sentiment": "positive"},
            cognitive_level=CognitiveLevel.INFERENCE,
        )
        assert pdo is not None
        data_id = pdo.data_id

        # Validation should pass (marked, even if inference)
        eligible, reason = pp.validate_for_decision(data_id)
        assert eligible
        assert "inference" in reason.lower()

    def test_perception_plane_rejects_expired_data(self):
        """T2.02: Expired data (>2h) rejected from decision chain"""
        pp = PerceptionPlane()

        # Register old data (3 hours ago)
        three_hours_ago = int(time.time() * 1000) - 10_800_000
        pdo = pp.register_data(
            source_type=DataSourceType.EXCHANGE_REST,
            content={"price": 50000},
            cognitive_level=CognitiveLevel.FACT,
        )
        assert pdo is not None
        # Manually set old timestamp
        pdo.fetched_at_ms = three_hours_ago
        data_id = pdo.data_id

        # Validation should fail due to expiration
        eligible, reason = pp.validate_for_decision(data_id)
        assert not eligible
        assert "expired" in reason.lower()

    def test_perception_plane_accepts_fresh_data(self):
        """T2.02: Fresh data (<5min) passes validation"""
        pp = PerceptionPlane()

        # Register fresh data (just now)
        pdo = pp.register_data(
            source_type=DataSourceType.EXCHANGE_WS,
            content={"price": 50000},
            cognitive_level=CognitiveLevel.FACT,
        )
        assert pdo is not None
        data_id = pdo.data_id

        # Validation should pass
        eligible, reason = pp.validate_for_decision(data_id)
        assert eligible
        assert "fact" in reason.lower()

    def test_perception_plane_data_store_grows(self):
        """T2.02: PerceptionPlane stores multiple data objects"""
        pp = PerceptionPlane()

        # Register many data objects
        for i in range(5):
            pdo = pp.register_data(
                source_type=DataSourceType.EXCHANGE_REST,
                content={"price": 50000 + i},
                cognitive_level=CognitiveLevel.FACT,
            )
            assert pdo is not None

        # Store should contain all objects
        stats = pp.get_stats()
        assert stats["total_objects"] == 5
        assert stats["facts"] == 5

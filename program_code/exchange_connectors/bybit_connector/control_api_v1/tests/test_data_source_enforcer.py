"""
Tests for T2.16 — Data Source Enforcer: External Data Marking Enforcement (GAP-M7)
===================================================================================
Governance refs: DOC-01 §5.10 (Root Principle #8: Cognitive Honesty)

Tests cover:
  - DataSourceTag creation and immutability
  - DataSourceClassifier: auto-classification by source type and URL pattern
  - DataSourceEnforcer: tagging, validation, rejection, statistics
  - Pipeline integration points: exchange, search, AI output, indicators
  - Thread safety
  - Audit callback integration
  - Edge cases and error handling
"""

import time
import threading
import pytest
from typing import List, Dict, Any

from app.data_source_enforcer import (
    DataSourceTag,
    DataSourceClassifier,
    DataSourceEnforcer,
)
from app.perception_data_plane import (
    CognitiveLevel,
    DataSourceType,
)


# ─────────────────────────────────────────────
# 1. DataSourceTag Tests
# ─────────────────────────────────────────────

class TestDataSourceTag:
    """Tests for immutable DataSourceTag dataclass."""

    def test_tag_creation(self):
        """Create a basic tag."""
        tag = DataSourceTag(
            tag_id="tag_test_001",
            source_url_or_api="https://api.bybit.com/v5/market/tickers",
            fetched_at_ms=int(time.time() * 1000),
            cognitive_level=CognitiveLevel.FACT,
            confidence=0.99,
            tagged_by="bybit_connector",
            tag_reason="Bybit REST API → FACT",
        )
        assert tag.tag_id == "tag_test_001"
        assert tag.cognitive_level == CognitiveLevel.FACT
        assert tag.confidence == 0.99
        assert tag.is_external is True

    def test_tag_immutability(self):
        """Tags are frozen and cannot be modified."""
        tag = DataSourceTag(
            tag_id="tag_test_002",
            source_url_or_api="https://example.com",
            fetched_at_ms=int(time.time() * 1000),
            cognitive_level=CognitiveLevel.INFERENCE,
            confidence=0.75,
            tagged_by="enforcer",
            tag_reason="Test",
        )
        with pytest.raises(AttributeError):
            tag.cognitive_level = CognitiveLevel.FACT

    def test_tag_to_dict(self):
        """Serialization to dict for audit logging."""
        tag = DataSourceTag(
            tag_id="tag_test_003",
            source_url_or_api="https://api.bybit.com/v5/account",
            fetched_at_ms=1000,
            cognitive_level=CognitiveLevel.FACT,
            confidence=0.95,
            tagged_by="enforcer",
            tag_reason="Exchange account data",
        )
        d = tag.to_dict()
        assert d["tag_id"] == "tag_test_003"
        assert d["cognitive_level"] == "fact"
        assert d["confidence"] == 0.95
        assert d["is_external"] is True


# ─────────────────────────────────────────────
# 2. DataSourceClassifier Tests
# ─────────────────────────────────────────────

class TestDataSourceClassifier:
    """Tests for automatic source classification."""

    # ── By Source Type ──

    def test_classify_bybit_rest(self):
        """Bybit REST → FACT with high confidence."""
        level, confidence, reason = DataSourceClassifier.classify_by_type(
            DataSourceType.EXCHANGE_REST
        )
        assert level == CognitiveLevel.FACT
        assert confidence >= 0.95
        assert "FACT" in reason

    def test_classify_bybit_ws(self):
        """Bybit WebSocket → FACT with high confidence."""
        level, confidence, reason = DataSourceClassifier.classify_by_type(
            DataSourceType.EXCHANGE_WS
        )
        assert level == CognitiveLevel.FACT
        assert confidence >= 0.95

    def test_classify_perplexity(self):
        """Perplexity search → INFERENCE."""
        level, confidence, reason = DataSourceClassifier.classify_by_type(
            DataSourceType.SEARCH_PERPLEXITY
        )
        assert level == CognitiveLevel.INFERENCE
        assert 0.5 <= confidence <= 0.9
        assert "INFERENCE" in reason

    def test_classify_duckduckgo(self):
        """Web search → INFERENCE."""
        level, confidence, reason = DataSourceClassifier.classify_by_type(
            DataSourceType.SEARCH_WEB
        )
        assert level == CognitiveLevel.INFERENCE
        assert 0.5 <= confidence <= 0.9

    def test_classify_ollama(self):
        """Ollama output → INFERENCE."""
        level, confidence, reason = DataSourceClassifier.classify_by_type(
            DataSourceType.LOCAL_OLLAMA
        )
        assert level == CognitiveLevel.INFERENCE
        assert 0.5 <= confidence <= 0.9

    def test_classify_local_indicator(self):
        """Local indicator (MA, RSI, BB) → FACT."""
        level, confidence, reason = DataSourceClassifier.classify_by_type(
            DataSourceType.LOCAL_INDICATOR
        )
        assert level == CognitiveLevel.FACT
        assert confidence >= 0.90

    def test_classify_event_calendar(self):
        """Event calendar → INFERENCE (conservative)."""
        level, confidence, reason = DataSourceClassifier.classify_by_type(
            DataSourceType.EVENT_CALENDAR
        )
        assert level == CognitiveLevel.INFERENCE

    def test_classify_learning_history(self):
        """Learning patterns → INFERENCE."""
        level, confidence, reason = DataSourceClassifier.classify_by_type(
            DataSourceType.LEARNING_HISTORY
        )
        assert level == CognitiveLevel.INFERENCE

    # ── By URL Pattern ──

    def test_classify_bybit_api_url(self):
        """Official Bybit API URL → FACT."""
        result = DataSourceClassifier.classify_by_url_pattern(
            "https://api.bybit.com/v5/market/tickers"
        )
        assert result is not None
        level, confidence, reason = result
        assert level == CognitiveLevel.FACT
        assert confidence >= 0.95

    def test_classify_bybit_stream_url(self):
        """Bybit WebSocket stream URL → FACT."""
        result = DataSourceClassifier.classify_by_url_pattern(
            "wss://stream.bybit.com/v5/public/spot"
        )
        assert result is not None
        level, confidence, reason = result
        assert level == CognitiveLevel.FACT

    def test_classify_perplexity_url(self):
        """Perplexity URL → INFERENCE."""
        result = DataSourceClassifier.classify_by_url_pattern(
            "https://api.perplexity.com/search?q=bitcoin"
        )
        assert result is not None
        level, confidence, reason = result
        assert level == CognitiveLevel.INFERENCE

    def test_classify_duckduckgo_url(self):
        """DuckDuckGo URL → INFERENCE."""
        result = DataSourceClassifier.classify_by_url_pattern(
            "https://duckduckgo.com/?q=ethereum"
        )
        assert result is not None
        level, confidence, reason = result
        assert level == CognitiveLevel.INFERENCE

    def test_classify_news_url(self):
        """News site URL → INFERENCE."""
        result = DataSourceClassifier.classify_by_url_pattern(
            "https://www.reuters.com/finance/crypto/"
        )
        assert result is not None
        level, confidence, reason = result
        assert level == CognitiveLevel.INFERENCE

    def test_classify_unknown_url(self):
        """Unknown URL → returns None."""
        result = DataSourceClassifier.classify_by_url_pattern(
            "https://example-unknown-domain.com/data"
        )
        assert result is None


# ─────────────────────────────────────────────
# 3. DataSourceEnforcer: Core Functionality
# ─────────────────────────────────────────────

class TestDataSourceEnforcerBasic:
    """Basic enforcer operations."""

    def test_enforcer_creation(self):
        """Create an enforcer instance."""
        enforcer = DataSourceEnforcer()
        assert enforcer is not None
        stats = enforcer.get_stats()
        assert stats["total_tagged"] == 0
        assert stats["total_rejected"] == 0

    def test_validate_and_tag_bybit_rest(self):
        """Tag a Bybit REST response."""
        enforcer = DataSourceEnforcer()
        tag = enforcer.validate_and_tag(
            data_id="response_001",
            source_type=DataSourceType.EXCHANGE_REST,
            source_url_or_api="https://api.bybit.com/v5/market/tickers",
        )
        assert tag.cognitive_level == CognitiveLevel.FACT
        assert tag.confidence >= 0.95
        assert tag.is_external is True

        # Verify stored
        stored_tag = enforcer.get_tag("response_001")
        assert stored_tag == tag

    def test_validate_and_tag_with_override(self):
        """Provide explicit cognitive_level override."""
        enforcer = DataSourceEnforcer()
        tag = enforcer.validate_and_tag(
            data_id="response_002",
            source_type=DataSourceType.SEARCH_PERPLEXITY,
            source_url_or_api="https://api.perplexity.com/search",
            cognitive_level=CognitiveLevel.HYPOTHESIS,  # Override
            confidence=0.50,
        )
        assert tag.cognitive_level == CognitiveLevel.HYPOTHESIS
        assert tag.confidence == 0.50

    def test_get_tag_not_found(self):
        """Get tag for untagged data returns None."""
        enforcer = DataSourceEnforcer()
        tag = enforcer.get_tag("nonexistent")
        assert tag is None

    def test_validate_empty_data_id(self):
        """Empty data_id raises ValueError."""
        enforcer = DataSourceEnforcer()
        with pytest.raises(ValueError, match="data_id cannot be empty"):
            enforcer.validate_and_tag(
                data_id="",
                source_type=DataSourceType.EXCHANGE_REST,
            )


# ─────────────────────────────────────────────
# 4. DataSourceEnforcer: Rejection & Validation
# ─────────────────────────────────────────────

class TestDataSourceEnforcerRejection:
    """Tests for reject_untagged_data."""

    def test_reject_untagged_raise(self):
        """Untagged data raises ValueError in strict mode."""
        enforcer = DataSourceEnforcer(strict_mode=True)
        with pytest.raises(ValueError, match="is not tagged"):
            enforcer.reject_untagged_data("untagged_001", raise_on_untagged=True)

    def test_reject_untagged_return_false(self):
        """Untagged data returns False in non-raising mode."""
        enforcer = DataSourceEnforcer(strict_mode=False)
        is_tagged, reason = enforcer.reject_untagged_data(
            "untagged_002", raise_on_untagged=False
        )
        assert is_tagged is False
        assert "not tagged" in reason

    def test_accept_tagged_data(self):
        """Tagged data passes validation."""
        enforcer = DataSourceEnforcer()
        enforcer.validate_and_tag(
            data_id="response_003",
            source_type=DataSourceType.EXCHANGE_REST,
        )
        is_tagged, reason = enforcer.reject_untagged_data("response_003", raise_on_untagged=True)
        assert is_tagged is True
        assert "properly tagged" in reason

    def test_rejection_increments_stats(self):
        """Rejecting untagged data increments rejected_count."""
        enforcer = DataSourceEnforcer()
        stats_before = enforcer.get_stats()
        assert stats_before["total_rejected"] == 0

        try:
            enforcer.reject_untagged_data("untagged_003", raise_on_untagged=True)
        except ValueError:
            pass

        stats_after = enforcer.get_stats()
        assert stats_after["total_rejected"] == 1


# ─────────────────────────────────────────────
# 5. DataSourceEnforcer: Pipeline Integration
# ─────────────────────────────────────────────

class TestDataSourceEnforcerPipeline:
    """Tests for pipeline integration points."""

    def test_wrap_exchange_response_rest(self):
        """Wrap Bybit REST exchange response."""
        enforcer = DataSourceEnforcer()
        response_data = {"symbol": "BTCUSDT", "price": 50000}

        tag, data = enforcer.wrap_exchange_response(
            data_id="ex_001",
            endpoint="/v5/market/tickers",
            response_data=response_data,
        )

        assert tag.cognitive_level == CognitiveLevel.FACT
        assert tag.confidence >= 0.95
        assert data == response_data
        assert "api.bybit.com" in tag.source_url_or_api or "EXCHANGE_REST" in tag.tag_reason

    def test_wrap_exchange_response_ws(self):
        """Wrap Bybit WebSocket exchange response."""
        enforcer = DataSourceEnforcer()
        response_data = {"trade": {"price": 49500}}

        tag, data = enforcer.wrap_exchange_response(
            data_id="ws_001",
            endpoint="/v5/ws/stream",
            response_data=response_data,
        )

        assert tag.cognitive_level == CognitiveLevel.FACT
        assert data == response_data

    def test_wrap_search_result_perplexity(self):
        """Wrap Perplexity search result."""
        enforcer = DataSourceEnforcer()
        result_data = {"summary": "Bitcoin news...", "sources": [...]}

        tag, data = enforcer.wrap_search_result(
            data_id="search_001",
            search_engine="perplexity",
            query="bitcoin market sentiment",
            result_data=result_data,
        )

        assert tag.cognitive_level == CognitiveLevel.INFERENCE
        assert 0.5 <= tag.confidence <= 0.95
        assert data == result_data
        assert "search://" in tag.source_url_or_api

    def test_wrap_search_result_duckduckgo(self):
        """Wrap DuckDuckGo search result."""
        enforcer = DataSourceEnforcer()
        result_data = {"results": [{"title": "...", "url": "..."}]}

        tag, data = enforcer.wrap_search_result(
            data_id="search_002",
            search_engine="duckduckgo",
            query="ethereum analysis",
            result_data=result_data,
        )

        assert tag.cognitive_level == CognitiveLevel.INFERENCE
        assert data == result_data

    def test_wrap_ai_output_ollama(self):
        """Wrap Ollama model output."""
        enforcer = DataSourceEnforcer()
        ai_output = {"sentiment": "bullish", "score": 0.75}

        tag, data = enforcer.wrap_ai_output(
            data_id="ai_001",
            model_name="ollama:llama2",
            prompt_used="Analyze market sentiment",
            output_data=ai_output,
        )

        assert tag.cognitive_level == CognitiveLevel.INFERENCE
        assert data == ai_output
        assert "ai_model://" in tag.source_url_or_api

    def test_wrap_ai_output_cloud(self):
        """Wrap cloud AI model output."""
        enforcer = DataSourceEnforcer()
        ai_output = {"decision": "BUY", "confidence": 0.85}

        tag, data = enforcer.wrap_ai_output(
            data_id="ai_002",
            model_name="claude-haiku",
            prompt_used="Decide trade action",
            output_data=ai_output,
        )

        assert tag.cognitive_level == CognitiveLevel.INFERENCE
        assert data == ai_output

    def test_wrap_computed_indicator(self):
        """Wrap computed trading indicator."""
        enforcer = DataSourceEnforcer()
        indicator_value = 50.5

        tag, data = enforcer.wrap_computed_indicator(
            data_id="ind_001",
            indicator_name="MA_20",
            symbol="BTCUSDT",
            indicator_value=indicator_value,
        )

        assert tag.cognitive_level == CognitiveLevel.FACT
        assert tag.confidence >= 0.90
        assert data == indicator_value
        assert "local_indicator://MA_20/BTCUSDT" in tag.source_url_or_api

    def test_wrap_indicator_rsi(self):
        """Wrap RSI indicator."""
        enforcer = DataSourceEnforcer()

        tag, data = enforcer.wrap_computed_indicator(
            data_id="ind_002",
            indicator_name="RSI_14",
            symbol="ETHUSDT",
            indicator_value=65.2,
        )

        assert tag.cognitive_level == CognitiveLevel.FACT
        assert "RSI_14" in tag.source_url_or_api


# ─────────────────────────────────────────────
# 6. DataSourceEnforcer: Statistics
# ─────────────────────────────────────────────

class TestDataSourceEnforcerStats:
    """Tests for statistics tracking."""

    def test_stats_initial(self):
        """Initial stats are zero."""
        enforcer = DataSourceEnforcer()
        stats = enforcer.get_stats()
        assert stats["total_tagged"] == 0
        assert stats["total_rejected"] == 0
        assert stats["by_cognitive_level"]["fact"] == 0
        assert stats["by_cognitive_level"]["inference"] == 0

    def test_stats_after_tagging_facts(self):
        """Stats updated after tagging FACT data."""
        enforcer = DataSourceEnforcer()
        for i in range(3):
            enforcer.validate_and_tag(
                data_id=f"fact_{i}",
                source_type=DataSourceType.EXCHANGE_REST,
            )
        stats = enforcer.get_stats()
        assert stats["total_tagged"] == 3
        assert stats["by_cognitive_level"]["fact"] == 3
        assert stats["by_cognitive_level"]["inference"] == 0

    def test_stats_after_tagging_inferences(self):
        """Stats updated after tagging INFERENCE data."""
        enforcer = DataSourceEnforcer()
        for i in range(2):
            enforcer.validate_and_tag(
                data_id=f"inf_{i}",
                source_type=DataSourceType.SEARCH_PERPLEXITY,
            )
        stats = enforcer.get_stats()
        assert stats["total_tagged"] == 2
        assert stats["by_cognitive_level"]["inference"] == 2

    def test_stats_mixed_levels(self):
        """Stats with mixed cognitive levels."""
        enforcer = DataSourceEnforcer()
        enforcer.validate_and_tag("fact_1", DataSourceType.EXCHANGE_REST)
        enforcer.validate_and_tag("fact_2", DataSourceType.LOCAL_INDICATOR)
        enforcer.validate_and_tag("inf_1", DataSourceType.SEARCH_WEB)
        enforcer.validate_and_tag("hyp_1", DataSourceType.LOCAL_OLLAMA, cognitive_level=CognitiveLevel.HYPOTHESIS)

        stats = enforcer.get_stats()
        assert stats["total_tagged"] == 4
        assert stats["by_cognitive_level"]["fact"] == 2
        assert stats["by_cognitive_level"]["inference"] >= 1

    def test_stats_by_source_type(self):
        """Stats breakdown by source type."""
        enforcer = DataSourceEnforcer()
        enforcer.validate_and_tag("rest_1", DataSourceType.EXCHANGE_REST)
        enforcer.validate_and_tag("rest_2", DataSourceType.EXCHANGE_REST)
        enforcer.validate_and_tag("search_1", DataSourceType.SEARCH_WEB)

        stats = enforcer.get_stats()
        assert stats["by_source_type"]["exchange_rest"] == 2
        assert stats["by_source_type"]["search_web"] == 1

    def test_rejection_rate(self):
        """Rejection rate calculation."""
        enforcer = DataSourceEnforcer()
        # Tag 8 items
        for i in range(8):
            enforcer.validate_and_tag(f"tagged_{i}", DataSourceType.EXCHANGE_REST)

        # Reject 2 items
        for i in range(2):
            try:
                enforcer.reject_untagged_data(f"untagged_{i}", raise_on_untagged=True)
            except ValueError:
                pass

        stats = enforcer.get_stats()
        assert stats["total_tagged"] == 8
        assert stats["total_rejected"] == 2
        rejection_rate = stats["rejection_rate"]
        assert 0 <= rejection_rate <= 1
        # rejection_rate ≈ 2 / (8 + 2) = 0.2
        assert 0.15 < rejection_rate < 0.25

    def test_reset_stats(self):
        """Reset statistics."""
        enforcer = DataSourceEnforcer()
        enforcer.validate_and_tag("fact_1", DataSourceType.EXCHANGE_REST)
        stats_before = enforcer.get_stats()
        assert stats_before["total_tagged"] == 1

        enforcer.reset_stats()
        stats_after = enforcer.get_stats()
        assert stats_after["total_tagged"] == 0
        assert stats_after["total_rejected"] == 0


# ─────────────────────────────────────────────
# 7. DataSourceEnforcer: Thread Safety
# ─────────────────────────────────────────────

class TestDataSourceEnforcerThreadSafety:
    """Tests for concurrent access."""

    def test_concurrent_tagging(self):
        """Multiple threads tagging simultaneously."""
        enforcer = DataSourceEnforcer()
        num_threads = 10
        tags_per_thread = 50

        def tag_data(thread_id: int):
            for i in range(tags_per_thread):
                data_id = f"thread_{thread_id}_item_{i}"
                enforcer.validate_and_tag(
                    data_id=data_id,
                    source_type=DataSourceType.EXCHANGE_REST,
                )

        threads = [
            threading.Thread(target=tag_data, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = enforcer.get_stats()
        expected_total = num_threads * tags_per_thread
        assert stats["total_tagged"] == expected_total
        assert stats["by_cognitive_level"]["fact"] == expected_total

    def test_concurrent_get_and_tag(self):
        """Concurrent get and tag operations."""
        enforcer = DataSourceEnforcer()
        results = {"gets": 0, "tags": 0, "errors": 0}
        lock = threading.Lock()

        def writer(thread_id: int):
            for i in range(20):
                try:
                    enforcer.validate_and_tag(
                        f"item_{thread_id}_{i}",
                        DataSourceType.SEARCH_WEB,
                    )
                    with lock:
                        results["tags"] += 1
                except Exception as e:
                    with lock:
                        results["errors"] += 1

        def reader(thread_id: int):
            for i in range(20):
                try:
                    tag = enforcer.get_tag(f"item_{thread_id}_{i}")
                    with lock:
                        results["gets"] += 1
                except Exception as e:
                    with lock:
                        results["errors"] += 1

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["errors"] == 0
        assert results["tags"] > 0


# ─────────────────────────────────────────────
# 8. DataSourceEnforcer: Audit Callback
# ─────────────────────────────────────────────

class TestDataSourceEnforcerAudit:
    """Tests for audit callback integration."""

    def test_audit_callback_on_tagging(self):
        """Audit callback invoked on tagging."""
        audit_events: List[Tuple[str, Dict[str, Any]]] = []

        def audit_callback(event_type: str, event_dict: Dict[str, Any]):
            audit_events.append((event_type, event_dict))

        enforcer = DataSourceEnforcer(audit_callback=audit_callback)
        enforcer.validate_and_tag("data_1", DataSourceType.EXCHANGE_REST)

        assert len(audit_events) == 1
        event_type, event_dict = audit_events[0]
        assert event_type == "data_tagged"
        assert "data_id" in event_dict
        assert "tag" in event_dict
        assert event_dict["data_id"] == "data_1"

    def test_audit_callback_on_rejection(self):
        """Audit callback invoked on rejection."""
        audit_events: List[Tuple[str, Dict[str, Any]]] = []

        def audit_callback(event_type: str, event_dict: Dict[str, Any]):
            audit_events.append((event_type, event_dict))

        enforcer = DataSourceEnforcer(audit_callback=audit_callback)
        try:
            enforcer.reject_untagged_data("untagged_1", raise_on_untagged=True)
        except ValueError:
            pass

        assert len(audit_events) == 1
        event_type, event_dict = audit_events[0]
        assert event_type == "untagged_data_rejected"
        assert "data_id" in event_dict
        assert event_dict["data_id"] == "untagged_1"

    def test_audit_callback_exception_tolerance(self):
        """Enforcer tolerates audit callback exceptions."""
        def bad_audit(event_type: str, event_dict: Dict[str, Any]):
            raise RuntimeError("Audit callback failed")

        enforcer = DataSourceEnforcer(audit_callback=bad_audit)
        # Should not raise, despite bad callback
        tag = enforcer.validate_and_tag("data_2", DataSourceType.EXCHANGE_REST)
        assert tag is not None

    def test_multiple_audit_events(self):
        """Multiple audit events recorded."""
        events: List[str] = []

        def audit_callback(event_type: str, event_dict: Dict[str, Any]):
            events.append(event_type)

        enforcer = DataSourceEnforcer(audit_callback=audit_callback)
        # Tag 3 items
        for i in range(3):
            enforcer.validate_and_tag(f"item_{i}", DataSourceType.SEARCH_WEB)
        # Reject 1
        try:
            enforcer.reject_untagged_data("untagged", raise_on_untagged=True)
        except ValueError:
            pass

        assert len(events) == 4
        assert events.count("data_tagged") == 3
        assert events.count("untagged_data_rejected") == 1


# ─────────────────────────────────────────────
# 9. DataSourceEnforcer: Edge Cases
# ─────────────────────────────────────────────

class TestDataSourceEnforcerEdgeCases:
    """Edge cases and error handling."""

    def test_tag_with_custom_timestamp(self):
        """Provide custom fetched_at_ms."""
        enforcer = DataSourceEnforcer()
        custom_time = 1000000000000  # Some past time
        tag = enforcer.validate_and_tag(
            data_id="custom_time",
            source_type=DataSourceType.EXCHANGE_REST,
            fetched_at_ms=custom_time,
        )
        assert tag.fetched_at_ms == custom_time

    def test_tag_with_zero_confidence(self):
        """Tag with zero confidence is accepted."""
        enforcer = DataSourceEnforcer()
        tag = enforcer.validate_and_tag(
            data_id="zero_conf",
            source_type=DataSourceType.LOCAL_OLLAMA,
            confidence=0.0,
        )
        assert tag.confidence == 0.0

    def test_tag_with_high_confidence(self):
        """Tag with confidence > 1.0 is accepted (no validation on bounds)."""
        enforcer = DataSourceEnforcer()
        tag = enforcer.validate_and_tag(
            data_id="high_conf",
            source_type=DataSourceType.LOCAL_INDICATOR,
            confidence=1.5,
        )
        assert tag.confidence == 1.5

    def test_very_long_source_url(self):
        """Handle very long source URLs."""
        enforcer = DataSourceEnforcer()
        long_url = "https://api.example.com/" + "x" * 10000
        tag = enforcer.validate_and_tag(
            data_id="long_url",
            source_type=DataSourceType.SEARCH_WEB,
            source_url_or_api=long_url,
        )
        assert tag.source_url_or_api == long_url

    def test_special_characters_in_data_id(self):
        """Data IDs with special characters."""
        enforcer = DataSourceEnforcer()
        special_id = "data:123/456-789_abc"
        tag = enforcer.validate_and_tag(
            data_id=special_id,
            source_type=DataSourceType.EXCHANGE_REST,
        )
        assert enforcer.get_tag(special_id) == tag

    def test_unicode_in_source_url(self):
        """Unicode characters in source URL."""
        enforcer = DataSourceEnforcer()
        url_with_unicode = "https://api.example.com/数据/查询"
        tag = enforcer.validate_and_tag(
            data_id="unicode_url",
            source_type=DataSourceType.SEARCH_WEB,
            source_url_or_api=url_with_unicode,
        )
        assert tag.source_url_or_api == url_with_unicode

    def test_duplicate_data_ids_overwrite(self):
        """Tagging same data_id twice overwrites previous tag."""
        enforcer = DataSourceEnforcer()
        tag1 = enforcer.validate_and_tag(
            data_id="dup_id",
            source_type=DataSourceType.EXCHANGE_REST,
        )
        tag2 = enforcer.validate_and_tag(
            data_id="dup_id",
            source_type=DataSourceType.SEARCH_WEB,
        )
        stored = enforcer.get_tag("dup_id")
        # Should be the second tag (last write wins)
        assert stored.tag_id == tag2.tag_id

        # Stats should account for both tags (counting both registrations)
        stats = enforcer.get_stats()
        assert stats["total_tagged"] == 2

    def test_clear_tagged_objects(self):
        """Clear all tagged objects."""
        enforcer = DataSourceEnforcer()
        enforcer.validate_and_tag("data_1", DataSourceType.EXCHANGE_REST)
        enforcer.validate_and_tag("data_2", DataSourceType.SEARCH_WEB)

        stats_before = enforcer.get_stats()
        assert stats_before["total_tagged"] == 2

        enforcer.clear_tagged_objects()
        assert enforcer.get_tag("data_1") is None
        assert enforcer.get_tag("data_2") is None

        # Stats still reflect the counts (clearing objects doesn't reset stats)
        stats_after = enforcer.get_stats()
        assert stats_after["total_tagged"] == 2


# ─────────────────────────────────────────────
# 10. Integration Tests: Full Workflow
# ─────────────────────────────────────────────

class TestDataSourceEnforcerIntegration:
    """End-to-end workflow tests."""

    def test_typical_trading_data_flow(self):
        """Typical trading data flow with mixed sources."""
        audit_log: List[str] = []

        def audit(event_type: str, event_dict: Dict[str, Any]):
            audit_log.append(event_type)

        enforcer = DataSourceEnforcer(audit_callback=audit)

        # 1. Exchange prices (FACT)
        tag_price, price_data = enforcer.wrap_exchange_response(
            data_id="price_btc_001",
            endpoint="/v5/market/tickers",
            response_data={"symbol": "BTCUSDT", "price": 50000},
        )
        assert tag_price.cognitive_level == CognitiveLevel.FACT

        # Validate can be used
        is_valid, reason = enforcer.reject_untagged_data(
            "price_btc_001", raise_on_untagged=True
        )
        assert is_valid is True

        # 2. Search sentiment (INFERENCE)
        tag_search, search_data = enforcer.wrap_search_result(
            data_id="sentiment_001",
            search_engine="perplexity",
            query="Bitcoin market sentiment",
            result_data={"sentiment": "bullish"},
        )
        assert tag_search.cognitive_level == CognitiveLevel.INFERENCE

        # 3. AI analysis (INFERENCE)
        tag_ai, ai_data = enforcer.wrap_ai_output(
            data_id="analysis_001",
            model_name="ollama:llama2",
            prompt_used="Analyze BTC price action",
            output_data={"recommendation": "BUY"},
        )
        assert tag_ai.cognitive_level == CognitiveLevel.INFERENCE

        # 4. Computed indicator (FACT)
        tag_ma, ma_value = enforcer.wrap_computed_indicator(
            data_id="ma20_btc_001",
            indicator_name="MA_20",
            symbol="BTCUSDT",
            indicator_value=49500,
        )
        assert tag_ma.cognitive_level == CognitiveLevel.FACT

        # Verify statistics
        stats = enforcer.get_stats()
        assert stats["total_tagged"] == 4
        assert stats["by_cognitive_level"]["fact"] == 2  # price + MA
        assert stats["by_cognitive_level"]["inference"] == 2  # search + AI

        # Verify audit trail
        assert len(audit_log) == 4
        assert all(event == "data_tagged" for event in audit_log)

    def test_reject_untagged_in_decision_chain(self):
        """Enforcing tagging requirement in decision chain."""
        enforcer = DataSourceEnforcer()

        # Some data is properly tagged
        enforcer.validate_and_tag("trusted_data", DataSourceType.EXCHANGE_REST)

        # Attempt to use untagged data in decision chain
        with pytest.raises(ValueError, match="not tagged"):
            enforcer.reject_untagged_data("untrusted_data", raise_on_untagged=True)

        # Reject count incremented
        stats = enforcer.get_stats()
        assert stats["total_rejected"] == 1

    def test_data_source_classifier_integration(self):
        """DataSourceClassifier used during tagging."""
        enforcer = DataSourceEnforcer()

        # Bybit API URL
        tag1 = enforcer.validate_and_tag(
            data_id="bybit_api",
            source_type=DataSourceType.EXCHANGE_REST,
            source_url_or_api="https://api.bybit.com/v5/market/tickers",
        )
        assert tag1.cognitive_level == CognitiveLevel.FACT

        # News site
        tag2 = enforcer.validate_and_tag(
            data_id="news_btc",
            source_type=DataSourceType.SEARCH_WEB,
            source_url_or_api="https://www.reuters.com/finance/markets/",
        )
        assert tag2.cognitive_level == CognitiveLevel.INFERENCE

        stats = enforcer.get_stats()
        assert stats["by_cognitive_level"]["fact"] == 1
        assert stats["by_cognitive_level"]["inference"] == 1

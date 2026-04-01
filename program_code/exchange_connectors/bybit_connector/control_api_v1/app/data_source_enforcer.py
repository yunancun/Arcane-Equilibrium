"""
MODULE_NOTE (中文):
  數據源標記強制器 — 確保所有外部數據在進入系統前被正確標記來源和認知層級。
  屬於治理層（T2.16），實現 DOC-01 §5.10 認知誠實原則。
  功能：DataSourceTag 不可變標記 / DataSourceEnforcer 驗證與標記 /
  來源自動分類（Bybit API→FACT, 搜索/AI→INFERENCE）/ 統計追蹤。

MODULE_NOTE (English):
  Data Source Enforcer — ensures all external data is properly tagged with source
  and cognitive level before entering the system. Part of governance layer (T2.16),
  implementing DOC-01 §5.10 (Cognitive Honesty). Features: DataSourceTag immutable
  marking / DataSourceEnforcer validation / source auto-classification (Bybit API
  → FACT, searches/AI → INFERENCE) / reject_untagged_data() / statistics tracking.

Safety invariant:
  未標記的數據默認被阻擋（fail-closed），不允許無來源標記的數據進入決策管線。
  Untagged data is blocked by default (fail-closed); no untagged data may enter
  the decision pipeline.

Governance refs: DOC-01 §5.10 (Root Principle #8: Cognitive Honesty)
Spec ref: T2.16 GAP-M7
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .perception_data_plane import (
    CognitiveLevel,
    DataSourceType,
    Freshness,
    DataQuality,
)


# ─────────────────────────────────────────────
# 1. Data Source Tag (Immutable Marking)
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class DataSourceTag:
    """Immutable mark applied to external data.

    Every piece of external data MUST carry this tag before entering
    the decision chain. Tags are created by DataSourceEnforcer and
    cannot be modified after creation (frozen=True).

    Attributes:
        tag_id: Unique identifier for audit trail
        source_url_or_api: The endpoint/URL/source location
        fetched_at_ms: Timestamp when data was fetched (milliseconds)
        cognitive_level: fact/inference/hypothesis (from CognitiveLevel enum)
        confidence: 0.0-1.0 confidence in the marking
        tagged_by: System component that created the tag
        tag_reason: Explanation for why this level was assigned
        is_external: Whether this is external data (not computed locally)
    """
    tag_id: str
    source_url_or_api: str
    fetched_at_ms: int
    cognitive_level: CognitiveLevel
    confidence: float  # 0.0-1.0
    tagged_by: str  # e.g., "bybit_connector", "search_wrapper", "ai_output_wrapper"
    tag_reason: str  # e.g., "Bybit REST API → FACT", "DuckDuckGo search → INFERENCE"
    is_external: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize tag for audit logging."""
        return {
            "tag_id": self.tag_id,
            "source_url_or_api": self.source_url_or_api,
            "fetched_at_ms": self.fetched_at_ms,
            "cognitive_level": self.cognitive_level.value,
            "confidence": self.confidence,
            "tagged_by": self.tagged_by,
            "tag_reason": self.tag_reason,
            "is_external": self.is_external,
        }


# ─────────────────────────────────────────────
# 2. Data Source Classification Rules
# ─────────────────────────────────────────────

class DataSourceClassifier:
    """Rules for auto-classifying external data sources.

    Maps source type/URL patterns to cognitive level and confidence.
    These rules implement DOC-01 §5.10 and the source taxonomy from
    perception_data_plane.py.
    """

    @staticmethod
    def classify_by_type(
        source_type: DataSourceType,
    ) -> Tuple[CognitiveLevel, float, str]:
        """Classify a data source by its type.

        Returns: (cognitive_level, confidence, reason)
        """
        # Bybit exchange endpoints → FACT (high confidence)
        if source_type == DataSourceType.EXCHANGE_REST:
            return (
                CognitiveLevel.FACT,
                0.99,
                "Bybit REST API → official exchange data = FACT",
            )
        if source_type == DataSourceType.EXCHANGE_WS:
            return (
                CognitiveLevel.FACT,
                0.99,
                "Bybit WebSocket → real-time exchange feed = FACT",
            )

        # Local computed indicators → FACT (derived from exchange data)
        if source_type == DataSourceType.LOCAL_INDICATOR:
            return (
                CognitiveLevel.FACT,
                0.95,
                "Local indicator (MA/RSI/BB) → computed from FACT = FACT",
            )

        # Search engines, AI models → INFERENCE
        if source_type == DataSourceType.SEARCH_PERPLEXITY:
            return (
                CognitiveLevel.INFERENCE,
                0.75,
                "Perplexity search → synthesized web content = INFERENCE",
            )
        if source_type == DataSourceType.SEARCH_WEB:
            return (
                CognitiveLevel.INFERENCE,
                0.65,
                "DuckDuckGo/web search → third-party sources = INFERENCE",
            )
        if source_type == DataSourceType.LOCAL_OLLAMA:
            return (
                CognitiveLevel.INFERENCE,
                0.70,
                "Ollama local model output = INFERENCE",
            )

        # Event calendar: mixed (dates are facts, analysis is inference)
        if source_type == DataSourceType.EVENT_CALENDAR:
            return (
                CognitiveLevel.INFERENCE,
                0.75,
                "Event calendar → contains scheduled events + forecasts = INFERENCE",
            )

        # Learning history: patterns, not ground truth
        if source_type == DataSourceType.LEARNING_HISTORY:
            return (
                CognitiveLevel.INFERENCE,
                0.80,
                "Analyst pattern discovery → historical analysis = INFERENCE",
            )

        # Default: be conservative, assume inference
        return (
            CognitiveLevel.INFERENCE,
            0.50,
            "Unknown source type → default to INFERENCE (conservative)",
        )

    @staticmethod
    def classify_by_url_pattern(url: str) -> Optional[Tuple[CognitiveLevel, float, str]]:
        """Classify by URL pattern. Returns None if no match.

        This allows fine-grained classification beyond source_type.
        """
        url_lower = url.lower()

        # Bybit official API
        if "api.bybit.com" in url_lower or "stream.bybit.com" in url_lower:
            return (
                CognitiveLevel.FACT,
                0.99,
                f"Official Bybit API ({url}) = FACT",
            )

        # Perplexity
        if "perplexity" in url_lower:
            return (
                CognitiveLevel.INFERENCE,
                0.75,
                f"Perplexity search ({url}) = INFERENCE",
            )

        # DuckDuckGo, Google, other public search
        if any(x in url_lower for x in ["duckduckgo", "google", "bing"]):
            return (
                CognitiveLevel.INFERENCE,
                0.65,
                f"Public search engine ({url}) = INFERENCE",
            )

        # News sites (conservative: inference)
        if any(x in url_lower for x in [
            "news", "reuters", "bloomberg", "cnn", "bbc"
        ]):
            return (
                CognitiveLevel.INFERENCE,
                0.60,
                f"News source ({url}) = INFERENCE",
            )

        # No specific pattern matched
        return None


# ─────────────────────────────────────────────
# 3. Data Source Enforcer
# ─────────────────────────────────────────────

class DataSourceEnforcer:
    """ENFORCEMENT LAYER for cognitive honesty (DOC-01 §5.10).

    Responsibilities:
      1. Validate all external data entering the system
      2. Auto-classify data by source using DataSourceClassifier
      3. Attach immutable DataSourceTag to each external data piece
      4. Reject untagged data before it enters decision chain
      5. Track statistics: tagged_count, rejected_count, by_level breakdown
      6. Maintain thread safety
      7. Call audit callback on all tagging decisions
    """

    def __init__(
        self,
        *,
        audit_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        strict_mode: bool = True,
    ):
        """Initialize the enforcer.

        Args:
            audit_callback: Optional function(event_type, event_dict) for audit logging
            strict_mode: If True, reject untagged data; if False, only warn
        """
        self._lock = threading.Lock()
        self._audit_callback = audit_callback
        self._strict_mode = strict_mode
        self._tagged_objects: Dict[str, DataSourceTag] = {}  # data_id → tag
        self._stats = {
            "tagged_count": 0,
            "rejected_count": 0,
            "by_level": {
                CognitiveLevel.FACT.value: 0,
                CognitiveLevel.INFERENCE.value: 0,
                CognitiveLevel.HYPOTHESIS.value: 0,
            },
            "by_source_type": {},  # DataSourceType.value → count
        }

    # ── Core Validation & Tagging ──

    def validate_and_tag(
        self,
        data_id: str,
        source_type: DataSourceType,
        source_url_or_api: str = "",
        *,
        fetched_at_ms: Optional[int] = None,
        cognitive_level: Optional[CognitiveLevel] = None,
        confidence: Optional[float] = None,
    ) -> DataSourceTag:
        """Validate and tag external data.

        If cognitive_level is not provided, auto-classifies based on source_type.
        Creates an immutable DataSourceTag and returns it.

        Args:
            data_id: Unique ID of the data object
            source_type: Type of source (from DataSourceType enum)
            source_url_or_api: URL or API endpoint string
            fetched_at_ms: Timestamp when data was fetched (default: now)
            cognitive_level: Override cognitive level (default: auto-classify)
            confidence: Override confidence (default: from classifier)

        Returns:
            DataSourceTag: immutable tag attached to this data

        Raises:
            ValueError: if data_id is empty or source_type is invalid
        """
        if not data_id:
            raise ValueError("data_id cannot be empty")

        # Use current time if not provided
        if fetched_at_ms is None:
            fetched_at_ms = int(time.time() * 1000)

        # Determine cognitive level and confidence
        if cognitive_level is None or confidence is None:
            # Try URL-pattern classification first
            url_result = DataSourceClassifier.classify_by_url_pattern(source_url_or_api)
            if url_result:
                classified_level, classified_confidence, reason = url_result
            else:
                # Fall back to source_type classification
                classified_level, classified_confidence, reason = (
                    DataSourceClassifier.classify_by_type(source_type)
                )

            # Use provided overrides if given, otherwise use classified values
            cognitive_level = cognitive_level or classified_level
            confidence = confidence if confidence is not None else classified_confidence
        else:
            reason = "Explicitly provided by caller"

        # Create tag
        tag = DataSourceTag(
            tag_id=f"tag_{uuid.uuid4().hex[:12]}",
            source_url_or_api=source_url_or_api or f"source_type:{source_type.value}",
            fetched_at_ms=fetched_at_ms,
            cognitive_level=cognitive_level,
            confidence=confidence,
            tagged_by="DataSourceEnforcer",
            tag_reason=reason,
            is_external=True,
        )

        # Store tag and update statistics
        with self._lock:
            self._tagged_objects[data_id] = tag
            self._stats["tagged_count"] += 1
            self._stats["by_level"][cognitive_level.value] += 1
            source_type_str = source_type.value
            self._stats["by_source_type"][source_type_str] = (
                self._stats["by_source_type"].get(source_type_str, 0) + 1
            )

        # Audit callback
        if self._audit_callback:
            try:
                self._audit_callback("data_tagged", {
                    "data_id": data_id,
                    "tag": tag.to_dict(),
                })
            except Exception:
                pass  # Don't let audit errors break the main flow

        return tag

    def get_tag(self, data_id: str) -> Optional[DataSourceTag]:
        """Retrieve tag for a data object.

        Returns None if data is not tagged.
        """
        with self._lock:
            return self._tagged_objects.get(data_id)

    def reject_untagged_data(
        self, data_id: str, raise_on_untagged: bool = True
    ) -> Tuple[bool, str]:
        """Check if data is tagged. Reject if not.

        Implements core principle: external data MUST be tagged before
        entering decision chain.

        Args:
            data_id: ID of the data object to check
            raise_on_untagged: If True, raise ValueError on untagged data;
                               if False, return (False, reason) and log

        Returns:
            (is_tagged, reason) tuple

        Raises:
            ValueError: if raise_on_untagged=True and data is not tagged
        """
        tag = self.get_tag(data_id)

        if tag is None:
            reason = (
                f"Data {data_id} is not tagged. External data MUST be tagged "
                f"before entering decision chain (DOC-01 §5.10)."
            )

            with self._lock:
                self._stats["rejected_count"] += 1

            if self._audit_callback:
                try:
                    self._audit_callback("untagged_data_rejected", {
                        "data_id": data_id,
                        "reason": reason,
                    })
                except Exception:
                    pass

            if raise_on_untagged:
                raise ValueError(reason)
            return (False, reason)

        return (True, f"Data is properly tagged with level={tag.cognitive_level.value}")

    # ── Pipeline Integration Points ──

    def wrap_exchange_response(
        self,
        data_id: str,
        endpoint: str,
        response_data: Any,
        fetched_at_ms: Optional[int] = None,
    ) -> Tuple[DataSourceTag, Any]:
        """Wrap Bybit exchange response (REST or WebSocket).

        Exchange data is classified as FACT.

        Args:
            data_id: Unique ID for this response
            endpoint: API endpoint path (e.g., "/v5/market/tickers")
            response_data: The actual response payload
            fetched_at_ms: Fetch timestamp (default: now)

        Returns:
            (tag, response_data) tuple
        """
        # Determine source type based on endpoint
        if "stream" in endpoint.lower() or "ws" in endpoint.lower():
            source_type = DataSourceType.EXCHANGE_WS
        else:
            source_type = DataSourceType.EXCHANGE_REST

        source_url = f"https://api.bybit.com{endpoint}" if not endpoint.startswith("http") else endpoint

        tag = self.validate_and_tag(
            data_id=data_id,
            source_type=source_type,
            source_url_or_api=source_url,
            fetched_at_ms=fetched_at_ms,
        )

        return (tag, response_data)

    def wrap_search_result(
        self,
        data_id: str,
        search_engine: str,  # "perplexity", "duckduckgo", etc.
        query: str,
        result_data: Any,
        fetched_at_ms: Optional[int] = None,
    ) -> Tuple[DataSourceTag, Any]:
        """Wrap search result (Perplexity, DuckDuckGo, etc.).

        Search results are classified as INFERENCE.

        Args:
            data_id: Unique ID for this search result
            search_engine: Name of the search engine
            query: The search query performed
            result_data: The search results
            fetched_at_ms: Fetch timestamp (default: now)

        Returns:
            (tag, result_data) tuple
        """
        # Map search engine name to source type
        search_engine_lower = search_engine.lower()
        if "perplexity" in search_engine_lower:
            source_type = DataSourceType.SEARCH_PERPLEXITY
        else:
            source_type = DataSourceType.SEARCH_WEB

        source_url = f"search://{search_engine}?q={query[:50]}"

        tag = self.validate_and_tag(
            data_id=data_id,
            source_type=source_type,
            source_url_or_api=source_url,
            fetched_at_ms=fetched_at_ms,
        )

        return (tag, result_data)

    def wrap_ai_output(
        self,
        data_id: str,
        model_name: str,  # "ollama:llama2", "claude-haiku", etc.
        prompt_used: str,
        output_data: Any,
        fetched_at_ms: Optional[int] = None,
    ) -> Tuple[DataSourceTag, Any]:
        """Wrap AI model output (local Ollama or cloud models).

        AI output is classified as INFERENCE.

        Args:
            data_id: Unique ID for this AI output
            model_name: Name of the model (e.g., "ollama:llama2")
            prompt_used: The prompt that generated this output
            output_data: The model output
            fetched_at_ms: Fetch timestamp (default: now)

        Returns:
            (tag, output_data) tuple
        """
        # Determine source type based on model name
        if "ollama" in model_name.lower():
            source_type = DataSourceType.LOCAL_OLLAMA
        else:
            source_type = DataSourceType.LOCAL_OLLAMA  # default to local

        source_url = f"ai_model://{model_name}?prompt={prompt_used[:50]}"

        tag = self.validate_and_tag(
            data_id=data_id,
            source_type=source_type,
            source_url_or_api=source_url,
            fetched_at_ms=fetched_at_ms,
        )

        return (tag, output_data)

    def wrap_computed_indicator(
        self,
        data_id: str,
        indicator_name: str,  # "MA_20", "RSI_14", "BOLLINGER_20", etc.
        symbol: str,
        indicator_value: Any,
    ) -> Tuple[DataSourceTag, Any]:
        """Wrap locally computed trading indicator.

        Computed indicators are classified as FACT (derived from exchange data).

        Args:
            data_id: Unique ID for this indicator
            indicator_name: Name of the indicator
            symbol: Trading symbol (e.g., "BTCUSDT")
            indicator_value: The computed value

        Returns:
            (tag, indicator_value) tuple
        """
        source_url = f"local_indicator://{indicator_name}/{symbol}"

        tag = self.validate_and_tag(
            data_id=data_id,
            source_type=DataSourceType.LOCAL_INDICATOR,
            source_url_or_api=source_url,
            confidence=0.95,  # High confidence in local computation
        )

        return (tag, indicator_value)

    # ── Statistics ──

    def get_stats(self) -> Dict[str, Any]:
        """Get enforcement statistics.

        Returns:
            Dict with tagged_count, rejected_count, by_level breakdown, by_source_type
        """
        with self._lock:
            return {
                "total_tagged": self._stats["tagged_count"],
                "total_rejected": self._stats["rejected_count"],
                "by_cognitive_level": dict(self._stats["by_level"]),
                "by_source_type": dict(self._stats["by_source_type"]),
                "rejection_rate": (
                    self._stats["rejected_count"] /
                    (self._stats["tagged_count"] + self._stats["rejected_count"] + 0.001)
                ),
            }

    def reset_stats(self) -> None:
        """Reset all statistics (for testing)."""
        with self._lock:
            self._stats = {
                "tagged_count": 0,
                "rejected_count": 0,
                "by_level": {
                    CognitiveLevel.FACT.value: 0,
                    CognitiveLevel.INFERENCE.value: 0,
                    CognitiveLevel.HYPOTHESIS.value: 0,
                },
                "by_source_type": {},
            }

    def clear_tagged_objects(self) -> None:
        """Clear all tagged objects (for testing)."""
        with self._lock:
            self._tagged_objects.clear()

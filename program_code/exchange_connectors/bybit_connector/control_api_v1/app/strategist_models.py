"""
MODULE_NOTE (中文):
  StrategistAgent 的資料模型與啟發式評估函數。
  從 strategist_agent.py 拆分而來（§14.1 行數約定：1203→~1010 行）。
  包含：StrategistConfig 配置、EdgeEvaluation 結果、_heuristic_evaluate 回退評估、_parse_sentiment 輔助。
  零副作用：純資料定義 + 純函數，不依賴任何單例或運行時狀態。

MODULE_NOTE (English):
  Data models and heuristic evaluation functions for StrategistAgent.
  Extracted from strategist_agent.py (§14.1 line limit compliance: 1203→~1010 lines).
  Contains: StrategistConfig, EdgeEvaluation, _heuristic_evaluate fallback, _parse_sentiment helper.
  Zero side-effects: pure data definitions + pure functions, no singletons or runtime state dependency.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict

from .multi_agent_framework import (
    DataQualityLevel,
    IntelObject,
    SentimentScore,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StrategistConfig:
    """Configuration for StrategistAgent / StrategistAgent 配置"""
    # Minimum confidence threshold to produce a TradeIntent
    # 产出 TradeIntent 的最低置信度阈值
    min_confidence: float = 0.4
    # Minimum relevance score from Scout intel to consider
    # Scout 情报的最低相关性分数
    min_relevance: float = 0.3
    # Maximum age of intel to evaluate (seconds)
    # 情报的最大可接受年龄（秒）
    max_intel_age_seconds: int = 300
    # Default position size (BTC)
    # 默认仓位大小
    default_size: float = 0.001
    # Shadow mode: log only, do not produce intents to bus
    # 影子模式：仅记录日志，不产出 intent 到消息总线
    shadow: bool = True
    # Maximum pending intents to buffer
    # 最大待处理 intent 缓冲数
    max_pending_intents: int = 50
    # Heuristic fallback thresholds / 启发式回退阈值
    heuristic_min_relevance: float = 0.6
    heuristic_min_freshness: int = 120  # seconds


# ═══════════════════════════════════════════════════════════════════════════════
# Edge Evaluation Result / Edge 评估结果
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EdgeEvaluation:
    """Result of edge evaluation (AI or heuristic) / Edge 评估结果"""
    has_edge: bool = False
    confidence: float = 0.0
    reason: str = ""
    source: str = "unknown"  # "ai" or "heuristic"
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_edge": self.has_edge,
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
            "latency_ms": self.latency_ms,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Heuristic Edge Evaluation (Ollama fallback) / 启发式 Edge 评估（Ollama 回退）
# ═══════════════════════════════════════════════════════════════════════════════

def _heuristic_evaluate(intel: IntelObject, config: StrategistConfig) -> EdgeEvaluation:
    """
    Local heuristic edge evaluation — used when Ollama is unavailable.
    本地启发式 edge 评估 — Ollama 不可用时使用。

    This is deliberately conservative (fail-closed).
    刻意保守（fail-closed）。
    """
    start = time.time()

    # Rule 1: Relevance must be high enough / 相关性必须足够高
    if intel.relevance_score < config.heuristic_min_relevance:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason=f"Relevance too low: {intel.relevance_score:.2f} < {config.heuristic_min_relevance}",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Rule 2: Data must be fresh / 数据必须新鲜
    if intel.freshness_seconds > config.heuristic_min_freshness:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason=f"Intel too stale: {intel.freshness_seconds}s > {config.heuristic_min_freshness}s",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Rule 3: Data quality must be FACT or INFERENCE (not HYPOTHESIS)
    # 数据质量必须是 FACT 或 INFERENCE（不是 HYPOTHESIS）
    if intel.data_quality == DataQualityLevel.HYPOTHESIS:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason="HYPOTHESIS-quality intel rejected by heuristic",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Rule 4: Sentiment must be directional (not NEUTRAL) / 情绪必须有方向性
    if intel.sentiment == SentimentScore.NEUTRAL:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason="Neutral sentiment — no directional edge",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Rule 5: Must have at least one symbol / 必须至少有一个交易对
    if not intel.symbols:
        return EdgeEvaluation(
            has_edge=False,
            confidence=0.0,
            reason="No symbols in intel",
            source="heuristic",
            latency_ms=(time.time() - start) * 1000,
        )

    # Passed all heuristic checks — conservative confidence
    # 通过所有启发式检查 — 保守置信度
    confidence = min(intel.relevance_score * 0.7, 0.6)  # Cap at 0.6 for heuristic
    return EdgeEvaluation(
        has_edge=True,
        confidence=confidence,
        reason="Heuristic: high relevance + fresh + directional sentiment",
        source="heuristic",
        latency_ms=(time.time() - start) * 1000,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_sentiment(value: str) -> Any:
    """Parse sentiment string to SentimentScore enum / 解析情绪字符串为 SentimentScore 枚举"""
    try:
        return SentimentScore(value)
    except (ValueError, KeyError):
        return SentimentScore.NEUTRAL

from __future__ import annotations

"""
Layer 2 AI Reasoning Engine — Type Definitions / 类型定义
Layer 2 AI 推理引擎的所有数据结构、抽象基类、配置类与常量

MODULE_NOTE (中文):
  本模块定义 Layer 2 AI 推理引擎的核心数据类型：
  - SearchResult / SearchProvider ABC：4 层搜索降级体系的抽象
  - Layer2Config：引擎全量配置（预算/模型/自适应/provider）
  - Layer2Session：单次推理 session 的完整生命周期记录
  - ToolCall / Recommendation / Insight：Agent 工具调用与输出结构
  - PricingTable：模型与搜索定价表（含 30 天核实）
  - AdaptiveBudgetState：自适应预算状态（倍率/ROI/历史）

MODULE_NOTE (English):
  Core type definitions for the Layer 2 AI Reasoning Engine:
  - SearchResult / SearchProvider ABC: abstraction for 4-tier search degradation
  - Layer2Config: full engine configuration (budget/model/adaptive/provider)
  - Layer2Session: complete lifecycle record of a single reasoning session
  - ToolCall / Recommendation / Insight: agent tool call and output structures
  - PricingTable: model & search pricing (with 30-day verification)
  - AdaptiveBudgetState: adaptive budget state (multiplier/ROI/history)
"""

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

# Session states / Session 状态
SESSION_STATE_PENDING = "pending"
SESSION_STATE_RUNNING = "running"
SESSION_STATE_COMPLETED = "completed"
SESSION_STATE_FAILED = "failed"
SESSION_STATE_BUDGET_EXCEEDED = "budget_exceeded"

# Model tiers / 模型层级
MODEL_HAIKU = "haiku"
MODEL_SONNET = "sonnet"
MODEL_OPUS = "opus"

# Model IDs (Anthropic API) / 模型 ID
MODEL_IDS: dict[str, str] = {
    MODEL_HAIKU: "claude-haiku-4-5-20251001",
    MODEL_SONNET: "claude-sonnet-4-6-20250326",
    MODEL_OPUS: "claude-opus-4-6-20250326",
}

# Default budget limits / 默认预算限制
DEFAULT_DAILY_HARD_CAP_USD = 15.0
DEFAULT_SESSION_BUDGET_SONNET_USD = 1.50
DEFAULT_SESSION_BUDGET_OPUS_USD = 4.00
DEFAULT_ADAPTIVE_BASE_DAILY_USD = 8.0

# Adaptive budget multiplier tiers / 自适应预算倍率层级
ADAPTIVE_TIERS: list[tuple[float, float]] = [
    (3.0, 2.0),   # ROI >= 3.0 → 2.0x
    (1.5, 1.5),   # ROI >= 1.5 → 1.5x
    (0.5, 1.0),   # ROI >= 0.5 → 1.0x
    (0.0, 0.7),   # ROI >= 0.0 → 0.7x
    (float("-inf"), 0.3),  # ROI < 0 → 0.3x
]

# Minimum days for adaptive budget calculation / 自适应预算计算最少天数
ADAPTIVE_MIN_DAYS = 3

# Search provider priority / 搜索 provider 优先级
SEARCH_PROVIDER_PERPLEXITY = "perplexity"
SEARCH_PROVIDER_LOCAL_LLM_WEB = "local_llm_web"
SEARCH_PROVIDER_LOCAL_LLM = "local_llm"
SEARCH_PROVIDER_WEBPILOT = "webpilot"

SEARCH_PROVIDER_PRIORITY: list[str] = [
    SEARCH_PROVIDER_PERPLEXITY,
    SEARCH_PROVIDER_LOCAL_LLM_WEB,
    SEARCH_PROVIDER_LOCAL_LLM,
    SEARCH_PROVIDER_WEBPILOT,
]

# Agent tool names / Agent 工具名称
TOOL_GET_MARKET_STATE = "get_market_state"
TOOL_GET_ACCOUNT_STATE = "get_account_state"
TOOL_GET_RECENT_DECISIONS = "get_recent_decisions"
TOOL_GET_EXPERIENCE = "get_experience"
TOOL_WEB_SEARCH = "web_search"
TOOL_FETCH_URL = "fetch_url"
TOOL_SUBMIT_RECOMMENDATION = "submit_recommendation"
TOOL_RECORD_INSIGHT = "record_insight"

# Max agent loop iterations / Agent 循环最大迭代次数
MAX_AGENT_ITERATIONS = 15

# Pricing verification interval / 定价核实间隔（天）
PRICING_VERIFY_INTERVAL_DAYS = 30


# ═══════════════════════════════════════════════════════════════════════════════
# Search Types / 搜索类型
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SearchResult:
    """Single search result from any provider / 任意搜索 provider 的单条搜索结果"""
    title: str
    snippet: str
    url: str = ""
    source_ts: str = ""          # ISO timestamp of the source, if available
    provider: str = ""           # Which provider returned this result
    citation_id: str = ""        # Perplexity citation ID, if applicable
    confidence: float = 0.0      # Provider's confidence in relevance (0-1)


@dataclass
class SearchResponse:
    """Aggregated search response / 聚合搜索响应"""
    query: str
    results: list[SearchResult] = field(default_factory=list)
    provider_used: str = ""
    providers_tried: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None
    is_degraded: bool = False    # True if fell back to lower-tier provider


class SearchProvider(ABC):
    """Abstract base class for search providers / 搜索 provider 抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier / Provider 标识"""
        ...

    @abstractmethod
    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        """Execute a search query / 执行搜索查询"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is currently available / 检查 provider 是否可用"""
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# Tool Call & Output Types / 工具调用与输出类型
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ToolCallRecord:
    """Record of a single tool call within an agent session / Agent session 内单次工具调用记录"""
    tool_name: str
    input_args: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class Recommendation:
    """Structured trade recommendation from the agent / Agent 的结构化交易推荐"""
    action: Literal["buy", "sell", "hold", "close_long", "close_short"]
    symbol: str
    confidence: float              # 0.0 - 1.0
    edge_bps: float                # Expected edge in basis points
    reasoning: str                 # Why this recommendation
    freshness_note: str = ""       # How fresh the data is
    risk_factors: list[str] = field(default_factory=list)
    suggested_size_fraction: float = 0.02  # Fraction of balance
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    time_horizon: str = ""         # e.g. "minutes", "hours", "days"
    source_tools: list[str] = field(default_factory=list)  # Which tools informed this


@dataclass
class Insight:
    """Market insight recorded by the agent / Agent 记录的市场洞察"""
    category: str                  # e.g. "macro", "sentiment", "technical", "correlation"
    title: str
    detail: str
    confidence: float = 0.0
    relevance_window: str = ""     # How long this insight is relevant
    source_tools: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Session Types / Session 类型
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Layer2Session:
    """Complete record of a single L2 reasoning session / 单次 L2 推理 session 的完整记录"""
    session_id: str = field(default_factory=lambda: f"l2s:{uuid.uuid4().hex[:12]}")
    state: str = SESSION_STATE_PENDING
    trigger: str = "manual"        # "manual" | "auto" | "scheduled"

    # Model tracking / 模型追踪
    initial_model: str = MODEL_SONNET
    current_model: str = MODEL_SONNET
    model_upgraded: bool = False
    upgrade_reason: str = ""

    # Budget / 预算
    session_budget_usd: float = DEFAULT_SESSION_BUDGET_SONNET_USD
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    search_cost_usd: float = 0.0

    # Tool calls / 工具调用
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    iterations: int = 0

    # Outputs / 输出
    recommendation: Recommendation | None = None
    insights: list[Insight] = field(default_factory=list)
    final_summary: str = ""

    # PnL attribution / PnL 归因
    shadow_decision_id: str | None = None
    paper_order_id: str | None = None
    pnl_attribution: dict[str, Any] | None = None  # Filled post-execution

    # Timing / 时间
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    started_at_ms: int | None = None
    completed_at_ms: int | None = None

    # Safety / 安全
    is_simulated: bool = True
    data_category: str = "paper_simulated"

    def total_cost(self) -> float:
        return round(self.cost_usd + self.search_cost_usd, 6)

    def duration_ms(self) -> int | None:
        if self.started_at_ms and self.completed_at_ms:
            return self.completed_at_ms - self.started_at_ms
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "trigger": self.trigger,
            "initial_model": self.initial_model,
            "current_model": self.current_model,
            "model_upgraded": self.model_upgraded,
            "upgrade_reason": self.upgrade_reason,
            "session_budget_usd": self.session_budget_usd,
            "cost_usd": round(self.cost_usd, 6),
            "search_cost_usd": round(self.search_cost_usd, 6),
            "total_cost_usd": self.total_cost(),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "iterations": self.iterations,
            "tool_calls": [
                {
                    "tool_name": tc.tool_name,
                    "latency_ms": tc.latency_ms,
                    "error": tc.error,
                    "timestamp_ms": tc.timestamp_ms,
                }
                for tc in self.tool_calls
            ],
            "recommendation": {
                "action": self.recommendation.action,
                "symbol": self.recommendation.symbol,
                "confidence": self.recommendation.confidence,
                "edge_bps": self.recommendation.edge_bps,
                "reasoning": self.recommendation.reasoning,
                "freshness_note": self.recommendation.freshness_note,
                "risk_factors": self.recommendation.risk_factors,
                "suggested_size_fraction": self.recommendation.suggested_size_fraction,
                "time_horizon": self.recommendation.time_horizon,
                "source_tools": self.recommendation.source_tools,
            } if self.recommendation else None,
            "insights": [
                {
                    "category": ins.category,
                    "title": ins.title,
                    "detail": ins.detail,
                    "confidence": ins.confidence,
                }
                for ins in self.insights
            ],
            "final_summary": self.final_summary,
            "shadow_decision_id": self.shadow_decision_id,
            "paper_order_id": self.paper_order_id,
            "pnl_attribution": self.pnl_attribution,
            "created_at_ms": self.created_at_ms,
            "started_at_ms": self.started_at_ms,
            "completed_at_ms": self.completed_at_ms,
            "duration_ms": self.duration_ms(),
            "is_simulated": self.is_simulated,
            "data_category": self.data_category,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Pricing Table / 定价表
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ModelPricing:
    """Pricing for a single model tier / 单个模型层级的定价"""
    model_id: str
    input_per_mtok: float   # USD per million input tokens
    output_per_mtok: float  # USD per million output tokens
    last_verified_date: str = ""  # ISO date string

    def cost_for_tokens(self, input_tokens: int, output_tokens: int) -> float:
        input_cost = (input_tokens / 1_000_000) * self.input_per_mtok
        output_cost = (output_tokens / 1_000_000) * self.output_per_mtok
        return round(input_cost + output_cost, 6)


@dataclass
class PricingTable:
    """Complete pricing table for all models and search providers / 所有模型与搜索的完整定价表"""
    models: dict[str, ModelPricing] = field(default_factory=lambda: {
        MODEL_HAIKU: ModelPricing(
            model_id=MODEL_IDS[MODEL_HAIKU],
            input_per_mtok=0.80,
            output_per_mtok=4.00,
            last_verified_date="2026-03-27",
        ),
        MODEL_SONNET: ModelPricing(
            model_id=MODEL_IDS[MODEL_SONNET],
            input_per_mtok=3.00,
            output_per_mtok=15.00,
            last_verified_date="2026-03-27",
        ),
        MODEL_OPUS: ModelPricing(
            model_id=MODEL_IDS[MODEL_OPUS],
            input_per_mtok=15.00,
            output_per_mtok=75.00,
            last_verified_date="2026-03-27",
        ),
    })
    perplexity_per_search: float = 0.005
    perplexity_last_verified_date: str = "2026-03-27"

    def is_stale(self, current_date: str = "") -> bool:
        """Check if any pricing entry is older than 30 days / 检查定价是否超过 30 天未核实"""
        import datetime
        if not current_date:
            current_date = datetime.date.today().isoformat()
        try:
            today = datetime.date.fromisoformat(current_date)
        except ValueError:
            return True
        for mp in self.models.values():
            if not mp.last_verified_date:
                return True
            try:
                verified = datetime.date.fromisoformat(mp.last_verified_date)
                if (today - verified).days > PRICING_VERIFY_INTERVAL_DAYS:
                    return True
            except ValueError:
                return True
        if self.perplexity_last_verified_date:
            try:
                verified = datetime.date.fromisoformat(self.perplexity_last_verified_date)
                if (today - verified).days > PRICING_VERIFY_INTERVAL_DAYS:
                    return True
            except ValueError:
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "models": {
                k: {
                    "model_id": v.model_id,
                    "input_per_mtok": v.input_per_mtok,
                    "output_per_mtok": v.output_per_mtok,
                    "last_verified_date": v.last_verified_date,
                }
                for k, v in self.models.items()
            },
            "perplexity_per_search": self.perplexity_per_search,
            "perplexity_last_verified_date": self.perplexity_last_verified_date,
            "is_stale": self.is_stale(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Layer2Config:
    """Full configuration for the Layer 2 engine / Layer 2 引擎完整配置"""
    # Budget / 预算
    daily_hard_cap_usd: float = DEFAULT_DAILY_HARD_CAP_USD
    session_budget_sonnet_usd: float = DEFAULT_SESSION_BUDGET_SONNET_USD
    session_budget_opus_usd: float = DEFAULT_SESSION_BUDGET_OPUS_USD
    adaptive_enabled: bool = True
    adaptive_base_daily_usd: float = DEFAULT_ADAPTIVE_BASE_DAILY_USD
    adaptive_max_multiplier: float = 2.0
    adaptive_min_multiplier: float = 0.3

    # Model / 模型
    default_model: str = MODEL_SONNET
    allow_opus_upgrade: bool = True
    max_iterations: int = MAX_AGENT_ITERATIONS

    # Search / 搜索
    search_providers_enabled: list[str] = field(
        default_factory=lambda: list(SEARCH_PROVIDER_PRIORITY)
    )
    search_max_results: int = 5

    # Integration / 集成
    auto_submit_to_paper: bool = True
    confidence_threshold: float = 0.5
    edge_threshold_bps: float = 25.0  # Must exceed round-trip cost floor (~21 bps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_hard_cap_usd": self.daily_hard_cap_usd,
            "session_budget_sonnet_usd": self.session_budget_sonnet_usd,
            "session_budget_opus_usd": self.session_budget_opus_usd,
            "adaptive_enabled": self.adaptive_enabled,
            "adaptive_base_daily_usd": self.adaptive_base_daily_usd,
            "adaptive_max_multiplier": self.adaptive_max_multiplier,
            "adaptive_min_multiplier": self.adaptive_min_multiplier,
            "default_model": self.default_model,
            "allow_opus_upgrade": self.allow_opus_upgrade,
            "max_iterations": self.max_iterations,
            "search_providers_enabled": self.search_providers_enabled,
            "search_max_results": self.search_max_results,
            "auto_submit_to_paper": self.auto_submit_to_paper,
            "confidence_threshold": self.confidence_threshold,
            "edge_threshold_bps": self.edge_threshold_bps,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Adaptive Budget State / 自适应预算状态
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AdaptiveBudgetState:
    """Current adaptive budget state / 当前自适应预算状态"""
    multiplier: float = 1.0
    effective_daily_budget_usd: float = DEFAULT_ADAPTIVE_BASE_DAILY_USD
    roi_7d: float | None = None            # None = insufficient data
    ai_spend_7d_usd: float = 0.0
    paper_pnl_7d_usd: float = 0.0
    data_days: int = 0
    last_recalculated_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "multiplier": self.multiplier,
            "effective_daily_budget_usd": round(self.effective_daily_budget_usd, 2),
            "roi_7d": round(self.roi_7d, 4) if self.roi_7d is not None else None,
            "ai_spend_7d_usd": round(self.ai_spend_7d_usd, 4),
            "paper_pnl_7d_usd": round(self.paper_pnl_7d_usd, 4),
            "data_days": self.data_days,
            "last_recalculated_ms": self.last_recalculated_ms,
        }

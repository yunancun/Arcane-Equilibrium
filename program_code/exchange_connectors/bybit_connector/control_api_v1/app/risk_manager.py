from __future__ import annotations

"""
Auto Risk Control Layer / 自动风险控制层
三层优先级风控框架 + 对抗性止损 + AI 注意力税

MODULE_NOTE (中文):
  本模块实现全品类风控框架，核心是三层优先级：
  P0 品类专属（用户按品类设置，覆盖 P1，只能更严格）
  P1 全局（用户设置全局上限）
  P2 Agent 自适应（Agent 在有效上限内自主调整，只能收紧）

  对抗性止损：硬止损（绝对防线）+ 软止损（Agent 评估）
  AI 注意力税：持仓真实成本 = 金融成本 + AI 监控成本
  所有操作都在 paper trading 范围内（is_simulated=True）。

MODULE_NOTE (English):
  This module implements the full-category risk control framework with 3-tier priority:
  P0 category-specific (user-set, overrides P1, can only be stricter)
  P1 global (user-set global caps)
  P2 agent-adaptive (agent adjusts within effective cap, can only tighten)

  Adversarial stops: hard stop (absolute defense) + soft stop (agent evaluates)
  AI attention tax: position real cost = financial + AI monitoring cost
  All operations within paper trading scope (is_simulated=True).
"""

import datetime
import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

from .portfolio_risk_control import PortfolioRiskControl, PortfolioRiskConfig

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

ALL_CATEGORIES = ["spot", "linear", "inverse", "option"]

# AI attention tax hourly rates by attention level (USD/hour estimates)
# AI 注意力税：按注意力等级的每小时费率（美元/小时估算）
AI_TAX_RATES = {
    "dormant": 0.000,
    "low": 0.003,
    "medium": 0.010,
    "high": 0.050,
    "critical": 0.100,
}

# Cost efficiency grades / 成本效率等级
GRADE_THRESHOLDS = [
    (0.2, "A"),
    (0.4, "B"),
    (0.6, "C"),
    (0.8, "D"),
]


def cost_efficiency_grade(ratio: float) -> str:
    for threshold, grade in GRADE_THRESHOLDS:
        if ratio < threshold:
            return grade
    return "F"


# ═══════════════════════════════════════════════════════════════════════════════
# Adversarial Stop Logic / 对抗性止损逻辑
# ═══════════════════════════════════════════════════════════════════════════════

# Price history window for ATR calculation / ATR 计算用价格历史窗口
ATR_WINDOW_SECONDS = 300  # 5 minutes of tick data
ATR_MIN_SAMPLES = 10      # Minimum samples to compute ATR

# Anti-clustering: max random offset as fraction of stop distance
# 反聚集：随机偏移占止损距离的最大比例
ANTI_CLUSTER_OFFSET_FRACTION = 0.15  # ±15% of stop distance

# Regime-aware stop/TP/time multipliers
# 市场状态感知止损/止盈/时间乘数
# trending: wider stop + larger TP + hold longer (trend continuation)
# volatile: wider stop (avoid noise) + smaller TP (take profit faster) + exit faster
# ranging: tighter stop + smaller TP (mean-revert quickly) + exit faster
# squeeze: very tight stop + small TP (breakout can fail fast) + exit very fast
# unknown: neutral
REGIME_STOP_MULTIPLIERS: dict[str, float] = {
    "trending": 1.0,
    "volatile": 1.5,
    "ranging": 0.7,
    "squeeze": 0.6,
    "unknown": 1.0,
}
REGIME_TP_MULTIPLIERS: dict[str, float] = {
    "trending": 1.5,
    "volatile": 0.8,
    "ranging": 0.7,
    "squeeze": 0.5,
    "unknown": 1.0,
}
# B6: squeeze multiplier changed 0.3→1.0 — mean-reversion strategies need 24-48h to complete
# B6：squeeze 乘数从 0.3 改为 1.0 — 均值回归策略需要 24-48h 完成
REGIME_TIME_MULTIPLIERS: dict[str, float] = {
    "trending": 1.5,
    "volatile": 0.8,
    "ranging": 0.8,
    "squeeze": 1.0,
    "unknown": 1.0,
}

# Spike detection thresholds / 尖刺检测阈值
SPIKE_REVERT_THRESHOLD_PCT = 0.5    # Price reverts >50% within window → spike
SPIKE_WINDOW_SECONDS = 180          # 3 minute window for spike detection
MAX_SPIKE_SUPPRESSIONS_PER_POSITION = 3  # Max times soft stop can be suppressed per position


class PriceHistoryTracker:
    """
    Tracks recent price ticks per symbol for ATR and spike detection.
    跟踪每个品种的近期价格 tick，用于 ATR 和尖刺检测。
    """

    def __init__(self, window_sec: float = ATR_WINDOW_SECONDS) -> None:
        self._history: dict[str, list[tuple[float, float]]] = {}  # symbol → [(ts, price)]
        self._window_sec = window_sec

    def record(self, symbol: str, price: float) -> None:
        if symbol not in self._history:
            self._history[symbol] = []
        now = time.time()
        self._history[symbol].append((now, price))
        # Prune old entries
        cutoff = now - self._window_sec
        self._history[symbol] = [(t, p) for t, p in self._history[symbol] if t >= cutoff]
        # Prune symbols with no recent data (prevent unbounded growth)
        if len(self._history) > 100:
            stale_symbols = [s for s, hist in self._history.items() if not hist]
            for s in stale_symbols:
                del self._history[s]

    def get_prices(self, symbol: str) -> list[tuple[float, float]]:
        return self._history.get(symbol, [])

    def compute_atr_pct(self, symbol: str) -> float | None:
        """
        Compute ATR-like metric as percentage of price.
        计算 ATR 类指标（占价格的百分比）。

        Uses absolute price changes between consecutive ticks.
        使用连续 tick 之间的绝对价格变化。
        """
        prices = self.get_prices(symbol)
        if len(prices) < ATR_MIN_SAMPLES:
            return None
        changes = []
        for i in range(1, len(prices)):
            prev_p = prices[i - 1][1]
            curr_p = prices[i][1]
            if prev_p > 0:
                changes.append(abs(curr_p - prev_p) / prev_p * 100)
        if not changes:
            return None
        return sum(changes) / len(changes)

    def detect_spike(self, symbol: str, current_price: float) -> dict[str, Any] | None:
        """
        Detect if current price movement looks like a stop-hunting spike.
        检测当前价格走势是否像止损猎杀的尖刺。

        A spike = rapid move to extreme then significant reversion within window.
        尖刺 = 快速到达极端值后在窗口内显著回归。
        """
        prices = self.get_prices(symbol)
        if len(prices) < 5:
            return None

        now = time.time()
        window_cutoff = now - SPIKE_WINDOW_SECONDS
        recent = [(t, p) for t, p in prices if t >= window_cutoff]
        if len(recent) < 3:
            return None

        # Find the extreme in the window
        min_p = min(p for _, p in recent)
        max_p = max(p for _, p in recent)
        first_p = recent[0][1]

        if first_p <= 0 or max_p <= min_p:
            return None

        total_range = max_p - min_p
        range_pct = total_range / first_p * 100

        # Check if price has reverted significantly from the extreme
        if current_price > first_p:
            # Price went up — check if it spiked down then came back
            revert_from_min = (current_price - min_p) / total_range if total_range > 0 else 0
            if revert_from_min > SPIKE_REVERT_THRESHOLD_PCT and range_pct > 0.3:
                return {
                    "type": "spike_down_reverted",
                    "range_pct": round(range_pct, 3),
                    "revert_fraction": round(revert_from_min, 3),
                    "confidence": min(revert_from_min, 0.95),
                }
        else:
            # Price went down — check if it spiked up then came back
            revert_from_max = (max_p - current_price) / total_range if total_range > 0 else 0
            if revert_from_max > SPIKE_REVERT_THRESHOLD_PCT and range_pct > 0.3:
                return {
                    "type": "spike_up_reverted",
                    "range_pct": round(range_pct, 3),
                    "revert_fraction": round(revert_from_max, 3),
                    "confidence": min(revert_from_max, 0.95),
                }

        return None


def compute_dynamic_stop_pct(
    base_stop_pct: float,
    atr_pct: float | None,
    symbol: str,
    entry_ts_ms: int,
    regime: str = "unknown",
) -> float:
    """
    Compute ATR-adjusted stop loss with anti-clustering random offset and regime scaling.
    计算 ATR 自适应止损 + 反聚集随机偏移 + 市场状态缩放。

    If ATR available: stop = max(base, 1.5 × ATR) + random offset
    If no ATR: stop = base + small random offset (still unpredictable)
    Regime multiplier widens stop in volatile/trending markets, tightens in ranging/squeeze.
    """
    regime_mult = REGIME_STOP_MULTIPLIERS.get(regime, 1.0)
    base_stop_pct = base_stop_pct * regime_mult

    if atr_pct is not None and atr_pct > 0:
        # ATR-based: use 1.5x ATR as minimum, but don't exceed base cap
        atr_stop = atr_pct * 1.5
        effective = max(base_stop_pct, min(atr_stop, base_stop_pct * 2.0))
    else:
        effective = base_stop_pct

    # Anti-clustering: deterministic-ish random offset based on symbol + entry time
    # This ensures the same position always gets the same offset (reproducible)
    # but different positions get different offsets (unpredictable to outsiders)
    seed_str = f"{symbol}:{entry_ts_ms}"
    seed_hash = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed_hash)
    offset = rng.uniform(-ANTI_CLUSTER_OFFSET_FRACTION, ANTI_CLUSTER_OFFSET_FRACTION)
    effective *= (1.0 + offset)

    # Never go below a tiny minimum
    return max(effective, 0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# P1: Global Risk Config / 全局风控配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GlobalRiskConfig:
    """
    Global risk caps set by operator (P1). Agent cannot loosen these.
    操作员设置的全局风险上限（P1）。Agent 不可放宽。
    """
    # Stop loss / take profit
    max_stop_loss_pct: float = 5.0
    max_take_profit_pct: float = 20.0

    # Position sizing
    max_single_position_pct: float = 10.0
    max_total_exposure_pct: float = 50.0
    max_correlated_exposure_pct: float = 30.0
    max_leverage: float = 20.0

    # Drawdown & cooldown
    max_session_drawdown_pct: float = 15.0
    max_daily_loss_pct: float = 5.0
    consecutive_loss_cooldown_count: int = 3
    consecutive_loss_cooldown_minutes: float = 30.0

    # Holding time
    max_holding_hours: float = 72.0

    # Category whitelist
    allowed_categories: list[str] = field(
        default_factory=lambda: ["spot", "linear", "inverse"]
    )

    # Margin & position mode preference
    preferred_margin_mode: str = "isolated"
    preferred_position_mode: str = "one_way"

    # AI attention tax
    max_cost_edge_ratio: float = 0.8

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_stop_loss_pct": self.max_stop_loss_pct,
            "max_take_profit_pct": self.max_take_profit_pct,
            "max_single_position_pct": self.max_single_position_pct,
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "max_correlated_exposure_pct": self.max_correlated_exposure_pct,
            "max_leverage": self.max_leverage,
            "max_session_drawdown_pct": self.max_session_drawdown_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "consecutive_loss_cooldown_count": self.consecutive_loss_cooldown_count,
            "consecutive_loss_cooldown_minutes": self.consecutive_loss_cooldown_minutes,
            "max_holding_hours": self.max_holding_hours,
            "allowed_categories": self.allowed_categories,
            "preferred_margin_mode": self.preferred_margin_mode,
            "preferred_position_mode": self.preferred_position_mode,
            "max_cost_edge_ratio": self.max_cost_edge_ratio,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GlobalRiskConfig:
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k) and v is not None})


# ═══════════════════════════════════════════════════════════════════════════════
# P0: Category Risk Config / 品类专属风控配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CategoryRiskConfig:
    """
    Category-specific risk overrides (P0). Can only be stricter than P1.
    品类专属风控覆盖（P0）。只能比 P1 更严格。
    """
    category: str = "linear"
    enabled: bool = True

    # Overridable fields (None = use global)
    max_leverage: float | None = None
    max_single_position_pct: float | None = None
    max_total_exposure_pct: float | None = None
    max_stop_loss_pct: float | None = None
    max_holding_hours: float | None = None
    allowed_symbols: list[str] | None = None

    # Spot-specific
    spot_allow_margin: bool = False

    # Perpetual-specific
    perp_max_funding_rate_abs: float = 0.03
    perp_auto_deleverage_threshold: float = 0.8

    # Options-specific
    option_max_premium_pct: float = 5.0
    option_max_delta_exposure: float = 0.5
    option_allowed_strategies: list[str] = field(
        default_factory=lambda: ["long_call", "long_put", "covered_call", "protective_put"]
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "enabled": self.enabled,
            "max_leverage": self.max_leverage,
            "max_single_position_pct": self.max_single_position_pct,
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "max_stop_loss_pct": self.max_stop_loss_pct,
            "max_holding_hours": self.max_holding_hours,
            "allowed_symbols": self.allowed_symbols,
            "spot_allow_margin": self.spot_allow_margin,
            "perp_max_funding_rate_abs": self.perp_max_funding_rate_abs,
            "perp_auto_deleverage_threshold": self.perp_auto_deleverage_threshold,
            "option_max_premium_pct": self.option_max_premium_pct,
            "option_max_delta_exposure": self.option_max_delta_exposure,
            "option_allowed_strategies": self.option_allowed_strategies,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CategoryRiskConfig:
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k) and v is not None})


# ═══════════════════════════════════════════════════════════════════════════════
# P2: Agent Risk Params / Agent 自适应风控参数
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AgentRiskParams:
    """
    Agent-adjustable risk parameters (P2). Bounded by effective P0/P1 cap.
    Agent 可调风控参数（P2）。受 P0/P1 有效上限约束。
    """
    effective_stop_loss_pct: float = 2.0
    effective_take_profit_pct: float = 4.0

    trailing_stop_enabled: bool = False
    trailing_stop_activation_pct: float = 1.0
    trailing_stop_distance_pct: float = 0.8

    position_size_multiplier: float = 1.0  # 0.1 - 1.0

    category_preference_weights: dict[str, float] = field(
        default_factory=lambda: {"spot": 0.3, "linear": 0.5, "inverse": 0.2}
    )

    prefer_limit_over_market: bool = True
    use_reduce_only_for_close: bool = True
    use_post_only_for_limit: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_stop_loss_pct": self.effective_stop_loss_pct,
            "effective_take_profit_pct": self.effective_take_profit_pct,
            "trailing_stop_enabled": self.trailing_stop_enabled,
            "trailing_stop_activation_pct": self.trailing_stop_activation_pct,
            "trailing_stop_distance_pct": self.trailing_stop_distance_pct,
            "position_size_multiplier": self.position_size_multiplier,
            "category_preference_weights": self.category_preference_weights,
            "prefer_limit_over_market": self.prefer_limit_over_market,
            "use_reduce_only_for_close": self.use_reduce_only_for_close,
            "use_post_only_for_limit": self.use_post_only_for_limit,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentRiskParams:
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k) and v is not None})


# ═══════════════════════════════════════════════════════════════════════════════
# 3-Tier Resolution / 三层合并逻辑
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_effective_limit(
    param_name: str,
    global_config: GlobalRiskConfig,
    category_config: CategoryRiskConfig | None,
) -> float:
    """
    Merge P0 + P1: effective_cap = min(P0 ?? P1, P1).
    P0 can only be stricter (smaller cap).
    """
    global_val = getattr(global_config, param_name, None)
    if global_val is None:
        return float("inf")

    if category_config is not None:
        cat_val = getattr(category_config, param_name, None)
        if cat_val is not None:
            return min(cat_val, global_val)

    return global_val


# ═══════════════════════════════════════════════════════════════════════════════
# Risk Manager / 风控管理器
# ═══════════════════════════════════════════════════════════════════════════════

class RiskManager:
    """
    Auto Risk Control Layer with 3-tier priority.
    三层优先级自动风控管理器。

    Hooks into PaperTradingEngine's submit_order() and tick() flow.
    接入 Paper Trading Engine 的 submit_order() 和 tick() 流程。
    """

    def __init__(
        self,
        config: GlobalRiskConfig | None = None,
        category_configs: dict[str, CategoryRiskConfig] | None = None,
        agent_params: AgentRiskParams | None = None,
    ) -> None:
        self._config = config or GlobalRiskConfig()
        self._category_configs: dict[str, CategoryRiskConfig] = category_configs or {}
        self._agent_params = agent_params or AgentRiskParams()
        self._trailing_stops: dict[str, dict[str, float]] = {}
        self._consecutive_losses: int = 0
        self._cooldown_until_ts_ms: int = 0
        self._price_tracker = PriceHistoryTracker()
        self._spike_suppression_count: dict[str, int] = {}  # symbol → count
        self._governance_hub = None  # Optional GovernanceHub for governance integration
        self._h0_gate: Any = None  # P1-16: sync cooldown to H0Gate / 同步冷卻期到 H0 確定性門控
        self._change_audit_log = None  # Optional ChangeAuditLog for audit tracking
        # T2.01: Portfolio Risk Control integration / 组合级风控
        self._portfolio_risk_control = PortfolioRiskControl(config=PortfolioRiskConfig())

    # ── Properties ──

    @property
    def config(self) -> GlobalRiskConfig:
        return self._config

    @property
    def agent_params(self) -> AgentRiskParams:
        return self._agent_params

    def set_governance_hub(self, hub: Any) -> None:
        """Inject GovernanceHub for governance state machine integration / 注入治理集線器"""
        self._governance_hub = hub

    def set_h0_gate(self, gate: Any) -> None:
        """Inject H0Gate to receive cooldown sync on consecutive loss (P1-16).
        注入 H0Gate 以在連續虧損冷卻期時同步狀態（P1-16）。
        """
        self._h0_gate = gate

    def set_change_audit_log(self, cal: Any) -> None:
        """Inject ChangeAuditLog for audit trail tracking / 注入变更审计日志"""
        self._change_audit_log = cal

    def set_portfolio_risk_control(self, prc: PortfolioRiskControl) -> None:
        """Inject or replace PortfolioRiskControl instance / 注入或替换组合风控实例"""
        self._portfolio_risk_control = prc

    def record_market_prices_for_portfolio_risk(self, market_prices: dict[str, float]) -> None:
        """
        Record market prices to PortfolioRiskControl for correlation tracking.
        记录市场价格用于组合相关性跟踪。
        """
        if self._portfolio_risk_control:
            self._portfolio_risk_control.record_prices(market_prices)

    # ── Config Management ──

    def update_global_config(self, updates: dict[str, Any]) -> GlobalRiskConfig:
        """Update P1 global config fields (only dataclass fields, not methods)."""
        valid_fields = GlobalRiskConfig.__dataclass_fields__
        for k, v in updates.items():
            if v is not None and k in valid_fields:
                old_value = getattr(self._config, k, None)
                setattr(self._config, k, v)
                # T3.06: Record risk config changes in audit log
                if self._change_audit_log:
                    try:
                        from .change_audit_log import ChangeType
                        self._change_audit_log.record_change(
                            change_type=ChangeType.CONFIG_CHANGE,
                            who="agent",
                            what=f"Updated risk config parameter: {k}",
                            reason="Risk parameter adjustment",
                            old_value=old_value,
                            new_value=v,
                            affected_components=["RiskManager"],
                            auto_approve=True,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record config change in audit log: {e} (non-fatal)")
        return self._config

    def update_category_config(self, category: str, updates: dict[str, Any]) -> CategoryRiskConfig:
        """Update P0 category config. Creates if not exists."""
        if category not in self._category_configs:
            self._category_configs[category] = CategoryRiskConfig(category=category)
        cfg = self._category_configs[category]
        valid_fields = CategoryRiskConfig.__dataclass_fields__
        for k, v in updates.items():
            if v is not None and k in valid_fields:
                setattr(cfg, k, v)
        return cfg

    def get_category_config(self, category: str) -> CategoryRiskConfig | None:
        return self._category_configs.get(category)

    def agent_adjust(self, updates: dict[str, Any]) -> AgentRiskParams:
        """
        Agent adjusts P2 params within effective caps.
        Agent 在有效上限内调整 P2 参数。
        Values exceeding caps are clamped silently.
        """
        for k, v in updates.items():
            if v is None or not hasattr(self._agent_params, k):
                continue

            if k == "effective_stop_loss_pct":
                cap = self._config.max_stop_loss_pct
                setattr(self._agent_params, k, min(v, cap))
            elif k == "effective_take_profit_pct":
                cap = self._config.max_take_profit_pct
                setattr(self._agent_params, k, min(v, cap))
            elif k == "position_size_multiplier":
                setattr(self._agent_params, k, max(0.1, min(v, 1.0)))
            else:
                setattr(self._agent_params, k, v)

        return self._agent_params

    # ── Effective Limit Helpers ──

    def effective_stop_loss_pct(self, category: str = "linear") -> float:
        cap = resolve_effective_limit("max_stop_loss_pct", self._config, self._category_configs.get(category))
        return min(self._agent_params.effective_stop_loss_pct, cap)

    def effective_take_profit_pct(self, category: str = "linear") -> float:
        cap = resolve_effective_limit("max_take_profit_pct", self._config, self._category_configs.get(category))
        return min(self._agent_params.effective_take_profit_pct, cap)

    def effective_max_leverage(self, category: str = "linear") -> float:
        return resolve_effective_limit("max_leverage", self._config, self._category_configs.get(category))

    def effective_max_single_position_pct(self, category: str = "linear") -> float:
        return resolve_effective_limit("max_single_position_pct", self._config, self._category_configs.get(category))

    # ── Pre-Order Check / 下单前检查 ──

    def check_order_allowed(
        self,
        state: dict[str, Any],
        symbol: str,
        side: str,
        qty: float,
        price: float,
        leverage: float = 1.0,
        category: str = "linear",
        market_prices: dict[str, float] | None = None,
    ) -> tuple[bool, str]:
        """
        Pre-trade risk gate. Returns (allowed, reason).
        下单前风控门。返回 (是否允许, 原因)。
        """
        sess = state.get("session", {})

        # Governance Hub authorization check / 治理集線器授權檢查
        if self._governance_hub:
            try:
                if not self._governance_hub.is_authorized():
                    return False, "governance_not_authorized"
            except Exception as exc:
                logger.error("Governance is_authorized error — fail-closed: %s", exc)
                return False, "governance_check_error"

        # Session halted?
        if sess.get("session_halted"):
            return False, "session_halted"

        # Cooldown active?
        now_ms = int(time.time() * 1000)
        if self._cooldown_until_ts_ms > now_ms:
            remaining_s = (self._cooldown_until_ts_ms - now_ms) / 1000
            return False, f"cooldown_active_{remaining_s:.0f}s_remaining"

        # Category allowed?
        if category not in self._config.allowed_categories:
            return False, f"category_{category}_not_allowed"

        cat_cfg = self._category_configs.get(category)
        if cat_cfg is not None and not cat_cfg.enabled:
            return False, f"category_{category}_disabled"

        # Symbol allowed?
        if cat_cfg and cat_cfg.allowed_symbols is not None:
            if symbol not in cat_cfg.allowed_symbols:
                return False, f"symbol_{symbol}_not_in_category_whitelist"

        # Determine if this order reduces an existing position (needed early for daily loss check)
        # 判断是否为减仓单（日内亏损检查需要提前判断）
        positions = state.get("positions", {})
        existing_pos = positions.get(symbol)
        is_reducing = (
            existing_pos is not None
            and existing_pos.get("side") != side
            and qty <= existing_pos.get("qty", 0)
        )

        # Daily loss check (block NEW orders if daily loss exceeded, allow reducing)
        # 日内亏损检查（超限时阻止新开仓，但允许减仓/平仓）
        if not is_reducing:
            today_str = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
            daily_start = sess.get("daily_start_balance_usdt", sess.get("initial_paper_balance_usdt", 0))
            stored_date = sess.get("daily_start_date", "")
            balance_now = sess.get("current_paper_balance_usdt", 0)
            if stored_date == today_str and daily_start > 0 and balance_now < daily_start:
                daily_loss_pct = ((daily_start - balance_now) / daily_start) * 100
                if daily_loss_pct >= self._config.max_daily_loss_pct:
                    return False, f"daily_loss_{daily_loss_pct:.1f}pct_exceeds_max_{self._config.max_daily_loss_pct:.1f}pct"

        # Leverage check
        max_lev = self.effective_max_leverage(category)
        if leverage > max_lev:
            return False, f"leverage_{leverage}_exceeds_max_{max_lev}"

        # Position size check (skip for reducing orders)
        # 仓位大小检查（减仓单跳过）
        balance = sess.get("current_paper_balance_usdt", 0)
        if balance <= 0:
            return False, "zero_balance"
        notional = qty * price

        if not is_reducing:
            position_pct = (notional / balance) * 100
            max_pos = self.effective_max_single_position_pct(category)
            effective_max = max_pos * self._agent_params.position_size_multiplier
            if position_pct > effective_max:
                return False, f"position_size_{position_pct:.1f}pct_exceeds_max_{effective_max:.1f}pct"

        # Total exposure check (reducing orders decrease exposure, skip check)
        # 总敞口检查（减仓单减少敞口，跳过）
        if not is_reducing:
            if not market_prices:
                logger.warning("No market prices for exposure calculation, using entry prices (may be stale) / 无市场价格，使用入场价（可能过时）")
            total_exposure = sum(
                p.get("qty", 0) * (market_prices.get(p.get("symbol", ""), p.get("avg_entry_price", 0)) if market_prices else p.get("avg_entry_price", 0))
                for p in positions.values()
            )
            # Include pending unfilled orders (working/partially_filled) in exposure
            # 将未成交挂单（working/partially_filled）计入敞口
            pending_notional = 0
            for o in state.get("orders", []):
                if o.get("state") not in ("paper_order_working", "paper_order_partially_filled"):
                    continue
                remaining = o.get("remaining_qty", 0)
                oprice = o.get("price")
                if oprice is None or oprice == 0:
                    # Market orders or orders without price: use market price if available
                    # 市价单或无价格的订单：使用市场价（如果可用）
                    fallback = market_prices.get(o.get("symbol", ""), 0) if market_prices else 0
                    if fallback == 0:
                        logger.warning(
                            "Pending order %s has no price and no market price, exposure=0 / "
                            "挂单 %s 无价格且无市场价，敞口=0",
                            o.get("order_id", "?"), o.get("order_id", "?"),
                        )
                    oprice = fallback
                pending_notional += remaining * oprice
            new_total = total_exposure + pending_notional + notional
            total_pct = (new_total / balance) * 100
            max_total = resolve_effective_limit("max_total_exposure_pct", self._config, self._category_configs.get(category))
            if total_pct > max_total:
                return False, f"total_exposure_{total_pct:.1f}pct_exceeds_max_{max_total:.1f}pct"

            # Correlated exposure (same side) check
            # 相关性敞口（同方向）检查
            same_side_exposure = sum(
                p.get("qty", 0) * (market_prices.get(p.get("symbol", ""), p.get("avg_entry_price", 0)) if market_prices else p.get("avg_entry_price", 0))
                for p in positions.values()
                if p.get("side") == side
            )
            pending_same_side = 0
            for o in state.get("orders", []):
                if o.get("state") not in ("paper_order_working", "paper_order_partially_filled"):
                    continue
                if o.get("side") != side:
                    continue
                remaining = o.get("remaining_qty", 0)
                oprice = o.get("price")
                if oprice is None or oprice == 0:
                    oprice = market_prices.get(o.get("symbol", ""), 0) if market_prices else 0
                pending_same_side += remaining * oprice
            new_corr = same_side_exposure + pending_same_side + notional
            corr_pct = (new_corr / balance) * 100
            max_corr = self._config.max_correlated_exposure_pct
            if corr_pct > max_corr:
                return False, f"correlated_exposure_{corr_pct:.1f}pct_exceeds_max_{max_corr:.1f}pct"

            # T2.01: Portfolio Risk Control check / 组合级风控检查
            try:
                allowed, reason = self._portfolio_risk_control.check_new_entry(
                    symbol=symbol,
                    side=side,
                    notional=notional,
                    positions=positions,
                    balance=balance,
                    market_prices=market_prices,
                )
                if not allowed:
                    # Only block on correlation (P3 risk). Sector/reserve are covered by P1/P2
                    # 仅在相关性上阻止（P3 风险）。部门/储备由 P1/P2 覆盖
                    if "correlation" in reason:
                        return False, f"portfolio_risk_{reason}"
                    else:
                        # Sector/reserve buffer: advisory only (P1/P2 limits take precedence)
                        # 部门/储备缓冲：仅建议性（P1/P2 限制优先）
                        logger.warning("Portfolio risk advisory: %s (non-blocking, P1/P2 check passed)", reason)
            except Exception as exc:
                logger.warning("Portfolio risk check error (non-fatal, passing through): %s", exc)

        return True, "ok"

    # ── Tick-Time Position Checks / Tick 时持仓检查 ──

    def check_positions_on_tick(
        self,
        state: dict[str, Any],
        market_prices: dict[str, float],
    ) -> list[dict[str, Any]]:
        """
        Check all positions against risk triggers. Returns list of close orders.
        检查所有持仓的风控触发条件。返回需要平仓的订单列表。

        Returns: [{"symbol", "side", "qty", "reason"}, ...]
        """
        close_orders: list[dict[str, Any]] = []
        positions = state.get("positions", {})
        sess = state.get("session", {})
        now_ms_val = int(time.time() * 1000)

        # Record current prices for ATR + spike detection / 记录当前价格（ATR + 尖刺检测）
        for sym, mp in market_prices.items():
            if mp > 0:
                self._price_tracker.record(sym, mp)

        for symbol, pos in list(positions.items()):
            mp = market_prices.get(symbol)
            if mp is None or mp <= 0:
                continue

            entry = pos.get("avg_entry_price", 0)
            if entry <= 0:
                continue

            qty = pos.get("qty", 0)
            if qty <= 0:
                continue

            pos_side = pos.get("side", "Buy")
            category = pos.get("category", "linear")

            # PnL % for this position
            if pos_side == "Buy":
                pnl_pct = ((mp - entry) / entry) * 100
            else:
                pnl_pct = ((entry - mp) / entry) * 100

            # 1. Hard stop loss (P1 cap — absolute defense, NEVER skip, invisible to exchange)
            # 硬止损（P1 上限 — 绝对防线，永远不跳过，对交易所不可见）
            hard_sl = self._config.max_stop_loss_pct
            if pnl_pct <= -hard_sl:
                close_orders.append({
                    "symbol": symbol, "qty": qty,
                    "reason": f"hard_stop_loss_{pnl_pct:.2f}pct",
                })
                continue

            # 2. Soft stop loss with adversarial logic / 对抗性软止损
            # Uses ATR-dynamic level + anti-clustering offset + spike detection + regime scaling
            regime = pos.get("regime", "unknown")
            base_soft_sl = self.effective_stop_loss_pct(category)
            atr_pct = self._price_tracker.compute_atr_pct(symbol)
            entry_ts = pos.get("opened_ts_ms", now_ms_val)
            dynamic_sl = compute_dynamic_stop_pct(base_soft_sl, atr_pct, symbol, entry_ts, regime=regime)

            if pnl_pct <= -dynamic_sl:
                # Check for spike (possible stop hunting) / 检查尖刺（可能的止损猎杀）
                spike = self._price_tracker.detect_spike(symbol, mp)
                suppress_count = self._spike_suppression_count.get(symbol, 0)
                if spike and spike.get("confidence", 0) > 0.6 and suppress_count < MAX_SPIKE_SUPPRESSIONS_PER_POSITION:
                    # Suspected stop hunting — hold position, don't close (limited suppressions)
                    # 疑似止损猎杀 — 持有仓位，不平仓（有次数限制，硬止损仍生效）
                    self._spike_suppression_count[symbol] = suppress_count + 1
                    logger.info(
                        "Spike detected for %s (confidence=%.2f, suppression %d/%d), soft stop suppressed at pnl=%.2f%%",
                        symbol, spike["confidence"], suppress_count + 1, MAX_SPIKE_SUPPRESSIONS_PER_POSITION, pnl_pct,
                    )
                    continue
                close_orders.append({
                    "symbol": symbol, "qty": qty,
                    "reason": f"soft_stop_loss_{pnl_pct:.2f}pct_dynamic_{dynamic_sl:.2f}pct"
                             f"{'_atr=' + f'{atr_pct:.3f}' if atr_pct else ''}",
                })
                continue

            # 3. Take profit (regime-adjusted)
            tp = self.effective_take_profit_pct(category) * REGIME_TP_MULTIPLIERS.get(regime, 1.0)
            if pnl_pct >= tp:
                close_orders.append({
                    "symbol": symbol, "qty": qty,
                    "reason": f"take_profit_{pnl_pct:.2f}pct",
                })
                continue

            # 4. Trailing stop
            if self._agent_params.trailing_stop_enabled and pnl_pct > 0:
                ts_state = self._trailing_stops.get(symbol, {})
                activation = self._agent_params.trailing_stop_activation_pct
                distance = self._agent_params.trailing_stop_distance_pct

                if pnl_pct >= activation and "peak_pnl_pct" not in ts_state:
                    # First entry into activation zone — initialize peak
                    ts_state["peak_pnl_pct"] = pnl_pct
                    self._trailing_stops[symbol] = ts_state

                if "peak_pnl_pct" in ts_state:
                    # Trailing stop is active — update peak and check distance
                    peak_pnl = ts_state["peak_pnl_pct"]
                    if pnl_pct > peak_pnl:
                        ts_state["peak_pnl_pct"] = pnl_pct
                        self._trailing_stops[symbol] = ts_state
                        peak_pnl = pnl_pct

                    drawback = peak_pnl - pnl_pct
                    if drawback >= distance:
                        close_orders.append({
                            "symbol": symbol, "qty": qty,
                            "reason": f"trailing_stop_peak_{peak_pnl:.2f}pct_current_{pnl_pct:.2f}pct",
                        })
                        continue

            # 5. Max holding time (regime-adjusted)
            opened_ts = pos.get("opened_ts_ms", 0)
            if opened_ts > 0:
                holding_hours = (now_ms_val - opened_ts) / (1000 * 3600)
                max_hold = resolve_effective_limit("max_holding_hours", self._config, self._category_configs.get(category))
                max_hold = max_hold * REGIME_TIME_MULTIPLIERS.get(regime, 1.0)
                if holding_hours >= max_hold:
                    close_orders.append({
                        "symbol": symbol, "qty": qty,
                        "reason": f"max_holding_time_{holding_hours:.1f}h",
                    })
                    continue

        # 6. AI attention tax update / AI 注意力税更新
        # Compute attention-based burn rate ONCE outside the loop (not per-position)
        n_active_orders = len([
            o for o in state.get("orders", [])
            if o.get("state") in ("paper_order_working", "paper_order_partially_filled")
        ])
        if len(positions) == 0 and n_active_orders == 0:
            base_burn_rate = AI_TAX_RATES["dormant"]
        elif n_active_orders > 0:
            base_burn_rate = AI_TAX_RATES["high"]
        elif len(positions) > 0:
            base_burn_rate = AI_TAX_RATES["medium"]
        else:
            base_burn_rate = AI_TAX_RATES["low"]

        for symbol, pos in positions.items():
            hc = pos.get("holding_cost")
            if hc is None:
                continue
            opened_ts = pos.get("opened_ts_ms", 0)
            if opened_ts <= 0:
                continue

            holding_hours = (now_ms_val - opened_ts) / (1000 * 3600)
            hc["hourly_ai_burn_rate_usd"] = base_burn_rate
            hc["ai_cost_attributed_usd"] = round(holding_hours * base_burn_rate, 6)

            # Financial cost = fees paid for this position's fills (approximated from position data)
            # The exact fee is tracked per fill; here we use a rough estimate
            entry = pos.get("avg_entry_price", 0)
            qty = pos.get("qty", 0)
            notional = entry * qty
            hc["financial_cost_usd"] = round(notional * 0.0011, 6)  # ~0.11% round trip estimate

            hc["total_holding_cost_usd"] = round(
                hc["financial_cost_usd"] + hc["ai_cost_attributed_usd"], 6
            )

            # Estimate remaining edge from unrealized PnL
            mp = market_prices.get(symbol, entry)
            if pos.get("side") == "Buy":
                edge_usd = (mp - entry) * qty
            else:
                edge_usd = (entry - mp) * qty
            hc["estimated_remaining_edge_usd"] = round(edge_usd - hc["total_holding_cost_usd"], 6)

            # Cost efficiency ratio and grade
            if edge_usd > 0:
                hc["cost_edge_ratio"] = round(hc["total_holding_cost_usd"] / edge_usd, 4)
            elif hc["total_holding_cost_usd"] > 0:
                hc["cost_edge_ratio"] = 9.99  # costs exist but no edge
            else:
                hc["cost_edge_ratio"] = 0.0
            hc["cost_efficiency_grade"] = cost_efficiency_grade(hc["cost_edge_ratio"])

            # If cost_edge_ratio exceeds max AND position was profitable → recommend close
            # (losing positions are handled by stop loss, not AI tax)
            # Guard: only close if edge covers the taker close fee; otherwise closing
            # creates a net loss (edge < close_fee means we'd exit at a net loss).
            # 只有盈利仓位被 AI 税吃光利润时才触发（亏损仓位由止损处理）。
            # 保护：edge 必须覆盖平仓 taker 手续费，否则平仓本身造成净亏损。
            taker_close_fee_usd = notional * 0.00055  # DEFAULT_TAKER_FEE_RATE
            if (edge_usd > taker_close_fee_usd
                    and hc["cost_edge_ratio"] >= self._config.max_cost_edge_ratio):
                already_closing = any(co["symbol"] == symbol for co in close_orders)
                if not already_closing and pos.get("qty", 0) > 0:
                    close_orders.append({
                        "symbol": symbol,
                        "qty": pos["qty"],
                        "reason": f"ai_attention_tax_ratio_{hc['cost_edge_ratio']:.2f}_grade_{hc['cost_efficiency_grade']}",
                    })

        # 7. Session drawdown circuit breaker
        # Fix P1-C1: actually set session_halted=True instead of only logging a warning.
        # check_order_allowed() already blocks orders when session_halted is set.
        # 修复 P1-C1：实际设置 session_halted=True，而非仅记录警告。
        # check_order_allowed() 已检查该标志并阻止新订单。
        peak = sess.get("peak_balance_usdt", sess.get("initial_paper_balance_usdt", 0))
        current = sess.get("current_paper_balance_usdt", 0)
        if peak > 0:
            drawdown_pct = ((peak - current) / peak) * 100
            if drawdown_pct >= self._config.max_session_drawdown_pct:
                if not sess.get("session_halted"):
                    sess["session_halted"] = True
                    sess["session_halt_reason"] = f"drawdown_{drawdown_pct:.1f}pct"
                    logger.warning(
                        "SESSION HALTED: drawdown %.1f%% >= %.1f%% limit / "
                        "会话已停止：回撤 %.1f%% 超过 %.1f%% 上限",
                        drawdown_pct, self._config.max_session_drawdown_pct,
                        drawdown_pct, self._config.max_session_drawdown_pct,
                    )
                    if self._change_audit_log:
                        try:
                            from .change_audit_log import ChangeType
                            self._change_audit_log.record_change(
                                change_type=ChangeType.STATE_CHANGE,
                                who="RiskManager",
                                what="Session halted due to drawdown circuit breaker",
                                reason=f"Drawdown {drawdown_pct:.1f}% exceeded limit {self._config.max_session_drawdown_pct:.1f}%",
                                new_value={"session_halted": True, "halt_reason": sess["session_halt_reason"]},
                                affected_components=["PaperTradingEngine", "RiskManager"],
                                auto_approve=True,
                            )
                        except Exception:
                            pass  # audit log failure is non-fatal

        # 8. Daily loss check / 日内亏损检查
        # Uses daily_start_balance (reset each calendar day), not session initial
        # 使用每日起始余额（每个自然日重置），而非 session 初始余额
        today_str = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        daily_start = sess.get("daily_start_balance_usdt", sess.get("initial_paper_balance_usdt", 0))
        stored_date = sess.get("daily_start_date", "")
        if stored_date != today_str:
            # New day — reset daily start balance (will be persisted by caller)
            sess["daily_start_balance_usdt"] = current
            sess["daily_start_date"] = today_str
            daily_start = current
        if daily_start > 0 and current < daily_start:
            daily_loss_pct = ((daily_start - current) / daily_start) * 100
            if daily_loss_pct >= self._config.max_daily_loss_pct:
                # T3.04: Close all positions and halt session as protective measure
                # 平掉所有仓位并熔断 session 作为保护措施
                for symbol, pos in list(positions.items()):
                    already_closing = any(co["symbol"] == symbol for co in close_orders)
                    if not already_closing and pos.get("qty", 0) > 0:
                        close_orders.append({
                            "symbol": symbol,
                            "qty": pos["qty"],
                            "reason": f"daily_loss_{daily_loss_pct:.1f}pct_exceeds_max_{self._config.max_daily_loss_pct:.1f}pct",
                        })
                # Halt session on daily loss exceeded
                sess["session_halted"] = True
                sess["session_halt_reason"] = f"daily_loss_{daily_loss_pct:.1f}pct"
                # T3.06: Record session halt in audit log
                if self._change_audit_log:
                    try:
                        from .change_audit_log import ChangeType
                        self._change_audit_log.record_change(
                            change_type=ChangeType.STATE_CHANGE,
                            who="system",
                            what="Session halted due to daily loss limit exceeded",
                            reason=f"Daily loss {daily_loss_pct:.1f}% exceeded limit {self._config.max_daily_loss_pct:.1f}%",
                            new_value={"session_halted": True, "halt_reason": sess["session_halt_reason"]},
                            affected_components=["PaperTradingEngine", "RiskManager"],
                            auto_approve=True,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record session halt in audit log: {e} (non-fatal)")

        return close_orders

    # ── Post-Fill Accounting / 成交后记账 ──

    def record_fill_result(self, pnl: float) -> None:
        """Track consecutive losses for cooldown."""
        if pnl < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self._config.consecutive_loss_cooldown_count:
                cooldown_ms = int(self._config.consecutive_loss_cooldown_minutes * 60 * 1000)
                self._cooldown_until_ts_ms = int(time.time() * 1000) + cooldown_ms
                logger.info(
                    "Consecutive losses %d → cooldown %d min",
                    self._consecutive_losses, self._config.consecutive_loss_cooldown_minutes,
                )
                # P1-16: Sync cooldown to H0Gate risk snapshot for deterministic pre-filter
                # P1-16：同步冷卻期到 H0Gate 風控快照以供確定性前置過濾
                if self._h0_gate is not None:
                    try:
                        from .h0_gate import H0GateRiskSnapshot  # noqa: PLC0415
                        _current_h0_snap = self._h0_gate._risk_snapshot
                        _h0_cooldown_snap = H0GateRiskSnapshot(
                            open_position_count=_current_h0_snap.open_position_count,
                            total_exposure_pct=_current_h0_snap.total_exposure_pct,
                            cooldown_until_ts_ms=self._cooldown_until_ts_ms,
                            kill_switch_active=_current_h0_snap.kill_switch_active,
                            snapshot_ts_ms=int(time.time() * 1000),
                        )
                        self._h0_gate.update_risk(_h0_cooldown_snap)
                        logger.info(
                            "H0Gate cooldown sync: cooldown_until_ts_ms=%d "
                            "/ H0 門控冷卻期已同步：%d",
                            self._cooldown_until_ts_ms,
                            self._cooldown_until_ts_ms,
                        )
                    except Exception as _h0_sync_err:
                        logger.warning(
                            "H0Gate cooldown sync failed (non-fatal): %s "
                            "/ H0 門控冷卻期同步失敗（不影響業務）：%s",
                            _h0_sync_err, _h0_sync_err,
                        )
        else:
            self._consecutive_losses = 0

    # ── Trailing Stop Management ──

    def clear_trailing_stop(self, symbol: str) -> None:
        self._trailing_stops.pop(symbol, None)
        self._spike_suppression_count.pop(symbol, None)

    # ── Cooldown Management ──

    def reset_cooldown(self) -> None:
        self._cooldown_until_ts_ms = 0
        self._consecutive_losses = 0

    def is_in_cooldown(self) -> bool:
        return self._cooldown_until_ts_ms > int(time.time() * 1000)

    # ── Risk Context for AI Decision / AI 决策用风控上下文 ──

    def get_risk_context_for_ai(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Provide risk context to L2 AI engine for informed decision-making.
        为 L2 AI 引擎提供风控上下文，使其能做出知情的决策。

        This bridges the gap between risk management and AI decision-making.
        The AI should factor this into its trading decisions.
        """
        sess = state.get("session", {})
        positions = state.get("positions", {})
        now_ms_val = int(time.time() * 1000)

        # Drawdown status
        peak = sess.get("peak_balance_usdt", sess.get("initial_paper_balance_usdt", 0))
        current = sess.get("current_paper_balance_usdt", 0)
        drawdown_pct = ((peak - current) / peak * 100) if peak > 0 else 0.0

        # Daily loss status
        daily_start = sess.get("daily_start_balance_usdt", sess.get("initial_paper_balance_usdt", 0))
        daily_loss_pct = ((daily_start - current) / daily_start * 100) if daily_start > 0 and current < daily_start else 0.0

        # Position cost efficiency summary
        worst_grade = "A"
        total_ai_cost = 0.0
        for pos in positions.values():
            hc = pos.get("holding_cost", {})
            grade = hc.get("cost_efficiency_grade", "A")
            if grade > worst_grade:
                worst_grade = grade
            total_ai_cost += hc.get("ai_cost_attributed_usd", 0.0)

        # Risk pressure: 0.0 (relaxed) to 1.0 (maximum pressure)
        # 风险压力指数：0.0（宽松）到 1.0（最大压力）
        pressure = 0.0
        pressure += min(drawdown_pct / self._config.max_session_drawdown_pct, 1.0) * 0.3
        pressure += min(daily_loss_pct / self._config.max_daily_loss_pct, 1.0) * 0.2
        pressure += min(self._consecutive_losses / max(self._config.consecutive_loss_cooldown_count, 1), 1.0) * 0.2
        pressure += (0.3 if self.is_in_cooldown() else 0.0)

        # Recommended position size reduction based on pressure
        # 基于压力的推荐仓位缩减
        recommended_size_multiplier = max(0.1, 1.0 - pressure)

        result = {
            "risk_pressure": round(pressure, 3),
            "recommended_size_multiplier": round(recommended_size_multiplier, 3),
            "drawdown_pct": round(drawdown_pct, 2),
            "drawdown_limit_pct": self._config.max_session_drawdown_pct,
            "daily_loss_pct": round(daily_loss_pct, 2),
            "daily_loss_limit_pct": self._config.max_daily_loss_pct,
            "consecutive_losses": self._consecutive_losses,
            "cooldown_active": self.is_in_cooldown(),
            "session_halted": sess.get("session_halted", False),
            "open_positions": len(positions),
            "worst_cost_grade": worst_grade,
            "total_ai_cost_usd": round(total_ai_cost, 4),
            "suggestion": (
                "reduce_activity" if pressure > 0.7
                else "caution" if pressure > 0.4
                else "normal"
            ),
        }

        # Feed risk metrics to Governance Hub / 将风控指标反馈给治理集線器
        if self._governance_hub:
            try:
                self._governance_hub.check_risk_and_act({
                    "risk_pressure": result["risk_pressure"],
                    "drawdown_pct": result["drawdown_pct"],
                    "daily_loss_pct": result["daily_loss_pct"],
                    "consecutive_losses": result["consecutive_losses"],
                    "session_halted": result["session_halted"],
                })
            except Exception:
                logger.warning("Governance check_risk_and_act failed (non-fatal) / 治理風控檢查失敗（非致命）")

        return result

    # ── Status / Serialization ──

    def get_status(self) -> dict[str, Any]:
        now_ms = int(time.time() * 1000)
        return {
            "consecutive_losses": self._consecutive_losses,
            "cooldown_active": self._cooldown_until_ts_ms > now_ms,
            "cooldown_until_ts_ms": self._cooldown_until_ts_ms,
            "trailing_stops": dict(self._trailing_stops),
            "is_simulated": True,
        }

    def get_full_config(self) -> dict[str, Any]:
        """Return all 3 tiers for API response."""
        return {
            "global_config": self._config.to_dict(),
            "category_configs": {k: v.to_dict() for k, v in self._category_configs.items()},
            "agent_params": self._agent_params.to_dict(),
        }

    def get_risk_state_for_persistence(self) -> dict[str, Any]:
        """JSON-serializable state for embedding in paper state."""
        return {
            "global_config": self._config.to_dict(),
            "category_configs": {k: v.to_dict() for k, v in self._category_configs.items()},
            "agent_params": self._agent_params.to_dict(),
            "trailing_stops": dict(self._trailing_stops),
            "consecutive_losses": self._consecutive_losses,
            "cooldown_until_ts_ms": self._cooldown_until_ts_ms,
            "last_updated_ts_ms": int(time.time() * 1000),
        }

    def load_risk_state(self, risk_state: dict[str, Any]) -> None:
        """Restore from persisted paper state with validation."""
        if not risk_state:
            return
        gc = risk_state.get("global_config")
        if gc:
            self._config = GlobalRiskConfig.from_dict(gc)
        cc = risk_state.get("category_configs", {})
        for cat, cd in cc.items():
            self._category_configs[cat] = CategoryRiskConfig.from_dict(cd)
        ap = risk_state.get("agent_params")
        if ap:
            self._agent_params = AgentRiskParams.from_dict(ap)
            # Validate ranges on restore / 恢复时验证范围
            self._agent_params.position_size_multiplier = max(0.1, min(self._agent_params.position_size_multiplier, 1.0))
            self._agent_params.effective_stop_loss_pct = max(0.1, min(self._agent_params.effective_stop_loss_pct, self._config.max_stop_loss_pct))
            self._agent_params.effective_take_profit_pct = max(0.1, min(self._agent_params.effective_take_profit_pct, self._config.max_take_profit_pct))
        self._trailing_stops = risk_state.get("trailing_stops", {})
        self._consecutive_losses = max(0, risk_state.get("consecutive_losses", 0))
        self._cooldown_until_ts_ms = max(0, risk_state.get("cooldown_until_ts_ms", 0))

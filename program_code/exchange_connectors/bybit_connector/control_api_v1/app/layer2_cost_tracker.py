from __future__ import annotations

"""
Layer 2 AI Reasoning Engine — Cost Tracker / 成本追踪器
成本追踪（Claude + Perplexity）+ 自适应预算 + 定价核实

MODULE_NOTE (中文):
  本模块负责 Layer 2 推理引擎的所有成本追踪与预算管理：
  - 每次 Claude API 调用的 token 用量与 USD 成本计入
  - 每次 Perplexity 搜索成本计入
  - 每日花费汇总 + 硬上限检查（$2/天，不可突破，DOC-08 §4）
  - 自适应预算：根据近 7 天 AI ROI 动态调整预算倍率
  - PnL 归因回填：session 推荐执行后追踪 paper PnL → 计算 ROI
  - 定价表管理：30 天核实提醒，支持手动更新
  - 状态持久化到 runtime/layer2_cost_state.json

MODULE_NOTE (English):
  Cost tracking and budget management for the Layer 2 reasoning engine:
  - Token usage & USD cost accounting for each Claude API call
  - Perplexity search cost accounting
  - Daily spend aggregation + hard cap enforcement ($2/day, absolute, per DOC-08 §4)
  - Adaptive budget: dynamic multiplier based on 7-day AI ROI
  - PnL attribution backfill: track paper PnL after session recommendation execution
  - Pricing table management: 30-day verification reminders, manual update support
  - State persisted to runtime/layer2_cost_state.json
"""

import datetime
import json
import logging
import os
import stat
import threading
import time
import warnings
from pathlib import Path
from typing import Any

from .layer2_types import (
    ADAPTIVE_MIN_DAYS,
    ADAPTIVE_TIERS,
    DEFAULT_ADAPTIVE_BASE_DAILY_USD,
    DEFAULT_DAILY_HARD_CAP_USD,
    AdaptiveBudgetState,
    Layer2Config,
    Layer2Session,
    PricingTable,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Cost State Store / 成本状态存储
# ═══════════════════════════════════════════════════════════════════════════════

def _default_cost_state() -> dict[str, Any]:
    """Default cost state structure / 默认成本状态结构"""
    return {
        "daily_spend": {},             # {"2026-03-27": {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0}}
        "sessions": [],                # List of session summaries (most recent first, max 500)
        "adaptive": {
            "multiplier": 1.0,
            "roi_7d": None,
            "ai_spend_7d_usd": 0.0,
            "paper_pnl_7d_usd": 0.0,
            "data_days": 0,
            "last_recalculated_ms": 0,
        },
        "pricing": PricingTable().to_dict(),
        "config": Layer2Config().to_dict(),
    }


class Layer2CostTracker:
    """
    Tracks all Layer 2 AI costs, enforces budgets, manages adaptive multiplier.
    追踪所有 Layer 2 AI 成本，执行预算限制，管理自适应倍率。
    """

    MAX_SESSION_HISTORY = 500

    def __init__(self, state_file: str | None = None):
        if state_file is None:
            state_file = os.getenv(
                "OPENCLAW_LAYER2_COST_FILE",
                os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "runtime", "layer2_cost_state.json")
                ),
            )
        self._file_path = Path(state_file)
        self._lock = threading.RLock()
        self._config = Layer2Config()
        self._pricing = PricingTable()
        self._adaptive = AdaptiveBudgetState()
        self._load()

    # ── Persistence / 持久化 ──

    def _load(self) -> None:
        """Load state from file or initialize defaults / 从文件加载状态或初始化默认值"""
        with self._lock:
            if self._file_path.exists():
                try:
                    with self._file_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._apply_state(data)
                    return
                except (json.JSONDecodeError, KeyError, TypeError):
                    logger.warning("layer2_cost_state.json corrupted, reinitializing")
            self._save()

    def _apply_state(self, data: dict[str, Any]) -> None:
        """Apply loaded state to in-memory objects / 将加载的状态应用到内存对象"""
        # Config
        cfg = data.get("config", {})
        for k, v in cfg.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)

        # Pricing
        pricing_data = data.get("pricing", {})
        models_data = pricing_data.get("models", {})
        for tier, mp in models_data.items():
            if tier in self._pricing.models:
                self._pricing.models[tier].input_per_mtok = mp.get("input_per_mtok", self._pricing.models[tier].input_per_mtok)
                self._pricing.models[tier].output_per_mtok = mp.get("output_per_mtok", self._pricing.models[tier].output_per_mtok)
                self._pricing.models[tier].last_verified_date = mp.get("last_verified_date", "")
        self._pricing.perplexity_per_search = pricing_data.get("perplexity_per_search", self._pricing.perplexity_per_search)
        self._pricing.perplexity_last_verified_date = pricing_data.get("perplexity_last_verified_date", "")

        # Adaptive
        adp = data.get("adaptive", {})
        self._adaptive.multiplier = adp.get("multiplier", 1.0)
        self._adaptive.roi_7d = adp.get("roi_7d")
        self._adaptive.ai_spend_7d_usd = adp.get("ai_spend_7d_usd", 0.0)
        self._adaptive.paper_pnl_7d_usd = adp.get("paper_pnl_7d_usd", 0.0)
        self._adaptive.data_days = adp.get("data_days", 0)
        self._adaptive.last_recalculated_ms = adp.get("last_recalculated_ms", 0)

    def _save(self) -> None:
        """Persist state to file with restricted permissions / 以受限权限持久化状态到文件"""
        with self._lock:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            state = self._read_raw()
            state["config"] = self._config.to_dict()
            state["pricing"] = self._pricing.to_dict()
            state["adaptive"] = self._adaptive.to_dict()
            with self._file_path.open("w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(self._file_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            except OSError:
                pass

    def _read_raw(self) -> dict[str, Any]:
        """Read raw state from file / 从文件读取原始状态"""
        if self._file_path.exists():
            try:
                with self._file_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, TypeError):
                pass
        return _default_cost_state()

    # ── Daily Spend / 每日花费 ──

    def _today_key(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def get_daily_spend(self, date_key: str | None = None) -> dict[str, Any]:
        """Get spend for a specific day / 获取某天的花费"""
        if date_key is None:
            date_key = self._today_key()
        raw = self._read_raw()
        return raw.get("daily_spend", {}).get(date_key, {
            "claude_usd": 0.0,
            "search_usd": 0.0,
            "total_usd": 0.0,
            "session_count": 0,
        })

    def get_today_total_usd(self) -> float:
        """Get today's total spend / 获取今天的总花费"""
        return self.get_daily_spend().get("total_usd", 0.0)

    def check_daily_budget(self) -> tuple[bool, float]:
        """
        Check if daily budget allows a new session.
        Returns (allowed, remaining_usd).
        Uses min(hard_cap, adaptive_effective_budget) when adaptive is enabled.
        检查每日预算是否允许新 session。自适应启用时使用有效预算和硬上限中的较小值。
        """
        today_total = self.get_today_total_usd()
        cap = self._config.daily_hard_cap_usd
        if self._config.adaptive_enabled and self._adaptive.effective_daily_budget_usd > 0:
            cap = min(cap, self._adaptive.effective_daily_budget_usd)
        remaining = round(cap - today_total, 4)
        return remaining > 0, max(0.0, remaining)

    def get_effective_session_budget(self, model_tier: str) -> float:
        """
        Get effective session budget considering adaptive multiplier.
        获取考虑自适应倍率后的有效 session 预算。
        """
        if model_tier == "opus":
            base = self._config.session_budget_opus_usd
        else:
            base = self._config.session_budget_sonnet_usd

        if self._config.adaptive_enabled:
            adjusted = round(base * self._adaptive.multiplier, 4)
        else:
            adjusted = base

        # Cannot exceed daily remaining
        _, remaining = self.check_daily_budget()
        return min(adjusted, remaining)

    # ── Record Costs / 记录成本 ──

    def record_claude_cost(self, session: Layer2Session, input_tokens: int, output_tokens: int, model_tier: str) -> float:
        """
        Record cost of a Claude API call. Returns USD cost.
        记录一次 Claude API 调用的成本。返回 USD 成本。
        """
        with self._lock:
            if model_tier not in self._pricing.models:
                logger.warning("Unknown model tier: %s, using sonnet pricing", model_tier)
                model_tier = "sonnet"
            cost = self._pricing.models[model_tier].cost_for_tokens(input_tokens, output_tokens)
            session.cost_usd = round(session.cost_usd + cost, 6)
            session.input_tokens += input_tokens
            session.output_tokens += output_tokens
            self._add_daily_claude_cost(cost)
            return cost

    def record_search_cost(self, session: Layer2Session, provider: str, cost_usd: float) -> None:
        """Record cost of a search query / 记录一次搜索查询的成本"""
        with self._lock:
            session.search_cost_usd = round(session.search_cost_usd + cost_usd, 6)
            self._add_daily_search_cost(cost_usd)

    def _add_daily_claude_cost(self, cost: float) -> None:
        raw = self._read_raw()
        key = self._today_key()
        daily = raw.setdefault("daily_spend", {})
        day = daily.setdefault(key, {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0})
        day["claude_usd"] = round(day["claude_usd"] + cost, 6)
        day["total_usd"] = round(day["claude_usd"] + day["search_usd"], 6)
        self._write_raw(raw)

    def _add_daily_search_cost(self, cost: float) -> None:
        raw = self._read_raw()
        key = self._today_key()
        daily = raw.setdefault("daily_spend", {})
        day = daily.setdefault(key, {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0})
        day["search_usd"] = round(day["search_usd"] + cost, 6)
        day["total_usd"] = round(day["claude_usd"] + day["search_usd"], 6)
        self._write_raw(raw)

    def _increment_daily_session_count(self) -> None:
        with self._lock:
            raw = self._read_raw()
            key = self._today_key()
            daily = raw.setdefault("daily_spend", {})
            day = daily.setdefault(key, {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0})
            day["session_count"] = day.get("session_count", 0) + 1
            self._write_raw(raw)

    def _write_raw(self, raw: dict[str, Any]) -> None:
        """Write raw state + update in-memory config/pricing/adaptive / 写入原始状态并更新内存"""
        with self._lock:
            raw["config"] = self._config.to_dict()
            raw["pricing"] = self._pricing.to_dict()
            raw["adaptive"] = self._adaptive.to_dict()
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            with self._file_path.open("w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(self._file_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass

    # ── Session Management / Session 管理 ──

    def record_session(self, session: Layer2Session) -> None:
        """Record a completed session summary / 记录已完成 session 的摘要"""
        with self._lock:
            self._increment_daily_session_count()
            raw = self._read_raw()
            sessions = raw.setdefault("sessions", [])
            sessions.insert(0, session.to_dict())
            # Trim to max history
            if len(sessions) > self.MAX_SESSION_HISTORY:
                raw["sessions"] = sessions[:self.MAX_SESSION_HISTORY]
            self._write_raw(raw)

    def get_sessions(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """Get session history / 获取 session 历史"""
        raw = self._read_raw()
        sessions = raw.get("sessions", [])
        return sessions[offset:offset + limit]

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        """Find a session by ID / 按 ID 查找 session"""
        raw = self._read_raw()
        for s in raw.get("sessions", []):
            if s.get("session_id") == session_id:
                return s
        return None

    # ── PnL Attribution / PnL 归因 ──

    def backfill_pnl_attribution(self, session_id: str, attribution: dict[str, Any]) -> bool:
        """
        Backfill PnL attribution for a completed session.
        为已完成 session 回填 PnL 归因。
        """
        with self._lock:
            raw = self._read_raw()
            for s in raw.get("sessions", []):
                if s.get("session_id") == session_id:
                    s["pnl_attribution"] = attribution
                    self._write_raw(raw)
                    return True
            return False

    # ── Adaptive Budget / 自适应预算 ──

    def recalculate_adaptive(self) -> AdaptiveBudgetState:
        """
        Recalculate adaptive budget multiplier based on 7-day AI ROI.
        根据近 7 天 AI ROI 重算自适应预算倍率。
        """
        with self._lock:
            raw = self._read_raw()
            daily_spend = raw.get("daily_spend", {})
            sessions = raw.get("sessions", [])

            today = datetime.date.today()
            seven_days_ago_dt = datetime.datetime.combine(today - datetime.timedelta(days=7), datetime.time(), tzinfo=datetime.timezone.utc)
            seven_days_ago_ms = int(seven_days_ago_dt.timestamp()) * 1000

            # Sum AI spend for last 7 days
            ai_spend_7d = 0.0
            data_days = 0
            for i in range(7):
                day_key = (today - datetime.timedelta(days=i)).isoformat()
                day_data = daily_spend.get(day_key, {})
                day_total = day_data.get("total_usd", 0.0)
                if day_total > 0:
                    data_days += 1
                ai_spend_7d += day_total

            # Sum paper PnL from sessions in last 7 days
            paper_pnl_7d = 0.0
            for s in sessions:
                created = s.get("created_at_ms", 0)
                if created < seven_days_ago_ms:
                    break  # sessions are sorted most-recent-first
                attr = s.get("pnl_attribution") or {}
                paper_pnl_7d += attr.get("realized_pnl_usd", 0.0)

            # Calculate ROI
            roi_7d: float | None = None
            multiplier = 1.0

            if data_days >= ADAPTIVE_MIN_DAYS and ai_spend_7d > 0:
                roi_7d = round(paper_pnl_7d / ai_spend_7d, 4)
                for threshold, mult in ADAPTIVE_TIERS:
                    if roi_7d >= threshold:
                        multiplier = mult
                        break

            # Clamp multiplier
            multiplier = max(self._config.adaptive_min_multiplier,
                             min(self._config.adaptive_max_multiplier, multiplier))

            effective = round(self._config.adaptive_base_daily_usd * multiplier, 2)
            # Never exceed hard cap
            effective = min(effective, self._config.daily_hard_cap_usd)

            self._adaptive = AdaptiveBudgetState(
                multiplier=multiplier,
                effective_daily_budget_usd=effective,
                roi_7d=roi_7d,
                ai_spend_7d_usd=round(ai_spend_7d, 4),
                paper_pnl_7d_usd=round(paper_pnl_7d, 4),
                data_days=data_days,
                last_recalculated_ms=int(time.time() * 1000),
            )
            self._save()
            return self._adaptive

    def get_adaptive_state(self) -> AdaptiveBudgetState:
        return self._adaptive

    # ── Pricing / 定价 ──

    def get_pricing(self) -> PricingTable:
        return self._pricing

    def update_pricing(self, updates: dict[str, Any]) -> PricingTable:
        """Update pricing table entries / 更新定价表条目"""
        with self._lock:
            models_update = updates.get("models", {})
            for tier, mp_update in models_update.items():
                if tier in self._pricing.models:
                    mp = self._pricing.models[tier]
                    if "input_per_mtok" in mp_update:
                        mp.input_per_mtok = mp_update["input_per_mtok"]
                    if "output_per_mtok" in mp_update:
                        mp.output_per_mtok = mp_update["output_per_mtok"]
                    if "last_verified_date" in mp_update:
                        mp.last_verified_date = mp_update["last_verified_date"]
            if "perplexity_per_search" in updates:
                self._pricing.perplexity_per_search = updates["perplexity_per_search"]
            if "perplexity_last_verified_date" in updates:
                self._pricing.perplexity_last_verified_date = updates["perplexity_last_verified_date"]
            self._save()
            return self._pricing

    # ── Config / 配置 ──

    def get_config(self) -> Layer2Config:
        return self._config

    def update_config(self, updates: dict[str, Any]) -> Layer2Config:
        """Update engine configuration / 更新引擎配置"""
        with self._lock:
            for k, v in updates.items():
                if hasattr(self._config, k):
                    setattr(self._config, k, v)
            self._save()
            return self._config

    # ── Cost Summary / 成本汇总 ──

    def get_cost_summary(self) -> dict[str, Any]:
        """
        Full cost summary for API response.
        完整成本汇总（用于 API 响应）。
        """
        raw = self._read_raw()
        today_key = self._today_key()
        today_data = raw.get("daily_spend", {}).get(today_key, {})
        allowed, remaining = self.check_daily_budget()

        # Total cumulative
        total_cumulative = 0.0
        total_sessions = 0
        for day_data in raw.get("daily_spend", {}).values():
            total_cumulative += day_data.get("total_usd", 0.0)
            total_sessions += day_data.get("session_count", 0)

        return {
            "today": {
                "date": today_key,
                "claude_usd": round(today_data.get("claude_usd", 0.0), 4),
                "search_usd": round(today_data.get("search_usd", 0.0), 4),
                "total_usd": round(today_data.get("total_usd", 0.0), 4),
                "session_count": today_data.get("session_count", 0),
            },
            "budget": {
                "daily_hard_cap_usd": self._config.daily_hard_cap_usd,
                "remaining_usd": remaining,
                "budget_ok": allowed,
            },
            "adaptive": self._adaptive.to_dict(),
            "cumulative": {
                "total_usd": round(total_cumulative, 4),
                "total_sessions": total_sessions,
            },
            "pricing_stale": self._pricing.is_stale(),
            # Principle 10 (cognitive honesty): all PnL-based metrics are paper simulation only
            # 根原則 10（認知誠實）：所有 PnL 相關指標均基於模擬，非真實盈虧
            "roi_basis": "paper_simulation_only",
            "roi_disclaimer": "基於模擬 PnL，非真實盈虧",
        }

    # ── Unified Call Recording / 統一調用記錄 ──

    def record_call(
        self,
        provider: str,
        model: str,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """
        Unified method to record any AI model call (Ollama, Claude, etc.).
        統一的 AI 模型調用記錄方法（Ollama、Claude 等均可使用）。

        This is the preferred entry point for all AI call tracking (principle 13).
        For Ollama calls, cost_usd is always 0.0 (local inference).
        For Claude calls, cost_usd should be the computed token cost.
        這是所有 AI 調用追蹤的首選入口（根原則 13）。
        Ollama 調用 cost_usd 始終為 0.0（本地推理）；
        Claude 調用應傳入計算後的 token 成本。

        Args:
            provider: AI provider name (e.g., "ollama", "claude", "perplexity")
                      AI 供應商名稱
            model: Model identifier (e.g., "l1_9b", "sonnet")
                   模型識別符
            duration_ms: Call duration in milliseconds / 調用耗時毫秒
            prompt_tokens: Number of prompt tokens used / 使用的 prompt token 數
            cost_usd: USD cost of the call (0.0 for local models) / 調用的 USD 成本
        """
        # Delegate to the internal Ollama tracking path for backward compatibility.
        # For non-Ollama providers, the same in-memory + persistent tracking applies.
        # 委派到內部 Ollama 追蹤路徑以保持向後兼容。
        # 非 Ollama 供應商同樣使用相同的記憶體 + 持久化追蹤。
        with self._lock:
            if not hasattr(self, "_ollama_stats"):
                self._ollama_stats: dict = {}
            key = f"{provider}/{model}"
            entry = self._ollama_stats.setdefault(
                key,
                {"call_count": 0, "total_duration_ms": 0.0, "total_prompt_tokens": 0, "total_cost_usd": 0.0},
            )
            entry["call_count"] += 1
            entry["total_duration_ms"] = round(entry["total_duration_ms"] + duration_ms, 2)
            entry["total_prompt_tokens"] += prompt_tokens
            entry["total_cost_usd"] = round(entry.get("total_cost_usd", 0.0) + cost_usd, 6)

        try:
            raw = self._read_raw()
            ollama_section = raw.setdefault("ollama_calls", {})
            model_entry = ollama_section.setdefault(
                key,
                {"call_count": 0, "total_duration_ms": 0.0},
            )
            model_entry["call_count"] = model_entry.get("call_count", 0) + 1
            model_entry["total_duration_ms"] = round(
                model_entry.get("total_duration_ms", 0.0) + duration_ms, 2
            )
            self._write_raw(raw)
        except Exception:
            # Persistence failure is non-fatal — in-memory stats still updated
            # 持久化失敗是非致命的 — 記憶體統計已更新
            logger.warning("record_call: failed to persist to state file, non-fatal")

    # ── Ollama Call Tracking (deprecated wrapper) / Ollama 調用追蹤（已棄用包裝） ──

    def record_ollama_call(
        self,
        model: str,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
    ) -> None:
        """
        DEPRECATED: Use record_call(provider="ollama", ...) instead.
        已棄用：請改用 record_call(provider="ollama", ...)。

        Record a local Ollama model call for cost and performance tracking.
        記錄本地 Ollama 模型調用，追蹤次數、延遲與 token 使用量。

        Ollama calls are free but tracked for ROI and resource awareness (principle 13).
        Ollama 調用免費，但仍追蹤以支持 AI 使用效果評估（根原則 13）。
        """
        warnings.warn(
            "record_ollama_call() is deprecated, use record_call(provider='ollama', ...) instead. "
            "record_ollama_call() 已棄用，請改用 record_call(provider='ollama', ...)。",
            DeprecationWarning,
            stacklevel=2,
        )
        self.record_call(
            provider="ollama",
            model=model,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            cost_usd=0.0,
        )

    def get_ollama_stats(self) -> dict:
        """
        Return in-memory Ollama call statistics per model.
        返回記憶體中每個模型的 Ollama 調用統計。

        Returns empty dict if no calls have been recorded this session.
        若本 session 未記錄任何調用，返回空字典。
        """
        with self._lock:
            if not hasattr(self, "_ollama_stats"):
                return {}
            # Strip "ollama/" prefix for backward compatibility with callers
            # expecting bare model names (e.g., "l1_9b" not "ollama/l1_9b").
            # 去除 "ollama/" 前綴，向後兼容調用者期望的裸模型名稱。
            result: dict = {}
            for key, val in self._ollama_stats.items():
                short_key = key.split("/", 1)[1] if "/" in key else key
                if key.startswith("ollama/") or "/" not in key:
                    result[short_key] = val
            return result

    def get_cost_edge_ratio(self) -> dict:
        """
        Calculate AI cost-to-edge ratio for the current session.
        計算當前 session 的 AI 成本效益比（cost_edge_ratio）。

        cost_edge_ratio = paper_pnl_7d_usd / ai_spend_7d_usd (when data is available).
        cost_edge_ratio = 7 日模擬 PnL / 7 日 AI 花費（數據充足時計算）。

        All values are based on paper simulation PnL — not real trading results.
        所有數值基於模擬 PnL，非真實交易結果。原則 10：認知誠實。

        Returns dict with roi_basis marker per principle 10 (cognitive honesty).
        返回含 roi_basis 標記的字典，符合根原則 10（認知誠實）要求。

        If insufficient data (< ADAPTIVE_MIN_DAYS), ratio is None.
        若數據不足（< ADAPTIVE_MIN_DAYS 天），比率返回 None。
        """
        state = self._adaptive
        ai_spend = state.ai_spend_7d_usd
        paper_pnl = state.paper_pnl_7d_usd
        data_days = state.data_days

        if data_days >= ADAPTIVE_MIN_DAYS and ai_spend > 0:
            ratio = round(paper_pnl / ai_spend, 4)
        else:
            ratio = None

        return {
            "cost_edge_ratio": ratio,
            "ai_spend_7d_usd": ai_spend,
            "paper_pnl_7d_usd": paper_pnl,
            "data_days": data_days,
            # Principle 10 (cognitive honesty): all ROI data is paper simulation only
            # 根原則 10（認知誠實）：所有 ROI 數據均基於模擬，非真實盈虧
            "roi_basis": "paper_simulation_only",
            "roi_disclaimer": "基於模擬 PnL，非真實盈虧",
        }

    # ── Budget Check for Session / Session 预算检查 ──

    def check_session_budget(self, session: Layer2Session) -> bool:
        """Check if session is still within budget / 检查 session 是否仍在预算内"""
        return session.total_cost() < session.session_budget_usd

    def check_daily_hard_cap(self) -> bool:
        """Check if daily hard cap is exceeded / 检查每日硬上限是否已超过"""
        allowed, _ = self.check_daily_budget()
        return allowed

    def reset_today_costs(self) -> dict[str, Any]:
        """
        Zero-out today's cost counters in the persistent state file.
        Returns the zeroed-out day record so callers can confirm what was cleared.
        将今日成本计数器归零（写入持久化文件）。返回归零后的记录供调用方确认。
        """
        with self._lock:
            raw = self._read_raw()
            key = self._today_key()
            zeroed = {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0}
            raw.setdefault("daily_spend", {})[key] = zeroed
            self._write_raw(raw)
            logger.info("Layer2CostTracker: today's costs reset to zero (date=%s)", key)
            return {"date": key, **zeroed}

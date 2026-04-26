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

# G3-08 Phase 3 Sub-task 3-1: H state cache invalidation hint channel.
# When ``OPENCLAW_H_STATE_GATEWAY != "1"`` (default) ``invalidate_async`` is
# a documented no-op (see h_state_invalidator.py MODULE_NOTE) — zero overhead
# for callers in the Phase 1/2 dormant deployment. Phase 3+ env=1 deploys
# upgrade this to a daemon-thread fire-and-forget IPC notification to Rust.
# G3-08 Phase 3 Sub-task 3-1：H 狀態快取失效提示通道。
# 當 ``OPENCLAW_H_STATE_GATEWAY != "1"``（預設）``invalidate_async`` 為
# 文件化的 no-op（見 h_state_invalidator.py MODULE_NOTE）—— Phase 1/2 dormant
# 部署下對 caller 零負擔。Phase 3+ env=1 部署時升級為 daemon thread
# fire-and-forget IPC 通知 Rust。
from .h_state_invalidator import invalidate_async as _invalidate_h_state_async

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
        # B14: Initialize _ollama_stats in __init__ instead of lazy hasattr check.
        # B14: 在 __init__ 中初始化 _ollama_stats，而非延迟的 hasattr 检查。
        self._ollama_stats: dict = {}
        self._ollama_stats_initialized: bool = False
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
        """Atomic persist: tmp-file-then-replace / 原子持久化：tmp→replace 防止損壞"""
        with self._lock:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            state = self._read_raw()
            state["config"] = self._config.to_dict()
            state["pricing"] = self._pricing.to_dict()
            state["adaptive"] = self._adaptive.to_dict()
            tmp_path = self._file_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            except OSError:
                pass
            tmp_path.replace(self._file_path)

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

    # ── G3-08 Phase 3: H state snapshot accessors / H 狀態 snapshot 存取器 ──
    # Sub-task 3-1 (commit 8cd257e): get_h2_snapshot (this section).
    # Sub-task 3-3 (this commit):    get_h5_snapshot (sibling, lower in this section).
    # Sub-task 3-1 (commit 8cd257e)：get_h2_snapshot（本區塊）。
    # Sub-task 3-3 (本 commit)：     get_h5_snapshot（同區塊下方姊妹）。

    def get_h2_snapshot(self) -> dict[str, Any]:
        """Return a thread-safe snapshot of H2 budget state for h_state_cache exposure.
        回傳 H2 預算閘狀態的線程安全 snapshot，供 h_state_cache 暴露使用。

        Schema (PA design §5.2 H2BudgetState parity, mirrors Rust struct
        ``rust/openclaw_engine/src/h_state_cache/types.rs:58-72``):
          - daily_remaining_usd: float — 當日剩餘預算 (USD)，反映 hard_cap
            與 adaptive effective budget 之較小者扣除已用後的可用額度
          - hard_cap_usd:        float — 當日硬上限 (USD)，治理常數，
            DOC-08 §4 規定不可突破
          - adaptive_multiplier: float — 自適應倍率（≤ 1.0 = 收縮 / > 1.0
            = 擴張）；由 7d ROI 推導，值 1.0 表中性

        Schema 對齊 PA design §5.2 H2BudgetState（鏡射 Rust struct
        ``rust/openclaw_engine/src/h_state_cache/types.rs:58-72``）：
          - daily_remaining_usd：當日剩餘預算 (USD)
          - hard_cap_usd：當日硬上限 (USD，治理常數)
          - adaptive_multiplier：自適應倍率（≤ 1.0 收縮 / > 1.0 擴張）

        Pure-read: NO side effects, NO state mutation, NO IPC. Acquires only
        the existing ``self._lock`` (RLock) shared with budget readers; no
        new lock introduced. Safe to call from any thread including the
        invalidator daemon thread (Phase 3 env=1 path).
        純讀取：無副作用、無狀態修改、無 IPC。僅取既有 ``self._lock``
        （與其他預算讀者共用的 RLock），不新增鎖。任何線程皆可呼叫，
        包含 invalidator daemon thread（Phase 3 env=1 路徑）。

        Returns:
            dict with 3 keys per H2BudgetState contract; all values are
            ``float``. ``check_daily_budget()`` already accounts for the
            ``adaptive_enabled`` toggle internally — when disabled the
            returned ``daily_remaining_usd`` reflects ``hard_cap_usd``
            minus today's spend (not the adaptive effective budget).
            含 3 個 key 的 dict（對齊 H2BudgetState contract），值皆為
            ``float``。``check_daily_budget()`` 已內部處理
            ``adaptive_enabled`` 開關 — 關閉時回傳的
            ``daily_remaining_usd`` 反映 ``hard_cap_usd`` 減今日花費
            （而非 adaptive effective budget）。
        """
        with self._lock:
            # ``check_daily_budget()`` returns ``(allowed: bool, remaining: float)``.
            # We surface only ``remaining`` here; the ``allowed`` boolean is
            # derivable downstream as ``remaining > 0`` and not part of
            # H2BudgetState wire schema (Rust mirror omits it for simplicity).
            # ``check_daily_budget()`` 回 ``(allowed, remaining)``。此處僅曝
            # ``remaining``；``allowed`` 下游可由 ``remaining > 0`` 推得，且
            # 非 H2BudgetState wire schema 一部分（Rust mirror 簡化未含）。
            _allowed, remaining = self.check_daily_budget()
            return {
                "daily_remaining_usd": float(remaining),
                "hard_cap_usd": float(self._config.daily_hard_cap_usd),
                "adaptive_multiplier": float(self._adaptive.multiplier),
            }

    def get_h5_snapshot(self) -> dict[str, Any]:
        """Return a thread-safe snapshot of H5 cost stats for h_state_cache exposure.
        回傳 H5 成本統計的線程安全 snapshot，供 h_state_cache 暴露使用。

        Schema (PA design §5.2 H5CostStats parity, mirrors Rust struct
        ``rust/openclaw_engine/src/h_state_cache/types.rs:167-178``, drops
        2 metadata keys for hot-path):
          - ai_spend_7d_usd:   float       — 7d AI 花費 (USD)
          - paper_pnl_7d_usd:  float       — 7d Paper 模擬 PnL (USD)
          - cost_edge_ratio:   Optional[float] — paper_pnl / ai_spend
            (None when data_days < ADAPTIVE_MIN_DAYS, 樣本不足)
          - data_days:         int         — 累積資料天數

        Schema 對齊 PA design §5.2 H5CostStats（鏡射 Rust struct
        ``rust/openclaw_engine/src/h_state_cache/types.rs:167-178``，丟棄
        2 個 metadata key 走 hot-path）：
          - ai_spend_7d_usd：7d AI 花費 (USD)
          - paper_pnl_7d_usd：7d Paper 模擬 PnL (USD)
          - cost_edge_ratio：paper_pnl / ai_spend（樣本不足回 None）
          - data_days：累積資料天數

        NOTE: ``get_cost_edge_ratio()`` returns 6 keys including
        ``roi_basis`` / ``roi_disclaimer`` metadata strings (principle 10
        cognitive honesty markers for the broader Cost Summary API).
        Rust ``H5CostStats`` only解 4 fields per PA design §5.2 (forward-
        compat — ``serde(default)`` lets Rust silently drop the 2 extra
        keys if a future schema variant ships them on the wire). Here we
        proactively filter at the Python boundary so the wire payload
        carries exactly the 4 fields Rust expects, matching the H2
        snapshot's "narrow projection" pattern (3 of N internal fields).
        註：``get_cost_edge_ratio()`` 回 6 個 key（含 ``roi_basis`` /
        ``roi_disclaimer`` metadata 字串，係更廣 Cost Summary API 的
        原則 10 認知誠實標記）。Rust ``H5CostStats`` 依 PA design §5.2
        只解 4 fields（forward-compat —— ``serde(default)`` 讓 Rust 在
        未來 schema 變種帶這 2 key 時靜默丟）。此處我們主動在 Python
        邊界過濾，wire payload 恰為 Rust 期望的 4 fields，對齊 H2
        snapshot 的「窄投影」模式（N 個內部 field 投影 3 個）。

        Pure-read: NO side effects, NO state mutation, NO IPC.
        ``get_cost_edge_ratio()`` itself reads ``self._adaptive`` (a value
        object, not lock-protected) — no lock acquired here because the
        upstream ``recalculate_adaptive()`` writer always replaces
        ``self._adaptive`` atomically under ``self._lock``, so any concurrent
        read sees either the old or new whole snapshot, never a torn one.
        Safe to call from any thread including the invalidator daemon
        thread (Phase 3 env=1 path).
        純讀取：無副作用、無狀態修改、無 IPC。``get_cost_edge_ratio()``
        本身讀 ``self._adaptive``（值物件，非鎖保護）—— 此處不取鎖因為
        上游 writer ``recalculate_adaptive()`` 始終在 ``self._lock`` 下
        原子性替換 ``self._adaptive``，任一並發讀只見到舊或新的完整
        snapshot，絕無 torn read。任何線程皆可呼叫，包含 invalidator
        daemon thread（Phase 3 env=1 路徑）。

        Returns:
            dict with 4 keys per H5CostStats contract. ``cost_edge_ratio``
            may be ``None`` when ``data_days < ADAPTIVE_MIN_DAYS`` (= 3,
            see layer2_types.py:75) — Rust ``Option<f64>`` accepts ``null``
            via serde JSON.
            含 4 個 key 的 dict（對齊 H5CostStats contract）。
            ``cost_edge_ratio`` 在 ``data_days < ADAPTIVE_MIN_DAYS``
            （= 3，見 layer2_types.py:75）時為 ``None``；Rust
            ``Option<f64>`` 透過 serde JSON 接受 ``null``。
        """
        # ``get_cost_edge_ratio()`` is itself pure-read on ``self._adaptive``;
        # we wrap it to project to the 4-field hot-path schema, dropping the
        # ``roi_basis`` / ``roi_disclaimer`` metadata markers (kept on the
        # broader Cost Summary API for principle 10 disclosure).
        # ``get_cost_edge_ratio()`` 本身對 ``self._adaptive`` 為純讀；
        # 此處包裹它投影到 4-field hot-path schema，丟棄 ``roi_basis`` /
        # ``roi_disclaimer`` 元資料標記（在更廣的 Cost Summary API 上保留，
        # 履行原則 10 揭露義務）。
        full = self.get_cost_edge_ratio()
        return {
            "ai_spend_7d_usd": float(full.get("ai_spend_7d_usd", 0.0)),
            "paper_pnl_7d_usd": float(full.get("paper_pnl_7d_usd", 0.0)),
            # ``cost_edge_ratio`` may be ``None`` (data_days < ADAPTIVE_MIN_DAYS).
            # Rust ``Option<f64>`` accepts ``null`` over JSON wire.
            # ``cost_edge_ratio`` 可能為 ``None``（樣本不足）；Rust
            # ``Option<f64>`` 接受 JSON wire 上的 ``null``。
            "cost_edge_ratio": full.get("cost_edge_ratio"),
            "data_days": int(full.get("data_days", 0)),
        }

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
        # FIX-57: Sync to Rust BudgetTracker (fire-and-forget, non-blocking).
        # FIX-57：同步到 Rust BudgetTracker（非阻塞，失敗不影響本地記錄）。
        self._sync_to_rust_budget(
            provider="anthropic", model=model_tier,
            tokens_in=input_tokens, tokens_out=output_tokens,
        )
        # G3-08 Phase 3 Sub-task 3-1: hint Rust h_state_cache that H2 state
        # changed. Daemon-thread fire-and-forget; never blocks hot-path.
        # env=0 → no-op (zero overhead). Even if hint drops, Rust poller
        # (10s default) eventually picks up the new snapshot.
        # G3-08 Phase 3 Sub-task 3-1：通知 Rust h_state_cache H2 狀態已變動。
        # daemon thread fire-and-forget；永不阻塞 hot-path。env=0 → no-op
        # （零負擔）。即使提示丟失，Rust poller（預設 10s）最終仍會撈到
        # 新 snapshot。
        _invalidate_h_state_async("h2.budget_consumed")
        # G3-08 Phase 3 Sub-task 3-3: H5 cost_logging hint — same tracker,
        # different lens. ``record_claude_cost`` mutates BOTH H2's budget
        # ledger AND H5's 7-day AI spend rollup; emit a second hint so the
        # Rust h_state_cache poller can refresh the H5 snapshot independently.
        # Both hints share the same daemon-thread fire-and-forget infra
        # (h_state_invalidator.invalidate_async), so the per-call cost is
        # ~2 ephemeral threads (env=1) or strict no-op (env=0). Per PA RFC
        # `2026-04-26--g3_08_phase3_subtask_split.md` §6 + §8.2 thread
        # safety analysis.
        # G3-08 Phase 3 Sub-task 3-3：H5 cost_logging 提示 —— 同一 tracker，
        # 不同視角。``record_claude_cost`` 同時改變 H2 預算帳本與 H5 7d
        # AI 花費彙總；發第二條提示讓 Rust h_state_cache poller 可獨立刷新
        # H5 snapshot。兩條提示共用同套 daemon-thread fire-and-forget 基礎
        # 設施（h_state_invalidator.invalidate_async），單次呼叫成本約
        # ~2 個短生命週期 thread（env=1）或嚴格 no-op（env=0）。詳 PA RFC
        # `2026-04-26--g3_08_phase3_subtask_split.md` §6 + §8.2 線程安全分析。
        _invalidate_h_state_async("h5.claude_cost_recorded")
        return cost

    def record_search_cost(self, session: Layer2Session, provider: str, cost_usd: float) -> None:
        """Record cost of a search query / 记录一次搜索查询的成本"""
        with self._lock:
            session.search_cost_usd = round(session.search_cost_usd + cost_usd, 6)
            self._add_daily_search_cost(cost_usd)
        # G3-08 Phase 3 Sub-task 3-3: H5 cost_logging hint — Perplexity /
        # search provider cost feeds the same 7-day AI spend rollup that H5
        # exposes. ``ai_spend_7d`` aggregator (recalculate_adaptive line
        # 471-479) sums ``daily_spend.<day>.total_usd`` which includes
        # ``search_usd`` — so search cost mutates H5's effective view too.
        # Hint reason ``h5.search_cost_recorded`` distinguishes from the
        # ``h5.claude_cost_recorded`` hint; both fire-and-forget, env=0
        # strict no-op. Sub-task 3-1 deliberately did NOT add this hook
        # (search cost does not directly mutate the H2 daily-remaining
        # ledger view — H2 reads ``check_daily_budget`` which uses
        # ``today_total`` that includes search but the per-call hint
        # bandwidth was scoped to Sub-task 3-1's H2 contract).
        # G3-08 Phase 3 Sub-task 3-3：H5 cost_logging 提示 —— Perplexity /
        # 搜尋供應商成本同樣灌入 H5 暴露的 7d AI 花費彙總。``ai_spend_7d``
        # 聚合器（recalculate_adaptive line 471-479）合計
        # ``daily_spend.<day>.total_usd`` 含 ``search_usd``，故搜尋成本
        # 也改變 H5 的有效視圖。提示 reason ``h5.search_cost_recorded``
        # 區別於 ``h5.claude_cost_recorded``；皆 fire-and-forget，env=0
        # 嚴格 no-op。Sub-task 3-1 刻意未加此 hook（搜尋成本不直接改變
        # H2 daily-remaining 帳本視圖 —— H2 讀 ``check_daily_budget`` 用
        # ``today_total``（含 search），但 H2 contract 的 per-call 提示
        # 頻寬已限縮在 Sub-task 3-1 範圍）。
        _invalidate_h_state_async("h5.search_cost_recorded")

    def _add_daily_claude_cost(self, cost: float) -> None:
        raw = self._read_raw()
        key = self._today_key()
        daily = raw.setdefault("daily_spend", {})
        day = daily.setdefault(key, {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0})
        day["claude_usd"] = round(day["claude_usd"] + cost, 6)
        day["total_usd"] = round(day["claude_usd"] + day["search_usd"], 6)
        self._write_raw(raw)

    def _sync_to_rust_budget(
        self, provider: str, model: str, tokens_in: int = 0, tokens_out: int = 0,
    ) -> None:
        """
        FIX-57: Fire-and-forget sync to Rust BudgetTracker via IPC.
        Non-blocking: runs in a background thread. Failure is non-fatal.
        FIX-57：透過 IPC 非阻塞同步到 Rust BudgetTracker。失敗不影響本地記錄。
        """
        import threading

        def _do_sync():
            try:
                import asyncio
                from .ipc_client import EngineIPCClient
                async def _call():
                    client = EngineIPCClient()
                    await client.connect()
                    try:
                        return await client.call("record_ai_usage", params={
                            "scope": "local_total",
                            "provider": provider,
                            "model": model,
                            "tokens_in": tokens_in,
                            "tokens_out": tokens_out,
                            "purpose": "layer2_sync",
                        }, timeout=3.0)
                    finally:
                        await client.disconnect()
                asyncio.run(_call())
            except Exception:
                # Non-fatal: Rust tracker may be unavailable (e.g., engine not running).
                # 非致命：Rust tracker 可能不可用（例如引擎未運行）。
                logger.debug("FIX-57: Rust budget sync failed (non-fatal)")

        threading.Thread(target=_do_sync, daemon=True).start()

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
        """Atomic write: tmp-file-then-replace to prevent corruption / 原子寫入：tmp→replace 防止損壞"""
        with self._lock:
            raw["config"] = self._config.to_dict()
            raw["pricing"] = self._pricing.to_dict()
            raw["adaptive"] = self._adaptive.to_dict()
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._file_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
            tmp_path.replace(self._file_path)

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
            key = f"{provider}/{model}"
            # B14: Log when first entry is populated (observability improvement).
            # B14: 首次填充时记录日志（可观察性改进）。
            if not self._ollama_stats_initialized and not self._ollama_stats:
                logger.debug("OllamaStats tracker initialized / OllamaStats 追踪器已初始化")
                self._ollama_stats_initialized = True
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

        B14: Returns a meaningful response even when empty (status + total_calls).
        B14: 即使无数据也返回有意义的响应（status + total_calls）。
        """
        with self._lock:
            if not self._ollama_stats:
                # B14: Return meaningful empty response instead of bare {}
                # B14: 返回有意义的空响应而非裸 {}
                return {"status": "no_data", "total_calls": 0}
            # Strip "ollama/" prefix for backward compatibility with callers
            # expecting bare model names (e.g., "l1_9b" not "ollama/l1_9b").
            # 去除 "ollama/" 前綴，向後兼容調用者期望的裸模型名稱。
            result: dict = {}
            total_calls = 0
            for key, val in self._ollama_stats.items():
                short_key = key.split("/", 1)[1] if "/" in key else key
                if key.startswith("ollama/") or "/" not in key:
                    result[short_key] = val
                    total_calls += val.get("call_count", 0)
            result["status"] = "active"
            result["total_calls"] = total_calls
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


# ═══════════════════════════════════════════════════════════════════════════════
# API Budget Manager — re-export for backward compatibility
# API 預算管理器 — 重導出以保持向後兼容
# Extracted to api_budget_manager.py / 已提取至 api_budget_manager.py
# ═══════════════════════════════════════════════════════════════════════════════
from .api_budget_manager import APIBudgetManager  # noqa: F401

from __future__ import annotations

"""
Layer 2 AI Reasoning Engine — Cost Recording Sibling / 成本記錄姊妹模組
G3-08 Phase 4 Method A 拆分（layer2_cost_tracker.py 930→~480 LOC）。

MODULE_NOTE (中文):
  本模組從 ``layer2_cost_tracker.py`` 抽出「成本寫入路徑」9 個方法，重構為
  module-level functions，第一參數統一為 ``tracker: 'Layer2CostTracker'``。
  原主檔以 1-line delegator 委派至此（per RFC §6.4 / §7.2）。

  涵蓋範圍：
  - record_claude_cost / record_search_cost：寫入單筆 AI 呼叫成本
  - _add_daily_claude_cost / _add_daily_search_cost：每日 USD 累計
  - _sync_to_rust_budget：fire-and-forget IPC 同步到 Rust BudgetTracker
  - _increment_daily_session_count：每日 session 計數
  - record_call / record_ollama_call：統一/已棄用呼叫追蹤入口
  - reset_today_costs：歸零今日計數器（operator 工具）

  H state 失效提示：
  - record_claude_cost 雙提示 ``h2.budget_consumed`` + ``h5.claude_cost_recorded``
  - record_search_cost 單提示 ``h5.search_cost_recorded``
  Sub-task 3-3 RFC §6 + §8.2 thread safety contract 不可破壞，emit order 保留。

MODULE_NOTE (English):
  This sibling extracts the "cost-write path" — 9 methods from
  ``layer2_cost_tracker.py`` — and rewrites them as module-level functions
  whose first argument is uniformly ``tracker: 'Layer2CostTracker'``. The
  original methods on ``Layer2CostTracker`` become 1-line delegators
  forwarding to these functions (per RFC §6.4 / §7.2).

  Scope:
  - record_claude_cost / record_search_cost: per-call AI cost ingest
  - _add_daily_claude_cost / _add_daily_search_cost: USD daily rollup
  - _sync_to_rust_budget: fire-and-forget IPC sync to Rust BudgetTracker
  - _increment_daily_session_count: daily session counter
  - record_call / record_ollama_call: unified / deprecated entry points
  - reset_today_costs: zero-out today (operator tool)

  H state invalidation hints:
  - record_claude_cost emits both ``h2.budget_consumed`` and
    ``h5.claude_cost_recorded`` (dual hint).
  - record_search_cost emits ``h5.search_cost_recorded`` (single).
  Sub-task 3-3 RFC §6 + §8.2 thread-safety contract preserved — emit order
  intact, daemon-thread fire-and-forget pattern unchanged.
"""

import logging
import warnings
from typing import TYPE_CHECKING

# G3-08 Phase 3 Sub-task 3-1: H state cache invalidation hint channel.
# Imported at module level so test patches at
# ``app.layer2_cost_recording._invalidate_h_state_async`` rebind correctly
# (per RFC §7.3 — patch path升級 from ``app.layer2_cost_tracker``).
# G3-08 Phase 3 Sub-task 3-1：H 狀態快取失效提示通道。
# 模組級 import，測試 patch path 升級到本模組
# (``app.layer2_cost_recording._invalidate_h_state_async``，per RFC §7.3)。
from .h_state_invalidator import invalidate_async as _invalidate_h_state_async
from .layer2_types import Layer2Session

if TYPE_CHECKING:
    from .layer2_cost_tracker import Layer2CostTracker

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Record Costs / 记录成本
# ═══════════════════════════════════════════════════════════════════════════════

def record_claude_cost(
    tracker: "Layer2CostTracker",
    session: Layer2Session,
    input_tokens: int,
    output_tokens: int,
    model_tier: str,
) -> float:
    """
    Record cost of a Claude API call. Returns USD cost.
    記錄一次 Claude API 調用的成本。返回 USD 成本。

    Side effects:
      1. Mutates session.cost_usd / input_tokens / output_tokens.
      2. Updates daily Claude rollup via _add_daily_claude_cost.
      3. Fires Rust BudgetTracker IPC sync (fire-and-forget).
      4. Emits dual H-state hints (H2 budget + H5 claude_cost) — see
         Sub-task 3-3 RFC §6 + §8.2 thread safety contract.

    副作用：
      1. 改變 session.cost_usd / input_tokens / output_tokens。
      2. 透過 _add_daily_claude_cost 更新每日 Claude 彙總。
      3. 發 Rust BudgetTracker IPC 同步（fire-and-forget）。
      4. 雙 H state 提示（H2 預算 + H5 claude_cost）—— 見
         Sub-task 3-3 RFC §6 + §8.2 線程安全 contract。
    """
    with tracker._lock:
        if str(model_tier or "").startswith("local:"):
            cost = 0.0
            session.input_tokens += input_tokens
            session.output_tokens += output_tokens
            _add_daily_claude_cost(tracker, cost)
            return cost
        if model_tier not in tracker._pricing.models:
            logger.warning("Unknown model tier: %s, using sonnet pricing", model_tier)
            model_tier = "sonnet"
        cost = tracker._pricing.models[model_tier].cost_for_tokens(input_tokens, output_tokens)
        session.cost_usd = round(session.cost_usd + cost, 6)
        session.input_tokens += input_tokens
        session.output_tokens += output_tokens
        _add_daily_claude_cost(tracker, cost)
    # FIX-57: Sync to Rust BudgetTracker (fire-and-forget, non-blocking).
    # FIX-57：同步到 Rust BudgetTracker（非阻塞，失敗不影響本地記錄）。
    _sync_to_rust_budget(
        tracker,
        provider="anthropic",
        model=model_tier,
        tokens_in=input_tokens,
        tokens_out=output_tokens,
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


def record_search_cost(
    tracker: "Layer2CostTracker",
    session: Layer2Session,
    provider: str,
    cost_usd: float,
) -> None:
    """Record cost of a search query / 記錄一次搜索查詢的成本"""
    with tracker._lock:
        session.search_cost_usd = round(session.search_cost_usd + cost_usd, 6)
        _add_daily_search_cost(tracker, cost_usd)
    # G3-08 Phase 3 Sub-task 3-3: H5 cost_logging hint — Perplexity /
    # search provider cost feeds the same 7-day AI spend rollup that H5
    # exposes. ``ai_spend_7d`` aggregator (recalculate_adaptive) sums
    # ``daily_spend.<day>.total_usd`` which includes ``search_usd`` —
    # so search cost mutates H5's effective view too.
    # Hint reason ``h5.search_cost_recorded`` distinguishes from the
    # ``h5.claude_cost_recorded`` hint; both fire-and-forget, env=0
    # strict no-op. Sub-task 3-1 deliberately did NOT add this hook
    # (search cost does not directly mutate the H2 daily-remaining
    # ledger view — H2 reads ``check_daily_budget`` which uses
    # ``today_total`` that includes search but the per-call hint
    # bandwidth was scoped to Sub-task 3-1's H2 contract).
    # G3-08 Phase 3 Sub-task 3-3：H5 cost_logging 提示 —— Perplexity /
    # 搜尋供應商成本同樣灌入 H5 暴露的 7d AI 花費彙總。``ai_spend_7d``
    # 聚合器（recalculate_adaptive）合計
    # ``daily_spend.<day>.total_usd`` 含 ``search_usd``，故搜尋成本
    # 也改變 H5 的有效視圖。提示 reason ``h5.search_cost_recorded``
    # 區別於 ``h5.claude_cost_recorded``；皆 fire-and-forget，env=0
    # 嚴格 no-op。Sub-task 3-1 刻意未加此 hook（搜尋成本不直接改變
    # H2 daily-remaining 帳本視圖 —— H2 讀 ``check_daily_budget`` 用
    # ``today_total``（含 search），但 H2 contract 的 per-call 提示
    # 頻寬已限縮在 Sub-task 3-1 範圍）。
    _invalidate_h_state_async("h5.search_cost_recorded")


def _add_daily_claude_cost(tracker: "Layer2CostTracker", cost: float) -> None:
    """Append cost to today's Claude USD rollup / 累計到今日 Claude USD 彙總"""
    raw = tracker._read_raw()
    key = tracker._today_key()
    daily = raw.setdefault("daily_spend", {})
    day = daily.setdefault(
        key, {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0},
    )
    day["claude_usd"] = round(day["claude_usd"] + cost, 6)
    day["total_usd"] = round(day["claude_usd"] + day["search_usd"], 6)
    tracker._write_raw(raw)


def _sync_to_rust_budget(
    tracker: "Layer2CostTracker",
    provider: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """
    FIX-57: Fire-and-forget sync to Rust BudgetTracker via IPC.
    Non-blocking: runs in a background thread. Failure is non-fatal.
    FIX-57：透過 IPC 非阻塞同步到 Rust BudgetTracker。失敗不影響本地記錄。

    SAFETY / 不變量：``threading`` + ``asyncio`` 仍走動態 import 保持與原
    Layer2CostTracker._sync_to_rust_budget hot-path 行為一致；daemon thread
    fire-and-forget pattern 不變（PA RFC §10 高風險警告 #1）。
    SAFETY: ``threading`` + ``asyncio`` retained as dynamic imports preserves
    the original ``Layer2CostTracker._sync_to_rust_budget`` hot-path
    behavior bit-for-bit; daemon-thread fire-and-forget pattern unchanged
    (PA RFC §10 high-risk warning #1).
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
                    return await client.call(
                        "record_ai_usage",
                        params={
                            "scope": "local_total",
                            "provider": provider,
                            "model": model,
                            "tokens_in": tokens_in,
                            "tokens_out": tokens_out,
                            "purpose": "layer2_sync",
                        },
                        timeout=3.0,
                    )
                finally:
                    await client.disconnect()

            asyncio.run(_call())
        except Exception:
            # Non-fatal: Rust tracker may be unavailable (e.g., engine not running).
            # 非致命：Rust tracker 可能不可用（例如引擎未運行）。
            logger.debug("FIX-57: Rust budget sync failed (non-fatal)")

    threading.Thread(target=_do_sync, daemon=True).start()


def _add_daily_search_cost(tracker: "Layer2CostTracker", cost: float) -> None:
    """Append cost to today's search USD rollup / 累計到今日 search USD 彙總"""
    raw = tracker._read_raw()
    key = tracker._today_key()
    daily = raw.setdefault("daily_spend", {})
    day = daily.setdefault(
        key, {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0},
    )
    day["search_usd"] = round(day["search_usd"] + cost, 6)
    day["total_usd"] = round(day["claude_usd"] + day["search_usd"], 6)
    tracker._write_raw(raw)


def _increment_daily_session_count(tracker: "Layer2CostTracker") -> None:
    """Increment today's session counter / 增加今日 session 計數"""
    with tracker._lock:
        raw = tracker._read_raw()
        key = tracker._today_key()
        daily = raw.setdefault("daily_spend", {})
        day = daily.setdefault(
            key, {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0},
        )
        day["session_count"] = day.get("session_count", 0) + 1
        tracker._write_raw(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# Unified Call Recording / 統一調用記錄
# ═══════════════════════════════════════════════════════════════════════════════

def record_call(
    tracker: "Layer2CostTracker",
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
        tracker: Layer2CostTracker instance / Layer2CostTracker 實例
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
    with tracker._lock:
        key = f"{provider}/{model}"
        # B14: Log when first entry is populated (observability improvement).
        # B14: 首次填充时记录日志（可观察性改进）。
        if not tracker._ollama_stats_initialized and not tracker._ollama_stats:
            logger.debug("OllamaStats tracker initialized / OllamaStats 追踪器已初始化")
            tracker._ollama_stats_initialized = True
        entry = tracker._ollama_stats.setdefault(
            key,
            {
                "call_count": 0,
                "total_duration_ms": 0.0,
                "total_prompt_tokens": 0,
                "total_cost_usd": 0.0,
            },
        )
        entry["call_count"] += 1
        entry["total_duration_ms"] = round(entry["total_duration_ms"] + duration_ms, 2)
        entry["total_prompt_tokens"] += prompt_tokens
        entry["total_cost_usd"] = round(entry.get("total_cost_usd", 0.0) + cost_usd, 6)

    try:
        raw = tracker._read_raw()
        ollama_section = raw.setdefault("ollama_calls", {})
        model_entry = ollama_section.setdefault(
            key,
            {"call_count": 0, "total_duration_ms": 0.0},
        )
        model_entry["call_count"] = model_entry.get("call_count", 0) + 1
        model_entry["total_duration_ms"] = round(
            model_entry.get("total_duration_ms", 0.0) + duration_ms, 2
        )
        tracker._write_raw(raw)
    except Exception:
        # Persistence failure is non-fatal — in-memory stats still updated
        # 持久化失敗是非致命的 — 記憶體統計已更新
        logger.warning("record_call: failed to persist to state file, non-fatal")


def record_ollama_call(
    tracker: "Layer2CostTracker",
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
    record_call(
        tracker,
        provider="ollama",
        model=model,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        cost_usd=0.0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Reset / 歸零
# ═══════════════════════════════════════════════════════════════════════════════

def reset_today_costs(tracker: "Layer2CostTracker") -> dict:
    """
    Zero-out today's cost counters in the persistent state file.
    Returns the zeroed-out day record so callers can confirm what was cleared.
    將今日成本計數器歸零（寫入持久化文件）。返回歸零後的記錄供調用方確認。
    """
    with tracker._lock:
        raw = tracker._read_raw()
        key = tracker._today_key()
        zeroed = {
            "claude_usd": 0.0,
            "search_usd": 0.0,
            "total_usd": 0.0,
            "session_count": 0,
        }
        raw.setdefault("daily_spend", {})[key] = zeroed
        tracker._write_raw(raw)
        logger.info(
            "Layer2CostTracker: today's costs reset to zero (date=%s)", key,
        )
        return {"date": key, **zeroed}

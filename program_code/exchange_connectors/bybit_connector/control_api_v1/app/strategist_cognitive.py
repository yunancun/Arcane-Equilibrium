"""
Batch 7 — StrategistAgent Cognitive / Fast Channel Sibling
============================================================
Governance refs: EX-06 §4 / CLAUDE.md §九 file-size discipline / G3-08 Phase 4

MODULE_NOTE (中文):
  本模組是 StrategistAgent 的 sibling，承載「V2 雙軌快速通道」與「認知調製器整合」
  相關的 4 個方法，從 strategist_agent.py 拆出以維持主檔在 §九 800 行警告線之下。
  函數一律接受 ``agent: StrategistAgent`` 作為第一個參數。

  涵蓋方法：
  1. handle_fast_channel — V2 緊急通道（reduce_all/close_all/flash_crash），
                           設置 _emergency_mode 阻斷正常通道
  2. clear_emergency_mode — 緊急模式清除，正常通道恢復
  3. set_cognitive_modulator — CognitiveModulator 注入（決策門檻調整來源）
  4. _apply_cognitive_modulation — 將 (confidence_floor, qty_ceiling) 套用到 confidence
  5. tick_cognitive_modulator — 週期性推進 modulator state（W1 FIX-B 既有）
  6. record_trade_outcome — LOSSES-WIRING consecutive_losses 計數器更新
                           （G3-08 Phase 4 P3 lift 自 strategist_agent.py）

MODULE_NOTE (English):
  StrategistAgent sibling carrying 4 methods around "V2 dual-track fast channel"
  and "CognitiveModulator integration". Extracted from strategist_agent.py so
  the main file stays under the §九 800-line warning threshold.
  Functions take ``agent: StrategistAgent`` as the first parameter.

  Covered methods:
  1. handle_fast_channel — V2 emergency channel (reduce_all/close_all/flash_crash),
                           sets _emergency_mode to block normal channel
  2. clear_emergency_mode — clear emergency mode, normal channel resumes
  3. set_cognitive_modulator — inject CognitiveModulator (decision-threshold source)
  4. _apply_cognitive_modulation — apply (confidence_floor, qty_ceiling) to confidence
  5. tick_cognitive_modulator — periodic modulator state advance (existing W1 FIX-B)
  6. record_trade_outcome — LOSSES-WIRING consecutive_losses counter update
                           (lifted from strategist_agent.py in G3-08 Phase 4 P3)

Hard boundaries (CLAUDE.md §四):
  - 緊急模式為 fail-closed 邊界（emergency mode is a fail-closed boundary）— 觸發後
    必須由 clear_emergency_mode 顯式關閉，避免 stale intent 在緊急時段流入。
  - 認知調製 ≠ 能力限制（cognitive modulation != capability restriction），詳 §二
    根原則 #11 衍生準則。Modulator 缺失時返回 (config.min_confidence, 1.0) 透傳。
  - 不變動業務邏輯，只搬位置 (no business-logic change, location-only refactor).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, List

from .multi_agent_framework import TradeIntent
from .strategist_fast_channel import build_emergency_intents

if TYPE_CHECKING:  # pragma: no cover — type-checker only / 僅型別檢查
    from .strategist_agent import StrategistAgent

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# V2 Dual-track Fast Channel / 雙軌快速通道
# ─────────────────────────────────────────────────────────────────────────────

def handle_fast_channel(
    agent: "StrategistAgent",
    trigger: str,
    symbols: list[str] | None = None,
) -> List[TradeIntent]:
    """
    V2 Fast channel: deterministic risk-driven actions (<10ms).
    V2 快速通道：確定性風控驅動的行動（<10ms）。

    Triggers: risk_governor >= DEFENSIVE -> reduce_all / close_all / flash_crash
    觸發條件：risk_governor >= DEFENSIVE -> 減倉/全平/閃崩保護

    Sets _emergency_mode flag to block normal channel, then generates pre-defined
    intents. Normal channel checks this flag before emitting.
    設置 _emergency_mode 標誌阻斷正常通道，然後生成預定義 intent。
    正常通道在發射前檢查此標誌。

    Args:
        trigger: Action type — "reduce_all" / "close_all" / "flash_crash"
        symbols: Specific symbols to act on (None = all)

    Returns:
        List of emergency TradeIntents
    """
    # Set emergency mode — blocks normal channel
    # 設置緊急模式 — 阻斷正常通道
    agent._emergency_mode.set()

    with agent._lock:
        # Clear normal channel queue (stale intents are dangerous during emergency)
        # 清空正常通道隊列（緊急時期過期 intent 是危險的）
        agent._normal_queue.clear()

        # Delegate intent construction to extracted module
        # 委託提取的模組構建 intent
        target_symbols = symbols or []
        emergency_intents = build_emergency_intents(
            trigger=trigger,
            symbols=target_symbols,
            TradeIntent=TradeIntent,
        )

        agent._pending_intents.extend(emergency_intents)
        agent._stats["intents_produced"] += len(emergency_intents)

        logger.warning(
            "Fast channel triggered: %s, %d intents generated / "
            "快速通道觸發：%s，生成 %d 個 intent",
            trigger, len(emergency_intents), trigger, len(emergency_intents),
        )

        return emergency_intents


def clear_emergency_mode(agent: "StrategistAgent") -> None:
    """
    V2: Clear emergency mode after fast channel actions are processed.
    V2：快速通道行動處理完畢後清除緊急模式。

    Normal channel resumes accepting signals after this call.
    此調用後正常通道恢復接收信號。
    """
    agent._emergency_mode.clear()
    logger.info("Emergency mode cleared, normal channel resumed / 緊急模式清除，正常通道恢復")


# ─────────────────────────────────────────────────────────────────────────────
# CognitiveModulator integration / 認知調製器整合
# ─────────────────────────────────────────────────────────────────────────────

def set_cognitive_modulator(agent: "StrategistAgent", modulator: Any) -> None:
    """
    V2: Inject CognitiveModulator for decision threshold adjustment.
    V2：注入 CognitiveModulator 用於決策門檻調整。

    Principle: cognitive modulation != capability restriction (see root principle derivative).
    原則：認知調製 != 能力限制（見根原則衍生準則）。
    """
    agent._cognitive_modulator = modulator
    logger.info(
        "CognitiveModulator injected into StrategistAgent / "
        "認知調製器已注入 StrategistAgent"
    )


def _apply_cognitive_modulation(
    agent: "StrategistAgent",
    confidence: float,
) -> tuple[float, float]:
    """
    V2: Apply CognitiveModulator thresholds to confidence and qty.
    V2：應用認知門檻調製到信心和倉位。

    Returns (adjusted_min_confidence, qty_ceiling_multiplier).
    返回 (調整後最低信心門檻, 倉位上限乘數)。

    If no modulator is injected, returns default config values (bypass).
    若未注入調製器，返回默認配置值（跳過）。
    """
    if agent._cognitive_modulator is None:
        return (agent.config.min_confidence, 1.0)

    try:
        # G8-01 W1 FIX-A：rename `get_current_params` → `get_all_params`
        # （前者並非 CognitiveModulator 公開 API，AttributeError 被下方 except 靜默吞掉
        # → conf_floor / qty_ceil 永遠回退 default，違反 feedback_no_dead_params。）
        # G8-01 W1 FIX-A: rename `get_current_params` → `get_all_params`
        # (former is NOT a CognitiveModulator public API; the AttributeError was
        # silently swallowed by the except below, returning defaults forever —
        # violates feedback_no_dead_params.)
        params = agent._cognitive_modulator.get_all_params()
        conf_floor = params.get("confidence_floor", agent.config.min_confidence)
        qty_ceil = params.get("qty_ceiling", 1.0)
        return (conf_floor, qty_ceil)
    except Exception as e:
        logger.warning(
            "CognitiveModulator error, using defaults: %s / "
            "認知調製器錯誤，使用默認值: %s", e, e,
        )
        return (agent.config.min_confidence, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# CognitiveModulator periodic tick / 認知調製器週期性 tick
# G8-01 W1 FIX-B (Option γ per PA RFC §3.1)
# ─────────────────────────────────────────────────────────────────────────────

def tick_cognitive_modulator(agent: "StrategistAgent") -> None:
    """
    Drive a single CognitiveModulator.update(...) cycle from current Strategist state.
    從當前 Strategist 狀態驅動一次 CognitiveModulator.update(...) 週期。

    Background / 背景:
      Pre-G8-01, ``CognitiveModulator.update(...)`` had **zero** production callers.
      The modulator stayed permanently at ctor base values (confidence_floor=0.60,
      qty_ceiling=1.0, update_count=0), turning the wired-but-dormant chain into
      dead code. PA RFC §3.1 picked Option γ: caller-side tick from
      ``StrategistAgent._handle_intel`` post-loop, every N intel events.
      G8-01 前 ``CognitiveModulator.update(...)`` production caller 數 = 0，modulator
      永遠卡在 ctor base value（confidence_floor=0.60 / qty_ceiling=1.0 /
      update_count=0），整鏈成為 dead code。PA RFC §3.1 採 Option γ：caller-side tick
      由 ``StrategistAgent._handle_intel`` loop 結尾每 N 個 intel 觸發。

    Inputs sourced from agent (best-effort, fail-soft) /
    輸入從 agent 抓取（盡力而為、fail-soft）:
      - ``consecutive_losses``：``agent._stats.get("consecutive_losses", 0)``
        — pre-G8-01 stat 不存在 → 0；FUP G8-01-FUP-LOSSES-WIRING 接 fill-result event。
        Pre-G8-01 the stat does not exist → 0; FUP wires fill-result event.
      - ``weekly_net_pnl``：``agent.cost_tracker.get_h5_snapshot().get("paper_net_pnl_7d", 0.0)``
        — cost_tracker 可為 None（test / fail-open）→ fallback 0.0。
        cost_tracker may be None (test / fail-open) → fallback 0.0.
      - ``regret_data`` / ``dream_data``：placeholder ``{}`` until OpportunityTracker /
        DreamEngine wired (out of G8-01 scope per PM 2026-04-26 reframe).

    Hard boundaries / 硬邊界 (CLAUDE.md §四):
      - Pure read-only on agent.cost_tracker; no IPC / no DB write.
        對 agent.cost_tracker 純唯讀；不發 IPC、不寫 DB。
      - Wrapped in broad try/except + logger.warning (fail-closed per principle #6) —
        modulator update is best-effort; failure must not poison handle_intel hot path.
        外層 try/except + warning 記錄（原則 #6 fail-closed）— modulator update 屬
        best-effort，失敗不可污染 handle_intel hot path。
      - No state mutation on the agent itself — only modulator internal EMA / counters
        advance, which are queried later via ``_apply_cognitive_modulation``.
        不變更 agent 本身狀態 — 僅 modulator 內部 EMA / counter 前進，稍後由
        ``_apply_cognitive_modulation`` 查詢使用。

    Args:
        agent: Live StrategistAgent instance (must have ``_cognitive_modulator`` /
               ``_stats`` / ``cost_tracker`` attrs; None ``_cognitive_modulator``
               makes this a fast no-op).
               活的 StrategistAgent instance（必有 ``_cognitive_modulator`` /
               ``_stats`` / ``cost_tracker`` 屬性；``_cognitive_modulator=None`` 則快速 no-op）。
    """
    modulator = getattr(agent, "_cognitive_modulator", None)
    if modulator is None:
        # No modulator wired — fast no-op (matches _apply_cognitive_modulation bypass).
        # 未注入 modulator — 快速 no-op（與 _apply_cognitive_modulation bypass 對稱）。
        return

    try:
        # consec_losses：StrategistAgent 內部統計，未來由 fill-result event 反饋接線。
        # consec_losses: StrategistAgent internal stat, future fill-result event wiring.
        try:
            consec_losses = int(agent._stats.get("consecutive_losses", 0))
        except Exception:
            consec_losses = 0

        # weekly_pnl：H5 SSOT 的 7d paper net PnL（cost_tracker 為 None 時 fallback 0.0）。
        # weekly_pnl: H5 SSOT 7d paper net PnL (fallback 0.0 when cost_tracker is None).
        weekly_pnl = 0.0
        cost_tracker = getattr(agent, "cost_tracker", None)
        if cost_tracker is not None:
            try:
                snapshot_fn = getattr(cost_tracker, "get_h5_snapshot", None)
                if snapshot_fn is not None:
                    snap = snapshot_fn() or {}
                    weekly_pnl = float(snap.get("paper_net_pnl_7d", 0.0))
            except Exception as snap_exc:
                logger.debug(
                    "cost_tracker.get_h5_snapshot failed in cognitive tick "
                    "(non-fatal): %s / cost_tracker.get_h5_snapshot 失敗（非致命）：%s",
                    snap_exc, snap_exc,
                )

        # Drive one EMA-smoothed update cycle. regret/dream remain placeholders until
        # OpportunityTracker / DreamEngine production wiring lands (out of G8-01 scope).
        # 驅動一個 EMA 平滑更新週期。regret/dream 維持 placeholder，待 OpportunityTracker /
        # DreamEngine production 接線（不在 G8-01 scope）。
        modulator.update(
            consecutive_losses=consec_losses,
            weekly_net_pnl=weekly_pnl,
            regret_data={},
            dream_data={},
        )
    except Exception as exc:
        # Fail-closed (principle #6): modulator failure must not poison hot path.
        # Fail-closed（原則 #6）：modulator 失敗不可污染 hot path。
        logger.warning(
            "tick_cognitive_modulator failed (non-fatal): %s / "
            "認知調製 tick 失敗（非致命）：%s",
            exc, exc,
        )


# ─────────────────────────────────────────────────────────────────────────────
# LOSSES-WIRING trade outcome ingress / 交易結果計數入口
# G8-01-FUP-LOSSES-WIRING (Wave A `aced662`) — counter feeding tick_cognitive_modulator
# G3-08 Phase 4 P3 (2026-04-28) — lift body from strategist_agent.py to keep main
# file under §九 800-line warning. Pure location refactor; behavior bit-identical.
# G3-08 Phase 4 P3（2026-04-28）— 從 strategist_agent.py 移出以維持主檔 §九 800 行
# 警告線之下。純位置重構，行為位元級一致。
# ─────────────────────────────────────────────────────────────────────────────

def record_trade_outcome(agent: "StrategistAgent", net_pnl: float) -> None:
    """
    Update ``agent._stats["consecutive_losses"]`` from a single round-trip outcome.
    以單筆交易結果更新 ``agent._stats["consecutive_losses"]``。

    Semantics / 語意：
      - net_pnl >  0  → win  → reset ``consecutive_losses`` to 0
                        勝 → 歸零
      - net_pnl <= 0  → loss / breakeven → increment by 1
                        輸 / 平手 → +1

    Breakeven (net_pnl == 0) treated as loss — fee-eaten trades drained capital
    without edge, which is what CognitiveModulator should react to (Principle #5
    survival > profit; #13 cost-edge awareness).

    平手 (net_pnl == 0) 視為輸 —— 被 fee 吃掉的交易雖無虧損但耗資本未產生 edge，
    正是 CognitiveModulator 該調製的場景（原則 #5 生存 > 利潤、#13 成本-edge 感知）。

    Thread-safe: takes ``agent._lock`` for the read-modify-write on _stats.
    Idempotent on the same outcome only if caller dedupes upstream — this method
    intentionally has NO trade_id memory; it's a pure counter ingress.

    線程安全：對 _stats 的 read-modify-write 取 ``agent._lock``。同一筆 outcome 的
    冪等性由上游 caller 負責去重 —— 本方法刻意不記憶 trade_id，純計數入口。

    Args:
        agent:  Live StrategistAgent instance.
        net_pnl: Post-fee PnL of the round-trip (USD or instrument quote unit).
                 Round-trip 扣費後 PnL（USD 或合約計價單位）。
    """
    try:
        with agent._lock:
            agent._stats["trade_outcomes_observed"] = (
                agent._stats.get("trade_outcomes_observed", 0) + 1
            )
            if net_pnl > 0:
                agent._stats["consecutive_losses"] = 0
            else:
                agent._stats["consecutive_losses"] = (
                    agent._stats.get("consecutive_losses", 0) + 1
                )
    except Exception as exc:
        # Fail-open: stat tracking failure must NOT propagate up the
        # Analyst→Strategist callback chain (Analyst already wraps us in
        # try/except, but defense-in-depth — never let a stats dict bug
        # disrupt trade analysis).
        # Fail-open：統計失敗絕不向 Analyst→Strategist callback chain 傳播
        # （Analyst 已包 try/except，此處 defense-in-depth —— 不讓統計 dict
        # bug 干擾交易分析）。
        logger.warning(
            "record_trade_outcome failed (non-fatal): %s / "
            "record_trade_outcome 失敗（非致命）：%s",
            exc, exc,
        )

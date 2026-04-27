from __future__ import annotations

"""
Layer 2 AI Reasoning Engine — H State Snapshots Sibling / H 狀態 snapshot 姊妹模組
G3-08 Phase 4 Method A 拆分（layer2_cost_tracker.py 930→~480 LOC）。

MODULE_NOTE (中文):
  本模組從 ``layer2_cost_tracker.py`` 抽出「H state snapshot 投影」2 個方法，
  重構為 module-level functions，第一參數 ``tracker: 'Layer2CostTracker'``。
  原主檔以 1-line delegator 委派至此（per RFC §6.4 / §7.2）。

  涵蓋範圍：
  - get_h2_snapshot：H2 預算閘狀態 wire-shape 投影（Sub-task 3-1）
  - get_h5_snapshot：H5 成本統計 wire-shape 投影（Sub-task 3-3）

  兩函式皆為純讀取（無副作用、無狀態修改、無 IPC），對應 Rust struct
  ``rust/openclaw_engine/src/h_state_cache/types.rs:58-72`` (H2)
  與 ``types.rs:167-178`` (H5)，由 h_state_query_handler 經 IPC 拉取。

MODULE_NOTE (English):
  This sibling extracts the "H state snapshot projection" path —
  2 methods from ``layer2_cost_tracker.py`` — and rewrites them as
  module-level functions whose first argument is uniformly
  ``tracker: 'Layer2CostTracker'``. Original methods become 1-line
  delegators forwarding to these functions (per RFC §6.4 / §7.2).

  Scope:
  - get_h2_snapshot: H2 budget gate wire-shape projection (Sub-task 3-1)
  - get_h5_snapshot: H5 cost stats wire-shape projection (Sub-task 3-3)

  Both functions are pure-read (no side effects, no state mutation,
  no IPC); they mirror Rust struct
  ``rust/openclaw_engine/src/h_state_cache/types.rs:58-72`` (H2) and
  ``types.rs:167-178`` (H5), and are pulled by h_state_query_handler
  over IPC.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .layer2_cost_tracker import Layer2CostTracker


# ═══════════════════════════════════════════════════════════════════════════════
# H State Snapshots / H 狀態快照
# ═══════════════════════════════════════════════════════════════════════════════
# G3-08 Phase 3:
# - Sub-task 3-1 (commit 8cd257e): get_h2_snapshot.
# - Sub-task 3-3:                  get_h5_snapshot.
# G3-08 Phase 3：
# - Sub-task 3-1 (commit 8cd257e)：get_h2_snapshot。
# - Sub-task 3-3：                  get_h5_snapshot。

def get_h2_snapshot(tracker: "Layer2CostTracker") -> dict[str, Any]:
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
    the existing ``tracker._lock`` (RLock) shared with budget readers; no
    new lock introduced. Safe to call from any thread including the
    invalidator daemon thread (Phase 3 env=1 path).
    純讀取：無副作用、無狀態修改、無 IPC。僅取既有 ``tracker._lock``
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
    with tracker._lock:
        # ``check_daily_budget()`` returns ``(allowed: bool, remaining: float)``.
        # We surface only ``remaining`` here; the ``allowed`` boolean is
        # derivable downstream as ``remaining > 0`` and not part of
        # H2BudgetState wire schema (Rust mirror omits it for simplicity).
        # ``check_daily_budget()`` 回 ``(allowed, remaining)``。此處僅曝
        # ``remaining``；``allowed`` 下游可由 ``remaining > 0`` 推得，且
        # 非 H2BudgetState wire schema 一部分（Rust mirror 簡化未含）。
        _allowed, remaining = tracker.check_daily_budget()
        return {
            "daily_remaining_usd": float(remaining),
            "hard_cap_usd": float(tracker._config.daily_hard_cap_usd),
            "adaptive_multiplier": float(tracker._adaptive.multiplier),
        }


def get_h5_snapshot(tracker: "Layer2CostTracker") -> dict[str, Any]:
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
    ``get_cost_edge_ratio()`` itself reads ``tracker._adaptive`` (a value
    object, not lock-protected) — no lock acquired here because the
    upstream ``recalculate_adaptive()`` writer always replaces
    ``tracker._adaptive`` atomically under ``tracker._lock``, so any
    concurrent read sees either the old or new whole snapshot, never a
    torn one. Safe to call from any thread including the invalidator
    daemon thread (Phase 3 env=1 path).
    純讀取：無副作用、無狀態修改、無 IPC。``get_cost_edge_ratio()``
    本身讀 ``tracker._adaptive``（值物件，非鎖保護）—— 此處不取鎖因為
    上游 writer ``recalculate_adaptive()`` 始終在 ``tracker._lock`` 下
    原子性替換 ``tracker._adaptive``，任一並發讀只見到舊或新的完整
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
    # ``get_cost_edge_ratio()`` is itself pure-read on ``tracker._adaptive``;
    # we wrap it to project to the 4-field hot-path schema, dropping the
    # ``roi_basis`` / ``roi_disclaimer`` metadata markers (kept on the
    # broader Cost Summary API for principle 10 disclosure).
    # ``get_cost_edge_ratio()`` 本身對 ``tracker._adaptive`` 為純讀；
    # 此處包裹它投影到 4-field hot-path schema，丟棄 ``roi_basis`` /
    # ``roi_disclaimer`` 元資料標記（在更廣的 Cost Summary API 上保留，
    # 履行原則 10 揭露義務）。
    full = tracker.get_cost_edge_ratio()
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

from __future__ import annotations

"""
Strategy Wiring -- H State Invalidator (G3-08 Phase 1C)
(Split from strategy_wiring.py per STRATEGY-WIRING-SPLIT P2, 2026-04-28)

MODULE_NOTE (中文):
  從 strategy_wiring.py 抽出的「H 狀態橋接器失效通知」接線。Phase 1C plumbing-only：
  根據 OPENCLAW_H_STATE_GATEWAY env 條件 spawn process-global singleton，否則
  維持 None、invalidate_async() 為 no-op、零負擔。

  此檔在 import 時即執行頂層接線，由 strategy_wiring.py 在原 init 順序的位置
  以 ``from .strategy_wiring_h_state import _H_STATE_INVALIDATOR`` 拉回 module
  attribute（保 sys.modules["app.strategy_wiring"] 屬性表 grep 穩定）。

  資料流（鏡 G3-03 ExecutorConfigCache 但相反）：Python 推送 fire-and-forget
  失效提示 → Rust h_state_cache poller 立即 ad-hoc poll；漏一次提示最多 ≤10s
  過時，不破壞正確性（Rust 端 10s 排程 poll 永遠仍生效）。

MODULE_NOTE (English):
  H State invalidator wiring extracted from strategy_wiring.py per
  STRATEGY-WIRING-SPLIT P2 (2026-04-28). Phase 1C plumbing-only: env-gated
  ``OPENCLAW_H_STATE_GATEWAY=="1"`` spawn; otherwise singleton stays None,
  ``invalidate_async()`` is no-op, zero overhead.

  Top-level executable on import; ``strategy_wiring.py`` re-imports
  ``_H_STATE_INVALIDATOR`` at the original init-sequence position so that
  ``app.strategy_wiring._H_STATE_INVALIDATOR`` attribute lookup remains stable
  for sys.modules-based introspection.

  Data flow (mirrors G3-03 ExecutorConfigCache but reversed): Python pushes
  fire-and-forget invalidation hints → Rust h_state_cache poller does an
  immediate ad-hoc poll; missing a hint costs ≤10s of staleness only (Rust
  10s scheduled poll always still runs).

安全不变量 / Safety invariants:
  - DEFAULT-OFF: env != "1" → singleton stays None; zero IPC traffic
  - Fail-closed: ImportError or unexpected raise → no invalidator + no crash;
    Rust 10s scheduled poll still works → observability degrades by ≤10s,
    not catastrophically (CLAUDE.md §二 原則 #6 失敗默認收縮)
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── G3-08 Phase 1C: H State Gateway invalidator (DEFAULT-OFF, env-gated) ──
# G3-08 Phase 1C: H 狀態橋接器失效通知（DEFAULT-OFF，env 閘控）
#
# Mirrors the G3-03 ExecutorConfigCache wiring pattern but flips the data
# flow: instead of Python pulling Rust config, Python pushes fire-and-forget
# invalidation hints to nudge the Rust ``h_state_cache`` poller (Phase 1A,
# commit ``aa287c4``) into an immediate ad-hoc poll after H1-H5 / 5-Agent
# state changes. Phase 1 is plumbing-only — H1-H5 / 5-Agent producers stay
# silent; Phase 2-4 wire ``invalidate_async`` call sites.
#
# Spawn condition: strict ``OPENCLAW_H_STATE_GATEWAY == "1"`` (per PA design
# §4.5 + §8.1). Anything else → singleton stays None, ``invalidate_async()``
# is no-op, zero overhead. The reverse IPC route ``query_h_state_full`` is
# already registered unconditionally in ``ai_service_dispatch.py``
# (Sub-task B), so disabling the gateway only stops the push channel — the
# pull channel is always reachable, returning the empty Phase 1 stub shape.
#
# 鏡射 G3-03 ExecutorConfigCache 接線模式但資料流相反：Python 不再拉 Rust
# config，而是推送 fire-and-forget 失效提示，觸發 Rust ``h_state_cache``
# poller（Phase 1A，commit ``aa287c4``）在 H1-H5 / 5-Agent 狀態變化後
# 立即執行 ad-hoc poll。Phase 1 純線路 —— H1-H5 / 5-Agent producer 保持靜默；
# Phase 2-4 才接 ``invalidate_async`` 呼叫點。
#
# Spawn 條件：嚴格 ``OPENCLAW_H_STATE_GATEWAY == "1"``（PA design §4.5 + §8.1）。
# 非 "1" 則 singleton 維持 None、``invalidate_async()`` 為 no-op、零負擔。
# Reverse IPC route ``query_h_state_full`` 在 Sub-task B 已於
# ``ai_service_dispatch.py`` 無條件註冊，因此關閉 gateway 只切斷 push 通道 ——
# pull 通道永遠可達，回 Phase 1 stub 空殼。
_H_STATE_INVALIDATOR: Optional[Any] = None
try:
    from .h_state_invalidator import (
        init_h_state_invalidator,
        is_gateway_enabled as _h_state_gateway_enabled,
    )

    if _h_state_gateway_enabled():
        # Constructs the process-global singleton (idempotent). Subsequent
        # ``invalidate_async(reason)`` calls (Phase 2-4) become live IPC
        # notifications. Failure here is non-fatal: ``init_h_state_invalidator``
        # already swallows env-gate misconfig; only an unexpected internal
        # raise (e.g. resource exhaustion at module import) would land us in
        # the except block.
        # 建構進程全域 singleton（冪等）。日後 Phase 2-4 的
        # ``invalidate_async(reason)`` 呼叫變為實際 IPC 通知。本 try 塊失敗
        # 為非致命：init_h_state_invalidator 內部已吞 env-gate 誤設；只有
        # 模組匯入期極端資源耗盡才會落入 except。
        _H_STATE_INVALIDATOR = init_h_state_invalidator()
        if _H_STATE_INVALIDATOR is not None:
            logger.info(
                "G3-08 Phase 1C: HStateInvalidator initialised "
                "(env=OPENCLAW_H_STATE_GATEWAY=1) / "
                "G3-08 Phase 1C：HStateInvalidator 已初始化"
            )
        else:
            # Race: env flipped between is_gateway_enabled() and init call.
            # Treat as disabled; no log spam.
            # 競態：is_gateway_enabled() 與 init 之間 env 翻轉，視同關閉。
            logger.debug(
                "G3-08 Phase 1C: env flipped during init; HStateInvalidator "
                "left unset (no-op) / env 在 init 期間翻轉，singleton 未設"
            )
    else:
        # DEFAULT-OFF path — singleton intentionally stays None. Skip the
        # info log to avoid every uvicorn worker spamming startup output.
        # DEFAULT-OFF 路徑 — singleton 故意維持 None；避免每個 uvicorn
        # worker 啟動都 spam log。
        _H_STATE_INVALIDATOR = None
except (ImportError, Exception) as _h_state_exc:  # noqa: BLE001 — non-fatal
    # Fail-closed: ImportError or unexpected raise → no invalidator + no
    # crash. Strategy-wiring continues; the only consequence is Phase 2-4
    # state changes won't trigger ad-hoc polls (Rust 10s scheduled poll
    # still works, so observability degrades by ≤10s, not catastrophically).
    # Fail-closed：ImportError 或非預期例外 → 無 invalidator 且不崩潰。
    # strategy_wiring 繼續；唯一後果是 Phase 2-4 的狀態變化不觸發 ad-hoc
    # poll（Rust 10s 排程 poll 仍生效，可觀察性最多劣化 ≤10s 非災難性）。
    _H_STATE_INVALIDATOR = None
    logger.warning(
        "G3-08 Phase 1C: HStateInvalidator init failed (non-fatal, "
        "scheduled poll still works): %s / 初始化失敗（非致命，"
        "排程 poll 仍生效）：%s",
        _h_state_exc, _h_state_exc,
    )


__all__ = ["_H_STATE_INVALIDATOR"]

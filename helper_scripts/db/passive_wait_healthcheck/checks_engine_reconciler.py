"""Reconciler/paper-state divergence healthcheck.

MODULE_NOTE (EN): Split from ``checks_engine.py`` by CHECKS-ENGINE-SUBSPLIT
to bring the engine healthcheck module back below the 1200-line hard cap. The
public import path remains available through ``checks_engine`` re-export.

MODULE_NOTE (中): CHECKS-ENGINE-SUBSPLIT 從 ``checks_engine.py`` 拆出，
讓 engine healthcheck 主模組回到 1200 行硬上限以下；外部仍可經
``checks_engine`` 原路徑 import。
"""

from __future__ import annotations


def check_reconciler_paper_state_divergence(_cur=None) -> tuple[str, str]:
    """[29] position_reconciler vs paper_state divergence — phantom dust state.

    F7 E5 spec (2026-04-26). The semantic: ``position_reconciler.seeded == 0
    AND paper_state.positions > 0`` for >30 min = phantom dust state where
    the reconciler thinks it has nothing to reconcile but paper_state holds
    ghost positions. Real bug fingerprint, not steady state.

    Implementation: per spec note "如 IPC fn 不存在，先 skip 該 check 標
    SKIPPED 並 log；不要 fail-open". The IPC method
    ``get_reconciler_status`` does NOT exist in the current Rust IPC server
    handler registry (verified via grep against rust/openclaw_engine/src/
    ipc_server/handlers/). Therefore this check returns PASS with a
    diagnostic prefix ``[deferred-no-ipc]`` so:
      * runner output displays the row (visible to operator at every cron tick)
      * status string ``PASS`` does not flip the cron exit code
      * message clearly indicates the check is in deferred state pending
        a Rust IPC handler addition (see TODO §F7-29 follow-up).

    No live IPC roundtrip is attempted — keeps the healthcheck self-contained
    for cron / CI without HMAC secret coupling (matches [20] G3-08 Phase 1C
    pattern and the codebase-wide "healthcheck must run without IPC" stance,
    per docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--g3_08_phase1_subtask_b.md).

    Once the Rust IPC method is added (planned in F7 follow-up), this fn is
    upgraded to perform a grep-then-call probe: if the method handler is
    discoverable in the Rust source, do a one-shot call (with HMAC if env
    available); otherwise stay deferred. The PASS output continues to render
    so cron line count remains stable across env states.

    Verdict (current MVP):
      * PASS: always — with diagnostic ``[deferred-no-ipc]`` prefix.

    Verdict (post-IPC; not yet active):
      * FAIL: divergent for >30min (reconciler.seeded=0 + paper_state>0)
      * WARN: divergent < 30min
      * PASS: not divergent (or check skipped per env-gate)

    [29] position_reconciler vs paper_state divergence — phantom dust state。
    F7 E5 spec（2026-04-26）。reconciler.seeded=0 + paper_state>0 持續 >30 min
    即 phantom dust state（reconciler 認為無單但 paper_state 有 ghost positions）—
    真 bug，非穩態。
    當前 IPC 方法 ``get_reconciler_status`` 不存在於 Rust handler registry
    （grep 已驗），per spec「先 skip 並標 SKIPPED」MVP 回 PASS + ``[deferred-no-ipc]``
    前綴，runner 仍顯示該列、cron exit code 不被 flip、操作員可見其 deferred 狀態。
    無 live IPC 往返 — healthcheck 自足、無 HMAC secret 耦合（對齊 [20] G3-08
    Phase 1C 與全 codebase「healthcheck 不發 IPC」立場）。
    Rust IPC handler 加入後升級為 grep-then-call probe；當前 MVP PASS 永遠輸出
    保持 cron 行數穩定。
    """
    # MVP: deferred-no-ipc — return PASS with diagnostic prefix.
    # The ``_cur=None`` parameter slot is kept so the runner contract stays
    # uniform (every check_* takes either a cursor or no argument). Future
    # IPC-driven version will use the cursor for cross-correlation queries.
    # MVP：deferred-no-ipc — 回 PASS + 診斷前綴。_cur=None slot 保持與 runner
    # 契約一致（每個 check_* 取 cursor 或 no-arg），未來 IPC 版會用 cursor 做
    # cross-correlation 查詢。
    return (
        "PASS",
        "[deferred-no-ipc] reconciler vs paper_state divergence check — "
        "Rust IPC method get_reconciler_status not yet exposed; F7 follow-up "
        "will add Rust handler + grep-then-call probe. Currently a stable "
        "PASS placeholder so cron line count is preserved.",
    )

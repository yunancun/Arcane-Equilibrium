# 2026-06-23 -- Profitability Next Move Root Blocker Interface

## Scope

本輪目標是把「demo 很久沒有再下單」與「如何翻越 Cost Gate 形成可持續盈利學習閉環」從人工拼 artifact，收斂成 alpha scorecard/killboard 的穩定 Interface。

## Findings

- Linux runtime 沒有 silent 丟失新信號：Cost Gate learning lane 有持續生成 blocked-signal / operator-authorization artifacts，alpha scorecard 也在讀取它們。
- 當前停單的直接原因不是沒有候選 alpha，而是 bounded Demo probe 還未通過 operator authorization source gates。
- `2026-06-23T12:31:23Z` canonical scorecard：
  - status: `PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING`
  - closure: `BOUNDED_DEMO_PROBE_OPERATOR_AUTHORIZATION_GATES_NOT_READY`
  - leading path: `horizon_edge_amplification:ma_crossover|BTCUSDT|Sell`
  - leading edge: `9.6773bps` vs cost `4.0bps`, `edge_above_cost=5.6773bps`, sample `20077`
  - primary root blocker: `sealed_horizon_probe_preflight.operator_sealed_horizon_review_recorded`
  - next move: `operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe`
  - no global Cost Gate lowering, no active order/probe authority, no authorization object, no promotion proof
- Parallel edge backlog now exposes stronger routes, notably `ma_crossover|ETHUSDT|Sell` with `edge_above_cost=47.4661bps`, while MM/Polymarket remain below cost and Gate-B waits for a live event window.

## Source Changes

- `profitability_path_scorecard.py`
  - Added `cost_gate_root_blockers`, `primary_cost_gate_root_blocker`, `profitability_next_move_v1`, and `edge_amplification_backlog`.
  - Supports both full `gates` arrays and legacy `blocking_gates`.
  - Keeps Cost Gate policy fail-closed: no global gate lowering, no order/probe authority, no runtime mutation, no promotion proof.
- `runtime_runner.py`
  - Mirrors the new next-move/root-blocker/backlog fields into Cost Gate arm, killboard summary, and history rows.
- `discovery_loop.py` / `learning_worklist.py`
  - Carry the new fields into blocker/worklist evidence.
- Tests updated for scorecard and runtime mirror behavior.

## Verification

- Mac: py_compile passed.
- Mac: `test_profitability_path_scorecard.py` plus two alpha runtime tests: `16 passed`.
- Mac: full alpha discovery runtime tests: `62 passed`.
- Mac: alpha cron static: `3 passed`.
- Mac: `git diff --check` passed.
- Commit `a97097a9` pushed to `origin/main` with `[skip ci]`.
- Linux `trade-core`: fast-forwarded clean to `a97097a9`.
- Linux: py_compile passed.
- Linux: scorecard + alpha runtime suite: `76 passed`.
- Linux: alpha cron static: `3 passed`.
- Linux: canonical artifact-only alpha cron smoke exited `0` and refreshed scorecard/killboard.

## Boundary

No CI. No PG write/schema migration. No Bybit private/signed/trading call. No deploy/rebuild/restart. No crontab/env/auth/risk/order/strategy mutation. No Cost Gate lowering. No active probe/order authority. No actual order. No promotion proof.

## Next Engineering Gate

Operator must review sealed-horizon learning evidence first. After that, refresh sealed preflight, placement repair, and authority readiness into a reviewable bounded Demo authorization packet, then collect candidate-matched fill/fee/slippage, matched controls, edge-capture, and execution-realism evidence before any Cost Gate change.

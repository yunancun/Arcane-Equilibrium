# 2026-06-23 -- Profitability Next Move Root Blocker Interface

本輪沒有降低 Cost Gate、沒有授權下單、沒有部署。改動是把盈利閉環的下一步變成機器可讀的 scorecard/killboard Interface。

## Current Runtime Read

- Demo 沒有繼續下單的主因不是沒有 alpha 候選，而是 bounded Demo probe 還沒通過 operator review / authorization gates。
- Canonical scorecard at `2026-06-23T12:31:23Z`：
  - leading candidate: `ma_crossover|BTCUSDT|Sell`
  - edge snapshot: `9.6773bps` vs `4.0bps` cost, `edge_above_cost=5.6773bps`, sample `20077`
  - primary blocker: `sealed_horizon_probe_preflight.operator_sealed_horizon_review_recorded`
  - next move: `operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe`
  - proof gates remaining: sealed preflight, near-touch placement repair, Rust authority readiness
- Parallel backlog exposes `ma_crossover|ETHUSDT|Sell` with `edge_above_cost=47.4661bps`, plus lower-priority MM/Polymarket/Gate-B/fee-scale routes.

## What Changed

- Scorecard now emits:
  - `profitability_next_move_v1`
  - `cost_gate_root_blockers`
  - `edge_amplification_backlog`
- Killboard and learning worklist now mirror those fields.

## Verified

- Mac focused tests green: scorecard/runtime `16 passed`, alpha runtime `62 passed`, cron static `3 passed`.
- Linux focused tests green: scorecard + alpha runtime `76 passed`, cron static `3 passed`.
- Linux artifact-only alpha cron smoke refreshed canonical artifacts successfully.
- Mac/origin/Linux source synced clean at source commit `a97097a9` before this docs checkpoint.

## Boundary

No CI, no deploy/restart, no DB write, no Bybit private/trading call, no Cost Gate lowering, no active order/probe authority, no actual order.

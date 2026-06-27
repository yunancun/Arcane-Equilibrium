# Current Candidate Order Enablement Review

## Status

`DONE_WITH_CONCERNS`

This checkpoint adds and runs a no-order bridge into explicit E3/BB enablement review. It does not admit, submit, cancel, modify, or authorize an order.

Operator correction remains binding: all risk parameters follow GUI-backed Rust RiskConfig. GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1` resolved from accepted Demo equity, not a fixed `10 USDT` cap. GUI `Max Single Position=25%` is `position_size_max_pct=25.0`.

## Source

- Commit: `467c1064337ae3d32a973b4e6ab1dd8b2772cceb`
- New helper: `helper_scripts/research/cost_gate_learning_lane/current_candidate_order_enablement_review.py`
- New tests: `helper_scripts/research/tests/test_current_candidate_order_enablement_review.py`
- Script index updated: `helper_scripts/SCRIPT_INDEX.md`

The helper consumes authority readiness, bounded Demo admission review, read-only governance snapshot, and runtime deploy manifest. It fails closed on stale inputs, non-GUI cap lineage, a `10 USDT` local cap marked authoritative, adapter/writer enablement, mainnet, non-`NORMAL` Guardian state, active leases before enablement review, or authority/proof contamination.

## Verification

- Local py_compile: passed
- Local focused helper tests: `7 passed`
- Local adjacent suite: `64 passed`
- `git diff --check`: passed
- Runtime py_compile on `trade-core`: passed
- Runtime focused helper tests: `7 passed`

## Runtime Sync

- Host: `trade-core`
- Repo: `/home/ncyu/BybitOpenClaw/srv`
- Runtime source checkout: `e8b5c77b171547f0660765cd6e4a9c77f391d70a -> 467c1064337ae3d32a973b4e6ab1dd8b2772cceb`
- Crontab expected-head pins: replaced to `467c1064337ae3d32a973b4e6ab1dd8b2772cceb`
- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_order_enablement_review_20260627T122437Z/runtime_sync_manifest.json`
  - sha `e20c6eeff07b61197fd1f5bb19c01e7e6931e3b0f1dca4cd4752455264da7d7e`
  - status `RUNTIME_SOURCE_SYNC_DONE_NO_RESTART_NO_ORDER`

No service or engine restart was performed in this checkpoint. The running engine binary remains the prior GUI-active-supplier rebuild (`fc60b4f212c19ae0b7124b17f39af8bb4f5e993dfd652818168bb9aa373d7900`, PID `3944810`), which is expected because this checkpoint adds Python review tooling and docs only.

The final docs commit for this checkpoint may advance `origin/main` beyond the runtime checkout. Treat that as documentation drift unless a later source-bearing commit or runtime binary mismatch appears.

## Runtime Review Artifact

- Review JSON: `/tmp/openclaw/current_candidate_order_enablement_review_20260627T122512Z/current_candidate_order_enablement_review.json`
  - sha `d676e0a0dc94c0cc50c81c6c85c13fce325ad8538018eeb513c6596ac22edb9a`
  - status `CURRENT_CANDIDATE_ORDER_ENABLEMENT_READY_FOR_E3_BB_REVIEW_NO_ORDER`
- Review Markdown: `/tmp/openclaw/current_candidate_order_enablement_review_20260627T122512Z/current_candidate_order_enablement_review.md`
  - sha `fe8c1cf296fb22087f8751746a194afb7765ba6575db0198ef44f13da0036010`
- Session state: `/tmp/openclaw/session_loop_state_20260627T122512Z_current_candidate_order_enablement_review/session_loop_state.json`
  - sha `42191b369f6029850fae5f1ca041b18635d6f7162d745d58d53bc8321c2bcef3`
  - status `DONE_WITH_CONCERNS`

Key packet values:

- Candidate: `grid_trading|AVAXUSDT|Sell`
- GUI P1 risk/trade display: `10.0%`
- Rust fraction: `0.1`
- Equity-resolved per-trade budget: `955.1369426 USDT`
- Max single position: `25.0%`
- Local `10 USDT` cap authority: `false`
- Guardian: `NORMAL`, multiplier `1.0`, `lease_live_count=0`, `lease_count=0`
- Runtime posture: `OPENCLAW_ALLOW_MAINNET=0`, adapter blank, writer blank
- `order_capable_action_allowed=false`
- `allowed_to_submit_order=false`

## Boundary

No order/cancel/modify was submitted. No Decision Lease was acquired or released. No Bybit public/private/order call was made. No PG query/write was performed. No writer/adapter was enabled. No runtime env mutation or service restart was performed. No Cost Gate lowering, risk expansion, live/mainnet authority, execution, fill, PnL, or profit proof was produced.

No subagents were spawned in this checkpoint; PM produced a machine-checkable source/runtime bridge because available multi-agent tooling disallowed spawning without an explicit subagent request.

## Next Action

Proceed only to explicit E3/BB exchange-facing enablement review. Before any Demo order-capable action, revalidate in the same window:

- bounded Demo authorization freshness
- active Decision Lease
- Guardian `NORMAL` and Rust authority
- fresh actual BBO and exact order shape
- GUI-derived cap lineage from Rust RiskConfig plus accepted Demo equity
- clean book / pending-order reconciliation
- auditability and reconstructability
- no Cost Gate lowering, risk expansion, live/mainnet, or proof contamination

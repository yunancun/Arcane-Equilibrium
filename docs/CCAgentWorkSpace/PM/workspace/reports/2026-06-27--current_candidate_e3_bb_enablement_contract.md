# Current Candidate E3/BB Enablement Review Contract

## Status

`DONE_WITH_CONCERNS`

This checkpoint turns the next E3/BB enablement review into a machine-checkable no-order contract. It does not provide E3 or BB signoff by itself and does not authorize any order-capable action.

Operator correction remains binding: GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1` resolved from accepted Demo equity, not a fixed `10 USDT` cap. GUI `Max Single Position=25%` is `position_size_max_pct=25.0`.

## Source

- Commit: `b753f4b0a380a0710769e5cf8cd52c019e864245`
- New helper: `helper_scripts/research/cost_gate_learning_lane/current_candidate_e3_bb_enablement_review_contract.py`
- New tests: `helper_scripts/research/tests/test_current_candidate_e3_bb_enablement_review_contract.py`
- Script index updated: `helper_scripts/SCRIPT_INDEX.md`

The helper consumes `current_candidate_order_enablement_review_v1`, revalidates GUI cap lineage and no-authority posture, then requires explicit `current_candidate_e3_bb_enablement_signoff_v1` artifacts for both `E3` and `BB`. Missing or contaminated signoffs fail closed.

## Verification

- Local py_compile: passed
- Local focused helper tests: `6 passed`
- Local adjacent suite: `26 passed`
- `git diff --check`: passed
- Runtime py_compile on `trade-core`: passed
- Runtime focused helper tests: `6 passed`

## Runtime Sync

- Host: `trade-core`
- Repo: `/home/ncyu/BybitOpenClaw/srv`
- Runtime source checkout: `467c1064337ae3d32a973b4e6ab1dd8b2772cceb -> b753f4b0a380a0710769e5cf8cd52c019e864245`
- Crontab expected-head pins: replaced to `b753f4b0a380a0710769e5cf8cd52c019e864245`
- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_e3_bb_enablement_contract_20260627T123939Z/runtime_sync_manifest.json`
  - sha `7b09c9d9731ed8222aee0f69665e114c6db99e84ed8abe88b217ea8346815891`
  - status `RUNTIME_SOURCE_SYNC_DONE_NO_RESTART_NO_ORDER`

No service or engine restart was performed. The running engine binary remains the prior GUI-active-supplier rebuild (`fc60b4f212c19ae0b7124b17f39af8bb4f5e993dfd652818168bb9aa373d7900`, PID `3944810`), which is expected because this checkpoint adds Python review tooling and docs only.

The final docs commit for this checkpoint may advance `origin/main` beyond the runtime checkout. Treat that as documentation drift unless a later source-bearing commit or runtime binary mismatch appears.

## Runtime Contract Artifact

- Contract JSON: `/tmp/openclaw/current_candidate_e3_bb_enablement_contract_20260627T124006Z/current_candidate_e3_bb_enablement_review_contract.json`
  - sha `efe1f1f81b32625a3578f0517b626e3932b92a2ae9610887568710e662b0728a`
  - status `CURRENT_CANDIDATE_E3_BB_ENABLEMENT_REVIEW_SIGNOFF_REQUIRED_NO_ORDER`
- Contract Markdown: `/tmp/openclaw/current_candidate_e3_bb_enablement_contract_20260627T124006Z/current_candidate_e3_bb_enablement_review_contract.md`
  - sha `24bfdd78d675873f6992f5263edb14a4ea9952d12ffcc882d0568260f4d51869`
- Session state: `/tmp/openclaw/session_loop_state_20260627T124006Z_current_candidate_e3_bb_enablement_contract/session_loop_state.json`
  - sha `6a0905ad216515b570aa38904df2ef9167a2f06ac39131acc45c3d7e541c9599`
  - status `DONE_WITH_CONCERNS`

Key packet values:

- Candidate: `grid_trading|AVAXUSDT|Sell`
- GUI P1 risk/trade display: `10.0%`
- Rust fraction: `0.1`
- Equity-resolved per-trade budget: `955.1369426 USDT`
- Max single position: `25.0%`
- Local `10 USDT` cap authority: `false`
- Guardian: `NORMAL`, multiplier `1.0`, `lease_live_count=0`
- Required signoff schema: `current_candidate_e3_bb_enablement_signoff_v1`
- Required signoff decision: `APPROVE_ENABLEMENT_REVIEW_NO_ORDER`
- Missing signoffs: `e3_signoff_missing`, `bb_signoff_missing`
- `order_capable_action_allowed=false`

## Boundary

No order/cancel/modify was submitted. No Decision Lease was acquired or released. No Bybit public/private/order call was made. No PG query/write was performed. No writer/adapter was enabled. No runtime env mutation or service restart was performed. No Cost Gate lowering, risk expansion, live/mainnet authority, execution, fill, PnL, or profit proof was produced.

No subagents were spawned in this checkpoint because the available multi-agent tool explicitly disallows spawning without an explicit subagent/delegation request. This checkpoint therefore does not claim E3 or BB signoff; it only defines and validates the artifact contract those roles must satisfy.

## Next Action

Collect explicit E3 and BB no-order signoff artifacts matching `current_candidate_e3_bb_enablement_signoff_v1` and the order-enable review sha `d676e0a0dc94c0cc50c81c6c85c13fce325ad8538018eeb513c6596ac22edb9a`.

After valid signoffs, any order-capable Demo action still requires a fresh same-window chain:

- bounded Demo authorization freshness
- active Decision Lease
- Guardian `NORMAL` and Rust authority
- fresh actual BBO and exact order shape
- GUI-derived cap lineage from Rust RiskConfig plus accepted Demo equity
- clean book / pending-order reconciliation
- auditability and reconstructability
- no Cost Gate lowering, risk expansion, live/mainnet, or proof contamination

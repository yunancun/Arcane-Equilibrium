# Post-E3/BB Fresh Envelope Cap-Lineage Preflight Blocked

- Date: 2026-06-27
- State transition: `BLOCKED_BY_LOSS_CONTROL`
- Candidate: `grid_trading|AVAXUSDT|Sell`
- Scope: runtime no-order artifact generation and dry-run only

## Result

After the E3/BB no-order signoffs, PM refreshed the current-candidate risk envelope from GUI/Rust RiskConfig plus current Demo equity. The GUI value `10.0` remains `10%`, not `10 USDT`.

Fresh cap resolution:

- Demo equity: `9549.38926928 USDT`
- P1 risk/trade: `10.0%`
- Per-trade/effective cap: `954.93892693 USDT`
- Max single position: `25%`
- Max-single-position budget: `2387.34731732 USDT`
- Local `10 USDT` authority: `false`

The post-signoff final-window dry-run correctly fail-closed before any active lease, quote capture, or order-capable action because downstream gate/sizing/admission artifacts still carry the prior equity/cap context `9551.36942603` / `955.1369426`.

## Runtime Artifacts

- Equity artifact: `/tmp/openclaw/post_e3bb_fresh_envelope_20260627T1506Z/demo_account_equity_artifact.json`
  - sha256: `6c3eb573b35a7edbbdceb80157a9fe8419e305d9c397d14fa9fd388e6ed40502`
  - status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`
- Fresh no-order envelope: `/tmp/openclaw/post_e3bb_fresh_envelope_20260627T1506Z/current_candidate_no_order_refresh_envelope.json`
  - sha256: `e5b4bab0de50dc45f8660f5fbf5505fed0349f4bc2643d081d7f73d6f8dd9d5b`
  - status: `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY`
- Final-window dry-run: `/tmp/openclaw/post_e3bb_fresh_envelope_20260627T1506Z/current_candidate_actual_admission_bbo_lease_window_dry_run_after_fresh_envelope.json`
  - sha256: `a45cf8c80cbbf70d830ffa9f603f48614de9db5d0c6c4f6086d6409d181923a1`
  - status: `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_SOURCE_NOT_READY`
- Session state: `/tmp/openclaw/session_loop_state_20260627T150724Z_post_e3bb_fresh_envelope_cap_mismatch_pause/session_loop_state.json`
  - sha256: `e9f83b10ff9eb0ad51b3800010eade390764e72e010c0a6747882f3ce2b1e26d`
  - state: `BLOCKED_BY_LOSS_CONTROL`

## Blockers

Source preflight blockers:

- `account_equity_usdt_mismatch_gate_packet`
- `admission_review_account_equity_usdt_mismatch`
- `admission_review_cap_mismatch_current_candidate_envelope`
- `admission_review_per_trade_budget_usdt_mismatch`
- `admission_review_single_position_budget_usdt_mismatch`
- `current_candidate_envelope_cap_mismatch_gate_packet`
- `per_trade_budget_usdt_mismatch_gate_packet`
- `single_position_budget_usdt_mismatch_gate_packet`

Runtime blockers were `[]`, loss-control blockers were `[]`, and authority contamination reasons were `[]`. The state is still loss-control blocked because stale cap lineage cannot be allowed into an active same-window admission path.

## Boundary

No Decision Lease acquire/release, Bybit public/private call during dry-run, order/cancel/modify, PG query/write, runtime mutation, Cost Gate lowering, risk expansion, writer/adapter enablement, live/mainnet authority, execution, fill, PnL, or profit proof occurred.

## Next

Per operator request, pause after this round and do not continue dispatching the loop. On resume, first revalidate or refresh any expired standing/auth evidence, then refresh downstream gate/sizing/admission lineage against equity `9549.38926928` and effective cap `954.93892693` before any active lease, quote capture, or order-capable Demo invocation.

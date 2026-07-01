# Renewed Active BBO Window Done

- Status: `DONE_WITH_CONCERNS`
- Active blocker: `P0-CURRENT-CANDIDATE-ACTIVE-LEASE-BBO-WINDOW-E3-BB-REVIEW-RENEWED`
- Next blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-E3-BB-REVIEW`
- Candidate: `grid_trading|ETHUSDT|Buy`
- Review packet: `/tmp/openclaw/renewed_active_bbo_e3_bb_review_20260701T023917Z/e3_bb_active_lease_bbo_renewed_review_request.json`
- Review packet sha: `13d8f44b5fc4e31c47ebd9142555ed38b1c3877f319d448a50c5a973b550eceb`
- Execution base: `trade-core:/tmp/openclaw/renewed_active_bbo_execution_20260701T025350Z/`
- Execution manifest sha: `d2824b348a9780b046853ced3df9d6469b20b3dd5a1113ab8e017e5f52d935ac`
- Final session state: `/tmp/openclaw/session_loop_state_20260701T_renewed_active_bbo_e3_bb_review/session_loop_state_final.json`
- Final session state sha: `996f122b362dfb8f8bfa5668ea8f9038b39c35f575551f9f665b381af3054b01`

## Summary

PM built a renewed E3/BB review packet, corrected the self-hash ambiguity by moving the packet sha into an external manifest, and received E3 plus BB `APPROVE_WITH_CONDITIONS` for the canonical packet sha above.

PM then ran only the approved Demo no-order sequence on `trade-core`. Phase 0 refreshed local Control API / runtime-snapshot equity and a no-authority envelope. Phase A made exactly three approved Demo public market-data GETs. Phase B acquired and released one short active Decision Lease while refreshing same-window public BBO/instrument data.

## Evidence

| Artifact | Status | SHA |
|---|---|---|
| Equity `equity/demo_account_equity_artifact.json` | `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY` | `658017b79117dcfc404e60155913f51baafcf7bb733d7e74c4d601a54c53e387` |
| No-authority envelope `envelope/current_candidate_no_order_refresh_envelope_noauth_ready.json` | `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY` | see manifest |
| Phase A quote `quote/current_candidate_public_quote_construction_refresh.json` | `CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER`; request count `3`; effective BBO age `793.171ms`; raw age `-5ms`; tolerance `10ms` | see manifest |
| Dry-run `actual_admission_dry_run/current_candidate_actual_admission_bbo_lease_window_dry_run.json` | `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DRY_RUN_READY` | see manifest |
| Active window `active_lease_bbo_window/current_candidate_actual_admission_bbo_lease_window_run.json` | `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DONE_NO_ORDER` | `55b7ccc7eeac5d32c0d7a482d0a8b3b9a363fa9bc1b123ed3cdc540a50227fe3` |
| Phase B quote `active_lease_bbo_window/actual_quote_construction_refresh.json` | `CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER`; request count `3`; effective BBO age `731.31ms`; raw age `-5ms`; tolerance `10ms` | `0a7785e092a31013548418c3b3bc4144e6be6c0bfbbade6cd1f9a7f157ffc910` |
| Post-governance `post_active_governance/runtime_governance_snapshot_after_active_lease_bbo_run.json` | `RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY`; `lease_count=0`; `lease_live_count=0` | `6dc5e9964bbb26cd8ab4d65882c2fe7b23e696381bdb4e66cbc6cd79dfbea4b4` |

Active lease details: `lease:36701be74236`, scope `TRADE_ENTRY`, TTL `5s`, acquire ok `true`, release ok `true`, released before artifact `true`.

## Boundary

No order, cancel, modify, Bybit private endpoint, PG write, service restart, env/crontab/risk mutation, Cost Gate lowering, live/mainnet action, fill, PnL, or profit proof occurred.

The released lease and no-order active-window success grant no persistent runtime admission or order authority. The next step is a separate order-capable Demo invocation review with fresh Decision Lease/BBO/order shape, Rust authority, auditability, and reconstructability checks.

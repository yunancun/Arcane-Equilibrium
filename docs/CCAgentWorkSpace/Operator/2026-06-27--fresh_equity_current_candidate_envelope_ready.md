# Operator Note: Fresh Equity Current-Candidate Envelope Ready

State transition: `DONE_WITH_CONCERNS`.

Fresh Demo fast-balance equity was captured through the fixed Control API GET `/api/v1/strategy/demo/balance?fast=1`; the API listens on `100.91.109.86:8000`, not `127.0.0.1:8000`.

Fresh equity artifact:

- `/tmp/openclaw/gui_risk_cap_fresh_equity_refresh_20260627T0150Z/demo_account_equity_artifact_ready_candidate.json`
- sha `f66f7777b6d552b4542c3fbb6347ca0506807c4d22e1d14b1bee5545dac0966b`
- equity `9552.43426257`
- status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`

Current-candidate no-order envelope is now READY:

- `/tmp/openclaw/current_candidate_no_order_refresh_envelope_20260627T0152Z/current_candidate_no_order_refresh_envelope.json`
- sha `6f853183d8dedc598f8d030e4babf1c48f9b7098f7e6123e2d31486d69ad9b36`
- candidate `grid_trading|AVAXUSDT|Sell`
- GUI P1 `10.0%`
- resolved cap `955.24342626 USDT`

No quote capture, no Bybit call, no PG query/write, no Control API POST, no runtime mutation, no order/probe/live authority, and no profit/proof claim.

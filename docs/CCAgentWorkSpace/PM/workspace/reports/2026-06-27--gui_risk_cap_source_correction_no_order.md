# GUI Risk Cap Source Correction No-Order

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-ETH-CONSTRUCTION-REFRESH-REVIEW` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T003527Z_gui_risk_cap_source_correction_no_order.json` |
| `session_loop_state_sha256` | `e5b2db0c00c0c56b3fa0b97e1765318759e7783493f6544a95f052d5136295ca` |

## Correction

Operator clarified that GUI risk settings are the source of truth. The GUI shows:

- `P1 Risk/Trade = 10.0%`
- `Max Single Position = 25%`
- `Total Exposure = 150%`
- `Correlated Exposure = 65%`

Source check confirms GUI `10.0%` maps to `settings/risk_control_rules/risk_config_demo.toml` `limits.per_trade_risk_pct = 0.1`. It is not `10 USDT`. The Rust bounded-probe active order default `DEFAULT_MAX_DEMO_NOTIONAL_USDT_PER_ORDER = 10.0` is a separate local bounded-probe envelope, not the global risk cap.

## Source Changes

- `current_cap_staircase_risk_worksheet.py` now derives `resolved_cap_usdt` from GUI-backed Rust RiskConfig plus auditable `account_equity_usdt`.
- Resolution rule: `min(equity * per_trade_risk_pct, equity * position_size_max_pct / 100, max_order_notional_usdt when enabled)`.
- Construction preview `cap_usdt` is retained only as `source_construction_cap_usdt`; it is not authority.
- Public quote capture and atomic runner no longer default-inject `10.0`; caller cap must match reviewed candidate cap, and artifacts mark global risk cap as unresolved.
- Quote capture/review packet tooling now binds request symbol to `reroute_review.selected_candidate`, so ETH uses ETHUSDT and invalid candidate identity fails before any public request.

## Verification

```text
PYTHONPATH=helper_scripts/research ./venvs/mac_dev/bin/python -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py \
  helper_scripts/research/tests/test_atomic_quote_adapter_preview_runner.py \
  helper_scripts/research/tests/test_cost_gate_atomic_quote_adapter_preview_design.py \
  helper_scripts/research/tests/test_cost_gate_reviewed_public_quote_capture_packet.py \
  helper_scripts/research/tests/test_public_quote_market_snapshot_adapter.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py \
  helper_scripts/research/tests/test_cost_gate_current_cap_staircase_risk_worksheet.py
109 passed

./venvs/mac_dev/bin/python -m py_compile ...modified modules/tests
PASS

git diff --check
PASS

CLI smoke with settings/risk_control_rules/risk_config_demo.toml and account_equity_usdt=100
status=CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY
per_trade_risk_pct_display=10.0
resolved_cap_usdt=10.0
```

## Boundary

No runtime sync, no Bybit call, no PG query/write, no order/cancel/modify, no service/crontab mutation, no Cost Gate lowering, no risk expansion, no adapter/writer enablement, no probe/order/live authority, and no profit/proof claim.

## Next

Resolve ETH no-order cap from GUI-backed RiskConfig plus audited Demo equity. If unresolved, mark `BLOCKED_BY_LOSS_CONTROL`; if resolved, open E3/BB for a fresh no-order public BBO/instruments construction refresh before any order-capable path.

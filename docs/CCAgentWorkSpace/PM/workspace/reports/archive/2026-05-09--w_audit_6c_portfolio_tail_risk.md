# W-AUDIT-6c Portfolio VaR/CVaR/EVT

Date: 2026-05-09
Role: PM
Scope: W-AUDIT-6c / P0-EDGE-1 promotion evidence
Source checkpoint commit: `cc6476dd`

## Decision

W-AUDIT-6c is source/test closed. Portfolio-level tail risk is now a required
promotion-evidence surface for DEMO_ACTIVE -> LIVE_PENDING. Missing or failing
tail-risk evidence blocks promotion fail-closed.

This is not a runtime order-risk switch and does not grant true-live authority.
No DB apply, rebuild, restart, live auth mutation, strategy activation, or order
authority change was performed.

## Implementation

- `program_code/learning_engine/cvar.py`
  - historical VaR and CVaR / Expected Shortfall
  - EVT/GPD peaks-over-threshold tail fit
  - stationary block-bootstrap VaR/CVaR confidence intervals
- `program_code/learning_engine/portfolio_var.py`
  - aligned weighted portfolio-return composition
  - LUNA 2022, FTX 2022, and COVID 2020 stress scenarios
  - `PortfolioTailRiskGate` with fail-closed reasons
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py`
  - adds `demo_tail_risk_report`
  - adds `update_demo_tail_risk_evidence(...)`
  - requires `demo_tail_risk_report.passes=true` before DEMO_ACTIVE can
    graduate to LIVE_PENDING

Fail-closed reasons include insufficient observations, missing stress exposure,
EVT low confidence, non-finite EVT CVaR, historical VaR/CVaR threshold breach,
and LUNA/FTX/COVID stress loss breach.

## Verification

- `python3 -m py_compile program_code/learning_engine/cvar.py program_code/learning_engine/portfolio_var.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py`
- `python3 -m pytest program_code/learning_engine/tests/test_cvar.py program_code/learning_engine/tests/test_portfolio_var.py -q` (13 passed)
- `PYTHONPATH=program_code/exchange_connectors/bybit_connector/control_api_v1:program_code python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_promotion_pipeline.py -q` (39 passed)
- `python3 -m pytest program_code/learning_engine/tests -q` (153 passed)
- `git diff --check`

## Residual

Runtime apply is separate. The new promotion evidence interface exists in source
and tests, but the active API/runtime process will not load it until an
operator-authorized rebuild/restart.

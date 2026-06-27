# Governance GUI Fast Demo Loop

**Status**: `DONE_WITH_CONCERNS`  
**Generated at**: `2026-06-27T19:28:17Z`

## Scope

This checkpoint fixes the Governance GUI semantics around Authorization, Decision Lease, and bounded Demo probe admission, then adds a fast Demo promotion loop spec for moving partially qualified candidates into bounded Demo verification.

## Changes

- `tab-governance.html`
  - Renamed the SM-01 action to `Approve Authorization / 批准授權`.
  - Added an explicit boundary note: Authorization approval is not Decision Lease approval.
  - Marked Decision Lease as read-only short TTL final-window evidence.
  - Added `Bounded Demo Probe Admission / 有界 Demo 驗證准入` panel with machine-checkable gate list.

- `governance-tab.js`
  - Updated the Governance explainer to distinguish Authorization from Decision Lease.
  - Added `updateDemoProbeAdmissionCard()` to derive runtime posture from auth/risk/lease state.

- `docs/agents/profit-first-fast-demo-promotion-loop.md`
  - New fast Demo loop for `DEMO_ELIGIBLE_PARTIAL` candidates.
  - Allows Demo verification when profitability proof is missing, but only if loss-control, GUI/Rust RiskConfig, Decision Lease, Rust authority, auditability, and reconstructability are present.

- `docs/agents/profit-first-autonomy-loop.md`
  - Links to the new fast Demo promotion loop as the bounded Demo acceleration sub-loop.

- `test_governance_demo_probe_admission_gui.py`
  - Static regression tests for Authorization/Lease boundary, Demo admission panel, and loop hard-boundary text.

## Verification

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_governance_demo_probe_admission_gui.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_w_audit_7c_typed_confirm_modal.py::test_w_audit_7c_case01_html_stack_residue_empty program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_w_audit_7c_typed_confirm_modal.py::test_w_audit_7c_case08_governance_tab_js_real_syntax_check`
  - `6 passed`
- `node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/governance-tab.js`
  - passed
- `git diff --check`
  - passed

## Boundary

No Decision Lease acquire/release, no order submission, no cancel/modify, no Bybit private call, no runtime risk mutation, no Cost Gate lowering, no live/mainnet authority, no writer/adapter enablement, no fill, no PnL, and no profit proof.

## Next Development

The next source/runtime task is to implement or wire the final bounded Demo probe runner around the new loop contract:

1. consume `DEMO_ELIGIBLE_PARTIAL` candidate packets;
2. compile the GUI/Rust RiskConfig loss-control envelope;
3. open the final same-window BBO + Decision Lease + Guardian/Rust authority gate;
4. submit at most one bounded Demo order only after all gates pass;
5. collect candidate-matched order/fill/fee/slippage/reconstruction evidence;
6. write after-cost review and feed learning/promotion chain.

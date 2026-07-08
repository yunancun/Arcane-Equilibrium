# IBKR Dual Engine Live-Grade Design Conclusion

Date: 2026-07-07
State: design conclusion stored

Operator clarified the intended IBKR architecture:

- one `ibkr_demo_engine` for paper/demo validation,
- one `ibkr_live_engine` for live-grade local gate/risk/session testing,
- future true-live API binding is possible only after live governance gates pass.

This matches the current Bybit pattern: demo/live profiles are separated by
engine profile, risk config, endpoint profile, secret slot, session identity,
authorization, and audit gates.

Important boundary:

- The live engine shape may be built now.
- True IBKR live contact/execution is not authorized now.
- Withdraw and transfer are not part of the interface.
- Secret contents remain operator-managed; engineering consumes only slot
  identity, capability flags, and fingerprint/status metadata.

Phase2 seal should be session/admission-epoch based, not per-order:

- re-seal on startup/reconnect/credential rotation/endpoint or policy change/TTL,
- per order do lightweight epoch + capability + lease + risk + audit checks.

PM source report:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ibkr_dual_engine_live_grade_design_conclusion.md`

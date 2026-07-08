# Profit-First Dynamic Candidate Gate Refresh E3 Review

Verdict: `APPROVE_FOR_PM_MATERIALIZATION_PREP`

Reviewed at: `2026-07-08T12:10:54Z`

Scope audited read-only. E3 performed no file edits, no Bybit calls, no Decision Lease, no order/probe/cancel, and no runtime/env/service/DB/Cost Gate mutation.

## Evidence

- Source alignment is stable enough for E3 consumption: Mac `HEAD`, Mac `origin/main`, Linux `HEAD`, and Linux `origin/main` all point to `da1a04ecac9e2de86a47a700b76e183509995362`; Linux worktree is clean.
- Mac worktree has unrelated dirty files, but the PM request/report artifacts, Operator summary, TODO/changelog, and standing-envelope producer files are clean.
- Latest runtime selection was re-read from Linux `_latest` artifacts, not the old prompt or committed snapshot. Current `false_negative_candidate_packet_latest.json` sha is `1387ae73...`, generated `2026-07-08T11:33:12Z`, and still selects top false-negative `ma_crossover|NEARUSDT|Buy`. E3 did not mark `ROTATED`.
- Current `autonomous_parameter_proposal_latest.json` sha is `676f6c3e...`, generated `2026-07-08T11:33:12Z`, `selected_side_cell_key=ma_crossover|NEARUSDT|Buy`, `selection_method=top_ranked_false_negative`.
- Runtime old standing auth remains invalid for this candidate: sha `eabf2dab...`, candidate `grid_trading|ETHUSDT|Buy`, expired `2026-07-08T01:53:48Z`.
- Revised request correctly does not pin the candidate: it requires dynamic latest-candidate recheck and says to return `ROTATED` if latest selection differs.
- Requested E3 scope stays no-authority. Forbidden surfaces are explicit: Bybit public/private calls, Decision Lease, order/probe/cancel/modify, bounded Demo final window, operator auth `authorize`, adapter enablement, restart/build, DB write/migration, Cost Gate lowering, live/mainnet, proof/promotion.
- All eight `machine_ready_artifacts` sha256 values in the exact request match current repo files: `1a95874f...`, `0578aba9...`, `cc750eb9...`, `c7492d63...`, `fafb0e44...`, `b54051db...`, `fe0da47b...`, `f278a8a5...`.

## Notes

- The request records generation at older `1d8caa7...`, but the current final checkpoint `da1a04e...` is aligned across Mac/GitHub/Linux and contains the later dynamic-candidate policy revision. E3 does not treat that as source drift.
- Runtime downstream `_latest` preflight/operator-auth artifacts are currently invalid because they still see the old ETH standing auth. That confirms they must not be consumed as authority.

## Allowed Next Actions

- PM may prepare/materialize only the candidate-aligned standing Demo loss-control envelope for current latest `ma_crossover|NEARUSDT|Buy`, preserving mode `0600`.
- Immediately before any runtime write, PM must recheck latest candidate selection and source heads again; if candidate differs, stop as `ROTATED`.
- After materialization, PM may run no-order refresh/readiness validation for the same candidate only.

## Forbidden Next Actions

- No Bybit public/private call before BB.
- No Decision Lease acquire/release.
- No order/probe/cancel/modify or bounded Demo final window.
- Do not set bounded-probe operator authorization to `authorize`.
- No adapter enablement, service restart/build, DB write/migration, Cost Gate lowering, live/mainnet, proof, or promotion.

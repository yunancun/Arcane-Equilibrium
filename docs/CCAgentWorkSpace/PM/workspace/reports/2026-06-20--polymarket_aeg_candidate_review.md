# 2026-06-20 Polymarket AEG Candidate Review

## Summary

- Polymarket lead-lag sample gate is now met for one candidate: `price_target|SOLUSDT|15m`.
- The candidate is statistically strong as an IC cell but is not profitability evidence.
- Added fail-closed AEG candidate metrics support for Polymarket IC reports and propagated `candidate_key` through candidate metrics, robustness matrix, and alpha-discovery.
- Fixed alpha killboard classification so a candidate already reviewed by the latest AEG matrix with zero durable rows is not still shown as promotion-ready.

## Runtime Evidence

- Polymarket latest: sha256 `01764dc4c2e9ade36ba0a9cfa3851aab7a3b9e7de45f543c206951ea56d672dd`, created `2026-06-20T20:02:04.270062+00:00`.
- Candidate: `price_target|SOLUSDT|15m`, sample `30/30`, IC `0.214554`, HAC t `6.754061`, BH q `3.378e-10`, partial IC `0.183527`.
- Feedback caveat: `price_feedback_warning=true`, partial-collapse warning `false`; warning count `33`, partial collapse count `6`.
- Candidate metrics: sha256 `213bdd0a5020e4c44415e2444fbc24a7ab0ae8c945a26f1a40348a2ad6ef9aaa`, `metric_status_counts={"FAIL":1}`, `candidate_key=polymarket_leadlag_ic|price_target|SOLUSDT|15m`.
- Formal matrix: sha256 `f3735c6aee690efb77ae1ccfd017a7ecd62f8ad9658f403aa697f0797074f792`, `final_label_counts={"insufficient evidence":3}`, `coverage_gate_status=FAIL`, `execution_realism_mode=unverified_missing_missing`.
- Alpha latest: sha256 `0f31b41faa50ad144e4419ac0621d99caa93f695f6d40da3c3e20e0115caec9a`, created `2026-06-20T20:06:01.065368+00:00`, status `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, promotion-ready `0`.

## Diagnosis

The candidate cleared the IC gate, but AEG correctly rejects promotion because no PnL, breadth, or execution-realism evidence exists yet. The next useful work is not another AEG rerun; it is to build candidate-specific PnL and execution-realism evidence for this `SOLUSDT` 15m Polymarket lead-lag rule.

## Verification

- Mac: AEG/alpha focused tests `46 passed`; wider focused tests `40 passed`.
- Linux: focused suite `86 passed`.
- `py_compile` and `git diff --check` passed.
- Runtime smoke: candidate metrics, matrix inputs, regime artifact, formal matrix, and alpha throughput all refreshed under `/tmp/openclaw`.

## Boundary

Artifact-only research plumbing and docs. No PG table write, schema migration, Bybit private/signed/trading call, engine/API rebuild/restart, credential/auth/risk/order/strategy mutation, or promotion proof.

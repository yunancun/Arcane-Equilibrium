# 2026-06-20 Polymarket Candidate Replay PnL

## Summary

- Added deterministic paper replay for the Polymarket lead-lag IC candidate.
- The current `price_target|SOLUSDT|15m` candidate is weakly positive after a 4.0bp diagnostic round-trip cost.
- This is not executable alpha: the evidence is single-day, PBO is missing, price-feedback warning remains, and execution realism is unmeasured.

## Runtime Evidence

- Lead-lag latest: sha256 `53bf78173cbd68c57e7a8d90ce6b65fedee8c9cd08eb47a4f39926ac9a8754c0`, created `2026-06-20T20:25:11.520024+00:00`, schema `polymarket.leadlag_report.v0.14`.
- Candidate key: `polymarket_leadlag_ic|price_target|SOLUSDT|15m`.
- Replay: sample `32`, gross mean `4.771bp`, explicit diagnostic cost `4.0bp`, net mean `0.771bp`, holdout net mean `6.829bp`.
- Caveats: `n_days=1`, `price_feedback_warning=true`, execution realism `UNMEASURED`.
- Replay summary sha256 `45a62f447ae19b4c279ef1912a65ad26e594e42deb47cf55f7ba59623a2e72ee`.
- Candidate rows summary sha256 `e98844f620e8633c1373b5fc51676393e1d6f9c2a2f6526c0fecb5e697bb0fb9`, `sample_count=32`, `pbo_status=missing_or_insufficient`.
- Candidate metrics sha256 `eefc76e1a1274358fd965c99ce813b02be9087f641d4ab7ebe1f6d86a168ddf4`, `metric_status_counts={"FAIL":1}`, reject reasons `["n_days_below_30","missing_pbo"]`.
- Formal matrix sha256 `949c8bf6ae97338854facd4f3dd0b49dd660aaf50cfa4ad028b104a057c12c25`, `final_label_counts={"insufficient evidence":3}`, `coverage_gate_status=FAIL`, `execution_realism_mode=unverified_missing_missing`.
- Alpha latest sha256 `612427663c7aa01deefcac8d2f9d224d8c48184845e4da4b566e193365a5f953`, created `2026-06-20T20:27:59.507488+00:00`, scorecard `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, promotion_ready `0`.

## Diagnosis

The replay closes the immediate "no PnL evidence at all" gap, but it does not solve profitability. Mean net is only `0.771bp` after a diagnostic 4.0bp cost and `net_to_cost_ratio≈0.193`; `psr_0≈0.551` is weak, PBO cannot be computed from one date, and no fill/queue/slippage/latency/capacity evidence exists.

The correct next step is accumulating more dated replay samples and building real execution/breadth sidecars. Rerunning AEG alone will keep producing `insufficient evidence`.

## Verification

- Mac focused tests: `68 passed`.
- Linux focused tests: `68 passed`.
- `py_compile` passed for touched research modules.
- Linux read-only smokes passed: lead-lag refresh, replay extraction, candidate rows, candidate metrics, matrix inputs, formal matrix, alpha runtime.

## Boundary

Artifact-only research plumbing and docs. No PG table write, schema migration, Bybit private/signed/trading call, engine/API rebuild/restart, credential/auth/risk/order/strategy mutation, signal, execution proof, or promotion proof.

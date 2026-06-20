# 2026-06-20 Polymarket Replay History Accumulator

## Summary

- Added a deterministic replay-history accumulator for Polymarket lead-lag candidates.
- The existing lead-lag cron now runs it fail-soft after each IC refresh and writes AEG-compatible history evidence.
- Latest result is still not tradable: history remains one date only, PBO still missing, execution realism still unmeasured.

## Runtime Evidence

- Natural cron lead-lag latest: sha256 `5f791942fed1ac7e280f0f0090beb8b6bb65a8b15a7529d0a86d379a33b61f2b`, created `2026-06-20T20:47:04.260456+00:00`.
- Cron status line `2026-06-20T20:47:06Z`: history rc `0`, candidate `polymarket_leadlag_ic|price_target|SOLUSDT|15m`, report_count `4`, matched_report_count `4`, sample_count `33`, n_days `1`, net mean `0.12063233bp`.
- History summary sha256 `ffae11d4e1aa0d4c71782c4eb2389fb808a009c3fe7fa6a844e874a535d9d66c`, status `REPLAY_HISTORY_DAYS_INSUFFICIENT`.
- History evidence sha256 `c176b159a648a7d666b3c1c3055f0bee18a8b8c53ded689c00b6464c6751bed7`.
- AEG direct rows summary sha256 `609964057405b507ef059f632b9f03a2a953b74a13f6b0985fa34692a9ee2a02`, sample_count `33`, pbo_status `missing_or_insufficient`.
- AEG candidate metrics summary sha256 `0853e23a2b6943701deea7b1c851305ef9bb56e3861ce8dec8b917cb1952c1d3`, `metric_status_counts={"FAIL":1}`.
- Metrics row: n_days `1`, n_independent `33`, net_bps `0.12063233`, psr_0 `0.50811419`, dsr_k `0.0`, reject reasons `["n_days_below_30","missing_pbo"]`.
- Alpha latest sha256 `9803397d6708ff935f853222bea8d4a32ab9a1cdd5cba9767b71135b44c0906e`, created `2026-06-20T20:47:58.663929+00:00`; scorecard remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, promotion_ready `0`.

## Diagnosis

This closes the automation gap from the previous checkpoint. Polymarket replay evidence is now accumulated automatically from dated reports and can be fed into AEG direct rows without manual extraction.

It also weakens the immediate profitability case: after the 20:47 refresh, deduped history net mean is only `0.1206bp` after 4bp diagnostic cost, still one date, with one PBO day and no execution realism. The next useful trigger is time plus data: accumulate distinct replay dates, then rerun AEG metrics/matrix and build execution/breadth sidecars.

## Verification

- Mac broad focused suite: `101 passed`.
- Linux broad focused suite: `101 passed`.
- Linux natural cron history status: rc `0`.
- Linux artifact smokes passed: history accumulator, AEG direct rows, AEG candidate metrics, alpha runtime.
- `py_compile`, `bash -n`, and `git diff --check` passed.

## Boundary

Artifact-only research/source/test/docs and `/tmp/openclaw` history artifacts. No PG write, schema migration, Bybit private/signed/trading call, engine/API rebuild/restart, credential/auth/risk/order/strategy mutation, signal, execution proof, or promotion proof.

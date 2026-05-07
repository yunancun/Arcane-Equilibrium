# REF-21 Replay Operator Runbook

**Date:** 2026-05-07  
**Owner:** PM  
**Scope:** one-click full-chain replay after strategy or parameter edits  
**Status:** Active for S2/S2+ development sandbox use; S1 advisory use only when
coverage thresholds pass.

---

## 1. What Replay Is For

Use REF-21 Replay when a strategy, risk parameter, scanner rule, or related
program file changes and you need a fast historical development signal without
waiting days for demo/live_demo data to accumulate.

Replay answers:

- which symbols the historical scanner would have surfaced,
- which strategy/risk decisions the isolated replay runner would have made,
- which fills, fees, rejects, and maker misses the replay model would record,
- whether local recorder coverage is strong enough for higher-confidence
  interpretation,
- how ML/Dream should rank replay summaries as read-only advisory evidence.

Replay does not answer:

- whether future unseen market tape will behave the same,
- whether an old window had historical orderbook data that was never recorded,
- whether parameters may be pushed to live/demo automatically.

---

## 2. One-Click Workflow

1. Open the OpenClaw Control Console.
2. Open the top-level **Replay** tab.
3. Choose:
   - time window,
   - universe preset / symbol cap,
   - strategy selection,
   - timeframe.
4. Click the one-click replay action.
5. Read the **Preflight** panel before the run launches:
   - BBO coverage,
   - orderbook coverage,
   - funding / open-interest / index-price coverage,
   - tick-size coverage,
   - edge snapshot status,
   - execution calibration sample count.
6. If the preflight tier is acceptable for the question being tested, let the
   run continue.
7. Load the report after completion.
8. Use the summary cells:
   - net bps after fee,
   - verdict,
   - maker-miss / risk-reject counts,
   - warnings.

The run path remains:

```text
Control API preflight -> fixture + manifest registration -> dedicated Rust
replay_runner subprocess -> report/finalize -> read-only report analytics
```

The Control API must not execute strategy/risk logic inline.

---

## 3. Fidelity Tiers

| Tier | Meaning | Allowed use |
|---|---|---|
| `S2_PUBLIC_KLINE_ONLY` | Public OHLCV fixture only; no sufficient local microstructure coverage. | Code/parameter development sandbox only. |
| `S2_PLUS_LOCAL_BBO` | Local BBO coverage is present enough to bound taker reference prices. | Better execution sanity check, still development sandbox. |
| `S1_LIMITED_READY` | BBO coverage and minimum execution samples pass the limited threshold. | Limited advisory evidence with explicit caveats. |
| `S1_CALIBRATED_READY` | BBO/orderbook coverage and execution samples pass the calibrated threshold. | Calibrated advisory evidence, still not automatic live/demo authority. |

Current thresholds are:

- S2+: local BBO coverage >= 50%.
- S1-limited: local BBO coverage >= 80% and maker/order samples >= 30.
- S1-calibrated: local BBO/orderbook coverage >= 80% and samples >= 200.

If a window predates local recorder data, replay must stay S2/S2+. Missing
historical BBO/orderbook data must not be fabricated.

---

## 4. Interpreting Results

Treat positive replay output as a development signal, not promotion proof.

Useful signals:

- fee-net bps improves after a strategy edit,
- maker misses or risk rejects decrease,
- scanner-selected symbols match the intended opportunity set,
- preflight shows enough local recorder coverage for the claim being made.

Weak or incomplete signals:

- report says `needs_more_data`,
- BBO/orderbook coverage is low,
- edge snapshots are missing,
- execution sample count is below threshold,
- drawdown / run-band status is unavailable.

The current C3 analytics overlay intentionally marks drawdown and run-band
analytics as unavailable until a balance curve / bootstrap series is added.

---

## 5. ML/Dream Boundary

ML and DreamEngine may use replay as an exploration and ranking surface through
read-only advisory summaries.

The current advisory endpoint returns:

- `advisory_only=true`,
- `mutation_allowed=false`,
- `eligible_for_demo_handoff=false`,
- `applier_path=not_invoked`.

Any parameter application remains a separate governance path. Replay output must
not directly mutate demo, live_demo, or live parameters.

---

## 6. Advanced Workflow

Use Advanced Replay only when you need explicit manifest registration, manual
run IDs, artifact inspection, or lower-level debugging.

Advanced Replay should not replace the one-click workflow for normal strategy
iteration. If the one-click path cannot answer the question, record that as a
replay gap rather than bypassing the trust-tier labels.

---

## 7. Calibration And Retention

The one-click workflow now surfaces the S1 calibration inputs directly in the
Replay tab:

- top-5 orderbook depth coverage controls partial-fill sizing,
- demo/live_demo order state changes provide latency q50/q90,
- report analytics include balance-curve drawdown and stationary block
  bootstrap q10/q50/q90 run bands,
- baseline-vs-candidate comparison is read-only advisory data and never calls
  the demo/live applier path,
- recorder retention is maintained by
  `helper_scripts/cron/ref21_market_recorder_retention.py --apply`.

Current remaining caveat:

- old windows before recorder startup cannot gain historical microstructure
  coverage retroactively.

---

## 8. Operator Rule

After a strategy edit, use replay to reduce the wait for a development signal.
Do not use replay alone to approve live/demo parameter mutation. Promotion still
requires the existing governance gates, demo/live_demo evidence, and explicit
operator approval where required.

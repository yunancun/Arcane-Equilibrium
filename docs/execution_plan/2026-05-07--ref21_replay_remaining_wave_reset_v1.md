# REF-21 Replay Remaining Wave Reset V1

**Date:** 2026-05-07  
**Owner:** PM  
**Status:** C2-C5 completed and Mac/Linux verified after `0eda6005`
**Supersedes for sequencing only:** V1.3 §11 wave table  
**Does not supersede:** REF-21 V1.3 governance gates, write confinement,
subprocess isolation, promotion FSM, or 16 root-principle acceptance.

---

## 0. PM Decision

REF-21 replay is now runtime-usable for one-click full-chain S2 replay:

- the Control API prepares public-market fixtures and registers signed
  manifests,
- strategy/risk execution runs inside the dedicated Rust `replay_runner`
  subprocess,
- scanner timeline replay is active for full-chain manifests,
- V058 symbol-universe snapshots and V059 edge snapshots are wired,
- local BBO/funding/OI/tick-size overlays are consumed when recorder data
  exists,
- taker slippage and maker fill probability are now replay-calibrated from
  demo/live_demo history,
- taker fill reference prices are BBO-anchored when local best bid/ask exists,
- BBO anchor coverage is exposed in API/manifest warnings and the one-click GUI,
- recorder preflight, report analytics, and read-only ML/Dream advisory ranking
  are deployed through `0eda6005`,
- Linux `trade-core` is synced and API-reloaded through `0eda6005`.

The remaining work is no longer "make replay exist". It is "raise replay from
S2/S2+ development sandbox to S1-calibrated advisory quality without inventing
market data that Bybit does not provide".

Therefore the previous R1-R6 table is reset into five practical waves. C2-C4
were intentionally executed sequentially because C3 consumes C2 trust fields
and C4 consumes C3 analytics. C5 is now the documentation, acceptance, and
runtime sign-off wave.

1. **Wave C1 - Execution Realism**
2. **Wave C2 - Data Coverage And Recorder Maturity**
3. **Wave C3 - Replay Result Analytics**
4. **Wave C4 - ML/Dream Advisory Integration**
5. **Wave C5 - Acceptance, UX, And Runtime Sign-Off**

---

## 1. Current Ground Truth

### Completed

| Area | Current state |
|---|---|
| Dedicated subprocess | `replay_runner` is the execution path; Control API does not run strategy/risk inline. |
| Full-chain orchestration | `/api/v1/replay/full-chain/run` registers per-strategy manifests and spawns replay subprocesses. |
| Scanner timeline | Rust scanner timeline reconstructs historical scanner-active symbols from fixture data. |
| Strategy/risk path | Real strategy adapter + replay risk adapter path is active. |
| Tick inputs | Indicators/signals are runner-derived; funding/index/OI/tick-size/BBO are passed when fixture overlays exist. |
| Fee/slippage | Fees are deducted; taker slippage floor is calibrated from demo/live_demo fills. |
| Maker fills | PostOnly order outcomes calibrate a conservative maker fill cap; Rust converts misses to qty=0 maker-miss ghost rows. |
| Universe | V058 symbol universe is the default source; ordering uses ticker turnover when present. |
| Edge snapshots | V059 edge snapshots are embedded when available; missing snapshots are explicit warnings. |
| GUI | One-click replay is available; Advanced replay remains available separately. |
| Preflight | `/api/v1/replay/full-chain/coverage` estimates local recorder, edge snapshot, and execution sample coverage before a run. |
| Report analytics | `/api/v1/replay/report/{experiment_id}` overlays fee-net bps, miss/reject counts, and a development-sandbox verdict. |
| ML/Dream advisory | `/api/v1/replay/advisory/rank` ranks replay summaries as read-only advisory output; no applier or mutation path is exposed. |
| Linux | Mac/origin/Linux synced through `0eda6005`; Linux API reloaded; release runner was rebuilt in the C1 checkpoint. |

### Hard Reality Boundary

Bybit public REST does not provide historical ticker/orderbook endpoints.
Historical L2/BBO for periods before the local recorder existed cannot be
recreated honestly. Those runs must stay labeled as public-kline S2/S2+
replay with missing microstructure coverage.

---

## 2. Remaining Work Count

PM count after the C2-C4 checkpoints:

| Severity | Count | Meaning |
|---|---:|---|
| P0 | 0 | No known blocker prevents replay from being usable as a development sandbox. |
| P1 | 3 | Still needed before calling output S1-calibrated advisory quality: partial fills, latency, and full baseline/candidate comparison. |
| P2 | 2 | Usability and diagnostic hardening after the C5 operator runbook/sign-off sync. |
| Data-maturity gates | 3 | Cannot be solved by code alone; require recorder history / demo outcomes. |

In practical terms: C1-C4 are partially or fully implemented as a usable
development sandbox. Remaining work is no longer an availability blocker; it is
the S1-calibrated advisory lift and richer comparison analytics.

---

## 3. Wave Plan

### Wave C1 - Execution Realism

**Goal:** replay fill quality should be bounded by local microstructure and
historical order outcomes, not only by global slippage floors.

Tasks:

1. **Done in `0bb61aeb` / `a03cdbb7`:** add BBO/spread-aware taker pricing
   in Rust replay fills and surface BBO anchor coverage.
   - Buy taker reference should not be better than best ask when BBO exists.
   - Sell taker reference should not be better than best bid when BBO exists.
   - Preserve slippage floor on top of the BBO anchor.
2. **Open:** add deterministic partial-fill modeling for large orders.
   - Use local `market.ob_snapshots` depth when event-aligned data exists.
   - If no orderbook depth exists, stay fail-conservative and mark
     `partial_fill_model=unavailable`.
3. **Open:** add latency model fields to execution calibration.
   - Use `trading.orders` → `trading.fills` / `order_state_changes` deltas when
     available.
   - Expose q50/q90 latency and freshness.
4. **Partial:** add per-strategy/per-symbol maker cap when samples are
   sufficient.
   - Fallback remains pooled cap `<= 0.40`.
   - Do not promote per-cell cap below `n >= 30`.

Acceptance:

- Rust unit tests show taker buy/sell BBO anchoring.
- Replay report exposes execution model coverage:
  `bbo_anchor_coverage`, `orderbook_depth_coverage`,
  `partial_fill_model_status`, `latency_model_status`.
- Missing BBO/orderbook remains warning, not silent fallback.
- Linux release `replay_runner` build passes.

### Wave C2 - Data Coverage And Recorder Maturity

**Goal:** make future replay windows increasingly S1-capable through durable
recorder data, while old windows remain honestly labeled.

Tasks:

1. **Done in `9ba6ebc6`:** add recorder health summary for `market.market_tickers` and
   `market.ob_snapshots`.
2. **Done in `9ba6ebc6`:** add replay-window coverage estimator before run starts.
   - Estimate BBO/orderbook/funding/OI/tick-size coverage for selected window.
   - GUI shows expected fidelity before launching the run.
3. **Open:** add retention policy / storage budget for microstructure recorder tables.
4. **Partial:** add recorder backfill status panel or healthcheck row.
5. **Done in `9ba6ebc6`:** decide minimum history thresholds:
   - S2+: local BBO coverage >= 50%.
   - S1-limited: local BBO coverage >= 80% and maker/order samples >= 30.
   - S1-calibrated: local BBO/orderbook coverage >= 80% and samples >= 200.

Acceptance:

- GUI cannot imply S1 quality when the recorder has insufficient history.
- Healthcheck detects stale recorder or insufficient recent rows.
- Linux cron proof is recorded where recorder jobs are deployed.

### Wave C3 - Replay Result Analytics

**Goal:** give strategy developers the fast 7-day development signal they need
without overclaiming predictive power.

Tasks:

1. **Open:** add baseline-vs-candidate comparison workflow.
   - Same window, same symbol universe, same recorder coverage.
   - Compare current working tree config vs selected baseline manifest.
2. **Partial in `925d3017`:** add fee-net edge metrics:
   - net bps after fee,
   - trade count,
   - reject/maker-miss rate,
   - max drawdown,
   - q10/q50/q90 run bands.
3. **Open:** add regret / missed-opportunity summary from scanner candidates.
4. **Partial in `925d3017`:** add report verdict:
   - `development_sandbox_pass`,
   - `needs_more_data`,
   - `execution_model_too_weak`,
   - `candidate_worse_than_baseline`.

Acceptance:

- One-click replay report partially answers whether a run was fee-net positive
  in the selected historical sandbox; it does not yet compare against a
  baseline manifest.
- Result copy explicitly says in-sample development sandbox unless a freeze/OOS
  manifest is used.

### Wave C4 - ML/Dream Advisory Integration

**Goal:** let ML and DreamEngine use replay as an exploration/evaluation tool
without turning replay outputs into live commands.

Tasks:

1. **Done in `0eda6005`:** add read-only ML/Dream replay request path.
   - Auth scope and K cap.
   - No direct live/demo parameter write.
2. **Done by policy in `0eda6005`:** keep replay advisory outputs read-only;
   no replay advisory writer or applier is exposed in this checkpoint.
3. **Partial in `0eda6005`:** add candidate ranking input for ML/Dream:
   - baseline delta,
   - confidence tier,
   - execution coverage,
   - promotion eligibility.
4. **Open:** add DreamEngine exploration loop budget and stop conditions.
5. **Done by boundary in `0eda6005`:** ensure existing demo applier gate remains
   a separate governance path; this route cannot hand off to it.

Acceptance:

- ML/Dream can request replay experiments and read advisory summaries.
- ML/Dream cannot directly mutate live parameters from replay output.
- Any demo candidate still passes existing demo applier governance.

### Wave C5 - Acceptance, UX, And Runtime Sign-Off

**Goal:** close REF-21 as a reliable development tool and S1-advisory path when
data quality permits.

Tasks:

1. Final adversarial audit against 16 root principles.
2. Linux full replay suite and release build.
3. GUI review:
   - one-click path remains simple,
   - advanced path remains available,
   - fidelity warnings are impossible to miss.
4. Operator runbook:
   - how to run one-click replay after strategy edits,
   - how to interpret S2/S2+/S1-limited/S1-calibrated,
   - what not to use replay for.
5. Update TODO / CLAUDE state if REF-21 status changes.

Acceptance:

- PM sign-off may say:
  - "usable development sandbox" for S2/S2+,
  - "limited advisory" for S1-limited,
  - "calibrated advisory" only when thresholds pass.

---

## 4. What Not To Do

- Do not fabricate historical orderbook or ticker data for old windows.
- Do not let Python Control API execute strategy/risk logic inline.
- Do not let ML/Dream apply replay-discovered parameters to live directly.
- Do not promote replay outputs as OOS unless the manifest freeze/embargo
  proves it.
- Do not use paper-engine PnL as a trusted calibration source.

---

## 5. Immediate Next Step

Close **Wave C5** for the C2-C4 checkpoint.

Required first slice:

1. Operator runbook for one-click replay.
2. PM sign-off report copied to Operator workspace.
3. TODO / CLAUDE state synchronization.
4. Mac targeted replay suite.
5. Linux sync, API reload, and route probes.

After C5, the next implementation wave should be scoped separately as S1
calibration: partial fills, latency, balance-curve/bootstrap analytics, and
baseline/candidate comparison.

---

## 6. Review Chain

Use shortened but explicit chain for the next checkpoint:

- `PM` local triage and integration.
- `PA` only if BBO/partial-fill design touches runner architecture.
- `E1` implementation.
- `E2` adversarial code review.
- `E4` regression.
- `QC/MIT` before any S1/S1-limited promotion rule changes.
- `BB` if Bybit endpoint semantics or rate policy changes.

For the immediate BBO-anchor slice, PM may implement locally only if the patch
stays narrow and is followed by Linux verification; otherwise dispatch E1/E2/E4.

---

## 7. Revision History

| Version | Date | Author | Notes |
|---|---|---|---|
| V1 | 2026-05-07 | PM | Resets remaining REF-21 work after runtime usable one-click replay and maker execution calibration checkpoint `5403fce3`. |
| V1.1 | 2026-05-07 | PM | Updates status after C1 BBO-anchor fill pricing and GUI/API coverage checkpoints `0bb61aeb` / `a03cdbb7`. |
| V1.2 | 2026-05-07 | PM | Updates status after C2 recorder preflight `9ba6ebc6`, C3 report analytics `925d3017`, and C4 read-only advisory ranking `0eda6005`; C5 becomes runbook/sign-off/runtime sync. |
| V1.3 | 2026-05-07 | PM | Records C5 operator runbook/sign-off and Mac/Linux targeted verification: replay remains usable as S2/S2+ development sandbox; S1 calibration remains a separate quality wave. |

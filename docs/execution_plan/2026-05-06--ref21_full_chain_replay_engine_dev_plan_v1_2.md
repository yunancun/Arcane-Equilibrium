# REF-21 Full-Chain Replay Engine Dev Plan V1.2

**Date:** 2026-05-06  
**Status:** Active revised design / R2-R3 blocked behind B-gates  
**Owner:** PM  
**Supersedes:** `2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_1.md`  
**Audit input:** V1.1 8-agent adversarial closure review, overall rating
`REVISE -> V1.2`  
**Emergency patch:** `/api/v1/replay/full-chain/prepare` is default-OFF behind
`OPENCLAW_REPLAY_PREPARE_ENABLED=0`. It may be enabled only for governed R1
hardening and must not be wired to default GUI.

---

## 0. PM Decision

V1.1 materially improved the REF-21 plan, but the review found one deployed
governance bypass and several unresolved design gaps. V1.2 keeps the product
goal but tightens implementation authority:

> REF-21 is a source-tagged replay sandbox first. It becomes an advisory
> evidence source only after dedicated subprocess isolation, data-tier
> migration, OOS/freeze gates, execution calibration, and verified learning
> readers are implemented.

The existing provisional endpoint from commit `18efb965` is not a REF-21 run
path. It is now treated as a disabled R1 data-preparation tool. Enabling it in
production requires an explicit env flag and still does not unlock R2/R3.

---

## 1. Product Goal And Claim Boundary

Default operator goal remains one-click historical feedback after code or
parameter changes:

```text
historical market universe
  -> historical scanner decisions
  -> active universe timeline
  -> strategies
  -> intent/risk
  -> execution simulator
  -> exits
  -> fee-net report
```

Allowed claim:

- "This is what the replay-isolated stack would have done on this declared
  historical window under declared data-tier limits."

Forbidden claim:

- "This is equivalent to seven days of new live/demo data."

Any report without freeze/OOS proof is labelled `IN_SAMPLE_SANDBOX`.

---

## 2. Emergency R1 Endpoint Gate

The provisional `POST /api/v1/replay/full-chain/prepare` endpoint must remain
default disabled:

- env flag: `OPENCLAW_REPLAY_PREPARE_ENABLED=0` by default,
- disabled response: HTTP 403 with `replay_full_chain_prepare_disabled`,
- disabled path must not fetch market data, scanner state, strategy params, or
  risk config,
- GUI must not bind to this endpoint unless an operator explicitly enables an
  R1 hardening session,
- any enabled use must be logged with actor, window, symbols, source tier, and
  request count.

R1 hardening must add request ceiling, fixture allowlist, duplicate/idempotency
handling, and degradation tests before the endpoint can be considered safe for
operator use.

---

## 3. B-Gates

### B1 Dedicated Subprocess And Runtime Environment

R3 must extend the existing dedicated binary subprocess model:

- canonical binary: `srv/rust/openclaw_engine/src/bin/replay_runner.rs`,
- replay subprocess must not inherit `OPENCLAW_ALLOW_MAINNET`,
- replay subprocess must not load or watch `authorization.json`,
- `EngineMode::Replay` must be compile-time mutually exclusive with Live,
  LiveDemo, Demo, and Paper execution modes,
- no same-process production singleton embedding,
- no use of live `_BYBIT_CLIENT`, `KLINE_MANAGER`, `GovernanceHub`,
  `ExecutorAgent`, DB writer channels, IPC server, or Decision Lease clients.

### B2 Forbidden Dispatch Fail-Closed

Every live dispatch/write/lease/exchange setter reachable from replay must have:

- compile-time trait separation so replay components do not implement live
  dispatch traits,
- runtime guard that hard-errors if isolated replay receives a live tx/client,
- coverage for all current dispatch setters in `tick_pipeline/on_tick`.

Silent `if let Some(tx)` skip behavior is not acceptable in replay isolation.

### B3 State Pollution And Write Confinement

V1.1's byte-equal singleton snapshot requirement is replaced because production
objects contain non-deterministic counters, lazy caches, mutex state, and channel
epochs.

Acceptance now requires:

- symbol audit proving replay subprocess does not import production singleton
  symbols,
- forbidden-path snapshot diff count `0`,
- production singleton access count `0`,
- no writes outside `replay.*` schema and
  `$OPENCLAW_DATA_DIR/replay/<run_id>/`,
- explicit denial for `trading.*`, `learning.*`, `settings/*.toml`,
  `mode_state.json`, `engine_maintenance.flag`, `authorization.json`, and live
  secret files.

### B4 Edge Estimate Snapshot Schema

Reserve migration `V059_edge_estimate_snapshots`:

- append-only hypertable or equivalent immutable table,
- required columns: `asof_ts`, `source_tier`, `config_hash`, `strategy_hash`,
  `scanner_config_hash`, `symbol`, `strategy`, `regime_key`, `cell_key`,
  `estimate_payload_hash`, `estimate_payload_jsonb`,
- retention: at least 75 days,
- writer triggers: hourly cron and on strategy/scanner/risk config hash change,
- scanner replay query: `asof_ts <= window_start - oos_embargo`.

Default `oos_embargo`:

```text
max(7 days, ceil(2 * half_life), max_trade_horizon_bars * bar_size)
```

If no qualifying snapshot exists, report is `IN_SAMPLE_EDGE_CURRENT` and cannot
promote to learning/advisory tiers.

### B5 Strategy Freeze And OOS Semantics

Every full-chain manifest must include:

- `strategy_freeze_date`,
- `strategy_git_sha`,
- `strategy_config_hash`,
- `risk_config_hash`,
- `scanner_config_hash`,
- `window_start`,
- `window_end`,
- `oos_embargo`.

Promotion requires `strategy_freeze_date <= window_start - oos_embargo`.
Otherwise the GUI shows an in-sample warning and report tier remains sandbox.

### B6 Replay Evidence Tier Migration And Learning Gates

Existing V050 tiers conflict with V1.1's matrix. Reserve
`V057_replay_evidence_tiers`:

- expand replay evidence enum / CHECK domain,
- keep legacy values readable but do not auto-promote them,
- map legacy `synthetic_replay` to `synthetic_replay`,
- map legacy `calibrated_replay` to `legacy_calibrated_replay_pending_review`,
- map legacy `counterfactual_replay` to
  `legacy_counterfactual_replay_pending_review`,
- add DB-level `REVOKE` on direct replay-learning reads,
- add `learning.read_replay_eligible_fills()` SECURITY DEFINER reader,
- add verified insert function mirroring REF-19/REF-20 V055/V037 pattern.

Statistical gates for promotion must include DSR, PBO, and Holm/Bonferroni
correction for candidate batches.

### B7 Tier Promotion Matrix

| From | To | Minimum Conditions | Approver |
|---|---|---|---|
| `synthetic_replay` | none | Never promotes | N/A |
| `s2_public_replay` | `s2_oos_replay` | freeze/OOS pass, edge snapshot pass, source mix complete | system gate + PM review |
| `s2_oos_replay` | `s1_calibrated_replay` | S1 recorder data, calibration freshness <= 30d, `n_fills >= 30` per cell or pooled `n >= 100`, MAD execution error <= 25 bps | QC + MIT |
| `s1_calibrated_replay` | `verified_replay_advisory` | DSR positive, PBO <= 0.20, OOS gap <= max(50 bps, 25% predicted edge), no forbidden-path findings | PM + QC + MIT |

No tier may promote if data quality is incomplete, deprecated strategy/symbol
contamination is unresolved, or report finalization is partial.

### B8 Maker Fill Clamp

S2 has no queue depth. Maker fills must be conservative:

- `maker_fill_clamp = min(model, live_demo_30d_p25)`,
- deprecated strategies/symbols and known abandoned positions are excluded from
  `live_demo_30d_p25`,
- default `PostOnly_fill_cap_default = 0.40` when calibration is unavailable,
- default `taker_slippage_default = 50 bps` until S1 calibration exists,
- confidence becomes `S2_OPTIMISTIC_BOUND`.

The report must separate decision correctness from execution realism.

### B9 Agent Endpoint Auth, Rate Limit, And K Cap

All REF-21 agent endpoints require:

- `replay:write` or stricter dedicated scope,
- operator role or signed agent principal,
- per-actor limiter equivalent to REF-20 default 10/min,
- `K <= 100` default,
- `K <= 1000` only with operator override and audit reason,
- no direct mutation of demo/live/live_demo params.

### B10 Decision Lease Canary Compatibility

Acceptance must run with both:

- `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0`,
- `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`.

Replay must never acquire a lease in either mode. All router acquire call sites
must be covered by forbidden-path tests.

### B11 Bybit Data Reality, Rate Safety, And URI Allowlist

Dataset builder must not fabricate unavailable history:

- no historical ticker endpoint is assumed without verified API/source proof,
- reconstructed BBO/ticker fields are labelled reconstructed,
- instrument info is fixture-frozen with `asof_fetch_ts`,
- fee cache is read-only and tier drift is displayed,
- public API ceiling `<= 50 req/s`,
- bulk backfill must not use production `trade-core` IP unless operator approves.

Allowed fixture/source schemes:

- `bybit-public://...`,
- `file://$OPENCLAW_DATA_DIR/replay/...`,
- `file://$OPENCLAW_DATA_DIR/recorder/...`.

Reject `http://`, `https://`, loopback, RFC1918, link-local, metadata IPs, path
traversal, symlink escape, and any file path outside the allowlisted roots.

### B12 Error Timeout And Rollback Criteria

Failure handling must be bounded:

| Failure | Timeout / Bound | Required Result |
|---|---:|---|
| auth / scope failure | <= 1s | 401/403 reason code |
| Bybit single request | 12s | retry budget or bounded failure |
| Bybit 429 / 5xx | <= 60s total prepare | fail-closed, no partial success |
| fixture validation | <= 5s | corrupt/missing reason code |
| disk write failure | immediate OS error | no registered success |
| DB query / transaction | <= 5s | rollback enforced |
| scanner snapshot unavailable | <= 5s | degraded label or fail per manifest |
| edge snapshot unavailable | <= 5s | `IN_SAMPLE_EDGE_CURRENT`, no promotion |
| MLDE/Dream timeout | <= 30s | advisory skipped, replay report intact |
| cancellation | <= 10s cleanup | terminal cancelled state |

Every write transaction must be atomic or compensating rollback must be tested.

### B13 DreamEngine / MLDE Applier Wiring Prerequisite

R6 cannot rely on "existing applier gates" until a separate governance ticket
lands:

- DreamEngine may propose parameter hypotheses only,
- MLDE may rank/veto verified reports only,
- neither may write demo/live/live_demo params directly,
- candidate application requires audited applier route, signed actor, diff,
  cooldown, rollback plan, and operator-visible approval state.

This is a prerequisite B-gate, not optional implementation detail.

### B14 Additional 16-Principle Acceptance

Acceptance must cover:

- Principle #5 survival over profit: replay hard-stop, liquidation buffer, and
  portfolio kill-switch behavior,
- Principle #13 cost_edge_ratio: fee/slippage/cost gate enforced in report
  verdict,
- Principle #14 L0 fallback: replay can run pure rules without ML/Dream,
- Principle #16 portfolio risk: correlation/exposure matrix and portfolio-level
  drawdown under multi-symbol scenarios.

### B15 ScannerCore Trait And Historical Universe

R2 is blocked until scanner live coupling is extracted:

- define `ScannerCore` or equivalent pure trait with explicit inputs,
- isolate live-only adapters from historical replay inputs,
- reserve `V058_symbol_universe_snapshots`,
- store daily/higher-frequency historical instrument universe, delist/relist,
  contract migration, qty/tick changes, and availability windows,
- scanner replay must use historical universe snapshots, not current survivors.

### B16 LOC And Baseline Exception

R3 is expected to exceed the normal 2000-line soft limit if implemented inside
existing large files. PM sign-off is required before any patch that:

- increases `runner.rs` or `bin/replay_runner.rs` by more than 500 LOC,
- adds multi-symbol/multi-strategy logic without extracting modules,
- crosses the 2000-line hard limit without documented baseline exception.

Preferred implementation is new small modules with explicit ownership.

---

## 4. Revised Implementation Waves

### R1 Hardening Only

Scope is limited to the disabled dataset endpoint:

- keep default OFF flag,
- add rate ceiling and request accounting,
- add fixture URI allowlist,
- add Bybit 429/5xx and disk failure tests,
- add canonical fixture hash,
- add idempotency cache for duplicate prepare clicks,
- document enabled-session operator procedure.

R1 does not create full-chain replay reports.

### R2 Historical Scanner Driver

Blocked by B4, B5, B15, and V058/V059. Must produce active universe timeline
from historical scanner inputs and edge snapshots.

### R3 Dedicated Replay Runner

Blocked by B1, B2, B3, B8, B10, B14, and B16. Must prove no order submit, no
lease, no live DB writes, no production singleton import, and fee-net lifecycle.

### R4 GUI

Blocked by R3 and the GUI/UX spec:
`2026-05-06--ref21_gui_ux_spec_v1.md`.

### R5 S1 Recorder

Adds local orderbook/trades/ticker/funding/OI recorder, retention, healthcheck,
and replay reader. Required for confidence above S2 optimistic bound.

### R6 MLDE / Dream Exploration

Blocked by B6, B7, B9, and B13. Advisory only.

---

## 5. Quantified Acceptance

REF-21 is not accepted until:

1. default full-chain prepare endpoint is disabled unless env flag is set,
2. 7-day replay covers at least two historically available scanner-selected
   symbols and one dynamic universe change,
3. historical scanner uses `V058` universe and `V059` edge snapshots or labels
   the report non-promotable,
4. strategy/risk/scanner freeze and OOS embargo pass for promotable reports,
5. accepted and rejected risk decisions remain visible with reason codes,
6. fee-net PnL deducts maker/taker fees from balance,
7. S2 execution uses maker clamp and confidence `S2_OPTIMISTIC_BOUND`,
8. hard-stop/liquidation/cost-edge/L0/portfolio-correlation tests pass,
9. report includes net bps, percent, q10/q50/q90, drawdown, trade/reject count,
   per-strategy, per-symbol, per-regime, and source mix,
10. forbidden-path audit proves no order submit, lease acquire, live DB write,
    live dispatch, production singleton import, or out-of-root file write,
11. agent endpoints enforce auth, limiter, K caps, and audit logging,
12. learning reads only use security-definer verified reader,
13. all failure paths in B12 return bounded JSON and terminal run states,
14. Linux unit/integration/forbidden/degradation/route-load suites are green.

---

## 6. Required Review Chain Before R2/R3

1. CC + E3: B1/B2/B3/B9/B10/B11/B12/B13/B14.
2. MIT: V057/V058/V059, learning gates, survivorship.
3. QC: OOS, DSR/PBO/Bonferroni, maker clamp, promotion thresholds.
4. BB: Bybit endpoint reality, rate/IP policy, instrument/fee drift.
5. FA: quantified acceptance and failure-state closure.
6. A3 + TW: GUI/UX spec.

R2/R3 may begin only after this review chain returns Conditional/B or the
operator explicitly overrides a named B-gate.

---

## 7. Revision History

| Version | Date | Author | Notes |
|---|---|---|---|
| V1 | 2026-05-06 | PM | Initial direction baseline; superseded. |
| V1.1 | 2026-05-06 | PM | Added B-gates after first audit; superseded after deployed endpoint bypass and residual gaps were found. |
| V1.2 | 2026-05-06 | PM | Adds default-OFF endpoint gate, subprocess env/auth rules, write confinement, V057/V058/V059 migration reservations, promotion thresholds, maker defaults, timeout criteria, applier prerequisite, 16-principle acceptance, ScannerCore, LOC exception, and GUI spec dependency. |

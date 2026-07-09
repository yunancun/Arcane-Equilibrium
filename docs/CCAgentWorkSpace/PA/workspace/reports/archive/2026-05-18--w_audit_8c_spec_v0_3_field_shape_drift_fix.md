# W-AUDIT-8c Spec v0.3 — Field-Shape Drift Fix + Density Floors

Date: 2026-05-18
Role: PA(default)
Workgroup: A-4 / W-AUDIT-8c
Repo root: `/Users/ncyu/Projects/TradeBot/srv`
Report status: PA spec surgical patch — implementation NOT authorized by this report
Single-agent + background; sibling-parallel with E1 healthcheck amend on `feature/w-audit-8a-c1-liq-writer-impl` (zero file overlap).

## §0 Executive Summary

W-AUDIT-8c strategy spec was v0.2 specified against an assumed 60s rolling window + `cluster_score` field. The C1-LIQ-WRITER provider IMPL (`feature/w-audit-8a-c1-liq-writer-impl` @ 7ab6c22d, 3-agent APPROVE) landed with a 5m sliding-window `LiquidationPulse` panel exposing notional-based fields (`cluster_notional_5m`, `long_notional_5m`, `short_notional_5m`, `event_count_5m`, `dominant_side`). MIT review (agent a09c6873) + E2 review (agent a9aee390) flagged the field-shape drift, and MIT 2026-05-18 empirical PG SoT showed 0.2-1.5% 7d 5m bucket coverage per symbol — single-event buckets trivially pass the provider's `DOMINANT_SIDE_RATIO = 0.6`.

v0.3 surgical patch (128 ins / 38 del / 365 LOC total):
1. Field-shape drift fixed against IMPL truth
2. Three density floors added with PA-defended defaults
3. Strategy hypothesis re-articulated for multi-event cluster requirement
4. Per-symbol density tier stratification (high / medium / low) — independent promotion
5. K_total enlarged 48× (243 → 11_664 per symbol) for density-floor sweep
6. Acceptance criteria add false-positive-rate gate + density-floor filter efficacy requirement

## §1 Field-shape Drift Fix

| Aspect | v0.2 spec | C1-LIQ-WRITER IMPL @ 7ab6c22d | v0.3 spec |
|---|---|---|---|
| Window | rolling 60s | 5m sliding (`WINDOW_5M_MS = 5*60*1000`) | 5m sliding (matched) |
| Cluster magnitude | `cluster_score` (normalized 0-1) | `cluster_notional_5m: f64` (USD-equiv) | `cluster_notional_5m` |
| Notional field | `notional_usd_60s = sum(qty * price)` | `cluster_notional_5m`, `long_notional_5m`, `short_notional_5m` | `cluster_notional_5m` (provider-supplied, not consumer-computed) |
| Event count | `event_count_60s` | `event_count_5m: u32` | `event_count_5m` |
| Threshold field | `cluster_score >= score_floor` | (no such field; renamed accordingly) | `cluster_notional_5m >= cluster_notional_floor_usd` |
| Dominance | `side_dominance = max(side_notional) / total_notional` | computed at provider with `DOMINANT_SIDE_RATIO = 0.6` → `dominant_side: LiquidationSide` enum | provider-supplied `dominant_side`; consumer recomputes `side_dominance_ratio` for floor check |
| Pulse age | `pulse_age_ms = decision_ts - cluster_end_ms` | `snapshot_ts_ms: i64` panel-level | `pulse_age_ms = ctx.ts_ms - pulse.snapshot_ts_ms` |

Drift fix count: **7 field-name / shape corrections**.

## §2 Density Floors Added (v0.3 NEW)

Single-event 5m buckets trivially pass `DOMINANT_SIDE_RATIO = 0.6` at provider side (a single Buy event = 100% long ratio). The strategy consumer must add density floors:

| Floor | Field check | PA-defended default | Rationale |
|---|---|---|---|
| `min_event_count_5m` | `pulse.event_count_5m >= K` | **K = 3** | Reject single/double-event buckets. MIT empirical: HYPEUSDT 31 → 14 multi-event clusters after K=3, BTCUSDT 18 → 8. K=5 over-prunes to ETH/BTC only. |
| `min_cluster_notional_5m_usd` | `pulse.cluster_notional_5m >= N_usd` | **N_usd = 10_000** | Reject micro-clusters. MIT empirical: ETHUSDT 10 / BTCUSDT 11 / SOLUSDT 6 / DOGEUSDT 5 buckets in 7d at this floor. Stage 0R calibrates per tier. |
| `min_dominant_event_count` | count(`recent_events` where side == `dominant_side`) `>= M` | **M = 2** | Reject pseudo-dominance from a single large-notional event. Provider uses notional ratio (one 1M USD Buy = 100% long); strategy adds event-count gate. |

All three must pass simultaneously. Stage 0R sweep grid: `(K, N_usd, M)` at `(2, 5K, 1)`, `(3, 10K, 2)`, `(5, 25K, 3)`, `(8, 50K, 3)`.

## §3 Strategy Hypothesis Revision (v0.3)

Old primary hypothesis: "post-cascade short-term mean reversion" — implicitly assumed any 5m bucket with a single liquidation event represents a tradable cluster.

New primary hypothesis (v0.3): **post-multi-event-cluster short-term mean reversion**.

Re-articulation key points added:
1. Empirical data-feasibility envelope table inserted (HYPEUSDT 1.54% / BTC 0.89% / ETH 0.99% / SOL 1.09% / LINK 0.20% 7d 5m bucket coverage).
2. v0.3 explicitly rejects v0.1/v0.2 implicit single-event-bucket assumption.
3. Acknowledges provider-side `DOMINANT_SIDE_RATIO = 0.6` cannot by itself filter single-event noise.
4. Per-symbol density tier stratification (high / medium / low) — promotion floors apply per tier independently; low-density tier expected to fail and be reported but not promoted.
5. K_total enlarged 48× (243 → 11_664 per symbol) for density-floor sweep — DSR penalty grows correspondingly.

## §4 Acceptance Criteria Revision (v0.3)

Stage 0R promotion floor adds 3 new gates:

1. **Density-floor filter efficacy**: must remove `≥ 60%` of single/double-event 5m buckets — proves the floor is doing real noise rejection rather than rubber-stamping provider output.
2. **False-positive rate gate**: forward return within ±5 bps after fee/slippage in winning grid cell `≤ 40%` — proves trigger isn't dominated by noise events.
3. **Per-tier independent promotion**: each density tier (high / medium / low) must independently pass `n_eff` + `avg_net_bps` + PSR/DSR; pooled promotion not allowed across tiers.

Mandatory report fields add: per-tier breakdown, FP-rate by sweep cell, density-floor filter efficacy (raw → after K → after N_usd → after M chain count), 5 exclusion categories (was 4: stale / missing / mixed-side / quiet-window; now adds density-floor-fail).

## §5 Pre-IMPL Trigger-Rate Prediction (post density floors at K=3 / N_usd=10K / M=2)

| Tier | Symbols | Multi-event clusters per 7d per symbol | Predicted triggers per day per symbol | Tier total per day |
|---|---|---|---|---|
| High-density | HYPE, SOL, ETH, BTC, DOGE, BSB, TON | 7-14 | 1-2 | ~10-14 |
| Medium-density | XRP, EDEN, SUI, PEPE, ZEC | 2-7 | 0.3-1 | ~2-5 |
| Low-density | LINK, LTC, NEAR, OP, ADA, + others | ≤ 1 | < 0.15 | < 1 |

Total cohort post-floors: roughly **20-25 candidate triggers per day**, of which (per FP-rate gate ≤ 40%) ≤ 8-10 expected uninformative.

## §6 Critical Risk — Alpha Feasibility Honest Assessment

Even with density floors landed, alpha feasibility faces four structural headwinds:

1. **n_eff per active side branch per tier is tight**: ~14 multi-event clusters per 7d per high-density symbol × ~3 side-dominance × ~3 quiet_window × 4 N_usd × 3 K cells drops per-cell n sharply. Per-tier-pooled n_eff likely 80-150 range for high-density tier, 30-60 range for medium tier on 7d window; promotion floor `n_eff ≥ 300 pooled when more than one symbol inspected` requires **21-30d replay window minimum**.
2. **Fee/slippage burden at 5m horizon**: alpha-deficient regime (P0-EDGE-1 root cause pending Phase B/C/D) means even `avg_gross_bps > 0` likely flips negative net after maker-taker mix.
3. **K_total inflation 48×**: K_total per symbol = 11_664; across ~8-10 inspected symbols × momentum branch counted = K_total ~100k-200k. PSR/DSR threshold 0.95 with that many comparisons is brutal.
4. **Provider data is brand new**: production WS revival 0e8a8ae8 only landed 2026-05-17. 7d window of real data is still <14 days into life. Early-life data may not represent regime-stable behavior.

**Honest verdict on `P(reach Demo canary in Stage 0R)`**: **15-25%**.

## §7 Recommendation: PROCEED (with eyes open)

Stage 0R replay is the right reality check. Either:
- (A) it produces evidence to retire the strategy candidate cleanly (most likely outcome at 15-25% pass probability), or
- (B) it produces a passing high-density tier surviving rigorous statistics (low probability but high value).

Status quo (mainnet excluded, demo gated, no real exposure) means downside is zero. Cost = ~1 replay sprint (Stage 0R-only). PA recommends PROCEED to W-AUDIT-8c Stage 0R IMPL dispatch when prerequisites are ready:

Prerequisites:
- ✅ C1 24h proof PASS_C1_PROOF_CANDIDATE (2026-05-17)
- ✅ BB cor-side mapping APPROVE
- ✅ V095 apply + production WS revival 0e8a8ae8
- ✅ MIT idempotency PK upgrade
- ✅ C1-LIQ-WRITER provider IMPL @ 7ab6c22d 3-agent APPROVE
- ⏳ MIT re-sign on density-floor + tier stratification semantics (will be triggered by this spec v0.3 review pass)
- ⏳ PM dispatches W-AUDIT-8c Stage 0R replay IMPL (separate worktree from this spec packet)

This v0.3 spec packet does NOT authorize IMPL. PA spec doc surgical patch only.

## §8 Side Effects + Hard Boundary Audit

PA risk rating for the spec change: **LOW** (spec-only; no runtime / TOML / Rust / migrations / authorization touch).

16-root-principles checklist:
- A 級 (16/16 + 0 violations)
- Spec-doc-only patch; 0 IMPL
- 0 commit; 0 push; 0 sub-agent dispatch
- 0 Rust / TOML / migrations / runtime config / authorization touch
- `live_execution_allowed` / `max_retries=0` / `system_mode` invariant unchanged
- DOC-08 §12 9 invariants all PASS
- Mainnet `OPENCLAW_ALLOW_MAINNET` invariant unchanged
- AlphaSurface.liquidation_pulse remains `None` for any strategy until W-AUDIT-8c IMPL lands separately

E2 review focus (when next IMPL dispatched):
1. Fail-closed behavior: missing / stale / mixed `liquidation_pulse` / density-floor-fail emit no action.
2. Event-trigger semantics: no REST/PG polling loop; no multiple actions from one cluster id.
3. Replay leakage: cluster construction, quiet window, forward returns all use strict as-of timestamps; 5m sliding window dedupe via `(symbol, dominant_side, floor(ts/300_000))` + 5m cooldown.

MIT review focus (when next IMPL dispatched):
1. Density-floor K / N_usd / M sweep grid correctly counted in K_total.
2. Per-tier stratification semantics (high / medium / low) independent promotion; tier boundaries are PA-defended not data-snooped.
3. False-positive rate definition (±5 bps after fee/slippage forward return).

BB review focus (when next IMPL dispatched): no change from v0.2 (topic syntax + side semantics + rate-limit + control-topic + topic-builder guard).

## §9 Files Touched

- `srv/docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md` (+128 / -38 / 365 LOC total)
- `srv/docs/CCAgentWorkSpace/PA/memory.md` (appended)
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8c_spec_v0_3_field_shape_drift_fix.md` (this report)

No code / Rust / TOML / migrations / runtime config changes.

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8c_spec_v0_3_field_shape_drift_fix.md

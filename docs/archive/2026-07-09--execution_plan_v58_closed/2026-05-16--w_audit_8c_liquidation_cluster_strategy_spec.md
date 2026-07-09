# W-AUDIT-8c -- A4-B Liquidation Cluster Reaction Strategy Spec

Date: 2026-05-18 (v0.3 — field-shape drift fix + density floors from empirical MIT sparsity finding)
Status: Spec v0.3 / spec-only re-shape against C1-LIQ-WRITER provider IMPL (`feature/w-audit-8a-c1-liq-writer-impl` @ 7ab6c22d) / no production runtime authority
Scope: New alpha candidate consuming AlphaSurface Tier 3 `LiquidationPulse`. v0.3 fixes 60s → 5m field-shape drift discovered after C1-LIQ-WRITER provider IMPL landed with 5m sliding-window panel shape, and adds three density floors (`min_event_count_5m`, `min_cluster_notional_5m_usd`, `min_dominant_event_count`) per MIT 2026-05-18 empirical PG SoT showing 0.2-1.5% 5m bucket coverage. No production WS subscription change, no runtime config change, no risk/sizing change, no demo/live launch.

## Changelog

| Version | Date | Author | Summary |
|---|---|---|---|
| v0.1 | 2026-05-16 | PA | Initial spec with 60s rolling window + `cluster_score` design |
| v0.2 | 2026-05-16 | PA | Source/test prerequisites; correction-scoped packet only |
| **v0.3** | **2026-05-18** | **PA** | **Field-shape drift fix: `60s` → `5m`, `cluster_score` → `cluster_notional_5m`, `notional_usd_60s` → `cluster_notional_5m`, `score_floor` → `cluster_notional_floor_usd`. Add density floors: `min_event_count_5m ≥ 3`, `min_cluster_notional_5m_usd ≥ 10000`, `min_dominant_event_count ≥ 2`. Strategy hypothesis re-articulated for multi-event cluster requirement. Acceptance criteria add false-positive-rate threshold + per-symbol density tier stratification. References C1-LIQ-WRITER IMPL @ 7ab6c22d (MIT + E2 + BB 3-agent APPROVE) and MIT empirical sparsity finding (HYPEUSDT 1.54% / BTC-ETH-SOL 0.8-1.1% / LINK-DOT 0.2-0.25% 7d 5m bucket coverage).** |

## PM / PA Verdict

`liquidation_cluster_reaction` remains blocked from production/runtime revival. W-AUDIT-8a C1 has a 2026-05-17 technical PASS (`PASS_C1_PROOF_CANDIDATE`), and BB approved the corrected Bybit side mapping, but MIT approval is conditional on fixing lossy `market.liquidations` idempotency before any production writer revival.

Until MIT re-signs the schema/writer identity and PM authorizes a separate revival task, production topic builders must continue to exclude `liquidation.*`, `price-limit.*`, `adl-notice.*`, and `allLiquidation*`; `AlphaSurface.liquidation_pulse` must remain `None`; any strategy declaring `LiquidationCascade` must fail closed.

## Relationship To W-AUDIT-8a C1

Hard prerequisites before any production writer/runtime revival:

1. C1 final report returns `PASS_C1_PROOF_CANDIDATE` for `allLiquidation.{symbol}` over the required real-connection window. Status: technical PASS on 2026-05-17.
2. BB signs zero topic rejection, zero `handler not found`, no candidate-topic poisoning of control streams, acceptable reconnect behavior, and corrected `S=Buy/Sell` semantics. Status: APPROVE on corrected mapping.
3. MIT signs the mapping from Bybit payload fields `T/s/S/v/p` to `market.liquidations` after the storage identity preserves one `data[]` item per row. Status: APPROVE-CONDITIONAL; old PK `(symbol, ts, side)` is lossy for same-ms same-side items.
4. PM authorizes the production revival task. This spec alone does not authorize it.

Replay can validate local fail-closed behavior before C1, and C0 already added that coverage. Replay cannot prove Bybit topic safety, connection health, or production subscription compatibility.

## Hypothesis Freeze

Primary hypothesis: **post multi-event-cluster short-term mean reversion**.

### Empirical data-feasibility envelope (MIT 2026-05-18 PG SoT)

| Symbol | 7d 5m buckets with ≥ 1 event (coverage_pct) | 7d 5m buckets with ≥ 3 events | 7d 5m buckets with ≥ 5 events | 7d 5m buckets with ≥ 10K USD notional | avg events / non-empty bucket |
|---|---|---|---|---|---|
| HYPEUSDT | 31 (1.54%) | 14 | 5 | 3 | 4.94 |
| SOLUSDT | 22 (1.09%) | 9 | 5 | 6 | 28.86 |
| ETHUSDT | 20 (0.99%) | 11 | 9 | 10 | 83.40 |
| BSBUSDT | 19 (0.94%) | 7 | 6 | 3 | 10.26 |
| BTCUSDT | 18 (0.89%) | 8 | 7 | 11 | 57.22 |
| TONUSDT | 18 (0.89%) | 9 | 4 | 6 | 8.22 |
| XRPUSDT | 17 (0.84%) | 6 | 3 | 3 | 25.47 |
| DOGEUSDT | 16 (0.79%) | 9 | 6 | 5 | 15.38 |
| LINKUSDT | 4 (0.20%) | (≤1) | (≤1) | (≤1) | small-n |
| LTCUSDT | 4 (0.20%) | (≤1) | (≤1) | (≤1) | small-n |

Out of 2016 5-minute buckets per 7d, the most-active symbol (HYPEUSDT) emits only 31 buckets with any liquidation events. After applying `min_event_count_5m ≥ 3`, that drops to 14 candidate clusters per 7d for HYPEUSDT — roughly **2 candidate triggers per day per top-density symbol**. Tail symbols (LINK / LTC / NEAR / EDEN) fall to **≤1 multi-event cluster per week**, making per-symbol stratification mandatory and rendering several symbols structurally ineligible.

### Rationale (v0.3 re-articulated)

- A liquidation cluster is forced flow, not discretionary informed flow. After the burst decelerates, the first tradable edge is more likely exhaustion/rebound than chasing the same forced flow.
- The survival-first posture prefers reacting after a burst has become stale or decelerating, rather than adding leverage into the middle of an active cascade.
- The strategy can express this with explicit event-trigger guards: fresh pulse required, **multi-event density required** (single/double event clusters are noise, not cascades — per MIT empirical), side dominance required, quiet window preregistered, and no fallback to TA-only signals.
- v0.3 explicitly rejects the v0.1/v0.2 implicit assumption that any 5m bucket with at least one event represents a tradable cluster. The provider-side `DOMINANT_SIDE_RATIO=0.6` constant in `liquidation_pulse.rs` cannot by itself filter single-event noise (a single Buy event in a bucket trivially passes 100%-long ratio) — the strategy consumer must add density floors.

Directional mapping, per BB corrected side-semantics sign-off:

- Dominant `Buy` liquidation payloads (`S=Buy`), interpreted as long liquidations (`LiquidationSide::LongLiquidated`), propose `expected_dir = +1` after the quiet-window guard.
- Dominant `Sell` liquidation payloads (`S=Sell`), interpreted as short liquidations (`LiquidationSide::ShortLiquidated`), propose `expected_dir = -1` after the quiet-window guard.
- Ambiguous side, mixed dominance, unknown Bybit side semantics, or `LiquidationSide::Mixed` emits no action.

### Per-symbol density tier stratification (v0.3 NEW)

Stage 0R replay must report results **stratified by per-symbol density tier**, not pooled:

- **High-density tier**: symbols with ≥ 10 multi-event clusters per 7d (HYPEUSDT / SOLUSDT / ETHUSDT / BTCUSDT / DOGEUSDT / BSBUSDT / TONUSDT).
- **Medium-density tier**: symbols with 4-9 multi-event clusters per 7d (XRPUSDT / EDENUSDT / SUIUSDT / PEPEUSDT / ZECUSDT).
- **Low-density tier**: symbols with ≤ 3 multi-event clusters per 7d (LINKUSDT / LTCUSDT / NEARUSDT / OPUSDT / ADAUSDT / others).

Promotion floors apply per tier independently. Low-density tier cannot reach `n_eff ≥ 50` per active side branch in any reasonable replay window without leakage; it must be reported but not promoted.

Secondary sensitivity: **momentum continuation** is preregistered only as a sensitivity branch. It reverses the direction mapping above, but it cannot make this mean-reversion spec eligible for Stage 1 Demo. If the sensitivity branch wins, PA must write a separate hypothesis update and its inspected cells must remain counted in `K_total`.

## AlphaSurface Tier 3 Consumer Contract

The strategy consumes the existing first-class interface:

```rust
fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
    const TAGS: &[AlphaSourceTag] = &[
        AlphaSourceTag::LiquidationCascade,
        AlphaSourceTag::Ta1m,
        AlphaSourceTag::Ta5m,
    ];
    TAGS
}

fn on_tick(
    &mut self,
    ctx: &TickContext<'_>,
    surface: &AlphaSurface<'_>,
) -> Vec<StrategyAction> {
    let Some(pulse) = surface.liquidation_pulse else {
        return Vec::new();
    };
    // evaluate event-trigger guard; no continuous polling or TA fallback
}
```

`LiquidationCascade` is the primary alpha source. Tier 1 TA is allowed only for volatility/cost and closed-bar confirmation; it cannot substitute for a missing or stale `liquidation_pulse`.

`OrderflowImbalance` is intentionally not declared in this spec. Adding it later would be a separate variant because it changes both availability and `K_total`.

### Required consumer fields (v0.3 — aligned to `LiquidationPulse` struct in `rust/openclaw_core/src/alpha_surface.rs` lines 248-265)

The provider produces a 5-minute sliding-window `LiquidationPulse` (not a 60s rolling window — IMPL chose 5m sliding per `WINDOW_5M_MS = 5 * 60 * 1000`). The strategy consumer reads:

- `recent_events: Vec<LiquidationEvent>` — the 5m sliding window of strictly per-symbol events
- `cluster_notional_5m: f64` — sum of `long_notional_5m + short_notional_5m` (USD-equivalent = `qty * price`)
- `long_notional_5m: f64`
- `short_notional_5m: f64`
- `event_count_5m: u32`
- `dominant_side: LiquidationSide` — `LongLiquidated` / `ShortLiquidated` / `Mixed`, computed at provider side using `DOMINANT_SIDE_RATIO = 0.6`
- `snapshot_ts_ms: i64`

Strategy-derived (computed in `on_tick` from above):

- `side_dominance_ratio = max(long_notional_5m, short_notional_5m) / cluster_notional_5m`
- `pulse_age_ms = ctx.ts_ms - snapshot_ts_ms`

### Freshness

- WARN if pulse age is greater than 10s.
- FAIL/no-action if pulse age is greater than 60s.
- FAIL/no-action if `dominant_side = Mixed`, density floors fail (see next subsection), or `ctx.symbol` has no entry in `LiquidationPulsePanel.pulses` HashMap.

### Density floors (v0.3 NEW — counters provider-side noise per MIT empirical)

A 5m bucket with a single Buy event trivially passes `DOMINANT_SIDE_RATIO = 0.6` at 100% — provider does **not** filter single-event noise. Strategy consumer applies three floors:

| Floor | Field | Initial value | Rationale |
|---|---|---|---|
| **`min_event_count_5m`** | `pulse.event_count_5m >= K` | **K = 3** | Reject single/double-event buckets. MIT empirical: HYPEUSDT 31 → 14 multi-event clusters after K=3, BTCUSDT 18 → 8. K=3 keeps top-density tier viable; K=5 would over-prune to ETHUSDT/BTCUSDT only. |
| **`min_cluster_notional_5m_usd`** | `pulse.cluster_notional_5m >= N_usd` | **N_usd = 10_000** | Reject micro-clusters (HYPEUSDT avg 4.94 events × small qty/price below 10K USD). MIT empirical: ETHUSDT 10 / BTCUSDT 11 / SOLUSDT 6 / DOGEUSDT 5 buckets in 7d. Stage 0R replay must calibrate this per tier (high-density tier may need higher floor). |
| **`min_dominant_event_count`** | count of events on `dominant_side` `>= M` | **M = 2** | Reject pseudo-dominance from a single large-notional event. Provider uses notional ratio (a single 1M USD Buy = 100% long); strategy adds the event-count check. |

All three must pass simultaneously. Stage 0R replay must perform a parameter sweep on `(K, N_usd, M)` at the values `(2, 5_000, 1)`, `(3, 10_000, 2)`, `(5, 25_000, 3)`, `(8, 50_000, 3)` and report per-tier FP-rate.

## Event-Trigger Mode

This strategy is event-triggered, not continuous polling.

Allowed:

- The normal engine may call `on_tick(ctx, surface)` on market ticks.
- The strategy evaluates only when `surface.liquidation_pulse` contains a new cluster id or new cluster timestamp for `ctx.symbol`.
- The provider may maintain an in-memory rolling buffer populated by the post-C1 WebSocket event path.

Forbidden:

- REST polling for liquidations.
- PG hot-path reads from `market.liquidations` inside strategy `on_tick`.
- Timer loops that scan all symbols continuously without a new liquidation event.
- Synthetic or stub liquidation events before C1.

Cluster dedupe:

- A cluster is keyed by `(symbol, dominant_side, cluster_window_start_ms, cluster_window_end_ms)`.
- A strategy instance may emit at most one open action per cluster id.
- Per-symbol cooldown after any emitted action is required in implementation and must be counted as a fixed parameter if varied.

## Signal Formula Draft (v0.3 — 5m window + density-floor gate)

For each symbol with a fresh pulse in `LiquidationPulsePanel.pulses`:

```text
let pulse = surface.liquidation_pulse?.pulses.get(ctx.symbol)?;

cluster_notional_5m = pulse.cluster_notional_5m    // provider-supplied
event_count_5m      = pulse.event_count_5m         // provider-supplied
long_notional_5m    = pulse.long_notional_5m
short_notional_5m   = pulse.short_notional_5m

side_dominance_ratio = max(long_notional_5m, short_notional_5m) / cluster_notional_5m

dominant_event_count = match pulse.dominant_side {
    LongLiquidated  => count(recent_events where side == LongLiquidated),
    ShortLiquidated => count(recent_events where side == ShortLiquidated),
    Mixed           => 0,
}

density_ok = event_count_5m         >= min_event_count_5m
          AND cluster_notional_5m   >= min_cluster_notional_5m_usd
          AND dominant_event_count  >= min_dominant_event_count

magnitude_ok = cluster_notional_5m  >= cluster_notional_floor_usd
            AND notional_percentile_24h >= notional_pct_floor
            AND side_dominance_ratio >= side_dominance_floor

cluster_ok = density_ok AND magnitude_ok
quiet_ok   = no same-side liquidation event in the final quiet_window_sec
```

Primary mean-reversion direction:

```text
if cluster_ok and quiet_ok and dominant_side == LongLiquidated:
    expected_dir = +1
elif cluster_ok and quiet_ok and dominant_side == ShortLiquidated:
    expected_dir = -1
else:
    expected_dir = 0
```

### Initial Stage 0R grid (v0.3 — fixed before replay)

- `min_event_count_5m`: 2 / 3 / 5 / 8
- `min_cluster_notional_5m_usd`: 5_000 / 10_000 / 25_000 / 50_000
- `min_dominant_event_count`: 1 / 2 / 3
- `cluster_notional_floor_usd`: 10_000 / 25_000 / 100_000 (was `score_floor`; replaced because IMPL panel exposes notional, not normalized score)
- `notional_pct_floor`: 0.90 / 0.95 / 0.98 versus the symbol's trailing 24h liquidation-cluster distribution
- `side_dominance_floor`: 0.70 / 0.80 / 0.90
- `quiet_window_sec`: 0 / 30 / 60
- holding horizon: 5m primary; 1m and 15m sensitivity cells

These are replay parameters only. They must not become TOML defaults before Stage 0R acceptance and PM authorization. `K_total` formula (see below) is now correspondingly enlarged.

## Stage 0R Replay-First Validation

Stage 0R may start only after C1 PASS + BB/MIT sign-off + real `market.liquidations` rows exist from the corrected item-level identity. Empty liquidation history, synthetic events, or MIT-idempotency-blocked status must emit `eligible_for_demo_canary=false`.

Replay construction:

- Build clusters only from real `market.liquidations` rows produced by the C1-signed path.
- Use as-of joins only: features at decision time may include events at or before `decision_ts`; forward returns start after the decision timestamp.
- Collapse overlapping clusters so one cascade cannot produce many duplicate labels. Because the provider uses a 5m **sliding** window, replay must dedupe by `(symbol, dominant_side, floor(ts/300_000))` plus a 5m cooldown to avoid double-counting near-bucket-edge events.
- Entry model uses the next available tradable mark/mid after the quiet window plus conservative fee/slippage.
- Funding, OI, and TA fields may be reported as diagnostics, but primary eligibility must depend on `LiquidationCascade` plus closed-bar cost/volatility filters only.

Mandatory report fields:

- C1 proof id and BB/MIT sign-off references
- liquidation source topic and symbol set
- side mapping rule and BB-signed side semantics
- pooled and per-symbol cluster `n` plus `n_eff`
- **per-tier breakdown** (high-density / medium-density / low-density tier) — per-pool stratification mandatory in v0.3
- branch breakdown: primary mean-reversion and preregistered momentum sensitivity if inspected
- avg gross/net bps after fee/slippage
- **false-positive rate by density-floor sweep cell** — count of clusters that pass `cluster_ok` but produce forward returns within ±5 bps after fee/slippage (uninformative trigger rate)
- **density-floor filter efficacy** — for each `(K, N_usd, M)` cell, report total raw 5m buckets with any event, count after `min_event_count_5m`, count after `min_cluster_notional_5m_usd`, count after `min_dominant_event_count`
- PSR(0) with skew/kurt adjustment
- DSR with explicit `K_total`
- block-bootstrap CI with 60m primary block and 4h sensitivity
- CSCV PBO using time blocks with purge/embargo
- parameter sensitivity surface, not a single best cell only
- stale/missing/mixed-side/quiet-window/density-floor-fail exclusion counts (5 categories now)
- panel latest times and pulse age distribution
- cost-edge ratio and maker/taker assumption
- baseline lift versus no-liquidation-cluster baseline and versus single-event-bucket noise baseline

`K_total` (v0.3 — enlarged for density-floor sweep):

```text
K_new_primary = N_symbols_inspected
              * 1 primary hypothesis branch
              * 4 min_event_count_5m              (NEW)
              * 4 min_cluster_notional_5m_usd     (NEW; replaces score_floor at 3)
              * 3 min_dominant_event_count        (NEW)
              * 3 cluster_notional_floor_usd      (renamed score_floor)
              * 3 notional_pct_floor
              * 3 side_dominance_floor
              * 3 quiet_window_sec
              * 3 horizons
              = N_symbols_inspected * 11_664

K_new_sensitivity = N_symbols_inspected * 11_664 if the momentum branch is inspected

K_total = K_prior + K_new_primary + K_new_sensitivity + any additional inspected variants
```

PA explicit acknowledgement: the v0.3 K_total is **48× the v0.1 value** (11_664 vs 243). DSR penalty grows; promotion floor (`avg_net_bps ≥ +15`, DSR ≥ 0.95) becomes correspondingly harder. This is intentional: density-floor sweep is real multiple-comparison cost and must be counted.

`K_prior` must be read from comparable `learning.strategy_trial_ledger` rows and signed by MIT. If the query is ambiguous, strict mode must overcount rather than undercount.

Suggested strict query seed, pending MIT approval:

```sql
SELECT count(DISTINCT candidate_key)::int
FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (
    strategy_name ILIKE '%liquidation%'
    OR trial_family ILIKE '%liquidation%'
    OR evidence->>'alpha_source_id' = 'liquidation_cluster_reaction'
  );
```

Promotion floor (v0.3 — density-floor + FP-rate gate added):

- no symbol may be eligible below `n_eff >= 100`
- active side branch must have `n_eff >= 50`
- pooled sample should be `n_eff >= 300` when more than one symbol is inspected
- sample must span at least 7 calendar days
- no single day may contribute more than 25% of eligible clusters
- `avg_net_bps >= +15`
- PSR(0) >= 0.95
- DSR >= 0.95 with explicit `K_total` (v0.3 K_total = N × 11_664)
- PBO <= 0.20
- 95% block-bootstrap lower bound > 0
- adjacent grid cells must form a plateau rather than a single lucky threshold
- primary mean-reversion branch must pass independently; a passing secondary sensitivity does not authorize demo
- **density-floor filter must remove `≥ 60%` of single/double-event 5m buckets** — proves the floor is doing real noise rejection rather than rubber-stamping the provider output
- **false-positive rate (forward return within ±5 bps after fee/slippage)** ≤ `40%` in winning grid cell — proves trigger isn't dominated by noise events
- **per-tier independent promotion**: each density tier (high / medium / low) must independently pass `n_eff` + `avg_net_bps` + PSR/DSR; low-density tier expected to fail and be reported but not promoted

Output is only `eligible_for_demo_canary=true/false` **per tier**. It is not Stage 1 PASS.

## Implementation Boundary

Allowed after C1 PASS and PM dispatch:

1. Source/test parser and dormant writer correction for `allLiquidation.{symbol}` after C1 technical PASS, while keeping production subscriptions disabled.
2. In-memory `LiquidationPulseProvider` feeding `AlphaSurface.liquidation_pulse`.
3. New read-only Stage 0R query/report tooling for `liquidation_cluster_reaction`.
4. Strategy skeleton that declares `LiquidationCascade` and fails closed when missing/stale.

Forbidden in this spec phase:

- subscribing production WS to `allLiquidation*`
- enabling the dormant production liquidation writer/runtime path before MIT idempotency re-sign
- changing risk sizing or leverage
- enabling demo/live trading
- using synthetic liquidation pulses as alpha evidence
- PG hot-path polling from strategy logic
- applying V095 to Linux production DB as part of this source/test packet
- counting the momentum sensitivity branch as mean-reversion eligibility

## Side Effects And Review Focus

PA risk rating for future implementation: high, because this touches Bybit WS topics, AlphaSurface Tier 3 availability, strategy dispatch, replay evidence, and a dormant table.

E2 must review:

1. Fail-closed behavior: missing/stale/mixed `liquidation_pulse` must emit no action and must not fall back to TA.
2. Event-trigger semantics: no REST/PG polling loop and no multiple actions from one cluster id.
3. Replay leakage: cluster construction, quiet window, and forward returns must use strict as-of timestamps.

BB must review:

- topic syntax `allLiquidation.{symbol}`
- side semantics for `S=Buy/Sell`
- rate-limit and control-topic behavior
- production topic-builder guard removal only after C1 PASS

MIT must review:

- schema mapping to `market.liquidations`, including item-level identity `(symbol, ts, side, qty, price)`
- as-of joins and cluster dedupe
- `K_prior`, DSR, PBO, bootstrap, and sample floors

## Acceptance For Spec v0.2 Correction Packet

This v0.2 correction packet may be accepted as source/test only when:

- parser tests cover `allLiquidation.{symbol}` `T/s/S/v/p` for both `Buy` and `Sell`, including fail-closed missing `s` and invalid timestamp cases
- dormant writer code uses `ON CONFLICT (symbol, ts, side, qty, price) DO NOTHING`
- V095 statically proves Guard A/B/C, exact old-PK replacement, side CHECK, and no table/data rewrite
- production `full_subscription_list` still excludes `allLiquidation*`
- no runtime config, deploy, Linux migration apply, strategy action path, risk sizing, leverage, demo, live, or mainnet behavior changes are made

After this packet, W-AUDIT-8c remains blocked for production revival until MIT re-signs the corrected storage/writer identity and PM dispatches a separate runtime task.

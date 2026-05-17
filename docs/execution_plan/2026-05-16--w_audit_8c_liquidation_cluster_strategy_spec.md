# W-AUDIT-8c -- A4-B Liquidation Cluster Reaction Strategy Spec

Date: 2026-05-16
Status: Spec v0.2 / correction-scoped source-test prerequisites / no production runtime authority
Scope: New alpha candidate consuming AlphaSurface Tier 3 `LiquidationCascade`. This revision allows only source/test correction for `allLiquidation.{symbol}` parser/storage identity prerequisites. No production WebSocket subscription change, no runtime config change, no risk/sizing change, no demo/live launch.

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

Primary hypothesis: **post-cascade short-term mean reversion**.

Rationale:

- A liquidation cluster is forced flow, not discretionary informed flow. After the burst decelerates, the first tradable edge is more likely exhaustion/rebound than chasing the same forced flow.
- The survival-first posture prefers reacting after a burst has become stale or decelerating, rather than adding leverage into the middle of an active cascade.
- The strategy can express this with explicit event-trigger guards: fresh pulse required, side dominance required, quiet window preregistered, and no fallback to TA-only signals.

Directional mapping, per BB corrected side-semantics sign-off:

- Dominant `Buy` liquidation payloads (`S=Buy`), interpreted as long liquidations, propose `expected_dir = +1` after the quiet-window guard.
- Dominant `Sell` liquidation payloads (`S=Sell`), interpreted as short liquidations, propose `expected_dir = -1` after the quiet-window guard.
- Ambiguous side, mixed dominance, or unknown Bybit side semantics emits no action.

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

Required consumer fields:

- `recent_events` from the rolling 60s liquidation window
- `cluster_score`
- `dominant_side`
- `snapshot_ts_ms`
- derived `event_count_60s`, `notional_usd_60s = sum(qty * price)`, and side-dominance ratio

Freshness:

- WARN if pulse age is greater than 10s.
- FAIL/no-action if pulse age is greater than 60s.
- FAIL/no-action if `dominant_side = Mixed`, `cluster_score` is below the active threshold, or `ctx.symbol` has no matching event in the current cluster.

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

## Signal Formula Draft

For each symbol with a fresh pulse:

```text
notional_usd_60s = sum(event.qty * event.price for events in rolling 60s)
side_dominance = max(side_notional_usd) / total_notional_usd
cluster_ok = cluster_score >= score_floor
          AND notional_percentile_24h >= notional_pct_floor
          AND side_dominance >= side_dominance_floor
quiet_ok = no same-side liquidation event in the final quiet_window_sec
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

Initial Stage 0R grid, fixed before replay:

- `score_floor`: 0.70 / 0.80 / 0.90
- `notional_pct_floor`: 0.90 / 0.95 / 0.98 versus the symbol's trailing 24h liquidation-cluster distribution
- `side_dominance_floor`: 0.70 / 0.80 / 0.90
- `quiet_window_sec`: 0 / 30 / 60
- holding horizon: 5m primary; 1m and 15m sensitivity cells

These are replay parameters only. They must not become TOML defaults before Stage 0R acceptance and PM authorization.

## Stage 0R Replay-First Validation

Stage 0R may start only after C1 PASS + BB/MIT sign-off + real `market.liquidations` rows exist from the corrected item-level identity. Empty liquidation history, synthetic events, or MIT-idempotency-blocked status must emit `eligible_for_demo_canary=false`.

Replay construction:

- Build clusters only from real `market.liquidations` rows produced by the C1-signed path.
- Use as-of joins only: features at decision time may include events at or before `decision_ts`; forward returns start after the decision timestamp.
- Collapse overlapping clusters so one cascade cannot produce many duplicate labels.
- Entry model uses the next available tradable mark/mid after the quiet window plus conservative fee/slippage.
- Funding, OI, and TA fields may be reported as diagnostics, but primary eligibility must depend on `LiquidationCascade` plus closed-bar cost/volatility filters only.

Mandatory report fields:

- C1 proof id and BB/MIT sign-off references
- liquidation source topic and symbol set
- side mapping rule and BB-signed side semantics
- pooled and per-symbol cluster `n` plus `n_eff`
- branch breakdown: primary mean-reversion and preregistered momentum sensitivity if inspected
- avg gross/net bps after fee/slippage
- PSR(0) with skew/kurt adjustment
- DSR with explicit `K_total`
- block-bootstrap CI with 60m primary block and 4h sensitivity
- CSCV PBO using time blocks with purge/embargo
- parameter sensitivity surface, not a single best cell only
- stale/missing/mixed-side/quiet-window exclusion counts
- panel latest times and pulse age distribution
- cost-edge ratio and maker/taker assumption
- baseline lift versus no-liquidation-cluster baseline

`K_total`:

```text
K_new_primary = N_symbols_inspected
              * 1 primary hypothesis branch
              * 3 score_floor
              * 3 notional_pct_floor
              * 3 side_dominance_floor
              * 3 quiet_window_sec
              * 3 horizons
              = N_symbols_inspected * 243

K_new_sensitivity = N_symbols_inspected * 243 if the momentum branch is inspected

K_total = K_prior + K_new_primary + K_new_sensitivity + any additional inspected variants
```

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

Promotion floor:

- no symbol may be eligible below `n_eff >= 100`
- active side branch must have `n_eff >= 50`
- pooled sample should be `n_eff >= 300` when more than one symbol is inspected
- sample must span at least 7 calendar days
- no single day may contribute more than 25% of eligible clusters
- `avg_net_bps >= +15`
- PSR(0) >= 0.95
- DSR >= 0.95 with explicit `K_total`
- PBO <= 0.20
- 95% block-bootstrap lower bound > 0
- adjacent grid cells must form a plateau rather than a single lucky threshold
- primary mean-reversion branch must pass independently; a passing secondary sensitivity does not authorize demo

Output is only `eligible_for_demo_canary=true/false`. It is not Stage 1 PASS.

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

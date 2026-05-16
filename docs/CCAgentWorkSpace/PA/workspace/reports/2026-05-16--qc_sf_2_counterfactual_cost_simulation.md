# QC-SF-2 Counterfactual Close-Maker Cost Simulation Evidence Packet

Date: 2026-05-16  
Role: PA(default)  
Workgroup: B-5 / QC-SF-2  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`  
Mode: read-only historical DB analysis on `trade-core`; no strategy/runtime/config/spec code changes

## Verdict

**DOES-NOT-SUPPORT** the spec claim of `0.5-2.0 bps net per close attempt` on the current 7d demo close sample.

Pooled eligible demo close fills have estimated expected delta:

```text
mean expected delta = -2.77 bps / close attempt
1000 day-block bootstrap 95% CI = [-3.50, -1.45] bps
```

Interpretation:

- Pooled evidence is powered enough for a directional conclusion (`n=226`, 8 calendar-day blocks).
- `grid_trading` is powered enough and also negative (`n=191`, CI fully below zero).
- `ma_crossover`, `bb_breakout`, and `bb_reversion` are **UNDERPOWERED** individually, but their point estimates do not rescue the pooled result.
- The evidence does not support Phase 1b close-maker-first as a net-positive cost optimization under the current BBO-touch + fallback-delay model.

## Required Inputs Read

- `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`
- `.codex/agents/PA.md`, `.claude/agents/PA.md`, PA profile and PA memory
- QC short re-review §3: `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_v0_3_spec_v1_2_qc_short_re_review.md`
- Phase 1b spec §1.2, §4.3, §11: `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- Entry maker empirical baseline: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--maker_fill_rate_empirical_baseline.md`

Key spec anchors:

- Bybit fee tier-0 assumption: maker `2.0 bps`, taker `5.5 bps`, fee saving cap `3.5 bps`.
- Spec expected net range: `0.5-2.0 bps net per close attempt`.
- Positive maker-first exit reasons: `grid_close_short`, `grid_close_long`, `bb_mean_revert`, `phys_lock_gate4_giveback`, `phys_lock_gate4_stale_roc_neg`, `ma_reverse_cross`, `bw_squeeze`, `pctb_revert`.
- Per-exit timeout: `phys_lock_gate4_giveback=15s`, `phys_lock_gate4_stale_roc_neg=10s`, others `30s`.
- Buffer ticks: `1` for all §4.3 positive reasons.

## Data Window

Query time: `2026-05-16T18:22Z` (`trade-core` DB).  
Window: `now() - interval '7 days'`.  
Universe:

```sql
trading.fills
WHERE engine_mode = 'demo'
  AND entry_context_id IS NOT NULL
  AND strategy_name IN ('grid_trading','ma_crossover','bb_breakout','bb_reversion')
  AND exit_reason IN (<spec §4.3 positive whitelist>)
```

Observed eligible close fills:

| Scope | n | Notional USDT | Side mix |
|---|---:|---:|---|
| pooled | 226 | 17,758.99 | Buy 187 / Sell 39 |
| grid_trading | 191 | 15,055.16 | mostly Buy |
| ma_crossover | 27 | 2,185.02 | low-power |
| bb_reversion | 7 | 454.14 | low-power |
| bb_breakout | 1 | 64.68 | low-power |

Data availability:

- Start BBO/tick invalid or missing: `54 / 226` rows. These are treated as strict-skip-to-market with `p_maker=0`.
- Fallback BBO missing at timeout: `16 / 226` rows. These use fail-closed positive observed slippage as fallback-cost proxy.
- `trading.orders.price` is currently NULL for demo PostOnly entries, so entry calibration reconstructs entry limit from BBO + tick using the same helper semantics instead of reading `orders.price`.

## Model

For each historical market close fill, the real close fill timestamp is used as the close-attempt proxy.

Counterfactual maker quote:

- close Buy: `limit = best_bid - 1 * tick_size`
- close Sell: `limit = best_ask + 1 * tick_size`
- locked/crossed book, missing tick, missing BBO, or `spread_bps > 50`: strict-skip to market, `p_maker=0`

BBO-touch event:

- close Buy fills only if future opposite BBO satisfies `best_ask <= limit` before timeout
- close Sell fills only if future opposite BBO satisfies `best_bid >= limit` before timeout

Queue/recording haircut is calibrated from existing demo PostOnly entry orders (`n=1026`, `valid BBO=644`) because close maker is not implemented yet:

| timeout | valid entry orders | BBO touch | fill within timeout | fill given touch |
|---:|---:|---:|---:|---:|
| 10s | 644 | 329 | 107 | 0.286 |
| 15s | 644 | 372 | 132 | 0.323 |
| 30s | 644 | 426 | 154 | 0.340 |

Per-fill maker probability:

```text
p_maker_i = fill_given_touch(timeout_i) if BBO touched within timeout
          = 0 otherwise
```

Expected delta:

```text
fallback_cost_i = adverse BBO-side move from real market fill price to timeout fallback market price
delta_i = p_maker_i * 3.5 bps - (1 - p_maker_i) * fallback_cost_i
```

This intentionally excludes any extra spread improvement from maker fills and only tests the requested fee saving minus fallback slippage cost.

## Results

### Pooled

| n | BBO valid | BBO touch | mean p_maker | fee component | fallback component | mean delta |
|---:|---:|---:|---:|---:|---:|---:|
| 226 | 172 | 106 | 0.158 | +0.55 bps | -3.32 bps | **-2.77 bps** |

1000 day-block bootstrap:

| Metric | Mean | 95% CI |
|---|---:|---:|
| expected delta bps | -2.77 | `[-3.50, -1.45]` |
| maker probability | 0.158 | `[0.118, 0.184]` |

### Per Strategy

| Strategy | n | BBO valid | BBO touch | mean p_maker | mean fallback cost | mean delta | Bootstrap |
|---|---:|---:|---:|---:|---:|---:|---|
| grid_trading | 191 | 141 | 86 | 0.152 | 4.07 | **-2.99** | supported, CI `[-3.67, -1.79]` |
| ma_crossover | 27 | 24 | 15 | 0.185 | 3.19 | -2.03 | underpowered |
| bb_reversion | 7 | 6 | 4 | 0.184 | 0.84 | -0.03 | underpowered |
| bb_breakout | 1 | 1 | 1 | 0.323 | 2.55 | -0.60 | underpowered |

### Per Exit Reason

| Exit reason | n | BBO valid | BBO touch | mean p_maker | mean fallback cost | mean delta | Bootstrap |
|---|---:|---:|---:|---:|---:|---:|---|
| grid_close_short | 98 | 74 | 43 | 0.149 | 3.54 | **-2.76** | supported, CI `[-3.68, -1.53]` |
| phys_lock_gate4_giveback | 74 | 47 | 24 | 0.105 | 2.89 | -2.04 | supported, CI `[-3.56, +0.35]` |
| bb_mean_revert | 32 | 30 | 25 | 0.266 | 7.35 | -5.18 | underpowered by blocks only (2 blocks) |
| grid_close_long | 13 | 12 | 8 | 0.209 | 5.71 | -3.42 | underpowered |
| ma_reverse_cross | 6 | 6 | 4 | 0.227 | 0.31 | +0.49 | underpowered |
| bw_squeeze | 2 | 2 | 1 | 0.170 | 0.00 | +0.60 | underpowered |
| pctb_revert | 1 | 1 | 1 | 0.340 | 0.00 | +1.19 | underpowered |
| phys_lock_gate4_stale_roc_neg | 0 | 0 | 0 | n/a | n/a | n/a | no data |

## Comparison To Spec Range

Spec expected range: `+0.5` to `+2.0 bps net per close attempt`.

Observed counterfactual estimate:

- Pooled mean: `-2.77 bps`
- Pooled 95% CI: `[-3.50, -1.45]`
- Grid mean: `-2.99 bps`, CI `[-3.67, -1.79]`

Conclusion:

```text
The 7d demo evidence DOES-NOT-SUPPORT the 0.5-2.0 bps net saving range.
```

The negative result is mainly driven by fallback-delay adverse movement. The modeled maker fee component is only about `+0.55 bps` pooled, while the fallback-delay component is about `-3.32 bps`.

## Data Limitations

Facts:

- There is no real close-maker path yet; this is counterfactual, not live A/B evidence.
- `trading.fills.price` provides real close fill price and is available for all sampled rows.
- `market.market_tickers` provides BBO (`best_bid`, `best_ask`) and `market.symbol_universe_snapshots` provides `tick_size`.
- `trading.orders.price` is NULL on current PostOnly entries; calibration therefore reconstructs entry limits from BBO/tick instead of reading order price.

Inference / proxy:

- Fill probability is not directly observable from BBO because BBO does not expose queue position or depth at the limit price. I used a conservative empirical haircut: actual entry fill-within-timeout among observed BBO-touch cases.
- Real market-fill timestamp is used as close-attempt timestamp. If dispatch-to-fill latency differs materially for market closes, the counterfactual BBO alignment can shift.
- Fallback market price uses timeout BBO side. Missing timeout BBO rows use a fail-closed positive observed-slippage proxy.
- The result is demo-only. LiveDemo was inspected for context but not included in this required demo packet.

Power:

- Pooled and grid estimates are powered for 1000 block-bootstrap.
- MA and BB per-strategy cells are underpowered.
- Several per-exit_reason cells are underpowered; `phys_lock_gate4_stale_roc_neg` had zero eligible demo rows.

## Commands Run

Representative commands:

```bash
sed -n '1,220p' AGENTS.md
sed -n '1,260p' CLAUDE.md
sed -n '1,260p' TODO.md
sed -n '1,260p' .codex/MEMORY.md
sed -n '1,260p' .codex/agents/PA.md
sed -n '1,260p' .claude/agents/PA.md
git status --short --branch
git stash list
sed -n '37,68p' docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_v0_3_spec_v1_2_qc_short_re_review.md
sed -n '28,44p' docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md
sed -n '190,244p' docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md
sed -n '1,360p' docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--maker_fill_rate_empirical_baseline.md
ssh trade-core 'ls -l /tmp/openclaw/runtime_secrets/openclaw_database_url'
ssh trade-core 'psql "$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url)" -Atc "SELECT current_database(), current_user, now();"'
ssh trade-core 'psql "$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url)" ... information_schema ...'
ssh trade-core 'python3 - <<PY ... /private/tmp/qc_sf2_summary.py base64 payload ... PY'
```

Scratch artifacts only:

- `/private/tmp/qc_sf2_counterfactual.py`
- `/private/tmp/qc_sf2_summary.py`

No repo source code, TODO, memory, spec, runtime config, strategy code, Rust code, SQL migration, DB rows, deploy state, commit, push, stash, or clean operation was modified.

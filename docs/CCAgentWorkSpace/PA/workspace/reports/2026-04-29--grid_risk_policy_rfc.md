# RFC — Grid Risk Policy For LiveDemo Lifecycle Drift

Date: 2026-04-29 21:45 CEST

## Decision Needed

Approve a bounded live_demo grid policy change. Recommended first wave:

1. Copy demo's current robust-negative `grid_trading.blocked_symbols` into `settings/strategy_params_live.toml`.
2. Reduce live grid density from `grid_levels = 10` to `grid_levels = 7`.
3. Do not change `risk_config_live.toml` trailing or partial TP in this wave.

This is intended to reduce repeated same-symbol grid open/close churn while preserving the ability to close or reduce existing positions.

## Current Evidence

Latest deployed state: `trade-core` HEAD `c48581d`; runtime code `854cae1`; `[38]` is no longer silent-dead.

`[38] grid_trading_lifecycle_drift` after W1-T2 deployment:

| mode | n | p50 lifetime | fee_burn | re-entry rate |
|---|---:|---:|---:|---:|
| demo | 40 | 4.8 min | 0.24 | 0.41 |
| live_demo | 98 | 1.7 min | 0.45 | 0.72 |

Verdict: `FAIL` because live_demo re-entry rate is above 0.70, with lifetime_ratio 0.35 and re-entry delta 0.31.

Important correction: the current live_demo close reasons are mostly `strategy_close:grid_close_*`, not trailing stops. 24h close reason counts:

| mode | reason | n |
|---|---|---:|
| live_demo | `strategy_close:grid_close_short` | 64 |
| live_demo | `strategy_close:grid_close_long` | 39 |
| demo | `risk_close:phys_lock_gate4_giveback` | 31 |
| demo | `strategy_close:grid_close_short` | 20 |

So the active failure is grid-level crossing churn, not primarily risk trailing.

## Current Config Delta

| lever | demo | live/live_demo |
|---|---:|---:|
| `strategy_params_*.[grid_trading].grid_levels` | 10 | 10 |
| `strategy_params_*.[grid_trading].blocked_symbols` | 11 symbols | none |
| `risk_config_*.[agent].trailing_activation_pct` | 0.8 | 0.5 |
| `risk_config_*.[agent].trailing_distance_pct` | 3.5 | 2.0 |
| `risk_config_*.[agent].partial_tp_enabled` | false | true |

Runtime code audit: `partial_tp_enabled` / `partial_tp_levels` are currently schema + validation only. There is no Rust runtime consumer outside config validation, so disabling partial TP is not expected to change current fills.

## Option Comparison

### Option A — Widen live trailing from 2.0% toward demo 3.5%

Effect:

- Would align live risk trailing with demo's looser stop behavior.
- Could reduce `risk_close:TRAILING STOP` rows when those are active.

Problems:

- Current `[38]` sample is dominated by `strategy_close:grid_close_*`, not trailing stops.
- Healthcheck `[6]` shows only 2 trailing-stop fires in 7d, so this is not the observed driver.
- This changes the live risk envelope and could increase adverse excursion without addressing grid crossing frequency.

Verdict: not first wave. Keep as second-order alignment if future `[38]` or close-reason data shows trailing-driven exits.

### Option B — Pause robust-negative grid cells

Effect:

- Demo already blocks new grid entries for robust-negative cells.
- Live/live_demo currently lacks this list, creating an obvious env delta.
- Low risk because `blocked_symbols` suppresses new grid opens only; close/reduce paths remain enabled.

Current robust-negative list from runtime `settings/edge_estimates.json` (`n>=30`, `shrunk_bps<0`):

`BSBUSDT`, `PRLUSDT`, `ZBTUSDT`, `FARTCOINUSDT`, `SOLUSDT`, `DOGEUSDT`, `GALAUSDT`, `ENAUSDT`, `AAVEUSDT`, `ORCAUSDT`, `PENGUUSDT`.

Limit:

- This will not fully fix the current 24h churn. The highest live_demo lifecycle symbols are `TAOUSDT`, `PUMPFUNUSDT`, `BIOUSDT`, `NAORISUSDT`, and `LYNUSDT`; most are not yet robust-negative by the `n>=30` rule.

Verdict: approve. It closes a clear demo/live policy gap and is safe, but it is not sufficient alone.

### Option C — Reduce live grid levels

Effect:

- Directly targets the dominant observed mechanism: grid level crossing churn.
- Current `grid_levels=10` means more grid boundaries and more open/close transitions in noisy ranges.
- Lowering to 7 widens level spacing materially while keeping grid behavior intact.

Tradeoff:

- Fewer entries means lower sample generation and fewer learning rows.
- Too low a value can underfit the intended grid behavior; `grid_levels=7` is a conservative first step versus jumping to 5 or disabling the strategy.

Verdict: approve as the primary first-wave lever. Proposed value: `grid_levels = 7` in `settings/strategy_params_live.toml`.

### Option D — Disable partial TP

Effect:

- Conceptually aligns live with demo (`partial_tp_enabled=false`).

Problem:

- Code audit shows `partial_tp_enabled` has no current runtime consumer. It is validation/schema only.
- Disabling it would mostly be documentation/config hygiene, not a fix for `[38]`.

Verdict: do not use as an operational lever in this wave. Optional cleanup later: set live to false for config clarity, but do not expect metric movement.

## Recommended First Wave

Change only `settings/strategy_params_live.toml`:

```toml
[grid_trading]
grid_levels = 7
blocked_symbols = [
  "BSBUSDT",
  "PRLUSDT",
  "ZBTUSDT",
  "FARTCOINUSDT",
  "SOLUSDT",
  "DOGEUSDT",
  "GALAUSDT",
  "ENAUSDT",
  "AAVEUSDT",
  "ORCAUSDT",
  "PENGUUSDT",
]
```

Leave these unchanged for now:

- `risk_config_live.toml [agent].trailing_distance_pct = 2.0`
- `risk_config_live.toml [agent].trailing_activation_pct = 0.5`
- `risk_config_live.toml [agent].partial_tp_enabled = true`

Rationale: fix the levers that actually map to the observed close path first. Avoid broad risk-envelope changes until `[38]` shows whether grid density and blocked cells are sufficient.

## Deployment And Verification

Preferred deployment: TOML change + restart with `restart_all.sh --rebuild --keep-auth` or an audited `update_strategy_params` IPC patch if operator wants runtime-only testing first. TOML persistence is preferred for reproducibility.

Acceptance:

- 2h smoke: no startup regression; `[22]` stays PASS; no spike in missing order/fill consistency.
- 6h: `[38]` no longer hard-fails on re-entry, or shows a clear drop from 0.72.
- 24h: target live_demo re-entry rate <= 0.60 and lifetime_ratio >= 0.50. This exits FAIL territory even if still WARN.
- 24h/48h: fee_burn trends down versus current 0.45 and remains below the absolute FAIL threshold 1.5.

Rollback:

- Restore `grid_levels = 10`.
- Remove `blocked_symbols` from live, or keep it if only grid density causes undesired side effects.

## Open Questions

- If live mainnet is later bound to `strategy_params_live.toml`, this decision must be re-reviewed before mainnet execution. Current runtime is live_demo on Bybit Demo endpoint, but the file name and governance surface are still live.
- If `[38]` remains FAIL after grid density reduction, next candidate is a more aggressive `grid_levels = 5` or a per-symbol extension of `blocked_symbols` based on 24h churn symbols, not trailing/partial TP.

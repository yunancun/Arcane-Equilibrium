# FA-PHANTOM-1 FUP-7: 90% margin crisis threshold decision

- **Status**: Awaiting operator decision
- **Owner**: Operator
- **Prepared by**: Claude (PM+Conductor)
- **Date**: 2026-04-14
- **Context**: Post FA-PHANTOM-1 fix (commit `7eef87f`), the 90% margin crisis check in `fast_track.rs` is architecturally near-unreachable under current runtime config. Need operator call on whether to lower, delete, or keep as last-resort fail-safe.

## The check in question

`rust/openclaw_engine/src/fast_track.rs:40`:

```rust
// Margin crisis: >90% utilization
if margin_utilization_pct >= 90.0 {
    return FastTrackAction::CloseAll;
}
```

Where `margin_utilization_pct = (total_notional / leverage) / balance × 100` — **true margin usage** (post-fix semantics).

## Why it's now (near-)unreachable

Current runtime config (`/tmp/openclaw/pipeline_snapshot_paper.json`):

| Knob | Value |
|---|---|
| `leverage_max` | 100.0 |
| `total_exposure_max_pct` | 200.0 |
| `position_size_max_pct` | 50.0 |
| `open_positions_max` | 25 |

Maximum achievable margin util under these limits:

```
max_notional    = balance × total_exposure_max_pct/100  = balance × 2.0
max_margin_used = max_notional / leverage_max            = balance × 0.02
max_margin_util = max_margin_used / balance × 100       = 2%  ← ceiling
```

**2% ≪ 90%.** The check cannot fire while other risk limits hold.

## When it WOULD fire

Only under non-current configs:

| leverage | exposure cap | margin at cap | fires? |
|---|---|---|---|
| 100 | 200% | 2% | no |
| 20 | 100% (Rust default) | 5% | no |
| 10 | 300% | 30% | no |
| 1 (cash) | 100% | 100% | **yes** |
| 2 | 200% | 100% | **yes** |

→ Effective only at cash / near-cash leverage regimes.

## Decision options

### A. Lower threshold to 50%

Protects mid-leverage accounts earlier.

- **Pro**: catches real risk under configs like `leverage=5, exposure=300%` (max margin 60%).
- **Con**: re-opens false-positive risk. With `position_size_max_pct=50%` and cash-like leverage, stacking 2 positions can hit 50% margin legitimately and fire CloseAll on Normal risk level — the exact FA-PHANTOM-1-shaped failure mode, just at a different threshold.
- **Con**: arbitrary number; would need per-regime calibration.

### B. Delete the check entirely

Rely on `total_exposure_max_pct` + `leverage_max` (enforced upstream in Guardian) + Phase 1 orphan handler + CircuitBreaker escalation for over-leverage protection.

- **Pro**: simplest; eliminates "dead code masquerading as safety" (E2's phrasing).
- **Pro**: other layers (Guardian pre-trade + Phase 6 reconciler escalation) already cover the actual leverage-limit scenarios.
- **Con**: removes a defence-in-depth layer. If someone changes config to cash + high exposure, there's no last-resort CloseAll.

### C. Keep 90% as last-resort fail-safe (**recommended**)

Accept that under current config it can't fire; preserve it for cash/low-leverage configs.

- **Pro**: cheap (one compare per tick), correct semantics post-fix ("we're about to be liquidated, flatten"), zero false-positive risk under any sane config with leverage ≥ 2 and exposure ≤ 100%.
- **Pro**: no code change, no new tests, no redeploy needed.
- **Con**: code reads as dead under current config → must be documented so future readers don't either (a) try to "fix" it by lowering the threshold or (b) assume it's providing protection it isn't.

### Recommendation: **C** with two clarifying actions

1. Add a comment at `fast_track.rs:39-41` explaining the check is intentionally configured-out under current leverage, and under what config it would fire.
2. Do NOT add a test that asserts the check fires today — it shouldn't, and adding one pins the wrong invariant.

Estimated effort for C: ~10 lines of comment. No rebuild required until normal next deploy.

## Cross-refs

- `memory/project_fa_phantom_bug.md` — root cause + fix
- `TODO.md` §255 FA-PHANTOM-1 FUP list
- `rust/openclaw_engine/src/fast_track.rs:24-55` — `evaluate_fast_track`
- `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:117-136` — post-fix margin_util calculation

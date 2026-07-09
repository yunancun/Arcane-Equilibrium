# W-AUDIT-8b Early RED Pivot Note

**Date**: 2026-05-16T22:34Z  
**Role**: PM(default)  
**Scope**: read-only early pre-gate sweep interpretation; no deploy, no DB schema write, no runtime restart, no auth mutation, no paper/live/mainnet enablement.

## Verdict

W-AUDIT-8b should no longer be treated as the near-term unlock path.

The early pre-gate v0.3 sweep is not a formal Stage 0R sign-off because panel coverage is still below the preregistered 7d empirical gate. It is still strong enough for planning: all four z-cells reject, and the observed failure mode is not close to recoverable by waiting another day.

Formal 7d rerun remains useful as governance closure evidence, not as the main critical path.

## Evidence

Early artifact:

- `trade-core:/tmp/openclaw/w_audit_8b_stage0r_early_pre_gate_v0_3_20260516_222301_pa.json`

Current panel state at run time:

- funding/OI panel coverage: about 5.95d
- symbols: 25
- strict funding-skew `K_prior`: 0
- relaxed funding-related `K_prior`: 9
- distinct funding cycles: 31

Sweep result:

- `eligible_for_demo_canary=false`
- `sweep_eligibility=REJECT`
- `promotion_ready_branch_count=0`
- `diagnostic_pass_branch_count=0`
- `PBO=0.75` versus required `<=0.20`

Best branch/cell remains too sparse:

| z cell | branch | n | n_eff | avg_net_bps | status |
|---|---|---:|---:|---:|---|
| 1.0 | crowded_short_squeeze | 7 | 1 | +116.78 | reject |
| 1.2 | crowded_short_squeeze | 7 | 1 | +116.78 | reject |
| 1.5 | crowded_short_squeeze | 7 | 1 | +116.78 | reject |
| 2.0 | crowded_short_squeeze | 7 | 1 | +116.78 | reject |

Relaxing to `z=1.0` only lifts `crowded_long_fade` to `n=9 / n_eff=1`, still far below the branch, pooled, per-symbol, cycle, day-concentration, DSR, PBO, and plateau requirements.

## Interpretation

The 8b problem is signal sparsity and concentration, not simply panel age. Waiting until 7d is unlikely to flip the verdict because the extra data is expected to add only a few candidate signals, not the hundreds of effective samples required for promotion readiness.

This supports treating W-AUDIT-8b as:

1. formal rerun / closure evidence after panel >= 7d;
2. tombstone or pivot candidate if the formal rerun matches the early result;
3. not a blocker worth idle-waiting on for alpha recovery.

## Recommended Path

Immediate priority stays on C1 -> W-AUDIT-8c:

- C1 v2 proof PID `377531` is `IN_PROGRESS_HEALTHY`.
- Started: `2026-05-16T14:56:16Z`.
- Target complete: `2026-05-17T14:56:16Z`.
- At `2026-05-16T22:34:06Z`, remaining time was `58,929s` (~16h 22m).
- Current C1 health: `connection_errors=0`, `reconnect_attempts=0`, `uptime_ratio=0.999976`.

After C1 completes:

1. BB + MIT sign-off if the 24h proof remains clean.
2. If C1 PASS, prioritize W-AUDIT-8c Liquidation Cluster Reaction.
3. If C1 FAIL, pivot to W-AUDIT-8a Phase C2/C3 orderflow/spread microstructure instead of waiting on 8b.
4. Run W-AUDIT-8b formal 7d rerun around `2026-05-18T00:30Z` for closure evidence only unless it unexpectedly changes materially.

## Boundaries

- Do not treat this early sweep as official Stage 0R PASS/FAIL sign-off.
- Do not start Stage 1 Demo from this artifact.
- Do not enable paper.
- Do not subscribe production `allLiquidation.*` beyond the approved C1 proof lane.
- Do not deploy Phase 1b / V094 from this note alone.

PM SIGN-OFF: CONDITIONAL — use early RED for planning/pivot; keep formal 7d rerun for governance closure.

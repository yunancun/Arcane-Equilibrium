# W-AUDIT-8b Formal Closure Prep

**Date**: 2026-05-17T07:19Z  
**Role**: PM(default)  
**Status**: PREP READY / FORMAL RERUN WAITS PANEL >= 7D  
**Related early note**: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--w_audit_8b_early_red_pivot_note.md`

## Current Decision

Do not idle-wait on W-AUDIT-8b as an unlock path.

The early v0.3 pre-gate sweep rejected all four z cells and found zero promotion-ready or diagnostic-pass branches. Formal rerun still matters for governance closure, but current planning should proceed as if W-AUDIT-8b is a tombstone/pivot candidate.

## Early Evidence Recap

Artifact:

- `trade-core:/tmp/openclaw/w_audit_8b_stage0r_early_pre_gate_v0_3_20260516_222301_pa.json`

Result:

- `eligible_for_demo_canary=false`
- `sweep_eligibility=REJECT`
- `promotion_ready_branch_count=0`
- `diagnostic_pass_branch_count=0`
- `PBO=0.75`

Best observed branch remains sparse:

| z cell | branch | n | n_eff | avg_net_bps | status |
|---|---|---:|---:|---:|---|
| 1.0 | crowded_short_squeeze | 7 | 1 | +116.78 | reject |
| 1.2 | crowded_short_squeeze | 7 | 1 | +116.78 | reject |
| 1.5 | crowded_short_squeeze | 7 | 1 | +116.78 | reject |
| 2.0 | crowded_short_squeeze | 7 | 1 | +116.78 | reject |

Interpretation: the failure is signal sparsity/concentration, not simply panel age.

## Formal Rerun Gate

Formal W-AUDIT-8b Round 2 rerun should wait until:

1. `funding span_days >= 7.0`
2. `oi span_days >= 7.0`
3. `funding sym_count = 25`
4. `oi rows >= funding rows * 0.95`
5. strict funding-skew `K_prior = 0`
6. `distinct_cycles_in_panel >= 21`

Expected window:

- panel reaches 7d around `2026-05-17T23:30Z`
- recommended rerun time: `2026-05-18T00:30Z`

## Pre-Rerun Assertion Commands

Run on Mac via ssh:

```bash
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -A -F'|' -c \"
SELECT
  to_timestamp(MIN(snapshot_ts_ms)/1000) AS funding_min_ts,
  to_timestamp(MAX(snapshot_ts_ms)/1000) AS funding_max_ts,
  EXTRACT(EPOCH FROM (to_timestamp(MAX(snapshot_ts_ms)/1000) - to_timestamp(MIN(snapshot_ts_ms)/1000)))/86400 AS span_days,
  COUNT(*) AS total_rows,
  COUNT(DISTINCT symbol) AS sym_count
FROM panel.funding_rates_panel;\""

ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -A -F'|' -c \"
SELECT
  to_timestamp(MIN(snapshot_ts_ms)/1000) AS oi_min_ts,
  to_timestamp(MAX(snapshot_ts_ms)/1000) AS oi_max_ts,
  EXTRACT(EPOCH FROM (to_timestamp(MAX(snapshot_ts_ms)/1000) - to_timestamp(MIN(snapshot_ts_ms)/1000)))/86400 AS span_days,
  COUNT(*) AS oi_rows,
  COUNT(DISTINCT symbol) AS sym_count
FROM panel.oi_delta_panel;\""

ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -A -F'|' -c \"
SELECT count(DISTINCT candidate_key)::int AS k_prior_strict_funding_skew
FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (strategy_name ILIKE '%funding_skew%'
       OR trial_family ILIKE '%funding_skew%'
       OR candidate_key ILIKE '%funding_skew%');\""

ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -A -F'|' -c \"
SELECT COUNT(DISTINCT next_funding_ms)::int AS distinct_cycles_in_panel
FROM panel.funding_rates_panel
WHERE next_funding_ms IS NOT NULL;\""
```

## Formal Rerun Command

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && \
  TS=\$(date -u +%Y%m%d_%H%M%S) && \
  PGPASSWORD='<REDACTED>' \
  OPENCLAW_DATABASE_URL=postgresql://trading_admin@localhost:5432/trading_ai \
  OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=600000 \
  timeout 3600 python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py \
    --sweep --z-cells 1.0,1.2,1.5,2.0 --window-days 7 \
    --format json \
    --out /tmp/openclaw/w_audit_8b_stage0r_round2_v0_3_\${TS}_pa.json \
    > /tmp/openclaw/w_audit_8b_stage0r_round2_v0_3_\${TS}.log 2>&1 && \
  echo /tmp/openclaw/w_audit_8b_stage0r_round2_v0_3_\${TS}_pa.json"
```

## Expected Report

If formal rerun matches early RED:

1. Write `docs/CCAgentWorkSpace/PA/workspace/reports/<date>--w_audit_8b_round2_formal_red_verdict.md`.
2. Copy a concise operator note to `docs/CCAgentWorkSpace/Operator/`.
3. Recommend W-AUDIT-8b tombstone or demotion to dormant diagnostic.
4. Keep C1 -> W-AUDIT-8c as the active alpha source push.
5. Do not use W-AUDIT-8b as a Phase 1b deploy unlock.

If formal rerun unexpectedly improves materially:

1. Stop and dispatch QC + MIT + BB review before any strategy/demo decision.
2. Treat the early note as superseded by the formal artifact only after reviewers sign the delta.
3. Do not start Stage 1 Demo directly from the formal artifact; Stage 0R output remains only `eligible_for_demo_canary=true/false`.

## Boundaries

- No DB writes beyond `/tmp/openclaw` report artifacts.
- No production SQL migration.
- No runtime restart.
- No paper/live/mainnet enablement.
- No Phase 1b deploy from W-AUDIT-8b closure alone.

PM STATUS: FORMAL CLOSURE PREP READY.

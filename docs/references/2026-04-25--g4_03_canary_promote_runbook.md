# G4-03 Canary Auto-Promote Runbook

**Date**: 2026-04-25
**Owner**: Operator + MIT (ML)
**Phase**: A (schema-only landing — DEFAULT-OFF)
**Spec**: `docs/references/2026-04-23--model_canary_promotion_rules_draft.md`

---

## What this is

Phase A of the auto-promote cron deferred by INFRA-PREBUILD-1 Part B.
A scanner that reads `learning.model_registry` rows in `canary_status='shadow'`
or `'promoting'`, applies the eligibility gates from the draft, and either
prints a `Hold | Promote | Retire` decision (dry-run) OR calls the
existing `model_registry.transition_canary_status` state machine.

**DEFAULT-OFF**: behind env var `OPENCLAW_AUTO_PROMOTE_ENABLED=1`. Operator
must explicitly opt in to apply transitions. Dry-run is always safe.

---

## When to use

- After enabling Combine Layer shadow exit (`exit.shadow_enabled=true`)
  and waiting for `learning.decision_shadow_exits` to accumulate observations.
- When reviewing whether a freshly-trained shadow model meets promotion criteria.
- When checking whether a `promoting` row is healthy enough for `production`.
- As a pre-cron sanity check before automated enforcement (Phase 4).

---

## Files

| Path | Purpose |
|---|---|
| `program_code/ml_training/canary_promoter.py` | Core evaluator + scanner |
| `program_code/ml_training/tests/test_canary_promoter.py` | Pytest cases |
| `helper_scripts/db/canary_promote_runner.py` | CLI runner |

---

## Quick start

### Preview (always safe)

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && \
  program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python3 \
  helper_scripts/db/canary_promote_runner.py"
```

Sample output:

```
Canary promote runner — mode=DRY-RUN ts=2026-04-25T03:55:00+00:00
Thresholds: CanaryThresholds(shadow_min_age_days=1.0, ...)

id    strategy        engine  q     from       decision  →     reason
----  --------------  ------  ----  ---------  --------  ----  -----------------------
1     grid_trading    demo    q10   shadow     promote   prom  shadow eligible: ...
2     grid_trading    demo    q50   shadow     promote   prom  shadow eligible: ...
3     grid_trading    demo    q90   shadow     promote   prom  shadow eligible: ...

Summary (3 rows): hold=0 | promote=3
```

### Apply (requires env var + operator review)

```bash
# Operator must explicitly opt-in via env var
ssh trade-core "cd ~/BybitOpenClaw/srv && \
  OPENCLAW_AUTO_PROMOTE_ENABLED=1 \
  program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python3 \
  helper_scripts/db/canary_promote_runner.py --apply"
```

The runner refuses `--apply` without the env var — exits 0 with stderr
warning.

### Verbose mode

```bash
... canary_promote_runner.py --verbose
```

Prints all reasons + metrics dict per row (useful for debugging gate failures).

---

## Threshold overrides

Thresholds are PLACEHOLDERS from the draft. Tune via env vars before running:

| Env var | Default | What it gates |
|---|---|---|
| `OPENCLAW_CANARY_SHADOW_MIN_AGE_DAYS` | 1.0 | shadow row age before eligibility |
| `OPENCLAW_CANARY_SHADOW_MIN_SAMPLES` | 200 | training_sample_size minimum |
| `OPENCLAW_CANARY_PROMOTING_MIN_OBS` | 500 | observations in window |
| `OPENCLAW_CANARY_PROMOTING_MIN_AGE_DAYS` | 7.0 | promoting row min age |
| `OPENCLAW_CANARY_PROMOTING_MIN_AGREEMENT` | 0.60 | full-window agreement % |

Example — tighten promoting agreement to 75%:

```bash
OPENCLAW_CANARY_PROMOTING_MIN_AGREEMENT=0.75 \
  helper_scripts/db/canary_promote_runner.py
```

---

## Eligibility gates implemented

Per draft §Phase-gated promotion criteria:

### shadow → promoting
- verdict ∈ {`should_ship`, `shadow_only`}
- `training_sample_size >= 200`
- row age ≥ 1 day (operator review window)

### promoting → production
- row age ≥ 7 days
- ≥500 observations in `learning.decision_shadow_exits` for the
  same `(strategy_name, engine_mode)` within the 7d window
- agreement ratio (`disagreed=FALSE` / total) ≥ 60%

### promoting → rejected (auto-retire)
- row age ≥ 3 days
- 3-day-window agreement < 40% with ≥1 observation

### Terminal states
- `production` / `retired` / `rejected` → no-op

### Not yet implemented (Phase B)
- Brier score gate (need shadow brier instrumentation)
- Per-dim PSI feature drift gate (need drift_detector.rs hook)
- Per-strategy threshold overrides (YAML)
- SIGHUP after promote (Rust reader hot-reload)
- Cron driver / alert channel

---

## Operator playbook

**Daily (manual)**: Run `--dry-run` to preview. If any rows show `promote`
or `retire`, review the reasons + metrics, then either:

1. Trust the evaluator → set env var + run `--apply`.
2. Investigate the underlying data (see "Diagnostic queries" below).
3. Manually invoke `POST /api/v1/ml/model_promote` for surgical control.

**Weekly**: Audit recent transitions:

```sql
SELECT id, strategy, engine_mode, quantile, canary_status,
       promoted_at, retired_at, retirement_reason
FROM learning.model_registry
WHERE updated_at > NOW() - INTERVAL '7 days'
ORDER BY updated_at DESC;
```

---

## Diagnostic queries

### Current shadow + promoting rows
```sql
SELECT id, strategy, engine_mode, quantile, canary_status, verdict,
       train_date, training_sample_size, created_at
FROM learning.model_registry
WHERE canary_status IN ('shadow', 'promoting')
ORDER BY created_at DESC;
```

### Shadow observations for a (strategy, engine_mode) over past 7 days
```sql
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE disagreed = FALSE) AS agreed,
       (COUNT(*) FILTER (WHERE disagreed = FALSE))::float / NULLIF(COUNT(*), 0)
         AS agreement_pct
FROM learning.decision_shadow_exits
WHERE strategy_name = 'grid_trading'
  AND engine_mode = 'demo'
  AND ts >= NOW() - INTERVAL '7 days';
```

### Audit log of promote API calls
See `change_audit_log` (the `/api/v1/ml/model_promote` route writes there).

---

## Phase B / Phase 4 deliverables

Per draft §Auto-promote cron, items deferred to Phase 4 second-half:

1. Brier score baseline + drift gate
2. Feature PSI gate (per Track P 7-dim)
3. Per-strategy YAML override
4. Cron driver (systemd timer or `cron`)
5. Alert channel for auto-retire (operator notification)
6. SIGHUP to Rust engine after `production` transition (currently
   requires manual restart for the Rust reader to pick up new artifact)

---

## Related

- Draft: `docs/references/2026-04-23--model_canary_promotion_rules_draft.md`
- Schema: `sql/migrations/V023__model_registry.sql`
- Python writer: `program_code/ml_training/model_registry.py`
- Rust reader: `rust/openclaw_engine/src/ml/registry.rs`
- API: `app/ml_routes.py` (`POST /api/v1/ml/model_promote`)
- Healthcheck: `helper_scripts/db/passive_wait_healthcheck.py [9]`

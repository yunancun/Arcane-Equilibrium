# MAG-082 24h Canary Validation Checklist

Date: 2026-05-07
Status: checklist only, no canary run
Review role: PM-local E4-style validation design

## Purpose

Define the 24h evidence checklist required before any M8 canary can be treated
as successful. This document does not start a canary and does not authorize
primary/live autonomy.

The checklist is complete only when every canary decision in the window can be
reconstructed from durable evidence:

StrategySignal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan ->
Decision Lease / idempotency -> ExecutionReport.

For non-submit decisions, the chain must prove why no ExecutionPlan or
ExecutionReport was allowed.

## Boundary

MAG-082 is validation design only:

- no runtime flag change;
- no rebuild, restart, deploy, or DB write;
- no live authorization renew/revoke;
- no Executor shadow unlock;
- no OpenClaw proposal/approval route;
- no trading authority change.

## Window Header

Every 24h canary report must start with this immutable header:

| Field | Required value |
|---|---|
| Canary name | Human-readable window name |
| Git commit | Mac, origin, and Linux commit SHA |
| Engine scope | `demo` or `live_demo` for Stage 2 |
| Strategy/symbol scope | Exact allowlist |
| Start time UTC | ISO-8601 |
| Planned stop time UTC | ISO-8601 |
| Actual stop time UTC | ISO-8601 or `running` |
| Flags | Exact values for event-store, spine, scanner authority, lease router, executor shadow, H-state, cost-edge |
| Rollback owner | Human operator present or on-call |
| Rollback commands | Exact commands or route payloads |
| Live auth state | Must show no unexpected true-live authorization anomaly |
| OpenClaw route posture | Must show read-only allowlist only |

Missing header fields are a NO-GO for accepting the 24h window.

## Entry Checklist

Complete before the 24h clock starts:

- MAG-080 policy exists and is the active cutover policy.
- MAG-081 risk review exists and no new flag/control surface has been added
  since that review without an addendum.
- Mac, origin, and Linux source commits match.
- Linux worktree is clean.
- Runtime owner records exact flag values.
- OpenClaw active allowlist is still only:
  - `GET /api/v1/openclaw/status`
  - `GET /api/v1/openclaw/self-state`
- No OpenClaw route can submit/cancel/close/mutate live config/mutate risk
  config/read secrets/restart/deploy.
- Executor `shadow_mode=false` is not enabled for `live` unless a separate
  operator-approved live 5-gate review explicitly says so.
- Stage 2 scope is demo/live_demo only.
- Rollback bundle from MAG-081 is ready.

## Required Evidence Files

Store the final 24h evidence under:

`docs/CCAgentWorkSpace/PM/workspace/reports/YYYY-MM-DD--agenttodo_mag082_24h_canary_validation_<window>.md`

The report must include:

- window header;
- operator checklist copy;
- query outputs or screenshots for every SQL/check below;
- watchdog status at start and end;
- passive healthcheck summary at start and end;
- rollback decision, even if rollback was not needed;
- PASS/WARN/FAIL verdict.

## Decision Chain Evidence

For every canary decision, capture these identifiers when present:

| Field | Required for | Source |
|---|---|---|
| `signal_id` | Every strategy-originated decision | `agent.decision_objects` `strategy_signal` |
| `decision_id` | Every tactical decision | `strategist_decision` payload/object |
| `verdict_id` + `verdict_version` | Every allowed/modified/rejected decision | `guardian_verdict` payload/object |
| `order_plan_id` | Every executable decision | `execution_plan` payload/object |
| `lease_id` | Every real submit candidate | `execution_plan.lease_id` and lease audit evidence when enabled |
| `idempotency_key` | Every execution plan intended for submit | `execution_plan.payload` and `agent.execution_idempotency_keys` |
| `execution_report_id` | Every submit/fill/failure report | `execution_report` object |
| `exchange_order_id` or failure reason | Every non-shadow submit attempt | `execution_report.payload` |

Non-submit decisions must prove the absence of an ExecutionPlan or
ExecutionReport is intentional, not a writer failure.

## SQL Checklist

Replace `:start_ts`, `:end_ts`, and `:engine_scope` with the window values.

### 1. Object Coverage

```sql
SELECT object_type, count(*)::int AS rows
FROM agent.decision_objects
WHERE created_at >= :start_ts
  AND created_at < :end_ts
  AND engine_mode = ANY(:engine_scope)
GROUP BY object_type
ORDER BY object_type;
```

Expected: counts are consistent with canary activity. Zero rows during an
active canary are FAIL unless the canary explicitly had no decisions.

### 2. Complete Signal To Plan Lineage

```sql
WITH sig AS (
  SELECT object_id, signal_id, engine_mode, symbol, strategy
  FROM agent.decision_objects
  WHERE object_type = 'strategy_signal'
    AND created_at >= :start_ts
    AND created_at < :end_ts
    AND engine_mode = ANY(:engine_scope)
),
chain AS (
  SELECT
    sig.object_id AS signal_object_id,
    sig.signal_id,
    dec.object_id AS decision_object_id,
    dec.decision_id,
    verdict.object_id AS verdict_object_id,
    verdict.verdict_id,
    verdict.verdict_version,
    plan.object_id AS plan_object_id,
    plan.order_plan_id,
    plan.lease_id
  FROM sig
  LEFT JOIN agent.decision_edges e_dec
    ON e_dec.from_object_id = sig.object_id
   AND e_dec.edge_type = 'signal_for'
  LEFT JOIN agent.decision_objects dec
    ON dec.object_id = e_dec.to_object_id
   AND dec.object_type = 'strategist_decision'
  LEFT JOIN agent.decision_edges e_verdict
    ON e_verdict.from_object_id = dec.object_id
   AND e_verdict.edge_type = 'reviewed_by'
  LEFT JOIN agent.decision_objects verdict
    ON verdict.object_id = e_verdict.to_object_id
   AND verdict.object_type = 'guardian_verdict'
  LEFT JOIN agent.decision_edges e_plan
    ON e_plan.from_object_id = verdict.object_id
   AND e_plan.edge_type = 'planned_by'
  LEFT JOIN agent.decision_objects plan
    ON plan.object_id = e_plan.to_object_id
   AND plan.object_type = 'execution_plan'
)
SELECT *
FROM chain
WHERE decision_object_id IS NULL
   OR verdict_object_id IS NULL
   OR (
        plan_object_id IS NULL
        AND EXISTS (
          SELECT 1
          FROM agent.decision_objects d
          WHERE d.object_id = chain.decision_object_id
            AND d.payload->>'decision_action' NOT IN ('hold', 'no_action')
        )
      );
```

Expected: zero rows. Any missing decision, missing verdict, or missing plan for
an executable decision is FAIL.

### 3. Guardian Verdict Before ExecutionPlan

```sql
SELECT plan.object_id, plan.order_plan_id, plan.decision_id, plan.verdict_id
FROM agent.decision_objects plan
LEFT JOIN agent.decision_objects verdict
  ON verdict.object_type = 'guardian_verdict'
 AND verdict.verdict_id = plan.verdict_id
 AND verdict.decision_id = plan.decision_id
WHERE plan.object_type = 'execution_plan'
  AND plan.created_at >= :start_ts
  AND plan.created_at < :end_ts
  AND plan.engine_mode = ANY(:engine_scope)
  AND (
    verdict.object_id IS NULL
    OR verdict.state NOT IN ('approved', 'modified')
  );
```

Expected: zero rows.

### 4. Symbol And Direction Scope Integrity

```sql
SELECT
  plan.order_plan_id,
  plan.decision_id,
  dec.symbol AS decision_symbol,
  plan.symbol AS plan_symbol,
  dec.payload->>'direction' AS decision_direction,
  plan.payload->>'direction' AS plan_direction,
  plan.payload->>'symbol_source' AS symbol_source,
  plan.payload->>'direction_source' AS direction_source
FROM agent.decision_objects plan
JOIN agent.decision_objects dec
  ON dec.object_type = 'strategist_decision'
 AND dec.decision_id = plan.decision_id
WHERE plan.object_type = 'execution_plan'
  AND plan.created_at >= :start_ts
  AND plan.created_at < :end_ts
  AND plan.engine_mode = ANY(:engine_scope)
  AND (
    plan.symbol <> dec.symbol
    OR plan.payload->>'direction' <> dec.payload->>'direction'
    OR plan.payload->>'symbol_source' <> 'strategist_decision'
    OR plan.payload->>'direction_source' <> 'strategist_decision'
  );
```

Expected: zero rows.

### 5. Real Submit Requires Lease

```sql
SELECT report.execution_report_id, report.order_plan_id, plan.lease_id
FROM agent.decision_objects report
JOIN agent.decision_objects plan
  ON plan.object_type = 'execution_plan'
 AND plan.order_plan_id = report.order_plan_id
WHERE report.object_type = 'execution_report'
  AND report.created_at >= :start_ts
  AND report.created_at < :end_ts
  AND report.engine_mode = ANY(:engine_scope)
  AND COALESCE(report.payload->>'status', report.state) NOT IN ('shadow', 'skipped')
  AND (plan.lease_id IS NULL OR plan.lease_id = '');
```

Expected: zero rows for any non-shadow submit/fill/failure report. If the
router lease canary flag is disabled for the window, the report must state
that real submit acceptance is blocked from Stage 3 until the lease evidence is
present.

### 6. Execution Idempotency Reserved

```sql
SELECT plan.order_plan_id, plan.decision_id, plan.engine_mode
FROM agent.decision_objects plan
LEFT JOIN agent.execution_idempotency_keys idem
  ON idem.order_plan_id = plan.order_plan_id
 AND idem.decision_id = plan.decision_id
 AND idem.engine_mode = plan.engine_mode
WHERE plan.object_type = 'execution_plan'
  AND plan.created_at >= :start_ts
  AND plan.created_at < :end_ts
  AND plan.engine_mode = ANY(:engine_scope)
  AND idem.idempotency_key IS NULL;
```

Expected: zero rows for any plan that can reach submit. Shadow-only planning
may be listed separately only if it is explicitly out of submit scope.

### 7. ExecutionReport Quality Metrics

```sql
SELECT execution_report_id, order_plan_id, payload
FROM agent.decision_objects
WHERE object_type = 'execution_report'
  AND created_at >= :start_ts
  AND created_at < :end_ts
  AND engine_mode = ANY(:engine_scope)
  AND (
    NOT (payload ? 'quality_metrics')
    OR NOT (payload ? 'requested_qty')
    OR NOT (payload ? 'filled_qty')
    OR NOT (payload ? 'liquidity_role')
  );
```

Expected: zero rows for reports generated by ExecutorReport V2.

### 8. No Submit Outside Engine Scope

```sql
SELECT object_id, object_type, engine_mode, symbol, order_plan_id, execution_report_id
FROM agent.decision_objects
WHERE created_at >= :start_ts
  AND created_at < :end_ts
  AND object_type IN ('execution_plan', 'execution_report')
  AND engine_mode <> ALL(:engine_scope);
```

Expected: zero rows.

### 9. No Scanner Or Analyst Direct Trading Authority

```sql
SELECT object_id, object_type, source_agent, payload
FROM agent.decision_objects
WHERE created_at >= :start_ts
  AND created_at < :end_ts
  AND engine_mode = ANY(:engine_scope)
  AND object_type IN ('execution_plan', 'execution_report')
  AND source_agent NOT IN ('executor');
```

Expected: zero rows. Scanner and Analyst may appear as evidence refs or
insights, not as the source agent for execution plans/reports.

### 10. OpenClaw Route Allowlist Still Read-Only

Run the existing route contract test or capture equivalent source evidence:

```bash
python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_openclaw_routes.py -q
```

Expected: active allowlist remains exactly the two GET routes; no proposal,
approval, order, secret, live TOML, deploy, restart, or risk-write route.

## Runtime Health Evidence

Collect at start and end:

```bash
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status
bash helper_scripts/db/passive_wait_healthcheck.sh
```

Required interpretation:

- watchdog must show the targeted engine scope alive/fresh;
- passive healthcheck must not introduce new P0/P1 lineage, live-auth, or
  execution-authority failures;
- pre-existing unrelated WARN/FAIL items must be listed separately and cannot
  be used to hide a canary regression.

## PASS / WARN / FAIL

PASS requires:

- 24h window completed or operator-stopped with explicit no-regression reason.
- 100% executable decisions have StrategistDecision + approved/modified
  GuardianVerdict + ExecutionPlan.
- 100% non-shadow submit reports have lease evidence or are declared out of
  Stage 3 eligibility.
- 100% submit-capable plans have idempotency reservation.
- 0 symbol/direction/source mismatch.
- 0 submit outside engine scope.
- 0 scanner or Analyst direct execution authority.
- OpenClaw remains read-only.
- Rollback path was available for the whole window.

WARN means the window may be useful for diagnosis but cannot promote:

- fewer than 50 decision chains and the operator wanted a larger sample;
- spine writer success below 95% but failures are visible and do not produce
  fake success;
- healthcheck has unrelated pre-existing WARN/FAIL that complicates reading.

FAIL means immediate rollback:

- missing GuardianVerdict before ExecutionPlan;
- missing ExecutionPlan before a submit/fill/failure report;
- missing lease on non-shadow submit report when lease canary is in scope;
- executor symbol/direction differs from StrategistDecision;
- direct scanner/Analyst close/reduce/order authority;
- any true-live route, flag, or authorization anomaly outside the written
  operator scope;
- any false execution success or hidden lease failure.

## Operator Acceptance

The 24h report is accepted only if it ends with:

```text
MAG-082 24h canary validation verdict: PASS | WARN | FAIL
Window:
Engine scope:
Decision count:
Executable chain count:
Non-shadow submit report count:
Rollback used: yes | no
Operator:
Timestamp UTC:
```

Only PASS can feed MAG-083 final release audit. WARN/FAIL must stay in M8 and
produce a follow-up or rollback record.

## MAG-082 Result

MAG-082 is complete as a checklist/validation contract. No 24h canary was run,
and no evidence row was generated by this checkpoint. The next M8 gate is
MAG-083 final release audit after an operator-approved canary window produces
evidence against this checklist.

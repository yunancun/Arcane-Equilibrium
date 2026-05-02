# LG-5-IMPL-3 Healthchecks `[42]` + `[42b]`

**Date**: 2026-05-02
**Owner**: E1 (LG-5-IMPL-3)
**Spec source**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md`
**Implementation**: `srv/helper_scripts/db/passive_wait_healthcheck/checks_governance.py`
**Tests**: `srv/helper_scripts/db/test_lg5_healthchecks.py` (13 tests, all PASS — round 2 added standard FAIL band fixture)
**Runner wire-up**: `srv/helper_scripts/db/passive_wait_healthcheck/runner.py` (cursor block, after `[41]`)

---

## `[42] live_candidate_eval_contract`

### Purpose

Verify that every newly inserted live promotion candidate row in
`learning.mlde_param_applications` has a matching audit row in
`learning.governance_audit_log` with `event_type = 'review_live_candidate'`
within **1 hour** of the candidate's `ts`.

This catches the silent-failure mode where:
- LG-5-IMPL-1 (`mlde_demo_applier._insert_live_candidate`) inserts the
  candidate row, but
- LG-5-IMPL-2 (`GovernanceHub.review_live_candidate`) consumer never fires,
  crashes mid-call, or skips the audit-row INSERT.

Without this sentinel, candidates would queue forever in `status='candidate'`
and live promotion would deadlock invisibly.

### SQL contract (1h SLA)

```sql
SELECT count(*) FROM learning.mlde_param_applications c
WHERE c.engine_mode = 'live'
  AND c.application_type = 'live_promotion_candidate'
  AND c.status = 'candidate'
  AND c.ts < now() - interval '1 hour'
  AND NOT EXISTS (
    SELECT 1 FROM learning.governance_audit_log a
    WHERE a.candidate_id = c.id
      AND a.event_type = 'review_live_candidate'
  );
```

### Verdict bands

| Unaudited count (>1h old) | Status | Meaning |
|---|---|---|
| 0 | PASS | Contract intact (1h SLA) |
| 1 ≤ n ≤ 2 | WARN | Small backlog; possible queuing or recent restart |
| n ≥ 3 | FAIL | Contract systematically broken; **lease_revoke_trigger fires** (RFC v2 §4) |

> **Note on band thresholds**: Verdict band thresholds (0 / 1-2 / ≥3) are an
> E1 engineering proposal; RFC v2 §6 IMPL-3 only specifies the 1h SLA + the
> audit-row contract itself. Adjust if production observation indicates a
> different operator-acceptable backlog (e.g. higher WARN ceiling under heavy
> candidate flow, or stricter FAIL threshold under quiet windows).

### Pre-conditions (fail-closed)

- `learning.mlde_param_applications` exists (V032 deployed) — else FAIL.
- `learning.governance_audit_log` exists (V035 deployed) — else FAIL.

### RFC traceability

- §6 IMPL-3 line 451-454 — original spec
- §4 line 404 — `[42]` listed as `lease_revoke_trigger`

---

## `[42b] live_candidate_attribution_drift`

### Purpose

Per-strategy 7d rolling `attribution_chain_ok` ratio detector for the 5 LG-5
strategies. Surfaces production attribution chain quality regression so that:

1. R-meta defer (RFC §3 line 366-367) is anticipated, and
2. Pipeline-level catastrophic regression (any strategy < 0.10) auto-revokes
   active leases (RFC §4 line 405).

### SQL contract (7d window)

```sql
SELECT strategy_name,
       count(*)::int AS total,
       count(*) FILTER (WHERE attribution_chain_ok)::int AS chain_ok,
       (count(*) FILTER (WHERE attribution_chain_ok))::float
         / nullif(count(*), 0)::float AS ratio
FROM learning.mlde_edge_training_rows
WHERE ts > now() - interval '7 days'
  AND engine_mode IN ('demo', 'live_demo')
  AND strategy_name IS NOT NULL
GROUP BY strategy_name;
```

The `engine_mode IN ('demo', 'live_demo')` filter MUST match the IMPL-1
producer `_compute_attribution_chain_ratio_by_strategy`
(`program_code/ml_training/mlde_demo_applier.py:907-920`) exactly — the
drift sentinel must measure the SAME source the producer feeds the consumer
(LG-5-IMPL-2 `GovernanceHub.review_live_candidate`). Including `'live'`
would diverge from the producer input and yield false alarms / false
reassurance vs the actual ratio R-meta sees.

Result is filtered to the 5 LG-5 strategies:
`grid_trading`, `ma_crossover`, `bb_breakout`, `bb_reversion`, `funding_arb`.
Missing strategy → ratio = 0.0 (forces alarm to expose producer bug).

### Verdict bands

Worst (lowest) ratio across the 5 strategies determines verdict. RFC v2
§6 IMPL-3 line 451 mandates three floors (0.50 / 0.30 / 0.10) producing
four bands; any strategy `< 0.10` additionally escalates to a pipeline-alert
(RFC §3 line 377):

| Worst ratio | Status | Meaning |
|---|---|---|
| ≥ 0.50 | PASS | All strategies above R-meta floor (RFC §3 line 366-367) |
| [0.30, 0.50) | WARN | Below R-meta 0.50 floor; `review_live_candidate` will defer for that strategy |
| [0.10, 0.30) | FAIL | Standard FAIL band; attribution chain systemically degraded — investigate producer (MIT-S2-1 `attribution_chain_ok` writer) |
| < 0.10 | FAIL (pipeline-alert escalation) | **lease_revoke_trigger fires** (RFC §4 line 405); GovernanceHub must auto-revoke active leases |

### Edge cases

- **First-deploy / production silent**: All 5 strategies have 0 rows in 7d →
  WARN (not FAIL); cannot evaluate drift without data.
- **Single missing strategy**: Treated as ratio 0.0 → FAIL (producer-side bug
  exposed, not hidden).

### Pre-conditions (fail-closed)

- `learning.mlde_edge_training_rows` exists (V031 deployed) — else FAIL.

### RFC traceability

- §3 R-meta line 357-377 — per-strategy attribution dict, 0.50 floor
- §3 line 377 — pipeline-level alert cross-ref to `[42b]` and MIT MF-M5
- §4 line 405 — `[42b]` listed as `lease_revoke_trigger`

---

## Operational notes

### Cron cadence

Both checks run inside the existing `passive_wait_healthcheck` cursor block,
already invoked by `helper_scripts/db/passive_wait_healthcheck_cron.sh`. No
new cron entry required.

### Lease auto-revoke wire-up

`[42]` FAIL or `[42b]` FAIL emits the alarm. The actual lease auto-revoke
mechanism is owned by `GovernanceHub` (LG-5-IMPL-2 consumer side) — when
either healthcheck flips FAIL during a lease's lifetime, GovernanceHub MUST
emit a `governance_audit_log` row with `event_type = 'lease_auto_revoke'`
and the trigger healthcheck id (RFC v2 §4 line 407). This sentinel surfaces
the alarm; downstream wiring is not part of LG-5-IMPL-3 scope.

### Test fixtures

`srv/helper_scripts/db/test_lg5_healthchecks.py` provides:

- **`[42]`**: 5 tests — PASS / WARN / FAIL / V035-missing / V032-missing
- **`[42b]`**: 7 tests — PASS / WARN / FAIL standard band / FAIL pipeline-alert / missing-strategy / silent-deploy / V031-missing
- **Constants**: 1 test — confirms 5 LG-5 strategies match RFC §3

All 13 tests deterministic (mocked cursor); 0 DB connection required.

**Round 2 (2026-05-02) test diff**: Added `test_fail_when_worst_in_standard_fail_band`
(fixture ratio 0.20) to cover RFC §6 IMPL-3 line 451's [0.10, 0.30) standard
FAIL band; renamed band semantics in `test_warn_when_worst_in_warn_band` from
0.30 → 0.40 to keep the WARN fixture strictly inside [0.30, 0.50) and avoid
the WARN/FAIL boundary at exactly 0.30.

### Future evolution

- If lease_revoke_triggers list grows in RFC, add new sentinels in this
  module.
- If `[42b]` band is over-broad (false positives at 0.10 due to small `n`),
  consider adding sample-size guard (e.g. `total >= 30` for FAIL).

---

## LG5-W3-FUP-1 — `review_live_candidate` consumer scheduler

**Module**: `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/lg5_review_consumer_scheduler.py`
**Wire-in**: `app/main.py` startup hook after `EdgeEstimatorScheduler`
**Tests**: `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_lg5_consumer_scheduler.py` (10 tests)
**Spec**: PA dispatch LG5-W3-FUP-1 (root cause of `[42]` runtime FAIL — IMPL-2 consumer landed but no scheduler called it).

### Why this exists

Pre-FUP runtime observation: `recent_24h_total=8`, `unaudited_over_1h=27`. RFC v2 §4 `[42] live_candidate_eval_contract` `lease_revoke_trigger` was firing because the IMPL-2 `review_live_candidate(hub, candidate_id)` consumer existed but was never invoked — pending `live_promotion_candidate` rows accumulated indefinitely.

This scheduler closes the loop: a daemon thread (sibling to `EdgeEstimatorScheduler`, independent leader election) polls `learning.mlde_param_applications` for pending live promotion candidates and dispatches `review_live_candidate` per row.

### Behaviour summary

- **Cycle cadence**: every `OPENCLAW_LG5_CONSUMER_CYCLE_SECS` seconds (default 300s = 5 min).
- **Per-cycle cap**: `OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE` (default 16) — matches `mlde_demo_applier.max_recommendations` so one producer flush drains in one consumer cycle.
- **Order**: oldest-first (`ORDER BY ts ASC`) so longest-waiting candidates are reviewed first; mitigates `[42] unaudited_over_1h` backlog.
- **Authorization handling (ROUND-2 HIGH-1 fix)**: the wrapper does **NOT** short-circuit on `hub.is_authorized() == False`. `review_live_candidate` (IMPL-2) is invoked unconditionally per pending candidate; its internal R6 evaluator (`evaluate_r6` at `governance_hub_live_candidate_review.py:1037-1047`) treats `auth_effective=False` as a hard veto and emits a `reject_hard_veto` audit row. This guarantees `[42] unaudited_over_1h` drains regardless of authorization state — short-circuiting at the wrapper layer would defeat the whole consumer.
- **Per-candidate fail-open**: a single candidate raising does not abort the batch; remaining candidates still reviewed. Failure recorded in `summary.errors` + `total_errors` stat (incremented under lock alongside other totals).
- **No duplicate audit emission**: `review_live_candidate` itself emits the audit row (RFC v2 §2.3); wrapper only INFO-logs aggregate `{reviewed, approved, rejected, rejected_hard_veto, deferred, errors}` per cycle for stdout grep. `rejected_hard_veto` is a verdict-derived subset of `rejected` (where `verdict.reason == 'reject_hard_veto'`) — operators use it to surface unauthorized-state cycles without coupling to the wrapper's hub query.
- **Single-leader**: independent flock sentinel `$OPENCLAW_DATA_DIR/lg5_review_consumer.leader.lock` — under uvicorn `--workers 4` only one worker runs the consumer (avoids 4× DB writes).

### Env-var inventory

| Env var | Default | Effect |
|---|---|---|
| `OPENCLAW_LG5_CONSUMER_ENABLED` | `1` | `0` disables daemon thread spawn entirely (start returns None); use to hard-disable consumer without touching code. |
| `OPENCLAW_LG5_CONSUMER_CYCLE_SECS` | `300.0` | Cycle interval in seconds. Lower = faster backlog drain + more reactive to auth changes; higher = lower DB load. Invalid value → falls back to default. |
| `OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE` | `16` | Per-cycle SQL `LIMIT`. Mirrors `mlde_demo_applier.max_recommendations`; raise only if observed backlog regularly exceeds 16. Invalid value → falls back to default. |
| `OPENCLAW_SCHEDULER_LEADER` | unset | Shared with `edge_estimator_scheduler` — set to `0` to force non-leader (testing / single-worker dev). To disable consumer specifically without affecting edge scheduler, prefer `OPENCLAW_LG5_CONSUMER_ENABLED=0`. |
| `OPENCLAW_DATA_DIR` | `/tmp/openclaw` | Parent dir of the leader-lock sentinel (cross-platform; Mac sets in `~/.zshrc`). |

### Rationale for defaults

- **`cycle_secs=300` (5 min)**: producer (`mlde_demo_applier`) runs hourly, so 5-min consumer cadence gives ≤5 min lag from producer insert to consumer review — comfortably within the `[42]` 1-hour SLA. More frequent cadence (e.g. 60s) would trade DB-poll cost for marginal latency gain on a queue that fills slowly. Less frequent (e.g. 1800s = 30 min) would risk WARN-band drift on bursty inserts.
- **`max_per_cycle=16`**: matches `mlde_demo_applier.max_recommendations = R4_PENDING_CAP` in `governance_hub_live_candidate_review.py`. One producer cycle's worst-case output is exactly drained in one consumer cycle.

### Operational verification

```bash
# Verify scheduler started (look for leader-elected log line)
journalctl -u openclaw-api --since "5 min ago" | grep "Lg5ReviewConsumer"

# Verify cycles firing (INFO log per cycle)
journalctl -u openclaw-api --since "30 min ago" | grep -E "Lg5ReviewConsumer\[(scheduled|manual_trigger)\]"

# Verify consumer is draining backlog (status via Python REPL or future route)
# Expect total_reviewed > 0 and last_run_ts within ~cycle_secs of now()
```

### Healthcheck `[42]` covers consumer drain proof

Once this scheduler is deployed, `[42] live_candidate_eval_contract` should flip from FAIL (27 unaudited) → PASS (0 unaudited) within ~5 min of API restart. If it stays FAIL after 30 min:
1. Check `OPENCLAW_LG5_CONSUMER_ENABLED` is not `0`.
2. Check leader log line — exactly one worker should report "elected leader".
3. Check `Lg5ReviewConsumer[scheduled]` INFO log line for cycle stats — note the `rejected (hard_veto=N)` segment.
4. **Unauthorized state observability** (replaces deleted `cycles_skipped_not_authorized` metric — see ROUND-2 HIGH-1 fix): IMPL-2 R6 evaluator now handles unauthorized state by emitting `reject_hard_veto` audit rows. To diagnose:
   - **Stdout / status grep**: look for `total_rejected_hard_veto > 0` in the `status()` payload (or the `(hard_veto=N)` field in INFO log per cycle). If `total_rejected_hard_veto` is climbing while `total_approved` stays at 0, authorization is likely missing/expired — fix authorization first.
   - **DB SQL grep** (authoritative): `SELECT COUNT(*) FROM learning.governance_audit_log WHERE event_type='review_live_candidate' AND verdict_reason='reject_hard_veto' AND ts > now() - interval '1 hour';` — every unauthorized-state cycle row is here, joinable to candidate_id.

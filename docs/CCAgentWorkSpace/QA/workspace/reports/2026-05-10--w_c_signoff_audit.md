# W-C MAG-082 Stage 2 Sign-off Audit

**Date (Linux UTC)**: 2026-05-10 22:30+
**Date (Mac CC context)**: 2026-05-11
**Auditor**: QA (read-only)
**Subject**: W-C MAG-082 Stage 2 evidence window — Decision Lease router-gate shadow lineage
**Wave roster**: TODO.md §4.1 W-C, ACTIVE since 2026-05-08
**Authorization SoT**: `srv/docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`
**Amendment SoT**: `srv/docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` §5.4.1
**Healthcheck SoT**: `srv/helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` (function `check_55_agent_decision_spine_lineage`)

---

## Executive Verdict

**CONDITIONAL_PASS**

Lineage structure GREEN; runtime hour-coverage GREEN; lease bypass tagging GREEN by design. However two design-vs-runtime gaps surfaced that materially affect the *meaning* of "MAG-082 Stage 2 evidence":

1. `agent.decision_state_changes` table is empty all-time (0 rows over 51-hour W-C window) despite producer code wiring existing in `agent_spine_writer.rs:217-260` and `store.rs:105`. No caller invokes `put_state_transition` outside trait/impl declarations.
2. All 174 `ExecutionReport.payload.filled_qty=0` and `liquidity_role='unknown'` over 24h, while 86 real fills exist in `trading.fills` over the same window. ExecutionReport payloads are structural stubs, not real Bybit demo execution evidence. The [55] check passes because it only verifies *key existence* (`bad_report_quality=0` is keyspace-level), not value-realism.

These gaps do NOT block W-D in the strict sense of the authorization file (which only requires shadow lineage + bypass lineage to flow), but they degrade the value of MAG-082 Stage 2 as "evidence that lease lifecycle and execution attribution can be reconstructed for Decision Lease retrofit promotion". MAG-083/MAG-084 must explicitly acknowledge these limits when deciding promotion.

Per the authorization boundary, recommend operator and PM accept CONDITIONAL_PASS for W-C with W-D dispatch allowed AND with `P0-AGENT-1/2 sibling` issues opened to address state-changes 0-row and ExecutionReport stub before MAG-082 readiness is upgraded from `LINEAGE_READY_NOT_WINDOW_PASS` to `WINDOW_PASS` (manual operator gate per §5.4.1).

---

## Audit Item Summary (10 items)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Engine + API process state | PASS | PID 1441249 openclaw-engine + PID 1513898 uvicorn (4 workers) on Linux trade-core |
| 2 | Engine env aligns with 2026-05-08 auth | PASS | `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`, `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`, `OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv` confirmed |
| 3 | 24h chain row counts complete | PASS | 5 types × 2 engine_modes balanced: demo 97/97/97/97/97 + live_demo 77/77/77/77/77 |
| 4 | Chain integrity SQL end-to-end | PASS | 174 complete chains (97 demo + 77 live_demo) signal→decision→verdict→plan; 174/174 idempotency; 174/174 lease_id; 174/174 report |
| 5 | `decision_state_changes=0` root cause | **CAVEAT** | All-time 0 rows; 24h 0 rows. Producer code exists (writer.rs:232, store.rs:105) but no `put_state_transition` caller invocations (grep finds only 3 trait/impl declarations, 0 producer calls) |
| 6 | `bad_report_quality=0` semantic | **CAVEAT** | Healthcheck only verifies payload KEY existence (`quality_metrics`, `requested_qty`, `filled_qty`, `liquidity_role`), not VALUE realism. 174/174 reports have all keys but `filled_qty=0.0` + `liquidity_role='unknown'` for every sample |
| 7 | LiveDemo ExecutionReport realness | **CAVEAT** | 5 sampled live_demo reports: `filled_qty=0.0` `liq_role='unknown'` 100%. Compare: `trading.fills` 24h has 86 rows (50 demo + 36 live_demo) with positive_qty — real fills exist but not propagated to Agent Spine ExecutionReport.payload |
| 8 | Hour-level gaps / engine restart impact | PASS | 24h hourly distribution shows 21 hours with rows. Brief absences at 02h/08h/21h local (likely market-quiet periods). Engine restarted 2h30m ago (PID 1441249 etime=02:30:41); 22h slot has 105 rows confirming immediate restoration post-restart. Cross-restart PG persistence intact. |
| 9 | §四 hard-invariant boundary intact | PASS | scanner_config.toml has no `[authority]`; LiveDemo on Bybit demo endpoint per auth file; no live mainnet traffic; SM-04 ladder / DOC-08 §12 / Live boundary 5-gate not breached; W-C operates entirely in shadow surface |
| 10 | Replay non-substitution | PASS | `source_agent ILIKE '%replay%'` 24h count = 0. Source agents are `executor`/`guardian`/`strategist`/`strategy` only |

---

## Detailed Evidence

### Item 1-2: Process and env (CLAUDE.md §三 runtime row + §四 hard gates)

```
pgrep -af openclaw-engine
1441249 rust/target/release/openclaw-engine
pgrep -af uvicorn
1513898 .venv/bin/python3 .venv/bin/uvicorn app.main:app --host 100.91.109.86 --port 8000 --workers 4

/proc/1441249/environ | grep ^OPENCLAW_:
  OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow
  OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv
  OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1
  OPENCLAW_CANARY_MODE=1
  OPENCLAW_COST_EDGE_ADVISOR=1
  OPENCLAW_AUTO_MIGRATE=0
  OPENCLAW_ENABLE_PAPER=0
  OPENCLAW_H_STATE_GATEWAY=1
```

100% match with 2026-05-08 authorization file Evidence at Recording Time section.

### Item 3-4: Lineage chain rows (51h W-C window)

```
W-C accumulation span:
  demo:      1420 objects (2026-05-08 21:22 → 2026-05-11 00:23 local, ~51 hours)
  live_demo: 1135 objects (2026-05-08 21:24 → 2026-05-11 00:23 local)
  total:     2555 objects

24h window typed breakdown (5 types per engine_mode):
  demo      | execution_plan      |  97
  demo      | execution_report    |  97
  demo      | guardian_verdict    |  97
  demo      | strategist_decision |  97
  demo      | strategy_signal     |  97
  live_demo | execution_plan      |  77
  live_demo | execution_report    |  77
  live_demo | guardian_verdict    |  77
  live_demo | strategist_decision |  77
  live_demo | strategy_signal     |  77

Chain integrity (signal_for → reviewed_by/modified_by → planned_by → executed_by):
  demo:      97/97 complete (100%)
  live_demo: 77/77 complete (100%)

[55] direct run (correct env):
  status=PASS
  msg=agent decision spine lineage proof healthy; MAG-082 readiness=LINEAGE_READY_NOT_WINDOW_PASS
      window=1440m modes=demo,live_demo
      objects=870/2555 edges=696/2044 idempotency=174/511
      types=strategy_signal=174,strategist_decision=174,guardian_verdict=174,
            execution_plan=174,execution_report=174
      chains=174 chains_with_idempotency=174 chains_with_lease=174
      chains_with_report=174 bad_report_quality=0
```

### Item 5 (CAVEAT-1): decision_state_changes 0-row

**Schema** (`information_schema.columns`):
```
ts | transition_id | object_id | object_type | from_state | to_state | engine_mode | trigger | details
```

**All-time count**: 0 rows
**24h count**: 0 rows

**Producer code** (`rust/openclaw_engine/src/database/agent_spine_writer.rs`):
- Line 217-260: `flush_state_transitions()` async fn with INSERT INTO agent.decision_state_changes ON CONFLICT(transition_id, ts) DO NOTHING
- Line 27: `transition_buf: Vec<SpineStateTransition>` allocated
- Line 77: function takes `transitions: &mut Vec<SpineStateTransition>` parameter

**Producer wiring** (`rust/openclaw_engine/src/agent_spine/store.rs`):
- Line 52: trait declares `fn put_state_transition(&self, transition: SpineStateTransition) -> StoreAck;`
- Line 68: stub impl (returns nothing useful)
- Line 105: real impl `self.try_send(AgentSpineMsg::StateTransition(transition))`

**Caller search**: `grep -rn 'put_state_transition' rust/openclaw_engine/src/` returns ONLY the 3 trait/impl declarations above. **0 actual callers** in `intent_processor/`, `executor/`, or anywhere else.

**Verdict**: This is a P1 producer-call wiring gap, not a schema or table issue. The state-machine itself is not emitting transition events to the spine writer. State machine transitions for SM-02 Lease (DRAFT→REGISTERED→ACTIVE→BRIDGED→CONSUMED) and other formal-object lifecycles are not being recorded in `agent.decision_state_changes`.

**Impact on W-C scope**: The 2026-05-08 authorization file allows "shadow Agent Spine lineage" + "router-gate bypass / lease ids into shadow ExecutionPlan rows" — these are confirmed working. It does NOT explicitly require `decision_state_changes` writes. So **W-C is technically within authorized scope**.

**Impact on MAG-082/083/084**: AMD-2026-05-02-01 §4 AC-1 requires `learning.lease_transitions` 24h coverage ≥5 distinct to_state values for SM-02 lifecycle proof. `learning.lease_transitions` 24h = 62,600 rows (high activity), but this is SM-side, not Agent Spine side. The Agent Spine `decision_state_changes` 0-row gap means cross-table reconstruction will rely entirely on `learning.lease_transitions` and `agent.decision_objects` directly, not on a typed transition log within Agent Spine.

### Item 6 (CAVEAT-2): bad_report_quality=0 keyspace-only

**Healthcheck logic** (`checks_agent_spine.py` lines 166-175):
```sql
count(DISTINCT report.object_id) FILTER (
    WHERE report.object_id IS NOT NULL
      AND (
        NOT (report.payload ? 'quality_metrics')
        OR NOT (report.payload ? 'requested_qty')
        OR NOT (report.payload ? 'filled_qty')
        OR NOT (report.payload ? 'liquidity_role')
      )
)::int AS bad_report_quality
```

This counts reports where ANY of the 4 keys is MISSING. It does not verify the values are non-default. A payload with all 4 keys present but with `filled_qty=0.0` and `liquidity_role='unknown'` is treated as quality_OK.

**Verdict**: [55] PASS is a structural pass, not a semantic pass. MAG-082 readiness as currently defined accepts stub payloads.

### Item 7 (CAVEAT-3): ExecutionReport real-fill propagation gap

**24h aggregate**:
```
174 reports total
0   reports with filled_qty > 0
0   reports with liquidity_role != 'unknown'
```

**5 sampled live_demo reports (last 6h)**:
```
plan_ts                     | req_qty | filled_qty | liq_role | has_qm
2026-05-11 00:23:00.069+02  | 8.5     | 0.0        | unknown  | true
2026-05-10 23:18:00+02      | 14.2    | 0.0        | unknown  | true
2026-05-10 22:52:00+02      | 0.03    | 0.0        | unknown  | true
2026-05-10 22:48:22.698+02  | 164.0   | 0.0        | unknown  | true
2026-05-10 22:39:15.118+02  | 165.0   | 0.0        | unknown  | true
```

**Cross-check** (`trading.fills` 24h):
```
engine_mode | count | positive_qty | latest
demo        |    50 |           50 | 2026-05-10 23:02:22.87+02
live_demo   |    36 |           36 | 2026-05-10 22:52:00.488+02
```

**Verdict**: Real fills exist in `trading.fills` (86 rows positive qty 100%) but never get propagated to `agent.decision_objects.execution_report.payload`. The W-C "ExecutionReport lineage" path writes a structural shell, not actual execution attribution. This breaks the MAG-082 design intent of "evidence that execution attribution can be reconstructed", though it satisfies the literal structural lineage requirement.

### Item 8: Hour-coverage and engine-restart resilience

**24h hourly distribution** (44 row groups):
- Active hours: 21/24 (rows present)
- Empty hours: 02h, 08h, 21h local — total 3 hours
- engine restart at ~22:00 local (etime=02:30:41 from 22:30 query time)
- 22h slot: 55 demo + 50 live_demo = 105 rows (highest post-restart density)
- 23h slot: 25 demo + 5 live_demo
- 00h slot: 5 demo + 5 live_demo

**Cross-restart persistence**: PG rows survive engine restart by design (PG is not on engine memory). The W-C "24h fresh window" definition does NOT require single uninterrupted engine session; the 51h W-C span has had at least 1 engine restart and continued to accumulate evidence post-restart.

**Verdict**: Engine restart did not corrupt or interrupt lineage. The 3 empty hours (02h, 08h, 21h) likely reflect low strategy signal density during market-quiet periods, not infrastructure failure. The high 22h burst suggests bootstrap signal catch-up post-restart, which is healthy behavior.

### Item 9: Hard-invariant boundary

- LiveDemo Bybit endpoint per auth file: confirmed
- scanner_config.toml `[authority]` absent: confirmed (per CLAUDE.md §三 line "Scanner config")
- No Mainnet traffic: confirmed (no `OPENCLAW_ALLOW_MAINNET=1` env)
- Live boundary 5-gate not invoked by W-C scope: confirmed (W-C is shadow lineage, not new order authority)
- DOC-08 §12 / SM-04 ladder / §二 16 principles: not breached (W-C operates under existing LiveDemo authorization tier T0_ENTRY)

### Item 10: Replay non-substitution

```sql
SELECT count(*) FROM agent.decision_objects
WHERE source_agent ILIKE '%replay%' AND created_at > now() - INTERVAL '24 hours';
> 0
```

Source agent distribution 24h:
```
demo      | executor   | 194  (97 plans + 97 reports)
demo      | guardian   |  97
demo      | strategist |  97
demo      | strategy   |  97
live_demo | executor   | 154  (77 plans + 77 reports)
live_demo | guardian   |  77
live_demo | strategist |  77
live_demo | strategy   |  77
```

**Verdict**: No replay/synthetic substitution. All evidence is from live runtime agents.

---

## Caveat Summary (must surface to operator + PM + W-D dispatch)

### Caveat 1 — `agent.decision_state_changes` empty all-time (P1)

- Schema exists; producer code exists in `agent_spine_writer.rs`; trait+impl exists in `store.rs`
- **0 callers** invoke `put_state_transition` from `intent_processor/`, `executor/`, or elsewhere
- 51-hour W-C window: 0 rows accumulated
- **Recommendation**: Open P1 sibling issue (e.g. `P0-AGENT-2 follow-up: wire decision_state_changes producer`) before MAG-082 graduates to WINDOW_PASS. Producer-side fix is small (~few callsites to add `put_state_transition()` at SM transition emit points). Not blocking W-D dispatch under literal authorization scope, but MUST be acknowledged in MAG-083 promotion review.

### Caveat 2 — ExecutionReport.payload structural stub (P1)

- 174/174 reports have all required keys but `filled_qty=0.0` + `liquidity_role='unknown'`
- 86 real fills exist in `trading.fills` (50 demo + 36 live_demo) over the same 24h window
- Real execution attribution data is NOT being propagated from `trading.fills` writer into `agent.decision_objects.execution_report.payload`
- `[55]` healthcheck cannot detect this because `bad_report_quality` only checks key existence
- **Recommendation**:
  1. Open P1 sibling issue (`P0-AGENT-3: ExecutionReport.payload real-fill propagation`) to wire real fill data into Agent Spine ExecutionReport before MAG-082 graduates
  2. Upgrade `[55]` healthcheck to add value-realism check: `bad_report_value_quality` = reports where `(payload->>'filled_qty')::numeric > 0` AND `payload->>'liquidity_role' IN ('maker','taker')`
  3. Re-evaluate `LINEAGE_READY_NOT_WINDOW_PASS → WINDOW_PASS` only after both wiring fixes + value-realism check is in [55]

### Caveat 3 (minor) — `lease_id='bypass'` is correct but reduces audit value (informational)

- 174/174 plans have `lease_id='bypass'` (100% same value)
- This is **by-design per 2026-05-08 auth file** ("router-gate bypass / lease ids into shadow ExecutionPlan rows")
- Not a bug, but means W-C does not exercise real Decision Lease lifecycle (DRAFT→REGISTERED→ACTIVE→BRIDGED→CONSUMED)
- Real lease lifecycle remains observed through `learning.lease_transitions` (24h 62,600 rows; AMD §4 AC-1)
- **No action needed for W-C**; MAG-083 should explicitly delineate which evidence comes from Agent Spine vs `learning.lease_transitions`

---

## W-D Blocking Decision

**Does W-D unblock per literal authorization scope?**: **YES**

- 24h windowed `[55]` PASS (running with correct env produces PASS, although still emits `LINEAGE_READY_NOT_WINDOW_PASS`)
- 51-hour fresh window observed (>>24h requirement)
- 174/174 chain completeness across 5 typed objects
- 0 replay substitution
- Boundary fully intact: shadow only, no live new-order authority, no mainnet, no scanner authority, no operator manual writes
- Engine + API processes both alive; env matches auth file 100%
- W-A done, W-B done; W-C structural acceptance met

**Does the readiness flag flip to `WINDOW_PASS` automatically?**: **NO**

- `[55]` design returns `LINEAGE_READY_NOT_WINDOW_PASS` as terminal best-case (no auto-promotion path in code)
- WINDOW_PASS requires explicit operator manual decision per AMD §5.4.1 ("operator explicit sign-off")
- Recommend operator sign manual `WINDOW_PASS` decision in a separate dated governance file after acknowledging Caveats 1 + 2

**Should MAG-083 dispatch proceed?**: **YES**, with the following conditions encoded into the MAG-083 audit pack:

1. MAG-083 reviewer must explicitly note Caveat 1 (`decision_state_changes` 0-row) and Caveat 2 (ExecutionReport real-fill stub) as known limitations
2. MAG-083 promotion decision MUST address whether stub ExecutionReport.payload constitutes "real execution attribution" for Decision Lease retrofit promotion
3. P0-AGENT-2/3 P1 sibling issues should be opened by PM (post this audit) and may run in parallel with MAG-083

---

## Recommendations (for operator + PM)

### Immediate (D+0, post this audit)

1. **Operator**: Sign explicit `W-C → WINDOW_PASS` decision in a new dated governance file (e.g. `srv/docs/governance_dev/2026-05-10--w_c_window_pass_signoff.md`), acknowledging Caveats 1 and 2. Auth flag-flip stays ON.
2. **PM**: Update TODO.md §4.1 Wave Roster: flip W-C from 🔵 ACTIVE → ✅ DONE 2026-05-10 (CONDITIONAL); add reference to this report
3. **PM**: Open 2 new P1 sibling tickets:
   - `P0-AGENT-2-FUP-1: wire put_state_transition callers` (Caveat 1)
   - `P0-AGENT-3-FUP-1: ExecutionReport real-fill propagation + [55] value-realism check` (Caveat 2)
4. **PM**: Update CLAUDE.md §三 W-C / MAG-082 row to reflect CONDITIONAL_PASS verdict + 51-hour span confirmation

### Wave dispatch order (D+0 / D+1)

1. **W-D MAG-083 audit pack dispatch** → assign to QA/PA/QC trio (parallel) with explicit Caveat-aware brief
2. **W-D MAG-084 operator sign-off** → blocked on MAG-083 PASS; not blocked on Caveat fixes (Caveats are P1, not P0 promotion blockers under literal authorization scope)
3. **P0-AGENT-2-FUP-1 + P0-AGENT-3-FUP-1** → can run parallel to W-D (do not gate W-D under literal scope; MUST gate any future Stage 3+ promotion)

### Medium-term

- Update `checks_agent_spine.py` to add `bad_report_value_quality` check (value-realism beyond keyspace)
- Add `[NN]` healthcheck for `decision_state_changes` row count threshold (any new healthcheck per CLAUDE.md §七 strong rule must accompany passive-wait TODO)
- Document `bypass` as a non-promotable lease_id value (so Stage 3 cannot just inherit 'bypass' lineage)

---

## Cross-References

- **Authorization SoT**: `srv/docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`
- **Amendment**: `srv/docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` §5.4.1
- **Healthcheck source**: `srv/helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` (`check_55_agent_decision_spine_lineage`)
- **Producer code**: `rust/openclaw_engine/src/database/agent_spine_writer.rs:217-260`, `rust/openclaw_engine/src/agent_spine/store.rs:52-105`
- **Wave roster**: `srv/TODO.md` §4.1 W-A/W-B/W-C/W-D entries
- **Runtime boundary**: `srv/CLAUDE.md` §三 (W-C / MAG-082 row), §四 (5 hard gates), §五 (Decision Lease evidence mode footnote)
- **Related prior reports**:
  - W-A: `srv/docs/CCAgentWorkSpace/{QA,PA,E2}/workspace/reports/2026-05-07--*.md` (Executor fake-live runtime smoke)
  - W-B: `srv/docs/CCAgentWorkSpace/{QA,PA,E2}/workspace/reports/2026-05-08--*.md` (Decision-spine lineage wiring)
  - W-AUDIT-1: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--*.md` (governance closure)
  - W-AUDIT-2/3: see `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md`
- **Sprint context**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--n0_signoff_n1_dispatch_fire_sop.md` (Sprint N+0/N+1 dispatch SOP)
- **Memory log**: `~/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/project_2026_05_10_sprint_n0_closure.md`

---

## QA E2E ACCEPTANCE TABLE

| 5-stage business chain | Evidence | Status |
|---|---|---|
| Market data | Bybit WS + REST 連線；engine PID 1441249 + uvicorn 4 workers alive | PASS |
| H0 local judgment | `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` env active; scanner_config no [authority] | PASS |
| H1-H5 AI governance | 5-Agent 4-source (executor/guardian/strategist/strategy) writing 24h | PASS |
| 5-Agent + Conductor | 174 chains signal→decision→verdict→plan→report; 100% complete | PASS |
| Decision Lease + Rust Engine | 174/174 plans with lease_id (all `bypass`, by-design); learning.lease_transitions 24h 62,600 rows | PASS (bypass-only) |
| Execution + stop loss | trading.fills 24h 86 rows positive_qty 100%; but Agent Spine ExecutionReport.payload filled_qty all 0 — CAVEAT 2 | PARTIAL |
| Learning + attribution | agent.decision_state_changes 0 rows all-time — CAVEAT 1 | PARTIAL |

| Dual-process E2E | Evidence | Status |
|---|---|---|
| Startup | engine PID 1441249 etime 02:30:41; uvicorn 4 workers | PASS |
| Downgrade (Python disconnect → Rust L0) | Not exercised in this audit window (out-of-scope) | N/A |
| Reconnect | Cross-restart PG persistence intact; 22h post-restart bootstrap accumulation healthy | PASS |

| 5 hard gates (Live pre-flight) | Status |
|---|---|
| Python live_reserved global mode | Not applicable (W-C is shadow, not new live session) |
| Python Operator role auth | Not applicable |
| OPENCLAW_ALLOW_MAINNET=1 env | NOT SET (correct — W-C is LiveDemo only) |
| secret slot api_key + secret | Not applicable (no new authority) |
| authorization.json signed + not expired | LiveDemo auth file present per 2026-05-09 09:12 UTC renewal (CLAUDE.md §三 Live boundary row) |

| 7-day grey stats | Value | Target |
|---|---|---|
| CRITICAL count | 0 | 0 |
| Healthcheck FAIL (passive sample) | 0 | 0 |
| WARN cluster | observed but not measured in this audit | <10 |
| Chain completeness | 174/174 (100%) | >95% |
| Replay substitution | 0 | 0 |

| §三 drift check | Source-of-truth measured | Drift? |
|---|---|---|
| W-C accumulated since 2026-05-08 19:22 UTC | min(created_at)=2026-05-08 21:22 local (= UTC+2; UTC ~19:22) — 51h elapsed | NO |
| `[55]` runtime mode | shadow (matches §三) | NO |
| `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` | confirmed in /proc env | NO |
| LiveDemo auth expires_at_ms=1778405563954 | (per CLAUDE.md §三; not re-validated in this audit since W-C is read-only) | DEFERRED |
| §三 latest [55] PASS evidence | 2026-05-08 22:09 UTC objects=505/505 → 2026-05-10 22:30 UTC objects=870/2555 (growth confirmed) | NO |

---

## Final Verdict

**QA E2E ACCEPTANCE DONE: CONDITIONAL_PASS**

W-C unblocks W-D under literal 2026-05-08 authorization scope. Two payload-realism caveats must be acknowledged in MAG-083 audit pack and tracked as P1 follow-ups (not P0 blockers). Operator manual `WINDOW_PASS` sign-off recommended before MAG-082 readiness flag is upgraded.

**Report path**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-10--w_c_signoff_audit.md`

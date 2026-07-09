# PA Implementation Spec — Cold Audit Package D: AI/ML Cost & Lineage

Date: 2026-05-29 Europe/Madrid. Repo root: `/Users/ncyu/Projects/TradeBot/srv`.
Role: PA(default). Mutation scope: this report file only.
Source HEAD context: per operator brief ~`b93d3210` on `main`.
Upstream: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--cold_audit_validated_fix_plan.md`
findings P1-12, P1-13, P1-14, P2-08; Serialized item 7; Operator Decision item 7.

This is an implementation spec. PA did NOT write feature code, apply migrations,
deploy, or make real paid AI calls. All recheck used read-only Read/grep.

PM pre-decided default applied: provider-native PAID calls FAIL CLOSED on missing
durable ledger/pricing; local/free (Ollama L1) path stays operable. Spec'd to this;
genuine residual operator decisions flagged in the closing section.

---

## 0. PA Recheck Evidence (call-path proof)

| Claim | Evidence |
|---|---|
| Selector expects `policy_ready_standard`, builder emits `policy_ready_standard_allowed` | `bybit_ai_route_selector_builder.py:303` (`{"policy_ready_light_only","policy_ready_standard"}`) vs `bybit_thought_gate_policy_builder.py:332`; contract check `bybit_thought_gate_policy_contract_check.py:37-41` allows the `_allowed` form. |
| Route C emitted but binder rejects | selector emits `route_c_escalated_standard` `bybit_ai_route_selector_builder.py:331,436-457`; canonical binder `misc_tools/bybit_bind_active_route_env.sh:97` accepts only `{route_c_strong, route_c_escalated, route_c}`. `scripts/.../bybit_bind_active_route_env.sh` is a 13-line `exec` shim to misc_tools. |
| H1-F writes JSON only, no DB ledger | `bybit_ai_invocation_attempt_builder.py:515-518` `write_json` latest+dated; `usage_summary` carried in payload (`:450`) but never inserted to DB. |
| Both durable ledgers + writers ALREADY EXIST | `agent.ai_invocations` table `sql/migrations/V003__trading_agent_tables.sql`; Python writer `agent_event_store.py:183-252` `record_ai_invocation` (**fail-soft**, returns False on error :250-252). `learning.ai_usage_log` table `sql/migrations/V010__...sql`; Rust writer `usage_io.rs:39-92` `insert_usage` (**fail-closed**, propagates Err :78) + `load_mtd_usage` :100-118. Rust `tracker.rs:330-365` records LLM usage fail-closed. |
| Daily spend not metered | `bybit_query_budget_gate.py:113-123` daily-exhaust check gated on `total_spent_today_usd` which comment :114-115 admits is "not yet tracked"; `bybit_query_budget_runtime.py:224,288` `usd_meter_available=False`. |
| Unpriced paid call passes | `bybit_ai_cost_log.py:86` sets warning `provider_pricing_table_not_bound_in_mainline` not blocker; `:111` `log_ok` ignores unpriced; `:142` records `pricing_source=not_bound_in_mainline` yet `log_state=ai_cost_log_recorded`. |
| Registry skips silently | `model_registry.py:188-199` verdict gate (`no_ship`→None, only `should_ship`/`shadow_only` register); `:201-203,134-136` DB-unavailable→None; `register_quantile_trio` `:327` drops `None` rows silently; caller treats empty `registered` as success. |
| Runtime registry stale | PA upstream SELECT: `learning.model_registry count=3 max=2026-04-24 production/promoting=0`. |
| Canary candidate query | `canary_promoter.py:617-626` selects `WHERE canary_status IN ('shadow','promoting')` — empty when nothing registered. |

Key architectural finding: **P1-13 requires NO new migration** — both ledger
tables and their writers are deployed. The defect is wiring (H1-F does not call
the writers), not schema. This cleanly separates implementable-now from
migration-apply-gated work.

---

## P1-12 — Enum/Route Name Normalization (Owner: E1 Python)

### Scope
- `bybit_ai_route_selector_builder.py:303` (policy_state allowlist), `:331,436-457` (route C plan/group/recommended_action).
- `bybit_thought_gate_policy_builder.py:332` (emit policy_state).
- `bybit_thought_gate_policy_contract_check.py:37-41` (ALLOWED_POLICY_STATES).
- `misc_tools/bybit_bind_active_route_env.sh:87-101` (route_plan→provider binding).
- (read-only confirm shim) `scripts/bybit_bind_active_route_env.sh`.

### Canonical enum set (SSOT — normalize ALL producers/consumers to these)

**policy_state** (produced H1-B builder, consumed by contract_check + selector):
```
policy_blocked
policy_ready_light_only
policy_ready_standard      <- CANONICAL. drop the "_allowed" suffix.
```
Decision: canonicalize to `policy_ready_standard` (the selector's form, no
suffix — consistent with `policy_ready_light_only`). Change builder `:332` and
contract_check `:40` to emit/allow `policy_ready_standard`. Selector `:303`
already correct, leave it.

**route_plan** (produced H1-R selector, consumed by binder + invocation builder):
```
route_a_light
route_b_standard
route_c_escalated_standard   <- CANONICAL (selector already emits this).
route_skip
```
Decision: canonicalize to `route_c_escalated_standard`. Change binder `:97`
elif branch to accept `{route_c_escalated_standard}` (may keep legacy aliases
`route_c_strong, route_c_escalated, route_c` as deprecated-tolerant during one
transition, but the canonical must match). Selector `:331,437,457` already correct.

**env_binding_group** stays `ROUTE_A/ROUTE_B/ROUTE_C/ROUTE_SKIP` (already consistent).

Production/consumption matrix:
| enum | produced at | consumed at |
|---|---|---|
| policy_state | policy_builder:332 | contract_check:37-41, selector:303 |
| route_plan | selector:331 etc | binder:87-101, invocation_builder request_summary:479 |

### Tests (E4)
- End-to-end fixture: standard lane — policy emits `policy_ready_standard` → selector
  passes `:303` → emits `route_b_standard` → binder binds ROUTE_B provider. Assert
  `should_call_ai=true` reaches a non-empty `BYBIT_AI_ACTIVE_PROVIDER_TARGET`.
- End-to-end fixture: route C — high urgency/opportunity → selector emits
  `route_c_escalated_standard` → binder binds ROUTE_C. Assert binder does NOT fall
  to skip branch (`route_tier != "skip"`, provider non-empty).
- Negative: any unknown policy_state/route_plan → selector blocks honestly with a
  blocking_reason, NOT `should_call_ai=true`-then-skip.

### Acceptance
`should_call_ai=true` always reaches provider binding OR blocks with an explicit
blocking_reason. No string-mismatch silent skip after a positive call decision.

### Risk: 中 (logic, well-covered once fixtures land). Implementable-now.

---

## P1-13 — Durable Ledger Write Contract (Owner: E1 Python + MIT verify; NO migration)

### Scope
- `bybit_ai_invocation_attempt_builder.py:385-518` (the only place a real paid call
  happens + its result/usage_summary).
- Writer (reuse, do not reinvent): `agent_event_store.py:183-252` `record_ai_invocation`
  → `agent.ai_invocations`.
- Rust budget contract reference: `usage_io.rs:39-92`, `tracker.rs:330-365`.

### Ledger write contract

Provider-native paid calls (`provider_target in {openai_native, anthropic_native}`
AND not a legal no-call path) MUST write a durable DB ledger row. The two ledgers
have distinct roles:

1. **`agent.ai_invocations`** (per-invocation lineage/audit) — write via existing
   `record_ai_invocation` after the call resolves. Columns to populate from H1-F:
   `invocation_id` (= idempotency_key, deterministic, reused on retry),
   `provider` (provider_target), `model` (model_name), `tier` (selected_ai_tier),
   `purpose` (route_plan / "h1f_thought_gate"), `prompt_hash` (from prompt material),
   `input_tokens`/`output_tokens` (usage_summary), `cost_usd` (priced; see below),
   `latency_ms`, `success` (invocation_state in success set), `context_id`
   (idempotency_key linkage), `engine_mode`, `details` (route_reason, lane_semantics).

2. **`learning.ai_usage_log`** (budget MTD metering — the one the Rust BudgetTracker
   reads via `load_mtd_usage`) — this is the budget-authoritative ledger. Spend
   metering for P2-08 reads from HERE.

### Pre vs post-call ordering

- **Pre-call**: a reservation/attempt row is NOT required for `agent.ai_invocations`
  (idempotency_key already provides dedup). The pre-call gate is the BUDGET gate
  (P2-08): before invoking a paid provider, the per-call + daily MTD budget must be
  affirmatively checkable. If pricing or MTD spend cannot be read, FAIL CLOSED
  (do not invoke). See P2-08.
- **Post-call**: immediately after the provider call resolves (success OR exception),
  write the `agent.ai_invocations` row AND the `learning.ai_usage_log` row with the
  observed/estimated cost. A paid call that completed at the provider but failed to
  record locally is the dangerous state.

### Failure behavior (the core PM decision, spec'd)

Per Rust budget contract (`usage_io.rs:11,78` fail-closed; `tracker.rs:330` "returns
Err on DB write failure"), and PM default:

- If the durable ledger write FAILS for a **paid** call: mark the H1-F invocation
  result `invocation_state="invocation_ledger_write_failed"`, set a blocking_reason,
  and set `allow_progress_to_h1g_response_check=False`. The downstream cost-gate
  (H5-A) must treat an un-ledgered paid call as BLOCKED, not "recorded". This is
  "fail closed" at the governance layer — we cannot un-call the provider, but we
  refuse to let an un-recorded paid call satisfy cost-cap gates or progress.
- IMPORTANT nuance vs current writer: `record_ai_invocation` is currently **fail-soft**
  (`agent_event_store.py:250-252` returns False, never raises). For paid calls the
  H1-F caller MUST check the boolean return and escalate False to a blocker. Do NOT
  change `record_ai_invocation` to raise globally (other callers rely on fail-soft
  observability) — escalation is the CALLER's responsibility in the paid path.
- Local/free path (Ollama L1, `provider_target` local/none, no_call_path_accepted):
  ledger write is best-effort; write failure is a warning, NOT a blocker (preserves
  root principle 14 baseline operability).

### Tests (MIT + E4)
- Unit: paid-call success writes one `agent.ai_invocations` row + one
  `learning.ai_usage_log` row with correct cost/tokens (mock writer asserts call args).
- Unit: paid-call where ledger write returns False → H1-F emits blocker + does not
  allow progress.
- Unit: local/free path with ledger write failure → warning only, progress allowed.
- MIT Linux read-only SELECT proof after a staged (non-mutating-trade) H1-F run:
  row count increments in both ledgers; idempotency_key retry collapses to one row.

### Acceptance
Every paid provider-native call produces a durable row in BOTH ledgers, or is
blocked from satisfying cost gates. No paid call is recorded only as a JSON file.

### Risk: 中-高 (touches paid-call path + governance gate semantics). Implementable-now
(no migration; tables/writers exist). MIT must run the read-only SELECT proof on Linux.

---

## P1-14 — Registry Persistence Criteria (Serialized item 7 — PA defines) (Owner: E1 Python + MIT verify)

### Scope
- `model_registry.py:139-203` (register_model), `:295-329` (register_quantile_trio caller).
- `canary_promoter.py:617-626` (candidate query).
- Caller in `run_training_pipeline.py` (handles the returned `registered` list).

### Which shadow artifacts REQUIRE registry persistence (the PA definition)

Registry persistence is REQUIRED (and its absence is a LOUD failure, not a silent
skip) for any artifact that is **live-readiness-bearing**, defined as:

> A quantile-trio export whose acceptance `verdict ∈ {should_ship, shadow_only}`
> AND all three quantiles (q10,q50,q90) were written to disk
> (`entry["written"]==True` with a non-empty path).

Rationale: `shadow_only` is explicitly a canary candidate (it is what canary_promoter
selects via `canary_status='shadow'`). `should_ship` is even stronger. Only `no_ship`
(and unknown verdict) artifacts are exempt — those are intentionally not registered
(`register_model:188-199`), which is correct and must stay.

So: **non-`no_ship` + fully-written trio ⇒ registry row REQUIRED.**

### Required behavior change

Today `register_quantile_trio:327` silently drops `None` returns; an empty
`registered` list is indistinguishable from "DB down" or "verdict no_ship". Change so
that for a REQUIRED artifact (per criteria above):

- If `register_model` returns `None` due to **DB unavailable** or **unexpected
  no-op** (slot not locked, verdict valid, trio written) → the training job must
  FAIL LOUD: raise / non-zero exit / emit an explicit `registry_persistence_failed`
  status that the scheduler surfaces. Do NOT report training success.
- Distinguish the three `None` causes so the failure is honest:
  1. `verdict==no_ship`/unknown → expected skip (NOT a failure).
  2. slot locked in `promoting`/`production` (the WHERE-filter no-op,
     `model_registry:169-186`) → expected skip, log INFO (Operator owns that slot).
  3. DB unavailable / connect fail → REQUIRED-artifact FAILURE (this is the P1-14
     bug: runtime had 0 fresh rows).
  Implementation: have `register_model` return a small result object or sentinel
  distinguishing (skip_no_ship | skip_locked | skip_db_unavailable | row_id), OR
  the caller pre-checks DB connectivity once and fails loud if unavailable while
  REQUIRED artifacts exist. Prefer the caller-side connectivity precheck (smaller
  blast radius, no signature churn for other callers/tests).

### Tests (MIT + E4)
- REQUIRED artifact + DB unavailable → training pipeline exits non-zero / status
  `registry_persistence_failed` (assert NOT success).
- `no_ship` verdict → expected skip, training still succeeds.
- slot locked promoting/production → expected skip, INFO logged, success.
- After a staged run with DB up: MIT SELECT shows fresh `shadow` rows with
  `train_date == today`; canary_promoter candidate query returns them.

### Acceptance
Fresh `shadow_only`/`should_ship` trios become registry candidates with current
`train_date`, OR the job fails loudly. `model_registry` is no longer silently stale.

### Risk: 中 (training-job control flow + caller). Implementable-now (V023 table exists).

---

## P2-08 — Cost-Gate Semantics (Owner: PA decision + E1 Python; reads Rust ledger)

### Scope
- `bybit_ai_cost_log.py:76-160` (pricing/unpriced + log_ok).
- `bybit_query_budget_gate.py:113-123` (daily-exhaust check).
- `bybit_query_budget_runtime.py:223-292` (usd_meter_available=False).
- Route A allowlist/binder `misc_tools/bybit_bind_active_route_env.sh:87-91`.

### PA recommendations (spec'd to PM default)

**(a) Block unpriced paid calls (fail closed).** A paid provider-native call whose
pricing table is not bound (`pricing_table_bound==False`, `actual_cost_usd is None`)
CANNOT satisfy a cost-cap gate — by definition it cannot prove it is under budget.
Change `bybit_ai_cost_log.py`: for a paid call (not no_call_path_accepted) with
`pricing_table_bound==False`, add `pricing_not_bound_for_paid_call` to
`blocking_reasons` so `log_ok=False`. The current warning-only path (`:86`) stays
ONLY for free/local. Couple with P1-13: an unpriced paid call also fails the ledger
cost contract. (Optional secondary: if operator wants the call recorded-but-flagged,
write an explicit `learning.ai_usage_log` row with `cost_usd=NULL`/sentinel and a
`details.unpriced=true`, then still block progress — recommended over silent advisory.)

**(b) Read cumulative daily spend (meter it).** Wire `total_spent_today_usd` so
`bybit_query_budget_gate.py:113-123` actually enforces. Source of truth is the Rust
budget ledger — `usage_io.rs:100-118 load_mtd_usage` returns MTD per scope; for a
daily gate, either add a `load_today_usage` (same query, `>= date_trunc('day',NOW())`)
or have the Python H2-A policy builder read `learning.ai_usage_log` directly for
today's SUM(cost_usd). PA preference: keep budget metering in the Rust authority and
expose today's spend to the Python gate via the existing IPC/policy snapshot, so
there is one budget truth (consistent with Rust = config/risk authority). Flip
`usd_meter_available=True` only once this is wired. This depends on P1-13 (rows must
exist to sum).

**(c) Route A semantics.** Route A currently defaults to `anthropic_native` paid
cloud (`bybit_bind_active_route_env.sh:88`). Per root principle 14 (baseline operable
without external paid services), the "cheap fast pass" default should be the LOCAL/
FREE tier (Ollama L1), with paid Route A as an explicit opt-in env. PA recommendation:
change Route A default provider target to the local LLM path; keep paid Route A
available only when an env flag explicitly enables it. This keeps L0+L1 baseline free.
(This is the one item touching a behavioral default — flagged as operator decision below.)

### Tests
- Paid + unpriced → cost log blocked (`log_ok=False`).
- Daily spend ≥ daily budget (with real metered value) → budget gate blocks
  `daily_budget_exhausted`.
- Route A default with no paid opt-in → binds local provider, no paid spend.

### Acceptance
"recorded" never means "unpriced and unblocked" for paid calls; daily spend is read
and enforced; baseline runs free.

### Risk: 中-高 (changes default provider economics + gate enforcement).
(a) implementable-now. (b) depends on P1-13 ledger rows + may touch Rust/IPC (MIT).
(c) is a default-behavior change needing operator sign-off.

---

## Implementable-Now vs Migration/Deploy-Gated

| Item | Status |
|---|---|
| P1-12 enum/route normalization | Implementable-now (Python + shell, no DB). |
| P1-13 ledger wiring | Implementable-now — **NO migration** (V003/V010 tables + writers exist). Apply/deploy + Linux SELECT proof are operator-deploy-gated (verification only). |
| P1-14 registry loud-fail | Implementable-now (V023 table exists). |
| P2-08 (a) block unpriced | Implementable-now (Python). |
| P2-08 (b) daily-spend meter | Code implementable-now; if it touches Rust `load_today_usage`/IPC → MIT + cargo + Linux dry-run; depends on P1-13. |
| P2-08 (c) Route A default→local | Implementable-now but is a behavioral-default change → operator sign-off first. |

No new DB migration is required by Package D. No deploy, no real paid AI call, no
TODO/memory/TOML/secret edits performed in this spec.

## E1 Dispatch Plan (max parallel; file scopes disjoint)
- **E1-D1 (Python, thought_gate dir)**: P1-12 + P2-08(a) — selector/policy_builder/
  contract_check/cost_log + binder shell. Independent file set.
- **E1-D2 (Python, ml_training dir)**: P1-14 — model_registry + register caller +
  run_training_pipeline. Independent file set.
- **E1-D3 (Python, control_api_v1 + thought_gate invocation)**: P1-13 — H1-F
  invocation builder wiring to `record_ai_invocation` + ai_usage_log path.
- **P2-08(b)/(c)**: serialize AFTER P1-13 (b depends on ledger rows) and AFTER
  operator sign-off (c). Owner E1 + MIT if Rust/IPC touched.

## E2 Top-3 Review Focus
1. P1-13 paid-call ledger FAILURE path: confirm `record_ai_invocation`'s fail-soft
   boolean is escalated to a blocker in the paid path ONLY, and that free/local stays
   non-blocking — the easiest place to get fail-open wrong.
2. P1-14 the three `None` causes are distinguished — a DB-down must fail loud, but a
   `no_ship`/locked-slot must NOT, or we break legitimate training runs.
3. P1-12 binder: ensure the canonical `route_c_escalated_standard` is accepted and the
   selector→binder→provider chain has no remaining string drift (grep all three).

---

## Genuine Operator Decisions Still Needed

1. **P2-08(c) Route A default provider.** PA recommends Route A "cheap fast pass"
   default = LOCAL/FREE (Ollama L1), paid only via explicit env opt-in (root principle
   14). This changes current paid-by-default economics → needs operator sign-off.
2. **P2-08(a) unpriced-paid handling shape.** PA recommends BLOCK. Operator may instead
   prefer "record explicit unpriced ledger row (cost_usd=NULL) AND still block progress".
   Either satisfies fail-closed; pick the audit shape. (Default applied: block.)
3. **P2-08(b) budget-truth location.** PA recommends daily/MTD spend metered in the Rust
   BudgetTracker (single authority) and exposed to the Python H2 gate. Operator may
   accept a Python-side direct SUM of `learning.ai_usage_log` if avoiding Rust/IPC churn
   is preferred for this sprint. (No new table either way.)

All other Package D decisions are spec'd to the PM default and need no further input.

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--cold_audit_pkgD_ai_ml_lineage_spec.md

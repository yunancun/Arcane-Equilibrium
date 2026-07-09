# AI-E AI Usage Effectiveness / Truthfulness Audit (Re-Run)

Date prefix: `2026-05-30` (campaign label "2026-05-17").
Actual local audit run: 2026-05-30.
Repo root: `/Users/ncyu/Projects/TradeBot/srv`.
Role: AI-E(default), READ-ONLY (only artifact = this report).
Baseline: frozen `187704f6`; source delta since = ZERO (verified: `git log
187704f6..HEAD -- program_code/ai_agents/` returns 0 commits; the 5 commits on
top of baseline are all `docs(todo)` / `[skip ci]`).
HEAD at run: `fe8393e2`.

## Executive Verdict

P0: 0. P1: 0. P2 (open/structural): 1. P3 (open): 1.

RE-RUN after the ~2026-05-29 cold-audit closure (TODO v84). All seven prior AI-E
findings (AI-E-001..007 in `2026-05-17--ai_usage_effectiveness_audit.md`) were
remediated and source-landed (Wave1/2/3/4: b93d3210 / 11b9531f / 7909ca3d /
dc2a15aa / f2b020e5; closure archive
`docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`). This run
re-verified the highest-risk truthfulness + cost-ledger remediations against the
ACTUAL source and they HELD. NO new source shipped on 2026-05-29/30 in the AI
path.

AI-invocation truthfulness verdict: HONEST. The provider-native thought-gate
chain (a) writes the cost ledger ONLY when a model was actually invoked, (b)
explicitly emits no-call states, and (c) fails closed for PAID providers when the
durable ledger write cannot be made.

Cost-ledger completeness verdict: COMPLETE at source level — durable dual-table
writes (`agent.ai_invocations` + `learning.ai_usage_log`) with deterministic
idempotency dedup (MED-1 fix present). One residual STRUCTURAL gap: H2 cumulative
daily-USD cap enforcement is advisory/structural, not yet runtime-proven (carried
P2, deploy-gated). Linux PG empirical validation of the ledger ON CONFLICT
semantics is an OPEN deploy-gate (cross-role — see Blockers).

## ENV / Anti-Fabrication Note (load-bearing)

FACT: The harness `Bash` tool was unreliable this run: (i) one path-scoped grep
returned EMPTY that, alone, would have produced a FALSE "ledger absent" P0; (ii)
some stdout sanitized the table tokens `ai_invocations` / `ai_usage_log` to
`ln` / `n` and mangled a few line numbers; (iii) late greps returned empty
repeatedly. I therefore did NOT cite any path/line from grep stdout. Every
evidence line below was confirmed by reading the actual source file with the
`Read` tool (`bybit_ai_invocation_ledger.py` read in full L1-301; caller region
L505-601). An earlier internal draft cited non-existent filenames
(`agent_ai_ledger.py`, `bybit_h_stage_ai_ledger_writer.py`) and guessed line
numbers; those were discarded after direct reads. No finding rests on a single
flaky read.

## Prior-Remediation Verification (verified against actual source)

### V1 — AI-E-001/002 (P1-12): policy/route enum normalization — HELD
- FACT. `bybit_thought_gate_policy_builder.py:335` emits
  `policy_state = "policy_ready_standard"` (comment L332 cites "P1-12 enum
  归一化"). `bybit_ai_route_selector_builder.py:303` consumes the SAME set
  `{"policy_ready_light_only", "policy_ready_standard"}`.
  `bybit_bind_active_route_env.sh:104` allowlist includes
  `route_c_escalated_standard` (with route_c_strong / route_c_escalated /
  route_c). Consistent across builder / selector / bind.
- Impact closed: the prior "should_call_ai=true then no-invocation"
  (`h1b_policy_not_ready` / unbindable route C) drift is resolved end-to-end.

### V2 — AI-E-003 (P1-13) + MED-1: durable AI cost/invocation ledger — HELD
- FACT. Durable writer
  `program_code/ai_agents/bybit_thought_gate/bybit_ai_invocation_ledger.py`,
  `write_invocation_ledger()` (def L139). Two durable INSERTs in one tx:
  - `agent.ai_invocations` INSERT L222, `ON CONFLICT (invocation_id, ts) DO
    NOTHING` L234.
  - `learning.ai_usage_log` INSERT L260, `ON CONFLICT (time, scope, request_id)
    DO NOTHING` L268.
  - Wrapped in `with conn:` (L217); `except` sets failure (L283-293); `finally`
    closes conn (L294-298).
- MED-1 dedup fix PRESENT: `PAID_PROVIDERS = {"openai_native",
  "anthropic_native"}` (L40); `deterministic_event_ts()` (def L55) derives the
  time PK component from the idempotency_key — first from an embedded ms epoch in
  keys shaped `h1f_<now_ms>` (L73-76), else a `sha256(key)`-derived offset
  ANCHORED to the current month-start (L78-84) so retries land the same PK and MTD
  stays in the correct month. Module docstring L14-20 + code comment L58-71
  explicitly document that this fixes the "now() -> PK differs -> ON CONFLICT
  never hits -> double-billing" bug. Time component is used for both tables
  (L237, L271). This is the E2 catch recorded in the closure.
- Honest no-call (truthfulness): caller writes the ledger ONLY when a model was
  actually invoked — `bybit_ai_invocation_attempt_builder.py:556` guards on
  `invocation_attempted and provider_target in {openai_native, anthropic_native,
  ollama_local}`. H1-F itself does not price (`cost_usd=None`, L568); pricing /
  unpriced-paid block is deferred to H5-A cost_log.
- Paid fail-closed: no DB conn + paid -> `ok=False`,
  `ledger_state="invocation_ledger_write_failed"`, error `db_unavailable_for_
  paid_call` (L195-198); write exception + paid -> `ok=False` +
  `invocation_ledger_write_failed` (L285-289); local provider (ollama_local)
  write failure is best-effort warn, ok stays True (L199-201, L290-293) —
  consistent with zero-cost local. Caller escalates a paid failure to a blocker
  via `apply_ledger_governance(payload, ledger_result, blocking_reasons,
  warning_flags)` (L586). Tests `tests/test_ai_invocation_ledger.py` assert both
  tables written + dedup (same idempotency_key -> identical event_ts).

### V3 — AI-E-006 (P2-08): Route A defaults to local/free — HELD
- FACT. `bybit_bind_active_route_env.sh:87-95`: route_a_light default provider is
  `ollama_local` (L91); paid cloud only when `BYBIT_ROUTE_A_PAID_OPT_IN=1`
  (L90), and even opted-in an unset target falls back to `ollama_local` (L93-94,
  comment "避免静默付费"). Satisfies Root Principle 14 (operable without paid
  services); zero-external-cost L1 is the default.

### V4 — CLAUDE §七 no provider-HTTP-leak in business code — HELD (scoped)
- FACT. Direct provider SDK/HTTP endpoints (`api.anthropic.com` /
  `api.openai.com` / `anthropic.Anthropic(` / `openai.OpenAI(`) appear only in the
  designated Layer2 provider abstraction (`layer2_engine.py`,
  `provider_client.py`, `provider_keys_store.py`) — behind the
  `LocalLLMClient`/provider-client boundary, not leaked into strategy/risk/route
  business code or the thought-gate decision builders. The ledger writer itself
  issues NO provider HTTP (its docstring L21 states this) — DB-only.

## Open Findings (carried, not new — not truthfulness defects)

### AI-E-R30-01 — H2 cumulative daily-USD cap is advisory, not runtime-proven
- Label: INFERENCE (from prior FACT AI-E-005 + closure deploy-gate list).
- Severity: P2 (structural; NOT a fabrication/truthfulness defect).
- Path: `program_code/ai_agents/bybit_thought_gate/bybit_query_budget_gate.py`,
  `bybit_query_budget_runtime.py` (prior audit cited self-declared "USD metering
  not available"). P2-08 closure added cumulative-spend read, but end-to-end proof
  that (today_cumulative + this_call) <= DOC-08 $2/day cap BLOCKS a paid call is
  not demonstrable on Mac (mock PG).
- Impact: DOC-08 daily HARD cap enforced per-call structurally; cumulative
  fail-closed not yet empirically proven. Risk bounded: Route A default is
  local/free and paid is opt-in, so baseline spend is ~$0.
- Why real not FP: matches prior self-declared limitation; closure archive lists
  "PkgD Linux PG empirical" as an OPEN deploy-gate.
- Fix direction: Linux PG empirical dry-run proving cumulative-cap fail-closed.
- Fix owner: E1(worker) + MIT(default). Verifier: AI-E(default) + E3 (deploy-gate).

### AI-E-R30-02 — H3 "model router" is audit/explainability, not the selector
- Label: FACT (unchanged from AI-E-007; no source change since).
- Severity: P3 (naming/architecture clarity; no cost/truthfulness impact).
- Path: `bybit_model_router_policy.py` / `_decision.py` / `_runtime.py`. H3 reads
  provider/model already chosen upstream (H1-E envelope / H1-F invocation) and
  explains/validates; it does not select or correct the binding.
- Fix direction: rename to router-audit, OR move selection into H3 as SoT.
- Fix owner: PA(default). Verifier: AI-E(default) + R4(explorer).

## Did Prior Remediation Hold?

YES. All four load-bearing checks (enum/route normalization; durable dual-table
ledger + deterministic-dedup + paid fail-closed; Route-A local default; no
provider-HTTP leak) verified PRESENT in actual source at HEAD. The two still-open
items are the same structural P2 (runtime cap proof, deploy-gated) and P3 (router
naming) the closure already classified deferred/advisory — not regressions.

## Blockers Needing Cross-Role / Operator

1. PkgD Linux PG empirical (AI-E-R30-01): runtime proof that ledger ON CONFLICT /
   deterministic event_ts dedup AND cumulative daily-cap fail-closed hold under
   real PG. Needs E3 (deploy/runtime) + MIT + operator (read-only `ssh trade-core`
   inspection of `agent.ai_invocations` / `learning.ai_usage_log`). AI-E cannot
   prove this from Mac (mock PG).

## Suggested Read-Only Runtime Verification (operator/E3, Linux)

```bash
# durable ledger receiving rows + no double-billing (dedup intact) — READ ONLY
psql "$OPENCLAW_DATABASE_URL" -c "SELECT provider, model, count(*), sum(cost_usd)
  FROM learning.ai_usage_log
  WHERE time > now() - interval '7 days' GROUP BY 1,2 ORDER BY 4 DESC NULLS LAST;"
psql "$OPENCLAW_DATABASE_URL" -c "SELECT count(*), count(DISTINCT (invocation_id, ts))
  FROM agent.ai_invocations;"   -- equal counts => dedup PK intact
```

AI-E AUDIT DONE: report path: `docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-30--AI-E--ai_usage_effectiveness_audit.md`

# AI-E AI Usage Effectiveness / Truthfulness Audit

Date prefix: `2026-05-17` per operator request.  
Actual local audit time: 2026-05-29 Europe/Madrid.  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`.  
Role: AI-E(default), read-only audit.

## Scope And Constraints

FACT: This audit evaluated AI usage effectiveness, development status, actual integration readiness/usability, model routing, cost ledger coverage, and AI invocation truthfulness.

FACT: Focus areas were `should_call_ai=true` but no invocation, fake/synthetic AI, dishonest fallback, untracked cost, and routing claims not matching actual call paths.

FACT: I did not call external paid AI providers, deploy, restart, migrate, edit auth, edit live/demo/paper config, start trading, or mutate runtime. The only created artifact is this report.

FACT: AI-E's normal completion sequence asks to append AI-E memory, but the operator explicitly forbade editing memory/other docs, so memory was not updated.

Evidence command / inspection method:

```bash
sed -n '1,260p' AGENTS.md CLAUDE.md .codex/MEMORY.md
sed -n '1,260p' .codex/agents/AI-E.md .claude/agents/AI-E.md
sed -n '1,260p' docs/CCAgentWorkSpace/AI-E/profile.md docs/CCAgentWorkSpace/AI-E/memory.md
sed -n '1,260p' docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--cold_audit_baseline_freeze.md
sed -n '1,260p' docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md
sed -n '1,280p' docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md
rg -n "should_call_ai|provider_target|route_c|ai_usage_log|agent\\.ai_invocations|record_usage|record_ai_invocation" program_code rust sql
```

## Executive Verdict

No P0 found.

P1 found: 3.

The most important AI-readiness issue is not model quality. It is call-chain truthfulness and accounting: several paths can declare that AI should be called, but deterministic integration drift prevents the provider call, and the newer provider-native call path is not connected to the durable DB cost ledgers.

## Findings

### AI-E-001 — Standard-Tier `should_call_ai=true` Is Blocked By Policy-State Enum Drift

- Label: FACT
- Severity: P1
- Affected path + line:
  - `program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_policy_builder.py:332`
  - `program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_policy_contract_check.py:40`
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_route_selector_builder.py:303`
- Evidence command or inspection method:
  - `rg -n "policy_ready_standard_allowed|policy_ready_standard\\b" program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_policy_builder.py program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_policy_contract_check.py program_code/ai_agents/bybit_thought_gate/bybit_ai_route_selector_builder.py`
  - Static check result: policy builder emits `policy_ready_standard_allowed`; policy contract allows `policy_ready_standard_allowed`; route selector accepts `policy_ready_standard` instead and does not mention `policy_ready_standard_allowed`.
- Impact: A valid H1-B standard policy can pass H1-C and set `should_call_ai=true`, then H1-R blocks before route binding with `h1b_policy_not_ready`. That is a direct no-invocation path after an upstream AI-call decision.
- Why this is real, not false positive: The enum mismatch is exact and internal to production scripts, not a docs-only typo. The contract checker confirms the builder's enum, so the route selector is the outlier.
- Suggested fix direction: Normalize the H1-B policy-state enum across builder, contract checker, and route selector. Add a regression fixture where standard policy + fired trigger produces a non-skip route and progresses to H1-E/H1-F.
- Fix owner role: E1(worker), with PA(default) only if the enum name is intentionally changing.
- Verification owner role: AI-E(default) for call-chain truthfulness, E4(worker) for regression.

### AI-E-002 — Route C Emits An Unbindable Route Name, So Escalated Calls Lose Provider/Model Binding

- Label: FACT
- Severity: P1
- Affected path + line:
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_route_selector_builder.py:331`
  - `program_code/exchange_connectors/bybit_connector/misc_tools/bybit_bind_active_route_env.sh:97`
- Evidence command or inspection method:
  - `rg -n "route_c_escalated_standard|route_c_escalated\\b|route_c_strong\\b|route_c\\b" program_code/ai_agents/bybit_thought_gate/bybit_ai_route_selector_builder.py program_code/exchange_connectors/bybit_connector/misc_tools/bybit_bind_active_route_env.sh`
  - Static check result: route selector emits `route_c_escalated_standard`; bind script recognizes `route_c_strong`, `route_c_escalated`, and `route_c`, but not `route_c_escalated_standard`.
- Impact: The highest-value/highest-urgency route C path can set `should_call_ai=true`, then bind no provider/model and cause H1-E/H1-F to block with provider/model missing. This is exactly the class of "should call AI but no invocation" failure requested in scope.
- Why this is real, not false positive: The route selector's own downstream fields map `route_c_escalated_standard` to `ROUTE_C`, but the shell binding script uses a different allowlist. There is no alternate binding script found by `rg BYBIT_AI_ACTIVE_PROVIDER_TARGET`.
- Suggested fix direction: Update route binding to accept the emitted route name, or change the selector to emit an existing accepted name. Add an end-to-end static/runtime fixture for route C from selector output through active env exports and request envelope.
- Fix owner role: E1(worker).
- Verification owner role: E4(worker), with AI-E(default) verifying route/cost semantics.

### AI-E-003 — Provider-Native AI Calls Are Not Connected To Durable Cost / Invocation Ledgers

- Label: FACT
- Severity: P1
- Affected path + line:
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_invocation_attempt_builder.py:385`
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_invocation_attempt_builder.py:515`
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_log.py:201`
  - `program_code/exchange_connectors/bybit_connector/misc_tools/bybit_h_stage_common.py:46`
  - Existing durable writers: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_event_store.py:216`, `rust/openclaw_engine/src/ai_budget/usage_io.rs:61`
- Evidence command or inspection method:
  - `rg -n "INSERT INTO agent\\.ai_invocations|INSERT INTO learning\\.ai_usage_log|record_ai_invocation|record_usage|write_report\\(|write_json\\(" program_code/ai_agents/bybit_thought_gate program_code/exchange_connectors/bybit_connector/misc_tools/bybit_h_stage_common.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_event_store.py rust/openclaw_engine/src/ai_budget/usage_io.rs`
  - Inspection: H1-F performs OpenAI/Anthropic SDK calls, then writes `bybit_ai_invocation_attempt_latest.json`; H5-A writes `bybit_ai_cost_log_latest.json`; neither calls `AgentEventStore.record_ai_invocation` nor Rust `BudgetTracker.record_usage`.
- Impact: Paid provider calls can occur without a durable DB invocation row or `learning.ai_usage_log` row. Monthly/daily cost ledgers, ROI calculations, and later truthfulness audits can undercount real spend.
- Why this is real, not false positive: Durable DB insert paths exist elsewhere, but the provider-native thought-gate path does not invoke them. JSON latest/dated files are audit artifacts, not the canonical cost ledger described by the Rust budget module.
- Suggested fix direction: Make the provider-native call path write a durable pre/post invocation record. For paid providers, fail closed if the budget ledger write cannot be made, matching the Rust `ai_budget` contract that usage write failure aborts the call.
- Fix owner role: E1(worker) for wiring; MIT(default) for DB/ledger contract if schema mapping is nontrivial.
- Verification owner role: AI-E(default) + MIT(default).

### AI-E-004 — Cost Log Can Be Marked Recorded While Actual USD Cost Is Unavailable

- Label: FACT
- Severity: P2
- Affected path + line:
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_log.py:76`
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_log.py:139`
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_log.py:155`
- Evidence command or inspection method:
  - `nl -ba program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_log.py | sed -n '71,160p'`
  - Inspection: `actual_cost_usd` is `None` when pricing is unbound; unbound pricing only becomes a warning flag; `log_ok` is still true if no blocking reasons, producing `ai_cost_log_recorded_soft_warn`.
- Impact: The system can present a cost log as recorded even though the monetary cost is unavailable. This weakens DOC-08 budget/cost-edge enforcement and makes "recorded" ambiguous for paid-provider calls.
- Why this is real, not false positive: The branch is explicit: `pricing_table_bound` controls `actual_cost_usd`, but not `log_ok`. The warning string does not prevent progression to H5-B.
- Suggested fix direction: For `should_call_ai=true` paid-provider paths, make missing pricing a blocking state or write an explicit `unpriced_paid_call` ledger row that cannot satisfy budget/ROI gates.
- Fix owner role: E1(worker) with AI-E(default) for pricing policy.
- Verification owner role: AI-E(default).

### AI-E-005 — H2 Budget Runtime States That USD Metering Is Not Available

- Label: FACT
- Severity: P2
- Affected path + line:
  - `program_code/ai_agents/bybit_thought_gate/bybit_query_budget_gate.py:113`
  - `program_code/ai_agents/bybit_thought_gate/bybit_query_budget_runtime.py:223`
- Evidence command or inspection method:
  - `nl -ba program_code/ai_agents/bybit_thought_gate/bybit_query_budget_gate.py | sed -n '107,123p'`
  - `nl -ba program_code/ai_agents/bybit_thought_gate/bybit_query_budget_runtime.py | sed -n '223,292p'`
  - Inspection: H2-B says `total_spent_today_usd` is not yet tracked by H2-A; H2-C hardcodes `usd_meter_available = False`.
- Impact: Daily cap enforcement is structural rather than actual. Even if per-call shape passes, H2 cannot prove cumulative spend is under the daily cap for provider-native calls.
- Why this is real, not false positive: This is a self-declared limitation in the budget gate and runtime output, not an inference from missing runtime data.
- Suggested fix direction: Read cumulative daily spend from the durable cost ledger before permitting paid calls. Until then, mark H2 as advisory/structural only and do not use it as proof of DOC-08 cap enforcement.
- Fix owner role: E1(worker) + MIT(default).
- Verification owner role: AI-E(default).

### AI-E-006 — "Light / Cheap-Fast" Route Defaults To Paid Cloud And Cannot Use Local Ollama In The Provider-Native Path

- Label: FACT
- Severity: P2
- Affected path + line:
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_route_selector_builder.py:15`
  - `program_code/exchange_connectors/bybit_connector/misc_tools/bybit_bind_active_route_env.sh:87`
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_request_envelope_builder.py:175`
  - `program_code/ai_agents/bybit_thought_gate/bybit_ai_invocation_attempt_builder.py:331`
- Evidence command or inspection method:
  - `rg -n "route_a_light|BYBIT_ROUTE_A_PROVIDER_TARGET|provider_target not in|openai_native|anthropic_native|ollama" program_code/ai_agents/bybit_thought_gate program_code/exchange_connectors/bybit_connector/misc_tools/bybit_bind_active_route_env.sh`
  - Inspection: route A is documented as light/cheap-fast; binding defaults route A to `anthropic_native`; request/invocation allowlists only accept `anthropic_native` and `openai_native`. A local Ollama provider target would be rejected by this path.
- Impact: The current provider-native route A does not satisfy the project's stated zero-external-cost L1 routing principle. It may be "cheap" relative to stronger cloud models, but it is not L1 local and not zero API cost.
- Why this is real, not false positive: The accepted provider allowlists exclude Ollama/LM Studio in both H1-E and H1-F. Separate legacy Ollama wrappers exist, but this provider-native thought-gate path cannot route to them.
- Suggested fix direction: Either add a real local provider target to H1-E/H1-F, or rename/re-document route A as a paid cloud-light lane and keep it out of DOC-08 L1-local compliance claims.
- Fix owner role: PA(default) for route semantics; E1(worker) for implementation.
- Verification owner role: AI-E(default).

### AI-E-007 — H3 Model Router Is A Post-Hoc Explanation Layer, Not The Provider Selector

- Label: FACT
- Severity: P3
- Affected path + line:
  - `program_code/ai_agents/bybit_thought_gate/bybit_model_router_policy.py:29`
  - `program_code/ai_agents/bybit_thought_gate/bybit_model_router_decision.py:35`
  - `program_code/ai_agents/bybit_thought_gate/bybit_model_router_runtime.py:39`
- Evidence command or inspection method:
  - `nl -ba program_code/ai_agents/bybit_thought_gate/bybit_model_router_policy.py | sed -n '21,121p'`
  - `nl -ba program_code/ai_agents/bybit_thought_gate/bybit_model_router_decision.py | sed -n '28,129p'`
  - Inspection: H3 reads provider/model already selected in the H1-E request envelope and H1-F invocation, then explains or checks them. It does not choose the active provider/model.
- Impact: Naming this a "model router" can overstate integration readiness. It can validate/explain a route, but it cannot correct a bad binding or switch to a cheaper local model.
- Why this is real, not false positive: H3 `provider_target` and `model_name` are loaded from prior request/invocation artifacts. No call to provider selection or env binding is performed in H3.
- Suggested fix direction: Rename H3 to router audit/explainability, or move provider/model selection into H3 and make H1-E consume H3 output as the single source of truth.
- Fix owner role: PA(default) for architecture naming; E1(worker) if code ownership changes.
- Verification owner role: AI-E(default) + R4(explorer) for docs/name consistency.

## No-Issue / Lower-Risk Notes

- FACT: The H1-F invocation builder does distinguish dry-run from real SDK invocation using `BYBIT_AI_DRY_RUN`, and it records `invocation_attempted=false` for dry-run. That part is truth-preserving.
- FACT: H1-G/H1-H explicitly label legal no-call synthetic observations as no-AI terminal paths. This is acceptable only when upstream `should_call_ai` is truly false; Findings AI-E-001 and AI-E-002 matter because integration drift can create false no-call states before that terminal path.
- INFERENCE: The older 5-Agent Ollama path has separate `AgentEventStore` and `Layer2CostTracker` hooks. This audit did not reclassify that entire legacy path as fake AI. The highest-risk issues above are in the newer provider-native thought-gate chain.

## Suggested Follow-Up Verification Commands

```bash
python3 - <<'PY'
from pathlib import Path
print('route_selector_accepts_standard_allowed',
      'policy_ready_standard_allowed' in Path('program_code/ai_agents/bybit_thought_gate/bybit_ai_route_selector_builder.py').read_text())
print('bind_accepts_route_c_escalated_standard',
      'route_c_escalated_standard' in Path('program_code/exchange_connectors/bybit_connector/misc_tools/bybit_bind_active_route_env.sh').read_text())
PY
```

```bash
rg -n "INSERT INTO agent\\.ai_invocations|INSERT INTO learning\\.ai_usage_log|record_ai_invocation|record_usage" \
  program_code/ai_agents/bybit_thought_gate \
  program_code/exchange_connectors/bybit_connector/control_api_v1/app \
  rust/openclaw_engine/src/ai_budget
```

AI-E AUDIT DONE: report path: `docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-17--ai_usage_effectiveness_audit.md`

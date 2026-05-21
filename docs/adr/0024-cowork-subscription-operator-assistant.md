# ADR 0024-lite: Cowork Subscription as Operator-Assistant (Not Autonomous L2)

Date: 2026-05-20
Status: Accepted-pending-commit

## Context

ADR-0020 (2026-05-09) decided Layer 2 cloud LLM is manual+supervisor-only,
prohibiting autonomous loops. Operator 2026-05-20 mandated dual-track
architecture with Track B requiring some form of LLM-driven hypothesis
generation. Original ADR-0024 draft (v4.1) proposed full autonomous L2
within budget envelope.

2nd reviewer audit 2026-05-20 critiqued this as overreach: Claude Max +
ChatGPT Plus subscriptions are operator-assistant tools, not production
autonomous components. ADR-0020 prohibition rationale (governance audit,
cost predictability, blast radius containment) applies equally to whether
LLM is API or subscription based.

This ADR (-lite suffix) is the minimal carve-out: codify how Cowork
subscription is allowed to participate in the system as operator-assistant
WITHOUT becoming production autonomous L2.

The full ADR-0024 autonomous L2 within budget envelope is deferred to Year
2; revival requires fresh operator + governance review.

## Decision

Cowork subscription (Claude Max, ChatGPT Plus, ChatGPT Team, similar
subscription-based LLM access) is treated as **operator-assistant** with the
following bounded surface:

### Allowed Uses

1. **Operator-initiated interactive analysis**: operator opens Cowork
   session and asks Claude/GPT to analyze trade logs, market state,
   hypothesis candidates, or design questions. Output: markdown / files
   to operator's working directory. **Operator reviews before any state
   change.**

2. **Scheduled Cowork tasks** (per
   `mcp__scheduled-tasks__create_scheduled_task`): periodic Cowork session
   triggers that:
   - Read `trading.fills` / `trading.signals` / `agent.ai_invocations` /
     `learning.cost_edge_advisor_log` for past 24h (read-only)
   - Write markdown analysis files to operator working directory
   - Optionally write to `learning.hypotheses` table with state =
     `DRAFT` and source = `cowork_assistant`
   - **Output is informational only**; cannot transition hypothesis state
     past DRAFT without operator manual approval via Console

3. **Cowork session writes hypothesis spec JSON**: into
   `learning.hypotheses` (DRAFT state only) — operator promotes to
   REGISTERED only through manual Console action.

### Forbidden Uses

1. **Cowork CANNOT transition any hypothesis state machine** past DRAFT
   automatically; all REGISTERED / EXPERIMENTING / PROMOTED transitions
   require operator manual Console action.

2. **Cowork CANNOT modify runtime config** at any level:
   - No risk_config_*.toml mutation
   - No strategy parameter runtime update
   - No live authorization grant
   - No live_reserved flag mutation
   - No Decision Lease state mutation
   - No order submission

3. **Cowork CANNOT bypass Guardian / H0 Gate / Decision Lease**: all trade
   side-effects route through existing Rust authority chain as in
   ADR-0001.

4. **Cowork CANNOT operate as 24/7 autonomous trading loop**: scheduled
   tasks are bounded frequency (max 4 per day) and bounded scope
   (read-mostly with whitelisted markdown / hypothesis-DRAFT writes only).

5. **Cowork CANNOT impersonate or substitute for L1 Ollama**: L1 Ollama
   continuous decision support remains the local-only, zero-marginal-cost
   path for runtime-touching analysis; Cowork is operator-time-bound.

### Cost & Audit Properties

- All Cowork invocations leave audit trail in `agent.ai_invocations` with:
  - `invocation_type` = `'cowork_operator_assist'` or
    `'cowork_scheduled_task'`
  - `track` = `'baseline'` (no specific track ownership; operator-mediated)
  - Cost recorded as $0 (subscription is sunk cost; no marginal API
    spend); but invocation count + tokens-consumed are logged
- Monthly subscription cost ($200 Claude Max + $200 GPT Plus) is treated
  as **operator overhead expense**, not as track-specific or
  invocation-specific cost.

### Relationship to ADR-0020

ADR-0020 prohibition on Layer 2 autonomous trading loop, runtime config
mutation, order submission, live authorization, and Rust authority bypass
**REMAINS IN FORCE for both Cowork subscription and API-based L2**.

This ADR-0024-lite does NOT carve out anything ADR-0020 prohibited; it
clarifies that the allowed `operator-assistant` use case fits within
ADR-0020's "GUI/manual supervisor escalation" allowance, expanded to
include scheduled tasks that produce informational output without state
transitions.

### Relationship to Future Full ADR-0024

A future full ADR-0024 (autonomous L2 within budget envelope) may be
proposed when:

1. Track A delivers verifiable demo evidence per AMD-2026-05-20-03 §5.1
2. Track B Hypothesis Ledger (manual-fed via this ADR's allowed uses)
   accumulates ≥10 operator-validated hypothesis
3. Operator + Reviewer + PA + QC agree autonomous L2 adds value beyond
   operator-assistant
4. Fresh budget envelope + monitoring + kill switch spec land

Until then, this ADR-0024-lite is the only authorized LLM-on-the-machine
pattern.

## Consequences

- Operator's existing $400/month subscription cost (Claude Max + GPT Plus)
  is **fully utilized** as operator-assistant + scheduled tasks; no need
  for additional API budget for Track B early-phase work.
- Track B Hypothesis Ledger in N+1-N+3 is **manually fed by operator
  through Cowork sessions** (write DRAFT hypothesis specs); no autonomous
  generator.
- Cowork-written DRAFT hypothesis specs are visible in
  `learning.hypotheses` but never auto-promote; operator-mediated state
  machine only.
- No new API budget needed in v4.2 sprint scope; v4.1 plan's $30-50/mo
  envelope is **withdrawn** until full ADR-0024 reviewed.
- Audit trail preserved in `agent.ai_invocations` with subscription-flag
  tagging.
- Scheduled task framework (`mcp__scheduled-tasks__*`) is already
  available; no new infrastructure needed.

## Reviewer Audit Trail

2nd reviewer audit 2026-05-20 §10 raised: "Claude Max/Cowork subscription
只能做 operator-assistant，不可當 production autonomous L2；ADR-0024-lite
先 ratify". v4.2 accepts in full. Original ADR-0024 (full autonomous L2)
is **withdrawn** from v4.2 scope and re-classified as a Year 2 candidate.

## References

- ADR-0020 Layer 2 manual-only
- AMD-2026-05-20-03 (ratifies v4.2 including this ADR)
- v4.2 spec: `srv/2026-05-20--dual-track-architecture-v4.2.md` §3
- `mcp__scheduled-tasks__create_scheduled_task` (existing infrastructure)

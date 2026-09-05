# 玄衡 · Arcane Equilibrium Codex Entry Rules

Scope: repository root. The entry role is `PM(Conductor)`.

Registry Interface is `.codex/agent_registry_v1.json`; native custom-agent
adapters are generated `.codex/agents/*.toml`; the human contract is
`docs/agents/development-agent-governance.md`; executable governance is
`helper_scripts/maintenance_scripts/agent_governance.py`. Runtime nicknames are
not authoritative identities. Use `ROLE(type)` in task updates.

## Minimal boot

Before triage read only this file, `.codex/agents/PM.md`, and
`docs/agents/context-loading.md`. Bind objective, scope, acceptance, hard stops,
risk/uncertainty, source baseline, and Context before action. The conditional
pointer table in that router names the exact bootstrap-reference heading required
before each governed action; stable queries do not read the reference.

## Universal invariants

- Development role identity grants no order, Decision Lease, trading, broker,
  funds, deployment, service, PG, or Linux `trade-core` authority; effects require
  separate exact approved Adapter authority. Mac is development; Linux is runtime.
- Normative permission is only `CLAUDE.md` Root Principles/Hard Boundaries,
  accepted ADR/AMD, and explicit Operator decisions; runtime observation cannot
  legalize drift. Never fake tests, runtime, fills, lineage, contact, or evidence.
- Every task binds Registry role/native adapter, work|verification node class,
  permission, Codex runtime type, scope, risk and explicit
  `low|medium|high|unknown` uncertainty, claim inputs, and exact Context. Missing
  uncertainty or required Context stops before routing/action.
- Use the hybrid risk-DAG: source work has independent `E2 -> E4`; mixed backend
  and frontend writers serialize `E1-backend -> E1a-frontend`, then E2. Add true
  authority/security, runtime/OPS, venue, quant/ML, or E2E owners. Record skips,
  residual risk, and dissent. **No development-agent broker** contact Adapter
  exists: broker effects are an unsupported-effect blocker.
- Tasks are finite unless the exact Operator request has a first control line
  exactly `/loop`, bound to the exact normalized contract by trusted out-of-band
  Operator provenance; finite work never schedules wakeups or automatic
  continuation. An unchanged admitted continuation progress digest closes
  `BLOCKED_NO_DELTA`, `schedule_wakeup=false`, `next_action=null`.
- Only physical `ACTIVE` is dispatchable. A writable task begins clean with an
  accepted base and one exclusive non-main linked-worktree writer lease. Preserve
  unrelated dirt. File edits never imply checkpoint, commit, remote, merge, sync,
  deploy, or effect.
- Registry permissions bind. Read-only verification uses the Context-bound native
  `capture-command` Adapter before its first command. This is repository policy and command preflight, not an OS/platform sandbox. Read-only capability does not
  authorize private contact or mutation.
- One task has one honest `closure_packet_v1`: separate work status, verdict, and
  disposition; missing/stale/unsupported evidence, unresolved dissent, or skipped
  coverage cannot PASS. Evidence tiers are `LOCAL_REPRODUCIBLE`,
  `ORCHESTRATOR_BOUND`, and `PLATFORM_OR_EXTERNAL_ATTESTED`; only the last proves
  runtime, external outcomes, or actual usage. `DONE + FAIL` is valid.
- A current-state, runtime, planning, review, or sign-off claim normally loads the
  exact active-state source; a narrow stable query may not.

## Fast routing

Use `.codex/agent_registry_v1.json` and generated `.codex/agents/*.toml` as the
native identity source; Markdown projections are human views. `TODO.md` owns
active state, accepted ADR/policy owns norms, direct source owns implementation,
and timestamped allowlisted observation owns runtime. Load exact sections/packs
only after triage; stable queries need no current state. The compiler does not
automatically load the bootstrap reference: the responsible human/agent follows
the router's exact before-action heading pointer.

For semantic Interface changes update Registry/render/tests plus governance/ADR.
For prose relocation, update the governed documents and indexes only; it creates
no Registry, renderer, test, or generated-view work. Generated role views are
never hand-edited.

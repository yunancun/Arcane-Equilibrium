# Sub-Agent Hygiene SOP

Canonical permissions: `.codex/agent_registry_v1.json`
Workflow: `docs/agents/development-agent-governance.md`

Use this SOP whenever a delegated task touches Rust/Cargo, Linux `trade-core`,
PG, deploy, service/cron, runtime verification, or broker contact.

## Dispatch declaration

The prompt declares role/type, owned scope, task shape, expected fragment/patch,
context digest, acceptance, hard stops, and verification surface. Unknown or
colliding ownership stops before edits.

## Mac source vs Linux runtime

- E1/E2/E4 source and cargo verification runs on Mac.
- Delegated roles never run Linux cargo build/test/check/clippy/run.
- Linux evidence is allowlisted read-only observation: process/status/log/file
  metadata, approved healthcheck, and source/build pin.
- Direct `psql` is disabled, including apparent SELECTs, until a local-socket/
  read-only-identity Adapter removes ambient `psqlrc` and `PG*` routing. A PG
  claim without a separately authorized platform-attested artifact stays
  UNVERIFIED.
- Linux PG write, sudo, restart, service/cron/env mutation, secret read, private
  broker effect, and unapproved external contact are denied.
- Mac engine not running is expected and is not runtime failure evidence.

Read-only roles invoke the exact verification argv only through the Context-bound Adapter:

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py capture-command \
  --native-agent NATIVE --node-id NODE \
  --context-artifact @context.json -- <argv...>
```

Do not preflight and then run the argv separately or evade denial by changing
shell spelling. `repository_policy_only` detects repo mutation but cannot prove
network/effect isolation; return an Adapter intent or blocker.

## Deploy seam

```text
green source/test evidence
-> OPS read-only preflight + rollback plan
-> PM/operator approves exact deployment_intent_v1
-> Deploy Adapter validates exact intent + runtime-environment contract
-> without a trusted reproducible local runtime probe: INTENT_VALIDATED_APPLY_DISABLED
-> no apply receipt, OPS postcheck PASS, QA outcome claim, or successful effect closure
-> reopen only after the missing probe/Adapter trust boundary is implemented and tested
```

OPS never applies and never treats PM's trigger/intent validation as a postcheck.
Preflight payload binds intent digest/source HEAD/component. The postcheck/effect
receipt contract is retained as a fail-closed target, not evidence that apply is
currently enabled.
Security stays with E3; Bybit/IBKR compatibility stays with BB/IB.

## Dirty-tree and checkpoints

- Read `git status` before edits; preserve unrelated WIP.
- One writer owns a file at a time. Use isolation only for genuinely colliding
  or destructive scopes.
- Sub-agents do not stage/commit/push unless the dispatch explicitly grants that
  exact checkpoint authority.
- A killed/retried Builder resumes from owned diff/checkpoint; it does not redo a
  completed milestone.
- No per-role report/memory writes. Return one immutable `role_fragment_v1`.

## Test evidence

Report exact command, exit, selected tests, source/diff/untracked/toolchain/env/
config signature, and whether proof was EXECUTED or REUSED. Linux/source/runtime
evidence are separate scopes. Both EXECUTED and REUSED checks reference a
validated Context-bound `command_capture_v2`; reuse also preserves its hash/TTL assessment.
Second run is required only for critical, failed, known-flaky, or release-gate
evidence; critical flaky fails.

Evidence assurance is explicit. `LOCAL_REPRODUCIBLE` repository/command captures
prove recapturable bytes; `ORCHESTRATOR_BOUND` call/wave receipts prove exact
controller-known task/context/role/result lineage; runtime/E2E/external/actual-
usage facts require `PLATFORM_OR_EXTERNAL_ATTESTED` capture. Self-digests prove
integrity only. Unit tests cannot stand in for E2E outcomes, source captures
cannot stand in for runtime, and repo writes require an exact before/after
`repository_change_record_v1` bound to the writer task/role/node/scope.

## Background-wave liveness

For desktop saved workflows, a pause may kill in-flight agents. Stay in-turn
while a wave runs. Resume from journal/checkpoint; no unchanged blind retry.
Platform transcript activity is preferred over worktree silence as liveness
evidence. Exact platform-specific handling belongs in `agent-wave`, not every
role prompt.

When statting the session's `subagents/agent-*.jsonl` for liveness, also check
byte size. A transcript growing past a threshold (suggested 10 MB) is a
`RUNAWAY_SUSPECT`: apply the existing TaskStop preconditions and let PM
adjudicate the stop. Transcript bytes are a proxy monitoring signal only; they
must never stand in for actual-usage accounting (see the development-agent
governance consumption truth contract).

Every workflow retains one canonical call record per attempt and a complete
wave ledger for admitted nodes, retries, nulls, planned input lower bounds,
coverage debt, and controller-overhead exclusions. Those counts are structural
accounting, not actual token/cache/tool/time telemetry.

## Stop conditions

Stop and return owner/unblock condition on hard-boundary conflict, contradictory
authority classes, missing mandatory context, denied command, unsafe deploy,
stale runtime proof, broker gate denial, or unowned collateral changes. Budget
review points trigger split/escalation, never PASS.

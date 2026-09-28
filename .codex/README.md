# Codex Workspace

This directory is the repo-synced workspace for Codex.

Purpose:
- Keep durable Codex notes in the repository instead of relying on hidden app state
- Make Codex handoff and reuse explicit across Mac, Linux, and future sessions
- Stay safe for git sync: no secrets, no runtime dumps, no local-only machine paths unless clearly documented

Recommended layout:
- `../AGENTS.md` - git-root auto-load entry rules for new Codex sessions
- `agent_registry_v1.json` - canonical development-agent capability/permission registry
- `config.toml` - native Codex fan-out bound (`max_concurrent_threads_per_session=3`); governed workflow policy separately forbids recursive child fan-out
- `agents/*.toml` - generated native Codex identities; Markdown siblings are human views
- `config.toml` registers the native child-recursion hook in `helper_scripts/maintenance_scripts/codex_subagent_guard.py`. Review and trust its exact definition through Codex `/hooks` before relying on it; untrusted hooks are skipped. It denies child spawn/follow-up/agent-control calls while allowing a verified parent. Unknown caller metadata is denied; automatic final results remain available.
- `schemas/closure_packet_v1.schema.json` - one machine-checkable task closure contract
- `schemas/closure_quality_followup_v1.schema.json` - immutable closure-digest follow-up state; unknown telemetry stays scheduled/unavailable
- `schemas/closure_quality_attestation_v1.schema.json` - external/platform durable-closure observation payload; schema alone does not confer trust
- `MEMORY.md` - compact stable operating memory; deep history is archived/on demand
- `WORKLOG.md` - rolling notes for recent Codex work
- `DISPATCH_LEDGER.md` - durable record of meaningful PM-first dispatch chains
- `AGENT_DISPATCH_PROTOCOL.md` - PM-first session and delegation rules
- `SUBAGENT_EXECUTION_RULES.md` - mandatory role binding and anti-anonymous dispatch rules
- `agents/*.toml` - generated native Codex custom agents; adjacent Markdown is human view only
- `skills/` - Codex index over the shared Claude skill corpus
- `reports/` - exceptional task-owned analyses, not automatic per-role output
- `archive/` - retired notes that should stay searchable

Ground rules:
- `.codex/agent_registry_v1.json` owns development-agent roles; `CLAUDE.md` owns product boundaries; `TODO.md` owns active dispatch state
- `docs/agents/context-loading.md` defines where each class of context belongs
- `docs/agents/todo-maintenance.md` defines how agents must update `TODO.md`
- Load context through `helper_scripts/maintenance_scripts/agent_governance.py`; do not universal-preload this folder
- Treat self-digests as integrity only: source/test claims use `LOCAL_REPRODUCIBLE` captures plus `ORCHESTRATOR_BOUND` verification; runtime/E2E/external/actual-usage claims require `PLATFORM_OR_EXTERNAL_ATTESTED` capture
- Require explicit uncertainty and pre-spawn Registry binding of role/native-agent/node-class/permission; PA/E4 writer and verifier identities are distinct
- Native read-only verification runs only through one Context-bound `capture-command` call (`--native-agent`, admitted node, immutable Context, then argv after `--`); the compact receipt binds task and whole-repo generations, but `effect_enforcement=repository_policy_only` is not host network/effect isolation
- Every saved workflow preserves canonical call-manifest/wave receipts; orchestrator ledgers exact-cover every captured wave, repo writes need before/after change records, and EXECUTED/REUSED checks need trusted-local-replayable command captures; absent a host verifier, Closure intentionally re-executes before strong PASS
- Serialized event-ledger digests are offline integrity only: post-hoc wave reconstruction is deterministic structural assembly and never mints a controller; the separate internal pre-action seam uses a process-lifetime single-issue, non-serializable, live-Registry-bound controller with a locked monotonic head plus policy/surface authority derived from one Registry snapshot, canonical-detaches each full ledger/event once under that lock, never uses caller-owned mutable mappings for cap/coverage decisions, exposes no public caller-named mint, and gives persisted or caller-resealed ledgers no resume authority
- Repository authority values equal the exact pinned Context-byte identity projection; interpreted semantics use typed claim evidence rather than reusing a source digest
- A Registry effect seam or runtime path is not executable authority: deploy apply and development-agent broker/private contact stay fail closed until their trusted Adapter contracts are complete
- Direct `psql` stays disabled until a local-socket/read-only-identity Adapter removes ambient `psqlrc` and `PG*` routing
- Do not store credentials, tokens, raw secrets, or volatile runtime state here
- Keep entries short, factual, and easy to diff; persist one closure instead of role-by-role duplicates

Native dispatch remains disabled. The recursion hook fixes one demonstrated
client gap: per-role `agents.enabled=false` / multi-agent feature flags did not
prevent a child spawn. It does not provide frozen parent-task/path bindings,
call/deadline accounting, or task admission, and is not permission to enable
generic delegation. Codex owns hook trust and runtime error handling; a missing,
disabled, failed or untrusted hook is not an attested enforcement boundary.
Verify actual native-call rejection on the current client. Tool visibility alone
neither proves nor disproves pre-call rejection.
On Codex 0.158.0-alpha.2.1, linked worktrees inherit hook declarations from the
main checkout, even when other settings come from the worktree. Check the
effective hook list before a probe; an unmerged worktree hook is not loaded
automatically. A one-invocation override can test the exact reviewed candidate,
but that test does not attest persistent installation or trust.

Persistence note:
- Codex does not rely on a repo-local hidden memory store that is automatically shared across sessions
- For this project, durable/shared Codex memory should be written into files under this directory
- New Codex sessions should be guided first by `AGENTS.md` at the git root, then by the files here

## Controlled CLI review

The Operator-approved project entry is
`helper_scripts/maintenance_scripts/codex_subagent_runner.py`. PM keeps the existing
DAG and implementation ownership; this entry executes one declared read-only
node. It does not turn on native automatic delegation or start work on its own.

Compile the role Context at a clean, approved local checkpoint with the existing
`agent_governance.py context` command. Include the delivery's stable `work_item_id`
and `lane_id`. Freeze one review question in a file outside the source checkout:

```sh
python3 helper_scripts/maintenance_scripts/codex_subagent_runner.py \
  --context /absolute/task/E2-context.json --node independent_review \
  --instruction /absolute/task/E2-question.txt --output /absolute/task/E2-run \
  --codex /absolute/path/to/installed/codex --deadline 180
```

The output directory must be new and outside source/Git metadata. `CODEX_THREAD_ID`
binds the calling Codex controller. The runner validates the exact Context and
generated role, sends semantic context once without parent-history inheritance,
and uses the Registry model/effort. It grants source read access and only the
run's scratch write access, with tool network access disabled. E4 test commands
still use the existing Context-bound `capture-command`, governed pytest bootstrap,
and committed-subject requirement. This is not a general shell/network worker.
The outer controller needs process enumeration (`ps`) and access to its existing
Codex model service; missing process monitoring denies dispatch before a model
call. On macOS the child sandbox denies `ps`, so the separate-session cleanup
integration test requires a host capture; a child-side skip is not execution.

One review runs at a time per delivery; mandatory review predecessors must PASS
on the same source generation. A source repair invalidates the older PASS for
successor admission and requires the one explicit bounded recheck.
Persistent spent attempts live under Git common-dir `codex-cli-reviews`; new output
folders or Context hashes do not reset them. Registry total-call/wall-clock caps
apply; each call defaults to 180 seconds, capped at 300 seconds and the Context
budget. A node can have only its initial call and one explicit original-blocker
recheck (`--recheck-of <failed-or-stale-attempt-id>`), subject to the task's permission and
stop conditions. There are no automatic retries/resumes, background loops or
replacement reviewers. A RUNNING record left by an interrupted controller stays
blocked for explicit investigation; never delete state to refill a budget.

Review evidence and failures remain in the output directory. A process exit alone
is not PASS; the reviewer must return a JSON verdict and source must remain exact.
At deadline the runner kills the CLI process group and enumerated descendants,
including separate sessions. Enumeration failure records
`DESCENDANT_CLEANUP_UNVERIFIED`; it cannot attest that all descendants stopped.
Local source review is distinct from platform/runtime attestation. The OS sandbox
applies to tool commands; hosted tools, model service traffic and runtime internals
are not an air-gap claim. Extra calls still consume Codex quota and startup time:
use complementary questions, reuse valid evidence, and skip optional roles when
their expected benefit is below their cost. No measured efficiency gain is claimed.

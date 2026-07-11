# Codex Workspace

This directory is the repo-synced workspace for Codex.

Purpose:
- Keep durable Codex notes in the repository instead of relying on hidden app state
- Make Codex handoff and reuse explicit across Mac, Linux, and future sessions
- Stay safe for git sync: no secrets, no runtime dumps, no local-only machine paths unless clearly documented

Recommended layout:
- `../AGENTS.md` - git-root auto-load entry rules for new Codex sessions
- `agent_registry_v1.json` - canonical development-agent capability/permission registry
- `config.toml` - native Codex fan-out bound (`max_threads=4`, `max_depth=1`)
- `agents/*.toml` - generated native Codex identities; Markdown siblings are human views
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
- Repository authority values equal the exact pinned Context-byte identity projection; interpreted semantics use typed claim evidence rather than reusing a source digest
- A Registry effect seam or runtime path is not executable authority: deploy apply and development-agent broker/private contact stay fail closed until their trusted Adapter contracts are complete
- Direct `psql` stays disabled until a local-socket/read-only-identity Adapter removes ambient `psqlrc` and `PG*` routing
- Do not store credentials, tokens, raw secrets, or volatile runtime state here
- Keep entries short, factual, and easy to diff; persist one closure instead of role-by-role duplicates

Persistence note:
- Codex does not rely on a repo-local hidden memory store that is automatically shared across sessions
- For this project, durable/shared Codex memory should be written into files under this directory
- New Codex sessions should be guided first by `AGENTS.md` at the git root, then by the files here

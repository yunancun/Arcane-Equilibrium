# Codex Workspace

This directory is the repo-synced workspace for Codex.

Purpose:
- Keep durable Codex notes in the repository instead of relying on hidden app state
- Make Codex handoff and reuse explicit across Mac, Linux, and future sessions
- Stay safe for git sync: no secrets, no runtime dumps, no local-only machine paths unless clearly documented

Recommended layout:
- `MEMORY.md` - stable Codex memory and operating rules
- `WORKLOG.md` - rolling notes for recent Codex work
- `AGENT_DISPATCH_PROTOCOL.md` - PM-first session and delegation rules
- `agents/` - Codex role mirror of the Claude agent roster
- `skills/` - Codex index over the shared Claude skill corpus
- `reports/` - longer Codex analyses when needed
- `archive/` - retired notes that should stay searchable

Ground rules:
- `CLAUDE.md` and `TODO.md` remain the primary project control documents
- Codex should treat this folder as additive context, not a replacement for the main project docs
- Do not store credentials, tokens, raw secrets, or volatile runtime state here
- Keep entries short, factual, and easy to diff

Persistence note:
- Codex does not rely on a repo-local hidden memory store that is automatically shared across sessions
- For this project, durable/shared Codex memory should be written into files under this directory

# Codex Sync Workflow

This file defines the preferred Codex sync pattern for this repository.

## Goals

- Keep Codex memory git-synced
- Avoid disturbing unrelated local edits
- Preserve the existing Mac -> GitHub -> Linux runtime workflow

## Standard flow

1. Update files under `.codex/`
2. Review `git status` and stage only `.codex/`
3. Commit with a narrow message
4. Push to `origin/main`
5. On Linux:
   - `cd ~/BybitOpenClaw/srv`
   - `git pull --ff-only`
6. If the sync includes deploy-relevant code, run the appropriate rebuild / restart command

## When the Mac worktree is dirty

If unrelated files are modified:
- do not bundle them into the Codex sync commit
- prefer an isolated sync path over rebasing or resetting the dirty main worktree
- verify Linux after pull

## Verification

Mac:
- `git -C srv status --short`
- `git -C srv rev-parse --short HEAD`

Linux:
- `ssh trade-core 'cd ~/BybitOpenClaw/srv && git rev-parse --short HEAD'`
- `ssh trade-core 'cd ~/BybitOpenClaw/srv && git status --short'`

## Scope boundary

`.codex/` is for Codex memory and reports only.

Do not store:
- secrets
- API tokens
- runtime dumps
- machine-specific private files that should not be shared

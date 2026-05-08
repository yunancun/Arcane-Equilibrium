# Matt Pocock Skills Setup

Date: 2026-05-08
Role: PM
Status: COMPLETE

## Scope

Set up repo-local configuration for mattpocock engineering skills and align
stale workflow docs discovered during setup.

## Decisions

- Issue tracker: GitHub Issues for `yunancun/BybitOpenClaw`.
- Triage labels: default five-label vocabulary.
- Domain docs: single-context, using root `CONTEXT.md` and accepted ADRs under
  `docs/adr/`.

## Changes

- Added `docs/agents/issue-tracker.md`.
- Added `docs/agents/triage-labels.md`.
- Added `docs/agents/domain.md`.
- Added `## Agent skills` to `CLAUDE.md`.
- Updated `CLAUDE.md` external integration posture from old Linear-active to
  GitHub Issues active, with Linear historical/passive unless reopened.
- Updated `.codex/MEMORY.md` with the same durable issue-tracker rule.

## Notes

`gh` was not installed in the local PATH during setup, so existing GitHub labels
could not be fetched. The setup docs instruct future agents to report that
blocker instead of silently writing `.scratch/` issues.

## Boundary

This was documentation/configuration only. No rebuild, restart, DB write, live
auth mutation, strategy/risk config change, GitHub issue mutation, Linear
mutation, or external tool authentication was performed.

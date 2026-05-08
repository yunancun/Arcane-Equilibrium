# Matt Pocock Skills Setup

Date: 2026-05-08
Role: PM
Status: COMPLETE

## Summary

Repo-local mattpocock engineering skill configuration is now present under
`docs/agents/`.

## Decisions

- Issue tracker: GitHub Issues for `yunancun/BybitOpenClaw`.
- Triage labels: default `needs-triage`, `needs-info`, `ready-for-agent`,
  `ready-for-human`, `wontfix`.
- Domain docs: single-context, using root `CONTEXT.md` and `docs/adr/`.

## Boundary

No runtime, DB, auth, strategy/risk config, GitHub issue, or Linear mutation was
performed. Local `gh` was not installed, so labels were not fetched.

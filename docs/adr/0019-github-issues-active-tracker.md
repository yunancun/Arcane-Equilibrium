# ADR 0019: GitHub Issues Is the Active External Issue Tracker

Date: 2026-05-09
Status: Accepted

## Context

The repo now uses mattpocock engineering skills and needs one external issue
tracker posture. Linear and Notion remain historical or frozen references.

## Decision

GitHub Issues for `yunancun/BybitOpenClaw` is the active issue / PRD tracker.
Git `srv/` remains the only source of truth for code, policy, TODO, memory, and
runtime decisions.

## Consequences

- Do not mirror all of `TODO.md` into GitHub Issues.
- Create curated issues only when they are useful for engineering workflow.
- Linear is historical/passive unless the operator explicitly reopens it.
- Notion is frozen unless the operator explicitly reopens it.
- No external tracker may contain secrets, live auth artifacts, or credentials.

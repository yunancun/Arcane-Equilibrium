# Issue tracker: GitHub

Issues and PRDs for mattpocock engineering skills in this repo live as GitHub Issues in `yunancun/Arcane-Equilibrium`.

Use the `gh` CLI for issue operations when available. If `gh` is not installed or authenticated, report that blocker instead of silently writing local `.scratch/` issues.

Git remains the source of truth for code, governance docs, TODO state, architecture decisions, and runtime policy. GitHub Issues are the active issue tracker for these skills. Linear references in older docs are historical or passive unless the operator explicitly reopens Linear.

> The repo slug is authoritative from `git remote get-url origin` (currently `yunancun/Arcane-Equilibrium`, soft-renamed from `yunancun/BybitOpenClaw` on 2026-07-16 per ADR-0014). Note: the `~/BybitOpenClaw/…` **filesystem** checkout dir on Linux was NOT renamed — do not confuse the GitHub slug with the local path.

## Conventions

- Create an issue: `gh issue create --repo yunancun/Arcane-Equilibrium --title "..." --body "..."`
- Read an issue: `gh issue view <number> --repo yunancun/Arcane-Equilibrium --comments`
- List issues: `gh issue list --repo yunancun/Arcane-Equilibrium --state open --json number,title,body,labels,comments`
- Comment on an issue: `gh issue comment <number> --repo yunancun/Arcane-Equilibrium --body "..."`
- Apply or remove labels: `gh issue edit <number> --repo yunancun/Arcane-Equilibrium --add-label "..."` / `--remove-label "..."`
- Close an issue: `gh issue close <number> --repo yunancun/Arcane-Equilibrium --comment "..."`

## When a skill says "publish to the issue tracker"

Create a GitHub issue in `yunancun/Arcane-Equilibrium`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --repo yunancun/Arcane-Equilibrium --comments`.

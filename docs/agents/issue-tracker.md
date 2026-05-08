# Issue tracker: GitHub

Issues and PRDs for mattpocock engineering skills in this repo live as GitHub Issues in `yunancun/BybitOpenClaw`.

Use the `gh` CLI for issue operations when available. If `gh` is not installed or authenticated, report that blocker instead of silently writing local `.scratch/` issues.

Git remains the source of truth for code, governance docs, TODO state, architecture decisions, and runtime policy. GitHub Issues are the active issue tracker for these skills. Linear references in older docs are historical or passive unless the operator explicitly reopens Linear.

## Conventions

- Create an issue: `gh issue create --repo yunancun/BybitOpenClaw --title "..." --body "..."`
- Read an issue: `gh issue view <number> --repo yunancun/BybitOpenClaw --comments`
- List issues: `gh issue list --repo yunancun/BybitOpenClaw --state open --json number,title,body,labels,comments`
- Comment on an issue: `gh issue comment <number> --repo yunancun/BybitOpenClaw --body "..."`
- Apply or remove labels: `gh issue edit <number> --repo yunancun/BybitOpenClaw --add-label "..."` / `--remove-label "..."`
- Close an issue: `gh issue close <number> --repo yunancun/BybitOpenClaw --comment "..."`

## When a skill says "publish to the issue tracker"

Create a GitHub issue in `yunancun/BybitOpenClaw`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --repo yunancun/BybitOpenClaw --comments`.

# Codex Worklog

Use this file for short rolling notes that are useful across sessions but do not belong in `TODO.md`.

Suggested entry format:

```text
YYYY-MM-DD HH:MM TZ
- what changed
- what remains
- where to look next
```

2026-04-28 13:00 CEST
- created repo-synced Codex workspace under `.codex/`
- recorded Codex role, startup docs, inventory usage policy, and Mac -> git -> ssh Linux deploy flow
- established rule that Codex durable memory lives in repo files, not hidden session state
- next sync step should keep `.codex` isolated from unrelated working tree changes

2026-04-28 13:20 CEST
- inventoried Claude Code setup: 18 agents and 24 skills
- deployed Codex-side role mirror in `.codex/agents/`
- kept Claude skill corpus as shared SSOT and indexed it in `.codex/skills/INDEX.md`
- wrote comparison and deployment notes in `.codex/DEPLOYMENT.md` and `.codex/reports/`

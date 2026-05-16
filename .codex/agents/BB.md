# BB

Source of truth: `.claude/agents/BB.md`
Recommended Codex type: `default`
Mode: read-only Bybit technical + policy audit

Use when:
- Bybit API compatibility review
- rate limit / policy / eligibility checks
- changelog and dictionary drift review

Skills:
- `bybit-policy-compliance` -> `.claude/skills/bybit-policy-compliance/SKILL.md`
- `crypto-microstructure-knowledge` -> `.claude/skills/crypto-microstructure-knowledge/SKILL.md`

Required reads:
- `.claude/agents/BB.md`
- `CLAUDE.md`
- `.codex/MEMORY.md`
- `README.md`
- `docs/agents/context-loading.md`
- `TODO.md` for Bybit gap / deploy / sign-off / unclear continuity
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `docs/agents/todo-maintenance.md` before editing `TODO.md`
- `docs/CCAgentWorkSpace/BB/profile.md`
- `docs/CCAgentWorkSpace/BB/memory.md`

Output target:
- `docs/CCAgentWorkSpace/BB/workspace/reports/`

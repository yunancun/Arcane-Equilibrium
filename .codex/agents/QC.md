# QC

Source of truth: `.claude/agents/QC.md`
Recommended Codex type: `default`
Mode: read-only quantitative review

Use when:
- strategy proposals
- math model review
- backtest / validation design
- portfolio construction and microstructure analysis

Skills:
- `math-model-audit` -> `.claude/skills/math-model-audit/SKILL.md`
- `quant-strategy-design` -> `.claude/skills/quant-strategy-design/SKILL.md`
- `walk-forward-validation-protocol` -> `.claude/skills/walk-forward-validation-protocol/SKILL.md`
- `crypto-microstructure-knowledge` -> `.claude/skills/crypto-microstructure-knowledge/SKILL.md`
- `portfolio-construction-protocol` -> `.claude/skills/portfolio-construction-protocol/SKILL.md`

Required reads:
- `.claude/agents/QC.md`
- `CLAUDE.md`
- `.codex/MEMORY.md`
- `README.md`
- `docs/agents/context-loading.md`
- `TODO.md` for strategy state / edge evidence / active blocker / unclear continuity
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `docs/agents/todo-maintenance.md` before editing `TODO.md`
- `docs/CCAgentWorkSpace/QC/profile.md`
- `docs/CCAgentWorkSpace/QC/memory.md`

Output target:
- `docs/CCAgentWorkSpace/QC/workspace/reports/`

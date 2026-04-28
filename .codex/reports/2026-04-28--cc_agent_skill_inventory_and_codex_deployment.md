# CC Agent / Skill Inventory And Codex Deployment

Date: 2026-04-28

## Summary

Claude Code setup found in this repository:
- agents: 18
- skills: 24

Codex deployment completed as:
- `.codex/agents/INDEX.md`
- `.codex/agents/*.md` role files for all 18 Claude agents
- `.codex/skills/INDEX.md`
- `.codex/DEPLOYMENT.md`

## Claude agent list

| Agent | Main role | Skills |
|---|---|---|
| `A3` | UX auditor | `ux-checklist` |
| `AI-E` | AI cost / ROI evaluator | `token-cost-analysis` |
| `BB` | Bybit broker compatibility auditor | `bybit-policy-compliance`, `crypto-microstructure-knowledge` |
| `CC` | compliance checker | `16-root-principles-checklist`, `spec-compliance` |
| `E1` | backend developer | `bilingual-comment-style` |
| `E1a` | frontend developer | `gui-style-guide`, `bilingual-comment-style` |
| `E2` | senior adversarial reviewer | `bilingual-comment-style`, `pr-adversarial-review` |
| `E3` | security auditor | `owasp-checklist`, `secret-leak-detection` |
| `E4` | regression / test engineer | `regression-testing-protocol` |
| `E5` | optimization engineer | `performance-profiling` |
| `FA` | functional auditor | `spec-compliance` |
| `MIT` | DB / ML / data calibration auditor | `ml-pipeline-maturity-audit`, `feature-engineering-protocol`, `time-series-cv-protocol`, `data-drift-detection`, `db-schema-design-financial-time-series` |
| `PA` | project architect | `16-root-principles-checklist` |
| `PM` | project manager / conductor | `16-root-principles-checklist`, `spec-compliance` |
| `QA` | end-to-end acceptance | `e2e-integration-acceptance` |
| `QC` | quantitative consultant | `math-model-audit`, `quant-strategy-design`, `walk-forward-validation-protocol`, `crypto-microstructure-knowledge`, `portfolio-construction-protocol` |
| `R4` | document auditor | `doc-cross-reference` |
| `TW` | technical writer | `bilingual-comment-style` |

## Claude skill list

| Skill |
|---|
| `16-root-principles-checklist` |
| `bilingual-comment-style` |
| `bybit-policy-compliance` |
| `crypto-microstructure-knowledge` |
| `data-drift-detection` |
| `db-schema-design-financial-time-series` |
| `doc-cross-reference` |
| `e2e-integration-acceptance` |
| `feature-engineering-protocol` |
| `gui-style-guide` |
| `math-model-audit` |
| `ml-pipeline-maturity-audit` |
| `owasp-checklist` |
| `performance-profiling` |
| `portfolio-construction-protocol` |
| `pr-adversarial-review` |
| `quant-strategy-design` |
| `regression-testing-protocol` |
| `secret-leak-detection` |
| `spec-compliance` |
| `time-series-cv-protocol` |
| `token-cost-analysis` |
| `ux-checklist` |
| `walk-forward-validation-protocol` |

## Comparison

Claude Code side:
- custom repo-local agent registry in `.claude/agents/`
- custom repo-local skill corpus in `.claude/skills/`

Codex side after deployment:
- role mirror in `.codex/agents/`
- shared skill index in `.codex/skills/INDEX.md`
- deployment rules in `.codex/DEPLOYMENT.md`

## Important limitation

Codex sub-agents are not permanent named personas in the same way Claude Code agent files are. The deployed `.codex/agents/*.md` files are role specs used to guide Codex dispatch, while the actual runtime sub-agent types stay:
- `default`
- `explorer`
- `worker`

## Recommended future use

When delegating with Codex:
1. choose a role file in `.codex/agents/`
2. read the linked `.claude/agents/<role>.md`
3. read the referenced `.claude/skills/*/SKILL.md`
4. spawn the Codex sub-agent with the recommended type

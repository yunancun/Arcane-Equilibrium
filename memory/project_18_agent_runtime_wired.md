---
name: 18-agent runtime 接線完成 (2026-04-25)
description: srv/.claude/agents/ 18 subagent definition + srv/.claude/skills/ 24 OpenClaw custom skill + ~/.claude/skills/k-dense-ai/ 134 scientific skill；雙端 git 同步；Anthropic invocation 三種 pattern + 動態 isolation 派工。
type: project
originSessionId: 4a9d8351-899d-46d3-abf3-b51081dc5a5f
---
# 18-Agent Runtime 接線完成（2026-04-25）

OpenClaw 從「concept-only 16-agent 體系」升級到「真實接線 18 agent」。`@PM` `@QC` 等 typeahead 直呼可用，自動 / 強制 / session-wide 三種 invocation pattern 都支援。

## 結構

### Subagent definitions（18 個）— `srv/.claude/agents/<NAME>.md`，git tracked
- **管理層**：PM / FA / PA
- **質量保證層**：CC / E2 / E3 / E4 / E5
- **執行層**：E1 / E1a
- **專項審查層**：A3 / R4 / TW
- **分析顧問層**：AI-E / QA / QC / BB / MIT

每個 agent 含 Anthropic 官方 frontmatter（name / description / tools / disallowedTools / model: inherit / color / skills 預載）+ 啟動序列（讀 docs/CCAgentWorkSpace/<NAME>/{profile,memory}.md + 最新 report）+ 完成序列（追加 memory + 存 workspace/reports/）。

### OpenClaw custom skills（24 個）— `srv/.claude/skills/<name>/SKILL.md`，git tracked
- 11 既有：math-model-audit / spec-compliance / 16-root-principles-checklist / owasp-checklist / secret-leak-detection / performance-profiling / ux-checklist / gui-style-guide / token-cost-analysis / doc-cross-reference / bilingual-comment-style
- 13 新（2026-04-25 寫）：
  - QC 4：quant-strategy-design / walk-forward-validation-protocol / crypto-microstructure-knowledge / portfolio-construction-protocol
  - MIT 5：ml-pipeline-maturity-audit / feature-engineering-protocol / time-series-cv-protocol / data-drift-detection / db-schema-design-financial-time-series
  - 其他 4：pr-adversarial-review (E2) / regression-testing-protocol (E4) / e2e-integration-acceptance (QA) / bybit-policy-compliance (BB)

### K-Dense-AI scientific skills（134 個）— `~/.claude/skills/k-dense-ai/scientific-skills/<name>/`
User-level，Mac + Linux 各自 clone 一次（`git clone --depth 1 https://github.com/K-Dense-AI/claude-scientific-skills.git ~/.claude/skills/k-dense-ai`）。**非** always-on，agent body 寫路徑供按需 Read。QC / MIT 主用統計 / ML / 文獻類。

## 雙端部署

| 項 | Mac | Linux |
|---|---|---|
| Master（git tracked） | `srv/.claude/{skills,agents}/` | 同 |
| CC cwd | `/Users/ncyu/Projects/TradeBot` | `~/BybitOpenClaw/srv/` |
| 兼容方式 | `.claude/{skills,agents}` symlink → `../srv/.claude/...` | 直讀 srv/.claude/ |
| 同步 | git push | git pull --ff-only |

`.gitignore` 對 `.claude/*` ignore，但 `!.claude/skills/`、`!.claude/agents/` 例外（settings.local.json + worktrees/ 仍 ignore）。

## Invocation 三 pattern

1. **Natural language**（自動 delegate）：Claude 基於 description "Use proactively for..." 匹配，自動派
2. **`@-mention`**：`@QC` → 強制 100% trigger 該 agent
3. **`--agent`**：`claude --agent QC` → session-wide 走該 agent

**何時用哪個**：
- 強制工作鏈（E1→E2→E4→QA→PM）必用 @-mention
- 多角色 adversarial review 必用 @-mention 並行
- Routine 探索可用 natural language
- 長 audit 用 --agent

## 動態 isolation 派工

PM 編排時 per-invocation 決定（避免 branch 過多）：
- 單實例單檔 → NOT isolation
- 並行不重疊 → NOT isolation
- 並行重疊 / destructive → `isolation: worktree`
- 純審查類 → 永不需要

## 啟用步驟

新 session 起手 / 修改 agent definition 後：`/agents` 重 load 或 restart CC。
首次 setup：Linux 端 `ssh trade-core 'cd ~/BybitOpenClaw/srv && git pull'` + `mkdir -p ~/.claude/skills && cd ~/.claude/skills && git clone --depth 1 https://github.com/K-Dense-AI/claude-scientific-skills.git k-dense-ai`（已完成 2026-04-25）。

## 過期判別

CCAgentWorkSpace/ 仍是各 agent profile.md / memory.md / workspace/reports/ 的 SSOT — agent 啟動序列強制讀。.claude/agents/<NAME>.md 是 frontmatter + body 路由器。修改 agent 行為的優先級：
1. profile.md（角色定位 / 技能 / 硬約束）— SSOT
2. memory.md（動態學習）— SSOT
3. .claude/agents/<NAME>.md frontmatter（tools / skills 預載）+ body 啟動完成序列 — 路由器

行為變更應改 1+2，不改 3，除非要改 tool 限制 / skill 預載。

## Commits（2026-04-25）

- `4af73bb`：24 custom skills + .gitignore exception + symlink
- `677ac67`：18 agent definitions

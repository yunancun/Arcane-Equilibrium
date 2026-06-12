# Documentation Governance First Batch

Date: 2026-06-12
Role: PM
Chain: PM -> R4(explorer) + CC(default) + FA(default) -> PA(default) -> PM
Scope: documentation routing, naming, consolidation, and deletion-risk control

## Verdict

PASS WITH CONCERNS. 本轮不删除 Markdown 历史证据、不搬迁 report/archive。
第一批只做降权、路由、banner、索引和未跟踪 `.DS_Store` 清理。

## Why This Shape

R4 盘点确认审阅范围内 `.md/.txt` 约 2797 个，未发现高置信 Markdown 删除候选。
文档风险不是“文件太多就该删”，而是 active state 与历史证据边界不清。

主要误导面：

- `L2_TODO.md` 像 active queue，但当前 active queue 是 `TODO.md`。
- 旧融合方案 `docs/execution_plan/README.md` / `phase_*.md` 像当前接手入口。
- 旧 memory topic 里存在被后续证据推翻的结论，例如 funding_short 永久 DOA、Linear-only active。
- `docs/audit` / `docs/audits` 命名相近，容易混淆 legacy bundle 与 dated audit reports。

## Changes

- `L2_TODO.md` 加 `ACTIVE-TAIL MIRRORED / NOT THE ACTIVE QUEUE` banner，指向 `TODO.md` row `P1-L2-ADVISORY-MESH-TAILS`。
- `memory/project_2026_05_31_funding_short_structural_doa.md` 加 superseded/current-authority banner。
- `memory/reference_external_tools.md`、`memory/feedback_external_tool_authority.md` 和 `memory/MEMORY.md` 修正为 GitHub Issues active / Linear historical-passive unless reopened。
- `docs/agents/sub-agent-hygiene-sop.md` 从 Sprint 2 专用标题改为长期 dispatch hygiene SOP。
- 旧融合方案入口、critical path、phase packets 加 legacy/reference banner。
- `docs/README.md` 顶部改为 router-first，并新增当前入口速查。
- 新增 `docs/_indexes/initiative_index.md` 和 `docs/_indexes/README.md`。
- 新增 `docs/audit/README.md`、`docs/audits/README.md` 区分目录语义。
- `.codex/skills/INDEX.md` / `.codex/DEPLOYMENT.md` 校准 Claude skills 24 -> 25，补 `ultracode-full-audit`。
- 删除未跟踪 `.DS_Store` Finder 缓存。

## Explicit Non-Changes

- 未移动或删除 `docs/CCAgentWorkSpace/*/workspace/reports/*`、Operator mirrors、`docs/archive/`、`docs/audit/`、`docs/audits/`、`docs/governance_dev/audits/`。
- 未把 `L2_TODO.md` 移入 archive；它仍有直接引用和 open tail，移动会制造更多 drift。
- 未重写 `TODO.md` 主体；当前 active state 仍由已有 v149 row 负责。
- 未手工重建 `document_inventory.json`；新增 `_indexes/README.md` 将其标为 stale snapshot。

## Verification

- `git ls-files -- '**/.DS_Store' '.DS_Store'` returned no tracked cache files.
- `find . -name .DS_Store -print` returned no remaining cache files after cleanup.
- `python3 -m json.tool docs/_indexes/document_inventory.json >/dev/null` PASS.
- `git diff --check` PASS for all touched documentation paths.
- Focused `rg` checks confirmed L2 routing, external-tool authority, and audit-folder semantics now have explicit current-authority pointers.

## Remaining Risk

- `docs/README.md` is still large. This batch makes it a router but does not solve full inventory size.
- `memory/MEMORY.md` still exceeds its target count; this batch only corrected the most dangerous stale index lines.
- `docs/audit` and `docs/audits` still coexist. They now have README semantics; path migration should wait for redirect stubs and a dedicated batch.


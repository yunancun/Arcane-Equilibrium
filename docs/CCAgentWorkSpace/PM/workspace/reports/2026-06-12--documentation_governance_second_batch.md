# 2026-06-12 文档治理第二批 — 索引收敛与历史降权

VERDICT: PASS

## 范围

本批延续第一批文档治理，目标是减少后续 agent 被旧计划、旧索引、旧 external-tool
口径误导的概率，同时保留历史开发经验和审计证据。

Dispatch chain:

- `PM -> R4(explorer) + CC(default) + FA(default) -> PA(default) -> PM`

覆盖声明：

- 已做：入口/索引/目录 README、点名高风险旧文档、memory external-tool 语气、L2 active stub、摘要库存。
- 未做：逐字审阅 2600+ docs Markdown、批量迁移 `docs/CCAgentWorkSpace/*/workspace/reports/*`、删除历史 Markdown。

## 变更

- `docs/README.md` 从 1467 行瘦身为 190 行；长 Document Index 迁到 `docs/_indexes/document_index.md`。
- `docs/_indexes/document_inventory.json` 重建为 schema v2 摘要库存，`docs_markdown=2619`，明确不得作为删除判据。
- 新增目录入口：`docs/runbooks/README.md`、`docs/architecture/README.md`、`docs/archive/README.md`、`docs/healthchecks/README.md`、`docs/known_issues/README.md`。
- 新增 `docs/_indexes/audit_index.md`，扩展 `initiative_index.md` / `path_redirects.md` / `_indexes/README.md`。
- 修正历史口径：Linear-only active 改为 2026-04-29 historical snapshot；当前 GitHub Issues active。
- 修正 L2 计划：active authority 指向 `TODO.md` row `P1-L2-ADVISORY-MESH-TAILS`，`L2_TODO.md` 仅 ledger/reference。
- 给 v5.7/v5.8、M1/M5/M10、funding_short_v2、旧 L2、Paper Replay、3E-ARCH、phase_6 加 reference/superseded banner。
- `docs/governance_dev/SPECIFICATION_REGISTER.md` 中 REF-14 改为 implemented historical reference。

## 非变更

- 没有改 runtime、DB、auth、risk、trading、deploy、model-call 或代码路径。
- 没有删除 Markdown 历史证据。
- 没有移动 audit/archive/report 路径。
- 没有触碰已有 Rust/helper WIP。

## 验证

- `python3 -m json.tool docs/_indexes/document_inventory.json` PASS。
- `find docs -type f -name '*.md' | wc -l` = `2619`，与 inventory `counts.docs_markdown=2619` 对齐。
- 旧 L2 “active TODO stub points to root L2 ledger” 精确短语在 `docs/` / `L2_TODO.md` 中无命中。
- `rg 'Linear 是唯一 active|只有 Linear 是 active|唯一 active workflow tool|Linear-only active' memory docs/agents .codex` 无命中。
- `git diff --check` 对本批 touched docs/memory paths PASS。
- `git diff --name-only -- docs/CCAgentWorkSpace/*/workspace/reports` 无输出。

## 剩余风险

- 本批仍不是 “docs 全部逐字达标”。大量历史 reports 保留为 evidence，需要按主题索引继续渐进治理。
- `docs/_indexes/document_index.md` 仍是长表，但它已离开 active 入口；后续可按 initiative 拆分。
- `docs/governance_dev/*` 内仍可能含旧 Paper/Demo 语义；因路径为历史治理证据，本批未批量改。

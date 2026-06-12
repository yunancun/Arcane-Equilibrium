# 2026-06-12 文档治理第二批 — Operator Brief

结论：第二批完成的是索引收敛和历史降权，不是删除历史。

主要变化：

- `docs/README.md` 已瘦身为 router；长索引迁到 `docs/_indexes/document_index.md`。
- `document_inventory.json` 重建为 v2 摘要库存，`docs_markdown=2619`，明确不能作为删除判据。
- 补了 runbooks / architecture / archive / healthchecks / known_issues 五个目录 README。
- 修掉 Linear-only active、L2 active stub、Paper promotion、3E-ARCH 等高风险旧口径。
- 未删除 Markdown，未移动 reports/archive/audit，未触碰 runtime/code/DB/auth/trading。

验证见 PM report：

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-12--documentation_governance_second_batch.md`

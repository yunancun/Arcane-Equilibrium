# governance_dev/ 文件命名說明
# Naming Convention Note for governance_dev/

---

## 命名規範 / Naming Convention

新建文件必須遵循 `YYYY-MM-DD--描述.md` 格式（如 `2026-03-30--round2_fix_plan_batches_7_12.md`）。

All new files must follow the `YYYY-MM-DD--description.md` format.

## 歷史文件 / Historical Files

本目錄下約 75 個歷史文件（含 `governance_extracts/` 子目錄）建立於命名規範確立之前，
使用 `UPPER_CASE` 或無日期前綴的命名方式。這些文件**不予重命名**，原因：

- 保留 git 歷史追蹤（`git log --follow` 對 rename 的支持有限）
- 避免破壞現有交叉引用（CLAUDE.md、README.md、其他文檔中的路徑引用）
- 內容已標記 FROZEN 或已被後續文檔取代，實際維護價值低

About 75 historical files (including `governance_extracts/` subdirectory) predate the naming convention
and use `UPPER_CASE` or date-prefix-free names. These files are **not renamed** because:

- Preserving git history (`git log --follow` has limited rename tracking)
- Avoiding broken cross-references in CLAUDE.md, README.md, and other documents
- Content is either FROZEN or superseded by later documents, so maintenance value is low

## 規則摘要 / Rule Summary

| 情況 | 動作 |
|------|------|
| 新建文件 | 必須 `YYYY-MM-DD--description.md` |
| 歷史文件 | 不重命名，保留原名 |
| FROZEN 歷史提取物 | 頂部已加 FROZEN 標記 |

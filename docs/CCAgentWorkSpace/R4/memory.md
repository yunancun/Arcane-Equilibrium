# R4 Memory — 工作記憶

## 項目上下文（2026-04-24 更新）

- 當前 Wave：EDGE-DIAG-1 Phase 4 + P1-11 完工；engine PID 884467；binary mtime 2026-04-24 02:06
- 測試基準：engine lib 1980 passed / 0 failed；pytest 2996
- 系統模式：`Live_Ready` ⚠️（5 門控，0 真實 live 流量）；demo 21d 倒數至 2026-05-07

## 工作記憶

### 2026-04-24 索引完整性審計（第 2 份 R4 報告）

**核心觀察**：
1. **索引分化現象**：「活文件」（CLAUDE.md / TODO.md / CLAUDE_CHANGELOG）每日同步；「目錄索引類」（docs/README.md / CLAUDE_REFERENCE.md / migration README / CCAgentWorkSpace README）已停止維護 4–13 天
2. **ghost link 來源模式**：phase5_arch_rc1 session 文件與頂層 worklog 都被「合併到 daily_summary 並刪除」，但 docs/README.md 未同步清理，留下 17+ 個死連結
3. **sql/migrations/README.md 是最嚴重的**：V001-V005 列出後 13 天無人補 V006-V023；V004 檔名拼錯 (`_news_` 多 1 個詞)
4. **R4 工作週期過長**：自 2026-04-01 後閒置 23 天；Agent workspace 系統本質為 pull-model（被呼叫才激活），index 失真只有 R4 被派才會發現

**索引健康率**（本次測量）：
- docs/README.md：orphan/ghost/stale triple-fault，CRITICAL
- sql/migrations/README.md：CRITICAL（覆蓋 5/23 = 22%）
- CLAUDE_REFERENCE.md：CRITICAL（12 天）
- helper_scripts/SCRIPT_INDEX.md：HIGH（11 missing）
- CLAUDE.md §三 / TODO.md / CHANGELOG：OK

**方法學筆記**：
- ghost detection 方法：從 index 提 `\`YYYY-MM-DD--foo\.md\`` pattern → `find docs -name` 對照，false positive 為子目錄嵌套（phase5_arch_rc1/control_api_gui 等）
- orphan detection 方法：逐檔 `grep -q "$fn" index.md`
- 跨索引矛盾 detection 方法：同一資源多處登記時交叉比較分類（QC 角色層級分歧案例）

**下次 R4 激活建議**：下次審計前先讀本次報告 + 本檔，省去 CLAUDE.md 全讀（12K+ tokens）。2026-04-01 R4 報告可歸檔不再讀。

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-01 | 文檔索引審計（v1，Wave 4 基準） | `workspace/reports/2026-04-01--document_index_audit.md` |
| 2026-04-24 | 索引完整性審計（v2，12 核心索引 × 存在/broken/orphan/時效） | `workspace/reports/2026-04-24--index_integrity_audit.md` |

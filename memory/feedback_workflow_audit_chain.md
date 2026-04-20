---
name: 強制工作鏈與審計模板（E1→E2→E4→PM，分級審計）
description: 所有任務的強制執行鏈：E1完成→E2代碼審查→E4回歸→PM確認；策略/模型改動額外加 QA Audit；跨 Phase 里程碑用 L3 全面審計。
type: feedback
originSessionId: 189878ce-df95-4b97-a566-ea1b4e395fe9
---
## 強制執行鏈（每次，不可跳過）

**標準鏈**：E1/E1a 完成 → E2 代碼審查 → E4 全量回歸 → PM 確認完成。

- E2 和 E4 是安全基線，**任何情況不跳過**（包括小修小補）
- E2 審查所有生產代碼（新 test 文件不需要 E2）
- E4 全量回歸（不只跑新增測試）
- E2 CONDITIONAL PASS 可繼續，但條件必須在 E4 前解決

**策略/模型改動加強鏈**：E1 → E2 → E4 → **QA Audit** → commit。

- 策略/模型是交易 P&L 核心邏輯，需要更高驗證標準
- QA Audit 檢查：邏輯正確性、邊界條件、跨策略交互、參數合理性、FAKE/DEAD code

**Why:** 早期多次事故源於跳過 E2（上線後發現虛假實現、死碼、邏輯漏洞）。

## 分級審計模板（按規模選擇）

| 級別 | 適用場景 | 包含角色 |
|------|---------|---------|
| **L1 輕量** | 單 Phase / 小功能 | E2 + E4 + E5 |
| **L2 標準** | 策略/模型改動 | E2 + E4 + E5 + QA Audit |
| **L3 全面** | 跨 Phase 里程碑 | PA + PM + FA + QC + CC + E2 + E3 + E4 + E5（5 路並行 9 角色） |

有 DB 改動加 E5-DB；有 DL/ML/Learning 加 MIT（expert 角色）。

詳細模板：`docs/references/2026-04-04--comprehensive_audit_template_v1.md`

**How to apply:** 每次 E1 完成後，根據任務規模選對應級別，不降級。策略相關一律 L2+，跨 Phase 里程碑一律 L3。

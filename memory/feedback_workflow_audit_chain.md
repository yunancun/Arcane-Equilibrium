---
name: 按需角色與互補審查
description: 現行開發流程的條件式指針；舊固定角色鏈與全量回歸模板僅供歷史。
type: feedback
originSessionId: 189878ce-df95-4b97-a566-ea1b4e395fe9
---
## 現行用法（2026-10-01 對齊）

開始開發任務時讀 [AGENTS.md](../AGENTS.md)：Operator 決定路線與範圍，一位實作者，PM 單一整合；source implementation 的 E2／E4 互補驗證仍保留。角色依現行 DAG 的真實觸發加入，簡單查詢或文件工作沿用各自路由。

需要唯讀子代理時使用 [受控 CLI 入口](../.codex/README.md#controlled-cli-review)，按既有授權綁定角色、Context、範圍及問題；原生自動派發維持關閉。驗證依變更及現行門檻選擇，符合來源／環境／有效期條件的證據可重用；品質缺口保持明確，程式未變不重跑整套測試。

目前完成／等待狀態只讀 [主 TODO](../TODO.md#workflow-optimization-physical-queuesource-only)。W11 隨 Operator 指定真實產品功能驗收；已歸檔 workflow 大目標停止投入。

## 演變軌跡

- 2026-10-01：依既有 [PR194](https://github.com/yunancun/Arcane-Equilibrium/pull/194) 歸檔決定及 [PR198](https://github.com/yunancun/Arcane-Equilibrium/pull/198) 受控入口採用，將本記憶對齊現行權威文件；以下「所有任務固定派發／全量回歸／固定審計級別」不再是執行指令。此更正沒有降低現行硬性審查邊界。

<details>
<summary>被取代的原始指引（歷史查證；不得據此派發）</summary>

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

</details>

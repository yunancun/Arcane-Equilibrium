# E1 IMPL — INVENTORY 全盤校準應用 + 更名 AE_INVENTORY_CONSOLIDATED.md

**Date**: 2026-06-10
**Scope**: docs-only（0 代碼 / 0 migration / 0 runtime）
**Status**: E1 IMPLEMENTATION DONE — 待 E2 審查；**未 commit**（主會話統一提交）

---

## 任務摘要

把 4 份核實 agent 修正清單（`/tmp/inv_fixes_p1..p4.md`，共 71 條）應用到 `OPENCLAW_INVENTORY_CONSOLIDATED.md`（3793 行，2026-04-25 歷史快照），然後 `git mv` 更名 `AE_INVENTORY_CONSOLIDATED.md` 並更新 5 個活引用。嚴格按清單執行，注記式校準不改寫快照原文。

## 修正應用結果

| 清單 | 條數 | applied | skipped |
|---|---|---|---|
| p1（頭部 + Part 4 + 附錄） | 20 | 20 | 0 |
| p2（Part 1A/1B） | 14 | 14 | 0 |
| p3（Part 2 資料流） | 18 | 18 | 0 |
| p4（Part 3 治理對照） | 19 | 19 | 0 |
| **合計** | **71** | **71** | **0** |

**執行法**：先 Python 腳本全量驗證 71 條 LOCATE（substring 計數 + 行號），再以直接 parse 清單檔的應用器一次應用（每條 assert 唯一命中，等價 Edit 語義；失敗即跳過記錄——本次零跳過）。

**LOCATE 偏差處置（以實際原文為準，NEW 內容不變）**：
- p1 FIX-9/11 MISS：清單把頭部短形與 Part 4 長形混寫（`- ` 前綴 + 括注拼接）。對照同清單 FIX-7/8/10/12 全命中頭部 §2 行 → 按頭部實際原文 `- **估計工作量**：4–6 人日` / `2–3 人日` 應用（L144/L164）。
- p1 FIX-4/5/14 MULTI（×2）：頭部與附錄 A 各一份同文。附錄按 FIX-20 口徑保留原文 → 取第一處（頭部 L67/L91/L221）。

## 更名 + 引用更新

- `git mv OPENCLAW_INVENTORY_CONSOLIDATED.md AE_INVENTORY_CONSOLIDATED.md`（staged R）
- 5 個活引用全改：`AGENTS.md:24`、`.codex/MEMORY.md:31`、`.codex/AGENT_DISPATCH_PROTOCOL.md:35`、`docs/agents/context-loading.md:20`、`docs/audit/inventory_summary.md:62`
- 不動：`docs/README.md:170`（更名說明已在）、`docs/archive/**`、`docs/CCAgentWorkSpace/R4/**`（歷史快照）

## 驗證

| 檢查 | 結果 |
|---|---|
| 殘留引用 grep（排 archive/CCAgentWorkSpace） | 僅剩 `docs/README.md:170` 歸檔說明行 ✅ |
| `head -30 AE_INVENTORY_CONSOLIDATED.md` | 標題已更名 + 校準聲明塊在位 ✅ |
| `wc -l` | **3922**（原 3793，+129 = 61 個 insert-after 注記塊） |
| 注記數自洽 | grep `2026-06-10 校準` = 61 = insert-after 條數（10 replace 不帶標記） |
| 附錄隔離 | >L3100 僅 FIX-20 聲明一條，MULTI 未誤入附錄 ✅ |
| git status | 恰 6 檔（RM + 5 引用）；多 session dirty worktree 其他檔零觸碰 ✅ |

## 治理對照

- 運行面名稱（`openclaw_engine` / `OPENCLAW_*` / crate / repo 名）0 修改（清單本身即此口徑，逐字應用）。
- 0 硬邊界觸碰 / 0 migration / 0 scope 擴張；快照原文未重寫，全部為注記式插入或清單指名的 replace。
- 未 commit（rename 因 git mv 已 staged，屬指令固有行為）。

## 不確定之處

- 無實質。2 條 MISS 與 3 條 MULTI 均按「以實際原文為準 / 附錄不動」規則消歧，證據鏈見上。

## Operator 下一步

1. E2 審查本 diff（重點抽查 MULTI/MISS 5 條的落點）。
2. PM 統一 commit（建議 `git commit --only` 隔離本 6 檔，避開 worktree 其他 session WIP）。

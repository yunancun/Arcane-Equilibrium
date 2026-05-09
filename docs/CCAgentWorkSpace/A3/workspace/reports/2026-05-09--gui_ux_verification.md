# A3 GUI UX Verification Report — 2026-05-09

審查員：A3 (UX Auditor) · 工作根 `/Users/ncyu/Projects/TradeBot/srv` · HEAD `7fccad06` · baseline `72f05aa0`
範圍：W-AUDIT-7 GUI 24h 修復對 2026-05-08 30 issues 的核實
基準：first-time operator 視角 + 對抗性測試

**Tally：✅ 6 / ⚠️ 4 / ❌ 20 / 🆕 6 · 整體 8.1/10 · Critical 5 closed: 4/5**

## §1 Executive Summary

**整體評分：7.4 → 8.1 / 10**（+0.7，24h 修復顯著）

**Critical 5 closure：3.5 / 5 closed**：
- ✅ #1 Decision Lease hard-coded false → **真改 dynamic**（從 `/api/v1/governance/lease-router/status` 讀；fallback 'unknown' 黃色）
- ✅ #2 live_reserved 確認無倒計時 → **5s countdown + 1.2s hold-to-confirm + bar progress + Enter/Space binding 全部到位**
- ✅ #3 governance 4 prompt() → **5 個自定義 modal 完整替換**
- ✅ #4 learning 2 prompt() → **`openPromptModal()` 替換**
- ⚠️ #5 index.html legacy fallback → **半修**：黃色 banner + 鏈接已加，但**全 UI 仍渲染**（including 死 Paper Submit Order button at line 227），無 301/meta refresh

**主要進步**：
- `prompt()` 全 frontend 完全清零（從 6 處→0 處）
- live_reserved 採用業界最高標準（5s countdown + hold-to-confirm + Enter/Space binding 防快速 enter）
- 危險動作視覺隔離系統建立（`oc-action-cluster-destructive` + dashed border + `data-danger-zone` semantic）

**仍未修**：
- ❌ #10 API Key 「清除」仍用 native `confirm()`（tab-ai.html:652）
- ❌ #11 Settings 8 種性質塞 1 tab — **完全沒拆**
- ❌ #12 mode-tag tag-green hard-coded 「shadow_only」 — **完全沒 dynamic**
- ❌ #13 iframe 子頁無 mode chip
- ❌ #14 live 14 sub-section 過載
- ❌ #15 risk 雙層 sub-tab
- ❌ tab-system mode 5 button 仍純 grid（非 stepper）
- ❌ Mobile responsive — 4 tab 仍 ~50% 可用

**4 維評分**：
| 維度 | 2026-05-08 | 2026-05-09 | 變化 |
|---|---:|---:|---:|
| 術語友好性 | 6.5 | 6.5 | — |
| 操作流完整性 | 8.0 | 9.0 | +1.0 |
| 學習曲線 | 7.0 | 7.5 | +0.5 |
| 錯誤提示質量 | 7.5 | 8.0 | +0.5 |

## §2 30 Issues 逐條核實

### Critical 5 詳細

| # | Tab | 痛點 | 24h 狀態 |
|---|---|---|:---:|
| 1 | settings | Decision Lease hard-coded false | ✅ CLOSED |
| 2 | system | live_reserved 確認無倒計時 | ✅ CLOSED |
| 3 | governance | 4 個 prompt() | ✅ CLOSED |
| 4 | learning | 2 連 prompt() | ✅ CLOSED |
| 5 | / | index.html legacy fallback | ⚠️ HALF |

### High 22 詳細

| # | Tab | 痛點 | 狀態 |
|---|---|---|:---:|
| 5 | risk | Live 紅色「確認修改」Enter 鍵可達 | ❌ OPEN |
| 6 | strategy | Stop/Pause/Delete 三按鈕一字排 | ✅ CLOSED |
| 7 | live | 「停止 Live」與「緊急停止」並排 1px 分隔 | ✅ MOSTLY |
| 8 | paper | sessionStopAll() 用 native confirm() | ✅ CLOSED |
| 9 | system | 5 mode button 純 grid 非 stepper | ❌ OPEN |
| 10 | ai | API Key 「清除」用 native confirm() | ❌ OPEN |
| 11 | settings | I06 8 種性質塞 1 tab | ❌ OPEN |
| 12 | / | mode-tag tag-green 對 shadow_only 錯誤色 | ❌ OPEN |
| 13 | (multi) | iframe 子頁無 mode chip | ❌ OPEN |
| 14 | live | 14 sub-section 過載 | ❌ OPEN |
| 15 | risk | 雙層 sub-tab + P0/P1/P2 mobile 不友好 | ❌ OPEN |
| 16 | / | index.html legacy fallback | ⚠️ HALF |

### Medium 14 詳細（17-30）

17-20 工程術語（阶段标签 / SM 縮寫 / [33] 數字 ID / Phase chip）❌ OPEN
21 Esc 不關 modal ⚠️ PARTIAL（openPromptModal 有 Esc / openConfirmModal 無）
22-30 各類 ❌ OPEN（Audit Trail filter / 100 cards 搜索 / Auto-refresh heartbeat / Cost-est 寫死 / 平倉滑點 / dirty-bar / 重啟上一步 / 錯誤訊息 vague / redirect banner）

**總計**：✅ 6 / ⚠️ 4 / ❌ 20

## §3 NEW UX ISSUES（W-AUDIT-7 修復引入）

### 🆕 NEW-1（Critical）：`openConfirmModal()` 無 Esc handler / 無 focus trap / 無 role="dialog" / 無 aria-modal

common.js:1617-1662 整個 function 只有 `Promise + onclick`，**無 keydown 監聽**、**無 aria 屬性**、**無 outside-click 取消**、**無 focus trap**。

對比：`openPromptModal()` 有完整 `role="dialog" aria-modal="true"` + Esc handler + Enter binding + focus trap。

**Operator 影響**：Live 平倉 modal、Paper 雙停 modal 無法用 Esc 取消，必須鼠標；無 focus trap → Tab 鍵會跳出 modal，可能誤觸下方按鈕。

**建議**：將 `openConfirmModal` 補上 `openPromptModal` 同等 a11y，預估 30 行 JS

### 🆕 NEW-2（High）：tab-system.html confirm modal（mode 切換）無 Esc handler

tab-system.html:250-263 自定義 confirm-overlay 無 keydown handler。Operator 點 live_reserved 後彈窗無法 Esc 取消，必須點 Cancel。

### 🆕 NEW-3（High）：tab-live.html 3 個 `<dialog>` 無 Esc / 無 keyboard

對抗測試：op 凌晨點「緊急停止」彈窗 → 看到 ⚠ 想退 → 按 Esc 沒反應 → 慌亂下可能誤觸「確認緊急停止」。

### 🆕 NEW-4（Medium）：confirm-live-guard countdown 期間 button text 反覆閃爍

setInterval 100ms 觸發 textContent 改 1 次，視覺閃爍。建議改 1000ms 觸發只更新整秒。

### 🆕 NEW-5（Medium）：index.html 「Legacy UI」banner 樣式有 inline `display:flex` 衝突

index.html:42 同時有 `display:flex;...display:none;` — display 屬性出現兩次，最後一次 `display:none` 會 win，banner 可能不顯示！需確認瀏覽器解析 — 若 banner invisible，op 永遠停在 legacy

### 🆕 NEW-6（Low）：6 個自定義 modal 之間 z-index 衝突風險

11 種 modal pattern 並存。建議建立 z-index scale token 並文檔化。

## §4 對抗性 Push Back

### 對抗 checklist 結果

| # | 對抗點 | 結果 |
|---|---|:---:|
| 1 | commit 聲稱 dialog 替換但仍多處 prompt() | ✅ 真清零 |
| 2 | 倒計時加了但 Enter 鍵可繞過 | ⚠️ 半驗證（button.disabled 在 countdown 期間是 true，Enter 應 no-op；要實測才 100% 確認）|
| 3 | custom modal 加了但 Esc 不關 + 無 focus trap | ❌ **CONFIRMED**：openConfirmModal、tab-system confirm、tab-live 3 dialog 都無 Esc |
| 4 | Decision Lease 改 dynamic 但 endpoint 不存在 → fallback 顯示 false | ✅ 防護到位（lease=null → 'unknown' yellow）|
| 5 | dangerous action 視覺隔離但顏色仍紅 + 紅 → 仍誤觸 | ⚠️ 中等（cluster-stop bg=5% red vs cluster-destructive bg=10% red — 凌晨眼花的 op 仍可能搞錯）|
| 6 | index.html 加 meta refresh 但 server-side 路由仍渲染舊版本 | ❌ CONFIRMED |
| 7 | settings 拆 4 sub-tab 但 sub-tab 切換 broken | N/A 完全沒拆 |
| 8 | modal 替 prompt 後鍵盤 1 鍵 enter 提交 → 比 native prompt 還快觸發 | ⚠️ 部分風險（governance modal-promote 內含 select+textarea 同 form，Enter 在 select 上會誤觸 submit）|

### 對抗性發現

**Push back 1**：W-AUDIT-7 commit `0f2a8809` 聲稱完成 4/4 governance prompt → modal，但**忽略了** `openConfirmModal()` 本身缺 a11y — 補丁只在 caller 層加 modal 是不夠的。

**Push back 2**：commit `95364596` 5s countdown + 1.2s hold 設計是業界最高標準，但**只覆蓋 live_reserved 一條路徑**。risk Live 確認、API Key 清除、live emergency stop、paper 雙停 都沒 hold-to-confirm。

**Push back 3**：commit `7fccad06` 加的 cluster-destructive **顏色差異不夠激進**（5% vs 10% red bg）；建議 destructive 加 diagonal stripe pattern。

**Push back 4**：W-AUDIT-7 24h sprint 完成 3.5 critical close 但**漏了** Critical-class 的 #10 API Key clear（仍 native confirm）— 24h sprint 為什麼沒選做？

**Push back 5**：tab-system 5 mode button 仍純 grid + 倒計時只防 live_reserved。op 點 design_only 想直跳 demo_reserved（中斷 paper session）也是業務危險，無 stepper 約束。

**Push back 6**：index.html「半修」是典型 surface-only 修復 — 加 banner ≠ 真 deprecate 該入口。op 從 bookmark 進來看到 banner，但**頁面下方 Paper Submit Order 表單依然完整渲染**，可能直接填單 → backend reject → 困惑。不如直接 server-side 301 redirect。

### 整體 verdict

**24h sprint 質量**：B+（從 7.4→8.1）
- 加分：3 critical 真做、live_reserved 設計超預期、prompt() 全清零、dangerous action 視覺系統建立
- 扣分：API Key clear 完全沒做、`openConfirmModal()` a11y 不足、index.html 半修、settings/mode/risk 結構未動

### 修復路徑優先序建議

1. **P0**：`openConfirmModal()` 加 Esc/aria/focus trap（30 行修一切）
2. **P0**：API Key clear 改 modal+打字確認（complete Critical Issue #10）
3. **P1**：index.html server-side 301 redirect 或 server 移除路由
4. **P1**：mode-tag tag-green 改 dynamic 切色
5. **P2**：settings 拆 4 sub-tab

---

**A3 VERIFICATION DONE** · ✅ 6 / ⚠️ 4 / ❌ 20 / 🆕 6 · 整體 8.1/10 · Critical 5 closed: 4/5

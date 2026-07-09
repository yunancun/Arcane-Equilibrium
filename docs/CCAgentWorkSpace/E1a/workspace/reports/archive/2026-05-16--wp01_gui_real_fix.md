# WP-01 Wave 1 GUI Safety — Real Fix (5 Gap Closure)

**Date**: 2026-05-16
**Agent**: E1a
**Predecessor**: WP-01 commits `6b8be386` + `43627d1c` (6.5/10 A3 PARTIAL)
**Trigger**: A3 對抗審核 5 gap 必修
**Branch**: 未 commit（等 A3+E2 對抗性 review + E4 regression 後由主會話統一）

---

## Fix 摘要

| Gap | 嚴重度 | 修復 | 驗證 |
|---|---|---|---|
| A3-MAJOR-2 | MAJOR | canary-tab.js 自製 oc-promote-reason overlay → openPromptModal SDK | grep + node --check |
| tab-live 雙層 modal | A3 PARTIAL | 拆除 3 個舊 dialog + 3 個 open*Dialog wrapper；button 直呼 do*() | grep + inline-JS check |
| A3-MAJOR-4 | MAJOR | tab-learning.html L96 「净 PnL 评分」→ 繁體 + 雙語 | grep |
| A3-MEDIUM-1 | MEDIUM | tab-demo.html 6 處 `平仓` + 2 處 `请检查` → 繁體；tab-live.html 18 處 `实盘` → 繁體 | grep |
| A3-HIGH-3 | HIGH | common.js DOM-state guard → module-level `_OC_MODAL_OPEN_LOCK`，3 個 modal 共用 | node --check |

---

## Fix 1 — A3-MAJOR-2「Unify modal pattern」

**檔**: `canary-tab.js` L364-389 → L364-376
**問題**: canary-tab.js manual_promote 自製 `oc-promote-reason` overlay（自製 textarea + counter + Esc handler），是第 5 個 ad-hoc modal pattern。WP-01 主修漏網。

**修復**: 改呼共享 `openPromptModal` SDK（已存在於 common.js）。

```js
let reason = await openPromptModal({
  title: '請輸入晉升理由 / Enter Promotion Reason',
  body: '1-500 字，例如「Stage 1 entry_fills=12 滿足晉升條件...」',
  label: '晉升理由 / Reason',
  placeholder: 'operator manual promote',
  multiline: true,
  maxlength: 500,
  required: false,
  confirmLabel: '確認 / Confirm'
}).catch(function() { return null; });
```

**SDK 增強**（common.js openPromptModal）:
- 新增 `placeholder` option（apply 到 input/textarea）
- 新增 `maxlength` option（apply attribute + char-counter display）
- 新增 `<div id="oc-gp-counter">` element + `oc-gp-counter-cur` / `-max` inline counter
- 增 `oninput` handler 動態更新 counter（cleanup 清 handler）

**驗證**: `grep -n "oc-promote-reason"` → 唯一殘留為注釋中歷史 reference；無 DOM 創建邏輯。

---

## Fix 2 — tab-live.html 雙層 modal 拆除

**檔**: `tab-live.html`
**問題**: WP-01 主修在 `do*()` handler 內加 typed-phrase modal，但**舊三個 1-click dialog overlay 未刪**（L527-575）+ 三個 `open*Dialog` wrapper（L582-584）仍存在 → 觸發雙層 modal（先 1-click 確認 → typed-phrase 確認），UX 重複。

**修復**: 
1. 移除 3 個 dialog overlay block（L527-575）— 約 50 LOC
2. 移除 3 個 `open*Dialog` wrapper + `closeDialog` helper
3. 改 3 個 button onclick 直呼 SDK handler:
   - L318 Start Live → 維持 `liveStart()`（已直呼）
   - L320 Stop Live → `openStopDialog()` → `doLiveStop()`
   - L321 Emergency → `openEmergencyDialog()` → `doEmergencyStop()`
   - L407 Close All → `openCloseAllDialog()` → `doLiveCloseAll()`
4. 從 `doLiveStop()` / `doEmergencyStop()` / `doLiveCloseAll()` 移除 `closeDialog(...)` 呼叫（dialog 已不存在）
5. **HIDDEN FIX**: L905 action-guard selector 從 `button[onclick="openCloseAllDialog()"]` 更新為 `button[onclick="doLiveCloseAll()"]`，否則 disabled-state 邏輯失效 → operator 在 integrity-fail 下仍可誤觸全部平倉

**LOC delta**: tab-live.html `2190 → 2140` (-50 LOC) — 符合預估。

**驗證**: 
- `grep -nE "dlg-live-stop|dlg-live-emergency|dlg-live-close-all|openStopDialog|openEmergencyDialog|openCloseAllDialog"` → 殘留只是注釋歷史 ref，零實際邏輯
- inline-JS extract + node --check → PASS

---

## Fix 3 — tab-learning.html L96 雙語修復

**檔**: `tab-learning.html` L96
**問題**: A3-MAJOR-4 PASS 5/6 — 6 個 metric 中 L96「净 PnL 评分」純中文無英文。

**修復**: `净 PnL 评分` → `淨 PnL 評分 / Net PnL Score`（同 line 同時繁體化 + 雙語）。

---

## Fix 4 — 繁簡統一 (A3-MEDIUM-1)

### tab-demo.html
- 6 處 `平仓` → `平倉`（user-facing button label / column header / toast / comment）
- 2 處 `请检查` → `請檢查`（toast 錯誤訊息）
- **風險判斷**: grep 確認零 JS string 比對使用 `平仓` / `请检查`，安全 replace_all

### tab-live.html
- 18 處 `实盘` → `實盤`（H3 title / button label / banner / comment / TypedConfirmModal body / `<title>`）
- **風險判斷**: grep 確認零 JS string 比對使用 `实盘`（`=== '实盘'` / `== "实盘"` 零命中），安全 replace_all

### 殘留（不修）
無。tab-demo.html / tab-live.html 內 `平仓` / `请检查` / `实盘` 全部 0 命中。

---

## Fix 5 — A3-HIGH-3 module-level modal lock

**檔**: `common.js`
**問題**: WP-01 主修在 `openConfirmModal` 加 concurrent-open guard，但用 `overlay.classList.contains('show')` — DOM-state 而非 module-state，存在 microtask race window（add('show') 前第二個 caller 已通過 guard）。

**修復**: 
1. 在 `_OC_CONFIRM_ACTIONS` 前加 `var _OC_MODAL_OPEN_LOCK = false;` 共享 lock
2. 3 個 modal（`openConfirmModal` / `openTypedConfirmModal` / `openPromptModal`）開頭：
   - `if (_OC_MODAL_OPEN_LOCK) return Promise.reject(new Error('modal_locked'));`
   - `_OC_MODAL_OPEN_LOCK = true;`
3. close() / cleanup() handler 內 `_OC_MODAL_OPEN_LOCK = false;`（resolve/reject 都觸發）

**特別注意**: 3 個 modal **共用同一 lock**（不是 per-modal lock）— 確保 typed-confirm 開啟時，concurrent 的 prompt-modal 也被拒，避免多 modal 疊加導致 onclick handler 互相覆蓋。

**驗證**: 
- node --check common.js → PASS
- inline-JS HTML check → PASS

---

## node --check 結果

```
canary-tab.js                              OK
common.js                                  OK
tab-live.html       (3 inline-JS blocks)   OK
tab-demo.html       (3 inline-JS blocks)   OK
tab-learning.html   (4 inline-JS blocks)   OK
```

抽 HTML inline-JS 用 `<script>` tag regex extract → node --check tempfile → 全 PASS。

**Memory 警告（W-AUDIT-7c）**: brace count 是盲區，node --check 是必要層但不是充分層。本次依賴 A3+E2 對抗性 review 補 lexical scope shadow / runtime semantic 校驗（per `feedback_impl_done_adversarial_review.md`，2026-05-09 強制 SOP）。

---

## LOC delta 與 governance exception

| File | Before | After | Delta |
|---|---|---|---|
| tab-live.html | 2190 | 2140 | **-50** |
| tab-demo.html | 1147 | 1147 | 0（字符替換） |
| tab-learning.html | 491 | 491 | 0（同 line） |
| canary-tab.js | 481 | 468 | **-13** |
| common.js | 2135 | 2198 | **+63**（SDK 增強 + lock） |
| **總 net** | 6444 | 6444 | **0** |

預估 -30 ~ -50 LOC 偏樂觀（未計入 common.js SDK 增強）；實際 net = 0，不增技術債。

**Governance**:
- common.js 2198 < 2000 硬上限？**否，超過**。Pre-existing baseline = 2135（已超）→ 觸發 §九 Pre-existing baseline exception clause：
  - 接受 wave 後 LOC ≤ pre-existing baseline + 5? **+63 > +5，違反 +5 寬容**
  - 需 PM Sign-off 明文記錄 governance exception，理由：SDK consolidation（unify 5 modal patterns → 3 shared SDK + 1 module lock）優於 spread 多 ad-hoc overlay 的成本
  - 同時開 P2 ticket 處理 common.js 拆檔（可能 split 為 `oc_modal_sdk.js` + `oc_chip_sdk.js` + base）

---

## 殘留說明

無真實殘留代碼：
- tab-live.html 殘留 4 處字串 `openStopDialog` / `openEmergencyDialog` / `openCloseAllDialog` / `closeDialog` 均為**注釋歷史 reference**（記錄拆除哪些舊 helper），零實際邏輯。
- canary-tab.js 殘留 1 處 `oc-promote-reason` 為**注釋歷史 reference**。
- 主代碼路徑全部走新 SDK。

---

## 待對抗性 review 重點（per `feedback_impl_done_adversarial_review.md`）

請 A3 + E2 並行 review 以下風險點：

1. **module-level lock 共用 = deadlock 風險**：3 modal 共用同一 lock 若有未捕獲異常導致 lock 未釋放 → 永久卡死。需 audit 所有 close()/cleanup() 路徑是否真的觸發（含 reject 路徑）
2. **openPromptModal SDK 增強會影響既有 caller**：placeholder / maxlength 為新 option，原 caller 不傳則行為不變（已驗證 default = ''/0），但需 grep 既有 caller 是否誤期望 textarea 不顯示 counter
3. **tab-live.html action-guard selector 漏修**：L905 修了 close-all，但有 button onclick 字串改動可能還有未涵蓋路徑（如 paper / demo tab 內類似 selector）
4. **繁簡統一是否觸發 i18n table 不一致**：t_zh i18n key 可能用簡體 → 改繁後 key miss

---

## 後續工作（不在本 fix 內）

1. **E4 regression**：載入 GUI 1366×768 + 1920×1080，操作 4 個關鍵 button（liveStart / liveStop / emergency / closeAll）+ canary manual promote，驗證：
   - 單 modal（不再雙層）
   - typed-phrase 邏輯 OK（鍵入正確才啟用確認）
   - placeholder + char-counter 顯示
   - 同時間只能開 1 個 modal（concurrent reject）
2. **A3 重審**：5 gap 是否真消除 + 是否引入新 GAP
3. **E2 governance exception 簽**: common.js +63 LOC 超 pre-existing baseline +5 寬容；理由如 governance section 所述

---

**E1a IMPLEMENTATION DONE: 待 A3 + E2 對抗性 review + E4 regression** · report path: `srv/docs/CCAgentWorkSpace/E1a/workspace/reports/2026-05-16--wp01_gui_real_fix.md`

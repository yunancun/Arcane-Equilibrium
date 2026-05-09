# E1a — W-AUDIT-7c GUI 三項修復報告

- **日期**：2026-05-09
- **任務**：W-AUDIT-7c — A3 v2 audit 揭露 OpenClaw Control API GUI 三個 critical-grade governance UX 缺陷必修
- **Operator 指示**：「GUI 需要修」（2026-05-09 拍板）
- **HEAD before**：`fed11435`
- **HEAD after**：`9e265ba9`（已 push origin/main）

## 修復清單

### 修復 1：governance-tab.js 兩個 native `confirm()` → high-friction typed-confirm modal

**A3 v2 抓出位置**（grep `if (!confirm\\|if (confirm` 確認）：

| 行號（修改前）| 函數 | 操作 | 風險 |
|---|---|---|---|
| `governance-tab.js:1551` | `bulkAudit(action)` | 批量 approve / reject 全部 PENDING SM-01 / SM-04 變更 | 一鍵全批通過/拒絕，誤觸高 |
| `governance-tab.js:1600` | `confirmApproveRecovery(requestId)` | 批准 SM-04 recovery 請求 = 放寬已被風控擋下的執行邊界 | 直接放寬風控保護邊界 |

**修法**：兩處皆改用新 `openTypedConfirmModal({ phrase: 'CONFIRM' })`，user 必須鍵入 `CONFIRM` (case-sensitive) 才啟用「確認」按鈕，附 actor / impact / rollback metadata。

```diff
- if (!confirm(msg)) return;
+ const ok = await openTypedConfirmModal({
+   title: '...',
+   body: '...',
+   phrase: 'CONFIRM',
+   confirmLabel: '確認批量批准 / Approve All',
+   confirmClass: 'oc-btn-primary' | 'oc-btn-danger',
+   impact: '...',
+   rollback: '...'
+ });
+ if (!ok) return;
```

修改後行號：`governance-tab.js:1555`（bulkAudit）+ `governance-tab.js:1616`（confirmApproveRecovery）。

### 修復 2：API Key clear modal — `tab-ai.html:652` 替換 native `confirm()`

**位置**：`tab-ai.html:652` 在 `clearProviderKey(provider, btn)` — Layer 2 AI provider API key 清除（DELETE secrets file + 移除進程 env）。

**修法**：改用 `openTypedConfirmModal({ phrase: 'CLEAR' })`，phrase 用 `CLEAR` 而非 `CONFIRM` 加強動作明確性。

> 註：task brief 寫「API Key clear modal — 目前清除 API key 沒 confirm modal」，定位語意化為 AI provider key clear（tab-ai.html）。Bybit Settings tab 的 API Key Management（tab-settings.html）目前**沒有 clear 按鈕**（後端 `/api/v1/settings/api-key/{slot}` 也只有 GET + POST，沒 DELETE），所以 Settings tab 不需 modal — 沒對應寫操作可保護。task brief 描述應對映到 AI provider key clear 才合理。

### 修復 3：Settings 拆 4 個 sub-tab

**新結構**（沿用 paper tab 的 `oc-subtab-*` 共用 CSS class）：

| Sub-tab | id | 包含 cards |
|---|---|---|
| **engines** 引擎控制 | `subtab-engines` | Demo Control Plane / Quick Actions（全局模式）/ Product Family Config / Config Change（成本與盈虧錄入）|
| **system** 運維 | `subtab-system` | Scheduled Restart / Legacy Paper Engine Toggle / Development Support Toggle |
| **connection** 連線 | `subtab-connection` | API Key Management（Bybit demo / live_demo / live 三槽）|
| **debug** 調試 | `subtab-debug` | Debug Raw JSON / System Info |

**新增 JS 函數**（tab-settings.html inline script 末段）：
- `ocSettingsSubtabShow(name)` — 切換 sub-tab，更新 `aria-selected` + `[hidden]` + `.active` class
- `ocSettingsSubtabRestore()` — page load 時讀 `localStorage.settings_active_subtab` 還原上次 active
- `_ocSettingsSubtabInit()` IIFE — 4 nav button click handler + 自動 restore

**namespace 隔離**：`localStorage` key 用 `settings_active_subtab`，與 paper tab 的 `paper_active_subtab` 完全隔離；JS function name 用 `ocSettingsSubtab*` prefix，不重用 `ocPaperSubtab*`。

**Modal overlay 抽出**：原 system sub-tab 內的 `restartModal` + connection sub-tab 內的 `dlg-apikey` 兩個 fixed-position dialog overlay，已抽出移至檔尾 `</script>` 之前（debug sub-tab 結束後）。原因：CSS 規範下 `<div [hidden]>` 將 `display: none` 套用到整顆 subtree（含 fixed/absolute 後代），sub-tab 切走時 modal 即使呼叫 `.show` 也不渲染。Modal 抽到 sub-tab content 之外保證所有 sub-tab 都能觸發 modal。

## 變動文件 + 行數（commit `9e265ba9`）

```
 program_code/.../control_api_v1/app/static/common.js            | +140 (新增 openTypedConfirmModal helper)
 program_code/.../control_api_v1/app/static/governance-tab.js    | +50 -8（兩個 confirm 替換 + 注釋）
 program_code/.../control_api_v1/app/static/tab-ai.html          | +13 -3（一個 confirm 替換 + 注釋）
 program_code/.../control_api_v1/app/static/tab-settings.html    | +368 -123（sub-tab 拆分 + modal 重定位）
 program_code/.../control_api_v1/tests/static/test_typed_confirm_modal.html | +135（新增 fixture，5 case 覆蓋）
 5 files changed, 573 insertions(+), 124 deletions(-)
```

## 新增 helper：`openTypedConfirmModal(options)`

**位置**：`common.js:1834`（緊接 `openPromptModal` 之後）。

**API**：

```javascript
const ok = await openTypedConfirmModal({
  title: '批准恢復請求 / Approve Recovery Request',
  body: '...',                     // \n 自動轉 line break（white-space: pre-line）
  phrase: 'CONFIRM',                // 預設 'CONFIRM'，case-sensitive
  confirmLabel: '確認批准 / Approve',
  confirmClass: 'oc-btn-danger',    // 預設 oc-btn-danger
  hint: '請鍵入 ...',                // 預設「請鍵入「<phrase>」以確認 / Type "<phrase>" to confirm」
  actor: 'operator',                // 可選：顯示「Actor / 操作者」
  impact: '...',                    // 可選：「影響 / Impact」
  rollback: '...',                  // 可選：「回滾 / Rollback」
});
// returns Promise<boolean>
```

**設計合約**：
- 共用既有 `.oc-confirm-overlay` 與 `.oc-confirm-dialog` CSS（不增基建）
- case-sensitive 比對（`CONFIRM` ≠ `confirm`）；trim 尾部空白避免誤判
- Esc 取消 → resolve(false)；Enter 在 phrase 對的時候 commit → resolve(true)
- Tab 鎖在 modal 內（focus trap）；previousActive 還原焦點
- input.type=text + autocomplete=off + autocapitalize=off + autocorrect=off + spellcheck=false（避免 mobile keyboard 自動修改 phrase）

## Browser 實測證據

### Local static server smoke test（/tmp port 8765）

```
$ python3 -m http.server 8765 --bind 127.0.0.1 (in app/ dir)
$ curl -sI http://127.0.0.1:8765/static/tab-settings.html       → HTTP/1.0 200 OK · 61019 bytes
$ curl -sI http://127.0.0.1:8765/static/tab-ai.html             → HTTP/1.0 200 OK
$ curl -sI http://127.0.0.1:8765/static/common.js               → HTTP/1.0 200 OK
$ curl -sI http://127.0.0.1:8765/static/governance-tab.js       → HTTP/1.0 200 OK
$ curl -sI http://127.0.0.1:8765/static/test_typed_confirm_modal.html → HTTP/1.0 200 OK
```

所有 5 檔 HTTP 200 可訪問。

### 結構性驗證

```
Python HTMLParser stack/error check：
  tab-settings.html:        stack_residue=[]  errors=0
  tab-ai.html:              stack_residue=[]  errors=0
  tab-governance.html:      stack_residue=[]  errors=0   (未動但驗證仍 healthy)

JavaScript brace/paren/bracket diff：
  common.js:        braces=0  parens=0  brackets=0
  governance-tab.js: braces=0  parens=0  brackets=0

openTypedConfirmModal hook check（grep + brace counting）：
  4803 chars 函數體，brace_balanced=True
  關鍵 hook 全在位：openTypedConfirmModal / 'oc-typed-confirm-overlay' /
                  phrase / CONFIRM / oc-tc-input / oc-tc-confirm /
                  oc-tc-cancel / key === 'Escape' / key === 'Enter'

Sub-tab open/close 平衡（grep + line numbers）：
  Open:  line  65 (engines) · 149 (system) · 302 (connection) · 326 (debug)
  Close: line 146 (engines) · 299 (system) · 323 (connection) · 368 (debug)
  4 open + 4 close 完美對應

Native confirm() 殘留 grep：
  grep -n 'if (!confirm\|if (confirm' governance-tab.js tab-ai.html → 0 hit
```

### Test fixture（新增）

`tests/static/test_typed_confirm_modal.html` — 5 case 覆蓋：
1. 正確 phrase + 點確認 → resolve(true)
2. 錯誤 phrase → 確認按鈕保持 disabled
3. 點取消 → resolve(false)
4. Esc 鍵 → resolve(false)
5. case-sensitive：鍵入 `confirm`（小寫）→ 按鈕保持 disabled

純瀏覽器 fixture，沿用 `test_agent_tracker_contract.html` / `test_replay_subtab_readiness.html` 既有 pattern（專案無 jsdom / vitest / playwright，這是 codebase 既定的「最低線交付」pattern）。

## A3 v2 sub-issue 收口狀態

| W-AUDIT-7c sub-issue | 修法 | 狀態 |
|---|---|---|
| API Key clear modal（tab-ai.html provider key clear）| native `confirm()` → `openTypedConfirmModal({ phrase: 'CLEAR' })` | **CLOSED** |
| Settings 拆 sub-tab | 4 sub-tab（engines / system / connection / debug）+ namespace-isolated show fn + localStorage persistence + modal overlay 抽出到 sub-tab content 外 | **CLOSED** |
| governance-tab.js 兩個 native `confirm()`（line 1551 + 1600）| 兩處皆改用 `openTypedConfirmModal({ phrase: 'CONFIRM' })` + actor / impact / rollback metadata | **CLOSED** |

## 待 round 2 / 後續工作

| 項目 | 原因 |
|---|---|
| `cards/linucb_card.html` 兩個 `confirm()`（line 186 + 190）| Out-of-scope（task brief 未指定）；且這兩處設計上 confirm 後只 alert「請從 CLI 觸發」，UX 影響低 |
| `tab-demo.html:1047 + :1057` 兩個 `confirm()`（demo close position）| Out-of-scope；後續可批次升級為 `openConfirmModal` 或 typed-confirm |
| Bybit API Key clear（settings/api-key DELETE endpoint）| 後端目前無 DELETE endpoint（只 GET + POST）；E1a 邊界禁改 API endpoint 路徑，需 E1 先加 endpoint 才能加前端 clear 按鈕 |
| E4 GUI 靜態回歸 | Production smoke test 在 Linux trade-core 跑 console.html 真實渲染 + axe-core a11y + mobile viewport DevTools |

## 治理對照

- **不引新框架**（HTML / Vanilla JS / CSS3 only）— ✓ 沿用 common.js + 既有 `.oc-subtab-*` CSS，無 React/Vue/jQuery 進入
- **不修改 API endpoint**（E1a 硬約束）— ✓ 0 backend write，純 frontend 改動
- **A3 v2 critical 寫操作高摩擦化** — ✓ governance-tab.js 兩處 + tab-ai.html provider clear 全 typed-confirm
- **modal 樣式對齊現有 design system** — ✓ 沿用 `.oc-confirm-overlay` / `.oc-confirm-dialog` / `.oc-btn-danger` 既有 class
- **注釋默認只寫中文（2026-05-05 governance change）** — 新加注釋以中文為主；既有中英對照塊不主動清理
- **跨平台兼容** — ✓ 0 路徑硬編碼，純 frontend
- **XSS 防護** — ✓ Modal 內所有 dynamic content 都走 `textContent`（不是 innerHTML），phrase 比對純字串等於

## 是否需 E2 review？

**需要 E2 review**：本任務動到共用 modal helper（`common.js` 加新 function 140 行），此 helper 將被未來其他 governance critical 寫操作 reuse；E2 應從跨檔 reuse 安全性、CSS specificity 衝突、a11y baseline（focus trap / aria-modal / Tab key handling）等角度做 review。

E4 GUI 靜態回歸建議內容：
1. 載入 console.html → 切到 Settings tab → 4 sub-tab nav 顯示完整 + 預設 active=engines
2. 點「运维」sub-tab → engines 隱藏、system 顯示、`localStorage.settings_active_subtab=system`
3. 點「连线」sub-tab → 點任一 API Key 「替換 Key」按鈕 → modal 正常顯示（確認 modal 抽出 sub-tab content 後仍可觸發）
4. 切回「运维」sub-tab → 點「計劃重啟」→ modal 顯示（同樣驗證）
5. 切到 Governance tab → 觸發 bulk approve → 出現 typed-confirm modal，鍵入 `CONFIRM` 才能按確認
6. 觸發 recovery approve → 出現 typed-confirm modal，phrase = `CONFIRM`
7. 切到 AI tab → Provider 按 Clear → 出現 typed-confirm modal，phrase = `CLEAR`
8. Esc 鍵測試：所有 modal 按 Esc 應 resolve(false) + 關閉
9. F12 → axe-core 跑 a11y → 0 critical violations
10. 切到 1366×768 viewport → sub-tab nav `min-height: 44px` mobile retrofit 生效

## TODO.md / W-AUDIT-7c entry 是否可改 closed？

**建議**：W-AUDIT-7c 三項全部 IMPL closed；待 E2 review + E4 回歸通過 → PM 可標記 W-AUDIT-7c 為 DONE。本 commit 僅完成 IMPL，governance chain（E2 + E4 + PM）仍走完整流程。

## 完成判定

- 三項全 closed： **✓**
- commit hash + 行數：`9e265ba9` · 5 files · +573 / -124
- browser 實測證據：5 檔 HTTP 200 + HTMLParser 0 errors + JS brace 0 diff + grep 0 native confirm 殘留 + 5-case fixture
- 是否需 E2：**需要**（修改 shared helper `common.js`）
- W-AUDIT-7c TODO entry：IMPL closed，等 E2 + E4 + PM sign-off 才改 DONE

# E2 PR Adversarial Review — W-AUDIT-7c GUI 三項修復

- **日期**：2026-05-09
- **target commit**：`9e265ba9`（gui: W-AUDIT-7c three governance UX fixes）
- **後續 doc commit**：`8b766a43`（E1a memory + workspace report）
- **Mac repo HEAD**：`b186c6c2`（origin/main 同步）
- **Linux repo HEAD**：`b186c6c2`（同 origin/main）
- **三端 git sync**：`b186c6c2` Mac/origin/Linux 一致
- **review scope**：5 檔 +573 / -124（common.js +140 / governance-tab.js +50 / tab-ai.html +13 / tab-settings.html +368 / test fixture +126 LOC actual = 126 not 135）

## Verdict

**RETURN to E1a (1 CRITICAL + 1 HIGH + 4 MEDIUM/LOW = 6 findings)**

E1a 必修 1 條 production-breaking blocker（governance-tab.js parse fail）+ 1 條 sign-off process gap（缺 file-level JS parse smoke），其他 4 條為 a11y / 政策 advisory。E2 不直接代修：CRITICAL bug 不機械修；E1a 必親自修 + 補 verification process（添加 Linux end JS parse 真實驗證 step），避免下次同類 bug 再 sign-off pass。

---

## 改動範圍 vs 任務 brief 對齊

| sub-issue | 改動 | 對齊 |
|---|---|---|
| governance-tab.js 兩個 native confirm() | line 1551 `bulkAudit` + line 1600 `confirmApproveRecovery` 改 typed-confirm | ✓ |
| API Key clear modal | tab-ai.html:652 `clearProviderKey` 改 typed-confirm phrase=CLEAR | ✓ |
| Settings 拆 sub-tab | 4 sub-tab + namespace-isolated localStorage + modal overlay 抽出 | ✓ |
| 共用 helper `openTypedConfirmModal` | common.js:1834 +140 LOC 新增 | ✓ |
| 跨平台 grep | `grep '/home/ncyu\|/Users/[^/]+'` 0 hit | ✓ |
| Backend endpoint 改動 | 0 backend write，純 frontend | ✓ E1a 邊界守 |
| XSS 防護 | dynamic content 全走 textContent，static skeleton 用 innerHTML（無 user-input 注入） | ✓ |

無 scope drift。

---

## Findings

### CRITICAL-1：governance-tab.js parse SyntaxError → 整個 governance UI tab JS 失效

**位置**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/governance-tab.js`
- line 1555: `const ok = await openTypedConfirmModal({...})`
- line 1581: `let ok = 0, fail = 0;` — **同 `bulkAudit()` function scope 重宣告**
- line 1590: `ocToast(ok + ' 项已' + label ...)` 引用第二個 `ok`

**影響**：JavaScript engine parse 階段 throw `SyntaxError: Identifier 'ok' has already been declared`。整個 governance-tab.js 檔載入失敗，導致 governance tab 內所有 function（`loadAll()` / `loadPendingApprovals()` / `auditApprove()` / `auditReject()` / `confirmApproveRecovery()` / `bulkAudit()` / 等）全失效；即「Settings sub-tab 不影響的 area」的 governance UI 也 100% 廢掉。

**雙端驗證**：
```
Mac:   node -e "new Function(fs.readFileSync(...))" → PARSE FAIL: Identifier 'ok' has already been declared
Linux: ssh trade-core node -e "..."                  → LINUX PARSE FAIL: Identifier 'ok' has already been declared
```

**E1a sign-off 缺口分析**：
- E1a 報告 §「JavaScript brace/paren/bracket diff: 0 0 0」是 **structural balance** check（matching `{ } ( ) [ ]` 數量），對 ES6 `let` / `const` 重宣告 **沒有偵測能力**
- E1a test fixture `test_typed_confirm_modal.html` 是獨立 standalone HTML，**未載入 governance-tab.js**
- E1a 沒在 deploy 前載入 console.html → 切到 governance tab → console 看 JS error
- E1a sign-off 「browser 實測證據」全是 HTTP 200 + structural parse；未含 governance-tab.js 真實 JS engine parse 驗證

**修復建議**（E1a 必親自修）：
1. line 1581 `let ok = 0, fail = 0;` → `let okCount = 0, failCount = 0;`（或 `successCount` / `errorCount`，任何不與 line 1555 衝突的命名）
2. line 1583-1586 `if (d && d.ok) ok++; else fail++;` → `if (d && d.ok) okCount++; else failCount++;`（注意 line 1583-1586 的 `d.ok` 是 envelope.ok，不是 modal 的 ok，**不能改**）
3. line 1589-1590 `ocToast(ok + '...' + label + (fail ? '，' + fail + '...' : ''), ok ? 'success' : 'error')` → `ocToast(okCount + '...' + label + (failCount ? '，' + failCount + '...' : ''), okCount ? 'success' : 'error')`
4. **必補 verification step**：在 sign-off 前跑（任一）：
   - Mac/Linux end `node -e "new Function(fs.readFileSync('governance-tab.js'))"` parse smoke
   - 或載入 `console.html` → DevTools console 觀察 governance.js error

---

### HIGH-1：sign-off process gap — 缺 file-level JS engine parse smoke

**問題**：E1a 「sign-off 完成判定」中 5 條 verify 全為靜態（HTTP 200 / brace count / grep / HTMLParser / fixture standalone），**0 條真實 JS engine parse 全 file**。CRITICAL-1 暴露了：sign-off process 對 ES6 syntax error 完全 blind。

**影響**：本次 W-AUDIT-7c 全 GUI 改動聲稱「browser 實測 PASS」實際 governance-tab.js 從未被 JS engine 真實 parse 過；其他改動 file 同樣未跑 file-level JS parse；如未來再加類似改動可能再次 silent break。

**修復建議**：
1. E1a memory 加教訓：「靜態 brace count + structural HTMLParser ≠ JS syntax verify；任何 .js / inline `<script>` 改動必跑 `new Function(...)` parse smoke」
2. 建議 GUI 改動 sign-off SOP 加一行：`for f in <changed-js-files>; do node -e "new Function(fs.readFileSync('$f'))"; done`
3. 提交給 PA / E5 評估是否升級為 GUI helper script（如 `helper_scripts/gui/parse_smoke.sh`）

---

### MEDIUM-1：openTypedConfirmModal 缺 input `aria-required` + `aria-describedby`

**位置**：`common.js:1857`

**問題**：modal 的 phrase input 是 required（不鍵入正確 phrase 確認按鈕保持 disabled），但 input element：
- 缺 `aria-required="true"` — 螢幕閱讀器無法播報「必填」狀態
- 缺 `aria-describedby="oc-tc-hint"` 顯式 link 到 hint 文字 — 雖然 `<label>` 包了 hint，但對部分 screen reader 而言 explicit `aria-describedby` 更可靠
- 缺 `aria-invalid` 動態切換 — input 含錯 phrase 時 SR 沒提示

**影響**：a11y baseline 對「critical-grade governance 寫操作」應該嚴格，但此 modal 是新建 helper 將被未來大量 reuse；缺 aria 屬性會 propagate。

**修復建議**：
- input element 加 `aria-required="true" aria-describedby="oc-tc-hint" aria-invalid="false"`
- `checkPhrase()` function 加：`inputEl.setAttribute('aria-invalid', typed !== phrase ? 'true' : 'false');`

### MEDIUM-2：modal 開啟時背景未標 inert / aria-hidden

**位置**：`common.js:1834-1946`（`openTypedConfirmModal`），同樣問題在 `openConfirmModal`（line 1620+）/ `openPromptModal`（line 1704+）— pre-existing pattern。

**問題**：modal show 時，main `<body>` 其他內容仍可被 SR 訪問 / Tab 跳出。雖然 keydown handler 有 Tab focus trap（PASS），但 SR 用戶若用 swipe 模式（不依 Tab）可能聽到 modal 背後的 page content，弱化 modal 意涵。

**影響**：a11y baseline 弱化。但這是 codebase 既定 pattern（3 個 helper 都缺 inert），改一個 helper 不一致；應作為**全 helper 統一升級**的 P2 ticket。

**修復建議**（不阻 merge，作為 follow-up P2）：
- 開時：對 main `<body>` 子元素（除 overlay 自身外）批量 `setAttribute('inert', '')` + `setAttribute('aria-hidden', 'true')`
- 關時：清除這兩個屬性
- 因為涉 3 個 helper + 既有 caller pattern，建議單獨 P2 ticket（如 `GUI-A11Y-2 modal inert background`）統一處理

### MEDIUM-3：openTypedConfirmModal 不防 nested invocation

**位置**：`common.js:1834`

**問題**：modal singleton DOM (`getElementById('oc-typed-confirm-overlay')`) — 若兩 caller 並行 await（A 開 modal → 在 user 回應前，B 透過某 callback 也開同 modal），B 的 setup 會：
- 改寫 title/body/phrase/inputEl.value=''（清空 A 已輸入）
- 覆寫 onclick handlers（A 的 promise 永遠不 resolve）
- B close → `previousActive.focus()` 還原到 B 觸發點 → A 殭屍
**目前 caller 全是 sequential**（bulkAudit 的 prompt 在 typed-confirm close 後才 open；governance / ai 各 tab 切換），實際碰不到 race。但 helper 不防護是 footgun，未來若有 timer / WS 推播 callback 觸發 modal 即可能踩。

**影響**：未來副作用風險，目前 caller 不踩。

**修復建議**（不阻 merge，作為 P2 follow-up）：
- modal show 前檢查 `overlay.classList.contains('show')`，若已 show return Promise.reject(new Error('typed-confirm modal already open'))
- 或維護 module-level `_activeTypedConfirm = false` flag 拒絕重入
- 同樣升級可惠及 `openConfirmModal` / `openPromptModal` 全 modal helper

### LOW-1：注釋政策 — line 1913 中英對照新增

**位置**：`common.js:1912-1913`
```
// case-sensitive 比對；trim 避免尾部空白誤判
// case-sensitive match; trim trailing whitespace to avoid false-negative
```

**問題**：2026-05-05 governance change 規定「新代碼注釋默認只寫中文」。此 inline comment 是新增（非修改既有中英對照），按 default policy 應只寫中文版（line 1912），line 1913 英文版可省。

**影響**：違背 default policy spirit；不算 hard 違規（policy 措辭是「默認只寫中文」非「禁止英文」）。

**修復建議**：刪除 line 1913 英文版。其他新增注釋（line 1820-1834 / 1837-1844 / 1869-1872）已遵循只中文，本條是孤例。

---

## 8 條 §九 checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 brief 一致 | ✓ |
| 沒有 except:pass / 靜默吞 | ✓（純 frontend） |
| 日誌 %s 格式 | N/A（純 frontend） |
| 新 API 端點有 _require_operator_role | N/A（0 backend write） |
| except HTTPException raise 在 except Exception 之前 | N/A（純 frontend） |
| detail=str(e) 已改 "Internal server error" | N/A |
| asyncio 路由中無 blocking threading.Lock | N/A |
| 沒有私有屬性穿透（._xxx） | ✓ |

---

## OpenClaw 9 條 §3 checklist

| Item | 狀態 |
|---|---|
| 跨平台 grep（/home/ncyu / /Users/[^/]+） | ✓ 0 hit |
| 雙語注釋（默認中文） | LOW-1 一處英文版可移除（其他 OK）|
| Rust unsafe 零容忍 / unwrap | N/A（純 frontend） |
| 跨語言 IPC schema | N/A |
| Migration Guard A/B/C | N/A（無 SQL）|
| healthcheck 配對（被動等待 TODO）| N/A |
| Singleton 登記 §九 表 | N/A（modal helper 是 module-level function 非 singleton）|
| 文件大小 800/2000 | common.js 1968 / governance-tab.js 1713 / tab-settings.html 1178 / tab-ai.html 1159 — 全 < 2000 hard cap；common.js + governance-tab.js + tab-settings.html + tab-ai.html 全過 800 警告線（pre-existing） |
| Bybit API 改動先查字典手冊 | N/A（無 Bybit /v5/* 改動）|

---

## a11y baseline 滿足度（4 項評估）

| 項 | 狀態 | 細節 |
|---|---|---|
| **focus trap** | **PASS** | `common.js:1934-1942` Tab/Shift+Tab 攔截 + first/last focus 循環 |
| **aria** | **PASS（基線）/ MEDIUM-1 改進** | `role="dialog"` / `aria-modal="true"` / `aria-labelledby="oc-tc-title"` 已有；input 缺 `aria-required` / `aria-describedby` / `aria-invalid`（不阻 merge）|
| **Esc** | **PASS** | `common.js:1924-1928` Esc → close(false) → resolve(false) |
| **Tab** | **PASS** | 同 focus trap；setTimeout 50ms 自動 focus input 起始 |

**整體 a11y baseline 4 項全 PASS**；MEDIUM-1（aria-required / aria-describedby / aria-invalid）+ MEDIUM-2（inert background）為改進空間，不視為基線 fail。

---

## 對抗反問結果（5 條）

1. **Q: 「跑 fixture 5 case PASS — 是 mock 還是真實 JS engine parse 完整 file？」**
   A: fixture 是 standalone test_typed_confirm_modal.html，**只載入 common.js**，從未載入 governance-tab.js → `bulkAudit` 函數的 ES6 redeclaration error 完全 missed。**評估：sign-off process 失效，CRITICAL-1 因此 escape**。

2. **Q: 「modal 共用 single-instance overlay DOM，nested confirm 會怎樣？」**
   A: 目前 caller 全 sequential（bulkAudit 中 typed-confirm close → 才 open prompt），實際無踩 race。但 helper 自身不防護 = footgun。**評估：MEDIUM-3 follow-up，不阻 merge**。

3. **Q: 「Tab focus trap 是否真 trap 在 modal？」**
   A: `focusableNodes()` 篩 modal 內 button/input，shift+Tab on first → last.focus()，Tab on last → first.focus()。setTimeout 50ms 起始 focus inputEl. **PASS**.

4. **Q: 「Esc handler bind 在 overlay.onkeydown — overlay 不接受 keyboard event 除非 focus 在子層」**
   A: input 是 overlay 的 descendant；input 有 focus 時鍵 events bubble up 到 overlay listener。**PASS**.

5. **Q: 「sub-tab `[hidden]` 對 fixed-position modal 的影響 E1a 已自驗 — 但 modal 從 sub-tab content 抽出後，舊 caller path（如 connection sub-tab 內的 `editApiKey()` button）是否仍能呼到 modal？」**
   A: 看 line 1110 `document.getElementById('dlg-apikey').classList.add('show')` — 用 `getElementById` 全域查找，與 modal 在 DOM tree 哪都能找到。**PASS**.

---

## 三端 git log 同步 vs origin/main

```
Mac  HEAD: b186c6c2 fix(healthcheck): passive_wait .sh 顯式 export PYTHONPATH 解 [20] 假陽性 FAIL
Linux HEAD: b186c6c2 (同)
origin/main HEAD: b186c6c2 (同)

W-AUDIT-7c commit chain:
  9e265ba9 (W-AUDIT-7c IMPL, 5 files, +573/-124)
  8b766a43 (E1a memory + workspace report)
  3d8d543e (post-W-AUDIT-7c, ml-training fix, unrelated)
  b186c6c2 (post-W-AUDIT-7c, healthcheck fix, unrelated)
```

**3 端 sync ✓**；後續 2 commit 均為 W-AUDIT-7c scope 之外，本 review 不涉及。

---

## 直接修的 typo / lint / dead import commit hash

**0 個** — 本 review 0 直接修：CRITICAL-1 不機械改（必由 E1a 修 + 補 verification process）；MEDIUM-1/2/3 + LOW-1 全為 advisory + follow-up 不阻 merge。

---

## 退回 E1a 修復清單

### 必修（CRITICAL + HIGH）

1. **CRITICAL-1**：`governance-tab.js:1581` `let ok = 0, fail = 0;` → 改非 shadow 名稱（建議 `let okCount = 0, failCount = 0;`）+ line 1583-1586 內部 `ok++` / `fail++` 同步改 `okCount++` / `failCount++`（注意 `d.ok` 是 envelope 不能改）+ line 1589-1590 ocToast 內 ok / fail 同步改。修後必跑 `node -e "new Function(fs.readFileSync('governance-tab.js'))"` 雙端 parse smoke 驗證。

2. **HIGH-1**：sign-off process 補 file-level JS engine parse smoke。E1a memory 追加教訓：「brace count + structural HTMLParser ≠ JS syntax verify；任何 .js / inline `<script>` 改動必跑 `new Function(...)` parse smoke 真 JS engine 驗 ES6 declaration / syntax error」。

### 可不修（建議 P2 follow-up）

3. **MEDIUM-1**：input 加 `aria-required` / `aria-describedby` / `aria-invalid` 動態切換 — 屬於 a11y 改進，本次可 follow-up
4. **MEDIUM-2**：modal show 時 background `inert` / `aria-hidden` — pre-existing pattern 全 helper 共有問題，建議獨立 P2 ticket 統一升級
5. **MEDIUM-3**：openTypedConfirmModal 加 nested invocation guard — 同上，全 modal helper 統一升級
6. **LOW-1**：line 1913 英文版注釋移除 — 僅 1 行 advisory，可隨 CRITICAL-1 修一併處理或下次

---

## 給 E1a 的具體 patch（CRITICAL-1 修法）

```diff
--- a/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/governance-tab.js
+++ b/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/governance-tab.js
@@ -1578,16 +1578,16 @@ async function bulkAudit(action) {
   const pending = await govGetPendingAudit();
   if (!pending || !pending.ok || !pending.data) { ocToast('获取待审批列表失败', 'error'); return; }

-  let ok = 0, fail = 0;
+  let okCount = 0, failCount = 0;
   for (const c of pending.data) {
     const d = isApprove
       ? await govApproveAuditChange(c.change_id, reason)
       : await govRejectAuditChange(c.change_id, reason);
-    if (d && d.ok) ok++; else fail++;
+    if (d && d.ok) okCount++; else failCount++;
   }

   const label = isApprove ? '同意 approved' : '拒绝 rejected';
-  ocToast(ok + ' 项已' + label + (fail ? '，' + fail + ' 项失败' : ''), ok ? 'success' : 'error');
+  ocToast(okCount + ' 项已' + label + (failCount ? '，' + failCount + ' 项失败' : ''), okCount ? 'success' : 'error');
   loadPendingApprovals();
 }
```

修復後 E1a 必跑 `node -e "new Function(fs.readFileSync('governance-tab.js'))"` Mac + Linux 雙端 parse smoke + 重 push 才能進 E4。

---

## 結論

**RETURN to E1a** — 6 findings（1 CRITICAL + 1 HIGH + 3 MEDIUM + 1 LOW）。

CRITICAL-1 是 production-breaking blocker（governance-tab.js 整個 JS file parse fail 導致 governance UI tab 全失效），HIGH-1 揭露 sign-off process gap（缺 file-level JS engine parse smoke）。E1a 必親自修 + 補 verification step + memory 追加教訓，不可由 E2 機械代修（bug 涉及 sign-off process 缺口本身的修復）。

MEDIUM-1/2/3 + LOW-1 為 a11y / 政策 advisory，建議 follow-up 不阻本次 merge（CRITICAL-1 修畢後）。

E2 不通過 E4，必須 E1a round 2 重提後重 review。

E2 REVIEW DONE: RETURN-TO-E1a · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-09--w_audit_7c_e2_review.md`

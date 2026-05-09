# E2 PR Adversarial Review — W-AUDIT-7c Round 2

- **日期**：2026-05-09
- **target commits**：`0fbed710`（gui round 2 fix）+ `78d5d013`（doc backfill）
- **Mac local HEAD**：`1448e0a1`（origin/main 同步；後續 ml_training fix `1448e0a1` 不在本 review scope）
- **Linux trade-core HEAD**：`1448e0a1`（三端 sync ✓）
- **三端 git sync**：Mac / origin/main / Linux 三端同 `1448e0a1`，W-AUDIT-7c round 2 commits 全到位
- **review scope**：4 檔（governance-tab.js +164 / common.js +6 / tab-ai.html +13 / fixture -2）+ memory.md + report；diff 範圍與 brief 一致
- **上輪 6 findings 收口比例**：4/6 closed + 2/6 partial-fail（singleton swallowed reject + LOW-6 英文注釋未刪）

## Verdict

**RETURN to E1a · 1 HIGH + 2 MEDIUM + 1 LOW = 4 new + retained findings**

E1a Round 2 修對了 4/6 上輪 finding（CRITICAL-1 SyntaxError / HIGH-2 sign-off SOP / fixture garbage / 9 項 A3 自評）— 整體解了 production-breaking blocker。但兩處 round 1 verdict 條目未真正落地：
- **MEDIUM-5 (round 1) singleton check**：實裝了 `Promise.reject` 但**所有 3 個 caller 沒 try/catch 包 await**，rejected promise 變 silent unhandled rejection（user 看不到 toast，只 console.error）。修了一半，正式破了「不靜默」初衷。
- **LOW-6 (round 1) 英文 inline 注釋**：line 1919（原 1913）`// case-sensitive match; trim trailing whitespace to avoid false-negative` 仍在；E1a report 自評未提及，未刪。

加上 round 2 IMPL 新引入的 1 HIGH (`Promise.reject` swallow path) + 1 MEDIUM (cache `_lastPendingAudit` 宣告但只寫不讀 dead-data state) + 1 LOW（rename 不一致 — bulkAudit 用 `proceed` 但 confirmApproveRecovery 仍 `ok`，雖無 SyntaxError 但 inconsistency 違 round 1 verdict patch 建議統一）+ LOW-6 retained。

E2 不直接代修：HIGH 涉及 caller-side error handling pattern（3 處 try/finally 是否要加 catch + toast），是 UX 設計決策；E1a 親自選方案。

---

## 上輪 6 findings 收口狀態

| Finding | 嚴重度 | 狀態 | 證據 |
|---|---|---|---|
| **CRITICAL-1** SyntaxError `ok` shadowing | CRITICAL | **PASS** | `node --check governance-tab.js` EXIT=0；`grep -E '\\b(let\|const\|var)\\s+ok\\b'` 1 hit（line 1727 `confirmApproveRecovery` scope，無 redeclare）；rename `okCount`/`failCount`/`proceed` 落地 |
| **HIGH-2** sign-off SOP 缺 node --check | HIGH | **PASS** | E1a memory line 298 加教訓「GUI E1a 任務 sign-off 必跑 `node --check <file>` 真實 V8 parser」；jsdom 驗證流程記錄到 memory line 309-322；建議升級 helper script 為 P2 follow-up（不阻 round 2） |
| **MEDIUM-3** input aria-required/-describedby/-invalid | MEDIUM | **DEFERRED-P2** | round 2 未實裝（grep 0 hit）；report 未提；不阻 merge 但建議建 P2 ticket `GUI-A11Y-1` |
| **MEDIUM-4** modal background inert/aria-hidden | MEDIUM | **DEFERRED-P2** | pre-existing 全 modal helper 共有問題；建議 P2 ticket `GUI-A11Y-2 modal inert background`（不阻本 round） |
| **MEDIUM-5** openTypedConfirmModal nested invocation guard | MEDIUM | **PARTIAL-FAIL** | `Promise.reject(new Error('modal already open'))` 實裝在 common.js:1846-1851，但 3 個 caller（governance-tab.js:1589 / 1727、tab-ai.html:660）`await` 在 try/finally 內無 catch → reject 變 silent unhandled rejection。半實 — guard 存在但 caller-side 沒接住，user 看不到 toast 反饋（與 round 2 [#8] cancel toast 設計初衷矛盾）|
| **LOW-6** line 1913 英文注釋政策 | LOW | **FAIL** | 上輪 line 1913 → round 2 line 1919（檔變大行偏移）；`// case-sensitive match; trim trailing whitespace to avoid false-negative` 仍存在；E1a round 2 report 未提；違背 2026-05-05 governance change（新代碼默認只中文）|

整體 4/6 closed + 2/6 partial-fail。

---

## Round 2 新發現 issue list

### HIGH-1：openTypedConfirmModal singleton reject 變 silent unhandled rejection

**位置**：caller side
- `governance-tab.js:1589`（bulkAudit）`const proceed = await openTypedConfirmModal({...})` 在外層 `try/finally` (line 1571) 內，無 `catch`
- `governance-tab.js:1727`（confirmApproveRecovery）同樣 `try/finally` (line 1687) 無 `catch`
- `tab-ai.html:660`（clearProviderKey）`try/finally` (line 659) 無 `catch`

**問題**：round 2 [#7] 為 nested invocation 加了 singleton guard：
```js
// common.js:1850
if (overlay && overlay.classList.contains('show')) {
  console.error('[openTypedConfirmModal] modal already open; rejecting concurrent open');
  return Promise.reject(new Error('modal already open'));
}
```
但 3 處 caller 都用 `const x = await openTypedConfirmModal(...)` 不帶 `.catch()` 也不在 try 後接 catch block。當 rejected promise 被 await：
1. **`finally` 區塊跑** → trigger button 被 re-enable（這部分 OK）
2. **JavaScript 拋出 unhandled rejection** → 異步 exception 浮到 `window.onunhandledrejection`，但 codebase 全域 grep 0 hit（無 handler）→ 在 Chrome / Safari / Firefox 都會吃進 devtools console，**user side 沒任何反饋**
3. **`if (!proceed)` / `if (!ok)` 之後的 cancel toast 永遠不會跑**（exception 已 throw 跳出區塊）

**對抗實證**（程式碼追蹤）：
```
情境：user A 開了 modal，user A 還沒輸 phrase；
     之前 user 不小心連點 trigger button 觸發 race 第二次 invocation。

預期：第二次 modal show 失敗，user 看到 toast「modal 已開啟，請先處理當前彈窗」
實際：
  - 第二次 await 拋 'modal already open' Error
  - finally 跑，re-enable trigger button（**反而讓 user 以為按鈕沒反應，可能再點第三次**）
  - 沒 toast / 沒 banner / 沒 user-facing 提示
  - 只 devtools console.error（user 看不到）
```

**影響嚴重性**：HIGH — 違背 round 2 [#8] cancel toast「不靜默」設計初衷；race 場景 user 完全看不到反饋；button re-enable 還可能誤導以為按鈕掛了。

**修復建議**（E1a 親決）：
- 方案 A（最少改）：3 處 await 包 try/catch：
  ```js
  let proceed;
  try {
    proceed = await openTypedConfirmModal({...});
  } catch (e) {
    if (e && e.message === 'modal already open') {
      ocToast('已有確認彈窗開啟，請先處理當前彈窗 / Modal already open', 'warn');
      return;
    }
    throw e;  // 其他錯誤照舊
  }
  if (!proceed) { ... }
  ```
- 方案 B：common.js singleton guard 改 return `false` 不 reject（語意降階為「拒絕但不是 error」）— 修改範圍小，但語意較弱（caller 無法區分「user 取消」vs「nested rejected」）
- 方案 C：加全域 `window.onunhandledrejection` handler 統一 fallback toast — 但會吃掉所有 unhandled rejection 不只本 case，副作用大

PM 推薦方案 A：caller-side 顯式 catch + toast，明確語意，不擴大副作用。

---

### MEDIUM-1：line 1919 英文 inline 注釋未刪（LOW-6 retained）

**位置**：`common.js:1919`
```js
// case-sensitive 比對；trim 避免尾部空白誤判
// case-sensitive match; trim trailing whitespace to avoid false-negative
```

**問題**：上輪 LOW-6 advisory；round 2 未順手清；E1a round 2 report 也未提。違背 2026-05-05 governance change「新代碼注釋默認只寫中文」。E1a round 2 自說「中文輸出 + 中文注釋（廢除 bilingual mandate 2026-05-05）— ✓ 新加注釋全中文」與此實況矛盾。

**修復建議**：`Edit` 刪 line 1919 一行。E2 可直接修（屬於上輪 LOW-6 + obvious typo/lint 範疇），但本輪 E2 不代修以保留 E1a sign-off 完整性 — round 2 結束 E1a 應親自順手清。

---

### MEDIUM-2：`_lastPendingAudit` 宣告但只寫不讀（dead-write data state）

**位置**：`governance-tab.js:26` 宣告，line 1577 / 1667 / 1670 寫入，但**全檔 0 read site**（grep 確認）。

**問題**：round 2 [#5][#6] 設計意圖是「bulkAudit / confirmApproveRecovery modal body 內顯示具體影響時可直接讀取」（comment line 21-22），但實際 bulkAudit 在 line 1565 直接呼 `await govGetPendingAudit()` 重新 fetch，沒讀 cache；confirmApproveRecovery 用的是 `_lastPendingRecovery` 不是 `_lastPendingAudit`。`_lastPendingAudit` 寫了 3 處但 0 讀 = dead data state。

**影響嚴重性**：MEDIUM — 不致 bug，但
1. 違背 E1a 自宣稱「無新 API call，從 list cache `find()`」設計（bulkAudit 仍 fetch）
2. 多餘的 mutable 全域狀態 = 未來 maintainer 困擾
3. 若哪天 caller 想用 cache，發現是 stale（多 tab 場景）需要再加 freshness check

**修復建議**（E1a 親決）：
- 方案 A：bulkAudit 改用 `_lastPendingAudit` cache 先試，empty / stale 才 fetch — 補完設計意圖
- 方案 B：徹底刪 `_lastPendingAudit`（line 26 declaration + line 1577 / 1667 / 1670 寫入），明確 round 2 不引入此 cache
- 方案 C：留著但加注釋「reserved for future use」
PM 推薦方案 B：YAGNI，dead data state 比錯設計更可維護。

---

### LOW-1：modal 變數命名 rename 不一致（confirmApproveRecovery 仍用 `ok`）

**位置**：`governance-tab.js:1727`：`const ok = await openTypedConfirmModal({...})`

**問題**：round 1 verdict patch 建議「outer rename `ok → proceed`」+「inner counter rename `ok/fail → okCount/failCount`」是因為 same-scope shadowing。round 2 在 bulkAudit (line 1589) 用 `proceed`，但 confirmApproveRecovery (line 1727) 仍 `ok`。

技術層面：confirmApproveRecovery scope 內**沒有第二個 `ok` 重宣告**（沒 inner counter loop），所以 node --check PASS — 不是 SyntaxError。但語意層面 inconsistent：兩個並肩函數同樣用 `openTypedConfirmModal` 結果一個叫 `proceed` 一個叫 `ok`，未來新增 inner counter 時又會踩同樣坑。

**影響嚴重性**：LOW — 不致 bug，但 future-proofing inconsistent。

**修復建議**：line 1727 + 1736 同步 rename `const ok` → `const proceed` + `if (!ok)` → `if (!proceed)`。

---

## 8 條 §九 checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 brief 一致 | ✓（4 檔 + memory + report，無 scope drift） |
| 沒有 except:pass / 靜默吞 | ✓（純 frontend；但 HIGH-1 是 silent unhandled rejection — 同類型問題的 JS 版） |
| 日誌 %s 格式 | N/A（純 frontend） |
| 新 API 端點有 _require_operator_role | N/A（0 backend write） |
| except HTTPException raise 在 except Exception 之前 | N/A |
| detail=str(e) 已改 "Internal server error" | N/A |
| asyncio 路由中無 blocking threading.Lock | N/A |
| 沒有私有屬性穿透（._xxx）| ✓ |

---

## OpenClaw 9 條 §3 checklist

| Item | 狀態 |
|---|---|
| 跨平台 grep（/home/ncyu / /Users/[^/]+） | ✓ 0 hit |
| 雙語注釋（默認中文）| **MEDIUM-1**：line 1919 retained 英文注釋；其他 round 2 新加注釋全中文 |
| Rust unsafe 零容忍 | N/A |
| 跨語言 IPC schema | N/A |
| Migration Guard A/B/C | N/A |
| healthcheck 配對（被動等待 TODO）| N/A |
| Singleton 登記 §九 表 | N/A（modal helper 是 module-level function 非 singleton；overlay DOM 是 lazily injected reuse pattern） |
| 文件大小 800/2000 | governance-tab.js 1830 / common.js 1974 / tab-ai.html 1165 / fixture 124 — 全 < 2000 hard cap；governance-tab.js + common.js 過 800 警告線（pre-existing；round 2 增 `+164/+6` LOC 推近 2000 邊緣）|
| Bybit API 改動先查字典手冊 | N/A |

---

## 對抗反問結果（5 條）

1. **Q：「修了 CRITICAL-1，整檔還剩 `\\bok\\b` 殘留？」**
   A：grep `(let|const|var)\\s+ok` 1 hit（line 1727 confirmApproveRecovery，scope 內單獨宣告，node --check EXIT=0 → 無 SyntaxError）；但 future-proofing 視角不一致 = LOW-1。`\\bok\\b` 全檔 27 hit，全為 `d.ok` envelope check 或 ocToast type，無新 redeclaration risk。**評估**：critical 解了，但 inconsistent rename 留 LOW-1。

2. **Q：「singleton check 真實裝？是 reject 還是 console.warn？」**
   A：實裝 `console.error` + `Promise.reject(new Error('modal already open'))`（common.js:1850-1851），不是 console.warn fallthrough。但 caller-side 沒 catch → silent unhandled rejection = HIGH-1。`Promise.reject` 表象正確但 end-to-end UX 失效。**評估**：guard 半實，user 仍看不到反饋。

3. **Q：「bulkAudit 加 fetch pending list — race 期間 list 變動？」**
   A：fetch → modal show 之間 ~50-200ms，只要 user 不在 modal 顯示後另起 tab 觸發 governance approve，list 不會在這視窗變。worst case：list shrink（user 在 fetch 後從 audit 那批先 manual approve），bulkAudit confirm 時呼 `govApproveAuditChange(c.change_id, ...)` 對已 approve 的 change_id 後端會 idempotency 401 / 已成功標 — 後端側保護存在。**評估**：window 短 + 後端 idempotent 雙保護，race 不阻 merge。

4. **Q：「confirmApproveRecovery cache miss fallback：fresh fetch 失敗會怎樣？」**
   A：line 1696-1701 try/catch，failed → modal 顯通用 body「請求細節無法載入，僅以 ID 識別」（line 1724），仍能繼續 confirm flow — degraded but not blocked。`govGetPendingRecovery` 失敗 → 進 catch 把 `_lastPendingRecovery` 不 mutate，detailLines = '' → modal 顯 fallback。**評估**：fallback 設計合理，PASS。

5. **Q：「bulk partial fail toast 列 change_id list — 超長截斷處理？」**
   A：line 1646-1648 `failedChangeIds.slice(0, 10).join(', ')` + `'...(+N)'` 超過 10 截斷，符合 toast UI 寬度約束。但 toast 本身 character cap 視 `ocToast` 實作（grep 看 ocToast 是直 textContent 注入，無自動 truncate），長 change_id（如 UUID 36 char）× 10 + 開銷 ~ 400+ char — 可能超 toast viewport。**評估**：截斷邏輯存在，但長 ID 場景 toast 會 visual overflow（CSS line-wrap 可緩解）；非阻 merge 風險，建議 P2 加 max-width + ellipsis。

---

## 三端 git log 同步 vs origin/main

```
Mac local HEAD:    1448e0a1 test(ml-training): IPC __auth handshake regression + LOW-1 cleanup
GitHub origin/main: 1448e0a1 (同)
Linux trade-core:   1448e0a1 (同)

W-AUDIT-7c round 2 commit chain:
  0fbed710 (W-AUDIT-7c round 2 fix per A3 verdict FALSE_CLOSED, 6 files, +485/-71)
  78d5d013 (E1a memory + report commit hash backfill)
  1448e0a1 (post-W-AUDIT-7c, ml_training fix, unrelated — 隔壁 sub-agent push)
```

**3 端 sync ✓**；後續 1 commit 為 ml_training scope，本 review 不涉及。

---

## 整體 PASS rate

- 上輪 6 findings：4 PASS（CRITICAL-1 / HIGH-2 / MEDIUM-3 deferred / MEDIUM-4 deferred）+ 2 partial/fail（MEDIUM-5 silent reject / LOW-6 retained）
- Round 2 9 自評項：8 IMPL OK + 1 設計矛盾（[#7] singleton + [#8] cancel toast 衝突 — 沒接 reject 變 silent）
- Round 2 新引入：3 issues（HIGH-1 caller catch / MEDIUM-1 LOW-6 retained / MEDIUM-2 dead `_lastPendingAudit` / LOW-1 rename inconsistency）

**淨 close rate**：4/6 round 1 + 8/9 round 2 IMPL = **12/15 closed**；3 retained + 4 new = **7 outstanding**

---

## 退回 E1a 修復清單

### 必修（HIGH）
1. **HIGH-1**：3 處 `await openTypedConfirmModal(...)` 補 try/catch + `ocToast('modal already open', 'warn')` + return；governance-tab.js:1589 + 1727、tab-ai.html:660 各一處。或選方案 B（singleton guard 改 return false）但需更新 common.js 注釋說明語意降階。

### 建議修（MEDIUM）
2. **MEDIUM-1（LOW-6 retained）**：刪 `common.js:1919` 英文注釋「`// case-sensitive match; trim trailing whitespace to avoid false-negative`」。E1a 順手 1 行 Edit。
3. **MEDIUM-2**：`_lastPendingAudit` 死狀態 — 推薦方案 B 徹底刪（line 26 + 1577 + 1667 + 1670）；或方案 A 在 bulkAudit 改用 cache 補完設計意圖。

### 建議修（LOW）
4. **LOW-1**：governance-tab.js:1727 / 1736 同步 rename `const ok` → `const proceed`。

### 仍 deferred-P2（不阻本 round）
5. round 1 MEDIUM-3：input aria-required/-describedby/-invalid 改進
6. round 1 MEDIUM-4：modal background inert/aria-hidden 全 helper 統一升級
7. 新 LOW（adversarial #5）：toast 長 change_id list visual overflow CSS 加 max-width + ellipsis

---

## E2 直接修的 typo / lint / dead import

**0 個** — 本 review 0 直接修：

- HIGH-1 涉設計選擇（caller catch vs reject vs return false）→ 不機械修
- MEDIUM-1 LOW-6 retained 是 E1a sign-off 自我矛盾（自宣稱「新加注釋全中文」但漏 line 1919）→ E1a 親修才能修正自評
- MEDIUM-2 `_lastPendingAudit` 涉設計選擇（補 cache 用法 vs 刪宣告）→ E1a 親決
- LOW-1 rename inconsistency 涉是否要全 codebase 統一 modal return var 命名 → 留 E1a

---

## 結論

**RETURN to E1a · 1 HIGH + 2 MEDIUM + 1 LOW + 2 retained advisory**

E1a Round 2 對 round 1 6 findings 收口 4/6（CRITICAL + HIGH + 2 deferred-P2 OK），但兩處 partial-fail：
- MEDIUM-5 singleton check 表象實裝但 caller 不接 reject → silent UX failure
- LOW-6 英文注釋未刪 + 自評矛盾

加上 round 2 新引入 1 HIGH（caller-side error handling）+ 1 MEDIUM（dead `_lastPendingAudit` cache）+ 1 LOW（rename inconsistency）。

**E2 不通過 E4**，必 round 3 重提後重 review。

優先級提示給 E1a：HIGH-1 是真 bug（user race 場景 button re-enable 但無 toast，誤導再點），必修；其他 MEDIUM/LOW 可一併處理。建議 round 3 commit 同包：HIGH-1 catch + MEDIUM-1 line 1919 刪 + MEDIUM-2 `_lastPendingAudit` 刪 + LOW-1 rename 統一。

E2 REVIEW DONE: RETURN-TO-E1a · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-09--w_audit_7c_round2_e2_review.md`

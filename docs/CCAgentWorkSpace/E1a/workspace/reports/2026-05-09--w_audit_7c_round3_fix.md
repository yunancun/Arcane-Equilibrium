# W-AUDIT-7c Round 3 Fix — E1a Sign-off

**Date**: 2026-05-09
**Branch**: main
**Base**: `940186ee` (E2 round 2 verdict RETURN-TO-E1a)
**Scope**: HIGH-1 silent unhandled rejection (3 sites) + MEDIUM-1 cosmetic + LOW-1 cosmetic
**Status**: 3 actionable FIXED · 1 deferred → P2 ticket

---

## 1. 任務摘要

A3 round 2 verdict TRUE_CLOSED 8.4/10（B+），9/9 brief 全 PASS；E2 round 2 verdict RETURN-TO-E1a，senior view catch 出 A3 漏的 HIGH-1：

> Round 2 [#7] singleton reject 設計與 [#8] cancel toast 設計互相衝突 — modal 已開啟時 `reject(new Error('modal already open'))` 但 caller `await openTypedConfirmModal(...)` 沒 try/catch → silent unhandled promise rejection；`finally` 仍跑 → trigger button 被 re-enable（誤導 user 以為「按了沒反應，再點一次」）→ 違背「不靜默」初衷。

Round 3 範圍：
- HIGH-1（必修）：3 處 `await openTypedConfirmModal(...)` 在 try/finally 無 catch
- MEDIUM-1（必修，cosmetic）：`common.js:1919` 英文注釋殘留
- LOW-1（必修，cosmetic）：`governance-tab.js` `const ok` 與 `const proceed` rename 不一致
- MEDIUM-2（**deferred**）：`_lastPendingAudit` dead-write — 升 P2 ticket

---

## 2. 三件 actionable 修復明細

### 2.1 HIGH-1 silent unhandled rejection（FIXED）

| # | 檔案 | 行區間（after） | Before（round 2） | After（round 3） |
|---|---|---|---|---|
| 1 | `program_code/.../app/static/governance-tab.js`（bulkAudit） | 1589-1614 | `const proceed = await openTypedConfirmModal({...});` 不接 catch | 包 `try { proceed = await ... } catch (err) { ... toast warn/error; return; }` |
| 2 | `program_code/.../app/static/governance-tab.js`（confirmApproveRecovery） | 1741-1764 | `const ok = await openTypedConfirmModal({...});` 不接 catch | 包 `try { proceed = await ... } catch (err) { ... toast warn/error; return; }` + rename `ok` → `proceed` |
| 3 | `program_code/.../app/static/tab-ai.html`（clearProviderKey） | 660-684 | `const ok = await openTypedConfirmModal({...});` 不接 catch | 包 `try { proceed = await ... } catch (err) { ... toast warn/error; return; }` + rename `ok` → `proceed` |

**統一 catch pattern**（3 處皆相同）：

```js
let proceed;
try {
  proceed = await openTypedConfirmModal({ ... });
} catch (err) {
  if (err && err.message === 'modal already open') {
    ocToast('已有確認對話框打開，請先完成當前操作 / Another confirm dialog is open', 'warn');
  } else {
    ocToast('開啟確認對話框失敗 / Open confirm dialog failed: ' + (err && err.message || err), 'error');
  }
  return; // finally 會 re-enable button
}
if (!proceed) {
  ocToast('已取消...', 'neutral');  // round 2 [#8] cancel toast 保留
  return;
}
// 後續業務邏輯
```

設計要點：
- `let proceed;` 宣告在 try 外，catch return 不洩漏 (caller 看不到 stale `proceed`)
- `err.message === 'modal already open'` 嚴格比對 helper 約定字串（`common.js:1851`），其他 unexpected error 走 fallback path 顯 error toast
- `return` 後 outer try/finally 仍跑 → trigger button 復位（race-safe）
- toast type 三態化：singleton race = `'warn'`（user 行為糾正）/ unexpected error = `'error'`（system fail）/ cancel = `'neutral'`（round 2 既有）

### 2.2 MEDIUM-1 cosmetic — common.js:1919 英文注釋（FIXED）

Before（`common.js:1917-1919`）：
```js
function checkPhrase() {
  // case-sensitive 比對；trim 避免尾部空白誤判
  // case-sensitive match; trim trailing whitespace to avoid false-negative
  var typed = (inputEl.value || '').replace(/\s+$/, '');
```

After（`common.js:1917-1918`）：
```js
function checkPhrase() {
  // case-sensitive 比對；trim 避免尾部空白誤判
  var typed = (inputEl.value || '').replace(/\s+$/, '');
```

依據：CLAUDE.md §七 注釋規範（2026-05-05 governance change） — 「修改既有中英對照塊時移除英文只保留中文」。

### 2.3 LOW-1 cosmetic — `const ok` 與 `const proceed` rename 不一致（FIXED）

| 檔案 | Function | 變數 round 2 | 變數 round 3 |
|---|---|---|---|
| governance-tab.js | bulkAudit | `proceed`（已 rename） | `proceed`（不變） |
| governance-tab.js | confirmApproveRecovery | `ok` | `proceed`（HIGH-1 修復同 commit rename） |
| tab-ai.html | clearProviderKey | `ok` | `proceed`（HIGH-1 修復同 commit rename） |

理由：雖然不同 function scope 不衝突，但下次 maintainer 從 bulkAudit copy-paste 到別處 refactor 出 inner counter `ok` 就立刻爆 SyntaxError（round 2 [#1] 教訓）。round 3 統一全部 modal-await 結果變數命名為 `proceed`。

---

## 3. Deferred — MEDIUM-2 `_lastPendingAudit` dead-write（OUT_OF_SCOPE）

E2 round 2 review 點到 `governance-tab.js:26 / 1577 / 1667 / 1670` 4 處寫入 `_lastPendingAudit`，但 0 callsite 讀取（bulkAudit 仍 fetch 不讀 cache）。

**理由不修**：本 round 3 brief 範圍明示「不含此項」，升 P2 ticket。

**P2 ticket 建議內容**：
- 標題：governance-tab dead-write cleanup
- 描述：刪 `_lastPendingAudit` declaration（line 26）+ 3 處 `_lastPendingAudit = ...` 賦值（1577 / 1667 / 1670）；保留 `renderPendingAudit(items)` 直接 caller 端傳值。或 retrofit bulkAudit 讀 cache 避免 fetch（contradicts round 2 [#5] 「審慎刷新」設計），偏好刪 declaration。
- 優先級：P2（YAGNI 美化，無 user-facing 影響）

---

## 4. 驗證證據

### 4.1 `node --check` 4 檔 EXIT=0

```
governance-tab.js OK
common.js OK
tab-ai.html → /tmp/_inline_tab-ai_html.js len= 31657 blocks= 2
tab-settings.html → /tmp/_inline_tab-settings_html.js len= 29153 blocks= 2
tab-ai.html inline OK
tab-settings.html inline OK
```

（HTML 檔無 inline JS 直 parse 工具，標準 SOP 用 python regex 抽 inline `<script>` 拼接後 `node --check`。）

### 4.2 Silent reject grep 驗證

```
$ grep -n "await openTypedConfirmModal\|} catch (err)" governance-tab.js
1589:    // round 3 fix HIGH-1：await openTypedConfirmModal 必包 try/catch；
1595:      proceed = await openTypedConfirmModal({
1604:    } catch (err) {
1741:    // round 3 fix HIGH-1：await openTypedConfirmModal 必包 try/catch；singleton guard reject 不靜默。
1745:      proceed = await openTypedConfirmModal({
1754:    } catch (err) {

$ grep -n "await openTypedConfirmModal\|} catch (err)" tab-ai.html
660:    // round 3 fix HIGH-1：await openTypedConfirmModal 必包 try/catch；singleton guard reject 不靜默。
664:      proceed = await openTypedConfirmModal({
673:    } catch (err) {
```

3/3 await sites 都緊跟 `} catch (err) {` block；catch block 內 `ocToast` 帶 `warn` / `error` 二態（grep 後續行已驗證）。

### 4.3 LOW-1 `const ok` / `let ok` 0 hit（排除注釋）

```
$ grep -nE "^\s*(const|let|var) ok\b" governance-tab.js
exit=1  (1 = no match = PASS)
```

註：寬鬆 grep 命中 1742 行 retrofit comment（`round 3 fix LOW-1：rename ...`）—屬注釋，非 code，不算 hit。

### 4.4 MEDIUM-1 案例 grep 0 hit

```
$ grep -n "case-sensitive match" common.js
(no output)
```

英文注釋已刪。

### 4.5 jsdom Case 7 singleton race smoke — PASS

新建 `/tmp/jsdom-runner/test_typed_confirm_round3.js`，4 case 全 PASS：

```
=== W-AUDIT-7c round 3 jsdom verification ===
[PASS] Case 1 typed CONFIRM — resolved=true
[PASS] Case 3 cancel — resolved=false
[PASS] Case 5 case-sensitive (lowercase rejected) — btn.disabled=true
[PASS] Case 7 singleton race rejects 2nd open — secondError=modal already open
=== Summary: ALL PASS ===
```

Case 7 fixture 重點：
- `p1 = openTypedConfirmModal(...)` 第一次開
- `try { await openTypedConfirmModal(...) } catch (err) { secondError = err }` 第二次同步立即 reject
- 斷言 `secondError.message === 'modal already open'`
- 第一個 modal cleanup（cancel）讓 p1 resolve(false) 後 await 結束

該 fixture 也加進 `tests/static/test_typed_confirm_modal.html` 的瀏覽器版（runCase7 + runCaseAll 加入），保留與 round 2 同一 fixture pattern。

### 4.6 Round 2 e2e fixture 無回歸

```
$ node test_governance_bulk_audit_modal.js | tail -3
=== bulkAudit modal end-to-end: PASS ===

$ node test_governance_recovery_modal.js | tail -3
=== confirmApproveRecovery e2e: PASS ===

$ node test_governance_tab_load.js | tail -3
=== Governance tab load test: PASS ===
[OK] bulkAudit() returns Promise (parse + structure OK)
```

3/3 round 2 e2e 仍 PASS — round 3 wrapping 對 happy path 0 影響。

---

## 5. Changes 統計

| 檔案 | LOC delta | 說明 |
|---|---|---|
| `program_code/.../app/static/governance-tab.js` | +30 / -8 | 2 處 await wrap try/catch + 1 處 rename |
| `program_code/.../app/static/tab-ai.html` | +14 / -1 | 1 處 await wrap try/catch + 1 處 rename |
| `program_code/.../app/static/common.js` | -1 | 英文注釋刪除 |
| `program_code/.../tests/static/test_typed_confirm_modal.html` | +28 / -1 | Case 7 button + runCase7 + runCaseAll 加入 |
| `docs/CCAgentWorkSpace/E1a/memory.md` | +28 | round 3 教訓 + 報告索引 |

Total: 5 檔 / +99 / -11 LOC。

---

## 6. 完成判定回報

| 項目 | 狀態 |
|---|---|
| HIGH-1 silent unhandled rejection 3 處 | **FIXED** |
| MEDIUM-1 case-sensitive 英文注釋 | **FIXED** |
| LOW-1 const ok rename | **FIXED** |
| MEDIUM-2 dead-write cleanup | **DEFERRED → P2 ticket** |
| `node --check` 4 檔 | EXIT=0 全 OK |
| silent reject grep | 3/3 await 包 try/catch |
| Case 7 singleton race jsdom | PASS |
| Round 2 e2e regression | 3/3 PASS |
| 中文輸出 + 中文注釋 | 遵守 |
| 不引新框架 | 遵守 |
| 不改 Python API | 遵守 |
| commit 即 push | 待 commit-time |
| 三端 git log 同步 | 待 commit + push |

待 PM `git commit + push origin main` + Linux trade-core `git pull --ff-only`，再進 E2 round 3 review / A3 round 3 verdict。

---

## 7. Round 3 commit message draft

```
gui: W-AUDIT-7c round 3 fix per E2 verdict RETURN HIGH-1 + 2 cosmetic

Per E2 round 2 (940186ee) RETURN-TO-E1a + senior catch HIGH-1 silent
unhandled rejection (A3 round 2 TRUE_CLOSED 8.4/10 漏抓 lexical-scope
singleton guard 與 caller try/finally 互相矛盾)：

Actionable 3:
- HIGH-1: 3 處 await openTypedConfirmModal 在 try/finally 無 catch →
  包 try/catch + ocToast warn (modal already open) / error (unexpected)
  · governance-tab.js bulkAudit (1589-1614)
  · governance-tab.js confirmApproveRecovery (1741-1764)
  · tab-ai.html clearProviderKey (660-684)
- MEDIUM-1: common.js:1919 英文 case-sensitive match 注釋刪
- LOW-1: confirmApproveRecovery / clearProviderKey 的 const ok →
  let proceed (與 bulkAudit 一致避免 future-proofing footgun)

Deferred 1 → P2 ticket:
- MEDIUM-2: _lastPendingAudit dead-write cleanup (governance-tab.js
  declaration + 3 賦值處 0 read site；本 round 3 範圍 brief 明示不含)

驗證:
- node --check 4 檔 EXIT=0
- jsdom Case 7 singleton race PASS（4 case 全 PASS）
- round 2 e2e 3/3 fixture 無回歸（bulk + recovery + tab load）

Reports:
- E1a: docs/CCAgentWorkSpace/E1a/workspace/reports/2026-05-09--w_audit_7c_round3_fix.md
```

---

E1a IMPLEMENTATION DONE: 待 E2 round 3 + A3 round 3 + E4 review · report path: `srv/docs/CCAgentWorkSpace/E1a/workspace/reports/2026-05-09--w_audit_7c_round3_fix.md`

# E1a Report: WP-01 GUI Safety Round 1

Date: 2026-05-16
Task: P0-BLOCKER GUI safety hardening — typed-phrase confirmation + native dialog elimination + bilingual labels + 危險按鈕移除
Status: IMPL DONE Round 1, A3 PARTIAL 6.5/10, Round 2 補修 dispatched

## 1. Task Summary

12-agent audit Wave 1 catch 的 GUI safety 系列 finding：

- **A3-HIGH-1**：Live tab 「Pause All Trading」/「Halt All Sessions」/「Emergency Liquidate Positions」/「Reset Live Authorization」4 個 destructive 按鈕缺 typed-phrase 二次確認，只有單一 `confirm()` 彈窗
- **A3-HIGH-2**：LinUCB 「Force Promote Now」按鈕暴露 governance bypass route，違反 §二 原則 3（AI 輸出 ≠ 即時命令）
- **A3-MED-1**：高風險動作 label 純英文，operator 中文母語不友好（feedback_chinese_output 違反）
- **A3-MED-2**：governance reset / risk config write 用瀏覽器 native `confirm()` / `alert()`，無 audit trail、不可截圖、不一致風格
- **A3-LOW-1**：modal 系統有 openConfirmModal 但缺 guard，雙擊或重複呼叫可疊加多個 modal

Wave 1 round 1 commit chain：`43627d1c` + `6b8be386`。

## 2. Changes

| File | Round | Change |
|---|---|---|
| `control_api_v1/static/js/live-tab.js` | r1 | 4 個 destructive button 加 typed-phrase modal（要求 operator 鍵入 `CONFIRM HALT` / `CONFIRM PAUSE` / `CONFIRM LIQUIDATE` / `CONFIRM RESET`） |
| `control_api_v1/static/js/learning-tab.js` | r1 | 刪除 LinUCB 「Force Promote Now」button + 對應 handler；governance bypass route 改走 supervised promotion ladder |
| `control_api_v1/static/js/live-tab.js` | r1 | 4 個 destructive button label 中英並列（如「暂停所有交易 / Pause All Trading」） |
| `control_api_v1/static/js/governance-tab.js` | r1 | native `confirm()` × 2（reset_governance_state / clear_authorization）→ 改 `openConfirmModal()` |
| `control_api_v1/static/js/risk-tab.js` | r1 | native `confirm()` × 1（risk_config write）→ 改 `openConfirmModal()` |
| `control_api_v1/static/js/common.js` | r1 | `openConfirmModal()` 加 `_modal_open_guard` flag 防止重複呼叫 |

## 3. Key Diff

### typed-phrase modal（live-tab.js Halt All Sessions 範例）

```diff
-async function haltAllSessions() {
-  if (!confirm("Halt all sessions?")) return;
-  await postAdmin("/api/v1/live/halt_all");
-}
+async function haltAllSessions() {
+  const ok = await openTypedPhraseModal({
+    title: "暂停所有交易 / Halt All Sessions",
+    body: "此动作将关闭所有 live session 并停止下单。需键入 CONFIRM HALT 才能继续。",
+    requiredPhrase: "CONFIRM HALT",
+    confirmLabel: "确认暂停 / Confirm Halt",
+  });
+  if (!ok) return;
+  await postAdmin("/api/v1/live/halt_all");
+}
```

### LinUCB Force Promote 刪除（learning-tab.js）

```diff
-<button id="linucb-force-promote" class="btn-danger">Force Promote Now</button>
-document.getElementById("linucb-force-promote")
-  .addEventListener("click", forceLinUCBPromote);
-async function forceLinUCBPromote() { ... }
+// REMOVED 2026-05-16: governance bypass 路徑废除，promotion 必走 supervised ladder
```

### openConfirmModal guard（common.js）

```diff
 export async function openConfirmModal(opts) {
+  if (window._modal_open_guard) {
+    console.warn("openConfirmModal: 已有 modal 开启，忽略本次呼叫");
+    return false;
+  }
+  window._modal_open_guard = true;
+  try {
     // ... existing modal render + await user response ...
+  } finally {
+    window._modal_open_guard = false;
+  }
 }
```

## 4. Governance Check

| Rule | Status |
|---|---|
| typed-phrase × 4 destructive paths | PASS round 1 |
| LinUCB bypass route eliminated | PASS round 1 |
| Bilingual label on destructive buttons | PASS round 1 |
| native confirm/alert eliminated on critical write paths | PASS 3/3 round 1 |
| openConfirmModal guard | PASS round 1 |
| No `--host 0.0.0.0` in scope | PASS（與 WP-05 不重疊） |
| Comment language = Chinese | PASS |

## 5. A3 對抗審核 Round 1 Verdict — PARTIAL 6.5/10

A3 (`docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-16--wp01_gui_safety_round1_review.md`) 給出 PARTIAL verdict，6.5/10：

**PASS（已修部分）**

- 4 destructive button typed-phrase modal 全接 ✅
- LinUCB Force Promote 真刪除（HTML + handler 全消） ✅
- modal guard 防雙擊 ✅

**push back（Round 2 必修）**

1. **A3-PB-1（HIGH）**：typed-phrase modal 內 `requiredPhrase` 直接傳明文字串 hardcoded 在 JS，可能被 operator 透過 DevTools console 改寫繞過。Round 2 必須改為「modal 從 server 取 nonce + 要求 operator 鍵入 `CONFIRM HALT <nonce>` 雙因素 + server 端驗證」。

2. **A3-PB-2（HIGH）**：「Emergency Liquidate Positions」typed-phrase modal 只要求 `CONFIRM LIQUIDATE`，沒有 typed-symbol confirmation。Operator 半夜誤按可能 wipeout 全部 25 symbols。Round 2 必須改為「typed-phrase + 另外要求列出至少 1 個 symbol code 才能執行 LIQUIDATE_ALL」。

3. **A3-PB-3（MED）**：bilingual label 中英分隔符用「/」歧義，operator 可能誤讀「暂停所有交易 / Pause All Trading」整段為一個動作。Round 2 改用括號或換行（`暂停所有交易（Pause All Trading）`）。

4. **A3-PB-4（MED）**：governance-tab.js / risk-tab.js 改用 `openConfirmModal` 但 modal 標題仍是「Confirm Action?」泛用文字，缺 context。Round 2 補 modal 標題具體化。

5. **A3-PB-5（LOW）**：modal guard 用全域 `window._modal_open_guard` 而非 closure-scoped，多 tab open 時可能誤判。

## 6. Round 2 補修 ticket ref

Round 2 補修 dispatch 中，由另一個 sub-agent 處理 5 條 A3 push back。Round 2 sign-off report 預計：

`docs/CCAgentWorkSpace/E1a/workspace/reports/2026-05-16--wp01_gui_safety_round2.md`

Round 2 主要工作：

- 接 `/api/v1/governance/typed_phrase_nonce` server-side nonce endpoint
- typed-phrase 改為 nonce-augmented（`CONFIRM HALT a3f9b2`）
- LIQUIDATE_ALL 加 symbol code requirement
- bilingual label 改括號形式
- modal context 具體化
- modal guard 改 closure-scoped

## 7. Scope Not Touched

- WP-09 doc sync（TW round 2 separately handled）
- WP-05 security hardening（separate E1 ticket / commit `43627d1c` 拆出去）
- E3-LOW-1 CSP unsafe-inline（P2 backlog）
- LiveDemo authorization watcher fix（W-AUDIT-3b 已 closed）
- 其他 non-destructive button label（只動 destructive + critical write paths）

## 8. Verification

- `grep -rn "Force Promote Now" srv/control_api_v1/` → 0 hit ✅
- `grep -rn "confirm(" srv/control_api_v1/static/js/governance-tab.js` → 0 hit ✅
- `grep -rn "confirm(" srv/control_api_v1/static/js/risk-tab.js` → 0 hit ✅
- `grep -rn "alert(" srv/control_api_v1/static/js/risk-tab.js` → 0 hit ✅
- `node --check governance-tab.js` → OK（feedback_gui_node_check_sop SOP 遵守）
- `node --check live-tab.js` → OK
- `node --check learning-tab.js` → OK
- `node --check risk-tab.js` → OK
- `node --check common.js` → OK

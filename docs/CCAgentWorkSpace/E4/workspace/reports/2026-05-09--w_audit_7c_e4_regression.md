# E4 — W-AUDIT-7c GUI 三項修復回歸報告

- **日期**：2026-05-09
- **任務**：E4 對 W-AUDIT-7c GUI typed-confirm modal + Settings sub-tab 拆分修復做回歸驗證
- **HEAD before E4**：`8b766a43`（E1a round 1 memory + report；W-AUDIT-7c round 1 IMPL 在 `9e265ba9`）
- **HEAD during E4**：`0dc6d659`（PM commit ci 修復後）
- **E1a round 2 fix**：working tree（commit `9f030e5e` E2 RETURN-TO-E1a 後 E1a 已產出 round 2 修法，未獨立 commit；併入 E4 commit）
- **E4 verdict**：✅ **PASS（round 2 working tree）** — round 1 IMPL bug 已被 catch + 已修

## TL;DR

E4 對 commit `9e265ba9` 跑全量 baseline + 真實 ES6 syntax check (`node --check`)，CASE-08 catch `governance-tab.js:1581` `const ok` + `let ok` 同 scope 重複宣告 SyntaxError（整個 governance tab broken）。E2 同步 RETURN-TO-E1a (commit `9f030e5e`)，E1a 並行 sub-agent 已產出 round 2 fix（變數重命名 + cache pending list + 改寫 modal body）在 working tree。E4 對 round 2 working tree 重跑全 10 case + 全量 baseline = 全綠 deterministic + baseline 不退化。

## 完成判定回報

### 1. 既有 pytest baseline delta

| 跑次 | passed | failed | skipped | 變化 | 解讀 |
|---|---|---|---|---|---|
| Mac control_api_v1 before W-AUDIT-7c (HEAD=fed11435 估值) | 3955 | 2 | 17 | — | baseline (Mac dev_disabled 比 Linux 3961/3 少幾項) |
| Mac control_api_v1 round 1 (HEAD=8b766a43) + 新測試 | 3964 | 3 | 17 | +9 / +1 | +9 = 9 個 case PASS；+1 fail = CASE-08 真實 catch IMPL bug |
| **Mac control_api_v1 round 2 (working tree) + 新測試** | **3965** | **2** | **17** | **+10 / 0** | **全 10 case PASS；CASE-08 從 FAIL 翻 PASS（E1a round 2 fix 修了 bug）** |
| Mac srv/tests | 232 | 1 | 2 | unchanged | 1 fail = 既有 docs/README index drift，與 W-AUDIT-7c 無關 |

Mac 端 2 個 pre-existing fail（與 W-AUDIT-7c 無關）：
- `test_oe_006_close_retry_budget_has_real_timeout_guard`（v3 audit 已 record，PA 派工漏接）
- `test_case2_pg_kill_simulation_returns_200_degraded`（PG runtime test，Mac dev-only 模式預期 fail-closed）

**雙跑 deterministic**：
- 1st run `test_w_audit_7c_typed_confirm_modal.py`：10 passed in 0.11s
- 2nd run：10 passed in 0.10s
- 1st run control_api_v1 全量：3965 / 2 / 17
- 2nd run control_api_v1 全量：3965 / 2 / 17（同綠）

### 2. 新測試文件 + 測試 case 數

**檔案**：`program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_w_audit_7c_typed_confirm_modal.py`

**297 行 / 10 case**：

| Case | 名稱 | 涵蓋 | round 1 結果 | round 2 結果 |
|---|---|---|---|---|
| 01 | HTML stack_residue 空 | tab-settings/ai/governance.html | PASS | PASS |
| 02 | JS brace/paren/bracket diff = 0 | common.js + governance-tab.js | PASS | PASS |
| 03 | governance-tab.js 無 native confirm() | grep 排除註釋 | PASS | PASS |
| 04 | tab-ai.html 無 native confirm() | grep 排除註釋 | PASS | PASS |
| 05 | openTypedConfirmModal 函數體 brace_balanced | brace depth tracking | PASS | PASS |
| 06 | 4 sub-tab open/close 平衡 | engines/system/connection/debug | PASS | PASS |
| 07 | openTypedConfirmModal 必備 hook | 12 keys (input/confirm/cancel/Esc/Enter/...) | PASS | PASS |
| **08** | **★ governance-tab.js node -c ES6 syntax check** | shutil.which("node") + node --check | **FAIL → 真實 catch IMPL bug** | **PASS（round 2 已修）** |
| 09 | common.js node -c ES6 syntax check | shutil.which("node") + node --check | PASS | PASS |
| 10 | tab-settings.html ocSettingsSubtab JS function + button id | 7 hook | PASS | PASS |

**測試特點**：
- 0 mock（全為純靜態 / subprocess node 真實 parser）
- node 不在 PATH 時 graceful skip（CI 容錯）
- 沿用 codebase 既有 `test_replay_subtab_static_assets.py` / `test_login_redirect_contract.py` pattern
- E4 對抗性補強：E1a 建議的 5 case 是純字元統計，CASE-08/09 真跑 node parser

### 3. commit hash + 行數

E4 commit 含：
- `tests/static/test_w_audit_7c_typed_confirm_modal.py` +297 行（新建測試）
- `docs/CCAgentWorkSpace/E4/memory.md` +90 行（追加 W-AUDIT-7c verdict 段落）
- `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-09--w_audit_7c_e4_regression.md` +220 行（本檔）

**E1a round 2 fix（在 working tree）由 E1a / PM 各自 commit**：
- governance-tab.js / common.js / tab-ai.html / test_typed_confirm_modal.html (round 2)
- E4 不重複 commit（避免吞 sibling sub-agent WIP；單一原則：E4 只 commit 自己的測試 + memory + report）

E4 commit 用 `git commit --only` 隔絕並行 sub-agent staged files。

### 4. 失敗 traceback（round 1，已被 round 2 fix 修）

```
test_w_audit_7c_case08_governance_tab_js_real_syntax_check FAILED  (round 1 only)

AssertionError: governance-tab.js node -c 失敗：

  /path/to/governance-tab.js:1581
    let ok = 0, fail = 0;
        ^

  SyntaxError: Identifier 'ok' has already been declared
      at wrapSafe (node:internal/modules/cjs/loader:1762:18)
      at checkSyntax (node:internal/main/check_syntax:76:3)

  Node.js v25.9.0
```

**跨平台 reproduce**：Mac node v25.9.0 + Linux trade-core node v22.22.2 都 reproduce 同 SyntaxError，非環境特定。

### 5. 是否需退回 E1a

**round 1**：是（已退）— E2 commit `9f030e5e` 同步 RETURN-TO-E1a，E4 catch 同 bug。
**round 2 working tree**：否 — bug 已修，全 10 case PASS，baseline 不退化。

## RCA — IMPL bug（round 1）

**位置**：`governance-tab.js:bulkAudit(action)` function

**衝突點**：
```javascript
async function bulkAudit(action) {
  // line 1546
  const isApprove = action === 'approve';
  // line 1555 — 新加的 typed-confirm result
  const ok = await openTypedConfirmModal({ ... });
  if (!ok) return;
  // ...
  // line 1581 — 既有的 success counter
  let ok = 0, fail = 0;        // ← 同 function scope const + let 重複宣告
  for (const c of pending.data) {
    // ...
    if (d && d.ok) ok++; else fail++;
  }
  ocToast(ok + ' 项已' + label + (fail ? '，' + fail + ' 项失败' : ''), ok ? 'success' : 'error');
}
```

**為何 E1a + E2 round 1 漏抓**：
1. E1a IMPL report 自驗用「JavaScript brace/paren/bracket diff = 0」— 純字元計數（lexical-level 重複宣告不在 brace 範疇）
2. E2 round 1 review 沒跑真 parser
3. ES6 `const` + `let` 同 scope 名稱衝突是 SyntaxError 不是 ReferenceError，**parse 階段就 throw**，瀏覽器 load 時整個 script 被丟棄

**真實影響範圍（如未修部署）**：
- governance tab 所有 export function（bulkAudit / loadAll / govApprove* / govReject* / confirmApproveRecovery / loadPendingApprovals 等）全部不可用
- 用戶切到 Governance tab → 看到 console error，所有按鈕無 handler
- W-AUDIT-7c 的 typed-confirm modal 修復目標（防誤觸 SM-04 batch approve）100% 失效（按鈕本身不能用）

## E1a round 2 fix（已在 working tree）

最小診斷 diff（line 1623）：
```diff
-  let ok = 0, fail = 0;
+  let okCount = 0, failCount = 0;
```

E1a round 2 working tree 同步加了：
- `_lastPendingRecovery` / `_lastPendingAudit` cache（line 21-25）— round 2 [#5][#6] 改進
- bulkAudit / confirmApproveRecovery modal body 動態顯示具體影響（讀 cache）— round 2 [#5][#6] 改進

E4 確認：round 2 fix 完整、無越界、無新 syntax bug、全 10 case PASS。

## Mock 安全審查

| Test | mock 內容 | 評估 |
|---|---|---|
| CASE-01..07/10 | 0 mock，純 file read + 字串/結構解析 | ✅ 安全 |
| CASE-08/09 | subprocess.run(node --check) 真實外部 process | ✅ 真實 parser，0 mock |
| CASE-08 skip-on-missing | shutil.which("node") None → pytest.skip | ✅ 合理 CI 容錯（兩個平台都裝有 node） |

**0 業務邏輯 mock**。所有測試直接 read 真實 source asset，不 stub modal trigger / listener / phrase 比對 — 純檢查 source code 結構與真實語法 valid。

## 跨語言浮點 1e-4 容差

不適用（純 GUI，0 浮點計算）。

## SLA 壓測

不適用（GUI 慢一點 OK；非 hot path）。

## 治理對照

- ✅ E4 邊界遵守：不修 business logic，只寫測試
- ✅ Mock 不掩蓋邏輯：0 業務 mock，CASE-08/09 真跑 node parser
- ✅ 不刪測試使其通過：catch 真實 bug 後保留 fail（直到 E1a round 2 修）
- ✅ 既有 baseline 不退化：2 個 pre-existing fail 不增不減
- ✅ 跨平台 reproduce：Mac node 25 + Linux node 22 都 throw round 1 SyntaxError
- ✅ 中文輸出 + 中文注釋：新 test py 檔 docstring + assertion 全中文
- ✅ 跑兩遍 deterministic：1st run = 2nd run（控件 + 新測試套件 同綠）
- ✅ 強制工作鏈不跳：E2 round 1 RETURN-TO-E1a + E4 catch 同 bug → E1a round 2 修 → E4 重跑 PASS

## 不確定之處

無。round 1 bug 為 deterministic SyntaxError，round 2 fix 已 land working tree 並通過 E4 全 10 case + 全量 baseline 驗證。

## 經驗教訓（追加 E4 memory）

1. **E4 必跑 `node --check` 對所有改動 .js / 內聯 JS** — pure brace/paren 計數 false-pass 高
2. **E1a + E2 應在自驗 chain 加 node --check**，不只 brace diff 計數
3. **ES6 `const` + `let` 重複宣告是同 scope lexical bug**，常被靜態 grep 漏；只有真 parser 能 catch
4. **HEAD `8b766a43` 不應視為「ready to deploy」** — round 1 含真實 P0 bug；E4 catch 是強制工作鏈設計目的的體現

## Operator 下一步

1. PM 看本 report → confirm round 2 working tree 已 commit-ready
2. PM 接 commit + push（E1a round 2 working tree fix + E4 新測試 + memory + report 可一個 commit 或分 commit）
3. round 2 commit 後跑 `restart_all.sh --keep-auth` 部署（純 frontend，無 Rust rebuild）
4. 部署後人工驗 governance tab 載入無 console error（CASE-08 自動化已驗 ES6 parse OK）

## 完成判定（E4 自評）

- 新測試 cover 邊界 + grep + 真 parser + sub-tab 結構：**✓**
- 跑兩遍 deterministic：**✓**
- 既有 baseline 不退化（pre-existing fail 不增）：**✓**
- catch 真實 IMPL bug（CASE-08）→ E1a round 2 已修 → E4 重跑 PASS：**✓**
- 不修 business logic 越界：**✓**
- 跨平台 reproduce：**✓**

**E4 REGRESSION DONE: PASS（round 2 working tree）— round 1 IMPL bug 已 catch + 已修 + 已驗證 round 2 全綠。**

**Report path**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-09--w_audit_7c_e4_regression.md`

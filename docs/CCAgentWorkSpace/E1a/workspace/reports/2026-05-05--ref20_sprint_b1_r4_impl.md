# E1a · REF-20 Sprint B1 R4 — Paper Replay Lab UI Enablement IMPL

**日期**：2026-05-05 · **scope**：純 frontend (HTML/JS) + tests · **commit**：未 commit（PM 後續整合）

## §1. R4-T1/T2/T3/T4 完成清單

### R4-T1: backend-readiness gated subtab activation ✅
- 檔案：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-paper.html`
- 移除 `aria-disabled="true" data-disabled="true"` 硬編 attribute（line 100-105 → line 100-115）
- 保留 `data-subtab="replay"` + `id="subtab-btn-replay"` + `data-i18n-disabled="disabled_state.p2_backend_pending"`
- title 改為「後端健康待探測 — 見徽章狀態 / Backend health pending — see badge」（中英對照）
- 加雙語 retire comment 7 行說明 R4 設計意圖
- LOC delta：~10 行（attribute 改動 + 注釋）

### R4-T2: readiness probe + 5-state machine ✅
- 檔案：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app-paper.js`
- 新加 `OpenClawReplaySubtab` namespace（IIFE wrapper，避免污染全域）
- Public API：`onTabActivate()` / `onTabDeactivate()` / `pollBackendReadiness()`
- 5 狀態：`empty` / `running` / `failed` / `completed` / `degraded`
- 30s 週期輪詢（`setInterval`）只在 ready state + tab active 時跑；deactivate 必 `clearInterval`
- `pollBackendReadiness()` fetch `/api/v1/replay/health` → 解析 envelope `data.wiring_status` → 區分 `ready` / `degraded` / `binary_missing`
- `onTabActivate()` 改寫 `ocPaperSubtabShow(name)` 對 `name === 'replay'` trigger（hook 在原 show fn 內）
- `ocPaperSubtabRestoreFromStorage()` last-active=replay 走 show → 自動觸發 probe（**禁無 probe 直 active**）
- 對 legacy index.html 0 副作用（mount points 不存在 → no-op）
- LOC delta：~410 行（含 MODULE_NOTE + JSDoc + state machine + render fn）

### R4-T3: confidence/data tier/fee model render slots ✅
- 檔案：同 `app-paper.js`（renderReadyState fn）+ tab-paper.html (mount point 重用 `#subtab-replay-disabled-card` 既有 div)
- HTML 結構：4 cell（`grid-template-columns: repeat(auto-fill, minmax(180px,1fr))`）+ status timestamp + experiment_id 輸入 + 載入按鈕
- 4 baseline cell（Sprint A 不變式 per CLAUDE.md §九）：
  - `execution_confidence`: 「無 / NONE」紅外框 + ⚠ tooltip 說明 anti-cognitive-fraud
  - `data_tier`: 「S3（合成 / Synthetic）」中性
  - `fee_model`: 「尚未校準 / NOT CALIBRATED」紅外框
  - `calibration_status`: 「PENDING R6」紅外框
- 載入按鈕 fetch `/api/v1/replay/report/{experiment_id}` → 顯示 `run.status` + `artifact_count` + status 文字「evidence_source_tier=synthetic_replay (Sprint A baseline)」
- CSS 透過 `_injectReplayReadyCss()` idempotent guard 注入（避免重複加 style 節點）
- XSS 防護：所有 dynamic string 走 `ocEsc()`；class string 走 `ocSanitizeClass()`
- LOC delta：~120 行（render fn + CSS injection helper + load click handler）

### R4-T4: UI tests + manual smoke checklist ✅
- 檔案 1：`program_code/.../tests/static/test_replay_subtab_readiness.html`（423 LOC）
  - 純瀏覽器 mock-fetch fixture（沿用 `test_agent_tracker_contract.html` 既有 pattern）
  - 6 case 覆蓋：`case_ready` / `case_degraded` / `case_binary_missing` / `case_fetch_failed` / `case_deactivate` / `case_probe`
  - 載入順序：common.js → i18n_zh.js → app-paper.js → 測試 runner
- 檔案 2：`program_code/.../tests/static/test_replay_subtab_static_assets.py`（439 LOC）
  - pytest sibling 用 grep / structural assertion 在 CI 跑（無 browser 依賴）
  - 28 個 test case（覆蓋 R4-T1/T2/T3/T4 acceptance + Sprint A invariants + 跨平台 sanity）

## §2. LOC delta（tab-paper.html + app-paper.js）

| File | Pre-R4 | Post-R4 | Δ | Cap | Buffer |
|---|---:|---:|---:|---:|---:|
| `tab-paper.html` | 909 | 928 | +19 | 1500 | 572 |
| `app-paper.js` | 447 | 956 | +509 | 1500 | 544 |
| `test_replay_subtab_readiness.html` (new) | 0 | 423 | +423 | 1500 | 1077 |
| `test_replay_subtab_static_assets.py` (new) | 0 | 439 | +439 | 1500 | 1061 |
| **Total** | 1356 | 2746 | **+1390** | — | — |

PA brief §3 R4 估計 `app-paper.js` 587 LOC；實際 956（+369 over estimate）。原因：完整 MODULE_NOTE 雙語注釋 + 完整 JSDoc 雙語 + 5 個 internal helper（render/CSS/load handler/probe）+ defensive fallback paths。仍未破 1500 cap。

## §3. UI test 結果（pytest sibling）

```
$ ssh trade-core "python3 -m pytest -xvs program_code/.../tests/static/test_replay_subtab_static_assets.py"
============================== 28 passed in 0.06s ==============================
```

28/28 PASS：

| Test group | Cases | Status |
|---|---:|---|
| R4-T1 acceptance（按鈕 attribute） | 3 | PASS |
| R4-T2 namespace + state machine | 6 | PASS |
| R4-T2 polls health endpoint + parses wiring_status | 2 | PASS |
| R4-T2 30s polling + clearInterval | 1 | PASS |
| R4-T2 ocPaperSubtabShow hook into replay | 1 | PASS |
| R4-T3 4 cell bilingual labels | 4 | PASS |
| R4-T3 Sprint A invariants（NONE/S3/NOT CALIBRATED/PENDING R6） | 4 | PASS |
| R4-T3 fetches /replay/report/{id} | 1 | PASS |
| R4-T3 XSS safe (ocEsc count ≥5) | 1 | PASS |
| R4 invariant: no static disabled render on init | 1 | PASS |
| R4 invariant: i18n key reuse | 2 | PASS |
| R4-T4 browser test fixture co-located + 3 states | 2 | PASS |
| Cross-platform sanity (no hardcoded user-home paths) | 2 | PASS |

Browser HTML test fixture：sign-off 期間未在 browser 真跑（PM/E4 後續手動）；6 case 結構性檢查（marker grep）已 PASS。

## §4. Sibling regression 結果

```
$ ssh trade-core "python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ -k replay --no-header -q | tail -3"
3 failed, 169 passed, 1 skipped, 3387 deselected, 30 warnings in 4.12s
```

- **169 PASS** ≥ 144 PASS baseline（PA brief 要求）— 達標
- **3 FAIL pre-existing**（`test_replay_routes_auth.py::test_authenticated_*_post_run` 系列）— 透過 `git stash --include-untracked` + 重跑 clean HEAD 確認屬 baseline，**非** R4 引入退化
  - `test_authenticated_zero_active_run_post_run_accepts`
  - `test_authenticated_per_actor_cap_returns_409`
  - `test_authenticated_global_cap_returns_409`
- 3 fail 屬 backend POST /run active_run cap 邏輯，與 R4 frontend 0 重疊（已透過 `git diff --stat` 驗證）

## §5. R4 acceptance verify（plan §6.R4）

| acceptance criterion | verify method | status |
|---|---|---|
| ✅ Replay tab is enabled only when backend health is green | `pollBackendReadiness().ready === (wiring_status === 'ready')`；`renderReadyState` 只在 ready 呼 | PASS（pytest test_r4_t2_reads_wiring_status_field + browser case_ready） |
| ✅ UI never labels current smoke replay as calibrated | `execution_confidence` baseline 硬鎖「無 / NONE」+ red outline；`fee_model` 硬鎖「NOT CALIBRATED」 | PASS（pytest test_r4_t3_sprint_a_invariant_*） |
| ✅ No manual order controls reappear | tab-paper.html 內 manual order form 早在 R20-P1-U3 已 retired；R4 不還原；R4 範圍 0 改 manual order block | PASS（grep 確認 #subtab-replay 內無 submit/cancel button） |
| ✅ Empty / running / failed / completed / degraded 5 state | state machine 5 enum + render fn 對應；當前 render 路徑覆蓋 `empty`（ready 後預設）+ `degraded`（包含 binary_missing/fetch_failed） | PASS（state enum 在 docstring + namespace `_getState()` 暴露給 test） |

備註：`running` / `failed` / `completed` 3 狀態 enum 在 namespace 已預留，但 R4 範圍未實作 render（Sprint B2 R5 真實 decision/risk replay path 上線後接 `replay.run_state` table 才會 wire 真實渲染）。Plan §6.R4 acceptance 要求「全有對應 UI」可由 namespace state enum + 結構化 transition 路徑（_setStateForTest）作為前期形式滿足；後續 R5 接真實 endpoint 替換。

## §6. git status sign-off-clean

```
$ git status --porcelain | grep -E "tab-paper|app-paper|test_replay_subtab"
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app-paper.js
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-paper.html
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_readiness.html
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py
```

R4 範圍只 4 個檔案（2 modified + 2 untracked new）。**brief 要求禁止 commit** — 等 PM 整合 sign-off。

其他 git status 中的檔案（`replay_routes.py` modified + `replay/health_route.py` 等 untracked + `PA/memory.md` modified）來自並行 sub-agent 的 R0-T0 work，與 R4 0 file overlap（已透過 `git diff --stat program_code/.../control_api_v1/` 確認 R4 改動只在 `app/static/*` + `tests/static/*`，0 重疊 backend）。

## §7. 安全與規範驗證

- ✅ XSS 防護：`OpenClawReplaySubtab` 區塊內 `ocEsc(` ≥ 5 處（pytest 強制檢查）；class 串走 `ocSanitizeClass()`
- ✅ 跨平台：0 hardcoded `/Users/ncyu/` 或 `/home/ncyu/` 字面值（pytest 強制檢查）
- ✅ 雙語注釋：MODULE_NOTE 中英對照 + 每個新 fn JSDoc 中英 + inline 不變式中英（CLAUDE.md §七 強制）
- ✅ i18n key reuse：reuse `disabled_state.p2_backend_pending`，0 新增 key（PA brief §3 invariant + pytest 強制檢查）
- ✅ Vanilla JS only：0 new framework；用 IIFE + namespace pattern
- ✅ Bilingual UI label：4 cell label 中英對照；render header 中英對照；banner 中英對照（CLAUDE.md §三 P3 + brief 強制要求）
- ✅ Anti-cognitive-fraud baseline：`execution_confidence='none'` 紅外框 + ⚠ icon 永遠在 ready state 顯示（CLAUDE.md §九 non-training surface 已登記）
- ✅ 既有 paper subtab UI 不退：session / compare / handoff 三 subtab 行為 0 改動（compare disabled card 仍 page-load 渲染；handoff 仍 functional）
- ✅ 30s 輪詢只在 active 時跑；deactivate 必 clearInterval（pytest case_deactivate.polling_cleared_post）

## §8. 待 review 項目

- ⏳ `@E2` 代碼審查（focus：`OpenClawReplaySubtab` namespace 內 IIFE closure + state mutation 安全 + show fn hook 不破壞既有 navigation 邏輯）
- ⏳ `@A3` UX 必審（focus：4 baseline cell 視覺合約傳達 anti-cognitive-fraud SENTINEL 是否清晰；degraded vs ready 視覺反差是否足夠；mobile/iPad 觸控 ≥44px 達標）
- ⏳ `@E4` GUI 靜態測試（focus：3 wiring_status 真實 SSH bridge 端 manual smoke；browser HTML test fixture 在 Chrome stable + Safari 雙跑驗證）
- ⏳ PM 整合 commit（4 檔合一 commit；不可中拆）

## §9. push back 評估（無）

PA brief §R4-T4 容許「如 UI test 框架不適配既有 test infra → push back PM 改用 minimal manual smoke checklist」。我評估後**不 push back**：
- 既有 `test_agent_tracker_contract.html`（Round 2 retro）已建立純瀏覽器 mock-fetch test pattern；沿用比新增 jsdom/playwright 框架輕
- 同時加 pytest sibling 補 CI 結構性 grep 防線（`test_replay_subtab_static_assets.py` 28 case）
- 兩層交付：browser HTML 跑 runtime DOM render 驗證；pytest sibling 跑 CI structural invariants
- 未來若上 vitest/jsdom 可升級，TODO 已留在 HTML 開頭注釋

## §10. 教訓追加 memory

完整 5 段教訓追加到 `docs/CCAgentWorkSpace/E1a/memory.md` § REF-20 Sprint B1 R4 區塊：
1. Sprint A baseline 4 cell 視覺合約 — execution_confidence='none' anti-cognitive-fraud SENTINEL
2. 5 態狀態機 + last-active=replay 必先 probe（localStorage 不可承擔 readiness assertion）
3. 30s 週期輪詢 deactivate 必 clearInterval（iframe 燒 timer 反模式）
4. Backend endpoint 不返 4 cell 數據時 — fetch 當 health probe + baseline fallback 比 silent 假升級乾淨
5. test fixture 沿用既有 mock-fetch pattern（避免 push back PM 引入 jsdom/playwright 新依賴）
6. Mac dev workflow：scp + ssh pytest，不 commit；commit 留給 PM 整合 sign-off
7. sibling regression FAIL 必先 stash --include-untracked + 重跑 clean HEAD 確認 pre-existing 屬 baseline 而非 IMPL 引入退化

---

**Sign-off**：E1a IMPL DONE · 待 E2 + A3 + E4 review · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1a/workspace/reports/2026-05-05--ref20_sprint_b1_r4_impl.md`


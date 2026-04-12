# A3 GUI 可用性審計修復工程日誌

**日期：** 2026-04-12  
**工程師：** PM+Conductor + E2 審查  
**範疇：** A3 GUI Usability Audit（`docs/CCAgentWorkSpace/A3/2026-04-12--gui_usability_audit_report.md`）全量修復  
**狀態：** ✅ E2 PASS（15/15）+ ✅ P3 Clean Sweep（§2.2 / §4.1 / §6.1）+ ✅ A3 驗收（20/20）— **正式完工**

---

## 一、背景

A3（UX/GUI Auditor）於 2026-04-12 對全部 22 個 HTML + 3 個 JS 文件完成靜態審計，輸出報告共 **CRITICAL ×2 / MAJOR ×14 / MINOR ×18 / SUGGESTION ×2** 計 36 條問題。本次工程在兩個 session 內完成全量修復。

---

## 二、修復清單

### CRITICAL（2/2 ✅）

| ID | 文件 | 問題 | 修復方式 |
|----|------|------|----------|
| C-1 | tab-risk.html / risk-tab.js | Danger Zone 操作（Reset Cooldown / Unhalt Session）`openConfirmModal()` 在 iframe 上下文中未定義，實際等同無確認直接執行 | `common.js` 新增完整 `openConfirmModal()` 實現，包含 `_OC_CONFIRM_ACTIONS` 元數據、自注入 `.oc-confirm-overlay` modal HTML；現在所有 tab iframe 都能使用 |
| C-2 | tab-strategy.html | 策略刪除 `deleteStrategy()` 調用 `openConfirmModal("delete-strategy")` 同樣在 iframe 無定義 | 同 C-1，`common.js` 統一修復 |

### MAJOR（14/14 ✅）

| ID | 文件 | 問題 | 修復方式 |
|----|------|------|----------|
| M-1 | app.js | MODULE_NOTE 仍寫「Bearer Token 認證」但已遷移 HttpOnly cookie | 更新頂部 docstring |
| M-2 | tab-risk.html | 信息過載（原 1390 行），無法快速定位目標設置 | 新增 Monitor/Config 子 tab 切換器（rtab-monitor/rtab-config）；Monitor 組含只讀狀態，Config 組含可編輯設置；`switchRiskTab()` 切換顯隱 |
| M-3 | tab-risk.html | P1 Per-Trade Risk 標籤誤導（實為軟參數非 P1 硬限制） | 改名「Per-Trade Risk Budget / 单笔风险预算」，描述更新 |
| M-4 | tab-risk.html | ATR Multiplier 缺具體數值範例 | 描述加入「例：BTCUSDT ATR=800 USDT 时，2.0x = 1600 USDT 止损；3.0x = 2400 USDT」 |
| M-5 | tab-risk.html | 保存按鈕分散，可能遺漏 | 頁面底部（`</body>` 前）加入浮動 dirty-state 提醒條 `#risk-dirty-bar`；所有 `.oc-input`/`.oc-select`/`checkbox` 修改時顯示 |
| M-6 | tab-governance.html | 首次打開信息過載，缺少引導 | 加入頂部 Quick Status Banner（4 項：Auth/Risk/Recon/Learning）；Decision Leases + Reconciliation 兩卡改為可折疊（預設收縮） |
| M-7 | tab-risk.html | btn-apply-ai 永久 disabled，誤導用戶 | 移除按鈕，改為說明文字 |
| M-8 | tab-paper.html | Paper 平倉使用原生 `confirm()`，與 Live tab 標準不一致 | 新增 `#paper-confirm-modal` 自定義 modal；`closePosition()` / `closeAllPositions()` 改用 callback 模式調用 |
| M-9 | tab-settings.html | 確認重啟後無法感知何時重啟 | 頁面頂部加入 sticky 倒計時橫幅 `#restart-top-banner`；`startRestartCountdown()` 同時更新橫幅 |
| M-10 | console.html | Charts tab（/trading）作為 iframe 嵌入時出現雙重 header | `trading.html` 新增 `?embed=1` 模式：`<script>` 在 `DOMContentLoaded` 前偵測參數並隱藏 `#trading-header`；console.html Charts src 改為 `/trading?embed=1`；URL 拼接修正為 `sep = src.includes('?') ? '&' : '?'` |
| M-11 | 多 tab | 大部分 tab 缺少移動端適配 | `common.js` `ocInjectBaseCSS()` 新增 `@media (max-width: 700px)` 規則（`oc-grid-2/3`/`oc-table`/`oc-input`/`oc-strat-grid`） |
| M-12 | tab-risk.html | 三引擎 Tab 視覺區分不足，Live 按鈕看起來像 disabled | Live 引擎 tab 按鈕加入紫色邊框（`rgba(168,85,247,0.5)`）+ `title` tooltip |
| M-13 | tab-system.html | Quick Action 按鈕三個 disabled 按鈕佔空間卻無互動 | qa-demo/qa-feed/qa-scanner 改為 `<span class="qa-status-row">` 純狀態指示器；Paper 按鈕根據 session 狀態動態顯示 Start/Stop |
| M-14 | tab-governance.html | SM-01/SM-04/EX-04 縮寫無解釋 | Authorization 卡標題加 `<abbr>` SM-01 tooltip；Risk Governor 加 SM-04 tooltip；Reconciliation 加 EX-04 tooltip |

### MINOR（18/18 ✅）

| ID | 文件 | 問題 | 修復方式 |
|----|------|------|----------|
| mn-1 | console.html | 貨幣切換 badge 重複（header + sidebar） | 移除 sidebar 中的 "Currency / 计价货币" section（含重複 badge） |
| mn-2 | console.html | sidebar Live/Paper toggle 違反直覺（點 Live → 切到 Paper） | `toggleSidePanel()` 改為 `_sidePanel = clicked`（直接顯示目標），加入明確的「🔴 Live / 🧪 Paper」切換按鈕組，移除混淆的點陣指示器 |
| mn-3 | console.html | UPL 縮寫無展開 | sidebar Net PnL 標籤加 `<abbr title="Net Unrealized Profit & Loss...">` tooltip；detail 文字從 `UPL:` 改為 `UPL (Unrealized PnL):` |
| mn-4 | tab-system.html | 模式升級路徑不直觀 | mode-btn-grid 上方加流程箭頭圖：🔒 设计 → 👁️ 观察 → 🌑 影子 → 🧪 Demo → 🟣 实盘 |
| mn-5 | login.html | OpenClaw Gateway 硬編碼 Tailscale URL | 改為 `<a id="gw-link">` + JS `document.getElementById('gw-link').href = window.location.origin + '/openclaw'` |
| mn-6 | tab-ai.html | API Key 保存後只顯示「已配置」無格式驗證 | 新增 `KEY_FORMATS` 物件（6 個 provider 的 prefix/minLen/hint）；`saveProviderKey()` 前置格式校驗，錯誤即 toast 提示 |
| mn-7 | tab-phase4.html | Teacher 卡片 30s 刷新過慢 | 新增單獨 `setInterval(loadTeacherCard, 10000)` 10s 刷新 |
| mn-8 | tab-live.html | 緊急停止按鈕與普通停止按鈕緊鄰，易誤觸 | 兩者間插入 1px 高 24px 分隔線（`width:1px;height:24px;background:var(--border);margin:0 8px`） |
| mn-9 | tab-strategy.html | 表格 headers 純英文 | Scanner/ActiveSymbols/Intents 三個表格 headers 改為「中文 / English」格式 |
| mn-10 | index.html | data-action 舊版 API 按鈕無 legacy 說明 | 頁面頂部加入黃色警告橫幅，標明「Legacy UI / 遗留界面」+ 前往 `/console` 按鈕 |
| mn-11 | tab-risk.html | Live 引擎 tab 視覺同 M-12，已修 | ✅（已含在 M-12） |
| mn-12 | tab-live.html | 30s 刷新偏慢 | 已為 15s（`setInterval(refreshPage, 15000)`），審計時已修，無需再改 |
| mn-13 | tab-governance.html | ATR 等縮寫未解釋 | ATR Multiplier 描述加入具體例子（已含在 M-4） |
| mn-14 | tab-strategy.html | 健康度缺少縱覽 | 新增 Strategy Health Summary Bar：Active/Paused/Stopped chips + 迷你分布條；`loadStrategies()` 更新 |
| mn-15 | tab-phase4.html | 同 mn-7 | ✅ |
| mn-16 | common.js | `openConfirmModal` 在 iframe 無定義 | ✅（已含在 C-1） |
| mn-17 | tab-paper.html | PnL 數據無趨勢可視化 | 新增 SVG 迷你折線圖（#pnl-sparkline）；`loadFills()` 調用 `updatePnlSparkline()` 計算累計 PnL 序列並繪製彩色折線 |
| mn-18 | trading.html | 嵌入 iframe 時有雙重 header | ✅（已含在 M-10） |

### SUGGESTION（2/2 ✅）

| ID | 文件 | 建議 | 實現 |
|----|------|------|------|
| S-1 | tab-paper.html | PnL 趨勢折線圖 | 純 SVG `<polyline>` 迷你圖，取最近 50 笔成交計算累計收益，正收益綠色/負收益紅色，不依賴外部庫 |
| S-2 | tab-strategy.html | 策略健康度彙總視圖 | 策略列表卡片上方加 Health Summary Bar：Active/Paused/Stopped chip 計數 + 彩色分布條（active=綠/paused=黃），由 `loadStrategies()` 更新 |

---

## 三、E2 代碼審查結果

**E2 審查員：** Explore 子 Agent（模擬 E2 角色）  
**審查時間：** 2026-04-12 本 session 末  
**方法：** 逐文件靜態檢查（函數/ID/CSS/邏輯）+ Node.js 語法校驗

| 文件 | 結論 | 行數 |
|------|------|------|
| common.js | ✅ PASS | 730（< 800 ⚠️） |
| console.html | ✅ PASS | — |
| tab-risk.html | ✅ PASS（dirty-bar 確認存在 L525-530） | 569（< 1200 🛑） |
| tab-governance.html | ✅ PASS | — |
| tab-system.html | ✅ PASS | — |
| tab-paper.html | ✅ PASS | 658（< 800 ⚠️） |
| tab-settings.html | ✅ PASS | — |
| tab-strategy.html | ✅ PASS | 554（< 800 ⚠️） |
| tab-phase4.html | ✅ PASS | — |
| tab-live.html | ✅ PASS | — |
| tab-ai.html | ✅ PASS | 797（< 800 ⚠️，臨界） |
| login.html | ✅ PASS | — |
| index.html | ✅ PASS | — |
| trading.html | ✅ PASS | — |
| governance-tab.js | ✅ PASS | — |

**JS 語法：** `node --check common.js` → exit:0 ✅  
**總結：** 15/15 PASS，無 FAIL，1 PARTIAL（dirty-bar）審查後確認為 PASS。

---

## 四、架構決策記錄

### D-1：`openConfirmModal` 加入 `common.js`

**問題：** `openConfirmModal` 定義在 `app.js`，只在 `index.html` 上下文加載。`tab-risk.html`/`tab-strategy.html` 等 iframe 上下文中此函數未定義，導致 `resetCooldown()`/`unhaltSession()`/`deleteStrategy()` 的確認彈窗無效（實際上是 ReferenceError）。

**決策：** 在 `common.js` 內定義 `openConfirmModal()` 作為 iframe 上下文的完整實現。`app.js` 的版本在 `index.html` 上下文中因後加載而自然覆蓋，不產生衝突。無需改動 `risk-tab.js` / `tab-strategy.html` 的調用代碼。

### D-2：SVG 折線圖而非 lightweight-charts

**問題：** `trading.html` 引入了 `lightweight-charts@4.1.0`，但該庫無法在多個 tab 中重複引入（體積大、初始化複雜）。

**決策：** Paper tab PnL sparkline 使用純 SVG `<polyline>`，通過計算累計 PnL 序列映射到 0-400×0-48 坐標系，無外部依賴。輕量、零加載時間、CSS 變量統一主題色。

### D-3：`?embed=1` 模式

**問題：** `trading.html` 有自己的 header/sidebar，嵌入 console.html iframe 時出現雙重 header。

**決策：** 不引入新的 template 系統，改為在 `trading.html` 用 URL 參數 `?embed=1` 控制 header 顯隱。URL 拼接修正：`sep = src.includes('?') ? '&' : '?'` 避免雙問號 bug。

---

## 五、已知遺留（非阻塞）

| 項目 | 原因 | 優先級 |
|------|------|--------|
| §4.1 tab-risk.html 左右雙欄 diff 模式 | ✅ **已修復**（P3 Clean Sweep） | — |
| §6.1 CSS metric 命名不一致（oc-metric / live-metric / mc） | ✅ **已修復**（P3 Clean Sweep） | — |
| §2.2 各 tab 缺少「加載失敗」狀態區分 | ✅ **已修復**（P3 Clean Sweep） | — |
| tab-ai.html 797 行，臨近 800 ⚠️ 警告線 | 下次添加功能時需考慮拆分 | 低 |

---

## 六、P3 Clean Sweep（後續 session 補完）

三個 P3 項目在後續 session 全量修復。

### §2.2 — 加載失敗狀態（11 個 silent return 修復）

| 文件 | 函數 | 修復方式 |
|------|------|----------|
| tab-paper.html | `loadSession()` | session badge → `oc-chip-bad` + "连接失败" |
| tab-paper.html | `loadPositions()` | positions-tbody → error 行 + 重試按鈕 |
| tab-paper.html | `loadOrders()` | orders-tbody → error 行 + 重試按鈕 |
| tab-paper.html | `loadFeed()` | feed-badge → `oc-chip-bad` |
| tab-paper.html | `loadFills()` | fills-tbody → error 行 + 重試按鈕 |
| tab-paper.html | `loadShadow()` | shadow-tbody → error 行 |
| tab-ai.html | `loadCost()` | a-today → "⚠ 失败 / Failed" |
| tab-ai.html | `loadAdaptive()` | ab-mult → "⚠" + ab-reason → "连接失败" |
| tab-ai.html | `loadConsult()` | ai-badge → `oc-chip-bad` "API 失败" |
| tab-ai.html | `loadSessions()` | sessions-tbody → error 行 |
| risk-tab.js | `loadRiskStatus()` | r-pressure/r-drawdown → "⚠" |
| risk-tab.js | `loadDynamicRisk()` | dr-status → `oc-chip-bad` "API 失败" |

tab-strategy.html、tab-learning.html 審核後確認**已有完整錯誤處理**，無需修改。

### §4.1 — Risk Tab 左右雙欄 Diff 模式（risk-tab.js）

**實現機制：**
1. `_setInput(id, val)` 同步設置 `el.dataset.original = String(val)` 儲存載入時原始值
2. `_DIFF_MAP`：14 個 `input ID → display cell ID` 映射（stop/tp/trailing/time/atr/drawdown/leverage/daily/p1/single/total/same-dir/cool-count/cool-min）
3. `_updateDiffHighlights()`：遍歷 `_DIFF_MAP`，若 `input.value !== dataset.original` → 在 display cell 加 `.oc-diff-changed` CSS 高亮 + 插入 `.oc-diff-label` 子元素顯示「← was: X」
4. `_resetDiffHighlights()`：保存成功後重置所有 `data-original` 為新值並清除高亮
5. 所有 `_RISK_INPUT_IDS` input 事件 + checkbox change 事件呼叫 `_updateDiffHighlights()`
6. 三個 save 函數（stop/position/cooldown）在 `_riskFormDirty = false` 後呼叫 `_resetDiffHighlights()`
7. tab-risk.html 右側欄 header 從「当前生效值 / Current Values」改為「原值 / Original（修改后高亮）」（3 個 section 同步更新）

### §6.1 — CSS Metric 命名統一

**實現機制：**
- `common.js` `ocInjectBaseCSS()` 新增 `live-metric*` CSS alias classes（`live-metric`/`live-metric-label`/`live-metric-val`/`live-metrics`）作為 canonical 定義
- `tab-live.html` 移除原有 57 行重複 `live-metric*` `<style>` 區塊，改為遷移注釋
- `oc-metric`（主 tab）= `live-metric`（live tab）= 語義等價，統一來源
- `mc`（console.html sidebar）上下文不同（compact 側邊欄），保留不動

---

## 七、文件修改摘要（完整）

| 文件 | 變更類型 | 主要內容 |
|------|----------|----------|
| common.js | 增強 | `openConfirmModal()` + CSS modal + mobile responsive + `live-metric*` CSS + `ocLoadError()` + `.oc-diff-changed`/`.oc-diff-label`/`.oc-load-error` CSS |
| console.html | 修復 | 側邊欄重構 + URL 拼接 + UPL tooltip |
| tab-risk.html | 重大增強 | Monitor/Config 子 tab + dirty bar + Live 紫色 + P1 改名 + 右側欄 header 改為「原值」 |
| risk-tab.js | 重大增強 | diff mode（`_DIFF_MAP`/`_updateDiffHighlights`/`_resetDiffHighlights`）+ `_setInput` 儲存 original + 2 silent return 修復 |
| tab-governance.html | 增強 | Quick Status Banner + 可折疊卡片 + SM/EX tooltips |
| governance-tab.js | 增強 | 4 處 `updateQuickStatus()` 調用 |
| tab-system.html | 修復 | QA status 指示器 + 模式流程箭頭 |
| tab-paper.html | 增強 | 自定義平倉 modal + SVG PnL sparkline + 5 個加載失敗狀態 |
| tab-settings.html | 增強 | 重啟倒計時 sticky banner |
| tab-strategy.html | 增強 | 雙語表頭 + 健康度彙總欄 |
| tab-phase4.html | 修復 | Teacher 10s 獨立刷新 |
| tab-live.html | 修復 | 緊急停止按鈕物理分隔 + 移除重複 `live-metric*` CSS |
| tab-ai.html | 增強 | API Key 格式驗證（6 providers）+ 4 個加載失敗狀態 |
| login.html | 修復 | 動態 Gateway URL |
| index.html | 修復 | Legacy 橫幅 |
| trading.html | 修復 | `?embed=1` header 隱藏 |
| app.js | 文檔 | Bearer Token → HttpOnly Cookie 注釋更新 |

---

---

## 八、A3 正式驗收（P3 Clean Sweep）

**驗收時間：** 2026-04-12（後續 session）  
**審查員：** A3（GUI/UX Auditor）  
**方法：** 逐條 grep + 行號核查

| 驗收項目 | 細項數 | 結果 |
|---------|--------|------|
| §2.2 加載失敗狀態 | 11 個 silent return | **11/11 PASS** |
| §4.1 Risk Tab diff 模式 | 7 項（risk-tab.js 6 + tab-risk.html 1） | **7/7 PASS** |
| §6.1 CSS metric 統一 | 2 項（common.js + tab-live.html） | **2/2 PASS** |
| **合計** | **20 項** | **✅ 20/20 PASS** |

**A3 結論：無發現問題，正式完工，可合併至主分支。**

---

*工程師：PM+Conductor*  
*E2 審查：Explore 子 Agent*  
*A3 驗收：A3 子 Agent*  
*A3 審計原報告：`docs/CCAgentWorkSpace/A3/2026-04-12--gui_usability_audit_report.md`*

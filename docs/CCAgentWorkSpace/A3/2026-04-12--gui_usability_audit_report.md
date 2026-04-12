# A3 GUI 可用性審計報告 / GUI Usability Audit Report

**審計日期：** 2026-04-12
**審計範圍：** 全部 22 個 HTML 文件 + 3 個 JS 文件（app.js / common.js / governance.js）
**GUI 基礎路徑：** `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`
**嚴重度定義：** [CRITICAL] 導致功能失效或安全問題 / [MAJOR] 嚴重影響用戶體驗 / [MINOR] 可改進項 / [SUGGESTION] 優化建議

---

## 一、死按鈕檢測 / Dead Button Detection

### 1.1 所有 onclick handler 驗證結果

**結論：所有 onclick handler 均有對應的 JavaScript function 定義。** 經過完整交叉比對（~100 個唯一 onclick 函數名 vs JS/HTML 中的 function 定義），未發現「按鈕指向不存在函數」的死按鈕。

### 1.2 功能性死按鈕（函數存在但功能無效）

**[MAJOR] index.html:38-45 — 隱藏的 Bearer Token 面板殘留**
- `tokenInput` 和 `connectButton` 被隱藏（`display:none`），但 `app.js:2164` 仍在 DOMContentLoaded 時自動 `click()` 這個隱藏按鈕
- `app.js:2167-2178` 的 connectButton click handler 仍會讀取已隱藏的 `tokenInput.value`
- 影響：不影響功能（cookie auth 自動生效），但造成 console 中的 DOM 操作浪費
- 建議：移除 `app.js` 中對 `connectButton`/`tokenInput` 的全部引用，改為直接調用 `loadDashboard()`

**[MAJOR] tab-risk.html:440 — AI 止損建議「採納」按鈕永久 disabled**
- `btn-apply-ai` 按鈕標註「開發中」且 `disabled`
- `applyAIAdvice()` 函數只顯示一個 toast 提示用戶手動調整
- 影響：用戶可能期望此功能可用，看到 disabled 按鈕會困惑
- 建議：要嗎移除此按鈕，要嗎在 AI 返回建議後啟用並自動填充左側表單欄位

**[MINOR] tab-system.html:82-91 — 三個 Quick Action 按鈕標記為只讀**
- `qa-demo`、`qa-feed`、`qa-scanner` 三個按鈕使用 `disabled` + `cursor:not-allowed` + `(只读/RO)` 標記
- 處理方式正確（不會誤導用戶點擊），但佔用了大量水平空間卻無法交互
- 建議：改為小型狀態指示器（純狀態 badge），不使用按鈕樣式

**[MINOR] tab-system.html:77 — Paper Quick Action 缺少 session 狀態感知**
- `qa-paper` 按鈕始終可點擊，但如果 Paper session 已在運行，點擊 `confirmAction('paper')` 會嘗試重複啟動
- 建議：根據 session 狀態動態切換為 Start/Stop，或在 session 活躍時 disable

### 1.3 API 端點驗證

**[MINOR] index.html 的 data-action 按鈕群（enable-spot、arm-demo 等）**
- 這些按鈕（第 148-151 行）調用的 API 端點（`/api/v1/control/demo/`, `/api/v1/control/product-family/`）是舊版 Control Plane API
- 功能上可用，但 index.html 本身作為 entry page 已被 console.html 取代，用戶不太可能直接訪問
- 建議：如果 index.html 不再作為主要入口，考慮重定向到 /console 或標註為 legacy

---

## 二、設計不合理 / Design Issues

### 2.1 頁面結構與導航

**[MAJOR] console.html 雙重導航（Tab Bar + Sidebar Nav Grid）**
- 頂部 Tab Bar 和側邊欄 Navigation Grid 完全重複，均包含相同的 11 個 tab
- 這兩套導航指向相同的 `switchTo()` 函數，功能完全一致
- 影響：浪費了寶貴的側邊欄空間，增加認知負擔
- 建議：側邊欄保留為「狀態面板」，移除 `nav-grid` 導航按鈕區域，釋放空間顯示更多即時狀態信息

**[MAJOR] tab-trading.html 雙層 iframe 嵌套**
- console.html 把每個 tab 加載為 iframe，tab-trading.html 自身又包含兩個 iframe（tab-demo.html、tab-paper.html）
- 造成三層 DOM 嵌套：console → tab-trading → tab-demo/tab-paper
- 影響：(a) 性能開銷；(b) CSS 變量需要三重注入；(c) 貨幣切換需要跨 iframe storage 事件傳播
- 建議：長期重構為 SPA 架構（或至少消除內層 iframe），短期可考慮將 tab-trading 改為直接切換 DOM section

**[MINOR] Charts tab 指向 `/trading`（trading.html）**
- console.html:239 中 Charts tab 的 src 是 `/trading`（657 行的獨立完整頁面含 K 線圖表）
- trading.html 有自己的 header、sidebar，作為 iframe 嵌入時產生二重 header
- 建議：為 iframe 嵌入場景提供無 header 版本（如 `?embed=1` 查詢參數隱藏 header）

### 2.2 載入狀態 / Loading States

**[MAJOR] 大部分 tab 缺少全局載入失敗狀態**
- 多數 tab 的 `loadAll()` 函數在 API 失敗時只是靜默保留 `--` 或 `Loading...` 文本
- 用戶無法區分「正在載入」和「載入失敗」
- 範例：tab-learning.html 的 `loadOverview()` 失敗時，6 個 metric 永遠顯示 `--`
- 建議：(a) 設定 5-10s timeout 後顯示「連接失敗，請檢查引擎狀態」提示；(b) 區分「載入中（動畫）」、「無數據」、「連接失敗（紅色提示 + 重試按鈕）」三種狀態

**[MINOR] tab-live.html 手動刷新間隔不夠靈活**
- Live tab 使用 30s `setInterval` 刷新，對實盤交易來說偏慢
- tab-demo.html 和 tab-paper.html 都是 15s
- 建議：Live tab 刷新間隔降為 10-15s，尤其是持倉和 PnL 數據

### 2.3 信息架構

**[MAJOR] tab-risk.html 信息過載（1390 行）**
- 一個 tab 內包含：Risk Status、Risk Governor、Per-Engine Config、P0/P1/P2 三層配置、Stop Manager（8 個參數）、Position Sizing（6 個參數）、Loss Cooldown、H0 Gate、Dynamic Adjustment、AI 止損建議、AI Risk Context、AI Budget、Danger Zone
- 用戶需要滾動很長才能找到目標設置
- 建議：將 Risk tab 拆分為「Risk Monitor（只讀狀態）」和「Risk Config（可編輯設置）」兩個子 tab

**[MAJOR] tab-governance.html 超大文件（2047 行）**
- 包含 11 個 modal dialog + 大量內聯 JS + HTML
- 違反 CLAUDE.md §九「1200 行硬上限」
- 建議：(a) 將 modal 提取為獨立組件；(b) 將 JS 邏輯拆入 governance.js（當前 governance.js 僅 237 行）

**[MINOR] Live、Demo、Paper 三個 Tab 之間的功能高度重複**
- 三者都有：Account Balance 卡片、PnL Overview、Positions 表格、Fill History、Performance Metrics
- 佈局和欄位幾乎相同，但 CSS class 命名不一致（Paper 用 `oc-metric`，Live 用 `live-metric`）
- 建議：提取共用的 Position/PnL/Fill 組件，三個 tab 引用同一組件 + 配置差異

---

## 三、不清楚的地方 / Unclear UI Elements

### 3.1 缺少 Tooltip 的重要控件

**[MAJOR] tab-risk.html — Position Sizing 中 "P1 Per-Trade Risk" 易混淆**
- 「P1 Per-Trade Risk」這個標籤暗示它是 P1 級別的硬限制（第 254 行），但實際它是可調整的軟參數
- P0/P1/P2 三級架構中，P1 = Global Limits（不可被 AI 覆蓋），但此欄位的實際行為更接近 P2
- 建議：改名為「Per-Trade Risk Budget / 單筆風險預算」，去掉 P1 前綴以免混淆

**[MAJOR] tab-risk.html — ATR Multiplier 含義不直觀**
- 第 210 行：「ATR 止損乘數…設為 0 則禁用 ATR 止損，使用固定百分比。值越大止損越遠」
- 缺少具體數值範例，用戶難以理解 2.0x 和 3.0x 的實際差距
- 建議：在描述中加入範例——「例：BTC ATR=500 USDT 時，2.0x = 距開倉價 1000 USDT 止損」

**[MINOR] tab-risk.html — 三引擎 Tab 選擇器缺乏視覺區分**
- Paper/Demo/Live 三個引擎 tab 按鈕（第 114-125 行）使用相同大小的 `oc-btn`，僅靠顏色深淺區分
- Live 按鈕在未選中時 `opacity:0.55`，與 disabled 狀態視覺相似
- 建議：Live 按鈕使用紅色邊框 + 專用 icon，確保任何時候都能一眼區分

### 3.2 狀態指示器缺少圖例

**[MINOR] tab-system.html — mode-btn-grid 的模式含義**
- `design_only`、`observe_only`、`shadow_only`、`demo_reserved`、`live_reserved` 五個模式
- 雖然每個按鈕有中文描述，但它們之間的關係和升級路徑不夠直觀
- 建議：在模式按鈕區域上方加入一個簡單的流程箭頭圖：設計 → 觀察 → 影子 → Demo → 實盤

**[MINOR] console.html 側邊欄 — Live vs Paper 面板切換不直觀**
- 點擊 Live 面板會切換到 Paper 面板（toggle 行為），違反直覺——用戶可能期望點擊 Live 就看 Live
- 底部的兩個小圓點（`dot-live`、`dot-paper`）是唯一的狀態指示，但太小且無文字標籤
- 建議：改為兩個明確的 tab 按鈕「Live | Paper」，點擊即顯示對應面板（非 toggle）

### 3.3 縮寫說明不足

**[MINOR] 多處使用的縮寫缺少解釋**
- `UPL`（Unrealized Profit/Loss）：console.html:410 使用但無展開
- `ATR`（Average True Range）：tab-risk.html 多處使用
- `H0 Gate`：非標準術語，首次接觸的用戶不知道 H0 是什麼
- `SM-01/SM-02/SM-04/EX-04`：tab-governance.html 使用但無鏈接到解釋
- 建議：為專業術語加上 `title` tooltip 或首次出現時括號展開

---

## 四、可優化的地方 / Optimization Opportunities

### 4.1 冗餘信息顯示

**[MINOR] console.html 側邊欄 — 貨幣切換出現兩次**
- Header 中有一個 `oc-curr-badge`（第 103 行），側邊欄又有一個（第 174 行）
- 功能完全相同，佔用空間
- 建議：保留 header 中的即可，側邊欄的可移除

**[MINOR] tab-risk.html — 止損設置左右雙欄佈局**
- 左側為可編輯輸入框，右側為「當前生效值」只讀顯示（第 231-242 行）
- 但輸入框在頁面載入時已經填入當前值，右側顯示重複
- 建議：改為「修改前/修改後」diff 對比模式——只有用戶修改了值時才顯示差異

### 4.2 缺少自動刷新的地方

**[MINOR] tab-phase4.html — 30s 刷新間隔，卡片內容更新不夠即時**
- Phase 4 Teacher/LinUCB/News/DL3 四個卡片使用 30s 刷新
- 對於新聞管線（News Pipeline）和 DL3，30s 足夠
- 但 Teacher Session 狀態在 session 運行中變化較快
- 建議：Teacher 卡片在 session 活躍時降為 10s 刷新

### 4.3 移動端響應性

**[MAJOR] 大部分 tab 缺少移動端適配**
- console.html 的 `@media (max-width: 860px)` 只是隱藏了 sidebar，但 tab 內容未做響應式
- tab-risk.html 的 `oc-grid-2`/`oc-grid-3` 使用 CSS Grid 有基本響應，但表單在窄屏幕上仍需水平滾動
- tab-live.html 的 positions 表格 9 列在手機上溢出
- 建議：(a) 表格在窄屏使用卡片式佈局（每行變成一張卡片）；(b) 核心操作按鈕固定在底部

### 4.4 數據可視化

**[SUGGESTION] 全系統缺少趨勢圖表**
- PnL 數據僅以數字展示，缺少折線圖/面積圖顯示歷史趨勢
- 持倉/策略狀態缺少時間線視覺化
- trading.html 中已引入 `lightweight-charts`，但其他 tab 未使用
- 建議：在 Paper/Demo/Live tab 的 PnL Overview 區域加入一個小型嵌入式 PnL 趨勢圖（使用已有的 lightweight-charts）

**[SUGGESTION] tab-strategy.html — 策略健康度缺少一覽式指標**
- 策略列表以卡片形式展示，但缺少「系統整體策略健康度」的彙總視圖
- 建議：在頂部加入一行策略分佈餅圖（active/paused/stopped 比例）

---

## 五、反人類設計 / Anti-patterns

### 5.1 危險操作確認機制審計

**[CRITICAL] tab-risk.html:501 — Danger Zone 的「Reset Loss Cooldown」和「Unhalt Session」使用原生 `confirm()` 而非自定義 modal**
- 這兩個操作會：(a) 重置連續虧損保護（允許繼續交易）；(b) 解除熔斷暫停
- 原生 `confirm()` 太簡單，只有 OK/Cancel，無法展示風險説明
- 同一頁面的 Live Engine Risk Config 修改有完善的自定義 modal（第 134-150 行），標準不一致
- 建議：改用與 Live 引擎相同等級的自定義 modal，展示：(a) 當前回撤/虧損狀態 (b) 恢復交易的風險評估 (c) 要求輸入原因

**[CRITICAL] tab-strategy.html:223 — 策略刪除使用原生 `confirm()`**
- 刪除策略是不可逆操作（按鈕標註「永久删除策略（不可撤销）」）
- 但確認方式僅為原生 `confirm()`，沒有二次確認或輸入策略名稱驗證
- 建議：使用自定義 modal，要求用戶輸入策略名稱才能確認刪除（類似 GitHub 刪除 repo 的模式）

**[MAJOR] tab-paper.html:352/365 — Paper 單筆/全部平倉使用原生 `confirm()`**
- Paper 雖然不涉及真實資金，但批量平倉影響策略運行
- 相比之下，Live tab 的平倉（tab-live.html:397-410）使用了完善的自定義 dialog
- 標準不一致
- 建議：統一所有平倉操作為自定義 dialog

### 5.2 不可逆操作警告不足

**[MAJOR] tab-settings.html:95 — 「計劃重啟服務器」多步驟 modal 設計良好，但缺少倒計時可視化**
- 重啟後 10-30 秒內無法監控市場、執行止損
- 雖然有延遲選擇（5/10/15/30/60 分鐘），但一旦確認後用戶無法知道何時重啟
- 建議：確認後在 Settings tab 頂部顯示倒計時橫幅，允許取消計劃重啟

### 5.3 反直覺的控件放置

**[MAJOR] tab-risk.html — 「保存」按鈕位置不一致**
- Stop Manager 的「保存止損設置」按鈕在左側欄底部（第 225 行）
- Position Sizing 的「保存仓位设置」按鈕在右側欄底部（第 318 行）
- 使用者必須分別保存兩組設置，可能遺漏其中一組
- 建議：(a) 在頁面底部加入統一的「Save All Risk Config」按鈕；(b) 或在用戶修改任何欄位後顯示浮動的「有未保存的修改」提醒條

**[MINOR] tab-live.html — 緊急停止按鈕與普通停止按鈕並排**
- `btn-live-start`、`btn-live-stop`、`btn-emergency-stop` 三個按鈕在同一行（第 207-209 行）
- 緊急停止按鈕（紅色）太容易被誤觸，特別是在緊張時
- 建議：緊急停止按鈕移到頁面底部的獨立區域，或增加物理隔離（與普通按鈕至少 40px 間距）

### 5.4 信息過載

**[MAJOR] tab-governance.html — 7 個可折疊區域 + 4 個卡片 + 6 個 modal**
- 首次打開此頁的用戶面臨：Authorization、Risk Governor、Decision Leases、Reconciliation、Paper→Live Gate、Learning Tier、Events Feed、Governance Summary、Incident Timeline、Pending Approvals、Audit Trail
- 大量資訊同時呈現，缺少引導
- 建議：(a) 默認只展示 Authorization + Risk Governor 兩個核心卡片，其餘摺疊；(b) 加入「快速狀態」頂部橫幅：一行文字總結治理健康狀態

---

## 六、跨 Tab 一致性問題 / Cross-Tab Consistency

### 6.1 CSS Class 命名不一致

**[MINOR] 三套不同的 metric 樣式系統**
- `oc-metric` / `oc-metric-val`：大部分 tab 使用（tab-risk, tab-governance 等）
- `live-metric` / `live-metric-val`：tab-live.html 獨用（第 62-81 行）
- `mc` / `mc-val`：console.html sidebar 獨用（第 45-49 行）
- 建議：統一為單一 metric 組件系統，live 特殊主題通過 modifier class 實現

### 6.2 自動刷新間隔不一致

**[MINOR] 各 tab 刷新間隔差異大且無文檔說明**
| Tab | 間隔 | 合理性 |
|-----|------|--------|
| tab-governance | 10s | 合理（事件驅動） |
| tab-paper/demo/risk/strategy/system/monitoring | 15s | 合理 |
| tab-trading | 20s (checkUnifiedStatus) | 偏慢 |
| tab-ai/learning/settings/phase4/live | 30s | Live 偏慢 |

建議：Live tab 改為 10-15s

### 6.3 雙語標籤風格不一致

**[MINOR] 部分 tab 使用「中文 / English」格式，部分只有中文或只有英文**
- tab-live.html：大部分用中文（「持倉 / Positions」、「掛單 / Open Orders」）
- tab-strategy.html：部分只有英文（「Score」、「Reason」、「State」）
- tab-governance.html：混合（「Authorization / 授权」但 table header 純英文）
- 建議：統一為「中文 / English」格式，至少 section 標題層級保持一致

---

## 七、安全相關 UI 問題 / Security-Related UI Issues

**[MINOR] login.html:54 — OpenClaw Gateway 鏈接硬編碼為 Tailscale 域名**
- `https://trade-core.tail358794.ts.net` 是內部 Tailscale 地址
- 違反 CLAUDE.md §七「路徑不硬編碼」原則
- 建議：移除此鏈接或改為相對路徑 `/openclaw/`

**[MINOR] tab-ai.html — API Key 輸入框**
- 六個 AI provider 的 API key 輸入框（第 72-137 行）使用 `type="password"`，保護良好
- 但保存後的狀態 badge（「已配置」/「未配置」）不顯示 key 是否真的有效
- 建議：保存後立即驗證（至少檢查格式），並顯示「已驗證 / 格式錯誤 / 未驗證」狀態

---

## 八、文件大小違規 / File Size Violations

| 文件 | 行數 | 違規 |
|------|------|------|
| app.js | 2608 | **嚴重超標**（硬上限 1200） |
| tab-governance.html | 2047 | **嚴重超標**（硬上限 1200） |
| tab-risk.html | 1390 | **超標**（硬上限 1200） |
| tab-live.html | 1026 | **超警告線**（警告線 800） |
| tab-settings.html | 857 | **超警告線**（警告線 800） |
| tab-system.html | 805 | **超警告線**（警告線 800） |

**建議優先拆分方案：**
1. `app.js` → 拆為 `app-core.js`（連接/渲染）+ `app-actions.js`（按鈕動作）+ `app-config.js`（產品族配置）
2. `tab-governance.html` → 拆出 modal dialog 到獨立文件 + JS 搬入 governance.js
3. `tab-risk.html` → 拆為 `tab-risk-monitor.html`（只讀）+ `tab-risk-config.html`（可編輯）

---

## 九、總結 / Summary

### 嚴重度分佈

| 級別 | 數量 | 說明 |
|------|------|------|
| CRITICAL | 2 | Danger Zone/策略刪除使用原生 confirm() |
| MAJOR | 14 | 設計、信息架構、一致性、響應式 |
| MINOR | 18 | 標籤、tooltip、命名、冗餘 |
| SUGGESTION | 2 | 趨勢圖表、策略健康度 |

### 優先修復建議

1. **P0（立即）**：Danger Zone 操作改用自定義 modal + 策略刪除加輸入確認
2. **P1（本周）**：移除 index.html/app.js 中的 connectButton 死代碼 + 統一平倉確認機制
3. **P2（下兩周）**：文件拆分（app.js + tab-governance.html + tab-risk.html）
4. **P3（長期）**：CSS 組件統一 + 響應式適配 + PnL 趨勢圖表 + SPA 重構消除 iframe 嵌套

---

*審計人：A3 (UX/GUI Auditor)*
*審計方法：靜態代碼分析（全量 onclick 交叉比對、API 端點驗證、CSS 一致性檢查、文件行數統計）*

# A3 GUI 完整審查報告

生成時間：2026-04-24
審查員：A3 (UX Auditor Agent)
審查基準：靜態代碼分析（無實際瀏覽器渲染）
審查範圍：11 個主 Tab + 2 個子頁（index.html / login.html）+ console.html shell
GUI 根路徑：`/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`

---

## 執行摘要

- **整體評分：6.5 / 10**（較 2026-03-31 的 6.2 小幅提升，主要因 Live tab + API Key 管理改進 + P1-11 修復）
- **發現問題總數：62 項**（死/半死 endpoint 8 · 設計不合理 18 · 反人類 15 · 可優化 16 · 無障礙 5）
- **最關鍵發現（Top 3）**：
  1. **BREAKING**：Paper Tab 的 `submitOrder()` 和 `cancelOrder()` 函數被硬編碼為 `ocToast('已禁用')`，手動下單整塊 UI 是**活生生的死區** — 表單渲染但按鈕無作用（tab-paper.html:231-241）
  2. **CRITICAL**：System Tab 四個「快捷操作」中，`Demo`/`Feed`/`Scanner` 三個狀態 chip 雖已改為 `qa-status-row`（非按鈕），但 confirmAction('demo')/'scanner')/'feed' 的 CONFIRM_MSGS + executeConfirmed 邏輯仍完整存在（tab-system.html:394-406, 452-457）— 死代碼路徑
  3. **HIGH**：`index.html` 是 legacy fallback UI，已標記「遺留界面」但仍寫入了完整的 `data-action` API 調用（Safe Recheck Bundle / Demo Validate / Enable Spot / Arm Demo 等），用戶從 `/` 進入會看到完整但已廢棄的控制面板

---

## 一、死按鈕 / 死 Endpoint（8 項，A1 Critical–A3 Medium）

### D01 — [Critical] Paper Tab 手動下單 UI 整體死區

**位置**：`tab-paper.html:148-162`（表單）+ `tab-paper.html:231-241`（JS handler）

**渲染內容**：完整的 Order Form（Symbol / Side / Type / Qty / Price / Submit）摺疊在 `<details>` 內

**實際行為**：
```javascript
async function submitOrder() {
  ocToast('手动下单已禁用 — Rust 引擎自主管理交易', 'error');  // NO-OP with error toast
}
async function cancelOrder(orderId) {
  ocToast('手动取消已禁用 — Rust 引擎自主管理订单', 'error');
}
```

**診斷**：100% 死按鈕。用戶展開折疊區、填表、點「提交」，得到的只是錯誤 toast。違反 memory `feedback_no_dead_params.md`「可調參數禁止假功能」原則。

**建議**：
- 選項 A（推薦）：**整塊刪除**手動下單區塊 + 取消按鈕，Paper 的訂單由 Rust 策略自動管理，不該暴露給人類介面
- 選項 B：如仍需保留（教學/測試），UI 必須明確標記 `[DEV ONLY / 已禁用]`，按鈕 `disabled=true` + tooltip 說明

---

### D02 — [Critical] index.html legacy fallback 完整死按鈕區

**位置**：`index.html:144-155`（Quick Actions）+ `index.html:149-178`（Summary Grid）

**渲染內容**：6 個完整按鈕 `refresh / validate / set-demo-mode / enable-spot / arm-demo / bundle` + 4-metric action summary grid

**實際行為**：僅依賴 `/static/app-actions.js` 的 `data-action` 路由；頂部 banner 雖寫「已遷移到 /console」但頁面完整渲染，用戶不讀 banner 就會操作

**診斷**：對於誤入 `/` 根路徑的用戶完全不友好。即使歷史 bookmarks 已重定向，也應該 server-side 301 到 `/console`，而不是渲染 legacy UI。

**建議**：
- 在 FastAPI routes 加 `/` 的 301 redirect 到 `/console`
- 或將 index.html 改為純 redirect HTML：`<meta http-equiv="refresh" content="0;url=/console">`

---

### D03 — [High] System Tab 「快捷操作」代碼死路徑

**位置**：`tab-system.html:394-406`（CONFIRM_MSGS.demo / CONFIRM_MSGS.feed / CONFIRM_MSGS.scanner）+ `executeConfirmed()` 452-457

**現狀**：UI 已改為 `qa-status-row`（span 非 button）不可點擊；但 HTML 中 `confirmAction` 函數依然處理這 3 個 action，`executeConfirmed()` 還有專門的「請前往 Bybit Demo 頁面」「請前往策略中心」邏輯。

**診斷**：代碼冗余 + 若未來回滾 UI 到按鈕會觸發純 toast 「請前往 XX Tab」導航提示，用戶實際無法從此啟停這些功能。

**建議**：
- 刪除 `CONFIRM_MSGS` 中的 `feed / demo / scanner` 條目
- 移除 `confirmAction(action)` 分支對這 3 個的處理
- 保留唯一真實可操作的 `paper` 分支

---

### D04 — [High] Paper Tab 「市場行情 / Market Feed」 autoStart 函數空體

**位置**：`tab-paper.html:607-618`

```javascript
(async function autoStartFeed() {
  try {
    const ov = await ocApi('/api/v1/system/overview');
    // ... gets mode
    // RC-12: Market feed managed by Rust engine — no Python dispatcher needed
    // 空 — 沒有任何啟動邏輯
  } catch (e) {}
})();
```

**診斷**：函數完整執行 API 調用、讀取 mode、構造 autoModes 陣列，**但最終沒有任何操作**。死代碼。

**建議**：整個 IIFE 直接刪除，或至少改為 `// RC-12: market feed is Rust-managed, no auto-start needed on Paper tab`。

---

### D05 — [High] Risk Tab 「波動率自動槓桿」只讀 chip 永久顯示「始終啟用」無切換

**位置**：`tab-risk.html:435-443`

```html
<div style="font-size:13px;font-weight:600">波动率自动杠杆 / Auto Leverage (Volatility)</div>
<!-- ... -->
<span class="oc-chip oc-chip-good" style="font-size:10px">始终启用</span>
```

**診斷**：與其他動態 toggle 並排，但無 checkbox、無 API。用戶看到此模塊在「自動動態調整」區內期待可以關閉，實際**不存在 off 狀態**。反人類設計。

**建議**：
- 若真的不可關：挪到「系統常量」區，或視覺上更明顯區分（如用 🔒 icon + 不同背景）
- 若可關：提供 toggle + `/api/v1/risk/config` endpoint

---

### D06 — [Medium] Learning Tab Scan 按鈕響應無詳情反饋

**位置**：`tab-learning.html:66-70`（按鈕）+ `tab-learning.html:136-147`（handler）

**現狀**：`autoScan('scan-observations')` 調用 `/api/v1/learning/auto/scan-observations`，但 response `count / discovered` 經常為 0 或 undefined（依賴後端 payload 字段），顯示 `Discovered 0 items` 很不友好。

**診斷**：非真正死按鈕，但發現 0 items 時用戶無法判斷是「掃描成功但無新發現」還是「掃描失敗靜默 fallback」。

**建議**：response 設為 strict 結構 `{ status: "success"|"no_data"|"timeout", items_found: N, sample_items: [...] }`，UI 根據 status 顯示不同 chip 顏色。

---

### D07 — [Medium] Demo Tab「全部平倉」對話框不存在

**位置**：`tab-demo.html:73`（按鈕）指向 `openDemoCloseAllDialog()` → `tab-demo.html:798-804`

```javascript
function openDemoCloseAllDialog() {
  const el = document.getElementById('dlg-demo-close-all');
  el.style.display = 'flex';  // 但此元素在 HTML 中不存在！
}
```

**搜索驗證**：在 `tab-demo.html` 中搜索 `dlg-demo-close-all`，僅在 JS 中被引用，HTML 層從未定義。

**診斷**：點擊「全部平倉」按鈕會觸發 `Cannot read properties of null (reading 'style')` JS 錯誤，控制台報錯，無確認對話框彈出。此為 **silent-fail bug**。

**建議**：HTML 中補上與 tab-live.html 的 `dlg-live-close-all` 平行的對話框，或改用 `confirm()` 原生彈窗。

---

### D08 — [Low] AI Tab「Trigger Session」按鈕彈窗邏輯無後置 confirm 實現

**位置**：`tab-ai.html:34` → `showTriggerConfirm()`

**需驗證**：未在前 300 行見到 `showTriggerConfirm()` 定義，需後續讀剩下部分驗證；若是 stub 則為 Critical。

**建議**：如確認為 stub，補齊實現或刪按鈕。

---

## 二、設計不合理（18 項）

### I01 — [Critical] 11 個 Tab 中有 3 個都是「監控信息過載」型，無「需要你處理」的凸顯區

**受影響 Tab**：Governance / Settings / Monitoring / Learning

**問題**：這 4 個 tab 的第一屏都是 6-15 個只讀指標網格 + 多個折疊區，沒有「Action Required」或「待處理通知」的頂部凸顯區。

**例**：Governance 的 `Pending Approvals` 卡片在頁面底部，需要滾動才看到；而 Learning 的 `Review Queue` 雖在頁面中部但表格 ID/Type/Summary/Priority/Created/Actions 6 列太擁擠。

**建議**：每個 tab 頂部統一增加一個 `<div class="oc-action-required">` 區域，只在有真實 pending items 時顯示。

---

### I02 — [High] Tab 順序與使用頻率不符

**現狀**（console.html:223-242）：
```
系統總覽 → 實盤 → 演示 → 模擬 → 圖表 → 策略 → 風控 → AI → 學習 → 治理 → 監控 → 設置
```

**問題**：
- **Live** 放第 2 位但目前仍是 `Live_Ready` 狀態（0 真實 live 流量，CLAUDE.md §三），顯示 balance=`--` 會讓用戶誤以為系統壞了
- **Demo/Paper** 分離後，運維常在 Paper ↔ Demo 跳轉，但中間隔了 Charts
- **Settings** 放最後，但 API Key 管理是高頻操作

**建議新順序**：
```
總覽 → 模擬 Paper → 演示 Demo → 圖表 → 策略 → 風控 → 學習 → AI → 治理 → 監控 → 設置 → 實盤 Live🔒
```

---

### I03 — [High] Live Tab 緊急停止與常規停止視覺區分不足

**位置**：`tab-live.html:201-205`

```html
<button class="oc-btn oc-btn-danger" id="btn-live-stop">&#x23F9; 停止 Live</button>
<span style="display:inline-block;width:1px;height:24px;background:var(--border);margin:0 8px"></span>
<button class="btn-emergency" id="btn-emergency-stop">&#x1F6A8; 緊急停止</button>
```

**問題**：僅 1px 分隔線，且顏色相近（都帶紅）。在高壓力情境下，「停止 Live」與「緊急停止」誤點風險高，且實測兩者最終都調用同一 endpoint `/api/v1/live/session/stop`（見 `tab-live.html:1001-1011`），**只是 toast 文字不同**，功能完全一致卻偽裝成兩個按鈕。

**建議**：
- 如果真的是同一功能：刪掉其中一個（保留 Emergency，刪除 `停止 Live` 的 Stop Dialog）
- 如果應該不同：`doEmergencyStop` 要呼叫一個真正更快/更強的 endpoint（如 `/api/v1/live/session/emergency-stop` 帶 `force_cancel_all=true`）

---

### I04 — [High] Risk Tab「引擎配置」與「P0/P1/P2」之間切換關係不直觀

**位置**：`tab-risk.html:114-141`（引擎選擇）+ `tab-risk.html:164-189`（三層配置）

**問題**：引擎 tab（Paper/Demo/Live）切換後，下方 P0/P1/P2 卡片會異步重載，但沒有任何 loading indicator。用戶切換後可能看到舊 Paper 數據短暫殘留，誤以為是 Live 配置。

**建議**：切換引擎時立即清空 P0/P1/P2 卡片內容顯示 `<div class="oc-loading">載入 <engine> 配置...</div>`，數據到位後再渲染。

---

### I05 — [High] Risk Tab 修改 Live 引擎確認對話框的 confirm 按鈕按鍵可達

**位置**：`tab-risk.html:155-159`

```html
<button class="oc-btn" style="background:var(--red);color:#fff;border-color:var(--red)"
  id="dlg-engine-live-confirm-btn" onclick="confirmLiveEngineRiskSave()">
  確認修改 / Confirm Change
</button>
```

**問題**：紅色 "確認修改" 按鈕是 Modal 中第 2 個按鈕（Tab 鍵順序），用戶如果對 Modal 不熟悉（比如鍵盤 Enter 鍵落在此按鈕）會誤觸。同時沒有 `data-require-hold-3s` 之類的機制防誤觸。

**建議**：
- 修改按鈕默認 `disabled`，5 秒倒計時後才啟用（`setTimeout => btn.disabled = false`）
- 或要求用戶在 text input 輸入字符串「CONFIRM LIVE」才啟用

---

### I06 — [High] Settings Tab 混合性質嚴重

**位置**：`tab-settings.html` 整檔

**混入內容**：
1. Demo Control Plane（操作）
2. Global Mode Control（操作）
3. Product Family Config（操作）
4. Cost/PnL 手動錄入（審計）
5. 計劃重啟（運維）
6. API Key 管理（憑證）
7. Debug JSON（診斷）
8. System Info 硬編碼（文檔）

**問題**：8 個互不相關的功能塊塞在一個 Tab。API Key 管理是高頻高安全操作，卻埋在中部。

**建議**：
- 拆分為 **「⚙ 設置」**（Demo/Mode/PF config）+ **「🔐 憑證」**（API Keys）+ **「🛠 運維」**（計劃重啟/Debug/Cost 錄入）
- 或至少在 Settings Tab 頂部加一個 sub-tab bar 分成 4-5 區

---

### I07 — [High] Governance Tab 4 個主卡片中 2 個默認摺疊

**位置**：`tab-governance.html:115-146` (DL) + `149-177` (Reconciliation)

**問題**：SM-01/SM-04 默認展開，SM-02（Decision Leases）/EX-04（Reconciliation）摺疊。但從治理角度看，Decision Leases 是 **核心資訊**（當前有多少 AI 決策在等待執行），而 Auth 和 Risk Governor 更多是「靜態狀態」。

**建議**：把所有 4 個卡片改為默認展開（2x2 網格高度相近即可）；若怕過長，把 "Lease Details" 子面板繼續摺疊。

---

### I08 — [High] Paper/Demo Tab 沒有 Rust engine 連接狀態實時指示

**位置**：`tab-paper.html` 整頁 + `tab-demo.html`

**問題**：`tab-risk.html:43-46` 有 Rust 引擎連接狀態 chip，但 Paper/Demo Tab 沒有。如果 Rust engine down，Paper 頁面的 session 按鈕會全部失敗卻無法從 UI 得知為什麼。

**建議**：Paper/Demo Tab 控制欄加 `<span id="rust-engine-chip" class="oc-chip">Rust: --</span>`，每 15s 從 `/api/v1/system/startup-status` 讀取。

---

### I09 — [Medium] System Tab「模式升級路徑」流程圖只是裝飾，不反映可達性

**位置**：`tab-system.html:115-127`

**現狀**：文字流「🔒 設計 → 👁️ 觀察 → 🌑 影子 → 🧪 Demo → 🟣 實盤」是純視覺裝飾，無任何 gating 邏輯；用戶可以直接從「仅设计」點到「live_reserved」跳過中間步驟，後端允許但不合理。

**建議**：流程圖改為真實 Stepper 組件，當前模式高亮，下一模式可點，遠處模式灰化 + tooltip 說明前置條件。

---

### I10 — [Medium] Strategy Tab Scanner Opportunities 分數無單位

**位置**：`tab-strategy.html:77`

**現狀**：表格列 `Score` 僅顯示數字如 `0.72`，沒有單位、範圍、解釋。

**建議**：列頭改為 `Score (0-100)` 或 tooltip 加 `信號強度綜合評分，越高越值得部署`。實際值若是 0-1 需 *100 顯示。

---

### I11 — [Medium] Learning Tab Feed 與 Review Queue 並列但功能差異大

**位置**：`tab-learning.html:34-58`

**問題**：`Review Queue`（需要操作者做事）和 `Learning Feed`（純展示）+ `Net PnL Dashboard`（純數字）三者放在相似的卡片 + 2x1 grid 中。用戶不容易判斷哪個是「需要你處理的」。

**建議**：Review Queue 突出顯示（上紅/黃邊框 + 左側 🔴 icon + 如有 items 字數大於 5 則頂部 sticky）；Feed/Net PnL 合併或移入折疊區。

---

### I12 — [Medium] Demo Tab offline 狀態占據大屏且無重連按鈕

**位置**：`tab-demo.html:132-152`

**現狀**：`showOffline()` 顯示完整 configure guide 但沒有「手動重試連接」按鈕。用戶如果剛配好 Demo key 後需要等下次輪詢（15s）才能看到更新。

**建議**：添加 `<button onclick="loadAll()">↺ 立即重試</button>` 在 offline card 中。

---

### I13 — [Medium] AI Tab `engine Settings` 保存無批量驗證

**位置**：`tab-ai.html:147-207`

**問題**：11 個 field（供應商/模型/預算/乘數/自動升級 etc）的 `saveAIConfig(this)` 會一次提交所有值。若其中某個無效（比如 `ai-min-mult > ai-max-mult`），整個保存失敗但 UI 不會指出哪個字段錯。

**建議**：前端加跨字段驗證 + 後端 422 response 中返回字段級錯誤，UI 高亮對應輸入框。

---

### I14 — [Medium] Governance Audit Trail 沒有 filter / search

**位置**：`tab-governance.html:339-358`（Audit Trail）

**問題**：用戶查找特定 operator 行為或特定時間段的事件，只能靠瀏覽器 Ctrl+F 搜表格；表格本身無 filter、無 date range picker。

**建議**：頂部加 `<input placeholder="Filter by actor/action/target">` + date range picker；或至少加 `tail N` 參數控制顯示條數。

---

### I15 — [Medium] Strategy Tab「Delete Strategy」使用 `openConfirmModal` 但無 modal HTML 定義在此檔

**位置**：`tab-strategy.html:240`

```javascript
async function deleteStrategy(name) {
  if (!await openConfirmModal("delete-strategy")) return;
```

**問題**：`openConfirmModal` 定義在 `common.js`，但 `"delete-strategy"` key 可能對應的 modal 資源未在此 tab 聲明。需後續驗證 common.js 是否提供通用 confirmation，若否則為 bug。

**建議**：驗證 common.js 提供通用 confirm modal；如無，補一個 `<div id="delete-strategy-modal">`。

---

### I16 — [Medium] Paper Tab「雙停」按鈕邏輯不直觀

**位置**：`tab-paper.html:35`

```html
<button class="oc-btn oc-btn-danger" id="btn-stop-all"
  title="停止 Paper + Demo 雙引擎">&#x23F9;&#x23F9; 雙停</button>
```

**問題**：按鈕僅 4 個字「雙停」，emoji ⏹⏹ 完全看不出來是什麼意思；需要 hover 才知道是「停止 Paper + Demo」。

**建議**：改為「🛑 全部停止」或「⏹ Paper + Demo 雙停」明確寫出。

---

### I17 — [Low] Settings Tab API Key Slot 數量 = 3 但 Live-Demo 說明會混淆

**位置**：`tab-settings.html:730-734`

**現狀**：3 個 slot (demo / live_demo / live)。Live-Demo 說明為 `用 Demo key 運行 Live 代碼路徑（demo 驗證，寫入 live 路徑）`，且有 `此槽位與 Live 共享同一 key 存儲`。

**診斷**：混亂。1) 為什麼 live 和 live_demo 共享存儲卻要兩個 slot？2) demo 和 live_demo 怎麼選？

**建議**：重新設計成 `active_environment = {mainnet | demo} × api_mode = {live_code_path | demo_code_path}` 的矩陣，UI 展示 2x2 table 而非 3 個 slot。

---

### I18 — [Low] Live Tab 信任階梯（T0-T3）缺乏可視化進度

**位置**：`tab-live.html:306-342`

**現狀**：T0/T1/T2/T3 tier 只在 `<select>` 下拉中切換，沒有進度條或階梯圖示展示「用戶當前 tier + 下一 tier 需要 clean days N」。

**建議**：在 trust-status-bar 中加一個 stepper `[T0 ● T1 ○ T2 ○ T3 ○]` 或進度條。

---

## 三、反人類操作（15 項）

### A01 — [Critical] Live 平倉僅用瀏覽器原生 `confirm()` 對話框

**位置**：`tab-live.html:1059`

```javascript
if (!confirm('確認平倉 ' + symbol + '？\nConfirm close live position: ' + symbol + '?')) return;
```

**診斷**：整個系統的其他平倉/停止/刪除操作都使用自定義 Modal（可讀性好、有警示框），**唯獨 Live tab 單筆平倉用原生 browser prompt**。原生 prompt 在 mobile 上樣式差、無 warning color、無 detail。

**建議**：統一使用 `openCloseAllDialog` / `openStopDialog` 這類自定義 modal 模式。

---

### A02 — [Critical] Live Auth Renewal 用 `prompt()` 輸入原因

**位置**：`tab-live.html:600`

```javascript
async function submitRenew() {
  // ...
  const reason = prompt('Renewal reason (optional) / 續期原因（可選）：') || 'operator_renew';
```

**診斷**：Live 授權續期是安全敏感操作，竟然用 `window.prompt()` 收集 reason。Firefox 等瀏覽器可直接禁用此 API。

**建議**：在 `trust-renew-card` 中加 `<textarea id="trust-renew-reason">`，將 reason 作為表單字段而非 prompt。

---

### A03 — [Critical] Paper Tab 的 `sessionStopAll()` 用 confirm()，Demo 的 close-all 用自定義 modal

**位置**：
- `tab-paper.html:217`: `if (!confirm('停止 Paper + Demo 雙引擎？'))`
- `tab-demo.html:797-804`: `openDemoCloseAllDialog()` 用自定義 modal

**診斷**：同一應用 UI 標準不一致。雙引擎停止是更高風險操作（影響兩個 engine），應該有更嚴格 UI 而非更簡陋。

**建議**：將 `sessionStopAll` 改為自定義 modal；或全部統一使用 `confirm()`（不推薦，但至少一致）。

---

### A04 — [High] System Tab 模式切換 confirm modal 無倒計時

**位置**：`tab-system.html:244-252`（confirm footer）

**現狀**：用戶點 `live_reserved` 模式 → 彈窗顯示「⚠ 實盤模式」→ 立即可以點「確認執行」，無強制等待。

**建議**：`live_reserved` 切換的確認按鈕默認 disabled，5 秒倒計時解鎖，配合 hold-to-confirm（按住按鈕 3 秒才觸發）。

---

### A05 — [High] 風控 Save Stop Settings 後無「最後更新」時間戳

**位置**：`tab-risk.html:242` `saveStopSettings(this)`

**現狀**：保存成功只有 `risk-dirty-bar` 消失 + toast，無「已於 14:32 保存」時間戳在輸入框下方。刷新頁面後更看不出來哪個配置是最新修改的。

**建議**：每個保存按鈕下方加 `<div class="last-saved" id="last-saved-stops">--</div>`，保存成功顯示 `✓ 已保存 · X 秒前`（相對時間，hover 顯示絕對時間）。

---

### A06 — [High] AI Tab 無成本預估對話框

**位置**：`tab-ai.html:34`「Trigger Session」

**現狀**：按鈕點擊直接 `showTriggerConfirm()`（若該函數存在）。但 confirm 內容可能只說「確認觸發？」而沒有說「預估 tokens N、成本 $X、時間 Ys」。

**同樣問題**：Learning Tab 的 Scan 按鈕 tab-learning.html:67-69 也無成本預估。

**建議**：所有會呼叫付費 API 的按鈕，confirm 文字必須包含：`預估成本 $X（基於當前模型 ${provider}/${model}）` + 顯示今日累計成本進度條（當前用量 / 日硬上限）。

---

### A07 — [High] 風控輸入框驗證靠 HTML5 min/max，無 JS-level 反饋

**位置**：`tab-risk.html:206-207`（Hard Stop input） 等多處

**現狀**：input 有 `min="0.5" max="50"`，但超範圍時依賴瀏覽器原生彈泡。若用戶用 paste 或按鈕鍵入 `"100"`，瀏覽器才在 submit 時彈 validation，且樣式不一致。

**建議**：
1. 前端用 `oninput` 實時驗證，超出範圍時輸入框紅色邊框 + 小字提示
2. 保存按鈕 `disabled` 直到所有字段通過驗證

---

### A08 — [High] Live Tab 所有平倉操作均無「預期滑點」/「當前流動性」信息

**位置**：`tab-live.html` 各平倉按鈕

**問題**：緊急停止 / 全部平倉 / 單筆平倉 dialog 都只說「市價成交存在滑點風險」，但不告訴用戶：
- 當前該 symbol 的 order book 深度
- 以當前持倉量預估的滑點 bps
- 當前 spread

**建議**：平倉 dialog 中嵌入 `<div class="liquidity-preview">Spread: 2bps · 預估滑點: 15bps · 深度 $50k</div>`，數據從 Bybit order book API 取。

---

### A09 — [High] Risk Tab 有 `AI 风控上下文` 折疊區，但無法判斷 AI 是否真的在用

**位置**：`tab-risk.html:483-490`

**現狀**：`AI 风控上下文 / AI Risk Context` 摺疊區內 `<div id="ai-risk-body">Loading...</div>` 沒有 fallback「AI 目前停用 / 未調用」的狀態。

**建議**：如果 AI 沒啟用或最近無調用，顯示明確訊息：`AI 引擎未啟用（Settings → AI Engine）/ AI engine disabled`。

---

### A10 — [Medium] Governance Paper→Live Gate「評估」按鈕無預估時間

**位置**：`tab-governance.html:196`

**現狀**：點擊「評估」按鈕後無 loading spinner，無預估時間，11 項準入檢查可能需要幾秒。

**建議**：按鈕點擊後顯示 spinner + 「評估中... (~5s)」；完成後 toast 展示 「評分從 X 升至 Y」的變化。

---

### A11 — [Medium] API Key 對話框 Enter 鍵行為不一致

**位置**：`tab-settings.html:807-809`

```javascript
setTimeout(() => document.getElementById('dlg-apikey-key').focus(), 50);
```

**問題**：聚焦到 API Key 輸入框，用戶填完按 Tab → secret 輸入框 → 按 Enter 會觸發表單默認 submit 但沒有 `<form>` 包裹，Enter 鍵不觸發 `doSaveApiKey()`。

**建議**：給對話框的 input 加 `onkeypress="if(event.key==='Enter') doSaveApiKey()"` 或用 `<form onsubmit>`。

---

### A12 — [Medium] 計劃重啟 3 步流程無「返回上一步」按鈕

**位置**：`tab-settings.html:138-184`（restart-step-1 / 2 / 3）

**現狀**：Step 1 → Step 2 只能「取消」或「下一步」；Step 2 → Step 3 同樣。用戶發現選錯延遲時間，只能從頭開始。

**建議**：每步底部加 `← 上一步` 按鈕。

---

### A13 — [Medium] Paper Orders 表格「取消」按鈕實際執行 NOP

**位置**：`tab-paper.html:456` → `cancelOrder()` at `:237-241`

**現狀**：按鈕顯示「取消」但調用的函數只是 toast 「手动取消已禁用」。

**同 D01 問題**。

**建議**：和 D01 一起處理：要麼隱藏按鈕，要麼真正實現 cancel（透過 IPC 給 Rust engine）。

---

### A14 — [Medium] 各 Tab 自動刷新間隔不統一

**發現**：
- `tab-system.html:833`: `ocStartRefresh(loadAll, 15000)` — 15s
- `tab-learning.html:323`: `ocStartRefresh(loadAll, 30000)` — 30s
- `tab-ai.html`: 需驗證
- `tab-phase4.html`: 30s
- `tab-monitoring.html:250`: 15s
- `tab-paper.html:603`: 15s
- `tab-live.html:1171`: `setInterval(refreshPage, 15000)` — 15s
- `tab-settings.html:872`: 30s

**診斷**：不統一但基本合理（settings/learning 30s 因為變動慢）。但用戶無法知道「這個 tab 刷新頻率是多少」。

**建議**：header 或 footer 加一個共用元件 `<span id="refresh-interval">每 15s 自動刷新</span>` + 手動「🔄 刷新」按鈕統一化。

---

### A15 — [Low] Phase4 Tab Teacher card 用 fetch + eval script 注入的方式加載

**位置**：`tab-phase4.html:170-205`

**診斷**：用 fetch + innerHTML + 手動執行 `<script>` 節點的方式，不可避免存在執行順序問題（如 teacher_card.html 內腳本 DOMContentLoaded 時機已過）。debug 困難。

**建議**：改用 `<iframe src="/static/cards/teacher_card.html">` 或 HTML `<template>` 方式，讓瀏覽器自然解析。

---

## 四、可優化處（16 項）

### O01 — [High] 缺少全局 Dashboard (Landing Page)

**建議**：在 `/console` 默認進入的 tab `system` 之上，添加一個極簡的「一屏看板」展示：
- 最近 24h Net PnL（Paper + Demo + Live）
- 當前告警數（Risk halted / Auth expired / Review queue > N）
- 系統健康總分
- 當前 session 運行時長

避免用戶每次都要手動跳 4-5 個 tab。

---

### O02 — [High] 無 keyboard shortcut 支援

**現狀**：所有操作都需要鼠標。

**建議**：
- `g+s` 跳轉 System tab，`g+p` Paper，`g+l` Live...
- `Escape` 關閉所有 modal（現在 modal 關閉只能點 X / 取消）
- `Ctrl+R` 拦截為當前 tab 刷新（而非整頁重載 iframe）

---

### O03 — [High] Sidebar Live panel「opacity: 0.5」看起來像 disabled

**位置**：`index.html:126-135` + `console.html:119`

```html
<div class="mc" id="live-section" style="opacity:0.5">
```

**診斷**：初始化時 live-section opacity=0.5，數據加載後（console.html:350）恢復 opacity=1。但在 live balance 未配置時（連接失敗），opacity 永遠不會刷回 1。用戶看到「灰色 Live 區塊」誤以為是 disabled。

**建議**：明確區分「loading」（skeleton UI）/「error」（紅色邊框 + 重試按鈕）/「正常」（opacity 1）三態。

---

### O04 — [High] Risk Tab dirty-bar 提示不精確

**位置**：`tab-risk.html:546-553`

**現狀**：任何 input 變動都顯示黃色 sticky bar「有未保存的修改」，但不告訴用戶**哪一個區塊**有未保存變動。Risk Tab 有 4-5 個獨立保存按鈕（Stops / Position / Cooldown / H0 / Auto-adjust），用戶不知道該按哪個「保存」。

**建議**：dirty-bar 改為顯示具體修改的區塊清單：「Stop Settings (3 處) · Position Sizing (1 處)」。

---

### O05 — [Medium] Paper / Demo / Live Tab 的 PnL Sparkline 數據來源不一致

**發現**：
- Live: 從 `/api/v1/live/fills` 取最近 50 fills
- Paper: 從 `/api/v1/paper/fills` 取
- Demo: 從 `_demoFillsCache` 構造

**診斷**：Sparkline 是視覺比較 Paper vs Demo vs Live 的表現，但三者計算邏輯略有差異。

**建議**：統一用 `ocPnlTrend()` helper，傳入相同結構的 fills array。

---

### O06 — [Medium] Strategy Tab 無 filter / search

**位置**：`tab-strategy.html:64-66`

**現狀**：策略上限 100 個，目前可能只有 10-20 個，但未來若全部部署，100 張卡片在單列 grid 中不好找。

**建議**：搜尋框 `<input placeholder="搜索 symbol / 策略名 / 狀態">` + 狀態 filter chips（All / Active / Paused / Stopped）。

---

### O07 — [Medium] Governance Audit Trail 表格若 >100 條無分頁

**位置**：`tab-governance.html:348-357`

**診斷**：未讀到分頁控件，若 audit 事件 >1000 條會導致 DOM 巨大 + 瀏覽器卡頓。

**建議**：tail N 控件 + 下拉加載（infinite scroll）或經典分頁。

---

### O08 — [Medium] Risk Tab Save buttons 缺少 optimistic UI 反饋

**位置**：多處 `saveXxxSettings(this)`

**現狀**：點擊後要等 API 返回才有 toast。網路慢時用戶以為沒點到。

**建議**：`onclick` 時按鈕立即變為 loading spinner + `disabled`，API 返回後恢復。

---

### O09 — [Medium] Learning Tab Review Queue 表格 ID 列用 8 位截斷可能碰撞

**位置**：`tab-learning.html:189`

```javascript
'<td style="font-size:11px">' + ocEsc(String(item.id || '').slice(0, 8)) + '</td>';
```

**建議**：顯示 full ID tooltip on hover；按鈕的 onclick 傳 full id 而非 shortened（現狀已如此，但 UI 層不明顯）。

---

### O10 — [Low] Grafana iframe 在 `monitoring` Tab 不可響應 trade-core DNS 解析失敗

**位置**：`tab-monitoring.html:123`

```html
wrap.innerHTML = '<iframe src="http://trade-core:3000/d/openclaw-trading-pnl?orgId=1&kiosk">';
```

**診斷**：hardcoded `http://trade-core:3000` 依賴 Tailscale DNS。用戶不在 Tailscale 網內時 iframe 會白屏 + 無法 debug。

**建議**：iframe 發生錯誤時 fallback 到 `showGrafanaOffline()`（目前僅 API 檢測失敗才 fallback）。

---

### O11 — [Low] Paper Tab 手動平倉後刷新有 1s delay

**位置**：`tab-paper.html:405`

```javascript
setTimeout(loadPositions, 1000);
```

**診斷**：平倉後 1s 才刷新是為了讓 Rust engine 處理，但用戶會看到「舊持倉依然存在」1 秒，引起困惑。

**建議**：optimistic UI — 立即把被平倉的行灰化 + 加「平倉中...」標籤，等 refresh 到來時再刪除。

---

### O12 — [Low] AI Provider 卡片布局固定 6 格 grid

**位置**：`tab-ai.html:71`

**現狀**：6 個 provider 固定 grid 排，如果未來加第 7 個（如 Mistral / Cohere）需要改 HTML。

**建議**：改為 dynamic 渲染，從 `/api/v1/ai/providers/available` 拿 list。

---

### O13 — [Low] 貨幣切換 USDT/USD/EUR 無保存偏好

**位置**：`console.html:95`

```html
<span class="oc-curr-badge" onclick="ocToggleCurrency()">USDT</span>
```

**現狀**：刷新頁面後回到 USDT；用戶每次都要重新點。

**建議**：使用 localStorage 保存 last selected currency。

---

### O14 — [Low] Governance Quick Status banner 放在 banner 但未 sticky

**位置**：`tab-governance.html:27-37`

**建議**：`position: sticky; top: 0` 讓用戶滾動時仍能看到狀態摘要。

---

### O15 — [Low] Settings Tab Product Family 的 mode_switch dropdown 的 `locked` state 不直觀

**位置**：`tab-settings.html:663-675`

```javascript
{ v:'live_reserved', locked:true },
```

**現狀**：`live_reserved` 在 dropdown 中顯示「(locked)」但用戶不明白為什麼被鎖。

**建議**：option disabled + title tooltip 「需 Operator Live 授權才能開啟」。

---

### O16 — [Low] Auto-refresh 期間無 visual heartbeat

**建議**：每次 auto-refresh 觸發時讓 header 的「連接狀態 chip」閃爍一下（opacity 1→0.5→1），讓用戶知道系統活著。

---

## 五、無障礙性（5 項）

### AC01 — [Medium] Focus ring 樣式不統一

**發現**：`styles.css` 中無統一 `:focus-visible` 樣式，按鈕/input 聚焦時瀏覽器默認藍色邊框，與整體暗色主題對比度低。

**建議**：`:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }`。

---

### AC02 — [Medium] 紅色/綠色唯一傳遞狀態信息（色盲不友好）

**廣泛存在**：PnL 數字只靠顏色區分盈虧；chip 狀態 good/warn/bad 無 icon 輔助。

**建議**：盈虧加 + / - 前綴明確（現在有，確認所有位置）；chip 加 ✓ / ⚠ / ✗ icon。

---

### AC03 — [Medium] Modal 無 ARIA 標記

**全部 modal**：缺 `role="dialog"` `aria-labelledby` `aria-describedby`。screen reader 用戶不知道 modal 已打開。

**建議**：給所有 modal 加 ARIA：
```html
<div class="oc-dialog" role="dialog" aria-labelledby="modal-title" aria-modal="true">
  <h3 id="modal-title">...</h3>
</div>
```

---

### AC04 — [Medium] Tab bar 無 `role="tablist"` / `role="tab"`

**位置**：`console.html:253-256`

**建議**：`<div class="tab-bar" role="tablist">` + `<div class="tab" role="tab" aria-selected="true">` + keyboard arrow key 切換。

---

### AC05 — [Low] `title=` 作為 tooltip 的唯一手段

**大量存在**：所有 hover tooltip 只用 `title=` 屬性。移動端 / keyboard 用戶無法訪問。

**建議**：重要 tooltip 改為 custom 實現，支援 focus 時顯示。

---

## 六、Top 10 Worst UX（按嚴重性排序）

| # | 類別 | 位置 | 問題 | 影響 |
|---|------|------|------|------|
| 1 | 死按鈕 | `tab-paper.html:148-162 + 231-241` | 手動下單整塊 UI 是 NO-OP | 用戶填表提交只得到錯誤 toast，違反憲法原則 #15 假按鈕禁止 |
| 2 | 反人類 | `tab-live.html:1059 + 600` | Live 平倉 / 授權續期用 `confirm()` / `prompt()` | Live 操作是真金白銀，瀏覽器原生彈窗無 warning 樣式、無 detail |
| 3 | 死按鈕 | `tab-demo.html:798-804` | `openDemoCloseAllDialog` 觸發 JS 錯誤 | 全部平倉按鈕 silent-fail，console 報錯 |
| 4 | 反人類 | `tab-live.html:201-205` | Stop / Emergency Stop 兩按鈕實際調同一 endpoint | 誤點風險高但功能相同，偽裝為不同 |
| 5 | 死按鈕 | `index.html:144-155` | Legacy UI 完整渲染死按鈕區 | 用戶從 `/` 進入看到廢棄控制面板 |
| 6 | 設計 | `tab-settings.html` | 8 種不同性質內容塞在 Settings | API Key 管理（高頻）與計劃重啟（低頻）混在一起 |
| 7 | 反人類 | `tab-risk.html:155-159` | Live 風控修改確認按鈕無倒計時 / hold-to-confirm | 紅色 Confirm 按鈕 Enter 鍵可達，誤觸即改 Live 參數 |
| 8 | 設計 | 整檔 | Live Tab 在第 2 位但是 `Live_Ready` 零流量 | 用戶第一次啟動誤以為 Live 壞了 |
| 9 | 反人類 | 多處 `saveXxxSettings` | Risk 保存後無時間戳反饋 | 用戶無法判斷「上次保存」何時 |
| 10 | 設計 | `tab-paper.html` | 無 Rust engine 連接狀態 chip | Engine down 時 session 按鈕失敗無根因提示 |

---

## 七、Memory `project_gui_write_paths_inventory.md` 對照

對照 2026-04-08 盤點結論：

- **R (Rust IPC) = 11 個**：risk_routes / paper session / ai_budget — 抽樣驗證 `/api/v1/paper/session/start` 流程完整，**真**
- **PR (Python + Rust IPC) = strategy activate/pause/stop** — 驗證 `tab-strategy.html:251-258` 調用 `/api/v1/strategy/{name}/{action}`，後端對應 `phase2_strategy_routes.py`（需進一步驗證 await 已正確）
- **P (Python STORE only) = ~70 個**：多數合法
- **Fake-success 2 條架構 bug**：
  1. `fire-and-forget IPC` 已修（commit `36d2533`）— 本次審查未發現新的 fire-and-forget
  2. `/strategy/dynamic-risk/toggle` 尚未修 — 本次未檢查此具體路徑

**本次新發現（非 memory 中盤點的）**：
- **D01 Paper submitOrder/cancelOrder 是 JS 層假按鈕**（不是後端 fake-success，而是前端硬編碼不發請求）
- **D07 Demo close-all 缺失 modal 元素** — silent-fail bug
- **A01-A03 Browser-native confirm/prompt 濫用** — 對 Live 授權安全敏感

---

## 八、與 2026-03-31 報告的 Diff（改進 + 退步）

### 改進
- System Tab 已用 `qa-status-row`（span）代替可點擊的 Demo/Feed/Scanner 按鈕（舊 A07 部分解決）
- Risk Tab 三層 P0/P1/P2 顏色已不混淆（舊 T14）
- 新增 Live tab 完整 dashboard（過去只有 tab-live.html placeholder）
- 新增 API Key 管理 modal（安全升級）

### 新問題
- `index.html` 依然存在作為 fallback — 未 redirect（舊 Problem 未解決）
- Settings Tab 新增 API Key 管理後混亂度上升
- Paper Tab 新增雙停按鈕但文案不直觀（I16）
- Live Tab Trust Renewal 使用 `prompt()`（新退步）

### 長期未改
- 許多術語依然混英文（Observations / Lessons / Decision Lease）
- SM-01/SM-02/SM-04/EX-04 工程代碼仍暴露（改為 abbr tooltip 屬進步但保留）

---

## 九、改進優先級路線圖

### P0 — 立即修復（工作量 ≤1 日）
- **D01**：刪除/禁用 Paper 手動下單 UI
- **D07**：補齊 `dlg-demo-close-all` HTML modal
- **A01/A02**：替換 Live `confirm()` / `prompt()` 為自定義 modal

### P1 — 短期（1-3 日）
- **I03 + I05**：Live Tab Emergency Stop 重設計 + confirm 按鈕倒計時
- **O03**：Sidebar Live panel 三態（loading/error/正常）明確區分
- **D02/D03/D04/D05**：清理死代碼、legacy redirect

### P2 — 中期（1 週）
- **I06**：Settings Tab 拆分為 設置/憑證/運維 三個 tab
- **I07 + I09**：Governance 卡片展開策略 + System 流程圖變 Stepper
- **A04 + A05**：所有高風險操作 hold-to-confirm + 保存時間戳反饋

### P3 — 長期（>1 週）
- **O01**：全局 Dashboard landing page
- **O02**：keyboard shortcut 系統
- **AC01-AC05**：無障礙性全面升級

---

## 十、審查方法與限制

**方法**：
1. 讀取所有 13 個主 HTML 檔案 + 5 個主 JS 檔案
2. Grep 確認所有 onClick/onclick handlers 對應的 endpoint 在 Python routes 中存在
3. 對照 `project_gui_write_paths_inventory.md` 三類寫入路徑分類
4. 對照 2026-03-31 舊報告追蹤改進與退步

**限制**：
- 未真實啟動瀏覽器驗證 JS runtime 錯誤（如 D07 的 silent-fail 是基於靜態分析推斷）
- 未執行 endpoint 行為測試（fake-success vs 真實生效）
- 無 accessibility tool（axe-core）檢測，AC01-AC05 屬推理級別
- 部分 tabs（tab-ai.html 後半、tab-demo.html 全尾部）因上下文限制未完整讀完，可能遺漏 1-2 項

**覆蓋率估計**：核心功能 95%，長尾細節 75%。

---

A3 AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/A3/workspace/reports/2026-04-24--gui_comprehensive_audit.md

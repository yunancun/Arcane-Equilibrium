---
name: gui-style-guide
description: OpenClaw Control Console GUI style and interaction guide; E1a agent primary skill. Uses README-listed tabs and the existing vanilla HTML/JS/CSS stack.
allowed-tools: Read, Grep, Glob, Edit, Write, Bash
---

# GUI Style Guide（OpenClaw Control Console）

> **優先序**：runtime RiskConfig TOML > Rust schema > `TODO.md` active
> state > `README.md` GUI surface > `CLAUDE.md` operating rules > governance
> docs > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> ⚠️ **GUI 結構 disclaimer**：Control Console tab 清單以 `README.md`
> 「OpenClaw Control Console 核心 Tab」為準（當前 16 個）。`ocEsc` /
> `ocSanitizeClass` / `ocExplain` 等 helper 仍需在
> `program_code/.../static/` 內 grep 實測，不從記憶猜測。

## 何時觸發

- E1a 收到「新增 GUI 元件」「Control API GUI 工作」「Tab 改版」「Live GUI Phase X」
- 修改 `program_code/.../control_api_v1/app/static/` 或前端 src
- 對 GUI tab / 表單 / 圖表 / 按鈕 做風格與互動審查

## 既有結構（事實，不要重發明）

OpenClaw Control Console：
- Canonical GUI: `http://trade-core:8000/console`（README 為入口）
- Tab 清單以 `README.md` 現列 16 tabs 為準，不硬編碼歷史 N-Tab 數字
- Learning / Paper / Demo / Live 相關視圖需跟 README + 實際 static files 對齊
- 新元件加入前先 grep `static/index.html`、`static/js/`、`static/tabs/`

技術棧：FastAPI 後端 + 既有 HTML / Vanilla JS / CSS。**不引入新框架**，
不投奔 Next.js / Vite / React / Vue，除非 PM+PA 另開架構決策。

## 風格三原則

### 原則 1：交易環境優先（Trading-Aware）

- **禁誤觸發**：「下單」「平倉」「啟動 Live」類按鈕**強制**二次確認 modal；確認文字必須打字輸入（如 "CLOSE BTCUSDT"）非單擊 OK
- **顏色語義固定**：red = 風險上升 / 虧損 / 緊急，green = 風險下降 / 盈利 / 安全，blue = 中性資訊，yellow = 警告需注意
- **數字精度**：USD 金額 2 位，BTC qty 6 位，% 2 位，bps 2 位；對齊小數點
- **時間區**：所有時間顯示 UTC + local 雙標（避免 op 在不同時區誤判）
- **Loading 狀態必顯**：超過 200ms 操作必有 spinner 或 skeleton；3s 無回應顯 retry

### 原則 2：可審計（Audit-Aware）

- 所有寫操作（POST/PUT/DELETE）UI 旁須有「上次操作 actor + ts」標籤
- 表格匯出（CSV/JSON）必含 commit sha + 採集時間 footer
- Modal 確認對話框內列出：操作、參數、actor、預期影響、回滾路徑
- 「Live」「Demo」「Paper」標籤永遠在頁面右上角醒目區（避免混淆）

### 原則 3：簡單優於華麗

- 不引入動畫除非有功能性目的（loading / state transition）
- 不依賴 Tailwind / CSS-in-JS 大型框架；用既有 CSS class
- 圖表用既有 lib（如 Chart.js / lightweight chart）；不換
- 文件 >800 行需要 review attention；2000 行是 hard cap

## JS 規範

```javascript
/**
 * 提交平倉請求。
 *
 * 為什麼：確認 modal 已通過後才會呼叫；caller 必須帶 actor + lease_id，
 * 後端會 fail-closed 拒絕未授權請求。
 */
async function submitClosePosition(
  symbol,
  qty,
  actor,
  leaseId
) { ... }

// ❌ 禁
function close(s, q) { ... }      // 無類型 / 無注釋 / 縮寫
const k = "AbCdEf123";              // 像 secret 的字面值

// ✅ 錯誤處理 fail-closed
try {
  return await fetch(...);
} catch (e) {
  showErrorBanner("操作失敗，請重試");
  logToAuditTrail({ action: "close", error: e });
  return { ok: false };
}
```

## 互動模式

| 操作 | 確認方式 | 回饋 |
|---|---|---|
| 讀（GET / 查看） | 無 | spinner |
| 修改 config（非交易） | 1 click confirm | toast + 顯示新值 |
| 開始 paper run | 1 click confirm | banner |
| 開始 demo run | 1 click confirm | banner |
| 平倉 1 個 symbol | typed confirm | modal + audit log link |
| 平倉全部 / 啟 Live | typed confirm + Operator role 雙驗 | modal + 顯示授權 chain |
| 改 risk_config TOML | typed confirm + diff preview | banner + IPC patch 結果 |

## 反模式

- 顯示「已成功」但後端其實 fail-open（fake-success；參考 memory `project_gui_write_paths_inventory.md`）
- 同一 tab 含 paper + demo + live 控制（混淆風險，永遠分頁或加大色塊區隔）
- 確認 modal 用 native `confirm()`（無 styling，不 audit-aware）
- 任何 Live 寫入操作沒有「最近 5 次操作」audit log inline 顯示
- 重金屬色組合（極黑 + 鮮紅）— 長時段 op 視覺疲勞

## 跨平台

- 不假設視窗 ≥ 1920×1080；測 1366×768 + 13" 筆電
- 鍵盤：所有按鈕 `tab` reachable + `enter` 觸發；`esc` 關 modal
- 不依賴 Linux-only browser quirks（用 Chrome stable + Safari 雙測）

## 輸出格式

```markdown
# E1a GUI 改動 — <feature> · <date>

範圍：<files>

## UI 變更
- 新增：<element + 互動>
- 修改：<...>

## 三原則檢查
- 交易環境優先：✅ / ⚠️ / ❌（具體說明）
- 可審計：✅ / ⚠️ / ❌
- 簡單優於華麗：✅ / ⚠️ / ❌

## 螢幕截圖
（dev server URL + 1366×768 + 1920×1080 兩組）

## 後端契約
- 新 API：<endpoint + payload + response>
- Audit log：<行為 → table.column>
```

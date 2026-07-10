# E1a — GUI P0.3 批次 B1(非資金 A)· 2026-07-10

STATUS: DONE(B1 非資金 A 落地;2 檔改動 + 3 檔 NO-OP;node --check 全綠;DoD grep 清零;guard 續綠)

範圍:`static/` 下 `tab-replay.html`、`tab-monitoring.html`、`tab-system.html`、
`tab-settings.html`、`app-actions.js`。spec-of-record = `design/06_numerics.md`。
B0 契約(commit 1f85b382d)已親讀確認可用:`ocBalance/ocMoney/ocNum/...` +
`oc-utilities.css §C .val-*/.num-key/.unit/.side-badge` 皆在。

---

## 1 · 每檔改動點

### tab-replay.html — NO-OP
純 subtab 容器(header + note + `#subtab-replay-disabled-card`),數值由 `app-paper.js`
的 `OpenClawReplaySubtab` 渲染(屬 B5-D,不在 B1)。本檔零 `.toFixed`/`%`/bps/數值 cell。

### tab-monitoring.html — 6 處 `.num`
KPI tile 計數/時間戳掛 `.num`(mono+tabular+右對齊;15s 輪詢會 tick,tabular 防寬度抖動):
| 行 | id | 語義 | 動作 |
|---|---|---|---|
| 68 | `pipe-ticks` | Tick Count 計數 | +`num` |
| 69 | `pipe-intents` | Intent Count 計數 | +`num` |
| 70 | `pipe-last` | Last Tick 時間戳 | +`num` |
| 80 | `tg-sent` | Messages Sent 計數 | +`num` |
| 81 | `tg-failed` | Failed 計數 | +`num` |
| 82 | `tg-last` | Last Sent 時間戳 | +`num` |

未動:`pipe-status`/`tg-status`/`oc-status`(狀態字串,className 被 JS 整串重寫,鐵則二);
`oc-agents`/`oc-channels`(「N agent(s)」計數+單位詞 — 見 §5 deferred)。

### tab-system.html — 2 處 formatter 轉換 + 6 處 `.num`
- **244** `b-cost`(今日 AI 成本):class +`num`;**1010** JS `'$'+today_cost.toFixed(4)` →
  `ocBalance(costD.data.today_cost, 4)`。**4dp column 例外**(見 §4)。
- **245** `b-cost30`(30 天 AI 成本):class +`num`;**1011** JS `'$'+total_cost_30d.toFixed(2)` →
  `ocBalance(costD.data.total_cost_30d)`(契約預設 2dp)。
- **246/247/248** `b-orders`/`b-positions`/`b-strategies`(計數):class +`num`(純排版,見 §6 邊界)。
- **912** `loadHealth()` 健康分數 cell:template class +`num`(`oc-metric-val fs-title num ' + cls`)。

未動:**243/1003** `b-pnl`(模擬淨 PnL)= paper 交易 PnL,已用 `ocMoney`,className 被 JS
重寫且屬 B5-D gated → 完整留待 B5-D 上第二通道(見 §6)。**611-612** progress-bar
`bar.style.width = progress.toFixed(0)+'%'` = 幾何寬度非資料顯示,依指令留原樣。

### tab-settings.html — NO-OP
全 `oc-metric-val` 為狀態字串(Demo State/System Mode `read_only`/Execution State
`disabled`/…);唯一數值字面 `531 Max Retries: 0` 為**靜態安全常數**(非 live-data、
不 tick、非數值欄),依 §3.1 判準留非 `.num`(見 §5,交 E2 裁決)。零 `.toFixed`/%/bps。

### app-actions.js — NO-OP
僅 `parseFloat` 解析**表單輸入值**(cost/pnl entry),非顯示渲染;零數值顯示點。

---

## 2 · `.num` 應用清單(共 12 cell)

| 檔 | cell | 類別 |
|---|---|---|
| tab-monitoring | pipe-ticks, pipe-intents, tg-sent, tg-failed | 計數 KPI |
| tab-monitoring | pipe-last, tg-last | 時間戳 KPI |
| tab-system | b-cost, b-cost30 | AI 成本額 |
| tab-system | b-orders, b-positions, b-strategies | 計數 KPI |
| tab-system | loadHealth 分數 cell(×N) | 健康分數 |

散文內數字未誤掛:tab-settings `最後更新 <ts>`(1620,散文流)、cooldown 秒數(1839,句流)
皆維持 sans、不掛 `.num`。

---

## 3 · 型別判別依據(% fraction/percent · b-cost 例外)

- **percent 型別**:B1 五檔**零 data-percent 顯示點**(全站 grep `\.toFixed(1)\+'%'` /
  `*100` 顯示 = 0)。唯一 `+'%'` 是 tab-system:612 progress-bar 幾何寬度(`bar.style.width`),
  非資料 % → 不經 `ocPct/ocPctVal`,依指令留原樣。故本批**無 fraction↔percent 消歧需求**。
- **b-cost 4dp 例外**:AI/LLM 每日成本 sub-cent 敏感;契約 2dp 會把 `$0.0034`→`$0.00`
  (canon 7 假零)。依任務裁決 column-fixed 4dp,以 formatter 出:`ocBalance(today_cost, 4)`
  (同 per-fill PnL 例外邏輯),就地中文註記已寫入。30d 聚合 = 契約預設 2dp `ocBalance(v)`。
- ocBalance 走 `ocFxConvert`+`ocCurrSymbol()`,與站上其餘金額顯示一致(取代裸 `'$'` 前綴)。

---

## 4 · 第二通道應用點

**0 處**(符合預期)。§2.2:純水位/計數/時間戳無漲跌語義 → 不加 sign/▲▼(「非資金 tab
多為計數/狀態…只在真有漲跌語義處加,不硬套」)。唯一帶方向的 `b-pnl`(paper PnL)屬
B5-D gated,本批不動。AI 成本以 `ocBalance`(無符號量值)出,無方向通道 = 正確。

---

## 5 · 判斷點(交 E2/PM 裁決)

1. **oc-agents/oc-channels(tab-monitoring 92-93)deferred**:值為「N agent(s)」計數+單位詞。
   裸掛 `.num` 會把 `agent(s)` 一併 mono 化;正解是 `<span class="num">N</span><span class="unit">…</span>`
   (§2.5),需 `ocSetText→ocSetHtml` 重構。為保 surgical + 避免本批同時引入 inline-span
   `.num` 變體,暫留原樣。低風險,可於 §C `.unit` 推廣或 P0.4 補。
2. **tab-settings:531 Max Retries `0`**:單一靜態安全常數,所在 grid 其餘皆字串
   (read_only/disabled/BLOCKED)。掛 `.num` 會孤立右對齊一個 `0`、無同欄數值可對齊、
   且非 live-data。依 §3.1「會 tick / 在欄 / 需小數對齊」判準留非 `.num`。若 E2 依 §5.1.4
   字面要求,單行補 `num` 即可(trivial)。

## 6 · 邊界(B1 vs B5-D gated)

- **b-pnl 完整留 B5-D**:paper 模擬 PnL,值格式(`ocMoney`)、色(`ocPnlClass` green/red)、
  第二通道皆屬 gated「顯示精度/第二通道變更需 QC+operator 眼證」,本批零觸碰。
- **b-orders/b-positions 已掛 `.num`**:雖源自 paper session,但**計數無精度/第二通道語義**,
  `.num` 純排版對齊(不改值、不改精度、不加色),不落 §1.5/§4.2 gating 理由;與同 grid
  的 b-cost/b-strategies 一致。透明列此,供 PM 裁;若判越界,撤 2 個 class token 即可。

---

## 7 · 驗證證據

- **node --check**:app-actions.js OK;tab-system/tab-monitoring/tab-replay/tab-settings
  各 inline `<script>` block 逐塊檢查(避免跨塊 redeclare 假陽)→ ALL OK。
- **DoD grep(§5.1)**:B1 五檔 `\.toFixed(1)\+'%'` / 裸 `+' bps'` / `>=0?'+':'-'` = **0**。
  殘留 `.toFixed` 唯 tab-system:612 progress-bar 幾何寬度(excepted)。
- **裸屬性自查**:新增 `num` class 全在 `class="…"` 內(grep 0 例外)。
- **formatter guard**:`tests/structure/test_gui_numeric_formatter_contract_static.py` 1 passed
  (未觸 common-formatters.js,契約 dp 不變)。§C spec-drift guard 未觸(未動 oc-utilities.css)。
- **viewport 證據**:Mac dev 無 live GUI/engine/data,tab 僅 `—`/offline 佔位,無法出真數據
  截圖;`.num` 右對齊+tabular 視覺變更(KPI hero 數移右緣)交 E2 於 Linux runtime + 1366×768 眼證。

## A3 必審

- b-orders/b-positions 掛 `.num`(paper 源計數,§6)是否越 B5-D 邊界 — 交 PM 裁(撤銷成本 = 2 token)。
- oc-agents/oc-channels 與 tab-settings:531 兩 deferred(§5)是否需本批補齊。
- `.num` 對 `.oc-metric-val`(label-上/value-下 tile)強制右對齊之視覺 — E2 眼證確認可接受。

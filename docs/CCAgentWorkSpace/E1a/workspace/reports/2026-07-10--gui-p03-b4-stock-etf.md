# E1a GUI P0.3 批次 B4 — stock-etf(IBKR read-only lane) · 2026-07-10

STATUS: NEAR-NO-OP(據實回報,零 source 改動)

範圍:`static/` 下 11 檔 `tab-stock-etf*.js` + `tab-stock-etf.html`
spec-of-record:`design/06_numerics.md`;B0 契約 `1f85b382d`

## 結論

stock-etf 面**無任何真數值 tabular/KPI 值格**需契約 formatter,亦**無** `.toFixed`/pct/ASCII 負號違規。
全部數值顯示落在三類——欄名 key / fallbacks 物件字面量 scaffold 預設 / `<span class="se-code">` compact 複合 debug label——皆**不**適用 `ocBps`/`ocNum`/`.num`。硬套會製造 `benchmark=0.00 bps` 冗長並錯誤右對齊複合 label。判定 **NEAR-NO-OP → 零改動**。

## 度量(B4 全檔)

| 度量 | 數 | 說明 |
|---|---|---|
| `.toFixed(N)` | 0 | 全站確認 0 處 |
| `+'%'` / pct 拼接 | 0 | 無百分比顯示 |
| `>= 0 ? '+' : '-'` ASCII 負號 | 0 | 無帶號金額顯示 |
| bps 提及 | 39 | 見下判別表:0 為 data-value cell |
| 真數值 tabular/KPI cell | 0 | `.se-metric-value` 全填 `textChip(state)` 狀態字串 |
| baseline `node --check`(11 JS) | 11/11 OK | 無改動,基線綠 |

## bps / 數值判別表(每提及 → 類別 + 動作)

判別三類:**①欄名/key**(kvRow 標籤或 object key,不動)/**②data-value cell**(單值 tabular → ocBps+.num)/**③compact 複合 label**(`se-code` 內 `key=value` packed 字串 → 保 String())。

| 位置 | 內容範例 | 類別 | 動作 |
|---|---|---|---|
| evidence-paper.js:110 `'dq.coverage_bps'` | kvRow 標籤字串 | ①欄名 | 不動 |
| evidence-paper.js:113-114 | `calendar=0 symbol=0`(se-code) | ③compact label | 保 String() |
| evidence-paper.js:200 `'shadow_cost_bps'` | kvRow 標籤 | ①欄名 | 不動 |
| evidence-paper.js:203-205 | `spread=0 slip=0 cost=0`(se-code) | ③compact label | 保 String() |
| fallbacks.js:277-278,512-519,617-622 | `psr_bps: 0,` 等物件字面量 | scaffold 結構預設 | 保留(非顯示路徑) |
| reconciliation.js:64-65 | `divergence_bps: 0,` 物件預設 | scaffold 結構預設 | 保留 |
| reconciliation.js:145-146 | `bps=0 threshold=0`(se-code) | ③compact label | 保 String() |
| scorecard-launch.js:129 `'lcbs_bps'` | kvRow 標籤 | ①欄名 | 不動 |
| scorecard-launch.js:132-133 | `benchmark=0 cost_stress=0`(se-code) | ③compact label | 保 String() |
| scorecard-launch.js:141-142 | `bps=0 max=0`(se-code) | ③compact label | 保 String() |
| scorecard-launch.js:147 `'psr_dsr_bps'` | kvRow 標籤 | ①欄名 | 不動 |
| scorecard-launch.js:150-153 | `psr=0 min_psr=0 dsr=0 min_dsr=0` | ③compact label | 保 String() |
| scorecard-launch.js:269-274 | `lcb=0 … cost_lcb=0 div=0 max_div=0` | ③compact label | 保 String() |

**為何 ③ 不需 ocBps**:`se-code` span 是 `key=value key2=value2` monospace packed 複合字串(多欄擠一格),不是單一 tabular 數值。
(a) `ocBps` 的 `2dp + ' bps'` 套上去 = `benchmark=0.00 bps cost_stress=0.00 bps`,語境冗餘(bps 單位已在 kvRow key `lcbs_bps`/`psr_dsr_bps`);
(b) `.num` 自帶 `text-align:right`,會把整條複合 label 錯誤右對齊(06_numerics §3.2「inline 文字內數字不可用 .num」);
(c) 屬 06_numerics §0.1 明列的「compact debug/scorecard label」不硬套範疇。

同理其餘非-bps compact label(counts / minor_units 金額 / notional_usd 風控caps / asof_ms 時戳)一律 ③,保 String()。

## `.num` 應用清單

**空(0 處)**。理由:此頁為 key/value 狀態儀表板,無 tabular 數值欄、無 KPI hero 數。

- `.se-metric-value`(18 格,id=`se-*-state`/`se-default-lane`):全填 `textChip(state)`/`boolChip(...)` 狀態字串,非數字 → 不掛。
- `se-denied-count`(readiness.js:169):`setChip(String(denied.length),…)` = oc-chip 徽章計數(read-only chip,P0.5 範疇)→ 不掛。
- `se-updated`(readiness.js:172):`toLocaleTimeString()` 於 chip 徽章 → 不掛。
- `event_sequence`(evidence-paper.js:260):唯一單值 `se-code`,但為 id-like sequence counter,獨處於左對齊 kv 值欄(其餘為 chip/label),掛 `.num` 會造成孤立右對齊不一致 → 不掛。

## canon 7 假零判別(`String(x || 0)`)

- **fallbacks.js 物件字面量**(`psr_bps: 0,` 等):資料結構 scaffold 預設,非顯示路徑 → 保留。
- **se-code 內 `String(x || 0)`**(~40 處):屬顯示路徑,但為 Phase 2 read-only 佔位值(上游 fallback 物件本就預設 0,`|| 0` 為 API 部分回傳時的防禦),且身處 compact 複合 debug label 而非會誤導 operator 的頭條數值格。依任務指引「scaffold 結構預設 → 保留」+ 避免把 em-dash 混入 packed `key=value` 字串 → 保留 String(x||0)。留待 Phase 2 真帳戶接線後,若升級為頭條數值格再走 OC_EMPTY。

## 驗證

1. 度量:B4 檔 `.toFixed`=0 / pct=0 / ASCII 負號=0(親跑 grep 確認)。bps 39 提及全 ①/②scaffold/③,0 為 data-value cell。
2. `node --check` 11 JS 全 OK(baseline;無改動故無新增觸碰);HTML inline 僅 `ocAuthCheck(); ocInjectBaseCSS();`,無數值邏輯。
3. **G0.5 guard 親跑:25/25 PASS**(`test_stock_etf_python_no_write_static_guard` + `_route_static_guard` + `_static_gui_guard` + `_surface_coverage_static_guard`,0.42s)。零改動 → guard 天然續綠,未觸 write path/surface coverage。
4. 裸屬性 0(無改動);新增行 0(無裸 hex);static/ 無殘留 scratch(未抽取任何暫存檔,inline 無邏輯無需抽取)。

## 自查

- 不動 IBKR fetch/授權/gate/邏輯:✓(零改動)。
- Rust/Python 權威不觸:✓。
- 兄弟髒改動不觸碰:✓。
- 未 commit:✓。
- static/ clean:✓(無 scratch 落地)。

## 異常 / 交接

無異常。B4 據實判為 NEAR-NO-OP:IBKR read-only readiness 面本質是狀態/布林/compact-debug-label 儀表板,無數值型別化 tabular/KPI 顯示,契約 formatter 與 `.num` 皆無正當落點。Phase 2 真帳戶數據接線後,若引入頭條數值格(如 cash/buying_power/PnL 獨立顯示),再走 B0 契約(ocBalance/ocMoney/ocBps + .num + OC_EMPTY)——屆時為新批次,非本 pass 遺漏。

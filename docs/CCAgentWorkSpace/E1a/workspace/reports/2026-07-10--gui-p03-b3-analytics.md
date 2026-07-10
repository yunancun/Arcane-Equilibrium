# E1a GUI 改動 — P0.3 批次 B3(analytics)· 2026-07-10

STATUS: DONE(3 檔改;canary NO-OP;node/inline-syntax 全綠;formatter+isolation+canary guard 續綠;無 static/ 殘留)

範圍(static/):`tab-strategy.html`、`tab-ai.html`、`tab-edge-gates.html`、`canary-tab.js`
spec-of-record:`docs/execution_plan/gui_redesign/design/06_numerics.md`
未動:common-formatters.js / oc-utilities.css(B0 契約沿用)、Python/Rust、兄弟髒改動。未 commit。

## 摘要
- bps 全走 `ocBps`;% 按型別走 `ocPct`(fraction)/`ocPctVal`(already-%);qty→`ocQty`;side→`ocSide`;帶方向淨值加 `.val-*`(§2.2 屬帶號水位 → 只 +/− 不加 ▲▼)。
- `tab-edge-gates.html` 泛型 `metricValue` **保留給非契約型別**(count/'x' 倍率/'m' 分鐘/rate),bps/% 逐呼叫點抽出走契約 → **bps 重複實作路徑消除**(PA finding);null 回傳 `'--'`→`OC_EMPTY`。
- `canary-tab.js` = **NO-OP**:其唯二 ratio×100 是 progress bar 的 CSS `--canary-fill-w` 寬度 + ARIA `aria-valuenow` 整數,非 data-value;threshold 為 registry 泛型值。皆非數值契約目標。
- fraction/percent 逐點分類經**後端生產者查驗**(misclassify=100× 顯示錯);揭一組同名反制陷阱:`win_rate`(fraction)vs `win_rate_24h_pct`(already-%,SQL `*100.0`)。

## fraction / percent 分類表(判定依據=後端生產者 / 欄名 / 既有 ×100)

| 檔:行 | 欄位 | 舊寫法 | 分類 | 判定依據(證據) | 動作 |
|---|---|---|---|---|---|
| edge-gates:180 | c.fee_drop_pct | metricValue(v,'%',1) | **already-%** | `prelive_edge_gate_trends.py:112` `_fee_drop_pct` 回 `…*100.0` | `ocPctVal` |
| edge-gates:181 | c.maker_like_pct | metricValue(v,'%',1) | **already-%** | `py:104` `_pct = num/den*100.0` | `ocPctVal` |
| edge-gates:231 | item.value(fee_drop/maker) | metricValue(v,'%',1) | **already-%** | 同上生產者 | `ocPctVal` |
| edge-gates:326 | row.win_rate_24h_pct | metricValue(v,'%',1) | **already-%** | SQL `py:924` `…*100.0 AS win_rate_24h_pct` | `ocPctVal` |
| edge-gates:198/324/327 | c/row.avg_net(_24h/_window)_bps | metricValue(v,' bps',2) | bps(帶方向) | `AVG(net_bps_after_fee)` `py:921/927`;可正負 | `ocBps`(+第二通道) |
| strategy:660/667 | i.confidence | (v*100).toFixed(0)+'%' | **fraction** | confidence 0-1,顯示 ×100 | `ocPct` |
| strategy:799 | eff.win_rate | `ocPct(...)`(已) | **fraction** | 既有 ocPct ×100;**B0 後驗得 2dp**(common-formatters:107-110 `(v*100).toFixed(2)`) | 驗證(僅加 .num) |
| ai:1170 | fallback_tier2_threshold_pct | (v*100).toFixed(0)+'%' | **fraction** | 預設 0.5(分數),顯示 ×100 | `ocPct` |
| ai:1172 | fallback_tier3_threshold_pct | (v*100).toFixed(0)+'%' | **fraction** | 預設 0.85,顯示 ×100 | `ocPct` |
| ai:1449 | avg kelly_fraction | (v*100).toFixed(2)+'%' | **fraction** | kelly_fraction 0-1;平均 ×100 | `ocPct` |
| ai:1465 | s.kelly_fraction | (v*100).toFixed(2)+'%' | **fraction** | ×100 顯示 | `ocPct` |
| ai:1467 | s.win_rate | (v*100).toFixed(1)+'%' | **fraction** | ×100 顯示;**與 edge-gates win_rate_24h_pct 同名不同制(已加註)** | `ocPct` |

**非-% 型別**(同區澄清,防誤判):ai:1417 `best_sharpe`=Sharpe 比率→`ocNum(_,2)`;ai:1466 `recommended_qty`=base-asset 量→`ocQty`(6dp);strategy:289 `net_funding_pnl`=帶號 PnL→`ocMoney`。

### canary-tab.js 5 pct 分類(NO-OP 逐點註明)
| 行 | 點 | 判定 | 理由 |
|---|---|---|---|
| 190 | round(ratio*100) | **N/A(ARIA)** | `aria-valuenow` 需裸整數 0-100,非顯示 data-value;套 ocPctVal 會壞 SR 語義 |
| 193 | round(ratio*100)+'%' | **N/A(CSS 寬度)** | `--canary-fill-w:NN%` 進度條寬度 plumbing(同 strategy `--fill-w`),非 data-value |
| 276/278/292 | threshold_value | **泛型 mono** | registry 值單位隨 metric 而異(可非數值),留 `<td class="mono">` 泛型 |
→ **canary 顯示層無任何 data-value % 文字**;整檔對數值契約 NO-OP,僅 node --check 過綠。

## metricValue 泛型 helper 處置(裁決 + 理由)
**裁決:保留 metricValue 給非契約型別,bps/% 逐呼叫點抽出走契約。**
- 理由:比率('x' 倍率)、時間('m' 分鐘)、計數、rate 非 §1.2 契約型別,無對應 canonical formatter;強拆只會把 `ocNum+單位` 重寫一遍無收益。抽走 bps/% 即滿足「bps 重複實作消除 + % 型別正確」的 DoD 意圖(§4.2)。
- bps 呼叫點(198/231/316/324/327)→ `ocBps`;% 呼叫點(180/181/231/326)→ `ocPctVal`。**抽走後零 metricValue 帶 ' bps'/'%' 呼叫**(grep 證實)。
- metricValue 本體:`return '--'`→`return OC_EMPTY`(canon 7);加 MODULE 級註解說明其縮限職責。
- 保留呼叫點(非契約):entry_fills/rows/bad_cells(count)、lifetime_ratio('x')、live_demo_p50_min('m')、reentry_rate/ratio(rate)、rows_24h/rows_window(count)。

## 第二通道應用點(§2;帶方向淨值)
沿 §2.2「帶號水位只 +/−、不加 ▲▼」——B3 signed 值皆為 net-edge/PnL/aggregate 之**帶號水位**(非 period-over-period delta),故 **sign + `.val-*` 色,零 ▲▼**(此為 delta 專屬,壓在 live/demo Batch D/E)。B1/B2 亦零箭頭,一致。
- edge-gates 策略表 avg_net_24h_bps(324)/avg_net_window_bps(327):`<td class="num {ocSignParts.cls}">`+`ocBps(v,true)`(§3.3 態 class 掛 td)。
- edge-gates gate-40 卡 avg_net(198):`ocSigned(c.avg_net_bps, ocBps)`(span 包裹,§3.3 span 場景)。
- strategy 7d-Effect Net PnL 卡(792/798):`ocSignParts.cls`(取代舊 green/red)+`ocMoney` 自帶 U+2212 號。
- strategy intents side 欄(664):`ocSide(i.side)` badge(取代裸 green/red + 裸 side 文字;三通道去色可辨)。
- **不加第二通道**(純水位/計數/比率):win_rate、confidence、fee_drop/maker_like %、qty、score、rows、Sharpe、ROI 'x'、kelly counts。

## 每檔度量 + `.num` 清單

### tab-edge-gates.html
- 改:metricValue null→OC_EMPTY;gate33/40 %→ocPctVal、avg_net→ocSigned;`.value num`;readinessValue %→ocPctVal、bps→ocBps;crisis/pass KPI +num;策略表 5 值格上契約 + 第二通道;bad-cell avg→ocBps。
- `.num` 新增:gate-card `.value`(全數值格)、crisis-val/pass-val KPI、策略表 avg_net_24h/rows_24h/win_rate/avg_net_window 四格。
- 度量:裸 ` bps`/`.toFixed(1)+'%'`/ASCII 負號/**metricValue bps 殘留 = 0**(grep 證實)。

### tab-strategy.html
- 改:282-284 bps→ocBps;289 net_funding_pnl→ocMoney(保 4dp 免假零);598 score +num;660 confidence→ocPct;664 side→ocSide;666 qty→ocQty;667 conf 格 +num;792/798 Net PnL 第二通道;793/795/799 Effect 卡 +num;799 win_rate 驗 2dp。
- `.num` 新增:scanner score、intents qty/confidence、Effect Fills/Net PnL/Win Rate。
- 度量:裸 bps/`.toFixed(1)+'%'`/ASCII 負號 = 0。**唯二 `.toFixed(0)` 殘留(399/400 activePct/pausedPct)= CSS `--fill-w` 寬度 plumbing,非 data-value,刻意排除**(同 canary)。

### tab-ai.html
- 改:1170/1172 threshold→ocPct;1417 Sharpe→ocNum;1449 avg kelly→ocPct(+OC_EMPTY);1465-1467 kelly 表 kelly_fraction/qty/win_rate→ocPct/ocQty/ocPct;1468 sample_size 格 +num;448/452/456 kelly KPI div +num。
- `.num` 新增:kelly KPI 3 tile、kelly 表 4 數值格。
- 度量:裸 bps 無(本檔無 bps);`.toFixed(1/2/0)+'%'` = 0;ASCII 負號 = 0;**7 toFixed 全清**。
- **邊界遵守**:ROI monitor(roi-pnl/roi-spend/ratio,paper_pnl 來源)+ AI cost 4dp `ocBalance` **未動**(已用契約 formatter;green/red 屬 status color=P0.4;且近 paper 交易值 B5/B6 gated 邊界)。

### canary-tab.js — NO-OP(見上分類表);node --check SYNTAX OK。

## 驗證(§5 DoD)
1. DoD grep(4 檔):裸 `.toFixed(1)+'%'` / 裸 bps 拼接 / ASCII 負號 / metricValue bps 殘留 = **0**(唯二 CSS `--fill-w` 的 `.toFixed(0)` 非 data-value,排除)。
2. `node --check canary-tab.js` = **OK**;3 HTML inline `<script>` 經 scratchpad `vm.Script` 語法檢查(**無抽取檔落 static/**,checker 用 vm 非落檔;跑後已刪 scratchpad checker)= **全綠(各 2 塊)**。
3. formatter 契約 guard `tests/structure/test_gui_numeric_formatter_contract_static.py` = **1 passed**(未動 common-formatters.js);`test_strategy_action_visual_isolation_static.py` + canary GUI static = **16 passed**(無回歸)。
4. 裸屬性 / 裸 hex:新增行 **0**(全 class-based,無 inline `style=`、無 `#hex`)。
5. 無假零:未知態經 formatter/OC_EMPTY 回 `—`,非 `0.00`(confidence/kelly/net_funding_pnl/avg_net 皆 null-safe)。
6. static/ 無殘留 scratch/extract/bak 檔(ls 證實 CLEAN)。

## A3 對抗自審
- **100× 誤判風險**:唯一高風險=fraction↔percent。全 % 點回溯後端生產者確認(edge-gates 三 `*_pct` 皆 `*100.0`=already-%;ai/strategy 五點皆 fraction ×100);同名 `win_rate` 兩制已源碼佐證並加註,無跨端誤植。
- **ocSigned 契約**:傳 `ocBps`(量值 formatter)非 `ocMoney`(避雙符號,符 common-formatters:158 註);null→`<span class="num val-flat">—</span>`,無假零。
- **邊界**:未越 P0.4(非數值 green/red status 留原地)、未動 paper/live/demo 交易值(B5/B6)、未動 fetch/事件/授權邏輯。
- **殘留判斷透明**:399/400 CSS `--fill-w` `.toFixed(0)` 與 canary fill-w 同類,刻意保留(整數 % 寬度),已於報告與代碼上下文標明——非漏改。

異常:無。待 E2:確認第二通道「帶號水位不加 ▲▼」之裁量與 §2.2 一致;確認 metricValue 保留(非全拆)符 §4.2 意圖。

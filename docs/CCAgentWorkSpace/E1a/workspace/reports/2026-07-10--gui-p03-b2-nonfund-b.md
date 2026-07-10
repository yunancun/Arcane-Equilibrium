# E1a GUI 改動 — P0.3 批次 B2 非資金 B(learning/earn/governance/risk)· 2026-07-10

STATUS: DONE — 核心 `fmtPctOrUnknown` 量級猜測已移除;7 檔實改(risk/governance/earn JS + tab-risk/governance/learning/earn HTML),`autonomy-posture.js` NO-OP;node --check 全綠、guard+spec-drift 續綠、DoD grep 清零。

spec-of-record:`docs/execution_plan/gui_redesign/design/06_numerics.md`。B0 契約 `1f85b382d`,B1 先例 `4d6ab4ceb`。

## 0 · 核心任務:`fmtPctOrUnknown` 量級猜測移除(§1.1)

**窮舉結果:`fmtPctOrUnknown` 全站僅 1 個定義 + 1 個呼叫點**(grep 全 static/ 確認)。
定義 risk-tab.js:521-525(已刪);呼叫點 risk-tab.js:542(drawdown,askAIStopLoss prompt 內)。

### fraction / percent 分類表(每呼叫點 + 判定依據)

| # | 呼叫點 | 值來源 | 判定 | 判定依據(欄名/來源) | 動作 |
|---|---|---|---|---|---|
| 1 | risk-tab.js:542 `- Drawdown:` | `riskStatus.drawdown_pct ?? .current_drawdown ?? .drawdown`(`/api/v1/paper/risk/status`) | **fraction** | 同檔 `loadRiskStatus()` L662-664 讀**同端點、同 3 欄**,以 `(drawdown * 100).toFixed(1) + '%'` 顯示 → ×100 證明底層是 fraction(0.05=5%)。原啟發式 `Math.abs(n)<=1?n*100:n` 對此欄恰好也判 fraction,但屬「碰巧對」;欄名 `*_pct` 誤導,以 runtime 用法為準。 | → `ocPct(drawdownRaw)`(fraction,內部 ×100,2dp) |

**移除方式**:刪 `fmtPctOrUnknown` arrow;在 prompt 前算 `drawdownForPrompt = Number.isFinite(Number(drawdownRaw)) ? ocPct(drawdownRaw) : 'unavailable'`。
- `'unavailable'` **刻意保留**:此函式(L505-507 註)整體設計即「後端缺值時明說 unavailable,避免餵 AI 偽造 0 值」;屬刻意 prompt 信號文案(§任務例外條款),故數值路徑走契約(`ocPct`),缺值路徑保留原文案。
- `fmtMoneyOrUnknown` / `fmtNumOrUnknown` **保留不動**:同屬 prompt-copy 助手,無量級猜測、`'unavailable'` 刻意、且刻意 **FX-free**(prompt 用裸 `$` 不轉幣別,與 stake 邏輯原值語義一致);轉 ocMoney 會引入 FX 轉換破壞 prompt 語義,故不轉。

## 1 · 每檔改動點 + 度量

### risk-tab.js(12 toFixed / 11 pct → 顯示 pct 全清)
- **核心**:刪 `fmtPctOrUnknown`(L521-525)+ 呼叫點 L542 → `ocPct`(見上表)。
- **顯示 cell fraction → `ocPct`**:`r-pressure`(原 `(pressure*100).toFixed(0)+'%'`)、`r-drawdown`(原 `.toFixed(1)+'%'`)。二者閾值 0.7/0.4/0.1/0.05 即以 fraction 比較,佐證 fraction。嚴重度色(red/yellow/green)是**風控狀態指示非盈虧符號**,保留不轉 `val-*`(P0.4);`.num` 進 JS className。
- **already-percent → `ocPctVal`**:P0 卡 `Max Single Position`;P1 卡 4 欄(drawdown/daily/total-exp/corr-exp);P2 卡 4 欄(stop-loss/take-profit/single-pos/trailing,`_p2pct` 助手);Stop Manager `s-hard`/`s-tp`/`s-trailing`/`s-drawdown`/`s-daily`;Position `s-p1-risk`(原 `.toFixed(1)+'%'`)/`s-single-pos`/`s-total-exp`/`s-corr-exp`。`?? '--'` 型別混入以 `!= null` 顯式 guard 修正(避免 `'--%'`)。
- **AI Budget block**:`--fill-w` 幾何寬度 `pct.toFixed(1)+'%'` → `.toFixed(0)`(整數寬度,除 grep 命中);MTD 文字 `pct.toFixed(1)+'%'` → `ocPctVal(pct)`;`$` 金額為 AI 預算 USD 散文保留。
- **`.num` 應用(見 §2)**。
- **刻意保留(非顯示/非違規)**:`fmtMoney/NumOrUnknown`(prompt-copy,L515/519)、`in-p1-risk` `_setInput(...toFixed(1))`(可編輯 input value,非顯示)、`dr-current-risk`/`dr-base-risk`(散文 `<strong>N</strong>%`,已 2dp,inline % 在 HTML,用 formatter 會雙 %)、`Sharpe=…toFixed(2)`(比率 chip,非 %/bps)。
- 度量:`.toFixed(1)+'%'`=0、`(*100).toFixed(N)+'%'`=0、`fmtPctOrUnknown`=0(僅注釋提及)、裸 bps=0、ASCII 負號=0。

### governance-tab.js(1 toFixed / 顯示 pct 1)
- `lt-winrate`:`winRate != null ? (winRate*100).toFixed(1)+'%' : '--'` → `ocPct(winRate)`(fraction,`data.win_rate`;×100 佐證;null → `OC_EMPTY`,canon 7)。
- 度量:`.toFixed(1)+'%'`=0。
- **A3 觀察(非 B2,不動)**:L822 `Math.abs(winRate)<=1 ? winRate*100 : winRate` 仍在——但這是 **gate-eval POST payload 正規化**(`win_rate_percent` 送 `/paper-live-gate/evaluate`)**非顯示**;改它=改送後端資料=邏輯變更,超 B2 範圍(任務禁動 gate/邏輯)。標記交 QC/PM。

### earn-tab.js(4 toFixed / 3 pct)
- **already-percent APR → `ocPctVal`**:products 表 APR cell(原 `aprPct.toFixed(2)+' %'`,刪 `aprPct` 中間變數)、`_updateFormProductFields` input value、modal impact `'% APR'`、records 表 APR cell。判定依據:`estimateApr` 直接顯示為「5.00 %」且 `aprBps = estimateApr × 100 = 500bps`(=5%)佐證 already-percent(非 fraction)。
- **canon 7 假零修正**:`earn-balance-usdt`/`claimable` 原 `(x == null) ? '0.0000' : ocNum(x,4)` → `ocNum(x,4)`(ocNum null → `OC_EMPTY`,除假零)。
- **money cell 保留 `ocNum`(不轉 ocBalance)**:Earn USDT-native 收益量值,避免 ocBalance 的 FX 把 USDT 顯成當前幣別(與 stake 原值語義一致);4dp 為 sub-cent 收益精度(per-fill 類例外)。加 `.num`。
- 度量:剩 modal 散文年化 `$` 估算 `(amount*apr/100).toFixed(2)`(prose money 估算,非顯示 cell,非 grep 命中)——保留。`.toFixed(1)+'%'`=0。

### autonomy-posture.js — **NO-OP**(實測確認)
- 全檔 grep:`toFixed`=0、`%`=0、`bps`=0、`ocNum/ocMoney`=0。純 enum/白話映射/status chip/時戳文字,**無任何數值格式化點**。零改動(diff 0)。

### tab-risk.html(5 input % / 顯示 cell 走 JS)
- 加 `.num` 至**恆為數值**的 display cell:`r-peak`/`r-losses`;`s-hard`/`s-drawdown`/`s-leverage`/`s-daily`;`s-p1-risk`/`s-single-pos`/`s-total-exp`/`s-corr-exp`/`s-same-dir`;`s-cool-count`/`s-cool-min`。
- **不加 `.num`**(混文字/OFF 或純文字):`s-tp`/`s-trailing`/`s-atr`/`s-time`(可顯「關閉 / OFF」)、`s-margin-mode`/`s-position-mode`/`s-allowed-cats`、`r-halted`/`r-cooldown`(狀態文字)。
- `r-pressure`/`r-drawdown` className 由 JS 重建 → `.num` 進 JS 字串(不重複掛 HTML)。
- input `<span class="fs-dense">%</span>` 單位不動(輸入輔助非顯示值)。

### tab-governance.html(5 toFixed / 4 pct)
- inline JS drawdown 顯示:`_govSignedAuthDisplayState` + `_govLiveAuthHaltText` 的 `session_drawdown_pct`/`drawdown_threshold_pct`(**already-percent**,直接顯示未 ×100)`.toFixed(2)+'%'` → `ocPctVal`(**零輸出變更**,純 formatter 集中化 + 除 raw toFixed);散文,不掛 `.num`。
- clean-days `days.toFixed(1)` → `ocNum(days,1)`(天數計數,非 %);散文。
- 加 `.num`:count cell `lease-active`/`lease-total`/`summary-incidents`/`summary-errors`/`lt-obs`;pct cell `lt-winrate`。

### tab-learning.html — 近 NO-OP(已用契約 money formatter)
- 淨 PnL grid 與 `l-score` 早已用 `ocMoney`(自帶 `+/−` U+2212 符號=第二通道)/`ocBalance(,4)`;無 raw toFixed/%/bps。
- B2 增量:加 `.num`(4 revenue cell + score);盈虧色沿用 `ocPnlClass`(green/red 舊 token)留 P0.4 遷 `val-*`(§6 邊界:不做全站舊色遷移)。

### tab-earn.html
- 加 `.num`:`earn-balance-usdt`/`earn-balance-claimable`。表格 data cell 的 `.num` 由 earn-tab.js 生成的 `<td class="num">` 承載(header/結構不掛)。

## 2 · `.num` 應用清單(data-value,散文未誤掛)

| 檔 | cell | 類型 |
|---|---|---|
| risk-tab.js(JS className) | `r-pressure` `r-drawdown` | fraction %(重建 className) |
| risk-tab.js(生成 HTML) | P0 `Max Single Position`;P1 8 欄;P2 5 欄 | config %/count/ratio |
| tab-risk.html | `r-peak` `r-losses` `s-hard` `s-drawdown` `s-leverage` `s-daily` `s-p1-risk` `s-single-pos` `s-total-exp` `s-corr-exp` `s-same-dir` `s-cool-count` `s-cool-min` | 恆數值 KPI/config |
| tab-governance.html | `lease-active` `lease-total` `summary-incidents` `summary-errors` `lt-obs` `lt-winrate` | count/% |
| tab-learning.html | 4 revenue cell + `l-score` | money(ocMoney/ocBalance) |
| tab-earn.html | `earn-balance-usdt` `earn-balance-claimable` | USDT 量值 |
| earn-tab.js(生成 `<td>`) | products APR/minStake/maxStake;positions amount/totalPnl/claimableYield;records amount/APR | %/money(USDT-native) |

**散文未誤掛**:risk `dr-current-risk`/`dr-base-risk`(`<strong>`inline 於句流)、gov drawdown/clean-days 散文、AI budget MTD 文字、earn 記錄時戳、`s-tp/s-trailing/s-atr/s-time`(混 OFF)、mode/cats 文字——皆**不掛** `.num`。

## 3 · 第二通道應用點清單(§2)

- **本批第二通道 = 0 處主動新增**(承 B1「第二通道 0 處」判斷),理由逐項:
  - risk:pressure/drawdown/config-limits 皆**水位/上限**(帶嚴重度色但非帶向 delta),§2.2 明令水位不加 ▲▼;無 PnL。
  - governance:全 count/status/tier,無帶向數值。
  - earn:`totalPnl`/`claimableYield` 為 Earn 利息 **≥0 的收益量值(水位,只增不減)**,依 §2.2「水位不加 ▲▼/sign」→ 不硬套 `val-*`;`.num` 對齊即可。
  - learning:PnL 用 `ocMoney` **已內建 `+/−`(U+2212)符號通道**(=第二通道 sign),色沿用 `ocPnlClass`(P0.4 遷 `val-*`);未再疊加箭頭(水位型 revenue 非 delta)。

## 4 · 驗證(§5 DoD)

1. **度量**:B2 七實改檔 `.toFixed(1)+'%'`=0、`(*100).toFixed(N)+'%'`=0、`fmtPctOrUnknown`=0(僅 1 注釋提及)、裸 `+' bps'`=0、`>=0?'+':'-'`=0。剩餘 `.toFixed` 全為刻意非顯示(prompt-copy/input-value/散文-inline-%/Sharpe-ratio/幾何寬度/prose-$),逐一列 §1。
2. **node --check**:`risk-tab.js`/`governance-tab.js`/`earn-tab.js`/`autonomy-posture.js` 全 OK;4 觸碰 HTML 的 inline `<script>` 全數抽出 node --check OK(governance 2 / learning 3 / risk 2 / earn 3 塊)。
3. **fraction/percent 分類表**:見 §0(fmtPctOrUnknown 唯一呼叫點 = fraction,附 runtime 佐證);其餘 already-percent/fraction 判定逐點列 §1。
4. **第二通道 / `.num`**:見 §2/§3。
5. **裸屬性 0**:所有 `num` 皆在 `class="…"` 內或 JS class 字串內(self-check grep 0 例外);新增行**零裸 hex**(未加任何色值);**無假零**(earn 餘額 `'0.0000'` → `OC_EMPTY`;risk pressure/drawdown 沿用既有 `|| 0` 資料層預設,非我引入)。
6. **guard 續綠**:`test_gui_numeric_formatter_contract_static` 1 passed;`test_gui_utilities_spec_drift_static` + `test_gui_tokens_root_fork_static` 4 passed。

## 5 · 邊界 / 未動

- **不動**:任何 risk 邏輯/fetch/授權/de-escalation/gate/事件(僅格式化顯示值);Python/Rust;live/demo/paper 交易數值(B5/B6 gated);兄弟髒改動;`ocPnlClass` 共享 helper(green/red 留 P0.4);未 commit。
- **A3 交 QC/PM**:governance-tab.js:822 gate-eval payload 的 `Math.abs<=1` 量級猜測仍在,屬**資料正規化非顯示**(改它=改送後端),刻意留範圍外。
- **E2 眼證項**:`.num`(mono+tabular+右對齊)對 `oc-metric-val` tile 之視覺(值右緣)交 E2 於 1366×768 + Linux runtime 確認可接受(同 B1 交接)。config echo `+ '%'` → 2dp(如 "20%"→"20.00%")屬 §5.1「percent 一律 2dp」刻意變更。

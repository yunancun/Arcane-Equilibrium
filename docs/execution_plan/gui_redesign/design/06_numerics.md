# 06 — 數值排版契約(P0.3 numeric-typography pass · spec-of-record)

> P0.3 是**設計敏感的全站數值 pass**,非 P0.2 的機械清理。本檔為 P0.3 全批
> 的唯一 spec-of-record;批次 B0-E 的 E1a 一律按本檔 formatter 契約、第二通道
> 規則、`.num` 應用規則執行。契約變更走 §8 append-only,不得原地改寫。
>
> 上游:GUI-DESIGN-WORKING-DOC.md canon 3(數字 mono+tabular+第二通道+精度)
> 、canon 7(數據態不塌縮)/ tokens.css(`.num` 原子)/ design/01_typography.md
> §3(NUMERICS)/ design/03_copy.md §1.4·§4(numeric voice + 狀態文案)。
> 姊妹檔:design/05_utilities.md(P0.2 詞彙表,`.val-*` 已在其 §22 註記預留給本檔)。

---

## 0 · 範圍與度量

### 0.1 P0.3 擁有 / 不擁有

| P0.3 擁有(本檔) | P0.3 不擁有(邊界見 §6) |
|---|---|
| 精度紀律:每個數值型別綁死 dp 的 canonical formatter 契約 | 色 token 收斂(舊 `green`/`red`/`var(--green)`→`--pos`/`--neg`)= P0.4 |
| fraction↔percent 語義消歧(1dp→2dp、`(v*100)` 陷阱) | 半徑 / chrome / 非數值 chip 中性化 = P0.4 |
| 第二通道:sign(`+`/`−` U+2212)、▲▼、LONG/SHORT、`.val-*` class 落地 | 純視覺 tabular-nums(已由 tokens.css `.num` 原子給,P0.3 只負責「掛上去」) |
| no-data / stale / blocked 態的 formatter 回傳(canon 7,不假 `0.00`) | 容器層 loading skeleton / freshness badge(canon 7 容器態,03_copy §4) |
| `.num` 應用規則 + 第二通道 class 組合約定 | i18n/label 機制(03_copy 領域) |

### 0.2 現況度量(2026-07-10 盤點,`static/` 全站)

工作目錄根:`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`

- `.toFixed(N)` 全站 121 處,dp 分佈:`2`×52 / `1`×33 / `4`×24 / `0`×10 / `6`×2。
  熱點檔:`tab-live.js`×24、`common-formatters.js`×19、`app-paper.js`×13、`risk-tab.js`×12、`tab-demo.html`×10。
- **`.toFixed(1)`×33 是最大違規源**——絕大多數是百分比 1dp(canon 3 要 2dp)。
- **percent 有兩套互斥慣例**(本 pass 最大語義陷阱):
  - **fraction 輸入**(`0.184`→`18.4%`):`ocPct`、`ocFormatPerformanceMetric` 的 `unit==='rate'`、
    及散落的手寫 `(v*100).toFixed(1)+'%'`(governance-tab / tab-live / risk-tab / tab-ai / tab-demo / tab-strategy 多處)。
  - **already-percent 輸入**(`18.4`→`18.40%`):`unit==='percent'`、`p1RiskPct.toFixed(1)`、`drawdownPct.toFixed(1)`、`progress.toFixed(0)`。
  - `risk-tab.js:524` 甚至用 `(Math.abs(n)<=1 ? n*100 : n)` 自動猜測——**危險**(真實 0.5% 可能是 `0.005` 或 `0.5`),本 pass 禁此啟發式。
- **bps 有 3 套實作**:`ocFormatPerformanceMetric` bps 分支(2dp,正確)/ `app-paper.js:876` `.toFixed(0)+' bps'`(0dp 違規)/
  兩份逐字重複的自訂 helper `tab-live.js:1291 _edgeMetricValue` 與 `tab-edge-gates.html:156 metricValue`(都 `(value, suffix, decimals)`)/ 原始 `s.total_fee_bps + 'bps'`、`(x*10000).toFixed(1)+'bps'`。
- **qty(BTC/base-asset)無 canonical**:`.toFixed(6)` 全站僅 2 處且都是 **fee**,不是 qty;qty 現況散用 `ocNum(q,6)`(僅 2 處)/`ocNum(q,2)`,精度不一致。
- **第二通道基本缺席**:
  - sign:`ocMoney` 第 31 行用 **ASCII hyphen `-`**(違 canon「U+2212」);另有 7 處手寫 `v>=0?'+':''`。無 `−`。
  - 方向:`tab-live.js:804` 裸 `ocEsc(p.side)`(無色無標無箭頭);`tab-demo.html:666/734` 用 `做多/做空`+舊 `green`/`red` class;無 ▲▼、無 canonical LONG/SHORT。
  - 箭頭:全站 0 處 ▲▼ 用於數值方向。
  - 色 class:全用舊 `green`/`red`/`yellow`(非 `.val-*`/新 token)。
- **`.num` 原子未被套用於任一數據值**(24 個含 "num" 的 class 全是 `oc-input--num`/`gov-th-num`/`strat-id-num`,無一是 tokens.css `.num`)。
- **`.val-pos`/`.val-neg`/`.delta-arrow` 在 01_typography.md 只有散文設計,任何 CSS 檔皆未定義**;oc-utilities.css §22 註記已把它們 **明文 defer 給 P0.3**。
- **no-data sentinel 現況 `'--'`(兩 ASCII hyphen)**,canon 7 要 em-dash `—`(U+2014);有 8 處程式碼 `=== '--'` 比對(多為輸入 guard,一處 `tab-live.js:1489` 是輸出鏈式比對→改 sentinel 有小 blast,見 §1.4)。

---

## 1 · 精度紀律 formatter 契約(問題 1)

### 1.1 裁決:改 `ocPct` 就地,不新增 `ocPct2`

- `ocPct` **唯一真實消費點 = `tab-strategy.html:795`(Win Rate)**(其餘引用皆是 doc 註解)。就地把 `1dp→2dp`
  blast radius = 1 格已知 cell,而 Win Rate 本就受益於 2dp。**新增 `ocPct2` 會製造混淆孿生名、且無收益**。
- 但 percent 的 **fraction↔percent 陷阱必須靠型別分開**,不能靠猜。故:
  - `ocPct(frac)` **保留 fraction 語義**(內部 `×100`)——保護既有 1 消費點與所有「rate/fraction」呼叫;僅改 dp。
  - **新增 `ocPctVal(pct)`**——輸入已是 percent 數(不 `×100`),給 `p1RiskPct`/`drawdownPct×100 後`/`progress` 這類 already-percent 手寫點的歸宿。
- **禁 `risk-tab.js:524` 式 magnitude 猜測**;呼叫端必須知道自己拿的是 fraction 還是 percent,選對 helper。

### 1.2 最終 formatter 契約表(名 / 精度 / 用途 / 現況映射)

> 命名沿用 `oc*` 慣例。**「顯示精度變更,非計算變更」**:下表 dp 只改渲染,底層值(Rust engine / DB / IPC 真值)一律不動;
> `ocPct` 由 1dp→2dp 只是多顯一位,`ocMoney` hyphen→minus 純字形,em-dash 純 no-data 字形。唯一需 operator/QC 知悉的
> 是 live/demo tab 上 4dp→2dp 的 PnL/價格顯示收斂(見 §1.5 + §4 Batch D/E)。

| Formatter | dp | 輸入語義 | 符號 | 未知態回傳 | 現況映射 / 動作 |
|---|---|---|---|---|---|
| `ocMoney(v)` | **2** | 帶符號 PnL 金額(FX 轉換後之當前幣別) | `+`/`−`(U+2212) | `OC_EMPTY` | **就地修**:ASCII `-`→U+2212;預設 dp 維持 2 |
| `ocBalance(v)` | **2** | 金額量值(無符號,FX 轉換後) | 無 | `OC_EMPTY` | 保留=USD/USDT 無符號 canonical |
| `ocQty(v)` | **6** | base-asset 數量(BTC/coin qty) | 無 | `OC_EMPTY` | **新增**;取代散落 `ocNum(q,6)`/`ocNum(q,2)`;不加千分位 |
| `ocPrice(v[,dp])` | **2**(≥1)/ 4-6(<1,column-fixed) | 標的價格 | 無 | `OC_EMPTY` | **新增薄封裝**=`ocNum(v,dp)` 之語義別名(利 grep);取代 `ocNum(p,2)`×24 |
| `ocPct(frac)` | **2** | **fraction**(`0.184`,內部 `×100`) | 可選 `+`/`−` | `OC_EMPTY` | **就地改 1dp→2dp**(1 消費點) |
| `ocPctVal(pct)` | **2** | **already-percent**(`18.4`,不 `×100`) | 可選 | `OC_EMPTY` | **新增**;already-% 手寫點歸宿 |
| `ocBps(v[,signed])` | **2** | bps 數 | 可選 `+`/`−` | `OC_EMPTY` | **新增**;合併 `ocFormatPerformanceMetric` bps 分支 + `_edgeMetricValue` + `metricValue` + 原始 bps 拼接 |
| `ocNum(v,dp)` | 呼叫端指定 | 泛型逃生口:count/ratio/id/非型別化數 | 無 | `OC_EMPTY` | 保留;不再用於「有型別」的價/量/率(那些走上面) |

**凍結(不新增呼叫者,所屬批次遷出):**
- `ocAmount(v[,dp])` — 變動精度(2 或 4 依量級)違「column-fixed dp」,且 `v<=0` 隱藏語義夾帶。9 個消費點按語境遷 `ocQty`(量)或 `ocBalance`(額);其 `v<=0` 隱藏語義如仍需,由呼叫端顯式 guard。P0.4 複審後刪。

**型別分派 helper(既有,對齊本契約):**
- `ocFormatPerformanceMetric(metric)` — 其 `unit` 分派內部改調本契約:`bps`→`ocBps`、`rate`→`ocPct`(fraction,2dp)、`percent`→`ocPctVal`、`money/usdt`→`ocMoney`、`money_abs`→`ocBalance`。**消除其 `rate` 分支的 1dp**。

### 1.3 USD / BTC / bps 對應總結(問題 1 明列)

- **USD / USDT**:量值→`ocBalance`(2dp,無符號);帶符號 PnL→`ocMoney`(2dp,U+2212)。**皆 2dp,canon**。
- **BTC / base-asset qty**:→`ocQty`(**6dp**,無千分位)。每標的 step 若 <6 位有效,column 可傳更小 dp,但**預設 6**。
- **bps**:→`ocBps`(**2dp** + ` bps`)。三份重複實作全歸一。

### 1.4 未知 / stale / blocked 態(canon 7)—— formatter 回傳

- **canonical no-data 常數 `OC_EMPTY = '—'`(U+2014 em-dash)**,取代現行 `'--'`。所有 formatter 對 `null / NaN / undefined` 回 `OC_EMPTY`。**永不回 `0.00`**(canon 7 假零)。
- **stale / loading / blocked 不是 formatter 的職責**——它們是**容器態**(canon 7 / 03_copy §4):
  - loading = row-height skeleton(容器,無文字);
  - stale = **真值** + `.is-stale`(dim 50%)+ freshness badge + last-updated ts(容器);
  - blocked/not-collected = 明文 label(如 IBKR「帳戶未連線 · 待 Phase 2」,容器);
  - contract-violation = loud banner(容器)。
  formatter 只在**真的沒有值**時回 `OC_EMPTY`;有值就照精度渲染,態由容器疊加。
- **sentinel 遷移安全**(解 8 處 `=== '--'` blast):新增 `ocIsBlank(v)`(對 `null / '' / '--' / '—'` 皆 true)。
  Batch B0 把 8 處輸入-guard 比對改走 `ocIsBlank()`——此為 **sentinel-agnostic 化,非顯示精度變更**,故可在 B0 跨檔一次做(含 trading 檔的 guard,因不改任何 live 顯示值)。
  唯 `tab-live.js:1489`(`fee !== '--' ? parseFloat…`)是**輸出鏈式**,其修正連同 live 顯示改動一起放 Batch E;在此之前 `ocIsBlank` 雙 sentinel 相容,順序無關不產生瞬態 bug。

### 1.5 LIVE 數值精度變更風險點(必標)

- **4dp→2dp 收斂**:現 13 處 `ocMoney(v,4)/ocBalance(v,4)` 與 per-fill `.toFixed(4/6)`,若無差別收 2dp,微額 PnL(如 `+0.0034`)→`+0.00` **讀似零**(canon 7 假零風險)。
- **裁決**:KPI / equity / balance / notional = **嚴格 2dp**;**per-fill 已實現 PnL 欄 + PnL-bucket 欄 = column-fixed 4dp 例外**(與「price<1 給 4-6dp」同類 column-fixed 例外),因收 2dp 會把微額成交塌成 0.00。`ocPnlCell` 維持 4dp,標為 column 例外。
- 以上落在 **live/demo tab = Batch D/E,最後做、獨立 commit、標明「顯示精度變更需 QC + operator 知悉」**(§4)。

---

## 2 · 第二通道規則(問題 2;canon 3 CVD-safe)

### 2.1 回傳結構裁決:**雙層 API**(權衡 XSS / ocEsc / 便利)

- **數字本身經 `toFixed` 產生 = 機械安全**,不含使用者/交易所字串,故無需 ocEsc;箭頭/方向詞是**固定字典字形**,亦安全。
  XSS 面只在 symbol/strategy 等外來字串——那些**仍各自走 ocEsc**,與本層無關。
- 既有慣例(`ocChip`/`ocStrategyChip`/`ocPnlCell`/`ocCategoryTag`)**回 HTML 串**;為與之一致 + 給表格 cell 靈活性,採雙層:
  - **低階 `ocSignParts(v)` → `{sign, cls, arrow}`**(純結構,無 HTML)。給需把 class 掛在 `<td>` 自身、自組 markup 的表格碼。
  - **高階 `ocSigned(v, fmtFn[, opts])` → HTML 串** `<span class="num val-pos">+1,842.30<i class="delta-arrow" aria-hidden="true"></i></span>`;`fmtFn` 傳 §1 的精度 formatter(`ocMoney`/`ocBps`/`ocPct`…),`opts.arrow=true` 才掛箭頭。數字為自產,不 ocEsc;箭頭由 **CSS `::before` content** 出(不進 HTML 串、不可選取複製進數字)。

### 2.2 sign:`+`/`−` + `.val-*`(+ 可選 ▲▼)

- 正負 → 前綴 `+` / `−`(**U+2212**,tabular 寬,與 `+` 對齊)+ `.val-pos`/`.val-neg`;零/平 → `.val-flat` + middot `·`,無箭頭。
- **▲▼ 只給「變化量 / delta」,不給「水位 / level」**(承 01_typography §3.4):
  - **要 ▲▼**:PnL delta、ROE%、價格變動%、今日淨 vs 昨日 等**帶方向的變化**。
  - **只 `+`/`−` 不加箭頭**:淨曝險(帶號但是水位)、帶號 funding rate、equity 等**量級/水位**。
  - 理由:箭頭語義是「往哪動」,水位沒有「動向」,加箭頭是誤導。

### 2.3 方向:LONG/SHORT 文字(非只綠紅)

- **`ocSide(side)` → badge HTML**:`多 LONG ▲`(`.side-badge .side-long`)/ `空 SHORT ▼`(`.side-badge .side-short`)。
  `Buy→多 LONG ▲`、`Sell→空 SHORT ▼`;未知→`OC_EMPTY`。
- 形制:**text badge**(非 pill,canon 5 資料控件不 pill;radius `--r-1`)。三通道 = 中文詞(多/空)+ 拉丁 token(LONG/SHORT,Mode B 常駐)+ 箭頭(▲▼)+ 色(long=`--pos` hue / short=`--neg` hue)。
- **色只是「方向約定」不是「盈虧」**:long 綠 / short 紅是方向習慣,已被 多/空 + LONG/SHORT + ▲▼ 三通道去色後仍可辨,故不與 PnL 盈虧色衝突(它們在不同欄)。

### 2.4 grayscale-survivable 自檢(CVD-safe 鐵則)

去色後(灰階)必須仍可辨,以下每列各自成立:

| 語義 | 去色後留下的通道 | 通過? |
|---|---|---|
| 正 PnL | 前綴 `+` + ▲(delta) / `+`(level) | ✓ |
| 負 PnL | 前綴 `−`(U+2212) + ▼ / `−` | ✓ |
| 平 / 零 | middot `·`(或 `OC_EMPTY` 若無值) | ✓ |
| LONG | `多` + `LONG` + `▲` | ✓ |
| SHORT | `空` + `SHORT` + `▼` | ✓ |
| warn(如保證金率注意) | `⚠` + 文字(canon 10 warn 必附 ⚠) | ✓(warn 屬狀態非本數值層,但同律) |

**鐵則:色永不是唯一載體**;任一數值/方向若去色後不可辨 = 違 canon 3,E2 擋。

### 2.5 P0.3 落地的 class(E1a 依 05_utilities.md §11 append-only 追加到 oc-utilities.css 新 §C「數值第二通道」)

> 命名採 01_typography 既定的 `.val-*`(oc-utilities.css §22 已明文預留),與 `.t-pos`/`.t-neg`(純文字色)**區分**:
> `.t-*` = 一般文字著色;`.val-*` = 帶符號數值組件(色 + 預期配 sign 字形 + 可選箭頭)。

```css
/* ═══ oc-utilities.css §C 數值第二通道(P0.3;append-only)═══ */
.val-pos { color:var(--pos)!important; }
.val-neg { color:var(--neg)!important; }
.val-flat{ color:var(--text-muted)!important; }
.num-key { font-weight:var(--weight-medium)!important; }   /* 表格 row-anchor 欄升一級字重(01_typography §6.3) */

.delta-arrow{ font-size:var(--fs-micro); margin-left:4px; }
.val-pos .delta-arrow::before{ content:"▲"; }
.val-neg .delta-arrow::before{ content:"▼"; }
.val-flat .delta-arrow::before{ content:"·"; }

.unit{ font-size:var(--fs-micro); font-weight:var(--weight-regular);
       color:var(--text-muted); margin-left:4px; }
.unit.tight{ margin-left:1px; }   /* % 與 × 貼緊 */

.side-badge{ display:inline-flex; align-items:center; gap:2px;
             font-size:var(--fs-micro); font-weight:var(--weight-semi);
             border-radius:var(--r-1); padding:1px 6px; letter-spacing:var(--ls-caps); }
.side-long { color:var(--pos); background:var(--pos-bg); }
.side-short{ color:var(--neg); background:var(--neg-bg); }
```

- 色 utility 沿 oc-utilities house style 用 `!important`(壓 inline / 運行時注入 `<style>`);結構性(`content`/`margin`/`::before`)無 inline 競爭者,`!important` 可省——E1a 依 05_utilities §3 就地判。
- 箭頭走 `::before content`:**不進 HTML 串、`aria-hidden`、不可被選取複製進數字**(sign+值已對 SR/CVD 表意,箭頭是強化)。

---

## 3 · `.num` 應用規則(問題 3)

### 3.1 哪些元素掛 `.num`

- **掛**:所有 mono-tabular 資料值——表格數字格、KPI hero 數、獨立 metric 值、價/量/率/bps、column 內的 id/hash/timestamp/latency。
- **不掛**:嵌在**散文句流**中的數(`持有 3 個倉位`、`第 2 頁`)——那些留 sans、不右對齊(01_typography §3.1)。KPI tile 內的獨立 count **是資料值 → 掛 `.num`**。
- 判準:「它在欄裡 / 會 tick / 需小數對齊」→ `.num`;「它在句子裡」→ 不掛。

### 3.2 右對齊與 inline 數字

- `.num` 原子**自帶 `text-align:right`**(tokens.css)。故:
  - 表格/KPI 數值欄 → `.num`(右對齊落地)。
  - **inline 文字內的數字**(散文)→ **不可用 `.num`**(會錯誤右對齊整段);用 sans inline。
  - 已右對齊者**不再疊 `.t-right`**(重複);需左對齊的文字欄本就不是 `.num`。

### 3.3 class 組合約定(`.num` + 第二通道並存)

- 順序:**`num` 原子在前 → 態 class → 可選 key 升級**。
  - `<td class="num val-neg">−312.08<i class="delta-arrow" aria-hidden="true"></i></td>`
  - row-anchor(uPnL/淨)欄升字重:`<td class="num val-pos num-key">…</td>`。
- 態互斥:`val-pos` / `val-neg` / `val-flat` 三選一。
- `.num` 給排版原子(mono+tabular+slashed-zero+右對齊);`.val-*` 給語義色;`.delta-arrow` 給子元素;`.unit` 給尾隨單位子 span。各司其職不混。
- 表格 cell 態 class 掛 **`<td>` 自身**(用 `ocSignParts` 取 `{cls}`);包裹 span 場景用 `ocSigned` 一次產出。

---

## 4 · 應用範圍與批次計劃(問題 4)

### 4.1 全站數值渲染點(按檔群)

| 檔群 | 主要數值面 | live 資金? |
|---|---|---|
| `common-formatters.js` | 契約本體(所有 formatter + 第二通道 helper) | — |
| `oc-utilities.css` | `.val-*` / `.delta-arrow` / `.unit` / `.side-badge` 落地 | — |
| research/replay:`tab-replay.html`、`app-review.js` | 回測/復盤數值 | 否 |
| monitor/system/settings:`tab-monitoring.html`、`tab-system.html`、`tab-settings.html`、`app-actions.js` | 系統/監控指標 | 否 |
| learning/earn:`tab-learning.html`、`app-learning.js`、`earn-tab.js`、`tab-earn.html` | 學習/理財數值 | 否 |
| governance/risk:`governance-tab.js`、`tab-governance.html`、`risk-tab.js`、`tab-risk.html`、`autonomy-posture.js` | 風控/治理%與 bps(唯讀) | 否(唯讀) |
| analytics:`tab-strategy.html`、`tab-edge-gates.html`、`tab-ai.html`、`canary-tab.js` | 策略/edge/AI bps%(含 `ocPct` 唯一消費點、兩 bps 自訂 helper 之一) | 否 |
| stock-etf:`tab-stock-etf*.js`(11 檔) | IBKR 唯讀佔位數值 | 否(read-only) |
| **demo**:`tab-demo.html`、`app-paper.js` | **live_demo PnL/價/量** | **是(live-grade)** |
| **live**:`tab-live.js`、`tab-live.html` | **live PnL/價/量/fill**(含另一 bps 自訂 helper `_edgeMetricValue`、`ocPnlCell`、`fee !== '--'` 鏈式) | **是(真金顯示)** |

### 4.2 批次表(承 P0.2「先契約後逐 tab」模型;trading 最後且 gated)

> 批次編號 `P0.3-B*` 以免與 P0.2 的 batch 1-8 混淆。每批 = 檔案互不重疊的獨立 commit(rollback 單位)。

| 批次 | 範圍 | 內容 | 可驗 checkpoint |
|---|---|---|---|
| **B0 契約落地**(先) | `common-formatters.js` + `oc-utilities.css` + `ocIsBlank` guard 8 處(除 tab-live:1489) | 新增 `ocQty/ocBps/ocPctVal/ocPrice/ocSignParts/ocSigned/ocSide/OC_EMPTY/ocIsBlank`;`ocPct`→2dp;`ocMoney` hyphen→U+2212;`ocFormatPerformanceMetric` 分派對齊;落 `.val-*/.delta-arrow/.unit/.side-badge` CSS。**零 tab 應用**(惰性,如 P0.2 B1) | `node --check` 全綠;§5 guard 測試 PASS;grep 確認新 helper 存在;無 tab 顯示改動 |
| **B1** 非資金 A | research/replay + monitor/system/settings + `app-actions.js` | 逐點 `.toFixed`→契約 formatter;掛 `.num`;% 走 `ocPct`/`ocPctVal` | `node --check`;該批檔 raw `.toFixed`/`+'%'`→0;截圖第二通道在 |
| **B2** 非資金 B | learning/earn + governance/risk + `autonomy-posture.js` | 同上;risk% 用對 fraction/percent helper;bps 走 `ocBps` | 同上;`risk-tab.js:524` 猜測式移除 |
| **B3** analytics | strategy/edge-gates/ai/canary | `ocPct` 唯一消費點驗 2dp;合併 `metricValue`(tab-edge-gates)→`ocBps` | 同上;bps 自訂 helper #1 消除 |
| **B4** stock-etf | `tab-stock-etf*.js` × 11 | 唯讀佔位數值上契約(無資金,但屬 IBKR lane) | 同上 |
| **B5-D demo(gated,倒數第二)** | `tab-demo.html`、`app-paper.js` | live_demo 數值上契約;`.toFixed(0) bps`→`ocBps`(2dp);4dp→2dp 收斂(per-fill 欄保 4dp 例外) | 獨立 commit;**標「顯示精度變更需 QC 知悉」**;node --check;截圖新舊對比 |
| **B6-E live(gated,最後)** | `tab-live.js`、`tab-live.html` | live 數值上契約;合併 `_edgeMetricValue`→`ocBps`(bps helper #2 消除);`ocPnlCell` 標 4dp column 例外;修 `fee !== '--'`→`ocIsBlank`;4dp→2dp 收斂 | **獨立 commit;標「LIVE 顯示精度變更 · 需 QC + operator 知悉」**;node --check;新舊對比;QA e2e |

**排序原則**:契約先(B0)→ 非資金(B1-B4,任意序,彼此不重疊)→ demo(B5-D)→ live(B6-E)最後。理由:精度/第二通道是**顯示語義變更**,live/demo 上要 operator/QC 眼證,故壓最後、獨立 commit、可單獨 rollback。

---

## 5 · 驗證 / CI(問題 5)

### 5.1 P0.3「完成」的可驗定義(Definition of Done)

某批完成 ⇔ 該批檔案:
1. **無裸 percent 1dp**:無 `(…*100).toFixed(1)+'%'`、無 `.toFixed(1)+'%'`(percent 一律經 `ocPct`/`ocPctVal` 出 2dp)。
2. **無 ASCII-hyphen 負號**:渲染的帶號數不得用 `'-' +`;U+2212 由 formatter 保證(grep `>= 0 ? '+' : '-'` 應歸零)。
3. **bps 一律 `ocBps`**:無 `+ ' bps'` / `+'bps'` 原始拼接、無自訂 bps helper 殘留。
4. **每個資料數值 cell 帶 `.num`**;帶號者帶 `.val-*`;方向欄用 `ocSide`。
5. **無假零**:未知態回 `OC_EMPTY`(`—`),非 `0.00`。

### 5.2 guard 測試(E1a 於 B0 建,鎖精度契約)

新增 formatter guard 測試檔(仿 G0.5 guard-tests 先例),斷言鎖死契約 dp,防未來悄改:
- `ocPct(0.1234) === '12.34%'`(fraction,2dp);`ocPctVal(18.4) === '18.40%'`(already-%)。
- `ocBps(11.4) === '11.40 bps'`;`ocBps(0) === '0.00 bps'`。
- `ocQty(0.001234) === '0.001234'`(6dp,無千分位)。
- `ocMoney(-3.5)` 含 `−`(U+2212)非 `-`;`ocMoney(0)` 為 `+…`(或依 flat 規則)。
- `ocMoney(null)===OC_EMPTY`、`ocBalance(NaN)===OC_EMPTY`、`ocQty(undefined)===OC_EMPTY`(未知→em-dash,非 0.00)。
- `ocSignParts(-2).sign==='−'` 且 `.cls==='val-neg'`;`ocSide('Buy')` 含 `LONG` 與 `side-long`。

### 5.3 CI grep 守衛(P0.6 預埋,仿 05_utilities §10)

- per-migrated-file 基線:`\.toFixed\(1\)\s*\+\s*['"]%` / `\+\s*['"]\s*bps` / `>= 0 \? '\+' : '-'` 計數;某批完成即把該批檔基線降 0,**永不回升**(> 基線 = fail)。
- 反 `.num` 缺失(較弱,可選):新表格數值 cell 無 `.num` 由 E2 人審擋(自動化難,列 review 註記)。

---

## 6 · 與 P0.4 邊界(問題 6)

- **P0.3 只管數值語義正確渲染**:精度契約、fraction/percent 消歧、第二通道(sign/▲▼/LONG-SHORT)、U+2212、`.num` 應用、`.val-*` class 落地與其在**被觸碰數值 cell** 上的替換。
- **P0.3 不順手做 P0.4**:
  - 不做全站舊色 class 大遷移(`green`/`red`/`var(--green)`→`--pos`/`--neg`)。P0.3 只在**為第二通道而觸碰的數值 cell** 上把 `class="red"`→`class="num val-neg"`(這是套第二通道組件,本就 P0.3 職責);**非數值** 的 `green`/`red`(狀態點/badge 等)留給 P0.4。
  - 不做半徑 / chrome / 非數值 chip 中性化。
  - `tokens-compat.css` 舊→新 token 橋接維持;`.val-*` 直接指新 `--pos`/`--neg`(canon),不經 compat。
- 純視覺 tabular-nums 已由 tokens.css `.num` 原子給;P0.3 的工作是「把 `.num` 掛上去」+ 加語義,不重定義 `.num`。

---

## 7 · 降級 / Rollback

- 每批獨立 commit;rollback 單位 = 批次 commit `git revert`。
- **B0 是所有應用批的前置**:撤 B0 前必先撤所有已引用新 helper 的應用批(否則呼叫未定義的 `ocQty/ocBps/…` → ReferenceError)。緊急止血序:先撤應用批(恢復舊 `.toFixed`/`ocPct 1dp`),`common-formatters.js`/`oc-utilities.css` 的新增可留(惰性,新 class/fn 無害)。
- live/demo(B5-D/B6-E)獨立 commit,可單獨 revert 恢復舊顯示精度,不影響非資金批。
- `.val-*`/`.delta-arrow` 為 append-only 新增,revert 應用批後遺留於 CSS 無副作用(無元素引用即惰性)。

---

*變更記錄:2026-07-10 PA 初版(P0.3 批次 B0 前定稿)。契約/第二通道/class 變更走 §8 append-only。*

## 8 · 契約治理(跨批接口穩定性)

- 本檔 formatter 契約表(§1.2)、第二通道 class(§2.5)、`.num` 組合約定(§3.3)= **append-only**:
  新增 formatter/class 允許(檔尾追記 + 批次註記 + PA 認可);**改名 / 改精度宣告 / 刪除既有** 一律禁,直到 P0.4 統一複審(批次間的 formatter 名與 dp 就是接口)。
- oc-utilities.css §C 的新增同走 05_utilities.md §11 append-only 協議(規格與實作同 commit 追加)。

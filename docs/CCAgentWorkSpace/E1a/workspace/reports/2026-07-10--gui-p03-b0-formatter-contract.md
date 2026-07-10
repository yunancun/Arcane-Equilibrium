# E1a — GUI P0.3 批次 B0:formatter 契約落地 · 2026-07-10

STATUS: DONE(全驗證通過;零 tab 重接;spec-drift guard 續綠)

範圍(嚴格三塊 + guard 測試,惰性不重接 tab):
- `static/common-formatters.js` — 契約落地(§1.2)+ 第二通道(§2.1)+ ocIsBlank(§1.4)
- `static/oc-utilities.css` — §C 數值第二通道 CSS(§2.5 逐字)
- ocIsBlank 輸入-guard 遷移 7 處(除 tab-live:1489)
- `tests/structure/test_gui_numeric_formatter_contract_static.py` — §5.2 guard 測試(新建)

工作目錄根:`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`

---

## A. common-formatters.js 契約落地

### 頂部新增哨兵
- `const OC_EMPTY = '—'`(U+2014,真 em-dash,已驗 codepoint)
- `function ocIsBlank(v)` — 對 `null/''/'--'/'—'` 皆 true(sentinel-agnostic)

### 就地修(§1.2 表)
| formatter | 改動 |
|---|---|
| `ocMoney` | 負號 ASCII `-`→U+2212 `−`;`return '--'`→`return OC_EMPTY`;dp 維持 2 |
| `ocPct(frac)` | `.toFixed(1)`→`.toFixed(2)`(保留 fraction ×100 語義);`'--'`→`OC_EMPTY` |
| `ocBalance` | `return '--'`→`return OC_EMPTY` |
| `ocNum` | `return '--'`→`return OC_EMPTY` |
| `ocAmount` | `return '--'`→`return OC_EMPTY` + 【P0.3 凍結】註記(不新增呼叫者,P0.4 複審刪) |
| `ocFormatPerformanceMetric` | unit 分派對齊契約:`bps`→`ocBps`、`rate`→`ocPct`(fraction 2dp,消除舊 1dp)、`percent`→`ocPctVal`、`money/usdt`→`ocMoney`、`money_abs`→`ocBalance`(2dp) |

### 新增 formatter(§1.2 dp 綁死)
- `ocQty(v)` — 6dp 無千分位;blank→OC_EMPTY
- `ocBps(v[,signed])` — 2dp+` bps`;signed 帶 U+2212/`+`;負號一律 U+2212(含 unsigned 負值);blank→OC_EMPTY
- `ocPctVal(pct)` — 2dp(不 ×100);blank→OC_EMPTY
- `ocPrice(v[,dp])` — 薄封裝 `ocNum(v, dp||2)` 語義別名(利 grep)

### 第二通道(§2.1 雙層)
- `ocSignParts(v)` → `{sign, cls, arrow}`(純結構;sign=`+`/`−`(U+2212)/`·`;cls=`val-pos`/`val-neg`/`val-flat`;flat/零/無值→middot+val-flat)
- `ocSigned(v, fmtFn[, opts])` → `<span class="num val-*">sign+fmtFn(abs)[+<i class="delta-arrow" aria-hidden>]</span>`;數字自產不 ocEsc;opts.arrow=true 才掛箭頭(glyph 由 CSS ::before);null/NaN→val-flat OC_EMPTY;文件註記 fmtFn 應傳量值 formatter,勿傳 ocMoney(雙符號)
- `ocSide(side)` → badge HTML;Buy/long→`<span class="side-badge side-long">多 LONG ▲</span>`、Sell/short→`…side-short 空 SHORT ▼`;未知→OC_EMPTY

### 契約 append-only(§8)
未改任何其他 formatter 名或既有 dp 宣告;ocFormatPerformanceMetric 的 `'--'` 輸入前置返回(非 §1.4 遷移目標)刻意保留原樣(surgical)。

---

## B. oc-utilities.css §C 數值第二通道
檔尾 append-only 追加 §C 塊(§2.5 逐字):`.val-pos/.val-neg/.val-flat`(色 !important)、`.num-key`、`.delta-arrow(+::before ▲▼·)`、`.unit(+.tight)`、`.side-badge/.side-long/.side-short`。色 utility 用 !important,結構性(content/margin/::before)依 05_utilities §3 省 !important。帶批次註記。

token 依賴全部存在(tokens.css 已驗):`--pos/--pos-bg/--neg/--neg-bg/--text-muted/--weight-medium/--weight-regular/--weight-semi/--fs-micro/--r-1/--ls-caps`。

**spec-drift guard(§A↔05_utilities §4)**:§C 追加在 §B annex marker 之後,不在 §A 比對範圍;guard 續綠(見驗證 3)。§A/§B 既有行零改動。

---

## C. ocIsBlank guard 遷移(§1.4,7 處輸入-guard;不動 1489)
| 檔:行(內容匹配) | 遷移前 | 遷移後 |
|---|---|---|
| autonomy-posture.js autonomyPlainLabel | `raw == null \|\| raw === '' \|\| raw === '--'` | `ocIsBlank(raw)` |
| autonomy-posture.js autonomyPlainWithRaw | 同上 | `ocIsBlank(raw)` |
| common-formatters.js ocStrategyKey | `!raw \|\| raw === '--'` | `ocIsBlank(raw)` |
| common-formatters.js ocStrategyChip | `!raw \|\| raw === '--'` | `ocIsBlank(raw)` |
| governance-tab.js _formatValue | `val == null \|\| val === '--'` | `ocIsBlank(val)`（順帶把 '' 併入 blank，語義收斂為 no-data） |
| tab-live.js _ocRenderOwnerStrategy | `strat == null \|\| strat === '' \|\| strat === '--'` | `ocIsBlank(strat)` |
| tab-demo.html _ocRenderOwnerStrategy(inline) | 同上 | `ocIsBlank(strat)` |

- **返回值全部保留原樣**('' / '--')— 純輸入-guard sentinel-agnostic 化,非顯示改動。
- **tab-live.js:1489**(`fee !== '--' ? parseFloat…`)輸出鏈式,未動(留 Batch E)。已 sed 確認原樣。
- ocIsBlank 可用性:7 處消費頁(tab-governance / tab-ai / tab-live / tab-demo)均 `<script src=common-formatters.js>`,全域函式運行時可達。

---

## D. guard 測試(§5.2)
`tests/structure/test_gui_numeric_formatter_contract_static.py`:pytest 殼出 `node -`,注入 ocFxConvert/ocCurrSymbol stub 載入整檔,逐條斷言。node 不可用時 skip(與 node --check 同前提)。斷言結果全 PASS:

- `ocPct(0.1234)==='12.34%'` ✓ / `ocPctVal(18.4)==='18.40%'` ✓
- `ocBps(11.4)==='11.40 bps'` ✓ / `ocBps(0)==='0.00 bps'` ✓
- `ocQty(0.001234)==='0.001234'` ✓
- `ocMoney(-3.5)` 含 U+2212、不含 ASCII `-` ✓
- `OC_EMPTY==='—'`(U+2014)✓ / `ocMoney(null)/ocBalance(NaN)/ocQty(undefined)===OC_EMPTY` ✓
- `ocSignParts(-2).sign==='−'`(U+2212)、`.cls==='val-neg'` ✓;pos/flat cls ✓
- `ocSide('Buy')` 含 `LONG`+`side-long` ✓;Sell 含 SHORT+side-short ✓;未知→OC_EMPTY ✓
- `ocBps(-11.4,true)==='−11.40 bps'`、`ocBps(11.4,true)==='+11.40 bps'` ✓
- `ocIsBlank('--'/''/'—'/null)===true`、`ocIsBlank('grid_trading')===false` ✓

---

## 驗證結果
1. **node --check**:common-formatters.js / autonomy-posture.js / governance-tab.js / tab-live.js 全 OK;tab-demo.html 2 個 inline `<script>` 塊經 vm.Script 解析 0 fail。
2. **guard 測試**:`OC_FORMATTER_CONTRACT_OK`;`3 passed`(本測試 + 2 spec-drift)。
3. **spec-drift guard(§A)**:`test_gui_utilities_spec_drift_static.py` 2 測試綠(§A byte-identical 續成立)。
4. **helper 全存在/global**:OC_EMPTY/ocIsBlank/ocQty/ocBps/ocPctVal/ocPrice/ocSignParts/ocSigned/ocSide 全為頂層 `const`/`function` 宣告(browser 全域,同既有慣例);grep 確認。ocIsBlank 7 遷移正確,1489 未動。
5. **零 tab 重接自查**:git diff 過濾 `class=/val-*/.num/delta-arrow/ocQty/ocBps/ocPctVal/ocSigned/ocSide` 於 tab-live.js/tab-demo.html/governance-tab.js/autonomy-posture.js 加行 = 無;僅 ocIsBlank guard 交換。無 tab markup 掛新 class/helper。
6. **裸 hex / codepoint**:所有 static 加行零裸 hex;U+2212 真為 0x2212、OC_EMPTY 真為 0x2014、CSS ▲▼· 真 glyph(python codepoint 驗證)。

## 需 QC/知悉的顯示變更(契約落地必然,非計算變更)
- `ocPct` 1dp→2dp:唯一真消費點 `tab-strategy.html` Win Rate 多顯一位。
- `ocMoney` 負號字形 `-`→`−`(U+2212)。
- `ocFormatPerformanceMetric` 對齊的既有消費點:`rate` 1dp→2dp、`money_abs` 4dp→2dp(來源 `trading_true_metrics.py`,performance metric grid 中的絕對金額量值,含 demo/live metric grid 可能波及)。task 已預先認定 ocFormatPerformanceMetric 對齊之顯示變更 acceptable(B0 就地 formatter 修)。
- 均為顯示精度/字形變更,底層真值(Rust/DB/IPC)不動;未主動改任何 tab markup。

## 異常
- 無。repo 為 dirty 多-session worktree(大量無關檔被其他 session 改動);本任務僅觸碰 6 個 static 檔 + 1 新測試,未碰他人改動。

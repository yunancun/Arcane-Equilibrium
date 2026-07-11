# E1a — GUI 大修 P0.4 C1b(交易檔死碼 + 懸空 var)· 2026-07-11

STATUS: DONE(E1a 交付,待 E2 硬邊界親算)

範圍(§11 C1b,兩項,交易檔,skin-only):
- `static/tab-demo.html`(LiveDemo):刪 `_ocMetricPct`/`_ocMetricRatio`/`_ocMetricBps` 三死函數 + 其上方僅服務它們的過渡註釋。
- `static/tab-risk.html`(風控):`.rc-dlg-detail` 懸空 `var(--bg-card)` → `var(--bg-surface)` + 刪「P0.4 懸空原樣保留」過渡註釋。

## 1 · 死函數 0-caller 證據(刪除前)
全 static/ grep,三者各僅 1 次命中 = 自身定義,0 caller:
- `_ocMetricPct` → tab-demo.html:1219(定義,唯一)
- `_ocMetricRatio` → tab-demo.html:1224(定義,唯一)
- `_ocMetricBps` → tab-demo.html:1229(定義,唯一)
P0.3 B5/D 已把 demo 數值改走 B0 契約 formatter(loadDemoMetrics 走 ocFormatPerformanceMetric),此三本地 helper 成真死碼;與 §0.2/§5「_ocMetric×3 真死,0-caller 確認」一致。

刪除範圍 = tab-demo.html 舊 1217-1233:兩行「以下三 helper 現無呼叫者…」過渡註釋 + 三函數定義 + 一尾空行;保留 1216 空行作 `loadComparison}` 與 `loadDemoMetrics` 分隔。

## 2 · 懸空 var 解析(親證)
- `--bg-card` 全站 0 定義(grep `--bg-card:` = NO DEFINITION)⇒ 確為懸空;tokens-compat.css 僅有 `--card-bg`/`--card`(皆 `var(--bg-surface)`)與 `--card-radius`,**無** `--bg-card`。
- `--bg-surface` tokens.css 三主題皆定義:帛晝(:58 `#F8F4EB`)、玄夜(:84 `#1D1619`)、第三塊(:99 `#1D1619`)。
- 改後 static/ `var(--bg-card)` 殘留 = 0。
- 語義正確性:`--card-bg`/`--card` 官方即解析為 `--bg-surface`,故 `.rc-dlg-detail` 卡片背景的正解就是 `--bg-surface`。

## 3 · 硬邊界零邏輯改動自查(git diff)
- 僅 2 檔改動:tab-demo.html(-17/0,純刪註釋+死函數)、tab-risk.html(+2/-2,一註釋+一 var 名)。
- fetch / confirm / typed-confirm / 授權 / gate / emergency / 事件 / POST:**一字未動**。
- diff 無任何 action-handler/onclick/fetch/gate 改動(逐行核對:tab-demo 只刪一段獨立死碼區塊;tab-risk 只改 `.rc-dlg-detail` 的 comment + background 值)。
- canon 6:tab-demo 琥珀虛擬資金未觸;tab-risk 熱紅未觸(`.rc-dlg-danger`=`var(--neg)`、`.rc-btn-live-confirm`=`var(--neg)`/`#fff`、`.rc-live-warn`=`var(--live)` 全部原樣)。改動點 `.rc-dlg-detail` 是明細背景,非 real-money marker。

## 4 · 驗證(§10 DoD)
- 死函數 grep = 0(定義也刪)— PASS。
- 懸空 `--bg-card` 全站 = 0;`--bg-surface` 三主題定義親證 — PASS。
- `node --check`:tab-demo/tab-risk 各 2 個 inline `<script>` 逐塊獨立檢查(避免跨塊 const 重宣告誤報),4/4 OK;抽取檔寫 scratchpad,檢後即刪,static/ 無 .inline/.block 殘留 — PASS。
- guard 續綠親跑:`pytest test_gui_numeric_formatter_contract_static.py test_gui_utilities_spec_drift_static.py -q` → 3 passed — PASS。
- 視覺:tab-risk `.rc-dlg-detail` 原 `var(--bg-card)` 懸空 → 無效宣告 → 背景退為 transparent/繼承;現 `var(--bg-surface)` → 取得設計預期的卡面背景。屬**修正非退化**(§6 明載)。零裸 hex 新增。static/ clean。

## 5 · 明確不做(未越界)
未碰 tokens-compat 遷移(C3/C4)、半徑(C2)、hex→token(C6)、POST 量級(C8);未動 `ocPnlClass`(活碼)、其他死碼;未動 Python/Rust;未觸兄弟髒改動;未 commit。

## 交付檔
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-demo.html`
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-risk.html`

next:E2 硬邊界親算(0-caller + IDENTICAL truth-table)。

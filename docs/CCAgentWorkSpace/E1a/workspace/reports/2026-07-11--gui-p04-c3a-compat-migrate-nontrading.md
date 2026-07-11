# E1a — GUI P0.4 C3a：tokens-compat 遷移(非交易 tab)· 2026-07-11

STATUS: PASS

範圍：13 個非交易 tab HTML,舊 token 名 → canonical 新名(§1.2 映射,純機械 computed-identical)。
工作目錄:`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`

## 做法

- 對每檔逐舊名施 boundary-preserving 替換:`var(--OLD[,)]` → `var(--NEW[,)]`(perl,`([,)])` 捕捉並還原邊界)。
- `var(--OLD, fallback)` → `var(--NEW, fallback)`:token 名遷移,**fallback hex 原樣保留**(屬 C6,本批不動)。
- `--blue` → `--text-secondary`(§1.3:機械 identical,不升 --accent);本批 13 檔無 `--red`(交易關鍵集中在 C4),
  故無 canon6 --live 爭議點需 defer。
- boundary `[,)]` 保證順序無關且無 prefix 誤傷(`var(--text-dim)` 不被 `--text` 命中;新名不被任何舊名 re-match)。

## 13 檔舊名前後計數表

| 檔 | 前(舊名) | 後(舊名) | 該檔命中舊名明細(前) |
|---|---|---|---|
| tab-earn.html | 31 | 0 | bg1 card-bg1 border4 text4 text-dim7 green4 red7 yellow2 card-radius1 |
| tab-agents.html | 20 | 0 | card-bg3 border5 text2 text-dim3 red3 yellow1 blue1 card-radius2 |
| tab-ai.html | 19 | 0 | bg3 border1 text2 text-dim8 green2 red2 yellow1 |
| tab-system.html | 18 | 0 | bg3 border5 text3 text-dim5 green1 red1 |
| tab-edge-gates.html | 14 | 0 | bg2 card-bg1 border3 text3 text-dim5 |
| tab-settings.html | 12 | 0 | bg2 text4 text-dim4 green1 yellow1(含 1 fallback `--yellow,#f0c040`) |
| tab-stock-etf.html | 11 | 0 | bg1 card-bg2 border2 text1 text-dim5 |
| tab-development.html | 11 | 0 | bg1 card-bg1 border2 text3 text-dim4 |
| tab-learning.html | 6 | 0 | border1 text2 text-dim1 blue1 card-radius1 |
| tab-phase4.html | 5 | 0 | border5(全 5 為 fallback `--border,#30363d`) |
| tab-monitoring.html | 5 | 0 | bg1 border1 text1 text-dim1 card-radius1 |
| tab-strategy.html | 3 | 0 | bg3 |
| tab-replay.html | 3 | 0 | card-bg1 text1 text-dim1 |
| **合計** | **158** | **0** | |

本批出現舊名:bg / card-bg / border / text / text-dim / green / red / yellow / blue / card-radius(10 種)。
未出現:card / dim / muted / neutral / good / bad(6 種;無 no-op 副作用)。

## Fallback 保留(C6 未動,親證)

- `tab-phase4.html` 50/74/111/135/141:`var(--border, #30363d)` → `var(--border-subtle, #30363d)`(hex 保留)。
- `tab-settings.html` 263:`var(--yellow, #f0c040)` → `var(--warn, #f0c040)`(hex 保留)。

## 驗證(§10 DoD)

1. **13 檔舊名 grep = 0**:全 0(上表),精確邊界 `var\(--…[,)]`。全站唯一未清 = login.html(13,兄弟 auth 出範圍)。
2. **canonical 存在**:遷入 10 名全在 tokens.css 有定義 — bg-app/bg-surface/border-subtle/text-primary/
   text-secondary/text-muted/pos/neg/warn 各 3 處(:root + 玄夜 media + 玄夜 attr),r-2 於 :root 共享塊 1 處。
3. **node --check**:13 檔全部 inline `<script>` 逐塊抽驗 PASS(抽取檔寫 scratchpad,即刪,static/ 不留)。
4. **guard 續綠**(親跑):
   - `test_gui_numeric_formatter_contract_static.py` + `test_gui_utilities_spec_drift_static.py` → **3 passed**。
   - **G0.5 stock-etf guard**(4 檔:static_gui / surface_coverage / python_no_write / route)→ **25 passed**。
5. **視覺 computed-identical**:逆映射驗證器對 13 檔逐行比對 — 每一改動行 = 純 var() token 名替換,
   removed→migrate()==added 全等(SURGICAL VERDICT PASS);兩主題別名同值,零視覺變更。
6. **零裸 hex 新增**:所有改動行僅 token 名變化,fallback hex 原封;無新 hex。
7. **static/ clean**:無 .tmp/.bak/抽取 js 殘留。

## 邊界遵守

- 未碰:共用 JS(common*.js/handoff_helper.js,C4)、交易 tab 及其 JS(C4 E2 親算)、殼層(console/index/trading,C5)、login.html。
- 未動 Python/Rust;fallback hex 留 C6;裸屬性 0;不 commit。
- **兄弟髒改動**:git 樹另見 login.html 既有 dirty(非本批;我未觸碰、未 revert)。

## 交回 PM

C3a 完成。C4(交易 tab + `--red` canon6 分類)、C5(刪 tokens-compat.css)為後續批,前置條件見 §1.4。

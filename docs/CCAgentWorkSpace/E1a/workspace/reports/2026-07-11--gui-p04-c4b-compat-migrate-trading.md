# E1a — GUI P0.4 C4b tokens-compat 遷移(交易 tab,8 檔) · 2026-07-11

STATUS: PASS — 170/170 舊名機械遷移到 canonical,8 檔舊名 grep=0,零邏輯改動,node --check 全綠,guard 續綠,REAL FUNDS 熱紅未觸。

範圍:`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/` 的 8 個交易 tab 檔。
基線 HEAD:`d8a7c41ad`。方法:確定性 perl 逐舊名 `var\(--OLD(?=[,)])` → `var(--NEW`(boundary lookahead,承 C4a §1.2);fallback hex/rgba 保留(C6);JS 字串內字面同遷。映射表 §1.2 逐條,無裁量。

## 1 · 8 檔前後計數表(16 舊名,boundary `[,)]`)

| 舊名→canonical | tab-gov | tab-live.html | tab-live.js | tab-paper | app-paper.js | tab-demo | tab-risk | risk-tab.js | 合計 |
|---|---|---|---|---|---|---|---|---|---|
| --bg→--bg-app | 11 | 1 | 0 | 2 | 2 | 0 | 2 | 0 | 18 |
| --card-bg→--bg-surface | 6 | 4 | 0 | 2 | 0 | 0 | 0 | 1 | 13 |
| --card→--bg-surface | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| --border→--border-subtle | 21 | 6 | 0 | 3 | 8 | 0 | 1 | 0 | 39 |
| --text→--text-primary | 5 | 2 | 0 | 1 | 6 | 0 | 1 | 0 | 15 |
| --text-dim→--text-secondary | 14 | 9 | 3 | 4 | 11 | 4 | 0 | 1 | 46 |
| --dim→--text-secondary | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| --muted→--text-muted | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| --neutral→--text-muted | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| --green→--pos | 2 | 2 | 2 | 1 | 4 | 1 | 0 | 1 | 13 |
| --good→--pos | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| --red→--neg | 4 | 0 | 3 | 1 | 4 | 1 | 0 | 1 | 14 |
| --bad→--neg | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| --yellow→--warn | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 1 | 4 |
| --blue→--text-secondary | 1 | 0 | 0 | 2 | 1 | 0 | 0 | 1 | 5 |
| --card-radius→--r-2 | 0 | 0 | 0 | 2 | 1 | 0 | 0 | 0 | 3 |
| **每檔合計(before)** | **65** | **24** | **9** | **18** | **37** | **7** | **4** | **6** | **170** |
| **每檔 after(舊名剩餘)** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |

- perl 實際替換數 = **170**(逐檔 65/24/9/18/37/7/4/6),與基線精確吻合。
- 遷移後 16 舊名 boundary grep 全站 8 檔 = **0**。
- 3 個 fallback 形式(全在 tab-governance.html)hex/rgba 保留:`165 var(--card-bg, rgba(22,27,34,.65))`→`var(--bg-surface, rgba(...))`、`199 var(--blue, #58a6ff)`→`var(--text-secondary, #58a6ff)`、`204 var(--red, #f85149)`→`var(--neg, #f85149)`。

## 2 · --red 分類(14 點,C4b 一律機械 →--neg)+ live-marker 候選 forward-pointer

**全部 14 個 `var(--red)` 已機械遷移 →`var(--neg)`(computed-identical)。** 分兩類:

### 2a · loss/alert/severity(7 點,純機械 --neg,非 live-marker)
| 檔:行 | 語境 |
|---|---|
| tab-governance.html:204 | `.canary-stage-4` 徽章(canary 第4階/危險階 severity) |
| tab-paper.html:67 | paper 錯誤/stale chip 文字 |
| app-paper.js:1547 | replay cell warn 值色 |
| app-paper.js:1557 | replay badge warn 色 |
| app-paper.js:1581 | replay warning-line 色 |
| app-paper.js:1605 | replay load-status warn 色 |
| tab-demo.html:23 | demo stale-banner `.bad` 文字色 |

### 2b · live-marker 候選 forward-pointer(7 點,**本批一律 --neg,不升 --live**;供未來獨立 canon 6 --live pass 逐點裁決)
理由(§1.3):升不升 --live,消費點都已 = 0 舊名,不阻塞刪檔;--live 升級是獨立值變更需 A3 目視 + operator canon 6 確認,不在 C4b。

| 檔:行 | 語境 | 任務預標 |
|---|---|---|
| tab-governance.html:1352 | `_gov*` Signed auth **MISSING** 狀態文字色(live 停機後 auth 撤銷) | 額外發現 |
| tab-governance.html:1360 | `_gov*` Signed auth **Renew required** 狀態文字色 | 額外發現 |
| tab-governance.html:1446 | `expiresEl.style.color` Trust TTL **EXPIRED** | ✓ 已列 |
| tab-live.js:90 | Signed auth **MISSING**(live)color | ✓ 已列 |
| tab-live.js:99 | Signed auth **Renew required**(live)color | ✓ 已列 |
| tab-live.js:138 | `expiresColor` Trust TTL **EXPIRED**(live) | ✓ 已列 |
| risk-tab.js:226 | `_updateEngineBadges` live 引擎徽章 `text:'var(--red)'` | ✓ 已列 |

> 額外發現 2 點(governance:1352/1360)是 live-auth 狀態文字,與任務預標的 1446 同屬 live-auth 語義家族,一併列給 canon 6 pass 裁決。任務預標 5 點(gov:1446、live.js:90/99/138、risk-tab.js:226)全部命中且本批一律機械 --neg。

### 2c · --blue accent-upgrade 候選(次要 forward-pointer,§1.3 A3 選配)
5 個 `var(--blue)` 已機械 →`var(--text-secondary)`(identical,不升 --accent,承 C4a)。其中 **tab-governance.html:199**(`.canary-stage-active` 徽章,帶 `#58a6ff` fallback)語義近「選中/active 態」,是 §1.3 所述 accent-升級選配點,列給未來 A3 逐點裁決;本批不升。其餘 4 點(tab-paper.html×2、app-paper.js×1、risk-tab.js:224 paper 徽章)為中性資訊,→text-secondary 正確。

## 3 · canonical 存在 + computed-identical
tokens.css(served)全 10 個 canonical 目標皆定義(玄夜/帛晝雙主題各一 + palette root):`--bg-app`/`--border-subtle`/`--text-primary`/`--pos`/`--neg`/`--warn` 各 3 定義;`--bg-surface`/`--text-secondary`/`--text-muted` 各 3(mid-line);`--r-2` 1 定義(半徑主題無關)。compat 別名(`--red:var(--neg)`、`--blue:var(--text-secondary)`、`--card-radius:var(--r-2)`…)解析值 == canonical 直接解析值 ⇒ 兩主題零視覺變更。

## 4 · node --check
- 直接 3 JS:tab-live.js / app-paper.js / risk-tab.js = **全 PASS**。
- 5 觸碰 HTML inline `<script>` 抽取檔 node --check:tab-governance.html(2 block)/ tab-live.html(1)/ tab-paper.html(2)/ tab-demo.html(2)/ tab-risk.html(2)= **全 PASS**。抽取檔在 scratchpad,**已即刪**,static/ 無殘留。

## 5 · guard 續綠(親跑)
`pytest tests/structure/`:`test_gui_numeric_formatter_contract_static.py`(formatter)+ `test_gui_utilities_spec_drift_static.py`(spec-drift)+ `test_gui_tokens_root_fork_static.py`(:root fork)= **5 passed**。本批無 stock-etf 檔,G0.5 stock-etf guard 不涉;formatter+spec-drift 續綠。

## 6 · 零邏輯改動自查(交易面最嚴)
- **airtight 證明**:對 backup 與遷移後版本各做 `var\(--[A-Za-z0-9_-]+`→`var(--X` 全 token 遮罩後 diff,8 檔全 **CLEAN(空 diff)** ⇒ 改動位元僅限 `var()` 內 token 名,無 fetch/事件/gate/typed-confirm/其他屬性/選擇器名/控制流變更。
- **git diff 交叉核**:8 檔每個 removed 行的真舊名計數 == 基線(65/24/9/18/37/7/4/6);同行共存的 canonical token(--r-1/--sp-*/--fs-*/--accent/--border-strong 等)在 -/+ 兩側相同(未變,僅共享變更行)。
- **REAL FUNDS 熱紅未觸**:硬編 `rgba(239,68,68)`/`rgba(248,81,73)` 為 standalone(非 var()),遷移只改 var 名故永不命中;backup vs 遷移後熱紅 rgba 計數逐檔相等(gov 5/live 11/paper 2/app-paper 4/demo 1/risk-tab 1 UNCHANGED)。canon 6 硬邊界維持。

## 7 · static clean + 邊界
- static/ 無 `*.inline.js`/`*.bak`/`*.orig`/`*~` 殘留;backup 在 scratchpad。
- **不 commit**(交 PM/E2)。
- **兄弟髒改動未觸碰**:worktree 為 multi-session dirty;`login.html` 於 `git diff --stat` 顯示 modified,但其內容為 auth 表單(`LOGIN_ERROR_FALLBACKS`)非 token,係他 session 兄弟改動,**我從未列入 8 檔清單/backup/perl 迴圈**。其餘 .claude/docs/memory/ml_training/Python 大量 `M`/`??` 皆前置兄弟髒狀態,未觸。

## 8 · 異常
無。170/170 機械遷移;交易面 skin-only,零邏輯;live-marker 7 點(含 2 額外發現)全列 forward-pointer 交未來 canon 6 --live pass(不阻塞刪檔)。C5 刪 compat 前置:本批貢獻「8 交易檔舊名=0」,其餘 served/legacy 面舊名清零由其他子批完成後方可刪檔。

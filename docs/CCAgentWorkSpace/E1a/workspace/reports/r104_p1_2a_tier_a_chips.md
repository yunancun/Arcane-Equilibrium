# E1a-1 · P1.2-a Tier A 頂欄/status 類別狀態 chips 接線 — R104

- 日期:2026-07-14
- 角色:E1a(source_writer)
- 範圍:design/14 §7 的 **E1a-1**(Tier A 遙測 chips)。**不做** cutover(E1a-2)/衡樑傾角(Tier B)/後端。
- worktree:`/Users/ncyu/Projects/TradeBot/.gui-loop-pub-wt/`(唯讀 git,只編輯 + node --check)。
- 四態:**IMPL-COMPLETE**。

## 1 · 改動清單(檔 + 行為)

### A. `.../app/static/shell.html`(§3.1:只加 id + 新 chip 佔位,零 class/樣式改動)
| 元素 | 動作 | id |
|---|---|---|
| 頂欄 engine 值 | 加 id(Tier A 接線) | `oc-top-engine`(保留佔位「待接線 · P1.2」為首載/失敗態) |
| 頂欄 lease 值 | 加 id(Tier B,維持 blocked `—`) | `oc-top-lease` |
| 頂欄 risk chip | **新增** `.topstat`(複用既有 class)`包絡 <span id=oc-top-risk>—</span>` | `oc-top-risk` |
| 頂欄 gate chip | 同上 `gate <span id=oc-top-gate>—</span>` | `oc-top-gate` |
| status wide engine | 加 id | `oc-st-engine` |
| status wide mode | 加 id | `oc-st-mode` |
| status wide PnL | **不加**(Tier B,留 blocked) | — |
| status core engine | 加 id | `oc-stc-engine` |
| status core mode | 加 id | `oc-stc-mode` |
| 載入 shell.js 的 `?v=` | bump | `20260713.r97` → `20260714.r104` |

- 衡樑 DOM(`oc-beam`/`oc-beam-used`/`oc-beam-left`)**不動**,維持 blocked。
- 既有所有 blocked 佔位文案保留作首載/失敗態(canon 7,非刪)。

### B. `.../app/static/shell.js`(§3.2:新增 `wireControlPlaneChips()` poll seam)
- `BUILD_TS`:`20260713.r97` → `20260714.r104`(= shell.html `?v=`,cache-buster 紀律 F-R96-1)。
- MODULE_NOTE:主要函數 + 依賴(加 ocApi)+ 硬邊界 ③ 全更新;新注釋全中文。標明 topbar 類別 chips = P1.2-a Tier A、衡樑+高頻遙測 = P1.2-b Tier B NEEDS-LINUX。
- 新增函數:`renderChip / renderChipBlocked / riskTone / gateTone / updateEngineChips / updateModeChips / updateRiskGateChips / pollControlPlane / wireControlPlaneChips` + `CHIP_TONE_CLASS` + `_cpInFlight`。
- 復用 `common.js` `ocApi(path)`(8s AbortSignal.timeout→null,不重造 fetch/CSRF)。
- 三路併發 `Promise.all([ocApi('/api/v1/system/overview'), ocApi('/api/v1/system/control-plane'), ocApi('/api/v1/openclaw/status')])`;任一 null 只令該來源 chip blocked。
- canon 7 三態:有值→真值+語義 class;null/timeout/401→`—`+blocked;首載未回→保留 html 佔位。**絕不 fake**。
- 字段路徑 byte-parity(mirror 既有 view 確切 access):
  - engine:`d.data.runtime.engine_alive`(view-agents-openclaw.js:146)→ true=運行中(good)/false=離線(warn)/null·timeout=blocked。
  - mode:`gr = d.data.global_runtime || d.data; gr.global_mode_state`(tab-system.html:818/821)→ 命中 `live`→canon-6 `--live` 熱紅(比照 tab-system.html:852)/`demo`→warn/其餘→good/null→blocked。
  - risk:`cp.data.risk_envelope.effective_risk_envelope_state`(envelope `.data` 解包 parity 錨=tab-settings.html:960 `loadControlPlane` live GUI 消費者;字段名對後端 state_store.py:205 核實)→ blocking=warn / reserved·configured=good / 其餘=blocked。
  - gate:`cp.data.health_gate_summary.health_gates_overall_state_summary`(同 `.data` 錨 tab-settings.html:960;字段名對後端 state_store.py:198 核實)→ passed 類=good / blocked·failed 類=bad / 其餘=warn。
- 輪詢生命週期:boot kick 一次 + `setInterval(…, 10000)`;`_cpInFlight` 重入閘;`document.visibilityState==='hidden'`→skip(可見性暫停);全 GET 零寫。
- 接線點:`boot()` 末 `setInterval(updateClock,1000)` 之後加 `wireControlPlaneChips()`;`renderBeamBlocked()` 呼叫**不動**。
- **build chip(healthz)= SKIP**(design §3.2 optional;healthz∈authoritative 未親證,避風險);但 BUILD_TS 仍 bump。
- **LIVE 熱紅 zero-CSS 實作**:`renderChip` 對 live 態走 `el.style.setProperty('color','var(--live)')`(scoped 正法,非 `style=` 字面 / 非裸 hex),其餘 tone 用既有 utility class `t-pos/t-warn/t-neg`(oc-utilities.css 已載),blocked 用既有 `.blocked`。零新 CSS。

## 2 · 驗證(§4)

### node --check
```
NODE_CHECK: OK
```
shell.html 結構完整:`<!doctype html>` 首、`</body></html>` 尾;html 1/1、body 1/1。

### style ratchet 自檢(shell.js + shell.html 維持 0/0/0)
- inline `style=` 字面(排除 `.style.` JS):**none**
- `<style>` 塊:**none**
- 裸 hex `#rgb/#rrggbb`:**none**
- pytest `test_gui_style_ratchet_static.py`:綠(shell.js/shell.html 不在 baseline → 預設 0/0/0)。

### 逐條 fetch(GET,path)grep → 後端 authoritative 路由(§3.3)
| path | shell.js 行 | 後端定義 |
|---|---|---|
| `/api/v1/system/overview` | 584 | system_legacy_routes.py `@app.get(f"{settings.api_prefix}/system/overview")` |
| `/api/v1/system/control-plane` | 585 | system_legacy_routes.py `@app.get(f"{settings.api_prefix}/system/control-plane")` |
| `/api/v1/openclaw/status` | 586 | openclaw_routes.py prefix `/api/v1/openclaw`(:53)+ `@openclaw_router.get("/status")`(:947) |

`test_gui_smoke_fetch_route_alignment_static.py`:綠(三路 ∈ authoritative;scanner 以 `(?<![.\w])ocApi(` 抽取,bare `ocApi(` 被納入對齊,非 vacuous)。

### cache-buster 對等
- shell.js `var BUILD_TS = '20260714.r104'`
- shell.html `shell.js?v=20260714.r104`
- `test_shell_js_cache_buster_matches_build_ts`(R99 guard):綠。

### 測試總覽
- `test_gui_shell_view_registry_static.py` + ratchet + alignment:**22 passed**。
- `tests/structure/ -k "gui or shell or ratchet or smoke or asset"`:**439 passed, 0 failed**。

## 3 · 硬邊界複核(通過)
- 殼全程 read-only:全 GET,零 POST/order/activation。Live 硬化面邏輯不碰(只頂欄 chip 顯示,mode=live→熱紅不稀釋)。
- 零 Python 後端改動(Tier A 刻意零新路由,復用既有 authoritative)。
- canon 7:null/timeout/401→blocked,絕不 fake 0.00/假 heartbeat/假成功。
- Vanilla JS,不引框架;零新 CSS(ratchet 0/0/0)。

## 4 · 殘留 / uncertainty
- **[med] chip 真值 = runtime(NEEDS-LINUX)**:源碼 Mac-可建可驗(node/ratchet/alignment 綠),但 chip 顯示的**真值**依 runtime snapshot / engine 發布(Linux)。Mac 無 runtime snapshot 時 engine_alive=null → 頂欄 blocked(誠實,非缺陷)。三態真渲染 / mode 熱紅 / risk·gate tone 真值 = operator §8 只讀批驗(V5-defer),不由本刀 attest。
- **[low] risk/gate tone 語義為判斷值**:reserved/configured/blocking 與 gate 狀態的 tone 映射依 gui-style-guide(綠=安全/黃=注意/紅=風險升高)+ canon 6 保守取定;真值文字為 byte-parity 原始 state 字串(不擅自漢化,避免與 legacy 分歧)。
- **build chip(healthz)刻意 SKIP**:design §3.2 標 optional;`/api/v1/healthz` ∈ authoritative 未親證,避風險;`#oc-build` 維持靜態 BUILD_TS。
- **衡樑 Tier B + lease/PnL/latency/sync/queue 維持 blocked**:P1.2-b NEEDS-LINUX,不在本 loop。

# 09 · P1.1 新殼 Shell — 建置分解設計正本(strangler-fig 起步)

> PA-design-writer 設計(2026-07-11,R50)。**架構已 locked**(working doc §1:strangler-fig
> iframe-per-tab → single-doc shell + view-router + shared WS;交易關鍵 tab 最後遷移 + flag)。
> 本檔是**實作分解**,非重新設計:把 locked 架構 + 形制正本(`2026-07-10--xuanheng_live_view_sample.html`)
> + 尺寸正本(`design/02_layout.md`)+ 識別正本(`design/04_identity.md`)落成 E1a 可直接建置的規格。
> 驗收權威=LOOP-DRIVER §0/§4/§6 + 樣式 ratchet + smoke suite(design/08)。
> **本檔只寫設計;shell.html/shell.css/shell.js 代碼=E1a。**

---

## 0 · 範圍、定位、關鍵約束

**目標(P1.1 觀察性結果):** 新增一個玄衡儀單文檔殼,以 hash view-router 承載全部 18 個既有 tab
(P1.1-a 階段**全部經 iframe 後備**渲染,零功能破壞),與 legacy `/console` 並存,opt-in 進入。
之後切片(P2)逐 tab 遷出 iframe。

**兩條決定性約束(先立,後文所有決策由此推出):**

- **C1 · 樣式 ratchet 逼出 CSS 策略。** `tests/structure/test_gui_style_ratchet_static.py` 掃 static/ 全
  `.html/.js/.css`(排除 tokens/compat/oc-utilities 三正本)。**不在 BASELINE 的新檔,三維上界皆隱含 0**
  (`base.get(dim,0)`)。故 `shell.html` 只要含 **任一** `<style>` 塊 / inline `style=` / 裸 hex → ratchet 立即紅。
  ⇒ **shell.html 必須零 `<style>`、零 `style=`、零裸 hex**;所有版式走既有 `tokens.css` + `oc-utilities.css`
  **+ 新外部 `shell.css`**(只消費 `var(--…)`,零裸 hex → 乾淨過 ratchet 0/0/0)。衡樑動態傾角用
  **`el.style.setProperty('--beam-angle', …)`**(JS scoped-var,`STYLE_ATTR_RE` 不匹配 `.style.setProperty`,合法)。
  這同時就是 canon 8(單一 stylesheet,零 inline sprawl)的正解——**約束與 canon 同向,非衝突**。
- **C2 · `/static/*.html` 已被 server 端 auth 守。** `main_legacy.py:532 static_auth_guard` 中介層:非豁免的
  `/static/*` 無有效 `oc_auth_token` cookie → 401。⇒ 靜態 `/static/shell.html` **天生 auth-gated**(與每個
  tab-*.html 同級),**無需任何 runtime 路由改動**即可安全上線。差別僅:未認證得 401 JSON 而非 `/login` 轉址
  (opt-in beta 可接受;shell.js 亦跑 client-side `ocAuthCheck()` 補轉址,與 tab 一致)。

**locked 輸入(不重議):** S1 Terminal 暖調玄衡儀 / vanilla JS + CSS var,無框架無 build / IA=lane×environment /
交易關鍵最後遷移 + flag + iframe 後備保留至 Phase 2 / 衡樑無真值顯 blocked 不 fake(canon 7 + LOOP §6)。

---

## 1 · 檔案拓撲

| 新檔 | 角色 | 行數預算 | ratchet 目標 |
|---|---|---|---|
| `static/shell.html` | 殼骨架 markup(chrome 容器 + iframe host + rail/topbar/status 結構)。**零 `<style>`/`style=`/hex。** `<link>` tokens.css + oc-utilities.css + shell.css;`<script src>` common 依賴 + shell.js。 | ~250–350 | 0/0/0 |
| `static/shell.css` | 殼 chrome 版式 class(grid areas / topbar / rail / statusbar / beam / iframe-host / mode-band)。只消費 tokens.css 語義 var。 | ~350–500 | hex=0 |
| `static/shell.js` | view-router(hash 路由)+ iframe host 管理 + lane 切換 + theme/density toggle + 衡樑 render(blocked)+ topbar 狀態接線。 | ~450–650 | 0/0/0 |

**拆檔種子(若 shell.js 逼近 800):** 抽 VIEWS 註冊表(純資料)→ `static/shell-views.js`,router 邏輯留 shell.js。
`shell-views.js` 為 second-adapter 的穩定接口(P2 遷移把某 view 的 `iframe:true` 改 `false` + 指向新 render fn,
不動 router)。三新檔各 <800 硬性;超則先拆再交。

**依賴載入順序(mirror console.html 頭部):** `fetch_with_csrf.js` → `common-formatters.js` →
`common-mode-badge.js` → `common-modals.js` → `common.js`(提供 `ocAuthCheck`/`withBuildVersion`/`ocEsc` 等)
→ `i18n_zh.js` → `shell-views.js`(若拆)→ `shell.js`。**不重造** auth/formatter/CSRF——殼復用既有 helper。

**CSS 策略 deletion test:** 刪 `shell.css` → 版式只能回 inline/`<style>`(ratchet 紅)或無版式。⇒ shell.css 是
**唯一 ratchet-合法的殼版式宿主**,存在成立。second-adapter:P2 遷入的原生 view 與未來 stock lane view
共用同一批殼 class,不複製。

---

## 2 · 頂欄 topbar 規格(48/44px,design/02 §1.1 anatomy)

`grid-area:topbar`,高 `var(--dim-topbar)`(48 舒適 / 44 緊湊),底 1px `--border-subtle`,底色 `--bg-surface`。
左→右 anatomy(全部 class 化,零 inline):

1. **品牌 玄衡**(`.brand`):`.zh`(思源宋體「玄衡」,銘文紀律 canon 11)+ `.en`(mono「ARCANE EQUILIBRIUM」,
   `--text-muted`,letter-spacing)。形制=樣品 L95–98,verbatim class 化。
2. **lane 切換**(見下【決策 A】)。
3. **衡樑**(`.beam-wrap` / `.beam`,見下【決策 B · canon 守恆】)。
4. **engine / lease / heartbeat 狀態**(`.topstat`):P1.1-a **顯 blocked 佔位**(見下【決策 C】)。
5. **Live/Demo PnL**:P1.1-a **blocked 佔位**(canon 7,不假 0)。
6. **UTC + local clock**:純 client `Date`(**無 fetch**,Mac-buildable 真值),`.num` mono tabular,UTC 上 / local 下。
7. **density toggle**(舒適/緊湊):P1.1-a **功能上線**(低風險,只調行高;樣品 L453–459 的 8 行,session-only)。
8. **theme toggle**(玄夜/帛晝):P1.1-a **按鈕渲染但 帛晝 P1.3-gated**(見下【決策 D】)。
9. **account**:顯當前 actor 名(既有 `ocAuthCheck` 已知);登出連既有路徑。

### 決策 A · lane 切換位置 = 頂欄 segmented control(答 §10-Q9)

**選:頂欄 segmented control**(`.lane`,樣品 L99–102 形制)。理由:

- lane 是**最高階語境**(在哪個資產宇宙交易);它框定其下的一切——rail 的 environment ladder、衡樑映射的
  風控包絡、mode 判定——都是 lane-scoped。最高階語境配頂欄 peer-to-品牌,語義正確。
- 樣品(2026-07-10)是 operator 裁決的**形制正本**,lane 置頂欄;且 §10-Q9 傾「how prominent」→ 頂欄最醒目。
- rail 因此簡化為 **env ladder(scoped to active lane)+ cross-cutting** 兩塊,mental model 更乾淨:頂欄選宇宙,
  rail 選該宇宙的階梯 + 正交的橫切面。
- chrome 預算(design/02 §1.4 ≤26%):lane 用**既有**頂欄空間,不新增 region;rail 反而更輕。

⚠ **DRIFT(跨同類設計 authority,保留兩者)**:`design/02_layout.md §1.3` 把 lane switcher 置 **rail-top**
(2-row segmented)。本檔以**較新 + operator 指定形制正本**(樣品)為準置頂欄。**待 PM 裁**:ratify 頂欄方案
並標 design/02 §1.3 `rail-lanes` 塊 superseded-by-sample,或保留 rail 方案(則本檔改跟 design/02)。E1a 開工前需此裁決。

### 決策 B · 衡樑(canon 守恆,非協商)

衡樑真值=**風控包絡已用/剩餘比例**,來自 Rust 風控權威。**P1.1-a 尚無 shared WS(P1.2 才有)** →
殼層無真值 → **按 canon 7 + LOOP §6 顯 blocked 態,絕不 fake 傾角**:

- 秤樑水平靜置(`--beam-angle:0deg`),色 `--text-muted`,標籤「包絡 · 待風控包絡接線(P1.2)」。
- 樣品的 `setBeam(31)` 假數據**僅樣品演示,shipped shell 不得抄真值**。shell.js 保留 `setBeam(usedPct)` 函數
  形制(scoped-var 寫法),但 P1.1-a **不呼叫**(或以 `null`→blocked 分支渲染),真接線=P1.2。
- reduced-motion:秤樑本就靜止(canon 10 例外的 500ms 緩動在有真值時才啟)。
- **真渲染(傾角/warn 閾)= NEEDS-LINUX runtime**(需 engine + 風控包絡 WS)。

### 決策 C · topbar live 遙測 = P1.1-a 顯 blocked,不新增 fetch

engine heartbeat / lease TTL / Live-Demo PnL / mode:**P1.1-a 全顯 canon-7 blocked 佔位**(「待接線 · P1.2」),
**不新增任何 fetch**。理由:(a)避免假 heartbeat/假 PnL(canon 7);(b)避免新 fetch 路徑落入 smoke 切片(5)
fetch↔route 對齊 ratchet 的新增負擔;(c)真遙測本就屬 P1.2 shared data layer。**例外**:clock 是純 client 真值,上線。
若 E1a 選擇在 P1.1-a 接**既有** GET(如 engine 狀態),必須:①用既有權威路由;②過(5)對齊 ratchet;③渲染
canon-7 三態——否則預設一律 blocked 佔位,真接線推 P1.2。

### 決策 D · theme toggle 尊重 P1.3 硬 gate

LOOP §6 + PROGRESS P1.3:**帛晝 AA 三綠前 data-theme 釘死玄夜,不宣稱雙主題可用**。故 P1.1-a:
`shell.html` 帶 `<html data-theme="dark">`(與既有 22 檔一致),theme 按鈕**渲染但 帛晝 path P1.3-gated**
(按鈕標「帛晝 · 待 P1.3」或 inert)。density toggle 上線(session-only)。**localStorage 持久化 = P1.3**(本刀不做,避免範疇蔓延)。

---

## 3 · rail 規格(lane×environment IA;240/200 + 56 collapsed)

`grid-area:rail`,寬 `var(--shell-rail-w)`,右 1px `--border-subtle`,底色 `--bg-surface`,flex column。
兩塊(lane 已上移頂欄,故 design/02 §1.3 的 rail-lanes 塊移除):

- **`.rail-envs`**(scoped to active lane,flex:1):當前 lane 的 environment ladder + 該 lane 專屬 view。
  lane 切換時**重繪本塊**(env 集隨 lane 變)。Live rung 前置 8px hairline divider + `--live` 左邊框
  (design/02 §1.3 的視覺 gate:不跨 hairline 到不了真金面)。
- **`.rail-cross`**(`margin-top:auto` 釘底,頂 1px hairline):lane/env 正交的橫切導航。

### VIEWS 註冊表(19 tab → lane×env cell;P1.1-a 全 `iframe:true`)

router 讀此表建 view + rail 導航。**內容守恆**(working doc §5:零靜默丟失)——全在,映射對 Phase 2 矩陣
(PROGRESS §Phase 2)。**R51 修正**:原表漏列 legacy `charts`(K線圖表 trading.html `/trading?embed=1`,legacy `edge` 組)
=真功能 view 非死碼→E2 N1 揭,PM 補回為 `charts`(lane=cross,`#/cross/charts`,無 visibility 消費者故 visId 無害),
恢復 legacy parity;18→**19 view**。

| view id | lane | rail 區/rung | hash | iframe src | ⚑ |
|---|---|---|---|---|---|
| `overview` | crypto | env·總覽 | `#/crypto/overview` | tab-system.html | |
| `live` | crypto | env·live | `#/crypto/live` | tab-live.html | ⚑ |
| `demo` | crypto | env·demo | `#/crypto/demo` | tab-demo.html | ⚑ |
| `paper` | crypto | env·paper | `#/crypto/paper` | tab-paper.html | |
| `replay` | crypto | env·replay | `#/crypto/replay` | tab-replay.html | |
| `strategy` | crypto | env·策略 | `#/crypto/strategy` | tab-strategy.html | |
| `earn` | crypto | env·earn | `#/crypto/earn` | tab-earn.html | |
| `stock` | stock | env·總覽(read-only) | `#/stock/overview` | tab-stock-etf.html | |
| `monitor` | cross | 監控 | `#/cross/monitor` | tab-monitoring.html | |
| `ai` | cross | AI | `#/cross/ai` | tab-ai.html | |
| `agents` | cross | AI·團隊 | `#/cross/agents` | tab-agents.html | |
| `learning` | cross | 學習 | `#/cross/learning` | tab-learning.html | |
| `development` | cross | 開發 | `#/cross/development` | tab-development.html | |
| `phase4` | cross | 開發·phase4 | `#/cross/phase4` | tab-phase4.html | |
| `gates` | cross | 治理·封驗 | `#/cross/gates` | tab-edge-gates.html | |
| `governance` | cross | 治理 | `#/cross/governance` | tab-governance.html | ⚑ |
| `risk` | cross | 風控(衡樑源) | `#/cross/risk` | tab-risk.html | ⚑ |
| `settings` | cross | 設置 | `#/cross/settings` | tab-settings.html | |

⚑=交易關鍵,P2 最後遷移且全程 flag+iframe 後備。`overview`(tab-system)兼 global-mode;Phase 2 與 settings
併「單一 home」時再處理去重,P1.1-a 先各自成 view(iframe 內容不動=零丟失)。tab-system 的 legacy 首載地位 →
**殼預設 landing = `#/crypto/overview`**(legacy parity,PM-tunable)。

- 每 rail item:`aria-current="page"` 標 active(樣品 L152–159 形制);env-badge mono 小字。
- **collapse**(design/02 §5:≤960 rail→drawer):P1.1-a **可最小實作**(rail 固定,drawer 化列 P1.1-b follow-up),
  但 status strip 促升(§4)是**硬要求**——窄屏 engine/mode/PnL 不得消失。E1a 至少保證 ≤960 不破版;drawer 動效可 defer。

---

## 4 · 底部 status strip 規格(28px,design/02 §1.2/§5.2)

`grid-area:statusbar`,**滿寬跨 rail 下方**(VS Code/Bloomberg 慣例),高 `var(--shell-status-h)`(28,兩密度同),
頂 1px `--border-subtle`,底色 `--bg-sunken`,mono 小字。**這是 rail collapse 時的倖存者**(design/02 §5.2 硬 invariant):
任何斷點都攜 **engine · mode · Live/Demo PnL**。

- 寬屏(`.app-status__wide`):engine 態 · mode chip · latency · last-sync · queue · build SHA。
- ≤960 促升(`--shell-status-h:40`,`.app-status__core`):僅三 chip **不截斷**——`[● ENGINE]` `[MODE]` `[P&L ▲]`。
- **P1.1-a**:engine/mode/PnL/latency/sync/queue = **canon-7 blocked 佔位**(待 P1.2);**build SHA 可真**
  (既有頁面已有 build 版號來源,如樣品 `build aedca22`;若靜態注入則標來源)。mode=LIVE 時 strip 得 2px `--live`
  頂框(design/02 §5.2)——但 mode 真值屬 P1.2,故 P1.1-a strip 為 **mode-neutral**;`--live` 跟隨真 mode = P1.2。

---

## 5 · view-router 規格(shell.js)

### 5.1 hash 方案 + 深連結

- 結構化 hash:**`#/<lane>/<view>`**(如 `#/crypto/live`、`#/cross/governance`)。lane∈{crypto,stock,cross}。
- **深連結 + 刷新保持**:載入時 parse `location.hash` → 定位 view;`window.addEventListener('hashchange', …)`
  → 切 view。改 view 用 `location.hash = view.hash`(推瀏覽器歷史,支援 back/forward)。
- **未知/空 hash → 預設 view**(`#/crypto/overview`),不崩;**非法 hash → fallback 預設 + console.warn**,不崩。

### 5.2 iframe host 管理 = 直接移植 legacy console.html 機制(降新風險)

**strangler-fig 核心 seam。逐項對映 console.html 既有函數**(E1a 移植,非重造):

| legacy(console.html) | 殼對應 | 語義 |
|---|---|---|
| `buildTabs()` L525–558 | `buildViews()` | 每 view 建 rail item + lazy iframe(`f-<id>`,`dataset.src`,首個 set `src`) |
| `switchTo(tabId)` L563–590 | `navigate(viewId)` | 顯 target iframe(首切懶載 `src`)、隱其餘、更新 rail active、發 visibility |
| `notifyTabVisibility()` L595–608 | **verbatim 移植** | **safety-critical**,見 5.3 |
| `flushPendingFrameMessages()` L614–624 | verbatim | iframe 未載完前的訊息佇列 |
| `postToTabFrame()` L626–639 | verbatim | 對單 frame 送訊息(載入態分派) |
| `withBuildVersion(src)` + `_v` | verbatim | cache-bust 版號,tab 更新才傳播 |

`iframe.src = withBuildVersion(view.iframeSrc)`,`iframeSrc` 即既有 `/static/tab-*.html`(**同一批檔,legacy 與殼共用**)。
lazy:首次 navigate 到某 view 才 set `src`;`load` 事件標 `dataset.loaded='true'` + flush queue + 發 visibility。

### 5.3 postMessage 廣播移植清單(「零靜默破壞」的真實邊界)

legacy console.html 對 iframe 發 6 類廣播;**殼必須顯式決定移植哪些,不得靜默丟**:

| 廣播 type | 作用 | P1.1-a 處置 |
|---|---|---|
| `openclaw-tab-visibility`(L602) | tab 據此**暫停/恢復 WS·輪詢**(隱藏即停) | **必移植 verbatim**——這是 per-tab 新鮮度/WS 安全機制(working doc §5「per-tab freshness=safety risk」)。漏發=隱藏 iframe WS 續跑=退步。**非協商。** |
| `openclaw-paper-engine-setting`(L656) | 閘 paper tab 可用性 | **移植**(rail 列 paper view;或 P1.1-a 保守讓 paper 常在,記為 delta) |
| `openclaw-development-support-setting` / `-mode-setting`(L690/L694) | 閘 dev tab | 同上,移植或記 delta |
| `openclaw-risk-select`(L744) | **跨 tab** 深連結(點 risk 項→跳 governance) | P1.1-a **可 defer**,記為 known delta(非靜默) |
| `openclaw-governance-scroll`(L751) | 跨 tab scroll 協調 | 同上,defer + 記 delta |

**「零功能破壞」的誠實定義**:P1.1-a 保證**每 tab 經 iframe 獨立渲染 + 運作如今日直開**,且 safety-critical
`openclaw-tab-visibility` verbatim。跨 tab 協調廣播(risk-select/governance-scroll)若本刀不移植=**明列 delta**
(待該 tab 遷移或 follow-up 恢復),**不靜默丟**。

### 5.4 失敗/恢復

- iframe 載入失敗(tab 404/500)→ view 顯錯誤佔位,殼**不崩**、其他 view 續可切。
- auth 過期 → shell.js `ocAuthCheck()` 與每個 iframe 各自轉 `/login`(N 次獨立 auth,與 legacy 同,P1.1-a 接受)。
- 並發:殼 = 純讀 chrome + router,無寫路徑,無並發寫風險。

---

## 6 · flag 路由 / strangler-fig(觸達機制)

### 6.1 P1.1-a 觸達 = 靜態檔 + 手動 opt-in(**零 runtime 路由改動**)

- shell.html/css/js 為**靜態檔**,經既有 `/static` mount 服務(disk 直服,免 rebuild/reload——R40 memory 實證)。
  觸達 URL = **`/static/shell.html`**。由 C2:已被 `static_auth_guard` auth-gated,安全。
- **opt-in(二選一,PM/operator 定)**:
  - **(a) 零觸 legacy**:operator 直接導航/書籤 `/static/shell.html`。strangler-fig 最純,console.html byte-frozen。
  - **(b) 可發現 flag 連結**:在 legacy `console.html` 加**一個** opt-in 連結/按鈕(「試用新殼 · New Shell (beta)」→
    `/static/shell.html`)。這正是 LOOP §6「legacy 只接 flag 跳轉」的**唯一 sanctioned 觸碰**——**非 re-theme/重構**,
    純附加、可逆、無寫路徑無邏輯,過 E2。console.html 是靜態檔,編輯免 reload。
- **反向 fallback**:shell.html 常駐「返回舊版 · Legacy Console」連結 → `/console`,beta 期一鍵退回。
- **建議**:採 (b) 求可發現性 + (a) 併存(URL 亦可直達);(b) 是唯一 legacy 觸碰,E2 需親證只增連結、零他改。

### 6.2 乾淨 `/shell` 路由 = 後續 deploy 步驟(NEEDS-OPERATOR / RUNTIME,**不在 P1.1-a**)

最終形應有 server 端守衛的 `GET /shell`(login 轉址而非 401 JSON)。**這需改 `gui_legacy_routes.py`(Python)+ app reload**
→ 觸犯 GUI loop 硬邊界(不改 runtime 路由 / 不 reload)。故:

- **GUI loop 不自行部署**;本檔提供**建議 route 規格**供未來 operator/OPS deploy:於 `register_gui_legacy_routes`
  加 `@app.get("/shell")`,body 復用 `_redirect_if_unauthenticated(request)` 守衛 + `FileResponse(_static_dir/"shell.html", headers=_NO_CACHE_HEADERS)`(mirror `console_index` L115–122)。
- 可選 server flag `OPENCLAW_GUI_SHELL=1`:閘 console.html opt-in 連結可見性 / 啟乾淨路由。同屬 **NEEDS-OPERATOR/RUNTIME**。
- **記入帳本 NEEDS-OPERATOR**:乾淨 `/shell` 路由 + server flag = deploy-time,P1.1-a 用靜態路徑不阻塞。

---

## 7 · 首刀 P1.1-a 交付邊界 + 驗收

### 7.1 In-scope(單輪 E1a-able + E4 可驗)

1. 新檔 `shell.html` + `shell.css`(+ 選配 `shell-views.js`)+ `shell.js`,ratchet 0/0/0(hex=0)。
2. **玄衡 chrome**:topbar(品牌 + lane segmented + 衡樑 **blocked** + 遙測 **blocked 佔位** + clock 真值 +
   density toggle **上線** + theme toggle **P1.3-gated** + account)+ rail(env ladder scoped active lane + cross-cutting,
   18 view 全列)+ status strip(engine/mode/PnL blocked 佔位 + build SHA,滿寬,≤960 促升不失 engine/mode/PnL)。
3. **hash view-router**:18 view **全 `iframe:true`** 包既有 tab-*.html;`openclaw-tab-visibility` verbatim 移植;
   深連結 + 刷新 + back/forward 保持;未知 hash→預設;iframe 載入失敗不崩。
4. **flag opt-in**:`/static/shell.html` 可達 + console.html 一個 opt-in 連結(或零觸 URL)+ 殼內反向連結。
5. `<html data-theme="dark">` 釘玄夜(尊重 P1.3 gate)。

### 7.2 Out-of-scope(明列,防蔓延)

shared WS / 真遙測(P1.2)· 遷任何 tab 出 iframe(P2)· 帛晝 上線宣稱(P1.3)· localStorage 持久化(P1.3)·
⌘K 命令面板(P1.3)· Live 硬化快照 + client audit(P1.5)· 乾淨 `/shell` 路由 + server flag(operator/OPS deploy)·
任何新寫路徑 · rail drawer 完整動效(可 P1.1-b)。

### 7.3 驗收(E4)

- **Mac-buildable(靜態事實)**:node --check shell.js(+ shell-views.js + shell.html 任何 inline script)全綠;
  ratchet:shell.* 三檔 0/0/0(**無需加 BASELINE 條目,born clean**);smoke suite(§8)自動納入且綠;
  HTML 結構平衡(smoke family 1 若啟)。
- **手動/視覺(dev server,截圖輔助)**:18 view 經 iframe 各自渲染如今日;hash 深連結/刷新/back 正確;
  切 view 時隱藏 iframe 收到 `visible:false`(WS 暫停可觀察);opt-in 進 + 反向退可用。
- **NEEDS-LINUX runtime**:衡樑真傾角 / 真遙測三態 / 帛晝 runtime AA / 全頁視覺回歸 / 鍵盤走查 = V5-defer,
  需 engine + WS,**不在本刀驗收**(誠實標記,不宣稱 GUI works)。

### 7.4 之後切片(排序)

P1.1-b rail drawer 完整 collapse → P1.2 shared WS(接衡樑真值 + topbar/status 遙測 + 每 view 新鮮度徽章)→
P1.3 帛晝 AA 三綠 + 主題/密度持久化 + ⌘K → P1.4 共用組件凍結 → P1.5 Live 硬化快照 → P2 逐 tab 遷出 iframe。

---

## 8 · smoke 覆蓋

- **零新測試碼**:既有 `test_gui_smoke_js_syntax_static.py`(node --check 全 `.js` + inline `<script>`)、
  `test_gui_smoke_asset_refs_static.py`(全 `/static/` `<script src>`/`<link href>` 存在)、
  `test_gui_style_ratchet_static.py` 皆以 glob 掃 static/ → **shell.html/shell.css/shell.js 自動納入**
  (design/08 §2 anti-vacuous floor 設計正是為此)。E1a 落檔即被掃;綠=syntax/ref/style 事實成立。
- **shell.js = design/08 §0 的 jsdom「credible consumer」觸發點**:view-router 的 hash→iframe DOM-wiring 是首個
  值得執行 DOM 行為的 consumer。**是否引 jsdom 測 router 行為(stub iframe/postMessage)= PM/operator 決策點**,
  非開發角色自決;本刀維持 static-only(誠實邊界:靜態 smoke 不 attest router runtime 行為)。
- **若 shell.js 新增 fetch**(§2 決策 C 預設不增):該 `(method,path)` 須進 `test_gui_smoke_fetch_route_alignment_static.py`
  的 authoritative∪allowlist,否則 fail。預設 P1.1-a topbar 遙測 blocked 佔位=**零新 fetch**,不觸此 ratchet。

---

## 9 · canon / 硬邊界守恆

- **衡樑無真值 = blocked,不 fake 傾角**(§2-B,canon 7 + LOOP §6)。真值 NEEDS-LINUX(P1.2 WS)。
- **Live view 經 iframe 保留全部既有硬化面**:tab-live.html 在 iframe 內**未改動**載入 → 五閘 / ⚠ REAL FUNDS 常駐 /
  typed-confirm / 緊急停止與平倉物理分離 / `--live` 熱紅**全部原樣**。殼**零新增寫路徑**;寫面仍走 iframe 內既有
  Rust authority IPC。這是 strangler-fig 的安全保證:交易關鍵面 byte-identical 續 work。
- **殼 = 純 chrome + router,無 fetch 寫、無 order、無 activation**。IBKR 面(stock lane)P1.1-a 僅 iframe 包
  tab-stock-etf.html(既有 read-only chips/banner),殼不新增任何 IBKR 寫/激活 UI(CLAUDE 硬邊界:GUI 永不成
  IBKR order/risk/activation 權威)。
- **canon 8 單一 stylesheet 零 inline**:shell.html 0/0/0(C1),殼本身即 canon 8 的正示範。
- **P1.5 依賴前置**:遷 Live **出** iframe(P2)前,必先 P1.5 快照 Live 硬化面 + 加 client audit events(§9 Guard)。
  P1.1-a 不遷 Live,故未觸此 gate,但**必記**:P2 ⚑ tab 遷移以 P1.5 為前置。

---

## 10 · P1.2 / P1.5 前瞻(不在 P1.1-a,標依賴)

- **P1.2 shared WS / data layer**:單一 WebSocket + 按 view 訂閱,取代 P1.1-a 的 N 個 iframe 各自 fetch/WS
  (working doc §5 root-cause A;P1.1-a **刻意保留** legacy 各自連線=零破壞代價,shared WS 是後續**優化**非本刀)。
  接線對象:衡樑真傾角、topbar engine/lease/PnL、status strip 遙測、每 view 新鮮度徽章(canon 7)。**真渲染 NEEDS-LINUX。**
- **P1.5 Live 硬化快照 + client audit**:遷 Live/governance/risk/demo(⚑)出 iframe 前,先快照現硬化面 + 佈 client
  audit events(§9 Guard),防遷移中靜默弱化。P1.1-a 的 iframe 保留即天然快照(原檔未動),P1.5 是 P2 遷移的前置門。

---

## 11 · 待 PM / operator 裁決點

1. **lane 位置 DRIFT(§2-A)**:ratify 頂欄 segmented(本檔 + 樣品)並標 design/02 §1.3 rail-lanes superseded,
   或改用 design/02 rail 方案。**E1a 開工前需定。**
2. **opt-in 機制(§6.1)**:採 (b) console.html 加連結(唯一 legacy 觸碰,過 E2)還是 (a) 純 URL 零觸。建議 (b)+(a) 併存。
3. **預設 landing(§3)**:`#/crypto/overview`(legacy parity)確認或改。
4. **乾淨 `/shell` 路由 + `OPENCLAW_GUI_SHELL` flag(§6.2)= NEEDS-OPERATOR/RUNTIME**:P1.1-a 用靜態路徑不阻塞;
   何時 deploy 乾淨路由由 operator/OPS 定。
5. **jsdom 決策(§8)**:shell.js 落地觸發 design/08 §0 的 jsdom 重訪;是否引 jsdom 測 router 行為 = PM/operator 決策點。

### PM 裁決(R50,2026-07-11)——E1a 開工前生效
1. **lane 位置 = RATIFY 頂欄 segmented control**(採本檔 §2-A + 樣品)。理由:樣品 `2026-07-10--xuanheng_live_view_sample.html` 是 operator 2026-07-10 形制裁決正本(design 類內較新 normative 權威),PA 架構理據(lane 框 rail env-ladder + 衡樑映射 + mode)成立。**design/02 §1.3 rail-lanes 標 superseded-for-lane**(cleanup debt,E1a 不需改 design/02,以本 §09 為 P1.1 正本)。
2. **opt-in = (b)+(a) 併存**:P1.1-a 落靜態 `/static/shell.html`(auth-gated 天生保護,零 runtime 改)+ console.html 加**一個** opt-in 連結(LOOP §6 唯一 sanctioned legacy 觸碰,過 E2)+ 殼內反向「返回舊版」連結。
3. **預設 landing = legacy parity**:map `#/` 到 legacy console 預設著陸 view(監控/儀表盤);E1a 以 legacy 現行預設 tab 為準(非硬編 crypto/overview 若與 legacy 不符),保 parity。
4. **乾淨 `/shell` 路由 + `OPENCLAW_GUI_SHELL` flag = NEEDS-OPERATOR/RUNTIME,DEFER**。P1.1-a 用靜態路徑不阻塞;乾淨路由 deploy 由 operator/OPS 定時,GUI loop 不自改 runtime 路由。
5. **jsdom = 續 DEFER(P1.1-a 不引)**:shell.js router 由 node --check(語法)+ 既有靜態 smoke(inline script/asset-ref)覆蓋;router **行為** DOM 測(真載對 iframe)屬 runtime/未來 jsdom 決策(當 router 變複雜或行為驗證變關鍵時重訪)。P1.1-a 不需 jsdom。
6. **§5.3 visibility postMessage verbatim 移植 = 非協商硬要求**(PA 對抗點採納):safety-critical `openclaw-tab-visibility` 必以 tab 既有消費形狀逐字移植,shape drift=隱藏 iframe WS 不暫停=freshness/safety 退步=E2 必退回。「零功能破壞」誠實限定=每 tab 經 iframe 獨立運作如今日 + safety visibility verbatim;跨 tab 協調廣播若 defer 明列 delta 不靜默丟。

---

## 附錄 · architecture-depth-review 結果

- **Deletion test**:shell.html(刪→回 18-doc iframe bloat)/ shell.js router(刪→無深連結/無 iframe host)/
  shell.css(刪→ratchet-illegal inline 或無版式)/ iframe host manager(刪→strangler-fig 無法漸進共存)——四者各刪各失
  一致能力,無 ceremonial 模組。
- **Second-Adapter**:VIEWS 註冊表 `iframe` 旗標 = 穩定接口;P2 遷入原生 view(改 `false` + render fn)、未來
  stock lane view 皆經此接,零 policy 複製。拒絕過早抽象:P1.1-a 不建「render 引擎」,全 iframe,待真有第二 adapter
  (首個遷出的原生 view)再引 render seam。
- **Authority/trust**:殼無寫、無 order、無 activation;所有 effect 在 iframe 內既有 Rust authority。衡樑/遙測真值
  = out-of-band trusted producer(Rust 風控 + engine WS),殼無真值時 blocked,不自造。
- **Cross-runtime parity**:`openclaw-tab-visibility` 必以 tab 既有消費形狀 verbatim 發送;shape drift → 隱藏 iframe
  WS 不暫停 = freshness/safety 退步(對抗性 second thought 的最小反例,已於 §5.3 釘死為非協商)。
- **Failure/recovery**:iframe 載入失敗/未知 hash/auth 過期均有確定性 fallback,殼不崩(§5.4)。
- **Consumption**:P1.1-a 刻意保留 N 個 iframe 各自連線(不強拆),因 shared WS 屬 P1.2;現階段強拆的一次性成本 >
  漸進遷移收益,符「不為省而增假閉合/返工」。零新測試碼(smoke glob 自納)= 低 recurring 成本。
- **實作 owner**:E1a(讀 srv:gui-style-guide + bilingual-comment-style)。**獨立驗證**:E2 對抗審查(特別核 §5.3
  visibility 移植 + §6.1 console.html 唯一觸碰 + 衡樑 blocked 不 fake)→ E4-writer/verifier(node --check + ratchet
  0/0/0 + smoke 自動納入 + 回歸對基線)。runtime 三態/帛晝 AA/衡樑真傾角 = NEEDS-LINUX(V5-defer),不由本刀 attest。

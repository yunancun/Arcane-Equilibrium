# 14 · P1.2 數據層接線(Tier A)+ `/console` cutover — 設計正本

> PA-design-writer 設計(2026-07-14,承 PROGRESS R102 後 operator 兩項授權)。
> **授權**:①**cutover-go**(玄衡新殼由 opt-in 轉 `/console` 預設);②**engine/runtime 工作 → P1.2 數據層接線(最高價值)**。
> 本檔是**實作分解 + Tier 裁線**,非重新設計。上游權威:`design/09 §2/§10`(衡樑 canon 守恆 + P1.2 前瞻)、
> `LOOP-DRIVER §3/§4/§6`(治理硬邊界 + canon 7)、`GUI-DESIGN-WORKING-DOC §3`(canon 7/9-11)、`srv/CLAUDE.md §四`。
> **本檔只寫設計;shell.html / shell.js / gui_legacy_routes.py 代碼 = E1a。**
> **第三項「V5 真渲染 = Linux runtime 目視」不在本設計範圍**,但標為下游依賴(§5.4)。

---

## 0 · 範圍、定位、關鍵約束

**目標(觀察性結果):**
1. **Tier A**:頂欄 + status strip 的**類別狀態 chips**(控制面服務存活 / engine 存活 / 風控包絡類別態 / mode / gate 態 / build)由 P1.1-a 的硬編 blocked 佔位,改為**接既有權威 REST 路由**,按 canon 7 三態渲染 → **消解 F-R96-2**(頂欄「engine 待接線」vs view「運行中」矛盾)。
2. **Cutover**:`/console` 由 `return console.html` 改為 `return shell.html`,保留一鍵回滾與 legacy 逃生路徑。

**決定性約束(先立):**
- **C1 · 零新 fetch 路由。** Tier A **只復用既有 view 已消費的 authoritative 路由**(§1 表),不新增任何 REST 路由 → 天生過 `test_gui_smoke_fetch_route_alignment_static.py`(§4)。**新增 Python 路由 = app reload = 觸 LOOP §3 硬邊界**,故 Tier A 刻意零後端改動。
- **C2 · Tier A 全靜態可部署免重啟。** shell.html / shell.js 為 StaticFiles 磁碟直服(R40 實證免 Python 重啟)→ **Tier A 落檔即生效**,不觸 engine restart/rebuild/DB 邊界。**唯一需重啟的是 cutover 的 `/console` 路由改動**(§6,NEEDS-LINUX 部署,非 Tier A)。
- **C3 · 殼全程 read-only。** 新增全為 GET;零 POST / 零 order / 零 activation。canon 7:未接 / null / timeout → blocked / `—`,**絕不假 0.00 / 假 heartbeat / 假成功**(LOOP §3/§4)。
- **C4 · style ratchet 不變。** shell.js 只加行為邏輯(無裸 hex / 無 `<style>` / 無 inline `style=`);shell.html 只加 `id` 屬性與既有 class,ratchet 維持 0/0/0。

---

## 1 · 關鍵事實(調查所得,已核)

**核心裁定:compiled control-plane state 已由多條 GUI-facing REST 路由服務——Tier A 無需新造路由。**
`main.py` 以 `runtime_aware_get_latest_snapshot()`(`runtime_bridge.overlay_runtime_facts`)把 engine 發布的 runtime facts 疊加到 config 快照,再由既有路由 `envelope_response` 輸出。下表所有路由**今日已被已遷原生 view 消費**(故已在 alignment ratchet 的 authoritative∪matched 集內),殼頂欄接線 = 這些路由的**第二消費者**(second-adapter,零 policy 複製):

| Tier A chip | 路由 | 方法/auth | 權威字段(payload) | 既有消費者 | 路由定義 |
|---|---|---|---|---|---|
| 控制面服務存活 | `/api/v1/system/startup-status` | GET / **no-auth** | `server:"up"`、`all_ready` | `common.js:99 waitForServerUp`(殼已載) | `main.py:764` |
| **engine 存活** | `/api/v1/openclaw/status` | GET / authed | `data.runtime.engine_alive`(`true`/`false`/`null`)、`data.runtime.global_mode_state`、`runtime_connection_state` | `view-agents-openclaw.js:241` | `openclaw_routes.py:947`(prefix `/api/v1/openclaw`) |
| **mode** | `/api/v1/system/overview` | GET / authed | `data.global_runtime.global_mode_state`、`global_execution_authority_state` | `tab-system.html:815` / `view-overview.js` | `system_legacy_routes.py:138` |
| **風控包絡類別態** | `/api/v1/system/control-plane` | GET / authed | `data.risk_envelope.effective_risk_envelope_state` ∈ {`reserved`,`configured`,`blocking`} | `tab-system.html:757` / `tab-settings.html:955` | `system_legacy_routes.py:170` |
| **gate 總態** | `/api/v1/system/control-plane` | GET / authed | `data.health_gate_summary.health_gates_overall_state_summary` | 同上 | `system_legacy_routes.py:170` |
| build SHA(可選) | `/api/v1/healthz` | GET / **no-auth** | `boot_sha`、`repo_head`(進程真值,勝過靜態 BUILD_TS) | —(新) | `system_legacy_routes.py:325` |

**風控包絡類別態的來源可信性(engine-independent 確認):** `state_compiler._compile_effective_risk_envelope_state`(`:243`)由 **config switch(`risk_policy_switch`)+ health telemetry gate + demo cooldown** 純函數推導出 `reserved/configured/blocking`,**不需 live engine 持倉**。此即 §09 §2-B 所稱「風控包絡類別態」——在**任何機器**(含 Mac 無 engine)都有確定值,故 Tier A。

**衡樑數值傾角無 Python 來源(Tier B 確認):** compiled snapshot **無**任何「已用/剩餘曝險 %」數值。唯一利用率真值 = `h0_gate_stats.total_exposure_pct`,由 **Rust engine 經 IPC pipeline snapshot** 提供,曝於 `/api/v1/risk/status`(`risk_routes.py:472`),**且僅當 `reader.is_engine_available("paper")` 為真**(`:464`)才存在;分母 cap = `max_total_exposure_pct`(`/api/v1/risk/config:300`,Rust config 權威)。無 running engine → 無 numerator → **無傾角**。詳 §5。

**runtime facts 的 fail-safe:** `overlay_runtime_facts`(`runtime_bridge.py:81`)在 `OPENCLAW_RUNTIME_SNAPSHOT_FILE` 缺席時回退 config 默認(`engine_alive` 缺 → `openclaw_routes.py:252` 回 `None`)。⇒ Mac/無 runtime snapshot 時 `engine_alive=null` → **canon 7 blocked**(正確,非缺陷)。

---

## 2 · Tier 分層裁線(核心)

### 2.1 Tier A(本 loop 於 Mac 可建源碼;node --check + grep 路由可驗;不需 engine 運行)

**範圍 = 頂欄 + status strip 的「類別狀態」chips 接既有權威路由,canon 7 三態。**

| chip | Tier A 值來源(§1 表) | canon 7 三態 |
|---|---|---|
| 控制面服務 | `startup-status.server` | up=真 / 首載=loading / fetch 失敗=blocked |
| engine 存活 | `openclaw/status → engine_alive` | `true`=存活(good)/ `false`=離線(warn)/ `null`·timeout=blocked `—` |
| mode | `system/overview → global_mode_state`(+ control-plane switch summary 校正,mirror view-overview) | 值=真(live→熱紅語義 canon 6)/ null=blocked |
| 風控包絡類別 | `control-plane → effective_risk_envelope_state` | reserved/configured/blocking=真 / null=blocked |
| gate 總態 | `control-plane → health_gates_overall_state_summary` | 值=真 / null=blocked |
| build SHA(可選) | `healthz → boot_sha`/`repo_head` | 值=真 / 失敗=保留靜態 BUILD_TS 後備 |

**數據源 engine-independence:** 上述 chips 的**類別語義**由 config + health telemetry 推導,在無 engine 時仍有確定態(engine_alive 例外:它是 runtime fact,無 runtime snapshot 時 canon 7 blocked——這**正是**誠實態)。**殼源碼變更 100% Mac-buildable**;chip **值的真確性**取決於 runtime snapshot 是否被 engine 發布(Linux),但 canon 7 已妥善處理 null,故**不阻塞本 loop 建置**。

### 2.2 Tier B(NEEDS-LINUX / Rust 權威;operator/引擎側)

**範圍 = 衡樑數值傾角 + 高頻 runtime 遙測。**

| 項 | 為何 Tier B | 真值來源 |
|---|---|---|
| **衡樑傾角(已用/剩餘 %)** | Python 控制面**無此數值**;唯一 numerator=`h0_gate_stats.total_exposure_pct` 由 Rust engine IPC 提供,僅 engine-available 時存在 | Rust 風控權威(h0_gate,engine 更新) |
| engine heartbeat / lease TTL | runtime fact,需 running engine + lease 發布 | runtime snapshot / IPC |
| Live/Demo PnL | engine 快照(balance/drawdown) | `risk/status → current_balance_usdt`(engine-gated) |
| latency / sync / queue | runtime 遙測 | engine WS |

**衡樑未接前維持 `renderBeamBlocked`(shell.js:469)= 正確設計非缺陷**(§09 §2-B、canon 7、LOOP §6)。**本 loop 不能建衡樑真傾角**,因:
- (a)numerator 只在 Rust engine 運行時存在(觸 §3 engine 邊界:需 running engine 對驗,GUI loop 不 restart/rebuild engine);
- (b)§09 §10 + LOOP §6 已裁定衡樑真渲染 = **P1.2 shared WS + engine 風控包絡**,真渲染 **NEEDS-LINUX**;以 8s REST poll `risk/status` 頂替 = 偏離 canonical 架構(N-fan-out poll 正是 shared WS 要取代者),且 Mac 恆 blocked → 零 Mac-可驗行為,得不償失。

### 2.3 F-R96-2 消解歸屬(明確)

- **Tier A 消解**:頂欄/status 的 engine·mode·risk·gate chips 改讀**與 view 同源的權威路由** → 頂欄與 view 顯示**同一真相**,「待接線 vs 運行中」矛盾消失(兩者皆讀 `openclaw/status`·`system/overview`·`control-plane`)。
- **Tier B 保留**:衡樑數值傾角 + heartbeat/lease/PnL/latency 高頻遙測仍 blocked,待 P1.2 shared WS + engine 契約(§5)。**這是誠實邊界,非未完成缺陷**。

**P1.2 重新分解(承此檔):**
- **P1.2-a(= 本檔 Tier A,Mac-buildable,免重啟)**:類別 chips REST-poll 接線 + canon 7。
- **P1.2-b(= Tier B,NEEDS-LINUX)**:衡樑傾角 + 高頻遙測,經 shared WS + engine 風控包絡契約(§5)。

---

## 3 · Tier A 確切源碼變更清單(E1a-writable)

### 3.1 `static/shell.html`(加 `id`,零 class/樣式改動)

頂欄 `.topstat`(:121-123)與 status strip(:159-173)的佔位 `<span class="blocked">` **目前無 `id`**,shell.js 無法定位更新。E1a 加 `id`(canon 7 blocked 佔位文案保留作**首載/失敗態**,非刪):

| 元素 | 現況(行) | 加 id |
|---|---|---|
| 頂欄 engine 值 | `.topstat` engine span(:122) | `id="oc-top-engine"` |
| 頂欄 lease 值(Tier B,留 blocked) | `.topstat` lease span(:122) | `id="oc-top-lease"`(本刀不接,維持 `—`) |
| status wide engine | `.app-status__wide`(:161) | `id="oc-st-engine"` |
| status wide mode | (:162) | `id="oc-st-mode"` |
| status wide PnL(Tier B) | (:163) | 不加 / 留 blocked |
| status core engine/mode | `.app-status__core`(:170-171) | `id="oc-stc-engine"` / `id="oc-stc-mode"` |
| 頂欄 risk/gate(新 chip) | `.topstat` 內新增一/兩 `<span>` | `id="oc-top-risk"` / `id="oc-top-gate"`(canon 7 初始 blocked 文案) |

**衡樑 DOM 不動**(:114-118 已有 `oc-beam`/`oc-beam-used`/`oc-beam-left`,維持 blocked)。**mode=LIVE 熱紅**:mode chip 命中 `live_*` 時加 canon-6 `--live` 語義 class(比照 `tab-system.html:840` badge 邏輯),絕不稀釋。

### 3.2 `static/shell.js`(新增 `wireControlPlaneChips()` poll seam)

**新增一個殼級輪詢器**(非 per-view;topbar/status 跨 view 常駐),嚴守既有 view `loadAll` 慣例:

- **fetch 助手**:復用 `common.js` `ocApi(path)`(`:195`,預設 8s `AbortSignal.timeout` → AbortError/network 皆 `return null`,`:266/269`)。**不重造 fetch/CSRF**。
- **canon 7 三態**:每 chip `if (!d || !d.data) → renderBlocked(id)`;有值 → 真值 + 語義 class;首載未回 → 保留 html 佔位(loading)。**null/timeout/401 一律 blocked,絕不 fake**。
- **多路併發**:`Promise.all([ocApi('/api/v1/system/overview'), ocApi('/api/v1/system/control-plane'), ocApi('/api/v1/openclaw/status')])`;任一 null 只令該來源 chip blocked,其餘正常(部分失敗不整組崩)。
- **輪詢生命週期(比照殼慣例)**:
  - boot 時 kick 一次 + `setInterval(pollControlPlane, 10000)`(~10s;非高頻,topbar 類別態足夠)。
  - `_cpInFlight` 布林重入閘(防 overlap,類比 `_demoRefreshInFlight`/`_riskRefreshInFlight` 先例)。
  - **可見性暫停**:在既有 `document.addEventListener('visibilitychange', …)`(:227)或 poll 入口判 `document.visibilityState === 'hidden'` → skip(鏡像 iframe/native `pause` 語義,不背景空轉)。
  - **零寫**:全 GET;無 POST/order/activation。
- **build(可選)**:`boot()`(:593)的 `#oc-build` 由靜態 `BUILD_TS` 改讀 `/api/v1/healthz → boot_sha`(真進程世代);失敗回退靜態 BUILD_TS。**列為 optional**——E1a 若採,須確認 `/api/v1/healthz` ∈ authoritative(§4);不採則零風險保留現狀。
- **接線點**:`boot()` 末尾加 `wireControlPlaneChips()`(緊接 `updateClock()` 之後);`renderBeamBlocked()` 呼叫**不動**(衡樑續 Tier B)。

**MODULE_NOTE 更新**:標明 topbar 類別 chips = P1.2-a Tier A(既有路由 REST poll,canon 7);衡樑 + 高頻遙測 = P1.2-b Tier B NEEDS-LINUX;新注釋全中文(LOOP §4)。

### 3.3 路由對齊(零新路由,復用既有 authoritative)

**所有新 fetch 路徑皆既有已遷 view 之消費路徑**(§1 表),故 alignment ratchet 天生綠。E1a 開工先 grep 逐條確認 ∈ authoritative(LOOP §4):
- `/api/v1/system/overview`、`/api/v1/system/control-plane` → `system_legacy_routes.py`(f-string prefix,ratchet §5⑦ 解析);今為 `tab-system.html`/`view-overview.js` 消費。
- `/api/v1/openclaw/status` → `openclaw_routes.py:947`(prefix `/api/v1/openclaw`);今為 `view-agents-openclaw.js:241` 消費。
- `/api/v1/system/startup-status` → `main.py:764`(literal `@app.get`);今為 `common.js` 消費。
- `/api/v1/healthz`(若採 build)→ `system_legacy_routes.py:325`;**E1a 須驗其 ∈ authoritative,否則改用 startup-status(已在集內)**。

---

## 4 · Tier A 驗證法(Mac-buildable,靜態)

1. **node --check**:`shell.js`(觸碰檔)全綠(LOOP §4;Data/Migrations §「GUI JS changes require node --check」)。
2. **grep 路由對齊**:逐條新 fetch `(GET, path)` grep 到後端路由定義(§3.3);跑 `tests/structure/test_gui_smoke_fetch_route_alignment_static.py` 綠(路徑 ∈ authoritative∪matched)。
3. **style ratchet**:`test_gui_style_ratchet_static.py` — shell.js/shell.html 維持 0/0/0(只加 `id` + JS 邏輯,無 hex/`<style>`/`style=`)。
4. **asset-ref / syntax smoke**:既有 glob smoke 自動納入,綠。
5. **cache-buster 紀律(F-R96-1 教訓)**:改 shell.js/shell.html → **bump `BUILD_TS` + shell.html `shell.js?v=`**(shell.js:37 註釋硬要求);`test_shell_js_cache_buster_matches_build_ts`(R99 guard)須綠。
6. **誠實邊界(綠 ≠ works)**:靜態只證 path/method/syntax 對齊;**chip 真值消費 / 三態真渲染 / auth 200 = runtime 事實**(NEEDS-LINUX,§8 operator console 只讀批驗)。

---

## 5 · Tier B 引擎數據契約 + NEEDS-LINUX

### 5.1 衡樑真傾角 — 引擎需發布什麼

| 契約項 | 值 | 來源 | 傳輸 |
|---|---|---|---|
| numerator(已用) | `total_exposure_pct`(相對可用保證金,0-100+) | Rust `h0_gate`(engine 更新,`h0_gate.py:134/270`) | P1.2 shared WS(push);**現況** REST `risk/status → h0_gate_stats`(engine-gated,`:472`) |
| denominator(上限) | `max_total_exposure_pct` | Rust config 權威(`risk/config → total_exposure_max_pct`,`:300`) | REST(config 面已可讀) |
| 衍生傾角 | `usedPct = total_exposure_pct / max_total_exposure_pct × 100`,餵 `setBeam(usedPct)`(shell.js:457,已備 seam) | 上二者 | — |
| warn 閾 | `usedPct ≥ 80` → `beam--warn`(shell.js:462 已備) | — | — |

**衡樑語義守恆(canon 9-11 / §09 §2-B)**:傾角 = 風控包絡已用/剩餘,青銅 accent 只給衡樑(canon 10);真值前 `renderBeamBlocked`(水平靜置 + `—`),**絕不假傾角**。

### 5.2 為何本 loop 不能建

- numerator 僅 running engine 存在(`is_engine_available` 閘,`risk_routes.py:464`)→ 需 engine 對驗;GUI loop **不 restart/rebuild engine**(LOOP §3)。
- §09 §10 + LOOP §6 已裁:衡樑真渲染 = P1.2 shared WS + engine 風控包絡,**NEEDS-LINUX**。
- Mac 上該值恆 null → 任何接線在 Mac 恆 blocked,零可驗行為。

### 5.3 建議傳輸(P1.2-b end-state)

**shared WebSocket**(§09 §10):engine → 控制面 → 單 WS → 殼按需訂閱 `risk_envelope`(取代 N-fan-out REST poll)。衡樑 + heartbeat/lease/PnL/latency 全走此通道。**契約細節(WS topic / 訊息 schema / engine publish 頻率)= P1.2-b spec**(未來 PA 設計,需 engine 側 Rust owner + Linux 對驗)。**過渡可選**:若 operator 要求先出「衡樑走既有 `risk/status` REST poll」的 Tier-A-stopgap,須另立裁決(本檔**不建議**,理由見 §2.2)。

### 5.4 下游依賴標注

- **V5 真渲染 = Linux runtime 目視**(衡樑真傾角 / chip 三態真值 / 帛晝 AA):**不在本設計範圍**,由 operator/Linux runtime 目視驗(§8;PROGRESS NEEDS-LINUX 欄)。
- **P1.2-b 引擎契約**:待 engine Rust owner + 未來 PA WS spec。

---

## 6 · Cutover 設計(`/console` → shell)+ 回滾 / fallback

### 6.1 現況

- `gui_legacy_routes.py:115 console_index`:`/console` → `FileResponse(console.html, _NO_CACHE_HEADERS)`(login 轉址守衛,`:119`)。
- `/`(`:99`)→ console.html;`/gui`(`:107`)→ index.html。
- `console.html:211`:`.header-btn` → `/static/shell.html`(「試用新殼」forward,LOOP §6 唯一 sanctioned 觸碰,已在)。
- **shell.html 已有反向 fallback**:`:137` `.legacy-link href="/console"`(「舊版」)+ `:154` `.view-error` 內 `href="/console"`(「返回舊版 Console」)。

### 6.2 最小改動(源碼 E1a-writable;**啟用 = NEEDS-LINUX 部署**)

**⚠ 回滾陷阱(前置硬要求)**:cutover 後 `/console`=shell,而 shell 的兩條 fallback 連結(:137/:154)仍指 `/console` → **無限迴圈回殼**。故 **cutover 前必先重指 fallback**,並保留一條**永久 legacy 路徑**。

**改動(建議 env-flag gate,傾向簡單但保一鍵回滾):**

1. **`gui_legacy_routes.py`**:
   - `console_index`(`/console`)flag-gate:
     `if os.getenv("OPENCLAW_GUI_SHELL_DEFAULT") == "1": return FileResponse(shell.html, _NO_CACHE_HEADERS)` else 維持 console.html。**default OFF** → 部署重啟後行為不變,operator 顯式設 `=1` 才 cutover(fail-safe;operator 已 §8 批驗 PASS,傾向硬翻但 flag 留一鍵退)。
   - **新增 `/console/legacy`**:無條件 `FileResponse(console.html, _NO_CACHE_HEADERS)`(復用 `_redirect_if_unauthenticated` 守衛,mirror `console_index`)= **永久 legacy 逃生口**。
2. **`shell.html`**:兩條 fallback(:137、:154)`/console` → **`/console/legacy`**(靜態改,免重啟,**須先於 flag=1 生效前落檔**)。
3. **`console.html`**:forward 連結(:211)已指 `/static/shell.html`,**不改**(cutover 後仍可從 legacy 前進新殼)。

**為何 env-flag 而非硬翻**:①一鍵回滾(unset flag + restart,免 git revert);②default OFF 使「部署 ≠ 立即翻臉」,operator 掌控翻轉時機;③與 §09 §6.2「乾淨 `/shell` 路由 = NEEDS-OPERATOR/RUNTIME」同治理級別。**硬翻(無 flag)亦可**(operator 已批),但失去免-revert 回滾——本檔**建議 flag**。

### 6.3 部署邊界(誠實標注)

- **shell.html 重指(改動 2)= 靜態,免重啟,即時生效**(StaticFiles)。
- **`gui_legacy_routes.py`(改動 1)= Python 路由改動,需 app 重啟才生效**(生產無 `--reload`)→ **NEEDS-LINUX/operator 部署**(觸 LOOP §3;同 §09 §6.2 乾淨路由裁定)。E1a 可**寫**源碼,**啟用**(git pull + restart + 設 flag)由 operator。
- **一鍵回滾**:unset `OPENCLAW_GUI_SHELL_DEFAULT`(+ restart)→ `/console` 回 console.html;或直接 `/console/legacy` 永遠可達(免重啟)。

### 6.4 是否需新 smoke test

- alignment/asset-ref/ratchet 為靜態 glob,**不覆蓋「路由 return 哪個檔」**。cutover 真驗 = operator §8 runtime(`curl /console` → shell body / `curl /console/legacy` → console body)。
- **可選 E1a**:一條輕結構 smoke 斷言 `gui_legacy_routes.py` 含 `/console/legacy` 路由 + `OPENCLAW_GUI_SHELL_DEFAULT` gate(防未來 cutover orphan console.html)。**低優,非阻塞**;PM 可 defer。

---

## 7 · E1a 實作分批建議(一批 = 單輪可完成 + 可驗 checkpoint)

**建議序(風險遞增,各批獨立可驗、獨立可回滾):**

- **E1a-1 · Tier A 遙測 chips(P1.2-a;最高價值,免重啟即部署)**
  範圍:§3.1 shell.html 加 id + §3.2 shell.js `wireControlPlaneChips()` poll + build(可選)。
  驗收:node --check shell.js 綠 / alignment ratchet 綠(路徑 ∈ authoritative)/ style ratchet 0/0/0 / cache-buster bump + guard 綠 / smoke 自動納入。
  效果:**消解 F-R96-2 頂欄側**;衡樑 + Tier B 遙測維持 blocked(canon 7)。
  → E2 對抗審查(核:零寫路徑 / canon 7 三態不 fake / 復用既有路由零新增 / visibility pause)→ E4-writer/verifier。

- **E1a-2 · Cutover plumbing(flag-gated OFF;源碼 Mac-buildable,啟用 NEEDS-LINUX)**
  範圍:§6.2 三改動(gui_legacy_routes flag-gate + `/console/legacy` 路由 + shell.html 重指 fallback)。
  **內部序**:先 shell.html 重指(靜態)→ 再 route 改動(default OFF)→ 同批 commit(operator 部署後行為不變,直到顯式 flag=1)。
  驗收:node --check(shell.html 無 JS 改則免)/ Python 語法(route handler parse→call→format,商業邏輯無)/ 靜態 smoke 綠。
  → E2(核:default OFF fail-safe / legacy 逃生口存在 / 守衛未弱化 / 零寫)→ E4。
  **啟用 = operator**:git pull + restart + `OPENCLAW_GUI_SHELL_DEFAULT=1`(§6.3)。

- **E1a-3 ·(可選)cutover 結構 smoke**(§6.4);低優,PM 可 defer。

**依賴**:E1a-1 與 E1a-2 無相互依賴,可任序;但 **E1a-2 的 shell.html 重指必須與 route 改動同批**(避免部署窗口內 fallback 迴圈)。衡樑 Tier B(P1.2-b)**不在本 loop**,待 engine 契約 + Linux。

---

## 8 · Open risks / uncertainty

- **[low] envelope 解包形狀**:`/system/control-plane` 回 `ResponseEnvelope`(payload 在 `.data`),但 `tab-system.html:861` 有處直讀 `cpd.execution_control_summary`(疑 ocApi 解包差異)。E1a **須 mirror 既有 `view-overview.js` 對同路由的確切 access path**(byte-parity reference),勿自造巢狀假設。
- **[low] engine_alive 語義**:`engine_alive` 為 runtime fact,Mac 無 runtime snapshot 恆 `null` → chip blocked(誠實)。**F-R96-2 消解 = 頂欄與 view 同源**;不宣稱「Mac 上看得到 engine 真存活」(那需 Linux runtime snapshot)。
- **[low] healthz ∈ authoritative 未親證**:build chip 若採 `/api/v1/healthz`,E1a 須 grep 確認在集內,否則改用 `startup-status`(已在集)。
- **[med] chip 值真確性 = runtime**:Tier A 源碼 Mac-可建可驗,但 chip **顯示的真值**依 runtime snapshot / engine 發布(Linux)。canon 7 妥善處理 null,故不阻塞建置——但 **operator §8 只讀批驗**才是三態真渲染的驗收(V5,NEEDS-LINUX)。
- **[low] cutover 部署重啟**:route 改動需 app restart(NEEDS-LINUX);flag default OFF 使部署與翻轉解耦,降風險。
- **硬邊界複核(通過)**:全程 read-only GET;零 order/activation;零 Python fake-success;Live 硬化面經 iframe/native view 既有路徑不碰(殼 chrome 不新增寫);IBKR 面零新增寫/激活 UI。

---

## 附錄 · architecture-depth-review 結果

- **Deletion test**:`wireControlPlaneChips`(刪 → 頂欄回硬編 blocked,F-R96-2 復現)/ `/console/legacy` 路由(刪 → cutover 後 legacy 不可達,回滾靠 git revert)/ shell.html id(刪 → shell.js 無法定位更新)——各刪各失一致能力,無 ceremonial。**未新增 Module/抽象**:復用既有路由 + ocApi + 既有 poll 慣例,通過 deletion test(不新造「遙測引擎」)。
- **Second-Adapter**:頂欄 chips = 既有路由(view 已消費)的**第二消費者**,零 policy 複製;未來 shared WS(P1.2-b)為第三 adapter,經同一 render seam(chip id + canon-7 renderer)接入,不改 poller 契約。**拒絕過早抽象**:不建 WS client(無 running engine 第二實作可驗),待 Linux 真有 WS producer 再引。
- **Authority/trust**:殼零寫、零 order、零 activation;所有真值 = out-of-band trusted producer(Rust 風控 + engine runtime facts + control-plane compiler)。衡樑無真值 → blocked,不自造。cutover flag 為 operator-gated env(default OFF fail-safe)。
- **Cross-runtime parity**:Tier A 讀 Python 控制面 compiled state(engine-independent 類別態);Tier B numerator 是 Rust engine runtime——**正確分置**,不以 Python REST 頂替 Rust 風控權威數值(§CLAUDE.md §四)。engine_alive 的 null-safe(Mac)↔ true(Linux)parity 由 canon 7 統一。
- **Failure/recovery**:ocApi 8s timeout → null → blocked;部分路由失敗只 blocked 該 chip;visibility hidden → pause;首載 loading;cutover default OFF + `/console/legacy` 永久逃生 + flag 一鍵回滾——確定性 fallback,殼不崩。
- **Consumption**:Tier A 復用既有 authoritative 路由(零新路由 = 零 alignment 負擔);~10s poll 低頻 + in-flight 閘 + visibility pause(不背景空轉);零新測試碼(smoke glob 自納)。shared WS(P1.2-b)是後續**優化**(取代 N-poll),一次性成本 > 現階段收益,故 defer,符「不為省而增假閉合/返工」。
- **實作 owner**:E1a(讀 srv:gui-style-guide + bilingual-comment-style)。**獨立驗證**:E2 對抗審查(核 canon 7 不 fake / 零寫 / 復用既有路由 / cutover fail-safe + 逃生口)→ E4-writer/verifier(node --check + ratchet 0/0/0 + alignment + cache-buster guard + smoke 自納)。**runtime 三態真值 / 衡樑真傾角 / cutover curl / 帛晝 AA = NEEDS-LINUX(V5-defer + operator §8)**,不由本刀 attest。

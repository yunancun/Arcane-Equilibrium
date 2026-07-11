# 08 · GUI Smoke Tests 設計正本(P1.0)

> PA-investigator 設計(2026-07-11,R44),PM 裁決 Option D。本檔=P1.0 實作正本;
> E4-writer 按「首批切片」實作,E4-verifier 獨立複核。驗收權威=LOOP-DRIVER §0.6/§4/§6。

## 0 · 裁決(PM,2026-07-11)
- **方案=Option D(靜態為主 hybrid,零新建置基建)**:延伸既有 `tests/structure/` 靜態守衛模式,
  複用**既有** pytest→node 子進程 seam(`test_gui_numeric_formatter_contract_static.py` 已用
  `subprocess.run(["node","-"], …)`+`pytest.skip` node 缺席);**不裝 jsdom、不建 package.json/node_modules**。
- **jsdom=DEFER 至 Phase 1**:jsdom 是新 devDependency + 新建置基建(npm install CI 步驟),
  且其獨有價值(真 DOM 跑 JS)與 NEEDS-LINUX-RUNTIME 集重疊(仍需 stub fetch/WS)。
  **重訪觸發=Phase 1 單文檔 `shell.js` view-router 落地**(首個值得執行 DOM-wiring 行為的 credible consumer,
  Second-Adapter 判準)。此為 PM/operator 決策點,非開發角色自決。

## 1 · 落地位置 + runner
- **擴 `tests/structure/`,不新建 `tests/gui/`**:既有 5 個 GUI 守衛已在此,formatter test 已從此 shell node
  →「structure」語義已含此類(靜態衍生守衛、可 shell node、絕不碰 live runtime/DB/WS)。同 pytest 發現,零新 config。
- **runner=pytest 驅動 node 子進程**(`node --check <file>`;DOM-free 契約用 `node -`),鏡像 formatter test 的
  `subprocess.run`+`pytest.skip("node 不可用")` graceful-degrade(node-less CI 自動 skip,契約一致)。
- **命名=`test_gui_smoke_*.py`**(如 `test_gui_js_syntax_static.py`/`test_gui_asset_refs_static.py`)。
- **anti-vacuous-green 紀律(鏡像 ratchet)**:每個掃描測試斷言「scanned-count 下限 + substantive-detector 錨點」,
  glob 壞掉/regex 被架空時大聲 fail 而非空綠。
- 與既有 61 GUI-guard 斷言零衝突(獨立 read-only 模組,不碰 ratchet BASELINE dict/scanned≥50 floor)。
  唯一成本=33+51 次 node 子進程;per-file parametrize 使單一失敗點名檔案。

## 2 · 首批切片(P1.0-impl 第一刀,單輪 E4 可驗)= 家族 (2)+(3)+(4)〔(1) 可選折入〕
**「syntax + reference-integrity floor」**——當前樹**即綠**(親證 33/33 JS 過 node --check;ref 是靜態檔查找),
首 commit=乾淨基線非清理專案;零 baseline curation、零路由解析複雜度(切片可控)。

- **(2) `node --check` 每 JS**:全 30 `*.js` + 3 `js/*.js`。把現行**手動** node --check sign-off gate 升為**強制** CI 測試。
- **(3) `node --check` 每 inline `<script>`**:27 HTML 內 51 inline JS block(tab-phase4 一檔就 8)**今日零覆蓋=最大盲區**
  (R45 E4 實測 27/51;原設計估 23/~55 為實作前低估——實際覆蓋更廣)。
  抽取每 block(濾 `type="module"`/`application/json`;偵測 top-level `await` 以 async-wrap 容忍——impl 細節,已由 E4-writer 處理),
  syntax-only 檢查(缺 browser globals `ocAuthCheck`/`document` **不**造成假失敗)。
  **前瞻 hardening(今日 0 影響,R45 E4-verifier 揭)**:抽取器以 script goal(CommonJS)解析,僅 top-level `await` 被 async-wrap;
  若**未來**新增 `type="module"` 的 inline `<script>` 且用 `import`/`export`,會被 node 判「Cannot use import outside module」假失敗
  → 屆時需 `--input-type=module` 分流(當前樹 0 個 module inline block,無現行假陽性)。
- **(4) asset-ref existence**:每 `<script src="/static/…">`/`<link href="/static/…">` 解析到真檔(strip `?v=` cache-bust)。
- **(1) 可選**:HTML parse/structure floor——每 `*.html` 過 Python stdlib `html.parser` 無例外 + 選定容器集
  (html/head/body/div/section/table/tbody/tr)tag-stack 平衡檢查。**誠實 caveat**:html.parser 是 HTML5-lenient
  (void 元素/隱式閉合),此為「parse-completes + container-balance」非嚴格 XML well-formed(抓粗未閉/錯套容器,
  =R8「裸屬性破版是 grep 盲區」類,非每個畸形屬性)。

E4-verifier 驗:當前樹全綠 + 逐斷言 red-proof(scratch copy 注入 syntax error/dangling src → 見點名失敗)+
scanned-floor/substantive-anchor 存在 + 對既有 GUI-guard 集無回歸(失敗者身分基線,非 passed 絕對數)。

## 3 · 後續切片(依序,勿混入首刀)
- **(5) fetch↔route 對齊矩陣(§0 終態 criterion-3 起點)**:抽 call-site 路徑(`ocApi`×173/`ocPost`×62/
  `apiGet`·`apiPost`×44/raw `fetch(`×29,~52 distinct literal path;方法可推:apiGet/ocApi-no-opts=GET,
  ocPost/apiPost=POST,ocApi(path,{method})需 opts-parse)↔路由清單(`*_routes.py` 的 `APIRouter(prefix=)`+
  decorator rel-path,及 `@app` 絕對路徑;prefix 在 APIRouter() 建立處非 include_router())。
  **明確 coverage-debt 處置**:template 插值/動態組路徑=靜態不可檢→列 declared debt allowlist,**絕不靜默通過**。
  設計為 ratchet/explicit-debt gate,非即時 100% 硬 gate(高工=獨立切片)。
- **(6) canon-7 假值守衛 — R49 調查後 DEFER(poor ratchet fit,非盲建)**:原設計為 curated-baseline ratchet,但 R49 實測揭 **grep-ratchet 是差配**:
  ①**數字假值面基本已清**——全站硬編 `0.00`/`$0.00`/`0.00%` **非-comment 顯示字面僅 1 個**(tab-paper.html:540 `totalMargin>0 ? ocBalance(…) : '$0.00'`,且屬 borderline-legit 真零 fallback);其餘 ~20 個 `0.00` grep 命中全是**canon-7 紀律註釋**(「永不回 '0.00'」「微額塌 0.00 假零」等)=P0.3 OC_EMPTY pass 已治理。
  ②**假成功不可 grep 判**——15+ `ocToast(…, 'success')` 全在 `.then`/await 後(response-gated,合法);fake-success(顯示已成功但後端 fail-open)是**語義**屬性,grep 無法辨 gated-vs-fake → ratchet 會 baseline 一堆合法 toast=噪音。
  ③grep-ratchet 對「硬編 0.00 vs 真零 0.00」無法區分 → Phase 2 會誤傷合法新真零 = churn。
  **裁決**:canon-7 已由 **OC_EMPTY formatter 契約(formatter test 覆蓋)+ P0.3 pass + code review** 執行;不建低價值噪音 ratchet。**DEFER**;若 Phase 2 遷移真引入硬編顯示假值再視需要建窄守衛(僅硬編 numeric 顯示字面,排除註釋+formatter+語義 toast)。tab-paper.html:540 屬 borderline-legit 真零,不強改。
- **(8) DOM-free helper load-time no-throw**:僅擴 formatter seam 到不需 document/window/fetch 的 helper
  (如 ocEsc 若純 string-escape:`node -`+最小 stub,斷言不 throw + `ocEsc('<a>')` 不吐 raw `<`)。窄範圍;
  觸 document/fetch 的 → Linux/headless。nice-to-have(formatter test 已錨 seam)。
- **(7) formatter 契約**:**已由 `test_gui_numeric_formatter_contract_static.py` 覆蓋**(06_numerics §5.2 dp/sign/sentinel),
  smoke suite **引用不重複**,零新工。

## 4 · NEEDS-LINUX-RUNTIME(或 CI-Linux headless;非誠實 Mac 可跑)
- `ocInjectBaseCSS`/`ocAuthCheck` 真 DOM load-time 行為(觸 document+fetch;即使 jsdom 仍需 stub fetch/WS)。
- 真 fetch round-trip / response 欄位消費正確性(路由真回傳被消費欄位)——需 FastAPI+engine。
- WebSocket 連線、live 新鮮度、**canon-7 三態 real/stale/blocked 真值渲染**——需 engine+WS。
- 全頁渲染、視覺回歸、衡樑傾角、雙主題玄夜/帛晝 **runtime AA 對比**(= LOOP-DRIVER §6 V5-defer + §1.3 AA ratchet)。
- 鍵盤走查 / focus order / a11y 互動。

> 誠實邊界:Mac 靜態 smoke 產出 implementation_contract/source 事實,**不能** attest runtime/真 fetch/三態真值;
> 綠的靜態 smoke **不得**被讀作「GUI works」。行為 gap 留至 Linux/headless(或 jsdom 決策)。仍移除今日最大執行風險
> (零自動 GUI 覆蓋)於任何 tab 遷移前。

## 5 · 切片 (5) fetch↔route 對齊矩陣 — 5a 調查結果 + 5b 實作規格(§0 終態 criterion-3)

> 5a=PA-investigator 調查(R46,read-only);5b=E4-writer 建 ratchet 測試(下輪)。

### 5a 實測(2026-07-11,PA)
- **權威路由=334 distinct (method, normalized_path)**(ast over 全 244 `control_api_v1/app/*.py`;247 decorator 因 `api_route(methods=[…])` fan-out 到 334;0 unresolved)。
- **GUI call-site=248 API-relevant**(294 wrapper 呼叫 − 46 nonapi[cards fragment/外部/相對]);distinct=153。
- **對齊:228 MATCHED / 14 DYNAMIC-DEBT / 2 REAL MISMATCH**。

### 5b 路由解析法(E4 必守;**優先 runtime introspection**)
- **首選**:test env 若能 import app → 讀 `app.routes`(`route.methods`/`route.path`)——FastAPI 已解析全部 prefix/include/nesting,**消除下列 AST 陷阱**且自維護。**勿手維護路由清單**。
- **AST fallback**(app import 拉不到 dep 時):①`include_router()` **不疊第二層 prefix**(main.py 全無 prefix= kwarg,單層);②prefix 綁在 `APIRouter(prefix=)` 建構子(per-file 解析,`router` 泛名在 7 檔不同 prefix);③**掃全 244 檔非 include 清單**(governance_router 跨 4 檔/live_router 跨 3 檔 side-effect decorator);④**⚠ two-level 陷阱**:`@core.live_router.get(…)`(`Attribute(value=Attribute)`)須解析**末層** attr(`live_router`),naive matcher 會漏掉全 16 個 `/api/v1/live/*` 交易面而**假報 drift**(PA 首過即中此,已修);⑤nested `paper_router.include_router(ai_cost_router)`→`/api/v1/paper/ai-cost`;⑥`@app` 絕對路由 ~60(5 個 `register_*_legacy_routes(app)`:auth/gui/system/learning/control + main;含頁面路由 `/`/`/login`/`/console`/`/gui`/`/trading`);⑦f-string:`control_legacy_routes.py:89 f"{settings.api_prefix}/system/scheduled-restart"`(api_prefix=`/api/v1`);⑧`{name}`/`{name:path}`→`{}`,`/openclaw/{path:path}`=prefix-match。
- **GUI 抽取**:ocApi(path,opts)→`opts.method||'GET'`(common.js:195)、ocPost/apiPost=POST、apiGet=GET、fetch(url,opts)→`opts.method||'GET'`;wrapper 全 verbatim 傳 path(無 base 前綴);balanced-paren + top-level comma split 取 arg0=path、掃 `method:`;normalize strip `?query`/`#frag`、`${…}`→`{}`、trailing-slash;分類 static-literal vs template/concat(param)vs bare-var(dynamic-base,實測 0)。

### 5b ratchet 設計(非即時 100% 硬 gate)
斷言:每個 GUI static/param `(method,path)` ∈ `authoritative ∪ DYNAMIC_DEBT_ALLOWLIST ∪ KNOWN_MISMATCH_ALLOWLIST`;**新增未匹配 path=fail**。兩 allowlist 為 checked-in 明列常量(增/減都過 code review;修好 mismatch=刪該列=收緊,絕不靜默放寬)。落 `tests/structure/`(命名如 `test_gui_smoke_fetch_route_alignment.py`)。26 個 `${param}`→`{}` exact-resolve 依賴 normalizer 正確(弱 normalizer 會假降級)。login.html 排除(他 session)→記為明列 coverage gap。**誠實邊界**:只證 path+method 形狀,不證 response 欄位真被消費/auth/200-vs-4xx(runtime,NEEDS-LINUX)。

**DYNAMIC_DEBT_ALLOWLIST 種子(14,concat-truncated,各解析到真 backend family)**:
`POST /api/v1/control/demo/{action}`(tab-settings:842)· `POST /api/v1/control/product-family/{fam}/config`(1119)· `POST /api/v1/learning/auto/{scan}`(tab-learning:231)· `POST /api/v1/learning/review/{id}/decide`(219)· `POST /api/v1/live/positions/{sym}/close`(tab-live.js:1201)· `DELETE /api/v1/paper/layer2/providers/{id}`(tab-ai:930)· `POST /api/v1/paper/positions/{id}/close`(tab-paper:604)· `POST /api/v1/paper/session/{action}`(tab-paper:402)· `GET|POST /api/v1/settings/api-key/{provider}`(tab-settings:1291/1411)· `DELETE /api/v1/strategy/{id}`(tab-strategy:360)· `POST /api/v1/strategy/{id}/{action}`(371)· `POST /api/v1/strategy/demo/positions/{id}/close`(tab-demo:1419)· `POST /api/v1/strategy/demo/session/{action}`(tab-demo:1290)。

**KNOWN_MISMATCH_ALLOWLIST 種子(2,附處置)**:
- **M1 `GET /api/v1/paper/status`**(governance.js:93)= **真 drift,但比 repoint 更深(R48 調查升級)**:三層失效——①dead route(後端無 `/paper/status`);②**shape mismatch**:GUI 建 `{positions:array, balance, total_orders}` ≠ `reconciliation_engine.py:255-256` 契約 `{orders:list, positions:dict, fills:list, snapshot_ts_ms:int, balances:dict}`;③`demo_state:null`→hub `remote_state=demo_state or paper_state`→**paper_state 跟自己比對→永遠 consistent**(退化 no-op)。**敏感度**:reconcile MISMATCH_MAJOR→**Risk escalate**/FATAL→**Auth freeze**(governance_hub 頭註),故錯誤形狀可致**假 escalate/假 auth freeze**。**現況安全但無效**(empty vs empty→consistent,不誤觸發)。**處置=NOT GUI-cosmetic-repoint**:需 governance-aware+Linux runtime 修(真 snapshot 契約+真 demo_state+reshape+runtime 驗證,或 product 決策移除)→**已 spawn 獨立 task `task_e86e4ad0`**(PA/E1 backend+GUI→QC/CC governance→Linux runtime)。GUI loop **不盲修 risk-escalation-feeding 路徑**(conservative-default/survival-first)。**M1 續留 KNOWN_MISMATCH_ALLOWLIST**(ratchet 保持可見),該 task 修好即刪列。
- **M2 `GET /api/v1/replay/handoff/state`**(handoff_helper.js:363)= **known forward-ref(HIGH)**:碼自證「Endpoint not yet shipped, Wave 8 sibling S13 in flight」+ graceful pending banner。**處置=allowlist(Wave 8 closure 建後端路由時刪)**,非 bug。

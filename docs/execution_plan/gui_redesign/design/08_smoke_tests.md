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
  唯一成本=~33+~55 次 node 子進程;per-file parametrize 使單一失敗點名檔案。

## 2 · 首批切片(P1.0-impl 第一刀,單輪 E4 可驗)= 家族 (2)+(3)+(4)〔(1) 可選折入〕
**「syntax + reference-integrity floor」**——當前樹**即綠**(親證 33/33 JS 過 node --check;ref 是靜態檔查找),
首 commit=乾淨基線非清理專案;零 baseline curation、零路由解析複雜度(切片可控)。

- **(2) `node --check` 每 JS**:全 30 `*.js` + 3 `js/*.js`。把現行**手動** node --check sign-off gate 升為**強制** CI 測試。
- **(3) `node --check` 每 inline `<script>`**:23 HTML 內 ~55 inline block(tab-phase4 一檔就 8)**今日零覆蓋=最大盲區**。
  抽取每 block(濾 `type="module"`/`application/json`;偵測 top-level `await` 需 wrap/skip——impl 細節,E4-writer 處理),
  syntax-only 檢查(缺 browser globals `ocAuthCheck`/`document` **不**造成假失敗)。
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
- **(6) canon-7 假值守衛**:grep HTML/JS **模板字面**內硬編 `0.00`/`0.00%`/假成功字串(非 formatter 計算輸出)。
  設計為**curated-baseline ratchet**(如 style ratchet;硬 ban 會誤傷合法字面)→需 baseline curation=獨立切片。
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

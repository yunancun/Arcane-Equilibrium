# R105 · E1a-2 Cutover Plumbing 實作報告

- 角色:E1a（玄衡儀 GUI cutover plumbing）
- 日期:2026-07-14
- 授權設計正本:`docs/execution_plan/gui_redesign/design/14_p1_2_wiring_and_cutover.md` §6.2 / §6.4 / §7 E1a-2
- worktree:`/Users/ncyu/Projects/TradeBot/.gui-loop-pub-wt/`（origin/main HEAD，含 R104 E1a-1 成果）
- 狀態:**IMPL-COMPLETE**(源碼落樹 + 全驗證綠;啟用=NEEDS-LINUX/operator 部署)

APP 前綴 = `program_code/exchange_connectors/bybit_connector/control_api_v1/app`

---

## 一、NO-OP 前置排除

開工前 grep 確認 `console/legacy` 與 `OPENCLAW_GUI_SHELL_DEFAULT` 在 app/ 與 tests/ 皆**不存在**,`gui_legacy_routes.py` 亦無 `import os` → 非 NO-OP,依設計實作。

---

## 二、改動清單(檔 + 行為)

### 改動 1 · `$APP/gui_legacy_routes.py`(Python 路由;啟用需 app 重啟)

| 項 | 行為 |
|---|---|
| import 區 | 頂部 stdlib 群加 `import os`(排在 `from pathlib import Path` 前,依 isort 直式 import 先於 from-import 慣例) |
| `console_index`(`/console`)flag-gate | 保留 `_redirect_if_unauthenticated` 守衛與 `_NO_CACHE_HEADERS` **零改動**;唯 FileResponse 檔案改條件:`if os.getenv("OPENCLAW_GUI_SHELL_DEFAULT") == "1": return FileResponse(_static_dir / "shell.html", ...)` else 維持 `console.html`。**default OFF**(未設或非 "1" → console.html) |
| 新增 `/console/legacy` 路由 | `@app.get("/console/legacy", include_in_schema=False)`;逐字複用 `console_index` 的 `_redirect_if_unauthenticated` 守衛;無條件 `FileResponse(_static_dir / "console.html", headers=_NO_CACHE_HEADERS)` = 永久 legacy 逃生口;緊鄰 `console_index` 定義後放置 |
| MODULE_NOTE | 路由清單 6→7 條(中英雙欄同步),補 `/console`(cutover flag 語義)+ `/console/legacy`(逃生口)描述,防 inventory 陳舊 |
| 注釋 | cutover flag 語義 + default-OFF fail-safe + 逃生口回滾陷阱 rationale,全中文(依 bilingual-comment-style 現規:新注釋預設中文) |

handler 維持 parse→call→format(僅選檔,零商業邏輯)。auth 守衛零弱化:`/console/legacy` 逃生口同樣先過 `_redirect_if_unauthenticated`,不引入未守衛的檔案暴露路徑。

### 改動 2 · `$APP/static/shell.html`(靜態;免重啟即生效)

| 行 | 前 | 後 |
|---|---|---|
| :143 | `<a class="legacy-link" href="/console" ...>舊版</a>` | `href="/console/legacy"` |
| :160 | `<a href="/console">返回舊版 · Legacy Console</a>` | `href="/console/legacy"` |

只改這兩處 href 值;文案/class/title/其餘一字未動。目的:cutover(flag=1)後 `/console`=shell.html,fallback 若仍指裸 `/console` 會回殼無限迴圈(design §6.2 回滾陷阱)→ 重指永久逃生口。
**未 bump cache-buster**:shell.js 未改,`BUILD_TS`/`?v=` 維持 r104,R99 guard(`test_shell_js_cache_buster_matches_build_ts`)仍綠。

### 改動 3 · `$APP/static/console.html` — 不改(確認)

forward 連結 `:211` 已指 `/static/shell.html`(cutover 後仍可從 legacy 前進新殼),無需改。

### 改動 4 · 新增 `tests/structure/test_gui_cutover_static.py`(純靜態 stdlib,零 runtime)

比照既有 `test_gui_smoke_*_static.py` 風格(ast/HTMLParser 抽 + scanned-floor + substantive-detector 有牙)。5 個測試:
- `test_route_extractor_scanned_floor` — ast 抽 @app.get 路由數 ≥6(防解析壞掉空洞綠)
- `test_console_legacy_route_exists_and_guarded` — `/console/legacy` 存在 + 含 `_redirect_if_unauthenticated` + 服 console.html
- `test_console_index_flag_gated_and_guard_retained` — `/console` 含 `OPENCLAW_GUI_SHELL_DEFAULT` gate + 兩檔分支(shell/console) + 守衛保留
- `test_shell_fallback_links_point_to_legacy_not_bare_console` — shell.html 兩條 /console* fallback 皆 `/console/legacy`,無裸 `/console`(≥2 floor)
- `test_extractors_are_substantive` — 合成正反例釘死 route ast 抽取 + 守衛偵測 + anchor 抽取 + norm strip 語義(防架空恆綠)

---

## 三、驗證輸出

### 1. Python 語法(py_compile)
```
$ python3 -m py_compile $APP/gui_legacy_routes.py
PY_COMPILE_OK gui_legacy_routes.py
```

### 2. shell.html 結構完整(node 首尾標籤平衡;無 JS 改故無 --check 目標)
```
html open/close 1 1 body open/close 1 1
SHELL_HTML_TAG_BALANCE_OK
```

### 3. 新 cutover smoke test
```
$ python3 -m pytest tests/structure/test_gui_cutover_static.py -q
.....                                          [100%]
5 passed in 0.02s
```

### 4. 回歸(gui / shell / ratchet / smoke 子集,含新增自動納入)
```
$ python3 -m pytest tests/structure/ -k "gui or shell or ratchet or smoke" -q
444 passed, 630 deselected in 6.13s
```

### 5. style ratchet 自證(shell.html 只改 2 href → 0/0/0 維持)
```
inline style= : 0
<style> block : 0
bare hex #    : 0
--- /console* hrefs 全為 /console/legacy ---
143: href="/console/legacy"
160: href="/console/legacy"
```
`test_gui_style_ratchet_static.py` 已含於步驟 4 綠集(shell.html 不在 BASELINE,預設 0/0/0,只改 href 值不觸三維)。

---

## 四、default-OFF 語義說明(fail-safe)

- **未設 / 非 "1"**:`os.getenv("OPENCLAW_GUI_SHELL_DEFAULT")` → `/console` 服 **console.html**(現行為)。故 operator 部署(git pull + restart)後**行為完全不變**,部署 ≠ 立即翻臉。
- **顯式 `=1`**:`/console` 服 shell.html(玄衡新殼 cutover 生效)。
- **一鍵回滾**:unset flag(+ restart)→ 回 console.html;或 `/console/legacy` 永久可達(免重啟,靜態直服),不需 git revert。
- shell.html 兩條 fallback 已先於 flag=1 重指 `/console/legacy`,同批落樹,避免部署窗口內 fallback 迴圈。

---

## 五、硬邊界複核(通過)

- **route 改動需 app restart 才生效** = NEEDS-LINUX/operator;E1a 只寫源碼,不設 flag、不 restart。default OFF 使部署後行為不變。
- **auth 守衛零弱化**:`/console/legacy` 逐字複用 `_redirect_if_unauthenticated`;無新增未守衛檔案暴露路徑。
- 殼 read-only;零寫 endpoint 新增;Vanilla JS 不引框架;Live 硬化面(五閘/授權/typed-confirm)未碰——cutover 只換 `/console` 服哪個檔。

---

## 六、殘留 / 下游依賴(NEEDS-LINUX,非本刀 attest)

- **cutover 真渲染驗收 = operator §8 runtime**:`curl /console`(flag OFF → console body / flag=1 → shell body)、`curl /console/legacy` → console body。靜態綠只證源碼結構不變量,不 attest runtime 三態。
- 啟用 = operator:git pull + restart + `OPENCLAW_GUI_SHELL_DEFAULT=1`(design §6.3)。
- 衡樑 Tier B(P1.2-b)不在本 loop,待 engine 契約 + Linux。
- git commit/push 由 PM 處理(E1a 未做任何 git 操作)。

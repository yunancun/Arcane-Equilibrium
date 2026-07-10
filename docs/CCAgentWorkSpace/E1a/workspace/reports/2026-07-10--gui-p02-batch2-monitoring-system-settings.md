# E1a GUI 改動 — P0.2 批次 2:monitoring/system/settings inline style 清理 · 2026-07-10

範圍:`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`
規格正本:`docs/execution_plan/gui_redesign/design/05_utilities.md`(下稱 §N 均指該檔)
狀態:**E1a IMPLEMENTATION DONE — 待 E2 + A3 + E4 review;未 commit**

## 一、觸碰檔案(每檔一行)

| 檔案 | 改動 |
|---|---|
| `tab-monitoring.html` | 27 處 style= → **0**;頁內新組件 `.card--flush`/`.gf-bar`/`.gf-icon`/`.gf-setup`/`.metrics-1col`/`.mv--sm`/`.mv--md`;JS 模板 2 處類化 |
| `tab-system.html` | 43 處 → **0**;頁內新組件 `.mv--sm/--md`/`.qa-chip-sm`(補死類名正本)/`.mode-flow`/`.mode-btn--live`/`.warn-box--live`(紫 relocate)/`.confirm-list`/`.metrics-2col`/`.metrics-fit`;MODE_CONFIRM 5 組模板 + loadSourceContext/loadHealth 模板類化 |
| `tab-settings.html` | 141 處 → **0**;頁內新組件 22 個(rst-banner/card--*/apikey-*/alert-*/pf-cap--*/slot-grid/btn-neutral/confirm-block--risk 等)+ 2 個既有規則擴充(confirm-modal-dialog width/oc-dialog max-width);**7 組 JS style 寫點 classList 化**(restart 三步/banner/qa-current-mode/warn-box/alert notes/alert body/capColors→capClasses) |
| `governance.js` | **NO-OP**(`style="`=0、`style='`=0、`.style.`=0、setAttribute('style')=0 程式證) |
| `oc-utilities.css` + 規格 §4 | §A 批次 2 追加 `ml-2`/`cursor-not-allowed`(§11 append-only,兩處同編輯,PA 認可待 review);追加後 §A 鏡像 normalized 一致 True |

## 二、驗證(逐項)

1. **度量(§0)**:monitoring 27→**0**;system 43→**0**;settings 141→**0**;governance.js 0→0。全站 `style="[^"]*"` 1,420→**1,210**(−210)。合法殘留(§7 scoped-var 屬性形式)= 無;**DEFER 清單 = 空**(全部 display/色 轉換點的寫點都在本批檔案內)。**量測歸因更正(E2 P0.2 批次 2 LOW)**:settings 的「141」不可由 `grep -o 'style="'` 對 HEAD 重現(同 regex 對 HEAD settings=140);重啟橫幅屬性跨兩物理行,line-based `grep -o` 兩行皆抓不到,先前「per-file grep -o 數到 141」歸因寫反。實質結論不變:settings 真屬性全清、全站 −210 對賬成立。
2. **node --check**:三 HTML inline `<script>`(排除 src=)抽取合檢 PASS(monitoring 6,999 / system 34,463 / settings 49,840 chars,附抽取長度斷言防空流假 PASS);governance.js 基線 PASS。
3. **HTML 結構**:三檔 HTMLParser tag-stack residue=0、errors=0;三連 link tokens→compat→utilities 程式斷言 3/3 未擾動。
4. **jsdom 兩態閉合 37/37 PASS**(真頁面函數 + mock 依賴驅動;事件→classList→CSS 規則存在三環):restart 三步 modal 顯隱閉環、rst-banner 顯/倒數歸零隱、qa-current-mode demo↔observe 兩態、dlg-apikey-warn-box live/live_demo/demo 三態(enum 類互摘)、alert-note 警示↔復位、alert-config-body 顯/網路斷 fail-closed 收回、mbtn active toggle 與 mode-btn--live 共存、qa-feed-chip wipe 後 qa-chip-sm 存活、pipe-status wipe 後父層 mv--md 命中、全部模板類產出斷言。
5. **零裸 hex / 零新 style=**:git added-lines `style="` 掃描=0;hex/rgba 掃描僅餘 2 行=紫色家族 verbatim relocation(見四.1,刻意);添加行 class token 110 個全解析到定義(JS enum 槽位逐一展開核對 PASS);註釋不含 grep 靶字面(批次 1 教訓,已把 4 條含原色值的註釋改為描述語)。
6. **鐵則檢查**:§3.1 已知 !important 面(entry-grid/oc-diff-changed)三檔零重疊;轉換元素 ID 在 common*.js/governance.js 的 style 寫點=0(跨檔證)。
7. **範圍**:未動 Python/Rust;worktree 兄弟髒改動(auth.py/tests/login.html/memory 檔等)未觸碰;僅 5 檔屬本批。

## 三、鐵則自查(每元素一行)

| 元素 | 鐵則 | 結果 |
|---|---|---|
| restart-step-1/2/3(settings) | 一(display 軸) | 寫點 L698-700/710-711/720-721(含 P2-14 guard 後死碼段,照轉),show 端原寫 '' → §3.3 引理,全部同批 classList 化,殘留=0 |
| restart-top-banner | 一(display 軸,show 端顯式 'flex') | §6 決策樹顯式值分支:`.rst-banner` 組件供給 display:flex + hidden 切換;寫點 ×2 同批轉,殘留=0 |
| alert-config-body | 一(display 軸) | 寫點 ×2(load 失敗收回/render 顯示)同批 classList 化,殘留=0;jsdom 斷言 fail-closed 路徑 |
| dlg-apikey-warn-box | 一(display+color 雙軸) | display 走 hidden(引理);color 三值 enum → `.apikey-warn--live/--livedemo` class-per-enum(§7),寫點 ×5 全轉,殘留=0 |
| qa-current-mode | 一(color 軸 enum) | `#qa-current-mode`/`.qa-mode--demo` 頁內規則 + `classList.toggle`,寫點 1 處轉,殘留=0 |
| alert-tg/wh-*-note | 一(color 軸兩態) | `.alert-note` 默認 dim + `.alert-note--warn`;alertMarkClear/加、_alertSetConfiguredNote/摘,殘留=0 |
| pf-cap / apikey-card / detail 色 / _alertCardStatus / exPerm | 一(模板 enum 內聯色) | capColors→capClasses、borderColor→cardCls、detailColor→detailCls、c→cls 全部 class-per-enum 查表,模板內聯色字串殘留=0 |
| pipe/tg/oc-status、grafana-badge(monitoring wipe) | 二 | 零直掛;字級走包裹層 `.oc-metric.mv--md/--sm`(9md+2sm) |
| m-stage/m-engine(wipe 家族)、dc-*(dc-valid wipe)、sys-info ×6(sys-decision-lease wipe) | 二 | 零直掛;wrapper 掛 mv--sm/mv--md(system 2、settings 3+6) |
| b-cost30(未 wipe,家族內唯一帶字級) | 二(判別) | 永不 wipe(僅 ocSetText)→ 直掛 `fs-md` 合法 |
| qa-feed-chip(wipe)/qa-demo-chip/qa-scanner-chip | 二 | `qa-chip-sm` 本就在 L958 wipe 重寫字串內(先前**死類名無定義**,本批補頁內正本)→ wipe 後類存活,jsdom 斷言;字號 10→11=oc-chip 基準,聲明省略 |
| alert-status-chip(wipe) | 二 | 零直掛;原 ml-auto 改父層 `row-between`(雙子元素等價);tg/wh state chips 走 `.alert-ch-head .oc-chip` 後代選擇器((0,2,0) 勝注入 (0,1,0)) |
| btn-set-demo/badges/cur-mode-chip/mode-badge/m-mode/m-auth/m-prot/qa-*-dot(wipe) | 二 | 本批未在其上掛任何類,零風險 |
| mbtn-live_reserved | 二(排除) | JS 僅 classList.toggle('active') 非 wipe → 靜態 `mode-btn--live` 安全,jsdom 斷言共存 |
| 全部新增行 class token | 拼寫 | 110 token + enum 槽位展開全數解析到定義(oc-utilities/頁內塊/注入 CSS);新類名 30 個全站既存使用 sweep 全 0(rst-banner 因 restart-banner-* 兄弟 ID substring 撞名而改名避讓) |

## 四、小決策與備註(理由)

1. **live_reserved 紫色家族 verbatim relocation(tab-system)**:`#a855f7` 系為 palette 外色(§5.5 禁新增色 token),但頁內塊既有 `.purple`/`confirm-live-guard`/`hold-bar` 全是同族紫且不在本批軸內——若把 inline 出現點單獨歸位 `--live` 會造成同一 modal 內紫紅混雜的中間態。故 3 處文字重用既有 `.purple`,2 處 border(`mode-btn--live`/`warn-box--live`)按原值遷入頁內塊(§8 第 3 級,淨效果 inline→塊),**零觀感變更**,P0.4 對紫色家族單點裁決;此為 added-lines hex 掃描僅餘的 2 行。
2. **settings 的紫(apikey live-demo 注記)按語義歸位 `--live`**:該處是孤點(頁內無紫色家族),且文義=「等同 Live 待遇」,canon 6/9 live 熱紅語義吻合;紫→紅為本批最大單點觀感變更,**A3 必審**。
3. **§A 追加 2 個 utility**(`ml-2`/`cursor-not-allowed`):§11 append-only,規格 §4 與 static 檔同批同內容追加(鏡像核對 True),批次註記已標;PA 認可掛在本批 review。
4. **父層字級修飾 mv--\* 用 var(--fs-\*) 而非字面 px**(與批次 1 console mc--\* 字面值不同):批次 1 字面值是 PA 計劃對側欄的特別裁決;本批 mv--\* 語義=「wipe 元素的 fs-dense/fs-md 等效替身」,用同 token 才與 utility 行為一致;且全站實測無任何 `data-density` 設置點,漂移目前純理論。
5. **§5.2 規則與對照表在 10px 上矛盾**(規則「等距取小」→8;表列 10→12):按表+批次 1 先例(oc-tc-meta 10→12)取 12;已在此標記請 PA 釐清規格文字。
6. **display:grid 單列 gap → `col gap-*`**:塊級子元素下 grid 單列與 flex column 佈局等價(無 margin collapse、同 stretch),省 5 個一次性組件。
7. **48px 裝飾 emoji → var(--fs-hero-lg)(32)**:§5.1 末行「逐點判」,判真 hero-lg 入頁內組件。
8. **`restart-status` 元素在 HEAD 就不存在**,`startRestartCountdown` 裸解引用會 throw——P2-14 停用流程的死路徑殘留(openRestartModal guard-return 使其不可達),**pre-existing 非本批引入**,列清理債。
9. **刻意視覺變更(§5 收斂,均為規格捨入/歸位;全列供 A3)**:gf-icon 48→32;健康分數 18→20(fs-title)、apikey 槽位 icon 18→20;各處 10px 字→11(fs-micro);mb/mt/gap 6→8、10→12、14→12 系列;mode-flow 內距 6/10→8/12、圓角 6→5;confirm-list 縮進 18→16;lh 1.7/1.5/1.55→1.6(lh-cjk);**色**:rst-banner 紅 .92→--neg 全濃度+暖白字+shadow-pop、confirm-block--risk 邊框紅 .3→--neg 全濃度(承批次 1 idx-banner 全濃度先例)+底 .05→--neg-bg、四張分類卡邊框 .28/.3→對應 -bg/weak 級(.11-.13,略淡但同 oc-card 默認髮絲線量級;藍系按 canon 1 中性化為青銅 accent-weak/border-subtle)、disabled 卡槽灰→border-strong、disabled chip→oc-chip-neutral、btn-neutral 槽灰→bg-hover、GitHub 紅/綠/黃字面值→玄衡 --neg/--pos/--warn 色相微移。
10. **palette 外色清單**:`#a855f7` 紫(處置見 1/2)、`rgba(71,85,105,*)` 槽灰 ×3(→border-strong/oc-chip-neutral/bg-hover)、`rgba(52,211,153,.28)` 翡翠(→pos-bg)、`#fff`/`rgba(255,255,255,.7)`(→text-primary/+opacity .7)、`rgba(240,192,64,*)` 舊黃 fallback(→warn-bg/t-warn)。
11. **留置(P0.4 候選;皆無軸衝突,元素未掛同軸 utility)**:tab-system mode-control-card `style.display`(L358)、live-hold-bar `style.width` ×5(§7 真動態,目標形態 scoped-var 屬所屬機制批次);tab-settings apikey-hint peek 色閃 ×2(批次 1 s-live-mode 同型先例)、alert-config-loading display/color ×4;common-modals oc-tc-meta whiteSpace(批次 1 已申報)、common-formatters 解說按鈕 style ×3(元素不在本批集)。
12. **雙主題**:本批新 CSS 全 token 化(唯一例外=紫 relocation 見 1);rst-banner 帛晝下玄墨字對 --neg 紅底對比偏低,存量文檔 data-theme="dark" 釘死故現無影響,解釘(P1.3)前併入紫色家族一起複審。

## 五、A3 必審項

1. apikey「Live-Demo 等同 Live 待遇」注記紫→--live 熱紅(四.2;與全 GUI live-demo 紫色慣例的張力)。
2. rst-banner 紅 .92→--neg 全濃度 + confirm-block--risk 邊框全濃度的觀感(死路徑 UI,但仍顯示於 markup)。
3. 四張分類卡邊框降為 -bg/weak 級髮絲tint(paper 綠/devsupport+alerts 青銅/apikey 琥珀)+ apikey 槽位卡 live 紅/livedemo 琥珀 tint——品類辨識度複核。
4. 健康分數 18→20、槽位 icon 18→20、gf-icon 48→32 的字階收斂觀感。
5. disabled chip 改 oc-chip-neutral(槽灰→標準中性灰)後「已停用」語義清晰度。

## 六、E4 回歸建議面

settings 四 sub-tab 切換 + restartModal 三步顯隱(死路徑但 markup 在)+ dlg-apikey 三槽位警示三態 + 告警卡(載入失敗態/clear 標記/save/test)+ 產品族卡(cap 標籤五色/toggle)+ apikey 槽位卡三色邊框;system 快捷列三 chip/模式流程條/live 確認 modal(purple 家族觀感)/健康分數字階;monitoring Grafana offline fallback/三組件卡字級/health detail 展開。1366×768 下 slot-grid(260px min)換行複核。

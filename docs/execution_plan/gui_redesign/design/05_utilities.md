# 05 — Utility Class 層規格(P0.2 inline style 清理 · spec-of-record)

> **地位**:本檔是 GUI 大修 Phase 0 P0.2(inline `style=` → utility class,8 批)的跨批接口正本。
> 批次 2-8 的 E1a 一律按本檔詞彙表與規則執行;詞彙變更走 §11 append-only 協議,不得原地改寫。
> 上游正本:`../GUI-DESIGN-WORKING-DOC.md`(§0 裁決/§3 canon)、`../tokens.css`(token 唯一正本)、
> `01_typography.md`(排級)、`02_layout.md`(排版)。
> 撰寫:PA,2026-07-10。基線量測與所有裁決附實測證據(static/ HEAD 當日 grep)。

---

## 0 · 範圍與度量

- **操作性度量**(P0.2 的「0」以此為準):
  `grep -rhoE 'style="[^"]*"' --include='*.html' --include='*.js' static/ | wc -l`
- **實測基線 2026-07-10 = 1,469**(工作文件 §4 的 1,375 為 07-08 快照,其後 stock-etf/GUI 工作使計數漂移;
  以 per-file ratchet(§10)吸收漂移,不追溯重測)。
- **計數對象 = `style="…"` 屬性出現次數**,含 JS 字串模板內的 `style="…"`。
  JS 屬性寫入(`el.style.display = …` 等,全 static 實測 159 處 `style.display` 寫點)**不在**本數字內,
  但受 §3.2(軸排除鐵則)與 §6(display 決策樹)約束:凡與被轉換元素同軸者,必須同批轉換。
- 文檔母體:static/ 下 22 份完整 HTML 文檔(`_dashboard_card.html` 與 `cards/*.html` 為無 `<head>` 的
  fragment,由宿主文檔供樣式,不接 `<link>`)。

---

## 1 · 檔案落點裁決(問題 4)

**裁決:獨立檔 `static/oc-utilities.css`,不併入 tokens.css,不鏡像 docs 正本。**

理由:
1. tokens.css 有 docs 正本(`docs/execution_plan/gui_redesign/tokens.css`)與 static 部署副本的
   雙鏡像關係,屬設計 canon、變更由設計裁決治理;utility 詞彙是**實作層**,在 8 批清理期間
   持續 append,混入 tokens.css 會迫使每批 utility 追加都做雙向鏡像同步(純摩擦,無設計價值)。
2. 生命週期不同:tokens 穩定;utilities 到 P0.4 樣式收斂後可能部分被組件層吸收。
3. tokens.css 檔尾基礎原子(`.num`/`.inscription`/`.silk`/`.seal-mark`)保留原地不動——
   它們是設計 canon 欽定原子;oc-utilities.css **不得重複定義**,只補其外的機械詞彙。

**內部結構**:
- **§A 詞彙表**(本檔 §4 的實作鏡像;append-only)。
- **§B 過渡組件附錄(annex)**:跨文檔 JS 模板產出的 enum 型迷你組件(如 `.oc-cat-tag`、`.oc-btn--xs`),
  因消費點跨 22 文檔、又不宜塞回 `ocInjectBaseCSS` JS 字串(P0 方向=CSS 離開 JS),暫居此;
  每條附 `/* P0.4: 併入組件層 */` 處置註記。

**`<link>` 接入**:
- 位置:所有 22 文檔統一插在 tokens-compat.css 之後,形成固定三連:
  ```html
  <link rel="stylesheet" href="/static/tokens.css" />
  <link rel="stylesheet" href="/static/tokens-compat.css" />
  <link rel="stylesheet" href="/static/oc-utilities.css" />
  ```
- 為何不追求「head 最末」:utility 全部 `!important`(§3),與非-important 規則的勝負與載入順序無關;
  而 tab 文檔的 `ocInjectBaseCSS` 是**運行時 append 到 head 的 `<style>`**,永遠排在所有靜態 link 之後,
  「link 放最末」本來就管不到它。統一三連位置換取 22 文檔零判斷的機械編輯。
- 時機:**批次 1 一次接齊 22 文檔**。未使用的 class 是惰性的,一次接齊零行為風險,
  換來批次 2-8 彼此順序無關、任何批都能立即用詞彙。

---

## 2 · 命名策略(問題 2)

**裁決:utility = bare 短名(kebab);組件 = `oc-*`;語義狀態 = `is-*`。**

- tokens.css 基礎原子已立 bare 先例(`.num`/`.silk`),utility 與其同族(單一用途屬性設定器),
  同用 bare;`oc-*` 保留給多屬性、有語義角色的組件(既有 `.oc-btn`/`.oc-chip`/`.oc-card` 慣例)。
  三族並存的判別:看到 `oc-` 就知道去組件層找定義,看到 bare 短名就知道是原子/utility,
  看到 `is-` 就知道是 JS 切換的狀態。
- **禁 px 數字命名**(不做 `mt-10px`/`w-80`):所有檔位名綁 `--sp-*`/`--fs-*` token 序數或角色名,
  token 調值時 utility 自動跟隨,不留死名字。
- 碰撞已實測:`row`/`col`/`wrap`/`block`/`mono`/`pointer`/`clip` 等作為**精確 class token**
  在全 static 使用數=0、CSS 定義=0(2026-07-10 exact-token grep;早前 `\brow\b` 誤中 `btn-row`
  類複合名的計數是 regex 邊界假象)。唯一既存:`hidden` 在 tab-settings.html 頁內定義
  `.hidden{display:none!important}` 且用於 1 處——與本規格宣告**逐字相同**,全局化後語義零變,
  tab-settings 所屬批次順手刪其頁內副本。

---

## 3 · Cascade 裁決:全體 `!important` + 兩條鐵則

### 3.1 為何 utility 一律 `!important`

被替換的 inline `style=` 具 inline 優先級(勝過一切非-important 規則)。若 utility 以普通
specificity(0,1,0)落地,會輸給:頁內 `<style>` 的後載同權規則、`.sidebar .mc-val` 這類
(0,2,0)後代選擇器、以及運行時 append 的 `ocInjectBaseCSS`。逐點審計每個轉換點的 specificity
在 8 批×1,469 點下不可維護。`!important` 使「utility 必然重現 inline 的勝負」成為結構保證,
審計成本從「全 CSS 面」縮到「該元素的 JS 寫點」(§3.2)。P0.4 收斂掉競爭宣告後可再議降權。

已知既存 `!important` 面(utility 不得與其同元素同屬性疊放;E1a 每批 grep 複核):
- `styles.css` `.entry-grid{gap:16px!important}` 與其 1 列響應式覆蓋(勿在 .entry-grid 元素上放 `gap-*`)
- `common.js` 注入 CSS `.oc-diff-changed{background/border-color !important}`(勿在其上放背景/邊框 utility)
- `tokens.css` reduced-motion 全停(與 utility 無交集)

### 3.2 兩條鐵則(本規格最大風險的結構性防線)

**鐵則一:JS 軸排除**——凡元素某屬性存在 JS `el.style.<prop> = …` 寫點,該元素**不得**掛同屬性
utility,除非同批把全部寫點改為 classList 操作。否則 `!important` utility 會壓死 JS inline 寫入,
狀態繪製靜默失效(例:`.is-stale{opacity:.5!important}` 會壓死 `style.opacity='1'`)。
轉換必須**元素級原子**:屬性 + 其全部 JS 寫點,一個 commit 內同批完成。

**鐵則二:className-wipe 陷阱**——凡元素在任何 JS 中被**整串賦值** `el.className = '…'`
(console.html 實測 20+ 處:`s-live-mode`/`s-api`/`s-oc`/`s-engine-alive`/`s-*-pnl`、
trading.html `regime-val` 等,每 30s 刷新即重寫),掛在該元素上的 utility 會在首次刷新被抹除。
此類元素**禁止**直接掛 utility;改用**父層修飾類**(父元素 className 不被 JS 觸碰):
頁內 `<style>` 加 `.mc--md .mc-val{font-size:14px}`,父 `.mc` 掛 `mc--md`。
E1a 逐元素檢法:`grep -n "getElementById('<id>')" <doc> <其載入的 js>` 追蹤變數,
再 grep `\.className\s*=` 與 `\.style\.` 寫點。

### 3.3 等價性引理(hidden 轉換的正確性依據)

當元素的 inline `display:none` 是其唯一 inline display 來源時:
`el.style.display=''`(現行 show 寫法)≡ `classList.remove('hidden')`——兩者都回落到
「CSS 規則/UA 默認」的 display 值。故 `''↔'none'` 型切換的 class 化是**證明安全**的,
無需知道元素可見時到底是 block 還是 flex。只有 show 端寫**顯式值**(`'block'`/`'flex'`)
時才需按 §6 決策樹判定。

---

## 4 · 詞彙表(問題 1;正本)

規則:只引用 tokens.css 變數;token 缺口以 `TOKEN-GAP` 註記字面值。全部宣告帶 `!important`
(§3.1)。檔內順序:多軸類(`m-0`)在前、單軸類(`mt-*`)在後,保證組合(`m-0 mb-1`)按後者勝出。

```css
/* ═══ oc-utilities.css §A 詞彙表(P0.2;append-only,變更走 05_utilities.md §11)═══ */

/* ── 1 文字色階(canon:降級用色階不用縮字號)── */
.t-primary{ color:var(--text-primary)!important; }
.t-dim    { color:var(--text-secondary)!important; } /* 舊 var(--text-dim) 395 處的歸宿 */
.t-muted  { color:var(--text-muted)!important; }
.t-warn   { color:var(--warn)!important; }           /* 舊 var(--yellow)/#d29922 系 */
.t-neg    { color:var(--neg)!important; }            /* 純文字紅;帶符號數值組件用 01_typography .val-neg(P0.3) */
.t-pos    { color:var(--pos)!important; }
.t-accent { color:var(--accent)!important; }         /* canon 10:僅焦點/選中/連結性 CTA */

/* ── 2 字階角色(canon 2:off-scale 收斂,對照表見 §5.1)── */
.fs-micro  { font-size:var(--fs-micro)!important; }   /* 9/10/11px → 11 */
.fs-dense  { font-size:var(--fs-dense)!important; }   /* 12px */
.fs-base   { font-size:var(--fs-base)!important; }    /* 13px */
.fs-md     { font-size:var(--fs-md)!important; }      /* 14px */
.fs-section{ font-size:var(--fs-section)!important; } /* 15/16px → 15 */
.fs-title  { font-size:var(--fs-title)!important; }   /* 18/20/22px → 20 */
.fs-hero   { font-size:var(--fs-hero)!important; }    /* 27/28px → 27 */

/* ── 3 字重(canon 2:僅 400/510/600;500→510,700→600)── */
.fw-medium{ font-weight:var(--weight-medium)!important; }
.fw-semi  { font-weight:var(--weight-semi)!important; }

/* ── 4 字族(僅字族;數字排版完整套件用 tokens.css .num)── */
.mono{ font-family:var(--font-mono)!important; }

/* ── 5 flex 家族 ── */
.row        { display:flex!important; align-items:center!important; }
.row-between{ display:flex!important; align-items:center!important; justify-content:space-between!important; }
.col        { display:flex!important; flex-direction:column!important; }
.wrap       { flex-wrap:wrap!important; }
.flex-1     { flex:1 1 0%!important; }
.ml-auto    { margin-left:auto!important; }

/* ── 6 間隙(--sp-* 檔位;收斂見 §5.2)── */
.gap-1{ gap:var(--sp-1)!important; }  /* 3/4/5px → 4 */
.gap-2{ gap:var(--sp-2)!important; }  /* 6/7/8px → 8 */
.gap-3{ gap:var(--sp-3)!important; }  /* 10/12/14px → 12 */
.gap-4{ gap:var(--sp-4)!important; }  /* 16px */

/* ── 7 margin(高頻方向 top/bottom + m-0/mx-1;多軸在前)── */
.m-0 { margin:0!important; }
.mx-1{ margin-left:var(--sp-1)!important; margin-right:var(--sp-1)!important; }
.mt-1{ margin-top:var(--sp-1)!important; }    .mb-1{ margin-bottom:var(--sp-1)!important; }
.mt-2{ margin-top:var(--sp-2)!important; }    .mb-2{ margin-bottom:var(--sp-2)!important; }
.mt-3{ margin-top:var(--sp-3)!important; }    .mb-3{ margin-bottom:var(--sp-3)!important; }
.mt-4{ margin-top:var(--sp-4)!important; }    .mb-4{ margin-bottom:var(--sp-4)!important; }

/* ── 8 padding(高頻檔位;chip/小按鈕的 2px 級內距屬組件,見 §8)── */
.p-2 { padding:var(--sp-2)!important; }
.p-3 { padding:var(--sp-3)!important; }
.p-4 { padding:var(--sp-4)!important; }
.px-2{ padding-left:var(--sp-2)!important; padding-right:var(--sp-2)!important; }
.px-3{ padding-left:var(--sp-3)!important; padding-right:var(--sp-3)!important; }
.py-1{ padding-top:var(--sp-1)!important; padding-bottom:var(--sp-1)!important; }
.py-2{ padding-top:var(--sp-2)!important; padding-bottom:var(--sp-2)!important; }

/* ── 9 寬度(定寬不設通用 utility,裁決見 §5.4)── */
.w-full{ width:100%!important; }

/* ── 10 顯示 ── */
.hidden{ display:none!important; }  /* 與 tab-settings.html 既有頁內定義逐字相同 */
.block { display:block!important; }

/* ── 11 文字雜項 ── */
.t-center { text-align:center!important; }
.t-right  { text-align:right!important; }
.nowrap   { white-space:nowrap!important; }
.pre-line { white-space:pre-line!important; }
.clip     { overflow:hidden!important; }

/* ── 12 行高/字距 ── */
.lh-cjk { line-height:var(--lh-cjk)!important; }      /* 多行中文段 1.6 */
.ls-wide{ letter-spacing:var(--ls-eyebrow)!important; } /* 舊 1px/0.5px 級手調字距歸宿 */

/* ── 13 透明度(機械過渡;TOKEN-GAP:無 opacity token。
       P0.4 複審:排版性降級應改走色階(canon),此類僅存真「圖層變暗」用途)── */
.o-50{ opacity:.5!important; }

/* ── 14 語義狀態(canon 7;JS 以 classList 切換)── */
.is-stale{ opacity:.5!important; }  /* 數據未就緒/過期變暗;就緒後 classList.remove */

/* ── 15 游標 ── */
.pointer    { cursor:pointer!important; }
.cursor-help{ cursor:help!important; }

/* ── §A 批次 2 追加(2026-07-10 P0.2 batch 2:monitoring/system/settings;§11 append-only)── */
.ml-2{ margin-left:var(--sp-2)!important; }              /* 家族 7 margin:高頻 margin-left 檔位(6/8px → 8) */
.cursor-not-allowed{ cursor:not-allowed!important; }     /* 家族 15 游標:disabled 控件 */
```

計 16 個 family、約 55 個 class(PM 目標 ~15 類 ±5 → 達標;「類」按 family 計)。
tokens.css 原子(`.num`/`.inscription`/`.silk`/`.seal-mark`)照用不重複。

---

## 5 · 收斂對照表(canon 2;渲染微變是設計意圖)

### 5.1 字階(inline 值 → utility → 渲染 px)

| inline | utility | 渲染 | 備註 |
|---|---|---|---|
| 9px / 10px / 11px / 0.8em / 0.85em | `fs-micro` | 11 | 實測 14+180+257+1+5 處 |
| 12px / 0.9em / 0.95em | `fs-dense` | 12 | 260 處 |
| 13px | `fs-base` | 13 | 59 處 |
| 14px | `fs-md` | 14 | 46 處 |
| 15px / 16px | `fs-section` | 15 | 2+24 處 |
| 18px / 20px / 22px | `fs-title` | 20 | 11+3+2 處 |
| 27px / 28px | `fs-hero` | 27 | |
| 32px / 48px | 元素屬 hero 級 → `fs-hero`;真 hero-lg 由所屬批次判 `font-size:var(--fs-hero-lg)` 入頁內組件 | 27/32 | 僅 3 處,逐點判 |

**CJK 12px 下限的刻意偏離**:01_typography §4.3 的 `.micro:lang(zh){12px}` 機制依賴正確的
lang 標註;存量 markup `<html lang="zh-CN">` 使 `:lang(zh)` 全域為真,現在烘進 `fs-micro`
會令全部 micro 變 12px(含純拉丁單位/ID)。**P0.2 的 `fs-micro` = 平 11px**;CJK 下限併入
P0.3 numeric/typography pass(該批補 lang 標註)。

### 5.2 間距(margin/padding/gap → `--sp-*`)

捨入規則(確定性,E1a 不得自由裁量):**取最近檔位;等距取小;1-3px 一律上取 4(永不取 0)**。

| inline px | 檔位 | 渲染 |
|---|---|---|
| 1 / 2 / 3 / 4 / 5 | `--sp-1` | 4 |
| 6 / 7 / 8 / 9 | `--sp-2` | 8(9 距 8 較近) |
| 10 / 11 / 12 / 13 / 14 | `--sp-3` | 12(14 等距取小) |
| 15 / 16 / 18 | `--sp-4` | 16 |
| 20 / 24 | `--sp-5` | 24(20 等距取小→16?否:|20−16|=4=|20−24| 等距取小=16→`--sp-4`) |

(20px 按規則歸 `--sp-4`=16;實測 inline 20px 間距極少,逐點過。)

> **10px 釐清(E2 批次 2 審查註記,2026-07-10)**:10px 依「等距取小」行文會得 8,但**以表為準歸
> `--sp-3`=12**——與 §4 `gap-3` 註記(`10/12/14px → 12`)及批次 1 已出貨先例(oc-tc-meta 10→12)一致;
> 「等距取小」tie-break 僅適用於 14→12 與 20→16,10px 是表定的唯一取大例外(與 §5.1 字階 10→11 同向)。

### 5.3 半徑 / 字重 / 邊框色

- 半徑:3/4/5/6px→`--r-1`(5);8/10px→`--r-2`(8);12/14px→`--r-3`(12);999/pill→數據控件禁用(canon 5)。
  半徑多出現於組件宣告,不設 utility,收斂在組件 CSS 內完成。
- 字重:500→`fw-medium`(510);600/700→`fw-semi`(600)。
- `color:var(--border)` 作**文字色**的 hack(10 處)→ `t-muted`(文字最暗合法階)。

### 5.4 定寬裁決(width:80px 類)

實測 `width:80px` 23 處**全部**落在 `input.oc-input` 數字欄位(tab-ai/tab-risk)。
**裁決:不設通用定寬 utility;`.oc-input--num{width:80px}` 組件修飾類入 §B annex**,
由 tab-ai/tab-risk 所屬批次應用(消費點跨 2+ 文檔故入 annex 而非頁內)。
其餘零星定寬(200/140/100px 等,各 ≤6 處):元素特定 → 所屬批次寫入**該頁既有 `<style>` 塊**
的具名組件/選擇器(§8 放置階梯),不入詞彙表。`min-width` 同理。
不採 scoped-var 方案(`style="--w:80px"` 仍是 style= 屬性,徒增 CI 白名單面;靜態定寬沒有動態性,
用 var 是偽動態)。

### 5.5 高頻 hex → token(P0.2 同批完成,§9 流程第 4 步)

| inline hex/rgba | token | 語義 |
|---|---|---|
| `#ef4444` / `rgba(239,68,68,*)` | `--live` / `--live-bg` | live 熱紅(canon 9 三紅歸位) |
| `#f87171` | `--neg` | 虧損紅 |
| `#d29922` / `rgba(210,153,34,*)` | `--warn` / `--warn-bg` | 琥珀 warn |
| `#388bfd` / `rgba(56,139,253,*)` | 中性資訊→`--text-secondary`;選中/焦點/CTA→`--accent`/`--accent-weak` | 承 tokens-compat `--blue` 中性化裁決,逐點二分 |
| `#8b949e` | `--text-secondary` | |
| `#30363d` / `#21262d` / `rgba(48,54,61,*)` | `--border-subtle`(強界 `--border-strong`) | 髮絲線 |
| `#3fb950` / `#22c55e` | `--pos` | |
| `#a855f7`(紫)等 palette 外色 | 無 token——按 canon 1 中性化或按語義歸位,禁新增色 token;逐點列批次報告 | |

---

## 6 · JS display 切換決策樹(問題 3;E1a 逐元素執行)

對每個含 `display:none` 的 inline `style=`(元素 E,文檔 F):

```
第 1 步 蒐集 E 的句柄:id、JS 查詢會用到的 class。
第 2 步 全域 grep(F 本體 + F 以 <script src> 載入的每個 JS + 注入模板來源):
        getElementById('<id>') / querySelector('…#<id>…') / '.'+class 查詢 /
        innerHTML 模板中再生成 E 的位置。
第 3 步 對每個命中變數綁定,grep 其 .style.display / .style.cssText /
        setAttribute('style' 寫點。
┌─ 無任何 display 寫點
│    → 靜態隱藏:inline 屬性刪除,class 加 `hidden`。完。
├─ 寫點存在,且 show 端全為 ''(hide 端 'none')
│    → §3.3 引理保證安全:屬性→`hidden` class;每個寫點改
│      classList.add/remove/toggle('hidden', cond)。
│      前提:E 與其全部寫點所在檔案都屬本批(元素級原子,鐵則一);
│      任一寫點在批外檔案 → 整個元素 DEFER(inline 原樣保留,計數留給
│      擁有該寫點的批次;批次報告記錄 defer 清單)。
├─ show 端寫顯式值('block'/'flex'/'grid'/'inline-block')
│    → 求 E 無 inline 時的可見 display(UA 默認 + 命中它的 CSS 規則):
│      a. 顯式值 == 該值(寫 'block' 的 div 等) → 冗餘顯式,按上一分支轉換。
│      b. 顯式值 ≠ 該值(JS 寫入承載佈局,如 span 被展成 block)
│         → 給 E 補靜態佈局類(row/col/block)使 CSS 供給該 display,
│           再按 hidden 轉換;沒把握或值非常量 → DEFER。
└─ display 值為運行時計算/三態以上
     → DEFER(留給所屬批次以組件狀態類重建;不塞 hidden)。
第 4 步 鐵則二檢查:grep `\.className\s*=` 命中 E → 本元素禁掛任何 utility,
        走父層修飾類(§3.2)。
第 5 步 驗收:兩態各實際觸發一次(手動/console 驅動),截圖或文字記錄入批次報告。
```

錯判防線總結:引理(''≡remove)消滅最大宗歧義;顯式值分支強制求「無 inline 的真 display」;
跨檔寫點一律 DEFER——**寧留 inline 一批,不賭永久隱藏/顯示**。

---

## 7 · 合法殘留與動態值(問題 5)

Phase 0 結束時 static/ 合法的 inline style 形態**只有兩種**:

1. **JS scoped-var 寫入**(canon 唯一豁免):`el.style.setProperty('--x', v)`,
   由 class 消費(`.meter-fill{width:var(--x,0)}`)。
2. **其屬性形式**(innerHTML 模板流無法在插入前 setProperty 的等價物):
   `style="--x:42%"`——**只允許 custom property**,一條或多條,禁夾任何真屬性。
   CI 判別 regex(P0.6 采用):`style="(\s*--[a-z0-9-]+:[^;"]*;?\s*)+"` 之外的 `style="` 皆違規。

真動態值過渡方案:
- **進度條寬度**(trading.html `refresh-bar`、各 tab meter):目標形態 =
  `.meter-fill{width:var(--progress,0%)}` + JS `setProperty('--progress', pct+'%')`。
  現存 JS 屬性寫入(`bar.style.width='30%'`)不在 P0.2 計數內,**不強制本階段轉換**;
  但凡所屬批次觸碰該元素(它帶其他 inline style=)時,順手按目標形態轉,禁半吊子。
- **圖表/canvas 定位、toast 疊放偏移**(common.js `style.bottom/top`):同上,P0.4 統一收。
- **enum 型「動態」**(模式色、分類色、狀態色):**不是**動態值,一律 class-per-enum
  (`data-cat` / `.mode-*` / `.is-*`)入組件層;禁用 scoped-var 偽裝。

---

## 8 · 放置階梯(每個被替換的 inline 樣式的歸宿判定)

自上而下取第一個滿足者:

1. **詞彙表 utility**(§4)——單屬性、值落檔位。
2. **語義狀態類 `is-*`**——JS 切換的狀態(stale/active/…)。
3. **頁內既有 `<style>` 塊**——頁面特定的多屬性組合/一次性組件(如 console 側欄切換鈕、
   trading kv 行)。只允許寫入**既有**塊;無塊的文檔(如 index.html)升到第 4 級。
   (頁內塊本身是 P0.4 的收斂對象;本階段淨效果=inline→塊,朝正確方向。)
4. **styles.css**——console/index/login/trading 殼層文檔共享的組件。
5. **oc-utilities.css §B annex**——跨 tab 文檔的 JS 模板組件(common*.js 產出)。
6. 以上皆不合(整組件級重造)→ **DEFER 至 P0.4**,inline 保留,入批次報告 defer 清單。

---

## 9 · E1a 每批標準流程

1. `git fetch` + 讀本檔;跑 §0 度量取當前 per-file 計數,鎖定本批檔案清單。
2. 逐檔 `grep -nE 'style="[^"]*"' <file>` 取行號×值;每條按 §5 對照表寫映射
   (值→class 串,或 §8 階梯落點),先成表後動手。
3. `display:none` 條目走 §6 決策樹;含 JS 寫點的元素做元素級原子轉換(鐵則一);
   任何元素轉換前過鐵則二(className-wipe)。
4. 同 attribute 內的 hex/rgba 同步按 §5.5 落 token;palette 外色列報告。
5. 需要新 utility:先按 §11 追加詞彙(獨立小 commit + PA 標記),再用。
6. 驗收:`node --check` 全部被改 JS(含 .html 內嵌腳本抽驗);§0 度量重跑,
   本批檔案計數=0(或=defer 清單數);JS 切換元素兩態實測;雙主題(玄夜/帛晝)各過目一次。
7. 批次報告:映射表、defer 清單、palette 外色清單、計數前後。

---

## 10 · CI 守衛接口(問題 7;P0.6 預埋)

**定調:per-file ratchet 白名單。**倉內落一份 `{file: inline_style_count}` 基線表;
guard 對 static/ 每檔計數(排除 §7 custom-property-only 形式):
計數 > 基線 → fail(禁新增);批次完成即把該批檔案基線降為 0(進入嚴格名單,永不回升)。
全部 8 批完成後基線表退化為「全 0 + regex 豁免」,P0.6 再併入 `<style` 與 raw-hex 兩軸(canon 8)。

---

## 11 · 詞彙治理(跨批接口穩定性)

- oc-utilities.css §A 與本檔 §4 **append-only**:新增 class 允許(檔尾追加 + 批次註記 + PA 認可);
  **改名/改宣告/刪除既有 class 一律禁止**(批次間的類名就是接口),直到 P0.4 統一複審。
- 兩處(本檔 §4 與 static 檔)以本檔為 spec、static 檔為實作;追加時兩處同 commit。
- 組件層(annex/頁內/styles.css)不受 append-only 約束,按普通代碼評審。

---

## 12 · 降級 / Rollback

- oc-utilities.css 純 additive、無 JS 依賴;未被引用的 class 惰性,檔案本身可獨立 revert。
- 每批 = 獨立 commit(檔案互不重疊),rollback 單位 = 批次 commit `git revert`;
  無 runtime/schema/API 依賴,iframe 架構未觸碰。
- 若需撤 utilities 檔本身:必須連同已引用它的批次 commit 一起 revert(否則 `hidden` 失效
  → 被隱藏元素露出)。緊急止血序:先 revert 批次 commit(恢復 inline),utilities 檔可留
  (惰性),再擇機清理。
- 視覺回滾錨點:git tag `gui-baseline-2026-07-09`。

---
*變更記錄:2026-07-10 PA 初版(P0.2 批次 1 前定稿)。*

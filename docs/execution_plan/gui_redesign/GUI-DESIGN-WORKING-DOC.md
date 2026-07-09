# 玄衡 Console — GUI 大修 · Design Working Document

> **Precompact anchor.** This is the single durable reference for the ground-up GUI redesign.
> The four deep specs are linked in §4; resume aesthetic work by *refining* them, not re-deriving.
> **2026-07-10 起正本移入 repo:`docs/execution_plan/gui_redesign/`**(原 scratchpad ephemeral 副本已救援)。

---

## 0 · 2026-07-10 operator 裁決 — 「玄衡儀」視覺主張(在 S1 骨架上收斂美學)

Operator 三項裁決(原文:「1 我認可你修改的主張 2 可以開始做。關於色彩我認同暖調近黑,但我希望你能考慮 light and dark mode 切換」):

1. **「玄衡儀」主張認可**——GUI 身分=「一台觀測市場的儀器」而非「另一個交易所界面」。具體元素:
   - **玄衡五色**:玄(暖近黑 `#171114`,黑而有赤)/帛(暖白文字)/青銅(唯一品牌 accent,答 §10-Q1)/朱(鈐印,只給權威態:sealed/authority,以印章形制與虧損紅雙重區分)/松煙(暖灰次要)。
   - **Signature = 衡樑**:頂欄常駐青銅髮絲線秤樑,實時映射風控包絡已用/剩餘;全站唯一環境動效預算。
   - **銘文標題**:思源宋體只用於面板題/報告大標,每屏 ≤3 處(aesthetic risk,節制)。
   - **雙密度檔位**:儀表態(規格表密度,teenage-engineering 式絲印標籤)/卷宗態(復盤/審計/報告,編輯排版 ~65ch)。與既有 comfortable/compact density 正交:density 調行高,檔位調頁面性格。
2. **色溫裁決:暖調近黑**——修訂 §1 S1 定義中的「cool near-black neutrals, one cool accent」為暖調;S1 其餘決策(dark-primary、monochrome chrome、色彩=數據語義、luminance 海拔、tabular-mono、密度優先)**全部不變**。§2 token block 的調色值由同目錄 **`tokens.css`** 取代(結構性 token:字階/間距/密度/動效/半徑沿用 §2 原值)。
3. **Light/dark 雙主題=真目標**(答 §10-Q7)——非 courtesy。設計語言:**玄夜**(玄底帛字,黑漆儀器)/**帛晝**(帛底玄字,絹紙卷宗),同一五色在兩地面互換角色而非數值反轉;`--live` 熱紅兩主題永不稀釋(canon 6 不變)。切換=OS 偏好默認+顯式 toggle 覆蓋(`data-theme`)。

裁決依據與參考庫:`docs/references/2026-07-09--gui_redesign_reference_board_v2.html`(玄衡儀主張+跨界參考;artifact 版本記錄含 v1 五方向)。方法論:Anthropic frontend-design skill(已裝 operator `~/.claude/skills/frontend-design/`)。

**本裁決的樣品正本 = `2026-07-10--xuanheng_live_view_sample.html`**(同目錄;雙主題+雙密度+衡樑+朱印,以 Live/LiveDemo 真實內容結構為底)。

---

## 1 · Locked decisions
- **Visual direction = S1 "Terminal"** (chosen over S2 "Cockpit"): dark-primary, monochrome chrome, saturated color reserved for data/state only, elevation by luminance/hairline (not shadow), ~~cool~~ near-black neutrals, one accent, tabular-mono numbers. Instrument-grade, austere, max scan-speed. **[2026-07-10:色溫與 accent 由 §0 裁決修訂為暖調+青銅;其餘不變]**
- **Architecture endgame = strangler-fig: iframe-per-tab → single-document shell** (view-router + one shared WebSocket/data layer). Trading-critical tabs migrate LAST behind flags; iframe fallback retained through Phase 2.
- **Framework = Vanilla JS + CSS custom properties only** (governance hard rule: no React/Vue/Angular, no build step). Three-tier tokens: primitive → semantic → component.
- **Information architecture = lane × environment** (asset lanes Crypto Perp·Bybit / Stock·ETF·IBKR as peers; environment ladder research→replay→paper→demo→live; cross-cutting: governance/risk/AI/learning/monitor/settings). Replaces the current 6 topical groups. Every write surface gets exactly ONE home.
- **Status: Phase 0 已由 operator 2026-07-10 放行開工**(§0);工程執行按 §9 role chain 派發。

---

## 2 · Canonical design system — `tokens.css` (single source of truth)

> **2026-07-10:調色值正本 = 同目錄 `tokens.css`(玄衡儀雙主題版)**;本節原 token block 的結構性部分(字階/行高/字距/字重/數字特性/間距/半徑/密度/動效/focus/reduced-motion)沿用不變,已併入 tokens.css。Ban inline `style=` and per-page `<style>`; the ONLY sanctioned style attribute is JS writing a scoped var (`el.style.setProperty('--x', v)`), consumed by a class。原 cool 調色值(GitHub-Primer-ish)留存於 git 歷史與 S1 樣品,不再是目標。

結構性基線(摘要;完整見 tokens.css):
- 字階(px):11 / 12 / 13(重心)/ 14 / 15 / 20 / 27 / 32;CJK line-height 1.60。
- 字重:400 / 510(workhorse)/ 600;數字:mono + `tabular-nums slashed-zero` + 右對齊。
- 間距 4px 基;半徑 5/8/12(數據控件永不 pill);密度 comfortable 34px / compact 27px 行高。
- 動效:120ms/200ms functional-only;`prefers-reduced-motion` 全停(衡樑亦靜止,以靜態傾角呈現)。

---

## 3 · The non-negotiable rules (the "canon")
1. **Monochrome chrome; color = a claim about risk/PnL.** 95% neutral gray ramp; hue is earned by data/state only. Accent appears on data, not decoration.
2. **Hierarchy by weight + color + case, NOT size.** Budget: ≤4 type levels per region, ≤6 per page. Size separates only structural tiers (11 / 12–13 / 15 / 20 / 27).
3. **Numbers: mono + `tabular-nums slashed-zero`, right-aligned, decimal-aligned.** Every PnL/direction/status carries a SECOND channel (sign +/−, ▲▼, LONG/SHORT text, icon) — grayscale-survivable (CVD-safe). Precision: USD 2dp, BTC 6dp, % 2dp, bps 2dp.
4. **Bilingual: Chinese primary visible, English on `title=`/tooltip (or global lang toggle).** Kill the ~480 inline zh/en double-labels. Only irreducible technical tokens stay inline English (`system_mode`, `bps`, `S0-S4`, symbols, endpoints). **Never `uppercase` on CJK.**
5. **Elevation by luminance + hairline borders, not shadow** (shadows "punch holes" on near-black). Single soft shadow reserved for true overlays (modal/popover) only. **Never pill-round a data control** (radii 5/8/12).
6. **Real-money hardening never dilutes.** `--live` hot red stays saturated in both themes; live/flatten actions = typed-confirm, physically separated from benign controls, persistent ⚠ REAL FUNDS.
7. **Data states never collapse into one:** real value / loading (skeleton at exact row height) / no-data (em-dash `—`) / stale (dim ~50% + freshness badge + last-updated ts) / blocked/not-collected (explicit label, e.g. IBKR "帳戶未連線 · 待 Phase 2") / contract-violation (loud). Never show `0.00` for unknown/loading.
8. **One shared design stylesheet; zero inline sprawl.** Enforce with CI grep for `style="`, `<style`, raw hex in templates.

**[2026-07-10 增補,承 §0]**
9. **朱印紀律:三種紅各司其職,形色雙分。** `--neg`(虧損/下跌,文字紅)/ `--live`(真金熱紅,badge/banner+⚠,永不稀釋)/ `--seal`(朱鈐印,只給 sealed/authority 態,只以方印形制出現,絕不做文字色)。任何新紅色需求必須歸入三者之一,不得新增第四紅。
10. **青銅紀律:accent 只給焦點/選中/衡樑/品牌刻度,不給數據不給裝飾**;warn 用琥珀橙(`#D98E1F` 系)與青銅拉開,且 warn 必附 ⚠(canon 3 第二通道)。
11. **銘文紀律:宋體只出現在面板題與卷宗態大標,每屏 ≤3 處;數據區永不用襯線。**

---

## 4 · Deep specs (full detail — linked, ~1,767 lines total)
| Dimension | 中文 | File | Contains |
|---|---|---|---|
| Typography & type-hierarchy | 排級邏輯 | `design/01_typography.md` | full type-role table, hierarchy-encoding logic, numerics, CJK+Latin mixed-run handling, density deltas, worked examples |
| Layout, grid & spatial rhythm | 排版 | `design/02_layout.md` | shell dims, 4px spacing application per component, panel/KPI/table/ladder anatomy, one consolidated breakpoint scale, mobile status-strip (keeps engine/mode/PnL), density modes |
| Copy, microcopy & bilingual labels | 文字 | `design/03_copy.md` | voice/tone, bilingual discipline + decision tree, canonical labels lexicon, state/status wording, action/confirm copy, empty/error states |
| Visual identity | 美學設計 | `design/04_identity.md` | full neutral ramp (step-roles, light+dark hex), elevation ladder, **icon strategy** (rationalizes current inconsistent emoji), motion, state visual language, focus/a11y, light mode, identity principles |

> 2026-07-10 note:四規格為 S1 冷調時期產物,**排級/排版/文字三份與色溫無關,照用**;`04_identity.md` 的 neutral ramp 色值按 tokens.css 玄衡版重讀(step-role 邏輯不變,hex 以 tokens.css 為準)。

**Key concrete findings already surfaced (from the specs):**
- Current live GUI tokens are GitHub-Primer-ish (`--bg #0d1117`, `--accent #58a6ff`) — close to but NOT the targets → retune.
- **1,375 inline `style=`** (the cleanup target); **83 hex** colors; radii chaotic (14px×9, 8px×7, plus 3/4/6/10/12/18/999 → canon 5/8/12).
- **Emoji-as-icon is pervasive and inconsistent**: ⚠×77, ✓×38 competing with ✔×4/✅×7, ✗×13 vs ✖×2/❌×8, 🔴 overloaded for BOTH live and error → needs a single disciplined icon strategy (see 04_identity §3).

---

## 5 · Problem analysis + content conservation (audit summary)
**Three structural root causes of the "bloat":**
- **A · iframe-per-tab** — 18 tabs = 18 documents; 143KB shared JS + 303-line CSS re-parsed per frame; 7 bare-string postMessage types; focus/hotkeys fragment across frames; N duplicate WebSockets (per-tab freshness = safety risk).
- **B · token fork + inline sprawl** — tokens in 3 places (styles.css / common.js hardcoded / console.html inline); 1,375 inline `style=`; 83 hex; "profit green" exists in ≥4 variants, red in ~5 → violates own principle "顏色語義固定".
- **C · KV walls, no disclosure** — stock-etf 19 tiles + 20 always-open panels + 712 KV / 0 `<details>`; risk/governance 200+ inline styles; ~480 inline zh/en double-labels.

**Content conservation (proven, zero silent loss):** 210 distinct surfaces → **KEEP 115 · RELOCATE 38 · MERGE/dedupe 26 · COLLAPSE-behind-disclosure 12 · FLAG-DEAD (removal candidate, needs evidence) 19**. Sum conserved. Dedupe seams handled: global-mode (system+settings)→one home; risk-deescalate (risk+governance)→one home; three close-alls kept per-environment; Live emergency-stop vs close-all are distinct capabilities both kept. **One live gray-area:** `app-learning.js` holds the ONLY observation/lesson/hypothesis/experiment INPUT forms but is already orphaned (not loaded) → explicit revive/retire decision at migration, never silent drop.

---

## 6 · Samples
- **玄衡儀(2026-07-10 裁決正本):`2026-07-10--xuanheng_live_view_sample.html`**(同目錄)——雙主題(玄夜/帛晝)+雙密度+衡樑+朱印+銘文,以 Live/LiveDemo 真實內容結構為底。
- S1 "Terminal"(冷調,歷史采納樣品):`2026-07-08--s1_terminal_sample.html`(同目錄)/ artifact https://claude.ai/code/artifact/07c769ec-b340-4118-812f-27decdaa2ea8
- S2 "Cockpit"(未採納,參照):artifact https://claude.ai/code/artifact/23c24c3a-8b5e-4586-ac35-e33a06a82b7b
- 設計參考圖鑑 v2(玄衡儀主張+跨界參考):`docs/references/2026-07-09--gui_redesign_reference_board_v2.html` / artifact https://claude.ai/code/artifact/8da08872-cab2-4a34-9f99-257f6a8384a8

---

## 7 · Implementation state (shipped)
Committed + three-end synced (Mac=origin=Linux) at **`c66338e8b`**:
- **AMD-2026-07-08-01** — IBKR Phase 2 read-only external-contact authorization (`fae556847`).
- **win① GUI fake-$0 honesty fix** + **G0.5 CI guard job** (`0ce7534a3`) — E2 APPROVE, node --check, 25 guard tests pass.
- **win② risk-TOML→Rust wiring (P0)** (`c66338e8b`) — Linux cargo verified (caps 1000/5000/10000/5/10 load).
- **GUI大修 Phase 0:operator 2026-07-10 放行,工程執行待派發(§9)。**
- Runtime note: Linux engine NOT rebuilt/restarted → win② display change needs a future authorized `restart_all --rebuild`.

GUI root: `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`
Shell: `console.html` (TABS array). Shared: `common.js` (`ocInjectBaseCSS` 303-line CSS string), `styles.css` (651 lines), `common-formatters.js`, `common-modals.js`, `i18n_zh.js`.

---

## 8 · IBKR backend track (handed off — do NOT pursue in this session)
A clean startup prompt was given to the operator for a separate session. State: G0/G0.5/P0 done at `c66338e8b`; next = P1 (Rust fingerprint-only secret-slot loader) → P2 → G4 (operator one-time approval for first external contact) → P3 (IB Gateway + Rust read-only TWS client). Governance: read-only / zero real money / live·tiny-live denied. See TODO row `P1-IBKR-STOCK-ETF-PHASE2-READONLY-EXTERNAL-CONTACT` + `docs/governance_dev/amendments/2026-07-08--AMD-2026-07-08-01-*.md`.

---

## 9 · Phase 0 execution plan (operator 已放行 2026-07-10)
Role chain PM→PA→E1a→E2→E4. Reversible, stays inside existing iframes, zero architecture risk:
1. Extract single `tokens.css`(**正本=本目錄 tokens.css 玄衡儀版**), `<link>` from all tabs, delete the JS-injected `:root` + console.html inline `:root` (kills the 3-way token fork + unstyled-flash race).
2. 1,375 inline `style=` → ~15 utility classes; 83 hex → ~12 semantic tokens.
3. Numeric-typography pass (tabular-nums + right-align + redundant encoding everywhere).
4. Consolidate onto `oc-*` primitives; delete `live-*`/`se-*`/`rc-*`/`gov-*` forks; freeze section-header/card/metric/chip.
5. IBKR lane: semantic chips (DENIED/PRESENT/MISSING/OK) + governance banner + the fake-$0 fix (already shipped).
Later: Phase 1 (single-doc shell + view-router + shared WS) → Phase 2 (migrate trading-critical tabs, flagged) → Phase 3 (delete iframes/legacy index.html). Guard: snapshot Live hardening + client audit events first; per-view freshness badges; add GUI smoke tests (currently zero automated coverage = biggest execution risk).

---

## 10 · Open aesthetic questions — the deepen/polish agenda
1. **Accent hue** — ~~default cool blue~~ **✅ RESOLVED 2026-07-10(§0):青銅 `#B49B5F`(玄夜)/`#7C6434`(帛晝);chrome 保持中性。**
2. **Icon strategy** — current: inconsistent emoji (⚠×77, ✓/✔/✅, 🔴 overloaded). Default: **single inline-SVG sprite set** (feather/lucide-style, stroke, inherit muted color) replacing decorative emoji; keep 🔴/⚠ ONLY as reinforced real-money/danger marks. Confirm vs disciplined-emoji-subset.
3. **Density default** — comfortable (34px) vs compact (27px) as the shipped default for operators who live in the console.
4. **Hero KPI treatment** — how dominant; 27px vs 32px; how many hero numbers per screen (default: 1 dominant + rest at section scale).
5. **Charts** — currently unaddressed surface; aesthetic (area fill + faint grid + emphasized endpoint), which lib (keep lightweight-charts/Chart.js), dark-tuned palette (玄衡版:語義綠紅+青銅端點)。
6. **Bilingual mechanism** — `abbr title=` tooltip vs global lang toggle vs `i18n_zh` `t_zh()` lookup. Default: primary-zh + `title=` tooltip, with a global toggle later.
7. **Light mode** — ~~real target, or courtesy?~~ **✅ RESOLVED 2026-07-10(§0):真目標,帛晝與玄夜同等用心。**
8. **Empty/zero states** — strict em-dash minimalism vs a light line of guidance copy.
9. **Lane switch** — top-bar segmented control vs rail-header switcher; how prominent.
10. **Motion level** — functional-only (loading shimmer, disclosure, hover, state transition) at 120/200ms; confirm nothing more. **衡樑例外:500ms 級環境緩動(§0),reduced-motion 全停。**

---
*Anchor maintained by main session (PM+Conductor). Deep specs in `design/`. Update this doc as decisions crystallize.*

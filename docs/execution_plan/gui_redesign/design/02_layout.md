# S1 TERMINAL — LAYOUT, GRID & SPATIAL RHYTHM SPEC (排版)

The definitive layout system. Every value below is production-final; an E1a can lift the CSS verbatim. All dimensions are multiples of the 4px base. Elevation is by luminance + hairline only — no shadow appears anywhere in this spec.

---

## 0. LAYOUT TOKENS (three-tier)

```css
:root {
  /* ── PRIMITIVE: raw spacing scale (4px base) ── */
  --space-1: 4px;   --space-2: 8px;   --space-3: 12px;  --space-4: 16px;
  --space-5: 24px;  --space-6: 32px;  --space-7: 48px;  --space-8: 64px;

  /* ── PRIMITIVE: raw layout dimensions ── */
  --dim-topbar:      48px;
  --dim-statusbar:   28px;
  --dim-rail:        240px;
  --dim-rail-icon:   56px;   /* icon-only collapsed */
  --dim-ctl:         32px;   /* control/button height */
  --dim-row:         34px;   /* table row */
  --dim-panelhead:   40px;
  --dim-hair:        1px;

  /* ── SEMANTIC: what the shell reads ── */
  --shell-topbar-h:    var(--dim-topbar);
  --shell-status-h:    var(--dim-statusbar);
  --shell-rail-w:      var(--dim-rail);
  --shell-content-pad: var(--space-5);   /* 24 */
  --gap-kpi:           var(--space-4);   /* 16 */
  --gap-panel:         var(--space-5);   /* 24 */
  --gap-section:       var(--space-6);   /* 32 */

  /* ── COMPONENT: panel internals ── */
  --panel-radius:      8px;
  --panel-head-h:      var(--dim-panelhead);
  --panel-head-pad:    0 var(--space-4);
  --panel-body-pad:    var(--space-4);
  --kpi-pad:           var(--space-4);
  --cell-pad:          var(--space-2) var(--space-3);  /* 8 × 12 */
}

/* Compact mode overrides ONLY the deltas */
[data-density="compact"] {
  --dim-topbar: 44px;  --dim-rail: 200px;  --dim-row: 27px;  --dim-panelhead: 34px;
  --shell-content-pad: var(--space-4);     /* 24 → 16 */
  --gap-kpi:  var(--space-3);              /* 16 → 12 */
  --gap-panel: var(--space-4);             /* 24 → 16 */
  --panel-head-pad: 0 var(--space-3);      /* 16 → 12 */
  --panel-body-pad: var(--space-3);        /* 12 */
  --kpi-pad: var(--space-3);               /* 12 */
  --cell-pad: var(--space-1) var(--space-2); /* 4 × 8 */
  --dim-ctl: 28px;
}
```

Rule: **compact never changes the token scale, only which rung a semantic token points at.** This keeps the two modes provably in the same rhythm.

---

## 1. SHELL LAYOUT

### 1.1 Structure & exact dimensions

| Region | Grid area | Size (comfortable / compact) | Contents |
|---|---|---|---|
| Top bar | `topbar` | **48 / 44** px tall, full width | brand mark · command/search · **engine heartbeat** · **Live/Demo PnL** · UTC clock · density toggle · theme toggle · account |
| Left rail | `rail` | **240 / 200** px wide | lane switcher (top) · environment ladder (mid) · cross-cutting nav (bottom) |
| Content | `content` | fluid, fills remainder | scrollable screen body, padding 24/16 |
| Status strip | `statusbar` | **28** px tall, **full width** (spans under rail) | engine state · mode chip · latency · last-sync · queue depth · build SHA |

The status strip spans full width (VS Code / Bloomberg convention) so the rail sits *between* top bar and status strip. This matters for responsive: the strip is the survivor when the rail collapses.

### 1.2 Grid composition

```css
.app-shell {
  display: grid;
  grid-template-columns: var(--shell-rail-w) 1fr;
  grid-template-rows: var(--shell-topbar-h) 1fr var(--shell-status-h);
  grid-template-areas:
    "topbar    topbar"
    "rail      content"
    "statusbar statusbar";
  height: 100dvh;
  background: var(--bg-app);
}
.app-topbar   { grid-area: topbar;    height: var(--shell-topbar-h);
                border-bottom: var(--dim-hair) solid var(--border-subtle);
                background: var(--bg-surface); }
.app-rail     { grid-area: rail;
                border-right: var(--dim-hair) solid var(--border-subtle);
                background: var(--bg-surface);
                display: flex; flex-direction: column;
                overflow-y: auto; overscroll-behavior: contain; }
.app-content  { grid-area: content; overflow-y: auto;
                padding: var(--shell-content-pad);
                background: var(--bg-app); }
.app-status   { grid-area: statusbar; height: var(--shell-status-h);
                border-top: var(--dim-hair) solid var(--border-subtle);
                background: var(--bg-sunken); }
```

The three chrome surfaces step luminance **inward-darker** to sink the frame and float the content: rail/topbar `--bg-surface #101319`, content `--bg-app #0a0c10`, status `--bg-sunken #0c0e13`. Cards inside content step *up* again to `--bg-surface`/`--bg-raised`. That luminance ladder (sunken → app → surface → raised) is the only depth cue — replaces shadows entirely.

### 1.3 Rail internal composition

The rail is a flex column with three blocks: lane switcher (fixed top), environment ladder (scrolls), cross-cutting nav (pinned bottom).

```css
.rail-lanes    { padding: var(--space-3); border-bottom: 1px solid var(--border-subtle); }
.rail-envs     { padding: var(--space-2) var(--space-3); flex: 1 1 auto; min-height: 0; }
.rail-cross    { padding: var(--space-3); border-top: 1px solid var(--border-subtle);
                 margin-top: auto; }
```

**Lane switcher** (asset lanes as peers) — a 2-row segmented stack, not a dropdown, so both lanes are always visible and one-click:

```
┌────────────────────────────┐  each item: 36px tall, radius 5,
│ ◈ Crypto Perp · Bybit      │  active = --bg-raised bg + 2px --accent
│ ▣ Stock · ETF · IBKR       │  left border; inactive = transparent,
└────────────────────────────┘  --text-secondary. 4px gap between.
```

**Environment ladder** (research → replay → paper → demo → live) — a vertical nav list *scoped to the active lane*. Each rung is a 32px row; the ladder is ordered and the live rung is visually terminal:

```
研究 Research        · dot --text-muted
回放 Replay          · dot --text-muted
紙上 Paper           · dot --accent
模擬 Demo            · dot --warn
──────────────────   ← 8px hairline gap + divider before live
實盤 Live            · dot --live, row gets 1px --live left-border
```

The divider + color break before **Live** is a physical/visual gate inside the nav itself — you cannot reach a real-money surface without crossing the hairline.

**Cross-cutting nav** (governance / risk / AI / learning / monitor / settings) — pinned to rail bottom, 28px rows, `--text-secondary`, icon+label, separated from the ladder by the `margin-top:auto` push and a top hairline. These are lane-and-environment-agnostic, so their spatial separation (bottom block) encodes that they're orthogonal to the lane×env matrix above.

### 1.4 Chrome-to-content ratio target

At the reference 1440×900 desktop:
- Horizontal: rail 240 / 1440 = **16.7%**
- Vertical: (48 + 28) / 900 = **8.4%**
- Total chrome pixel area ≈ **23%**; content ≈ **77%**.

**Target band: chrome 20–26% at ≥1280px.** Compact mode pulls it to ~19%. Never exceed 30% chrome at any breakpoint ≥1280 — if a new chrome element threatens that, it belongs in a disclosure, not the frame.

---

## 2. SPACING SYSTEM APPLIED

### 2.1 The when-to-use-which table

| Token | px | Primary uses (this console's vocabulary) |
|---|---:|---|
| `--space-1` | 4 | icon→label gap; number→unit (`1.234` `bps`); inside a badge/chip; between stacked micro-labels; hairline-adjacent nudges |
| `--space-2` | 8 | chip→chip; toolbar icon-button gaps; **table cell vertical pad (comfortable)** / cell horizontal pad (compact); segmented-control inner gap |
| `--space-3` | 12 | **table cell horizontal pad (comfortable)**; panel-head horizontal pad (compact); KPI/card pad (compact); rail block padding; form label→field |
| `--space-4` | 16 | **panel body pad**; **KPI tile pad**; **gap between KPI tiles**; panel-head horizontal pad (comfortable); form field→field |
| `--space-5` | 24 | **gap between panels**; **content region padding**; KPI-row → panel-block separation |
| `--space-6` | 32 | **section → section** (major block break, e.g. positions block → orders block); above an action bar |
| `--space-7` | 48 | page top breathing on large screens; empty-state vertical; live-action physical separation minimum |
| `--space-8` | 64 | hero/rare; full-screen empty or onboarding states only |

### 2.2 Governing rules

1. **Padding ≤ the gap it sits in.** A KPI tile (16 pad) lives in a 16-gap row — never a tile with 24 pad in a 16 gap.
2. **Every vertical measure is a 4-multiple.** Row heights 34/27, tile min-height 96, etc. This makes an implicit 4px baseline grid that keeps unrelated panels aligned across a 2-col split.
3. **Nesting steps down exactly one rung.** Content pad 24 → panel body 16 → inner list gap 8 → chip inner 4. Never skip rungs going inward; never go back up.
4. **Inline (horizontal-in-text) gaps stay in {4, 8}.** Anything ≥12 becomes structural, not inline.

---

## 3. PANEL / CARD COMPOSITION

### 3.1 Panel anatomy

```
┌──────────────────────────────────────────────┐ ← 1px --border-subtle, radius 8
│ HEAD  h=40   pad 0/16   border-bottom 1px      │
│  ┌ title 15/600 --text-primary  [count badge] ┐│
│  └ ......................... [tool] [tool] ────┘│  tools = 28px icon buttons
├──────────────────────────────────────────────┤
│ BODY  pad 16 (12 compact)                      │
│                                                │
├──────────────────────────────────────────────┤ ← border-top 1px (footer only)
│ FOOT  pad 12/16  bg --bg-sunken  (optional)    │
└──────────────────────────────────────────────┘
```

```css
.panel { background: var(--bg-surface); border: 1px solid var(--border-subtle);
         border-radius: var(--panel-radius); overflow: hidden; }
.panel__head { height: var(--panel-head-h); padding: var(--panel-head-pad);
               display: flex; align-items: center; justify-content: space-between;
               gap: var(--space-3); border-bottom: 1px solid var(--border-subtle); }
.panel__title { font-size: 15px; font-weight: 600; color: var(--text-primary);
                display: flex; align-items: center; gap: var(--space-2); }
.panel__tools { display: flex; align-items: center; gap: var(--space-1); }
.panel__body { padding: var(--panel-body-pad); }
.panel__body--flush { padding: 0; }   /* tables go edge-to-edge */
.panel__foot { padding: var(--space-3) var(--space-4); background: var(--bg-sunken);
               border-top: 1px solid var(--border-subtle); }
```

Key rule: **a panel that contains a full-width data table uses `--flush` (0 body pad)** so the table's own cell padding is the only inset and rows bleed to the hairline border. Panels containing prose/forms/KPIs keep the 16 pad.

### 3.2 KPI tile

```css
.kpi { background: var(--bg-raised); border: 1px solid var(--border-subtle);
       border-radius: var(--panel-radius); padding: var(--kpi-pad);
       min-height: 96px; display: flex; flex-direction: column; gap: var(--space-2); }
.kpi__label { font-size: 12px; font-weight: 500; color: var(--text-secondary); }
.kpi__value { font-size: 27px; font-weight: 600; line-height: 1.1;
              font-family: var(--font-mono); font-variant-numeric: tabular-nums slashed-zero;
              color: var(--text-primary); }
.kpi__delta { font-size: 12px; font-family: var(--font-mono);
              font-variant-numeric: tabular-nums; display: flex; align-items: center;
              gap: var(--space-1); }  /* arrow + sign + value; color = --pos/--neg */
```

Internal rhythm: label (12) → 8 gap → value (27) → 8 gap → delta (12). Redundant encoding on the delta: arrow glyph **and** sign **and** color — CVD-safe.

### 3.3 KPI row grid

```css
.kpi-row { display: grid; gap: var(--gap-kpi);
           grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
```

- `minmax(200px, 1fr)` → tiles never narrower than 200 (27px hero number never truncates a 9-digit equity + sign). At 1200px content: 5–6 tiles per row; at 1366 desktop: 6; wraps cleanly to 3/2/1 as width drops.
- For a fixed-count strip (exactly 4 KPIs, never wrap) use `repeat(4, 1fr)` instead of auto-fit.

### 3.4 Data table

```css
.tbl { width: 100%; border-collapse: collapse; table-layout: fixed;
       font-size: 13px; }
.tbl thead th { position: sticky; top: 0; z-index: 1;
       height: var(--dim-row); padding: var(--cell-pad);
       background: var(--bg-sunken); color: var(--text-secondary);
       font-size: 12px; font-weight: 500;
       border-bottom: 1px solid var(--border-strong); }   /* strong = header rule */
.tbl tbody td { height: var(--dim-row); padding: var(--cell-pad);
       border-bottom: 1px solid var(--border-subtle);      /* subtle = row rules */
       color: var(--text-primary); }
.tbl tbody tr:hover { background: var(--bg-hover); }
.tbl .num { text-align: right; font-family: var(--font-mono);
            font-variant-numeric: tabular-nums slashed-zero; }
```

- **Header rule = `--border-strong`; row rules = `--border-subtle`.** One weight of contrast difference separates the header from the body without a fill change.
- No vertical gridlines by default; whitespace + right-alignment separates numeric columns. Add a single `--border-subtle` vertical rule **only** when a table exceeds 6 numeric columns (scan aid), never more than one weight.
- No zebra striping (violates monochrome-chrome restraint). Hover is the only row-level fill.

### 3.5 Status ladder (progressive disclosure — the Gates panel)

```
┌ 閘門 Gates ─────────────────────────── 4/5 ┐   head badge = pass count
│ ● cost_gate        PASS      ▸            │   32px rows; state dot left
│ ● beta_neutral     PASS      ▸            │   dot: --pos/--neg/--warn/--muted
│ ● attribution_ok   PASS      ▸            │   status label 12px mono right-of-center
│ ✕ live_auth        BLOCK     ▾            │   chevron ▸/▾ = expandable
│   └───────────────────────────────────    │   expanded detail: indent 24,
│     RiskConfig bypasses 5-gate. Blocked   │   bg --bg-sunken, pad 12,
│     at 2026-07-06 03:17 UTC. [detail →]   │   border-left 2px state color
│ ● schema_contract  PASS      ▸            │
└───────────────────────────────────────────┘
```

```css
.ladder__step { height: 32px; display: grid;
   grid-template-columns: 16px 1fr auto 16px;  /* dot · label · status · chevron */
   align-items: center; gap: var(--space-2);
   padding: 0 var(--space-3); border-bottom: 1px solid var(--border-subtle); }
.ladder__detail { padding: var(--space-3); padding-left: var(--space-5);
   background: var(--bg-sunken); border-left: 2px solid var(--state-color);
   font-size: 12px; color: var(--text-secondary); }
```

Redundant encoding: state = dot color **and** glyph (● pass / ✕ block / ▲ warn) **and** text label (PASS/BLOCK/WARN). The whole step is the click target; chevron rotates ▸→▾.

### 3.6 Two-column panel grid

```css
.panel-2col { display: grid; gap: var(--gap-panel);
              grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr); }
```

`minmax(0, …)` on the wide column lets an overflow-x table shrink without blowing the grid; the narrow column floors at 320 so a ladder/detail rail never crushes. Collapses to single column below the 960 breakpoint (see §5).

### 3.7 Column sizing (fixed-layout tables)

Use `table-layout: fixed` + `<colgroup>` with `ch`-based widths so numbers align across pages of data and never reflow on new rows:

| Column class | Width | Align | Notes |
|---|---|---|---|
| `col-symbol` | `12ch` (auto if truncatable) | left | e.g. `BTCUSDT` |
| `col-side` | `6ch` | left | LONG/SHORT chip |
| `col-qty` | `10ch` | right | mono tabular |
| `col-price` | `12ch` | right | mono tabular, fixed decimals |
| `col-pnl` | `11ch` | right | mono tabular, +/- + color |
| `col-pct` | `8ch` | right | mono tabular |
| `col-actions` | `88px` | right | icon buttons |

Fixed decimals per column (not per value) so decimal points stack: a price column renders `65 432.10` and `65.10` both to the same decimal count.

---

## 4. ALIGNMENT & RHYTHM

### 4.1 Alignment law

- **Numbers right-align, always mono + `tabular-nums slashed-zero`.** Their column header right-aligns too (header alignment must match cell alignment).
- **Text/labels left-align**; their headers left-align.
- **Never center a data cell.** Centering is reserved for single-glyph status columns (a lone dot/icon) and for empty-state bodies.
- A value + unit pair (`1.234 bps`) keeps the number mono/tabular and the unit `--text-muted` at 11px, 4px gap, so the number column still stacks by decimal.

### 4.2 Baseline & vertical rhythm

- Base text 13px on **line-height 20px** (a 4-multiple → every text line lands on the 4px grid).
- Table rows use **fixed height** (34/27), not line-height, so a wrapping cell can't break the grid — content is `overflow: hidden; text-overflow: ellipsis` on a single line.
- Section header 15px on 24 line. Page title 20px on 28. Hero KPI 27px on ~30 (line-height 1.1) — the one place we break the 20-grid, isolated inside its tile so it doesn't propagate.

### 4.3 Staying calm at density

The visual noise budget per table is **one hairline weight + one hover fill + one accent for state**. Concretely:
- All horizontal rules are `--border-subtle` except the single `--border-strong` header rule.
- Color appears **only** in data cells (PnL sign, state dots) — never in structure. A screen of all-flat positions is pure monochrome; color literally means "something is happening."
- Row height is generous enough (34) that the hairline reads as separation, not a cage. In compact (27) the eye relies more on the tabular alignment than the rules.

### 4.4 Hairline gridline strategy

| Context | Horizontal | Vertical |
|---|---|---|
| Data table | `--border-subtle` per row; `--border-strong` header | none (≤6 num cols); single `--border-subtle` if >6 |
| KPI row | none (gap separates) | none |
| Panel-to-panel | none (24 gap separates) | none |
| Shell chrome seams | topbar bottom, status top: `--border-subtle` | rail right: `--border-subtle` |
| Live-action separator | — | `--border-strong` divider before the hot cluster |

Rule: **whitespace separates blocks; hairlines separate rows.** If two things are far enough apart to warrant a gap ≥16, they get no line.

---

## 5. RESPONSIVE — ONE COHERENT SCALE

Replace the five ad-hoc breakpoints (700/860/900/980/1180) with **four named stops**:

```css
:root {
  --bp-1:  640px;   /* phone → large phone   */
  --bp-2:  960px;   /* RAIL COLLAPSE THRESHOLD; tablet-landscape / small laptop */
  --bp-3: 1280px;   /* laptop → desktop      */
  --bp-4: 1680px;   /* desktop → wide        */
}
```

The old 860/900/980 cluster collapses into the single meaningful event — **rail collapse — anchored at 960** (covers all three; chosen so tablet-landscape and half-screen 1080p windows both trigger it). The old 700 → 640; 1180 → 1280.

### 5.1 Behavior by tier

| Width | Tier | Rail | Content grid | Chrome survivors |
|---|---|---|---|---|
| **≥1680** | wide | 240 full | 2-col panels; KPI 6-up | all |
| **1280–1679** | desktop *(1366×768, 13" laptop)* | 240 full | 2-col panels; KPI auto-fit 5–6 | all |
| **960–1279** | small-laptop | **200 (compact rail)** | 2-col → secondary col drops under primary; KPI 3–4 | all |
| **640–959** | tablet | **collapsed → drawer** | single column; KPI 2-up | **status strip promoted** |
| **<640** | phone | collapsed → drawer | single column; KPI 1–2-up; tables overflow-x | **status strip promoted** |

```css
@media (max-width: 1279px) { :root { --shell-rail-w: 200px; } }
@media (max-width:  959px) {
  .app-shell { grid-template-columns: 1fr;
               grid-template-areas: "topbar" "content" "statusbar"; }
  .app-rail  { position: fixed; inset: var(--shell-topbar-h) auto var(--shell-status-h) 0;
               width: 280px; transform: translateX(-100%);
               transition: transform .18s ease; z-index: 40; }
  .app-rail[data-open="true"] { transform: none; }
  .panel-2col { grid-template-columns: 1fr; }
}
```

### 5.2 The rail-collapse fix (critical requirement)

The current design **loses engine-alive + mode + Live/Demo PnL** when the rail collapses. The fix: those three signals do not live *only* in the rail — they live in the **always-present status strip**, and below 960 the strip is **promoted** (taller, higher-priority content) so they stay glued to the viewport bottom while the rail becomes a hamburger drawer.

```css
/* Status strip: default carries a full telemetry set on wide screens */
.app-status__wide { display: flex; }        /* latency, sync, queue, SHA … */
.app-status__core { display: none; }         /* engine · mode · pnl */

@media (max-width: 959px) {
  :root { --shell-status-h: 40px; }          /* promote: 28 → 40 for tap targets */
  .app-status__wide { display: none; }        /* shed low-priority telemetry */
  .app-status__core { display: flex; align-items: center; gap: var(--space-3);
                      padding: 0 var(--space-3); font-size: 12px; }
}
```

The promoted strip renders exactly three chips, left→right, never truncated:

```
[ ● ENGINE alive ]   [ DEMO ]   [ P&L +1,284.50 ▲ ]
   dot --pos/--neg    mode chip    mono tabular, --pos/--neg
```

- `ENGINE` dot: `--pos` alive / `--neg` dead / `--warn` degraded, with text label (redundant).
- Mode chip inherits environment color: RESEARCH/REPLAY `--text-secondary`, PAPER `--accent`, DEMO `--warn`, **LIVE `--live` (filled)**. When mode is LIVE the whole strip gets a 2px `--live` top border — the real-money frame follows you down to phone width.
- PnL: mono tabular, sign + arrow + color.

Top bar on collapse keeps the hamburger (opens rail drawer) + brand + the same engine/PnL as a secondary redundancy, but the **status strip is the guarantee** — it's the one element that never leaves the layout at any width.

### 5.3 Wide tables

Every data table is wrapped so the panel never forces body-level horizontal scroll:

```css
.table-scroll { overflow-x: auto; overscroll-behavior-x: contain; }
.table-scroll .tbl { min-width: 720px; }         /* below this, scroll */
.table-scroll .tbl thead th:first-child,
.table-scroll .tbl tbody td:first-child {
  position: sticky; left: 0; background: var(--bg-surface); z-index: 2; }  /* pin symbol */
```

The **symbol column pins left** during horizontal scroll so a row is never anonymous. The scroll lives inside the panel body — the app shell body never scrolls sideways at any breakpoint (hard invariant).

---

## 6. DENSITY MODES — exact deltas

| Element | Comfortable | Compact | Δ |
|---|---:|---:|---:|
| Base font | 13px | 12px | −1 |
| Table row height | 34px | 27px | −7 |
| Cell padding | 8 × 12 | 4 × 8 | −4 / −4 |
| Panel head height | 40px | 34px | −6 |
| Panel body padding | 16px | 12px | −4 |
| KPI tile padding | 16px | 12px | −4 |
| KPI value size | 27px | 24px | −3 |
| Control height | 32px | 28px | −4 |
| Rail width | 240px | 200px | −40 |
| Top bar height | 48px | 44px | −4 |
| Status strip height | 28px | 28px | 0 |
| KPI gap | 16px | 12px | −4 |
| Panel gap | 24px | 16px | −8 |
| Content padding | 24px | 16px | −8 |

Density is a *content* setting, not a *chrome* setting — the status strip height holds at 28 in both (it's already minimal) and mode/live coloring is identical. Rows-per-1080p-viewport: **~24 comfortable → ~32 compact** in a positions table (a 33% density gain). Toggle via `[data-density]` on `:root`; all values above flow from the token overrides in §0.

---

## 7. WORKED EXAMPLE — OVERVIEW SCREEN

Reference viewport **1366×768, comfortable density, DEMO mode.** Content region = 1366 − 240 rail = **1126px wide**, minus 24 padding each side = **1078px usable**. Vertical: 768 − 48 top − 28 status = **692px** content viewport.

```
┌─ TOPBAR  h48 ─────────────────────────────────────────────────────────┐
│ ◈ OpenClaw   ⌘search        ● ENGINE alive   DEMO   P&L +1,284.50 ▲  ⚙ │
├──────────┬────────────────────────────────────────────────────────────┤
│ RAIL 240 │ CONTENT  pad 24                                             │
│          │ ┌──────────────────────────────────────────────────────┐   │
│ ◈ Crypto │ │ KPI ROW  grid auto-fit minmax(200,1fr) gap16          │   │  ← row 1
│ ▣ Stock  │ │ [Equity][Day P&L][Open P&L][Exposure][Margin][Win%]   │   │    6 tiles,
│  ──────  │ │  each: pad16, val 27 mono, min-h 96                   │   │    each ≈171w
│ Research │ └──────────────────────────────────────────────────────┘   │
│ Replay   │            ↕ 24 (--gap-section-lite / panel gap)            │
│ Paper    │ ┌─ panel-2col  cols minmax(0,2fr) / minmax(320,1fr) g24 ─┐  │  ← row 2
│ Demo ◀   │ │ ┌ 持倉 Positions      12 ┐  ┌ 閘門 Gates       4/5 ┐  │  │
│  ──────  │ │ │ head40                  │  │ head40             │  │  │
│ Live     │ │ │ body--flush             │  │ body16             │  │  │
│          │ │ │ ┌ table-scroll ───────┐ │  │ ● cost_gate PASS ▸ │  │  │
│ ──────   │ │ │ │ sym  side qty … pnl │ │  │ ● beta_neut PASS ▸ │  │  │
│ Govern   │ │ │ │ rows 34, pin symbol │ │  │ ● attrib_ok PASS ▸ │  │  │
│ Risk     │ │ │ └─────────────────────┘ │  │ ✕ live_auth BLOCK▾ │  │  │
│ AI       │ │ └─────────────────────────┘  └────────────────────┘  │  │
│ Learning │ └────────────────────────────────────────────────────────┘ │
│ Monitor  │            ↕ 32 (--gap-section, before action bar)          │
│ Settings │ ┌─ ACTION BAR  h56 sticky-bottom ──────────────────────┐   │  ← row 3
│          │ │ [刷新 Refresh] [平倉全部 Flatten]    ┃  [ ⏻ 啟動實盤 ] │   │
├──────────┴─┴──────────────────────────────────────┴─────────────────┴─┤
│ STATUS  h28   ● alive · DEMO · lat 42ms · sync 3s · q0 · 5d162299     │
└───────────────────────────────────────────────────────────────────────┘
```

### Exact annotations

**Row 1 — KPI row.** `grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap:16`. At 1078 usable: 6 columns → each tile ≈ (1078 − 5×16)/6 ≈ **166px** wide (floors above 200? no — auto-fit fits 5 at 200+; here 6 tiles requested → each ~166, which is below 200 so auto-fit yields **5 per row + 1 wraps**, or specify `repeat(6,1fr)` for a fixed strip). For Overview use fixed `repeat(6,1fr)` → each **164px**, tile pad 16, value 27 mono tabular, min-height 96. Row block height = **96**.

**Gap → 24** (`--gap-panel`).

**Row 2 — panel-2col.** `minmax(0,2fr) / minmax(320px,1fr)`, gap 24. Left column = (1078−24)×2/3 ≈ **703px** (Positions), right = **351px** (Gates).
- *Positions panel*: head 40 (`持倉 Positions` 15/600 + count badge `12`; tools: filter, columns, export as 28px icon buttons, 4px gap). Body `--flush` (0 pad) → `.table-scroll` → table rows 34, header row 34 sticky on `--bg-sunken` with `--border-strong` bottom rule. 12 rows visible = 40 + 34 + 12×34 = **482px** tall.
- *Gates ladder panel*: head 40 (`閘門 Gates` + `4/5` badge). Body pad 16. Five 32px steps = 160; one expanded (`live_auth` BLOCK) adds a detail block pad 12, left-border 2px `--live`, ~48px. Panel ≈ 40 + 16 + 160 + 48 + 16 = **280px**. Shorter than Positions — both top-align; the 2fr/1fr grid rows are independent, no forced equal-height.

**Gap → 32** (`--gap-section`, more air before a consequential control cluster).

**Row 3 — action bar.** Height 56, `display:flex; align-items:center; justify-content:space-between; padding:0 16`.
- *Benign cluster* (left): `刷新 Refresh`, `平倉全部 Flatten` — 32px controls, 8px gap, neutral `--bg-raised` + `--border-strong`.
- *Physical separation*: `margin-left:auto` + a **`--border-strong` vertical divider** + minimum **48px gap** (`--space-7`) before the hot cluster.
- *Live cluster* (right): `⏻ 啟動實盤 Arm Live` — boxed in a 1px `--live` container, `--live` fill on the button, requires typed-confirm modal. In DEMO mode this control is present but the modal enforces the mode gate; the `--live` treatment is always literal so the operator can never mistake it for a benign action.

**Vertical budget check:** 96 + 24 + 482 + 32 + 56 = **690px** vs 692 available → fits without content scroll at 1366×768 with the positions table showing ~12 rows. In **compact** the same screen shows ~16 positions rows in the same height (row 34→27, gaps 24→16/32→24). This is the density payoff realized on the primary screen.

---

### Invariants (the layout's non-negotiables)

1. Status strip is present at **every** breakpoint and always carries engine · mode · Live/Demo PnL.
2. App shell body **never** scrolls horizontally; wide content scrolls inside its own `.table-scroll`.
3. No `box-shadow` anywhere — depth is the luminance ladder (sunken→app→surface→raised) + hairlines.
4. Every height/gap is a 4-multiple; the 20px text line-height keeps text on the 4px baseline.
5. Color lives only in data/state cells; all structure is monochrome.
6. Live real-money controls are always `--live`-framed and physically separated (≥48px + `--border-strong` divider) from benign controls.
# S1 Terminal — Typography & Type-Hierarchy System ("排級邏輯")

Definitive, build-ready spec. Every value is grounded in the established scale (11·12·13·14·15·20·27, weights 400/500/510/600) and the dark semantic tokens. Where a role had no assigned value, it is derived and marked *(derived)* with rationale.

Anchoring principle for this console: **hierarchy is carried by weight, case, color, and letter-spacing — NOT by size.** Trading operators scan dense grids; big size jumps waste vertical budget and break column rhythm. The scale is deliberately shallow (13px is the gravitational center; most of the UI lives in the 11–15 band). Size separates only *structural* tiers (page / section / hero KPI); everything inside a tier is separated by the other three channels.

---

## 0. Foundation token set (copy-paste)

```css
:root{
  /* ---- font stacks ---- */
  --font-sans: system-ui, -apple-system, "Segoe UI", Roboto,
               "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC",
               "Hiragino Sans GB", sans-serif;
  --font-mono: ui-monospace, "SF Mono", "JetBrains Mono", "IBM Plex Mono",
               Menlo, Consolas, monospace;

  /* ---- primitive: font-size ramp (px, fixed to the agreed scale) ---- */
  --fs-micro:   11px;  /* units, sub-labels, dense chip text            */
  --fs-dense:   12px;  /* compact table cells, table column headers     */
  --fs-base:    13px;  /* body / default table cell / most controls     */
  --fs-md:      14px;  /* emphasized body, primary button label, nav    */
  --fs-section: 15px;  /* section header, modal title                   */
  --fs-title:   20px;  /* page title                                    */
  --fs-hero:    27px;  /* KPI hero number                               */
  --fs-hero-lg: 32px;  /* (derived) single dominant KPI on a dashboard  */

  /* ---- primitive: line-height (unitless, Latin-tuned) ---- */
  --lh-solid:  1.0;    /* single-line hero numbers, tight KPI           */
  --lh-tight:  1.15;   /* numeric cells, titles, chips                  */
  --lh-snug:   1.30;   /* table text cells, controls, nav               */
  --lh-normal: 1.45;   /* body copy, help text                          */
  --lh-cjk:    1.60;   /* (derived) CJK paragraph baseline — see §4     */

  /* ---- primitive: letter-spacing ---- */
  --ls-hero:    -0.02em;  /* large numbers: tighten                     */
  --ls-title:   -0.01em;  /* page title                                */
  --ls-normal:   0;       /* body / cells                              */
  --ls-label:    0.01em;  /* KPI labels, nav                           */
  --ls-eyebrow:  0.08em;  /* overline / eyebrow (uppercase Latin)      */
  --ls-caps:     0.04em;  /* small uppercase column headers, badges    */

  /* ---- primitive: weight ---- */
  --weight-regular: 400;
  --weight-medium:  510;  /* the workhorse emphasis weight             */
  --weight-semi:    600;  /* strong: titles, hero, active nav          */

  /* ---- numeric rendering ---- */
  --num-features: "tnum" 1, "zero" 1, "cv01" 0; /* tabular + slashed 0 */
}
```

`--weight-medium` is set to **510**, not 500 — on the system-ui / SF stack 500 is nearly indistinguishable from 400 at 12–13px on non-Retina panels; 510 forces the next hinting bucket and gives a visible but non-bold emphasis. On CJK it maps to the same visual weight bucket as 500 (CJK fonts quantize to fewer weights) so no harm.

Numeric utility, applied to every number:

```css
.num, td.num, .kpi, .cell-num{
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums slashed-zero;
  font-feature-settings: var(--num-features);
  font-variant-ligatures: none;   /* kill arrow/→ ligatures in mono */
}
```

---

## 1. TYPE ROLE TABLE

sans = `--font-sans`, mono = `--font-mono`. Sizes/weights/LH/LS reference the tokens above. "case" = text-transform.

| Role | 中文/用途 | family | size | weight | line-height | letter-spacing | case | color token | align |
|---|---|---|---|---|---|---|---|---|---|
| **Page title** | 頁標題 | sans | `--fs-title` 20 | 600 | `--lh-tight` 1.15 | `--ls-title` −0.01em | none | `--text-primary` | start |
| **Section header** | 區塊標題「開倉 Positions」 | sans | `--fs-section` 15 | 600 | `--lh-tight` 1.15 | 0 | none | `--text-primary` | start |
| **Section eyebrow / overline** | 上緣分類標 | sans | `--fs-micro` 11 | 600 | `--lh-tight` 1.15 | `--ls-eyebrow` 0.08em | UPPERCASE | `--text-muted` | start |
| **KPI hero number** | 主數字 27 | mono | `--fs-hero` 27 | 600 | `--lh-solid` 1.0 | `--ls-hero` −0.02em | none | state* / `--text-primary` | end (right) |
| **KPI label** | KPI 說明「今日淨 Net Today」 | sans | `--fs-micro` 11 | 510 | `--lh-snug` 1.30 | `--ls-label` 0.01em | none | `--text-secondary` | start |
| **Table column header** | 表頭 | sans | `--fs-dense` 12 | 510 | `--lh-tight` 1.15 | `--ls-caps` 0.04em | none¹ | `--text-muted` | matches col |
| **Table cell — text** | 文字格 (symbol, strategy) | sans | `--fs-base` 13 | 400 | `--lh-snug` 1.30 | 0 | none | `--text-primary` | start |
| **Table numeric cell** | 數字格 | mono | `--fs-base` 13 | 400² | `--lh-tight` 1.15 | 0 | none | `--text-primary` / state | end (right) |
| **Body / paragraph** | 內文 | sans | `--fs-base` 13 | 400 | `--lh-normal` 1.45 | 0 | none | `--text-primary` | start |
| **Secondary / caption** | 輔助說明 | sans | `--fs-dense` 12 | 400 | `--lh-snug` 1.30 | 0 | none | `--text-secondary` | start |
| **Micro-label / unit** | 單位 USDT · bps · % | mono³ | `--fs-micro` 11 | 400 | `--lh-tight` 1.15 | 0 | none | `--text-muted` | follows number |
| **Badge / chip text** | 狀態徽章 | sans | `--fs-micro` 11 | 600 | `--lh-tight` 1.15 | `--ls-caps` 0.04em | none¹ | state / on-color | center |
| **Button label** | 按鈕 | sans | `--fs-md` 14⁴ | 510 | `--lh-solid` 1.0 | `--ls-label` 0.01em | none | on-surface / on-accent | center |
| **Nav item** | 導覽項 | sans | `--fs-md` 14 | 510 (active 600) | `--lh-snug` 1.30 | `--ls-label` 0.01em | none | secondary → primary (active) | start |
| **Modal title** | 對話框標題 | sans | `--fs-section` 15 | 600 | `--lh-tight` 1.15 | 0 | none | `--text-primary` | start |
| **Code / mono id** | orderLinkId, hash, symbol id | mono | `--fs-dense` 12 | 400 | `--lh-snug` 1.30 | 0 | none | `--text-secondary` | start |

\* KPI hero color: `--pos` / `--neg` when it represents signed PnL; `--text-primary` when it's a neutral count (e.g. "持倉 12"). Never color a neutral magnitude.

¹ **Case rule — do NOT uppercase Chinese.** Column headers and badges use `--ls-caps` spacing and muted color for the "small-caps feel" but keep `text-transform:none`, because `uppercase` is a no-op on CJK and mixed zh+EN headers would look ransom-note. Uppercase is allowed **only** on the eyebrow/overline role and **only** for pure-Latin strings (see §4).

² Numeric cells default weight 400 for scan-neutrality; promote the *row-key* number (e.g. net PnL column) to 510 to anchor the eye — see §2 demote/promote.

³ Units are mono so a right-aligned number+unit column keeps its decimal grid; if the unit is a standalone chip caption (not trailing a number) use sans 11 muted.

⁴ Compact density drops button label to 13 — see §5.

---

## 2. HIERARCHY LOGIC — encoding LEVEL without size

### The four channels, ranked by strength on this palette

1. **Color/luminance** (strongest here — near-black surfaces make the primary→muted text ramp #e7edf4 → #98a2b0 → #656e7c very legible). Demote by dropping one text-color step.
2. **Weight** (400 → 510 → 600). Three steps only.
3. **Case + letter-spacing** (the "overline" signal: uppercase-Latin + 0.08em reads as a label/kicker regardless of size).
4. **Size** (reserved for structural tiers; 4 sizes do 90% of work: 11 / 12–13 / 15 / 20 / 27).

### Hierarchy budget

- **Max 4 distinct *type levels* visible per screen region** (a panel/card), **max 6 per full page**. If you need a 5th within a region, you're missing a container — add a card/hairline divider instead of a new type size.
- A "level" = a unique combination of (size, weight, color). Two roles that share size+weight but differ only in color count as the *same* structural level, one tone apart — that's the point.

### Standard demote / promote moves (apply in this order, cheapest first)

| Want to… | Move | Example |
|---|---|---|
| Promote 1 notch, cheap | color step up (secondary→primary) | make a caption read as body |
| Promote 1 notch | weight 400→510 | anchor a key numeric column |
| Promote hard | weight →600 **and** color→primary | section header, active nav |
| Add "kicker/label" quality | case→UPPERCASE + `--ls-eyebrow`, size↓ to 11, color→muted | eyebrow over a KPI cluster |
| Demote 1 notch | color step down (primary→secondary→muted) | timestamps, secondary ids |
| Demote hard | color→muted **and** weight→400 | disabled / historical rows |
| **Never** | jump size to signal emphasis inside a table | — |

### Worked hierarchy: a KPI tile (4 levels, in budget)

1. eyebrow `--fs-micro` 11 / 600 / uppercase-Latin / muted — `CRYPTO PERP · DEMO`
2. label `--fs-micro` 11 / 510 / secondary — `今日淨 Net Today`
3. hero `--fs-hero` 27 / 600 / `--pos` — `+1,842.30`
4. unit `--fs-micro` 11 / 400 / mono / muted — `USDT`

Note levels 1 and 2 are the *same size* — separated purely by case+spacing+color. That's the shallow-scale technique.

---

## 3. NUMERICS

### 3.1 mono vs sans decision

- **mono** (tabular): any value that (a) appears in a column, (b) updates live/ticks, or (c) must align by decimal — prices, qty, PnL, %, bps, funding, sizes, ids/hashes, timestamps, latency ms.
- **sans**: numbers embedded in prose ("持有 3 個倉位", "第 2 頁"), and counts inside sentence flow. A standalone count in a KPI tile is mono (it's a data value, not prose).

### 3.2 Universal rules

- `font-variant-numeric: tabular-nums slashed-zero;` on every mono number → equal advance width (no column shimmer on tick) + `0` disambiguated from `O`.
- `font-variant-ligatures: none` on mono to stop `->`, `>=`, `--` from fusing inside ids/log strings.
- Right-align every numeric cell/column. Decimal alignment falls out of tabular-nums + right-align **only when precision is fixed per column** — so fix dp per column (below), don't mix 2dp and 6dp in one column.
- Thousands separators: `,` grouping on values ≥ 1,000 for fiat/USDT magnitudes; **no** grouping on crypto qty (BTC 0.001234) or ids.

### 3.3 Precision per type (fixed decimal places)

| Value type | dp | Example | Notes |
|---|---|---|---|
| USD / USDT notional | 2 | `1,842.30` | always show trailing zeros (tabular fill) |
| Price (perp, ≥100) | 2 | `2,410.55` | |
| Price (< 1, alt/micro) | 4–6 | `0.006721` | per-symbol tick; column-fixed |
| BTC / coin qty | 6 | `0.001234` | strip grouping |
| Percent | 2 | `−3.87%` | `%` unit styling below |
| bps | 2 | `+11.40 bps` | |
| Funding rate | 4 | `0.0100%` | funding shown as % |
| Leverage | 1 | `3.0×` | `×` not `x` |
| Latency | 0 | `142 ms` | integer |
| Count | 0 | `12` | |

Guarantee fixed dp in JS: `value.toFixed(dp)` before render; never let float precision leak (`0.1+0.2`). Pad integer counts to column, don't pad-zero (`12` not `0012`).

### 3.4 Sign · color · arrow (CVD-safe redundant encoding)

Every signed value carries **three** channels: explicit sign glyph + color + directional glyph/label. Color alone is never load-bearing.

```
+1,842.30  ▲   (pos: --pos #3fb950, leading "+", ▲)
−312.08    ▼   (neg: --neg #f85149, leading "−" U+2212, ▼)
0.00       ·   (flat: --text-muted, middot, no arrow)
```

Rules:
- Use the **real minus** `−` (U+2212), not hyphen — it's tabular-width in the mono stack and aligns with `+`.
- Reserve a fixed **sign column**: render `+`/`−` in a fixed-width slot so magnitudes align regardless of sign. In practice: right-align the number, and the tabular `+`/`−`/space all share one advance, so `+1,842.30` and `−312.08` line up on the decimal automatically.
- Arrow is a **separate inline element** (`.delta-arrow`), 11px, same color as the number, `aria-hidden="true"`; the sign+value already convey direction to SR/CVD users, arrow is reinforcement.
- Percent deltas get the arrow; absolute-balance figures (e.g. equity `24,918.44 USDT`) do **not** — they're a level, not a change.

```css
.val-pos{ color:var(--pos); }
.val-neg{ color:var(--neg); }
.val-flat{ color:var(--text-muted); }
.delta-arrow{ font-size:var(--fs-micro); margin-left:4px; }
/* arrow via content, so it's not selectable/copyable into the number */
.val-pos .delta-arrow::before{ content:"▲"; }
.val-neg .delta-arrow::before{ content:"▼"; }
```

### 3.5 Unit / suffix styling

Units (`USDT`, `bps`, `%`, `×`, `ms`) are **demoted** so the magnitude dominates:

- Color: `--text-muted` (one+ step below the number's color).
- Size: for hero numbers, unit is **11px** even though the number is 27px — a large unit competes with the magnitude. For inline table numbers (13px) the unit is also 11px.
- Weight: 400 (number may be 510/600).
- Spacing: **4px** gap between number and unit; `%` and `×` sit tight (**1px**, no space) because they're mathematically bound to the number (`3.87%`, `3.0×`). `USDT` / `bps` / `ms` take the 4px space.
- Unit stays **mono** when trailing a mono number so the column's right edge stays a clean grid.

```html
<span class="kpi val-pos">+1,842.30<span class="unit">USDT</span></span>
```
```css
.unit{ font-size:var(--fs-micro); font-weight:400; color:var(--text-muted);
       margin-left:4px; }
.unit.tight{ margin-left:1px; }   /* % and × */
```

---

## 4. CJK + LATIN MIXED RUNS

The core failure: line-heights and metrics tuned to Latin at 13px break when Chinese glyphs (which fill more of the em box and sit on a different baseline) share the run, and mixed 中文-label + mono-digit runs shift column widths on every render.

### 4.1 Line-height: CJK needs more

Latin body is comfortable at 1.45; **CJK paragraphs need ≥1.6** or the dense glyphs visually collide. But **single-line labels/cells must NOT inherit the taller LH** or rows grow. So bind LH to context, not globally:

| Context | Latin LH | CJK LH | Rule |
|---|---|---|---|
| Single-line label / table cell / button | 1.15–1.30 | **same** (1.30) | one line = no interline risk; keep row height stable |
| Multi-line body / help / tooltip | 1.45 | **1.60** (`--lh-cjk`) | detect zh, bump LH |
| KPI hero (mono digits) | 1.0 | 1.0 | pure numeric, no CJK |

Apply the paragraph bump with a language hook, not per-element inline:

```css
:lang(zh) p, [lang^="zh"] .prose{ line-height: var(--lh-cjk); }
```

Set `lang="zh"` on the labels/regions that are Chinese-primary (which is most of this console's chrome), and `lang="en"` on irreducibly-English technical blocks (log lines, ids). This lets the browser pick correct CJK metrics *and* your LH rule.

### 4.2 The zh-label + mono-number run (the column-width killer)

Pattern in this console: `今日淨 Net Today  +1,842.30 USDT` — Chinese label + Latin gloss + mono number. Problems: (a) CJK punctuation/spacing eats width unpredictably, (b) the mono number's tabular width is stable but the *label* isn't, so a right-aligned number in a grid can drift if label and number share a flex line without a fixed label column.

Rules:
1. **Never** let a CJK label and its number auto-flow in the same inline run for tabular data. Structure as two cells / two flex children with a **fixed or min-width label column**, number right-aligned in its own column. The label may wrap; the number never moves.
2. Between a CJK glyph and an adjacent Latin/number, insert **font-level spacing, not a space character** — use `text-spacing-trim` where supported and a 2px margin fallback; a literal space between 淨 and `Net` is fine (it's word-level), but do **not** put a space between a CJK glyph and a trailing number glued to it. Keep the mono number in its own span so CJK metrics never touch it.
3. **Letter-spacing on CJK: 0.** Never apply `--ls-caps`/`--ls-eyebrow` to runs containing CJK — inter-CJK letter-spacing looks broken and widens columns. The uppercase-eyebrow role is **Latin-only**; if an eyebrow must be bilingual, render the Chinese with normal spacing and only the English token uppercased+spaced:
   ```html
   <span class="eyebrow"><span lang="zh">加密永續</span>
     <span lang="en" class="caps">CRYPTO PERP</span></span>
   ```
   ```css
   .eyebrow{ letter-spacing:0; }
   .eyebrow .caps{ text-transform:uppercase; letter-spacing:var(--ls-eyebrow); }
   ```

### 4.3 Does the size scale change for zh vs en?

Keep the **same px sizes** — CJK at 13px is readable and matching sizes keeps the grid. Two adjustments only:
- **Optical size floor:** CJK below 12px loses stroke detail on non-Retina. So the **11px micro role, when it contains CJK, bumps to 12px**; pure-Latin micro (units, ids) stays 11px. Encode as a modifier:
  ```css
  .micro{ font-size:var(--fs-micro); }        /* 11 */
  .micro:lang(zh){ font-size:var(--fs-dense); } /* 12 for CJK legibility */
  ```
- **Weight:** CJK renders visually heavier than Latin at the same weight. For CJK section headers/titles, 600 is fine, but avoid stacking 600 + tight tracking on long Chinese strings — it muddies. Titles ≥15px CJK: 600 OK; body emphasis CJK: prefer color-step over jumping to 600.

### 4.4 Baseline alignment in a mixed line

When a mono number sits inline with a CJK label on one baseline (unavoidable in some status strips), align by baseline (default) and set the number's line-height to match the label's (1.30), *not* its own tight 1.15 — otherwise the number's box shrinks and it appears to float. Rule: **in a shared line, the number inherits the label's line-height.**

---

## 5. COMPACT vs COMFORTABLE DENSITY

Density shifts a *subset* of tokens. Structural sizes (page title 20, section 15, hero 27) **do not change** — only the row/control band tightens. Row height 34px comfortable → 27px compact (per the established spec).

| Token / role | Comfortable | Compact `[data-density=compact]` |
|---|---|---|
| Table cell size | 13 | **12** |
| Table cell line-height | 1.30 | **1.15** |
| Table column header | 12 | **11** |
| Cell vertical padding | 8px | **4px** |
| Cell horizontal padding | 12px | **8px** |
| Button label size | 14 | **13** |
| Button padding (v/h) | 8 / 16 | **4 / 12** |
| Nav item size | 14 | **13** |
| Badge/chip size | 11 | 11 (unchanged) |
| KPI hero | 27 | 27 (unchanged) |
| KPI label | 11 | 11 (unchanged) |
| Body paragraph | 13 / 1.45 | 13 / 1.45 (prose unchanged) |
| CJK micro floor (§4.3) | 12 | 12 (never below 12 for CJK) |

```css
[data-density=compact]{
  --fs-cell: var(--fs-dense);   /* 12 */
  --lh-cell: var(--lh-tight);   /* 1.15 */
  --fs-colhead: var(--fs-micro);/* 11 */
  --pad-cell-y: 4px; --pad-cell-x: 8px;
  --fs-btn: var(--fs-base);     /* 13 */
}
:root{ /* comfortable defaults */
  --fs-cell: var(--fs-base); --lh-cell: var(--lh-snug);
  --fs-colhead: var(--fs-dense); --pad-cell-y:8px; --pad-cell-x:12px;
  --fs-btn: var(--fs-md);
}
```

Guardrail: compact **never** shrinks CJK below 12px, never shrinks the hero KPI, never shrinks badges (they're already at the 11px floor and carry live state — legibility > density).

---

## 6. WORKED EXAMPLES (real console vocabulary)

### 6.1 KPI tile — "今日淨 Net Today +1,842.30 USDT"

```html
<article class="kpi-tile" lang="zh">
  <div class="eyebrow">
    <span lang="zh">加密永續</span>
    <span lang="en" class="caps">CRYPTO PERP · DEMO</span>
  </div>
  <div class="kpi-label">今日淨 <span lang="en">Net Today</span></div>
  <div class="kpi-value val-pos">
    +1,842.30<span class="unit">USDT</span>
    <span class="delta-arrow" aria-hidden="true"></span>
  </div>
</article>
```
```css
.eyebrow   { font:600 var(--fs-micro)/1.15 var(--font-sans); color:var(--text-muted); letter-spacing:0; }
.eyebrow .caps{ text-transform:uppercase; letter-spacing:var(--ls-eyebrow); margin-left:4px; }
.kpi-label { font:510 var(--fs-micro)/1.30 var(--font-sans); color:var(--text-secondary); letter-spacing:var(--ls-label); margin:8px 0 4px; }
.kpi-value { font:600 var(--fs-hero)/1.0 var(--font-mono);
             font-variant-numeric:tabular-nums slashed-zero;
             letter-spacing:var(--ls-hero); text-align:right; }
```
Four levels, in budget. Number dominates by size+weight+color; unit demoted 27→11 + muted; label and eyebrow share 11px, separated by case/spacing/color.

### 6.2 Section header — "開倉 Positions"

```html
<h2 class="section-head" lang="zh">開倉 <span lang="en">Positions</span>
  <span class="count num">12</span></h2>
```
```css
.section-head{ font:600 var(--fs-section)/1.15 var(--font-sans); color:var(--text-primary); }
.section-head .count{ font:400 var(--fs-dense)/1 var(--font-mono);
  color:var(--text-muted); margin-left:8px; vertical-align:2px; }
```
Header at 15/600; the count is demoted (mono, 12, 400, muted) so "12" reads as metadata, not a second heading — keeps the region at one heading level.

### 6.3 Positions row (comfortable)

| 標的 Symbol | 方向 Side | 數量 Qty | 均價 Entry | 標記 Mark | 未實現 uPnL | ROE% |
|---|---|---:|---:|---:|---:|---:|
| BTCUSDT | 多 LONG ▲ | 0.125000 | 61,240.50 | 61,988.00 | +93.44 | +1.22% ▲ |
| TONUSDT | 空 SHORT ▼ | 420.000000 | 7.8810 | 7.9450 | −26.88 | −0.81% ▼ |

Column type rules applied:
- `標的/方向/策略` → sans 13/400, `--text-primary`, left.
- `數量/均價/標記` → mono 13/400, tabular+slashed-zero, right, fixed dp (qty 6, price 2).
- `未實現 uPnL` (the row-key) → mono 13/**510** + `--pos`/`--neg` + real `−` + arrow. Promoted one weight step to anchor the scan.
- `Side` cell → text label `多/空 LONG/SHORT` + arrow + color (three channels; never color-only).
- Column headers → sans 12/510, `--text-muted`, `--ls-caps`, `text-transform:none` (bilingual, no uppercase).

```css
td.num{ font:400 var(--fs-cell)/var(--lh-cell) var(--font-mono);
  font-variant-numeric:tabular-nums slashed-zero; text-align:right;
  padding:var(--pad-cell-y) var(--pad-cell-x); color:var(--text-primary); }
td.num.key{ font-weight:510; }         /* uPnL column */
td.text{ font:400 var(--fs-cell)/var(--lh-cell) var(--font-sans); text-align:left; }
th{ font:510 var(--fs-colhead)/1.15 var(--font-sans);
  color:var(--text-muted); letter-spacing:var(--ls-caps); text-transform:none;
  text-align:right; }                  /* left for text columns */
```

### 6.4 Typed-confirm modal (live real-money) — title + hot number

```html
<div class="modal" role="dialog" aria-modal="true">
  <h3 class="modal-title" lang="zh">確認實盤下單 <span lang="en">Confirm LIVE order</span></h3>
  <p class="modal-body" lang="zh">將於 <span lang="en">Bybit</span> 市價<span class="chip live">實盤 LIVE</span>賣出</p>
  <div class="confirm-figure val-neg">−0.250000<span class="unit">BTC</span></div>
  <label class="confirm-label">輸入 <code class="mono">SELL</code> 以確認</label>
</div>
```
```css
.modal-title { font:600 var(--fs-section)/1.15 var(--font-sans); color:var(--text-primary); }
.modal-body  { font:400 var(--fs-base)/var(--lh-cjk) var(--font-sans); color:var(--text-secondary); }
.chip.live   { font:600 var(--fs-micro)/1.15 var(--font-sans); letter-spacing:var(--ls-caps);
  color:#fff; background:var(--live); border-radius:5px; padding:1px 6px; margin:0 4px; }
.confirm-figure{ font:600 var(--fs-hero)/1 var(--font-mono);
  font-variant-numeric:tabular-nums slashed-zero; letter-spacing:var(--ls-hero); }
.mono        { font:400 var(--fs-dense)/1.30 var(--font-mono); color:var(--text-secondary); }
```
The `LIVE` chip is the only place `--live #ff5457` touches type; the order size is rendered at hero scale (27, mono, `--neg`) so magnitude and direction are unmistakable before typed confirm. Body uses `--lh-cjk` 1.60 because it's a multi-line Chinese sentence.

### 6.5 Status ladder eyebrow (environment)

```
研究 · 重放 · 紙上 · 模擬 · 實盤     ← Chinese, ls:0
RESEARCH·REPLAY·PAPER·DEMO·LIVE     ← Latin gloss, uppercase, ls:0.08em, muted 11
```
Latin token uppercased+tracked reads as the machine-ladder; Chinese primary stays natural-spaced. Active step promotes: color `--text-primary` + weight 600; inactive steps `--text-muted` 510.

---

## 7. Enforcement notes (governance-aligned)

- All values above are `var(--*)` — **no inline `style=`, no per-page `<style>`.** Density and state switch via `data-density` / class hooks writing to component vars. The one sanctioned exception (JS `el.style.setProperty('--x', v)`) applies only to runtime-computed values like a sparkline height, never to type tokens.
- Three-tier flow respected: primitive (`--fs-*`, `--lh-*`, `--ls-*`, `--weight-*`) → semantic (`--fs-cell`, `--fs-colhead`, `--fs-btn`) → component (`.kpi-value`, `.section-head`, `td.num`). Components must consume semantic/primitive tokens, never raw px.
- Lint rules to add: (1) reject `px` font-size in component CSS (must be `var(--fs-*)`); (2) reject `text-transform:uppercase` on any selector that can match `:lang(zh)`; (3) reject `letter-spacing` > 0 on CJK-bearing selectors; (4) require `font-variant-numeric` on any `.num`/`td.num`; (5) reject hyphen-minus in rendered numbers (enforce U+2212 in the formatter).
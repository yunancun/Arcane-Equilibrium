I have enough grounding. Concrete findings from the live GUI to anchor the spec: current tokens are GitHub-Primer-ish (`--bg #0d1117`, `--accent #58a6ff`) — close to but not the S1 targets; **1,375** inline `style=` occurrences (the governance target); emoji-as-icon is pervasive and inconsistent (⚠×77, ✓×38 competing with ✔×4/✅×7, ✗×13 vs ✖×2/❌×8, 🔴 overloaded for both live and error); radii are chaotic (14px×9, 8px×7, plus 3/4/6/10/12/18/999). Below is the definitive visual-identity spec.

---

# S1 "Terminal" — Aesthetic / Visual-Identity System
### The one-instrument spec. Build on the established tokens; this hardens them into a closed system.

**North star:** chrome is a colorless instrument panel; hue is a *reading*, not decoration. If you see saturated color anywhere, it is making a claim about pnl, risk, state, or real-money danger — nothing else. Every tab is the same instrument with different gauges.

---

## 1. COLOR SYSTEM

### 1.1 The neutral ramp (Radix/Geist-style, cool-biased)

One 12-role cool-gray scale drives 95% of every screen. Hue is biased ~220° (toward the blue accent) so neutrals and accent share a family and never clash. Steps are **role-named**, not numbered-in-the-wild — components reference the *role*, so a re-tune touches one line.

| Role token | Role (Radix idiom) | Dark hex | Light hex | Primary use |
|---|---|---|---|---|
| `--gray-1` `--bg-app` | app background | `#0a0c10` | `#f4f6f9` | outermost canvas, body |
| `--gray-2` `--bg-sunken` | subtle / well | `#0c0e13` | `#eceff3` | inset wells, table body behind sticky header, code |
| `--gray-3` `--bg-surface` | component bg | `#101319` | `#ffffff` | cards, panels, table surface |
| `--gray-4` `--bg-raised` | raised / secondary bg | `#161a21` | `#fbfcfd` | raised tiles, dropdown menu, popover body |
| `--gray-5` `--bg-hover` | hover / selected | `#1c212a` | `#eef1f5` | row hover, selected tab, active nav |
| `--gray-6` `--border-subtle` | subtle border | `#202632` | `#e2e7ee` | gridlines, internal dividers, card inner rules |
| `--gray-7` `--border` | UI element border | `#29303d` | `#cfd7e1` | input/button resting border, panel edge |
| `--gray-8` `--border-strong` | strong / hover border | `#313947` | `#b4becb` | input hover/focus base, emphasized panel edge |
| `--gray-9` `--solid-muted` | solid low | `#3d4757` | `#8b95a3` | disabled solid fills, track backgrounds, skeleton base |
| `--gray-10` `--solid` | solid hover | `#4a5568` | `#79838f` | skeleton shimmer peak, slider track fill |
| `--gray-11` `--text-secondary` | low-contrast text | `#98a2b0` | `#565e6b` | secondary labels, units, axis ticks |
| `--gray-12` `--text-primary` | high-contrast text | `#e7edf4` | `#12161c` | primary numbers, headings, body |
| `--text-muted` | (between 9–11) | `#656e7c` | `#7b8593` | tertiary/disabled text, placeholders, timestamps |

**Reading the ladder (dark):** app `#0a0c10` → surface `#101319` → raised `#161a21` → hover `#1c212a`. Each rung is ~+4–6 in luminance. That single monotonic climb *is* the elevation system (see §2).

**Light is not an invert.** In dark, higher = lighter; in light, the ladder compresses toward white and elevation is carried by **whiter surface + hairline**, not by darkening. `--bg-app` is the *cool gray*, cards go to `#ffffff`, and `--bg-raised` (`#fbfcfd`) sits a hair above the surface. Text primary is a near-black with a cool cast (`#12161c`), never pure `#000`.

### 1.2 The semantic layer (mapped onto roles, dark ~4.5:1)

Six meanings, each with a **foreground** (text/glyph/border) and a low-luminance **`-bg` tint** (chip/row fill). Tints are given as a pre-composited solid *and* the rgba recipe over `--bg-surface` so either implementation matches.

| Token | Meaning | Dark fg | Dark `-bg` (solid ≈ recipe) | Light fg | Light `-bg` |
|---|---|---|---|---|---|
| `--pos` | profit / up / healthy | `#3fb950` | `#122417` ≈ `rgba(63,185,80,.13)` | `#197f3c` | `#e7f6ec` |
| `--neg` | loss / down / breach | `#f85149` | `#2a1514` ≈ `rgba(248,81,73,.13)` | `#cf222e` | `#fdeceb` |
| `--warn` | caution / degraded / stale | `#d6a419` | `#241d0c` ≈ `rgba(214,164,25,.12)` | `#9a6700` | `#fbf3dc` |
| `--accent` | selection / focus / info / active | `#4c8dff` | `#11213c` ≈ `rgba(76,141,255,.14)` | `#0b62d6` | `#e6effd` |
| `--live` | **real-money armed** | `#ff5457` | `#2b1215` ≈ `rgba(255,84,87,.16)` | `#e5484d` | `#fdeaea` |
| `--info`/mute | neutral status | `--text-secondary` | `--bg-hover` | `--text-secondary` | `--bg-hover` |

Each semantic also gets a `-border` (the fg at ~40% over the tint) for chip outlines: e.g. `--pos-border: #1f4a2b` dark / `#a8d8b6` light.

### 1.3 The three governing rules

1. **95% neutral / hue is earned.** Chrome — nav, panels, borders, labels, buttons, icons, table structure — is *exclusively* the gray ramp. Saturated hue appears only where it encodes pnl sign, a state, focus/selection, or live-armed. A screen at rest with no positions and no alerts should be **monochrome**. If a designer reaches for `--accent` to "make it pop," that is a bug.
2. **Accent-in-data-only.** `--accent` (`#4c8dff`) is not a brand-paint. It is licensed for exactly four jobs: (a) focus/selection state, (b) the single primary action per view, (c) informational data marks (an "info" chip, a series line in a chart), (d) active-nav indicator. It never fills a card, never a decorative header, never a resting button.
3. **`--live` never dilutes by theme.** `#ff5457` / light `#e5484d` stay maximally hot in both modes — the live red is the one color that must not soften to fit a palette. It is reserved *solely* for real-money-armed surfaces (see §5.6). It never appears as a generic "error"; use `--neg` for losses/failures. Overloading live-red onto errors is the single most dangerous palette mistake in this console. (Current GUI violates this — `🔴` is used for both; must split.)

---

## 2. ELEVATION & BORDERS

### 2.1 Luminance ladder, not shadow ladder

Depth is expressed by **surface luminance + a hairline**, never by drop shadows (shadows read as "web app," not "instrument"). Four in-flow rungs:

| Surface tier | Dark | Light | Border | Where |
|---|---|---|---|---|
| **surface-0** app | `--bg-app` `#0a0c10` | `#f4f6f9` | none | body canvas |
| **surface-1** panel/card | `--bg-surface` `#101319` | `#ffffff` | `1px --border-subtle` | KPI tiles, tables, panels |
| **surface-2** raised | `--bg-raised` `#161a21` | `#fbfcfd` | `1px --border` | nested cards, menus, popover, sticky table header |
| **surface-3** hover/active | `--bg-hover` `#1c212a` | `#eef1f5` | `1px --border` or `--border-strong` | row hover, selected item, open control |

Rule: **go up a rung by lightening one step and, if it's a distinct container, adding the next-heavier hairline.** Never stack more than surface-2 in normal flow; surface-3 is transient (hover/active).

### 2.2 Hairline border tokens — exact assignment

| Border token | Value (dark) | Weight | Used for |
|---|---|---|---|
| `--border-subtle` `#202632` | 1px | gridlines, table row rules, internal dividers, card inner separators |
| `--border` `#29303d` | 1px | panel/card outer edge, resting inputs & buttons, tab underline track |
| `--border-strong` `#313947` | 1px | input hover, emphasized/section panel edge, active tab border, table sticky-header bottom rule |
| `--accent` `#4c8dff` | 2px | focus-visible ring only (see §6) |
| `--live` `#ff5457` | 2px (+ `-bg` fill) | real-money panel frame |

Gridlines vs panel edges: **gridlines are always `--border-subtle`** (recede), **panel edges always `--border`** (define the container), **focus is always 2px accent**. Never mix — a designer should be able to name the border weight from its role alone.

### 2.3 The single sanctioned shadow — overlays only

Exactly one shadow token, used *only* for surfaces that float above the plane (modal, popover, dropdown, toast, command palette). In-flow elements never cast it.

```
--shadow-overlay:
  0 8px 24px -6px rgba(0,0,0,.60),
  0 2px  6px -2px rgba(0,0,0,.45);          /* dark */
--shadow-overlay (light):
  0 8px 24px -8px rgba(16,24,40,.16),
  0 2px  6px -3px rgba(16,24,40,.10);
```

Overlays combine shadow **+** a `--border-strong` hairline **+** surface-2 luminance so they read as lifted in both themes (shadow alone is nearly invisible on `#0a0c10`).

---

## 3. ICONOGRAPHY

### 3.1 Strategy: one inline SVG sprite sheet. Zero emoji. Zero CDN.

**Decision: inline SVG `<symbol>` sprite.** A single `icons.svg` sheet (`<svg><symbol id="ic-warn" viewBox="0 0 24 24">…</symbol>…</svg>`) is inlined once into `console.html`; every icon is `<svg class="ic"><use href="#ic-warn"/></svg>`. This is the only approach that satisfies *all* governance constraints: no webfont/CDN (CSP-safe, offline), `currentColor` inheritance (icons obey the neutral rule automatically), crisp at any DPI, one HTTP payload, and no per-page `<style>`.

**Why emoji must go entirely:** emoji (a) render with OS-controlled *color*, which detonates the monochrome-chrome rule (an uncontrolled hue on every button); (b) vary in glyph/baseline/weight across macOS/Win/Linux — the console must look identical on the Mac dev box and the Linux runtime; (c) cannot inherit `currentColor`, so they can't participate in muted/hover/disabled states; (d) are used inconsistently today (✓/✔/✅ are three "OK" glyphs; ✗/✖/❌ three "bad"; 🔴 means both live and error). **All 40+ emoji become named sprite icons or CSS state dots.**

### 3.2 Sizing, stroke, color

| Property | Value |
|---|---|
| Grid | 24×24 viewBox, 1.5px stroke, round cap/join, no fill (line icons) |
| Render size | **16px** default; **14px** compact/inline-in-text; **20px** section headers & empty-states; **12px** only for the disclosure caret |
| Color | `stroke: currentColor` → inherits `--text-secondary` by default; hover/active lifts to `--text-primary` via the *text* color, not an icon override |
| Hit area | icon is decorative; the *interactive* wrapper is min 24×24 (dense) / 32×32 (comfortable) — see §6 |
| Optical alignment | icons in a text run get `vertical-align: -0.125em`; never rely on emoji baseline |

Semantic-colored icons are the **exception**, allowed only where the icon *is* the state (status chip glyph, live-armed shield): the icon then takes the semantic fg (`--warn`, `--neg`, `--live`) — same license as any hue.

### 3.3 When an icon is allowed vs. noise

- **Allowed:** state that must be scannable pre-reading (status chip, direction arrow, live shield, stale-clock); disclosure affordance (caret); a genuinely iconic action with no room for a label (close ✕, copy, expand, external-link); nav-rail lane/environment markers.
- **Noise (ban):** decorating a text label that already says the thing (`💰 Balance`, `🤖 AI` — drop the glyph, keep the word); one-off illustrative flourishes; two icons meaning the same state; emoji as bullet points.

### 3.4 Emoji → sprite mapping (rationalize the current 40+)

| Current emoji (count) | Replace with | Color |
|---|---|---|
| ⚠ (77) | `#ic-warn` (triangle) | `--warn` (or inherit in neutral context) |
| ✓ ✔ ✅ (38+4+7) — **collapse to one** | `#ic-check` | `--pos` in status, else inherit |
| ✗ ✖ ❌ (13+2+8) — **collapse to one** | `#ic-x` / `#ic-close` (distinguish "failed-state" vs "dismiss") | `--neg` for fail; inherit for dismiss |
| 🔴 (8) — **overloaded, split** | live→`#ic-shield-live` (`--live`); error→`#ic-x` (`--neg`); status→CSS dot | per meaning |
| 🟢 🟡 🟠 🟣 🔵 | **CSS `::before` status dots** (§5.2), not glyphs | semantic |
| 🔒 (8) / 🔓 | `#ic-lock` / `#ic-unlock` | inherit |
| 🧪 (5) | `#ic-flask` (replay/paper env) | inherit |
| 🤖 (5) | `#ic-cpu` (AI/agent) | inherit |
| 🚨 (5) | `#ic-alert` | `--neg`/`--live` per context |
| 👁 👀 (4+1) | `#ic-eye` (watch/monitor) | inherit |
| 🌑 🌙 / ☀ | `#ic-moon` / `#ic-sun` (theme toggle) | inherit |
| 🐢 🪫 💤 🥶 (perf/dormant states) | `#ic-slow` / `#ic-battery-low` / `#ic-pause` | inherit/`--warn` |
| 💰 📜 💾 🔄 🔍 🗂 🛡 🔌 | named line icons | inherit |

---

## 4. MOTION

### 4.1 Discipline: functional only

Motion exists to (a) confirm a value changed, (b) show where a thing came from (disclosure), (c) mask latency (skeleton/shimmer), (d) acknowledge a pointer. Nothing moves for delight. An instrument that animates decoratively reads as untrustworthy.

### 4.2 Tokens

```
--dur-instant: 80ms;    /* micro: dot pulse tick, checkbox */
--dur-fast:    120ms;   /* hover bg, border, icon color */
--dur-base:    200ms;   /* disclosure, chip in/out, tab switch */
--dur-slow:    320ms;   /* modal/overlay enter, large panel expand */
--ease-out:    cubic-bezier(0.2, 0, 0, 1);      /* default — decelerate in */
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);    /* two-way (expand/collapse) */
--ease-in:     cubic-bezier(0.4, 0, 1, 1);      /* exits only */
--shimmer-dur: 1200ms;  /* skeleton sweep, linear infinite */
```

### 4.3 Per-interaction spec

| Interaction | Property | Duration / easing |
|---|---|---|
| Hover feedback (row, button, tab) | `background-color`, `border-color`, `color` | `--dur-fast` / `--ease-out` |
| Focus ring appear | `outline`/`box-shadow` | `--dur-instant` (near-instant; ring must feel immediate) |
| Chip / badge enter/exit | `opacity` + 2px `translateY` | `--dur-base` / `--ease-out` |
| Disclosure expand/collapse | `grid-template-rows: 0fr↔1fr` (or height), caret `rotate(0↔90deg)` | `--dur-base` / `--ease-in-out` |
| Tab / panel switch | `opacity` crossfade (no slide) | `--dur-base` / `--ease-out` |
| Modal / overlay enter | `opacity` + `scale(0.98→1)`; backdrop `opacity` | `--dur-slow` / `--ease-out` |
| Skeleton shimmer | background-position sweep | `--shimmer-dur` linear infinite |
| Live value tick (number changed) | brief `--pos-bg`/`--neg-bg` flash on the cell, fade out | in `--dur-instant`, out `--dur-slow` |
| Status-dot "live/streaming" | opacity pulse 1↔0.4 | 1600ms ease-in-out infinite (the *only* sanctioned looping animation besides shimmer) |

### 4.4 What NOT to animate

- Never animate **layout of live data** (positions rows reordering, KPI numbers sliding) — the number changes in place; only a subtle tint-flash marks it. Sliding rows destroys scan-speed and can hide a fill.
- No parallax, no easing on scroll, no bouncy/`elastic`/`back` easings, no spinners longer than a skeleton (>1 cycle → use skeleton).
- No hover animation on non-interactive elements.
- No entrance animation on initial page paint (data must be readable at frame 1).
- Duration ceiling for any state change is `--dur-slow` (320ms). Nothing in the console animates longer, except the two sanctioned infinite loops (shimmer, live-pulse).

### 4.5 Reduced motion

```
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
    scroll-behavior: auto !important;
  }
}
```
State still *changes* (colors, carets, expansion) — instantly. The **live-pulse and shimmer stop entirely** (freeze at full opacity); replace the streaming pulse with a static filled dot so "live" is still legible without motion.

---

## 5. STATE VISUAL LANGUAGE

One chip anatomy, one dot, one caret, one skeleton — reused identically in all 18 tabs. This section *is* the "one instrument" guarantee.

### 5.1 Chips / badges — universal anatomy

`radius 5px · height 20px (compact) / 24px (comfortable) · padding 0 8px · 11px/500 uppercase-optional label · optional 12px leading icon · gap 6px`. Structure: `background:<sem>-bg · color:<sem> · border:1px <sem>-border`. **Redundant encoding is mandatory** — every chip pairs color with a second channel (icon glyph AND/OR text token):

| Variant | bg / fg / border | Icon | Example label (this console) |
|---|---|---|---|
| `ok` | `--pos-bg` / `--pos` / `--pos-border` | `#ic-check` | `GREEN` · `已對帳 Reconciled` · `net+ 8.75bps` |
| `warn` | `--warn-bg` / `--warn` / `--warn-border` | `#ic-warn` | `DEGRADED` · `stale 42s` · `MIN_SAMPLES 未達` |
| `bad` | `--neg-bg` / `--neg` / `--neg-border` | `#ic-x` | `BREACH` · `rejected` · `−17.82bps` |
| `info` | `--accent-bg` / `--accent` / `--accent-border` | `#ic-info` | `SHADOW` · `canary` · `dormant` |
| `mute` | `--bg-hover` / `--text-secondary` / `--border` | (none) | `n/a` · `disabled` · `—` |
| `live` | `--live-bg` / `--live` / `--live` (2px) | `#ic-shield-live` | `LIVE · REAL FUNDS` (see §5.6) |

### 5.2 Status dots (replacing 🟢🟡🟠🔴🟣)

CSS `::before`, **8px** circle, `border-radius:50%`, `margin-right:8px`, color = semantic. Never an emoji. States: `--pos` healthy / `--warn` degraded / `--neg` down / `--accent` info-active / `--text-muted` idle-off / `--live` armed. **Streaming/connected** dot adds the sanctioned pulse (§4.3); a *static* dot means "known state, not live-updating." Grayscale survivability: dot alone is ambiguous → always followed by a text label (`● 連線 Connected`), never a bare dot.

### 5.3 Disclosure caret

`#ic-caret` 12px, resting `rotate(0)` pointing right, expanded `rotate(90deg)`, `--dur-base`/`--ease-in-out`, color `--text-secondary` → `--text-primary` on hover. Single caret glyph everywhere (status-ladder rows, collapsible panels, tree rows). Never ▶/▼ emoji, never swap glyphs.

### 5.4 Skeletons

Base `--solid-muted` block at the exact final element's radius/size; shimmer = a `--solid` (`#4a5568`) 120px linear-gradient band sweeping L→R over `--shimmer-dur`. Rules: skeleton mirrors the real layout (a table skeleton has rows/columns), never a generic spinner for data; numeric cells skeleton at tabular width so no reflow on load; **min display 300ms** to avoid flash, but if data arrives <150ms show nothing (no skeleton flash).

### 5.5 Freshness / stale badge

Data age is a first-class state (this is a trading console — stale data is dangerous). A `staleness` chip attaches to any live feed:

| Age | Treatment |
|---|---|
| fresh (< 1× expected interval) | no chip, or `mute` dot only |
| aging (1–3×) | `warn` chip `#ic-clock` + `stale {n}s` |
| stale (> 3× or feed down) | `bad` chip `#ic-clock-off` + `STALE {mm:ss}`, and the associated **numbers dim to `--text-muted`** (data you can't trust must visibly lose confidence) |

The dimming-on-stale rule is what makes a frozen feed unmissable — color-blind-safe because it's a luminance change, not a hue swap.

### 5.6 Real-money hardening — the `--live` treatment

The Live lane/tab and any real-money-armed control get a **persistent, physically distinct** treatment that cannot be confused with paper/demo:

1. **Persistent banner** pinned top of the Live surface: full-width `--live-bg`, 2px `--live` bottom border, `#ic-shield-live` + `⚠ REAL FUNDS · 真實資金` in `--live` 13px/600 — always visible, never scrolls away, never dismissible.
2. **Live-armed panel frame:** the active-execution panel carries a 2px `--live` border (the only 2px non-focus border in the system) + `--live-bg` fill.
3. **Physical separation:** real-money action buttons live in their own bottom-anchored zone, not inline with benign controls; a `--border-strong` divider + spacing-32 gap separates them from research/replay controls.
4. **Typed-confirm modal** for any live order/arm: user must type the symbol or `LIVE` to enable the confirm button; confirm button is the only element allowed a solid `--live` *fill* with `--bg-app` text; cancel is a neutral ghost button of equal-or-greater visual weight.
5. **Never reused:** `--live` red appears *only* in these contexts. Paper/replay/demo lanes use `--accent`/`--warn`/neutral env chips (`#ic-flask` paper, `#ic-history` replay) so the eye learns live-red = money at risk, exclusively.

---

## 6. FOCUS & ACCESSIBILITY

### 6.1 Focus-visible ring

```
--focus-ring: 0 0 0 2px var(--bg-app), 0 0 0 4px var(--accent);
:where(a,button,input,select,[tabindex]):focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
  border-radius: inherit;
}
```
Double-ring (2px app-bg gap + 2px accent) so the ring reads on any surface rung, dark or light. `:focus-visible` only (no ring on mouse click of buttons; always on keyboard). On inputs already bordered, the ring replaces the resting border color with `--accent` and adds the outer halo. Ring appears in `--dur-instant`. The ring is `--accent` in both themes; on the live-armed confirm, the ring becomes `--live` to keep contrast against the red fill.

### 6.2 Hit targets in dense rows (WCAG 2.2 §2.5.8)

Comfortable rows are ~34px (targets clear 24×24). **Compact rows are ~27px** — below the 44px AAA target but the row itself and inline controls must still meet the **24×24 minimum**. Rules:
- Any interactive glyph (caret, close, icon-button) sits in a `min-width:24px; min-height:24px` hit box even when the visible icon is 12–16px (padding makes up the difference).
- Row-level actions: the *entire row* is the click target where possible; per-cell icon-buttons keep 24px hit boxes with ≥4px spacing between adjacent targets (2.5.8 spacing exception).
- Never place two <24px targets closer than they can be individually hit; if space-constrained, collapse to a `⋯` overflow menu (single 24px target).

### 6.3 Contrast floors

| Content | Floor | Notes |
|---|---|---|
| Primary text / numbers | 7:1 (AAA where feasible) | `--text-primary` on surfaces clears this |
| Secondary text, labels | 4.5:1 (AA) | `--text-secondary` tuned to ~4.6:1 on `--bg-surface` |
| Muted/disabled text | 3:1 min | `--text-muted` — never used for load-bearing info |
| Semantic fg on its `-bg` tint | 4.5:1 | verified per pair; chip text always legible |
| UI borders / focus ring / dots | 3:1 vs adjacent (2.2 §1.4.11) | `--border-strong` & `--accent` clear it |
| Large numbers (KPI 27px) | 3:1 acceptable but we hold 4.5:1 | |

### 6.4 Grayscale survivability (CVD-safe, mandatory)

**Every** state that carries meaning through color must survive a grayscale render — because 8% of male traders have CVD and because a printed/screenshotted P&L must still parse. Enforcement: pnl/direction/status = color **+** one of {sign `+/−`, arrow `↑/↓`, text token, icon}. Stale = color **+** luminance dim. Live = color **+** persistent text `REAL FUNDS` + shield icon + physical placement. Test: run the console through a grayscale filter; if any state becomes ambiguous, it's non-compliant.

---

## 7. THE "FEEL" — identity principles + do/don't

### Seven principles
1. **Instrument, not interface.** It reads like a Bloomberg/oscilloscope panel: dense, calm, colorless at rest. Whitespace is structural, not luxurious.
2. **Color is a claim.** Every saturated pixel asserts something about risk, pnl, state, or money. No color is ever "just style."
3. **Elevation is light, not shadow.** Depth = a lighter surface + a hairline. Shadows exist only for things that truly float.
4. **The number is the hero.** Tabular mono numerals, tight alignment, no chart-junk. Chrome recedes so data advances.
5. **State reads pre-reading.** Chips, dots, and dimming let an operator parse health in a glance before reading a word — and it reads identically in every one of the 18 tabs.
6. **Real money looks like real money.** Live-red is sacred, loud, and never borrowed for anything else.
7. **Motion earns its keep or doesn't exist.** If an animation isn't confirming a change or masking latency, delete it.

### Do / Don't

| Do | Don't |
|---|---|
| Keep chrome on the neutral ramp; let a screen at rest be monochrome | Sprinkle `--accent` to "liven up" panels or headers |
| Reserve `--live` red strictly for real-money-armed surfaces | Use live-red (or 🔴) for generic errors — that's `--neg` |
| Use radii **5 / 8 / 12** only (controls / cards / modals) | Pill-round a data control (`999px`/`18px`) — kills the instrument feel *(current GUI has both)* |
| Encode state in ≥2 channels (color + icon/sign/text) | Rely on hue alone for pnl or status |
| Depth via surface luminance + hairline | Add drop-shadows to in-flow cards |
| Inline-SVG sprite icons inheriting `currentColor` | Emoji-as-icon (uncontrolled color, OS-variant, no currentColor) *(current GUI: 40+ emoji, must remove)* |
| Flat matte surfaces from the cool-gray ramp | Decorative gradients, glows, glassmorphism, tinted-glass blur |
| Change numbers in place with a tint-flash | Animate rows sliding/reordering on data update |
| One chip/dot/caret/skeleton spec across all tabs | Bespoke per-tab badges — that's the 18-bespoke-tabs failure |
| Bilingual label (zh visible / en on title=) | Inline `style=` attributes (target: eliminate all **1,375**) |

---

## 8. LIGHT MODE (equal-care, not an invert)

Light is a **cool, low-glare "daylight instrument"** — an off-white canvas (never `#fff` body, which glares under a trading-floor light), white cards that lift by luminance + hairline, near-black cool text. The full light ramp is in the §1.1 table; the additions specific to light:

### 8.1 Light-mode elevation flips direction
In dark, higher = lighter. In light, the app canvas is the *gray* (`#f4f6f9`), and elevation climbs **toward white**: surface cards `#ffffff`, raised `#fbfcfd`. Because you can't go lighter than white, surface-2/3 lean harder on the **hairline** (`--border` → `--border-strong`) and, for true overlays only, the light `--shadow-overlay`. Wells/sunken go *darker* than app (`#eceff3`).

### 8.2 Semantics re-tuned for legibility on white
Dark-tuned neons wash out on white, so foregrounds darken while tints stay pale:

| Token | Light fg (on white ≥4.5:1) | Light `-bg` | Note |
|---|---|---|---|
| `--pos` | `#197f3c` | `#e7f6ec` | green darkened for text-on-white |
| `--neg` | `#cf222e` | `#fdeceb` | |
| `--warn` | `#9a6700` | `#fbf3dc` | amber must go brown-gold; `#d6a419` fails on white |
| `--accent` | `#0b62d6` | `#e6effd` | ring & selection stay clearly blue |
| `--live` | `#e5484d` fg / solid fill for confirm | `#fdeaea` | **still vivid** — the live banner/frame must feel as urgent in light as in dark; do not soften to fit the palette |
| text-secondary | `#565e6b` | — | verified ~4.6:1 on `#ffffff` |

### 8.3 Light-mode specifics
- **Borders carry more load:** `--border-subtle #e2e7ee` for gridlines, `--border #cfd7e1` for panels — slightly stronger relative to bg than dark, since white-on-white needs the line to define edges.
- **Focus ring** stays `--accent #0b62d6` with the double-ring; inner gap becomes `--bg-app` (`#f4f6f9`) so it reads on white cards.
- **Skeletons** invert: base `#e6e9ee`, shimmer peak `#f2f4f7` (never gray-on-white so dark it looks like content).
- **Chart/data marks** re-pick from light semantics; a series line at `--accent` light is `#0b62d6`.
- **Live banner** in light: `--live-bg #fdeaea` fill, 2px `#e5484d` border, `#e5484d` text — verified to read as "danger," not "pink accent."
- **The neutral rule holds identically:** a resting light screen is cool-gray + white, monochrome; hue only on data/state.

---

### Implementation notes for E1a
- Ship as three-tier tokens: primitive ramp (`--gray-1..12`, semantic hues) → semantic roles (`--bg-*`, `--text-*`, `--border-*`, `--pos/neg/warn/accent/live` + `-bg`/`-border`) → component vars. Theme switch flips *primitive→semantic* mapping under `:root[data-theme="light"]` / `@media (prefers-color-scheme)`; components never reference primitives directly.
- Radius tokens `--radius-control:5px; --radius-card:8px; --radius-modal:12px;` — retire the 3/6/10/14/18/999 values found in `styles.css`.
- One `icons.svg` sprite inlined in `console.html`; migrate all emoji per §3.4.
- Governance lints to add: ban `style=` (1,375 to remove), ban per-page `<style>`, ban hex literals outside the token file, ban emoji in markup, ban `border-radius` values outside the three tokens.
- Relevant source: `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/styles.css` (651 lines, current `:root` at lines 1–21) and the 18 `tab-*.html` files that carry the inline styles and emoji.
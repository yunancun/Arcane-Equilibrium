# W7-4 5 策略 STRATEGY-POSITION-SYNC systemic audit (post-W7 chain land)

**Date**: 2026-05-10
**Author**: PA
**Scope**: read-only audit of 5 strategies for W7-2/3/5 fix coverage uniformity. Discover whether identical STRATEGY-POSITION-SYNC bug pattern exists in non-fixed strategies.
**Predecessor**: W7-3 `b42731f6` deployed (engine PID 1441249) + W7-1 `c9fb0b8f` + W7-2 `22efd9de` + W7-5 `bb7cb293` PR ready (NOT DEPLOYED yet — pending sign-off restart). HEAD `94d688fb`.
**This audit complements**: 2026-05-10 PA #3 P1-MA-CROSSOVER root-cause audit + earlier `2026-05-10--w7_4_systemic_position_sync_audit.md` (pre-IMPL verdict). This refresh verifies post-IMPL coverage matrix per the 4-point audit framework requested.

---

## §1 Executive Summary

| 策略 | (1) entry query | (2) on_fill sync | (3) on_rejection 1-tick defense | (4) bootstrap import | Overall |
|---|---|---|---|---|---|
| `ma_crossover` | PASS | PASS | PASS | PASS | **A — full W7 coverage** |
| `bb_reversion` | PASS | PASS | **WARN — missing 1-tick defense** | PASS | **B — entry guarded but residual hot-loop window** |
| `bb_breakout` | **FAIL — no entry query** | PASS | **FAIL — no 1-tick defense** | PASS | **C — desync hot-loop structurally possible** |
| `grid_trading` | N/A (inventory model) | PASS (no-op by-design) | N/A (M-2 30s backoff) | PASS | **A — by-design alternative architecture** |
| `funding_arb` | N/A (RETIRED-LOW dormant) | PASS (defensive) | N/A (1h cooldown + dormant) | PASS | **A — by-design dormant** |

**Discovered tickets**: **0 P0** (no immediate live blocker — engine still pre-W7-2/W7-5 deploy, so post-deploy state matters most), **2 P1** (bb_reversion + bb_breakout on_rejection 1-tick defense), **1 P2** (bb_breakout entry path query Option A coverage).

**Cross-strategy systemic finding**: W7-3 Option B 1-tick defense (added to `ma_crossover.on_rejection` in `b42731f6`) **was not propagated to bb_reversion or bb_breakout** in W7-2 (`22efd9de`). W7-2 added entry path query (Option A) to ma_crossover + bb_reversion, but the on_rejection-side defense remains ma_crossover-only. This is a **partial systemic fix** — W7-2 closes the trigger, but the contract-fallback safety net (W7-3 Option B) is not uniform.

---

## §2 Per-strategy verdict

### grid_trading

| Audit point | Status | Evidence | Risk |
|---|---|---|---|
| (1) entry query position | N/A | `grid_trading/signal.rs:151-203` uses `net_inventory: HashMap<String,f64>` + `last_cross_idx`, not `ctx.position_state`. M-2 backoff `signal.rs:137-141` is the structural guard. | LOW |
| (2) on_fill sync | PASS (by-design no-op) | `grid_trading/mod.rs:337-350` writes nothing — entry path eagerly mutates `net_inventory` at signal emit (`signal.rs:242,274`); on_fill double-write would be redundant for inventory model. W7-5 commit explicitly documents "by-design no-op for inventory model". | LOW |
| (3) on_rejection identify duplicate | N/A | `grid_trading/position_mgmt.rs:162-194` `on_rejection_impl`: M-2 arms `reject_cooldown_until_ms = emit_ts + reject_backoff_ms` (default 30s). `signal.rs:137-141` checks at on_tick entry → structurally impossible for grid to hot-loop on duplicate_position. | LOW |
| (4) bootstrap import | PASS | `grid_trading/mod.rs:358-374` `import_positions`: filters `pos.owner_strategy == "grid_trading"`, rebuilds `self.net_inventory[symbol] = if pos.is_long { qty } else { -qty }` (sign convention preserved). | LOW |

**Verdict**: A — by-design alternative architecture (inventory model + M-2 backoff) makes W7 pattern not applicable. No new ticket.

---

### ma_crossover (W7-2/3/5 deployed → all 4 PASS)

| Audit point | Status | Evidence | Risk |
|---|---|---|---|
| (1) entry query position | PASS | `strategy_impl.rs:253-266` (W7-2 Option A): `if let Some(existing) = ctx.position_state { self.positions.insert(sym, existing.is_long); return vec![]; }` — `None` branch entry only when paper_state has no position for sym. | LOW |
| (2) on_fill sync | PASS | `strategy_impl.rs:131-148` (W7-5 part 1): `self.positions.insert(intent.symbol, intent.is_long)` after fill confirmed. Idempotent O(1). | LOW |
| (3) on_rejection identify duplicate | PASS | `strategy_impl.rs:55-91` (W7-3 Option B): parses `reason.contains("duplicate_position") + already LONG/SHORT`, syncs self.positions to paper_state direction without RC-04 rollback. Falls back to RC-04 if reason contract drift. | LOW |
| (4) bootstrap import | PASS | `strategy_impl.rs:159-175` (W7-5 part 2): filters `pos.owner_strategy == "ma_crossover"`, rebuilds self.positions from paper_state. | LOW |

**Verdict**: A — full W7 coverage. Three concentric defenses (W7-2 entry-path Option A → W7-3 on_rejection Option B → W7-5 fill+bootstrap sync). Reference implementation for other strategies.

---

### bb_breakout — **2 GAPs identified**

| Audit point | Status | Evidence | Risk |
|---|---|---|---|
| (1) entry query position | **FAIL** | `bb_breakout/mod.rs:567-569` reads `current_position = self.symbols.get(sym).and_then(|s| s.position)` (own state). **No `ctx.position_state` query in None branch (line 570+)**. grep `ctx.position_state` against `bb_breakout/mod.rs` returns 0 hits. | **MEDIUM** |
| (2) on_fill sync | PASS | `bb_breakout/mod.rs:335-348` (W7-5 part 1): `self.symbols.get_or_init(&intent.symbol).position = Some(intent.is_long)`. entry_price/trailing_stop intentionally not overwritten. | LOW |
| (3) on_rejection identify duplicate | **FAIL** | `bb_breakout/mod.rs:394-429` `on_rejection`: only RC-04 rollback (with oi_buffer preservation per EDGE-P2-2 FUP). **No `duplicate_position` branch**. grep `duplicate_position` against `bb_breakout/mod.rs` returns 0 hits. | **MEDIUM** |
| (4) bootstrap import | PASS | `bb_breakout/mod.rs:355-373` (W7-5 part 2): filters `pos.owner_strategy == "bb_breakout"`, rebuilds `self.symbols.get_or_init(&pos.symbol).position = Some(pos.is_long); .entry_price = Some(pos.entry_price)`. | LOW |

**Verdict**: **C — desync hot-loop structurally possible.** Two reasons it has NOT manifested empirically (per W6 baseline):
- bb_breakout entry path requires **6 concentric gates** (squeeze 45min window + bandwidth>expansion + vol_ratio>threshold + Donchian breach `Hard` mode default + persistence 60s + confluence score) — frequency of "enter while another strategy holds same symbol" is naturally low.
- W6 baseline shows 0 visible reject burst for bb_breakout — empirically rare alignment.

**Architectural risk remains**: identical desync mechanism as ma_crossover (per-symbol state field that doesn't query paper_state). Once gates align (e.g., grid_trading holds INXUSDT + bb_breakout squeeze→expansion fires), per-tick reject loop would form, throttled only by 60s persistence (≈1 reject/min instead of ma_crossover's 30-50/sec, but still not zero).

---

### bb_reversion — **1 GAP identified**

| Audit point | Status | Evidence | Risk |
|---|---|---|---|
| (1) entry query position | PASS | `bb_reversion/mod.rs:500-512` (W7-2 Option A, mirror of ma_crossover): `if let Some(existing) = ctx.position_state { self.positions.insert(...); return intents; }`. | LOW |
| (2) on_fill sync | PASS | `bb_reversion/mod.rs:379-392` (W7-5 part 1): `self.positions.insert(intent.symbol, intent.is_long)`. | LOW |
| (3) on_rejection identify duplicate | **FAIL** | `bb_reversion/mod.rs:345-366` `on_rejection`: only original RC-04 rollback (`prev=None → self.positions.remove(sym)`). **No `duplicate_position` branch**. grep `duplicate_position` against `bb_reversion/mod.rs` returns 0 hits. | **MEDIUM-LOW** |
| (4) bootstrap import | PASS | `bb_reversion/mod.rs:398-414` (W7-5 part 2): same pattern as ma_crossover. | LOW |

**Verdict**: **B — entry guarded but residual hot-loop window.** W7-2 entry path Option A normally closes the trigger before reject. **Edge case**: if `ctx.position_state` is `None` at on_tick entry (paper_state empty for sym) but a concurrent fill from another strategy lands during this tick's on_tick→intent_emit window (race), router gate 1.5 will reject + on_rejection RC-04 rolls back to None → next tick re-enters entry path (1-tick window because at next tick, ctx.position_state = `Some(...)` from W7-2 query). **Bounded to ~1 spurious reject** because W7-2 closes within 1 tick. NOT a hot loop (unlike pre-W7 ma_crossover INXUSDT 11:34), but still produces 1 noise reject + 1 polluted decision_features row + 1 IPC noise event per race.

The **W7-3 Option B 1-tick defense pattern** (parse reason → sync self.positions → skip RC-04 rollback) would fully close even this 1-tick window, providing parity with ma_crossover. P1 ticket recommended.

---

### funding_arb (ADR-0018 dormant by design)

| Audit point | Status | Evidence | Risk |
|---|---|---|---|
| (1) entry query position | N/A | `funding_arb.rs:467-579` `on_tick` entry path: dormant when `active=false` (default per ADR-0018). 1h cooldown + 8h funding cycle structurally limits entry frequency to ≤3/day even if active. No `ctx.position_state` query. | LOW |
| (2) on_fill sync | PASS (defensive) | `funding_arb.rs:392-415` (W7-5 part 1): writes `FundingPosition { is_positive_funding: !intent.is_long, entry_ms: 0 }` + warn log if `!self.active` (orphan/race detection). | LOW |
| (3) on_rejection identify duplicate | N/A | `funding_arb.rs:356-378` `on_rejection`: only RC-04 rollback. **No `duplicate_position` branch**, but dormant + 1h cooldown structural guards make hot-loop impossible. | LOW |
| (4) bootstrap import | PASS (defensive) | `funding_arb.rs:422-445` (W7-5 part 2): filters `pos.owner_strategy == "funding_arb"`. Note **`is_positive_funding = !pos.is_long`** sign-flip preserved (per `funding_arb.rs:461-462,398` direction-mapping rule). | LOW |

**Verdict**: A — dormant by ADR-0018 + structural cooldowns make W7 pattern not applicable. No new ticket.

---

## §3 Discovered systemic issues — ticket draft

### P1-1: `bb_reversion` on_rejection W7-3 Option B 1-tick defense missing
- **Severity**: P1 (parity with ma_crossover, low fix cost, eliminates residual race window)
- **Reproduce**: W7-2 entry path query closes 99% of cases. Edge case: another strategy fills mid-tick → `ctx.position_state == None` at on_tick start, but router gate 1.5 sees position when intent arrives. on_rejection RC-04 rollback → next-tick entry path re-evaluates → W7-2 catches → 1 spurious reject + 1 polluted decision_features.
- **Fix scope**: ~30 LOC (mirror `ma_crossover/strategy_impl.rs:55-91`):
  1. Add `if reason.contains("duplicate_position")` branch at top of `on_rejection`
  2. Parse `already LONG/SHORT` and call `self.positions.insert(sym, existing_is_long)`
  3. Return early; do NOT rollback cooldown (preserve `prev_last_trade_ms`)
  4. Add 2 unit tests (already SHORT / already LONG sync)
- **Owner**: E1
- **Reviewers**: E2 (reason-string contract conformance) + E4 (regression test for race window)
- **Wave fit**: Sprint N+1 W5 phase if capacity, else Sprint N+2

### P1-2: `bb_breakout` on_rejection W7-3 Option B 1-tick defense missing
- **Severity**: P1 (no W7-2 entry query → both layers missing → architectural gap larger than bb_reversion)
- **Reproduce**: Without W7-2 entry query, bb_breakout enters entry path despite paper_state holding. 6-gate flow (squeeze + bandwidth + vol + Donchian + persistence + confluence) eventually emits intent → router gate 1.5 rejects duplicate_position → on_rejection rolls back PerSymbolState `position=None` → 60s persistence reset → repeat next persistence window.
- **Empirical**: W6 baseline 0 visible burst (gate alignment rare). But identical class of bug as ma_crossover INXUSDT 11:34.
- **Fix scope**: ~35 LOC:
  1. Add `if reason.contains("duplicate_position")` branch at top of `bb_breakout/mod.rs:394` `on_rejection`
  2. Parse `already LONG/SHORT` and call `self.symbols.get_or_init(sym).position = Some(existing_is_long)`
  3. Preserve oi_buffer per EDGE-P2-2 FUP (use `live_oi_buffer` clone before sync, mirror existing `on_rejection` logic)
  4. Return early without RC-04 rollback for `duplicate_position`
  5. Add 2 unit tests
- **Owner**: E1
- **Reviewers**: E2 (oi_buffer interaction with sync) + E4 (regression)
- **Wave fit**: Sprint N+1 W5 phase or Sprint N+2 (paired with P2-1 below)

### P2-1: `bb_breakout` entry path Option A coverage (W7-2 pattern propagation)
- **Severity**: P2 (architectural completeness — close trigger before it fires; complements P1-2)
- **Reproduce**: same as P1-2 trigger condition.
- **Fix scope**: ~30 LOC:
  1. Insert `ctx.position_state` query at top of `None` branch (line 570+) in `bb_breakout/mod.rs:on_tick`
  2. Sync `self.symbols.get_or_init(sym).position = Some(existing.is_long)` and return `vec![]`
  3. Need decision: do we also sync `entry_price`? Recommendation: **No** — entry_price drives bb_breakout-specific trailing_stop math; using cross-strategy entry price would mis-calibrate trailing. Leave `entry_price` None until next bb_breakout-emitted entry. Document trade-off in code comment.
  4. Add 3 unit tests (skip when paper_state has other strategy / proceed when None / verify entry_price not overwritten)
- **Owner**: E1
- **Reviewers**: E2 (entry_price decision rationale) + E4 (regression + integration with squeeze gate)
- **Wave fit**: Sprint N+2 (NOT urgent post P1-2 land)

### Recommendation: pair P1-2 + P2-1 in same wave
Implementing P2-1 alone leaves the on_rejection path unfortified; P1-2 alone leaves the trigger open. Both together = parity with ma_crossover. Combined LOC ~65 + 5 unit tests + ~3 hour total work. PA recommends bundling.

---

## §4 Cross-strategy pattern review

### Trait-level enforcement assessment

The `Strategy` trait (`strategies/mod.rs:73-227`) provides defaults for all 4 audit points:
- `on_tick`: required (no default), correctly enforces signature with `ctx: &TickContext`
- `on_rejection`: default no-op; `RC-04` rollback is per-strategy responsibility (not enforced)
- `on_fill`: default no-op (W7-5 added); per-strategy override is opt-in
- `import_positions`: default no-op (W7-5 added); per-strategy override is opt-in

**Architectural observation**: The trait is intentionally **permissive** — strategies opt-in to lifecycle hooks based on whether they maintain internal position state. This is correct: not every strategy will mirror paper_state internally. But the **systemic risk** is that future strategies authored without referring to ma_crossover as the gold standard could ship without entry-path Option A query, repeating the desync hot-loop class.

### Recommendation: trait-level invariant strengthening (Sprint N+2 RFC candidate)

Three options of increasing strictness:

1. **Documentation only (cheap)**: extend `Strategy::on_tick` doc comment to require: "If your strategy maintains per-symbol position state, MUST query `ctx.position_state` at entry decision point and skip when `Some(_)`." → relies on author discipline.

2. **Compile-time helper (medium)**: extract a `should_skip_for_cross_strategy_holding(ctx, self_position) -> bool` helper into `strategies::common::position_sync` that all entry-path strategies call. Doesn't enforce, but makes the right path the easy path.

3. **Trait-level invariant (high)**: add a non-overridable `Strategy::should_proceed_to_entry(&self, ctx, sym) -> bool` default that does the ctx.position_state check + self.has_internal_position_for(sym) cross-check. Strategies override `has_internal_position_for(sym) -> bool`. Compiler-enforced uniformity. **Cost**: requires changing all 5 strategies, adds 1 method per strategy. Not a Sprint N+1 fit; RFC candidate for Sprint N+3.

PA recommendation: **Option 1 now** (cheap; close P1-1/P1-2/P2-1), **Option 2 if 6th strategy gets authored** (Sprint N+3 candidate; pairs with W-AUDIT-8a 5-alpha-source migration).

### Current trait-level safety nets (positive)

`Strategy` trait DOES enforce:
- `on_tick(ctx, surface)` signature uniformity → all strategies receive `ctx.position_state` access
- `import_positions(paper_state)` callable for all → bootstrap covers all 5 (orchestrator iterates blindly)
- `on_fill(intent, fill)` callable for all → W7-5 callsite at `step_4_5_dispatch.rs:973` invokes for every strategy regardless of override

These ensure **bootstrap + on_fill coverage is uniform** by trait design — it is on_rejection (Option B) and entry-query (Option A) that need per-strategy opt-in.

---

## §5 D+1 follow-up dispatch

| Ticket | Severity | Recommended Wave | Owner | LOC est | Notes |
|---|---|---|---|---|---|
| **P1-1**: `bb_reversion` on_rejection 1-tick defense | P1 | Sprint N+1 W5 (if capacity) | E1 | ~30 | Mirror ma_crossover; minor risk; isolated change |
| **P1-2**: `bb_breakout` on_rejection 1-tick defense | P1 | Sprint N+2 W5 (paired with P2-1) | E1 | ~35 | More complex (oi_buffer interaction); pair with P2-1 |
| **P2-1**: `bb_breakout` entry path Option A query | P2 | Sprint N+2 W5 (paired with P1-2) | E1 | ~30 | Architectural; entry_price decision needs E2 review |
| **P3 (deferred)**: trait-level Option 1 doc strengthening | P3 | Sprint N+2 backlog | PA | ~20 | Update `Strategy` trait doc comments per §4 Option 1 |
| **P3 (RFC)**: trait-level Option 2/3 invariant | P3 | Sprint N+3 RFC | PA | TBD | Pair with W-AUDIT-8a 6th-alpha-source migration timing |

**Logging recommendation (no ticket)**: Add `tracing::debug!` with target `"strategy_position_sync"` to all 5 strategies' on_rejection `duplicate_position` branch (bb_reversion + bb_breakout currently silently RC-04 rollback) so future hot-loop forensics has a single grep handle.

---

## §6 Confidence

| Audit point | Confidence | Caveat |
|---|---|---|
| (1) entry query coverage | HIGH | Direct grep `ctx.position_state` per strategy file confirmed presence/absence |
| (2) on_fill coverage | HIGH | Direct grep `on_fill` per strategy; trait default no-op verified at `strategies/mod.rs:116-118`; W7-5 commit `bb7cb293` file list confirmed all 5 strategies touched |
| (3) on_rejection 1-tick defense | HIGH | Direct grep `duplicate_position` against all strategy files; only ma_crossover hit (strategy_impl.rs:55-91 + tests.rs); bb_reversion/bb_breakout/funding_arb all use original RC-04 rollback only |
| (4) bootstrap import | HIGH | Direct grep `import_positions` per strategy; orchestrator iteration verified at `orchestrator.rs:60-64`; bootstrap callsite verified at `event_consumer/bootstrap.rs:772-774` (after register, before grant_paper_auth as specified in W7-5 design) |
| Risk severity (P1 vs P0) | MEDIUM | Risk severity is read-only static analysis; runtime impact depends on trigger frequency. ma_crossover INXUSDT 11:34 was 30-50 reject/sec; bb_reversion residual race is bounded to ~1 reject per cross-strategy fill collision (estimated <10/day per cohort given current 7-symbol cohort + 0 visible burst in W6 baseline). bb_breakout residual is theoretical (0 historical occurrence). E2 should re-verify with grep-by-source-tree before merge. |
| Verdict completeness | HIGH | All 5 strategies × 4 audit points = 20 cells fully covered; cross-references to W7 chain commits + earlier W7-4 audit + PA #3 root-cause audit consistent |

---

## §7 Cross-reference to predecessor reports

This audit refreshes `2026-05-10--w7_4_systemic_position_sync_audit.md` (pre-IMPL phase verdict) with **post-IMPL coverage matrix**:

| Strategy | Pre-IMPL verdict (earlier W7-4) | Post-IMPL verdict (this audit) | Delta |
|---|---|---|---|
| ma_crossover | HIGH (confirmed P1, Option A pending) | A — full W7 coverage | W7-2 + W7-5 land closed gap |
| bb_reversion | HIGH (potential, structural same as ma_crossover) | B — entry guarded, on_rejection 1-tick defense gap | W7-2 closed entry; W7-3 not propagated → P1-1 |
| bb_breakout | MEDIUM (potential, gate-throttled) | C — both Option A + Option B gaps | W7-2 not extended to bb_breakout → P1-2 + P2-1 |
| grid_trading | LOW (M-2 backoff) | A — by-design alternative architecture | unchanged |
| funding_arb | RETIRED-LOW (dormant + 1h cooldown) | A — by-design dormant | unchanged |

**Net change post-W7 deploy**: 1 strategy fully closed (ma_crossover), 1 partially closed (bb_reversion), 1 still open (bb_breakout), 2 N/A by-design.

---

## §8 Evidence files

- `srv/rust/openclaw_engine/src/strategies/mod.rs:73-227` (Strategy trait + W7-5 default no-op for on_fill/import_positions)
- `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs:55-91` (W7-3 Option B), `:131-175` (W7-5 on_fill+import), `:253-266` (W7-2 Option A)
- `srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs:345-366` (on_rejection no W7-3), `:379-414` (W7-5), `:500-512` (W7-2 Option A)
- `srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs:319-326` (on_external_close), `:335-373` (W7-5 only), `:394-429` (on_rejection no W7-3), `:567-569` (entry path no W7-2 query)
- `srv/rust/openclaw_engine/src/strategies/grid_trading/mod.rs:337-374` (W7-5 by-design), `signal.rs:137-141` (M-2 check), `position_mgmt.rs:162-194` (RC-04 + M-2 arm)
- `srv/rust/openclaw_engine/src/strategies/funding_arb.rs:340-445` (RC-04 + W7-5 defensive, dormant by ADR-0018)
- `srv/rust/openclaw_engine/src/orchestrator.rs:55-64` (import_positions_for_all)
- `srv/rust/openclaw_engine/src/event_consumer/bootstrap.rs:765-774` (bootstrap callsite)
- `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:285-292` (W7-1/W7-2 per-iteration borrow wire), `:973` (on_fill callsite)
- `srv/rust/openclaw_engine/src/tick_pipeline/mod.rs:729` (TickContext.position_state field)
- W7 chain commits: `c9fb0b8f` (W7-1) + `b42731f6` (W7-3 deployed) + `22efd9de` (W7-2 NOT DEPLOYED) + `bb7cb293` (W7-5 NOT DEPLOYED)
- Predecessor PA audits:
  - `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`
  - `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_4_systemic_position_sync_audit.md` (pre-IMPL phase)

---

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_4_5_strategy_position_sync_systemic_audit.md

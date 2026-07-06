# 2026-07-06 Maker-First / Microstructure Edge Feasibility — Verdict

PM sign-off: `SIGNED — NO-GO (maker-first as an engineering profit lever) at current fee tier`

Scope: PM ran a read-only, $0, offline feasibility investigation into whether a maker-first
(passive liquidity-provision) execution paradigm could fix the two operator-stated problems —
(1) the bot is not profitable, and (2) it is mechanically designed, below institutional AI/agent
trading. This report integrates a four-agent wave (QC/BB/MIT/PA) plus a two-window run of the
existing `fill_sim` microstructure tool over real recorded L1 order-book data. No runtime mutation,
no order, no secret, no exchange contact, no Cost Gate change, no DB write.

## Executive Verdict

Maker-first passive liquidity provision is a **NO-GO as an engineering profit lever for us at the
current Bybit VIP0 fee tier.** This is now triple-confirmed by independent lines of evidence:

- **BB (exchange economics):** VIP0 maker fee is **+2.0 bps/side (a fee, not a rebate)**. The regular
  VIP ladder never turns negative (best 0.0% at Supreme VIP, ~$500M/30d volume). A genuine maker
  rebate exists only via the institution-gated Market Maker Incentive Program (KYB business entity +
  BD application + winning Bybit-wide maker share) — an operator capital/legal lever, not engineering.
- **QC (market-making-native analysis):** on liquid perps the captured half-spread (~0.5–2.5 bps)
  barely exceeds the +2.0 bps maker fee, so the gross incentive is ≈0 before adverse selection even
  enters.
- **`fill_sim` (empirical, 2 windows, ~34M rows of recorded L1):** **0 of 172 evaluated cells are
  net-positive.** Even the single best symbol/queue cell loses ~3.2 bps/fill. No conditioning signal
  survives walk-forward holdout at our fee.

The structural reason is market-making-native, not a directional-alpha objection: on this venue and
symbol universe, **captured half-spread < adverse selection + maker fee**, and the maker fee is the
binding wall. Wider-spread symbols do **not** rescue it — adverse selection scales up with spread
(the tool's pre-registered "wide-spread tension"), so the extra spread is eaten by informed flow.

Important honesty note: my initial session thesis — that the hot path was a "hardcoded naive taker"
with a dormant execution layer — was **partially falsified at the code level by PA** and is corrected
below. The corrected picture makes the NO-GO stronger, not weaker.

## What The Initial Thesis Got Wrong (corrected)

- **FALSE:** "the live/demo hot path is hardcoded to `market` (taker)." The two `order_type: "market"`
  sites originally grepped (`orchestrator.rs`, `mode_state.rs`) are both inside `#[cfg(test)]`
  fixtures. The production path carries `order_type`/TIF faithfully end-to-end
  (`strategies/.../helpers.rs` → `event_consumer/dispatch.rs` → `order_manager.rs`).
- **TRUE (reframed):** maker/PostOnly entry is already live (`use_maker_entry=true` in demo+live
  TOMLs); demo close-maker is attempted but Demo-gated. The taker cost wall is real but lives on the
  **exit leg** and is a **microstructure reality**, not a code gap: passive close quotes mostly time
  out (~54% for grid) or get adversely selected, and fall back to taker.
- **TRUE (dormant, but a different capability class):** `order_router.rs` M12 `OrderRouter` trait is
  a 0-caller `unimplemented!()` stub — adaptive slippage-aware routing / reverse-snipe defense /
  rebate-tier monitoring. This is a **cost-reduction** capability, not an alpha source.

## Four-Agent Wave Inputs

- **QC (crypto-microstructure lead):** the `close_maker_first` machinery is already live; 408 real
  close-maker attempts measurable. Fill economics are strategy/regime-structured — grid
  (mean-reversion) 34.8% maker fill / 10.5% adverse-reject; `flash_dip_buy` (momentum) 0% fill /
  95.7% adverse-reject. Initial verdict `NEEDS-DATA`, leaning conditional-GO only on
  mean-reverting / wide-spread niches; decisive test = realized-markout harness.
- **BB (Bybit broker economics):** VIP0 maker +2.0 bps; ladder never negative to Supreme VIP; rebate
  only via institution-gated MM program. API constraints are NOT the blocker (linear order limit
  20/s, amend 10/s, no published cancel-ratio penalty, PostOnly ToS-compliant, our baseline ~0.7
  req/s). Verdict: NO-GO at current scale unless spread capture is net-positive while paying +2.0 bps.
- **MIT (data feasibility):** the microstructure recorder stack is LIVE, not a stub —
  `market.l1_events` 259M rows (resolved BBO, 18 regime-days, bad-tick 0.00%), `market.trades` 233M
  rows; `program_code/research/microstructure/fill_sim.py` already built. The maker study is
  offline-feasible today; the only quality ceiling is regime diversity (accumulates with time, needs
  no P0 unblock). `trading.fills` already carries `maker_markout_bps`/`liquidity_role`/`slippage_bps`
  (V145), context_id-keyed.
- **PA (execution-path reality + P0 prep):** corrected the taker thesis (above). P0 read-only prep is
  CLEAN: Rust `RiskConfig` is sole cap authority; the June live-RiskConfig 5-gate-bypass P1 is
  remediated at HEAD (token chokepoint + removed fail-open); no hidden 10-USDT authority path;
  outcome keying is context_id-based, not time-window. Residual: E3 should confirm
  `OPENCLAW_LIVE_PATCH_SECRET` is provisioned on Linux.

## `fill_sim` — The Decisive Evidence

Tool: `program_code/research/microstructure/fill_sim.py` — a purpose-built, anti-optimism
microstructure fill simulator. Why its verdict is trustworthy:

- **Back-of-queue conservative default** (`size_ahead := Q0`) — assumes we are last in queue, the
  real non-colocated retail posture. It also sweeps front/mid/back as a dose-response.
- **Point-in-time single forward pass** (t sees only events `ts<=t`) — structurally leak-free, no
  look-ahead.
- **Beta-residual adverse selection** at 5/15/30s (removes BTC-beta so it measures true adverse
  selection, not market drift).
- **Maker fee = 2.0 bps/side, no rebate** baked into `NET = half_spread − adverse_selection −
  2×maker_fee`, matching the BB/PA hard gate.
- **Walk-forward holdout + DSR/CP-3 pre-registered requirements** guard against in-window overfitting.

### Two windows, both decisive

| Metric | Fast 3h (2026-07-06 03:00–06:00Z, 32 sym, 1.84M L1) | Window A 72h (2026-07-03→07-06Z, 46 sym, 31.99M L1) |
|---|---|---|
| edge_scorecard status | `NO_POSITIVE_FILL_ONLY_CELL` (0/72) | `NO_POSITIVE_FILL_ONLY_CELL` (0/100) |
| best fill-only cell | ADAUSDT back: **−3.269 bps** (hs 2.674 / adv 1.943) | ADAUSDT: **−3.185 bps** (hs 2.78 / adv 1.965) |
| per-symbol positive @15 maker-exit | 0/32 | 0/46 |
| front-of-queue (most optimistic) net@15 fill-only | −4.117 | −3.984 |
| walk-forward holdout confirmed | 0 (of 51 candidates) | 0 |
| conditional-feature positive | 0 | 0 |
| low-friction signal | holdout-gross-positive **below fee** | train-only, below fee |
| break-even maker fee needed (bps/side) | ≤ ~1.08 (best gated cell) | ≤ **0.407** |
| our actual maker fee (bps/side) | 2.0 | 2.0 |

Cross-window stability (ADA −3.27 vs −3.19; front/back both ≈ −4) shows this is a **structural fee
wall, not regime noise.**

### Key mechanistic findings

- Even at **front-of-queue** (which we cannot achieve as non-colocated retail), pooled captured
  half-spread (0.74 bps) is **less than adverse selection (0.85 bps)** — negative before fees.
- **Wide-spread does not help:** ICP half-spread 2.29 / adverse 2.61; VANRY adverse 3.95. The widest
  spreads carry the worst adverse selection. QC's "wide-spread niche" hope is refuted on the existing
  established-perp universe.
- **Attack side fully null:** 51 walk-forward feature candidates, 0 survive holdout; best in-sample
  (LABUSDT −2.69) collapses to −9.06 out-of-sample (classic overfit). The only cells that flicker
  positive require maker fee ≤ ~0.4–1.1 bps/side — i.e. a lower fee tier / rebate (infrastructure).

## Answer To The Two Operator Problems

- **Not profitable:** the maker/execution axis is now **empirically closed** as an edge source at our
  tier. Combined with the prior finding that directional OHLCV alpha ≈ 0, the honest conclusion is
  that the bot is not unprofitable because it is "too mechanical" or "lacks AI" — it is unprofitable
  because it has **no directional alpha** and **execution edge is fee-gated behind an infrastructure
  tier we cannot trade our way into.** `fill_sim` shows even sophisticated conditioning does not flip
  it. Adding an LLM/agent to the decision or execution cannot manufacture edge the fee wall and alpha
  absence preclude.
- **Too mechanical / not institutional:** the genuinely missing institutional capability is the
  dormant M12 adaptive execution router (slippage-aware routing, reverse-snipe defense) plus
  regime-conditioning — but that is **cost reduction, not alpha.** The correct institutional posture
  keeps LLMs/agents out of the order path; the agentic value is in the research loop (this wave is an
  instance of it), not the trade decision.

## What Remains Genuinely Open (not concluded)

We did not commit the "declare the whole market edgeless from one corner" error. Still untested:

1. **Brand-new-listing first-hours spread capture (20–100 bps):** not in this established-perp
   universe; a different, narrower, more operationally fraught niche. Offline-screenable at $0.
2. **Full CP-3 multi-regime accumulation** (≥10–12 regime-days incl. trend-stress): both windows are
   recent/calm; the tool itself labels this "NOT go/no-go." However, the fee wall is regime-
   independent and trend-stress typically worsens passive-maker adverse selection, so an overturn is
   unlikely. This accumulates passively via the existing recorder + cron — no action needed.
3. **Infrastructure-tier change** (capital → VIP/MM tier → rebate): an operator capital/BD decision,
   not engineering. `fill_sim` quantifies the threshold precisely (break-even ≈ 0.4 bps/side maker).

## Operational Incident (reconstructability)

The QC agent that launched `fill_sim` was suspended by the desktop idle-pause, resumed on operator
return, and was then prematurely `TaskStop`-ed by PM under a mistaken death diagnosis. The two
`fill_sim` runs had been launched detached (reparented to init) and survived; PM recovered by reading
the durable JSON artifacts in the main session. No data was lost. Lesson recorded to memory: a
detached long job's liveness (remote PID + output artifact) is independent of the launching agent;
diagnose before `TaskStop`.

## Reproduce

```
# on trade-core, read-only, ~4min (3h) / ~30min (72h), $0
python3 -m program_code.research.microstructure.fill_sim \
  --since 2026-07-06T03:00:00+00:00 --until 2026-07-06T06:00:00+00:00 \
  --horizons 5,15,30 --out fillsim_fast3h.json
python3 -m program_code.research.microstructure.fill_sim \
  --since 2026-07-03T06:00:00+00:00 --until 2026-07-06T06:00:00+00:00 \
  --horizons 5,15,30 --out fillsim_winA_recent72h.json
```

Artifacts:
- trade-core: `/home/ncyu/qc_fillsim_run_20260706/fillsim_{fast3h,winA_recent72h}.json` (+ per-symbol CSV)
- repo (per-symbol evidence): `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--fillsim_{fast3h,winA72h}_per_symbol.csv`

## Non-Negotiable Boundaries Held

- Read-only, offline, $0 throughout. No order, no probe, no private read, no exchange contact.
- No secret access, no MCP install, no Cost Gate change, no DB write, no migration, no runtime mutation.
- No live/mainnet action. `fill_sim` and read-only `ssh trade-core` SELECT only.
- Maker-rebate is excluded from all net math (we are not an approved MM and cannot receive it).

## PM Sign-Off

PM signs this as a **NO-GO** for investing engineering in a maker-first pivot as a profit lever at the
current fee tier. This is an evidence-based kill, evaluated in market-making-native math (queue,
adverse selection, no-rebate, back-of-queue, leak-free), not the prior directional-taker corner.

Recommended next fork (operator decision, no work dispatched yet):
1. Screen the brand-new-listing wide-spread niche offline ($0), OR
2. Treat maker economics as an operator infrastructure/capital decision (VIP/MM tier), OR
3. Scope the M12 adaptive router as a bounded execution cost-reduction (not alpha) engineering item.

This is not authorization to trade, change gates, contact exchanges, touch secrets, or dispatch
implementation work.

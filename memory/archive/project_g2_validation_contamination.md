---
name: G-2 FundingArb paper validation — data contamination window
description: Paper TOML funding_threshold temporarily lowered 0.0005→0.0001 from 2026-04-14; edge_estimates_paper.json records during this window are NOT valid signal
type: project
originSessionId: 258747c1-ad4c-4e68-89b4-57dab2c6a8e0
---
**Fact**: `settings/strategy_params_paper.toml` `[funding_arb]` two params temporarily lowered on **2026-04-14 ~15:12 local** (follow-up edit ~17:35 after edge-gate diagnosis): `funding_threshold` 0.0005→0.0001 AND `total_cost_bps` 34.0→1.0. Demo/live TOMLs unchanged. Reason the second edit was needed: `amortized_fee = total_cost_bps / 10000 / expected_periods` — at 34/10000/3 ≈ 11.33 bps, edge gate `|rate| > amortized_fee` rejects even rates that pass the funding_threshold.

**Why**: Default 0.0005 threshold vs calm market funding rates (BTC/ETH max |rate| 0.01%) would produce zero fills in a reasonable observation window. Temporarily lowering threshold 5× forces enough entry attempts to verify OC-5 code path end-to-end (entry gating / direction mapping / exit reason / close_tag / PnL calc). This is **not** a production parameter decision.

**How to apply**:
- Any fills with `strategy_name='funding_arb'` and `engine_mode='paper'` dated 2026-04-14 15:12+ until threshold is reverted are **contaminated** — do not treat as signal quality evidence.
- `edge_estimates_paper.json` during this window contains low-quality funding_arb entries; exclude from edge tuning decisions.
- Revert condition: ≥20 funding_arb paper fills accumulated + analysis done → revert to 0.0005 and purge/flag contaminated window fills.
- If future session finds funding_arb with unexpectedly negative edge in paper, check whether the threshold revert happened before drawing conclusions.

**Where tracked**: TODO.md G-2 section has full detail and revert plan. CLAUDE.md §三 one-liner notes the window.

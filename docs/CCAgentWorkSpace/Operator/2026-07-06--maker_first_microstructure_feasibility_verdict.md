# 2026-07-06 Maker-First / Microstructure Feasibility — Verdict (Operator Summary)

Canonical PM report:
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--maker_first_microstructure_feasibility_verdict.md`

Evidence artifacts (per-symbol):
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--fillsim_fast3h_per_symbol.csv`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--fillsim_winA72h_per_symbol.csv`

Question: can a maker-first (passive liquidity-provision) paradigm fix the two problems — not
profitable, and too mechanical / below institutional AI trading?

Verdict: **NO-GO** for maker-first as an engineering profit lever at our current Bybit VIP0 fee tier.
Triple-confirmed:
- BB: VIP0 maker is a +2.0 bps fee, not a rebate; a rebate needs the institution-gated Market Maker
  program (capital/entity/BD lever, not engineering).
- QC: on liquid perps captured half-spread ≈ the +2.0 bps fee, so gross incentive ≈ 0 before adverse
  selection.
- `fill_sim` over ~34M rows of real recorded L1, two windows: **0 of 172 cells net-positive**; best
  cell −3.2 bps/fill; 0 signals survive walk-forward holdout; break-even needs maker fee ≤ ~0.4
  bps/side (i.e. a lower tier / rebate we cannot reach by trading).

Honest correction: the initial "hardcoded naive taker" thesis was falsified — maker/PostOnly is
already live; the taker cost wall is on the exit leg and is a microstructure reality (passive exits
don't reliably fill), not a code gap. The genuinely dormant piece is the M12 adaptive router — a
cost-reduction capability, not alpha.

What this means: the bot is not unprofitable because it "lacks AI" — it lacks directional alpha and
its execution edge is fee-gated behind an infrastructure tier. Adding an LLM/agent to the order path
cannot manufacture that edge.

Still open (not concluded): brand-new-listing wide-spread capture (offline-screenable, $0);
full multi-regime CP-3 accumulation (passive, unlikely to overturn the fee wall); infrastructure-tier
change (operator capital/BD decision).

Posture: read-only, offline, $0. No order, secret, MCP, Cost Gate, DB write, or exchange contact.
No implementation work dispatched — awaiting operator fork choice (niche screen / infra decision /
M12 cost-reduction).

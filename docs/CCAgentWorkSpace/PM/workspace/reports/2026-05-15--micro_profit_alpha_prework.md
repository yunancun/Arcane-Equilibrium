# P0-MICRO-PROFIT Alpha Prework

Date: 2026-05-15
Scope: PM execution of operator request: do items 1-3 from the prior recommendation, update TODO, and prepare three-side sync. No runtime mutation, no DB write, no auth change, no production WS topic change, no paper/demo launch.

## Verdict

Direct micro-profit amplification remains BLOCKED.

The correct current work is alpha prework:

1. W-AUDIT-8a C1 standalone liquidation-topic proof packet.
2. W-AUDIT-8b Funding Skew Directional spec.
3. A4-C revise/archive decision.

## 1. C1 Liquidation Topic Proof Packet

Added:

- `docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md`
- `helper_scripts/bybit/liquidation_topic_probe.py`

Important correction: the current official Bybit topic is `allLiquidation.{symbol}`, for example `allLiquidation.BTCUSDT`, not bare `allLiquidation`.

C1 remains blocked until a 24h isolated public WS proof passes. Short probe runs are only smoke evidence.

2026-05-15 addendum: the 60s smoke passed as `SMOKE_PASS_NOT_C1_PROOF`, and
the 24h isolated `allLiquidation.BTCUSDT` proof is running on `trade-core` as
PID `4100789` since `2026-05-15T19:53:09Z`.

## 2. W-AUDIT-8b Funding Skew Spec

Added:

- `docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`

Boundary:

- This is not retired `funding_arb`.
- It uses funding as a cross-sectional crowding signal.
- Positive funding payment cannot count as edge until funding settlement attribution is first-class and MIT signs the ledger join.
- QC/MIT/BB review has since conditionally approved Stage 0R replay design only. Next step is a read-only replay query/report packet, not strategy implementation.

## 3. A4-C Revise-Or-Archive

Added:

- `docs/execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md`

Decision: archive A4-C from the active promotion path. The earlier bounded
exception has now been exercised: `P1-A4C-RCA-1` is closed no-revive after
QC/MIT review, so `P1-A4C-REV-1` is not opened and no same-feature Stage 0R
rerun is authorized.

Basis: Step 5b failed the spec archive rule. R²(60/120/300)=`0.0009/0.0005/0.0027`; N=60 remains far below the `0.04` minimum. Further threshold loosening would be selection pressure, not alpha repair.

A4-C producer/panel remains useful diagnostic infrastructure and can feed future Hypothesis Pipeline exploration.

## State Updates

Updated:

- `TODO.md`
- `CLAUDE.md`
- `active-plan.md`
- `.codex/MEMORY.md`
- `.codex/WORKLOG.md`
- `docs/README.md`
- `helper_scripts/SCRIPT_INDEX.md`
- `docs/CLAUDE_CHANGELOG.md`
- `docs/references/2026-04-04--bybit_api_reference.md`
- A4-C and 8a specs with C1/A4-C pointers

## Hard Boundary Check

- No production subscription list change.
- No `OPENCLAW_ENABLE_PAPER=1`.
- No Stage 1 demo launch.
- No risk sizing/leverage edit.
- No live auth renewal.
- No DB migration or write.
- No runtime restart/rebuild.

PM SIGN-OFF: CONDITIONAL

Condition: C1 remains blocked until the running 24h isolated proof passes and
BB/MIT sign off; 8b remains design-only until a read-only Stage 0R replay
query/report packet is implemented and reviewed.

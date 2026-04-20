---
name: G-2 / Edge analysis prefers demo data over paper
description: For edge accumulation and strategy validation, use demo engine fills not paper. Operator feels paper data is too distorted to be reference-quality.
type: feedback
originSessionId: 258747c1-ad4c-4e68-89b4-57dab2c6a8e0
---
For edge accumulation, strategy validation, and any analysis that informs production decisions (Phase 5 promotion, JS edge estimates, G-2 FundingArb validation, etc.), prefer **demo engine fills over paper engine fills**.

**Why:** Operator stated (2026-04-15) "paper 的數據實際上很失真，沒有太多參考價值" — paper data is too distorted to be useful as reference. This is consistent with the existing edge-data-isolation work (memory `project_edge_data_isolation.md`), where paper exploration mode allows large negative-edge fills that contaminate JS edge estimates. Paper's permissive cost gate + exploration semantics mean its fills don't represent realistic trading conditions.

**How to apply:**
- When asked to validate strategy edge / accumulate clean fills / count toward "≥N samples" gates → query `engine_mode = 'demo'`
- When showing edge breakdowns or PnL summaries for decision-making → split by engine_mode and lead with demo numbers
- Paper data still has uses: regression testing, signal-firing presence checks, smoke tests of code paths — but **not** edge magnitude or strategy quality assessments
- The G-2 FundingArb ≥20-clean-fills gate should count demo fills, not paper. Pace will be slower; that's accepted.
- If only paper data is available for some analysis, explicitly flag it as "paper-only — likely distorted" rather than presenting as authoritative

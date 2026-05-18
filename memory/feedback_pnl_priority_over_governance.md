---
name: PnL Improvement + Real IMPL Priority Over Governance Writing
description: Governance docs important but operator prefers seeing substantive dev recommendations + PnL improvement over governance paper trail
type: feedback
originSessionId: f72e23f5-4eba-4338-890a-26dfa94d90d7
---
Governance documentation (AMD wording, spec tombstone, consolidated verdict, TODO sync) 重要但**不是最高優先**。Operator wants to see substantive dev IMPL recommendations + actual PnL improvement signals over governance polish.

**Why:** Trading losses cure requires alpha-bearing strategy land (W-AUDIT-8c Liquidation Cluster / W-AUDIT-8a Phase B/C/D alpha source infrastructure)，not paper trail completeness. Past sessions have been governance-heavy (Round 2 RED tombstone → AMD v0.7 → spec v0.4 → consolidated 4-agent verdict → AMD v0.3 patch chain) without proportional alpha-bearing IMPL progress. 5 textbook strategies still -110 USDT/30d demo / -27 USDT/30d live_demo. Phase 1b is execution-quality optimization (~5-15% of loss), not the cure.

**How to apply:**
- **Recommend / dispatch priority order**:
  1. Alpha-bearing strategy IMPL (W-AUDIT-8c Liquidation Cluster, W-AUDIT-8a Phase B/C/D)
  2. Infrastructure that unblocks alpha (C1-LIQ-WRITER, B-REM-5 schema, W-AUDIT-8a Wave 1-3)
  3. Verification + healthcheck that proves PnL impact (Phase 1b T+24h verify, AC-A SQL, healthcheck [62-65])
  4. Governance docs (AMD wording, spec tombstone, ADR) — necessary but ranked after IMPL
- **Recommendation framing**: 每次 propose action 必含「does this move PnL?」judgment。If governance polish only, label as such + propose alternative IMPL action.
- **4-agent review threshold**: reserve heavy 4-agent parallel review for architectural decisions (e.g., new AMD, new strategy promotion gate). Cosmetic wording fixes use single-PA patch + light review.
- **Status reports**: lead with PnL-impacting metrics (alpha_attempt_pct, realized_net_bps, fills生產率) over commit hashes / governance paper count. Commit count is means, PnL is end.
- **End-of-batch closure**: after governance batch lands (like AMD v0.7 + spec tombstone), immediately reorient to alpha-bearing IMPL queue — don't accumulate more governance.

**Lesson from 2026-05-18 phys_lock 4-agent review**: MIT found 25d realized_net_bps avg = -1.97 bps challenging AMD's profit-protection claim — empirical PnL truth (negative) > governance framing (positive). Prior 5 agents missed this because none ran independent PG empirical query. Future reviews on alpha/PnL claims must include empirical SoT verification, not just spec compliance check.

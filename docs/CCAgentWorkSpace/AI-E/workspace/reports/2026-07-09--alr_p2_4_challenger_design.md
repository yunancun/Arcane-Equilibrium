# AI-E Design - ALR P2-4 Challenger Artifact

Date: 2026-07-09
Verdict: `CHALLENGER_RESEARCH_ONLY`
Mode: `ROLE_FALLBACK_SINGLE_SESSION`

P2-4 reuses `alr_stat_selector_baseline` as the existing deterministic
statistical pipeline. Its selected target determines only which scanner pattern
has the most information value for future evidence collection. The resulting
artifact links target -> PIT dataset -> statistical experiment -> challenger
candidate -> after-cost defer reason.

The artifact has no model binary, no serving binding, no promotion path, no
`_latest` action, and all exchange/trading/proof/serving/promotion counters are
false. It becomes eligible for P2-5 outcome feedback only when independently
verified ProofPacket/RewardLedger evidence exists.

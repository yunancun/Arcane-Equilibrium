# FA Effect Review - WP1 Gate Incident

Date: 2026-07-10
Verdict: `SOURCE_CHECKPOINT_ALLOWED_WITH_REMEDIATION`

- `FINANCIAL_EFFECT=NONE_OBSERVED`
- `TRADING_AUTHORITY_EFFECT=NONE`
- `PRODUCTION_LINUX_EXCHANGE_EFFECT=NONE_OBSERVED`
- `SAFETY_GOVERNANCE_EFFECT=MATERIAL_GATE_SEQUENCE_NONCONFORMANCE`
- `QA_LOCAL_PG_EVIDENCE=RETRACTED_UNCONSUMABLE`
- `QA_SOURCE_STATIC_UNIT_VERDICT=SEPARABLE_AND_VALID`

No financial or trading impact is evidenced, but the disposable/local label
does not waive the PostgreSQL gate. Source checkpointing is permitted only
with this durable RCA and no runtime claim. The next gate must bind the exact
post-documentation SHA, target host, ALR-only service, commands, database
read/write scope, no-migration condition, rollback, 300-second-or-longer soak,
and post-action residue/effect checks. Any scope or SHA change invalidates it.

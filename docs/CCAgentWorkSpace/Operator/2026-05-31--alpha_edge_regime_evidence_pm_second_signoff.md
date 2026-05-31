# PM Report — Alpha-Edge Regime Evidence Second Sign-off

Date: 2026-05-31
Role: PM(default)
Scope: second sign-off after PA engineering arrangement.
Mode: planning and governance only. No runtime deploy, DB write, auth change, or trading action.

## Verdict

PM SECOND SIGN-OFF: **APPROVED FOR AEG-S0 CONTRACT SPRINT ONLY**.

This approval does not authorize E1 backfill, DB retention mutation, Bybit client implementation, listing collector implementation, or alpha scoring.

## Signed Engineering Arrangement

SSOT: `docs/execution_plan/2026-05-31--alpha_edge_regime_evidence_engineering_arrangement.md`

Immediate executable work is AEG-S0:

1. `AEG-S0-W0-S1 Evidence Storage Contract`
2. `AEG-S0-W0-S2 Regime Classifier Freeze`
3. `AEG-S0-W0-S3 Bybit Endpoint Contract`
4. `AEG-S0-W0-S4 TODO Archive Plan`

These four sessions may run in parallel. Maximum parallelism: 4, below the project ceiling of 7.

## Hard Gate

E1 remains blocked from implementation until AEG-S0 passes and PM signs the next gate.

Specifically blocked:

- Bybit historical backfill writer.
- `market.klines` retention/runtime PG mutation.
- funding/OI/long-short 18mo backfill.
- mark/index/premium kline client implementation.
- collector listing-capture IMPL.
- alpha scoring / promotion report.

## Rationale

QC, MIT, and PA converged on the same point: direct backfill would create data without a reliable evidence contract. The system first needs provenance, regime labels, breadth automation, endpoint semantics, and side-evidence boundaries.

## Next PM Dispatch

Dispatch AEG-S0 as a 4-session contract sprint. After completion, PM must review the four outputs before opening AEG-S1 Foundation Sprint.

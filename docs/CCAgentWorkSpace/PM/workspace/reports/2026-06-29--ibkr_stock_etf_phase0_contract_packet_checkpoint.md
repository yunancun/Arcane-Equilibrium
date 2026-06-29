# PM Checkpoint - IBKR Stock/ETF Phase 0 Contract Packet

日期：2026-06-29
角色：PM(default)
範圍：IBKR `stock_etf_cash` paper/shadow Phase 0 governance materialization.

## Verdict

**STATUS: DONE_WITH_CONCERNS**

Phase 0 ADR/AMD/named contract packet 已落地，可作後續 Phase 1 source foundation 的治理與契約基線。

這不是 IBKR launch approval，也不是 connector implementation approval。

## Completed Artifacts

- `docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md`
- `docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md`
- `docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md`
- `docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json`

Updated stable routing and boundary docs:

- `CLAUDE.md`
- `.codex/MEMORY.md`
- `README.md`
- `docs/agents/context-loading.md`
- `docs/_indexes/document_index.md`
- `docs/_indexes/initiative_index.md`
- `docs/governance_dev/SPECIFICATION_REGISTER.md`

## Boundary

Allowed next work:

- Phase 1 closed type/config/schema/IPC source foundation.
- Default-OFF flag/readiness parsing.
- Source-only DDL implementation from `stock_etf_db_evidence_ddl_v1`.
- Lane-scoped IPC/order-lifecycle fixtures.
- Denial-first tests and Bybit regression checks.

Still blocked:

- IBKR API call.
- IBKR connector.
- IBKR process startup.
- Secret-slot creation.
- Paper order rehearsal.
- DB migration apply.
- GUI runtime stock activation.
- Evidence clock start.
- IBKR tiny-live/live, margin, short, options, CFD, transfer, account-management writes.

## Concern

`TODO.md` already had concurrent v675 learning proof/promotion WIP when this checkpoint was written. PM therefore did not edit TODO in this batch to avoid mixing unrelated work. The IBKR routing state is captured in ADR/AMD/spec/index/report artifacts; a later clean TODO checkpoint should add the Phase 1 row if it is not already present.

## Next Action

Start `P0-IBKR-STOCK-ETF-PHASE1-SOURCE-FOUNDATION` with chain:

`PM -> PA -> E1 -> E2 -> E4 -> QA -> PM`

If sub-agent dispatch is unavailable, keep work local only for planning/docs; do not claim E2/E4/QA sign-off without those roles or equivalent review artifacts.

## Verification

Planned verification for this checkpoint:

- manifest JSON parse
- markdown path/link sanity
- `git diff --check`
- no IBKR runtime/API/secret paths touched
- no Bybit execution-path source change

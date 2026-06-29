STATUS: DONE
CERTIFICATION: CERTIFIABLE_IF_GATES_PASS, SCOPE=paper_shadow_only, FINDINGS=0(C:0/H:0/M:0/L:0)

# MIT Round 3 Launch-Certification Closure Audit

日期：2026-06-29
角色：MIT(default)
範圍：`stock_etf_cash` data/schema/evidence reproducibility launch certification only。
邊界：report-only；未改 code/runtime/TODO；未觸碰 Linux `trade-core`、PG、services、secrets、IBKR、Bybit 或 network。

## Decision

在 operator 指定的假設下，MIT 可以認證 data/evidence side 對 `stock_etf_cash` paper/shadow launch 完整：

- hardened DDL gate 全部 PASS。
- immutable event-source / audit-source gate 全部 PASS。
- market-data / instrument / corporate-action / cash-FX-cost / benchmark provenance gate 全部 PASS。
- storage / retention / compression / raw-hash retention gate 全部 PASS。
- deterministic evidence-clock / DQ / quarantine gate 全部 PASS。
- release packet gate 全部 PASS，且能從 manifest hash 反查 atomic evidence 並重算 scorecard。

若以上 gate **exactly as written** 全部通過，MIT 不再要求額外的 data gate 才允許 paper/shadow data collection go online。這只認證可重建資料與證據收集，不認證 broker/runtime security、IBKR live/tiny-live、盈利能力或 durable alpha。

## Data Launch Checklist

MIT certification requires the release packet to contain passing, immutable artifacts for:

1. Accepted ADR/AMD: only `stock_etf_cash` read-only / broker-paper rehearsal / synthetic shadow research; live/tiny-live/margin/short/options/CFD/transfer excluded.
2. `stock_etf_db_evidence_ddl_v1`: DDL/ERD with columns, types, NOT NULL, CHECK, PK/FK, natural keys, indexes, hypertable/chunk/compression/retention decisions, write owners, derived-vs-atomic labels, Guard A/B/C, Linux PG dry-run and double-apply evidence.
3. `audit.asset_lane_events_v1`: immutable event records or hash-chain/artifact refs with sequence or previous hash, payload hash, producer commit, schema version, actor/source, asset lane, broker, environment, and input artifact hashes.
4. Instrument and PIT universe contract: IBKR `conid`, `secType`, currency, primary exchange/MIC, validity windows, aliases display-only, universe rule hash, data cutoff, membership validity, inclusion/exclusion reasons.
5. Market-data and corporate-action provenance: vendor, tier, subscription/source, `exchange_ts`, `received_ts`, `request_ts/run_id`, raw payload hash, raw/adjusted policy, replayable adjustment set.
6. Cash/FX/cost/tax/benchmark versions: component-level source URL/as-of/effective windows, unknown costs fail-closed or conservative, cash ledger and FX conversion lineage, benchmark total-return/price-return/currency/calendar/matched-control mapping.
7. Paper/shadow reconciliation: stable signal/order/fill/commission/scorecard IDs, broker-paper vs synthetic-shadow separation, divergence taxonomy, threshold version, quarantine action.
8. `stock_etf_storage_capacity_v1`: universe size, row-volume estimate, retention, compression, index budget, query SLO, raw payload hash retention, archived evidence policy.
9. `stock_etf_evidence_clock_v1`: deterministic PASS/FAIL/QUARANTINED checker for trading calendar, timezone, holiday/early close, expected symbols, coverage, completeness, latency, DQ failures, pause/reset/quarantine state, and all input hashes.
10. Scorecard reproducibility: scorecard is derived-only; regeneration from atomic facts, code commit, schema version, universe/cost/benchmark/fill-model hashes, and DQ manifest passes.
11. Statistical/evidence preregistration: hypothesis id, K count, primary metric, independent sample rule, cluster/block unit, purge/embargo where applicable, PSR/DSR or equivalent deflation, ADR-0047 regime/breadth/freshness/survivorship/execution-realism labels.
12. `stock_etf_release_packet_v1`: role reports, E2/E4/QA logs, manifest hashes, PG logs, redaction fixture outputs, GUI evidence screenshots if applicable, DQ manifests, scorecard regeneration outputs, and disable/cleanup runbook paths.

## Explicit Exclusions

This certification excludes:

- IBKR live or tiny-live.
- Margin, short, options, CFD, transfer, withdrawal, account-management writes.
- Any promise that IBKR paper fills represent live execution quality.
- Any profitability guarantee, durable-alpha proof, or automatic tiny-live eligibility.
- Any relaxation of existing Bybit live gates, Rust authority, Decision Lease, Guardian, or root-principle controls.
- Any reuse of legacy Paper promotion semantics.
- Any current permission to create secrets, call IBKR, run PG migrations, start collectors, enable GUI runtime surfaces, or submit paper orders unless the non-MIT gates also pass.

## Missing Data Gates

None under the stated hypothetical.

If PM asks about current non-hypothetical status, the data/evidence side remains uncertified until the actual gate artifacts exist and pass. But there is no additional MIT-only data gate missing beyond the hardened DDL/event-source/provenance/storage/evidence-clock/release-packet set.

## PM Wording

PM may use this exact wording:

> MIT certifies the `stock_etf_cash` data/evidence side as complete for paper/shadow launch if and only if the accepted hardened DDL, immutable event-source, provenance, storage/capacity, evidence-clock, scorecard-regeneration, and release-packet gates all pass exactly as written. This certification is limited to reproducible paper/shadow data and evidence collection. It does not certify IBKR live or tiny-live, margin, short, options, CFD, transfer, profitability, durable alpha, or broker/runtime security gates.

## Basis Reviewed

- `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, `TODO.md`
- `docs/agents/context-loading.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/agents/PM.md`, `.codex/agents/MIT.md`, `.claude/agents/MIT.md`
- `docs/adr/0010-timescale-hypertable-with-guard-migrations.md`
- `docs/adr/0011-v-migration-linux-pg-dry-run-mandatory.md`
- `docs/adr/0047-alpha-edge-regime-evidence-governance.md`
- `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round2_pm_integration.md`
- Round-2 CC/FA/PA/E3/E5/QC/MIT/QA reports under `docs/CCAgentWorkSpace/*/workspace/reports/`

## Final PM-Facing Decision

PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS

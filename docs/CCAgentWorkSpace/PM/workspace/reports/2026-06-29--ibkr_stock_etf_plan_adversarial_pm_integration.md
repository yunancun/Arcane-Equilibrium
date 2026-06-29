# PM 整合報告 — IBKR Stock/ETF Paper + Shadow 方案對抗性檢查

日期：2026-06-29
角色：PM(default)
範圍：整合 CC / FA / PA / E3 / QC / MIT 對 `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md` 的對抗性審查。
結論：方案方向有效，但只批准 Phase 0 ADR/spec；Phase 1+ implementation 與 6-8 週 evidence clock 均 blocked。

## Verdict

**PM SIGN-OFF: CONDITIONAL**

批准：

- Phase 0 governance / ADR / spec review。
- 進一步定義 `stock_etf_cash` paper/shadow research lane。
- 繼續評估 IBKR 作第一 broker baseline。

不批准：

- Phase 1+ 實作。
- IBKR API 呼叫或 runtime healthcheck。
- IBKR secret slot 建立。
- IBKR paper order submit/cancel/replace rehearsal。
- GUI lane selector runtime rollout。
- `TODO.md` active implementation row。
- 6-8 週 evidence clock 起算。
- 任何 IBKR live / tiny-live / margin / short / options / CFD / transfer。

## Role Results

| Role | Verdict | Severity summary | Report |
|---|---|---|---|
| CC | DONE_WITH_CONCERNS | Critical 0 / High 1 / Medium 4 / Low 2 | `docs/CCAgentWorkSpace/CC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_cc_review.md` |
| FA | DONE_WITH_CONCERNS | Critical 3 / High 7 / Medium 3 / Low 1 | `docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_fa_review.md` |
| PA | DONE_WITH_CONCERNS | Critical 1 / High 6 / Medium 8 / Low 2 | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_pa_review.md` |
| E3 | DONE_WITH_CONCERNS | Critical 0 / High 1 / Medium 6 / Low 4 | `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md` |
| QC | DONE_WITH_CONCERNS | Critical 0 / High 6 / Medium 5 / Low 1 | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_qc_review.md` |
| MIT | DONE_WITH_CONCERNS | Blocker 8 / High 6 / Medium 3 / Low 2 | `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md` |

Severity labels are role-local; PM uses deduplicated blockers below rather than summing counts mechanically.

## Deduplicated Findings

### B1 — Governance unlock is mandatory before any implementation

Current repo authority remains Bybit-only execution. `stock_etf_cash` can be discussed only as a paper/shadow research lane until a new ADR/AMD explicitly amends ADR-0006 for this narrow scope. Chat-only approval is not enough for Phase 1.

Required action: Phase 0 ADR/AMD must name allowed and forbidden scopes: read-only, shadow, broker-paper research, live reserved, no margin/short/options/CFD/transfer.

### B2 — IBKR API/session baseline is unspecified

The plan cannot proceed to connector work until it chooses TWS API, IB Gateway, or Client Portal Web API as the first baseline. Runtime ownership, host/port, session lifecycle, account selection, market data tier, rate limits, and maintenance behavior differ materially.

Required action: make API/session choice a Phase 0 deliverable; if unresolved, add a no-order spike before connector implementation.

### B3 — IBKR paper is order-capable, not harmless read-only research

Paper submit/cancel/replace creates broker-side order state. It is not live capital risk, but it is still effect-capable and must be Rust-owned, auditable, and separately authorized.

Required action: classify operations into read-only, shadow-only, fill import, paper order rehearsal, and forbidden live; require signed scoped envelope for paper order rehearsal.

### B4 — Rust lane-scoped IPC/order Interface is missing

Existing Bybit/Paper `submit_paper_order` cannot be reused for equities. It lacks asset lane, broker, environment, instrument identity, currency, listing venue, cost model, and paper/shadow provenance.

Required action: define new lane-scoped Rust command/IPC and `ibkr_paper_order_lifecycle_v1` before E1 implementation.

### B5 — Python connector boundary must be structurally no-write

A Python `paper_client.py` can easily become a direct broker writer. That would violate Rust authority even if the decision was made upstream.

Required action: Python IBKR connector may do health/snapshots/fill import/fixtures only. Add static/grep guards against direct broker `place_order`, `cancel_order`, `replace_order` methods or routes outside Rust-owned authority.

### B6 — DB evidence contract is not yet a schema

The plan lists table names but not keys, constraints, lineage, migration guards, hypertable decisions, or source-of-truth rules. Daily scorecard rows cannot be primary evidence.

Required action: produce DDL-level contract before Phase 1 schema work, including instrument identity, PIT universe, corporate actions, market data provenance, FX/cash ledger, cost model, benchmark, paper/shadow reconciliation, and audit event hashes.

### B7 — Feature flags and secrets need machine-checkable invariants

Flags are listed but not ordered by authority or precedence. Secrets are path-level only. `IBKR live` must not become a dormant toggle.

Required action: remove functional live enable flag, require live slot absence/empty proof, exact secret filenames/modes/fingerprints/rotation, no env fallback, broker paper attestation before any order-capable call, and full flag matrix tests.

### B8 — GUI lane selector can only be display/filter state

The GUI can help the operator navigate lanes, but cannot select trading authority, risk config, broker environment, or order route.

Required action: server/Rust must revalidate signed lane/broker/environment/risk/auth context for every effect-capable operation. localStorage/query params/hidden fields are untrusted.

### B9 — 6-8 week evidence clock is under-specified

Current plan can prove operational collection, not profitability feasibility. QC and MIT both reject starting the evidence clock without pre-registered universe, benchmark, sample-size, cost-wall, paper/shadow divergence, and statistical gates.

Required action: define `stock_etf_evidence_clock_v1` with hashes for universe, benchmark, cost model, hypothesis, collector version, data-quality report, and start/pause/reset rules.

### B10 — Profitability criteria need statistical and benchmark rigor

Positive point estimates over 6-8 weeks are not durable alpha evidence. Bootstrap cannot create independent observations for low-frequency strategies.

Required action: pre-register exact universe cohorts, 2-3 hypotheses, matched benchmarks, independent observation counting, confidence intervals, PSR/DSR or equivalent deflation, concentration caps, and verdict labels.

## Plan Patch Applied

PM updated `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md` after review:

- Added adversarial-review conclusion to §0.
- Replaced `BrokerVenue::{IbkrPaper, IbkrLiveReserved}` with separated `Broker` + `BrokerEnvironment`.
- Added lane-scoped IPC and paper lifecycle requirements.
- Added Python no-write constraints.
- Added DB evidence contract expectations.
- Removed functional `OPENCLAW_IBKR_LIVE_ENABLED` toggle.
- Added secret/API/session/feature-flag requirements.
- Made GUI selector display/filter-only.
- Tightened universe, strategy, scorecard, evidence clock, and verdict labels.
- Split Phase 1 into smaller no-connector slices.
- Added §11 hard blockers.

## PM Decision

The engineering方案 is **valid as a Phase 0 exploration plan** and **invalid as an implementation-ready plan**.

Next allowed dispatch:

- `PM -> CC -> FA -> PA -> E3 -> QC -> MIT -> PM`
- Scope: draft the Phase 0 ADR/spec packet only.
- No IBKR API, no secret slot, no runtime change, no GUI runtime enablement, no DB migration apply.

Next blocked dispatch:

- Any E1 implementation.
- Any runtime connector spike touching IBKR.
- Any evidence clock run.

## Verification

- Sub-agent work was report-only.
- No Linux `trade-core`, IBKR API, Bybit API, PG write, runtime restart, or live path was touched by PM integration.
- `git diff --check` must pass before commit.

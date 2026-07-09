# Alpha-Edge Regime Evidence Engineering Arrangement

Date: 2026-05-31
Status: **PM 2 APPROVED / AEG-S0 FORMAL PASS / AEG-S1 FOUNDATION LIMITED-OPEN**
Owner: PM -> PA/QC/MIT/BB -> E1 only after AEG-S0 contracts pass
Scope: Alpha-history provenance, breadth automation, local trend/state classification, global regime robustness, side-evidence boundary.

## 0. Operating Decision

S4 is no longer a standalone 2024 bull-data proof track. It is a global S1-Sx regime/falsification overlay.

Bull data is allowed, but must be labeled. Bybit market APIs are raw state inputs, not prediction. Trend/state labels are generated locally from leak-free, point-in-time features. News / X / Reddit / market-summary agents are secondary side evidence only.

AEG-S0 contracts passed after PA/MIT/QC/BB/TW/CC re-review. Contract work lives
in `docs/execution_plan/2026-05-31--aeg_s0_contracts.md`; PM closure is
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--aeg_s0_formal_review_closure.md`.
S1 is limited-open only for Foundation scope. Direct E1 backfill, DB mutation,
runtime deploy, collector IMPL, and alpha scoring remain blocked until their
own scoped gates open.

## 1. AEG-S0 Contract Sprint（NOW）

Purpose: freeze the contracts before implementation. No code, migration, DB, runtime, or backfill work.

Current draft: `docs/execution_plan/2026-05-31--aeg_s0_contracts.md`.
Formal pass completed after owner-chain re-review. This section remains as the
contract record.

| Session | Owner chain | Output | Acceptance |
|---|---|---|---|
| `AEG-S0-W0-S1 Evidence Storage Contract` | PM -> PA+MIT -> QC | `alpha_history_run_manifest`, coverage/provenance, regime/breadth/side-evidence artifact contract | Includes `run_id`, `git_sha`, `session_id`, window, symbols, universe source, endpoint list, cost model, feature rules, classifier version. Explicitly states `panel.*` 14d surfaces are not 18mo history. Excludes `market_tickers.index_price/mark_price` for historical basis until persistence is fixed. |
| `AEG-S0-W0-S2 Regime Classifier Freeze` | PM -> QC+PA -> MIT | Bull/range/bear/chop/high-vol taxonomy + overlay flags | Rules fixed before alpha scoring; all features lagged / `shift(1)`; closed bars only; supports `bull-heavy`, `2024-dominated`, `stale-sensitive`, and `low-breadth` flags. |
| `AEG-S0-W0-S3 Bybit Endpoint Contract` | PM -> MIT+BB -> PA | Endpoint adoption plan | Covers kline, funding, OI, long-short, mark/index/premium kline, ticker, orderbook, option IV where relevant. Defines pagination, rate limits, retention, client gaps, and BB review. |
| `AEG-S0-W0-S4 TODO Archive Plan` | PM -> TW/CC -> PM | TODO cleanup map | Active TODO keeps next actions only; completed or historical evidence is moved to archive/report pointers. |

Parallelism: all four AEG-S0 sessions can run in parallel. Ceiling: 4, below the project limit of 7.

## 2. E1 Prohibited Work Before AEG-S0 Pass

E1 must not start:

- Bybit historical backfill writer.
- `market.klines` retention/runtime PG mutation.
- Funding/OI/long-short 18mo backfill.
- Mark/index/premium kline client implementation.
- Listing-capture collector implementation.
- Alpha scoring or promotion report generation.

Allowed: read-only probes and sizing estimates only.

## 3. AEG-S1 Foundation Sprint（after AEG-S0 contracts pass）

| Session | Owner chain | Dependency | Acceptance |
|---|---|---|---|
| `AEG-S1-W1-S1 Retention + Alpha-History Storage` | PM -> E1+MIT -> E2/E4 | `AEG-S0-W0-S1` | `market.klines` retention/storage path decided and landed safely if chosen; funding/OI/long-short retention or dedicated research storage decided; rollback and verify plan has evidence. |
| `AEG-S1-W1-S2 Public Bybit Backfill Writer` | PM -> E1+BB -> MIT -> E2/E4 | S1-W1-S1 + endpoint contract | Idempotent; fail-closed; closed candles only; `retCode != 0` creates no fabricated row; every run emits manifest, coverage, and provenance. |
| `AEG-S1-W1-S3 Symbol Universe PIT Builder` | PM -> MIT -> PA | Storage contract | Uses `market.symbol_universe_snapshots`; includes active + delisted/closed; current-survivor-only universe is rejected. |
| `AEG-S1-W1-S4 Side Evidence Artifact` | PM -> PA/E1 -> QC | Storage contract | News/X/Reddit context is linked to `run_id`, marked secondary, and excluded from promotion gates. |

Parallelism: S1-W1-S1, S1-W1-S3, and S1-W1-S4 can run in parallel. S1-W1-S2 waits for storage and endpoint contracts.

## 4. AEG-S2 Evidence Automation Sprint

| Session | Owner chain | Dependency | Acceptance |
|---|---|---|---|
| `AEG-S2-W1-S1 Regime Label Runner` | PM -> E1+QC -> MIT | S1 backfill green | Fixed classifier version; `feature_ts <= signal_ts`; main regime + overlay flags; no candidate-tuned boundary. |
| `AEG-S2-W1-S2 Breadth Ladder Runner` | PM -> E1+MIT -> QC | PIT universe + backfill green | core25 / scanner-active / top-liquidity 40-50 / full survivorship diagnostics; reruns monthly when >=30d new data, universe drift >10%, and before promotion. |
| `AEG-S2-W1-S3 Robustness Matrix Builder` | PM -> E1+QC -> MIT | Regime + breadth artifacts | candidate x regime x cohort x freshness matrix; flags bull-only, stale-only, and breadth-limited results. |

Parallelism: regime and breadth runners can run in parallel. Robustness matrix waits for both.

## 5. AEG-S3 Alpha Research Sprint

| Session | Owner chain | Dependency | Acceptance |
|---|---|---|---|
| `S1-W2-S1 TSMOM Sweep` | PM -> QC+MIT -> PM | AEG-S2 green | net edge > 2x cost; PSR(0)>0.95; DSR>0; OOS Sharpe >=0.5x IS; OOS<0.3x kills. |
| `S1-W2-S2 X-Sectional Sweep` | PM -> QC+MIT -> PM | AEG-S2 green | Same statistical gates; if breadth is insufficient, label `breadth-limited` and block promotion. |
| `S4/Sx Regime Falsification Overlay` | PM -> QC+MIT -> PA | AEG-S2 green | Bull-only/stale-only positives are `regime-bet / learning-only`; cannot promote. |
| `S2-W1 BB PreLaunch Probe` | PM -> BB+MIT -> QC | S2 Gate-A proceed | 24h phase-transition probe; no collector write implementation; confirms subscription, handler, and rate-limit feasibility. |

Parallelism: four sessions can run in parallel. Track 3 ensemble remains blocked on Track 1 GO.

## 6. AEG-S4 Decision Sprint

`S1-W3-S1 CP-2 Verdict`: PM -> QC+MIT -> PA -> Operator.

Acceptance:

- Every candidate returns one final label: `durable-alpha candidate`, `regime-bet / learning-only`, `stale-data artifact`, `breadth-limited`, `insufficient evidence`, or `kill`.
- Aggregate metrics are accompanied by regime, breadth, freshness, survivorship, and execution-realism matrices.
- No bull-only, stale-only, survivor-only, or narrative-only result can promote.

## 7. PM 2nd Sign-off

PM second sign-off approved this arrangement and opened AEG-S0 only. Subsequent
PA/MIT/QC/BB/TW/CC re-review passed AEG-S0 and opens AEG-S1 Foundation in
limited scope. This document still does not authorize E1 backfill, DB mutation,
runtime deploy, collector IMPL, or promotion scoring.

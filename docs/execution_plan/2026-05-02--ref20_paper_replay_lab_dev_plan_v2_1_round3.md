> **SUPERSEDED** by [ref20_paper_replay_lab_dev_plan_v3.md](2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md) -- retained for historical reference.

# REF-20 Paper Replay Lab 開發方案 V2.1 Round3

**日期：** 2026-05-02
**狀態：** SUPERSEDED by V3；V2.1 Round3 implementation-planning baseline 歷史保留
**Owner：** PM
**上游契約：** REF-19 / REF-20
**審查輸入：** V2、Round3 audit
**配套 UX 文件：** `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`

---

## 1. PM 判定

Round3 audit 大部分成立，但它不推翻 V2。V2 的核心方向仍正確：Paper Replay Lab 的價值不是價格播放器，而是在不等待真實時間流逝的前提下，壓縮測試 strategy decision、risk gate、IntentProcessor 行為、費率與執行假設。Round3 的價值是把 V2 裡仍偏文字化的條款補成 P0 commit 前可執行的工程 contract。

本文件將 V2 收斂為 V2.1 Round3。V2 保留為審查歷史；實作接手時以本文件為準。

接受的 Round3 finding：

1. `manifest_jsonb` 內的 calibration / OOS / candidate windows 與 `total_candidates_K` 必須拉成物理欄位，不能只靠 JSONB。
2. `learning.mlde_shadow_recommendations` retrofit 必須有 backfill allowlist、ambiguous row policy、migration report 與 owner。
3. `replay.experiments.parent_experiment_id`、`replay.simulated_fills.intent_id`、`decision_lease_id`、`idempotency_key`、`engine_binary_sha` nullable semantics 必須明確。
4. Replay-derived MLDE/Dream advisory 寫入必須由 DB role / verified function 收斂，不能只寫 application rule。
5. Migration V### 必須由 PM 集中預留，PR/commit gate 必須引用 Guard A/B/C；不在設計文件硬寫死具體 V###。
6. P2 啟動前必須完成當前 5 個策略的 indicator leak-free sweep。
7. P3+ canonical runner 必須在 P0 前定為 dedicated Rust binary target，不再保留三選一。
8. Manifest/resource quota、TTL、key retention、fail-closed 行為必須寫死。
9. P1 前必須 land dedicated UX subdoc；PR section 不能替代。

需要修正 Round3 原文的地方：

1. 不接受「P2 禁用 `TickPipeline` / `IntentProcessor`」。正確方案是使用同一 decision/risk hot path，但在 `ReplayProfile::Isolated` no-write profile 下 fail-closed。
2. 不接受全面禁止 Mac S2 public data。Mac 可跑 S2 public-data / S3 synthetic smoke，但不得讀 S0/S1/private runtime DB，不得寫 registry/advisory，不得產生 actionable result；任何可行動解讀必須 Linux `trade-core` 重跑。
3. `nm` / `objdump` symbol grep 可作為 defense-in-depth regression check，但不能是唯一 enforcement，因為 Rust 符號可能被 strip 或 mangled。
4. `decision_lease_id` 在 replay artifacts 裡是 nullable lineage metadata。P2 isolated replay 不得 acquire Decision Lease，也不得把 simulated fill 當成真實 lease outcome。

---

## 2. Non-Negotiable Boundaries

1. Replay never submits live orders.
2. Replay never writes simulated rows to `trading.fills`.
3. Replay never inserts simulated labels into `learning.mlde_edge_training_rows`.
4. Replay-derived MLDE/Dream rows are advisory only and must be registry-backed.
5. Live/live_demo mutation remains GovernanceHub + Decision Lease + live gates.
6. Demo handoff remains bounded, audited, reversible, and routed through existing MLDE demo applier guards.
7. P2 smoke replay cannot emit `demo_candidate`, `live_candidate_research_only`, or `live_approved`.
8. P3+ calibration cannot train on the same window used to select a candidate.
9. Any actionable candidate must be reproducible from signed manifest + registry artifacts + Linux runtime binary sha.
10. Paper Replay Lab UI must show run mode, data tier, runtime environment, and execution confidence before any result is interpreted.
11. Mac dev smoke is non-actionable by definition.
12. MLDE / DreamEngine are called by Replay as advisory participants; they are not rewritten into replay-only tools.

---

## 3. Round3 P0 Hard Gates

These items block P0 amendment commit and any runtime implementation PR that depends on REF-20.

| Gate | Requirement | Blocking phase |
|---|---|---|
| R3-G1 schema windows | `replay.experiments` has physical calibration / OOS / candidate window columns and `total_candidates_K` | P2a / P3a |
| R3-G2 lineage columns | `parent_experiment_id`, `intent_id`, `decision_lease_id`, `idempotency_key`, `engine_binary_sha` nullable rule | P2a / P2b |
| R3-G3 MLDE retrofit | backfill allowlist, ambiguous rows, migration report, owner, healthcheck | P2a / P4 |
| R3-G4 DB role guard | DB-level insert path for replay-derived advisory rows; no ad hoc INSERT | P2a / P4 |
| R3-G5 migration governance | PM V### reservation + Guard A/B/C templates in PR/commit | P0 |
| R3-G6 indicator sweep | 5 strategy indicator leak-free audit before P2 runner | P2 |
| R3-G7 runner decision | dedicated Rust binary target `replay_runner` chosen before implementation | P0 / P2 |
| R3-G8 fail-closed isolation | forbidden P2 wiring aborts immediately and logs reason | P2 |
| R3-G9 manifest quotas | 30d TTL, per-actor active cap, global storage cap, key retention | P2a |
| R3-G10 UX subdoc | dedicated `ref20_ux_subdoc_v1.md` landed before P1 | P1 |
| R3-G11 Mac policy | Mac writes no registry/advisory and produces no actionable result | P2 |
| R3-G12 quant patches | embargo, shrinkage tree, regime warmup, cost gate | P3+ |

---

## 4. Schema Contract

### 4.1 Replay Registry

Implementation must add a `replay` schema through normal SQL migrations. Actual V### numbers are reserved by PM after checking current `sql/migrations/` HEAD.

`replay.experiments` minimum:

| Column | Contract |
|---|---|
| `experiment_id` | primary external id |
| `parent_experiment_id` | nullable FK/self-reference for baseline vs candidate lineage |
| `created_at` | timestamptz |
| `created_by` | actor id |
| `runtime_environment` | `linux_trade_core` / `mac_dev_smoke_test_only` |
| `git_sha` | repo sha |
| `engine_binary_sha` | required for `linux_trade_core`; NULL for non-actionable Mac dry-run only |
| `strategy_config_sha256` | strategy config hash |
| `risk_config_sha256` | risk config hash |
| `timeframe` | `CHECK IN ('1m','3m','5m','15m','1h','4h','1d','tick')` |
| `data_tier` | `S0` / `S1` / `S2` / `S3` / `S4` |
| `execution_confidence` | `none` / `limited` / `calibrated` |
| `calibration_train_window_start` / `end` | physical timestamptz columns |
| `oos_label_window_start` / `end` | physical timestamptz columns |
| `candidate_window_start` / `end` | physical timestamptz columns |
| `oos_embargo_seconds` | physical integer, computed from `max(7d, 2 * signal_half_life)` in P3+ |
| `total_candidates_K` | physical integer, required for DSR/PBO accounting |
| `manifest_jsonb` | canonical manifest |
| `manifest_hash` | hash of canonical manifest |
| `manifest_signature` | server-side HMAC |
| `signature_key_ref` | key reference only, never secret value |
| `expires_at` | TTL boundary for artifact retention |
| `status` | created / running / completed / failed / cancelled |
| `output_policy_jsonb` | handoff flags; live flags always false |

Window constraints:

1. Each start/end pair must satisfy `start < end`.
2. Calibration train, OOS label, and candidate windows must be pairwise non-overlapping.
3. Candidate start must satisfy OOS embargo.
4. Baseline and candidate runs compared in the same report must use the same market data window and data tier.
5. SQL must enforce what SQL can enforce directly. If implementation uses `tstzrange` / `EXCLUDE USING gist`, the migration must include the required extension such as `btree_gist` when needed and must pass Guard A/B/C.

`replay.report_artifacts` minimum:

| Column | Contract |
|---|---|
| `artifact_id` | primary external id |
| `experiment_id` | FK to `replay.experiments` |
| `artifact_type` | summary / canary_jsonl / comparison / diagnostic / calibration / ux_snapshot |
| `uri` | `replay://...` or allowlisted runtime-local path |
| `source_mix_jsonb` | NOT NULL |
| `metrics_jsonb` | NOT NULL |
| `created_at` | timestamptz |
| `expires_at` | inherited or shorter than experiment TTL |

`replay.simulated_fills` minimum:

| Column | Contract |
|---|---|
| `sim_fill_id` | primary external id |
| `experiment_id` | FK to `replay.experiments` |
| `intent_id` | nullable lineage id from IntentProcessor output |
| `decision_lease_id` | nullable metadata only; P2 isolated replay must not acquire leases |
| `idempotency_key` | per simulated order/fill lifecycle |
| `ts` / `ts_ms` | simulated event time |
| `symbol` | Bybit symbol |
| `strategy_name` | strategy key |
| `side` | buy/sell or long/short normalized |
| `qty` | simulated qty |
| `price` | simulated fill price |
| `fee` | modeled fee |
| `fee_rate` | maker/taker rate used |
| `liquidity_role` | maker / taker / unknown |
| `evidence_source_tier` | calibrated_replay / synthetic_replay / counterfactual_replay |
| `execution_model_version` | nullable in P2, required in P3+ |
| `ci_low_bps` / `ci_mid_bps` / `ci_high_bps` | nullable row-level or linked aggregate confidence fields |
| `payload` | JSONB details |

No replay table may be read by existing live/demo metric code unless explicitly wired through replay routes.

### 4.2 MLDE Evidence Source Guard

Before replay-derived advisory rows are allowed, add columns to `learning.mlde_shadow_recommendations`:

| Column | Contract |
|---|---|
| `evidence_source_tier` | NOT NULL, default `real_outcome`, CHECK enum |
| `replay_experiment_id` | NULL for real outcome; NOT NULL for replay-derived rows |
| `manifest_hash` | NULL for real outcome; NOT NULL for replay-derived rows |

Allowed `evidence_source_tier`:

- `real_outcome`
- `calibrated_replay`
- `synthetic_replay`
- `counterfactual_replay`

Initial producer allowlist for legacy `real_outcome` backfill:

- `dream_engine`
- `ml_shadow`
- `opportunity_tracker`

Migration preflight must run `SELECT DISTINCT source FROM learning.mlde_shadow_recommendations` and attach the result to the migration report. Any source outside the allowlist must be explicitly classified by PM before Guard B. Ambiguous rows are not silently backfilled; they are written to a migration report table and block healthcheck until classified or excluded.

Required migration report:

| Field | Requirement |
|---|---|
| `migration_id` | V### once reserved |
| `owner` | PM-assigned migration owner |
| `source` | legacy producer source |
| `row_count` | count affected |
| `classification` | real_outcome / ambiguous / excluded |
| `reason` | human-readable reason |
| `created_at` | timestamptz |

Replay-derived row CHECK:

```sql
(
  evidence_source_tier = 'real_outcome'
  AND replay_experiment_id IS NULL
  AND manifest_hash IS NULL
)
OR
(
  evidence_source_tier <> 'real_outcome'
  AND replay_experiment_id IS NOT NULL
  AND manifest_hash IS NOT NULL
)
```

DB write permission:

1. Implementation must inspect current grants before changing permissions.
2. Direct ad hoc INSERT of replay-derived evidence is forbidden.
3. Replay-derived advisory rows must go through a verified insert function that checks replay registry FK, manifest hash, source tier, and output policy.
4. `REVOKE INSERT FROM PUBLIC` / role-based `GRANT EXECUTE` is the target posture, but final SQL must preserve legitimate existing producers for `real_outcome`.

Required healthchecks:

- `check_evidence_source_tier_completeness`
- `mlde_replay_source_guard`
- `replay_shadow_sink_boundary`
- `replay_registry_fk_contract`

---

## 5. Manifest, Quota, and Retention

Manifest signature remains mandatory from P2a.

| Field | Requirement |
|---|---|
| algorithm | HMAC-SHA256 |
| key path | `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` |
| key separation | must not reuse live `auth_signing_key` |
| rotation | 90 days target |
| old key retention | verify archived manifests for at most 180 days |
| signer | server-side only |
| client supplied signature | rejected |
| verification order | verify signature first, then manifest hash |
| failure mode | fail-closed; run / handoff rejected |

Resource limits:

| Limit | Value |
|---|---|
| manifest TTL | 30 days default |
| per-actor active manifests/runs | 20 active manifests, 1 active run |
| global active runs | 1 in P2/P3 |
| artifact storage cap | implementation must define env-specific cap before P2a merge |
| prune job | required before sustained P2 usage |

Canonical manifest must include git sha, engine binary sha, strategy/risk config hashes, runtime environment, symbol list, timeframe, data tier, source mix expectation, calibration train window, OOS label window, candidate window, total candidates explored, selection-bias correction metadata, fee model, execution confidence, output policy, and expiry.

---

## 6. Replay Runner Contract

### 6.1 Canonical Implementation Choice

P3+ and durable P2 execution use a dedicated Rust binary target named `replay_runner`.

The target may share internal strategy, risk, `TickPipeline`, and `IntentProcessor` modules, but it must not share live process bootstrap, IPC, exchange dispatch, DB writer channels, or Decision Lease acquisition wiring.

### 6.2 P2 Isolated Smoke Runner

P2 is for developer speed and decision/risk smoke replay. It may use `TickPipeline` and `IntentProcessor` only under `ReplayProfile::Isolated`.

Allowed:

- S2 public Bybit data fetched from public API
- S3 synthetic OHLC/tick data
- `TickPipeline`
- `IntentProcessor`
- in-memory paper state
- canary / diagnostic output
- baseline vs candidate comparison

Forbidden:

- Decision Lease acquisition
- IPC server usage
- WebSocket usage
- exchange dispatch
- DB writer channels inside the runner
- writes to `trading.*`, `learning.*`, live/demo config, or advisory tables
- MLDE/Dream advisory writes
- `demo_candidate`
- `live_candidate_research_only`
- `live_approved`

Fail-closed behavior:

- Any forbidden path detected at startup aborts before replay begins.
- Any forbidden path detected during replay aborts the run, records a failed experiment status where allowed, and emits a non-actionable diagnostic.
- Logging-only failure is not accepted.

Acceptance checks:

- `ReplayProfile::Isolated` is required for P2.
- no `acquire_lease` path is called.
- `trading_tx`, `market_data_tx`, `feature_tx`, `context_tx`, `decision_feature_tx`, and `order_dispatch_tx` are not wired.
- no exchange/API credential is loaded by the runner.
- no DB DSN is required by the runner itself for P2 dry-run execution.
- output has `execution_confidence='none'`.
- optional `nm` / `objdump` symbol grep may be added as defense-in-depth, but runtime and unit tests remain authoritative.

### 6.3 Mac Policy

Mac dev machine policy:

1. May run S2 public-data smoke and S3 synthetic smoke.
2. Must not read S0/S1 private runtime data, `trading.fills`, `learning.exit_features`, demo/live_demo fills, or local private orderbook captures.
3. Must not write replay registry, MLDE/Dream advisory rows, or handoff candidates.
4. Must produce dry-run console/local artifact output only.
5. Must mark `runtime_environment='mac_dev_smoke_test_only'`, `engine_binary_sha=NULL`, and `execution_confidence='none'`.
6. Any actionable interpretation requires Linux rerun on `linux_trade_core`.

`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` is the default and must fail closed if Mac attempts S0/S1/private data access.

---

## 7. P2 Precondition: Indicator Leak-Free Sweep

Before P2 runner implementation starts, QC owns an indicator leak-free sweep across the currently wired 5 strategies.

Required output:

| Field | Requirement |
|---|---|
| strategy inventory | generated from runtime registration, not manually guessed |
| indicator list | every rolling/lagged feature used by each strategy |
| shift compliance | `indicator x shift(1)` or equivalent no-lookahead proof |
| fixture | at least one deterministic replay window per strategy |
| verdict | pass / retract / fix-required |

If any strategy has lookahead leakage:

1. It is retracted from replay eligibility immediately.
2. P2 may proceed only if the leaking strategy is excluded and the exclusion is explicit in manifest/report.
3. If the strategy is part of the baseline comparison set, P2 is blocked until fixed.

This gate exists because replay invalidates itself if strategy indicators can see future bars. It is not a claim that a leak currently exists.

---

## 8. Quant and Calibration Patches

P3+ remains blocked until these numeric gates are implemented.

| Gate | Requirement |
|---|---|
| attribution completeness | `attribution_chain_ok_ratio >= 0.70` over calibration OOS label window |
| strategy-window sample | `n >= 200` fills per strategy-window for global calibration |
| cell sample | `n >= 30` per strategy/symbol/side cell |
| stale calibration | model age <= 72h for actionable handoff |
| OOS embargo | `max(7d, 2 * signal_half_life)` |
| DSR | `DSR(K) > 0.95` for promotion-oriented reports |
| PBO | `PBO < 0.5` when candidates K >= 10 and CSCV has sufficient splits |
| cost gate | `cost_edge_ratio >= 0.8` for LLM/ML assisted candidate loops |

Shrinkage decision tree:

1. cell `n < 30`: report low confidence; block handoff.
2. small cell but enough related cells: hierarchical Bayes preferred.
3. cross-strategy global estimate: James-Stein allowed.
4. small-K candidate comparison: empirical Bayes allowed.
5. method must be declared in manifest/report; ad hoc shrinkage is forbidden.

Regime controls:

1. First 500 fills after a negative-edge regime transition are warmup and cannot drive handoff.
2. CUSUM on realized edge per cell freezes actionable calibration on +/- 3 sigma break.
3. Kupiec POF uses calibration OOS sample when enough fills exist; if sample competes with PBO power, verdict becomes `defer_data`.
4. PSR(0) < 0.95 across repeated windows triggers refit recommendation and PM alert.

---

## 9. Product / UX Contract

Dedicated UX subdoc is mandatory:

- `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`

P1 frontend work is blocked until that file is accepted.

Core UX decisions:

1. Paper Tab becomes Paper Replay Lab with Session / Replay / Compare / Handoff.
2. `tab-paper.html` Replay workflow must not expose order submit/cancel controls.
3. Existing manual paper submit/cancel controls are removed from Paper Replay Lab P1 unless operator explicitly creates a separate legacy-only dev surface.
4. Disabled states must be honest and phase-labelled.
5. Mode badges must show session/replay mode, data tier, execution confidence, and runtime environment.
6. `execution_confidence='none'` must be visually non-actionable.
7. Handoff remains disabled until P6 and requires typed confirmation.
8. Learning remains a knowledge cockpit; it does not run replay.
9. Agents Monitor extraction waits until LG-2/3/4 frontend merged plus 7d stable.

---

## 10. Phased Delivery

### P0 - Amendments and Gates

Deliverables:

- REF-19 v2 amendment
- REF-20 v2 amendment
- V2.1 Round3 baseline
- UX subdoc v1
- migration reservation plan
- Guard A/B/C templates attached to migration PR plan
- indicator leak-free sweep task assigned

Exit:

- docs-only sign-off
- no runtime changes
- no DB migration yet

### P1 - Paper Replay Lab IA

Deliverables:

- Paper Tab shell reorganized into Session / Replay / Compare / Handoff
- manual submit/cancel removed from Replay Lab surface
- honest disabled states and mode badges
- existing Paper session display regression passes

Exit:

- `paper_replay_lab_no_order_submit` passes for Replay workflow and Paper Replay Lab shell.

### P2a - Registry / Auth / Manifest Foundation

Deliverables:

- `replay.experiments`
- `replay.report_artifacts`
- manifest canonicalization
- HMAC signature
- route auth scaffolding
- `evidence_source_tier` migration and healthcheck
- manifest quota/TTL/prune path

Exit:

- Guard A/B/C pass.
- route auth tests pass.
- manifest signature verify tests pass.
- evidence source healthcheck green.

### P2b - Read-Only S2/S3 Smoke Replay

Deliverables:

- `replay_runner` P2 isolated profile
- run/status/cancel/report routes
- canary/diagnostic artifacts registered on Linux only
- baseline vs candidate smoke comparison

Exit:

- no DB writer channels wired in runner.
- no exchange/IPC/WS/live auth path.
- no advisory/handoff output.
- `execution_confidence='none'`.

### P3a - Global Execution Calibration

Deliverables:

- S0-only calibration labels
- OOS embargo
- fee model
- maker/taker execution estimates
- bootstrap CI and shrinkage method

Exit:

- attribution >=0.70.
- n>=200 per strategy-window.
- stale<=72h.
- actionable handoff still disabled until P4/P6 guards.

### P3b - Cell-Level Calibration

Deliverables:

- strategy/symbol/side cell calibration
- n>=30 cell gate
- hierarchical/empirical shrinkage
- S1 recorder dependency tracked separately

Exit:

- insufficient cells blocked from handoff.
- regime shift controls present.

### P4 - MLDE / Dream Advisory

Deliverables:

- DreamEngine proposes replay candidates.
- MLDE ranks/vetoes replay candidates.
- source-guarded advisory rows.
- PBO / DSR metadata.

Exit:

- every replay-derived row references replay registry.
- `mlde_demo_applier` ignores unverified replay-derived rows.
- no demo mutation yet unless P6 enabled.

### P5 - Agents Monitor Extraction

Deliverables:

- 5-Agent panel moved out of Learning.
- Learning redirect notice.
- Agents Monitor read-only route behavior preserved.

Entry:

- LG-2/3/4 frontend merged.
- 7d frontend stable.

### P6 - Bounded Demo A/B Handoff

Deliverables:

- `/api/v1/replay/candidates` enabled for `demo_candidate`.
- typed confirmation.
- applier source guard.
- bound validation.
- audit row.

Exit:

- demo handoff is bounded, idempotent, reversible.
- live/live_demo still requires GovernanceHub + Decision Lease + live gates.
- replay cannot emit `live_approved`.

---

## 11. Acceptance Checks

| Check | Phase | Requirement |
|---|---|---|
| `replay_manifest_contract` | P2a | signed manifest, hash, timeframe enum, data tier, output policy, physical windows |
| `replay_signature_verify` | P2a | signature verified before hash; fail-closed |
| `replay_route_auth_contract` | P2a | route role/scope/idempotency/rate tests |
| `replay_manifest_quota_guard` | P2a | TTL, active caps, storage cap |
| `check_evidence_source_tier_completeness` | P2a | no NULL/invalid evidence tier |
| `mlde_replay_source_guard` | P2a/P4 | replay-derived advisory rows require registry FK and manifest hash |
| `replay_registry_fk_contract` | P2a | report artifacts and simulated fills reference experiments |
| `replay_resource_isolation` | P2b | no IPC/WS/exchange/DB writer channels |
| `replay_no_decision_lease_acquire` | P2b | smoke replay does not call `acquire_lease` |
| `replay_forbidden_wiring_fail_closed` | P2b | forbidden path aborts run, not log-only |
| `replay_execution_confidence_label` | P2b | S2/S3 smoke reports say execution confidence none |
| `replay_mac_non_actionable` | P2b | Mac dry-run cannot write registry/advisory |
| `strategy_indicator_leak_free` | P2 | 5 strategy sweep passed or explicit exclusion exists |
| `replay_no_live_mutation` | all | no live/demo config mutation or live orders |
| `execution_calibration_freshness` | P3 | model age <=72h for handoff |
| `execution_calibration_power` | P3 | n thresholds enforced |
| `replay_cv_protocol` | P4/P6 | DSR and PBO gates enforced |
| `replay_regime_shift_gate` | P3+ | frozen regime blocks actionable candidates |
| `paper_replay_lab_no_order_submit` | P1+ | Replay Lab has no submit/cancel controls |
| `replay_handoff_typed_confirm` | P6 | typed confirmation and idempotency required |
| `agents_monitor_read_only` | P5 | extracted Agents Monitor remains read-only |

---

## 12. Immediate Next Work

1. Land this V2.1 Round3 baseline and the UX subdoc as docs-only.
2. Draft REF-19 v2 / REF-20 v2 amendments from this baseline.
3. Reserve migration V### through PM before touching SQL.
4. Assign QC/E3 sweep for 5 strategy indicator leak-free audit.
5. Start P1 only after UX subdoc sign-off.
6. Start P2a only after migration Guard A/B/C plan is attached.

PM sign-off: **CONDITIONAL APPROVE FOR P0 AMENDMENT PLANNING**. Runtime implementation remains blocked until REF-19 v2 / REF-20 v2, migration reservation, UX subdoc sign-off, and P2a schema/auth/signature contracts land.

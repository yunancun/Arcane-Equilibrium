> **SUPERSEDED** by [ref20_paper_replay_lab_dev_plan_v3.md](2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md) -- retained for historical reference.

# REF-20 Paper Replay Lab 開發方案 V2

**日期：** 2026-05-02
**狀態：** SUPERSEDED by V3；V2 development baseline 歷史保留
**Owner：** PM
**上游契約：** REF-19 / REF-20
**審查輸入：** V1、v0.1、Round2 audit

---

## 1. PM 判定

Round2 audit 的主方向成立：V1 把產品與治理邊界釐清了，但很多條款仍停留在「應該」層面，還不足以進入 replay backend、MLDE/Dream advisory、或 demo handoff 實作。V2 將 round2 的真實問題補成可落地 contract。

接受的核心 finding：

1. `evidence_source_tier` 必須是 DB row-level column，帶 `CHECK`、backfill、healthcheck、grant 收斂；不能只靠 JSONB payload tag。
2. replay registry 需要 `replay.experiments`、`replay.report_artifacts`，且 P2b 前新增 `replay.simulated_fills`；simulated fills 永遠不寫 `trading.fills`，也不借用 `engine_mode='paper'`。
3. manifest 必須 server-side HMAC-SHA256 簽名，使用獨立 `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`，不重用 live authorization signing key。
4. replay routes 必須明確 role、scope、idempotency、rate limit、global concurrency cap。
5. attribution、sample power、staleness、OOS embargo、PBO、DSR、bootstrap CI 必須有硬閾值，不能保留「equivalent gate」。
6. P1 frontend 前必須有 UX contract，避免 Paper Replay Lab 變成看似完整但不可用的假界面。
7. P5 5-Agent extraction 必須等 LG-2/3/4 frontend merged + 7d stable，避免前端多路 merge 互撞。

需要反對或改寫的 finding：

1. **反對 C-3 的原句：P2/P2b 不應禁止 `IntentProcessor` 或禁止 link Rust trading code。**
   事實上，現有 Rust replay mode 透過 `TickPipeline` 跑 `on_tick()`，`TickPipeline` 本身擁有 `IntentProcessor`。Replay 的開發價值正是壓縮測 decision、risk、strategy intent 行為。如果禁止 `IntentProcessor`，P2 會退化成價格播放器，不能解決 operator 的開發痛點。

   V2 改為：P2/P2b 可以使用 `TickPipeline` / `IntentProcessor`，但必須在 isolated no-write replay profile 下運行：不接 IPC、不接 WS、不接 exchange dispatch、不接 DB writer、不 acquire Decision Lease、不寫 `trading.*` / `learning.*`、不產生 advisory / handoff。

2. **反對 E3 NEW-01 的過度版本：Mac smoke 不應全面禁止 S2 public data。**
   S2 Bybit public klines / trades / funding / OI 是公開市場資料，Mac 開發機可直接從 public API 拉取並跑 smoke。真正應禁止的是 Mac 讀 S0/S1 私有 runtime DB、`trading.fills`、`learning.exit_features`、demo/live_demo fills、local recorded private orderbook。任何可行動結論或 `demo_candidate` 都必須在 `linux_trade_core` 使用 deployed/runtime binary sha 重跑。

3. **改寫 C-4：P3+ 需要 dedicated replay runner，但不強制只能新建 crate。**
   可以是 `replay_engine` crate、獨立 binary、或清晰隔離的 process target；但不得只沿用 P2 canary JSONL replay 和 `CanaryRecord` 作 execution-realistic replay。P3+ 必須產生完整 simulated fill / order lifecycle artifacts，並接 execution calibration。

4. **改寫 V### 編號建議。**
   migration 順序必須固定，但具體 V### 不在文件中硬編，因為 HEAD 可能被其他 session 推進。實作時採「當前 latest migration 之後連續分配」。

本文件替代 V1 作為當前 dev plan。早期 v0.1 / V1 / round2 audit 保留為審查歷史，不再作實作基線區分。

---

## 2. Non-Negotiable Boundaries

1. Replay never submits live orders.
2. Replay never writes simulated rows to `trading.fills`.
3. Replay never inserts simulated labels into `learning.mlde_edge_training_rows`.
4. Replay-derived MLDE/Dream rows are advisory only and must be registry-backed.
5. Live/live_demo mutation remains GovernanceHub + Decision Lease + live gates.
6. Demo handoff remains bounded, audited, reversible, and routed through existing MLDE demo applier guards.
7. P2 smoke replay cannot emit `demo_candidate`.
8. P3+ calibration cannot train on the same window used to select a candidate.
9. Any actionable candidate must be reproducible from signed manifest + registry artifacts.
10. Paper Replay Lab UI must show data tier and execution confidence before any result is interpreted.

---

## 3. Schema Contract

### 3.1 Replay Registry

Implementation must add a `replay` schema. Logical migration order:

1. replay registry and manifest signing fields
2. MLDE evidence source columns and backfill
3. simulated fill artifacts

Actual V### numbers are allocated at implementation time after the latest migration in `sql/migrations/`.

`replay.experiments` minimum:

| Column | Contract |
|---|---|
| `experiment_id` | primary external id |
| `created_at` | timestamptz |
| `created_by` | actor id |
| `runtime_environment` | `linux_trade_core` / `mac_dev_smoke_test_only` |
| `git_sha` | repo sha |
| `engine_binary_sha` | runtime binary sha when available |
| `strategy_config_sha256` | strategy config hash |
| `risk_config_sha256` | risk config hash |
| `timeframe` | `CHECK IN ('1m','3m','5m','15m','1h','4h','1d','tick')` |
| `data_tier` | `S0` / `S1` / `S2` / `S3` / `S4` |
| `execution_confidence` | `none` / `limited` / `calibrated` |
| `manifest_jsonb` | canonical manifest |
| `manifest_hash` | hash of canonical manifest |
| `manifest_signature` | server-side HMAC |
| `signature_key_ref` | key reference only, never secret value |
| `status` | created / running / completed / failed / cancelled |
| `output_policy_jsonb` | handoff flags, live flags always false |

`replay.report_artifacts` minimum:

| Column | Contract |
|---|---|
| `artifact_id` | primary external id |
| `experiment_id` | FK to `replay.experiments` |
| `artifact_type` | summary / canary_jsonl / comparison / diagnostic / calibration |
| `uri` | `replay://...` or allowlisted runtime-local path |
| `source_mix_jsonb` | NOT NULL |
| `metrics_jsonb` | NOT NULL |
| `created_at` | timestamptz |

`replay.simulated_fills` minimum:

| Column | Contract |
|---|---|
| `sim_fill_id` | primary external id |
| `experiment_id` | FK to `replay.experiments` |
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
| `payload` | JSONB details |

No replay table may be read by existing live/demo metric code unless explicitly wired through replay routes.

### 3.2 MLDE Evidence Source Guard

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

Producer identity stays in the existing `source` column (`dream_engine`, `ml_shadow`, `opportunity_tracker`, etc.). Do not mix producer identity into `evidence_source_tier`.

Backfill rule:

- Existing rows become `real_outcome` only when they are known existing MLDE/Dream/Opportunity rows from current producers.
- Any ambiguous legacy row must be marked by migration report and fail the healthcheck until manually classified or excluded.

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

Required healthcheck:

- `check_evidence_source_tier_completeness`
- `mlde_replay_source_guard`
- `replay_shadow_sink_boundary`

Write permission:

- Normal MLDE/Dream producers may write `real_outcome`.
- Replay-derived producers must write through replay registry verification.
- Direct ad hoc INSERT to replay-derived evidence is not an accepted path.

---

## 4. Manifest Signature Contract

Manifest signature is mandatory from P2a.

| Field | Requirement |
|---|---|
| algorithm | HMAC-SHA256 |
| key path | `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` |
| key separation | must not reuse live `auth_signing_key` |
| rotation | 90 days target; old keys may verify archived manifests until retention expires |
| signer | server-side only |
| client supplied signature | rejected |
| verification order | verify signature first, then manifest hash |
| failure mode | fail-closed; run / handoff rejected |
| audit | distinguish `signature_mismatch`, `manifest_hash_mismatch`, `key_missing`, `key_expired` |

Canonical manifest must include:

- git sha
- engine binary sha
- strategy config sha
- risk config sha
- runtime environment
- symbol list
- timeframe enum
- data tier
- source mix expectation
- calibration train window
- calibration OOS label window
- candidate window
- total candidates explored
- selection bias correction metadata
- output policy

---

## 5. API Contract

New replay routes live in new replay modules, not in `paper_trading_routes.py` or legacy `backtest_routes.py`.

Suggested files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_models.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_manifests.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_reports.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_registry.py`

Route contract:

| Route | Method | Auth / Scope | Limit |
|---|---|---|---|
| `/api/v1/replay/health` | GET | actor required, `replay:read` | 60/min |
| `/api/v1/replay/manifests` | POST | Operator, `replay:write`, idempotency key | 10/min |
| `/api/v1/replay/runs` | POST | Operator, `replay:run`, idempotency key | global concurrent=1, actor concurrent=1 |
| `/api/v1/replay/runs/{id}` | GET | actor required, `replay:read` | 60/min |
| `/api/v1/replay/runs/{id}/cancel` | POST | Operator, `replay:run` | 10/min |
| `/api/v1/replay/reports/{id}` | GET | actor required, `replay:read` | 60/min |
| `/api/v1/replay/compare` | POST | actor required, `replay:read` | 30/min |
| `/api/v1/replay/candidates` | POST | Operator, `replay:handoff`, idempotency key, typed confirm | disabled until P6 |

Concurrency:

- global active replay run cap = 1 in P2/P3
- per-actor active run cap = 1
- cap exceeded = HTTP 429 with current active experiment id
- wall-clock run budget = 5 minutes in P2; P3+ requires explicit budget field

URI safety:

- `report_uri` must be `replay://...` or runtime-local allowlisted path.
- GUI renders report text with safe text rendering, not arbitrary HTML.

---

## 6. Replay Runner Contract

### 6.1 P2 Smoke Runner

P2 is for developer speed and decision/risk smoke replay. It may use the existing Rust replay mode only under a strict no-write profile.

Allowed:

- S2 public Bybit data fetched from public API
- S3 synthetic OHLC ticks
- `TickPipeline`
- `IntentProcessor`
- in-memory `paper_state`
- canary / diagnostic output
- baseline vs candidate comparison

Forbidden:

- Decision Lease acquisition
- IPC server usage
- WebSocket usage
- exchange dispatch
- DB writer channels
- writes to `trading.*`, `learning.*`, or live/demo config
- MLDE/Dream advisory writes
- `demo_candidate`
- `live_candidate_research_only`

Acceptance checks must prove:

- no `acquire_lease` path is called
- `trading_tx`, `market_data_tx`, `feature_tx`, `context_tx`, and `decision_feature_tx` are not wired
- `order_dispatch_tx` is not wired
- no DB DSN is required for P2 runner execution
- output has `execution_confidence='none'`

Baseline definition:

- default baseline = current active demo strategy/risk config snapshot at `experiment_start_ts`
- candidate = explicit config patch or git/config snapshot under test
- both baseline and candidate must use the same market data window

Mac policy:

- Mac may run S2 public-data smoke and S3 synthetic smoke.
- Mac must not read S0/S1 private runtime data, `trading.fills`, `learning.exit_features`, or demo/live_demo fill labels.
- Any actionable interpretation requires Linux rerun on `linux_trade_core`.

### 6.2 P3+ Canonical Runner

P3+ must not use P2 canary replay as a calibrated backtest engine.

Required:

- dedicated replay process / binary / crate boundary
- may share TickPipeline / IntentProcessor code to preserve behavior
- no strategy fork for replay-only behavior
- no canary-mode flip as the main output mechanism
- full simulated order/fill lifecycle artifacts
- writes only to `replay.*`
- execution calibration model integration
- calibrated / pessimistic / optimistic report bands

The dedicated runner may be implemented as:

- a new Rust binary target,
- a new `replay_engine` crate,
- or an isolated Rust process target with explicit no-live/no-DB-writer profile.

The implementation choice is a PA/E1 design decision, but the boundary above is not optional.

---

## 7. Quant and Calibration Contract

P3+ is blocked until these numeric gates are implemented.

### 7.1 Attribution and Sample Power

| Gate | Threshold |
|---|---|
| attribution completeness | `attribution_chain_ok_ratio >= 0.70` over calibration OOS label window |
| strategy-window sample | `n >= 200` fills per strategy-window for global calibration |
| cell sample | `n >= 30` per strategy/symbol/side cell for cell-level actionable calibration |
| stale calibration | model age <= 72h for actionable handoff |
| OOS embargo | calibration train window and candidate window separated by >= 7d minimum |

Cells below n=30 may be reported with `low_confidence`, but cannot drive demo handoff.

### 7.2 Quantile and Shrinkage

q10/q50/q90:

- block bootstrap, Politis-Romano style, 1000 iterations
- preserve autocorrelation
- output 95% CI
- n<30 fallback may be parametric only if marked `low_confidence` and blocked from handoff

Shrinkage:

- allowed methods: `james_stein`, `empirical_bayes`, `hierarchical_bayes`
- method must be declared in manifest/report
- ad-hoc shrinkage is forbidden

### 7.3 Selection Bias Controls

For candidate exploration:

- `total_candidates_explored` is mandatory in manifest
- `DSR(K) > 0.95` required for promotion-oriented reports
- `PBO < 0.5` required when candidates K >= 10 and CSCV has sufficient splits
- if PBO cannot run because power is insufficient, verdict must be `defer_data`, not `demo_candidate`
- no generic "equivalent gate" fallback

### 7.4 Regime Shift Controls

P3+ report must include regime health:

- CUSUM on realized edge per cell; freeze calibration on +/- 3 sigma break
- Kupiec POF backtest every 250 fills when enough samples exist
- PSR(0) < 0.95 across repeated windows triggers refit recommendation and PM alert

If regime status is frozen or stale, replay may report research metrics but cannot hand off candidates.

---

## 8. Product / UX Contract

P1 frontend work is blocked until UX contract is landed, either as a dedicated `ref20_ux_subdoc_v1.md` or an approved equivalent section in the implementation PR.

Minimum UX requirements:

1. Paper Replay Lab sub-tabs: Session / Replay / Compare / Handoff.
2. Existing Paper submit/cancel controls, if retained, stay only in Session and never appear in Replay workflow.
3. Disabled states must be honest: no fake active buttons; use explicit "P2B pending" or "Coming in P2" cards.
4. Mode badges must distinguish paper session, replay run, data tier, and execution confidence.
5. Handoff requires typed confirmation, idempotency key, manifest hash, baseline delta, data tier, and trace id.
6. Compare must display at least net bps, q10/q50/q90, max drawdown, trade count, source mix, fee model, reject rate, calibration freshness.
7. Learning shows replay evidence and ML/Dream producer health only; it does not run replay.
8. Agents Monitor extraction waits until LG-2/3/4 frontend merged + 7d stable.

---

## 9. Phased Delivery

### P0 - Amendment and UX Contract

Deliverables:

- REF-19 v2 amendment
- REF-20 v2 amendment
- UX contract
- migration order design
- acceptance check list

Exit:

- V2 accepted as implementation baseline
- no runtime changes

### P1 - Paper Replay Lab IA

Deliverables:

- Paper Tab shell reorganized into Session / Replay / Compare / Handoff
- Session behavior preserved
- placeholders explicit and honest

Exit:

- existing Paper session UI regression passes
- Replay workflow has no order submission controls

### P2a - Registry / Auth / Manifest Foundation

Deliverables:

- `replay.experiments`
- `replay.report_artifacts`
- manifest canonicalization
- HMAC signature
- route auth scaffolding
- `evidence_source_tier` migration and healthcheck

Exit:

- route auth tests pass
- manifest signature verify tests pass
- evidence source healthcheck green
- GUI shows `P2B_PENDING` if no runnable backend exists

### P2b - Read-Only S2/S3 Smoke Replay

Deliverables:

- isolated no-write Rust replay wrapper
- run/status/cancel/report routes
- canary/diagnostic artifacts registered in `replay.report_artifacts`
- optional `replay.simulated_fills` only if fill-like artifacts are produced
- baseline vs candidate smoke comparison

Exit:

- global concurrent=1 enforced
- no DB writer channels wired
- no exchange/IPC/WS/live auth path
- no advisory/handoff output
- `execution_confidence='none'`

### P3a - Global Execution Calibration

Deliverables:

- calibration feature spec
- S0-only calibration labels
- OOS embargo
- fee model
- maker/taker execution estimates
- bootstrap CI and shrinkage method

Exit:

- attribution >=0.70
- n>=200 per strategy-window
- stale<=72h
- actionable handoff still disabled until P4/P6 guards

### P3b - Cell-Level Calibration

Deliverables:

- strategy/symbol/side cell calibration
- n>=30 cell gate
- hierarchical/empirical shrinkage
- S1 recorder dependency tracked separately

Exit:

- insufficient cells blocked from handoff
- regime shift controls present

### P4 - MLDE / Dream Advisory

Deliverables:

- DreamEngine proposes replay candidates
- MLDE ranks/vetoes replay candidates
- source-guarded advisory rows
- PBO / DSR metadata

Exit:

- every replay-derived row references replay registry
- `mlde_demo_applier` ignores unverified replay-derived rows
- no demo mutation yet unless P6 enabled

### P5 - Agents Monitor Extraction

Deliverables:

- 5-Agent panel moved out of Learning
- Learning redirect notice
- Agents Monitor read-only route behavior preserved

Entry:

- LG-2/3/4 frontend merged
- 7d frontend stable

### P6 - Bounded Demo A/B Handoff

Deliverables:

- `/api/v1/replay/candidates` enabled for `demo_candidate`
- typed confirmation
- applier source guard
- bound validation
- audit row

Exit:

- demo handoff is bounded, idempotent, reversible
- live/live_demo still requires GovernanceHub + Decision Lease + live gates
- replay cannot emit `live_approved`

---

## 10. Acceptance Checks

| Check | Phase | Requirement |
|---|---|---|
| `replay_manifest_contract` | P2a | signed manifest, hash, timeframe enum, data tier, output policy |
| `replay_signature_verify` | P2a | signature verified before hash; fail-closed |
| `replay_route_auth_contract` | P2a | route role/scope/idempotency/rate tests |
| `check_evidence_source_tier_completeness` | P2a | no NULL/invalid evidence tier |
| `mlde_replay_source_guard` | P2a/P4 | replay-derived advisory rows require registry FK and manifest hash |
| `replay_registry_fk_contract` | P2a | report artifacts and simulated fills reference experiments |
| `replay_resource_isolation` | P2b | no IPC/WS/exchange/DB writer channels |
| `replay_no_decision_lease_acquire` | P2b | smoke replay does not call `acquire_lease` |
| `replay_execution_confidence_label` | P2b | S2/S3 smoke reports say execution confidence none |
| `replay_no_live_mutation` | all | no live/demo config mutation or live orders |
| `execution_calibration_freshness` | P3 | model age <=72h for handoff |
| `execution_calibration_power` | P3 | n thresholds enforced |
| `replay_cv_protocol` | P4/P6 | DSR and PBO gates enforced |
| `replay_regime_shift_gate` | P3+ | frozen regime blocks actionable candidates |
| `paper_replay_lab_no_order_submit` | P1+ | Replay workflow has no submit/cancel controls |
| `replay_handoff_typed_confirm` | P6 | typed confirmation and idempotency required |
| `agents_monitor_read_only` | P5 | extracted Agents Monitor remains read-only |

---

## 11. Immediate Next Work

1. Draft REF-19 v2 / REF-20 v2 amendments from this V2.
2. Create the UX contract before P1 implementation.
3. Design migration sequence for `replay.*` + MLDE evidence source guard.
4. Add replay route auth and manifest signature test plan.
5. Add P2 no-write replay isolation tests before wiring any backend route.

PM sign-off: **CONDITIONAL APPROVE FOR P0 AMENDMENT PLANNING**. Runtime implementation remains blocked until REF-19 v2 / REF-20 v2, UX contract, and P2a schema/auth/signature contracts land.

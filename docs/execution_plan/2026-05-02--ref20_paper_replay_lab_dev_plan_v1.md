# REF-20 Paper Replay Lab 開發方案 V1

**日期：** 2026-05-02
**狀態：** V1 development baseline；不得直接從 draft v0.1 開工
**Owner：** PM
**上游契約：** REF-19 / REF-20
**輸入審查：** `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md`

---

## 1. PM 判定

draft v0.1 提出的改進建議大方向合理：REF-20 v0.1 只能作產品面設計，不足以直接進入後端 replay / MLDE / Dream / demo handoff 實作。

已確認為真實或高可信問題：

1. 現有 Rust `--replay-mode` 是 canary / smoke replay，不是 production-grade canonical replay path。
2. 現有 Python `BacktestEngine` 是 stub，且 `backtest_routes.py` 仍引用不存在的 `_live_kline_manager` 屬性，不能作為新 Replay Lab 的基礎。
3. `learning.mlde_shadow_recommendations` 目前沒有 row-level replay evidence source 欄位；若未來 replay-derived rows 進入同表，單靠 JSONB payload tag 風險過高。
4. `mlde_demo_applier._fetch_pending()` 目前只按 `engine_mode`、`applied`、`confidence`、`sample_count` 過濾；沒有 replay registry / manifest signature 驗證。
5. REF-20 §8 的 replay routes 缺明確 auth / scope / idempotency / rate-limit contract。
6. REF-19 / REF-20 manifest 目前沒有簽名契約；只列 git/config sha 不足以防止 report metadata 偽造。
7. file-only report sink 會製造 dangling reference 與後續 migration debt；Replay Lab 至少需要 DB registry。
8. 多 candidate search 後選 best candidate 存在 selection bias；必須有 candidate count、CV / PBO / DSR 或等價多重檢驗控制。
9. execution calibration 不能用同窗資料閉環訓練再評估；必須有 OOS / embargo / sample-power gate。
10. Paper / Learning / 5-Agent 的產品邊界仍正確：Paper 做 Replay Lab，Learning 做 evidence + producer monitor，5-Agent 應抽為 Agents Monitor。

需要修正 draft v0.1 的地方：

1. draft 口中的「7-agent 審查」本地無法獨立驗證，只能視為 review input，不視為正式 sign-off。
2. P2 read-only S3/S2 smoke replay 不應被 Decision Lease retrofit 完全阻塞；只要它獨立 process、無 live/demo mutation、無 handoff，就不需要等 lease retrofit deploy。P3+ calibration / P4 advisory / P6 handoff 才受 Decision Lease 與 applier guard 阻塞。
3. Mac replay 不必全部禁止。Mac 可跑 `mac_dev_smoke_test_only`，但任何可行動建議或 demo candidate 必須在 `linux_trade_core` / deployed binary sha 上重跑。
4. `source_tier` 不應混淆 producer 類型。V1 改為 `evidence_source_tier` 表示資料證據來源；現有 `source` 欄保留為 producer，例如 `dream_engine`、`ml_shadow`、`opportunity_tracker`。
5. P2 可以使用 S2 public klines / trades 與 S3 synthetic OHLC ticks，但必須標 `execution_confidence=NONE`，不得產生 `demo_candidate`。

結論：採納 draft 的安全、資料、量化與 UX 改進方向；調整過度阻塞與欄位語義後，形成以下 V1 開發方案。

---

## 2. 不可開工項

在以下條件落檔前，不得實作 replay-derived MLDE / Dream advisory 或 demo handoff：

1. REF-19 v2 / REF-20 v2 amendment 明確補入本文件的安全、資料、校準與 API contract。
2. replay registry migration landed：至少 `replay.experiments` + `replay.report_artifacts`。
3. manifest signature contract landed：server-side HMAC，client 不可自帶 signature。
4. replay route auth contract landed：role、scope、idempotency、rate limit、max concurrency。
5. MLDE recommendation source guard landed：`evidence_source_tier` + `replay_experiment_id` + applier verification。
6. execution calibration spec landed：OOS embargo、sample-power、quantile CI、shrinkage method。
7. Paper Replay Lab UI 明確標出 data tier / execution confidence / disabled handoff state。

---

## 3. 目標架構

```text
Paper Replay Lab UI
  Session | Replay | Compare | Handoff
        |
        v
/api/v1/replay/*
  replay_routes.py
  replay_models.py
  replay_manifests.py
  replay_reports.py
        |
        v
Replay Registry
  replay.experiments
  replay.report_artifacts
        |
        v
Isolated Replay Runner
  P2: existing Rust replay mode, S2/S3 smoke only
  P3+: canonical replay runner with calibrated execution model
        |
        v
Reports / Evidence
  Paper Replay Lab summary
  Learning replay evidence inbox
  MLDE/Dream advisory, only after P4 guards
  Demo handoff, only after P6 guards
```

Runtime authority remains unchanged:

- Rust remains trading / risk / strategy execution authority.
- Python remains control plane / API / GUI / orchestration plane.
- Replay routes never submit live orders.
- Replay rows never enter `trading.fills`.
- Replay labels never enter `learning.mlde_edge_training_rows`.

---

## 4. Schema Contract

### 4.1 Replay Registry

P2 開工前新增 migration，至少落兩張表。

`replay.experiments` minimum columns:

| Column | Requirement |
|---|---|
| `experiment_id` | primary external id |
| `created_at` | timestamptz |
| `created_by` | actor id |
| `runtime_environment` | `linux_trade_core` or `mac_dev_smoke_test_only` |
| `git_sha` | repo sha |
| `engine_binary_sha` | deployed/runtime binary sha when available |
| `strategy_config_sha256` | strategy config hash |
| `risk_config_sha256` | risk config hash |
| `data_tier` | S0 / S1 / S2 / S3 / S4 |
| `execution_confidence` | `none` / `limited` / `calibrated` |
| `manifest_jsonb` | canonical manifest |
| `manifest_signature` | server-side HMAC |
| `status` | created / running / completed / failed / cancelled |
| `output_policy_jsonb` | handoff flags, all live flags false |

`replay.report_artifacts` minimum columns:

| Column | Requirement |
|---|---|
| `artifact_id` | primary external id |
| `experiment_id` | FK to `replay.experiments` |
| `artifact_type` | summary / canary_jsonl / comparison / diagnostic |
| `uri` | `replay://...` or allowlisted local runtime path |
| `source_mix_jsonb` | required |
| `metrics_jsonb` | required |
| `created_at` | timestamptz |

File artifacts are allowed only when indexed by `replay.report_artifacts`.

### 4.2 MLDE Recommendation Guard

Before replay-derived advisory rows are allowed, add row-level evidence fields to
`learning.mlde_shadow_recommendations`.

Required fields:

| Column | Meaning |
|---|---|
| `evidence_source_tier` | `real_outcome`, `calibrated_replay`, `synthetic_replay`, `counterfactual_replay` |
| `replay_experiment_id` | non-null when evidence source is replay-derived |
| `manifest_hash` | hash of canonical replay manifest for replay-derived rows |

Rules:

- Existing real MLDE / Dream rows default to `evidence_source_tier='real_outcome'`.
- Existing `source` remains producer identity (`dream_engine`, `ml_shadow`, `opportunity_tracker`, etc.).
- Replay-derived rows must reference `replay.experiments`.
- `mlde_demo_applier` must reject replay-derived rows unless:
  - `replay_experiment_id` exists in `replay.experiments`
  - manifest signature verifies
  - output policy allows demo candidate handoff
  - candidate is within existing demo applier parameter bounds
  - operator handoff action has idempotency key and typed confirmation

---

## 5. API Contract

New routes must live in a new route module, not in `paper_trading_routes.py` or
legacy `backtest_routes.py`.

Suggested files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_models.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_manifests.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_reports.py`

Route contract:

| Route | Method | Auth / Scope | Notes |
|---|---|---|---|
| `/api/v1/replay/health` | GET | actor required, `replay:read` | readiness only |
| `/api/v1/replay/manifests` | POST | Operator, `replay:write`, idempotency key | server signs manifest |
| `/api/v1/replay/runs` | POST | Operator, `replay:run`, max concurrent=1 | starts isolated process |
| `/api/v1/replay/runs/{id}` | GET | actor required, `replay:read` | status / progress |
| `/api/v1/replay/runs/{id}/cancel` | POST | Operator, `replay:run` | kill isolated runner only |
| `/api/v1/replay/reports/{id}` | GET | actor required, `replay:read` | report summary |
| `/api/v1/replay/compare` | POST | actor required, `replay:read` | baseline vs candidate |
| `/api/v1/replay/candidates` | POST | Operator, `replay:handoff`, idempotency key | disabled until P6 |

Security requirements:

- All POST routes require explicit scope and Operator where listed.
- Manifest signing is server-side only.
- Active runs per actor are capped.
- Run wall-clock budget defaults to 5 minutes in P2.
- `report_uri` accepts only `replay://` or allowlisted runtime-local paths.
- GUI must render report text through `textContent` or equivalent safe rendering.

---

## 6. Replay Runner Contract

### P2 Runner

P2 may use existing Rust replay mode, with strict labeling:

- data tier: S2 or S3 only
- execution confidence: `none`
- output: canary / smoke report only
- no MLDE advisory write
- no DreamEngine proposal write
- no `demo_candidate`
- no live/demo config mutation

This is valid because current Rust replay mode:

- reads JSONL `PriceEvent`
- builds a standalone `TickPipeline`
- registers MA / BB / Grid strategies only
- grants paper auth internally
- forces canary mode
- writes `CanaryRecord`, not real fills
- has no WS, no IPC, no live authorization path

Therefore P2 is useful for developer speed and signal smoke tests, but not enough
for execution-realistic backtesting.

### P3+ Runner

P3+ must not pretend current canary replay is enough. It needs a canonical replay
runner or isolated process that can:

- load exact config bundle
- report binary/config hashes
- produce reproducible report artifacts
- call calibrated execution model
- keep order/fill lifecycle separate from real `trading.fills`
- expose calibrated / pessimistic / optimistic outcomes

---

## 7. Quant / Calibration Contract

Execution calibration starts only after source quality gates pass.

Minimum gates:

| Gate | Requirement |
|---|---|
| attribution | `attribution_chain_ok` health is sufficient for the selected strategy/window |
| OOS | calibration window does not overlap candidate replay window |
| embargo | strategy-specific embargo or minimum 7d embargo for first implementation |
| sample power | low-sample cells are marked insufficient and cannot hand off |
| estimator | q10/q50/q90 must include uncertainty interval |
| shrinkage | use explicit empirical Bayes / hierarchical Bayes / James-Stein method |
| selection bias | candidate search records total candidates and applies PBO / DSR / equivalent gate before demo handoff |

Do not train execution calibration on the same replay window used to choose the
candidate. Do not let replay-generated fills become labels for real-outcome
training views.

---

## 8. Product Surface Plan

### Paper Tab -> Paper Replay Lab

Sub-tabs:

1. Session
2. Replay
3. Compare
4. Handoff

P1 may ship UI scaffolding only if disabled states are explicit:

- "Coming in P2" banner
- data tier explanation
- execution confidence badge
- no grey button that looks actionable
- no manual order submission inside Replay workflow

### Learning Tab

Keep as Learning Cockpit:

- observations
- lessons
- hypotheses
- experiments
- review queue
- replay evidence inbox
- ML/Dream producer monitor

Learning does not run replay. It consumes evidence and producer status.

### Agents Monitor

Move current 5-Agent panel out of Learning after frontend collision risk is lower.

Rules:

- preserve read-only `agents_routes.py` posture
- preserve degraded-safe responses
- preserve `agent-tracker.js` behavior where practical
- add a temporary redirect notice in Learning for 90 days after extraction

P5 should happen after LG-2/3/4 frontend work stabilizes, unless the operator
explicitly prioritizes IA cleanup over LG frontend work.

---

## 9. Phased Delivery

### P0 - Spec Amendment

Deliverables:

- REF-19 v2 amendment
- REF-20 v2 amendment
- this V1 plan accepted as execution baseline

Exit criteria:

- manifest signature contract written
- replay API auth contract written
- replay registry schema written
- MLDE evidence source guard written
- P2/P3/P4/P6 dependency split written

### P1 - Frontend IA Only

Deliverables:

- Paper Tab reorganized as Paper Replay Lab shell
- Session behavior unchanged
- Replay / Compare / Handoff disabled placeholders
- no backend replay routes required yet

Exit criteria:

- existing Paper session UI behavior preserved
- no replay UI order submission path
- disabled states are clear and honest

### P2a - Registry / Auth / Manifest Foundation

Deliverables:

- `replay.experiments`
- `replay.report_artifacts`
- manifest canonicalization
- server-side HMAC signature
- `/api/v1/replay/health`
- `/api/v1/replay/manifests`

Exit criteria:

- `replay_manifest_contract` healthcheck passes
- route auth tests pass
- manifest signature verify test passes

### P2b - Read-Only S2/S3 Smoke Replay

Deliverables:

- isolated replay process wrapper
- run / status / cancel / report routes
- canary JSONL artifact registration
- baseline vs candidate smoke comparison

Exit criteria:

- max concurrent replay = 1
- process PID / output dir isolated from production engine
- `execution_confidence=none`
- no MLDE / Dream / demo handoff output

### P3a - Global Execution Calibration

Deliverables:

- calibration feature spec
- OOS / embargo implementation
- fee model
- maker fill / timeout / latency / adverse selection estimates
- taker slippage q10/q50/q90 with uncertainty

Exit criteria:

- stale or underpowered calibration blocks handoff
- calibrated / pessimistic / optimistic report bands exist

### P3b - Cell-Level Calibration

Deliverables:

- per strategy / symbol / side grouping where sample power permits
- hierarchical or empirical shrinkage
- S1 recorder dependency tracked separately

Exit criteria:

- low-sample cells marked insufficient
- no ad-hoc shrinkage

### P4 - MLDE / Dream Advisory

Deliverables:

- DreamEngine can propose replay parameter candidates
- MLDE can rank / veto replay candidates
- rows are source-guarded and registry-backed

Exit criteria:

- no replay-derived advisory row without `replay_experiment_id`
- applier ignores unverified replay-derived rows
- total candidates explored recorded

### P5 - Agents Monitor Extraction

Deliverables:

- 5-Agent dashboard moved out of Learning
- Learning redirect notice
- Agents Monitor remains read-only

Exit criteria:

- existing 5-Agent API behavior preserved
- Learning no longer carries operational 5-Agent visual weight

### P6 - Bounded Demo Handoff

Deliverables:

- `/api/v1/replay/candidates` enabled for `demo_candidate`
- typed confirmation modal
- applier source guard and manifest verification
- existing parameter bound validation reused

Exit criteria:

- replay cannot approve live
- demo handoff is audited, bounded, idempotent, reversible
- live/live_demo remains GovernanceHub + Decision Lease + live gates only

---

## 10. Acceptance Checks

| Check | Phase | Requirement |
|---|---|---|
| `replay_manifest_contract` | P2a | manifest has git/config/runtime hashes, signature, output policy |
| `replay_route_auth_contract` | P2a | all replay routes enforce role/scope/idempotency where required |
| `replay_registry_fk_contract` | P2a | report artifacts reference existing experiments |
| `replay_resource_isolation` | P2b | replay process/output/DB pool cannot starve production engine |
| `replay_execution_confidence_label` | P2b | S2/S3 smoke reports say execution confidence none |
| `replay_no_live_mutation` | all | replay cannot write `trading.fills` or mutate live/live_demo configs |
| `mlde_replay_source_guard` | P4 | replay-derived recommendations require registry-backed evidence fields |
| `execution_calibration_freshness` | P3 | stale calibration blocks actionable handoff |
| `execution_calibration_power` | P3 | insufficient cells cannot hand off |
| `replay_cv_protocol` | P4/P6 | multiple-candidate selection bias controlled before demo handoff |
| `paper_replay_lab_no_order_submit` | P1+ | Replay workflow exposes no manual/live order submit |
| `learning_monitor_read_only` | P4+ | ML/Dream producer monitor is read-only |
| `agents_monitor_read_only` | P5 | extracted Agents Monitor stays read-only and degraded-safe |
| `replay_handoff_typed_confirm` | P6 | demo handoff requires typed confirmation and idempotency key |

---

## 11. Immediate Next Work

Recommended next checkpoint:

1. Draft REF-19 v2 / REF-20 v2 amendments from this V1 plan.
2. Add replay registry migration design.
3. Add replay route auth and manifest signature test plan.
4. Run a narrow indicator / feature leakage audit before enabling calibration.
5. Implement P1 Paper Replay Lab frontend IA only after amendment acceptance.

PM sign-off: **CONDITIONAL APPROVE FOR PLANNING**. Implementation remains blocked
until P0 amendment + P2a contracts are landed.

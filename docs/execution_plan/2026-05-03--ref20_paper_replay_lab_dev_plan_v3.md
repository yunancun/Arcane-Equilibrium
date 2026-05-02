# REF-20 Paper Replay Lab 開發方案 V3

**日期：** 2026-05-03
**狀態：** P0 commit-ready implementation baseline
**Owner：** PM
**上游契約：** REF-19 / REF-20
**配套 UX 文件：** `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`（強制依賴）
**審查歷史：** v0.1 / V1 / Round 2 audit / V2 / Round 3 audit / V2.1 Round 3 / UX subdoc V1
**取代：** V2.1 Round3（保留為審查歷史；實作以本文件為準）

---

## 0. V3 與 V2.1 Round 3 的差異

V2.1 Round3 已實質滿足 Round 3 audit 12 條必補。V3 不重做設計，僅補完三輪 audit 中被「PM 同意但仍偏文字化」的最後幾個工程坑：

| 新增章節 | 補的是哪一條 | 來源 |
|---|---|---|
| §6.4 Baseline Snapshot 機制 | CC N-2 跨環境 baseline；FA #1 baseline ambiguity | CC R3 / FA R3 / PA R3 §六 |
| §8.4 ML Maturity 評級表 | MIT R3 #7「P6 ≠ Production」防誤讀 | MIT R3 |
| §10 Happy Path 業務 flow | FA R3 #3「E1 接手寫不出端到端業務鏈」 | FA R3 |
| §11 Phase 業務 KPI | FA R3 #5「phase exit 缺業務驗收」 | FA R3 |
| §12 acceptance #20 `replay_routes_use_safe_query_pattern` | MIT R3 §6 agents_routes degraded posture mirror | MIT R3 |
| §3 Round 3 P0 Hard Gates 收斂為 12 條獨立 gate | 整合 12 條 R3 必補 | All |

V2.1 Round3 既有的 §1–§12 內容全部繼承，措辭優化但不改 contract 邊界。

---

## 1. PM 判定

REF-20 經過三輪 7-agent 對抗審查後，工程契約已收斂至 P0 commit-ready 狀態。剩餘風險（business KPI、跨環境 baseline、ML maturity 防誤讀、safe_query mirror）以本文件第 §6.4 / §8.4 / §10 / §11 / §12 補完。

**核心方向（穩定）**：

- Paper Tab 升級為 Paper Replay Lab。
- Learning 保持知識 cockpit，新增 replay evidence inbox + ML/Dream producer monitor。
- 5-Agent 抽出 Agents Monitor，等 LG-2/3/4 frontend merged + 7d stable。
- P3+ canonical replay 走 dedicated Rust binary `replay_runner`。
- P2 isolated smoke replay 走 `ReplayProfile::Isolated`，使用同一 decision/risk hot path 但 fail-closed。
- Mac 可跑 S2 public + S3 synthetic smoke，不可寫 registry/advisory，產出非 actionable。
- Replay 不替代 demo / live_demo 驗證；它加速壞參數淘汰。

**Round 3 三條 PM 反對的 audit 改寫**（V2.1 已立論，V3 不變）：

1. P2/P2b 不禁 `TickPipeline` / `IntentProcessor`，改用 `ReplayProfile::Isolated` no-write profile + fail-closed。
2. Mac 不全面禁止 S2 public data；只禁讀 S0/S1 私有 + 寫 registry/advisory。
3. `nm` / `objdump` symbol grep 為 defense-in-depth，runtime + unit test 為 authoritative。

---

## 2. Non-Negotiable Boundaries

1. Replay never submits live orders.
2. Replay never writes simulated rows to `trading.fills`.
3. Replay never inserts simulated labels into `learning.mlde_edge_training_rows`.
4. Replay-derived MLDE/Dream rows are advisory only and must be registry-backed.
5. Live/live_demo mutation remains GovernanceHub + Decision Lease + live gates.
6. Demo handoff remains bounded, audited, reversible, routed through existing MLDE demo applier guards.
7. P2 smoke replay cannot emit `demo_candidate`, `live_candidate_research_only`, or `live_approved`.
8. P3+ calibration cannot train on the same window used to select a candidate.
9. Any actionable candidate must be reproducible from signed manifest + registry artifacts + Linux runtime binary sha.
10. Paper Replay Lab UI must show run mode, data tier, runtime environment, and execution confidence before any result is interpreted.
11. Mac dev smoke is non-actionable by definition.
12. MLDE / DreamEngine are called by Replay as advisory participants; they are not rewritten into replay-only tools.
13. Replay routes mirror `agents_routes.py` PG-degraded-safe pattern; Replay subsystem outage cannot return 5xx and must degrade to 200 + status payload.

---

## 3. P0 Commit Hard Gates

These items block P0 amendment commit and any runtime implementation PR depending on REF-20.

| Gate | Requirement | Blocking phase |
|---|---|---|
| **G1 schema windows** | `replay.experiments` has physical calibration / OOS / candidate window columns + `total_candidates_K` + `oos_embargo_seconds` | P2a / P3a |
| **G2 lineage columns** | `parent_experiment_id`, `intent_id`, `decision_lease_id`, `idempotency_key`, `engine_binary_sha` nullable rule | P2a / P2b |
| **G3 MLDE retrofit** | backfill allowlist, ambiguous rows policy, migration report table, owner, healthcheck | P2a / P4 |
| **G4 DB role guard** | DB-level insert path for replay-derived advisory rows; no ad hoc INSERT | P2a / P4 |
| **G5 migration governance** | PM V### reservation + Guard A/B/C templates in PR/commit | P0 |
| **G6 indicator sweep** | 5-strategy indicator leak-free audit before P2 runner | P2 |
| **G7 runner decision** | dedicated Rust binary `replay_runner` chosen and wired before implementation | P0 / P2 |
| **G8 fail-closed isolation** | forbidden P2 wiring aborts immediately and logs reason; logging-only failure rejected | P2 |
| **G9 manifest quotas** | 30d TTL, per-actor active cap=20, global active run=1, key retention 180d max | P2a |
| **G10 UX subdoc** | dedicated `ref20_ux_subdoc_v1.md` accepted before P1 | P1 |
| **G11 Mac policy** | Mac writes no registry/advisory; produces no actionable result; `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` enforced | P2 |
| **G12 quant patches** | embargo `max(7d, 2 * signal_half_life)`, shrinkage decision tree, regime warmup 500 fills, cost_edge_ratio gate | P3+ |
| **G13 baseline snapshot** | snapshot mechanism specified (§6.4); Mac vs Linux trace path documented | P2a |
| **G14 safe_query mirror** | replay routes mirror `agents_routes.py` PG-degraded-safe pattern | P2a |
| **G15 ML maturity transparency** | per-phase maturity rating displayed in UI / docs (Foundation → Production); P6 ≠ Production | P0 / P5 |

---

## 4. Schema Contract

### 4.1 Replay Registry

Migrations land via PM-reserved V### numbers. Logical migration order:

1. replay registry tables + signing fields
2. MLDE evidence source columns + backfill + healthcheck
3. simulated fill artifacts + lineage columns

`replay.experiments` minimum:

| Column | Contract |
|---|---|
| `experiment_id` | primary external id |
| `parent_experiment_id` | nullable self-reference for baseline vs candidate lineage |
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
| `calibration_train_window_start` / `_end` | physical timestamptz |
| `oos_label_window_start` / `_end` | physical timestamptz |
| `candidate_window_start` / `_end` | physical timestamptz |
| `oos_embargo_seconds` | physical integer; computed `max(7d, 2 * signal_half_life)` |
| `total_candidates_K` | physical integer; required for DSR/PBO accounting |
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
5. SQL must enforce what SQL can enforce directly. If implementation uses `tstzrange` / `EXCLUDE USING gist`, the migration must include `btree_gist` extension when needed and pass Guard A/B/C.

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
| `execution_model_version` | nullable in P2; required in P3+ |
| `ci_low_bps` / `ci_mid_bps` / `ci_high_bps` | nullable; aggregate-level CI link allowed |
| `payload` | JSONB details |

No replay table may be read by existing live/demo metric code unless explicitly wired through replay routes.

### 4.2 MLDE Evidence Source Guard

Add columns to `learning.mlde_shadow_recommendations`:

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

Migration preflight:

1. `SELECT DISTINCT source FROM learning.mlde_shadow_recommendations` and attach to migration report.
2. Any source outside allowlist must be explicitly classified by PM before Guard B.
3. Ambiguous rows (`source NOT IN allowlist OR source IS NULL`) are written to migration report table; healthcheck blocks until classified or excluded.

Required migration report table `replay.evidence_tier_backfill_report`:

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

DB write permission target posture:

1. Implementation must inspect current grants before changing permissions.
2. Direct ad hoc INSERT of replay-derived evidence is forbidden.
3. Replay-derived advisory rows must go through verified insert function (checks replay registry FK + manifest hash + source tier + output policy).
4. `REVOKE INSERT FROM PUBLIC` + role-based `GRANT EXECUTE` is the target; final SQL must preserve legitimate existing producers writing `real_outcome`.

Required healthchecks:

- `check_evidence_source_tier_completeness`
- `mlde_replay_source_guard`
- `replay_shadow_sink_boundary`
- `replay_registry_fk_contract`
- `replay_routes_use_safe_query_pattern`

---

## 5. Manifest, Quota, Retention

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
| audit | distinguish `signature_mismatch`, `manifest_hash_mismatch`, `key_missing`, `key_expired` |

Resource limits:

| Limit | Value |
|---|---|
| manifest TTL | 30 days default |
| per-actor active manifests | 20 |
| per-actor active runs | 1 |
| global active runs | 1 in P2/P3 |
| artifact storage cap | implementation defines env-specific cap before P2a merge |
| prune job | required before sustained P2 usage |

Canonical manifest must include git sha, engine binary sha, strategy/risk config hashes, runtime environment, symbol list, timeframe, data tier, source mix expectation, calibration train window, OOS label window, candidate window, total candidates explored, selection-bias correction metadata, fee model, execution confidence, output policy, expiry.

---

## 6. Replay Runner Contract

### 6.1 Canonical Implementation Choice

P3+ and durable P2 execution use a dedicated Rust binary target named `replay_runner`.

May share internal strategy / risk / `TickPipeline` / `IntentProcessor` modules, but MUST NOT share live process bootstrap, IPC, exchange dispatch, DB writer channels, or Decision Lease acquisition wiring.

### 6.2 P2 Isolated Smoke Runner

P2 uses `TickPipeline` and `IntentProcessor` only under `ReplayProfile::Isolated`.

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
- `demo_candidate`, `live_candidate_research_only`, `live_approved`

Fail-closed behavior:

- Any forbidden path detected at startup aborts before replay begins.
- Any forbidden path detected during replay aborts the run, records failed status where allowed, emits non-actionable diagnostic.
- Logging-only failure is not accepted.

Acceptance checks:

- `ReplayProfile::Isolated` is required for P2.
- no `acquire_lease` path called.
- `trading_tx`, `market_data_tx`, `feature_tx`, `context_tx`, `decision_feature_tx`, `order_dispatch_tx` not wired.
- no exchange/API credential loaded by runner.
- no DB DSN required by runner itself for P2 dry-run execution.
- output has `execution_confidence='none'`.
- optional `nm` / `objdump` symbol grep as defense-in-depth; runtime + unit tests authoritative.

### 6.3 Mac Policy

1. May run S2 public-data smoke and S3 synthetic smoke.
2. Must not read S0/S1 private runtime data, `trading.fills`, `learning.exit_features`, demo/live_demo fills, local private orderbook captures.
3. Must not write replay registry, MLDE/Dream advisory rows, or handoff candidates.
4. Must produce dry-run console / local artifact output only.
5. Must mark `runtime_environment='mac_dev_smoke_test_only'`, `engine_binary_sha=NULL`, `execution_confidence='none'`.
6. Any actionable interpretation requires Linux rerun on `linux_trade_core`.
7. `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` is the default; Mac fails closed if S0/S1/private access attempted.

### 6.4 Baseline Snapshot Mechanism（V3 新增）

Baseline = same-strategy production-active config snapshot at `experiment_start_ts`.

Linux `linux_trade_core` baseline capture:

1. `replay_runner` reads strategy/risk active config from runtime ConfigManager export.
2. Computes `strategy_config_sha256` + `risk_config_sha256` from canonical TOML representation.
3. Captures active strategy whitelist via `SELECT FROM strategy.active_registry`.
4. Persists snapshot pointer to `replay.experiments.baseline_snapshot_jsonb` (manifest_jsonb subset).

Mac `mac_dev_smoke_test_only` baseline capture:

1. May NOT pull live snapshot from Linux runtime DB.
2. Must use one of:
   - locally checked-in `srv/research_notes/replay_fixtures/<date>_demo_baseline.toml` fixture (PM-curated, sha-pinned)
   - explicit operator-provided baseline patch via UI
3. Snapshot pointer must mark `baseline_source='mac_fixture'` to surface non-portable result.
4. Any candidate report whose baseline came from Mac fixture is automatically flagged non-actionable.

Cross-environment reproducibility rule:

- Mac smoke result with Linux fixture sha → may inform exploration; not actionable.
- Linux runtime baseline snapshot sha → required for actionable demo handoff.
- Manifest must record both `baseline_source` and `engine_binary_sha`; mismatch → verdict downgraded to `defer_data`.

---

## 7. P2 Precondition: Indicator Leak-Free Sweep

Before P2 runner implementation starts, QC + E3 jointly own indicator leak-free sweep across currently wired 5 strategies.

Required output:

| Field | Requirement |
|---|---|
| strategy inventory | generated from runtime registration, not manually guessed |
| indicator list | every rolling/lagged feature used by each strategy |
| shift compliance | `indicator x shift(1)` or equivalent no-lookahead proof |
| fixture | at least one deterministic replay window per strategy |
| verdict | pass / retract / fix-required |

Lookahead-leakage retraction rules:

1. Retract from replay eligibility immediately.
2. P2 may proceed only if leaking strategy excluded and exclusion is explicit in manifest/report.
3. If strategy is part of baseline comparison set, P2 blocked until fixed.

Rationale: replay invalidates itself if strategy indicators see future bars. This is not a claim that a leak currently exists; it is a precondition gate.

---

## 8. Quant and Calibration Patches

P3+ blocked until numeric gates implemented.

### 8.1 Sample, Freshness, Embargo

| Gate | Requirement |
|---|---|
| attribution completeness | `attribution_chain_ok_ratio >= 0.70` over calibration OOS label window |
| strategy-window sample | `n >= 200` fills per strategy-window for global calibration |
| cell sample | `n >= 30` per strategy/symbol/side cell |
| stale calibration | model age <= 72h for actionable handoff |
| OOS embargo | `max(7d, 2 * signal_half_life)` per strategy |
| DSR | `DSR(K) > 0.95` for promotion-oriented reports |
| PBO | `PBO < 0.5` when K >= 10 and CSCV has sufficient splits (total trades >= 320) |
| cost gate | `cost_edge_ratio >= 0.8` for LLM/ML assisted candidate loops |

Insufficient power → verdict `defer_data` (not `demo_candidate`).

Half-life estimation:

- Per strategy fit `PnL_t = PnL_0 * exp(-lambda * t)` on cell-level realized edge.
- Half-life = `ln(2) / lambda`.
- Half-life unmeasured → conservative default 14d.

### 8.2 Quantile and Shrinkage

q10 / q50 / q90:

- block bootstrap, Politis-Romano style, 1000 iterations
- preserve autocorrelation
- output 95% CI
- n<30 fallback parametric only if marked `low_confidence` and blocked from handoff

Shrinkage decision tree:

1. cell `n < 30`: report low confidence; block handoff.
2. small cell + enough related cells: hierarchical Bayes preferred.
3. cross-strategy global estimate: James-Stein allowed.
4. small-K candidate comparison: empirical Bayes allowed.
5. method must be declared in manifest/report; ad hoc shrinkage forbidden.

### 8.3 Selection Bias Controls

- `total_candidates_K` mandatory in manifest.
- DSR(K) > 0.95 for promotion.
- PBO < 0.5 when K >= 10 and total trades >= 320.
- if PBO cannot run because power insufficient → verdict `defer_data`, not `demo_candidate`.
- no generic "equivalent gate" fallback.

### 8.4 Regime Controls

1. **Warmup**: First 500 fills after a negative-edge regime transition cannot drive handoff (prevents permanent CUSUM freeze in current 5-strategy negative-edge environment).
2. **CUSUM**: realized edge per cell freezes actionable handoff (not calibration model itself) on +/- 3 sigma break.
3. **Kupiec POF**: per (strategy, symbol) cell when n >= 250 fills; cell n < 250 skipped (do not borrow PBO sample).
4. **PSR(0)**: < 0.95 across 3 consecutive 250-fill windows triggers refit recommendation + PM alert.

---

## 9. Product / UX Contract

The dedicated UX subdoc `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md` is mandatory and authoritative for UI/UX decisions. It specifies sub-tab IA, Mode Badges, Disabled State Contract, Terminology mapping, Accessibility, and P1 Acceptance.

P1 frontend work blocked until UX subdoc accepted.

V3-level core constraints (UI subdoc 是 SoT):

1. Paper Tab → Paper Replay Lab with Session / Replay / Compare / Handoff sub-tabs.
2. Replay workflow exposes no order submit/cancel controls.
3. Existing manual paper submit/cancel removed from Paper Replay Lab P1 unless operator explicitly creates separate legacy-only dev surface.
4. Disabled states phase-labelled.
5. Mode badges show session/replay mode + data tier + execution confidence + runtime environment.
6. `execution_confidence='none'` visually non-actionable.
7. Handoff disabled until P6; typed confirmation required.
8. Learning is knowledge cockpit; does not run replay.
9. Agents Monitor extraction waits LG-2/3/4 frontend merged + 7d stable.

---

## 10. Happy Path Business Flow（V3 新增）

### 10.1 Operator 端到端流程（P2 Smoke / 12-step）

```
Step 1  Operator opens Paper Replay Lab → Replay sub-tab
Step 2  Selects symbol set, timeframe, data tier (S2 or S3), market data window
Step 3  Picks baseline = current active demo snapshot (auto-filled by §6.4)
Step 4  Picks candidate = explicit config patch / git snapshot
Step 5  POST /api/v1/replay/manifests
        - server canonicalizes manifest
        - server signs HMAC-SHA256
        - server validates window non-overlap (SQL EXCLUDE)
        - server validates timeframe enum + data_tier
        - server checks per-actor active manifest cap (20)
        - returns experiment_id + manifest_hash + signature_key_ref
Step 6  POST /api/v1/replay/runs {experiment_id}
        - server checks global active run cap (1)
        - spawns isolated `replay_runner` process with ReplayProfile::Isolated
        - runner verifies signature first, hash second, fail-closed on mismatch
        - runner verifies §7 indicator leak-free sweep status (pass/exclusion)
        - runner runs TickPipeline + IntentProcessor in-memory
        - writes diagnostic artifacts to allowlisted local path
        - registers artifacts via replay_routes (DB write through verified function)
Step 7  Operator monitors GET /api/v1/replay/runs/{id} (60/min)
Step 8  Run completes; status → completed; experiment.expires_at set TTL=30d
Step 9  Operator views Compare sub-tab: baseline vs candidate
        - 12 metrics rendered (net bps, q10/q50/q90, max DD, ...)
        - 4 mode badges visible
        - verdict label one of: reject / defer_data / defer_calibration / research_only
Step 10 Operator interprets result; verdict NEVER `demo_candidate` or `live_approved` in P2
Step 11 If actionable interest → Operator triggers Linux rerun (Mac case) or proceeds to next phase
Step 12 Artifacts auto-prune at expires_at
```

### 10.2 Verdict 流轉表

| Verdict | 何時產生 | 下游動作 |
|---|---|---|
| `reject` | candidate worse than baseline / safety gate fail | 結束；evidence inbox 留證據 |
| `defer_data` | sample / power 不足 / attribution < 0.7 | 結束；建議延長 demo 累積期 |
| `defer_calibration` | calibration stale > 72h / regime frozen | 結束；觸發 calibration refit pipeline |
| `research_only` | passed methodology gates 但未到 demo handoff bar | Learning evidence inbox 留證據 |
| `demo_candidate` | passed all P3+P4+P6 gates | P6 typed confirm → MLDE demo applier |

P2 phase only emits `reject` / `defer_data` (data tier gate). `defer_calibration` / `research_only` need P3+. `demo_candidate` needs P6.

### 10.3 Failure Modes

| Failure | Step | Behavior |
|---|---|---|
| signature mismatch | Step 6 | abort run; audit `signature_mismatch`; status=failed |
| hash mismatch | Step 6 | abort run; audit `manifest_hash_mismatch`; status=failed |
| window overlap detected | Step 5 | reject manifest with HTTP 400 |
| forbidden path attempted | Step 6 | abort run immediately (NOT log-only); status=failed; reason recorded |
| PG outage | Step 5/7 | route returns 200 + `{status: degraded, reason: pg_unavailable}` (mirror agents_routes) |
| Mac attempts S0/S1 read | Step 6 | runner fails closed via `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` |
| concurrent run cap hit | Step 6 | HTTP 429 with current active experiment_id |
| TTL expired | Step 7+ | artifact removed; query returns 404 with reason `expired` |

---

## 11. Phased Delivery

Each phase includes Deliverables, Exit, and **Business KPI**（V3 新增）.

### P0 - Amendments and Gates

Deliverables:
- REF-19 v2 amendment
- REF-20 v2 amendment
- V3 baseline acceptance
- UX subdoc v1 acceptance
- migration reservation plan
- Guard A/B/C templates attached
- indicator leak-free sweep task assigned (QC+E3)
- baseline snapshot mechanism §6.4 reviewed
- runtime feature flag `replay_isolated` design reviewed (PA + E1)

Exit:
- docs-only sign-off
- no runtime changes
- no DB migration yet

**Business KPI**: P0 commit lands within 1 sprint of V3 acceptance; 0 runtime regressions.

### P1 - Paper Replay Lab IA

Deliverables:
- Paper Tab shell reorganized into Session / Replay / Compare / Handoff sub-tabs
- manual submit/cancel removed from Replay Lab surface
- honest disabled states + mode badges
- existing Paper session display regression passes

Exit:
- `paper_replay_lab_no_order_submit` passes for Replay workflow and Paper Replay Lab shell.

**Business KPI**: 0 Paper session regressions in 7d post-deploy; UX subdoc 8 mode badges all rendering.

### P2a - Registry / Auth / Manifest Foundation

Deliverables:
- `replay.experiments` (with §4.1 physical window columns)
- `replay.report_artifacts`
- `replay.evidence_tier_backfill_report`
- manifest canonicalization + HMAC signature
- route auth scaffolding (8 routes with Auth/Scope/Idempotency/Limit)
- `evidence_source_tier` migration + backfill + healthcheck
- manifest quota / TTL / prune path
- `replay_routes_use_safe_query_pattern` mirror

Exit:
- Guard A/B/C pass on all migrations
- route auth tests pass
- manifest signature verify tests pass
- evidence source healthcheck green
- `check_evidence_source_tier_completeness` green
- `replay_routes_use_safe_query_pattern` green
- migration report all rows classified

**Business KPI**: 0 dangling FK / 0 NULL `evidence_source_tier`; PG outage simulation → routes degrade not 5xx.

### P2b - Read-Only S2/S3 Smoke Replay

Deliverables:
- `replay_runner` Rust binary with `ReplayProfile::Isolated`
- run/status/cancel/report routes wired
- canary/diagnostic artifacts registered on Linux only
- baseline vs candidate smoke comparison rendering
- Mac smoke path with `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` enforced

Exit:
- no DB writer channels wired in runner
- no exchange/IPC/WS/live auth path
- no advisory/handoff output
- `execution_confidence='none'` always emitted
- forbidden-path-fail-closed unit + runtime tests pass

**Business KPI**: 5+ operator-driven baseline-vs-candidate runs / week; mean run time <5min; 0 Decision Lease acquisitions detected.

### P3a - Global Execution Calibration

Deliverables:
- S0-only calibration labels (post FUP-2 attribution writer deploy)
- OOS embargo (`max(7d, 2 * half_life)`)
- fee model
- maker/taker execution estimates
- bootstrap CI + shrinkage method declaration

Exit:
- attribution >= 0.70 over calibration OOS window
- n >= 200 per strategy-window
- stale <= 72h
- actionable handoff still disabled until P4/P6 guards

**Business KPI**: Calibration coverage ≥3 strategies × ≥10 symbols; q10/q50/q90 CI 95% spans visibly tighter than naive empirical quantile.

### P3b - Cell-Level Calibration

Deliverables:
- strategy/symbol/side cell calibration
- n>=30 cell gate
- hierarchical/empirical shrinkage
- S1 recorder dependency tracked separately (REF-21 future spec)

Exit:
- insufficient cells blocked from handoff
- regime shift controls present (CUSUM + Kupiec + PSR + warmup)

**Business KPI**: per-cell calibration green covers ≥40% (strategy × symbol × side) cells with n≥30 within 30d S0 accumulation.

### P4 - MLDE / Dream Advisory

Deliverables:
- DreamEngine proposes replay candidates
- MLDE ranks/vetoes replay candidates
- source-guarded advisory rows (verified insert function)
- PBO / DSR metadata captured per manifest

Exit:
- every replay-derived row references replay registry
- `mlde_demo_applier` ignores unverified replay-derived rows
- no demo mutation yet unless P6 enabled

**Business KPI**: ≥10 advisory rows / week; 0 unverified rows reach applier; PBO-fail rejection rate visible.

### P5 - Agents Monitor Extraction

Entry:
- LG-2/3/4 frontend merged
- 7d frontend stable

Deliverables:
- 5-Agent panel moved out of Learning to dedicated Agents Monitor surface
- Learning redirect notice (90d)
- Agents Monitor read-only route behavior preserved

Exit:
- existing 5-Agent API behavior preserved
- Learning no longer carries operational 5-Agent visual weight

**Business KPI**: 0 agent monitor regressions; redirect click-through ≥80% in first 7d.

### P6 - Bounded Demo A/B Handoff

Deliverables:
- `/api/v1/replay/candidates` enabled for `demo_candidate`
- typed confirmation modal (UX subdoc §6)
- applier source guard via verified insert function
- bound validation
- audit row in `learning.governance_audit_log`

Exit:
- demo handoff is bounded, idempotent, reversible
- live/live_demo still requires GovernanceHub + Decision Lease + live gates
- replay cannot emit `live_approved`

**Business KPI**: ≥1 demo handoff / week with operator typed confirmation; 0 live mutation events; 14d gradient 0 incident.

---

## 12. Acceptance Checks

| # | Check | Phase | Requirement |
|---|---|---|---|
| 1 | `replay_manifest_contract` | P2a | signed manifest, hash, timeframe enum, data tier, output policy, physical windows |
| 2 | `replay_signature_verify` | P2a | signature verified before hash; fail-closed |
| 3 | `replay_route_auth_contract` | P2a | route role/scope/idempotency/rate tests |
| 4 | `replay_manifest_quota_guard` | P2a | TTL, active caps, storage cap |
| 5 | `check_evidence_source_tier_completeness` | P2a | no NULL/invalid evidence tier |
| 6 | `mlde_replay_source_guard` | P2a/P4 | replay-derived advisory rows require registry FK + manifest hash |
| 7 | `replay_registry_fk_contract` | P2a | report artifacts + simulated fills reference experiments |
| 8 | `replay_resource_isolation` | P2b | no IPC/WS/exchange/DB writer channels |
| 9 | `replay_no_decision_lease_acquire` | P2b | smoke replay does not call `acquire_lease` |
| 10 | `replay_forbidden_wiring_fail_closed` | P2b | forbidden path aborts run, not log-only |
| 11 | `replay_execution_confidence_label` | P2b | S2/S3 smoke reports say execution confidence none |
| 12 | `replay_mac_non_actionable` | P2b | Mac dry-run cannot write registry/advisory |
| 13 | `strategy_indicator_leak_free` | P2 | 5-strategy sweep passed or explicit exclusion exists |
| 14 | `replay_no_live_mutation` | all | no live/demo config mutation or live orders |
| 15 | `execution_calibration_freshness` | P3 | model age <=72h for handoff |
| 16 | `execution_calibration_power` | P3 | n thresholds enforced (n>=200 strategy / n>=30 cell) |
| 17 | `replay_cv_protocol` | P4/P6 | DSR(K)>0.95 + PBO<0.5 (K>=10) + power gate enforced |
| 18 | `replay_regime_shift_gate` | P3+ | frozen regime + warmup phase block actionable candidates |
| 19 | `paper_replay_lab_no_order_submit` | P1+ | Replay Lab has no submit/cancel controls |
| 20 | `replay_handoff_typed_confirm` | P6 | typed confirmation + idempotency required |
| 21 | `agents_monitor_read_only` | P5 | extracted Agents Monitor remains read-only |
| 22 | **`replay_routes_use_safe_query_pattern`** | P2a | replay routes mirror `agents_routes.py` PG-degraded-safe pattern (V3 新增) |
| 23 | **`replay_baseline_snapshot_provenance`** | P2a | manifest records `baseline_source` + `engine_binary_sha`; mismatch downgrades verdict (V3 新增) |
| 24 | **`replay_cost_edge_ratio_gate`** | P3+ | LLM/ML assisted candidate loops respect `cost_edge_ratio >= 0.8` (V3 新增, CC #13) |
| 25 | **`replay_ml_maturity_label`** | P0 / P5 | each phase output / UI surfaces ML-pipeline maturity stage; P6 ≠ Production (V3 新增) |

---

## 13. ML Pipeline Maturity Mapping（V3 新增）

Per `ml-pipeline-maturity-audit` 5-stage × 4-dimension framework. Surfaces explicitly to avoid "P6 deploy = production" misread.

| Phase | writer-spawn | consumer | row-accumulation | decision-impact | Stage |
|---|---|---|---|---|---|
| P0 | docs only | none | none | none | Pre-Foundation |
| P1 | docs only | none | none | none | Pre-Foundation |
| P2a | replay routes / manifest writer | none | manifest rows | none | **Foundation** |
| P2b | + isolated runner writes report_artifacts | report viewer GUI | + report rows | none (`execution_confidence='none'`) | **Foundation → Skeleton** |
| P3a | + global calibration writer | calibration reader | + calibration rows | none (handoff still disabled) | **Skeleton** |
| P3b | + cell-level calibration writer | + cell calibration reader | + cell calibration rows | none | **Skeleton** |
| P4 | + replay-derived MLDE/Dream advisory writer (verified function) | mlde_demo_applier reads but rejects unverified | + advisory rows | 0 (applier reject path active) | **Skeleton → Shadow** |
| P5 | (no new writer) | Agents Monitor extracted | (no change) | none | **Shadow** |
| P6 | + demo_candidate handoff writer | demo applier accepts after typed confirm | + handoff rows | demo positions indirectly | **Shadow → Canary** |

**Important**: P6 deploy ≠ Production. Production stage requires real live decision impact, which REF-20 explicitly never reaches (Replay never approves live). UI / docs / phase exit reports must surface stage label to operator.

---

## 14. Round-3 Audit 12 Must-Fix 解決狀態

| # | Round 3 必補 | V3 章節 | 狀態 |
|---|---|---|---|
| R3-1 | manifest_jsonb 升級為物理 column | §4.1 | ✅ |
| R3-2 | mlde_shadow_recommendations retrofit SQL | §4.2 + migration report 表 | ✅ |
| R3-3 | schema 缺 4 個關鍵物理欄位 | §4.1 + §4.1 simulated_fills | ✅ |
| R3-4 | DB 寫權限收斂硬化 | §4.2 DB write permission target posture | ✅ |
| R3-5 | V### 治理 PM 集中分配 + Guard A/B/C | §3 G5 + §4 開頭 | ✅ |
| R3-6 | 5 策略 indicator leak-free sweep 為 P2 前置 | §3 G6 + §7 | ✅ |
| PA 三選一 → new binary | §6.1 | ✅ |
| PA IntentProcessor cfg gate | §6.2 + §3 G7 | ✅ |
| CC N-4 fail-closed | §6.2 fail-closed behavior | ✅ |
| E3 HIGH-04 quota | §5 resource limits | ✅ |
| A3 dedicated UX subdoc | §9 + 配套 UX subdoc V1 | ✅ |
| E3 NEW-01 Mac env var | §6.3 | ✅ |

**V3 額外補完**（Round 3 audit 提出但 V2.1 Round3 未閉合）：

| # | Audit 來源 | V3 章節 | 狀態 |
|---|---|---|---|
| CC N-2 cross-env baseline | §6.4 Baseline Snapshot Mechanism | ✅ |
| CC N-5 cost_edge_ratio gate | §8.1 + §12 #24 | ✅ |
| FA #3 happy path business flow | §10 | ✅ |
| FA #5 phase exit business KPI | §11 (every phase) | ✅ |
| MIT R3 #6 safe_query mirror | §12 #22 | ✅ |
| MIT R3 #7 ML maturity table | §13 + §12 #25 | ✅ |

---

## 15. Immediate Next Work

1. Land V3 + UX subdoc V1 as P0 amendment baseline (docs-only commit).
2. Reserve migration V### through PM before touching SQL.
3. Assign QC + E3 indicator leak-free sweep (G6).
4. PA + E1 design `replay_runner` Rust binary scaffold + `ReplayProfile::Isolated` cfg gate (G7 + G8).
5. PA + E1a design Baseline Snapshot Mechanism §6.4 implementation (G13).
6. Start P1 only after UX subdoc accepted.
7. Start P2a only after Guard A/B/C plan attached + migration V### reserved.
8. Schedule short 7-agent confirm round (≤300 chars each) on V3 once operator accepts; expected unanimous APPROVE.

---

## 16. PM Sign-off

**APPROVE FOR P0 AMENDMENT COMMIT.**

V3 closes all 12 Round-3 must-fix items plus 6 additional gaps surfaced during V2.1 Round3 review. Runtime implementation may proceed phase-by-phase per §11, gated by §3 hard gates G1–G15 and §12 acceptance checks #1–#25.

Replay never approves live. Replay never writes simulated rows to real-outcome tables. Replay manifest is signed, quota-bounded, and reproducible. Mac smoke is non-actionable by design. P3+ calibration is power-gated, embargo-protected, regime-aware, cost-aware, and bias-corrected. Demo handoff at P6 remains bounded, audited, reversible; live/live_demo mutation continues to require GovernanceHub + Decision Lease + live gates.

V3 is implementation-planning baseline. Subsequent updates follow standard amendment process; do not silently overwrite this file.

---

## 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v0.1 | 2026-05-02 | PM | 7-agent 並行冷酷審查回收後初稿；REF-20 v0.1 REJECT |
| V1 | 2026-05-02 | PM | 接受 v0.1 多項改進；P2 解綁 lease retrofit；evidence_source_tier 命名分離 |
| V2 | 2026-05-02 | PM | 完整 schema + DDL CHECK + manifest HMAC + 5 量化閾值 + regime detector |
| V2.1 Round3 | 2026-05-02 | PM | 12 條 R3 必補；schema 物理 column + DB role guard + dedicated `replay_runner` |
| **V3** | **2026-05-03** | **PM** | **V2.1 Round3 + UX subdoc V1 合成 P0-commit-ready baseline；補 Baseline Snapshot Mechanism / Happy Path / Phase Business KPI / safe_query mirror / ML Maturity Mapping / cost_edge_ratio gate** |

---

## 附錄 A — 配套文件

- UX SoT：`docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`
- 治理上游：`docs/references/2026-05-02--reality_calibrated_fast_replay_governance_zh.md` (REF-19)
- 產品設計上游：`docs/references/2026-05-02--paper_replay_learning_surface_design_zh.md` (REF-20)
- DOC-01：`srv/CLAUDE.md` §二 16 條根原則
- AMD-2026-05-02-01：`docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
- 18 Live Blocker：`srv/CLAUDE.md` §三

## 附錄 B — Audit 軌跡

| 輪次 | 文件 | 主要結論 |
|---|---|---|
| Round 1 | `2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md` | 全 REJECT |
| Round 2 | `2026-05-02--ref20_v1_round2_audit.md` | 5/7 Conditional；2/7 阻塞（MIT 強拒 / A3 P1 拒） |
| Round 3 | `2026-05-02--ref20_v2_round3_audit.md` | 5/7 Conditional Approve；12 條 V2.1 必補 |
| Round 4 (推測) | 待確認 | 預期 7/7 APPROVE V3 |

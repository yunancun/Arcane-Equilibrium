# REF-20 v2 — Paper Replay Lab Governance Amendment

**Status:** REF-20 v2 governance amendment — **supersedes v1 (2026-05-02)**
**Owner:** PM (with PA co-author for §3 / §6 / §11 / §12 amendments)
**Date:** 2026-05-03
**Supersedes:** `docs/references/2026-05-02--paper_replay_learning_surface_design.md` (v1 product surface design, retained as historical baseline)
**Upstream contract:** `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` (V3 baseline)
**UX SoT:** `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md` (V1)
**Indicator sweep verdict:** `docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md` (5/5 PASS, 2026-05-03)
**REF-19 governance partner:** `docs/references/2026-05-03--reality_calibrated_fast_replay_governance_v2.md` (v2)
**Related:** REF-03, REF-04, REF-18, DOC-01 §5.1–§5.16

---

## 0. v2 與 v1 的差異（讀者導讀）

REF-20 v1（2026-05-02）為 product surface design — 描述 Paper Tab → Paper Replay Lab 升級、Learning 維持知識 cockpit、5-Agent 抽出為 Agents Monitor。v1 主要 surface IA + Learning 邊界，**未**鎖死治理層細節。

v2 的職責是把 V3 baseline 確立的工程坑反映進 governance amendment：哪些路徑被禁、哪些路徑必經 verified function、哪些路徑必經 typed confirm、哪些路徑必經 isolated runner。v2 不重做 v1 的 surface IA（凍結 v1 §3–§5），僅補三項整合：

| 整合來源 | v1 缺口 | v2 章節 | 性質 |
|---|---|---|---|
| V3 baseline §6.1（`replay_runner` binary） | v1 沒指定 runner 是 binary 還是 inline service | §3 v2 補丁 + §6 runner contract | **整合，固化既有工程決策** |
| V3 baseline §3 G2/G3/G5（manifest sign + `evidence_source_tier` retrofit + DB role guard 3-PR） | v1 未指定 schema retrofit / sign / role 細節 | §4 v2 schema 補丁 + §5 v2 quota | **整合** |
| V3 baseline §3 G7/G8（`ReplayProfile::Isolated` cfg gate + fail-closed） | v1 未指定 P2 isolation 機制 | §6 v2 runner contract | **整合** |
| V3 baseline §3 G10（UX subdoc binding） | v1 寫了 IA 但沒指定 SoT | §9 UX SoT binding | **新增 SoT 引用** |
| V3 baseline §11 phase exit KPI | v1 沒指定 business KPI | §11 phase exit KPI 補丁 | **整合** |
| V3 baseline §12 acceptance（25 條） | v1 沒指定 acceptance | §12 acceptance binding | **整合** |
| Indicator sweep verdict（2026-05-03） | v1 §6 R0/R1 entry 未明文 G6 satisfied | §13 G6 解封紀錄 | **新增證據紀錄** |
| v1 §6 Manifest schema (12-field) | v1 詳細 12-field schema 在 v2 中濃縮為 §2.2 1 行 | V3 §4.1 / §4.2 + REF-19 v2 §2 #5 + REF-20 v2 §15 (collectively 涵蓋) | **trace path 披露** |

v1 §1–§7 的 surface IA 與 Learning / Agents Monitor 邊界承諾以本文件 §1–§7 重述（措辭微調為與 V3 一致），不改變 v1 surface 邊界。新增章節 §9 / §11 / §12 / §13 為 v2 獨有的整合層。

---

## 1. Purpose（v1 §1 沿用）

REF-19 定義 Reality-Calibrated Fast Replay 的治理邊界。REF-20 定義那個能力**在現有產品表面的位置**，以及它如何連接 Learning / MLDE / DreamEngine / 現有 5-Agent monitor。

立刻的 developer pain 很清楚：每個策略或參數 edit 都要等新 paper / demo 資料。Paper Replay Lab 必須把這個迴路從小時/天壓到分鐘級，做法是用最接近的 runtime path 回放歷史市場條件，**同時誠實報告**執行不確定性、fees、資料來源 tier、calibration freshness。

REF-20 v2 額外補：產品表面現在綁定 V3 工程坑。v2 沒有重做 IA，但鎖定 IA 與工程坑之間的對應關係，讓 P1 frontend / P2 runner / P4 advisory / P6 handoff 之間的契約清晰。

---

## 2. Current System Findings（v1 §2 沿用，要點摘錄）

### 2.1 Paper Tab → Paper Replay Lab

- `tab-paper.html` + `app-paper.js` + `paper_trading_routes.py` + `paper_trading_metrics.py`
- Paper Tab 已是 simulated non-live surface；Python paper engine 已退役；Rust engine 為唯一 paper 引擎。
- 結論：Paper Tab 是升級為 Paper Replay Lab 的正確 surface。**Live Tab 不得**用於 replay。

### 2.2 Learning Tab

- `tab-learning.html` + `app-learning.js` + `learning_legacy_routes.py` + `learning_ops.py` 等
- Learning 是知識 cockpit：observations / lessons / hypotheses / experiments / review queue / net PnL summaries。
- 結論：Learning 維持知識 cockpit，**不**變成 replay runner；可顯示 replay evidence inbox + ML/Dream producer health。

### 2.3 5-Agent Monitor

- `agent-tracker.js` + `agents_routes.py`
- 目前 embed 在 Learning Tab；後端 routes read-only + PG-degraded posture。
- 結論：5-Agent 抽出為 Agents Monitor surface；功能保留；產品邊界改變。

### 2.4 MLDE / DreamEngine（v1 沿用）

繼續 advisory 角色；**不**改 MLDE / DreamEngine 為 replay-only；都經 advisory contract 寫入。

---

## 3. v2 補丁：Sub-Tab IA 鎖定（凍結 v1 §3，UX subdoc V1 為唯一 SoT）

v1 提出 Paper Replay Lab 4 sub-tab；v2 把 IA 鎖定到 UX subdoc V1：

| Sub-tab | Purpose | Actionability | UX SoT |
|---|---|---|---|
| Session | current paper session status + historical paper state | read-only after P1 | UX subdoc V1 §3 |
| Replay | create + monitor non-actionable replay runs | P2+ only | UX subdoc V1 §4 |
| Compare | compare baseline vs candidate reports | non-actionable until P3/P4 gates | UX subdoc V1 §5 |
| Handoff | bounded demo candidate review | disabled until P6 | UX subdoc V1 §6 |

**Frozen contract**：任何 sub-tab IA 改動先改 UX subdoc V1，才 frontend；UX subdoc V1 為唯一 SoT。

**Replay Lab no order submit/cancel**：v2 確認 v1 §3.1 — Replay Lab surface 上**不得**有 manual submit / cancel controls。若 operator debugging 需要，必開獨立 legacy-only dev surface，**不得**與 Replay Lab workflow 混合。

---

## 4. v2 補丁：Schema Contract（承襲 V3 §4）

v1 沒指定 replay schema；v2 鎖定到 V3 §4：

### 4.1 Replay Registry 三表

| Table | 角色 |
|---|---|
| `replay.experiments` | 實驗主表（lineage + windows + manifest + signature + status + TTL） |
| `replay.report_artifacts` | 報告 artifact（summary / canary / comparison / diagnostic / calibration / ux_snapshot） |
| `replay.simulated_fills` | 模擬 fills（FK to experiments + lineage ids + evidence_source_tier） |
| `replay.evidence_tier_backfill_report` | `evidence_source_tier` retrofit migration report |

詳細欄位契約見 V3 §4.1。**v2 不複述**，僅引用 V3。

### 4.2 MLDE Evidence Source Guard

`learning.mlde_shadow_recommendations` 必加 3 columns：

| Column | Requirement |
|---|---|
| `evidence_source_tier` | NOT NULL, default `real_outcome`, CHECK in `(real_outcome, calibrated_replay, synthetic_replay, counterfactual_replay)` |
| `replay_experiment_id` | NULL for `real_outcome`; NOT NULL for replay-derived |
| `manifest_hash` | NULL for `real_outcome`; NOT NULL for replay-derived |

**Insert 路徑硬化**（承襲 REF-19 v2 §8.4）：禁直接 `INSERT INTO learning.mlde_shadow_recommendations`；必經 `verify_replay_evidence_and_insert()` PL/pgSQL function（**SECURITY INVOKER**）。3-PR sequence:

1. PR-1: 建 verified function + GRANT EXECUTE
2. PR-2: 既有 producer 切換到 verified function
3. PR-3: REVOKE INSERT FROM PUBLIC

**禁止**：單 PR 直接 REVOKE — 會 break live demo 寫入路徑。

### 4.3 Migration V### Reservation（V3 §3 G5）

任何 SQL migration 必經 PM 預留 V### number。**禁止**ad-hoc V### claim — 多 sub-agent 並行會撞號。Migration 必含 Guard A/B/C templates（CLAUDE.md §七 強制）。

---

## 5. v2 補丁：Manifest, Quota, Retention（承襲 V3 §5）

| Field | Requirement |
|---|---|
| algorithm | HMAC-SHA256 |
| key path | `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` |
| key separation | 不得與 live `auth_signing_key` 共用 |
| rotation | 90 天目標 |
| key archive retention | 歸檔 keys verify manifests 至多 180 天 |
| signer | 純 server-side |
| client-supplied signature | rejected |
| verification order | 先驗 signature，後驗 manifest hash |
| 4 fail-mode | `signature_mismatch` / `manifest_hash_mismatch` / `key_missing` / `key_expired` 區分 audit |
| manifest TTL | 30 天默認 |
| per-actor active manifests | 20 |
| per-actor active runs | 1 |
| global active runs | 1（P2 / P3 phase） |
| artifact storage cap | implementation 在 P2a merge 前定義 env-specific cap |
| prune job | 持續 P2 使用前 required |

Canonical manifest 必含：git sha / engine binary sha（NULL for Mac）/ strategy & risk config hashes / runtime environment / symbol list / timeframe / data tier / source mix expectation / calibration train window / OOS label window / candidate window / `total_candidates_K` / selection-bias correction metadata / fee model / execution confidence / output policy / expiry。

---

## 6. v2 補丁：Replay Runner Contract（承襲 V3 §6）

### 6.1 Canonical Runner = `replay_runner` Rust binary

P3+ canonical runner = dedicated Rust binary `replay_runner`。

**May share**: internal strategy / risk / `TickPipeline` / `IntentProcessor` modules.

**Must NOT share**:
- live process bootstrap
- IPC server
- exchange dispatch
- DB writer channels
- Decision Lease acquisition wiring
- WebSocket usage

**Cargo feature**: `replay_isolated` 編譯時排除 forbidden imports；`ReplayProfile::Isolated` runtime cfg gate 額外驗證。**雙層保險**：feature flag 編譯時隔離 + runtime profile enum guard。

**Crate 邊界白名單**：white list 必明列允許的 mod path；任何 P0-T9 review 後 mod 加入須 PA + E3 sign-off。`nm` / `objdump` symbol grep 為 defense-in-depth（CI step），runtime + unit test authoritative。

### 6.2 P2 Isolated Smoke Runner

P2 phase 使用 `TickPipeline` + `IntentProcessor`，僅在 `ReplayProfile::Isolated` 下：

**Allowed**: S2 public Bybit data + S3 synthetic OHLC/tick + `TickPipeline` + `IntentProcessor` + in-memory paper state + canary/diagnostic output + baseline vs candidate comparison.

**Forbidden**:
- Decision Lease acquisition
- IPC server usage
- WebSocket usage
- exchange dispatch
- DB writer channels inside the runner
- writes to `trading.*`, `learning.*`, live/demo config, advisory tables
- MLDE/Dream advisory writes
- `demo_candidate`, `live_candidate_research_only`, `live_approved`

**Fail-closed behavior**:
- Any forbidden path detected at startup → abort before replay begins
- Any forbidden path detected during replay → abort run, record failed status, emit non-actionable diagnostic
- **Logging-only failure is rejected**

### 6.3 Mac Policy

1. May run S2 public-data smoke + S3 synthetic smoke.
2. Must NOT read S0/S1 private runtime data, `trading.fills`, `learning.exit_features`, demo/live_demo fills, local private orderbook captures.
3. Must NOT write replay registry, MLDE/Dream advisory rows, handoff candidates.
4. Must produce dry-run console / local artifact output only.
5. Must mark `runtime_environment='mac_dev_smoke_test_only'`, `engine_binary_sha=NULL`, `execution_confidence='none'`.
6. Any actionable interpretation requires Linux rerun on `linux_trade_core`.
7. `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` is the **default**; Mac fails closed if S0/S1/private access attempted.

### 6.4 Baseline Snapshot Mechanism

Baseline = same-strategy production-active config snapshot at `experiment_start_ts`。

**Linux** baseline capture:
1. `replay_runner` reads strategy/risk active config from runtime ConfigManager export.
2. Computes `strategy_config_sha256` + `risk_config_sha256` from canonical TOML.
3. Captures active strategy whitelist via `SELECT FROM strategy.active_registry`.
4. Persists snapshot pointer to `replay.experiments.baseline_snapshot_jsonb`.

**Mac** baseline capture:
1. **May NOT** pull live snapshot from Linux runtime DB.
2. Must use one of:
   - locally checked-in `srv/research_notes/replay_fixtures/<date>_demo_baseline.toml` fixture (PM-curated, sha-pinned)
   - explicit operator-provided baseline patch via UI
3. Snapshot pointer must mark `baseline_source='mac_fixture'` to surface non-portable result.
4. Any candidate report whose baseline came from Mac fixture is automatically flagged non-actionable.

**Cross-environment reproducibility rule**:
- Mac smoke result with Linux fixture sha → may inform exploration; **not actionable**.
- Linux runtime baseline snapshot sha → required for actionable demo handoff.
- Manifest must record both `baseline_source` and `engine_binary_sha`; mismatch → verdict downgraded to `defer_data`.

---

## 7. P2 Precondition: Indicator Leak-Free Sweep（V3 §3 G6 解封 + 本 v2 新增；v1 無對應節）

P2 runner 開工前，QC + E3 必須完成 5-strategy indicator leak-free sweep。

**Required output**: strategy inventory（runtime registration）/ indicator list / shift compliance / fixture / verdict (pass/retract/fix-required).

**Lookahead-leakage retraction rules**:
1. Retract from replay eligibility immediately.
2. P2 may proceed only if leaking strategy excluded and exclusion is explicit in manifest/report.
3. If strategy is part of baseline comparison set, P2 blocked until fixed.

**v2 狀態**：✅ 5/5 PASS（`docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`）— 解封 V3 §3 G6 + §7。詳見 §13。

---

## 8. Quant and Calibration Patches（承襲 V3 §8）

P3+ 阻塞於下列數值 gate 實裝：

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

Insufficient power → verdict `defer_data` (NOT `demo_candidate`).

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
- if PBO cannot run because power insufficient → verdict `defer_data`, NOT `demo_candidate`.
- no generic "equivalent gate" fallback.

### 8.4 Regime Controls

1. **Warmup**: First 500 fills after a negative-edge regime transition cannot drive handoff (prevents permanent CUSUM freeze in current 5-strategy negative-edge environment).
2. **CUSUM**: realized edge per cell freezes actionable handoff (NOT calibration model itself) on +/- 3 sigma break.
3. **Kupiec POF**: per (strategy, symbol) cell when n >= 250 fills; cell n < 250 skipped (do NOT borrow PBO sample).
4. **PSR(0)**: < 0.95 across 3 consecutive 250-fill windows triggers refit recommendation + PM alert.

---

## 9. v2 補丁：UX SoT Binding（凍結 v1 §6.5，UX subdoc V1 為唯一 SoT）

v1 沒指定 UX SoT；v2 鎖定到 UX subdoc V1：

| 概念 | 唯一 SoT |
|---|---|
| Sub-tab IA | UX subdoc V1 §2 |
| Session sub-tab | UX subdoc V1 §3 |
| Replay sub-tab | UX subdoc V1 §4 |
| Compare sub-tab | UX subdoc V1 §5 |
| Handoff sub-tab | UX subdoc V1 §6 |
| Mode badges（4 維） | UX subdoc V1 §7 |
| Disabled state contract | UX subdoc V1 §8 |
| Terminology（中英對照） | UX subdoc V1 §9 |
| Accessibility | UX subdoc V1 §10 |
| P1 Acceptance | UX subdoc V1 §11 |

**Mode badges (4 維 + rule)**:

| Badge | Values |
|---|---|
| run mode | paper_session / replay_smoke / calibrated_replay / advisory / handoff |
| data tier | S0 / S1 / S2 / S3 / S4 |
| execution confidence | none / limited / calibrated |
| runtime environment | linux_trade_core / mac_dev_smoke_test_only |

Rules:
1. `execution_confidence=none` must be visually non-actionable.
2. `mac_dev_smoke_test_only` must show dry-run status; cannot show handoff controls.
3. S2/S3 results cannot be framed as production evidence.
4. A verdict must never appear without all four badges in same viewport context.

**Cognitive overload mitigation**: 4 mode badge + 5 verdict label same screen ≥10 chip overcrowding risk. Mitigation = inline pill + grey-tone disabled + `execution_confidence='none'` warning color + grey background + ⚠️ icon + tooltip + card top-right red border.

**Disabled state forbidden**:
- fake active submit buttons
- hidden no-op clicks
- generic `Coming soon` without phase/gate
- success styling on non-actionable results
- replay controls that resemble live trading controls

---

## 10. Happy Path Business Flow（承襲 V3 §10）

### 10.1 Operator P2 Smoke 12-step flow（摘錄）

```
Step 1  Operator opens Paper Replay Lab → Replay sub-tab
Step 2  Selects symbol set, timeframe, data tier (S2/S3), market data window
Step 3  Picks baseline = current active demo snapshot (auto-filled by §6.4)
Step 4  Picks candidate = explicit config patch / git snapshot
Step 5  POST /api/v1/replay/manifests
        - server canonicalizes / signs / validates / returns experiment_id
Step 6  POST /api/v1/replay/runs {experiment_id}
        - global active run cap check
        - spawn isolated replay_runner with ReplayProfile::Isolated
        - signature verify first / hash second / fail-closed
        - indicator leak-free sweep status check
        - run TickPipeline + IntentProcessor in-memory
        - register artifacts via verified function
Step 7  Operator monitors GET /api/v1/replay/runs/{id}
Step 8  Run completes; status → completed; expires_at TTL=30d
Step 9  Operator views Compare sub-tab (12 metrics + verdict)
Step 10 Verdict in P2 NEVER `demo_candidate` or `live_approved`
Step 11 If actionable → Linux rerun (Mac case) or next phase
Step 12 Artifacts auto-prune at expires_at
```

### 10.2 Verdict 流轉（rule）

P2 phase: 只能 `reject` / `defer_data`.
P3+ enables: `defer_calibration` / `research_only`.
P6 enables: `demo_candidate` (with typed confirm).
**永遠**: 不可 `live_approved`.

### 10.3 Failure Modes（摘錄）

| Failure | Step | Behavior |
|---|---|---|
| signature mismatch | Step 6 | abort run; audit `signature_mismatch`; status=failed |
| hash mismatch | Step 6 | abort run; audit `manifest_hash_mismatch`; status=failed |
| window overlap | Step 5 | reject manifest with HTTP 400 |
| forbidden path attempted | Step 6 | **abort immediately (NOT log-only)**; status=failed |
| PG outage | Step 5/7 | route returns 200 + `{status: degraded, reason: pg_unavailable}` |
| Mac S0/S1 read attempt | Step 6 | runner fails closed via `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` |
| concurrent run cap hit | Step 6 | HTTP 429 with current active experiment_id |
| TTL expired | Step 7+ | artifact removed; query returns 404 reason=`expired` |

詳細 see V3 §10.

---

## 11. v2 補丁：Phase Exit KPI（承襲 V3 §11）

v1 沒指定 phase exit KPI；v2 鎖定到 V3：

| Phase | KPI |
|---|---|
| **P0** | docs-only land within 1 sprint of V3 acceptance; 0 runtime regressions |
| **P1** | 0 paper session regressions in 7d post-deploy; 8 mode badges all rendering |
| **P2a** | 0 dangling FK / 0 NULL `evidence_source_tier`; PG outage simulation → routes degrade not 5xx |
| **P2b** | ≥5 operator-driven baseline-vs-candidate runs / week; mean run time <5min, p95<10min; 0 Decision Lease acquire detected |
| **P3a** | calibration coverage ≥3 strategies × ≥10 symbols; CI tightness Welch p<0.05 |
| **P3b** | per-cell calibration green ≥40% of (strategy × symbol × side) cells with n≥30 within 30d S0 accumulation |
| **P4** | ≥10 advisory rows / week with replay_experiment_id; 0 unverified rows reach applier |
| **P5** | 0 agent monitor regressions; redirect click-through ≥80% in first 7d |
| **P6** | ≥1 demo handoff / week with typed confirmation; 0 live mutation events; 14d gradient 0 incident |

### 11.1 Cross-Phase Regression（每 phase exit 必跑）

| Phase N | 必跑前 phase regression |
|---|---|
| P1 | Paper session legacy regression |
| P2a | P1 #19 + 既有 8 governance routes auth contract |
| P2b | P2a #1-#7, #22, #23 + 既有 path alias `OPENCLAW_SRV_ROOT`/`OPENCLAW_BASE_DIR` 不 fallback 行為 |
| P3a | P2a + P2b 全部 + FUP-2 attribution writer healthcheck + 既有 5 strategy fill DB 寫不受影響 |
| P3b | P3a 全部 + CUSUM/Kupiec/PSR healthcheck baseline 不漂移 |
| P4 | P3a + P3b 全部 + 既有 `mlde_demo_applier` 對 `real_outcome` row 接受路徑不破（baseline ±10%） |
| P5 | P4 全部 + 既有 5-Agent API schema 不變 + `/api/v1/agents/*` shape 不破 |
| P6 | P5 全部 + GovernanceHub.acquire_lease + Decision Lease retrofit 回歸 + live gate 4 項 fail-closed 仍守 |

**全 phase continuous regression**（不分 phase 一律每 commit + nightly）：
- `replay_no_live_mutation`
- 16 根原則 #1 / #4 / #7 grep
- 跨平台路徑：`grep -E '(/home/ncyu|/Users/[^/]+)' <diff>` per commit

---

## 12. v2 補丁：Acceptance Binding（承襲 V3 §12 25 條）

v1 沒指定 acceptance；v2 鎖定到 V3 §12：

| 類型 | 數量 | 範例 |
|---|---|---|
| 直接 SQL probe（healthcheck.py 加 check_*） | 17 | #1 manifest_contract / #4 quota / #5 evidence_tier_completeness / #6 replay_source_guard / #7 registry_fk / #11 confidence_label / #12 mac_non_actionable / #14 no_live_mutation / #15 freshness / #16 power / #18 regime_gate / #22 safe_query / #23 baseline_provenance / #24 cost_gate |
| 部分可測（需新表/物理欄位） | 6 | #2 signature_verify（4 fail-mode unit test）/ #3 route_auth（integration）/ #8 resource_isolation（unit + nm grep）/ #9 no_lease_acquire（log grep + unit test）/ #10 fail_closed（chaos test）/ #17 cv_protocol（calibration model output assert） |
| GUI E2E（Playwright + a11y） | 4 | #19 no_order_submit（Playwright）/ #20 typed_confirm / #21 agents_monitor_read_only / #25 ml_maturity_label（雙驗 DB + UI） |
| 不可測 → V3.1 改寫 | 0 | （Round 3 audit 已 close） |

### 12.1 Acceptance 清單（25 條摘要）

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
| 13 | `strategy_indicator_leak_free` | P2 | 5-strategy sweep passed or explicit exclusion exists ✅ |
| 14 | `replay_no_live_mutation` | all | no live/demo config mutation or live orders |
| 15 | `execution_calibration_freshness` | P3 | model age <=72h for handoff |
| 16 | `execution_calibration_power` | P3 | n thresholds enforced (n>=200 strategy / n>=30 cell) |
| 17 | `replay_cv_protocol` | P4/P6 | DSR(K)>0.95 + PBO<0.5 (K>=10) + power gate enforced |
| 18 | `replay_regime_shift_gate` | P3+ | frozen regime + warmup phase block actionable candidates |
| 19 | `paper_replay_lab_no_order_submit` | P1+ | Replay Lab has no submit/cancel controls |
| 20 | `replay_handoff_typed_confirm` | P6 | typed confirmation + idempotency required |
| 21 | `agents_monitor_read_only` | P5 | extracted Agents Monitor remains read-only |
| 22 | `replay_routes_use_safe_query_pattern` | P2a | replay routes mirror `agents_routes.py` PG-degraded-safe pattern |
| 23 | `replay_baseline_snapshot_provenance` | P2a | manifest records `baseline_source` + `engine_binary_sha`; mismatch downgrades verdict |
| 24 | `replay_cost_edge_ratio_gate` | P3+ | LLM/ML assisted candidate loops respect `cost_edge_ratio >= 0.8` |
| 25 | `replay_ml_maturity_label` | P0 / P5 | each phase output / UI surfaces ML-pipeline maturity stage; P6 ≠ Production |

詳細 SQL probe / unit test / integration test templates 見 V3 §12 + implementation workplan §5。

---

## 13. v2 新增：G6 Indicator Sweep 解封紀錄（同 REF-19 v2 §18）

V3 §3 G6 / §7 P2 precondition 要求 5-strategy indicator leak-free audit 在 P2 runner 開工前完成。

### 13.1 解封證據

**Verdict 文件**：`docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`（5/5 PASS, 2026-05-03）

| # | 策略 | QC | E3 | PM compute_indicators body | Final |
|---|---|---|---|---|---|
| 1 | grid_trading | Conditional → PASS | PASS | closed-bar only | ✅ PASS |
| 2 | ma_crossover | Conditional → PASS | PASS | closed-bar only | ✅ PASS |
| 3 | bb_breakout | Conditional → PASS（Donchian shift(1) 已修） | PASS | closed-bar only | ✅ PASS |
| 4 | bb_reversion | Conditional → PASS | PASS | closed-bar only | ✅ PASS |
| 5 | funding_arb | PASS（架構級無 indicator） | PASS | N/A | ✅ PASS |

### 13.2 阻塞解除

- **V3 §3 G6**：✅ 解除
- **V3 §7 P2 Precondition**：✅ 解除（5/5 verdict=pass）
- **V3 §12 #13 healthcheck**：可寫 SQL probe（fixture 驗證模式，P2b 開工時補完）

詳細關鍵盲點補位 + Follow-up（L-01 / L-02 升 P2 / Mac/Linux byte-equality）見 REF-19 v2 §18.4 / verdict 文件。

---

## 14. ML Pipeline Maturity Mapping（承襲 V3 §13）

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

## 15. Storage and Table Separation（v1 §8 沿用 — API and Storage Design）

允許 sinks:
- local JSON/Markdown report under `docs/CCAgentWorkSpace/PM/workspace/reports/`
- `learning.mlde_shadow_recommendations` with explicit replay tags (經 verified function)
- `replay.*` schema for experiment manifests, replay fills, reports

禁止 sinks:
- 把 replay fills 當 real 寫入 `trading.fills`
- 把 replay rows 寫入 `learning.mlde_edge_training_rows` 沒有新 source column/view
- mutating live/live_demo configs from replay output

---

## 16. Phased Delivery（v1 §10 沿用 — Phased Delivery + v2 §11 KPI binding）

| Phase | Deliverables（摘錄） | Exit |
|---|---|---|
| **P0** | REF-19 v2 + REF-20 v2 + V3 + UX subdoc V1 + migration reservation + Guard A/B/C + indicator sweep ✅ + baseline snapshot mechanism | docs-only sign-off |
| **P1** | Paper Tab → Paper Replay Lab; 4 sub-tab IA; mode badges; manual submit/cancel removed | `paper_replay_lab_no_order_submit` PASS |
| **P2a** | replay registry + manifest sign + auth scaffold + evidence_source_tier retrofit + safe_query pattern | Guard A/B/C green; healthcheck #1-#7 + #22 green |
| **P2b** | `replay_runner` binary + isolated runner + run/status/cancel/report routes | #8/#9/#10/#11/#12 green |
| **P3a** | global execution calibration | attribution >=0.70; n>=200; stale<=72h |
| **P3b** | cell-level calibration | n>=30 cell gate; regime warmup green |
| **P4** | MLDE/Dream advisory + verified function | every replay row registry-backed |
| **P5** | Agents Monitor extraction (event-triggered after LG-2/3/4 + 7d stable) | API schema preserved |
| **P6** | bounded demo handoff with typed confirm | bounded, idempotent, reversible |

---

## 17. Implementation Sequence (high-level reference)

完整 implementation workplan + 9-Wave / 76-task breakdown 見 `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`。

**Wave 1**（立刻可開）：P0 docs amendment + scaffold 設計，9 task 並行（PA + E1 + E3 + A3 + PM 多 owner）。

**Wave 2-9**：sequential per workplan §1 9-Wave bar；hard prereq（FUP-2 attribution writer / decision_outcomes timeframe fix / 21d demo unlock 2026-05-07 / migration V### reservation / Decision Lease retrofit AMD-2026-05-02-01）見 workplan §6。

---

## 18. Operator-Facing Summary

REF-20 v2 把 v1 的 product surface IA + Learning / Agents Monitor 邊界鎖死，**外加**整合 V3 工程坑 + UX subdoc V1 SoT + indicator sweep G6 解封。

Paper Replay Lab：
- **能說**：這組參數不值得浪費 demo 時間 / 這組參數值得 bounded demo A/B / 這個 candidate 寫入 future governance review
- **不能說**：這已經 live-approved / synthetic PnL 是 real PnL / ML/Dream output 是 order / paper fill assumptions 是 exchange truth

Paper Replay Lab 是研究工具，不是 production trading surface。Live / live_demo 仍由 GovernanceHub + Decision Lease + live gates 保護。

---

## 19. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v1 | 2026-05-02 | PM | REF-20 初版 product surface design；Paper Tab → Paper Replay Lab + Learning 知識 cockpit + 5-Agent 抽出規劃 |
| **v2** | **2026-05-03** | **PA + PM** | **整合 V3 contract baseline（§3-§6 + §11-§12）+ UX subdoc V1（§9 binding）+ INDICATOR SWEEP verdict（§13 G6 解封）；新增 phase exit KPI / acceptance / ML maturity mapping；不改 v1 surface IA + Learning + Agents Monitor 邊界承諾** |
| v2.0.1 | 2026-05-03 | PA + E2 fix | cross-ref label 修字（M1/M2/M3）— §7 / §15 / §16 cross-ref 標的修正；§0 mapping table 補 v1 §6 manifest schema trace path；0 boundary / 0 spec 改動 |

---

## 附錄 A — 配套文件

| 角色 | 文件路徑 |
|---|---|
| v1 historical baseline | `docs/references/2026-05-02--paper_replay_learning_surface_design.md` |
| v1 中文版 | `docs/references/2026-05-02--paper_replay_learning_surface_design_zh.md` |
| v2 中文版 | `docs/references/2026-05-03--ref20_paper_replay_lab_governance_v2_zh.md` |
| V3 contract baseline | `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` |
| UX subdoc V1 | `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md` |
| Implementation workplan V1 | `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` |
| Indicator sweep verdict | `docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md` |
| REF-19 governance partner（v2） | `docs/references/2026-05-03--reality_calibrated_fast_replay_governance_v2.md` |
| DOC-01 16 根原則 | `srv/CLAUDE.md` §二 |
| AMD-2026-05-02-01（Decision Lease 路徑 A） | `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` |

## 附錄 B — Audit 軌跡

| 輪次 | 文件 | 主要結論 |
|---|---|---|
| Round 1 | `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md` | 全 REJECT |
| Round 2 | `docs/execution_plan/2026-05-02--ref20_v1_round2_audit.md` | 5/7 Conditional；2/7 阻塞 |
| Round 3 | `docs/execution_plan/2026-05-02--ref20_v2_round3_audit.md` | 5/7 Conditional Approve；12 條必補 |
| V3 baseline | `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` | P0 commit-ready；25 條 acceptance；15 條 hard gate |
| Indicator sweep | `docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md` | 5/5 PASS；G6 解除 |
| **v2 整合** | **本文件** | **PA + PM 整合 V3 + UX subdoc + sweep verdict 為 v2 governance amendment** |

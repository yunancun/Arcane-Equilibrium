---
spec: Sprint 1A-ζ Phase 2 — 3 E1 IMPL Dispatch Packet (Track A/B/C)
date: 2026-05-21
author: PA (Project Architect)；Phase 1 PA Refine deliverable
phase: Sprint 1A-ζ Phase 2 dispatch packet（PM 將以此為派發 prompt 三 E1 sub-agent）
status: SPEC-DRAFT-V0（待 Phase 0 sandbox prep §6 6 confirm 全 PASS 後 PM stagger 5min dispatch 3 並行 sub-agent）
parent specs:
  - srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md §2 Track A/B/C scope + §3 Phase split + §4 AC + §6.1.1 V### ordering
  - srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_phase0_sandbox_prep_checklist.md §6 GO criteria 6 confirm
  - srv/docs/execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md §4.1-4.12 per-V### dry-run SOP
  - srv/docs/adr/0034-decision-lease-layered-approval-lal.md (Decision 6 LAL Tier 0 RETIRED blocker)
  - srv/docs/adr/0042-m3-health-monitoring.md (Decision 4 amplification cap)
  - srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md (M11 governance)
  - srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md (697 行)
  - srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md (648 行)
  - srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md (619 行)
  - srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md (1329 行 full DDL)
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md (1087 行 full DDL)
  - srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md (1471 行 full DDL)
scope: 3 並行 E1 dispatch packet 撰寫（Phase 1 PA single-thread deliverable）；非 IMPL；非 commit；非 派下游 sub-agent
out-of-scope:
  - V### IMPL SQL 寫入（Phase 2 E1 IMPL 工作）
  - Rust skeleton 寫入（Phase 2 E1 IMPL 工作）
  - Python skeleton 寫入（Phase 2 Track C E1 IMPL 工作 per Q4a override）
  - Sandbox DB 創建（Phase 0 E3 工作）
  - TOTP secret 注入（Phase 0 AI-E 工作）
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# Sprint 1A-ζ Phase 2 — 3 E1 IMPL Dispatch Packet

## §0 TL;DR

| Track | Owner | 工時 | Sequential V### apply | AC coverage |
|---|---|---|---|---|
| **Track A** | E1 (Rust) | 12-18 hr | V113 placeholder + V112 (V113 ref) | AC-1 + AC-2 + AC-3 + AC-4 (含 AC-1.1) |
| **Track B** | E1 (Rust) | 13-19 hr | V106 standalone | AC-1 + AC-2 + AC-3 + AC-5 (含 AC-5.1) |
| **Track C** | E1 (Py/Rust) | 16-27 hr | V107 first standalone | AC-1 + AC-2 + AC-3 + AC-6 |

派發順序（per §4 + spike spec §6.1.1）：
- **Step 1**: Track C V107 first（standalone）— stagger T+0
- **Step 2**: Track A V113 (placeholder + §8-§13 PM 已 transcribe full DDL；不需新 V### apply per Sprint 1A-β closure) — stagger T+5min
- **Step 3**: Track A V112 (V113 ref)
- **Step 4**: Track B V106 (standalone) — stagger T+10min（與 Step 2-3 IMPL 並行但 PG apply 必 sequential 後跑）

---

## §1 Track A E1 Dispatch Packet — M1 LAL + V112 PG Apply

### 1.1 Sub-agent dispatch prompt (PM 派 prompt 用)

**Subagent role**: E1 (Engineer 1; Rust 主)；high-risk IMPL per `feedback_impl_done_adversarial_review` Phase 3a E2 強制對抗 review

**Working branch**: `feature/sprint_1a_zeta_track_a_m1_lal`

**Working DB**: `trading_ai_sandbox`（sandbox 隔絕 production；per spike spec §7.2 + Phase 0 prep）

### 1.2 Scope

**V### apply（sandbox PG）**:

- V112 (M1 LAL tiers) Linux PG migration apply on `trading_ai_sandbox`
- V113 (M7 decay) placeholder transcribe（§8-§13 PM 已 transcribe full DDL；Track A 工作 = sandbox PG apply only；不寫新 V### .sql 實檔；不修 V113 spec doc）

**Rust skeleton IMPL**:

- `engine/openclaw_engine/src/governance/lal_state_machine.rs`
  - `LalTier` enum: `Auto / LightReview / FullReview / OperatorApproval / OperatorAttestation`
  - `numeric_value(&self) -> i32` 對齊 ADR-0034「數字越大越嚴」
  - `from_i32(level: i32) -> Result<LalTier, LalTierError>` 對齊 PG CHECK BETWEEN 0 AND 4
  - State machine Tier 0 / Tier 1 transition only；Tier 2/3/4 stub `unimplemented!()`
  - 24h undo handler skeleton（per ADR-0034 Decision 5；scope = config + risk envelope only NOT fills）

- `engine/openclaw_engine/src/governance/lal_tier_0_fill_blocker.rs`
  - LAL Tier 0 fill query path 接 V113 `learning.decay_signals.lifecycle_state = 'RETIRED'` check
  - `RETIRED` 觸 fail-closed（per ADR-0034 Decision 6）
  - `RETIRED` 觸 fail 必寫 audit log（per `governance.audit_log` table；V098 已 land）

- `tests/spike_lal_transition.rs`
  - 5 row PG empirical transition test：Tier 0 emit → eligibility PASS → Tier 1 升階 → Tier 1 active → 5-gate kill 模擬 → Tier 1 demoted
  - 反向 INSERT test：`lal_level = -1` + `lal_level = 5` 必 RAISE CHECK constraint
  - Rust assert test：`LalTier::from_i32(-1)` + `LalTier::from_i32(5)` 必 Err；`numeric_value()` 數字越大越嚴對齊

### 1.3 工時

**12-18 hr**（含 V112 PG apply 5-7 hr + Rust skeleton IMPL 5-8 hr + 5 row PG empirical test 2-3 hr）

### 1.4 Acceptance Criteria (AC)

| AC | Pass criteria |
|---|---|
| **AC-1** | V112 在 `_sqlx_migrations` 顯示 `success=t` |
| **AC-2** | V112 Round 1 + Round 2 idempotency 跑 0 RAISE（NOTICE skip ≥ 6 = 2 table + 3 index + 1 MV）|
| **AC-3** | `restart_all.sh --rebuild --keep-auth` 後 `journalctl -u openclaw_engine --since '10 min ago' \| grep -c panic` = 0 |
| **AC-4** | 5 row Tier 0→1 transition cycle 真實 fire + ADR-0034 LAL 0-4 數字方向 PG CHECK 反向 INSERT 必 RAISE（per spike spec §AC-1.1）+ Rust `LalTier::from_i32(-1/5)` 必 Err + `numeric_value()` 越大越嚴 |

### 1.5 必讀文件清單（必須在 IMPL 動手前讀完）

1. `srv/docs/adr/0034-decision-lease-layered-approval-lal.md`（全文；7 Decision + Cross-references；尤其 Decision 6 LAL Tier 0 RETIRED blocker）
2. `srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md`（1329 行全文；含 §2.1 lease_lal_tiers + §2.2 lease_lal_assignments + §2.3 MV mv_lease_lal_eligibility）
3. `srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md`（697 行；尤其 §3 state machine + §10 IMPL phase split）
4. `srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md` §2.1 Track A scope + §4 AC-4 / AC-1.1 / AC-2 / AC-3
5. `srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_phase0_sandbox_prep_checklist.md` §6 GO criteria（必確認 6 confirm 全 PASS 才可動工）
6. `srv/docs/execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md` §4.8 V112 dry-run SOP（5 reflection Q1-Q5 + idempotency Round 1+2）

### 1.6 Sequential V### Constraint within Track A

```
Step 1: V113 (M7 decay; PM 已 transcribe full DDL §8-§13；Track A 只 sandbox PG apply 不寫新 spec)
        ↓
Step 2: V112 (M1 LAL; ref V113 no_incident_check_v113_ref BIGINT FK)
        ↓
Step 3: Rust skeleton IMPL（與 Track B/C IMPL 並行；不撞 PG）
        ↓
Step 4: 5 row PG empirical test
```

### 1.7 Reference Memory

- `feedback_v_migration_pg_dry_run` 2026-05-05（V055 5-round loop 教訓 — Mac mock pytest 抓不到 PG runtime）
- `project_2026_05_02_p0_sqlx_hash_drift` 2026-05-02（sqlx checksum drift incident SOP）
- `feedback_chinese_only_comments` 2026-05-05（注釋默認中文）
- `feedback_fetch_before_dispatch` 2026-04-24（git fetch 先做）
- `feedback_impl_done_adversarial_review` 2026-05-09（IMPL DONE 強制走 A3+E2 對抗 review）

### 1.8 反模式（明示禁止）

- (a) 直接在 production DB apply V112 → 違反 operator Q1d/Q2 sign-off「sandbox 隔絕」；BLOCKER
- (b) LAL Tier 2/3/4 寫真實 transition 邏輯 → violates spike scope（只測 Tier 0/1）；stub `unimplemented!()` 即 OK
- (c) LAL Tier 0 fill query path 不 check `learning.decay_signals.lifecycle_state = 'RETIRED'` → violates ADR-0034 Decision 6；BLOCKER
- (d) ADR-0034 LAL 0-4 數字方向反向（如「數字越小越嚴」）→ violates ADR-0034 line 41；BLOCKER
- (e) 修 V112 spec doc / ADR-0034 / Track B/C 文件 → violates spike scope（spec doc read-only；only sandbox PG apply）
- (f) Tier 4 manual override 繞 protected scope（即 spike 內測 Tier 4 fall-through）→ violates AMD-2026-05-21-01

### 1.9 Disconnect Recovery Protocol

- 接手 sub-agent 必跑 spike spec §6.3.1 三連檢查（memory log / git log / TODO entry）
- 接手前 commit 鎖（commit-first 後再動代碼；per `project_multi_session_memory_race`）
- 中斷點重啟必驗 V112 partial apply 狀態：`SELECT version, success FROM _sqlx_migrations WHERE version = 112`

---

## §2 Track B E1 Dispatch Packet — M3 Health + V106 PG Apply

### 2.1 Sub-agent dispatch prompt

**Subagent role**: E1 (Engineer 1; Rust 主)；high-risk IMPL

**Working branch**: `feature/sprint_1a_zeta_track_b_m3_health`

**Working DB**: `trading_ai_sandbox`

### 2.2 Scope

**V### apply（sandbox PG）**:

- V106 (M3 health observations) Linux PG migration apply on `trading_ai_sandbox`
- 含 hypertable 7d chunk + 90d retention policy
- 含 6 health domain ENUM CHECK + 4 health state ENUM CHECK

**Rust skeleton IMPL**:

- `engine/openclaw_engine/src/health/state_machine.rs`
  - 4-state ladder enum: `Ok / Warn / Degraded / Critical`
  - Per-domain SM (6 domain typically；spike 只 IMPL `engine_runtime` 1 domain)
  - Dwell time + flap suppression (per M3 spec §3.3：OK→WARN 60s / WARN→DEGRADED 5min)
  - `#[cfg(feature = "spike")]` mock time hook (per spike spec §AC-5.1：tokio::time::pause + advance)

- `engine/openclaw_engine/src/health/engine_runtime_domain.rs`
  - 1 domain only（per spike spec §1.4 scope）
  - 採 3 metric: `engine_cpu_pct` / `engine_rss_mb` / `engine_heartbeat`
  - 30s sampling（per M3 spec §2.3 line 75-77 engine_runtime row）
  - procfs Linux 平台 / sysctl Mac fallback（per `feedback_cross_platform` no-hardcode）

- `engine/openclaw_engine/src/health/amplification_cap.rs`
  - 24h rolling window 計數（per ADR-0042 Decision 4）
  - `amplification_loop_24h_count` 寫入 `learning.health_observations` table（per V106 spec §column inventory）
  - 同 `anomaly_id` 在 24h window 內最多觸發 1 次 state transition（per ADR-0042 Decision 4 cap 規則）

- `tests/spike_health_amp_cap_fire.rs`
  - per spike spec §AC-5.1 mock time hook test：第一個 spike → WARN；24h hop；第二個 spike → cap suppress（仍 WARN 不升 DEGRADED）
  - 反向 assert：24h cap 窗口內 inject 第二個 spike 必被 suppress

### 2.3 工時

**13-19 hr**（含 V106 PG apply hypertable 7d chunk 6-8 hr + Rust skeleton 4-7 hr + amp cap fire test 3-4 hr）

### 2.4 Acceptance Criteria

| AC | Pass criteria |
|---|---|
| **AC-1** | V106 在 `_sqlx_migrations` 顯示 `success=t` |
| **AC-2** | V106 Round 1 + Round 2 idempotency 跑 0 RAISE（NOTICE skip ≥ 5 = 1 hypertable + 4 index）|
| **AC-3** | `restart_all.sh --rebuild --keep-auth` 後 0 panic |
| **AC-5** | amp cap 24h-suppression empirical fire（per AC-5.1 mock time hook test）— inject fake CPU spike → HEALTH_WARN dwell time 60s pass；24h 內第二個 spike → cap suppress 不升 DEGRADED；`amplification_loop_24h_count = 1` |

### 2.5 必讀文件清單

1. `srv/docs/adr/0042-m3-health-monitoring.md`（全文；7 Decision 尤其 Decision 4 amplification cap）
2. `srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`（1087 行全文）
3. `srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`（648 行；尤其 §2.3 SLO threshold + §3.3 dwell time + §6 amplification logic）
4. `srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md` §2.2 Track B scope + §4 AC-5 / AC-5.1
5. `srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_phase0_sandbox_prep_checklist.md` §6 GO criteria
6. `srv/docs/execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md` §4.2 V106 dry-run SOP

### 2.6 Sequential V### Constraint within Track B

```
Step 1: V106 (M3 health; standalone；無 upstream FK dep)
        ↓
Step 2: Rust skeleton IMPL（與 Track A/C 並行；不撞 PG）
        ↓
Step 3: amp cap mock time fire test (per AC-5.1)
```

### 2.7 反模式（明示禁止）

- (a) 多 domain 同時 IMPL（CPU/memory/pipeline/api/strategy_quality/risk 6 個）→ violates spike scope（只 `engine_runtime` 1 domain）
- (b) 修 amp cap 從 24h 改 12h / 48h → violates ADR-0042 Decision 4
- (c) cascade gate cap 加進來（per ADR-0042 Decision 5）→ violates spike scope
- (d) HEALTH_CRITICAL 路徑接 5-gate kill → violates ADR-0042 Decision 6（M3 ≠ true live kill）

### 2.8 Disconnect Recovery Protocol

同 §1.9（Track A）。

---

## §3 Track C E1 Dispatch Packet — M11 Replay + V107 PG Apply + Python Skeleton

### 3.1 Sub-agent dispatch prompt

**Subagent role**: E1 (Engineer 1; Python + Rust mixed 因 Q4a override 含 Python skeleton + Rust fill query)

**Working branch**: `feature/sprint_1a_zeta_track_c_m11_replay`

**Working DB**: `trading_ai_sandbox`

### 3.2 Scope (per Q4a override 2026-05-21 operator decision)

**V### apply（sandbox PG）**:

- V107 (M11 replay divergence log) Linux PG migration apply on `trading_ai_sandbox`
- 含 hypertable 7d chunk
- 含 7 divergence_type ENUM CHECK + 3 severity ENUM CHECK + 5 flag_action_taken ENUM CHECK
- 含 forbidden field RAISE pattern (6 個禁忌字段：`auto_demote / target_state / decay_recommendation / demote_proposal_id / decay_stage / stage_demoted`)

**Python skeleton IMPL（per Q4a override 含 Python skeleton；2026-05-22 PA reconcile §2 path 對齊 IMPL reality）**:

- `helper_scripts/replay/m11_spike/spike_trigger.py`
  - 不真 nightly cron；手動 1 次 trigger
  - scope 限 1 strategy × 1 symbol × 1 day（per spike spec §2.3 C3）
  - 接 `trading_ai_sandbox` sandbox DB（per Phase 0 sample fills fixture 100-500 rows）
  - 寫 V107 row（`engine_mode = 'replay'`）

- `helper_scripts/replay/m11_spike/divergence_d1_fill_chain.py`
  - 1 種 divergence type：D1 fill_chain count delta
  - query `trading.fills` 內 strategy='bb_breakout' symbol='BTCUSDT' 1 day window
  - 計算 fill_chain count；對比 baseline；delta > 5 = D1 divergence
  - 寫 V107 row：`flag_action_taken = 'm7_decay_candidate'` + `divergence_type = 'fill_chain_count_delta'`

> **PA reconcile 說明**:`srv/python/` 頂層目錄不存在;`helper_scripts/` 是 CLAUDE.md §七 + `SCRIPT_INDEX.md` 約定的 Python helper script convention;spike trigger 為 manual-once 一次性執行不是 nightly cron production module → 屬 helper_scripts/ 範圍。Phase A Sprint 3 W15-18 升級為 nightly cron 時可再評估是否遷至 `helper_scripts/cron/` 或 `srv/openclaw/`(per V107 spec §7.3 cron schedule 設計)。

- `tests/spike_m11_m7_dedup_contract.py`
  - M7 dedup contract empirical verify：M11 寫 V107 後 driver query 驗 `learning.decay_signals` 0 row 寫入
  - grep V107 schema 6 個禁忌字段 = 0 hit
  - grep V107 .sql 實檔 6 個禁忌字段 = 0 hit

### 3.3 工時 (per Q4a override)

**16-27 hr**（原 11-17 + 5-10 hr Q4a override 含 Python skeleton + fill_chain detector empirical）

含：
- V107 PG apply + Guard A forbidden field RAISE 驗：5-7 hr
- M11 Python skeleton (spike_trigger.py)：3-4 hr
- divergence_d1_fill_chain.py：2-3 hr
- M7 dedup contract empirical test：2-3 hr
- 1 種 divergence empirical fire test：2-3 hr
- Acceptance report write-up：2-3 hr

### 3.4 Acceptance Criteria

| AC | Pass criteria |
|---|---|
| **AC-1** | V107 在 `_sqlx_migrations` 顯示 `success=t` |
| **AC-2** | V107 Round 1 + Round 2 idempotency 跑 0 RAISE |
| **AC-3** | `restart_all.sh --rebuild --keep-auth` 後 0 panic |
| **AC-6** | M11 → M7 dedup contract empirical verify — M11 manual trigger 寫 V107 row (`flag_action_taken='m7_decay_candidate'`)；driver query 驗 `learning.decay_signals` 0 row 寫入；grep V107 schema 6 個禁忌字段 = 0 hit + grep V107.sql 6 個禁忌字段 = 0 hit |

### 3.5 必讀文件清單

1. `srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（全文；M11 self-hosted PG + 3σ + M7 dedup contract）
2. `srv/docs/adr/0044-m7-decay-enforced-single-authority.md`（M7 single decay authority；含 RETIRED → LAL Tier 0 blocker）
3. `srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md`（1471 行全文；尤其 §5.1 Guard A forbidden action column）
4. `srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md`（619 行；尤其 §1.2 M7 dedup contract）
5. `srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md` §2.3 Track C scope + §4 AC-6 + §12 Q4a override
6. `srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_phase0_sandbox_prep_checklist.md` §4 sample fills fixture（100-500 rows bb_breakout BTCUSDT live_demo）
7. `srv/docs/execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md` §4.3 V107 dry-run SOP

### 3.6 Sequential V### Constraint within Track C

```
Step 1: V107 (M11 replay; standalone；無 upstream FK dep；first to apply per spike spec §6.1.1 ordering)
        ↓
Step 2: Guard A forbidden field RAISE 驗 (per V107 spec §5.1 + V099_V116 SOP §4.3 Round 1 Q3)
        ↓
Step 3: Python skeleton IMPL (spike_trigger.py + divergence_d1_fill_chain.py；與 Track A/B 並行；不撞 PG)
        ↓
Step 4: M7 dedup contract empirical test (M11 寫 V107 → 0 row in learning.decay_signals)
        ↓
Step 5: divergence empirical fire test (inject 1 synthetic divergence → V107 row 寫入 + flag_action_taken='m7_decay_candidate' backfill)
```

### 3.7 反模式（明示禁止）

- (a) V107 schema 含 6 個禁忌字段任一個 → violates V107 spec §5.1 + CR-7 M7 single decay authority；BLOCKER
- (b) M11 寫 `learning.decay_signals` 任一 row → violates M7 single decay authority；BLOCKER
- (c) M11 引用 Bybit historical liquidations API → violates ADR-0038 self-hosted only（per CR-14）
- (d) nightly cron 寫入 → violates spike scope（只手動 1 次 trigger）
- (e) 多 divergence type IMPL → violates spike scope（只 D1 fill_chain count delta）
- (f) 跨 strategy 或 跨 symbol query → violates spike scope（限 1 strategy × 1 symbol × 1 day）

### 3.8 Disconnect Recovery Protocol

同 §1.9（Track A）；額外驗 Python skeleton commit 狀態：`git log --oneline helper_scripts/replay/m11_spike/`

---

## §4 派發順序 (per spike spec §6.1.1 sequential V### apply)

Phase 0 §6 GO criteria 6 confirm 全 PASS 後，PM stagger 5 min dispatch 3 並行 sub-agent；V### apply 走 sequential：

```
[T+0 min]   Phase 0 §6 GO confirmed
            ↓
[T+0 min]   PM 派 Track C E1 (Step 1 V107 PG apply standalone) 
            ↓                  ↓
[T+5 min]   PM 派 Track A E1 (Step 2 V113 transcribe + Step 3 V112 PG apply)
            ↓                  ↓
[T+10 min]  PM 派 Track B E1 (Step 4 V106 PG apply standalone)
            ↓                  ↓
[T+15 min]  3 並行 Rust/Python skeleton IMPL（不撞 PG；走獨立 sibling file path per H-19）
            ↓                  ↓
[D+3]       3 並行 Phase 2 IMPL 收口 → Phase 3a E2 review × 3 並行 sub-agent
```

**為什麼 V107 first**：
- V107 (M11 replay) 是 standalone schema（無 upstream FK dep；唯獨 `replay_divergence_log.hypothesis_v103_ref` 是 nullable hard FK to V103，但 V103 已 Sprint 1A-α land）
- V107 ENUM CHECK + Guard A forbidden field RAISE 可獨立 verify
- 跨 Track 並行 IMPL 期間 V112 (M1 LAL) + V106 (M3 health) Rust skeleton 可獨立寫，不撞 V107

**為什麼 V113 + V112 在 V107 後**：
- V112 ref V113 `no_incident_check_v113_ref` BIGINT FK；V113 必先 apply
- V113 PM 已 transcribe full DDL §8-§13（Sprint 1A-β closure）；不需新 V### .sql 實檔 + 不修 spec doc；Track A 只 sandbox PG apply

**為什麼 V106 standalone 可後跑**：
- V106 (M3 health) 無 upstream FK；理論可與 V107 並行
- 但 sequential 派發避 3 並行 sandbox PG apply 撞 sqlx migration lock；stagger 5 min 即解

---

## §5 Phase 0 + Phase 1 GO Criteria Checklist

進入 Phase 2 E1 dispatch 前，PA + PM 必確認以下 8 條全 PASS：

### 5.1 Phase 0 §6 GO criteria 6 confirm（per sandbox prep checklist §6）

| # | Confirm | Owner | Status |
|---|---|---|---|
| C1 | sandbox DB `trading_ai_sandbox` 存在 + 連線可進 | E3 | [ ] |
| C2 | TimescaleDB extension 已裝 + 版本對齊 production | E3 | [ ] |
| C3 | V001-V096 baseline schema catch-up 完整（`_sqlx_migrations` max=96）| E3 | [ ] |
| C4 | TOTP secret `$OPENCLAW_SECRETS_DIR/vault/totp_2fa_sandbox.json` 存在 + 14d 有效期 | AI-E | [ ] |
| C5 | Sample fills 100-500 rows 在 sandbox `trading.fills` (bb_breakout BTCUSDT live_demo) | E3 + MIT | [ ] |
| C6 | `~/.pgpass` 含 sandbox role 一行 + chmod 600 | E3 | [ ] |

### 5.2 Phase 1 PA Refine 額外確認

| # | Confirm | Owner | Status |
|---|---|---|---|
| C7 | V103 EXTEND M4 PM Q1 verdict（V### naming + DEFAULT path）狀態 — 是否需 Phase 1 處理 OR carry-over Sprint 1A-ε 已 close | PA + PM | **carry-over Sprint 1A-ε 已 close**（per Sprint 1A-β closure 2026-05-21 verdict；V103 EXTEND 已 land；不影響 Sprint 1A-ζ spike）|
| C8 | 3 E1 dispatch packet 本 spec land + spike spec §AC-1.1 / §AC-5.1 / §6.3.1 三 subsection append | PA | [ ] PA Phase 1 closure 前驗 |

### 5.3 GO/BLOCK Verdict

**全 8 條 PASS** → PM 派 Phase 2 E1 × 3 sub-agent（per §4 sequential dispatch order）

**任一 FAIL** → 走 sandbox prep checklist §7 fallback：
- C1-C3 fail = Phase 0 sandbox infra BLOCKER → operator decide (a)/(b)/(c)
- C4 fail = TOTP secret BLOCKER → AI-E manual base32 + HMAC-SHA1 fallback
- C5 fail = sample fills seed BLOCKER → E3 + MIT 重跑 seed SQL
- C6 fail = pgpass BLOCKER → E3 補 + chmod
- C7 = 已 confirm carry-over Sprint 1A-ε close（不阻 Phase 2）
- C8 fail = PA 自審 BLOCKER → PA 補 + 重 verdict

---

## §6 Phase 2 → Phase 3 Sign-off Chain（per spike spec §10.1 + Phase 3a E2 強制對抗）

```
Phase 0 6 confirm GO (本 spec §5.1)
  ↓
Phase 1 PA refine deliverable land (本 spec §5.2)
  ↓
[T+0 min] PM 派 Track C E1 sub-agent
[T+5 min] PM 派 Track A E1 sub-agent
[T+10 min] PM 派 Track B E1 sub-agent
  ↓
Phase 2 Track A/B/C IMPL DONE（3 sub-agent 各自 commit + 自評）
  ↓
Phase 3a E2 對抗 review × 3 並行 sub-agent（per `feedback_impl_done_adversarial_review` 高風險強制）
  - Track A E2: review V112 PG apply + LAL state machine + AC-1.1 反向 INSERT empirical
  - Track B E2: review V106 PG apply + amp cap mock time hook + AC-5.1 fire test
  - Track C E2: review V107 PG apply + Guard A forbidden field + M11→M7 dedup contract
  ↓
Phase 3b E4 regression (pytest + cargo test --workspace + cross-language 1e-4 fixture)
  ↓
Phase 3c QA empirical (5 row PG transition / amp cap fire / dedup contract / 反向 INSERT RAISE)
  ↓
Phase 3d TW spike acceptance report (合併 3 Track AC 結果 + Lessons Learned)
  ↓
Phase 3e PM closure verdict (PASS / FAIL / Partial PASS per spike spec §5)
  ↓
operator sign-off Sprint 1B 派發 readiness（per spike spec §5.1 PASS condition）
```

---

## §7 Cross-Reference

- Sprint 1A-ζ spike spec：`/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md`
- Sandbox prep checklist：`/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_phase0_sandbox_prep_checklist.md`
- V099-V116 SOP：`/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md`
- V112 / V106 / V107 spec doc 路徑見 frontmatter parent specs
- ADR-0034 / ADR-0042 / ADR-0038 / ADR-0044 / AMD-2026-05-21-01

---

**END Sprint 1A-ζ Phase 2 — 3 E1 IMPL Dispatch Packet**

**PA DESIGN DONE**: 3 dispatch packet path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_3_e1_dispatch_packet.md`

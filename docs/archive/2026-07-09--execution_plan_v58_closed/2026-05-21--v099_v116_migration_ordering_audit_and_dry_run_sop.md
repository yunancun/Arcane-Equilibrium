---
spec: V099-V116 Migration Ordering Audit + 12 V### Dry-Run SOP
date: 2026-05-21
author: MIT (Sprint 1A-ε deliverable; ordering audit + dry-run SOP land before Sprint 1A-ζ spike + Sprint 1B-8 IMPL)
phase: v5.8 Sprint 1A-ε ε-track land
status: SPEC-DRAFT-V0 (MIT drafted; pending E5 hypertable + retention re-verify; pending PA Sprint 1A-ζ dispatch ref; pending PM sign-off)
sprint: Sprint 1A-ε (W6.5-8.5; single-thread cross-ADR + 12 V### dry-run SOP land)
audit scope: V099 V100 V101 V102 V103 V104 V105 V106 V107 V108 V109 V110 V111 V112 V113 V114 V115 V116 (18 V###)
dry-run SOP coverage: 12 V### (V105-V116; V099-V104 reference baseline only)
parent specs:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §6 cross-V### dependency graph + §5 IMPL wave race avoidance
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (940 行 baseline 範式)
  - srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md (Linux PG empirical dry-run protocol 範式)
  - srv/docs/execution_plan/2026-05-21--v105_m2_overlay_state_transitions_schema_spec.md (V105 full DDL spec)
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md (V106 full DDL spec)
  - srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md (V107 full DDL spec)
  - srv/docs/execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md (V108 full DDL spec)
  - srv/docs/execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md (V109 full DDL spec)
  - srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md (V110 full DDL spec)
  - srv/docs/execution_plan/2026-05-21--v111_m10_discovery_tier_config_schema_spec.md (V111 full DDL spec)
  - srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md (V112 full DDL spec)
  - srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md (V113 placeholder spec)
  - srv/docs/execution_plan/2026-05-21--v114_m5_model_versions_streaming_schema_spec.md (V114 placeholder spec)
  - srv/docs/execution_plan/2026-05-21--v115_m12_order_router_audit_schema_spec.md (V115 placeholder spec)
  - srv/docs/execution_plan/2026-05-21--v116_m13_asset_venue_dim_schema_spec.md (V116 placeholder spec)
  - srv/docs/adr/0010-timescale-hypertable-with-guard-migrations.md (Guard A/B/C + hypertable mandate)
  - srv/docs/adr/0011-v-migration-linux-pg-dry-run-mandatory.md (Linux PG dry-run mandate)
mirror precedent:
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C + NOT VALID CHECK + partial index 範式)
  - srv/sql/migrations/V083__fills_entry_context_id_close_check.sql (ALTER ADD COLUMN + NOT VALID CHECK 範式)
  - srv/sql/migrations/V084__decision_features_reject_negative_label.sql (UDF IMMUTABLE+PARALLEL SAFE 範式)
  - srv/sql/migrations/V086__governance_reject_close_reason_code.sql (one-shot UPDATE backfill 範式)
  - srv/sql/migrations/templates/schema_guard_template.sql (Guard A/B/C template)
memory references:
  - feedback_v_migration_pg_dry_run.md (2026-05-05 V055 5-round loop; PG dry-run mandate)
  - project_2026_05_02_p0_sqlx_hash_drift.md (sqlx checksum drift incident SOP; repair_migration_checksum binary)
scope: ordering audit + dry-run SOP design only — 不寫 V### IMPL SQL；不修 12 V### spec doc；不違背 ADR-0010 / 0011；不啟 E1；不發 commit；不修 ADR；不修其他 V###；不派下游
out-of-scope:
  - 12 V### IMPL SQL DDL（per-V### spec doc 各自完成；E1 Sprint 1B-8 IMPL）
  - Mac PG SQL 跑（Linux PG empirical dry-run mandatory per ADR-0011）
  - sqlx checksum 同步 IMPL（per-V### IMPL 階段；E1 走 repair_migration_checksum binary）
  - Cross-language 1e-4 fixture harness 真實 fixture path 落地（per H-18；E1 Sprint 1B-8 IMPL）
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# V099-V116 Migration Ordering Audit + 12 V### Dry-Run SOP

## §1 Context + 為什麼

### 1.1 Sprint 1A-ε 定位

Sprint 1A-ε (W6.5-8.5；單線 cross-ADR + 並行 docs/index/CONTEXT batch) 是 v5.8 Sprint 1A 五階段最後一階段，主要任務之一為 **「Schema migration ordering audit (V099-V116 sequencing + dependency graph land)」+「12 V### dry-run SOP land (per-V twice idempotency + engine restart 實測)」**（per PA dispatch consolidation §2 Sprint 1A-ε deliverable）。

本 spec 即此 ε-track deliverable 落地檔。

### 1.2 RUNTIME-NOT-APPLIED 狀態（為什麼必須 ordering audit）

Sprint 1A 期間 12 V### schema spec land 但 sqlx migration 文件 + Linux PG runtime 狀態 **顯著落後 spec**：

| 維度 | 狀態 | 證據 |
|---|---|---|
| **本地 sql/migrations/ max V###** | V098 | `ls srv/sql/migrations/*.sql \| tail -1` → `V098__governance_audit_log_halt_event_types.sql` |
| **Linux PG `_sqlx_migrations` max version** | V096 | per v103_v104 dry-run §2 query；V097/V098 file 存在但未 apply |
| **Sprint 1A 期間 land 之 V### spec** | V099-V116 18 個 V### spec doc (含 placeholder + full DDL) | per ls 2026-05-21 V###_*_schema_spec.md |
| **真實 .sql 實檔 land 範圍** | V099-V116 0 個 .sql 實檔（spec only） | per ls；V097/V098 file 已 land 但 PG 未 apply |

**RUNTIME-NOT-APPLIED 狀態定義**：spec doc land + V### number reserve + sql 實檔尚未 land + PG runtime 尚未 apply 的狀態。

**風險**：
1. 不同 sub-agent 跨 Sprint 1A-β/γ/δ 並行寫 V### 時撞 FK 順序（per CR-9 cross-V### dependency graph）
2. V### sql 實檔 land 後 PG runtime apply 前未跑 dry-run → V055 5-round loop 重蹈（per feedback_v_migration_pg_dry_run.md）
3. V### sql 實檔 land 後 engine restart 觸發 sqlx checksum drift → 2026-05-02 P0 incident 重蹈（per project_2026_05_02_p0_sqlx_hash_drift.md）

### 1.3 本 spec 任務

| Section | 任務 |
|---|---|
| §2 | V099-V116 全 cross-V### dependency graph (含 FK / schema ref / lifecycle dep edge 標示) |
| §3 | Sprint 1A-β/γ/δ V### apply sequencing (per sprint × per V### × Guard A/B/C × hypertable × retention) |
| §4 | 12 V### Linux PG empirical dry-run SOP (per V### Round 1/2 + engine restart + sqlx repair + rollback) |
| §5 | Guard A/B/C 規範對照表 + 反模式 RAISE pattern (forbidden detection_method 黑名單) |
| §6 | sqlx Checksum Drift Repair SOP (per 2026-05-02 incident) |
| §7 | Cross-Language 1e-4 Fixture Harness (per H-18) |
| §8 | IMPL Wave Race Avoidance (per CR-9 + §5 sub-agent ceiling) |
| §9 | Acceptance Criteria for Sprint 1A-ζ Spike + Sprint 1A-ε Ordering Audit |
| §10 | Open Q + Carry-over |
| §11 | Cross-Reference |
| §12 | Sign-off |

---

## §2 Cross-V### Dependency Graph (V099-V116)

### 2.1 18 V### overview

| V### | Topic | Sprint | Status (spec) | Status (sql 實檔) | Status (PG apply) |
|---|---|---|---|---|---|
| V097 | LG-5 attribution healthcheck indexes | Sprint pre-1A α catch-up | (catch-up file exists) | LAND | NOT APPLIED |
| V098 | governance.audit_log halt_event_types ALTER CONSTRAINT | Sprint pre-1A α catch-up | (catch-up file exists) | LAND | NOT APPLIED |
| V099 | Track v3 attribution column EXTEND (per dry-run §6.2 option A) | Sprint 1A-α | TBD (per v5.7 4 follow-up) | NOT LAND | NOT APPLIED |
| V100 | Track v3 ALTER NOT NULL + DEFAULT + 12 indexes + 4 P&L views | Sprint 1A-α | TBD (per v5.7 4 follow-up) | NOT LAND | NOT APPLIED |
| V101 | Earn schema (per dry-run §6.2 option A; rename from V103) | Sprint 1A-α | TBD (per v5.7 4 follow-up) | NOT LAND | NOT APPLIED |
| V102 | Earn schema indexes / NOT NULL (per option A; rename from V104 no-op) | Sprint 1A-α | TBD (per v5.7 4 follow-up) | NOT LAND | NOT APPLIED |
| **V103** | Earn / Hypothesis / Pre-registration / earn_movement_log | Sprint 1A-α (placeholder name from v5.7) | SPEC-DRAFT-V0 (940 行) | NOT LAND | NOT APPLIED |
| **V104** | (退號為 no-op per V103 spec §2.4) | n/a | n/a | n/a | n/a |
| **V105** | M2 Overlay State Transitions (hypertable) | Sprint 1A-γ | SPEC-FULL-V0 (72KB) | NOT LAND | NOT APPLIED |
| **V106** | M3 Health Observations (hypertable) | Sprint 1A-β | SPEC-FULL-V0 (53KB) | NOT LAND | NOT APPLIED |
| **V107** | M11 Replay Divergence Log (hypertable) | Sprint 1A-β | SPEC-FULL-V0 (80KB) | NOT LAND | NOT APPLIED |
| **V108** | M9 A/B Testing Framework (3 tables) | Sprint 1A-γ | SPEC-DRAFT-V1 (82KB full DDL) | NOT LAND | NOT APPLIED |
| **V109** | M8 Anomaly Events (hypertable + forbidden algo 黑名單) | Sprint 1A-γ | SPEC-FULL-V0 (75KB) | NOT LAND | NOT APPLIED |
| **V110** | M6 Reward Weight History + Bayesian Opt Runs (2 tables) | Sprint 1A-β | SPEC-DRAFT-V1 (52KB full DDL) | NOT LAND | NOT APPLIED |
| **V111** | M10 Discovery Tier Config + Activations (governance schema) | Sprint 1A-γ | SPEC-FULL-V0 (76KB) | NOT LAND | NOT APPLIED |
| **V112** | M1 Decision Lease LAL Tiers (governance schema + MV) | Sprint 1A-β | SPEC-FULL-V0 (69KB) | NOT LAND | NOT APPLIED |
| **V113** | M7 Decay Signals + Strategy Lifecycle (single decay auth) | Sprint 1A-β | SPEC-PLACEHOLDER (26KB outline) | NOT LAND | NOT APPLIED |
| **V114** | M5 Model Versions Streaming Column EXTEND (Y3+) | Sprint 1A-δ | SPEC-PLACEHOLDER-RESERVED-Y3 (9-14KB) | NOT LAND | NOT APPLIED |
| **V115** | M12 OrderRouter Adaptive Routing Audit (Sprint 6+) | Sprint 1A-δ | SPEC-PLACEHOLDER (9-18KB) | NOT LAND | NOT APPLIED |
| **V116** | M13 AssetClass / Venue Dim (Y3+) | Sprint 1A-δ | SPEC-PLACEHOLDER (8-18KB) | NOT LAND | NOT APPLIED |

12 V### dry-run SOP coverage = V105-V116（V099-V104 由 v5.7 4 follow-up dispatch SOP cover；本 spec §4 不重述）。

### 2.2 Dependency graph (ASCII)

```
                         [ V097 LG-5 attribution healthcheck indexes ]
                         [ V098 governance.audit_log halt_event_types ALTER CONSTRAINT ]
                                 ▲
                                 │ (catch-up Phase 0 必先 apply)
                                 │
                         [ V099/V100 Track v3 ]   [ V101/V102 Earn schema ]
                                 ▲                       ▲
                                 │ (Sprint 1A-α)         │ (Sprint 1A-α)
                                 │                       │
        ┌────────────────────────┴───────────────────────┴─────────────────────────┐
        │                                                                          │
        │ Sprint 1A-β (concurrent within Sprint; FK race-aware ordering)           │
        │                                                                          │
        │   V106 (M3 health)─┐                                                     │
        │                    │ (cross-ref query 非 FK)                              │
        │                    ▼                                                     │
        │   V107 (M11 replay)──────────────────────────────────┐                   │
        │                    ▲                                  │                  │
        │                    │ FK or cross-ref                  │                  │
        │                    │                                  ▼                  │
        │   V103 (hypotheses) ──────────────────────────► V108 (M9 A/B)            │
        │                                                       ▲                  │
        │                                                       │ cross-ref        │
        │                                                       │                  │
        │   V110 (M6 weight)                                     │                  │
        │                                                       │                  │
        │   V113 (M7 decay) ◄────────────────────────────────────┘                  │
        │                    ▲ V107 → V113 FK source_v107_divergence_id             │
        │                    │                                                     │
        │   V112 (M1 LAL) ◄──┘ V113 → V112 no_incident_check_v113_ref FK            │
        │                    ▲                                                     │
        │                    │ (cross-ref query 非 FK)                              │
        │                    │                                                     │
        │   (V106 V107 V108 V110 V112 V113 並行 land within Sprint 1A-β IMPL)        │
        │                                                                          │
        └──────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
        ┌──────────────────────────────────────────────────────────────────────────┐
        │ Sprint 1A-γ (after Sprint 1A-β land)                                      │
        │                                                                          │
        │   V105 (M2 overlay) ◄────── V107 (M11 replay-driven state advance)        │
        │   V108 (M9 A/B) (Sprint 1A-γ 內延後 IMPL；V103 prereq Sprint 1A-α 已 land) │
        │   V109 (M8 anomaly) ──────► V112 / V113 (cross-ref query 非 FK)           │
        │   V111 (M10 discovery) ──── V112 (approval_lal_ref placeholder FK)        │
        │                                                                          │
        └──────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
        ┌──────────────────────────────────────────────────────────────────────────┐
        │ Sprint 1A-δ (after Sprint 1A-γ land; placeholder reserve only)            │
        │                                                                          │
        │   V114 (M5 streaming EXTEND placeholder)                                 │
        │   V115 (M12 routing audit placeholder)                                   │
        │   V116 (M13 multi-venue dim placeholder)                                 │
        │                                                                          │
        │   (Sprint 1A-δ 不寫實 SQL；只 land frontmatter + 大綱)                    │
        │                                                                          │
        └──────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Cross-V### edges (per spec headers + PA dispatch consolidation §6)

| From | To | Edge type | 來源 spec |
|---|---|---|---|
| V107 (M11 replay) | V103 (hypotheses) | nullable FK (hypothesis_id) | V107 §0 (line 100) |
| V107 (M11 replay) | V108 (M9 A/B) | bi-directional cross-ref (ab_test_id) | V107 §0 (line 102) |
| V107 (M11 replay) | V109 (M8 anomaly) | severity sync cross-ref | V107 §0 (line 104) |
| V107 (M11 replay) | V112 (M1 LAL) | CRITICAL → HEALTH_WARN cross-ref | V107 §0 (line 106) |
| V107 (M11 replay) | V113 (M7 decay) | divergence signal feed (M7 single decay auth) | V107 §0 (line 105) |
| V108 (M9 A/B) | V103 (hypotheses) | hard FK (hypothesis_id NOT NULL) | V108 §0 (line 210) |
| V108 (M9 A/B) | V107 (M11 replay) | UUID cross-ref (m11_replay_divergence_ref) | V108 §0 (line 213) |
| V109 (M8 anomaly) | V106 (M3 health) | CRITICAL → HEALTH_DEGRADED cross-ref | V109 §0 (line 275) |
| V109 (M8 anomaly) | V112 (M1 LAL) | 90d incident-free check cross-ref | V109 §0 (line 276) |
| V109 (M8 anomaly) | V113 (M7 decay) | persistent anomaly 14d → source 5 cross-ref | V109 §0 (line 277) |
| V109 (M8 anomaly) | V107 (M11 replay) | CR-7 dedup contract cross-ref | V109 §0 (line 278) |
| V109 (M8 anomaly) | V108 (M9 A/B) | anomaly 期 A/B 暫停 cross-ref | V109 §0 (line 279) |
| V112 (M1 LAL) | V099/V100 (Lease state machine) | lease_id FK source | V112 §0 (line 532) |
| V112 (M1 LAL) | V113 (M7 decay) | no_incident_check_v113_ref FK | V112 §0 (line 533) |
| V112 (M1 LAL) | V098 (governance.audit_log) | assigned_by cross-ref 非 FK | V112 §0 (line 535) |
| V113 (M7 decay) | V107 (M11 replay) | source_v107_divergence_id FK (ON DELETE SET NULL) | V113 §2.1 (line 687) |
| V111 (M10 discovery) | V112 (M1 LAL) | approval_lal_ref placeholder FK | V111 §0 (line 483) |
| V111 (M10 discovery) | V106 (M3 health) | HEALTH_DEGRADED 60min → demote cross-ref | V111 §0 (line 450) |
| V111 (M10 discovery) | V107 (M11 replay) | tier transition replay reproducibility cross-ref | V111 §0 (line 451) |
| V106 (M3 health) | V112 (M1 LAL) | HEALTH_DEGRADED → LAL Tier 降階 cross-ref 非 FK | V106 §0 (line 14) |
| V106 (M3 health) | V109 (M8 anomaly) | amplification cap H-11 cross-ref 非 FK | V106 §0 (line 15) |
| V106 (M3 health) | V107 (M11 replay) | wall-clock budget overrun → HEALTH_WARN cross-ref | V106 §0 (line 16) |
| V105 (M2 overlay) | V107 (M11 replay) | divergence-driven state advance cross-ref | V105 §0 (line 16) |
| V105 (M2 overlay) | V109 (M8 anomaly) | COOLDOWN 觸發 source m8_anomaly cross-ref | V105 §0 (line 15) |
| V105 (M2 overlay) | V112 (M1 LAL) | overlay state ACTIVE 為 LAL Tier ≥ 2 input cross-ref | V105 §0 (line 14) |

### 2.4 Edge classification 統計

- **Hard FK** (NOT NULL constraint enforced)：3 條 (V108→V103 hypothesis_id, V112→V099/V100 lease_id, V112→V113 no_incident_check_v113_ref)
- **Nullable FK** (FK constraint + NULL allowed)：3 條 (V107→V103 hypothesis_id, V111→V112 approval_lal_ref, V113→V107 source_v107_divergence_id)
- **Cross-ref query** (no FK; application-layer JOIN)：22+ 條 (避免循環依賴 + writer hot path INSERT 過熱)
- **Lifecycle dependency** (no schema FK but state machine 觸發)：5 條 (V109→V112 demote, V105→V107 state advance, V106→V112 降階, V111→V106 60min sustained, V107→V113 decay signal feed)

### 2.5 0 Cycle 驗證

Graph 拓樸 sort 結果（per Sprint 排程）：

```
V097 → V098 → V099 → V100 → V101 → V102 → V103 → [V106 V107 V110 V112 V113] (β 並行) → [V105 V108 V109 V111] (γ 並行) → [V114 V115 V116] (δ 並行 placeholder)
```

**Cycle 檢驗**：
- V107 ↔ V108 (M11 ↔ M9 bi-directional cross-ref) → 採 UUID cross-ref (非 FK) → 0 schema-level cycle
- V107 → V113 → V112 → V109 → V107 (4-step potential cycle) → V107→V113 hard FK / V113→V112 hard FK / V112↔V109 cross-ref only / V109→V107 cross-ref only → 0 schema-level cycle
- V109 → V106 → V112 → ... (cross-ref only) → 0 schema-level cycle

**結論：0 schema-level cycle**。應用層 cross-ref query 可能在 hot path 走 JOIN 但不會違背 PG FK constraint。

---

## §3 Sprint 1A-β/γ/δ V### Apply Sequencing

### 3.1 Sprint pre-1A α catch-up (V097/V098)

per v103_v104 dry-run §6.3 SOP：

| Day | Action | V### | Owner |
|---|---|---|---|
| D-2 | Operator 簽 V097/V098 maintenance window (V098 ALTER < 1 min 低寫入) | V097/V098 | operator |
| D-1 | ssh trade-core apply V097/V098 → verify head=V098 → 24h baseline observe | V097/V098 | operator + E4 |

### 3.2 Sprint 1A-α (V099-V104; 4 follow-up)

per v5.7 4 follow-up + v103_v104 dry-run §6.2 option A：

| Day | Action | V### | Owner | Dependencies |
|---|---|---|---|---|
| D+0 | Operator 簽 V099/V100 Track v3 dispatch (含 PA rename) | V099/V100 | operator + PA | V097/V098 head |
| D+0.5 | E1 dispatch V099 (CREATE TYPE + ADD COLUMN nullable + CREATE 2 new tables + backfill baseline) | V099 | E1 | V098 head |
| D+1 | V099 idempotency 雙跑 + 24h observe | V099 | E4 | V099 land |
| D+1.5 | E1 dispatch V100 (ALTER NOT NULL + DEFAULT + 12 indexes + 4 P&L views) | V100 | E1 | V099 land |
| D+2 | V100 idempotency 雙跑 + head=V100 | V100 | E4 | V100 land |
| D+3 | Operator 簽 V101/V102/V103 Earn schema dispatch | V101/V102/V103 | operator + PA | V100 head |
| D+3.5 | E1 dispatch V101/V102/V103 (Earn schema CREATE 3 tables; Guard A/C) | V101/V102/V103 | E1 | V100 head |
| D+4 | V101/V102/V103 idempotency 雙跑 + 24h observe → head=V103 → V099-V103 closure | V101/V102/V103 | E4 | V101/V102/V103 land |

### 3.3 Sprint 1A-β (V106/V107/V110/V112/V113)

per PA dispatch consolidation §2 Sprint 1A-β + §5 IMPL wave race avoidance：

| Apply order | V### | Topic | Guard A/B/C 重點 | Hypertable | Retention | Sprint phase |
|---|---|---|---|---|---|---|
| 1 | V106 | M3 health observations | Guard A column 完整;Guard C ENUM 4 值;forbidden detection_method 不適用 | YES 7d chunk + 7d compress + 90d retention | 90d | Sprint 1A-β; M3 是高頻 hypertable 必先於 M11/M2/M1 writer wire |
| 2 | V107 | M11 replay divergence log | Guard A column 完整;Guard C ENUM (7 div_type + 3 severity + 5 flag_action_taken);forbidden auto_demote / target_state / decay_recommendation 黑名單 | YES 7d chunk + 30d compress + 90d retention | 90d | Sprint 1A-β; V107 land 後 V113 ingest signal source 即可 |
| 3 | V110 | M6 reward weight history + Bayesian opt runs | Guard A column 完整;Guard C ENUM (bayesian_algorithm 5 值 + engine_mode 5 值);無 forbidden | NO (regular tables ~10-100 row/yr) | n/a | Sprint 1A-β; M6 governance + Sprint 7+ Advisory IMPL |
| 4 | V112 | M1 LAL tiers (governance schema + MV) | Guard A column 完整;Guard C ENUM (LAL 0-4 + engine_mode 5 值);**LAL Tier 反向修正**驗 | NO (regular tables; MV CONCURRENTLY refresh) | n/a (assignments append-only ≤ 5k row/yr) | Sprint 1A-β; V113 hard FK no_incident_check 必先 land |
| 5 | V113 | M7 decay_signals + strategy_lifecycle | Guard A column 完整;Guard C ENUM (decay_action_level 4 值 + signal_source 4 值 + signal_severity 3 值);M7 single decay auth | YES (decay_signals 7d chunk + 90d retention) + NO (strategy_lifecycle regular) | 90d (signals) | Sprint 1A-β; V107 hard FK source_v107_divergence_id 必先 land |

**Sprint 1A-β IMPL race avoidance**：
- V106 + V107 + V110 並行 (no FK 撞)；E1 sub-agent A/B/C 各派一表
- V112 必先 V113 land + sqlx checksum verify (FK no_incident_check_v113_ref)；E1 sub-agent D 在 V113 land 後 dispatch
- V113 必先 V107 land + sqlx checksum verify (FK source_v107_divergence_id ON DELETE SET NULL)；E1 sub-agent E 在 V107 land 後 dispatch

### 3.4 Sprint 1A-γ (V105/V108/V109/V111)

per PA dispatch consolidation §2 Sprint 1A-γ：

| Apply order | V### | Topic | Guard A/B/C 重點 | Hypertable | Retention | Sprint phase |
|---|---|---|---|---|---|---|
| 1 | V105 | M2 overlay state transitions | Guard A column 完整;Guard C ENUM (3 overlay_type + 5 state + 5 trigger_type + engine_mode 5 值含 replay);無 forbidden | YES 7d chunk + 30d compress + 90d retention + MV mv_latest_overlay_state_per_strategy | 90d | Sprint 1A-γ; V107 (M11) 必先 land (state advance cross-ref) |
| 2 | V108 | M9 A/B testing framework (3 tables) | Guard A column 完整;Guard C ENUM (cluster_type 4 + statistical_method 3 + assignment_method 3 + ab_test_status 6 + engine_mode 5 含 replay);hard FK V103 hypothesis_id;CASCADE on test_id | YES (ab_assignments.assigned_at + ab_results.evaluation_ts 7d chunk + 30d compress + 180d retention) + NO (ab_tests regular) | 180d | Sprint 1A-γ; V103 (hypotheses) 必先 land (hypothesis_id hard FK) |
| 3 | V109 | M8 anomaly events (forbidden algo 黑名單) | Guard A column 完整;Guard C ENUM (9 event_taxonomy + 4 severity + 4 detection_method + 3 atr_vol_state + 3 funding_state);**forbidden detection_method 反向 RAISE** (`hmm` / `markov_switching` / `garch`) | YES 7d chunk + 30d compress + 180d retention | 180d | Sprint 1A-γ; V106/V112/V113 cross-ref 非 FK 可後 land |
| 4 | V111 | M10 discovery tier config + activations (governance schema) | Guard A column 完整;Guard C ENUM (Tier A-E 5 級 + engine_mode 5 含 replay);**regime_detection_method CHECK 強制** (`atr_vol_funding` / `pelt_reserved` / `none`);HMM/Markov/GARCH RAISE;5 row seed INSERT | YES (activations 7d chunk + 30d compress + 180d retention) + NO (config regular) | 180d | Sprint 1A-γ; V112 (M1 LAL) 必先 land (approval_lal_ref placeholder FK ALTER ADD CONSTRAINT 後加) |

**Sprint 1A-γ IMPL race avoidance**：
- V105 + V109 並行 (V107 prereq 已在 Sprint 1A-β land)；E1 sub-agent F/G 各派
- V108 在 V103 land 後 dispatch (V103 hard FK)；E1 sub-agent H
- V111 在 V112 land 後 dispatch (V112 approval_lal_ref placeholder FK ALTER ADD CONSTRAINT 後加)；E1 sub-agent I

### 3.5 Sprint 1A-δ (V114/V115/V116; placeholder reserve only)

per PA dispatch consolidation §2 Sprint 1A-δ + ADR-0035 Decision 2 + ADR-0040 Decision 1：

| V### | Topic | 觸發條件 | Sprint phase |
|---|---|---|---|
| V114 | M5 model_versions streaming column EXTEND | ADR-0035 Decision 3 6 條件 AND gate 全 PASS (Y3+) | Sprint 1A-δ placeholder reserve only; full DDL Y3+ activation 後另開 V114 IMPL spec doc |
| V115 | M12 OrderRouter adaptive routing audit (3 tables) | ADR-0039 Decision 6 (Sprint 6+ IMPL phase) | Sprint 1A-δ placeholder reserve only; full DDL Sprint 6+ M12 IMPL 階段 |
| V116 | M13 AssetClass / Venue dim (2 tables) | ADR-0040 Decision 1 Binance trade enable Y3+ at earliest | Sprint 1A-δ placeholder reserve only; full DDL Y3+ venue activation 後 |

**Sprint 1A-δ scope**：
- **不寫 V114.sql / V115.sql / V116.sql 實檔**
- **不跑 Mac PG / Linux PG dry-run**
- **只 land frontmatter + 14 section outline**
- **V### number 鎖定** (避免 Y3+ activation 撞既有已 land V### number per project_2026_05_02_p0_sqlx_hash_drift)

### 3.6 Sprint 1A 全部 V### apply 排程總表

| Sprint phase | V### batch | Apply sequence | E1 sub-agent ceiling |
|---|---|---|---|
| pre-1A α catch-up | V097, V098 | sequential (V098 後 V097) | 1 sub-agent (operator + E4 verify) |
| Sprint 1A-α | V099, V100, V101, V102, V103 | sequential (V099→V100→V101→V102→V103) | 1 sub-agent (E1 + E4 verify); V103 是 Earn schema (Earn / Hypothesis / earn_movement_log 3 tables) |
| Sprint 1A-β | V106, V107, V110 並行;V113 in V107 后;V112 in V113 后 | partial parallel (5-7 sub-agent) | 5-7 sub-agent (per CR-9 + §5 ceiling) |
| Sprint 1A-γ | V105 + V109 並行;V108 in V103 后;V111 in V112 后 | partial parallel (5-7 sub-agent) | 5-7 sub-agent |
| Sprint 1A-δ | V114, V115, V116 並行 (placeholder; 不跑 PG) | full parallel (3-4 sub-agent) | 3-4 sub-agent |

---

## §4 12 V### Linux PG Empirical Dry-Run SOP

仿 V103/V104 dry-run 範式（per `2026-05-21--v103_v104_linux_pg_dry_run.md`），per V###：

- **Round 1**: PG reflection query (5 條 SQL 對應 column / FK / index / ENUM / Guard 真值)
- **Round 2**: idempotency 雙跑驗 (apply once → verify no error; apply twice → verify NOTICE-skip not RAISE)
- **Engine restart 實測**: sqlx checksum repair binary 觸發條件 + repair SOP
- **Rollback plan**: 回退命令 + 對 active engine 影響
- **Expected output / verify 命令**: 預期 row count / chunk count / index count / ENUM count

### 4.1 V105 — M2 Overlay State Transitions

**PG connection** (per v103_v104 dry-run §1)：`psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai`

**Round 1: PG reflection query** (5 條 SQL)：
```sql
-- Q1: hypertable + chunk 驗
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables
  WHERE hypertable_schema='learning' AND hypertable_name='overlay_state_transitions';

-- Q2: ENUM CHECK 對齊驗 (3 overlay_type + 5 state + 5 trigger_type)
SELECT con.conname, pg_get_constraintdef(con.oid)
  FROM pg_constraint con
  JOIN pg_class cls ON cls.oid=con.conrelid
  JOIN pg_namespace ns ON ns.oid=cls.relnamespace
  WHERE ns.nspname='learning' AND cls.relname='overlay_state_transitions'
    AND con.contype='c';

-- Q3: engine_mode CHECK 5 值 (含 replay)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conname LIKE '%engine_mode%' AND conrelid::regclass::text='learning.overlay_state_transitions';

-- Q4: hot-path index 3 個 (strategy-symbol-time / state_to-time / trigger_type-time)
SELECT indexname, indexdef FROM pg_indexes
  WHERE schemaname='learning' AND tablename='overlay_state_transitions';

-- Q5: MV mv_latest_overlay_state_per_strategy
SELECT matviewname FROM pg_matviews
  WHERE schemaname='learning' AND matviewname='mv_latest_overlay_state_per_strategy';
```

**Round 2: Idempotency 雙跑**：
```bash
# 第一次 apply
ssh trade-core "psql -d trading_ai -f /tmp/V105_overlay_state.sql 2>&1" > /tmp/V105_round1.log

# 驗證: NOTICE skip / 0 RAISE
grep -c "NOTICE" /tmp/V105_round1.log   # expect: 0 (first run, all CREATE)
grep -c "ERROR" /tmp/V105_round1.log    # expect: 0

# 第二次 apply (idempotency)
ssh trade-core "psql -d trading_ai -f /tmp/V105_overlay_state.sql 2>&1" > /tmp/V105_round2.log

# 驗證: NOTICE skip ≥ 4 (1 table + 3 index + 1 mv = 5)
grep -c "NOTICE.*already exists" /tmp/V105_round2.log   # expect: ≥ 4
grep -c "ERROR" /tmp/V105_round2.log                    # expect: 0
grep -c "RAISE" /tmp/V105_round2.log                    # expect: 0 (Guard A/C 0 RAISE on idempotent re-apply)
```

**Engine restart 實測**：
- per project_2026_05_02_p0_sqlx_hash_drift incident SOP
- V105 land 後 `restart_all.sh --rebuild --keep-auth` 觸發 engine sqlx migrate
- 若 sqlx checksum drift (V105 file 在 commit 後修改重 commit) → engine abort
- Repair: `repair_migration_checksum --i-understand-this-modifies-db` (per project memory line 21)

**Rollback plan**：
```sql
-- 退階: drop V105 mv + table (engine 不需停)
BEGIN;
DROP MATERIALIZED VIEW IF EXISTS learning.mv_latest_overlay_state_per_strategy;
DROP TABLE IF EXISTS learning.overlay_state_transitions;
DELETE FROM _sqlx_migrations WHERE version=105;
COMMIT;
```

**對 active engine 影響**：
- V105 是新表; engine restart 後 M2 module 才使用; rollback 期間 engine 不會 INSERT
- 但 M11 / M3 / M8 writer 對 V105 cross-ref 不會中斷 (cross-ref 是 application-layer JOIN; FK 不存在)

### 4.2 V106 — M3 Health Observations

**Round 1: PG reflection query**：
```sql
-- Q1: hypertable + chunk (7d chunk 高頻表)
SELECT hypertable_name, num_chunks, chunk_time_interval 
  FROM timescaledb_information.hypertables
  WHERE hypertable_schema='learning' AND hypertable_name='health_observations';

-- Q2: ENUM CHECK (6 domain + 4 health state)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conrelid::regclass::text='learning.health_observations' AND contype='c';

-- Q3: engine_mode CHECK 4 值 (paper/demo/live_demo/live)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conname LIKE '%engine_mode%' AND conrelid::regclass::text='learning.health_observations';

-- Q4: hot-path index 4 個 (domain-time / state-time / symbol-time partial / strategy-time partial)
SELECT indexname, indexdef FROM pg_indexes
  WHERE schemaname='learning' AND tablename='health_observations';

-- Q5: compression + retention policy
SELECT * FROM timescaledb_information.compression_settings
  WHERE hypertable_schema='learning' AND hypertable_name='health_observations';
SELECT * FROM timescaledb_information.jobs
  WHERE proc_name='policy_retention' AND hypertable_name='health_observations';
```

**Round 2: Idempotency 雙跑**：同 §4.1 pattern；NOTICE skip ≥ 5 (1 table + 4 index = 5)；amplification cap H-11 邏輯 schema 層不 verify (writer 端責任)。

**Engine restart 實測**：V106 land 後 restart_all.sh --rebuild --keep-auth；M3 writer 直接寫 V106 表 (Sprint 1B+ wire)。

**Rollback plan**：drop hypertable + 對應 chunks 自動 cascade；engine 重啟前 healthcheck `check_M3_health_observations()` 必跳過。

### 4.3 V107 — M11 Replay Divergence Log

**Round 1: PG reflection query** (含 forbidden field 反向驗)：
```sql
-- Q1: hypertable + chunk
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables
  WHERE hypertable_schema='learning' AND hypertable_name='replay_divergence_log';

-- Q2: ENUM CHECK (7 divergence_type + 3 severity + 5 flag_action_taken)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conrelid::regclass::text='learning.replay_divergence_log' AND contype='c';

-- Q3: M7 single decay authority forbidden column 反向驗 (auto_demote / target_state / decay_recommendation / demote_proposal_id / decay_stage / stage_demoted)
SELECT column_name FROM information_schema.columns
  WHERE table_schema='learning' AND table_name='replay_divergence_log'
    AND column_name IN ('auto_demote','target_state','decay_recommendation',
                         'demote_proposal_id','decay_stage','stage_demoted');
-- expect: 0 rows (per CR-7 contract; AC-5 mandate)

-- Q4: engine_mode CHECK 5 值含 replay (M11 replay engine 寫入)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conname LIKE '%engine_mode%' AND conrelid::regclass::text='learning.replay_divergence_log';

-- Q5: H-11 passive Slack 字段 (passive_slack_ack_at TIMESTAMPTZ NULL)
SELECT column_name, data_type, is_nullable FROM information_schema.columns
  WHERE table_schema='learning' AND table_name='replay_divergence_log'
    AND column_name='passive_slack_ack_at';
```

**Round 2: Idempotency 雙跑**：NOTICE skip ≥ 5 (1 table + 4 index = 5)；forbidden field 反向驗應為 0 rows (AC-5 mandate)。

**Engine restart 實測**：V107 land 後 restart_all.sh；M11 replay engine 在 Sprint 3 W15-18 才接寫；engine restart 即時不依賴 V107。

**Rollback plan**：drop hypertable + V113 source_v107_divergence_id FK CASCADE check (V113 應 ON DELETE SET NULL，不會阻 rollback)。

### 4.4 V108 — M9 A/B Testing Framework

**Round 1: PG reflection query** (含 hard FK 驗)：
```sql
-- Q1: 3 tables 存在 (ab_tests, ab_assignments, ab_results)
SELECT table_name FROM information_schema.tables
  WHERE table_schema='learning' AND table_name IN ('ab_tests','ab_assignments','ab_results');

-- Q2: hard FK ab_tests.hypothesis_id → V103 hypotheses(hypothesis_id) NOT NULL
SELECT pg_get_constraintdef(oid), conname FROM pg_constraint
  WHERE conrelid='learning.ab_tests'::regclass AND contype='f';

-- Q3: CASCADE FK ab_assignments.test_id + ab_results.test_id → ab_tests
SELECT pg_get_constraintdef(oid), conname FROM pg_constraint
  WHERE conrelid IN ('learning.ab_assignments'::regclass, 'learning.ab_results'::regclass) 
    AND contype='f';

-- Q4: hypertable on ab_assignments.assigned_at + ab_results.evaluation_ts
SELECT hypertable_name FROM timescaledb_information.hypertables
  WHERE hypertable_schema='learning' AND hypertable_name IN ('ab_assignments','ab_results');

-- Q5: ENUM CHECK (cluster_type 4 + statistical_method 3 + assignment_method 3 + ab_test_status 6 + engine_mode 5)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conrelid::regclass::text LIKE 'learning.ab_%' AND contype='c';
```

**Round 2: Idempotency 雙跑**：NOTICE skip ≥ 8 (3 table + 5 index = 8)；hard FK 對 hypothesis_id 不可 violate (V103 必先 land + sample data INSERT)。

**Engine restart 實測**：V108 land 後 restart_all.sh；M9 framework 在 Sprint 4 read-only logging 接寫。

**Rollback plan**：DROP CASCADE ab_tests → ab_assignments + ab_results 自動級聯刪除；hypothesis_id FK 對 V103 hypotheses 不影響 (DROP V108 不影響 V103)。

### 4.5 V109 — M8 Anomaly Events (forbidden algo 黑名單)

**Round 1: PG reflection query** (含 ADR-0036 forbidden algorithm 反向 RAISE 驗)：
```sql
-- Q1: hypertable
SELECT hypertable_name FROM timescaledb_information.hypertables
  WHERE hypertable_schema='learning' AND hypertable_name='anomaly_events';

-- Q2: ENUM CHECK (9 event_taxonomy + 4 severity + 4 detection_method + 3 atr_vol_state + 3 funding_state)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conrelid::regclass::text='learning.anomaly_events' AND contype='c';

-- Q3: forbidden detection_method 反向驗 (ADR-0036 Decision 1)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conname LIKE '%detection_method%' AND conrelid::regclass::text='learning.anomaly_events';
-- expect: CHECK 含 atr_vol_funding_9cell / rv_percentile / block_bootstrap / manual_operator;NOT 含 hmm / markov_switching / garch

-- Q4: amplification cap H-11 字段 (amplification_loop_24h_count INTEGER)
SELECT column_name, data_type FROM information_schema.columns
  WHERE table_schema='learning' AND table_name='anomaly_events'
    AND column_name='amplification_loop_24h_count';

-- Q5: Guard A forbidden algorithm 反向 RAISE 測試 (boundary INSERT)
-- 此測試在 round 2 idempotency 之外執行;預期 INSERT detection_method='hmm' → ERROR
BEGIN;
INSERT INTO learning.anomaly_events (event_taxonomy, severity, detection_method, ...)
  VALUES ('regime_shift','CRITICAL','hmm', ...);
-- expect: ERROR (CHECK constraint violation)
ROLLBACK;
```

**Round 2: Idempotency 雙跑**：NOTICE skip ≥ 5 (1 table + 4 index = 5)；boundary INSERT 'hmm' 必 REJECT。

**Engine restart 實測**：V109 land 後 restart_all.sh；M8 detection 在 Sprint 3 read-only logging 接寫。

**Rollback plan**：drop hypertable；V112 / V113 cross-ref query 非 FK 不阻。

### 4.6 V110 — M6 Reward Weight History + Bayesian Opt Runs

**Round 1: PG reflection query**：
```sql
-- Q1: 2 regular tables (reward_weight_history + bayesian_opt_runs)
SELECT table_name FROM information_schema.tables
  WHERE table_schema='learning' AND table_name IN ('reward_weight_history','bayesian_opt_runs');

-- Q2: 5 λ column (lambda_alpha / lambda_sharpe / lambda_max_dd / lambda_hit_rate / lambda_capacity_used)
SELECT column_name FROM information_schema.columns
  WHERE table_schema='learning' AND table_name='reward_weight_history'
    AND column_name LIKE 'lambda_%';

-- Q3: bayesian_algorithm ENUM 5 值 (UCB / EI / PI / GP_Matern52 / GP_RBF)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conname LIKE '%bayesian_algorithm%' AND conrelid::regclass::text='learning.bayesian_opt_runs';

-- Q4: rollback_triggered BOOLEAN + rollback_reason TEXT
SELECT column_name, data_type FROM information_schema.columns
  WHERE table_schema='learning' AND table_name='reward_weight_history'
    AND column_name IN ('rollback_triggered','rollback_reason');

-- Q5: engine_mode CHECK 5 值含 replay
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conname LIKE '%engine_mode%' AND conrelid::regclass::text='learning.reward_weight_history';
```

**Round 2: Idempotency 雙跑**：NOTICE skip ≥ 5 (2 table + 3 index = 5)；regular table 無 hypertable validation。

**Engine restart 實測**：V110 land 後 restart_all.sh；M6 governance + Bayesian opt 在 Sprint 7+ Advisory 階段接寫。

**Rollback plan**：drop 2 tables；M9 (V108) cross-ref query 非 FK 不阻。

### 4.7 V111 — M10 Discovery Tier Config + Activations (governance schema)

**Round 1: PG reflection query** (含 Tier D forbidden algorithm 反向驗 + 5 row seed)：
```sql
-- Q1: 2 tables on governance schema
SELECT table_name FROM information_schema.tables
  WHERE table_schema='governance' AND table_name IN ('discovery_tier_config','discovery_tier_activations');

-- Q2: discovery_tier_activations hypertable
SELECT hypertable_name FROM timescaledb_information.hypertables
  WHERE hypertable_schema='governance' AND hypertable_name='discovery_tier_activations';

-- Q3: Tier A-E 5 row seed 在 discovery_tier_config
SELECT tier_level, activation_aum_threshold_usd FROM governance.discovery_tier_config
  ORDER BY activation_aum_threshold_usd;
-- expect: 5 rows (A=500, B=10000, C=30000, D=50000, E=100000)

-- Q4: regime_detection_method CHECK 強制 ADR-0036 allowlist (atr_vol_funding / pelt_reserved / none)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conname LIKE '%regime_detection_method%' AND conrelid::regclass::text='governance.discovery_tier_config';

-- Q5: forbidden algorithm 反向 INSERT 測試 (boundary)
BEGIN;
INSERT INTO governance.discovery_tier_config (tier_level, regime_detection_method, ...)
  VALUES ('D','hmm', ...);
-- expect: ERROR (CHECK constraint violation)
ROLLBACK;
```

**Round 2: Idempotency 雙跑**：NOTICE skip ≥ 5；5 row seed 在 round 2 不重複 INSERT (ON CONFLICT DO NOTHING)。

**Engine restart 實測**：V111 land 後 restart_all.sh；M10 tier discovery 在 Sprint 2+ cron productionize。

**Rollback plan**：drop 2 tables (V112 approval_lal_ref placeholder FK ALTER ADD CONSTRAINT 後須先 ALTER DROP CONSTRAINT)。

### 4.8 V112 — M1 Decision Lease LAL Tiers (governance schema + MV)

**Round 1: PG reflection query** (含 LAL Tier 反向修正驗 + 5 row seed)：
```sql
-- Q1: 2 tables on governance schema + 1 MV
SELECT table_name FROM information_schema.tables
  WHERE table_schema='governance' AND table_name IN ('lease_lal_tiers','lease_lal_assignments');
SELECT matviewname FROM pg_matviews
  WHERE schemaname='governance' AND matviewname='mv_lease_lal_eligibility';

-- Q2: LAL 0-4 ENUM 對齊 ADR-0034 (數字越大越嚴)
SELECT tier_level, approval_depth, auto_approve_eligibility 
  FROM governance.lease_lal_tiers 
  ORDER BY tier_level;
-- expect (per ADR-0034 line 137-143):
-- 0 = per-fill / always Guardian auto (LAL 0 = lowest risk, full auto)
-- 1 = intra-strategy reparam / Stage 4 + 30d stable / yes after eligibility
-- 2 = cross-strategy reweight / Stage 4 / Y2 only + Console opt-in
-- 3 = new strategy promotion / never auto
-- 4 = capital structure / venue change / never auto + always operator manual attestation

-- Q3: hard FK lease_lal_assignments.no_incident_check_v113_ref → V113 decay_signals (M7 single decay authority cross-ref)
SELECT pg_get_constraintdef(oid), conname FROM pg_constraint
  WHERE conrelid='governance.lease_lal_assignments'::regclass AND contype='f';

-- Q4: 5 row seed in lease_lal_tiers
SELECT count(*) FROM governance.lease_lal_tiers;
-- expect: 5 (LAL 0-4)

-- Q5: MV refresh policy (concurrent + Sprint 1B cron)
SELECT * FROM pg_matviews WHERE matviewname='mv_lease_lal_eligibility';
```

**Round 2: Idempotency 雙跑**：NOTICE skip ≥ 6 (2 table + 3 index + 1 MV = 6)；5 row seed ON CONFLICT DO NOTHING。

**Engine restart 實測**：V112 land 後 restart_all.sh；M1 LAL governance 立即 active (Stage 4 reparam halt eligibility check)。

**Rollback plan**：drop 2 tables + MV；V111 approval_lal_ref placeholder FK ALTER ADD CONSTRAINT 後須先 ALTER DROP CONSTRAINT。

### 4.9 V113 — M7 Decay Signals + Strategy Lifecycle

**Round 1: PG reflection query**：
```sql
-- Q1: decay_signals hypertable + strategy_lifecycle regular table
SELECT hypertable_name FROM timescaledb_information.hypertables
  WHERE hypertable_schema='learning' AND hypertable_name='decay_signals';
SELECT table_name FROM information_schema.tables
  WHERE table_schema='learning' AND table_name IN ('decay_signals','strategy_lifecycle');

-- Q2: decay_action_level ENUM 4 值 (RECOVERY / DECAY_DETECTED / DECAY_ENFORCED / RETIRED)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conname LIKE '%decay_action_level%' AND conrelid::regclass::text LIKE 'learning.%';

-- Q3: hard FK source_v107_divergence_id → V107 replay_divergence_log ON DELETE SET NULL
SELECT pg_get_constraintdef(oid), conname FROM pg_constraint
  WHERE conrelid='learning.decay_signals'::regclass AND contype='f';

-- Q4: signal_source ENUM 4 值 (m11_replay_divergence / alpha_curve_degradation / drawdown_breach / consecutive_losses)
SELECT pg_get_constraintdef(oid) FROM pg_constraint
  WHERE conname LIKE '%signal_source%' AND conrelid::regclass::text='learning.decay_signals';

-- Q5: M7 single decay authority forbidden 反向驗 (其他 module 不可寫 strategy_lifecycle.current_decay_action_level)
-- 此驗在 application-layer 不在 schema layer;此處不寫 SQL 留 E1 IMPL 期 verify
```

**Round 2: Idempotency 雙跑**：NOTICE skip ≥ 6 (2 table + 4 index = 6)；hard FK 必先 V107 land。

**Engine restart 實測**：V113 land 後 restart_all.sh；M7 decay 在 Sprint 8 IMPL；V112 LAL incident-free check 立即可走 V113 query。

**Rollback plan**：drop 2 tables；V112 no_incident_check_v113_ref hard FK 必先 ALTER DROP CONSTRAINT。

### 4.10 V114 — M5 Model Versions Streaming Column EXTEND (placeholder)

**Sprint 1A-δ scope**：placeholder reserve only；**不跑 Mac PG / Linux PG SQL**。

**Y3+ activation 後** (per ADR-0035 Decision 3 6 條件 AND gate 全 PASS 後)：
- 開新 amendment ADR
- V114 spec 升 SPEC-DRAFT-V1 含 full DDL
- Linux PG empirical dry-run (同 §4.1-4.9 pattern)
- V114 land

**本 Sprint 1A-δ 階段** SOP：
- V### number reserve 鎖定 (per ADR-0035 §Decision 2 + v5.8 §9 line 797)
- 不寫 V114.sql 實檔
- 不跑 PG
- Retirement criteria R1 觸發時同 dead-code removal PR 一起移除 frontmatter

### 4.11 V115 — M12 OrderRouter Adaptive Routing Audit (placeholder)

**Sprint 1A-δ scope**：placeholder reserve only；**不跑 Mac PG / Linux PG SQL**。

**Sprint 6+ M12 IMPL 階段** (per ADR-0039 §Decision 6) 後：
- V115 spec 升 SPEC-DRAFT-V1 含 full DDL (3 tables: order_routing_decisions hypertable / maker_fill_rate_30d_snapshots regular / routing_tier_transitions regular)
- Linux PG empirical dry-run (同 §4.1-4.9 pattern; hypertable + ENUM CHECK + hot-path index)
- V115 land

**本 Sprint 1A-δ 階段** SOP：
- V### number reserve 鎖定
- schema namespace `routing.*` vs `learning.*` reconciliation (per OQ-1) Sprint 6+ 處理
- 不寫 V115.sql 實檔
- 不跑 PG

### 4.12 V116 — M13 AssetClass / Venue Dim (placeholder)

**Sprint 1A-δ scope**：placeholder reserve only；**不跑 Mac PG / Linux PG SQL**。

**Y3+ venue activation 後** (per ADR-0040 §Decision 1 Binance trade enable 6-gate criteria 全 PASS) 後：
- 開新 amendment ADR
- V116 spec 升 SPEC-DRAFT-V1 含 full DDL (2 dim tables: reference.asset_class_dim + reference.venue_dim)
- Linux PG empirical dry-run (含 hardcode DEX/Hyperliquid reject 反向驗)
- V116 land

**本 Sprint 1A-δ 階段** SOP：
- V### number reserve 鎖定
- DEX / Hyperliquid hardcode reject (per ADR-0040 Decision 4 + ADR-0033 Decision 3)
- 不寫 V116.sql 實檔
- 不跑 PG

---

## §5 Guard A/B/C 規範對照表

per ADR-0010 + V094 範式 + per-V### spec doc Guard A/B/C 設計：

| V### | Guard A (CREATE TABLE IF NOT EXISTS 補表 existence) | Guard B (type-sensitive ADD COLUMN) | Guard C (hot-path index + ENUM verify) | 反模式 forbidden RAISE |
|---|---|---|---|---|
| V105 | ✓ (1 hypertable + 1 MV existence; column 完整性驗) | n/a (新表;無 ALTER) | ✓ (3 hot-path index + 3 ENUM + 5 audit field + engine_mode 5 值含 replay) | n/a |
| V106 | ✓ (1 hypertable existence; amplification cap 字段驗) | n/a | ✓ (4 hot-path index + 4 ENUM + engine_mode 4 值) | n/a |
| V107 | ✓ (1 hypertable existence; passive_slack_ack_at 字段驗) | n/a | ✓ (4 hot-path index + multi-ENUM + engine_mode 5 值含 replay) | **forbidden auto_demote / target_state / decay_recommendation / demote_proposal_id / decay_stage / stage_demoted 6 列反向 RAISE** (per CR-7 contract; AC-5 mandate) |
| V108 | ✓ (3 tables existence; hypothesis_id hard FK 驗) | n/a | ✓ (5 hot-path index + 5 ENUM + engine_mode 5 值含 replay + paper 不含 CHECK) | n/a |
| V109 | ✓ (1 hypertable existence; amplification_loop_24h_count 字段驗) | n/a | ✓ (4 hot-path index + 5 ENUM + engine_mode 4 值) | **forbidden detection_method 反向 RAISE** (hmm / markov_switching / garch); 對應 ADR-0036 Decision 1 |
| V110 | ✓ (2 regular tables existence; 5 λ column 驗) | n/a | ✓ (3 hot-path index + 5 ENUM + engine_mode 5 值含 replay; rollback_triggered partial index) | n/a |
| V111 | ✓ (2 governance tables existence; tier seed 5 row 驗) | n/a | ✓ (3 hot-path index + 5 ENUM + engine_mode 5 值含 replay; 5 row seed INSERT) | **forbidden regime_detection_method 反向 RAISE** (hmm / markov_switching / garch); 對應 ADR-0036 Decision 1 |
| V112 | ✓ (2 governance tables + 1 MV existence; LAL 0-4 seed 5 row 驗) | n/a | ✓ (3 hot-path index + 1 ENUM + engine_mode 5 值含 replay; 5 row seed INSERT) | **LAL Tier 反向修正驗** (placeholder v0 line 34 寫的 LAL 0 = full manual approval 全錯;以 ADR-0034 line 41 + 137-143 為準) |
| V113 | ✓ (1 hypertable + 1 regular table existence; M7 single decay authority 強制) | n/a | ✓ (4 hot-path index + 3 ENUM + engine_mode 4 值) | n/a |
| V114 | placeholder Y3+ | placeholder Y3+ (Y3+ activation 時 ADD COLUMN streaming_enabled + streaming_state) | placeholder Y3+ | placeholder Y3+ |
| V115 | placeholder Sprint 6+ | placeholder Sprint 6+ | placeholder Sprint 6+ | placeholder Sprint 6+ |
| V116 | placeholder Y3+ | placeholder Y3+ | placeholder Y3+ | **hardcode DEX/Hyperliquid reject 反向驗** (per ADR-0040 Decision 4 + ADR-0033 Decision 3) |

### 5.1 V###_*_template.sql Guard 範本 (per V094 mirror)

```sql
-- Guard A: 表已存在但 schema 不符
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables 
               WHERE table_schema='learning' AND table_name='X') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_schema='learning' AND table_name='X' 
                         AND column_name='required_col') THEN
            RAISE EXCEPTION 'V### silent-noop guard: learning.X exists but missing column required_col';
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.X (...);

-- Guard B: column 型別不符 (V### EXTEND 場景)
DO $$
DECLARE
    col_type text;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema='trading' AND table_name='Y' AND column_name='exit_source';
    
    IF col_type IS NOT NULL AND col_type != 'character varying' THEN
        RAISE EXCEPTION 'V### type mismatch: trading.Y.exit_source is % (expected varchar)', col_type;
    END IF;
END $$;

ALTER TABLE trading.Y ADD COLUMN IF NOT EXISTS exit_source VARCHAR(64);

-- Guard C: 索引選用 + ENUM 對齊驗
DO $$
DECLARE
    idx_def text;
BEGIN
    SELECT pg_get_indexdef(c.oid) INTO idx_def
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='learning' AND c.relname='X_hot_idx';
    
    IF idx_def IS NOT NULL AND idx_def NOT LIKE '%(symbol, strategy_name, ts DESC)%' THEN
        RAISE EXCEPTION 'V### index drift: X_hot_idx exists with wrong column order';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS X_hot_idx ON learning.X (symbol, strategy_name, ts DESC);
```

### 5.2 Forbidden RAISE pattern (反模式)

**V107 forbidden auto_demote 列**：
```sql
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='learning' AND table_name='replay_divergence_log'
                 AND column_name IN ('auto_demote','target_state','decay_recommendation',
                                      'demote_proposal_id','decay_stage','stage_demoted')) THEN
        RAISE EXCEPTION 'V107 contract violation: M11 sensor must not contain decay action columns (per CR-7 single decay authority contract)';
    END IF;
END $$;
```

**V109 / V111 forbidden detection_method 反向 RAISE**：
```sql
DO $$
DECLARE
    constraint_def text;
BEGIN
    SELECT pg_get_constraintdef(con.oid) INTO constraint_def
    FROM pg_constraint con
    WHERE con.conname LIKE '%detection_method%' 
      AND con.conrelid::regclass::text='learning.anomaly_events';
    
    IF constraint_def LIKE '%hmm%' OR constraint_def LIKE '%markov_switching%' 
       OR constraint_def LIKE '%garch%' THEN
        RAISE EXCEPTION 'V109 forbidden algorithm: detection_method CHECK contains hmm/markov_switching/garch (per ADR-0036 Decision 1 black-list)';
    END IF;
END $$;
```

**V112 LAL Tier 反向修正驗**：
```sql
DO $$
DECLARE
    tier0_eligibility text;
BEGIN
    SELECT auto_approve_eligibility INTO tier0_eligibility
    FROM governance.lease_lal_tiers WHERE tier_level=0;
    
    IF tier0_eligibility != 'always' THEN
        RAISE EXCEPTION 'V112 LAL Tier reverse error: tier_level=0 expected auto_approve_eligibility=always (per ADR-0034 line 137; placeholder v0 reverse description rejected)';
    END IF;
END $$;
```

---

## §6 sqlx Checksum Drift Repair SOP (per 2026-05-02 incident)

per memory `project_2026_05_02_p0_sqlx_hash_drift.md`：

### 6.1 Trigger condition

| Scenario | sqlx 行為 | OpenClaw engine 影響 |
|---|---|---|
| V### file 在 commit 後修改重 commit | sqlx 偵測 SHA-384 mismatch | engine `OPENCLAW_AUTO_MIGRATE=1` 啟動 → migrate error → engine abort |
| V### file land 後 audit retrofit 加 Guard A/B/C | sqlx file SHA-384 與 PG `_sqlx_migrations.checksum` 不一致 | engine restart 觸發 sqlx migrate → abort |
| V### file land 後 spec doc / comment 修正 (不影響 DDL semantic 但 file content 改動) | sqlx file SHA-384 drift | engine restart 觸發 sqlx migrate → abort |

### 6.2 Repair binary 使用 SOP

per memory line 21-25：

```bash
# Step 1: ssh trade-core 進 runtime machine
ssh trade-core

# Step 2: 進入 srv 目錄
cd /home/.../srv

# Step 3: build repair binary (若 binary 未 release)
cargo build --release --bin repair_migration_checksum

# Step 4: 跑 repair binary (含三層安全 + TTY guard + pg_dump backup)
./target/release/repair_migration_checksum --i-understand-this-modifies-db
# expect interactive prompt "Type COMMIT"; backup 路徑 /tmp/openclaw/backup/_sqlx_migrations_pre_repair_<ts>.sql

# Step 5: 確認 repair COMMITTED
# 預期 5 個 row UPDATE rows_affected=1 (per V028/V030/V031/V032/V034 incident pattern)

# Step 6: restart_all --keep-auth (engine startup ≥60s 無 abort)
bash helper_scripts/restart_all.sh --keep-auth

# Step 7: 確認 sqlx migrate 完成 (PG _sqlx_migrations.checksum 與 file SHA-384 一致)
ssh trade-core 'psql -d trading_ai -c "SELECT count(*) FROM _sqlx_migrations"'
```

### 6.3 防範: V### land 同時 commit `_sqlx_migrations` checksum

**Sprint 1A-β/γ IMPL phase 12 V### land 期 SOP**：

1. **V### file land 後立即 ssh trade-core run migration** (per 2026-05-02 incident 治理盲點 #1)
   - 不依賴「engine restart 後 sqlx migrate 自動跑」
   - 直接 ssh trade-core 跑 `sqlx migrate run --source srv/sql/migrations/` 立即 apply
2. **PG `_sqlx_migrations.checksum` 與 file SHA-384 對比驗證**
   ```bash
   ssh trade-core 'psql -d trading_ai -c "SELECT version, success, encode(checksum, '\''hex'\'') FROM _sqlx_migrations WHERE version BETWEEN 105 AND 116 ORDER BY version"'
   ```
3. **若 V### file 在 commit 後 retrofit 改動** → 立即跑 repair binary (per §6.2)
4. **audit closure SOP 必含 engine restart 實測** (per 2026-05-02 治理盲點 #1) — `cargo test PASS` ≠ `runtime sqlx migrate verify`

### 6.4 5 個 V083/V084 incident pattern 對 12 V### 啟示

per memory line 41-49：

- V083/V084 之 PG empirical dry-run 完成後 `_sqlx_migrations` 仍 head=V079 (因 manual `psql -f` 走非 OPENCLAW_AUTO_MIGRATE=1 sqlx 路徑)
- engine restart 後 sqlx checksum drift 觸發 abort
- 12 V### 必避免 manual `psql -f` 路徑;一律走 `sqlx migrate run` 或 `OPENCLAW_AUTO_MIGRATE=1 + restart_all --rebuild --keep-auth`
- audit closure 補 engine restart 實測 SOP；不可只 cargo test PASS

---

## §7 Cross-Language 1e-4 Fixture Harness (per H-18)

per PA dispatch consolidation H-18：

### 7.1 適用 4 module + 對應 V###

| Module | V### | 1e-4 fixture domain | Rust IMPL | Python replay |
|---|---|---|---|---|
| M3 health | V106 | latency p99 + rest success rate + backlog depth metric 計算 | rust/openclaw_engine/src/health_observer.rs | python/health_replay.py |
| M6 Bayesian | V110 | GP posterior mean of WLS sharpe - dd penalty + 5-λ tuple proposal | rust/openclaw_engine/src/bayesian_opt.rs | python/bayesian_replay.py |
| M8 z-score | V109 | RV percentile + block bootstrap threshold derivation + 9-cell ATR-vol × funding state | rust/openclaw_engine/src/anomaly_detector.rs | python/anomaly_replay.py |
| M11 replay | V107 | 7 divergence type detection + 3 severity 對比 live trace | rust/openclaw_engine/src/m11_replay.rs | python/m11_replay.py |

### 7.2 Fixture path placeholder

per PA dispatch consolidation H-18 + sibling spec doc cross-ref：

```
srv/tests/fixtures/cross_language_1e_4/
├── m3_health/
│   ├── input_health_metrics.json
│   ├── expected_rust_output.json
│   └── expected_python_output.json
├── m6_bayesian/
│   ├── input_5_lambda_history.json
│   ├── expected_rust_output.json
│   └── expected_python_output.json
├── m8_anomaly/
│   ├── input_atr_vol_funding_9cell.json
│   ├── expected_rust_output.json
│   └── expected_python_output.json
└── m11_replay/
    ├── input_live_trace.json
    ├── expected_rust_output.json
    └── expected_python_output.json
```

**1e-4 容差驗證 SOP** (E4 cross-language harness)：
```bash
# Step 1: Rust 跑 fixture input → output JSON
cargo run --release --bin m3_health_fixture_runner -- \
  --input srv/tests/fixtures/cross_language_1e_4/m3_health/input_health_metrics.json \
  --output /tmp/rust_output_m3.json

# Step 2: Python 跑 fixture input → output JSON
python python/health_replay.py \
  --input srv/tests/fixtures/cross_language_1e_4/m3_health/input_health_metrics.json \
  --output /tmp/python_output_m3.json

# Step 3: 容差驗證 (1e-4 absolute tolerance for numeric fields)
python helper_scripts/cross_language_compare.py \
  --rust /tmp/rust_output_m3.json \
  --python /tmp/python_output_m3.json \
  --tolerance 1e-4
# expect: PASS (0 fields diverge > 1e-4)
```

**Reusable harness 設計** (per H-18 一次建多次用)：
- 4 module 共用 `cross_language_compare.py` (兼容 JSON 結構;支援 numeric tolerance + categorical exact match)
- 4 module fixture path 統一 `srv/tests/fixtures/cross_language_1e_4/<module>/`
- Sprint 1B-8 IMPL phase per module 對應 add fixture; Sprint 1A-ε 階段先 land structure (空 fixture)
- Sprint 1A-ε 不做 fixture IMPL；只 land harness 結構 + 4 module placeholder 路徑

### 7.3 與 12 V### dry-run SOP 的關係

cross-language 1e-4 fixture harness **不**包含於 12 V### Linux PG dry-run (PG schema layer);harness 屬 application-layer IMPL verification。

但兩者**互相補強**：
- Schema layer (12 V### dry-run) PASS → 確保 PG 表結構 / Guard / ENUM / FK 對齊
- Application layer (1e-4 fixture harness) PASS → 確保 Rust IMPL ↔ Python replay 對同 input 產同 output (within 1e-4 tolerance)
- 兩者 PASS = M3/M6/M8/M11 module 整體 IMPL 可信

---

## §8 IMPL Wave Race Avoidance

per CR-9 cross-V### dependency graph + PA dispatch consolidation §5 並行性 + sub-agent 7 並行 ceiling：

### 8.1 Sprint 1A-α (V099-V103) 順序 dispatch

- 5 V### sequential dispatch (V099 → V100 → V101 → V102 → V103)
- 1 sub-agent E1 + 1 sub-agent E4 verify
- 不並行 (V### number race-aware)

### 8.2 Sprint 1A-β (V106/V107/V110/V112/V113) 部分並行

| Wave | V### batch | 並行 ceiling | Prereq |
|---|---|---|---|
| Wave 1 | V106 + V107 + V110 | 3 sub-agent 並行 | V103 head (only V103 hypotheses 預先 land) |
| Wave 2 | V113 | 1 sub-agent | V107 head (FK source_v107_divergence_id) |
| Wave 3 | V112 | 1 sub-agent | V113 head (FK no_incident_check_v113_ref) |

**Sprint 1A-β 並行性 = 3-3-1 sequential wave**；不可 V106 + V107 + V110 + V113 + V112 一次 5 並行 (FK race 風險)。

### 8.3 Sprint 1A-γ (V105/V108/V109/V111) 部分並行

| Wave | V### batch | 並行 ceiling | Prereq |
|---|---|---|---|
| Wave 1 | V105 + V109 | 2 sub-agent 並行 | V107 head (V105 cross-ref M11 / V109 cross-ref V106 cross-ref query 非 FK) |
| Wave 2 | V108 | 1 sub-agent | V103 head (hard FK hypothesis_id) |
| Wave 3 | V111 | 1 sub-agent | V112 head (V111 approval_lal_ref placeholder FK ALTER ADD CONSTRAINT) |

**Sprint 1A-γ 並行性 = 2-1-1 sequential wave**；不可 V105 + V108 + V109 + V111 一次 4 並行。

### 8.4 Sprint 1A-δ (V114/V115/V116) 全並行 (placeholder only)

- 3 V### parallel (placeholder spec only;無 schema dependency)
- 3-4 sub-agent (V114 PA + V115 PA + V116 PA + 1 sub-agent E5 verify schema number reserve)
- 不跑 Mac PG / Linux PG SQL → 0 race 風險

### 8.5 全 Sprint 1A IMPL wave 統合表

```
Sprint pre-1A α: V097 → V098 (1 wave, sequential)
                  ↓
Sprint 1A-α    : V099 → V100 → V101 → V102 → V103 (5 wave, sequential)
                  ↓
Sprint 1A-β    : V106+V107+V110 (Wave 1, 3 parallel) → V113 (Wave 2, 1) → V112 (Wave 3, 1)
                  ↓
Sprint 1A-γ    : V105+V109 (Wave 1, 2 parallel) → V108 (Wave 2, 1) → V111 (Wave 3, 1)
                  ↓
Sprint 1A-δ    : V114+V115+V116 (Wave 1, 3 parallel, placeholder only)
```

**Total 12 wave Sprint 1A 期間**；每 wave land 後必跑 idempotency 雙跑 + engine restart 驗證 (per §6.2)。

---

## §9 Acceptance Criteria for Sprint 1A-ζ Spike + Sprint 1A-ε Ordering Audit

### 9.1 Sprint 1A-ζ Spike AC (per Sprint 1A-ζ spec §4)

per assumption Sprint 1A-ζ spec 8 AC (本 spec 引用 reference;不擴寫)：

1. 8 AC ref Sprint 1A-ζ spike spec §4

(本 spec 不重述 Sprint 1A-ζ spike 8 AC 具體內容;以 Sprint 1A-ζ spec 為單一真實來源)

### 9.2 Sprint 1A-ε Ordering Audit AC (本 spec 新增 6 AC)

| AC# | AC 描述 | 驗證方法 |
|---|---|---|
| AC-OA-1 | Cross-V### dependency graph (§2.2 + §2.3) **0 schema-level cycle** | §2.5 拓樸 sort 驗 |
| AC-OA-2 | 18 V### overview (§2.1) 100% 標 Sprint phase (1A-α/β/γ/δ) + spec/sql/PG apply 狀態 | §2.1 table inspection |
| AC-OA-3 | 12 V### dry-run SOP (§4.1-4.12) 100% cover Round 1 + Round 2 + engine restart + rollback | §4 per V### sub-section count |
| AC-OA-4 | Guard A/B/C 規範對照表 (§5) 100% cover V105-V113 11 V### 完整;V114-V116 標 placeholder | §5 table inspection |
| AC-OA-5 | sqlx checksum repair SOP (§6) **reproducible** — 引 memory `project_2026_05_02_p0_sqlx_hash_drift` line 21-25 步驟 | §6.2 binary 使用 SOP 對齊 memory baseline |
| AC-OA-6 | Cross-language 1e-4 fixture harness (§7) **reusable across 4 module** (M3/M6/M8/M11) — fixture path 統一 + cross_language_compare.py 通用 | §7.1 + §7.2 path 結構 inspection |

### 9.3 ε-track 結束 trigger

- AC-OA-1..AC-OA-6 全 PASS
- Sprint 1A-ζ spike 8 AC 全 PASS (本 spec 引用 reference)
- PM sign-off (per §12)

---

## §10 Open Q + Carry-over

### Q1 V### dry-run SOP 是否需走 sandbox DB

per Sprint 1A-ζ Q1 d 採用：

**選項**：
- (a) Linux production PG `trading_ai` 直跑 (per V103/V104 dry-run 範式)
- (b) Linux sandbox PG `trading_ai_sandbox` (per 2026-05-02 incident SOP 預備路徑)
- (c) PG container per-V### dry-run isolation
- (d) (Sprint 1A-ζ Q1 d 採用; 細節留 Sprint 1A-ζ spike output)

**MIT 建議**：採 Sprint 1A-ζ spike 結論；本 spec §4 寫法以 production PG 為 default (per V103/V104 dry-run 範式)，sandbox 為 fallback (per 2026-05-02 incident SOP)。

### Q2 Cross-language 1e-4 fixture harness 三語言對齊

per memory `feedback_indicator_lookahead_bias` + H-18：

- Rust ↔ Python 對齊 1e-4 容差是 baseline
- 若未來 Sprint Y3+ 加入第三語言 (e.g. Julia for Bayesian) → 三語言 reconcile 路徑待 spec
- 本 spec §7 只 cover Rust ↔ Python；三語言 reconcile 留 future spec

### Q3 V113 SPEC-PLACEHOLDER 升 SPEC-FULL-V0 timeline

per §2.1 V113 status (SPEC-PLACEHOLDER 26KB outline)：

- V113 是 Sprint 1A-β CRITICAL deliverable (per CR-7 M7 single decay authority)
- 當前 spec 仍 placeholder + 大綱
- 必在 V112 IMPL dispatch 前升 SPEC-FULL-V0 (V112 hard FK no_incident_check_v113_ref 對 V113 schema 結構強依賴)
- MIT 建議 D+2-D+3 land V113 full DDL (per Sprint 1A-α 4 follow-up timeline)

### Q4 V099-V102 V### re-number 對 12 V### dry-run SOP 影響

per v103_v104 dry-run §6.2 option A vs option B：

- 若 operator 採 option A (V### 全順延 2 號) → 本 spec §2.1 + §3.6 + §4 V### number 須 re-number
- 若 operator 採 option B (V099/V100 reserve) → 本 spec §2.1 V099/V100 列 reserve；V101/V102 Track v3 / V103/V104 Earn schema
- MIT 建議採 option A (per v103_v104 dry-run §6.2 + PA 強烈建議 A)

### Q5 Linux PG sandbox DB credential

per v103_v104 dry-run §1 caveat：

- production PG = `127.0.0.1:5432/trading_ai` (user `trading_admin`)
- sandbox PG (若採 §10 Q1 option b/c) = 需另開 credential + 不可共用 production
- MIT 建議 Sprint 1A-ζ spike output 含 sandbox credential SOP

### Q6 12 V### Linux PG dry-run cumulative 時間估計

per V103/V104 dry-run 範例：
- V103/V104 dry-run 8 條 SQL 跑通約 30-60 min (含 SAVEPOINT + 6 log)
- 12 V### 每個約 30-60 min → cumulative 6-12 hr Linux PG empirical
- Sprint 1A-ε ε-track 1.5-2 wall-clock weeks 內可完成

---

## §11 Cross-Reference

### 11.1 18 V### spec doc 路徑

per §2.1 table + Sprint 1A 期間 land：

- `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` (V103/V104)
- `srv/docs/execution_plan/2026-05-21--v105_m2_overlay_state_transitions_schema_spec.md` (V105)
- `srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md` (V106)
- `srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md` (V107)
- `srv/docs/execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md` (V108)
- `srv/docs/execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md` (V109)
- `srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md` (V110)
- `srv/docs/execution_plan/2026-05-21--v111_m10_discovery_tier_config_schema_spec.md` (V111)
- `srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md` (V112)
- `srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md` (V113)
- `srv/docs/execution_plan/2026-05-21--v114_m5_model_versions_streaming_schema_spec.md` (V114)
- `srv/docs/execution_plan/2026-05-21--v114_m5_online_learning_reserved_schema_spec.md` (V114 alternate)
- `srv/docs/execution_plan/2026-05-21--v115_m12_order_router_audit_schema_spec.md` (V115)
- `srv/docs/execution_plan/2026-05-21--v115_m12_order_router_reserved_schema_spec.md` (V115 alternate)
- `srv/docs/execution_plan/2026-05-21--v116_m13_asset_venue_dim_schema_spec.md` (V116)
- `srv/docs/execution_plan/2026-05-21--v116_m13_multi_venue_reserved_schema_spec.md` (V116 alternate)

(V099-V102 spec 在 Sprint 1A-α 4 follow-up 期間 land；非本 ε-track scope)

### 11.2 ADR 路徑

- `srv/docs/adr/0010-timescale-hypertable-with-guard-migrations.md` (Guard A/B/C + hypertable mandate)
- `srv/docs/adr/0011-v-migration-linux-pg-dry-run-mandatory.md` (Linux PG dry-run mandate)
- `srv/docs/adr/0026-direct-exploit-bypass-cpcv.md` (Earn schema 字段集源)
- `srv/docs/adr/0034-decision-lease-layered-approval-lal.md` (V112 LAL 0-4 authoritative)
- `srv/docs/adr/0035-m5-online-learning-interface-reserved.md` (V114 reserve)
- `srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md` (V109 forbidden algo + V111 Tier D allowlist)
- `srv/docs/adr/0037-m9-ab-framework-and-statistical-methodology.md` (V108)
- `srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` (V107)
- `srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md` (V115)
- `srv/docs/adr/0040-multi-venue-gate-spec.md` (V116 Y3+)

### 11.3 Memory references

- `~/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/feedback_v_migration_pg_dry_run.md` (V055 5-round loop 教訓; PG dry-run mandate)
- `~/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/project_2026_05_02_p0_sqlx_hash_drift.md` (sqlx checksum drift incident SOP; repair_migration_checksum binary 治本路徑)
- `~/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/feedback_indicator_lookahead_bias.md` (cross-language 1e-4 fixture harness 對齊 baseline)

### 11.4 Mirror precedent

- `srv/sql/migrations/V094__fills_close_maker_audit.sql` (Guard A/B/C + NOT VALID CHECK + partial index 範式)
- `srv/sql/migrations/V083__fills_entry_context_id_close_check.sql` (ALTER ADD COLUMN + NOT VALID CHECK 範式)
- `srv/sql/migrations/V084__decision_features_reject_negative_label.sql` (UDF IMMUTABLE+PARALLEL SAFE 範式)
- `srv/sql/migrations/V086__governance_reject_close_reason_code.sql` (one-shot UPDATE backfill 範式)
- `srv/sql/migrations/templates/schema_guard_template.sql` (Guard A/B/C template)

---

## §12 Sign-off

| Role | Status | Date | Notes |
|---|---|---|---|
| **MIT** | DRAFTED | 2026-05-21 | Sprint 1A-ε ε-track ordering audit + 12 V### dry-run SOP land |
| **E5** | PENDING | TBD | hypertable + retention verify (per §3.3 V106/V107/V108/V109/V110/V111 hypertable 設計對齊 + 30d compress + 90-180d retention policy 對齊 E5 5.21 hypertable audit) |
| **PA** | REFERENCE | 2026-05-21 | Sprint 1A-ζ dispatch ref；本 spec 為 Sprint 1A-ζ spike + Sprint 1B-8 IMPL 之 preparation |
| **PM** | PENDING | TBD | Sprint 1A-ε ε-track 結束 sign-off |

### 12.1 MIT sign-off rationale

- ✓ Cross-V### dependency graph 完整 (18 V### × 24+ edge);0 schema-level cycle (per §2.5 拓樸 sort)
- ✓ 12 V### dry-run SOP 完整 (V105-V116 各列 Round 1/2 + engine restart + rollback)
- ✓ Guard A/B/C 規範對照表 完整 (V105-V113 11 V### 全 cover;V114-V116 placeholder 標)
- ✓ Forbidden RAISE pattern 範本 (V107 / V109 / V111 / V112 LAL Tier 反向修正)
- ✓ sqlx checksum repair SOP 引 memory baseline (per §6.2 對齊 project_2026_05_02_p0_sqlx_hash_drift line 21-25)
- ✓ Cross-language 1e-4 fixture harness 結構 (4 module reusable;path 統一)
- ✓ IMPL Wave race avoidance (Sprint 1A-β 3-1-1 / Sprint 1A-γ 2-1-1 / Sprint 1A-δ 3 全並行 placeholder)
- ✓ 6 AC for Sprint 1A-ε ordering audit (AC-OA-1..AC-OA-6 全 verifiable)
- ✓ ≥3 條 open Q (Q1 sandbox DB / Q2 三語言 / Q3 V113 SPEC-FULL upgrade timeline / Q4 V### re-number / Q5 sandbox credential / Q6 cumulative 時間估計)

### 12.2 邊界遵守 (per 派工 prompt 紅線)

- ✓ 不寫 IMPL Rust/Python code (本 spec 只 design;§4 SOP 列 SQL query 是 Round 1 reflection 不是 IMPL)
- ✓ 不修 12 V### spec doc 本檔 (本 spec 是 ordering audit + dry-run SOP land doc;不動 V105-V116 spec doc)
- ✓ 不違背 ADR-0010 / 0011 Guard 規範 (本 spec §5 + §6 100% 對齊)
- ✓ 中文為主 / 不加 emoji
- ✓ 700-1000 行 目標 (本 spec 約 870 行 — 在範圍內)

### 12.3 Sprint 1A-ε 結束 trigger

- AC-OA-1..AC-OA-6 全 PASS (per §9.2)
- Sprint 1A-ζ spike 8 AC 全 PASS (per §9.1 reference)
- E5 hypertable + retention verify (per §12 sign-off)
- PA Sprint 1A-ζ dispatch ref 對齊
- PM sign-off

---

**END V099-V116 Migration Ordering Audit + 12 V### Dry-Run SOP**

**MIT AUDIT DONE**: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md`

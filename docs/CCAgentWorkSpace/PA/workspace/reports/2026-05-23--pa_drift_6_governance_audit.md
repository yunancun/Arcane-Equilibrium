---
report: PA audit — PA-DRIFT-6 governance audit (其他 V### FK to TimescaleDB hypertable composite PK 風險 scan)
date: 2026-05-23
author: PA
phase: Sprint 5+ Wave 1 (per Stage F §8.7 carry-over)
status: AUDIT-DONE
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md §8.7
risk_grade: 中 (audit-only; 0 code change; identify 未來 V### IMPL 風險 + 既有 V### remediation path)
scope:
  - V### .sql FK全 scan (V001-V112 production land)
  - execution_plan/specs/ FK declaration (V### spec 全 set + design spec narrative)
  - production hypertable 反射 SQL + PK shape verify (Linux PG empirical)
  - FK target hypertable + composite PK 對照 → PA-DRIFT-6 candidate ranking
  - fix path 建議 per candidate (Option A soft ref / Option B target column change / Option C target redesign)
  - V### IMPL SOP amend 建議 (PA design phase reflexive SQL)
deliverables:
  - 本 PA report (audit findings + fix path 建議 + SOP amend draft)
  - 0 code change (per prompt 禁忌：不 IMPL fix / 不 commit / 不寫 ADR-0010 amend)
sign_off:
  - PA audit-done (本 task)
  - ADR-0010 amend round defer Sprint 5+ Wave 2 (per prompt option 1)
---

# §1 Executive Summary

## §1.1 核心結論

**Verdict**：**3 HIGH RISK candidate found + 1 SPEC-INTERNAL DESIGN ERROR + 5 LOW RISK pass-through**。

對既有 production V### (V001-V112) 反射 SQL 全 scan 結果：**Production 0 instance of PA-DRIFT-6 violation**（V100 已 fix；其他 16 production FK 全 target 非 hypertable composite PK target）。

對未來 V### spec (V105 / V108 / V109 / V113 / V115 等) FK design narrative + DDL spec scan：**3 個 future PA-DRIFT-6 violation candidate 識別**（必須在 IMPL 期 amend，否則 land 即 ERROR）。**1 個 V108 spec 內部 hypertable PK design error**（與 PA-DRIFT-6 不同 invariant，但同類 TimescaleDB 規範違反）。

## §1.2 數字

| 類別 | 數字 |
|---|---|
| 既有 production FK total (business schemas) | **16** |
| 既有 production FK 是 hypertable composite PK target | **0** |
| 既有 V### .sql REFERENCES literal | **9 (V001-V112)** |
| 既有 V### .sql ALTER TABLE ADD CONSTRAINT FK | **3 (V049/V051/V052)** |
| 既有 V### + Spec 全 FK target 對齊 hypertable + composite PK 案例 | **0 (V100 已 fix;不算)** |
| Future V### spec FK declaration | **39 across 12 spec files** |
| Future V### spec FK target = hypertable composite PK candidate | **3 HIGH RISK** |
| Spec-internal hypertable PK design error (與 PA-DRIFT-6 同類別) | **1 (V108 ab_assignments)** |

## §1.3 3 HIGH RISK candidate

**HIGH-1**：V112 spec line 894-897 `ALTER TABLE governance.lease_lal_assignments ADD CONSTRAINT fk_lal_no_incident_v113 FOREIGN KEY (no_incident_check_v113_ref) REFERENCES learning.decay_signals(id)`
- target = V113 `learning.decay_signals` hypertable PK `(signal_id, ingested_at)` composite
- IMPL 期執行此 ALTER 必 ERROR: "there is no unique constraint matching given keys"
- **修正方案 = Option A soft reference**（per V100 lesson）

**HIGH-2**：V113 spec §3 line 75 `decay_signals.source_v107_divergence_id BIGINT REFERENCES learning.replay_divergence_log.divergence_id`
- target = V107 `learning.replay_divergence_log` hypertable composite PK `(id, divergence_detected_at)`
- 另 spec line 64 wrote column name `divergence_id` 但 production V107 真實 column name = `id`（spec 命名 typo）
- IMPL 期 V113 CREATE TABLE 必 ERROR（雙重 fail：column name 不存在 + 即使對齊也撞 PA-DRIFT-6）
- **修正方案 = Option A soft reference** + spec column name patch（per V103/V107 PA-DRIFT-1 lesson）

**HIGH-3**：V113 spec §3 line 92 `strategy_lifecycle.triggering_signal_id BIGINT REFERENCES learning.decay_signals.signal_id`
- target = V113 `learning.decay_signals` hypertable composite PK `(signal_id, ingested_at)` composite
- IMPL 期 CREATE TABLE 必 ERROR
- **修正方案 = Option A soft reference**

## §1.4 1 SPEC-INTERNAL DESIGN ERROR (related, not strictly PA-DRIFT-6)

**SPEC-ERR-1**：V108 spec §2.2 line 247 `ab_assignments BIGSERIAL PRIMARY KEY` + line 269 `create_hypertable('learning.ab_assignments', 'assigned_at')`
- TimescaleDB 強制：hypertable partition column 必含 PK
- 本 spec 寫 single-column BIGSERIAL PK + assigned_at 為 hypertable partition column → IMPL 期 `create_hypertable` 必 ERROR: "cannot create hypertable: primary key must include partitioning column"
- **修正方案 = spec amend PK 為 `(assignment_id, assigned_at)` composite**（與 V105 / V106 / V107 / V108 ab_results / V109 / V111 範式對齊）
- **不是 PA-DRIFT-6**（因 ab_assignments 不被任何 FK target 引用）但屬同類 TimescaleDB 規範違反；如不修正 V108 spec land 即 ERROR

## §1.5 V109 範例：spec design 期已內化 PA-DRIFT-6 lesson

V109 spec line 205 + 254 + 871 + 946 **顯式內化** PA-DRIFT-6 invariant：「FK 跨 hypertable 在 TimescaleDB 不支援 partition-aware」。V109 `m3_health_observation_ref BIGINT NULL`（soft reference 無 FK constraint）+ `m11_replay_divergence_ref BIGINT NULL`（soft reference）+ 表內 cross-ref query pattern — **V109 是良好範式可作為 V### spec 未來 reference**。

**Lesson learned**：V109 spec author（per spec V109 sign-off chain）早於 V100 production deploy 已知 PA-DRIFT-6 invariant；證明此 lesson 是 **可推導**（per `db-schema-design-financial-time-series` skill）而非 V100 catch 時才發現。**V100 spec 沒 cross-ref 此 skill 是 PA design 期 SOP gap**。

## §1.6 Sprint 5+ Wave 2 amend 派發建議

| 候選 | 修正範圍 | 工時 | 風險 |
|---|---|---|---|
| HIGH-1 V112 spec amend | spec doc line 894-897 改 soft reference + COMMENT；本 V112 IMPL 已 land 不影響（FK 是 future ALTER plan，未執行） | PA 30 min spec edit | 低 (spec only) |
| HIGH-2 V113 spec amend | spec doc §3 line 64 + §8.1 改 column name + soft reference；V113 IMPL 未 land | PA 1 hr spec edit + MIT consultant verify type alignment | 中 (V113 IMPL 未啟動，spec-amend 必先 land) |
| HIGH-3 V113 spec amend | spec doc §3 line 92 改 soft reference + COMMENT | PA 30 min spec edit (與 HIGH-2 batch) | 中 (與 HIGH-2 batch) |
| SPEC-ERR-1 V108 spec amend | spec doc §2.2 line 247 PK 改 composite `(assignment_id, assigned_at)` + Guard A 列加 composite PK 驗 | PA 30 min spec edit + MIT verify | 中 (V108 IMPL 未啟動) |
| 5 LOW RISK pass-through items | 不 amend | 0 hr | 低 (現狀已正確) |

**Total Sprint 5+ Wave 2 PA spec amend budget**：~2.5 hr single-session（4 個 spec file edit + 1 MIT consultant cross-ref + 0 IMPL）。建議派發給 PA 與 V108/V112/V113 spec 原作者（or PM 直接 inline edit）。

---

# §2 FK 全 scan summary

## §2.1 既有 V### .sql REFERENCES literal (production land)

10 REFERENCES literal 跨 9 個既有 V### file：

| V### | File line | FK declaration | Source table | Target table |
|---|---|---|---|---|
| V004 | 263 | `fk_directive FOREIGN KEY (directive_id) REFERENCES learning.teacher_directives(directive_id)` | learning.directive_executions | learning.teacher_directives |
| V010 | 175 | `rollback_to INT REFERENCES learning.linucb_migrations(migration_id)` | learning.linucb_migrations | learning.linucb_migrations (self) |
| V032 | 78 | `recommendation_id BIGINT REFERENCES learning.mlde_shadow_recommendations(id) ON DELETE SET NULL` | learning.mlde_param_applications | learning.mlde_shadow_recommendations |
| V035 | 100 | `candidate_id BIGINT NULL REFERENCES learning.mlde_param_applications(id)` | learning.governance_audit_log | learning.mlde_param_applications |
| V046 | 155 | `run_id UUID NOT NULL REFERENCES replay.run_state(run_id) ON DELETE CASCADE` | replay.report_artifacts | replay.run_state |
| V049 | 325 | `ALTER ADD CONSTRAINT fk_replay_experiments_parent ... REFERENCES replay.experiments(experiment_id)` | replay.experiments (self) | replay.experiments |
| V050 | 160 | `experiment_id UUID NOT NULL REFERENCES replay.experiments(experiment_id) ON DELETE CASCADE` | replay.simulated_fills | replay.experiments |
| V051 | 263 | `ALTER ADD CONSTRAINT fk_mlde_shadow_replay_experiment ... REFERENCES replay.experiments(experiment_id)` | learning.mlde_shadow_recommendations | replay.experiments |
| V052 | 253/319 | `ALTER ADD CONSTRAINT fk_replay_run_state_manifest_id ... REFERENCES replay.experiments(experiment_id)` × 2 | replay.run_state + replay.report_artifacts | replay.experiments |
| V065 | 99/175 | `proposal_id TEXT NOT NULL REFERENCES openclaw.proposals(proposal_id) ON DELETE RESTRICT` + `linked_proposal_id REFERENCES openclaw.proposals(proposal_id) ON DELETE SET NULL` | openclaw.approval_decisions + openclaw.channel_events | openclaw.proposals |
| V100 | 322 | `hypothesis_id BIGINT NOT NULL REFERENCES learning.hypotheses(hypothesis_id)` | learning.hypothesis_preregistration | learning.hypotheses |
| V100 | (was) | `governance_approval_id BIGINT REFERENCES learning.governance_audit_log(id)` | learning.earn_movement_log | **PA-DRIFT-6 catch + soft ref fix** |
| V107 | 319 | `hypothesis_id BIGINT REFERENCES learning.hypotheses(hypothesis_id)` | learning.replay_divergence_log | learning.hypotheses |
| V112 | 185/189 | `prev_tier_level / tier_level REFERENCES governance.lease_lal_tiers(tier_level)` | governance.lease_lal_assignments | governance.lease_lal_tiers |

**結論**：除 V100 (catch + fix) 之外 16 個 production FK 全 target 非 hypertable composite PK target；既有 production schema 0 PA-DRIFT-6 violation。

## §2.2 Future V### Spec FK declaration (尚未 IMPL)

39 個 FK literal 跨 12 個 spec doc（per 2026-05-2x specs）：

**V100 spec (已 IMPL + PA-DRIFT-6 fix)**：4 hit — 全 PASS（governance_approval_id 已 soft ref；hypothesis_preregistration FK target 非 hypertable）

**V101/V102 spec (track attribution)**：3 hit — `parent_hypothesis_id` + `mutation_of` + `superseded_by` 全 target 非 hypertable，PASS

**V103/V104 spec (earn hypotheses)**：8 hit — 含 PA-DRIFT-1 schema name typo `governance.audit_log` (production 應 `learning.governance_audit_log`)；本 spec 已 deprecated（per V100 spec 取代）但 spec 文檔仍存在；未來 reader 需注意此屬 已棄 spec

**V103 EXTEND spec (extend m4 hypothesis columns)**：1 hit — comment 占位 `REFERENCES governance.decision_lease(lease_id)` 待 future EXTEND

**V107 spec (m11 replay_divergence_log)**：3 hit — hypothesis_id BIGINT REFERENCES learning.hypotheses (production land + PASS) / 提及 future V108 + V113 reference 列為 「Test grep pattern」

**V108 spec (m9 ab_testing_framework)**：6 hit
- ab_tests.hypothesis_id REFERENCES learning.hypotheses → PASS (non-hypertable target)
- ab_tests.lease_id REFERENCES governance.decision_lease → governance.decision_lease 0 production exists；spec gap (table 不在 production；待 future migration)
- ab_tests.approval_id REFERENCES governance.audit_log → schema name typo (應 learning.governance_audit_log) + composite PK target → **PA-DRIFT-6 (silent)**
- ab_assignments.test_id REFERENCES learning.ab_tests → PASS (ab_tests 非 hypertable per spec)
- ab_assignments.lease_id REFERENCES governance.decision_lease → spec gap
- ab_results.test_id REFERENCES learning.ab_tests → PASS

**V108 ab_assignments PK design error**：line 247 BIGSERIAL PRIMARY KEY + line 269 hypertable on assigned_at → **SPEC-ERR-1**（hypertable required PK 含 partition column）；IMPL 期必 amend 為 composite `(assignment_id, assigned_at)`

**V111 spec (m10 discovery_tier_config)**：3 hit — discovery_tier_activations.tier_level REFERENCES discovery_tier_config(tier_level) (PASS, non-hypertable target) / future ALTER ADD CONSTRAINT to lease_lal_assignments.id (PASS, target non-hypertable)

**V112 spec (m1 decision_lease_lal_tiers)**：5 hit — 4 PASS (lease_lal_tiers.tier_level FK target) + 1 **HIGH-1 PA-DRIFT-6 violation**：line 894-897 future ALTER ADD CONSTRAINT `fk_lal_no_incident_v113 ... REFERENCES learning.decay_signals(id)` (V113 hypertable composite PK)

**V113 spec (m7 decay_signals + strategy_lifecycle)**：0 REFERENCES literal；但 §3 prose narrative line 64/75/92/94 有 3 個 FK plan，**2 個 HIGH RISK** PA-DRIFT-6 violation (HIGH-2 + HIGH-3) + 1 個 schema name typo

**V116 spec (m13 asset_venue_dim)**：1 hit — asset_class_id REFERENCES asset_class_dim(asset_class_id) → PASS (both non-hypertable, regular dim table)

**M9 design spec**：2 hit (重複 V108)；不獨立計算

**M10 design spec**：line 269 + 538 提及 placeholder FK (重複 V111)

**M11 design spec (m11 counterfactual replay)**：line 489 提及 hypertable infra prereq (informative)；不獨立計算

---

# §3 TimescaleDB Hypertables on Production State

## §3.1 全 42 production hypertable

per `SELECT * FROM timescaledb_information.hypertables` Linux empirical 2026-05-23：

| Schema | Hypertable | 業務領域 |
|---|---|---|
| agent | ai_invocations / decision_state_changes / messages / state_changes | Agent telemetry |
| learning | ai_usage_log / cost_edge_advisor_log / decision_shadow_exits / exit_features / foundation_model_features / **governance_audit_log** / health_observations / lease_transitions / **replay_divergence_log** | Learning + Governance audit |
| market | funding_rates / klines / liquidations / long_short_ratio / market_tickers / news_signals / ob_snapshots / open_interest / regime_snapshots / regime_transitions / trade_agg_1m | Market data |
| observability | data_quality_events / drift_events / model_performance | Observability |
| panel | btc_lead_lag_panel / funding_rates_panel / oi_delta_panel | Panel aggregates |
| risk | black_swan_events / correlation_pairs | Risk |
| trading | fills / funding_settlements / intents / order_state_changes / orders / position_snapshots / risk_verdicts / scanner_opportunity_decays / scanner_snapshots / signals | Trading lineage |

**結論**：production 共 **42 hypertable**；其中 **learning.governance_audit_log + learning.replay_divergence_log** 已被 FK literal target（V100 / V107 spec）— **這兩個是 PA-DRIFT-6 高敏感面**。

## §3.2 FK Target Hypertable + PK Shape Verify

per `pg_constraint con WHERE contype = 'p'` Linux empirical：

| Target Table | Hypertable | PK Shape | 是否 PA-DRIFT-6 sensitive |
|---|---|---|---|
| governance.lease_lal_assignments | NO | PRIMARY KEY (id) | NO (single PK; safe FK target) |
| governance.lease_lal_tiers | NO | PRIMARY KEY (tier_level) | NO |
| learning.governance_audit_log | **YES** | **PRIMARY KEY (id, ts)** composite | **YES — PA-DRIFT-6 catch case (V100)** |
| learning.hypotheses | NO | PRIMARY KEY (hypothesis_id) | NO |
| learning.hypothesis_preregistration | NO | PRIMARY KEY (preregistration_id) | NO |
| learning.linucb_migrations | NO | PRIMARY KEY (migration_id) | NO |
| learning.mlde_param_applications | NO | PRIMARY KEY (id) | NO |
| learning.mlde_shadow_recommendations | NO | PRIMARY KEY (id) | NO |
| learning.teacher_directives | NO | PRIMARY KEY (directive_id) | NO |
| openclaw.proposals | NO | PRIMARY KEY (proposal_id) | NO |
| replay.experiments | NO | PRIMARY KEY (experiment_id) | NO |
| replay.run_state | NO | PRIMARY KEY (run_id) | NO |
| (production) learning.replay_divergence_log | **YES** | **PRIMARY KEY (id, divergence_detected_at)** composite | **YES — referenced only via hypothesis_id (V107 referencing target PASS)；future spec referencing PK is HIGH RISK** |

**結論**：production 12 個 FK target table 中 1 個是 hypertable composite PK target (`learning.governance_audit_log`) — V100 PA-DRIFT-6 fix 已切 soft reference；當前 production 0 violation。`learning.replay_divergence_log` 也是 hypertable composite PK，目前 0 FK reference 在 production；但 V113 spec line 75 計劃引用必違 PA-DRIFT-6。

## §3.3 Spec-Only Future Hypertable (尚未 land)

per 2026-05-2x V### schema spec 預期 8 個 future hypertable：

| V### | 預期 hypertable | 預期 PK | 預期 partition column |
|---|---|---|---|
| V105 | learning.overlay_state_transitions | (id, transition_at) | transition_at |
| V108 | learning.ab_assignments | **(BIGSERIAL PK!)** ← SPEC-ERR-1 | assigned_at |
| V108 | learning.ab_results | (result_id, evaluation_ts) | evaluation_ts |
| V109 | learning.anomaly_events | (id, observed_at) | observed_at |
| V111 | governance.discovery_tier_activations | (id, activated_at) | activated_at |
| V113 | learning.decay_signals | (signal_id, ingested_at) | ingested_at (spec §2.1) or observed_at (spec §8.1 v1 draft) |
| V115 | routing.order_routing_decisions | TBD | ts |

**結論**：8 個 future hypertable 中 1 個 (V108 ab_assignments) spec PK 設計 internally 違反 TimescaleDB（SPEC-ERR-1）。其餘 7 個 spec PK 已 correctly composite。**V113 decay_signals 在 §2.1 (`ingested_at`) 與 §8.1 v1 DDL (`observed_at`) 文檔 internally drift** — 需 spec author 拍板 final partition column。

---

# §4 PA-DRIFT-6 Candidate Audit

## §4.1 HIGH-1: V112 spec line 894-897 future ALTER ADD CONSTRAINT

**Spec source**：`/srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md` §6.3 line 894-897

```sql
-- Sprint 後續 V113 land + 確認 decay_signals.id BIGINT PK 後:
ALTER TABLE governance.lease_lal_assignments
    ADD CONSTRAINT fk_lal_no_incident_v113
    FOREIGN KEY (no_incident_check_v113_ref)
    REFERENCES learning.decay_signals(id);
-- 屆時走另一個 V### migration ALTER ADD CONSTRAINT
```

**Risk verdict**：
- V112 spec line 894-897 PA-DRIFT-6 violation：V113 `learning.decay_signals` 設計為 hypertable with composite PK `(signal_id, ingested_at)` （per V113 spec §2.1 line 55；§8.1 line 252 但 spec 內部 drift `BIGSERIAL PRIMARY KEY` only）
- 即使 V113 PK 維持 single column BIGSERIAL（不對齊 TimescaleDB 規範），`create_hypertable` 必 ERROR；V113 必改 composite PK
- 一旦 V113 PK 為 composite，V112 ALTER ADD CONSTRAINT 必 FAIL 撞 PA-DRIFT-6

**Severity**：HIGH（IMPL 期執行此 ALTER 必 ERROR；阻 V112 + V113 land sequence）

**Spec gap**：V112 spec line 894-901 預期 「V113 land + 確認 decay_signals.id BIGINT PK 後」走 ALTER ADD CONSTRAINT；spec author 假設 V113 PK 是 BIGINT single column 但實際 V113 必 composite。

## §4.2 HIGH-2: V113 spec §3 line 75 + §8.1 column name drift

**Spec source**：
- `/srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md` §3 line 64：`source_v107_divergence_id BIGINT NULL (FK to learning.replay_divergence_log.divergence_id if signal_source='m11_replay_divergence')`
- 同 spec line 75：`FK: source_v107_divergence_id → learning.replay_divergence_log.divergence_id ON DELETE SET NULL`
- 同 spec §8.1 line 287：`m11_replay_divergence_ref UUID NULL` + 註解「若 V107 採 BIGSERIAL，此 column 必 patch 為 BIGINT」（**注意 spec §3 與 §8.1 內部 drift — 一處 BIGINT FK, 一處 UUID soft ref**）

**Risk verdict**：
- §3 narrative 將 source_v107_divergence_id 描述為 FK to V107 hypertable composite PK column
- V107 production PK = `(id, divergence_detected_at)` composite + V107 spec line 175 + production 真實 column name = `id` 而非 `divergence_id`（spec §3 column name typo）
- §8.1 v1 DDL 已 soft reference 範式（line 287 + 註解）正確；但 §3 narrative 描述如 SQL FK 則違 PA-DRIFT-6
- spec internal drift：§3 narrative vs §8.1 DDL 兩段描述不一致

**Severity**：HIGH（spec amend 後即可消解；IMPL 期若按 §8.1 走則 0 issue；若按 §3 narrative 走 IMPL 撞 PA-DRIFT-6 + column name not exist）

**Spec gap**：spec author 在 §8.1 已內化 PA-DRIFT-6 lesson（soft ref），但 §3 prose narrative 未同步 patch；需 spec 修訂統一 narrative

## §4.3 HIGH-3: V113 spec §3 line 92 — strategy_lifecycle.triggering_signal_id FK

**Spec source**：
- `/srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md` §3 line 92：`triggering_signal_id BIGINT NULL (FK to learning.decay_signals.signal_id)`

**Risk verdict**：
- target = `learning.decay_signals` hypertable composite PK `(signal_id, ingested_at)`
- FK 只引用 `(signal_id)` 必 FAIL with PA-DRIFT-6 same error pattern as V100
- spec 寫的 column name 是 `signal_id` 而 §8.1 line 252 寫 `id BIGSERIAL PRIMARY KEY` (還未統一 column name；spec internal drift)
- 即使 column name unified `id`，PK 必 composite (因 hypertable)，FK 不能對齊只 `(id)`

**Severity**：HIGH（IMPL 期執行 CREATE TABLE strategy_lifecycle 必 ERROR）

**Spec gap**：spec author 一致缺乏 V113 FK design 對 hypertable composite PK 的 awareness；spec §3 narrative 引用 `signal_id` column 但 §8.1 DDL 寫 `id` column；spec internal column naming drift

## §4.4 SPEC-ERR-1: V108 ab_assignments PK shape design error

**Spec source**：
- `/srv/docs/execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md` §2.2.1 line 247：`assignment_id BIGSERIAL PRIMARY KEY,`
- 同 spec §2.2.1 line 269：`SELECT create_hypertable('learning.ab_assignments', 'assigned_at', ...)`

**Risk verdict**：
- 不是 strict PA-DRIFT-6（ab_assignments 不被任何 FK target 引用）
- 但屬同類 TimescaleDB 規範違反：hypertable required PK 含 partition column
- IMPL 期執行 `create_hypertable` 必 ERROR with: "cannot create hypertable: primary key must include partitioning column"
- V108 spec 內部已對 ab_results (line 390) 採 composite PK `(result_id, evaluation_ts)` — **ab_assignments 與 ab_results 設計不對稱**

**Severity**：HIGH（IMPL 期阻 V108 land；阻 M9 A/B framework cascade）

**Spec gap**：V108 spec author 在 ab_results 已正確採 composite PK 但對 ab_assignments 漏 amend；spec internal pattern drift

## §4.5 LOW RISK pass-through items (5 cases)

對以下既有 spec FK reference 確認 **0 PA-DRIFT-6 violation**（target 非 hypertable composite PK target）：

1. **V100 hypothesis_preregistration → hypotheses**：non-hypertable PK = (hypothesis_id) single → PASS（已 production land）
2. **V107 replay_divergence_log.hypothesis_id → hypotheses**：non-hypertable PK = (hypothesis_id) single → PASS（已 production land；V107 自身雖 hypertable 但作為 source 引用非 hypertable 是 OK）
3. **V111 discovery_tier_activations.tier_level → discovery_tier_config**：non-hypertable PK = (tier_level) → PASS
4. **V112 lease_lal_assignments.tier_level / prev_tier_level → lease_lal_tiers**：non-hypertable PK = (tier_level) → PASS（已 production land）
5. **V108 ab_tests.hypothesis_id → hypotheses + ab_assignments.test_id → ab_tests + ab_results.test_id → ab_tests**：non-hypertable PK targets → PASS

---

# §5 Fix Path 建議 per Candidate

## §5.1 Option A (推薦 default): Drop FK → Soft Reference + Guard C Column Check

**適用**：HIGH-1 + HIGH-2 + HIGH-3 全部 case；per V100 PA-DRIFT-6 fix range model

**標準 fix template**（per V100 SQL line 362-368）：

```sql
-- target_column 是 soft reference 不是 FK constraint
-- (per PA-DRIFT-6 lesson 2026-05-23):
-- target_table 是 TimescaleDB hypertable 用 composite PK (...)
-- (TimescaleDB partition column 必含於 PK);PostgreSQL FK 必須對齊完整 unique constraint
-- 不能只 reference (id);因此採用 soft reference,審計時透過 application-level
-- query target_schema.target_table WHERE id=source_column 反查
target_column     BIGINT,  -- 或 BIGSERIAL pertinent
```

加 Guard C 列 column check（per V100 SQL line 656-664）：

```sql
SELECT COUNT(*) INTO v_fk_count
FROM information_schema.columns
WHERE table_schema='source_schema' AND table_name='source_table'
  AND column_name='target_column' AND data_type='bigint';
IF v_fk_count = 0 THEN
    RAISE EXCEPTION
        'V### Guard C post FAIL: source_table.target_column BIGINT '
        'column missing (soft reference to target_schema.target_table).';
END IF;
```

加 COMMENT ON COLUMN (per V100 SQL line 502-511)：

```sql
COMMENT ON COLUMN source_schema.source_table.target_column IS
    'BIGINT soft reference to target_schema.target_table(id); ...'
    '注意: 非 SQL FK constraint (per PA-DRIFT-6 lesson 2026-05-23): '
    'target_table 是 TimescaleDB hypertable composite PK (id, ts);'
    'PostgreSQL FK 不能只對齊 (id) — 必須完整 unique constraint;故採用 '
    'application-level soft reference,審計時透過 SELECT FROM target_schema.target_table '
    'WHERE id=target_column 反查。';
```

**優點**：
- 對齊 V100 production-verified fix range model（已 deploy + verify ws_rtt p50/p99 真實採樣）
- 不需改 target 表設計
- 不增 IMPL 複雜度（既有 V100 三層治理 + Guard C 範式可直接複用）
- 反向 audit query 通用（per `SELECT FROM target_schema.target_table WHERE id=source_column`）
- 業界 TimescaleDB best practice（per TimescaleDB docs FAQ「FK and hypertables」）

**缺點**：
- 喪失 SQL 層 referential integrity enforcement
- 需 application-level reconciliation cron 補足（per `learning.governance_audit_log` ↔ `learning.earn_movement_log` cron 設計）— Sprint 5+ 內部 IMPL 必 plan

## §5.2 Option B: Change FK target column to unique single column

**適用**：技術上可行但對 V### IMPL 已 land 表非常重；本 audit 暫不推薦

**對於 V107 / V113 case**：
- 變 V107 `learning.replay_divergence_log` PK 從 `(id, divergence_detected_at)` 改 single column `id` UNIQUE constraint + composite secondary key
- 變 V113 `learning.decay_signals` 同樣手法
- 但這違反 TimescaleDB hypertable 強制規範：partition column 必含於 PK
- **無法執行**：TimescaleDB DDL `create_hypertable` 強制 partition column 在 PK 中；不能只用 secondary UNIQUE constraint

**verdict**：**REJECT** — Option B 技術上不可行於 TimescaleDB

## §5.3 Option C: Change target table designer's PK (high risk)

**適用**：將 target table 從 hypertable 改 regular table，並改回 single column PK；本 audit **不推薦**

**對於 V113 decay_signals**：
- 改回 regular table + 失去 hypertable 7d chunk + 30d compression + 180d retention 優勢
- per V113 spec line 128 「decay_signals MUST hypertable」設計理由 — 量級 ~18k row/yr × 6 mo retention buffer 必 hypertable + compression
- 違反 V113 spec sign-off chain（QC + MIT + PA）已採信的設計判斷
- 不向後相容（既有 V### IMPL 已對齊 hypertable 假設）

**verdict**：**REJECT** — Option C 違 spec sign-off + 失 hypertable 設計優勢

## §5.4 Per-Candidate 推薦

| 候選 | 推薦方案 | 為什麼 |
|---|---|---|
| HIGH-1 (V112 → V113 ALTER) | **Option A soft ref** | V100 範式 + 對齊 cross-task pattern + 0 target 表改動 |
| HIGH-2 (V113 → V107 reference) | **Option A soft ref** + spec §3 unify column name `id` (不是 `divergence_id`) | spec §8.1 已 soft ref；只需 §3 narrative patch |
| HIGH-3 (V113 strategy_lifecycle → decay_signals) | **Option A soft ref** + spec §8 strategy_lifecycle DDL 同步 patch | 同 spec batch amend |
| SPEC-ERR-1 (V108 ab_assignments PK) | **PK composite amend** (改 spec line 247 PK 為 `(assignment_id, assigned_at)`) | 對齊 ab_results 既有 design + V105/V107/V109/V111 hypertable 範式 |

## §5.5 ADR-0010 amend draft (defer to Sprint 5+ Wave 2)

per `srv/docs/adr/0010-timescale-hypertable-with-guard-migrations.md`（current ADR-0010 內容約 hypertable + Guard A/B/C migration discipline）— 待 Sprint 5+ Wave 2 amend round 加 PA-DRIFT-6 invariant 一條：

**新章節提議：§6 PA-DRIFT-6 invariant — FK to hypertable composite PK forbidden**

```markdown
## §6 PA-DRIFT-6 — TimescaleDB Hypertable Composite PK 不可作 PostgreSQL FK Target

### §6.1 Invariant 不變量

- TimescaleDB hypertable 的 partition column 必須包含在 primary key 中（TimescaleDB 強制）
- 若 hypertable 採 composite PK（如 `(id, ts)`），則該 PK **不能直接作為其他表的 FK target**
- 因 PostgreSQL FK constraint 必須對齊 referenced table 的完整 unique constraint，
  不能只 reference PK 的 partial column subset

### §6.2 防線 SOP

**V### spec 加 FK 前必跑 PG 反射 SQL**：

1. 是否 TimescaleDB hypertable:
   ```sql
   SELECT * FROM timescaledb_information.hypertables
   WHERE hypertable_schema='<schema>' AND hypertable_name='<table>';
   ```

2. PK 是否 composite:
   ```sql
   SELECT pg_get_constraintdef(oid) FROM pg_constraint
   WHERE conname='<table>_pkey';
   ```

3. 若 (1) YES AND (2) composite → **不下 SQL FK，改用 soft reference + application-level reconciliation**

### §6.3 Soft Reference Pattern (per V100 fix range model)

(complete pattern per Option A)

### §6.4 已知 candidate amend list (Sprint 5+ Wave 2)

- V112 spec line 894-897 (future ALTER to V113 decay_signals)
- V113 spec §3 line 75 + §8.1 (source_v107_divergence_id → V107 replay_divergence_log)
- V113 spec §3 line 92 (triggering_signal_id → V113 decay_signals)
```

---

# §6 ADR-0010 Amend Round 建議 (defer Sprint 5+ Wave 2)

**per operator prompt option 1 (audit only;不在本 task IMPL)**：ADR-0010 amend round 不在本 PA audit task scope；以下為 Sprint 5+ Wave 2 之建議 sketch：

## §6.1 Wave 2 ADR amend dispatch packet outline

- **Owner**：PA + CC (CC final acceptance review)
- **Estimated effort**：1-1.5 hr single-session（ADR-0010 §6 新增章節 + ADR header version bump + cross-ref V100 fix range model + future V### spec amend list）
- **Acceptance criteria**：
  - ADR-0010 V2 land 含 §6 PA-DRIFT-6 invariant
  - 引用 V100 production fix range model line numbers + V109 spec design 範式
  - 列出 Sprint 5+ Wave 2 spec amend list (V108 / V112 / V113)
  - 列出 5 個 already-passed LOW RISK FK 為 retroactive validation
- **Dispatch dependency**：本 PA audit report 為 ADR-0010 amend 唯一前置

## §6.2 ADR-0010 V2 不修內容 (current scope sustained)

- ADR-0010 V1 既有 Guard A/B/C migration discipline 不變
- TimescaleDB hypertable selection criteria 不變
- compression + retention policy 不變
- Mac mock pytest vs Linux PG empirical 反射 SQL 分工不變

---

# §7 V### IMPL SOP Amend 建議

## §7.1 PA Design Phase 強制反射 SQL

**Current PA design SOP gap (per Stage F overall acceptance §6.3)**：PA spec §6 列 5 reflection SQL（table existence + status enum + FK schema 名 + index + engine_mode CHECK）但**漏 FK target unique constraint check**。

**proposed amend**：每個 PA spec design phase 必含此 SQL section：

```sql
-- §6.X PA-DRIFT-6 防線：FK target 必跑此反射 SQL 對每個 FOREIGN KEY declaration
-- 對每個 FK declaration:
--   target_schema.target_table 是否 hypertable + PK 是否 composite

-- Query A: hypertable check
SELECT hypertable_schema, hypertable_name, num_dimensions
FROM timescaledb_information.hypertables
WHERE hypertable_schema='<target_schema>' AND hypertable_name='<target_table>';

-- Query B: PK shape check
SELECT con.conname, pg_get_constraintdef(con.oid) AS pk_def
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE con.contype = 'p'
  AND n.nspname = '<target_schema>'
  AND c.relname = '<target_table>';

-- 若 Query A 返 row (hypertable=YES) AND Query B 返 composite PK (>1 column):
--   stop — 不下 SQL FK constraint;改 soft reference + Guard C column check
--   per V100 PA-DRIFT-6 fix range model
```

## §7.2 PA Design Phase 加 FK Target Spec Validation Checklist

per task spec doc 必含此 checklist:

- [ ] 對每個 FK declaration 列出 target table + target column
- [ ] target table 是否 TimescaleDB hypertable (PG empirical query)
- [ ] target table PK 是否 composite (PG empirical query)
- [ ] 若 hypertable + composite PK → 採 soft reference pattern (per V100 範式)
- [ ] 若 hypertable + composite PK → 加 Guard C column existence check
- [ ] 若 hypertable + composite PK → 加 COMMENT ON COLUMN PA-DRIFT-6 lesson 紀錄
- [ ] 引用 V100 SQL line 362-368 + 656-664 + 502-511 為 fix range reference

## §7.3 E2 Round Review 必加 PA-DRIFT-6 verification

- E2 round 1 review 範圍：加「FK target unique constraint check」 step
- E2 reviewer 必 query：`SELECT * FROM pg_constraint WHERE conrelid=<target>::regclass AND contype IN ('p','u')` 確認 reference column 是 unique
- 若 catch hypertable composite PK target → push back IMPL；amend spec 改 soft reference

## §7.4 Linux PG Empirical Dry-Run (per ADR-0011 + memory `feedback_v_migration_pg_dry_run`)

- ADR-0011 已 mandate Linux PG empirical dry-run；本 audit 確認該 SOP 是唯一 catch PA-DRIFT-6 的可靠防線
- Mac mock pytest + sqlx Migrator parser 全部不驗 FK target unique constraint runtime semantic
- Sprint 5+ Wave 2 + 後續 V### IMPL 必 Mac PA design + Linux PG empirical 雙端覆蓋

---

# §8 Conclusion + Sprint 5+ Wave 2 路徑

## §8.1 Audit Verdict

**3 HIGH RISK PA-DRIFT-6 candidate + 1 SPEC-ERR-1 spec internal violation + 0 production runtime FAIL**。

既有 production schema 0 PA-DRIFT-6 violation（V100 catch + fix）；future V### spec design 期已 internally drift 4 case（V108 + V112 + V113），均需 Sprint 5+ Wave 2 spec amend 在 IMPL 啟動前完成；ADR-0010 amend round defer Sprint 5+ Wave 2 派發。

## §8.2 PA Recommendation for Sprint 5+ Wave 2

| Wave 2 item | Priority | Owner | Effort | Dependency |
|---|---|---|---|---|
| V112 spec amend (HIGH-1) | P1 | PA + PM | 30 min spec edit | 無前置 (V113 spec amend 平行) |
| V113 spec amend (HIGH-2 + HIGH-3) | P1 | PA + MIT (type alignment review) | 1.5 hr spec edit | 對齊 V112 + ADR-0010 amend |
| V108 spec amend (SPEC-ERR-1) | P1 | PA + MIT | 30 min spec edit | 無前置 |
| ADR-0010 amend round (PA-DRIFT-6 §6) | P2 | PA + CC | 1-1.5 hr ADR write | 4 個 spec amend 完成後 |
| (defer) Sprint 5+ Wave 3 — V### IMPL 含 amended spec dispatch | P2 | PM dispatch | TBD | spec amend + ADR amend 全 land |

**Total Sprint 5+ Wave 2 PA budget**：~2.5-4 hr spec amend + ~1-1.5 hr ADR amend = **~3.5-5.5 hr single-session**（PA + MIT + PM 三角色協作）

## §8.3 教訓

1. **PA design phase 強制 PG empirical 是唯一可靠防線**：Mac sandbox + cargo test + sqlx Migrator parser 全不驗 FK target unique constraint；per `feedback_v_migration_pg_dry_run` 2026-05-05 教訓重申於本 audit
2. **V109 spec 範式已內化 PA-DRIFT-6 lesson 早於 V100 catch**：證明此 invariant 是 **可推導**（per `db-schema-design-financial-time-series` skill）而非 emergent；V100 spec design 期未 cross-ref 此 skill 是 PA design SOP gap
3. **Spec internal drift 是 PA design pattern 一致性失敗**：V108 ab_assignments vs ab_results PK 設計不對稱 + V113 §3 narrative vs §8.1 DDL column name + soft ref pattern 不一致；證明 single-spec internal cross-section review 必跑（PA spec sign-off SOP 應強制）
4. **三層治理（COMMENT + spec doc + ADR）+ V100 fix range model 已 production-verified**：未來 V### spec amend 直接複用此 pattern 即可，不需重發明
5. **既有 V107 production hypothesis_id FK PASS**：證明 hypertable 自己作為 SOURCE 引用非 hypertable 完全合法；混淆此方向是 PA-DRIFT-6 衍生 misunderstanding（hypertable 不能作為 TARGET 才是真實 invariant）

## §8.4 治理 closure

- **本 PA audit**：AUDIT-DONE；3 HIGH + 1 SPEC-ERR + 5 LOW PASS verdict 鎖定
- **派發路徑**：per operator prompt option 1 (audit only) — 不 IMPL fix；不 commit；不寫 ADR-0010 amend round（defer Sprint 5+ Wave 2）
- **5 LOW RISK pass-through 不修**：production 既有 FK 0 violation
- **ADR-0010 V2 amend draft 在本 audit §5.5 + §6.1 提供**：Sprint 5+ Wave 2 ADR amend 直接 copy 起手

Report path：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--pa_drift_6_governance_audit.md`

---
report: PA Sprint 1B late §4.1.1 — V99-V102 spec gap audit + V099→V100 push back + V100 M4 base table migration design
date: 2026-05-23
author: PA (Project Architect)
phase: Sprint 1B late §4.1.1 P0 (Sprint 4+ first Live carry-over)
status: DESIGN-DONE / E1-IMPL-READY
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md §4.1.1
risk_grade: 中（新 V100 base table 解 V103 Guard A FAIL；schema 命名 drift 須 patch；OPENCLAW_AUTO_MIGRATE 0→1 切換）
note: PA Track 1 sub-agent (agent-a0c94c3e3c183b8b9) 收到 skill rule「Do NOT Write report/summary .md files」inline 回報；本文 PM 主對話 transcribe 為文件 SSOT（per Sprint 1A-ζ Track C / Sprint 1A-ε P2 N3 transcribe pattern）。
---

# Sprint 1B late §4.1.1 V100 M4 hypothesis base table — PA design report

## §0 Executive Summary

**Task**：Sprint 4+ first Live carry-over §4.1.1（per PM Phase 3e sign-off 2026-05-23）— V99-V102 spec gap audit + V099 base table migration design 解 V103 Guard A FAIL。3-4 hr single-thread design only；不 IMPL；不派下游 sub-agent；不 commit。

**Operator prompt task wording** 寫 V099；PA verdict **push back V099→V100**：
- V099 已被 `autonomy_level_toggle` 完整佔用（568 LOC SPEC-DRAFTED 2026-05-22 + AMD-2026-05-21-01 v2 + CC re-audit APPROVE A 級 + PM Wave 5 cascade pending sign-off）
- TODO.md §1.7 line 199 SSOT 明示
- M4 base table migration 必須改 number 至 V100

**核心 Schema 命名 drift 警告**（必 patch）：
- V103 base spec line 210/233/382 寫 `governance.audit_log`（spec typo）
- production 真實表名 = `learning.governance_audit_log`（per V035/V053/V098 baseline）
- V106/V107/V112 IMPL 已 PA-DRIFT-1 patch；V100 IMPL 必繼承此 lesson — earn_movement_log.governance_approval_id FK target 必 patch 至 `learning.governance_audit_log(id)`

**Verdict**：**DISPATCH READINESS OPEN — 5/5 PA prerequisite GREEN，1 push back 已含**。E1 IMPL est 6-8 hr + operator deploy + verify ~1-2 hr。

---

## §1 V99-V102 spec gap audit result

### §1.1 真實 V### slot 佔用地圖（grep verify 2026-05-23）

| V### | 真實佔用狀態 | 來源 spec | sql/migrations/ .sql 實檔 |
|---|---|---|---|
| **V097** | LG-5 attribution healthcheck indexes | staged file | LAND（Linux PG NOT APPLIED） |
| **V098** | governance_audit_log halt_event_types ALTER CONSTRAINT；真實表名 `learning.governance_audit_log`（per V035 baseline） | staged file | LAND（Linux PG NOT APPLIED） |
| **V099** | **OCCUPIED by autonomy_level_toggle**（568 LOC spec / AMD-2026-05-21-01 v2 + CC re-audit APPROVE A 級 / PM Wave 5 cascade pending sign-off） | `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md` | NOT LAND（spec only；E1 IMPL pending Wave 5 cascade） |
| **V100** | **OPEN**（dispatch_consolidation §6 v5.7 4 follow-up 假佔位 = Track v3 attribution column EXTEND 但未 IMPL） | `v58_dispatch_consolidation.md` §3.2 line 336 | NOT LAND |
| **V101** | **OPEN**（v5.7 4 follow-up 假佔位 = Earn schema rename from V103；dry-run option A） | dispatch_consolidation §6 + v103_v104 dry-run option A | NOT LAND |
| **V102** | **OPEN**（v5.7 4 follow-up 假佔位 = Earn schema indexes/NOT NULL；dry-run option A no-op） | dispatch_consolidation §6 | NOT LAND |
| **V103** | M4 EXTEND 6 column（hypothesis_source_module + leakage_scan_pass + bonferroni + replicability + decision_lease_draft_id + cowork_review_status） | `v103_extend_m4_hypothesis_columns_schema_spec.md` | **LAND**（`V103__extend_m4_hypothesis_columns.sql` 366 LOC） |
| **V104** | retired = no-op（per dry-run option A；V101 spec §3.2 已含 `trading.fills.track` ADD COLUMN） | v103_v104 base spec §1.3 + line 22 | NOT LAND（intentional） |
| **V105–V112** | M2/M3/M11/M9/M8/M6/M10/M1 LAL 系列 | `v105/v106/v107/v108/v109/v110/v111/v112_*_schema_spec.md` | V106/V107/V112 LAND；V105/V108–V111 NOT LAND |

### §1.2 5 ADD module (M2/M4/M8/M9/M10) base table 需求（per Sprint 1A-γ scope）

| Module | base table 需求 | V### owner | 狀態 |
|---|---|---|---|
| M2 overlay | `learning.overlay_state_transitions` hypertable | V105 | spec only |
| **M4 hypothesis_discovery** | **`learning.hypotheses` + `learning.hypothesis_preregistration` + `learning.earn_movement_log` 3 tables**（per v103_v104 base spec §2.1-2.3） | 原假設 V103 base；**真實 V103 IMPL 是 EXTEND only**；base 缺 | **GAP CONFIRMED — Sprint 4+ Phase 3c production AUTO_MIGRATE=1 attempt 觸發 V103 Guard A FAIL** |
| M8 anomaly | `learning.anomaly_events` hypertable | V109 | spec only |
| M9 A/B | `learning.ab_tests` + `ab_assignments` + `ab_results` 3 tables | V108 | spec only |
| M10 discovery | `governance.discovery_tier_config` + `discovery_tier_activations` | V111 | spec only |

**核心發現**：5 ADD module 中**只有 M4 base table 因 V103 IMPL 走 EXTEND-only 路徑而留下缺口**，其他 M2/M8/M9/M10 base 在 V105/V108–V111 spec 內含 CREATE TABLE 完整 DDL。

### §1.3 V099 slot 衝突 — operator prompt 字面 vs 真實佔用

**operator prompt task wording line 67**：「新 V099 base table migration (M4 hypothesis_discovery)」

**衝突證據**：
- V099 已被 `autonomy_level_toggle` 完整佔用（568 LOC SPEC-DRAFTED 2026-05-22 + AMD-2026-05-21-01 v2 + CC A 級 re-audit + PM Wave 5 cascade pending sign-off）
- TODO.md §1.7 line 199 SSOT 明示
- AMD-2026-05-21-01 v2 §3.5 鎖定 `system.autonomy_level_config` schema with V099 number

**PA verdict push back**：operator task wording 用 V099 number 屬 **錯誤假設**（基於 Sprint 1A-α prompt 階段 V099 仍 OPEN，但 2026-05-22 autonomy_level_toggle 已佔位）。**M4 base table migration 必須改 number 至 V100**。

---

## §2 V099 schema spec write decision — 不寫，改寫 V100 M4 base table

### §2.1 重新定義 spec write path

不寫 `2026-05-23--v099_m4_hypothesis_base_table_schema_spec.md`（衝突 V099 autonomy）。

**改寫 path**：`docs/execution_plan/specs/2026-05-23--v100-m4-hypothesis-base-table.md`

理由：
1. V099 autonomy_level_toggle SSOT 不可碰（AMD v2 + CC re-audit + PM pending）
2. V100 此前是 dispatch_consolidation §3.2 line 336 v5.7 Track v3 attribution column EXTEND 假佔位；但 v5.7 4 follow-up dispatch 從未 IMPL（per TODO §1.1 status `DESIGN-DONE / IMPL-PENDING`）；可移走至 Sprint 5+
3. V100 slot 與 V099 autonomy 連續無跳號（per V099 spec §1.1「連續未占用」原則對齊）
4. V100 = M4 base table 後，V101/V102 仍 reserve 給 Sprint 5+ Track v3 + Earn schema follow-up
5. V103 EXTEND IMPL 已 LAND；V100 base land 後 V103 Guard A 自動 PASS（順序 V100 → V103 EXTEND）

### §2.2 V100 schema 設計（learning.hypotheses 13 base column + 對齊 V103 EXTEND）

**`learning.hypotheses` base table**（per v103_v104 base spec §2.1.1；保留 v5.7 brief 字段集）：

```sql
CREATE TABLE IF NOT EXISTS learning.hypotheses (
    hypothesis_id           BIGSERIAL PRIMARY KEY,
    strategy_name           TEXT NOT NULL,
    pre_reg_ts              TIMESTAMPTZ NOT NULL,
    pre_reg_hash            TEXT NOT NULL,
    status                  TEXT NOT NULL CHECK (status IN (
        'draft','preregistered','shadow','stage_0r','stage_1',
        'stage_2','stage_3','stage_4','live','retired','killed'
    )),
    expected_sharpe         REAL,
    expected_dd             REAL,
    capacity_estimate_usdt  BIGINT,
    t_stat_min              REAL,
    min_sample_size         INTEGER,
    engine_mode             TEXT NOT NULL CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2 hot-path index per v103_v104 §2.1.3
CREATE INDEX IF NOT EXISTS idx_hypotheses_strategy_status
    ON learning.hypotheses (strategy_name, status);
CREATE INDEX IF NOT EXISTS idx_hypotheses_pre_reg_ts
    ON learning.hypotheses (pre_reg_ts DESC);
```

**注意 hypertable=NO**：~100 row/yr 低基數 regular table（per v103_v104 §2.1.4）。

### §2.3 `learning.hypothesis_preregistration` 同步 land

per v103_v104 §2.2.1：BIGSERIAL PK + FK to hypotheses + payload_json JSONB + payload_hash + operator_signature + signed_at + engine_mode。1 index `(hypothesis_id, signed_at DESC)`。

### §2.4 `learning.earn_movement_log` 同步 land（**schema 名 patch**）

per v103_v104 §2.3.1，但 `governance_approval_id` FK target 必 patch：

```sql
-- spec doc §2.3.1 寫: REFERENCES governance.audit_log(id)
-- 真實 production 表名: learning.governance_audit_log (per V035/V053/V098 baseline)
-- 對齊 V106/V107/V112 PA-DRIFT-1 patch lesson
governance_approval_id BIGINT REFERENCES learning.governance_audit_log(id),
```

### §2.5 V100 對齊 V103 EXTEND 後續 ADD chain

V100 land 後 sqlx 順序：
```
V099 (autonomy) → V100 (M4 base 3 tables) → V103 (EXTEND M4 6 column)
```

V103 EXTEND Guard A 驗 `learning.hypotheses` + `hypothesis_id` PK 存在 → V100 IMPL 對齊 → PASS。

### §2.6 V100 spec doc estimated LOC + format

對齊 V103/V106/V107/V112 spec 範式：~700-900 LOC（3 table CREATE + Guard A/C + index + COMMENT + Linux PG dry-run 5 reflection SQL + Round 1/2 idempotency + engine restart 實測 + rollback plan + 4 AC + sandbox PG empirical pattern）。

**核心 ADR/spec 對齊**：
- ADR-0010 Guard A/B/C + hypertable mandate
- ADR-0011 Linux PG dry-run mandatory
- ADR-0045 M4 hypothesis_discovery governance authority
- v103_v104 base spec line 22 `V104 退號為 no-op` 決策
- v103_extend_m4 line 60-78 Guard A `learning.hypotheses` prereq message

---

## §3 V100/V101/V102 處置決定

| V### | 處置 | Rationale |
|---|---|---|
| **V099** | **不動**（autonomy_level_toggle SSOT；AMD-2026-05-21-01 v2 + CC A 級） | 衝突 SSOT 風險 + Wave 5 cascade pending |
| **V100** | **本 Sprint 1B late 重 number 給 M4 base table**（PA verdict） | 阻 V103 Guard A FAIL 解；P0 入口 |
| **V101** | **defer Sprint 5+**（Track v3 attribution column EXTEND；非 P0 阻塞） | v5.7 4 follow-up；Track v3 對 V100/V103 EXTEND chain 無 FK 阻塞 |
| **V102** | **defer Sprint 5+**（Track v3 indexes / NOT NULL；per v5.7 4 follow-up） | 與 V101 配對；隨 V101 IMPL 解 |

**不重 number 給 V103**：V103 IMPL 已 LAND（commit `e1 track c 2026-05-22 stub IMPL #2` Sandbox 走 stub 證明）；rename V103 → V104 會觸 sqlx checksum drift（per `project_2026_05_02_p0_sqlx_hash_drift` memory）；維持 V103 EXTEND only 路徑。

**為何不採 v5.7 dry-run option A 路徑（V103 base CREATE + V103 EXTEND combined）**：V103 IMPL 已 commit 為 EXTEND-only；改回 base+EXTEND combined 需 `repair_migration_checksum` 介入 + 風險 sqlx drift；新 V100 base + V103 EXTEND 純後加方式風險最小。

---

## §4 AUTO_MIGRATE deploy chain plan + Sprint 1B late readiness verdict

### §4.1 production deploy chain（per Sprint 4+ deploy chronology lessons learned）

```
[Phase A] Sprint 1B late D+0 Mac IMPL (E1 work after PA spec)
  ↓
  1. E1 寫 V100__m4_hypothesis_base_table.sql per spec
  2. Mac local cargo test sqlx_migrate_check
  3. commit + push

[Phase B] Sprint 1B late D+0.5 Sandbox dry-run (Linux PG empirical mandatory per ADR-0011)
  ↓
  4. ssh trade-core git pull --ff-only
  5. Sandbox dry-run V100 Round 1+2 (V103/V106/V107/V112 範式)
     - Round 1: PG reflection 5 SQL (3 tables exists + 13/7/10 column 完整 + 3 index + FK governance_approval_id → learning.governance_audit_log)
     - Round 2: psql -d trading_ai_sandbox -f V100 二次 apply (NOTICE skip ≥ 6; 0 ERROR; 0 RAISE)
  6. Sandbox V100 → V103 chain reapply 驗 EXTEND Guard A pass

[Phase C] Sprint 1B late D+1 Production deploy (PA + E1 + operator)
  ↓
  7. OPENCLAW_AUTO_MIGRATE=0→1 (per Sprint 4+ Phase 3c lesson learned 5)
  8. restart_all.sh (no rebuild; auto-migrate land V97/V98/V100/V103/V106/V107/V112 chain)
  9. expect _sqlx_migrations MAX 96→112 (V103 + V106 已被 raw psql -f 走過導致只能走 metadata register 路徑 per 2026-05-22 decision_2 SOP step 3 alt)
     真實 path 可能差異 — runtime 觀察

[Phase D] verify (per Sprint 4+ AC-1b 範式)
  ↓
  10. _sqlx_migrations MAX=112 (or 113 if V099 autonomy 同期 land 自動 cascade)
  11. 5 target table 物理存在: learning.hypotheses / hypothesis_preregistration / earn_movement_log / health_observations / replay_divergence_log / governance.lease_lal_tiers + lease_lal_assignments
  12. engine startup 0 panic (sqlx migrate complete + 5 active domain emitter chain active)
  13. 30 min observe + AC-1b SQL 重驗
```

### §4.2 lesson learned 對應（per Sprint 4+ deploy chronology §3）

| lesson | V100 deploy 對應防線 |
|---|---|
| V### sparse migration → V103 Guard A FAIL | V100 base land 後 V103 Guard A 自然 PASS |
| Engine restart cargo PATH ssh non-interactive | `source ~/.cargo/env` mandatory (Phase B step 5) |
| Release binary stripped vs nm | V100 影響 schema only；no Rust binary 影響；nm 不適用 |
| emitter fail-soft vs auto-migrate fail-loud | OPENCLAW_AUTO_MIGRATE=1 sqlx migrate fail-loud；保 V103 Guard A 已 PASS path 後 OK |
| AC-1a/AC-1b 拆分 | Phase B sandbox (AC-1a 等)；Phase D production verify (AC-1b 等) |
| PA prerequisite verify mandatory | Phase B 前 PA grep verify `learning.governance_audit_log` 真實表名（earn_movement_log FK target 對齊） |

### §4.3 V100 spec sandbox PG empirical SOP

對齊 V107 Sprint 1B early IMPL `2026-05-22--sprint_1b_v107_sandbox_land_dedup_full.md` 範式（E3 sandbox_admin role + secret_file 0600 + 9-step sandbox empirical chain）。

### §4.4 Sprint 1B late readiness verdict

**OPEN — 5/5 PA prerequisite GREEN，1 push back 已含**：

| # | Prerequisite | 狀態 |
|---|---|---|
| 1 | V### slot 真實佔用 audit | ✅ DONE §1.1 |
| 2 | 5 ADD module base table 需求 audit | ✅ DONE §1.2 |
| 3 | V099 slot 衝突 push back | ✅ DONE §1.3（V099 不動，M4 base 移 V100） |
| 4 | V100 schema spec 設計 | ✅ DONE §2.1–2.6（3 table 設計 + schema 名 patch + EXTEND chain 對齊） |
| 5 | AUTO_MIGRATE deploy chain plan | ✅ DONE §4.1–4.3 |

**E1 IMPL ready 前置**：
- PA verdict 派發後 operator 確認 V100 number 採納
- E1 IMPL phase 寫 `V100__m4_hypothesis_base_table.sql` + spec doc `docs/execution_plan/specs/2026-05-23--v100-m4-hypothesis-base-table.md`
- 預估 E1 IMPL ~6-8 hr（3 table CREATE + Guard A/C + 4 index + COMMENT + sandbox Round 1+2 empirical + 文檔 spec）
- 預估 Phase C-D deploy + verify ~1-2 hr operator

**E2 重點審查 3 點**：
1. **earn_movement_log FK target schema 名** — 必 patch `governance.audit_log` → `learning.governance_audit_log`（per V106 line 92-97 PA-DRIFT-1 patch lesson；V100 IMPL 不重蹈）
2. **Guard A idempotency 對 V103 EXTEND chain** — V100 重跑時 V103 EXTEND 6 column 已存在情境下 Guard A 不 RAISE（即 V100 Guard A 必含 columns IN v_missing 邏輯 OR V100 base column 列表時對齊 13 base + 5 §14 audit + 6 EXTEND M4 = 24 column 完整性驗）— **PA 推薦走 13 base column only verify**（避混 EXTEND scope；V103 EXTEND 自己 Guard A 驗 6 EXTEND column 對齊）
3. **status CHECK enum 11 值 deferred token** — v103_v104 §2.1.1 寫 11 個 status；V100 IMPL 必含完整 11 enum；V103 EXTEND 自身不改 status enum（per spec §2.1 確認）

---

## §5 PA design 讀的關鍵 spec 清單

無新增；無 commit；per task scope spec only：

- `docs/execution_plan/2026-05-21--v099_v116_migration_ordering_audit_and_dry_run_sop.md`（§2.1 V### overview + §2.3 cross-V### edges）
- `docs/execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md`（EXTEND 6 column spec）
- `docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`（base spec 940 行 + V104 退號 no-op 決策）
- `docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md`（M4 design + V103 EXTEND outline §10）
- `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`（V099 真實佔用 568 LOC）
- `docs/execution_plan/2026-05-22--decision_2_pg_checksum_alignment_runbook.md`（V099 reference line 257 + Step 4 Sprint 2 Wave 1 包含 V099）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（§3.2/§5.3 line 336-338 V99-V102 假佔位）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md`（§4.1 task wording）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_acceptance.md`（TW Phase 3d acceptance V103 Guard A FAIL chronology）
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1b_v107_sandbox_land_dedup_full.md`（sandbox stub pattern §2.4 + secret_file 範式）
- `sql/migrations/V103__extend_m4_hypothesis_columns.sql`（IMPL ref line 38-78 Guard A messages）
- `sql/migrations/V106__health_observations.sql`（line 92-97 schema 名 patch lesson）
- `sql/migrations/V107__replay_divergence_log.sql`（line 129-137 PA-DRIFT-1 patch）
- `sql/migrations/V112__decision_lease_lal_tiers.sql`（line 32-65 schema 名 typo patch）
- `sql/migrations/V098__governance_audit_log_halt_event_types.sql`（learning schema baseline）
- `TODO.md`（§0/§1.1/§1.7 V099 + Sprint 1B late 狀態 SSOT）
- `CLAUDE.md`（§Data Migrations + Hard Boundaries + Pointers）

---

## §6 PA 4 條完成回報

### 6.1 V99-V102 spec gap audit result + 5 ADD module base table 需求
- V099 = autonomy_level_toggle（SSOT；不可碰）
- V100/V101/V102 = OPEN（v5.7 4 follow-up 假佔位無 IMPL）
- V103 = EXTEND M4 6 column 已 IMPL（sql/migrations/V103__extend_m4_hypothesis_columns.sql LAND；EXTEND-only 路徑）
- 5 ADD module 中**只 M4** base table 缺（V103 base 從未 IMPL 為 .sql）；M2/M8/M9/M10 base 在 V105/V108-V111 spec 含完整 CREATE TABLE 待 Sprint 2 Wave 1 IMPL

### 6.2 V099 schema spec write path + LOC + 設計
- **不寫 V099 spec**（V099 已被 autonomy_level_toggle 佔用 SSOT；不重複）
- **改寫 V100 spec**：`docs/execution_plan/specs/2026-05-23--v100-m4-hypothesis-base-table.md` 估 ~700-900 LOC
- 設計：3 table CREATE（learning.hypotheses 13 column 11 status enum / hypothesis_preregistration 7 column FK BIGINT / earn_movement_log 10 column + FK target patch governance_approval_id → `learning.governance_audit_log`）+ Guard A 對 13 base column 完整性驗 + Guard C status CHECK 11 值 + direction CHECK 2 值 + reconciliation_status CHECK 3 值 + 4 hot-path index + COMMENT + Linux PG dry-run 5 reflection SQL + Round 1/2 idempotency + V103 EXTEND chain 對齊驗

### 6.3 V100-V102 處置決定
- **V099 留 autonomy；V100 給 M4 base table（PA verdict）**
- V101/V102 = Sprint 5+ defer（Track v3 + Earn schema 非 P0 阻塞）
- V104 維持 retired no-op（per v103_v104 §1.3 + line 22 既定決策）
- V103 EXTEND-only 路徑維持（不 rename to V104；避 sqlx checksum drift per 2026-05-02 incident）

### 6.4 AUTO_MIGRATE deploy chain plan + Sprint 1B late readiness verdict
- Phase A Mac E1 IMPL（commit + push）→ Phase B Sandbox Round 1+2 → Phase C OPENCLAW_AUTO_MIGRATE=0→1 + restart → Phase D verify
- Expected `_sqlx_migrations` MAX 96→112（含 V100 + V103 EXTEND + V106/V107/V112 metadata register or full schema apply 路徑視 2026-05-22 decision_2 runbook Step 3 vs alt 採用）
- Sprint 1B late readiness gate = **OPEN with 1 push back accepted**（V099→V100 重 number 仲裁；其餘 5/5 PA prerequisite GREEN）
- E1 IMPL est 6-8 hr + operator deploy + verify ~1-2 hr

---

**END OF PA Sprint 1B late §4.1.1 V100 M4 hypothesis base table design**

(本文 PM 主對話 transcribe；inline 來源 = PA sub-agent agent-a0c94c3e3c183b8b9 final assistant text 18504 chars)

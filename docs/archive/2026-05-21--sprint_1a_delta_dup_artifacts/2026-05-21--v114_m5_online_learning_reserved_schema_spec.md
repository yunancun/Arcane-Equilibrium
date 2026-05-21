---
spec: V114 — M5 Online Learning Reserved Schema (PLACEHOLDER)
date: 2026-05-21
phase: v5.8 Sprint 1A-δ reserve frontmatter only — full DDL deferred Y3+
status: SPEC-PLACEHOLDER-RESERVED-Y3
parent specs:
  - srv/docs/adr/0035-m5-online-learning-interface-reserved.md（治理 ADR；V114 reserve 為 ADR §Decision 2 落地佔位）
  - srv/docs/execution_plan/2026-05-21--m5_online_learning_design_spec.md（M5 interface stub DESIGN spec；V114 schema 與 trait 6 method slot 對齊）
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §9 line 797「V114 reserved frontmatter only, not used Y1」
related V###:
  - V108（M9 A/B framework own schema；Y3+ activation 時 cross-link M5 streaming weight update audit row）
  - V110（M6 Bayesian reward weight history；Y3+ activation 時 cross-link M5 model version id）
  - V107（M11 nightly replay divergence；Y3+ activation 時雙路徑 model_path enum 加 streaming）
  - 既有 `learning.model_versions` 表加 `streaming_enabled BOOL DEFAULT FALSE` column（per ADR-0035 §Decision 2；不在 V114 內，在 Sprint 1A-δ in-flight V### migration）
scope: reserve frontmatter + 14 section outline only — 不寫 V114.sql 實檔，不執行 PG，不在 Mac 跑 SQL，不寫 full DDL（Y3+ activation 後另開 V114 IMPL spec doc 走 PG empirical dry-run）
---

# V114 M5 Online Learning Reserved Schema Spec — PLACEHOLDER

## §0 TL;DR

- **V114 為 M5 online learning 模組 schema 預留**；per ADR-0035 §Decision 2 + v5.8 §9 line 797 + M5 DESIGN spec §7.1，Sprint 1A-δ **不寫 V114 full DDL**，僅交付本 frontmatter + 14 section outline。
- **V114 IMPL 觸發條件** = ADR-0035 §Decision 3 6 條件 AND gate 全 PASS（daily-batch 不足 + AUM > $50k + operator opt-in + M9 GA + Live PnL 3 month > 0 + baseline Sharpe > X）；Y3+ activation 後另開 V114 IMPL spec doc。
- **預留 V114 slot 必要性**：sqlx migration 順序是 git 歷史強制單向；Y3+ 才分配 V### 會撞既有 V### number；提前 reserve V114 是 schema number planning 紀律（per ADR-0035 §Alternatives 第 6 條 + 既有 V### 系統 V110-V113 已連續分配）。
- **本 spec sign-off 後 V114 number 鎖定**；Y3+ activation 時直接走 V114 不再爭奪 number；Retirement R1 觸發時 V114 frontmatter 同 dead-code removal PR 一起移除。

---

## §1 Background + Scope

**Sprint 1A-δ 階段**：本 spec body 全為 placeholder「待 Y3+ activation 後補（per ADR-0035 retirement criteria）」。

**Y3+ activation 後**：本 spec replace 為完整 V114 IMPL spec doc（範式 ref V103 spec `2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`），含：
- 完整 column inventory（learning.online_learning_models / learning.streaming_updates_audit 兩表）
- index 設計（CONCURRENTLY + WHERE partial 適當組合）
- Guard A/B/C 對齊 V094 範式
- engine_mode CHECK constraint 4 值齊全
- Linux PG empirical dry-run protocol（per CLAUDE §七 + feedback_v_migration_pg_dry_run）
- sqlx checksum repair SOP（per memory project_2026_05_02_p0_sqlx_hash_drift）
- 對既有 learning schema 21+ table 的 backward compat 分析

---

## §2 Schema Changes — `learning.online_learning_models`（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時預期 column 草案（per ADR-0035 §Decision 2 line 91 草案；非鎖定）：
- `model_id` BIGSERIAL PK
- `version` TEXT NOT NULL（streaming model version；對 trait `ModelVersion` 結構）
- `streaming_enabled` BOOL NOT NULL DEFAULT FALSE
- `drift_threshold` REAL（KL divergence trigger threshold）
- `last_streaming_update_ts` TIMESTAMPTZ
- `rollback_baseline_version` TEXT（trait `rollback()` 目標 baseline version）
- `engine_mode` TEXT NOT NULL CHECK IN ('paper','demo','live_demo','live')
- 其他 column Y3+ activation 時 DESIGN spec 鎖定

---

## §3 Schema Changes — `learning.streaming_updates_audit`（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時預期：per-streaming-update audit row（trait `get_predict_streaming()` 觸發後寫一 row）；對齊 §二 原則 8「交易可解釋」每筆 streaming update 可重建。

---

## §4 Schema Changes — 既有 `learning.model_versions` 加 `streaming_enabled` column

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

注：per ADR-0035 §Decision 2 + M5 DESIGN spec §6.1 + §7.1，`streaming_enabled` column 在 Sprint 1A-δ 由獨立 in-flight V### migration 加（非 V114）；Y3+ activation 時 V114 才寫 ALTER DEFAULT TRUE 邏輯。

---

## §5 Guard A/B/C Templates（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時範式對齊 V094 / V103：Guard A（NEW table 重建驗 column）+ Guard B（ALTER 既有 column type 驗）+ Guard C（CHECK constraint + index 對齊）。

---

## §6 Linux PG Dry-Run Protocol（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時必走 Linux PG empirical dry-run（per CLAUDE §七 + feedback_v_migration_pg_dry_run + memory project_2026_05_02_p0_sqlx_hash_drift）；Mac mock pytest 不足以驗證 PL/pgSQL Guard DO block 真實 PG semantic。

---

## §7 sqlx Checksum Repair SOP（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時對齊 V094 SOP：V114.sql 落地後跑 `cargo run --release --bin repair_migration_checksum -- --version 114` 同步 DB checksum；engine restart 後驗 sqlx migrate runtime PASS。

---

## §8 IMPL Plan（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時 V114 IMPL workload 預估 40-80 hr（per M5 DESIGN spec §6.3）；含 DDL + healthcheck + writer code + cross-V### binding integration。

---

## §9 Backward Compat（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時必驗：V114 append-only schema migration 不破既有 21+ learning tables / 既有 healthcheck / 既有 ML training pipeline 對 `learning.model_versions` 查詢路徑。

---

## §10 Rollback Path（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時 rollback SQL 對齊 V103 §8：`DROP TABLE IF EXISTS learning.streaming_updates_audit; DROP TABLE IF EXISTS learning.online_learning_models;`；ALTER `streaming_enabled` DEFAULT 回 FALSE。Retirement R1 dead-code removal PR 走 rollback path 完整移除。

---

## §11 風險評估 + 16 原則 / DOC-08 §12 / §四 觸碰（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時對齊 V103 §9 範式：risk 評級 + 16 原則合規 + DOC-08 §12 安全不變量 9 條 + §四 硬邊界觸碰盤點。

---

## §12 Cross-V### Integration（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

Y3+ activation 時對齊 M5 DESIGN spec §7.2：V108（M9 variant 加 `streaming_update_id`）/ V110（M6 reward weight 加 `streaming_model_version_id`）/ V107（M11 replay 加 model_path enum 雙路徑）— 三 V### cross-binding 全 Y3+ activation 時同 V114 一 Sprint land。

---

## §13 Retirement R1 dead-code removal PR scope（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

per ADR-0035 §Decision 4 R1：Y3 末（Sprint 30 / W144）若 activation 6 條件未全 PASS → dead-code removal PR 範圍含：
- 本 V114 frontmatter spec doc 移除
- `learning.model_versions.streaming_enabled` column DROP
- `ModelClient` trait + 6 method stub + sibling panic test 移除
- ADR-0035 Supersede + 新 ADR 列入 ADR-debt closure
- 對 ADR-0036/0037/0038 中 M5 placeholder ref 移除

---

## §14 Sign-off + audit cadence（PLACEHOLDER）

**body 待 Y3+ activation 後補（per ADR-0035 retirement criteria）**。

| Role | Sprint 1A-δ 階段 status | Y3+ activation 階段 status |
|---|---|---|
| Operator | 🟡 PENDING（待 M5 DESIGN spec PM sign-off 連帶）| Y3+ activation 時 LAL 4 operator approval mandatory |
| PA | ✅ Drafted（本 frontmatter + 14 section outline）| Y3+ activation 時另開 V114 IMPL spec doc |
| MIT | 🟡 PENDING（schema 草案 review）| Y3+ activation 時 column inventory 鎖定 review |
| E1 | N/A（Sprint 1A-δ 不寫 V114 SQL）| Y3+ activation 時 V114.sql IMPL + Linux PG dry-run |
| E4 | N/A | Y3+ activation 時 healthcheck + writer regression |
| E2 | N/A | Y3+ activation 時 V114 PR review + grep gate |
| QA | N/A | Y3+ activation 時 Sprint closure + sqlx migrate runtime PASS verify |
| PM | 🟡 PENDING（連帶 M5 DESIGN spec sign-off）| Y3+ activation 時 6 條件 AND gate 仲裁 + retirement audit 仲裁 |

### Retirement audit cadence（per ADR-0035 §Decision 4）

| 時點 | Sprint | Audit 內容 | V114 placeholder 命運 |
|---|---|---|---|
| Y1 Review | Sprint 10 | R1-R4 retirement signal 評估 #1 | 保留 placeholder |
| Y2 Q4 | TBD | retirement signal 評估 #2 | 保留 placeholder |
| Y3 Q2 | TBD | retirement signal 評估 #3 | 若 6 條件 PASS → 啟動 V114 IMPL spec doc |
| Y3 末 | Sprint 30 / W144 | 最終 retirement audit | R1 觸發 → §13 dead-code removal PR |

---

*OpenClaw / Arcane Equilibrium V114 M5 Online Learning Reserved Schema Spec — PLACEHOLDER frontmatter + 14 section outline only（Sprint 1A-δ deliverable per ADR-0035 §Decision 2 + v5.8 §9 line 797；full DDL deferred Y3+ activation；retirement R1 觸發時 dead-code removal）*

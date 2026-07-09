---
spec: V114 — M5 Model Versions Streaming Column EXTEND Schema (Placeholder Reserve)
date: 2026-05-21
author: PA Sprint 1A-δ M5 track（placeholder reserve only；對齊 ADR-0035 Decision 2 + v5.8 §9 line 797 V114 reserved frontmatter only）
phase: v5.8 Sprint 1A-δ schema reserve
status: SPEC-PLACEHOLDER（frontmatter + 大綱 reserve only；full DDL land Y3+ activation 期；scope = placeholder spec only）
parent specs:
  - srv/docs/adr/0035-m5-online-learning-interface-reserved.md（Decision 2 V114 reserved migration placeholder 權威；本 spec 100% 對齊不違背）
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §9 line 797（V114 reserved frontmatter only, not used Y1）+ §2 M5 line 188-217
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-δ (line 159-167)
sibling specs:
  - srv/docs/execution_plan/2026-05-21--m5_model_client_design_spec.md（M5 ModelClient trait stub DESIGN spec；本 V114 placeholder 與 trait stub 共享 Sprint 1A-δ land + 同治理 pattern）
  - srv/docs/execution_plan/2026-05-21--v115_m12_order_router_reserved_schema_spec.md（M12 OrderRouter V115 reserved 同 Sprint 1A-δ；同 pattern）
  - srv/docs/execution_plan/2026-05-21--v116_m13_multi_venue_reserved_schema_spec.md（M13 Multi-Venue V116 reserved 同 Sprint 1A-δ；同 pattern）
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md（V113 placeholder format reference）
scope: V114 placeholder spec — 不寫 V114.sql, 不在 Mac 跑 SQL, 不執行 PG, 不寫 full DDL, full DDL 在 Y3+ activation 期 land（per ADR-0035 Decision 3 6 條件全 PASS 後）；本 Sprint 1A-δ 只 land placeholder frontmatter + 大綱
---

# V114 — M5 Model Versions Streaming Column EXTEND Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V114 EXTEND 既有 `learning.model_versions` table**（不創新 table）：加 `streaming_enabled BOOL NOT NULL DEFAULT FALSE` + `streaming_state JSONB NULL` 兩個 column（per ADR-0035 Decision 2）
- **既有 `learning.model_versions` table** 屬於 LightGBM / Optuna / 3DL daily-batch ML 註冊表（per memory `project_ml_dl_learning_architecture`）— V114 在 Y3+ activation 期 ALTER TABLE ADD COLUMN 增 streaming 路徑支援
- **Sprint 1A-δ scope = placeholder spec only**：不創 V114.sql、不寫 full DDL、不跑 Mac PG / Linux PG SQL；只 land frontmatter + 大綱 + cross-ref ADR-0035 + sibling M5 DESIGN spec
- **Y3+ activation 時點**：per ADR-0035 Decision 3 6 條件全 PASS（daily retrain insufficient + AUM > $50k + operator opt-in + M9 GA + Live PnL 3 month > 0 + baseline Sharpe > X）→ 開新 amendment ADR + 本 V114 spec 升 SPEC-DRAFT-V1 含 full DDL → Linux PG empirical dry-run → V114 land
- **依賴**：既有 `learning.model_versions` table（v5.7 baseline ML 註冊表；版本 schema 待 Y3+ activation 期 reflect）
- **Hypertable 判斷**：**否** — `learning.model_versions` 是 regular table（per-strategy per-day 1 row register；非 high-frequency）；V114 EXTEND ADD COLUMN 不改 hypertable 屬性
- **Linux PG dry-run note**：deferred 至 Y3+ activation 期（Sprint 1A-δ placeholder 不跑 SQL；per `feedback_v_migration_pg_dry_run`）

---

## §1 Background

### 1.1 v5.8 §9 V114 reserved + §2 M5 module 出處

per v5.8 §9 line 797「V114 reserved frontmatter only, not used Y1」+ v5.8 §2 M5 line 205「learning.model_versions table includes streaming_enabled BOOL column (default FALSE)」：

- V114 schema number 提前保留為 placeholder（避免 Y3+ activation 期撞已 land V### sequencing）
- 「learning.model_versions table includes streaming_enabled BOOL column」即本 V114 EXTEND 對應
- v5.8 §2 M5 line 207「No engineering past interface stub」directive → Sprint 1A-δ 不寫 full DDL

### 1.2 ADR-0035 Decision 2 V114 reserved placeholder

per ADR-0035 Decision 2：

| 元素 | 設計 |
|---|---|
| V114 SQL file | **Sprint 1A-δ 不創建** `sql/migrations/V114__online_learning_models.sql`；spec doc placeholder only |
| V114 spec doc | 即本檔（frontmatter + cross-ref ADR-0035 + Y3+ activation trigger condition；不含 DDL） |
| Y3+ activation 時點 | ADR-0035 Decision 4 三條件 (a)(b)(c) 全滿足 + Decision 3 6 條件 AND PASS → 開新 amendment ADR + 本 V114 spec full DDL Sprint land |
| Y3+ activation 觸發後 schema 草案 | EXTEND 既有 `learning.model_versions` 表 ADD COLUMN `streaming_enabled BOOL NOT NULL DEFAULT FALSE` + `streaming_state JSONB NULL`（後者含 streaming model 當前狀態 snapshot）— 草案僅參考，Y3+ activation 時走完整 IMPL DESIGN |
| `streaming_enabled` 預留欄默認值 | **DEFAULT FALSE**（per fail-closed + default-OFF 紀律）；Y3+ activation 時 ALTER TABLE 改 DEFAULT TRUE 即可，無 schema rewrite |

### 1.3 既有 `learning.model_versions` Table（Y1 + Y2 baseline）

per memory `project_ml_dl_learning_architecture`：

| 既有元素 | Y1 + Y2 角色 | V114 EXTEND 影響 |
|---|---|---|
| `learning.model_versions` table | LightGBM / Optuna / 3DL daily-batch baseline 版本 register | V114 ADD COLUMN 不改 baseline 路徑；Y3+ activation 前 `streaming_enabled=FALSE` 全行 |
| daily cron 寫入 | LightGBM / Optuna / 3DL daily 訓練後 INSERT 新版本 row | V114 後 daily cron 寫入時 streaming_enabled 仍 DEFAULT FALSE；不改 daily cron 邏輯 |
| 模型版本 swap | daily boundary swap | V114 後 baseline swap 路徑不變；streaming model 走獨立 lifecycle（Y3+ activation 期 design）|

### 1.4 Audit 來源

- ADR-0035 Decision 2 V114 reserved placeholder（2026-05-21 land）
- v5.8 §9 line 797「V114 reserved frontmatter only」
- v5.8 §2 M5 line 205「streaming_enabled BOOL column (default FALSE)」
- PA dispatch consolidation 行 159-167 Sprint 1A-δ M5 + V114 deliverable

---

## §2 Schema Outline (Placeholder)

### 2.1 EXTEND 對象：`learning.model_versions` (既有 regular table)

**V114 不創新 table** — EXTEND 既有 ML baseline register table。

具體既有 schema 細節（column set / PK / FK / index）待 Y3+ activation 期 Linux PG empirical reflect；Sprint 1A-δ placeholder 不查詢既有 schema（per `feedback_v_migration_pg_dry_run` — Mac mock pytest cannot catch PG runtime semantic）。

### 2.2 V114 ADD COLUMN 大綱（per ADR-0035 Decision 2）

```sql
-- 注：以下為 Y3+ activation 期 full DDL 草案參考 — Sprint 1A-δ 不寫 V114.sql
-- Y3+ activation 期走完整 IMPL DESIGN spec + Linux PG empirical dry-run 後 land

-- ALTER TABLE EXTEND（per ADR-0035 Decision 2）
-- 新增 2 column：streaming_enabled + streaming_state
ALTER TABLE learning.model_versions
    ADD COLUMN IF NOT EXISTS streaming_enabled BOOL NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS streaming_state JSONB NULL;
```

### 2.3 Column 大綱

| Column | Type | NULL? | Default | 用途 | Y3+ activation 時點 |
|---|---|---|---|---|---|
| `streaming_enabled` | BOOL | NOT NULL | FALSE | 標記該 model version 是否啟用 streaming 路徑；Y3+ activation 後 ALTER 改 DEFAULT TRUE | per ADR-0035 Decision 2 + ModelClient trait `streaming_supported()` method 對齊 |
| `streaming_state` | JSONB | NULL | NULL | streaming model 當前狀態 snapshot（如 last_streaming_update_ts / streaming_version / drift_score / rollback_baseline_version 等）；Sprint 1A-δ placeholder 不鎖定具體 JSON schema | per ADR-0035 Decision 2 Y3+ activation 觸發後 schema 草案行 |

### 2.4 設計決策摘要

- **EXTEND 而非新表**：既有 `learning.model_versions` 已是 ML 註冊權威表（LightGBM / Optuna / 3DL daily-batch 共用）；streaming model 仍是「model」一種，自然 EXTEND；避免 JOIN；DEFAULT FALSE 不破既有 caller
- **`streaming_state` 用 JSONB**：Y3+ activation 期 streaming 算法未鎖（incremental gradient descent / online RandomForest 等）→ JSONB 為 schema flexibility 預留；trade-off = JSONB 不支援 CHECK constraint，應用層 Y3+ IMPL 期加 invariant
- **Hypertable**：**否** — `learning.model_versions` 是 regular table（per-strategy per-day 1 row；非 high-frequency）；V114 ADD COLUMN 不改 hypertable 屬性
- **Index**：Y3+ activation 期 full DDL 草案 — partial index `(model_id, version_ts DESC) WHERE streaming_enabled = TRUE` 支援 ModelClient hot path；本 placeholder 階段不寫
- **ENUM / FK / CHECK**：V114 不新增 ENUM / FK / CHECK constraint（BOOL NOT NULL DEFAULT FALSE 即足；JSONB 結構應用層約束）

### 2.5 Cross-V### 依賴

V114 EXTEND target = 既有 `learning.model_versions` table（v5.7 baseline）；依賴既有 ML schema 已 land。其他 Sprint 1A-δ V### (V115 / V116) 各自獨立，無 cross-ref。

---

## §3 Sprint 1A-δ 範圍（Placeholder Only）

| What This Spec IS | What This Spec IS NOT |
|---|---|
| Frontmatter（status / phase / parent / sibling / scope）| 不創 `sql/migrations/V114__online_learning_models.sql` |
| 大綱（column outline / hypertable 判斷 / index 草案 / ENUM-FK-CHECK 判斷） | 不寫 full ALTER TABLE DDL（草案 §2.2 僅參考）|
| Cross-ref ADR-0035 Decision 2 + sibling M5 DESIGN spec | 不跑 Mac PG / Linux PG SQL |
| Y3+ activation 6 條件對齊（per ADR-0035 Decision 3） | 不寫 Guard A/B/C template / AC list / idempotency / rollback SQL |
| Linux PG dry-run note（deferred Y3+） | 不假設 V107 / V108 / V112 等 final type |

---

## §5 Y3+ Activation 觸發條件對齊

per ADR-0035 Decision 3 6 條件 AND gate（本 V114 spec 升級 SPEC-DRAFT-V1 含 full DDL 的觸發條件）：

| 條件 | 內容 | Owner |
|---|---|---|
| (a) | daily-batch retrain 已證實不足（regime shift latency + M11 replay divergence 持續）| MIT + QC |
| (b) | AUM > $50k sustained 30d | PM + operator |
| (c) | operator opt-in（顯式 signed approval）| operator |
| (d) | M9 A/B framework 已 GA（per ADR-0037）| MIT + QC |
| (e) | Live PnL 連續 3 month > 0（per §二 原則 5）| PM + FA |
| (f) | 既有 LightGBM / 3DL daily-batch 連續 30d Sharpe > X（X 由 Y3+ activation 期 PM + MIT 仲裁）| PM + MIT |

**6 條全 PASS** → 開新 amendment ADR amend ADR-0035 Decision 4 retirement criteria（從 retirement 轉 activation）+ 本 V114 spec 升 SPEC-DRAFT-V1 + full DDL + Linux PG empirical dry-run + V114 land

**任一 FAIL** → 維持 placeholder 狀態，繼續 defer；retirement audit cadence Sprint 10 / Y2 Q4 / Y3 Q2 三輪 evaluation

---

## §6 Linux PG Empirical Dry-Run Note（Deferred Y3+）

per `feedback_v_migration_pg_dry_run` 教訓：

- **Sprint 1A-δ 階段不跑 SQL**：不寫 V114.sql、不跑 Mac PG / Linux PG SQL；既有 `learning.model_versions` table 具體 schema reflect 不在本 placeholder spec 階段
- **Y3+ activation IMPL 期必跑**：(1) `learning.model_versions` 既有 schema 反射 SQL；(2) V114 apply 後驗 2 新 column；(3) `streaming_enabled` DEFAULT FALSE 全 row 驗；(4) idempotency 雙跑（IF NOT EXISTS + ADD COLUMN fail-safe）；(5) `restart_all.sh --rebuild` engine restart 實測 + sqlx `_sqlx_migrations V114 success=t` 驗
- **Rollback**：`ALTER TABLE ... DROP COLUMN IF EXISTS streaming_state, streaming_enabled;`（PG DROP COLUMN instant；既有 row 全 DEFAULT FALSE/NULL → 0 真實 data loss）
- **sqlx checksum drift 防護**：per `project_2026_05_02_p0_sqlx_hash_drift`；若 drift → `helper_scripts/db/repair_migration_checksum` binary

---

## §7 Cross-References

- **Parent**：ADR-0035 (`srv/docs/adr/0035-m5-online-learning-interface-reserved.md`) Decision 2 + v5.8 §9 line 797 + §2 M5 line 188-217
- **Sibling**：M5 DESIGN spec (`2026-05-21--m5_model_client_design_spec.md`) + V115 (`2026-05-21--v115_m12_order_router_reserved_schema_spec.md`) + V116 (`2026-05-21--v116_m13_multi_venue_reserved_schema_spec.md`)（同 Sprint 1A-δ deliverable）
- **Mirror precedent**：V113 placeholder spec (`2026-05-21--v113_m7_decay_signals_schema_spec.md`)
- **ADR cross-ref**：ADR-0034 LAL Tier 3 / ADR-0037 M9 GA / ADR-0039 M12 / ADR-0040 M13
- **Skill**：`srv/.claude/skills/db-schema-design-financial-time-series`（Y3+ full DDL 期對齊）
- **Memory**：`project_ml_dl_learning_architecture` / `feedback_v_migration_pg_dry_run` / `project_2026_05_02_p0_sqlx_hash_drift` / `feedback_chinese_only_comments`

---

## §8 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| Operator | APPROVED-pending-spec-land | 2026-05-21 | 主會話 PM dispatch via D1 v5.8 §2 M5 ADD-per-operator LOW priority + D4 interface-stub policy 已批 |
| PA Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve + ADR-0035 Decision 2 對齊 + sibling M5 DESIGN spec cross-ref + Y3+ activation 6 條件對齊 + Linux PG dry-run note deferred |
| MIT | PENDING | — | Y3+ activation 期 full DDL 草案 review（既有 `learning.model_versions` schema reflect 確認 + streaming_state JSONB 結構 design） |
| E1 | PENDING | — | Y3+ activation 期 V114.sql IMPL（per Y3+ activation full DDL spec） |
| E4 | PENDING | — | Y3+ activation 期 V114 land 後 regression（包括 streaming_enabled DEFAULT FALSE 驗 + idempotency 雙跑） |
| E5 | PENDING | — | Y3+ activation 期 EXTEND table hypertable 屬性確認（既有 `learning.model_versions` 不是 hypertable，但 Y3+ activation 期 IMPL 需驗證） |
| PA cross-ref audit | PENDING | — | Sprint 1A-ε cross-ADR consistency audit（本 V114 placeholder 與 ADR-0035 + M5 DESIGN spec 雙向 cross-ref 一致） |
| PM Sign-off | PENDING | — | Sprint 1A-δ closure（含 V114 placeholder land + M5 DESIGN spec land + E1 IMPL trait stub） |

---

**END V114 M5 Model Versions Streaming Column EXTEND Schema Migration Spec PLACEHOLDER（Sprint 1A-δ；對齊 ADR-0035 Decision 2；待 Y3+ activation 期 6 條件全 PASS 後升 SPEC-DRAFT-V1 含 full DDL；待 Linux PG empirical dry-run + V114 land）**

---

Sub-agent dispatch: PA Sprint 1A-δ M5 track
完成時間：2026-05-21

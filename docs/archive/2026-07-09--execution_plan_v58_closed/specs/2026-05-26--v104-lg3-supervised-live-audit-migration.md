# V104 — LG-3 Supervised Live Audit Migration Spec

**Date**: 2026-05-26
**Owner**: PA（spec only；E1 IMPL + MIT dry-run 在 LG-3 Wave 2.4.A 派發）
**Status**: SPEC SCAFFOLD — DISPATCH PENDING v56 P0 Layer B deploy + 24h gate (~2026-05-29)
**Parent spec**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md` §4（含 2026-05-26 AMENDMENT V094→V104 替換規則）
**Dispatch refresh**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md`（§2.4 V099→V104 patch per 2026-05-26 amendment）
**Templates referenced**: `srv/sql/migrations/V086__governance_reject_close_reason_code.sql`（enum + NOT VALID + backfill）/ `V090__governance_unblock_candidates.sql`（governance schema + verdict/outcome 雙層 enum）/ `V107__replay_divergence_log.sql`（TimescaleDB hypertable + forbidden column 反模式 Guard A）

---

## 0. Scope & Non-Scope

### Scope（本 spec 涵蓋）

1. V104 migration 結構性 IMPL spec（SQL 不寫；只列 schema、Guard 模板、policy、index）
2. Linux PG empirical dry-run plan（4 step + 必經驗證 query）
3. 與 spec v2 §4.1 / §4.2 / AC-T4-1~10 V094 字眼 replacement 規則
4. 與 V054 lease_transitions / V035 governance_audit_log prereq dependency
5. sqlx checksum SOP 對齊（per P0 sqlx hash drift incident `project_2026_05_02_p0_sqlx_hash_drift`）
6. Non-training surface invariant E3 grep guard 對齊（per MIT MUST-5）

### Non-Scope（本 spec 不涵蓋）

- ❌ SQL 全文（E1+MIT 領域，本 spec 只列 schema 必含 column 列 + Guard 模板套用 hint）
- ❌ Rust audit writer / Python checks（spec v2 §4.3 / §4.4 各自負責；LG3-T4 IMPL）
- ❌ healthcheck `[59]` / `[60]` / `[61]` IMPL（spec v2 §10 各自負責；LG3-T4）
- ❌ GUI Approval response panel（spec v2 §6.5A；LG3-T7）
- ❌ V104 IMPL 簽屬與後續 E2/E4/QA（PM 派 Wave 2.4 後續事項）

---

## 1. V104 Migration File Identity

| 屬性 | 值 |
|---|---|
| File name | `srv/sql/migrations/V104__supervised_live_audit.sql` |
| Migration number | V104（per spec v2 2026-05-26 amendment A1 + dispatch refresh §2.4 patch） |
| Predecessor 占用 | V099-V103 全占（autonomy_level_config / m4_hypothesis_base_table / track_v3_×2 / m4_hypothesis_extend） |
| Successor 自由 | V105 / V108 / V110 / V111（V104 不阻其他 spec） |
| sqlx checksum 治理 | per MIT MUST-4 SOP — file edit 後若 DB 已 apply 過必 `bin/repair_migration_checksum --target V104` |
| Auto-migrate flag | `OPENCLAW_AUTO_MIGRATE=1`（per restart_all.sh 既定 flow） |

---

## 2. Schema Spec（引用 spec v2 §4.1 表結構）

### 2.1 Table 21 column allowlist（per spec v2 §4.1 Guard A part 2）

| # | Column | Type | Null | 來源 spec v2 |
|---|---|---|---|---|
| 1 | `event_id` | TEXT | NOT NULL | `evt:` + 16-hex random |
| 2 | `ts_ms` | BIGINT | NOT NULL | emit ms epoch |
| 3 | `operator_id` | TEXT | NOT NULL | per RequestEnvelope |
| 4 | `session_id` | TEXT | NULLable | NULL only for REGISTERED/REJECTED |
| 5 | `request_id` | TEXT | NOT NULL | `req:` + UUID v4 |
| 6 | `decision_lease_id` | TEXT | NULLable | NULL until ACTIVE_TRADING |
| 7 | `engine_mode` | TEXT | NOT NULL | CHECK in (live, live_demo) |
| 8 | `symbols` | TEXT[] | NOT NULL DEFAULT [] | — |
| 9 | `strategies` | TEXT[] | NOT NULL DEFAULT [] | — |
| 10 | `risk_limits` | JSONB | NOT NULL DEFAULT '{}' | 4-field shape |
| 11 | `action` | TEXT | NOT NULL | CHECK 17 enum |
| 12 | `src_state` | TEXT | NULLable | NULL for first row |
| 13 | `dst_state` | TEXT | NOT NULL | — |
| 14 | `result` | TEXT | NOT NULL | CHECK in (ok, rejected, forced) |
| 15 | `reason_codes` | TEXT[] | NOT NULL DEFAULT [] | — |
| 16 | `alpha_source_id` | TEXT | NULLable | R-4 forward-compat |
| 17 | `cohort_ref` | TEXT | NULLable | W-AUDIT-9 Stage>=3 |
| 18 | `strategy_alpha_score` | FLOAT8 | NULLable | MIT SHOULD-2 forward-compat |
| 19 | `regime_tag` | TEXT | NULLable | MIT SHOULD-3 forward-compat |
| 20 | `payload` | JSONB | NOT NULL DEFAULT '{}' | previous_session_id / submitted_override / effective_after_min |
| 21 | `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | hypertable partition |

**PK**：`(event_id, created_at)`（hypertable 必含 partition column；per V107 樣板硬邊界）

### 2.2 CHECK constraints（per spec v2 §4.1 ADD CONSTRAINT block）

1. `chk_supervised_live_audit_action`：17 enum（per spec v2 §4.1 + §2.2A inverse map 對應）
   - request_registered / approval_granted / approval_rejected / expired_pre_auth
   - auth_file_observed / auth_file_invalid / lease_acquired / lease_released
   - auth_recheck_fail / drawdown_breach / drawdown_close_complete
   - kill_api / kill_ipc / session_max_duration / reconcile_force_close
   - illegal_transition_attempted / session_closed
2. `chk_supervised_live_audit_result`：result IN (ok, rejected, forced)
3. `chk_supervised_live_audit_engine_mode`：engine_mode IN (live, live_demo)
4. `chk_supervised_live_audit_ts_ms_positive`：ts_ms > 0

**ADD CONSTRAINT 套用模板**：V086 §245-317 ADD CONSTRAINT IF NOT EXISTS 模式（idempotent re-runs 0 RAISE）

### 2.3 TimescaleDB hypertable policy

| 參數 | 值 | 對應樣板 |
|---|---|---|
| Partition column | `created_at` | V107 line 17 |
| Chunk interval | INTERVAL '7 days' | spec v2 §4.1 line 667（lower volume justifies） |
| Compression policy | 30 days | V107 line 19 |
| Compression segmentby | `session_id` | LG-3 hot read pattern |
| Compression orderby | `created_at DESC` | TimescaleDB best practice |
| Retention policy | 90 days | V107 line 20（learning.* governance retention 對齊） |

### 2.4 Index plan（per spec v2 §4.1 Guard C）

| Index | Columns | Purpose |
|---|---|---|
| `idx_supervised_live_audit_session_id` | (session_id, created_at DESC) | 5 SoT reconcile 對賬 |
| `idx_supervised_live_audit_request_id` | (request_id, created_at DESC) | per-request audit lookup |
| `idx_supervised_live_audit_action` | (action, created_at DESC) | healthcheck [59] + [60] 30d window scan |
| `idx_supervised_live_audit_operator` | (operator_id, created_at DESC) | per-operator 30d 1% violation budget gate |

---

## 3. Guard Layer Spec

### 3.1 Guard A：Prereq + 既有 schema 完整性（per CLAUDE.md §七 + spec v2 §4.1）

**A part 1**（per V086 / V107 樣板模式）：
- 驗 `learning.lease_transitions`（V054）+ `learning.governance_audit_log`（V035）兩 prereq 已 land
- 缺其一 → `RAISE EXCEPTION 'V104 Guard A part 1: V054 or V035 prerequisite missing'`

**A part 2**（per MIT MUST-1，21-column allowlist check）：
- 若 `learning.supervised_live_audit` 已存在 → 驗 21 column 全在
- 缺 column → `RAISE EXCEPTION 'V104 Guard A part 2: supervised_live_audit missing columns: %'`
- 套用 V086 line 250-280 missing column 累積 RAISE pattern

**A part 3**（per MIT MUST-5 + V107 line 165-200 forbidden column 反模式）：
- 反向驗 `supervised_live_audit` **無** 以下 forbidden column：
  - `ml_label` / `training_label`（非 ML training surface）
  - `feature_vector`（非 feature store）
  - `signal_id`（非 signal lifecycle）
- 防 ML/training pipeline 誤接 supervised_live_audit
- 違反 → `RAISE EXCEPTION 'V104 Guard A part 3: supervised_live_audit violates non-training surface invariant'`

### 3.2 Guard B（per CLAUDE.md §七）

**N/A** — V104 為新 CREATE TABLE，無既有 column type 改動。

如未來 amendment 加 ALTER COLUMN TYPE → 必加 Guard B（per CLAUDE.md type-sensitive ADD COLUMN）。

### 3.3 Guard C（per CLAUDE.md §七 + V107 line 215-280）

**Enum 完整性 check**：
- 驗 `chk_supervised_live_audit_action` 17 enum 全在 pg_constraint
- 驗 `chk_supervised_live_audit_result` 3 enum 全在
- 驗 `chk_supervised_live_audit_engine_mode` 2 enum 全在

**Hypertable 完整性**：
- 驗 `_timescaledb_catalog.hypertable` 含 `learning.supervised_live_audit` row
- 驗 chunk_time_interval = 7 days
- 驗 compression policy + retention policy 都存在

**Index 完整性**：
- 驗 4 索引全 land

---

## 4. Linux PG Empirical Dry-Run Plan（per MIT MUST-3 + `feedback_v_migration_pg_dry_run`）

### 4.1 SOP 4 step

**Step 1：Linux runtime PG snapshot 對齊**
```bash
# On trade-core via ssh
psql $OPENCLAW_PG_URL -c "SELECT MAX(version) FROM _sqlx_migrations;"
# 預期 >= 112（per 2026-05-27 empirical）；確認 V104 為 forward-only target
```

**Step 2：Mac → Linux file sync + dry-run apply**
```bash
# Mac SSOT 寫 V104__supervised_live_audit.sql 後
scp srv/sql/migrations/V104__supervised_live_audit.sql trade-core:/tmp/V104_dryrun.sql
ssh trade-core "psql $OPENCLAW_PG_URL_DRYRUN -f /tmp/V104_dryrun.sql"
# 必跑在 dryrun DB（非 production；per `docs/agents/context-loading.md` PG Connection Examples）
```

**Step 3：Idempotency 驗證（apply twice）**
```bash
ssh trade-core "psql $OPENCLAW_PG_URL_DRYRUN -f /tmp/V104_dryrun.sql"
# Expected: 0 RAISE / 0 ERROR / 0 NOTICE 「already exists」之外的訊息
```

**Step 4：Schema reflection 驗證**
```sql
-- 4a. 21 column 全 land
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'learning' AND table_name = 'supervised_live_audit'
ORDER BY ordinal_position;
-- Expected: 21 row

-- 4b. 4 CHECK constraint 全 land
SELECT conname FROM pg_constraint
WHERE conrelid = 'learning.supervised_live_audit'::regclass
  AND contype = 'c';
-- Expected: chk_supervised_live_audit_action / _result / _engine_mode / _ts_ms_positive

-- 4c. hypertable 已建
SELECT hypertable_name, num_chunks, num_dimensions
FROM _timescaledb_information.hypertables
WHERE hypertable_schema = 'learning' AND hypertable_name = 'supervised_live_audit';
-- Expected: 1 row, num_dimensions = 1

-- 4d. compression + retention policy 已掛
SELECT * FROM _timescaledb_information.jobs
WHERE hypertable_schema = 'learning' AND hypertable_name = 'supervised_live_audit';
-- Expected: 2 row（compression + retention）

-- 4e. 4 索引全 land
SELECT indexname FROM pg_indexes
WHERE schemaname = 'learning' AND tablename = 'supervised_live_audit'
ORDER BY indexname;
-- Expected: 4 row（plus PK index automatic）

-- 4f. Action enum 17 個全在 CHECK 內
SELECT pg_get_constraintdef(oid) FROM pg_constraint
WHERE conname = 'chk_supervised_live_audit_action';
-- Expected: 17 enum string 全在
```

### 4.2 Dry-run sign-off gate

MIT 完成 4 step → 出 `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/<DATE>--v104_lg3_supervised_live_audit_pg_dryrun.md` 回填以下表：

| Step | Pass/Fail | Evidence path or query output snippet |
|---|---|---|
| 1. Snapshot | ☐ | `_sqlx_migrations` max version |
| 2. Apply | ☐ | psql stdout 「CREATE TABLE / CREATE INDEX」記錄 |
| 3. Idempotency | ☐ | 第二次 apply 「already exists」NOTICE 全列 |
| 4a. 21 column | ☐ | 21 row 完整 |
| 4b. 4 CHECK | ☐ | 4 conname 完整 |
| 4c. Hypertable | ☐ | num_dimensions=1 |
| 4d. Policy | ☐ | compression + retention 各 1 row |
| 4e. 4 index | ☐ | 4 indexname |
| 4f. 17 enum | ☐ | 17 enum 全在 |

**Sign-off rule**：9/9 PASS 才 sign IMPL ready；任一 FAIL → 回 PA 出 amendment（spec scaffold patch）。

---

## 5. sqlx Checksum 治理（per `project_2026_05_02_p0_sqlx_hash_drift` 教訓）

### 5.1 V104 file edit 後 SOP

若 V104 file 在 dry-run DB apply 過後又 edit（例：MIT dry-run fail → PA amend → file 改）：

```bash
# Mac SSOT
ssh trade-core "/path/to/openclaw_engine/bin/repair_migration_checksum --target V104"
```

或 fallback：

```bash
ssh trade-core "unset OPENCLAw_AUTO_MIGRATE; bash helper_scripts/bootstrap_db.sh"
```

對齊 V083 / V084 / V028-V034 既有教訓（per `project_2026_05_02_p0_sqlx_hash_drift`）。

### 5.2 Production deploy 後 checksum 監控

V104 land production → 自動加進 `_sqlx_migrations` row。後續 file 修改禁（per CLAUDE.md `Migration idempotency` 規範 forward-only）；改動必走 V105+ forward migration。

---

## 6. Non-Training Surface Invariant（per MIT MUST-5）

### 6.1 E3 grep guard 規則

LG3-T4 配套 IMPL：`scripts/e3_grep_non_training_surface.sh`（spec v2 §4.4B 列）

```bash
# 反模式：禁 ML/training pipeline 讀 supervised_live_audit
PATTERNS='SELECT.*FROM learning\.supervised_live_audit'
EXCEPT_PATHS='program_code/healthcheck|program_code/reconciler|tests/'

grep -rE "$PATTERNS" program_code/ \
  | grep -v "$EXCEPT_PATHS" \
  | grep -E 'ml/|training/|learning/'
# Expected: 0 hit；非 0 → CI fail
```

### 6.2 spec v2 §4.4B cross-ref

對齊 spec v2 §4.4B Non-training surface invariant 規範。

---

## 7. 與 spec v2 V094 字眼 replacement 規則

### 7.1 Spec v2 章節 V094 字眼分布

| Spec v2 章節 | V094 字眼出現位置 | IMPL 時動作 |
|---|---|---|
| §4.1 SQL header | `V094__supervised_live_audit.sql` / 「V094 file edit 後...」 | 替換 V104 |
| §4.1 Guard A | `'V094 Guard A part 1: V054 or V035 prerequisite missing'` | 替換 V104 |
| §4.1 Guard A | `'V094 Guard A part 2: supervised_live_audit missing columns: %'` | 替換 V104 |
| §4.2 RFC 11 欄 + 補欄位 | （無 V094 字眼，只列 column 設計） | 0 動作 |
| §8 AC-T4-1~10 | LG3-T4 acceptance criteria | 文字內 V094 → V104 |
| §13.4.1 Linux PG dry-run SOP | 「V094 dry-run」 | V104 |

### 7.2 E1 dispatch packet 必含

PM 派 LG3-T4 E1 prompt 必含：

```
V094 → V104 replacement rule:
- 所有 V094 字眼 1:1 替換為 V104
- IMPL 完成前必跑 `grep -n 'V094\|V099' <touched_files>` 確認 0 match
- 若 grep 結果 non-zero → 回 PA 報告（不算 IMPL DONE）
```

---

## 8. Dependency & Ordering

### 8.1 Migration ordering

```
V054 (lease_transitions) [LAND]
  → V035 (governance_audit_log) [LAND]
    → V104 (supervised_live_audit) [本 spec target]
      → LG3-T4 Rust audit writer IMPL（spec v2 §4.3）
        → LG3-T4 Python checks IMPL（spec v2 §4.4）
```

### 8.2 Wave 2.4 dispatch dependency

per `2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md` §3.3 Option B：

```
Wave 2.4.A: T1（Rust SM core）+ T4（V104 audit writer）並行雙派
  ↳ T4 含 V104 migration apply + Rust audit_writer.rs + Python checks_supervised_live_audit.py
Wave 2.4.B: T2（Python SM mirror，依 T1）
Wave 2.4.C: T3（Approval RPC，依 T2）
Wave 2.4.D: T5（Kill + override + lease，依 T1+T2+T3）
Wave 2.4.E: T7（GUI surface，依 T5 對 live_session_routes.py 提交完）
Wave 2.4.F: T6（E2E acceptance，依 T1..T5+T7 全 land）
```

V104 在 Wave 2.4.A 與 T1 並行 — 文件零 overlap（T1 = `supervised_live_sm/` Rust new module；T4 = `V104__supervised_live_audit.sql` 新 SQL + `supervised_live_audit_writer.rs` 新 .rs + `checks_supervised_live_audit.py` 新 .py + `e3_grep_non_training_surface.sh` 新 shell；零 surface 衝突）。

---

## 9. Risk Assessment

| 部分 | 風險評級 | 緩解 |
|---|---|---|
| V104 schema 結構 | **中** | spec v2 §4.1 已 3-review APPROVE；本 spec 只 V### renumber + scaffold |
| V104 hypertable + policy | **中** | V107 樣板 100% 對齊；Guard A part 3 forbidden column 反模式防 ML 接管 |
| Idempotency | **中** | Guard A IF NOT EXISTS + ADD CONSTRAINT IF NOT EXISTS + index IF NOT EXISTS 模式；apply twice 必 pass |
| sqlx checksum drift | **中** | repair_migration_checksum SOP 對齊 P0 hash drift 教訓 |
| V104 與 V105/V108/V110/V111 hole 衝突 | **低** | V104 free，V105/V108/V110/V111 全 free，無 sqlx 連續性問題 |
| MIT dry-run 工時 | **中** | ~2-4h（estimate），在 v56 Layer B 24h gate 內可完 |

整體：**中**（非 hot path schema；TimescaleDB hypertable 既有樣板 100% 對齊；3-review APPROVE baseline 不變）。

---

## 10. PA Sign-Off

**Spec scaffold ready for**：
- ⏳ v56 P0 Layer B deploy + 24h gate（~2026-05-29）
- ⏳ PM 派 LG-3 Wave 2.4.A E1 + MIT 並行（T1 + T4 雙派）
- ⏳ MIT 先走本 spec §4 4-step dry-run → 出 sign-off report
- ⏳ MIT dry-run 9/9 PASS → E1 IMPL T4 SQL + Rust writer + Python checks

**Spec scaffold NOT 涵蓋**：
- ❌ SQL 全文（E1+MIT 在 dry-run 出 PASS 後 IMPL）
- ❌ Rust audit writer / Python checks IMPL（LG3-T4 sub-task）
- ❌ healthcheck [59]/[60]/[61] IMPL（LG3-T4 sub-task）

---

PA V104 SPEC SCAFFOLD DONE: report path: `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md`

Next:
- ⏳ PA memory.md 追加（V104 spec scaffold + V### renumber + dispatch trigger correction）
- ⏳ Operator / PM apply TODO §1 行 48 reframe text（PA report 內提供）
- ⏳ v56 P0 Layer B 7d observation 開始日 ~2026-05-29 → PM 派 Wave 2.4.A

# REF-20 Sprint 1 Track D — V049/V050/V051/V052 Schema Drift Remediation

**日期：** 2026-05-03
**Owner：** E1 (Sprint 1 Track D)
**派發：** PM 對 PA `2026-05-03--ref20_sprint1_partition_design.md` Track D
**結果：** 4 個 V### 全 IMPL，pytest 24/24 PASS，Mac dev psql 4 V### × 2 idempotent + 5 sanity 全綠

---

## 1. 任務摘要

PA Sprint 1 partition Track D。把 V3 §4.1 `replay.experiments` 22 col + `replay.simulated_fills` 17 col + V3 §4.2 paired CHECK 與 V045/V046 FK redirect — W1 dispatch 偷換成「P2b runner SQL fixture」逃避 Guard A/B/C 的 schema drift 修復。4 個 V### + 1 healthcheck + REF-20_RESERVATION.md v1.7→v1.8 + route_helpers `_table_present` factory。

**根因（PA W1 自審）：** Reservation v1.x 把 V3 §4.1 規範表預留為 fixture，IMPL 跟著繞 migration governance；V045 FK 指向不存在的 `replay.experiments`；V3 §12 #6 `replay_source_guard` 無法 PASS。

**解：** Track D 4 個 V### 把 22+17 col + paired CHECK + V045/V046 FK redirect 拉回真正 migration（forward-only ALTER 避觸 2026-05-02 P0 sqlx hash drift incident）。

---

## 2. 修改清單

### 新檔（5 個 SQL + 1 個 pytest）
| 路徑 | 行數 | 用途 |
|---|---:|---|
| `srv/sql/migrations/V049__replay_experiments.sql` | 699 | V041 4 col stub → V3 §4.1 22 col promotion |
| `srv/sql/migrations/V050__replay_simulated_fills.sql` | 385 | V3 §4.1 17 col simulated-fill registry |
| `srv/sql/migrations/V051__mlde_recommendations_replay_columns.sql` | 377 | V3 §4.2 paired CHECK + 2 col + FK V049 |
| `srv/sql/migrations/V052__replay_run_state_artifacts_fk_redirect.sql` | 374 | V045/V046 forward-only FK redirect to V049 |
| `srv/sql/migrations/V052_preflight.sql` | 127 | 5 read-only probe healthcheck (V040_healthcheck 風格) |
| `srv/tests/migrations/test_v049_v050_v051_v052_track_d.py` | 507 | 24 pytest fixture (Mac dev static-parse + cross-file invariants) |

### 修改檔（2 個）
| 路徑 | 變更 |
|---|---|
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py` | 既有 `v045_table_present` 重構為 thin wrapper；新加 `table_present(cur, schema, table)` factory + `v049_table_present` / `v050_table_present` / `v051_columns_present`；`__all__` 4 個新增 export |
| `srv/sql/migrations/REF-20_RESERVATION.md` | §2 預留範圍 V036-V050→V036-V055；§3 reservation map 新增 V049/V050/V051/V052 4 row（status: reserved buffer/new → land）；§5 audit grep 範圍擴；§6 修訂歷史 v1.8 row（與 Track C 同 session 並列） |

---

## 3. 關鍵 diff

### V049 — V041 stub → V3 §4.1 22 col promotion 要點

```sql
-- ALTER experiment_id TEXT → UUID 對齊 V045/V046 既建 UUID type
ALTER TABLE replay.experiments
    ALTER COLUMN experiment_id TYPE UUID
    USING experiment_id::uuid;

-- 18 個新 V3 §4.1 column（V041 stub 已有 4 個）
ALTER TABLE replay.experiments
    ADD COLUMN IF NOT EXISTS parent_experiment_id          UUID,
    ADD COLUMN IF NOT EXISTS runtime_environment           TEXT,
    ADD COLUMN IF NOT EXISTS engine_binary_sha             TEXT,
    -- ... (15 more)

-- intra-row 3-pair window non-overlap (Postgres 不支 intra-row EXCLUDE，用 CHECK + tstzrange &&)
ALTER TABLE replay.experiments
    ADD CONSTRAINT chk_replay_experiments_window_no_overlap
    CHECK (
        ... NOT tstzrange(calibration_train_window_start, calibration_train_window_end)
            && tstzrange(oos_label_window_start, oos_label_window_end) ...
    );

-- inter-row EXCLUDE GIST defense-in-depth（btree_gist extension 缺時 graceful WARN）
ALTER TABLE replay.experiments
    ADD CONSTRAINT excl_replay_experiments_candidate_window_per_id
    EXCLUDE USING gist (
        experiment_id WITH =,
        tstzrange(candidate_window_start, candidate_window_end) WITH &&
    ) WHERE (candidate_window_start IS NOT NULL AND candidate_window_end IS NOT NULL);
```

### V051 — V3 §4.2 paired CHECK 完整搬

```sql
ALTER TABLE learning.mlde_shadow_recommendations
    ADD COLUMN IF NOT EXISTS replay_experiment_id UUID,
    ADD COLUMN IF NOT EXISTS manifest_hash        BYTEA;

-- V3 §4.2 lines 220-234 paired CHECK 完整移植
ALTER TABLE learning.mlde_shadow_recommendations
    ADD CONSTRAINT chk_mlde_shadow_replay_lineage
    CHECK (
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
    );

-- FK ON DELETE NO ACTION（非 SET NULL — paired CHECK 衝突；非 CASCADE — advisory row 是 evidence）
ALTER TABLE learning.mlde_shadow_recommendations
    ADD CONSTRAINT fk_mlde_shadow_replay_experiment
    FOREIGN KEY (replay_experiment_id)
    REFERENCES replay.experiments(experiment_id)
    ON DELETE NO ACTION;
```

### V052 — preflight + V045/V046 forward-only FK redirect

```sql
-- preflight (PA Push Back #1)
SELECT COUNT(*) INTO v_v045_dangling
FROM replay.run_state r
LEFT JOIN replay.experiments e ON r.manifest_id = e.experiment_id
WHERE e.experiment_id IS NULL;

IF v_v045_dangling > 0 THEN
    RAISE EXCEPTION
        'V052 preflight: replay.run_state has % rows whose manifest_id has no matching '
        'replay.experiments(experiment_id). Operator decision required: ...';
END IF;

-- 不改 V045/V046 file（forward-only ALTER；避觸 2026-05-02 P0 sqlx hash drift incident）
ALTER TABLE replay.run_state
    ADD CONSTRAINT fk_replay_run_state_manifest_id
    FOREIGN KEY (manifest_id) REFERENCES replay.experiments(experiment_id)
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- V046 ADD COLUMN + JOIN backfill + FK
ALTER TABLE replay.report_artifacts ADD COLUMN IF NOT EXISTS experiment_id UUID;
UPDATE replay.report_artifacts a
SET experiment_id = r.manifest_id
FROM replay.run_state r
WHERE a.run_id = r.run_id AND a.experiment_id IS NULL;

ALTER TABLE replay.report_artifacts
    ADD CONSTRAINT fk_replay_report_artifacts_experiment_id
    FOREIGN KEY (experiment_id) REFERENCES replay.experiments(experiment_id)
    ON DELETE CASCADE;
```

### route_helpers — `_table_present` factory

```python
def table_present(cur: Any, schema: str, table: str) -> bool:
    """Generic schema-presence factory used by REF-20 V### gating paths."""
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
            (schema, table),
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def v045_table_present(cur: Any) -> bool:
    """Check whether replay.run_state (V045) is deployed."""
    return table_present(cur, "replay", "run_state")  # legacy thin wrapper

def v049_table_present(cur: Any) -> bool: ...  # new
def v050_table_present(cur: Any) -> bool: ...  # new
def v051_columns_present(cur: Any) -> bool: ...  # new (probes 2 column names)
```

---

## 4. 治理對照（CLAUDE.md §七 強制檢查）

| 項目 | 結果 |
|---|---|
| 雙語 SQL comment（Purpose / 目的 / V3 spec section）| ✅ 4 V### + healthcheck 全雙語 MODULE_NOTE + Spec source citation |
| `grep -E '/home/ncyu\|/Users/[^/]+'` 修改 diff | ✅ 0 hit（pytest `test_no_user_home_path_hardcoded` PASS）|
| 4 V### idempotent（local psql -f × 2 第二次 0 RAISE）| ✅ Mac PG 16.13 真實 smoke test 4 V### 全跑兩遍 0 RAISE EXCEPTION |
| 4 V### Guard A/B/C 完備 | ✅ V049 A+B+C / V050 A+C / V051 A+B / V052 A+B + preflight |
| V049 EXCLUDE GIST 對應 V3 spec | ✅ btree_gist extension + `excl_replay_experiments_candidate_window_per_id`（feature_not_supported 時 graceful WARN）|
| V050 FK to V049 + cascade 規則 | ✅ ON DELETE CASCADE（fills 屬 experiment 生命週期）|
| V051 雙路 CHECK 落地 | ✅ `chk_mlde_shadow_replay_lineage` 完整搬 V3 §4.2 lines 220-234 SQL |
| V052 preflight LEFT JOIN dangling check + abort | ✅ 兩路（V045 + V046）統計 + RAISE EXCEPTION 一條訊息含 diagnostic SQL |
| 0 SQL `INSERT INTO trading.*` / 0 `live_*` mutate | ✅ pytest `test_no_trading_or_live_mutation_in_v_files` PASS |
| 0 觸 max_retries / live_execution_allowed / execution_authority / system_mode | ✅ pytest `test_no_hard_boundary_columns_touched` PASS |
| 不改 V045/V046 file（P0 sqlx hash drift 教訓）| ✅ pytest `test_v052_does_not_edit_v045_v046_files` PASS（直接讀 V045/V046 source 驗證）|

### 真實 Mac PG smoke test 結果（throwaway DB `track_d_smoke_test`）

| 測試 | 結果 |
|---|---|
| V049 first run | NOTICE × N + DO + COMMENT，0 ERROR |
| V049 second run（idempotency）| 全 NOTICE「already present; skipping」+ skipping，0 ERROR |
| V050 first run | NOTICE 5 × CHECK + 3 × index created，0 ERROR |
| V050 second run | 全「already present; skipping」 |
| V051 first run | NOTICE Guard A V040+V049 verified + FK NO ACTION + paired CHECK，post-apply verified |
| V051 second run | 全 skipping，post-apply 仍 verified |
| V052 first run | preflight 0 dangling rows + V045/V046 FK 加 + 0 orphan + post-apply verified |
| V052 second run | 全 skipping，post-apply verified |
| V052_preflight.sql | 5 probe 全綠：dangling=0+0 / FK present=t+t / PK type=uuid |
| Sanity: V051 paired CHECK 擋假 row | ✅ `INSERT calibrated_replay+兩欄 NULL` → ERROR `chk_mlde_shadow_replay_lineage` |
| Sanity: V051 ON DELETE NO ACTION 擋 parent DELETE | ✅ `DELETE replay.experiments` referenced row → ERROR FK violation |
| Sanity: V050 FK CASCADE | ✅ DELETE experiment → fills 連帶清（雖被 V051 NO ACTION 阻斷的測試組合，但 CASCADE 路徑 mock 中已驗）|
| Sanity: V049 chk_window_no_overlap | ✅ INSERT overlapping calibration+oos_label window → ERROR |
| pytest `test_v049_v050_v051_v052_track_d.py` | **24/24 PASS** |

---

## 5. 不確定之處

1. **EXCLUDE GIST 在 V045 沒 candidate_window NOT NULL row 時無法防 inter-row 重複**：實際 use case 中 V045 row 可能寫 candidate_window NULL（research 階段）；此時 EXCLUDE 不生效，CHECK chk_window_no_overlap 仍守 intra-row。已 doc。
2. **V051 ON DELETE NO ACTION 對 operator 體驗**：當 operator 在 GUI 嘗試刪 experiment 時會見到 FK 錯誤訊息「still referenced from table mlde_shadow_recommendations」；UX 層需在 Track A/C 處理（GUI 顯示「先 archive advisory rows 才能刪 manifest」）。
3. **V050 deferred FK behavior**：V050 FK to V049 用 NOT DEFERRABLE（預設）；P3+ replay_runner batch INSERT 時若同 transaction 先 INSERT V050 row 再 INSERT V049 row 會 fail。產品端 caller 應先 INSERT V049 manifest 再 INSERT V050 fills。
4. **V049 self-FK ON DELETE SET NULL**：parent_experiment_id 自引 FK 用 SET NULL；如 parent baseline 被刪，child candidate 的 lineage 設 NULL。這正常，因 baseline 與 candidate 是 sibling lineage 而非 strict containment。
5. **跨 commit 對 V045 既有 row 的補建決策**：PA push back #1 提兩 option（INSERT minimal V049 stub for dangling V045 row / DELETE archive V045 dangling row），Mac smoke test 0 row 不撞觸發；Linux operator 部署前必先跑 V052_preflight.sql 真實驗 0 dangling，否則必選 a 或 b。

---

## 6. 跨 Track 影響評估

| Track | 影響 |
|---|---|
| Track A（spawn argv schema）| Track A E1 寫 manifest fixture 後 INSERT V045 仍走 manifest_id UUID；V052 FK ADD 後同 transaction 會檢驗 manifest_id ∈ V049 — Track A 必先 INSERT V049 row 才 INSERT V045 row，否則 FK 失敗。**待 Track A E1 確認 spawn 時序**。 |
| Track B（Rust manifest signature）| 純 Rust 改，與 V049/V050 解耦。V049 manifest_hash + manifest_signature 兩 BYTEA column 為 Rust 端 verify 路徑提供 spec-conform schema。 |
| Track C（Python /replay/* 安全洞）| Track C E1 加 5 新 governance_audit_log event_type（V053 reserved buffer，由 PM 派 Track C IMPL 出）；V051 paired CHECK 透過 fk_mlde_shadow_replay_experiment 與 V049 lineage 綁定，Track C 不直接觸碰。 |
| 跨 Track 共同 helper | `table_present(cur, schema, table)` factory 已 land 於 route_helpers.py；4 個 v045/v049/v050/v051 wrapper 都用 factory；Track A/C 後續 IMPL 直接 import 即可。 |

---

## 7. Operator 下一步

### 7.1 Linux trade-core 部署前 healthcheck（必跑）

```bash
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai \
  -f /opt/openclaw/srv/sql/migrations/V052_preflight.sql"
```

預期結果（pre-V052 deploy）：
- v045_dangling.row_count = 0（V045 row 對應 V049 manifest 都存在）
- v046_dangling.row_count = 0
- v045_fk_present.has_fk = false
- v046_fk_present.has_fk = false
- v049_pk_type.pk_type = uuid

如果 v045_dangling > 0 → operator 必選擇：
- **(a) reconcile**：每筆 dangling V045 row 寫一筆 minimal V049 stub（filled fields: experiment_id=manifest_id, runtime_environment, created_at）
- **(b) archive**：DELETE/搬 V045 dangling row 到 archive 表

### 7.2 Linux 部署順序（V049→V050→V051→V052）

```bash
ssh trade-core "cd /opt/openclaw/srv && \
  psql -h 127.0.0.1 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 \
    -f sql/migrations/V049__replay_experiments.sql && \
  psql -h 127.0.0.1 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 \
    -f sql/migrations/V050__replay_simulated_fills.sql && \
  psql -h 127.0.0.1 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 \
    -f sql/migrations/V051__mlde_recommendations_replay_columns.sql && \
  psql -h 127.0.0.1 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 \
    -f sql/migrations/V052__replay_run_state_artifacts_fk_redirect.sql"
```

### 7.3 部署後驗證（必跑）

```bash
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai \
  -f /opt/openclaw/srv/sql/migrations/V052_preflight.sql"
```

預期結果（post-V052 deploy）：
- v045_dangling.row_count = 0
- v046_dangling.row_count = 0
- v045_fk_present.has_fk = **true**
- v046_fk_present.has_fk = **true**
- v049_pk_type.pk_type = uuid

### 7.4 sqlx_migrations checksum 寫入（防 P0 sqlx hash drift incident 重觸）

部署 4 V### 後 engine restart 前，operator 應確認 `_sqlx_migrations` row 寫入：

```bash
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai \
  -c \"SELECT version, description, success FROM _sqlx_migrations WHERE version >= 49 ORDER BY version;\""
```

如果 V049-V052 之 sqlx 自動寫入失敗，跑 `bin/repair_migration_checksum`（per memory `project_2026_05_02_p0_sqlx_hash_drift.md`）。

### 7.5 不需 commit；等 PM 批准後 4 並行 Track 全完一起 commit

PA partition 設計 = Track D 起頭做 → Track A/B/C 全並行 → 一起 E2/E4 → 一起 commit。**E1 不自行 commit**（CLAUDE.md §七 強制鏈 E1→E2→E4→QA→PM）。

---

## 8. 文件指針

- PA partition design：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md` §2 Track D + §5 Push Back #1
- V3 spec：`srv/docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §4.1 + §4.2
- Reservation：`srv/sql/migrations/REF-20_RESERVATION.md` v1.8 row V049/V050/V051/V052
- 4 V### + healthcheck：`srv/sql/migrations/V049__replay_experiments.sql` / V050 / V051 / V052 / V052_preflight.sql
- Pytest：`srv/tests/migrations/test_v049_v050_v051_v052_track_d.py`
- route_helpers patch：`srv/program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py`
- 教訓參考：memory `project_2026_05_02_p0_sqlx_hash_drift.md`（V052 forward-only 設計依據）

---

E1 IMPLEMENTATION DONE：待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_d_schema_migrations.md`）

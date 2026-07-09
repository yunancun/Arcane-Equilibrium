# REF-20 R20-P2a-S6 — `evidence_source_tier` 3-step retrofit migration land
# REF-20 R20-P2a-S6 — `evidence_source_tier` 三步回補 migration land

**日期 / Date：** 2026-05-03
**Owner：** E1 (sub-agent, Wave 3 P2a-S6 task)
**契約上游 / Upstream contract：**
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G3 + §4.2
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 3 R20-P2a-S6 + §7.1 風險 #3
- `sql/migrations/REF-20_RESERVATION.md` §3 V038/V039/V040
- `sql/migrations/templates/schema_guard_template.sql` Guard A/B/C 模板

**Mode：** WRITE (4 SQL files + 1 pytest + 1 ledger update)；0 真實 DB apply（Mac dev；Linux operator deploy 由 PM 排程）.
**Mode (EN):** WRITE only (4 SQL files + pytest fixture + ledger row); zero real-DB apply (Mac dev; Linux operator deploys per PM schedule).

---

## 0. TL;DR

**5 SQL/test artifacts + 1 ledger update + bilingual + 17/17 pytest PASS：**

| Artifact | Path | Purpose |
|---|---|---|
| V038 | `sql/migrations/V038__add_evidence_source_tier.sql` | ADD COLUMN evidence_source_tier TEXT NULLABLE (no production write impact) |
| V039 | `sql/migrations/V039__backfill_evidence_source_tier.sql` | UPDATE NULL → 'real_outcome' for 3 P0-T7 allowlist sources + audit row |
| V040 | `sql/migrations/V040__finalize_evidence_source_tier.sql` | ALTER COLUMN SET NOT NULL + ADD CHECK enum allowlist |
| V040_healthcheck | `sql/migrations/V040_healthcheck.sql` | 3 read-only probes (NULL count / tier distribution / constraint state) |
| pytest fixture | `tests/migrations/test_v038_v039_v040_evidence_source_tier.py` | 17 static-parse tests covering 4 dispatch deliverables (V3 §12 #5/#7) |
| Ledger row | `sql/migrations/REF-20_RESERVATION.md` v1.2 | V038/V039/V040 status reserved → land |

紅線符合 / Red lines pass：

- ✅ 0 single-step ALTER NOT NULL（必 3-step 含 backfill）
- ✅ 0 production data lose（V039 WHERE evidence_source_tier IS NULL → 0 row clobber）
- ✅ 0 force-update 既有 non-NULL row（同上 IS NULL guard）
- ✅ 27 row engine_mode='live' 走 'real_outcome'（V039 source IN ('ml_shadow', ...) 命中）
- ✅ 0 actual migration apply 在 Mac dev env
- ✅ 4/4 SQL file 雙語表頭（Purpose / 目的）
- ✅ 編號順序 V038 → V039 → V040（operator manual sequence）
- ✅ 0 hardcoded `/home/ncyu` / `/Users/<u>` 路徑
- ✅ pytest 17/17 PASS

---

## 1. V038 — ADD COLUMN nullable

### 1.1 設計重點

- `ALTER TABLE learning.mlde_shadow_recommendations ADD COLUMN IF NOT EXISTS evidence_source_tier TEXT;`（**無 NOT NULL**）
- 上 Guard B：偵測欄位型別漂移（若 partial apply 存留為非 text 型，RAISE 給 operator 解漂移後再 run）
- 雙語 header + COMMENT ON COLUMN

### 1.2 為什麼 nullable

V3 §4.2 spec 對 `evidence_source_tier` 最終目標是 `NOT NULL DEFAULT 'real_outcome' CHECK enum`。但既有 ~2,482 row（4-day window，2026-04-29 後）+ 持續每小時 cycle 寫入流量，若 V038 一次 ADD COLUMN NOT NULL DEFAULT 會：

1. 觸發 hypertable 全表 rewrite（鎖表，影響 producer cron cycle）
2. 違反 V3 §7.1 風險 #3 「3-step migration 必含」
3. 與 P0-T7 ambiguous-classification 流程脫鉤（雖然本次 0 ambiguous，但 SOP 必保留）

故 V038 stays nullable，留 V039 mass UPDATE + V040 ALTER NOT NULL + CHECK 兩步處理。

### 1.3 Guard B 觸發場景

| 場景 | 結果 |
|---|---|
| Fresh apply（欄位不存在）| Guard B SELECT 返回 NULL → no-op；ADD COLUMN 自然加上 |
| 第二次 apply（欄位已存在為 text）| Guard B notice，ADD COLUMN IF NOT EXISTS no-op，整檔 idempotent |
| 部分漂移（欄位存在但型別非 text；e.g. operator 手動 DROP + ADD as VARCHAR(50)）| Guard B RAISE，要求解漂移後重 run |

---

## 2. V039 — Backfill 'real_outcome' for 3 sources

### 2.1 設計重點

```sql
WITH updated AS (
    UPDATE learning.mlde_shadow_recommendations
       SET evidence_source_tier = 'real_outcome'
     WHERE evidence_source_tier IS NULL
       AND source IN ('dream_engine', 'ml_shadow', 'opportunity_tracker')
    RETURNING 1
)
SELECT COUNT(*) INTO v_updated_count FROM updated;

INSERT INTO learning.governance_audit_log (...) VALUES (
    now(), 'bulk_re_evaluation', NULL, NULL, NULL,
    'evidence_source_tier_backfill', ARRAY[]::TEXT[],
    'migration:V039',
    jsonb_build_object(
        'migration_id', 'V039', 'task_id', 'R20-P2a-S6',
        'rows_updated', v_updated_count,
        'allowlist', ['dream_engine', 'ml_shadow', 'opportunity_tracker'],
        'classification', 'real_outcome',
        'env', current_setting('replay.migration_env', true),
        'preflight_distinct_sources', 3,
        'preflight_ambiguous', 0, 'preflight_forbidden', 0
    )
);
```

### 2.2 P0-T7 source classification 證據鍊（dispatch §2 #2 PM clarify）

| source | row_count (4d) | tier 分類 | 27-live 處理 |
|---|---:|---|---|
| dream_engine | 1,117 | real_outcome | N/A (engine_mode in [demo, live_demo]) |
| ml_shadow | 1,185 | real_outcome | **27 row engine_mode='live'** 也走 real_outcome（demo applier audit, applied=false, no manifest_hash） |
| opportunity_tracker | 180 | real_outcome | N/A |

**P0-T7 dispatch §2 #2 PM clarify 對齊：** 27 row 是 LG-5 promotion-candidate audit row，applied=false / decision_lease_id=NULL / replay_experiment_id will be NULL（V038 加完仍 NULL）/ manifest_hash will be NULL —— 滿足 V3 §4.2 的「real_outcome AND replay_experiment_id IS NULL AND manifest_hash IS NULL」分支。V039 的 WHERE source IN (...) 不過濾 engine_mode，故 27 row 自然命中。

### 2.3 Guard B / B' 雙重前置

- Guard B：V038 已 land（欄位以 text 型存在）— RAISE if missing
- Guard B'：V035 已 land（governance_audit_log 表存在）— RAISE if missing

### 2.4 幂等性

| 場景 | 行為 |
|---|---|
| 第 1 次 apply | UPDATE N row（4-day window 預期 ~2,482，但實際取決 operator deploy 時點當下 NULL row count）+ INSERT 1 audit row |
| 第 2 次 apply | UPDATE 0 row（IS NULL guard 已清空）+ INSERT 1 audit row（rows_updated=0）|
| V038 未 land | Guard B RAISE「V038 must run before V039」 |
| V035 未 land | Guard B' RAISE「V035 must run before V039」 |

第 2 次 apply 時 UPDATE 為 0 row 是預期幂等行為；但 audit table 多一 row 是設計選擇（operator 重 apply 時可從 audit log 看到 rows_updated=0 確認 noop）。

---

## 3. V040 — ALTER NOT NULL + CHECK enum allowlist

### 3.1 設計重點

```sql
-- Guard B: 0 NULL row precheck
SELECT COUNT(*) INTO v_null_count FROM ... WHERE evidence_source_tier IS NULL;
IF v_null_count > 0 THEN
    RAISE EXCEPTION 'V040 Guard B: % rows have NULL evidence_source_tier. V039 backfill must complete before V040.';
END IF;

ALTER TABLE learning.mlde_shadow_recommendations
    ALTER COLUMN evidence_source_tier SET NOT NULL;

-- Conditional ADD CONSTRAINT (idempotent)
IF NOT EXISTS (... pg_constraint conname = 'chk_evidence_source_tier' ...) THEN
    ALTER TABLE ... ADD CONSTRAINT chk_evidence_source_tier
        CHECK (evidence_source_tier IN (
            'real_outcome', 'calibrated_replay',
            'synthetic_replay', 'counterfactual_replay'
        ));
END IF;

-- Guard B'': post-apply verification
- is_nullable = 'NO' (RAISE if YES)
- pg_constraint EXISTS (RAISE if missing)
```

### 3.2 4 enum value 來源（V3 §4.2 line 189-194）

| tier | scope |
|---|---|
| `real_outcome` | 既有 producer 寫實際觀察值（V039 backfill 對應） |
| `calibrated_replay` | P3a calibration replay output |
| `synthetic_replay` | P2 S3 synthetic OHLC tick replay |
| `counterfactual_replay` | P4+ MLDE replay veto/rank advisory output |

V040 之後任何 INSERT 不寫合法 tier 值會被 CHECK 拒絕；現有 4 producer 由 R20-P2a-S4（V036 verify function）已切到 verify-and-insert path，writes 'real_outcome'。

### 3.3 Operator 部署檢查清單

```bash
# Step 1: 檢查 V040 ready (0 NULL row 預期)
psql -f sql/migrations/V040_healthcheck.sql
# 預期: null_check.null_row_count = 0
#       constraint_state.is_nullable = YES
#       constraint_state.has_check_constraint = false

# Step 2: 若 step 1 預期符合，apply V040
psql -f sql/migrations/V040__finalize_evidence_source_tier.sql

# Step 3: 再跑 healthcheck 驗 V040 land 成功
psql -f sql/migrations/V040_healthcheck.sql
# 預期: null_check.null_row_count = 0
#       constraint_state.is_nullable = NO
#       constraint_state.has_check_constraint = true
```

### 3.4 NULL row recovery flow（V3 §4.2 ambiguous-rows policy）

若 step 1 healthcheck 顯示 >0 NULL row（不應發生，但 SOP 留下安全網）：

1. `SELECT source, COUNT(*) FROM ... WHERE evidence_source_tier IS NULL GROUP BY 1;` → 找出 unknown source
2. PM 依 V3 §4.2 ambiguous-rows protocol classify：real_outcome / ambiguous / excluded
3. 寫一次性 `V039_PATCH_*.sql`（取 V045 buffer 編號 PM 預留）對 unknown source backfill
4. 重跑 V040 healthcheck 驗 0 NULL → V040 apply

---

## 4. V040_healthcheck.sql — 3 read-only probes

| Probe | SQL | 部署前期望 | 部署後期望 |
|---|---|---|---|
| Probe 1 | `COUNT(*) WHERE IS NULL` | 0 (V039 後) | 0 |
| Probe 2 | `GROUP BY tier` | 1 row: real_outcome | 1+ row: real_outcome 起步，未來新 tier 加入 |
| Probe 3 | `is_nullable + has_check + check_definition` | YES / false / NULL | NO / true / `CHECK (... IN (...4 values...))` |

完全 read-only（pytest enforce 無 INSERT/UPDATE/DELETE/ALTER/CREATE/DROP keyword）。可 ssh `psql -f` 跑為 cron healthcheck。

---

## 5. Pytest fixture — 17 static-parse tests

### 5.1 為什麼 mock 而非真 DB

- Mac dev no PostgreSQL 連線（全 runtime 在 Linux trade-core）— 跨平台合規
- 本層是「靜態 compile-time gate」 → E2 review-ready bundle
- 真 DB integration 由 Linux operator psql apply + V040_healthcheck.sql 驗

### 5.2 17 test 覆蓋

| Test class | 子測試 | 對應 dispatch §E |
|---|---|---|
| `TestV038AddColumn` | `test_adds_nullable_text_column` | dispatch §E #1 ADD COLUMN nullable |
| | `test_v038_has_guard_b` | Guard B template compliance |
| `TestV039Backfill` | `test_updates_only_allowlisted_sources` | dispatch §E #2 backfill 3 source |
| | `test_does_not_force_update_existing_non_null` | 紅線 #3「不 force-update 既有 non-NULL」 |
| | `test_writes_governance_audit_log_row` | dispatch §D INSERT governance_audit_log |
| | `test_v039_has_guards` | Guard B/B' 雙前置 |
| `TestV040Finalize` | `test_alters_column_not_null` | dispatch §E #3 ALTER NOT NULL |
| | `test_adds_check_constraint_with_4_value_allowlist` | dispatch §E #4 CHECK with 4 enum |
| | `test_v040_check_rejects_invalid_tier_values` | CHECK IN list 嚴格 = 4 values |
| | `test_v040_has_null_precheck_guard` | Guard B 0-NULL precheck |
| `TestHealthcheck` | `test_healthcheck_file_exists` | dispatch §D V040_healthcheck.sql |
| | `test_healthcheck_has_3_probes` | 3 probe 結構 |
| | `test_healthcheck_is_read_only` | 紅線 read-only |
| `TestBilingualComments` | `test_bilingual_header[path0..3]` | CLAUDE.md §七 雙語對照（4 file × 1） |

### 5.3 執行結果

```
============================== 17 passed in 0.01s ==============================
```

---

## 6. V3 §12 acceptance binding

| # | Acceptance | 本 task 滿足？ | 證據 |
|---|---|---|---|
| #5 | evidence_tier_completeness: 0 NULL row post-V040 | ✅（V040 ALTER NOT NULL + Guard B precheck）| V040 Guard B, Guard B'' |
| #7 | registry_fk: 0 dangling | ⏳ 不直屬本 task；R20-P2a-S6 step 不動 FK | V3 §4.2 spec 由 R20-P2a-S4 verify function 守護 |
| backfill_report 0 ambiguous | ✅（P0-T7 evidence: 0 ambiguous, 0 forbidden）| `mlde_shadow_source_classification.md` |

---

## 7. PM 確認 / Ambiguity 不確定點（dispatch context "1 ambiguity 預期"）

dispatch context「期待 1 ambiguity (V042 archive vs V038-V040 fence sequence — V042 預留 R20-P2a-S2 已 land Wave 2，本 task 不衝突)」：

**ambiguity 解釋：** REF-20_RESERVATION.md §3 中 V042 是 R20-P2a-S2 + G9 「replay_signing_keys 表」預留；R20-P2a-S2 是 Wave 2 已 land；V042 file artifact 應已存在。本 task 對 V038/V039/V040（不重疊 V042 編號），無實際衝突。

**驗證確認：** V042 SQL file 編號是 sibling agent 該 land 的範圍；本 E1 sub-agent 不接觸 V042（保持 PA 派發邊界紅線「不擴大改動範圍」）。

**未決事項回 PM：**

1. **V039 audit row 重複 apply 是否需 dedup？** 設計選擇是「每次 apply 寫 1 audit row，rows_updated 反映實際 UPDATE 數」（重 apply 時 rows_updated=0 是有效記錄）。如 PM 想要「同 migration_id 唯一」可改用 `INSERT ... ON CONFLICT DO NOTHING`，但需 governance_audit_log 加 UNIQUE (migration_id) constraint —— 不在本 task 範圍。

2. **`current_setting('replay.migration_env', true)` 是否會 NULL？** 本檔已加 fallback 為 `'unknown'`。Operator 跑 psql 時若想標記環境，可：
   ```bash
   psql -c "SET replay.migration_env = 'linux_trade_core'" -f V039__backfill_evidence_source_tier.sql
   ```
   但目前不 enforce；audit row 標 'unknown' 不影響功能。

3. **Healthcheck 是否要進 cron？** V040_healthcheck.sql 適合放 `helper_scripts/db/passive_wait_healthcheck/checks_execution.py` 加 `check_evidence_source_tier_completeness()` Python wrapper（V3 §4.2 spec required healthchecks 列表中明確含此項）。**不在本 task 範圍**；後續 task 由 PA 派 E1 加 Python wrapper。

4. **V040 land 順序與 R20-P2a-S4 V037 REVOKE 的時序：** V037 REVOKE INSERT FROM PUBLIC 之後，新 INSERT 全走 `verify_replay_evidence_and_insert()` function。如該 function 內 evidence_source_tier 預設值未 align V040 CHECK enum，會 CHECK fail。建議 PM operator deploy 順序：

   ```
   V037 (REVOKE)  →  Producer 切換驗  →  V038  →  V039  →  V040 healthcheck → V040
   ```

   或反向（`V038 → V039 → V040 healthcheck → V040 → V037`），看 PM 排程意圖。本 E1 task 不擴大此邊界。

---

## 8. 修改清單

| File | Operation | Lines |
|---|---|---:|
| `sql/migrations/V038__add_evidence_source_tier.sql` | NEW | 88 |
| `sql/migrations/V039__backfill_evidence_source_tier.sql` | NEW | 175 |
| `sql/migrations/V040__finalize_evidence_source_tier.sql` | NEW | 199 |
| `sql/migrations/V040_healthcheck.sql` | NEW | 110 |
| `tests/migrations/__init__.py` | NEW (empty package marker) | 0 |
| `tests/migrations/test_v038_v039_v040_evidence_source_tier.py` | NEW | 308 |
| `sql/migrations/REF-20_RESERVATION.md` | UPDATE row V038/V039/V040 + add v1.2 history | +5 / -3 |

**單純新增**（除 `REF-20_RESERVATION.md` ledger row update + history append 1 行）。**0 既有檔被改動邏輯**。

---

## 9. PM commit message draft

```
feat(replay): V038/V039/V040 evidence_source_tier 3-step retrofit (Wave 3 P2a-S6)

REF-20 R20-P2a-S6 — `evidence_source_tier` 3-step retrofit migration on
learning.mlde_shadow_recommendations per V3 §3 G3 + §4.2:

- V038: ADD COLUMN evidence_source_tier TEXT NULLABLE (no production write impact)
- V039: backfill NULL → 'real_outcome' for 3 P0-T7 allowlist sources
        (dream_engine / ml_shadow / opportunity_tracker; 27 ml_shadow
        engine_mode='live' audit row also → 'real_outcome' per dispatch §2 #2)
        + governance_audit_log batch row
- V040: ALTER COLUMN SET NOT NULL + ADD CHECK enum constraint
        (real_outcome / calibrated_replay / synthetic_replay / counterfactual_replay)

Sibling helper sql/migrations/V040_healthcheck.sql (3 read-only probes:
NULL count / tier distribution / constraint state).

Pytest fixture tests/migrations/test_v038_v039_v040_evidence_source_tier.py
17/17 PASS (Mac dev static-parse layer; Linux operator deploys real psql).

V3 §12 acceptance: #5 evidence_tier_completeness 0 NULL post-V040.
Ledger sql/migrations/REF-20_RESERVATION.md v1.2 status reserved → land.
```

---

## 10. 不確定之處 + Operator 下一步

### 不確定之處

1. **V040 deploy 順序** 與 R20-P2a-S4 V037 REVOKE 的相互依賴（見 §7 #4）—— 由 PM 整合 P2a 全 wave deploy plan 決定。
2. **Healthcheck cron** 是否要 Python wrapper —— 由 PM 後續派 task。
3. **27-live row 在 V040 之後的後續處理**：dispatch context 已 PM clarify「走 real_outcome」；但 LG-5 promotion-candidate audit row 流程是否在 P5+ 改寫成不在 mlde_shadow_recommendations 而走 `replay.experiments` —— 屬 future scope，不 block 本 task。

### Operator 下一步（PM commit + push 之後）

1. E2 review（可順手 grep `INSERT INTO learning.mlde_shadow_recommendations` 0 直接 INSERT — 其實本 task 不改 producer，Producer 切換是 R20-P2a-S4 範圍）
2. E3 安全 review（Guard B 邏輯 / governance_audit_log 寫權限）
3. MIT review（CHECK enum 4-value contract 對齊 V3 §4.2）
4. PM ambiguous classify review-ready flag（P0-T7 已驗 0 ambiguous，本 task 無需 PM 個別 classify）
5. PM 整合 commit + push（Mac → Linux trade-core）
6. Linux operator deploy 順序：V038 → V039 → `psql -f V040_healthcheck.sql` 驗 0 NULL → V040 → 再驗 healthcheck 後狀態
7. V3 §12 #5 evidence_tier_completeness 進入 hourly probe（PM 在後續 task 加 Python wrapper）

---

## 11. 雙語注釋合規 / Bilingual comment compliance（CLAUDE.md §七）

本 task 全部新檔中英對照：
- 4 SQL file header `Purpose / 目的`、`3-step sequence / 三步序列`、Guard 段中英對照
- pytest 模組 docstring + 函數 docstring + inline 不變量中英對照
- COMMENT ON COLUMN 加長字串內 `... / ...` 中英對照
- ledger v1.2 row 中文為主，技術名詞保留英文

E2 grep 不會抓到「無 MODULE_NOTE / 無 docstring」違規。

---

## 12. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v1 | 2026-05-03 | E1 (R20-P2a-S6) | Initial 3-step retrofit + healthcheck + 17/17 pytest PASS；ledger v1.2 status reserved → land |

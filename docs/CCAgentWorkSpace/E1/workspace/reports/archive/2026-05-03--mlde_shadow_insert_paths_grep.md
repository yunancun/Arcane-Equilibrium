# REF-20 R20-P0-T6 — `learning.mlde_shadow_recommendations` INSERT 路徑全 codebase grep
# REF-20 R20-P0-T6 — Full-codebase grep of INSERT paths into `learning.mlde_shadow_recommendations`

**日期 / Date：** 2026-05-03
**Owner：** E1 (sub-agent, Wave 1 task)
**契約上游 / Upstream contract：**
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 1 R20-P0-T6 + Wave 3 R20-P2a-S6
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §4.2 (`evidence_source_tier` retrofit + `verify_replay_evidence_and_insert()` PL/pgSQL spec)

**Mode：** READ-ONLY grep + ssh probe；0 INSERT/UPDATE/DELETE 寫入 / 0 source-code modification.
**Mode (EN):** READ-ONLY grep + ssh probe; zero INSERT/UPDATE/DELETE writes; zero source-code modifications.

---

## 0. TL;DR

- **直接 INSERT 路徑 / Direct INSERT paths：4 producer + 1 test fixture（5 hits）**
- **ORM / stored proc INSERT：0**
- **Rust 端 INSERT：0**（grep `mlde_shadow_recommendations` in `rust/` returns no match）
- **Trigger pattern：全部由 `edge_estimator_scheduler.py` 每小時 cycle 串行驅動**（cycle=3600s）
- **R20-P2a-S6 必改 producer 點：4 處**（`dream_engine.py:350` / `opportunity_tracker.py:236` / `mlde_shadow_advisor.py:302` / `mlde_demo_applier.py:1223`）
- **schema CHECK 已限制 source ∈ {'linucb','ml_shadow','dream_engine','opportunity_tracker'}**（無需擔心新 source 偷渡）
- **27 rows engine_mode='live'**（`mlde_demo_applier._insert_live_candidate` LG-5 audit row, applied=false; not real live mutation）

---

## 1. Grep 命令 / Grep commands

### 1.1 直接 INSERT statement

```bash
grep -rn 'INSERT INTO learning.mlde_shadow_recommendations' \
  program_code/ rust/ sql/ helper_scripts/ 2>/dev/null
```

注意：CLAUDE.md / V1 workplan 雖寫 `python/` 路徑但本 repo 實際 Python source 在 `program_code/`，已修正。
Note: workplan referenced `python/` but actual Python source lives in `program_code/`; corrected.

### 1.2 廣泛 reference + execute pattern

```bash
grep -rn 'mlde_shadow_recommendations' \
  program_code/ rust/ sql/ helper_scripts/ 2>/dev/null \
  | grep -iE 'insert|execute|executemany|copy_from|copy '
```

---

## 2. INSERT 路徑詳細 / INSERT path inventory

### 2.1 Producer A — `dream_engine.persist_dream_insights()`

| 字段 / Field | 值 / Value |
|---|---|
| File / 檔案 | `program_code/local_model_tools/dream_engine.py` |
| Line / 行 | **350** |
| Function / 函數 | `persist_dream_insights(dsn, *, engine_mode='demo', cfg=None)` |
| Caller / 呼叫者 | `edge_estimator_scheduler.py:587-589` (cron-like, cycle=3600s) |
| Trigger condition / 觸發 | hourly cycle, every engine_mode in `[demo, live_demo]`; gated by non-empty `summary['insights']` list |
| `source` written? | YES — **constant `'dream_engine'`**（SQL literal, line 355） |
| `engine_mode` written? | parameter `cfg.engine_mode`（passed from scheduler `mode`，可能 `demo` / `live_demo`） |
| Producer 分類 / Producer category | **Producer A: ML pipeline（DreamEngine 主產生 parameter_proposal）** |
| `recommendation_type` 常量 | `'parameter_proposal'`（SQL literal） |
| `created_by` 常量 | `'mlde_dream_engine'`（SQL literal） |
| `applied` / `requires_governance` | `false` / `true`（hardcoded） |

```python
# dream_engine.py:347-367 (excerpt)
for insight in insights:
    cur.execute(
        """
        INSERT INTO learning.mlde_shadow_recommendations
            (engine_mode, strategy_name, source, recommendation_type,
             primary_metric, expected_net_bps, confidence, sample_count,
             payload, applied, requires_governance, created_by)
        VALUES
            (%s, %s, 'dream_engine', 'parameter_proposal',
             'net_bps_after_fee', %s, %s, %s, %s,
             false, true, 'mlde_dream_engine')
        """,
        (cfg.engine_mode, insight.get("strategy_name"), ...))
```

### 2.2 Producer B — `opportunity_tracker.persist_regret_summary()`

| 字段 / Field | 值 / Value |
|---|---|
| File / 檔案 | `program_code/local_model_tools/opportunity_tracker.py` |
| Line / 行 | **236** |
| Function / 函數 | `persist_regret_summary(dsn, *, engine_mode='demo', cfg=None)` |
| Caller / 呼叫者 | `edge_estimator_scheduler.py:594-596` (cron-like, cycle=3600s) |
| Trigger condition / 觸發 | hourly cycle; `sample_count >= cfg.min_samples`（MIT-S2-6 noise gate） |
| `source` written? | YES — **constant `'opportunity_tracker'`**（SQL literal, line 241） |
| `engine_mode` written? | parameter `cfg.engine_mode` |
| Producer 分類 / Producer category | **Producer A: ML pipeline（regret summary 廣義屬 ML observation）** |
| `recommendation_type` 常量 | `'regret_summary'`（SQL literal） |
| `created_by` 常量 | `'mlde_opportunity_tracker'`（SQL literal） |
| `applied` / `requires_governance` | `false` / `true`（hardcoded） |

### 2.3 Producer C — `mlde_shadow_advisor._persist_recommendations()`

| 字段 / Field | 值 / Value |
|---|---|
| File / 檔案 | `program_code/ml_training/mlde_shadow_advisor.py` |
| Line / 行 | **302** |
| Function / 函數 | `_persist_recommendations(dsn, recommendations) -> int` |
| Caller / 呼叫者 | `mlde_shadow_advisor.generate_shadow_recommendations()` ← `edge_estimator_scheduler.py:574-582`（cron-like, cycle=3600s） |
| Trigger condition / 觸發 | hourly cycle; non-empty `recommendations` list |
| `source` written? | YES — **變量 `rec.source`**（不是常量；source 由 `ShadowRecommendation` dataclass 構造時帶入） |
| `engine_mode` written? | 變量 `rec.engine_mode`（同上） |
| Producer 分類 / Producer category | **Producer A: ML pipeline（mlde_shadow_recommender 主路徑 = ml_shadow rank/veto）** |
| `recommendation_type` 變量 | `rec.recommendation_type`（dataclass 帶入；schema CHECK 限定 ∈ {rank/veto/...}） |
| `created_by` 常量 | `'mlde_shadow_advisor'`（SQL literal） |
| `applied` / `requires_governance` | `false` / `true`（hardcoded） |

**source 變量推導路徑 / `source` variable derivation path：**
- `mlde_shadow_advisor` 內 `ShadowRecommendation` dataclass 構造時直接 set `source='ml_shadow'`（lib-internal contract; 唯一可能值）
- Schema CHECK 排除 `linucb`/`dream_engine`/`opportunity_tracker` 從此 producer 寫入

### 2.4 Producer D — `mlde_demo_applier._insert_live_candidate()`

| 字段 / Field | 值 / Value |
|---|---|
| File / 檔案 | `program_code/ml_training/mlde_demo_applier.py` |
| Line / 行 | **1223** |
| Function / 函數 | `_insert_live_candidate(cur, *, source_row, application_id, application_type, patch)` |
| Caller / 呼叫者 | `_apply_one()` line 1367，gated by `status == 'applied' and should_create_live_candidate(row, cfg)`（line 1366）|
| Trigger condition / 觸發 | demo apply 完成且 `expected_net_bps >= cfg.live_candidate_min_net_bps && confidence >= cfg.live_candidate_min_confidence && samples >= cfg.live_candidate_min_samples` |
| Outer caller / 外層呼叫 | `run_mlde_demo_applier()` ← `edge_estimator_scheduler.py:602-608`（cron-like, cycle=3600s, only `mode='demo'` executes applier） |
| `source` written? | YES — **constant `'ml_shadow'`**（SQL literal, line 1228） |
| `engine_mode` written? | **HARDCODED `'live'`**（SQL literal, line 1228） |
| Producer 分類 / Producer category | **Producer A 變體（LG-5 demo→live promotion candidate audit row；不是 real-outcome producer）** |
| `recommendation_type` 常量 | `'experiment_plan'`（SQL literal） |
| `created_by` 常量 | `'mlde_demo_applier'`（SQL literal） |
| `applied` / `requires_governance` | `false` / `true`（hardcoded） |

```python
# mlde_demo_applier.py:1221-1240 (excerpt)
cur.execute(
    """
    INSERT INTO learning.mlde_shadow_recommendations
        (engine_mode, symbol, strategy_name, source, recommendation_type,
         primary_metric, expected_net_bps, confidence, sample_count,
         payload, applied, requires_governance, created_by)
    VALUES
        ('live', %s, %s, 'ml_shadow', 'experiment_plan',
         'net_bps_after_fee', %s, %s, %s, %s, false, true,
         'mlde_demo_applier')
    """,
    ...
)
```

**重要 / Important：** 這 27 row engine_mode='live' 是 **LG-5 §2.1 audit/monitoring trail**（`applied=false`），非真 live mutation。Consumer 真正讀的 row 在 `mlde_param_applications`（FK 回 `mlde_shadow_recommendations.id`）。下游 `lg5_review_consumer_scheduler` (`463890d` sibling CC) 從這條鏈 drain。

### 2.5 Test fixture — `test_mlde_demo_applier.py:426`

| 字段 / Field | 值 / Value |
|---|---|
| File / 檔案 | `program_code/ml_training/tests/test_mlde_demo_applier.py` |
| Line / 行 | **426** |
| Trigger / 觸發 | unittest assertion only |
| Producer category | **Test fixture（不在 production path）** |

---

## 3. Migration backfill / 預存欄位 / SQL 文件

| File | 用途 / Purpose | INSERT? |
|---|---|---|
| `sql/migrations/V031__ml_dream_edge_unblock.sql:402` | `CREATE TABLE IF NOT EXISTS` 主 schema + Guard A | NO（DDL only） |
| `sql/migrations/V032__mlde_demo_param_applications.sql:78` | `mlde_param_applications.recommendation_id REFERENCES mlde_shadow_recommendations(id)` | NO（FK only） |
| `sql/migrations/tests/test_v028_v034_guards.sql:33,350,391` | Guard A test fixture | NO（DDL test only） |

**Migration backfill INSERT：0**（V028-V034 retrofit 無往 mlde_shadow_recommendations 補資料）

---

## 4. ORM / stored proc / COPY 路徑

| Pattern / 樣式 | Hits | 結論 |
|---|---|---|
| `INSERT INTO learning.mlde_shadow_recommendations` | 5（4 producer + 1 test） | enumerated above |
| ORM model class / SQLAlchemy / Pydantic ORM | 0 | 非 ORM-managed |
| `COPY learning.mlde_shadow_recommendations` / `copy_from` | 0 | 無 bulk-load 路徑 |
| stored procedure 已存在 | 0（V031 + V032 無 PL/pgSQL function 寫入）| R20-P2a-S6 即將新增 `verify_replay_evidence_and_insert()` |
| Rust `INSERT` / sqlx | 0 | grep `rust/` returns nothing |

---

## 5. 統計 / Statistics

| 指標 / Metric | 值 / Value |
|---|---|
| 直接 INSERT path | **5**（4 producer + 1 test）|
| 走 stored proc INSERT | 0 |
| 經 ORM INSERT | 0 |
| Rust INSERT | 0 |
| Migration backfill INSERT | 0 |
| Trigger pattern 數 | 1（hourly scheduler thread, `EdgeEstimatorScheduler.run_loop()`） |
| Producer 函數數 | **4**（dream / opportunity / shadow_advisor / demo_applier）|
| Producer A（ML pipeline 主路徑） | 4（全部）|
| Producer B（其他 advisor / scanner） | 0 |
| Test fixture | 1 |

---

## 6. R20-P2a-S6 verified-insert function 切換 surgical change list

**契約上游 / Upstream contract：**
V3 §4.2 要求 `verify_replay_evidence_and_insert()` PL/pgSQL function（SECURITY INVOKER），CHECK replay registry FK + manifest_hash + source tier + output policy。R20-P2a-S6 的 3-PR sequence 第二步「producer 切換」必動以下 4 點：

| # | File:Line | 函數 / Function | 修改類型 / Change type | 風險 / Risk |
|---|---|---|---|---|
| 1 | `program_code/local_model_tools/dream_engine.py:350-358` | `persist_dream_insights` | 從 `INSERT INTO learning.mlde_shadow_recommendations (...)` 改為 `SELECT learning.verify_replay_evidence_and_insert(...)` 或 wrap function | LOW（純 advisory，applied=false; switch idempotent if function preserves row shape）|
| 2 | `program_code/local_model_tools/opportunity_tracker.py:236-243` | `persist_regret_summary` | 同上 | LOW（同上）|
| 3 | `program_code/ml_training/mlde_shadow_advisor.py:301-308` | `_persist_recommendations` | 同上（注意此處 source 是變量 `rec.source`，需 verified function 接受 source argument） | MEDIUM（`recommendation_type` 也是變量；function signature 需支援更廣參數）|
| 4 | `program_code/ml_training/mlde_demo_applier.py:1221-1240` | `_insert_live_candidate` | 同上（注意此處 hardcoded `'live'` engine_mode + LG-5 §2.1 schema_version 必保留 payload） | **HIGH**（這是 LG-5 promotion-candidate audit trail，下游 `lg5_review_consumer` 依賴此 row 存在；任何 schema 漂移會 break LG-5 reviewer pipeline） |

**重要：R20-P2a-S6 切換時必先檢查 `learning.mlde_param_applications` FK 行為**：
此 FK ON DELETE SET NULL（V032:78）；若 verified-insert function 改用 different sequence / id allocation，必確保 sequence 名稱 `mlde_shadow_recommendations_id_seq` 仍可被 grant；否則 LG-5 audit chain `mlde_shadow_recommendations.id ↔ mlde_param_applications.recommendation_id` 斷鏈。

---

## 7. R20-P2a-S6 producer 切換 PR 排序建議 / suggested PR sequence

per V3 §4.2 「3-PR sequence: function+grant → producer 切換 → REVOKE」：

**PR-A**（function 上線、producer 不動，writes both old + new path 共存可選）：
1. `sql/migrations/V0XX__replay_evidence_source_guard.sql` — `verify_replay_evidence_and_insert()` PL/pgSQL function + GRANT EXECUTE TO `openclaw_writer`
2. Healthcheck `mlde_replay_source_guard` baseline 採 `WARN`（function 存在但未 enforced）

**PR-B**（producer 切換）：
1. 4 producer point 改用 `verify_replay_evidence_and_insert()`（按上表 risk 順序：先 LOW dream/opportunity → MEDIUM shadow_advisor → HIGH demo_applier）
2. 每 PR 切換後 healthcheck `mlde_replay_source_guard` 維持 WARN，但 row count distribution unchanged（baseline diff ≤5%）
3. **HIGH risk producer (#4 demo_applier) 切換需先在 staging shell 對 LG-5 §2.1 payload 做 schema_version 比對 unit test**

**PR-C**（REVOKE INSERT 收束）：
1. `REVOKE INSERT ON learning.mlde_shadow_recommendations FROM PUBLIC` + GRANT writer role only via function
2. Healthcheck `mlde_replay_source_guard` 升 PASS

---

## 8. 紅線 / Red lines

- 0 寫入 / 0 source modification（本 task 純 read-only）
- ssh trade-core 跑 `psql` 限定 SELECT + `\d`（schema introspection）；無 GRANT/REVOKE/ALTER
- grep 範圍：`program_code/` `rust/` `sql/` `helper_scripts/`（4 dir, 對齊 V1 workplan §4 R20-P0-T6 範圍）
- 不修任何 source code（本報告僅作 doc）

---

## 9. 雙語注釋 / Bilingual comment compliance（CLAUDE.md §七）

本 report 全文中英對照（標題雙語 / 表頭雙語 / 段落必要時雙語），符合：
- `MODULE_NOTE` 中英對照（§0 TL;DR）
- 表頭中英對照（§2 producer 表）
- 函數 / 函數 / 觸發條件等技術描述雙語（§2.1-2.4）
- 修改類型 / 風險 / 方向等業務描述雙語（§6 surgical change list）

---

## 10. PM 必看 / unknowns

1. **`linucb` source 值有 schema CHECK allow 但 0 實際 row 寫入**（`SELECT DISTINCT source` 無 'linucb'）— 可能是 LinUCB pipeline 不直接寫 mlde_shadow_recommendations，而是寫 `learning.linucb_*` 自己的 table；R20-P2a-S6 retrofit 時要確認 `linucb` 是否需要列為 verified-insert function 接受的 source value（建議 PM 排除）
2. **`mlde_demo_applier._insert_live_candidate` hardcoded `'live'` engine_mode 且不依 cfg.engine_mode**：是 LG-5 §2.1 spec 設計（demo→live promotion candidate 必標記 'live' for downstream live reviewer 處理），R20-P2a-S6 切換時必保留此語意（PM 確認）
3. **27 row engine_mode='live' & `created_by='mlde_demo_applier'` 全 ma_crossover strategy**：可能與 ma_crossover net_bps_after_fee 高於 demo→live promotion threshold 有關（無 stride 跨策略多樣性）；非 grep task 範圍但 PM 可能需要關注 `should_create_live_candidate` threshold 是否合適（live_candidate_min_net_bps / min_confidence / min_samples）
4. **`should_create_live_candidate` cfg 欄位現值 PM 確認**：目前 demo applier 連續觸發 27 ma_crossover live candidate 但 0 actually applied（applied=false in all 27 rows）— 是 LG-5 reviewer 還沒 deploy 的預期狀態（per CLAUDE.md §三 [42]/[42b]，sibling CC FUP-1 commit `463890d` 待 deploy 後啟動）

---

## 11. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v1 | 2026-05-03 | E1 (sub-agent, R20-P0-T6) | Initial grep + producer enumeration; 4 producer + 1 test fixture; R20-P2a-S6 surgical change list 含 4 點 |

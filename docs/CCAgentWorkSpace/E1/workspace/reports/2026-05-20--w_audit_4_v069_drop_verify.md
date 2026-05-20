---
作者: E1 (Backend Developer)
日期: 2026-05-20
任務: P2-AUDIT-VERIFY-3 — W-AUDIT-4 V069 drop 真實生效驗證
範圍: V069 migration 內容 / verify SQL probe / source tree grep / 殘留風險評估
邊界: verify 報告 only，不修源碼、不 ssh trade-core、不 commit
---

# §1 V069 migration 內容（drop list 全名）

## 1.1 檔案位置

- `srv/sql/migrations/V069__drop_dead_observability_scorer_predictions.sql`（48 行）

## 1.2 實際 drop list

V069 **唯一 DROP target**：

| Schema | Object | Type |
|---|---|---|
| `observability` | `scorer_predictions` | TABLE |

**注意**：原任務描述提及「6 個 ML dead schema」與 V069 SQL 不一致。實際 V069 SQL 內含的 MODULE_NOTE 已說明範圍 audit 修訂後縮窄：

```
-- W-AUDIT-4 originally proposed dropping scorer_predictions and
-- model_performance. Source audit corrected the scope:
--   - observability.scorer_predictions has no production reader/writer.
--   - observability.model_performance is still read by canary_promoter.
--   - observability.feature_baselines and observability.drift_events are kept
--     for the drift-detector contract pending V072 resolution.
```

確認本任務以 SQL 為準 = **1 表 DROP**。其餘 W-AUDIT-4 衍生 migration（V068 / V070 / V071）為 reclassification guard（COMMENT only / 0 destructive），V072 為 contract guard，已比對 grep 過內含 `DROP TABLE/VIEW/INDEX/FUNCTION/SCHEMA` keyword **0 hit** 確認。

## 1.3 Guard 結構

V069 採 **Guard A**（DROP Safety）三重保護：

1. `to_regclass('observability.scorer_predictions') IS NULL` → 已 drop 則 NOTICE return（冪等）
2. `count(*) <> 0` → `RAISE EXCEPTION 'V069 Guard A FAIL ... not empty'`（拒非空 drop）
3. `pg_depend / pg_rewrite` 查 dependent relation 數 → `<> 0` 則 `RAISE EXCEPTION ... dependent relation(s)`（拒被 view/rule 依賴）

DDL：`DROP TABLE IF EXISTS observability.scorer_predictions RESTRICT;`（RESTRICT 雙保險）

# §2 4 條 verify SQL probe（ready-to-run，含預期結果）

> 操作對象：`trading_ai` DB（Linux trade-core PG）
> 連線：以實際 `DSN` / `POSTGRES_*` env vars 為準
> 全部為唯讀 SELECT，無副作用

## Probe 1：information_schema.tables — drop target 不存在

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'observability'
  AND table_name IN ('scorer_predictions');
```

**預期結果**：0 rows。

**判讀**：
- 0 rows → V069 drop 真實生效。
- ≥1 row → drop 未 apply 或 schema 有殘留，需追 `schema_migrations` 是否含 V069 success=t。

## Probe 2：information_schema.routines — function/procedure 內無殘留引用

```sql
SELECT routine_schema, routine_name, routine_type
FROM information_schema.routines
WHERE routine_definition LIKE '%observability.scorer_predictions%'
   OR routine_definition LIKE '%scorer_predictions%';
```

**預期結果**：0 rows。

**判讀**：
- 0 rows → 無 stored function/procedure 引用 dropped table，V069 dependent check 已涵蓋。
- ≥1 row → DB 內存在引用 dropped table 的 function/procedure（V069 dependent check 只看 view/rule，未必覆蓋 function 體），需人工 review。

## Probe 3：pg_views — view 定義內無殘留引用

```sql
SELECT schemaname, viewname, definition
FROM pg_views
WHERE definition LIKE '%observability.scorer_predictions%'
   OR definition LIKE '%scorer_predictions%';
```

**預期結果**：0 rows。

**判讀**：
- 0 rows → 無 view 引用 dropped table（V069 Guard A 已用 pg_depend 拒絕 dependent drop）。
- ≥1 row → 異常：V069 Guard A 應已拒絕 drop。請即時把 pg_views 結果回報給 PA 評估是否需新 migration restore 或 view DROP。

## Probe 4：pg_indexes — index 已隨 DROP TABLE cascade 回收

```sql
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE indexname LIKE '%scorer_pred%'
   OR (schemaname = 'observability' AND tablename = 'scorer_predictions');
```

**預期結果**：0 rows。

**判讀**：
- 0 rows → DROP TABLE 已 cascade drop V005 建的 `idx_scorer_pred_model` / `idx_scorer_pred_executed`。
- ≥1 row → index 殘留（理論不可能，因 DROP TABLE 必 cascade indexes），需追 PG 異常或 schema rebuild 狀態。

## Probe 5（附贈，verify migration ledger）：schema_migrations 記錄 V069 success

```sql
SELECT version, description, success, applied_at
FROM schema_migrations
WHERE version = 'V069'
   OR description LIKE '%scorer_predictions%';
```

**預期結果**：1 row，`success = TRUE`。

**判讀**：用來確認 V069 確實已 apply（防止 information_schema 看不到表 + 但其實是 fresh start 沒跑過 V004 也沒跑 V069 的偽通過情境）。

# §3 Source tree grep 結果

## 3.1 Grep 範圍

Python：`program_code/`（實際 Python code 樹）+ `helper_scripts/` + `tests/`
Rust：`rust/`（含 openclaw_engine + openclaw_core + 其餘 crate）
全 srv 二次掃：排除 `__pycache__` / `*.pyc` / `.claude/worktrees/*` / `.git/`

## 3.2 Python hits（依分類）

| 檔:行 | 分類 | 該行 context | runtime impact |
|---|---|---|---|
| `helper_scripts/db/fresh_start_reset.py:136` | **string** (WIPE_TABLES list entry) | `("observability.scorer_predictions",  "model score log"),` | LOW — `_exact_count` 回 -1 觸發 `SKIPPED missing table` 分支（line 411-412），有對應 test `tests/helper_scripts/test_fresh_start_reset_missing_tables.py` 覆蓋 |
| `tests/migrations/test_v069_drop_dead_observability_scorer_predictions.py:10/14/17/25` | **test** | 驗 V069 SQL 內容 + Guard 邏輯 | LOW — 是 V069 本身的測試，合法保留 |
| `tests/helper_scripts/test_fresh_start_reset_missing_tables.py:13/26/28` | **test** | 驗 fresh_start_reset 對 dropped table 的 graceful skip | LOW — 防回歸測試，合法保留 |

**Python writer / reader hit**：**0** （`INSERT INTO/SELECT FROM/UPDATE observability.scorer_predictions` 全文 0 hit）。

## 3.3 Rust hits

| 檔:行 | 分類 | 該行 context |
|---|---|---|
| (none) | — | Rust workspace 0 hit（`grep -rn 'scorer_predictions\|scorer_pred' rust/ 2>/dev/null \| grep -v target` 全 empty） |

**Rust writer / reader hit**：**0**。

## 3.4 SQL migration hits（已 applied 的歷史 migration）

| 檔:行 | 分類 | 該行 context | 風險 |
|---|---|---|---|
| `sql/migrations/V004__learning_features_obs_risk_tables.sql:24/309/313/330/526` | **migration-history** (CREATE TABLE + hypertable + comment) | V069 的 drop target 是這裡 CREATE 的 | NONE — 歷史 migration 不會 re-apply，schema_migrations 已記 V004 success；fresh DB rebuild 走 V001→Vlatest 順序，V069 在最後 drop |
| `sql/migrations/V005__indexes_views.sql:176/178/180` | **migration-history** (CREATE INDEX) | V004 建表後在此建 index | NONE — DROP TABLE 在 V069 cascade drop index |
| `sql/migrations/V006__timescaledb_policies.sql:84` | **migration-history** (add_retention_policy) | TimescaleDB 90d 保留策略 | NONE — DROP TABLE 在 V069 cascade drop policy |
| `sql/migrations/V009__phase4_ml_news_tables.sql:12` | **migration-comment** | Comment 列舉前 phase 已有的表（含 scorer_predictions） | NONE — 純註解 |
| `sql/migrations/V069__*.sql:1/4/6/21/22/26/29/38/39/43/48` | **own migration** | V069 自身 | NONE |

## 3.5 Docs / TODO / governance hits（不涉 runtime）

| 路徑 | 類型 |
|---|---|
| `TODO.md:420` | `P1-WA4B-DROP-1` 條目，note V069 已 drop 無 producer wire-up target |
| `2026-05-20--strategy-architecture-redesign-recommendation.md:56` | 表格標 ⛔ V069 已 DROP |
| `docs/archive/2026-05-09--qctodo_sprint_n0_n5_archive.md`, `docs/CCAgentWorkSpace/*/workspace/reports/*` | 多份 audit/sign-off/review 報告，引用作 audit trail |
| `docs/governance_dev/amendments/2026-05-10--AMD-2026-05-10-03-invariant-5-wording-n0-scope.md` | invariant 5 wording 改寫文，引用 scorer_predictions 為 6 表 wire-up 上層消費者（屬未來計劃 wording，不是當前 writer） |
| `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md:63` | 提到 `learning.scorer_predictions`（不同 schema 名稱，**注意**：此 spec 用 `learning.scorer_predictions` 非 `observability.scorer_predictions`，是 N+4 spec 的 future schema 命名，V069 已 drop 的是 `observability.*`） |
| `docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md:50` | 早期 schema 規劃文 |
| `docs/audits/2026-04-12--full_program_chain_audit.md:4165` | 全鏈 audit 中列舉的 observability tables 圖譜 |
| `.codex/WORKLOG.md:286-287` | codex 端 V069 retrofit 記錄 |

**docs hits 全為被動引用**：audit trail / 計劃文 / amendment wording / TODO 條目，無 runtime executor 接 DB。

# §4 殘留風險評估

## 4.1 風險矩陣

| 項目 | hits | 分類 | 風險等級 |
|---|---|---|---|
| Python `INSERT/SELECT/UPDATE observability.scorer_predictions` | 0 | runtime writer/reader | NONE |
| Rust `scorer_predictions` 任意引用 | 0 | runtime writer/reader | NONE |
| Python config / list-entry（`fresh_start_reset.py`） | 1 | string (with graceful skip) | LOW（有 test 覆蓋） |
| Test code | 7 (3 個檔) | test (assert V069 邏輯 / fresh_start skip) | NONE（合法保留） |
| SQL migration history（V004/V005/V006/V009） | 7 | applied-once migration | NONE |
| docs / TODO / archive / governance / report | 30+ | passive reference | NONE（無 runtime impact） |

## 4.2 整體判定

**HIGH/LOW**：**LOW**（接近 NONE）

理由：
1. Source tree 內 **0 runtime writer / 0 runtime reader**（Python + Rust 雙語 grep 確認）。
2. 唯一非 docs 的 Python hit (`fresh_start_reset.py:136`) 是 `WIPE_TABLES` list entry，搭配 line 411-412 的 `SKIPPED missing table` graceful skip + 對應 regression test，已防回歸。
3. SQL migration history hits 都是 V069 之前的 CREATE/INDEX/RETENTION，DROP TABLE CASCADE 已自動回收 dependent objects。
4. 全部 docs/TODO/AMD/archive hits 是 audit trail 與未來 wording，不會反向引出 writer 接線。
5. V069 Guard A 三重設計（已 drop 冪等 / 非空拒絕 / dependent 拒絕 + RESTRICT）令 drop 行為自帶安全網。

## 4.3 額外提醒（不在本任務修，僅標記）

- `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md:63` 提到 `learning.scorer_predictions`（**learning schema**，非 observability schema）。這是 **N+4 未來 spec 命名**，與 V069 dropped 的 `observability.scorer_predictions` 是不同物件，但**未來 IMPL 時要明確區分 schema 命名空間**避免讓 reviewer 誤以為「resurrect V069 drop target」。當前不需處理，但建議 PA 在 v101/v102 spec finalize 時 explicit note 改名或維持。
- `docs/CCAgentWorkSpace/MIT/memory.md:32` 仍記「未接線：observability.scorer_predictions、observability.model_performance」— observability.scorer_predictions 已 drop，這條 memory log 過期。memory race 治理偏好不主動 revert 他人 agent memory，但 MIT 下次自我審計時可順手 update。本任務不動。

# §5 建議 follow-up

## 5.1 PM / operator 下一步（核心）

1. **Linux trade-core 執行 Probe 1-5**，預期全部達到「§2 預期結果」。
2. 若 5 條 probe 全綠 → **建議 close P2-AUDIT-VERIFY-3**，evidence 連到本報告。
3. 若任一 probe 異常 → PA 重啟分析（最可能：Probe 5 schema_migrations 缺 V069 success 記錄；其次 Probe 2 function body 殘留引用）。

## 5.2 Probe 執行 one-liner（給 operator 手貼，per shell-paste-safety）

```bash
ssh trade-core "psql -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='observability' AND table_name='scorer_predictions';\""
```

```bash
ssh trade-core "psql -d trading_ai -c \"SELECT routine_schema, routine_name, routine_type FROM information_schema.routines WHERE routine_definition LIKE '%scorer_predictions%';\""
```

```bash
ssh trade-core "psql -d trading_ai -c \"SELECT schemaname, viewname FROM pg_views WHERE definition LIKE '%scorer_predictions%';\""
```

```bash
ssh trade-core "psql -d trading_ai -c \"SELECT schemaname, tablename, indexname FROM pg_indexes WHERE indexname LIKE '%scorer_pred%' OR (schemaname='observability' AND tablename='scorer_predictions');\""
```

```bash
ssh trade-core "psql -d trading_ai -c \"SELECT version, description, success, applied_at FROM schema_migrations WHERE version='V069' OR description LIKE '%scorer_predictions%';\""
```

## 5.3 不在本任務修，建議追蹤

- **N+4 spec wording 衝突**（§4.3）：`learning.scorer_predictions` vs dropped `observability.scorer_predictions` 區分，建議 PA 在 W-AUDIT-8f spec finalize 階段 explicit note；非 P2 阻塞。
- **MIT memory.md:32 過期條目**（§4.3）：MIT 自審時順手 update；非本任務範圍。

## 5.4 不需處理

- `fresh_start_reset.py:136` 條目：有 graceful skip + test 覆蓋，**不要清理**（一旦清理會破壞 fresh-start 流程的「全 schema knowledge」原則 — list 條目兼作系統知識文件用途）。
- V004/V005/V006/V009 歷史 migration：applied-once，不會 re-apply，不要回去改。

# §6 不確定之處

1. 本任務 prompt 提到「6 個 ML dead schema」與 V069 SQL 實際 1 表不一致。已以 V069 SQL 為準（per MODULE_NOTE 已記 audit 修訂縮窄），但若操作員的「6 個」指的是 W-AUDIT-4 **完整原議題** 中包含 V068/V070/V071 列出但**未真 drop** 的其他 dead schema，那本任務 verify 範圍只覆蓋了「真 drop 那 1 個」，**未涵蓋「reclassified-but-not-dropped 的其他 5+ 個」**。若要 verify 那些，需另開 P2-AUDIT-VERIFY-3-EXTENDED 並 read V068/V070/V071 reclassification list 全名 + 各自 source grep。本報告**只回應「V069 drop 真實生效」範圍**。

2. Probe 2/3 用 `LIKE '%scorer_predictions%'`，可能誤命中含「scorer_predictions」字串的非 SQL 路徑（e.g. comment 內含此字的 function body）。若回 ≥1 row，需人工區分是 SQL 語句引用還是 comment 內容。

3. 未實際在 Linux trade-core 執行 probe（per 任務邊界「不 ssh trade-core」），所有 PG 端結論為**理論結論**，最終以 §5.2 probe runtime result 為準。

# Sources 路徑（絕對路徑）

- `/Users/ncyu/Projects/TradeBot/srv/sql/migrations/V069__drop_dead_observability_scorer_predictions.sql`
- `/Users/ncyu/Projects/TradeBot/srv/sql/migrations/V004__learning_features_obs_risk_tables.sql`
- `/Users/ncyu/Projects/TradeBot/srv/sql/migrations/V005__indexes_views.sql`
- `/Users/ncyu/Projects/TradeBot/srv/sql/migrations/V006__timescaledb_policies.sql`
- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/fresh_start_reset.py`
- `/Users/ncyu/Projects/TradeBot/srv/tests/migrations/test_v069_drop_dead_observability_scorer_predictions.py`
- `/Users/ncyu/Projects/TradeBot/srv/tests/helper_scripts/test_fresh_start_reset_missing_tables.py`

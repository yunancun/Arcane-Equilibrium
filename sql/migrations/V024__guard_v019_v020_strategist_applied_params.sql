-- ============================================================
-- V024: Retroactive Guard A for V019/V020
--   learning.strategist_applied_params + tie-break index
-- 追溯式 Guard A：V019/V020 的 strategist_applied_params 表 + 索引
-- ============================================================
--
-- Postmortem context (G6-03 V024 redo, 2026-04-24):
--   The first attempt at retrofitting Guard A directly into V019/V020
--   (commit ff5bf1f) succeeded locally but crashed engine startup on
--   Linux: sqlx auto_migrate detected a checksum change for V019 (its
--   row in `_sqlx_migrations` carried the pre-guard checksum) and
--   refused to start with:
--     "migration 19 was previously applied but has been modified"
--   Reverted at commit 55ed449. Per CLAUDE.md §七「新 SQL migration
--   規範」the guard is required, but **already-applied V019/V020 are
--   immutable from sqlx's perspective**. Pure-new V024 carries the
--   guard without touching V019/V020 checksums.
--
-- 事故脈絡（G6-03 V024 重做，2026-04-24）：
--   首次直接修 V019/V020 加 Guard A（commit ff5bf1f）在 Linux engine
--   起不來：sqlx auto_migrate 偵測到 V019 checksum 改變（`_sqlx_migrations`
--   存了改前的 checksum）即拒啟動，錯誤訊息：
--     "migration 19 was previously applied but has been modified"
--   2026-04-24 revert 為 55ed449。CLAUDE.md §七 規範要求加 guard，但
--   **既有已套用的 V019/V020 對 sqlx 是 immutable**。本 V024 純新增、
--   不動 V019/V020 即達成相同保護目的。
--
-- What this migration does / 本遷移做什麼：
--   Two DO blocks. Both are pure runtime checks — NO `CREATE TABLE`,
--   NO `CREATE INDEX`, NO `ALTER TABLE`. Idempotent by construction
--   (re-applying yields zero schema delta, identical RAISE behaviour).
--
--   兩個 DO block，純 runtime 檢查 — 不 CREATE TABLE / 不 CREATE INDEX
--   / 不 ALTER TABLE。設計即 idempotent（重複套用不改 schema、RAISE 行為相同）。
--
--   Block 1 (Guard A for V019 table):
--     Verify `learning.strategist_applied_params` exists with all 9
--     required columns (id, engine_mode, strategy_name, params_json,
--     applied_at, applied_at_ms, source, reason, prev_params_json).
--     RAISE if table exists but ≥1 column missing — this is the
--     "legacy stub" detection signal that V019's CREATE TABLE IF NOT
--     EXISTS would silently no-op against.
--
--   Block 2 (Guard A for V020 indexes):
--     Verify the four hot-path indexes installed by V019 + V020 are
--     present and shaped correctly:
--       (a) idx_strategist_applied_engine_strategy_ts must contain
--           the tie-break key `id DESC` (V020 patch).
--       (b) idx_strategist_applied_ts must exist (V019 audit index).
--     RAISE if either index missing or shape drifted — Strategist
--     restore-on-startup query (DISTINCT ON ... ORDER BY ...) silently
--     becomes non-deterministic without these indexes, producing the
--     same race that V020 was written to fix.
--
--   區塊 1（V019 表的 Guard A）：
--     驗 `learning.strategist_applied_params` 存在且 9 必要欄位俱在
--     （id / engine_mode / strategy_name / params_json / applied_at /
--      applied_at_ms / source / reason / prev_params_json）。表存在
--     但缺 ≥1 欄位即 RAISE — 這是 legacy stub 的偵測信號；V019 的
--     CREATE TABLE IF NOT EXISTS 在這種情況下會靜默 no-op。
--
--   區塊 2（V020 索引的 Guard A）：
--     驗 V019 + V020 安裝的四個熱路徑索引存在且形狀正確：
--       (a) idx_strategist_applied_engine_strategy_ts 必含 tie-break
--           key `id DESC`（V020 patch）。
--       (b) idx_strategist_applied_ts 必存在（V019 audit index）。
--     缺任一索引或 shape 漂移即 RAISE — Strategist 重啟時的 restore
--     query（DISTINCT ON ... ORDER BY ...）若無此索引會悄悄退化為
--     non-deterministic，引發 V020 原欲修復的 race。
--
-- Idempotency / 冪等性：
--   No DDL emitted by this file. Guards only RAISE on drift; on a
--   correct schema, both blocks fall through silently. Re-applying
--   the migration (manually `psql -f V024__*.sql` twice) is a true
--   no-op — `_sqlx_migrations.checksum` will not change.
--
--   本檔不發 DDL。Guard 僅在 drift 時 RAISE；schema 正確時兩個 block
--   靜默通過。手動重複套用（psql -f V024__*.sql ×2）為真 no-op，
--   `_sqlx_migrations.checksum` 不變。
--
-- Engine auto_migrate path / Engine 自動遷移路徑：
--   `OPENCLAW_AUTO_MIGRATE=1` 時 engine 啟動會偵測 V024（檔名 V024__
--   符合 `is_eligible_migration_file` 規則 + version 24 > LEGACY_APPLIED_MAX_VERSION
--   23），透過 `Migrator::run_direct` 視為 pending → 自動套用、寫入
--   `_sqlx_migrations` 一行新 row。手動 `bash helper_scripts/linux_bootstrap_db.sh
--   --apply` 路徑同樣會套用此檔。
--
-- Template source / 模板來源：
--   sql/migrations/templates/schema_guard_template.sql § Guard A
-- ============================================================


-- ------------------------------------------------------------
-- Block 1: Guard A for learning.strategist_applied_params (V019)
-- 區塊 1：V019 表的 Guard A
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name   = 'strategist_applied_params'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id',
            'engine_mode',
            'strategy_name',
            'params_json',
            'applied_at',
            'applied_at_ms',
            'source',
            'reason',
            'prev_params_json'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'strategist_applied_params'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V024 schema_guard A: learning.strategist_applied_params exists but missing required columns: %. '
                'A pre-V019 legacy stub or hand-applied partial table is present. '
                'Operator action: '
                '  1. psql -d trading_ai -c "\d learning.strategist_applied_params" to inspect actual shape. '
                '  2. If table is empty / safely droppable: DROP TABLE learning.strategist_applied_params CASCADE; '
                '     then re-apply V019 to recreate with the full 9-column shape. '
                '  3. If table holds data: ALTER TABLE ADD the missing columns with V019-matching types. '
                '  4. Re-run this V024 to confirm the guard passes. '
                'See sql/migrations/templates/schema_guard_template.sql § Guard A. '
                'V024 schema_guard A：learning.strategist_applied_params 存在但缺必要欄位：%。'
                'pre-V019 legacy stub 或手動套用的部分表。 '
                'Operator 動作：(1) psql 檢查實際 shape (2) 若表空可 DROP 重建 V019 '
                '(3) 若有資料則 ALTER ADD 缺失欄位（型別對齊 V019） (4) 重跑 V024 驗證。',
                v_missing,
                v_missing;
        END IF;
    ELSE
        RAISE EXCEPTION
            'V024 schema_guard A: learning.strategist_applied_params does not exist. '
            'V019 must be applied before V024. This migration is a retroactive guard '
            'for V019/V020, not a creator. '
            'Operator action: '
            '  bash helper_scripts/linux_bootstrap_db.sh --apply '
            '(or psql -f sql/migrations/V019__strategist_applied_params.sql) '
            'then re-run V024. '
            'V024 schema_guard A：learning.strategist_applied_params 不存在。'
            'V019 必須先套用，本 V024 是追溯式 guard 而非建表者。'
            'Operator 動作：先跑 linux_bootstrap_db.sh --apply 或手動 psql V019 後再跑 V024。';
    END IF;
END $$;


-- ------------------------------------------------------------
-- Block 2: Guard A for V019/V020 indexes
-- 區塊 2：V019/V020 索引的 Guard A
-- ------------------------------------------------------------
DO $$
DECLARE
    v_idx_engine_strategy_ts TEXT;
    v_idx_ts                 TEXT;
BEGIN
    -- (a) Tie-break index installed by V020 must contain `id DESC`.
    --     V020 安裝的 tie-break index 必含 `id DESC`。
    SELECT pg_get_indexdef(i.indexrelid) INTO v_idx_engine_strategy_ts
    FROM pg_index i
    JOIN pg_class c     ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'learning'
      AND c.relname = 'idx_strategist_applied_engine_strategy_ts';

    IF v_idx_engine_strategy_ts IS NULL THEN
        RAISE EXCEPTION
            'V024 schema_guard A: index learning.idx_strategist_applied_engine_strategy_ts is missing. '
            'Both V019 (initial) and V020 (tie-break patch) install this index. '
            'Strategist restart-restore query (DISTINCT ON ... ORDER BY engine_mode, strategy_name, applied_at_ms DESC, id DESC) '
            'silently degrades to a sequential scan + non-deterministic ordering without it. '
            'Operator action: '
            '  bash helper_scripts/linux_bootstrap_db.sh --apply '
            '(or manually psql V019 + V020) then re-run V024. '
            'V024 schema_guard A：缺 learning.idx_strategist_applied_engine_strategy_ts 索引。'
            'V019 + V020 都應安裝；缺索引會讓 Strategist restart-restore 查詢退化為'
            'sequential scan + non-deterministic ordering（V020 原欲修復的 race 重現）。'
            'Operator：bash helper_scripts/linux_bootstrap_db.sh --apply 後重跑 V024。';
    END IF;

    IF position('id DESC' IN v_idx_engine_strategy_ts) = 0 THEN
        RAISE EXCEPTION
            'V024 schema_guard A: index learning.idx_strategist_applied_engine_strategy_ts exists but missing `id DESC` tie-break. '
            'Actual definition: %. '
            'V020 (STRATEGIST-PERSIST-TIE-BREAK-1) requires (engine_mode, strategy_name, applied_at_ms DESC, id DESC). '
            'Without `id DESC`, concurrent writes with identical applied_at_ms are restored in '
            'PG physical-row order (page-layout dependent, non-stable). '
            'Operator action: '
            '  psql -d trading_ai -f sql/migrations/V020__strategist_applied_params_tie_break.sql '
            '(V020 uses DROP IF EXISTS + CREATE; safe to re-run) then re-run V024. '
            'V024 schema_guard A：索引 learning.idx_strategist_applied_engine_strategy_ts 存在但缺 `id DESC` tie-break。'
            '實際定義：%。V020 要求 (engine_mode, strategy_name, applied_at_ms DESC, id DESC)。'
            '無 `id DESC` → 同 ms 的並發寫入按 PG physical-row order 取最舊。'
            'Operator：psql -f V020 重套（V020 含 DROP IF EXISTS，安全）後重跑 V024。',
            v_idx_engine_strategy_ts,
            v_idx_engine_strategy_ts;
    END IF;

    -- (b) V019 audit index must exist.
    --     V019 audit index 必存在。
    SELECT pg_get_indexdef(i.indexrelid) INTO v_idx_ts
    FROM pg_index i
    JOIN pg_class c     ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'learning'
      AND c.relname = 'idx_strategist_applied_ts';

    IF v_idx_ts IS NULL THEN
        RAISE EXCEPTION
            'V024 schema_guard A: index learning.idx_strategist_applied_ts is missing. '
            'V019 installs this index for global "latest applies across all (engine_mode, strategy)" audit queries. '
            'Operator action: '
            '  bash helper_scripts/linux_bootstrap_db.sh --apply '
            '(or manually psql V019) then re-run V024. '
            'V024 schema_guard A：缺 learning.idx_strategist_applied_ts 索引。'
            'V019 安裝此索引供「全部 (engine_mode, strategy) 跨表最新 applies」audit query 使用。'
            'Operator：bash helper_scripts/linux_bootstrap_db.sh --apply 後重跑 V024。';
    END IF;

    IF position('applied_at_ms DESC' IN v_idx_ts) = 0 THEN
        RAISE EXCEPTION
            'V024 schema_guard A: index learning.idx_strategist_applied_ts exists but column shape drifted. '
            'Actual definition: %. '
            'V019 requires (applied_at_ms DESC). Drift breaks the audit query plan. '
            'Operator action: '
            '  psql -d trading_ai -c "DROP INDEX IF EXISTS learning.idx_strategist_applied_ts;" '
            '  psql -d trading_ai -f sql/migrations/V019__strategist_applied_params.sql '
            'then re-run V024. '
            'V024 schema_guard A：索引 learning.idx_strategist_applied_ts 存在但欄位 shape 漂移。'
            '實際定義：%。V019 要求 (applied_at_ms DESC)。漂移會破壞 audit query plan。'
            'Operator：DROP INDEX + 重套 V019 後重跑 V024。',
            v_idx_ts,
            v_idx_ts;
    END IF;
END $$;

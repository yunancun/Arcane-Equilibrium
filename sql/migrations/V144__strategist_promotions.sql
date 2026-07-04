-- ============================================================
-- V144: learning.strategist_promotions — demo→live 策略參數促升/回滾的
--       fail-closed audit lineage 表（INTELLIGENT-PARAM-ADJUST Phase 2）
--
-- 目的 / Motivation:
--   Phase 2 把既有 strategist_promote_routes.py 的 live promote/demote
--   從「fire-and-forget change_audit_log」升級成「commit gate 在耐久 audit
--   row 寫成功」。live param 改動而無耐久 audit row = 違 root #8（每筆交易/
--   變更必可重建）；audit_events / engine_events 歷史稀疏甚至為空（P8 風險），
--   故 promote/demote 的權威耐久證據必須有自己的專屬表。
--
--   本表存的是「稀疏促升/回滾事件」（非時序高頻 tick），因此：
--   - 非 hypertable（無 compress / retention，永久保留 audit lineage — root #8）。
--   - criteria_input_json 完整保留促升當下的 EDGE-ANCHORED 量化證據，供事後
--     QC 重審「這次促升的量化依據」（per-cell edge snapshot + coverage）。
--
--   schema 鏡像既有 learning.strategist_applied_params（V019）+ 加促升專屬欄
--   （action / source/target_engine / pre+promoted params / criteria 證據 /
--    gate_passed / reverts_promotion_id）。
--
-- 編號決策 (load-bearing — migration 號是 git 看不見的全局命名空間):
--   ssh trade-core 查 prod _sqlx_migrations max(version) = 139（2026-06-17）。
--   repo file chain 最高 = V143（V140 缺號；V141/V142/V143 file 尚未 apply 到
--   prod）。next-free = max(applied=139, file-chain=143)+1 = V144。
--   sqlx 在 apply 本 file 前會先依序補 apply V141/V142/V143（forward-only）。
--   E1-B 已 ssh trade-core 在 scratch DB 雙 apply 驗冪等（見報告）。
--
-- 範圍 / Scope (V144):
--   §A CREATE SCHEMA IF NOT EXISTS learning（schema 已由 V019 建，
--      重複 IF NOT EXISTS 安全）。
--   §B CREATE TABLE IF NOT EXISTS learning.strategist_promotions（16 欄）。
--   §C 兩條 CREATE INDEX IF NOT EXISTS（hot-path 查詢索引）。
--   §D 表 COMMENT。
--   ⚠️ 誠實更正（2026-07-04 P2-11 ①）：本檔 body 從未含 Guard A 型反射 DO-block
--   （header 原把 IF NOT EXISTS 誤稱 Guard A/Guard C）。必要 16 欄的 Guard A
--   反射由 V148__recorder_promotions_guard_retrofit 補齊；checksum 漂移由
--   bin/repair_migration_checksum 處理（不手改 _sqlx_migrations）。
--
--   ⚠️ 純 additive（新表，無改既有表）→ git revert 安全；表留存無害
--      （無 writer 時就是空表）。prod apply 走 sqlx auto-migrate at engine boot
--      或 operator-gated migrate，不手 psql 打 prod（避 checksum 漂移）。
-- ============================================================

-- ==========================================================
-- §A learning schema（V019 已建，IF NOT EXISTS 重複安全；
--    非 Guard A —— 反射型 Guard A 見 V148 retrofit）
-- ==========================================================
CREATE SCHEMA IF NOT EXISTS learning;

-- ==========================================================
-- §B learning.strategist_promotions — promote/demote 耐久 audit row
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.strategist_promotions (
    id                      BIGSERIAL PRIMARY KEY,
    action                  TEXT        NOT NULL,                   -- 'promote' / 'demote'
    strategy_name           TEXT        NOT NULL,
    symbol                  TEXT,                                   -- audit scope hint，不參與語意（鏡像既有 route 的 symbol-as-hint）
    source_engine           TEXT        NOT NULL,                   -- promote 來源：'demo' / 'paper'
    target_engine           TEXT        NOT NULL DEFAULT 'live',
    pre_promotion_params_json   JSONB   NOT NULL,                   -- 完整 live set（促升前 / demote 還原目標）
    promoted_params_json        JSONB   NOT NULL,                   -- 完整促升後寫入 live 的 set（demote precondition 比對基準）
    criteria_verdict        TEXT        NOT NULL,                   -- 'Eligible' / 'Pending:reason' / 'Reject:reason' / 'demote_exempt'
    criteria_input_json     JSONB,                                  -- 促升當下 EDGE-ANCHORED 證據快照（root #8 可重建：per-cell edge + coverage）
    actor_id                TEXT        NOT NULL,
    gate_passed             BOOLEAN     NOT NULL,                   -- 5-gate 結果
    applied_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at_ms           BIGINT      NOT NULL,                   -- client ts_ms for ordering
    reverts_promotion_id    BIGINT,                                 -- demote 指回被回滾的 promote row id（FK-soft，不建硬 FK）
    reason                  TEXT
);

-- ==========================================================
-- §C hot-path 索引（CREATE INDEX IF NOT EXISTS）
--   idx1：依 (strategy, target_engine) 取最近促升 row（demote precondition /
--         latest-promote 查詢）。
--   idx2：依 action 取最近 promote/demote 事件（auto-demote scan / GUI 時間軸）。
-- ==========================================================
CREATE INDEX IF NOT EXISTS idx_strategist_promotions_strategy_target_ts
    ON learning.strategist_promotions (strategy_name, target_engine, applied_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_strategist_promotions_action_ts
    ON learning.strategist_promotions (action, applied_at_ms DESC);

-- ==========================================================
-- §D 表 COMMENT
-- ==========================================================
COMMENT ON TABLE learning.strategist_promotions IS
    'INTELLIGENT-PARAM-ADJUST Phase 2: fail-closed audit lineage for demo->live '
    'strategist param promotion / demote. The synchronous INSERT here is the '
    'commit gate (not fire-and-forget); IPC-OK-but-INSERT-fail => route 500. '
    'Non-hypertable, permanent retention (root #8 reconstructability). '
    'criteria_input_json holds the per-cell EDGE-ANCHORED evidence at promote time.';

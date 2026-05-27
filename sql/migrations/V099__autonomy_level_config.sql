-- V099__autonomy_level_config.sql
-- Autonomy Level Toggle system-wide policy state + append-only switch audit
--
-- Spec source / 規格來源：
--   docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md（MIT v2 sync 後 568 行 SSOT）
--   docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md §3（PA spec v2 SSOT）
--   docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md §3.5
--
-- 目的 / Purpose：
--   新建 `system` schema + 2 table 持有 Autonomy Level Toggle 全系統 policy 狀態。
--   CONSERVATIVE (Level 1, default, CC stance) / STANDARD (Level 2, PM Path B)。
--   single-row config 表 + append-only switch audit 表 + PG NOTIFY channel
--   `autonomy_level_changed`（cache invalidation 主路徑，engine listener subscribe）。
--
-- Guard 範圍 / Guard scope：
--   Guard A：新建 system schema + 2 表 + ENUM type 存在性 + column 完整性（缺欄 RAISE）
--   Guard B：current_level / level_before / level_after 型別必 USER-DEFINED + udt_name=autonomy_level_enum
--   Guard C：hot-path index 對齊驗（24h cooldown 走 switched_at_utc DESC；
--             rolling 30d emergency_override 計算走 switched_at_local DESC partial index）
--
-- Idempotency / 冪等性：
--   CREATE SCHEMA / TYPE / TABLE IF NOT EXISTS + ON CONFLICT DO NOTHING + DO block
--   IF NOT EXISTS pg_type 探。Apply 二次必 NOTICE skip 不 RAISE。
--
-- sqlx hash drift 防線 / sqlx hash drift防線：
--   per memory `project_2026_05_02_p0_sqlx_hash_drift`：禁本地 psql -f；engine restart
--   with OPENCLAW_AUTO_MIGRATE=1 sqlx 第一次 apply 寫 _sqlx_migrations.checksum；後續
--   file edit 必走 bin/repair_migration_checksum。
--
-- 範本來源 / Template source：
--   sql/migrations/V098__governance_audit_log_halt_event_types.sql（Guard A + idempotency pattern）
--   sql/migrations/V112__decision_lease_lal_tiers.sql（Guard A column 完整性 + ENUM CHECK pattern）

-- ─────────────────────────────────────────────────────────────────────────────
-- Phase 1: system schema 創建（idempotent）
-- 為什麼新建 system schema 而非塞 governance：per MIT Q2 + AMD v2 §3.5
--   - system schema 為 system-wide policy state 預留 namespace
--   - governance schema 已被 V112 LAL 5-tier 占用，性質不同（per-decision audit）
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS system;

COMMENT ON SCHEMA system IS
    'System-wide policy state (Autonomy Level Toggle, per AMD-2026-05-21-01 v2 §3.5).';

-- ─────────────────────────────────────────────────────────────────────────────
-- Phase 1.5: PG ENUM type 創建（idempotent，per MIT Q1 + PA spec §3.2）
-- 為什麼用 PG ENUM 取代 smallint/text CHECK：
--   - AMD v2 §3.3 命名「Level 1 Conservative」「Level 2 Standard」是 first-class 字串
--   - Rust sqlx mapping #[sqlx(type_name = "autonomy_level_enum", rename_all = "UPPERCASE")]
--     自動處理；0 mental mapping
--   - DB-level 自動 reject invalid value，無需額外 CHECK constraint 維護
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'autonomy_level_enum' AND n.nspname = 'system'
    ) THEN
        CREATE TYPE system.autonomy_level_enum AS ENUM ('CONSERVATIVE', 'STANDARD');
        RAISE NOTICE 'V099: created ENUM system.autonomy_level_enum';
    ELSE
        RAISE NOTICE 'V099: ENUM system.autonomy_level_enum already exists, skipping';
    END IF;
END $$;

COMMENT ON TYPE system.autonomy_level_enum IS
    'Autonomy Level enum: CONSERVATIVE (Level 1, default, CC stance) / STANDARD (Level 2, PM Path B). '
    'Per MIT Q1 + AMD-2026-05-21-01 v2 §3.3 + PA spec §3.2.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Phase 2: Table 1 — system.autonomy_level_config（single-row state）
-- ─────────────────────────────────────────────────────────────────────────────

-- Guard A part 1：若表已存在，驗 7 column 完整性
-- 為什麼：legacy partial schema deploy 後 column 不齊會 silent 違反 spec；提前 RAISE
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='system' AND table_name='autonomy_level_config') THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'current_level', 'last_switched_at', 'switched_by',
            'switch_reason', 'created_at', 'updated_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='system'
              AND table_name='autonomy_level_config'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION
                'V099 Guard A: system.autonomy_level_config exists but missing columns: %. '
                'Resolve legacy schema (DROP + re-apply, or ALTER ADD missing) before V099 re-apply.',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS system.autonomy_level_config (
    -- 設計為 single-row table；row id 永遠 = 1
    -- 為什麼 CHECK(id=1)：防止 future code accidental INSERT 第二 row 破 singleton 不變量
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),

    -- 當前 Autonomy Level（PG ENUM type per MIT Q1 + AMD v2 §3.3 + PA spec §3.2）
    -- DB-level 自動 reject invalid value（'INVALID'/'LEVEL1'/typo 全拒）
    current_level system.autonomy_level_enum NOT NULL DEFAULT 'CONSERVATIVE',

    -- 最近一次切換時間（UTC）
    last_switched_at timestamptz NOT NULL DEFAULT now(),

    -- 切換者 actor identifier（對應 operator role authentication 結果；cold start = 'system_default'）
    switched_by text NOT NULL DEFAULT 'system_default',

    -- 切換理由（operator 必填自由文本；GUI handler enforce ≥30 chars per A3 spec §5.2）
    -- 注意：本 column 不在 DB 層 enforce ≥30，因 cold start 用固定字串 'cold_start_default_conservative'
    -- 才合理；operator-path 的 ≥30 字元紀律由 audit 表 CHECK constraint 強制（per §audit）
    switch_reason text NOT NULL DEFAULT 'cold_start_default_conservative',

    -- Bookkeeping
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Guard B：current_level type 必 USER-DEFINED + udt_name='autonomy_level_enum'
-- 為什麼：PG ENUM column 在 information_schema 顯示 data_type='USER-DEFINED'；若 ENUM
--   type 創建 mismatch（如 spec 漂移 lower-case），engine sqlx mapping INSERT 立即 fail
DO $$
DECLARE v_actual TEXT; v_udt_name TEXT;
BEGIN
    SELECT data_type, udt_name INTO v_actual, v_udt_name
    FROM information_schema.columns
    WHERE table_schema='system'
      AND table_name='autonomy_level_config'
      AND column_name='current_level';
    IF v_actual IS NOT NULL
       AND (v_actual <> 'USER-DEFINED' OR v_udt_name <> 'autonomy_level_enum') THEN
        RAISE EXCEPTION
            'V099 Guard B: system.autonomy_level_config.current_level data_type=% udt_name=%, expected USER-DEFINED / autonomy_level_enum',
            v_actual, v_udt_name;
    END IF;
END $$;

-- 確保只有一行（idempotent；id PRIMARY KEY 已隱含 UNIQUE，本顯式 index 為 audit 清晰性）
CREATE UNIQUE INDEX IF NOT EXISTS uniq_autonomy_level_config_singleton
    ON system.autonomy_level_config (id);

-- updated_at trigger（與既有 timestamp pattern 對齊）
CREATE OR REPLACE FUNCTION system.touch_autonomy_level_config()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_touch_autonomy_level_config
    ON system.autonomy_level_config;
CREATE TRIGGER trg_touch_autonomy_level_config
    BEFORE UPDATE ON system.autonomy_level_config
    FOR EACH ROW EXECUTE FUNCTION system.touch_autonomy_level_config();

-- Cold start seed（idempotent — 已有 row 不覆蓋）
-- 為什麼 CONSERVATIVE 為 default：per AMD v2 §3.3 + CLAUDE.md §二 原則 6 (uncertainty defaults to conservative)
INSERT INTO system.autonomy_level_config (id, current_level, switched_by, switch_reason)
VALUES (1, 'CONSERVATIVE', 'system_default', 'cold_start_default_conservative')
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE system.autonomy_level_config IS
    'Single-row Autonomy Level state (id=1 enforced via CHECK). '
    'CONSERVATIVE = Level 1 (default; CC stance) / STANDARD = Level 2 (PM Path B). '
    'Toggle handler必走 PG transaction wrap + NOTIFY autonomy_level_changed for engine cache invalidation. '
    'See PA spec §4.3 + §B4 R-2.';
COMMENT ON COLUMN system.autonomy_level_config.current_level IS
    'PG ENUM system.autonomy_level_enum: CONSERVATIVE (default; CC stance) / STANDARD (PM Path B). '
    'Per MIT Q1 + AMD v2 §3.3 + PA spec §3.2.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Phase 3: Table 2 — system.autonomy_level_switch_audit（append-only history）
-- ─────────────────────────────────────────────────────────────────────────────

-- Guard A part 2：若 audit 表已存在，驗 17 column 完整性（含 v2 sync 後雙時間戳 + escalation_result）
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='system' AND table_name='autonomy_level_switch_audit') THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'audit_id',
            'switched_at_utc', 'switched_at_local',
            'actor', 'actor_role',
            'level_before', 'level_after',
            'twofa_verify_result', 'twofa_method',
            'switch_reason', 'result',
            'emergency_override', 'emergency_override_reason',
            'notification_slack_status', 'notification_email_status', 'notification_banner_status',
            'notification_escalation_result',
            'created_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='system'
              AND table_name='autonomy_level_switch_audit'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing,1) > 0 THEN
            RAISE EXCEPTION
                'V099 Guard A: system.autonomy_level_switch_audit exists but missing columns: %. '
                'Resolve legacy schema before V099 re-apply.',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS system.autonomy_level_switch_audit (
    audit_id bigserial PRIMARY KEY,

    -- 切換時間 雙時間戳（per E2 Q4 拍板 + PA spec §3.3）
    -- switched_at_utc：UTC ms 精度（跨 timezone 統一審計；24h cooldown query 用此 column）
    -- switched_at_local：machine local timezone（per Q4「machine local time」for rolling 30d
    --   emergency override 比率計算窗口；FA U-FA-2 30% trigger 計算用此 column）
    -- 兩 timestamp 同步寫入；audit log 不擇一保留兩者
    switched_at_utc   timestamptz NOT NULL DEFAULT now(),
    switched_at_local timestamp   NOT NULL DEFAULT (now() AT TIME ZONE current_setting('TimeZone')),

    -- Actor + auth result
    actor text NOT NULL,
    actor_role text NOT NULL CHECK (actor_role IN ('operator', 'system_default')),

    -- Before / after level（per MIT Q1 改用 ENUM；DB-level auto reject invalid value）
    level_before system.autonomy_level_enum NOT NULL,
    level_after  system.autonomy_level_enum NOT NULL,

    -- before != after, unless system_default cold start（cold seed level_before=level_after=CONSERVATIVE）
    CONSTRAINT chk_level_changes_or_system_default
        CHECK (level_before <> level_after OR actor_role = 'system_default'),

    -- 2FA verification result（operator-initiated 必填；system_default seed = NULL）
    -- 為什麼允許 FAIL 寫入：audit failed attempts 紀律，不限 PASS-only
    -- per AV-11 fail-mode：backend timeout/unreachable → twofa_verify_result='FAIL', twofa_method='backend_unreachable'
    twofa_verify_result text NULL CHECK (twofa_verify_result IN ('PASS', 'FAIL') OR twofa_verify_result IS NULL),
    twofa_method        text NULL,  -- 'TOTP' / 'backend_unreachable' / NULL；禁 'hardware_key' / 禁 'remember_device_30d'（per A3 AP-5）

    -- 切換理由（operator 自由文本必填 ≥30 chars；system_default 走固定字串）
    -- 為什麼 ≥30：A3 spec §5.2 防 'fix'、'oops' 等無價值 audit 串
    switch_reason text NOT NULL CHECK (
        actor_role = 'system_default' OR char_length(switch_reason) >= 30
    ),

    -- 切換結果（per AV-10 race-lost / per B1 escalation freeze fail / etc.）
    result text NOT NULL DEFAULT 'success' CHECK (result IN (
        'success',
        'cooldown_blocked',
        'race_lost',                           -- AV-10：另一 session win 此 session lose
        'twofa_fail',                          -- 2FA verify fail
        'twofa_backend_down',                  -- AV-11 fail-closed
        'freeze_active_block',                 -- PA spec §7.4 freeze 期間禁切換
        'notification_3way_fail_escalated',    -- B1：三路全 fail 進 1h wait → SM-04 Defensive
        'emergency_override_rate_freeze',      -- FA U-FA-2：30% 比率達標 freeze 24h
        'typed_confirm_mismatch',              -- A3 U1：操作員輸入錯字串
        'system_seed'                          -- cold start
    )),

    -- 是否屬於 emergency override path（24h cooldown 內強制切換；per PA spec §4.2）
    emergency_override         boolean NOT NULL DEFAULT false,
    emergency_override_reason  text NULL,
    CONSTRAINT chk_emergency_override_has_reason
        CHECK (
            emergency_override = false
            OR (emergency_override = true AND emergency_override_reason IS NOT NULL)
        ),

    -- 三路通知 emit 結果（per AMD v2 §Decision 3.1）
    notification_slack_status   text NULL CHECK (notification_slack_status   IN ('SENT', 'FAILED', 'SKIPPED') OR notification_slack_status   IS NULL),
    notification_email_status   text NULL CHECK (notification_email_status   IN ('SENT', 'FAILED', 'SKIPPED') OR notification_email_status   IS NULL),
    notification_banner_status  text NULL CHECK (notification_banner_status  IN ('SHOWN','FAILED', 'SKIPPED') OR notification_banner_status  IS NULL),

    -- per B1 三路全 fail Escalation Ladder（PA spec §4.4 Stage 3a/3b）
    -- NULL = 未觸發 escalation
    -- 'operator_responded' = operator 1h 內介入
    -- 'auto_escalated_to_sm04_defensive' = 1h 內無 response 自動進 SM-04 Defensive + active 鎖利
    notification_escalation_result text NULL CHECK (notification_escalation_result IN (
        'operator_responded',
        'auto_escalated_to_sm04_defensive'
    ) OR notification_escalation_result IS NULL),

    -- Bookkeeping
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Append-only constraint（per AMD v2 §Decision 3.2 audit immutability）
-- trading_ai 業務 role 完全不可 UPDATE / DELETE；只有 trading_admin 透過顯式 ADR-0006
-- 數據訂正路徑可動，且訂正本身留 audit trail。
-- DO block 包住，避免 trading_ai role 不存在的 dev 環境 fail（dev sandbox empirical 已驗 role 不存在）
REVOKE UPDATE, DELETE ON system.autonomy_level_switch_audit FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON system.autonomy_level_switch_audit FROM trading_ai';
        RAISE NOTICE 'V099: REVOKE UPDATE/DELETE on system.autonomy_level_switch_audit FROM trading_ai applied';
    ELSE
        RAISE NOTICE 'V099: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: hot-path index 對齊驗（per PA spec §3.3）
--   (1) 24h cooldown query 走 switched_at_utc DESC
--   (2) emergency_override rolling 30d 計數走 switched_at_local DESC + partial WHERE
--   (3) actor_role 過濾 compound
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_autonomy_audit_switched_at_utc
    ON system.autonomy_level_switch_audit (switched_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_autonomy_audit_switched_at_local_override
    ON system.autonomy_level_switch_audit (switched_at_local DESC)
    WHERE emergency_override = true;

CREATE INDEX IF NOT EXISTS idx_autonomy_audit_actor_role
    ON system.autonomy_level_switch_audit (actor_role, switched_at_utc DESC);

-- Guard C 索引存在性驗（確認 24h cooldown 主 hot-path 索引 ordering 字面）
-- 為什麼：若 future migration 不慎 DROP 此 index 而忘了重建，24h cooldown query 退化
--   Seq Scan，audit 表年累積後爆
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='system' AND c.relname='idx_autonomy_audit_switched_at_utc';
    IF v_actual IS NOT NULL AND position('switched_at_utc DESC' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'V099 Guard C: idx_autonomy_audit_switched_at_utc missing switched_at_utc DESC ordering. Actual: %',
            v_actual;
    END IF;
END $$;

COMMENT ON TABLE system.autonomy_level_switch_audit IS
    'Append-only history of Autonomy Level toggle switches with 雙時間戳 (UTC + machine local per E2 Q4) + '
    'escalation result (per B1 三路 fail ladder per PA spec §4.4). '
    'UPDATE/DELETE revoked on PUBLIC + trading_ai; operator data correction via ADR-0006 leaves its own audit trail.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Phase 4: PG NOTIFY channel contract 紀錄（per PA spec §4.3 B4 R-2）
-- 為什麼註記於此：channel 名稱 `autonomy_level_changed` 必三處字面對齊：
--   - V099 spec §2.4
--   - PA spec §4.3
--   - engine `AutonomyLevelCache::listen_loop` Rust code（Packet C/Wave 5 cascade IMPL）
-- NOTIFY emit logic 不在 V099 migration（在 application-level toggle handler）；
-- 本 migration 僅在 COMMENT 紀錄 channel 名稱避免 future contributor 漂移。
--
-- 範例 emit pattern（在 toggle handler，非 V099 內）:
--   BEGIN;
--     UPDATE system.autonomy_level_config SET current_level=$target_level, ... WHERE id=1;
--     INSERT INTO system.autonomy_level_switch_audit (..., notification_escalation_result) VALUES (...);
--     NOTIFY autonomy_level_changed;  -- engine listener subscribe；典型 latency ≤ 200ms
--   COMMIT;
-- ─────────────────────────────────────────────────────────────────────────────

-- 完成 marker
DO $$
BEGIN
    RAISE NOTICE 'V099: Autonomy Level Toggle schema land complete (system schema + autonomy_level_enum + 2 tables + 3 indexes + trigger + cold seed)';
END $$;

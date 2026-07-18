> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）

# V099 Migration Schema Spec — Autonomy Level Toggle

**Date**: 2026-05-22
**Owner**: MIT (schema spec) → E1 (IMPL) → E4 (Linux PG empirical dry-run)
**Status**: SPEC DRAFTED — pending E1 IMPL + Linux PG dry-run before sign-off
**Source spec**: `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md` §3
**AMD governance**: `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` §3.5
**ADR refs**: ADR-0010 (Guard A/B/C) + ADR-0011 (Linux PG dry-run mandatory) + ADR-0034 (LAL gate) + ADR-0040 (venue gate)

---

## §0 摘要

新增 2 個 PG 表 + 1 個 schema (`system`) 落地 Autonomy Level Toggle system-wide policy state + append-only audit chain。設計嚴格對齊既有 V112 (LAL 5-tier) + V098 (governance_audit_log enum extend) 範式。

| 項目 | 值 |
|---|---|
| V### number | **V099** |
| 命名 | `V099__autonomy_level_config.sql` |
| Linux PG max applied | V96 (2026-05-22 ssh trade-core empirical verify) |
| Local staged unapplied | V097, V098, V106, V107, V112 (V99 free, no collision) |
| 新增 schema | `system` (per MIT Q2 拍板 + PA spec §3.1；verify Linux PG: schema 不存在；migration 內 `CREATE SCHEMA IF NOT EXISTS`) |
| 新增 ENUM | `system.autonomy_level_enum AS ENUM ('CONSERVATIVE', 'STANDARD')` (per MIT Q1 拍板 + PA spec §3.2；replaces 原 spec smallint 1/2 + text CHECK 設計) |
| 新增表 | `system.autonomy_level_config` (single-row state with `current_level autonomy_level_enum`) + `system.autonomy_level_switch_audit` (append-only history with 雙時間戳 + escalation result) |
| 新增 NOTIFY channel | `NOTIFY autonomy_level_changed` (per PA spec §4.3 B4 R-2 cache invalidation 主路徑；toggle handler COMMIT 後 emit；引擎 PG listener subscribe；典型 latency ≤ 200ms；配 polling 5s fallback) |
| Guard 範圍 | Guard A (schema + ENUM + table 存在性驗) + Guard B (column type 驗 — current_level 必 autonomy_level_enum) + Guard C (cooldown + emergency_override + actor_role index 驗) |
| Idempotency | apply 二次安全（CREATE SCHEMA / TYPE / TABLE IF NOT EXISTS + ON CONFLICT DO NOTHING + DO block NOTICE skip + ENUM DO block IF NOT EXISTS pg_type） |
| Linux PG dry-run | **MUST per ADR-0011**（per feedback_v_migration_pg_dry_run）— 13 條必驗（per PA spec §3.4，含 ENUM 自動 reject + 雙時間戳一致性 + advisory lock race + 2FA fail-closed + escalation + PG NOTIFY） |
| Rollback | 設計時無 destructive 路徑；rollback 必走 ADR-0006 數據訂正紀律（DROP TABLE + 重新 apply）— 詳 §4 |

---

## §1 V### 決策推導

### 1.1 號碼選擇邏輯

```
Linux PG _sqlx_migrations max(version) = 96
Local sql/migrations/ staged 號碼:
  ..., 95, 96, 97, 98, 106, 107, 112
  (V99-V105 free; V108-V111 free; V113+ free)
```

**選 V099 理由**：
1. **連續未占用** — 跟 V96 直接相連，不跳號（avoid 「跳號殘留」audit 困擾）
2. **不撞 staged** — V97/V98/V106/V107/V112 已 staged，V99 clean
3. **與 cascade patch 隊列協調** — AMD v2 §9.5 列 V112 為 LAL schema patch；本 V099 與之獨立、無 dependency

### 1.2 P0 sqlx hash drift 防線（per memory `project_2026_05_02_p0_sqlx_hash_drift.md`）

**Pre-deploy SOP**:
1. V099 file 寫好後，**先 commit 到 git** (不 force apply 任何手動 psql -f)
2. Engine restart with `OPENCLAW_AUTO_MIGRATE=1` 觸發 sqlx 自動 apply
3. sqlx 第一次 apply 寫 `_sqlx_migrations.checksum`；後續任何 file edit 必經 `bin/repair_migration_checksum`
4. **禁止**：本地 `psql -U trading_admin -d trading_ai -f V099__...sql` 跑 production DB（因為 sqlx not registered 會導致下次 engine restart 觸發 hash drift）

---

## §2 Schema 完整 SQL（spec 草案；E1 IMPL 細節可微調）

### 2.1 Header + Schema 創建

```sql
-- V099__autonomy_level_config.sql
-- Autonomy Level Toggle system-wide policy state + append-only switch audit
-- 
-- Spec source: docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md §3
-- AMD governance: AMD-2026-05-21-01 v2 §Decision 1.5 + §3.5
-- MIT schema spec: docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md
--
-- Guard A: 新建 system schema + 2 表存在性 + column 完整性驗
-- Guard B: current_level / level_before / level_after smallint 型別驗
-- Guard C: hot-path index 對齊驗（24h cooldown query 走 last_switched_at DESC）
-- Idempotency: apply 二次安全（CREATE IF NOT EXISTS + ON CONFLICT DO NOTHING + DO NOTICE skip）

-- ─────────────────────────────────────────────────────────────────────────────
-- Phase 1: schema creation (idempotent)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS system;

COMMENT ON SCHEMA system IS
    'System-wide policy state (Autonomy Level Toggle, per AMD-2026-05-21-01 v2 §3.5).';

-- ─────────────────────────────────────────────────────────────────────────────
-- Phase 1.5: PG ENUM type creation (idempotent — per MIT Q1 + PA spec §3.2)
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'autonomy_level_enum' AND n.nspname = 'system'
    ) THEN
        CREATE TYPE system.autonomy_level_enum AS ENUM ('CONSERVATIVE', 'STANDARD');
    END IF;
END $$;

COMMENT ON TYPE system.autonomy_level_enum IS
    'Autonomy Level enum: CONSERVATIVE (Level 1, default, CC stance) / STANDARD (Level 2, PM Path B). '
    'Per MIT Q1 + AMD-2026-05-21-01 v2 §3.3 + PA spec §3.2.';
```

### 2.2 表 1：`system.autonomy_level_config`（single-row state）

```sql
-- Guard A part 1: 若表已存在，驗 column 完整性
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
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),

    -- 當前 Autonomy Level（per MIT Q1 PG ENUM 取代原 smallint/text CHECK 設計）
    -- ENUM 值對齊 AMD v2 §3.3 + PA spec §3.2 命名：CONSERVATIVE = Level 1 / STANDARD = Level 2
    -- DB-level 自動 reject invalid value（無需額外 CHECK constraint）
    current_level system.autonomy_level_enum NOT NULL DEFAULT 'CONSERVATIVE',

    -- 最近一次切換時間（UTC）
    last_switched_at timestamptz NOT NULL DEFAULT now(),

    -- 切換者（actor identifier；對應 operator role authentication 結果）
    switched_by text NOT NULL DEFAULT 'system_default',

    -- 切換理由（operator 必填；自由文本，audit 用途；min 30 chars enforced by GUI handler per A3 spec §5.2）
    switch_reason text NOT NULL DEFAULT 'cold_start_default_conservative',

    -- Bookkeeping
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Guard B: current_level type 驗（per MIT Q1 ENUM type，非 text）
-- ENUM column data_type 在 information_schema 顯示 'USER-DEFINED'，udt_name 為 'autonomy_level_enum'
DO $$
DECLARE v_actual TEXT; v_udt_name TEXT;
BEGIN
    SELECT data_type, udt_name INTO v_actual, v_udt_name
    FROM information_schema.columns
    WHERE table_schema='system'
      AND table_name='autonomy_level_config'
      AND column_name='current_level';
    IF v_actual IS NOT NULL AND (v_actual <> 'USER-DEFINED' OR v_udt_name <> 'autonomy_level_enum') THEN
        RAISE EXCEPTION
            'V099 Guard B: system.autonomy_level_config.current_level data_type=% udt_name=%, expected USER-DEFINED / autonomy_level_enum',
            v_actual, v_udt_name;
    END IF;
END $$;

-- 確保只有一行（idempotent）
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
INSERT INTO system.autonomy_level_config (id, current_level, switched_by, switch_reason)
VALUES (1, 'CONSERVATIVE', 'system_default', 'cold_start_default_conservative')
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE system.autonomy_level_config IS
    'Single-row Autonomy Level state (id=1 enforced). CONSERVATIVE = Level 1 (default) / STANDARD = Level 2. '
    'Toggle handler必走 PG transaction wrap + NOTIFY autonomy_level_changed channel for engine cache invalidation. '
    'See PA spec §4.3 + §B4 R-2.';
COMMENT ON COLUMN system.autonomy_level_config.current_level IS
    'PG ENUM type system.autonomy_level_enum: CONSERVATIVE (default; CC stance) / STANDARD (PM Path B). '
    'Per MIT Q1 + AMD v2 §3.3 + PA spec §3.2; replaces 原 spec smallint/text CHECK 設計.';
```

### 2.3 表 2：`system.autonomy_level_switch_audit`（append-only history）

```sql
-- Guard A part 2: 若 audit 表已存在，驗 column 完整性（含 v2 sync 後雙時間戳 + escalation_result）
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='system' AND table_name='autonomy_level_switch_audit') THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'audit_id',
            'switched_at_utc', 'switched_at_local',   -- per E2 Q4 雙時間戳
            'actor', 'actor_role',
            'level_before', 'level_after',
            'twofa_verify_result', 'twofa_method',
            'switch_reason', 'result',
            'emergency_override', 'emergency_override_reason',
            'notification_slack_status', 'notification_email_status', 'notification_banner_status',
            'notification_escalation_result',   -- per B1 escalation ladder
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
    -- switched_at_utc：UTC ms 精度（跨 timezone 統一審計）
    -- switched_at_local：machine local timezone（per Q4「machine local time」for rolling 30d 計數窗口計算）
    -- 兩 timestamp 同步寫入；audit log 不擇一保留兩者（per V099 spec §0 雙寫一致紀律）
    switched_at_utc timestamptz NOT NULL DEFAULT now(),
    switched_at_local timestamp NOT NULL DEFAULT (now() AT TIME ZONE current_setting('TimeZone')),

    -- Actor + auth result
    actor text NOT NULL,
    actor_role text NOT NULL CHECK (actor_role IN ('operator', 'system_default')),

    -- Before / after level（per MIT Q1 改用 ENUM；Guard against silent corruption；DB-level auto reject invalid value）
    level_before system.autonomy_level_enum NOT NULL,
    level_after  system.autonomy_level_enum NOT NULL,

    -- before != after, unless system_default cold start
    CONSTRAINT chk_level_changes_or_system_default
        CHECK (level_before <> level_after OR actor_role = 'system_default'),

    -- 2FA verification result（operator-initiated 必填；system_default seed = NULL）
    -- 注意：FAIL 也要記錄（audit failed attempts），不限 PASS-only
    -- per AV-11 fail-mode：backend timeout/unreachable → twofa_verify_result='FAIL', twofa_method='backend_unreachable'（fail-closed）
    twofa_verify_result text NULL CHECK (twofa_verify_result IN ('PASS', 'FAIL') OR twofa_verify_result IS NULL),
    twofa_method        text NULL,  -- 'TOTP' / 'backend_unreachable' / NULL；禁 'hardware_key' / 禁 'remember_device_30d'（per A3 anti-pattern AP-5）

    -- 切換理由（operator 自由文本必填 ≥ 30 chars enforced by GUI handler per A3 spec §5.2；system_default 走固定字串）
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
        'notification_3way_fail_escalated',    -- B1：三路全 fail 進 1h wait → SM-04 Defensive escalation
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
-- trading_ai 業務 role 完全不可 UPDATE / DELETE；只有 trading_admin (operator) 透過顯式
-- ADR-0006 數據訂正路徑可動，且訂正本身留 audit trail。
REVOKE UPDATE, DELETE ON system.autonomy_level_switch_audit FROM PUBLIC;
-- DO block 包住，避免 trading_ai role 不存在的 dev 環境 fail
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON system.autonomy_level_switch_audit FROM trading_ai';
    END IF;
END $$;

-- Guard C: hot-path index（per PA spec §3.3）
-- (1) 24h cooldown query 走 switched_at_utc DESC
-- (2) emergency_override rolling 30d 計數走 switched_at_local DESC + partial WHERE emergency_override=true
-- (3) actor_role 過濾
CREATE INDEX IF NOT EXISTS idx_autonomy_audit_switched_at_utc
    ON system.autonomy_level_switch_audit (switched_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_autonomy_audit_switched_at_local_override
    ON system.autonomy_level_switch_audit (switched_at_local DESC)
    WHERE emergency_override = true;

CREATE INDEX IF NOT EXISTS idx_autonomy_audit_actor_role
    ON system.autonomy_level_switch_audit (actor_role, switched_at_utc DESC);

-- Guard C 索引存在性驗
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
    'UPDATE/DELETE revoked on auto path; operator data correction via ADR-0006 leaves its own audit trail.';
```

### 2.4 PG LISTEN/NOTIFY 通道設計（per PA spec §4.3 B4 R-2 cache invalidation 主路徑）

引擎內部 `Arc<AtomicU8>` cache autonomy_level；lease emit 時 `lal_level` 字段 snapshot 必從該 atomic 讀（非 DB query — 防 hot path PG round-trip）。Toggle handler PG transaction COMMIT 後必 atomic store 新值，並透過 PG `NOTIFY autonomy_level_changed` channel 通知引擎 listener task 觸發 cache reload。

**3 選項評估（per PA spec §4.3 B4 R-2）**：
- (a) Polling reload 60s：簡單但 lag 高（worst case 60s 後 lease 仍用舊 Level）→ **單獨採用 = ❌**
- (b) PG LISTEN/NOTIFY：toggle handler commit 後 emit `NOTIFY autonomy_level_changed`；引擎 listener task SUBSCRIBE 收到後 atomic store；典型 latency ≤ 200ms → **主路徑 ✅**
- (c) Engine 重啟讀：要求每次切換重啟引擎；UX 摩擦 + lease 中斷 → **單獨採用 = ❌**

**PA 拍板（B4 R-2）**：**(b) PG LISTEN/NOTIFY 主路徑 + (a) polling 5s fallback**（不用 60s — 5s 容錯保證即使 NOTIFY 漏觸發 cache 5s 內必收斂）。**禁** (c) engine 重啟。

V099 migration 不創建 NOTIFY emit logic（NOTIFY 在 application-level toggle handler 內 emit，per PA spec §5.2 [6](d) `BEGIN; UPDATE config; INSERT audit; NOTIFY autonomy_level_changed; COMMIT;` 單 transaction wrap）。本 spec 僅在 `system.autonomy_level_config` COMMENT ON TABLE 註記 NOTIFY channel 名稱以避免 future contributor 漂移；channel 名稱 = `autonomy_level_changed`（hard-coded const）。

```sql
-- NOTIFY 範例（emit 在 application toggle handler，非 V099 migration 內；列此為 contract 紀錄）
-- BEGIN;
--   UPDATE system.autonomy_level_config SET current_level=$target_level, ... WHERE id=1;
--   INSERT INTO system.autonomy_level_switch_audit (
--       switched_at_utc, switched_at_local, actor, actor_role,
--       level_before, level_after, twofa_verify_result, twofa_method,
--       switch_reason, result, emergency_override, emergency_override_reason,
--       notification_slack_status, notification_email_status, notification_banner_status,
--       notification_escalation_result
--   ) VALUES (...);
--   NOTIFY autonomy_level_changed;  -- 引擎 PG listener subscribe；典型 latency ≤ 200ms
-- COMMIT;
--
-- 任一 statement FAIL → 全 ROLLBACK（per AV-9 atomic）
-- 引擎 fallback：tokio::time::sleep(Duration::from_secs(5)) 後 polling reload_from_db（防 NOTIFY 漏觸發）
```

---

## §3 Linux PG empirical dry-run plan（per ADR-0011 + feedback_v_migration_pg_dry_run）

### 3.1 必驗 13 條（per PA spec §3.4；最高風險 = #5 ENUM + #6 REVOKE + #11 escalation + #12 NOTIFY + #13 雙時間戳）

| # | 必驗項 | 為何重要 | ssh trade-core 一行指令（per feedback_shell_paste_safety 抗貼上 one-liner） |
|---|---|---|---|
| **D1** | Linux PG `_sqlx_migrations` 版本對齊 | 確認 V96 baseline；確認 V099 尚未 apply（避免 hash drift incident，per project_2026_05_02_p0_sqlx_hash_drift） | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c 'SELECT version FROM _sqlx_migrations WHERE version IN (96, 99) ORDER BY version;'"` |
| **D2** | 第一次 apply（schema + ENUM + table 真寫入 + reflection 驗 column type / nullability / default） | 驗 Guard A 不誤觸 RAISE；驗 ENUM type + column 設計與 spec 字面一致；驗 default value & nullability | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -f /tmp/V099__autonomy_level_config.sql && psql -U trading_admin -d trading_ai -c 'SELECT column_name, data_type, udt_name, is_nullable, column_default FROM information_schema.columns WHERE table_schema=\\\"system\\\" AND table_name IN (\\\"autonomy_level_config\\\", \\\"autonomy_level_switch_audit\\\") ORDER BY table_name, ordinal_position;'"` |
| **D3** | 二次 apply idempotency（必 NOTICE skip 不 RAISE） | 驗 CREATE SCHEMA/TYPE/TABLE IF NOT EXISTS + ON CONFLICT DO NOTHING + Guard A 雙跑安全；防止「第一次成功第二次炸」破 idempotency；ENUM 重 apply 必透過 DO block IF NOT EXISTS pg_type | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -f /tmp/V099__autonomy_level_config.sql"` (must 0 RAISE) |
| **D4** | INSERT default → SELECT 反讀對齊（Cold start seed = CONSERVATIVE） | 驗 cold start default 真寫進 row id=1 + current_level='CONSERVATIVE'；驗 system_default actor + reason 字串對齊 | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c 'SELECT id, current_level, switched_by, switch_reason FROM system.autonomy_level_config WHERE id=1;'"` |
| **D5** | **PG ENUM constraint 強制驗（最高風險）** — INSERT 'INVALID' enum 必 reject | 驗 PG ENUM type 自動 reject invalid value；CONSERVATIVE/STANDARD 以外字串必拒（PG error: invalid input value for enum autonomy_level_enum）；'LEVEL1' / 'CONSERVATIVE  '（trailing space）都應 reject | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c \"BEGIN; UPDATE system.autonomy_level_config SET current_level='INVALID' WHERE id=1; ROLLBACK;\" 2>&1 \| grep -i 'invalid input value for enum'"` (must catch violation) |
| **D6** | **REVOKE UPDATE/DELETE 強制驗（最高風險）** — trading_ai role 無 UPDATE/DELETE 權 + Index 命中（EXPLAIN ANALYZE） | (a) 驗 append-only 真不被繞 — trading_ai SET ROLE 嘗試 UPDATE/DELETE audit 必拒 (b) 驗 idx_autonomy_audit_switched_at_utc 對 24h cooldown query 真被 PG planner 採用 | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c \"SET ROLE trading_ai; BEGIN; DELETE FROM system.autonomy_level_switch_audit WHERE audit_id=1; ROLLBACK; RESET ROLE;\" 2>&1 \| grep -i 'permission denied'"` + `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c 'EXPLAIN ANALYZE SELECT switched_at_utc FROM system.autonomy_level_switch_audit ORDER BY switched_at_utc DESC LIMIT 1;'"` (must show Index Scan on idx_autonomy_audit_switched_at_utc) |
| **D7** | Audit insert with twofa_verify_result='FAIL' 必成功（記錄 fail 嘗試） | 驗 FAIL 也要記錄（audit failed attempts），不限 PASS-only；twofa_method='backend_unreachable' fail-closed 可接受 | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c \"BEGIN; INSERT INTO system.autonomy_level_switch_audit (actor, actor_role, level_before, level_after, twofa_verify_result, twofa_method, switch_reason, result, emergency_override) VALUES ('test_operator', 'operator', 'CONSERVATIVE', 'STANDARD', 'FAIL', 'backend_unreachable', 'test fail-mode audit row record minimum 30 char reason', 'twofa_backend_down', false); ROLLBACK;\""` (must succeed) |
| **D8** | switch_reason char_length < 30 必拒（per A3 spec ≥30 字元） | 驗 CHECK constraint actor_role 'operator' 時 char_length(switch_reason) ≥ 30 enforce | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c \"BEGIN; INSERT INTO system.autonomy_level_switch_audit (actor, actor_role, level_before, level_after, twofa_verify_result, twofa_method, switch_reason, emergency_override) VALUES ('test_operator', 'operator', 'CONSERVATIVE', 'STANDARD', 'PASS', 'TOTP', 'short reason', false); ROLLBACK;\" 2>&1 \| grep -i 'violates check constraint'"` (must catch violation) |
| **D9** | **AV-9 atomic** — 模擬 INSERT audit 失敗（如違反 CHECK）後 UPDATE config 必 ROLLBACK | 驗 PG transaction wrap 對 UPDATE config + INSERT audit + NOTIFY 三步驟原子性保證；任一 FAIL 全 ROLLBACK | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c \"BEGIN; UPDATE system.autonomy_level_config SET current_level='STANDARD' WHERE id=1; INSERT INTO system.autonomy_level_switch_audit (actor, actor_role, level_before, level_after, switch_reason) VALUES ('test', 'operator', 'CONSERVATIVE', 'STANDARD', 'short'); COMMIT;\" 2>&1; psql -U trading_admin -d trading_ai -c 'SELECT current_level FROM system.autonomy_level_config WHERE id=1;'"` (must still show 'CONSERVATIVE' after rollback) |
| **D10** | **AV-10 race** — 兩 session 同時走 toggle handler，PG advisory lock win 1 lose 1 | 驗 `pg_try_advisory_xact_lock` 真 serialize toggle handler；audit 兩 row（win = success / lose = race_lost） | （需 2 parallel session 模擬；E4 regression 用 pytest async 或 2 psql session 跑 timing test）|
| **D11** | **B1 escalation** — notification_status 三路全 FAILED 必 trigger `notification_escalation_result` 寫入 | 驗 1h timeout 後 `notification_escalation_result='auto_escalated_to_sm04_defensive'` 可寫入；operator_responded 路徑也驗 | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c \"BEGIN; INSERT INTO system.autonomy_level_switch_audit (actor, actor_role, level_before, level_after, twofa_verify_result, twofa_method, switch_reason, result, notification_slack_status, notification_email_status, notification_banner_status, notification_escalation_result, emergency_override) VALUES ('test_operator', 'operator', 'CONSERVATIVE', 'STANDARD', 'PASS', 'TOTP', 'three way notification all failed test minimum reason', 'notification_3way_fail_escalated', 'FAILED', 'FAILED', 'FAILED', 'auto_escalated_to_sm04_defensive', false); ROLLBACK;\""` (must succeed) |
| **D12** | **B4 PG NOTIFY** — toggle commit 後 `LISTEN autonomy_level_changed` channel 必收 notification | 驗 PG NOTIFY/LISTEN 真 wire；mock subscriber 驗 ≤ 200ms latency；引擎 listener task SUBSCRIBE 收到後 atomic store | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c 'LISTEN autonomy_level_changed; NOTIFY autonomy_level_changed; SELECT 1;'"` (must show Asynchronous notification received) |
| **D13** | **雙時間戳一致性** — `switched_at_utc` 與 `switched_at_local AT TIME ZONE 'UTC'` 必差 < 1s | 驗 Q4 雙時間戳設計；machine local timezone setting 對齊 + 兩 timestamp 同 row 寫入時刻一致；防 timezone setting 飄移導致 rolling 30d 計算錯誤 | `ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c 'SELECT switched_at_utc, switched_at_local, switched_at_local AT TIME ZONE current_setting(\\\"TimeZone\\\"), EXTRACT(EPOCH FROM (switched_at_utc - (switched_at_local AT TIME ZONE current_setting(\\\"TimeZone\\\")))) AS diff_seconds FROM system.autonomy_level_switch_audit LIMIT 1;'"` (diff_seconds must be < 1) |

### 3.2 D5 + D6 + D11 + D12 + D13 為什麼 highest risk

**D5 PG ENUM**：若 ENUM type 創建 mismatch（如 spec 寫 `('CONSERVATIVE', 'STANDARD')` 但 DO block 跑 lower-case），engine Rust 端 sqlx mapping `#[sqlx(type_name = "autonomy_level_enum", rename_all = "UPPERCASE")]` INSERT 立即 fail；engine startup 死路。**必 Linux PG empirical reflection 驗字面對齊**（Mac mock pytest 無 PG runtime semantic 無法 catch）；PG ENUM 比 text CHECK 自動 reject invalid value 但 ENUM type 一旦創建 ALTER TYPE ADD VALUE 不可 rollback，apply 紀律更嚴。

**D6 REVOKE**：若 REVOKE 路徑 dev 環境跳過（如 trading_ai role 不存在 silently skipped）→ production 部署時 grant 未實際生效 → append-only 不變量被破。**且 EXPLAIN ANALYZE 確認 Index Scan 而非 Seq Scan**——否則 24h cooldown query 每次 full table scan，audit 表年累積後爆。

**D11 escalation**：若 `notification_escalation_result` CHECK enum 寫錯（如 missing `'auto_escalated_to_sm04_defensive'`），B1 1h timeout 後 INSERT 立即 reject → escalation ladder Stage 3b 無法寫 audit → operator 看不到自動進入 SM-04 Defensive 的紀錄。

**D12 PG NOTIFY**：若 channel 名稱 typo（e.g. `autonomy_level_change` vs `autonomy_level_changed`），引擎 listener task SUBSCRIBE 永遠收不到 → cache 永遠用舊 Level 直到 polling 5s fallback 觸發 → 違反 ≤ 200ms latency SLA。**channel 名稱 hard-coded 紀律對齊**：V099 spec §2.4 + PA spec §4.3 + engine `AutonomyLevelCache::listen_loop` 三處字面必一致。

**D13 雙時間戳**：若 `current_setting('TimeZone')` 在 PG container 設成 'UTC' 而 machine local 是 'Asia/Taipei'，`switched_at_local` 會與 `switched_at_utc` 差 8 hr → rolling 30d 計數窗口 query 用 `switched_at_local` 會錯邊界 → 月初規避紀律失敗 → emergency override rate 計算偏差 30% 比率達標 trigger 漏觸發。**必 Linux PG empirical 驗 timezone setting + 雙 timestamp 同步寫**。

### 3.3 Pre-deploy SOP 對 sqlx hash drift

按 §1.2，**禁止本地 psql -f**；改用：
1. V099 file commit + push
2. Linux engine restart `OPENCLAW_AUTO_MIGRATE=1` 觸發 sqlx 第一次 apply（也是 D2-D6 驗 baseline）
3. 任何後續修改必走 `bin/repair_migration_checksum`（per project_2026_05_02_p0_sqlx_hash_drift）

---

## §4 Rollback strategy

### 4.1 設計原則

本 V099 為 **additive schema migration**（純 CREATE，無 ALTER 既有 row / DROP COLUMN / 改 type）；理論 rollback = `DROP SCHEMA system CASCADE` 即可清乾淨；但實踐紀律：

| 場景 | Rollback path |
|---|---|
| Apply 後立即發現 schema bug（before any production row written beyond cold seed） | `DROP TABLE system.autonomy_level_switch_audit; DROP TABLE system.autonomy_level_config; DROP SCHEMA system CASCADE;` + 從 `_sqlx_migrations` 刪 V99 row + 重 land 修好 V099 |
| Apply 後有 operator 切換 row 進 audit（real production data） | **不 rollback** — 走 ADR-0006 數據訂正紀律 + 補新 V### migration patch（如 V100__autonomy_level_audit_column_extend.sql 加缺 column） |
| 5-gate live / mainnet 期間（Bybit live order 上線後）| **永不 destructive rollback** — 走 V### forward patch + 補資料訂正 audit |

### 4.2 對齊紀律

per CLAUDE.md §四 + ADR-0006，production 期間 schema rollback 風險高於 forward-patch。本 V099 設計保守的 additive 風格降低需要 rollback 機率。

---

## §5 ML pipeline / data drift implication

### 5.1 Autonomy Level 切換是否觸發 ML re-training reset？

**結論**：**否**（per `ml-pipeline-maturity-audit` skill 評級框架）。

理由：
1. **Autonomy Level 是 governance posture，非 feature distribution change** — 不會改變 OHLCV / funding / volatility 等 ML feature 統計分布
2. **不改 cost_gate / Wilson CI / 30d rolling 紀律** — per spec §1.4 + AMD v2 §Decision 2.5，Level toggle 不可繞 fail-safe 5 條 hard requirements
3. **不改 attribution_chain_ok denominator / sample weight** — V084 + V086 + W6 ML pipeline 不關心 system policy level
4. **不改 engine_mode IN ('live', 'live_demo') filter** — Training filter 不變

**例外場景需重新評估**：若 Level 2 切換後 **strategy promotion rate 顯著上升 → auto_eligible LAL 3 lease 數量 +10×** → ML training set distribution 可能 shift（更多 immature strategy 樣本進 training set）→ **`data-drift-detection` skill 適用**：建議 M3 health monitor 對 Level 切換後 30d window 用 PSI 監控 feature distribution + label distribution drift。

### 5.2 M3 health monitor 看 Level switch 紀錄？

**Yes**（推薦），per `data-drift-detection` skill §3.3 警報門檻：

- **新增 healthcheck** `check_autonomy_level_switch_recent_24h()`（per CLAUDE.md §七「TODO 必附 healthcheck」）：
  - **Query**: `SELECT switched_at, level_before, level_after, emergency_override FROM system.autonomy_level_switch_audit ORDER BY switched_at DESC LIMIT 1;`
  - **Alert criteria**: 
    - 24h 內 ≥ 2 次切換 → CRITICAL（防快速切換 attack 24h cooldown 被 emergency override 連續突破）
    - emergency_override = true → WARNING（提醒 PM monthly review SLA）
- **Healthcheck 接 M3 health domain**：Level switch 不算 health degradation（per AMD v2 §Decision 2.4 freeze trigger 不含 level switch），但 anomalous 切換頻率屬可觀察 governance metric

---

## §6 Resolved schema 設計（operator 2026-05-22 拍板）

### ~~Q1~~ ✅ RESOLVED — PG ENUM type（per MIT Q1 拍板）

**Operator 2026-05-22 拍板（MIT Q1）**：**升級為 PG ENUM type** `system.autonomy_level_enum AS ENUM ('CONSERVATIVE', 'STANDARD')`（取代原 spec smallint 1/2 或 text CHECK 過渡設計）。

**設計理由**：
- (a) AMD v2 §3.3 命名「Level 1 Conservative」「Level 2 Standard」是 first-class 字串 enum
- (b) Rust 端 enum mapping 用 `text` 比 `smallint` 字面對齊 source-of-truth，0 ambiguity；sqlx `#[sqlx(type_name = "autonomy_level_enum", rename_all = "UPPERCASE")]` 自動處理
- (c) `data-drift-detection` healthcheck query 可直接 `WHERE level_after = 'STANDARD'`，無 mental mapping
- (d) PG ENUM 自動 reject invalid value（DB-level CHECK constraint 自動），無需額外 CHECK constraint 維護
- (e) PG `enum` 與 `text + CHECK` 性能近似（single-row config table；audit 表 lifetime < 1000 row）；但 ENUM 比 text CHECK 提供更強的 schema-level 信號

**Resolution patch land**：本 spec §2.2 current_level 型別 + §2.3 audit table level_before/after 型別 + §3.1 D5 dry-run + §7 cross-checklist。

### ~~Q2~~ ✅ RESOLVED — `system` schema（per MIT Q2 拍板）

**Operator 2026-05-22 拍板（MIT Q2）**：**新建 `system` schema**（不塞既有 `governance` schema）。

**設計理由**：
- (a) `system.autonomy_level_*` 是 system-wide policy state，性質不同於 `learning.governance_audit_log` (V035) / `governance.lease_lal_tiers` (V112) 的 per-decision audit
- (b) `governance` schema 已被 V112 LAL 5-tier 占用，混入 system-wide policy 概念 dilute namespace 純度
- (c) `system` schema 新建為未來 system-wide config 預留空間（e.g. `system.maintenance_window`）

**Resolution patch land**：本 spec §2.1 `CREATE SCHEMA IF NOT EXISTS system` + 所有表/ENUM `system.` schema prefix。

### Q3 (new) — PG NOTIFY channel 命名規範

**MIT 提議**：channel 名稱 = `autonomy_level_changed`（hard-coded const）。

**設計理由**：
- (a) `_changed` past-tense 對齊 PG NOTIFY/LISTEN 範式（event 已發生通知 subscriber）
- (b) `autonomy_level_*` prefix 避免與其他 future channel 命名衝突
- (c) channel 名稱必 hard-coded 三處字面對齊：V099 spec §2.4 + PA spec §4.3 + engine `AutonomyLevelCache::listen_loop` Rust code（per D12 dry-run 風險紀錄）

✅ **RESOLVED**：採 `autonomy_level_changed`（per PA spec §4.3 + §3.2 COMMENT ON TABLE 紀錄）。

### Q4 (new) — 雙時間戳設計（per E2 Q4 拍板）

**Operator 2026-05-22 拍板（E2 Q4）**：emergency override 月度計數窗口 = **Rolling 30 天 + Machine local time**（per FA U-FA-2 30% 比率達標 trigger）。

**Resolution patch land**：本 spec §2.3 audit table 新增 `switched_at_utc` + `switched_at_local` 雙 column；§3.1 D13 dry-run 驗一致性；§2.3 idx_autonomy_audit_switched_at_local_override partial index 對 `WHERE emergency_override = true` query 加速。

✅ **RESOLVED**：雙時間戳設計 land。

---

## §7 Cross-checklist 對齊（per ADR-0010 / MIT skill set）

| Checklist 項 | 狀態 |
|---|---|
| ADR-0010 Guard A retrofit | ✅ §2.1 schema + §2.2 + §2.3 (CREATE SCHEMA + TYPE + TABLE IF NOT EXISTS + column missing array verify) |
| ADR-0010 Guard B retrofit | ✅ §2.2 (current_level type='USER-DEFINED' + udt_name='autonomy_level_enum' verify per MIT Q1 PG ENUM) |
| ADR-0010 Guard C retrofit | ✅ §2.3 (idx_autonomy_audit_switched_at_utc + idx_autonomy_audit_switched_at_local_override partial + idx_autonomy_audit_actor_role column ordering verify) |
| Idempotency 雙跑 | ✅ §3.1 D3（CREATE SCHEMA / TYPE / TABLE IF NOT EXISTS + ON CONFLICT DO NOTHING + DO NOTICE skip + DO block ENUM IF NOT EXISTS pg_type） |
| Linux PG empirical dry-run | ✅ §3.1 13 條（per feedback_v_migration_pg_dry_run + PA spec §3.4；MUST before E1 IMPL sign-off） |
| Append-only constraint | ✅ §2.3 (REVOKE UPDATE/DELETE on PUBLIC + trading_ai) |
| 雙時間戳（per E2 Q4 + PA spec §3.3）| ✅ §2.3 (switched_at_utc + switched_at_local 雙 column + idx_autonomy_audit_switched_at_local_override partial index for emergency_override rolling 30d 計算) |
| Escalation result（per B1 + PA spec §4.4）| ✅ §2.3 (notification_escalation_result CHECK enum: 'operator_responded' / 'auto_escalated_to_sm04_defensive') |
| PG NOTIFY channel（per PA spec §4.3 B4 R-2）| ✅ §2.4 (channel = `autonomy_level_changed`；hard-coded 對齊 V099 spec + PA spec + engine listener task 三處字面) |
| Engine mode filter (per `db-schema-design-financial-time-series` skill §5) | **N/A** — Level table 是 system-wide governance state，不分 engine_mode (paper/demo/live_demo/live) |
| Hypertable / chunk / compression | **N/A** — single-row config + small audit (lifetime < 1000 row)；hypertable over-engineering |
| Healthcheck 新增 | ✅ §5.2 推薦 `check_autonomy_level_switch_recent_24h()` + PA spec §13 M3 health monitor 24h ≥ 2 switch CRITICAL |
| Cold start fail-closed (per CLAUDE.md §二 原則 6) | ✅ §2.2 INSERT default CONSERVATIVE + engine read fail → Level 1 (per PA spec §5.3) |

---

## §8 Sign-off

| Role | 任務 | Status |
|---|---|---|
| **MIT (本 spec)** | V099 number 拍板 + schema spec 草案 + 13 條 Linux PG dry-run 必驗 + Rollback strategy + ML drift implication + Q1/Q2 PG ENUM + system schema 拍板 + 雙時間戳 + escalation_result + NOTIFY channel sync (v2 patch) | ✅ DRAFTED + v2 SYNCED |
| **PA** | PA spec v2 §3 schema 設計（SSOT）+ 13 條 dry-run + AV-9/10/11 + B1/B4/Q4 補入；與 cascade patch 隊列協調 V99 不撞其他 patch | ✅ PA spec v2 LAND；MIT spec v2 SYNCED |
| **TW** | AMD v2 wording 10 條 sync + V099 spec dual write（ENUM + NOTIFY trigger + 雙時間戳 + escalation_result）對齊 PA spec v2 SSOT | ✅ SYNCED（本次完成） |
| **E1** | V099 SQL IMPL（per §2 草案 + v2 sync 後 ENUM + 雙時間戳 + escalation_result + NOTIFY channel）+ commit + push（**禁本地 psql -f**） | 🟡 PENDING |
| **E4 / Operator** | Linux PG empirical dry-run × 13 條（per §3 v2 patch）+ engine restart auto-migrate + healthcheck 對齊驗 | 🟡 PENDING (MUST before sign-off) |
| **E2** | Code review V099 SQL + Guard A/B/C 完整性 + idempotency 雙跑 + grep `runtime_failsafe_override` / `disable_failsafe` patterns 零出現 + AV-9/10/11 atomic/race/fail-closed regression | 🟡 PENDING |
| **CC** | 16 root principles walkthrough（原則 6 fail-closed / 原則 9 audit traceability / 原則 11 portfolio risk）對 V099 對齊 | 🟡 PENDING |
| **A3** | GUI Governance tab Autonomy Posture sub-section UI flow（per PA spec §5.2 7-step）對 V099 schema 字段引用 + 8 anti-pattern AP-1..AP-8 | 🟡 PENDING |
| **FA** | §Decision 2 5 條 fail-safe hard req 在 Level 1+2 雙 level 對齊驗 + U-FA-1 Level 2 toggle disabled until evidence baseline + U-FA-2 emergency override 30% 混合 action 對 V099 audit schema 引用 | 🟡 PENDING |

---

*MIT DB Schema Spec — V099 Autonomy Level Config — 對齊 ADR-0010 Guard A/B/C + ADR-0011 Linux PG dry-run mandatory + AMD-2026-05-21-01 v2 §3.5 + PA design spec 2026-05-22 §3*

*v2 sync 2026-05-22（TW）：PG ENUM type 升級（MIT Q1）+ `system` schema 確認（MIT Q2）+ 雙時間戳 switched_at_utc / switched_at_local（E2 Q4）+ notification_escalation_result（B1）+ NOTIFY autonomy_level_changed channel §2.4（B4 R-2）+ 13 條 dry-run 必驗 + Sign-off table 加 PA/TW/A3/FA + Q1-Q4 全部 RESOLVED*

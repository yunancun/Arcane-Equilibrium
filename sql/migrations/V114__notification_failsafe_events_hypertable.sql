-- ============================================================
-- V114: Notification Failsafe Events Hypertable
-- 用途: Wave 5 Packet C C2 — observability.notification_failsafe_events
--       自動 escalation audit append-only hypertable。
--
--   - SOURCE：PA C spec §5 + operator Q5 拍板 hybrid PC.B
--     · Q5.1: 表名 = observability.notification_failsafe_events
--     · Q5.2: 編號 = V114 (V113 為當前最高)
--     · Q5.3: acked_at_utc UPDATE 路徑 = trading_admin role grant
--
-- 範圍:
--   - CREATE TABLE IF NOT EXISTS observability.notification_failsafe_events
--     (17 column: id BIGSERIAL + ts_ms BIGINT + event_type + transition 5 column
--      + adjustments 3 column + atr_buffer_multiplier + now_ms + acked 2 column
--      + payload_jsonb + created_at)
--   - create_hypertable(ts_ms, chunk_time_interval => 604800000) — 7d in ms;
--     BIGINT partition column 用 ms cast (per V026 pattern)。
--   - INDEX (event_type, ts_ms DESC) — query pattern: 按 event_type filter +
--     time DESC (operator GUI banner / audit 排序)。
--   - INDEX 第二條 partial: WHERE acked_at_utc IS NULL — unacked row 快速 GUI poll。
--   - GRANT 對 trading_admin: SELECT/INSERT (全表) + UPDATE (限 acked_at_utc/acked_by);
--     PUBLIC REVOKE UPDATE/DELETE (append-only enforcement)。
--     注意: GRANT 必在 add_compression_policy 之前 (FIX MIT-2026-05-28 dry-run blocker)
--     — enable compression 後 column-level GRANT UPDATE 會傳播到 compressed twin
--     (_compressed_hypertable_NN) 而 twin 無 acked_at_utc column → apply abort。
--   - add_compression_policy(30 days) — 在 GRANT 之後執行。
--   - Guard A: schema 必存 + V113 baseline 已 land (V113 為 V114 前置 sqlx chain).
--   - Guard B: chunk_time_interval BIGINT ms 對齊 (重 apply drift 防護).
--   - Guard C: 17 column 完整性 + CHECK enum + hypertable + GRANT row。
--
-- Parent specs:
--   docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §5
--   docs/decisions/AMD-2026-05-21-01_layered_autonomy_v2.md §Decision 2.5 + 3.1
--   srv/rust/openclaw_engine/src/notification_failsafe/mod.rs (FailsafeAuditEmitter trait)
--
-- Pattern source:
--   V109 (M8 anomaly_events hypertable + Guard A/B/C) — 主 reference
--   V026 (cost_edge_advisor BIGINT ts_ms chunk_time_interval => 86400000) — BIGINT ts_ms pattern
--   V113 (governance_audit_log enum DROP+ADD ACCESS EXCLUSIVE) — append-only pattern
--
-- 硬邊界:
--   - append-only: PUBLIC REVOKE UPDATE/DELETE; UPDATE 限 trading_admin role + 限 acked_* 2 column
--   - ts_ms BIGINT 不變: 對齊 `FailsafeWatcher` mod.rs FailsafeClock::now_ms() u64
--     output 直接 INSERT; 不引入 timestamptz 轉換以保 audit_emitter Rust 端 cast 最小化
--   - event_type CHECK 預留擴展: 當前只 'auto_escalated_to_sm04_defensive' 一值,
--     後續 wave 加 ALTER 擴 CHECK enum (per V053/V098/V113 DROP+ADD 範式)
--   - 不重用 system.autonomy_level_switch_audit (V099) / learning.governance_audit_log (V035) —
--     PA spec §5.1 明確此為自動 escalation 路徑 (actor=system 非 operator) +
--     含 exchange sync_records JSONB payload 不適合既有表 schema
-- ============================================================

-- ============================================================
-- Guard A: observability schema 存在 + V113 baseline 已 land 反向防護
-- 為什麼分兩層: schema 是 V001 land (P0 schema), V113 是 V114 前置 sqlx chain;
--   兩者皆缺 = 環境異常須 RAISE EXCEPTION
-- ============================================================
DO $$
DECLARE
    v_schema_exists BOOLEAN;
    v_v113_event_present BOOLEAN := FALSE;
    v_check_def TEXT;
BEGIN
    -- observability schema 必存 (V001 P0 schema)
    SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'observability'
    ) INTO v_schema_exists;
    IF NOT v_schema_exists THEN
        RAISE EXCEPTION
            'V114 Guard A FAIL: observability schema missing. V001 must apply first.';
    END IF;

    -- V113 已 land 反向防護 (sqlx chain 不可跳號)
    -- 探 pg_dump_completed event_type 是否在 governance_audit_log_event_type_check (V113 引入)
    SELECT pg_get_constraintdef(c.oid)
    INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'learning'
      AND t.relname = 'governance_audit_log'
      AND c.contype = 'c'
      AND c.conname = 'governance_audit_log_event_type_check';
    IF v_check_def IS NOT NULL AND position('pg_dump_completed' IN v_check_def) > 0 THEN
        v_v113_event_present := TRUE;
    END IF;
    IF NOT v_v113_event_present THEN
        RAISE EXCEPTION
            'V114 Guard A FAIL: V113 baseline missing (pg_dump_completed not in '
            'governance_audit_log CHECK enum). V113 must apply before V114.';
    END IF;

    -- TimescaleDB extension 必存 (V096 boundary;hypertable 必須)
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
    ) THEN
        RAISE EXCEPTION
            'V114 Guard A FAIL: TimescaleDB extension missing. V096 boundary not satisfied.';
    END IF;
END $$;

-- ============================================================
-- Guard B: 既有 table 情境 — chunk_time_interval drift 防護
-- 為什麼: idempotent 重跑時若 chunk 設定漂移 (如 7d → 30d 被手動 ALTER)
--   立即 fail-loud,避免 silent skip 後 row 進錯 chunk。
-- ============================================================
DO $$
DECLARE
    v_chunk_interval BIGINT;
    v_target_oid OID;
BEGIN
    v_target_oid := to_regclass('observability.notification_failsafe_events');
    IF v_target_oid IS NULL THEN
        RAISE NOTICE
            'V114 Guard B pre: observability.notification_failsafe_events not yet created; '
            'skipping pre-check.';
        RETURN;
    END IF;

    -- BIGINT partition: chunk interval 以 BIGINT ms 表示 (per V026 pattern)
    SELECT integer_interval INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_schema='observability'
      AND hypertable_name='notification_failsafe_events'
      AND column_name='ts_ms';
    -- 7d in ms = 604_800_000
    IF v_chunk_interval IS NOT NULL AND v_chunk_interval <> 604800000 THEN
        RAISE EXCEPTION
            'V114 Guard B FAIL: chunk_time_interval = % (expected 604800000 = 7d in ms).',
            v_chunk_interval;
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 1: CREATE TABLE
-- 17 column 對齊 Rust audit_emitter payload (mod.rs FailsafeExecutionReport)
-- ============================================================
CREATE TABLE IF NOT EXISTS observability.notification_failsafe_events (
    -- BIGSERIAL PK; hypertable PK 必含 partition column (ts_ms)
    id                          BIGSERIAL,
    -- partition column: ms epoch (對齊 FailsafeClock::now_ms() u64 直 INSERT)
    -- 為什麼用 BIGINT 不是 timestamptz: audit_emitter Rust 端持 now_ms: u64,
    --   不引入 chrono 轉換最小化 Rust binding 複雜度;對齊 V026 pattern
    ts_ms                       BIGINT NOT NULL,
    -- event_type: 當前只 1 值 (預留 ALTER 擴展);per V053/V098/V113 DROP+ADD 範式
    event_type                  TEXT NOT NULL
                                CHECK (event_type IN (
                                    'auto_escalated_to_sm04_defensive'
                                )),
    -- trigger: 通常 = 'notification_failsafe_timeout' (RiskEvent.as_str())
    trigger                     TEXT,
    -- initiator: 通常 = 'RiskGovernor' (RiskInitiator)
    initiator                   TEXT,
    -- from/to risk level (NORMAL/CAUTIOUS/REDUCED/DEFENSIVE/CIRCUITBREAKER/MANUALREVIEW)
    from_level                  TEXT,
    to_level                    TEXT,
    -- transition 是否成功;失敗時 transition_skipped_reason 含原因
    transition_succeeded        BOOLEAN,
    transition_skipped_reason   TEXT,
    -- active_lock_profit adjustment 數 + per-symbol exchange sync 結果 array
    adjustments_count           INTEGER,
    -- sync_records JSONB: per-symbol StopSyncRecord[]
    --   [{"symbol":"BTCUSDT","side":"Buy","new_sl":102.0,"success":true,"error":null}, ...]
    sync_records                JSONB,
    -- atr_buffer_multiplier: 鎖利公式 ATR 乘數 (default 0.5 per FailsafeConfig)
    atr_buffer_multiplier       DOUBLE PRECISION,
    -- now_ms: escalate 執行時刻 (== ts_ms; 冗餘存留 audit reconstruction 便利性)
    now_ms                      BIGINT,
    -- acked_*: operator GUI ack 後 UPDATE 填;NULL = 未 ack
    -- 為什麼 acked_at_utc 用 TIMESTAMPTZ 不是 BIGINT: ack 是 control_api GUI write 路徑,
    --   server-side NOW() PG default 較直觀;與 ts_ms BIGINT (engine write) 分工
    acked_at_utc                TIMESTAMPTZ,
    acked_by                    TEXT,
    -- payload_jsonb: 完整 audit payload 原樣存 (FailsafeAuditEmitter::emit_auto_escalated 入參)
    --   即使 column 拆出,完整 payload 留作 forward-compat 與 audit reconstruction
    payload_jsonb               JSONB,
    -- bookkeeping
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, ts_ms)
);

-- ============================================================
-- Main DDL Step 2: Hypertable (7d chunk; BIGINT ms partition)
-- ============================================================
SELECT create_hypertable(
    'observability.notification_failsafe_events',
    'ts_ms',
    chunk_time_interval => 604800000,  -- 7 days in ms (per V026 BIGINT pattern)
    if_not_exists => TRUE
);

-- ============================================================
-- Main DDL Step 3: Indexes
-- (event_type, ts_ms DESC) — query pattern: per-type timeline
-- partial (acked_at_utc IS NULL) — GUI poll 未 ack 行
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_notification_failsafe_event_type_ts
    ON observability.notification_failsafe_events (event_type, ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_notification_failsafe_unacked
    ON observability.notification_failsafe_events (ts_ms DESC)
    WHERE acked_at_utc IS NULL;

-- ============================================================
-- Main DDL Step 4: GRANT (trading_admin) + REVOKE PUBLIC
-- 為什麼 trading_admin: control_api GUI ack 路徑透過 trading_admin role UPDATE
--   acked_at_utc/acked_by;對齊 operator Q5.3 拍板。
-- 為什麼 column-level UPDATE GRANT: append-only 語義保留 — 其他 column 永遠 immutable
-- 為什麼此 Step 必在 enable compression 之前 (FIX MIT-2026-05-28 dry-run blocker):
--   TimescaleDB enable compression 後會建一 compressed twin hypertable
--   (_compressed_hypertable_NN),其 column 為壓縮格式 (compressed segment) 而非原表
--   column;column-level `GRANT UPDATE (acked_at_utc, acked_by)` 會被 TimescaleDB
--   傳播到該 twin → twin 無 acked_at_utc column → `ERROR: column "acked_at_utc"
--   of relation "_compressed_hypertable_NN" does not exist` → apply abort。
--   table-level GRANT SELECT,INSERT 不查 column 存在性故不受影響;只有 column-level
--   GRANT 觸發此 bug。將整段 GRANT/REVOKE 移到 compression enable 之前,
--   twin 尚未存在時 column-level grant 合法。
-- 為什麼 reorder 仍不夠 + nested EXCEPTION (FIX MIT-2026-05-29 idempotency blocker):
--   reorder 只解 first-run。compressed twin 一旦由 first-run 的 compression enable
--   建立即跨 migration run 持久存在;re-apply 場景 (engine restart sqlx migrate /
--   雙跑 idempotency) 時 twin 已存在 → column-level GRANT 又被傳播 → 同 abort。
--   故 column-level GRANT UPDATE 必包 nested BEGIN/EXCEPTION 吞 undefined_column:
--   first-run 已落 pg_attribute.attacl,re-apply 無需再執行,skip 不破冪等。
-- ============================================================
DO $$
BEGIN
    -- trading_admin role 必存 (V001/V003 P0;若缺 RAISE NOTICE skip GRANT 由 DBA 後補)
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'trading_admin'
    ) THEN
        RAISE NOTICE
            'V114: trading_admin role missing; skipping GRANT statements. '
            'DBA must add GRANT manually after creating role.';
        RETURN;
    END IF;

    -- SELECT/INSERT 全表 (table-level grant 不查 column 存在性,天然冪等且不傳播到 compressed twin)
    EXECUTE 'GRANT SELECT, INSERT ON observability.notification_failsafe_events TO trading_admin';

    -- UPDATE 限 acked_at_utc + acked_by 2 column (append-only enforcement)
    -- 為什麼包 nested BEGIN/EXCEPTION (FIX MIT-2026-05-29 idempotency blocker, 2nd-run-only):
    --   GRANT-before-compression 的 reorder 只解 first-run;但 compression enable 建的
    --   compressed twin (_compressed_hypertable_NN) 跨 migration run 持久存在。
    --   re-apply (engine restart sqlx migrate / 雙跑 idempotency) 時 twin 已存在 →
    --   TimescaleDB 把 column-level GRANT 傳播到 twin → twin 只有壓縮格式 column 無
    --   acked_at_utc → `ERROR: column "acked_at_utc" of relation
    --   "_compressed_hypertable_NN" does not exist` (SQLSTATE 42703 undefined_column) → abort。
    --   first-run 已把 grant 落 pg_attribute.attacl (acked_at_utc/acked_by = w),
    --   re-apply 不需再執行;故 swallow undefined_column 即可保冪等,不破 first-run 正確性。
    BEGIN
        EXECUTE 'GRANT UPDATE (acked_at_utc, acked_by) ON observability.notification_failsafe_events TO trading_admin';
    EXCEPTION
        WHEN undefined_column THEN
            -- compressed twin 已存在 (re-apply 場景);grant 已在 first-run 落 attacl,重跑無需再執行
            RAISE NOTICE
                'V114: column-level GRANT UPDATE skipped — compressed twin exists on '
                're-apply (grant already in pg_attribute.attacl from first-run; idempotent)';
    END;

    -- BIGSERIAL sequence 也需 GRANT (INSERT 用)
    EXECUTE 'GRANT USAGE ON SEQUENCE observability.notification_failsafe_events_id_seq TO trading_admin';
    RAISE NOTICE 'V114: granted SELECT/INSERT (full) + UPDATE (acked_* only) to trading_admin';

    -- REVOKE PUBLIC UPDATE/DELETE (append-only enforcement)
    EXECUTE 'REVOKE UPDATE, DELETE ON observability.notification_failsafe_events FROM PUBLIC';
END $$;

-- ============================================================
-- Main DDL Step 5: Compression policy (30d)
-- 對齊 V109 30d compression cadence; fail-safe event 罕見,30d 內保 hot read
-- 注意: 本 Step 必在 Step 4 GRANT 之後 — enable compression 建 compressed twin
--   後,column-level GRANT 會傳播失敗 (見 Step 4 FIX 註解)。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema = 'observability'
          AND hypertable_name = 'notification_failsafe_events'
    ) THEN
        ALTER TABLE observability.notification_failsafe_events SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'event_type',
            timescaledb.compress_orderby = 'ts_ms DESC, id DESC'
        );
        RAISE NOTICE
            'V114: enabled compression on observability.notification_failsafe_events '
            '(segmentby=event_type; orderby=ts_ms DESC)';
    ELSE
        RAISE NOTICE
            'V114: compression already enabled; skipping ALTER';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_compression'
          AND hypertable_name = 'notification_failsafe_events'
    ) THEN
        PERFORM add_compression_policy(
            'observability.notification_failsafe_events',
            BIGINT '2592000000'  -- 30 days in ms
        );
        RAISE NOTICE
            'V114: added compression policy (30 days) on notification_failsafe_events';
    ELSE
        RAISE NOTICE
            'V114: compression policy already present; skipping';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 6: COMMENT
-- ============================================================
COMMENT ON TABLE observability.notification_failsafe_events IS
    'Wave 5 Packet C C2 — 3-way notification fail-safe escalation audit '
    'append-only hypertable (V114). ts_ms BIGINT partition (對齊 Rust '
    'FailsafeClock::now_ms()). 7d chunk + 30d compression. '
    'UPDATE 限 trading_admin role + acked_at_utc/acked_by 2 column; '
    'PUBLIC 不可 UPDATE/DELETE (append-only enforcement)。';

COMMENT ON COLUMN observability.notification_failsafe_events.ts_ms IS
    'ms epoch partition column;對齊 Rust FailsafeClock::now_ms() u64 直 INSERT '
    '(不引 timestamptz 轉換以保 Rust binding 簡單)。';

COMMENT ON COLUMN observability.notification_failsafe_events.event_type IS
    '當前 1 值 auto_escalated_to_sm04_defensive;後續 wave 用 ALTER DROP+ADD '
    '擴展 (per V053/V098/V113 ACCESS EXCLUSIVE pattern)。';

COMMENT ON COLUMN observability.notification_failsafe_events.acked_at_utc IS
    'operator GUI ack 時刻;NULL = 未 ack。UPDATE 路徑限 trading_admin role '
    '(per operator Q5.3 拍板;control_api ack endpoint 走此 role)。';

COMMENT ON COLUMN observability.notification_failsafe_events.payload_jsonb IS
    '完整 FailsafeAuditEmitter::emit_auto_escalated payload 原樣存;'
    'forward-compat 與 audit reconstruction 用 (即使 column 拆出仍保完整 row)。';

-- ============================================================
-- Guard C 後驗: 17 column + hypertable + CHECK + GRANT row 全到位
-- ============================================================
DO $$
DECLARE
    v_column_count INTEGER;
    v_chunk_interval BIGINT;
    v_check_def TEXT;
    v_index_count INTEGER;
    v_role_exists BOOLEAN;
    v_grant_exists BOOLEAN;
BEGIN
    -- 17 column 完整性
    SELECT COUNT(*) INTO v_column_count
    FROM information_schema.columns
    WHERE table_schema='observability' AND table_name='notification_failsafe_events';
    IF v_column_count <> 17 THEN
        RAISE EXCEPTION
            'V114 Guard C post FAIL: column count = % (expected 17). Schema drift detected.',
            v_column_count;
    END IF;

    -- event_type CHECK 必含 auto_escalated_to_sm04_defensive
    SELECT pg_get_constraintdef(oid) INTO v_check_def
    FROM pg_constraint
    WHERE conrelid='observability.notification_failsafe_events'::regclass
      AND conname LIKE '%event_type%check%'
    LIMIT 1;
    IF v_check_def IS NULL THEN
        RAISE EXCEPTION
            'V114 Guard C post FAIL: event_type CHECK constraint not found.';
    END IF;
    IF position('auto_escalated_to_sm04_defensive' IN v_check_def) = 0 THEN
        RAISE EXCEPTION
            'V114 Guard C post FAIL: event_type CHECK missing required value. Actual: %.',
            v_check_def;
    END IF;

    -- hypertable chunk = 7d in ms
    SELECT integer_interval INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_schema='observability'
      AND hypertable_name='notification_failsafe_events'
      AND column_name='ts_ms';
    IF v_chunk_interval IS NULL THEN
        RAISE EXCEPTION
            'V114 Guard C post FAIL: hypertable not created on ts_ms.';
    END IF;
    IF v_chunk_interval <> 604800000 THEN
        RAISE EXCEPTION
            'V114 Guard C post FAIL: chunk_time_interval = % (expected 604800000).',
            v_chunk_interval;
    END IF;

    -- 2 index 到位
    SELECT COUNT(*) INTO v_index_count
    FROM pg_indexes
    WHERE schemaname='observability'
      AND tablename='notification_failsafe_events'
      AND indexname IN (
          'idx_notification_failsafe_event_type_ts',
          'idx_notification_failsafe_unacked'
      );
    IF v_index_count <> 2 THEN
        RAISE EXCEPTION
            'V114 Guard C post FAIL: 2 hot-path index expected, found %.',
            v_index_count;
    END IF;

    -- GRANT 驗 (trading_admin exists 才驗)
    SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_admin')
      INTO v_role_exists;
    IF v_role_exists THEN
        SELECT EXISTS (
            SELECT 1 FROM information_schema.role_table_grants
            WHERE table_schema = 'observability'
              AND table_name = 'notification_failsafe_events'
              AND grantee = 'trading_admin'
              AND privilege_type = 'INSERT'
        ) INTO v_grant_exists;
        IF NOT v_grant_exists THEN
            RAISE EXCEPTION
                'V114 Guard C post FAIL: trading_admin INSERT grant missing.';
        END IF;
    END IF;

    RAISE NOTICE
        'V114: all guards PASS — 17 column, event_type CHECK 1 value, '
        'hypertable chunk=7d in ms (604800000), 2 index, '
        'trading_admin GRANT (if role exists)。';
END $$;

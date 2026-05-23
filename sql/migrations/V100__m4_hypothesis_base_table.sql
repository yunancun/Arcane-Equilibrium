-- ============================================================
-- V100: M4 Hypothesis Discovery Base Tables
--
-- 用途:
--   建立 M4 hypothesis discovery 模塊的 3 個 base table:
--     1. learning.hypotheses (registry; 13 column + 11 status enum +
--        4 engine_mode enum) — regular table 非 hypertable (~100 row/yr)
--     2. learning.hypothesis_preregistration (append-only signed ledger;
--        7 column + FK to hypotheses)
--     3. learning.earn_movement_log (Bybit Earn stake/redeem audit;
--        10 column + FK to learning.governance_audit_log)
--   本 V100 是 Sprint 1B late §4.1.1 P0 入口 — 解 V103 EXTEND Guard A
--   FAIL (Sprint 4+ Phase 3c production AUTO_MIGRATE=1 V103 attempt)。
--   V100 land 後 sqlx chain 變 V099 (autonomy) → V100 (M4 base) → V103
--   (EXTEND M4 6 column);V103 Guard A 自然 PASS。
--
-- 範圍:
--   - CREATE TABLE IF NOT EXISTS 3 表 (learning.hypotheses 13 column /
--     hypothesis_preregistration 7 column / earn_movement_log 10 column)
--   - Guard A: 3 table 已存在情境下驗 base column 完整性 +
--     learning.governance_audit_log prereq (earn_movement_log FK target)
--   - Guard C: status CHECK 11 值 + engine_mode CHECK 4 值 +
--     direction CHECK 2 值 + reconciliation_status CHECK 3 值 對齊
--   - 4 hot-path index (idx_hypotheses_strategy_status /
--     idx_hypotheses_pre_reg_ts / idx_preregistration_hypothesis_signed /
--     idx_earn_movement_log_strategy_ts)
--   - 4 FK constraint (preregistration → hypotheses;
--     earn_movement_log.governance_approval_id → learning.governance_audit_log)
--   - COMMENT ON TABLE / COLUMN 中文註釋每 column
--
-- Parent specs:
--   docs/execution_plan/specs/2026-05-23--v100-m4-hypothesis-base-table.md
--   docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md §2.1-§2.3
--   docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_late_v100_m4_hypothesis_base_table_design.md
--   docs/adr/0010-database-migration-guards.md (Guard A/B/C)
--   docs/adr/0011-database-migration-linux-pg-empirical-dry-run.md
--   docs/adr/0045-m4-hypothesis-discovery-governance.md
--
-- 硬邊界:
--   - earn_movement_log.governance_approval_id FK target =
--     learning.governance_audit_log(id) — 不是 governance.audit_log(id)
--     (per V103 base spec §2.3.1 schema 名 typo; production 真實表名
--     見 V035/V053/V098 baseline; PA-DRIFT-1 patch lesson 對齊 V106/V107/V112)
--   - learning.hypotheses 是 regular table 非 hypertable (低基數 ~100 row/yr
--     per v103_v104 §2.1.4); 不加 TimescaleDB extension dependency
--   - engine_mode CHECK 4 值齊全 (paper/demo/live_demo/live);
--     ML training filter 必 IN ('live','live_demo') per CLAUDE.md §七
--   - status CHECK 11 值對齊 ADR-0026 v3 canary stage + Sprint 2 promotion
--     (draft/preregistered/shadow/stage_0r/stage_1/stage_2/stage_3/stage_4/
--      live/retired/killed)
--   - V100 base land 後 V103 EXTEND 自然 PASS (V103 Guard A 驗 base table
--     + hypothesis_id PK 存在);本 V100 不混 V103 EXTEND 6 column scope
--   - amount_usdt NUMERIC(18,8) 高精度 (Bybit Earn stable coin satoshi-scale);
--     不用 REAL 避免精度誤差
-- ============================================================

-- ============================================================
-- Guard A: 3 NEW table column 完整性 + learning.governance_audit_log prereq
-- Guard A: 3 表 column 完整性與 V098 base 前置驗證
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    -- learning.hypotheses 已存在情境下驗 13 base column 完整性
    -- (V019 / Sprint 1A-α stub 路徑可能已 land 半成品)
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='hypotheses'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'hypothesis_id', 'strategy_name', 'pre_reg_ts', 'pre_reg_hash',
            'status', 'expected_sharpe', 'expected_dd', 'capacity_estimate_usdt',
            't_stat_min', 'min_sample_size', 'engine_mode',
            'created_at', 'updated_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='hypotheses'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V100 Guard A FAIL: learning.hypotheses exists but missing base columns: %. '
                'Possible legacy stub conflict — resolve schema reconciliation before V100. '
                'Reference v103_v104 base spec §2.1.1 for canonical 13-column shape.',
                v_missing;
        END IF;
    END IF;

    -- learning.hypothesis_preregistration 已存在情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='hypothesis_preregistration'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'preregistration_id', 'hypothesis_id', 'payload_json',
            'payload_hash', 'operator_signature', 'signed_at', 'engine_mode'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='hypothesis_preregistration'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V100 Guard A FAIL: learning.hypothesis_preregistration exists but missing columns: %. '
                'Possible legacy stub conflict — resolve schema reconciliation before V100.',
                v_missing;
        END IF;
    END IF;

    -- learning.earn_movement_log 已存在情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='earn_movement_log'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'movement_id', 'event_ts', 'direction', 'amount_usdt',
            'apr_at_time', 'governance_approval_id', 'bybit_response_payload',
            'engine_mode', 'api_scope_used', 'reconciliation_status'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='earn_movement_log'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V100 Guard A FAIL: learning.earn_movement_log exists but missing columns: %. '
                'Resolve schema drift before V100.',
                v_missing;
        END IF;
    END IF;

    -- learning.governance_audit_log 必須存在 (earn_movement_log FK target;
    -- V035 baseline + V053/V098 extension; 對齊 V106/V107/V112 PA-DRIFT-1 patch:
    -- spec doc 寫 governance.audit_log 但 production 真實表名為
    -- learning.governance_audit_log)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='governance_audit_log'
    ) THEN
        RAISE EXCEPTION
            'V100 Guard A FAIL: learning.governance_audit_log missing — '
            'V035/V053/V098 baseline must apply before V100 (earn_movement_log.governance_approval_id FK target). '
            'Verify _sqlx_migrations.';
    END IF;
END $$;

-- ============================================================
-- Guard C 預檢: idempotency 重跑時驗 CHECK enum 對齊
-- (首次 apply 上述 object 不存在 → 全 skip; 重跑時抓 drift)
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_target_oid OID;
BEGIN
    -- learning.hypotheses 用 to_regclass() 安全測;首次 apply 為 NULL skip
    v_target_oid := to_regclass('learning.hypotheses');
    IF v_target_oid IS NOT NULL THEN
        -- hypotheses.status CHECK 11 值齊全
        SELECT pg_get_constraintdef(oid) INTO v_actual
        FROM pg_constraint
        WHERE conrelid=v_target_oid
          AND conname LIKE '%status%check%'
        LIMIT 1;
        IF v_actual IS NOT NULL THEN
            IF position('draft' IN v_actual) = 0
               OR position('preregistered' IN v_actual) = 0
               OR position('shadow' IN v_actual) = 0
               OR position('stage_0r' IN v_actual) = 0
               OR position('stage_1' IN v_actual) = 0
               OR position('stage_2' IN v_actual) = 0
               OR position('stage_3' IN v_actual) = 0
               OR position('stage_4' IN v_actual) = 0
               OR position('live' IN v_actual) = 0
               OR position('retired' IN v_actual) = 0
               OR position('killed' IN v_actual) = 0
            THEN
                RAISE EXCEPTION
                    'V100 Guard C FAIL: learning.hypotheses status CHECK enum mismatch. '
                    'Actual: %. Expected 11 values (draft/preregistered/shadow/stage_0r/'
                    'stage_1/stage_2/stage_3/stage_4/live/retired/killed) per ADR-0026 v3 + Sprint 2 promotion.',
                    v_actual;
            END IF;
        END IF;

        -- hypotheses.engine_mode CHECK 4 值齊全
        SELECT pg_get_constraintdef(oid) INTO v_actual
        FROM pg_constraint
        WHERE conrelid=v_target_oid
          AND conname LIKE '%engine_mode%check%'
        LIMIT 1;
        IF v_actual IS NOT NULL THEN
            IF position('paper' IN v_actual) = 0
               OR position('demo' IN v_actual) = 0
               OR position('live_demo' IN v_actual) = 0
               OR position('live' IN v_actual) = 0
            THEN
                RAISE EXCEPTION
                    'V100 Guard C FAIL: learning.hypotheses engine_mode CHECK enum mismatch. '
                    'Actual: %. Expected 4 values (paper/demo/live_demo/live).',
                    v_actual;
            END IF;
        END IF;
    END IF;

    -- learning.earn_movement_log CHECK 預檢
    v_target_oid := to_regclass('learning.earn_movement_log');
    IF v_target_oid IS NOT NULL THEN
        -- direction CHECK 2 值齊全
        SELECT pg_get_constraintdef(oid) INTO v_actual
        FROM pg_constraint
        WHERE conrelid=v_target_oid
          AND conname LIKE '%direction%check%'
        LIMIT 1;
        IF v_actual IS NOT NULL THEN
            IF position('stake' IN v_actual) = 0
               OR position('redeem' IN v_actual) = 0
            THEN
                RAISE EXCEPTION
                    'V100 Guard C FAIL: earn_movement_log direction CHECK enum mismatch. '
                    'Actual: %. Expected 2 values (stake/redeem).',
                    v_actual;
            END IF;
        END IF;

        -- reconciliation_status CHECK 3 值齊全
        SELECT pg_get_constraintdef(oid) INTO v_actual
        FROM pg_constraint
        WHERE conrelid=v_target_oid
          AND conname LIKE '%reconciliation_status%check%'
        LIMIT 1;
        IF v_actual IS NOT NULL THEN
            IF position('pending' IN v_actual) = 0
               OR position('matched' IN v_actual) = 0
               OR position('mismatch' IN v_actual) = 0
            THEN
                RAISE EXCEPTION
                    'V100 Guard C FAIL: earn_movement_log reconciliation_status CHECK enum mismatch. '
                    'Actual: %. Expected 3 values (pending/matched/mismatch).',
                    v_actual;
            END IF;
        END IF;
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 1: CREATE TABLE learning.hypotheses (13 column registry)
-- 主 DDL Step 1: 假設註冊主表 (13 column + 11 status enum + 4 engine_mode)
--
-- 設計依據 (per v103_v104 base spec §2.1.1):
-- - BIGSERIAL PK: sequential ID 利於 audit log temporal ordering
-- - strategy_name TEXT: 動態擴增 (5 既有 + Sprint 2+ 新策略); CHECK enum 易過時
-- - pre_reg_ts + pre_reg_hash: pre-registration 不變式 (ADR-0026 v3 + DOC-08 §12);
--   hash = spec_json + config_hash 的 git-style content hash
-- - status TEXT + CHECK 11 值: 統一 Sprint 1A canary preflight + Sprint 2 promotion
--   (draft → preregistered → shadow → stage_0r → stage_1-4 → live / retired / killed)
-- - expected_sharpe / expected_dd / capacity_estimate_usdt / t_stat_min /
--   min_sample_size NULL allowed: 起始 hypothesis 可暫不填;preregistered 後
--   IMPL 須 backfill
-- - REAL vs DOUBLE PRECISION: sharpe/dd/t_stat 4 byte 足夠;節省 storage
-- - capacity_estimate_usdt BIGINT: capacity 估計天然 round to USDT 整數
-- - engine_mode CHECK 4 值: paper/demo/live_demo/live;
--   training filter 必 IN ('live','live_demo') per CLAUDE.md §七
-- - 注意非 hypertable: regular table ~100 row/yr 低基數
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.hypotheses (
    hypothesis_id           BIGSERIAL PRIMARY KEY,
    strategy_name           TEXT NOT NULL,
    pre_reg_ts              TIMESTAMPTZ NOT NULL,
    pre_reg_hash            TEXT NOT NULL,
    status                  TEXT NOT NULL
                            CHECK (status IN (
                                'draft',
                                'preregistered',
                                'shadow',
                                'stage_0r',
                                'stage_1',
                                'stage_2',
                                'stage_3',
                                'stage_4',
                                'live',
                                'retired',
                                'killed'
                            )),
    expected_sharpe         REAL,
    expected_dd             REAL,
    capacity_estimate_usdt  BIGINT,
    t_stat_min              REAL,
    min_sample_size         INTEGER,
    engine_mode             TEXT NOT NULL
                            CHECK (engine_mode IN ('paper', 'demo', 'live_demo', 'live')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- Main DDL Step 2: CREATE TABLE learning.hypothesis_preregistration (append-only ledger)
-- 主 DDL Step 2: 假設預註冊簽署日誌 (7 column;append-only;FK to hypotheses)
--
-- 設計依據 (per v103_v104 base spec §2.2.1):
-- - BIGSERIAL PK + FK to hypotheses: 一對多 (一 hypothesis 可有多次簽署版本)
-- - payload_json JSONB NOT NULL: 序列化 hypothesis spec + statistical thresholds
--   + variance estimator + trigger rule (ADR-0026 v3 字段集移入 JSONB)
-- - payload_hash TEXT NOT NULL: git-style content hash of canonical JSON serialization
-- - operator_signature TEXT NOT NULL: 簽署人 ID + cryptographic signature
--   (Ed25519 / HMAC-SHA256 by IMPL 定;per DOC-08 §12 + §四 Operator 角色)
-- - signed_at TIMESTAMPTZ NOT NULL: audit timestamp
-- - engine_mode CHECK 4 值: 對齊 hypotheses 表
-- - 注意無 updated_at: append-only audit log; 任何 amendment = 新 row
--   (hypothesis_id 同 / payload_hash 不同 / signed_at 不同)
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.hypothesis_preregistration (
    preregistration_id      BIGSERIAL PRIMARY KEY,
    hypothesis_id           BIGINT NOT NULL
                            REFERENCES learning.hypotheses(hypothesis_id),
    payload_json            JSONB NOT NULL,
    payload_hash            TEXT NOT NULL,
    operator_signature      TEXT NOT NULL,
    signed_at               TIMESTAMPTZ NOT NULL,
    engine_mode             TEXT NOT NULL
                            CHECK (engine_mode IN ('paper', 'demo', 'live_demo', 'live'))
);

-- ============================================================
-- Main DDL Step 3: CREATE TABLE learning.earn_movement_log (Bybit Earn audit)
-- 主 DDL Step 3: Bybit Earn 質押/贖回審計日誌 (10 column;FK to governance_audit_log)
--
-- 設計依據 (per v103_v104 base spec §2.3.1):
-- - BIGSERIAL PK: audit log temporal ordering
-- - event_ts TIMESTAMPTZ NOT NULL: stake/redeem 真實時間 (Bybit response 提供)
-- - direction TEXT + CHECK 2 值 (stake/redeem): 雙向流動
-- - amount_usdt NUMERIC(18,8): 高精度 (Bybit Earn stable coin satoshi-scale);
--   不用 REAL 避免精度誤差
-- - apr_at_time REAL: APR 4-decimal float 足夠;NULL allowed for redeem
-- - governance_approval_id BIGINT FK:
--   **schema 名 patch — FK target = learning.governance_audit_log(id)**
--   (v103_v104 base spec §2.3.1 line 210 寫 governance.audit_log 為 schema typo;
--    production 真實表名為 learning.governance_audit_log per V035/V053/V098 baseline;
--    對齊 V106/V107/V112 PA-DRIFT-1 patch lesson)
-- - bybit_response_payload JSONB NULL: API raw response (reconciliation/debug);
--   NULL allowed for paper/demo dry-run
-- - engine_mode CHECK 4 值: 對齊 hypotheses 表
-- - api_scope_used TEXT NOT NULL: Bybit API permission scope
--   (e.g. account:earn:write); audit trail 必含 scope evidence
-- - reconciliation_status TEXT + CHECK 3 值 + DEFAULT 'pending':
--   daily reconciliation cron 將 pending → matched / mismatch
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.earn_movement_log (
    movement_id                BIGSERIAL PRIMARY KEY,
    event_ts                   TIMESTAMPTZ NOT NULL,
    direction                  TEXT NOT NULL
                               CHECK (direction IN ('stake', 'redeem')),
    amount_usdt                NUMERIC(18, 8) NOT NULL,
    apr_at_time                REAL,
    governance_approval_id     BIGINT REFERENCES learning.governance_audit_log(id),
    bybit_response_payload     JSONB,
    engine_mode                TEXT NOT NULL
                               CHECK (engine_mode IN ('paper', 'demo', 'live_demo', 'live')),
    api_scope_used             TEXT NOT NULL,
    reconciliation_status      TEXT NOT NULL DEFAULT 'pending'
                               CHECK (reconciliation_status IN (
                                   'pending',
                                   'matched',
                                   'mismatch'
                               ))
);

-- ============================================================
-- Main DDL Step 4: Hot-path indexes (4 個)
-- 主 DDL Step 4: 熱查詢索引 (4 個;對齊 v103_v104 §2.1.3/§2.2.3/§2.3.3)
--
-- 設計依據:
-- - idx_hypotheses_strategy_status: 高頻 query
--   SELECT * FROM learning.hypotheses WHERE strategy_name=$1 AND
--   status IN ('shadow','stage_0r','stage_1') for canary dashboard
-- - idx_hypotheses_pre_reg_ts: audit log temporal 排序 + recent preregistration
--   列表 (ORDER BY pre_reg_ts DESC)
-- - idx_preregistration_hypothesis_signed: 高頻 query
--   SELECT ... WHERE hypothesis_id=$1 ORDER BY signed_at DESC LIMIT 1
--   (latest signature lookup)
-- - idx_earn_movement_log_strategy_ts: daily reconciliation cron
--   WHERE event_ts > now() - INTERVAL '24 hours' ORDER BY event_ts DESC
--
-- 注意: 全 regular table 走 CREATE INDEX IF NOT EXISTS (非 CONCURRENTLY);
-- sqlx migrate BEGIN/COMMIT 包裹下 CONCURRENTLY 會 RAISE;對齊 V103 EXTEND 範式。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_hypotheses_strategy_status
    ON learning.hypotheses (strategy_name, status);

CREATE INDEX IF NOT EXISTS idx_hypotheses_pre_reg_ts
    ON learning.hypotheses (pre_reg_ts DESC);

CREATE INDEX IF NOT EXISTS idx_preregistration_hypothesis_signed
    ON learning.hypothesis_preregistration (hypothesis_id, signed_at DESC);

CREATE INDEX IF NOT EXISTS idx_earn_movement_log_strategy_ts
    ON learning.earn_movement_log (event_ts DESC);

-- ============================================================
-- Main DDL Step 5: COMMENT ON TABLE / COLUMN (audit metadata; 中文註釋)
-- 主 DDL Step 5: 表 / 欄位註釋 (運維說明;per feedback_chinese_only_comments)
-- ============================================================
COMMENT ON TABLE learning.hypotheses IS
    'M4 hypothesis discovery 主註冊表 (V100 base). 13 column + 11 status enum '
    '(draft/preregistered/shadow/stage_0r/stage_1-4/live/retired/killed per '
    'ADR-0026 v3 + Sprint 2 promotion). 對應 V103 EXTEND 6 column (M4 source '
    'lineage + leakage + Bonferroni + replicability + lease + cowork); 本 V100 '
    '不混 EXTEND scope。低基數 ~100 row/yr regular table 非 hypertable。';

COMMENT ON COLUMN learning.hypotheses.hypothesis_id IS
    'BIGSERIAL PK; sequential audit log temporal ordering; V103 EXTEND 與 V107 '
    'replay_divergence_log + 後續 M4 cohort 表 FK target。';

COMMENT ON COLUMN learning.hypotheses.strategy_name IS
    'TEXT 動態擴增 (5 既有 + Sprint 2+ ASDS-generated + cointegration_pairs); '
    '不採 CHECK enum 避過時。';

COMMENT ON COLUMN learning.hypotheses.pre_reg_ts IS
    'Pre-registration 不變式時間戳 (ADR-0026 v3 + DOC-08 §12); 與 pre_reg_hash '
    '配對組成 immutable 簽署 ID。';

COMMENT ON COLUMN learning.hypotheses.pre_reg_hash IS
    'spec_json + config_hash 的 git-style content hash; algorithm 由 IMPL 期 '
    'trainer adapter 定 (typical: SHA-256 of canonical JSON serialization)。';

COMMENT ON COLUMN learning.hypotheses.status IS
    '11 enum 統一 canary preflight + promotion: '
    'draft (起草) / preregistered (簽署) / shadow (影子) / stage_0r (replay 預檢) / '
    'stage_1-4 (Stage 1-4 promotion) / live (生產) / retired (退役) / killed '
    '(中止)。對齊 ADR-0026 v3 4-stage + Sprint 2 dual-track promotion。';

COMMENT ON COLUMN learning.hypotheses.expected_sharpe IS
    'REAL single-precision; pre-registered 統計門檻 (preregistered 後 IMPL '
    '須 backfill); 起始 NULL allowed。';

COMMENT ON COLUMN learning.hypotheses.expected_dd IS
    'REAL single-precision; pre-registered 最大回撤門檻 (preregistered 後 '
    '須 backfill); 起始 NULL allowed。';

COMMENT ON COLUMN learning.hypotheses.capacity_estimate_usdt IS
    'BIGINT 整數 USDT (capacity 估計天然 round); 不用 NUMERIC 小數精度。';

COMMENT ON COLUMN learning.hypotheses.t_stat_min IS
    'REAL pre-registered t-statistic 最低門檻 (statistical significance gate); '
    '起始 NULL allowed。';

COMMENT ON COLUMN learning.hypotheses.min_sample_size IS
    'INTEGER pre-registered 最低樣本量 (Wilson CI + n>=200 統計守門 gate); '
    '起始 NULL allowed。';

COMMENT ON COLUMN learning.hypotheses.engine_mode IS
    '4 enum (paper/demo/live_demo/live); ML training filter 必 IN '
    '(''live'',''live_demo'') per CLAUDE.md §七; preregistration 期 paper / '
    'shadow 期 demo / promotion 期 live_demo → live。';

COMMENT ON TABLE learning.hypothesis_preregistration IS
    'M4 hypothesis 預註冊簽署日誌 (V100; append-only). FK to learning.hypotheses; '
    '一 hypothesis 可有多次簽署版本 (amendment = 新 row);無 updated_at;7 column '
    '包含 payload_json (JSONB spec + thresholds + variance + trigger rule)。';

COMMENT ON COLUMN learning.hypothesis_preregistration.payload_json IS
    'JSONB 序列化 hypothesis 完整 spec; 含 statistical thresholds + variance '
    'estimator + trigger rule (ADR-0026 v3 字段集移入此 JSONB)。';

COMMENT ON COLUMN learning.hypothesis_preregistration.payload_hash IS
    'git-style content hash of canonical JSON serialization; 防 payload 篡改。';

COMMENT ON COLUMN learning.hypothesis_preregistration.operator_signature IS
    'Operator 簽署 ID + cryptographic signature (Ed25519 / HMAC-SHA256 by IMPL); '
    'per DOC-08 §12 + §四 Operator 角色硬邊界。';

COMMENT ON TABLE learning.earn_movement_log IS
    'Bybit Earn 質押/贖回審計日誌 (V100; append-only). 10 column 含 FK to '
    'learning.governance_audit_log (Decision Lease 審批 cross-ref); '
    'reconciliation_status 3 值 (pending → matched/mismatch 由 daily cron 寫入)。';

COMMENT ON COLUMN learning.earn_movement_log.direction IS
    '2 enum (stake/redeem) 雙向流動方向。';

COMMENT ON COLUMN learning.earn_movement_log.amount_usdt IS
    'NUMERIC(18,8) 高精度 (Bybit Earn stable coin satoshi-scale);不用 REAL '
    '避免精度誤差 (REAL 在 satoshi-scale amount 會丟精度)。';

COMMENT ON COLUMN learning.earn_movement_log.apr_at_time IS
    'REAL APR 4-decimal float 足夠;NULL allowed for redeem (redemption 不 lock APR)。';

COMMENT ON COLUMN learning.earn_movement_log.governance_approval_id IS
    'FK to learning.governance_audit_log(id); Decision Lease 審批 cross-ref。'
    '注意: spec doc §2.3.1 寫 governance.audit_log 為 schema 名 typo;'
    '真實 production 表名為 learning.governance_audit_log (per V035/V053/V098 baseline)。'
    'V106/V107/V112 PA-DRIFT-1 patch lesson 對齊。';

COMMENT ON COLUMN learning.earn_movement_log.bybit_response_payload IS
    'JSONB Bybit API raw response (reconciliation/debug); NULL allowed for '
    'paper/demo dry-run。';

COMMENT ON COLUMN learning.earn_movement_log.api_scope_used IS
    'Bybit API permission scope (e.g. account:earn:write); audit trail 必含 '
    'scope evidence (compliance + post-incident forensic)。';

COMMENT ON COLUMN learning.earn_movement_log.reconciliation_status IS
    '3 enum (pending/matched/mismatch); daily reconciliation cron 將 pending '
    '→ matched/mismatch (per Sprint 1B daily_reconciliation 邏輯)。';

COMMENT ON COLUMN learning.earn_movement_log.engine_mode IS
    '4 enum (paper/demo/live_demo/live); ML training filter 必 IN '
    '(''live'',''live_demo'') per CLAUDE.md §七。';

-- ============================================================
-- Guard C 後驗: 確保 DDL 成功後 CHECK + index + FK 全到位
-- (與 Guard C 前置一致但放寬:後驗預期 constraint 必存在)
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_index_count INTEGER;
    v_fk_count INTEGER;
BEGIN
    -- hypotheses.status CHECK 11 值齊全 (後驗;首次 apply 必經此 path)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.hypotheses'::regclass
      AND conname LIKE '%status%check%'
    LIMIT 1;
    IF v_actual IS NULL THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: hypotheses status CHECK constraint not found after DDL.';
    END IF;
    IF position('draft' IN v_actual) = 0
       OR position('preregistered' IN v_actual) = 0
       OR position('shadow' IN v_actual) = 0
       OR position('stage_0r' IN v_actual) = 0
       OR position('stage_1' IN v_actual) = 0
       OR position('stage_2' IN v_actual) = 0
       OR position('stage_3' IN v_actual) = 0
       OR position('stage_4' IN v_actual) = 0
       OR position('live' IN v_actual) = 0
       OR position('retired' IN v_actual) = 0
       OR position('killed' IN v_actual) = 0
    THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: hypotheses status CHECK missing required 11 values. Actual: %.',
            v_actual;
    END IF;

    -- hypotheses.engine_mode CHECK 4 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.hypotheses'::regclass
      AND conname LIKE '%engine_mode%check%'
    LIMIT 1;
    IF v_actual IS NULL THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: hypotheses engine_mode CHECK constraint not found.';
    END IF;
    IF position('paper' IN v_actual) = 0
       OR position('demo' IN v_actual) = 0
       OR position('live_demo' IN v_actual) = 0
       OR position('live' IN v_actual) = 0
    THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: hypotheses engine_mode CHECK missing required 4 values. Actual: %.',
            v_actual;
    END IF;

    -- earn_movement_log.direction CHECK 2 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.earn_movement_log'::regclass
      AND conname LIKE '%direction%check%'
    LIMIT 1;
    IF v_actual IS NULL THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: earn_movement_log direction CHECK constraint not found.';
    END IF;
    IF position('stake' IN v_actual) = 0
       OR position('redeem' IN v_actual) = 0
    THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: earn_movement_log direction CHECK missing required 2 values. Actual: %.',
            v_actual;
    END IF;

    -- earn_movement_log.reconciliation_status CHECK 3 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.earn_movement_log'::regclass
      AND conname LIKE '%reconciliation_status%check%'
    LIMIT 1;
    IF v_actual IS NULL THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: earn_movement_log reconciliation_status CHECK constraint not found.';
    END IF;
    IF position('pending' IN v_actual) = 0
       OR position('matched' IN v_actual) = 0
       OR position('mismatch' IN v_actual) = 0
    THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: earn_movement_log reconciliation_status CHECK missing required 3 values. Actual: %.',
            v_actual;
    END IF;

    -- 4 hot-path index 全到位
    SELECT COUNT(*) INTO v_index_count
    FROM pg_indexes
    WHERE schemaname='learning'
      AND indexname IN (
          'idx_hypotheses_strategy_status',
          'idx_hypotheses_pre_reg_ts',
          'idx_preregistration_hypothesis_signed',
          'idx_earn_movement_log_strategy_ts'
      );
    IF v_index_count <> 4 THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: 4 hot-path index expected, found %.',
            v_index_count;
    END IF;

    -- FK 必存在:preregistration → hypotheses
    SELECT COUNT(*) INTO v_fk_count
    FROM pg_constraint c
    JOIN pg_class r ON c.conrelid = r.oid
    JOIN pg_namespace n ON r.relnamespace = n.oid
    WHERE n.nspname='learning' AND r.relname='hypothesis_preregistration'
      AND c.contype='f';
    IF v_fk_count = 0 THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: hypothesis_preregistration.hypothesis_id FK to '
            'learning.hypotheses missing.';
    END IF;

    -- FK 必存在:earn_movement_log → governance_audit_log
    -- (注意 FK target schema 名 patch:learning.governance_audit_log 非
    -- governance.audit_log per PA-DRIFT-1 lesson)
    SELECT COUNT(*) INTO v_fk_count
    FROM pg_constraint c
    JOIN pg_class r ON c.conrelid = r.oid
    JOIN pg_namespace n ON r.relnamespace = n.oid
    WHERE n.nspname='learning' AND r.relname='earn_movement_log'
      AND c.contype='f';
    IF v_fk_count = 0 THEN
        RAISE EXCEPTION
            'V100 Guard C post FAIL: earn_movement_log.governance_approval_id FK to '
            'learning.governance_audit_log missing.';
    END IF;

    RAISE NOTICE
        'V100: M4 base table all guards PASS — 3 NEW table (learning.hypotheses '
        '13 col / hypothesis_preregistration 7 col / earn_movement_log 10 col), '
        'status CHECK 11 values, engine_mode CHECK 4 values, direction CHECK 2 '
        'values, reconciliation_status CHECK 3 values, 4 hot-path index built, '
        '2 FK installed (preregistration.hypothesis_id → hypotheses; '
        'earn_movement_log.governance_approval_id → learning.governance_audit_log '
        '[schema patch per PA-DRIFT-1]). V103 EXTEND Guard A now satisfied; '
        'sqlx chain V099 (autonomy) → V100 (M4 base) → V103 (EXTEND M4 6 col) ready.';
END $$;

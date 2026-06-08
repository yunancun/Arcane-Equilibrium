-- ============================================================
-- V135: learning.l2_gate_seam_log
--       L2 Advisory Mesh — D3 gate-seam 取證日誌（Phase 1）
--
-- 目的：
--   記錄每個 L2-origin artifact「被哪個確定性 gate 放行、放行後變成什麼」。
--   §D.4 fault-localization protocol step-3 的 forensic 來源：給定 l2_reply_id
--   → 查哪個 gate 以何 verdict 讓它通過、applier 把它落成什麼（或僅 proposal）。
--
-- 範圍 / 硬邊界：
--   - additive only；不改任何既有表、不碰 order / promotion / lease / live。
--   - 純 audit/provenance，非交易真相層，不授權任何 live 行為。
--   - 純 append-only：REVOKE UPDATE, DELETE；trading_ai 只 INSERT/SELECT；
--     全表零 column-level UPDATE grant（與 V134 三表統一，將來一致可壓縮）。
--   - 寫入唯一入口 = L2CallLedgerWriter.record_gate_seam（INSERT-only）；read 唯讀。
--   - l2_reply_id 為 logical FK（非 DB FK），對齊 V064 decision_edges
--     「logical FK only」範式；故 V134/V135 可獨立 dry-run + 雙 apply。
--
-- 為什麼獨立 migration（非併入 V134）：
--   不同 schema（learning vs agent）、不同表、不同生命週期。把無關 DDL 併進
--   一個 migration 會混淆 dry-run blast radius 與冪等推理（CLAUDE「Git And Sync」
--   每個 V### 應為一個 coherent green checkpoint）。
--
-- 為什麼 idempotent / double-apply safe：
--   全部物件 IF NOT EXISTS；Guard A 反射必要欄位防 schema 漂移；REVOKE DO 包住
--   dev-sandbox role 缺失。Linux PG 雙 apply 冪等 dry-run owed（E4，operator-gated）。
--
-- Guard：
--   Guard A：既有表缺必要欄 → RAISE。
--   Guard C：forensic 索引存在性。
--   （verdict enum 由 CHECK 約束強制，非額外 Guard B。）
--
-- Precedent（file:line）：
--   - REVOKE 區塊 = V099:298-307。hypertable + 複合 PK = V064:163,180-184。
--   - verdict CHECK enum 對齊 ledger guard_verdict 詞彙（V134 chk_l2_calls_guard_verdict）。
-- ============================================================

BEGIN;

-- learning schema 在既有 migration 已建（V054/V100 等）；此處保險 IF NOT EXISTS。
CREATE SCHEMA IF NOT EXISTS learning;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A：表已存在時反射必要欄位，缺欄即 RAISE（防 schema 漂移）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'l2_gate_seam_log'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'seam_id',
            'ts',
            'l2_reply_id',
            'gate_id',
            'verdict',
            'applier',
            'applied_as',
            'details'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning' AND table_name = 'l2_gate_seam_log'
              AND column_name = c
        );

        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V135 Guard A FAIL: learning.l2_gate_seam_log exists but missing required columns: %.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Main DDL：learning.l2_gate_seam_log
--   PK = (seam_id, ts)：hypertable 要求 partition key 入唯一約束。
--   verdict CHECK enum 與 V134 ledger.guard_verdict 詞彙對齊。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learning.l2_gate_seam_log (
    seam_id        BIGSERIAL,
    ts             TIMESTAMPTZ NOT NULL DEFAULT NOW(),   -- hypertable partition key
    l2_reply_id    TEXT        NOT NULL,                 -- artifact root provenance（joins l2_calls）
    gate_id        TEXT        NOT NULL,                 -- 哪個確定性 gate（dsr/pbo/leak/beta_neutral/...）
    verdict        TEXT        NOT NULL,                 -- pass|clamp|reject
    applier        TEXT,                                 -- 哪個 lane-bound applier（NULL=proposal only）
    applied_as     TEXT,                                 -- 具體變成什麼，或 "proposal only"
    details        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (seam_id, ts),
    CONSTRAINT chk_l2_gate_seam_verdict CHECK (verdict IN ('pass', 'clamp', 'reject'))
);

-- hypertable on ts（7-day chunks）。
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('learning.l2_gate_seam_log', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
    RAISE NOTICE 'V135: learning.l2_gate_seam_log hypertable (ts, 7-day chunks) ready';
ELSE
    RAISE NOTICE 'V135: timescaledb absent; learning.l2_gate_seam_log stays plain table';
END IF;
END $$;

-- §D.4-step-3 forensic query：WHERE l2_reply_id = ? → 哪個 gate 放行。
CREATE INDEX IF NOT EXISTS idx_l2_gate_seam_reply
    ON learning.l2_gate_seam_log (l2_reply_id, ts DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C：forensic 索引存在性。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'learning' AND tablename = 'l2_gate_seam_log'
          AND indexname = 'idx_l2_gate_seam_reply'
    ) THEN
        RAISE EXCEPTION 'V135 Guard C FAIL: idx_l2_gate_seam_reply missing.';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Append-only：REVOKE UPDATE, DELETE；trading_ai 只 INSERT/SELECT + sequence USAGE。
--   零 column-level UPDATE grant。範式 = V099:298-307。
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE UPDATE, DELETE ON learning.l2_gate_seam_log FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON learning.l2_gate_seam_log FROM trading_ai';
        EXECUTE 'GRANT SELECT, INSERT ON learning.l2_gate_seam_log TO trading_ai';
        EXECUTE 'GRANT USAGE ON SEQUENCE learning.l2_gate_seam_log_seam_id_seq TO trading_ai';
        RAISE NOTICE 'V135: learning.l2_gate_seam_log — trading_ai = INSERT/SELECT only; UPDATE/DELETE revoked';
    ELSE
        RAISE NOTICE 'V135: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient';
    END IF;
END $$;

COMMENT ON TABLE learning.l2_gate_seam_log IS
    'L2 Advisory Mesh D3 gate-seam log. One append-only row per (artifact, deterministic gate): which gate passed/clamped/rejected an L2-origin artifact and what it concretely became (or "proposal only"). Pure append-only, zero column-level UPDATE grant. Audit/provenance only.';

COMMIT;

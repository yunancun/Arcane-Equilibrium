-- ============================================================
-- V136: upstream provenance additive columns（source_l2_reply_id）
--       L2 Advisory Mesh — D3 Provenance chain（Phase 1）
--
-- 目的：
--   把 L2 root provenance handle（source_l2_reply_id，= agent.l2_calls.l2_reply_id）
--   以「additive nullable column」掛到 upstream research-plane targets，讓任何
--   L2-origin artifact 從 reply → hypothesis → replay-experiment → demo-fill 可被
--   逐跳追溯。root id 在每一跳「原樣前傳，永不 re-derive」（PA 設計 §C :751-754）。
--
-- 範圍 / 硬邊界（operator scope ruling 2026-06-08）：
--   - P1 只加到 upstream RESEARCH-PLANE targets：
--       learning.hypotheses / replay.experiments / trading.fills（demo）。
--   - 全部 additive nullable，NO backfill，NO NOT NULL：provenance 對既有
--     /human/deterministic-origin row 為 NULL，是正確的（gate 收到無 source 的
--     artifact 視為 non-L2，設計 §D.2 :771-772）。
--   - trading.fills 是 TimescaleDB columnstore hypertable（V101:49-53）→ ADD COLUMN
--     必須 nullable / 無 DEFAULT / 不 SET NOT NULL（columnstore feature_not_supported，
--     V077 lesson / V101:170-181 vetted range）。本檔對 trading.fills 嚴守此形。
--   - trading.decision_outcomes 不在 P1：屬 deferred R2-5 live hop（需 Rust engine
--     改 live-record path + 可能 hash-chained live 表），本檔不觸碰任何 live 表。
--   - 無 physical strategy-variant 表（grep 0 hit；asds_factory 是 trading.fills.track
--     的 enum 值 V101:79-82，非 variant 表 row）→ 該 hop deferred-by-absence，
--     chain 仍 forward-compatible（variant 表首次出現時 root id 自然前傳）。
--   - agent.lessons：用既有 context_id 欄映射到 l2_reply_id（V133 已有欄）→ 無 DDL。
--   - demo Stage-1 manifest：source_l2_reply_id 以 jsonb key 隨 manifest 走 → 無 DDL。
--
-- 為什麼獨立 migration（operator-LOCKED，§E，覆蓋早期 fold-into-V134 rec）：
--   ledger（V134）今天完全可定稿、可早簽；本 V136 的 ALTER 有 Linux-verify
--   依賴（trading.fills columnstore 形需 live DB 確認；decision_outcomes/manifest
--   table-vs-jsonb 需 live 確認）。拆出 V136 讓 V134 不必等這些確認即可簽，且
--   columnstore feature_not_supported regression（若有）被隔離在 V136、不污染
--   ledger migration 的 rollback / dry-run blast radius。
--
-- 為什麼 idempotent / double-apply safe：
--   全部 ADD COLUMN IF NOT EXISTS；first-apply 加欄，second-apply no-op 乾淨。
--   Guard A 確認 target 表存在；Guard B 在欄已存在時反射 type/nullable，漂移即 RAISE。
--   Linux PG 雙 apply 冪等 dry-run + trading.fills columnstore no-raise 驗 owed
--   （E4，operator-gated；§H.7）。
--
-- Guard：
--   Guard A：每個 target 表必存在（缺 → RAISE，指向其 base migration）。
--   Guard B：source_l2_reply_id 已存在時反射 data_type=text / nullable=YES，漂移即 RAISE。
--
-- Precedent（file:line）：
--   - columnstore-safe ADD COLUMN = V101:170-181（trading.fills.track nullable 無 DEFAULT）。
--   - Guard B type/nullable 反射 = V101:143-167。
-- ============================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A：三個 target 表必存在（additive 前提）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'hypotheses'
    ) THEN
        RAISE EXCEPTION
            'V136 Guard A FAIL: learning.hypotheses missing — V100 must apply first.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'experiments'
    ) THEN
        RAISE EXCEPTION
            'V136 Guard A FAIL: replay.experiments missing — V041 must apply first.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'trading' AND table_name = 'fills'
    ) THEN
        RAISE EXCEPTION
            'V136 Guard A FAIL: trading.fills missing — V003 must apply first.';
    END IF;
    RAISE NOTICE 'V136 Guard A PASS: learning.hypotheses / replay.experiments / trading.fills present';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B：source_l2_reply_id 已存在時反射 type/nullable，型別/可空漂移即 RAISE。
--   首次 apply SELECT 返 NULL → skip → PASS。三表共用同一形（text NULL）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    r RECORD;
    v_data_type TEXT;
    v_is_nullable TEXT;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('learning', 'hypotheses'),
            ('replay', 'experiments'),
            ('trading', 'fills')
        ) AS t(sch, tbl)
    LOOP
        SELECT data_type, is_nullable
          INTO v_data_type, v_is_nullable
        FROM information_schema.columns
        WHERE table_schema = r.sch AND table_name = r.tbl
          AND column_name = 'source_l2_reply_id';

        IF v_data_type IS NOT NULL THEN
            IF v_data_type IS DISTINCT FROM 'text'
               OR v_is_nullable IS DISTINCT FROM 'YES' THEN
                RAISE EXCEPTION
                    'V136 Guard B FAIL: %.%.source_l2_reply_id type drift. '
                    'Expected text NULL, got type=%, nullable=%.',
                    r.sch, r.tbl, v_data_type, v_is_nullable;
            END IF;
            RAISE NOTICE 'V136 Guard B PASS: %.%.source_l2_reply_id already text NULL (idempotent)',
                r.sch, r.tbl;
        END IF;
    END LOOP;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Main DDL：additive nullable source_l2_reply_id（三 target）。
--   learning.hypotheses / replay.experiments 為 plain table → 普通 ADD COLUMN。
--   trading.fills 為 columnstore hypertable → 嚴守 nullable / 無 DEFAULT / 不 SET NOT NULL。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS source_l2_reply_id TEXT NULL;

ALTER TABLE replay.experiments
    ADD COLUMN IF NOT EXISTS source_l2_reply_id TEXT NULL;

-- columnstore-safe：nullable，無 DEFAULT，不 SET NOT NULL（V101:170-181 範式）。
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS source_l2_reply_id TEXT NULL;

COMMENT ON COLUMN learning.hypotheses.source_l2_reply_id IS
    'L2 Advisory Mesh provenance. Root agent.l2_calls.l2_reply_id propagated unchanged from the originating L2 reply (NULL for pre-existing/human/deterministic-origin rows). Additive, audit-only.';
COMMENT ON COLUMN replay.experiments.source_l2_reply_id IS
    'L2 Advisory Mesh provenance. Root l2_reply_id copied forward from the originating hypothesis/reply, never re-derived. NULL = non-L2 origin. Additive, audit-only.';
COMMENT ON COLUMN trading.fills.source_l2_reply_id IS
    'L2 Advisory Mesh provenance (demo plane). Root l2_reply_id copied forward, never re-derived. NULL = non-L2 origin. Columnstore-safe additive nullable column (no DEFAULT, no SET NOT NULL per V077/V101). Audit-only; no live authority.';

COMMIT;

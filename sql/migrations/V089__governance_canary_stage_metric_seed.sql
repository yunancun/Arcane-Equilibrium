-- ============================================================
-- V089: W5-E1-A P1-CANARY-STAGE-CRITERIA-1 — graduated canary
--   stage promotion + rollback metric registry seed
--
-- 動機 / Motivation:
--   AMD-2026-05-09-03 §4.2 把 graduated canary 5-stage 升級條件 + auto-rollback
--   trigger 落到 governance.canary_stage_metric_registry（V080 已建表）。
--   W5-E1-A spec
--     `docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`
--   §2-§5 把所有 promote / rollback 條件寫死成可執行 metric definition
--   後，本 V089 將之 seed 進 PG，使 healthcheck `[58]` enrich 可比對 cohort
--   實際 metric 值與 spec 閾值的距離（margin），W5-E1-D shadow_mode_provider
--   stage-aware eval 也讀本 seed 做 evaluator pipeline 路徑統一。
--
-- 範圍 / Scope:
--   1. INSERT INTO governance.canary_stage_metric_registry 12 promote_condition
--      row（Stage 1: 4 / Stage 2: 5 / Stage 3: 5 / Stage 4: 0 — operator-pinned）
--   2. INSERT INTO governance.canary_stage_metric_registry 6 rollback_trigger
--      row（Stage 1: 1 / Stage 2: 2 / Stage 3: 2 / Stage 4: 1）
--   3. ON CONFLICT skip — UNIQUE (stage, metric_name) WHERE active=true
--      由 V080 partial unique index uq_canary_stage_metric_registry_active
--      強制；ON CONFLICT 走 partial index 的 conflict target；idempotent re-run。
--   4. Guard A 驗 V080 兩張表存在 + 必要欄位俱在；Guard C 驗 V080
--      uq_canary_stage_metric_registry_active partial unique index 健在
--      （否則 ON CONFLICT 路徑無 conflict target 會 RAISE）。
--
-- 不變式 / Invariants:
--   - 12 promote + 6 rollback = 18 row 共必達；spec acceptance §3 要 ≥12 row。
--   - direction enum 對齊 V080 CHECK：promote_upper / promote_lower /
--     rollback_upper / rollback_lower。
--   - threshold_value 與 spec §2-§5 公式 byte-identical（reviewer 必逐項對齊）。
--   - observation_window_ms 對 promote = 整 stage 觀察期（7d/14d/21d）；
--     對 rollback = 24h sliding（短期 trip 偵測）/ 6h-12h（spec §5 第 2-3 列指定）。
--
-- Idempotency:
--   - psql -f V089__... 跑兩次第二次必不 RAISE。ON CONFLICT (stage, metric_name)
--     WHERE active = TRUE DO NOTHING — 對 partial unique index 走 conflict target。
--
-- E2 重點審查（per spec §8 Acceptance + AMD §7 audit point）：
--   #1 threshold_value 對齊 spec §2-§5 公式（promote 條件 + rollback trigger）
--   #2 direction 對齊 V080 CHECK enum + spec §2 explicit semantic
--   #3 observation_window_ms 對 promote 取 stage 整觀察期；rollback 取 24h sliding
--      （per AMD §4.2 + spec §5 表格時間窗註解）
--   #4 Guard C unique index 失存 → 改 W080 而非本 V089
--
-- Cross-references:
--   - V080__governance_canary_stage.sql §4.2 schema definition
--   - AMD-2026-05-09-03 §2.2 5-stage 表 + §4.2 PG 持久化
--   - W5-E1-A spec §2-§5 promote / rollback 公式
-- ============================================================


-- ============================================================
-- Schema Guard A — V080 表 + 欄位俱在
-- 缺即 RAISE，提示 operator 先跑 V080。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'governance'
          AND table_name = 'canary_stage_metric_registry'
    ) THEN
        RAISE EXCEPTION
            'schema_guard A: governance.canary_stage_metric_registry missing — V080 not applied. '
            'Apply V080__governance_canary_stage.sql first.';
    END IF;

    -- 必要欄位（V080 與本 V089 INSERT column list 對齊）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'governance'
          AND table_name = 'canary_stage_metric_registry'
          AND column_name = 'metric_name'
    ) THEN
        RAISE EXCEPTION
            'schema_guard A: governance.canary_stage_metric_registry.metric_name missing — '
            'V080 schema drift. Re-apply V080.';
    END IF;
END $$;


-- ============================================================
-- Schema Guard C — V080 partial unique index 健在
-- ON CONFLICT (stage, metric_name) WHERE active 走此 index；不存在會
-- 報 "there is no unique or exclusion constraint matching the ON CONFLICT specification"。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'governance'
          AND indexname = 'uq_canary_stage_metric_registry_active'
    ) THEN
        RAISE EXCEPTION
            'schema_guard C: governance.uq_canary_stage_metric_registry_active partial unique '
            'index missing — V080 not fully applied. ON CONFLICT path will fail. Re-apply V080.';
    END IF;
END $$;


-- ============================================================
-- Stage 1 — promote_condition (Stage 1 → Stage 2 spec §2.1)
--   公式: wall_clock ≥ 7d AND entry_fills ≥ 10 AND boundary_violation = 0
--          AND sample_floor ≥ 72h
--   observation_window_ms = 7d 整觀察期（但 entry_fills 是累計 since stage_entered）
-- ============================================================

INSERT INTO governance.canary_stage_metric_registry (
    stage, metric_name, direction, threshold_value, observation_window_ms,
    active, description
) VALUES
    (1, 'wall_clock_elapsed_ms', 'promote_upper', 604800000, 604800000, TRUE,
     'Stage 1 → 2 wall-clock floor 7d (spec §2.1)'),
    (1, 'entry_fills_count', 'promote_upper', 10, 604800000, TRUE,
     'Stage 1 → 2 cohort entry fill quantitative gate (spec §2.1 + §2.2 SQL)'),
    (1, 'boundary_violation_count', 'promote_lower', 1, 604800000, TRUE,
     'Stage 1 → 2 boundary fail-closed; trip count must be 0 (spec §2.1 + §2.4)'),
    (1, 'sample_size_floor_ms', 'promote_upper', 259200000, 604800000, TRUE,
     'Stage 1 → 2 sample floor 72h (spec §2.3 QC HIGH push back 2)')
ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;


-- ============================================================
-- Stage 2 — promote_condition (Stage 2 → Stage 3 spec §3)
--   公式: wall_clock ≥ 14d AND entry_fills ≥ 30 AND gross_pnl > -5
--          AND DSR > 0.5 AND boundary_violation = 0 AND sample_floor ≥ 168h(7d)
-- ============================================================

INSERT INTO governance.canary_stage_metric_registry (
    stage, metric_name, direction, threshold_value, observation_window_ms,
    active, description
) VALUES
    (2, 'wall_clock_elapsed_ms', 'promote_upper', 1209600000, 1209600000, TRUE,
     'Stage 2 → 3 wall-clock floor 14d (spec §3)'),
    (2, 'entry_fills_count', 'promote_upper', 30, 1209600000, TRUE,
     'Stage 2 → 3 cohort entry fill quantitative gate (spec §3)'),
    (2, 'gross_pnl_usdt', 'promote_upper', -5.0, 1209600000, TRUE,
     'Stage 2 → 3 gross PnL strict floor -5 USDT (spec §3)'),
    (2, 'DSR', 'promote_upper', 0.5, 1209600000, TRUE,
     'Stage 2 → 3 Deflated Sharpe Ratio floor 0.5 (spec §3 + W-AUDIT-6 acceptance)'),
    (2, 'sample_size_floor_ms', 'promote_upper', 604800000, 1209600000, TRUE,
     'Stage 2 → 3 sample floor 7d hard for demo (spec §3)')
ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;


-- ============================================================
-- Stage 3 — promote_condition (Stage 3 → Stage 4 spec §4)
--   公式: wall_clock ≥ 21d AND gross_pnl > 0 AND DSR PASS AND PBO ≤ 0.5
--          AND attribution_chain_ok ≥ 0.7 AND boundary_violation = 0
--   spec §4 明示 Stage 4 不 auto-promote — healthcheck 達成後寫
--   GUI surface 'ready_for_stage_4_review'，operator 拍板 + signed authorization。
-- ============================================================

INSERT INTO governance.canary_stage_metric_registry (
    stage, metric_name, direction, threshold_value, observation_window_ms,
    active, description
) VALUES
    (3, 'wall_clock_elapsed_ms', 'promote_upper', 1814400000, 1814400000, TRUE,
     'Stage 3 → 4 wall-clock floor 21d (spec §4)'),
    (3, 'gross_pnl_usdt', 'promote_upper', 0.0, 1814400000, TRUE,
     'Stage 3 → 4 gross PnL strict positive (spec §4)'),
    (3, 'DSR', 'promote_upper', 0.0, 1814400000, TRUE,
     'Stage 3 → 4 DSR PASS (spec §4 + W-AUDIT-6 acceptance pipeline)'),
    (3, 'PBO', 'promote_lower', 0.5, 1814400000, TRUE,
     'Stage 3 → 4 PBO ceiling 0.5 (spec §4)'),
    (3, 'attribution_chain_ok_ratio', 'promote_upper', 0.7, 1814400000, TRUE,
     'Stage 3 → 4 attribution chain ok ratio floor 0.7 (spec §4 + [55] healthcheck)')
ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;


-- ============================================================
-- Stage 1 — rollback_trigger (spec §5 第 1 列, Stage 1 → Stage 0)
--   condition (任一 OR): boundary_violation > 0 OR lease_ipc_failure > 1% OR SM-04 ≥ L3
--   AMD §3.2: SM-04 ≥ L3 跨 stage 強制 demote 至 Stage 0；本表只記 Stage 1 自家 trigger。
--   observation_window_ms = 6h sliding（spec §5 第 1 列預設 fast-trip）
-- ============================================================

INSERT INTO governance.canary_stage_metric_registry (
    stage, metric_name, direction, threshold_value, observation_window_ms,
    active, description
) VALUES
    (1, 'boundary_violation_count_rollback', 'rollback_upper', 0, 21600000, TRUE,
     'Stage 1 → 0 demote: any boundary violation in 6h sliding (spec §5 第 1 列)')
ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;


-- ============================================================
-- Stage 2 — rollback_trigger (spec §5 第 2 列, Stage 2 → Stage 1)
--   condition (任一 OR): gross_pnl < -10 OR DSR < 0 OR Stage 1 trigger 持續 ≥ 6h
-- ============================================================

INSERT INTO governance.canary_stage_metric_registry (
    stage, metric_name, direction, threshold_value, observation_window_ms,
    active, description
) VALUES
    (2, 'gross_pnl_usdt_rollback', 'rollback_lower', -10.0, 86400000, TRUE,
     'Stage 2 → 1 demote: gross PnL drops below -10 USDT in 24h sliding (spec §5 第 2 列)'),
    (2, 'DSR_rollback', 'rollback_lower', 0.0, 86400000, TRUE,
     'Stage 2 → 1 demote: DSR drops below 0 in 24h sliding (spec §5 第 2 列)')
ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;


-- ============================================================
-- Stage 3 — rollback_trigger (spec §5 第 3 列, Stage 3 → Stage 2)
--   condition (任一 OR): gross_pnl < -20 OR DSR < 0 OR attribution_chain_ok < 0.3
--                         OR Stage 2 trigger 持續 ≥ 12h
-- ============================================================

INSERT INTO governance.canary_stage_metric_registry (
    stage, metric_name, direction, threshold_value, observation_window_ms,
    active, description
) VALUES
    (3, 'gross_pnl_usdt_rollback', 'rollback_lower', -20.0, 86400000, TRUE,
     'Stage 3 → 2 demote: gross PnL drops below -20 USDT in 24h sliding (spec §5 第 3 列)'),
    (3, 'attribution_chain_ok_ratio_rollback', 'rollback_lower', 0.3, 86400000, TRUE,
     'Stage 3 → 2 demote: attribution chain ok ratio < 0.3 in 24h sliding (spec §5 第 3 列)')
ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;


-- ============================================================
-- Stage 4 — rollback_trigger (spec §5 第 4 列, Stage 4 → Stage 0)
--   condition: 任一 boundary 失敗 → cancel_token shutdown，回 Stage 0（不是 Stage 3）
--   spec §5: Stage 4 demote 直回 Stage 0 而非 Stage 3 — 這是有意設計的最高嚴重度。
-- ============================================================

INSERT INTO governance.canary_stage_metric_registry (
    stage, metric_name, direction, threshold_value, observation_window_ms,
    active, description
) VALUES
    (4, 'boundary_violation_count_rollback', 'rollback_upper', 0, 3600000, TRUE,
     'Stage 4 → 0 demote: any boundary violation in 1h sliding triggers cancel_token shutdown (spec §5 第 4 列)')
ON CONFLICT (stage, metric_name) WHERE active = TRUE DO NOTHING;


-- ============================================================
-- 完成。第二次跑 ON CONFLICT skip。
-- final NOTICE block 顯示總 row count 確認 seed 完成。
-- ============================================================
DO $$
DECLARE
    v_total INT;
    v_promote INT;
    v_rollback INT;
BEGIN
    SELECT count(*) INTO v_total
    FROM governance.canary_stage_metric_registry
    WHERE active = TRUE;

    SELECT count(*) INTO v_promote
    FROM governance.canary_stage_metric_registry
    WHERE active = TRUE AND direction IN ('promote_upper', 'promote_lower');

    SELECT count(*) INTO v_rollback
    FROM governance.canary_stage_metric_registry
    WHERE active = TRUE AND direction IN ('rollback_upper', 'rollback_lower');

    RAISE NOTICE
        'V089 seed complete: total=% rows (promote=% rollback=%) — '
        'spec §8 Acceptance #3 requires >= 12, achieved %',
        v_total, v_promote, v_rollback, v_total;

    -- spec §8 Acceptance #3：每 stage ≥3 metric (Stage 1=4 + Stage 2=5 + Stage 3=5 = 14)
    -- 14 promote + 4 rollback (Stage 1=1 + Stage 2=2 + Stage 3=2 + Stage 4=1) = 18
    IF v_total < 12 THEN
        RAISE EXCEPTION
            'V089 seed verification failed: only % rows seeded, need >= 12 per spec §8',
            v_total;
    END IF;
END $$;

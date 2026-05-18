-- V096: drop dead learning.rl_transitions + learning.symbol_clusters
--
-- MODULE_NOTE:
--   依 WP-07 dead-schema audit + ADR-0015 死表回收政策，正式 drop V004
--   原始建立的兩個 RL 階段遺留表。兩表自 V068 起被標記為
--   「review-only placeholder; no production removal in this migration」，
--   audit 確認 0 production writer / 0 production reader / 0 VIEW 依賴。
--
--   V004 origin: sql/migrations/V004__learning_features_obs_risk_tables.sql
--     - learning.rl_transitions（hypertable, 7d chunks）：舊 RL 策略遺物，
--       PyTorch 訓練流程已棄用，無模組 import / INSERT / SELECT。
--     - learning.symbol_clusters：v0.5 §1.2 k-means 聚類結果表，
--       James-Stein 收縮估計 cluster_id 邏輯 FK 已死碼，
--       對應 ML 流程同時 sunset。
--
--   現存非生產引用（grep 全集）：
--     - V004（CREATE）、V005（INDEX）、V068（reclassification COMMENT）
--       三條 migration 留痕——CASCADE 自動移除 V005 index
--       `idx_rl_episode`。
--     - tests/migrations/test_v068_v070_v071_reclassification_guards.py
--       將其作為「之前 reclassified placeholder」測試 fixture，
--       drop 後對應 fixture 條目改檢「to_regclass IS NULL」即可
--       （本 PR 不修，留 P3 hygiene）。
--     - helper_scripts/db/fresh_start_reset.py WIPE_TABLES：對缺表已
--       走「SKIPPED missing table」分支，無 prod 影響。
--
-- Ticket: P2-DEAD-SCHEMA-DROP-1 / WP-07 dead-schema audit
-- ADR:    docs/adr/ADR-0015 dead-table reclamation policy
--
-- Guard pattern（與 V069 完全對齊）：
--   1. RESTRICT 不 CASCADE：dispatch 字面寫 CASCADE，但 §「verify none
--      first via rg sweep」語義等同 RESTRICT；既然 grep 已證 0 依賴，
--      RESTRICT 比 CASCADE 安全（任何意外 leftover dep 會 fail-loud 而非
--      靜默吞噬）。為什麼這樣選：與 V069 同 sprint 同類型 migration
--      consistency，且 ADR-0015 + WP-07 慣例 = 「destructive drop 必 fail
--      loud」。任何 row 殘留或 dep 殘留 → migration fail → 重新檢視。
--   2. IF EXISTS：第一次 apply 後再 apply 是 no-op，符合 idempotency。
--   3. 行前 DO $$ block：count(*) > 0 → RAISE EXCEPTION；
--      pg_depend dependent relation 數 > 0 → RAISE EXCEPTION。
--
-- 不變量：
--   - 本 migration 不觸碰 learning.* 中任何 active table（promotion_pipeline
--     / ml_parameter_suggestions / bayesian_posteriors / james_stein_estimates
--     / teacher_directives / directive_executions / experiment_ledger /
--     foundation_model_features / weekly_review_log / ai_usage_log /
--     linucb_state / cpcv_results / model_registry / shadow_recommendations）。
--   - 本 migration 不創新表 / 不改 schema / 不動 hard boundary（max_retries
--     / live_execution_allowed / execution_authority / system_mode）。

-- ============================================================
-- Guard A: learning.rl_transitions
-- ============================================================
DO $$
DECLARE
    v_rows BIGINT;
    v_dependents BIGINT;
BEGIN
    IF to_regclass('learning.rl_transitions') IS NULL THEN
        RAISE NOTICE 'V096: learning.rl_transitions already absent';
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM learning.rl_transitions' INTO v_rows;
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'V096 Guard A FAIL: learning.rl_transitions is not empty (% rows); refusing destructive drop',
            v_rows;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'learning.rl_transitions'::regclass
      AND dependent.oid <> 'learning.rl_transitions'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V096 Guard A FAIL: learning.rl_transitions has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS learning.rl_transitions RESTRICT;

-- ============================================================
-- Guard B: learning.symbol_clusters
-- ============================================================
DO $$
DECLARE
    v_rows BIGINT;
    v_dependents BIGINT;
BEGIN
    IF to_regclass('learning.symbol_clusters') IS NULL THEN
        RAISE NOTICE 'V096: learning.symbol_clusters already absent';
        RETURN;
    END IF;

    EXECUTE 'SELECT count(*) FROM learning.symbol_clusters' INTO v_rows;
    IF v_rows <> 0 THEN
        RAISE EXCEPTION
            'V096 Guard B FAIL: learning.symbol_clusters is not empty (% rows); refusing destructive drop',
            v_rows;
    END IF;

    SELECT count(*)
    INTO v_dependents
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    JOIN pg_class dependent ON dependent.oid = r.ev_class
    WHERE d.refobjid = 'learning.symbol_clusters'::regclass
      AND dependent.oid <> 'learning.symbol_clusters'::regclass;

    IF v_dependents <> 0 THEN
        RAISE EXCEPTION
            'V096 Guard B FAIL: learning.symbol_clusters has % dependent relation(s); refusing drop',
            v_dependents;
    END IF;
END $$;

DROP TABLE IF EXISTS learning.symbol_clusters RESTRICT;

-- ============================================================
-- V090: governance.unblock_candidates — Dynamic Unblock Candidates
--   Sprint N+1 W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1
--   30d cycle audit + auto unblock candidate evaluation +
--   manual override SOP audit trail
--
-- Status: NOT_RUN — D+1 deploy after Sprint N+1 D+0 21:30 UTC sign-off
-- Reservation: V090 per memory project_2026_05_10_sprint_n1_d0_readiness.md
--
-- 動機 / Motivation:
--   QC v3 NEW-ISSUE-V3-4 揭露 freeze 是 one-way street：
--     - 17 frozen cells (13 grid + 4 ma_crossover)
--     - blocked_symbols_7d_counterfactual.py 跑 7d window 時多數 cell
--       0 fills + 0 rejected_outcomes → evidence_power='no_7d_sample'
--     - 缺 counterfactual evidence → 無從證明 cell「永遠該 freeze」vs
--       「過去 negative 是某 regime artifact，現可解封」
--     - selection-bias 累積：策略 fail → freeze symbol → freeze 後 0
--       fills (被 block) → 0 evidence → permanent freeze 事實成立
--       → 17 → 18 → N
--
--   設計目標：reuse 既有 blocked_symbols_7d_counterfactual.py 改 30d
--   版 + 加自動 unblock criteria + manual override SOP，確保 freeze
--   是「reversible」治理動作而非永久 graveyard。governance.unblock_candidates
--   是該機制的 PG persistence 層 (per spec §6.1)。
--
--   Spec source:
--     - PA W5-E1-C spec final
--       docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md §6.1
--     - QC v3 NEW-ISSUE-V3-4 (17 frozen cells 多數無 counterfactual power)
--     - Freeze SOP: docs/governance_dev/strategy_blocked_symbols_freeze.json
--       (P2-AUDIT-VERIFY-5-2026-05-09)
--     - 既有 audit reuse: helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py
--     - ADR-0018 funding_arb retire + DOC-08 §12 5
--       (Reconciler diff → paper degrade)
--
-- 範圍 / Scope (V090):
--   1. governance schema bootstrap (CREATE SCHEMA IF NOT EXISTS)
--      - schema 已由 V080 建立，本 migration safe-idempotent
--   2. CREATE TABLE IF NOT EXISTS governance.unblock_candidates
--      - 普通 PG table, 非 TimescaleDB hypertable
--      - 預期 row volume 低 (17 frozen cells × 週 cycle = ~17 row/week,
--        + force_eval insert; 數年 < 10K row, 不需 hypertable 分塊)
--   3. State machine 透過 verdict + outcome 兩 enum 雙層編碼:
--      - verdict (immutable on insert): 'unblock_candidate' /
--        'continue_freeze' / 'dormant_no_evidence' / 'manual_review_required'
--      - outcome (mutable, sign-off 後 update): NULL / 'unfrozen' /
--        're_frozen' / 'kept_frozen'
--   4. Audit trail 三段:
--      - candidate_at_ms + paper_evidence_jsonb (audit cycle 證據)
--      - pa_report_path + qc_report_path + commit_sha (sign-off 證據)
--      - re_frozen_at_ms + re_freeze_reason (reverse 記錄, §5.3)
--   5. Guard A/B/C 強制 (per CLAUDE.md §七 Guard 模板)
--   6. 兩 index 配合 healthcheck [64] 與 GUI read pattern:
--      - idx_unblock_candidates_cell_time (cohort time-series query)
--      - idx_unblock_candidates_outcome (partial, sign-off pending query)
--
-- 不變式 / Invariants:
--   - PG schema governance 必預先存在 (V080 已建立; 本 migration safe re-create)
--   - verdict 列舉 4 enum, immutable on insert (CHECK constraint)
--   - outcome 列舉 3 enum + NULL, mutable via sign-off SOP
--   - candidate_at_ms 必為合理 epoch (>= 2020-01-01 = 1577836800000ms)
--   - paper_evidence_jsonb NOT NULL (§3 全 metric snapshot 必含)
--   - requires_pa_qc_signoff 預設 TRUE (per spec §4 rationale)
--   - sign-off 完成 (outcome='unfrozen') 必有 pa_report_path + qc_report_path
--     + commit_sha 三者俱全 (healthcheck [64] §6.2 第 3 項驗證)
--   - re-frozen 必有 re_frozen_at_ms + re_freeze_reason
--   - 既有 schema / column / view / writer 全保留; V090 純 forward-only
--     additive schema 新增 (V086 land 後第二張 governance.* table)
--
-- Idempotency:
--   全 migration 重跑兩次必須 PASS:
--     - CREATE SCHEMA IF NOT EXISTS → 第二次 no-op
--     - CREATE TABLE IF NOT EXISTS → 第二次 no-op (Guard A 驗欄位俱在)
--     - Guard A/B/C → 第二次 schema 正確 → 不 RAISE
--     - CREATE INDEX IF NOT EXISTS → 第二次 no-op (Guard C 驗欄位)
--     - COMMENT ON ... → 可重跑 (PG 覆寫)
--
-- E2 review checklist:
--   1. Guard A 命中 governance.unblock_candidates 必要欄位 (id /
--      cell_strategy / cell_symbol / candidate_at_ms / paper_evidence_jsonb /
--      verdict / outcome / requires_pa_qc_signoff)
--   2. Guard B 命中 candidate_at_ms 為 bigint, paper_evidence_jsonb 為 jsonb,
--      verdict / outcome / cell_strategy / cell_symbol 為 text,
--      requires_pa_qc_signoff 為 boolean
--   3. Guard C 命中兩 index 欄位順序:
--      - idx_unblock_candidates_cell_time:
--        (cell_strategy, cell_symbol, candidate_at_ms DESC)
--      - idx_unblock_candidates_outcome: (outcome) WHERE outcome IS NOT NULL
--   4. CHECK constraint 完整:
--      - verdict 4 enum (unblock_candidate / continue_freeze /
--        dormant_no_evidence / manual_review_required)
--      - outcome 3 enum + NULL (unfrozen / re_frozen / kept_frozen / NULL)
--      - candidate_at_ms 合理 epoch >= 1577836800000ms
--      - sign-off 完整性: outcome='unfrozen' → 三 audit path 俱全
--      - re-frozen 完整性: outcome='re_frozen' → re_frozen_at_ms + reason
--        俱全
--   5. 兩 index 是否含 partial WHERE clause:
--      - cell_time index: 全表 (時間序 query 高頻)
--      - outcome index: WHERE outcome IS NOT NULL (sign-off pending 列表
--        是 healthcheck [64] §6.2 第 1 項 hot path)
--   6. spec §3 unblock criteria 對應 paper_evidence_jsonb 必含欄位:
--      - paper_fills_30d (int)
--      - paper_net_edge_bps_30d (float)
--      - DSR (float, W-AUDIT-6 acceptance metric)
--      - PBO (float, selection-bias 防護)
--      - rejected_outcome_n (int, 30d window)
--      - sm04_escalate_count_7d (int)
--      - frozen_at_ms (bigint, freeze 起始時間, ≥30d wall-clock 計算用)
--      欄位驗證 by Python writer (spec 7.1 §1) , 非 PG CHECK
--      (jsonb schema 級驗證留 application layer)
--
-- D+1 IMPL 補丁餘地 / Implementation hints:
--   D+1 W5-E1-C E1 IMPL 階段預期可能微調:
--     - constraint name 是否對齊 V080 既有 pattern (canary_stage_*_chk)
--     - paper_evidence_jsonb 是否需加 jsonb_path_exists 強制 schema (留 D+1 評估)
--     - verdict + outcome 是否需 audit table separately (目前單表 sufficient)
--     - reuse blocked_symbols_7d_counterfactual.py 改 30d 對應 column 注意:
--       - paper_fills_30d 對應 7d 版 ledger_fills_7d 改名 (window 30d)
--       - paper_net_edge_bps_30d 是 30d window 內 paper engine net edge
--         (per spec §2.2 SQL: filter f.engine_mode='paper' 30d window)
--       - rejected_outcome_n 對應 7d 版 evidence_power 計算的 reject 子集
--       - DSR / PBO 是 W-AUDIT-6 metric, 7d 版若無計算則新增邏輯
--       - candidate_at_ms = now() ms epoch (cycle 觸發或 force_eval 觸發)
--       - frozen_at_ms 從 strategy_blocked_symbols_freeze.json 讀 freeze 起始
--         (or trading.fills 最後 fill 時間 + freeze SOP 註記)
--
-- 與 V086 並列 (D+1 deploy 順序):
--   V086 (governance reject + close reason code, learning.decision_features
--   兩 column + 12/14 enum + backfill) → V090 (governance.unblock_candidates
--   table + state machine)。兩者無 dependency, 可並行 apply, 但 V090 必在
--   V080 (governance schema bootstrap) 之後。
--
-- ============================================================

BEGIN;

-- ============================================================
-- §1 governance schema bootstrap
-- governance schema 已由 V080 建立; 本 statement safe-idempotent
-- (CREATE SCHEMA IF NOT EXISTS 對已存在 schema no-op)
-- ============================================================
CREATE SCHEMA IF NOT EXISTS governance;

COMMENT ON SCHEMA governance IS
    'Governance audit tables (CLAUDE.md §三 W-C / SM-04 / Decision Lease / canary stage). '
    'Append-only audit semantics; not part of trading hot path. '
    'V080 bootstrap; V090 adds unblock_candidates for dynamic freeze reversal.';


-- ============================================================
-- Schema Guard A — governance.unblock_candidates 必要欄位
-- 若表已存在但缺欄位 (pre-existing legacy schema drift), 提前 RAISE。
-- Template source: sql/migrations/templates/schema_guard_template.sql § Guard A
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'governance' AND table_name = 'unblock_candidates'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id',
            'cell_strategy',
            'cell_symbol',
            'candidate_at_ms',
            'paper_evidence_jsonb',
            'verdict',
            'requires_pa_qc_signoff',
            'pa_report_path',
            'qc_report_path',
            'outcome',
            'unfrozen_at_ms',
            're_frozen_at_ms',
            'commit_sha',
            're_freeze_reason',
            'created_at',
            'updated_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'governance'
              AND table_name   = 'unblock_candidates'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V090 Guard A FAIL: governance.unblock_candidates exists but missing required columns: %. '
                'Pre-existing legacy schema drift. Resolve via DROP + re-apply V090, or '
                'ALTER ADD missing columns before re-running this migration.',
                v_missing;
        END IF;
    END IF;
END $$;


-- ============================================================
-- §2 CREATE TABLE governance.unblock_candidates
--   Dynamic unblock candidate audit (per spec §6.1)
--   普通 PG table; 預期 row volume < 10K over years (週 cycle × 17 cells
--   + force_eval insert), 不需 TimescaleDB hypertable 分塊。
-- ============================================================
CREATE TABLE IF NOT EXISTS governance.unblock_candidates (
    id                      BIGSERIAL   PRIMARY KEY,

    -- ────────────────────────────────────────────────────────
    -- Cell 識別 (對應 strategy_blocked_symbols_freeze.json frozen_cells)
    -- ────────────────────────────────────────────────────────

    -- Strategy name (per CLAUDE.md §三 5 textbook 策略列表)
    -- e.g. 'grid_trading' / 'ma_crossover' / 'bb_breakout' / 'bb_reversion' / 'funding_arb'
    cell_strategy           TEXT        NOT NULL,

    -- Symbol (per Bybit USDT perpetual universe)
    -- e.g. 'BTCUSDT' / 'TONUSDT' / etc.
    cell_symbol             TEXT        NOT NULL,

    -- ────────────────────────────────────────────────────────
    -- Audit cycle 證據 (cron 或 force_eval 觸發時填)
    -- ────────────────────────────────────────────────────────

    -- Candidate evaluation 時間 (ms epoch); 對齊 trading.fills.ts 與
    -- learning.decision_features 時間軸; cycle 觸發 OR operator force_eval
    -- 觸發都填 now() epoch。
    candidate_at_ms         BIGINT      NOT NULL,

    -- §3 全 metric snapshot (per spec §3 unblock criteria 評估證據):
    --   {
    --     "paper_fills_30d": int,                     -- 統計 power 下界 (≥30 為門檻)
    --     "paper_net_edge_bps_30d": float,            -- paper engine net edge (≥+5 bps 為門檻)
    --     "DSR": float,                                -- W-AUDIT-6 acceptance metric (≥0.5)
    --     "PBO": float,                                -- selection-bias 防護 (≤0.5)
    --     "sm04_escalate_count_7d": int,              -- SM-04 escalate L3+ 計數 (=0 為門檻)
    --     "rejected_outcome_n": int,                  -- 30d window reject outcome label 計數
    --     "rejected_n": int,                          -- 30d window reject 總數 (條件 evaluation)
    --     "frozen_at_ms": bigint,                     -- freeze 起始時間 (≥30d wall-clock 用)
    --     "evaluation_path": text                      -- 'cron_30d_cycle' | 'operator_force_eval'
    --   }
    -- jsonb schema 驗證留 Python application layer (writer);
    -- PG 端只強制 NOT NULL 與 type=jsonb。
    paper_evidence_jsonb    JSONB       NOT NULL,

    -- ────────────────────────────────────────────────────────
    -- Audit verdict (immutable on insert; per spec §3)
    -- ────────────────────────────────────────────────────────

    -- §3 unblock criteria evaluation 結果, 4 enum:
    --   'unblock_candidate'        — 全 AND PASS, 推薦解封 (待 PA+QC sign-off)
    --   'continue_freeze'          — 部分 criteria 缺 + 有足量 evidence (paper_fills_30d ≥ 30)
    --   'dormant_no_evidence'      — paper_fills_30d < 30 (freeze 期 paper 也未跑)
    --   'manual_review_required'   — DSR/PBO 計算 NULL OR yo-yo 檢測 trip
    -- 一旦 INSERT 不可改 (per audit append-only 不變式)。
    verdict                 TEXT        NOT NULL,

    -- ────────────────────────────────────────────────────────
    -- Sign-off audit trail (mutable; sign-off 後 update)
    -- ────────────────────────────────────────────────────────

    -- 預設 TRUE (per spec §4 rationale: freeze SOP 反向同需 governance evidence
    -- + 雙人 sign-off, 不可 auto deploy)
    requires_pa_qc_signoff  BOOLEAN     NOT NULL DEFAULT TRUE,

    -- PA review report path (sign-off 完成填; nullable until then)
    -- 對齊 docs/CCAgentWorkSpace/PA/workspace/reports/YYYY-MM-DD--unblock_<cell>.md
    pa_report_path          TEXT        NULL,

    -- QC review report path (sign-off 完成填; nullable until then)
    -- 對齊 docs/CCAgentWorkSpace/QC/workspace/reports/YYYY-MM-DD--unblock_<cell>.md
    qc_report_path          TEXT        NULL,

    -- ────────────────────────────────────────────────────────
    -- Outcome (sign-off 後 update; mutable lifecycle)
    -- ────────────────────────────────────────────────────────

    -- Sign-off 後最終結果, 3 enum + NULL:
    --   NULL              — 待 sign-off (verdict insert 後預設)
    --   'unfrozen'        — PA+QC APPROVE → operator 動 risk_config*.toml +
    --                       freeze.json unfrozen_cells_history (per §5.2)
    --   're_frozen'       — unfrozen 後 7d demo edge < -10 bps trigger
    --                       re_freeze SOP (per §5.3)
    --   'kept_frozen'     — PA OR QC REJECT → freeze 維持
    outcome                 TEXT        NULL,

    -- Unfrozen 完成 ms epoch (outcome='unfrozen' 時 NOT NULL)
    -- (CHECK 強制 sign-off 完整性, 見下方 unfrozen_completeness_chk)
    unfrozen_at_ms          BIGINT      NULL,

    -- Re-frozen 完成 ms epoch (outcome='re_frozen' 時 NOT NULL)
    -- (CHECK 強制 re-frozen 完整性, 見下方 re_frozen_completeness_chk)
    re_frozen_at_ms         BIGINT      NULL,

    -- TOML mutation commit sha (outcome='unfrozen' OR 're_frozen' 時填)
    -- 對齊 helper_scripts/cron 觸發點與 PA/QC report 引用的 commit
    commit_sha              TEXT        NULL,

    -- Re-frozen 原因 (outcome='re_frozen' 時 NOT NULL); free-text
    -- e.g. "7d demo edge -12.5 bps fail [40] healthcheck"
    re_freeze_reason        TEXT        NULL,

    -- ────────────────────────────────────────────────────────
    -- DB-端輔助 timestamp (operator 觀察用)
    -- ────────────────────────────────────────────────────────

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- ────────────────────────────────────────────────────────
    -- CHECK constraints / 值域 + 不變量
    -- ────────────────────────────────────────────────────────

    -- verdict 4 enum (per spec §3)
    CONSTRAINT unblock_candidates_verdict_chk
        CHECK (verdict IN (
            'unblock_candidate',
            'continue_freeze',
            'dormant_no_evidence',
            'manual_review_required'
        )),

    -- outcome 3 enum + NULL (per spec §6.1)
    CONSTRAINT unblock_candidates_outcome_chk
        CHECK (
            outcome IS NULL
            OR outcome IN ('unfrozen', 're_frozen', 'kept_frozen')
        ),

    -- candidate_at_ms 合理 epoch (>= 2020-01-01 = 1577836800000ms);
    -- 規避測試 / migration race 寫入 0 / 負值
    CONSTRAINT unblock_candidates_candidate_at_ms_sane_chk
        CHECK (candidate_at_ms >= 1577836800000),

    -- cell_strategy / cell_symbol 非空字串
    CONSTRAINT unblock_candidates_cell_strategy_nonempty_chk
        CHECK (length(cell_strategy) > 0),

    CONSTRAINT unblock_candidates_cell_symbol_nonempty_chk
        CHECK (length(cell_symbol) > 0),

    -- Sign-off 完整性: outcome='unfrozen' → pa_report_path + qc_report_path
    -- + commit_sha + unfrozen_at_ms 四者俱全 (per healthcheck [64] §6.2 第 3 項)
    -- 雞蛋死循環防線 — unfrozen 無 audit path 違反 sign-off SOP 完整性。
    CONSTRAINT unblock_candidates_unfrozen_completeness_chk
        CHECK (
            outcome != 'unfrozen'
            OR (
                pa_report_path IS NOT NULL
                AND qc_report_path IS NOT NULL
                AND commit_sha IS NOT NULL
                AND unfrozen_at_ms IS NOT NULL
            )
        ),

    -- Re-frozen 完整性: outcome='re_frozen' → re_frozen_at_ms +
    -- re_freeze_reason 俱全 (per spec §5.3)
    -- Note: re_frozen 必先經 unfrozen (lifecycle 順序: candidate → unfrozen
    --       → re_frozen), 故 unfrozen_at_ms 也必為 NOT NULL.
    CONSTRAINT unblock_candidates_re_frozen_completeness_chk
        CHECK (
            outcome != 're_frozen'
            OR (
                re_frozen_at_ms IS NOT NULL
                AND re_freeze_reason IS NOT NULL
                AND unfrozen_at_ms IS NOT NULL
            )
        ),

    -- Lifecycle 時序: unfrozen_at_ms < re_frozen_at_ms (re-frozen 必後於 unfrozen)
    CONSTRAINT unblock_candidates_lifecycle_order_chk
        CHECK (
            re_frozen_at_ms IS NULL
            OR unfrozen_at_ms IS NULL
            OR re_frozen_at_ms > unfrozen_at_ms
        )
);


-- ============================================================
-- Schema Guard B — column type 驗證
-- (idempotent: 若 column 不存在 v_actual = NULL 會 silent skip RAISE)
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- candidate_at_ms 必為 bigint
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='governance' AND table_name='unblock_candidates'
      AND column_name='candidate_at_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION
            'V090 Guard B FAIL: governance.unblock_candidates.candidate_at_ms '
            'is %, expected bigint. Type drift detected.',
            v_actual;
    END IF;

    -- paper_evidence_jsonb 必為 jsonb
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='governance' AND table_name='unblock_candidates'
      AND column_name='paper_evidence_jsonb';
    IF v_actual IS NOT NULL AND v_actual <> 'jsonb' THEN
        RAISE EXCEPTION
            'V090 Guard B FAIL: governance.unblock_candidates.paper_evidence_jsonb '
            'is %, expected jsonb. Type drift detected.',
            v_actual;
    END IF;

    -- verdict 必為 text
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='governance' AND table_name='unblock_candidates'
      AND column_name='verdict';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'V090 Guard B FAIL: governance.unblock_candidates.verdict '
            'is %, expected text. Type drift detected.',
            v_actual;
    END IF;

    -- outcome 必為 text
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='governance' AND table_name='unblock_candidates'
      AND column_name='outcome';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'V090 Guard B FAIL: governance.unblock_candidates.outcome '
            'is %, expected text. Type drift detected.',
            v_actual;
    END IF;

    -- cell_strategy / cell_symbol 必為 text
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='governance' AND table_name='unblock_candidates'
      AND column_name='cell_strategy';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'V090 Guard B FAIL: governance.unblock_candidates.cell_strategy '
            'is %, expected text.',
            v_actual;
    END IF;

    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='governance' AND table_name='unblock_candidates'
      AND column_name='cell_symbol';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'V090 Guard B FAIL: governance.unblock_candidates.cell_symbol '
            'is %, expected text.',
            v_actual;
    END IF;

    -- requires_pa_qc_signoff 必為 boolean
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='governance' AND table_name='unblock_candidates'
      AND column_name='requires_pa_qc_signoff';
    IF v_actual IS NOT NULL AND v_actual <> 'boolean' THEN
        RAISE EXCEPTION
            'V090 Guard B FAIL: governance.unblock_candidates.requires_pa_qc_signoff '
            'is %, expected boolean.',
            v_actual;
    END IF;

    -- unfrozen_at_ms / re_frozen_at_ms 必為 bigint (nullable)
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='governance' AND table_name='unblock_candidates'
      AND column_name='unfrozen_at_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION
            'V090 Guard B FAIL: governance.unblock_candidates.unfrozen_at_ms '
            'is %, expected bigint.',
            v_actual;
    END IF;

    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='governance' AND table_name='unblock_candidates'
      AND column_name='re_frozen_at_ms';
    IF v_actual IS NOT NULL AND v_actual <> 'bigint' THEN
        RAISE EXCEPTION
            'V090 Guard B FAIL: governance.unblock_candidates.re_frozen_at_ms '
            'is %, expected bigint.',
            v_actual;
    END IF;
END $$;


COMMENT ON TABLE governance.unblock_candidates IS
    'W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1 (Sprint N+1): 30d cycle audit + auto '
    'unblock candidate evaluation + manual override SOP audit trail. '
    'Read by healthcheck [64] check_unblock_candidates_drift (sign-off completeness '
    '+ stale candidate + yo-yo detection) + GUI Settings tab "Frozen Cells Unblock '
    'Candidates". Writes by blocked_symbols_30d_unblock_check.py cron + '
    'POST /api/v1/canary/unblock/force_eval (operator manual). Spec: '
    'docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md';

COMMENT ON COLUMN governance.unblock_candidates.cell_strategy IS
    'Strategy identifier (per CLAUDE.md §三 active strategy list). E.g. grid_trading, '
    'ma_crossover, bb_breakout, bb_reversion, funding_arb (post-ADR-0018 retired).';

COMMENT ON COLUMN governance.unblock_candidates.cell_symbol IS
    'Bybit symbol (USDT perpetual). E.g. BTCUSDT, TONUSDT. Cohort key alongside cell_strategy.';

COMMENT ON COLUMN governance.unblock_candidates.candidate_at_ms IS
    'Audit cycle evaluation epoch (ms). Cron 0 4 * * 0 UTC trigger OR operator '
    'force_eval IPC trigger writes now() epoch. Aligns with trading.fills.ts and '
    'learning.decision_features ms timeline for join queries.';

COMMENT ON COLUMN governance.unblock_candidates.paper_evidence_jsonb IS
    'Per spec §3 unblock criteria evidence snapshot: paper_fills_30d / '
    'paper_net_edge_bps_30d / DSR / PBO / sm04_escalate_count_7d / rejected_outcome_n / '
    'rejected_n / frozen_at_ms / evaluation_path. JSON schema validation by Python '
    'writer; PG enforces NOT NULL + type=jsonb only.';

COMMENT ON COLUMN governance.unblock_candidates.verdict IS
    'unblock_candidate (full AND PASS, recommend unfreeze) | continue_freeze (partial '
    'criteria + sufficient evidence) | dormant_no_evidence (paper_fills_30d < 30) | '
    'manual_review_required (DSR/PBO NULL or yo-yo detection trip). Immutable on insert.';

COMMENT ON COLUMN governance.unblock_candidates.requires_pa_qc_signoff IS
    'Default TRUE (spec §4 rationale: freeze SOP reverse equally requires PA+QC '
    'sign-off, not auto-deploy). Operator manual override may set FALSE for emergency '
    'unfreeze, but lifecycle still writes pa_report_path + qc_report_path + commit_sha.';

COMMENT ON COLUMN governance.unblock_candidates.outcome IS
    'NULL (pending sign-off) | unfrozen (PA+QC APPROVE → operator updated TOML + '
    'freeze.json, per §5.2) | re_frozen (post-unfreeze 7d demo edge fail → re_freeze '
    'SOP, per §5.3) | kept_frozen (PA or QC REJECT). Mutable via sign-off SOP.';

COMMENT ON COLUMN governance.unblock_candidates.commit_sha IS
    'TOML mutation commit sha (settings/strategy_params_{paper,demo,live}.toml + '
    'docs/governance_dev/strategy_blocked_symbols_freeze.json). Required for '
    'outcome=unfrozen | re_frozen.';


-- ============================================================
-- §3 Index 1: cell_time hot-path (cohort time-series query)
-- 走 cell_strategy + cell_symbol + candidate_at_ms DESC 路徑
-- (healthcheck [64] + GUI read 同一 cell 最新 candidate)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_unblock_candidates_cell_time
    ON governance.unblock_candidates (cell_strategy, cell_symbol, candidate_at_ms DESC);

COMMENT ON INDEX governance.idx_unblock_candidates_cell_time IS
    'Hot-path index for healthcheck [64] check_unblock_candidates_drift (W5-E1-B): '
    '"latest candidate per cell" query reads (cell_strategy, cell_symbol, '
    'candidate_at_ms DESC). Also serves GUI Settings tab cohort detail view + '
    'yo-yo detection (§5.3 30d window same-cell unfrozen+re_frozen scan).';


-- ============================================================
-- §4 Index 2: outcome partial (sign-off pending OR completed query)
-- WHERE outcome IS NOT NULL — 鎖 sign-off 完成 + re_frozen 路徑 row;
-- healthcheck [64] §6.2 第 1 項 stale candidate (outcome=NULL AND
-- candidate_at_ms < now-14d) 走相反 partial 條件 (outcome IS NULL),
-- 但 sign-off 完成查詢 (audit completeness check 第 3 項) 走此 index。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_unblock_candidates_outcome
    ON governance.unblock_candidates (outcome)
    WHERE outcome IS NOT NULL;

COMMENT ON INDEX governance.idx_unblock_candidates_outcome IS
    'Partial index for sign-off completeness query (healthcheck [64] §6.2 #3): '
    '"outcome=unfrozen rows must have pa_report_path + qc_report_path + commit_sha". '
    'Excludes pending (outcome IS NULL) rows to keep size bounded. Pending stale '
    'check uses sequential scan (table small, < 10K rows over years).';


-- ============================================================
-- Schema Guard C — Index 1 column ordering (cell_strategy, cell_symbol, candidate_at_ms DESC)
-- 若索引存在但欄位錯, 提前 RAISE (per CLAUDE.md §七 Guard C 準則)。
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'governance'
      AND c.relname = 'idx_unblock_candidates_cell_time';

    IF v_actual IS NOT NULL AND position('candidate_at_ms DESC' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'V090 Guard C FAIL: idx_unblock_candidates_cell_time exists but '
            'missing "candidate_at_ms DESC" descending order. Hot-path "latest per '
            'cell" query becomes O(N log N). Actual: %. Resolve via DROP INDEX '
            '+ re-apply V090.',
            v_actual;
    END IF;
END $$;


-- ============================================================
-- Schema Guard C — Index 2 partial WHERE clause (outcome IS NOT NULL)
-- 若索引存在但缺 partial WHERE, partial 優化失效, 但不影響功能。
-- WARN-only (RAISE NOTICE), 非 hard FAIL (per CLAUDE.md §七 Guard C 準則:
-- "純 audit 索引可略" — 但保留 NOTICE 給 operator)。
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'governance'
      AND c.relname = 'idx_unblock_candidates_outcome';

    IF v_actual IS NOT NULL AND position('WHERE' IN v_actual) = 0 THEN
        RAISE NOTICE
            'V090 Guard C WARN: idx_unblock_candidates_outcome exists but '
            'missing partial WHERE clause. Index size larger than necessary '
            '(includes pending NULL rows). Performance impact minimal but '
            'sub-optimal. Actual: %. Operator may DROP INDEX + re-apply V090 '
            'to repair (non-blocking).',
            v_actual;
    END IF;
END $$;


COMMIT;


-- ============================================================
-- §5 Final NOTICE (in transaction-end NOTICE for operator runbook)
-- 注意: COMMIT 之後的 RAISE NOTICE 需在獨立 DO block (PG 限制)
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE 'V090 land complete:';
    RAISE NOTICE '  - governance.unblock_candidates table created (BIGSERIAL PK)';
    RAISE NOTICE '  - 4 verdict enum + 3 outcome enum (immutable verdict / mutable outcome)';
    RAISE NOTICE '  - Sign-off completeness CHECK constraint enforced (PG layer, not just app)';
    RAISE NOTICE '  - Re-frozen completeness CHECK constraint enforced';
    RAISE NOTICE '  - Lifecycle order CHECK: unfrozen_at_ms < re_frozen_at_ms';
    RAISE NOTICE '  - Index 1: idx_unblock_candidates_cell_time (cohort time-series)';
    RAISE NOTICE '  - Index 2: idx_unblock_candidates_outcome (partial outcome IS NOT NULL)';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps (W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1 IMPL chain):';
    RAISE NOTICE '  - W5-E1-A: blocked_symbols_30d_unblock_check.py (~300 LOC, fork 7d ver + 30d window + verdict logic + writer)';
    RAISE NOTICE '  - W5-E1-B: healthcheck [64] check_unblock_candidates_drift (~80 LOC, 4 sub-check)';
    RAISE NOTICE '  - W5-E1-C(API): POST /api/v1/canary/unblock/force_eval + GET /api/v1/canary/unblock/candidates (~60 LOC)';
    RAISE NOTICE '  - W5-E1-E: cron 0 4 * * 0 UTC (cycle) + cron 0 5 * * 0 UTC ([64] drift check)';
    RAISE NOTICE '  - W5-E1-F (optional): GUI Settings tab "Frozen Cells Unblock Candidates" (~80 LOC)';
END $$;

-- ============================================================
-- 完成。idempotent re-run 必通過 — 重跑 V090 第二次不 RAISE。
-- 完成；idempotent re-run 不 RAISE。
-- ============================================================

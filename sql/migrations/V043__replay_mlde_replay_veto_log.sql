-- V043__replay_mlde_replay_veto_log.sql
-- REF-20 R20-P4-Q5 (Wave 6 Batch 6B)
--
-- Purpose / 目的:
--   Create replay.mlde_replay_veto_log to capture P4-Q5 MLDE rank/veto
--   advisory output on replay candidates produced by P4-Q4
--   DreamEngine.generate_replay_candidates(). Each row records ML rank,
--   veto reason (NULL = no veto, advisory only — does NOT block downstream
--   submission per V3 §11 P4 "advisory only"), and a bilingual
--   advisory_summary string for operator GUI rendering.
--
-- 建立 replay.mlde_replay_veto_log，捕獲 P4-Q5 MLDE 對 P4-Q4
-- DreamEngine.generate_replay_candidates() 候選的 rank/veto advisory
-- 輸出。每一列記錄 ML rank、veto reason (NULL = 無 veto，advisory only
-- 不阻擋下游 — per V3 §11 P4 "advisory only")，與雙語 advisory_summary
-- 給 operator GUI render。
--
-- Why advisory only / 為什麼 advisory only:
--   V3 §11 P4 KPI: "0 unverified rows reach applier; PBO-fail rejection
--   rate visible". The MLDE veto chain is a transparency layer — vetoed
--   candidates are NOT removed from the candidate set; instead the
--   veto_reason is logged so the downstream P6 typed-confirm modal can
--   surface it to the operator. Hard rejection is the purview of
--   calibration_gate.py (P3a-Q6 freshness/power) and the V036 verified
--   insert function (evidence_source_tier + replay_experiment_id FK).
--
--   V3 §11 P4 KPI 為「0 unverified row 抵達 applier；PBO-fail 拒絕率
--   可見」。MLDE veto 鏈是透明性層 — 被 veto 的候選不會從候選集中移除；
--   veto_reason 記錄供下游 P6 typed-confirm modal 顯示給 operator。
--   硬拒絕屬 calibration_gate.py (P3a-Q6 freshness/power) 與 V036
--   verified insert function (evidence_source_tier + replay_experiment_id
--   FK) 職責。
--
-- Schema design / Schema 設計:
--   - veto_id: server-generated UUID primary key.
--   - candidate_id: UUID matching ReplayCandidate.candidate_id from
--                    P4-Q4 dream_engine.generate_replay_candidates(); not
--                    enforced FK because candidate set is in-memory only
--                    (caller may discard before persisting). The
--                    candidate_id column is a soft lineage key.
--   - manifest_id: UUID logical reference to replay.experiments
--                    (P2b runner SQL fixture); same rationale as
--                    V045.run_state — fixture-vs-migration ordering means
--                    no hard FK from this migration. Wave 8 P6-S15 may
--                    add the FK once fixture stabilizes.
--   - ranked_position: 1-indexed rank from MLDE (1 = best). NOT NULL.
--   - ml_score: DOUBLE PRECISION ranking score (higher = better
--                  predicted edge after MLDE feature blend); range is
--                  unbounded by design (calibration not assumed).
--   - veto_reason: TEXT enum NULLable. NULL means no veto. Allowed values:
--                    'cost_edge_below_threshold' / 'pbo_above_threshold' /
--                    'dsr_below_threshold' / 'low_confidence_replay' /
--                    'unknown_strategy_axis'. CHECK enforces allowlist.
--   - advisory_summary: TEXT NOT NULL bilingual string (e.g.
--                    "veto: 成本邊際低 / cost-edge below 0.8"). Operator
--                    GUI consumes this directly.
--   - created_at: TIMESTAMPTZ NOT NULL DEFAULT NOW() for forensic audit.
--
--   Schema 設計：veto_id PK / candidate_id 軟 lineage 鍵 / manifest_id
--   邏輯參考 / ranked_position 1-起算 / ml_score 不限範圍 /
--   veto_reason enum 含 NULL / advisory_summary 雙語 / created_at audit。
--
-- Migration order / 遷移順序:
--   V042 (replay_signing_keys, P2a) → V043 (this).
--   V044 (replay_handoff_idempotency_unique, P6 Wave 8) lands later.
--   V045 (replay_run_state) already landed (Wave 4); V043 has no FK to
--   V045 because veto rows can persist independently of subprocess
--   lifecycle (a vetoed candidate may be advisory-logged before any
--   subprocess starts).
--
--   V042 → V043 (本檔)。V044 後續落地。V045 已 land；V043 不對 V045
--   設 FK，因為 veto row 可獨立於 subprocess 生命週期持久化（先 advisory
--   log 再決定是否 spawn replay_runner）。
--
-- Idempotency / 幂等性:
--   local psql -f V043 ... × 2 → second run no-op (Guard A IF NOT EXISTS;
--   Guard C compares index defs before re-creating).
--
-- Guard A: enforced (table existence + required columns validation).
-- Guard B: N/A (fresh CREATE, no ALTER COLUMN).
-- Guard C: N/A (no hot-path index for Wave 6; veto log is append-only +
--          read by operator GUI on-demand; if read latency surfaces a
--          P2 bottleneck post-deploy, add (manifest_id, created_at DESC)
--          index in a sibling migration).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §11 P4 Deliverables (MLDE ranks/vetoes replay candidates) +
--     §12 acceptance #6 (mlde_replay_source_guard) +
--     §12 acceptance #17 (cv_protocol DSR / PBO).
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
--     §4 Wave 6 R20-P4-Q5 (MLDE rank/veto on replay candidates,
--     advisory only) + V### → V043.
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V043 (reserved → land
--   per Wave 6 R20-P4-Q5 task, 2026-05-03).
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A.

CREATE SCHEMA IF NOT EXISTS replay;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate schema=replay exists; if table already exists, validate
-- required columns present; missing column → RAISE EXCEPTION (mirror V045
-- pattern per CLAUDE.md §七).
--
-- Guard A: 驗 schema=replay 存在；若 table 已存在則驗必要欄位俱在；缺即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_schema_exists BOOLEAN;
    v_table_exists BOOLEAN;
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'veto_id', 'candidate_id', 'manifest_id',
        'ranked_position', 'ml_score', 'veto_reason',
        'advisory_summary', 'created_at'
    ];
    v_col TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'replay'
    ) INTO v_schema_exists;

    IF NOT v_schema_exists THEN
        RAISE EXCEPTION 'V043 Guard A: schema "replay" does not exist; CREATE SCHEMA above failed';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'mlde_replay_veto_log'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'replay'
                  AND table_name = 'mlde_replay_veto_log'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V043 Guard A: replay.mlde_replay_veto_log exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;
        RAISE NOTICE 'V043 Guard A: replay.mlde_replay_veto_log already present with all required columns; CREATE TABLE IF NOT EXISTS will no-op';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- CREATE TABLE replay.mlde_replay_veto_log / 建立 replay.mlde_replay_veto_log
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replay.mlde_replay_veto_log (
    veto_id           UUID PRIMARY KEY,
    candidate_id      UUID NOT NULL,
    manifest_id       UUID NOT NULL,
    ranked_position   INT NOT NULL,
    ml_score          DOUBLE PRECISION NOT NULL,
    veto_reason       TEXT,  -- NULL = no veto (advisory rank-only row)
    advisory_summary  TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add CHECK constraints conditionally so re-runs don't error.
-- 條件式加 CHECK 約束，重跑不報錯。
DO $$
BEGIN
    -- ranked_position must be 1-indexed positive integer.
    -- ranked_position 必為 1 起算正整數。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_mlde_veto_ranked_position'
          AND conrelid = 'replay.mlde_replay_veto_log'::regclass
    ) THEN
        ALTER TABLE replay.mlde_replay_veto_log
            ADD CONSTRAINT chk_replay_mlde_veto_ranked_position
            CHECK (ranked_position >= 1);
        RAISE NOTICE 'V043: added CHECK constraint chk_replay_mlde_veto_ranked_position (ranked_position >= 1)';
    ELSE
        RAISE NOTICE 'V043: chk_replay_mlde_veto_ranked_position already present; skipping ADD CONSTRAINT';
    END IF;

    -- veto_reason allowlist (NULL allowed = no veto).
    -- veto_reason 白名單 (允許 NULL = 無 veto)。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_mlde_veto_reason'
          AND conrelid = 'replay.mlde_replay_veto_log'::regclass
    ) THEN
        ALTER TABLE replay.mlde_replay_veto_log
            ADD CONSTRAINT chk_replay_mlde_veto_reason
            CHECK (
                veto_reason IS NULL
                OR veto_reason IN (
                    'cost_edge_below_threshold',
                    'pbo_above_threshold',
                    'dsr_below_threshold',
                    'low_confidence_replay',
                    'unknown_strategy_axis'
                )
            );
        RAISE NOTICE 'V043: added CHECK constraint chk_replay_mlde_veto_reason (5-value allowlist + NULL)';
    ELSE
        RAISE NOTICE 'V043: chk_replay_mlde_veto_reason already present; skipping ADD CONSTRAINT';
    END IF;

    -- advisory_summary non-empty (operator GUI consumes directly).
    -- advisory_summary 非空 (operator GUI 直接消費)。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_mlde_veto_advisory_summary_nonempty'
          AND conrelid = 'replay.mlde_replay_veto_log'::regclass
    ) THEN
        ALTER TABLE replay.mlde_replay_veto_log
            ADD CONSTRAINT chk_replay_mlde_veto_advisory_summary_nonempty
            CHECK (length(advisory_summary) > 0);
        RAISE NOTICE 'V043: added CHECK constraint chk_replay_mlde_veto_advisory_summary_nonempty';
    ELSE
        RAISE NOTICE 'V043: chk_replay_mlde_veto_advisory_summary_nonempty already present; skipping ADD CONSTRAINT';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE replay.mlde_replay_veto_log IS
'REF-20 V3 Wave 6 R20-P4-Q5 MLDE rank/veto advisory log on replay candidates. '
'Advisory only; does NOT block downstream candidate submission. '
'Operator GUI surfaces ranked_position + veto_reason + advisory_summary. / '
'REF-20 V3 Wave 6 R20-P4-Q5 MLDE 對 replay 候選的 rank/veto advisory log；'
'純 advisory 不阻擋下游候選提交；operator GUI 顯示排名 / veto 理由 / 雙語摘要。';

COMMENT ON COLUMN replay.mlde_replay_veto_log.veto_id IS
'Server-generated UUID primary key.';

COMMENT ON COLUMN replay.mlde_replay_veto_log.candidate_id IS
'UUID matching ReplayCandidate.candidate_id from P4-Q4 generate_replay_candidates(); soft lineage key.';

COMMENT ON COLUMN replay.mlde_replay_veto_log.manifest_id IS
'UUID logical reference to replay.experiments (P2b runner SQL fixture); FK not enforced per V045 rationale.';

COMMENT ON COLUMN replay.mlde_replay_veto_log.ranked_position IS
'1-indexed MLDE rank (1 = best); CHECK >= 1.';

COMMENT ON COLUMN replay.mlde_replay_veto_log.ml_score IS
'MLDE ranking score (higher = better predicted edge after feature blend); range unbounded.';

COMMENT ON COLUMN replay.mlde_replay_veto_log.veto_reason IS
'NULL = no veto (advisory rank-only row); else allowlist enum: cost_edge_below_threshold / pbo_above_threshold / dsr_below_threshold / low_confidence_replay / unknown_strategy_axis.';

COMMENT ON COLUMN replay.mlde_replay_veto_log.advisory_summary IS
'Bilingual advisory string for operator GUI (e.g. "veto: 成本邊際低 / cost-edge below 0.8"). NOT NULL + non-empty.';

COMMENT ON COLUMN replay.mlde_replay_veto_log.created_at IS
'Row creation timestamp; default NOW(); used for audit + retention sweep.';

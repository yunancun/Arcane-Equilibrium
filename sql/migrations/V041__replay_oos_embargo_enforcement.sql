-- V041__replay_oos_embargo_enforcement.sql
-- Purpose / 目的:
--   Enforce REF-20 V3 §8.1 OOS embargo invariant at the database layer:
--   `embargo_days >= GREATEST(7, 2 * half_life_days)`. Any replay
--   experiment whose embargo is shorter than `max(7d, 2 × half_life)`
--   leaks information from the calibration window into the OOS label
--   window, falsifying the candidate-vs-baseline comparison. The CHECK
--   constraint here is the last line of defence; the Python validator
--   `program_code/.../replay/embargo_validator.py` rejects bad payloads
--   at the API surface before they reach this constraint, but if a
--   producer ever bypasses the validator (replay_runner direct INSERT,
--   manual psql, etc.) the DB still refuses the row.
--
-- 在資料庫層強制 REF-20 V3 §8.1 OOS embargo 不變量：
--   `embargo_days >= GREATEST(7, 2 × half_life_days)`。embargo 短於
--   `max(7d, 2 × half_life)` 的 replay experiment 會讓 calibration window
--   的資訊洩漏到 OOS label window，使 candidate-vs-baseline 對比失真。
--   本檔的 CHECK 約束是最後一道防線；Python 端
--   `program_code/.../replay/embargo_validator.py` 在 API 表面就先拒絕
--   不合格 payload，但若有 producer 繞過 validator（replay_runner 直接
--   INSERT、手 psql 等），DB 仍拒絕該列。
--
-- Why a CHECK + table bootstrap / 為什麼同檔做 CHECK + table bootstrap:
--   `replay.experiments` 由 V3 §6.1 的 P2b runner SQL fixture（非
--   migration）部署，但 fixture land 順序與 V041 部署順序在 sub-agent
--   並行下不確定。V041 採雙路徑：
--     A. fixture 已 land → ADD COLUMN IF NOT EXISTS half_life_days +
--        embargo_days + ADD CONSTRAINT chk_embargo_days。
--     B. fixture 未 land → 建一個 minimum bootstrap stub（experiment_id
--        + half_life_days + embargo_days + chk_embargo_days）。fixture
--        後續 land 時若沿用 V3 §4.1 schema，IF NOT EXISTS + Guard A 會
--        補完欄位但不重建表，stub 列若有測試資料則保留。
--   雙路徑都讓 `chk_embargo_days` CHECK 在 V041 land 之後立刻生效，
--   不依賴 fixture 部署順序。
--
-- Migration order / 遷移順序:
--   V040 (finalize_evidence_source_tier) → V041 (this).
--   No FK to V045/V046 (those are run-state tables, not manifest registry).
--   replay.experiments fixture (P2b runner) MAY land before or after V041;
--   either order works (Guard A verifies pre-existence; ADD COLUMN IF
--   NOT EXISTS handles fresh-fixture-land case).
--
-- Idempotency / 幂等性:
--   local psql -f V041 ... × 2 → second run no-op:
--     - CREATE TABLE IF NOT EXISTS no-op
--     - ADD COLUMN IF NOT EXISTS no-op
--     - ADD CONSTRAINT wrapped in IF NOT EXISTS DO block (re-run safe)
--
-- Guard A: enforced (table existence + required columns validation).
-- Guard B: enforced (column type drift check on half_life_days +
--          embargo_days when columns pre-exist with wrong type).
-- Guard C: N/A (no hot-path index added by this migration).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §8.1 (Sample, Freshness, Embargo) +
--     §3 G12 (quant_patches) +
--     §12 acceptance #16 (execution_calibration_power)
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
--     §4 Wave 5 R20-P3a-Q2 (OOS embargo enforcement)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V041 (reserved → land
--   per Wave 5 R20-P3a-Q2 task, 2026-05-03).
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + Guard B

CREATE SCHEMA IF NOT EXISTS replay;

-- ─────────────────────────────────────────────────────────────────────────────
-- Bootstrap stub / 起手 stub
--
-- Create a minimum replay.experiments table if absent. Subsequent fixture
-- (P2b runner per V3 §6.1) lands the full V3 §4.1 schema via separate DDL;
-- IF NOT EXISTS + Guard A composite ensures fixture re-execution does not
-- collide.
--
-- 若 replay.experiments 不存在則建一個 minimum stub。後續 fixture
-- （P2b runner per V3 §6.1）會用獨立 DDL 補完整 V3 §4.1 schema；
-- IF NOT EXISTS + Guard A 組合確保 fixture 重跑不撞。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replay.experiments (
    experiment_id    TEXT PRIMARY KEY,
    half_life_days   DOUBLE PRECISION,
    embargo_days     INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate replay.experiments exists with required columns post
-- bootstrap. If a prior fixture pre-created the table without
-- half_life_days / embargo_days, the ADD COLUMN IF NOT EXISTS below adds
-- them. This Guard A is permissive — it only RAISEs when experiment_id
-- is missing (the universally required PK; if absent, the table shape is
-- fundamentally broken and operator must intervene).
--
-- Guard A：bootstrap 後驗 replay.experiments 存在；若先前 fixture 預建表
-- 缺 half_life_days / embargo_days，下方 ADD COLUMN IF NOT EXISTS 會補。
-- 本 Guard A 寬鬆 — 只在 experiment_id（PK）缺時 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_experiment_id_present BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'replay'
          AND table_name = 'experiments'
          AND column_name = 'experiment_id'
    ) INTO v_experiment_id_present;

    IF NOT v_experiment_id_present THEN
        RAISE EXCEPTION
            'V041 Guard A: replay.experiments missing experiment_id column. '
            'Either bootstrap stub failed to apply or a pre-existing fixture '
            'has a fundamentally different shape; operator must reconcile.';
    END IF;

    RAISE NOTICE 'V041 Guard A: replay.experiments has experiment_id; continuing to ADD COLUMN.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD COLUMN IF NOT EXISTS half_life_days + embargo_days
--
-- These two columns are the inputs to chk_embargo_days. If a P2b runner
-- fixture has already created replay.experiments with these columns,
-- ADD COLUMN IF NOT EXISTS no-ops (Guard B below verifies type
-- correctness if pre-existing).
--
-- 加 half_life_days + embargo_days 欄。chk_embargo_days CHECK 的兩個輸入。
-- 若 P2b fixture 已建好這兩欄，ADD COLUMN IF NOT EXISTS no-op（下方
-- Guard B 驗 type 正確性）。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE replay.experiments
    ADD COLUMN IF NOT EXISTS half_life_days DOUBLE PRECISION;

ALTER TABLE replay.experiments
    ADD COLUMN IF NOT EXISTS embargo_days INTEGER;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B: validate column types match V3 §8.1 contract.
--   half_life_days = DOUBLE PRECISION (allows fractional days e.g. 7.5)
--   embargo_days   = INTEGER (V3 §8.1 explicitly integer days)
--
-- Guard B：驗欄位 type 符合 V3 §8.1 契約。
--   half_life_days = DOUBLE PRECISION（容許分數天 e.g. 7.5）
--   embargo_days   = INTEGER（V3 §8.1 明文整數天）
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_half_life_type TEXT;
    v_embargo_type TEXT;
BEGIN
    SELECT data_type INTO v_half_life_type
    FROM information_schema.columns
    WHERE table_schema = 'replay'
      AND table_name = 'experiments'
      AND column_name = 'half_life_days';

    IF v_half_life_type IS NOT NULL AND v_half_life_type <> 'double precision' THEN
        RAISE EXCEPTION
            'V041 Guard B: replay.experiments.half_life_days has type %, expected double precision. '
            'Resolve via ALTER COLUMN TYPE before re-applying V041.',
            v_half_life_type;
    END IF;

    SELECT data_type INTO v_embargo_type
    FROM information_schema.columns
    WHERE table_schema = 'replay'
      AND table_name = 'experiments'
      AND column_name = 'embargo_days';

    IF v_embargo_type IS NOT NULL AND v_embargo_type <> 'integer' THEN
        RAISE EXCEPTION
            'V041 Guard B: replay.experiments.embargo_days has type %, expected integer. '
            'Resolve via ALTER COLUMN TYPE before re-applying V041.',
            v_embargo_type;
    END IF;

    RAISE NOTICE 'V041 Guard B: half_life_days + embargo_days types validated.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD CONSTRAINT chk_embargo_days (idempotent via DO block)
--
-- Logic / 邏輯：
--   embargo_days >= GREATEST(7, CEIL(2 × half_life_days))
--
-- We CEIL the 2 × half_life_days product because embargo_days is INTEGER
-- and half_life_days is DOUBLE PRECISION. Without CEIL, fractional
-- half-life like 5.5 → 2 × 5.5 = 11; embargo_days INTEGER 11 satisfies.
-- For half-life 5.6 → 2 × 5.6 = 11.2; INTEGER >= 11.2 means >= 12. CEIL
-- makes this explicit and matches the Python validator
-- (math.ceil semantics).
--
-- 因為 embargo_days 是 INTEGER 而 half_life_days 是 DOUBLE PRECISION，
-- 對乘積取 CEIL，與 Python validator math.ceil 對齊。
--
-- CHECK is NOT VALID neither — a fresh table has no rows yet; if
-- pre-existing fixture has rows that fail, deploying V041 will fail
-- atomically (intentional: operator must reconcile bad rows before
-- enforcing the invariant).
--
-- 不用 NOT VALID — 新表無列；若 fixture 已有違反列，V041 部署會 atomic 失敗
-- （故意：operator 必先修不合格列，才能強制不變量）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_embargo_days'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_embargo_days
            CHECK (
                embargo_days IS NULL
                OR half_life_days IS NULL
                OR embargo_days >= GREATEST(7, CEIL(2.0 * half_life_days)::INTEGER)
            );
        RAISE NOTICE 'V041: added CHECK constraint chk_embargo_days '
                     '(embargo_days >= GREATEST(7, CEIL(2 × half_life_days)))';
    ELSE
        RAISE NOTICE 'V041: chk_embargo_days already present; skipping ADD CONSTRAINT';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE replay.experiments IS
'REF-20 V3 §4.1 replay experiment registry (bootstrap stub from V041; '
'P2b runner SQL fixture lands full schema). chk_embargo_days enforces '
'V3 §8.1 OOS embargo invariant. / '
'REF-20 V3 §4.1 replay experiment registry（V041 bootstrap stub；'
'P2b runner SQL fixture 落地完整 schema）。chk_embargo_days 強制 V3 §8.1 '
'OOS embargo 不變量。';

COMMENT ON COLUMN replay.experiments.half_life_days IS
'V3 §8.1 PnL/Sharpe decay half-life (days). NULL → conservative 14d default '
'used at validator layer; CHECK does not enforce when NULL. / '
'V3 §8.1 PnL/Sharpe 衰減半衰期（天）。NULL → validator 層用保守預設 14d；'
'CHECK 在 NULL 時不強制。';

COMMENT ON COLUMN replay.experiments.embargo_days IS
'V3 §8.1 OOS embargo (days) between calibration window end and OOS label '
'window start. CHECK chk_embargo_days enforces >= GREATEST(7, '
'CEIL(2 × half_life_days)). / V3 §8.1 OOS embargo（天），calibration window '
'結束與 OOS label window 起始之間。chk_embargo_days 強制 >= GREATEST(7, '
'CEIL(2 × half_life_days))。';

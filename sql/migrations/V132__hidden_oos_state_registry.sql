-- ============================================================
-- V132: learning.hidden_oos_state_registry
--       Durable hidden OOS state machine seed
--
-- 目的：
--   P1-B 已把 hidden_oos_state 放入 replay.experiments.manifest_jsonb，
--   並由 source contract 驗 sealed/open_count/consumed 等欄位；但它仍是
--   manifest-only，沒有 durable state row，也沒有可被消費後標記的狀態機。
--   本 migration 建立最小 durable registry：register 時寫 sealed，MLDE
--   live-candidate producer 消費後轉 consumed，防同一 hidden OOS split 被重用。
--
-- 範圍：
--   - additive only；不改 replay.experiments、不改 promotion stage、不碰 order。
--   - table 本身不授權 promotion；source contract 仍要同時驗 replay registry、
--     residual report registry、SignalSpec、hidden OOS durable state。
--   - 不設 retention；hidden OOS state 是 promotion audit evidence。
--
-- Guard：
--   Guard A：既有表缺必要欄 → RAISE。
--   Guard B：核心欄位型別反射。
--   Guard C：unique/index/constraint 存在性。
-- ============================================================

BEGIN;

DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name = 'hidden_oos_state_registry'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'state_id',
            'created_at',
            'updated_at',
            'replay_experiment_id',
            'replay_manifest_hash',
            'family_id',
            'split_hash',
            'state',
            'open_count',
            'opened_for_iteration',
            'consumed',
            'invalidated',
            'calibration_train_window_start',
            'calibration_train_window_end',
            'candidate_window_start',
            'candidate_window_end',
            'window_start',
            'window_end',
            'embargo_seconds',
            'total_candidates_k',
            'residual_alpha_report_hash',
            'state_jsonb',
            'actor_id',
            'source',
            'transition_reason',
            'evidence'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name = 'hidden_oos_state_registry'
              AND column_name = c
        );

        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V132 Guard A FAIL: learning.hidden_oos_state_registry exists but missing required columns: %.',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.hidden_oos_state_registry (
    state_id                         BIGSERIAL   PRIMARY KEY,
    created_at                       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replay_experiment_id             UUID        NOT NULL
        REFERENCES replay.experiments(experiment_id) ON DELETE RESTRICT,
    replay_manifest_hash             TEXT        NOT NULL,
    family_id                        TEXT        NOT NULL,
    split_hash                       TEXT        NOT NULL,
    state                            TEXT        NOT NULL DEFAULT 'sealed',
    open_count                       INTEGER     NOT NULL DEFAULT 0,
    opened_for_iteration             BOOLEAN     NOT NULL DEFAULT FALSE,
    consumed                         BOOLEAN     NOT NULL DEFAULT FALSE,
    invalidated                      BOOLEAN     NOT NULL DEFAULT FALSE,
    calibration_train_window_start   TIMESTAMPTZ NOT NULL,
    calibration_train_window_end     TIMESTAMPTZ NOT NULL,
    candidate_window_start           TIMESTAMPTZ NOT NULL,
    candidate_window_end             TIMESTAMPTZ NOT NULL,
    window_start                     TIMESTAMPTZ NOT NULL,
    window_end                       TIMESTAMPTZ NOT NULL,
    embargo_seconds                  BIGINT      NOT NULL,
    total_candidates_k               INTEGER     NOT NULL,
    residual_alpha_report_hash       TEXT        NOT NULL,
    state_jsonb                      JSONB       NOT NULL,
    actor_id                         TEXT        NOT NULL,
    source                           TEXT        NOT NULL DEFAULT 'replay_experiment_register',
    transition_reason                TEXT,
    evidence                         JSONB       NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT hidden_oos_state_registry_replay_manifest_hash_chk
        CHECK (replay_manifest_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT hidden_oos_state_registry_residual_hash_chk
        CHECK (residual_alpha_report_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT hidden_oos_state_registry_state_chk
        CHECK (state IN ('sealed', 'opened', 'consumed', 'invalidated')),
    CONSTRAINT hidden_oos_state_registry_open_count_chk
        CHECK (open_count >= 0),
    CONSTRAINT hidden_oos_state_registry_windows_chk
        CHECK (
            calibration_train_window_start < calibration_train_window_end
            AND candidate_window_start < candidate_window_end
            AND window_start < window_end
        ),
    CONSTRAINT hidden_oos_state_registry_positive_counts_chk
        CHECK (embargo_seconds > 0 AND total_candidates_k > 0),
    CONSTRAINT hidden_oos_state_registry_state_jsonb_object_chk
        CHECK (jsonb_typeof(state_jsonb) = 'object'),
    CONSTRAINT hidden_oos_state_registry_state_flags_chk
        CHECK (
            (
                state = 'sealed'
                AND open_count = 0
                AND opened_for_iteration IS FALSE
                AND consumed IS FALSE
                AND invalidated IS FALSE
            )
            OR (
                state = 'opened'
                AND open_count > 0
                AND opened_for_iteration IS TRUE
                AND consumed IS FALSE
                AND invalidated IS FALSE
            )
            OR (
                state = 'consumed'
                AND open_count > 0
                AND opened_for_iteration IS TRUE
                AND consumed IS TRUE
                AND invalidated IS FALSE
            )
            OR (
                state = 'invalidated'
                AND invalidated IS TRUE
            )
        ),
    CONSTRAINT hidden_oos_state_registry_one_row_per_experiment_uk
        UNIQUE (replay_experiment_id),
    CONSTRAINT hidden_oos_state_registry_family_split_uk
        UNIQUE (family_id, split_hash)
);

CREATE INDEX IF NOT EXISTS idx_hidden_oos_state_registry_state_updated
    ON learning.hidden_oos_state_registry (state, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_hidden_oos_state_registry_family_split
    ON learning.hidden_oos_state_registry (family_id, split_hash);

COMMENT ON TABLE learning.hidden_oos_state_registry IS
    'Durable hidden OOS state machine registry. Register writes sealed; candidate promotion consumption transitions to consumed. Audit evidence only, not promotion authority.';

COMMENT ON COLUMN learning.hidden_oos_state_registry.state_jsonb IS
    'Original hidden_oos_state body from replay manifest, kept for source-contract reconstruction.';

-- Guard B：核心欄位型別反射。
DO $$
DECLARE
    v_bad TEXT[];
BEGIN
    SELECT array_agg(column_name || ':' || data_type) INTO v_bad
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'hidden_oos_state_registry'
      AND (
        (column_name = 'replay_experiment_id' AND data_type <> 'uuid')
        OR (column_name = 'replay_manifest_hash' AND data_type <> 'text')
        OR (column_name = 'state' AND data_type <> 'text')
        OR (column_name = 'open_count' AND data_type <> 'integer')
        OR (column_name = 'opened_for_iteration' AND data_type <> 'boolean')
        OR (column_name = 'consumed' AND data_type <> 'boolean')
        OR (column_name = 'invalidated' AND data_type <> 'boolean')
        OR (column_name = 'state_jsonb' AND data_type <> 'jsonb')
      );

    IF v_bad IS NOT NULL AND array_length(v_bad, 1) > 0 THEN
        RAISE EXCEPTION
            'V132 Guard B FAIL: learning.hidden_oos_state_registry type drift: %.',
            v_bad;
    END IF;
END $$;

-- Guard C：狀態機最小不變量。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'hidden_oos_state_registry_one_row_per_experiment_uk'
          AND conrelid = 'learning.hidden_oos_state_registry'::regclass
    ) THEN
        RAISE EXCEPTION
            'V132 Guard C FAIL: one-row-per-experiment unique constraint missing.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'hidden_oos_state_registry_family_split_uk'
          AND conrelid = 'learning.hidden_oos_state_registry'::regclass
    ) THEN
        RAISE EXCEPTION
            'V132 Guard C FAIL: family/split unique constraint missing.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'hidden_oos_state_registry_state_flags_chk'
          AND conrelid = 'learning.hidden_oos_state_registry'::regclass
    ) THEN
        RAISE EXCEPTION
            'V132 Guard C FAIL: state/flag consistency CHECK missing.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'learning'
          AND tablename = 'hidden_oos_state_registry'
          AND indexname = 'idx_hidden_oos_state_registry_state_updated'
    ) THEN
        RAISE EXCEPTION
            'V132 Guard C FAIL: state updated index missing.';
    END IF;
END $$;

COMMIT;

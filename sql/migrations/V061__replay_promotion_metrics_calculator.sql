-- V061__replay_promotion_metrics_calculator.sql
-- REF-21 P0-REF21-5: SECURITY DEFINER replay promotion metrics calculator.
--
-- Purpose: create a non-stub `replay.calculate_promotion_metrics()` function that
--   derives promotion metrics from replay-owned database rows instead of
--   trusting producer-supplied payloads. This function is deliberately
--   fail-closed: missing experiments, missing OOS windows, missing edge
--   snapshots, negative predicted edge, negative OOS edge, insufficient PBO
--   power, or invalid tier transitions all return `eligible=false`.
--
-- Alignment mirrors `program_code/learning_engine/{dsr_gate,pbo_gate,quantile_bootstrap}.py`.
-- This migration creates only the calculator/helpers; approvals remain separate.

CREATE SCHEMA IF NOT EXISTS replay;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF to_regtype('replay.replay_evidence_tier_v057') IS NULL THEN
        RAISE EXCEPTION
            'V061 Guard A: replay.replay_evidence_tier_v057 missing; V057 must run before V061';
    END IF;

    IF to_regclass('replay.tier_promotion_approval') IS NULL THEN
        RAISE EXCEPTION
            'V061 Guard A: replay.tier_promotion_approval missing; V057 must run before V061';
    END IF;

    IF to_regclass('replay.experiments') IS NULL THEN
        RAISE EXCEPTION
            'V061 Guard A: replay.experiments missing; V049 must run before V061';
    END IF;

    IF to_regclass('replay.simulated_fills') IS NULL THEN
        RAISE EXCEPTION
            'V061 Guard A: replay.simulated_fills missing; V050 must run before V061';
    END IF;

    IF to_regclass('learning.edge_estimate_snapshots') IS NULL THEN
        RAISE EXCEPTION
            'V061 Guard A: learning.edge_estimate_snapshots missing; V059 must run before V061';
    END IF;

    RAISE NOTICE 'V061 Guard A: calculator prerequisites verified';
END $$;

CREATE OR REPLACE FUNCTION replay._jsonb_double_v061(
    p_payload JSONB,
    p_key TEXT
) RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_text TEXT;
BEGIN
    IF p_payload IS NULL OR p_key IS NULL THEN
        RETURN NULL;
    END IF;

    v_text := p_payload ->> p_key;
    IF v_text IS NULL OR v_text !~ '^[+-]?(([0-9]+([.][0-9]*)?)|([.][0-9]+))([eE][+-]?[0-9]+)?$' THEN
        RETURN NULL;
    END IF;

    RETURN v_text::DOUBLE PRECISION;
END $$;

CREATE OR REPLACE FUNCTION replay._normal_cdf_v061(
    p_x DOUBLE PRECISION
) RETURNS DOUBLE PRECISION
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT 0.5::DOUBLE PRECISION * (1.0::DOUBLE PRECISION + erf(p_x / sqrt(2.0::DOUBLE PRECISION)));
$$;

CREATE OR REPLACE FUNCTION replay._is_finite_v061(
    p_value DOUBLE PRECISION
) RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_value::TEXT NOT IN ('Infinity', '-Infinity', 'NaN');
$$;

CREATE OR REPLACE FUNCTION replay._normal_inv_cdf_v061(
    p_probability DOUBLE PRECISION
) RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    q DOUBLE PRECISION;
    r DOUBLE PRECISION;
    p_low CONSTANT DOUBLE PRECISION := 0.02425;
    p_high CONSTANT DOUBLE PRECISION := 0.97575;
BEGIN
    IF p_probability <= 0.0 OR p_probability >= 1.0 THEN
        RAISE EXCEPTION 'V061 _normal_inv_cdf_v061: probability % outside (0,1)', p_probability;
    END IF;

    IF p_probability < p_low THEN
        q := sqrt(-2.0 * ln(p_probability));
        RETURN (((((-0.007784894002430293 * q - 0.3223964580411365) * q - 2.400758277161838) * q - 2.549732539343734) * q + 4.374664141464968) * q + 2.938163982698783)
            / ((((0.007784695709041462 * q + 0.3224671290700398) * q + 2.445134137142996) * q + 3.754408661907416) * q + 1.0);
    ELSIF p_probability <= p_high THEN
        q := p_probability - 0.5;
        r := q * q;
        RETURN (((((-39.69683028665376 * r + 220.9460984245205) * r - 275.9285104469687) * r + 138.3577518672690) * r - 30.66479806614716) * r + 2.506628277459239) * q
            / (((((-54.47609879822406 * r + 161.5858368580409) * r - 155.6989798598866) * r + 66.80131188771972) * r - 13.28068155288572) * r + 1.0);
    ELSE
        q := sqrt(-2.0 * ln(1.0 - p_probability));
        RETURN -(((((-0.007784894002430293 * q - 0.3223964580411365) * q - 2.400758277161838) * q - 2.549732539343734) * q + 4.374664141464968) * q + 2.938163982698783)
            / ((((0.007784695709041462 * q + 0.3224671290700398) * q + 2.445134137142996) * q + 3.754408661907416) * q + 1.0);
    END IF;
END $$;

CREATE OR REPLACE FUNCTION replay._expected_max_sharpe_v061(
    p_k INTEGER
) RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    gamma CONSTANT DOUBLE PRECISION := 0.5772156649015329;
BEGIN
    IF p_k < 1 THEN
        RAISE EXCEPTION 'V061 _expected_max_sharpe_v061: K % must be >= 1', p_k;
    END IF;

    IF p_k = 1 THEN
        RETURN 0.0;
    END IF;

    RETURN (1.0 - gamma) * replay._normal_inv_cdf_v061(1.0 - 1.0 / p_k::DOUBLE PRECISION)
        + gamma * replay._normal_inv_cdf_v061(1.0 - 1.0 / (p_k::DOUBLE PRECISION * exp(1.0)));
END $$;

CREATE OR REPLACE FUNCTION replay._psr_v061(
    p_observed_sharpe DOUBLE PRECISION,
    p_sharpe_threshold DOUBLE PRECISION,
    p_n_observations INTEGER
) RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    v_variance_term DOUBLE PRECISION;
    v_z DOUBLE PRECISION;
BEGIN
    IF p_n_observations < 2 THEN
        RETURN 0.0;
    END IF;

    v_variance_term := 1.0 + 0.5 * p_observed_sharpe * p_observed_sharpe;
    IF v_variance_term <= 0.0 THEN
        RETURN 0.5;
    END IF;

    v_z := (p_observed_sharpe - p_sharpe_threshold) * sqrt((p_n_observations - 1)::DOUBLE PRECISION) / sqrt(v_variance_term);
    RETURN replay._normal_cdf_v061(v_z);
END $$;

CREATE OR REPLACE FUNCTION replay._sharpe_v061(
    p_values DOUBLE PRECISION[]
) RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_avg DOUBLE PRECISION;
    v_std DOUBLE PRECISION;
BEGIN
    SELECT avg(v), stddev_samp(v)
    INTO v_avg, v_std
    FROM unnest(COALESCE(p_values, ARRAY[]::DOUBLE PRECISION[])) AS t(v)
    WHERE replay._is_finite_v061(v);

    IF v_avg IS NULL OR v_std IS NULL OR v_std = 0.0 THEN
        RETURN 0.0;
    END IF;

    RETURN v_avg / v_std;
END $$;

CREATE OR REPLACE FUNCTION replay._quantile_v061(
    p_values DOUBLE PRECISION[],
    p_q DOUBLE PRECISION
) RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_result DOUBLE PRECISION;
BEGIN
    IF p_q <= 0.0 OR p_q >= 1.0 THEN
        RAISE EXCEPTION 'V061 _quantile_v061: q % outside (0,1)', p_q;
    END IF;

    SELECT percentile_cont(p_q) WITHIN GROUP (ORDER BY v)
    INTO v_result
    FROM unnest(COALESCE(p_values, ARRAY[]::DOUBLE PRECISION[])) AS t(v)
    WHERE replay._is_finite_v061(v);

    RETURN v_result;
END $$;

CREATE OR REPLACE FUNCTION replay._sha_uniform_v061(
    p_seed TEXT,
    p_iter INTEGER,
    p_pos INTEGER,
    p_salt TEXT
) RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    v_hex TEXT;
    v_int BIGINT;
BEGIN
    v_hex := substr(encode(public.digest((p_seed || ':' || p_iter::TEXT || ':' || p_pos::TEXT || ':' || p_salt)::TEXT, 'sha256'), 'hex'), 1, 13);
    v_int := ('x' || v_hex)::bit(52)::BIGINT;
    RETURN v_int::DOUBLE PRECISION / 4503599627370496.0;
END $$;

CREATE OR REPLACE FUNCTION replay._stationary_bootstrap_quantile_ci_v061(
    p_values DOUBLE PRECISION[],
    p_q DOUBLE PRECISION,
    p_seed TEXT
) RETURNS JSONB
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_values DOUBLE PRECISION[];
    v_n INTEGER;
    v_block_size INTEGER;
    v_iter INTEGER;
    v_pos INTEGER;
    v_idx INTEGER;
    v_sample DOUBLE PRECISION[];
    v_boot DOUBLE PRECISION[] := ARRAY[]::DOUBLE PRECISION[];
    v_jump_probability DOUBLE PRECISION;
BEGIN
    SELECT COALESCE(array_agg(v ORDER BY ord), ARRAY[]::DOUBLE PRECISION[])
    INTO v_values
    FROM unnest(COALESCE(p_values, ARRAY[]::DOUBLE PRECISION[])) WITH ORDINALITY AS t(v, ord)
    WHERE replay._is_finite_v061(v);

    v_n := COALESCE(array_length(v_values, 1), 0);
    IF v_n = 0 THEN
        RETURN jsonb_build_object(
            'point', NULL,
            'ci_lower', NULL,
            'ci_upper', NULL,
            'n_iter', 0,
            'block_size', 0,
            'sample_size', 0,
            'low_confidence', true
        );
    END IF;

    v_block_size := GREATEST(1, LEAST(v_n, floor(sqrt(v_n::DOUBLE PRECISION))::INTEGER));
    v_jump_probability := 1.0 / v_block_size::DOUBLE PRECISION;

    FOR v_iter IN 1..1000 LOOP
        v_sample := ARRAY[]::DOUBLE PRECISION[];
        v_idx := floor(replay._sha_uniform_v061(p_seed, v_iter, 0, 'start') * v_n)::INTEGER + 1;

        FOR v_pos IN 1..v_n LOOP
            IF v_pos > 1 THEN
                IF replay._sha_uniform_v061(p_seed, v_iter, v_pos, 'jump') < v_jump_probability THEN
                    v_idx := floor(replay._sha_uniform_v061(p_seed, v_iter, v_pos, 'idx') * v_n)::INTEGER + 1;
                ELSE
                    v_idx := (v_idx % v_n) + 1;
                END IF;
            END IF;

            v_sample := array_append(v_sample, v_values[v_idx]);
        END LOOP;

        v_boot := array_append(v_boot, replay._quantile_v061(v_sample, p_q));
    END LOOP;

    RETURN jsonb_build_object(
        'point', replay._quantile_v061(v_values, p_q),
        'ci_lower', replay._quantile_v061(v_boot, 0.025),
        'ci_upper', replay._quantile_v061(v_boot, 0.975),
        'n_iter', 1000,
        'block_size', v_block_size,
        'sample_size', v_n,
        'low_confidence', v_n < 30
    );
END $$;

CREATE OR REPLACE FUNCTION replay._popcount_v061(
    p_mask INTEGER,
    p_width INTEGER
) RETURNS INTEGER
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    v_i INTEGER;
    v_count INTEGER := 0;
BEGIN
    FOR v_i IN 0..(p_width - 1) LOOP
        IF ((p_mask::BIGINT >> v_i) & 1) = 1 THEN
            v_count := v_count + 1;
        END IF;
    END LOOP;

    RETURN v_count;
END $$;

CREATE OR REPLACE FUNCTION replay.calculate_promotion_metrics(
    p_report_id UUID,
    p_from_tier replay.replay_evidence_tier_v057,
    p_to_tier replay.replay_evidence_tier_v057
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, replay, learning, pg_temp
AS $$
DECLARE
    v_manifest_hash BYTEA;
    v_total_candidates_k INTEGER;
    v_parent_experiment_id UUID;
    v_root_experiment_id UUID;
    v_cal_start TIMESTAMPTZ;
    v_cal_end TIMESTAMPTZ;
    v_oos_start TIMESTAMPTZ;
    v_oos_end TIMESTAMPTZ;
    v_candidate_start TIMESTAMPTZ;
    v_all_returns DOUBLE PRECISION[] := ARRAY[]::DOUBLE PRECISION[];
    v_is_returns DOUBLE PRECISION[] := ARRAY[]::DOUBLE PRECISION[];
    v_oos_returns DOUBLE PRECISION[] := ARRAY[]::DOUBLE PRECISION[];
    v_n INTEGER := 0;
    v_is_n INTEGER := 0;
    v_oos_n INTEGER := 0;
    v_is_net_bps DOUBLE PRECISION;
    v_oos_net_bps DOUBLE PRECISION;
    v_is_sr DOUBLE PRECISION := 0.0;
    v_oos_sr DOUBLE PRECISION := 0.0;
    v_oos_gap_bps DOUBLE PRECISION;
    v_predicted_edge_bps DOUBLE PRECISION;
    v_psr0 DOUBLE PRECISION := 0.0;
    v_dsr DOUBLE PRECISION := 0.0;
    v_trials_max_sharpe DOUBLE PRECISION := 0.0;
    v_pbo DOUBLE PRECISION;
    v_pbo_combinations INTEGER := 0;
    v_pbo_bad INTEGER := 0;
    v_pbo_insufficient_power BOOLEAN := true;
    v_candidate_count INTEGER := 0;
    v_min_len INTEGER := 0;
    v_total_candidate_trades INTEGER := 0;
    v_mask INTEGER;
    v_best_oos DOUBLE PRECISION;
    v_n_below INTEGER;
    v_n_equal INTEGER;
    v_rank_probability DOUBLE PRECISION;
    v_fail_reasons TEXT[] := ARRAY[]::TEXT[];
    v_transition_allowed BOOLEAN := false;
    v_metrics JSONB;
    v_metrics_hash BYTEA;
    v_seed TEXT;
BEGIN
    IF p_report_id IS NULL OR p_from_tier IS NULL OR p_to_tier IS NULL THEN
        RETURN jsonb_build_object(
            'eligible', false,
            'fail_reasons', jsonb_build_array('null_input'),
            'metrics_hash_hex', NULL,
            'report_id', p_report_id
        );
    END IF;

    v_transition_allowed := (
        (p_from_tier = 's2_public_replay'::replay.replay_evidence_tier_v057
            AND p_to_tier = 's2_oos_replay'::replay.replay_evidence_tier_v057)
        OR (p_from_tier = 's2_oos_replay'::replay.replay_evidence_tier_v057
            AND p_to_tier = 's1_calibrated_replay'::replay.replay_evidence_tier_v057)
        OR (p_from_tier = 's1_calibrated_replay'::replay.replay_evidence_tier_v057
            AND p_to_tier = 'verified_replay_advisory'::replay.replay_evidence_tier_v057)
    );

    IF NOT v_transition_allowed THEN
        v_fail_reasons := array_append(v_fail_reasons, 'invalid_tier_transition');
    END IF;

    SELECT
        manifest_hash,
        COALESCE(total_candidates_k, 1),
        parent_experiment_id,
        calibration_train_window_start,
        calibration_train_window_end,
        oos_label_window_start,
        oos_label_window_end,
        candidate_window_start
    INTO
        v_manifest_hash,
        v_total_candidates_k,
        v_parent_experiment_id,
        v_cal_start,
        v_cal_end,
        v_oos_start,
        v_oos_end,
        v_candidate_start
    FROM replay.experiments
    WHERE experiment_id = p_report_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'eligible', false,
            'fail_reasons', jsonb_build_array('experiment_missing'),
            'metrics_hash_hex', NULL,
            'report_id', p_report_id
        );
    END IF;

    v_root_experiment_id := COALESCE(v_parent_experiment_id, p_report_id);
    v_seed := encode(public.digest(p_report_id::TEXT || ':' || COALESCE(encode(v_manifest_hash, 'hex'), 'no_manifest'), 'sha256'), 'hex');

    IF v_manifest_hash IS NULL OR octet_length(v_manifest_hash) <> 32 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'manifest_hash_missing');
    END IF;

    IF v_cal_start IS NULL OR v_cal_end IS NULL OR v_oos_start IS NULL OR v_oos_end IS NULL THEN
        v_fail_reasons := array_append(v_fail_reasons, 'is_oos_windows_missing');
    END IF;

    WITH returns AS (
        SELECT
            sf.ts,
            COALESCE(
                replay._jsonb_double_v061(sf.payload, 'net_bps_after_fee'),
                replay._jsonb_double_v061(sf.payload, 'realized_net_bps'),
                replay._jsonb_double_v061(sf.payload, 'net_bps'),
                sf.ci_mid_bps
            ) AS return_bps
        FROM replay.simulated_fills sf
        WHERE sf.experiment_id = p_report_id
    )
    SELECT
        COALESCE(array_agg(return_bps ORDER BY ts), ARRAY[]::DOUBLE PRECISION[]),
        COUNT(*)::INTEGER
    INTO v_all_returns, v_n
    FROM returns
    WHERE return_bps IS NOT NULL AND replay._is_finite_v061(return_bps);

    IF v_n = 0 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'return_bps_missing');
    END IF;

    IF v_cal_start IS NOT NULL AND v_cal_end IS NOT NULL THEN
        WITH returns AS (
            SELECT
                sf.ts,
                COALESCE(
                    replay._jsonb_double_v061(sf.payload, 'net_bps_after_fee'),
                    replay._jsonb_double_v061(sf.payload, 'realized_net_bps'),
                    replay._jsonb_double_v061(sf.payload, 'net_bps'),
                    sf.ci_mid_bps
                ) AS return_bps
            FROM replay.simulated_fills sf
            WHERE sf.experiment_id = p_report_id
              AND sf.ts >= v_cal_start
              AND sf.ts < v_cal_end
        )
        SELECT
            COALESCE(array_agg(return_bps ORDER BY ts), ARRAY[]::DOUBLE PRECISION[]),
            COUNT(*)::INTEGER,
            avg(return_bps)
        INTO v_is_returns, v_is_n, v_is_net_bps
        FROM returns
        WHERE return_bps IS NOT NULL AND replay._is_finite_v061(return_bps);
    END IF;

    IF v_oos_start IS NOT NULL AND v_oos_end IS NOT NULL THEN
        WITH returns AS (
            SELECT
                sf.ts,
                COALESCE(
                    replay._jsonb_double_v061(sf.payload, 'net_bps_after_fee'),
                    replay._jsonb_double_v061(sf.payload, 'realized_net_bps'),
                    replay._jsonb_double_v061(sf.payload, 'net_bps'),
                    sf.ci_mid_bps
                ) AS return_bps
            FROM replay.simulated_fills sf
            WHERE sf.experiment_id = p_report_id
              AND sf.ts >= v_oos_start
              AND sf.ts < v_oos_end
        )
        SELECT
            COALESCE(array_agg(return_bps ORDER BY ts), ARRAY[]::DOUBLE PRECISION[]),
            COUNT(*)::INTEGER,
            avg(return_bps)
        INTO v_oos_returns, v_oos_n, v_oos_net_bps
        FROM returns
        WHERE return_bps IS NOT NULL AND replay._is_finite_v061(return_bps);
    END IF;

    v_is_sr := replay._sharpe_v061(v_is_returns);
    v_oos_sr := replay._sharpe_v061(v_oos_returns);
    v_oos_gap_bps := GREATEST(
        abs(COALESCE(v_oos_net_bps, 0.0) - COALESCE(v_is_net_bps, 0.0)),
        abs(COALESCE(v_oos_sr, 0.0) - COALESCE(v_is_sr, 0.0)) * 100.0
    );

    IF v_is_n = 0 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'is_returns_missing');
    END IF;
    IF v_oos_n = 0 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'oos_returns_missing');
    END IF;
    IF v_oos_net_bps IS NULL OR v_oos_net_bps <= 0.0 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'oos_net_bps_not_positive');
    END IF;
    IF v_oos_gap_bps IS NULL OR v_oos_gap_bps > 30.0 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'oos_gap_gt_30bps');
    END IF;

    WITH cells AS (
        SELECT DISTINCT sf.symbol, sf.strategy_name AS strategy
        FROM replay.simulated_fills sf
        WHERE sf.experiment_id = p_report_id
    ),
    latest AS (
        SELECT DISTINCT ON (e.symbol, e.strategy, e.regime_key, e.cell_key)
            COALESCE(
                replay._jsonb_double_v061(e.estimate_payload_jsonb, 'predicted_edge_bps'),
                replay._jsonb_double_v061(e.estimate_payload_jsonb, 'edge_bps'),
                replay._jsonb_double_v061(e.estimate_payload_jsonb, 'expected_net_bps'),
                replay._jsonb_double_v061(e.estimate_payload_jsonb, 'net_bps_after_fee')
            ) AS edge_bps
        FROM learning.edge_estimate_snapshots e
        JOIN cells c ON c.symbol = e.symbol AND c.strategy = e.strategy
        WHERE e.asof_ts <= COALESCE(v_candidate_start, v_oos_start, now())
          AND NOT e.is_deprecated_at_asof
        ORDER BY e.symbol, e.strategy, e.regime_key, e.cell_key, e.asof_ts DESC
    )
    SELECT avg(edge_bps)
    INTO v_predicted_edge_bps
    FROM latest
    WHERE edge_bps IS NOT NULL AND replay._is_finite_v061(edge_bps);

    IF v_predicted_edge_bps IS NULL THEN
        v_fail_reasons := array_append(v_fail_reasons, 'edge_snapshot_missing');
    ELSIF v_predicted_edge_bps <= 0.0 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'predicted_edge_bps_not_positive');
    END IF;

    v_trials_max_sharpe := replay._expected_max_sharpe_v061(GREATEST(1, v_total_candidates_k));
    v_psr0 := replay._psr_v061(COALESCE(v_oos_sr, 0.0), 0.0, GREATEST(0, v_oos_n));
    v_dsr := replay._psr_v061(COALESCE(v_oos_sr, 0.0), v_trials_max_sharpe, GREATEST(0, v_oos_n));

    IF v_psr0 < 0.95 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'psr0_lt_0_95');
    END IF;
    IF v_dsr <= 0.0 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'dsr_not_positive');
    END IF;

    DROP TABLE IF EXISTS replay_promotion_returns_v061;
    CREATE TEMP TABLE replay_promotion_returns_v061 (
        experiment_id UUID NOT NULL,
        seq_no INTEGER NOT NULL,
        return_bps DOUBLE PRECISION NOT NULL,
        slice_idx INTEGER
    ) ON COMMIT DROP;

    INSERT INTO replay_promotion_returns_v061 (experiment_id, seq_no, return_bps)
    SELECT experiment_id, seq_no, return_bps
    FROM (
        SELECT
            e.experiment_id,
            row_number() OVER (PARTITION BY e.experiment_id ORDER BY sf.ts)::INTEGER AS seq_no,
            COALESCE(
                replay._jsonb_double_v061(sf.payload, 'net_bps_after_fee'),
                replay._jsonb_double_v061(sf.payload, 'realized_net_bps'),
                replay._jsonb_double_v061(sf.payload, 'net_bps'),
                sf.ci_mid_bps
            ) AS return_bps
        FROM replay.experiments e
        JOIN replay.simulated_fills sf ON sf.experiment_id = e.experiment_id
        WHERE (e.experiment_id = v_root_experiment_id OR e.parent_experiment_id = v_root_experiment_id)
          AND e.oos_label_window_start IS NOT NULL
          AND e.oos_label_window_end IS NOT NULL
          AND sf.ts >= e.oos_label_window_start
          AND sf.ts < e.oos_label_window_end
    ) ranked
    WHERE return_bps IS NOT NULL AND replay._is_finite_v061(return_bps);

    SELECT COUNT(DISTINCT experiment_id), COALESCE(MIN(cnt), 0), COALESCE(SUM(cnt), 0)
    INTO v_candidate_count, v_min_len, v_total_candidate_trades
    FROM (
        SELECT experiment_id, COUNT(*)::INTEGER AS cnt
        FROM replay_promotion_returns_v061
        GROUP BY experiment_id
    ) c;

    IF v_candidate_count >= 2 AND v_min_len >= 16 AND v_total_candidate_trades >= 320 THEN
        DELETE FROM replay_promotion_returns_v061 WHERE seq_no > v_min_len;
        UPDATE replay_promotion_returns_v061
        SET slice_idx = floor(((seq_no - 1)::DOUBLE PRECISION * 16.0) / v_min_len::DOUBLE PRECISION)::INTEGER;

        FOR v_mask IN 0..65535 LOOP
            IF replay._popcount_v061(v_mask, 16) = 8 THEN
                WITH stats AS (
                    SELECT
                        experiment_id,
                        CASE
                            WHEN stddev_samp(return_bps) FILTER (WHERE ((v_mask::BIGINT >> slice_idx) & 1) = 1) IS NULL
                              OR stddev_samp(return_bps) FILTER (WHERE ((v_mask::BIGINT >> slice_idx) & 1) = 1) = 0.0
                            THEN 0.0
                            ELSE avg(return_bps) FILTER (WHERE ((v_mask::BIGINT >> slice_idx) & 1) = 1)
                                / stddev_samp(return_bps) FILTER (WHERE ((v_mask::BIGINT >> slice_idx) & 1) = 1)
                        END AS is_sr,
                        CASE
                            WHEN stddev_samp(return_bps) FILTER (WHERE ((v_mask::BIGINT >> slice_idx) & 1) = 0) IS NULL
                              OR stddev_samp(return_bps) FILTER (WHERE ((v_mask::BIGINT >> slice_idx) & 1) = 0) = 0.0
                            THEN 0.0
                            ELSE avg(return_bps) FILTER (WHERE ((v_mask::BIGINT >> slice_idx) & 1) = 0)
                                / stddev_samp(return_bps) FILTER (WHERE ((v_mask::BIGINT >> slice_idx) & 1) = 0)
                        END AS oos_sr
                    FROM replay_promotion_returns_v061
                    GROUP BY experiment_id
                ),
                best AS (
                    SELECT experiment_id, oos_sr
                    FROM stats
                    ORDER BY is_sr DESC, experiment_id
                    LIMIT 1
                )
                SELECT
                    b.oos_sr,
                    COUNT(*) FILTER (WHERE s.oos_sr < b.oos_sr)::INTEGER,
                    COUNT(*) FILTER (WHERE s.oos_sr = b.oos_sr)::INTEGER
                INTO v_best_oos, v_n_below, v_n_equal
                FROM best b
                CROSS JOIN stats s
                GROUP BY b.oos_sr;

                v_rank_probability := v_n_below::DOUBLE PRECISION / GREATEST(1, v_candidate_count - 1)::DOUBLE PRECISION;
                IF v_n_equal > 1 THEN
                    v_rank_probability := (v_n_below::DOUBLE PRECISION + 0.5 * (v_n_equal - 1)::DOUBLE PRECISION)
                        / GREATEST(1, v_candidate_count - 1)::DOUBLE PRECISION;
                END IF;

                IF v_rank_probability < 0.5 THEN
                    v_pbo_bad := v_pbo_bad + 1;
                END IF;
                v_pbo_combinations := v_pbo_combinations + 1;
            END IF;
        END LOOP;

        IF v_pbo_combinations > 0 THEN
            v_pbo := v_pbo_bad::DOUBLE PRECISION / v_pbo_combinations::DOUBLE PRECISION;
            v_pbo_insufficient_power := false;
        END IF;
    END IF;

    IF v_pbo_insufficient_power THEN
        v_fail_reasons := array_append(v_fail_reasons, 'pbo_insufficient_power');
    ELSIF v_pbo IS NULL OR v_pbo > 0.20 THEN
        v_fail_reasons := array_append(v_fail_reasons, 'pbo_gt_0_20');
    END IF;

    DROP TABLE IF EXISTS replay_promotion_returns_v061;

    v_metrics := jsonb_build_object(
        'schema_version', 'V061',
        'report_id', p_report_id,
        'from_tier', p_from_tier::TEXT,
        'to_tier', p_to_tier::TEXT,
        'transition_allowed', v_transition_allowed,
        'manifest_hash_hex', CASE WHEN v_manifest_hash IS NULL THEN NULL ELSE encode(v_manifest_hash, 'hex') END,
        'n_fills', v_n,
        'is_n', v_is_n,
        'oos_n', v_oos_n,
        'is_net_bps', v_is_net_bps,
        'oos_net_bps', v_oos_net_bps,
        'is_sharpe', v_is_sr,
        'oos_sharpe', v_oos_sr,
        'oos_gap_bps', v_oos_gap_bps,
        'predicted_edge_bps', v_predicted_edge_bps,
        'psr0', v_psr0,
        'dsr', v_dsr,
        'trials_max_sharpe', v_trials_max_sharpe,
        'total_candidates_k', v_total_candidates_k,
        'pbo', v_pbo,
        'pbo_combinations', v_pbo_combinations,
        'pbo_candidate_count', v_candidate_count,
        'pbo_min_len', v_min_len,
        'pbo_total_candidate_trades', v_total_candidate_trades,
        'pbo_insufficient_power', v_pbo_insufficient_power,
        'bootstrap', jsonb_build_object(
            'method', 'deterministic_stationary_bootstrap_v061',
            'q10', replay._stationary_bootstrap_quantile_ci_v061(v_oos_returns, 0.10, v_seed || ':q10'),
            'q50', replay._stationary_bootstrap_quantile_ci_v061(v_oos_returns, 0.50, v_seed || ':q50'),
            'q90', replay._stationary_bootstrap_quantile_ci_v061(v_oos_returns, 0.90, v_seed || ':q90')
        )
    );

    v_metrics_hash := public.digest(v_metrics::TEXT, 'sha256');

    RETURN jsonb_build_object(
        'eligible', array_length(v_fail_reasons, 1) IS NULL,
        'fail_reasons', COALESCE(to_jsonb(v_fail_reasons), '[]'::jsonb),
        'metrics_hash_hex', encode(v_metrics_hash, 'hex'),
        'metrics_hash', encode(v_metrics_hash, 'hex'),
        'manifest_hash_hex', CASE WHEN v_manifest_hash IS NULL THEN NULL ELSE encode(v_manifest_hash, 'hex') END,
        'metrics', v_metrics
    );
END $$;

DO $$
DECLARE
    v_function_exists BOOLEAN;
    v_is_security_definer BOOLEAN;
    v_public_execute_grants INTEGER;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'replay'
          AND p.proname = 'calculate_promotion_metrics'
          AND p.pronargs = 3
    ) INTO v_function_exists;

    SELECT p.prosecdef
    INTO v_is_security_definer
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'replay'
      AND p.proname = 'calculate_promotion_metrics'
      AND p.pronargs = 3;

    REVOKE ALL ON FUNCTION replay.calculate_promotion_metrics(
        UUID,
        replay.replay_evidence_tier_v057,
        replay.replay_evidence_tier_v057
    ) FROM PUBLIC;

    REVOKE ALL ON FUNCTION replay._jsonb_double_v061(JSONB, TEXT) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._normal_cdf_v061(DOUBLE PRECISION) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._is_finite_v061(DOUBLE PRECISION) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._normal_inv_cdf_v061(DOUBLE PRECISION) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._expected_max_sharpe_v061(INTEGER) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._psr_v061(DOUBLE PRECISION, DOUBLE PRECISION, INTEGER) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._sharpe_v061(DOUBLE PRECISION[]) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._quantile_v061(DOUBLE PRECISION[], DOUBLE PRECISION) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._sha_uniform_v061(TEXT, INTEGER, INTEGER, TEXT) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._stationary_bootstrap_quantile_ci_v061(DOUBLE PRECISION[], DOUBLE PRECISION, TEXT) FROM PUBLIC;
    REVOKE ALL ON FUNCTION replay._popcount_v061(INTEGER, INTEGER) FROM PUBLIC;

    SELECT COUNT(*)
    INTO v_public_execute_grants
    FROM information_schema.routine_privileges
    WHERE routine_schema = 'replay'
      AND routine_name IN (
          'calculate_promotion_metrics',
          '_jsonb_double_v061',
          '_normal_cdf_v061',
          '_is_finite_v061',
          '_normal_inv_cdf_v061',
          '_expected_max_sharpe_v061',
          '_psr_v061',
          '_sharpe_v061',
          '_quantile_v061',
          '_sha_uniform_v061',
          '_stationary_bootstrap_quantile_ci_v061',
          '_popcount_v061'
      )
      AND grantee = 'PUBLIC'
      AND privilege_type = 'EXECUTE';

    IF NOT v_function_exists OR NOT v_is_security_definer OR v_public_execute_grants <> 0 THEN
        RAISE EXCEPTION
            'V061 Guard B/C: function_exists=% security_definer=% public_execute_grants=%',
            v_function_exists, v_is_security_definer, v_public_execute_grants;
    END IF;

    RAISE NOTICE 'V061 Guard B/C: calculator exists, is SECURITY DEFINER, and PUBLIC EXECUTE is revoked';
END $$;

COMMENT ON FUNCTION replay.calculate_promotion_metrics(
    UUID,
    replay.replay_evidence_tier_v057,
    replay.replay_evidence_tier_v057
) IS
'REF-21 SECURITY DEFINER promotion metrics calculator. Derives metrics from replay.simulated_fills, replay.experiments, and learning.edge_estimate_snapshots; fail-closed by design.';

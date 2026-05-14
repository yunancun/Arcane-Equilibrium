"""Feature baseline readiness healthcheck.
Feature baseline readiness 健康檢查。

MODULE_NOTE:
  [67] W-AUDIT-4b retained INSERT table readiness for
  ``observability.feature_baselines``. The writer already exists in Rust; this
  sentinel proves the runtime path has populated active baselines and that the
  34-dim feature-vector contract remains aligned with ``feature_collector``.

  Drift events intentionally depend on active baselines plus the configured
  ADWIN burn-in window. This check does not shorten or bypass burn-in; it only
  verifies the baseline side of the dependency is no longer empty.
"""

from __future__ import annotations

FEATURE_DIM: int = 34

# Keep in lockstep with rust/openclaw_engine/src/feature_collector.rs
# ``FEATURE_NAMES``. The healthcheck treats any active baseline outside this
# contract as a hard failure because drift_detector maps names back to vector
# positions.
EXPECTED_FEATURE_NAMES: tuple[str, ...] = (
    "sma_20",
    "sma_50",
    "ema_12",
    "ema_26",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "bb_bandwidth",
    "bb_percent_b",
    "atr_14",
    "atr_14_percent",
    "atr_5",
    "atr_5_percent",
    "stoch_k",
    "stoch_d",
    "kama",
    "kama_efficiency",
    "adx",
    "plus_di",
    "minus_di",
    "hurst",
    "regime_id",
    "ewma_vol",
    "vol_regime_id",
    "volume_ratio",
    "donchian_upper",
    "donchian_lower",
    "donchian_middle",
    "donchian_width",
    "price",
)

assert len(EXPECTED_FEATURE_NAMES) == FEATURE_DIM


def _feature_name_array() -> list[str]:
    """Return a mutable list for psycopg2 array binding."""
    return list(EXPECTED_FEATURE_NAMES)


def check_67_feature_baseline_readiness(cur) -> tuple[str, str]:
    """[67] feature_baselines active rows + 34-dim contract readiness.

    PASS:
      * ``observability.feature_baselines`` and ``features.online_latest`` exist
      * active baseline rows > 0
      * every active symbol has exactly 34 distinct feature names
      * no active feature name falls outside the Rust 34-name contract
      * ``features.online_latest.feature_vector`` rows are 34-dim

    FAIL:
      * table missing, active baselines still zero, invalid feature names,
        partial per-symbol baseline coverage, or online vector dim drift.

    WARN:
      * active baselines exist but ``features.online_latest`` has zero current
        rows, so vector-dim verification cannot be observed yet.
    """
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 - defensive cleanup must not raise
        pass

    try:
        cur.execute(
            "SELECT to_regclass('observability.feature_baselines') IS NOT NULL, "
            "       to_regclass('features.online_latest') IS NOT NULL"
        )
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - passive sentinel should surface
        return (
            "FAIL",
            f"[67] feature_baseline table existence query failed: {type(exc).__name__}: {exc}",
        )

    baseline_exists = bool(exists_row and exists_row[0])
    online_exists = bool(exists_row and exists_row[1])
    if not baseline_exists:
        return ("FAIL", "[67] observability.feature_baselines missing")
    if not online_exists:
        return ("FAIL", "[67] features.online_latest missing; cannot verify 34-dim source vectors")

    try:
        cur.execute(
            """
            SELECT
                COUNT(*)::INT AS active_rows,
                COUNT(DISTINCT symbol)::INT AS active_symbols,
                COUNT(DISTINCT feature_name)::INT AS active_feature_names,
                COUNT(*) FILTER (
                    WHERE feature_name IS NULL OR NOT (feature_name = ANY(%s::TEXT[]))
                )::INT AS invalid_feature_rows
            FROM observability.feature_baselines
            WHERE valid_until IS NULL
            """,
            (_feature_name_array(),),
        )
        active_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return (
            "FAIL",
            f"[67] active feature_baselines query failed: {type(exc).__name__}: {exc}",
        )

    active_rows = int(active_row[0] or 0) if active_row else 0
    active_symbols = int(active_row[1] or 0) if active_row else 0
    active_feature_names = int(active_row[2] or 0) if active_row else 0
    invalid_feature_rows = int(active_row[3] or 0) if active_row else 0

    if active_rows <= 0:
        return (
            "FAIL",
            "[67] active feature_baselines=0 — run feature_baseline_writer apply path; "
            "drift_events remains gated until baselines exist",
        )

    try:
        cur.execute(
            """
            SELECT feature_name, COUNT(*)::INT
            FROM observability.feature_baselines
            WHERE valid_until IS NULL
              AND (feature_name IS NULL OR NOT (feature_name = ANY(%s::TEXT[])))
            GROUP BY feature_name
            ORDER BY COUNT(*) DESC, feature_name
            LIMIT 5
            """,
            (_feature_name_array(),),
        )
        invalid_names = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[67] invalid feature-name drill-down failed: {type(exc).__name__}: {exc}")

    if invalid_feature_rows > 0 or invalid_names:
        preview = ", ".join(f"{name}={count}" for name, count in invalid_names[:5])
        return (
            "FAIL",
            f"[67] invalid active baseline feature names rows={invalid_feature_rows} "
            f"preview={preview or 'unavailable'}; expected exactly {FEATURE_DIM} Rust FEATURE_NAMES",
        )

    try:
        cur.execute(
            """
            SELECT symbol, COUNT(DISTINCT feature_name)::INT AS feature_count
            FROM observability.feature_baselines
            WHERE valid_until IS NULL
            GROUP BY symbol
            HAVING COUNT(DISTINCT feature_name) <> %s
            ORDER BY symbol
            LIMIT 8
            """,
            (FEATURE_DIM,),
        )
        partial_symbols = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[67] per-symbol baseline drill-down failed: {type(exc).__name__}: {exc}")

    if partial_symbols:
        preview = ", ".join(f"{symbol}={count}/{FEATURE_DIM}" for symbol, count in partial_symbols)
        return (
            "FAIL",
            f"[67] partial active feature_baselines per symbol: {preview}; "
            "writer must preserve the 34-dim contract",
        )

    if active_feature_names != FEATURE_DIM:
        return (
            "FAIL",
            f"[67] active feature_name coverage={active_feature_names}/{FEATURE_DIM}; "
            "34-dim baseline contract not fully populated",
        )

    try:
        cur.execute(
            """
            SELECT
                COUNT(*)::INT AS online_rows,
                MIN(cardinality(feature_vector))::INT AS min_dim,
                MAX(cardinality(feature_vector))::INT AS max_dim,
                COUNT(*) FILTER (WHERE cardinality(feature_vector) <> %s)::INT AS bad_dim_rows
            FROM features.online_latest
            """,
            (FEATURE_DIM,),
        )
        online_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[67] online_latest vector-dim query failed: {type(exc).__name__}: {exc}")

    online_rows = int(online_row[0] or 0) if online_row else 0
    min_dim = online_row[1] if online_row else None
    max_dim = online_row[2] if online_row else None
    bad_dim_rows = int(online_row[3] or 0) if online_row else 0

    base_msg = (
        f"[67] feature_baselines active_rows={active_rows} active_symbols={active_symbols} "
        f"feature_names={active_feature_names}/{FEATURE_DIM}; "
        f"online_latest_rows={online_rows} vector_dim_min={min_dim} vector_dim_max={max_dim}"
    )

    if online_rows <= 0:
        return (
            "WARN",
            base_msg + " — active baselines exist, but online_latest has 0 rows; "
            "cannot observe current vector contract yet",
        )
    if bad_dim_rows > 0 or min_dim != FEATURE_DIM or max_dim != FEATURE_DIM:
        return (
            "FAIL",
            base_msg + f" bad_dim_rows={bad_dim_rows}; expected every current vector to be {FEATURE_DIM}-dim",
        )

    return (
        "PASS",
        base_msg + " — 34-dim baseline contract ready; drift_events will activate after configured burn-in",
    )

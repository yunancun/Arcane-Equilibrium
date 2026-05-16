"""Close-maker audit healthchecks for V094 observability.

MODULE_NOTE:
  ``[70]``-``[74]`` rebase the frozen V094 semantic checks away from occupied
  runner slots ``[64]`` and ``[65]``. They monitor close-maker fill quality,
  zero-spine close lineage, fallback/NULL-ladder completeness, and rate-limit
  backoff coverage. MIT-AC-19 per-strategy x per-symbol outputs are appended
  as diagnostic text only; they do not drive PASS/WARN/FAIL verdicts.

  ``[70]``-``[74]`` 將 V094 凍結文本的語義 check 從已占用的 ``[64]`` /
  ``[65]`` 重排到自由 slot。監測 close-maker fill-rate、close path 0 spine
  lineage、fallback / NULL ladder 完整性，以及 rate-limit backoff scope。
  MIT-AC-19 的 strategy x symbol breakdown 只作診斷文字，不參與部署 gate。
"""

from __future__ import annotations

import math
import os
from typing import Any


REQUIRED_ENV = "OPENCLAW_CLOSE_MAKER_HEALTH_REQUIRED"

FILL_RATE_MIN_SAMPLE: int = 30
FILL_RATE_WARN_LOWER_BOUND: float = 0.40
FILL_RATE_PASS_LOWER_BOUND: float = 0.60
FALLBACK_TO_TAKER_WARN_LOWER_BOUND: float = 0.85
FALLBACK_TO_TAKER_PASS_LOWER_BOUND: float = 0.90

NULL_LADDER_MIN_SAMPLE: int = 5
NULL_LADDER_PASS_RATIO: float = 0.999
NULL_LADDER_WARN_RATIO: float = 0.99

RATE_LIMIT_GLOBAL_WARN_MAX: int = 5
RATE_LIMIT_PER_SYMBOL_PASS_MAX: int = 100
RATE_LIMIT_PER_SYMBOL_WARN_MAX: int = 500

FALLBACK_REASONS: tuple[str, ...] = (
    "timeout_taker",
    "postonly_reject",
    "cancel_grace_expired",
    "ack_lost",
    "rate_limit_pause_global",
    "rate_limit_backoff_per_symbol",
    "fast_escalate_safety_upgrade",
    "not_attempted_safety_path",
    "engine_shutdown_safety",
    "fallback_to_taker_mandatory",
)

SAFETY_FALLBACK_REASONS: tuple[str, ...] = (
    "fast_escalate_safety_upgrade",
    "not_attempted_safety_path",
    "engine_shutdown_safety",
)

FALLBACK_TO_TAKER_REASONS: tuple[str, ...] = tuple(
    reason for reason in FALLBACK_REASONS if reason != "not_attempted_safety_path"
)

SCHEMA_FLAG_NAMES: tuple[str, ...] = (
    "trading.fills",
    "ts",
    "engine_mode",
    "strategy_name",
    "symbol",
    "fill_id",
    "details_jsonb",
    "close_maker_attempt_boolean",
    "close_maker_fallback_reason_text",
)


def _enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() == "1"


def _rollback(cur: Any) -> None:
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 - rollback is best-effort cleanup
        pass


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _severity_max(left: str, right: str) -> str:
    order = {"PASS": 0, "WARN": 1, "FAIL": 2}
    return right if order.get(right, 0) > order.get(left, 0) else left


def _wilson_bounds(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    p_hat = successes / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = p_hat + z2 / (2.0 * total)
    spread = z * math.sqrt((p_hat * (1.0 - p_hat) + z2 / (4.0 * total)) / total)
    return ((center - spread) / denom, (center + spread) / denom)


def _v094_expected(cur: Any) -> bool:
    if _enabled(REQUIRED_ENV):
        return True
    try:
        cur.execute("SELECT to_regclass('public._sqlx_migrations') IS NOT NULL")
        row = cur.fetchone()
        if not row or not row[0]:
            return False
        cur.execute(
            "SELECT EXISTS ("
            "SELECT 1 FROM public._sqlx_migrations WHERE version >= 94 LIMIT 1"
            ")"
        )
        row = cur.fetchone()
        return bool(row and row[0])
    except Exception:  # noqa: BLE001 - inability to inspect migrations should not false-FAIL
        return False


def _schema_guard(cur: Any, check_id: str) -> tuple[str, str] | None:
    _rollback(cur)
    try:
        cur.execute(
            """
            SELECT
              to_regclass('trading.fills') IS NOT NULL,
              EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='trading' AND table_name='fills' AND column_name='ts'
              ),
              EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='trading' AND table_name='fills' AND column_name='engine_mode'
              ),
              EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='trading' AND table_name='fills' AND column_name='strategy_name'
              ),
              EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='trading' AND table_name='fills' AND column_name='symbol'
              ),
              EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='trading' AND table_name='fills' AND column_name='fill_id'
              ),
              EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='trading' AND table_name='fills'
                  AND column_name='details' AND data_type='jsonb'
              ),
              EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='trading' AND table_name='fills'
                  AND column_name='close_maker_attempt' AND data_type='boolean'
              ),
              EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='trading' AND table_name='fills'
                  AND column_name='close_maker_fallback_reason' AND data_type='text'
              )
            """
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"{check_id} V094 schema guard query failed: {type(exc).__name__}: {exc}")

    flags = tuple(bool(v) for v in row) if row else tuple(False for _ in SCHEMA_FLAG_NAMES)
    missing = [name for name, ok in zip(SCHEMA_FLAG_NAMES, flags, strict=True) if not ok]
    if not missing:
        return None

    expected = _v094_expected(cur)
    status = "FAIL" if expected else "WARN"
    marker = "V094_EXPECTED_SCHEMA_MISSING" if expected else "NEEDS_SCHEMA"
    return (
        status,
        f"{check_id} {marker}: missing={','.join(missing)}; "
        "close-maker audit checks require V094 trading.fills schema",
    )


def _format_stratified_fill_cells(rows: list[tuple[Any, ...]], max_cells: int = 8) -> str:
    cells: list[tuple[int, float, str]] = []
    for row in rows:
        engine_mode, strategy_name, symbol = row[0], row[1], row[2]
        attempts = _as_int(row[3])
        maker_fills = _as_int(row[4])
        fallbacks = _as_int(row[5])
        lower, upper = _wilson_bounds(maker_fills, attempts)
        fill_rate = maker_fills / attempts if attempts else 0.0
        if attempts < FILL_RATE_MIN_SAMPLE:
            cell_status = "NEUTRAL_LOW_SAMPLE"
        elif lower >= FILL_RATE_PASS_LOWER_BOUND:
            cell_status = "PASS_CELL"
        elif upper < FILL_RATE_WARN_LOWER_BOUND:
            cell_status = "FAIL_CELL_DIAGNOSTIC"
        else:
            cell_status = "WARN_CELL_DIAGNOSTIC"
        text = (
            f"{engine_mode}/{strategy_name}/{symbol} n={attempts} "
            f"fill={fill_rate:.3f} wilson_low={lower:.3f} "
            f"wilson_high={upper:.3f} fallbacks={fallbacks} status={cell_status}"
        )
        mature_rank = 0 if attempts >= FILL_RATE_MIN_SAMPLE else 1
        cells.append((mature_rank, lower, text))

    if not cells:
        return "stratified_weak_cells=none"
    cells.sort(key=lambda item: (item[0], item[1], item[2]))
    return "stratified_weak_cells=" + "; ".join(item[2] for item in cells[:max_cells])


def _fetch_fill_rate_stratification(cur: Any) -> str:
    cur.execute(
        """
        SELECT
            engine_mode,
            COALESCE(NULLIF(strategy_name, ''), 'unknown') AS strategy_name,
            symbol,
            COUNT(*)::int AS attempts,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason IS NULL)::int AS maker_fills,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason IS NOT NULL)::int AS fallbacks
        FROM trading.fills
        WHERE ts > NOW() - INTERVAL '7 days'
          AND engine_mode IN ('demo', 'live_demo', 'live')
          AND close_maker_attempt = TRUE
        GROUP BY 1, 2, 3
        ORDER BY attempts DESC, engine_mode, strategy_name, symbol
        LIMIT 64
        """
    )
    return _format_stratified_fill_cells(list(cur.fetchall() or []))


def _fetch_fallback_to_taker_cells(cur: Any) -> tuple[str, str]:
    cur.execute(
        """
        SELECT
            engine_mode,
            COUNT(*) FILTER (
                WHERE close_maker_fallback_reason IS NOT NULL
                  AND close_maker_fallback_reason <> 'not_attempted_safety_path'
            )::int AS fallback_required,
            COUNT(*) FILTER (
                WHERE close_maker_fallback_reason = ANY(%s::text[])
            )::int AS fallback_to_taker
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND ts > NOW() - INTERVAL '7 days'
          AND engine_mode IN ('demo', 'live_demo', 'live')
        GROUP BY engine_mode
        ORDER BY engine_mode
        """,
        (list(FALLBACK_TO_TAKER_REASONS),),
    )
    rows = list(cur.fetchall() or [])
    if not rows:
        return ("PASS", "ac18_fallback_to_taker_rate=no_fallback_samples")

    status = "PASS"
    cells: list[str] = []
    for engine_mode, required_raw, taker_raw in rows:
        required = _as_int(required_raw)
        taker = _as_int(taker_raw)
        if required <= 0:
            cells.append(f"{engine_mode}: n=0 status=NO_FALLBACK_SAMPLES")
            continue
        rate = taker / required
        lower, upper = _wilson_bounds(taker, required)
        if required < FILL_RATE_MIN_SAMPLE:
            cell_status = "WARN"
            verdict = "NEUTRAL_LOW_SAMPLE"
        elif lower >= FALLBACK_TO_TAKER_PASS_LOWER_BOUND:
            cell_status = "PASS"
            verdict = "PASS"
        elif lower >= FALLBACK_TO_TAKER_WARN_LOWER_BOUND:
            cell_status = "WARN"
            verdict = "WARN"
        else:
            cell_status = "FAIL"
            verdict = "FAIL"
        status = _severity_max(status, cell_status)
        cells.append(
            f"{engine_mode}: n={required}, fallback_to_taker={taker}, "
            f"rate={rate:.3f}, wilson95=[{lower:.3f},{upper:.3f}], verdict={verdict}"
        )
    return (status, "ac18_fallback_to_taker_rate=" + "; ".join(cells))


def _fetch_reject_sample_cells(cur: Any) -> str:
    cur.execute(
        """
        WITH reject_events AS (
            SELECT
                engine_mode,
                COALESCE(NULLIF(strategy_name, ''), 'unknown') AS strategy_name,
                symbol,
                CASE
                  WHEN close_maker_fallback_reason = 'postonly_reject'
                    OR details->>'reject_reason' = 'EC_PostOnlyWillTakeLiquidity'
                  THEN 'postonly_will_take'
                  WHEN close_maker_fallback_reason IN (
                      'rate_limit_pause_global',
                      'rate_limit_backoff_per_symbol'
                    )
                    OR details->>'reject_reason' = 'EC_ReachMaxPendingOrders'
                  THEN 'reach_max_pending'
                  WHEN close_maker_fallback_reason IS NOT NULL
                    AND close_maker_fallback_reason NOT IN (
                      'fast_escalate_safety_upgrade',
                      'not_attempted_safety_path',
                      'engine_shutdown_safety'
                    )
                  THEN 'other_reject_or_fallback'
                  ELSE NULL
                END AS reject_category
            FROM trading.fills
            WHERE ts > NOW() - INTERVAL '7 days'
              AND engine_mode IN ('demo', 'live_demo', 'live')
              AND close_maker_attempt = TRUE
        )
        SELECT
            engine_mode,
            strategy_name,
            symbol,
            COUNT(*) FILTER (WHERE reject_category = 'postonly_will_take')::int AS postonly_will_take,
            COUNT(*) FILTER (WHERE reject_category = 'reach_max_pending')::int AS reach_max_pending,
            COUNT(*) FILTER (WHERE reject_category = 'other_reject_or_fallback')::int AS other_reject_or_fallback,
            COUNT(*) FILTER (WHERE reject_category IS NOT NULL)::int AS total_reject_or_fallback_samples
        FROM reject_events
        GROUP BY 1, 2, 3
        HAVING COUNT(*) FILTER (WHERE reject_category IS NOT NULL) > 0
        ORDER BY total_reject_or_fallback_samples DESC, engine_mode, strategy_name, symbol
        LIMIT 8
        """
    )
    rows = list(cur.fetchall() or [])
    if not rows:
        return "reject_samples_by_cell=none"
    cells = []
    for row in rows:
        cells.append(
            f"{row[0]}/{row[1]}/{row[2]} postonly={_as_int(row[3])} "
            f"max_pending={_as_int(row[4])} other={_as_int(row[5])} total={_as_int(row[6])}"
        )
    return "reject_samples_by_cell=" + "; ".join(cells)


def check_close_maker_fill_rate(cur: Any) -> tuple[str, str]:
    """[70] close_maker_fill_rate — Wilson 95% CI gate / Wilson 信賴區間 gate。"""
    schema = _schema_guard(cur, "[70]")
    if schema is not None:
        return schema

    try:
        cur.execute(
            """
            SELECT
                engine_mode,
                COUNT(*)::int AS attempts,
                COUNT(*) FILTER (WHERE close_maker_fallback_reason IS NULL)::int AS maker_fills
            FROM trading.fills
            WHERE close_maker_attempt = TRUE
              AND ts > NOW() - INTERVAL '24 hours'
            GROUP BY engine_mode
            ORDER BY engine_mode
            """
        )
        rows = list(cur.fetchall() or [])
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[70] close_maker_fill_rate query failed: {type(exc).__name__}: {exc}")

    if not rows:
        return (
            "WARN",
            "[70] NEUTRAL_LOW_SAMPLE no close-maker attempts in 24h; "
            "cannot evaluate Wilson fill-rate gate",
        )

    status = "PASS"
    parts: list[str] = []
    for engine_mode, attempts_raw, maker_raw in rows:
        attempts = _as_int(attempts_raw)
        maker_fills = _as_int(maker_raw)
        fill_rate = maker_fills / attempts if attempts else 0.0
        lower, upper = _wilson_bounds(maker_fills, attempts)
        if attempts < FILL_RATE_MIN_SAMPLE:
            cell_status = "WARN"
            cell_note = "NEUTRAL_LOW_SAMPLE"
        elif lower >= FILL_RATE_PASS_LOWER_BOUND:
            cell_status = "PASS"
            cell_note = "PASS"
        elif upper < FILL_RATE_WARN_LOWER_BOUND:
            cell_status = "FAIL"
            cell_note = "FAIL"
        else:
            cell_status = "WARN"
            cell_note = "WARN"
        status = _severity_max(status, cell_status)
        parts.append(
            f"{engine_mode}: n={attempts}, maker={maker_fills}, fill={fill_rate:.3f}, "
            f"wilson95=[{lower:.3f},{upper:.3f}], verdict={cell_note}"
        )

    diag_parts: list[str] = []
    try:
        ac18_status, ac18_diag = _fetch_fallback_to_taker_cells(cur)
        status = _severity_max(status, ac18_status)
        diag_parts.append(ac18_diag)
    except Exception as exc:  # noqa: BLE001
        diag_parts.append(f"ac18_fallback_to_taker_rate=query_failed:{type(exc).__name__}")
    try:
        diag_parts.append(_fetch_fill_rate_stratification(cur))
    except Exception as exc:  # noqa: BLE001
        diag_parts.append(f"stratified_weak_cells=query_failed:{type(exc).__name__}")
    return (
        status,
        "[70] close_maker_fill_rate Wilson gate — "
        + "; ".join(parts)
        + "; "
        + "; ".join(diag_parts),
    )


def check_close_maker_zero_spine_lineage(cur: Any) -> tuple[str, str]:
    """[71] close_maker_zero_spine_lineage — close path 必須維持 0 spine row。"""
    schema = _schema_guard(cur, "[71]")
    if schema is not None:
        return schema

    try:
        cur.execute("SELECT to_regclass('agent.decision_objects') IS NOT NULL")
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[71] agent.decision_objects existence check failed: {type(exc).__name__}: {exc}")
    if not exists_row or not exists_row[0]:
        return ("FAIL", "[71] agent.decision_objects missing; cannot prove zero-spine close lineage")

    try:
        cur.execute(
            """
            SELECT COUNT(*)::int
            FROM trading.fills
            WHERE close_maker_attempt = TRUE
              AND ts > NOW() - INTERVAL '24 hours'
            """
        )
        attempts_row = cur.fetchone()
        attempts = _as_int(attempts_row[0] if attempts_row else 0)

        cur.execute(
            """
            SELECT COUNT(*)::int
            FROM agent.decision_objects
            WHERE object_type IN ('execution_plan', 'execution_report')
              AND payload::jsonb @> '{"is_close": true}'
              AND created_at > NOW() - INTERVAL '24 hours'
            """
        )
        spine_row = cur.fetchone()
        spine_close_rows = _as_int(spine_row[0] if spine_row else 0)
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[71] zero-spine lineage query failed: {type(exc).__name__}: {exc}")

    base = f"[71] close_maker_attempts_24h={attempts}, spine_close_rows_24h={spine_close_rows}"
    if spine_close_rows == 0:
        return ("PASS", base + " — W-C Caveat 2 holding; close path remains spine-free")
    if spine_close_rows <= 5:
        return ("WARN", base + " — small close spine leakage; investigate race/taxonomy before deploy")
    return ("FAIL", base + " — close path emitted spine rows; W-C Caveat 2 invariant broken")


def check_close_maker_fallback_null_ladder(cur: Any) -> tuple[str, str]:
    """[72] close_maker_fallback_null_ladder — fallback reason / JSON audit 完整性。"""
    schema = _schema_guard(cur, "[72]")
    if schema is not None:
        return schema

    try:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE close_maker_attempt = TRUE)::int AS attempts,
                COUNT(*) FILTER (
                    WHERE close_maker_attempt = FALSE
                      AND close_maker_fallback_reason IS NOT NULL
                )::int AS false_reason,
                COUNT(*) FILTER (
                    WHERE close_maker_attempt = TRUE
                      AND close_maker_fallback_reason IS NOT NULL
                      AND NOT (close_maker_fallback_reason = ANY(%s::text[]))
                )::int AS invalid_reason,
                COUNT(*) FILTER (
                    WHERE close_maker_attempt = TRUE
                      AND (
                        close_maker_fallback_reason IS NULL
                        OR NOT (close_maker_fallback_reason = ANY(%s::text[]))
                      )
                )::int AS not_safety_total,
                COUNT(*) FILTER (
                    WHERE close_maker_attempt = TRUE
                      AND (
                        close_maker_fallback_reason IS NULL
                        OR NOT (close_maker_fallback_reason = ANY(%s::text[]))
                      )
                      AND details ? 'close_initial_limit_price'
                      AND details ? 'close_final_fill_price'
                      AND details ? 'close_maker_eligible_reason'
                )::int AS jsonb_complete,
                COUNT(*) FILTER (
                    WHERE close_maker_attempt = TRUE
                      AND close_maker_fallback_reason IS NULL
                      AND NOT (details ? 'close_initial_limit_price')
                )::int AS maker_success_audit_missing
            FROM trading.fills
            WHERE ts > NOW() - INTERVAL '24 hours'
            """,
            (list(FALLBACK_REASONS), list(SAFETY_FALLBACK_REASONS), list(SAFETY_FALLBACK_REASONS)),
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[72] close_maker NULL ladder query failed: {type(exc).__name__}: {exc}")

    attempts = _as_int(row[0] if row else 0)
    false_reason = _as_int(row[1] if row else 0)
    invalid_reason = _as_int(row[2] if row else 0)
    not_safety_total = _as_int(row[3] if row else 0)
    jsonb_complete = _as_int(row[4] if row else 0)
    maker_success_audit_missing = _as_int(row[5] if row else 0)

    base = (
        f"[72] attempts_24h={attempts}, false_attempt_reason_n={false_reason}, "
        f"invalid_reason_n={invalid_reason}, not_safety_total={not_safety_total}, "
        f"jsonb_complete={jsonb_complete}, maker_success_audit_missing={maker_success_audit_missing}"
    )
    try:
        base += "; " + _fetch_reject_sample_cells(cur)
    except Exception as exc:  # noqa: BLE001
        base += f"; reject_samples_by_cell=query_failed:{type(exc).__name__}"

    if false_reason > 0 or invalid_reason > 0:
        return ("FAIL", base + " — V094 fallback enum / close_maker_attempt NULL ladder violation")
    if attempts < NULL_LADDER_MIN_SAMPLE:
        return ("WARN", base + f" — NEUTRAL_LOW_SAMPLE need >= {NULL_LADDER_MIN_SAMPLE} attempts")
    if not_safety_total == 0:
        return ("PASS", base + " — only safety-exempt fallback rows observed")

    ratio = jsonb_complete / not_safety_total
    base += f", completeness_ratio={ratio:.5f}"
    if ratio >= NULL_LADDER_PASS_RATIO:
        return ("PASS", base + " — close-maker audit JSON completeness holding")
    if ratio >= NULL_LADDER_WARN_RATIO:
        return ("WARN", base + " — close-maker audit JSON completeness near floor")
    return ("FAIL", base + " — close-maker audit JSON completeness below fail-closed floor")


def check_close_maker_rate_limit_backoff_coverage(cur: Any) -> tuple[str, str]:
    """[73] close_maker_rate_limit_backoff_coverage — per-symbol/global pause scope 覆蓋。"""
    schema = _schema_guard(cur, "[73]")
    if schema is not None:
        return schema

    try:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE close_maker_fallback_reason = 'rate_limit_pause_global'
                )::int AS global_pause_count,
                COUNT(*) FILTER (
                    WHERE close_maker_fallback_reason = 'rate_limit_backoff_per_symbol'
                )::int AS per_symbol_backoff_count,
                COUNT(*) FILTER (
                    WHERE close_maker_fallback_reason IN (
                        'rate_limit_pause_global',
                        'rate_limit_backoff_per_symbol'
                    )
                      AND COALESCE(details->>'rate_limit_scope', '') = ''
                )::int AS missing_scope_count,
                COUNT(*) FILTER (
                    WHERE close_maker_fallback_reason = 'rate_limit_pause_global'
                      AND COALESCE(details->>'rate_limit_scope', '') <> 'global'
                )::int AS bad_global_scope_count,
                COUNT(*) FILTER (
                    WHERE close_maker_fallback_reason = 'rate_limit_backoff_per_symbol'
                      AND COALESCE(details->>'rate_limit_scope', '') NOT IN (
                        'per_symbol',
                        'per-symbol',
                        'symbol'
                      )
                )::int AS bad_per_symbol_scope_count
            FROM trading.fills
            WHERE close_maker_attempt = TRUE
              AND ts > NOW() - INTERVAL '24 hours'
            """
        )
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[73] close_maker rate-limit scope query failed: {type(exc).__name__}: {exc}")

    global_pause = _as_int(row[0] if row else 0)
    per_symbol = _as_int(row[1] if row else 0)
    missing_scope = _as_int(row[2] if row else 0)
    bad_global_scope = _as_int(row[3] if row else 0)
    bad_per_symbol_scope = _as_int(row[4] if row else 0)
    base = (
        f"[73] global_pause_count={global_pause}, per_symbol_backoff_count={per_symbol}, "
        f"missing_scope_count={missing_scope}, bad_global_scope_count={bad_global_scope}, "
        f"bad_per_symbol_scope_count={bad_per_symbol_scope}"
    )

    if missing_scope > 0 or bad_global_scope > 0 or bad_per_symbol_scope > 0:
        return ("FAIL", base + " — rate_limit_scope coverage broken for V094 audit rows")
    if global_pause > RATE_LIMIT_GLOBAL_WARN_MAX or per_symbol > RATE_LIMIT_PER_SYMBOL_WARN_MAX:
        return ("FAIL", base + " — close-maker rate-limit backoff/global pause exceeds fail threshold")
    if global_pause > 0 or per_symbol > RATE_LIMIT_PER_SYMBOL_PASS_MAX:
        return ("WARN", base + " — close-maker rate-limit pressure elevated")
    return ("PASS", base + " — close-maker rate-limit/backoff scope coverage healthy")


def check_close_maker_reject_samples(cur: Any) -> tuple[str, str]:
    """[74] close_maker_reject_samples — PostOnly / max-pending reject sample proof."""
    schema = _schema_guard(cur, "[74]")
    if schema is not None:
        return schema

    try:
        cur.execute(
            """
            SELECT
                engine_mode,
                COUNT(*)::int AS attempts,
                COUNT(*) FILTER (
                    WHERE close_maker_fallback_reason = 'postonly_reject'
                       OR details->>'reject_reason' = 'EC_PostOnlyWillTakeLiquidity'
                )::int AS postonly_reject_samples,
                COUNT(*) FILTER (
                    WHERE close_maker_fallback_reason IN (
                        'rate_limit_pause_global',
                        'rate_limit_backoff_per_symbol'
                    )
                       OR details->>'reject_reason' = 'EC_ReachMaxPendingOrders'
                )::int AS max_pending_samples
            FROM trading.fills
            WHERE close_maker_attempt = TRUE
              AND ts > NOW() - INTERVAL '7 days'
              AND engine_mode IN ('demo', 'live_demo', 'live')
            GROUP BY engine_mode
            ORDER BY engine_mode
            """
        )
        rows = list(cur.fetchall() or [])
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[74] close_maker_reject_samples query failed: {type(exc).__name__}: {exc}")

    if not rows:
        return (
            "WARN",
            "[74] NEUTRAL_LOW_SAMPLE no close-maker attempts in 7d; "
            "cannot prove PostOnly/max-pending reject sample coverage",
        )

    status = "PASS"
    parts: list[str] = []
    for engine_mode, attempts_raw, postonly_raw, max_pending_raw in rows:
        attempts = _as_int(attempts_raw)
        postonly = _as_int(postonly_raw)
        max_pending = _as_int(max_pending_raw)
        cell_status = "PASS" if postonly > 0 and max_pending > 0 else "FAIL"
        status = _severity_max(status, cell_status)
        parts.append(
            f"{engine_mode}: attempts={attempts}, postonly_reject_samples={postonly}, "
            f"max_pending_samples={max_pending}, verdict={cell_status}"
        )

    msg = "[74] close_maker_reject_samples — " + "; ".join(parts)
    if status == "PASS":
        return ("PASS", msg + " — reject sample coverage present")
    return ("FAIL", msg + " — missing PostOnly or max-pending reject samples blocks promotion")

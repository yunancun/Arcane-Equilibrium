"""Scanner market-gate / opportunity-shadow healthchecks.
Scanner 行情 gate 後驗 / opportunity shadow 健康檢查。

MODULE_NOTE (EN): Owns [41], which verifies that scanner market/edge gates
are not silently blocking cells that later show positive demo/live_demo edge,
and [51], which verifies scanner opportunity shadow coverage/calibration
without enforcing any live trading gate. It is split from checks_execution.py
to keep each healthcheck module under the repository line cap.

MODULE_NOTE (中): 本檔負責 [41]，驗證 scanner 行情/edge gate 不會靜默擋下
後續證明為正 edge 的 demo/live_demo cell；並負責 [51]，驗證 scanner
opportunity shadow 的覆蓋率 / 校準性，但不接任何 live trading gate。從
checks_execution.py 拆出，維持 repo 行數硬上限。
"""

from __future__ import annotations

from .checks_execution import _as_float, _as_int

# [41] scanner market-gate confirmation.
# [41] scanner 行情 gate 後驗。
MARKET_GATE_CONFIRM_MIN_LABELS = 3

# [51] scanner opportunity shadow acceptance.
# [51] scanner opportunity shadow 驗收。
OPPORTUNITY_SHADOW_RECENT_WINDOW_HOURS = 3
OPPORTUNITY_SHADOW_LABEL_WINDOW_HOURS = 24
OPPORTUNITY_SHADOW_MIN_ROUTE_COVERAGE = 0.95
OPPORTUNITY_SHADOW_MIN_INTENT_COVERAGE = 0.95
OPPORTUNITY_SHADOW_MIN_INTENT_SAMPLE = 3
OPPORTUNITY_SHADOW_MIN_LABEL_SAMPLE = 10
OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_SAMPLE = 10
OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_AVG_NET_BPS = 0.0


def check_scanner_market_gate_confirmation(cur) -> tuple[str, str]:
    """[41] Confirm scanner market gates against subsequent realized edge.

    The scanner emits per-strategy market route judgements in
    ``trading.scanner_snapshots.candidates[*].strategy_judgments``. This check
    asks whether cells gated out by market judgement / negative-edge gates later
    show negative demo/live_demo post-fee edge while that gate is still active.
    If a later scanner snapshot marks the route compatible again, labels after
    that transition are excluded because they no longer contradict the old gate.
    Lack of labels is WARN, not FAIL, because a successful gate can intentionally
    suppress all future opens.

    [41] scanner 行情 gate 後驗。scanner 在 snapshot candidate 中輸出分策略
    market route judgement；本 check 觀察被 gate / 負 edge gate 擋下的 cell，
    且只統計 gate 仍生效期間內的後續 demo/live_demo post-fee label。若後續
    scanner snapshot 已將 route 標回 compatible，之後的 label 不再算作舊 gate
    的反證。無 label 是 WARN 而非 FAIL，因為成功 gate 可能本來就會抑制後續開倉。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    try:
        cur.execute("SELECT to_regclass('trading.scanner_snapshots') IS NOT NULL")
        scanner_exists = cur.fetchone()
        cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
        mlde_exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"scanner market-gate table check failed: {exc}")
    if not scanner_exists or not scanner_exists[0]:
        return ("WARN", "trading.scanner_snapshots missing — cannot confirm scanner gates")
    if not mlde_exists or not mlde_exists[0]:
        return ("WARN", "learning.mlde_edge_training_rows missing — cannot confirm scanner gates")

    sql = """
WITH raw_routes AS (
    SELECT
        s.ts AS route_ts,
        c.candidate->>'symbol' AS symbol,
        j.key AS strategy_name,
        lower(coalesce(j.value->>'market_status', '')) AS market_status,
        lower(coalesce(j.value->>'route_mode', '')) AS route_mode,
        lower(coalesce(j.value->>'edge_status', '')) AS edge_status,
        coalesce(j.value->>'route_reason', '') AS route_reason,
        (
            lower(coalesce(j.value->>'route_mode', '')) = 'market_gate'
         OR lower(coalesce(j.value->>'market_status', '')) = 'edge_quarantine'
         OR (
              lower(coalesce(j.value->>'route_mode', '')) = 'exploration_only'
          AND lower(coalesce(j.value->>'edge_status', '')) IN ('robust_negative', 'posterior_negative')
            )
        ) AS is_gate
    FROM trading.scanner_snapshots s
    CROSS JOIN LATERAL jsonb_array_elements(s.candidates) AS c(candidate)
    CROSS JOIN LATERAL jsonb_each(coalesce(c.candidate->'strategy_judgments', '{}'::jsonb)) AS j(key, value)
    WHERE s.ts > now() - interval '24 hours'
      AND c.candidate ? 'symbol'
),
raw_gates AS (
    SELECT *
    FROM raw_routes
    WHERE is_gate
      AND coalesce(strategy_name, '') <> ''
      AND coalesce(symbol, '') <> ''
),
gate_segments AS (
    SELECT
        g.strategy_name,
        g.symbol,
        g.route_ts AS first_gate_ts,
        g.route_reason AS sample_reason,
        (
            SELECT min(r.route_ts)
            FROM raw_routes r
            WHERE r.strategy_name = g.strategy_name
              AND r.symbol = g.symbol
              AND r.route_ts > g.route_ts
              AND NOT r.is_gate
        ) AS next_compatible_ts
    FROM raw_gates g
),
label_segments AS (
    SELECT
        g.strategy_name,
        g.symbol,
        g.sample_reason,
        count(m.*)::int AS label_n,
        avg(m.net_bps_after_fee)::float8 AS avg_net_bps
    FROM gate_segments g
    LEFT JOIN learning.mlde_edge_training_rows m
      ON m.strategy_name = g.strategy_name
     AND m.symbol = g.symbol
     AND m.ts > g.first_gate_ts
     AND m.ts <= least(
            g.first_gate_ts + interval '12 hours',
            coalesce(g.next_compatible_ts, g.first_gate_ts + interval '12 hours')
         )
     AND m.engine_mode IN ('demo', 'live_demo')
     AND m.attribution_chain_ok
     AND m.net_bps_after_fee IS NOT NULL
    GROUP BY g.strategy_name, g.symbol, g.first_gate_ts, g.sample_reason
)
SELECT
    count(DISTINCT strategy_name || '::' || symbol)::int AS gate_cells,
    count(*)::int AS gate_events,
    count(*) FILTER (WHERE label_n >= %s)::int AS scoreable_cells,
    count(*) FILTER (WHERE label_n >= %s AND avg_net_bps < 0)::int AS confirmed_negative,
    count(*) FILTER (WHERE label_n >= %s AND avg_net_bps >= 0)::int AS contradicted,
    count(*) FILTER (WHERE label_n > 0 AND label_n < %s)::int AS low_sample_cells
FROM label_segments
"""
    bad_sql = """
WITH raw_routes AS (
    SELECT
        s.ts AS route_ts,
        c.candidate->>'symbol' AS symbol,
        j.key AS strategy_name,
        coalesce(j.value->>'route_reason', '') AS route_reason,
        lower(coalesce(j.value->>'market_status', '')) AS market_status,
        lower(coalesce(j.value->>'route_mode', '')) AS route_mode,
        lower(coalesce(j.value->>'edge_status', '')) AS edge_status,
        (
            lower(coalesce(j.value->>'route_mode', '')) = 'market_gate'
         OR lower(coalesce(j.value->>'market_status', '')) = 'edge_quarantine'
         OR (
              lower(coalesce(j.value->>'route_mode', '')) = 'exploration_only'
          AND lower(coalesce(j.value->>'edge_status', '')) IN ('robust_negative', 'posterior_negative')
            )
        ) AS is_gate
    FROM trading.scanner_snapshots s
    CROSS JOIN LATERAL jsonb_array_elements(s.candidates) AS c(candidate)
    CROSS JOIN LATERAL jsonb_each(coalesce(c.candidate->'strategy_judgments', '{}'::jsonb)) AS j(key, value)
    WHERE s.ts > now() - interval '24 hours'
      AND c.candidate ? 'symbol'
),
raw_gates AS (
    SELECT *
    FROM raw_routes
    WHERE is_gate
      AND coalesce(strategy_name, '') <> ''
      AND coalesce(symbol, '') <> ''
),
gate_segments AS (
    SELECT
        g.strategy_name,
        g.symbol,
        g.route_ts AS first_gate_ts,
        g.route_reason AS sample_reason,
        (
            SELECT min(r.route_ts)
            FROM raw_routes r
            WHERE r.strategy_name = g.strategy_name
              AND r.symbol = g.symbol
              AND r.route_ts > g.route_ts
              AND NOT r.is_gate
        ) AS next_compatible_ts
    FROM raw_gates g
),
label_segments AS (
    SELECT
        g.strategy_name,
        g.symbol,
        g.sample_reason,
        count(m.*)::int AS label_n,
        avg(m.net_bps_after_fee)::float8 AS avg_net_bps
    FROM gate_segments g
    JOIN learning.mlde_edge_training_rows m
      ON m.strategy_name = g.strategy_name
     AND m.symbol = g.symbol
     AND m.ts > g.first_gate_ts
     AND m.ts <= least(
            g.first_gate_ts + interval '12 hours',
            coalesce(g.next_compatible_ts, g.first_gate_ts + interval '12 hours')
         )
     AND m.engine_mode IN ('demo', 'live_demo')
     AND m.attribution_chain_ok
     AND m.net_bps_after_fee IS NOT NULL
    GROUP BY g.strategy_name, g.symbol, g.first_gate_ts, g.sample_reason
)
SELECT strategy_name, symbol, label_n, avg_net_bps, sample_reason
FROM label_segments
WHERE label_n >= %s AND avg_net_bps >= 0
ORDER BY avg_net_bps DESC, label_n DESC
LIMIT 6
"""
    try:
        cur.execute(
            sql,
            (
                MARKET_GATE_CONFIRM_MIN_LABELS,
                MARKET_GATE_CONFIRM_MIN_LABELS,
                MARKET_GATE_CONFIRM_MIN_LABELS,
                MARKET_GATE_CONFIRM_MIN_LABELS,
            ),
        )
        row = cur.fetchone()
        cur.execute(bad_sql, (MARKET_GATE_CONFIRM_MIN_LABELS,))
        contradicted_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"scanner market-gate confirmation query failed: {type(exc).__name__}: {exc}")

    gate_cells = _as_int(row[0]) if row else 0
    gate_events = _as_int(row[1]) if row else 0
    scoreable = _as_int(row[2]) if row else 0
    confirmed = _as_int(row[3]) if row else 0
    contradicted = _as_int(row[4]) if row else 0
    low_sample = _as_int(row[5]) if row else 0

    base = (
        f"24h scanner gates: events={gate_events}, cells={gate_cells}, "
        f"scoreable_cells={scoreable} (min_labels={MARKET_GATE_CONFIRM_MIN_LABELS}), "
        f"confirmed_negative={confirmed}, contradicted={contradicted}, low_sample={low_sample}"
    )
    if gate_cells == 0:
        return ("PASS", base + " — no market/edge gates fired yet")
    if contradicted_rows:
        parts = [
            f"{r[0]}/{r[1]} n={_as_int(r[2])} avg={_as_float(r[3]):.2f}bps reason={str(r[4])[:80]}"
            for r in contradicted_rows
        ]
        return ("FAIL", base + " — gated cells later non-negative: " + "; ".join(parts))
    if scoreable == 0:
        return ("WARN", base + " — gates fired but no subsequent labels yet")
    return ("PASS", base + " — gated cells with labels were negative post-fee")


def _pct(numer: int, denom: int) -> str:
    """Return a compact percentage string for healthcheck messages."""
    if denom <= 0:
        return "n/a"
    return f"{100.0 * numer / denom:.1f}%"


def _fmt_float(value: object, suffix: str = "") -> str:
    """Format optional SQL float values without hiding NULL as zero."""
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}{suffix}"
    except Exception:  # noqa: BLE001
        return "n/a"


def check_scanner_opportunity_shadow_acceptance(cur) -> tuple[str, str]:
    """[51] Verify scanner opportunity shadow coverage and calibration.

    This is intentionally a shadow acceptance check, not an enforcement gate.
    It verifies three neutral contracts:
      1. recent scanner snapshots carry ``strategy_judgments.*.opportunity``;
      2. recent scanner-origin intents preserve ``details.scanner.opportunity``;
      3. MLDE row proof preserves the same shadow object and lets us compare
         ``opportunity_lcb_bps`` against realized post-fee ``net_bps_after_fee``.

    Low labeled sample is WARN rather than FAIL because a new shadow signal
    needs time to accumulate outcomes. Coverage regression is FAIL because it
    means the row-proof contract is broken before learning can start.

    [51] scanner opportunity shadow 驗收。這不是交易 gate，只驗三個中性
    contract：scanner snapshot 有 opportunity、intent details 保留
    opportunity、MLDE row proof 可把 opportunity_lcb_bps 對上實現後 fee net
    bps。label 樣本不足是 WARN；覆蓋率斷裂才 FAIL。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    try:
        cur.execute("SELECT to_regclass('trading.scanner_snapshots') IS NOT NULL")
        scanner_exists = cur.fetchone()
        cur.execute("SELECT to_regclass('trading.intents') IS NOT NULL")
        intents_exists = cur.fetchone()
        cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
        mlde_exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"scanner opportunity table check failed: {exc}")
    if not scanner_exists or not scanner_exists[0]:
        return ("WARN", "trading.scanner_snapshots missing — cannot verify opportunity shadow")
    if not intents_exists or not intents_exists[0]:
        return ("WARN", "trading.intents missing — cannot verify opportunity shadow")
    if not mlde_exists or not mlde_exists[0]:
        return ("WARN", "learning.mlde_edge_training_rows missing — cannot verify opportunity shadow")

    snapshot_sql = """
WITH routes AS (
    SELECT
        s.scan_id,
        j.value AS judgement
    FROM trading.scanner_snapshots s
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(s.candidates) = 'array' THEN s.candidates
            ELSE '[]'::jsonb
        END
    ) AS c(candidate)
    CROSS JOIN LATERAL jsonb_each(
        CASE
            WHEN jsonb_typeof(c.candidate->'strategy_judgments') = 'object'
                THEN c.candidate->'strategy_judgments'
            ELSE '{}'::jsonb
        END
    ) AS j(key, value)
    WHERE s.ts > now() - (%s * interval '1 hour')
)
SELECT
    count(*)::int AS route_n,
    count(*) FILTER (WHERE judgement ? 'opportunity')::int AS opportunity_n,
    count(DISTINCT scan_id)::int AS scan_n
FROM routes
"""
    intent_sql = """
SELECT
    count(*)::int AS scanner_intent_n,
    count(*) FILTER (WHERE details #> '{scanner,opportunity}' IS NOT NULL)::int AS opportunity_intent_n
FROM trading.intents
WHERE ts > now() - (%s * interval '1 hour')
  AND engine_mode IN ('demo', 'live_demo')
  AND details ? 'scanner'
"""
    label_sql = """
WITH labeled AS (
    SELECT
        (metadata #>> '{scanner,opportunity,opportunity_lcb_bps}')::float8 AS opportunity_lcb_bps,
        net_bps_after_fee
    FROM learning.mlde_edge_training_rows
    WHERE ts > now() - (%s * interval '1 hour')
      AND engine_mode IN ('demo', 'live_demo')
      AND attribution_chain_ok
      AND net_bps_after_fee IS NOT NULL
      AND metadata #> '{scanner,opportunity}' IS NOT NULL
      AND jsonb_typeof(metadata #> '{scanner,opportunity,opportunity_lcb_bps}') = 'number'
)
SELECT
    count(*)::int AS label_n,
    count(*) FILTER (WHERE opportunity_lcb_bps > 0)::int AS positive_lcb_n,
    avg(net_bps_after_fee)::float8 AS avg_net_bps,
    avg(net_bps_after_fee) FILTER (WHERE opportunity_lcb_bps > 0)::float8 AS positive_lcb_avg_net_bps,
    avg(net_bps_after_fee) FILTER (WHERE opportunity_lcb_bps <= 0)::float8 AS nonpositive_lcb_avg_net_bps,
    corr(opportunity_lcb_bps, net_bps_after_fee)::float8 AS lcb_realized_corr
FROM labeled
"""
    bad_positive_sql = """
SELECT
    strategy_name,
    symbol,
    count(*)::int AS label_n,
    avg(net_bps_after_fee)::float8 AS avg_net_bps,
    avg((metadata #>> '{scanner,opportunity,opportunity_lcb_bps}')::float8)::float8 AS avg_lcb_bps
FROM learning.mlde_edge_training_rows
WHERE ts > now() - (%s * interval '1 hour')
  AND engine_mode IN ('demo', 'live_demo')
  AND attribution_chain_ok
  AND net_bps_after_fee IS NOT NULL
  AND metadata #> '{scanner,opportunity}' IS NOT NULL
  AND jsonb_typeof(metadata #> '{scanner,opportunity,opportunity_lcb_bps}') = 'number'
  AND (metadata #>> '{scanner,opportunity,opportunity_lcb_bps}')::float8 > 0
GROUP BY strategy_name, symbol
HAVING count(*) >= %s
   AND avg(net_bps_after_fee) < %s
ORDER BY avg(net_bps_after_fee), label_n DESC
LIMIT 6
"""
    try:
        cur.execute(snapshot_sql, (OPPORTUNITY_SHADOW_RECENT_WINDOW_HOURS,))
        snapshot_row = cur.fetchone()
        cur.execute(intent_sql, (OPPORTUNITY_SHADOW_RECENT_WINDOW_HOURS,))
        intent_row = cur.fetchone()
        cur.execute(label_sql, (OPPORTUNITY_SHADOW_LABEL_WINDOW_HOURS,))
        label_row = cur.fetchone()
        cur.execute(
            bad_positive_sql,
            (
                OPPORTUNITY_SHADOW_LABEL_WINDOW_HOURS,
                OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_SAMPLE,
                OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_AVG_NET_BPS,
            ),
        )
        bad_positive_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"scanner opportunity shadow query failed: {type(exc).__name__}: {exc}")

    route_n = _as_int(snapshot_row[0]) if snapshot_row else 0
    route_opp_n = _as_int(snapshot_row[1]) if snapshot_row else 0
    scan_n = _as_int(snapshot_row[2]) if snapshot_row else 0
    intent_n = _as_int(intent_row[0]) if intent_row else 0
    intent_opp_n = _as_int(intent_row[1]) if intent_row else 0
    label_n = _as_int(label_row[0]) if label_row else 0
    positive_lcb_n = _as_int(label_row[1]) if label_row else 0
    avg_net = label_row[2] if label_row else None
    positive_avg_net = label_row[3] if label_row else None
    nonpositive_avg_net = label_row[4] if label_row else None
    corr = label_row[5] if label_row else None

    route_coverage = (route_opp_n / route_n) if route_n else 1.0
    intent_coverage = (intent_opp_n / intent_n) if intent_n else 1.0
    base = (
        f"{OPPORTUNITY_SHADOW_RECENT_WINDOW_HOURS}h snapshot routes={route_opp_n}/{route_n} "
        f"({_pct(route_opp_n, route_n)}), scans={scan_n}; "
        f"{OPPORTUNITY_SHADOW_RECENT_WINDOW_HOURS}h scanner intents={intent_opp_n}/{intent_n} "
        f"({_pct(intent_opp_n, intent_n)}); "
        f"{OPPORTUNITY_SHADOW_LABEL_WINDOW_HOURS}h labels={label_n}, "
        f"positive_lcb_n={positive_lcb_n}, avg_net={_fmt_float(avg_net, 'bps')}, "
        f"positive_avg={_fmt_float(positive_avg_net, 'bps')}, "
        f"nonpositive_avg={_fmt_float(nonpositive_avg_net, 'bps')}, "
        f"corr={_fmt_float(corr)}"
    )

    if route_n == 0:
        return ("WARN", base + " — no recent scanner routes to verify")
    if route_coverage < OPPORTUNITY_SHADOW_MIN_ROUTE_COVERAGE:
        return (
            "FAIL",
            base
            + f" — snapshot opportunity coverage below "
            + f"{OPPORTUNITY_SHADOW_MIN_ROUTE_COVERAGE:.0%} contract",
        )
    if intent_n >= OPPORTUNITY_SHADOW_MIN_INTENT_SAMPLE and intent_coverage < OPPORTUNITY_SHADOW_MIN_INTENT_COVERAGE:
        return (
            "FAIL",
            base
            + f" — intent opportunity coverage below "
            + f"{OPPORTUNITY_SHADOW_MIN_INTENT_COVERAGE:.0%} contract",
        )
    if bad_positive_rows:
        parts = [
            f"{r[0]}/{r[1]} n={_as_int(r[2])} avg={_as_float(r[3]):.2f}bps lcb={_as_float(r[4]):.2f}bps"
            for r in bad_positive_rows
        ]
        return ("FAIL", base + " — positive opportunity LCB realized negative: " + "; ".join(parts))
    if label_n < OPPORTUNITY_SHADOW_MIN_LABEL_SAMPLE:
        return (
            "WARN",
            base
            + f" — insufficient labeled outcomes for calibration "
            + f"(min={OPPORTUNITY_SHADOW_MIN_LABEL_SAMPLE})",
        )
    if (
        positive_lcb_n >= OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_SAMPLE
        and positive_avg_net is not None
        and float(positive_avg_net) < OPPORTUNITY_SHADOW_MIN_POSITIVE_LCB_AVG_NET_BPS
    ):
        return (
            "FAIL",
            base
            + " — positive opportunity LCB bucket is negative post-fee",
        )
    return ("PASS", base + " — opportunity shadow contract healthy")

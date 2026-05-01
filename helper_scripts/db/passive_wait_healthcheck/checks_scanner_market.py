"""Scanner market-gate confirmation healthcheck.
Scanner 行情 gate 後驗健康檢查。

MODULE_NOTE (EN): Owns [41], which verifies that scanner market/edge gates
are not silently blocking cells that later show positive demo/live_demo edge.
It is split from checks_execution.py to keep each healthcheck module under the
repository 1200-line hard cap.

MODULE_NOTE (中): 本檔負責 [41]，驗證 scanner 行情/edge gate 不會靜默擋下
後續證明為正 edge 的 demo/live_demo cell。從 checks_execution.py 拆出，維持
repo 1200 行硬上限。
"""

from __future__ import annotations

from .checks_execution import _as_float, _as_int

# [41] scanner market-gate confirmation.
# [41] scanner 行情 gate 後驗。
MARKET_GATE_CONFIRM_MIN_LABELS = 3


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

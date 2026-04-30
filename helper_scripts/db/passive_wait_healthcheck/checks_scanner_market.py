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
    asks whether cells gated out by market judgement / early negative-edge
    quarantine later show negative demo/live_demo post-fee edge when labels are
    available. Lack of labels is WARN, not FAIL, because a successful gate can
    intentionally suppress all future opens.

    [41] scanner 行情 gate 後驗。scanner 在 snapshot candidate 中輸出分策略
    market route judgement；本 check 觀察被 gate / 早期負 edge quarantine
    擋下的 cell，在後續有 demo/live_demo post-fee label 時是否確實偏負。
    無 label 是 WARN 而非 FAIL，因為成功 gate 可能本來就會抑制後續開倉。
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
WITH raw_gates AS (
    SELECT
        s.ts AS gate_ts,
        c.candidate->>'symbol' AS symbol,
        j.key AS strategy_name,
        lower(coalesce(j.value->>'market_status', '')) AS market_status,
        lower(coalesce(j.value->>'route_mode', '')) AS route_mode,
        lower(coalesce(j.value->>'edge_status', '')) AS edge_status,
        coalesce(j.value->>'route_reason', '') AS route_reason
    FROM trading.scanner_snapshots s
    CROSS JOIN LATERAL jsonb_array_elements(s.candidates) AS c(candidate)
    CROSS JOIN LATERAL jsonb_each(coalesce(c.candidate->'strategy_judgments', '{}'::jsonb)) AS j(key, value)
    WHERE s.ts > now() - interval '24 hours'
      AND c.candidate ? 'symbol'
      AND (
            lower(coalesce(j.value->>'route_mode', '')) = 'market_gate'
         OR lower(coalesce(j.value->>'market_status', '')) = 'edge_quarantine'
         OR (
              lower(coalesce(j.value->>'route_mode', '')) = 'exploration_only'
          AND lower(coalesce(j.value->>'edge_status', '')) IN ('robust_negative', 'posterior_negative')
            )
      )
),
gate_cells AS (
    SELECT
        strategy_name,
        symbol,
        min(gate_ts) AS first_gate_ts,
        count(*)::int AS gate_count,
        max(route_reason) AS sample_reason
    FROM raw_gates
    WHERE coalesce(strategy_name, '') <> ''
      AND coalesce(symbol, '') <> ''
    GROUP BY strategy_name, symbol
),
label_cells AS (
    SELECT
        g.strategy_name,
        g.symbol,
        g.gate_count,
        g.sample_reason,
        count(m.*)::int AS label_n,
        avg(m.net_bps_after_fee)::float8 AS avg_net_bps
    FROM gate_cells g
    LEFT JOIN learning.mlde_edge_training_rows m
      ON m.strategy_name = g.strategy_name
     AND m.symbol = g.symbol
     AND m.ts > g.first_gate_ts
     AND m.ts <= g.first_gate_ts + interval '12 hours'
     AND m.engine_mode IN ('demo', 'live_demo')
     AND m.attribution_chain_ok
     AND m.net_bps_after_fee IS NOT NULL
    GROUP BY g.strategy_name, g.symbol, g.gate_count, g.sample_reason
)
SELECT
    count(*)::int AS gate_cells,
    coalesce(sum(gate_count), 0)::int AS gate_events,
    count(*) FILTER (WHERE label_n >= %s)::int AS scoreable_cells,
    count(*) FILTER (WHERE label_n >= %s AND avg_net_bps < 0)::int AS confirmed_negative,
    count(*) FILTER (WHERE label_n >= %s AND avg_net_bps >= 0)::int AS contradicted,
    count(*) FILTER (WHERE label_n > 0 AND label_n < %s)::int AS low_sample_cells
FROM label_cells
"""
    bad_sql = """
WITH raw_gates AS (
    SELECT
        s.ts AS gate_ts,
        c.candidate->>'symbol' AS symbol,
        j.key AS strategy_name,
        coalesce(j.value->>'route_reason', '') AS route_reason,
        lower(coalesce(j.value->>'market_status', '')) AS market_status,
        lower(coalesce(j.value->>'route_mode', '')) AS route_mode,
        lower(coalesce(j.value->>'edge_status', '')) AS edge_status
    FROM trading.scanner_snapshots s
    CROSS JOIN LATERAL jsonb_array_elements(s.candidates) AS c(candidate)
    CROSS JOIN LATERAL jsonb_each(coalesce(c.candidate->'strategy_judgments', '{}'::jsonb)) AS j(key, value)
    WHERE s.ts > now() - interval '24 hours'
      AND c.candidate ? 'symbol'
      AND (
            lower(coalesce(j.value->>'route_mode', '')) = 'market_gate'
         OR lower(coalesce(j.value->>'market_status', '')) = 'edge_quarantine'
         OR (
              lower(coalesce(j.value->>'route_mode', '')) = 'exploration_only'
          AND lower(coalesce(j.value->>'edge_status', '')) IN ('robust_negative', 'posterior_negative')
            )
      )
),
gate_cells AS (
    SELECT strategy_name, symbol, min(gate_ts) AS first_gate_ts, max(route_reason) AS sample_reason
    FROM raw_gates
    WHERE coalesce(strategy_name, '') <> ''
      AND coalesce(symbol, '') <> ''
    GROUP BY strategy_name, symbol
),
label_cells AS (
    SELECT
        g.strategy_name,
        g.symbol,
        g.sample_reason,
        count(m.*)::int AS label_n,
        avg(m.net_bps_after_fee)::float8 AS avg_net_bps
    FROM gate_cells g
    JOIN learning.mlde_edge_training_rows m
      ON m.strategy_name = g.strategy_name
     AND m.symbol = g.symbol
     AND m.ts > g.first_gate_ts
     AND m.ts <= g.first_gate_ts + interval '12 hours'
     AND m.engine_mode IN ('demo', 'live_demo')
     AND m.attribution_chain_ok
     AND m.net_bps_after_fee IS NOT NULL
    GROUP BY g.strategy_name, g.symbol, g.sample_reason
)
SELECT strategy_name, symbol, label_n, avg_net_bps, sample_reason
FROM label_cells
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

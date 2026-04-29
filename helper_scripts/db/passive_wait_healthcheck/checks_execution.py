"""Execution-shape healthchecks.
執行形態 healthcheck。

These checks compare configuration intent against the runtime records written
by the engine. They stay separate from ``checks_strategy.py`` so that already
large module does not grow further.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

MAKER_FEE_RATE = 0.00020
TAKER_FEE_RATE = 0.00055
MAKER_FEE_CUTOFF = (MAKER_FEE_RATE + TAKER_FEE_RATE) / 2.0
MAKER_FEE_DROP_TARGET_PCT = 60.0
MAKER_FILL_MIN_SAMPLE = 30


def _load_demo_strategy_params() -> tuple[dict[str, Any] | None, str]:
    """Load ``settings/strategy_params_demo.toml`` fail-soft.
    讀取 demo strategy params TOML；失敗時回診斷，不拋例外。
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        except ImportError:
            return (None, "tomllib/tomli unavailable")

    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))
    toml_path = base / "settings" / "strategy_params_demo.toml"
    if not toml_path.exists():
        return (None, f"strategy_params_demo.toml not found at {toml_path}")

    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as exc:  # noqa: BLE001 — healthcheck fail-soft
        return (None, f"TOML parse error: {exc}")
    if not isinstance(data, dict):
        return (None, "strategy_params_demo.toml did not parse to a table")
    return (data, "ok")


def _maker_enabled_demo_strategies() -> tuple[list[str], str]:
    """Return active demo strategies that intend maker entries.
    回傳 demo TOML 中 active 且 use_maker_entry=true 的策略。
    """
    data, diag = _load_demo_strategy_params()
    if data is None:
        return ([], diag)

    strategies: list[str] = []
    for name, section in data.items():
        if not isinstance(section, dict):
            continue
        if section.get("active") is False:
            continue
        if section.get("use_maker_entry") is True:
            strategies.append(str(name))
    return (sorted(strategies), "ok")


def check_maker_entry_intent_drift(cur) -> tuple[str, str]:
    """[32] Demo maker-entry intent drift.

    If demo TOML says a strategy should use maker entries, its recent entry
    intents should not be ``order_type='market'``. This checks
    ``trading.intents`` rather than ``trading.orders`` because close orders are
    intentionally Market and the orders table does not persist ``is_close``.

    [32] Demo maker 入場 intent 漂移。若 demo TOML 指定 maker entry，近期
    入場 intent 不應仍為 market。使用 trading.intents 而非 orders，因為
    平倉本來就是 Market，orders 表也沒有 is_close 可安全過濾。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    strategies, diag = _maker_enabled_demo_strategies()
    if not strategies:
        if diag == "ok":
            return ("PASS", "no active demo strategies with use_maker_entry=true")
        return ("WARN", f"maker-entry TOML read unavailable: {diag}")

    placeholders = ", ".join(["%s"] * len(strategies))
    try:
        cur.execute(
            f"""
            SELECT strategy_name, lower(order_type) AS order_type, COUNT(*)::int AS n
            FROM trading.intents
            WHERE ts > now() - interval '30 minutes'
              AND engine_mode = 'demo'
              AND strategy_name IN ({placeholders})
            GROUP BY strategy_name, lower(order_type)
            ORDER BY strategy_name, lower(order_type)
            """,
            tuple(strategies),
        )
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — healthcheck fail-soft
        return ("WARN", f"maker-entry intent drift query failed: {exc}")

    totals: dict[str, int] = {name: 0 for name in strategies}
    market: dict[str, int] = {name: 0 for name in strategies}
    limit: dict[str, int] = {name: 0 for name in strategies}
    other: dict[str, int] = {name: 0 for name in strategies}
    for strategy_name, order_type, n in rows:
        name = str(strategy_name)
        typ = str(order_type or "").lower()
        count = int(n or 0)
        totals[name] = totals.get(name, 0) + count
        if typ == "market":
            market[name] = market.get(name, 0) + count
        elif typ == "limit":
            limit[name] = limit.get(name, 0) + count
        else:
            other[name] = other.get(name, 0) + count

    active_rows = [name for name, total in totals.items() if total > 0]
    if not active_rows:
        return (
            "PASS",
            "maker-enabled demo strategies emitted no entry intents in 30m "
            f"({', '.join(strategies)})",
        )

    parts = [
        f"{name}: total={totals[name]}, market={market[name]}, "
        f"limit={limit[name]}, other={other[name]}"
        for name in active_rows
    ]
    bad = [name for name in active_rows if market[name] > 0]
    if bad:
        return (
            "FAIL",
            "maker-enabled demo strategies emitted market entry intents — "
            + "; ".join(parts)
            + " — check StrategyParams partial-merge / persisted replay drift",
        )
    return ("PASS", "maker-entry intent shape ok — " + "; ".join(parts))


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fee_drop_pct(avg_fee_rate: float) -> float:
    fee_span = TAKER_FEE_RATE - MAKER_FEE_RATE
    if fee_span <= 0.0:
        return 0.0
    pct = (TAKER_FEE_RATE - avg_fee_rate) / fee_span * 100.0
    return max(0.0, min(100.0, pct))


def _format_strategy_slices(rows: list[tuple[Any, ...]]) -> str:
    parts: list[str] = []
    for row in rows[:8]:
        name = str(row[0] or "unknown")
        total = _as_int(row[1])
        maker_like = _as_int(row[2])
        avg_fee_rate = _as_float(row[3], TAKER_FEE_RATE)
        maker_pct = maker_like / total * 100.0 if total else 0.0
        fee_drop = _fee_drop_pct(avg_fee_rate)
        parts.append(
            f"{name}: n={total}, maker_like={maker_pct:.1f}%, "
            f"avg_fee={avg_fee_rate * 10_000:.2f}bps, fee_drop={fee_drop:.1f}%"
        )
    return "; ".join(parts) if parts else "no per-strategy rows"


_MAKER_FILL_CTE = """
WITH entry_fills AS (
    SELECT
        f.strategy_name,
        lower(coalesce(f.liquidity_role, '')) AS liquidity_role,
        lower(coalesce(o.order_type, '')) AS order_type,
        lower(coalesce(o.time_in_force, '')) AS time_in_force,
        coalesce(nullif(f.fee_rate, 0), %s)::float8 AS effective_fee_rate,
        CASE
            WHEN lower(coalesce(f.liquidity_role, '')) = 'maker'
              OR coalesce(nullif(f.fee_rate, 0), %s) <= %s
            THEN 1
            ELSE 0
        END AS maker_like
    FROM trading.fills f
    LEFT JOIN trading.orders o
      ON o.order_id = f.order_id
     AND o.ts > now() - interval '8 days'
    WHERE f.ts > now() - interval '7 days'
      AND f.engine_mode IN ('demo', 'live_demo')
      AND coalesce(f.strategy_name, '') <> ''
      AND f.strategy_name NOT LIKE 'risk_close:%%'
      AND f.strategy_name NOT LIKE 'strategy_close:%%'
      AND f.strategy_name NOT LIKE 'ipc_close%%'
      AND f.strategy_name NOT LIKE 'unattributed:%%'
      AND coalesce(f.exit_source, '') = ''
)
"""


def check_maker_fill_rate(cur) -> tuple[str, str]:
    """[33] G2-01 PostOnly maker-fill / fee-drop monitor.

    G2-01 validates whether PostOnly demo execution actually reduces fees.
    Earlier docs mistakenly mapped this to [3], but [3] is the
    exit_features writer check. This dedicated check measures the last 7d of
    demo/live_demo entry fills, joins orders only for limit diagnostics, and
    scores acceptance on effective fee-drop from taker 5.5bps toward maker
    2.0bps. ``trading.orders.time_in_force`` is not written by the current
    Rust order writer, so fee_rate/liquidity_role are the runtime truth.

    [33] G2-01 PostOnly maker 成交 / fee-drop 監控。過去文件曾誤標 [3]，
    但 [3] 實際是 exit_features writer；此處用 7d demo/live_demo 入場 fill
    的有效 fee_rate 驗證 5.5bps taker → 2.0bps maker 的降費幅度。
    """
    try:
        cur.connection.rollback()
    except Exception:
        pass

    params = (TAKER_FEE_RATE, TAKER_FEE_RATE, MAKER_FEE_CUTOFF)
    summary_sql = (
        _MAKER_FILL_CTE
        + """
SELECT
    count(*)::int AS total_fills,
    coalesce(sum(maker_like), 0)::int AS maker_like_fills,
    avg(effective_fee_rate)::float8 AS avg_fee_rate,
    count(*) FILTER (WHERE order_type = 'limit')::int AS limit_order_fills,
    count(*) FILTER (WHERE time_in_force = 'postonly')::int AS postonly_order_fills
FROM entry_fills
"""
    )
    strategy_sql = (
        _MAKER_FILL_CTE
        + """
SELECT
    strategy_name,
    count(*)::int AS total_fills,
    coalesce(sum(maker_like), 0)::int AS maker_like_fills,
    avg(effective_fee_rate)::float8 AS avg_fee_rate
FROM entry_fills
GROUP BY strategy_name
ORDER BY total_fills DESC, strategy_name
LIMIT 8
"""
    )

    try:
        cur.execute(summary_sql, params)
        row = cur.fetchone()
        cur.execute(strategy_sql, params)
        strategy_rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 — healthcheck fail-soft
        return ("WARN", f"maker fill-rate query failed: {type(exc).__name__}: {exc}")

    if row is None:
        return ("WARN", "maker fill-rate query returned no row (PG / cursor anomaly)")

    total = _as_int(row[0])
    maker_like = _as_int(row[1])
    avg_fee_rate = _as_float(row[2], TAKER_FEE_RATE)
    limit_rows = _as_int(row[3])
    postonly_rows = _as_int(row[4])

    if total == 0:
        return (
            "PASS",
            "7d demo/live_demo entry_fills=0 — no G2-01 maker-fill sample yet",
        )

    maker_pct = maker_like / total * 100.0
    fee_drop = _fee_drop_pct(avg_fee_rate)
    limit_pct = limit_rows / total * 100.0
    postonly_pct = postonly_rows / total * 100.0
    base_msg = (
        f"7d demo/live_demo entry_fills={total}, "
        f"avg_fee={avg_fee_rate * 10_000:.2f}bps, "
        f"fee_drop={fee_drop:.1f}% target>={MAKER_FEE_DROP_TARGET_PCT:.0f}%, "
        f"maker_like={maker_like}/{total} ({maker_pct:.1f}%), "
        f"limit_order_rows={limit_rows} ({limit_pct:.1f}%), "
        f"postonly_order_rows={postonly_rows} ({postonly_pct:.1f}%); "
        f"by_strategy: {_format_strategy_slices(list(strategy_rows or []))}"
    )

    if total < MAKER_FILL_MIN_SAMPLE:
        return (
            "WARN",
            base_msg + f" — insufficient sample (<{MAKER_FILL_MIN_SAMPLE})",
        )
    if fee_drop >= MAKER_FEE_DROP_TARGET_PCT:
        return ("PASS", base_msg)
    return (
        "WARN",
        base_msg
        + " — below G2-01 PostOnly fee-drop target; keep passive monitor until settlement",
    )

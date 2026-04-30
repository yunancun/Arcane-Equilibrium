from __future__ import annotations

"""DB-backed realized trading metrics for GUI display.

The UI should not reconstruct trade outcomes from recent fills. The engine
already writes realized PnL, fees, funding, and MLDE post-fee labels to DB.
This module exposes a small read-only aggregate used by Demo, Paper, and Live.
"""

import logging
from collections.abc import Sequence
from typing import Any

from . import db_pool

logger = logging.getLogger(__name__)


def fetch_db_true_metrics(
    engine_modes: Sequence[str],
    *,
    edge_engine_modes: Sequence[str] | None = None,
    window_days: int = 7,
) -> dict[str, Any]:
    """Return DB-truth metrics for the requested engine modes.

    ``account_metrics`` is money-denominated and net of fees/funding.
    ``trade_metrics`` is realized close-fill based and money-denominated.
    ``edge_metrics`` is MLDE post-fee bps when the training view has rows.
    """
    modes = _clean_modes(engine_modes)
    edge_modes = _clean_modes(edge_engine_modes or engine_modes)
    window_days = max(1, min(int(window_days or 7), 90))
    if not modes:
        return _empty(window_days, "no_engine_modes")

    conn = None
    try:
        conn = db_pool.get_conn()
        if conn is None:
            return _empty(window_days, "pg_unavailable")
        with conn.cursor() as cur:
            account = _fetch_account_metrics(cur, modes, window_days)
            trade = _fetch_close_trade_metrics(cur, modes, window_days)
            edge = _fetch_mlde_edge_metrics(cur, edge_modes, window_days)
        return {
            "available": True,
            "source": "pg_trading_fills",
            "window_days": window_days,
            "engine_modes": modes,
            "edge_engine_modes": edge_modes,
            "account_metrics": account,
            "trade_metrics": trade,
            "edge_metrics": edge,
        }
    except Exception as exc:  # noqa: BLE001 - metrics must fail soft
        logger.warning("DB true metrics failed for %s: %s", modes, exc)
        return _empty(window_days, f"{type(exc).__name__}: {exc}")
    finally:
        if conn is not None:
            db_pool.put_conn(conn)


def _clean_modes(modes: Sequence[str]) -> list[str]:
    out: list[str] = []
    for mode in modes:
        m = str(mode or "").strip()
        if m and m not in out:
            out.append(m)
    return out


def _empty(window_days: int, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "source": "pg_trading_fills",
        "reason": reason,
        "window_days": window_days,
        "engine_modes": [],
        "account_metrics": _zero_account(),
        "trade_metrics": _zero_trade("trading.fills_close_realized", "usdt"),
        "edge_metrics": _zero_trade("learning.mlde_edge_training_rows", "bps"),
    }


def _placeholders(n: int) -> str:
    return ", ".join(["%s"] * n)


def _window_clause(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f" AND {prefix}ts > now() - (%s::int || ' days')::interval "


def _fetch_account_metrics(cur: Any, modes: list[str], window_days: int) -> dict[str, Any]:
    mode_sql = _placeholders(len(modes))
    params: list[Any] = [*modes, window_days]
    cur.execute(
        f"""
        SELECT
            COUNT(*)::int,
            COALESCE(SUM(realized_pnl), 0)::float8,
            COALESCE(SUM(fee), 0)::float8,
            COALESCE(AVG(NULLIF(fee_rate, 0)), 0)::float8,
            MIN(ts),
            MAX(ts)
        FROM trading.fills
        WHERE engine_mode IN ({mode_sql})
        {_window_clause()}
        """,
        tuple(params),
    )
    row = cur.fetchone() or (0, 0.0, 0.0, 0.0, None, None)
    funding = _fetch_funding_pnl(cur, modes, window_days)
    total_fills = _as_int(row[0])
    gross_pnl = _as_float(row[1])
    fees = _as_float(row[2])
    net_pnl = gross_pnl - fees + funding
    return {
        "total_fills": total_fills,
        "gross_pnl": round(gross_pnl, 6),
        "total_fees": round(fees, 6),
        "funding_pnl": round(funding, 6),
        "net_pnl": round(net_pnl, 6),
        "avg_fee_rate": round(_as_float(row[3]), 8),
        "first_ts": row[4].isoformat() if row[4] is not None and hasattr(row[4], "isoformat") else None,
        "last_ts": row[5].isoformat() if row[5] is not None and hasattr(row[5], "isoformat") else None,
    }


def _fetch_funding_pnl(cur: Any, modes: list[str], window_days: int) -> float:
    try:
        cur.execute("SELECT to_regclass('trading.funding_settlements') IS NOT NULL")
        exists = cur.fetchone()
        if not exists or not exists[0]:
            return 0.0
        mode_sql = _placeholders(len(modes))
        cur.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0)::float8
            FROM trading.funding_settlements
            WHERE engine_mode IN ({mode_sql})
            {_window_clause()}
            """,
            tuple([*modes, window_days]),
        )
        row = cur.fetchone()
        return _as_float(row[0]) if row else 0.0
    except Exception:
        return 0.0


def _fetch_close_trade_metrics(cur: Any, modes: list[str], window_days: int) -> dict[str, Any]:
    mode_sql = _placeholders(len(modes))
    cur.execute(
        f"""
        WITH close_rows AS (
          SELECT (COALESCE(realized_pnl, 0) - COALESCE(fee, 0))::float8 AS pnl
          FROM trading.fills
          WHERE engine_mode IN ({mode_sql})
            {_window_clause()}
            AND (
              COALESCE(realized_pnl, 0) <> 0
              OR COALESCE(entry_context_id, '') <> ''
              OR COALESCE(exit_reason, '') <> ''
              OR strategy_name LIKE 'risk_close:%%'
              OR strategy_name LIKE 'strategy_close:%%'
              OR strategy_name LIKE 'stop_trigger:%%'
              OR strategy_name LIKE 'ipc_close%%'
            )
        )
        SELECT
          COUNT(*)::int,
          COUNT(*) FILTER (WHERE pnl > 0)::int,
          COUNT(*) FILTER (WHERE pnl < 0)::int,
          COALESCE(AVG(pnl) FILTER (WHERE pnl > 0), 0)::float8,
          COALESCE(ABS(AVG(pnl) FILTER (WHERE pnl < 0)), 0)::float8,
          COALESCE(MAX(pnl), 0)::float8,
          COALESCE(MIN(pnl), 0)::float8,
          COALESCE(SUM(pnl), 0)::float8
        FROM close_rows
        """,
        tuple([*modes, window_days]),
    )
    row = cur.fetchone() or (0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return _trade_from_row(row, "trading.fills_close_realized", "usdt")


def _fetch_mlde_edge_metrics(cur: Any, modes: list[str], window_days: int) -> dict[str, Any]:
    try:
        cur.execute("SELECT to_regclass('learning.mlde_edge_training_rows') IS NOT NULL")
        exists = cur.fetchone()
        if not exists or not exists[0] or not modes:
            return _zero_trade("learning.mlde_edge_training_rows", "bps")
        mode_sql = _placeholders(len(modes))
        cur.execute(
            f"""
            WITH rows AS (
              SELECT net_bps_after_fee::float8 AS pnl
              FROM learning.mlde_edge_training_rows
              WHERE engine_mode IN ({mode_sql})
                {_window_clause()}
                AND attribution_chain_ok
                AND net_bps_after_fee IS NOT NULL
            )
            SELECT
              COUNT(*)::int,
              COUNT(*) FILTER (WHERE pnl > 0)::int,
              COUNT(*) FILTER (WHERE pnl < 0)::int,
              COALESCE(AVG(pnl) FILTER (WHERE pnl > 0), 0)::float8,
              COALESCE(ABS(AVG(pnl) FILTER (WHERE pnl < 0)), 0)::float8,
              COALESCE(MAX(pnl), 0)::float8,
              COALESCE(MIN(pnl), 0)::float8,
              COALESCE(SUM(pnl), 0)::float8,
              COALESCE(AVG(pnl), 0)::float8
            FROM rows
            """,
            tuple([*modes, window_days]),
        )
        row = cur.fetchone()
        if not row:
            return _zero_trade("learning.mlde_edge_training_rows", "bps")
        out = _trade_from_row(row, "learning.mlde_edge_training_rows", "bps")
        out["avg_net_bps"] = round(_as_float(row[8]), 4)
        out["sum_net_bps"] = round(_as_float(row[7]), 4)
        return out
    except Exception:
        return _zero_trade("learning.mlde_edge_training_rows", "bps")


def _trade_from_row(row: Sequence[Any], source: str, unit: str) -> dict[str, Any]:
    total = _as_int(row[0])
    wins = _as_int(row[1])
    losses = _as_int(row[2])
    avg_win = _as_float(row[3])
    avg_loss = _as_float(row[4])
    ratio = avg_win / avg_loss if avg_win > 0 and avg_loss > 0 else 0.0
    trade_count = wins + losses
    return {
        "metric_source": source,
        "metric_unit": unit,
        "total_round_trips": total,
        "win_count": wins,
        "loss_count": losses,
        "win_rate": round(wins / trade_count, 4) if trade_count > 0 else 0.0,
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "win_loss_ratio": round(ratio, 4),
        "largest_win": round(_as_float(row[5]), 6),
        "largest_loss": round(_as_float(row[6]), 6),
        "sum_pnl": round(_as_float(row[7]), 6),
    }


def _zero_account() -> dict[str, Any]:
    return {
        "total_fills": 0,
        "gross_pnl": 0.0,
        "total_fees": 0.0,
        "funding_pnl": 0.0,
        "net_pnl": 0.0,
        "avg_fee_rate": 0.0,
        "first_ts": None,
        "last_ts": None,
    }


def _zero_trade(source: str, unit: str) -> dict[str, Any]:
    return {
        "metric_source": source,
        "metric_unit": unit,
        "total_round_trips": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "win_loss_ratio": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "sum_pnl": 0.0,
        "avg_net_bps": 0.0,
        "sum_net_bps": 0.0,
    }


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

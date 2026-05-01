from __future__ import annotations

"""DB-backed realized trading metrics for GUI display.

The UI should not reconstruct trade outcomes from recent fills. The engine
already writes realized PnL, fees, funding, and MLDE post-fee labels to DB.
This module exposes a small read-only aggregate used by Demo, Paper, and Live.

GUI 顯示用 DB 真實交易指標。UI 不應從最近 fills 自行重建交易結果；
engine 已將 realized PnL、fees、funding 與 MLDE 費後標籤寫入 DB。
本模組提供 Demo / Paper / Live 共用的只讀彙總。
"""

import logging
import math
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

    回傳指定 engine modes 的 DB 真實指標：account_metrics 為扣費/資金費後
    金額口徑，trade_metrics 為 close-fill 金額口徑，edge_metrics 在 MLDE
    training view 有資料時為費後 bps 口徑。
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
            account_24h = _fetch_account_metrics(cur, modes, 1)
            trade = _fetch_close_trade_metrics(cur, modes, window_days)
            edge = _fetch_mlde_edge_metrics(cur, edge_modes, window_days)
            risk = _fetch_db_risk_metrics(cur, modes, window_days)
        payload = {
            "available": True,
            "source": "pg_trading_fills",
            "window_days": window_days,
            "engine_modes": modes,
            "edge_engine_modes": edge_modes,
            "account_metrics": account,
            "account_metrics_24h": account_24h,
            "trade_metrics": trade,
            "edge_metrics": edge,
            "risk_metrics": risk,
        }
        payload["performance_metrics"] = build_performance_metrics(payload)
        return payload
    except Exception as exc:  # noqa: BLE001 - metrics must fail soft
        logger.warning("DB true metrics failed for %s: %s", modes, exc)
        return _empty(window_days, f"{type(exc).__name__}: {exc}")
    finally:
        if conn is not None:
            db_pool.put_conn(conn)


def _clean_modes(modes: Sequence[str]) -> list[str]:
    """Normalize engine mode inputs while preserving order.

    正規化 engine mode 輸入並保留原始順序。
    """
    out: list[str] = []
    for mode in modes:
        m = str(mode or "").strip()
        if m and m not in out:
            out.append(m)
    return out


def _empty(window_days: int, reason: str) -> dict[str, Any]:
    """Build a fail-soft empty metrics payload.

    建立 fail-soft 的空指標 payload。
    """
    return {
        "available": False,
        "source": "pg_trading_fills",
        "reason": reason,
        "window_days": window_days,
        "engine_modes": [],
        "account_metrics": _zero_account(),
        "account_metrics_24h": _zero_account(),
        "trade_metrics": _zero_trade("trading.fills_close_realized", "usdt"),
        "edge_metrics": _zero_trade("learning.mlde_edge_training_rows", "bps"),
        "risk_metrics": _zero_risk(),
        "performance_metrics": [],
    }


def _placeholders(n: int) -> str:
    """Build psycopg2 placeholder list for IN clauses.

    建立 psycopg2 `IN` 條件使用的 placeholder 清單。
    """
    return ", ".join(["%s"] * n)


def _window_clause(alias: str = "") -> str:
    """Return the shared time-window SQL predicate.

    回傳共用時間窗口 SQL predicate。
    """
    prefix = f"{alias}." if alias else ""
    return f" AND {prefix}ts > now() - (%s::int || ' days')::interval "


def _fetch_account_metrics(cur: Any, modes: list[str], window_days: int) -> dict[str, Any]:
    """Fetch money-denominated fill/funding aggregates.

    讀取金額口徑的成交與資金費彙總。
    """
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
    """Fetch funding PnL when the settlements table exists.

    在 funding settlements 表存在時讀取資金費 PnL。
    """
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
    """Fetch realized close-trade metrics from DB fills.

    從 DB fills 讀取已實現平倉交易指標。
    """
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


def _fetch_close_pnl_rows(cur: Any, modes: list[str], window_days: int) -> list[tuple[Any, float]]:
    """Fetch ordered close PnL rows for risk metrics.

    讀取按時間排序的平倉 PnL rows，供風險指標計算。
    """
    mode_sql = _placeholders(len(modes))
    cur.execute(
        f"""
        SELECT
          ts,
          (COALESCE(realized_pnl, 0) - COALESCE(fee, 0))::float8 AS pnl
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
        ORDER BY ts ASC
        """,
        tuple([*modes, window_days]),
    )
    return [(row[0], _as_float(row[1])) for row in (cur.fetchall() or [])]


def _fetch_db_risk_metrics(cur: Any, modes: list[str], window_days: int) -> dict[str, Any]:
    """Compute drawdown and simple Sharpe from DB close PnL.

    由 DB 平倉 PnL 計算回撤與簡化 Sharpe。
    """
    rows = _fetch_close_pnl_rows(cur, modes, window_days)
    holding = _fetch_db_holding_period_metrics(cur, modes, window_days)
    if not rows:
        out = _zero_risk()
        out.update(holding)
        return out

    baseline = 10_000.0
    cumulative = 0.0
    peak = 0.0
    max_drawdown_abs = 0.0
    returns: list[float] = []
    for _, pnl in rows:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        max_drawdown_abs = max(max_drawdown_abs, drawdown)
        returns.append(pnl / baseline)

    current_drawdown_abs = max(0.0, peak - cumulative)
    max_drawdown_pct = (max_drawdown_abs / baseline) * 100.0
    current_drawdown_pct = (current_drawdown_abs / baseline) * 100.0

    sharpe = 0.0
    if len(returns) >= 2:
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        std_ret = math.sqrt(variance) if variance > 0 else 0.0
        if std_ret > 0:
            sharpe = mean_ret / std_ret

    return {
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "max_drawdown_abs": round(max_drawdown_abs, 6),
        "current_drawdown_pct": round(current_drawdown_pct, 4),
        "sharpe_ratio": round(sharpe, 4),
        "return_count": len(returns),
        **holding,
        "metric_source": "trading.fills_close_realized",
    }


def _fetch_db_holding_period_metrics(cur: Any, modes: list[str], window_days: int) -> dict[str, Any]:
    """Compute holding-period metrics by joining entry/exit contexts.

    透過 entry/exit context join 計算持倉時間指標。
    """
    try:
        mode_sql = _placeholders(len(modes))
        cur.execute(
            f"""
            WITH exits AS (
              SELECT entry_context_id, ts AS exit_ts
              FROM trading.fills
              WHERE engine_mode IN ({mode_sql})
                {_window_clause()}
                AND COALESCE(entry_context_id, '') <> ''
            ),
            entries AS (
              SELECT context_id, MIN(ts) AS entry_ts
              FROM trading.fills
              WHERE engine_mode IN ({mode_sql})
                AND COALESCE(context_id, '') <> ''
              GROUP BY context_id
            ),
            durations AS (
              SELECT EXTRACT(EPOCH FROM exits.exit_ts - entries.entry_ts)::float8 AS sec
              FROM exits
              JOIN entries ON entries.context_id = exits.entry_context_id
              WHERE exits.exit_ts > entries.entry_ts
            )
            SELECT
              COALESCE(AVG(sec), 0)::float8,
              COALESCE(MIN(sec), 0)::float8,
              COALESCE(MAX(sec), 0)::float8,
              COUNT(*)::int
            FROM durations
            """,
            tuple([*modes, window_days, *modes]),
        )
        row = cur.fetchone() or (0.0, 0.0, 0.0, 0)
        return {
            "avg_holding_period_sec": round(_as_float(row[0]), 2),
            "min_holding_period_sec": round(_as_float(row[1]), 2),
            "max_holding_period_sec": round(_as_float(row[2]), 2),
            "total_orders_measured": _as_int(row[3]),
        }
    except Exception:
        return {
            "avg_holding_period_sec": 0.0,
            "min_holding_period_sec": 0.0,
            "max_holding_period_sec": 0.0,
            "total_orders_measured": 0,
        }


def _fetch_mlde_edge_metrics(cur: Any, modes: list[str], window_days: int) -> dict[str, Any]:
    """Fetch MLDE post-fee edge metrics when the view exists.

    在 MLDE training view 存在時讀取費後 edge 指標。
    """
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
    """Convert a SQL aggregate row into the shared trade metric shape.

    將 SQL 彙總 row 轉為共用 trade metric 結構。
    """
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
    """Return zero account metrics.

    回傳 account metrics 的零值結構。
    """
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


def _zero_risk() -> dict[str, Any]:
    """Return zero risk metrics.

    回傳 risk metrics 的零值結構。
    """
    return {
        "max_drawdown_pct": 0.0,
        "max_drawdown_abs": 0.0,
        "current_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "return_count": 0,
        "avg_holding_period_sec": 0.0,
        "min_holding_period_sec": 0.0,
        "max_holding_period_sec": 0.0,
        "total_orders_measured": 0,
        "metric_source": "trading.fills_close_realized",
    }


def _zero_trade(source: str, unit: str) -> dict[str, Any]:
    """Return zero trade metrics for a metric source.

    依來源回傳 trade metrics 的零值結構。
    """
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


def build_performance_metrics(
    db_metrics: dict[str, Any],
    *,
    fallback_metrics: dict[str, Any] | None = None,
    total_ai_cost: float | None = None,
) -> list[dict[str, Any]]:
    """Build the canonical GUI performance metric list.

    The three GUI tabs render this list directly so labels, order, tooltip text,
    and source semantics stay identical across Live, Demo, and Paper.

    建立 GUI 共用的 canonical performance metric list；Demo/Paper/Live 三個
    tab 直接渲染此列表，讓 label、排序、tooltip 與 source 語義一致。
    """
    account = db_metrics.get("account_metrics") or {}
    account_24h = db_metrics.get("account_metrics_24h") or {}
    trade = db_metrics.get("trade_metrics") or {}
    edge = db_metrics.get("edge_metrics") or {}
    risk = db_metrics.get("risk_metrics") or {}
    fallback = fallback_metrics or {}
    fallback_drawdown = fallback.get("drawdown_metrics") or {}
    fallback_holding = fallback.get("holding_period_metrics") or {}
    fallback_sharpe = fallback.get("sharpe_ratio") or {}
    pnl_summary = fallback.get("pnl_summary") or {}

    edge_count = _as_int(edge.get("total_round_trips"))
    trade_count = _as_int(trade.get("total_round_trips"))
    quality = edge if edge_count > 0 else trade
    quality_source = str(quality.get("metric_source") or "")
    quality_unit = str(quality.get("metric_unit") or "usdt")

    if total_ai_cost is None:
        total_ai_cost = pnl_summary.get("total_ai_cost")

    max_drawdown = _coalesce_number(
        risk.get("max_drawdown_pct"),
        fallback_drawdown.get("max_drawdown_pct"),
    )
    sharpe = _coalesce_number(
        risk.get("sharpe_ratio"),
        fallback_sharpe.get("sharpe_ratio"),
    )
    avg_hold_sec = _coalesce_number(
        risk.get("avg_holding_period_sec"),
        fallback_holding.get("avg_holding_period_sec"),
    )

    return [
        _metric("total_fills_7d", "7D 成交笔数 / TOTAL FILLS",
                "最近 7 天的所有成交腿数量；一笔完整交易通常包含开仓腿和平仓腿。", account.get("total_fills"), "count", account.get("source") or "trading.fills"),
        _metric("round_trips_7d", "7D 完整交易 / ROUND TRIPS",
                "最近 7 天已平仓的完整交易次数；按后端 close-fill 规则统计。", trade_count, "count", trade.get("metric_source")),
        _metric("attributed_trades_7d", "7D 已归因交易 / ATTRIBUTED TRADES",
                "最近 7 天已通过 MLDE 归因链并带有净 bps 标签的交易数。", edge_count, "count", edge.get("metric_source")),

        _metric("net_pnl_24h", "24H 净盈亏 / NET PNL",
                "最近 24 小时后端按 realized_pnl - 手续费 + 资金费计算的净盈亏。", account_24h.get("net_pnl"), "money", "trading.fills + trading.funding_settlements", "pnl"),
        _metric("net_pnl_7d", "7D 净盈亏 / NET PNL",
                "最近 7 天后端按 realized_pnl - 手续费 + 资金费计算的净盈亏。", account.get("net_pnl"), "money", "trading.fills + trading.funding_settlements", "pnl"),
        _metric("gross_pnl_7d", "7D 总毛利 / GROSS PNL",
                "最近 7 天未扣手续费和资金费前的 realized_pnl 总和。", account.get("gross_pnl"), "money", "trading.fills", "pnl"),
        _metric("total_fees_7d", "7D 手续费 / TOTAL FEES",
                "最近 7 天所有成交手续费总额；手续费会直接侵蚀净边际。", account.get("total_fees"), "money_abs", "trading.fills"),
        _metric("funding_7d", "7D 资金费 / FUNDING",
                "最近 7 天资金费结算净额；正数增加权益，负数减少权益。", account.get("funding_pnl"), "money", "trading.funding_settlements", "pnl"),
        _metric("total_ai_cost", "总 AI 成本 / TOTAL AI COST",
                "后端记录的 AI 推理调用累计成本；用于评估交易收益是否覆盖智能调用成本。", total_ai_cost, "money_abs", "api_budget"),

        _metric("avg_net_edge", "平均净边际 / AVG NET EDGE",
                "已归因交易的平均费后净边际，单位 bps；大于 0 才代表交易本身有正边际。", quality.get("avg_net_bps"), "bps", quality_source, "pnl"),
        _metric("win_rate", "胜率 / WIN RATE",
                "盈利交易数除以盈利+亏损交易数；需结合盈亏比一起看。", quality.get("win_rate"), "rate", quality_source),
        _metric("win_loss_ratio", "盈亏比 / WIN/LOSS RATIO",
                "平均盈利除以平均亏损；大于 1 表示单笔盈利通常大于单笔亏损。", quality.get("win_loss_ratio"), "ratio", quality_source),
        _metric("largest_win", "单笔最高盈利 / LARGEST WIN",
                "统计窗口内单笔交易的最大盈利。若来源为 MLDE 则单位为 bps，否则为账户货币。", quality.get("largest_win"), quality_unit, quality_source, "pnl"),
        _metric("largest_loss", "单笔最高亏损 / LARGEST LOSS",
                "统计窗口内单笔交易的最大亏损。若来源为 MLDE 则单位为 bps，否则为账户货币。", quality.get("largest_loss"), quality_unit, quality_source, "pnl"),
        _metric("avg_loss", "平均亏损 / AVG LOSS",
                "亏损交易的平均亏损幅度；用于判断亏损尾部是否过大。", -abs(_as_float(quality.get("avg_loss"))), quality_unit, quality_source, "pnl"),

        _metric("max_drawdown", "最大回撤 / MAX DRAWDOWN",
                "从阶段峰值到随后低点的最大跌幅；衡量最坏情况下资金曲线回落。", max_drawdown, "percent", risk.get("metric_source") or "backend_metrics"),
        _metric("sharpe_ratio", "夏普比率 / SHARPE RATIO",
                "单位波动获得的收益；数值越高说明风险调整后收益越好。", sharpe, "ratio", risk.get("metric_source") or "backend_metrics"),
        _metric("avg_hold_time", "平均持仓时间 / AVG HOLD TIME",
                "从开仓到平仓的平均时间；过短可能代表过度交易，过长可能代表退出不及时。", avg_hold_sec, "seconds", risk.get("metric_source") or "backend_metrics"),
    ]


def _metric(
    key: str,
    label: str,
    tooltip_zh: str,
    value: Any,
    unit: str,
    source: Any,
    polarity: str = "neutral",
) -> dict[str, Any]:
    """Build one canonical GUI metric descriptor.

    建立單個 canonical GUI metric 描述。
    """
    return {
        "key": key,
        "label": label,
        "tooltip_zh": tooltip_zh,
        "value": _metric_value(value),
        "unit": unit,
        "source": str(source or "backend"),
        "polarity": polarity,
    }


def _metric_value(value: Any) -> float | int | str | None:
    """Normalize metric values to JSON-safe scalars.

    將 metric value 正規化為 JSON-safe scalar。
    """
    if value is None:
        return None
    if isinstance(value, str):
        if value == "inf":
            return value
        try:
            value = float(value)
        except ValueError:
            return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return round(v, 6)


def _coalesce_number(*values: Any) -> float | None:
    """Return the first numeric value from a fallback chain.

    從 fallback 鏈回傳第一個數值。
    """
    for value in values:
        parsed = _metric_value(value)
        if isinstance(parsed, (int, float)):
            return float(parsed)
    return None


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

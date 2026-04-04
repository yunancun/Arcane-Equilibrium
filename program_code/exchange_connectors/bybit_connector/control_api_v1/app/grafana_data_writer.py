"""
Grafana Data Writer — Periodically writes trading data to PostgreSQL for Grafana dashboards.
Grafana 数据写入器 — 定期将交易数据写入 PostgreSQL 供 Grafana 仪表盘使用。

MODULE_NOTE (中文):
  本模块是 Grafana 监控仪表盘的数据源。它定期从交易系统内部状态
  读取数据，写入 PostgreSQL 表中。Grafana 的仪表盘查询这些表来展示数据。

  写入频率：每 30 秒（可配置）
  写入内容：
  1. paper_pnl_snapshots — PnL 快照（已实现/未实现/手续费/净值/胜率/Sharpe）
  2. market_tickers — 最新价格（last/bid/ask/volume/funding_rate/open_interest）
  3. system_health — 系统健康状态（kline_manager / pipeline_bridge 等组件）
  4. trade_executions — 新的成交记录（增量写入，避免重复）

  表结构匹配 init_trading_schema.sql 中的定义，字段名与现有 schema 一致。
  所有 paper trading 数据标记 is_paper=true。

MODULE_NOTE (English):
  Data source for Grafana monitoring dashboards. Periodically reads from
  trading system internal state and writes to PostgreSQL tables.

  Write interval: 30s (configurable)
  Tables written:
  1. paper_pnl_snapshots — PnL snapshots (realized/unrealized/fees/net/win_rate/sharpe)
  2. market_tickers — latest prices (last/bid/ask/volume/funding_rate/open_interest)
  3. system_health — component health (kline_manager / pipeline_bridge etc.)
  4. trade_executions — new fill records (incremental, no duplicates)

  Column names match the existing schema in init_trading_schema.sql.
  All paper trading data marked is_paper=true.

安全不变量 / Safety invariant:
  - 本模块只写入 PostgreSQL，不修改任何交易系统状态
  - system_mode = read_only 不变
  - 连接失败时静默降级，不影响交易系统运行
"""
from __future__ import annotations

import logging
import os
import threading
import time
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

def _read_pg_pass_from_secrets() -> str:
    """Read PG password from secrets file. 从 secrets 文件读取数据库密码。"""
    try:
        path = os.path.expanduser("~/BybitOpenClaw/secrets/compose_env/trading_services.env")
        with open(path) as f:
            for line in f:
                if line.startswith("POSTGRES_PASSWORD="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""


# PostgreSQL connection config — override via env vars
# PostgreSQL 连接配置 — 通过环境变量覆盖
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "trading_admin")
PG_PASS = os.getenv("PG_PASS") or _read_pg_pass_from_secrets()
PG_DB = os.getenv("PG_DB", "trading_ai")


def _get_pg_conn():
    """Get a PostgreSQL connection. Returns None on failure (graceful degradation).
    获取 PostgreSQL 连接，失败时返回 None（静默降级）。"""
    try:
        import psycopg2
        return psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=PG_DB,
            connect_timeout=5,
        )
    except ImportError:
        logger.debug("psycopg2 not installed — Grafana data writer disabled")
        return None
    except Exception as e:
        logger.debug("PostgreSQL connection failed: %s", e)
        return None


class GrafanaDataWriter:
    """Periodically writes trading data to PostgreSQL for Grafana.
    定期将交易数据写入 PostgreSQL 供 Grafana 使用。

    Dependencies (all optional — writes what it can):
      paper_engine   — PaperTradingEngine for PnL/fills/positions
      kline_manager  — KlineManager for health stats
      signal_engine  — SignalEngine (reserved for future signal metrics)
      orchestrator   — StrategyOrchestrator (reserved for future strategy metrics)
      pipeline_bridge — PipelineBridge for latest prices + bridge stats
    """

    def __init__(
        self,
        paper_engine: Any = None,
        kline_manager: Any = None,
        signal_engine: Any = None,
        orchestrator: Any = None,
        pipeline_bridge: Any = None,
        *,
        interval_sec: float = 30.0,
    ) -> None:
        self._engine = paper_engine
        self._km = kline_manager
        self._se = signal_engine
        self._orch = orchestrator
        self._bridge = pipeline_bridge
        self._interval = interval_sec
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_fill_count = 0
        self._stats = {"writes": 0, "errors": 0, "last_write_ts": None}

    def start(self) -> None:
        """Start the background writer thread. Idempotent."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="grafana-writer")
        self._thread.start()
        logger.info(
            "Grafana data writer started (interval=%ds) / Grafana 数据写入器已启动",
            self._interval,
        )

    def stop(self) -> None:
        """Stop the background writer thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Grafana data writer stopped / Grafana 数据写入器已停止")

    def _loop(self) -> None:
        """Main loop — runs in daemon thread."""
        while self._running:
            try:
                self._write_snapshot()
            except Exception:
                logger.exception("Grafana write error / Grafana 写入异常")
                self._stats["errors"] += 1
            time.sleep(self._interval)

    def _write_snapshot(self) -> None:
        """Write one round of data to PostgreSQL."""
        conn = _get_pg_conn()
        if conn is None:
            return

        try:
            cur = conn.cursor()
            now_ms = int(time.time() * 1000)

            self._write_pnl(cur, now_ms)
            self._write_market_tickers(cur, now_ms)
            self._write_system_health(cur, now_ms)
            self._write_trade_executions(cur, now_ms)

            conn.commit()
            self._stats["writes"] += 1
            self._stats["last_write_ts"] = now_ms

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── 1. Paper PnL Snapshots ──

    def _write_pnl(self, cur, now_ms: int) -> None:
        """Write PnL snapshot to paper_pnl_snapshots table.
        Schema: ts, session_id, realized_pnl, unrealized_pnl, total_fees,
                ai_cost, net_pnl, open_positions, total_trades, win_rate, sharpe_ratio"""
        if not self._engine:
            return
        try:
            state = self._engine.get_state()
            sess = state.get("session", {})
            if sess.get("session_state") != "active":
                return

            balance = float(sess.get("current_paper_balance_usdt", 0))
            initial = float(sess.get("initial_paper_balance_usdt", 10000))
            session_id = sess.get("session_id", "")

            fills = state.get("fills", [])
            total_fees = sum(float(f.get("fee_usdt", 0)) for f in fills) if isinstance(fills, list) else 0
            total_trades = len(fills) if isinstance(fills, list) else 0

            positions = state.get("positions", {})
            open_positions = len(positions) if isinstance(positions, dict) else 0

            realized_pnl = balance - initial
            net_pnl = realized_pnl - total_fees

            # Win rate: count profitable fills vs total
            win_count = 0
            if isinstance(fills, list) and total_trades > 0:
                win_count = sum(1 for f in fills if float(f.get("realized_pnl", 0)) > 0)

            win_rate = (win_count / total_trades * 100) if total_trades > 0 else None

            cur.execute("""
                INSERT INTO paper_pnl_snapshots_legacy
                    (ts, session_id, realized_pnl, unrealized_pnl, total_fees,
                     ai_cost, net_pnl, open_positions, total_trades, win_rate, sharpe_ratio)
                VALUES (to_timestamp(%s / 1000.0), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                now_ms, session_id, realized_pnl, 0, total_fees,
                0, net_pnl, open_positions, total_trades, win_rate, None,
            ))
        except Exception as e:
            logger.debug("PnL write failed: %s", e)

    # ── 2. Market Tickers ──

    def _write_market_tickers(self, cur, now_ms: int) -> None:
        """Write latest prices to market_tickers table.
        Schema: ts, symbol, last_price, bid_price, ask_price, volume_24h,
                funding_rate, open_interest, index_price, mark_price"""
        if not self._bridge:
            return
        try:
            prices = getattr(self._bridge, "_latest_prices", {})
            if not prices:
                return
            for symbol, price in prices.items():
                try:
                    cur.execute("""
                        INSERT INTO market_tickers_legacy
                            (ts, symbol, last_price, bid_price, ask_price,
                             volume_24h, funding_rate, open_interest,
                             index_price, mark_price)
                        VALUES (to_timestamp(%s / 1000.0), %s, %s, %s, %s,
                                %s, %s, %s, %s, %s)
                    """, (now_ms, symbol, price, None, None,
                          None, None, None, None, None))
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Market ticker write failed: %s", e)

    # ── 3. System Health ──

    def _write_system_health(self, cur, now_ms: int) -> None:
        """Write component health to system_health table.
        Schema: ts, component, status, latency_ms, detail, metrics"""
        import json

        if self._km:
            try:
                km_stats = self._km.get_stats()
                staleness = self._km.get_staleness()
                is_stale = staleness.get("is_stale", False) if isinstance(staleness, dict) else False
                status = "stale" if is_stale else "healthy"
                metrics_json = json.dumps({
                    "total_ticks": km_stats.get("total_ticks_processed", 0),
                    "total_klines_closed": km_stats.get("total_klines_closed", 0),
                    "symbols": km_stats.get("symbols", []),
                })
                cur.execute("""
                    INSERT INTO system_health_legacy (ts, component, status, latency_ms, detail, metrics)
                    VALUES (to_timestamp(%s / 1000.0), %s, %s, %s, %s, %s)
                """, (
                    now_ms, "kline_manager", status, None,
                    f"ticks={km_stats.get('total_ticks_processed', 0)}, "
                    f"klines={km_stats.get('total_klines_closed', 0)}",
                    metrics_json,
                ))
            except Exception as e:
                logger.debug("KlineManager health write failed: %s", e)

        if self._bridge:
            try:
                b_stats = self._bridge.get_stats()
                status = "active" if b_stats.get("active") else "inactive"
                metrics_json = json.dumps({
                    "ticks_received": b_stats.get("ticks_received", 0),
                    "intents_submitted": b_stats.get("intents_submitted", 0),
                    "stops_triggered": b_stats.get("stops_triggered", 0),
                })
                cur.execute("""
                    INSERT INTO system_health_legacy (ts, component, status, latency_ms, detail, metrics)
                    VALUES (to_timestamp(%s / 1000.0), %s, %s, %s, %s, %s)
                """, (
                    now_ms, "pipeline_bridge", status, None,
                    f"ticks={b_stats.get('ticks_received', 0)}, "
                    f"intents={b_stats.get('intents_submitted', 0)}, "
                    f"stops={b_stats.get('stops_triggered', 0)}",
                    metrics_json,
                ))
            except Exception as e:
                logger.debug("PipelineBridge health write failed: %s", e)

    # ── 4. Trade Executions (incremental) ──

    def _write_trade_executions(self, cur, now_ms: int) -> None:
        """Write new fills to trade_executions table (incremental).
        Schema: ts, exec_id, order_id, symbol, side, exec_type, exec_qty,
                exec_price, fee, fee_currency, realized_pnl, is_paper, strategy, metrics"""
        if not self._engine:
            return
        try:
            import json
            state = self._engine.get_state()
            fills = state.get("fills", [])
            if not isinstance(fills, list) or len(fills) <= self._last_fill_count:
                return

            new_fills = fills[self._last_fill_count:]
            for f in new_fills:
                try:
                    cur.execute("""
                        INSERT INTO trade_executions_legacy
                            (ts, exec_id, order_id, symbol, side, exec_type,
                             exec_qty, exec_price, fee, fee_currency, realized_pnl,
                             is_paper, strategy, metrics)
                        VALUES (to_timestamp(%s / 1000.0), %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        f.get("fill_ts_ms", now_ms),
                        f.get("fill_id", f.get("exec_id", "")),
                        f.get("order_id", ""),
                        f.get("symbol", ""),
                        f.get("side", ""),
                        f.get("order_type", "paper_fill"),
                        f.get("qty", 0),
                        f.get("fill_price", 0),
                        f.get("fee_usdt", 0),
                        "USDT",
                        f.get("realized_pnl", 0),
                        True,  # is_paper
                        f.get("strategy", None),
                        json.dumps(f),
                    ))
                except Exception as e:
                    logger.debug("Fill write failed: %s", e)

            self._last_fill_count = len(fills)
        except Exception as e:
            logger.debug("Trade execution write failed: %s", e)

    # ── Public API ──

    def get_stats(self) -> dict[str, Any]:
        """Return writer statistics for status endpoints."""
        return {
            "component": "grafana_data_writer",
            "running": self._running,
            "interval_sec": self._interval,
            **self._stats,
        }

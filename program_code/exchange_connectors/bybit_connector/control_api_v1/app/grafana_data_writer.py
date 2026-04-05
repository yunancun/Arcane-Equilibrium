"""
Grafana Data Writer — Periodically writes PnL + health data to PostgreSQL for Grafana.
Grafana 数据写入器 — 定期将 PnL + 健康数据写入 PostgreSQL 供 Grafana 仪表盘使用。

MODULE_NOTE (中文):
  本模块为 Grafana 监控仪表盘提供补充数据源。Rust 引擎已直接写入：
  - market.market_tickers（行情）
  - trading.signals / fills（信号/成交）
  - features.online_latest（特征）
  本模块只负责 Rust 不覆盖的数据：
  1. paper_pnl_snapshots — PnL 快照（从 Rust IPC 快照读取）
  2. system_health — 引擎健康状态（从 Rust IPC 快照读取）

MODULE_NOTE (English):
  Supplementary data source for Grafana. Rust engine now directly writes:
  - market.market_tickers (tickers)
  - trading.signals / fills (signals/fills)
  - features.online_latest (features)
  This module only handles data Rust does NOT cover:
  1. paper_pnl_snapshots — PnL snapshots (read from Rust IPC snapshot)
  2. system_health — engine health (read from Rust IPC snapshot)

  DEPRECATED writes (now handled by Rust engine):
  - market_tickers → Rust market_writer
  - trade_executions → Rust trading_writer

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
    """Periodically writes PnL + health data to PostgreSQL for Grafana.
    定期将 PnL + 健康数据写入 PostgreSQL 供 Grafana 使用。

    Data source: Rust engine IPC snapshot (pipeline_snapshot.json).
    数据源：Rust 引擎 IPC 快照。

    Legacy deps (paper_engine, kline_manager, pipeline_bridge) retained for
    backwards compatibility but no longer required — Rust IPC is primary source.
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
        snapshot_path: str | None = None,
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
        # Rust IPC snapshot path / Rust IPC 快照路径
        data_dir = os.getenv("OPENCLAW_DATA_DIR", "/tmp/openclaw")
        self._snapshot_path = snapshot_path or os.path.join(data_dir, "pipeline_snapshot.json")

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

    def _read_rust_snapshot(self) -> dict | None:
        """Read Rust engine pipeline_snapshot.json. Returns None on failure.
        读取 Rust 引擎管线快照，失败返回 None。"""
        import json
        try:
            with open(self._snapshot_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.debug("Rust snapshot read failed: %s / Rust 快照读取失败", e)
            return None

    def _write_snapshot(self) -> None:
        """Write one round of data to PostgreSQL.
        写入一轮数据到 PostgreSQL。"""
        conn = _get_pg_conn()
        if conn is None:
            return

        try:
            cur = conn.cursor()
            now_ms = int(time.time() * 1000)
            snap = self._read_rust_snapshot()

            self._write_pnl_from_rust(cur, now_ms, snap)
            # market_tickers: handled by Rust market_writer → SKIP
            # 市場行情：由 Rust market_writer 處理 → 跳過
            self._write_system_health_from_rust(cur, now_ms, snap)
            # trade_executions: handled by Rust trading_writer → SKIP
            # 成交記錄：由 Rust trading_writer 處理 → 跳過

            conn.commit()
            self._stats["writes"] += 1
            self._stats["last_write_ts"] = now_ms

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── 1. Paper PnL Snapshots (from Rust IPC snapshot) ──

    def _write_pnl_from_rust(self, cur, now_ms: int, snap: dict | None) -> None:
        """Write PnL snapshot from Rust engine IPC snapshot.
        从 Rust 引擎 IPC 快照写入 PnL 数据。"""
        if snap is None:
            return
        try:
            ps = snap.get("paper_state", {})
            balance = float(ps.get("balance", 0))
            peak = float(ps.get("peak_balance", 0))
            realized_pnl = float(ps.get("total_realized_pnl", 0))
            total_fees = float(ps.get("total_fees", 0))
            trade_count = int(ps.get("trade_count", 0))
            positions = ps.get("positions", [])
            open_positions = len(positions) if isinstance(positions, list) else 0
            net_pnl = realized_pnl - total_fees

            # Unrealized PnL from open positions / 未实现 PnL
            unrealized_pnl = sum(
                float(p.get("position", {}).get("unrealized_pnl", 0))
                for p in positions
            ) if isinstance(positions, list) else 0.0

            cur.execute("""
                INSERT INTO paper_pnl_snapshots_legacy
                    (ts, session_id, realized_pnl, unrealized_pnl, total_fees,
                     ai_cost, net_pnl, open_positions, total_trades, win_rate, sharpe_ratio)
                VALUES (to_timestamp(%s / 1000.0), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                now_ms, "rust_engine", realized_pnl, unrealized_pnl, total_fees,
                0, net_pnl, open_positions, trade_count, None, None,
            ))
        except Exception as e:
            logger.debug("PnL write failed: %s / PnL 写入失败", e)

    # ── 2. System Health (from Rust IPC snapshot) ──

    def _write_system_health_from_rust(self, cur, now_ms: int, snap: dict | None) -> None:
        """Write engine health from Rust IPC snapshot.
        从 Rust IPC 快照写入引擎健康状态。"""
        import json

        if snap is None:
            return
        try:
            stats = snap.get("stats", {})
            total_ticks = stats.get("total_ticks", 0)
            total_fills = stats.get("total_fills", 0)
            last_tick_ms = stats.get("last_tick_ms", 0)
            is_paused = snap.get("paper_paused", False)

            # Staleness check: if last tick > 30s ago, mark stale
            # 过期检查：最后 tick 超过 30 秒标记为过期
            stale_threshold_ms = 30_000
            is_stale = (now_ms - last_tick_ms) > stale_threshold_ms if last_tick_ms > 0 else True
            status = "paused" if is_paused else ("stale" if is_stale else "healthy")

            metrics_json = json.dumps({
                "total_ticks": total_ticks,
                "total_fills": total_fills,
                "last_tick_ms": last_tick_ms,
                "source": "rust_engine",
                "strategies": [s.get("name", "") for s in snap.get("strategies", [])],
            })

            cur.execute("""
                INSERT INTO system_health_legacy (ts, component, status, latency_ms, detail, metrics)
                VALUES (to_timestamp(%s / 1000.0), %s, %s, %s, %s, %s)
            """, (
                now_ms, "rust_engine", status, None,
                f"ticks={total_ticks}, fills={total_fills}, paused={is_paused}",
                metrics_json,
            ))
        except Exception as e:
            logger.debug("Health write failed: %s / 健康写入失败", e)

    # ── Public API ──

    def get_stats(self) -> dict[str, Any]:
        """Return writer statistics for status endpoints."""
        return {
            "component": "grafana_data_writer",
            "running": self._running,
            "interval_sec": self._interval,
            **self._stats,
        }

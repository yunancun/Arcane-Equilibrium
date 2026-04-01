"""
Bybit Demo Data Synchronizer — Pull Demo execution data into PostgreSQL
Bybit Demo 数据同步器 — 从 Demo API 拉取执行数据写入 PostgreSQL

MODULE_NOTE (中文):
  定期从 Bybit Demo API 拉取：
  1. 成交记录 (executions) → trade_executions 表（标记 is_demo=true）
  2. 持仓快照 (positions) → position_snapshots 表
  3. 账户余额 (wallet) → account_snapshots 表

  与 Paper Trading 数据写在同一张表，通过 is_paper / is_demo 标记区分。
  Grafana 可以同时展示两者进行对比。

MODULE_NOTE (English):
  Periodically pulls from Bybit Demo API:
  1. Executions → trade_executions (marked is_demo=true)
  2. Positions → position_snapshots
  3. Wallet balance → account_snapshots

  Written to same tables as Paper Trading data, distinguished by flags.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


def _read_pg_pass_from_secrets() -> str:
    """Read PG password from secrets file. 从 secrets 文件读取数据库密码。"""
    import os
    try:
        path = os.path.expanduser("~/BybitOpenClaw/secrets/compose_env/trading_services.env")
        with open(path) as f:
            for line in f:
                if line.startswith("POSTGRES_PASSWORD="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""


def _default_pg_pass() -> str:
    """Get PG password from env var or secrets file. 从环境变量或 secrets 文件获取密码。"""
    import os
    return os.getenv("PG_PASS") or _read_pg_pass_from_secrets()


class BybitDemoSync:
    """Periodically syncs Bybit Demo data to PostgreSQL."""

    def __init__(
        self,
        demo_connector: Any,
        *,
        interval_sec: float = 60.0,
        pg_host: str = "127.0.0.1",
        pg_port: int = 5432,
        pg_user: str = "trading_admin",
        pg_pass: str = "",
        pg_db: str = "trading_ai",
    ) -> None:
        self._demo = demo_connector
        self._interval = interval_sec
        # Use provided pg_pass, fall back to env/secrets if empty
        # 使用传入的密码，若为空则回退到环境变量/secrets 文件
        effective_pass = pg_pass or _default_pg_pass()
        self._pg_config = dict(host=pg_host, port=pg_port, user=pg_user, password=effective_pass, dbname=pg_db)
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_exec_cursor: str = ""  # Pagination cursor for executions
        self._stats = {"syncs": 0, "executions_synced": 0, "positions_synced": 0, "errors": 0}

    def _get_conn(self):
        try:
            import psycopg2
            return psycopg2.connect(**self._pg_config, connect_timeout=5)
        except Exception as e:
            logger.debug("PG connection failed: %s", e)
            return None

    def start(self) -> None:
        if self._running or not self._demo or not self._demo.is_enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="demo-sync")
        self._thread.start()
        logger.info("Bybit Demo sync started (interval=%ds) / Demo 同步器已启动", self._interval)

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        time.sleep(10)  # Initial delay
        while self._running:
            try:
                self._sync()
            except Exception:
                logger.exception("Demo sync error")
                self._stats["errors"] += 1
            time.sleep(self._interval)

    def _sync(self) -> None:
        conn = self._get_conn()
        if conn is None:
            return

        try:
            cur = conn.cursor()
            now_ms = int(time.time() * 1000)

            # 1. Sync executions (recent trades)
            self._sync_executions(cur, now_ms)

            # 2. Sync positions
            self._sync_positions(cur, now_ms)

            # 3. Sync wallet balance
            self._sync_wallet(cur, now_ms)

            conn.commit()
            self._stats["syncs"] += 1
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _sync_executions(self, cur: Any, now_ms: int) -> None:
        """Pull recent executions from Bybit Demo."""
        try:
            # Get last 50 executions
            result = self._demo.get_executions(category="linear", limit=50)
            if result.get("retCode") != 0:
                return

            executions = result.get("result", {}).get("list", [])
            for ex in executions:
                try:
                    cur.execute("""
                        INSERT INTO trade_executions (ts, exec_id, order_id, symbol, side, exec_type, exec_qty, exec_price, fee, fee_currency, is_paper, strategy)
                        VALUES (to_timestamp(%s/1000.0), %s, %s, %s, %s, %s, %s, %s, %s, %s, false, %s)
                        ON CONFLICT DO NOTHING
                    """, (
                        int(ex.get("execTime", now_ms)),
                        ex.get("execId", ""),
                        ex.get("orderId", ""),
                        ex.get("symbol", ""),
                        ex.get("side", ""),
                        ex.get("execType", "Trade"),
                        float(ex.get("execQty", 0)),
                        float(ex.get("execPrice", 0)),
                        float(ex.get("execFee", 0)),
                        ex.get("feeCurrency", "USDT"),
                        "bybit_demo",
                    ))
                    self._stats["executions_synced"] += 1
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Execution sync failed: %s", e)

    def _sync_positions(self, cur: Any, now_ms: int) -> None:
        """Pull current positions from Bybit Demo — linear and inverse.
        从 Bybit Demo 拉取持仓快照（线性 + 反向，现货无持仓概念跳过）。
        """
        # Spot is intentionally excluded: spot trades produce wallet balance changes,
        # not position entries in /v5/position/list.
        # 现货不走持仓接口，余额变动已在 _sync_wallet() 中记录。
        for cat in ("linear", "inverse"):
            try:
                result = self._demo.get_positions(category=cat)
                if result.get("retCode") != 0:
                    logger.debug("get_positions failed category=%s: %s", cat, result.get("retMsg"))
                    continue

                positions = result.get("result", {}).get("list", [])
                for pos in positions:
                    size = float(pos.get("size", 0))
                    if size == 0:
                        continue
                    try:
                        cur.execute("""
                            INSERT INTO position_snapshots (ts, symbol, side, size, entry_price, mark_price, unrealized_pnl, leverage, position_value, category)
                            VALUES (to_timestamp(%s/1000.0), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            now_ms,
                            pos.get("symbol", ""),
                            pos.get("side", ""),
                            size,
                            float(pos.get("avgPrice", 0)),
                            float(pos.get("markPrice", 0)),
                            float(pos.get("unrealisedPnl", 0)),
                            float(pos.get("leverage", 1)),
                            float(pos.get("positionValue", 0)),
                            cat,
                        ))
                        self._stats["positions_synced"] += 1
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("Position sync failed category=%s: %s", cat, e)

    def _sync_wallet(self, cur: Any, now_ms: int) -> None:
        """Pull wallet balance from Bybit Demo."""
        try:
            result = self._demo.get_wallet_balance()
            if result.get("retCode") != 0:
                return

            coins = result.get("result", {}).get("list", [{}])[0].get("coin", [])
            total_equity = sum(float(c.get("equity", 0)) for c in coins)
            total_balance = sum(float(c.get("walletBalance", 0)) for c in coins)
            unrealized = sum(float(c.get("unrealisedPnl", 0)) for c in coins)

            cur.execute("""
                INSERT INTO account_snapshots (ts, total_equity, available_balance, unrealized_pnl, account_type)
                VALUES (to_timestamp(%s/1000.0), %s, %s, %s, %s)
            """, (now_ms, total_equity, total_balance, unrealized, "bybit_demo"))
        except Exception as e:
            logger.debug("Wallet sync failed: %s", e)

    def get_current_snapshot(self) -> dict[str, Any] | None:
        """
        T7.04: Build reconciliation-format snapshot from current Demo API state.
        从当前 Demo API 状态构建对账格式快照。

        Queries linear and inverse positions.  Spot is intentionally excluded:
        spot trades on Bybit produce wallet balance changes, not position entries.
        Paper spot positions are never submitted to Demo (spot guard in
        pipeline_bridge), so they should not appear in the Demo snapshot either.

        查询线性和反向合约持仓。现货故意排除：Bybit 现货交易体现为余额变化，
        不走持仓接口。pipeline_bridge 中的 spot guard 确保现货不提交到 Demo。

        Returns snapshot in reconciliation format:
        {
            "snapshot_ts_ms": int,
            "orders": [],
            "positions": {symbol: {"side", "size", "avg_entry_price", "category"}},
            "fills": [],
            "balances": {asset: balance},
            "spot_positions_excluded": True,  # signal to reconciler
        }
        """
        try:
            # Query positions for linear and inverse categories
            # 查询线性和反向合约持仓（各自独立请求）
            positions_dict: dict[str, Any] = {}
            for cat in ("linear", "inverse"):
                cat_result = self._demo.get_positions(category=cat)
                if cat_result.get("retCode") != 0:
                    logger.warning(
                        "Demo get_positions failed category=%s: %s",
                        cat, cat_result.get("retMsg"),
                    )
                    continue
                for pos in cat_result.get("result", {}).get("list", []):
                    symbol = pos.get("symbol")
                    if symbol and float(pos.get("size", 0)) > 0:
                        positions_dict[symbol] = {
                            "side": pos.get("side"),
                            "size": float(pos.get("size")),
                            "avg_entry_price": float(pos.get("avgPrice", 0)),
                            "category": cat,
                        }

            wallet_raw = self._demo.get_wallet_balance()
            coins = wallet_raw.get("result", {}).get("list", [{}])[0].get("coin", [])
            balances: dict[str, float] = {}
            for c in coins:
                coin_name = c.get("coin")
                balance = float(c.get("walletBalance", 0))
                if coin_name and balance > 0:
                    balances[coin_name] = balance

            return {
                "snapshot_ts_ms": int(time.time() * 1000),
                "orders": [],
                "positions": positions_dict,
                "fills": [],
                "balances": balances,
                "spot_positions_excluded": True,  # signal: reconciler should skip spot symbols
            }
        except Exception as e:
            logger.error("Failed to get demo snapshot for reconciliation: %s", e)
            return None

    def get_stats(self) -> dict[str, Any]:
        return {"component": "bybit_demo_sync", "running": self._running, **self._stats}

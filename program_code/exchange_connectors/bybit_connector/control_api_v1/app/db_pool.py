"""
Shared PostgreSQL connection pool for Dashboard and API read paths.
共享 PostgreSQL 連接池，供 Dashboard 和 API 讀取路徑使用。

MODULE_NOTE (EN): ThreadedConnectionPool wraps psycopg2 with connection reuse.
  Eliminates per-request connection overhead (3-5s connect timeout).
  Graceful degradation: returns None on pool exhaustion or PG unavailability.
  Singleton initialized on first import — thread-safe via psycopg2.pool internals.

MODULE_NOTE (中): ThreadedConnectionPool 封裝 psycopg2 實現連接復用。
  消除每請求的連接開銷（3-5s 連接超時）。
  優雅降級：連接池耗盡或 PG 不可用時返回 None。
  單例在首次導入時初始化 — 通過 psycopg2.pool 內部實現線程安全。
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


def _read_pg_pass_from_secrets() -> str:
    """Read PG password from secrets file. 從 secrets 文件讀取數據庫密碼。

    Cross-platform (CLAUDE.md §七): resolves $OPENCLAW_SECRETS_ROOT first,
    then falls back to ~/BybitOpenClaw/secrets (Linux legacy layout).
    跨平台 (CLAUDE.md §七)：優先解析 $OPENCLAW_SECRETS_ROOT，再 fallback 到
    ~/BybitOpenClaw/secrets（Linux 舊佈局）。
    """
    roots: list[str] = []
    env_root = os.environ.get("OPENCLAW_SECRETS_ROOT")
    if env_root:
        roots.append(env_root)
    roots.append(os.path.expanduser("~/BybitOpenClaw/secrets"))

    candidates: list[str] = []
    for root in roots:
        candidates.append(os.path.join(root, "environment_files", "basic_system_services.env"))
        candidates.append(os.path.join(root, "compose_env", "trading_services.env"))

    for path in candidates:
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("POSTGRES_PASSWORD="):
                        return line.split("=", 1)[1].strip()
        except FileNotFoundError:
            continue
    return ""


# Connection parameters / 連接參數
# Cross-platform: prefer OPENCLAW_PG_PORT (shared with restart_all.sh / engine)
# before falling through to PG_PORT. Mac dev's dockerised PG runs on 15432;
# Linux native on 5432.
# 跨平台：優先讀 OPENCLAW_PG_PORT（與 restart_all.sh / engine 共用），再 fallback
# PG_PORT。Mac dev dockerised PG 在 15432，Linux 原生 5432。
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("OPENCLAW_PG_PORT") or os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "trading_admin")
PG_PASS = os.getenv("PG_PASS") or _read_pg_pass_from_secrets()
PG_DB = os.getenv("PG_DB", "trading_ai")

# Pool sizing / 連接池大小
_POOL_MIN = int(os.getenv("PG_POOL_MIN", "2"))
_POOL_MAX = int(os.getenv("PG_POOL_MAX", "10"))

# Singleton pool instance / 單例連接池
_pool = None
_pool_init_attempted = False


def _init_pool():
    """Initialize the singleton connection pool. 初始化單例連接池。"""
    global _pool, _pool_init_attempted
    if _pool_init_attempted:
        return
    _pool_init_attempted = True

    try:
        from psycopg2.pool import ThreadedConnectionPool
        _pool = ThreadedConnectionPool(
            _POOL_MIN, _POOL_MAX,
            host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=PG_DB,
            connect_timeout=5,
        )
        logger.info("PG pool initialized (min=%d, max=%d) / PG 連接池已初始化", _POOL_MIN, _POOL_MAX)
    except ImportError:
        logger.debug("psycopg2 not installed — DB pool disabled / psycopg2 未安裝")
    except Exception as e:
        logger.warning("PG pool init failed: %s — fallback to per-request / PG 連接池初始化失敗，回退到每請求連接", e)


def get_conn():
    """Get a connection from the pool. Returns None on failure (graceful degradation).
    從連接池獲取連接。失敗時返回 None（優雅降級）。

    Caller must call put_conn(conn) when done, or use the get_pg_conn() context manager.
    調用者完成後必須調用 put_conn(conn)，或使用 get_pg_conn() 上下文管理器。
    """
    if _pool is None:
        _init_pool()
    if _pool is None:
        return None
    try:
        return _pool.getconn()
    except Exception as e:
        logger.debug("Pool getconn failed: %s", e)
        return None


def put_conn(conn) -> None:
    """Return a clean connection to the pool.

    Always roll back before reuse so a failed handler cannot leak transaction
    state, locks, or session errors into the next request. If rollback itself
    fails, discard the connection instead of recycling a poisoned handle.
    歸還前一律 rollback，避免失敗請求的 transaction/session 狀態污染下一次借用；
    rollback 失敗時關閉丟棄該連接。
    """
    if _pool is None or conn is None:
        return
    close_conn = False
    try:
        conn.rollback()
    except Exception as exc:
        close_conn = True
        logger.warning("PG pooled connection rollback failed; discarding connection: %s", exc)
    try:
        _pool.putconn(conn, close=close_conn)
    except TypeError:
        # Test doubles or alternate pool shims may not support close=.
        try:
            if close_conn and hasattr(conn, "close"):
                conn.close()
            _pool.putconn(conn)
        except Exception:
            logger.debug("Pool putconn failed after rollback handling", exc_info=True)
    except Exception:
        logger.debug("Pool putconn failed after rollback handling", exc_info=True)


@contextmanager
def get_pg_conn():
    """Context manager that borrows a pooled connection and auto-returns it.
    上下文管理器，借用連接池連接並自動歸還。

    Usage / 用法:
        with get_pg_conn() as conn:
            if conn is None:
                return  # DB unavailable
            cur = conn.cursor()
            ...
    """
    conn = get_conn()
    try:
        yield conn
    finally:
        if conn is not None:
            put_conn(conn)


def pool_stats() -> dict:
    """Return pool statistics for /health/db endpoint. 返回連接池統計信息。"""
    if _pool is None:
        return {"available": False, "reason": "pool_not_initialized"}
    try:
        # psycopg2 ThreadedConnectionPool doesn't expose stats directly,
        # but we can check pool state
        return {
            "available": True,
            "min_connections": _POOL_MIN,
            "max_connections": _POOL_MAX,
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}

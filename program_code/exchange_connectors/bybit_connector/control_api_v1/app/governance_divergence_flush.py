"""
Governance Divergence Comparator — counter → PG snapshot flusher
（SM Option 2 收斂 step-(i) soak 可觀測性 B-3）。

MODULE_NOTE:
    模塊用途：把 governance_divergence.py 的 in-memory comparator 計數器
    （``_COUNTERS``：total/matches/divergences，API worker process-local 記憶體）
    best-effort 週期 UPSERT 到 PG 表 ``learning.lease_ipc_divergence_snapshot``
    （V128），讓獨立的 passive_wait_healthcheck cron process 能以 SQL-cursor 讀到
    soak 信號（cron 既讀不到 API worker 記憶體、counter 也不落 PG → 需此橋接）。

    主要類/函數：
      - ``flush_divergence_snapshot_once``：讀 counter snapshot → UPSERT 一次（純函式，
        回傳是否成功，供測試直驅）。
      - ``divergence_snapshot_flusher``：asyncio 背景協程，leader-elected 單一 writer，
        每 ``_FLUSH_INTERVAL_S`` 跑一次 flush，cancellation-aware。
      - ``_acquire_flusher_leader_lock``：flock-based best-effort leader 鎖（對齊
        paper_trading_wiring._acquire_reconciler_alert_lock 範式），避免多 worker
        重複寫同一 'singleton' row。

    依賴：
      - governance_divergence.get_divergence_counters()（讀 in-memory 計數器，唯讀）。
      - governance_lease_bridge.is_lease_ipc_enabled()（記錄 flush 當下 flag 狀態）。
      - db_pool.get_pg_conn()（共享 PG 連接池，fail-soft 回 None）。

    硬邊界（fail-soft 契約，對齊 governance_divergence.py best-effort）：
      - **本 flusher 絕不向上傳播例外到熱路徑 / record_divergence / 任一 5 live-auth
        gate。** flush 失敗只 log + 下一輪重試；comparator 與權威 lease 回傳值完全
        不受影響（G-2）。
      - **不持有 comparator lock 過久**：只呼叫 get_divergence_counters()（內部短暫
        持 _DIVERGENCE_LOCK 取 dict copy 即釋放），釋鎖*後*才連 PG / 寫入。flush 的
        PG I/O 不在 comparator lock 內（G-2）。
      - 本模塊不改 comparator 計數器、不改任何 lease / SM / 風控狀態；純*讀*計數器 +
        *寫*獨立投影表。
      - 純觀測投影；step-(iv) cleanup 連同 comparator 退役。

    為什麼與 governance_divergence.py 分檔：comparator 是純觀測（無 PG / 無 I/O，
    其 fail-soft 契約靠「不做任何會失敗的事」維持）；flusher 需 PG + leader-lock +
    asyncio，是不同關注點。分檔讓 comparator 保持 byte-unchanged（其 singleton-registry
    §2.5 登記與契約不動），flusher 的 I/O 失敗面隔離在本檔。

singleton-registry：本模塊新增一個 module-level 可變 leader-lock fd
    ``_FLUSHER_LEADER_LOCK_FD``，已登記於 docs/architecture/singleton-registry.md
    §2.5.4（與 comparator sink 同 step-(i) 退役）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

# flush 週期（秒）。soak 視窗 24-48h；30s cadence 對 1-row UPSERT 開銷可忽略，
# 且讓 healthcheck freshness gate 的 stale 偵測有足夠解析度（freshness threshold
# 通常 >> 30s）。對齊 reconciler_alert_monitor 的 30s poll cadence。
_FLUSH_INTERVAL_S: int = 30

# UPSERT 目標 key（V128 表 snapshot_key 預設值）；單一 leader writer 永遠寫此 key。
_SNAPSHOT_KEY: str = "singleton"

# 強制非 leader 的 env（對齊 OPENCLAW_RECON_ALERT_MONITOR_LEADER 慣例）。
_LEADER_ENV: str = "OPENCLAW_LEASE_DIVERGENCE_FLUSHER_LEADER"

# module-level leader-lock fd（singleton-registry §2.5.4）。None=尚未取得 / 非 leader。
_FLUSHER_LEADER_LOCK_FD: int | None = None


def _acquire_flusher_leader_lock() -> bool:
    """best-effort leader 鎖：避免多 uvicorn worker 重複 flush 同一 'singleton' row。

    對齊 paper_trading_wiring._acquire_reconciler_alert_lock 的 flock 範式
    （O_CREAT + LOCK_EX|LOCK_NB；拿到 = 本 worker 為 leader）。

    為什麼 best-effort 而非 PG advisory lock：flusher 是純觀測，多 worker 同時寫
    同一 UPSERT row 也只是冪等覆蓋（不會壞資料），flock 只是減少冗餘寫；取不到鎖
    就安靜退出（非 leader worker 不 flush）。env 可強制關閉本 worker 的 flush。
    """
    global _FLUSHER_LEADER_LOCK_FD
    if _FLUSHER_LEADER_LOCK_FD is not None:
        return True
    if os.environ.get(_LEADER_ENV) == "0":
        logger.info(
            "lease-divergence flusher forced non-leader by env / 由環境變數強制非 leader"
        )
        return False

    import fcntl  # noqa: PLC0415 — Unix-only；對齊 reconciler lock 的 local import

    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    lock_path = os.path.join(data_dir, "lease_ipc_divergence_flusher.leader.lock")
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as exc:
        logger.warning(
            "lease-divergence flusher: unable to open leader lock %s (%s), "
            "flusher disabled on this worker / 無法開啟 leader 鎖，本 worker 停用 flusher",
            lock_path, exc,
        )
        return False

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        os.close(fd)
        logger.info(
            "lease-divergence flusher: non-leader worker (lock held at %s) / 非 leader worker",
            lock_path,
        )
        return False

    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
    except OSError:
        pass
    _FLUSHER_LEADER_LOCK_FD = fd
    return True


def flush_divergence_snapshot_once() -> bool:
    """讀 comparator 計數器 snapshot → UPSERT learning.lease_ipc_divergence_snapshot 一次。

    Best-effort / fail-soft：本函式絕不向 caller 拋例外（任何失敗回 False + log）。
    **絕不影響權威路徑 / comparator / record_divergence**——只*讀* counter（get_divergence_
    counters 內部短持 lock 取 dict copy 即釋放）並*寫*獨立投影表；PG I/O 不在 comparator
    lock 內持有（G-2）。

    Returns / 回傳:
        True 若成功 UPSERT；False 若任何步驟失敗（counter 讀取 / PG 不可用 / 寫入例外）。
    """
    try:
        # ── 步驟 1：讀 in-memory counter snapshot（釋鎖後即得 dict copy，不持 lock）──
        from .governance_divergence import get_divergence_counters  # noqa: PLC0415

        counters = get_divergence_counters()
        total = int(counters.get("total", 0))
        matches = int(counters.get("matches", 0))
        divergences = int(counters.get("divergences", 0))

        # ── 步驟 2：讀 flag 狀態（記錄 flush 當下是否 flag-ON，供 soak gate 前置判定）──
        try:
            from .governance_lease_bridge import is_lease_ipc_enabled  # noqa: PLC0415
            flag_enabled = bool(is_lease_ipc_enabled())
        except Exception:  # noqa: BLE001 — flag 讀取失敗不阻斷 flush，保守記 False
            flag_enabled = False

        flusher_ts_ms = int(time.time() * 1000)

        # ── 步驟 3：UPSERT 投影表（PG I/O 在此，不持任何 comparator lock）──
        from .db_pool import get_pg_conn  # noqa: PLC0415

        with get_pg_conn() as conn:
            if conn is None:
                # PG 不可用 → fail-soft（不拋）；healthcheck freshness gate 會偵測 stale。
                logger.debug(
                    "lease-divergence flush skipped: PG unavailable / PG 不可用，跳過本輪 flush"
                )
                return False
            with conn.cursor() as cur:
                # updated_at 用 DB-side now()（freshness gate 權威）；ON CONFLICT 覆蓋
                # 既有 'singleton' row（表至多 1 row）。
                cur.execute(
                    """
                    INSERT INTO learning.lease_ipc_divergence_snapshot
                        (snapshot_key, total, matches, divergences,
                         flag_enabled, flusher_ts_ms, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (snapshot_key) DO UPDATE SET
                        total         = EXCLUDED.total,
                        matches       = EXCLUDED.matches,
                        divergences   = EXCLUDED.divergences,
                        flag_enabled  = EXCLUDED.flag_enabled,
                        flusher_ts_ms = EXCLUDED.flusher_ts_ms,
                        updated_at    = now()
                    """,
                    (_SNAPSHOT_KEY, total, matches, divergences,
                     flag_enabled, flusher_ts_ms),
                )
            conn.commit()
        return True
    except Exception:  # noqa: BLE001 — flusher best-effort，絕不影響權威路徑 / comparator
        # debug 級別：soak 期 PG 抖動不該洗 WARN log；真死掉由 healthcheck freshness 抓。
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "flush_divergence_snapshot_once 內部錯誤已吞噬（不影響權威路徑）",
                exc_info=True,
            )
        return False


async def divergence_snapshot_flusher() -> None:
    """asyncio 背景協程：leader-elected，每 _FLUSH_INTERVAL_S 跑一次 flush。

    由 main.py @app.on_event("startup") 以 asyncio.create_task 排程（fail-open，不阻斷
    啟動）。cancellation-aware：shutdown 時 CancelledError 乾淨退出。

    為什麼把 flush 放 executor：flush_divergence_snapshot_once 是同步 PG I/O（psycopg2
    阻塞）；放 loop.run_in_executor 避免阻塞事件循環（對齊「啟動 <100ms / 不阻塞 await」
    紀律）。flush 自身 fail-soft，executor 內例外已被吞（回 False），故 await 不會拋。
    """
    if not _acquire_flusher_leader_lock():
        return

    logger.info(
        "lease-divergence snapshot flusher started (interval=%ds) / "
        "lease 分歧計數器 PG 投影 flusher 已啟動",
        _FLUSH_INTERVAL_S,
    )
    loop = asyncio.get_event_loop()
    while True:
        try:
            await asyncio.sleep(_FLUSH_INTERVAL_S)
        except asyncio.CancelledError:
            logger.info(
                "lease-divergence snapshot flusher cancelled / lease 分歧 flusher 已取消"
            )
            return
        try:
            # 同步 PG I/O 丟 executor，不阻塞事件循環；flush 內部 fail-soft 不拋。
            await loop.run_in_executor(None, flush_divergence_snapshot_once)
        except asyncio.CancelledError:
            logger.info(
                "lease-divergence snapshot flusher cancelled mid-flush / flusher 取消"
            )
            return
        except Exception as exc:  # noqa: BLE001 — 雙保險，executor 異常也不殺協程
            logger.debug(
                "lease-divergence flusher loop iteration error (continuing): %s", exc
            )


def _reset_flusher_leader_lock_for_tests() -> None:
    """僅供測試隔離：清空 module-level leader-lock fd（勿於 production 呼叫）。"""
    global _FLUSHER_LEADER_LOCK_FD
    if _FLUSHER_LEADER_LOCK_FD is not None:
        try:
            os.close(_FLUSHER_LEADER_LOCK_FD)
        except OSError:
            pass
    _FLUSHER_LEADER_LOCK_FD = None


__all__ = [
    "flush_divergence_snapshot_once",
    "divergence_snapshot_flusher",
]

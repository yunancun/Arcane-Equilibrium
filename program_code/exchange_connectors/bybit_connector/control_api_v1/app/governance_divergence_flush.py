"""
Governance Divergence Comparator — counter → PG snapshot flusher
（SM Option 2 收斂 step-(i) soak 可觀測性 B-3）。

MODULE_NOTE:
    模塊用途：把 governance_divergence.py 的 in-memory comparator 計數器
    （``_COUNTERS``：total/matches/divergences，API worker process-local 記憶體）
    best-effort 週期 UPSERT 到 PG 表 ``learning.lease_ipc_divergence_snapshot``
    （V129），讓獨立的 passive_wait_healthcheck cron process 能以 SQL-cursor 讀到
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

    ── P5-SM soak 第二輪擴充（E1-B，2026-06-10）──
    per PA 設計 `2026-06-10--p5sm_soak_observability_redesign.md` §3.1：
      - ``flush_canary_snapshot_once``：把 governance_ipc_canary 計數器 UPSERT 到
        V129 key='canary'（欄位映射 total=attempts / matches=ok / divergences=fail；
        V129 CHECK total>=matches+divergences 因 attempts==ok+fail 天然成立）。
        **同進程不變量**：canary 複用本檔同一把 flock（見 governance_ipc_canary
        MODULE_NOTE）→ leader 進程內 get_canary_counters() 讀到的就是真計數。
      - epoch/flag 事件帳本（V137 learning.lease_ipc_soak_events，append-only）：
        leader 啟動時先讀舊 V129 兩 row 寫 ``epoch_rollover``（搶救前一 epoch 終值，
        損失 ≤30s）+ ``flusher_start``；週期偵測 flag 變遷（``flag_change``）/
        canary 失敗連段增量（``canary_fail_streak``）/ 程內計數器倒退
        （``counter_regression``）。`[82]` soak-window check 以這些事件跨 epoch
        重建連續有效窗。V137 未 apply 時全部 fail-soft（事件寫入失敗只 debug log，
        絕不影響權威路徑 / comparator / canary）。

singleton-registry：本模塊的 module-level 可變單例：
    ``_FLUSHER_LEADER_LOCK_FD``（§2.5.4）+ soak 事件偵測 trackers
    ``_SOAK_TRACKERS``（§2.5.6；單一 flusher 協程順序讀寫，await happens-before
    保證可見性，無需鎖）。皆與 comparator sink 同 step-(iv) 退役。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# flush 週期（秒）。soak 視窗 24-48h；30s cadence 對 1-row UPSERT 開銷可忽略，
# 且讓 healthcheck freshness gate 的 stale 偵測有足夠解析度（freshness threshold
# 通常 >> 30s）。對齊 reconciler_alert_monitor 的 30s poll cadence。
_FLUSH_INTERVAL_S: int = 30

# UPSERT 目標 key（V129 表 snapshot_key 預設值）；單一 leader writer 永遠寫此 key。
_SNAPSHOT_KEY: str = "singleton"

# canary 計數器投影的 V129 key（P5-SM soak 第二輪 E1-B；同一 leader writer）。
_CANARY_SNAPSHOT_KEY: str = "canary"

# 強制非 leader 的 env（對齊 OPENCLAW_RECON_ALERT_MONITOR_LEADER 慣例）。
_LEADER_ENV: str = "OPENCLAW_LEASE_DIVERGENCE_FLUSHER_LEADER"

# module-level leader-lock fd（singleton-registry §2.5.4）。None=尚未取得 / 非 leader。
_FLUSHER_LEADER_LOCK_FD: int | None = None

# ── P5-SM soak 第二輪：事件偵測 trackers（singleton-registry §2.5.6）──
# 只由 leader 進程的單一 flusher 協程順序讀寫（run_in_executor 逐次 await，
# happens-before 保證跨 executor thread 可見性）→ 無需鎖。restart 歸零 = epoch
# 邊界語義（epoch_rollover 事件本身就是為此存在）。
_SOAK_TRACKERS: dict[str, Any] = {
    # 上次 flush 觀測到的 lease-IPC flag 狀態（None=本 epoch 尚未觀測）。
    "last_flag_state": None,
    # 上次觀測到的 canary fail_streak_breaches（增量 → 寫 canary_fail_streak 事件）。
    "last_canary_breaches": None,
    # 本 epoch 是否已寫 canary_leader_start（attempts 0→>0 時寫一次）。
    "canary_start_recorded": False,
    # 上次 flush 的計數值（程內單調性交叉檢查；倒退 → counter_regression 事件）。
    "last_comparator_counts": None,
    "last_canary_counts": None,
    # 本 epoch 是否已寫 epoch 起點事件（flusher_start + epoch_rollover）。
    "epoch_start_recorded": False,
}


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


# ═══════════════════════════════════════════════════════════════════════════════
# P5-SM soak 第二輪（E1-B）：canary 投影 + V137 事件帳本
# ═══════════════════════════════════════════════════════════════════════════════

def _read_lease_flag_state() -> bool:
    """讀 lease-IPC flag 當下狀態（讀取失敗保守記 False，與既有 flush 同策略）。"""
    try:
        from .governance_lease_bridge import is_lease_ipc_enabled  # noqa: PLC0415

        return bool(is_lease_ipc_enabled())
    except Exception:  # noqa: BLE001 — flag 讀取失敗不阻斷，保守 False
        return False


def flush_canary_snapshot_once() -> bool:
    """讀 canary 計數器 → UPSERT V129 key='canary' 一次（best-effort / fail-soft）。

    欄位映射（V137 頭部 + singleton-registry §2.5.5 文檔化）：
    total=attempts / matches=ok / divergences=fail。canary 的 attempts==ok+fail
    不變量讓 V129 CHECK ``total >= matches + divergences`` 天然成立。

    為什麼 canary 行也由本 flusher 寫：canary 複用本檔同一把 flock → 兩者必在
    同一 leader 進程 → 本進程的 get_canary_counters() 讀到真計數（同進程不變量，
    load-bearing；分鎖會選出不同進程 = flusher 永遠讀到 0 = silent 假死）。
    """
    try:
        from .governance_ipc_canary import get_canary_counters  # noqa: PLC0415

        counters = get_canary_counters()
        attempts = int(counters.get("attempts", 0))
        ok_count = int(counters.get("ok", 0))
        fail_count = int(counters.get("fail", 0))
        flag_enabled = _read_lease_flag_state()
        flusher_ts_ms = int(time.time() * 1000)

        from .db_pool import get_pg_conn  # noqa: PLC0415

        with get_pg_conn() as conn:
            if conn is None:
                logger.debug(
                    "canary snapshot flush skipped: PG unavailable / PG 不可用，跳過"
                )
                return False
            with conn.cursor() as cur:
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
                    (_CANARY_SNAPSHOT_KEY, attempts, ok_count, fail_count,
                     flag_enabled, flusher_ts_ms),
                )
            conn.commit()
        return True
    except Exception:  # noqa: BLE001 — fail-soft，絕不影響權威路徑 / canary
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "flush_canary_snapshot_once 內部錯誤已吞噬（不影響權威路徑）",
                exc_info=True,
            )
        return False


def _insert_soak_events(events: list[dict[str, Any]]) -> bool:
    """把一批事件 INSERT 進 V137 learning.lease_ipc_soak_events（append-only）。

    Best-effort / fail-soft：V137 未 apply / PG 不可用 / 任何例外 → 回 False +
    debug log，**絕不拋**。每事件 dict 鍵：event_type（必）、flag_enabled（必）、
    prev_total / prev_matches / prev_divergences / prev_canary_attempts /
    prev_canary_ok / prev_canary_fail（可 None）、detail（dict 或 None）。
    """
    if not events:
        return True
    try:
        from .db_pool import get_pg_conn  # noqa: PLC0415

        with get_pg_conn() as conn:
            if conn is None:
                logger.debug("soak event insert skipped: PG unavailable")
                return False
            with conn.cursor() as cur:
                for ev in events:
                    detail = ev.get("detail")
                    cur.execute(
                        """
                        INSERT INTO learning.lease_ipc_soak_events
                            (event_type, flag_enabled,
                             prev_total, prev_matches, prev_divergences,
                             prev_canary_attempts, prev_canary_ok, prev_canary_fail,
                             detail)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            ev["event_type"],
                            bool(ev["flag_enabled"]),
                            ev.get("prev_total"),
                            ev.get("prev_matches"),
                            ev.get("prev_divergences"),
                            ev.get("prev_canary_attempts"),
                            ev.get("prev_canary_ok"),
                            ev.get("prev_canary_fail"),
                            json.dumps(detail) if detail is not None else None,
                        ),
                    )
            conn.commit()
        return True
    except Exception:  # noqa: BLE001 — V137 未 apply / PG 抖動皆 fail-soft
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "_insert_soak_events 內部錯誤已吞噬（V137 未 apply 或 PG 不可用）",
                exc_info=True,
            )
        return False


def _current_counts_snapshot() -> tuple[dict[str, int], dict[str, int]]:
    """讀 comparator + canary 當下計數快照（事件的 prev_* 欄；讀失敗回空 dict）。"""
    comparator: dict[str, int] = {}
    canary_counts: dict[str, int] = {}
    try:
        from .governance_divergence import get_divergence_counters  # noqa: PLC0415

        comparator = get_divergence_counters()
    except Exception:  # noqa: BLE001 — 計數讀取失敗不阻斷事件記錄（prev_* NULL-able）
        pass
    try:
        from .governance_ipc_canary import get_canary_counters  # noqa: PLC0415

        canary_counts = get_canary_counters()
    except Exception:  # noqa: BLE001 — 同上
        pass
    return comparator, canary_counts


def _event_payload(
    event_type: str,
    flag_enabled: bool,
    comparator: dict[str, int],
    canary_counts: dict[str, int],
    detail: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """組一筆事件 dict（prev_* = emit 當下的本 epoch 計數快照；V137 語義）。"""
    return {
        "event_type": event_type,
        "flag_enabled": flag_enabled,
        "prev_total": comparator.get("total"),
        "prev_matches": comparator.get("matches"),
        "prev_divergences": comparator.get("divergences"),
        "prev_canary_attempts": canary_counts.get("attempts"),
        "prev_canary_ok": canary_counts.get("ok"),
        "prev_canary_fail": canary_counts.get("fail"),
        "detail": detail,
    }


def record_epoch_start_events_once() -> bool:
    """leader 啟動時記 epoch 起點事件（每 epoch 恰一次）：epoch_rollover + flusher_start。

    epoch_rollover：讀 V129 既有 'singleton'/'canary' row（前一 epoch 被 UPSERT
    覆寫前的終值，損失 ≤30s），prev_* 攜終值、detail 攜兩 row 的末次 flush 時間戳
    （epoch 秒）供 `[82]` 算 epoch 間隙 ≤30min。V129 無 row（首次部署）→ 只寫
    flusher_start。Best-effort：任何失敗回 False，下輪**不再重試**（標記已記，
    避免把「啟動事件」變成週期噪音；epoch 邊界證據缺失由 `[82]` counter-regression
    交叉偵測兜底）。
    """
    if _SOAK_TRACKERS["epoch_start_recorded"]:
        return True
    _SOAK_TRACKERS["epoch_start_recorded"] = True

    flag_enabled = _read_lease_flag_state()
    events: list[dict[str, Any]] = []
    try:
        prev_rows: dict[str, tuple[int, int, int, int, bool]] = {}
        from .db_pool import get_pg_conn  # noqa: PLC0415

        with get_pg_conn() as conn:
            if conn is not None:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT snapshot_key, total, matches, divergences,
                               EXTRACT(EPOCH FROM updated_at)::BIGINT,
                               flag_enabled
                        FROM learning.lease_ipc_divergence_snapshot
                        WHERE snapshot_key IN (%s, %s)
                        """,
                        (_SNAPSHOT_KEY, _CANARY_SNAPSHOT_KEY),
                    )
                    for row in cur.fetchall() or []:
                        prev_rows[str(row[0])] = (
                            int(row[1] or 0), int(row[2] or 0),
                            int(row[3] or 0), int(row[4] or 0),
                            bool(row[5]),
                        )
                # 唯讀查詢後 rollback 釋放 tx（不留 idle-in-transaction）。
                conn.rollback()

        if prev_rows:
            singleton = prev_rows.get(_SNAPSHOT_KEY)
            canary_prev = prev_rows.get(_CANARY_SNAPSHOT_KEY)
            # prev_flag_enabled = 前一 epoch 末次 flush 的 flag 狀態（兩 row OR）。
            # 為什麼必要：跨 restart 的 OFF→ON 轉變（operator 寫 env 檔後重啟）不會
            # 產生同 epoch 內的 flag_change 事件，`[82]` 靠本欄識別「flag 在本
            # rollover 才轉 ON」→ 窗錨點重置在 rollover，不可往前延伸虛胖窗。
            prev_flag = bool(
                (singleton[4] if singleton else False)
                or (canary_prev[4] if canary_prev else False)
            )
            events.append({
                "event_type": "epoch_rollover",
                "flag_enabled": flag_enabled,
                "prev_total": singleton[0] if singleton else None,
                "prev_matches": singleton[1] if singleton else None,
                "prev_divergences": singleton[2] if singleton else None,
                "prev_canary_attempts": canary_prev[0] if canary_prev else None,
                "prev_canary_ok": canary_prev[1] if canary_prev else None,
                "prev_canary_fail": canary_prev[2] if canary_prev else None,
                "detail": {
                    # tuple 佈局：(total, matches, divergences, updated_at_epoch_s, flag)
                    "prev_singleton_updated_at_epoch_s": (
                        singleton[3] if singleton else None
                    ),
                    "prev_canary_updated_at_epoch_s": (
                        canary_prev[3] if canary_prev else None
                    ),
                    "prev_flag_enabled": prev_flag,
                },
            })
    except Exception:  # noqa: BLE001 — 前值搶救失敗不阻斷 flusher_start 記錄
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("epoch_rollover 前值讀取失敗（已吞噬）", exc_info=True)

    comparator, canary_counts = _current_counts_snapshot()
    events.append(_event_payload("flusher_start", flag_enabled, comparator, canary_counts))
    return _insert_soak_events(events)


def detect_and_record_soak_events_once() -> bool:
    """週期事件偵測（每輪 flush 後跑一次）：flag_change / canary_leader_start /
    canary_fail_streak / counter_regression。

    全部 best-effort；偵測本身純記憶體比對（trackers vs 當下快照），只有事件
    INSERT 碰 PG（fail-soft）。trackers 在**寫入成功與否之外**都會前移——事件
    寫失敗寧可漏記也不重複轟（append-only 帳本的 dedupe 由 tracker 前移保證）。
    """
    try:
        flag_enabled = _read_lease_flag_state()
        comparator, canary_counts = _current_counts_snapshot()
        events: list[dict[str, Any]] = []

        # ── flag 變遷（S4 flag-OFF 觀測軸；首次觀測只記 baseline 不發事件）──
        last_flag = _SOAK_TRACKERS["last_flag_state"]
        if last_flag is not None and bool(last_flag) != flag_enabled:
            events.append(_event_payload(
                "flag_change", flag_enabled, comparator, canary_counts,
                detail={"from": bool(last_flag), "to": flag_enabled},
            ))
        _SOAK_TRACKERS["last_flag_state"] = flag_enabled

        # ── canary 開始 probe（attempts 0→>0，每 epoch 一次）──
        attempts = int(canary_counts.get("attempts", 0) or 0)
        if attempts > 0 and not _SOAK_TRACKERS["canary_start_recorded"]:
            _SOAK_TRACKERS["canary_start_recorded"] = True
            events.append(_event_payload(
                "canary_leader_start", flag_enabled, comparator, canary_counts,
            ))

        # ── canary 失敗連段增量（S3 ≥15min 連段證據）──
        breaches = int(canary_counts.get("fail_streak_breaches", 0) or 0)
        last_breaches = _SOAK_TRACKERS["last_canary_breaches"]
        if last_breaches is not None and breaches > int(last_breaches):
            events.append(_event_payload(
                "canary_fail_streak", flag_enabled, comparator, canary_counts,
                detail={"breaches": breaches, "prev_breaches": int(last_breaches)},
            ))
        _SOAK_TRACKERS["last_canary_breaches"] = breaches

        # ── 程內計數器倒退（S4 記帳完整性；in-memory 計數器設計上單調，倒退 =
        #    bug / 測試 reset 汙染，必須留痕）──
        for axis, current, tracker_key in (
            ("comparator", comparator, "last_comparator_counts"),
            ("canary", canary_counts, "last_canary_counts"),
        ):
            last = _SOAK_TRACKERS[tracker_key]
            if last is not None and current:
                for key, last_val in last.items():
                    cur_val = current.get(key)
                    if cur_val is not None and int(cur_val) < int(last_val):
                        events.append(_event_payload(
                            "counter_regression", flag_enabled,
                            comparator, canary_counts,
                            detail={
                                "axis": axis, "key": key,
                                "before": int(last_val), "after": int(cur_val),
                            },
                        ))
                        break  # 每軸每輪至多一筆（避免單次倒退多鍵轟帳本）
            if current:
                _SOAK_TRACKERS[tracker_key] = dict(current)

        return _insert_soak_events(events)
    except Exception:  # noqa: BLE001 — 偵測層雙保險，絕不影響權威路徑
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "detect_and_record_soak_events_once 內部錯誤已吞噬", exc_info=True
            )
        return False


def flush_observability_cycle_once() -> bool:
    """單輪完整觀測 flush（loop 每 30s 跑）：comparator 投影 + canary 投影 + 事件偵測。

    各步驟獨立 fail-soft（一步失敗不阻斷其他步驟）；回傳「全部成功與否」僅供測試
    斷言，caller（flusher loop）不依賴回傳值。
    """
    ok_singleton = flush_divergence_snapshot_once()
    ok_canary = flush_canary_snapshot_once()
    ok_events = detect_and_record_soak_events_once()
    return ok_singleton and ok_canary and ok_events


def _reset_soak_event_trackers_for_tests() -> None:
    """僅供測試隔離：重置事件偵測 trackers（勿於 production 呼叫）。"""
    _SOAK_TRACKERS.update(
        last_flag_state=None,
        last_canary_breaches=None,
        canary_start_recorded=False,
        last_comparator_counts=None,
        last_canary_counts=None,
        epoch_start_recorded=False,
    )


async def divergence_snapshot_flusher() -> None:
    """asyncio 背景協程：leader-elected，每 _FLUSH_INTERVAL_S 跑一次觀測 flush 週期。

    由 main.py @app.on_event("startup") 以 asyncio.create_task 排程（fail-open，不阻斷
    啟動）。cancellation-aware：shutdown 時 CancelledError 乾淨退出。

    P5-SM soak 第二輪擴充：啟動先記 epoch 起點事件（epoch_rollover 搶救前一 epoch
    終值 + flusher_start），之後每輪 = comparator 投影（既有，byte-unchanged）+
    canary 投影（V129 'canary' row）+ 事件偵測（flag_change / canary_leader_start /
    canary_fail_streak / counter_regression → V137）。

    為什麼把 flush 放 executor：同步 PG I/O（psycopg2 阻塞）；放 loop.run_in_executor
    避免阻塞事件循環（對齊「啟動 <100ms / 不阻塞 await」紀律）。各步驟自身 fail-soft，
    executor 內例外已被吞，故 await 不會拋。
    """
    if not _acquire_flusher_leader_lock():
        return

    logger.info(
        "lease-divergence snapshot flusher started (interval=%ds) / "
        "lease 分歧計數器 PG 投影 flusher 已啟動",
        _FLUSH_INTERVAL_S,
    )
    loop = asyncio.get_event_loop()
    # epoch 起點事件（搶救前一 epoch 終值；fail-soft，失敗不阻斷 flush 循環）。
    try:
        await loop.run_in_executor(None, record_epoch_start_events_once)
    except Exception as exc:  # noqa: BLE001 — 雙保險
        logger.debug("epoch start events error (continuing): %s", exc)
    while True:
        try:
            await asyncio.sleep(_FLUSH_INTERVAL_S)
        except asyncio.CancelledError:
            logger.info(
                "lease-divergence snapshot flusher cancelled / lease 分歧 flusher 已取消"
            )
            return
        try:
            # 同步 PG I/O 丟 executor，不阻塞事件循環；週期內部 fail-soft 不拋。
            await loop.run_in_executor(None, flush_observability_cycle_once)
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
    "flush_canary_snapshot_once",
    "flush_observability_cycle_once",
    "record_epoch_start_events_once",
    "detect_and_record_soak_events_once",
    "divergence_snapshot_flusher",
]

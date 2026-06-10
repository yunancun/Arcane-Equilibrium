"""
Governance IPC Canary — 唯讀 IPC 管線曝險探針
（P5-SM-OPTION2 step-(i) soak 監測第二輪，E1-C）。

MODULE_NOTE:
    模塊用途：cutover 後 Python 控制面所有治理讀寫全騎在 Python→IPC→Rust 管線上，
    但該管線在生產環境 organic≈0 次被呼叫（shadow 默認 SHADOW_BYPASS 短路）。本
    canary 以 leader-elected asyncio task 週期（默認 120s ±10% jitter）打兩個**唯讀**
    dispatch arm 做結構驗證，把管線（event-loop dispatch / serde / socket auth /
    fail-closed timeout）的健康轉成可累計的 in-memory 計數器，由 flusher（E1-B）
    投影到 PG 供 `[82]` soak-window gate 讀取。

    probe 軸（PA 設計 §3.2；§2.4 鐵則 = 不做 Rust vs Python 雙邊比對，gate 軸是
    **結構有效性**非等價性）：
      - probe-1 `governance.is_authorized`：strict bool 即 ok；None（IPC 失敗 /
        畸形 / 超時）即 fail。**不**與 Python hub.is_authorized() 比對。
      - probe-2 `governance.get_status`：parse_get_status_response 結構驗證
        （必備鍵 + 型別；enum 字串不釘大小寫）。提前曝險 step-ii Python 投影的依賴。

    主要函數：
      - ``run_canary_tick``：單拍（probe-1 + probe-2 + 計數 + 連段/退頻記帳）；
        測試直驅入口。
      - ``governance_ipc_canary_loop``：asyncio 背景協程（kill-switch + leader +
        cadence + jitter），由 main.py startup 排程。
      - ``get_canary_counters() -> dict[str, int]``：PA 鎖定簽名的計數器 getter
        （flusher 讀此投影到 V129 'canary' row：total=attempts / matches=ok /
        divergences=fail）。

    引擎 fire 機率五條硬防護（PM 定案 `2026-06-10--p5sm_soak_cadence_decision.md`）：
      1. **single-flight + 2s timeout**：同一時刻最多 1 個 in-flight probe 對
         （``_CANARY_STATE["in_flight"]`` 守衛 + 協程內順序 await）；單 probe 以
         ``asyncio.wait_for`` 硬切 2s；timeout 記 fail 後**等下一拍，禁止立即重試**
         （retry storm 是唯一真實風險源）。
      2. **jitter ±10%**：每拍 sleep = interval × uniform(0.9, 1.1)（獨立 Random
         實例，不動全域 seed），避免與 03:17 residual cron 等定時任務鎖相。
      3. **fail-backoff 只降頻不加頻**：連敗 ≥10 → 拍距退到 max(配置值, 300s) +
         一條 WARN；恢復成功才回配置頻率。失敗路徑**永不**比配置值更快。
      4. **kill-switch 默認 OFF**：``OPENCLAW_SM_IPC_CANARY_ENABLED`` 嚴格 "1" 才跑
         （soak 期寫入 basic_system_services.env 持久，restart_all.sh 轉發）；每拍
         複查，OFF 即退出。
      5. **O(1) 唯讀**：只打 is_authorized / get_status 兩個讀 arm（Rust 端 µs 級
         快照讀，不觸發重算）；每拍 log DEBUG 級（WARN 僅限 ≥15min 連段與退頻事件）；
         leader-elected 單 prober（見下）。

    leader election（load-bearing 設計不變量）：**複用 flusher 的同一個 flock
    檔**（governance_divergence_flush._acquire_flusher_leader_lock；
    $OPENCLAW_DATA_DIR/lease_ipc_divergence_flusher.leader.lock）。為什麼必須同檔：
    4 個 uvicorn worker 是 4 個獨立進程，canary 計數器是 process-local 記憶體——
    若 canary 與 flusher 各用一把鎖，可能被選在**不同進程**，flusher 永遠只能讀到
    自己進程裡恆 0 的 canary 計數（silent 假死）。同一把 flock ⇒ 同一個 leader
    進程 ⇒ flusher 從同進程記憶體讀到真計數。flock 是進程內冪等的（fd 已持有即
    回 True），故 canary / flusher 兩個 task 的啟動順序無關緊要。

    E4 對抗壓測鉤子：``OPENCLAW_SM_CANARY_INTERVAL_SECS=1`` 可注入 1s 極端頻率
    （120× 設計頻率）驗證 tick SLA 不退步（per PM 決策「過殺餘量證明」）。

    依賴：
      - lease_ipc_schema（METHOD_IS_AUTHORIZED / METHOD_GET_STATUS + parsers）。
      - ipc_dispatch.one_shot_ipc_call（lazy import；生產 dispatcher，與 lease
        bridge 同一條 fail-closed one-shot 路徑）。
      - governance_divergence_flush._acquire_flusher_leader_lock（同鎖同 leader，
        見上）。

    硬邊界（鐵則，grep 可驗）：
      - **0 mutation**：本模組 0 個 acquire_lease / release_lease 方法引用
        （tests 以 source-grep + 剝註解雙軌驗證）；0 PG 寫入（PG 投影全在 flusher）；
        0 lease / SM / 風控狀態改動。worst case = canary 死 = 只少觀測數據。
      - **fail-soft 對權威路徑**：本協程任何例外不向 startup / 權威 lease 路徑
        傳播；fail-closed 對自身判定（畸形 payload 計 fail，絕不當健康）。
      - step-(iv) cleanup 連同 flusher 擴充 / V137 / `[82]` 一起退役。

singleton-registry：本模塊的 module-level 可變單例 ``_CANARY_COUNTERS`` /
    ``_CANARY_STATE`` / ``_CANARY_LOCK`` 登記於
    docs/architecture/singleton-registry.md §2.5.5（與 comparator sink 同
    step-(iv) 退役組）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import threading
import time
from typing import Any, Awaitable, Callable, Mapping, Optional

from .lease_ipc_schema import (
    METHOD_GET_STATUS,
    METHOD_IS_AUTHORIZED,
    parse_get_status_response,
    parse_is_authorized_response,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 配置常量 / env（PM 定案 2026-06-10--p5sm_soak_cadence_decision.md）
# ═══════════════════════════════════════════════════════════════════════════════

# kill-switch（防護 4）：嚴格 "1" 才啟用（對齊 OPENCLAW_LEASE_PYTHON_IPC_ENABLED
# 的嚴格等值慣例）。默認 OFF——canary 是 soak 期儀器，非常駐負載。
CANARY_ENABLED_ENV: str = "OPENCLAW_SM_IPC_CANARY_ENABLED"

# cadence env（PM 定案 120s；E4 可注入 1s 做 120× 過殺壓測）。
CANARY_INTERVAL_ENV: str = "OPENCLAW_SM_CANARY_INTERVAL_SECS"
DEFAULT_CANARY_INTERVAL_SECONDS: float = 120.0

# 單 probe 硬超時（防護 1）。比 lease bridge 默認 5s 更緊：canary 是觀測儀器，
# 慢回應對它就是失敗信號，不值得佔住 in-flight 槽等。
PROBE_TIMEOUT_SECONDS: float = 2.0

# jitter 幅度（防護 2）：±10%。
_JITTER_FRACTION: float = 0.10

# fail-backoff（防護 3）：連敗 ≥10 → 拍距退到 max(配置值, 300s)。
BACKOFF_CONSECUTIVE_FAILURES: int = 10
BACKOFF_INTERVAL_SECONDS: float = 300.0

# 失敗連段 WARN 閾值（S3 連段定義：≥15min）。連段以**時間**計（不以拍數計）——
# cadence 可配置（120s/300s/1s），拍數在不同 cadence 下對應不同牆鐘時長，S3 gate
# 的語義是牆鐘 15min。
FAIL_STREAK_WARN_SECONDS: float = 900.0

# 獨立隨機源（jitter 用）：不動全域 random seed（對齊 bootstrap seed per-caller
# 獨立慣例，避免影響任何研究代碼的可重現性）。
_JITTER_RNG = random.Random()

# monotonic 時鐘間接層：連段時長判定用。測試 patch 此名而非全域 time.monotonic
# （asyncio 事件循環內部依賴 time.monotonic，patch 全域會破壞 sleep/wait_for 排程）。
_monotonic = time.monotonic


# ═══════════════════════════════════════════════════════════════════════════════
# module-level 可變單例（singleton-registry §2.5.5）
# ═══════════════════════════════════════════════════════════════════════════════

_CANARY_LOCK = threading.Lock()

# 計數器（單調累加；flusher 經 get_canary_counters 讀後投影 V129 'canary' row）。
# attempts = 拍數（每拍 = probe-1 + probe-2 兩個 IPC 讀）；ok = 兩 probe 皆結構
# 有效的拍數；fail = 任一 probe 失敗的拍數；attempts == ok + fail 恆成立（V129
# CHECK total >= matches + divergences 天然滿足）。
# fail_streak_breaches = 跨 15min 失敗連段的累計次數（每個連段至多 +1；flusher
# 觀測到增量即寫 V137 'canary_fail_streak' 事件，供 [82] 判 S3 連段條件）。
_CANARY_COUNTERS: dict[str, int] = {
    "attempts": 0,
    "ok": 0,
    "fail": 0,
    "fail_streak_breaches": 0,
}

# 運行時狀態（非計數器；同鎖保護）。
#   last_ok_ts          — 最近成功拍的 epoch 秒（觀測用）。
#   consecutive_failures — 當前連敗拍數（退頻判定；成功即歸零）。
#   fail_streak_started_mono — 當前失敗連段起點（time.monotonic()；None=無連段）。
#       為什麼 monotonic：連段時長判定不可被系統時鐘跳變（NTP 校正）偽造或掩蓋。
#   streak_breach_recorded — 當前連段是否已計入 breaches（每連段至多 WARN+計數一次）。
#   in_backoff          — 是否處於退頻狀態（進入時 WARN 一次）。
#   in_flight           — single-flight 守衛（防護 1）：True 期間任何重入 tick
#       直接跳過不計數（雙排程 wiring bug 不可放大 IPC 負載）。
_CANARY_STATE: dict[str, Any] = {
    "last_ok_ts": None,
    "consecutive_failures": 0,
    "fail_streak_started_mono": None,
    "streak_breach_recorded": False,
    "in_backoff": False,
    "in_flight": False,
}


# ═══════════════════════════════════════════════════════════════════════════════
# 讀取 / 重置（getter 契約 PA 已鎖定簽名）
# ═══════════════════════════════════════════════════════════════════════════════

def is_canary_enabled() -> bool:
    """kill-switch（防護 4）：env 嚴格等於 "1" 才回 True（默認 OFF）。"""
    return os.environ.get(CANARY_ENABLED_ENV, "") == "1"


def get_canary_counters() -> dict[str, int]:
    """回傳 canary 計數器快照（PA 鎖定契約：``() -> dict[str, int]``）。

    flusher（E1-B）讀此投影 V129 'canary' row：total=attempts / matches=ok /
    divergences=fail；fail_streak_breaches 供 flusher 偵測連段事件。
    """
    with _CANARY_LOCK:
        return dict(_CANARY_COUNTERS)


def get_canary_runtime_state() -> dict[str, Any]:
    """回傳運行時狀態快照（測試 + 觀測；不含計數器）。"""
    with _CANARY_LOCK:
        return dict(_CANARY_STATE)


def reset_canary_state_for_tests() -> None:
    """清空計數器與運行時狀態（僅供測試隔離；勿於 production 呼叫）。"""
    with _CANARY_LOCK:
        for k in _CANARY_COUNTERS:
            _CANARY_COUNTERS[k] = 0
        _CANARY_STATE.update(
            last_ok_ts=None,
            consecutive_failures=0,
            fail_streak_started_mono=None,
            streak_breach_recorded=False,
            in_backoff=False,
            in_flight=False,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# cadence 解析
# ═══════════════════════════════════════════════════════════════════════════════

def _canary_interval_seconds() -> float:
    """讀 cadence env（每拍重讀，E4 1s 注入鉤子）；無效值回默認 120s。

    為什麼 fail-safe 回默認而非 fail-closed 停跑：cadence 配置錯不該讓 soak 觀測
    靜默消失（canary 死 = 少觀測數據 = [82] 會 FAIL）；回默認 120s 是 PM 定案的
    安全值。非正數 / 非數字 → 默認 + DEBUG log。
    """
    raw = os.environ.get(CANARY_INTERVAL_ENV, "")
    if not raw:
        return DEFAULT_CANARY_INTERVAL_SECONDS
    try:
        val = float(raw)
    except (TypeError, ValueError):
        logger.debug(
            "canary interval env 非數字（%r）→ 用默認 %.0fs",
            raw, DEFAULT_CANARY_INTERVAL_SECONDS,
        )
        return DEFAULT_CANARY_INTERVAL_SECONDS
    if val <= 0:
        logger.debug(
            "canary interval env 非正數（%r）→ 用默認 %.0fs",
            raw, DEFAULT_CANARY_INTERVAL_SECONDS,
        )
        return DEFAULT_CANARY_INTERVAL_SECONDS
    return val


def _effective_interval_seconds(*, base: Optional[float] = None) -> float:
    """當前有效拍距：退頻時 = max(配置值, 300s)，否則 = 配置值（防護 3）。

    不變量：失敗路徑**只降頻不加頻**——若 operator 配置值本就 > 300s（例如 600s），
    退頻不得把它「加速」到 300s，故取 max。
    """
    interval = _canary_interval_seconds() if base is None else base
    with _CANARY_LOCK:
        in_backoff = _CANARY_STATE["in_backoff"]
    if in_backoff:
        return max(interval, BACKOFF_INTERVAL_SECONDS)
    return interval


def _jittered(interval: float) -> float:
    """±10% jitter（防護 2）：避免與定時任務（03:17 cron 等）鎖相。"""
    return interval * _JITTER_RNG.uniform(1.0 - _JITTER_FRACTION, 1.0 + _JITTER_FRACTION)


# ═══════════════════════════════════════════════════════════════════════════════
# dispatcher（與 lease bridge 同 one-shot 生產路徑；測試可注入）
# ═══════════════════════════════════════════════════════════════════════════════

# 型別對齊 governance_lease_bridge.IPCDispatcher：(method, params, timeout) -> awaitable[dict]。
IPCDispatcher = Callable[..., Awaitable[Mapping[str, Any]]]


def _default_dispatcher() -> IPCDispatcher:
    """延遲匯入 one_shot_ipc_call（避免循環匯入；與 lease bridge 同生產 dispatcher）。"""
    from .ipc_dispatch import one_shot_ipc_call  # noqa: PLC0415

    async def _dispatch(method: str, params: Mapping[str, Any], timeout: float) -> Mapping[str, Any]:
        return await one_shot_ipc_call(
            method,
            params=dict(params),
            timeout=timeout,
            wrap_errors_as_http=False,   # canary 自行把例外計為 fail，不需 HTTP 包裝
            error_context="sm_ipc_canary",
        )

    return _dispatch


# ═══════════════════════════════════════════════════════════════════════════════
# probes（唯讀；結構驗證軸 — §2.4 鐵則：不做雙邊比對）
# ═══════════════════════════════════════════════════════════════════════════════

async def _probe_is_authorized(dispatch: IPCDispatcher) -> bool:
    """probe-1：governance.is_authorized 結構驗證（strict bool 即 ok）。

    為什麼任何例外都計 fail 而非上拋：canary 的失敗就是它要觀測的信號；上拋會殺
    協程 = 觀測面靜默消失（fail-soft 對權威路徑、fail-closed 對自身判定）。
    """
    try:
        raw = await asyncio.wait_for(
            dispatch(METHOD_IS_AUTHORIZED, {}, PROBE_TIMEOUT_SECONDS),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — IPC 失敗 / 超時 / 任意例外 = 一次 fail
        logger.debug("canary probe-1 is_authorized failed: %s", exc)
        return False
    if not isinstance(raw, Mapping):
        return False
    # 結構驗證 = strict bool（True/False 皆健康；授權與否不是 canary 的判定軸）。
    return parse_is_authorized_response(raw) is not None


async def _probe_get_status(dispatch: IPCDispatcher) -> bool:
    """probe-2：governance.get_status 結構驗證（必備鍵 + 型別；不釘 enum 大小寫）。"""
    try:
        raw = await asyncio.wait_for(
            dispatch(METHOD_GET_STATUS, {}, PROBE_TIMEOUT_SECONDS),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — 同 probe-1：失敗即信號，不上拋
        logger.debug("canary probe-2 get_status failed: %s", exc)
        return False
    if not isinstance(raw, Mapping):
        return False
    return parse_get_status_response(raw) is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 單拍（測試直驅入口）
# ═══════════════════════════════════════════════════════════════════════════════

async def run_canary_tick(dispatcher: Optional[IPCDispatcher] = None) -> Optional[bool]:
    """跑一拍（probe-1 + probe-2 + 計數 + 連段/退頻記帳）。

    Returns:
        ``True`` = 本拍 ok；``False`` = 本拍 fail；``None`` = single-flight 守衛
        跳過（已有 in-flight 拍，本次**不計數**——雙排程 wiring bug 不可放大 IPC
        負載，也不可污染成功率統計）。

    防護 1 落實：in_flight 守衛 + 兩 probe 順序 await（同拍內也不並發）+ 單 probe
    2s 硬超時；失敗**不在本拍內重試**，等 caller 的下一拍。
    """
    with _CANARY_LOCK:
        if _CANARY_STATE["in_flight"]:
            logger.warning(
                "canary tick skipped: probe already in-flight（single-flight 守衛；"
                "若持續出現代表 canary 被雙重排程，請查 main.py wiring）"
            )
            return None
        _CANARY_STATE["in_flight"] = True

    try:
        dispatch = dispatcher or _default_dispatcher()
        # 順序 await（非 gather）：同一時刻引擎只見 1 個 canary in-flight 請求。
        ok1 = await _probe_is_authorized(dispatch)
        ok2 = await _probe_get_status(dispatch)
        tick_ok = ok1 and ok2
        _record_tick_result(tick_ok)
        logger.debug(
            "canary tick: is_authorized=%s get_status=%s -> %s",
            ok1, ok2, "ok" if tick_ok else "fail",
        )
        return tick_ok
    finally:
        with _CANARY_LOCK:
            _CANARY_STATE["in_flight"] = False


def _record_tick_result(tick_ok: bool) -> None:
    """更新計數器 + 連段/退頻記帳（持鎖；純記憶體，無 I/O）。

    連段語義（S3）：以**牆鐘時長**判定（monotonic 起點），跨 FAIL_STREAK_WARN_SECONDS
    （15min）時 breaches +1 並發一條 WARN ``SM_IPC_CANARY_DOWN``（每連段至多一次；
    soak 收口可 grep）。成功拍清空連段並退出 backoff。
    """
    now_mono = _monotonic()
    warn_streak = False
    warn_backoff = False
    with _CANARY_LOCK:
        _CANARY_COUNTERS["attempts"] += 1
        if tick_ok:
            _CANARY_COUNTERS["ok"] += 1
            _CANARY_STATE["last_ok_ts"] = time.time()
            _CANARY_STATE["consecutive_failures"] = 0
            _CANARY_STATE["fail_streak_started_mono"] = None
            _CANARY_STATE["streak_breach_recorded"] = False
            if _CANARY_STATE["in_backoff"]:
                _CANARY_STATE["in_backoff"] = False
                logger.info("canary 恢復成功，退出 backoff（回配置頻率）")
        else:
            _CANARY_COUNTERS["fail"] += 1
            _CANARY_STATE["consecutive_failures"] += 1
            if _CANARY_STATE["fail_streak_started_mono"] is None:
                _CANARY_STATE["fail_streak_started_mono"] = now_mono
            # 連段跨 15min → breach 計數 +1（每連段至多一次）。
            elapsed = now_mono - _CANARY_STATE["fail_streak_started_mono"]
            if (
                elapsed >= FAIL_STREAK_WARN_SECONDS
                and not _CANARY_STATE["streak_breach_recorded"]
            ):
                _CANARY_COUNTERS["fail_streak_breaches"] += 1
                _CANARY_STATE["streak_breach_recorded"] = True
                warn_streak = True
            # 連敗 ≥10 → 進入 backoff（防護 3；進入時 WARN 一次）。
            if (
                _CANARY_STATE["consecutive_failures"] >= BACKOFF_CONSECUTIVE_FAILURES
                and not _CANARY_STATE["in_backoff"]
            ):
                _CANARY_STATE["in_backoff"] = True
                warn_backoff = True
        consecutive = _CANARY_STATE["consecutive_failures"]

    # WARN 在鎖外發（log I/O 不持鎖）。
    if warn_streak:
        logger.warning(
            "SM_IPC_CANARY_DOWN: canary 失敗連段已跨 %.0f 分鐘（連敗 %d 拍）— "
            "Python→IPC→Rust 管線可能不健康；[82] soak window 將標記本連段",
            FAIL_STREAK_WARN_SECONDS / 60.0, consecutive,
        )
    if warn_backoff:
        logger.warning(
            "canary 連敗 %d 拍 ≥ %d，退頻到 max(配置值, %.0fs)（防護 3：失敗路徑"
            "只降頻不加頻）",
            consecutive, BACKOFF_CONSECUTIVE_FAILURES, BACKOFF_INTERVAL_SECONDS,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 背景協程（main.py startup 排程）
# ═══════════════════════════════════════════════════════════════════════════════

def _acquire_canary_leadership() -> bool:
    """leader election：複用 flusher 的同一把 flock（load-bearing，見 MODULE_NOTE）。

    同一把鎖 ⇒ canary 與 flusher 必在同一進程 ⇒ flusher 能從同進程記憶體讀到
    canary 計數器。flock 進程內冪等（fd 已持有回 True），兩 task 啟動順序無關。
    """
    from .governance_divergence_flush import _acquire_flusher_leader_lock  # noqa: PLC0415

    return _acquire_flusher_leader_lock()


async def governance_ipc_canary_loop(dispatcher: Optional[IPCDispatcher] = None) -> None:
    """asyncio 背景協程：kill-switch + leader + cadence（jitter / backoff）+ 單拍。

    由 main.py @startup 以 asyncio.create_task 排程（fail-open，不阻斷啟動）。
    cancellation-aware：shutdown 時 CancelledError 乾淨退出。

    kill-switch 每拍複查：env 變 OFF（測試注入 / 進程內翻轉）即退出循環——kill-switch
    的語義是「立即可殺」，不是「下次 restart 才生效」。
    """
    if not is_canary_enabled():
        logger.info(
            "SM IPC canary disabled（%s != \"1\"，默認 OFF）— 不排程 probe / "
            "canary 默認休眠，soak 啟動時經 basic_system_services.env 開啟",
            CANARY_ENABLED_ENV,
        )
        return
    if not _acquire_canary_leadership():
        logger.info("SM IPC canary: non-leader worker，本進程不 probe")
        return

    logger.info(
        "SM IPC canary started (interval=%.0fs ±%.0f%% jitter, probe timeout=%.1fs, "
        "backoff=%d 連敗→%.0fs) / SM IPC canary 已啟動",
        _canary_interval_seconds(), _JITTER_FRACTION * 100,
        PROBE_TIMEOUT_SECONDS, BACKOFF_CONSECUTIVE_FAILURES, BACKOFF_INTERVAL_SECONDS,
    )
    while True:
        try:
            await asyncio.sleep(_jittered(_effective_interval_seconds()))
        except asyncio.CancelledError:
            logger.info("SM IPC canary cancelled / canary 已取消")
            return
        # kill-switch 每拍複查（OFF 即退出；防護 4）。
        if not is_canary_enabled():
            logger.info("SM IPC canary: kill-switch 轉 OFF，退出 probe 循環")
            return
        try:
            await run_canary_tick(dispatcher)
        except asyncio.CancelledError:
            logger.info("SM IPC canary cancelled mid-tick / canary 拍中取消")
            return
        except Exception as exc:  # noqa: BLE001 — 雙保險：任何拍級例外不殺協程
            logger.debug("canary loop iteration error (continuing): %s", exc)


__all__ = [
    "CANARY_ENABLED_ENV",
    "CANARY_INTERVAL_ENV",
    "DEFAULT_CANARY_INTERVAL_SECONDS",
    "PROBE_TIMEOUT_SECONDS",
    "BACKOFF_CONSECUTIVE_FAILURES",
    "BACKOFF_INTERVAL_SECONDS",
    "FAIL_STREAK_WARN_SECONDS",
    "is_canary_enabled",
    "get_canary_counters",
    "get_canary_runtime_state",
    "reset_canary_state_for_tests",
    "run_canary_tick",
    "governance_ipc_canary_loop",
]

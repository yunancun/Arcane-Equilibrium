from __future__ import annotations

"""
LG5-W3-FUP-1 — Live Candidate Review Consumer Scheduler
LG-5 Live Candidate 評估 consumer 排程器

MODULE_NOTE (EN):
  Polls ``learning.mlde_param_applications`` for pending live promotion
  candidates and invokes ``governance_hub_live_candidate_review.review_live_candidate(hub, cid)``
  on each. This wires LG-5 IMPL-2 consumer into a long-running scheduler so the
  RFC v2 §4 ``[42] live_candidate_eval_contract`` revoke trigger does not fire
  for ``unaudited_over_1h > 0``.

  Architecture / 架構：
    - Sibling of EdgeEstimatorScheduler (same lifecycle slot, separate file to
      keep edge_estimator_scheduler.py within §九 LOC budget).
    - Owns its own leader lock sentinel ``lg5_review_consumer.leader.lock``
      under $OPENCLAW_DATA_DIR — independent election so a crashed edge
      scheduler leader doesn't block consumer election.
    - daemon thread runs ``_run_cycle()`` every
      ``OPENCLAW_LG5_CONSUMER_CYCLE_SECS`` seconds (default 300s = 5min).
    - Per-cycle SQL fetch is capped by
      ``OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE`` (default 16) — matches
      ``mlde_demo_applier.max_recommendations`` so one producer cycle's
      output can be drained in one consumer cycle.
    - Each candidate evaluation is wrapped in try/except so a single failure
      does not abort the batch (per CLAUDE.md §二 #6 fail-closed-per-item).
    - Unauthorized state is **NOT** short-circuited at the wrapper level —
      ``review_live_candidate`` itself runs R6 hard-veto and emits a
      ``reject_hard_veto`` audit row when ``hub.is_authorized() == False``
      (governance_hub_live_candidate_review.py:1199-1252 / evaluate_r6).
      Hard-skipping here would defeat the [42] unaudited_over_1h drain
      contract — see ROUND-2 HIGH-1 fix history.

  Audit emission per RFC v2 §2.3:
    ``review_live_candidate`` itself emits an audit row per candidate (one of
    ``review_live_candidate`` / ``approve`` / ``reject`` / ``defer``); this
    wrapper does NOT duplicate audit emission. Wrapper-level INFO log per
    cycle records the aggregate ``{reviewed, approved, rejected, deferred,
    rejected_hard_veto}`` counts so operators can grep stdout for scheduler
    health.

  env var inventory / 環境變數清單：
    - OPENCLAW_LG5_CONSUMER_ENABLED      (default "1"; "0" disables thread spawn)
    - OPENCLAW_LG5_CONSUMER_CYCLE_SECS   (default 300.0)
    - OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE (default 16)
    - OPENCLAW_SCHEDULER_LEADER          (shared with edge scheduler; "0"
                                           forces non-leader for testing)

MODULE_NOTE (中):
  輪詢 ``learning.mlde_param_applications`` 中 pending live promotion
  candidates，逐一呼叫 ``review_live_candidate(hub, cid)``。將 LG-5 IMPL-2
  consumer 接入長期運行排程器，避免 RFC v2 §4 ``[42]
  live_candidate_eval_contract`` 在 ``unaudited_over_1h > 0`` 時觸發 revoke。

  架構：
    - 與 EdgeEstimatorScheduler 並列（同生命週期欄位，獨立檔避免
      edge_estimator_scheduler.py 撞 §九 LOC 警告線）。
    - 持有自己的 leader lock sentinel，與 edge scheduler 獨立選舉，
      避免一方掛掉拖累另一方。
    - daemon thread 每 OPENCLAW_LG5_CONSUMER_CYCLE_SECS（預設 300s）
      跑一次 ``_run_cycle()``。
    - 每 cycle SQL fetch 上限 OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE（預設 16）
      —— 對齊 mlde_demo_applier.max_recommendations，使單次 producer
      輸出可在單次 consumer cycle 排空。
    - 單一 candidate 評估以 try/except 包覆，單筆失敗不中斷整批。
    - 未授權狀態**不**在 wrapper 層 short-circuit ——
      ``review_live_candidate`` 內部會跑 R6 hard-veto，
      ``hub.is_authorized() == False`` 時 emit ``reject_hard_veto`` audit
      row（governance_hub_live_candidate_review.py:1199-1252 / evaluate_r6）。
      若 wrapper 在這裡 hard-skip 反而會破壞 [42] unaudited_over_1h drain
      契約 —— 見 ROUND-2 HIGH-1 修復歷史。

  Audit emission 由 review_live_candidate 自帶（RFC v2 §2.3），wrapper
  不重複；wrapper 只在 INFO log 記錄每 cycle 聚合統計
  （含 reject_hard_veto 計數）。

關聯 / Cross-ref:
    - Consumer impl: app/governance_hub_live_candidate_review.py
        (review_live_candidate / _fetch_pending_candidate_pool)
    - Producer:  program_code/ml_training/mlde_demo_applier.py
        (_insert_live_candidate writes the rows this consumer drains)
    - Healthcheck: docs/healthchecks/2026-05-02--lg5_health_checks.md
        ([42] unaudited_over_1h consumer drain monitor)
    - Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
        2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md §2.2 / §4
"""

import fcntl
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .db_pool import get_conn, put_conn

logger = logging.getLogger(__name__)

# Default cycle secs: 5min — more frequent than producer (~hourly) so newly
# inserted candidates do not wait long; well under the [42] 1h SLA.
# 預設 5min，比 producer (~hourly) 更頻繁，新 candidate 等待時間短，
# 遠低於 [42] 1h SLA。
DEFAULT_CYCLE_SECS = 300.0

# Default max per cycle: 16 — matches mlde_demo_applier.max_recommendations
# so a single producer flush can be drained in one consumer cycle.
# 預設每 cycle 上限 16，對齊 mlde_demo_applier.max_recommendations，
# 一輪 producer 輸出可在一輪 consumer cycle 排空。
DEFAULT_MAX_PER_CYCLE = 16


# ═══════════════════════════════════════════════════════════════════════════════
# DB helper / DB 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_pending_candidate_ids(limit: int) -> list[int]:
    """Fetch unaudited pending live promotion candidate IDs.
    取尚未 audit 的 pending live promotion candidate ID。

    Returns oldest-first so the longest-waiting candidates are reviewed first
    (mitigates [42] unaudited_over_1h backlog).
    依 ts ASC 排序，最舊先處理（緩解 [42] unaudited_over_1h 背壓）。

    fail-soft: any DB exception → empty list + warn log; consumer cycle no-op.
    fail-soft：任何 DB 例外 → 空 list + warn log；consumer cycle no-op。
    """
    conn = get_conn()
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM learning.mlde_param_applications AS c
                WHERE c.engine_mode = 'live'
                  AND c.status = 'candidate'
                  AND c.application_type = 'live_promotion_candidate'
                  AND c.decision_lease_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM learning.governance_audit_log AS a
                      WHERE a.candidate_id = c.id
                        AND a.event_type = 'review_live_candidate'
                  )
                ORDER BY c.ts ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [int(row[0]) for row in rows if row and row[0] is not None]
    except Exception as exc:  # noqa: BLE001 — fail-soft per docstring
        logger.warning(
            "lg5_consumer fetch_pending_candidate_ids failed (fail-soft): %s "
            "/ lg5_consumer 取 pending IDs 失敗（fail-soft）：%s",
            exc, exc,
        )
        return []
    finally:
        put_conn(conn)


# ═══════════════════════════════════════════════════════════════════════════════
# Leader election (sibling sentinel; independent of edge scheduler)
# Leader 選舉（獨立 sentinel，與 edge scheduler 解耦）
# ═══════════════════════════════════════════════════════════════════════════════

_LEADER_LOCK_FD: Optional[int] = None
_LEADER_LOCK_PATH: Optional[str] = None


def _leader_lock_path() -> Path:
    """Resolve consumer leader-election sentinel path under $OPENCLAW_DATA_DIR.
    計算 consumer leader 選舉 sentinel 路徑。

    Cross-platform: $OPENCLAW_DATA_DIR per CLAUDE.md §六 (Mac sets in ~/.zshrc;
    Linux falls back to /tmp/openclaw).
    跨平台：$OPENCLAW_DATA_DIR 見 CLAUDE.md §六（Mac 在 ~/.zshrc 設；
    Linux fallback /tmp/openclaw）。
    """
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "lg5_review_consumer.leader.lock"


def _acquire_leader_lock() -> bool:
    """Single-host leader election via fcntl.flock; True iff this process won.
    單機 leader 選舉（fcntl.flock）；本進程贏為 True。

    Mirror of edge_estimator_scheduler._acquire_leader_lock with separate
    sentinel — same uvicorn --workers 4 → only 1 worker runs the consumer.
    與 edge_estimator_scheduler 邏輯相同但使用獨立 sentinel —— 同 uvicorn
    --workers 4 仍只有 1 worker 跑 consumer。

    env opt-out: OPENCLAW_SCHEDULER_LEADER=0 → forced non-leader (shared with
    edge scheduler; any operator wishing to disable consumer specifically
    should use OPENCLAW_LG5_CONSUMER_ENABLED=0 instead).
    env opt-out：OPENCLAW_SCHEDULER_LEADER=0 → 強制非 leader（與 edge
    scheduler 共用；要單獨關 consumer 用 OPENCLAW_LG5_CONSUMER_ENABLED=0）。
    """
    global _LEADER_LOCK_FD, _LEADER_LOCK_PATH

    if _LEADER_LOCK_FD is not None:
        return True

    if os.environ.get("OPENCLAW_SCHEDULER_LEADER") == "0":
        logger.info(
            "Lg5ReviewConsumer[pid=%d]: OPENCLAW_SCHEDULER_LEADER=0, forced non-leader "
            "/ pid=%d：環境變數強制非 leader",
            os.getpid(), os.getpid(),
        )
        return False

    lock_path = _leader_lock_path()
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as mkdir_exc:
        logger.warning(
            "Lg5ReviewConsumer[pid=%d]: cannot mkdir parent for leader lock %s (%s) "
            "— non-leader / 無法建立 leader lock 父目錄 %s（%s），降級為非 leader",
            os.getpid(), lock_path, mkdir_exc, lock_path, mkdir_exc,
        )
        return False

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as open_exc:
        logger.warning(
            "Lg5ReviewConsumer[pid=%d]: cannot open leader lock %s (%s) — non-leader "
            "/ 無法開啟 leader lock %s（%s），非 leader",
            os.getpid(), lock_path, open_exc, lock_path, open_exc,
        )
        return False

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as lock_exc:
        os.close(fd)
        logger.info(
            "Lg5ReviewConsumer[pid=%d]: non-leader worker (lock held by another worker at %s; %s) "
            "/ 非 leader worker（鎖由另一 worker 持有於 %s；%s）",
            os.getpid(), lock_path, lock_exc, lock_path, lock_exc,
        )
        return False

    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
    except OSError:
        pass

    _LEADER_LOCK_FD = fd
    _LEADER_LOCK_PATH = str(lock_path)
    logger.info(
        "Lg5ReviewConsumer[pid=%d]: elected leader (lock=%s) / pid=%d 當選 leader（鎖=%s）",
        os.getpid(), lock_path, os.getpid(), lock_path,
    )
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# Consumer scheduler class / Consumer 排程器類
# ═══════════════════════════════════════════════════════════════════════════════

class Lg5ReviewConsumer:
    """LG-5 Live Candidate Review Consumer scheduler.
    LG-5 Live Candidate 評估 consumer 排程器。

    fail-open: any single candidate failure is logged and skipped; loop continues.
    fail-open：單一 candidate 失敗 log 後跳過，loop 繼續。
    """

    def __init__(
        self,
        *,
        cycle_secs: float = DEFAULT_CYCLE_SECS,
        max_per_cycle: int = DEFAULT_MAX_PER_CYCLE,
        hub_provider: Optional[Any] = None,
    ) -> None:
        """Construct consumer with cycle + cap config.
        以 cycle / cap config 建構 consumer。

        Args:
            cycle_secs: interval between cycles in seconds
                       (default 300s = 5min, override via env).
            max_per_cycle: per-cycle candidate cap
                          (default 16, matches producer max).
            hub_provider: optional callable returning the GovernanceHub instance.
                         Defaults to lazy import of paper_trading_wiring.GOV_HUB
                         to avoid circular import at module load.
                         若為 None，採用 lazy import paper_trading_wiring.GOV_HUB
                         避免模組載入時循環 import。
        """
        self._cycle_secs = cycle_secs
        self._max_per_cycle = max_per_cycle
        self._hub_provider = hub_provider
        # Thread-safe stats / 線程安全統計
        self._lock = threading.Lock()
        self._started = False
        self._runs = 0
        # ROUND-2 HIGH-1: removed _cycles_skipped_not_authorized — wrapper no
        # longer hard-skips on unauthorized; IMPL-2 handles via R6 hard veto.
        # Operators wishing to observe unauthorized cycles should look at
        # _total_rejected_hard_veto (verdict-derived) or grep
        # `governance_audit_log WHERE event_type='review_live_candidate'
        # AND verdict_reason='reject_hard_veto'`.
        # ROUND-2 HIGH-1：移除 _cycles_skipped_not_authorized —— wrapper 不再
        # hard-skip 未授權；IMPL-2 經 R6 hard veto 處理。
        # operator 觀察未授權 cycle 改看 _total_rejected_hard_veto（verdict 推導）
        # 或 grep `governance_audit_log WHERE event_type='review_live_candidate'
        # AND verdict_reason='reject_hard_veto'`。
        self._total_reviewed = 0
        self._total_approved = 0
        self._total_rejected = 0
        self._total_rejected_hard_veto = 0
        self._total_deferred = 0
        self._total_errors = 0
        self._last_run_ts: Optional[float] = None
        self._last_cycle_summary: dict[str, Any] = {}
        # SCHEDULER-SHUTDOWN-PRIMITIVE-1 pattern: event-based stop for clean
        # pytest teardown (mirrors EdgeEstimatorScheduler).
        # SHUTDOWN-PRIMITIVE-1 模式：事件式 stop，pytest teardown 乾淨 join
        # （鏡 EdgeEstimatorScheduler）。
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _resolve_hub(self) -> Optional[Any]:
        """Resolve hub via provider or lazy import. None if unavailable.
        透過 provider 或 lazy import 取得 hub；不可用則回 None。

        Lazy import path (default): import paper_trading_wiring inside the
        function so module load order does not require GOV_HUB to be ready
        at this module's import time.
        Lazy import 路徑（預設）：在函數內 import paper_trading_wiring，
        避免本模組 import 時就要求 GOV_HUB 已備妥。
        """
        if self._hub_provider is not None:
            try:
                return self._hub_provider() if callable(self._hub_provider) else self._hub_provider
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Lg5ReviewConsumer: hub_provider raised: %s "
                    "/ hub_provider 拋出例外：%s", exc, exc,
                )
                return None
        try:
            from .paper_trading_wiring import GOV_HUB  # noqa: PLC0415
            return GOV_HUB
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Lg5ReviewConsumer: cannot import GOV_HUB (%s); cycle will skip "
                "/ 無法 import GOV_HUB（%s），cycle 跳過", exc, exc,
            )
            return None

    def start(self) -> None:
        """Idempotent start; spawns daemon thread on first call.
        冪等啟動；首次呼叫 spawn daemon thread。"""
        with self._lock:
            if self._started:
                return
            self._started = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="lg5-review-consumer",
        )
        self._thread.start()
        logger.info(
            "Lg5ReviewConsumer started: cycle_secs=%.0f max_per_cycle=%d "
            "/ LG-5 consumer 排程器已啟動：cycle=%.0fs cap=%d",
            self._cycle_secs, self._max_per_cycle,
            self._cycle_secs, self._max_per_cycle,
        )

    def shutdown(self, join_timeout: float = 5.0) -> bool:
        """Graceful shutdown — signal stop + join thread within timeout.
        優雅關閉 —— signal stop 並在 timeout 內 join thread。

        Returns True if thread exited cleanly (or never running). Idempotent.
        thread 乾淨退出（或從未啟動）回 True。冪等。
        """
        self._stop_event.set()
        thread = self._thread
        if thread is None or not thread.is_alive():
            return True
        thread.join(timeout=join_timeout)
        clean = not thread.is_alive()
        if not clean:
            logger.warning(
                "Lg5ReviewConsumer.shutdown: thread did not exit within %.1fs "
                "/ consumer thread 未在 %.1fs 內退出", join_timeout, join_timeout,
            )
        return clean

    def trigger_now(self) -> dict[str, Any]:
        """Synchronous on-demand cycle (for IPC / route hot-trigger / tests).
        IPC / route 熱觸發 / 測試用：同步執行一次 cycle。"""
        return self._run_cycle(reason="manual_trigger")

    def status(self) -> dict[str, Any]:
        """Return current consumer stats (non-blocking).
        返回 consumer 統計（非阻塞）。"""
        with self._lock:
            return {
                "started": self._started,
                "runs": self._runs,
                # ROUND-2 HIGH-1: cycles_skipped_not_authorized removed.
                # See _total_rejected_hard_veto for unauthorized observability.
                # ROUND-2 HIGH-1：cycles_skipped_not_authorized 已移除。
                # 未授權觀察改看 total_rejected_hard_veto。
                "total_reviewed": self._total_reviewed,
                "total_approved": self._total_approved,
                "total_rejected": self._total_rejected,
                "total_rejected_hard_veto": self._total_rejected_hard_veto,
                "total_deferred": self._total_deferred,
                "total_errors": self._total_errors,
                "last_run_ts": self._last_run_ts,
                "cycle_secs": self._cycle_secs,
                "max_per_cycle": self._max_per_cycle,
                "last_cycle_summary": dict(self._last_cycle_summary),
            }

    def _loop(self) -> None:
        """Main daemon loop; mirrors EdgeEstimatorScheduler._loop pattern.
        主 daemon loop；複製 EdgeEstimatorScheduler._loop 模式。

        Warm-up 30s (shorter than edge scheduler's 60s — consumer is
        backlog-draining, not CPU-heavy estimation).
        預熱 30s（比 edge scheduler 的 60s 短，consumer 是排空背壓而非
        CPU 重負載估計）。
        """
        if self._stop_event.wait(timeout=30.0):
            return
        while not self._stop_event.is_set():
            try:
                self._run_cycle(reason="scheduled")
            except Exception as exc:  # noqa: BLE001 — fail-open daemon
                logger.warning(
                    "Lg5ReviewConsumer cycle raised (fail-open): %s "
                    "/ consumer cycle 拋出（fail-open）：%s", exc, exc,
                )
            if self._stop_event.wait(timeout=self._cycle_secs):
                return

    def _run_cycle(self, *, reason: str) -> dict[str, Any]:
        """Execute one review cycle: fetch pending IDs, review each, aggregate.
        執行一輪 review cycle：取 pending IDs、逐一 review、聚合統計。

        Returns aggregated summary dict for status / log / test introspection.
        返回聚合摘要 dict 供 status / log / 測試 introspect 使用。
        """
        t_start = time.time()
        hub = self._resolve_hub()
        if hub is None:
            summary = {"skipped": "hub_unavailable", "reason": reason}
            with self._lock:
                self._runs += 1
                self._last_run_ts = time.time()
                self._last_cycle_summary = summary
            logger.warning(
                "Lg5ReviewConsumer[%s]: hub unavailable, cycle skipped "
                "/ consumer[%s]：hub 不可用，cycle 跳過", reason, reason,
            )
            return summary

        # NOTE (ROUND-2 HIGH-1 fix):
        # We deliberately do NOT short-circuit on hub.is_authorized() == False
        # at this layer. ``review_live_candidate`` itself runs R6 hard-veto
        # via evaluate_r6(auth_effective=...) and emits a reject_hard_veto
        # audit row when authorization is missing
        # (governance_hub_live_candidate_review.py:1199-1252 / 1037-1047).
        # Hard-skipping here would bypass IMPL-2 audit emission entirely and
        # leave [42] unaudited_over_1h backlog growing — defeating the very
        # purpose of this consumer. Trust IMPL-2; this wrapper just dispatches.
        # 註（ROUND-2 HIGH-1 修復）：
        # 本層**不**短路 hub.is_authorized() == False。
        # ``review_live_candidate`` 內部會經 evaluate_r6(auth_effective=...)
        # R6 hard-veto，未授權時發出 reject_hard_veto audit row
        # （governance_hub_live_candidate_review.py:1199-1252 / 1037-1047）。
        # 若在 wrapper 層 hard-skip 反會繞過 IMPL-2 audit emission，讓 [42]
        # unaudited_over_1h backlog 持續累積 —— 與本 consumer 目的相悖。
        # 信任 IMPL-2；wrapper 純派發即可。

        # Fetch pending IDs (capped) — no hub lock held during DB read.
        # 取 pending IDs（capped）— DB read 期間不持 hub lock。
        candidate_ids = _fetch_pending_candidate_ids(self._max_per_cycle)
        reviewed = 0
        approved = 0
        rejected = 0
        rejected_hard_veto = 0  # Subset of rejected with reason==reject_hard_veto
        deferred = 0
        errors: list[dict[str, Any]] = []

        # Lazy import the consumer entry point — avoids loading the heavy
        # review module at this scheduler's import time + matches
        # edge_estimator_scheduler.py lazy-import idiom.
        # Lazy import consumer 入口 —— 避免本排程器 import 時即拉起重型
        # review 模組，並對齊 edge_estimator_scheduler.py 的 lazy-import 慣例。
        try:
            from .governance_hub_live_candidate_review import (  # noqa: PLC0415
                review_live_candidate,
            )
        except Exception as exc:  # noqa: BLE001
            summary = {"skipped": "review_module_unavailable", "error": str(exc), "reason": reason}
            with self._lock:
                self._runs += 1
                self._last_run_ts = time.time()
                self._last_cycle_summary = summary
            logger.warning(
                "Lg5ReviewConsumer[%s]: cannot import review_live_candidate (%s) "
                "/ consumer[%s]：無法 import review_live_candidate（%s）",
                reason, exc, reason, exc,
            )
            return summary

        for cid in candidate_ids:
            try:
                verdict = review_live_candidate(
                    hub,
                    candidate_id=cid,
                    decided_by="GovernanceHub.review_live_candidate.scheduler",
                )
                reviewed += 1
                # Verdict.decision is one of "approve" / "reject" / "defer"
                # per ReviewVerdict spec (§2.2). Defensive: unknown → defer.
                # Verdict.decision 為 approve / reject / defer 之一（§2.2）；
                # 防禦性處理：未知值計入 deferred。
                decision = getattr(verdict, "decision", "defer")
                reason_str = getattr(verdict, "reason", "") or ""
                if decision == "approve":
                    approved += 1
                elif decision == "reject":
                    rejected += 1
                    # Track unauthorized-as-reject_hard_veto subset so
                    # operators can grep stdout for "rejected_hard_veto>0"
                    # (replaces the deleted is_authorized() hard-skip metric).
                    # 追蹤未授權→reject_hard_veto 子集，operator 可 grep
                    # stdout 中 rejected_hard_veto>0（取代被刪的 is_authorized
                    # hard-skip 計數）。
                    if reason_str == "reject_hard_veto":
                        rejected_hard_veto += 1
                else:
                    deferred += 1
            except Exception as exc:  # noqa: BLE001 — per-candidate fail-open
                # Single failure does not abort batch — log + continue.
                # 單一 candidate 失敗不中斷批次 —— log 後繼續。
                # NIT-4: increment under lock with other totals (see lock
                # block below). Local count tracked here for batch summary.
                # NIT-4：與其他 totals 一起在 lock 內遞增（見下方 lock block）。
                # 本處只追加 errors list 供 batch summary 用。
                errors.append({"candidate_id": cid, "error_class": type(exc).__name__,
                               "error_msg": str(exc)})
                logger.warning(
                    "Lg5ReviewConsumer[%s]: candidate_id=%d review raised (%s); "
                    "continuing batch / consumer[%s]：candidate_id=%d review 拋出（%s）；繼續批次",
                    reason, cid, exc, reason, cid, exc,
                )

        duration_ms = int((time.time() - t_start) * 1000)
        summary = {
            "reason": reason,
            "candidates_fetched": len(candidate_ids),
            "reviewed": reviewed,
            "approved": approved,
            "rejected": rejected,
            "rejected_hard_veto": rejected_hard_veto,
            "deferred": deferred,
            "errors": errors,
            "duration_ms": duration_ms,
        }

        with self._lock:
            self._runs += 1
            self._last_run_ts = time.time()
            self._total_reviewed += reviewed
            self._total_approved += approved
            self._total_rejected += rejected
            self._total_rejected_hard_veto += rejected_hard_veto
            self._total_deferred += deferred
            # NIT-4: increment _total_errors under lock with other totals.
            # NIT-4：_total_errors 與其他 totals 一起在 lock 內遞增。
            self._total_errors += len(errors)
            self._last_cycle_summary = summary

        # INFO log per cycle for operator stdout grep / observability.
        # 每 cycle INFO log，operator stdout grep / observability 用。
        logger.info(
            "Lg5ReviewConsumer[%s]: fetched=%d reviewed=%d approved=%d rejected=%d "
            "(hard_veto=%d) deferred=%d errors=%d duration_ms=%d "
            "/ consumer[%s]：fetched=%d reviewed=%d approved=%d rejected=%d "
            "(hard_veto=%d) deferred=%d errors=%d duration_ms=%d",
            reason, len(candidate_ids), reviewed, approved, rejected,
            rejected_hard_veto, deferred, len(errors), duration_ms,
            reason, len(candidate_ids), reviewed, approved, rejected,
            rejected_hard_veto, deferred, len(errors), duration_ms,
        )
        return summary


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level singleton + start hook / 模組級單例 + 啟動鉤子
# ═══════════════════════════════════════════════════════════════════════════════

_consumer: Optional[Lg5ReviewConsumer] = None
_consumer_lock = threading.Lock()


def _config_from_env() -> tuple[float, int, bool]:
    """Read env-derived consumer config; fail-soft to defaults on bad values.
    從 env 讀 consumer config；值無效時 fail-soft 回預設。

    Returns:
        (cycle_secs, max_per_cycle, enabled)
    """
    enabled = os.environ.get("OPENCLAW_LG5_CONSUMER_ENABLED", "1") != "0"
    try:
        cycle_secs = float(os.environ.get("OPENCLAW_LG5_CONSUMER_CYCLE_SECS",
                                          str(DEFAULT_CYCLE_SECS)))
        if cycle_secs <= 0:
            raise ValueError("cycle_secs must be > 0")
    except ValueError as exc:
        logger.warning(
            "Lg5ReviewConsumer: invalid OPENCLAW_LG5_CONSUMER_CYCLE_SECS (%s); using default %.0f "
            "/ 無效 OPENCLAW_LG5_CONSUMER_CYCLE_SECS（%s），用預設 %.0f",
            exc, DEFAULT_CYCLE_SECS, exc, DEFAULT_CYCLE_SECS,
        )
        cycle_secs = DEFAULT_CYCLE_SECS
    try:
        max_per_cycle = int(os.environ.get("OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE",
                                           str(DEFAULT_MAX_PER_CYCLE)))
        if max_per_cycle <= 0:
            raise ValueError("max_per_cycle must be > 0")
    except ValueError as exc:
        logger.warning(
            "Lg5ReviewConsumer: invalid OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE (%s); using default %d "
            "/ 無效 OPENCLAW_LG5_CONSUMER_MAX_PER_CYCLE（%s），用預設 %d",
            exc, DEFAULT_MAX_PER_CYCLE, exc, DEFAULT_MAX_PER_CYCLE,
        )
        max_per_cycle = DEFAULT_MAX_PER_CYCLE
    return cycle_secs, max_per_cycle, enabled


def start_consumer_scheduler(
    *,
    cycle_secs: Optional[float] = None,
    max_per_cycle: Optional[int] = None,
    hub_provider: Optional[Any] = None,
) -> Optional[Lg5ReviewConsumer]:
    """Idempotent global start, gated by leader election + ENABLED env.
    冪等全域啟動，受 leader 選舉 + ENABLED env 把關。

    Returns the consumer instance if this process is leader and consumer is
    enabled; None otherwise. Mirrors edge_estimator_scheduler.start_scheduler
    semantics (callers can ignore None — non-leader workers do nothing).
    本進程為 leader 且 consumer enabled 時回傳 instance；否則 None。
    語意對齊 edge_estimator_scheduler.start_scheduler（呼叫端可忽略 None
    —— 非 leader worker 什麼都不做）。

    Args:
        cycle_secs: optional override (env wins if this is None).
        max_per_cycle: optional override (env wins if this is None).
        hub_provider: optional hub provider override (test seam).
    """
    global _consumer
    env_cycle, env_cap, enabled = _config_from_env()
    if not enabled:
        logger.info(
            "Lg5ReviewConsumer: OPENCLAW_LG5_CONSUMER_ENABLED=0 — start skipped "
            "/ consumer：env 已關閉，跳過啟動"
        )
        return None
    if _consumer is None:
        with _consumer_lock:
            if _consumer is None:
                if not _acquire_leader_lock():
                    return None
                _consumer = Lg5ReviewConsumer(
                    cycle_secs=cycle_secs if cycle_secs is not None else env_cycle,
                    max_per_cycle=max_per_cycle if max_per_cycle is not None else env_cap,
                    hub_provider=hub_provider,
                )
    _consumer.start()
    return _consumer


def get_consumer_scheduler() -> Optional[Lg5ReviewConsumer]:
    """Return current global consumer (None if not yet started).
    返回單例（尚未啟動回 None）。"""
    return _consumer


def _reset_for_tests() -> None:
    """Test-only: reset module globals + release leader lock fd.
    測試專用：重置模組全域 + 釋放 leader lock fd。

    Mirrors edge_estimator_scheduler._reset_for_tests semantics — gracefully
    shuts down running consumer before clearing the singleton so daemon
    threads do not leak across tests in the same pytest session.
    對齊 edge_estimator_scheduler._reset_for_tests —— 清單例前先優雅關閉
    running consumer，daemon thread 不跨測試洩漏。
    """
    global _consumer, _LEADER_LOCK_FD, _LEADER_LOCK_PATH
    if _consumer is not None:
        try:
            _consumer.shutdown(join_timeout=5.0)
        except Exception:
            pass
    _consumer = None
    if _LEADER_LOCK_FD is not None:
        try:
            fcntl.flock(_LEADER_LOCK_FD, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(_LEADER_LOCK_FD)
        except OSError:
            pass
        _LEADER_LOCK_FD = None
        _LEADER_LOCK_PATH = None

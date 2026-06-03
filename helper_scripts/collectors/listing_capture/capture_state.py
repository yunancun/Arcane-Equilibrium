#!/usr/bin/env python3
"""production listing capture-only collector — capture-window ledger（生命週期 + resume）。

MODULE_NOTE:
  模塊用途：管理 capture-window 生命週期 ledger（PA 設計 §3.4）——symbol 轉 Trading
    （或 PreLaunch 偵測）即進 window，記 captured_at + window_expiry；過期自動移除
    （上層 sync_subscriptions 隨之退訂）；quota 滿則拒收新 symbol（fail-closed）。
    restart-resume：daemon 啟動時從 PG 讀「最近 N 小時內有捕捉事件」的 symbol，
    依其最早事件時刻推算 window_expiry resume（REST + PG 是 SoT，無需持久化 in-memory
    state，G4）。
  主要類/函數：
    - ``CaptureWindow`` — 單 symbol 的 window（captured_at_ms / launch_time_ms / expiry_ms）。
    - ``CaptureStateLedger`` — in-memory ledger：mark_captured / active_window_symbols /
      expire_due / can_admit（quota）/ resume_from_rows。
  依賴：僅 Python 標準庫（dataclasses / typing）。clock 注入式（測試）。
  硬邊界（capture-only 旁路 + 防 first-detection deadlock）:
    - 零 import 生產模組、零 auth、零 order、零 DB（PG resume 由 pg_sink 餵 rows，本層
      只做純記憶體 ledger 邏輯，方便單測）。
    - **每個 window 必有過期**（expiry = captured_at + HOLD）：防 project_first_detection
      _deadlock_pattern「進得去出不來」永久佔用 bug。
    - **quota 是 fail-closed 上限**：滿了 can_admit() 回 False，不收新 symbol（等舊的
      過期釋放），避免單連接 topic 無上限膨脹。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional


@dataclass
class CaptureWindow:
    """單 symbol 的 capture window（point-in-time 記錄）。

    captured_at_ms：進 window 的時刻（首次 mark）。
    launch_time_ms：該 symbol 鎖定的 launchTime（capture_lag 基準；可能 None）。
    expiry_ms：window 過期時刻 = captured_at_ms + HOLD（過期自動退訂）。
    """

    symbol: str
    captured_at_ms: int
    launch_time_ms: Optional[int]
    expiry_ms: int


class CaptureStateLedger:
    """capture-window in-memory ledger（生命週期 + quota + resume）。

    為什麼 in-memory 而非持久化 daemon state：REST PreLaunch 集合 + PG 捕捉事件是
    SoT；daemon 重啟可從兩者完全重建 window（resume_from_rows），無需自己持久化
    （G4，避免 daemon 內部 state 與 SoT 漂移）。
    """

    def __init__(
        self,
        *,
        hold_hours: float,
        max_concurrent: int,
        clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._hold_ms = int(hold_hours * 60 * 60 * 1000)
        self._max_concurrent = max_concurrent
        self._clock_ms = clock_ms
        # symbol → CaptureWindow。
        self._windows: dict[str, CaptureWindow] = {}

    # ── 進 window ──

    def can_admit(self, symbol: str) -> bool:
        """是否可收新 symbol 進 capture window（quota fail-closed）。

        為什麼 fail-closed：quota 是單連接 topic 上限保護；滿了不收新 symbol（等舊的
        過期釋放），避免 listing 高峰期同時訂太多毒化面 / 超 Bybit 單連接 args 上限。
        已在 window 內的 symbol 永遠可（重複 mark 不增量）。
        """
        if symbol in self._windows:
            return True
        return len(self._windows) < self._max_concurrent

    def mark_captured(
        self, symbol: str, launch_time_ms: Optional[int], *, now_ms: Optional[int] = None
    ) -> bool:
        """把 symbol 標進 capture window（首次進場記 captured_at + expiry）。

        回傳 True=成功進場 / False=quota 滿被拒（fail-closed）。
        為什麼首次才記 captured_at：window 從「首次偵測/轉移」起算 HOLD，後續重複
        mark 只更新 launchTime（若先前 None 現在有值），不延長 window（防無限續）。
        """
        now = now_ms if now_ms is not None else self._clock_ms()
        existing = self._windows.get(symbol)
        if existing is not None:
            # 已在 window：只在 launchTime 由 None → 有值時更新（鎖 capture_lag 基準），
            # 不重設 captured_at / expiry（不延長 window）。
            if existing.launch_time_ms is None and launch_time_ms is not None:
                self._windows[symbol] = CaptureWindow(
                    symbol=symbol,
                    captured_at_ms=existing.captured_at_ms,
                    launch_time_ms=launch_time_ms,
                    expiry_ms=existing.expiry_ms,
                )
            return True
        if not self.can_admit(symbol):
            return False
        self._windows[symbol] = CaptureWindow(
            symbol=symbol,
            captured_at_ms=now,
            launch_time_ms=launch_time_ms,
            expiry_ms=now + self._hold_ms,
        )
        return True

    # ── 出 window ──

    def expire_due(self, *, now_ms: Optional[int] = None) -> list[str]:
        """移除所有過期 window，回傳被移除的 symbol 列表（供上層退訂）。

        為什麼必有此路徑：window 過期是「出口」；無出口 = first-detection deadlock
        （symbol 永久佔訂閱槽）。上層每輪 poll 後呼叫，過期者從 active 集合消失，
        sync_subscriptions 隨之退訂。
        """
        now = now_ms if now_ms is not None else self._clock_ms()
        expired = [s for s, w in self._windows.items() if w.expiry_ms <= now]
        for s in expired:
            del self._windows[s]
        return expired

    # ── 查詢 ──

    def active_window_symbols(self, *, now_ms: Optional[int] = None) -> set[str]:
        """當前仍在 capture window 內（未過期）的 symbol 集合。

        為什麼不在此移除過期：查詢應無副作用；過期移除由 expire_due 顯式驅動（讓上層
        能拿到「被移除清單」做退訂）。此處只回未過期者（過期者即使還在 dict 也不算 active）。
        """
        now = now_ms if now_ms is not None else self._clock_ms()
        return {s for s, w in self._windows.items() if w.expiry_ms > now}

    def launch_time_of(self, symbol: str) -> Optional[int]:
        """回傳某 symbol 鎖定的 launchTime（capture_lag 基準），未知回 None。"""
        w = self._windows.get(symbol)
        return w.launch_time_ms if w is not None else None

    def window_of(self, symbol: str) -> Optional[CaptureWindow]:
        return self._windows.get(symbol)

    def size(self) -> int:
        """當前 ledger 內 window 數（含尚未 expire_due 清掉的過期者）。"""
        return len(self._windows)

    # ── restart-resume（G4）──

    def resume_from_rows(
        self, rows: Iterable[dict[str, Any]], *, now_ms: Optional[int] = None
    ) -> list[str]:
        """從 PG 查詢結果重建 capture window（daemon 重啟 resume）。

        rows: 每筆 = {'symbol': str, 'earliest_event_ts_ms': int,
                      'launch_time_ms': Optional[int]}（pg_sink 提供）。
        window_expiry 從「該 symbol 最早捕捉事件時刻」+ HOLD 推算（不從 now 重起算），
        故 resume 不會把舊 symbol 的 window 無限續——若最早事件已超過 HOLD，該 symbol
        在第一次 expire_due 即被清掉（不訂閱）。

        為什麼用最早事件：window 語義 = 「從首次捕捉起 HOLD 小時」；PG 最早事件 ≈
        captured_at，據此重建保持與運行期一致的過期時刻。受 quota 限制（resume 也
        fail-closed：超 quota 的多餘 symbol 不收，由最早事件時刻排序保留最近的）。
        """
        now = now_ms if now_ms is not None else self._clock_ms()
        resumed: list[str] = []
        # 依最早事件時刻新→舊排序，quota 滿時優先保留較新的 listing（更可能仍在 window）。
        sorted_rows = sorted(
            (r for r in rows if r.get("symbol")),
            key=lambda r: int(r.get("earliest_event_ts_ms") or 0),
            reverse=True,
        )
        for r in sorted_rows:
            symbol = str(r["symbol"])
            earliest = int(r.get("earliest_event_ts_ms") or 0)
            expiry = earliest + self._hold_ms
            if expiry <= now:
                # 最早事件已超 HOLD：window 早該過期，不 resume（不訂閱殭屍 window）。
                continue
            if symbol in self._windows:
                continue
            if len(self._windows) >= self._max_concurrent:
                # quota 滿：不再收（已按新→舊排序，保留的是較新的）。
                break
            launch_raw = r.get("launch_time_ms")
            launch = int(launch_raw) if launch_raw not in (None, "") else None
            self._windows[symbol] = CaptureWindow(
                symbol=symbol,
                captured_at_ms=earliest,
                launch_time_ms=launch,
                expiry_ms=expiry,
            )
            resumed.append(symbol)
        return resumed


__all__ = [
    "CaptureWindow",
    "CaptureStateLedger",
]

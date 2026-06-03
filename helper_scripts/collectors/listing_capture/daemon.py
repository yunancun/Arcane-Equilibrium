#!/usr/bin/env python3
"""production listing capture-only collector — 常駐 daemon 組裝。

MODULE_NOTE:
  模塊用途：把 gate_b_rest（SoT 輪詢 + phase SM）、gate_b_ws（獨立 public WS 捕捉 +
    capture_lag + markout + poison 哨兵）、pg_sink（雙寫 + JSONL fallback）、
    capture_state（window 生命週期 + resume）組裝成一個常駐 daemon（PA 設計 §3.3）。
    主執行緒固定間隔 REST 輪詢 → 偵測 PreLaunch/transition → 更新 capture window →
    動態同步 WS 訂閱 → poison 監測 + forced reconnect；WS 背景執行緒收逐筆事件，經
    writer 路由進 pg_sink（雙寫 research + market.klines）。SIGTERM 乾淨收尾。
  主要類/函數：``ListingCaptureDaemon`` / ``run_daemon`` / ``main``。
  依賴：同 package 的 config/pg_sink/capture_state/healthcheck + research/gate_b_rest +
    research/gate_b_ws（reuse 純邏輯，不重抄）+ 標準庫（threading / signal）。WS 的
    websocket-client 由 gate_b_ws 延遲 import。
  硬邊界（capture-only 旁路）:
    - 絕不 import 任何生產交易模組（openclaw_engine / SymbolRegistry / governance_hub /
      intent_processor / decision_lease / production bybit_rest_client）。只 import 同
      package 模組 + research/gate_b_* 隔離探針 + pg_sink（research/klines additive）。
    - 零 order / 零 strategy intent / 零 IPC trading / 零 live / 零 execution_authority。
    - **本檔不在匯入時啟動任何連線或副作用**：只有 main()/run_daemon() 被顯式呼叫才
      連 WS、打 REST、連 PG。匯入本 module（import smoke / 隔離測試）零副作用。
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# reuse 探針三層所在目錄（research/）；本 package 目錄。兩者都加進 sys.path 後以模組名
# 匯入，維持「可當 script 直跑、亦可被測試匯入」且不 import 生產套件。
_THIS_DIR = Path(__file__).resolve().parent
_RESEARCH_DIR = _THIS_DIR.parents[1] / "research"
for _p in (str(_THIS_DIR), str(_RESEARCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config as collector_config  # noqa: E402
import gate_b_rest as rest  # noqa: E402
import gate_b_ws as ws  # noqa: E402
from capture_state import CaptureStateLedger  # noqa: E402
from healthcheck import build_healthcheck  # noqa: E402
from pg_sink import ListingPgSink  # noqa: E402


def _utc_dt_from_ms(event_ts_ms: int) -> datetime:
    """毫秒 → UTC datetime（PG timestamptz 寫入用）。"""
    return datetime.fromtimestamp(event_ts_ms / 1000.0, tz=timezone.utc)


class ListingCaptureDaemon:
    """常駐 listing capture daemon：REST 主迴圈 + WS 背景捕捉 + PG 雙寫 + 生命週期。"""

    def __init__(
        self,
        *,
        cfg: Optional[collector_config.ListingCollectorConfig] = None,
        pg_sink: Optional[ListingPgSink] = None,
        ledger: Optional[CaptureStateLedger] = None,
        rest_probe: Optional[Any] = None,
        ws_probe_factory: Optional[Any] = None,
        clock_ms: Any = lambda: int(time.time() * 1000),
    ) -> None:
        self._cfg = cfg or collector_config.current_collector_config()
        self._clock_ms = clock_ms
        self._collector_version = collector_config.COLLECTOR_VERSION
        # pg_sink：production 用真連線；測試注入 fake。
        self._sink = pg_sink or ListingPgSink(
            collector_version=self._collector_version,
            pg_write_max_attempts=self._cfg.pg_write_max_attempts,
            pg_batch_size=self._cfg.pg_batch_size,
        )
        # capture-window ledger（生命週期 + quota + resume）。
        self._ledger = ledger or CaptureStateLedger(
            hold_hours=self._cfg.capture_hold_hours,
            max_concurrent=self._cfg.max_concurrent_symbols,
            clock_ms=clock_ms,
        )
        # REST 層（gate_b_rest，reuse）。collector 自己消化 transition，不需 jsonl_writer。
        self._rest_probe = rest_probe or rest.GateBRestProbe(clock_ms=clock_ms)
        # WS probe factory（每次 forced reconnect 重建一個新 probe，避免殘留狀態）。
        self._ws_probe_factory = ws_probe_factory or self._default_ws_probe_factory
        self._ws_probe: Any = None

        self._stop = threading.Event()
        self._ws_thread: Optional[threading.Thread] = None
        # forced reconnect 節流：上次 reconnect 時刻。
        self._last_reconnect_ms = 0
        # 健康指標。
        self._started_at_ms = self._clock_ms()
        self._last_poll_ok_ms: Optional[int] = None
        # WS 連線旗標（_on_open 設 True，連線斷/重建設 False）。
        self._ws_connected = False

    # ── WS probe 建構 + writer 路由 ──

    def _default_ws_probe_factory(self) -> Any:
        """建一個 production WS probe：persist_control_ticks=False（G1）+ writer 路由到 PG。

        為什麼每次 reconnect 重建：forced reconnect 後需全新 WS 連線（舊連線可能被
        毒化）；重建 probe 一併清掉 in-memory subscribed/ring 狀態，由主迴圈重新訂閱
        當前 active window symbol。
        """
        writers = {
            "publictrade": self._on_ws_public_trade,
            "kline": self._on_ws_kline,
            "capture_lag": self._on_ws_capture_lag,
            # control / markout 不寫 PG（control=liveness only G1；markout=研究衍生，
            # 由逐筆 publicTrade 在 PG 端重算即可，不額外存）。
        }
        return ws.GateBWsProbe(
            jsonl_writers=writers,
            persist_control_ticks=self._cfg.persist_control_ticks,
        )

    def _on_ws_public_trade(self, row: dict[str, Any]) -> None:
        """WS 逐筆 publicTrade → research.listing_capture_events（public_trade 事件）。"""
        event_ts_ms = int(row.get("event_ts_exchange_ms") or 0)
        self._sink.write_research_events([{
            "event_ts_exchange": _utc_dt_from_ms(event_ts_ms),
            "symbol": row.get("symbol"),
            "event_kind": "public_trade",
            "trade_id": row.get("trade_id"),
            "launch_time_ms": self._ledger.launch_time_of(str(row.get("symbol") or "")),
            "price": row.get("price"),
            "side": row.get("side"),
            "size": row.get("size"),
            "ingest_ts_local_ms": row.get("ingest_ts_local_ms"),
            "event_ts_exchange_ms": event_ts_ms,
            "ingest_minus_event_ms": row.get("ingest_minus_event_ms"),
        }])

    def _on_ws_kline(self, row: dict[str, Any]) -> None:
        """WS 1m kline → research（kline_1m 事件）+ confirm bar 雙寫 market.klines。"""
        event_ts_ms = int(row.get("event_ts_exchange_ms") or 0)
        symbol = str(row.get("symbol") or "")
        confirm = bool(row.get("confirm"))
        # research 表記每個 kline（含未 confirm，完整捕捉管線）。
        self._sink.write_research_events([{
            "event_ts_exchange": _utc_dt_from_ms(event_ts_ms),
            "symbol": symbol,
            "event_kind": "kline_1m",
            "launch_time_ms": self._ledger.launch_time_of(symbol),
            "price": row.get("close"),
            "kline_open": row.get("open"),
            "kline_high": row.get("high"),
            "kline_low": row.get("low"),
            "kline_close": row.get("close"),
            "kline_volume": row.get("volume"),
            "kline_confirm": confirm,
            "ingest_ts_local_ms": row.get("ingest_ts_local_ms"),
            "event_ts_exchange_ms": event_ts_ms,
            "ingest_minus_event_ms": row.get("ingest_minus_event_ms"),
        }])
        # 僅 confirm bar 雙寫 market.klines（與 engine 同 schema；未確認 bar 不入主表，
        # 避免污染下游以 confirm bar 為前提的工具鏈）。
        if confirm:
            close_ts_ms = event_ts_ms + 60_000  # 1m bar：start + 60s
            self._sink.write_klines([{
                "ts": _utc_dt_from_ms(event_ts_ms),
                "open_ts_ms": event_ts_ms,
                "close_ts_ms": close_ts_ms,
                "symbol": symbol,
                "timeframe": "1m",
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "turnover": None,  # WS kline.1 不帶 turnover；留 NULL 不臆造
                "tick_count": None,
            }])

    def _on_ws_capture_lag(self, row: dict[str, Any]) -> None:
        """WS capture_lag → research（capture_lag 事件）。"""
        # capture_lag 事件以「首筆成交 event_ts」為排序鍵（leak-free）。
        event_ts_ms = int(row.get("first_trade_event_ts_ms") or 0)
        ingest_ms = int(row.get("first_trade_ingest_ts_local_ms") or 0)
        self._sink.write_research_events([{
            "event_ts_exchange": _utc_dt_from_ms(event_ts_ms),
            "symbol": row.get("symbol"),
            "event_kind": "capture_lag",
            "launch_time_ms": row.get("launch_time_ms"),
            "capture_lag_ms": row.get("capture_lag_ms"),
            "capture_verdict": row.get("verdict"),
            "ingest_ts_local_ms": ingest_ms,
            "event_ts_exchange_ms": event_ts_ms,
            "ingest_minus_event_ms": ingest_ms - event_ts_ms,
        }])

    # ── phase transition → research（主迴圈呼叫）──

    def _write_phase_transition(self, t: Any, cur_auction_phase: Optional[str]) -> None:
        detected_ms = int(getattr(t, "detected_ingest_ts_ms", 0) or 0)
        self._sink.write_research_events([{
            # phase transition 無交易所事件 ts，用偵測時刻當排序鍵（明確標記為偵測，
            # 非交易所事件——provenance ingest==event 表示這是本地偵測事件）。
            "event_ts_exchange": _utc_dt_from_ms(detected_ms),
            "symbol": t.symbol,
            "event_kind": "phase_transition",
            "launch_time_ms": getattr(t, "launch_time_ms", None),
            "prev_status": getattr(t, "prev_status", None),
            "new_status": getattr(t, "new_status", None),
            "cur_auction_phase": cur_auction_phase,
            "ingest_ts_local_ms": detected_ms,
            "event_ts_exchange_ms": detected_ms,
            "ingest_minus_event_ms": 0,
        }])

    # ── 主迴圈 ──

    def run(self) -> int:
        """常駐執行：resume → 啟 WS 背景 thread → REST 主迴圈 → SIGTERM 乾淨收尾。"""
        self._install_signal_handlers()
        self._resume_from_pg()
        self._start_ws()
        try:
            while not self._stop.is_set():
                self._poll_cycle()
                # 等到下一輪或被 stop 喚醒（取較小者）。
                self._stop.wait(timeout=self._cfg.poll_interval_seconds)
        finally:
            self._shutdown()
        return 0

    def _poll_cycle(self) -> None:
        """單輪：REST poll → 更新 window → 同步訂閱 → poison 監測 forced reconnect。"""
        try:
            phases, transitions = self._rest_probe.poll_once()
        except rest.GateBRestError as exc:
            # REST 失敗：skip cycle，下輪重試（fail-closed，不無限重試本輪）。
            import logging
            logging.getLogger(__name__).warning("listing_capture REST poll failed: %s", exc)
            return
        self._last_poll_ok_ms = self._clock_ms()

        # symbol → cur_auction_phase（供 phase_transition 記錄相位時間線）。
        phase_by_symbol = {p.symbol: p.cur_auction_phase for p in phases}

        # PreLaunch 候選進 window（quota fail-closed）。
        candidates = self._rest_probe.state.prelaunch_symbols()
        for sym in candidates:
            launch = self._rest_probe.state.launch_time_of(sym)
            admitted = self._ledger.mark_captured(sym, launch)
            if admitted and self._ws_probe is not None:
                self._ws_probe.set_launch_time(sym, launch)

        # 轉 Trading 的 transition：續留 window（延長捕捉）+ 寫 phase_transition + 餵 launchTime。
        for t in transitions:
            self._ledger.mark_captured(t.symbol, getattr(t, "launch_time_ms", None))
            if self._ws_probe is not None:
                self._ws_probe.set_launch_time(t.symbol, getattr(t, "launch_time_ms", None))
            self._write_phase_transition(t, phase_by_symbol.get(t.symbol))

        # 過期 window 出場（防 first-detection deadlock）。
        self._ledger.expire_due()

        # 訂閱集 = 仍在 window 內的 symbol（PreLaunch 候選 + 未過期已轉 Trading）。
        active = self._ledger.active_window_symbols()
        if self._ws_probe is not None:
            self._ws_probe.sync_subscriptions(active)

        # poison 監測 → forced reconnect（PA 設計 §3.1）。
        self._maybe_forced_reconnect(active)

    # ── WS 生命週期 + poison forced reconnect ──

    def _start_ws(self) -> None:
        """建 WS probe + 啟背景 thread 跑 event loop。"""
        self._ws_probe = self._ws_probe_factory()
        # 包一層 on_open hook：用 control_liveness 的 tick 心跳間接判斷連上；這裡用
        # 一個輕量旗標——connect 後標記 connected（真實斷線由 control stale 偵測）。
        self._ws_connected = True
        self._ws_thread = threading.Thread(
            target=self._run_ws_loop, name="listing_capture_ws", daemon=True
        )
        self._ws_thread.start()

    def _run_ws_loop(self) -> None:
        probe = self._ws_probe
        if probe is None:
            return
        try:
            probe.connect()
            probe.run_forever()
        except Exception as exc:  # noqa: BLE001 - WS thread 錯誤記錄但不殺主迴圈
            import logging
            logging.getLogger(__name__).warning("listing_capture WS loop error: %s", exc)
        finally:
            self._ws_connected = False

    def _maybe_forced_reconnect(self, active: set[str]) -> None:
        """control 哨兵疑似毒化 → 主動重建 WS 連線並重訂閱 active window symbol。

        為什麼：Bybit public WS handler-not-found 會靜默毒化整條連線（2026-04-05 教訓）；
        control（BTCUSDT）哨兵 stale 即疑似毒化。forced reconnect 是縱深防護（QC/BB
        Gate-B 建議）。節流（reconnect_min_interval_ms）防 thrash。
        """
        probe = self._ws_probe
        if probe is None:
            return
        liveness = probe.control_liveness()
        if not liveness.get("poisoned_suspect"):
            return
        # control tick_count==0 在剛啟動時也會觸發 poisoned_suspect（還沒收到首筆 BTC
        # tick）；用「啟動後超過 stale 閾值才算真 poison」避免啟動瞬間誤判。
        stale_ms = liveness.get("control_stale_ms")
        tick_count = int(liveness.get("control_tick_count") or 0)
        if tick_count == 0 and (self._clock_ms() - self._started_at_ms) < self._cfg.control_stale_reconnect_ms:
            return  # 啟動暖機期，尚未收到首筆 control，不算毒化
        if stale_ms is not None and stale_ms < self._cfg.control_stale_reconnect_ms:
            return  # 有 tick 且未 stale 到閾值
        now = self._clock_ms()
        if now - self._last_reconnect_ms < self._cfg.reconnect_min_interval_ms:
            return  # 節流：兩次 reconnect 間隔不足
        self._last_reconnect_ms = now
        import logging
        logging.getLogger(__name__).warning(
            "listing_capture control sentinel poisoned_suspect (stale_ms=%s tick=%s); forcing WS reconnect",
            stale_ms, tick_count,
        )
        self._reconnect_ws(active)

    def _reconnect_ws(self, active: set[str]) -> None:
        """關閉舊 WS、起新 WS、重訂閱 active window symbol。"""
        old = self._ws_probe
        if old is not None:
            try:
                if old._ws is not None:  # noqa: SLF001 - 受控存取：關閉底層連線觸發 run_forever 退出
                    old._ws.close()
            except Exception:  # noqa: BLE001
                pass
        # join 舊 thread（run_forever 隨連線關閉退出）。
        if self._ws_thread is not None:
            self._ws_thread.join(timeout=5.0)
        # 重建並重訂閱。
        self._start_ws()
        if self._ws_probe is not None:
            for sym in active:
                self._ws_probe.set_launch_time(sym, self._ledger.launch_time_of(sym))
            self._ws_probe.sync_subscriptions(active)

    # ── restart-resume（G4）──

    def _resume_from_pg(self) -> None:
        """daemon 啟動時從 PG 讀 window 內 symbol resume（REST + PG 是 SoT）。"""
        try:
            rows = self._sink.query_resume_symbols(lookback_hours=self._cfg.resume_lookback_hours)
        except Exception as exc:  # noqa: BLE001 - resume 失敗退化為 REST-only，不中斷啟動
            import logging
            logging.getLogger(__name__).warning("listing_capture resume query error: %s", exc)
            return
        resumed = self._ledger.resume_from_rows(rows)
        if resumed:
            import logging
            logging.getLogger(__name__).info(
                "listing_capture resumed %s capture window(s) from PG: %s",
                len(resumed), sorted(resumed),
            )

    # ── shutdown ──

    def _install_signal_handlers(self) -> None:
        """SIGTERM / SIGINT → set stop event（systemd stop / Ctrl-C 乾淨收尾）。

        為什麼：systemd Restart=always 下 stop 走 SIGTERM；daemon 需乾淨關 WS + flush
        PG，避免半成型 state。signal handler 只 set event，真正收尾在 run() finally。
        """
        def _handler(signum: int, _frame: Any) -> None:
            import logging
            logging.getLogger(__name__).info("listing_capture received signal %s; stopping", signum)
            self._stop.set()

        try:
            signal.signal(signal.SIGTERM, _handler)
            signal.signal(signal.SIGINT, _handler)
        except ValueError:
            # 非主執行緒無法裝 handler（如測試在 thread 內跑）；忽略，由 stop event 控制。
            pass

    def _shutdown(self) -> None:
        """乾淨收尾：關 WS → join thread → 關 PG 連線。"""
        self._stop.set()
        probe = self._ws_probe
        if probe is not None:
            try:
                if probe._ws is not None:  # noqa: SLF001
                    probe._ws.close()
            except Exception:  # noqa: BLE001
                pass
        if self._ws_thread is not None:
            self._ws_thread.join(timeout=5.0)
        self._sink.close()

    # ── healthcheck 快照 ──

    def healthcheck(self) -> dict[str, Any]:
        liveness = (
            self._ws_probe.control_liveness()
            if self._ws_probe is not None
            else {"poisoned_suspect": False, "control_tick_count": 0}
        )
        return build_healthcheck(
            started_at_ms=self._started_at_ms,
            last_poll_ok_ms=self._last_poll_ok_ms,
            ws_connected=self._ws_connected,
            control_liveness=liveness,
            active_window_count=len(self._ledger.active_window_symbols()),
            pg_stats=self._sink.stats(),
            clock_ms=self._clock_ms,
        )


def run_daemon() -> int:
    """建立並執行常駐 daemon（production 用真連線）。"""
    daemon = ListingCaptureDaemon()
    return daemon.run()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "production listing capture-only collector daemon — standalone public WS "
            "+ REST instruments-info, dual-write market.klines + research.listing_"
            "capture_events. Zero auth/order/intent/IPC/live. systemd Restart=always."
        )
    )
    parser.add_argument(
        "--smoke-seconds",
        type=float,
        default=None,
        help="限時 smoke 模式：跑 N 秒後乾淨停（DoD #9 管線就緒驗證；不指定則常駐）。",
    )
    args = parser.parse_args(argv)

    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    daemon = ListingCaptureDaemon()
    if args.smoke_seconds is not None:
        # smoke：背景跑，到時 set stop。
        def _smoke_stopper() -> None:
            time.sleep(float(args.smoke_seconds))
            daemon._stop.set()  # noqa: SLF001 - smoke 限時停

        threading.Thread(target=_smoke_stopper, name="smoke_stopper", daemon=True).start()
    return daemon.run()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Gate-B 隔離探針 — 獨立 public WS 連線 + 動態訂閱 + capture_lag + markout ring。

MODULE_NOTE:
  模塊用途：Gate-B isolated listing-capture 探針的「捕捉管線」層。用 websocket-client
    開一條 **獨立** public WS 連線（``wss://stream.bybit.com/v5/public/linear``），
    只在某 symbol 進入 PreLaunch 候選時動態訂閱 ``kline.1.{sym}`` + ``publicTrade.{sym}``，
    同時固定訂閱 BTC control topic 作為 liveness/unpoisoned 哨兵。把每筆 kline /
    publicTrade 落地 JSONL，量測 capture_lag（first publicTrade event_ts − launchTime），
    並維護 in-memory mid-price ring buffer 以回填 +30/+60/+300s markout。
  主要類/函數：
    - ``MidPriceRing`` — 每 symbol 的 (event_ts, mid) 環形緩衝，供 markout 回填。
    - ``GateBWsProbe`` — WS 連線管理 / 動態 sub/unsub / 訊息分派 / capture_lag /
      markout / BTC control unpoisoned 判定。
  依賴：``websocket-client``（Linux runtime 已驗可用；Mac dev 無此套件，故 import
    延遲到實際連線時才發生，import 本 module 不需要它）+ Python 標準庫。
  硬邊界（R-0 隔離紅線）：
    - 絕不 import openclaw_engine / SymbolRegistry / KlineManager / governance_hub /
      production bybit_rest_client / ws_client / scanner / strategy / intent /
      decision_lease。本連線與生產 WS 完全隔離，自帶 URL / 訂閱列表 / 重連策略。
    - 零 auth、零 order、零 DB write。只訂 public topic。
    - 為什麼只訂 kline.1 + publicTrade（非生產的 7/symbol 默認集）：Gate-B 只需
      「首筆成交時刻」與「分鐘 K」就能量 capture_lag 與 markout；多訂 topic 只增加
      poison 面與頻寬，無助於 Gate-B 結論。
    - **WS poison 防護（2026-04-05 教訓）**：Bybit public WS 對不存在的 topic 回
      ``handler not found`` 並會**靜默停掉同連線上所有其他訂閱**（零 tick 但心跳
      正常，極難排查）。故本探針把 BTC ``publicTrade.BTCUSDT`` 設為 control 哨兵：
      只要它持續有 tick，即證明連線未被某個壞訂閱毒化。
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── 隔離常量（自帶 URL / topic，不從生產 ws_client 取） ──
_BYBIT_PUBLIC_WS_URL = "wss://stream.bybit.com/v5/public/linear"
# BTC publicTrade 作為 liveness/unpoisoned 哨兵：BTC 永遠高頻成交，只要它持續
# 有 tick 就證明連線健康且未被壞訂閱毒化。
_CONTROL_SYMBOL = "BTCUSDT"
_CONTROL_TOPIC = f"publicTrade.{_CONTROL_SYMBOL}"
# Bybit 訂閱分批上限：每則 subscribe 訊息最多 10 個 topic。
_MAX_TOPICS_PER_MSG = 10
# capture_lag PASS 閾值（毫秒）：首筆成交距 launchTime ≤ 5min 視為 PASS_CAPTURE。
_CAPTURE_LAG_PASS_MS = 5 * 60 * 1000
# control 哨兵多久沒 tick 視為可能被毒化（毫秒）。
_CONTROL_STALE_MS = 60 * 1000
# markout 回填 horizon（秒）。
_MARKOUT_HORIZONS_S = (30, 60, 300)
# mid ring 每 symbol 最多保留多少筆（足以覆蓋 +300s 視窗的高頻 tick）。
_RING_MAXLEN = 20_000


@dataclass
class MidPriceRing:
    """單 symbol 的 (event_ts_ms, mid) 環形緩衝，供 markout 回填。

    為什麼用 deque(maxlen)：探針短窗運行，記憶體有限；只需保留足以覆蓋最長
    markout horizon（+300s）的近期 mid，舊的自動淘汰。所有時間以 exchange
    event_ts 為準（leak-free，不用本地 ingest 時刻排序）。
    """

    points: deque = field(default_factory=lambda: deque(maxlen=_RING_MAXLEN))

    def push(self, event_ts_ms: int, mid: float) -> None:
        self.points.append((event_ts_ms, mid))

    def mid_at_or_after(self, target_ts_ms: int) -> Optional[tuple[int, float]]:
        """回傳 event_ts ≥ target 的第一筆 (ts, mid)；沒有則 None（尚未到該時點）。

        為什麼取「≥ target 的第一筆」：markout 是「trigger 後 +Ns 的價格」，用第一
        個落在或超過目標時刻的成交價近似，缺資料（窗口未填滿）回 None 不臆造。
        """
        best: Optional[tuple[int, float]] = None
        for ts, mid in self.points:
            if ts >= target_ts_ms:
                best = (ts, mid)
                break
        return best


@dataclass
class _PendingMarkout:
    """一個待回填的 markout 任務（trigger 時建立，到點後回填各 horizon）。"""

    symbol: str
    trigger_event_ts_ms: int
    mid_at_trigger: float
    # horizon 秒 → 是否已回填。
    filled: dict[int, bool] = field(default_factory=dict)


class GateBWsProbe:
    """獨立 public WS 連線管理：動態 sub/unsub + capture_lag + markout + control 哨兵。

    設計成可注入 ws factory 與 clock，方便在不真連 WS 的情況下對訊息分派、
    capture_lag、markout、control unpoisoned 判定做單元測試。
    """

    def __init__(
        self,
        *,
        jsonl_writers: Optional[dict[str, Callable[[dict[str, Any]], None]]] = None,
        ws_app_factory: Optional[Callable[..., Any]] = None,
        clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
        ws_url: str = _BYBIT_PUBLIC_WS_URL,
        persist_control_ticks: bool = True,
    ) -> None:
        # jsonl_writers: 各 artifact 檔的寫入回呼（kline / publictrade / control /
        # capture_lag / markout）。注入式，方便測試與由 artifact 層接管落地。
        self._writers = jsonl_writers or {}
        # persist_control_ticks（G1 firehose 殺手）：是否把每筆 BTC control 哨兵 tick
        # 落盤（_emit("control", control_trade)）。預設 True 保探針行為不變（向後相容，
        # 32 既有測試仍綠）；production collector 傳 False → control tick 只更新
        # in-memory liveness counter（_control_last_seen_ms/_control_tick_count），不
        # 落盤，避免探針觀測到的 346MB/43h firehose（PA 設計 §3.1 / G1）。
        # 為什麼只關 control 落盤不影響其他：control symbol（BTCUSDT）在 _handle_public
        # _trade 早 continue，不進 capture_lag/markout/候選 publictrade 路徑；liveness
        # counter 在 _emit 之前已更新，故 poison 哨兵 control_liveness() 完全不受影響。
        self._persist_control_ticks = persist_control_ticks
        self._ws_app_factory = ws_app_factory
        self._clock_ms = clock_ms
        self._ws_url = ws_url
        self._ws: Any = None
        self._lock = threading.Lock()

        # symbol → 是否已訂閱（避免重複 subscribe）。
        self._subscribed: set[str] = set()
        # symbol → 已記到的首筆 publicTrade event_ts（capture_lag 用）。
        self._first_trade_ts: dict[str, int] = {}
        # symbol → launchTime（由 REST 層餵入，capture_lag 基準）。
        self._launch_time: dict[str, Optional[int]] = {}
        # symbol → mid ring。
        self._rings: dict[str, MidPriceRing] = {}
        # 待回填 markout 任務。
        self._pending_markouts: list[_PendingMarkout] = []
        # control 哨兵：最後一次收到 BTC control tick 的本地時刻。
        self._control_last_seen_ms: Optional[int] = None
        self._control_tick_count: int = 0

    # ── 連線生命週期 ──

    def connect(self) -> None:
        """建立獨立 WS 連線並固定訂閱 BTC control 哨兵。

        為什麼把 websocket import 延遲到這裡：Mac dev 無 websocket-client，import
        本 module（及單元測試）不該因此失敗；只有真正要連線時才需要該套件。
        """
        if self._ws_app_factory is None:
            import websocket  # 延遲 import；Linux runtime 已驗可用。

            self._ws_app_factory = websocket.WebSocketApp
        self._ws = self._ws_app_factory(
            self._ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

    def run_forever(self, *, ping_interval: int = 20, ping_timeout: int = 10) -> None:
        """阻塞執行 WS event loop（心跳 ping 每 20s，對齊 Bybit 慣例）。"""
        if self._ws is None:
            self.connect()
        # 指數退避重連由 websocket-client 的 reconnect 參數處理（base 3s 對齊生產慣例）。
        self._ws.run_forever(
            ping_interval=ping_interval, ping_timeout=ping_timeout, reconnect=3
        )

    def _on_open(self, _ws: Any) -> None:
        # 連線一建立即固定訂閱 control 哨兵。
        self._send_subscribe([_CONTROL_TOPIC])

    def _on_error(self, _ws: Any, error: Any) -> None:
        self._emit("control", {"kind": "ws_error", "ts_local_ms": self._clock_ms(), "error": str(error)})

    def _on_close(self, _ws: Any, code: Any, msg: Any) -> None:
        self._emit(
            "control",
            {"kind": "ws_close", "ts_local_ms": self._clock_ms(), "code": code, "msg": str(msg)},
        )

    # ── 動態訂閱 ──

    def set_launch_time(self, symbol: str, launch_time_ms: Optional[int]) -> None:
        """由 REST 層餵入某 symbol 的 launchTime（capture_lag 基準）。"""
        with self._lock:
            self._launch_time[symbol] = launch_time_ms

    def sync_subscriptions(self, prelaunch_symbols: set[str]) -> None:
        """依當前 PreLaunch 候選集合動態 subscribe/unsubscribe。

        為什麼動態：只在 symbol 進 PreLaunch 候選才訂 kline.1+publicTrade，轉
        Trading 並收完首筆成交後不再需要佔頻寬（但 unsub 由上層決策；此處只
        負責「新候選補訂」與「不再是候選者退訂」）。control 哨兵不在此集合內，
        永不退訂。
        """
        with self._lock:
            to_add = prelaunch_symbols - self._subscribed
            to_remove = self._subscribed - prelaunch_symbols
        new_topics: list[str] = []
        for sym in sorted(to_add):
            new_topics.append(f"kline.1.{sym}")
            new_topics.append(f"publicTrade.{sym}")
        if new_topics:
            self._send_subscribe(new_topics)
            with self._lock:
                self._subscribed |= to_add
        drop_topics: list[str] = []
        for sym in sorted(to_remove):
            drop_topics.append(f"kline.1.{sym}")
            drop_topics.append(f"publicTrade.{sym}")
        if drop_topics:
            self._send_unsubscribe(drop_topics)
            with self._lock:
                self._subscribed -= to_remove

    def _send_subscribe(self, topics: list[str]) -> None:
        self._send_op("subscribe", topics)

    def _send_unsubscribe(self, topics: list[str]) -> None:
        self._send_op("unsubscribe", topics)

    def _send_op(self, op: str, topics: list[str]) -> None:
        if self._ws is None:
            return
        # 分批：每則訊息最多 10 個 topic（Bybit 限制）。
        for i in range(0, len(topics), _MAX_TOPICS_PER_MSG):
            batch = topics[i : i + _MAX_TOPICS_PER_MSG]
            self._ws.send(json.dumps({"op": op, "args": batch}))

    # ── 訊息分派 ──

    def _on_message(self, _ws: Any, raw: Any) -> None:
        """WS 訊息入口：解析 topic → 分派到 kline / publicTrade / control 處理。"""
        ingest_ts_local = self._clock_ms()
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        self.handle_message(msg, ingest_ts_local)

    def handle_message(self, msg: dict[str, Any], ingest_ts_local_ms: int) -> None:
        """純函數式訊息處理（測試可直接餵 dict，不需真 WS）。"""
        # 訂閱確認 / pong 等控制訊息。
        if isinstance(msg, dict) and msg.get("op") in ("subscribe", "unsubscribe", "pong", "ping"):
            self._emit(
                "control",
                {
                    "kind": "ws_op_ack",
                    "ts_local_ms": ingest_ts_local_ms,
                    "op": msg.get("op"),
                    "success": msg.get("success"),
                    "ret_msg": msg.get("ret_msg"),
                },
            )
            # handler-not-found 毒化偵測：訂閱失敗要顯式記錄（2026-04-05 教訓）。
            if msg.get("success") is False:
                self._emit(
                    "control",
                    {
                        "kind": "ws_subscribe_failed",
                        "ts_local_ms": ingest_ts_local_ms,
                        "ret_msg": msg.get("ret_msg"),
                    },
                )
            return

        topic = msg.get("topic") if isinstance(msg, dict) else None
        if not isinstance(topic, str):
            return
        if topic.startswith("publicTrade."):
            self._handle_public_trade(topic, msg, ingest_ts_local_ms)
        elif topic.startswith("kline."):
            self._handle_kline(topic, msg, ingest_ts_local_ms)

    def _handle_public_trade(
        self, topic: str, msg: dict[str, Any], ingest_ts_local_ms: int
    ) -> None:
        symbol = topic.split(".", 1)[1] if "." in topic else ""
        trades = msg.get("data") or []
        if not isinstance(trades, list):
            return
        for tr in trades:
            if not isinstance(tr, dict):
                continue
            # publicTrade event_ts 欄位為 "T"（毫秒）；價格 "p"，方向 "S"。
            event_ts = self._coerce_int(tr.get("T"))
            price = self._coerce_float(tr.get("p"))
            if event_ts is None or price is None:
                continue

            # control 哨兵 tick（不寫進候選 capture_lag/markout，只更新 liveness）。
            if symbol == _CONTROL_SYMBOL:
                # liveness counter 永遠更新（poison 哨兵的真實依據；與是否落盤無關）。
                self._control_last_seen_ms = ingest_ts_local_ms
                self._control_tick_count += 1
                # G1：production 模式（persist_control_ticks=False）不逐筆落盤，避免
                # BTC 高頻成交灌爆 control JSONL（探針觀測 346MB/43h firehose）。
                # 探針預設 True 維持逐筆 control_trade 落盤（向後相容）。
                if self._persist_control_ticks:
                    self._emit(
                        "control",
                        {
                            "kind": "control_trade",
                            "ts_local_ms": ingest_ts_local_ms,
                            "event_ts_ms": event_ts,
                            "price": price,
                            "tick_count": self._control_tick_count,
                        },
                    )
                continue

            self._emit(
                "publictrade",
                self._provenance_row(
                    {
                        "kind": "public_trade",
                        "symbol": symbol,
                        "event_ts_exchange_ms": event_ts,
                        "price": price,
                        "side": tr.get("S"),
                        "size": self._coerce_float(tr.get("v")),
                        # OQ-3：Bybit publicTrade trade_id `i`（全 symbol 唯一）。collector
                        # pg_sink 用它進 PK 防 listing pump 同價同毫秒誤併。探針不讀此欄
                        # 不受影響（additive；其 artifact JSONL 多一欄無害）。
                        "trade_id": tr.get("i"),
                    },
                    ingest_ts_local_ms,
                    event_ts,
                ),
            )

            # markout：用成交價近似 mid 推進 ring。必須在 capture_lag 之前 push，
            # 因為首筆成交會註冊 markout trigger，trigger 需用「自己這筆」的 mid
            # 當 mid@trigger（先 push 後 register，否則 ring 為空抓不到 trigger mid）。
            ring = self._rings.setdefault(symbol, MidPriceRing())
            ring.push(event_ts, price)
            # capture_lag：首筆成交（內部會註冊 markout trigger，依賴上面已 push 的 ring）。
            self._maybe_record_capture_lag(symbol, event_ts, ingest_ts_local_ms)
            # 回填已到點的 pending markout horizon。
            self._fill_due_markouts(ingest_ts_local_ms)

    def _handle_kline(self, topic: str, msg: dict[str, Any], ingest_ts_local_ms: int) -> None:
        parts = topic.split(".")
        symbol = parts[2] if len(parts) >= 3 else ""
        klines = msg.get("data") or []
        if not isinstance(klines, list):
            return
        for k in klines:
            if not isinstance(k, dict):
                continue
            # 未確認 K 線（confirm=false）也記錄（探針要完整捕捉管線，不過濾）。
            start_ts = self._coerce_int(k.get("start"))
            close_px = self._coerce_float(k.get("close"))
            if start_ts is None:
                continue
            self._emit(
                "kline",
                self._provenance_row(
                    {
                        "kind": "kline_1m",
                        "symbol": symbol,
                        "event_ts_exchange_ms": start_ts,
                        "open": self._coerce_float(k.get("open")),
                        "high": self._coerce_float(k.get("high")),
                        "low": self._coerce_float(k.get("low")),
                        "close": close_px,
                        "volume": self._coerce_float(k.get("volume")),
                        "confirm": bool(k.get("confirm", False)),
                    },
                    ingest_ts_local_ms,
                    start_ts,
                ),
            )

    # ── capture_lag ──

    def _maybe_record_capture_lag(
        self, symbol: str, event_ts_ms: int, ingest_ts_local_ms: int
    ) -> None:
        """記錄某 symbol 的首筆成交 capture_lag = first_trade_event_ts − launchTime。

        為什麼用 event_ts 而非 ingest 時刻：capture_lag 衡量的是「交易所首筆成交相對
        排定 launchTime 的延遲」，必須用交易所事件時間；ingest 時刻另記在 provenance
        裡供 leak/clock-skew 診斷，不混入 capture_lag 本體。
        """
        if symbol in self._first_trade_ts:
            return
        self._first_trade_ts[symbol] = event_ts_ms
        launch = self._launch_time.get(symbol)
        capture_lag_ms: Optional[int] = None
        verdict = "NO_LAUNCH_TIME"
        if launch is not None:
            capture_lag_ms = event_ts_ms - launch
            verdict = "PASS_CAPTURE" if capture_lag_ms <= _CAPTURE_LAG_PASS_MS else "SLOW_CAPTURE"
        self._emit(
            "capture_lag",
            {
                "kind": "capture_lag",
                "symbol": symbol,
                "launch_time_ms": launch,
                "first_trade_event_ts_ms": event_ts_ms,
                "first_trade_ingest_ts_local_ms": ingest_ts_local_ms,
                "capture_lag_ms": capture_lag_ms,
                "verdict": verdict,
            },
        )
        # 同步在首筆成交建立一個 markout trigger（trigger=首筆成交價）。
        self._register_markout_trigger(symbol, event_ts_ms, ingest_ts_local_ms)

    # ── markout ──

    def _register_markout_trigger(
        self, symbol: str, trigger_event_ts_ms: int, ingest_ts_local_ms: int
    ) -> None:
        ring = self._rings.setdefault(symbol, MidPriceRing())
        # trigger 當下 mid 用「該時刻或之後第一筆」近似（剛 push 進去的首筆）。
        mid_at_trigger = ring.mid_at_or_after(trigger_event_ts_ms)
        if mid_at_trigger is None:
            return
        pending = _PendingMarkout(
            symbol=symbol,
            trigger_event_ts_ms=trigger_event_ts_ms,
            mid_at_trigger=mid_at_trigger[1],
            filled={h: False for h in _MARKOUT_HORIZONS_S},
        )
        self._pending_markouts.append(pending)
        self._emit(
            "markout",
            {
                "kind": "markout_trigger",
                "symbol": symbol,
                "trigger_event_ts_ms": trigger_event_ts_ms,
                "trigger_ingest_ts_local_ms": ingest_ts_local_ms,
                "mid_at_trigger": mid_at_trigger[1],
            },
        )

    def _fill_due_markouts(self, ingest_ts_local_ms: int) -> None:
        """對所有 pending markout，回填已到點（ring 有 ≥ target_ts 資料）的 horizon。"""
        for pending in self._pending_markouts:
            ring = self._rings.get(pending.symbol)
            if ring is None:
                continue
            for horizon in _MARKOUT_HORIZONS_S:
                if pending.filled.get(horizon):
                    continue
                target_ts = pending.trigger_event_ts_ms + horizon * 1000
                hit = ring.mid_at_or_after(target_ts)
                if hit is None:
                    continue
                pending.filled[horizon] = True
                markout_bps = (
                    (hit[1] - pending.mid_at_trigger) / pending.mid_at_trigger * 10_000.0
                    if pending.mid_at_trigger
                    else None
                )
                self._emit(
                    "markout",
                    {
                        "kind": "markout_fill",
                        "symbol": pending.symbol,
                        "trigger_event_ts_ms": pending.trigger_event_ts_ms,
                        "horizon_s": horizon,
                        "target_event_ts_ms": target_ts,
                        "filled_event_ts_ms": hit[0],
                        "mid_at_trigger": pending.mid_at_trigger,
                        "mid_at_horizon": hit[1],
                        "markout_bps": markout_bps,
                        "fill_ingest_ts_local_ms": ingest_ts_local_ms,
                    },
                )

    # ── control 哨兵 unpoisoned 判定 ──

    def control_liveness(self) -> dict[str, Any]:
        """回傳 control 哨兵狀態：tick 數 + 是否疑似被毒化。

        為什麼是 unpoisoned 的證明：BTC publicTrade 永遠高頻；若一段時間（預設
        60s）內 control 完全沒 tick，極可能是某個壞訂閱觸發了 handler-not-found
        把整條連線毒化（2026-04-05 教訓）。此判定給 verdict 層當隔離健康證據。
        """
        now = self._clock_ms()
        last = self._control_last_seen_ms
        stale_ms = None if last is None else now - last
        poisoned_suspect = (
            self._control_tick_count == 0 or (stale_ms is not None and stale_ms > _CONTROL_STALE_MS)
        )
        return {
            "control_symbol": _CONTROL_SYMBOL,
            "control_tick_count": self._control_tick_count,
            "control_last_seen_ms": last,
            "control_stale_ms": stale_ms,
            "poisoned_suspect": poisoned_suspect,
        }

    def first_trade_ts(self, symbol: str) -> Optional[int]:
        return self._first_trade_ts.get(symbol)

    # ── 共用小工具 ──

    def _provenance_row(
        self, base: dict[str, Any], ingest_ts_local_ms: int, event_ts_exchange_ms: int
    ) -> dict[str, Any]:
        """為每筆事件附 leak-free provenance：本地 ingest 時刻 + 交易所事件時刻 + 差值。

        為什麼三欄都記：研究階段只能用 event_ts 排序（point-in-time，無 look-ahead）；
        ingest_ts_local 與 ingest_minus_event_ms 僅供 clock-skew / 延遲診斷，不可用於
        排序或構造特徵。
        """
        row = dict(base)
        row["ingest_ts_local_ms"] = ingest_ts_local_ms
        row["event_ts_exchange_ms"] = event_ts_exchange_ms
        row["ingest_minus_event_ms"] = ingest_ts_local_ms - event_ts_exchange_ms
        return row

    def _emit(self, channel: str, row: dict[str, Any]) -> None:
        writer = self._writers.get(channel)
        if writer is not None:
            writer(row)

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


__all__ = [
    "MidPriceRing",
    "GateBWsProbe",
]

"""
Tests for counterfactual_exit_audit CLI (DUAL-TRACK-EXIT-1 Track P T5).
counterfactual_exit_audit CLI 測試（DUAL-TRACK-EXIT-1 Track P T5）。

Design note / 設計註解：
  These tests use **in-memory fixtures + dependency injection**, never touching
  Postgres. The `conn_factory` argument on `run_audit` is the injection seam;
  `pair_fills_to_positions` / `simulate_phys_lock` / `check_kline_freshness`
  are tested as pure functions on synthetic data.
  測試僅用記憶體 fixture + 依賴注入，不連 Postgres。`run_audit` 的 `conn_factory`
  參數為注入縫；`pair_fills_to_positions` / `simulate_phys_lock` /
  `check_kline_freshness` 以純函式方式對合成資料測試。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from program_code.audit import counterfactual_exit_audit as cfa


# ---------------------------------------------------------------------------
# Shared fixtures / 共用 fixture
# ---------------------------------------------------------------------------


_T0 = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)


def _mk_bar(offset_min: int, o: float, h: float, l: float, c: float) -> cfa.KlineBar:
    """Build a 1-min KlineBar at T0+offset_min. / 在 T0+offset_min 建立 1-min KlineBar。"""
    return cfa.KlineBar(
        ts=_T0 + timedelta(minutes=offset_min),
        open=o, high=h, low=l, close=c,
    )


def _mk_position(
    *, side: str = "Buy", entry_price: float = 100.0, exit_price: float = 101.0,
    entry_offset_min: int = 0, exit_offset_min: int = 15,
    strategy: str = "grid_trading", symbol: str = "BTCUSDT",
) -> cfa.Position:
    """Build a synthetic Position at T0+offsets. / 以 T0 偏移建立合成 Position。"""
    return cfa.Position(
        strategy=strategy, symbol=symbol,
        entry_ts=_T0 + timedelta(minutes=entry_offset_min),
        exit_ts=_T0 + timedelta(minutes=exit_offset_min),
        entry_price=entry_price, exit_price=exit_price,
        qty=1.0, side=side,
        entry_context_id="ctx-test-001",
    )


# ---------------------------------------------------------------------------
# Test 1 — Kline stale detection triggers fills-only fallback
# 測試 1 — Kline 陳舊偵測會觸發 fills-only 降級
# ---------------------------------------------------------------------------


def test_kline_stale_detection_triggers_fallback(caplog) -> None:
    """
    Given: latest kline ts is 48h before `now`
    Then : check_kline_freshness returns False AND run_audit degrades to
           mode=fills_only with delta_bps=None.
    給定：最新 kline ts 為 now-48h
    斷言：check_kline_freshness 回 False 且 run_audit 降級為 mode=fills_only，
          delta_bps=None。
    """
    now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)
    stale_ts = now - timedelta(hours=48)

    # Unit-level check on the pure helper.
    # 純函式層級單元檢查。
    assert cfa.check_kline_freshness(stale_ts, now=now) is False
    assert cfa.check_kline_freshness(None, now=now) is False
    assert cfa.check_kline_freshness(now - timedelta(hours=1), now=now) is True

    # End-to-end: wire a fake conn that returns stale ts + a paired exit row.
    # 端到端：注入假 conn，回傳陳舊 ts 與一組配對 exit fill。
    entry_ts = now - timedelta(hours=2)
    exit_ts = now - timedelta(hours=1, minutes=30)
    fills = [
        {
            "ts": entry_ts, "symbol": "BTCUSDT", "strategy_name": "grid_trading",
            "side": "Buy", "qty": 1.0, "price": 100.0, "fee": 0.1,
            "realized_pnl": 0.0, "engine_mode": "demo",
            "context_id": "ctx-A", "entry_context_id": None,
        },
        {
            "ts": exit_ts, "symbol": "BTCUSDT", "strategy_name": "strategy_close:tp",
            "side": "Sell", "qty": 1.0, "price": 101.0, "fee": 0.1,
            "realized_pnl": 1.0, "engine_mode": "demo",
            "context_id": "ctx-A-close", "entry_context_id": "ctx-A",
        },
    ]

    fake_conn = _FakeConn(fills=fills, latest_kline_ts=stale_ts, klines={})

    with caplog.at_level(logging.WARNING, logger=cfa.logger.name):
        output = cfa.run_audit(
            days=7, strategy="grid_trading", engine_mode="demo",
            conn_factory=lambda: fake_conn,
            now=now,
        )

    assert output["meta"]["mode"] == "fills_only"
    assert output["meta"]["kline_fresh"] is False
    assert output["meta"]["n_positions"] == 1
    rec = output["records"][0]
    assert rec["delta_bps"] is None
    assert rec["phys_reason"] == "klines_stale_fallback"
    # Warning was emitted
    assert any("stale" in msg.lower() or "陳舊" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# Test 2 — Missing entry_context_id yields graceful skip + warning
# 測試 2 — 缺失 entry_context_id 會優雅 skip + 警告
# ---------------------------------------------------------------------------


def test_fills_join_missing_entry_context_id_graceful() -> None:
    """
    Exit fills with entry_context_id=NULL must NOT crash the audit; they must
    be skipped with a warning, and the paired row must still be produced when
    present.
    entry_context_id=NULL 的 exit fill 必須不讓審計 crash；應 skip 並發 warning，
    同時正確配對的行仍應產出。
    """
    captured: list[str] = []

    fills = [
        # Good pair — entry ctx-A with a close fill that points back via entry_context_id.
        # 好配對 — entry ctx-A 配 exit entry_context_id=ctx-A
        {
            "ts": _T0, "symbol": "BTCUSDT", "strategy_name": "grid_trading",
            "side": "Buy", "qty": 1.0, "price": 100.0, "fee": 0.0,
            "realized_pnl": 0.0, "context_id": "ctx-A",
            "entry_context_id": None,
        },
        {
            "ts": _T0 + timedelta(minutes=5), "symbol": "BTCUSDT",
            "strategy_name": "strategy_close:tp",
            "side": "Sell", "qty": 1.0, "price": 101.0, "fee": 0.0,
            "realized_pnl": 1.0, "context_id": "ctx-A-close",
            "entry_context_id": "ctx-A",
        },
        # Bad exit — entry_context_id is NULL on the close fill (bybit_sync artefact).
        # 壞 exit — close fill 的 entry_context_id 為 NULL（bybit_sync 舊物）。
        {
            "ts": _T0 + timedelta(minutes=10), "symbol": "ETHUSDT",
            "strategy_name": "strategy_close:tp",
            "side": "Sell", "qty": 1.0, "price": 200.0, "fee": 0.0,
            "realized_pnl": 2.0, "context_id": "ctx-B-close",
            "entry_context_id": None,
        },
        # Bad exit — entry_context_id references a non-existent entry.
        # 壞 exit — entry_context_id 指向不存在的 entry。
        {
            "ts": _T0 + timedelta(minutes=11), "symbol": "SOLUSDT",
            "strategy_name": "strategy_close:tp",
            "side": "Sell", "qty": 1.0, "price": 50.0, "fee": 0.0,
            "realized_pnl": 1.0, "context_id": "ctx-Z-close",
            "entry_context_id": "ctx-does-not-exist",
        },
    ]

    positions = cfa.pair_fills_to_positions(
        fills, strategy_filter="grid_trading",
        unpaired_warn=lambda msg: captured.append(msg),
    )

    # Only the good pair should survive.
    # 只有好配對會留下。
    assert len(positions) == 1
    assert positions[0].strategy == "grid_trading"
    assert positions[0].symbol == "BTCUSDT"
    # Two warnings were emitted for the two unpaired exits.
    # 兩個壞 exit 各發一次 warning。
    assert len(captured) == 2
    assert any("entry_context_id" in m for m in captured)


# ---------------------------------------------------------------------------
# Test 3 — Synthetic peak+decay position locks at the right moment
# 測試 3 — 合成「峰值+衰減」倉位會在正確時刻觸發鎖倉
# ---------------------------------------------------------------------------


def test_phys_lock_rule_on_synthetic_fixture_locks_expected() -> None:
    """
    Synthetic long position: entry=100 at t=0, peak=102 at t=5min,
    decays to 101 by t=15min. With a relaxed cfg (giveback_atr_threshold small)
    Track P should propose locking when giveback is material.
    合成多單：t=0 entry=100, t=5min peak=102, t=15min 回到 101。
    放寬設定後 Track P 應在 giveback 具體化時建議鎖倉。
    """
    position = _mk_position(entry_price=100.0, exit_price=101.0,
                            entry_offset_min=0, exit_offset_min=15)

    # Construct bars: rising to t=5 (peak 102.5 intraday high, close 102),
    # then drifting down to close 101 at t=15. Each bar range ~0.3% → atr_pct ≈ 0.3.
    # 建構 bars：t=5 峰值；t=15 回到 101。每根 bar 約 0.3% 寬度 → atr_pct ≈ 0.3。
    bars: list[cfa.KlineBar] = []
    # Ramp up
    for i in range(6):
        c = 100.0 + i * 0.4
        bars.append(_mk_bar(i, o=c - 0.15, h=c + 0.15, l=c - 0.2, c=c))
    # bars[5] close = 102.0; this is the peak.
    # Drift down (5 more bars), each closing 0.2 below previous.
    for i in range(6, 16):
        prev_close = bars[-1].close
        c = prev_close - 0.1
        bars.append(_mk_bar(i, o=prev_close, h=prev_close + 0.1, l=c - 0.15, c=c))

    cfg = cfa.PhysLockConfig(
        min_net_floor_bps=5.0,        # very permissive
        min_hold_secs=60,             # 1 min
        min_peak_atr_norm=0.2,        # permissive
        giveback_atr_threshold=0.5,   # permissive
        stale_peak_ms=60_000,
        atr_fallback_pct=1.0,
    )

    decision = cfa.simulate_phys_lock(
        position, bars, cfg, fee_rate_bps=5.0,
    )

    assert decision.phys_rule_hit is True, (
        f"Expected lock, got reason={decision.phys_reason}"
    )
    assert decision.cf_exit_ts is not None
    # Lock must be strictly after the peak bar (t=5min).
    # 鎖倉必須嚴格晚於峰值 bar（t=5min）。
    assert decision.cf_exit_ts > position.entry_ts + timedelta(minutes=5)
    # And not later than the real exit.
    # 也不應晚於真實退場。
    assert decision.cf_exit_ts <= position.exit_ts
    assert "PHYS-LOCK" in decision.phys_reason

    # End-to-end audit_position: delta_bps should be positive (cf locked above
    # real exit price for a long).
    # 端到端 audit_position：delta_bps 對多單應為正（cf 鎖價高於真實 exit 101）。
    record = cfa.audit_position(position, bars, cfg, kline_fresh=True, fee_rate_bps=5.0)
    assert record.delta_bps is not None
    assert record.delta_bps > 0.0
    assert record.cf_phys_exit_pnl_pct is not None
    assert record.cf_phys_exit_pnl_pct > record.real_exit_pnl_pct


# ---------------------------------------------------------------------------
# Extra smoke test — summariser handles empty + mixed inputs
# 額外冒煙測試 — summariser 處理空 + 混合輸入
# ---------------------------------------------------------------------------


def test_summarise_empty_and_mixed() -> None:
    """summarise() returns None-safe aggregates on empty / mixed records.
    summarise() 對空 / 混合輸入須回 None-safe 聚合。
    """
    # Empty
    empty = cfa.summarise([])
    assert empty["delta_bps_mean"] is None
    assert empty["n_positions_with_delta"] == 0

    # Mixed: one hit positive, one hit negative, one None (fallback).
    # 混合：一正、一負、一 None（fallback）。
    records = [
        cfa.AuditRecord(
            strategy="grid_trading", symbol="BTCUSDT",
            entry_ts="2026-04-18T12:00:00+00:00",
            exit_ts="2026-04-18T12:15:00+00:00",
            real_exit_pnl_pct=0.5, cf_phys_exit_pnl_pct=1.0,
            delta_bps=50.0, phys_rule_hit=True, phys_reason="PHYS-LOCK",
        ),
        cfa.AuditRecord(
            strategy="grid_trading", symbol="ETHUSDT",
            entry_ts="2026-04-18T12:00:00+00:00",
            exit_ts="2026-04-18T12:15:00+00:00",
            real_exit_pnl_pct=0.5, cf_phys_exit_pnl_pct=0.2,
            delta_bps=-30.0, phys_rule_hit=True, phys_reason="PHYS-LOCK",
        ),
        cfa.AuditRecord(
            strategy="grid_trading", symbol="SOLUSDT",
            entry_ts="2026-04-18T12:00:00+00:00",
            exit_ts="2026-04-18T12:15:00+00:00",
            real_exit_pnl_pct=0.5, cf_phys_exit_pnl_pct=None,
            delta_bps=None, phys_rule_hit=False, phys_reason="klines_stale_fallback",
        ),
    ]
    summary = cfa.summarise(records)
    assert summary["n_positions_with_delta"] == 2
    assert summary["n_phys_would_lock"] == 2
    assert summary["n_phys_better"] == 1
    assert summary["n_phys_worse"] == 1
    assert summary["delta_bps_mean"] == pytest.approx((50.0 + -30.0) / 2)


# ---------------------------------------------------------------------------
# Fake DB connection for end-to-end run_audit test
# run_audit 端到端測試用的假 DB 連線
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Psycopg2 cursor stand-in backed by prepared query→rows mapping.
    預先備好 query→rows 對照的 psycopg2 cursor 替身。
    """

    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn
        self.description: list[tuple[str, ...]] = []
        self._rows: list[tuple] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str, params: dict | None = None) -> None:
        params = params or {}
        q_strip = " ".join(query.split())
        if q_strip.startswith("SELECT MAX(ts) AS latest_ts"):
            self.description = [("latest_ts",)]
            self._rows = [(self._conn.latest_kline_ts,)]
            return
        if "FROM trading.fills" in q_strip:
            # Emit fills as rows in the order the SELECT declares.
            # 按 SELECT 宣告順序回傳 fills。
            self.description = [
                ("ts",), ("symbol",), ("strategy_name",), ("side",),
                ("qty",), ("price",), ("fee",), ("realized_pnl",),
                ("engine_mode",), ("context_id",), ("entry_context_id",),
            ]
            self._rows = [
                (
                    f["ts"], f["symbol"], f["strategy_name"], f["side"],
                    f["qty"], f["price"], f["fee"], f["realized_pnl"],
                    f["engine_mode"], f["context_id"], f["entry_context_id"],
                )
                for f in self._conn.fills
            ]
            return
        if "FROM market.klines" in q_strip:
            sym = params["symbol"]
            start_ts = params["start_ts"]
            end_ts = params["end_ts"]
            bars = self._conn.klines.get(sym, [])
            self.description = [("ts",), ("open",), ("high",), ("low",), ("close",)]
            self._rows = [
                (b.ts, b.open, b.high, b.low, b.close)
                for b in bars
                if start_ts <= b.ts <= end_ts
            ]
            return
        raise AssertionError(f"Unrecognised query in fake cursor: {q_strip!r}")

    def fetchall(self) -> list[tuple]:
        return list(self._rows)

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None


class _FakeConn:
    """Minimal psycopg2 connection stand-in for run_audit tests.
    run_audit 測試用的最小 psycopg2 連線替身。
    """

    def __init__(
        self,
        *,
        fills: list[dict],
        latest_kline_ts: Any,
        klines: dict[str, list[cfa.KlineBar]],
    ) -> None:
        self.fills = fills
        self.latest_kline_ts = latest_kline_ts
        self.klines = klines
        self._closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def close(self) -> None:
        self._closed = True

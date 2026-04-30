"""Tests for ``strategy_wiring_scanner`` Scout heartbeat wiring.
``strategy_wiring_scanner`` Scout 心跳接線測試。

MODULE_NOTE (English):
  Hermetic tests for the production ScoutWorker scan closure. The real wiring
  imports MarketScanner, StrategyAutoDeployer, ScoutWorker, and route modules
  inside ``wire_market_scanner_and_workers``; these tests replace those modules
  with fakes so no background threads, exchange calls, or FastAPI app startup
  are triggered.

MODULE_NOTE (中文):
  針對 production ScoutWorker scan closure 的封閉測試。真實 wiring 會在
  ``wire_market_scanner_and_workers`` 內部 import MarketScanner、
  StrategyAutoDeployer、ScoutWorker 與 route 模組；本測試以 fake module
  替換，避免啟動背景 thread、交易所呼叫或 FastAPI app。
"""

from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest


_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
_CONTROL_API_DIR = os.path.dirname(_TEST_DIR)
if _CONTROL_API_DIR not in sys.path:
    sys.path.insert(0, _CONTROL_API_DIR)


@dataclass
class _Opportunity:
    """Minimal market-scanner opportunity fake / 最小 market-scanner 機會替身。"""

    symbol: str
    score: float


class _FakeMarketScanner:
    """Fake MarketScanner that exposes a configurable ``scan`` result.
    可配置 ``scan`` 結果的 MarketScanner 測試替身。"""

    opportunities: list[_Opportunity] = []
    last_instance: "_FakeMarketScanner | None" = None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.callbacks: list[Any] = []
        self.started = False
        _FakeMarketScanner.last_instance = self

    def register_on_scan(self, callback: Any) -> None:
        self.callbacks.append(callback)

    def start(self) -> None:
        self.started = True

    def scan(self) -> list[_Opportunity]:
        return list(self.opportunities)


class _FakeAutoDeployer:
    """Fake auto-deployer for scanner callback wiring.
    scanner callback 接線用的自動部署器替身。"""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.backtest_engine = None

    def on_scan_results(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def set_backtest_engine(self, engine: Any, *, min_sharpe: float) -> None:
        self.backtest_engine = (engine, min_sharpe)


class _FakeScoutWorker:
    """Fake ScoutWorker that captures scan_fn without starting a thread.
    捕獲 scan_fn 但不啟動 thread 的 ScoutWorker 替身。"""

    last_instance: "_FakeScoutWorker | None" = None

    def __init__(self, scan_fn: Any, *_args: Any, **_kwargs: Any) -> None:
        self.scan_fn = scan_fn
        self.started = False
        _FakeScoutWorker.last_instance = self

    def start(self) -> None:
        self.started = True


class _FakeScoutAgent:
    """Small ScoutAgent fake with the production methods used by the closure.
    只含 closure 所需 production method 的 ScoutAgent 替身。"""

    def __init__(self) -> None:
        self.intel_calls: list[dict[str, Any]] = []
        self.record_scan_count = 0

    def produce_intel(self, **kwargs: Any) -> None:
        self.intel_calls.append(kwargs)

    def record_scan(self) -> None:
        self.record_scan_count += 1


@pytest.fixture
def scanner_wiring_fakes(monkeypatch: pytest.MonkeyPatch):
    """Install fake import targets consumed by strategy_wiring_scanner.
    安裝 strategy_wiring_scanner 內部 import 會消費的替身模組。"""

    _FakeMarketScanner.opportunities = []
    _FakeMarketScanner.last_instance = None
    _FakeScoutWorker.last_instance = None

    monkeypatch.setitem(
        sys.modules,
        "local_model_tools.market_scanner",
        types.SimpleNamespace(MarketScanner=_FakeMarketScanner),
    )
    monkeypatch.setitem(
        sys.modules,
        "local_model_tools.strategy_auto_deployer",
        types.SimpleNamespace(StrategyAutoDeployer=_FakeAutoDeployer),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.scout_worker",
        types.SimpleNamespace(ScoutWorker=_FakeScoutWorker),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.backtest_routes",
        types.SimpleNamespace(get_backtest_engine=lambda: object()),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.evolution_routes",
        types.SimpleNamespace(set_auto_deployer=lambda _auto_deployer: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.scout_routes",
        types.SimpleNamespace(
            set_scout_agent=lambda _agent: None,
            set_message_bus=lambda _bus: None,
            set_perception_plane=lambda _plane: None,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "app.paper_trading_routes",
        types.SimpleNamespace(PERCEPTION_PLANE=None),
    )

    from app.strategy_wiring_scanner import wire_market_scanner_and_workers

    return wire_market_scanner_and_workers


def _wire_fake_scout_worker(wire_market_scanner_and_workers: Any, scout: _FakeScoutAgent) -> _FakeScoutWorker:
    """Run wiring and return the captured fake ScoutWorker.
    執行 wiring 並回傳捕獲到的 fake ScoutWorker。"""

    result = wire_market_scanner_and_workers(
        orchestrator=object(),
        kline_manager=object(),
        paper_engine=None,
        scout_agent=scout,
        message_bus=object(),
    )
    assert result.market_scanner is not None
    assert result.auto_deployer is not None
    assert result.scout_worker is not None
    assert _FakeScoutWorker.last_instance is not None
    return _FakeScoutWorker.last_instance


def test_scout_worker_scan_records_heartbeat_after_intel(scanner_wiring_fakes: Any) -> None:
    """Successful ScoutWorker scan emits intel and records one heartbeat.
    ScoutWorker 成功掃描時產出情報並記錄一次心跳。"""

    _FakeMarketScanner.opportunities = [
        _Opportunity("LOWUSDT", 0.1),
        _Opportunity("TOPUSDT", 0.9),
        _Opportunity("MIDUSDT", 0.5),
    ]
    scout = _FakeScoutAgent()
    worker = _wire_fake_scout_worker(scanner_wiring_fakes, scout)

    worker.scan_fn()

    assert scout.record_scan_count == 1
    assert len(scout.intel_calls) == 1
    assert scout.intel_calls[0]["source"] == "ScoutWorker"
    assert scout.intel_calls[0]["symbols"] == ["TOPUSDT", "MIDUSDT", "LOWUSDT"]


def test_scout_worker_empty_scan_records_heartbeat(scanner_wiring_fakes: Any) -> None:
    """Empty ScoutWorker scan still records one completed scan heartbeat.
    ScoutWorker 空掃描仍記錄一次完成掃描心跳。"""

    _FakeMarketScanner.opportunities = []
    scout = _FakeScoutAgent()
    worker = _wire_fake_scout_worker(scanner_wiring_fakes, scout)

    worker.scan_fn()

    assert scout.record_scan_count == 1
    assert scout.intel_calls == []

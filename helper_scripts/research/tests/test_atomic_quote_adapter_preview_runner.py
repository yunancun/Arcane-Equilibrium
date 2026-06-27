from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from cost_gate_learning_lane import bbo_freshness_public_quote_capture as quote_capture
from cost_gate_learning_lane.atomic_quote_adapter_preview_runner import (
    QUOTE_NOT_READY_STATUS,
    READY_STATUS,
    _output_path_allowed,
    run_atomic_quote_adapter_preview,
)


START = dt.datetime(2026, 6, 26, 10, 45, tzinfo=dt.timezone.utc)
START_MS = int(START.timestamp() * 1000)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


class Clock:
    def __init__(self) -> None:
        self.now_ms = START_MS

    def now(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(self.now_ms / 1000.0, tz=dt.timezone.utc)

    def monotonic(self) -> float:
        return self.now_ms / 1000.0

    def advance(self, ms: int) -> None:
        self.now_ms += ms


class FakeHTTPResponse:
    def __init__(self, payload: dict, *, status: int = 200) -> None:
        self.status = status
        self.headers = {"X-Bapi-Limit": "120"}
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self._raw


class FakeOpener:
    def __init__(
        self,
        clock: Clock,
        *,
        retcode: int = 0,
        symbol: str = "AVAXUSDT",
        bid: str = "6.174",
        ask: str = "6.175",
        last_price: str = "6.174",
        mark_price: str = "6.175",
        qty_step: str = "0.1",
        min_notional: str = "5",
    ) -> None:
        self.clock = clock
        self.retcode = retcode
        self.symbol = symbol
        self.bid = bid
        self.ask = ask
        self.last_price = last_price
        self.mark_price = mark_price
        self.qty_step = qty_step
        self.min_notional = min_notional
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        path = __import__("urllib.parse").parse.urlsplit(req.full_url).path
        self.clock.advance(10)
        return FakeHTTPResponse(
            _payload_for_path(
                path,
                retcode=self.retcode,
                symbol=self.symbol,
                bid=self.bid,
                ask=self.ask,
                last_price=self.last_price,
                mark_price=self.mark_price,
                qty_step=self.qty_step,
                min_notional=self.min_notional,
            )
        )


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    if "side_cell_key" not in overrides:
        payload["side_cell_key"] = (
            f"{payload['strategy_name']}|{payload['symbol']}|{payload['side']}"
        )
    return payload


def _reroute(candidate: dict | None = None, **overrides) -> dict:
    payload = {
        **(candidate or _candidate()),
        "false_negative_rank": 2,
        "friction_rank": 2,
        "avg_net_bps": 73.5511,
        "net_positive_pct": 100.0,
        "outcome_count": 48,
        "current_cap_usdt": 10.0,
        "minimum_required_demo_notional_usdt_per_order": 5.0,
        "instrument_status": "Trading",
    }
    payload.update(overrides)
    return {
        "schema_version": "bounded_demo_probe_lower_price_reroute_review_v1",
        "generated_at_utc": START.isoformat(),
        "status": "LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW",
        "selected_candidate": payload,
        "answers": {
            "bybit_call_performed": False,
            "pg_write_performed": False,
            "order_submission_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }


def _payload_for_path(
    path: str,
    *,
    retcode: int = 0,
    symbol: str = "AVAXUSDT",
    bid: str = "6.174",
    ask: str = "6.175",
    last_price: str = "6.174",
    mark_price: str = "6.175",
    qty_step: str = "0.1",
    min_notional: str = "5",
) -> dict:
    retmsg = "OK" if retcode == 0 else "bad"
    if path == quote_capture.TIME_PATH:
        return {
            "retCode": retcode,
            "retMsg": retmsg,
            "result": {"timeSecond": str(int((START_MS + 10) / 1000))},
            "time": START_MS + 10,
        }
    if path == quote_capture.TICKERS_PATH:
        return {
            "retCode": retcode,
            "retMsg": retmsg,
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": symbol,
                        "bid1Price": bid,
                        "ask1Price": ask,
                        "bid1Size": "726.5",
                        "ask1Size": "71.4",
                        "lastPrice": last_price,
                        "markPrice": mark_price,
                    }
                ],
            },
            "time": START_MS + 20,
        }
    if path == quote_capture.INSTRUMENTS_PATH:
        return {
            "retCode": retcode,
            "retMsg": retmsg,
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": symbol,
                        "status": "Trading",
                        "priceFilter": {"tickSize": "0.001"},
                        "lotSizeFilter": {
                            "qtyStep": qty_step,
                            "minNotionalValue": min_notional,
                        },
                    }
                ],
            },
            "time": START_MS + 30,
        }
    raise AssertionError(f"unexpected path: {path}")


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_atomic_runner_keeps_quote_adapter_preview_inside_freshness_window(tmp_path) -> None:
    reroute = _reroute()
    reroute_path = tmp_path / "reroute.json"
    output_dir = tmp_path / "atomic"
    _write_json(reroute_path, reroute)
    clock = Clock()
    opener = FakeOpener(clock)

    packet = run_atomic_quote_adapter_preview(
        reroute_review=reroute,
        reroute_review_path=reroute_path,
        output_dir=output_dir,
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        demo_operational_authorization_available=True,
        source_head="source-head",
        runtime_head="runtime-head",
    )

    assert packet["status"] == READY_STATUS
    assert packet["request_count"] == 3
    assert packet["statuses"]["public_quote"] == "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER"
    assert (
        packet["statuses"]["market_snapshot"]
        == "PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_NO_ORDER"
    )
    assert (
        packet["statuses"]["construction_preview"]
        == "CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER"
    )
    assert packet["answers"]["bybit_public_market_data_call_performed"] is True
    assert packet["answers"]["adapter_reused_public_quote_artifact"] is True
    assert packet["answers"]["construction_preview_ready_no_order"] is True
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert (output_dir / "public_quote.json").exists()
    assert (output_dir / "market_snapshot.json").exists()
    assert (output_dir / "construction_preview.json").exists()


def test_atomic_runner_derives_eth_cap_from_reviewed_candidate_without_default_10(
    tmp_path,
) -> None:
    candidate = _candidate(symbol="ETHUSDT", side="Buy")
    reroute = _reroute(
        candidate=candidate,
        current_cap_usdt=20.0,
        minimum_required_demo_notional_usdt_per_order=5.0,
    )
    reroute_path = tmp_path / "reroute.json"
    output_dir = tmp_path / "atomic"
    _write_json(reroute_path, reroute)
    clock = Clock()
    opener = FakeOpener(
        clock,
        symbol="ETHUSDT",
        bid="2500.0",
        ask="2500.5",
        last_price="2500.2",
        mark_price="2500.2",
        qty_step="0.001",
    )

    packet = run_atomic_quote_adapter_preview(
        reroute_review=reroute,
        reroute_review_path=reroute_path,
        output_dir=output_dir,
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        demo_operational_authorization_available=True,
    )

    public_quote = json.loads((output_dir / "public_quote.json").read_text())
    market_snapshot = json.loads((output_dir / "market_snapshot.json").read_text())
    preview = json.loads((output_dir / "construction_preview.json").read_text())

    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|ETHUSDT|Buy"
    assert public_quote["risk_limits"]["cap_usdt"] == 20.0
    assert public_quote["risk_limits"]["reviewed_candidate_cap_usdt"] == 20.0
    assert (
        public_quote["risk_limits"]["cap_source"]
        == "reroute_review.selected_candidate.current_cap_usdt"
    )
    assert public_quote["risk_limits"]["global_risk_single_order_cap_resolved"] is False
    assert market_snapshot["risk_limits"]["cap_usdt"] == 20.0
    assert preview["construction"]["cap_usdt"] == 20.0
    urls = [request.full_url for request in opener.requests]
    assert "category=linear&symbol=ETHUSDT" in urls[1]
    assert "category=linear&symbol=ETHUSDT" in urls[2]
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_atomic_runner_stops_after_public_quote_fail_closed(tmp_path) -> None:
    reroute = _reroute()
    reroute_path = tmp_path / "reroute.json"
    output_dir = tmp_path / "atomic"
    _write_json(reroute_path, reroute)
    clock = Clock()
    opener = FakeOpener(clock, retcode=10001)

    packet = run_atomic_quote_adapter_preview(
        reroute_review=reroute,
        reroute_review_path=reroute_path,
        output_dir=output_dir,
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
    )

    assert packet["status"] == QUOTE_NOT_READY_STATUS
    assert packet["statuses"]["public_quote"] == "PUBLIC_QUOTE_CAPTURE_SOURCE_FAILURE_NO_ORDER"
    assert packet["artifacts"]["public_quote"]["exists"] is True
    assert packet["artifacts"]["market_snapshot"]["exists"] is False
    assert packet["artifacts"]["construction_preview"]["exists"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_atomic_runner_stops_after_adapter_fail_closed(tmp_path) -> None:
    reroute = _reroute()
    reroute_path = tmp_path / "reroute.json"
    output_dir = tmp_path / "atomic"
    _write_json(reroute_path, reroute)
    clock = Clock()
    opener = FakeOpener(clock)

    packet = run_atomic_quote_adapter_preview(
        reroute_review=reroute,
        reroute_review_path=reroute_path,
        output_dir=output_dir,
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        cap_usdt=20.0,
    )

    assert packet["status"] == QUOTE_NOT_READY_STATUS
    assert packet["statuses"]["public_quote"] == quote_capture.INPUT_REQUIRED_STATUS
    public_quote = json.loads((output_dir / "public_quote.json").read_text())
    assert "cap_usdt_mismatch_reviewed_candidate_cap" in public_quote["blocking_gates"]
    assert packet["artifacts"]["public_quote"]["exists"] is True
    assert packet["artifacts"]["market_snapshot"]["exists"] is False
    assert packet["artifacts"]["construction_preview"]["exists"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_atomic_runner_rejects_latest_output_paths(tmp_path) -> None:
    reroute = _reroute()
    reroute_path = tmp_path / "reroute.json"
    _write_json(reroute_path, reroute)

    with pytest.raises(ValueError, match="must not contain latest"):
        run_atomic_quote_adapter_preview(
            reroute_review=reroute,
            reroute_review_path=reroute_path,
            output_dir=tmp_path / "atomic_latest",
        )


def test_atomic_runner_summary_outputs_must_stay_under_output_dir() -> None:
    output_dir = Path("/tmp/openclaw/atomic_runner_20260626T1045Z")

    assert _output_path_allowed(output_dir, output_dir) is False
    assert _output_path_allowed(output_dir, output_dir / "summary.json") is True
    assert _output_path_allowed(output_dir, output_dir / "nested" / "summary.md") is True
    assert _output_path_allowed(output_dir, Path("/tmp/openclaw/outside.json")) is False
    assert _output_path_allowed(output_dir, output_dir / "summary_latest.json") is False

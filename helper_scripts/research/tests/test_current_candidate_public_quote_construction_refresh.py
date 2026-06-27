from __future__ import annotations

import datetime as dt
import json

from cost_gate_learning_lane import bbo_freshness_public_quote_capture as quote_mod
from cost_gate_learning_lane import current_candidate_public_quote_construction_refresh as mod


START = dt.datetime(2026, 6, 27, 2, 20, tzinfo=dt.timezone.utc)
START_MS = int(START.timestamp() * 1000)


class Clock:
    def __init__(self, start_ms: int = START_MS):
        self.now_ms = start_ms

    def now(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(self.now_ms / 1000.0, tz=dt.timezone.utc)

    def monotonic(self) -> float:
        return self.now_ms / 1000.0

    def advance(self, ms: int) -> None:
        self.now_ms += ms


class FakeHTTPResponse:
    def __init__(self, payload: dict, *, status: int = 200):
        self.status = status
        self.headers = {"X-Bapi-Limit": "120"}
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self._raw


class FakeOpener:
    def __init__(self, clock: Clock, payloads: dict[str, dict] | None = None):
        self.clock = clock
        self.payloads = payloads or _payloads()
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        path = __import__("urllib.parse").parse.urlsplit(req.full_url).path
        self.clock.advance(10)
        if path not in self.payloads:
            raise AssertionError(f"unexpected path: {path}")
        return FakeHTTPResponse(self.payloads[path])


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
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


def _answers(**overrides) -> dict:
    payload = {
        "current_candidate_no_order_refresh_envelope_ready": True,
        "public_quote_capture_performed": False,
        "network_call_performed": False,
        "bybit_call_performed": False,
        "bybit_public_market_data_call_performed": False,
        "bybit_private_call_performed": False,
        "private_endpoint_called": False,
        "order_submission_performed": False,
        "order_admission_ready": False,
        "order_authority_granted": False,
        "probe_authority_granted": False,
        "live_authority_granted": False,
        "runtime_mutation_performed": False,
        "pg_write_performed": False,
        "global_cost_gate_lowering_recommended": False,
    }
    payload.update(overrides)
    return payload


def _required_requests(symbol: str = "AVAXUSDT") -> list[dict]:
    return [
        {
            "label": "server_time",
            "method": "GET",
            "path": quote_mod.TIME_PATH,
            "query": {},
        },
        {
            "label": "ticker",
            "method": "GET",
            "path": quote_mod.TICKERS_PATH,
            "query": {"category": "linear", "symbol": symbol},
        },
        {
            "label": "instrument",
            "method": "GET",
            "path": quote_mod.INSTRUMENTS_PATH,
            "query": {"category": "linear", "symbol": symbol},
        },
    ]


def _envelope(**overrides) -> dict:
    candidate = overrides.pop("candidate", _candidate())
    payload = {
        "schema_version": mod.CURRENT_ENVELOPE_SCHEMA_VERSION,
        "generated_at_utc": START.isoformat(),
        "status": mod.CURRENT_ENVELOPE_READY_STATUS,
        "candidate": candidate,
        "source_inputs": {
            "authority_preserved": True,
            "bounded_auth_no_authority": True,
        },
        "cap_resolution": {
            "risk_source_of_truth": "GUI-backed Rust RiskConfig",
            "account_equity_usdt": 9552.43426257,
            "per_trade_risk_pct_fraction": 0.1,
            "per_trade_risk_pct_display": 10.0,
            "position_size_max_pct": 25.0,
            "per_trade_budget_usdt": 955.24342626,
            "single_position_budget_usdt": 2388.10856564,
            "max_order_notional_usdt": 0.0,
            "resolved_cap_usdt": 955.24342626,
            "bounded_probe_local_cap_usdt_is_authority": False,
            "cap_formula": (
                "min(account_equity_usdt * per_trade_risk_pct, "
                "account_equity_usdt * position_size_max_pct / 100)"
            ),
        },
        "refresh_envelope": {
            "request_envelope_review": {
                "method": "GET",
                "required_requests": _required_requests(candidate["symbol"]),
                "allowed_base_urls": sorted(quote_mod.ALLOWED_BASE_URLS),
                "headers_allowlist": ["User-Agent"],
                "auth_or_cookie_headers_allowed": False,
                "private_or_order_paths_allowed": False,
                "redirects_allowed": False,
                "exact_query_required": True,
                "additional_requests_allowed": False,
            },
        },
        "summary": {
            "current_candidate_no_order_refresh_envelope_ready": True,
            "public_quote_capture_performed": False,
            "network_call_performed": False,
            "order_admission_ready": False,
            "request_count": 3,
            "max_fresh_bbo_age_ms": 1000,
            "resolved_cap_usdt": 955.24342626,
            "gui_p1_risk_trade_pct": 10.0,
            "local_10_usdt_cap_is_global_risk_authority": False,
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _payloads(
    *,
    symbol: str = "AVAXUSDT",
    bid: str = "6.044",
    ask: str = "6.045",
    bid_size: str = "120.0",
    ask_size: str = "110.0",
    last_price: str = "6.0445",
    mark_price: str = "6.0444",
    tick_size: str = "0.001",
    qty_step: str = "0.1",
    min_notional: str = "5",
    ticker_time_ms: int | None = START_MS + 20,
    instrument_status: str = "Trading",
) -> dict[str, dict]:
    return {
        quote_mod.TIME_PATH: {
            "retCode": 0,
            "retMsg": "OK",
            "result": {"timeSecond": str(int((START_MS + 10) / 1000))},
            "time": START_MS + 10,
        },
        quote_mod.TICKERS_PATH: {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": symbol,
                        "bid1Price": bid,
                        "ask1Price": ask,
                        "bid1Size": bid_size,
                        "ask1Size": ask_size,
                        "lastPrice": last_price,
                        "markPrice": mark_price,
                    }
                ],
            },
            "time": ticker_time_ms,
        },
        quote_mod.INSTRUMENTS_PATH: {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": symbol,
                        "status": instrument_status,
                        "priceFilter": {"tickSize": tick_size},
                        "lotSizeFilter": {
                            "qtyStep": qty_step,
                            "minNotionalValue": min_notional,
                        },
                    }
                ],
            },
            "time": START_MS + 30,
        },
    }


def _build(*, envelope=None, payloads=None, clock=None, **kwargs):
    clock = clock or Clock()
    opener = FakeOpener(clock, payloads)
    packet = mod.build_current_candidate_public_quote_construction_refresh(
        current_candidate_envelope=envelope or _envelope(),
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        **kwargs,
    )
    return packet, opener


def test_uses_gui_resolved_percent_cap_for_public_quote_and_construction() -> None:
    packet, opener = _build()

    assert packet["schema_version"] == mod.SCHEMA_VERSION
    assert packet["status"] == mod.READY_STATUS
    assert packet["summary"]["resolved_cap_usdt"] == 955.24342626
    assert packet["summary"]["local_10_usdt_cap_is_global_risk_authority"] is False
    assert packet["summary"]["order_admission_ready"] is False
    assert packet["public_quote"]["risk_limits"]["cap_usdt"] == 955.24342626
    assert packet["public_quote"]["risk_limits"]["cap_usdt"] != 10.0
    assert (
        packet["public_quote"]["risk_limits"]["effective_single_order_cap_usdt"]
        == 955.24342626
    )
    assert (
        packet["public_quote"]["risk_limits"]["single_position_budget_usdt"]
        == 2388.10856564
    )
    assert (
        packet["public_quote"]["risk_limits"]["cap_source"]
        == "current_candidate_envelope.cap_resolution.resolved_cap_usdt"
    )
    assert packet["market_snapshot"]["risk_limits"]["cap_usdt"] == 955.24342626
    assert (
        packet["market_snapshot"]["risk_limits"]["single_position_budget_usdt"]
        == 2388.10856564
    )
    assert packet["summary"]["per_trade_budget_usdt"] == 955.24342626
    assert packet["summary"]["single_position_budget_usdt"] == 2388.10856564
    assert packet["summary"]["position_size_max_pct"] == 25.0
    construction = packet["construction_preview"]["construction"]
    assert construction["constructible"] is True
    assert construction["cap_usdt"] == 955.24342626
    assert construction["limit_price"] == 6.045
    assert construction["rounded_notional_usdt"] <= 955.24342626
    assert packet["answers"]["bybit_public_market_data_call_performed"] is True
    assert packet["answers"]["bybit_private_call_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert len(opener.requests) == 3


def test_missing_single_position_budget_blocks_before_network() -> None:
    envelope = _envelope()
    envelope["cap_resolution"].pop("single_position_budget_usdt")

    packet, opener = _build(envelope=envelope)

    assert packet["status"] == mod.ENVELOPE_NOT_READY_STATUS
    assert "single_position_budget_usdt_missing_or_non_positive" in packet[
        "blocking_gates"
    ]
    assert packet["summary"]["network_call_performed"] is False
    assert len(opener.requests) == 0


def test_stale_current_candidate_envelope_blocks_before_network() -> None:
    old_envelope = _envelope(generated_at_utc=(START - dt.timedelta(hours=1)).isoformat())
    packet, opener = _build(envelope=old_envelope)

    assert packet["status"] == mod.ENVELOPE_NOT_READY_STATUS
    assert "current_candidate_envelope_stale" in packet["blocking_gates"]
    assert packet["summary"]["network_call_performed"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert len(opener.requests) == 0


def test_authority_contamination_blocks_before_network() -> None:
    envelope = _envelope(answers=_answers(order_authority_granted=True))
    packet, opener = _build(envelope=envelope)

    assert packet["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert "answers.order_authority_granted_true" in packet["blocking_gates"]
    assert packet["summary"]["network_call_performed"] is False
    assert len(opener.requests) == 0


def test_stale_bbo_blocks_construction_even_with_gui_cap() -> None:
    packet, opener = _build(payloads=_payloads(ticker_time_ms=START_MS - 5000))

    assert packet["status"] == mod.STALE_BBO_STATUS
    assert "bbo_freshness_exceeds_gate" in packet["blocking_gates"]
    assert packet["summary"]["request_count"] == 3
    assert packet["construction_preview"]["status"] == mod.CONSTRUCTION_NOT_READY_STATUS
    assert packet["summary"]["order_admission_ready"] is False
    assert len(opener.requests) == 3


def test_request_envelope_private_path_blocks_before_network() -> None:
    envelope = _envelope()
    envelope["refresh_envelope"]["request_envelope_review"]["required_requests"][1][
        "path"
    ] = "/v5/order/create"
    packet, opener = _build(envelope=envelope)

    assert packet["status"] == mod.ENVELOPE_NOT_READY_STATUS
    assert "request_envelope_ticker_path_mismatch" in packet["blocking_gates"]
    assert "request_envelope_ticker_private_or_order_path" in packet["blocking_gates"]
    assert packet["summary"]["network_call_performed"] is False
    assert len(opener.requests) == 0

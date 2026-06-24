from __future__ import annotations

import datetime as dt
import json
import socket
import sys
import urllib.error
from pathlib import Path

from cost_gate_learning_lane import bbo_freshness_public_quote_capture as mod
from cost_gate_learning_lane.bounded_probe_candidate_construction_preview import (
    build_candidate_construction_preview,
)


START = dt.datetime(2026, 6, 24, 19, 30, tzinfo=dt.timezone.utc)
START_MS = int(START.timestamp() * 1000)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


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
    def __init__(self, payload=None, *, raw=None, status=200, headers=None):
        self.status = status
        self.headers = headers or {"X-Bapi-Limit": "120"}
        self._raw = raw if raw is not None else json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self._raw


class FakeOpener:
    def __init__(self, clock: Clock, *, payloads=None, raw_by_path=None, exc_by_path=None):
        self.clock = clock
        self.payloads = payloads or _payloads()
        self.raw_by_path = raw_by_path or {}
        self.exc_by_path = exc_by_path or {}
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        path = __import__("urllib.parse").parse.urlsplit(req.full_url).path
        self.clock.advance(10)
        if path in self.exc_by_path:
            raise self.exc_by_path[path]
        if path in self.raw_by_path:
            return FakeHTTPResponse(raw=self.raw_by_path[path])
        if path not in self.payloads:
            raise AssertionError(f"unexpected path: {path}")
        return FakeHTTPResponse(self.payloads[path])


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    return payload


def _reroute(candidate=None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_lower_price_reroute_review_v1",
        "generated_at_utc": "2026-06-24T19:30:00+00:00",
        "status": "LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW",
        "selected_candidate": {
            **(candidate or _candidate()),
            "false_negative_rank": 1,
            "avg_net_bps": 73.5511,
            "current_cap_usdt": 10.0,
            "instrument_status": "Trading",
        },
        "answers": {
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _payloads(
    *,
    ticker_time_ms: int | None = START_MS + 20,
    rows=None,
    instrument_status="Trading",
    retcode=0,
) -> dict:
    ticker_rows = rows if rows is not None else [
        {
            "symbol": "AVAXUSDT",
            "bid1Price": "6.044",
            "ask1Price": "6.045",
            "bid1Size": "120.0",
            "ask1Size": "110.0",
            "lastPrice": "6.0445",
            "markPrice": "6.0444",
        }
    ]
    return {
        mod.TIME_PATH: {
            "retCode": retcode,
            "retMsg": "OK" if retcode == 0 else "bad",
            "result": {"timeSecond": str(int((START_MS + 10) / 1000))},
            "time": START_MS + 10,
        },
        mod.TICKERS_PATH: {
            "retCode": retcode,
            "retMsg": "OK" if retcode == 0 else "bad",
            "result": {"category": "linear", "list": ticker_rows},
            "time": ticker_time_ms,
        },
        mod.INSTRUMENTS_PATH: {
            "retCode": retcode,
            "retMsg": "OK" if retcode == 0 else "bad",
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": "AVAXUSDT",
                        "status": instrument_status,
                        "priceFilter": {"tickSize": "0.001"},
                        "lotSizeFilter": {
                            "qtyStep": "0.1",
                            "minNotionalValue": "5",
                        },
                    }
                ],
            },
            "time": START_MS + 30,
        },
    }


def _capture(*, payloads=None, **kwargs):
    clock = kwargs.pop("clock", Clock())
    opener = kwargs.pop("opener", FakeOpener(clock, payloads=payloads))
    packet = mod.capture_public_quote(
        reroute_review=kwargs.pop("reroute_review", _reroute()),
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
        **kwargs,
    )
    return packet, opener


def test_happy_path_emits_public_quote_ready_no_order() -> None:
    packet, opener = _capture()

    assert packet["schema_version"] == mod.PUBLIC_QUOTE_CAPTURE_SCHEMA_VERSION
    assert packet["status"] == mod.READY_STATUS
    assert packet["candidate"]["side_cell_key"] == SIDE_CELL
    assert packet["parsed"]["ticker"]["bid1Price"] == 6.044
    assert packet["derived"]["bbo_fresh"] is True
    assert packet["derived"]["effective_bbo_age_ms"] == 20.0
    assert packet["answers"]["bybit_call_performed"] is True
    assert packet["answers"]["bybit_public_market_data_call_performed"] is True
    assert packet["answers"]["bybit_private_call_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert len(opener.requests) == 3
    assert packet["requests"][1]["raw_response_sha256"]
    assert packet["requests"][1]["normalized_response_sha256"]
    assert packet["artifact_self_hash_sha256"]


def test_redirect_is_refused_and_fails_closed_no_order() -> None:
    clock = Clock()
    exc = urllib.error.HTTPError(
        f"{mod.DEFAULT_BASE_URL}{mod.TICKERS_PATH}",
        302,
        "Found",
        {"Location": "https://example.com"},
        None,
    )
    opener = FakeOpener(clock, exc_by_path={mod.TICKERS_PATH: exc})

    packet, _ = _capture(clock=clock, opener=opener)

    assert packet["status"] == mod.SOURCE_FAILURE_STATUS
    assert "redirect_refused" in packet["blocking_gates"]
    assert packet["requests"][1]["redirect_refused"] is True
    assert packet["answers"]["order_submission_performed"] is False


def test_wrong_host_non_get_wrong_query_and_auth_headers_are_rejected() -> None:
    packet, opener = _capture(base_url="https://evil.example")

    assert packet["status"] == mod.INPUT_REQUIRED_STATUS
    assert "base_url_not_allowlisted" in packet["blocking_gates"]
    assert opener.requests == []
    ok, reasons, _details = mod._validate_request_envelope(
        url=f"{mod.DEFAULT_BASE_URL}{mod.TICKERS_PATH}?category=spot&symbol=AVAXUSDT",
        method="POST",
        expected_path=mod.TICKERS_PATH,
        expected_params={"category": "linear", "symbol": "AVAXUSDT"},
        headers={"X-BAPI-API-KEY": "secret"},
    )
    assert ok is False
    assert "method_not_get" in reasons
    assert "query_not_exact_allowlist" in reasons
    assert "auth_or_cookie_header_present:x-bapi-api-key" in reasons

    packet, opener = _capture(extra_headers={"X-BAPI-API-KEY": "secret"})
    assert packet["status"] == mod.INPUT_REQUIRED_STATUS
    assert packet["answers"]["auth_headers_present"] is True
    assert opener.requests == []


def test_http_error_malformed_json_and_retcode_fail_closed() -> None:
    for opener in [
        FakeOpener(
            Clock(),
            exc_by_path={
                mod.TIME_PATH: urllib.error.HTTPError(
                    f"{mod.DEFAULT_BASE_URL}{mod.TIME_PATH}",
                    500,
                    "server error",
                    {},
                    None,
                )
            },
        ),
        FakeOpener(Clock(), raw_by_path={mod.TIME_PATH: b"not-json"}),
        FakeOpener(Clock(), payloads=_payloads(retcode=10001)),
    ]:
        packet = mod.capture_public_quote(
            reroute_review=_reroute(),
            opener=opener,
            now_fn=opener.clock.now,
            monotonic_fn=opener.clock.monotonic,
        )
        assert packet["status"] == mod.SOURCE_FAILURE_STATUS
        assert packet["answers"]["order_submission_performed"] is False


def test_transport_urlerror_records_sanitized_reason_details() -> None:
    clock = Clock()
    reason = (
        "temporary failure BYBIT_API_KEY=abc123 OPENCLAW_LIVE_PATCH_SECRET=def456 "
        "X-BAPI-API-KEY=ghi789 Authorization: Bearer deadbeef "
        "DATABASE_URL=postgres://user:pass@db postgres://bare:dsn@db/app "
        "/Users/ncyu/Projects/TradeBot/secrets.txt "
        "/tmp/openclaw/secrets.json /var/log/openclaw/private.log "
        "https://evil.example/path "
        "https://api.bybit.com/v5/market/tickers?category=linear&symbol=AVAXUSDT#frag "
        "https://user:pass@api.bybit.com/v5/market/time"
    )
    opener = FakeOpener(
        clock,
        exc_by_path={mod.TIME_PATH: urllib.error.URLError(reason)},
    )

    packet = mod.capture_public_quote(
        reroute_review=_reroute(),
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
    )
    request = packet["requests"][0]
    sanitized = request["transport_error_reason_sanitized"]

    assert packet["status"] == mod.SOURCE_FAILURE_STATUS
    assert request["error"] == "transport_error:URLError"
    assert request["transport_error_class"] == "URLError"
    assert request["transport_error_reason_type"] == "str"
    assert request["transport_error_errno"] is None
    assert request["transport_error_stage"] == "opener"
    assert request["transport_error_sanitized"] is True
    assert "abc123" not in sanitized
    assert "def456" not in sanitized
    assert "ghi789" not in sanitized
    assert "deadbeef" not in sanitized
    assert "user:pass" not in sanitized
    assert "bare:dsn" not in sanitized
    assert "/Users/ncyu" not in sanitized
    assert "/tmp/openclaw" not in sanitized
    assert "/var/log" not in sanitized
    assert "evil.example" not in sanitized
    assert "category=linear" not in sanitized
    assert "#frag" not in sanitized
    assert "user:pass@api.bybit.com" not in sanitized
    assert "<redacted>" in sanitized
    assert "<path-redacted>" in sanitized
    assert "<url-redacted>" in sanitized
    assert len(opener.requests) == 3
    answers = packet["answers"]
    for key in [
        "bybit_private_call_performed",
        "pg_write_performed",
        "order_submission_performed",
        "probe_authority_granted",
        "order_authority_granted",
        "live_authority_granted",
        "promotion_evidence",
    ]:
        assert answers[key] is False
    assert answers["main_cost_gate_adjustment"] == "NONE"


def test_transport_cookie_diagnostics_redact_through_line() -> None:
    clock = Clock()
    reason = "temporary failure Cookie: session=secret, csrf=tok; Path=/, Set-Cookie: id=abc"
    opener = FakeOpener(clock, exc_by_path={mod.TIME_PATH: urllib.error.URLError(reason)})

    packet = mod.capture_public_quote(
        reroute_review=_reroute(),
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
    )
    sanitized = packet["requests"][0]["transport_error_reason_sanitized"]

    assert "session=secret" not in sanitized
    assert "csrf=tok" not in sanitized
    assert "Path=/" not in sanitized
    assert "id=abc" not in sanitized
    assert sanitized == "temporary failure Cookie=<redacted>"


def test_transport_url_sanitizer_preserves_only_allowlisted_bybit_public_paths() -> None:
    clock = Clock()
    reason = (
        "url https://api.bybit.com/v5/market/tickers?category=linear&symbol=AVAXUSDT#frag "
        "bad https://user:pass@api.bybit.com/v5/market/time "
        "demo https://api-demo.bybit.com/v5/market/tickers?category=linear&symbol=AVAXUSDT "
        "other https://api.bybit.com/v5/order/create"
    )
    opener = FakeOpener(clock, exc_by_path={mod.TIME_PATH: urllib.error.URLError(reason)})

    packet = mod.capture_public_quote(
        reroute_review=_reroute(),
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
    )
    sanitized = packet["requests"][0]["transport_error_reason_sanitized"]

    assert "https://api.bybit.com/v5/market/tickers" in sanitized
    assert "category=linear" not in sanitized
    assert "#frag" not in sanitized
    assert "user:pass" not in sanitized
    assert "api-demo.bybit.com" not in sanitized
    assert "/v5/order/create" not in sanitized
    assert "<url-redacted>" in sanitized


def test_transport_exception_reason_shapes_are_structured_and_fail_closed() -> None:
    cases = [
        (
            urllib.error.URLError(socket.timeout("timed out token=secret")),
            "URLError",
            {"TimeoutError", "timeout"},
            None,
        ),
        (TimeoutError("timed out password=secret"), "TimeoutError", "TimeoutError", None),
        (
            urllib.error.URLError(socket.gaierror(8, "nodename nor servname")),
            "URLError",
            "gaierror",
            8,
        ),
        (OSError(12345, "generic failure"), "OSError", "OSError", 12345),
    ]

    for exc, expected_class, expected_reason_type, expected_errno in cases:
        clock = Clock()
        opener = FakeOpener(clock, exc_by_path={mod.TICKERS_PATH: exc})
        packet = mod.capture_public_quote(
            reroute_review=_reroute(),
            opener=opener,
            now_fn=clock.now,
            monotonic_fn=clock.monotonic,
        )
        request = packet["requests"][1]

        assert packet["status"] == mod.SOURCE_FAILURE_STATUS
        assert request["error"] == f"transport_error:{expected_class}"
        assert request["transport_error_class"] == expected_class
        if isinstance(expected_reason_type, set):
            assert request["transport_error_reason_type"] in expected_reason_type
        else:
            assert request["transport_error_reason_type"] == expected_reason_type
        assert request["transport_error_errno"] == expected_errno
        assert request["transport_error_stage"] == "opener"
        assert request["transport_error_sanitized"] is True
        assert "secret" not in str(request["transport_error_reason_sanitized"])
        assert packet["answers"]["order_submission_performed"] is False


def test_ticker_row_and_bbo_validation_fail_closed() -> None:
    cases = [
        _payloads(rows=[]),
        _payloads(rows=[
            {
                "symbol": "AVAXUSDT",
                "bid1Price": "6.044",
                "ask1Price": "6.045",
                "bid1Size": "1",
                "ask1Size": "1",
            },
            {
                "symbol": "AVAXUSDT",
                "bid1Price": "6.044",
                "ask1Price": "6.045",
                "bid1Size": "1",
                "ask1Size": "1",
            },
        ]),
        _payloads(rows=[
            {
                "symbol": "DOGEUSDT",
                "bid1Price": "6.044",
                "ask1Price": "6.045",
                "bid1Size": "1",
                "ask1Size": "1",
            }
        ]),
        _payloads(rows=[
            {
                "symbol": "AVAXUSDT",
                "bid1Price": "6.045",
                "ask1Price": "6.044",
                "bid1Size": "1",
                "ask1Size": "1",
            }
        ]),
    ]

    for payloads in cases:
        packet, _ = _capture(payloads=payloads)
        assert packet["status"] == mod.SOURCE_FAILURE_STATUS
        assert packet["answers"]["order_submission_performed"] is False


def test_stale_and_future_ticker_time_fail_closed() -> None:
    stale, _ = _capture(payloads=_payloads(ticker_time_ms=START_MS - 2000))
    future, _ = _capture(payloads=_payloads(ticker_time_ms=START_MS + 5000))

    assert stale["status"] == mod.STALE_STATUS
    assert "bbo_freshness_exceeds_gate" in stale["blocking_gates"]
    assert future["status"] == mod.SOURCE_FAILURE_STATUS
    assert "ticker_time_future_or_clock_ambiguous" in future["blocking_gates"]


def test_instrument_non_trading_or_malformed_fails_closed() -> None:
    non_trading, _ = _capture(payloads=_payloads(instrument_status="PreLaunch"))
    malformed_payloads = _payloads()
    malformed_payloads[mod.INSTRUMENTS_PATH]["result"]["list"][0]["lotSizeFilter"] = {
        "qtyStep": "0.1"
    }
    malformed, _ = _capture(payloads=malformed_payloads)

    assert non_trading["status"] == mod.SOURCE_FAILURE_STATUS
    assert "instrument_status_not_trading" in non_trading["blocking_gates"]
    assert malformed["status"] == mod.SOURCE_FAILURE_STATUS
    assert "instrument_min_notional_missing_or_nonpositive" in malformed["blocking_gates"]


def test_authority_contamination_blocks_before_public_call() -> None:
    clock = Clock()
    opener = FakeOpener(clock)
    packet = mod.capture_public_quote(
        reroute_review=_reroute(order_authority="DEMO_ORDER_GRANTED"),
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
    )

    assert packet["status"] == mod.AUTHORITY_VIOLATION_STATUS
    assert "order_authority_contaminating" in packet["authority_contamination_reasons"]
    assert packet["answers"]["bybit_call_performed"] is False
    assert opener.requests == []

    packet = mod.capture_public_quote(
        reroute_review=_reroute(),
        authority_inputs={"pg_write_performed": True},
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
    )
    assert packet["status"] == mod.AUTHORITY_VIOLATION_STATUS
    assert "pg_write_performed_contaminating" in packet["authority_contamination_reasons"]


def test_cli_uses_injectable_opener_and_writes_artifact(tmp_path, monkeypatch) -> None:
    clock = Clock()
    opener = FakeOpener(clock)
    reroute_path = tmp_path / "reroute.json"
    out_path = tmp_path / "quote.json"
    reroute_path.write_text(json.dumps(_reroute()), encoding="utf-8")
    monkeypatch.setattr(mod, "urlopen_no_redirect", opener)
    monkeypatch.setattr(mod, "_utc_now", clock.now)
    monkeypatch.setattr(mod.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bbo_freshness_public_quote_capture",
            "--reroute-review-json",
            str(reroute_path),
            "--json-output",
            str(out_path),
        ],
    )

    assert mod.main() == 0
    packet = json.loads(out_path.read_text(encoding="utf-8"))
    assert packet["status"] == mod.READY_STATUS
    assert len(opener.requests) == 3
    assert all("api.bybit.com" in req.full_url for req in opener.requests)


def test_existing_pg_construction_preview_still_rejects_bybit_call_snapshot() -> None:
    market = {
        "schema_version": "bounded_probe_candidate_market_snapshot_v1",
        "generated_at_utc": START.isoformat(),
        "pg_snapshot_timestamp": START.isoformat(),
        "source": "read_only_pg:market.market_tickers+market.symbol_universe_snapshots",
        "candidate": _candidate(),
        "risk_limits": {"cap_usdt": 10.0, "max_fresh_bbo_age_ms": 1000},
        "ticker": {
            "ts": (START - dt.timedelta(milliseconds=100)).isoformat(),
            "symbol": "AVAXUSDT",
            "last_price": 6.0445,
            "mark_price": 6.0444,
            "best_bid": 6.044,
            "best_ask": 6.045,
            "spread_bps": 1.654,
        },
        "instrument": {
            "ts": START.isoformat(),
            "category": "linear",
            "symbol": "AVAXUSDT",
            "status": "Trading",
            "tick_size": 0.001,
            "qty_step": 0.1,
            "min_notional": 5.0,
        },
        "derived": {
            "bbo_age_ms": 100.0,
            "instrument_status": "Trading",
            "best_bid": 6.044,
            "best_ask": 6.045,
            "spread_bps": 1.654,
            "tick_size": 0.001,
            "qty_step": 0.1,
            "min_notional": 5.0,
        },
        "answers": {
            "pg_query_performed": True,
            "pg_write_performed": False,
            "bybit_call_performed": True,
            "order_submission_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "promotion_evidence": False,
        },
    }

    packet = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=market,
        demo_operational_authorization_available=True,
        now_utc=START,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "bybit_call_performed_contaminating" in packet[
        "authority_contamination_reasons"
    ]


def test_public_quote_artifact_cannot_satisfy_pg_construction_preview_input() -> None:
    clock = Clock()
    opener = FakeOpener(clock)
    public_quote = mod.capture_public_quote(
        reroute_review=_reroute(),
        opener=opener,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
    )

    packet = build_candidate_construction_preview(
        reroute_review=_reroute(),
        market_snapshot=public_quote,
        demo_operational_authorization_available=True,
        now_utc=START,
    )

    assert public_quote["status"] == mod.READY_STATUS
    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "bybit_call_performed_contaminating" in packet[
        "authority_contamination_reasons"
    ]
    assert "market_snapshot_ready" in packet["blocking_gates"]

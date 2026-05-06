from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from typing import Any


_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from replay.bybit_public_client import (  # noqa: E402
    ReplayBybitPublicClient,
    ReplayBybitPublicClientError,
    current_replay_public_rate_policy,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class _FakeUrlOpen:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[str] = []

    def __call__(self, request: Any, timeout: float) -> _FakeResponse:
        self.requests.append(request.full_url)
        if not self.responses:
            raise AssertionError("unexpected extra replay Bybit request")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _FakeResponse(item)


def _ok_payload(ts: int = 1_700_000_000_000) -> dict[str, Any]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "list": [
                [str(ts), "100", "110", "90", "105", "12.5"],
            ]
        },
    }


def test_replay_public_rate_policy_defaults_stay_under_ref21_ceiling(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_REPLAY_PUBLIC_GLOBAL_RPS", raising=False)
    monkeypatch.delenv("OPENCLAW_REPLAY_PUBLIC_KLINE_RPS", raising=False)
    monkeypatch.delenv("OPENCLAW_REPLAY_PUBLIC_TICKER_RPS", raising=False)
    monkeypatch.delenv("OPENCLAW_REPLAY_PUBLIC_ORDERBOOK_RPS", raising=False)

    policy = current_replay_public_rate_policy()

    assert policy.global_rps <= 50.0
    assert policy.kline_rps < policy.global_rps
    assert policy.kline_rps == 20.0
    assert policy.ticker_rps == 5.0
    assert policy.orderbook_rps == 10.0


def test_replay_public_rate_policy_clamps_operator_overrides(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_PUBLIC_GLOBAL_RPS", "500")
    monkeypatch.setenv("OPENCLAW_REPLAY_PUBLIC_KLINE_RPS", "500")
    monkeypatch.setenv("OPENCLAW_REPLAY_PUBLIC_TICKER_RPS", "500")
    monkeypatch.setenv("OPENCLAW_REPLAY_PUBLIC_ORDERBOOK_RPS", "500")

    policy = current_replay_public_rate_policy()

    assert policy.global_rps == 50.0
    assert policy.kline_rps == 49.0
    assert policy.ticker_rps == 50.0
    assert policy.orderbook_rps == 50.0


def test_replay_public_client_fetches_and_parses_kline_rows(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_PUBLIC_GLOBAL_RPS", "50")
    fake = _FakeUrlOpen([_ok_payload()])
    client = ReplayBybitPublicClient(
        urlopen=fake,
        sleeper=lambda _: None,
        monotonic=lambda: 0.0,
    )

    rows = client.fetch_klines_sync(
        symbol="BTCUSDT",
        category="linear",
        timeframe="1m",
        start_ms=1_699_999_999_000,
        end_ms=1_700_000_001_000,
        max_bars=10,
    )

    assert rows == [
        {
            "ts_ms": 1_700_000_000_000,
            "symbol": "BTCUSDT",
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 12.5,
            "turnover": None,
        }
    ]
    assert len(fake.requests) == 1
    assert fake.requests[0].startswith("https://api.bybit.com/v5/market/kline?")


def test_replay_public_client_retries_429_then_succeeds(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_PUBLIC_RETRY_MAX_ATTEMPTS", "2")
    sleeps: list[float] = []
    fake = _FakeUrlOpen([
        urllib.error.HTTPError(
            url="https://api.bybit.com/v5/market/kline",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        ),
        _ok_payload(),
    ])
    client = ReplayBybitPublicClient(
        urlopen=fake,
        sleeper=sleeps.append,
        monotonic=lambda: 0.0,
    )

    rows = client.fetch_klines_sync(
        symbol="ETHUSDT",
        category="linear",
        timeframe="1m",
        start_ms=1_699_999_999_000,
        end_ms=1_700_000_001_000,
        max_bars=10,
    )

    assert len(rows) == 1
    assert len(fake.requests) == 2
    assert sleeps


def test_replay_public_client_preserves_kline_turnover(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_PUBLIC_GLOBAL_RPS", "50")
    fake = _FakeUrlOpen([
        {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    [
                        "1700000000000",
                        "100",
                        "110",
                        "90",
                        "105",
                        "12.5",
                        "1312.5",
                    ],
                ]
            },
        }
    ])
    client = ReplayBybitPublicClient(
        urlopen=fake,
        sleeper=lambda _: None,
        monotonic=lambda: 0.0,
    )

    rows = client.fetch_klines_sync(
        symbol="BTCUSDT",
        category="linear",
        timeframe="1m",
        start_ms=1_699_999_999_000,
        end_ms=1_700_000_001_000,
        max_bars=10,
    )

    assert rows[0]["turnover"] == 1312.5


def test_replay_public_client_rejects_non_allowlisted_endpoint(
    monkeypatch,
) -> None:
    fake = _FakeUrlOpen([])
    client = ReplayBybitPublicClient(
        urlopen=fake,
        sleeper=lambda _: None,
        monotonic=lambda: 0.0,
    )

    try:
        client._request_json("/v5/private/order", {})  # noqa: SLF001
    except ReplayBybitPublicClientError as exc:
        assert "replay_bybit_endpoint_not_allowed" in str(exc)
    else:
        raise AssertionError("non-allowlisted replay endpoint should fail closed")


def test_replay_public_client_fetches_current_ticker_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_PUBLIC_GLOBAL_RPS", "50")
    fake = _FakeUrlOpen([
        {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "100",
                        "bid1Price": "99.9",
                        "ask1Price": "100.1",
                    }
                ]
            },
        }
    ])
    client = ReplayBybitPublicClient(
        urlopen=fake,
        sleeper=lambda _: None,
        monotonic=lambda: 0.0,
    )

    rows = client.fetch_tickers_sync(category="linear", symbol="BTCUSDT")

    assert rows[0]["symbol"] == "BTCUSDT"
    assert "/v5/market/tickers?" in fake.requests[0]
    assert "symbol=BTCUSDT" in fake.requests[0]


def test_replay_public_client_fetches_current_orderbook_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_REPLAY_PUBLIC_GLOBAL_RPS", "50")
    fake = _FakeUrlOpen([
        {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "s": "BTCUSDT",
                "b": [["99.9", "2.0"]],
                "a": [["100.1", "1.5"]],
                "ts": 1_700_000_000_123,
            },
        }
    ])
    client = ReplayBybitPublicClient(
        urlopen=fake,
        sleeper=lambda _: None,
        monotonic=lambda: 0.0,
    )

    row = client.fetch_orderbook_sync(category="linear", symbol="BTCUSDT", limit=5)

    assert row["s"] == "BTCUSDT"
    assert row["b"][0] == ["99.9", "2.0"]
    assert "/v5/market/orderbook?" in fake.requests[0]
    assert "limit=5" in fake.requests[0]

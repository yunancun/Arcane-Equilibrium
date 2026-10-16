"""U1 的純離線契約測試；原始回應均為合成樣本。"""
import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path
import socket
import sys

import pytest

from program_code.research.r8_data import public_data as mod


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("測試禁止任何網路連線")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


class Clock:
    def __init__(self):
        self.value = 0.0
    def __call__(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


def response(rows=(), cursor="", code=0):
    return 200, mod.encoded({"retCode": code, "result": {"list": list(rows), "nextPageCursor": cursor}})


def instrument(symbol="BTCUSDT", status="Trading", funding=240):
    return {"symbol": symbol, "contractType": "LinearPerpetual", "settleCoin": "USDT", "status": status,
            "launchTime": "1640995200000", "fundingInterval": str(funding)}


def kline(t, close="1"):
    return [str(t), "1", "2", "0.5", close, "10", "15"]


@pytest.fixture
def plan_path(tmp_path):
    value = json.loads((Path(mod.__file__).parent / "stage2_plan.json").read_text())
    value["end"] = "2022-01-02T00:00:00Z"
    path = tmp_path / "plan.json"
    path.write_bytes(mod.encoded(value))
    return path


def collector(plan_path, tmp_path, send):
    clock = Clock()
    return mod.Collector(mod.Plan(plan_path), tmp_path / "out", send=send, clock=clock, sleep=clock.sleep,
                         now=lambda: "2026-10-16T00:00:00Z")


def universe_sender(endpoint, params):
    assert endpoint == mod.INSTRUMENTS
    assert params["limit"] == 1000
    return response([] if params.get("status") else [instrument()])


def test_universe_paginates_and_records_observed_filter(plan_path, tmp_path):
    calls = []
    def send(endpoint, params):
        calls.append(params)
        if params.get("status"):
            return response([instrument("OLDUSDT", "Closed")])
        return response([instrument("ETHUSDT")]) if params.get("cursor") else response([instrument()], "page2")
    c = collector(plan_path, tmp_path, send)
    assert set(c.fetch_universe()) == {"BTCUSDT", "ETHUSDT", "OLDUSDT"}
    assert calls[1]["cursor"] == "page2"
    assert len(c.manifest["universe_request_ids"]) == 3
    assert c.manifest["filtering"]["observed_values"]["status"] == ["Closed", "Trading"]
    assert c.manifest["delistings"]["obtained"] == 1
    assert c.manifest["delistings"]["point_in_time_universe_complete"] is False
    assert c.manifest["delistings"]["cross_sectional_candidate_allowed"] is False
    assert c.client.records[1]["pagination"] == {"page": 2, "parent_request_id": 1, "cursor": "page2", "window": {}}
    for row in c.client.records:
        assert hashlib.sha256((c.out / "raw" / (str(row["request_id"]) + ".json")).read_bytes()).hexdigest() == row["raw_sha256"]


@pytest.mark.parametrize("mode", ["repeat", "limit", "missing_cursor"])
def test_instruments_incomplete_pagination_fails(plan_path, tmp_path, mode):
    value = json.loads(plan_path.read_text()); value["universe_max_pages"] = 1 if mode == "limit" else 3
    plan_path.write_bytes(mod.encoded(value))
    def send(*args):
        if mode == "missing_cursor":
            return 200, mod.encoded({"retCode": 0, "result": {"list": [instrument()]}})
        return response([instrument()], "same")
    with pytest.raises(mod.DataError):
        collector(plan_path, tmp_path, send).fetch_universe()


def test_probe_error_recorded_once_and_not_claimed_complete_history(plan_path, tmp_path):
    calls = []
    def send(endpoint, params):
        calls.append(params)
        return response(code=10001) if "status" in params else response([instrument()])
    c = collector(plan_path, tmp_path, send); c.fetch_universe(); c.fetch_universe()
    assert sum("status" in p for p in calls) == 1
    assert c.manifest["delistings"]["probe_status"] == "REQUEST_FAILED"
    assert c.client.records[-1]["retCode"] == 10001


@pytest.mark.parametrize("changes", [
    {"base_url": "https://example.com"}, {"max_rps": 5}, {"max_attempts": 6},
    {"end": "2027-01-01T00:00:00Z"}, {"start": "2021-01-01T00:00:00Z"},
])
def test_plan_cannot_expand_authorized_scope(plan_path, changes):
    value = json.loads(plan_path.read_text()); value.update(changes); plan_path.write_bytes(mod.encoded(value))
    with pytest.raises(mod.DataError):
        mod.Plan(plan_path)


def test_whitelist_rejects_endpoint_auth_extra_params_and_scope(plan_path, tmp_path):
    c = collector(plan_path, tmp_path, universe_sender); c.fetch_universe()
    base = {"category": "linear", "limit": 1000, "symbol": "BTCUSDT", "interval": "60", "start": c.plan.start, "end": c.plan.end-1}
    c.plan.authorize(mod.ENDPOINTS["kline"], base, c.universe)
    for endpoint, params in [
        ("/v5/order/create", base), (mod.ENDPOINTS["kline"], {**base, "api_key": "fake"}),
        (mod.ENDPOINTS["kline"], {**base, "limit": 200}), (mod.ENDPOINTS["kline"], {**base, "symbol": "UNKNOWN"}),
        (mod.ENDPOINTS["kline"], {**base, "end": c.plan.end}), (mod.ENDPOINTS["kline"], {**base, "start": c.plan.start-1}),
        (mod.ENDPOINTS["kline"], {**base, "interval": "5"}),
    ]:
        with pytest.raises(mod.DataError):
            c.plan.authorize(endpoint, params, c.universe)


@pytest.mark.parametrize("name,rows", [
    ("kline", [["1640995200000", "1"]]),
    ("kline", [kline(1640995200000, "NaN")]),
    ("funding", [{"symbol": "BTCUSDT", "fundingRateTimestamp": "1640995200000"}]),
    ("funding", [{"symbol": "BTCUSDT", "fundingRateTimestamp": "1640995200000", "fundingRate": "Infinity"}]),
    ("open_interest", [{"timestamp": "1.5", "openInterest": "1"}]),
    ("open_interest", [{"timestamp": True, "openInterest": "1"}]),
    ("open_interest", [{"timestamp": "1640995200000", "openInterest": None}]),
])
def test_strict_parser_rejects_bad_fields(name, rows):
    with pytest.raises(mod.DataError):
        mod.parse_rows(name, rows, symbol="BTCUSDT", start=1640995200000, end=1641081600000, interval="60", now_ms=2000000000000)


def test_funding_zero_and_negative_are_valid():
    start = 1640995200000
    rows = [{"symbol": "BTCUSDT", "fundingRateTimestamp": str(start+i*14400000), "fundingRate": rate} for i,rate in enumerate(("0", "-0.001"))]
    assert mod.parse_rows("funding", rows, symbol="BTCUSDT", start=start, end=start+86400000, interval="funding", now_ms=2000000000000) == [(start, 0.0), (start+14400000, -0.001)]


def test_kline_reverse_order_dedup_and_open_candle_removed():
    start = 1640995200000
    parsed = mod.parse_rows("kline", [kline(start+7200000), kline(start+3600000), kline(start), kline(start)], symbol="BTCUSDT", start=start, end=start+86400000, interval="60", now_ms=start+8000000)
    assert [r[0] for r in parsed] == [start, start+3600000]


def test_rate_limit_is_global_between_endpoints(plan_path, tmp_path):
    times = []; clock = Clock()
    def send(endpoint, params):
        times.append(clock()); return response([instrument()])
    c = mod.Client(mod.Plan(plan_path), tmp_path / "rate", send=send, clock=clock, sleep=clock.sleep)
    for _ in range(6):
        c.request(mod.INSTRUMENTS, {"category": "linear", "limit": 1000})
    assert times == pytest.approx([0, .25, .5, .75, 1, 1.25])


@pytest.mark.parametrize("status", [429, 500, 503, "network"])
def test_retry_exhaustion_is_bounded_and_logged(plan_path, tmp_path, status):
    calls = []
    def send(*args):
        calls.append(1)
        if status == "network":
            raise OSError("offline synthetic")
        return status, b'{}'
    c = collector(plan_path, tmp_path, send)
    with pytest.raises(mod.RequestFailed):
        c.fetch_universe()
    assert len(calls) == 5
    assert len(c.client.records) == 5
    assert c.client.clock() >= 15


@pytest.mark.parametrize("status,code", [(400, 0), (401, 0), (404, 0), (200, 10001)])
def test_nonretryable_errors_are_not_retried(plan_path, tmp_path, status, code):
    calls = []
    def send(*args):
        calls.append(1); return status, response(code=code)[1]
    with pytest.raises(mod.RequestFailed):
        collector(plan_path, tmp_path, send).fetch_universe()
    assert len(calls) == 1


def test_403_stops_entire_client_and_other_requests(plan_path, tmp_path):
    calls = []
    def send(*args):
        calls.append(1); return 403, b'{}'
    c = collector(plan_path, tmp_path, send)
    with pytest.raises(mod.Forbidden): c.fetch_universe()
    with pytest.raises(mod.Forbidden): c.client.request(mod.INSTRUMENTS, {"category": "linear", "limit": 1000})
    assert len(calls) == 1


@pytest.mark.parametrize("period,funding", [(3600000, False), (14400000, True), (14400000, False)])
def test_gap_detection_including_four_hour_funding(period, funding):
    start = 1640995200000
    result = mod.gaps([(start, 1), (start+2*period, 1)], start, start+4*period, period, funding=funding)
    assert result["missing_count"] == 2
    assert result["missing_intervals"] == [
        {"start": start+period, "end_exclusive": start+2*period, "count": 1},
        {"start": start+3*period, "end_exclusive": start+4*period, "count": 1},
    ]
    assert len(result["observed_interval_mismatches"]) == (1 if funding else 0)


def test_all_endpoints_paginate_manifest_hashes_and_resume(plan_path, tmp_path):
    calls = []; start = 1640995200000
    def send(endpoint, params):
        calls.append((endpoint, dict(params)))
        if endpoint == mod.INSTRUMENTS:
            return universe_sender(endpoint, params)
        assert params["limit"] == (1000 if endpoint == mod.ENDPOINTS["kline"] else 200)
        if endpoint == mod.ENDPOINTS["kline"]:
            period = mod.PERIODS[params["interval"]]
            rows = [kline(t) for t in (start, start+period) if t <= params["end"]]
            # 強制時間分頁：先只送後一根。
            return response(rows[-1:])
        if endpoint == mod.ENDPOINTS["funding"]:
            assert "endTime" in params and "cursor" not in params
            ts = start+14400000 if params["endTime"] >= start+14400000 else start
            return response([{"symbol": "BTCUSDT", "fundingRateTimestamp": str(ts), "fundingRate": "-0.001"}])
        assert params["intervalTime"] == "4h"
        if params.get("cursor"):
            return response([{"timestamp": str(start), "openInterest": "1"}])
        return response([{"timestamp": str(start+14400000), "openInterest": "2"}], "oi2")
    c = collector(plan_path, tmp_path, send); manifest = c.collect()
    assert len(manifest["files"]) == 5
    assert manifest["request_count"] == len(calls)
    assert manifest["request_log_sha256"] == hashlib.sha256(c.client.log.read_bytes()).hexdigest()
    for filename, entry in manifest["files"].items():
        raw = (c.out / filename).read_bytes()
        assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
        assert entry["plan_sha256"] == hashlib.sha256(plan_path.read_bytes()).hexdigest()
        assert entry["interval_ms"] == (14400000 if entry["dataset"] in ("funding", "open_interest") else mod.PERIODS[entry["interval"]])
        timestamps = [int(line.split(",")[0]) for line in gzip.decompress(raw).decode().splitlines()[1:]]
        assert timestamps == sorted(set(timestamps))
        assert all(c.client.records[i-1]["params"]["symbol"] == entry["symbol"] for i in entry["request_ids"])
    def forbidden(*args):
        raise AssertionError("完整且雜湊相符時不能再請求")
    resumed = collector(plan_path, tmp_path, forbidden)
    assert resumed.collect()["files"] == manifest["files"]
    assert resumed.dry_run()["network_requests"] == 0


def test_interrupted_write_preserves_old_file_and_removes_temp(tmp_path, monkeypatch):
    target = tmp_path / "file.gz"; target.write_bytes(b"old")
    def fail(*args): raise OSError("synthetic interruption")
    monkeypatch.setattr(mod.os, "replace", fail)
    with pytest.raises(OSError): mod.atomic_write(target, b"new")
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


def test_dry_run_requires_cached_raw_universe(plan_path, tmp_path):
    def forbidden(*args): raise AssertionError("dry-run 不得請求")
    c = collector(plan_path, tmp_path, forbidden)
    with pytest.raises(mod.DataError, match="instruments-info"):
        c.dry_run()


def test_universe_only_and_cli_rate_refusal(plan_path, tmp_path, monkeypatch):
    calls = []
    original = mod.transport
    def fake(endpoint, params):
        calls.append(endpoint); return universe_sender(endpoint, params)
    # CLI 使用同一個 Collector 介面，注入傳輸以保留 socket 禁令。
    real = mod.Collector
    monkeypatch.setattr(mod, "Collector", lambda plan,out,**kwargs: real(plan,out,send=fake,**kwargs))
    mod.main(["--plan", str(plan_path), "--out", str(tmp_path / "cli"), "--universe-only"])
    assert calls and set(calls) == {mod.INSTRUMENTS}
    count = len(calls)
    mod.main(["--plan", str(plan_path), "--out", str(tmp_path / "cli"), "--dry-run"])
    assert len(calls) == count
    with pytest.raises(SystemExit) as exc:
        mod.main(["--plan", str(plan_path), "--out", str(tmp_path / "bad"), "--max-rps", "4.1"])
    assert exc.value.code == 2


def test_stdlib_only_ast():
    for path in Path(mod.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in sys.stdlib_module_names for a in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level:
                assert node.module.split(".")[0] in sys.stdlib_module_names


def test_interruption_resumes_only_unfinished_data_pages(plan_path, tmp_path):
    value = json.loads(plan_path.read_text())
    value["datasets"] = [value["datasets"][0]]
    value["datasets"][0]["intervals"] = ["60"]
    plan_path.write_bytes(mod.encoded(value))
    start = 1640995200000
    calls = []
    def interrupted(endpoint, params):
        calls.append((endpoint, dict(params)))
        if endpoint == mod.INSTRUMENTS:
            return universe_sender(endpoint, params)
        if params["end"] == start+3600000-1:
            raise RuntimeError("模擬程序中斷")
        return response([kline(start+3600000)])
    c = collector(plan_path, tmp_path, interrupted)
    with pytest.raises(RuntimeError): c.collect()
    resumed_calls = []
    def resumed(endpoint, params):
        resumed_calls.append((endpoint, params))
        assert endpoint == mod.ENDPOINTS["kline"]
        assert params["end"] == start+3600000-1
        return response([kline(start)])
    r = collector(plan_path, tmp_path, resumed); manifest = r.collect()
    assert len(resumed_calls) == 1
    entry = next(iter(manifest["files"].values()))
    assert entry["count"] == 2
    assert len(entry["source_request_ids"]) == 2


def test_delisted_partial_cursor_failure_cannot_be_silently_accepted(plan_path, tmp_path):
    def send(endpoint, params):
        if "status" not in params: return response([instrument()])
        if "cursor" not in params: return response([instrument("OLDUSDT", "Closed")], "more")
        return response(code=10001)
    c = collector(plan_path, tmp_path, send)
    with pytest.raises(mod.RequestFailed): c.fetch_universe()
    assert not c.manifest.get("universe_complete")


def test_retry_attempts_are_counted_in_file_provenance(plan_path, tmp_path):
    value = json.loads(plan_path.read_text()); value["datasets"] = [value["datasets"][2]]
    plan_path.write_bytes(mod.encoded(value))
    calls = []
    def send(endpoint, params):
        if endpoint == mod.INSTRUMENTS: return universe_sender(endpoint, params)
        calls.append(1)
        if len(calls) == 1: return 503, b'{}'
        return response([{"symbol": "BTCUSDT", "fundingRateTimestamp": "1640995200000", "fundingRate": "0"}])
    c = collector(plan_path, tmp_path, send); result = c.collect()
    entry = next(iter(result["files"].values()))
    assert entry["request_count"] == 2
    assert len(entry["source_request_ids"]) == 1
    assert len(entry["request_ids"]) == 2


def test_manifest_bound_request_prefix_tampering_rejected(plan_path, tmp_path):
    c = collector(plan_path, tmp_path, universe_sender); c.fetch_universe()
    rows = c.client.log.read_bytes().splitlines()
    row = json.loads(rows[0]); row["http_status"] = 503
    rows[0] = mod.encoded(row); c.client.log.write_bytes(b"\n".join(rows)+b"\n")
    with pytest.raises(mod.DataError, match="前綴"):
        collector(plan_path, tmp_path, universe_sender)

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
    {"end": "2027-01-01T00:00:00Z"}, {"start": "2019-12-31T00:00:00Z"},
])
def test_plan_cannot_expand_authorized_scope(plan_path, changes):
    value = json.loads(plan_path.read_text()); value.update(changes); plan_path.write_bytes(mod.encoded(value))
    with pytest.raises(mod.DataError):
        mod.Plan(plan_path)


def test_whitelist_rejects_endpoint_auth_extra_params_and_scope(plan_path, tmp_path):
    c = collector(plan_path, tmp_path, universe_sender); c.fetch_universe()
    # 請求起點是計畫起點與上市時間（對齊網格）兩者較晚者。
    start = c.plan.job_start("kline", "BTCUSDT", "60", c.universe)
    base = {"category": "linear", "limit": 1000, "symbol": "BTCUSDT", "interval": "60", "start": start, "end": c.plan.end-1}
    c.plan.authorize(mod.ENDPOINTS["kline"], base, c.universe)
    for endpoint, params in [
        ("/v5/order/create", base), (mod.ENDPOINTS["kline"], {**base, "api_key": "fake"}),
        (mod.ENDPOINTS["kline"], {**base, "limit": 200}), (mod.ENDPOINTS["kline"], {**base, "symbol": "UNKNOWN"}),
        (mod.ENDPOINTS["kline"], {**base, "end": c.plan.end}), (mod.ENDPOINTS["kline"], {**base, "start": start-1}),
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
    with pytest.raises(mod.IntegrityError):
        c.fetch_universe()
    assert len(calls) == 5
    assert len(c.client.records) == 5
    assert c.client.clock() >= 15


@pytest.mark.parametrize("status,code", [(400, 0), (401, 0), (404, 0), (200, 10001)])
def test_nonretryable_errors_are_not_retried(plan_path, tmp_path, status, code):
    calls = []
    def send(*args):
        calls.append(1); return status, response(code=code)[1]
    with pytest.raises(mod.IntegrityError):
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
    assert result["missing_count"] == (None if funding else 2)
    assert result["missing_intervals"] == ([] if funding else [
        {"start": start+period, "end_exclusive": start+2*period, "count": 1},
        {"start": start+3*period, "end_exclusive": start+4*period, "count": 1},
    ])
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
    c.close()
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
            elif isinstance(node, ast.Call):
                assert not (isinstance(node.func, ast.Name) and node.func.id == "__import__")
                assert not (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module")
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
    assert c.collect()["failures"]
    c.close()
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
    c.fetch_universe()
    assert c.manifest["delistings"]["probe_status"] == "REQUEST_FAILED"


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
    c.close()
    with pytest.raises(mod.DataError, match="前綴"):
        collector(plan_path, tmp_path, universe_sender)


def test_funding_gaps_follow_observed_one_hour_offset():
    start = 1640995200000
    period = 4*3600000
    result = mod.gaps([(start+3600000, 0), (start+5*3600000, -.001)],
                      start, start+8*3600000, period, funding=True)
    assert result["missing_count"] == 0
    assert result["missing_intervals"] == []
    assert result["off_grid_timestamps"] == []
    assert result["settlement_phase_ms"] == 3600000
    assert result["certainty"] == "OBSERVED_INTERVALS_MATCH"


@pytest.mark.parametrize("offsets", [[], [3600000, 6*3600000]])
def test_unknown_or_changed_funding_phase_does_not_invent_missing_count(offsets):
    start = 1640995200000
    result = mod.gaps([(start+x, 0) for x in offsets], start, start+86400000,
                      4*3600000, funding=True)
    assert result["missing_count"] is None
    assert result["certainty"] == "UNKNOWN_HISTORICAL_INTERVAL"


@pytest.mark.parametrize("name,intervals", [("open_interest", ["1"]), ("open_interest", ["4h"]), ("funding", ["1"]), ("funding", [])])
def test_non_kline_intervals_override_is_rejected(plan_path, name, intervals):
    value = json.loads(plan_path.read_text())
    next(r for r in value["datasets"] if r["name"] == name)["intervals"] = intervals
    plan_path.write_bytes(mod.encoded(value))
    with pytest.raises(mod.DataError, match="只有 K 線"):
        mod.Plan(plan_path)


@pytest.mark.parametrize("failure", [10006, 10016, 10018, "http_exception", "invalid"])
def test_request_failure_classification_and_log(plan_path, tmp_path, failure):
    import http.client
    calls = []
    def send(*args):
        calls.append(1)
        if failure == "http_exception":
            raise http.client.IncompleteRead(b"partial")
        if failure == "invalid":
            raise RecursionError("synthetic parser failure")
        return response(code=failure)
    clock = Clock()
    client = mod.Client(mod.Plan(plan_path), tmp_path / "out", send=send, clock=clock, sleep=clock.sleep)
    expected = mod.ResponseInvalid if failure == "invalid" else mod.RequestFailed
    with pytest.raises(expected):
        client.request(mod.INSTRUMENTS, {"category": "linear", "limit": 1000})
    assert len(calls) == (1 if failure == "invalid" else 5)
    assert len(client.records) == len(calls)
    if failure == "invalid":
        assert client.records[0]["network_error"] == "RecursionError"


def test_cursor_transport_preserves_percent_and_uses_explicit_tls(monkeypatch):
    captured = {}
    class Reply:
        code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return b'{}'
    class Opener:
        def open(self, request, timeout):
            captured['url'] = request.full_url
            return Reply()
    tls = object()
    monkeypatch.setattr(mod.ssl, 'create_default_context', lambda: tls)
    def build(*handlers):
        captured['tls'] = [h._context for h in handlers if isinstance(h, mod.urllib.request.HTTPSHandler)]
        return Opener()
    monkeypatch.setattr(mod.urllib.request, 'build_opener', build)
    mod.transport(mod.INSTRUMENTS, {'category': 'linear', 'cursor': 'abc%2Fdef%3D~_-.'})
    assert captured['url'].endswith('category=linear&cursor=abc%2Fdef%3D~_-.')
    assert captured['tls'] == [tls]


def test_directory_lock_repository_guard_and_403_cooldown(plan_path, tmp_path):
    c = collector(plan_path, tmp_path, lambda *args: (403, b'{}'))
    with pytest.raises(mod.IntegrityError, match='鎖'):
        collector(plan_path, tmp_path, universe_sender)
    with pytest.raises(mod.Forbidden): c.fetch_universe()
    c.close()
    with pytest.raises(mod.IntegrityError, match='冷卻'):
        collector(plan_path, tmp_path, universe_sender)
    clock = Clock()
    with mod.Collector(mod.Plan(plan_path), tmp_path/'out', send=universe_sender,
                       clock=clock, sleep=clock.sleep, now=lambda: '2026-10-16T00:10:00Z') as resumed:
        assert resumed.fetch_universe()
    repo = tmp_path/'repo'; repo.mkdir(); (repo/'.git').write_text('gitdir: elsewhere')
    with pytest.raises(mod.IntegrityError, match='倉庫'):
        mod.Collector(mod.Plan(plan_path), repo/'nested'/'out')


@pytest.mark.parametrize('cursor', ['x/y', 'x&limit=9', 'x%', '%2G', '中文', 'x\n'])
def test_cursor_syntax_rejected_at_response_and_plan(plan_path, tmp_path, cursor):
    c = collector(plan_path, tmp_path, lambda *args: response([instrument()], cursor))
    with pytest.raises(mod.IntegrityError): c.fetch_universe()
    with pytest.raises(mod.IntegrityError):
        c.plan.authorize(mod.INSTRUMENTS, {'category': 'linear', 'limit': 1000, 'cursor': cursor}, {})


def test_failed_jobs_continue_retry_once_and_delisted_unavailable(plan_path, tmp_path):
    attempts = {}
    def send(endpoint, params):
        if endpoint == mod.INSTRUMENTS:
            return response([instrument('OLDUSDT', 'Closed')] if 'status' in params else [instrument()])
        key = (params['symbol'], endpoint, params.get('interval'))
        attempts[key] = attempts.get(key, 0) + 1
        if params['symbol'] == 'OLDUSDT': return response(code=10001)
        if endpoint == mod.ENDPOINTS['funding']: return response(code=10016)
        return response()
    c = collector(plan_path, tmp_path, send); result = c.collect()
    assert len(result['files']) == 4
    assert len(result['failures']) == 5
    assert result['failures']['funding_BTCUSDT_funding.csv.gz']['status'] == 'FAILED'
    assert all(f['attempts'] == 1 for f in result['failures'].values())
    assert all(f['status'] == 'FAILED_UNAVAILABLE' for k,f in result['failures'].items() if 'OLDUSDT' in k)
    old_calls = sum(n for k,n in attempts.items() if k[0] == 'OLDUSDT')
    c.close()
    c = collector(plan_path, tmp_path, send); result = c.collect()
    assert result['failures']['funding_BTCUSDT_funding.csv.gz']['attempts'] == 2
    assert sum(n for k,n in attempts.items() if k[0] == 'OLDUSDT') == old_calls
    before = dict(attempts); c.collect(); assert attempts == before


def test_funding_changed_interval_is_unknown_even_same_phase():
    result = mod.gaps([(0, 0), (8, 0), (12, 0)], 0, 20, 4, funding=True)
    assert result['missing_count'] is None
    assert result['observed_interval_mismatches'] == [{'from': 0, 'to': 8, 'actual_interval_ms': 8, 'expected_interval_ms': 4}]
    assert mod.gaps([(0, 0), (4, 0)], 0, 20, 4, funding=True)['missing_count'] == 0


def test_kline_launch_grid_delivery_gaps_and_delistings(plan_path, tmp_path):
    start = 1640995200000
    def send(endpoint, params):
        if endpoint == mod.INSTRUMENTS:
            item = instrument('OLDUSDT', 'Closed') if 'status' in params else instrument()
            item.update(launchTime=str(start+1000), deliveryTime=str(start+7200000) if 'status' in params else '0')
            return response([item])
        if endpoint == mod.ENDPOINTS['kline']:
            assert params['start'] == start
        else:
            assert params['startTime'] == start+1000
        return response()
    c = collector(plan_path, tmp_path, send); m = c.collect()
    assert m['files']['kline_OLDUSDT_60.csv.gz']['coverage'][0] == start
    assert m['files']['kline_OLDUSDT_60.csv.gz']['gaps']['missing_count'] == 2
    assert m['universe']['OLDUSDT']['deliveryTime'] == start+7200000
    assert m['delistings']['period_contains_delistings'] is True


@pytest.mark.parametrize('name', ['kline', 'funding', 'open_interest'])
@pytest.mark.parametrize('tail_nonempty', [False, True])
def test_full_oldest_page_direction_probe(plan_path, tmp_path, name, tail_nonempty):
    value = json.loads(plan_path.read_text()); value['end'] = '2023-01-01T00:00:00Z'
    rule = next(r for r in value['datasets'] if r['name'] == name)
    if name == 'kline': rule['intervals'] = ['60']
    value['datasets'] = [rule]; plan_path.write_bytes(mod.encoded(value))
    start = 1640995200000; period = 3600000 if name == 'kline' else 14400000
    count = rule['params']['limit']; probe_start = start+count*period; probes=[]
    def row(t):
        if name == 'kline': return kline(t)
        if name == 'funding': return {'symbol': 'BTCUSDT', 'fundingRateTimestamp': str(t), 'fundingRate': '0'}
        return {'timestamp': str(t), 'openInterest': '1'}
    def send(endpoint, params):
        if endpoint == mod.INSTRUMENTS: return universe_sender(endpoint, params)
        if params[rule['window_keys'][0]] == probe_start:
            probes.append(params); return response([row(probe_start)] if tail_nonempty else [])
        return response([row(start+i*period) for i in range(count)])
    c = collector(plan_path, tmp_path, send); m = c.collect()
    assert len(probes) == 1
    assert bool(m['failures']) is tail_nonempty
    assert bool(m['files']) is not tail_nonempty


@pytest.mark.parametrize('name,key,bad', [('kline','symbol','ETHUSDT'),('kline','category','spot'),('open_interest','symbol','ETHUSDT'),('open_interest','category','spot')])
def test_response_identity_mismatch_fails_only_job(plan_path, tmp_path, name, key, bad):
    def send(endpoint, params):
        if endpoint == mod.INSTRUMENTS: return universe_sender(endpoint, params)
        payload = {'retCode': 0, 'result': {'list': [], 'nextPageCursor': ''}}
        if endpoint == mod.ENDPOINTS[name]: payload['result'][key] = bad
        return 200,mod.encoded(payload)
    c=collector(plan_path,tmp_path,send); m=c.collect()
    assert len(m['failures']) == (3 if name == 'kline' else 1)
    assert all(f['exception_type']=='ResponseInvalid' for f in m['failures'].values())


def test_universe_unique_cursors_hit_limit_and_symbol_bound(plan_path, tmp_path):
    p=json.loads(plan_path.read_text()); p['universe_max_pages']=2; plan_path.write_bytes(mod.encoded(p))
    calls=[]
    def send(*args):
        calls.append(1); return response([instrument()], 'p'+str(len(calls)))
    with pytest.raises(mod.IntegrityError, match='頁數'):
        collector(plan_path,tmp_path,send).fetch_universe()
    assert len(calls)==2
    p['max_symbols']=1; plan_path.write_bytes(mod.encoded(p))
    c=mod.Collector(mod.Plan(plan_path),tmp_path/'symbol-bound',send=lambda *args: response([instrument(),instrument('ETHUSDT')]))
    with pytest.raises(mod.IntegrityError): c.fetch_universe()


@pytest.mark.parametrize('change', ['pages','symbols','probe','minute'])
def test_plan_rejects_limit_probe_or_minute_expansion(plan_path,change):
    p=json.loads(plan_path.read_text())
    if change=='pages': p['max_pages']=5001
    if change=='symbols': p['max_symbols']=2001
    if change=='probe': p['delisted_probe']['logical_scans']=2
    if change=='minute': p['datasets'][1]['symbols'].append('SOLUSDT')
    plan_path.write_bytes(mod.encoded(p))
    with pytest.raises(mod.IntegrityError): mod.Plan(plan_path)


@pytest.mark.parametrize('symbol',['../BTCUSDT','A'*33,'btc'])
def test_unsafe_universe_symbol_rejected(plan_path,tmp_path,symbol):
    c=collector(plan_path,tmp_path,lambda *args: response([instrument(symbol)]))
    with pytest.raises(mod.IntegrityError): c.fetch_universe()


@pytest.mark.parametrize('case',['funding_symbol','kline_window','funding_window','oi_window'])
def test_symbol_and_requested_window_parser_gaps(case):
    start=1640995200000
    name = 'funding' if case.startswith('funding') else 'kline' if case.startswith('kline') else 'open_interest'
    stamp=start if case=='funding_symbol' else start-1
    row = kline(stamp) if name=='kline' else {'timestamp':str(stamp),'openInterest':'1'} if name=='open_interest' else {'symbol':'WRONG' if case=='funding_symbol' else 'BTCUSDT','fundingRateTimestamp':str(stamp),'fundingRate':'0'}
    with pytest.raises(mod.ResponseInvalid):
        mod.parse_rows(name,[row],symbol='BTCUSDT',start=start,end=start+10000,interval='60',now_ms=start+9999999)


def test_cursor_must_come_from_parent_page(plan_path,tmp_path):
    c=collector(plan_path,tmp_path,lambda *args: response([instrument()],'parent-cursor'))
    _,rid=c.client.request(mod.INSTRUMENTS,{'category':'linear','limit':1000})
    with pytest.raises(mod.IntegrityError,match='父頁'):
        c.client.request(mod.INSTRUMENTS,{'category':'linear','limit':1000,'cursor':'forged'},page=2,parent=rid)
    assert len(c.client.records)==1


def test_probe_network_error_resume_and_raw_null_guard(plan_path,tmp_path):
    def send(endpoint,params):
        if 'status' in params: raise OSError('offline')
        return response([instrument()])
    c=collector(plan_path,tmp_path,send); c.fetch_universe(); c.close()
    with collector(plan_path,tmp_path,lambda *args: pytest.fail('unexpected network')) as r:
        assert r.fetch_universe()['BTCUSDT']
        assert r.manifest['delistings']['probe_status']=='REQUEST_FAILED'
    (tmp_path/'out'/'raw'/'2.json').write_bytes(b'{}')
    with pytest.raises(mod.IntegrityError): collector(plan_path,tmp_path,send)


@pytest.mark.parametrize('change',['symbol','id_zero','id_bool','id_too_large','checkpoint'])
def test_resume_revalidates_manifest_and_checkpoint(plan_path,tmp_path,change):
    def send(endpoint,params):
        return universe_sender(endpoint,params) if endpoint==mod.INSTRUMENTS else response()
    c=collector(plan_path,tmp_path,send); c.collect(); c.close()
    path=tmp_path/'out'/'manifest.json'; m=json.loads(path.read_text())
    if change=='symbol': m['universe']['../bad']=m['universe'].pop('BTCUSDT')
    elif change=='checkpoint':
        cp=next((tmp_path/'out').glob('*.progress.json')); data=json.loads(cp.read_text()); data['plan_sha256']='f'*64; cp.write_bytes(mod.encoded(data))
        (tmp_path/'out'/cp.name.removesuffix('.progress.json')).write_bytes(b'tampered')
    else: m['universe_request_ids']=[{'id_zero':0,'id_bool':True,'id_too_large':999}[change]]
    path.write_bytes(mod.encoded(m))
    with pytest.raises(mod.IntegrityError):
        with collector(plan_path,tmp_path,send) as r: r.collect()


def test_tampered_output_rebuilds_from_raw_without_network(plan_path,tmp_path):
    def send(endpoint,params):
        return universe_sender(endpoint,params) if endpoint==mod.INSTRUMENTS else response()
    c=collector(plan_path,tmp_path,send); m=c.collect(); c.close()
    name=next(iter(m['files'])); (tmp_path/'out'/name).write_bytes(b'tampered')
    with collector(plan_path,tmp_path,lambda *args: pytest.fail('unexpected network')) as r:
        assert r.collect()['files'][name]['sha256']==m['files'][name]['sha256']
        assert mod.digest((tmp_path/'out'/name).read_bytes())==m['files'][name]['sha256']


def test_failed_job_recovery_removes_failure(plan_path,tmp_path):
    calls=[]
    def send(endpoint,params):
        if endpoint==mod.INSTRUMENTS: return universe_sender(endpoint,params)
        calls.append(1); return response(code=10001) if len(calls)==1 else response()
    c=collector(plan_path,tmp_path,send); assert len(c.collect()['failures'])==1; c.close()
    with collector(plan_path,tmp_path,send) as r:
        assert not r.collect()['failures']
        assert len(r.manifest['files'])==5


@pytest.mark.parametrize('exc', [RecursionError('nested'), UnicodeEncodeError('ascii','中',0,1,'bad'), mod.ResponseInvalid('回應超過有界大小')])
def test_post_send_exception_always_logged_without_retry(plan_path,tmp_path,exc):
    def send(*args): raise exc
    client=mod.Client(mod.Plan(plan_path),tmp_path/'out',send=send)
    with pytest.raises(mod.ResponseInvalid): client.request(mod.INSTRUMENTS,{'category':'linear','limit':1000})
    assert len(client.records)==1
    assert client.records[0]['network_error']==type(exc).__name__


@pytest.mark.parametrize('unavailable',[False,True])
def test_cli_exit_code_and_ascii_summary(plan_path,tmp_path,monkeypatch,capsys,unavailable):
    def send(endpoint,params):
        if endpoint==mod.INSTRUMENTS:
            return response([instrument('OLDUSDT','Closed')] if 'status' in params else [instrument()])
        return response(code=10001) if unavailable and params['symbol']=='OLDUSDT' or not unavailable else response()
    real=mod.Collector; clock=Clock()
    monkeypatch.setattr(mod,'Collector',lambda plan,out,**opts:real(plan,out,send=send,clock=clock,sleep=clock.sleep,**opts))
    args=['--plan',str(plan_path),'--out',str(tmp_path/'out')]
    if unavailable: mod.main(args)
    else:
        with pytest.raises(SystemExit) as error: mod.main(args)
        assert error.value.code==3
    output=capsys.readouterr().out
    assert output.isascii()
    assert json.loads(output)['failures']


@pytest.mark.parametrize('field,value',[('complete',True),('end',1640995200000),('cursor','fake')])
def test_checkpoint_state_must_match_raw_pages(plan_path,tmp_path,field,value):
    p=json.loads(plan_path.read_text()); p['datasets']=[p['datasets'][0]]; p['datasets'][0]['intervals']=['60']; plan_path.write_bytes(mod.encoded(p))
    start=1640995200000
    def send(endpoint,params):
        if endpoint==mod.INSTRUMENTS: return universe_sender(endpoint,params)
        if params['end']==start+3600000-1: raise RuntimeError('interrupted')
        return response([kline(start+3600000)])
    c=collector(plan_path,tmp_path,send); c.collect(); c.close()
    cp=next((tmp_path/'out').glob('*.progress.json')); state=json.loads(cp.read_text()); state[field]=value; cp.write_bytes(mod.encoded(state))
    with collector(plan_path,tmp_path,send) as r:
        with pytest.raises(mod.IntegrityError,match='checkpoint'): r.collect()


def test_non_json_failure_records_parser_exception(plan_path,tmp_path):
    c=mod.Client(mod.Plan(plan_path),tmp_path/'out',send=lambda *args:(200,b'not json'))
    with pytest.raises(mod.RequestFailed): c.request(mod.INSTRUMENTS,{'category':'linear','limit':1000})
    assert len(c.records)==1
    assert c.records[0]['network_error']=='JSONDecodeError'


@pytest.mark.parametrize('tamper',['missing_page','delete_symbol','too_many_symbols'])
def test_universe_resume_rebuilds_exact_raw_members_and_completion(plan_path,tmp_path,tamper):
    p=json.loads(plan_path.read_text()); p['max_symbols']=2; plan_path.write_bytes(mod.encoded(p))
    def send(endpoint,params):
        if 'status' in params: return response()
        return response([instrument('ETHUSDT')]) if 'cursor' in params else response([instrument()],'page2')
    c=collector(plan_path,tmp_path,send); c.fetch_universe(); c.close()
    mp=tmp_path/'out'/'manifest.json'; m=json.loads(mp.read_text())
    if tamper=='missing_page':
        mp.unlink()
        cp=tmp_path/'out'/'instruments_pages.json'; state=json.loads(cp.read_text())
        state.update(ids=[1],cursor='page2',complete=True); cp.write_bytes(mod.encoded(state))
    elif tamper=='delete_symbol':
        del m['universe']['ETHUSDT']; mp.write_bytes(mod.encoded(m))
    else:
        m['universe']['SOLUSDT']=dict(m['universe']['BTCUSDT']); mp.write_bytes(mod.encoded(m))
    with pytest.raises(mod.IntegrityError):
        with collector(plan_path,tmp_path,lambda *args:pytest.fail('unexpected network')) as r: r.fetch_universe()


class Crash(BaseException):
    """模擬程序在 manifest 完成前中斷；不被收集器當成請求失敗。"""


@pytest.mark.parametrize('evidence', ['retcode', 'network', 'page_limit', 'forged', 'forged_ids', 'dropped_ids'])
def test_resumed_probe_failure_requires_verifiable_evidence(plan_path, tmp_path, evidence):
    if evidence == 'page_limit':
        p = json.loads(plan_path.read_text()); p['universe_max_pages'] = 1; plan_path.write_bytes(mod.encoded(p))
    def send(endpoint, params):
        if 'status' not in params: return response([instrument()])
        if 'cursor' not in params: return response([instrument('OLDUSDT', 'Closed')], 'more')
        if evidence in ('retcode', 'dropped_ids'): return response(code=10001)
        if evidence == 'network': raise OSError('offline')
        raise Crash()
    c = collector(plan_path, tmp_path, send)
    if evidence == 'dropped_ids':
        # 真實的最終失敗，但狀態檔刪掉了失敗請求清單：來源紀錄不完整，同樣拒絕。
        c.fetch_universe(); c.close()
        cp = tmp_path/'out'/'delisted_probe_pages.json'; state = json.loads(cp.read_text())
        assert state['failed'] and state['failure_request_ids']
        state['failure_request_ids'] = []; cp.write_bytes(mod.encoded(state))
        (tmp_path/'out'/'manifest.json').unlink()
        with pytest.raises(mod.IntegrityError, match='失敗證據'):
            with collector(plan_path, tmp_path, lambda *args: pytest.fail('unexpected network')) as r: r.fetch_universe()
        return
    if evidence.startswith('forged'):
        with pytest.raises(Crash): c.fetch_universe()
        c.close()
        cp = tmp_path/'out'/'delisted_probe_pages.json'; state = json.loads(cp.read_text())
        assert state['ids'] == [2] and state['cursor'] == 'more' and not state['failed']
        state.update(failed=True, complete=True)
        if evidence == 'forged_ids': state['failure_request_ids'] = [2]
        cp.write_bytes(mod.encoded(state))
        with pytest.raises(mod.IntegrityError, match='失敗證據'):
            with collector(plan_path, tmp_path, lambda *args: pytest.fail('unexpected network')) as r: r.fetch_universe()
        return
    c.fetch_universe(); c.close()
    assert c.manifest['delistings']['probe_status'] == 'REQUEST_FAILED'
    (tmp_path/'out'/'manifest.json').unlink()
    with collector(plan_path, tmp_path, lambda *args: pytest.fail('unexpected network')) as r:
        assert set(r.fetch_universe()) == {'BTCUSDT', 'OLDUSDT'}
        assert r.manifest['delistings']['probe_status'] == 'REQUEST_FAILED'


@pytest.mark.parametrize('case', ['transient_500', 'rate_limited', 'retried_ok', 'retried_ok_all'])
def test_forged_probe_failure_cannot_point_at_non_final_attempts(plan_path, tmp_path, monkeypatch, case):
    # 審查反例：偽造的失敗只指向還能重試的嘗試，或指向之後重試成功的那一頁。
    calls = []
    def send(endpoint, params):
        if 'status' not in params: return response([instrument()])
        if 'cursor' not in params: return response([instrument('OLDUSDT', 'Closed')], 'more')
        calls.append(1)
        if len(calls) == 1:
            return response(code=10006) if case == 'rate_limited' else (500, mod.encoded({}))
        if case.startswith('retried_ok'): return response([instrument('NEWUSDT', 'Closed')])
        raise Crash()
    write = mod.atomic_write
    def crash_before_checkpoint(path, data):
        if Path(path).name == 'delisted_probe_pages.json' and json.loads(data)['ids'] == [2, 4]: raise Crash()
        return write(path, data)
    monkeypatch.setattr(mod, 'atomic_write', crash_before_checkpoint)
    c = collector(plan_path, tmp_path, send)
    with pytest.raises(Crash): c.fetch_universe()
    c.close()
    cp = tmp_path/'out'/'delisted_probe_pages.json'; state = json.loads(cp.read_text())
    assert state['ids'] == [2] and state['cursor'] == 'more' and not state['failed']
    assert c.client.records[2]['retryable'] is True and c.client.records[2]['attempt'] == 1
    state.update(failed=True, complete=True, failure_request_ids=[3, 4] if case == 'retried_ok_all' else [3])
    cp.write_bytes(mod.encoded(state))
    with pytest.raises(mod.IntegrityError, match='失敗證據'):
        with collector(plan_path, tmp_path, lambda *args: pytest.fail('unexpected network')) as r: r.fetch_universe()


def test_float_zero_retcode_is_a_real_probe_failure_on_resume(plan_path, tmp_path):
    # retCode 0.0 被客戶端判為失敗；續傳時同樣要承認這是真實失敗，而不是當成成功頁。
    def send(endpoint, params):
        if 'status' not in params: return response([instrument()])
        if 'cursor' not in params: return response([instrument('OLDUSDT', 'Closed')], 'more')
        return 200, mod.encoded({'retCode': 0.0, 'result': {'list': [], 'nextPageCursor': ''}})
    c = collector(plan_path, tmp_path, send); c.fetch_universe(); c.close()
    assert c.manifest['delistings']['probe_status'] == 'REQUEST_FAILED'
    (tmp_path/'out'/'manifest.json').unlink()
    with collector(plan_path, tmp_path, lambda *args: pytest.fail('unexpected network')) as r:
        assert set(r.fetch_universe()) == {'BTCUSDT', 'OLDUSDT'}

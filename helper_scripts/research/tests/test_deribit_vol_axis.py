"""Deribit 隱含波動率數據軸採集器測試（mock HTTP；真實 API 煙測為 opt-in env gate）。

覆蓋（R-0 紅線 + Polymarket 軸紀律逐條對應）：
  - 分頁無關（單請求 surface）/ throttle / backoff / host allowlist / 禁 redirect
    / JSON-RPC error body 偵測（client 層）。
  - instrument_name 解析（CCY-DDMMMYY-STRIKE-{C|P} → 結構化）。
  - 零過濾不變量：mark_iv 缺漏 / 零 OI / 名稱不可解析的 instrument 不丟 row；
    採集端代碼零 relevance 截斷（tokenize 剝註釋字串後驗禁字）。
  - term-structure（各到期 ATM IV）+ skew（各到期 put/call wing IV）構造正確 +
    缺料到期標 None 不丟。
  - manifest 完整性（sha256 重驗）+ append-only（run dir 重名拒絕）+ PIT 標記。
  - 隔離紅線：collector / artifact 源碼零生產 import、零 auth / private / order token。
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import tokenize
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from deribit_vol_axis import (
    COLLECTION_CURRENCIES,
    COLLECTION_SET_VERSION,
    COLLECTOR_VERSION,
)
from deribit_vol_axis import artifact as artifact_mod
from deribit_vol_axis import collector as collector_mod


# ---------------------------------------------------------------------------
# fake transport
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _make_client(router, **kwargs):
    """router(url) -> payload 或 Exception 實例（raise）。"""
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        calls.append(url)
        result = router(url)
        if isinstance(result, Exception):
            raise result
        return _FakeResponse(result)

    kwargs.setdefault("min_interval_s", 0.0)
    kwargs.setdefault("sleep", lambda s: None)
    client = collector_mod.ThrottledJsonClient(urlopen=fake_urlopen, **kwargs)
    return client, calls


def _rpc(result):
    return {"jsonrpc": "2.0", "result": result}


def _dvol_result(closes=(40.0, 41.0)):
    base = 1781442000000
    data = [[base + i * 3600000, c, c + 0.5, c - 0.5, c] for i, c in enumerate(closes)]
    return {"data": data, "continuation": None}


def _opt(name, *, mark_iv, underlying, oi=10.0, vol=1.0):
    return {
        "instrument_name": name,
        "mark_iv": mark_iv,
        "underlying_price": underlying,
        "mark_price": 0.05,
        "mid_price": 0.05,
        "open_interest": oi,
        "volume": vol,
        "volume_usd": vol * 100.0,
        "underlying_index": "BTC-15JUN26",
        "creation_timestamp": 1781164816000,
    }


# ---------------------------------------------------------------------------
# client：throttle / backoff / allowlist / redirect / jsonrpc-error
# ---------------------------------------------------------------------------

class TestClient:
    def test_get_result_unwraps_result_key(self):
        client, _ = _make_client(lambda url: _rpc({"data": []}))
        out = client.get_result(collector_mod.DERIBIT_BASE, "/api/v2/public/get_volatility_index_data")
        assert out == {"data": []}

    def test_jsonrpc_error_body_raises_not_returned(self):
        # HTTP 200 但帶 error 物件：必須升 CollectorHTTPError，不可當資料回。
        client, _ = _make_client(lambda url: {"jsonrpc": "2.0", "error": {"code": 10009, "message": "bad"}})
        with pytest.raises(collector_mod.CollectorHTTPError):
            client.get_result(collector_mod.DERIBIT_BASE, "/api/v2/public/ticker")

    def test_missing_result_raises(self):
        client, _ = _make_client(lambda url: {"jsonrpc": "2.0"})
        with pytest.raises(collector_mod.CollectorHTTPError):
            client.get_result(collector_mod.DERIBIT_BASE, "/x")

    def test_throttle_spaces_requests(self):
        sleeps: list[float] = []
        client, _ = _make_client(
            lambda url: _rpc({"data": []}),
            min_interval_s=0.5, sleep=sleeps.append,
            monotonic=lambda: 0.0,
        )
        client.get_result(collector_mod.DERIBIT_BASE, "/x")
        client.get_result(collector_mod.DERIBIT_BASE, "/x")
        assert any(s > 0 for s in sleeps)

    def test_backoff_retry_then_success(self):
        attempts = {"n": 0}

        def router(url):
            attempts["n"] += 1
            if attempts["n"] < 2:
                return urllib.error.URLError("boom")
            return _rpc({"data": []})

        sleeps: list[float] = []
        client, _ = _make_client(router, retries=3, backoff_base_s=1.0, sleep=sleeps.append)
        out = client.get_result(collector_mod.DERIBIT_BASE, "/x")
        assert out == {"data": []}
        assert len(sleeps) >= 1

    def test_retries_exhausted_raises(self):
        client, _ = _make_client(lambda url: urllib.error.URLError("boom"), retries=1)
        with pytest.raises(collector_mod.CollectorHTTPError):
            client.get_result(collector_mod.DERIBIT_BASE, "/x")

    def test_http_4xx_fails_fast_no_retry(self):
        calls = {"n": 0}

        def router(url):
            calls["n"] += 1
            return urllib.error.HTTPError(url, 404, "nf", {}, None)

        client, _ = _make_client(router, retries=3)
        with pytest.raises(collector_mod.CollectorHTTPError):
            client.get_result(collector_mod.DERIBIT_BASE, "/x")
        assert calls["n"] == 1  # 4xx 不重試

    def test_http_429_does_retry(self):
        calls = {"n": 0}

        def router(url):
            calls["n"] += 1
            if calls["n"] < 2:
                return urllib.error.HTTPError(url, 429, "rate", {}, None)
            return _rpc({"data": []})

        client, _ = _make_client(router, retries=3, backoff_base_s=0.0)
        assert client.get_result(collector_mod.DERIBIT_BASE, "/x") == {"data": []}
        assert calls["n"] == 2

    def test_host_allowlist_rejects_other_bases(self):
        client, _ = _make_client(lambda url: _rpc({}))
        with pytest.raises(ValueError):
            client.get_result("https://evil.example.com", "/x")

    def test_http_30x_fails_fast_as_redirect_refused(self):
        client, _ = _make_client(lambda url: urllib.error.HTTPError(url, 302, "moved", {}, None), retries=3)
        with pytest.raises(collector_mod.CollectorHTTPError) as ei:
            client.get_result(collector_mod.DERIBIT_BASE, "/x")
        assert "redirect_refused" in str(ei.value)

    def test_default_urlopen_is_no_redirect_opener(self):
        client = collector_mod.ThrottledJsonClient()
        assert client._urlopen is collector_mod._urlopen_no_redirect

    def test_redirect_handler_raises_with_bounded_message(self):
        handler = collector_mod._RedirectRefusedHandler()
        req = urllib.request.Request(collector_mod.DERIBIT_BASE + "/x")
        long_url = "https://evil.example.com/" + "a" * 1000
        with pytest.raises(urllib.error.HTTPError) as ei:
            handler.redirect_request(req, None, 302, "moved", {}, long_url)
        assert len(str(ei.value.reason if hasattr(ei.value, "reason") else ei.value)) < 400


# ---------------------------------------------------------------------------
# instrument 名稱解析
# ---------------------------------------------------------------------------

class TestInstrumentParse:
    def test_parse_call(self):
        out = collector_mod.parse_instrument_name("BTC-26MAR27-105000-C")
        assert out == {"ccy": "BTC", "expiry_date": "2027-03-26", "strike": 105000.0, "option_type": "call"}

    def test_parse_put(self):
        out = collector_mod.parse_instrument_name("ETH-15JUN26-3000-P")
        assert out["option_type"] == "put"
        assert out["expiry_date"] == "2026-06-15"
        assert out["strike"] == 3000.0

    def test_parse_fractional_strike(self):
        out = collector_mod.parse_instrument_name("BTC-15JUN26-0.5-C")
        assert out is not None and out["strike"] == 0.5

    def test_parse_malformed_returns_none(self):
        assert collector_mod.parse_instrument_name("BTC-PERPETUAL") is None
        assert collector_mod.parse_instrument_name("BTC-15ZZZ26-100-C") is None
        assert collector_mod.parse_instrument_name("") is None

    def test_float_or_none(self):
        assert collector_mod._float_or_none(None) is None
        assert collector_mod._float_or_none(True) is None  # bool 不當數
        assert collector_mod._float_or_none("x") is None
        assert collector_mod._float_or_none("1.5") == 1.5


# ---------------------------------------------------------------------------
# 攤平：零過濾不變量
# ---------------------------------------------------------------------------

class TestFlatten:
    def test_dvol_bars_flattened_with_raw(self):
        rows = collector_mod.flatten_dvol_rows(
            _dvol_result((40.0, 41.0)), currency="BTC",
            snapshot_ts_utc="2026-06-14T00:00:00Z", collector_git_sha="deadbeef",
        )
        assert len(rows) == 2
        assert rows[0]["dvol_close"] == 40.0
        assert rows[0]["currency"] == "BTC"
        assert rows[0]["raw_bar"][0] == 1781442000000
        assert rows[0]["collection_set_version"] == COLLECTION_SET_VERSION

    def test_dvol_malformed_bar_kept_with_parse_error(self):
        bad = {"data": [[1, 2]]}  # 短 bar
        rows = collector_mod.flatten_dvol_rows(
            bad, currency="BTC", snapshot_ts_utc="t", collector_git_sha="g",
        )
        assert len(rows) == 1
        assert rows[0]["parse_error"] is not None
        assert rows[0]["raw_bar"] == [1, 2]

    def test_zero_oi_and_missing_iv_instruments_are_kept(self):
        summary = [
            _opt("BTC-15JUN26-60000-C", mark_iv=50.0, underlying=63000, oi=0.0, vol=0.0),
            {"instrument_name": "BTC-15JUN26-70000-C", "underlying_price": 63000},  # 無 mark_iv
        ]
        rows = collector_mod.flatten_surface_rows(
            summary, currency="BTC", snapshot_ts_utc="t", collector_git_sha="g",
        )
        assert len(rows) == 2  # 零 OI / 缺 IV 都不丟
        assert rows[1]["mark_iv"] is None  # 缺席 → None 非 0

    def test_unparseable_name_kept_with_flag(self):
        rows = collector_mod.flatten_surface_rows(
            [_opt("BTC-PERPETUAL", mark_iv=1.0, underlying=63000)],
            currency="BTC", snapshot_ts_utc="t", collector_git_sha="g",
        )
        assert len(rows) == 1
        assert rows[0]["name_parse_ok"] is False
        assert rows[0]["expiry_date"] is None

    def test_raw_instrument_preserved(self):
        summary = [_opt("BTC-15JUN26-60000-C", mark_iv=50.0, underlying=63000)]
        rows = collector_mod.flatten_surface_rows(
            summary, currency="BTC", snapshot_ts_utc="t", collector_git_sha="g",
        )
        assert rows[0]["raw_instrument"] == summary[0]

    def test_collector_code_has_no_relevance_truncation_or_auth_tokens(self):
        # 負面不變量：採集端零 relevance 截斷 + 零 auth/private/order。tokenize 剝
        # COMMENT/STRING 後驗禁字，防 MODULE_NOTE 合法提及（如「private 全程不碰」）誤紅。
        src = Path(collector_mod.__file__).read_text(encoding="utf-8")
        code_tokens: list[str] = []
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                code_tokens.append(tok.string)
        joined = " ".join(code_tokens).lower()
        for banned in ("relevance", "ranking", "top_n", "private", "order_id", "authorization"):
            assert banned not in joined, f"banned token in code: {banned}"


# ---------------------------------------------------------------------------
# term-structure / skew 構造
# ---------------------------------------------------------------------------

def _surface_for_skew(currency="BTC", und=60000.0):
    """單一到期、橫跨多 strike 的 surface（put wing IV 高於 call wing = 正 skew）。"""
    rows = []
    spec = [
        ("BTC-15JUN26-54000-P", "put", 54000.0, 70.0),   # OTM put（und×0.9 附近）
        ("BTC-15JUN26-60000-C", "call", 60000.0, 50.0),  # ATM
        ("BTC-15JUN26-60000-P", "put", 60000.0, 50.0),
        ("BTC-15JUN26-66000-C", "call", 66000.0, 55.0),  # OTM call（und×1.1 附近）
    ]
    for name, otype, strike, iv in spec:
        rows.append({
            "expiry_date": "2026-06-15", "currency": currency,
            "option_type": otype, "strike": strike, "mark_iv": iv, "underlying_price": und,
        })
    return rows


class TestTermStructureAndSkew:
    def test_term_structure_picks_nearest_atm(self):
        rows = _surface_for_skew()
        ts = collector_mod.build_term_structure(rows, currency="BTC", snapshot_ts_utc="t")
        assert len(ts) == 1
        cell = ts[0]
        assert cell["expiry_date"] == "2026-06-15"
        assert cell["atm_strike"] == 60000.0  # 最接近 underlying
        assert cell["atm_mark_iv"] == 50.0
        assert cell["n_instruments"] == 4

    def test_term_structure_missing_data_expiry_emits_none(self):
        rows = [{"expiry_date": "2026-07-01", "currency": "BTC",
                 "option_type": "call", "strike": None, "mark_iv": None, "underlying_price": None}]
        ts = collector_mod.build_term_structure(rows, currency="BTC", snapshot_ts_utc="t")
        assert len(ts) == 1 and ts[0]["atm_mark_iv"] is None  # 不丟行

    def test_skew_computes_put_minus_call_wing(self):
        rows = _surface_for_skew()
        sk = collector_mod.build_skew(rows, currency="BTC", snapshot_ts_utc="t")
        assert len(sk) == 1
        cell = sk[0]
        assert cell["otm_put_strike"] == 54000.0
        assert cell["otm_call_strike"] == 66000.0
        # (70 - 55) * 100 = 1500 bps，正值 = put wing 較貴。
        assert cell["skew_proxy_bps"] == pytest.approx(1500.0)

    def test_skew_missing_wing_is_none_not_dropped(self):
        # 只有 call wing、無 OTM put → skew_proxy_bps=None 但行仍在。
        rows = [{"expiry_date": "2026-06-15", "currency": "BTC",
                 "option_type": "call", "strike": 66000.0, "mark_iv": 55.0, "underlying_price": 60000.0}]
        sk = collector_mod.build_skew(rows, currency="BTC", snapshot_ts_utc="t")
        assert len(sk) == 1
        assert sk[0]["otm_put_iv"] is None
        assert sk[0]["skew_proxy_bps"] is None


# ---------------------------------------------------------------------------
# 採集編排
# ---------------------------------------------------------------------------

class TestCollectSnapshot:
    def _router(self):
        def router(url):
            if "get_volatility_index_data" in url:
                return _rpc(_dvol_result((40.0, 41.0)))
            if "get_book_summary_by_currency" in url:
                return _rpc([
                    _opt("BTC-15JUN26-54000-P", mark_iv=70.0, underlying=60000),
                    _opt("BTC-15JUN26-60000-C", mark_iv=50.0, underlying=60000),
                    _opt("BTC-15JUN26-66000-C", mark_iv=55.0, underlying=60000),
                ])
            return urllib.error.HTTPError(url, 404, "nf", {}, None)
        return router

    def test_single_currency_collects_all_views(self):
        client, _ = _make_client(self._router())
        out = collector_mod.collect_vol_snapshot(
            client, currencies=("BTC",), collector_git_sha="g",
        )
        assert out["stats"]["dvol_rows"] == 2
        assert out["stats"]["surface_rows"] == 3
        assert out["stats"]["term_structure_rows"] == 1
        assert out["stats"]["skew_rows"] == 1
        assert out["errors"] == []
        assert out["raw_instruments"][0]["n"] == 3

    def test_dvol_failure_isolated_from_surface(self):
        def router(url):
            if "get_volatility_index_data" in url:
                return urllib.error.HTTPError(url, 500, "boom", {}, None)
            if "get_book_summary_by_currency" in url:
                return _rpc([_opt("BTC-15JUN26-60000-C", mark_iv=50.0, underlying=60000)])
            return urllib.error.HTTPError(url, 404, "nf", {}, None)

        client, _ = _make_client(router, retries=0)
        out = collector_mod.collect_vol_snapshot(client, currencies=("BTC",), collector_git_sha="g")
        assert any(e.startswith("dvol:BTC") for e in out["errors"])
        assert out["stats"]["surface_rows"] == 1  # surface 仍採到

    def test_multi_currency_one_failure_isolated(self):
        def router(url):
            if "currency=ETH" in url:
                return urllib.error.HTTPError(url, 500, "boom", {}, None)
            if "get_volatility_index_data" in url:
                return _rpc(_dvol_result())
            if "get_book_summary_by_currency" in url:
                return _rpc([_opt("BTC-15JUN26-60000-C", mark_iv=50.0, underlying=60000)])
            return urllib.error.HTTPError(url, 404, "nf", {}, None)

        client, _ = _make_client(router, retries=0)
        out = collector_mod.collect_vol_snapshot(client, currencies=("BTC", "ETH"), collector_git_sha="g")
        assert out["stats"]["surface_rows"] == 1  # BTC 採到
        assert any("ETH" in e for e in out["errors"])


# ---------------------------------------------------------------------------
# artifact：manifest 完整性 / append-only / PIT 標記
# ---------------------------------------------------------------------------

class TestArtifact:
    def _write(self, tmp_path, run_id="daily-test"):
        return artifact_mod.write_run(
            mode="daily",
            run_id=run_id,
            repo_root=tmp_path,
            stats={"dvol_rows": 1},
            errors=[],
            dvol_rows=[{"currency": "BTC", "dvol_close": 40.0}],
            surface_rows=[{"instrument_name": "BTC-15JUN26-60000-C", "mark_iv": 50.0}],
            term_structure_rows=[{"expiry_date": "2026-06-15", "atm_mark_iv": 50.0}],
            skew_rows=[{"expiry_date": "2026-06-15", "skew_proxy_bps": 1500.0}],
            raw_instruments=[{"currency": "BTC", "n": 1}],
            artifact_root=tmp_path / "runs",
            parquet_mirror=False,
        )

    def test_manifest_and_index_sha256_reverify(self, tmp_path):
        written = self._write(tmp_path)
        run_dir = Path(written["written"]["run_dir"])
        index = json.loads((run_dir / "artifact_index.json").read_text())
        for entry in index["artifacts"]:
            p = Path(entry["path"])
            h = artifact_mod._sha256(p)
            assert h == entry["sha256"], f"sha256 mismatch {entry['name']}"

    def test_manifest_marks_point_in_time(self, tmp_path):
        written = self._write(tmp_path)
        m = written["manifest"]
        assert m["point_in_time"] is True
        assert m["retrospective"] is False
        assert m["program"] == "deribit-vol-axis-collector"
        assert m["collector_version"] == COLLECTOR_VERSION

    def test_append_only_run_dir_rename_rejected(self, tmp_path):
        self._write(tmp_path, run_id="dup")
        with pytest.raises(FileExistsError):
            self._write(tmp_path, run_id="dup")  # 同名重跑 = 禁回填/覆寫

    def test_all_five_jsonl_files_written(self, tmp_path):
        written = self._write(tmp_path)
        run_dir = Path(written["written"]["run_dir"])
        for f in ("dvol.jsonl", "iv_surface.jsonl", "term_structure.jsonl", "skew.jsonl", "raw_instruments.jsonl"):
            assert (run_dir / f).exists()

    def test_artifact_root_honors_env_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path / "envroot"))
        root = artifact_mod.resolve_artifact_root()
        assert str(tmp_path / "envroot") in str(root)
        assert root.name == "deribit_vol_axis_runs"


# ---------------------------------------------------------------------------
# 隔離紅線（R-0）：零生產 import
# ---------------------------------------------------------------------------

class TestIsolationRedline:
    def test_no_production_imports_in_package(self):
        for mod in (collector_mod, artifact_mod):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            # 採集軸只准標準庫 + 本 package 相對 import；禁 control_api / openclaw 生產模組。
            for banned in ("from control_api", "import control_api", "openclaw_engine", "psycopg", "import asyncpg"):
                assert banned not in src, f"{mod.__name__} leaks production dep: {banned}"

    def test_collection_currencies_btc_eth(self):
        assert COLLECTION_CURRENCIES == ("BTC", "ETH")


# ---------------------------------------------------------------------------
# 真實 API 煙測（opt-in；預設 skip，避 CI 打外網）
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("OPENCLAW_DERIBIT_LIVE_SMOKE") != "1",
    reason="set OPENCLAW_DERIBIT_LIVE_SMOKE=1 for live Deribit public API smoke",
)
def test_live_dvol_connectivity():
    client = collector_mod.ThrottledJsonClient()
    end_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    result = collector_mod.fetch_dvol(
        client, currency="BTC", start_ts_ms=end_ms - 7200000, end_ts_ms=end_ms, resolution_s=3600,
    )
    assert "data" in result
    assert isinstance(result["data"], list)


# ===========================================================================
# E4 補測（覆蓋既有測試漏掉的面）：cli 編排端到端 / parquet 鏡像非阻斷契約 /
#   PIT 時間戳一致性。所有業務邏輯（collect_vol_snapshot / flatten / build_* /
#   write_run）真跑，只以 fake transport stub HTTP IO 邊界（不 stub 受測對象）。
# ===========================================================================

from deribit_vol_axis import cli as cli_mod  # noqa: E402


class _CliRouter:
    """daily 編排用 fake transport router（DVOL 2 bar + 3-instrument surface）。"""

    @staticmethod
    def route(url):
        if "get_volatility_index_data" in url:
            return _rpc(_dvol_result((40.0, 41.0)))
        if "get_book_summary_by_currency" in url:
            return _rpc([
                _opt("BTC-15JUN26-54000-P", mark_iv=70.0, underlying=60000),
                _opt("BTC-15JUN26-60000-C", mark_iv=50.0, underlying=60000),
                _opt("BTC-15JUN26-66000-C", mark_iv=55.0, underlying=60000),
            ])
        return urllib.error.HTTPError(url, 404, "nf", {}, None)


def _patch_cli_transport(monkeypatch, router=_CliRouter.route):
    """把 cli 內 ThrottledJsonClient 構造改注入 fake urlopen（只 stub HTTP IO 邊界；
    collect_vol_snapshot/write_run 等業務邏輯全經真路徑跑）。"""
    real_ctor = collector_mod.ThrottledJsonClient

    def _fake_ctor(**kwargs):
        kwargs.setdefault("sleep", lambda s: None)
        kwargs["min_interval_s"] = 0.0

        def fake_urlopen(req, timeout=None):
            result = router(req.full_url)
            if isinstance(result, Exception):
                raise result
            return _FakeResponse(result)

        return real_ctor(urlopen=fake_urlopen, **kwargs)

    monkeypatch.setattr(collector_mod, "ThrottledJsonClient", _fake_ctor)


class TestCliOrchestration:
    """E1 cli.run_collect 端到端：collect → write_run → run dir + summary。"""

    def _args(self, tmp_path, **over):
        ns = cli_mod._build_arg_parser().parse_args([])
        ns.data_root = str(tmp_path / "data")
        ns.artifact_root = str(tmp_path / "runs")
        ns.no_parquet_mirror = True
        ns.currencies = "BTC"
        ns.run_id = over.pop("run_id", "daily-clitest")
        for k, v in over.items():
            setattr(ns, k, v)
        return ns

    def test_run_collect_writes_run_dir_and_summary(self, tmp_path, monkeypatch):
        _patch_cli_transport(monkeypatch)
        summary = cli_mod.run_collect(self._args(tmp_path))
        # summary 結構正確（cli 解析 stats）。
        assert summary["dvol_rows"] == 2
        assert summary["surface_rows"] == 3
        assert summary["term_structure_rows"] == 1
        assert summary["skew_rows"] == 1
        assert summary["errors"] == []
        assert summary["currencies"] == ["BTC"]
        # run dir 落地 + 五個 jsonl + manifest/index 真寫出。
        run_dir = Path(summary["run_dir"])
        assert run_dir.is_dir()
        for f in ("dvol.jsonl", "iv_surface.jsonl", "term_structure.jsonl",
                  "skew.jsonl", "raw_instruments.jsonl", "manifest.json", "artifact_index.json"):
            assert (run_dir / f).exists(), f"missing {f}"

    def test_run_collect_artifact_root_honors_data_root(self, tmp_path, monkeypatch):
        # 未顯式給 artifact_root 時，由 data_root 推導（root 禁硬編碼路徑驗證）。
        _patch_cli_transport(monkeypatch)
        ns = self._args(tmp_path, run_id="daily-rootcheck")
        ns.artifact_root = None
        summary = cli_mod.run_collect(ns)
        assert str(tmp_path / "data") in summary["run_dir"]
        assert "deribit_vol_axis_runs" in summary["run_dir"]

    def test_run_collect_manifest_marks_pit(self, tmp_path, monkeypatch):
        _patch_cli_transport(monkeypatch)
        summary = cli_mod.run_collect(self._args(tmp_path, run_id="daily-pit"))
        manifest = json.loads((Path(summary["run_dir"]) / "manifest.json").read_text())
        assert manifest["point_in_time"] is True
        assert manifest["retrospective"] is False
        # cli 的 git_sha 傳進 surface row（採集 provenance 真接線）。
        surf = (Path(summary["run_dir"]) / "iv_surface.jsonl").read_text().splitlines()
        assert len(surf) == 3
        first = json.loads(surf[0])
        assert "collector_git_sha" in first and first["collector_git_sha"]

    def test_run_collect_isolates_dvol_failure(self, tmp_path, monkeypatch):
        # cli 經 fail-soft：DVOL 500 仍寫 surface + 把 error 帶進 summary。
        def router(url):
            if "get_volatility_index_data" in url:
                return urllib.error.HTTPError(url, 500, "boom", {}, None)
            if "get_book_summary_by_currency" in url:
                return _rpc([_opt("BTC-15JUN26-60000-C", mark_iv=50.0, underlying=60000)])
            return urllib.error.HTTPError(url, 404, "nf", {}, None)

        _patch_cli_transport(monkeypatch, router=router)
        ns = self._args(tmp_path, run_id="daily-dvolfail")
        ns.min_interval_s = 0.0
        summary = cli_mod.run_collect(ns)
        assert summary["surface_rows"] == 1
        assert any(e.startswith("dvol:BTC") for e in summary["errors"])
        assert (Path(summary["run_dir"]) / "iv_surface.jsonl").exists()


class TestParquetMirrorContract:
    """E1 mirror_jsonl_to_parquet 非阻斷契約（duckdb 在時走真鏡像路徑）。"""

    def _write_with_mirror(self, tmp_path):
        return artifact_mod.write_run(
            mode="daily", run_id="daily-parq", repo_root=tmp_path,
            stats={"dvol_rows": 1}, errors=[],
            dvol_rows=[{"currency": "BTC", "dvol_close": 40.0}],
            surface_rows=[{"instrument_name": "BTC-15JUN26-60000-C", "mark_iv": 50.0}],
            term_structure_rows=[{"expiry_date": "2026-06-15", "atm_mark_iv": 50.0}],
            skew_rows=[{"expiry_date": "2026-06-15", "skew_proxy_bps": 1500.0}],
            raw_instruments=[{"currency": "BTC", "n": 1}],
            artifact_root=tmp_path / "runs", parquet_mirror=True,
        )

    def test_parquet_mirror_status_in_manifest(self, tmp_path):
        duckdb = pytest.importorskip("duckdb")
        del duckdb
        written = self._write_with_mirror(tmp_path)
        mres = written["manifest"]["parquet_mirror"]
        assert mres["parquet_mirror"] == "ok"
        # 5 個 jsonl 全鏡像成 parquet（無 .tmp 殘檔 = 原子寫成功）。
        run_dir = Path(written["written"]["run_dir"])
        assert len(mres["files_ok"]) == 5 and mres["files_failed"] == []
        assert list(run_dir.glob("*.parquet.tmp")) == []
        for jf in run_dir.glob("*.jsonl"):
            assert jf.with_suffix(".parquet").exists()

    def test_parquet_mirror_missing_duckdb_skips_not_raises(self, tmp_path, monkeypatch):
        # 缺 duckdb 時收斂成 skipped（非阻斷契約）：模擬 import 失敗。
        import builtins
        real_import = builtins.__import__

        def _no_duckdb(name, *a, **k):
            if name == "duckdb":
                raise ImportError("simulated missing duckdb")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", _no_duckdb)
        out = artifact_mod.mirror_jsonl_to_parquet(tmp_path)
        assert out["parquet_mirror"] == "skipped"
        assert out["reason"] == "duckdb_not_available"

    def test_parquet_mirror_disabled_records_disabled(self, tmp_path):
        # parquet_mirror=False → manifest 記 disabled，不嘗試 import duckdb。
        written = artifact_mod.write_run(
            mode="daily", run_id="daily-nomirror", repo_root=tmp_path,
            stats={}, errors=[], dvol_rows=[{"x": 1}],
            artifact_root=tmp_path / "runs", parquet_mirror=False,
        )
        assert written["manifest"]["parquet_mirror"] == {"parquet_mirror": "disabled"}


class TestPitTimestampConsistency:
    """PIT 紀律：單輪 snapshot 所有衍生行共用同一 snapshot_ts_utc（單時刻一致快照）。"""

    def test_single_snapshot_shares_one_timestamp(self):
        def router(url):
            if "get_volatility_index_data" in url:
                return _rpc(_dvol_result((40.0, 41.0)))
            if "get_book_summary_by_currency" in url:
                return _rpc([
                    _opt("BTC-15JUN26-54000-P", mark_iv=70.0, underlying=60000),
                    _opt("BTC-15JUN26-66000-C", mark_iv=55.0, underlying=60000),
                ])
            return urllib.error.HTTPError(url, 404, "nf", {}, None)

        client, _ = _make_client(router)
        out = collector_mod.collect_vol_snapshot(
            client, currencies=("BTC",), collector_git_sha="g",
            now_iso="2026-06-14T12:00:00+00:00", now_ts_ms=1781442000000,
        )
        seen = set()
        for key in ("dvol_rows", "surface_rows", "term_structure_rows", "skew_rows"):
            for row in out[key]:
                seen.add(row["snapshot_ts_utc"])
        assert seen == {"2026-06-14T12:00:00+00:00"}  # 全鏈共用單一 PIT 時刻

    def test_dvol_window_anchored_to_now_ts_ms(self):
        # append-only 不回填：DVOL 窗口錨定 now_ts_ms 往回 dvol_window_s，不抓更早歷史。
        captured = {}

        def router(url):
            if "get_volatility_index_data" in url:
                captured["url"] = url
                return _rpc(_dvol_result())
            return _rpc([])

        client, _ = _make_client(router)
        collector_mod.collect_vol_snapshot(
            client, currencies=("BTC",), collector_git_sha="g",
            dvol_window_s=3600, now_ts_ms=1781442000000,
        )
        assert "end_timestamp=1781442000000" in captured["url"]
        assert "start_timestamp=1781438400000" in captured["url"]  # end - 3600*1000

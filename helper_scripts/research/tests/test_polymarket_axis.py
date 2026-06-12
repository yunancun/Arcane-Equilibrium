"""Polymarket 數據軸採集器測試（mock HTTP；真實 API 煙測為 opt-in env gate）。

覆蓋（QC memo 鐵則逐條對應）：
  - 分頁 / throttle / backoff / host allowlist（client 層）。
  - 上游移植解析（_parse_outcome_prices / _safe_float）。
  - 零過濾不變量：closed / 零流動性 market 不丟 row；採集端代碼零 relevance
    截斷（tokenize 剝註釋字串後驗禁字，防 MODULE_NOTE 合法提及誤紅）。
  - track-to-resolution 狀態機（tracking → resolved / lost 終態 + 不回退）。
  - manifest 完整性（sha256 重驗）+ append-only（run dir 重名拒絕）+
    lane 隔離（retrospective 永不混 snapshot）。
"""

from __future__ import annotations

import inspect
import io
import json
import os
import tokenize
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from polymarket_axis import (
    LANE_RETROSPECTIVE,
    LANE_SNAPSHOT,
    QUERY_SET_V1_KEYWORDS,
    QUERY_SET_VERSION,
    UPSTREAM_ATTRIBUTION,
)
from polymarket_axis import artifact as artifact_mod
from polymarket_axis import collector as collector_mod
from polymarket_axis import state as state_mod


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


def _market(mid="101", *, closed=False, active=True, uma=None, prices='["0.4", "0.6"]', **extra):
    m = {
        "id": mid,
        "question": f"Q{mid}?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": prices,
        "clobTokenIds": '["tok-a", "tok-b"]',
        "closed": closed,
        "active": active,
        "volumeNum": 123.0,
        "endDate": "2027-01-01T00:00:00Z",
    }
    if uma is not None:
        m["umaResolutionStatus"] = uma
    m.update(extra)
    return m


def _event(eid="1", markets=None, **extra):
    e = {
        "id": eid,
        "slug": f"ev-{eid}",
        "title": f"Event {eid}",
        "tags": [{"slug": "crypto"}, {"slug": "finance"}],
        "closed": False,
        "active": True,
        "liquidity": 100.0,
        "competitive": 0.5,
        "volume24hr": 10.0,
        "volume1wk": 20.0,
        "volume1mo": 30.0,
        "endDate": "2027-01-01T00:00:00Z",
        "updatedAt": "2026-06-11T00:00:00Z",
        "markets": markets if markets is not None else [_market()],
    }
    e.update(extra)
    return e


# ---------------------------------------------------------------------------
# client：分頁 / throttle / backoff / allowlist
# ---------------------------------------------------------------------------

class TestClient:
    def test_events_pagination_until_short_page(self):
        def router(url):
            if "offset=0" in url:
                return [_event(str(i)) for i in range(100)]
            return [_event(str(100 + i)) for i in range(30)]

        client, calls = _make_client(router)
        events, stats = collector_mod.fetch_events_by_tag(client, tag_slug="crypto")
        assert len(events) == 130
        assert stats == {"pages": 2, "page_cap_hit": False, "events": 130}
        assert "offset=0" in calls[0] and "offset=100" in calls[1]
        assert all("tag_slug=crypto" in c and "closed=false" in c for c in calls)

    def test_events_page_cap_is_honest_not_silent(self):
        client, _ = _make_client(lambda url: [_event(str(i)) for i in range(100)])
        events, stats = collector_mod.fetch_events_by_tag(client, tag_slug="crypto", max_pages=3)
        assert len(events) == 300
        assert stats["page_cap_hit"] is True  # 觸保險絲必須對研究端可見。

    def test_throttle_spaces_requests(self):
        sleeps: list[float] = []
        clock = {"t": 0.0}

        def fake_sleep(s):
            sleeps.append(s)
            clock["t"] += s

        client, _ = _make_client(lambda url: [], min_interval_s=0.5,
                                 sleep=fake_sleep, monotonic=lambda: clock["t"])
        client.get_json(collector_mod.GAMMA_BASE, "/events")
        client.get_json(collector_mod.GAMMA_BASE, "/events")
        # 第二發必須等滿 min interval（fake clock 不前進除了 sleep）。
        assert sleeps and abs(sleeps[0] - 0.5) < 1e-9

    def test_backoff_retry_then_success(self):
        attempts = {"n": 0}

        def router(url):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                return urllib.error.URLError("conn reset")
            return {"ok": True}

        sleeps: list[float] = []
        client, _ = _make_client(router, retries=3, backoff_base_s=1.0, sleep=sleeps.append)
        out = client.get_json(collector_mod.GAMMA_BASE, "/events")
        assert out == {"ok": True}
        # 指數退避：1s, 2s（throttle 為 0 不另加）。
        assert sleeps == [1.0, 2.0]

    def test_retries_exhausted_raises(self):
        client, calls = _make_client(lambda url: urllib.error.URLError("down"), retries=2)
        with pytest.raises(collector_mod.CollectorHTTPError, match="retries exhausted"):
            client.get_json(collector_mod.GAMMA_BASE, "/events")
        assert len(calls) == 3  # 1 + 2 retries。

    def test_http_4xx_fails_fast_no_retry(self):
        err = urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b""))
        client, calls = _make_client(lambda url: err, retries=3)
        with pytest.raises(collector_mod.CollectorHTTPError, match="http_404"):
            client.get_json(collector_mod.GAMMA_BASE, "/events")
        assert len(calls) == 1  # 4xx 不重試。

    def test_http_429_does_retry(self):
        attempts = {"n": 0}

        def router(url):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return urllib.error.HTTPError("u", 429, "slow down", {}, io.BytesIO(b""))
            return []

        client, _ = _make_client(router, retries=2)
        assert client.get_json(collector_mod.GAMMA_BASE, "/events") == []

    def test_host_allowlist_rejects_other_bases(self):
        client, calls = _make_client(lambda url: [])
        with pytest.raises(ValueError, match="allowlist"):
            client.get_json("https://example.com", "/events")
        assert calls == []  # 連請求都不該發出。

    # ---- E3（修復輪 2026-06-12）：禁 redirect ----

    def test_http_30x_fails_fast_as_redirect_refused(self):
        """默認 opener 拒 redirect 升上來的 30x：立即終止，不浪費 retry。"""
        err = urllib.error.HTTPError(
            "https://gamma-api.polymarket.com/events", 302, "Found", {}, None)
        client, calls = _make_client(lambda url: err, retries=3)
        with pytest.raises(collector_mod.CollectorHTTPError, match="redirect_refused"):
            client.get_json(collector_mod.GAMMA_BASE, "/events")
        assert len(calls) == 1  # redirect 非可重試網路況。

    def test_default_urlopen_is_no_redirect_opener(self):
        """E3 接線斷言：不注入時 client 默認用 _urlopen_no_redirect（allowlist 防不了跟跳）。"""
        sig = inspect.signature(collector_mod.ThrottledJsonClient.__init__)
        assert sig.parameters["urlopen"].default is collector_mod._urlopen_no_redirect

    def test_redirect_handler_raises_with_bounded_message(self):
        """Location 是外部可控文本：refused message 截斷，exc log 進 cron log 不灌爆。"""
        handler = collector_mod._RedirectRefusedHandler()
        req = urllib.request.Request("https://gamma-api.polymarket.com/events")
        with pytest.raises(urllib.error.HTTPError) as ei:
            handler.redirect_request(
                req, None, 302, "Found", {}, "https://evil.example/" + "a" * 5000)
        assert "redirect refused" in str(ei.value)
        assert len(str(ei.value)) < 400


# ---------------------------------------------------------------------------
# 上游移植解析（MIT attribution 邏輯保真）
# ---------------------------------------------------------------------------

class TestPortedParsing:
    def test_parse_outcome_prices_json_encoded_strings(self):
        m = {"outcomes": '["Yes", "No"]', "outcomePrices": '["0.35", "0.65"]'}
        assert collector_mod._parse_outcome_prices(m) == [("Yes", 0.35), ("No", 0.65)]

    def test_parse_outcome_prices_native_lists(self):
        m = {"outcomes": ["A", "B"], "outcomePrices": [0.1, 0.9]}
        assert collector_mod._parse_outcome_prices(m) == [("A", 0.1), ("B", 0.9)]

    def test_parse_outcome_prices_malformed_prices_returns_empty(self):
        assert collector_mod._parse_outcome_prices({"outcomes": '["Yes"]', "outcomePrices": "{bad"}) == []
        assert collector_mod._parse_outcome_prices({"outcomes": '["Yes"]'}) == []

    def test_parse_outcome_prices_malformed_outcomes_falls_back_to_placeholder(self):
        m = {"outcomes": "{bad json", "outcomePrices": '["0.5", "0.5"]'}
        assert collector_mod._parse_outcome_prices(m) == [("Outcome 1", 0.5), ("Outcome 2", 0.5)]

    def test_parse_outcome_prices_skips_non_numeric_price(self):
        m = {"outcomes": '["A", "B"]', "outcomePrices": '["0.5", "oops"]'}
        assert collector_mod._parse_outcome_prices(m) == [("A", 0.5)]

    def test_safe_float_and_float_or_none(self):
        assert collector_mod._safe_float("1.5") == 1.5
        assert collector_mod._safe_float(None) == 0.0
        assert collector_mod._safe_float("junk", default=7.0) == 7.0
        assert collector_mod._float_or_none(None) is None
        assert collector_mod._float_or_none("junk") is None
        assert collector_mod._float_or_none(True) is None  # bool 不是研究數值。
        assert collector_mod._float_or_none("2.5") == 2.5
        assert collector_mod._float_or_none(0) == 0.0  # 真 0 保留，缺席才 None。


# ---------------------------------------------------------------------------
# 攤平：零過濾不變量 + raw 保底
# ---------------------------------------------------------------------------

class TestFlatten:
    def test_closed_and_zero_liquidity_markets_are_kept(self):
        # QC memo §1/§2 鐵則：採集端零過濾——lib 原版會丟 closed / 零流動性，
        # 移植版必須全保留。
        ev = _event("9", markets=[
            _market("1", closed=True, uma="resolved", prices='["0", "1"]'),
            _market("2", closed=False),
            _market("3", closed=False, liquidityNum=0.0),
        ])
        rows = collector_mod.flatten_event_rows(
            ev, snapshot_ts_utc="2026-06-11T00:00:00+00:00",
            collector_git_sha="sha", row_source="events_tag")
        assert len(rows) == 3
        closed_row = next(r for r in rows if r["market_id"] == "1")
        assert closed_row["closed"] is True
        assert closed_row["uma_resolution_status"] == "resolved"
        assert closed_row["outcome_prices"] == [0.0, 1.0]

    def test_absent_numeric_fields_become_none_not_zero(self):
        m = {"id": "5", "question": "Q?"}  # 無 liquidity / volume 欄。
        row = collector_mod.flatten_market_row(
            m, _event("9"), snapshot_ts_utc="t", collector_git_sha="s", row_source="events_tag")
        assert row["liquidity_num"] is None
        assert row["volume24hr"] is None
        assert row["parse_error"] is None

    def test_raw_market_and_event_header_preserved(self):
        ev = _event("9", weird_new_field={"drift": 1})
        rows = collector_mod.flatten_event_rows(
            ev, snapshot_ts_utc="t", collector_git_sha="s", row_source="events_tag")
        row = rows[0]
        assert row["raw_market"] == ev["markets"][0]
        assert row["raw_event_header"]["weird_new_field"] == {"drift": 1}
        assert "markets" not in row["raw_event_header"]  # 防 sibling N 倍重複。

    def test_flatten_failure_still_emits_row_with_raw(self):
        class _Boom(dict):
            def get(self, key, default=None):
                if key == "volumeNum":
                    raise RuntimeError("schema drift boom")
                return super().get(key, default)

        m = _Boom(_market("7"))
        row = collector_mod.flatten_market_row(
            m, _event("9"), snapshot_ts_utc="t", collector_git_sha="s", row_source="events_tag")
        assert row["parse_error"] and "schema drift boom" in row["parse_error"]
        assert row["raw_market"] is m  # raw 保底永遠在。

    def test_row_carries_query_set_version_and_lane(self):
        row = collector_mod.flatten_market_row(
            _market(), _event(), snapshot_ts_utc="t", collector_git_sha="abc", row_source="events_tag")
        assert row["query_set_version"] == QUERY_SET_VERSION == "v1"
        assert row["lane"] == LANE_SNAPSHOT
        assert row["collector_git_sha"] == "abc"

    def test_collector_code_has_no_relevance_truncation_tokens(self):
        # 負面不變量：採集端零 relevance 截斷。tokenize 剝 COMMENT/STRING 後驗
        # 禁字（裸 grep 會被 MODULE_NOTE 的合法說明誤紅——既有教訓）。
        src = Path(collector_mod.__file__).read_text(encoding="utf-8")
        code_tokens = []
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                code_tokens.append(tok.string)
        code_only = " ".join(code_tokens)
        for banned in ("_MIN_RELEVANCE", "RESULT_CAP", "token_overlap_relevance",
                       "relevance", "_compute_text_similarity", "_shorten_question",
                       "_passes_topic_filter"):
            assert banned not in code_only, f"collection-side truncation token leaked: {banned}"


# ---------------------------------------------------------------------------
# track-to-resolution 狀態機
# ---------------------------------------------------------------------------

class TestTrackerState:
    def test_new_market_enters_tracking(self):
        st = state_mod.TrackerState()
        st.record_seen(_market("1"), "ev1", seen_at_utc="t0")
        e = st.entries["1"]
        assert e["status"] == state_mod.STATUS_TRACKING
        assert e["first_seen_utc"] == e["last_seen_utc"] == "t0"
        assert e["clob_token_ids"] == ["tok-a", "tok-b"]

    def test_closed_but_unresolved_stays_tracking(self):
        st = state_mod.TrackerState()
        st.record_seen(_market("1", closed=True, uma="proposed"), "ev1")
        assert st.entries["1"]["status"] == state_mod.STATUS_TRACKING

    def test_closed_and_uma_resolved_is_terminal_with_outcome(self):
        st = state_mod.TrackerState()
        st.record_seen(_market("1"), "ev1", seen_at_utc="t0")
        st.record_seen(
            _market("1", closed=True, uma="resolved", prices='["0", "1"]', closedTime="2026-06-10"),
            "ev1", seen_at_utc="t1")
        e = st.entries["1"]
        assert e["status"] == state_mod.STATUS_RESOLVED
        assert e["resolved_at_utc"] == "t1"
        assert e["resolution_outcome_prices"] == '["0", "1"]'
        assert e["closed_time"] == "2026-06-10"

    def test_terminal_status_never_regresses(self):
        st = state_mod.TrackerState()
        st.record_seen(_market("1", closed=True, uma="resolved"), "ev1", seen_at_utc="t0")
        st.record_seen(_market("1", closed=False), "ev1", seen_at_utc="t1")  # 偽回活觀測。
        e = st.entries["1"]
        assert e["status"] == state_mod.STATUS_RESOLVED  # 不回退（calibration 樣本保護）。
        assert e["last_seen_utc"] == "t1"  # last_seen 照常更新。

    def test_fetch_errors_accumulate_to_lost_and_seen_resets(self):
        st = state_mod.TrackerState()
        st.record_seen(_market("1"), "ev1")
        for _ in range(state_mod.LOST_AFTER_CONSECUTIVE_ERRORS - 1):
            st.record_fetch_error("1")
        assert st.entries["1"]["status"] == state_mod.STATUS_TRACKING
        st.record_seen(_market("1"), "ev1")  # 一次成功觀測歸零計數。
        assert st.entries["1"]["consecutive_fetch_errors"] == 0
        for _ in range(state_mod.LOST_AFTER_CONSECUTIVE_ERRORS):
            st.record_fetch_error("1")
        assert st.entries["1"]["status"] == state_mod.STATUS_LOST

    def test_follow_up_ids_excludes_seen_and_terminal(self):
        st = state_mod.TrackerState()
        st.record_seen(_market("1"), "ev1")
        st.record_seen(_market("2"), "ev1")
        st.record_seen(_market("3", closed=True, uma="resolved"), "ev1")
        assert st.follow_up_ids(seen_this_run={"1"}) == ["2"]

    def test_state_round_trip_and_corrupt_file_fail_soft(self, tmp_path):
        st = state_mod.TrackerState()
        st.record_seen(_market("1"), "ev1", seen_at_utc="t0")
        path = state_mod.resolve_state_path(tmp_path)
        state_mod.save_state(st, path)
        assert not path.with_suffix(".json.tmp").exists()  # 原子替換不留 tmp。
        loaded = state_mod.load_state(path)
        assert loaded.entries == st.entries
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"].startswith("polymarket.axis_state")
        path.write_text("{broken", encoding="utf-8")
        assert state_mod.load_state(path).entries == {}  # 壞檔回空不 raise。

    # ---- P-2（修復輪 2026-06-12）：壞 entry 容錯 + 披露桶 ----

    def test_p2_corrupt_entry_missing_status_does_not_kill_sweep(self):
        """缺 status 鍵的壞 entry：任何寫面不得 KeyError 毀整輪（連 snapshot 全丟）。"""
        st = state_mod.TrackerState({"bad": {"market_id": "bad"}})
        st.record_seen(_market("bad"), "ev1")   # 不得 raise；unknown 視同凍結不推進終態。
        st.record_fetch_error("bad")            # 不得 raise。
        assert st.entries["bad"].get("status") is None
        assert st.follow_up_ids(seen_this_run=set()) == []  # 壞 entry 不進 follow-up。

    def test_p2_corrupt_entry_counted_in_unknown_bucket_not_silent(self):
        """壞 entry 流進 counts() 的 unknown 披露桶 → manifest stats.tracker_counts 可見。"""
        st = state_mod.TrackerState({
            "good": {"market_id": "good", "status": state_mod.STATUS_TRACKING,
                     "consecutive_fetch_errors": 0, "clob_token_ids": ["t"]},
            "bad": {"market_id": "bad"},
            "weird": {"market_id": "weird", "status": "not-a-real-status"},
        })
        counts = st.counts()
        assert counts[state_mod.STATUS_TRACKING] == 1
        assert counts[state_mod.STATUS_UNKNOWN] == 2  # 缺鍵 + 未知值都歸披露桶。

    def test_p2_corrupt_entry_survives_load_state_round_trip(self, tmp_path):
        """load_state fail-soft 真的能載入壞 entry —— 載入後全 API 不炸。"""
        path = state_mod.resolve_state_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"schema_version": "x", "entries": {
            "good": {"market_id": "good", "status": state_mod.STATUS_TRACKING,
                     "consecutive_fetch_errors": 0, "clob_token_ids": []},
            "bad": {"market_id": "bad"},
        }}), encoding="utf-8")
        st = state_mod.load_state(path)
        st.record_fetch_error("bad")
        st.record_seen(_market("bad"), "ev")
        assert st.counts()[state_mod.STATUS_UNKNOWN] == 1
        assert st.follow_up_ids(set()) == ["good"]


# ---------------------------------------------------------------------------
# sweep 編排（fake transport 全鏈）
# ---------------------------------------------------------------------------

def _sweep_router(*, tag_events, search_events_by_kw=None, market_by_id=None):
    search_events_by_kw = search_events_by_kw or {}
    market_by_id = market_by_id or {}

    def router(url):
        if "/public-search" in url:
            for kw, events in search_events_by_kw.items():
                if f"q={kw.replace(' ', '+')}" in url:
                    return {"events": events, "pagination": {"hasMore": False}}
            return {"events": [], "pagination": {"hasMore": False}}
        if "/markets/" in url:
            mid = url.rsplit("/", 1)[1].split("?")[0]
            payload = market_by_id.get(mid)
            if payload is None:
                return urllib.error.HTTPError(url, 404, "nf", {}, io.BytesIO(b""))
            return payload
        if "/events" in url:
            if "offset=0" in url:
                return tag_events
            return []
        raise AssertionError(f"unexpected url: {url}")

    return router


class TestSnapshotSweep:
    def test_daily_sweep_dedups_events_and_merges_discovery_sources(self):
        shared = _event("1", markets=[_market("11")])
        only_tag = _event("2", markets=[_market("21"), _market("22")])
        router = _sweep_router(tag_events=[shared, only_tag],
                               search_events_by_kw={"bitcoin": [shared]})
        client, _ = _make_client(router)
        tracker = state_mod.TrackerState()
        result = collector_mod.collect_snapshot_sweep(
            client, tracker, collector_git_sha="sha", tag_slug="crypto",
            keywords=("bitcoin",), keyword_pages=1)
        assert result["stats"]["unique_events"] == 2
        assert result["stats"]["snapshot_rows"] == 3  # 1 + 2，無重複攤平。
        shared_rows = [r for r in result["rows"] if r["event_id"] == "1"]
        assert len(shared_rows) == 1
        assert shared_rows[0]["discovery_queries"] == ["tag:crypto", "kw:bitcoin"]
        assert {"11", "21", "22"} <= set(tracker.entries)

    def test_daily_sweep_follow_up_fetches_unseen_tracked_market(self):
        # 前輪 tracked 的 market 本輪枚舉沒出現（已 closed 掉出 active 列表）→
        # 必須走 /markets/{id} 續抓到 resolution（QC memo §2 鐵則）。
        tracker = state_mod.TrackerState()
        tracker.record_seen(_market("99"), "ev9", seen_at_utc="t-1")
        resolved_market = _market("99", closed=True, uma="resolved", prices='["1", "0"]')
        router = _sweep_router(tag_events=[_event("1", markets=[_market("11")])],
                               market_by_id={"99": resolved_market})
        client, calls = _make_client(router)
        result = collector_mod.collect_snapshot_sweep(
            client, tracker, collector_git_sha="sha", tag_slug="crypto",
            keywords=(), keyword_pages=0)
        assert any("/markets/99" in c for c in calls)
        follow_rows = [r for r in result["rows"] if r["row_source"] == "resolution_follow_up"]
        assert len(follow_rows) == 1 and follow_rows[0]["market_id"] == "99"
        assert tracker.entries["99"]["status"] == state_mod.STATUS_RESOLVED
        assert result["stats"]["follow_up"] == {"attempted": 1, "ok": 1, "failed": 0}
        assert len(result["raw_markets"]) == 1

    def test_daily_sweep_follow_up_404_records_error_not_crash(self):
        tracker = state_mod.TrackerState()
        tracker.record_seen(_market("404404"), "ev9")
        router = _sweep_router(tag_events=[])
        client, _ = _make_client(router)
        result = collector_mod.collect_snapshot_sweep(
            client, tracker, collector_git_sha="sha", tag_slug="crypto",
            keywords=(), keyword_pages=0)
        assert result["stats"]["follow_up"]["failed"] == 1
        assert tracker.entries["404404"]["consecutive_fetch_errors"] == 1
        assert any("follow_up:404404" in e for e in result["errors"])

    def test_hourly_topn_single_page_no_keyword_no_follow_up(self):
        tracker = state_mod.TrackerState()
        tracker.record_seen(_market("99"), "ev9")  # 有 tracked 也不該 follow-up。
        captured: list[str] = []

        def router(url):
            captured.append(url)
            assert "/events" in url and "/markets/" not in url and "/public-search" not in url
            return [_event("1", markets=[_market("11")])]

        client, _ = _make_client(router)
        result = collector_mod.collect_snapshot_sweep(
            client, tracker, collector_git_sha="sha", tag_slug="crypto",
            keywords=tuple(QUERY_SET_V1_KEYWORDS), keyword_pages=2, top_n=50)
        assert len(captured) == 1
        assert "order=volume24hr" in captured[0] and "limit=50" in captured[0]
        assert "ascending=false" in captured[0]
        assert result["stats"]["mode_top_n"] == 50
        assert "follow_up" not in result["stats"]

    def test_keyword_failure_is_isolated(self):
        def router(url):
            if "/public-search" in url:
                if "q=bitcoin" in url and "q=bitcoin+price" not in url:
                    return urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b""))
                return {"events": [_event("2", markets=[_market("21")])],
                        "pagination": {"hasMore": False}}
            if "/events" in url:
                return [] if "offset" not in url or "offset=0" in url else []
            raise AssertionError(url)

        client, _ = _make_client(router, retries=0)
        tracker = state_mod.TrackerState()
        result = collector_mod.collect_snapshot_sweep(
            client, tracker, collector_git_sha="sha", tag_slug="crypto",
            keywords=("bitcoin", "etf"), keyword_pages=1)
        assert any(e.startswith("keyword:bitcoin") for e in result["errors"])
        assert result["stats"]["unique_events"] == 1  # etf 那路照常收。


# ---------------------------------------------------------------------------
# retrospective lane
# ---------------------------------------------------------------------------

class TestRetrospective:
    def test_prices_history_rows_marked_retrospective_and_empty_history_kept(self):
        def router(url):
            assert url.startswith(collector_mod.CLOB_BASE)
            if "market=tok-full" in url:
                return {"history": [{"t": 1, "p": 0.5}]}
            return {"history": []}

        client, _ = _make_client(router)
        result = collector_mod.collect_prices_history(
            client,
            token_jobs=[{"market_id": "1", "clob_token_id": "tok-full"},
                        {"market_id": "2", "clob_token_id": "tok-empty"}],
            interval="max", fidelity=720, start_ts=None, end_ts=None,
            collector_git_sha="sha", now_iso="t0")
        assert len(result["rows"]) == 2
        for row in result["rows"]:
            assert row["lane"] == LANE_RETROSPECTIVE
            assert row["retrospective"] is True
            assert row["retrieved_at_utc"] == "t0"  # 拉取日標記（永不冒充當時採集）。
        empty = next(r for r in result["rows"] if r["clob_token_id"] == "tok-empty")
        assert empty["n_points"] == 0 and empty["fetch_error"] is None  # 已知限制照存。

    def test_single_token_failure_isolated(self):
        def router(url):
            if "market=tok-bad" in url:
                return urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b""))
            return {"history": [{"t": 1, "p": 0.4}]}

        client, _ = _make_client(router, retries=0)
        result = collector_mod.collect_prices_history(
            client,
            token_jobs=[{"market_id": "1", "clob_token_id": "tok-bad"},
                        {"market_id": "2", "clob_token_id": "tok-ok"}],
            interval=None, fidelity=None, start_ts=None, end_ts=None,
            collector_git_sha="sha")
        bad = next(r for r in result["rows"] if r["clob_token_id"] == "tok-bad")
        ok = next(r for r in result["rows"] if r["clob_token_id"] == "tok-ok")
        assert bad["fetch_error"] and bad["history"] is None
        assert ok["n_points"] == 1
        assert len(result["errors"]) == 1


# ---------------------------------------------------------------------------
# artifact：manifest 完整性 / append-only / lane 隔離
# ---------------------------------------------------------------------------

def _snapshot_run(tmp_path, run_id="daily-20260611T000000Z"):
    rows = [collector_mod.flatten_market_row(
        _market(), _event(), snapshot_ts_utc="t", collector_git_sha="s", row_source="events_tag")]
    return artifact_mod.write_run(
        lane=LANE_SNAPSHOT, mode="daily", run_id=run_id,
        repo_root=tmp_path,  # 非 git dir → provenance fail-soft "unknown"。
        stats={"snapshot_rows": 1}, errors=[],
        snapshot_rows=rows, raw_events=[{"event": _event()}], raw_markets=[],
        artifact_root=tmp_path / "runs", parquet_mirror=False)


class TestArtifact:
    def test_manifest_and_index_sha256_reverify(self, tmp_path):
        import hashlib
        out = _snapshot_run(tmp_path)
        run_dir = Path(out["written"]["run_dir"])
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["lane"] == LANE_SNAPSHOT
        assert manifest["retrospective"] is False
        assert manifest["point_in_time"] is True
        assert manifest["query_set_version"] == "v1"
        assert manifest["upstream_attribution"] == UPSTREAM_ATTRIBUTION
        assert manifest["upstream_attribution"]["source_commit"].startswith("12215841")
        index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
        names = {a["name"] for a in index["artifacts"]}
        assert names == {"snapshots.jsonl", "raw_events.jsonl", "raw_markets.jsonl", "manifest.json"}
        for entry in index["artifacts"]:
            digest = hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest()
            assert digest == entry["sha256"]  # sha256 必須可重驗。

    def test_append_only_second_write_same_run_id_raises(self, tmp_path):
        _snapshot_run(tmp_path)
        with pytest.raises(FileExistsError):
            _snapshot_run(tmp_path)  # 同 run_id 重寫 = 覆寫舊 snapshot，必拒。

    def test_lane_isolation_rejects_cross_lane_payload(self, tmp_path):
        with pytest.raises(ValueError, match="snapshot lane"):
            artifact_mod.write_run(
                lane=LANE_SNAPSHOT, mode="daily", run_id="x1", repo_root=tmp_path,
                stats={}, errors=[], snapshot_rows=[], prices_history_rows=[],
                artifact_root=tmp_path / "runs", parquet_mirror=False)
        with pytest.raises(ValueError, match="retrospective lane"):
            artifact_mod.write_run(
                lane=LANE_RETROSPECTIVE, mode="retrospective", run_id="x2", repo_root=tmp_path,
                stats={}, errors=[], snapshot_rows=[], prices_history_rows=[],
                artifact_root=tmp_path / "runs", parquet_mirror=False)
        with pytest.raises(ValueError, match="unknown lane"):
            artifact_mod.write_run(
                lane="bogus", mode="daily", run_id="x3", repo_root=tmp_path,
                stats={}, errors=[], artifact_root=tmp_path / "runs", parquet_mirror=False)

    def test_retrospective_run_writes_only_history_file(self, tmp_path):
        out = artifact_mod.write_run(
            lane=LANE_RETROSPECTIVE, mode="retrospective", run_id="retro-1",
            repo_root=tmp_path, stats={}, errors=[],
            prices_history_rows=[{"lane": LANE_RETROSPECTIVE, "history": []}],
            artifact_root=tmp_path / "runs", parquet_mirror=False)
        run_dir = Path(out["written"]["run_dir"])
        files = {p.name for p in run_dir.iterdir()}
        assert "prices_history.jsonl" in files
        assert "snapshots.jsonl" not in files  # lane 檔案集合互斥。
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["retrospective"] is True and manifest["point_in_time"] is False

    def test_parquet_mirror_skips_without_duckdb(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "duckdb", None)  # import duckdb → ImportError。
        out = artifact_mod.mirror_jsonl_to_parquet(tmp_path)
        assert out == {"parquet_mirror": "skipped", "reason": "duckdb_not_available"}

    def test_p1_parquet_conversion_failure_no_residue_and_partial(self, tmp_path, monkeypatch):
        """P-1（修復輪 2026-06-12）：轉換中途炸 → 最終路徑零 0-byte 殘檔、tmp 已清、status=partial。

        2026-06-11 真 smoke 實測：舊直寫版在 raw_events.jsonl 轉換失敗後留 0-byte
        raw_events.parquet（manifest 記 failed 但檔在 = 被誤認有效輸出的場景）。
        """
        import sys
        import types

        run = tmp_path / "run1"
        run.mkdir()
        (run / "aaa_good.jsonl").write_text('{"x": 1}\n', encoding="utf-8")
        (run / "bbb_bad.jsonl").write_text('{"x": 2}\n', encoding="utf-8")

        class _Rel:
            def __init__(self, src):
                self._src = src

            def write_parquet(self, out_path):
                if "bbb_bad" in self._src:
                    Path(out_path).write_bytes(b"")  # 模擬轉換中途死：目標已創 0-byte。
                    raise RuntimeError("conversion exploded")
                Path(out_path).write_bytes(b"PAR1-fake")

        class _Con:
            def read_json(self, src, format=None):
                return _Rel(src)

            def close(self):
                pass

        monkeypatch.setitem(
            sys.modules, "duckdb", types.SimpleNamespace(connect=lambda: _Con()))
        out = artifact_mod.mirror_jsonl_to_parquet(run)
        assert out["parquet_mirror"] == "partial"
        assert out["files_ok"] == ["aaa_good.jsonl"]
        assert out["files_failed"] == ["bbb_bad.jsonl"]
        assert (run / "aaa_good.parquet").read_bytes() == b"PAR1-fake"
        # P-1 主斷言：最終路徑絕不出現殘檔（舊直寫版此處留 0-byte bbb_bad.parquet）。
        assert not (run / "bbb_bad.parquet").exists()
        assert not (run / "bbb_bad.parquet.tmp").exists()  # tmp 殘檔已 unlink。


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

class TestCli:
    def test_retrospective_requires_explicit_scope(self, tmp_path):
        from polymarket_axis import cli as cli_mod
        with pytest.raises(SystemExit):
            cli_mod.main(["--mode", "retrospective", "--data-root", str(tmp_path)])

    def test_daily_end_to_end_writes_run_dir_and_state(self, tmp_path, monkeypatch):
        from polymarket_axis import cli as cli_mod

        router = _sweep_router(tag_events=[_event("1", markets=[_market("11")])])
        real_client_cls = collector_mod.ThrottledJsonClient

        def patched_client(**kwargs):
            calls: list[str] = []

            def fake_urlopen(req, timeout=None):
                calls.append(req.full_url)
                result = router(req.full_url)
                if isinstance(result, Exception):
                    raise result
                return _FakeResponse(result)

            kwargs.update({"urlopen": fake_urlopen, "sleep": lambda s: None, "min_interval_s": 0.0})
            return real_client_cls(**kwargs)

        monkeypatch.setattr(cli_mod.collector_mod, "ThrottledJsonClient", patched_client)
        rc = cli_mod.main([
            "--mode", "daily", "--data-root", str(tmp_path),
            "--keyword-pages", "0", "--no-parquet-mirror",
            "--run-id", "daily-test-1",
        ])
        assert rc == 0
        run_dir = tmp_path / "polymarket_axis_runs" / "daily-test-1"
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "snapshots.jsonl").exists()
        state_path = state_mod.resolve_state_path(tmp_path)
        assert state_path.exists()
        loaded = state_mod.load_state(state_path)
        assert "11" in loaded.entries


# ---------------------------------------------------------------------------
# 真實 API 煙測（opt-in：打真網路，默認 skip；報告附樣例由任務輪一次性執跑）
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("OPENCLAW_POLYMARKET_SMOKE") != "1",
                    reason="real-API smoke is opt-in (set OPENCLAW_POLYMARKET_SMOKE=1)")
def test_real_api_smoke_crypto_tag_one_page():
    client = collector_mod.ThrottledJsonClient()
    events, stats = collector_mod.fetch_events_by_tag(
        client, tag_slug="crypto", max_pages=1, page_limit=20)
    assert stats["pages"] == 1 and events, "crypto tag page 1 must return events"
    rows = collector_mod.flatten_event_rows(
        events[0], snapshot_ts_utc="smoke", collector_git_sha="smoke", row_source="events_tag")
    assert rows, "first crypto event must flatten to >=1 market row"
    row = rows[0]
    # schema 假設釘子：這些鍵必須存在（值可 None——fail-soft），缺鍵 = 漂移警報。
    for key in ("event_id", "market_id", "outcomes", "outcome_prices",
                "closed", "active", "raw_market", "raw_event_header"):
        assert key in row

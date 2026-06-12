#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：gate_b_watch 單元測試。覆蓋 Gate-B 公告窗口解析、PreLaunch live
  狀態判斷、去重告警、failure meta-alert、artifact 狀態與隔離紅線。
"""

import datetime as dt
import inspect
import json
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gate_b_watch as gbw  # noqa: E402

NOW = dt.datetime(2026, 6, 12, 10, 0, tzinfo=dt.timezone.utc).timestamp()


def _ms(year, month, day, hour=0, minute=0):
    return int(dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc).timestamp() * 1000)


def _announcement(
    title,
    *,
    description="",
    url="https://announcements.bybit.com/en-US/article/sample-blt123/",
    publish=None,
    tags=("Derivatives",),
):
    return {
        "title": title,
        "description": description,
        "url": url,
        "publishTime": publish if publish is not None else _ms(2026, 6, 12, 9),
        "dateTimestamp": publish if publish is not None else _ms(2026, 6, 12, 9),
        "type": {"key": "new_crypto", "title": "New Crypto"},
        "tags": list(tags),
    }


def _prelaunch(symbol="BPUSDT", *, launch=None, phase="ContinuousTrading"):
    return {
        "symbol": symbol,
        "status": "PreLaunch",
        "launchTime": str(launch if launch is not None else _ms(2026, 3, 16, 5, 45)),
        "preListingInfo": {"curAuctionPhase": phase, "phases": []},
    }


def _v5_list(rows):
    return {"retCode": 0, "retMsg": "OK", "result": {"total": len(rows), "list": rows}}


class FakeHTTPResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self._body


class MultiOpener:
    def __init__(self, *, announcement_pages=None, prelaunch=None, exc=None):
        self.announcement_pages = announcement_pages or {1: []}
        self.prelaunch = prelaunch or []
        self.exc = exc
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req.full_url)
        if self.exc is not None:
            raise self.exc
        if "/v5/announcements/index" in req.full_url:
            query = dict((k, v[0]) for k, v in __import__("urllib.parse").parse.parse_qs(__import__("urllib.parse").parse.urlsplit(req.full_url).query).items())
            page = int(query.get("page", "1"))
            return FakeHTTPResponse(_v5_list(self.announcement_pages.get(page, [])))
        if "/v5/market/instruments-info" in req.full_url:
            return FakeHTTPResponse(_v5_list(self.prelaunch))
        raise AssertionError(f"unexpected url: {req.full_url}")


class AlertRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, subject, body, severity, data_dir):
        self.calls.append(
            {"subject": subject, "body": body, "severity": severity, "data_dir": data_dir}
        )


def _no_sleep(_seconds):
    return None


def _latest(data_dir):
    return json.loads((Path(data_dir) / gbw.ARTIFACT_DIR / gbw.LATEST_FILE).read_text(encoding="utf-8"))


def _run(tmp_path, *, announcement_pages=None, prelaunch=None, opener=None, alert=None, dry_run=False, now=NOW):
    opener = opener or MultiOpener(announcement_pages=announcement_pages, prelaunch=prelaunch)
    alert = alert or AlertRecorder()
    rc = gbw.run_once(
        str(tmp_path),
        opener=opener,
        alert_fn=alert,
        now=now,
        dry_run=dry_run,
        announcement_pages=1,
        sleep_fn=_no_sleep,
    )
    return rc, opener, alert, _latest(tmp_path)


def test_pre_market_listing_inside_start_window_alerts(tmp_path):
    item = _announcement(
        "Bybit to List Pre-Market Perpetuals for ABCUSDT",
        description="ABCUSDT Pre-Market Perpetual starts on Jun 12, 2026, 1:00PM UTC.",
    )
    rc, opener, alert, latest = _run(tmp_path, announcement_pages={1: [item]}, prelaunch=[])

    assert rc == 0
    assert latest["status"] == gbw.STATUS_ACTIONABLE_START
    assert latest["candidate_counts"]["start_now"] == 1
    assert latest["candidates"][0]["symbol"] == "ABCUSDT"
    assert latest["candidates"][0]["event_time_utc"] == "2026-06-12T13:00:00Z"
    assert len(alert.calls) == 1
    assert "[GATE-B-WATCH][P1]" in alert.calls[0]["subject"]
    assert "aeg_gate_b_probe.py" in alert.calls[0]["body"]
    assert "type=new_crypto" in opener.requests[0]


def test_standard_conversion_future_is_schedule_candidate(tmp_path):
    item = _announcement(
        "Bybit to convert MEGAUSDT Pre-Market Perpetual Contract to standard Perpetual Contract",
        description="The conversion will occur on Jun 13, 2026, 6:30AM UTC.",
        url="https://announcements.bybit.com/en-US/article/mega-blt999/",
    )
    rc, _opener, alert, latest = _run(tmp_path, announcement_pages={1: [item]}, prelaunch=[])

    assert rc == 0
    assert latest["status"] == gbw.STATUS_ACTIONABLE_SCHEDULE
    candidate = latest["candidates"][0]
    assert candidate["trigger_type"] == gbw.TRIGGER_STANDARD_CONVERSION
    assert candidate["recommended_action"] == gbw.ACTION_SCHEDULE
    assert candidate["event_time_utc"] == "2026-06-13T06:30:00Z"
    assert len(alert.calls) == 1


def test_stale_historical_pre_market_candidate_does_not_alert_or_set_active_status(tmp_path):
    item = _announcement(
        "Bybit to convert OLDUSDT Pre-Market Perpetual Contract to standard Perpetual Contract",
        description="The conversion occurred on Apr 30, 2026, 8:00AM UTC.",
        publish=_ms(2026, 4, 29, 8),
    )
    rc, _opener, alert, latest = _run(tmp_path, announcement_pages={1: [item]}, prelaunch=[])

    assert rc == 0
    assert latest["status"] == gbw.STATUS_NO_CANDIDATE
    assert latest["candidate_counts"]["alertable"] == 0
    assert latest["candidates"][0]["recommended_action"] == gbw.ACTION_STALE
    assert alert.calls == []


def test_old_continuous_trading_prelaunch_is_watch_conversion_not_alert(tmp_path):
    rc, _opener, alert, latest = _run(tmp_path, announcement_pages={1: []}, prelaunch=[_prelaunch()])

    assert rc == 0
    assert latest["status"] == gbw.STATUS_WATCH_ONLY
    candidate = latest["candidates"][0]
    assert candidate["symbol"] == "BPUSDT"
    assert candidate["recommended_action"] == gbw.ACTION_WATCH_CONVERSION
    assert candidate["cur_auction_phase"] == "ContinuousTrading"
    assert alert.calls == []


def test_call_auction_prelaunch_alerts_start_now(tmp_path):
    row = _prelaunch("NEWUSDT", launch=_ms(2026, 6, 12, 11), phase="CallAuction")
    rc, _opener, alert, latest = _run(tmp_path, announcement_pages={1: []}, prelaunch=[row])

    assert rc == 0
    assert latest["status"] == gbw.STATUS_ACTIONABLE_START
    assert latest["candidates"][0]["recommended_action"] == gbw.ACTION_START_NOW
    assert latest["candidates"][0]["launch_time_utc"] == "2026-06-12T11:00:00Z"
    assert len(alert.calls) == 1


def test_seen_candidate_fingerprint_dedupes_repeated_alerts(tmp_path):
    item = _announcement(
        "Bybit to List Pre-Market Perpetuals for ABCUSDT",
        description="ABCUSDT Pre-Market Perpetual starts on Jun 12, 2026, 1:00PM UTC.",
    )
    alert = AlertRecorder()
    rc1, _opener1, _alert1, latest1 = _run(
        tmp_path, announcement_pages={1: [item]}, prelaunch=[], alert=alert
    )
    rc2, _opener2, _alert2, latest2 = _run(
        tmp_path, announcement_pages={1: [item]}, prelaunch=[], alert=alert
    )

    assert rc1 == rc2 == 0
    assert latest1["alerts_sent"] == 1
    assert latest2["alerts_sent"] == 0
    assert len(alert.calls) == 1


def test_consecutive_failures_emit_one_meta_alert_at_threshold(tmp_path):
    opener = MultiOpener(exc=urllib.error.URLError("boom"))
    alert = AlertRecorder()

    for _ in range(gbw.META_ALERT_AFTER_FAILURES):
        rc = gbw.run_once(
            str(tmp_path),
            opener=opener,
            alert_fn=alert,
            now=NOW,
            announcement_pages=1,
            sleep_fn=_no_sleep,
        )
        assert rc == 0

    assert len(alert.calls) == 1
    assert "[GATE-B-WATCH][META]" in alert.calls[0]["subject"]
    latest = _latest(tmp_path)
    assert latest["status"] == gbw.STATUS_SOURCE_FAILURE


def test_static_isolation_no_runtime_or_db_routes():
    src = inspect.getsource(gbw)
    forbidden = (
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "place_order",
        "cancel_order",
        "X-BAPI-SIGN",
        "OPENCLAW_ALLOW_MAINNET",
        "control_api_v1",
        "program_code",
        "rust/",
    )
    for needle in forbidden:
        assert needle not in src, f"forbidden route token found: {needle}"

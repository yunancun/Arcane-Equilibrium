#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：bybit_announcement_sentinel 單元測試（BB advisory §10 驗收清單對應）。
主要類/函數：去重鍵（normalize_url/blt/sha256 fallback）、severity 分類映射全分支、
  首輪 baseline flood guard、seen-set 差集增量、>90d 修剪、fail-quiet + 連續失敗
  meta-alert（恰一條）、單輪告警上限彙總、untrusted 紀律（body 不展開 description）、
  watchlist runtime 注入、emitter 簽名 smoke、alert-only 結構斷言、每輪恰 1 call。
依賴：bybit_announcement_sentinel.py、engine_watchdog.py（sibling path-insert）、pytest。
硬邊界（測試隔離鐵則，mirror test_incident_sentinel）：
  - 0 真 urlopen / 0 真外發：fetch 全吃注入 opener；alert 全吃 recorder。
  - 全部 tmp_path；不觸真 OPENCLAW_DATA_DIR；env 改動 finally 還原。
  - 0 DSN / 0 DB：本哨兵本就零 DB，測試結構性斷言鎖死這一點。
"""

import inspect
import json
import os
import sys
import time
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bybit_announcement_sentinel as bbs  # noqa: E402

NOW = 1_781_172_074.0  # 2026-06-11 前後（對齊 BB 實證樣本 publishTime）

# BB §1.3 實證樣本形 url（尾帶 -blt<hex>/）。
SAMPLE_URL = (
    "https://announcements.bybit.com/en-US/article/"
    "delisting-of-tonusdt-perpetual-contract-blt9656c79c61b0a2bd/"
)


# ───────────────────────────────────────────────────────────────────────────
# 測試替身：HTTP opener（V5 envelope）+ alert recorder。
# ───────────────────────────────────────────────────────────────────────────


def _item(
    title="Delisting of TONUSDT Perpetual Contract",
    type_key="delistings",
    tags=("Derivatives", "Institutions", "Delistings"),
    url=SAMPLE_URL,
    description="Bybit will delist TONUSDT. SECRET-DESC-MARKER do not expand.",
    publish=1_781_172_074_000,
):
    return {
        "title": title,
        "description": description,
        "type": {"title": type_key.replace("_", " ").title(), "key": type_key},
        "tags": list(tags),
        "url": url,
        "dateTimestamp": publish,
        "publishTime": publish,
    }


def _v5_payload(items, ret_code=0, ret_msg="OK"):
    return {
        "retCode": ret_code,
        "retMsg": ret_msg,
        "result": {"total": len(items), "list": items},
        "retExtInfo": {},
        "time": 1_781_172_074_000,
    }


class FakeHTTPResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self._body


class RecordingOpener:
    """記錄每次請求的 urlopen 替身（驗每輪恰 1 call + 請求參數）。"""

    def __init__(self, payload=None, status=200, exc=None, raw=None):
        self.requests = []
        self._payload = payload
        self._status = status
        self._exc = exc
        self._raw = raw

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        if self._exc is not None:
            raise self._exc
        body = self._raw if self._raw is not None else json.dumps(self._payload).encode("utf-8")
        return FakeHTTPResponse(body, self._status)


class AlertRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, subject, body, severity, data_dir):
        self.calls.append(
            {"subject": subject, "body": body, "severity": severity, "data_dir": data_dir}
        )


def _no_sleep(_seconds):
    return None


def _run(data_dir, items=None, *, opener=None, alert=None, now=NOW, dry_run=False):
    """run_once 便捷包裝：默認單頁 items + recorder + 不睡。"""
    opener = opener or RecordingOpener(_v5_payload(items or []))
    alert = alert if alert is not None else AlertRecorder()
    rc = bbs.run_once(
        str(data_dir), opener=opener, alert_fn=alert, now=now,
        dry_run=dry_run, sleep_fn=_no_sleep,
    )
    return rc, opener, alert


def _state(data_dir):
    return json.loads((Path(data_dir) / bbs.STATE_FILE).read_text(encoding="utf-8"))


def _baseline(data_dir, items=None):
    """先跑一輪 baseline（全標 seen 不告警），讓後續輪走增量路徑。"""
    rc, _, alert = _run(data_dir, items or [])
    assert rc == 0 and alert.calls == []


# ───────────────────────────────────────────────────────────────────────────
# 去重鍵（BB §4）
# ───────────────────────────────────────────────────────────────────────────


class TestDedupKeys:
    def test_normalize_strips_query_fragment_and_trailing_slash(self):
        base = "https://announcements.bybit.com/en-US/article/x-blt0abc/"
        variants = [
            base,
            base.rstrip("/"),
            base + "?utm_source=tg",
            base + "#section",
            base + "?a=1#b",
        ]
        keys = {bbs.normalize_url(u) for u in variants}
        assert len(keys) == 1
        assert keys.pop() == "https://announcements.bybit.com/en-US/article/x-blt0abc"

    def test_normalize_lowercases_scheme_and_host_keeps_path_case(self):
        norm = bbs.normalize_url("HTTPS://Announcements.Bybit.com/en-US/Article/X-blt0a/")
        assert norm == "https://announcements.bybit.com/en-US/Article/X-blt0a"

    def test_normalize_rejects_malformed(self):
        for bad in (None, "", "   ", 42, "not a url", "/relative/only"):
            assert bbs.normalize_url(bad) is None

    def test_blt_id_extracted_from_url_tail(self):
        norm = bbs.normalize_url(SAMPLE_URL)
        assert bbs.extract_blt_id(norm) == "blt9656c79c61b0a2bd"

    def test_blt_id_none_when_absent(self):
        assert bbs.extract_blt_id("https://announcements.bybit.com/en-US/article/no-uid") is None

    def test_derive_key_prefers_url(self):
        key, blt = bbs.derive_article_key(_item())
        assert key.startswith("https://announcements.bybit.com/")
        assert blt == "blt9656c79c61b0a2bd"

    def test_derive_key_sha256_fallback_without_url(self):
        item = _item(url=None)
        key, blt = bbs.derive_article_key(item)
        assert key.startswith("sha256:")
        assert blt is None
        # 同 title+publishTime → 同 fallback key（穩定）。
        key2, _ = bbs.derive_article_key(_item(url=""))
        assert key == key2

    def test_derive_key_none_when_url_and_title_both_missing(self):
        assert bbs.derive_article_key({"description": "x"}) == (None, None)

    def test_no_timestamp_watermark_behavioral(self, tmp_path):
        """BB F-2（load-bearing）：增量=seen-set 差集，禁 timestamp watermark。
        行為證明：比已見條目「更舊」（publishTime/dateTimestamp 都更小）的未見公告
        仍必須告警 —— 任何高水位線法在排序 inversion（BB §1.3 實證）下必漏此件。"""
        newer = _item(publish=1_781_172_074_000)
        _baseline(tmp_path, [newer])
        older_unseen = _item(
            title="Old-dated but never seen delisting",
            url="https://announcements.bybit.com/en-US/article/old-blt0dd/",
            publish=1_781_172_074_000 - 30 * 86400 * 1000,  # 早 30 天
        )
        rc, _, alert = _run(tmp_path, [newer, older_unseen])
        assert rc == 0
        assert len(alert.calls) == 1  # watermark 法會誤判「已處理過」而漏件

    def test_no_watermark_identifier_in_code_tokens(self):
        """結構輔證（剝 COMMENT/STRING 只看真碼，防 docstring 解釋文誤紅）：
        碼內無 watermark / 高水位線 identifier。"""
        import io
        import tokenize
        src = inspect.getsource(bbs)
        code = " ".join(
            t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)
        )
        for needle in ("watermark", "max_seen_ts", "high_water"):
            assert needle not in code, f"watermark-style identifier found: {needle}"


# ───────────────────────────────────────────────────────────────────────────
# severity 分類映射（BB §2）
# ───────────────────────────────────────────────────────────────────────────


class TestClassify:
    def _sev(self, **kw):
        watchlist = kw.pop("watchlist", ())
        return bbs.classify_announcement(_item(**kw), watchlist)

    def test_delistings_p0_unconditional(self):
        sev, _ = self._sev(type_key="delistings", tags=(), title="Anything", description="")
        assert sev == bbs.SEV_P0

    def test_maintenance_p0_unconditional(self):
        sev, _ = self._sev(type_key="maintenance_updates", tags=(), title="W", description="")
        assert sev == bbs.SEV_P0

    def test_product_updates_default_p1(self):
        sev, _ = self._sev(type_key="product_updates", tags=("Spot",),
                           title="Some copy change", description="cosmetic")
        assert sev == bbs.SEV_P1

    def test_product_updates_tag_escalates_p0(self):
        sev, matched = self._sev(type_key="product_updates", tags=("Derivatives",),
                                 title="Plain title", description="plain")
        assert sev == bbs.SEV_P0
        assert "tag:derivatives" in matched

    def test_product_updates_keyword_escalates_p0(self):
        sev, matched = self._sev(type_key="product_updates", tags=("Spot",),
                                 title="Adjustment to risk limit tiers", description="")
        assert sev == bbs.SEV_P0
        assert any(m.startswith("kw:risk_limit") for m in matched)

    def test_new_crypto_derivatives_p1_spot_p2(self):
        sev_d, _ = self._sev(type_key="new_crypto", tags=("Derivatives",),
                             title="New listing X", description="")
        sev_s, _ = self._sev(type_key="new_crypto", tags=("Spot",),
                             title="New listing X", description="")
        assert (sev_d, sev_s) == (bbs.SEV_P1, bbs.SEV_P2)

    def test_news_default_p2_tag_p1_keyword_p0(self):
        sev0, _ = self._sev(type_key="latest_bybit_news", tags=(),
                            title="Community update", description="hello")
        sev1, _ = self._sev(type_key="latest_bybit_news", tags=("Institutions",),
                            title="Community update", description="hello")
        sev2, _ = self._sev(type_key="latest_bybit_news", tags=(),
                            title="API maintenance notice", description="")
        assert (sev0, sev1, sev2) == (bbs.SEV_P2, bbs.SEV_P1, bbs.SEV_P0)

    def test_activities_and_fiat_p2_ignore(self):
        for tk in ("latest_activities", "new_fiat_listings"):
            sev, _ = self._sev(type_key=tk, tags=("Derivatives",),
                               title="Football VIP raffle", description="")
            assert sev == bbs.SEV_P2

    def test_unknown_type_key_p1_wide_net(self):
        for tk in ("other", "brand_new_bucket", ""):
            sev, _ = self._sev(type_key=tk, tags=(), title="X", description="")
            assert sev == bbs.SEV_P1

    def test_keyword_word_boundary_capital_not_api(self):
        """BB §2：word-boundary 防 `capital` 誤命中 `api`。"""
        _, matched = self._sev(type_key="latest_bybit_news", tags=(),
                               title="Capital gains report", description="capitalize")
        assert not any(m == "kw:api" for m in matched)

    def test_watchlist_runtime_injection_marks_symbol(self):
        """BB 驗收 #3：25-symbol 名單 runtime 注入（env），非硬編碼。"""
        old = os.environ.get("OPENCLAW_BB_SENTINEL_WATCHLIST")
        os.environ["OPENCLAW_BB_SENTINEL_WATCHLIST"] = "tonusdt, BTCUSDT"
        try:
            wl = bbs._load_watchlist()
            assert wl == ("TONUSDT", "BTCUSDT")
            _, matched = self._sev(watchlist=wl)
            assert "watchlist:TONUSDT" in matched
        finally:
            if old is None:
                os.environ.pop("OPENCLAW_BB_SENTINEL_WATCHLIST", None)
            else:
                os.environ["OPENCLAW_BB_SENTINEL_WATCHLIST"] = old

    def test_watchlist_empty_without_env_no_builtin_default(self):
        """env 未設 → 空名單（無任何內建 symbol 默認；行為層驗非硬編碼，
        裸 source-grep 會被 docstring 的 csv 範例誤紅）。"""
        old = os.environ.pop("OPENCLAW_BB_SENTINEL_WATCHLIST", None)
        try:
            assert bbs._load_watchlist() == ()
        finally:
            if old is not None:
                os.environ["OPENCLAW_BB_SENTINEL_WATCHLIST"] = old


# ───────────────────────────────────────────────────────────────────────────
# fetch（V5 envelope 衛生 + 每輪恰 1 call + 請求形）
# ───────────────────────────────────────────────────────────────────────────


class TestFetch:
    def test_request_shape_locale_page_limit_no_type(self):
        opener = RecordingOpener(_v5_payload([_item()]))
        items = bbs.fetch_announcements(opener=opener)
        assert len(items) == 1
        assert len(opener.requests) == 1
        url = opener.requests[0].full_url
        assert url.startswith("https://api.bybit.com/v5/announcements/index?")
        assert "locale=en-US" in url and "page=1" in url and "limit=50" in url
        assert "type=" not in url  # BB §3：不傳 type，本地分類

    def test_ret_code_nonzero_raises(self):
        with pytest.raises(bbs.FetchError, match="retCode"):
            bbs.fetch_announcements(opener=RecordingOpener(_v5_payload([], ret_code=10006)))

    def test_http_non_200_raises(self):
        with pytest.raises(bbs.FetchError, match="http_status_403"):
            bbs.fetch_announcements(opener=RecordingOpener(_v5_payload([]), status=403))

    def test_network_error_raises_fetch_error(self):
        with pytest.raises(bbs.FetchError, match="http_error"):
            bbs.fetch_announcements(opener=RecordingOpener(exc=ConnectionRefusedError("x")))

    def test_bad_json_raises(self):
        with pytest.raises(bbs.FetchError, match="parse_error"):
            bbs.fetch_announcements(opener=RecordingOpener(raw=b"<html>ban page</html>"))

    def test_missing_list_raises(self):
        with pytest.raises(bbs.FetchError, match="result.list_missing"):
            bbs.fetch_announcements(opener=RecordingOpener({"retCode": 0, "result": {}}))

    def test_non_dict_rows_filtered(self):
        payload = _v5_payload([_item(), "junk", 42])
        # json round-trip 後 list 含非 dict 條目 → 過濾不炸。
        items = bbs.fetch_announcements(opener=RecordingOpener(payload))
        assert len(items) == 1

    def test_empty_list_is_not_error(self):
        assert bbs.fetch_announcements(opener=RecordingOpener(_v5_payload([]))) == []


# ───────────────────────────────────────────────────────────────────────────
# run_once：baseline / 增量 / 去重 / 修剪 / fail-quiet
# ───────────────────────────────────────────────────────────────────────────


class TestBaselineMode:
    def test_first_round_marks_all_seen_no_alert(self, tmp_path):
        items = [_item(), _item(title="Maint window", type_key="maintenance_updates",
                               url="https://announcements.bybit.com/en-US/article/m-blt01/")]
        rc, opener, alert = _run(tmp_path, items)
        assert rc == 0
        assert alert.calls == []  # flood guard：首輪 0 告警
        assert len(opener.requests) == 1  # 每輪恰 1 call（BB §3）
        st = _state(tmp_path)
        assert st["baseline_done"] is True
        assert len(st["seen"]) == 2
        # 原文落 state（untrusted 紀律：審計可回溯）。
        assert all("raw" in e for e in st["seen"].values())

    def test_second_round_only_new_items_alert(self, tmp_path):
        _baseline(tmp_path, [_item()])
        new = _item(title="Scheduled maintenance for trading API",
                    type_key="maintenance_updates",
                    url="https://announcements.bybit.com/en-US/article/m-blt02/")
        rc, _, alert = _run(tmp_path, [_item(), new])  # 舊 1 + 新 1
        assert rc == 0
        assert len(alert.calls) == 1
        assert alert.calls[0]["subject"].startswith("[BB-SENTINEL][P0] maintenance_updates:")
        assert alert.calls[0]["severity"] == "CRITICAL"  # P0 → CRITICAL 通道層級

    def test_dedup_same_item_never_realerts(self, tmp_path):
        _baseline(tmp_path, [_item()])
        for _ in range(3):
            rc, _, alert = _run(tmp_path, [_item()])
            assert rc == 0 and alert.calls == []

    def test_url_variant_same_normalized_key_dedups(self, tmp_path):
        _baseline(tmp_path, [_item(url=SAMPLE_URL)])
        variant = _item(url=SAMPLE_URL.rstrip("/") + "?utm_source=feed")
        rc, _, alert = _run(tmp_path, [variant])
        assert rc == 0 and alert.calls == []

    def test_p2_recorded_seen_but_not_alerted(self, tmp_path):
        _baseline(tmp_path, [])
        p2 = _item(title="Football VIP raffle", type_key="latest_activities",
                   tags=("Spot",),
                   url="https://announcements.bybit.com/en-US/article/raffle-blt03/")
        rc, _, alert = _run(tmp_path, [p2])
        assert rc == 0 and alert.calls == []
        st = _state(tmp_path)
        assert len(st["seen"]) == 1
        entry = next(iter(st["seen"].values()))
        assert entry["severity"] == bbs.SEV_P2 and entry["alerted"] is False

    def test_malformed_item_skipped_not_poisoning_seen(self, tmp_path):
        _baseline(tmp_path, [])
        rc, _, alert = _run(tmp_path, [{"description": "no url no title"}])
        assert rc == 0 and alert.calls == []
        assert _state(tmp_path)["seen"] == {}

    def test_alert_body_untrusted_discipline(self, tmp_path):
        """BB §6.3：body=title+url+類別 plain-text；description 絕不展開。"""
        _baseline(tmp_path, [])
        rc, _, alert = _run(tmp_path, [_item()])
        assert len(alert.calls) == 1
        body = alert.calls[0]["body"]
        assert "Delisting of TONUSDT" in body
        assert "announcements.bybit.com" in body
        assert "delistings" in body
        assert "SECRET-DESC-MARKER" not in body  # description 不展開
        assert "SECRET-DESC-MARKER" not in alert.calls[0]["subject"]
        # 但原文（含 description）在 state raw 欄供審計。
        st = _state(tmp_path)
        assert "SECRET-DESC-MARKER" in json.dumps(st["seen"])

    def test_alert_cap_overflow_aggregated(self, tmp_path):
        _baseline(tmp_path, [])
        many = [
            _item(title=f"Delisting {i}",
                  url=f"https://announcements.bybit.com/en-US/article/d{i}-blt{i:02x}/")
            for i in range(bbs.MAX_ALERTS_PER_RUN + 3)
        ]
        rc, _, alert = _run(tmp_path, many)
        assert rc == 0
        # 上限條數 + 1 條彙總。
        assert len(alert.calls) == bbs.MAX_ALERTS_PER_RUN + 1
        assert "aggregate" in alert.calls[-1]["subject"]
        # 全數仍落 state（明細不丟）。
        assert len(_state(tmp_path)["seen"]) == len(many)

    def test_dry_run_no_alert_fn_calls_state_still_written(self, tmp_path):
        _baseline(tmp_path, [])
        rc, _, alert = _run(tmp_path, [_item()], dry_run=True)
        assert rc == 0 and alert.calls == []
        assert len(_state(tmp_path)["seen"]) == 1


class TestPrune:
    def test_entries_older_than_retention_pruned(self, tmp_path):
        _baseline(tmp_path, [_item()])
        # 把唯一 seen 條目改成 91d 前。
        st = _state(tmp_path)
        key = next(iter(st["seen"]))
        st["seen"][key]["first_seen_at"] = NOW - 91 * 86400.0
        bbs.save_state(str(tmp_path), st)
        rc, _, alert = _run(tmp_path, [])
        assert rc == 0
        assert _state(tmp_path)["seen"] == {}

    def test_recent_entries_kept(self, tmp_path):
        _baseline(tmp_path, [_item()])
        rc, _, _ = _run(tmp_path, [])
        assert len(_state(tmp_path)["seen"]) == 1

    def test_prune_pure_function_boundary(self):
        state = {"seen": {
            "old": {"first_seen_at": NOW - 90.5 * 86400.0},
            "edge": {"first_seen_at": NOW - 89.5 * 86400.0},
            "bad_ts": {"first_seen_at": "not-a-number"},
        }}
        pruned = bbs.prune_seen(state, NOW)
        assert pruned == 2  # old + bad_ts（壞 ts 視同過期清掉，state 自癒）
        assert list(state["seen"]) == ["edge"]


class TestFailQuiet:
    def test_fetch_failure_quiet_skip_exit0_no_alert(self, tmp_path):
        rc, _, alert = _run(tmp_path, opener=RecordingOpener(exc=OSError("net down")))
        assert rc == 0
        assert alert.calls == []
        st = _state(tmp_path)
        assert st["consecutive_failures"] == 1
        assert not st.get("baseline_done")  # 失敗輪不消耗 baseline

    def test_no_tight_retry_single_call_even_on_failure(self, tmp_path):
        opener = RecordingOpener(exc=OSError("403 ban"))
        rc, opener, _ = _run(tmp_path, opener=opener)
        assert rc == 0
        assert len(opener.requests) == 1  # 失敗即收手，禁 tight retry（BB §3）

    def test_meta_alert_exactly_once_at_threshold(self, tmp_path):
        alert = AlertRecorder()
        for i in range(bbs.META_ALERT_AFTER_FAILURES + 2):
            rc, _, _ = _run(
                tmp_path, opener=RecordingOpener(exc=OSError("down")), alert=alert,
                now=NOW + i * 1800.0,
            )
            assert rc == 0
        # 連續 10 輪失敗 → 恰第 8 輪發 1 條 meta-alert（episode ≤1 條）。
        assert len(alert.calls) == 1
        assert "sentinel-health" in alert.calls[0]["subject"]
        assert alert.calls[0]["severity"] == "WARN"

    def test_success_resets_failure_counter(self, tmp_path):
        for i in range(3):
            _run(tmp_path, opener=RecordingOpener(exc=OSError("down")), now=NOW + i)
        rc, _, _ = _run(tmp_path, [], now=NOW + 10)
        assert rc == 0
        st = _state(tmp_path)
        assert st["consecutive_failures"] == 0
        # 之後再連續失敗 → episode 計數重新累積（不殘留舊 episode）。
        rc, _, alert = _run(tmp_path, opener=RecordingOpener(exc=OSError("down")), now=NOW + 11)
        assert _state(tmp_path)["consecutive_failures"] == 1 and alert.calls == []

    def test_corrupt_state_file_self_heals_to_baseline(self, tmp_path):
        (Path(tmp_path) / bbs.STATE_FILE).write_text("{corrupt", encoding="utf-8")
        rc, _, alert = _run(tmp_path, [_item()])
        assert rc == 0 and alert.calls == []  # 壞檔 → 空 state → baseline 模式
        assert _state(tmp_path)["baseline_done"] is True


# ───────────────────────────────────────────────────────────────────────────
# 告警鏈接縫（emitter 簽名 smoke）+ alert-only 結構斷言
# ───────────────────────────────────────────────────────────────────────────


class TestAlertSeamAndStructure:
    def test_emitter_signature_smoke(self):
        """sibling-import 接縫：engine_watchdog._send_alert_best_effort 改簽名須同步本哨兵。"""
        import engine_watchdog
        params = list(inspect.signature(engine_watchdog._send_alert_best_effort).parameters)
        assert params == ["subject", "body", "severity", "data_dir"]

    def test_resolve_alert_fn_returns_watchdog_emitter(self):
        import engine_watchdog
        assert bbs._resolve_alert_fn() is engine_watchdog._send_alert_best_effort

    def test_format_alert_subject_prefix_and_truncation(self):
        subject, body = bbs.format_alert("P0", "delistings", "T" * 500, "u" * 600, ["kw:api"])
        assert subject.startswith("[BB-SENTINEL][P0] delistings:")
        assert len(subject) < 300
        assert "kw:api" in body

    def test_zero_credential_zero_db_structure(self):
        """BB 驗收 #1：不經簽名 client、零 credential、零 PG。"""
        src = inspect.getsource(bbs)
        for forbidden in (
            "psycopg2", "asyncpg", "hmac", "X-BAPI", "api_key", "API_KEY",
            "get_checked", "pybit", "sign(",
        ):
            assert forbidden not in src, f"credential/DB surface found: {forbidden}"

    def test_host_is_public_api_bybit(self):
        assert bbs.API_HOST == "https://api.bybit.com"
        assert bbs.API_PATH == "/v5/announcements/index"

    def test_state_is_only_local_write_surface(self, tmp_path):
        """唯一本地寫入 = state json（+ 注入 alert recorder，無其他檔案落地）。"""
        _run(tmp_path, [_item()])
        files = sorted(p.name for p in Path(tmp_path).iterdir())
        assert files == [bbs.STATE_FILE]


class TestFormatAlertSanitization:
    """W-3（修復輪 2026-06-12）：外部公告文本進 subject/body/log 前剝控制字符。"""

    def test_title_newline_injection_cannot_forge_log_lines(self):
        subject, body = bbs.format_alert(
            "P0", "delistings",
            "Notice\r\n2026-06-12 [WATCHDOG] INFO forged line\x1b[31m\x00END",
            "https://announcements.bybit.com/x\r\n/forged", ["kw:delist"],
        )
        # subject 進 watchdog INFO log（單行語義）：任何換行/控制字符都是注入面。
        assert "\r" not in subject and "\n" not in subject
        assert "\x1b" not in subject and "\x00" not in subject
        # body 換行只能是固定欄位分隔：title/url/type/escalators/尾註 = 恰 5 行。
        lines = body.split("\n")
        assert len(lines) == 5
        assert not any("\r" in ln or "\x1b" in ln or "\x00" in ln for ln in lines)
        # 剝而非吞：注入文字變平文字留在 title 欄（保留審計可讀性）。
        assert "forged line" in lines[0]
        assert lines[1].startswith("url: ") and "/forged" in lines[1]

    def test_type_key_and_escalators_also_stripped(self):
        subject, body = bbs.format_alert(
            "P1", "new\ncrypto", "T", "u", ["kw:\r\nxx", "tag:\tyy"],
        )
        assert "\n" not in subject
        assert body.count("\n") == 4  # 仍是固定 5 行。

    def test_strip_control_keeps_unicode_text(self):
        assert bbs._strip_control("中文 Title — ok\x07!") == "中文 Title — ok !"


class TestNoRedirectWiring:
    """E3 LOW（修復輪 2026-06-12）：fetch 默認 opener = alert_sink.urlopen_no_redirect。"""

    def test_default_opener_is_no_redirect(self, monkeypatch):
        calls = []

        def _fake_opener(req, timeout=None):
            calls.append(req.full_url)
            raise urllib.error.URLError("stop here")  # 立即終止：只驗 default 接線。

        monkeypatch.setattr(bbs.alert_sink, "urlopen_no_redirect", _fake_opener)
        with pytest.raises(bbs.FetchError):
            bbs.fetch_announcements(opener=None)
        assert calls and "api.bybit.com" in calls[0]

    def test_redirect_refused_collapses_to_fetch_error(self):
        def _redirecting_opener(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 302, "redirect refused (-> 'x')", {}, None)

        with pytest.raises(bbs.FetchError, match="http_error"):
            bbs.fetch_announcements(opener=_redirecting_opener)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

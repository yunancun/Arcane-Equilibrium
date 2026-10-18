"""有界、可續傳的公開資料擷取；測試使用假傳輸，真實取數須另行執行。"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import http.client
import io
import json
import math
import os
from pathlib import Path
import re
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.bybit.com"
INSTRUMENTS = "/v5/market/instruments-info"
ENDPOINTS = {"kline": "/v5/market/kline", "funding": "/v5/market/funding/history", "open_interest": "/v5/market/open-interest"}
TOOL_VERSION = "r8-public-data-1"
PARSER_VERSION = "r8-strict-2"
CURSOR = re.compile(r"(?:[A-Za-z0-9_.~-]|%[0-9A-Fa-f]{2})+")
SYMBOL = re.compile(r"[A-Z0-9]{1,32}")
PERIODS = {"1": 60000, "60": 3600000, "D": 86400000, "4h": 14400000}
HEADERS = {"kline": ("timestamp", "open", "high", "low", "close", "volume", "turnover"), "funding": ("timestamp", "funding_rate"), "open_interest": ("timestamp", "open_interest")}


class DataError(ValueError):
    """資料、計畫、分頁或續傳證據不符合契約。"""


class IntegrityError(DataError):
    """計畫或續傳證據不完整，必須中止。"""


class ResponseInvalid(DataError):
    """回應無法解析為本工作的有效資料。"""


class RequestFailed(DataError):
    """請求失敗，原始回應已留存。"""

    def __init__(self, message, *, ret_code=None):
        super().__init__(message)
        self.ret_code = ret_code


class Forbidden(RequestFailed):
    """403 必須停止整個程序，不可繼續其他標的。"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def milliseconds(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ResponseInvalid("時間戳須為非負整數毫秒")
    return int(value)


def iso_ms(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
            raise ValueError()
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ResponseInvalid("計畫時間須為 UTC ISO8601") from exc


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ResponseInvalid("缺少有限數值")
    try:
        number = float(value)
    except ValueError as exc:
        raise ResponseInvalid("無法解析數值") from exc
    if not math.isfinite(number):
        raise ResponseInvalid("數值必須有限")
    return number


def atomic_write(path, data):
    """暫存檔與目標在同一目錄；中斷時保留舊完整檔。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _json(path):
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, ValueError) as exc:
        raise IntegrityError("無法讀取完整 JSON: " + Path(path).name) from exc


class Plan:
    """白名單以固定參數、實際標的集合與有界時間窗共同約束。"""

    def __init__(self, path):
        try:
            self._validate(path)
        except (DataError, KeyError, TypeError, ValueError, OSError) as exc:
            raise IntegrityError(str(exc)) from exc

    def _validate(self, path):
        self.raw = Path(path).read_bytes()
        self.sha256 = digest(self.raw)
        self.value = json.loads(self.raw)
        p = self.value
        if p.get("schema_version") != 1 or p.get("base_url") != BASE_URL:
            raise IntegrityError("不允許的計畫版本或基底網址")
        self.start, self.end = iso_ms(p["start"]), iso_ms(p["end"])
        if not iso_ms("2022-01-01T00:00:00Z") <= self.start < self.end <= iso_ms("2026-10-01T00:00:00Z"):
            raise IntegrityError("計畫超出已授權期間")
        if not 0 < finite(p["max_rps"]) <= 4:
            raise IntegrityError("計畫速率超出上限")
        for key, maximum in (("max_attempts", 5), ("max_pages", 5000), ("max_symbols", 2000), ("universe_max_pages", 1000)):
            if type(p[key]) is not int or not 1 <= p[key] <= maximum:
                raise IntegrityError("計畫限額不合法: " + key)
        if p.get("symbol_scope") != "observed_usdt_linear_perpetuals":
            raise IntegrityError("標的範圍不合法")
        for key, params in (("instruments", {"category": "linear", "limit": 1000}),
                            ("delisted_probe", {"category": "linear", "limit": 1000, "status": "Closed"})):
            rule = p[key]
            if rule["endpoint"] != INSTRUMENTS or rule["params"] != params or rule["pagination_keys"] != ["cursor"]:
                raise IntegrityError("不允許的標的清單請求")
        if p["delisted_probe"].get("logical_scans") != 1:
            raise IntegrityError("只允許一次下架品種邏輯探測")
        if p["instruments"]["filter_candidate"] != {"contractType": "LinearPerpetual", "settleCoin": "USDT", "status": "Trading"}:
            raise IntegrityError("篩選候選條件超出已授權範圍")
        if not isinstance(p["datasets"], list) or not p["datasets"]:
            raise IntegrityError("計畫缺資料集")
        seen = set()
        for rule in p["datasets"]:
            name = rule["name"]
            if name not in ENDPOINTS or rule["endpoint"] != ENDPOINTS[name]:
                raise IntegrityError("不允許的端點")
            expected = {"category": "linear", "limit": 1000 if name == "kline" else 200}
            if name == "open_interest":
                expected["intervalTime"] = "4h"
            if rule["params"] != expected:
                raise IntegrityError("資料集固定參數不符")
            keys = ["start", "end"] if name == "kline" else ["startTime", "endTime"]
            if rule["window_keys"] != keys or rule.get("pagination_keys", []) != (["cursor"] if name == "open_interest" else []):
                raise IntegrityError("不允許的分頁鍵")
            scope = rule["symbols"]
            if scope != "universe" and (not isinstance(scope, list) or not scope or not all(isinstance(s, str) and re.fullmatch(r"[A-Z0-9]+", s) for s in scope)):
                raise IntegrityError("標的白名單格式錯誤")
            if name != "kline" and "intervals" in rule:
                raise IntegrityError("只有 K 線可以指定 intervals")
            intervals = rule["intervals"] if name == "kline" else [expected.get("intervalTime", "funding")]
            if not isinstance(intervals, list) or not intervals or not all(isinstance(i, str) for i in intervals):
                raise IntegrityError("K 線週期須為非空字串清單")
            for interval in intervals:
                if name == "kline" and (interval not in ("1", "60", "D") or interval == "1" and (scope == "universe" or not set(scope) <= {"BTCUSDT", "ETHUSDT"})):
                    raise IntegrityError("K 線週期超出已授權範圍")
                identity = (name, interval)
                if identity in seen:
                    raise IntegrityError("資料集週期重複")
                seen.add(identity)

    def authorize(self, endpoint, params, universe):
        try:
            self._authorize(endpoint, params, universe)
        except (DataError, KeyError, TypeError, ValueError) as exc:
            raise IntegrityError(str(exc)) from exc

    def _authorize(self, endpoint, params, universe):
        if endpoint == INSTRUMENTS:
            for key in ("instruments", "delisted_probe"):
                rule = self.value[key]
                extra = set(params) - set(rule["params"])
                if extra <= {"cursor"} and all(params.get(k) == v for k, v in rule["params"].items()):
                    if "cursor" in params and (not isinstance(params["cursor"], str) or not CURSOR.fullmatch(params["cursor"])):
                        raise IntegrityError("cursor 不合法")
                    return
            raise IntegrityError("標的請求不在計畫白名單")
        for rule in self.value["datasets"]:
            if endpoint != rule["endpoint"]:
                continue
            allowed = set(rule["params"]) | {"symbol"} | set(rule["window_keys"]) | set(rule.get("pagination_keys", []))
            if rule["name"] == "kline":
                allowed.add("interval")
                if params.get("interval") not in rule["intervals"]:
                    continue
            required = allowed - {"cursor"}
            if not required <= set(params) or not set(params) <= allowed or any(params.get(k) != v for k, v in rule["params"].items()):
                continue
            symbol = params["symbol"]
            if symbol not in universe or rule["symbols"] != "universe" and symbol not in rule["symbols"]:
                continue
            a, b = (milliseconds(params[k]) for k in rule["window_keys"])
            if not self.job_start(rule["name"], symbol, params.get("interval"), universe) <= a <= b < self.end:
                raise IntegrityError("請求超出計畫或上市時間")
            if "cursor" in params and (not isinstance(params["cursor"], str) or not CURSOR.fullmatch(params["cursor"])):
                raise IntegrityError("cursor 不合法")
            return
        raise IntegrityError("端點或完整參數組合不在計畫白名單")

    def job_start(self, name, symbol, interval, universe):
        launch = universe[symbol]["launch_time"]
        if name == "kline":
            launch = launch // PERIODS[interval] * PERIODS[interval]
        return max(self.start, launch)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 保留 3xx 原始回應供請求帳記錄，不跟隨重新導向。


def transport(endpoint, params):
    """不使用環境 proxy、認證標頭或金鑰；固定公開 HTTPS 主機。"""
    if "cursor" in params and (not isinstance(params["cursor"], str) or not CURSOR.fullmatch(params["cursor"])):
        raise IntegrityError("cursor 不合法")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                         urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    query = "&".join(urllib.parse.urlencode({k: v}) if k != "cursor" else "cursor=" + v for k, v in params.items())
    request = urllib.request.Request(BASE_URL + endpoint + "?" + query,
                                     headers={"User-Agent": TOOL_VERSION}, method="GET")
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ResponseInvalid("回應超過有界大小")
        return response.code, raw


class Client:
    def __init__(self, plan, out, *, send=transport, max_rps=4, clock=time.monotonic,
                 sleep=time.sleep, now=utc_now):
        if not 0 < finite(max_rps) <= min(4, plan.value["max_rps"]):
            raise DataError("--max-rps 只能調低且必須大於 0")
        self.plan, self.out, self.send = plan, Path(out), send
        self.period, self.clock, self.sleep, self.now = 1 / max_rps, clock, sleep, now
        self.last = None
        self.stopped = False
        self.universe = {}
        self.out.mkdir(parents=True, exist_ok=True)
        self.log = self.out / "requests.jsonl"
        self.records = []
        if self.log.exists():
            raw = self.log.read_bytes()
            if raw and not raw.endswith(b"\n"):
                raise IntegrityError("請求記錄末行不完整，拒絕續傳")
            self.records = [json.loads(x) for x in raw.splitlines()]
            for i, row in enumerate(self.records, 1):
                if type(row.get("request_id")) is not int or row["request_id"] != i or row.get("plan_sha256") != plan.sha256:
                    raise IntegrityError("請求記錄身份不符")
                if row.get("raw_sha256") is not None:
                    path = self.out / "raw" / (str(i) + ".json")
                    if not path.exists() or digest(path.read_bytes()) != row["raw_sha256"]:
                        raise IntegrityError("原始回應缺失或雜湊不符")
                elif (self.out / "raw" / (str(i) + ".json")).exists():
                    raise IntegrityError("網路錯誤不得有原始檔")
            if self.records and self.records[-1].get("http_status") == 403:
                if iso_ms(self.now()) - iso_ms(self.records[-1]["received_at"]) < 600000:
                    raise IntegrityError("403 冷卻未滿 10 分鐘")

    def request(self, endpoint, params, *, page=1, parent=None):
        if self.stopped:
            raise Forbidden("先前收到 403，程序已停止")
        self.plan.authorize(endpoint, params, self.universe)
        if page < 1 or (page == 1) != (parent is None):
            raise IntegrityError("分頁鏈缺少父頁")
        if parent is not None:
            if type(parent) is not int or not 1 <= parent <= len(self.records):
                raise IntegrityError("父頁不存在")
            prior = self.records[parent-1]
            if prior["endpoint"] != endpoint or page != prior["pagination"]["page"] + 1:
                raise IntegrityError("分頁鏈不連續")
            if "cursor" in params:
                previous = _json(self.out / "raw" / (str(parent) + ".json"))
                if params["cursor"] != previous["result"]["nextPageCursor"]:
                    raise IntegrityError("cursor 不是由父頁推得")
        elif "cursor" in params:
            raise IntegrityError("第一頁不得自帶 cursor")
        for attempt in range(1, self.plan.value["max_attempts"] + 1):
            if self.last is not None:
                wait = self.period - (self.clock() - self.last)
                if wait > 0:
                    self.sleep(wait)
            self.last = self.clock()
            status, raw, error = None, None, None
            caught = None
            payload = None
            try:
                status, raw = self.send(endpoint, dict(params))
                if not isinstance(raw, bytes):
                    raw = None
                    raise ResponseInvalid("傳輸層須回傳原始 bytes")
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError):
                    pass
            except Exception as exc:
                caught = exc
                error = type(exc).__name__
            received = self.now()
            request_id = len(self.records) + 1
            if raw is not None:
                atomic_write(self.out / "raw" / (str(request_id) + ".json"), raw)
            record = {"request_id": request_id, "method": "GET", "base_url": BASE_URL,
                      "endpoint": endpoint, "params": dict(params), "plan_sha256": self.plan.sha256,
                      "pagination": {"page": page, "parent_request_id": parent, "cursor": params.get("cursor"),
                                     "window": {k: params[k] for k in ("start", "end", "startTime", "endTime") if k in params}},
                      "attempt": attempt, "http_status": status, "retCode": payload.get("retCode") if isinstance(payload, dict) else None,
                      "raw_sha256": digest(raw) if raw is not None else None, "received_at": received, "network_error": error}
            with self.log.open("ab") as stream:
                stream.write(encoded(record) + b"\n"); stream.flush(); os.fsync(stream.fileno())
            self.records.append(record)
            if status == 403:
                self.stopped = True
                raise Forbidden("HTTP 403：停止整個程序；不重試")
            if isinstance(caught, (Forbidden, IntegrityError)):
                raise caught
            if caught is not None and not isinstance(caught, (OSError, http.client.HTTPException)):
                raise ResponseInvalid("請求送出後回應失敗: " + error) from caught
            ret_code = payload.get("retCode") if isinstance(payload, dict) else None
            retry = caught is not None or status == 429 or status is not None and 500 <= status <= 599 or status == 200 and ret_code in (10006, 10016, 10018)
            if retry:
                if attempt < self.plan.value["max_attempts"]:
                    self.sleep(min(2 ** (attempt-1), 16))
                    continue
                raise RequestFailed("重試次數已用完", ret_code=ret_code)
            if status != 200 or not isinstance(payload, dict):
                raise RequestFailed("HTTP 或 JSON 回應失敗")
            if type(payload.get("retCode")) is not int or payload["retCode"] != 0:
                raise RequestFailed("retCode 非 0 或缺失", ret_code=ret_code)
            if not isinstance(payload.get("result"), dict) or not isinstance(payload["result"].get("list"), list):
                raise ResponseInvalid("缺 result.list")
            if endpoint in (ENDPOINTS["kline"], ENDPOINTS["open_interest"]):
                for key in ("symbol", "category"):
                    if key in payload["result"] and payload["result"][key] != params[key]:
                        raise ResponseInvalid("回應 " + key + " 與請求不符")
            return payload["result"], request_id
        raise AssertionError("不可到達")


def parse_rows(name, records, *, symbol, start, end, interval, now_ms):
    rows = {}
    for item in records:
        try:
            if name == "kline":
                if not isinstance(item, list) or len(item) != 7:
                    raise ResponseInvalid("K 線須有七欄")
                stamp = milliseconds(item[0]); row = (stamp,) + tuple(finite(x) for x in item[1:])
            elif name == "funding":
                if item["symbol"] != symbol:
                    raise ResponseInvalid("資金費標的不符")
                stamp = milliseconds(item["fundingRateTimestamp"]); row = (stamp, finite(item["fundingRate"]))
            else:
                stamp = milliseconds(item["timestamp"]); row = (stamp, finite(item["openInterest"]))
        except (KeyError, TypeError, IndexError) as exc:
            raise ResponseInvalid("缺少資料欄位") from exc
        if not start <= stamp < end:
            raise ResponseInvalid("回應時點超出請求範圍")
        if name == "kline" and stamp + PERIODS[interval] > now_ms:
            continue
        if stamp in rows and rows[stamp] != row:
            raise ResponseInvalid("同一時點的重複資料內容衝突")
        rows[stamp] = row
    return [rows[k] for k in sorted(rows)]


def gaps(rows, start, end, period, *, funding=False):
    """K 線與持倉量依 UTC 網格；資金費僅用觀察到的結算相位。"""
    if period <= 0:
        raise ResponseInvalid("缺漏間隔必須為正")
    timestamps = sorted({r[0] for r in rows})
    actual = [{"from": a, "to": b, "actual_interval_ms": b-a, "expected_interval_ms": period}
              for a,b in zip(timestamps,timestamps[1:]) if b-a != period]
    phases = {t % period for t in timestamps}
    if funding:
        unknown = bool(actual) or not timestamps
        return {"missing_count": None if unknown else 0, "missing_intervals": [],
                "off_grid_timestamps": [], "observed_interval_mismatches": actual,
                "settlement_phase_ms": next(iter(phases)) if len(phases) == 1 else None,
                "certainty": "UNKNOWN_HISTORICAL_INTERVAL" if unknown else "OBSERVED_INTERVALS_MATCH",
                "basis": "歷史間隔可能變更；只比較相鄰紀錄，不以現行間隔外推缺漏"}
    phase = next(iter(phases)) if funding else 0
    first = ((start - phase + period - 1) // period) * period + phase
    missing, intervals = 0, []
    cursor = first
    for stamp in timestamps + [end]:
        if stamp > cursor:
            last = min(stamp, end)
            count = max(0, (last - 1 - cursor) // period + 1)
            if count:
                intervals.append({"start": cursor, "end_exclusive": cursor + count*period, "count": count})
                missing += count
        if stamp < end:
            cursor = max(cursor, stamp + period)
    return {"missing_count": missing, "missing_intervals": intervals,
            "off_grid_timestamps": [t for t in timestamps if (t-phase) % period],
            "observed_interval_mismatches": actual if funding else [],
            "settlement_phase_ms": phase if funding else None,
            "certainty": "INFERRED_FROM_OBSERVED_PHASE" if funding else "FIXED_INTERVAL",
            "basis": "依已觀察結算相位與標的間隔外推；歷史間隔變更仍須查核" if funding else "UTC_INTERVAL_GRID"}


class Collector:
    def __init__(self, plan, out, **client_options):
        self.plan, self.out = plan, Path(out).resolve()
        self._lock = None
        if any((ancestor / ".git").exists() for ancestor in (self.out, *self.out.parents)):
            raise IntegrityError("輸出必須在倉庫之外")
        self.out.mkdir(parents=True, exist_ok=True)
        self._lock = (self.out / ".collector.lock").open("a+b")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.close()
            raise IntegrityError("拿不到輸出目錄排他鎖") from exc
        try:
            self._initialize(client_options)
        except Exception:
            self.close()
            raise

    def _initialize(self, client_options):
        plan = self.plan
        self.client = Client(plan, self.out, **client_options)
        self.manifest_path = self.out / "manifest.json"
        self.manifest = _json(self.manifest_path) if self.manifest_path.exists() else {
            "tool_version": TOOL_VERSION, "parser_version": PARSER_VERSION, "plan_sha256": plan.sha256, "files": {}}
        if self.manifest.get("plan_sha256") != plan.sha256 or self.manifest.get("parser_version") != PARSER_VERSION:
            raise IntegrityError("續傳計畫或解析器版本不符")
        count = self.manifest.get("request_count", 0)
        if type(count) is not int or not 0 <= count <= len(self.client.records):
            raise IntegrityError("manifest 請求數與記錄不符")
        if "request_log_sha256" in self.manifest:
            prefix = b"".join(self.client.log.read_bytes().splitlines(keepends=True)[:count]) if self.client.log.exists() else b""
            if digest(prefix) != self.manifest["request_log_sha256"]:
                raise IntegrityError("manifest 綁定的請求記錄前綴已改變")
        self.manifest.setdefault("failures", {})
        self._load_universe()

    def close(self):
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()

    def _save(self):
        self.manifest["fetched_at"] = self.client.now()
        self.manifest["request_count"] = len(self.client.records)
        self.manifest["request_log_sha256"] = digest(self.client.log.read_bytes()) if self.client.log.exists() else digest(b"")
        atomic_write(self.manifest_path, encoded(self.manifest) + b"\n")

    def _load_universe(self):
        self.universe = self.manifest.get("universe", {})
        self.client.universe = self.universe
        if not isinstance(self.universe, dict):
            raise IntegrityError("universe 格式不符")
        for symbol, item in self.universe.items():
            if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
                raise IntegrityError("續傳標的不合法")
            if not isinstance(item, dict) or type(item.get("launch_time")) is not int or type(item.get("funding_interval_ms")) is not int or item["funding_interval_ms"] <= 0:
                raise IntegrityError("續傳標的欄位不符")
        for request_id in self.manifest.get("universe_request_ids", []):
            if type(request_id) is not int or not 1 <= request_id <= len(self.client.records):
                raise IntegrityError("universe_request_ids 不合法")
            row = self.client.records[request_id-1]
            if row["raw_sha256"] is None:
                continue
            if row["endpoint"] != INSTRUMENTS or digest((self.out / "raw" / (str(request_id) + ".json")).read_bytes()) != row["raw_sha256"]:
                raise IntegrityError("標的清單原始回應證據不符")

    def fetch_universe(self):
        try:
            return self._fetch_universe()
        except (Forbidden, IntegrityError):
            raise
        except (DataError, KeyError, TypeError, ValueError) as exc:
            raise IntegrityError("universe 階段失敗: " + str(exc)) from exc

    def _fetch_universe(self):
        if self.manifest.get("universe_complete"):
            return self.universe
        observed, request_ids, probe_status = [], [], "UNVERIFIED"
        for key in ("instruments", "delisted_probe"):
            # 已完成的探測可由原始頁重建，不重送同一個邏輯探測。
            cache = self.out / (key + "_pages.json")
            state = _json(cache) if cache.exists() else {"ids": [], "cursor": None, "complete": False, "failed": False}
            params = dict(self.plan.value[key]["params"])
            cursor, parent = state["cursor"], state["ids"][-1] if state["ids"] else None
            seen = set()
            for request_id in state["ids"]:
                row = self.client.records[request_id-1]
                old = row["params"].get("cursor")
                if old:
                    seen.add(old)
            before_scan = len(self.client.records)
            try:
                while not state["complete"]:
                    page = len(state["ids"]) + 1
                    if page > self.plan.value["universe_max_pages"]:
                        raise ResponseInvalid("instruments-info 超過頁數上限且 cursor 未清空")
                    if cursor:
                        if cursor in seen:
                            raise ResponseInvalid("instruments-info cursor 未前進")
                        seen.add(cursor); params["cursor"] = cursor
                    result, request_id = self.client.request(INSTRUMENTS, params, page=page, parent=parent)
                    if not isinstance(result.get("nextPageCursor"), str) or result["nextPageCursor"] and not CURSOR.fullmatch(result["nextPageCursor"]):
                        raise ResponseInvalid("instruments-info 缺 nextPageCursor")
                    cursor = result["nextPageCursor"]
                    if cursor and cursor in seen:
                        raise ResponseInvalid("instruments-info cursor 未前進")
                    state["ids"].append(request_id)
                    state.update(cursor=cursor, complete=not cursor)
                    atomic_write(cache, encoded(state)); parent = request_id
            except (Forbidden, IntegrityError):
                raise
            except (RequestFailed, ResponseInvalid):
                if key != "delisted_probe":
                    raise
                state.update(complete=True, failed=True, failure_request_ids=list(range(before_scan+1, len(self.client.records)+1)))
                atomic_write(cache, encoded(state))
            request_ids.extend(state["ids"])
            if key == "delisted_probe":
                probe_status = "REQUEST_FAILED" if state["failed"] else "RESPONSE_RECORDED_NOT_HISTORICAL_PROOF"
                request_ids.extend(state.get("failure_request_ids", []))
            for request_id in state["ids"]:
                payload = _json(self.out / "raw" / (str(request_id) + ".json"))
                observed.extend((key, item) for item in payload["result"]["list"])
        universe, inventory = {}, {"contractType": set(), "settleCoin": set(), "status": set()}
        for source, item in observed:
            try:
                for key in inventory:
                    if not isinstance(item[key], str) or not item[key]:
                        raise DataError("標的篩選欄位缺失或型別錯誤")
                    inventory[key].add(item[key])
                if item["contractType"] != "LinearPerpetual" or item["settleCoin"] != "USDT":
                    continue
                expected_status = "Trading" if source == "instruments" else "Closed"
                if item["status"] != expected_status:
                    raise DataError("實際狀態與查詢候選值不符，須先查核原始回應")
                symbol = item["symbol"]
                if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
                    raise DataError("標的名稱不合法")
                launch = milliseconds(item["launchTime"])
                funding_minutes = milliseconds(item["fundingInterval"])
                if funding_minutes <= 0:
                    raise DataError("fundingInterval 必須為正的分鐘數")
                value = {"launch_time": launch, "status": item["status"], "funding_interval_ms": funding_minutes*60000, "source": source, "deliveryTime": milliseconds(item.get("deliveryTime", "0"))}
                if symbol in universe and universe[symbol] != value:
                    raise DataError("不同頁的標的資訊衝突")
                if launch < self.plan.end:
                    universe[symbol] = value
            except (KeyError, TypeError) as exc:
                raise DataError("原始回應尚不能確認合約篩選契約") from exc
        if len(universe) > self.plan.value["max_symbols"]:
            raise IntegrityError("universe 超過 max_symbols")
        if not universe:
            raise DataError("沒有可由原始回應確認的 USDT 永續合約")
        self.universe = dict(sorted(universe.items())); self.client.universe = self.universe
        self.manifest.update(universe=self.universe, universe_request_ids=request_ids, universe_complete=True,
                             filtering={"rules": self.plan.value["instruments"]["filter_candidate"],
                                        "delisted_status_rule": "Closed", "observed_values": {k: sorted(v) for k,v in inventory.items()},
                                        "verified_from_raw_request_ids": request_ids},
                             delistings={"probe_status": probe_status, "obtained": sum(v["status"] == "Closed" for v in universe.values()),
                                         "period_contains_delistings": True if any(v["status"] == "Closed" and self.plan.start <= v["deliveryTime"] < self.plan.end for v in universe.values()) else "UNKNOWN", "point_in_time_universe_complete": False,
                                         "cross_sectional_candidate_allowed": False})
        self._save()
        return self.universe

    def _jobs(self):
        for rule in self.plan.value["datasets"]:
            for symbol in sorted(self.universe):
                if rule["symbols"] != "universe" and symbol not in rule["symbols"]:
                    continue
                intervals = rule["intervals"] if rule["name"] == "kline" else [rule["params"].get("intervalTime", "funding")]
                for interval in intervals:
                    start = self.plan.job_start(rule["name"], symbol, interval, self.universe)
                    if start < self.plan.end:
                        yield rule, symbol, interval, start

    def dry_run(self, max_rps=4):
        if not self.manifest.get("universe_complete") or not self.manifest.get("universe_request_ids"):
            raise DataError("dry-run 需要先前存下且完整的 instruments-info 原始回應；請先執行 universe-only")
        if not 0 < finite(max_rps) <= min(4, self.plan.value["max_rps"]):
            raise DataError("max-rps 超出上限")
        requests = 0
        for rule, symbol, interval, start in self._jobs():
            period = self.universe[symbol]["funding_interval_ms"] if interval == "funding" else PERIODS[interval]
            requests += math.ceil(math.ceil((self.plan.end-start)/period)/rule["params"]["limit"]) + 1
        return {"estimated_requests": requests, "minimum_seconds_at_max_rps": requests/max_rps,
                "assumption": "依目前原始清單與固定間隔估計；不含重試，實際空頁與歷史覆蓋可能不同", "network_requests": 0}

    def collect(self):
        self.fetch_universe()
        for rule, symbol, interval, start in self._jobs():
            filename = rule["name"] + "_" + symbol + "_" + interval + ".csv.gz"
            prior = self.manifest["failures"].get(filename)
            if prior and (prior["status"] == "FAILED_UNAVAILABLE" or prior["attempts"] >= 2):
                continue
            attempts = prior["attempts"] + 1 if prior else 1
            before = len(self.client.records)
            try:
                self._dataset(rule, symbol, interval, start)
            except (Forbidden, IntegrityError):
                raise
            except (RequestFailed, ResponseInvalid) as exc:
                unavailable = (self.universe[symbol]["source"] == "delisted_probe"
                               and isinstance(exc, RequestFailed) and type(exc.ret_code) is int
                               and exc.ret_code != 0 and exc.ret_code not in (10006, 10016, 10018))
                self.manifest["failures"][filename] = {
                    "status": "FAILED_UNAVAILABLE" if unavailable else "FAILED",
                    "exception_type": type(exc).__name__, "message": str(exc),
                    "request_ids": list(range(before + 1, len(self.client.records) + 1)), "attempts": attempts}
                self._save()
            else:
                self.manifest["failures"].pop(filename, None)
        self._save()
        return self.manifest

    def _validate_checkpoint(self, state, rule, symbol, interval, start):
        """從已驗雜湊的原始頁重算進度，不信任可改寫的完成旗標。"""
        expected = {"end": self.plan.end-1, "cursor": None, "complete": False}
        pending_probe = None
        window_stamps = []
        parent = None
        name = rule["name"]
        a, b = rule["window_keys"]
        try:
            for page, request_id in enumerate(state["request_ids"], 1):
                if type(request_id) is not int or not 1 <= request_id <= len(self.client.records):
                    raise IntegrityError("checkpoint 請求 ID 不合法")
                record = self.client.records[request_id-1]
                params = {**rule["params"], "symbol": symbol, a: start, b: expected["end"]}
                if name == "kline":
                    params["interval"] = interval
                if expected["cursor"]:
                    params["cursor"] = expected["cursor"]
                if pending_probe:
                    params = pending_probe
                elif expected["complete"]:
                    raise IntegrityError("checkpoint 完成後仍有頁面")
                if (record["params"] != params or record["endpoint"] != rule["endpoint"]
                        or record["http_status"] != 200 or record["retCode"] != 0
                        or record["pagination"]["page"] != page or record["pagination"]["parent_request_id"] != parent):
                    raise IntegrityError("checkpoint 分頁鏈不符")
                payload = _json(self.out / "raw" / (str(request_id) + ".json"))["result"]
                rows = parse_rows(name, payload["list"], symbol=symbol, start=params[a], end=params[b]+1,
                                  interval=interval, now_ms=iso_ms(self.client.now()))
                if pending_probe:
                    if rows or payload.get("nextPageCursor"):
                        raise IntegrityError("checkpoint 方向確認不為空")
                    pending_probe = None
                else:
                    stamps = [row[0] for row in rows]
                    window_stamps.extend(stamps)
                    cursor = payload.get("nextPageCursor", "") if name == "open_interest" else ""
                    if cursor:
                        if not isinstance(cursor, str) or not CURSOR.fullmatch(cursor) or not rows:
                            raise IntegrityError("checkpoint cursor 不符")
                        expected["cursor"] = cursor
                    else:
                        expected["cursor"] = None
                        if not window_stamps or min(window_stamps) <= start:
                            expected["complete"] = True
                        else:
                            expected["end"] = min(window_stamps)-1
                        window_stamps = []
                    period = self.universe[symbol]["funding_interval_ms"] if name == "funding" else PERIODS[interval]
                    if (expected["complete"] and len(payload["list"]) == rule["params"]["limit"] and stamps
                            and min(stamps) <= start and max(stamps)+period < params[b]):
                        pending_probe = {**params, a: max(stamps)+period}
                        pending_probe.pop("cursor", None)
                parent = request_id
            if pending_probe or any(state[k] != v or type(state[k]) is not type(v) for k, v in expected.items()):
                raise IntegrityError("checkpoint 狀態與原始頁不符")
        except (KeyError, TypeError, IndexError, ResponseInvalid) as exc:
            raise IntegrityError("checkpoint 格式或原始頁不符") from exc

    def _dataset(self, rule, symbol, interval, start):
        name = rule["name"]; filename = name + "_" + symbol + "_" + interval + ".csv.gz"
        target = self.out / filename
        old = self.manifest["files"].get(filename)
        if old and old.get("coverage") == [start, self.plan.end] and target.exists() and digest(target.read_bytes()) == old["sha256"]:
            return
        checkpoint = self.out / (filename + ".progress.json")
        state = _json(checkpoint) if checkpoint.exists() else {"plan_sha256": self.plan.sha256, "request_ids": [], "end": self.plan.end-1, "cursor": None, "complete": False}
        if state["plan_sha256"] != self.plan.sha256:
            raise IntegrityError("續傳 checkpoint 計畫不符")
        for request_id in state["request_ids"]:
            if type(request_id) is not int or not 1 <= request_id <= len(self.client.records):
                raise IntegrityError("續傳請求 ID 不合法")
            record = self.client.records[request_id-1]
            if record["endpoint"] != rule["endpoint"] or record["params"].get("symbol") != symbol or (name == "kline" and record["params"].get("interval") != interval):
                raise IntegrityError("續傳原始頁不屬於本資料集")
            self.plan.authorize(record["endpoint"], record["params"], self.universe)
        self._validate_checkpoint(state, rule, symbol, interval, start)
        # 原始頁即續傳單位；每頁原子保存進度，中斷後只補未完成的頁。
        while not state["complete"]:
            page = len(state["request_ids"]) + 1
            if page > self.plan.value["max_pages"]:
                raise ResponseInvalid("資料集頁數超出上限")
            params = dict(rule["params"]); params["symbol"] = symbol
            if name == "kline":
                params["interval"] = interval
            a,b = rule["window_keys"]; params[a], params[b] = start, state["end"]
            if state["cursor"]:
                params["cursor"] = state["cursor"]
            result, request_id = self.client.request(rule["endpoint"], params, page=page, parent=state["request_ids"][-1] if state["request_ids"] else None)
            rows = parse_rows(name, result["list"], symbol=symbol, start=start, end=state["end"]+1, interval=interval, now_ms=iso_ms(self.client.now()))
            next_cursor = result.get("nextPageCursor", "") if name == "open_interest" else ""
            if not isinstance(next_cursor, str) or next_cursor and not CURSOR.fullmatch(next_cursor):
                raise ResponseInvalid("持倉量 cursor 型別錯誤")
            if next_cursor:
                seen = {self.client.records[i-1]["params"].get("cursor") for i in state["request_ids"]}
                if next_cursor == state["cursor"] or next_cursor in seen or not rows:
                    raise ResponseInvalid("持倉量 cursor 未前進或空頁仍有 cursor")
                state["cursor"] = next_cursor
            else:
                # 同一時間窗的所有 cursor 頁走完，再向過去移動。
                stamps = [r[0] for r in rows]
                if name == "open_interest" and state["cursor"]:
                    for prior_id in state["request_ids"]:
                        prior = self.client.records[prior_id-1]
                        if prior["params"][b] == state["end"]:
                            stamps.extend(milliseconds(x["timestamp"]) for x in _json(self.out / "raw" / (str(prior_id) + ".json"))["result"]["list"])
                state["cursor"] = None
                if not stamps or min(stamps) <= start:
                    state["complete"] = True
                else:
                    new_end = min(stamps)-1
                    if new_end >= state["end"]:
                        raise ResponseInvalid("時間分頁未前進")
                    state["end"] = new_end
            state["request_ids"].append(request_id)
            period = self.universe[symbol]["funding_interval_ms"] if name == "funding" else PERIODS[interval]
            if (state["complete"] and len(result["list"]) == rule["params"]["limit"] and rows
                    and min(r[0] for r in rows) <= start and max(r[0] for r in rows) + period < params[b]):
                if len(state["request_ids"]) >= self.plan.value["max_pages"]:
                    raise ResponseInvalid("方向確認超過資料集頁數上限")
                probe = dict(params)
                probe.pop("cursor", None)
                probe[a] = max(r[0] for r in rows) + period
                check, check_id = self.client.request(rule["endpoint"], probe, page=page+1, parent=request_id)
                if check["list"] or check.get("nextPageCursor"):
                    raise ResponseInvalid("滿頁方向確認不為空，拒絕靜默截斷")
                state["request_ids"].append(check_id)
            atomic_write(checkpoint, encoded(state))
        all_rows = {}
        for request_id in state["request_ids"]:
            record = self.client.records[request_id-1]
            raw_path = self.out / "raw" / (str(request_id) + ".json")
            if digest(raw_path.read_bytes()) != record["raw_sha256"]:
                raise IntegrityError("續傳原始回應雜湊不符")
            payload = _json(raw_path)
            for row in parse_rows(name, payload["result"]["list"], symbol=symbol, start=start, end=self.plan.end, interval=interval, now_ms=iso_ms(self.client.now())):
                if row[0] in all_rows and all_rows[row[0]] != row:
                    raise ResponseInvalid("跨頁重複資料衝突")
                all_rows[row[0]] = row
        rows = [all_rows[k] for k in sorted(all_rows)]
        buffer = io.StringIO(newline=""); writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(HEADERS[name]); writer.writerows(rows)
        compressed = gzip.compress(buffer.getvalue().encode(), mtime=0)
        atomic_write(target, compressed)
        period = self.universe[symbol]["funding_interval_ms"] if name == "funding" else PERIODS[interval]
        gap_end = min(self.plan.end, iso_ms(self.client.now()) // period * period) if name == "kline" else self.plan.end
        delivery = self.universe[symbol].get("deliveryTime", 0)
        if delivery:
            gap_end = min(gap_end, delivery)
        source_ids = state["request_ids"]
        ids = [r["request_id"] for r in self.client.records
               if r["endpoint"] == rule["endpoint"] and r["params"].get("symbol") == symbol
               and (name != "kline" or r["params"].get("interval") == interval)]
        self.manifest["files"][filename] = {"dataset": name, "symbol": symbol, "interval": interval, "interval_ms": period,
                                          "first_timestamp": rows[0][0] if rows else None, "last_timestamp": rows[-1][0] if rows else None,
                                          "count": len(rows), "coverage": [start, self.plan.end], "gaps": gaps(rows,start,gap_end,period,funding=name=="funding"),
                                          "sha256": digest(compressed), "bytes": len(compressed), "fetched_at": self.client.now(),
                                          "request_ids": ids, "source_request_ids": source_ids, "request_count": len(ids), "parser_version": PARSER_VERSION,
                                          "tool_version": TOOL_VERSION, "plan_sha256": self.plan.sha256}
        self._save()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-rps", type=float, default=4)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--universe-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        with Collector(Plan(args.plan), args.out, max_rps=args.max_rps) as collector:
            result = collector.dry_run(args.max_rps) if args.dry_run else collector.fetch_universe() if args.universe_only else collector.collect()
            print(json.dumps(result, ensure_ascii=True, sort_keys=True))
            if not args.universe_only and not args.dry_run and any(f["status"] == "FAILED" for f in result["failures"].values()):
                parser.exit(3, "仍有 FAILED 工作；請查看 failures 摘要\n")
    except (DataError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Capture a bounded public Bybit BBO quote artifact for one Demo candidate.

This helper is exchange-facing only when its CLI is explicitly run. It is
restricted to public Bybit market-data GET requests for the candidate selected
by the reviewed reroute packet. It writes only artifacts; it never writes PG,
submits/cancels/modifies orders, grants probe/order/live authority, lowers the
Cost Gate, appends ledgers, or mutates runtime state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


PUBLIC_QUOTE_CAPTURE_SCHEMA_VERSION = (
    "bounded_probe_bbo_freshness_public_quote_capture_v1"
)
REROUTE_SCHEMA_VERSION = "bounded_demo_probe_lower_price_reroute_review_v1"
REROUTE_READY_STATUS = "LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW"

READY_STATUS = "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER"
STALE_STATUS = "PUBLIC_QUOTE_CAPTURE_BBO_STALE_NO_ORDER"
SOURCE_FAILURE_STATUS = "PUBLIC_QUOTE_CAPTURE_SOURCE_FAILURE_NO_ORDER"
INPUT_REQUIRED_STATUS = "PUBLIC_QUOTE_CAPTURE_INPUT_REQUIRED_NO_ORDER"
AUTHORITY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEFAULT_BASE_URL = "https://api.bybit.com"
ALLOWED_BASE_URLS = {"https://api.bybit.com", "https://api-demo.bybit.com"}
ALLOWED_HOSTS = {"api.bybit.com", "api-demo.bybit.com"}
TIME_PATH = "/v5/market/time"
TICKERS_PATH = "/v5/market/tickers"
INSTRUMENTS_PATH = "/v5/market/instruments-info"
USER_AGENT = "openclaw-bbo-public-quote-capture/1.0"

SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,40}$")

BOUNDARY = (
    "public market-data quote capture artifact only; no private/auth endpoint, "
    "PG write, order, cancel, modify, config, risk, auth, runtime/service/env/"
    "crontab mutation, global Cost Gate lowering, probe authority, order "
    "authority, live/mainnet authority, ledger append, or promotion proof"
)

DANGER_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "auth_headers_present",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "canonical_plan_mutation_performed",
    "config_mutation_performed",
    "cookie_headers_present",
    "cost_gate_lowering_recommended",
    "cost_gate_mutation_found",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "environment_mutation_performed",
    "execution_authority",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "live_promotion_performed",
    "mainnet_authority_granted",
    "operator_authorization_object_emitted",
    "order_authority",
    "order_authority_granted",
    "order_authority_granted_in_authorization_object",
    "order_authority_granted_in_object",
    "order_cancel_performed",
    "order_cancel_modify_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "private_endpoint_called",
    "probe_authority",
    "probe_authority_granted",
    "probe_authority_granted_in_authorization_object",
    "probe_authority_granted_in_object",
    "promotion_evidence",
    "promotion_proof",
    "review_grants_runtime_authority",
    "risk_mutation_performed",
    "runtime_env_mutation_performed",
    "runtime_mutation_performed",
    "runtime_order_authority_found",
    "runtime_order_authority_granted",
    "runtime_probe_authority_found",
    "runtime_probe_authority_granted",
    "service_restart_performed",
    "writer_enabled",
}

REQUEST_HEADER_ALLOWLIST = {"user-agent"}
AUTH_HEADER_PREFIXES = ("x-bapi-", "authorization")
MAX_TRANSPORT_REASON_CHARS = 240
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
COOKIE_FIELD_RE = re.compile(r"(?i)\b(?:cookie|set-cookie)\s*[:=].*")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([a-z0-9_-]*"
    r"(?:authorization|x-bapi-[a-z0-9-]+|api[_-]?key|secret|token|"
    r"password|passwd|dsn|database[_-]?url|openclaw_database_url)"
    r"[a-z0-9_-]*"
    r")\s*[:=]\s*[^\s,;&]+"
)
BEARER_TOKEN_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
LOCAL_PATH_RE = re.compile(r"(?<!:)(?:/(?:Users|home|tmp|var|private|etc|opt|usr|Volumes)/[^\s,;)'\"]+)")
URI_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s,;)'\"]+")

NowFn = Callable[[], dt.datetime]
MonotonicFn = Callable[[], float]
Opener = Callable[..., Any]


class _RedirectRefusedHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"redirect refused: {msg}",
            headers,
            fp,
        )


def _certifi_cafile() -> str | None:
    try:
        import certifi  # type: ignore[import-not-found]
    except ImportError:
        return None
    where = getattr(certifi, "where", None)
    if not callable(where):
        return None
    path = _str(where())
    return path or None


def _verified_ssl_context() -> ssl.SSLContext:
    cafile = _certifi_cafile()
    if cafile:
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


def _no_redirect_opener() -> urllib.request.OpenerDirector:
    https_handler = urllib.request.HTTPSHandler(context=_verified_ssl_context())
    return urllib.request.build_opener(_RedirectRefusedHandler, https_handler)


def urlopen_no_redirect(req: urllib.request.Request, timeout: float) -> Any:
    opener = _no_redirect_opener()
    return opener.open(req, timeout=timeout)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _round(value: Any, ndigits: int = 6) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _floats_equal(left: Any, right: Any, *, tolerance: float = 1e-9) -> bool:
    left_f = _float(left)
    right_f = _float(right)
    return (
        left_f is not None
        and right_f is not None
        and abs(left_f - right_f) <= tolerance
    )


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat()


def _ms_to_iso(value_ms: int | float | None) -> str | None:
    if value_ms is None:
        return None
    return dt.datetime.fromtimestamp(
        float(value_ms) / 1000.0, tz=dt.timezone.utc
    ).isoformat()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _sanitize_uri_in_diagnostic(match: re.Match[str]) -> str:
    url = match.group(0)
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "<url-redacted>"
    host = (parts.hostname or "").lower()
    if (
        parts.scheme == "https"
        and parts.netloc.lower() == host
        and host == urllib.parse.urlsplit(DEFAULT_BASE_URL).hostname
        and parts.path in {TIME_PATH, TICKERS_PATH, INSTRUMENTS_PATH}
    ):
        return urllib.parse.urlunsplit((parts.scheme, host, parts.path, "", ""))
    return "<url-redacted>"


def _sanitize_transport_reason(value: Any) -> str | None:
    text = _str(value)
    if not text:
        return None
    if "Traceback (most recent call last)" in text or "\n  File " in text:
        return "<traceback-redacted>"
    text = CONTROL_CHARS_RE.sub(" ", text)
    text = BEARER_TOKEN_RE.sub("Bearer <redacted>", text)
    text = COOKIE_FIELD_RE.sub("Cookie=<redacted>", text)
    text = SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=<redacted>", text)
    text = URI_RE.sub(_sanitize_uri_in_diagnostic, text)
    text = LOCAL_PATH_RE.sub("<path-redacted>", text)
    text = " ".join(text.split())
    if len(text) > MAX_TRANSPORT_REASON_CHARS:
        text = text[:MAX_TRANSPORT_REASON_CHARS] + "...<truncated>"
    return text or None


def _errno_from(value: Any) -> int | None:
    parsed = _int(getattr(value, "errno", None))
    if parsed is not None:
        return parsed
    args = getattr(value, "args", None)
    if isinstance(args, tuple) and args:
        return _int(args[0])
    return None


def _transport_error_diagnostics(exc: BaseException) -> dict[str, Any]:
    reason = getattr(exc, "reason", None)
    if reason is None:
        reason = exc
    return {
        "transport_error_class": type(exc).__name__,
        "transport_error_reason_type": type(reason).__name__ if reason is not None else None,
        "transport_error_reason_sanitized": _sanitize_transport_reason(reason),
        "transport_error_errno": _errno_from(reason),
        "transport_error_stage": "opener",
        "transport_error_sanitized": True,
    }


def _contaminating_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {
            "",
            "0",
            "false",
            "no",
            "none",
            "not_granted",
            "null",
            "unset",
        }
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    return True


def _authority_enum_contaminating(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().upper() not in {
            "",
            "0",
            "FALSE",
            "NO",
            "NONE",
            "NOT_GRANTED",
            "NULL",
            "UNSET",
        }
    return _contaminating_value(value)


def _iter_nodes(value: Any) -> list[Any]:
    nodes = [value]
    if isinstance(value, dict):
        for child in value.values():
            nodes.extend(_iter_nodes(child))
    elif isinstance(value, list):
        for child in value:
            nodes.extend(_iter_nodes(child))
    return nodes


def _authority_preserved(*payloads: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for payload in payloads:
        for node in _iter_nodes(_dict(payload)):
            if not isinstance(node, dict):
                continue
            for key, value in node.items():
                if (
                    key in DANGER_KEYS
                    and (
                        _authority_enum_contaminating(value)
                        if key
                        in {
                            "order_authority",
                            "probe_authority",
                            "execution_authority",
                        }
                        else _contaminating_value(value)
                    )
                ):
                    reasons.append(f"{key}_contaminating")
            if _str(node.get("main_cost_gate_adjustment")).upper() not in ("", "NONE"):
                reasons.append("main_cost_gate_adjustment_not_none")
    return not reasons, sorted(set(reasons))


def _normalized_horizon(value: Any) -> int | None:
    parsed = _float(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": _str(candidate.get("side_cell_key")) or None,
        "strategy_name": _str(candidate.get("strategy_name")) or None,
        "symbol": _str(candidate.get("symbol")).upper() or None,
        "side": _str(candidate.get("side")) or None,
        "outcome_horizon_minutes": _normalized_horizon(
            candidate.get("outcome_horizon_minutes")
        ),
    }


def _candidate_from_reroute(reroute_review: dict[str, Any] | None) -> dict[str, Any]:
    return _candidate_identity(_dict(_dict(reroute_review).get("selected_candidate")))


def _selected_candidate_from_reroute(
    reroute_review: dict[str, Any] | None,
) -> dict[str, Any]:
    return _dict(_dict(reroute_review).get("selected_candidate"))


def _reviewed_candidate_cap_usdt(
    reroute_review: dict[str, Any] | None,
) -> float | None:
    candidate = _selected_candidate_from_reroute(reroute_review)
    return _float(candidate.get("current_cap_usdt"))


def _candidate_identity_reasons(candidate: dict[str, Any]) -> list[str]:
    raw_symbol = _str(candidate.get("symbol"))
    symbol = raw_symbol.upper()
    strategy = _str(candidate.get("strategy_name"))
    side = _str(candidate.get("side"))
    side_cell_key = _str(candidate.get("side_cell_key"))
    horizon = _normalized_horizon(candidate.get("outcome_horizon_minutes"))
    reasons: list[str] = []
    if not side_cell_key or not strategy or not raw_symbol or not side or horizon is None:
        reasons.append("candidate_identity_incomplete")
    if raw_symbol and raw_symbol != symbol:
        reasons.append("candidate_symbol_not_uppercase")
    if symbol and SYMBOL_RE.fullmatch(symbol) is None:
        reasons.append("candidate_symbol_not_safe")
    if side and side not in {"Buy", "Sell"}:
        reasons.append("candidate_side_not_buy_sell")
    if horizon is not None and horizon <= 0:
        reasons.append("candidate_horizon_not_positive")
    if side_cell_key and strategy and symbol and side:
        expected_side_cell = f"{strategy}|{symbol}|{side}"
        if side_cell_key != expected_side_cell:
            reasons.append("candidate_side_cell_key_mismatch")
    return sorted(set(reasons))


def _candidate_identity_valid(candidate: dict[str, Any]) -> bool:
    return not _candidate_identity_reasons(candidate)


def _reroute_ready(reroute_review: dict[str, Any] | None) -> tuple[bool, list[str]]:
    payload = _dict(reroute_review)
    reasons: list[str] = []
    if payload.get("schema_version") != REROUTE_SCHEMA_VERSION:
        reasons.append("reroute_review_schema_mismatch")
    if payload.get("status") != REROUTE_READY_STATUS:
        reasons.append("reroute_review_not_ready")
    selected_candidate = _dict(payload.get("selected_candidate"))
    reasons.extend(_candidate_identity_reasons(selected_candidate))
    return not reasons, reasons


def _sorted_query(params: dict[str, Any]) -> str:
    clean = [(str(k), str(v)) for k, v in sorted(params.items())]
    return urllib.parse.urlencode(clean)


def _build_url(base_url: str, path: str, params: dict[str, Any]) -> str:
    base = base_url.rstrip("/")
    return f"{base}{path}?{_sorted_query(params)}" if params else f"{base}{path}"


def _headers_allowed(headers: dict[str, str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for key in headers:
        lowered = key.strip().lower()
        if lowered not in REQUEST_HEADER_ALLOWLIST:
            reasons.append(f"request_header_not_allowlisted:{lowered}")
        if lowered == "cookie" or lowered.startswith(AUTH_HEADER_PREFIXES):
            reasons.append(f"auth_or_cookie_header_present:{lowered}")
    return not reasons, sorted(set(reasons))


def _validate_request_envelope(
    *,
    url: str,
    method: str,
    expected_path: str,
    expected_params: dict[str, str],
    headers: dict[str, str],
) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        parts = urllib.parse.SplitResult("", "", "", "", "")
        reasons.append("url_parse_failed")
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    query = {
        key: values
        for key, values in urllib.parse.parse_qs(
            parts.query, keep_blank_values=True
        ).items()
    }
    flattened_query = {
        key: values[0] if len(values) == 1 else values
        for key, values in sorted(query.items())
    }
    if method.upper() != "GET":
        reasons.append("method_not_get")
    if scheme != "https":
        reasons.append("scheme_not_https")
    if host not in ALLOWED_HOSTS:
        reasons.append("host_not_allowlisted")
    if parts.path != expected_path:
        reasons.append("path_not_allowlisted")
    expected_flat = {str(k): str(v) for k, v in sorted(expected_params.items())}
    if flattened_query != expected_flat:
        reasons.append("query_not_exact_allowlist")
    headers_ok, header_reasons = _headers_allowed(headers)
    if not headers_ok:
        reasons.extend(header_reasons)
    details = {
        "scheme": scheme or None,
        "host": host or None,
        "path": parts.path or None,
        "query": flattened_query,
        "method": method.upper(),
        "headers_allowlisted": headers_ok,
        "headers_checked": sorted(headers.keys()),
    }
    return not reasons, sorted(set(reasons)), details


def _response_status(resp: Any) -> int | None:
    status = getattr(resp, "status", None)
    if status is not None:
        return _int(status)
    getcode = getattr(resp, "getcode", None)
    if callable(getcode):
        return _int(getcode())
    return None


def _response_headers(resp: Any) -> dict[str, str]:
    raw_headers = getattr(resp, "headers", None) or {}
    try:
        items = raw_headers.items()
    except AttributeError:
        return {}
    out: dict[str, str] = {}
    for key, value in items:
        lowered = str(key).lower()
        if lowered.startswith("x-bapi-limit") or lowered in {
            "ret_code",
            "traceid",
        }:
            out[str(key)] = str(value)
    return out


def _read_response(resp: Any) -> bytes:
    data = resp.read()
    if isinstance(data, bytes):
        return data
    return str(data).encode("utf-8")


def _http_get_json(
    *,
    label: str,
    base_url: str,
    path: str,
    params: dict[str, str],
    opener: Opener,
    timeout_seconds: float,
    now_fn: NowFn,
    monotonic_fn: MonotonicFn,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        headers.update({str(k): str(v) for k, v in extra_headers.items()})
    url = _build_url(base_url, path, params)
    envelope_ok, envelope_reasons, envelope = _validate_request_envelope(
        url=url,
        method="GET",
        expected_path=path,
        expected_params=params,
        headers=headers,
    )
    request_basis = {
        "method": "GET",
        "url": url,
        "headers": {key: headers[key] for key in sorted(headers)},
    }
    record: dict[str, Any] = {
        "label": label,
        "ok": False,
        "url": url,
        "canonical_request_sha256": _json_sha256(request_basis),
        "request_envelope": envelope,
        "request_envelope_ok": envelope_ok,
        "request_envelope_reasons": envelope_reasons,
        "redirect_refused": False,
        "redirect_status": None,
        "http_status": None,
        "retCode": None,
        "retMsg": None,
        "response_headers": {},
        "raw_response_sha256": None,
        "normalized_response_sha256": None,
        "request_start_utc": None,
        "request_end_utc": None,
        "duration_ms": None,
        "error": None,
        "transport_error_class": None,
        "transport_error_reason_type": None,
        "transport_error_reason_sanitized": None,
        "transport_error_errno": None,
        "transport_error_stage": None,
        "transport_error_sanitized": False,
    }
    if not envelope_ok:
        record["error"] = "request_envelope_violation"
        return record

    req = urllib.request.Request(url, headers=headers, method="GET")
    start_utc = now_fn().astimezone(dt.timezone.utc)
    start_mono = monotonic_fn()
    record["request_start_utc"] = _iso(start_utc)
    try:
        response_obj = opener(req, timeout=timeout_seconds)
        with response_obj as resp:
            status = _response_status(resp)
            raw = _read_response(resp)
            record["http_status"] = status
            record["response_headers"] = _response_headers(resp)
    except urllib.error.HTTPError as exc:
        record["http_status"] = _int(exc.code)
        if exc.code and 300 <= int(exc.code) < 400:
            record["redirect_refused"] = True
            record["redirect_status"] = int(exc.code)
            record["error"] = "redirect_refused"
        else:
            record["error"] = "http_error"
        try:
            raw = exc.read() or b""
        except Exception:
            raw = b""
        if raw:
            record["raw_response_sha256"] = _sha256_bytes(raw)
        end_utc = now_fn().astimezone(dt.timezone.utc)
        end_mono = monotonic_fn()
        record["request_end_utc"] = _iso(end_utc)
        record["duration_ms"] = round(max(0.0, end_mono - start_mono) * 1000.0, 3)
        return record
    except Exception as exc:  # noqa: BLE001 - artifact must fail closed.
        end_utc = now_fn().astimezone(dt.timezone.utc)
        end_mono = monotonic_fn()
        record["request_end_utc"] = _iso(end_utc)
        record["duration_ms"] = round(max(0.0, end_mono - start_mono) * 1000.0, 3)
        record["error"] = f"transport_error:{type(exc).__name__}"
        record.update(_transport_error_diagnostics(exc))
        return record
    end_utc = now_fn().astimezone(dt.timezone.utc)
    end_mono = monotonic_fn()
    record["request_end_utc"] = _iso(end_utc)
    record["duration_ms"] = round(max(0.0, end_mono - start_mono) * 1000.0, 3)
    record["raw_response_sha256"] = _sha256_bytes(raw)

    if record["http_status"] is None or not (200 <= int(record["http_status"]) < 300):
        record["error"] = "http_status_not_2xx"
        return record
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        record["error"] = "json_parse_error"
        return record
    if not isinstance(payload, dict):
        record["error"] = "json_object_required"
        return record
    record["payload"] = payload
    record["normalized_response_sha256"] = _json_sha256(payload)
    record["retCode"] = payload.get("retCode")
    record["retMsg"] = payload.get("retMsg")
    if payload.get("retCode") != 0:
        record["error"] = "bybit_retcode_not_zero"
        return record
    record["ok"] = True
    return record


def _bybit_time_ms(payload: dict[str, Any] | None) -> int | None:
    data = _dict(payload)
    top_time = _int(data.get("time"))
    if top_time is not None and top_time > 0:
        return top_time
    result = _dict(data.get("result"))
    time_nano = _int(result.get("timeNano"))
    if time_nano is not None and time_nano > 0:
        return int(time_nano / 1_000_000)
    time_second = _int(result.get("timeSecond"))
    if time_second is not None and time_second > 0:
        return time_second * 1000
    return None


def _single_result_row(payload: dict[str, Any] | None) -> tuple[dict[str, Any] | None, list[str]]:
    result = _dict(_dict(payload).get("result"))
    rows = [_dict(row) for row in _list(result.get("list"))]
    if len(rows) != 1:
        return None, ["result_list_must_have_exactly_one_row"]
    return rows[0], []


def _parse_ticker(payload: dict[str, Any] | None, *, symbol: str) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    row, row_reasons = _single_result_row(payload)
    reasons.extend(row_reasons)
    if row is None:
        return None, reasons
    if _str(row.get("symbol")).upper() != symbol:
        reasons.append("ticker_symbol_mismatch")
    bid = _float(row.get("bid1Price"))
    ask = _float(row.get("ask1Price"))
    bid_size = _float(row.get("bid1Size"))
    ask_size = _float(row.get("ask1Size"))
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        reasons.append("ticker_bid_ask_missing_or_nonpositive")
    elif bid >= ask:
        reasons.append("ticker_bid_ask_crossed_or_locked")
    if bid_size is None or ask_size is None or bid_size <= 0 or ask_size <= 0:
        reasons.append("ticker_bid_ask_size_missing_or_nonpositive")
    ticker_time_ms = _bybit_time_ms(payload)
    if ticker_time_ms is None:
        reasons.append("ticker_response_time_missing_or_malformed")
    parsed = {
        "symbol": _str(row.get("symbol")).upper() or None,
        "bid1Price": bid,
        "ask1Price": ask,
        "bid1Size": bid_size,
        "ask1Size": ask_size,
        "lastPrice": _float(row.get("lastPrice")),
        "markPrice": _float(row.get("markPrice")),
        "bybit_response_time_ms": ticker_time_ms,
        "bybit_response_time_utc": _ms_to_iso(ticker_time_ms),
        "spread_bps": (
            round(((ask - bid) / ((ask + bid) / 2.0)) * 10000.0, 6)
            if bid is not None and ask is not None and bid > 0 and ask > 0
            else None
        ),
    }
    return (parsed if not reasons else parsed), reasons


def _parse_instrument(
    payload: dict[str, Any] | None,
    *,
    symbol: str,
    category: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    row, row_reasons = _single_result_row(payload)
    reasons.extend(row_reasons)
    if row is None:
        return None, reasons
    if _str(row.get("symbol")).upper() != symbol:
        reasons.append("instrument_symbol_mismatch")
    status = _str(row.get("status"))
    if status != "Trading":
        reasons.append("instrument_status_not_trading")
    price_filter = _dict(row.get("priceFilter"))
    lot_filter = _dict(row.get("lotSizeFilter"))
    tick_size = _float(price_filter.get("tickSize"))
    qty_step = _float(lot_filter.get("qtyStep"))
    min_notional = _float(
        lot_filter.get("minNotionalValue") or lot_filter.get("minNotional")
    )
    if tick_size is None or tick_size <= 0:
        reasons.append("instrument_tick_size_missing_or_nonpositive")
    if qty_step is None or qty_step <= 0:
        reasons.append("instrument_qty_step_missing_or_nonpositive")
    if min_notional is None or min_notional <= 0:
        reasons.append("instrument_min_notional_missing_or_nonpositive")
    parsed = {
        "category": category,
        "symbol": _str(row.get("symbol")).upper() or None,
        "status": status or None,
        "tick_size": tick_size,
        "qty_step": qty_step,
        "min_notional": min_notional,
        "bybit_response_time_ms": _bybit_time_ms(payload),
        "bybit_response_time_utc": _ms_to_iso(_bybit_time_ms(payload)),
    }
    return (parsed if not reasons else parsed), reasons


def _parse_request_end_ms(record: dict[str, Any]) -> int | None:
    text = _str(record.get("request_end_utc"))
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.astimezone(dt.timezone.utc).timestamp() * 1000)


def _freshness(
    *,
    time_record: dict[str, Any],
    ticker_record: dict[str, Any],
    ticker_time_ms: int | None,
    max_fresh_bbo_age_ms: int,
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    time_ms = _bybit_time_ms(_dict(time_record.get("payload")))
    time_local_end_ms = _parse_request_end_ms(time_record)
    ticker_local_end_ms = _parse_request_end_ms(ticker_record)
    time_duration_ms = _float(time_record.get("duration_ms"))
    ticker_duration_ms = _float(ticker_record.get("duration_ms"))
    if time_ms is None:
        reasons.append("server_time_missing_or_malformed")
    if ticker_time_ms is None:
        reasons.append("ticker_time_missing_or_malformed")
    if time_local_end_ms is None or ticker_local_end_ms is None:
        reasons.append("local_request_end_time_missing_or_malformed")
    if time_duration_ms is None or ticker_duration_ms is None:
        reasons.append("request_duration_missing_or_malformed")
    if reasons:
        return {
            "freshness_rule": "bybit_server_time_offset_plus_request_durations",
            "effective_bbo_age_ms": None,
            "bbo_fresh": False,
            "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
        }, reasons

    assert time_ms is not None
    assert ticker_time_ms is not None
    assert time_local_end_ms is not None
    assert ticker_local_end_ms is not None
    assert time_duration_ms is not None
    assert ticker_duration_ms is not None
    local_minus_server_ms = time_local_end_ms - time_ms
    estimated_server_at_ticker_end_ms = ticker_local_end_ms - local_minus_server_ms
    raw_age_ms = estimated_server_at_ticker_end_ms - ticker_time_ms
    effective_age_ms = raw_age_ms + time_duration_ms + ticker_duration_ms
    if raw_age_ms < -1.0 or effective_age_ms < 0:
        reasons.append("ticker_time_future_or_clock_ambiguous")
    bbo_fresh = not reasons and effective_age_ms <= float(max_fresh_bbo_age_ms)
    if not bbo_fresh and not reasons:
        reasons.append("bbo_freshness_exceeds_gate")
    return {
        "freshness_rule": "bybit_server_time_offset_plus_request_durations",
        "server_time_ms": time_ms,
        "server_time_utc": _ms_to_iso(time_ms),
        "ticker_time_ms": ticker_time_ms,
        "ticker_time_utc": _ms_to_iso(ticker_time_ms),
        "time_request_end_local_ms": time_local_end_ms,
        "ticker_request_end_local_ms": ticker_local_end_ms,
        "local_minus_server_ms": local_minus_server_ms,
        "estimated_server_at_ticker_end_ms": estimated_server_at_ticker_end_ms,
        "raw_bbo_age_ms": round(raw_age_ms, 3),
        "time_request_duration_ms": round(time_duration_ms, 3),
        "ticker_request_duration_ms": round(ticker_duration_ms, 3),
        "effective_bbo_age_ms": round(effective_age_ms, 3),
        "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
        "bbo_fresh": bbo_fresh,
    }, reasons


def _attach_self_hash(packet: dict[str, Any]) -> dict[str, Any]:
    clone = dict(packet)
    clone.pop("artifact_self_hash_sha256", None)
    packet["artifact_self_hash_sha256"] = _json_sha256(clone)
    return packet


def capture_public_quote(
    *,
    reroute_review: dict[str, Any] | None,
    base_url: str = DEFAULT_BASE_URL,
    include_instruments_info: bool = True,
    timeout_seconds: float = 2.0,
    cap_usdt: float | None = None,
    max_fresh_bbo_age_ms: int = 1000,
    opener: Opener | None = None,
    now_fn: NowFn | None = None,
    monotonic_fn: MonotonicFn | None = None,
    extra_headers: dict[str, str] | None = None,
    authority_inputs: dict[str, Any] | None = None,
    source_head: str | None = None,
    runtime_head: str | None = None,
) -> dict[str, Any]:
    now_fn = now_fn or _utc_now
    monotonic_fn = monotonic_fn or time.monotonic
    opener = opener or urlopen_no_redirect
    generated_at = now_fn().astimezone(dt.timezone.utc)
    category = "linear"
    candidate = _candidate_from_reroute(reroute_review)
    selected_candidate = _selected_candidate_from_reroute(reroute_review)
    reviewed_cap_usdt = _reviewed_candidate_cap_usdt(reroute_review)
    effective_cap_usdt = cap_usdt if cap_usdt is not None else reviewed_cap_usdt
    symbol = _str(candidate.get("symbol")).upper()
    base_url_clean = base_url.rstrip("/")
    reroute_ok, reroute_reasons = _reroute_ready(reroute_review)
    authority_ok, authority_reasons = _authority_preserved(
        reroute_review,
        authority_inputs,
    )
    proposed_headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        proposed_headers.update({str(k): str(v) for k, v in extra_headers.items()})
    proposed_headers_ok, proposed_header_reasons = _headers_allowed(proposed_headers)
    auth_headers_present = any(
        key.strip().lower() == "cookie"
        or key.strip().lower().startswith(AUTH_HEADER_PREFIXES)
        for key in proposed_headers
    )
    cookie_headers_present = any(
        key.strip().lower() == "cookie" for key in proposed_headers
    )
    blocking_gates: list[str] = []
    blocking_gates.extend(reroute_reasons)
    if not proposed_headers_ok:
        blocking_gates.append("request_headers_allowlisted")
        blocking_gates.extend(proposed_header_reasons)
    if base_url_clean not in ALLOWED_BASE_URLS:
        blocking_gates.append("base_url_not_allowlisted")
    if timeout_seconds <= 0 or timeout_seconds > 10:
        blocking_gates.append("timeout_seconds_out_of_bounds")
    if max_fresh_bbo_age_ms <= 0 or max_fresh_bbo_age_ms > 5000:
        blocking_gates.append("max_fresh_bbo_age_ms_out_of_bounds")
    if reviewed_cap_usdt is None or reviewed_cap_usdt <= 0:
        blocking_gates.append("reroute_candidate_current_cap_invalid")
    elif cap_usdt is not None and not _floats_equal(cap_usdt, reviewed_cap_usdt):
        blocking_gates.append("cap_usdt_mismatch_reviewed_candidate_cap")
    if effective_cap_usdt is None or effective_cap_usdt <= 0:
        blocking_gates.append("cap_usdt_not_positive")

    requests: list[dict[str, Any]] = []
    ticker: dict[str, Any] | None = None
    instrument: dict[str, Any] | None = None
    freshness: dict[str, Any] = {
        "freshness_rule": "bybit_server_time_offset_plus_request_durations",
        "effective_bbo_age_ms": None,
        "bbo_fresh": False,
        "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
    }
    parse_reasons: list[str] = []

    if not authority_ok:
        status = AUTHORITY_VIOLATION_STATUS
        reason = "input_artifacts_contain_authority_or_mutation_contamination"
    elif blocking_gates:
        status = INPUT_REQUIRED_STATUS
        reason = "valid_ready_candidate_reroute_and_public_quote_parameters_required"
    else:
        time_record = _http_get_json(
            label="server_time",
            base_url=base_url_clean,
            path=TIME_PATH,
            params={},
            opener=opener,
            timeout_seconds=timeout_seconds,
            now_fn=now_fn,
            monotonic_fn=monotonic_fn,
            extra_headers=extra_headers,
        )
        ticker_record = _http_get_json(
            label="ticker",
            base_url=base_url_clean,
            path=TICKERS_PATH,
            params={"category": category, "symbol": symbol},
            opener=opener,
            timeout_seconds=timeout_seconds,
            now_fn=now_fn,
            monotonic_fn=monotonic_fn,
            extra_headers=extra_headers,
        )
        requests.extend([time_record, ticker_record])
        if include_instruments_info:
            instrument_record = _http_get_json(
                label="instrument",
                base_url=base_url_clean,
                path=INSTRUMENTS_PATH,
                params={"category": category, "symbol": symbol},
                opener=opener,
                timeout_seconds=timeout_seconds,
                now_fn=now_fn,
                monotonic_fn=monotonic_fn,
                extra_headers=extra_headers,
            )
            requests.append(instrument_record)
        else:
            instrument_record = None

        for record in requests:
            if record.get("ok") is not True:
                blocking_gates.append(f"{record.get('label')}_request_ok")
                if record.get("error"):
                    blocking_gates.append(str(record.get("error")))
                blocking_gates.extend(_list(record.get("request_envelope_reasons")))
        if time_record.get("ok") is True and ticker_record.get("ok") is True:
            ticker, ticker_reasons = _parse_ticker(
                _dict(ticker_record.get("payload")),
                symbol=symbol,
            )
            parse_reasons.extend(ticker_reasons)
            freshness, freshness_reasons = _freshness(
                time_record=time_record,
                ticker_record=ticker_record,
                ticker_time_ms=_dict(ticker).get("bybit_response_time_ms"),
                max_fresh_bbo_age_ms=max_fresh_bbo_age_ms,
            )
            parse_reasons.extend(freshness_reasons)
        if include_instruments_info and instrument_record and instrument_record.get("ok") is True:
            instrument, instrument_reasons = _parse_instrument(
                _dict(instrument_record.get("payload")),
                symbol=symbol,
                category=category,
            )
            parse_reasons.extend(instrument_reasons)
        blocking_gates.extend(parse_reasons)

        if blocking_gates:
            if "bbo_freshness_exceeds_gate" in blocking_gates:
                status = STALE_STATUS
                reason = "public_quote_bbo_age_exceeds_freshness_gate"
            else:
                status = SOURCE_FAILURE_STATUS
                reason = "public_quote_capture_failed_closed"
        elif freshness.get("bbo_fresh") is not True:
            status = STALE_STATUS
            reason = "public_quote_bbo_age_exceeds_freshness_gate"
            blocking_gates.append("bbo_freshness_exceeds_gate")
        else:
            status = READY_STATUS
            reason = "public_quote_capture_is_fresh_and_parseable_no_order"

    bybit_call_performed = any(_str(record.get("request_start_utc")) for record in requests)
    packet = {
        "schema_version": PUBLIC_QUOTE_CAPTURE_SCHEMA_VERSION,
        "generated_at_utc": _iso(generated_at),
        "status": status,
        "reason": reason,
        "candidate": candidate,
        "required_candidate": {
            "source": "reroute_review.selected_candidate",
            "identity_rule": "side_cell_key must equal strategy_name|symbol|side and symbol must be uppercase/safe before any request",
        },
        "candidate_match": _candidate_identity_valid(selected_candidate),
        "candidate_identity_valid": _candidate_identity_valid(selected_candidate),
        "source_head": source_head,
        "runtime_head": runtime_head,
        "market_data_environment": {
            "base_url": base_url_clean,
            "host": urllib.parse.urlsplit(base_url_clean).netloc.lower(),
            "execution_target": "demo",
            "public_market_data_only": True,
            "demo_live_applicability_note": (
                "public market data evidence only; not demo order behavior proof"
            ),
        },
        "endpoint_allowlist": {
            "methods": ["GET"],
            "base_urls": sorted(ALLOWED_BASE_URLS),
            "paths": [TIME_PATH, TICKERS_PATH, INSTRUMENTS_PATH],
            "symbol": symbol or None,
            "category": category,
            "orderbook_required": False,
            "private_or_order_paths_allowed": False,
        },
        "risk_limits": {
            "cap_usdt": effective_cap_usdt,
            "reviewed_candidate_cap_usdt": reviewed_cap_usdt,
            "cap_source": (
                "caller_supplied_must_match_reroute_review.selected_candidate.current_cap_usdt"
                if cap_usdt is not None
                else "reroute_review.selected_candidate.current_cap_usdt"
            ),
            "cap_semantics": (
                "reviewed bounded-probe candidate cap only; not the global risk "
                "single-order exposure source of truth"
            ),
            "global_risk_single_order_cap_resolved": False,
            "global_risk_single_order_cap_note": (
                "not resolved by public quote capture; order-capable admission "
                "must bind a machine-checkable global risk cap separately"
            ),
            "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
        },
        "requests": requests,
        "parsed": {
            "ticker": ticker,
            "instrument": instrument,
        },
        "derived": {
            "spread_bps": _dict(ticker).get("spread_bps"),
            "effective_bbo_age_ms": freshness.get("effective_bbo_age_ms"),
            "bbo_fresh": freshness.get("bbo_fresh") is True,
            "freshness": freshness,
        },
        "readiness": {
            "reroute_review_ready": reroute_ok,
            "candidate_exact_match": _candidate_identity_valid(selected_candidate),
            "candidate_identity_valid": _candidate_identity_valid(selected_candidate),
            "authority_preserved": authority_ok,
            "request_count": len(requests),
            "public_quote_capture_ready_no_order": status == READY_STATUS,
            "blocking_gates": sorted(set(blocking_gates)),
            "blocking_gate_count": len(set(blocking_gates)),
        },
        "blocking_gates": sorted(set(blocking_gates)),
        "blocking_gate_count": len(set(blocking_gates)),
        "authority_contamination_reasons": authority_reasons,
        "answers": {
            "bybit_call_performed": bybit_call_performed,
            "bybit_public_market_data_call_performed": bybit_call_performed,
            "bybit_private_call_performed": False,
            "private_endpoint_called": False,
            "auth_headers_present": auth_headers_present,
            "cookie_headers_present": cookie_headers_present,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "order_cancel_modify_performed": False,
            "runtime_mutation_performed": False,
            "runtime_env_mutation_performed": False,
            "service_restart_performed": False,
            "crontab_mutation_performed": False,
            "config_mutation_performed": False,
            "risk_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
            "fees_assumed": False,
        },
        "next_actions": [
            "review_public_quote_capture_artifact_before_any_order_admission",
            "do_not_feed_public_quote_artifact_into_pg_construction_preview_without_reviewed_adapter",
            "do_not_count_as_promotion_or_profit_proof",
        ],
        "boundary": BOUNDARY,
        "next_blocker_id": (
            "P0-BOUNDED-PROBE-PUBLIC-QUOTE-ONE-SHOT-RUNTIME-REVIEW-DEMO-ONLY"
            if not bybit_call_performed
            else "P0-BOUNDED-PROBE-PUBLIC-QUOTE-OUTCOME-REVIEW-DEMO-ONLY"
        ),
    }
    return _attach_self_hash(packet)


def render_markdown(packet: dict[str, Any]) -> str:
    ticker = _dict(_dict(packet.get("parsed")).get("ticker"))
    freshness = _dict(_dict(packet.get("derived")).get("freshness"))
    lines = [
        "# BBO Freshness Public Quote Capture",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Base URL: `{_dict(packet.get('market_data_environment')).get('base_url')}`",
        f"- Bid/ask: `{ticker.get('bid1Price')}` / `{ticker.get('ask1Price')}`",
        f"- Effective BBO age ms: `{freshness.get('effective_bbo_age_ms')}` / max `{freshness.get('max_fresh_bbo_age_ms')}`",
        f"- Blocking gates: `{packet.get('blocking_gates')}`",
        f"- Artifact self hash: `{packet.get('artifact_self_hash_sha256')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Requests",
        "",
    ]
    for request in _list(packet.get("requests")):
        request = _dict(request)
        lines.append(
            f"- `{request.get('label')}` ok=`{request.get('ok')}` "
            f"status=`{request.get('http_status')}` retCode=`{request.get('retCode')}` "
            f"duration_ms=`{request.get('duration_ms')}` raw_sha256=`{request.get('raw_response_sha256')}`"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in _list(packet.get("next_actions")):
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reroute-review-json", type=Path, required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    parser.add_argument("--cap-usdt", type=float)
    parser.add_argument("--max-fresh-bbo-age-ms", type=int, default=1000)
    parser.add_argument("--skip-instruments-info", action="store_true")
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = capture_public_quote(
        reroute_review=_read_json(args.reroute_review_json),
        base_url=args.base_url,
        include_instruments_info=not args.skip_instruments_info,
        timeout_seconds=args.timeout_seconds,
        cap_usdt=args.cap_usdt,
        max_fresh_bbo_age_ms=args.max_fresh_bbo_age_ms,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, sort_keys=True, ensure_ascii=False, default=str))
    if not args.json_output and not args.output and not args.print_json:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from cost_gate_learning_lane import bbo_freshness_public_quote_capture as quote_capture
from cost_gate_learning_lane import bounded_probe_candidate_construction_preview as construction_preview


SCHEMA_VERSION = "current_candidate_public_quote_construction_refresh_v1"
PUBLIC_QUOTE_SCHEMA_VERSION = "current_candidate_public_quote_capture_v1"
MARKET_SNAPSHOT_SCHEMA_VERSION = "current_candidate_public_quote_market_snapshot_v1"
CONSTRUCTION_PREVIEW_SCHEMA_VERSION = "current_candidate_no_order_construction_preview_v1"

CURRENT_ENVELOPE_SCHEMA_VERSION = "cost_gate_current_candidate_no_order_refresh_envelope_v1"
CURRENT_ENVELOPE_READY_STATUS = (
    "CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY"
)

READY_STATUS = "CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER"
ENVELOPE_NOT_READY_STATUS = "CURRENT_CANDIDATE_ENVELOPE_NOT_READY_NO_ORDER"
SOURCE_FAILURE_STATUS = "CURRENT_CANDIDATE_PUBLIC_QUOTE_CAPTURE_FAILED_CLOSED_NO_ORDER"
STALE_BBO_STATUS = "CURRENT_CANDIDATE_PUBLIC_QUOTE_BBO_STALE_NO_ORDER"
CONSTRUCTION_NOT_READY_STATUS = (
    "CURRENT_CANDIDATE_CONSTRUCTION_PREVIEW_NOT_READY_NO_ORDER"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEFAULT_MAX_ENVELOPE_AGE_SECONDS = 15 * 60
DEFAULT_MAX_FRESH_BBO_AGE_MS = 1000
DEFAULT_TIMEOUT_SECONDS = 2.0

AUTHORITY_TRUE_ANSWER_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authorized",
    "cap_envelope_mutation_allowed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "network_call_performed",
    "order_admission_ready",
    "order_authority_granted",
    "order_submission_performed",
    "operator_authorization_object_emitted",
    "pg_write_performed",
    "probe_authority_granted",
    "public_quote_capture_performed",
    "runtime_capture_allowed_by_this_packet",
    "runtime_mutation_performed",
}

ORDER_OR_PRIVATE_PATH_TOKENS = (
    "/v5/order",
    "/v5/position",
    "/v5/account",
    "/v5/execution",
    "/v5/user",
    "/v5/private",
)

NowFn = Callable[[], dt.datetime]
MonotonicFn = Callable[[], float]
Opener = Callable[..., Any]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> dt.datetime | None:
    text = _str(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat()


def _json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_path(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"json object required: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    strategy_name = _str(candidate.get("strategy_name"))
    symbol = _str(candidate.get("symbol")).upper()
    side = _str(candidate.get("side"))
    side_cell_key = _str(candidate.get("side_cell_key"))
    return {
        "side_cell_key": side_cell_key,
        "strategy_name": strategy_name,
        "symbol": symbol,
        "side": side,
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _candidate_identity_reasons(candidate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    strategy_name = _str(candidate.get("strategy_name"))
    raw_symbol = _str(candidate.get("symbol"))
    symbol = raw_symbol.upper()
    side = _str(candidate.get("side"))
    side_cell_key = _str(candidate.get("side_cell_key"))
    if not strategy_name:
        reasons.append("candidate_strategy_name_missing")
    if not raw_symbol:
        reasons.append("candidate_symbol_missing")
    elif raw_symbol != symbol:
        reasons.append("candidate_symbol_not_uppercase")
    if side not in {"Buy", "Sell"}:
        reasons.append("candidate_side_not_buy_sell")
    if not side_cell_key:
        reasons.append("candidate_side_cell_key_missing")
    elif side_cell_key != f"{strategy_name}|{symbol}|{side}":
        reasons.append("candidate_side_cell_key_mismatch")
    return reasons


def _authority_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for scope_name, scope in (
        ("answers", _dict(payload.get("answers"))),
        ("summary", _dict(payload.get("summary"))),
    ):
        for key in AUTHORITY_TRUE_ANSWER_KEYS:
            if scope.get(key) is True:
                reasons.append(f"{scope_name}.{key}_true")
    source_inputs = _dict(payload.get("source_inputs"))
    if source_inputs.get("authority_preserved") is False:
        reasons.append("source_inputs.authority_preserved_false")
    if source_inputs.get("bounded_auth_no_authority") is False:
        reasons.append("source_inputs.bounded_auth_no_authority_false")
    return sorted(set(reasons))


def _expected_requests(symbol: str) -> dict[str, dict[str, Any]]:
    return {
        "server_time": {
            "method": "GET",
            "path": quote_capture.TIME_PATH,
            "query": {},
        },
        "ticker": {
            "method": "GET",
            "path": quote_capture.TICKERS_PATH,
            "query": {"category": "linear", "symbol": symbol},
        },
        "instrument": {
            "method": "GET",
            "path": quote_capture.INSTRUMENTS_PATH,
            "query": {"category": "linear", "symbol": symbol},
        },
    }


def _request_envelope_reasons(
    envelope: dict[str, Any],
    *,
    symbol: str,
) -> list[str]:
    reasons: list[str] = []
    refresh = _dict(envelope.get("refresh_envelope"))
    review = _dict(refresh.get("request_envelope_review"))
    if review.get("method") != "GET":
        reasons.append("request_envelope_method_not_get")
    if review.get("additional_requests_allowed") is not False:
        reasons.append("request_envelope_allows_additional_requests")
    if review.get("private_or_order_paths_allowed") is not False:
        reasons.append("request_envelope_allows_private_or_order_paths")
    if review.get("auth_or_cookie_headers_allowed") is not False:
        reasons.append("request_envelope_allows_auth_or_cookie_headers")
    if review.get("redirects_allowed") is not False:
        reasons.append("request_envelope_allows_redirects")

    expected = _expected_requests(symbol)
    required = {
        _str(item.get("label")): _dict(item)
        for item in _list(review.get("required_requests"))
    }
    if set(required) != set(expected):
        reasons.append("request_envelope_required_request_labels_mismatch")
    for label, expected_request in expected.items():
        request = required.get(label)
        if not request:
            continue
        if request.get("method") != expected_request["method"]:
            reasons.append(f"request_envelope_{label}_method_mismatch")
        if request.get("path") != expected_request["path"]:
            reasons.append(f"request_envelope_{label}_path_mismatch")
        if _dict(request.get("query")) != expected_request["query"]:
            reasons.append(f"request_envelope_{label}_query_mismatch")
        path_text = _str(request.get("path")).lower()
        if any(token in path_text for token in ORDER_OR_PRIVATE_PATH_TOKENS):
            reasons.append(f"request_envelope_{label}_private_or_order_path")
    return sorted(set(reasons))


def _cap_resolution_reasons(
    cap_resolution: dict[str, Any],
    summary: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    cap = _float(cap_resolution.get("resolved_cap_usdt"))
    per_trade_fraction = _float(cap_resolution.get("per_trade_risk_pct_fraction"))
    per_trade_display = _float(cap_resolution.get("per_trade_risk_pct_display"))
    if cap is None or cap <= 0:
        reasons.append("resolved_gui_cap_usdt_missing_or_non_positive")
    if cap_resolution.get("risk_source_of_truth") != "GUI-backed Rust RiskConfig":
        reasons.append("risk_source_of_truth_not_gui_backed_rust_risk_config")
    if cap_resolution.get("bounded_probe_local_cap_usdt_is_authority") is not False:
        reasons.append("bounded_probe_local_cap_marked_authority")
    if summary.get("local_10_usdt_cap_is_global_risk_authority") is not False:
        reasons.append("summary_local_10_usdt_cap_marked_global_authority")
    if per_trade_fraction is None or per_trade_fraction <= 0:
        reasons.append("per_trade_risk_pct_fraction_missing_or_non_positive")
    elif per_trade_fraction > 1:
        reasons.append("per_trade_risk_pct_fraction_not_fraction")
    if (
        per_trade_fraction is not None
        and per_trade_display is not None
        and abs((per_trade_fraction * 100.0) - per_trade_display) > 1e-6
    ):
        reasons.append("per_trade_risk_pct_display_fraction_mismatch")
    return sorted(set(reasons))


def _validate_current_candidate_envelope(
    envelope: dict[str, Any],
    *,
    now_utc: dt.datetime,
    max_envelope_age_seconds: int,
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    if envelope.get("schema_version") != CURRENT_ENVELOPE_SCHEMA_VERSION:
        reasons.append("current_candidate_envelope_schema_version_invalid")
    if envelope.get("status") != CURRENT_ENVELOPE_READY_STATUS:
        reasons.append("current_candidate_envelope_status_not_ready")
    generated_at = _parse_dt(envelope.get("generated_at_utc"))
    if generated_at is None:
        reasons.append("current_candidate_envelope_generated_at_missing")
    else:
        age_seconds = (now_utc - generated_at).total_seconds()
        if age_seconds < 0:
            reasons.append("current_candidate_envelope_generated_in_future")
        elif age_seconds > max_envelope_age_seconds:
            reasons.append("current_candidate_envelope_stale")

    candidate = _candidate_identity(_dict(envelope.get("candidate")))
    reasons.extend(_candidate_identity_reasons(candidate))
    symbol = _str(candidate.get("symbol")).upper()
    if symbol:
        reasons.extend(_request_envelope_reasons(envelope, symbol=symbol))

    summary = _dict(envelope.get("summary"))
    answers = _dict(envelope.get("answers"))
    if summary.get("current_candidate_no_order_refresh_envelope_ready") is not True:
        reasons.append("summary_current_candidate_envelope_ready_false")
    if summary.get("public_quote_capture_performed") is not False:
        reasons.append("summary_public_quote_capture_not_false")
    if summary.get("network_call_performed") is not False:
        reasons.append("summary_network_call_performed_not_false")
    if summary.get("order_admission_ready") is not False:
        reasons.append("summary_order_admission_ready_not_false")
    if answers.get("current_candidate_no_order_refresh_envelope_ready") is not True:
        reasons.append("answers_current_candidate_envelope_ready_false")
    if answers.get("public_quote_capture_performed") is not False:
        reasons.append("answers_public_quote_capture_not_false")
    if answers.get("bybit_call_performed") is not False:
        reasons.append("answers_bybit_call_performed_not_false")

    reasons.extend(_authority_reasons(envelope))
    cap_resolution = _dict(envelope.get("cap_resolution"))
    reasons.extend(_cap_resolution_reasons(cap_resolution, summary))
    return candidate, sorted(set(reasons))


def _market_snapshot_from_parsed(
    *,
    candidate: dict[str, Any],
    ticker: dict[str, Any] | None,
    instrument: dict[str, Any] | None,
    freshness: dict[str, Any],
    cap_usdt: float,
    max_fresh_bbo_age_ms: int,
    source_public_quote_sha256: str,
    generated_at_utc: dt.datetime,
) -> dict[str, Any]:
    ticker_dict = _dict(ticker)
    instrument_dict = _dict(instrument)
    return {
        "schema_version": MARKET_SNAPSHOT_SCHEMA_VERSION,
        "generated_at_utc": _iso(generated_at_utc),
        "status": "CURRENT_CANDIDATE_MARKET_SNAPSHOT_READY_NO_ORDER",
        "candidate": candidate,
        "source": "bybit_public_quote_current_candidate_refresh",
        "source_public_quote_schema_version": PUBLIC_QUOTE_SCHEMA_VERSION,
        "source_public_quote_sha256": source_public_quote_sha256,
        "ticker": {
            "symbol": ticker_dict.get("symbol"),
            "best_bid": ticker_dict.get("bid1Price"),
            "best_ask": ticker_dict.get("ask1Price"),
            "bid_size": ticker_dict.get("bid1Size"),
            "ask_size": ticker_dict.get("ask1Size"),
            "last_price": ticker_dict.get("lastPrice"),
            "mark_price": ticker_dict.get("markPrice"),
            "spread_bps": ticker_dict.get("spread_bps"),
            "ts": ticker_dict.get("bybit_response_time_utc"),
        },
        "instrument": {
            "category": instrument_dict.get("category"),
            "symbol": instrument_dict.get("symbol"),
            "status": instrument_dict.get("status"),
            "tick_size": instrument_dict.get("tick_size"),
            "qty_step": instrument_dict.get("qty_step"),
            "min_notional": instrument_dict.get("min_notional"),
            "ts": instrument_dict.get("bybit_response_time_utc"),
        },
        "derived": {
            "best_bid": ticker_dict.get("bid1Price"),
            "best_ask": ticker_dict.get("ask1Price"),
            "spread_bps": ticker_dict.get("spread_bps"),
            "instrument_status": instrument_dict.get("status"),
            "tick_size": instrument_dict.get("tick_size"),
            "qty_step": instrument_dict.get("qty_step"),
            "min_notional": instrument_dict.get("min_notional"),
            "bbo_age_ms": freshness.get("effective_bbo_age_ms"),
            "bbo_fresh": freshness.get("bbo_fresh") is True,
        },
        "risk_limits": {
            "cap_usdt": cap_usdt,
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
            "gui_risk_config_is_source_of_truth": True,
            "bounded_probe_local_10_usdt_cap_is_authority": False,
        },
        "answers": _no_authority_answers(
            bybit_call_performed=True,
            bybit_public_market_data_call_performed=True,
            public_quote_capture_performed=True,
        ),
    }


def _no_authority_answers(**overrides: Any) -> dict[str, Any]:
    answers = {
        "source_only_research_artifact": True,
        "public_market_data_only": True,
        "bybit_call_performed": False,
        "bybit_public_market_data_call_performed": False,
        "bybit_private_call_performed": False,
        "private_endpoint_called": False,
        "network_call_performed": False,
        "public_quote_capture_performed": False,
        "order_submission_performed": False,
        "order_admission_ready": False,
        "order_authority_granted": False,
        "probe_authority_granted": False,
        "live_authority_granted": False,
        "runtime_mutation_performed": False,
        "pg_write_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "bounded_probe_local_10_usdt_cap_is_authority": False,
    }
    if overrides.get("bybit_call_performed") is True:
        answers["network_call_performed"] = True
    answers.update(overrides)
    return answers


def _attach_self_hash(packet: dict[str, Any]) -> dict[str, Any]:
    clone = dict(packet)
    clone.pop("artifact_self_hash_sha256", None)
    packet["artifact_self_hash_sha256"] = _json_sha256(clone)
    return packet


def build_current_candidate_public_quote_construction_refresh(
    *,
    current_candidate_envelope: dict[str, Any],
    current_candidate_envelope_path: Path | None = None,
    base_url: str = quote_capture.DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_fresh_bbo_age_ms: int = DEFAULT_MAX_FRESH_BBO_AGE_MS,
    max_envelope_age_seconds: int = DEFAULT_MAX_ENVELOPE_AGE_SECONDS,
    opener: Opener | None = None,
    now_fn: NowFn | None = None,
    monotonic_fn: MonotonicFn | None = None,
    source_head: str | None = None,
    runtime_head: str | None = None,
) -> dict[str, Any]:
    now_fn = now_fn or _utc_now
    monotonic_fn = monotonic_fn or time.monotonic
    opener = opener or quote_capture.urlopen_no_redirect
    generated_at = now_fn().astimezone(dt.timezone.utc)
    base_url_clean = base_url.rstrip("/")
    candidate, envelope_reasons = _validate_current_candidate_envelope(
        current_candidate_envelope,
        now_utc=generated_at,
        max_envelope_age_seconds=max_envelope_age_seconds,
    )
    symbol = _str(candidate.get("symbol")).upper()
    cap_resolution = _dict(current_candidate_envelope.get("cap_resolution"))
    cap_usdt = _float(cap_resolution.get("resolved_cap_usdt"))

    blocking_gates: list[str] = []
    blocking_gates.extend(envelope_reasons)
    if base_url_clean not in quote_capture.ALLOWED_BASE_URLS:
        blocking_gates.append("base_url_not_allowlisted")
    if timeout_seconds <= 0 or timeout_seconds > 10:
        blocking_gates.append("timeout_seconds_out_of_bounds")
    if max_fresh_bbo_age_ms <= 0 or max_fresh_bbo_age_ms > 5000:
        blocking_gates.append("max_fresh_bbo_age_ms_out_of_bounds")
    if cap_usdt is None or cap_usdt <= 0:
        blocking_gates.append("resolved_cap_usdt_not_positive")

    authority_reasons = [
        reason
        for reason in blocking_gates
        if "authority" in reason or "order_authority" in reason
    ]
    requests: list[dict[str, Any]] = []
    ticker: dict[str, Any] | None = None
    instrument: dict[str, Any] | None = None
    freshness: dict[str, Any] = {
        "freshness_rule": "bybit_server_time_offset_plus_request_durations",
        "effective_bbo_age_ms": None,
        "bbo_fresh": False,
        "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
    }

    if authority_reasons:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "input_artifacts_contain_authority_or_mutation_contamination"
    elif blocking_gates:
        status = ENVELOPE_NOT_READY_STATUS
        reason = "current_candidate_envelope_and_no_order_request_contract_required"
    else:
        assert cap_usdt is not None
        time_record = quote_capture._http_get_json(
            label="server_time",
            base_url=base_url_clean,
            path=quote_capture.TIME_PATH,
            params={},
            opener=opener,
            timeout_seconds=timeout_seconds,
            now_fn=now_fn,
            monotonic_fn=monotonic_fn,
            extra_headers=None,
        )
        ticker_record = quote_capture._http_get_json(
            label="ticker",
            base_url=base_url_clean,
            path=quote_capture.TICKERS_PATH,
            params={"category": "linear", "symbol": symbol},
            opener=opener,
            timeout_seconds=timeout_seconds,
            now_fn=now_fn,
            monotonic_fn=monotonic_fn,
            extra_headers=None,
        )
        instrument_record = quote_capture._http_get_json(
            label="instrument",
            base_url=base_url_clean,
            path=quote_capture.INSTRUMENTS_PATH,
            params={"category": "linear", "symbol": symbol},
            opener=opener,
            timeout_seconds=timeout_seconds,
            now_fn=now_fn,
            monotonic_fn=monotonic_fn,
            extra_headers=None,
        )
        requests.extend([time_record, ticker_record, instrument_record])
        for record in requests:
            if record.get("ok") is not True:
                blocking_gates.append(f"{record.get('label')}_request_ok")
                if record.get("error"):
                    blocking_gates.append(str(record.get("error")))
                blocking_gates.extend(_list(record.get("request_envelope_reasons")))
        parse_reasons: list[str] = []
        if time_record.get("ok") is True and ticker_record.get("ok") is True:
            ticker, ticker_reasons = quote_capture._parse_ticker(
                _dict(ticker_record.get("payload")),
                symbol=symbol,
            )
            parse_reasons.extend(ticker_reasons)
            freshness, freshness_reasons = quote_capture._freshness(
                time_record=time_record,
                ticker_record=ticker_record,
                ticker_time_ms=_dict(ticker).get("bybit_response_time_ms"),
                max_fresh_bbo_age_ms=max_fresh_bbo_age_ms,
            )
            parse_reasons.extend(freshness_reasons)
        if instrument_record.get("ok") is True:
            instrument, instrument_reasons = quote_capture._parse_instrument(
                _dict(instrument_record.get("payload")),
                symbol=symbol,
                category="linear",
            )
            parse_reasons.extend(instrument_reasons)
        blocking_gates.extend(parse_reasons)
        if blocking_gates:
            if "bbo_freshness_exceeds_gate" in blocking_gates:
                status = STALE_BBO_STATUS
                reason = "public_quote_bbo_age_exceeds_freshness_gate"
            else:
                status = SOURCE_FAILURE_STATUS
                reason = "public_quote_capture_failed_closed"
        elif freshness.get("bbo_fresh") is not True:
            blocking_gates.append("bbo_freshness_exceeds_gate")
            status = STALE_BBO_STATUS
            reason = "public_quote_bbo_age_exceeds_freshness_gate"
        else:
            status = READY_STATUS
            reason = "fresh_public_quote_and_no_order_construction_preview_ready"

    public_quote = {
        "schema_version": PUBLIC_QUOTE_SCHEMA_VERSION,
        "generated_at_utc": _iso(generated_at),
        "status": (
            "CURRENT_CANDIDATE_PUBLIC_QUOTE_READY_NO_ORDER"
            if status in {READY_STATUS, CONSTRUCTION_NOT_READY_STATUS}
            else status
        ),
        "reason": reason,
        "candidate": candidate,
        "source_head": source_head,
        "runtime_head": runtime_head,
        "source_current_candidate_envelope": {
            "path": str(current_candidate_envelope_path)
            if current_candidate_envelope_path
            else None,
            "sha256": _sha256_path(current_candidate_envelope_path),
            "schema_version": current_candidate_envelope.get("schema_version"),
            "status": current_candidate_envelope.get("status"),
            "generated_at_utc": current_candidate_envelope.get("generated_at_utc"),
        },
        "market_data_environment": {
            "base_url": base_url_clean,
            "host": urllib.parse.urlsplit(base_url_clean).netloc.lower(),
            "execution_target": "demo",
            "public_market_data_only": True,
            "private_or_order_paths_allowed": False,
        },
        "endpoint_allowlist": {
            "methods": ["GET"],
            "base_urls": sorted(quote_capture.ALLOWED_BASE_URLS),
            "paths": [
                quote_capture.TIME_PATH,
                quote_capture.TICKERS_PATH,
                quote_capture.INSTRUMENTS_PATH,
            ],
            "symbol": symbol or None,
            "category": "linear",
            "additional_requests_allowed": False,
            "private_or_order_paths_allowed": False,
            "auth_or_cookie_headers_allowed": False,
        },
        "risk_limits": {
            "cap_usdt": cap_usdt,
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "risk_source_of_truth": cap_resolution.get("risk_source_of_truth"),
            "per_trade_risk_pct_fraction": cap_resolution.get(
                "per_trade_risk_pct_fraction"
            ),
            "per_trade_risk_pct_display": cap_resolution.get(
                "per_trade_risk_pct_display"
            ),
            "account_equity_usdt": cap_resolution.get("account_equity_usdt"),
            "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
            "bounded_probe_local_10_usdt_cap_is_authority": False,
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
            "current_candidate_envelope_ready": not envelope_reasons,
            "candidate_identity_valid": not _candidate_identity_reasons(candidate),
            "cap_matches_resolved_gui_risk_cap": cap_usdt is not None and cap_usdt > 0,
            "request_count": len(requests),
            "public_quote_capture_ready_no_order": status == READY_STATUS,
            "blocking_gates": sorted(set(blocking_gates)),
            "blocking_gate_count": len(set(blocking_gates)),
        },
        "blocking_gates": sorted(set(blocking_gates)),
        "blocking_gate_count": len(set(blocking_gates)),
        "authority_contamination_reasons": authority_reasons,
        "answers": _no_authority_answers(
            bybit_call_performed=bool(requests),
            bybit_public_market_data_call_performed=bool(requests),
            public_quote_capture_performed=bool(requests),
        ),
    }
    _attach_self_hash(public_quote)

    market_snapshot: dict[str, Any] | None = None
    construction: dict[str, Any] = {
        "constructible": False,
        "reason": "public_quote_not_ready",
    }
    if status == READY_STATUS and cap_usdt is not None:
        market_snapshot = _market_snapshot_from_parsed(
            candidate=candidate,
            ticker=ticker,
            instrument=instrument,
            freshness=freshness,
            cap_usdt=cap_usdt,
            max_fresh_bbo_age_ms=max_fresh_bbo_age_ms,
            source_public_quote_sha256=public_quote["artifact_self_hash_sha256"],
            generated_at_utc=generated_at,
        )
        inputs = construction_preview._market_inputs(market_snapshot)
        construction = construction_preview._placement_and_sizing(
            candidate=candidate,
            inputs=inputs,
        )
        if construction.get("constructible") is not True:
            status = CONSTRUCTION_NOT_READY_STATUS
            reason = "current_candidate_construction_preview_not_constructible"
            blocking_gates.extend(_list(construction.get("blocking_reasons")))
            blocking_gates.append(_str(construction.get("reason")) or "not_constructible")

    if market_snapshot is None:
        market_snapshot = {
            "schema_version": MARKET_SNAPSHOT_SCHEMA_VERSION,
            "generated_at_utc": _iso(generated_at),
            "status": "CURRENT_CANDIDATE_MARKET_SNAPSHOT_NOT_READY_NO_ORDER",
            "candidate": candidate,
            "source": "bybit_public_quote_current_candidate_refresh",
            "risk_limits": {
                "cap_usdt": cap_usdt,
                "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
                "gui_risk_config_is_source_of_truth": True,
                "bounded_probe_local_10_usdt_cap_is_authority": False,
            },
            "blocking_gates": sorted(set(blocking_gates)),
            "answers": _no_authority_answers(
                bybit_call_performed=bool(requests),
                bybit_public_market_data_call_performed=bool(requests),
                public_quote_capture_performed=bool(requests),
            ),
        }
    _attach_self_hash(market_snapshot)

    construction_preview_packet = {
        "schema_version": CONSTRUCTION_PREVIEW_SCHEMA_VERSION,
        "generated_at_utc": _iso(generated_at),
        "status": (
            "CURRENT_CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER"
            if status == READY_STATUS
            else CONSTRUCTION_NOT_READY_STATUS
        ),
        "reason": (
            "constructible_under_resolved_gui_cap_no_order"
            if status == READY_STATUS
            else reason
        ),
        "candidate": candidate,
        "construction": construction,
        "risk_limits": {
            "cap_usdt": cap_usdt,
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "risk_source_of_truth": cap_resolution.get("risk_source_of_truth"),
            "per_trade_risk_pct_display": cap_resolution.get(
                "per_trade_risk_pct_display"
            ),
            "account_equity_usdt": cap_resolution.get("account_equity_usdt"),
            "bounded_probe_local_10_usdt_cap_is_authority": False,
        },
        "market_snapshot_sha256": market_snapshot.get("artifact_self_hash_sha256"),
        "order_admission_ready": False,
        "blocking_gates": sorted(set(blocking_gates)),
        "answers": _no_authority_answers(
            bybit_call_performed=bool(requests),
            bybit_public_market_data_call_performed=bool(requests),
            public_quote_capture_performed=bool(requests),
        ),
    }
    _attach_self_hash(construction_preview_packet)

    packet = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso(generated_at),
        "status": status,
        "reason": reason,
        "candidate": candidate,
        "source_head": source_head,
        "runtime_head": runtime_head,
        "source_current_candidate_envelope": {
            "path": str(current_candidate_envelope_path)
            if current_candidate_envelope_path
            else None,
            "sha256": _sha256_path(current_candidate_envelope_path),
            "schema_version": current_candidate_envelope.get("schema_version"),
            "status": current_candidate_envelope.get("status"),
            "generated_at_utc": current_candidate_envelope.get("generated_at_utc"),
        },
        "cap_resolution": cap_resolution,
        "public_quote": public_quote,
        "market_snapshot": market_snapshot,
        "construction_preview": construction_preview_packet,
        "summary": {
            "current_candidate_public_quote_construction_refresh_ready": (
                status == READY_STATUS
            ),
            "public_quote_capture_performed": bool(requests),
            "network_call_performed": bool(requests),
            "bybit_public_market_data_call_performed": bool(requests),
            "bybit_private_call_performed": False,
            "private_endpoint_called": False,
            "request_count": len(requests),
            "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
            "resolved_cap_usdt": cap_usdt,
            "cap_source": "current_candidate_envelope.cap_resolution.resolved_cap_usdt",
            "gui_risk_config_is_source_of_truth": True,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "construction_constructible": construction.get("constructible") is True,
            "order_admission_ready": False,
            "order_or_probe_authority_granted": False,
            "runtime_mutation_performed": False,
            "pg_write_performed": False,
        },
        "blocking_gates": sorted(set(blocking_gates)),
        "blocking_gate_count": len(set(blocking_gates)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
        "answers": _no_authority_answers(
            bybit_call_performed=bool(requests),
            bybit_public_market_data_call_performed=bool(requests),
            public_quote_capture_performed=bool(requests),
        ),
        "artifacts": {},
    }
    _attach_self_hash(packet)
    return packet


def render_markdown(packet: dict[str, Any]) -> str:
    candidate = _dict(packet.get("candidate"))
    summary = _dict(packet.get("summary"))
    construction = _dict(_dict(packet.get("construction_preview")).get("construction"))
    lines = [
        "# Current Candidate Public Quote / Construction Refresh",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- Resolved GUI cap USDT: `{summary.get('resolved_cap_usdt')}`",
        f"- Cap source: `{summary.get('cap_source')}`",
        f"- Public quote requests: `{summary.get('request_count')}`",
        f"- BBO age ms: `{_dict(_dict(packet.get('public_quote')).get('derived')).get('effective_bbo_age_ms')}`",
        f"- Constructible: `{construction.get('constructible')}`",
        f"- Limit price: `{construction.get('limit_price')}`",
        f"- Rounded qty: `{construction.get('rounded_qty')}`",
        f"- Rounded notional USDT: `{construction.get('rounded_notional_usdt')}`",
        f"- Order admission ready: `{summary.get('order_admission_ready')}`",
        f"- Local 10 USDT cap is global risk authority: `{summary.get('local_10_usdt_cap_is_global_risk_authority')}`",
        "",
        "## Blocking Gates",
    ]
    blocking = _list(packet.get("blocking_gates"))
    if blocking:
        lines.extend(f"- `{gate}`" for gate in blocking)
    else:
        lines.append("- none")
    lines.extend(["", "## Artifacts"])
    artifacts = _dict(packet.get("artifacts"))
    if artifacts:
        for name, meta in sorted(artifacts.items()):
            meta_dict = _dict(meta)
            lines.append(
                f"- `{name}`: `{meta_dict.get('path')}` sha256=`{meta_dict.get('sha256')}`"
            )
    else:
        lines.append("- not written by in-memory builder")
    return "\n".join(lines)


def write_artifacts(packet: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_payloads = {
        "public_quote": _dict(packet.get("public_quote")),
        "market_snapshot": _dict(packet.get("market_snapshot")),
        "construction_preview": _dict(packet.get("construction_preview")),
    }
    artifacts: dict[str, dict[str, str | None]] = {}
    for name, payload in artifact_payloads.items():
        json_path = output_dir / f"{name}.json"
        md_path = output_dir / f"{name}.md"
        _write_json(json_path, payload)
        _write_text(md_path, render_markdown({**packet, "artifacts": {}}))
        artifacts[name] = {
            "path": str(json_path),
            "sha256": _sha256_path(json_path),
            "markdown_path": str(md_path),
            "markdown_sha256": _sha256_path(md_path),
        }
    packet["artifacts"] = artifacts
    _attach_self_hash(packet)
    summary_path = output_dir / "current_candidate_public_quote_construction_refresh.json"
    summary_md_path = output_dir / "current_candidate_public_quote_construction_refresh.md"
    _write_json(summary_path, packet)
    _write_text(summary_md_path, render_markdown(packet))
    packet["summary_artifact"] = {
        "path": str(summary_path),
        "sha256": _sha256_path(summary_path),
        "markdown_path": str(summary_md_path),
        "markdown_sha256": _sha256_path(summary_md_path),
    }
    return packet


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a current-candidate no-order public quote and construction "
            "refresh using GUI-resolved cap from the current candidate envelope."
        )
    )
    parser.add_argument(
        "--current-candidate-envelope-json",
        required=True,
        type=Path,
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--base-url",
        default=quote_capture.DEFAULT_BASE_URL,
        choices=sorted(quote_capture.ALLOWED_BASE_URLS),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--max-fresh-bbo-age-ms",
        type=int,
        default=DEFAULT_MAX_FRESH_BBO_AGE_MS,
    )
    parser.add_argument(
        "--max-envelope-age-seconds",
        type=int,
        default=DEFAULT_MAX_ENVELOPE_AGE_SECONDS,
    )
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    envelope = _read_json(args.current_candidate_envelope_json)
    packet = build_current_candidate_public_quote_construction_refresh(
        current_candidate_envelope=envelope,
        current_candidate_envelope_path=args.current_candidate_envelope_json,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        max_fresh_bbo_age_ms=args.max_fresh_bbo_age_ms,
        max_envelope_age_seconds=args.max_envelope_age_seconds,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    packet = write_artifacts(packet, args.output_dir)
    print(json.dumps(
        {
            "status": packet.get("status"),
            "summary_path": packet["summary_artifact"]["path"],
            "summary_sha256": packet["summary_artifact"]["sha256"],
            "request_count": _dict(packet.get("summary")).get("request_count"),
            "resolved_cap_usdt": _dict(packet.get("summary")).get("resolved_cap_usdt"),
            "order_admission_ready": _dict(packet.get("summary")).get(
                "order_admission_ready"
            ),
        },
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Adapt one reviewed public quote capture into a construction market snapshot.

This helper is source-only glue between the reviewed public quote capture
artifact and the existing no-order construction preview. It does not call Bybit,
query or write PG, submit orders, lower gates, grant authority, or mutate
runtime state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.bounded_probe_candidate_construction_preview import (
    MARKET_SNAPSHOT_SCHEMA_VERSION,
    PUBLIC_QUOTE_ADAPTER_STATUS,
    PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE,
)


PUBLIC_QUOTE_SCHEMA_VERSION = "bounded_probe_bbo_freshness_public_quote_capture_v1"
PUBLIC_QUOTE_READY_STATUS = "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER"
LOWER_PRICE_REROUTE_REVIEW_SCHEMA_VERSION = (
    "bounded_demo_probe_lower_price_reroute_review_v1"
)
LOWER_PRICE_REROUTE_READY_STATUS = (
    "LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW"
)
BOUNDARY = (
    "public quote artifact to construction market snapshot adapter; no Bybit call, "
    "PG query/write, order, config, risk, auth, runtime mutation, Cost Gate "
    "lowering, probe authority, order authority, live/mainnet authority, ledger "
    "append, or promotion proof"
)
CANONICAL_MAX_FRESH_BBO_AGE_MS = 1000
FORBIDDEN_TRUE_KEYS = {
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
PUBLIC_QUOTE_ALLOWED_TRUE_KEYS = {
    "bybit_call_performed",
    "bybit_public_market_data_call_performed",
}


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


def _round(value: Any, ndigits: int = 6) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _floats_equal(left: Any, right: Any, *, tolerance: float = 1e-9) -> bool:
    parsed_left = _float(left)
    parsed_right = _float(right)
    if parsed_left is None or parsed_right is None:
        return False
    return abs(parsed_left - parsed_right) <= tolerance


def _contaminating_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    return True


def _authority_enum_contaminating(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().upper() not in {
            "",
            "0",
            "FALSE",
            "NO",
            "NONE",
            "NULL",
            "NOT_GRANTED",
            "UNSET",
        }
    return _contaminating_value(value)


def _iter_nodes(value: Any) -> list[Any]:
    out = [value]
    if isinstance(value, dict):
        for child in value.values():
            out.extend(_iter_nodes(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(_iter_nodes(child))
    return out


def _authority_contamination_reasons(
    payload: dict[str, Any],
    *,
    allowed_true_keys: set[str] | None = None,
) -> list[str]:
    allowed = allowed_true_keys or set()
    reasons: list[str] = []
    for node in _iter_nodes(payload):
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if key in FORBIDDEN_TRUE_KEYS and key not in allowed:
                contaminating = (
                    _authority_enum_contaminating(value)
                    if key in {"order_authority", "probe_authority", "execution_authority"}
                    else _contaminating_value(value)
                )
                if contaminating:
                    reasons.append(f"{key}_contaminating")
        if _str(node.get("main_cost_gate_adjustment")).upper() not in ("", "NONE"):
            reasons.append("main_cost_gate_adjustment_not_none")
    return sorted(set(reasons))


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


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path_payload_matches(path: Path | None, payload: dict[str, Any]) -> bool:
    if path is None or not path.exists() or not path.is_file():
        return False
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return parsed == payload


def _is_sha256_hex(value: Any) -> bool:
    text = _str(value)
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text.lower())


def _candidate_identity(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": payload.get("side_cell_key"),
        "strategy_name": payload.get("strategy_name"),
        "symbol": payload.get("symbol"),
        "side": payload.get("side"),
        "outcome_horizon_minutes": payload.get("outcome_horizon_minutes"),
    }


def _identity_key(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
        payload.get("side_cell_key"),
        payload.get("strategy_name"),
        payload.get("symbol"),
        payload.get("side"),
        payload.get("outcome_horizon_minutes"),
    )


def _reroute_candidate(reroute_review: dict[str, Any]) -> dict[str, Any]:
    return _candidate_identity(_dict(reroute_review.get("selected_candidate")))


def _reroute_selected_candidate(reroute_review: dict[str, Any]) -> dict[str, Any]:
    return _dict(reroute_review.get("selected_candidate"))


def _quote_candidate(public_quote: dict[str, Any]) -> dict[str, Any]:
    return _candidate_identity(_dict(public_quote.get("candidate")))


def _answers_false_or_none(answers: dict[str, Any], keys: list[str]) -> bool:
    for key in keys:
        value = answers.get(key)
        if value not in (False, None, "", "NONE"):
            return False
    return True


def _validate_inputs(
    *,
    public_quote: dict[str, Any],
    reroute_review: dict[str, Any],
    public_quote_path: Path | None,
    reroute_review_path: Path | None,
    generated_at_utc: dt.datetime,
    cap_usdt: float | None,
    max_fresh_bbo_age_ms: int | None,
) -> list[str]:
    reasons: list[str] = []
    if _sha256(public_quote_path) is None:
        reasons.append("public_quote_path_sha_required")
    elif not _path_payload_matches(public_quote_path, public_quote):
        reasons.append("public_quote_path_payload_mismatch")
    if _sha256(reroute_review_path) is None:
        reasons.append("reroute_review_path_sha_required")
    elif not _path_payload_matches(reroute_review_path, reroute_review):
        reasons.append("reroute_review_path_payload_mismatch")
    if (
        max_fresh_bbo_age_ms is not None
        and max_fresh_bbo_age_ms > CANONICAL_MAX_FRESH_BBO_AGE_MS
    ):
        reasons.append("max_fresh_bbo_age_ms_wider_than_canonical")
    if public_quote.get("schema_version") != PUBLIC_QUOTE_SCHEMA_VERSION:
        reasons.append("public_quote_schema_mismatch")
    if public_quote.get("status") != PUBLIC_QUOTE_READY_STATUS:
        reasons.append("public_quote_not_ready")
    if reroute_review.get("schema_version") != LOWER_PRICE_REROUTE_REVIEW_SCHEMA_VERSION:
        reasons.append("reroute_review_schema_mismatch")
    if reroute_review.get("status") != LOWER_PRICE_REROUTE_READY_STATUS:
        reasons.append("reroute_review_not_ready")
    reasons.extend(
        "public_quote_" + reason
        for reason in _authority_contamination_reasons(
            public_quote,
            allowed_true_keys=PUBLIC_QUOTE_ALLOWED_TRUE_KEYS,
        )
    )
    reasons.extend(
        "reroute_review_" + reason
        for reason in _authority_contamination_reasons(reroute_review)
    )
    if _identity_key(_quote_candidate(public_quote)) != _identity_key(
        _reroute_candidate(reroute_review)
    ):
        reasons.append("candidate_identity_mismatch")
    reviewed_cap_usdt = _float(_reroute_selected_candidate(reroute_review).get("current_cap_usdt"))
    if reviewed_cap_usdt is None or reviewed_cap_usdt <= 0:
        reasons.append("reroute_candidate_current_cap_invalid")
    elif cap_usdt is not None and not _floats_equal(cap_usdt, reviewed_cap_usdt):
        reasons.append("cap_usdt_mismatch_reviewed_candidate_cap")

    answers = _dict(public_quote.get("answers"))
    if answers.get("bybit_public_market_data_call_performed") is not True:
        reasons.append("public_market_data_call_not_recorded")
    if answers.get("bybit_private_call_performed") is not False:
        reasons.append("private_bybit_call_not_false")
    if answers.get("auth_headers_present") is not False:
        reasons.append("auth_headers_not_false")
    if answers.get("order_submission_performed") is not False:
        reasons.append("order_submission_not_false")
    if answers.get("pg_write_performed") is not False:
        reasons.append("pg_write_not_false")
    if answers.get("main_cost_gate_adjustment") != "NONE":
        reasons.append("cost_gate_adjustment_not_none")
    if not _answers_false_or_none(
        answers,
        [
            "probe_authority_granted",
            "order_authority_granted",
            "live_authority_granted",
            "promotion_evidence",
            "runtime_mutation_performed",
            "runtime_env_mutation_performed",
            "service_restart_performed",
            "crontab_mutation_performed",
            "config_mutation_performed",
            "risk_mutation_performed",
        ],
    ):
        reasons.append("authority_or_mutation_answer_not_false")

    parsed = _dict(public_quote.get("parsed"))
    ticker = _dict(parsed.get("ticker"))
    instrument = _dict(parsed.get("instrument"))
    freshness = _dict(_dict(public_quote.get("derived")).get("freshness"))
    if freshness.get("bbo_fresh") is not True:
        reasons.append("public_quote_bbo_not_fresh")
    freshness_gate = _float(freshness.get("max_fresh_bbo_age_ms"))
    if freshness_gate is None or freshness_gate <= 0:
        reasons.append("public_quote_freshness_gate_missing_or_invalid")
    elif freshness_gate > CANONICAL_MAX_FRESH_BBO_AGE_MS:
        reasons.append("public_quote_freshness_gate_wider_than_canonical")
    elif max_fresh_bbo_age_ms is not None and not _floats_equal(
        max_fresh_bbo_age_ms,
        freshness_gate,
    ):
        reasons.append("max_fresh_bbo_age_ms_mismatch_public_quote_gate")
    if not _is_sha256_hex(public_quote.get("artifact_self_hash_sha256")):
        reasons.append("public_quote_self_hash_missing_or_invalid")
    if len(_list(public_quote.get("requests"))) <= 0:
        reasons.append("public_quote_request_count_missing")
    ticker_ts = _parse_dt(ticker.get("bybit_response_time_utc"))
    if ticker_ts is None:
        reasons.append("ticker_response_time_missing")
    else:
        age_ms = (generated_at_utc.astimezone(dt.timezone.utc) - ticker_ts).total_seconds() * 1000.0
        effective_max_fresh_bbo_age_ms = (
            max_fresh_bbo_age_ms
            if max_fresh_bbo_age_ms is not None
            else freshness_gate
        )
        if age_ms < 0:
            reasons.append("ticker_response_time_future")
        elif (
            effective_max_fresh_bbo_age_ms is not None
            and age_ms > effective_max_fresh_bbo_age_ms
        ):
            reasons.append("public_quote_stale_at_adapter_generation")
    if _str(instrument.get("status")) != "Trading":
        reasons.append("instrument_not_trading")
    candidate = _quote_candidate(public_quote)
    if ticker.get("symbol") != candidate.get("symbol"):
        reasons.append("ticker_symbol_mismatch")
    if instrument.get("symbol") != candidate.get("symbol"):
        reasons.append("instrument_symbol_mismatch")
    if instrument.get("category") != "linear":
        reasons.append("instrument_category_not_linear")
    bid = _float(ticker.get("bid1Price"))
    ask = _float(ticker.get("ask1Price"))
    bid_size = _float(ticker.get("bid1Size"))
    ask_size = _float(ticker.get("ask1Size"))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid >= ask:
        reasons.append("invalid_public_quote_bbo")
    if bid_size is None or ask_size is None or bid_size <= 0 or ask_size <= 0:
        reasons.append("invalid_public_quote_bbo_size")
    for key in ("tick_size", "qty_step", "min_notional"):
        value = _float(instrument.get(key))
        if value is None or value <= 0:
            reasons.append(f"instrument_{key}_invalid")
    for key in ("bid1Price", "ask1Price", "symbol", "bybit_response_time_utc"):
        if key not in ticker or _str(ticker.get(key)) == "":
            reasons.append(f"ticker_{key}_missing")
    for key in ("tick_size", "qty_step", "min_notional", "symbol", "category"):
        if key not in instrument or _str(instrument.get(key)) == "":
            reasons.append(f"instrument_{key}_missing")
    return sorted(set(reasons))


def build_market_snapshot_from_public_quote(
    *,
    public_quote: dict[str, Any],
    reroute_review: dict[str, Any],
    public_quote_path: Path | None = None,
    reroute_review_path: Path | None = None,
    generated_at_utc: dt.datetime | None = None,
    cap_usdt: float | None = None,
    max_fresh_bbo_age_ms: int | None = None,
) -> dict[str, Any]:
    now = (generated_at_utc or _utc_now()).astimezone(dt.timezone.utc)
    reasons = _validate_inputs(
        public_quote=public_quote,
        reroute_review=reroute_review,
        public_quote_path=public_quote_path,
        reroute_review_path=reroute_review_path,
        generated_at_utc=now,
        cap_usdt=cap_usdt,
        max_fresh_bbo_age_ms=max_fresh_bbo_age_ms,
    )
    if reasons:
        raise ValueError("public quote cannot be adapted: " + ",".join(reasons))

    candidate = _quote_candidate(public_quote)
    reviewed_cap_usdt = _float(_reroute_selected_candidate(reroute_review).get("current_cap_usdt"))
    parsed = _dict(public_quote.get("parsed"))
    quote_ticker = _dict(parsed.get("ticker"))
    quote_instrument = _dict(parsed.get("instrument"))
    freshness = _dict(_dict(public_quote.get("derived")).get("freshness"))
    source_max_fresh_bbo_age_ms = _float(freshness.get("max_fresh_bbo_age_ms"))
    best_bid = _float(quote_ticker.get("bid1Price"))
    best_ask = _float(quote_ticker.get("ask1Price"))
    ticker_ts = _parse_dt(quote_ticker.get("bybit_response_time_utc"))
    instrument_ts = _parse_dt(quote_instrument.get("bybit_response_time_utc"))
    ticker = {
        "ts": ticker_ts.isoformat() if ticker_ts else quote_ticker.get("bybit_response_time_utc"),
        "symbol": quote_ticker.get("symbol"),
        "last_price": _float(quote_ticker.get("lastPrice")),
        "mark_price": _float(quote_ticker.get("markPrice")),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_bps": _float(quote_ticker.get("spread_bps")),
        "bid_size": _float(quote_ticker.get("bid1Size")),
        "ask_size": _float(quote_ticker.get("ask1Size")),
    }
    instrument = {
        "ts": instrument_ts.isoformat()
        if instrument_ts
        else quote_instrument.get("bybit_response_time_utc"),
        "category": quote_instrument.get("category"),
        "symbol": quote_instrument.get("symbol"),
        "status": quote_instrument.get("status"),
        "tick_size": _float(quote_instrument.get("tick_size")),
        "qty_step": _float(quote_instrument.get("qty_step")),
        "min_notional": _float(quote_instrument.get("min_notional")),
    }
    return {
        "schema_version": MARKET_SNAPSHOT_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "source": PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE,
        "candidate": candidate,
        "risk_limits": {
            "cap_usdt": reviewed_cap_usdt,
            "max_fresh_bbo_age_ms": source_max_fresh_bbo_age_ms,
        },
        "ticker": ticker,
        "instrument": instrument,
        "derived": {
            "bbo_age_ms": _round(freshness.get("effective_bbo_age_ms"), 3),
            "instrument_status": instrument.get("status"),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": _round((best_bid + best_ask) / 2.0, 8)
            if best_bid is not None and best_ask is not None
            else None,
            "spread_bps": _float(quote_ticker.get("spread_bps")),
            "tick_size": instrument.get("tick_size"),
            "qty_step": instrument.get("qty_step"),
            "min_notional": instrument.get("min_notional"),
        },
        "adapter": {
            "status": PUBLIC_QUOTE_ADAPTER_STATUS,
            "source_schema_version": PUBLIC_QUOTE_SCHEMA_VERSION,
            "generated_at_utc": now.isoformat(),
            "public_quote_path": str(public_quote_path) if public_quote_path else None,
            "public_quote_sha256": _sha256(public_quote_path),
            "reroute_review_path": str(reroute_review_path) if reroute_review_path else None,
            "reroute_review_sha256": _sha256(reroute_review_path),
            "reviewed_cap_usdt": reviewed_cap_usdt,
            "source_max_fresh_bbo_age_ms": source_max_fresh_bbo_age_ms,
        },
        "public_quote_artifact": {
            "path": str(public_quote_path) if public_quote_path else None,
            "sha256": _sha256(public_quote_path),
            "schema_version": public_quote.get("schema_version"),
            "status": public_quote.get("status"),
            "artifact_self_hash_sha256": public_quote.get("artifact_self_hash_sha256"),
            "request_count": len(_list(public_quote.get("requests"))),
            "bybit_public_market_data_call_performed": True,
            "source_max_fresh_bbo_age_ms": source_max_fresh_bbo_age_ms,
        },
        "reroute_review_artifact": {
            "path": str(reroute_review_path) if reroute_review_path else None,
            "sha256": _sha256(reroute_review_path),
            "schema_version": reroute_review.get("schema_version"),
            "status": reroute_review.get("status"),
            "selected_candidate_current_cap_usdt": reviewed_cap_usdt,
        },
        "answers": {
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "bybit_public_market_data_call_reused_from_artifact": True,
            "bybit_private_call_performed": False,
            "auth_headers_present": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
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
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    ticker = _dict(packet.get("ticker"))
    instrument = _dict(packet.get("instrument"))
    lines = [
        "# Public Quote Market Snapshot Adapter",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Source: `{packet.get('source')}`",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Bid/ask: `{ticker.get('best_bid')}` / `{ticker.get('best_ask')}`",
        f"- Instrument status: `{instrument.get('status')}`",
        f"- Public quote artifact: `{_dict(packet.get('public_quote_artifact')).get('path')}`",
        f"- Boundary: {packet.get('boundary')}",
    ]
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
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
    parser.add_argument("--public-quote-json", type=Path, required=True)
    parser.add_argument("--reroute-review-json", type=Path, required=True)
    parser.add_argument("--cap-usdt", type=float)
    parser.add_argument("--max-fresh-bbo-age-ms", type=int)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_market_snapshot_from_public_quote(
        public_quote=_read_json(args.public_quote_json),
        reroute_review=_read_json(args.reroute_review_json),
        public_quote_path=args.public_quote_json,
        reroute_review_path=args.reroute_review_json,
        cap_usdt=args.cap_usdt,
        max_fresh_bbo_age_ms=args.max_fresh_bbo_age_ms,
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

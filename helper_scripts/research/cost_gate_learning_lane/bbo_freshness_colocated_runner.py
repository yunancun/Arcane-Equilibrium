#!/usr/bin/env python3
"""Run a co-located read-only market snapshot plus construction preview.

This source-only helper is a latency-reduction design for bounded Demo probe
BBO freshness. It can combine a read-only PG ticker/instrument snapshot and the
candidate construction preview in one process so the preview timestamp is close
to the market-data read. It never writes PG, calls Bybit, submits orders, grants
authority, lowers the Cost Gate, or mutates runtime state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.bounded_probe_candidate_construction_preview import (
    BBO_STALE_STATUS,
    CONSTRUCTION_PREVIEW_SCHEMA_VERSION,
    READY_STATUS as PREVIEW_READY_STATUS,
    build_candidate_construction_preview,
    render_markdown as render_preview_markdown,
)


COLOCATED_RUNNER_SCHEMA_VERSION = (
    "bounded_probe_bbo_freshness_colocated_runner_v1"
)
REPAIR_PROPOSAL_SCHEMA_VERSION = "bounded_probe_bbo_freshness_repair_proposal_v1"
REPAIR_PROPOSAL_READY_STATUS = "BBO_FRESHNESS_REPAIR_PROPOSAL_READY_NO_AUTHORITY"
MARKET_SNAPSHOT_SCHEMA_VERSION = "bounded_probe_candidate_market_snapshot_v1"
EXPECTED_SOURCE = "read_only_pg:market.market_tickers+market.symbol_universe_snapshots"

READY_STATUS = "COLOCATED_RUNNER_READY_NO_ORDER"
SUPPLIED_SMOKE_READY_STATUS = "SUPPLIED_MARKET_PREVIEW_READY_NO_PG_SMOKE"
BBO_STALE_RUNNER_STATUS = "COLOCATED_RUNNER_BBO_STALE_NO_ORDER"
PREVIEW_NOT_READY_STATUS = "COLOCATED_RUNNER_PREVIEW_NOT_READY_NO_ORDER"
INPUT_REQUIRED_STATUS = "COLOCATED_RUNNER_INPUT_REQUIRED"
AUTHORITY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

BOUNDARY = (
    "source-only co-located read-only PG snapshot plus construction preview; no "
    "PG write, Bybit call, order, config, risk, auth, runtime mutation, global "
    "Cost Gate lowering, probe authority, order authority, live/mainnet "
    "authority, ledger append, or promotion proof"
)

DANGER_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "canonical_plan_mutation_performed",
    "config_mutation_performed",
    "cost_gate_lowering_recommended",
    "cost_gate_mutation_found",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "environment_mutation_performed",
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
    "execution_authority",
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


def _clean_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc).isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(k): _clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_json(v) for v in value]
    return value


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


def _sha(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    nodes = [value]
    if isinstance(value, dict):
        for child in value.values():
            nodes.extend(_iter_nodes(child))
    elif isinstance(value, list):
        for child in value:
            nodes.extend(_iter_nodes(child))
    return nodes


def _authority_preserved(
    *,
    repair_proposal: dict[str, Any] | None,
    reroute_review: dict[str, Any] | None,
    market_snapshot: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    payload_rules = [
        (repair_proposal, set()),
        (reroute_review, set()),
        (market_snapshot, {"pg_query_performed"}),
    ]
    for payload, allowed_true_keys in payload_rules:
        for node in _iter_nodes(_dict(payload)):
            if not isinstance(node, dict):
                continue
            for key, value in node.items():
                if (
                    key in DANGER_KEYS
                    and key not in allowed_true_keys
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


def _candidate_from_reroute(reroute_review: dict[str, Any] | None) -> dict[str, Any]:
    candidate = _dict(_dict(reroute_review).get("selected_candidate"))
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _repair_proposal_ready(repair_proposal: dict[str, Any] | None) -> tuple[bool, list[str]]:
    payload = _dict(repair_proposal)
    reasons: list[str] = []
    if payload.get("schema_version") != REPAIR_PROPOSAL_SCHEMA_VERSION:
        reasons.append("repair_proposal_schema_mismatch")
    if payload.get("status") != REPAIR_PROPOSAL_READY_STATUS:
        reasons.append("repair_proposal_not_ready")
    options = [_dict(item) for item in _list(payload.get("repair_options"))]
    rank1 = next((item for item in options if item.get("rank") == 1), {})
    if rank1.get("option_id") != "co_located_read_only_pg_snapshot_preview_runner":
        reasons.append("rank1_co_located_runner_option_missing")
    if _str(rank1.get("status")) != "RECOMMENDED_SOURCE_ONLY_DESIGN":
        reasons.append("rank1_co_located_runner_not_source_only_recommended")
    return not reasons, reasons


def build_market_snapshot_from_rows(
    *,
    candidate: dict[str, Any],
    ticker: dict[str, Any],
    instrument: dict[str, Any],
    pg_snapshot_timestamp: dt.datetime,
    generated_at_utc: dt.datetime,
    cap_usdt: float,
    max_fresh_bbo_age_ms: int = 1000,
) -> dict[str, Any]:
    ticker_ts = _parse_dt(ticker.get("ts"))
    instrument_ts = _parse_dt(instrument.get("ts"))
    pg_now = pg_snapshot_timestamp.astimezone(dt.timezone.utc)
    bbo_age_ms = (
        (pg_now - ticker_ts).total_seconds() * 1000.0 if ticker_ts else None
    )
    instrument_age_seconds = (
        (pg_now - instrument_ts).total_seconds() if instrument_ts else None
    )
    best_bid = _float(ticker.get("best_bid"))
    best_ask = _float(ticker.get("best_ask"))
    return {
        "schema_version": MARKET_SNAPSHOT_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc.astimezone(dt.timezone.utc).isoformat(),
        "pg_snapshot_timestamp": pg_now.isoformat(),
        "source": EXPECTED_SOURCE,
        "candidate": candidate,
        "risk_limits": {
            "cap_usdt": cap_usdt,
            "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
        },
        "ticker": _clean_json(ticker),
        "instrument": _clean_json(instrument),
        "derived": {
            "bbo_age_ms": _round(bbo_age_ms, 3),
            "instrument_age_seconds": _round(instrument_age_seconds, 3),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": _round((best_bid + best_ask) / 2.0, 8)
            if best_bid is not None and best_ask is not None
            else None,
            "spread_bps": _float(ticker.get("spread_bps")),
            "tick_size": _float(instrument.get("tick_size")),
            "qty_step": _float(instrument.get("qty_step")),
            "min_notional": _float(instrument.get("min_notional")),
            "instrument_status": instrument.get("status"),
        },
        "answers": {
            "pg_query_performed": True,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
        },
    }


def _load_runtime_pg_env() -> None:
    if os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL"):
        return
    secrets_root = Path(
        os.environ.get("OPENCLAW_SECRETS_ROOT")
        or Path.home() / "BybitOpenClaw" / "secrets"
    )
    env_path = secrets_root / "environment_files" / "basic_system_services.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        if item.startswith("export "):
            item = item[len("export "):]
        key, value = item.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def load_pg_market_snapshot(
    *,
    candidate: dict[str, Any],
    cap_usdt: float,
    max_fresh_bbo_age_ms: int = 1000,
) -> dict[str, Any]:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor  # type: ignore

    _load_runtime_pg_env()
    dsn = os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")
    kwargs: dict[str, Any] = {}
    if not dsn:
        kwargs = {
            "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "port": os.environ.get("POSTGRES_PORT", "5432"),
            "dbname": os.environ.get("POSTGRES_DB"),
            "user": os.environ.get("POSTGRES_USER"),
        }
        if os.environ.get("POSTGRES_PASSWORD"):
            kwargs["password"] = os.environ["POSTGRES_PASSWORD"]
    conn = psycopg2.connect(
        dsn or None,
        **kwargs,
        application_name="openclaw_bbo_freshness_colocated_runner_ro",
    )
    conn.set_session(readonly=True, autocommit=True)
    symbol = _str(candidate.get("symbol"))
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("select now() as pg_now")
        pg_now = cur.fetchone()["pg_now"].astimezone(dt.timezone.utc)
        cur.execute(
            """
            select ts, symbol, last_price, mark_price, index_price, best_bid,
                   best_ask, bid_size, ask_size, spread_bps, funding_rate
            from market.market_tickers
            where symbol=%s
              and best_bid is not null and best_ask is not null
              and best_bid > 0 and best_ask > 0
            order by ts desc
            limit 1
            """,
            (symbol,),
        )
        ticker = cur.fetchone()
        cur.execute(
            """
            select ts, exchange, category, symbol, status, base_coin, quote_coin,
                   contract_type, tick_size, qty_step, min_notional, source_uri,
                   encode(payload_hash,'hex') as payload_hash_hex
            from market.symbol_universe_snapshots
            where symbol=%s and category='linear'
            order by ts desc
            limit 1
            """,
            (symbol,),
        )
        instrument = cur.fetchone()
    if ticker is None or instrument is None:
        raise RuntimeError(f"missing ticker or instrument row for {symbol}")
    return build_market_snapshot_from_rows(
        candidate=candidate,
        ticker=dict(ticker),
        instrument=dict(instrument),
        pg_snapshot_timestamp=pg_now,
        generated_at_utc=_utc_now(),
        cap_usdt=cap_usdt,
        max_fresh_bbo_age_ms=max_fresh_bbo_age_ms,
    )


def build_colocated_runner_packet(
    *,
    repair_proposal: dict[str, Any] | None,
    reroute_review: dict[str, Any] | None,
    market_snapshot: dict[str, Any] | None,
    pg_readonly_mode: bool = False,
    demo_operational_authorization_available: bool = False,
    now_utc: dt.datetime | None = None,
    artifact_paths: dict[str, Path | None] | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = artifact_paths or {}
    authority_preserved, contamination_reasons = _authority_preserved(
        repair_proposal=repair_proposal,
        reroute_review=reroute_review,
        market_snapshot=market_snapshot,
    )
    repair_ready, repair_reasons = _repair_proposal_ready(repair_proposal)
    candidate = _candidate_from_reroute(reroute_review)
    preview = build_candidate_construction_preview(
        reroute_review=reroute_review,
        market_snapshot=market_snapshot,
        demo_operational_authorization_available=demo_operational_authorization_available,
        now_utc=now,
        artifact_paths={
            "reroute_review": paths.get("reroute_review"),
            "market_snapshot": paths.get("market_snapshot"),
        },
    )
    preview_status = preview.get("status")
    blocking_gates = list(repair_reasons)
    blocking_gates.extend(_list(preview.get("blocking_gates")))
    if not authority_preserved:
        status = AUTHORITY_VIOLATION_STATUS
        reason = "input_artifacts_contain_authority_or_mutation_contamination"
    elif not repair_ready:
        status = INPUT_REQUIRED_STATUS
        reason = "ready_co_located_repair_proposal_required"
    elif preview_status == PREVIEW_READY_STATUS and pg_readonly_mode is True:
        status = READY_STATUS
        reason = "co_located_snapshot_preview_is_fresh_and_constructible_no_order"
    elif preview_status == PREVIEW_READY_STATUS:
        status = SUPPLIED_SMOKE_READY_STATUS
        reason = "supplied_market_snapshot_preview_is_ready_but_does_not_close_co_located_pg_gate"
    elif preview_status == BBO_STALE_STATUS:
        status = BBO_STALE_RUNNER_STATUS
        reason = "co_located_snapshot_preview_still_failed_bbo_freshness"
    else:
        status = PREVIEW_NOT_READY_STATUS
        reason = "co_located_snapshot_preview_not_ready"
    return {
        "schema_version": COLOCATED_RUNNER_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": candidate,
        "mode": "pg_readonly" if pg_readonly_mode else "supplied_market_snapshot",
        "source_artifacts": {
            "repair_proposal": {
                "path": str(paths.get("repair_proposal"))
                if paths.get("repair_proposal")
                else None,
                "sha256": _sha(paths.get("repair_proposal")),
                "status": _dict(repair_proposal).get("status"),
            },
            "reroute_review": {
                "path": str(paths.get("reroute_review"))
                if paths.get("reroute_review")
                else None,
                "sha256": _sha(paths.get("reroute_review")),
                "status": _dict(reroute_review).get("status"),
            },
            "market_snapshot": {
                "path": str(paths.get("market_snapshot"))
                if paths.get("market_snapshot")
                else None,
                "sha256": _sha(paths.get("market_snapshot")),
                "schema_version": _dict(market_snapshot).get("schema_version"),
            },
        },
        "repair_proposal_ready": repair_ready,
        "repair_proposal_blocking_reasons": repair_reasons,
        "market_snapshot": market_snapshot,
        "construction_preview": preview,
        "latency_reduction_design": {
            "design": "query PG read-only and build construction preview in one process",
            "does_not_change_freshness_gate": True,
            "does_not_lower_cost_gate": True,
            "does_not_grant_order_or_probe_authority": True,
            "runtime_sync_required_before_pg_mode_on_trade_core": True,
            "direct_public_quote_capture_required": False,
        },
        "blocking_gates": sorted(set(blocking_gates)),
        "blocking_gate_count": len(set(blocking_gates)),
        "answers": {
            "pg_query_performed": pg_readonly_mode is True,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
        },
        "authority_preserved": authority_preserved,
        "authority_contamination_reasons": contamination_reasons,
        "boundary": BOUNDARY,
        "next_blocker_id": (
            "P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY"
            if status != READY_STATUS
            else "P0-BOUNDED-PROBE-REROUTE-DEMO-ORDER-ADMISSION-REVIEW"
        ),
    }


def render_markdown(packet: dict[str, Any]) -> str:
    preview = _dict(packet.get("construction_preview"))
    inputs = _dict(preview.get("market_inputs"))
    lines = [
        "# BBO Freshness Co-Located Runner",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Mode: `{packet.get('mode')}`",
        f"- Preview status: `{preview.get('status')}`",
        f"- Effective BBO age ms: `{inputs.get('effective_bbo_age_ms')}`",
        f"- Blocking gates: `{packet.get('blocking_gates')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Construction Preview",
        "",
        render_preview_markdown(preview),
    ]
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
    parser.add_argument("--repair-proposal-json", type=Path, required=True)
    parser.add_argument("--reroute-review-json", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--market-snapshot-json", type=Path)
    mode.add_argument("--pg-readonly", action="store_true")
    parser.add_argument(
        "--cap-usdt",
        type=float,
        help=(
            "Resolved GUI/Rust RiskConfig per-order cap in USDT. Required with "
            "--pg-readonly; this helper no longer injects a 10 USDT default."
        ),
    )
    parser.add_argument("--max-fresh-bbo-age-ms", type=int, default=1000)
    parser.add_argument("--demo-operational-authorization-available", action="store_true")
    parser.add_argument("--market-snapshot-output", type=Path)
    parser.add_argument("--preview-json-output", type=Path)
    parser.add_argument("--preview-output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.pg_readonly and args.market_snapshot_output is None:
        raise SystemExit("--market-snapshot-output is required with --pg-readonly")
    if args.pg_readonly and args.cap_usdt is None:
        raise SystemExit(
            "--cap-usdt resolved from GUI/Rust RiskConfig is required with --pg-readonly"
        )
    if args.cap_usdt is not None and args.cap_usdt <= 0:
        raise SystemExit("--cap-usdt must be positive when supplied")
    repair_proposal = _read_json(args.repair_proposal_json)
    reroute_review = _read_json(args.reroute_review_json)
    candidate = _candidate_from_reroute(reroute_review)
    if args.pg_readonly:
        market_snapshot = load_pg_market_snapshot(
            candidate=candidate,
            cap_usdt=args.cap_usdt,
            max_fresh_bbo_age_ms=args.max_fresh_bbo_age_ms,
        )
        market_path = args.market_snapshot_output
        if market_path:
            _write_json(market_path, market_snapshot)
    else:
        market_snapshot = _read_json(args.market_snapshot_json)
        market_path = args.market_snapshot_json
    packet = build_colocated_runner_packet(
        repair_proposal=repair_proposal,
        reroute_review=reroute_review,
        market_snapshot=market_snapshot,
        pg_readonly_mode=args.pg_readonly,
        demo_operational_authorization_available=(
            args.demo_operational_authorization_available
        ),
        artifact_paths={
            "repair_proposal": args.repair_proposal_json,
            "reroute_review": args.reroute_review_json,
            "market_snapshot": market_path,
        },
    )
    if args.preview_json_output:
        _write_json(args.preview_json_output, _dict(packet.get("construction_preview")))
    if args.preview_output:
        _write_text(args.preview_output, render_preview_markdown(_dict(packet.get("construction_preview"))))
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

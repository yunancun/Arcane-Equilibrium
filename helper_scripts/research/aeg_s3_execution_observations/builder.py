"""Build AEG-S3 execution observation JSONL rows from event capture artifacts."""

from __future__ import annotations

import datetime as dt
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from aeg_s3_event_breadth.builder import (
    UnsupportedCandidateEvidence,
    normalize_event_samples,
)

from . import OBSERVATION_SCHEMA_VERSION, RUNNER_VERSION, SUMMARY_SCHEMA_VERSION

SUPPORTED_GATE_B_CANDIDATES = frozenset({"listing_fade"})


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            s = line.strip()
            if not s:
                continue
            obj = json.loads(s)
            if not isinstance(obj, dict):
                raise ValueError(f"invalid_jsonl_row:{path}:{line_no}")
            rows.append(obj)
    return rows


def load_gate_b_run(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    run_dir = Path(run_dir)
    return {
        "capture_lag": load_jsonl(run_dir / "capture_lag.jsonl") if (run_dir / "capture_lag.jsonl").exists() else [],
        "markout": load_jsonl(run_dir / "markout.jsonl") if (run_dir / "markout.jsonl").exists() else [],
        "publictrade": (
            load_jsonl(run_dir / "ws_publictrade.jsonl")
            if (run_dir / "ws_publictrade.jsonl").exists()
            else []
        ),
    }


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _int_or_none(value: Any) -> Optional[int]:
    f = _float_or_none(value)
    return int(f) if f is not None else None


def _parse_ts(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _ms_from_ts(value: Any) -> Optional[int]:
    parsed = _parse_ts(value)
    if parsed is None:
        return None
    return int(parsed.timestamp() * 1000)


def _capture_by_symbol_ts(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        ts_ms = _int_or_none(row.get("first_trade_event_ts_ms") or row.get("event_ts_exchange_ms"))
        if not symbol or ts_ms is None:
            continue
        key = (symbol, ts_ms)
        current = out.get(key)
        current_ingest = _int_or_none((current or {}).get("first_trade_ingest_ts_local_ms"))
        ingest = _int_or_none(row.get("first_trade_ingest_ts_local_ms"))
        if current is None or (ingest is not None and (current_ingest is None or ingest < current_ingest)):
            out[key] = row
    return out


def _trades_by_symbol(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        ts_ms = _int_or_none(row.get("event_ts_exchange_ms"))
        if not symbol or ts_ms is None:
            continue
        out[symbol].append(row)
    for symbol in list(out):
        out[symbol].sort(key=lambda r: _int_or_none(r.get("event_ts_exchange_ms")) or 0)
    return out


def _markout_trigger_by_symbol_ts(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        if row.get("kind") != "markout_trigger":
            continue
        symbol = str(row.get("symbol") or "").strip()
        ts_ms = _int_or_none(row.get("trigger_event_ts_ms"))
        if symbol and ts_ms is not None:
            out[(symbol, ts_ms)] = row
    return out


def _accepted_capture(row: Optional[dict[str, Any]], *, allow_slow_capture: bool) -> tuple[bool, str]:
    if row is None:
        return False, "missing_capture_lag"
    verdict = str(row.get("verdict") or row.get("capture_verdict") or "").strip()
    if verdict == "PASS_CAPTURE":
        return True, ""
    if allow_slow_capture and verdict == "SLOW_CAPTURE":
        return True, ""
    return False, f"capture_verdict_not_allowed:{verdict or 'missing'}"


def _trade_notional(row: dict[str, Any]) -> Optional[float]:
    price = _float_or_none(row.get("price"))
    size = _float_or_none(row.get("size"))
    if price is None or size is None:
        return None
    return abs(price * size)


def _window_notional(trades: list[dict[str, Any]], *, start_ms: int, window_s: int) -> Optional[float]:
    end_ms = start_ms + window_s * 1000
    total = 0.0
    seen = False
    for row in trades:
        ts_ms = _int_or_none(row.get("event_ts_exchange_ms"))
        if ts_ms is None or ts_ms < start_ms or ts_ms > end_ms:
            continue
        notional = _trade_notional(row)
        if notional is None:
            continue
        total += notional
        seen = True
    return total if seen else None


def _first_trade_at_or_after(trades: list[dict[str, Any]], ts_ms: int) -> Optional[dict[str, Any]]:
    return next(
        (
            row for row in trades
            if (_int_or_none(row.get("event_ts_exchange_ms")) or -1) >= ts_ms
        ),
        None,
    )


def _raw_sample_index(candidate_evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in candidate_evidence.get("samples") or []:
        if not isinstance(raw, dict):
            continue
        sample_id = str(raw.get("sample_id") or "").strip()
        if sample_id:
            out[sample_id] = raw
    return out


def build_gate_b_observations(
    *,
    candidate_evidence: dict[str, Any],
    gate_b_payload: dict[str, list[dict[str, Any]]],
    source_path: str,
    maker_fee_bps: float,
    taker_fee_bps: float,
    order_notional_usdt: float,
    evidence_source_tier: str = "calibrated_replay",
    order_style: str = "taker",
    slippage_floor_bps: float = 0.0,
    capacity_window_s: int = 60,
    allow_slow_capture: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert Gate-B public-trade captures into event execution observations.

    The rows are intended for ``aeg_s3_event_execution_realism``. They are
    deliberately tied to candidate sample_id so unmatched historical samples do
    not silently become execution evidence.
    """
    candidate_id = str(candidate_evidence.get("candidate_id") or "").strip()
    if candidate_id not in SUPPORTED_GATE_B_CANDIDATES:
        raise UnsupportedCandidateEvidence(
            f"unsupported_candidate_for_gate_b_execution_observations:{candidate_id or 'missing'}"
        )
    if maker_fee_bps < 0 or taker_fee_bps < 0:
        raise ValueError("fee_bps_must_be_non_negative")
    if taker_fee_bps < maker_fee_bps:
        raise ValueError("taker_fee_bps_below_maker_fee_bps")
    if order_notional_usdt <= 0:
        raise ValueError("order_notional_usdt_must_be_positive")
    if slippage_floor_bps < 0:
        raise ValueError("slippage_floor_bps_must_be_non_negative")
    if capacity_window_s <= 0:
        raise ValueError("capacity_window_s_must_be_positive")

    samples, rejected_samples = normalize_event_samples(candidate_evidence)
    raw_by_id = _raw_sample_index(candidate_evidence)
    captures = _capture_by_symbol_ts(gate_b_payload.get("capture_lag", []))
    trades_by_symbol = _trades_by_symbol(gate_b_payload.get("publictrade", []))
    markout_triggers = _markout_trigger_by_symbol_ts(gate_b_payload.get("markout", []))

    observations: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    parameter_cell_id = str(candidate_evidence.get("parameter_cell_id") or "").strip() or None

    for sample in samples:
        ts_ms = int(sample.sample_ts.timestamp() * 1000)
        key = (sample.symbol, ts_ms)
        capture = captures.get(key)
        ok, reason = _accepted_capture(capture, allow_slow_capture=allow_slow_capture)
        if not ok:
            rejects.append({"sample_id": sample.sample_id, "symbol": sample.symbol, "reason": reason})
            continue

        trades = trades_by_symbol.get(sample.symbol, [])
        first_trade = _first_trade_at_or_after(trades, ts_ms)
        if first_trade is None:
            rejects.append({"sample_id": sample.sample_id, "symbol": sample.symbol, "reason": "missing_public_trade"})
            continue

        first_price = _float_or_none(first_trade.get("price"))
        raw_sample = raw_by_id.get(sample.sample_id) or {}
        entry_price = _float_or_none(raw_sample.get("entry_price"))
        trigger = markout_triggers.get(key)
        if entry_price is None and trigger is not None:
            entry_price = _float_or_none(trigger.get("mid_at_trigger"))
        if first_price is None or first_price <= 0 or entry_price is None or entry_price <= 0:
            rejects.append({"sample_id": sample.sample_id, "symbol": sample.symbol, "reason": "missing_entry_or_trade_price"})
            continue

        capacity = _window_notional(trades, start_ms=ts_ms, window_s=capacity_window_s)
        if capacity is None or capacity <= 0:
            rejects.append({"sample_id": sample.sample_id, "symbol": sample.symbol, "reason": "missing_capacity_window_notional"})
            continue

        first_trade_ts = _int_or_none(first_trade.get("event_ts_exchange_ms"))
        first_ingest = _int_or_none(first_trade.get("ingest_ts_local_ms"))
        capture_ingest = _int_or_none(capture.get("first_trade_ingest_ts_local_ms")) if capture else None
        latency = None
        if first_trade_ts is not None and first_ingest is not None:
            latency = max(0.0, float(first_ingest - first_trade_ts))
        elif first_trade_ts is not None and capture_ingest is not None:
            latency = max(0.0, float(capture_ingest - first_trade_ts))
        else:
            latency = _float_or_none(first_trade.get("ingest_minus_event_ms"))

        slippage = abs(first_price - entry_price) / entry_price * 10_000.0
        slippage = max(slippage, slippage_floor_bps)
        observation = {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "runner_version": RUNNER_VERSION,
            "sample_id": sample.sample_id,
            "sample_ts_utc": sample.sample_ts.isoformat(),
            "symbol": sample.symbol,
            "candidate_id": candidate_id,
            "strategy_family": candidate_evidence.get("strategy_family"),
            "parameter_cell_id": parameter_cell_id,
            "evidence_source_tier": evidence_source_tier,
            "order_style": order_style,
            "maker_fee_bps": maker_fee_bps,
            "taker_fee_bps": taker_fee_bps,
            "slippage_bps": round(slippage, 8),
            "latency_ms": latency,
            "participation_rate": order_notional_usdt / capacity,
            "capacity_notional_usdt": capacity,
            "order_availability_status": "PASS",
            "source": {
                "source_type": "gate_b_run",
                "source_path": source_path,
                "capture_verdict": capture.get("verdict") if capture else None,
                "order_notional_usdt": order_notional_usdt,
                "capacity_window_s": capacity_window_s,
                "slippage_floor_bps": slippage_floor_bps,
                "trade_print_replay_limit": "publicTrade prints only; no historical orderbook depth",
            },
        }
        observations.append(observation)

    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "candidate_id": candidate_id,
        "strategy_family": candidate_evidence.get("strategy_family"),
        "parameter_cell_id": parameter_cell_id,
        "source_type": "gate_b_run",
        "source_path": source_path,
        "candidate_sample_count": len(samples),
        "candidate_rejected_sample_count": len(rejected_samples),
        "observation_count": len(observations),
        "rejected_observation_count": len(rejects),
        "reject_reasons": dict(sorted(Counter(row["reason"] for row in rejects).items())),
        "evidence_source_tier": evidence_source_tier,
        "order_style": order_style,
        "order_notional_usdt": order_notional_usdt,
        "capacity_window_s": capacity_window_s,
        "slippage_floor_bps": slippage_floor_bps,
        "allow_slow_capture": allow_slow_capture,
        "notes": [
            "observations are matched to candidate sample_id before execution-realism aggregation",
            "Gate-B v0.1 source uses publicTrade prints and does not claim orderbook-depth fill realism",
        ],
        "rejected_observations": rejects,
    }
    return observations, summary


__all__ = [
    "SUPPORTED_GATE_B_CANDIDATES",
    "UnsupportedCandidateEvidence",
    "build_gate_b_observations",
    "load_gate_b_run",
    "load_json",
    "load_jsonl",
]


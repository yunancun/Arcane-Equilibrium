"""Runtime artifact killboard for alpha discovery throughput.

MODULE_NOTE:
  模塊用途：讀既有 runtime artifacts，產出 alpha discovery 多臂 killboard。
  硬邊界：artifact-only；不連 DB、不連 Bybit、不下單、不碰 auth/risk/runtime state。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.status import (
    summarize_cost_gate_learning_lane_historical_review,
    summarize_cost_gate_learning_lane_ledger,
    summarize_cost_gate_learning_lane_loop,
    summarize_cost_gate_learning_lane_source,
)
from polymarket_leadlag import replay_history as polymarket_replay_history

from . import RUNNER_VERSION
from .discovery_loop import build_discovery_plan

RUNTIME_KILLBOARD_SCHEMA_VERSION = "alpha_discovery_runtime_killboard_v7"
DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60
DEFAULT_DAILY_ARTIFACT_MAX_AGE_SECONDS = 36 * 60 * 60
DEFAULT_POLYMARKET_REPLAY_HISTORY_REPORT_LIMIT = 4096


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    return max(0.0, (now_utc - parsed).total_seconds())


def _int(value: Any, default: int = 0) -> int:
    try:
        out = int(float(value))
    except (TypeError, ValueError):
        return default
    return out


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"malformed:{type(exc).__name__}"
    if not isinstance(data, dict):
        return None, "not_object"
    return data, None


def _latest_json_line(
    path: Path,
    *,
    prefix: str | None = None,
    max_scan_bytes: int = 4 * 1024 * 1024,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"

    scan = min(size, 262144)
    while scan <= min(size, max_scan_bytes):
        try:
            with open(path, "rb") as fh:
                start = max(0, size - scan)
                fh.seek(start, os.SEEK_SET)
                chunk = fh.read().decode("utf-8", errors="replace")
        except OSError as exc:
            return None, f"read_error:{type(exc).__name__}"

        lines = chunk.splitlines()
        # If the chunk starts mid-line, skip that first partial line. The last
        # line can also be partial only when the writer is concurrently appending;
        # JSON decoding below naturally rejects it and older complete lines remain.
        if start > 0 and lines:
            lines = lines[1:]
        for raw_line in reversed(lines):
            line = raw_line.strip()
            if not line:
                continue
            if prefix:
                if not line.startswith(prefix):
                    continue
                line = line[len(prefix):]
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data, None
        if scan >= size or scan >= max_scan_bytes:
            break
        scan = min(size, scan * 2)
    return None, "no_json_status_line"


def _source_fresh(
    generated_at: Any,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> tuple[bool, float | None, str | None]:
    age = _age_seconds(generated_at, now_utc=now_utc)
    if age is None:
        return False, None, "missing_generated_at"
    if age > max_age_seconds:
        return False, age, "stale_artifact"
    return True, age, None


def _arm(
    *,
    arm_id: str,
    gate_status: str,
    sample_count: int,
    artifacts_ready: bool,
    source_ok: bool = True,
    source_path: Path | None = None,
    source_error: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "arm_id": arm_id,
        "gate_status": gate_status,
        "sample_count": sample_count,
        "artifacts_ready": artifacts_ready,
        "source_ok": source_ok,
        "source_path": str(source_path) if source_path else None,
        "source_error": source_error,
        "detail": detail or {},
    }


def collect_gate_b_arm(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
) -> dict[str, Any]:
    path = data_dir / "gate_b_watch" / "gate_b_watch_latest.json"
    payload, err = _read_json(path)
    if err:
        return _arm(
            arm_id="gate_b_listing_fade",
            gate_status="SOURCE_FAILURE",
            sample_count=0,
            artifacts_ready=False,
            source_ok=False,
            source_path=path,
            source_error=err,
        )
    assert payload is not None
    generated_at = payload.get("generated_at_utc") or payload.get("created_at_utc")
    fresh, age, freshness_error = _source_fresh(
        generated_at, now_utc=now_utc, max_age_seconds=max_age_seconds,
    )
    counts = payload.get("candidate_counts") if isinstance(payload.get("candidate_counts"), dict) else {}
    status = str(payload.get("artifact_status") or payload.get("status") or "NO_CANDIDATE").upper()
    actionable = _int(counts.get("alertable")) + _int(counts.get("start_now")) + _int(counts.get("schedule"))
    return _arm(
        arm_id="gate_b_listing_fade",
        gate_status=status if fresh else "SOURCE_FAILURE",
        sample_count=actionable,
        artifacts_ready=False,
        source_ok=fresh,
        source_path=path,
        source_error=freshness_error,
        detail={
            "generated_at_utc": generated_at,
            "age_seconds": age,
            "candidate_counts": counts,
            "alerts_sent": payload.get("alerts_sent"),
        },
    )


def _flash_dip_l1_short_exit_replay_detail(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    path = data_dir / "logs" / "flash_dip_l1_short_exit_replay.log"
    status, err = _latest_json_line(path)
    if err:
        return {
            "source_path": str(path),
            "source_error": err,
        }
    assert status is not None
    ts_utc = status.get("ts_utc")
    fresh, age, freshness_error = _source_fresh(
        ts_utc,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    return {
        "source_path": str(path),
        "source_ok": fresh,
        "source_error": freshness_error,
        "ts_utc": ts_utc,
        "age_seconds": age,
        "artifact_path": status.get("artifact_path"),
        "latest_path": status.get("latest_path"),
        "sha256": status.get("sha256"),
        "verdict_status": status.get("verdict_status"),
        "fail_reasons": status.get("fail_reasons"),
        "candidate_events": status.get("candidate_events"),
        "candidate_days": status.get("candidate_days"),
        "candidate_symbols": status.get("candidate_symbols"),
        "l1_rows_post_filter": status.get("l1_rows_post_filter"),
        "trade_rows": status.get("trade_rows"),
        "symbols_with_l1": status.get("symbols_with_l1"),
        "symbols_missing_l1": status.get("symbols_missing_l1"),
        "event_window_maker_timeout_minutes": status.get("event_window_maker_timeout_minutes"),
        "events_with_l1_in_event_window": status.get("events_with_l1_in_event_window"),
        "events_missing_l1_in_event_window": status.get("events_missing_l1_in_event_window"),
        "days_with_l1_in_event_window": status.get("days_with_l1_in_event_window"),
        "days_missing_l1_in_event_window": status.get("days_missing_l1_in_event_window"),
        "event_window_l1_relation_counts": status.get("event_window_l1_relation_counts"),
        "dominant_missing_event_window_l1_relation": status.get(
            "dominant_missing_event_window_l1_relation"
        ),
        "coverage_action_status": status.get("coverage_action_status"),
        "coverage_action_reason": status.get("coverage_action_reason"),
        "coverage_action_scorecard": status.get("coverage_action_scorecard"),
        "gate_exit_measured": status.get("gate_exit_measured"),
        "gate_distinct_exit_days": status.get("gate_distinct_exit_days"),
        "gate_annret": status.get("gate_annret"),
        "gate_maxdd": status.get("gate_maxdd"),
        "boundary": status.get("boundary"),
    }


def collect_flash_dip_l1_replay_arm(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_DAILY_ARTIFACT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    detail = _flash_dip_l1_short_exit_replay_detail(
        data_dir,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    path = Path(detail["source_path"])
    source_error = detail.get("source_error")
    if "source_ok" not in detail:
        return _arm(
            arm_id="flash_dip_l1_short_exit_replay",
            gate_status="CAPTURING",
            sample_count=0,
            artifacts_ready=False,
            source_ok=True,
            source_path=path,
            source_error=str(source_error) if source_error else None,
            detail={**detail, "note": "l1_replay_status_missing_or_not_yet_fired"},
        )

    sample_count = _int(detail.get("gate_exit_measured"))
    source_ok = detail.get("source_ok") is True
    verdict = str(detail.get("verdict_status") or "").upper()
    if not source_ok:
        gate_status = "SOURCE_FAILURE"
        artifacts_ready = False
    elif verdict == "L1_SHORT_EXIT_CONDITIONAL_PASS":
        gate_status = "READY"
        artifacts_ready = True
    elif verdict == "L1_SHORT_EXIT_BLOCKED":
        gate_status = "REJECTED"
        artifacts_ready = False
    else:
        gate_status = "CAPTURING"
        artifacts_ready = False
    return _arm(
        arm_id="flash_dip_l1_short_exit_replay",
        gate_status=gate_status,
        sample_count=sample_count,
        artifacts_ready=artifacts_ready,
        source_ok=source_ok,
        source_path=path,
        source_error=str(source_error) if source_error else None,
        detail=detail,
    )


def _flash_dip_l1_dependency_summary(detail: dict[str, Any]) -> dict[str, Any]:
    coverage_scorecard = (
        detail.get("coverage_action_scorecard")
        if isinstance(detail.get("coverage_action_scorecard"), dict)
        else {}
    )
    engineering_actionable = coverage_scorecard.get("engineering_actionable")
    return {
        "source_ok": detail.get("source_ok"),
        "source_error": detail.get("source_error"),
        "verdict_status": detail.get("verdict_status"),
        "candidate_events": detail.get("candidate_events"),
        "events_missing_l1_in_event_window": detail.get(
            "events_missing_l1_in_event_window"
        ),
        "dominant_missing_event_window_l1_relation": detail.get(
            "dominant_missing_event_window_l1_relation"
        ),
        "coverage_action_status": (
            detail.get("coverage_action_status") or coverage_scorecard.get("status")
        ),
        "coverage_action_reason": (
            detail.get("coverage_action_reason") or coverage_scorecard.get("reason")
        ),
        "coverage_action_next_trigger": coverage_scorecard.get("next_trigger"),
        "engineering_actionable": (
            engineering_actionable if isinstance(engineering_actionable, bool) else None
        ),
        "coverage_action_scorecard": coverage_scorecard or None,
    }


def _flash_dip_execution_realism_detail(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    path = data_dir / "logs" / "flash_dip_execution_realism.log"
    status, err = _latest_json_line(path)
    if err:
        return {
            "source_path": str(path),
            "source_error": err,
        }
    assert status is not None
    ts_utc = status.get("ts_utc")
    fresh, age, freshness_error = _source_fresh(
        ts_utc,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    return {
        "source_path": str(path),
        "source_ok": fresh,
        "source_error": freshness_error,
        "ts_utc": ts_utc,
        "age_seconds": age,
        "artifact_path": status.get("artifact_path"),
        "latest_path": status.get("latest_path"),
        "sha256": status.get("sha256"),
        "version": status.get("version"),
        "generated_utc": status.get("generated_utc"),
        "candidate_label": status.get("candidate_label"),
        "k_pct": status.get("k_pct"),
        "verdict_status": status.get("verdict_status"),
        "fail_reasons": status.get("fail_reasons"),
        "gate_buffer_bps": status.get("gate_buffer_bps"),
        "gate_filled": status.get("gate_filled"),
        "gate_distinct_days": status.get("gate_distinct_days"),
        "gate_annret": status.get("gate_annret"),
        "gate_maxdd": status.get("gate_maxdd"),
        "daily_n_raw": status.get("daily_n_raw"),
        "daily_n_kept_after_cap": status.get("daily_n_kept_after_cap"),
        "daily_n_kept_with_intraday_day": status.get("daily_n_kept_with_intraday_day"),
        "intraday_coverage_rate_vs_kept": status.get("intraday_coverage_rate_vs_kept"),
        "short_exit_status": status.get("short_exit_status"),
        "best_short_exit_buffer_bps": status.get("best_short_exit_buffer_bps"),
        "best_short_exit_horizon": status.get("best_short_exit_horizon"),
        "best_short_exit_annret": status.get("best_short_exit_annret"),
        "best_short_exit_maxdd": status.get("best_short_exit_maxdd"),
        "best_short_exit_n_filled": status.get("best_short_exit_n_filled"),
        "best_short_exit_days": status.get("best_short_exit_days"),
        "boundary": status.get("boundary"),
    }


def collect_flash_dip_execution_realism_arm(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_DAILY_ARTIFACT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    detail = _flash_dip_execution_realism_detail(
        data_dir,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    l1_replay_detail = _flash_dip_l1_short_exit_replay_detail(
        data_dir,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    detail["dependent_l1_short_exit_replay"] = _flash_dip_l1_dependency_summary(
        l1_replay_detail
    )
    path = Path(detail["source_path"])
    source_error = detail.get("source_error")
    if "source_ok" not in detail:
        return _arm(
            arm_id="flash_dip_execution_realism",
            gate_status="CAPTURING",
            sample_count=0,
            artifacts_ready=False,
            source_ok=True,
            source_path=path,
            source_error=str(source_error) if source_error else None,
            detail={**detail, "note": "execution_realism_status_missing_or_not_yet_fired"},
        )

    source_ok = detail.get("source_ok") is True
    verdict = str(detail.get("verdict_status") or "").upper()
    short_exit_status = str(detail.get("short_exit_status") or "").upper()
    sample_count = max(
        _int(detail.get("gate_filled")),
        _int(detail.get("best_short_exit_n_filled")),
    )
    if not source_ok:
        gate_status = "SOURCE_FAILURE"
        artifacts_ready = False
    elif verdict == "EXECUTION_REALISM_CONDITIONAL_PASS":
        gate_status = "READY"
        artifacts_ready = True
    elif verdict == "EXECUTION_REALISM_BLOCKED" and short_exit_status != "SHORT_EXIT_RESEARCH_SIGNAL":
        gate_status = "REJECTED"
        artifacts_ready = False
    else:
        gate_status = "CAPTURING"
        artifacts_ready = False
    return _arm(
        arm_id="flash_dip_execution_realism",
        gate_status=gate_status,
        sample_count=sample_count,
        artifacts_ready=artifacts_ready,
        source_ok=source_ok,
        source_path=path,
        source_error=str(source_error) if source_error else None,
        detail=detail,
    )


def _flash_dip_touchability_action_scorecard(
    touch_detail: dict[str, Any],
) -> dict[str, Any]:
    """Turn the touchability K ladder into a diagnostic research trigger."""
    if touch_detail.get("source_ok") is not True:
        return {
            "status": "NO_FRESH_TOUCHABILITY_SOURCE",
            "reason": touch_detail.get("source_error") or "missing_or_stale_touchability",
            "promotion_boundary": "diagnostic_only_not_retune_or_promotion_authority",
        }

    true_order_count = _int(touch_detail.get("true_order_count"))
    touched_count = _int(touch_detail.get("touched_count"))
    current_k = _float(touch_detail.get("current_k_pct"))
    ladder = touch_detail.get("k_ladder") if isinstance(touch_detail.get("k_ladder"), list) else []
    if true_order_count <= 0:
        return {
            "status": "NO_FLASH_DIP_ORDERS_TO_SCORE",
            "current_k_pct": current_k,
            "true_order_count": true_order_count,
            "promotion_boundary": "diagnostic_only_not_retune_or_promotion_authority",
        }

    touchable_candidates: list[dict[str, Any]] = []
    for row in ladder:
        if not isinstance(row, dict):
            continue
        k = _float(row.get("k_pct"))
        if k is None or current_k is None or k >= current_k:
            continue
        candidate_touched = _int(row.get("touched_count"))
        if candidate_touched <= 0:
            continue
        touchable_candidates.append({
            "k_pct": k,
            "true_order_count": row.get("true_order_count"),
            "touched_count": candidate_touched,
            "touch_rate_pct": row.get("touch_rate_pct"),
            "median_closest_miss_bps": row.get("median_closest_miss_bps"),
            "max_closest_miss_bps": row.get("max_closest_miss_bps"),
        })
    touchable_candidates.sort(key=lambda row: _float(row.get("k_pct")) or -1.0, reverse=True)
    research_candidate = touchable_candidates[0] if touchable_candidates else None

    if touched_count > 0:
        status = "CURRENT_K_TOUCHABLE"
        reason = "configured_k_has_touches"
    elif research_candidate:
        status = "SHALLOW_REPRICE_RESEARCH_BAND_PRESENT"
        reason = "configured_k_no_touch_but_shallower_k_has_touches"
    else:
        status = "CURRENT_K_NO_TOUCH_NO_SHALLOW_TOUCH"
        reason = "configured_k_and_candidate_ladder_no_touch"

    return {
        "status": status,
        "reason": reason,
        "current_k_pct": current_k,
        "true_order_count": true_order_count,
        "current_touched_count": touched_count,
        "current_touch_rate_pct": touch_detail.get("touch_rate_pct"),
        "research_candidate_k_pct": (
            research_candidate.get("k_pct") if research_candidate else None
        ),
        "research_candidate_touched_count": (
            research_candidate.get("touched_count") if research_candidate else None
        ),
        "research_candidate_touch_rate_pct": (
            research_candidate.get("touch_rate_pct") if research_candidate else None
        ),
        "touchable_lower_k_count": len(touchable_candidates),
        "touchable_lower_k_candidates": touchable_candidates[:8],
        "promotion_boundary": "diagnostic_only_not_retune_or_promotion_authority",
    }


def collect_flash_dip_arm(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_DAILY_ARTIFACT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    touch_path = data_dir / "logs" / "flash_dip_touchability.log"
    touchability, touch_err = _latest_json_line(touch_path)
    touch_detail: dict[str, Any] = {
        "source_path": str(touch_path),
        "source_error": touch_err,
    }
    if touchability is not None:
        touch_ts = touchability.get("ts_utc")
        touch_fresh, touch_age, touch_freshness_error = _source_fresh(
            touch_ts,
            now_utc=now_utc,
            max_age_seconds=max_age_seconds,
        )
        touch_detail = {
            "source_path": str(touch_path),
            "source_ok": touch_fresh,
            "source_error": touch_freshness_error,
            "ts_utc": touch_ts,
            "age_seconds": touch_age,
            "true_order_count": touchability.get("true_order_count"),
            "order_labeled_count": touchability.get("order_labeled_count"),
            "strategy_mismatch_count": touchability.get("strategy_mismatch_count"),
            "touched_count": touchability.get("touched_count"),
            "touch_rate_pct": touchability.get("touch_rate_pct"),
            "median_ref_to_limit_bps": touchability.get("median_ref_to_limit_bps"),
            "median_closest_miss_bps": touchability.get("median_closest_miss_bps"),
            "max_closest_miss_bps": touchability.get("max_closest_miss_bps"),
            "current_k_pct": touchability.get("current_k_pct"),
            "deepest_candidate_k_with_touch_pct": touchability.get(
                "deepest_candidate_k_with_touch_pct"
            ),
            "k_ladder": touchability.get("k_ladder"),
        }
        touch_detail["action_scorecard"] = _flash_dip_touchability_action_scorecard(
            touch_detail
        )

    l1_replay_detail = _flash_dip_l1_short_exit_replay_detail(
        data_dir,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    execution_realism_detail = _flash_dip_execution_realism_detail(
        data_dir,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )

    path = data_dir / "logs" / "flash_dip_death_rate.log"
    status, err = _latest_json_line(path)
    if err:
        gate_status = "CAPTURING"
        if (
            _int(touch_detail.get("true_order_count")) > 0
            and _int(touch_detail.get("touched_count")) == 0
            and touch_detail.get("source_ok") is True
        ):
            gate_status = "CAPTURING_NO_TOUCH"
        return _arm(
            arm_id="flash_dip_buy_demo",
            gate_status=gate_status,
            sample_count=0,
            artifacts_ready=False,
            source_ok=True,
            source_path=path,
            source_error=err,
            detail={
                "note": "death_rate_status_missing_or_not_yet_fired",
                "touchability": touch_detail,
                "execution_realism": execution_realism_detail,
                "l1_short_exit_replay": l1_replay_detail,
            },
        )
    assert status is not None
    ts_utc = status.get("ts_utc")
    fresh, age, freshness_error = _source_fresh(
        ts_utc,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    sample_count = _int(status.get("n_closed_slots"))
    alerted = bool(status.get("alerted"))
    gate_status = "REJECTED" if alerted else ("READY" if sample_count > 0 else "CAPTURING")
    if not fresh:
        gate_status = "SOURCE_FAILURE"
    elif (
        sample_count == 0
        and _int(touch_detail.get("true_order_count")) > 0
        and _int(touch_detail.get("touched_count")) == 0
        and touch_detail.get("source_ok") is True
    ):
        gate_status = "CAPTURING_NO_TOUCH"
    return _arm(
        arm_id="flash_dip_buy_demo",
        gate_status=gate_status,
        sample_count=sample_count,
        artifacts_ready=(
            fresh
            and not alerted
            and sample_count >= _int((status.get("thresholds") or {}).get("min_n"), 20)
        ),
        source_ok=fresh,
        source_path=path,
        source_error=freshness_error,
        detail={
            "ts_utc": ts_utc,
            "age_seconds": age,
            "death_rate_pct": status.get("death_rate_pct"),
            "n_deaths": status.get("n_deaths"),
            "actionable": status.get("actionable"),
            "alerted": alerted,
            "touchability": touch_detail,
            "execution_realism": execution_realism_detail,
            "l1_short_exit_replay": l1_replay_detail,
        },
    )


def collect_vol_event_arm(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "order_flow_alpha" / "vol_event_ledger.json"
    payload, err = _read_json(path)
    if err:
        return _arm(
            arm_id="vol_event_order_flow",
            gate_status="CAPTURING",
            sample_count=0,
            artifacts_ready=False,
            source_ok=True,
            source_path=path,
            source_error=err,
        )
    assert payload is not None
    events = payload.get("events") if isinstance(payload.get("events"), dict) else {}
    rows = list(events.values())
    sample_count = len(rows)
    n_up = sum(1 for row in rows if row.get("direction") == "upside_squeeze")
    n_survive = sum(1 for row in rows if (row.get("analysis") or {}).get("survives_wall"))
    threshold_met = sample_count >= 3 and n_up >= 1
    if threshold_met and n_survive <= 0:
        gate_status = "NO_EDGE_SURVIVES"
    elif threshold_met and n_survive > 0:
        gate_status = "READY"
    else:
        gate_status = "CAPTURING"
    return _arm(
        arm_id="vol_event_order_flow",
        gate_status=gate_status,
        sample_count=sample_count,
        artifacts_ready=threshold_met and n_survive > 0,
        source_ok=True,
        source_path=path,
        detail={
            "n_upside_squeeze": n_up,
            "n_events_survive_cost_wall": n_survive,
            "threshold_met": threshold_met,
            "milestones": payload.get("milestones"),
        },
    )


def collect_mm_verdict_arm(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_DAILY_ARTIFACT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    path = data_dir / "logs" / "recorder_mm_verdict.log"
    status, err = _latest_json_line(path)
    if err:
        return _arm(
            arm_id="mm_verdict_maker_edge",
            gate_status="CAPTURING",
            sample_count=0,
            artifacts_ready=False,
            source_ok=True,
            source_path=path,
            source_error=err,
            detail={"note": "mm_verdict_status_missing_or_not_yet_fired"},
        )
    assert status is not None
    ts_utc = status.get("ts_utc")
    fresh, age, freshness_error = _source_fresh(
        ts_utc,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    thresholds = status.get("thresholds") if isinstance(status.get("thresholds"), dict) else {}
    min_fills = _int(thresholds.get("min_maker_fills"), 30)
    net_by_symbol = status.get("net_edge_per_symbol") if isinstance(status.get("net_edge_per_symbol"), dict) else {}
    positive_symbols = []
    max_sample = 0
    for symbol, row in net_by_symbol.items():
        if not isinstance(row, dict):
            continue
        n = _int(row.get("n_maker_fills"))
        max_sample = max(max_sample, n)
        net = _float(row.get("net_edge_bps"))
        if net is not None and net > 0 and n >= min_fills:
            positive_symbols.append(symbol)
    sample_count = max(_int(status.get("markout_n_total")), max_sample)
    if not fresh:
        return _arm(
            arm_id="mm_verdict_maker_edge",
            gate_status="SOURCE_FAILURE",
            sample_count=sample_count,
            artifacts_ready=False,
            source_ok=False,
            source_path=path,
            source_error=freshness_error,
            detail={
                "ts_utc": ts_utc,
                "age_seconds": age,
                "positive_symbols": sorted(positive_symbols),
                "adverse_selection_usable": status.get("adverse_selection_usable"),
                "cost_wall_summary": status.get("cost_wall_summary"),
                "sample_gated_cost_wall_summary": status.get(
                    "sample_gated_cost_wall_summary"
                ),
                "gross_edge_cost_decomposition": status.get(
                    "gross_edge_cost_decomposition"
                ),
                "fee_path_feasibility": status.get("fee_path_feasibility"),
                "history_scorecard": (status.get("fillsim") or {}).get(
                    "history_scorecard"
                ),
                "horizon_scorecard": (status.get("fillsim") or {}).get("horizon_scorecard"),
                "walk_forward_failure_summary": (
                    ((status.get("fillsim") or {}).get("walk_forward_feature_scorecard") or {})
                    .get("failure_summary")
                ),
                "low_friction_signal_scorecard": (
                    (status.get("fillsim") or {}).get("low_friction_signal_scorecard")
                ),
                "l1_fill_sim_ready": status.get("l1_fill_sim_ready"),
                "highvol_day": status.get("highvol_day"),
                "markout_n_total": status.get("markout_n_total"),
                "note": "mm_verdict_status_stale_or_missing_timestamp",
            },
        )
    gate_status = "READY" if positive_symbols else "CAPTURING"
    return _arm(
        arm_id="mm_verdict_maker_edge",
        gate_status=gate_status,
        sample_count=sample_count,
        artifacts_ready=bool(positive_symbols),
        source_ok=True,
        source_path=path,
        detail={
            "ts_utc": ts_utc,
            "age_seconds": age,
            "positive_symbols": sorted(positive_symbols),
            "adverse_selection_usable": status.get("adverse_selection_usable"),
            "cost_wall_summary": status.get("cost_wall_summary"),
            "sample_gated_cost_wall_summary": status.get("sample_gated_cost_wall_summary"),
            "gross_edge_cost_decomposition": status.get("gross_edge_cost_decomposition"),
            "fee_path_feasibility": status.get("fee_path_feasibility"),
            "history_scorecard": (status.get("fillsim") or {}).get("history_scorecard"),
            "horizon_scorecard": (status.get("fillsim") or {}).get("horizon_scorecard"),
            "walk_forward_failure_summary": (
                ((status.get("fillsim") or {}).get("walk_forward_feature_scorecard") or {})
                .get("failure_summary")
            ),
            "low_friction_signal_scorecard": (
                (status.get("fillsim") or {}).get("low_friction_signal_scorecard")
            ),
            "l1_fill_sim_ready": status.get("l1_fill_sim_ready"),
            "highvol_day": status.get("highvol_day"),
            "markout_n_total": status.get("markout_n_total"),
        },
    )


def _max_ic_points(payload: dict[str, Any]) -> int:
    rows = payload.get("ic_results")
    if not isinstance(rows, list):
        return 0
    return max((_int(row.get("n_points")) for row in rows if isinstance(row, dict)), default=0)


def _sample_ic_points(payload: dict[str, Any]) -> tuple[int, int]:
    raw_points = _max_ic_points(payload)
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    if "max_overlap_adjusted_ic_points" in counts:
        return _int(counts.get("max_overlap_adjusted_ic_points")), raw_points
    rows = payload.get("ic_results")
    rows = rows if isinstance(rows, list) else []
    adjusted_from_rows = max(
        (
            _int(row.get("overlap_adjusted_sample_floor"))
            for row in rows
            if isinstance(row, dict)
        ),
        default=0,
    )
    if adjusted_from_rows > 0:
        return adjusted_from_rows, raw_points
    return raw_points, raw_points


def _polymarket_sample_gate_recheck_scorecard(
    *,
    now_utc: dt.datetime,
    sample_count: int,
    sample_gate_clock: dict[str, Any],
    pre_gate_persistence: dict[str, Any],
) -> dict[str, Any]:
    eta = _parse_dt(sample_gate_clock.get("fastest_gate_ready_utc"))
    seconds_to_eta = None
    if eta is not None:
        seconds_to_eta = (eta - now_utc).total_seconds()
    min_points = _int(sample_gate_clock.get("min_points"), 30)
    remaining = _int(
        sample_gate_clock.get("min_samples_remaining_to_gate"),
        max(0, min_points - sample_count),
    )
    persistence_status = str(pre_gate_persistence.get("status") or "")
    floor_qualified_persistent = _int(
        pre_gate_persistence.get("floor_qualified_persistent_cell_count")
    )
    floor_qualified_recurring = _int(
        pre_gate_persistence.get("floor_qualified_recurring_cell_count")
    )
    has_floor_qualified_watch = (
        floor_qualified_persistent > 0 or floor_qualified_recurring > 0
    )
    near_gate = 0 < remaining <= 6
    eta_due = seconds_to_eta is not None and seconds_to_eta <= 0
    eta_soon = seconds_to_eta is not None and 0 < seconds_to_eta <= 2 * 60 * 60

    if sample_count >= min_points:
        status = "SAMPLE_GATE_RECHECK_NOW"
        reason = "overlap_adjusted_sample_floor_reached_min_points"
        next_trigger = "rerun_polymarket_leadlag_ic_then_candidate_review"
        recheck_actionable = True
    elif has_floor_qualified_watch and near_gate and eta_due:
        status = "PERSISTENT_PRE_GATE_SAMPLE_GATE_ETA_DUE"
        reason = "floor_qualified_persistent_watchlist_at_or_past_eta"
        next_trigger = "rerun_polymarket_leadlag_ic_then_alpha_discovery"
        recheck_actionable = True
    elif has_floor_qualified_watch and near_gate and eta_soon:
        status = "PERSISTENT_PRE_GATE_NEAR_SAMPLE_GATE_WAIT_ETA"
        reason = "floor_qualified_persistent_watchlist_near_sample_gate_eta"
        next_trigger = "rerun_polymarket_leadlag_ic_after_sample_gate_eta_then_alpha_discovery"
        recheck_actionable = False
    elif persistence_status == "PERSISTENT_PRE_GATE_WATCHLIST":
        status = "PERSISTENT_PRE_GATE_WAIT_SAMPLE"
        reason = "persistent_watchlist_but_sample_gate_not_close"
        next_trigger = "continue_polymarket_capture_until_sample_gate_eta"
        recheck_actionable = False
    else:
        status = "WAIT_SAMPLE_GATE"
        reason = "no_floor_qualified_persistent_watchlist_near_gate"
        next_trigger = "wait_until_sample_gate_eta_then_recompute_hac_bh_filters"
        recheck_actionable = False

    return {
        "schema_version": "polymarket_sample_gate_recheck_v1",
        "status": status,
        "reason": reason,
        "next_trigger": next_trigger,
        "recheck_actionable": recheck_actionable,
        "sample_count": sample_count,
        "min_points": min_points,
        "min_samples_remaining_to_gate": remaining,
        "sample_gate_eta_utc": sample_gate_clock.get("fastest_gate_ready_utc"),
        "seconds_to_eta": seconds_to_eta,
        "pre_gate_watchlist_persistence_status": persistence_status or None,
        "floor_qualified_persistent_cell_count": floor_qualified_persistent,
        "floor_qualified_recurring_cell_count": floor_qualified_recurring,
        "promotion_boundary": "diagnostic_recheck_routing_only_not_signal_or_promotion_proof",
    }


def _polymarket_candidate_key(candidate: dict[str, Any]) -> str | None:
    bucket = str(candidate.get("bucket") or "").strip()
    symbol = str(candidate.get("symbol") or "").strip()
    horizon = candidate.get("horizon_minutes")
    try:
        horizon_text = f"{int(float(horizon))}m"
    except (TypeError, ValueError):
        horizon_text = f"{horizon}m" if horizon is not None else ""
    if not (bucket and symbol and horizon_text):
        return None
    return f"polymarket_leadlag_ic|{bucket}|{symbol}|{horizon_text}"


def _polymarket_replay_history_scorecard(
    report_dir: Path,
    *,
    candidate_key: str | None,
) -> dict[str, Any]:
    limit = _int(
        os.environ.get("OPENCLAW_POLYMARKET_REPLAY_HISTORY_REPORT_LIMIT"),
        DEFAULT_POLYMARKET_REPLAY_HISTORY_REPORT_LIMIT,
    )
    try:
        return polymarket_replay_history.build_history_scorecard_from_report_dir(
            report_dir,
            candidate_key=candidate_key,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001 - killboard must survive diagnostic failure.
        return {
            "status": "REPLAY_HISTORY_ERROR",
            "reason": f"{type(exc).__name__}:{exc}",
            "candidate_key": candidate_key,
            "promotion_boundary": "history_diagnostic_error_not_source_or_signal_failure",
        }


def collect_polymarket_leadlag_arm(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
) -> dict[str, Any]:
    path = data_dir / "research" / "polymarket_leadlag" / "polymarket_leadlag_latest.json"
    payload, err = _read_json(path)
    if err:
        return _arm(
            arm_id="polymarket_leadlag_ic",
            gate_status="CAPTURING",
            sample_count=0,
            artifacts_ready=False,
            source_ok=True,
            source_path=path,
            source_error=err,
            detail={"note": "polymarket_leadlag_report_missing_or_not_yet_fired"},
        )
    assert payload is not None
    created_at = payload.get("created_at_utc")
    fresh, age, freshness_error = _source_fresh(
        created_at,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    verdict = payload.get("verdict") if isinstance(payload.get("verdict"), dict) else {}
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    label_readiness = (
        counts.get("label_readiness") if isinstance(counts.get("label_readiness"), dict) else {}
    )
    sample_gate_clock = (
        counts.get("sample_gate_clock") if isinstance(counts.get("sample_gate_clock"), dict) else {}
    )
    pre_gate_persistence = (
        counts.get("pre_gate_watchlist_persistence_scorecard")
        if isinstance(counts.get("pre_gate_watchlist_persistence_scorecard"), dict)
        else {}
    )
    status = str(verdict.get("status") or "").upper()
    sample_count, raw_sample_count = _sample_ic_points(payload)
    candidate_count = _int(verdict.get("candidate_count"))
    watchlist = (
        payload.get("pre_gate_hac_watchlist")
        if isinstance(payload.get("pre_gate_hac_watchlist"), list)
        else []
    )
    best_watch = watchlist[0] if watchlist and isinstance(watchlist[0], dict) else None
    candidates = (
        payload.get("candidates")
        if isinstance(payload.get("candidates"), list)
        else []
    )
    best_candidate = (
        candidates[0]
        if candidates and isinstance(candidates[0], dict)
        else None
    )
    candidate_key = _polymarket_candidate_key(best_candidate or {})
    replay_scorecard = (
        payload.get("candidate_replay_scorecard")
        if isinstance(payload.get("candidate_replay_scorecard"), dict)
        else {}
    )
    replay_summary = (
        replay_scorecard.get("selected_summary")
        if isinstance(replay_scorecard.get("selected_summary"), dict)
        else {}
    )
    replay_history_scorecard = _polymarket_replay_history_scorecard(
        path.parent,
        candidate_key=candidate_key,
    )
    replay_history_summary = (
        replay_history_scorecard.get("selected_summary")
        if isinstance(replay_history_scorecard.get("selected_summary"), dict)
        else {}
    )
    sample_gate_recheck = _polymarket_sample_gate_recheck_scorecard(
        now_utc=now_utc,
        sample_count=sample_count,
        sample_gate_clock=sample_gate_clock,
        pre_gate_persistence=pre_gate_persistence,
    )

    if not fresh:
        gate_status = "SOURCE_FAILURE"
        artifacts_ready = False
        source_ok = False
    elif status == "IC_CANDIDATE_REVIEW_REQUIRED":
        gate_status = "READY"
        artifacts_ready = candidate_count > 0
        source_ok = True
    elif status == "IC_READY_NO_SIGNIFICANT_EDGE":
        gate_status = "NO_EDGE_SURVIVES"
        artifacts_ready = False
        source_ok = True
    elif status == "NO_PRICE_DATA":
        gate_status = "SOURCE_FAILURE"
        artifacts_ready = False
        source_ok = False
        freshness_error = "no_price_data"
    else:
        gate_status = "CAPTURING"
        artifacts_ready = False
        source_ok = True

    return _arm(
        arm_id="polymarket_leadlag_ic",
        gate_status=gate_status,
        sample_count=sample_count,
        artifacts_ready=artifacts_ready,
        source_ok=source_ok,
        source_path=path,
        source_error=freshness_error,
        detail={
            "created_at_utc": created_at,
            "age_seconds": age,
            "verdict_status": status,
            "reason": verdict.get("reason"),
            "candidate_count": candidate_count,
            "candidate_key": candidate_key,
            "best_candidate": best_candidate,
            "candidate_replay_status": replay_scorecard.get("status"),
            "candidate_replay_candidate_id": replay_summary.get("candidate_id"),
            "candidate_replay_parameter_cell_id": replay_summary.get("parameter_cell_id"),
            "candidate_replay_sample_count": replay_summary.get("sample_count"),
            "candidate_replay_round_trip_cost_bps": replay_summary.get("round_trip_cost_bps"),
            "candidate_replay_gross_bps_mean": replay_summary.get("gross_bps_mean"),
            "candidate_replay_net_bps_mean": replay_summary.get("net_bps_mean"),
            "candidate_replay_holdout_net_bps_mean": replay_summary.get("holdout_net_bps_mean"),
            "candidate_replay_cost_wall_status": replay_summary.get("cost_wall_status"),
            "candidate_replay_execution_realism_status": replay_summary.get(
                "execution_realism_status"
            ),
            "candidate_replay_scorecard": replay_scorecard or None,
            "candidate_replay_history_status": replay_history_scorecard.get("status"),
            "candidate_replay_history_reason": replay_history_scorecard.get("reason"),
            "candidate_replay_history_report_count": replay_history_scorecard.get("report_count"),
            "candidate_replay_history_matched_report_count": replay_history_scorecard.get(
                "matched_report_count"
            ),
            "candidate_replay_history_sample_count": replay_history_summary.get("sample_count"),
            "candidate_replay_history_n_days": replay_history_summary.get("n_days"),
            "candidate_replay_history_min_days": replay_history_summary.get("min_history_days"),
            "candidate_replay_history_min_samples": replay_history_summary.get(
                "min_history_samples"
            ),
            "candidate_replay_history_net_bps_mean": replay_history_summary.get("net_bps_mean"),
            "candidate_replay_history_holdout_net_bps_mean": replay_history_summary.get(
                "holdout_net_bps_mean"
            ),
            "candidate_replay_history_pbo_day_count": replay_history_summary.get(
                "pbo_history_day_count"
            ),
            "candidate_replay_history_execution_realism_status": replay_history_summary.get(
                "execution_realism_status"
            ),
            "candidate_replay_history_scorecard": replay_history_scorecard or None,
            "preliminary_raw_candidate_count": verdict.get("preliminary_raw_candidate_count"),
            "preliminary_hac_candidate_count": verdict.get("preliminary_hac_candidate_count"),
            "pre_gate_hac_watchlist_count": verdict.get("pre_gate_hac_watchlist_count"),
            "pre_gate_watchlist_persistence_status": verdict.get(
                "pre_gate_watchlist_persistence_status"
            ),
            "pre_gate_watchlist_recurring_cell_count": verdict.get(
                "pre_gate_watchlist_recurring_cell_count"
            ),
            "pre_gate_watchlist_persistent_cell_count": verdict.get(
                "pre_gate_watchlist_persistent_cell_count"
            ),
            "pre_gate_watchlist_floor_qualified_recurring_cell_count": verdict.get(
                "pre_gate_watchlist_floor_qualified_recurring_cell_count"
            ),
            "pre_gate_watchlist_floor_qualified_persistent_cell_count": verdict.get(
                "pre_gate_watchlist_floor_qualified_persistent_cell_count"
            ),
            "pre_gate_watchlist_persistence_scorecard": pre_gate_persistence,
            "price_feedback_warning_count": verdict.get("price_feedback_warning_count"),
            "price_feedback_partial_collapse_count": verdict.get(
                "price_feedback_partial_collapse_count"
            ),
            "best_pre_gate_hac_watch": best_watch,
            "significance_t_stat": verdict.get("significance_t_stat"),
            "max_bh_q": verdict.get("max_bh_q"),
            "query_set_version": payload.get("query_set_version"),
            "mode": payload.get("mode"),
            "symbols": payload.get("symbols"),
            "horizons_minutes": payload.get("horizons_minutes"),
            "price_source": payload.get("price_source"),
            "snapshot_rows": counts.get("snapshot_rows"),
            "snapshot_distinct_timestamps": counts.get("snapshot_distinct_timestamps"),
            "delta_rows": counts.get("delta_rows"),
            "feature_points": counts.get("feature_points"),
            "feature_bucket_counts": counts.get("feature_bucket_counts"),
            "feature_bucket_view_counts": counts.get("feature_bucket_view_counts"),
            "feature_source_counts": counts.get("feature_source_counts"),
            "joined_rows": counts.get("joined_rows"),
            "price_rows": counts.get("price_rows"),
            "max_ic_points": raw_sample_count,
            "max_overlap_adjusted_ic_points": sample_count,
            "min_samples_remaining_to_gate": counts.get("min_samples_remaining_to_gate"),
            "sample_gate_status": sample_gate_clock.get("status"),
            "sample_gate_eta_utc": sample_gate_clock.get("fastest_gate_ready_utc"),
            "sample_gate_clock": sample_gate_clock,
            "sample_gate_recheck_scorecard": sample_gate_recheck,
            "sample_gate_recheck_status": sample_gate_recheck.get("status"),
            "price_feedback_summary": counts.get("price_feedback_summary"),
            "max_abs_t_stat_hac": counts.get("max_abs_t_stat_hac"),
            "label_feature_horizon_pairs": label_readiness.get("feature_horizon_pairs"),
            "label_joinable_pairs": label_readiness.get("joinable_pairs"),
            "label_status_counts": label_readiness.get("status_counts"),
            "label_by_horizon": label_readiness.get("by_horizon"),
            "latest_feature_ts_utc": label_readiness.get("latest_feature_ts_utc"),
            "latest_price_ts_utc_by_symbol": label_readiness.get(
                "latest_price_ts_utc_by_symbol"
            ),
            "oldest_unmatured_exit_target_utc": label_readiness.get(
                "oldest_unmatured_exit_target_utc"
            ),
            "newest_unmatured_exit_target_utc": label_readiness.get(
                "newest_unmatured_exit_target_utc"
            ),
            "promotion_boundary": verdict.get("promotion_boundary"),
        },
    )


def _latest_matrix_summary(alpha_history_root: Path) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    try:
        candidates = sorted(
            alpha_history_root.glob("*/verdict_matrix_summary.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError as exc:
        return None, None, f"scan_error:{type(exc).__name__}"
    for path in candidates:
        payload, err = _read_json(path)
        if not err:
            return path, payload, None
    return None, None, "missing"


def collect_aeg_matrix_arm(data_dir: Path) -> dict[str, Any]:
    root = data_dir / "alpha_history_runs"
    path, payload, err = _latest_matrix_summary(root)
    if err:
        return _arm(
            arm_id="aeg_robustness_matrix",
            gate_status="WAIT",
            sample_count=0,
            artifacts_ready=False,
            source_ok=True,
            source_path=root,
            source_error=err,
            detail={"note": "no_robustness_matrix_artifact_seen"},
        )
    assert payload is not None
    counts = payload.get("final_label_counts") if isinstance(payload.get("final_label_counts"), dict) else {}
    durable = _int(counts.get("durable-alpha candidate"))
    row_count = _int(payload.get("row_count"))
    gate_status = "READY" if durable > 0 else "WAIT"
    return _arm(
        arm_id="aeg_robustness_matrix",
        gate_status=gate_status,
        sample_count=row_count,
        artifacts_ready=durable > 0,
        source_ok=True,
        source_path=path,
        detail={
            "run_id": payload.get("run_id"),
            "candidate_id": payload.get("candidate_id"),
            "candidate_key": payload.get("candidate_key"),
            "candidate_metrics_source_report_type": payload.get(
                "candidate_metrics_source_report_type"
            ),
            "candidate_metrics_selected_variant": payload.get(
                "candidate_metrics_selected_variant"
            ),
            "final_label_counts": counts,
            "durable_candidate_rows": durable,
            "coverage_gate_status": payload.get("coverage_gate_status"),
            "execution_realism_mode": payload.get("execution_realism_mode"),
        },
    )


def summarize_demo_learning_evidence_audit(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_DAILY_ARTIFACT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    path = data_dir / "demo_learning_evidence" / "demo_learning_evidence_audit_latest.json"
    payload, err = _read_json(path)
    if err:
        return {
            "demo_learning_evidence_status": "NOT_SEEN",
            "demo_learning_evidence_source_path": str(path),
            "demo_learning_evidence_source_error": err,
        }
    assert payload is not None
    generated_at = payload.get("generated_at_utc")
    fresh, age, freshness_error = _source_fresh(
        generated_at,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    classification = (
        payload.get("classification")
        if isinstance(payload.get("classification"), dict)
        else {}
    )
    answers = (
        classification.get("answers")
        if isinstance(classification.get("answers"), dict)
        else {}
    )
    counts = (
        classification.get("key_counts")
        if isinstance(classification.get("key_counts"), dict)
        else {}
    )
    order_scorecard = (
        payload.get("order_stall_scorecard")
        if isinstance(payload.get("order_stall_scorecard"), dict)
        else {}
    )
    order_classification = (
        order_scorecard.get("classification")
        if isinstance(order_scorecard.get("classification"), dict)
        else {}
    )
    preflight = (
        payload.get("cost_gate_learning_preflight")
        if isinstance(payload.get("cost_gate_learning_preflight"), dict)
        else {}
    )
    return {
        "demo_learning_evidence_status": (
            str(classification.get("status") or "UNKNOWN") if fresh else "STALE_ARTIFACT"
        ),
        "demo_learning_evidence_classification_status": classification.get("status"),
        "demo_learning_evidence_reason": classification.get("reason"),
        "demo_learning_evidence_next_action": classification.get("next_action"),
        "demo_learning_evidence_generated_at_utc": generated_at,
        "demo_learning_evidence_age_seconds": age,
        "demo_learning_evidence_source_ok": fresh,
        "demo_learning_evidence_source_path": str(path),
        "demo_learning_evidence_source_error": freshness_error,
        "demo_learning_evidence_order_stall_status": order_classification.get("status"),
        "demo_learning_evidence_preflight_status": preflight.get("status"),
        "demo_learning_evidence_cost_gate_rejects_recorded_in_pg": answers.get(
            "cost_gate_rejects_recorded_in_pg"
        ),
        "demo_learning_evidence_observation_only_contexts_active": answers.get(
            "demo_observation_only_contexts_active"
        ),
        "demo_learning_evidence_candidate_or_reject_data_accumulating": answers.get(
            "candidate_or_reject_data_accumulating"
        ),
        "demo_learning_evidence_learning_lane_ledger_rows_present": answers.get(
            "learning_lane_ledger_rows_present"
        ),
        "demo_learning_evidence_currently_accumulating": answers.get(
            "learning_lane_currently_accumulating_evidence"
        ),
        "demo_learning_evidence_blocked_outcome_review_candidate_present": answers.get(
            "blocked_outcome_review_candidate_present"
        ),
        "demo_learning_evidence_order_flow_silent_drop_risk": answers.get(
            "order_flow_silent_drop_risk"
        ),
        "demo_learning_evidence_order_flow_evidence_status": counts.get(
            "order_flow_evidence_status"
        ),
        "demo_learning_evidence_order_flow_evidence_reason": counts.get(
            "order_flow_evidence_reason"
        ),
        "demo_learning_evidence_order_flow_evidence_next_action": counts.get(
            "order_flow_evidence_next_action"
        ),
        "demo_learning_evidence_recent_order_flow_present": answers.get(
            "recent_order_flow_present"
        ),
        "demo_learning_evidence_recent_fill_evidence_present": answers.get(
            "recent_fill_evidence_present"
        ),
        "demo_learning_evidence_order_flow_evidence_starved": answers.get(
            "order_flow_evidence_starved"
        ),
        "demo_learning_evidence_cost_gate_adjustment_recommendation_status": counts.get(
            "cost_gate_adjustment_recommendation_status"
        ),
        "demo_learning_evidence_cost_gate_adjustment_recommendation_reason": counts.get(
            "cost_gate_adjustment_recommendation_reason"
        ),
        "demo_learning_evidence_cost_gate_adjustment_recommendation_next_action": counts.get(
            "cost_gate_adjustment_recommendation_next_action"
        ),
        "demo_learning_evidence_cost_gate_learning_gate_adjustment": counts.get(
            "cost_gate_learning_gate_adjustment"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_preflight_blocking": counts.get(
            "cost_gate_adjustment_runtime_preflight_blocking"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_activation_ready": counts.get(
            "cost_gate_adjustment_runtime_activation_ready"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_activation_blockers": counts.get(
            "cost_gate_adjustment_runtime_activation_blockers"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_source_activation_ready": counts.get(
            "cost_gate_adjustment_runtime_source_activation_ready"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_source_activation_status": counts.get(
            "cost_gate_adjustment_runtime_source_activation_status"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_writer_config_required": counts.get(
            "cost_gate_adjustment_runtime_writer_config_required"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_writer_config_enabled": counts.get(
            "cost_gate_adjustment_runtime_writer_config_enabled"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_writer_config_status": counts.get(
            "cost_gate_adjustment_runtime_writer_config_status"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_writer_process_required": counts.get(
            "cost_gate_adjustment_runtime_writer_process_required"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_writer_process_enabled": counts.get(
            "cost_gate_adjustment_runtime_writer_process_enabled"
        ),
        "demo_learning_evidence_cost_gate_adjustment_runtime_writer_process_status": counts.get(
            "cost_gate_adjustment_runtime_writer_process_status"
        ),
        "demo_learning_evidence_data_flow_freshness_status": counts.get(
            "data_flow_freshness_status"
        ),
        "demo_learning_evidence_latest_learning_stage": counts.get(
            "latest_learning_stage"
        ),
        "demo_learning_evidence_latest_learning_ts_utc": counts.get(
            "latest_learning_ts_utc"
        ),
        "demo_learning_evidence_latest_learning_age_seconds": counts.get(
            "latest_learning_age_seconds"
        ),
        "demo_learning_evidence_learning_data_flow_fresh": answers.get(
            "learning_data_flow_fresh"
        ),
        "demo_learning_evidence_learning_data_flow_stale": answers.get(
            "learning_data_flow_stale"
        ),
        "demo_learning_evidence_bounded_learning_lane_recommended": answers.get(
            "bounded_demo_learning_lane_recommended"
        ),
        "demo_learning_evidence_contexts": counts.get("decision_context_snapshots"),
        "demo_learning_evidence_risk_verdicts": counts.get("risk_verdicts"),
        "demo_learning_evidence_rejected_features": counts.get(
            "rejected_decision_features"
        ),
        "demo_learning_evidence_orders": counts.get("orders"),
        "demo_learning_evidence_fills": counts.get("fills"),
        "demo_learning_evidence_learning_ledger_rows": counts.get(
            "learning_ledger_rows"
        ),
        "demo_learning_evidence_blocked_signal_outcomes": counts.get(
            "blocked_signal_outcomes"
        ),
    }


def summarize_demo_learning_stack_healthcheck(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_DAILY_ARTIFACT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    path = (
        data_dir
        / "demo_learning_stack_healthcheck"
        / "demo_learning_stack_healthcheck_latest.json"
    )
    payload, err = _read_json(path)
    if err:
        return {
            "demo_learning_stack_healthcheck_status": "NOT_SEEN",
            "demo_learning_stack_healthcheck_source_path": str(path),
            "demo_learning_stack_healthcheck_source_error": err,
        }
    assert payload is not None
    ts_utc = payload.get("ts_utc")
    fresh, age, freshness_error = _source_fresh(
        ts_utc,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else {}
    return {
        "demo_learning_stack_healthcheck_status": (
            str(payload.get("status") or "UNKNOWN") if fresh else "STALE_ARTIFACT"
        ),
        "demo_learning_stack_healthcheck_raw_status": payload.get("status"),
        "demo_learning_stack_healthcheck_reason": payload.get("reason"),
        "demo_learning_stack_healthcheck_next_action": payload.get("next_action"),
        "demo_learning_stack_healthcheck_ts_utc": ts_utc,
        "demo_learning_stack_healthcheck_age_seconds": age,
        "demo_learning_stack_healthcheck_source_ok": fresh,
        "demo_learning_stack_healthcheck_source_path": str(path),
        "demo_learning_stack_healthcheck_source_error": freshness_error,
        "demo_learning_stack_source_ready": answers.get("source_ready"),
        "demo_learning_stack_stack_installed": answers.get("stack_installed"),
        "demo_learning_stack_heartbeats_recent": answers.get("heartbeats_recent"),
        "demo_learning_stack_statuses_recent": answers.get("statuses_recent"),
        "demo_learning_stack_latest_artifacts_present": answers.get(
            "latest_artifacts_present"
        ),
        "demo_learning_stack_cost_gate_learning_stage_error": answers.get(
            "cost_gate_learning_stage_error"
        ),
        "demo_learning_stack_cost_gate_learning_ledger_rows_present": answers.get(
            "cost_gate_learning_ledger_rows_present"
        ),
        "demo_learning_stack_blocked_signal_outcomes_present": answers.get(
            "blocked_signal_outcomes_present"
        ),
        "demo_learning_stack_blocked_outcome_review_present": answers.get(
            "blocked_outcome_review_present"
        ),
        "demo_learning_stack_demo_learning_evidence_classification_status": answers.get(
            "demo_learning_evidence_classification_status"
        ),
        "demo_learning_stack_cost_gate_learning_review_status": answers.get(
            "cost_gate_learning_review_status"
        ),
    }


def collect_cost_gate_learning_lane_arm(
    data_dir: Path,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int = DEFAULT_DAILY_ARTIFACT_MAX_AGE_SECONDS,
    repo_root: Path | None = None,
    expected_head: str | None = None,
) -> dict[str, Any]:
    path = data_dir / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"
    ledger_path = data_dir / "cost_gate_learning_lane" / "probe_ledger.jsonl"
    ledger_summary = summarize_cost_gate_learning_lane_ledger(ledger_path)
    loop_summary = summarize_cost_gate_learning_lane_loop(data_dir, now_utc=now_utc)
    historical_summary = summarize_cost_gate_learning_lane_historical_review(
        data_dir,
        now_utc=now_utc,
    )
    demo_evidence_summary = summarize_demo_learning_evidence_audit(
        data_dir,
        now_utc=now_utc,
    )
    stack_health_summary = summarize_demo_learning_stack_healthcheck(
        data_dir,
        now_utc=now_utc,
    )
    source_summary: dict[str, Any] = {}
    if repo_root is not None:
        source = summarize_cost_gate_learning_lane_source(
            repo_root,
            expected_head=expected_head,
        )
        source_summary = {
            "learning_lane_source_status": source.get("source_status"),
            "learning_lane_source_ready": source.get("source_ready"),
            "learning_lane_source_activation_status": source.get("source_activation_status"),
            "learning_lane_source_activation_ready": source.get("source_activation_ready"),
            "learning_lane_git_status": source.get("git_status"),
            "learning_lane_git_head": source.get("git_head"),
            "learning_lane_git_head_short": source.get("git_head_short"),
            "learning_lane_git_branch": source.get("git_branch"),
            "learning_lane_git_upstream": source.get("git_upstream"),
            "learning_lane_git_behind_count": source.get("git_behind_count"),
            "learning_lane_git_ahead_count": source.get("git_ahead_count"),
            "learning_lane_git_dirty_path_count": source.get("git_dirty_path_count"),
            "learning_lane_git_untracked_path_count": source.get("git_untracked_path_count"),
            "learning_lane_expected_head": source.get("expected_head"),
            "learning_lane_expected_head_status": source.get("expected_head_status"),
            "learning_lane_expected_head_matches": source.get("expected_head_matches"),
            "learning_lane_missing_source_relative_paths": source.get(
                "missing_source_relative_paths"
            ),
            "learning_lane_non_executable_source_relative_paths": source.get(
                "non_executable_source_relative_paths"
            ),
        }
    payload, err = _read_json(path)
    if err:
        return _arm(
            arm_id="cost_gate_demo_learning_lane",
            gate_status="WAIT",
            sample_count=0,
            artifacts_ready=False,
            source_ok=True,
            source_path=path,
            source_error=f"optional_plan_{err}",
            detail={
                "plan_status": "SOURCE_SCORECARD_UNAVAILABLE",
                "note": "cost_gate_learning_lane_plan_not_seen",
                **source_summary,
                **demo_evidence_summary,
                **stack_health_summary,
                **historical_summary,
                **loop_summary,
                **ledger_summary,
            },
        )
    assert payload is not None
    generated_at = payload.get("generated_at_utc")
    fresh, age, freshness_error = _source_fresh(
        generated_at,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    status = str(payload.get("status") or "WAIT")
    gate_status = str(payload.get("gate_status") or "WAIT").upper()
    candidates = payload.get("probe_candidates") if isinstance(payload.get("probe_candidates"), list) else []
    selected_count = _int(payload.get("selected_probe_candidate_count"), len(candidates))
    if not fresh:
        gate_status = "SOURCE_FAILURE"
    return _arm(
        arm_id="cost_gate_demo_learning_lane",
        gate_status=gate_status,
        sample_count=selected_count,
        artifacts_ready=False,
        source_ok=fresh,
        source_path=path,
        source_error=freshness_error,
        detail={
            "plan_status": status,
            "generated_at_utc": generated_at,
            "age_seconds": age,
            "main_cost_gate_adjustment": payload.get("main_cost_gate_adjustment"),
            "learning_gate_adjustment": payload.get("learning_gate_adjustment"),
            "order_authority": payload.get("order_authority"),
            "probe_budget": payload.get("probe_budget"),
            "probe_candidate_count": payload.get("probe_candidate_count"),
            "selected_probe_candidate_count": selected_count,
            "probe_candidates": candidates[:8],
            "do_not_probe_side_cells": payload.get("do_not_probe_side_cells"),
            "data_coverage_tasks": payload.get("data_coverage_tasks"),
            "source": payload.get("source"),
            "boundary": payload.get("boundary"),
            **source_summary,
            **demo_evidence_summary,
            **stack_health_summary,
            **historical_summary,
            **loop_summary,
            **ledger_summary,
        },
    )


def collect_runtime_arms(
    *,
    data_dir: Path,
    repo_root: Path | None = None,
    expected_head: str | None = None,
    now_utc: dt.datetime | None = None,
    max_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
) -> list[dict[str, Any]]:
    now = now_utc or _utc_now()
    return [
        collect_gate_b_arm(data_dir, now_utc=now, max_age_seconds=max_age_seconds),
        collect_flash_dip_arm(data_dir, now_utc=now),
        collect_flash_dip_execution_realism_arm(data_dir, now_utc=now),
        collect_flash_dip_l1_replay_arm(data_dir, now_utc=now),
        collect_vol_event_arm(data_dir),
        collect_mm_verdict_arm(data_dir, now_utc=now),
        collect_polymarket_leadlag_arm(data_dir, now_utc=now),
        collect_cost_gate_learning_lane_arm(
            data_dir,
            now_utc=now,
            repo_root=repo_root,
            expected_head=expected_head,
        ),
        collect_aeg_matrix_arm(data_dir),
    ]


def _action_counts(plan: dict[str, Any]) -> dict[str, int]:
    return {str(k): _int(v) for k, v in (plan.get("action_counts") or {}).items()}


def _learning_worklist(plan: dict[str, Any]) -> dict[str, Any]:
    worklist = plan.get("learning_worklist")
    return worklist if isinstance(worklist, dict) else {}


def _learning_top_task(worklist: dict[str, Any]) -> dict[str, Any]:
    top_task = worklist.get("top_task")
    return top_task if isinstance(top_task, dict) else {}


def _learning_summary(worklist: dict[str, Any]) -> dict[str, Any]:
    top_task = _learning_top_task(worklist)
    completion_evidence_required = top_task.get("completion_evidence_required")
    if not isinstance(completion_evidence_required, list):
        completion_evidence_required = []
    evidence = top_task.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    return {
        "learning_worklist_status": worklist.get("status"),
        "learning_task_count": _int(worklist.get("task_count")),
        "learning_promotion_ready_count": _int(worklist.get("promotion_ready_count")),
        "learning_operator_required_count": _int(worklist.get("operator_required_count")),
        "learning_runtime_mutation_required_count": _int(
            worklist.get("runtime_mutation_required_count")
        ),
        "learning_engineering_actionable_count": _int(
            worklist.get("engineering_actionable_count")
        ),
        "top_learning_task_id": top_task.get("task_id"),
        "top_learning_task_arm_id": top_task.get("arm_id"),
        "top_learning_task_type": top_task.get("task_type"),
        "top_learning_task_objective": top_task.get("learning_objective"),
        "top_learning_task_completion_gate": top_task.get("completion_gate"),
        "top_learning_task_completion_status": top_task.get("completion_status"),
        "top_learning_task_completion_evidence_required_count": len(
            completion_evidence_required
        ),
        "top_learning_task_actionability": top_task.get("actionability"),
        "top_learning_task_requires_operator_authorization": top_task.get(
            "requires_operator_authorization"
        ),
        "top_learning_task_runtime_mutation_required": top_task.get(
            "runtime_mutation_required"
        ),
        "top_learning_task_next_trigger": top_task.get("next_trigger"),
        "top_learning_task_evidence_key_count": len(evidence),
        "top_learning_task_evidence": evidence or None,
        "top_learning_task_blocked_signal_top_review_candidate_side_cell_key": (
            evidence.get("blocked_signal_top_review_candidate_side_cell_key")
        ),
        "top_learning_task_blocked_signal_top_review_candidate_wrongful_block_score": (
            evidence.get("blocked_signal_top_review_candidate_wrongful_block_score")
        ),
        "top_learning_task_blocked_signal_top_review_candidate_net_cost_cushion_bps": (
            evidence.get("blocked_signal_top_review_candidate_net_cost_cushion_bps")
        ),
    }


def build_runtime_killboard(
    *,
    data_dir: Path,
    repo_root: Path,
    expected_head: str | None = None,
    now_utc: dt.datetime | None = None,
    min_samples: int = 30,
    max_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    runtime_source = summarize_cost_gate_learning_lane_source(
        repo_root,
        expected_head=expected_head,
    )
    arms = collect_runtime_arms(
        data_dir=data_dir,
        repo_root=repo_root,
        expected_head=expected_head,
        now_utc=now,
        max_age_seconds=max_age_seconds,
    )
    plan = build_discovery_plan(arms, min_samples=min_samples, now_utc=now)
    counts = _action_counts(plan)
    learning_worklist = _learning_worklist(plan)
    learning_summary = _learning_summary(learning_worklist)
    scorecard = (
        plan.get("profitability_blocker_scorecard")
        if isinstance(plan.get("profitability_blocker_scorecard"), dict)
        else {}
    )
    promotion_ready_count = _int(scorecard.get("promotion_ready_count"))
    runtime_source_activation_ready = (
        runtime_source.get("source_activation_ready") is True
    )
    source_ok_count = sum(1 for arm in arms if arm.get("source_ok") is True)
    source_present_count = sum(
        1 for arm in arms
        if arm.get("source_ok") is True and not arm.get("source_error")
    )
    active_arm_count = sum(
        1 for row in plan["arms"]
        if row["action"] in {"READY_FOR_AEG_CHAIN", "READY_FOR_PROBE", "RUN_READ_ONLY_CAPTURE", "WAIT"}
    )
    return {
        "schema_version": RUNTIME_KILLBOARD_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "created_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "policy": "artifact_only_runtime_discovery_no_db_no_bybit_no_trade_side_effect",
        "data_dir": str(data_dir),
        "repo_root": str(repo_root),
        "expected_source_head": expected_head,
        "killboard": {
            "is_fast_discovery_active": active_arm_count >= 3 and source_present_count >= 3,
            "active_arm_count": active_arm_count,
            "source_ok_count": source_ok_count,
            "source_present_count": source_present_count,
            "runtime_source_activation_ready": runtime_source_activation_ready,
            "runtime_source_activation_status": runtime_source.get(
                "source_activation_status"
            ),
            "runtime_source_git_status": runtime_source.get("git_status"),
            "runtime_source_expected_head_status": runtime_source.get(
                "expected_head_status"
            ),
            "ready_for_aeg_chain": counts.get("READY_FOR_AEG_CHAIN", 0),
            "ready_for_probe": counts.get("READY_FOR_PROBE", 0),
            "run_read_only_capture": counts.get("RUN_READ_ONLY_CAPTURE", 0),
            "wait": counts.get("WAIT", 0),
            "block": counts.get("BLOCK", 0),
            "promotion_ready_count": promotion_ready_count,
            "promotion_ready_candidate_found": promotion_ready_count > 0,
            "aeg_candidate_artifact_found": counts.get("READY_FOR_AEG_CHAIN", 0) > 0,
            "actionable_alpha_found": (
                promotion_ready_count > 0 and runtime_source_activation_ready
            ),
            "actionable_probe_found": (
                counts.get("READY_FOR_PROBE", 0) > 0
                and runtime_source_activation_ready
            ),
            **learning_summary,
        },
        "runtime_source": runtime_source,
        "discovery_plan": plan,
        "profitability_blocker_scorecard": plan.get("profitability_blocker_scorecard"),
        "learning_worklist": learning_worklist,
        "arms_raw": arms,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _history_row(killboard: dict[str, Any]) -> dict[str, Any]:
    kb = killboard.get("killboard") or {}
    return {
        "created_at_utc": killboard.get("created_at_utc"),
        "is_fast_discovery_active": kb.get("is_fast_discovery_active"),
        "ready_for_aeg_chain": kb.get("ready_for_aeg_chain"),
        "ready_for_probe": kb.get("ready_for_probe"),
        "runtime_source_activation_ready": kb.get("runtime_source_activation_ready"),
        "runtime_source_activation_status": kb.get("runtime_source_activation_status"),
        "runtime_source_git_status": kb.get("runtime_source_git_status"),
        "runtime_source_expected_head_status": kb.get(
            "runtime_source_expected_head_status"
        ),
        "promotion_ready_count": kb.get("promotion_ready_count"),
        "promotion_ready_candidate_found": kb.get("promotion_ready_candidate_found"),
        "aeg_candidate_artifact_found": kb.get("aeg_candidate_artifact_found"),
        "actionable_alpha_found": kb.get("actionable_alpha_found"),
        "actionable_probe_found": kb.get("actionable_probe_found"),
        "run_read_only_capture": kb.get("run_read_only_capture"),
        "wait": kb.get("wait"),
        "block": kb.get("block"),
        "learning_worklist_status": kb.get("learning_worklist_status"),
        "learning_task_count": kb.get("learning_task_count"),
        "learning_operator_required_count": kb.get("learning_operator_required_count"),
        "learning_runtime_mutation_required_count": kb.get(
            "learning_runtime_mutation_required_count"
        ),
        "learning_engineering_actionable_count": kb.get(
            "learning_engineering_actionable_count"
        ),
        "top_learning_task_arm_id": kb.get("top_learning_task_arm_id"),
        "top_learning_task_type": kb.get("top_learning_task_type"),
        "top_learning_task_completion_gate": kb.get("top_learning_task_completion_gate"),
        "top_learning_task_completion_status": kb.get("top_learning_task_completion_status"),
        "top_learning_task_completion_evidence_required_count": kb.get(
            "top_learning_task_completion_evidence_required_count"
        ),
        "top_learning_task_actionability": kb.get("top_learning_task_actionability"),
        "top_learning_task_requires_operator_authorization": kb.get(
            "top_learning_task_requires_operator_authorization"
        ),
        "top_learning_task_runtime_mutation_required": kb.get(
            "top_learning_task_runtime_mutation_required"
        ),
        "top_learning_task_evidence_key_count": kb.get(
            "top_learning_task_evidence_key_count"
        ),
        "top_learning_task_evidence": kb.get("top_learning_task_evidence"),
        "top_learning_task_blocked_signal_top_review_candidate_side_cell_key": kb.get(
            "top_learning_task_blocked_signal_top_review_candidate_side_cell_key"
        ),
        "top_learning_task_blocked_signal_top_review_candidate_wrongful_block_score": kb.get(
            "top_learning_task_blocked_signal_top_review_candidate_wrongful_block_score"
        ),
        "top_learning_task_blocked_signal_top_review_candidate_net_cost_cushion_bps": kb.get(
            "top_learning_task_blocked_signal_top_review_candidate_net_cost_cushion_bps"
        ),
    }


def write_runtime_artifacts(killboard: dict[str, Any], *, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "alpha_discovery_latest.json"
    stamp = re.sub(r"[^0-9A-Za-z]+", "", str(killboard["created_at_utc"]))[:15]
    dated = out_dir / f"alpha_discovery_{stamp}.json"
    history = out_dir / "alpha_discovery_history.jsonl"
    _atomic_write_json(latest, killboard)
    _atomic_write_json(dated, killboard)
    with open(history, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(_history_row(killboard), ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return {"latest": str(latest), "dated": str(dated), "history": str(history)}


def run_once(
    *,
    data_dir: Path,
    repo_root: Path,
    out_dir: Path | None = None,
    expected_head: str | None = None,
    now_utc: dt.datetime | None = None,
    min_samples: int = 30,
    max_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
) -> dict[str, Any]:
    killboard = build_runtime_killboard(
        data_dir=data_dir,
        repo_root=repo_root,
        expected_head=expected_head,
        now_utc=now_utc,
        min_samples=min_samples,
        max_age_seconds=max_age_seconds,
    )
    artifact_dir = out_dir or (data_dir / "alpha_discovery_throughput")
    killboard["written"] = write_runtime_artifacts(killboard, out_dir=artifact_dir)
    return killboard


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build artifact-only alpha discovery runtime killboard.",
    )
    parser.add_argument("--data-dir", default=os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    parser.add_argument("--repo-root", default=os.environ.get("OPENCLAW_BASE_DIR", str(Path.cwd())))
    parser.add_argument(
        "--expected-head",
        default=(
            os.environ.get("OPENCLAW_EXPECTED_SOURCE_HEAD")
            or os.environ.get("OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD")
        ),
    )
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--max-age-seconds", type=int, default=DEFAULT_MAX_ARTIFACT_AGE_SECONDS)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_once(
        data_dir=Path(args.data_dir),
        repo_root=Path(args.repo_root),
        out_dir=Path(args.out_dir) if args.out_dir else None,
        expected_head=args.expected_head,
        min_samples=args.min_samples,
        max_age_seconds=args.max_age_seconds,
    )
    if args.print_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps(_history_row(result), ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "RUNTIME_KILLBOARD_SCHEMA_VERSION",
    "build_runtime_killboard",
    "collect_polymarket_leadlag_arm",
    "collect_runtime_arms",
    "run_once",
    "write_runtime_artifacts",
]

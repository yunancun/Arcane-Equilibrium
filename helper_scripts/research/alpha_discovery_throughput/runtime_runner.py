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

from . import RUNNER_VERSION
from .discovery_loop import build_discovery_plan

RUNTIME_KILLBOARD_SCHEMA_VERSION = "alpha_discovery_runtime_killboard_v1"
DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60
DEFAULT_DAILY_ARTIFACT_MAX_AGE_SECONDS = 36 * 60 * 60


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


def _latest_json_line(path: Path, *, prefix: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 262144), os.SEEK_SET)
            chunk = fh.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"

    for raw_line in reversed(chunk.splitlines()):
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
            "l1_fill_sim_ready": status.get("l1_fill_sim_ready"),
            "highvol_day": status.get("highvol_day"),
            "markout_n_total": status.get("markout_n_total"),
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
            "final_label_counts": counts,
            "durable_candidate_rows": durable,
            "coverage_gate_status": payload.get("coverage_gate_status"),
            "execution_realism_mode": payload.get("execution_realism_mode"),
        },
    )


def collect_runtime_arms(
    *,
    data_dir: Path,
    now_utc: dt.datetime | None = None,
    max_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
) -> list[dict[str, Any]]:
    now = now_utc or _utc_now()
    return [
        collect_gate_b_arm(data_dir, now_utc=now, max_age_seconds=max_age_seconds),
        collect_flash_dip_arm(data_dir, now_utc=now),
        collect_vol_event_arm(data_dir),
        collect_mm_verdict_arm(data_dir, now_utc=now),
        collect_aeg_matrix_arm(data_dir),
    ]


def _action_counts(plan: dict[str, Any]) -> dict[str, int]:
    return {str(k): _int(v) for k, v in (plan.get("action_counts") or {}).items()}


def build_runtime_killboard(
    *,
    data_dir: Path,
    repo_root: Path,
    now_utc: dt.datetime | None = None,
    min_samples: int = 30,
    max_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    arms = collect_runtime_arms(data_dir=data_dir, now_utc=now, max_age_seconds=max_age_seconds)
    plan = build_discovery_plan(arms, min_samples=min_samples, now_utc=now)
    counts = _action_counts(plan)
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
        "killboard": {
            "is_fast_discovery_active": active_arm_count >= 3 and source_present_count >= 3,
            "active_arm_count": active_arm_count,
            "source_ok_count": source_ok_count,
            "source_present_count": source_present_count,
            "ready_for_aeg_chain": counts.get("READY_FOR_AEG_CHAIN", 0),
            "ready_for_probe": counts.get("READY_FOR_PROBE", 0),
            "run_read_only_capture": counts.get("RUN_READ_ONLY_CAPTURE", 0),
            "wait": counts.get("WAIT", 0),
            "block": counts.get("BLOCK", 0),
            "actionable_alpha_found": counts.get("READY_FOR_AEG_CHAIN", 0) > 0,
            "actionable_probe_found": counts.get("READY_FOR_PROBE", 0) > 0,
        },
        "discovery_plan": plan,
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
        "run_read_only_capture": kb.get("run_read_only_capture"),
        "wait": kb.get("wait"),
        "block": kb.get("block"),
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
    now_utc: dt.datetime | None = None,
    min_samples: int = 30,
    max_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
) -> dict[str, Any]:
    killboard = build_runtime_killboard(
        data_dir=data_dir,
        repo_root=repo_root,
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
    "collect_runtime_arms",
    "run_once",
    "write_runtime_artifacts",
]

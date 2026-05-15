"""
Live halt recovery bridge for Governance pending approvals.

The live drawdown halt is emitted by the Rust pipeline snapshot, while the
Governance recovery gate stores only Python-submitted in-memory requests. This
module turns the shared live snapshot into a deterministic virtual recovery
request and executes the operator-approved recovery action.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LIVE_HALT_REQUEST_ID = "live_halt:drawdown"
LIVE_HALT_SENTINEL_FILENAME = "live_halt_recovery_approved.json"
LIVE_HALT_SNAPSHOT_FILENAME = "pipeline_snapshot_live.json"
LIVE_STATE_FILENAME = "live_state.json"
LIVE_CHECKPOINT_ENGINE_MODES = ("live", "live_demo")


def is_live_halt_recovery_request(request_id: str) -> bool:
    return request_id == LIVE_HALT_REQUEST_ID


def openclaw_data_dir() -> Path:
    return Path(os.environ.get("OPENCLAW_DATA_DIR") or "/tmp/openclaw")


def _snapshot_path() -> Path:
    return openclaw_data_dir() / LIVE_HALT_SNAPSHOT_FILENAME


def _sentinel_path() -> Path:
    return openclaw_data_dir() / LIVE_HALT_SENTINEL_FILENAME


def _live_state_path() -> Path:
    return openclaw_data_dir() / LIVE_STATE_FILENAME


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning("failed to read JSON file %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def _file_mtime_ms(path: Path) -> int:
    try:
        return int(path.stat().st_mtime * 1000)
    except FileNotFoundError:
        return 0


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _nested_get(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _snapshot_drawdown_limit_pct(snapshot: dict[str, Any]) -> float | None:
    candidates = (
        ("risk_manager_config", "limits", "session_drawdown_max_pct"),
        ("risk_manager_config", "limits", "session_drawdown_limit_pct"),
        ("risk", "limits", "session_drawdown_max_pct"),
        ("guardian_config", "max_drawdown_pct"),
        ("max_drawdown_pct",),
    )
    for path in candidates:
        value = _finite_float(_nested_get(snapshot, path))
        if value is not None:
            return value
    return None


def _sentinel_covers_snapshot(snapshot_mtime_ms: int) -> bool:
    sentinel = _read_json_file(_sentinel_path())
    if not sentinel or snapshot_mtime_ms <= 0:
        return False
    approved_at_ms = _finite_float(sentinel.get("approved_at_ms"))
    approved_snapshot_mtime_ms = _finite_float(sentinel.get("snapshot_mtime_ms"))
    return bool(
        (approved_at_ms is not None and int(approved_at_ms) >= snapshot_mtime_ms)
        or (
            approved_snapshot_mtime_ms is not None
            and int(approved_snapshot_mtime_ms) >= snapshot_mtime_ms
        )
    )


def build_live_halt_recovery_request(*, respect_sentinel: bool = True) -> dict[str, Any] | None:
    snapshot = _read_json_file(_snapshot_path())
    if not snapshot or not _truthy(snapshot.get("session_halted")):
        return None

    snapshot_mtime_ms = _file_mtime_ms(_snapshot_path())
    if respect_sentinel and _sentinel_covers_snapshot(snapshot_mtime_ms):
        return None

    drawdown_pct = _finite_float(snapshot.get("session_drawdown_pct"))
    limit_pct = _snapshot_drawdown_limit_pct(snapshot)
    requested_at = _iso_from_ms(snapshot_mtime_ms or _now_ms())

    if drawdown_pct is not None and limit_pct is not None:
        freeze_reason = (
            "Live halt active: reset risk before renew "
            f"(snapshot DD {drawdown_pct:.2f}% / limit {limit_pct:.2f}%)."
        )
    else:
        freeze_reason = "Live halt active: reset risk before renewing signed auth."

    return {
        "request_id": LIVE_HALT_REQUEST_ID,
        "id": LIVE_HALT_REQUEST_ID,
        "status": "pending",
        "recovery_type": "trading_resume",
        "from_state": "LIVE_HALTED",
        "to_state": "LIVE_RECOVERY_READY",
        "requested_by": "rust_live_halt_detector",
        "requested_at": requested_at,
        "created_at": requested_at,
        "reason": "signed auth renewal is auto-revoked until live risk is reset",
        "freeze_reason": freeze_reason,
        "description": (
            "Live halt recovery / 實盤風控解封：批准後會重置 live drawdown baseline、"
            "解除 live halt，然後可重新續期 Signed Auth。"
        ),
        "observation_period_hours": 0,
        "evidence": {
            "engine": "live",
            "checkpoint_engine_modes": list(LIVE_CHECKPOINT_ENGINE_MODES),
            "snapshot_path": str(_snapshot_path()),
            "snapshot_mtime_ms": snapshot_mtime_ms,
            "session_drawdown_pct": drawdown_pct,
            "session_drawdown_limit_pct": limit_pct,
            "paper_paused": _truthy(snapshot.get("paper_paused")),
            "system_mode": snapshot.get("system_mode"),
        },
    }


async def _try_ipc_reset_live() -> dict[str, Any]:
    from .risk_routes import _get_risk_view_client

    client = await _get_risk_view_client()
    return await client.reset_drawdown_baseline("live")


async def _try_ipc_unhalt_live() -> dict[str, Any]:
    from .risk_routes import _get_risk_view_client

    client = await _get_risk_view_client()
    return await client.unhalt_session("live")


def _ipc_result_ok(result: dict[str, Any] | None) -> bool:
    return bool(isinstance(result, dict) and result and result.get("ok", True) is not False)


def _offline_reset_live_state() -> dict[str, Any]:
    path = _live_state_path()
    state = _read_json_file(path)
    if not state:
        return {"ok": False, "reason": "live_state_missing", "path": str(path)}

    balance = _finite_float(state.get("balance"))
    if balance is None or balance < 0:
        return {
            "ok": False,
            "reason": "invalid_live_balance",
            "path": str(path),
            "balance": state.get("balance"),
        }

    before_peak = _finite_float(state.get("peak_balance"))
    state["peak_balance"] = balance
    _write_json_atomic(path, state)
    return {
        "ok": True,
        "path": str(path),
        "balance": balance,
        "previous_peak_balance": before_peak,
        "new_peak_balance": balance,
    }


def _delete_live_checkpoints() -> dict[str, Any]:
    try:
        from . import db_pool
    except Exception as exc:
        return {"ok": False, "reason": f"db_pool_import_failed: {exc}", "deleted_rows": 0}

    try:
        with db_pool.get_pg_conn() as conn:
            if conn is None:
                return {"ok": False, "reason": "db_unavailable", "deleted_rows": 0}
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM trading.paper_state_checkpoint "
                    "WHERE engine_mode IN (%s, %s)",
                    LIVE_CHECKPOINT_ENGINE_MODES,
                )
                deleted_rows = int(cur.rowcount or 0)
            conn.commit()
            return {
                "ok": True,
                "deleted_rows": deleted_rows,
                "engine_modes": list(LIVE_CHECKPOINT_ENGINE_MODES),
            }
    except Exception as exc:
        logger.warning("offline live checkpoint reset failed: %s", exc)
        return {"ok": False, "reason": str(exc), "deleted_rows": 0}


def _offline_reset_persisted_live_drawdown() -> dict[str, Any]:
    state_result = _offline_reset_live_state()
    checkpoint_result = _delete_live_checkpoints()
    return {
        "ok": bool(checkpoint_result.get("ok")),
        "mode": "offline_persisted_state",
        "live_state": state_result,
        "checkpoint": checkpoint_result,
    }


def _write_approval_sentinel(actor_id: str, result: dict[str, Any]) -> None:
    snapshot_mtime_ms = _file_mtime_ms(_snapshot_path())
    payload = {
        "approved_at_ms": _now_ms(),
        "approved_at": _iso_from_ms(_now_ms()),
        "approved_by": actor_id,
        "request_id": LIVE_HALT_REQUEST_ID,
        "snapshot_mtime_ms": snapshot_mtime_ms,
        "result": result,
    }
    _write_json_atomic(_sentinel_path(), payload)


async def approve_live_halt_recovery(actor_id: str) -> dict[str, Any]:
    request = build_live_halt_recovery_request(respect_sentinel=False)
    if request is None:
        return {
            "request_id": LIVE_HALT_REQUEST_ID,
            "status": "not_pending",
            "message": "live_snapshot_not_halted",
        }

    reset_result: dict[str, Any] = {"ok": False, "mode": "ipc"}
    try:
        ipc_reset = await _try_ipc_reset_live()
        reset_result = {"ok": _ipc_result_ok(ipc_reset), "mode": "ipc", "result": ipc_reset}
    except Exception as exc:
        reset_result = {"ok": False, "mode": "ipc", "error": str(exc)}

    offline_result: dict[str, Any] | None = None
    if not reset_result.get("ok"):
        offline_result = _offline_reset_persisted_live_drawdown()

    effective_reset_ok = bool(reset_result.get("ok") or (offline_result or {}).get("ok"))
    if not effective_reset_ok:
        raise RuntimeError(
            "live halt recovery failed: IPC reset failed and offline persisted reset failed"
        )

    unhalt_result: dict[str, Any] = {"ok": False, "mode": "ipc"}
    try:
        ipc_unhalt = await _try_ipc_unhalt_live()
        unhalt_result = {"ok": _ipc_result_ok(ipc_unhalt), "mode": "ipc", "result": ipc_unhalt}
    except Exception as exc:
        unhalt_result = {"ok": False, "mode": "ipc", "error": str(exc)}

    result = {
        "request_id": LIVE_HALT_REQUEST_ID,
        "status": "approved",
        "recovery_type": "trading_resume",
        "reset": reset_result,
        "offline_reset": offline_result,
        "unhalt": unhalt_result,
        "next_step": "renew_signed_auth",
        "request": request,
    }
    _write_approval_sentinel(actor_id, result)
    return result

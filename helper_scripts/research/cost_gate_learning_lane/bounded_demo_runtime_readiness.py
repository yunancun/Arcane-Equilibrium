#!/usr/bin/env python3
"""Read-only bounded Demo runtime readiness guard.

The bounded Demo probe runner should only enter final-window admission after
Demo credentials, connector write-mode, engine safety env, plan scope, and
standing authorization scope are machine-checkable. This helper inspects those
inputs and emits one JSON artifact. It does not validate credentials with
Bybit, mutate runtime state, acquire leases, or submit orders.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "bounded_demo_runtime_readiness_v1"
READY_STATUS = "BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES"
BLOCKED_BY_CREDENTIALS_STATUS = "BOUNDED_DEMO_RUNTIME_BLOCKED_BY_CREDENTIALS"
BLOCKED_BY_CONNECTOR_MODE_STATUS = "BOUNDED_DEMO_RUNTIME_BLOCKED_BY_CONNECTOR_MODE"
BLOCKED_BY_ENGINE_ENV_STATUS = "BOUNDED_DEMO_RUNTIME_BLOCKED_BY_ENGINE_ENV"
BLOCKED_BY_AUTH_OR_PLAN_STATUS = "BOUNDED_DEMO_RUNTIME_BLOCKED_BY_AUTH_OR_PLAN"
BLOCKED_BY_INPUT_STATUS = "BOUNDED_DEMO_RUNTIME_BLOCKED_BY_INPUT"
READY_PLAN_STATUS = "READY_FOR_DEMO_LEARNING_PROBE"
READY_PLAN_GATE_STATUS = "OPERATOR_REVIEW"
ACTIVE_STANDING_AUTH_STATUS = "STANDING_DEMO_AUTHORIZATION_ACTIVE"
DEFAULT_CONNECTOR_ENV_FILE = Path(
    "/home/ncyu/BybitOpenClaw/secrets/environment_files/trading_services.env"
)
DEFAULT_PLAN_JSON = Path(
    "/tmp/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json"
)
DEFAULT_STANDING_AUTH_JSON = Path(
    "/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json"
)
BOUNDARY = (
    "read-only bounded Demo runtime readiness inspection only; no Bybit private "
    "call, no credential validation request, no Decision Lease acquire/release, "
    "no order/cancel/modify, no PG query/write, no runtime/service/env/risk/config "
    "mutation, no writer/adapter enablement, no Cost Gate lowering, no live/mainnet "
    "authority, and no promotion/profit proof"
)

TRUTHY_VALUES = {"1", "true", "yes", "y", "on", "enabled"}
FALSY_VALUES = {"0", "false", "no", "n", "off", "disabled", ""}
SAFE_ENGINE_ENV_EXPECTATIONS = {
    "OPENCLAW_ALLOW_MAINNET": "0",
    "OPENCLAW_ENABLE_PAPER": "0",
    "OPENCLAW_DEMO_LEARNING_LANE_WRITER": "1",
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED": "1",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mode_octal(path: Path) -> str | None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None
    return oct(mode)


def _mtime_utc(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return dt.datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=dt.timezone.utc,
        ).isoformat()
    except OSError:
        return None


def _read_json(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "not_provided"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError:
        return None, "invalid_json"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return None, "not_json_object"
    return payload, None


def _artifact_summary(path: Path | None, payload: dict[str, Any] | None, error: str | None) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "present": payload is not None,
        "read_error": error,
        "sha256": _sha256_file(path),
        "mtime_utc": _mtime_utc(path),
        "schema_version": payload.get("schema_version") if payload else None,
        "status": payload.get("status") if payload else None,
    }


def _strip_env_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _read_env_file(path: Path | None) -> tuple[dict[str, str] | None, str | None]:
    if path is None:
        return None, "not_provided"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"

    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _strip_env_value(value)
    return values, None


def _read_proc_environ(path: Path | None) -> tuple[dict[str, str] | None, str | None]:
    if path is None:
        return None, "not_provided"
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"

    values: dict[str, str] = {}
    for chunk in raw.split(b"\0"):
        if not chunk or b"=" not in chunk:
            continue
        text = chunk.decode("utf-8", errors="replace")
        key, value = text.split("=", 1)
        if key:
            values[key] = value
    return values, None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _default_secrets_dir() -> Path:
    override = os.environ.get("OPENCLAW_SECRETS_DIR")
    if override:
        return Path(override)
    return Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit"


def _mask_api_key(value: str | None) -> str | None:
    text = _str(value)
    if not text:
        return None
    if len(text) <= 8:
        return f"{text[:2]}...{text[-2:]}"
    return f"{text[:6]}...{text[-4:]}"


def _read_text_secret(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8").strip(), None
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{type(exc).__name__}"


def _secret_presence_summary(path: Path) -> dict[str, Any]:
    value, error = _read_text_secret(path)
    return {
        "path": str(path),
        "present": value is not None,
        "read_error": error,
        "nonempty": bool(value),
        "mode_octal": _mode_octal(path) if value is not None else None,
        "value_omitted": True,
    }


def _api_key_summary(
    *,
    path: Path,
    expected_sha256: str | None,
    expected_prefix: str | None,
    require_expected_match: bool,
) -> dict[str, Any]:
    value, error = _read_text_secret(path)
    value_hash = _sha256_text(value) if value else None
    expected_sha = _str(expected_sha256).lower() or None
    expected_prefix_text = _str(expected_prefix) or None
    expected_prefix_hash = (
        _sha256_text(expected_prefix_text)[:12] if expected_prefix_text else None
    )
    sha_match = (
        value_hash == expected_sha
        if value_hash and expected_sha and len(expected_sha) == 64
        else None
    )
    prefix_match = (
        value.startswith(expected_prefix_text)
        if value and expected_prefix_text
        else None
    )
    expected_match = True
    if sha_match is not None:
        expected_match = expected_match and sha_match
    if prefix_match is not None:
        expected_match = expected_match and prefix_match
    if sha_match is None and prefix_match is None:
        expected_match = None

    return {
        "path": str(path),
        "present": value is not None,
        "read_error": error,
        "nonempty": bool(value),
        "mode_octal": _mode_octal(path) if value is not None else None,
        "masked_value": _mask_api_key(value),
        "length": len(value) if value else None,
        "sha256_12": value_hash[:12] if value_hash else None,
        "expected_key_check_provided": bool(expected_sha or expected_prefix_text),
        "expected_sha256_match": sha_match,
        "expected_prefix_match": prefix_match,
        "expected_prefix_len": len(expected_prefix_text) if expected_prefix_text else None,
        "expected_prefix_sha256_12": expected_prefix_hash,
        "expected_key_matches_observed": expected_match,
        "expected_key_match_required": require_expected_match,
    }


def _demo_slot_check(
    *,
    secrets_dir: Path,
    slot: str,
    expected_sha256: str | None,
    expected_prefix: str | None,
    require_expected_match: bool,
) -> dict[str, Any]:
    slot_dir = secrets_dir / slot
    api_key = _api_key_summary(
        path=slot_dir / "api_key",
        expected_sha256=expected_sha256,
        expected_prefix=expected_prefix,
        require_expected_match=require_expected_match,
    )
    api_secret = _secret_presence_summary(slot_dir / "api_secret")
    endpoint_value, endpoint_error = _read_text_secret(slot_dir / "bybit_endpoint")
    endpoint = _str(endpoint_value).lower() or None
    blockers: list[str] = []
    if not api_key["nonempty"]:
        blockers.append("demo_api_key_missing_or_empty")
    if not api_secret["nonempty"]:
        blockers.append("demo_api_secret_missing_or_empty")
    if endpoint != "demo":
        blockers.append("demo_endpoint_not_demo")
    advisory_reasons: list[str] = []
    if api_key["expected_key_matches_observed"] is False:
        advisory_reasons.append("demo_api_key_expected_value_mismatch")
    if api_key["expected_key_matches_observed"] is False and require_expected_match:
        blockers.append("demo_api_key_expected_value_mismatch")
    ready = not blockers
    return {
        "status": "READY" if ready else "BLOCKED",
        "slot": slot,
        "secrets_dir": str(secrets_dir),
        "slot_dir": str(slot_dir),
        "api_key": api_key,
        "api_secret": api_secret,
        "endpoint": {
            "path": str(slot_dir / "bybit_endpoint"),
            "present": endpoint_value is not None,
            "read_error": endpoint_error,
            "value": endpoint,
            "is_demo": endpoint == "demo",
            "mode_octal": _mode_octal(slot_dir / "bybit_endpoint")
            if endpoint_value is not None
            else None,
        },
        "advisory_reasons": advisory_reasons,
        "blocking_reasons": blockers,
        "ready": ready,
    }


def _truthy_env(value: str | None) -> bool | None:
    lowered = _str(value).lower()
    if lowered in TRUTHY_VALUES:
        return True
    if lowered in FALSY_VALUES:
        return False
    return None


def _connector_mode_check(path: Path) -> dict[str, Any]:
    env, error = _read_env_file(path)
    values = env or {}
    mode = _str(values.get("BYBIT_MODE")).lower() or None
    write_enabled = _truthy_env(values.get("BYBIT_CONNECTOR_WRITE_ENABLED"))
    endpoint_ready = mode in {"demo", "live_demo"}
    write_ready = write_enabled is True
    blockers: list[str] = []
    if error:
        blockers.append(f"connector_env_{error}")
    if not endpoint_ready:
        blockers.append("bybit_mode_not_demo")
    if not write_ready:
        blockers.append("bybit_connector_write_not_enabled")
    ready = not blockers
    return {
        "status": "READY" if ready else "BLOCKED",
        "path": str(path),
        "present": env is not None,
        "read_error": error,
        "BYBIT_MODE": mode,
        "BYBIT_CONNECTOR_WRITE_ENABLED": values.get("BYBIT_CONNECTOR_WRITE_ENABLED"),
        "BYBIT_CONNECTOR_WRITE_ENABLED_bool": write_enabled,
        "BYBIT_CONNECTOR_HEALTH_STATE": values.get("BYBIT_CONNECTOR_HEALTH_STATE"),
        "BYBIT_CONNECTOR_CONTRACT_VERSION": values.get(
            "BYBIT_CONNECTOR_CONTRACT_VERSION"
        ),
        "demo_or_live_demo_mode": endpoint_ready,
        "write_enabled": write_ready,
        "blocking_reasons": blockers,
        "ready": ready,
    }


def _candidate_from_side_cell(side_cell_key: str | None) -> dict[str, Any]:
    parts = [part.strip() for part in _str(side_cell_key).split("|")]
    if len(parts) != 3:
        return {"side_cell_key": _str(side_cell_key) or None}
    return {
        "side_cell_key": _str(side_cell_key),
        "strategy_name": parts[0],
        "symbol": parts[1].upper(),
        "side": parts[2],
    }


def _candidate_side_cell(candidate: dict[str, Any]) -> str | None:
    direct = _str(candidate.get("side_cell_key"))
    if direct:
        return direct
    strategy = _str(candidate.get("strategy_name"))
    symbol = _str(candidate.get("symbol")).upper()
    side = _str(candidate.get("side"))
    if strategy and symbol and side:
        return f"{strategy}|{symbol}|{side}"
    return None


def _candidate_from_plan(plan: dict[str, Any], requested_side_cell_key: str | None) -> dict[str, Any]:
    requested = _str(requested_side_cell_key)
    direct = _dict(plan.get("candidate"))
    if direct and (not requested or _candidate_side_cell(direct) == requested):
        return dict(direct)
    for row in _list(plan.get("probe_candidates")):
        if not isinstance(row, dict):
            continue
        if requested and _candidate_side_cell(row) != requested:
            continue
        return dict(row)
    return _candidate_from_side_cell(requested_side_cell_key)


def _candidate_scope_from_auth(auth: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(auth.get("candidate"))
    return {
        "side_cell_key": (
            auth.get("side_cell_key")
            or auth.get("selected_side_cell_key")
            or candidate.get("side_cell_key")
        ),
        "strategy_name": auth.get("strategy_name") or candidate.get("strategy_name"),
        "symbol": auth.get("symbol") or candidate.get("symbol"),
        "side": auth.get("side") or candidate.get("side"),
        "outcome_horizon_minutes": (
            auth.get("outcome_horizon_minutes")
            or candidate.get("outcome_horizon_minutes")
            or candidate.get("dominant_horizon_minutes")
        ),
    }


def _scope_matches_observed(scope: dict[str, Any], observed: dict[str, Any]) -> bool:
    for key, value in scope.items():
        text = _str(value)
        if text and text != _str(observed.get(key)):
            return False
    return True


def _plan_check(
    *,
    plan_path: Path,
    requested_side_cell_key: str | None,
    now_utc: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan, error = _read_json(plan_path)
    artifact = _artifact_summary(plan_path, plan, error)
    candidate = _candidate_from_plan(plan or {}, requested_side_cell_key)
    requested = _str(requested_side_cell_key)
    observed_side_cell = _candidate_side_cell(candidate)
    generated_at = _parse_dt((plan or {}).get("generated_at_utc"))
    blockers: list[str] = []
    if error:
        blockers.append(f"plan_{error}")
    if (plan or {}).get("status") != READY_PLAN_STATUS:
        blockers.append("plan_status_not_ready")
    if (plan or {}).get("gate_status") != READY_PLAN_GATE_STATUS:
        blockers.append("plan_gate_status_not_operator_review")
    if requested and observed_side_cell != requested:
        blockers.append("plan_candidate_mismatch")
    if generated_at and generated_at > now_utc + dt.timedelta(minutes=5):
        blockers.append("plan_generated_in_future")
    ready = not blockers
    return {
        "status": "READY" if ready else "BLOCKED",
        "artifact": artifact,
        "generated_at_utc": generated_at.isoformat() if generated_at else None,
        "candidate": candidate,
        "requested_side_cell_key": requested or None,
        "observed_side_cell_key": observed_side_cell,
        "candidate_matches_requested": None if not requested else observed_side_cell == requested,
        "operator_authorization_id": _dict((plan or {}).get("operator_authorization")).get(
            "authorization_id"
        ),
        "order_authority_field_present": (plan or {}).get("order_authority"),
        "blocking_reasons": blockers,
        "ready": ready,
    }, candidate


def _standing_auth_check(
    *,
    standing_auth_path: Path,
    candidate: dict[str, Any],
    now_utc: dt.datetime,
) -> dict[str, Any]:
    payload, error = _read_json(standing_auth_path)
    artifact = _artifact_summary(standing_auth_path, payload, error)
    data = payload or {}
    scope = _candidate_scope_from_auth(data)
    expires_at = _parse_dt(data.get("expires_at_utc"))
    blockers: list[str] = []
    if error:
        blockers.append(f"standing_auth_{error}")
    if data.get("status") != ACTIVE_STANDING_AUTH_STATUS:
        blockers.append("standing_auth_status_not_active")
    if data.get("demo_only") is not True:
        blockers.append("standing_auth_not_demo_only")
    if _str(data.get("environment")).lower() not in {"demo", "live_demo"}:
        blockers.append("standing_auth_environment_not_demo")
    if expires_at is None:
        blockers.append("standing_auth_expiry_missing_or_invalid")
    elif expires_at <= now_utc:
        blockers.append("standing_auth_expired")
    if not _scope_matches_observed(scope, candidate):
        blockers.append("standing_auth_candidate_scope_mismatch")
    ready = not blockers
    return {
        "status": "READY" if ready else "BLOCKED",
        "artifact": artifact,
        "standing_authorization_id": data.get("standing_authorization_id")
        or data.get("authorization_id"),
        "operator_id": data.get("operator_id"),
        "environment": data.get("environment"),
        "scope": data.get("scope") or data.get("authorization_scope"),
        "demo_only": data.get("demo_only"),
        "expires_at_utc": expires_at.isoformat() if expires_at else None,
        "candidate_scope": scope,
        "candidate_scope_matches_plan": _scope_matches_observed(scope, candidate),
        "blocking_reasons": blockers,
        "ready": ready,
    }


def _engine_env_check(
    *,
    environ_file: Path | None,
    require_engine_env: bool,
    expected_plan_path: Path,
) -> dict[str, Any]:
    env, error = _read_proc_environ(environ_file)
    values = env or {}
    blockers: list[str] = []
    if error != "not_provided":
        if error:
            blockers.append(f"engine_env_{error}")
        for key, expected in SAFE_ENGINE_ENV_EXPECTATIONS.items():
            if values.get(key) != expected:
                blockers.append(f"engine_env_{key}_not_{expected}")
        observed_plan = values.get("OPENCLAW_DEMO_LEARNING_LANE_PLAN")
        if observed_plan != str(expected_plan_path):
            blockers.append("engine_env_plan_path_mismatch")
    elif require_engine_env:
        blockers.append("engine_env_not_provided")
    ready = not blockers
    return {
        "status": "READY" if ready else "BLOCKED",
        "path": str(environ_file) if environ_file else None,
        "present": env is not None,
        "read_error": error,
        "required": require_engine_env,
        "expected": {
            **SAFE_ENGINE_ENV_EXPECTATIONS,
            "OPENCLAW_DEMO_LEARNING_LANE_PLAN": str(expected_plan_path),
        },
        "observed": {
            key: values.get(key)
            for key in (
                *SAFE_ENGINE_ENV_EXPECTATIONS.keys(),
                "OPENCLAW_DEMO_LEARNING_LANE_PLAN",
            )
        },
        "blocking_reasons": blockers,
        "ready": ready,
    }


def _state_transition(status: str) -> str:
    if status == READY_STATUS:
        return "DONE_WITH_CONCERNS"
    return "BLOCKED_BY_RUNTIME"


def _top_status(checks: dict[str, dict[str, Any]]) -> str:
    if not checks["engine_env"]["ready"]:
        return BLOCKED_BY_ENGINE_ENV_STATUS
    if not checks["demo_api_slot"]["ready"]:
        return BLOCKED_BY_CREDENTIALS_STATUS
    if not checks["connector_mode"]["ready"]:
        return BLOCKED_BY_CONNECTOR_MODE_STATUS
    if not checks["plan"]["ready"] or not checks["standing_authorization"]["ready"]:
        return BLOCKED_BY_AUTH_OR_PLAN_STATUS
    return READY_STATUS


def build_bounded_demo_runtime_readiness(
    *,
    secrets_dir: Path,
    slot: str = "demo",
    connector_env_file: Path = DEFAULT_CONNECTOR_ENV_FILE,
    plan_json: Path = DEFAULT_PLAN_JSON,
    standing_auth_json: Path = DEFAULT_STANDING_AUTH_JSON,
    candidate_side_cell_key: str | None = None,
    expected_demo_api_key_sha256: str | None = None,
    expected_demo_api_key_prefix: str | None = None,
    require_expected_demo_api_key_match: bool = False,
    engine_environ_file: Path | None = None,
    require_engine_env: bool = False,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now_utc or _utc_now()
    if slot != "demo":
        status = BLOCKED_BY_INPUT_STATUS
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": now.isoformat(),
            "status": status,
            "profit_first_state_transition": _state_transition(status),
            "blocking_reasons": ["slot_must_be_demo"],
            "candidate": _candidate_from_side_cell(candidate_side_cell_key),
            "checks": {},
            "answers": _answers(final_window_ready=False),
            "boundary": BOUNDARY,
        }

    plan_check, candidate = _plan_check(
        plan_path=plan_json,
        requested_side_cell_key=candidate_side_cell_key,
        now_utc=now,
    )
    checks = {
        "engine_env": _engine_env_check(
            environ_file=engine_environ_file,
            require_engine_env=require_engine_env,
            expected_plan_path=plan_json,
        ),
        "demo_api_slot": _demo_slot_check(
            secrets_dir=secrets_dir,
            slot=slot,
            expected_sha256=expected_demo_api_key_sha256,
            expected_prefix=expected_demo_api_key_prefix,
            require_expected_match=require_expected_demo_api_key_match,
        ),
        "connector_mode": _connector_mode_check(connector_env_file),
        "plan": plan_check,
        "standing_authorization": _standing_auth_check(
            standing_auth_path=standing_auth_json,
            candidate=candidate,
            now_utc=now,
        ),
    }
    status = _top_status(checks)
    blocking_reasons: list[str] = []
    for name, check in checks.items():
        for reason in _list(check.get("blocking_reasons")):
            blocking_reasons.append(f"{name}:{reason}")
    final_window_ready = status == READY_STATUS
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "profit_first_state_transition": _state_transition(status),
        "candidate": candidate,
        "checks": checks,
        "blocking_reasons": blocking_reasons,
        "next_actions": _next_actions(status),
        "answers": _answers(
            final_window_ready=final_window_ready,
            require_expected_demo_api_key_match=require_expected_demo_api_key_match,
        ),
        "boundary": BOUNDARY,
    }


def _answers(
    *,
    final_window_ready: bool,
    require_expected_demo_api_key_match: bool = False,
) -> dict[str, Any]:
    return {
        "bounded_demo_runtime_readiness_inspected": True,
        "bounded_demo_final_window_prerequisites_ready": final_window_ready,
        "expected_demo_api_key_match_required": require_expected_demo_api_key_match,
        "order_capable_action_allowed_by_this_packet": False,
        "decision_lease_acquire_performed": False,
        "runtime_mutation_performed": False,
        "service_restart_performed": False,
        "env_mutation_performed": False,
        "risk_config_mutation_performed": False,
        "writer_enabled_by_this_packet": False,
        "adapter_enabled_by_this_packet": False,
        "bybit_private_call_performed": False,
        "bybit_credential_validation_call_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "order_submission_performed": False,
        "order_cancel_performed": False,
        "order_modify_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "live_or_mainnet": False,
        "live_authority_granted": False,
        "promotion_evidence": False,
        "promotion_proof": False,
    }


def _next_actions(status: str) -> list[str]:
    if status == READY_STATUS:
        return [
            "refresh final-window BBO/instrument evidence",
            "runner-acquire short Decision Lease in the final execution window",
            "verify Guardian/Rust authority gates and GUI/Rust RiskConfig cap",
            "only then allow the bounded Demo runner to attempt an order",
        ]
    if status == BLOCKED_BY_CREDENTIALS_STATUS:
        return [
            "replace/validate the Demo API slot through the approved settings API path",
            "keep live/mainnet disabled and do not write secrets from chat",
            "rerun this readiness guard before final-window gates",
        ]
    if status == BLOCKED_BY_CONNECTOR_MODE_STATUS:
        return [
            "switch connector config to Demo write-enabled only through the approved runtime config path",
            "restart/sync services only after operator-approved Demo-only config is present",
            "rerun this readiness guard before final-window gates",
        ]
    if status == BLOCKED_BY_ENGINE_ENV_STATUS:
        return [
            "restore Demo-only engine env without enabling mainnet or paper",
            "verify the engine plan override points at the bounded Demo soak plan",
            "rerun this readiness guard before final-window gates",
        ]
    if status == BLOCKED_BY_AUTH_OR_PLAN_STATUS:
        return [
            "refresh standing Demo authorization through loss-control review if expired or mismatched",
            "materialize a bounded Demo soak plan only after plan-inclusion gates pass",
            "rerun this readiness guard before final-window gates",
        ]
    return ["fix invalid readiness input and rerun"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secrets-dir", type=Path, default=_default_secrets_dir())
    parser.add_argument("--slot", default="demo")
    parser.add_argument("--connector-env-file", type=Path, default=DEFAULT_CONNECTOR_ENV_FILE)
    parser.add_argument("--plan-json", type=Path, default=DEFAULT_PLAN_JSON)
    parser.add_argument("--standing-auth-json", type=Path, default=DEFAULT_STANDING_AUTH_JSON)
    parser.add_argument("--candidate-side-cell-key")
    parser.add_argument("--expected-demo-api-key-sha256")
    parser.add_argument("--expected-demo-api-key-prefix")
    parser.add_argument(
        "--require-expected-demo-api-key-match",
        action="store_true",
        help=(
            "Treat expected Demo API key sha/prefix mismatch as a blocker. Without "
            "this, expected key mismatch is advisory so stale operator hints do not "
            "block an otherwise present Demo slot."
        ),
    )
    parser.add_argument("--engine-environ-file", type=Path)
    parser.add_argument("--require-engine-env", action="store_true")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    packet = build_bounded_demo_runtime_readiness(
        secrets_dir=args.secrets_dir,
        slot=args.slot,
        connector_env_file=args.connector_env_file,
        plan_json=args.plan_json,
        standing_auth_json=args.standing_auth_json,
        candidate_side_cell_key=args.candidate_side_cell_key,
        expected_demo_api_key_sha256=args.expected_demo_api_key_sha256,
        expected_demo_api_key_prefix=args.expected_demo_api_key_prefix,
        require_expected_demo_api_key_match=args.require_expected_demo_api_key_match,
        engine_environ_file=args.engine_environ_file,
        require_engine_env=args.require_engine_env,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json or not args.json_output:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

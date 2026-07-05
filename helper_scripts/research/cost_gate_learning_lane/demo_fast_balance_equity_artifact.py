#!/usr/bin/env python3
"""Build a Demo account-equity artifact from the fast Rust snapshot balance.

The artifact is a source-only input for GUI-risk-cap resolution. Capture mode is
restricted to GET /api/v1/strategy/demo/balance?fast=1 on approved local control
API bases. It never calls Bybit, reads or writes PG, submits/cancels/modifies
orders, mutates risk/config/runtime, lowers the Cost Gate, or grants authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_str/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_str as _str,
    utc_now as _utc_now,
)


SCHEMA_VERSION = "demo_account_equity_artifact_v1"
READY_STATUS = "DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY"
NOT_READY_STATUS = "DEMO_FAST_BALANCE_EQUITY_ARTIFACT_NOT_READY_NO_AUTHORITY"
INPUT_REQUIRED_STATUS = "DEMO_FAST_BALANCE_EQUITY_ARTIFACT_INPUT_REQUIRED_NO_AUTHORITY"
SOURCE_FAILURE_STATUS = "DEMO_FAST_BALANCE_EQUITY_ARTIFACT_SOURCE_FAILURE_NO_AUTHORITY"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEMO_FAST_BALANCE_ENDPOINT = "/api/v1/strategy/demo/balance?fast=1"
SOURCE_READ_CONTRACT = (
    "control_api_demo_fast_balance_rust_snapshot_only_no_bybit_no_pg"
)
APPROVED_API_BASES = {
    "http://100.91.109.86:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
}
DEFAULT_API_BASE = "http://127.0.0.1:8000"
DEFAULT_TOKEN_FILE = Path(
    "program_code/exchange_connectors/bybit_connector/control_api_v1/"
    ".secrets/api_token"
)
USER_AGENT = "openclaw-demo-fast-balance-equity-artifact/1.0"

BOUNDARY = (
    "Demo fast-balance equity artifact only; fixed local control API GET "
    "/api/v1/strategy/demo/balance?fast=1 or supplied captured response; no "
    "Bybit call, Bybit private call, PG query/write, order, cancel, modify, "
    "config/risk/runtime/env/service/crontab mutation, global Cost Gate "
    "lowering, probe authority, order authority, live/mainnet authority, or "
    "promotion proof"
)

DANGER_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "canonical_plan_mutation_performed",
    "config_mutation_performed",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "mainnet_authority_granted",
    "operator_authorization_object_emitted",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}

EQUITY_FIELDS = (
    "totalEquity",
    "total_equity",
    "equity",
    "balance",
    "totalWalletBalance",
    "total_wallet_balance",
    "walletBalance",
    "wallet_balance",
)
SNAPSHOT_FILENAMES = (
    "pipeline_snapshot_demo.json",
    "pipeline_snapshot.json",
    "pipeline_snapshot_paper.json",
)
DEFAULT_RUNTIME_SNAPSHOT_STALE_SECONDS = 60.0

NowFn = Callable[[], dt.datetime]
Opener = Callable[..., Any]


class SourcePolicyError(ValueError):
    """Raised before any Control API GET when source policy is not satisfied."""


class _RedirectRefusedHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"redirect refused: {msg}",
            headers,
            fp,
        )


def urlopen_no_redirect(req: urllib.request.Request, timeout: float) -> Any:
    opener = urllib.request.build_opener(_RedirectRefusedHandler)
    return opener.open(req, timeout=timeout)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
            "enabled",
            "grant",
            "granted",
            "authorize",
            "authorized",
        }
    return False


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _round_decimal(value: Decimal | None, places: int = 8) -> float | None:
    if value is None:
        return None
    quant = Decimal("1").scaleb(-places)
    return float(value.quantize(quant))


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _authority_preserved(*payloads: Any) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    stack: list[Any] = list(payloads)
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        data = _dict(item)
        if not data:
            continue
        adjustment = data.get("main_cost_gate_adjustment")
        if adjustment not in (None, "", "NONE"):
            reasons.append("main_cost_gate_adjustment_not_none")
        for key in DANGER_KEYS:
            if _truthy(data.get(key)):
                reasons.append(f"{key}_true")
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return not reasons, sorted(set(reasons))


def _payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    return _dict(payload.get("data"))


def _extract_equity_usdt(data: dict[str, Any]) -> tuple[Decimal | None, str | None]:
    for field in EQUITY_FIELDS:
        equity = _dec(data.get(field))
        if equity is not None:
            return equity, field
    return None, None


def _validate_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], Decimal | None, str | None, list[str]]:
    reasons: list[str] = []
    if not payload:
        return {}, None, None, ["balance_payload_required"]
    data = _payload_data(payload)
    if not data:
        reasons.append("balance_payload_data_missing")
    if payload.get("action_result") != "success":
        reasons.append("balance_payload_action_result_not_success")
    if payload.get("is_simulated") is not True:
        reasons.append("balance_payload_is_simulated_not_true")
    if payload.get("data_category") != "paper_simulated":
        reasons.append("balance_payload_data_category_not_paper_simulated")
    if _str(data.get("source")) != "rust_engine":
        reasons.append("balance_data_source_not_rust_engine")
    if _str(data.get("read_model")) != "rust_snapshot_fast":
        reasons.append("balance_data_read_model_not_rust_snapshot_fast")
    if _str(data.get("pipeline_status")) != "connected":
        reasons.append("balance_data_pipeline_status_not_connected")
    equity, equity_field = _extract_equity_usdt(data)
    if equity is None or equity <= 0:
        reasons.append("balance_data_equity_missing_or_non_positive")
    return data, equity, equity_field, sorted(set(reasons))


def _path_metadata(path: Path, now: dt.datetime) -> dict[str, Any]:
    try:
        st = path.stat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    meta: dict[str, Any] = {
        "path": str(path),
        "exists": True,
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
        "mode": oct(stat.S_IMODE(st.st_mode)),
        "mtime_utc": _iso(dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc)),
        "age_seconds": round(max(0.0, now.timestamp() - st.st_mtime), 3),
    }
    return meta


def _engine_snapshot_summary(data: dict[str, Any]) -> dict[str, Any]:
    paper_state = _dict(data.get("paper_state"))
    return {
        "source": data.get("source"),
        "schema_version": data.get("schema_version"),
        "trading_mode": data.get("trading_mode"),
        "system_mode": data.get("system_mode"),
        "paper_paused": data.get("paper_paused"),
        "paper_state_present": bool(paper_state),
        "paper_state_balance_present": paper_state.get("balance") is not None,
        "paper_state_initial_balance_present": (
            paper_state.get("initial_balance") is not None
        ),
        "paper_state_peak_balance_present": paper_state.get("peak_balance") is not None,
        "paper_state_positions_count": len(_dict(paper_state.get("positions"))),
    }


def _snapshot_metadata(
    path: Path,
    *,
    now: dt.datetime,
    stale_seconds: float,
) -> dict[str, Any]:
    meta = _path_metadata(path, now)
    meta["stale_seconds"] = stale_seconds
    meta["stale"] = (
        meta.get("exists") is True
        and isinstance(meta.get("age_seconds"), (int, float))
        and float(meta["age_seconds"]) > stale_seconds
    )
    if meta.get("exists") is True and meta.get("is_file") is True:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            meta["summary"] = _engine_snapshot_summary(_dict(raw))
        except Exception as exc:
            meta["read_error"] = f"{type(exc).__name__}: {_str(exc)[:160]}"
    return meta


def _bybit_secret_slot_diagnostics(
    root: Path | None,
    *,
    now: dt.datetime,
) -> dict[str, Any]:
    if root is None:
        return {"provided": False}
    result: dict[str, Any] = {
        "provided": True,
        "root": _path_metadata(root, now),
        "slot_names": [],
        "disabled_demo_slot_names": [],
        "active_demo_slot": None,
    }
    if not root.exists() or not root.is_dir():
        return result

    slot_names = [p.name for p in sorted(root.iterdir(), key=lambda item: item.name)]
    result["slot_names"] = slot_names
    result["disabled_demo_slot_names"] = [
        name
        for name in slot_names
        if name.startswith("demo.") or name.startswith("demo_")
    ]

    demo_slot = root / "demo"
    active = _path_metadata(demo_slot, now)
    child_names: list[str] = []
    children: dict[str, Any] = {}
    if demo_slot.exists() and demo_slot.is_dir():
        for child in sorted(demo_slot.iterdir(), key=lambda item: item.name):
            child_names.append(child.name)
            children[child.name] = _path_metadata(child, now)
    active["child_names"] = child_names
    active["children"] = children
    active["required_file_names_present"] = {
        "api_key": "api_key" in child_names,
        "api_secret": "api_secret" in child_names,
    }
    result["active_demo_slot"] = active
    return result


def build_runtime_diagnostics(
    *,
    runtime_data_dir: Path | None = None,
    bybit_secret_root: Path | None = None,
    snapshot_stale_seconds: float = DEFAULT_RUNTIME_SNAPSHOT_STALE_SECONDS,
    now_fn: NowFn = _utc_now,
) -> dict[str, Any]:
    now = now_fn().astimezone(dt.timezone.utc)
    stale_seconds = max(0.0, float(snapshot_stale_seconds))
    diagnostics: dict[str, Any] = {
        "schema_version": "demo_fast_balance_runtime_diagnostics_v1",
        "generated_at_utc": _iso(now),
        "provided": runtime_data_dir is not None or bybit_secret_root is not None,
        "runtime_data_dir": (
            _path_metadata(runtime_data_dir, now)
            if runtime_data_dir is not None
            else {"provided": False}
        ),
        "snapshot_stale_seconds": stale_seconds,
        "snapshots": {},
        "bybit_secret_slots": _bybit_secret_slot_diagnostics(
            bybit_secret_root,
            now=now,
        ),
        "answers": {
            "secret_values_read": False,
            "secret_values_written": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
            "bybit_call_performed": False,
            "order_submission_performed": False,
        },
    }
    if runtime_data_dir is not None:
        diagnostics["snapshots"] = {
            name: _snapshot_metadata(
                runtime_data_dir / name,
                now=now,
                stale_seconds=stale_seconds,
            )
            for name in SNAPSHOT_FILENAMES
        }
    return diagnostics


def _runtime_diagnostic_blocking_reasons(
    runtime_diagnostics: dict[str, Any] | None,
    validation_reasons: list[str],
) -> list[str]:
    diagnostics = _dict(runtime_diagnostics)
    if diagnostics.get("provided") is not True:
        return []

    reasons: list[str] = []
    runtime_dir = _dict(diagnostics.get("runtime_data_dir"))
    if runtime_dir and runtime_dir.get("provided") is not False:
        if runtime_dir.get("exists") is False:
            reasons.append("runtime_data_dir_missing")
        elif runtime_dir.get("is_dir") is not True:
            reasons.append("runtime_data_dir_not_directory")

    snapshots = _dict(diagnostics.get("snapshots"))
    demo_snapshot = _dict(snapshots.get("pipeline_snapshot_demo.json"))
    if snapshots:
        if demo_snapshot.get("exists") is False:
            reasons.append("demo_snapshot_missing")
        elif demo_snapshot.get("is_file") is not True:
            reasons.append("demo_snapshot_not_file")
        else:
            if demo_snapshot.get("stale") is True:
                reasons.append("demo_snapshot_stale")
            if demo_snapshot.get("read_error"):
                reasons.append("demo_snapshot_unreadable")
            summary = _dict(demo_snapshot.get("summary"))
            if not summary.get("paper_state_present"):
                reasons.append("demo_snapshot_paper_state_missing")
            if not summary.get("paper_state_balance_present"):
                reasons.append("demo_snapshot_paper_state_balance_missing")
            if (
                "balance_data_pipeline_status_not_connected" in validation_reasons
                and summary.get("paper_state_balance_present") is True
            ):
                reasons.append("api_payload_disconnected_but_demo_snapshot_has_balance")

    secret_slots = _dict(diagnostics.get("bybit_secret_slots"))
    if secret_slots.get("provided") is True:
        root = _dict(secret_slots.get("root"))
        if root.get("exists") is False:
            reasons.append("bybit_secret_root_missing")
        elif root.get("is_dir") is not True:
            reasons.append("bybit_secret_root_not_directory")
        active = _dict(secret_slots.get("active_demo_slot"))
        if active.get("exists") is False:
            reasons.append("active_demo_secret_slot_missing")
        elif active.get("is_dir") is not True:
            reasons.append("active_demo_secret_slot_not_directory")
        else:
            required = _dict(active.get("required_file_names_present"))
            if required.get("api_key") is not True or required.get("api_secret") is not True:
                reasons.append("active_demo_secret_slot_missing_required_files")
    return sorted(set(reasons))


def _build_packet(
    *,
    balance_payload: dict[str, Any] | None,
    control_api_call_performed: bool,
    api_base: str | None,
    source_transport: dict[str, Any],
    now_fn: NowFn,
    runtime_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now_fn().astimezone(dt.timezone.utc)
    payload = _dict(balance_payload)
    data, equity, equity_field, validation_reasons = _validate_payload(payload)
    authority_ok, authority_reasons = _authority_preserved(payload)
    runtime_reasons = _runtime_diagnostic_blocking_reasons(
        runtime_diagnostics,
        validation_reasons,
    )
    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_balance_payload"
    elif _dict(source_transport).get("transport_status") == "failure":
        status = SOURCE_FAILURE_STATUS
        reason = "demo_fast_balance_transport_failure"
    elif not payload:
        status = INPUT_REQUIRED_STATUS
        reason = "demo_fast_balance_payload_required"
    elif validation_reasons or runtime_reasons:
        status = NOT_READY_STATUS
        reason = (
            "demo_fast_balance_runtime_diagnostics_not_accepted"
            if runtime_reasons and not validation_reasons
            else "demo_fast_balance_payload_not_accepted"
        )
    else:
        status = READY_STATUS
        reason = "demo_fast_balance_equity_artifact_ready"

    blocking_reasons = sorted(
        set(validation_reasons + authority_reasons + runtime_reasons)
    )
    packet = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso(now),
        "status": status,
        "reason": reason,
        "environment": "demo",
        "source_endpoint": DEMO_FAST_BALANCE_ENDPOINT,
        "source_method": "GET",
        "source_api_base": api_base,
        "source_read_contract": SOURCE_READ_CONTRACT,
        "source_transport": source_transport,
        "payload": payload,
        "payload_sha256": _json_sha256(payload) if payload else None,
        "payload_checks": {
            "action_result": payload.get("action_result"),
            "is_simulated": payload.get("is_simulated"),
            "data_category": payload.get("data_category"),
            "data_source": data.get("source"),
            "read_model": data.get("read_model"),
            "pipeline_status": data.get("pipeline_status"),
            "equity_field": equity_field,
            "blocking_reasons": blocking_reasons,
            "runtime_diagnostic_blocking_reasons": runtime_reasons,
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
        },
        "runtime_diagnostics": runtime_diagnostics or {"provided": False},
        "equity": {
            "equity_usdt": _round_decimal(equity, 8),
            "source_field": equity_field,
        },
        "answers": {
            "source_only_research_artifact": True,
            "control_api_call_performed": bool(control_api_call_performed),
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "bybit_public_market_data_call_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "runtime_mutation_performed": False,
            "risk_mutation_performed": False,
            "cap_envelope_mutation_allowed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }
    packet["artifact_self_hash_sha256"] = _json_sha256(packet)
    return packet


def build_demo_account_equity_artifact(
    *,
    balance_payload: dict[str, Any] | None,
    now_fn: NowFn = _utc_now,
    runtime_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_packet(
        balance_payload=balance_payload,
        control_api_call_performed=False,
        api_base=None,
        source_transport={"transport_status": "not_performed", "source": "supplied_json"},
        now_fn=now_fn,
        runtime_diagnostics=runtime_diagnostics,
    )


def _normalize_api_base_url(api_base: str) -> str:
    parts = urllib.parse.urlsplit(_str(api_base).rstrip("/"))
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError("api base must not include path, query, or fragment")
    normalized = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    if normalized not in APPROVED_API_BASES:
        raise ValueError(f"unapproved control API base: {normalized or '<empty>'}")
    return normalized


def _read_token(
    token_file: Path | None,
    *,
    forbid_env_token: bool = False,
) -> tuple[str | None, dict[str, Any]]:
    env_token = _str(os.environ.get("OPENCLAW_API_TOKEN"))
    path = token_file or DEFAULT_TOKEN_FILE
    meta: dict[str, Any] = {
        "token_source": "none",
        "env_token_present": bool(env_token),
        "env_token_allowed": not forbid_env_token,
        "env_token_used": False,
        "token_file_path": str(path),
        "token_file_exists": path.exists(),
        "token_file_used": False,
    }
    if env_token and forbid_env_token:
        raise SourcePolicyError(
            "OPENCLAW_API_TOKEN present while env token fallback is forbidden"
        )
    if env_token:
        meta["token_source"] = "environment"
        meta["env_token_used"] = True
        return env_token, meta
    if not path.exists():
        return None, meta
    mode = stat.S_IMODE(path.stat().st_mode)
    meta["token_file_mode"] = oct(mode)
    if mode & 0o077:
        raise SourcePolicyError(f"token file permissions too broad: {path}")
    token = _str(path.read_text(encoding="utf-8"))
    if token:
        meta["token_source"] = "token_file"
        meta["token_file_used"] = True
        return token, meta
    return None, meta


def fetch_demo_fast_balance(
    *,
    api_base: str,
    token_file: Path | None = None,
    forbid_env_token: bool = False,
    timeout_seconds: float = 5.0,
    opener: Opener = urlopen_no_redirect,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_base = _normalize_api_base_url(api_base)
    url = f"{normalized_base}{DEMO_FAST_BALANCE_ENDPOINT}"
    token, token_meta = _read_token(token_file, forbid_env_token=forbid_env_token)
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with opener(req, timeout=timeout_seconds) as response:
        raw = response.read()
        status_code = response.getcode()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("demo fast balance response was not a JSON object")
    return payload, {
        "transport_status": "success",
        "http_status": status_code,
        "api_base": normalized_base,
        "endpoint": DEMO_FAST_BALANCE_ENDPOINT,
        "method": "GET",
        "authorization_header_used": bool(token),
        **token_meta,
    }


def capture_demo_fast_balance_equity_artifact(
    *,
    api_base: str = DEFAULT_API_BASE,
    token_file: Path | None = None,
    forbid_env_token: bool = False,
    timeout_seconds: float = 5.0,
    opener: Opener = urlopen_no_redirect,
    now_fn: NowFn = _utc_now,
    runtime_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        normalized_base = _normalize_api_base_url(api_base)
    except Exception as exc:
        return _build_packet(
            balance_payload=None,
            control_api_call_performed=False,
            api_base=None,
            source_transport={
                "transport_status": "failure",
                "api_base": None,
                "endpoint": DEMO_FAST_BALANCE_ENDPOINT,
                "method": "GET",
                "error_class": type(exc).__name__,
                "error": _str(exc)[:240],
            },
            now_fn=now_fn,
            runtime_diagnostics=runtime_diagnostics,
        )
    try:
        payload, transport = fetch_demo_fast_balance(
            api_base=normalized_base,
            token_file=token_file,
            forbid_env_token=forbid_env_token,
            timeout_seconds=timeout_seconds,
            opener=opener,
        )
    except Exception as exc:
        call_performed = not isinstance(exc, SourcePolicyError)
        return _build_packet(
            balance_payload=None,
            control_api_call_performed=call_performed,
            api_base=normalized_base,
            source_transport={
                "transport_status": "failure",
                "api_base": normalized_base,
                "endpoint": DEMO_FAST_BALANCE_ENDPOINT,
                "method": "GET",
                "env_token_present": bool(_str(os.environ.get("OPENCLAW_API_TOKEN"))),
                "env_token_allowed": not forbid_env_token,
                "token_file_path": str(token_file or DEFAULT_TOKEN_FILE),
                "error_class": type(exc).__name__,
                "error": _str(exc)[:240],
            },
            now_fn=now_fn,
            runtime_diagnostics=runtime_diagnostics,
        )
    return _build_packet(
        balance_payload=payload,
        control_api_call_performed=True,
        api_base=normalized_base,
        source_transport=transport,
        now_fn=now_fn,
        runtime_diagnostics=runtime_diagnostics,
    )


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_outputs(packet: dict[str, Any], json_output: Path | None, print_json: bool) -> None:
    text = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if json_output:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(text, encoding="utf-8")
    if print_json or not json_output:
        print(text, end="")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--balance-response-json", type=Path)
    source.add_argument("--capture", action="store_true")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--forbid-env-token", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--runtime-data-dir", type=Path)
    parser.add_argument("--bybit-secret-root", type=Path)
    parser.add_argument("--runtime-diagnostics-json", type=Path)
    parser.add_argument(
        "--runtime-snapshot-stale-seconds",
        type=float,
        default=DEFAULT_RUNTIME_SNAPSHOT_STALE_SECONDS,
    )
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    runtime_diagnostics = _read_json(args.runtime_diagnostics_json)
    if runtime_diagnostics is None and (
        args.runtime_data_dir is not None or args.bybit_secret_root is not None
    ):
        runtime_diagnostics = build_runtime_diagnostics(
            runtime_data_dir=args.runtime_data_dir,
            bybit_secret_root=args.bybit_secret_root,
            snapshot_stale_seconds=args.runtime_snapshot_stale_seconds,
        )
    if args.capture:
        packet = capture_demo_fast_balance_equity_artifact(
            api_base=args.api_base,
            token_file=args.token_file,
            forbid_env_token=args.forbid_env_token,
            timeout_seconds=max(0.1, float(args.timeout_seconds)),
            runtime_diagnostics=runtime_diagnostics,
        )
    else:
        packet = build_demo_account_equity_artifact(
            balance_payload=_read_json(args.balance_response_json),
            runtime_diagnostics=runtime_diagnostics,
        )
    _write_outputs(packet, args.json_output, args.print_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

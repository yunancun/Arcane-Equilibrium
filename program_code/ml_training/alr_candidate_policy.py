"""
MODULE_NOTE
模塊用途：驗證並 provision ALR candidate arbiter 的 canonical static policy。
主要函數：validate_candidate_policy_configuration、provision_candidate_policy。
依賴：標準庫與 alr_safe_file。
硬邊界：decision clock 只由 consumer 注入；policy 缺失、漂移或權限過寬必 fail-closed。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ml_training.alr_safe_file import AlrSafeFileError, read_bounded_regular_file


ALGORITHM_VERSION = "candidate_learning_arbiter_v1"
TIE_BREAK_VERSION = "candidate_learning_tie_break_v1"
Q18_SCALE = 18
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_POLICY_KEYS = {
    "algorithm_version",
    "tie_break_version",
    "q18_scale",
    "thresholds",
    "row_budget",
    "byte_budget",
    "collection_window_days",
    "max_new_entries_per_window",
    "cooldown_seconds",
    "unknown_portfolio_penalty",
    "policy_config_hash",
}
_TEMPLATE_SCHEMA_VERSION = "alr_candidate_arbiter_policy_template_v1"
_TEMPLATE_KEYS = _POLICY_KEYS | {"schema_version"}
_BUDGET_KEYS = (
    "row_budget",
    "byte_budget",
    "collection_window_days",
    "max_new_entries_per_window",
)


class CandidatePolicyError(ValueError):
    """Static policy 無法安全供 candidate arbiter 使用。"""


def load_candidate_policy_template(path: str | Path) -> dict[str, Any]:
    """讀取不可直接 provision、且不含 production budget default 的 template。"""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise CandidatePolicyError("policy_template_unavailable") from exc
    template = _decode_mapping(raw)
    if set(template) != _TEMPLATE_KEYS:
        raise CandidatePolicyError("policy_template_fields_invalid")
    if template.get("schema_version") != _TEMPLATE_SCHEMA_VERSION:
        raise CandidatePolicyError("policy_template_schema_invalid")
    if any(
        template.get(key) is not None
        for key in (*_BUDGET_KEYS, "policy_config_hash")
    ):
        raise CandidatePolicyError("policy_template_contains_production_defaults")
    fixed = {
        key: value
        for key, value in template.items()
        if key not in {*_BUDGET_KEYS, "policy_config_hash", "schema_version"}
    }
    if fixed != {
        "algorithm_version": ALGORITHM_VERSION,
        "tie_break_version": TIE_BREAK_VERSION,
        "q18_scale": Q18_SCALE,
        "thresholds": {
            "e1_n_eff_min": 30,
            "e2_utc_days_min": 5,
            "e3_top_day_share_max": "0.5",
            "e4_censored_share_max": "0.3",
        },
        "cooldown_seconds": 1_800,
        "unknown_portfolio_penalty": "1",
    }:
        raise CandidatePolicyError("policy_template_fixed_semantics_invalid")
    return template


def render_candidate_policy_configuration(
    template: Mapping[str, Any],
    *,
    row_budget: int,
    byte_budget: int,
    collection_window_days: int,
    max_new_entries_per_window: int,
) -> dict[str, Any]:
    """只用 caller 明示的四項 budget render production policy 並重算 hash。"""
    if not isinstance(template, Mapping) or set(template) != _TEMPLATE_KEYS:
        raise CandidatePolicyError("policy_template_fields_invalid")
    if template.get("schema_version") != _TEMPLATE_SCHEMA_VERSION:
        raise CandidatePolicyError("policy_template_schema_invalid")
    if any(
        template.get(key) is not None
        for key in (*_BUDGET_KEYS, "policy_config_hash")
    ):
        raise CandidatePolicyError("policy_template_contains_production_defaults")
    budgets = {
        "row_budget": row_budget,
        "byte_budget": byte_budget,
        "collection_window_days": collection_window_days,
        "max_new_entries_per_window": max_new_entries_per_window,
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in budgets.values()
    ):
        raise CandidatePolicyError("provision_budgets_required")
    policy = {
        key: copy.deepcopy(value)
        for key, value in template.items()
        if key not in {*_BUDGET_KEYS, "policy_config_hash", "schema_version"}
    }
    policy.update(budgets)
    policy["policy_config_hash"] = _canonical_hash(policy)
    return validate_candidate_policy_configuration(policy)


def validate_candidate_policy_configuration(
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """驗證 frozen gates、bounded resources 與 stable config hash。"""
    if not isinstance(policy, Mapping) or set(policy) != _POLICY_KEYS:
        raise CandidatePolicyError("policy_fields_invalid")
    normalized = copy.deepcopy(dict(policy))
    if (
        normalized["algorithm_version"] != ALGORITHM_VERSION
        or normalized["tie_break_version"] != TIE_BREAK_VERSION
        or normalized["q18_scale"] != Q18_SCALE
    ):
        raise CandidatePolicyError("policy_version_invalid")
    thresholds = normalized["thresholds"]
    if not isinstance(thresholds, Mapping) or dict(thresholds) != {
        "e1_n_eff_min": 30,
        "e2_utc_days_min": 5,
        "e3_top_day_share_max": "0.5",
        "e4_censored_share_max": "0.3",
    }:
        raise CandidatePolicyError("policy_thresholds_invalid")
    for key in _BUDGET_KEYS:
        value = normalized[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise CandidatePolicyError("policy_resource_budget_invalid")
    if normalized["cooldown_seconds"] != 1_800:
        raise CandidatePolicyError("policy_cooldown_invalid")
    unknown_penalty_raw = normalized["unknown_portfolio_penalty"]
    if not isinstance(unknown_penalty_raw, str):
        raise CandidatePolicyError("policy_unknown_penalty_invalid")
    try:
        unknown_penalty = Decimal(unknown_penalty_raw)
    except (InvalidOperation, ValueError) as exc:
        raise CandidatePolicyError("policy_unknown_penalty_invalid") from exc
    if (
        not unknown_penalty.is_finite()
        or not Decimal("0") <= unknown_penalty <= Decimal("1")
        or unknown_penalty_raw != _canonical_decimal_string(unknown_penalty)
    ):
        raise CandidatePolicyError("policy_unknown_penalty_invalid")
    supplied_hash = normalized["policy_config_hash"]
    stable_config = {
        key: value for key, value in normalized.items() if key != "policy_config_hash"
    }
    if (
        not isinstance(supplied_hash, str)
        or _HASH_RE.fullmatch(supplied_hash) is None
        or supplied_hash != _canonical_hash(stable_config)
    ):
        raise CandidatePolicyError("policy_config_hash_invalid")
    return normalized


def check_provisioned_candidate_policy(path: str | Path) -> dict[str, Any]:
    """檢查 private destination；缺失或 mode/內容漂移一律阻止 service preflight。"""
    policy_path = Path(path)
    if not policy_path.exists():
        raise CandidatePolicyError("provisioned_policy_missing")
    _validate_policy_parent(policy_path.parent)
    try:
        raw = read_bounded_regular_file(
            policy_path,
            max_bytes=65_536,
            require_nonempty=True,
            require_private_mode=True,
        )
    except AlrSafeFileError as exc:
        raise CandidatePolicyError("provisioned_policy_invalid") from exc
    return validate_candidate_policy_configuration(_decode_mapping(raw))


def provision_candidate_policy(
    template_path: str | Path,
    destination_path: str | Path,
    *,
    apply: bool,
    row_budget: int,
    byte_budget: int,
    collection_window_days: int,
    max_new_entries_per_window: int,
) -> dict[str, Any]:
    """預設 dry-run；目的檔缺失時只回報，絕不隱式 provision。"""
    if not isinstance(apply, bool):
        raise CandidatePolicyError("provision_apply_invalid")
    template = load_candidate_policy_template(template_path)
    rendered_policy = render_candidate_policy_configuration(
        template,
        row_budget=row_budget,
        byte_budget=byte_budget,
        collection_window_days=collection_window_days,
        max_new_entries_per_window=max_new_entries_per_window,
    )
    destination = Path(destination_path)
    if not destination.exists():
        if apply:
            _write_private_policy(destination, rendered_policy)
            provisioned = check_provisioned_candidate_policy(destination)
            if provisioned != rendered_policy:
                raise CandidatePolicyError("provisioned_policy_drift")
            return _provision_result(
                status="PROVISIONED",
                template=rendered_policy,
                destination=destination,
                service_preflight_ready=True,
                destination_write_performed=True,
            )
        return _provision_result(
            status="DRY_RUN_PROVISION_REQUIRED",
            template=rendered_policy,
            destination=destination,
            service_preflight_ready=False,
            destination_write_performed=False,
        )
    provisioned = check_provisioned_candidate_policy(destination)
    if provisioned != rendered_policy:
        raise CandidatePolicyError("provisioned_policy_drift")
    return _provision_result(
        status="ALREADY_PROVISIONED",
        template=rendered_policy,
        destination=destination,
        service_preflight_ready=True,
        destination_write_performed=False,
    )


def _provision_result(
    *,
    status: str,
    template: Mapping[str, Any],
    destination: Path,
    service_preflight_ready: bool,
    destination_write_performed: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "alr_candidate_policy_provision_v1",
        "status": status,
        "policy_config_hash": template["policy_config_hash"],
        "rendered_policy": copy.deepcopy(dict(template)),
        "destination": str(destination),
        "service_preflight_ready": service_preflight_ready,
        "destination_write_performed": destination_write_performed,
        "policy_file_mutation_performed": destination_write_performed,
        "runtime_process_mutation_performed": False,
        "service_unit_mutation_performed": False,
    }


def _write_private_policy(destination: Path, policy: Mapping[str, Any]) -> None:
    parent = destination.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_stat = parent.lstat()
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or stat.S_ISLNK(parent_stat.st_mode)
        or parent_stat.st_mode & 0o077
    ):
        raise CandidatePolicyError("policy_parent_not_private")
    raw = (
        json.dumps(
            policy,
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    temp_path: Path | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=".alr-policy-", dir=parent)
        temp_path = Path(temp_name)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # hard-link 保證 no-replace；已存在的 policy 必須走顯式 drift 處理。
        os.link(temp_path, destination)
        temp_path.unlink()
        temp_path = None
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as exc:
        raise CandidatePolicyError("provisioned_policy_collision") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _validate_policy_parent(parent: Path) -> None:
    try:
        metadata = parent.lstat()
    except OSError as exc:
        raise CandidatePolicyError("policy_parent_not_private") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_mode & 0o022
    ):
        raise CandidatePolicyError("policy_parent_not_private")


def _decode_mapping(raw: bytes) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non_finite:{value}")

    try:
        payload = json.loads(raw, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CandidatePolicyError("policy_json_invalid") from exc
    if not isinstance(payload, dict):
        raise CandidatePolicyError("policy_json_invalid")
    return payload


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_decimal_string(value: Decimal) -> str:
    if value == Decimal("0"):
        return "0"
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def main(argv: list[str] | None = None) -> int:
    """提供 dry-run provision 與 unit 外部 pre-apply semantic check。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-provisioned", type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--row-budget", type=int)
    parser.add_argument("--byte-budget", type=int)
    parser.add_argument("--collection-window-days", type=int)
    parser.add_argument("--max-new-entries-per-window", type=int)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        if arguments.check_provisioned is not None:
            if (
                arguments.template is not None
                or arguments.destination is not None
                or arguments.apply
                or any(
                    value is not None
                    for value in (
                        arguments.row_budget,
                        arguments.byte_budget,
                        arguments.collection_window_days,
                        arguments.max_new_entries_per_window,
                    )
                )
            ):
                raise CandidatePolicyError("policy_cli_mode_invalid")
            policy = check_provisioned_candidate_policy(arguments.check_provisioned)
            result = {
                "schema_version": "alr_candidate_policy_provision_v1",
                "status": "PROVISIONED_POLICY_READY",
                "policy_config_hash": policy["policy_config_hash"],
                "destination": str(arguments.check_provisioned),
                "service_preflight_ready": True,
                "destination_write_performed": False,
                "policy_file_mutation_performed": False,
                "runtime_process_mutation_performed": False,
                "service_unit_mutation_performed": False,
            }
        else:
            if arguments.template is None or arguments.destination is None:
                raise CandidatePolicyError("policy_cli_mode_invalid")
            if any(
                value is None
                for value in (
                    arguments.row_budget,
                    arguments.byte_budget,
                    arguments.collection_window_days,
                    arguments.max_new_entries_per_window,
                )
            ):
                raise CandidatePolicyError("provision_budgets_required")
            result = provision_candidate_policy(
                arguments.template,
                arguments.destination,
                apply=arguments.apply,
                row_budget=arguments.row_budget,
                byte_budget=arguments.byte_budget,
                collection_window_days=arguments.collection_window_days,
                max_new_entries_per_window=arguments.max_new_entries_per_window,
            )
    except (CandidatePolicyError, OSError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "alr_candidate_policy_provision_v1",
                    "status": "POLICY_PREFLIGHT_FAILED",
                    "reason": str(exc),
                    "service_preflight_ready": False,
                    "destination_write_performed": False,
                    "policy_file_mutation_performed": False,
                    "runtime_process_mutation_performed": False,
                    "service_unit_mutation_performed": False,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["service_preflight_ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

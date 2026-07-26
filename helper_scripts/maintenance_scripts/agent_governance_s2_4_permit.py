#!/usr/bin/env python3
"""S2.4(WP4·W4a)§9 時間/授權預算葉——三條 TTL 不等式與「過期後只剩安全清理」的權限收斂。

§9 的三條不等式各有自己的 bound 集合,絕不互相代替:

```text
APPLY   apply_budget + postcheck_duration + postcheck_sample_interval + rollback_budget
        + safety_margin
        <= min(install_intent, operator_authorization, pg_migration_authorization,
               topology_attestation, installed_unit_probe_receipt, prepared_bundle,
               dependency_effect_receipt 的 remaining TTL)

PREPARE fetch_budget + build_import_budget + prepare_postcheck + prepare_rollback
        + safety_margin
        <= min(PREPARE SSHSIG, terminal PREPARE_SANDBOX probe receipt, target platform,
               source dependency 的 remaining TTL)

PROBE   probe + cleanup + independent_postcheck + safety_margin
        <= min(該 probe 自己的 SSHSIG remaining TTL)
```

「一個 3600 秒的操作不能在 900 秒的 permit 下執行」由 :func:`derive_ttl_budget_status` 逐項
再導出;term/bound 的鍵集是 **exact set**(缺項或夾帶額外項都是 typed 拒——少一項就等於偷偷
放寬不等式)。

§10.5 #10 的另一半:**apply 期間過期**。過期禁止「新建立/恢復觀測」,但**不得**阻擋安全
清理——:func:`derive_post_expiry_operation_status` 把這條規則變成一個可測的封閉表,
:func:`derive_expiry_during_apply_status` 則把「過期即補償、過期永不把部分 apply 變成成功」
收斂成 typed 結果。

本葉零主機動作、零 I/O;九 authority 恆 false。
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402

# ── §9 的三組 exact term/bound 集 ─────────────────────────────────────────────
APPLY_TTL_BUDGET_TERMS = (
    "apply_budget",
    "postcheck_duration",
    "postcheck_sample_interval",
    "rollback_budget",
    "safety_margin",
)
APPLY_TTL_BOUND_TERMS = (
    "dependency_effect_receipt_remaining_ttl",
    "install_intent_remaining_ttl",
    "installed_unit_probe_receipt_remaining_ttl",
    "operator_authorization_remaining_ttl",
    "pg_migration_authorization_remaining_ttl",
    "prepared_bundle_remaining_ttl",
    "topology_attestation_remaining_ttl",
)
PREPARE_TTL_BUDGET_TERMS = (
    "build_import_budget",
    "fetch_budget",
    "prepare_postcheck",
    "prepare_rollback",
    "safety_margin",
)
# §9:PREPARE 只被 PREPARE SSHSIG、terminal PREPARE_SANDBOX probe receipt、target platform
# 與 source dependency 的 TTL 界定——**不**依賴 final unit / PG topology / HBA delta / W6B permit。
PREPARE_TTL_BOUND_TERMS = (
    "prepare_authorization_remaining_ttl",
    "prepare_sandbox_probe_receipt_remaining_ttl",
    "source_dependency_remaining_ttl",
    "target_platform_remaining_ttl",
)
PROBE_TTL_BUDGET_TERMS = (
    "cleanup",
    "independent_postcheck",
    "probe",
    "safety_margin",
)
PROBE_TTL_BOUND_TERMS = ("probe_authorization_remaining_ttl",)
TTL_PHASES = {
    "APPLY": (APPLY_TTL_BUDGET_TERMS, APPLY_TTL_BOUND_TERMS),
    "PREPARE": (PREPARE_TTL_BUDGET_TERMS, PREPARE_TTL_BOUND_TERMS),
    "PROBE": (PROBE_TTL_BUDGET_TERMS, PROBE_TTL_BOUND_TERMS),
}
# §9.1:APPLY/PG permit 上限 900 秒、時鐘偏移 60 秒(PROBE/PREPARE 沿用同一保守上限)。
MAX_PERMIT_TTL_SECONDS = 900
PERMIT_CLOCK_SKEW_SECONDS = 60

TTL_STATUS_SATISFIED = "TTL_BUDGET_SATISFIED"
TTL_STATUS_EXCEEDED = "TTL_BUDGET_EXCEEDED"
TTL_STATUS_REJECTED = "TTL_BUDGET_REJECTED"
TTL_TYPED_STATUSES = (TTL_STATUS_EXCEEDED, TTL_STATUS_REJECTED, TTL_STATUS_SATISFIED)

# ── §10.5 #10 / §5.2:過期後只剩 exact 安全清理權 ───────────────────────────────
POST_EXPIRY_SAFETY_OPERATIONS = (
    "bounded_cgroup_drain",
    "compensate_task_owned_delta",
    "independent_residue_postcheck",
    "journal_transition",
    "reset_failed",
    "staging_delta_removal",
    "transient_unit_remove",
    "transient_unit_stop",
)
POST_EXPIRY_FORBIDDEN_OPERATIONS = (
    "credential_install",
    "daemon_reload",
    "observation_resume",
    "pg_role_acl_migration",
    "publish_tree",
    "resume_apply",
    "staging_create",
    "transient_unit_create",
    "unit_fragment_install",
)
POST_EXPIRY_STATUS_AUTHORIZED = "OPERATION_AUTHORIZED"
POST_EXPIRY_STATUS_SAFETY_ONLY = "POST_EXPIRY_SAFETY_CLEANUP_AUTHORIZED"
POST_EXPIRY_STATUS_FORBIDDEN = "POST_EXPIRY_OPERATION_FORBIDDEN"
POST_EXPIRY_STATUS_UNKNOWN = "UNKNOWN_OPERATION_FORBIDDEN"
EXPIRY_DURING_APPLY_STATUS_COMPENSATE = "EXPIRY_DURING_APPLY_COMPENSATE"
EXPIRY_DURING_APPLY_STATUS_LIVE = "PERMIT_LIVE"
EXPIRY_DURING_APPLY_STATUS_RECOVERY = "RECOVERY_REQUIRED"


class PermitBudgetError(ValueError):
    """§9 預算契約層硬錯誤(帶 typed ``code``)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _nonnegative_number_reasons(payload: Any, terms: tuple[str, ...], label: str) -> list[str]:
    """exact 鍵集 + 每項為非負有限數;缺項/多項/負值/非數一律 typed 拒。"""

    if not isinstance(payload, dict):
        return [f"{label} must be an object of {list(terms)}"]
    reasons: list[str] = []
    present = set(str(key) for key in payload)
    expected = set(terms)
    if present != expected:
        reasons.append(
            f"{label} key set is not the exact §9 term set (extra="
            f"{sorted(present - expected)}, missing={sorted(expected - present)}); a missing "
            "term silently loosens the inequality"
        )
    for term in sorted(present & expected):
        value = payload[term]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            reasons.append(f"{label}[{term!r}] must be a number of seconds")
        elif value < 0:
            reasons.append(f"{label}[{term!r}] must not be negative")
        elif value != value or value in (float("inf"), float("-inf")):  # NaN/inf
            reasons.append(f"{label}[{term!r}] must be finite")
    return reasons


def derive_ttl_budget_status(
    phase: Any, *, budget: Any, remaining_ttls: Any
) -> dict[str, Any]:
    """§9:該 phase 的預算總和是否 ``<=`` 其**所有**證據 remaining TTL 的最小值。

    回 ``{"status": TTL_BUDGET_SATISFIED|TTL_BUDGET_EXCEEDED|TTL_BUDGET_REJECTED,
    "reasons": [...], "required_seconds": …, "available_seconds": …, "binding_evidence": …}``。

    ``TTL_BUDGET_REJECTED`` 保留給「形狀不成立」(未知 phase、term 集不 exact、負值/非數);
    ``TTL_BUDGET_EXCEEDED`` 才是不等式本身不成立(§9:3600 秒的操作不能在 900 秒 permit 下跑)。
    """

    verdict: dict[str, Any] = {
        "schema_version": "s2_4_ttl_budget_verdict_v1_informal",
        "status": TTL_STATUS_REJECTED,
        "reasons": [],
        "phase": phase,
        "required_seconds": None,
        "available_seconds": None,
        "binding_evidence": None,
    }
    terms = TTL_PHASES.get(str(phase))
    if terms is None:
        verdict["reasons"] = [
            f"{phase!r} is not one of the three §9 budget phases {sorted(TTL_PHASES)}"
        ]
        return verdict
    budget_terms, bound_terms = terms
    reasons = _nonnegative_number_reasons(budget, budget_terms, f"{phase} budget")
    reasons += _nonnegative_number_reasons(
        remaining_ttls, bound_terms, f"{phase} remaining TTLs"
    )
    if reasons:
        verdict["reasons"] = reasons
        return verdict
    required = sum(float(budget[term]) for term in budget_terms)
    binding_evidence = min(bound_terms, key=lambda term: float(remaining_ttls[term]))
    available = float(remaining_ttls[binding_evidence])
    verdict["required_seconds"] = required
    verdict["available_seconds"] = available
    verdict["binding_evidence"] = binding_evidence
    if required > available:
        verdict["status"] = TTL_STATUS_EXCEEDED
        verdict["reasons"] = [
            f"{phase} needs {required:g}s but only {available:g}s remain on "
            f"{binding_evidence}; §9 forbids running the operation (expiry during apply "
            "triggers compensation and never converts a partial apply into success)"
        ]
        return verdict
    verdict["status"] = TTL_STATUS_SATISFIED
    return verdict


def derive_permit_ttl_ceiling_status(
    authorization: Any, *, max_ttl_seconds: int = MAX_PERMIT_TTL_SECONDS
) -> dict[str, Any]:
    """§9.1:單張 permit 的 ``expires_at - issued_at`` 不得超過 profile 上限。"""

    verdict: dict[str, Any] = {
        "status": TTL_STATUS_REJECTED, "reasons": [], "ttl_seconds": None
    }
    if not isinstance(authorization, dict):
        verdict["reasons"] = ["permit must be an object"]
        return verdict
    try:
        issued = central_validator._parse_timestamp(authorization["issued_at"])
        expires = central_validator._parse_timestamp(authorization["expires_at"])
    except (KeyError, TypeError, ValueError):
        verdict["reasons"] = ["permit timestamps are invalid"]
        return verdict
    ttl = (expires - issued).total_seconds()
    verdict["ttl_seconds"] = ttl
    if ttl <= 0:
        verdict["reasons"] = ["permit issued_at must precede expires_at"]
        return verdict
    if ttl > max_ttl_seconds:
        verdict["status"] = TTL_STATUS_EXCEEDED
        verdict["reasons"] = [
            f"permit TTL {ttl:g}s exceeds the §9.1 ceiling of {max_ttl_seconds}s"
        ]
        return verdict
    verdict["status"] = TTL_STATUS_SATISFIED
    return verdict


def derive_post_expiry_operation_status(
    *, operation: Any, permit_expired: bool
) -> dict[str, Any]:
    """§10.5 #10 / §5.2:permit 過期後哪些操作仍被授權。

    未過期 → 已知操作一律 ``OPERATION_AUTHORIZED``。過期後:安全清理面(stop / 有界 drain /
    reset-failed / remove / staging delta 移除 / 補償 / journal 轉移 / 獨立殘留 postcheck)
    仍 ``POST_EXPIRY_SAFETY_CLEANUP_AUTHORIZED``——**過期不得阻擋安全清理**;新建立、發佈、
    PG/credential/unit 變更與「恢復觀測/恢復 apply」一律 ``POST_EXPIRY_OPERATION_FORBIDDEN``。
    表外的操作名回 ``UNKNOWN_OPERATION_FORBIDDEN``(fail-closed,絕不默認放行)。
    """

    name = str(operation)
    known = name in POST_EXPIRY_SAFETY_OPERATIONS or name in POST_EXPIRY_FORBIDDEN_OPERATIONS
    if not known:
        return {
            "status": POST_EXPIRY_STATUS_UNKNOWN,
            "operation": name,
            "reasons": [
                f"{name!r} is not in the closed post-expiry operation table; fail-closed"
            ],
        }
    if not permit_expired:
        return {"status": POST_EXPIRY_STATUS_AUTHORIZED, "operation": name, "reasons": []}
    if name in POST_EXPIRY_SAFETY_OPERATIONS:
        return {
            "status": POST_EXPIRY_STATUS_SAFETY_ONLY,
            "operation": name,
            "reasons": [
                "the permit expired during execution; only the exact safety-cleanup authority "
                "remains, and expiry can never block that cleanup (§5.2)"
            ],
        }
    return {
        "status": POST_EXPIRY_STATUS_FORBIDDEN,
        "operation": name,
        "reasons": [
            "the permit expired during execution; expiry forbids new creation, publication and "
            "observation/apply resumption (§10.5 #10)"
        ],
    }


def derive_expiry_during_apply_status(
    *,
    permit_expires_at: Any,
    observed_now: Any,
    mutation_performed: bool,
    compensation_available: bool = True,
) -> dict[str, Any]:
    """§9/§10.5 #10:apply 期間過期的 typed 收斂。

    過期 + 已變更 + 有補償權(rollback digest 授權的 task-owned delta)→
    ``EXPIRY_DURING_APPLY_COMPENSATE``;過期 + 已變更但**沒有**可用補償 →
    ``RECOVERY_REQUIRED``;未過期 → ``PERMIT_LIVE``。過期永不把部分 apply 變成成功。
    """

    verdict: dict[str, Any] = {
        "schema_version": "s2_4_expiry_during_apply_verdict_v1_informal",
        "status": EXPIRY_DURING_APPLY_STATUS_RECOVERY,
        "reasons": [],
        "permit_expired": None,
        "apply_may_resume": False,
        "safety_cleanup_authorized": True,
        "converts_partial_apply_to_success": False,
    }
    try:
        expires = central_validator._parse_timestamp(permit_expires_at)
        now = central_validator._parse_timestamp(
            observed_now if isinstance(observed_now, str) else _iso_or_raise(observed_now)
        )
    except (TypeError, ValueError):
        verdict["reasons"] = [
            "expiry-during-apply requires a parseable permit expiry and observed clock "
            "(fail-closed)"
        ]
        return verdict
    expired = now >= expires
    verdict["permit_expired"] = expired
    if not expired:
        verdict["status"] = EXPIRY_DURING_APPLY_STATUS_LIVE
        verdict["apply_may_resume"] = True
        return verdict
    if not mutation_performed:
        verdict["status"] = EXPIRY_DURING_APPLY_STATUS_COMPENSATE
        verdict["reasons"] = [
            "the permit expired before any mutation; there is no delta to compensate and no "
            "new creation or observation may start (§10.5 #10)"
        ]
        return verdict
    if compensation_available:
        verdict["status"] = EXPIRY_DURING_APPLY_STATUS_COMPENSATE
        verdict["reasons"] = [
            "the permit expired mid-apply; the signed rollback digest still authorizes "
            "compensation of exactly this journal's task-owned delta, and expiry never "
            "converts a partial apply into success (§9)"
        ]
        return verdict
    verdict["reasons"] = [
        "the permit expired mid-apply and no exact compensation authority is available; "
        "RECOVERY_REQUIRED blocks S2.5 and the installed service stays disabled/inactive"
    ]
    return verdict


def _iso_or_raise(value: Any) -> str:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(
            timezone.utc
        ).isoformat()
    raise TypeError("observed_now must be an ISO-8601 string or datetime")


def permit_abi_projection() -> dict[str, Any]:
    """W4 exported-ABI 折入的 §9 預算/過期面。"""

    return {
        "apply_ttl_budget_terms": list(APPLY_TTL_BUDGET_TERMS),
        "apply_ttl_bound_terms": list(APPLY_TTL_BOUND_TERMS),
        "prepare_ttl_budget_terms": list(PREPARE_TTL_BUDGET_TERMS),
        "prepare_ttl_bound_terms": list(PREPARE_TTL_BOUND_TERMS),
        "probe_ttl_budget_terms": list(PROBE_TTL_BUDGET_TERMS),
        "probe_ttl_bound_terms": list(PROBE_TTL_BOUND_TERMS),
        "max_permit_ttl_seconds": MAX_PERMIT_TTL_SECONDS,
        "permit_clock_skew_seconds": PERMIT_CLOCK_SKEW_SECONDS,
        "post_expiry_safety_operations": list(POST_EXPIRY_SAFETY_OPERATIONS),
        "post_expiry_forbidden_operations": list(POST_EXPIRY_FORBIDDEN_OPERATIONS),
        "ttl_typed_statuses": list(TTL_TYPED_STATUSES),
    }

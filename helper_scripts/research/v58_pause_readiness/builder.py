"""Pure builder for V5.8 pause readiness summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import RUNNER_VERSION, SUMMARY_SCHEMA_VERSION


@dataclass(frozen=True)
class RequiredFile:
    check_id: str
    path: str
    label: str


REQUIRED_DESIGN_FILES: tuple[RequiredFile, ...] = (
    RequiredFile("design.main_plan", "docs/execution_plan/2026-05-20--execution-plan-v5.8.md", "V5.8 main plan"),
    RequiredFile("design.v58_preservation", "docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--v58_design_progress_preservation_audit.md", "V5.8 preservation audit"),
    RequiredFile("design.v59_changelog", "CHANGELOG.md", "v5.9 freeze changelog"),
    RequiredFile("design.m1", "docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md", "M1 LAL spec"),
    RequiredFile("design.m2", "docs/execution_plan/2026-05-21--m2_overlay_state_machine_design_spec.md", "M2 overlay spec"),
    RequiredFile("design.m3", "docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md", "M3 health spec"),
    RequiredFile("design.m4", "docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md", "M4 hypothesis spec"),
    RequiredFile("design.m5", "docs/execution_plan/2026-05-21--m5_online_learning_design_spec.md", "M5 online learning spec"),
    RequiredFile("design.m6", "docs/execution_plan/2026-05-21--m6_bayesian_reward_weight_design_spec.md", "M6 reward spec"),
    RequiredFile("design.m7", "docs/execution_plan/2026-05-21--m7_decay_enforced_design_spec.md", "M7 decay spec"),
    RequiredFile("design.m8", "docs/execution_plan/2026-05-21--m8_anomaly_detection_design_spec.md", "M8 anomaly spec"),
    RequiredFile("design.m9", "docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md", "M9 A/B spec"),
    RequiredFile("design.m10", "docs/execution_plan/2026-05-21--m10_discovery_tier_design_spec.md", "M10 discovery spec"),
    RequiredFile("design.m11", "docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md", "M11 replay spec"),
    RequiredFile("design.m12", "docs/execution_plan/2026-05-21--m12_order_router_design_spec.md", "M12 order router spec"),
    RequiredFile("design.m13", "docs/execution_plan/2026-05-21--m13_asset_class_venue_design_spec.md", "M13 asset/venue spec"),
    RequiredFile("design.m7_v116", "docs/execution_plan/specs/2026-05-31--v116-m7-decay-detector-spec.md", "M7 V116 detector spec"),
)

REQUIRED_GOVERNANCE_FILES: tuple[RequiredFile, ...] = (
    RequiredFile("gov.adr0034", "docs/adr/0034-decision-lease-layered-approval-lal.md", "ADR-0034 M1 LAL"),
    RequiredFile("gov.adr0035", "docs/adr/0035-m5-online-learning-interface-reserved.md", "ADR-0035 M5"),
    RequiredFile("gov.adr0036", "docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md", "ADR-0036 M8/M10"),
    RequiredFile("gov.adr0037", "docs/adr/0037-m9-ab-framework-and-statistical-methodology.md", "ADR-0037 M9"),
    RequiredFile("gov.adr0038", "docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md", "ADR-0038 M11"),
    RequiredFile("gov.adr0039", "docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md", "ADR-0039 M12"),
    RequiredFile("gov.adr0040", "docs/adr/0040-multi-venue-gate-spec.md", "ADR-0040 M13"),
    RequiredFile("gov.adr0042", "docs/adr/0042-m3-health-monitoring.md", "ADR-0042 M3"),
    RequiredFile("gov.adr0043", "docs/adr/0043-m6-bayesian-reward-weight.md", "ADR-0043 M6"),
    RequiredFile("gov.adr0044", "docs/adr/0044-m7-decay-enforced-single-authority.md", "ADR-0044 M7"),
    RequiredFile("gov.adr0045", "docs/adr/0045-m4-hypothesis-discovery-governance.md", "ADR-0045 M4"),
    RequiredFile("gov.adr0047", "docs/adr/0047-alpha-edge-regime-evidence-governance.md", "ADR-0047 Alpha-Edge"),
    RequiredFile("gov.amd_alpha_edge", "docs/governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md", "AMD alpha-edge governance"),
    RequiredFile("gov.amd_autonomy", "docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md", "AMD autonomy boundary"),
)

REQUIRED_SOURCE_SURFACES: tuple[RequiredFile, ...] = (
    RequiredFile("source.v099", "sql/migrations/V099__autonomy_level_config.sql", "autonomy level schema"),
    RequiredFile("source.v100", "sql/migrations/V100__m4_hypothesis_base_table.sql", "M4 hypothesis base schema"),
    RequiredFile("source.v103", "sql/migrations/V103__extend_m4_hypothesis_columns.sql", "M4 hypothesis extension"),
    RequiredFile("source.v106", "sql/migrations/V106__health_observations.sql", "M3 health observations schema"),
    RequiredFile("source.v107", "sql/migrations/V107__replay_divergence_log.sql", "M11 replay divergence schema"),
    RequiredFile("source.v109", "sql/migrations/V109__m8_anomaly_events_hypertable.sql", "M8 anomaly events schema"),
    RequiredFile("source.v112", "sql/migrations/V112__decision_lease_lal_tiers.sql", "M1 LAL schema"),
    RequiredFile("source.m1_lal", "rust/openclaw_engine/src/governance/lal/mod.rs", "M1 LAL Rust skeleton"),
    RequiredFile("source.m4_miner", "rust/openclaw_core/src/m4_miner/mod.rs", "M4 miner module"),
    RequiredFile("source.m8_writer", "rust/openclaw_engine/src/database/anomaly_event_writer.rs", "M8 anomaly writer"),
    RequiredFile("source.m13_enum", "rust/openclaw_types/src/asset_venue.rs", "M13 asset/venue enum"),
)


def _read_text(repo_root: Path, relative: str) -> str:
    path = repo_root / relative
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _check_files(repo_root: Path, files: tuple[RequiredFile, ...], *, status_if_missing: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for spec in files:
        path = repo_root / spec.path
        if path.exists():
            checks.append({
                "id": spec.check_id,
                "status": "PASS",
                "message": "required_file_present",
                "path": spec.path,
                "label": spec.label,
            })
        else:
            checks.append({
                "id": spec.check_id,
                "status": status_if_missing,
                "message": "required_file_missing",
                "path": spec.path,
                "label": spec.label,
            })
    return checks


def _text_check(check_id: str, text: str, needles: list[str], message: str, *, path: str, fail_status: str = "FAIL") -> dict[str, Any]:
    missing = [needle for needle in needles if needle not in text]
    return {
        "id": check_id,
        "status": "PASS" if not missing else fail_status,
        "message": message if not missing else f"{message}_missing_terms",
        "path": path,
        "missing_terms": missing,
    }


def _migration_reality(repo_root: Path) -> dict[str, Any]:
    sql_dir = repo_root / "sql" / "migrations"
    names = sorted(path.name for path in sql_dir.glob("V*.sql")) if sql_dir.exists() else []
    by_version = {name.split("__", 1)[0]: name for name in names if "__" in name}
    original_slots = {
        "V105": "M2 overlay original V5.8 slot remains spec-only",
        "V108": "M9 A/B original V5.8 slot remains spec-only",
        "V110": "M6 reward original V5.8 slot remains spec-only",
        "V111": "M10 discovery original V5.8 slot remains spec-only",
        "V113": "Original M7 slot is occupied by later pg_dump event migration",
        "V114": "Original M5 reserve slot is occupied by notification failsafe migration",
        "V115": "Original M12 reserve slot is occupied by basis panel migration",
        "V116": "Current M7 detector spec uses V116, but no sqlx migration is applied yet",
    }
    rows = []
    for version, note in original_slots.items():
        rows.append({
            "version": version,
            "migration_file": by_version.get(version),
            "note": note,
            "status": "DOCUMENTED_DRIFT" if version in {"V113", "V114", "V115"} and by_version.get(version) else "SPEC_ONLY",
        })
    return {
        "latest_sql_file": names[-1] if names else None,
        "original_v58_slots": rows,
        "policy": "Do not replay V5.8 V105-V116 roster as migration plan without PM/MIT review.",
    }


def _gate_watch(path: str | None) -> dict[str, Any]:
    if not path:
        return {
            "path": None,
            "artifact_status": "NOT_PROVIDED",
            "operator_action": "NO_GATE_WATCH_CONTEXT",
            "candidate_counts": {},
            "probe_command_hints": [],
        }
    p = Path(path)
    if not p.exists():
        return {
            "path": str(p),
            "artifact_status": "MISSING",
            "operator_action": "NO_GATE_WATCH_CONTEXT",
            "candidate_counts": {},
            "probe_command_hints": [],
        }
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "path": str(p),
            "artifact_status": "MALFORMED",
            "operator_action": "BLOCKED_MALFORMED_GATE_WATCH",
            "candidate_counts": {},
            "probe_command_hints": [],
        }
    status = str(payload.get("status") or "UNKNOWN")
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    hints = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        action = candidate.get("recommended_action")
        if action not in {"START_GATE_B_NOW", "SCHEDULE_GATE_B_WINDOW"}:
            continue
        symbol = candidate.get("symbol")
        hints.append({
            "symbol": symbol,
            "recommended_action": action,
            "event_time_utc": candidate.get("event_time_utc"),
            "shell": (
                "python helper_scripts/research/aeg_gate_b_probe.py "
                f"--symbol {symbol} --duration-seconds 86400 --mode isolated"
            ) if symbol else None,
        })
    operator_action = {
        "WATCH_ONLY": "WAIT_FOR_ACTIONABLE_WATCH",
        "ACTIONABLE_START_NOW": "START_ISOLATED_24H_PROBE",
        "ACTIONABLE_SCHEDULE": "SCHEDULE_ISOLATED_24H_PROBE",
    }.get(status, "REVIEW_GATE_WATCH_ARTIFACT")
    return {
        "path": str(p),
        "artifact_status": status,
        "operator_action": operator_action,
        "candidate_counts": payload.get("candidate_counts") if isinstance(payload.get("candidate_counts"), dict) else {},
        "generated_at_utc": payload.get("generated_at_utc"),
        "probe_command_hints": hints,
    }


def build_summary(
    *,
    repo_root: str | Path,
    run_id: str,
    gate_watch_latest_json: str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    checks: list[dict[str, Any]] = []
    checks.extend(_check_files(root, REQUIRED_DESIGN_FILES, status_if_missing="FAIL"))
    checks.extend(_check_files(root, REQUIRED_GOVERNANCE_FILES, status_if_missing="FAIL"))
    checks.extend(_check_files(root, REQUIRED_SOURCE_SURFACES, status_if_missing="WARN"))

    todo = _read_text(root, "TODO.md")
    changelog = _read_text(root, "CHANGELOG.md")
    v58_audit = _read_text(root, "docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--v58_design_progress_preservation_audit.md")
    lal = _read_text(root, "rust/openclaw_engine/src/governance/lal/mod.rs")
    m5_stub_test = _read_text(root, "rust/openclaw_engine/tests/m5_model_client_stub_panic.rs")
    m12_stub_test = _read_text(root, "rust/openclaw_engine/tests/m12_order_router_stub.rs")

    checks.append(_text_check(
        "policy.freeze_visible",
        todo + "\n" + changelog + "\n" + v58_audit,
        ["active-IMPL", "凍結", "stage0_ready"],
        "v58_freeze_and_unfreeze_gate_visible",
        path="TODO.md + CHANGELOG.md + v58 audit",
    ))
    checks.append(_text_check(
        "policy.alpha_edge_current",
        todo,
        ["P0-EDGE-1", "listing fade", "NO-GO", "Gate-B"],
        "alpha_edge_current_posture_visible",
        path="TODO.md",
    ))
    checks.append(_text_check(
        "policy.lal_no_silent_autonomy",
        lal,
        ["Tier 2/3/4 transition", "not implemented", "defer to Sprint 4+"],
        "lal_high_tiers_remain_fail_loud",
        path="rust/openclaw_engine/src/governance/lal/mod.rs",
        fail_status="WARN",
    ))
    checks.append(_text_check(
        "policy.m5_m12_stubs_fail_loud",
        m5_stub_test + "\n" + m12_stub_test,
        ["unimplemented", "fail-loud"],
        "m5_m12_interface_stubs_have_fail_loud_tests",
        path="rust/openclaw_engine/tests",
        fail_status="WARN",
    ))

    gate_watch = _gate_watch(gate_watch_latest_json)
    if gate_watch["artifact_status"] in {"MALFORMED"}:
        checks.append({
            "id": "edge.gate_b_watch",
            "status": "FAIL",
            "message": "gate_b_watch_artifact_malformed",
            "path": gate_watch["path"],
        })
    elif gate_watch["artifact_status"] in {"NOT_PROVIDED", "MISSING"}:
        checks.append({
            "id": "edge.gate_b_watch",
            "status": "WARN",
            "message": "gate_b_watch_not_attached_to_pause_packet",
            "path": gate_watch["path"],
        })
    else:
        checks.append({
            "id": "edge.gate_b_watch",
            "status": "PASS",
            "message": "gate_b_watch_context_attached",
            "path": gate_watch["path"],
            "artifact_status": gate_watch["artifact_status"],
            "operator_action": gate_watch["operator_action"],
        })

    fail_count = sum(1 for row in checks if row["status"] == "FAIL")
    warn_count = sum(1 for row in checks if row["status"] == "WARN")
    status = "BLOCKED_MISSING_PAUSE_ASSET" if fail_count else (
        "PASS_PAUSE_READY_WITH_WARNINGS" if warn_count else "PASS_PAUSE_READY"
    )
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "pause_readiness_status": status,
        "counts": {
            "checks": len(checks),
            "pass": sum(1 for row in checks if row["status"] == "PASS"),
            "warn": warn_count,
            "fail": fail_count,
        },
        "checks": checks,
        "migration_reality": _migration_reality(root),
        "gate_watch": gate_watch,
        "unfreeze_gate": {
            "met": False,
            "required": "first net-positive alpha-bearing candidate reaches stage0_ready under AEG/ADR-0047",
            "current_reason": "Current TODO keeps P0-EDGE-1 active; trend and funding-tilt are NO-GO, listing fade awaits fresh Gate-B evidence.",
            "m7_exception": "M7 detector-only work may be separately scoped, but enforcement/autonomy remains frozen.",
        },
        "next_actions": [
            "Keep V5.8 M1-M13 active-IMPL frozen until the stage0_ready gate is met.",
            "Wait for Gate-B ACTIONABLE_* watch; run preflight before any isolated 24h probe.",
            "After a fresh probe, require >=30 matched samples plus E2/MIT/QC review before promotion proof.",
            "Do not replay original V105-V116 migration roster without PM/MIT migration review.",
        ],
        "boundaries": [
            "artifact-only",
            "no DB connection",
            "no exchange call",
            "no runtime restart",
            "no auth/risk/order/trading mutation",
        ],
    }


__all__ = [
    "REQUIRED_DESIGN_FILES",
    "REQUIRED_GOVERNANCE_FILES",
    "REQUIRED_SOURCE_SURFACES",
    "build_summary",
]

#!/usr/bin/env python3
"""Build a source-only candidate/control identity contract.

The contract fixes which future AVAX rows may count as probe proof, which rows
may count as matched controls, and which rows are research-only controls. It
does not query PG, call Bybit, read ledgers, submit orders, lower Cost Gate, or
grant any authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_source_only_control_identity_contract_v1"
READY_STATUS = "SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY"
INPUT_NOT_READY_STATUS = "GAP_CLOSURE_INPUT_NOT_READY"
NO_CANDIDATE_STATUS = "CONTROL_IDENTITY_CANDIDATE_MISSING"
REQUIRED_GAP_NOT_PRESENT_STATUS = "CANDIDATE_MATCHED_CONTROL_GAP_NOT_PRESENT"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

GAP_CLOSURE_SCHEMA_VERSION = (
    "cost_gate_false_negative_evidence_floor_gap_closure_design_v1"
)
GAP_CLOSURE_READY_STATUS = "EVIDENCE_FLOOR_GAP_CLOSURE_DESIGN_READY_NO_AUTHORITY"
REQUIRED_GAP_KEY = "candidate_matched_controls_present"

BOUNDARY = (
    "artifact-only source-only control identity contract; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate "
    "lowering, cap mutation, probe authority, order authority, live authority, "
    "or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "operator_authorization_object_emitted",
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

NON_COUNTABLE_EVIDENCE = [
    "cross_symbol_control_as_candidate_proof",
    "unattributed_fill",
    "cleanup_or_risk_close_fill",
    "local_stale_working_order_row",
    "artifact_count",
    "source_smoke_result",
    "single_window_positive",
    "replay_only_result",
    "flash_dip_buy_demo_fill_for_cost_gate_proof",
]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


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


def _authority_preserved(payload: dict[str, Any] | None) -> bool:
    stack: list[Any] = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        data = _dict(item)
        if not data:
            continue
        if data.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            return False
        for key in AUTHORITY_TRUE_KEYS:
            if _truthy(data.get(key)):
                return False
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return True


def _gap_closure_ready(gap_closure: dict[str, Any]) -> bool:
    return (
        gap_closure.get("schema_version") == GAP_CLOSURE_SCHEMA_VERSION
        and gap_closure.get("status") == GAP_CLOSURE_READY_STATUS
    )


def _candidate(gap_closure: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(gap_closure.get("candidate"))
    if candidate:
        return candidate
    return _dict(gap_closure.get("source_candidate"))


def _candidate_matches_selected(
    candidate: dict[str, Any],
    selected_side_cell_key: str | None,
) -> bool:
    selected = _str(selected_side_cell_key)
    if not selected:
        return True
    return _str(candidate.get("side_cell_key")) == selected


def _required_gap_present(gap_closure: dict[str, Any]) -> bool:
    for item in _list(gap_closure.get("gap_closure_items")):
        data = _dict(item)
        if data.get("gap_key") == REQUIRED_GAP_KEY:
            return True
    return False


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    side_cell_key = _str(candidate.get("side_cell_key"))
    return {
        "side_cell_key": side_cell_key,
        "strategy_name": _str(candidate.get("strategy_name")),
        "symbol": _str(candidate.get("symbol")),
        "side": _str(candidate.get("side")),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
        "identity_rule": (
            "candidate proof rows must match side_cell_key, strategy_name, "
            "symbol, side, and outcome_horizon_minutes exactly"
        ),
    }


def _proof_outcome_identity(candidate_identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "probe_outcome",
        "required_exact_fields": {
            key: candidate_identity.get(key)
            for key in (
                "side_cell_key",
                "strategy_name",
                "symbol",
                "side",
                "outcome_horizon_minutes",
            )
        },
        "required_preconditions": [
            "candidate_scoped_bounded_demo_authorization_existed_before_attempt",
            "pm_e3_bb_order_envelope_review_passed_before_attempt",
            "probe_admission_decision_was_ADMIT_DEMO_LEARNING_PROBE",
            "attempt_id_links_admission_order_and_outcome",
            "fees_slippage_and_maker_taker_labels_present",
            "proof_exclusion_reasons_empty",
        ],
        "forbidden_as_proof": NON_COUNTABLE_EVIDENCE,
    }


def _matched_control_identity(candidate_identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "blocked_signal_outcome",
        "required_exact_fields": {
            key: candidate_identity.get(key)
            for key in (
                "side_cell_key",
                "strategy_name",
                "symbol",
                "side",
                "outcome_horizon_minutes",
            )
        },
        "required_preconditions": [
            "same_side_cell_as_candidate",
            "same_outcome_horizon_as_candidate",
            "point_in_time_signal_timestamp_not_after_probe_outcome_timestamp",
            "realized_net_bps_after_fees_slippage_available",
            "proof_exclusion_reasons_empty_if_fill_backed",
        ],
        "must_not_be": [
            "cross_symbol_control",
            "future_leaked_control",
            "replay_only_control",
            "source_smoke_control",
            "unattributed_or_cleanup_fill_control",
        ],
    }


def _research_control_identity(candidate_identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "allowed_use": [
            "robustness_context",
            "candidate_selection_reopen_evidence",
            "regime_or_breadth_diagnostics",
        ],
        "prohibited_use": [
            "candidate_proof",
            "bounded_probe_proof",
            "cost_gate_proof",
            "promotion_evidence",
            "global_cost_gate_adjustment",
        ],
        "identity_rule": (
            "rows with a different side_cell_key, symbol, strategy_name, side, "
            "or horizon are research controls only for "
            f"{candidate_identity.get('side_cell_key')}"
        ),
    }


def _join_requirements(candidate_identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "probe_join_keys": [
            "side_cell_key",
            "attempt_id",
            "order_link_id_or_openclaw_order_link_id",
            "source_admission_decision",
            "source_artifact_or_ledger_record_id",
        ],
        "matched_control_join_keys": [
            "side_cell_key",
            "outcome_horizon_minutes",
            "signal_timestamp_or_context_timestamp",
            "source_artifact_or_ledger_record_id",
        ],
        "candidate_side_cell_key": candidate_identity.get("side_cell_key"),
        "same_side_cell_control_required": True,
        "cross_symbol_control_counts_as_candidate_proof": False,
    }


def build_source_only_control_identity_contract(
    *,
    gap_closure: dict[str, Any] | None,
    selected_side_cell_key: str | None = None,
    gap_closure_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a no-authority control identity contract from gap closure output."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    payload = _dict(gap_closure)
    authority_preserved = _authority_preserved(payload)
    input_ready = _gap_closure_ready(payload)
    candidate = _candidate(payload)
    candidate_ok = bool(candidate) and _candidate_matches_selected(
        candidate,
        selected_side_cell_key,
    )
    gap_present = _required_gap_present(payload)

    if not authority_preserved:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_gap_closure_input"
    elif not input_ready:
        status = INPUT_NOT_READY_STATUS
        reason = "gap_closure_input_not_ready"
    elif not candidate_ok:
        status = NO_CANDIDATE_STATUS
        reason = "candidate_missing_or_selected_side_cell_mismatch"
    elif not gap_present:
        status = REQUIRED_GAP_NOT_PRESENT_STATUS
        reason = "candidate_matched_control_gap_not_present"
    else:
        status = READY_STATUS
        reason = "source_only_control_identity_contract_ready"

    identity = _candidate_identity(candidate) if status == READY_STATUS else {}
    contract = (
        {
            "candidate_identity": identity,
            "admissible_probe_outcome_identity": _proof_outcome_identity(identity),
            "admissible_matched_control_identity": _matched_control_identity(identity),
            "research_control_identity": _research_control_identity(identity),
            "join_requirements": _join_requirements(identity),
            "proof_exclusion_rule": (
                "unattributed, cleanup/risk-close, stale local, source-smoke, "
                "artifact-count, replay-only, lineage-incomplete, or cross-symbol "
                "rows never count as AVAX proof"
            ),
            "future_result_review_requirements": [
                "run bounded_probe_result_review on candidate-matched future outcomes",
                "require same-side-cell blocked_signal_outcome controls",
                "run proof_exclusion checks before counting any fill-backed row",
                "run execution_realism_review before any Cost Gate or promotion review",
            ],
            "max_safe_next_action": (
                "implement_current_cap_staircase_risk_worksheet_or_review_real_auth_delta"
            ),
        }
        if status == READY_STATUS
        else {}
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_gap_closure": {
            "path": str(gap_closure_path) if gap_closure_path else None,
            "schema_version": payload.get("schema_version"),
            "status": payload.get("status"),
            "gap_count": _dict(payload.get("summary")).get("gap_count"),
            "candidate_matched_control_gap_present": gap_present,
        },
        "candidate": candidate if status == READY_STATUS else {},
        "contract": contract,
        "summary": {
            "contract_ready": status == READY_STATUS,
            "candidate_side_cell_key": identity.get("side_cell_key") if identity else None,
            "same_side_cell_control_required": status == READY_STATUS,
            "cross_symbol_control_counts_as_candidate_proof": False,
            "p0_authorization_required_before_probe": True,
            "max_safe_next_action": (
                contract.get("max_safe_next_action")
                if status == READY_STATUS
                else "refresh_ready_no_authority_gap_closure_design"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "control_identity_contract_ready": status == READY_STATUS,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    candidate = _dict(packet.get("candidate"))
    contract = _dict(packet.get("contract"))
    lines = [
        "# Source-Only Control Identity Contract",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Contract",
        "",
    ]
    for section in (
        "candidate_identity",
        "admissible_probe_outcome_identity",
        "admissible_matched_control_identity",
        "research_control_identity",
        "join_requirements",
    ):
        lines.append(f"### `{section}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(_dict(contract.get(section)), ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    lines.extend(["## No-Authority Answers", ""])
    for key, value in _dict(packet.get("answers")).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gap-closure-json", type=Path, required=True)
    parser.add_argument("--selected-side-cell-key")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_source_only_control_identity_contract(
        gap_closure=_read_json(args.gap_closure_json),
        selected_side_cell_key=args.selected_side_cell_key,
        gap_closure_path=args.gap_closure_json,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

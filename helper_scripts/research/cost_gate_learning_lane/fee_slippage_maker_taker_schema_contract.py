#!/usr/bin/env python3
"""Build a source-only fee/slippage/maker-taker schema contract.

The contract fixes the fields future AVAX proof rows and matched controls must
carry before any net PnL after fees/slippage can be credited. It does not query
PG, call Bybit, read fills, submit orders, lower Cost Gate, or grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_fee_slippage_maker_taker_schema_contract_v1"
READY_STATUS = "FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY"
WORKSHEET_NOT_READY_STATUS = "CURRENT_CAP_WORKSHEET_INPUT_NOT_READY"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"
CANDIDATE_MISSING_STATUS = "FEE_SCHEMA_CANDIDATE_MISSING"

WORKSHEET_SCHEMA_VERSION = "cost_gate_current_cap_staircase_risk_worksheet_v1"
WORKSHEET_READY_STATUS = "CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY"

BOUNDARY = (
    "artifact-only fee/slippage/maker-taker schema contract; no PG query/write, "
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
    "cap_mutation_performed",
    "canonical_plan_mutation_performed",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
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

IDENTITY_FIELDS = [
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
]

LINEAGE_FIELDS = [
    "attempt_id",
    "context_id",
    "signal_id",
    "source_admission_decision",
    "decision_lease_id",
    "order_link_id",
    "exchange_order_id",
    "exec_id",
    "source_artifact",
    "source_ledger_record_id",
]

FEE_FIELDS = [
    "fee_bps",
    "fee_rate",
    "fee_asset",
    "exec_fee",
    "maker_fee_bps",
    "taker_fee_bps",
]

SLIPPAGE_FIELDS = [
    "slippage_bps",
    "entry_slippage_bps",
    "exit_slippage_bps",
    "reference_price",
    "entry_price",
    "exit_price",
]

ROLE_FIELDS = [
    "liquidity_role",
    "maker_taker",
    "exec_type",
    "time_in_force",
    "post_only",
]

PNL_FIELDS = [
    "gross_bps",
    "cost_bps",
    "realized_net_bps",
    "notional_usdt",
    "qty",
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


def _authority_preserved(payload: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    stack: list[Any] = [payload]
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
        for key in AUTHORITY_TRUE_KEYS:
            if _truthy(data.get(key)):
                reasons.append(f"{key}_true")
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return not reasons, sorted(set(reasons))


def _worksheet_ready(worksheet: dict[str, Any]) -> bool:
    return (
        worksheet.get("schema_version") == WORKSHEET_SCHEMA_VERSION
        and worksheet.get("status") == WORKSHEET_READY_STATUS
    )


def _candidate(worksheet: dict[str, Any]) -> dict[str, Any]:
    return _dict(worksheet.get("candidate"))


def _required_exact_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: candidate.get(key) for key in IDENTITY_FIELDS}


def _field_group(
    *,
    group_id: str,
    fields: list[str],
    rule: str,
    proof_blocker_if_missing: bool = True,
) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "fields": fields,
        "rule": rule,
        "proof_blocker_if_missing": proof_blocker_if_missing,
    }


def _schema_contract(candidate: dict[str, Any], worksheet: dict[str, Any]) -> dict[str, Any]:
    construction_inputs = _dict(worksheet.get("construction_inputs"))
    risk = _dict(worksheet.get("risk_worksheet"))
    return {
        "candidate_identity": {
            "required_exact_fields": _required_exact_fields(candidate),
            "identity_rule": "future proof/control rows must exact-match the AVAX candidate identity",
        },
        "row_types": {
            "candidate_probe_outcome": {
                "record_type": "probe_outcome",
                "required_exact_fields": _required_exact_fields(candidate),
                "required_field_groups": [
                    _field_group(
                        group_id="lineage",
                        fields=LINEAGE_FIELDS,
                        rule="attempt/order/fill/outcome rows must be reconstructable",
                    ),
                    _field_group(
                        group_id="actual_fee",
                        fields=FEE_FIELDS,
                        rule="actual fee evidence is required; modeled fee alone is not proof",
                    ),
                    _field_group(
                        group_id="actual_slippage",
                        fields=SLIPPAGE_FIELDS,
                        rule="slippage must be measured against recorded reference prices",
                    ),
                    _field_group(
                        group_id="maker_taker_label",
                        fields=ROLE_FIELDS,
                        rule="liquidity role must be known as maker or taker",
                    ),
                    _field_group(
                        group_id="net_pnl_reconstruction",
                        fields=PNL_FIELDS,
                        rule="realized_net_bps must be reconstructable from gross, fees, and slippage",
                    ),
                ],
                "net_pnl_formula": "realized_net_bps = gross_bps - fee_bps - slippage_bps",
                "proof_exclusion_if_missing_any_required_group": True,
            },
            "matched_blocked_control_outcome": {
                "record_type": "blocked_signal_outcome",
                "required_exact_fields": _required_exact_fields(candidate),
                "required_field_groups": [
                    _field_group(
                        group_id="control_identity",
                        fields=[*IDENTITY_FIELDS, "source_signal_ts_ms", "control_reason"],
                        rule="control must be same-side-cell and point-in-time",
                    ),
                    _field_group(
                        group_id="control_fee_slippage",
                        fields=[*FEE_FIELDS, *SLIPPAGE_FIELDS, *PNL_FIELDS],
                        rule="control comparison must use the same after-cost reconstruction standard",
                    ),
                ],
                "cross_symbol_controls_allowed_as_proof": False,
            },
        },
        "maker_taker_policy": {
            "expected_liquidity_role_for_bounded_probe": "maker",
            "post_only_expected": True,
            "allowed_labels": ["maker", "taker"],
            "taker_label_policy": (
                "taker rows are not silently discarded if fully attributed, but they "
                "force execution-realism review and cannot support maker-path success "
                "without operator/QC review"
            ),
            "missing_label_policy": "proof_excluded_until_label_repaired",
        },
        "fee_slippage_policy": {
            "modeled_cost_only_allowed_for_proof": False,
            "actual_fee_required": True,
            "actual_slippage_required": True,
            "fee_asset_required": True,
            "fee_rate_or_bps_required": True,
            "reference_price_required": True,
            "negative_cost_allowed_without_review": False,
        },
        "risk_and_cap_context": {
            "per_order_cap_usdt": risk.get("per_order_cap_usdt"),
            "max_probe_orders_before_review": risk.get("max_probe_orders_before_review"),
            "max_total_demo_notional_before_review": risk.get(
                "max_total_demo_notional_before_review"
            ),
            "max_executable_tier_reserved_notional_usdt": risk.get(
                "max_executable_tier_reserved_notional_usdt"
            ),
            "order_admission_ready_from_this_contract": False,
            "bbo_refresh_required_before_order_admission": construction_inputs.get(
                "bbo_refresh_required_before_order_admission"
            ),
        },
        "failure_conditions": [
            "missing_actual_fee",
            "missing_actual_slippage",
            "missing_maker_taker_label",
            "missing_order_or_fill_lineage",
            "realized_net_not_reconstructable",
            "modeled_cost_used_as_proof",
            "cross_symbol_control_counted_as_candidate_proof",
            "unattributed_or_cleanup_fill_counted_as_proof",
        ],
        "future_review_requirements": [
            "proof_exclusion_reasons must be empty before proof count",
            "bounded_probe_result_review must enforce same-side-cell controls",
            "execution_realism_review must inspect taker rows, slippage outliers, and fee gaps",
            "no Cost Gate or promotion review may use rows failing this schema",
        ],
        "max_safe_next_action": "design_fresh_bbo_readonly_readiness_path_or_review_real_auth_delta",
    }


def build_fee_slippage_maker_taker_schema_contract(
    *,
    current_cap_worksheet: dict[str, Any] | None,
    current_cap_worksheet_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    worksheet = _dict(current_cap_worksheet)
    authority_ok, authority_reasons = _authority_preserved(worksheet)
    worksheet_ready = _worksheet_ready(worksheet)
    candidate = _candidate(worksheet)
    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_current_cap_worksheet"
    elif not worksheet_ready:
        status = WORKSHEET_NOT_READY_STATUS
        reason = "current_cap_worksheet_input_not_ready"
    elif not candidate:
        status = CANDIDATE_MISSING_STATUS
        reason = "candidate_missing_from_current_cap_worksheet"
    else:
        status = READY_STATUS
        reason = "fee_slippage_maker_taker_schema_ready"

    contract = _schema_contract(candidate, worksheet) if status == READY_STATUS else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_current_cap_worksheet": {
            "path": str(current_cap_worksheet_path) if current_cap_worksheet_path else None,
            "schema_version": worksheet.get("schema_version"),
            "status": worksheet.get("status"),
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
            "constructible_under_current_cap": _dict(worksheet.get("summary")).get(
                "constructible_under_current_cap"
            ),
            "order_admission_ready": _dict(worksheet.get("summary")).get(
                "order_admission_ready"
            ),
        },
        "candidate": candidate if status == READY_STATUS else {},
        "contract": contract,
        "summary": {
            "schema_contract_ready": status == READY_STATUS,
            "candidate_side_cell_key": candidate.get("side_cell_key") if candidate else None,
            "actual_fee_required": status == READY_STATUS,
            "actual_slippage_required": status == READY_STATUS,
            "maker_taker_label_required": status == READY_STATUS,
            "modeled_cost_only_allowed_for_proof": False,
            "order_admission_ready": False,
            "p0_authorization_required_before_probe": True,
            "max_safe_next_action": (
                contract.get("max_safe_next_action")
                if status == READY_STATUS
                else "refresh_ready_no_authority_current_cap_worksheet"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "fee_slippage_maker_taker_schema_ready": status == READY_STATUS,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "cap_mutation_performed": False,
            "risk_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "runtime_mutation_performed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "order_submission_performed": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    contract = _dict(packet.get("contract"))
    lines = [
        "# Fee/Slippage/Maker-Taker Schema Contract",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Row Types", ""])
    for row_type, spec in _dict(contract.get("row_types")).items():
        lines.append(f"### `{row_type}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True))
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
    parser.add_argument("--current-cap-worksheet-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_fee_slippage_maker_taker_schema_contract(
        current_cap_worksheet=_read_json(args.current_cap_worksheet_json),
        current_cap_worksheet_path=args.current_cap_worksheet_json,
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

#!/usr/bin/env python3
"""Build a source-only regime/OOS label contract for future AVAX proof.

The contract defines point-in-time regime, freshness, breadth/survivorship,
repeat, and OOS requirements before any future candidate-matched rows can be
used as proof. It does not query PG, call Bybit, read fills, submit orders,
lower Cost Gate, or grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_regime_oos_label_contract_v1"
READY_STATUS = "REGIME_OOS_LABEL_CONTRACT_READY_NO_AUTHORITY"
GAP_CLOSURE_NOT_READY_STATUS = "GAP_CLOSURE_INPUT_NOT_READY"
CONTROL_IDENTITY_NOT_READY_STATUS = "CONTROL_IDENTITY_INPUT_NOT_READY"
REQUIRED_GAPS_MISSING_STATUS = "REGIME_OOS_REQUIRED_GAPS_MISSING"
CANDIDATE_MISMATCH_STATUS = "REGIME_OOS_CANDIDATE_MISMATCH"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

GAP_CLOSURE_SCHEMA_VERSION = (
    "cost_gate_false_negative_evidence_floor_gap_closure_design_v1"
)
GAP_CLOSURE_READY_STATUS = "EVIDENCE_FLOOR_GAP_CLOSURE_DESIGN_READY_NO_AUTHORITY"
CONTROL_IDENTITY_SCHEMA_VERSION = "cost_gate_source_only_control_identity_contract_v1"
CONTROL_IDENTITY_READY_STATUS = "SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY"

REQUIRED_GAP_KEYS = {
    "regime_breadth_freshness_survivorship_labels",
    "repeat_or_oos_path_before_any_promotion_claim",
}

BOUNDARY = (
    "artifact-only regime/OOS label contract; no PG query/write, Bybit call, "
    "order, config, risk, auth, runtime mutation, Cost Gate lowering, "
    "freshness-gate lowering, cap mutation, probe authority, order authority, "
    "live authority, or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "active_order_submission_ready",
    "adapter_enabled",
    "adapter_enablement_performed",
    "bounded_demo_probe_authorized",
    "bounded_probe_authority_granted",
    "bounded_probe_proof",
    "bybit_call_performed",
    "bybit_account_call_performed",
    "bybit_order_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "canonical_plan_mutation_performed",
    "cost_gate_evidence",
    "cost_gate_proof",
    "credential_loaded",
    "crontab_mutation_performed",
    "demo_probe_authorized",
    "demo_probe_proof",
    "env_mutation_performed",
    "exchange_call_performed",
    "exchange_private_call_performed",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "order_admission_ready",
    "order_authority_granted",
    "order_call_performed",
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

AUTHORITY_NONEMPTY_KEYS = {
    "active_order_submission_ready",
    "auth_id",
    "authorization_id",
    "authorization_object_id",
    "bounded_probe_authorization_id",
    "bounded_probe_proof",
    "cost_gate_evidence",
    "cost_gate_proof",
    "demo_probe_proof",
    "exchange_order_id",
    "live_authority_id",
    "operator_authorization_id",
    "operator_authorization_object_id",
    "order_admission_ready",
    "order_authority_id",
    "order_id",
    "promotion_evidence",
    "promotion_proof",
    "promotion_ready",
    "probe_authority_id",
    "typed_confirm",
    "typed_confirm_expected",
    "typed_confirm_phrase",
    "typed_confirm_value",
}

IDENTITY_FIELDS = [
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
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


def _normalized_key(value: Any) -> str:
    with_separators = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value))
    return re.sub(r"[^a-z0-9]+", "_", with_separators.lower()).strip("_")


def _nonempty_signal(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized not in {
            "",
            "0",
            "false",
            "no",
            "n",
            "off",
            "disabled",
            "none",
            "null",
            "not_available",
            "not_applicable",
            "not_authorized",
            "not_granted",
            "not_ready",
            "unauthorized",
            "defer",
            "deferred",
            "n/a",
            "na",
        }
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _authority_preserved(*payloads: dict[str, Any] | None) -> tuple[bool, list[str]]:
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
        if data.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            reasons.append("main_cost_gate_adjustment_not_none")
        for key, value in data.items():
            normalized_key = _normalized_key(key)
            if normalized_key == "main_cost_gate_adjustment":
                continue
            if normalized_key in AUTHORITY_TRUE_KEYS and _truthy(value):
                reasons.append(f"{normalized_key}_true")
            if normalized_key in AUTHORITY_NONEMPTY_KEYS and _nonempty_signal(value):
                reasons.append(f"{normalized_key}_present")
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return not reasons, sorted(set(reasons))


def _gap_closure_ready(gap_closure: dict[str, Any]) -> bool:
    return (
        gap_closure.get("schema_version") == GAP_CLOSURE_SCHEMA_VERSION
        and gap_closure.get("status") == GAP_CLOSURE_READY_STATUS
    )


def _control_identity_ready(control_identity: dict[str, Any]) -> bool:
    return (
        control_identity.get("schema_version") == CONTROL_IDENTITY_SCHEMA_VERSION
        and control_identity.get("status") == CONTROL_IDENTITY_READY_STATUS
    )


def _candidate_from_gap(gap_closure: dict[str, Any]) -> dict[str, Any]:
    return _dict(gap_closure.get("candidate"))


def _candidate_from_control(control_identity: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(control_identity.get("candidate"))
    if candidate:
        return candidate
    return _dict(_dict(control_identity.get("contract")).get("candidate_identity"))


def _candidate_complete(candidate: dict[str, Any]) -> bool:
    return all(_str(candidate.get(key)) for key in IDENTITY_FIELDS)


def _candidate_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        _candidate_complete(left)
        and _candidate_complete(right)
        and all(left.get(key) == right.get(key) for key in IDENTITY_FIELDS)
    )


def _candidate_matches_selected(
    candidate: dict[str, Any],
    selected_side_cell_key: str | None,
) -> bool:
    selected = _str(selected_side_cell_key)
    return not selected or _str(candidate.get("side_cell_key")) == selected


def _present_gap_keys(gap_closure: dict[str, Any]) -> set[str]:
    return {
        _str(_dict(item).get("gap_key"))
        for item in _list(gap_closure.get("gap_closure_items"))
        if _str(_dict(item).get("gap_key"))
    }


def _required_exact_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: candidate.get(key) for key in IDENTITY_FIELDS}


def _label_contract(candidate: dict[str, Any]) -> dict[str, Any]:
    exact = _required_exact_fields(candidate)
    return {
        "candidate_identity": {
            "required_exact_fields": exact,
            "identity_rule": (
                "future regime/OOS labels must join to the exact AVAX candidate "
                "side-cell, not to cross-symbol controls"
            ),
        },
        "join_requirements": {
            "required_join_keys": [
                "side_cell_key",
                "strategy_name",
                "symbol",
                "side",
                "outcome_horizon_minutes",
                "signal_ts_ms_or_context_ts_ms",
                "source_artifact_or_label_packet_id",
            ],
            "join_time_rule": (
                "label_feature_ts_ms and label_effective_ts_ms must be <= "
                "signal_ts_ms_or_context_ts_ms; outcome_ts_ms cannot be used "
                "to form pre-entry labels"
            ),
            "candidate_side_cell_key": candidate.get("side_cell_key"),
            "same_side_cell_labels_required_for_candidate_proof": True,
            "cross_symbol_regime_labels_count_as_candidate_proof": False,
        },
        "label_groups": {
            "point_in_time_regime": {
                "required_fields": [
                    "regime_label",
                    "market_anchor_regime",
                    "overlay_flags",
                    "regime_model_version",
                    "label_feature_ts_ms",
                    "label_effective_ts_ms",
                    "label_source_artifact_sha256",
                ],
                "forbidden_sources": [
                    "future_return_bucket",
                    "post_outcome_pnl",
                    "manual_after_the_fact_label",
                    "bull_market_global_default_without_timestamp",
                ],
                "classifier_threshold_rule": (
                    "regime classifier thresholds and overlay rules must be fixed "
                    "before candidate scoring"
                ),
                "bybit_market_data_role": (
                    "Bybit market data may be raw input only; it is never a "
                    "prediction label or proof label"
                ),
                "proof_blocker_if_missing": True,
            },
            "freshness": {
                "required_fields": [
                    "label_generated_at_utc",
                    "label_max_age_ms",
                    "label_age_ms_at_signal",
                    "freshness_status",
                    "freshness_bucket",
                    "recent_90d_net_bps",
                    "recent_180d_net_bps",
                ],
                "rule": "freshness_status must be FRESH; stale labels keep rows research-only",
                "freshness_gate_lowering_allowed": False,
                "proof_blocker_if_missing": True,
            },
            "breadth_survivorship": {
                "required_fields": [
                    "point_in_time_universe_id",
                    "listed_at_or_before_signal",
                    "alive_through_signal",
                    "breadth_cohort",
                    "survivorship_source",
                    "survivorship_mode",
                ],
                "rule": (
                    "symbol must be in the point-in-time tradable universe at "
                    "signal time; current-survivor-only labels are research-only"
                ),
                "proof_blocker_if_missing": True,
            },
            "repeat_oos": {
                "required_fields": [
                    "split_id",
                    "is_oos",
                    "repeat_window_id",
                    "distinct_signal_date",
                    "distinct_signal_date_count",
                    "train_cutoff_ts_ms",
                    "purge_seconds",
                    "embargo_seconds",
                    "n_independent",
                    "sample_unit",
                    "final_verdict_label",
                    "reject_reasons",
                ],
                "rule": (
                    "single-window positives, replay-only positives, and artifact "
                    "counts cannot satisfy proof or promotion review"
                ),
                "allowed_final_verdict_labels": [
                    "durable-alpha candidate",
                    "regime-bet / learning-only",
                    "stale-data artifact",
                    "breadth-limited",
                    "insufficient evidence",
                    "kill",
                ],
                "proof_blocker_if_missing": True,
            },
        },
        "adr_0047_downgrade_rules": {
            "bull_heavy_or_rally_only_positive": "regime-bet / learning-only",
            "2024_dominated_or_stale_year_positive": "stale-data artifact",
            "current_survivor_only_or_narrow_breadth": "breadth-limited",
            "non_bull_insufficient_positives": "insufficient evidence",
            "thresholds_changed_after_scoring": "kill",
        },
        "row_use_policy": {
            "candidate_probe_row": {
                "allowed_use": "future_candidate_context_only_until_fills_exist",
                "proof_requires": [
                    "candidate_scoped_bounded_demo_authorization",
                    "candidate_matched_fill_rows",
                    "actual_fee_slippage_maker_taker_schema_pass",
                    "same_side_cell_matched_controls",
                    "point_in_time_regime_labels",
                    "freshness_status_FRESH",
                    "survivorship_pit_verified",
                    "repeat_or_oos_path_present",
                    "execution_realism_review_pass",
                ],
            },
            "cross_symbol_or_research_control_row": {
                "allowed_use": "robustness_or_candidate_selection_context_only",
                "prohibited_use": [
                    "candidate_proof",
                    "bounded_probe_proof",
                    "cost_gate_proof",
                    "promotion_evidence",
                    "global_cost_gate_adjustment",
                ],
            },
        },
        "failure_conditions": [
            "label_feature_ts_after_signal_ts",
            "label_effective_ts_after_signal_ts",
            "freshness_status_not_FRESH",
            "current_survivor_only_universe",
            "missing_point_in_time_universe_id",
            "single_window_positive_used_as_proof",
            "replay_only_result_used_as_proof",
            "artifact_count_used_as_profit_evidence",
            "cross_symbol_label_counted_as_candidate_proof",
            "bull_heavy_positive_used_as_general_market_proof",
            "rally_only_positive_used_as_general_market_proof",
            "stale_year_dominated_positive_used_as_fresh_proof",
            "current_survivor_only_positive_used_as_proof",
            "classifier_thresholds_changed_after_scoring",
            "missing_purge_or_embargo_metadata",
            "missing_n_independent_or_sample_unit",
            "missing_recent_90d_or_180d_net_fields",
            "missing_final_verdict_or_reject_reasons",
        ],
        "future_review_requirements": [
            "runtime_or_PG_label_query_requires_separate_read_only_PM_E3_review",
            "no promotion review before repeat_or_oos_path is present",
            "no Cost Gate proof from rows missing regime/OOS labels",
            "future outcome review must keep unmatched labels research-only",
        ],
        "max_safe_next_action": "keep_contract_source_only_or_review_real_auth_delta",
    }


def build_regime_oos_label_contract(
    *,
    gap_closure: dict[str, Any] | None,
    control_identity: dict[str, Any] | None,
    gap_closure_path: Path | None = None,
    control_identity_path: Path | None = None,
    selected_side_cell_key: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    gap = _dict(gap_closure)
    control = _dict(control_identity)
    authority_ok, authority_reasons = _authority_preserved(gap, control)
    gap_ready = _gap_closure_ready(gap)
    control_ready = _control_identity_ready(control)
    gap_candidate = _candidate_from_gap(gap)
    control_candidate = _candidate_from_control(control)
    missing_gaps = sorted(REQUIRED_GAP_KEYS - _present_gap_keys(gap))
    candidate_ok = (
        bool(gap_candidate)
        and bool(control_candidate)
        and _candidate_matches(gap_candidate, control_candidate)
        and _candidate_matches_selected(gap_candidate, selected_side_cell_key)
    )

    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_inputs"
    elif not gap_ready:
        status = GAP_CLOSURE_NOT_READY_STATUS
        reason = "gap_closure_input_not_ready"
    elif not control_ready:
        status = CONTROL_IDENTITY_NOT_READY_STATUS
        reason = "control_identity_input_not_ready"
    elif missing_gaps:
        status = REQUIRED_GAPS_MISSING_STATUS
        reason = "required_regime_oos_gap_keys_missing"
    elif not candidate_ok:
        status = CANDIDATE_MISMATCH_STATUS
        reason = "candidate_missing_or_mismatched"
    else:
        status = READY_STATUS
        reason = "regime_oos_label_contract_ready"

    contract = _label_contract(gap_candidate) if status == READY_STATUS else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_gap_closure": {
            "path": str(gap_closure_path) if gap_closure_path else None,
            "schema_version": gap.get("schema_version"),
            "status": gap.get("status"),
            "required_gap_keys_present": sorted(REQUIRED_GAP_KEYS - set(missing_gaps)),
            "missing_required_gap_keys": missing_gaps,
        },
        "source_control_identity": {
            "path": str(control_identity_path) if control_identity_path else None,
            "schema_version": control.get("schema_version"),
            "status": control.get("status"),
        },
        "authority_preserved": authority_ok,
        "authority_contamination_reasons": authority_reasons,
        "candidate": gap_candidate if status == READY_STATUS else {},
        "contract": contract,
        "summary": {
            "contract_ready": status == READY_STATUS,
            "candidate_side_cell_key": (
                gap_candidate.get("side_cell_key") if status == READY_STATUS else None
            ),
            "point_in_time_regime_required": status == READY_STATUS,
            "freshness_labels_required": status == READY_STATUS,
            "survivorship_labels_required": status == READY_STATUS,
            "repeat_or_oos_required_before_promotion": status == READY_STATUS,
            "runtime_or_pg_label_query_performed": False,
            "order_admission_ready": False,
            "promotion_proof": False,
            "max_safe_next_action": (
                contract.get("max_safe_next_action")
                if status == READY_STATUS
                else "refresh_ready_no_authority_gap_and_control_inputs"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "regime_oos_label_contract_ready": status == READY_STATUS,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "freshness_gate_lowering_recommended": False,
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
        "# Regime/OOS Label Contract",
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
    lines.extend(["", "## Label Groups", ""])
    for group, spec in _dict(contract.get("label_groups")).items():
        lines.append(f"### `{group}`")
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
    parser.add_argument("--gap-closure-json", type=Path, required=True)
    parser.add_argument("--control-identity-json", type=Path, required=True)
    parser.add_argument("--selected-side-cell-key")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_regime_oos_label_contract(
        gap_closure=_read_json(args.gap_closure_json),
        control_identity=_read_json(args.control_identity_json),
        gap_closure_path=args.gap_closure_json,
        control_identity_path=args.control_identity_json,
        selected_side_cell_key=args.selected_side_cell_key,
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

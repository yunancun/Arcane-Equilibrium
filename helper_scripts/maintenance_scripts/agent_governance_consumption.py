"""Strict consumption status and closure aggregation validation."""

from __future__ import annotations

import re
from typing import Any

from agent_governance_registry import load_registry


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ROLE_METRICS = {
    "input_tokens", "output_tokens", "cache_read_tokens", "tool_calls",
    "retry_count", "wall_time_ms", "rework_count",
}
CLOSURE_METRICS = ROLE_METRICS | {
    "planned_tokens", "fan_out", "accepted_findings",
}
COMMON_FIELDS = {
    "measurement_status", "unavailable_reason", "measurement_source",
    "telemetry_digest", "telemetry_ref", "missing_metrics",
}
SUM_METRICS = {
    "input_tokens", "output_tokens", "cache_read_tokens", "tool_calls",
    "retry_count", "rework_count",
}


def _record_errors(
    record: Any,
    *,
    metrics: set[str],
    label: str,
    require_quality_reserve: bool = False,
    allow_wave_refs: bool = False,
) -> list[str]:
    if not isinstance(record, dict):
        return [f"{label} consumption must be an object"]
    allowed = COMMON_FIELDS | metrics
    if require_quality_reserve:
        allowed.add("quality_reserve_used")
    if allow_wave_refs:
        allowed.add("wave_record_refs")
    errors: list[str] = []
    extras = set(record) - allowed
    if extras:
        errors.append(f"{label} consumption has unknown fields {sorted(extras)}")
    status = record.get("measurement_status")
    if not isinstance(status, str) or status not in {"measured", "partial", "unavailable"}:
        return [f"{label} consumption measurement_status is invalid", *errors]
    numeric_present = {field for field in metrics if field in record}
    for field in numeric_present:
        value = record[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{label} consumption {field} must be a non-negative integer")
    if status == "unavailable":
        if not isinstance(record.get("unavailable_reason"), str) or not record.get("unavailable_reason", "").strip():
            errors.append(f"{label} unavailable consumption requires a reason")
        if (
            numeric_present
            or record.get("telemetry_digest") is not None
            or record.get("telemetry_ref") is not None
            or record.get("measurement_source") is not None
            or record.get("wave_record_refs") is not None
        ):
            errors.append(f"{label} unavailable consumption cannot claim telemetry or metrics")
        if record.get("missing_metrics") is not None:
            errors.append(f"{label} unavailable consumption cannot carry missing_metrics")
        if require_quality_reserve and "quality_reserve_used" in record:
            errors.append(
                f"{label} unavailable consumption cannot claim quality_reserve_used"
            )
        return errors
    measurement_source = record.get("measurement_source")
    if not isinstance(measurement_source, str) or measurement_source not in {
        "platform_telemetry", "provider_usage_api", "orchestrator_receipt",
    }:
        errors.append(f"{label} measured/partial consumption requires a trusted source")
    telemetry_ref = record.get("telemetry_ref")
    wave_refs = record.get("wave_record_refs")
    if measurement_source == "orchestrator_receipt":
        if status == "measured":
            errors.append(f"{label} orchestrator receipt cannot claim fully measured usage")
        if not allow_wave_refs:
            errors.append(f"{label} fragment consumption cannot substitute a wave receipt for telemetry")
        if (
            not isinstance(wave_refs, list) or not wave_refs
            or any(not isinstance(item, str) or not item for item in wave_refs)
            or len(wave_refs) != len(set(wave_refs))
        ):
            errors.append(f"{label} orchestrator partial consumption requires unique wave refs")
        if telemetry_ref is not None or record.get("telemetry_digest") is not None:
            errors.append(f"{label} orchestrator partial consumption cannot claim telemetry")
    else:
        if not isinstance(telemetry_ref, str) or not telemetry_ref:
            errors.append(f"{label} measured/partial consumption requires telemetry ref")
        if not DIGEST_RE.fullmatch(str(record.get("telemetry_digest", ""))):
            errors.append(f"{label} measured/partial consumption requires telemetry digest")
        if wave_refs is not None:
            errors.append(f"{label} platform/provider consumption cannot substitute wave refs")
    if (
        require_quality_reserve
        and "planned_tokens" in numeric_present
        and not isinstance(record.get("quality_reserve_used"), bool)
    ):
        errors.append(f"{label} consumption planned_tokens requires quality_reserve_used")
    if (
        require_quality_reserve
        and "quality_reserve_used" in record
        and "planned_tokens" not in numeric_present
    ):
        errors.append(f"{label} quality_reserve_used requires planned_tokens")
    if status == "measured":
        if numeric_present != metrics:
            errors.append(f"{label} measured consumption requires every metric")
        if record.get("unavailable_reason") is not None or record.get("missing_metrics") is not None:
            errors.append(f"{label} measured consumption cannot claim missing telemetry")
    else:
        if not numeric_present:
            errors.append(f"{label} partial consumption requires at least one measured metric")
        missing = record.get("missing_metrics")
        if (
            not isinstance(missing, list)
            or not missing
            or any(not isinstance(item, str) or item not in metrics for item in missing)
            or len(missing) != len(set(missing))
            or set(missing) != metrics - numeric_present
        ):
            errors.append(f"{label} partial consumption missing_metrics is inconsistent")
        if not isinstance(record.get("unavailable_reason"), str) or not record.get("unavailable_reason", "").strip():
            errors.append(f"{label} partial consumption requires an unavailable reason")
        if require_quality_reserve and "quality_reserve_used" in record and not isinstance(record["quality_reserve_used"], bool):
            errors.append(f"{label} quality_reserve_used must be boolean")
    return errors


def validate_consumption_binding(
    packet: Any,
    fragments: Any,
    expected_route: dict[str, Any] | None,
    capture_index: dict[str, Any] | None = None,
) -> list[str]:
    """Validate status honesty and deterministic fragment-to-closure totals."""

    errors: list[str] = []
    if not isinstance(packet, dict):
        errors.append("closure packet must be an object")
        packet = {}
    if not isinstance(fragments, list):
        errors.append("role_fragments must be an array")
        fragments = []
    if expected_route is not None and not isinstance(expected_route, dict):
        errors.append("expected route must be an object")
        expected_route = None
    fragment_records: list[dict[str, Any]] = []
    for index, fragment in enumerate(fragments):
        if not isinstance(fragment, dict):
            errors.append(f"role_fragments[{index}] must be an object")
            continue
        record = fragment.get("consumption")
        errors.extend(_record_errors(record, metrics=ROLE_METRICS, label=f"role_fragments[{index}]"))
        if isinstance(record, dict):
            fragment_records.append(record)
    telemetry_refs = [
        record.get("telemetry_ref")
        for record in fragment_records
        if isinstance(record.get("measurement_status"), str)
        and record.get("measurement_status") in {"measured", "partial"}
        and isinstance(record.get("telemetry_ref"), str)
    ]
    if len(telemetry_refs) != len(set(telemetry_refs)):
        errors.append("fragment telemetry refs must be unique")
    aggregate = packet.get("consumption")
    errors.extend(
        _record_errors(
            aggregate, metrics=CLOSURE_METRICS, label="closure",
            require_quality_reserve=True,
            allow_wave_refs=True,
        )
    )
    if not isinstance(aggregate, dict):
        return errors
    status = aggregate.get("measurement_status")
    accepted_findings = sum(
        1
        for fragment in fragments
        if isinstance(fragment, dict)
        and fragment.get("work_status") in {"DONE", "DONE_WITH_CONCERNS"}
        and fragment.get("gate_verdict") == "PASS"
        and fragment.get("classification") == "FACT"
        and fragment.get("confidence") in {"high", "med"}
        and fragment.get("concerns") == []
    )
    if (
        "accepted_findings" in aggregate
        and aggregate.get("accepted_findings") != accepted_findings
    ):
        errors.append(
            "closure accepted_findings differs from accepted FACT fragments"
        )
    if (
        aggregate.get("measurement_source") == "orchestrator_receipt"
        and "rework_count" in aggregate
    ):
        fragment_rework = [
            record.get("rework_count") for record in fragment_records
            if isinstance(record.get("rework_count"), int)
            and not isinstance(record.get("rework_count"), bool)
        ]
        if len(fragment_rework) != len(fragment_records):
            errors.append(
                "closure orchestrator rework_count lacks complete attested fragment metrics"
            )
        elif aggregate.get("rework_count") != sum(fragment_rework):
            errors.append(
                "closure orchestrator rework_count differs from attested fragment sum"
            )
    platform_attested = (
        set(capture_index.get("platform_attested", set()))
        if isinstance(capture_index, dict) else set()
    )
    telemetry_by_id = (
        capture_index.get("telemetry", {})
        if isinstance(capture_index, dict) else {}
    )
    bound_consumption = [
        (f"role_fragments[{index}]", item)
        for index, item in enumerate(fragment_records)
    ] + [("closure", aggregate)]
    for label, record in bound_consumption:
        record_status = record.get("measurement_status")
        if not isinstance(record_status, str) or record_status not in {
            "measured", "partial"
        }:
            continue
        if record.get("measurement_source") == "orchestrator_receipt":
            continue
        telemetry_ref = record.get("telemetry_ref")
        telemetry = telemetry_by_id.get(telemetry_ref) if isinstance(telemetry_by_id, dict) else None
        if telemetry_ref not in platform_attested or not isinstance(telemetry, dict):
            errors.append(f"{label} actual usage requires platform/external-attested telemetry")
            continue
        if record.get("telemetry_digest") != telemetry.get("record_digest"):
            errors.append(f"{label} telemetry digest differs from referenced record")
        metrics = telemetry.get("body", {}).get("metrics", {})
        for field in ROLE_METRICS:
            if field in record and record.get(field) != metrics.get(field):
                errors.append(f"{label} {field} differs from telemetry body")
        if label == "closure" and "fan_out" in record:
            subject_calls = telemetry.get("body", {}).get("subject_call_ids", [])
            if not isinstance(subject_calls, list) or record.get("fan_out") != len(subject_calls):
                errors.append("closure fan_out differs from telemetry subject calls")
    fragment_statuses = {
        record.get("measurement_status") for record in fragment_records
        if isinstance(record.get("measurement_status"), str)
    }
    if status == "measured" and fragment_statuses != {"measured"}:
        errors.append("measured closure consumption requires every fragment measured")
    if status == "unavailable" and fragment_statuses - {"unavailable"}:
        errors.append("unavailable closure consumption hides available fragment telemetry")
    if status == "partial":
        known_fragment_metrics = {
            field for field in ROLE_METRICS
            if any(
                isinstance(record.get(field), int)
                and not isinstance(record.get(field), bool)
                for record in fragment_records
            )
        }
        missing = aggregate.get("missing_metrics")
        hidden = (
            known_fragment_metrics & set(missing)
            if isinstance(missing, list)
            and all(isinstance(item, str) for item in missing)
            else set()
        )
        if hidden:
            errors.append(
                f"closure partial consumption hides known fragment metrics {sorted(hidden)}"
            )
        if aggregate.get("measurement_source") == "orchestrator_receipt":
            waves_by_id = (
                capture_index.get("waves_by_id", {})
                if isinstance(capture_index, dict) else {}
            )
            refs = aggregate.get("wave_record_refs")
            expected_wave_refs = (
                set(waves_by_id) if isinstance(waves_by_id, dict) else set()
            )
            if not isinstance(refs, list) or set(refs) != expected_wave_refs:
                errors.append(
                    "closure orchestrator consumption wave refs must exactly cover every captured wave"
                )
            selected_waves = [
                waves_by_id.get(ref) for ref in (refs if isinstance(refs, list) else [])
                if isinstance(waves_by_id, dict)
            ]
            if (
                not isinstance(refs, list)
                or len(selected_waves) != len(refs)
                or any(not isinstance(wave, dict) for wave in selected_waves)
            ):
                errors.append("closure orchestrator consumption references missing wave records")
            else:
                expected_planned = sum(
                    wave["scheduled_call_admitted_input_tokens_lower_bound"]
                    for wave in selected_waves
                )
                expected_retries = sum(wave["retry_call_count"] for wave in selected_waves)
                expected_fan_out = sum(len(wave["admitted_tasks"]) for wave in selected_waves)
                for field, expected in (
                    ("planned_tokens", expected_planned),
                    ("retry_count", expected_retries),
                    ("fan_out", expected_fan_out),
                ):
                    if aggregate.get(field) != expected:
                        errors.append(
                            f"closure orchestrator consumption {field} differs from wave ledger"
                        )
    for field in SUM_METRICS:
        measured_values = [
            record[field] for record in fragment_records
            if isinstance(record.get(field), int) and not isinstance(record.get(field), bool)
        ]
        if field not in aggregate:
            continue
        expected = sum(measured_values)
        aggregate_value = aggregate[field]
        aggregate_is_integer = isinstance(aggregate_value, int) and not isinstance(
            aggregate_value, bool
        )
        if status == "measured" and aggregate_is_integer and aggregate_value != expected:
            errors.append(f"closure consumption {field} does not equal fragment sum")
        elif status == "partial" and aggregate_is_integer and aggregate_value < expected:
            errors.append(f"closure partial consumption {field} is below known fragment sum")
    known_walls = [
        record["wall_time_ms"] for record in fragment_records
        if isinstance(record.get("wall_time_ms"), int) and not isinstance(record.get("wall_time_ms"), bool)
    ]
    aggregate_wall = aggregate.get("wall_time_ms")
    if (
        isinstance(aggregate_wall, int)
        and not isinstance(aggregate_wall, bool)
        and known_walls
        and aggregate_wall < max(known_walls)
    ):
        errors.append("closure wall_time_ms is below a known fragment duration")
    if "planned_tokens" in aggregate and expected_route is not None:
        envelope_name = expected_route.get("budget_envelope")
        envelope = load_registry()["budget_envelopes"].get(envelope_name, {})
        target = envelope.get("target_context_tokens")
        planned_tokens = aggregate.get("planned_tokens")
        if (
            isinstance(target, int)
            and isinstance(planned_tokens, int)
            and not isinstance(planned_tokens, bool)
            and "quality_reserve_used" in aggregate
        ):
            expected_reserve = planned_tokens > target
            if aggregate["quality_reserve_used"] is not expected_reserve:
                errors.append("closure quality_reserve_used disagrees with governed envelope")
    return errors

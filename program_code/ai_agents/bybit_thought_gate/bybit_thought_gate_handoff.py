#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from bybit_h1_report_utils import THOUGHT_GATE_DIR, read_json, save_latest_and_dated

try:
    from program_code.ml_training.advisory_review_packet import (
        build_advisory_review_packet,
        stable_sha256_json,
    )
except ModuleNotFoundError:  # pragma: no cover - import path depends on runner cwd/PYTHONPATH
    from ml_training.advisory_review_packet import (  # type: ignore
        build_advisory_review_packet,
        stable_sha256_json,
    )

SUMMARY = THOUGHT_GATE_DIR / "bybit_thought_gate_regression_summary_latest.json"


def main() -> None:
    now_ms = int(time.time() * 1000)
    s = read_json(SUMMARY, {})
    summary_ok = bool(s.get("summary_ok"))
    hard_safety_boundaries = {
        "system_mode": "read_only",
        "execution_state": "disabled",
        "execution_authority": "not_granted",
        "decision_lease_emitted": False,
        "not_authority": True,
        "inactive_review_packet": True,
        "active": False,
        "no_order_mutation": True,
        "no_probe_mutation": True,
        "no_live_mutation": True,
        "no_mainnet_mutation": True,
        "no_runtime_mutation": True,
        "no_db_mutation": True,
        "no_secret_mutation": True,
        "no_promotion_mutation": True,
        "no_cost_gate_mutation": True,
        "no_strategy_config_mutation": True,
        "demo_envelope_required_for_mutation": True,
        "current_packet_grants_demo_mutation": False,
    }
    input_hashes = {
        "regression_summary": stable_sha256_json(s),
        "hard_safety_boundaries": stable_sha256_json(hard_safety_boundaries),
        "recommended_next_build_order": stable_sha256_json(s.get("recommended_next_build_order") or []),
    }
    advisory_review_packet = build_advisory_review_packet(
        capability_id="bybit_thought_gate.handoff",
        producer="bybit_thought_gate_handoff",
        mode="h1_closed_ready_for_h2" if summary_ok else "h1_not_ready_for_handoff",
        input_hashes=input_hashes,
        budget_ref="bybit_thought_gate_regression_summary",
        notes=[
            "H1 handoff is a role-contract summary for downstream review only.",
            "It grants no mutation, execution, Decision Lease, demo, live, mainnet, Cost Gate, or runtime authority.",
        ],
    )

    report = {
        "handoff_type": "bybit_thought_gate_handoff",
        "handoff_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-I",
        "handoff_ok": summary_ok,
        "handoff_state": "h1_closed_ready_for_h2" if summary_ok else "h1_not_ready_for_handoff",
        "hard_safety_boundaries": hard_safety_boundaries,
        "input_hashes": input_hashes,
        "advisory_review_packet": advisory_review_packet,
        "recommended_next_build_order": s.get("recommended_next_build_order") or [],
        "operator_guidance": [
            "Do not treat H1 output as execution permission.",
            "Proceed to H2 query_budget before expanding model routing complexity.",
            "Keep provider-native output under contract and audit checks.",
        ],
        "operator_message": (
            "H1 handoff complete. Chapter is closed as a governed AI observation path and ready to hand off to H2."
            if summary_ok
            else "H1 handoff blocked because summary is not yet green."
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_thought_gate_handoff", report)


if __name__ == "__main__":
    main()

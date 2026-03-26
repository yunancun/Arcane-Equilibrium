from __future__ import annotations

"""
Generate a normalized OpenClaw runtime snapshot JSON file.
生成归一化的 OpenClaw runtime 快照 JSON 文件。

Usage / 用法:
python3 scripts/generate_runtime_snapshot.py \
  --runtime-status-file examples/runtime_status.fragment.example.json \
  --product-family-facts-file examples/product_family_facts.fragment.example.json \
  --health-file examples/health_telemetry.fragment.example.json \
  --output /tmp/runtime_snapshot.generated.json
"""

import argparse
import json
from pathlib import Path
from typing import Any

from runtime_snapshot_contract import RuntimeSnapshotValidationError, validate_runtime_snapshot_payload


def load_json_file(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeSnapshotValidationError(f"{path} must contain a JSON object")
    return payload


def build_runtime_snapshot(
    *,
    runtime_status_payload: dict[str, Any],
    product_family_facts_payload: dict[str, Any],
    health_payload: dict[str, Any] | None,
    readonly_connector_name: str | None,
    execution_connector_name: str | None,
) -> dict[str, Any]:
    snapshot = {
        "runtime_snapshot_id": runtime_status_payload["runtime_snapshot_id"],
        "runtime_snapshot_ts_ms": runtime_status_payload["runtime_snapshot_ts_ms"],
        "readonly_connector_name": readonly_connector_name
        if readonly_connector_name is not None
        else runtime_status_payload.get("readonly_connector_name", "bybit_prod_readonly_main"),
        "execution_connector_name": execution_connector_name
        if execution_connector_name is not None
        else runtime_status_payload.get("execution_connector_name"),
        "rest_private_connection_state": runtime_status_payload["rest_private_connection_state"],
        "ws_private_connection_state": runtime_status_payload["ws_private_connection_state"],
        "runtime_connection_state": runtime_status_payload["runtime_connection_state"],
        "account_fact_completeness_state": runtime_status_payload["account_fact_completeness_state"],
        "source_snapshot_completeness_state": runtime_status_payload["source_snapshot_completeness_state"],
        "global_runtime_facts": runtime_status_payload["global_runtime_facts"],
        "product_family_facts": product_family_facts_payload,
    }
    if health_payload is not None:
        snapshot["health_telemetry"] = health_payload
    return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a normalized OpenClaw runtime snapshot JSON file.")
    parser.add_argument("--runtime-status-file", required=True, help="JSON file containing runtime-level facts and connection states.")
    parser.add_argument("--product-family-facts-file", required=True, help="JSON file containing normalized product-family facts.")
    parser.add_argument("--health-file", required=False, help="Optional JSON file containing health telemetry.")
    parser.add_argument("--readonly-connector-name", required=False, help="Optional override for readonly_connector_name.")
    parser.add_argument("--execution-connector-name", required=False, help="Optional override for execution_connector_name.")
    parser.add_argument("--output", required=False, help="Optional output file path. If omitted, print to stdout.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    runtime_status_payload = load_json_file(args.runtime_status_file)
    product_family_facts_payload = load_json_file(args.product_family_facts_file)
    health_payload = load_json_file(args.health_file) if args.health_file else None

    snapshot = build_runtime_snapshot(
        runtime_status_payload=runtime_status_payload,
        product_family_facts_payload=product_family_facts_payload,
        health_payload=health_payload,
        readonly_connector_name=args.readonly_connector_name,
        execution_connector_name=args.execution_connector_name,
    )

    validate_runtime_snapshot_payload(snapshot)
    rendered = json.dumps(snapshot, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        print(f"OK: runtime snapshot generated at {args.output}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()

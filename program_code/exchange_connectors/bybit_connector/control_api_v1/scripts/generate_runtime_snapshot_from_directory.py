from __future__ import annotations

"""
Generate a normalized runtime snapshot from a standard fragment directory.
从标准 fragment 目录生成归一化 runtime snapshot。

Usage / 用法:
python3 scripts/generate_runtime_snapshot_from_directory.py \
  --input-dir examples/runtime_fragments_directory_example \
  --output /tmp/runtime_snapshot.generated.json
"""

import argparse
import json
from pathlib import Path

from generate_runtime_snapshot import build_runtime_snapshot
from runtime_snapshot_contract import validate_runtime_snapshot_payload
from runtime_snapshot_providers import DirectoryFragmentProvider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a normalized runtime snapshot from a standard fragment directory.")
    parser.add_argument("--input-dir", required=True, help="Directory containing runtime_status.json and product_family_facts.json.")
    parser.add_argument("--readonly-connector-name", required=False, help="Optional override for readonly_connector_name.")
    parser.add_argument("--execution-connector-name", required=False, help="Optional override for execution_connector_name.")
    parser.add_argument("--output", required=False, help="Optional output file path. If omitted, print to stdout.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fragments = DirectoryFragmentProvider(args.input_dir).load_fragments()

    snapshot = build_runtime_snapshot(
        runtime_status_payload=fragments.runtime_status_payload,
        product_family_facts_payload=fragments.product_family_facts_payload,
        health_payload=fragments.health_payload,
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

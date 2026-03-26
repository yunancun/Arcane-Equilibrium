from __future__ import annotations

"""
Validate an OpenClaw runtime snapshot JSON file.
校验 OpenClaw runtime 快照 JSON 文件。

Usage / 用法:
python3 scripts/validate_runtime_snapshot.py /path/to/runtime_snapshot.json
"""

import json
import sys
from pathlib import Path

from runtime_snapshot_contract import RuntimeSnapshotValidationError, validate_runtime_snapshot_payload


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: python3 scripts/validate_runtime_snapshot.py /path/to/runtime_snapshot.json")

    path = Path(sys.argv[1])
    if not path.exists() or not path.is_file():
        fail(f"file not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid json: {exc}")

    try:
        validate_runtime_snapshot_payload(payload)
    except RuntimeSnapshotValidationError as exc:
        fail(str(exc))

    print("OK: runtime snapshot validation passed")


if __name__ == "__main__":
    main()

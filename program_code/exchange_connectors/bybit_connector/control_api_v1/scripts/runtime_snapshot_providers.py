from __future__ import annotations

"""
Runtime snapshot providers.
Runtime 快照 provider 集合。

当前提供：
- DirectoryFragmentProvider: 从标准目录读取 fragment JSON 文件。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime_snapshot_contract import RuntimeSnapshotValidationError


@dataclass(slots=True)
class RuntimeSnapshotFragments:
    runtime_status_payload: dict[str, Any]
    product_family_facts_payload: dict[str, Any]
    health_payload: dict[str, Any] | None = None


class DirectoryFragmentProvider:
    """
    Read normalized runtime fragments from a directory.
    从标准目录读取归一化 runtime 片段。

    Expected files / 约定文件：
    - runtime_status.json (required)
    - product_family_facts.json (required)
    - health_telemetry.json (optional)
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    def _load_json_file(self, filename: str, *, required: bool) -> dict[str, Any] | None:
        path = self.directory / filename
        if not path.exists():
            if required:
                raise RuntimeSnapshotValidationError(f"required fragment file missing: {path}")
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeSnapshotValidationError(f"invalid json in {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeSnapshotValidationError(f"fragment file must contain a JSON object: {path}")
        return payload

    def load_fragments(self) -> RuntimeSnapshotFragments:
        runtime_status_payload = self._load_json_file("runtime_status.json", required=True)
        product_family_facts_payload = self._load_json_file("product_family_facts.json", required=True)
        health_payload = self._load_json_file("health_telemetry.json", required=False)
        return RuntimeSnapshotFragments(
            runtime_status_payload=runtime_status_payload or {},
            product_family_facts_payload=product_family_facts_payload or {},
            health_payload=health_payload,
        )

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 对 K 章 paper position / balance projection capability latest 做 contract check。
- 这一层的目标，是把 projection 当前的能力边界正式 contract 化：
  1. projection 模型面已经定义；
  2. projection 仍不能驱动真实 paper ledger；
  3. ledger path 仍保持关闭；
  4. paper/live execution 都没有被打开。
- 这不是放开 projection，而是把“模型已经定义到哪一步、仍不能做什么”
  用结构化方式固定下来。

English:
- Contract-check the K paper position / balance projection capability latest artifact.
- The goal is to formalize the current projection boundary:
  1. the projection model surface is defined,
  2. projection still cannot drive a real paper ledger,
  3. the ledger path remains closed,
  4. paper/live execution are not opened.
- This does NOT enable projection. It structurally fixes how far the model has been defined
  and what it must still NOT do.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without machine-specific absolute paths.
    中文：避免维护继续依赖单机路径。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for projection capability contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
PROJECTION_PATH = BASE / "bybit_paper_position_balance_projection_capability_latest.json"
OUT_LATEST = BASE / "bybit_paper_position_balance_projection_capability_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_paper_position_balance_projection_capability_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = PROJECTION_PATH.exists()
    checks.append(check("projection_latest_exists", exists, str(PROJECTION_PATH)))

    projection: Dict[str, Any] = {}
    if exists:
        projection = load_json(PROJECTION_PATH)

    checks.append(check("projection_type_ok", projection.get("projection_type") == "bybit_paper_position_balance_projection_capability", projection.get("projection_type")))
    checks.append(check("chapter_ok", projection.get("chapter") == "K", projection.get("chapter")))
    checks.append(check(
        "projection_state_ok",
        projection.get("projection_state") in {"projection_model_defined_ledger_closed", "projection_capability_not_ready"},
        projection.get("projection_state"),
    ))
    checks.append(check("projection_ready_false", projection.get("projection_ready") is False, projection.get("projection_ready")))
    checks.append(check("projection_can_drive_paper_ledger_false", projection.get("projection_can_drive_paper_ledger") is False, projection.get("projection_can_drive_paper_ledger")))
    checks.append(check("internal_projection_model_defined_bool", isinstance(projection.get("internal_projection_model_defined"), bool), projection.get("internal_projection_model_defined")))
    checks.append(check("ledger_path_closed_true", projection.get("ledger_path_closed") is True, projection.get("ledger_path_closed")))
    checks.append(check("live_projection_closed_true", projection.get("live_projection_closed") is True, projection.get("live_projection_closed")))
    checks.append(check("runtime_still_protected_bool", isinstance(projection.get("runtime_still_protected"), bool), projection.get("runtime_still_protected")))
    checks.append(check("missing_prerequisites_list", isinstance(projection.get("missing_prerequisites"), list), projection.get("missing_prerequisites")))
    checks.append(check("blockers_list", isinstance(projection.get("blockers"), list), projection.get("blockers")))

    components = projection.get("projection_components") or []
    checks.append(check("projection_components_list", isinstance(components, list), type(components).__name__))
    if isinstance(components, list):
        component_names = [row.get("component") for row in components if isinstance(row, dict)]
    else:
        component_names = []
    required_components = {
        "paper_position_snapshot_model",
        "paper_balance_snapshot_model",
        "paper_pnl_projection_model",
        "paper_fee_projection_model",
        "paper_reserved_margin_projection_model",
    }
    checks.append(check("required_components_present", required_components.issubset(set(component_names)), component_names))

    summary = projection.get("projection_summary") or {}
    checks.append(check("component_count_int", isinstance(summary.get("component_count"), int), summary.get("component_count")))
    checks.append(check("summary_model_defined_bool", isinstance(summary.get("internal_projection_model_defined"), bool), summary.get("internal_projection_model_defined")))
    checks.append(check("summary_ledger_false", summary.get("projection_can_drive_paper_ledger") is False, summary.get("projection_can_drive_paper_ledger")))
    checks.append(check("summary_ledger_path_closed_true", summary.get("ledger_path_closed") is True, summary.get("ledger_path_closed")))
    checks.append(check("summary_missing_prereq_count_int", isinstance(summary.get("missing_prerequisite_count"), int), summary.get("missing_prerequisite_count")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_paper_position_balance_projection_capability_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "projection_shape_valid": len(failed_checks) == 0,
            "ledger_closed_boundary_preserved": (
                projection.get("projection_can_drive_paper_ledger") is False
                and projection.get("ledger_path_closed") is True
                and projection.get("live_projection_closed") is True
                and summary.get("projection_can_drive_paper_ledger") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

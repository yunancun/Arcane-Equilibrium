#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 对 K 章 paper adapter transition intent latest 做 contract check。
- 该检查确认 adapter intent 当前只表达“design-only 可形成内部 intent 包”，
  而不会错误打开 paper order submission / live execution。
- 这是对 adapter 桥接层的结构与安全边界校验，不是执行放权。

English:
- Contract-check the K paper-adapter transition-intent latest artifact.
- This verifies the adapter intent only expresses that an internal design-only intent envelope
  can be formed, without opening paper order submission or live execution.
- This is a structural and boundary validation for the adapter bridge layer, not execution authority.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without using machine-specific absolute paths.
    中文：避免未来维护时再次被单机路径绑死。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for adapter transition intent contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
INTENT_PATH = BASE / "bybit_demo_paper_adapter_transition_intent_latest.json"
OUT_LATEST = BASE / "bybit_demo_paper_adapter_transition_intent_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_demo_paper_adapter_transition_intent_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = INTENT_PATH.exists()
    checks.append(check("intent_latest_exists", exists, str(INTENT_PATH)))

    intent: Dict[str, Any] = {}
    if exists:
        intent = load_json(INTENT_PATH)

    checks.append(check("intent_type_ok", intent.get("intent_type") == "bybit_demo_paper_adapter_transition_intent", intent.get("intent_type")))
    checks.append(check("chapter_ok", intent.get("chapter") == "K", intent.get("chapter")))
    checks.append(check(
        "intent_state_ok",
        intent.get("intent_state") in {"paper_transition_intent_formable_design_only", "paper_transition_intent_not_formable"},
        intent.get("intent_state"),
    ))
    checks.append(check("intent_ready_bool", isinstance(intent.get("intent_ready"), bool), intent.get("intent_ready")))
    checks.append(check("paper_intent_formable_bool", isinstance(intent.get("paper_intent_formable"), bool), intent.get("paper_intent_formable")))
    checks.append(check("paper_order_submission_disabled", intent.get("paper_order_submission_enabled") is False, intent.get("paper_order_submission_enabled")))
    checks.append(check("live_order_submission_disabled", intent.get("live_order_submission_enabled") is False, intent.get("live_order_submission_enabled")))
    checks.append(check("runtime_still_protected_bool", isinstance(intent.get("runtime_still_protected"), bool), intent.get("runtime_still_protected")))
    checks.append(check("blockers_list", isinstance(intent.get("blockers"), list), intent.get("blockers")))

    adapter_view = intent.get("transition_adapter_view") or {}
    checks.append(check("j_decision_state_present", isinstance(adapter_view.get("j_decision_state"), str) and len(adapter_view.get("j_decision_state")) > 0, adapter_view.get("j_decision_state")))
    checks.append(check("k_decision_state_present", isinstance(adapter_view.get("k_decision_state"), str) and len(adapter_view.get("k_decision_state")) > 0, adapter_view.get("k_decision_state")))
    checks.append(check("adapter_state_expected", adapter_view.get("adapter_state") == "skeleton_defined_not_active", adapter_view.get("adapter_state")))
    checks.append(check("adapter_ready_false", adapter_view.get("adapter_ready") is False, adapter_view.get("adapter_ready")))
    checks.append(check("adapter_can_accept_orders_false", adapter_view.get("adapter_can_accept_orders") is False, adapter_view.get("adapter_can_accept_orders")))

    template = intent.get("paper_order_intent_template") or {}
    checks.append(check("template_mode_ok", template.get("mode") == "paper_design_only", template.get("mode")))
    checks.append(check("template_authority_false", template.get("order_authority_granted") is False, template.get("order_authority_granted")))
    checks.append(check("template_submission_false", template.get("submission_enabled") is False, template.get("submission_enabled")))
    checks.append(check("template_required_fields_list", isinstance(template.get("required_future_fields"), list), template.get("required_future_fields")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_demo_paper_adapter_transition_intent_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "intent_shape_valid": len(failed_checks) == 0,
            "design_only_adapter_boundary_preserved": (
                intent.get("paper_order_submission_enabled") is False
                and intent.get("live_order_submission_enabled") is False
                and template.get("order_authority_granted") is False
                and template.get("submission_enabled") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

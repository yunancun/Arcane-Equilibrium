#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_checkpoint_contract_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章阶段收口 / checkpoint
- 这一层的白话解释:
  把 J 章各层结果打包成 checkpoint，作为后续 K 章继续施工的基线。

Role:
- 校验本脚本对应输出文件的结构、版本与基础字段是否稳定。

Purpose in system:
- 防止 J 章脚本在后续维护时发生结构漂移，给 summary / handoff / final audit / checkpoint 提供稳定上游。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 contract check 层
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.9
- 该临时编号现已废弃
- 后续以 Revision 2 正式章节树为准

Maintenance notes:
- 本批修正只改头部注释归位，不改文件名、latest 路径、JSON stage 字段
- 如后续要改 stage / 输出字段，必须单独做兼容性修订
\'\'\'
"""
import json
import time
from pathlib import Path

CHECK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_checkpoint_latest.json")

OUT_DIR = CHECK_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_transition_engine_checkpoint_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_transition_engine_checkpoint_contract_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    report = load_json(CHECK_PATH)
    checks = []

    checks.append(check("checkpoint_exists", CHECK_PATH.exists(), str(CHECK_PATH)))
    checks.append(check("checkpoint_type_expected", report.get("checkpoint_type") == "bybit_transition_engine_checkpoint", report.get("checkpoint_type")))
    checks.append(check("checkpoint_version_v1", report.get("checkpoint_version") == "v1", report.get("checkpoint_version")))
    checks.append(check("stage_g4_9", report.get("stage") == "G4.9", report.get("stage")))
    checks.append(check("exchange_bybit", report.get("exchange") == "bybit", report.get("exchange")))
    checks.append(check("checkpoint_status_allowed", report.get("checkpoint_status") in {"skeleton_checkpoint_ready", "checkpoint_not_ready"}, report.get("checkpoint_status")))

    checks.append(check("runtime_safety_context_present", isinstance(report.get("runtime_safety_context"), dict), type(report.get("runtime_safety_context")).__name__))
    checks.append(check("source_refs_present", isinstance(report.get("source_refs"), dict), type(report.get("source_refs")).__name__))
    checks.append(check("checkpoint_layers_present", isinstance(report.get("checkpoint_layers"), dict), type(report.get("checkpoint_layers")).__name__))
    checks.append(check("checkpoint_conclusion_present", isinstance(report.get("checkpoint_conclusion"), dict), type(report.get("checkpoint_conclusion")).__name__))
    checks.append(check("operator_guidance_list", isinstance(report.get("operator_guidance"), list), type(report.get("operator_guidance")).__name__))

    layers = report.get("checkpoint_layers", {})
    checks.append(check("matrix_layer_present", isinstance(layers.get("matrix_layer"), dict), type(layers.get("matrix_layer")).__name__))
    checks.append(check("audit_layer_present", isinstance(layers.get("audit_layer"), dict), type(layers.get("audit_layer")).__name__))
    checks.append(check("rule_layer_present", isinstance(layers.get("rule_layer"), dict), type(layers.get("rule_layer")).__name__))
    checks.append(check("summary_layer_present", isinstance(layers.get("summary_layer"), dict), type(layers.get("summary_layer")).__name__))
    checks.append(check("handoff_layer_present", isinstance(layers.get("handoff_layer"), dict), type(layers.get("handoff_layer")).__name__))
    checks.append(check("final_audit_layer_present", isinstance(layers.get("final_audit_layer"), dict), type(layers.get("final_audit_layer")).__name__))
    checks.append(check("graph_layer_present", isinstance(layers.get("graph_layer"), dict), type(layers.get("graph_layer")).__name__))
    checks.append(check("graph_consistency_layer_present", isinstance(layers.get("graph_consistency_layer"), dict), type(layers.get("graph_consistency_layer")).__name__))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "report_type": "bybit_transition_engine_checkpoint_contract_check",
        "report_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

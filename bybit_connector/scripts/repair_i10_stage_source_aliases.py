#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

# 这些名字是给 I10 “喂更干净的 canonical source”的稳定别名
CANONICAL: Dict[str, str] = {
    "I1": "bybit_decision_lease_final_audit_latest.json",
    "I2": "bybit_decision_lease_shadow_audit_latest.json",
    "I3": "bybit_decision_lease_consume_final_audit_latest.json",
    "I4": "bybit_decision_lease_replay_final_audit_latest.json",
    "I5": "bybit_decision_lease_friction_final_audit_latest.json",
    "I6": "bybit_decision_lease_approval_bridge_final_audit_latest.json",
    "I7": "bybit_execution_authority_aggregator_final_audit_latest.json",
    "I8": "bybit_manual_approval_packet_final_audit_latest.json",
    "I9": "bybit_operator_ack_shadow_final_audit_latest.json",
}

def safe_read_json(p: Path) -> Optional[dict]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def rank_path(p: Path):
    """
    越小越优先：
    0 = final_audit
    1 = handoff
    2 = summary
    3 = audit latest（如 shadow_audit）
    4 = 其他 latest 主报告
    5 = contract
    6 = 其他
    """
    name = p.name
    if name.endswith("_final_audit_latest.json"):
        return (0, len(name), name)
    if name.endswith("_handoff_latest.json"):
        return (1, len(name), name)
    if name.endswith("_summary_latest.json"):
        return (2, len(name), name)
    if name.endswith("_audit_latest.json"):
        return (3, len(name), name)
    if name.endswith("_latest.json") and not name.endswith("_contract_latest.json"):
        return (4, len(name), name)
    if name.endswith("_contract_latest.json"):
        return (5, len(name), name)
    return (6, len(name), name)

def normalize_stage_name(stage: object) -> Optional[str]:
    if not isinstance(stage, str):
        return None
    head = stage.split("-", 1)[0]
    if head in CANONICAL:
        return head
    if stage in CANONICAL:
        return stage
    return None


def infer_stage(obj: dict, p: Path) -> Optional[str]:
    # 1) 最优先：直接看 JSON 内 stage 字段（支持 I2-C -> I2 归一）
    stage = normalize_stage_name(obj.get("stage"))
    if stage in CANONICAL:
        return stage

    name = p.name

    # 2) 文件名关键词回退
    if name == "bybit_decision_lease_final_audit_latest.json":
        return "I1"
    if "preflight" in name:
        return "I2"
    if "consume" in name:
        return "I3"
    if "replay" in name:
        return "I4"
    if "friction" in name:
        return "I5"
    if "approval_bridge" in name:
        return "I6"
    if "execution_authority_aggregator" in name:
        return "I7"
    if "manual_approval_packet" in name:
        return "I8"
    if "operator_ack" in name:
        return "I9"

    # 3) 再回退：从字段名中猜 stage
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True)

    for i in range(1, 10):
        if f'"i{i}_stage_closed"' in payload:
            return f"I{i}"

    return None

def main() -> None:
    if not BASE.exists():
        raise SystemExit(f"runtime dir not found: {BASE}")

    candidates: Dict[str, List[Path]] = {k: [] for k in CANONICAL}

    # 只扫描 latest.json；同时跳过 symlink，避免 alias 反过来污染候选集
    for p in sorted(BASE.glob("*latest.json")):
        if p.is_symlink():
            continue
        obj = safe_read_json(p)
        if not isinstance(obj, dict):
            continue
        stage = infer_stage(obj, p)
        if stage in candidates:
            candidates[stage].append(p)

    print("===== I10 STAGE SOURCE ALIAS REPAIR =====")
    repaired = 0

    for stage, alias_name in CANONICAL.items():
        alias_path = BASE / alias_name
        stage_candidates = sorted(candidates[stage], key=rank_path)

        print("")
        print(f"[{stage}] canonical = {alias_name}")

        if not stage_candidates:
            print("  status = no_candidate_found")
            continue

        best = stage_candidates[0]
        print(f"  selected = {best.name}")
        print("  candidates =")
        for cand in stage_candidates:
            print(f"    - {cand.name}")

        # 情况 A：alias 本身就是“真实文件”且正好就是最佳文件
        if alias_path.exists() and (not alias_path.is_symlink()) and alias_path.resolve() == best.resolve():
            print("  action = keep_existing_real_file")
            repaired += 1
            continue

        # 情况 B：已有 symlink
        if alias_path.is_symlink():
            current_target = alias_path.resolve()
            if current_target == best.resolve():
                print("  action = symlink_already_correct")
                repaired += 1
                continue
            alias_path.unlink()

        # 情况 C：已有普通文件，但不是最佳文件；先备份再改成 symlink
        elif alias_path.exists():
            backup = alias_path.with_name(alias_path.name + ".bak_before_i10_alias_fix")
            if not backup.exists():
                alias_path.rename(backup)
                print(f"  backup = {backup.name}")
            else:
                alias_path.unlink()

        # 建立相对 symlink
        os.symlink(best.name, alias_path)
        print(f"  action = symlink_created -> {best.name}")
        repaired += 1

    print("")
    print("===== I10 ALIAS REPAIR SUMMARY =====")
    print(f"repaired_or_confirmed = {repaired}")
    print("done = True")

if __name__ == "__main__":
    main()

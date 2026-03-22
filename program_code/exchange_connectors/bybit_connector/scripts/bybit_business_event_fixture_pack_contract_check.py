#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_business_event_fixture_pack_contract_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G1. replay fixtures / fixture pack
- 这一层的白话解释:
  构建业务事件样本包，给后续 replay harness 提供可重复使用的测试输入。

Role:
- 校验本脚本对应输出文件的结构、版本与基础字段是否稳定。

Purpose in system:
- 防止 G 章验证输出在后续维护时发生结构漂移，给 regression / consistency / handoff 提供稳定依据。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 contract check 层
- 所有 replay / negative / consistency 输出都应与主 runtime 隔离

Maintenance notes:
- 本批修正主要增强白话说明，不改变 G 章归属
- 本批修正不改文件名、latest 路径、JSON stage 字段
- 如后续要把 replay 结果真正接到更高层，必须显式经过 J / K 章节边界
\'\'\'
"""
import json
import time
from pathlib import Path

PACK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/fixtures/bybit_business_event_fixture_pack_latest.json")

OUT_DIR = PACK_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_business_event_fixture_pack_contract_latest.json"

REQUIRED_TOPICS = {"wallet", "order", "execution", "position"}


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def main():
    ts_ms = int(time.time() * 1000)
    pack = load_json(PACK_PATH)

    checks = []

    def add_check(name: str, ok: bool, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add_check("pack_exists", pack is not None, str(PACK_PATH))

    if pack is not None:
        add_check("report_type_expected", pack.get("report_type") == "bybit_business_event_fixture_pack", pack.get("report_type"))
        add_check("report_version_v1", pack.get("report_version") == "v1", pack.get("report_version"))
        add_check("exchange_bybit", pack.get("exchange") == "bybit", pack.get("exchange"))
        add_check("stage_g1_1", pack.get("stage") == "G1.1", pack.get("stage"))
        add_check("fixture_count_ge_4", int(pack.get("fixture_count", 0)) >= 4, pack.get("fixture_count"))

        fixtures = pack.get("fixtures") or []
        actual_topics = {x.get("topic") for x in fixtures if isinstance(x, dict)}
        add_check("required_topics_present", REQUIRED_TOPICS.issubset(actual_topics), sorted(actual_topics))

        all_have_source_message = all(isinstance(x.get("source_message"), dict) for x in fixtures)
        add_check("source_message_present", all_have_source_message, all_have_source_message)

        all_have_nonempty_data = all((x.get("source_message", {}).get("data") or []) for x in fixtures)
        add_check("source_message_data_nonempty", all_have_nonempty_data, all_have_nonempty_data)

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_business_event_fixture_pack_contract_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    dated = save_report(report, OUT_LATEST, "bybit_business_event_fixture_pack_contract")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

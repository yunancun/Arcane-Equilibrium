#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_business_event_negative_fixture_pack_builder.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G3. 负向阻断验证 / negative fixtures
- 这一层的白话解释:
  构建不完整的负向样本，只提供部分 topic，用来证明系统不会被错误放行。

Role:
- 生成本脚本对应的 G 章验证输出。

Purpose in system:
- 把 G. 真实业务事件验证层的对应子层固定下来，证明真实业务事件相关语义是否成立，同时不污染主 runtime。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 fixture pack
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
import os

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/fixtures_negative")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_business_event_negative_fixture_pack_latest.json"


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_business_event_negative_fixture_pack_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)

    fixtures = [
        {
            "fixture_id": "wallet_only_negative_v1",
            "topic": "wallet",
            "description": "negative-case fixture with only wallet topic",
            "source_conn_id": "fixture-negative-wallet",
            "source_sequence_hint": 1,
            "source_message": {
                "topic": "wallet",
                "type": "snapshot",
                "ts": now_ms - 60000,
                "data": [
                    {
                        "coin": "USDT",
                        "walletBalance": "610.23363",
                        "equity": "610.23363",
                        "availableToWithdraw": "610.23363",
                        "updatedTime": now_ms - 60000,
                    }
                ],
            },
        }
    ]

    report = {
        "report_type": "bybit_business_event_negative_fixture_pack",
        "report_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G3.1",
        "fixture_count": len(fixtures),
        "topic_counts": {"wallet": 1},
        "fixtures": fixtures,
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

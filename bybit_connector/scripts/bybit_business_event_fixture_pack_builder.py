#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_business_event_fixture_pack_builder.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G1. replay fixtures / fixture pack
- 这一层的白话解释:
  构建业务事件样本包，给后续 replay harness 提供可重复使用的测试输入。

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

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/fixtures")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "bybit_business_event_fixture_pack_latest.json"


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def main():
    now_ms = int(time.time() * 1000)
    base_ts = now_ms - 60_000

    fixtures = [
        {
            "fixture_id": "wallet_basic_v1",
            "topic": "wallet",
            "description": "single-coin wallet update fixture",
            "source_conn_id": "fixture-conn-wallet",
            "source_sequence_hint": 1,
            "source_message": {
                "topic": "wallet",
                "type": "snapshot",
                "ts": base_ts + 100,
                "data": [
                    {
                        "coin": "USDT",
                        "walletBalance": "610.23363",
                        "equity": "610.23363",
                        "availableToWithdraw": "610.23363",
                        "updatedTime": base_ts + 100,
                    }
                ],
            },
        },
        {
            "fixture_id": "order_basic_v1",
            "topic": "order",
            "description": "single active order fixture",
            "source_conn_id": "fixture-conn-order",
            "source_sequence_hint": 2,
            "source_message": {
                "topic": "order",
                "type": "delta",
                "ts": base_ts + 200,
                "data": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "orderId": "fixture-order-001",
                        "orderLinkId": "fixture-link-001",
                        "orderStatus": "New",
                        "qty": "0.010",
                        "price": "65000",
                        "updatedTime": base_ts + 200,
                    }
                ],
            },
        },
        {
            "fixture_id": "execution_basic_v1",
            "topic": "execution",
            "description": "single execution fixture",
            "source_conn_id": "fixture-conn-execution",
            "source_sequence_hint": 3,
            "source_message": {
                "topic": "execution",
                "type": "delta",
                "ts": base_ts + 300,
                "data": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "orderId": "fixture-order-001",
                        "execId": "fixture-exec-001",
                        "execQty": "0.010",
                        "execPrice": "64995",
                        "execTime": base_ts + 300,
                    }
                ],
            },
        },
        {
            "fixture_id": "position_basic_v1",
            "topic": "position",
            "description": "single position update fixture",
            "source_conn_id": "fixture-conn-position",
            "source_sequence_hint": 4,
            "source_message": {
                "topic": "position",
                "type": "delta",
                "ts": base_ts + 400,
                "data": [
                    {
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "size": "0.010",
                        "entryPrice": "64995",
                        "positionValue": "649.95",
                        "updatedTime": base_ts + 400,
                    }
                ],
            },
        },
    ]

    topic_counts = {}
    for item in fixtures:
        topic = item.get("topic", "")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    report = {
        "report_type": "bybit_business_event_fixture_pack",
        "report_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G1.1",
        "fixture_count": len(fixtures),
        "topic_counts": topic_counts,
        "fixtures": fixtures,
    }

    dated = save_report(report, OUT_LATEST, "bybit_business_event_fixture_pack")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

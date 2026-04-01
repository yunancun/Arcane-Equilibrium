#!/usr/bin/env python3
import json
import time


def now_ms():  # TODO: consolidate with app.utils.time_utils.now_ms
    return int(time.time() * 1000)


def main():
    ts = now_ms()

    fixtures = [
        {
            "topic": "wallet",
            "ts": ts,
            "conn_id": "fixture-conn-wallet",
            "data": [
                {
                    "coin": "USDT",
                    "walletBalance": "610.18483",
                    "equity": "610.18483",
                    "availableToWithdraw": "610.18483",
                    "updatedTime": ts
                }
            ]
        },
        {
            "topic": "position",
            "ts": ts + 1,
            "conn_id": "fixture-conn-position",
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "size": "0.001",
                    "avgPrice": "82000",
                    "positionIdx": 0,
                    "unrealisedPnl": "0.21",
                    "updatedTime": ts + 1
                }
            ]
        },
        {
            "topic": "order",
            "ts": ts + 2,
            "conn_id": "fixture-conn-order",
            "data": [
                {
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "orderId": "fixture-order-001",
                    "orderStatus": "New",
                    "orderType": "Limit",
                    "price": "4200",
                    "qty": "0.01",
                    "updatedTime": ts + 2
                }
            ]
        },
        {
            "topic": "execution",
            "ts": ts + 3,
            "conn_id": "fixture-conn-exec",
            "data": [
                {
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "orderId": "fixture-order-001",
                    "execId": "fixture-exec-001",
                    "execPrice": "4200",
                    "execQty": "0.01",
                    "execFee": "0.02",
                    "execType": "Trade",
                    "execTime": ts + 3
                }
            ]
        }
    ]

    print(json.dumps({
        "ok": True,
        "fixture_version": "v1",
        "message_count": len(fixtures),
        "messages": fixtures
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

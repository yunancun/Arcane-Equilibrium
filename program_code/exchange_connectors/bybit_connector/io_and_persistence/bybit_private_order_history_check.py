#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_private_order_history_check.py
Role:
- 读取 Bybit 订单历史只读信息
- 提供近期订单活动观察依据

Purpose in system:
- 用于 observer 判断近期是否存在挂单/订单历史
- 当前无订单历史也可以是正常状态

Upstream:
- Bybit private REST API

Downstream:
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py
- bybit_build_decision_packet.py

Maintenance notes:
- 不要把 order_count = 0 误判为系统故障
- 字段改动需同步 snapshot / packet / audit
'''

"""

import os
import sys
from pathlib import Path

BASE = Path("/home/ncyu/srv/helper_scripts/maintenance_scripts/bybit_connector")
WRAPPER = BASE / "_bybit_latest_wrapper.py"
ORIG = BASE / "bybit_private_order_history_check.py.orig"
LATEST = "/home/ncyu/srv/log_files/connector_logs/bybit_private_order_history_check_latest.json"
PREFIX = "bybit_private_order_history_check"

os.execv(sys.executable, [sys.executable, str(WRAPPER), str(ORIG), LATEST, PREFIX])

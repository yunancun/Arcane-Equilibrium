#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_private_positions_check.py
Role:
- 读取 Bybit 私有持仓只读信息
- 用于判断当前是否有非零持仓

Purpose in system:
- 作为 observer 风险判断的基础输入
- 当前常见健康状态是 position_count = 0

Upstream:
- Bybit private REST API

Downstream:
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py
- bybit_build_decision_packet.py

Maintenance notes:
- 当前“无持仓”是正常健康状态，不代表异常
- 若调整 category / symbol 逻辑，需同步检查 packet 与 verdict
'''

"""

import os
import sys
from pathlib import Path

BASE = Path("/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts")
WRAPPER = BASE / "_bybit_latest_wrapper.py"
ORIG = BASE / "bybit_private_positions_check.py.orig"
LATEST = "/home/ncyu/srv/log_files/connector_logs/bybit_private_positions_check_latest.json"
PREFIX = "bybit_private_positions_check"

os.execv(sys.executable, [sys.executable, str(WRAPPER), str(ORIG), LATEST, PREFIX])

#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_private_execution_history_check.py
Role:
- 读取 Bybit 成交历史只读信息
- 观察最近是否存在真实成交

Purpose in system:
- 为 observer 提供 execution history 上下文
- 当前 spot / linear 都可能为 0，且属于允许状态

Upstream:
- Bybit private REST API

Downstream:
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py
- bybit_build_decision_packet.py

Maintenance notes:
- 当前无成交历史是正常状态
- 若修改输出结构，需同步 snapshot payload_time_summary 与 audit
'''

"""

import os
import sys
from pathlib import Path

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/helper_scripts/maintenance_scripts/bybit_connector")
WRAPPER = BASE / "_bybit_latest_wrapper.py"
ORIG = BASE / "bybit_private_execution_history_check.py.orig"
LATEST = os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/connector_logs/bybit/bybit_private_execution_history_latest.json"
PREFIX = "bybit_private_execution_history"

os.execv(sys.executable, [sys.executable, str(WRAPPER), str(ORIG), LATEST, PREFIX])

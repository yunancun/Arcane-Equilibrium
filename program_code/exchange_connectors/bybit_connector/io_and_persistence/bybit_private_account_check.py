#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_private_account_check.py
Role:
- 读取 Bybit 私有账户只读信息
- 生成账户余额/权益相关的最新结果文件

Purpose in system:
- 是 readonly observer 链路最基础的数据源之一
- 为 preflight guard / snapshot / audit 提供账户侧输入

Upstream:
- Bybit private REST API

Downstream:
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py
- bybit_full_readonly_observer_cycle.py

Maintenance notes:
- 当前定位是只读，不允许出现任何下单或写操作
- 如修改输出字段，需同步检查 snapshot 和 guard 的字段引用
'''

"""

import os
import sys
from pathlib import Path

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/helper_scripts/maintenance_scripts/bybit_connector")
WRAPPER = BASE / "_bybit_latest_wrapper.py"
ORIG = BASE / "bybit_private_account_check.py.orig"
LATEST = os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/log_files/connector_logs/bybit_private_account_check_latest.json"
PREFIX = "bybit_private_account_check"

os.execv(sys.executable, [sys.executable, str(WRAPPER), str(ORIG), LATEST, PREFIX])

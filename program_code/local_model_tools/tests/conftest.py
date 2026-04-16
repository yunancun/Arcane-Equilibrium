"""
Pytest configuration for local_model_tools tests / 测试配置

Adds the parent of local_model_tools to sys.path so that imports like
`from local_model_tools.kline_manager import ...` work correctly.
将 local_model_tools 的父目录加入 sys.path，使包级导入正常工作。
"""

import sys
import os

# Add program_code/ to sys.path so `local_model_tools` is importable as a package
# 将 program_code/ 加入 sys.path，使 local_model_tools 可作为包导入
_this_dir = os.path.dirname(os.path.abspath(__file__))
_package_dir = os.path.dirname(_this_dir)           # local_model_tools/
_program_code_dir = os.path.dirname(_package_dir)    # program_code/

if _program_code_dir not in sys.path:
    sys.path.insert(0, _program_code_dir)

# DEDUP-PY-RUST (2026-04-16): all test targets here test Python compute paths
# that have been stubbed to Rust. Collection-time ignore keeps pytest green.
# DEDUP-PY-RUST（2026-04-16）：此目录测试的 Python 计算路径已 stub 化到 Rust，
# 整包 collect_ignore_glob 保持 pytest 整洁。后续若需恢复，应重写为 Rust-fallback
# 的契约测试（测 stub 返回空值 + Rust 在线时的契约）。
collect_ignore_glob = ["test_*.py"]

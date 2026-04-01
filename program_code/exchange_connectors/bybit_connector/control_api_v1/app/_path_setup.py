"""
Path Setup — sys.path injection for route modules under app/
路徑設定 — 為 app/ 下的路由模塊注入 sys.path

MODULE_NOTE (中文):
  本模塊統一管理 app/ 目錄下多個路由文件共用的 sys.path 注入邏輯。
  從 app/ 向上 5 級目錄回溯至 program_code/，使 local_model_tools 等模塊可被 import。
  冪等設計：重複 import 不會重複添加路徑。

  原則對應 / Principle alignment:
  - 原則 7: 路徑注入使路由模塊能導入 local_model_tools（學習/回測/進化工具），
    這些工具本身維持 Live 平面隔離。

MODULE_NOTE (English):
  Centralizes the sys.path injection logic shared by multiple route files under app/.
  Traverses 5 directory levels up from app/ to reach program_code/, enabling imports
  of local_model_tools and other modules.
  Idempotent: repeated imports will not add duplicate paths.

  Principle alignment:
  - Principle 7: Path injection enables route modules to import local_model_tools
    (learning/backtest/evolution tools), which themselves maintain Live plane isolation.

Usage in route files / 路由文件中的用法:
  import _path_setup  # noqa: F401  — ensures program_code/ is on sys.path
"""

import os
import sys

# ── 5-level dirname traversal: app/ → control_api_v1/ → bybit_connector/ → exchange_connectors/ → program_code/
# ── 5 級目錄上溯：app/ → control_api_v1/ → bybit_connector/ → exchange_connectors/ → program_code/
_app_dir = os.path.dirname(os.path.abspath(__file__))               # app/
_control_api_dir = os.path.dirname(_app_dir)                        # control_api_v1/
_bybit_connector_dir = os.path.dirname(_control_api_dir)            # bybit_connector/
_exchange_connectors_dir = os.path.dirname(_bybit_connector_dir)    # exchange_connectors/
_program_code_dir = os.path.dirname(_exchange_connectors_dir)       # program_code/

# Idempotent: only add if not already present / 冪等：僅在路徑不存在時添加
if _program_code_dir not in sys.path:
    sys.path.insert(0, _program_code_dir)

# Export for any module that needs to reference these paths directly
# 導出路徑供需要直接引用的模塊使用
APP_DIR = _app_dir
PROGRAM_CODE_DIR = _program_code_dir

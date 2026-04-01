"""
MODULE_NOTE
  (中文) 時間工具模組 — 提供統一的 now_ms() 毫秒時間戳函數，消除全域 int(time.time()*1000) 重複。
  (English) Time utility module — provides unified now_ms() millisecond timestamp function.
"""
import time

def now_ms() -> int:
    """Return current time as milliseconds since epoch. / 返回當前毫秒級時間戳。"""
    return int(time.time() * 1000)

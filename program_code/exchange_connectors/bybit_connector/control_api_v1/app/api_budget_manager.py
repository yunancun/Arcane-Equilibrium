from __future__ import annotations

"""
API Budget Manager — Monthly budget + per-tier cooldown for L1.5/L2 Claude API calls.
API 預算管理器 — L1.5/L2 Claude API 調用的月度預算 + 分層冷卻管理。

MODULE_NOTE (中文):
  從 layer2_cost_tracker.py 提取的獨立模組。
  負責月度 API 預算上限（默認 $50/月）與分層冷卻管理：
  - L1.5 冷卻 1800 秒，L2 冷卻 3600 秒
  - 月份自動重置（UTC 日曆月邊界）
  - 狀態持久化到 runtime/api_budget_state.json（原子寫入防損壞）
  - 與 Layer2CostTracker 的日預算（$2 硬上限）共存
  - 線程安全：所有公開方法由 threading.Lock 保護
  - debug_mode：can_call 始終返回 True，record_call 僅記錄不扣預算

MODULE_NOTE (English):
  Extracted from layer2_cost_tracker.py as a standalone module.
  Manages monthly API budget cap (default $50/mo) and per-tier cooldowns:
  - L1.5 cooldown 1800s, L2 cooldown 3600s
  - Automatic month reset at UTC calendar month boundary
  - State persisted to runtime/api_budget_state.json (atomic write to prevent corruption)
  - Coexists with Layer2CostTracker's daily budget ($2 hard cap)
  - Thread-safe: all public methods protected by threading.Lock
  - debug_mode: can_call always True, record_call logs without deducting budget
"""

import datetime
import json
import logging
import os
import stat
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class APIBudgetManager:
    """
    Monthly budget + per-tier cooldown manager for L1.5/L2 Claude API calls.
    月度預算 + 分層冷卻管理器，用於 L1.5/L2 Claude API 調用。

    Coexists with Layer2CostTracker's daily budget ($2 hard cap).
    與 Layer2CostTracker 的日預算（$2 硬上限）共存。

    Thread-safe: all public methods are protected by threading.Lock.
    線程安全：所有公開方法均由 threading.Lock 保護。
    """

    # Valid tier names / 合法的 tier 名稱
    _VALID_TIERS = {"l1_5", "l2"}

    # Default cooldown per tier in seconds / 每 tier 默認冷卻秒數
    _DEFAULT_COOLDOWNS: dict[str, int] = {"l1_5": 1800, "l2": 3600}

    def __init__(self, monthly_budget_usd: float = 50.0, state_dir: str | None = None,
                 debug_mode: bool = False):
        """
        Initialize budget manager with monthly cap and per-tier cooldowns.
        以月度上限和分層冷卻初始化預算管理器。

        Args:
            monthly_budget_usd: Monthly spending limit in USD / 月度花費上限（美元）
            state_dir: Directory for state persistence; uses OPENCLAW_RUNTIME_DIR env var if None
                       狀態持久化目錄；為 None 時使用 OPENCLAW_RUNTIME_DIR 環境變量
            debug_mode: If True, can_call always returns True and record_call logs without deducting budget
                        若 True，can_call 始終返回 True，record_call 僅記錄不扣預算
        """
        self._debug_mode = debug_mode
        self._monthly_budget_usd = monthly_budget_usd
        self._tier_cooldowns = dict(self._DEFAULT_COOLDOWNS)
        self._last_call_ts: dict[str, float] = {"l1_5": 0.0, "l2": 0.0}
        self._monthly_spend_usd: float = 0.0
        self._month_key: str = self._current_month_key()
        self._lock = threading.Lock()

        # State file path — no hardcoded paths (cross-platform rule)
        # 狀態文件路徑 — 不硬編碼路徑（跨平台規則）
        if state_dir is None:
            state_dir = os.environ.get(
                "OPENCLAW_RUNTIME_DIR",
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runtime")),
            )
        self._state_path = Path(state_dir) / "api_budget_state.json"

        self._load()

    @staticmethod
    def _current_month_key() -> str:
        """Return current month as 'YYYY-MM' / 返回當前月份字串 'YYYY-MM'"""
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")

    def _check_month_reset(self) -> None:
        """
        Reset monthly spend if the calendar month has changed.
        若日曆月份已變更，重置月度花費。
        """
        current = self._current_month_key()
        if current != self._month_key:
            logger.info(
                "APIBudgetManager: month rolled %s -> %s, resetting spend / 月度重置",
                self._month_key, current,
            )
            self._monthly_spend_usd = 0.0
            self._month_key = current

    def can_call(self, tier: str) -> bool:
        """
        Check if a call to the given tier is allowed (budget + cooldown).
        檢查給定 tier 是否允許調用（預算 + 冷卻）。

        Args:
            tier: 'l1_5' or 'l2' / 'l1_5' 或 'l2'

        Returns:
            True if call is allowed, False otherwise / 允許調用返回 True，否則 False
        """
        if tier not in self._VALID_TIERS:
            return False
        # Debug mode: always allow / 除錯模式：始終允許
        if self._debug_mode:
            return True

        with self._lock:
            self._check_month_reset()

            # Budget check / 預算檢查
            if self._monthly_spend_usd >= self._monthly_budget_usd:
                return False

            # Cooldown check / 冷卻檢查
            elapsed = time.time() - self._last_call_ts.get(tier, 0.0)
            if elapsed < self._tier_cooldowns.get(tier, 0):
                return False

            return True

    def record_call(self, tier: str, cost_usd: float) -> None:
        """
        Record a completed API call: accumulate cost and update cooldown timestamp.
        記錄已完成的 API 調用：累計成本並更新冷卻時間戳。

        Args:
            tier: 'l1_5' or 'l2'
            cost_usd: Cost of this call in USD / 此次調用的 USD 成本
        """
        if tier not in self._VALID_TIERS:
            logger.warning("APIBudgetManager.record_call: invalid tier '%s'", tier)
            return

        with self._lock:
            self._check_month_reset()
            self._last_call_ts[tier] = time.time()
            if not self._debug_mode:
                # Normal mode: deduct budget / 正常模式：扣除預算
                self._monthly_spend_usd = round(self._monthly_spend_usd + cost_usd, 6)
            else:
                logger.debug("APIBudgetManager debug_mode: skipping budget deduction for %s ($%.4f)", tier, cost_usd)
            self._save()

    def get_remaining_budget(self) -> float:
        """
        Return remaining monthly budget in USD.
        返回月度預算餘額（美元）。
        """
        with self._lock:
            self._check_month_reset()
            return round(max(0.0, self._monthly_budget_usd - self._monthly_spend_usd), 4)

    def set_debug_mode(self, enabled: bool) -> None:
        """Toggle debug mode at runtime / 運行時切換除錯模式"""
        self._debug_mode = enabled
        logger.info("APIBudgetManager debug_mode set to %s / 除錯模式已設為 %s", enabled, enabled)

    def get_status(self) -> dict[str, Any]:
        """
        Return full budget + cooldown status for API/GUI consumption.
        返回完整預算 + 冷卻狀態（供 API/GUI 使用）。
        """
        with self._lock:
            self._check_month_reset()
            now = time.time()
            cooldown_status: dict[str, Any] = {}
            for tier in self._VALID_TIERS:
                elapsed = now - self._last_call_ts.get(tier, 0.0)
                cd = self._tier_cooldowns.get(tier, 0)
                cooldown_status[tier] = {
                    "cooldown_seconds": cd,
                    "elapsed_seconds": round(elapsed, 1),
                    "ready": elapsed >= cd,
                }
            return {
                "month_key": self._month_key,
                "monthly_budget_usd": self._monthly_budget_usd,
                "monthly_spend_usd": round(self._monthly_spend_usd, 4),
                "remaining_usd": round(max(0.0, self._monthly_budget_usd - self._monthly_spend_usd), 4),
                "cooldowns": cooldown_status,
            }

    # ── Persistence / 持久化 ──

    def _load(self) -> None:
        """
        Load state from JSON file. If missing or corrupt, start fresh.
        從 JSON 文件加載狀態。文件缺失或損壞時從零開始。
        """
        if self._state_path.exists():
            try:
                with self._state_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self._month_key = data.get("month_key", self._current_month_key())
                self._monthly_spend_usd = data.get("monthly_spend_usd", 0.0)
                saved_ts = data.get("last_call_ts", {})
                for tier in self._VALID_TIERS:
                    self._last_call_ts[tier] = saved_ts.get(tier, 0.0)
                # Auto-reset if month has changed since last save
                # 若上次保存後月份已變更，自動重置
                self._check_month_reset()
                return
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("api_budget_state.json corrupted, reinitializing / 狀態文件損壞，重新初始化")
        # No file or corrupt — save defaults
        # 無文件或損壞 — 保存默認值
        self._save()

    def _save(self) -> None:
        """
        Atomic persist: tmp-file-then-replace to prevent corruption.
        原子持久化：tmp→replace 防止損壞。
        """
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "month_key": self._month_key,
                "monthly_budget_usd": self._monthly_budget_usd,
                "monthly_spend_usd": self._monthly_spend_usd,
                "last_call_ts": dict(self._last_call_ts),
            }
            tmp_path = self._state_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            except OSError:
                pass
            tmp_path.replace(self._state_path)
        except Exception:
            logger.warning("APIBudgetManager._save failed, non-fatal / 持久化失敗，非致命")

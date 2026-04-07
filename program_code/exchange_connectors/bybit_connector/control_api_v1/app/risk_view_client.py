from __future__ import annotations

"""
RiskViewClient — thin IPC view over Rust authoritative RiskConfig (ARCH-RC1 1C-3-B).

MODULE_NOTE (中文):
  這是 ARCH-RC1 1C-3 的核心：把 Python `RiskManager` (1633 行、7 套並行風控系統之一)
  空殼化成對 Rust 唯一權威 RiskConfig + 運行時狀態的薄 IPC 視圖。

  語義變化（重要）：
  - reads 走 `get_risk_config` / `get_risk_runtime_status` IPC，結果快取
  - writes 走 `patch_risk_config` IPC（成功後 Rust ConfigStore 會熱重載給 5 個引擎）
  - 舊 Python 風控邏輯 (check_order_allowed / check_positions_on_tick / record_fill_result /
    clear_trailing_stop / record_market_prices_for_portfolio_risk) 全部變 no-op 兼容 stub —
    真正的執行路徑在 Rust intent_processor + position_risk_evaluator 內
  - `get_status()` 回傳的 shape 已從 Python 時代的 {consecutive_losses, cooldown_active, ...}
    換成 Rust 原生 shape {governor_tier, consecutive_losses_by_symbol, ...}。GUI 需同步改
    欄位綁定（1C-3-C）
  - governor 手動 override (解鎖危險能力) 留給 1C-3-B-2 獨立 commit

MODULE_NOTE (English):
  ARCH-RC1 1C-3 core: shrinks the 1633-line Python `RiskManager` into a thin IPC view
  of the Rust-authoritative `RiskConfig` + runtime state. Reads are cached via
  `get_risk_config` / `get_risk_runtime_status`; writes forward to `patch_risk_config`
  (which triggers hot-reload across 5 downstream engines). Deprecated Python-era
  behaviour methods become no-op stubs — all real enforcement lives in Rust.

  The `get_status()` shape is deliberately Rust-native and differs from the Python
  shape; GUI must rebind fields in 1C-3-C. Governor manual override is deferred to
  1C-3-B-2.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ipc_client import EngineIPCClient

logger = logging.getLogger(__name__)

# Tracks which deprecated stub methods we've already WARN-logged, so tests and
# production don't spam a line per call. Set entries are method names.
# 已經 WARN-log 過的 deprecated stub 方法（避免每次呼叫都刷 log）。
_WARNED_DEPRECATED: set[str] = set()


def _warn_deprecated_once(method: str) -> None:
    if method not in _WARNED_DEPRECATED:
        _WARNED_DEPRECATED.add(method)
        logger.warning(
            "RiskViewClient.%s is a no-op stub post-RRC-1; the real enforcement "
            "lives in Rust intent_processor / position_risk_evaluator. Remove the "
            "caller in 1C-3-D. / 此方法為 no-op，真正執行在 Rust 側，1C-3-D 移除呼叫點。",
            method,
        )


class RiskViewClient:
    """Thin IPC view of the Rust-authoritative RiskConfig + runtime state."""

    def __init__(self, ipc_client: "EngineIPCClient | None") -> None:
        self._ipc = ipc_client
        # Cached full config from last successful get_risk_config call.
        # Start empty — any read before first refresh returns {} and logs WARN.
        # 快取最近一次 get_risk_config 成功的完整 config；refresh 前讀取回傳 {}。
        self._cached_config: dict[str, Any] = {}
        self._cached_version: int = 0
        # Cached runtime status (governor_tier / consecutive_losses_by_symbol / ...)
        # 快取最近一次 get_risk_runtime_status 的結果
        self._cached_runtime: dict[str, Any] = {}

    # ═══════════════════════════════════════════════════════════════════════
    # Refresh (background or on-demand)
    # 刷新（背景或按需）
    # ═══════════════════════════════════════════════════════════════════════

    async def refresh_config(self) -> dict[str, Any]:
        """Pull authoritative RiskConfig snapshot from Rust into local cache."""
        if self._ipc is None:
            return self._cached_config
        try:
            resp = await self._ipc.call("get_risk_config")
            if isinstance(resp, dict):
                self._cached_config = resp.get("config", {}) or {}
                self._cached_version = int(resp.get("version", 0))
        except Exception as e:
            logger.warning("refresh_config failed: %s", e)
        return self._cached_config

    async def refresh_runtime_status(self) -> dict[str, Any]:
        """Pull Rust-native risk runtime status into local cache."""
        if self._ipc is None:
            return self._cached_runtime
        try:
            resp = await self._ipc.call("get_risk_runtime_status")
            if isinstance(resp, dict):
                self._cached_runtime = resp
        except Exception as e:
            logger.warning("refresh_runtime_status failed: %s", e)
        return self._cached_runtime

    # ═══════════════════════════════════════════════════════════════════════
    # Cached reads (sync — for FastAPI/sync call sites)
    # 快取讀取（sync — 供 FastAPI/sync 呼叫點使用）
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def config(self) -> dict[str, Any]:
        """Full cached RiskConfig snapshot (dict form)."""
        return self._cached_config

    @property
    def config_version(self) -> int:
        return self._cached_version

    def get_full_config(self) -> dict[str, Any]:
        """Alias for `.config` — matches legacy `RiskManager.get_full_config()`."""
        return self._cached_config

    def get_category_config(self, category: str) -> dict[str, Any]:
        """Derive per-category config from cached snapshot."""
        overrides = self._cached_config.get("overrides", {}) or {}
        return overrides.get(category, {}) or {}

    def get_agent_params(self) -> dict[str, Any]:
        """Read P2 Agent self-tunable params from cached snapshot.
        Replaces legacy `rm.agent_params.to_dict()` (1C-3-C migration target)."""
        return self._cached_config.get("agent_p2", {}) or {}

    def get_status(self) -> dict[str, Any]:
        """
        Rust-native runtime status (governor_tier / consecutive_losses_by_symbol /
        boot_cooldown_remaining_ms / paper_paused / session_halted).

        ★ Intentional shape change from Python-era `RiskManager.get_status()`.
        GUI Risk tab must rebind fields in 1C-3-C.
        ★ 與 Python 時代 shape 刻意不同。GUI 需同步改欄位綁定。
        """
        return self._cached_runtime

    def get_risk_state_for_persistence(self) -> dict[str, Any]:
        """Compat shim for paper_state persistence — bundles config + runtime."""
        return {
            "config": self._cached_config,
            "config_version": self._cached_version,
            "runtime": self._cached_runtime,
        }

    # ═══════════════════════════════════════════════════════════════════════
    # Writes (forward to Rust ConfigStore via patch_risk_config)
    # 寫入（透過 patch_risk_config 轉發到 Rust ConfigStore）
    # ═══════════════════════════════════════════════════════════════════════

    async def update_global_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Operator-initiated global config patch."""
        return await self._patch("operator", updates)

    async def update_category_config(
        self, category: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Operator-initiated per-category override patch."""
        patch = {"overrides": {category: updates}}
        return await self._patch("operator", patch)

    async def agent_adjust(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Agent self-tuning patch (always stamped with source=agent for audit)."""
        return await self._patch("agent", updates)

    async def _patch(self, source: str, patch: dict[str, Any]) -> dict[str, Any]:
        if self._ipc is None:
            logger.warning("patch_risk_config skipped — no IPC client configured")
            return {}
        resp = await self._ipc.call(
            "patch_risk_config",
            params={"patch": patch, "source": source},
        )
        # On success refresh our local cache so the next sync read sees new values
        # 成功後刷新本地快取，下一次 sync read 能看到新值
        await self.refresh_config()
        return resp if isinstance(resp, dict) else {}

    async def unhalt_session(self) -> dict[str, Any]:
        """
        Clear Rust-side session_halted + paper_paused via `resume_paper` IPC.
        Replaces the Python-era PAPER_STORE.mutate() path. After 1C-3-D the
        Python PAPER_STORE.session_halted should derive from Rust snapshot,
        not be a parallel write.
        透過 IPC `resume_paper` 清除 Rust 端 session_halted + paper_paused，
        取代 Python 時代的 PAPER_STORE.mutate()。
        """
        if self._ipc is None:
            logger.warning("unhalt_session skipped — no IPC client")
            return {}
        resp = await self._ipc.call("resume_paper")
        await self.refresh_runtime_status()
        return resp if isinstance(resp, dict) else {}

    async def clear_consecutive_losses(self) -> dict[str, Any]:
        """
        Safe reset: clear per-symbol loss counters. Does NOT affect RiskGovernor
        tier — for tier override see `force_governor_tier_*` in 1C-3-B-2.
        安全重置：清除 per-symbol 連虧計數器（不影響 governor tier）。
        """
        if self._ipc is None:
            logger.warning("clear_consecutive_losses skipped — no IPC client")
            return {}
        resp = await self._ipc.call("clear_consecutive_losses")
        await self.refresh_runtime_status()
        return resp if isinstance(resp, dict) else {}

    # ═══════════════════════════════════════════════════════════════════════
    # Governor manual override (1C-3-B-2 — stubs for now)
    # Governor 手動 override（1C-3-B-2 實作，此處先佔位）
    # ═══════════════════════════════════════════════════════════════════════

    async def force_governor_tier_tighter(
        self, target_tier: str, reason: str
    ) -> dict[str, Any]:
        """
        Escalate RiskGovernor one level toward more restrictive (operator action).
        Allowed steps: Normal→Cautious→Reduced→Defensive→CircuitBreaker→ManualReview.
        No 24h cooldown — operator can always be more careful. Writes V014 audit.
        升級 RiskGovernor 一級（operator 行為，無冷卻）。寫入 V014 audit。
        """
        if self._ipc is None:
            logger.warning("force_governor_tier_tighter skipped — no IPC client")
            return {}
        resp = await self._ipc.call(
            "force_governor_tier_tighter",
            params={"target_tier": target_tier, "reason": reason},
        )
        await self.refresh_runtime_status()
        return resp if isinstance(resp, dict) else {}

    async def force_governor_tier_looser(
        self, target_tier: str, reason_code: str, notes: str = ""
    ) -> dict[str, Any]:
        """
        De-escalate RiskGovernor one level toward less restrictive (operator action).
        Hard guards: reason_code in {false_positive, root_cause_fixed, accept_risk},
        24h IPC cooldown, single-step only, CB / ManualReview cannot be unlocked
        from IPC. Writes V014 audit row with full payload.
        降級 RiskGovernor 一級（operator 行為）。reason_code 白名單 / 24h 冷卻 /
        CB/MR 不可解 / 寫入 V014 audit。
        """
        if self._ipc is None:
            logger.warning("force_governor_tier_looser skipped — no IPC client")
            return {}
        resp = await self._ipc.call(
            "force_governor_tier_looser",
            params={
                "target_tier": target_tier,
                "reason_code": reason_code,
                "notes": notes,
            },
        )
        await self.refresh_runtime_status()
        return resp if isinstance(resp, dict) else {}

    # ═══════════════════════════════════════════════════════════════════════
    # Deprecated no-op stubs (Python-era behaviour methods)
    # 舊 Python 行為方法 — 全部變 no-op，真實執行在 Rust
    # ═══════════════════════════════════════════════════════════════════════

    def check_order_allowed(self, *args: Any, **kwargs: Any) -> tuple[bool, str]:
        _warn_deprecated_once("check_order_allowed")
        return (True, "")

    def check_positions_on_tick(self, *args: Any, **kwargs: Any) -> list[Any]:
        _warn_deprecated_once("check_positions_on_tick")
        return []

    def record_fill_result(self, *args: Any, **kwargs: Any) -> None:
        _warn_deprecated_once("record_fill_result")

    def clear_trailing_stop(self, *args: Any, **kwargs: Any) -> None:
        _warn_deprecated_once("clear_trailing_stop")

    def record_market_prices_for_portfolio_risk(self, *args: Any, **kwargs: Any) -> None:
        _warn_deprecated_once("record_market_prices_for_portfolio_risk")

    def reset_cooldown(self) -> None:
        """Python-era API. Post-RRC-1 = alias for async clear_consecutive_losses +
        governor de-escalation, which caller should invoke explicitly."""
        _warn_deprecated_once("reset_cooldown")

    # Setters used in paper_trading_wiring.py boot path
    # paper_trading_wiring.py 啟動路徑用的 setter
    def set_governance_hub(self, *args: Any) -> None:
        _warn_deprecated_once("set_governance_hub")

    def set_change_audit_log(self, *args: Any) -> None:
        _warn_deprecated_once("set_change_audit_log")

    def set_portfolio_risk_control(self, *args: Any) -> None:
        _warn_deprecated_once("set_portfolio_risk_control")

    def set_h0_gate(self, *args: Any) -> None:
        _warn_deprecated_once("set_h0_gate")

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
    clear_trailing_stop / record_market_prices_for_portfolio_risk / set_h0_gate / 等)
    在 1C-3-D 清理中已連同呼叫點一起刪除 —
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


# ─── GUI → Rust field mapping ───────────────────────────────────────────────
# GUI 送來的平坦欄位名稱 → Rust RiskConfig 嵌套路徑 (section, rust_key)
# GUI flat field names → Rust RiskConfig nested path (section, rust_key)
_GLOBAL_TO_RUST: dict[str, tuple[str, str]] = {
    # limits section
    "max_stop_loss_pct":            ("limits", "stop_loss_max_pct"),
    "max_take_profit_pct":          ("limits", "take_profit_max_pct"),
    "tp_enabled":                   ("limits", "take_profit_enforced"),
    "max_single_position_pct":      ("limits", "position_size_max_pct"),
    "max_total_exposure_pct":       ("limits", "total_exposure_max_pct"),
    "max_correlated_exposure_pct":  ("limits", "correlated_exposure_max_pct"),
    "max_leverage":                 ("limits", "leverage_max"),
    "max_session_drawdown_pct":     ("limits", "session_drawdown_max_pct"),
    "max_daily_loss_pct":           ("limits", "daily_loss_max_pct"),
    "consecutive_loss_cooldown_count":   ("limits", "consec_loss_cooldown_count"),
    "consecutive_loss_cooldown_minutes": ("limits", "consec_loss_cooldown_min"),
    "max_holding_hours":            ("limits", "holding_hours_max"),
    "p1_risk_pct":                  ("limits", "per_trade_risk_pct"),
    "allowed_categories":           ("limits", "allowed_categories"),
    "preferred_margin_mode":        ("limits", "margin_mode"),
    "preferred_position_mode":      ("limits", "position_mode"),
    # anti_cluster section
    "max_same_direction_positions": ("anti_cluster", "max_same_direction"),
    # agent section
    "trailing_stop_pct":            ("agent", "trailing_distance_pct"),
    # dynamic_stop section
    "atr_multiplier":               ("dynamic_stop", "atr_stop_mult"),
    # runtime section
    "h0_shadow_mode":               ("runtime", "h0_shadow_mode"),
}

# Agent self-adjust fields → Rust agent section
# Agent 自調整欄位 → Rust agent 區段
_AGENT_TO_RUST: dict[str, str] = {
    "effective_stop_loss_pct":     "stop_loss_pct",
    "effective_take_profit_pct":   "take_profit_pct",
    "trailing_stop_enabled":       "trailing_enabled",
    "trailing_stop_activation_pct": "trailing_activation_pct",
    "trailing_stop_distance_pct":  "trailing_distance_pct",
    "position_size_multiplier":    "size_multiplier",
    "prefer_limit_over_market":    "prefer_limit",
    "use_reduce_only_for_close":   "reduce_only_close",
    "use_post_only_for_limit":     "post_only_limit",
    "category_preference_weights": "category_weights",
}

# Category override fields → Rust CategoryOverride fields
# 分類覆蓋欄位 → Rust CategoryOverride 欄位
_CATEGORY_TO_RUST: dict[str, str] = {
    "enabled":                 "enabled",
    "max_leverage":            "leverage_max",
    "max_single_position_pct": "position_size_max_pct",
    "max_total_exposure_pct":  "total_exposure_max_pct",
    "max_stop_loss_pct":       "stop_loss_max_pct",
    "max_holding_hours":       "holding_hours_max",
    "allowed_symbols":         "allowed_symbols",
    "spot_allow_margin":       "spot_margin_allowed",
}


def _remap_global_to_rust(flat: dict[str, Any]) -> dict[str, Any]:
    """Convert flat GUI field names to Rust nested config patch format.
    Unknown fields are dropped (not forwarded) to avoid silent top-level injection.
    / 把 GUI 平坦欄位轉為 Rust 嵌套 patch。未知欄位直接捨棄。
    """
    nested: dict[str, Any] = {}
    for key, value in flat.items():
        if key in _GLOBAL_TO_RUST:
            section, rust_key = _GLOBAL_TO_RUST[key]
            # GUI sends p1_risk_pct as percent (e.g. 3.0 = 3%); Rust stores it
            # as fraction (0.03). Normalise here so the GUI can stay percent-native.
            # GUI 用百分比（3.0 = 3%），Rust 內部用小數（0.03），此處統一換算。
            if rust_key == "per_trade_risk_pct" and isinstance(value, (int, float)) and value > 1:
                value = value / 100.0
            nested.setdefault(section, {})[rust_key] = value
        else:
            logger.debug("_remap_global_to_rust: unknown field %r dropped", key)
    return nested


def _remap_agent_to_rust(flat: dict[str, Any]) -> dict[str, Any]:
    """Map agent-adjust field names to Rust agent section.
    / 把 agent-adjust 欄位映射到 Rust agent 區段。
    """
    agent: dict[str, Any] = {}
    for key, value in flat.items():
        rust_key = _AGENT_TO_RUST.get(key)
        if rust_key:
            agent[rust_key] = value
        else:
            logger.debug("_remap_agent_to_rust: unknown field %r dropped", key)
    return {"agent": agent} if agent else {}


def _remap_category_to_rust(flat: dict[str, Any]) -> dict[str, Any]:
    """Map category override field names to Rust CategoryOverride fields.
    / 把分類覆蓋欄位映射到 Rust CategoryOverride 欄位。
    """
    mapped: dict[str, Any] = {}
    for key, value in flat.items():
        rust_key = _CATEGORY_TO_RUST.get(key)
        if rust_key:
            mapped[rust_key] = value
        else:
            logger.debug("_remap_category_to_rust: unknown field %r dropped", key)
    return mapped


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
        """Operator-initiated global config patch.
        Maps flat GUI field names to Rust nested config format before patching.
        Cross-Config field `max_cost_edge_ratio` is split off and routed to
        BudgetConfig.attention_tax.cost_edge_max_ratio via patch_budget_config
        (closes Task #8 — was a silent dead-write before).
        / 將 GUI 平坦欄位映射為 Rust 嵌套 config 格式。跨 Config 欄位
        `max_cost_edge_ratio` 拆出來經 patch_budget_config 路由到
        BudgetConfig.attention_tax.cost_edge_max_ratio（閉合 Task #8）。
        """
        # CFG-COST-EDGE-1: route max_cost_edge_ratio to BudgetConfig
        cost_edge = updates.pop("max_cost_edge_ratio", None) if isinstance(updates, dict) else None
        nested = _remap_global_to_rust(updates)
        result: dict[str, Any] = {}
        if nested:
            result = await self._patch("operator", nested)
        if cost_edge is not None and self._ipc is not None:
            try:
                await self._ipc.call(
                    "patch_budget_config",
                    params={
                        "patch": {"attention_tax": {"cost_edge_max_ratio": float(cost_edge)}},
                        "source": "operator",
                    },
                )
            except Exception as e:
                logger.error("patch_budget_config(cost_edge_max_ratio) failed: %s", e)
                raise
        return result

    async def update_category_config(
        self, category: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Operator-initiated per-category override patch.
        Remaps flat GUI field names to Rust CategoryOverride field names.
        / 把 GUI 平坦欄位映射到 Rust CategoryOverride 欄位後再 patch。
        """
        mapped = _remap_category_to_rust(updates)
        patch = {"overrides": {category: mapped}}
        return await self._patch("operator", patch)

    async def agent_adjust(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Agent self-tuning patch (always stamped with source=agent for audit).
        Remaps agent-adjust field names to Rust agent section fields.
        / 把 agent-adjust 欄位映射到 Rust agent 區段後再 patch。
        """
        nested = _remap_agent_to_rust(updates)
        if not nested:
            logger.warning("agent_adjust: no mappable fields in %r", list(updates))
            return {}
        return await self._patch("agent", nested)

    async def _patch(self, source: str, patch: dict[str, Any]) -> dict[str, Any]:
        if self._ipc is None:
            logger.warning("patch_risk_config skipped — no IPC client configured")
            raise RuntimeError("patch_risk_config: no IPC client configured")
        prev_version = self._cached_version
        resp = await self._ipc.call(
            "patch_risk_config",
            params={"patch": patch, "source": source},
        )
        # On success refresh our local cache so the next sync read sees new values
        # 成功後刷新本地快取，下一次 sync read 能看到新值
        await self.refresh_config()
        # ARCH-RC1 fake-success guard: if Rust accepted the patch, ConfigStore version
        # MUST advance. If it didn't, Rust silently dropped the patch — surface as error
        # rather than letting the GUI show "Saved!" while displaying stale values.
        # 寫後驗證：patch 成功後 ConfigStore version 必須前進；否則 Rust 靜默丟棄了
        # patch，回報錯誤而非讓 GUI 顯示「已保存」但實際是舊值。
        if self._cached_version <= prev_version:
            logger.error(
                "patch_risk_config returned but version did not advance "
                "(prev=%d cur=%d source=%s patch_keys=%s) — treating as silent failure",
                prev_version, self._cached_version, source, list(patch.keys()),
            )
            raise RuntimeError(
                f"patch_risk_config: ConfigStore version did not advance "
                f"(prev={prev_version} cur={self._cached_version}) — silent IPC drop"
            )
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

    async def reset_drawdown_baseline(self, engine: str) -> dict[str, Any]:
        """
        P1-5 A2: Operator-driven drawdown baseline reset for the selected engine.

        Equalises `peak_balance = balance` in memory, clears `forced_drawdown`,
        and DELETEs the `trading.paper_state_checkpoint` row so the next
        restart cold-starts the drawdown envelope. This is the ONLY path that
        lowers `peak_balance`; restarts never do it automatically (fail-closed
        per Root Principle #5 生存>利潤 / #6 失敗默認收縮).

        P1-5 A2：Operator 手動重置所選引擎的 drawdown 基準。記憶體中
        `peak_balance = balance`、清除 `forced_drawdown`，並 DELETE
        `trading.paper_state_checkpoint` 對應 row；下次啟動即冷起。此為
        **唯一**可降 peak 的路徑，重啟永不自動降（根原則 #5/#6 fail-closed）。

        Args:
            engine: engine mode — one of `paper`, `demo`, `live`, `live_demo`.
                    Routed to the correct pipeline via IPC `engine` param.

        Returns:
            Raw IPC response dict; caller is responsible for writing
            change_audit_log per Root Principle #8 (交易可解釋).
        """
        if self._ipc is None:
            logger.warning("reset_drawdown_baseline skipped — no IPC client")
            return {}
        resp = await self._ipc.call("reset_drawdown_baseline", {"engine": engine})
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


"""Risk-config IPC payload builder split from ``ipc_client``.
自 ``ipc_client`` 抽出的 risk-config IPC payload builder。
"""

from __future__ import annotations

from typing import Any


def build_update_risk_config_params(
    *,
    unset_marker: Any,
    hard_stop_pct: float | None = None,
    p1_risk_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    time_stop_hours: float | None = None,
    atr_multiplier: float | None = None,
    take_profit_pct: float | None = None,
    max_leverage: float | None = None,
    max_drawdown_pct: float | None = None,
    max_same_direction_positions: int | None = None,
    h0_shadow_mode: bool | None = None,
    exit_stale_peak_ms: int | None = None,
) -> dict[str, Any]:
    """Build ``update_risk_config`` params and fail fast on invalid local inputs.
    構造 ``update_risk_config`` params，並在本地輸入非法時先 fail-fast。
    """
    params: dict[str, Any] = {}
    if hard_stop_pct is not None:
        params["hard_stop_pct"] = hard_stop_pct
    if p1_risk_pct is not None:
        params["p1_risk_pct"] = p1_risk_pct
    if trailing_stop_pct is not unset_marker:
        params["trailing_stop_pct"] = trailing_stop_pct
    if time_stop_hours is not unset_marker:
        params["time_stop_hours"] = time_stop_hours
    if atr_multiplier is not unset_marker:
        params["atr_multiplier"] = atr_multiplier
    if take_profit_pct is not unset_marker:
        params["take_profit_pct"] = take_profit_pct
    if max_leverage is not None:
        params["max_leverage"] = max_leverage
    if max_drawdown_pct is not None:
        params["max_drawdown_pct"] = max_drawdown_pct
    if max_same_direction_positions is not None:
        params["max_same_direction_positions"] = max_same_direction_positions
    if h0_shadow_mode is not None:
        params["h0_shadow_mode"] = h0_shadow_mode
    if exit_stale_peak_ms is not None:
        if exit_stale_peak_ms < 0:
            raise ValueError(
                f"exit_stale_peak_ms must be >= 0 (got {exit_stale_peak_ms}); "
                f"Rust ExitConfig.stale_peak_ms is i64 milliseconds and "
                f"validate() rejects negative values"
            )
        params["exit_stale_peak_ms"] = exit_stale_peak_ms
    return params

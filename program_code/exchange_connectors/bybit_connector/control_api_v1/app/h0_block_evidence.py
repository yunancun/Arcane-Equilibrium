"""H0 block evidence read-model for Control API routes.
Control API 使用的 H0 阻擋證據唯讀模型。

Rust pipeline snapshot 是 H0 Gate 真值；本 Module 只把 snapshot 投影成
operator-facing evidence，避免 route handler 重複理解 GateStats shape。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


H0_REASON_KEYS: tuple[tuple[str, str], ...] = (
    ("freshness", "blocked_freshness"),
    ("health", "blocked_health"),
    ("eligibility", "blocked_eligibility"),
    ("envelope", "blocked_envelope"),
    ("cooldown", "blocked_cooldown"),
)


@dataclass(frozen=True)
class H0GateEvidence:
    """單一 engine snapshot 投影出的 H0 Gate evidence。"""

    by_reason: dict[str, int] = field(default_factory=dict)
    total_blocked: int = 0
    total_checks: int = 0
    allow_rate_pct: float = 0.0
    h0_shadow_mode: bool | None = None
    last_check_at_utc: str | None = None

    @classmethod
    def from_snapshot(cls, snap: dict[str, Any]) -> H0GateEvidence:
        by_reason, total_blocked, total_checks = h0_reason_breakdown(
            snap.get("h0_gate_stats")
        )
        return cls(
            by_reason=by_reason,
            total_blocked=total_blocked,
            total_checks=total_checks,
            allow_rate_pct=allow_rate_pct(total_blocked, total_checks),
            h0_shadow_mode=extract_h0_shadow_mode(snap),
            last_check_at_utc=written_at_ms_to_utc(snap.get("written_at_ms")),
        )


def _as_int(raw: Any) -> int:
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def h0_reason_breakdown(
    gate_stats: dict[str, Any] | None,
) -> tuple[dict[str, int], int, int]:
    """從 Rust GateStats dict 抽出 reason counters + totals。"""

    if not isinstance(gate_stats, dict):
        return ({}, 0, 0)
    by_reason = {
        public_key: _as_int(gate_stats.get(snapshot_key, 0))
        for public_key, snapshot_key in H0_REASON_KEYS
    }
    total_blocked = sum(by_reason.values())
    total_checks = _as_int(gate_stats.get("total_checks", 0))
    return (by_reason, total_blocked, total_checks)


def allow_rate_pct(total_blocked: int, total_checks: int) -> float:
    """計算 H0 放行率百分比。"""

    if total_checks <= 0:
        return 0.0
    return (total_checks - total_blocked) / total_checks * 100.0


def extract_h0_shadow_mode(snap: dict[str, Any]) -> bool | None:
    """從 snapshot.risk_manager_config.runtime 抽 h0_shadow_mode。"""

    risk_cfg = snap.get("risk_manager_config") or {}
    runtime = risk_cfg.get("runtime") or {}
    val = runtime.get("h0_shadow_mode")
    return bool(val) if isinstance(val, bool) else None


def written_at_ms_to_utc(raw: Any) -> str | None:
    """把 snapshot.written_at_ms 轉成 ISO UTC 字串。"""

    if not isinstance(raw, (int, float)) or raw <= 0:
        return None
    return datetime.fromtimestamp(raw / 1000.0, tz=timezone.utc).isoformat(
        timespec="seconds"
    )

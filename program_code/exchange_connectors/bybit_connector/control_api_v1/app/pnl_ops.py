from __future__ import annotations

"""
MODULE_NOTE (中文):
  PnL 與經營指標操作模塊。包含 PnL 條目錄入、經營摘要構建、周期快照保存、
  Net PnL 儀表盤構建等函數。從 main_legacy.py 拆分而來。

  ★ 寫操作通過 _base.STORE / _base.get_latest_snapshot() 間接訪問單例。

MODULE_NOTE (English):
  PnL and business metrics operations module. Contains PnL entry recording,
  business summary builder, period snapshot saving, and Net PnL dashboard builder.
  Extracted from main_legacy.py.

  ★ Write operations access singletons indirectly via _base.STORE / _base.get_latest_snapshot().
"""

import copy
import logging
from typing import Any

from fastapi import HTTPException

from . import main_legacy as _base
from .auth import AuthenticatedActor, require_scope_and_identity
from .state_compiler import _compile_for_response, now_ms
from .state_helpers import (
    _assert_revision,
    _bump_revision,
    _check_idempotency,
    _store_idempotent_response,
    _write_audit_fields,
)
from .state_models import RequestEnvelope

logger = logging.getLogger(__name__)


# ── PnL 条目录入 / PnL Entry Input ──────────────────────────────────────────



def apply_pnl_entry(envelope: RequestEnvelope, actor: AuthenticatedActor) -> tuple[dict[str, Any], str]:
    """
    录入一条 PnL 更新记录 / Record a PnL update entry.

    payload 字段（均可选）/ payload fields (all optional):
    - entry_type: str  例如 "realized" | "unrealized" | "manual_adjustment"
    - realized_pnl: float  当次已实现盈亏增量 / realized PnL delta for this entry
    - unrealized_pnl: float  当前未实现盈亏（取最新值）/ current unrealized PnL (snapshot, not delta)
    - symbol: str  涉及标的 / symbol involved
    - note: str  备注 / note
    - category: str  成本/盈亏类型分类，用于 cost_breakdown

    注意：unrealized_pnl 取最新值覆盖（snapshot），realized_pnl 是累计增量。
    Note: unrealized_pnl is a snapshot (overwrite); realized_pnl is an accumulative delta.
    """
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "input:cost", envelope)  # 复用 cost scope / reuse cost scope for PnL writes
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        payload = dict(envelope.payload)
        payload["recorded_ts_ms"] = now_ms()
        payload["recorded_by"] = actor.actor_id

        entry_type = str(payload.get("entry_type", "manual_adjustment"))
        delta_realized = float(payload.get("realized_pnl", 0.0))
        delta_unrealized = float(payload.get("unrealized_pnl", 0.0))
        has_unrealized = "unrealized_pnl" in envelope.payload

        # 确保 pnl_entries 列表存在（兼容旧快照文件）
        # Ensure pnl_entries list exists (backward-compatible with old state files)
        if "pnl_entries" not in state["records"]:
            state["records"]["pnl_entries"] = []
        state["records"]["pnl_entries"].append(payload)

        # 更新每日 PnL / Update daily PnL metrics
        daily = state["business_metrics"]["daily"]
        daily["realized_pnl"] = daily.get("realized_pnl", 0.0) + delta_realized
        if has_unrealized:
            # unrealized 取最新快照值，不累加 / unrealized is a snapshot value, not accumulated
            daily["unrealized_pnl"] = delta_unrealized
        daily["gross_pnl"] = daily["realized_pnl"] + daily.get("unrealized_pnl", 0.0)
        daily["net_operating_pnl"] = daily["gross_pnl"] - daily.get("total_cost", 0.0)

        audit_ref = _write_audit_fields(
            state,
            action_type="pnl_entry",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "accepted": True,
                "entry_type": entry_type,
                "delta_realized_pnl": delta_realized,
                "delta_unrealized_pnl": delta_unrealized,
                "record_count_delta": 1,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    payload = envelope.payload
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {
            "accepted": True,
            "entry_type": str(payload.get("entry_type", "manual_adjustment")),
            "delta_realized_pnl": float(payload.get("realized_pnl", 0.0)),
            "delta_unrealized_pnl": float(payload.get("unrealized_pnl", 0.0)),
            "record_count_delta": 1,
        },
        "snapshot": final_state,
    }, "success"


# ── 经营摘要构建器 / Business Summary Builder ────────────────────────────────

_MAX_RECENT_ENTRIES: int = 20  # 每次最多返回多少条历史记录 / Max entries returned per call


def build_business_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建完整的经营与收益汇总 / Build a complete business and income summary.

    包含：每日 PnL 指标 + 最近费用条目 + 最近事件条目 + 最近 PnL 条目 + 成本分类合计
    Includes: daily PnL metrics + recent cost entries + recent event entries
              + recent PnL entries + cost breakdown by category
    """
    daily = copy.deepcopy(snapshot["business_metrics"]["daily"])
    records = snapshot.get("records", {})

    cost_entries: list[dict[str, Any]] = records.get("cost_entries", [])
    event_entries: list[dict[str, Any]] = records.get("event_entries", [])
    pnl_entries: list[dict[str, Any]] = records.get("pnl_entries", [])

    # 取最近 N 条，按最新在前排列 / Take last N, newest first
    cost_recent = list(reversed(cost_entries[-_MAX_RECENT_ENTRIES:]))
    event_recent = list(reversed(event_entries[-_MAX_RECENT_ENTRIES:]))
    pnl_recent = list(reversed(pnl_entries[-_MAX_RECENT_ENTRIES:]))

    # 按 category 做成本分解 / Compute cost breakdown by category
    cost_breakdown: dict[str, float] = {}
    for entry in cost_entries:
        category = str(entry.get("category", "manual"))
        cost_breakdown[category] = round(
            cost_breakdown.get(category, 0.0) + float(entry.get("amount", 0.0)),
            8,
        )

    return {
        "daily": daily,
        "cost_entries_recent": cost_recent,
        "event_entries_recent": event_recent,
        "pnl_entries_recent": pnl_recent,
        "cost_breakdown": cost_breakdown,
        "entry_totals": {
            "total_cost_entries": len(cost_entries),
            "total_event_entries": len(event_entries),
            "total_pnl_entries": len(pnl_entries),
        },
    }



def apply_pnl_period_snapshot(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    保存当前经营指标为周期快照 / Save current business metrics as a period snapshot.

    用于 Net PnL 趋势追踪：Operator 手动冻结当前时刻的经营指标。
    For Net PnL trend tracking: Operator manually freezes current-moment business metrics.

    payload 必填字段 / Required payload fields:
    - period_label: str  周期标签，例如 "2026-03-26" / Period label, e.g. "2026-03-26"
    """
    snapshot, _ = _base.get_latest_snapshot()
    require_scope_and_identity(actor, "input:cost", envelope)  # 复用 cost scope / Reuse cost scope
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    period_label = str(p.get("period_label", "")).strip()
    if not period_label:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_period_label"]})

    ts = now_ms()

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        daily = state["business_metrics"]["daily"]

        # 构建成本分解快照 / Build cost breakdown snapshot
        cost_breakdown: dict[str, float] = {}
        for entry in state.get("records", {}).get("cost_entries", []):
            cat = str(entry.get("category", "manual"))
            cost_breakdown[cat] = round(cost_breakdown.get(cat, 0.0) + float(entry.get("amount", 0.0)), 8)

        period_record = {
            "snapshot_ts_ms": ts,
            "period_label": period_label,
            "realized_pnl": daily.get("realized_pnl", 0.0),
            "unrealized_pnl": daily.get("unrealized_pnl", 0.0),
            "gross_pnl": daily.get("gross_pnl", 0.0),
            "total_cost": daily.get("total_cost", 0.0),
            "net_operating_pnl": daily.get("net_operating_pnl", 0.0),
            "cost_breakdown": cost_breakdown,
            "recorded_by": actor.actor_id,
        }

        # 确保 period_snapshots 列表存在（兼容旧快照文件）
        # Ensure period_snapshots list exists (backward-compatible)
        state["business_metrics"].setdefault("period_snapshots", []).append(period_record)

        audit_ref = _write_audit_fields(
            state, action_type="pnl_period_snapshot", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = _compile_for_response(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted": True, "record_count_delta": 1},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        return compiled

    final_state = _base.STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"



def build_net_pnl_dashboard(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建含所有成本分解的净 PnL 仪表盘 / Build Net PnL dashboard with full cost breakdown.

    整合：每日经营指标 + 成本分类 + 周期快照趋势 + 最近录入条目。
    Integrates: daily business metrics + cost categories + period snapshot trends + recent entries.
    """
    daily = copy.deepcopy(snapshot["business_metrics"]["daily"])
    records = snapshot.get("records", {})
    bm = snapshot.get("business_metrics", {})

    cost_entries = records.get("cost_entries", [])
    pnl_entries = records.get("pnl_entries", [])
    period_snapshots = bm.get("period_snapshots", [])

    # 成本分解 / Cost breakdown
    cost_breakdown: dict[str, float] = {}
    for entry in cost_entries:
        cat = str(entry.get("category", "manual"))
        cost_breakdown[cat] = round(cost_breakdown.get(cat, 0.0) + float(entry.get("amount", 0.0)), 8)

    # 趋势数据：从周期快照提取 net_operating_pnl 序列
    # Trend data: extract net_operating_pnl series from period snapshots
    net_pnl_trend = [
        {
            "period_label": ps.get("period_label", ""),
            "net_operating_pnl": ps.get("net_operating_pnl", 0.0),
            "gross_pnl": ps.get("gross_pnl", 0.0),
            "total_cost": ps.get("total_cost", 0.0),
            "snapshot_ts_ms": ps.get("snapshot_ts_ms", 0),
        }
        for ps in period_snapshots
    ]

    return {
        "daily": daily,
        "cost_breakdown": cost_breakdown,
        "period_snapshots": list(reversed(period_snapshots[-_MAX_RECENT_ENTRIES:])),
        "pnl_entries_recent": list(reversed(pnl_entries[-_MAX_RECENT_ENTRIES:])),
        "cost_entries_recent": list(reversed(cost_entries[-_MAX_RECENT_ENTRIES:])),
        "net_pnl_trend": net_pnl_trend,
        "entry_totals": {
            "total_cost_entries": len(cost_entries),
            "total_pnl_entries": len(pnl_entries),
            "total_period_snapshots": len(period_snapshots),
        },
    }


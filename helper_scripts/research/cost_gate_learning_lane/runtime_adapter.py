#!/usr/bin/env python3
"""Admission and ledger adapter for the cost-gate demo learning lane.

The policy artifact selects side-cells that may be worth a bounded demo probe.
This module turns that artifact into a deterministic admission decision and an
append-only JSONL ledger contract. It deliberately does not submit orders,
connect to PG, call Bybit, or mutate runtime config. Actual exchange routing
must be wired in the Rust hot path after explicit operator authority exists.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.contract import (
    ADAPTER_SCHEMA_VERSION,
    ADMIT_DECISION,
    AUTHORITY_PATH_PATCH_READY_STATUS,
    BOUNDED_PROBE_AUTHORIZED_STATUS,
    BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ELIGIBLE_REJECT_REASON_CODE,
    ORDER_AUTHORITY_GRANTED,
    OUTCOME_ADAPTER_SCHEMA_VERSION,
)
from cost_gate_learning_lane.candidate_evaluation_context import (
    validate_candidate_event_context,
)
from cost_gate_learning_lane.ledger_rotation import (
    maybe_rotate_ledger,
    retained_ledger_files,
)
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
    build_probe_outcome_records,
    read_price_observations,
)
from cost_gate_learning_lane.policy import DEMO_LEARNING_LANE_SCHEMA_VERSION
from cost_gate_learning_lane.proof_exclusion import proof_exclusion_reasons


CANDIDATE_EVENT_CONTEXT_VALID_STATUS = "VALID"
CANDIDATE_EVENT_CONTEXT_UNQUALIFIED_STATUS = "UNQUALIFIED_CONTEXT_MISSING"


@dataclass(frozen=True)
class RuntimeAdmissionConfig:
    """Runtime-side guardrails for probe admission decisions."""

    max_plan_age_hours: int = 24
    # P2-7:n=2 對 ±75bps 效應量兩向都近擲硬幣(誤殺率 ~42%)=負淨貢獻 gate。UCB-futility
    # 規則需 n≥8 才禁用;此常數是「觸發禁用檢定的最小樣本」,非 probe 預算。與 Rust
    # AdmissionConfig::default() 逐值對齊(demo_learning_lane.rs)。
    min_failed_outcomes_to_disable: int = 8
    # P2-7 起 net_positive_pct 腿已從禁用規則刪除;此欄仍供 review/報表消費,不再 gate 禁用。
    min_outcome_net_positive_pct: float = 50.0
    min_avg_net_bps: float = 0.0


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    # B2（冷審計 R2）：naive datetime（無 tz offset）一律拒收，不再默認視為 UTC。
    # 為什麼 fail-closed：Rust 側 validate_operator_authorization_envelope 以
    # DateTime::parse_from_rfc3339 嚴格要求 offset（demo_learning_lane.rs），
    # Python 寬鬆接受會造成同一 envelope 跨語言 accept/reject 分歧；統一嚴格側，
    # 存疑輸入默認收縮。
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


def _int(value: Any, default: int = 0) -> int:
    # B3（冷審計 R2）：字串數值（如 "5"）一律回 default，不再靜默轉型。
    # 為什麼：Rust 側 serde Option<u64> 對 JSON 字串 reject，Python 若接受 "5"
    # 會造成同一 envelope 兩側判定分歧；default=0 在下游一律走「缺失/無效」
    # 分支（fail-closed 方向）。
    if isinstance(value, str):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def validate_ledger_event_candidate_context(
    event: Mapping[str, Any],
) -> dict[str, Any]:
    """驗證並綁定 ledger event 的 prospective context；缺欄保留 legacy shape。

    為什麼 fail-closed：只驗 event hash 仍可把合法 context graft 到另一個 outer
    event；七個 event-time identity 欄位必須型別與值都完全相等，且不得回填。
    """
    validated_event = dict(event)
    if "candidate_event_context" not in validated_event:
        return validated_event
    context = validate_candidate_event_context(
        validated_event["candidate_event_context"]
    )
    bindings = (
        ("strategy_name", "strategy_name"),
        ("symbol", "symbol"),
        ("side", "side"),
        ("context_id", "context_id"),
        ("signal_id", "signal_id"),
        ("engine_mode", "evidence_engine_mode"),
        ("ts_ms", "captured_at_ms"),
    )
    for outer_field, context_field in bindings:
        outer_value = validated_event.get(outer_field)
        context_value = context[context_field]
        if (
            outer_field not in validated_event
            or type(outer_value) is not type(context_value)
            or outer_value != context_value
        ):
            raise ValueError(
                "CANDIDATE_EVENT_CONTEXT_OUTER_BINDING_MISMATCH:"
                f"{outer_field}"
            )
    validated_event["candidate_event_context"] = context
    return validated_event


def side_cell_key(strategy_name: Any, symbol: Any, side: Any) -> str:
    return "|".join([_str(strategy_name), _str(symbol).upper(), _str(side)])


def normalize_reject_reason_code(value: Any) -> str:
    text = _str(value)
    lowered = text.lower()
    if lowered == ELIGIBLE_REJECT_REASON_CODE:
        return ELIGIBLE_REJECT_REASON_CODE
    negative_markers = (
        "negative" in lowered
        or "estimated=-" in lowered
        or "< 0" in lowered
        or "負估計" in text
        or "負" in text and "阻擋" in text
    )
    if "cost_gate(js-demo)" in lowered and negative_markers:
        return ELIGIBLE_REJECT_REASON_CODE
    if "cost_gate" in lowered and "js-demo" in lowered and negative_markers:
        return ELIGIBLE_REJECT_REASON_CODE
    return lowered


def validate_runtime_config(cfg: RuntimeAdmissionConfig) -> None:
    if cfg.max_plan_age_hours < 1 or cfg.max_plan_age_hours > 24 * 14:
        raise ValueError("--max-plan-age-hours must be in [1, 336]")
    if cfg.min_failed_outcomes_to_disable < 1 or cfg.min_failed_outcomes_to_disable > 20:
        raise ValueError("--min-failed-outcomes-to-disable must be in [1, 20]")
    if cfg.min_outcome_net_positive_pct < 0.0 or cfg.min_outcome_net_positive_pct > 100.0:
        raise ValueError("--min-outcome-net-positive-pct must be in [0, 100]")
    if cfg.min_avg_net_bps < -10_000.0 or cfg.min_avg_net_bps > 10_000.0:
        raise ValueError("--min-avg-net-bps must be in [-10000, 10000]")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def read_jsonl_ledger(path: Path) -> list[dict[str, Any]]:
    """讀取 retention 窗內的完整 ledger 視圖(輪轉段升冪 + 主檔)。

    P1-10:輪轉後主檔只剩最新段,消費者的 dedup / outcome join 語義需要
    retention 窗內全量行,故此處跨段讀;成本由 50MB 輪轉 + 14d retention 封頂
    (修前為無界單檔全量讀)。逐行 streaming 讀,避免整檔 read_text 的雙倍峰值
    記憶體。
    """
    rows: list[dict[str, Any]] = []
    for file_path in retained_ledger_files(path):
        with file_path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"malformed JSONL ledger at {file_path}:{line_no}"
                    ) from exc
                if isinstance(row, dict):
                    summary = row.get("candidate_summary")
                    summary_has_context = isinstance(summary, Mapping) and (
                        "candidate_event_context" in summary
                        or "candidate_event_context_status" in summary
                    )
                    if isinstance(row.get("event"), Mapping):
                        row = dict(row)
                        row["event"] = validate_ledger_event_candidate_context(row["event"])
                        if (
                            "candidate_event_context" in row["event"]
                            or summary_has_context
                        ):
                            row["candidate_summary"] = (
                                _candidate_summary_with_event_context(
                                    _dict(summary),
                                    row["event"],
                                )
                            )
                    elif summary_has_context:
                        # 為什麼 fail-closed：summary-only VALID/context 無 outer event
                        # 可供 identity binding，不能把缺失/非 object event 當 legacy。
                        _candidate_summary_with_event_context(_dict(summary), {})
                    rows.append(row)
    return rows


def append_jsonl_ledger(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # P1-10:append 前檢查輪轉(fast path 僅一次 stat)。輪轉細節與並發安全
    # 論證見 ledger_rotation.py MODULE_NOTE。
    maybe_rotate_ledger(path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def _candidate_by_side_cell(plan: dict[str, Any], key: str) -> dict[str, Any] | None:
    for row in _list(plan.get("probe_candidates")):
        if isinstance(row, dict) and _str(row.get("side_cell_key")) == key:
            return row
    return None


def _event_to_side_cell(event: dict[str, Any]) -> str:
    return side_cell_key(
        event.get("strategy_name") or event.get("strategy"),
        event.get("symbol"),
        event.get("side"),
    )


def _ledger_side_cell(row: dict[str, Any]) -> str:
    if row.get("side_cell_key"):
        return _str(row.get("side_cell_key"))
    event = _dict(row.get("event"))
    if event:
        return _event_to_side_cell(event)
    return side_cell_key(row.get("strategy_name"), row.get("symbol"), row.get("side"))


def _row_decision(row: dict[str, Any]) -> str:
    if row.get("decision"):
        return _str(row.get("decision"))
    decision = _dict(row.get("admission_decision"))
    return _str(decision.get("decision"))


def _row_ts_ms(row: dict[str, Any]) -> int:
    for key in ("ts_ms", "attempt_ts_ms", "generated_at_ms"):
        value = _int(row.get(key), default=0)
        if value > 0:
            return value
    event = _dict(row.get("event"))
    return _int(event.get("ts_ms"), default=0)


def _attempt_id(row: dict[str, Any]) -> str:
    event = _dict(row.get("event"))
    context_id = _str(event.get("context_id"))
    if context_id:
        return context_id
    signal_id = _str(event.get("signal_id"))
    if signal_id:
        return signal_id
    return "|".join([_ledger_side_cell(row), str(_row_ts_ms(row))])


def _candidate_max_orders(candidate: dict[str, Any]) -> int:
    return max(0, _int(_dict(candidate.get("probe_proposal")).get("max_probe_orders")))


def _candidate_cooldown_ms(candidate: dict[str, Any]) -> int:
    minutes = max(0, _int(_dict(candidate.get("probe_proposal")).get("cooldown_minutes")))
    return minutes * 60_000


def _valid_candidate_guardrails(candidate: dict[str, Any]) -> tuple[bool, str | None]:
    proposal = _dict(candidate.get("probe_proposal"))
    guardrails = _dict(candidate.get("guardrails"))
    if proposal.get("mode") != "demo_only_learning_probe":
        return False, "candidate_probe_mode_not_demo_only"
    if _candidate_max_orders(candidate) <= 0:
        return False, "candidate_probe_budget_not_positive"
    if proposal.get("requires_runtime_policy_adapter") is not True:
        return False, "candidate_missing_runtime_adapter_requirement"
    if proposal.get("requires_probe_attempt_logging") is not True:
        return False, "candidate_missing_attempt_logging_requirement"
    if proposal.get("requires_probe_outcome_logging") is not True:
        return False, "candidate_missing_outcome_logging_requirement"
    if guardrails.get("main_cost_gate_adjustment") != "NONE":
        return False, "candidate_main_cost_gate_adjustment_not_none"
    if guardrails.get("may_bypass_main_live_gate") is not False:
        return False, "candidate_live_bypass_guardrail_invalid"
    if guardrails.get("demo_only") is not True:
        return False, "candidate_demo_only_guardrail_missing"
    if guardrails.get("notional_or_qty_not_granted_by_artifact") is not True:
        return False, "candidate_qty_authority_guardrail_missing"
    return True, None


def _valid_operator_authorization(
    plan: dict[str, Any],
    candidate: dict[str, Any],
    side_cell_key_value: str,
    *,
    now_utc: dt.datetime,
) -> tuple[bool, str]:
    auth = _dict(plan.get("operator_authorization"))
    if not auth:
        return False, "operator_authorization_missing_for_order_authority"
    if auth.get("schema_version") != BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION:
        return False, "operator_authorization_schema_mismatch"
    if auth.get("status") != BOUNDED_PROBE_AUTHORIZED_STATUS:
        return False, "operator_authorization_status_not_authorized"
    if not _str(auth.get("authorization_id")):
        return False, "operator_authorization_id_missing"
    if not _str(auth.get("operator_id")):
        return False, "operator_authorization_operator_id_missing"
    if _str(auth.get("side_cell_key")) != side_cell_key_value:
        return False, "operator_authorization_side_cell_mismatch"
    if auth.get("authority_path_readiness_status") != AUTHORITY_PATH_PATCH_READY_STATUS:
        return False, "operator_authorization_authority_path_not_ready"
    if auth.get("main_cost_gate_adjustment") != "NONE":
        return False, "operator_authorization_cost_gate_adjustment_not_none"
    if auth.get("order_authority") != ORDER_AUTHORITY_GRANTED:
        return False, "operator_authorization_order_authority_mismatch"
    max_authorized_probe_orders = _int(auth.get("max_authorized_probe_orders"))
    if max_authorized_probe_orders <= 0:
        return False, "operator_authorization_probe_budget_missing"
    if _candidate_max_orders(candidate) > max_authorized_probe_orders:
        return False, "operator_authorization_probe_budget_below_candidate_budget"
    if auth.get("probe_authority_granted") is not True:
        return False, "operator_authorization_probe_authority_not_granted"
    if auth.get("order_authority_granted") is not True:
        return False, "operator_authorization_order_authority_not_granted"
    if auth.get("promotion_evidence") is not False:
        return False, "operator_authorization_promotion_boundary_invalid"
    expires_at = _parse_dt(auth.get("expires_at_utc"))
    if expires_at is None:
        return False, "operator_authorization_expiry_missing_or_malformed"
    if expires_at <= now_utc:
        return False, "operator_authorization_expired"
    return True, "operator_authorization_valid"


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {}
    proposal = _dict(candidate.get("probe_proposal"))
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "source_kind": candidate.get("source_kind"),
        "learning_lane_action": candidate.get("learning_lane_action"),
        "learning_lane_reason": candidate.get("learning_lane_reason"),
        "outcome_horizon_minutes": _int(
            proposal.get("outcome_horizon_minutes")
            or candidate.get("outcome_horizon_minutes")
            or candidate.get("learning_outcome_horizon_minutes")
        ),
        "learning_outcome_horizon_minutes": _int(
            proposal.get("learning_outcome_horizon_minutes")
            or candidate.get("learning_outcome_horizon_minutes")
            or candidate.get("outcome_horizon_minutes")
        ),
        "max_probe_orders": _candidate_max_orders(candidate),
        "cooldown_minutes": _int(proposal.get("cooldown_minutes")),
        "requires_candidate_horizon_outcome_logging": (
            proposal.get("requires_candidate_horizon_outcome_logging") is True
        ),
        "horizon_stability": candidate.get("horizon_stability"),
        "sealed_horizon_replay": candidate.get("sealed_horizon_replay"),
        "guardrails": {
            "main_cost_gate_adjustment": _dict(candidate.get("guardrails")).get(
                "main_cost_gate_adjustment"
            ),
            "demo_only": _dict(candidate.get("guardrails")).get("demo_only"),
            "notional_or_qty_not_granted_by_artifact": _dict(
                candidate.get("guardrails")
            ).get("notional_or_qty_not_granted_by_artifact"),
        },
    }


def _candidate_summary_with_event_context(
    summary: Mapping[str, Any],
    event: Mapping[str, Any],
) -> dict[str, Any]:
    """把已驗證 raw context 正規化進 summary，拒絕第二份衝突 lineage。"""
    normalized_summary = dict(summary)
    validated_event = validate_ledger_event_candidate_context(event)
    if "candidate_event_context" not in validated_event:
        if "candidate_event_context" in normalized_summary:
            raise ValueError("CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT")
        status = normalized_summary.get("candidate_event_context_status")
        if status is not None and status != CANDIDATE_EVENT_CONTEXT_UNQUALIFIED_STATUS:
            raise ValueError("CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT")
        return normalized_summary

    context = validated_event["candidate_event_context"]
    if (
        "candidate_event_context" in normalized_summary
        and normalized_summary["candidate_event_context"] != context
    ):
        raise ValueError("CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT")
    if (
        "candidate_event_context_status" in normalized_summary
        and normalized_summary["candidate_event_context_status"]
        != CANDIDATE_EVENT_CONTEXT_VALID_STATUS
    ):
        raise ValueError("CANDIDATE_EVENT_CONTEXT_SUMMARY_CONFLICT")
    normalized_summary["candidate_event_context"] = context
    normalized_summary["candidate_event_context_status"] = (
        CANDIDATE_EVENT_CONTEXT_VALID_STATUS
    )
    return normalized_summary


def summarize_side_cell_runtime_state(
    candidate: dict[str, Any],
    ledger_rows: list[dict[str, Any]],
    *,
    now_ms: int,
    cfg: RuntimeAdmissionConfig | None = None,
) -> dict[str, Any]:
    """Summarize attempts/outcomes and derive auto-disable state."""
    cfg = cfg or RuntimeAdmissionConfig()
    validate_runtime_config(cfg)
    key = _str(candidate.get("side_cell_key"))
    max_orders = _candidate_max_orders(candidate)
    cooldown_ms = _candidate_cooldown_ms(candidate)

    matching = [row for row in ledger_rows if _ledger_side_cell(row) == key]
    admitted = [row for row in matching if _row_decision(row) == ADMIT_DECISION]
    admitted_count = len(admitted)
    remaining = max(0, max_orders - admitted_count)
    attempt_ts = [_row_ts_ms(row) for row in admitted if _row_ts_ms(row) > 0]
    latest_attempt_ts_ms = max(attempt_ts) if attempt_ts else None
    cooldown_until = (
        latest_attempt_ts_ms + cooldown_ms
        if latest_attempt_ts_ms is not None and cooldown_ms > 0
        else None
    )
    cooldown_active = cooldown_until is not None and now_ms < cooldown_until

    raw_completed_outcomes = [
        row
        for row in matching
        if _str(row.get("record_type")) == "probe_outcome"
    ]
    # LOW-3(operator 2026-07-05 裁定 Python 對齊 Rust):禁用判準的 realized 向量
    # 必須與 Rust 權威側 demo_learning_lane.rs::summarize_side_cell_runtime_state 同源。
    # Rust 只保留 record_type=="probe_outcome" 且 realized_net_bps 為有限值的 row
    # (filter_map + is_finite),完全不做 proof_exclusion。此處據此構造判準向量:
    # _float 已含 math.isfinite,None/NaN/inf 自動排除,對齊 Rust 的 filter_map+is_finite。
    # 為什麼移除過濾:Rust 是 golden 認定的權威側,有真 fill 的 row 若在 Python 側被
    # proof-exclude 而 Rust 不排,兩側 completed_outcome_count 會分歧(跨語言行為 drift)。
    # 注意:proof_exclusion 仍用於下方診斷欄位(透明度),且在 outcome_review 立案 gate 等
    # 別處保持不變——本次只移除「禁用判準計算」這一處的過濾。
    realized_bps = [
        value
        for value in (_float(row.get("realized_net_bps")) for row in raw_completed_outcomes)
        if value is not None
    ]
    outcome_count = len(realized_bps)
    # 診斷欄位(不進禁用判準):如實報告 proof-exclusion 情況供 operator 觀察。
    proof_exclusion_reason_counts: dict[str, int] = {}
    proof_excluded_completed_outcome_count = 0
    for row in raw_completed_outcomes:
        net_bps = _float(row.get("realized_net_bps"))
        reasons = proof_exclusion_reasons(row)
        if net_bps is None:
            reasons = [*reasons, "realized_net_bps_missing"]
        if reasons:
            proof_excluded_completed_outcome_count += 1
            for reason in reasons:
                proof_exclusion_reason_counts[reason] = (
                    proof_exclusion_reason_counts.get(reason, 0) + 1
                )
    avg_net = sum(realized_bps) / outcome_count if outcome_count else None
    net_positive_pct = (
        100.0 * sum(1 for value in realized_bps if value > 0.0) / outcome_count
        if outcome_count
        else None
    )
    # P2-7:UCB-futility 禁用規則需樣本標準差(ddof=1)。n<2 無法估變異數 → None,
    # 由下方退回純均值判準。與 Rust summarize_side_cell_runtime_state 逐值對齊。
    std_net = None
    if outcome_count >= 2 and avg_net is not None:
        variance = sum((value - avg_net) ** 2 for value in realized_bps) / (
            outcome_count - 1
        )
        std_net = math.sqrt(variance)

    manual_disable = next(
        (
            row for row in matching
            if _str(row.get("record_type")) == "side_cell_disabled"
        ),
        None,
    )
    # P2-7:UCB-futility 禁用規則。disable ⇔ n≥cfg ∧ (x̄ + z₀.₉₀·s/√n < min_avg_net_bps)。
    # 為什麼 UCB 而非均值:n<20 下均值判準對 ±75bps 效應量兩向都近擲硬幣(誤殺率 ~42%);
    # 加 90% 信賴上界後只在「連樂觀上界都為負」時才 futility 禁用(真 μ=+30 誤殺率降到 ~4%)。
    # net_positive_pct 腿刪除:n<20 下比例判準更噪(Rust P2-7 已刪,兩側須同鍵同規則,
    # 否則同 n=8 但不同規則 = 跨語言行為分歧,golden 只測常量會假綠)。
    # z₀.₉₀ = 1.2815515655446004(標準常態 0.90 分位),與 demo_learning_lane.rs 逐值對齊。
    _Z_090 = 1.281_551_565_544_600_4
    ucb_futility = False
    if outcome_count >= cfg.min_failed_outcomes_to_disable and avg_net is not None:
        if std_net is not None:
            ucb = avg_net + _Z_090 * std_net / math.sqrt(outcome_count)
            ucb_futility = ucb < cfg.min_avg_net_bps
        else:
            # s 不可估(n<2)但已達門檻(僅在 min_failed_outcomes_to_disable=1 且 n=1 時):
            # 退回純均值判準,避免無變異數時漏禁真負 cell。
            ucb_futility = avg_net < cfg.min_avg_net_bps
    disable_reason = None
    if manual_disable is not None:
        disable_reason = _str(manual_disable.get("disable_reason")) or "manual_disable"
    elif remaining <= 0:
        disable_reason = "probe_budget_exhausted"
    elif ucb_futility:
        disable_reason = "realized_probe_outcomes_fail_learning_threshold"

    return {
        "side_cell_key": key,
        "max_probe_orders": max_orders,
        "admitted_attempt_count": admitted_count,
        "remaining_probe_orders": remaining,
        "latest_probe_attempt_ts_ms": latest_attempt_ts_ms,
        "cooldown_ms": cooldown_ms,
        "cooldown_until_ts_ms": cooldown_until,
        "cooldown_active": cooldown_active,
        "raw_completed_outcome_count": len(raw_completed_outcomes),
        # completed_outcome_count 現與 Rust 逐值一致(未做 proof_exclusion,對齊權威側)。
        "completed_outcome_count": outcome_count,
        # proof_eligible 保留其字面語義=proof 合格且淨值有限的數量(診斷透明度,不進禁用判準);
        # 現已可能小於 completed_outcome_count,因 proof-excluded row 仍計入禁用判準。
        "proof_eligible_completed_outcome_count": len(raw_completed_outcomes)
        - proof_excluded_completed_outcome_count,
        "proof_excluded_completed_outcome_count": proof_excluded_completed_outcome_count,
        "proof_exclusion_present": proof_excluded_completed_outcome_count > 0,
        "proof_exclusion_reason_counts": dict(sorted(proof_exclusion_reason_counts.items())),
        "avg_realized_net_bps": avg_net,
        "net_positive_pct": net_positive_pct,
        "disabled": disable_reason is not None,
        "disable_reason": disable_reason,
    }


def _decision(
    decision: str,
    *,
    reason: str,
    now_utc: dt.datetime,
    event: dict[str, Any],
    side_cell_key_value: str | None = None,
    runtime_state: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    allowed = decision == ADMIT_DECISION
    validated_event = validate_ledger_event_candidate_context(event)
    candidate_summary = _candidate_summary_with_event_context(
        _candidate_summary(candidate),
        validated_event,
    )
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat(),
        "decision": decision,
        "reason": reason,
        "allowed_to_submit_order": allowed,
        "no_order_authority": not allowed,
        "side_cell_key": side_cell_key_value,
        "event": validated_event,
        "runtime_state": runtime_state or {},
        "candidate_summary": candidate_summary,
        "plan_summary": {
            "schema_version": (plan or {}).get("schema_version"),
            "status": (plan or {}).get("status"),
            "gate_status": (plan or {}).get("gate_status"),
            "main_cost_gate_adjustment": (plan or {}).get("main_cost_gate_adjustment"),
            "learning_gate_adjustment": (plan or {}).get("learning_gate_adjustment"),
            "order_authority": (plan or {}).get("order_authority"),
            "selected_probe_candidate_count": (plan or {}).get("selected_probe_candidate_count"),
        },
        "boundary": (
            "admission-ledger artifact only; no PG, Bybit, order, config, risk, "
            "auth, or runtime mutation"
        ),
    }


def evaluate_probe_admission(
    plan: dict[str, Any],
    reject_event: dict[str, Any],
    *,
    ledger_rows: list[dict[str, Any]] | None = None,
    now_utc: dt.datetime | None = None,
    cfg: RuntimeAdmissionConfig | None = None,
    adapter_enabled: bool = False,
    risk_state: str = "NORMAL",
) -> dict[str, Any]:
    """Return a fail-closed admission decision for one rejected demo signal."""
    cfg = cfg or RuntimeAdmissionConfig()
    validate_runtime_config(cfg)
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    rows = ledger_rows or []

    normalized_event = dict(reject_event)
    normalized_event = validate_ledger_event_candidate_context(normalized_event)
    normalized_event["side_cell_key"] = _event_to_side_cell(reject_event)
    normalized_event["reject_reason_code"] = normalize_reject_reason_code(
        reject_event.get("reject_reason_code") or reject_event.get("rejected_reason")
    )
    if _int(normalized_event.get("ts_ms")) <= 0:
        normalized_event["ts_ms"] = now_ms

    key = normalized_event["side_cell_key"]
    if plan.get("schema_version") != DEMO_LEARNING_LANE_SCHEMA_VERSION:
        return _decision(
            "PLAN_SCHEMA_MISMATCH",
            reason="plan_schema_version_is_not_cost_gate_demo_learning_lane_plan_v1",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    if plan.get("status") != "READY_FOR_DEMO_LEARNING_PROBE":
        return _decision(
            "PLAN_NOT_READY",
            reason="plan_status_is_not_ready_for_demo_learning_probe",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    plan_age = _age_seconds(plan.get("generated_at_utc"), now_utc=now)
    if plan_age is None or plan_age > cfg.max_plan_age_hours * 3600:
        return _decision(
            "PLAN_STALE_OR_MISSING_GENERATED_AT",
            reason="plan_generated_at_missing_or_too_old",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    if plan.get("main_cost_gate_adjustment") != "NONE":
        return _decision(
            "MAIN_COST_GATE_ADJUSTMENT_NOT_ALLOWED",
            reason="demo_learning_lane_must_not_lower_main_cost_gate",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )

    if _str(normalized_event.get("engine_mode")).lower() not in {"demo", "live_demo"}:
        return _decision(
            "NON_DEMO_ENGINE_MODE",
            reason="learning_probe_admission_is_demo_only",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    if normalized_event["reject_reason_code"] != ELIGIBLE_REJECT_REASON_CODE:
        return _decision(
            "REJECT_REASON_NOT_ELIGIBLE",
            reason="only_cost_gate_js_demo_negative_edge_rejections_are_probe_eligible",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )
    candidate = _candidate_by_side_cell(plan, key)
    if candidate is None:
        return _decision(
            "SIDE_CELL_NOT_SELECTED",
            reason="rejected_signal_side_cell_is_not_in_selected_probe_candidates",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            plan=plan,
        )

    valid_candidate, invalid_reason = _valid_candidate_guardrails(candidate)
    runtime_state = summarize_side_cell_runtime_state(
        candidate,
        rows,
        now_ms=now_ms,
        cfg=cfg,
    )
    if not valid_candidate:
        return _decision(
            "CANDIDATE_GUARDRAIL_INVALID",
            reason=invalid_reason or "candidate_guardrail_invalid",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
            candidate=candidate,
        )
    if runtime_state["disabled"]:
        return _decision(
            runtime_state["disable_reason"].upper(),
            reason=runtime_state["disable_reason"],
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
            candidate=candidate,
        )
    if runtime_state["cooldown_active"]:
        return _decision(
            "COOLDOWN_ACTIVE",
            reason="side_cell_probe_cooldown_active",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
            candidate=candidate,
        )
    if _str(risk_state).upper() != "NORMAL":
        return _decision(
            "RISK_STATE_NOT_NORMAL",
            reason="session_halt_or_guardian_risk_state_not_normal",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
            candidate=candidate,
        )
    if plan.get("order_authority") != ORDER_AUTHORITY_GRANTED:
        return _decision(
            "ORDER_AUTHORITY_NOT_GRANTED",
            reason="plan_matches_candidate_but_artifact_has_no_order_authority",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
            candidate=candidate,
        )
    valid_authorization, authorization_reason = _valid_operator_authorization(
        plan,
        candidate,
        key,
        now_utc=now,
    )
    if not valid_authorization:
        return _decision(
            "OPERATOR_AUTHORIZATION_INVALID",
            reason=authorization_reason,
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
            candidate=candidate,
        )
    if not adapter_enabled:
        return _decision(
            "ADAPTER_DISABLED",
            reason="runtime_adapter_enable_flag_is_false",
            now_utc=now,
            event=normalized_event,
            side_cell_key_value=key,
            runtime_state=runtime_state,
            plan=plan,
            candidate=candidate,
        )

    return _decision(
        ADMIT_DECISION,
        reason="selected_side_cell_with_budget_cooldown_clear_and_explicit_demo_probe_authority",
        now_utc=now,
        event=normalized_event,
        side_cell_key_value=key,
        runtime_state=runtime_state,
        plan=plan,
        candidate=candidate,
    )


def build_ledger_record(
    decision: dict[str, Any],
    *,
    record_type: str = "probe_admission_decision",
) -> dict[str, Any]:
    event = validate_ledger_event_candidate_context(_dict(decision.get("event")))
    candidate_summary = _candidate_summary_with_event_context(
        _dict(decision.get("candidate_summary")),
        event,
    )
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "record_type": record_type,
        "generated_at_utc": decision["generated_at_utc"],
        "attempt_id": _attempt_id({"side_cell_key": decision.get("side_cell_key"), "event": event}),
        "decision": decision["decision"],
        "allowed_to_submit_order": decision["allowed_to_submit_order"],
        "side_cell_key": decision.get("side_cell_key"),
        "event": event,
        "runtime_state": decision.get("runtime_state") or {},
        "candidate_summary": candidate_summary,
        "reason": decision.get("reason"),
        "boundary": decision.get("boundary"),
    }


def _default_plan_path() -> Path:
    # RES-8：逐位鏡像 Rust demo_learning_lane_writer.rs:211-231 的 plan 路徑解析——
    # OPENCLAW_DEMO_LEARNING_LANE_PLAN env override 優先（trim 後非空才生效，空白/
    # 空串回退默認），否則 OPENCLAW_DATA_DIR 派生默認。為什麼必須對齊：Python
    # adapter 與 Rust writer/soak 圍欄若解析出不同 plan 路徑，兩實現對賬失義
    # （guard 與 admission 判準漂移=安全洞，2026-07-02 設計 §1.2）。
    override = os.environ.get("OPENCLAW_DEMO_LEARNING_LANE_PLAN")
    if override is not None and override.strip():
        return Path(override.strip())
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"


def _default_ledger_path() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_learning_lane" / "probe_ledger.jsonl"


def _event_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.event_json:
        return _read_json(args.event_json)
    required = {
        "--strategy": args.strategy,
        "--symbol": args.symbol,
        "--side": args.side,
        "--reject-reason-code": args.reject_reason_code,
        "--engine-mode": args.engine_mode,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"missing required event args without --event-json: {', '.join(missing)}")
    return {
        "strategy_name": args.strategy,
        "symbol": args.symbol,
        "side": args.side,
        "reject_reason_code": args.reject_reason_code,
        "engine_mode": args.engine_mode,
        "ts_ms": args.ts_ms,
        "context_id": args.context_id,
        "signal_id": args.signal_id,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=_default_plan_path())
    parser.add_argument("--ledger", type=Path, default=_default_ledger_path())
    parser.add_argument("--price-observations", type=Path)
    parser.add_argument("--event-json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--record-decision", action="store_true")
    parser.add_argument("--record-outcomes", action="store_true")
    parser.add_argument("--record-blocked-outcomes", action="store_true")
    parser.add_argument("--adapter-enabled", action="store_true")
    parser.add_argument("--risk-state", default="NORMAL")
    parser.add_argument("--strategy")
    parser.add_argument("--symbol")
    parser.add_argument("--side")
    parser.add_argument("--reject-reason-code")
    parser.add_argument("--engine-mode")
    parser.add_argument("--ts-ms", type=int)
    parser.add_argument("--context-id")
    parser.add_argument("--signal-id")
    parser.add_argument("--max-plan-age-hours", type=int, default=24)
    # P2-7:CLI 默認與 RuntimeAdmissionConfig dataclass 同步(n≥8 才觸發 UCB-futility 禁用)。
    parser.add_argument("--min-failed-outcomes-to-disable", type=int, default=8)
    parser.add_argument("--min-outcome-net-positive-pct", type=float, default=50.0)
    parser.add_argument("--min-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--outcome-horizon-minutes", type=int, default=60)
    parser.add_argument("--outcome-cost-bps", type=float, default=4.0)
    parser.add_argument("--max-entry-delay-ms", type=int, default=5 * 60_000)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = RuntimeAdmissionConfig(
        max_plan_age_hours=args.max_plan_age_hours,
        min_failed_outcomes_to_disable=args.min_failed_outcomes_to_disable,
        min_outcome_net_positive_pct=args.min_outcome_net_positive_pct,
        min_avg_net_bps=args.min_avg_net_bps,
    )
    validate_runtime_config(cfg)
    ledger = read_jsonl_ledger(args.ledger)
    if args.record_outcomes or args.record_blocked_outcomes:
        if args.price_observations is None:
            raise ValueError(
                "--record-outcomes/--record-blocked-outcomes requires --price-observations"
            )
        outcome_cfg = ProbeOutcomeConfig(
            horizon_minutes=args.outcome_horizon_minutes,
            cost_bps=args.outcome_cost_bps,
            max_entry_delay_ms=args.max_entry_delay_ms,
        )
        price_rows = read_price_observations(args.price_observations)
        outcome_rows = (
            build_probe_outcome_records(ledger, price_rows, cfg=outcome_cfg)
            if args.record_outcomes
            else []
        )
        blocked_outcome_rows = (
            build_blocked_signal_outcome_records(ledger, price_rows, cfg=outcome_cfg)
            if args.record_blocked_outcomes
            else []
        )
        for row in outcome_rows + blocked_outcome_rows:
            append_jsonl_ledger(args.ledger, row)
        payload = {
            # batch 包裹 outcome 面 record → 用 outcome 面版本,與 base_row 一致。
            "schema_version": OUTCOME_ADAPTER_SCHEMA_VERSION,
            "record_type": "probe_outcome_batch",
            "outcome_count": len(outcome_rows),
            "blocked_signal_outcome_count": len(blocked_outcome_rows),
            "outcomes": outcome_rows,
            "blocked_signal_outcomes": blocked_outcome_rows,
            "boundary": "artifact-only; no PG, Bybit, order, config, risk, auth, or runtime mutation",
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
                + "\n",
                encoding="utf-8",
            )
        if args.print_json or not args.output:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 0

    plan = _read_json(args.plan)
    event = _event_from_args(args)
    decision = evaluate_probe_admission(
        plan,
        event,
        ledger_rows=ledger,
        cfg=cfg,
        adapter_enabled=args.adapter_enabled,
        risk_state=args.risk_state,
    )
    if args.record_decision:
        append_jsonl_ledger(args.ledger, build_ledger_record(decision))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    if args.print_json or not args.output:
        print(json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

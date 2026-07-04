#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：在 operator 簽名的 soak 授權窗內，自動把過期(generated_at 陳舊)的
canonical soak plan 重新蓋章(re-materialize)，讓 admission 的 plan-staleness 判準
(demo_learning_lane.rs `max_plan_age_hours`)不再每 24h 需人工重跑全鏈，同時**不延長
任何 authority**。授權由簽名塊 `operator_authorization.expires_at_utc` 硬界定，本腳本
只搬運不生成。
主要函數：rematerialize_soak_plan(核心)、build_rematerialization(純函數決策)、main(CLI)。
依賴：cost_gate_learning_lane.policy(fresh scorecard 候選再選)、contract(schema 常量)。
硬邊界(全 fail-closed，任一不成立=no-op+告警 artifact，絕不 rotate/改檔)：
  1. envelope 有效：內嵌 operator_authorization 塊 schema 對、status 授權態、未過期。
  2. 簽名塊 sha256 逐字節不變(byte-preserve)：輸出 plan 的 operator_authorization 塊
     必須與輸入逐字節相同，禁任何欄位重寫(等同腳本代簽=災難類)。
  3. side_cell / caps 一致：plan candidate 的 side_cell_key、max_probe_orders 與簽名塊一致。
  4. fresh scorecard 仍選中：以最新 scorecard 重跑 policy 候選選擇後，該 side_cell 仍在選集。
本腳本不寫 runtime 授權、不動 env/crontab、不取 Decision Lease、不呼叫 Bybit、不下/改/撤單、
不查/寫 PG、不降 Cost Gate、不授 live/mainnet、不產 promotion/profit proof。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cost_gate_learning_lane import policy
from cost_gate_learning_lane.contract import (
    BOUNDED_PROBE_AUTHORIZED_STATUS,
    BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ORDER_AUTHORITY_GRANTED,
)

# canonical soak plan 的 wrapper schema(=policy.DEMO_LEARNING_LANE_SCHEMA_VERSION，
# 對齊 policy.py 與 bounded_probe_plan_inclusion_review.py 的 plan 生產者)。
DEMO_LEARNING_LANE_SCHEMA_VERSION = policy.DEMO_LEARNING_LANE_SCHEMA_VERSION
SCHEMA_VERSION = "soak_plan_rematerializer_v1"
REMATERIALIZED_STATUS = "SOAK_PLAN_REMATERIALIZED_NO_AUTHORITY_CHANGE"
NO_OP_STATUS = "SOAK_PLAN_REMATERIALIZE_NO_OP"
READY_PLAN_STATUS = "READY_FOR_DEMO_LEARNING_PROBE"
READY_PLAN_GATE_STATUS = "OPERATOR_REVIEW"

BOUNDARY = (
    "source-only soak plan re-materialization; re-stamp generated_at and candidate "
    "snapshot only, byte-preserve the operator_authorization block, no authority "
    "extension, no runtime file mutation, no env/crontab mutation, no Decision "
    "Lease, no Bybit/order/PG call, no Cost Gate lowering, no live/mainnet "
    "authority, no promotion/profit proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> dt.datetime | None:
    text = _str(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _canonical_bytes(payload: Any) -> bytes:
    """把任意 JSON 值序列化為確定性 bytes(sort_keys)以做 sha256 逐字節比對。

    為什麼確定性：byte-preserve 不變量要求「同一授權塊搬運前後 sha 相同」，序列化必須
    key 排序穩定否則會出現假陽性 drift。
    """
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_obj(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _default_plan_path() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return (
        data_dir / "cost_gate_learning_lane" / "bounded_demo_probe_soak_plan.json"
    )


def _default_scorecard_path() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return (
        data_dir
        / "cost_gate_counterfactual"
        / "cost_gate_reject_counterfactual_latest.json"
    )


def _default_alert_path() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return (
        data_dir
        / "cost_gate_learning_lane"
        / "soak_plan_rematerializer_alerts.jsonl"
    )


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"malformed:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return None, "not_object"
    return payload, None


def _plan_side_cell(plan: dict[str, Any]) -> str | None:
    """從 plan 取被授權的 side_cell_key(candidate 塊優先，退回首個 probe_candidate)。"""
    candidate = _dict(plan.get("candidate"))
    key = _str(candidate.get("side_cell_key"))
    if key:
        return key
    for row in _list(plan.get("probe_candidates")):
        row_key = _str(_dict(row).get("side_cell_key"))
        if row_key:
            return row_key
    return None


def _plan_probe_caps(plan: dict[str, Any]) -> int | None:
    """取 plan probe_candidate 的 max_probe_orders(caps 一致性判準用)。"""
    for row in _list(plan.get("probe_candidates")):
        row = _dict(row)
        if _str(row.get("side_cell_key")):
            return _int(row.get("max_probe_orders"), 0)
    return None


def _fresh_selected_side_cells(fresh_plan: dict[str, Any]) -> list[str]:
    return [
        _str(_dict(row).get("side_cell_key"))
        for row in _list(fresh_plan.get("probe_candidates"))
        if _str(_dict(row).get("side_cell_key"))
    ]


def _auth_preconditions(auth: dict[str, Any], *, now_utc: dt.datetime) -> list[str]:
    """簽名塊有效性 fail-closed 判準。

    為什麼要逐欄位驗授權塊(不只 byte-preserve)：byte-preserve 只保證「搬運不改」，
    但攻擊者若把 plan 內 operator_authorization 塊本身改成越權形態(如 promotion_evidence
    =True / main_cost_gate_adjustment≠NONE / order_authority 非既定值)，byte-preserve 會
    忠實搬運越權塊=等同腳本代簽災難類。故此處逐欄位鎖定「合法已簽 soak envelope 指紋」，
    鏡像 bounded_probe_plan_inclusion_review._auth_packet_safe 的授權邊界，任一偏離即拒。
    """
    reasons: list[str] = []
    if not auth:
        return ["operator_authorization_missing"]
    if auth.get("schema_version") != BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION:
        reasons.append("operator_authorization_schema_mismatch")
    if auth.get("status") != BOUNDED_PROBE_AUTHORIZED_STATUS:
        reasons.append("operator_authorization_status_not_authorized")
    # 已簽 soak envelope 的授權邊界指紋：order_authority 必為既定常量、probe/order 授權旗標
    # 必 True(這是 operator 簽的態)、promotion 邊界必 False、cost gate 不動。
    if auth.get("order_authority") != ORDER_AUTHORITY_GRANTED:
        reasons.append("operator_authorization_order_authority_mismatch")
    if auth.get("order_authority_granted") is not True:
        reasons.append("operator_authorization_order_authority_not_granted")
    if auth.get("probe_authority_granted") is not True:
        reasons.append("operator_authorization_probe_authority_not_granted")
    if auth.get("promotion_evidence") is not False:
        reasons.append("operator_authorization_promotion_boundary_invalid")
    if auth.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
        reasons.append("operator_authorization_cost_gate_adjustment_not_none")
    expires_at = _parse_dt(auth.get("expires_at_utc"))
    if expires_at is None:
        reasons.append("operator_authorization_expiry_missing_or_malformed")
    elif expires_at <= now_utc:
        # 為什麼 fail-closed：簽名塊過期=授權窗結束，re-materialize 絕不能延長 authority。
        reasons.append("operator_authorization_expired")
    return reasons


def build_rematerialization(
    *,
    plan: dict[str, Any] | None,
    fresh_scorecard_plan: dict[str, Any] | None,
    fresh_scorecard_error: str | None,
    now_utc: dt.datetime,
    plan_path: Path | None = None,
    scorecard_path: Path | None = None,
    expected_authorization_sha256: str | None = None,
) -> dict[str, Any]:
    """純函數決策：判斷是否可重蓋章，並在可時產出新 plan(不做 IO)。

    返回 dict 含 status / blocking_reasons / rematerialized_plan(僅可時非 None)以及
    byte-preserve 自證欄位(authorization_sha256_before / _after)。
    """
    plan = _dict(plan)
    reasons: list[str] = []

    # 判準 0：輸入 plan 形態。
    if not plan:
        reasons.append("canonical_plan_missing_or_not_object")
    if plan and plan.get("schema_version") != DEMO_LEARNING_LANE_SCHEMA_VERSION:
        reasons.append("canonical_plan_schema_mismatch")
    if plan and plan.get("status") != READY_PLAN_STATUS:
        reasons.append("canonical_plan_status_not_ready")
    if plan and plan.get("gate_status") != READY_PLAN_GATE_STATUS:
        reasons.append("canonical_plan_gate_status_not_operator_review")

    auth = _dict(plan.get("operator_authorization"))
    # 判準 1：簽名塊有效。
    reasons.extend(_auth_preconditions(auth, now_utc=now_utc))

    plan_side_cell = _plan_side_cell(plan)
    auth_side_cell = _str(auth.get("side_cell_key"))
    # 判準 3：side_cell 一致。
    if not plan_side_cell:
        reasons.append("canonical_plan_side_cell_missing")
    if not auth_side_cell:
        reasons.append("operator_authorization_side_cell_missing")
    if plan_side_cell and auth_side_cell and plan_side_cell != auth_side_cell:
        reasons.append("plan_and_authorization_side_cell_mismatch")

    # 判準 3(caps)：plan probe caps ≤ 簽名塊 max_authorized_probe_orders。
    plan_caps = _plan_probe_caps(plan)
    auth_caps = _int(auth.get("max_authorized_probe_orders"), 0) if auth else 0
    if plan_caps is None:
        reasons.append("canonical_plan_probe_caps_missing")
    elif auth and (plan_caps < 1 or plan_caps > auth_caps):
        reasons.append("plan_probe_caps_inconsistent_with_authorization")

    # 判準 4：fresh scorecard 重選後同 side_cell 仍被選中。
    if fresh_scorecard_error:
        reasons.append(f"fresh_scorecard_unavailable:{fresh_scorecard_error}")
    fresh_selected = _fresh_selected_side_cells(_dict(fresh_scorecard_plan))
    if fresh_scorecard_plan is not None and not fresh_scorecard_error:
        fresh_status = _dict(fresh_scorecard_plan).get("status")
        if fresh_status != READY_PLAN_STATUS:
            reasons.append("fresh_scorecard_plan_not_ready_for_probe")
        elif plan_side_cell and plan_side_cell not in fresh_selected:
            reasons.append("side_cell_no_longer_selected_by_fresh_scorecard")

    authorization_sha256_before = _sha256_obj(auth) if auth else None
    # 可選 anchor：orchestrator 在 operator 簽名時刻記錄授權塊 sha256，傳入後任何偏離即拒。
    # 這是 byte-preserve 對「可信參照」的鎖定——攔截連授權邊界指紋都合法但欄位被改的篡改
    # (如 operator_id / max_authorized_probe_orders，本腳本無法獨立再推導者)。
    if (
        expected_authorization_sha256
        and authorization_sha256_before
        and authorization_sha256_before != expected_authorization_sha256
    ):
        reasons.append("operator_authorization_sha256_anchor_mismatch")

    accepted = not reasons
    rematerialized_plan: dict[str, Any] | None = None
    authorization_sha256_after: str | None = None
    fresh_generated_at = _dict(fresh_scorecard_plan).get("generated_at_utc")
    if accepted:
        # 只重生 generated_at 與候選快照；operator_authorization 塊原封搬運(byte-preserve)。
        rematerialized_plan = dict(plan)
        rematerialized_plan["generated_at_utc"] = now_utc.isoformat()
        rematerialized_plan["operator_authorization"] = auth
        # 記錄本次重蓋章的來源快照(candidate 數據時效由 fresh scorecard 提供)。
        rematerialized_plan["soak_rematerialization"] = {
            "schema_version": SCHEMA_VERSION,
            "rematerialized_at_utc": now_utc.isoformat(),
            "previous_generated_at_utc": plan.get("generated_at_utc"),
            "fresh_scorecard_generated_at_utc": fresh_generated_at,
            "fresh_scorecard_selected_side_cells": fresh_selected,
            "authority_extended": False,
            "operator_authorization_byte_preserved": True,
        }
        authorization_sha256_after = _sha256_obj(
            _dict(rematerialized_plan.get("operator_authorization"))
        )
        # byte-preserve 自證：搬運後 sha 必與搬運前逐字節相同，否則視為授權塊被改=拒。
        if authorization_sha256_after != authorization_sha256_before:
            reasons.append("operator_authorization_byte_preserve_violated")
            rematerialized_plan = None
            accepted = False

    status = REMATERIALIZED_STATUS if accepted else NO_OP_STATUS
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat(),
        "status": status,
        "accepted": accepted,
        "plan_path": str(plan_path) if plan_path else None,
        "scorecard_path": str(scorecard_path) if scorecard_path else None,
        "plan_side_cell_key": plan_side_cell,
        "authorization_side_cell_key": auth_side_cell or None,
        "plan_probe_caps": plan_caps,
        "authorization_max_authorized_probe_orders": auth_caps or None,
        "authorization_expires_at_utc": auth.get("expires_at_utc") if auth else None,
        "authorization_sha256_before": authorization_sha256_before,
        "authorization_sha256_after": authorization_sha256_after,
        "authorization_byte_preserved": (
            accepted and authorization_sha256_after == authorization_sha256_before
        ),
        "previous_generated_at_utc": plan.get("generated_at_utc"),
        "fresh_scorecard_generated_at_utc": fresh_generated_at,
        "fresh_scorecard_selected_side_cells": fresh_selected,
        "blocking_reasons": sorted(set(reasons)),
        "rematerialized_plan": rematerialized_plan,
        "answers": {
            "source_only_research_artifact": True,
            "authority_extended": False,
            "operator_authorization_object_emitted": False,
            "operator_authorization_byte_preserved": (
                accepted and authorization_sha256_after == authorization_sha256_before
            ),
            "canonical_plan_mutation_performed": accepted,
            "runtime_mutation_performed": False,
            "env_mutation_performed": False,
            "crontab_mutation_performed": False,
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "order_submission_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def _atomic_write_json_0600(path: Path, payload: dict[str, Any]) -> None:
    """原子寫 + 0600 權限。

    為什麼 0600：plan 內含 operator 簽名塊(授權物)，與現有 SSOT 檔權限對齊，避免旁路讀取。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _append_alert(alert_path: Path, review: dict[str, Any], *, now_utc: dt.datetime) -> None:
    """no-op 時 append 一行告警 JSONL(不改 plan、不 rotate)。"""
    alert_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts_utc": now_utc.isoformat().replace("+00:00", "Z"),
        "schema_version": SCHEMA_VERSION,
        "status": review.get("status"),
        "plan_path": review.get("plan_path"),
        "blocking_reasons": review.get("blocking_reasons"),
        "plan_side_cell_key": review.get("plan_side_cell_key"),
        "authorization_expires_at_utc": review.get("authorization_expires_at_utc"),
        "severity": "warning",
    }
    with alert_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def rematerialize_soak_plan(
    *,
    plan_path: Path,
    scorecard_path: Path,
    alert_path: Path,
    now_utc: dt.datetime | None = None,
    write: bool = True,
    max_scorecard_age_hours: int = policy.DEFAULT_MAX_SCORECARD_AGE_HOURS,
    min_candidate_sample: int = 100,
    expected_authorization_sha256: str | None = None,
) -> dict[str, Any]:
    """讀 canonical plan + fresh scorecard，決策後(可時)原子重蓋章 plan，(否則)告警。"""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    plan, _plan_err = _read_json(plan_path)
    cfg = policy.LearningLanePolicyConfig(
        max_scorecard_age_hours=max_scorecard_age_hours,
        min_candidate_sample=min_candidate_sample,
    )
    fresh_plan = policy.build_plan_from_file(scorecard_path, now_utc=now, cfg=cfg)
    fresh_error = _dict(fresh_plan.get("source")).get("source_error")
    review = build_rematerialization(
        plan=plan,
        fresh_scorecard_plan=fresh_plan,
        fresh_scorecard_error=fresh_error,
        now_utc=now,
        plan_path=plan_path,
        scorecard_path=scorecard_path,
        expected_authorization_sha256=expected_authorization_sha256,
    )
    if review["accepted"] and review.get("rematerialized_plan") is not None:
        if write:
            _atomic_write_json_0600(plan_path, review["rematerialized_plan"])
        review["plan_written"] = write
    else:
        if write:
            _append_alert(alert_path, review, now_utc=now)
        review["plan_written"] = False
    return review


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", type=Path, default=_default_plan_path())
    parser.add_argument("--scorecard-json", type=Path, default=_default_scorecard_path())
    parser.add_argument("--alert-jsonl", type=Path, default=_default_alert_path())
    parser.add_argument("--max-scorecard-age-hours", type=int, default=policy.DEFAULT_MAX_SCORECARD_AGE_HOURS)
    parser.add_argument("--min-candidate-sample", type=int, default=100)
    parser.add_argument(
        "--expected-authorization-sha256",
        default=None,
        help=(
            "optional operator-sign-time sha256 of the operator_authorization block; "
            "any deviation fails closed (no-op + alert)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="decide only; never write the plan or append an alert",
    )
    parser.add_argument("--json-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    review = rematerialize_soak_plan(
        plan_path=args.plan_json,
        scorecard_path=args.scorecard_json,
        alert_path=args.alert_jsonl,
        write=not args.dry_run,
        max_scorecard_age_hours=args.max_scorecard_age_hours,
        min_candidate_sample=args.min_candidate_sample,
        expected_authorization_sha256=args.expected_authorization_sha256,
    )
    review_out = dict(review)
    review_out.pop("rematerialized_plan", None)
    text = json.dumps(review_out, ensure_ascii=False, sort_keys=True, indent=2)
    print(text)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text + "\n", encoding="utf-8")
    # fail-soft：no-op 不視為錯誤退出碼(告警已落 JSONL)，讓 cron 鏈續跑。
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

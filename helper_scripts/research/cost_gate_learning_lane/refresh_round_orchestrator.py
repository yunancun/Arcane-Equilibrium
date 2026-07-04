#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：把 envelope refresh 全鏈 SOP(原 TODO.md prose)碼化為確定性步驟機，讓每輪
refresh 的步驟序、耗時、人工介入標記、終態全部 append 到 refresh_round_ledger.jsonl，
使「refresh 是否只在兩個合法停點(E3/BB 審查、operator 簽名)介入人工」可量測、可審計
(v739 驗收判準的證據源)。
主要函數：build_round_plan(確定性步驟序，純函數)、advance_round(推進一步 + append ledger)、
main(CLI)。
依賴：僅標準庫 + 本 lane 的 ledger 目錄慣例。
硬邊界：本腳本是**編排/記帳器**，不代執行授權動作、不代 operator 簽名、不代 E3/BB 審查、
不下單/不改 runtime/不動 env/crontab/不呼叫 Bybit/不寫 PG/不降 Cost Gate。兩個停點是僅有的
人類/agent 交接口(deterministic routing 進代碼、判斷留人；Operating Style #5)：任何繞過停點
的人工動作都會在 ledger 缺步驟=可審計。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "refresh_round_orchestrator_v1"
LEDGER_RECORD_SCHEMA_VERSION = "refresh_round_ledger_entry_v1"

# 停點種類：僅有的兩個合法人工/agent 交接口。
STOP_E3_BB_REVIEW = "STOP_E3_BB_REVIEW"
STOP_OPERATOR_SIGNATURE = "STOP_OPERATOR_SIGNATURE"

# 步驟終態。
STEP_STATE_PENDING = "PENDING"
STEP_STATE_DONE = "DONE"
STEP_STATE_STOP = "STOP_AWAITING_HUMAN"
STEP_STATE_FAILED = "FAILED"

# 確定性步驟序(對齊設計正本 §4.E / TODO refresh SOP)。每步標明是否為停點。
# 兩個停點=僅有的人工介入合法位置；其餘步驟是 deterministic routing。
REFRESH_ROUND_STEPS: tuple[dict[str, Any], ...] = (
    {"step": "fetch_origin", "stop": None, "human_expected": False},
    {"step": "quiet_window_sample_1", "stop": None, "human_expected": False},
    {"step": "quiet_window_sample_2", "stop": None, "human_expected": False},
    {"step": "generate_e3_bb_signoff_packet", "stop": None, "human_expected": False},
    {"step": "e3_bb_review", "stop": STOP_E3_BB_REVIEW, "human_expected": True},
    {"step": "step1_two_stage_check", "stop": None, "human_expected": False},
    {"step": "operator_signature", "stop": STOP_OPERATOR_SIGNATURE, "human_expected": True},
    {"step": "detached_worktree_prepare", "stop": None, "human_expected": False},
    {"step": "fast_balance_artifact", "stop": None, "human_expected": False},
    {"step": "runtime_readiness", "stop": None, "human_expected": False},
    {"step": "standing_guardrail", "stop": None, "human_expected": False},
    {"step": "materialization", "stop": None, "human_expected": False},
    {"step": "post_refresh_validation", "stop": None, "human_expected": False},
)

BOUNDARY = (
    "deterministic refresh-round orchestrator and ledger only; two human/agent "
    "stop points (E3/BB review, operator signature); no order, auth signing, "
    "runtime/env/crontab mutation, Bybit/PG call, Cost Gate lowering, live/mainnet "
    "authority, or promotion/profit proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _new_round_id(now_utc: dt.datetime) -> str:
    return f"refresh-{now_utc.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def _default_ledger_path() -> Path:
    data_dir = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
    return data_dir / "cost_gate_learning_lane" / "refresh_round_ledger.jsonl"


def build_round_plan(
    *,
    round_id: str | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """產出一輪的確定性步驟計劃(純函數，不做 IO)。"""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    rid = round_id or _new_round_id(now)
    return {
        "schema_version": SCHEMA_VERSION,
        "round_id": rid,
        "created_at_utc": now.isoformat(),
        "stop_points": [STOP_E3_BB_REVIEW, STOP_OPERATOR_SIGNATURE],
        "steps": [
            {
                "index": index,
                "step": spec["step"],
                "stop": spec["stop"],
                "human_expected": spec["human_expected"],
                "state": STEP_STATE_PENDING,
            }
            for index, spec in enumerate(REFRESH_ROUND_STEPS)
        ],
        "boundary": BOUNDARY,
    }


def _step_spec(step_name: str) -> dict[str, Any] | None:
    for spec in REFRESH_ROUND_STEPS:
        if spec["step"] == step_name:
            return spec
    return None


def make_ledger_entry(
    *,
    round_id: str,
    step: str,
    state: str,
    now_utc: dt.datetime,
    duration_seconds: float | None = None,
    human_intervention: bool = False,
    detail: str | None = None,
) -> dict[str, Any]:
    """建構一條 ledger 記錄(不做 IO)。

    human_intervention 標記=本步是否有真人工/agent 介入；停點步驟預期 True，其餘步驟若標
    True 即代表出現「停點外人工動作」，交叉自報時可被 QC 抓為 ledger 外繞行。
    """
    spec = _step_spec(step)
    return {
        "schema_version": LEDGER_RECORD_SCHEMA_VERSION,
        "ts_utc": now_utc.isoformat().replace("+00:00", "Z"),
        "round_id": round_id,
        "step": step,
        "state": state,
        "stop_point": (spec or {}).get("stop"),
        "human_expected": bool((spec or {}).get("human_expected")),
        "human_intervention": bool(human_intervention),
        "duration_seconds": duration_seconds,
        "detail": detail,
    }


def _append_ledger(ledger_path: Path, entry: dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def advance_round(
    *,
    round_id: str,
    step: str,
    state: str,
    ledger_path: Path,
    now_utc: dt.datetime | None = None,
    duration_seconds: float | None = None,
    human_intervention: bool = False,
    detail: str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """推進一步：驗步名合法、建 ledger 記錄、(可時)append。

    停點步驟(e3_bb_review / operator_signature)的合法終態只允許 STOP_AWAITING_HUMAN 或
    DONE：碼化「機器只能停在停點等人，不能替人走過去」。
    """
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    spec = _step_spec(step)
    reasons: list[str] = []
    if spec is None:
        reasons.append(f"unknown_step:{step}")
    valid_states = {
        STEP_STATE_PENDING,
        STEP_STATE_DONE,
        STEP_STATE_STOP,
        STEP_STATE_FAILED,
    }
    if state not in valid_states:
        reasons.append(f"invalid_state:{state}")
    # 停點紀律：停點步驟不接受被機器直接標 DONE 而無人工介入標記。
    if spec is not None and spec.get("stop") and state == STEP_STATE_DONE and not human_intervention:
        reasons.append("stop_point_marked_done_without_human_intervention")
    accepted = not reasons
    entry = make_ledger_entry(
        round_id=round_id,
        step=step,
        state=state if accepted else STEP_STATE_FAILED,
        now_utc=now,
        duration_seconds=duration_seconds,
        human_intervention=human_intervention,
        detail=detail if accepted else ";".join(reasons),
    )
    if write:
        _append_ledger(ledger_path, entry)
    return {
        "schema_version": SCHEMA_VERSION,
        "accepted": accepted,
        "blocking_reasons": reasons,
        "ledger_entry": entry,
        "ledger_path": str(ledger_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    plan_p = sub.add_parser("plan", help="print a fresh deterministic round plan")
    plan_p.add_argument("--round-id", default=None)
    plan_p.add_argument("--json-output", type=Path)

    step_p = sub.add_parser("record-step", help="append a step outcome to the round ledger")
    step_p.add_argument("--round-id", required=True)
    step_p.add_argument("--step", required=True)
    step_p.add_argument(
        "--state",
        required=True,
        choices=[STEP_STATE_PENDING, STEP_STATE_DONE, STEP_STATE_STOP, STEP_STATE_FAILED],
    )
    step_p.add_argument("--ledger-jsonl", type=Path, default=_default_ledger_path())
    step_p.add_argument("--duration-seconds", type=float, default=None)
    step_p.add_argument("--human-intervention", action="store_true")
    step_p.add_argument("--detail", default=None)
    step_p.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "plan":
        plan = build_round_plan(round_id=args.round_id)
        text = json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2)
        print(text)
        if args.json_output is not None:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(text + "\n", encoding="utf-8")
        return 0
    if args.command == "record-step":
        result = advance_round(
            round_id=args.round_id,
            step=args.step,
            state=args.state,
            ledger_path=args.ledger_jsonl,
            duration_seconds=args.duration_seconds,
            human_intervention=args.human_intervention,
            detail=args.detail,
            write=not args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        # 非法步名/態=退出碼 2(讓 orchestration 呼叫端 fail-loud)。
        return 0 if result["accepted"] else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

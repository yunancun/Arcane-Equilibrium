#!/usr/bin/env python3
"""Learning-lane source generation pin resolution and drift classification.

MODULE_NOTE
模塊用途：learning lane 的部署世代（expected source head）統一判準公共庫（P1-4，
  2026-07-04 over-gate 統一設計 §4.C）。解析 pin（env 鏈 →
  $OPENCLAW_DATA_DIR/runtime_generation/expected_source_head.json → None），
  並在 checkout HEAD 與 pin 不等時，對 expected..HEAD 淨差異套用 IMPL-B
  post-approval drift 分類器，輸出四態：MATCH / DRIFT_EXEMPT / DRIFT_ROTATED /
  INDETERMINATE。docs/tests/.codex-only 前進不再凍結 lane（v710-v738 拒真死循環
  的 pin 乘數），其餘一律 fail-close。
主要函數：resolve_expected_source_head（pin 解析，env 鏈優先=crontab 現存 inline
  pin 在割接完成前繼續生效）、classify_source_generation（四態分類）、
  main（cron shell 消費的 verdict-line CLI：stdout 單行 `STATUS\\tEFFECTIVE_HEAD`）。
依賴：standing_envelope_post_approval_drift_gate（分類器 `_classify_change` 與
  policy 常量——單一 policy SSOT，本檔禁止出現第二份豁免表）、
  standing_envelope_source_impact_guard.collect_git_impact_inputs（mode-aware git
  採集，binary/gitlink/symlink 歧義已內建 fail-close）。
硬邊界：source-only 判準；不 fetch、不連 runtime/Bybit、不查/寫 PG、不改
  service/env/risk/Cost Gate、不授權任何 order/live/proof。DRIFT_EXEMPT 只代表
  「豁免面前進不凍結 lane」，不是新批准；存疑態（pin 檔壞 / git 失敗 / 未知
  路徑 / 非 ancestor）一律 fail-close（INDETERMINATE / DRIFT_ROTATED）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

# 共用純函數葉節點：以 alias-import 保持函數體內 _utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    utc_now as _utc_now,
)

# 直接以檔案路徑執行時需把 research root 加進 sys.path 才能 import 同 package
# 模塊（沿 standing_envelope_post_approval_drift_gate 慣例）。
_RESEARCH_ROOT = Path(__file__).resolve().parents[1]
if str(_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_ROOT))

# 豁免判準的唯一正本：per-change 分類（含 rename 兩端 / 非常規 diff 狀態 /
# binary·submodule 歧義覆蓋）與 policy 常量都 import IMPL-B 模組，禁止在本檔
# 複製豁免前綴表（E2 審查點 2：repo 內不得出現第二份豁免清單）。
from cost_gate_learning_lane.standing_envelope_post_approval_drift_gate import (  # noqa: E402
    DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1,
    _classify_change,
)
from cost_gate_learning_lane.standing_envelope_source_impact_guard import (  # noqa: E402
    collect_git_impact_inputs,
)


SCHEMA_VERSION = "cost_gate_learning_lane_source_generation_v1"

MATCH_STATUS = "MATCH"
DRIFT_EXEMPT_STATUS = "DRIFT_EXEMPT"
DRIFT_ROTATED_STATUS = "DRIFT_ROTATED"
INDETERMINATE_STATUS = "INDETERMINATE"
# 僅 CLI verdict 使用：pin 完全未配置（env 鏈與 pin 檔皆無）時沿用各 lane 既有
# 「expected head 未提供」行為（向後兼容，不新增凍結面）。
PIN_NOT_PROVIDED_STATUS = "PIN_NOT_PROVIDED"

# env 鏈（既有變量名，向後兼容；順序=alpha_discovery_throughput_cron 既有優先序）。
EXPECTED_SOURCE_HEAD_ENV_CHAIN = (
    "OPENCLAW_EXPECTED_SOURCE_HEAD",
    "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD",
    "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD",
)

# pin SSOT 檔（寫者=restart_all.sh / helper_scripts/deploy/derive_expected_source_head.sh）。
PIN_FILE_RELATIVE_PATH = "runtime_generation/expected_source_head.json"

# fail-close sentinel：非 hex，傳入任何 lane 既有 exact-compare 都必然不匹配
# （status.py → EXPECTED_HEAD_INVALID；healthcheck startswith → False），
# 使「pin 檔存在但不可讀/不合法」不會退化成「未配置=綠」的 fail-open 邊。
INVALID_PIN_SENTINEL = "pin_file_invalid"
ARTIFACT_WRITE_FAILED_SENTINEL = "source_generation_artifact_write_failed"

# 本 lib 只比 expected..HEAD 兩點；origin/main 是否可解析與此判準正交（fresh
# clone / detached CI 可能無 origin/main 遠端 ref，但 checkout 世代仍可證）。
# collect_git_impact_inputs 為 IMPL-B gate 附帶採集 origin/main（供其 HEAD==
# origin/main 非阻斷觀察），該 ref 缺失不影響 expected..HEAD 的 diff 與 ancestor
# 判定，故從本 lib 的 fail-close 集合排除；其餘所有 git error（base/current/HEAD
# ref 解析、diff 三路、binary/mode 對賬）都直接壓垮世代判準，必 INDETERMINATE。
_COMPARISON_IRRELEVANT_GIT_ERRORS = frozenset({"origin_main_ref_unresolved"})

BOUNDARY = (
    "source-only generation pin resolution and drift classification; no fetch, "
    "no runtime/Bybit call, no PG query/write, no service/env/risk/Cost Gate "
    "mutation, no order/live/proof authority; DRIFT_EXEMPT only keeps the "
    "learning lane unfrozen across docs/tests/.codex-only source advance"
)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
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


def _is_hex_sha_prefix(text: str) -> bool:
    # 與 status.py `_expected_head_status` / installer `_validate_sha_prefix`
    # 同一判準：7-40 hex 前綴。
    if len(text) < 7 or len(text) > 40:
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in text)


def resolve_expected_source_head(
    cli_value: str | None = None,
    *,
    data_dir: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """解析 expected source head：CLI/lane env → 通用 env 鏈 → pin 檔 → None。

    為什麼 env 鏈優先於 pin 檔：crontab 現存 inline pin 在割接完成前必須繼續
    生效（§4.C rollback 路徑）；pin 檔只是新增的自動化來源，不推翻顯式配置。
    pin 檔存在但不可讀/JSON 壞/head 不合法 → error 非 None（呼叫端必須
    fail-close，不得視同「未配置」）。
    """
    result: dict[str, Any] = {
        "head": None,
        "source": None,
        "pin_path": None,
        "pin_derived_at_utc": None,
        "pin_writer": None,
        "error": None,
    }
    text = str(cli_value or "").strip()
    if text:
        result["head"] = text
        result["source"] = "cli"
        return result
    env_map = os.environ if env is None else env
    for name in EXPECTED_SOURCE_HEAD_ENV_CHAIN:
        value = str(env_map.get(name) or "").strip()
        if value:
            result["head"] = value
            result["source"] = f"env:{name}"
            return result
    if data_dir is None:
        return result
    pin_path = Path(data_dir) / PIN_FILE_RELATIVE_PATH
    result["pin_path"] = str(pin_path)
    try:
        raw = pin_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return result
    except OSError as exc:
        result["error"] = f"pin_file_unreadable:{exc.__class__.__name__}"
        return result
    try:
        payload = json.loads(raw)
    except ValueError:
        result["error"] = "pin_file_json_invalid"
        return result
    if not isinstance(payload, dict):
        result["error"] = "pin_file_json_not_object"
        return result
    head = str(payload.get("head") or "").strip()
    if not _is_hex_sha_prefix(head):
        result["error"] = "pin_file_head_invalid"
        return result
    result["head"] = head
    result["source"] = "pin_file"
    result["pin_derived_at_utc"] = payload.get("derived_at_utc")
    result["pin_writer"] = payload.get("writer")
    return result


def classify_source_generation(
    repo_root: Path | str,
    expected_head: str | None,
    *,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """對 checkout 世代做四態分類（deny-by-default）。

    - MATCH：HEAD 與 expected 解析為同一 commit。
    - DRIFT_EXEMPT：expected 是 HEAD ancestor，且 expected..HEAD 每個 changed
      path 都命中 IMPL-B 豁免集（docs/tests/.codex/頂層 md/SCRIPT_INDEX），
      無 binary/gitlink/symlink 歧義。
    - DRIFT_ROTATED：任何 hard-deny/未分類路徑、非 ancestor（rollback/改史）、
      binary/mode 歧義——真代碼世代漂移，lane 必須凍結。
    - INDETERMINATE：expected 缺失/不合法、任何 git 採集錯誤——證據缺失時
      不能宣告世代等價，fail-close。
    worktree dirty 僅記錄不影響本判準（鏡 IMPL-B：只比 committed refs；dirty
    檢查由各 lane 既有邏輯獨立負責，職責不重疊）。
    """
    now = now_utc or _utc_now()
    expected = str(expected_head or "").strip()
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso(now),
        "policy": DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1,
        "expected_source_head_input": expected or None,
        "expected_source_head": None,
        "current_source_head": None,
        "changed_path_count": 0,
        "changed_path_classifications": [],
        "non_blocking_observations": [],
        "blockers": [],
        "boundary": BOUNDARY,
    }

    def _finish(status: str, reason: str, blockers: list[str]) -> dict[str, Any]:
        packet["status"] = status
        packet["reason"] = reason
        packet["blockers"] = sorted(set(blockers))
        return packet

    if not expected:
        return _finish(
            INDETERMINATE_STATUS,
            "expected_source_head_unresolved",
            ["expected_source_head_unresolved"],
        )
    if not _is_hex_sha_prefix(expected):
        return _finish(
            INDETERMINATE_STATUS,
            "expected_source_head_invalid",
            ["expected_source_head_invalid"],
        )

    git_inputs = collect_git_impact_inputs(
        Path(repo_root).resolve(),
        base_source_head=expected,
        current_source_head="HEAD",
        now_utc=now,
    )
    packet["expected_source_head"] = git_inputs.get("base_source_head")
    packet["current_source_head"] = git_inputs.get("current_source_head")
    if git_inputs.get("worktree_clean") is not True:
        packet["non_blocking_observations"].append("worktree_dirty_recorded_not_blocking")

    git_error_keys: list[str] = []
    for error in git_inputs.get("git_errors") or []:
        key = str(error.get("key") or "git_error") if isinstance(error, dict) else "git_error"
        # origin/main 缺失與 expected..HEAD 判準正交，不 fail-close（見常量註釋）。
        if key in _COMPARISON_IRRELEVANT_GIT_ERRORS:
            packet["non_blocking_observations"].append(f"{key}_recorded_not_blocking")
            continue
        git_error_keys.append(key)
    if git_error_keys:
        # 為什麼 fail-close：git 證據缺失（ref 解析失敗 / diff 失敗 / binary·mode
        # 對賬不上）時無法證明世代等價，必須 INDETERMINATE 讓 lane 凍結。
        return _finish(
            INDETERMINATE_STATUS,
            "git_evidence_unavailable_or_inconsistent",
            git_error_keys,
        )

    resolved_expected = str(git_inputs.get("base_source_head") or "")
    resolved_head = str(git_inputs.get("current_source_head") or "")
    if resolved_expected and resolved_expected == resolved_head:
        return _finish(MATCH_STATUS, "checkout_head_matches_expected_source_head", [])

    blockers: list[str] = []
    if git_inputs.get("base_is_ancestor_of_current") is not True:
        # rollback / force-push 改史不屬「豁免面前進」，一律 ROTATED。
        blockers.append("expected_head_not_ancestor_of_current_head")

    classifications: list[dict[str, Any]] = []
    for change in git_inputs.get("changed_paths") or []:
        if not isinstance(change, dict):
            classifications.append(
                {
                    "path": None,
                    "category": "diff_entry_not_object",
                    "exempt": False,
                    "policy_sensitive_docs": False,
                    "blocker": "diff_entry_not_object",
                    "change_status": None,
                }
            )
            continue
        classifications.extend(_classify_change(change))
    packet["changed_path_count"] = len(classifications)
    packet["changed_path_classifications"] = classifications
    blockers.extend(
        str(item.get("blocker")) for item in classifications if item.get("blocker")
    )

    if blockers:
        return _finish(
            DRIFT_ROTATED_STATUS,
            "source_generation_drift_outside_exempt_allowlist",
            blockers,
        )
    return _finish(
        DRIFT_EXEMPT_STATUS,
        "source_generation_drift_fully_within_docs_tests_codex_exempt_allowlist",
        [],
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve the learning-lane expected source head pin and classify "
            "checkout generation drift; prints one 'STATUS\\tEFFECTIVE_HEAD' line."
        )
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--lane", default="unspecified")
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--print-json", action="store_true")
    parser.add_argument("--now-utc", default=None, help="test hook: ISO timestamp")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    now = _parse_dt(args.now_utc) if args.now_utc else _utc_now()
    if now is None:
        raise SystemExit("--now-utc must be an ISO-8601 timestamp")

    resolution = resolve_expected_source_head(args.expected_head, data_dir=args.data_dir)
    classification: dict[str, Any] | None = None
    if resolution["error"]:
        # pin 檔壞 ≠ pin 未配置：必須 fail-close（sentinel 讓下游 exact-compare 必紅）。
        status = INDETERMINATE_STATUS
        effective = INVALID_PIN_SENTINEL
    elif not resolution["head"]:
        status = PIN_NOT_PROVIDED_STATUS
        effective = ""
    else:
        classification = classify_source_generation(
            args.repo_root, resolution["head"], now_utc=now
        )
        status = str(classification["status"])
        if status == DRIFT_EXEMPT_STATUS:
            # 豁免面前進：改傳當前 HEAD，讓 lane 既有 exact-compare 綠；
            # 完整分類記錄落 artifact（放行必留痕，E2 審查點 2）。
            effective = str(classification.get("current_source_head") or resolution["head"])
        else:
            # MATCH → 原 pin（行為與割接前逐位一致）；DRIFT_ROTATED /
            # INDETERMINATE → 原 pin，沿各 lane 既有 mismatch/unknown fail-close。
            effective = str(resolution["head"])

    packet = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso(now),
        "lane": str(args.lane or "unspecified"),
        "status": status,
        "effective_expected_head": effective or None,
        "resolution": resolution,
        "classification": classification,
        "boundary": BOUNDARY,
    }

    artifact_error: str | None = None
    artifact_paths: list[Path] = []
    if args.json_output is not None:
        artifact_paths.append(args.json_output)
    if args.data_dir is not None:
        lane_dir = Path(args.data_dir) / "cost_gate_learning_lane"
        artifact_paths.append(lane_dir / "source_generation_check_latest.json")
    try:
        for path in artifact_paths:
            _write_json(path, packet)
        if args.data_dir is not None:
            _append_jsonl(
                Path(args.data_dir)
                / "cost_gate_learning_lane"
                / "source_generation_check_history.jsonl",
                {
                    "generated_at_utc": packet["generated_at_utc"],
                    "lane": packet["lane"],
                    "status": status,
                    "effective_expected_head": effective or None,
                    "resolution_source": resolution.get("source"),
                    "resolution_head": resolution.get("head"),
                    "blockers": (classification or {}).get("blockers") or [],
                },
            )
    except OSError as exc:
        artifact_error = f"artifact_write_failed:{exc.__class__.__name__}"
    if artifact_error and status == DRIFT_EXEMPT_STATUS:
        # 為什麼降級：DRIFT_EXEMPT 是唯一「放寬」出口，審計記錄寫不進去就不放行
        # （fail-close）；MATCH / fail-close 態不依賴 artifact，不降級。
        status = INDETERMINATE_STATUS
        effective = ARTIFACT_WRITE_FAILED_SENTINEL
        packet["status"] = status
        packet["effective_expected_head"] = effective
        packet["artifact_error"] = artifact_error

    print(f"{status}\t{effective}")
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

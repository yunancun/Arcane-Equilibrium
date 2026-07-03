#!/usr/bin/env python3
"""Post-approval drift gate for standing-envelope refresh (source-only).

MODULE_NOTE
模塊用途：E3/BB 批准 standing-envelope refresh 之後、任何 runtime 動作之前，對
  approved_head..origin/main 的兩點淨差異做 deny-by-default 影響面分類，判定既有
  批准是否延續（EXEMPT）或作廢（ROTATED）。取代舊「exact-sha 等式」final check，
  解決 codex 高頻 docs/memory/tests commits 造成的 v710-v738 批准死循環。
主要函數：classify_post_approval_path（四步 deny-first 分類）、
  load_approved_request_meta（approved request packet sha256 / policy 字段驗證）、
  collect_mode_aware_diff_inputs（--raw mode bits + --no-renames numstat 補充採集，
  回應 E2 2026-07-03 對抗審查退回的修復）、build_post_approval_drift_gate
  （組 gate packet）、main（CLI）。
依賴：同 package standing_envelope_source_impact_guard.collect_git_impact_inputs
  （git 採集復用）。與舊 guard 的關鍵差異：本 gate 只比 committed refs，本地
  worktree dirty 與 HEAD != origin/main 僅記錄、不作 blocker——否則 codex 常態
  流量下死循環無解（operator 2026-07-02 已批准放寬方向）。
硬邊界：source-only；不 fetch、不連 runtime/Bybit、不查/寫 PG、不 acquire/release
  Decision Lease、不改 service/env/risk/Cost Gate、不授權任何 runtime action /
  order / live / proof。EXEMPT 只代表「批准延續判定」，不是新批准；且 EXEMPT
  延續時 runtime 動作必須從 approved_head 的 clean detached worktree 執行。
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# 直接以檔案路徑執行時（python3 helper_scripts/.../standing_envelope_post_approval_drift_gate.py）
# 需要把 research root 加進 sys.path 才能 import 同 package 的 git 採集函數（沿 sibling 慣例）。
_RESEARCH_ROOT = Path(__file__).resolve().parents[1]
if str(_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_ROOT))

from cost_gate_learning_lane.standing_envelope_source_impact_guard import (  # noqa: E402
    collect_git_impact_inputs,
)


SCHEMA_VERSION = "standing_envelope_post_approval_drift_gate_v1"

EXEMPT_STATUS = "POST_APPROVAL_DRIFT_EXEMPT_APPROVAL_STILL_VALID"
ROTATED_STATUS = "POST_APPROVAL_DRIFT_ROTATED"

# 唯一合法 policy 值：CLI --policy 與 approved request packet 內
# post_approval_drift_policy 字段都必須等於它，否則 fail-closed ROTATED。
DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1 = "docs_tests_codex_exempt_v1"
POLICY_FIELD = "post_approval_drift_policy"

BOUNDARY = (
    "post-approval drift gate only; no new approval, no fetch, no runtime call, "
    "no Control API GET, no exchange/public/private/order endpoint, no Decision "
    "Lease acquire/release, no order/cancel/modify, no PG query/write, no "
    "service/env/risk mutation, no Cost Gate change, no live/mainnet authority, "
    "no fill/PnL, and no proof; EXEMPT only continues an existing exact E3/BB "
    "approval and requires execution from the approved-head clean detached worktree"
)

# 第 1 步 hard-deny 前綴：任一命中即 ROTATED，即使副檔名是 .md
# （settings/sql=runtime 生效面；.github/docker*/scripts/tools/venvs=CI/部署面；
#  .claude/=可執行 hooks）。
HARD_DENY_PREFIXES = (
    "settings/",
    "sql/",
    ".github/",
    "docker/",
    "docker_projects/",
    "scripts/",
    "tools/",
    "venvs/",
    ".claude/",
)

# 第 1 步 hard-deny 檔名（basename）模式：依賴/配置面，位置不限。
HARD_DENY_BASENAME_PATTERNS = (
    "*.toml",
    "*.lock",
    "requirements*.txt",
    "package*.json",
    "pytest.ini",
    "skills-lock.json",
)

# 第 3 步豁免但仍標 policy_sensitive_docs 的治理文檔面（供 packet 匯總
# policy_sensitive_docs_changed 審計字段；operator 已批准豁免，標記僅供 E3/BB 審計）。
POLICY_SENSITIVE_DOC_PREFIXES = (
    "docs/agents/",
    "docs/adr/",
    "docs/decisions/",
    "docs/runbooks/",
)
POLICY_SENSITIVE_TOP_LEVEL_DOCS = {
    "AGENTS.md",
    "CLAUDE.md",
    "TODO.md",
}

SCRIPT_INDEX_PATH = "helper_scripts/SCRIPT_INDEX.md"

# gitlink（submodule）與 symlink 的 git file mode：任一端命中即強制 deny，不論
# 路徑落在哪個豁免樹（symlink 可指向豁免樹外、gitlink 內容根本不在本 repo 可審範圍）。
DENIED_FILE_MODES = {"160000", "120000"}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


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


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _parse_raw_diff_line(line: str) -> dict[str, Any] | None:
    """解析 `git diff --raw` 單行：`:<src_mode> <dst_mode> <src_sha> <dst_sha> <status>\\t<path>[\\t<path2>]`。"""
    if not line.startswith(":"):
        return None
    head, *paths = line.split("\t")
    fields = head[1:].split(" ")
    if len(fields) < 5 or not paths:
        return None
    return {
        "src_mode": fields[0],
        "dst_mode": fields[1],
        "status": fields[4],
        "paths": [p for p in paths if p],
    }


def collect_mode_aware_diff_inputs(
    repo_root: Path,
    *,
    base_source_head: str,
    current_source_head: str = "origin/main",
) -> dict[str, Any]:
    """補充採集層（E2 2026-07-03 REJECT 修復，PM 裁決不改 v734 共用採集）。

    為什麼需要這層：spec 原配方「帶 rename 偵測的 numstat 出現 '-'」已被 E2 實證
    無效——(a) binary rename 的 numstat 給 curly-brace 合併路徑（docs/{a.png => b.png}），
    與 name-status 兩端都不相等，per-change ambiguous 永不觸發；(b) 裸 gitlink 的
    numstat 是 `1\\t0` 而非 '-'，根本不觸 binary 偵測。本層以 mode-aware 偵測兌現
    spec intent（binary/submodule 歧義=ROTATED），方向嚴格更 fail-closed：
    - `git diff --raw`：任一端 mode 屬 DENIED_FILE_MODES（160000 gitlink /
      120000 symlink）→ 該 path 強制 deny，不論豁免樹。
    - `git diff --numstat --no-renames`：rename 兩端各自以原始路徑出現（無
      curly-brace），用它做可靠的 binary path 集合；對不回分類條目的 binary 行
      由 build 上全局 blocker `binary_numstat_entry_unmatched`。
    v734 collect_git_impact_inputs 的同源缺陷已於 2026-07-03 修復（--no-renames
    numstat + --raw mode 白名單）；本層保留為 belt-and-suspenders 雙保險。
    """
    errors: list[dict[str, str]] = []
    raw_entries: list[dict[str, Any]] = []
    denied_mode_paths: list[str] = []
    binary_paths: set[str] = set()

    raw_result = _run_git(
        repo_root, ["diff", "--raw", f"{base_source_head}..{current_source_head}"]
    )
    if raw_result.returncode != 0:
        errors.append({"key": "git_diff_raw_failed", "stderr": raw_result.stderr.strip()})
    else:
        for line in raw_result.stdout.splitlines():
            if not line.strip():
                continue
            entry = _parse_raw_diff_line(line)
            if entry is None:
                # 為什麼 fail-closed：解析不了的 raw 行代表 diff 形態超出已知契約，
                # 不能假設它安全。
                errors.append({"key": "git_diff_raw_parse_failed", "line": line})
                continue
            raw_entries.append(entry)
            if entry["src_mode"] in DENIED_FILE_MODES or entry["dst_mode"] in DENIED_FILE_MODES:
                denied_mode_paths.extend(entry["paths"])

    numstat_result = _run_git(
        repo_root,
        ["diff", "--numstat", "--no-renames", f"{base_source_head}..{current_source_head}"],
    )
    if numstat_result.returncode != 0:
        errors.append(
            {"key": "git_diff_numstat_no_renames_failed", "stderr": numstat_result.stderr.strip()}
        )
    else:
        for line in numstat_result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            if parts[0] == "-" or parts[1] == "-":
                binary_paths.update(p for p in parts[2:] if p)

    return {
        "raw_entries": raw_entries,
        "denied_mode_paths": sorted(set(denied_mode_paths)),
        "binary_paths_no_renames": sorted(binary_paths),
        "mode_aware_errors": errors,
    }


def _deny(path: str, blocker: str) -> dict[str, Any]:
    return {
        "path": path,
        "category": blocker,
        "exempt": False,
        "policy_sensitive_docs": False,
        "blocker": blocker,
    }


def _exempt(path: str, category: str, *, policy_sensitive_docs: bool = False) -> dict[str, Any]:
    return {
        "path": path,
        "category": category,
        "exempt": True,
        "policy_sensitive_docs": policy_sensitive_docs,
        "blocker": None,
    }


def classify_post_approval_path(path: str) -> dict[str, Any]:
    """對單一 changed path 做 deny-by-default 四步分類。

    為什麼順序不可顛倒：hard-deny 必須先於任何豁免（例如
    rust/*/src/**/tests/** 是 rust src 面，不能被第 2 步 test 豁免穿透；
    program_code/README.md 不能被 .md 印象誤放行）；兩者都不中的一律
    unclassified=ROTATED（fail-closed）。
    """
    normalized = str(path or "").strip()
    if not normalized:
        return _deny(normalized, "diff_entry_missing_path")
    parts = normalized.split("/")
    dir_segments = parts[:-1]
    basename = parts[-1]

    # 第 0 步：路徑成分防禦（E2 LOW-2）。含 `.` / `..` 成分的路徑可讓 deny 面
    # 偽裝成豁免前綴（docs/../rust/...），一律 deny。
    if any(part in {".", ".."} for part in parts):
        return _deny(normalized, "path_traversal_component_denied")

    # 第 1 步：hard-deny（觸即 ROTATED，即使 .md）。
    # rust 檔含精確 /src/ 目錄 segment：src 下的 tests 模組可能被 cfg(test) 編進
    # binary 或影響編譯單元，一律不豁免。
    if normalized.startswith("rust/") and "src" in dir_segments:
        return _deny(normalized, "rust_src_surface_changed")
    if normalized.startswith(HARD_DENY_PREFIXES):
        return _deny(normalized, "hard_denied_prefix_changed")
    # basename 先 lower 再比（E2 MEDIUM-1）：macOS/Windows 檔案系統大小寫不敏感，
    # docs/evil.TOML 與 .ENV.production 若照原樣比對會漏；fnmatchcase 避免平台
    # normcase 差異。以下 .env / 模式判定皆以 lowered basename 為準。
    lowered_basename = basename.lower()
    # basename 以 .env 開頭的任何檔（.env / .env.template / .envrc ...）＝憑證/環境面。
    if lowered_basename.startswith(".env"):
        return _deny(normalized, "env_file_changed")
    if any(
        fnmatch.fnmatchcase(lowered_basename, pattern)
        for pattern in HARD_DENY_BASENAME_PATTERNS
    ):
        return _deny(normalized, "dependency_or_config_file_changed")

    # 第 2 步：test 豁免（精確目錄 segment `tests`，且限 spec 列舉四家族——
    # PM 2026-07-03 裁決收緊，E2 MEDIUM-2）：cargo 頂層 tests/ 不編入 release
    # binary，pytest 檔不被 production import。其餘含 tests segment 的路徑
    # （newdir/tests/、helper_scripts 非 research/tests 子樹等）不得經此豁免，
    # 落到後續 docs 判定或默認 deny。
    if "tests" in dir_segments and (
        parts[0] == "rust"  # rust/<crate>/tests/**（src 已在第 1 步擋）
        or parts[0] == "program_code"
        or normalized.startswith("helper_scripts/research/tests/")
        or parts[0] == "tests"  # 頂層 tests/**
    ):
        return _exempt(normalized, "test_exempt")

    # 第 3 步：docs / 記憶豁免（operator 已批准 docs/** 全部，含 docs/agents/、
    # docs/adr/；policy-sensitive 前綴僅標記供審計，不阻斷）。
    if normalized.startswith("docs/"):
        return _exempt(
            normalized,
            "docs_exempt",
            policy_sensitive_docs=normalized.startswith(POLICY_SENSITIVE_DOC_PREFIXES),
        )
    if normalized.startswith(".codex/"):
        return _exempt(normalized, "codex_memory_exempt")
    if "/" not in normalized and normalized.endswith(".md"):
        return _exempt(
            normalized,
            "top_level_markdown_exempt",
            policy_sensitive_docs=normalized in POLICY_SENSITIVE_TOP_LEVEL_DOCS,
        )
    if normalized == SCRIPT_INDEX_PATH:
        return _exempt(normalized, "script_index_exempt")

    # 第 4 步：默認 deny（未知路徑、新頂層目錄、非 tests 的 rust/program_code/
    # helper_scripts 一律 ROTATED）。
    return _deny(normalized, "unclassified_post_approval_drift")


def _diff_status_allowed(status: str) -> bool:
    """僅接受 A/M/D/R*/C*；T/U/X/B 等狀態無法安全歸類，fail-closed。"""
    text = str(status or "").strip()
    if text in {"A", "M", "D"}:
        return True
    if text and text[0] in {"R", "C"} and (len(text) == 1 or text[1:].isdigit()):
        return True
    return False


def _classify_change(change: dict[str, Any]) -> list[dict[str, Any]]:
    """對單一 diff 條目分類；rename/copy（R*/C*）新舊兩端都要分類。"""
    status = str(change.get("status") or "").strip()
    paths = change.get("paths") or []
    if not isinstance(paths, list):
        paths = []
    status_ok = _diff_status_allowed(status)
    classified: list[dict[str, Any]] = []
    for path in paths:
        item = classify_post_approval_path(str(path))
        item["change_status"] = status or None
        if not status_ok:
            item["category"] = "unsupported_diff_status"
            item["exempt"] = False
            item["blocker"] = f"unsupported_diff_status:{status or 'missing'}"
        # binary/submodule 歧義最後覆蓋：內容不可審，即使路徑在豁免集也 ROTATED。
        if change.get("binary_or_submodule_ambiguous") is True:
            item["category"] = "binary_or_submodule_change_ambiguous"
            item["exempt"] = False
            item["blocker"] = "binary_or_submodule_change_ambiguous"
        classified.append(item)
    if not classified:
        classified.append(
            {
                "path": None,
                "category": "diff_entry_missing_path",
                "exempt": False,
                "policy_sensitive_docs": False,
                "blocker": "diff_entry_missing_path",
                "change_status": status or None,
            }
        )
    return classified


def load_approved_request_meta(path: Path, expected_sha256: str) -> dict[str, Any]:
    """讀 approved request packet 並驗證 sha256 與 policy 字段。

    為什麼 fail-closed：packet sha256 是 E3/BB 批准綁定的唯一內容錨點；
    policy 字段缺失代表批准時放寬條款未明示納入（舊版 packet），不得走豁免路徑。
    """
    meta: dict[str, Any] = {
        "path": str(path),
        "expected_sha256": str(expected_sha256 or "").strip().lower(),
        "actual_sha256": None,
        "sha256_match": False,
        "policy_field_present": False,
        "policy_field_value": None,
        "read_error": None,
    }
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        meta["read_error"] = f"approved_request_read_failed:{exc.__class__.__name__}"
        return meta
    meta["actual_sha256"] = hashlib.sha256(raw).hexdigest()
    meta["sha256_match"] = bool(meta["expected_sha256"]) and (
        meta["actual_sha256"] == meta["expected_sha256"]
    )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        meta["read_error"] = f"approved_request_json_invalid:{exc.__class__.__name__}"
        return meta
    if not isinstance(payload, dict):
        meta["read_error"] = "approved_request_json_not_object"
        return meta
    if POLICY_FIELD in payload:
        meta["policy_field_present"] = True
        meta["policy_field_value"] = payload.get(POLICY_FIELD)
    return meta


def build_post_approval_drift_gate(
    *,
    git_inputs: dict[str, Any],
    approved_request_meta: dict[str, Any],
    policy: str,
    mode_aware_inputs: dict[str, Any] | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """組 post-approval drift gate packet（deny-by-default）。

    ROTATED 條件（任一即 ROTATED）：ref 解析失敗 / 任何 git error /
    approved_head 非 origin/main ancestor（擋 force-push/rebase 改史）/
    任何 changed path 分類 deny / rename 半邊出界 / 非 A/M/D/R/C 狀態 /
    binary/gitlink/symlink 歧義（mode-aware 層；採集缺失或解析失敗本身也是
    blocker）/ packet sha256 不符 / policy 字段缺失或不符 /
    CLI policy 非唯一合法值。
    非 blocker、僅記錄：worktree dirty、HEAD != origin/main（gate 只比
    committed refs；此為與 v734 source-impact guard 的刻意差異，否則
    codex 常態流量下批准死循環無解）。
    """
    now = now_utc or _utc_now()
    blockers: list[str] = []

    policy_text = str(policy or "").strip()
    if policy_text != DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1:
        blockers.append("unknown_drift_policy")

    meta = approved_request_meta if isinstance(approved_request_meta, dict) else {}
    if not isinstance(approved_request_meta, dict):
        blockers.append("approved_request_meta_missing")
    if meta.get("read_error"):
        blockers.append("approved_request_unreadable")
    if meta.get("sha256_match") is not True:
        blockers.append("approved_request_sha256_mismatch")
    if meta.get("policy_field_present") is not True:
        blockers.append("approved_request_policy_field_missing")
    elif str(meta.get("policy_field_value") or "").strip() != policy_text:
        blockers.append("approved_request_policy_field_mismatch")

    approved = str(git_inputs.get("base_source_head") or "").strip()
    target = str(git_inputs.get("current_source_head") or "").strip()
    head = str(git_inputs.get("head") or "").strip()
    origin_main = str(git_inputs.get("origin_main") or "").strip()
    if not approved:
        blockers.append("approved_source_head_unresolved")
    if not target:
        blockers.append("drift_target_unresolved")
    if git_inputs.get("base_is_ancestor_of_current") is not True:
        blockers.append("approved_head_not_ancestor_of_origin_main")
    for error in git_inputs.get("git_errors") or []:
        if isinstance(error, dict):
            blockers.append(str(error.get("key") or "git_error"))
        else:
            blockers.append("git_error")

    changed_paths = git_inputs.get("changed_paths") or []
    if not isinstance(changed_paths, list):
        changed_paths = []
        blockers.append("changed_paths_not_list")

    classifications: list[dict[str, Any]] = []
    for change in changed_paths:
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

    # mode-aware 補充層（E2 HIGH-1/HIGH-2 修復）：採集缺失即 fail-closed——
    # 沒有 mode/binary 證據就不能宣告 EXEMPT。
    mode_aware = mode_aware_inputs if isinstance(mode_aware_inputs, dict) else None
    denied_mode_paths: set[str] = set()
    binary_no_renames: set[str] = set()
    mode_aware_errors: list[Any] = []
    if mode_aware is None:
        blockers.append("mode_aware_diff_inputs_missing")
    else:
        mode_aware_errors = list(mode_aware.get("mode_aware_errors") or [])
        for error in mode_aware_errors:
            if isinstance(error, dict):
                blockers.append(str(error.get("key") or "mode_aware_git_error"))
            else:
                blockers.append("mode_aware_git_error")
        denied_mode_paths = {str(p) for p in (mode_aware.get("denied_mode_paths") or [])}
        binary_no_renames = {str(p) for p in (mode_aware.get("binary_paths_no_renames") or [])}

    # per-path 覆蓋：--no-renames binary 集合可靠對回分類條目；gitlink/symlink
    # mode deny 最後蓋（比 binary 更具體）。任何殘留對不上的 binary 行上全局
    # blocker（配不回=內容不可審，fail-closed）。
    matched_binary: set[str] = set()
    for item in classifications:
        item_path = item.get("path")
        if item_path in binary_no_renames:
            matched_binary.add(str(item_path))
            item["category"] = "binary_or_submodule_change_ambiguous"
            item["exempt"] = False
            item["blocker"] = "binary_or_submodule_change_ambiguous"
        if item_path in denied_mode_paths:
            item["category"] = "gitlink_or_symlink_change_denied"
            item["exempt"] = False
            item["blocker"] = "gitlink_or_symlink_change_denied"
    unmatched_binary = binary_no_renames - matched_binary
    if unmatched_binary:
        blockers.append("binary_numstat_entry_unmatched")
    if denied_mode_paths:
        # 即使 denied path 因引號/編碼差異對不回分類條目，也必須整體 ROTATED。
        blockers.append("gitlink_or_symlink_change_denied")

    blockers.extend(
        sorted({str(item.get("blocker")) for item in classifications if item.get("blocker")})
    )

    policy_sensitive_docs_changed = any(
        item.get("policy_sensitive_docs") is True for item in classifications
    )

    worktree_clean = git_inputs.get("worktree_clean") is True
    head_equals_origin_main = bool(head) and head == origin_main
    non_blocking_observations: list[str] = []
    if not worktree_clean:
        non_blocking_observations.append("worktree_dirty_recorded_not_blocking")
    if not head_equals_origin_main:
        non_blocking_observations.append("head_not_equal_origin_main_recorded_not_blocking")

    exempt = not blockers
    status = EXEMPT_STATUS if exempt else ROTATED_STATUS
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _iso(now),
        "status": status,
        "reason": (
            "post_approval_net_drift_fully_within_docs_tests_codex_exempt_allowlist"
            if exempt
            else "post_approval_drift_outside_exempt_allowlist_or_gate_inputs_invalid"
        ),
        "policy": policy_text or None,
        "boundary": BOUNDARY,
        "source_state": {
            "approved_source_head": approved or None,
            # CLI 恆以 origin/main 為 drift 比較目標；歷史回放可傳其他 committed sha。
            "drift_target_head": target or None,
            "origin_main": origin_main or None,
            "head": head or None,
            "head_equals_origin_main": head_equals_origin_main,
            "worktree_clean": worktree_clean,
            "dirty_paths": git_inputs.get("dirty_paths") or [],
            "approved_head_is_ancestor_of_origin_main": git_inputs.get(
                "base_is_ancestor_of_current"
            )
            is True,
            "status_short_branch": git_inputs.get("status_short_branch"),
        },
        "approved_request": {
            "path": meta.get("path"),
            "expected_sha256": meta.get("expected_sha256"),
            "actual_sha256": meta.get("actual_sha256"),
            "sha256_match": meta.get("sha256_match") is True,
            "policy_field_present": meta.get("policy_field_present") is True,
            "policy_field_value": meta.get("policy_field_value"),
            "read_error": meta.get("read_error"),
        },
        "changed_path_count": len(classifications),
        "changed_path_classifications": classifications,
        "policy_sensitive_docs_changed": policy_sensitive_docs_changed,
        "mode_aware_diff": {
            "collected": mode_aware is not None,
            "denied_mode_paths": sorted(denied_mode_paths),
            "binary_paths_no_renames": sorted(binary_no_renames),
            "unmatched_binary_paths": sorted(unmatched_binary),
            "raw_entry_count": len((mode_aware or {}).get("raw_entries") or []),
            "errors": mode_aware_errors,
        },
        "git_errors": git_inputs.get("git_errors") or [],
        "non_blocking_observations": non_blocking_observations,
        "blockers": sorted(set(blockers)),
        # 配套約束：EXEMPT 延續時 runtime 動作必須從 approved_head 的 clean detached
        # worktree 執行，確保實際執行字節與 E3/BB 批准時逐位一致。
        "approved_execution_constraint": (
            "runtime actions under a continued approval must run from a clean "
            "detached worktree checked out at approved_source_head; do not rebase "
            "onto or rerun from the advanced head"
        ),
        "answers": {
            "post_approval_drift_exempt": exempt,
            "approved_execution_must_run_from_approved_head_worktree": True,
            "approval_granted_by_this_packet": False,
            "runtime_call_performed": False,
            "control_api_get_performed": False,
            "bybit_call_performed": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
            "risk_mutation_performed": False,
            "cost_gate_change_performed": False,
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "promotion_proof": False,
            "profit_proof": False,
        },
        "max_safe_next_action": (
            "PROCEED_APPROVED_RUNTIME_STEPS_FROM_APPROVED_HEAD_CLEAN_DETACHED_WORKTREE_ONLY"
            if exempt
            else "ROTATE_APPROVAL_REGENERATE_EXACT_REQUEST_AND_REDO_E3_BB_REVIEW_NO_RUNTIME_ACTION"
        ),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    # 全主參數必填、無默認寬鬆值（禁 dead param）；不引入任何環境變量 flag。
    parser = argparse.ArgumentParser(
        description="Build a post-approval drift gate packet for standing-envelope refresh."
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--approved-source-head", required=True)
    parser.add_argument("--approved-request-json", type=Path, required=True)
    parser.add_argument("--approved-request-sha256", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--now-utc")
    parser.add_argument("--print-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    now = _parse_dt(args.now_utc) if args.now_utc else _utc_now()
    if now is None:
        raise SystemExit("--now-utc must be an ISO-8601 timestamp")
    approved_request_meta = load_approved_request_meta(
        args.approved_request_json, args.approved_request_sha256
    )
    # 不 fetch：只比較本地已知的 approved head 與 origin/main committed refs。
    git_inputs = collect_git_impact_inputs(
        args.repo_root.resolve(),
        base_source_head=args.approved_source_head,
        current_source_head="origin/main",
        now_utc=now,
    )
    # 消除與 v734 collector 間的 TOCTOU 窄縫：mode-aware 層對 v734 已 resolve 的
    # 同一個 sha 採集，而非再解析一次 symbolic origin/main（兩次解析之間 ref 可能
    # 前進，兩層會看到不同 diff）。resolved 為空（ref 解析失敗）時沿用 symbolic
    # 值——git diff 必再失敗並產生 mode_aware error blocker，維持 fail-closed，
    # 不引入新放行邊。
    resolved_target = str(git_inputs.get("current_source_head") or "").strip()
    mode_aware_inputs = collect_mode_aware_diff_inputs(
        args.repo_root.resolve(),
        base_source_head=args.approved_source_head,
        current_source_head=resolved_target or "origin/main",
    )
    packet = build_post_approval_drift_gate(
        git_inputs=git_inputs,
        approved_request_meta=approved_request_meta,
        policy=args.policy,
        mode_aware_inputs=mode_aware_inputs,
        now_utc=now,
    )
    _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

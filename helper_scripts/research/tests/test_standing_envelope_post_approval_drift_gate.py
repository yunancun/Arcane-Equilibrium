from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from cost_gate_learning_lane import standing_envelope_post_approval_drift_gate as mod


NOW = dt.datetime(2026, 7, 2, 12, 0, tzinfo=dt.timezone.utc)
APPROVED = "a" * 40
TARGET = "b" * 40

# 真實歷史回放錨點（本 repo；shallow clone 解析不到時 skip）。
REPO_ROOT = Path(__file__).resolve().parents[3]
EXEMPT_REPLAY_BASE = "bfbbd343fa359216813fc865962ba1730d164d64"
EXEMPT_REPLAY_TARGET = "70f0f3750ba34989496e48b8817c1aa0aae1d7a1"
ROTATED_REPLAY_BASE = "c0a827b630cf3c4c57096525125c95b03e4d89ef"
ROTATED_REPLAY_TARGET = "929593791f3f20e46e1dde0d7bb688db1dc4ade3"


def _change(path: str, status: str = "M") -> dict:
    return {"status": status, "paths": [path], "raw": f"{status}\t{path}"}


def _two_path_change(old: str, new: str, status: str = "R100") -> dict:
    return {"status": status, "paths": [old, new], "raw": f"{status}\t{old}\t{new}"}


def _inputs(*changes: dict, **overrides) -> dict:
    payload = {
        "base_source_head": APPROVED,
        "current_source_head": TARGET,
        "head": TARGET,
        "origin_main": TARGET,
        "status_short_branch": "## main...origin/main",
        "worktree_clean": True,
        "dirty_paths": [],
        "base_is_ancestor_of_current": True,
        "changed_paths": list(changes),
        "git_errors": [],
    }
    payload.update(overrides)
    return payload


def _meta(**overrides) -> dict:
    payload = {
        "path": "approved_request.json",
        "expected_sha256": "f" * 64,
        "actual_sha256": "f" * 64,
        "sha256_match": True,
        "policy_field_present": True,
        "policy_field_value": mod.DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1,
        "read_error": None,
    }
    payload.update(overrides)
    return payload


def _mode_aware(**overrides) -> dict:
    payload = {
        "raw_entries": [],
        "denied_mode_paths": [],
        "binary_paths_no_renames": [],
        "mode_aware_errors": [],
    }
    payload.update(overrides)
    return payload


_UNSET = object()


def _packet(
    *changes: dict,
    policy: str | None = None,
    meta: dict | None = None,
    mode_aware=_UNSET,
    **overrides,
) -> dict:
    return mod.build_post_approval_drift_gate(
        git_inputs=_inputs(*changes, **overrides),
        approved_request_meta=meta if meta is not None else _meta(),
        policy=policy if policy is not None else mod.DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1,
        mode_aware_inputs=_mode_aware() if mode_aware is _UNSET else mode_aware,
        now_utc=NOW,
    )


def _git(repo, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def _init_repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "docs").mkdir()
    (repo / "docs" / "base.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    return repo


def _commit_file(repo: Path, rel: str, content="x\n", message: str = "c") -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _write_request(tmp_path, name: str = "approved_request.json", payload: dict | None = None):
    request = tmp_path / name
    body = (
        {mod.POLICY_FIELD: mod.DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1, "schema_version": "x_v1"}
        if payload is None
        else payload
    )
    request.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    sha = hashlib.sha256(request.read_bytes()).hexdigest()
    return request, sha


def _run_gate(repo: Path, approved: str, request: Path, sha: str, out: Path, policy: str | None = None) -> dict:
    rc = mod.main(
        [
            "--repo-root",
            str(repo),
            "--approved-source-head",
            approved,
            "--approved-request-json",
            str(request),
            "--approved-request-sha256",
            sha,
            "--policy",
            policy or mod.DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1,
            "--json-output",
            str(out),
            "--now-utc",
            "2026-07-02T12:00:00Z",
        ]
    )
    assert rc == 0
    return json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1) 表驅動 classify 單測
# ---------------------------------------------------------------------------

EXEMPT_PATHS = [
    "docs/CCAgentWorkSpace/PM/workspace/reports/x.md",
    "docs/agents/x.md",
    ".codex/MEMORY.md",
    "TODO.md",
    "README.md",
    "CLAUDE.md",
    "helper_scripts/SCRIPT_INDEX.md",
    "rust/openclaw_types/tests/x.rs",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_x.py",
    "helper_scripts/research/tests/test_x.py",
]

ROTATED_PATHS = [
    "rust/openclaw_engine/src/ipc_server/handlers/x.rs",
    # src 下的 tests 模組不可被 test 豁免穿透（cfg(test) 可能編進 binary）
    "rust/openclaw_engine/src/ipc_server/tests/x.rs",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/app/x.py",
    "helper_scripts/research/cost_gate_learning_lane/x.py",
    "helper_scripts/restart_all.sh",
    "settings/x.toml",
    "sql/V140__x.sql",
    ".env.template",
    "engine.toml",
    "Cargo.lock",
    ".github/workflows/ci.yml",
    ".claude/hooks/rtk-rewrite.sh",
    # deny 先判：program_code 下的 .md 不因副檔名放行
    "program_code/README.md",
    # 全新頂層目錄默認 deny
    "newdir/x.py",
    # E2 MEDIUM-1：大小寫變體不得繞過 basename hard-deny（docs 豁免前先判）
    "docs/evil.TOML",
    "docs/.ENV.production",
    # E2 MEDIUM-2（PM 裁決收緊）：tests 豁免限四家族，其餘含 tests segment 落默認 deny
    "newdir/tests/x.py",
    "helper_scripts/cron/tests/x.sh",
    # E2 LOW-2：路徑成分防禦——`..` 可讓 deny 面偽裝成豁免前綴
    "docs/../rust/openclaw_engine/src/lib.rs",
]


@pytest.mark.parametrize("path", EXEMPT_PATHS)
def test_classify_exempt_paths(path: str) -> None:
    item = mod.classify_post_approval_path(path)
    assert item["exempt"] is True
    assert item["blocker"] is None


@pytest.mark.parametrize("path", ROTATED_PATHS)
def test_classify_rotated_paths(path: str) -> None:
    item = mod.classify_post_approval_path(path)
    assert item["exempt"] is False
    assert item["blocker"]


def test_policy_sensitive_docs_marked_but_exempt() -> None:
    item = mod.classify_post_approval_path("docs/agents/x.md")
    assert item["exempt"] is True
    assert item["policy_sensitive_docs"] is True

    packet = _packet(_change("docs/agents/x.md"), _change("TODO.md"))
    assert packet["status"] == mod.EXEMPT_STATUS
    assert packet["policy_sensitive_docs_changed"] is True

    plain = _packet(_change("docs/CCAgentWorkSpace/PM/workspace/reports/x.md"))
    assert plain["status"] == mod.EXEMPT_STATUS
    assert plain["policy_sensitive_docs_changed"] is False


def test_exempt_packet_answers_declare_no_authority_and_worktree_constraint() -> None:
    packet = _packet(_change("docs/safe.md"))

    assert packet["schema_version"] == mod.SCHEMA_VERSION
    assert packet["status"] == mod.EXEMPT_STATUS
    assert packet["blockers"] == []
    answers = packet["answers"]
    assert answers["post_approval_drift_exempt"] is True
    assert answers["approved_execution_must_run_from_approved_head_worktree"] is True
    assert answers["approval_granted_by_this_packet"] is False
    assert answers["runtime_call_performed"] is False
    assert answers["order_submission_performed"] is False
    assert answers["live_authority_granted"] is False
    assert "APPROVED_HEAD_CLEAN_DETACHED_WORKTREE" in packet["max_safe_next_action"]


def test_zero_diff_is_exempt() -> None:
    packet = _packet(
        current_source_head=APPROVED,
        origin_main=APPROVED,
        head=APPROVED,
    )
    assert packet["status"] == mod.EXEMPT_STATUS
    assert packet["changed_path_count"] == 0


def test_worktree_dirty_and_head_mismatch_are_recorded_not_blockers() -> None:
    # 與舊 v734 guard 的關鍵差異：這兩項僅記錄、不阻斷（否則 codex 常態流量下死循環）。
    packet = _packet(
        _change("docs/safe.md"),
        worktree_clean=False,
        dirty_paths=[" M memory/MEMORY.md"],
        head="c" * 40,
    )
    assert packet["status"] == mod.EXEMPT_STATUS
    assert packet["source_state"]["worktree_clean"] is False
    assert packet["source_state"]["head_equals_origin_main"] is False
    assert "worktree_dirty_recorded_not_blocking" in packet["non_blocking_observations"]
    assert "head_not_equal_origin_main_recorded_not_blocking" in packet["non_blocking_observations"]


# ---------------------------------------------------------------------------
# 2) rename/copy 與 diff 狀態
# ---------------------------------------------------------------------------

def test_rename_docs_to_docs_exempt() -> None:
    packet = _packet(_two_path_change("docs/a.md", "docs/b.md", "R100"))
    assert packet["status"] == mod.EXEMPT_STATUS


def test_rename_docs_to_program_code_rotated() -> None:
    packet = _packet(_two_path_change("docs/a.md", "program_code/x/a.py", "R100"))
    assert packet["status"] == mod.ROTATED_STATUS
    assert "unclassified_post_approval_drift" in packet["blockers"]


def test_rename_program_code_to_docs_rotated() -> None:
    packet = _packet(_two_path_change("program_code/x/a.py", "docs/a.md", "R100"))
    assert packet["status"] == mod.ROTATED_STATUS
    assert "unclassified_post_approval_drift" in packet["blockers"]


def test_copy_docs_to_program_code_rotated() -> None:
    packet = _packet(_two_path_change("docs/a.md", "program_code/x/a.py", "C100"))
    assert packet["status"] == mod.ROTATED_STATUS


def test_copy_docs_to_docs_exempt() -> None:
    packet = _packet(_two_path_change("docs/a.md", "docs/b.md", "C100"))
    assert packet["status"] == mod.EXEMPT_STATUS


@pytest.mark.parametrize("status", ["T", "U"])
def test_unsupported_diff_status_rotated(status: str) -> None:
    packet = _packet(_change("docs/a.md", status=status))
    assert packet["status"] == mod.ROTATED_STATUS
    assert any(b.startswith("unsupported_diff_status") for b in packet["blockers"])


def test_binary_or_submodule_ambiguity_rotated_even_under_docs() -> None:
    packet = _packet(
        {
            "status": "A",
            "paths": ["docs/image.png"],
            "raw": "A\tdocs/image.png",
            "binary_or_submodule_ambiguous": True,
        }
    )
    assert packet["status"] == mod.ROTATED_STATUS
    assert "binary_or_submodule_change_ambiguous" in packet["blockers"]


# ---------------------------------------------------------------------------
# mode-aware 補充層（E2 HIGH-1/HIGH-2/LOW-1 修復）
# ---------------------------------------------------------------------------

def test_missing_mode_aware_inputs_rotated() -> None:
    # 沒有 mode/binary 證據不能宣告 EXEMPT
    packet = _packet(_change("docs/safe.md"), mode_aware=None)
    assert packet["status"] == mod.ROTATED_STATUS
    assert "mode_aware_diff_inputs_missing" in packet["blockers"]
    assert packet["mode_aware_diff"]["collected"] is False


def test_mode_aware_collection_errors_rotated() -> None:
    packet = _packet(
        _change("docs/safe.md"),
        mode_aware=_mode_aware(
            mode_aware_errors=[{"key": "git_diff_raw_failed", "stderr": "boom"}]
        ),
    )
    assert packet["status"] == mod.ROTATED_STATUS
    assert "git_diff_raw_failed" in packet["blockers"]


def test_denied_mode_path_rotated_even_under_docs() -> None:
    # gitlink/symlink mode 強制 deny，不論路徑落在豁免樹
    packet = _packet(
        _change("docs/sublink", status="A"),
        mode_aware=_mode_aware(denied_mode_paths=["docs/sublink"]),
    )
    assert packet["status"] == mod.ROTATED_STATUS
    assert "gitlink_or_symlink_change_denied" in packet["blockers"]
    denied = [
        item
        for item in packet["changed_path_classifications"]
        if item["path"] == "docs/sublink"
    ]
    assert denied and denied[0]["blocker"] == "gitlink_or_symlink_change_denied"


def test_binary_no_renames_set_marks_matching_path_rotated() -> None:
    packet = _packet(
        _change("docs/image.png", status="A"),
        mode_aware=_mode_aware(binary_paths_no_renames=["docs/image.png"]),
    )
    assert packet["status"] == mod.ROTATED_STATUS
    assert "binary_or_submodule_change_ambiguous" in packet["blockers"]


def test_unmatched_binary_numstat_entry_global_blocker() -> None:
    # binary 行對不回任何分類條目（引號/編碼差異）→ 全局 fail-closed
    packet = _packet(
        _two_path_change("docs/a.png", "docs/b.png", "R099"),
        mode_aware=_mode_aware(binary_paths_no_renames=["docs/{a.png => b.png}"]),
    )
    assert packet["status"] == mod.ROTATED_STATUS
    assert "binary_numstat_entry_unmatched" in packet["blockers"]


# ---------------------------------------------------------------------------
# packet / policy fail-closed
# ---------------------------------------------------------------------------

def test_non_ancestor_approved_head_rotated() -> None:
    packet = _packet(_change("docs/a.md"), base_is_ancestor_of_current=False)
    assert packet["status"] == mod.ROTATED_STATUS
    assert "approved_head_not_ancestor_of_origin_main" in packet["blockers"]


def test_git_errors_rotated() -> None:
    packet = _packet(
        _change("docs/a.md"),
        git_errors=[{"key": "base_ref_unresolved", "stderr": "bad rev"}],
    )
    assert packet["status"] == mod.ROTATED_STATUS
    assert "base_ref_unresolved" in packet["blockers"]


def test_request_sha256_mismatch_rotated() -> None:
    packet = _packet(_change("docs/a.md"), meta=_meta(sha256_match=False))
    assert packet["status"] == mod.ROTATED_STATUS
    assert "approved_request_sha256_mismatch" in packet["blockers"]


def test_request_policy_field_missing_rotated() -> None:
    packet = _packet(
        _change("docs/a.md"),
        meta=_meta(policy_field_present=False, policy_field_value=None),
    )
    assert packet["status"] == mod.ROTATED_STATUS
    assert "approved_request_policy_field_missing" in packet["blockers"]


def test_request_policy_field_mismatch_rotated() -> None:
    packet = _packet(_change("docs/a.md"), meta=_meta(policy_field_value="other_policy"))
    assert packet["status"] == mod.ROTATED_STATUS
    assert "approved_request_policy_field_mismatch" in packet["blockers"]


def test_unknown_cli_policy_rotated() -> None:
    packet = _packet(_change("docs/a.md"), policy="docs_tests_codex_exempt_v2")
    assert packet["status"] == mod.ROTATED_STATUS
    assert "unknown_drift_policy" in packet["blockers"]


# ---------------------------------------------------------------------------
# 3) temp-git 整合 + 5) CLI 端到端
# ---------------------------------------------------------------------------

def test_temp_git_docs_codex_tests_drift_exempt_then_app_commit_rotated(tmp_path) -> None:
    repo = _init_repo(tmp_path)
    approved = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "docs/CCAgentWorkSpace/PM/workspace/reports/x.md")
    _commit_file(repo, ".codex/MEMORY.md")
    _commit_file(repo, "helper_scripts/research/tests/test_new.py")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    request, sha = _write_request(tmp_path)

    packet = _run_gate(repo, approved, request, sha, tmp_path / "gate_exempt.json")
    assert packet["status"] == mod.EXEMPT_STATUS
    assert packet["blockers"] == []
    assert packet["source_state"]["approved_source_head"] == approved
    assert packet["answers"]["post_approval_drift_exempt"] is True

    # 再疊一個 app 檔 commit → ROTATED
    _commit_file(repo, "program_code/x/app.py")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    rotated = _run_gate(repo, approved, request, sha, tmp_path / "gate_rotated.json")
    assert rotated["status"] == mod.ROTATED_STATUS
    assert "unclassified_post_approval_drift" in rotated["blockers"]


def test_temp_git_non_ancestor_approved_head_rotated(tmp_path) -> None:
    repo = _init_repo(tmp_path)
    _git(repo, "checkout", "-b", "side")
    approved = _commit_file(repo, "docs/side.md")
    _git(repo, "checkout", "main")
    _commit_file(repo, "docs/main.md")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    request, sha = _write_request(tmp_path)

    packet = _run_gate(repo, approved, request, sha, tmp_path / "gate.json")
    assert packet["status"] == mod.ROTATED_STATUS
    assert "approved_head_not_ancestor_of_origin_main" in packet["blockers"]


def test_temp_git_binary_file_rotated(tmp_path) -> None:
    repo = _init_repo(tmp_path)
    approved = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "docs/blob.bin", content=b"\x00\x01\x02binary")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    request, sha = _write_request(tmp_path)

    packet = _run_gate(repo, approved, request, sha, tmp_path / "gate.json")
    assert packet["status"] == mod.ROTATED_STATUS
    assert "binary_or_submodule_change_ambiguous" in packet["blockers"]


def test_temp_git_binary_rename_rotated(tmp_path) -> None:
    # E2 HIGH-1 repro：binary rename 的 curly-brace numstat 曾使 per-change
    # ambiguous 永不觸發 → false-EXEMPT；--no-renames 集合必須抓回。
    repo = _init_repo(tmp_path)
    payload = bytes([0, 1, 2, 3] * 50)
    _commit_file(repo, "docs/a.png", content=payload)
    approved = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", "docs/a.png", "docs/b.png")
    (repo / "docs" / "b.png").write_bytes(payload[:-2] + b"\xff\xfe")
    _git(repo, "add", "docs/b.png")
    _git(repo, "commit", "-m", "rename+modify binary")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    request, sha = _write_request(tmp_path)

    packet = _run_gate(repo, approved, request, sha, tmp_path / "gate.json")
    assert packet["status"] == mod.ROTATED_STATUS
    assert (
        "binary_or_submodule_change_ambiguous" in packet["blockers"]
        or "binary_numstat_entry_unmatched" in packet["blockers"]
    )
    # 釘住 rename 場景本身（name-status 確為 R*）
    assert any(
        str(item.get("change_status") or "").startswith("R")
        for item in packet["changed_path_classifications"]
    )


def test_temp_git_bare_gitlink_add_and_modify_rotated(tmp_path) -> None:
    # E2 HIGH-2 repro：裸 gitlink 的 numstat 是 1\t0 非 "-"，原配方永不觸發
    # → false-EXEMPT；--raw mode 160000 必須 deny。
    repo = _init_repo(tmp_path)
    approved = _git(repo, "rev-parse", "HEAD")
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{approved},docs/sublink",
    )
    _git(repo, "commit", "-m", "add bare gitlink")
    first_gitlink_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    request, sha = _write_request(tmp_path)

    added = _run_gate(repo, approved, request, sha, tmp_path / "gate_gitlink_add.json")
    assert added["status"] == mod.ROTATED_STATUS
    assert "gitlink_or_symlink_change_denied" in added["blockers"]

    # M 場景：改 gitlink 指向的 sha
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{'1' * 40},docs/sublink",
    )
    _git(repo, "commit", "-m", "modify bare gitlink")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    modified = _run_gate(
        repo, first_gitlink_commit, request, sha, tmp_path / "gate_gitlink_mod.json"
    )
    assert modified["status"] == mod.ROTATED_STATUS
    assert "gitlink_or_symlink_change_denied" in modified["blockers"]


def test_temp_git_symlink_add_rotated(tmp_path) -> None:
    # symlink（mode 120000）可指向豁免樹外，即使檔名長得像 docs md 也 deny。
    repo = _init_repo(tmp_path)
    approved = _git(repo, "rev-parse", "HEAD")
    os.symlink("base.md", repo / "docs" / "link.md")
    _git(repo, "add", "docs/link.md")
    _git(repo, "commit", "-m", "add symlink")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    request, sha = _write_request(tmp_path)

    packet = _run_gate(repo, approved, request, sha, tmp_path / "gate.json")
    assert packet["status"] == mod.ROTATED_STATUS
    assert "gitlink_or_symlink_change_denied" in packet["blockers"]


def test_temp_git_request_sha_mismatch_rotated(tmp_path) -> None:
    repo = _init_repo(tmp_path)
    approved = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "docs/safe.md")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    request, _sha = _write_request(tmp_path)

    packet = _run_gate(repo, approved, request, "0" * 64, tmp_path / "gate.json")
    assert packet["status"] == mod.ROTATED_STATUS
    assert "approved_request_sha256_mismatch" in packet["blockers"]


def test_temp_git_request_missing_policy_field_rotated(tmp_path) -> None:
    repo = _init_repo(tmp_path)
    approved = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "docs/safe.md")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    request, sha = _write_request(
        tmp_path, name="approved_request_no_policy.json", payload={"schema_version": "x_v1"}
    )

    packet = _run_gate(repo, approved, request, sha, tmp_path / "gate.json")
    assert packet["status"] == mod.ROTATED_STATUS
    assert "approved_request_policy_field_missing" in packet["blockers"]


def test_temp_git_wrong_cli_policy_rotated(tmp_path) -> None:
    repo = _init_repo(tmp_path)
    approved = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "docs/safe.md")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    request, sha = _write_request(tmp_path)

    packet = _run_gate(
        repo, approved, request, sha, tmp_path / "gate.json", policy="not_a_policy"
    )
    assert packet["status"] == mod.ROTATED_STATUS
    assert "unknown_drift_policy" in packet["blockers"]
    # CLI policy 與 packet 字段也不一致 → 同時觸發 mismatch
    assert "approved_request_policy_field_mismatch" in packet["blockers"]


# ---------------------------------------------------------------------------
# 4) 真實歷史回放（本 repo；shallow clone 解析不到就 skip，不得靜默 pass）
# ---------------------------------------------------------------------------

def _resolve_or_skip(*shas: str) -> None:
    for sha in shas:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--verify", f"{sha}^{{commit}}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            pytest.skip(
                f"replay commit {sha} not resolvable in {REPO_ROOT} (shallow clone?)"
            )


def test_real_history_replay_v738_docs_tests_codex_drift_is_exempt() -> None:
    # v738 死循環殺手 diff：純 .codex + docs + rust/openclaw_types/tests → 新判準下 EXEMPT。
    _resolve_or_skip(EXEMPT_REPLAY_BASE, EXEMPT_REPLAY_TARGET)
    git_inputs = mod.collect_git_impact_inputs(
        REPO_ROOT,
        base_source_head=EXEMPT_REPLAY_BASE,
        current_source_head=EXEMPT_REPLAY_TARGET,
        now_utc=NOW,
    )
    mode_aware = mod.collect_mode_aware_diff_inputs(
        REPO_ROOT,
        base_source_head=EXEMPT_REPLAY_BASE,
        current_source_head=EXEMPT_REPLAY_TARGET,
    )
    packet = mod.build_post_approval_drift_gate(
        git_inputs=git_inputs,
        approved_request_meta=_meta(),
        policy=mod.DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1,
        mode_aware_inputs=mode_aware,
        now_utc=NOW,
    )
    assert packet["status"] == mod.EXEMPT_STATUS
    assert packet["blockers"] == []
    assert packet["changed_path_count"] > 0


def test_real_history_replay_true_code_drift_is_rotated() -> None:
    # 真代碼漂移（program_code app + rust src）仍 fail-closed ROTATED。
    _resolve_or_skip(ROTATED_REPLAY_BASE, ROTATED_REPLAY_TARGET)
    git_inputs = mod.collect_git_impact_inputs(
        REPO_ROOT,
        base_source_head=ROTATED_REPLAY_BASE,
        current_source_head=ROTATED_REPLAY_TARGET,
        now_utc=NOW,
    )
    mode_aware = mod.collect_mode_aware_diff_inputs(
        REPO_ROOT,
        base_source_head=ROTATED_REPLAY_BASE,
        current_source_head=ROTATED_REPLAY_TARGET,
    )
    packet = mod.build_post_approval_drift_gate(
        git_inputs=git_inputs,
        approved_request_meta=_meta(),
        policy=mod.DRIFT_POLICY_DOCS_TESTS_CODEX_EXEMPT_V1,
        mode_aware_inputs=mode_aware,
        now_utc=NOW,
    )
    assert packet["status"] == mod.ROTATED_STATUS
    assert "rust_src_surface_changed" in packet["blockers"]
    assert "unclassified_post_approval_drift" in packet["blockers"]

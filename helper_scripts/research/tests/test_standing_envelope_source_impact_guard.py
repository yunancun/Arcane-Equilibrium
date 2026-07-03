from __future__ import annotations

import datetime as dt
import json
import os
import subprocess

from cost_gate_learning_lane import standing_envelope_source_impact_guard as mod


NOW = dt.datetime(2026, 7, 1, 18, 20, tzinfo=dt.timezone.utc)
BASE = "19dae0394eb75be349b34ffaed1010ff9b3cd777"
CURRENT = "8ff95f3a2471f9404ed391c82f7214d1f07ad02a"


def _change(path: str, status: str = "M") -> dict:
    return {"status": status, "paths": [path], "raw": f"{status}\t{path}"}


def _inputs(*changes: dict, **overrides) -> dict:
    payload = {
        "base_source_head": BASE,
        "current_source_head": CURRENT,
        "head": CURRENT,
        "origin_main": CURRENT,
        "status_short_branch": "## HEAD (no branch)",
        "worktree_clean": True,
        "dirty_paths": [],
        "base_is_ancestor_of_current": True,
        "changed_paths": list(changes),
    }
    payload.update(overrides)
    return payload


def _packet(*changes: dict, **overrides) -> dict:
    return mod.build_standing_envelope_source_impact_guard(
        git_inputs=_inputs(*changes, **overrides),
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


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "docs").mkdir()
    return repo


def _collect_and_build(repo, base: str) -> dict:
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git_inputs = mod.collect_git_impact_inputs(
        repo,
        base_source_head=base,
        current_source_head="HEAD",
        now_utc=NOW,
    )
    return mod.build_standing_envelope_source_impact_guard(
        git_inputs=git_inputs,
        now_utc=NOW,
    )


def test_docs_tests_and_guard_tooling_are_ready_no_authority() -> None:
    packet = _packet(
        _change("docs/CCAgentWorkSpace/PM/memory.md"),
        _change("rust/openclaw_types/tests/stock_etf_gui_lane_contract_acceptance.rs"),
        _change(
            "helper_scripts/research/cost_gate_learning_lane/"
            "standing_envelope_source_impact_guard.py",
            "A",
        ),
        _change("helper_scripts/research/tests/test_standing_envelope_source_impact_guard.py", "A"),
        _change("helper_scripts/SCRIPT_INDEX.md"),
    )

    assert packet["schema_version"] == mod.SCHEMA_VERSION
    assert packet["status"] == mod.READY_STATUS
    assert packet["blockers"] == []
    assert packet["answers"]["source_impact_ready_for_e3_bb_review"] is True
    assert packet["answers"]["approval_granted_by_this_packet"] is False
    assert packet["answers"]["runtime_call_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["max_safe_next_action"] == (
        "REQUEST_E3_BB_WITH_SOURCE_IMPACT_PACKET_NO_RUNTIME_ACTION"
    )


def test_policy_sensitive_docs_block() -> None:
    packet = _packet(
        _change("TODO.md"),
        _change("AGENTS.md"),
        _change("docs/agents/profit-first-autonomy-loop.md"),
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert packet["blockers"] == ["policy_sensitive_context_changed"]


def test_blocks_standing_refresh_guardrail_source_change() -> None:
    packet = _packet(
        _change(
            "helper_scripts/research/cost_gate_learning_lane/"
            "standing_demo_authorization_refresh_guardrail.py"
        )
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "cost_gate_learning_lane_surface_changed" in packet["blockers"]
    assert packet["answers"]["source_impact_ready_for_e3_bb_review"] is False


def test_blocks_control_api_fast_balance_surface_change() -> None:
    packet = _packet(
        _change("program_code/exchange_connectors/bybit_connector/control_api_v1/app/demo_routes.py")
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "bybit_connector_surface_changed" in packet["blockers"]


def test_blocks_rust_production_source_change_but_not_rust_tests() -> None:
    blocked = _packet(_change("rust/openclaw_engine/src/main.rs"))
    ready = _packet(_change("rust/openclaw_engine/tests/standing_refresh_fixture.rs"))

    assert blocked["status"] == mod.BLOCKED_STATUS
    assert "rust_production_surface_changed" in blocked["blockers"]
    assert ready["status"] == mod.READY_STATUS


def test_blocks_runtime_scripts_and_dependency_changes() -> None:
    packet = _packet(
        _change("helper_scripts/restart_all.sh"),
        _change("rust/Cargo.toml"),
        _change(".github/workflows/ci.yml"),
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "runtime_script_surface_changed" in packet["blockers"]
    assert "dependency_or_config_surface_changed" in packet["blockers"]
    assert "ci_runtime_policy_surface_changed" in packet["blockers"]


def test_blocks_unclassified_source_change() -> None:
    packet = _packet(_change("scripts/unknown_runtime_tool.sh"))

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "unclassified_source_change" in packet["blockers"]


def test_blocks_dirty_worktree() -> None:
    packet = _packet(
        _change("docs/safe.md"),
        worktree_clean=False,
        dirty_paths=[" M TODO.md"],
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "worktree_dirty" in packet["blockers"]


def test_blocks_head_origin_mismatch_and_non_head_current() -> None:
    packet = _packet(
        _change("docs/safe.md"),
        origin_main="different",
        current_source_head="different",
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "head_origin_mismatch" in packet["blockers"]
    assert "current_source_head_not_checked_out_head" in packet["blockers"]


def test_blocks_non_ancestor_base() -> None:
    packet = _packet(_change("docs/safe.md"), base_is_ancestor_of_current=False)

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "base_not_ancestor_of_current" in packet["blockers"]


def test_blocks_git_ref_errors() -> None:
    packet = _packet(
        _change("docs/safe.md"),
        git_errors=[{"key": "base_ref_unresolved", "stderr": "bad rev"}],
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "base_ref_unresolved" in packet["blockers"]


def test_blocks_binary_or_submodule_ambiguity() -> None:
    packet = _packet(
        {
            "status": "M",
            "paths": ["docs/binary.pdf"],
            "raw": "M\tdocs/binary.pdf",
            "binary_or_submodule_ambiguous": True,
        }
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "binary_or_submodule_change_ambiguous" in packet["blockers"]


def test_render_markdown_includes_status_and_boundary() -> None:
    packet = _packet(_change("docs/safe.md"))
    markdown = mod.render_markdown(packet)

    assert "# Standing Envelope Source Impact Guard" in markdown
    assert f"- Status: `{mod.READY_STATUS}`" in markdown
    assert "no runtime call" in markdown


def test_temp_git_blocks_binary_rename_under_docs(tmp_path) -> None:
    # 假陰性回歸（E2 2026-07-03 實證）：binary rename 在帶 rename 偵測的 numstat
    # 中是 curly-brace 合併路徑，舊碼 flag 永不觸發，docs/ 下即 READY 放行。
    repo = _make_repo(tmp_path)
    (repo / "docs" / "a.bin").write_bytes(b"\x00\x01\x02binary-payload")
    _git(repo, "add", "docs/a.bin")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", "docs/a.bin", "docs/b.bin")
    _git(repo, "commit", "-m", "rename binary under docs")

    packet = _collect_and_build(repo, base)

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "binary_or_submodule_change_ambiguous" in packet["blockers"]


def test_temp_git_blocks_bare_gitlink_under_docs(tmp_path) -> None:
    # 假陰性回歸：裸 gitlink（mode 160000）的 numstat 是行數而非 "-"，舊碼根本
    # 不觸 binary 偵測；靠 --raw mode 白名單攔。gitlink 目錄不存在於 worktree，
    # 可能同時觸 worktree_dirty，本測試只釘 mode 歧義 blocker。
    repo = _make_repo(tmp_path)
    (repo / "docs" / "safe.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "docs/safe.md")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{base},docs/subrepo")
    _git(repo, "commit", "-m", "add bare gitlink under docs")

    packet = _collect_and_build(repo, base)

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "binary_or_submodule_change_ambiguous" in packet["blockers"]


def test_temp_git_blocks_symlink_under_docs(tmp_path) -> None:
    # 假陰性回歸：symlink（mode 120000）numstat 給行數、name-status 是 A/M，
    # 舊碼按路徑分類（docs/ = documentation_or_todo）放行；symlink 可指向豁免樹
    # 外任意目標，必須 fail-closed。
    repo = _make_repo(tmp_path)
    (repo / "docs" / "safe.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "docs/safe.md")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    os.symlink("safe.md", repo / "docs" / "link.md")
    _git(repo, "add", "docs/link.md")
    _git(repo, "commit", "-m", "add symlink under docs")

    packet = _collect_and_build(repo, base)

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "binary_or_submodule_change_ambiguous" in packet["blockers"]


def test_unmatched_flagged_paths_escalate_to_blocker() -> None:
    # unmatched 安全網：flagged 路徑對不回任何 name-status 條目時，per-change
    # flag 無處落地，必須經 git_errors 升為 blocker，不得默默放行。
    unmatched = mod._unmatched_flagged_paths(
        {"docs/orphan.bin", "docs/covered.bin"},
        [{"status": "M", "paths": ["docs/covered.bin"]}],
    )
    assert unmatched == ["docs/orphan.bin"]

    packet = _packet(
        _change("docs/safe.md"),
        git_errors=[
            {"key": "binary_or_mode_path_unmatched", "paths": '["docs/orphan.bin"]'}
        ],
    )
    assert packet["status"] == mod.BLOCKED_STATUS
    assert "binary_or_mode_path_unmatched" in packet["blockers"]


def test_collect_escalates_unmatched_flagged_path_to_blocker(tmp_path, monkeypatch) -> None:
    # e2e 接線回歸（E2 RETURN 2026-07-03）：上面的 seam 測試直呼私函數 + 合成
    # git_errors，釘不住 collect_git_impact_inputs 內「_unmatched_flagged_paths
    # 呼叫 + git_errors append」的真實接線（E2 mutation 刪接線後全 suite 仍綠＝
    # 逃逸）；該接線同時是防「未來有人拔 --no-renames」回退的唯一 backstop。
    # 構造：monkeypatch 上游 numstat 採集，製造三路輸出不一致的 phantom flagged path。
    repo = _make_repo(tmp_path)
    (repo / "docs" / "safe.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "docs/safe.md")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "docs" / "safe.md").write_text("base\ncurrent\n", encoding="utf-8")
    _git(repo, "commit", "-am", "current")
    monkeypatch.setattr(
        mod, "_binary_paths_from_numstat", lambda output: {"docs/phantom.bin"}
    )

    packet = _collect_and_build(repo, base)

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "binary_or_mode_path_unmatched" in packet["blockers"]


def test_collect_git_inputs_and_cli_required_origin_mismatch(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "docs").mkdir()
    (repo / "docs" / "safe.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "docs/safe.md")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "docs" / "safe.md").write_text("base\ncurrent\n", encoding="utf-8")
    _git(repo, "commit", "-am", "current")
    current = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    git_inputs = mod.collect_git_impact_inputs(
        repo,
        base_source_head=base,
        current_source_head="HEAD",
        now_utc=NOW,
    )
    packet = mod.build_standing_envelope_source_impact_guard(
        git_inputs=git_inputs,
        now_utc=NOW,
    )

    assert packet["status"] == mod.READY_STATUS
    assert packet["source_state"]["base_source_head"] == base
    assert packet["source_state"]["current_source_head"] == current
    assert packet["changed_path_classifications"][0]["path"] == "docs/safe.md"

    out = tmp_path / "required_origin_mismatch.json"
    rc = mod.main(
        [
            "--repo-root",
            str(repo),
            "--approved-base-ref",
            base,
            "--required-current-origin-main",
            "0" * 40,
            "--now-utc",
            "2026-07-01T18:20:00Z",
            "--json-output",
            str(out),
        ]
    )
    cli_packet = json.loads(out.read_text(encoding="utf-8"))

    assert rc == 0
    assert cli_packet["status"] == mod.BLOCKED_STATUS
    assert "required_current_origin_main_mismatch" in cli_packet["blockers"]
    assert cli_packet["answers"]["source_impact_ready_for_e3_bb_review"] is False

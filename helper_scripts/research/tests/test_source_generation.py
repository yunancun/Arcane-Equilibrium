"""source_generation 公共庫測試（P1-4 over-gate 統一設計 §4.C）。

覆蓋：
- resolve_expected_source_head：env 鏈優先、pin 檔有效/壞/缺、CLI 覆蓋。
- classify_source_generation 四態矩陣（temp-git 真倉）：
  docs-only 前進→DRIFT_EXEMPT；rust src 前進→DRIFT_ROTATED；
  git 失敗（非法 expected / 不存在 base）→INDETERMINATE fail-close；
  非 ancestor（rollback/改史）→DRIFT_ROTATED；HEAD==expected→MATCH。
- CLI verdict-line：豁免面前進 effective 改傳當前 HEAD；MATCH/fail-close 沿用原 pin；
  pin 檔壞→INDETERMINATE + INVALID_PIN_SENTINEL（不退化成綠）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cost_gate_learning_lane import source_generation as mod


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
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


def _commit_file(repo: Path, rel: str, content: str = "x\n", message: str = "c") -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


# ── resolve_expected_source_head ──────────────────────────────────────────


def test_resolve_cli_value_wins() -> None:
    result = mod.resolve_expected_source_head(
        "abcdef1", env={"OPENCLAW_EXPECTED_SOURCE_HEAD": "9999999"}
    )
    assert result["head"] == "abcdef1"
    assert result["source"] == "cli"
    assert result["error"] is None


def test_resolve_env_chain_priority_over_pin_file(tmp_path: Path) -> None:
    pin_dir = tmp_path / "runtime_generation"
    pin_dir.mkdir(parents=True)
    (pin_dir / "expected_source_head.json").write_text(
        json.dumps({"head": "b" * 40}), encoding="utf-8"
    )
    result = mod.resolve_expected_source_head(
        None, data_dir=tmp_path, env={"OPENCLAW_EXPECTED_SOURCE_HEAD": "a" * 40}
    )
    # env 鏈優先：割接完成前 crontab 現存 inline pin 必須繼續生效。
    assert result["head"] == "a" * 40
    assert result["source"] == "env:OPENCLAW_EXPECTED_SOURCE_HEAD"


def test_resolve_pin_file_when_env_absent(tmp_path: Path) -> None:
    pin_dir = tmp_path / "runtime_generation"
    pin_dir.mkdir(parents=True)
    (pin_dir / "expected_source_head.json").write_text(
        json.dumps({"head": "c" * 40, "derived_at_utc": "2026-07-04T00:00:00Z", "writer": "x"}),
        encoding="utf-8",
    )
    result = mod.resolve_expected_source_head(None, data_dir=tmp_path, env={})
    assert result["head"] == "c" * 40
    assert result["source"] == "pin_file"
    assert result["pin_writer"] == "x"
    assert result["error"] is None


def test_resolve_pin_file_missing_is_none_not_error(tmp_path: Path) -> None:
    result = mod.resolve_expected_source_head(None, data_dir=tmp_path, env={})
    assert result["head"] is None
    assert result["source"] is None
    assert result["error"] is None


def test_resolve_pin_file_broken_json_fails_closed(tmp_path: Path) -> None:
    pin_dir = tmp_path / "runtime_generation"
    pin_dir.mkdir(parents=True)
    (pin_dir / "expected_source_head.json").write_text("{ not json", encoding="utf-8")
    result = mod.resolve_expected_source_head(None, data_dir=tmp_path, env={})
    # pin 檔壞 ≠ 未配置：error 必須非 None，呼叫端 fail-close。
    assert result["head"] is None
    assert result["error"] == "pin_file_json_invalid"


def test_resolve_pin_file_invalid_head_fails_closed(tmp_path: Path) -> None:
    pin_dir = tmp_path / "runtime_generation"
    pin_dir.mkdir(parents=True)
    (pin_dir / "expected_source_head.json").write_text(
        json.dumps({"head": "not-a-sha"}), encoding="utf-8"
    )
    result = mod.resolve_expected_source_head(None, data_dir=tmp_path, env={})
    assert result["head"] is None
    assert result["error"] == "pin_file_head_invalid"


def test_resolve_no_data_dir_returns_none() -> None:
    result = mod.resolve_expected_source_head(None, data_dir=None, env={})
    assert result["head"] is None
    assert result["error"] is None


# ── classify_source_generation 四態矩陣 ──────────────────────────────────


def test_classify_match_when_head_equals_expected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    packet = mod.classify_source_generation(repo, head)
    assert packet["status"] == mod.MATCH_STATUS
    assert packet["blockers"] == []


def test_classify_docs_only_forward_is_exempt(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "docs/new_note.md", "note\n")
    packet = mod.classify_source_generation(repo, base)
    # docs-only 前進不凍結 lane（v710-v738 拒真死循環的 pin 乘數）。
    assert packet["status"] == mod.DRIFT_EXEMPT_STATUS
    assert packet["blockers"] == []


def test_classify_rust_src_forward_is_rotated(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "rust/openclaw_engine/src/foo.rs", "fn x() {}\n")
    packet = mod.classify_source_generation(repo, base)
    # rust src 前進=真代碼世代漂移，lane 必須凍結。
    assert packet["status"] == mod.DRIFT_ROTATED_STATUS
    assert any("rust_src" in b for b in packet["blockers"])


def test_classify_invalid_expected_is_indeterminate(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    packet = mod.classify_source_generation(repo, "not-a-sha")
    assert packet["status"] == mod.INDETERMINATE_STATUS
    assert "expected_source_head_invalid" in packet["blockers"]


def test_classify_empty_expected_is_indeterminate(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    packet = mod.classify_source_generation(repo, "")
    assert packet["status"] == mod.INDETERMINATE_STATUS
    assert "expected_source_head_unresolved" in packet["blockers"]


def test_classify_unknown_base_ref_is_indeterminate(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    # 合法 hex 但 repo 內不存在的 commit：git rev-parse 失敗 → 證據缺失 → fail-close。
    packet = mod.classify_source_generation(repo, "0" * 40)
    assert packet["status"] == mod.INDETERMINATE_STATUS


def test_classify_rollback_non_ancestor_is_rotated(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    forward = _commit_file(repo, "docs/forward.md", "f\n")
    # expected=forward，但 checkout 回退到 base（forward 非 base 的 ancestor）。
    base = _git(repo, "rev-parse", "HEAD~1")
    _git(repo, "checkout", base)
    packet = mod.classify_source_generation(repo, forward)
    assert packet["status"] == mod.DRIFT_ROTATED_STATUS
    assert "expected_head_not_ancestor_of_current_head" in packet["blockers"]


# ── CLI verdict line ─────────────────────────────────────────────────────


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    research_root = Path(mod.__file__).resolve().parents[1]
    return subprocess.run(
        ["python3", "-m", "cost_gate_learning_lane.source_generation", *args],
        cwd=str(research_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_cli_exempt_emits_current_head(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "docs/n.md", "n\n")
    head = _git(repo, "rev-parse", "HEAD")
    proc = _run_cli(["--repo-root", str(repo), "--expected-head", base])
    assert proc.returncode == 0, proc.stderr
    status, _, effective = proc.stdout.splitlines()[0].partition("\t")
    # 豁免面前進：effective 改傳當前 HEAD，讓 lane 既有 exact-compare 綠。
    assert status == mod.DRIFT_EXEMPT_STATUS
    assert head.startswith(effective) or effective == head


def test_cli_rotated_keeps_expected_pin(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    _commit_file(repo, "rust/openclaw_engine/src/foo.rs", "fn y() {}\n")
    proc = _run_cli(["--repo-root", str(repo), "--expected-head", base])
    assert proc.returncode == 0, proc.stderr
    status, _, effective = proc.stdout.splitlines()[0].partition("\t")
    # ROTATED：沿原 pin，下游 exact-compare 對當前 HEAD 必然 MISMATCH → fail-close。
    assert status == mod.DRIFT_ROTATED_STATUS
    assert effective == base


def test_cli_broken_pin_file_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    data_dir = tmp_path / "data"
    pin_dir = data_dir / "runtime_generation"
    pin_dir.mkdir(parents=True)
    (pin_dir / "expected_source_head.json").write_text("{ broken", encoding="utf-8")
    proc = _run_cli(["--repo-root", str(repo), "--data-dir", str(data_dir)])
    assert proc.returncode == 0, proc.stderr
    status, _, effective = proc.stdout.splitlines()[0].partition("\t")
    # 壞 pin 檔的 sentinel 是非 hex，讓下游 exact-compare 必紅（不退化成綠）。
    assert status == mod.INDETERMINATE_STATUS
    assert effective == mod.INVALID_PIN_SENTINEL


def test_cli_pin_not_provided_is_backward_compatible(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    proc = _run_cli(["--repo-root", str(repo)])
    assert proc.returncode == 0, proc.stderr
    status, _, effective = proc.stdout.splitlines()[0].partition("\t")
    # 完全未配置 pin：沿各 lane 既有「expected head 未提供」行為，不新增凍結面。
    assert status == mod.PIN_NOT_PROVIDED_STATUS
    assert effective == ""

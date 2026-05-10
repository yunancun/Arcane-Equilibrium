from __future__ import annotations

from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
).read_text(encoding="utf-8")


def test_ci_workflow_has_required_cross_platform_targets() -> None:
    assert "x86_64-unknown-linux-gnu" in WORKFLOW
    assert "aarch64-apple-darwin" in WORKFLOW
    assert "ubuntu-latest" in WORKFLOW
    assert "macos-latest" in WORKFLOW


def test_ci_workflow_runs_release_cargo_check_for_openclaw_engine() -> None:
    # 2026-05-09 commit 0dc6d659（W-AUDIT-7c GUI round 3 副作用）：CI workflow
    # 由單一 matrix job 拆為 rust-check-linux + rust-check-macos 兩 job
    # （macOS 10x 計費倍率，push 事件僅 Linux），target 改為硬寫字面值
    # 而非 ${{ matrix.target }}。本 assertion 對齊新的雙 job 結構。
    assert "rustup target add x86_64-unknown-linux-gnu" in WORKFLOW
    assert "rustup target add aarch64-apple-darwin" in WORKFLOW
    assert (
        "cargo check --target x86_64-unknown-linux-gnu --release "
        "-p openclaw_engine --bin openclaw-engine"
    ) in WORKFLOW
    assert (
        "cargo check --target aarch64-apple-darwin --release "
        "-p openclaw_engine --bin openclaw-engine"
    ) in WORKFLOW


def test_ci_workflow_triggers_on_push_and_pull_request() -> None:
    assert "push:" in WORKFLOW
    assert "pull_request:" in WORKFLOW
    assert "branches:" in WORKFLOW
    assert "- main" in WORKFLOW

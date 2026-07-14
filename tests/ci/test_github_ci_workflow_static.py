from __future__ import annotations

from pathlib import Path
import re


WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
).read_text(encoding="utf-8")


def _job(name: str) -> str:
    marker = f"\n  {name}:\n"
    assert marker in WORKFLOW
    body = WORKFLOW.split(marker, 1)[1]
    next_job = re.search(r"\n  [a-z0-9][a-z0-9-]*:\n", body)
    return body if next_job is None else body[: next_job.start()]


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


def test_ci_workflow_cancels_obsolete_heads_and_uses_read_only_permissions() -> None:
    assert "permissions:\n  contents: read" in WORKFLOW
    assert (
        "group: ci-${{ github.workflow }}-"
        "${{ github.event_name }}-"
        "${{ github.event.pull_request.number || github.ref }}"
    ) in WORKFLOW
    assert "cancel-in-progress: true" in WORKFLOW


def test_ci_workflow_classifies_paths_before_expensive_jobs() -> None:
    classifier = _job("changes")
    assert "timeout-minutes: 2" in classifier
    assert "git diff --name-only -z" in classifier
    assert "helper_scripts/ci/classify_ci_changes.py" in classifier

    expected_gate = {
        "development-agent-governance": "governance",
        "alr-fit-verifier": "alr_fit_verifier",
        "rust-check-linux": "rust",
        "rust-check-macos": "rust",
        "schema-contract": "schema",
        "stock-etf-static-guards": "stock_etf",
    }
    for job_name, output_name in expected_gate.items():
        job = _job(job_name)
        assert "needs: changes" in job
        assert f"needs.changes.outputs.{output_name} == 'true'" in job


def test_ci_workflow_keeps_cheap_guards_unconditional() -> None:
    for job_name in ("migration-immutability-guard", "stable-id-duplication-guard"):
        job = _job(job_name)
        assert "needs: changes" not in job

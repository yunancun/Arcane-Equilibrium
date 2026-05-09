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
    assert 'rustup target add "${{ matrix.target }}"' in WORKFLOW
    assert (
        'cargo check --target "${{ matrix.target }}" --release '
        "-p openclaw_engine --bin openclaw-engine"
    ) in WORKFLOW


def test_ci_workflow_triggers_on_push_and_pull_request() -> None:
    assert "push:" in WORKFLOW
    assert "pull_request:" in WORKFLOW
    assert "branches:" in WORKFLOW
    assert "- main" in WORKFLOW

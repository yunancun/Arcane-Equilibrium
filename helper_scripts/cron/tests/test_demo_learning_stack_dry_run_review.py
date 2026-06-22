from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[2]
RESEARCH_DIR = HELPER_DIR / "research"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

from cost_gate_learning_lane.status import REQUIRED_SOURCE_RELATIVE_PATHS

REVIEW = Path(__file__).resolve().parents[1] / "demo_learning_stack_dry_run_review.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _git_output(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _init_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    for rel in REQUIRED_SOURCE_RELATIVE_PATHS:
        path = repo / rel
        if path.suffix == ".sh":
            _write(path, "#!/usr/bin/env bash\nexit 0\n")
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        else:
            _write(path, '"""fixture source file."""\n')
    installer = repo / "helper_scripts" / "cron" / "install_demo_learning_stack_crons.sh"
    _write(
        installer,
        """#!/usr/bin/env bash
set -euo pipefail
echo "apply=${OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY:-}"
echo "expected=${OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD:-}"
echo "preinstall=${OPENCLAW_DEMO_LEARNING_STACK_PREINSTALL_REFRESH:-}"
echo "fake installer stderr" >&2
exit "${FAKE_DRY_RUN_RC:-0}"
""",
    )
    installer.chmod(installer.stat().st_mode | stat.S_IXUSR)
    _write(repo / "README.md", "fixture\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo, _git_output(repo, "rev-parse", "HEAD")


def _run_review(
    *,
    repo: Path,
    data_dir: Path,
    env: dict[str, str] | None = None,
) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(REVIEW),
            "--repo-root",
            str(repo),
            "--data-dir",
            str(data_dir),
            "--python-bin",
            sys.executable,
            "--timeout-seconds",
            "10",
            "--now-utc",
            "2026-06-22T00:00:00Z",
        ],
        capture_output=True,
        check=True,
        env={**os.environ, **(env or {})},
        text=True,
    )
    return json.loads(proc.stdout)


def test_dry_run_review_passes_without_apply_gate(tmp_path: Path) -> None:
    repo, head = _init_repo(tmp_path)

    payload = _run_review(repo=repo, data_dir=tmp_path / "data")

    assert payload["schema_version"] == "demo_learning_stack_dry_run_review_v1"
    assert payload["status"] == "DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED"
    assert payload["expected_head"] == head
    assert payload["answers"]["dry_run_preview_executed"] is True
    assert payload["answers"]["dry_run_preview_passed"] is True
    assert payload["answers"]["crontab_mutated"] is False
    assert payload["answers"]["operator_apply_required"] is True
    assert payload["answers"]["global_cost_gate_lowering_recommended"] is False
    assert payload["answers"]["order_authority_granted"] is False
    assert payload["answers"]["probe_authority_granted"] is False
    assert payload["dry_run_preview"]["returncode"] == 0
    assert payload["dry_run_preview"]["mutates_crontab"] is False
    assert payload["dry_run_preview"]["forced_apply_gate"] == "0"
    assert "apply=0" in payload["dry_run_preview"]["stdout_tail"]
    assert f"expected={head}" in payload["dry_run_preview"]["stdout_tail"]
    assert "preinstall=0" in payload["dry_run_preview"]["stdout_tail"]
    assert "OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1" in payload[
        "operator_only_apply_shell"
    ]


def test_dry_run_review_skips_when_activation_source_not_ready(tmp_path: Path) -> None:
    repo, _head = _init_repo(tmp_path)
    _write(repo / "dirty.txt", "dirty\n")

    payload = _run_review(repo=repo, data_dir=tmp_path / "data")

    assert payload["status"] == "DRY_RUN_SKIPPED_ACTIVATION_SOURCE_NOT_READY"
    assert payload["activation_packet_status"] == "SOURCE_NOT_READY"
    assert payload["answers"]["dry_run_preview_executed"] is False
    assert payload["answers"]["dry_run_preview_passed"] is False
    assert payload["dry_run_preview"]["executed"] is False


def test_dry_run_review_records_failed_preview(tmp_path: Path) -> None:
    repo, _head = _init_repo(tmp_path)

    payload = _run_review(
        repo=repo,
        data_dir=tmp_path / "data",
        env={"FAKE_DRY_RUN_RC": "13"},
    )

    assert payload["status"] == "DRY_RUN_PREVIEW_FAILED_REPAIR_REQUIRED"
    assert payload["answers"]["dry_run_preview_executed"] is True
    assert payload["answers"]["dry_run_preview_passed"] is False
    assert payload["answers"]["operator_apply_required"] is False
    assert payload["dry_run_preview"]["returncode"] == 13
    assert "fake installer stderr" in payload["dry_run_preview"]["stderr_tail"]

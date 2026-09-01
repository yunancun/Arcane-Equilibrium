from __future__ import annotations

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from helper_scripts.ci.classify_ci_changes import GATES  # noqa: E402


WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
).read_text(encoding="utf-8")
HYGIENE_WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "public-repository-hygiene.yml"
)


def _job(name: str) -> str:
    marker = f"\n  {name}:\n"
    assert marker in WORKFLOW
    body = WORKFLOW.split(marker, 1)[1]
    next_job = re.search(r"\n  [a-z0-9][a-z0-9-]*:\n", body)
    return body if next_job is None else body[: next_job.start()]


def _workflow_step(workflow: str, name: str) -> str:
    marker = f"\n      - name: {name}\n"
    assert marker in workflow
    body = workflow.split(marker, 1)[1]
    next_step = re.search(r"\n      - name: ", body)
    return body if next_step is None else body[: next_step.start()]


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
    assert (
        '"${{ github.event.pull_request.base.sha }}...'
        '${{ github.event.pull_request.head.sha }}"'
    ) in classifier
    assert "helper_scripts/ci/classify_ci_changes.py" in classifier

    expected_gate = {
        "development-agent-governance-shard": "governance",
        "alr-fit-verifier": "alr_fit_verifier",
        "rust-check-linux": "rust",
        "rust-check-macos": "rust",
        "schema-contract": "schema",
        "stock-etf-static-guards": "stock_etf",
        "learning-runtime-sealed-build": "sealed_build",
    }
    for job_name, output_name in expected_gate.items():
        job = _job(job_name)
        assert "needs: changes" in job
        assert f"needs.changes.outputs.{output_name} == 'true'" in job

    # Exhaustiveness: every classifier GATE must be BOTH declared as a `changes` output
    # AND consumed by at least one gated job. A dropped job / removed `if:` gate / removed
    # `changes` output reddens here (guards against silently orphaning an expensive gate).
    classifier_gate = _job("changes")
    for gate in GATES:
        assert f"{gate}: ${{{{ steps.classify.outputs.{gate} }}}}" in classifier_gate, gate
        assert f"needs.changes.outputs.{gate} == 'true'" in WORKFLOW, gate
    assert set(expected_gate.values()) == set(GATES)


def test_development_agent_governance_suite_is_sharded_without_filtering() -> None:
    governance = _job("development-agent-governance-shard")
    assert "timeout-minutes: 45" in governance
    assert "fail-fast: false" in governance
    assert "shard: [0, 1, 2, 3, 4, 5, 6, 7]" in governance
    assert "name: development-agent governance shard ${{ matrix.shard }} of 8" in governance
    assert "-p helper_scripts.ci.select_pytest_shard" in governance
    assert "--governance-shard-index ${{ matrix.shard }}" in governance
    assert "--governance-shard-count 8" in governance
    assert "--governance-shard-minimum 4548" in governance
    assert "--governance-shard-source-sha ${{ github.sha }}" in governance
    assert '"${{ runner.temp }}/governance-pytest-shard-${{ matrix.shard }}.json"' in governance
    assert "uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in governance
    assert "name: governance-pytest-shard-${{ matrix.shard }}" in governance
    assert "if-no-files-found: error" in governance
    assert "retention-days: 1" in governance
    assert "overwrite: false" in governance
    upload = _workflow_step("\n" + governance, "Upload exact governance shard evidence")
    assert "if: always()" in upload
    assert "path: ${{ runner.temp }}/governance-pytest-shard-${{ matrix.shard }}.json" in upload
    assert "tests/structure/test_codex_memory_policy.py" in governance
    assert "tests/structure/test_role_memory_compaction.py" in governance
    for forbidden in (" -k ", "--ignore", "--deselect", "--maxfail", " -x", "xdist"):
        assert forbidden not in governance


def test_development_agent_governance_keeps_legacy_fail_closed_aggregate() -> None:
    aggregate = _job("development-agent-governance")
    assert "name: development-agent governance (cheap static gate)" in aggregate
    assert "needs: [changes, development-agent-governance-shard]" in aggregate
    assert "if: always()" in aggregate
    assert "GOVERNANCE_SELECTED: ${{ needs.changes.outputs.governance }}" in aggregate
    assert "SHARD_RESULT: ${{ needs.development-agent-governance-shard.result }}" in aggregate
    assert '"$GOVERNANCE_SELECTED" == "true" && "$SHARD_RESULT" == "success"' in aggregate
    assert '"$GOVERNANCE_SELECTED" == "false" && "$SHARD_RESULT" == "skipped"' in aggregate
    assert "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5" in aggregate
    assert "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093" in aggregate
    assert "pattern: governance-pytest-shard-*" in aggregate
    assert "merge-multiple: false" in aggregate
    assert "helper_scripts/ci/verify_pytest_shards.py" in aggregate
    assert "--expected-source-sha ${{ github.sha }}" in aggregate
    assert "--expected-shard-count 8" in aggregate
    assert "--expected-minimum-count 4548" in aggregate
    artifact_guard = (
        "if: needs.changes.outputs.governance == 'true' && "
        "needs.development-agent-governance-shard.result == 'success'"
    )
    for step_name in (
        "Check out exact governance source",
        "Download preserved governance shard evidence",
        "Verify exhaustive governance shard evidence",
    ):
        assert artifact_guard in _workflow_step("\n" + aggregate, step_name)
    assert "ref: ${{ github.sha }}" in aggregate
    assert "path: ${{ runner.temp }}/governance-pytest-shards" in aggregate
    for forbidden in ("github-token:", "repository:", "run-id:"):
        assert forbidden not in aggregate
    assert "exit 1" in aggregate


def test_shard_verifier_tests_are_unconditional_and_self_triggering() -> None:
    policy = _job("git-workflow-policy")
    assert "tests/ci/test_verify_pytest_shards.py" in policy


def test_v158_v159_contracts_run_once_on_shard_zero() -> None:
    governance = _job("development-agent-governance-shard")
    contract_step = _workflow_step(
        "\n" + governance, "Run V158/V159 qualified challenger source contracts"
    )
    assert "if: matrix.shard == 0" in contract_step
    assert "tests/migrations/test_v158_alr_qualified_challenger_training.py" in contract_step
    assert "tests/migrations/test_v159_alr_durable_fit_attestation.py" in contract_step


def test_ci_workflow_keeps_cheap_guards_unconditional() -> None:
    for job_name in ("migration-immutability-guard", "stable-id-duplication-guard"):
        job = _job(job_name)
        assert "needs: changes" not in job


def test_public_repository_hygiene_check_is_defined_by_base_trusted_workflow() -> None:
    assert "\n  public-repository-hygiene:\n" not in WORKFLOW
    assert HYGIENE_WORKFLOW.is_file()

    hygiene = HYGIENE_WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request_target:" in hygiene
    assert "pull_request:\n" not in hygiene


def test_privileged_hygiene_workflow_never_uses_checkout_or_other_actions() -> None:
    hygiene = HYGIENE_WORKFLOW.read_text(encoding="utf-8")

    assert "actions/checkout@" not in hygiene
    assert "uses:" not in hygiene
    for forbidden in (
        "uses: ./",
        "working-directory: .untrusted-public-repo-head",
        "git lfs",
        "submodule update",
        "pip install",
        "npm install",
        "source ",
        "eval ",
    ):
        assert forbidden not in hygiene


def test_public_repository_hygiene_anonymously_fetches_exact_base_and_head() -> None:
    hygiene = HYGIENE_WORKFLOW.read_text(encoding="utf-8")
    fetch = _workflow_step(hygiene, "Fetch exact PR trees without actions")

    assert hygiene.startswith("name: public repository hygiene\n")
    assert "types: [opened, synchronize, reopened, ready_for_review]" in hygiene
    assert "permissions:\n  contents: read" in hygiene
    assert "if: github.event_name == 'pull_request_target'" in fetch
    assert "BASE_SHA: ${{ github.event.pull_request.base.sha }}" in fetch
    assert "HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in fetch
    assert "BASE_REPOSITORY_FULL_NAME: ${{ github.repository }}" in fetch
    assert (
        "HEAD_REPOSITORY_FULL_NAME: "
        "${{ github.event.pull_request.head.repo.full_name }}"
    ) in fetch
    assert "TRUSTED_REPOSITORY_URL: ${{ github.server_url }}/${{ github.repository }}.git" in fetch
    assert (
        "UNTRUSTED_REPOSITORY_URL: ${{ github.server_url }}/"
        "${{ github.event.pull_request.head.repo.full_name }}.git"
    ) in fetch
    assert 'safe_git init --quiet --template="$EMPTY_GIT_TEMPLATE" "$TRUSTED_BASE_ROOT"' in fetch
    assert '"$TRUSTED_REPOSITORY_URL" "$BASE_SHA"' in fetch
    assert 'checkout --quiet --detach "$BASE_SHA"' in fetch
    assert 'safe_git init --quiet --template="$EMPTY_GIT_TEMPLATE" "$UNTRUSTED_HEAD_ROOT"' in fetch
    assert '"$UNTRUSTED_REPOSITORY_URL" "$HEAD_SHA"' in fetch
    assert 'checkout --quiet --detach "$HEAD_SHA"' in fetch
    assert 'rev-parse --verify HEAD)" = "$BASE_SHA"' in fetch
    assert 'rev-parse --verify HEAD)" = "$HEAD_SHA"' in fetch
    assert "GIT_CONFIG_NOSYSTEM: '1'" in fetch
    assert "GIT_CONFIG_GLOBAL: /dev/null" in fetch
    assert "GIT_ASKPASS: /bin/false" in fetch
    assert "SSH_ASKPASS: /bin/false" in fetch
    assert "unset GITHUB_TOKEN GH_TOKEN SSH_AUTH_SOCK" in fetch
    for hardening in (
        "core.hooksPath=/dev/null",
        "credential.helper=",
        "http.extraHeader=",
        "submodule.recurse=false",
        "filter.lfs.required=false",
        "filter.lfs.smudge=",
        "filter.lfs.process=",
        "protocol.file.allow=never",
        "protocol.ext.allow=never",
        "protocol.git.allow=never",
        "protocol.ssh.allow=never",
        "fetch.fsckObjects=true",
    ):
        assert hardening in fetch


def test_public_repository_hygiene_pr_scan_uses_only_trusted_policy_for_exact_range() -> None:
    hygiene = HYGIENE_WORKFLOW.read_text(encoding="utf-8")
    scan = _workflow_step(hygiene, "Scan exact PR head with trusted base policy")

    assert "if: github.event_name == 'pull_request_target'" in scan
    assert "BASE_SHA: ${{ github.event.pull_request.base.sha }}" in scan
    assert "HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in scan
    assert "TRUSTED_BASE_ROOT: ${{ github.workspace }}/.trusted-public-repo-security-base" in scan
    assert "UNTRUSTED_HEAD_ROOT: ${{ github.workspace }}/.untrusted-public-repo-head" in scan
    assert 'git -C "$UNTRUSTED_HEAD_ROOT" cat-file -e "${BASE_SHA}^{commit}"' in scan
    assert (
        'python3 "$TRUSTED_BASE_ROOT/helper_scripts/maintenance_scripts/'
        'public_repo_security_gate.py"'
    ) in scan
    assert '--repo-root "$UNTRUSTED_HEAD_ROOT"' in scan
    assert (
        '--allowlist-file "$TRUSTED_BASE_ROOT/.github/'
        'public-repo-security-allowlist.json"'
    ) in scan
    assert '--tree "$HEAD_SHA"' in scan
    assert '--range "$BASE_SHA..$HEAD_SHA"' in scan
    assert "$UNTRUSTED_HEAD_ROOT/helper_scripts" not in scan


def test_public_repository_hygiene_push_and_schedule_scan_current_tree() -> None:
    hygiene = HYGIENE_WORKFLOW.read_text(encoding="utf-8")
    fetch = _workflow_step(hygiene, "Fetch exact current tree without actions")
    scan = _workflow_step(hygiene, "Scan current tree for push or schedule")

    assert "push:\n    branches:\n      - main" in hygiene
    assert "schedule:\n    - cron: '0 3 * * 1'" in hygiene
    assert "if: github.event_name != 'pull_request_target'" in fetch
    assert "CURRENT_SHA: ${{ github.sha }}" in fetch
    assert "TRUSTED_REPOSITORY_URL: ${{ github.server_url }}/${{ github.repository }}.git" in fetch
    assert 'safe_git init --quiet --template="$EMPTY_GIT_TEMPLATE" "$CURRENT_ROOT"' in fetch
    assert '"$TRUSTED_REPOSITORY_URL" "$CURRENT_SHA"' in fetch
    assert 'checkout --quiet --detach "$CURRENT_SHA"' in fetch
    assert 'rev-parse --verify HEAD)" = "$CURRENT_SHA"' in fetch
    assert "unset GITHUB_TOKEN GH_TOKEN SSH_AUTH_SOCK" in fetch
    assert "core.hooksPath=/dev/null" in fetch
    assert "credential.helper=" in fetch
    assert "submodule.recurse=false" in fetch
    assert "filter.lfs.process=" in fetch
    assert "if: github.event_name != 'pull_request_target'" in scan
    assert (
        'python3 "$CURRENT_ROOT/helper_scripts/maintenance_scripts/'
        'public_repo_security_gate.py"'
    ) in scan
    assert '--repo-root "$CURRENT_ROOT"' in scan
    assert '--allowlist-file "$CURRENT_ROOT/.github/public-repo-security-allowlist.json"' in scan
    assert '--tree "$CURRENT_SHA"' in scan
    assert 'scan_args+=(--range "$BEFORE_SHA..$CURRENT_SHA")' in scan


def test_ci_workflow_runs_git_policy_tests_in_unconditional_cheap_gate() -> None:
    policy = _job("git-workflow-policy")
    assert "needs: changes" not in policy
    assert "needs.changes.outputs" not in policy
    assert "ubuntu-latest" in policy
    for path in (
        "tests/structure/test_git_loop_guard.py",
        "tests/structure/test_public_repo_security_gate.py",
        "tests/structure/test_public_repo_security_policy.py",
        "tests/ci/test_classify_ci_changes.py",
        "tests/ci/test_github_ci_workflow_static.py",
        "tests/ci/test_select_pytest_shard.py",
    ):
        assert path in policy

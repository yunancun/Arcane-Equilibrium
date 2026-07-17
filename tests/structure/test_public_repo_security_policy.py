from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _workflow_step(workflow: str, name: str) -> str:
    marker = f"\n      - name: {name}\n"
    assert marker in workflow
    body = workflow.split(marker, 1)[1]
    return body.split("\n      - name: ", 1)[0]


def test_public_security_policy_uses_private_github_reporting() -> None:
    policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    assert "security/advisories/new" in policy
    assert "Do not open a public issue" in policy
    assert "0700" in policy
    assert "0600" in policy


def test_codeowners_marks_the_real_owner_without_inventing_a_reviewer() -> None:
    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

    assert "* @yunancun" in codeowners
    assert codeowners.count("@") == 1
    assert "must not require this review until" in codeowners


def test_history_hardening_record_names_both_removed_database_paths() -> None:
    record = (
        ROOT / "docs" / "security" / "2026-07-17--public_repository_hardening.md"
    ).read_text(encoding="utf-8")

    assert "backups/trading_ai_pre_phase0a_20260404_180411.dump" in record
    assert "`.coverage`" in record
    assert "--force-with-lease=<ref>:<old-sha>" in record
    assert "`--all` and `--mirror` are forbidden" in record
    assert "external_cleanup_pending" in record


def test_temporary_security_allowlist_is_bound_to_history_rewrite_removal() -> None:
    record = (
        ROOT / "docs" / "security" / "2026-07-17--public_repository_hardening.md"
    ).read_text(encoding="utf-8")

    assert "`.github/public-repo-security-allowlist.json`" in record
    assert "temporary pre-rewrite bridge" in record
    assert "MUST be removed in the same change as the history rewrite" in record


def test_pull_request_target_hygiene_has_no_untrusted_execution_or_authority_escalation() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "public-repository-hygiene.yml"
    ).read_text(encoding="utf-8")
    pr_fetch = _workflow_step(workflow, "Fetch exact PR trees without actions")
    pr_scan = _workflow_step(workflow, "Scan exact PR head with trusted base policy")
    current_fetch = _workflow_step(workflow, "Fetch exact current tree without actions")
    current_scan = _workflow_step(workflow, "Scan current tree for push or schedule")

    assert workflow.count("permissions:") == 1
    assert "permissions:\n  contents: read" in workflow
    assert ": write" not in workflow
    assert "secrets." not in workflow
    assert "github.token" not in workflow
    assert "Authorization:" not in workflow
    assert "persist-credentials: true" not in workflow
    assert "github.actor" not in workflow
    assert "github.event.pull_request.title" not in workflow
    assert "github.event.pull_request.body" not in workflow
    assert "github.event.pull_request.head.ref" not in workflow
    assert "github.event.pull_request.base.ref" not in workflow
    assert workflow.count("github.event.pull_request.head.repo.full_name") == 2
    assert "a2b873825e2fe25037ce305b23122de47235b37e" not in workflow
    assert "Bootstrap" not in workflow
    assert "working-directory: .untrusted-public-repo-head" not in workflow
    uses = [line.strip() for line in workflow.splitlines() if "uses:" in line]
    assert uses == []
    assert "actions/checkout@" not in workflow
    for forbidden in (
        "uses: ./",
        "pip install",
        "npm install",
        "source ",
        "eval ",
        "curl ",
        "wget ",
        'python3 "$UNTRUSTED_HEAD_ROOT/',
        'bash "$UNTRUSTED_HEAD_ROOT/',
        'sh "$UNTRUSTED_HEAD_ROOT/',
        '--allowlist-file "$UNTRUSTED_HEAD_ROOT/',
    ):
        assert forbidden not in workflow

    assert "if: github.event_name == 'pull_request_target'" in pr_fetch
    assert "BASE_SHA: ${{ github.event.pull_request.base.sha }}" in pr_fetch
    assert "HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in pr_fetch
    assert "BASE_REPOSITORY_FULL_NAME: ${{ github.repository }}" in pr_fetch
    assert (
        "HEAD_REPOSITORY_FULL_NAME: "
        "${{ github.event.pull_request.head.repo.full_name }}"
    ) in pr_fetch
    assert (
        "TRUSTED_REPOSITORY_URL: "
        "${{ github.server_url }}/${{ github.repository }}.git"
    ) in pr_fetch
    assert (
        "UNTRUSTED_REPOSITORY_URL: ${{ github.server_url }}/"
        "${{ github.event.pull_request.head.repo.full_name }}.git"
    ) in pr_fetch
    assert '"$BASE_REPOSITORY_FULL_NAME" =~ ^[A-Za-z0-9_.-]+/' in pr_fetch
    assert '"$HEAD_REPOSITORY_FULL_NAME" =~ ^[A-Za-z0-9_.-]+/' in pr_fetch
    assert (
        'test "$TRUSTED_REPOSITORY_URL" = '
        '"${GITHUB_SERVER_URL%/}/${BASE_REPOSITORY_FULL_NAME}.git"'
    ) in pr_fetch
    assert (
        'test "$UNTRUSTED_REPOSITORY_URL" = '
        '"${GITHUB_SERVER_URL%/}/${HEAD_REPOSITORY_FULL_NAME}.git"'
    ) in pr_fetch

    for fetch_step in (pr_fetch, current_fetch):
        assert "GIT_CONFIG_NOSYSTEM: '1'" in fetch_step
        assert "GIT_CONFIG_GLOBAL: /dev/null" in fetch_step
        assert "GIT_TERMINAL_PROMPT: '0'" in fetch_step
        assert "GIT_ASKPASS: /bin/false" in fetch_step
        assert "SSH_ASKPASS: /bin/false" in fetch_step
        assert "unset GITHUB_TOKEN GH_TOKEN SSH_AUTH_SOCK" in fetch_step
        assert (
            "env -u GITHUB_TOKEN -u GH_TOKEN -u SSH_AUTH_SOCK git \\"
            in fetch_step
        )
        assert 'test ! -e "$EMPTY_GIT_TEMPLATE"' in fetch_step
        assert 'mkdir -m 0700 "$EMPTY_GIT_TEMPLATE"' in fetch_step
        assert '--template="$EMPTY_GIT_TEMPLATE"' in fetch_step
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
            assert hardening in fetch_step

    assert (
        'safe_git init --quiet --template="$EMPTY_GIT_TEMPLATE" '
        '"$TRUSTED_BASE_ROOT"'
    ) in pr_fetch
    assert '"$TRUSTED_REPOSITORY_URL" "$BASE_SHA"' in pr_fetch
    assert 'checkout --quiet --detach "$BASE_SHA"' in pr_fetch
    assert 'rev-parse --verify HEAD)" = "$BASE_SHA"' in pr_fetch
    assert (
        'safe_git init --quiet --template="$EMPTY_GIT_TEMPLATE" '
        '"$UNTRUSTED_HEAD_ROOT"'
    ) in pr_fetch
    assert '"$UNTRUSTED_REPOSITORY_URL" "$HEAD_SHA"' in pr_fetch
    assert 'checkout --quiet --detach "$HEAD_SHA"' in pr_fetch
    assert 'rev-parse --verify HEAD)" = "$HEAD_SHA"' in pr_fetch
    assert 'cat-file -e "${BASE_SHA}^{commit}"' in pr_fetch

    assert "if: github.event_name == 'pull_request_target'" in pr_scan
    assert 'git -C "$TRUSTED_BASE_ROOT" rev-parse HEAD)" = "$BASE_SHA"' in pr_scan
    assert 'git -C "$UNTRUSTED_HEAD_ROOT" rev-parse HEAD)" = "$HEAD_SHA"' in pr_scan
    assert (
        'python3 "$TRUSTED_BASE_ROOT/helper_scripts/maintenance_scripts/'
        'public_repo_security_gate.py"'
    ) in pr_scan
    assert '--repo-root "$UNTRUSTED_HEAD_ROOT"' in pr_scan
    assert (
        '--allowlist-file "$TRUSTED_BASE_ROOT/.github/'
        'public-repo-security-allowlist.json"'
    ) in pr_scan
    assert '--tree "$HEAD_SHA"' in pr_scan
    assert '--range "$BASE_SHA..$HEAD_SHA"' in pr_scan

    assert "push:\n    branches:\n      - main" in workflow
    assert "schedule:\n    - cron: '0 3 * * 1'" in workflow
    assert "if: github.event_name != 'pull_request_target'" in current_fetch
    assert "CURRENT_SHA: ${{ github.sha }}" in current_fetch
    assert "BEFORE_SHA: ${{ github.event.before }}" in current_fetch
    assert "BASE_REPOSITORY_FULL_NAME: ${{ github.repository }}" in current_fetch
    assert (
        'test "$TRUSTED_REPOSITORY_URL" = '
        '"${GITHUB_SERVER_URL%/}/${BASE_REPOSITORY_FULL_NAME}.git"'
    ) in current_fetch
    assert '"$TRUSTED_REPOSITORY_URL" "$CURRENT_SHA"' in current_fetch
    assert 'checkout --quiet --detach "$CURRENT_SHA"' in current_fetch
    assert 'rev-parse --verify HEAD)" = "$CURRENT_SHA"' in current_fetch
    assert '"$EVENT_NAME" == "push"' in current_fetch
    assert '"$TRUSTED_REPOSITORY_URL" "$BEFORE_SHA"' in current_fetch

    assert "if: github.event_name != 'pull_request_target'" in current_scan
    assert 'git -C "$CURRENT_ROOT" rev-parse HEAD)" = "$CURRENT_SHA"' in current_scan
    assert (
        'python3 "$CURRENT_ROOT/helper_scripts/maintenance_scripts/'
        'public_repo_security_gate.py"'
    ) in current_scan
    assert '--repo-root "$CURRENT_ROOT"' in current_scan
    assert '--tree "$CURRENT_SHA"' in current_scan
    assert 'scan_args+=(--range "$BEFORE_SHA..$CURRENT_SHA")' in current_scan

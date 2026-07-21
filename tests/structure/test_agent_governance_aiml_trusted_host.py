from __future__ import annotations

import copy
import inspect
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_aiml_trusted_host as host  # noqa: E402
import agent_governance as governance  # noqa: E402
import agent_governance_closure as closure  # noqa: E402


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
NOW = datetime(2026, 7, 21, 20, 0, tzinfo=timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _entry(kind: str, subject: str, artifact: dict) -> dict:
    return {
        "kind": kind,
        "subject_digest": subject,
        "artifact_digest": host.canonical_digest(artifact),
        "observed_at": _timestamp(NOW - timedelta(minutes=1)),
        "expires_at": _timestamp(NOW + timedelta(minutes=5)),
    }


def _bundle(entries: list[dict]) -> dict:
    return {
        "schema_version": "trusted_execution_bundle_v1",
        "signer_identity": host.EXPECTED_EXECUTION_SIGNER_IDENTITY,
        "signer_fingerprint": host.EXPECTED_EXECUTION_SIGNER_FINGERPRINT,
        "algorithm": host.EXECUTION_BUNDLE_ALGORITHM,
        "signature_namespace": host.EXECUTION_SIGNATURE_NAMESPACE,
        "task_contract_digest": DIGEST_A,
        "context_artifact_digest": DIGEST_B,
        "dag_digest": DIGEST_C,
        "issued_at": _timestamp(NOW - timedelta(minutes=1)),
        "expires_at": _timestamp(NOW + timedelta(minutes=5)),
        "entries": entries,
    }


def _generate_signer(root: Path, name: str) -> tuple[Path, str]:
    private_key = root / name
    subprocess.run(
        [
            host.SSH_KEYGEN_EXECUTABLE,
            "-q", "-t", "ed25519", "-N", "", "-C", name,
            "-f", str(private_key),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    public_key = " ".join(
        private_key.with_suffix(".pub").read_text(encoding="ascii").split()[:2]
    )
    return private_key, public_key


def _sign_bundle(bundle: dict, private_key: Path, root: Path) -> bytes:
    payload_path = root / (host.canonical_digest(bundle).split(":", 1)[1] + ".json")
    payload_path.write_bytes(host._canonical_bytes(bundle))
    signature_path = Path(str(payload_path) + ".sig")
    subprocess.run(
        [
            host.SSH_KEYGEN_EXECUTABLE,
            "-Y", "sign",
            "-f", str(private_key),
            "-n", host.EXECUTION_SIGNATURE_NAMESPACE,
            str(payload_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return signature_path.read_bytes()


@pytest.fixture
def trusted_signer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    private_key, public_key = _generate_signer(tmp_path, "trusted_signer")
    monkeypatch.setattr(host, "TRUSTED_EXECUTION_PUBLIC_KEY", public_key)
    monkeypatch.setattr(
        host,
        "EXPECTED_EXECUTION_SIGNER_FINGERPRINT",
        host.ssh_public_key_fingerprint(public_key),
    )
    return private_key, tmp_path


def _index(
    bundle: dict,
    signature: bytes,
) -> host.AuthenticatedExecutionEvidenceIndex:
    return host.AuthenticatedExecutionEvidenceIndex.from_bundle(
        bundle,
        signature=signature,
        now=NOW,
        task_contract_digest=DIGEST_A,
        context_artifact_digest=DIGEST_B,
        dag_digest=DIGEST_C,
    )


def test_execution_bundle_authenticates_exact_artifact_and_consumption(
    trusted_signer: tuple[Path, Path],
) -> None:
    private_key, root = trusted_signer
    artifact = {"schema_version": "context_artifact_v1", "value": 1}
    bundle = _bundle([_entry("context_artifact_v1", DIGEST_B, artifact)])
    index = _index(bundle, _sign_bundle(bundle, private_key, root))

    assert index.verify("context_artifact_v1", DIGEST_B, artifact) is True
    assert index.exact_consumption_errors() == []
    assert index.verify(
        "context_artifact_v1", DIGEST_B, {**artifact, "value": 2}
    ) is False


def test_source_pinned_public_key_matches_declared_fingerprint() -> None:
    assert (
        host.ssh_public_key_fingerprint(host.TRUSTED_EXECUTION_PUBLIC_KEY)
        == host.EXPECTED_EXECUTION_SIGNER_FINGERPRINT
    )


@pytest.mark.parametrize("mutation", ["signature", "task", "stale", "future"])
def test_execution_bundle_rejects_forged_or_wrong_generation(
    mutation: str,
    trusted_signer: tuple[Path, Path],
) -> None:
    private_key, root = trusted_signer
    artifact = {"schema_version": "context_artifact_v1"}
    bundle = _bundle([_entry("context_artifact_v1", DIGEST_B, artifact)])
    if mutation == "signature":
        signature = b"not-an-ssh-signature"
    elif mutation == "task":
        bundle["task_contract_digest"] = DIGEST_C
        signature = _sign_bundle(bundle, private_key, root)
    elif mutation == "stale":
        bundle["issued_at"] = _timestamp(NOW - timedelta(minutes=6))
        bundle["expires_at"] = _timestamp(NOW + timedelta(minutes=1))
        signature = _sign_bundle(bundle, private_key, root)
    else:
        bundle["issued_at"] = _timestamp(NOW + timedelta(minutes=2))
        bundle["expires_at"] = _timestamp(NOW + timedelta(minutes=10))
        signature = _sign_bundle(bundle, private_key, root)

    with pytest.raises(ValueError):
        _index(bundle, signature)


def test_execution_bundle_rejects_duplicate_and_reports_extra_entries(
    trusted_signer: tuple[Path, Path],
) -> None:
    private_key, root = trusted_signer
    first = {"schema_version": "context_artifact_v1"}
    duplicate = _entry("context_artifact_v1", DIGEST_B, first)
    duplicate_bundle = _bundle([duplicate, duplicate])
    with pytest.raises(ValueError, match="duplicate"):
        _index(
            duplicate_bundle,
            _sign_bundle(duplicate_bundle, private_key, root),
        )

    second = {"schema_version": "workflow_wave_record_v1"}
    bundle = _bundle([
        _entry("context_artifact_v1", DIGEST_B, first),
        _entry("workflow_wave_record_v1", DIGEST_C, second),
    ])
    index = _index(bundle, _sign_bundle(bundle, private_key, root))
    assert index.verify("context_artifact_v1", DIGEST_B, first)
    assert index.exact_consumption_errors() == [
        "trusted execution bundle contains unconsumed entries"
    ]


def test_caller_selected_key_cannot_forge_execution_bundle(
    trusted_signer: tuple[Path, Path],
) -> None:
    _trusted_private, root = trusted_signer
    rogue_private, _rogue_public = _generate_signer(root, "rogue_signer")
    artifact = {"schema_version": "context_artifact_v1"}
    bundle = _bundle([_entry("context_artifact_v1", DIGEST_B, artifact)])

    with pytest.raises(ValueError, match="authentication failed"):
        _index(bundle, _sign_bundle(bundle, rogue_private, root))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def _repo_with_file(tmp_path: Path) -> tuple[Path, str, str]:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    target = tmp_path / "bound.txt"
    target.write_bytes(b"first\n")
    _git(tmp_path, "add", "bound.txt")
    _git(tmp_path, "commit", "-qm", "first")
    reviewed = _git(tmp_path, "rev-parse", "HEAD")
    target.write_bytes(b"second\n")
    _git(tmp_path, "add", "bound.txt")
    _git(tmp_path, "commit", "-qm", "second")
    merged = _git(tmp_path, "rev-parse", "HEAD")
    return tmp_path, reviewed, merged


def test_source_verifier_proves_ancestry_and_exact_merge_blob(tmp_path: Path) -> None:
    repo, reviewed, merged = _repo_with_file(tmp_path)
    verifier = host.GitSourceManifestVerifier(repo)
    digest = "sha256:" + __import__("hashlib").sha256(b"second\n").hexdigest()

    assert verifier(reviewed, merged, {"bound.txt": digest}) is True
    assert verifier(merged, reviewed, {"bound.txt": digest}) is False
    assert verifier(reviewed, merged, {"bound.txt": DIGEST_A}) is False
    assert verifier(reviewed, merged, {"../bound.txt": digest}) is False
    assert verifier(reviewed, merged, {":(glob)bound.txt": digest}) is False


def test_source_verifier_rejects_oversized_blob_before_materializing_it(
    tmp_path: Path,
) -> None:
    object_id = "d" * 40
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        if argv == ["rev-parse", "--show-toplevel"]:
            stdout, returncode = (str(tmp_path) + "\n").encode(), 0
        elif argv == ["rev-parse", "--is-shallow-repository"]:
            stdout, returncode = b"false\n", 0
        elif argv == ["replace", "-l"]:
            stdout, returncode = b"", 0
        elif argv[:2] == ["config", "--get-regexp"]:
            stdout, returncode = b"", 1
        elif argv[:2] == ["rev-parse", "--git-path"]:
            stdout, returncode = (str(tmp_path / argv[-1]) + "\n").encode(), 0
        elif argv[:2] == ["cat-file", "-e"]:
            stdout, returncode = b"", 0
        elif argv[:2] == ["merge-base", "--is-ancestor"]:
            stdout, returncode = b"", 0
        elif argv[:2] == ["ls-tree", "-z"]:
            stdout = f"100644 blob {object_id}\tbound.txt\0".encode()
            returncode = 0
        elif argv == ["cat-file", "-s", object_id]:
            stdout, returncode = f"{host.MAX_BLOB_BYTES + 1}\n".encode(), 0
        elif argv == ["cat-file", "blob", object_id]:
            pytest.fail("oversized blob was materialized")
        else:
            raise AssertionError(f"unexpected Git command: {argv}")
        return subprocess.CompletedProcess(argv, returncode, stdout, b"")

    verifier = host.GitSourceManifestVerifier(tmp_path, runner=runner)
    assert verifier("a" * 40, "b" * 40, {"bound.txt": DIGEST_A}) is False
    assert ["cat-file", "blob", object_id] not in calls


def test_source_verifier_rejects_symlink_and_alternate_object_store(
    tmp_path: Path,
) -> None:
    repo, reviewed, _merged = _repo_with_file(tmp_path)
    (repo / "link").symlink_to("bound.txt")
    _git(repo, "add", "link")
    _git(repo, "commit", "-qm", "link")
    merged = _git(repo, "rev-parse", "HEAD")
    link_digest = "sha256:" + __import__("hashlib").sha256(b"bound.txt").hexdigest()
    verifier = host.GitSourceManifestVerifier(repo)
    assert verifier(reviewed, merged, {"link": link_digest}) is False

    alternates = Path(_git(repo, "rev-parse", "--git-path", "objects/info/alternates"))
    if not alternates.is_absolute():
        alternates = repo / alternates
    alternates.parent.mkdir(parents=True, exist_ok=True)
    alternates.write_text("/tmp/not-trusted\n", encoding="utf-8")
    regular_digest = "sha256:" + __import__("hashlib").sha256(b"second\n").hexdigest()
    assert verifier(reviewed, merged, {"bound.txt": regular_digest}) is False


class FakeGitHubTransport:
    def __init__(self, payloads: dict[str, object]):
        self.payloads = payloads
        self.calls: list[str] = []

    def get_json(self, path: str, token: bytes) -> object:
        assert token == b"token-value"
        self.calls.append(path)
        return copy.deepcopy(self.payloads[path])


def _github_rules() -> list[dict[str, object]]:
    return [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": copy.deepcopy(host.EXPECTED_PULL_REQUEST_PARAMETERS),
        },
        {
            "type": "required_status_checks",
            "parameters": copy.deepcopy(
                host.EXPECTED_REQUIRED_STATUS_CHECK_PARAMETERS
            ),
        },
    ]


def _github_payloads(
    reviewed_head: str = "c" * 40,
    merge_head: str = "d" * 40,
) -> dict[str, object]:
    paths = host._github_static_paths()
    inventory_path = host._github_inventory_path(1)
    effective_path = host._github_effective_rules_path(1)
    rules = _github_rules()
    pull_number = 106
    merged_at = _timestamp(NOW - timedelta(minutes=2))
    check_started_at = _timestamp(NOW - timedelta(minutes=4))
    check_completed_at = _timestamp(NOW - timedelta(minutes=3))
    effective_rules = []
    for rule in rules:
        item = {
            "type": rule["type"],
            "ruleset_id": host.EXPECTED_RULESET_ID,
            "ruleset_source_type": "Repository",
            "ruleset_source": host.EXPECTED_REPOSITORY_FULL_NAME,
        }
        if "parameters" in rule:
            item["parameters"] = copy.deepcopy(rule["parameters"])
        effective_rules.append(item)
    return {
        paths["repository"]: {
            "id": host.EXPECTED_REPOSITORY_ID,
            "full_name": host.EXPECTED_REPOSITORY_FULL_NAME,
            "default_branch": host.EXPECTED_DEFAULT_BRANCH,
            "archived": False,
            "disabled": False,
        },
        inventory_path: [{
            "id": host.EXPECTED_RULESET_ID,
            "name": host.EXPECTED_RULESET_NAME,
            "target": "branch",
            "source_type": "Repository",
            "source": host.EXPECTED_REPOSITORY_FULL_NAME,
            "enforcement": "active",
        }],
        paths["ruleset_detail"]: {
            "id": host.EXPECTED_RULESET_ID,
            "name": host.EXPECTED_RULESET_NAME,
            "target": "branch",
            "source_type": "Repository",
            "source": host.EXPECTED_REPOSITORY_FULL_NAME,
            "enforcement": "active",
            "bypass_actors": [],
            "current_user_can_bypass": "never",
            "conditions": {
                "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}
            },
            "rules": rules,
        },
        effective_path: effective_rules,
        paths["default_branch_ref"]: {
            "ref": "refs/heads/main",
            "object": {"type": "commit", "sha": merge_head},
        },
        host._github_commit_path(reviewed_head): {
            "sha": reviewed_head,
            "parents": [{"sha": "b" * 40}],
        },
        host._github_commit_path(merge_head): {
            "sha": merge_head,
            "parents": [{"sha": "e" * 40}, {"sha": reviewed_head}],
        },
        host._github_compare_path(reviewed_head, merge_head): {
            "status": "identical" if reviewed_head == merge_head else "ahead",
            "ahead_by": 0 if reviewed_head == merge_head else 1,
            "behind_by": 0,
            "total_commits": 0 if reviewed_head == merge_head else 1,
            "base_commit": {"sha": reviewed_head},
            "merge_base_commit": {"sha": reviewed_head},
        },
        host._github_associated_pulls_path(reviewed_head, page=1): [{
            "number": pull_number,
            "state": "closed",
            "draft": False,
            "merged_at": merged_at,
            "merge_commit_sha": merge_head,
            "head": {
                "sha": reviewed_head,
                "repo": {
                    "id": host.EXPECTED_REPOSITORY_ID,
                    "full_name": host.EXPECTED_REPOSITORY_FULL_NAME,
                },
            },
            "base": {
                "ref": host.EXPECTED_DEFAULT_BRANCH,
                "sha": "e" * 40,
                "repo": {
                    "id": host.EXPECTED_REPOSITORY_ID,
                    "full_name": host.EXPECTED_REPOSITORY_FULL_NAME,
                },
            },
        }],
        host._github_pull_path(pull_number): {
            "number": pull_number,
            "state": "closed",
            "draft": False,
            "merged": True,
            "merged_at": merged_at,
            "merge_commit_sha": merge_head,
            "head": {
                "sha": reviewed_head,
                "repo": {
                    "id": host.EXPECTED_REPOSITORY_ID,
                    "full_name": host.EXPECTED_REPOSITORY_FULL_NAME,
                },
            },
            "base": {
                "ref": host.EXPECTED_DEFAULT_BRANCH,
                "sha": "e" * 40,
                "repo": {
                    "id": host.EXPECTED_REPOSITORY_ID,
                    "full_name": host.EXPECTED_REPOSITORY_FULL_NAME,
                },
            },
        },
        host._github_check_runs_path(reviewed_head, page=1): {
            "total_count": len(host.EXPECTED_REQUIRED_CHECKS),
            "check_runs": [
                {
                    "id": 1000 + index,
                    "name": check["context"],
                    "head_sha": reviewed_head,
                    "status": "completed",
                    "conclusion": "success",
                    "app": {"id": check["integration_id"]},
                    "started_at": check_started_at,
                    "completed_at": check_completed_at,
                    "pull_requests": [{"number": pull_number}],
                }
                for index, check in enumerate(host.EXPECTED_REQUIRED_CHECKS)
            ],
        },
    }


def _github_attestation(payloads: dict[str, object]) -> dict:
    paths = host._github_static_paths()
    inventory_path = host._github_inventory_path(1)
    effective_path = host._github_effective_rules_path(1)
    repo = host._repo_projection(payloads[paths["repository"]])
    inventory = host._ruleset_inventory_projection(
        payloads[inventory_path], page=1
    )
    ruleset_projection, ruleset = host._ruleset_projection(
        payloads[paths["ruleset_detail"]]
    )
    effective = host._effective_rules_projection(
        payloads[effective_path], page=1
    )
    ref = host._ref_projection(payloads[paths["default_branch_ref"]])
    merge_head = str(ref["object_sha"])
    commit_heads = [
        path.rsplit("/", 1)[-1]
        for path in payloads
        if "/commits/" in path
    ]
    reviewed_head = next(head for head in commit_heads if head != merge_head)
    compare_path = host._github_compare_path(reviewed_head, merge_head)
    pull_pages = []
    for page in range(1, host.MAX_GITHUB_PAGES + 1):
        path = host._github_associated_pulls_path(reviewed_head, page=page)
        if path not in payloads:
            break
        pull_pages.append((path, host._associated_pulls_projection(
            payloads[path], page=page
        )))
        if len(payloads[path]) < host.GITHUB_PAGE_SIZE:
            break
    pull_number = next(
        (
            item["number"]
            for _, projection in pull_pages
            for item in projection["items"]
            if item["head_sha"] == reviewed_head
            and item["merge_commit_sha"] == merge_head
        ),
        pull_pages[0][1]["items"][0]["number"],
    )
    pull_path = host._github_pull_path(pull_number)
    check_pages = []
    for page in range(1, host.MAX_GITHUB_PAGES + 1):
        path = host._github_check_runs_path(reviewed_head, page=page)
        if path not in payloads:
            break
        check_pages.append((path, host._check_runs_projection(
            payloads[path], page=page
        )))
        if len(payloads[path]["check_runs"]) < host.GITHUB_PAGE_SIZE:
            break
    observed = _timestamp(NOW - timedelta(minutes=1))
    projections = {
        host.GITHUB_API_ORIGIN + paths["repository"]: repo,
        host.GITHUB_API_ORIGIN + inventory_path: inventory,
        host.GITHUB_API_ORIGIN + paths["ruleset_detail"]: ruleset_projection,
        host.GITHUB_API_ORIGIN + effective_path: effective,
        host.GITHUB_API_ORIGIN + paths["default_branch_ref"]: ref,
        host.GITHUB_API_ORIGIN + host._github_commit_path(reviewed_head): (
            host._commit_projection(
                payloads[host._github_commit_path(reviewed_head)],
                requested_head=reviewed_head,
            )
        ),
        host.GITHUB_API_ORIGIN + host._github_commit_path(merge_head): (
            host._commit_projection(
                payloads[host._github_commit_path(merge_head)],
                requested_head=merge_head,
            )
        ),
        host.GITHUB_API_ORIGIN + compare_path: host._compare_projection(
            payloads[compare_path]
        ),
        **{
            host.GITHUB_API_ORIGIN + path: projection
            for path, projection in pull_pages
        },
        host.GITHUB_API_ORIGIN + pull_path: host._pull_projection(
            payloads[pull_path]
        ),
        **{
            host.GITHUB_API_ORIGIN + path: projection
            for path, projection in check_pages
        },
    }
    return {
        "repository": {
            "repository_id": host.EXPECTED_REPOSITORY_ID,
            "full_name": host.EXPECTED_REPOSITORY_FULL_NAME,
            "default_branch": host.EXPECTED_DEFAULT_BRANCH,
        },
        "reviewed_head": reviewed_head,
        "merge_head": merge_head,
        "ruleset": ruleset,
        "observed_at": observed,
        "expires_at": _timestamp(NOW + timedelta(minutes=5)),
        "evidence_captures": [
            {
                "url": url,
                "response_digest": host.canonical_digest(projection),
                "captured_at": observed,
            }
            for url, projection in sorted(projections.items())
        ],
    }


def test_github_verifier_reobserves_exact_policy_and_default_head() -> None:
    payloads = _github_payloads()
    transport = FakeGitHubTransport(payloads)
    verifier = host.GitHubRulesetVerifier(
        b"token-value", now=NOW, transport=transport
    )

    assert verifier(_github_attestation(payloads)) is True
    paths = host._github_static_paths()
    assert transport.calls == [
        paths["repository"],
        host._github_inventory_path(1),
        paths["ruleset_detail"],
        host._github_effective_rules_path(1),
        paths["default_branch_ref"],
        host._github_commit_path("c" * 40),
        host._github_commit_path("d" * 40),
        host._github_compare_path("c" * 40, "d" * 40),
        host._github_associated_pulls_path("c" * 40, page=1),
        host._github_pull_path(106),
        host._github_check_runs_path("c" * 40, page=1),
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "bypass", "head", "capture", "unknown", "inventory", "effective",
        "commit", "ancestry", "parameters", "merge_parent", "pr_unmerged",
        "pr_substitute", "pr_detail", "check_missing", "check_failed",
        "check_late", "check_wrong_app", "check_duplicate", "parent_order",
        "merge_after_observation", "check_total", "check_timestamp",
        "check_pending", "check_neutral", "pr_wrong_repo", "pr_wrong_base",
        "check_wrong_head", "check_other_pr", "parent_reflexive",
    ],
)
def test_github_verifier_fails_closed_on_policy_or_capture_drift(
    mutation: str,
) -> None:
    payloads = _github_payloads()
    attestation = _github_attestation(payloads)
    live = copy.deepcopy(payloads)
    paths = host._github_static_paths()
    ruleset_path = paths["ruleset_detail"]
    ref_path = paths["default_branch_ref"]
    pulls_path = host._github_associated_pulls_path("c" * 40, page=1)
    pull_path = host._github_pull_path(106)
    checks_path = host._github_check_runs_path("c" * 40, page=1)
    if mutation == "bypass":
        live[ruleset_path]["bypass_actors"] = [{"actor_id": 1}]
    elif mutation == "head":
        live[ref_path]["object"]["sha"] = "e" * 40
    elif mutation == "capture":
        attestation["evidence_captures"][0]["response_digest"] = DIGEST_A
    elif mutation == "unknown":
        live[ruleset_path]["rules"].append({"type": "creation"})
    elif mutation == "inventory":
        live[host._github_inventory_path(1)] = []
    elif mutation == "effective":
        live[host._github_effective_rules_path(1)].pop()
    elif mutation == "commit":
        live[host._github_commit_path("c" * 40)]["sha"] = "e" * 40
    elif mutation == "ancestry":
        compare_path = host._github_compare_path("c" * 40, "d" * 40)
        live[compare_path]["status"] = "diverged"
    elif mutation == "parameters":
        live[ruleset_path]["rules"][2]["parameters"][
            "required_review_thread_resolution"
        ] = False
    elif mutation == "merge_parent":
        live[host._github_commit_path("d" * 40)]["parents"] = [{"sha": "e" * 40}]
    elif mutation == "parent_order":
        live[host._github_commit_path("d" * 40)]["parents"].reverse()
    elif mutation == "parent_reflexive":
        live[host._github_commit_path("d" * 40)]["parents"][0]["sha"] = "c" * 40
    elif mutation == "pr_unmerged":
        live[pulls_path][0]["state"] = "open"
        live[pulls_path][0]["merged_at"] = None
    elif mutation == "pr_substitute":
        live[pulls_path][0]["head"]["sha"] = "a" * 40
    elif mutation == "pr_detail":
        live[pull_path]["merge_commit_sha"] = "a" * 40
    elif mutation == "pr_wrong_repo":
        live[pulls_path][0]["head"]["repo"]["id"] = 1
    elif mutation == "pr_wrong_base":
        live[pulls_path][0]["base"]["ref"] = "not-main"
    elif mutation == "check_missing":
        live[checks_path]["check_runs"].pop()
        live[checks_path]["total_count"] -= 1
    elif mutation == "check_failed":
        live[checks_path]["check_runs"][0]["conclusion"] = "failure"
    elif mutation == "check_late":
        live[checks_path]["check_runs"][0]["completed_at"] = _timestamp(
            NOW - timedelta(minutes=1)
        )
    elif mutation == "check_wrong_app":
        live[checks_path]["check_runs"][0]["app"]["id"] = 1
    elif mutation == "check_wrong_head":
        live[checks_path]["check_runs"][0]["head_sha"] = "a" * 40
    elif mutation == "check_other_pr":
        live[checks_path]["check_runs"][0]["pull_requests"] = [{"number": 1}]
    elif mutation == "check_duplicate":
        duplicate = copy.deepcopy(live[checks_path]["check_runs"][0])
        duplicate["id"] = 9999
        live[checks_path]["check_runs"].append(duplicate)
        live[checks_path]["total_count"] += 1
    elif mutation == "merge_after_observation":
        timestamp = _timestamp(NOW)
        live[pulls_path][0]["merged_at"] = timestamp
        live[pull_path]["merged_at"] = timestamp
    elif mutation == "check_total":
        live[checks_path]["total_count"] += 1
    elif mutation == "check_timestamp":
        live[checks_path]["check_runs"][0]["completed_at"] = None
    elif mutation == "check_pending":
        live[checks_path]["check_runs"][0]["status"] = "in_progress"
        live[checks_path]["check_runs"][0]["conclusion"] = None
    elif mutation == "check_neutral":
        live[checks_path]["check_runs"][0]["conclusion"] = "neutral"
    gate_mutations = {
        "merge_parent", "parent_order", "parent_reflexive", "pr_unmerged",
        "pr_substitute", "pr_detail", "pr_wrong_repo", "pr_wrong_base",
        "check_missing", "check_failed", "check_late", "check_wrong_app",
        "check_wrong_head", "check_other_pr", "check_duplicate",
        "merge_after_observation", "check_total", "check_timestamp",
        "check_pending", "check_neutral",
    }
    if mutation in gate_mutations:
        # Prove the semantic gate fails even when the packet forges matching
        # projection digests for the ineligible GitHub responses.
        attestation = _github_attestation(live)
    verifier = host.GitHubRulesetVerifier(
        b"token-value", now=NOW, transport=FakeGitHubTransport(live)
    )
    assert verifier(attestation) is False


def test_github_verifier_paginates_all_check_runs_before_acceptance() -> None:
    payloads = _github_payloads()
    first_path = host._github_check_runs_path("c" * 40, page=1)
    required = payloads[first_path]["check_runs"]
    irrelevant = [
        {
            **copy.deepcopy(required[0]),
            "id": 2000 + index,
            "name": f"irrelevant-{index}",
        }
        for index in range(host.GITHUB_PAGE_SIZE)
    ]
    payloads[first_path] = {
        "total_count": host.GITHUB_PAGE_SIZE + len(required),
        "check_runs": irrelevant,
    }
    payloads[host._github_check_runs_path("c" * 40, page=2)] = {
        "total_count": host.GITHUB_PAGE_SIZE + len(required),
        "check_runs": required,
    }
    transport = FakeGitHubTransport(payloads)
    verifier = host.GitHubRulesetVerifier(
        b"token-value", now=NOW, transport=transport
    )

    assert verifier(_github_attestation(payloads)) is True
    assert host._github_check_runs_path("c" * 40, page=2) in transport.calls


@pytest.mark.parametrize("mutation", ["total_drift", "duplicate_id"])
def test_github_verifier_rejects_forged_check_pagination(
    mutation: str,
) -> None:
    payloads = _github_payloads()
    first_path = host._github_check_runs_path("c" * 40, page=1)
    required = payloads[first_path]["check_runs"]
    irrelevant = [
        {
            **copy.deepcopy(required[0]),
            "id": 2000 + index,
            "name": f"irrelevant-{index}",
        }
        for index in range(host.GITHUB_PAGE_SIZE)
    ]
    total = host.GITHUB_PAGE_SIZE + len(required)
    payloads[first_path] = {"total_count": total, "check_runs": irrelevant}
    second_path = host._github_check_runs_path("c" * 40, page=2)
    payloads[second_path] = {"total_count": total, "check_runs": required}
    if mutation == "total_drift":
        payloads[second_path]["total_count"] += 1
    else:
        payloads[second_path]["check_runs"][0]["id"] = irrelevant[0]["id"]
    verifier = host.GitHubRulesetVerifier(
        b"token-value", now=NOW, transport=FakeGitHubTransport(payloads)
    )

    assert verifier(_github_attestation(payloads)) is False


def test_github_verifier_reads_associated_pull_terminal_page() -> None:
    payloads = _github_payloads()
    first_path = host._github_associated_pulls_path("c" * 40, page=1)
    target = payloads[first_path][0]
    payloads[first_path] = [
        {
            **copy.deepcopy(target),
            "number": 1000 + index,
            "head": {**copy.deepcopy(target["head"]), "sha": "a" * 40},
        }
        for index in range(host.GITHUB_PAGE_SIZE)
    ]
    second_path = host._github_associated_pulls_path("c" * 40, page=2)
    payloads[second_path] = [target]
    transport = FakeGitHubTransport(payloads)
    verifier = host.GitHubRulesetVerifier(
        b"token-value", now=NOW, transport=transport
    )

    assert verifier(_github_attestation(payloads)) is True
    assert second_path in transport.calls


def test_github_verifier_accepts_empty_check_pr_projection_for_exact_head() -> None:
    payloads = _github_payloads()
    checks_path = host._github_check_runs_path("c" * 40, page=1)
    payloads[checks_path]["check_runs"][0]["pull_requests"] = []
    verifier = host.GitHubRulesetVerifier(
        b"token-value", now=NOW, transport=FakeGitHubTransport(payloads)
    )

    assert verifier(_github_attestation(payloads)) is True


def test_github_verifier_does_not_treat_pull_base_sha_as_merge_parent() -> None:
    payloads = _github_payloads()
    pulls_path = host._github_associated_pulls_path("c" * 40, page=1)
    pull_path = host._github_pull_path(106)
    payloads[pulls_path][0]["base"]["sha"] = "f" * 40
    payloads[pull_path]["base"]["sha"] = "a" * 40
    verifier = host.GitHubRulesetVerifier(
        b"token-value", now=NOW, transport=FakeGitHubTransport(payloads)
    )

    assert verifier(_github_attestation(payloads)) is True


def test_github_verifier_reads_the_terminal_pagination_page() -> None:
    payloads = _github_payloads()
    inventory_path = host._github_inventory_path(1)
    template = payloads[inventory_path][0]
    payloads[inventory_path] = [
        {**template, "id": index + 1, "name": f"ruleset-{index + 1}"}
        for index in range(host.GITHUB_PAGE_SIZE)
    ]
    payloads[host._github_inventory_path(2)] = []
    transport = FakeGitHubTransport(payloads)
    verifier = host.GitHubRulesetVerifier(
        b"token-value", now=NOW, transport=transport
    )

    assert verifier(_github_attestation(_github_payloads())) is False
    assert host._github_inventory_path(2) in transport.calls


def test_finalizer_calls_canonical_closure_once_and_never_mutates_packet(
    monkeypatch: pytest.MonkeyPatch,
    trusted_signer: tuple[Path, Path],
) -> None:
    private_key, root = trusted_signer
    context = {
        "schema_version": "context_artifact_v1",
        "artifact_digest": DIGEST_B,
        "task_contract_digest": DIGEST_A,
    }
    packet = {
        "dispatch": {"context_artifact": context, "dag_digest": DIGEST_C},
        "evidence": [{
            "kind": "program_adoption_receipt_v1",
            "artifact": {"receipt": {"self_digest": DIGEST_A}},
        }],
    }
    original = copy.deepcopy(packet)
    bundle = _bundle([_entry("context_artifact_v1", DIGEST_B, context)])
    index = _index(bundle, _sign_bundle(bundle, private_key, root))
    calls = 0

    def fake_validate(candidate: dict, **kwargs: object) -> list[str]:
        nonlocal calls
        calls += 1
        assert kwargs["execution_attestation_verifier"](
            "context_artifact_v1", DIGEST_B, candidate["dispatch"]["context_artifact"]
        )
        assert callable(kwargs["external_evidence_verifier"])
        assert callable(kwargs["source_manifest_verifier"])
        candidate["mutated_only_inside_deepcopy"] = True
        return []

    monkeypatch.setattr(closure, "validate_closure", fake_validate)
    result = host._finalize_program_adoption(
        packet,
        execution_index=index,
        github_verifier=host.GitHubRulesetVerifier(
            b"token-value", now=NOW, transport=FakeGitHubTransport({})
        ),
        source_verifier=host.GitSourceManifestVerifier(ROOT),
        evaluated_at=NOW,
    )

    assert result["status"] == "PASS"
    assert result["program_adoption_receipt_digest"] == DIGEST_A
    assert calls == 1
    assert packet == original


def test_secure_json_reader_rejects_symlink_and_writable_input(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    target.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(OSError):
        host.read_secure_json(link)

    target.chmod(0o666)
    with pytest.raises(ValueError, match="writable"):
        host.read_secure_json(target)


def test_cli_does_not_accept_a_caller_selected_execution_key() -> None:
    args = governance._build_parser().parse_args([
        "aiml-trusted-finalize",
        "--packet", "packet.json",
        "--execution-bundle", "bundle.json",
        "--execution-signature", "bundle.json.sig",
        "--github-token-fd", "3",
    ])

    assert not hasattr(args, "execution_key_fd")
    assert args.execution_signature == Path("bundle.json.sig")


def test_cli_rejects_non_object_packet_with_structured_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    packet_path = tmp_path / "packet.json"
    bundle_path = tmp_path / "bundle.json"
    signature_path = tmp_path / "bundle.sig"
    packet_path.write_text("[]", encoding="utf-8")
    bundle_path.write_text("{}", encoding="utf-8")
    signature_path.write_text("not-a-signature", encoding="ascii")
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"token-value")
    os.close(write_fd)
    try:
        return_code = governance.main([
            "aiml-trusted-finalize",
            "--packet", str(packet_path),
            "--execution-bundle", str(bundle_path),
            "--execution-signature", str(signature_path),
            "--github-token-fd", str(read_fd),
        ])
    finally:
        os.close(read_fd)

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert return_code == 1
    assert result == {
        "schema_version": "aiml_trusted_host_finalization_result_v1",
        "status": "FAIL",
        "closure_digest": None,
        "program_adoption_receipt_digest": None,
        "errors": ["closure packet must be an object"],
    }
    assert captured.err == ""


def test_secret_pipe_uses_newline_frame_without_waiting_for_eof() -> None:
    read_fd, write_fd = os.pipe()

    def close_writer_later() -> None:
        time.sleep(0.4)
        os.close(write_fd)

    closer = threading.Thread(target=close_writer_later)
    os.write(write_fd, b"token-value\n")
    closer.start()
    started_at = time.monotonic()
    try:
        assert host.read_secret_fd(read_fd, label="GitHub credential") == b"token-value"
        elapsed = time.monotonic() - started_at
    finally:
        os.close(read_fd)
        closer.join(timeout=1)

    assert elapsed < 0.2


def test_secret_pipe_fails_closed_when_frame_never_terminates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"unterminated-token")
    monkeypatch.setattr(host.select, "select", lambda *_args: ([], [], []))
    try:
        with pytest.raises(ValueError, match="missing a newline frame or EOF"):
            host.read_secret_fd(read_fd, label="GitHub credential")
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_production_finalizer_surface_has_no_injectable_trust_capabilities() -> None:
    assert "finalize_program_adoption" not in governance.__all__
    assert not hasattr(governance, "finalize_program_adoption")
    assert not hasattr(host, "finalize_program_adoption")
    assert list(inspect.signature(host.finalize_from_host_inputs).parameters) == [
        "packet",
        "bundle",
        "execution_signature",
        "github_token",
    ]


def test_manifests_bind_trusted_host_module_and_test() -> None:
    from aiml_gate_receipt_validator import (  # type: ignore[import-not-found]
        PROGRAM_GOVERNANCE_PATHS,
        S0_3_EXACT_OWNED_PATHS,
    )

    expected = {
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_common.py",
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_git.py",
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_github.py",
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_github_pr.py",
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_host.py",
        "helper_scripts/maintenance_scripts/agent_governance_closure_time.py",
        "tests/structure/test_agent_governance_aiml_trusted_host.py",
    }
    assert expected.issubset(PROGRAM_GOVERNANCE_PATHS)
    assert expected.issubset(S0_3_EXACT_OWNED_PATHS)


def test_normative_docs_bind_trusted_finalizer_operator_interface() -> None:
    required_markers = {
        "aiml-trusted-finalize",
        "--github-token-fd",
        host.EXPECTED_EXECUTION_SIGNER_IDENTITY,
        host.EXPECTED_EXECUTION_SIGNER_FINGERPRINT,
        host.EXECUTION_SIGNATURE_NAMESPACE,
        "github_capture_projection_v2",
        "POST_MERGE_FINALIZATION",
        "merge-base --is-ancestor",
        "check-runs",
        "newline-framed",
        "CC / E2 / E3 / E4 / MIT / QA / R4",
        "PROGRAM_ADOPTED",
    }
    for relative_path in (
        "docs/agents/development-agent-governance.md",
        "docs/adr/0050-development-agent-governance.md",
    ):
        document = (ROOT / relative_path).read_text(encoding="utf-8")
        missing = sorted(marker for marker in required_markers if marker not in document)
        assert not missing, (
            f"{relative_path} missing trusted-finalizer contract: {missing}"
        )

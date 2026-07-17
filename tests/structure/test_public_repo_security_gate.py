from __future__ import annotations

import json
from pathlib import Path
import re
import runpy
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "helper_scripts" / "maintenance_scripts" / "public_repo_security_gate.py"
PRE_COMMIT = ROOT / "helper_scripts" / "git_hooks" / "pre-commit"
HISTORY_REPLACEMENTS = (
    ROOT
    / "helper_scripts"
    / "maintenance_scripts"
    / "public_repo_history_replacements.txt"
)
ARCHIVED_AI_EFFECTIVENESS_REPORT = (
    ROOT
    / "docs"
    / "CCAgentWorkSpace"
    / "AI-E"
    / "workspace"
    / "reports"
    / "archive"
    / "2026-05-09--ai_effectiveness_verification.md"
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Security Gate Test")
    _git(repo, "config", "user.email", "security-gate@example.invalid")
    (repo / ".github").mkdir()
    (repo / ".github" / "public-repo-security-allowlist.json").write_text(
        json.dumps(
            {
                "schema_version": "public_repo_security_allowlist_v1",
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    return repo


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _run_gate(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), "--repo-root", str(repo), *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def _json_lines(stdout: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in stdout.splitlines() if line]


def test_head_tree_rejects_tracked_dump_without_echoing_content(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    canary = "sensitive-canary-must-not-be-printed"
    (repo / "backups").mkdir()
    (repo / "backups" / "snapshot.dump").write_text(canary, encoding="utf-8")
    _commit_all(repo, "add forbidden dump")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert canary not in completed.stdout
    assert canary not in completed.stderr
    findings = _json_lines(completed.stdout)
    assert len(findings) == 1
    assert findings[0]["rule"] == "tracked_database_artifact"
    assert findings[0]["path"] == "backups/snapshot.dump"
    assert set(findings[0]) <= {"rule", "path", "line", "blob_oid", "fingerprint"}


@pytest.mark.parametrize(
    ("magic", "rule"),
    [
        (b"PG" + b"DMP" + b"fixture", "postgres_dump_magic"),
        (b"SQLite " + b"format 3" + b"\x00fixture", "sqlite_database_magic"),
    ],
)
def test_head_tree_rejects_database_magic_in_neutral_filename(
    tmp_path: Path, magic: bytes, rule: str
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "artifact.bin").write_bytes(magic)
    _commit_all(repo, "add disguised database")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    findings = _json_lines(completed.stdout)
    assert [finding["rule"] for finding in findings] == [rule]
    assert findings[0]["path"] == "artifact.bin"


def test_head_tree_rejects_private_key_header_without_echoing_key(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    key_header = "-----BEGIN " + "PRIVATE KEY-----"
    canary = "private-key-material-must-not-be-printed"
    (repo / "config.txt").write_text(
        f"label=test\n{key_header}\n{canary}\n", encoding="utf-8"
    )
    _commit_all(repo, "add private material")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert canary not in completed.stdout
    assert canary not in completed.stderr
    findings = _json_lines(completed.stdout)
    assert [(finding["rule"], finding["line"]) for finding in findings] == [
        ("private_key_header", 2)
    ]


def test_head_tree_rejects_embedded_credential_dsn_without_echoing_it(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    scheme = "postgres" + "ql"
    password = "".join(("v9Qm2", "Zr7Kx4", "Np8Ty"))
    dsn = f"{scheme}://service:{password}@db.example.invalid/app"
    (repo / "settings.toml").write_text(f"mode = 'test'\ndsn = '{dsn}'\n", encoding="utf-8")
    _commit_all(repo, "add embedded credential dsn")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert password not in completed.stdout
    assert password not in completed.stderr
    findings = _json_lines(completed.stdout)
    assert [(finding["rule"], finding["line"]) for finding in findings] == [
        ("embedded_credential_dsn", 2)
    ]


def test_head_tree_rejects_low_entropy_embedded_dsn_password(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    scheme = "postgres" + "ql"
    password = "k7"
    dsn = f"{scheme}://service:{password}@db.example.invalid/app"
    (repo / "settings.toml").write_text(f"dsn = '{dsn}'\n", encoding="utf-8")
    _commit_all(repo, "add low entropy credential dsn")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert password not in completed.stdout
    assert password not in completed.stderr
    assert [finding["rule"] for finding in _json_lines(completed.stdout)] == [
        "embedded_credential_dsn"
    ]


def test_same_line_multi_match_emits_one_fingerprint(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    first_password = "k7"
    second_password = "m9"
    payload = (
        f"primary=postgresql://service:{first_password}@db.example.invalid/app "
        f"fallback=mysql://service:{second_password}@db.example.invalid/app\n"
    )
    (repo / "settings.toml").write_text(payload, encoding="utf-8")
    _commit_all(repo, "add two same-line credential dsns")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert first_password not in completed.stdout
    assert second_password not in completed.stdout
    findings = _json_lines(completed.stdout)
    assert len(findings) == 1
    assert findings[0]["rule"] == "embedded_credential_dsn"
    assert findings[0]["line"] == 1


def test_distinct_lines_rules_and_paths_keep_distinct_findings(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    token = "AK" + "IA" + "Q7W9E2R4T6Y8U1I3"
    payload = (
        "primary=postgresql://service:k7@db.example.invalid/app "
        "fallback=mysql://service:m9@db.example.invalid/app "
        f"token={token}\n"
        "secondary=redis://service:p3@cache.example.invalid/0\n"
    )
    (repo / "settings-a.toml").write_text(payload, encoding="utf-8")
    (repo / "settings-b.toml").write_text(payload, encoding="utf-8")
    _commit_all(repo, "add shared blob at two paths")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert token not in completed.stdout
    findings = _json_lines(completed.stdout)
    assert [
        (finding["path"], finding["line"], finding["rule"])
        for finding in findings
    ] == [
        ("settings-a.toml", 1, "embedded_credential_dsn"),
        ("settings-a.toml", 1, "provider_token"),
        ("settings-a.toml", 2, "embedded_credential_dsn"),
        ("settings-b.toml", 1, "embedded_credential_dsn"),
        ("settings-b.toml", 1, "provider_token"),
        ("settings-b.toml", 2, "embedded_credential_dsn"),
    ]
    assert len({finding["fingerprint"] for finding in findings}) == len(findings)


def test_head_tree_rejects_every_dsn_password_placeholder_value(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    scheme = "postgres" + "ql"
    passwords = ("changeme", "example", "password", "placeholder", "redacted")
    payload = "\n".join(
        f"dsn_{index}={scheme}://service:{password}@db.example.invalid/app"
        for index, password in enumerate(passwords)
    )
    (repo / "settings.toml").write_text(payload + "\n", encoding="utf-8")
    _commit_all(repo, "add dsn placeholder password values")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert all(password not in completed.stdout for password in passwords)
    assert all(password not in completed.stderr for password in passwords)
    findings = _json_lines(completed.stdout)
    assert [finding["rule"] for finding in findings] == [
        "embedded_credential_dsn"
    ] * len(passwords)
    assert [finding["line"] for finding in findings] == list(
        range(1, len(passwords) + 1)
    )


@pytest.mark.parametrize(
    "token",
    [
        "gh" + "p_" + "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5",
        "AK" + "IA" + "Q7W9E2R4T6Y8U1I3",
        "AI" + "za" + "Q7w9E2r4T6y8U1i3O5p7A9s2D4f6G8h1J3k",
        "sk" + "-" + "Q7w9E2r4T6y8U1i3O5p7A9s2D4f6G8h1",
    ],
)
def test_head_tree_rejects_provider_shaped_tokens_without_echoing_them(
    tmp_path: Path, token: str
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "provider.env").write_text(f"PROVIDER_TOKEN={token}\n", encoding="utf-8")
    _commit_all(repo, "add provider-shaped token")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert token not in completed.stdout
    assert token not in completed.stderr
    assert [finding["rule"] for finding in _json_lines(completed.stdout)] == [
        "provider_token"
    ]


@pytest.mark.parametrize("suffix", ["...", "-..."])
def test_head_tree_rejects_provider_token_with_ellipsis_suffix(
    tmp_path: Path, suffix: str
) -> None:
    repo = _init_repo(tmp_path)
    token = "sk" + "-ant-api03-" + "Q7w9E2r4T6y8U1i3O5p7A9s2D4f6G8h1" + suffix
    (repo / "provider.env").write_text(f"PROVIDER_TOKEN={token}\n", encoding="utf-8")
    _commit_all(repo, "add provider token with ellipsis suffix")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert token not in completed.stdout
    assert token not in completed.stderr
    assert [finding["rule"] for finding in _json_lines(completed.stdout)] == [
        "provider_token"
    ]


def test_archived_ai_effectiveness_report_contains_no_provider_token() -> None:
    assert ARCHIVED_AI_EFFECTIVENESS_REPORT.is_file()
    payload = ARCHIVED_AI_EFFECTIVENESS_REPORT.read_bytes()
    lines = payload.splitlines()
    assert len(lines) >= 52
    assert lines[51]
    scanner = runpy.run_path(str(GATE), run_name="public_repo_security_gate_test")[
        "PROVIDER_TOKEN"
    ]

    assert sum(1 for _match in scanner.finditer(payload)) == 0


def test_head_tree_rejects_jwt_shaped_secret_without_echoing_it(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    header = "ey" + "JhbGciOiJIUzI1NiJ9"
    payload = "ey" + "JzdWIiOiJzZXJ2aWNlIn0"
    signature = "Q7w9E2r4T6y8U1i3O5p7A9s2D4f6G8h1"
    token = ".".join((header, payload, signature))
    (repo / "session.txt").write_text(f"token={token}\n", encoding="utf-8")
    _commit_all(repo, "add jwt-shaped token")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert token not in completed.stdout
    assert token not in completed.stderr
    assert [finding["rule"] for finding in _json_lines(completed.stdout)] == [
        "jwt_token"
    ]


def test_head_tree_rejects_secret_pattern_inside_binary_blob(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    token = "AK" + "IA" + "Q7W9E2R4T6Y8U1I3"
    (repo / "opaque.bin").write_bytes(b"\x00binary-prefix\x00" + token.encode("ascii"))
    _commit_all(repo, "add secret-shaped bytes in binary blob")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 1
    assert token not in completed.stdout
    assert token not in completed.stderr
    assert [finding["rule"] for finding in _json_lines(completed.stdout)] == [
        "provider_token"
    ]


def test_commit_range_rejects_secret_removed_before_head(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    base = _commit_all(repo, "base")

    token = "gh" + "o_" + "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5"
    (repo / "transient.txt").write_text(f"token={token}\n", encoding="utf-8")
    _commit_all(repo, "introduce transient secret")
    (repo / "transient.txt").unlink()
    _commit_all(repo, "remove transient secret")

    head_scan = _run_gate(repo, "--tree", "HEAD")
    range_scan = _run_gate(repo, "--range", f"{base}..HEAD")

    assert head_scan.returncode == 0
    assert range_scan.returncode == 1
    assert token not in range_scan.stdout
    assert token not in range_scan.stderr
    findings = _json_lines(range_scan.stdout)
    assert [(finding["rule"], finding["path"]) for finding in findings] == [
        ("provider_token", "transient.txt")
    ]


def test_commit_range_keeps_distinct_blob_fingerprints_for_same_path_and_line(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    base = _commit_all(repo, "base")
    first_password = "k7"
    second_password = "m9"
    (repo / "settings.toml").write_text(
        f"dsn=postgresql://service:{first_password}@db.example.invalid/app\n",
        encoding="utf-8",
    )
    _commit_all(repo, "add first dsn blob")
    (repo / "settings.toml").write_text(
        f"dsn=postgresql://service:{second_password}@db.example.invalid/app\n",
        encoding="utf-8",
    )
    _commit_all(repo, "replace with second dsn blob")

    completed = _run_gate(repo, "--range", f"{base}..HEAD")

    assert completed.returncode == 1
    assert first_password not in completed.stdout
    assert second_password not in completed.stdout
    findings = [
        finding
        for finding in _json_lines(completed.stdout)
        if finding["path"] == "settings.toml"
    ]
    assert len(findings) == 2
    assert {finding["rule"] for finding in findings} == {"embedded_credential_dsn"}
    assert {finding["line"] for finding in findings} == {1}
    assert len({finding["blob_oid"] for finding in findings}) == 2
    assert len({finding["fingerprint"] for finding in findings}) == 2


def test_history_inventory_rejects_dump_deleted_from_head(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    canary = "deleted-history-canary-must-not-be-printed"
    (repo / "snapshot.dump").write_text(canary, encoding="utf-8")
    _commit_all(repo, "add historical dump")
    (repo / "snapshot.dump").unlink()
    _commit_all(repo, "delete historical dump")

    head_scan = _run_gate(repo, "--tree", "HEAD")
    history_scan = _run_gate(
        repo,
        "--history-ref",
        "HEAD",
        "--expected-ref-count",
        "1",
    )

    assert head_scan.returncode == 0
    assert history_scan.returncode == 1
    assert canary not in history_scan.stdout
    assert canary not in history_scan.stderr
    assert [(finding["rule"], finding["path"]) for finding in _json_lines(history_scan.stdout)] == [
        ("tracked_database_artifact", "snapshot.dump")
    ]


def test_history_path_policy_checks_every_path_for_a_shared_blob(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    payload = "same blob, two reachable paths\n"
    (repo / "safe.txt").write_text(payload, encoding="utf-8")
    (repo / "secret.dump").write_text(payload, encoding="utf-8")
    _commit_all(repo, "add safe and forbidden aliases for one blob")

    completed = _run_gate(
        repo,
        "--history-ref",
        "HEAD",
        "--expected-ref-count",
        "1",
    )

    assert completed.returncode == 1
    assert [(finding["rule"], finding["path"]) for finding in _json_lines(completed.stdout)] == [
        ("tracked_database_artifact", "secret.dump")
    ]


def test_history_refs_file_fails_closed_when_expected_inventory_is_incomplete(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    _commit_all(repo, "base")
    refs_file = tmp_path / "refs.txt"
    refs_file.write_text("HEAD\n", encoding="utf-8")

    completed = _run_gate(
        repo,
        "--history-refs-file",
        str(refs_file),
        "--expected-ref-count",
        "2",
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "[public-repo-security-gate][ERROR] scan failed closed\n"


def test_exact_allowlist_entry_suppresses_only_its_matching_finding(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "snapshot.dump").write_text("fixture", encoding="utf-8")
    _commit_all(repo, "add allowlisted dump")
    finding = _json_lines(_run_gate(repo, "--tree", "HEAD").stdout)[0]
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps(
            {
                "schema_version": "public_repo_security_allowlist_v1",
                "entries": [
                    {
                        "fingerprint": finding["fingerprint"],
                        "rule": finding["rule"],
                        "path": finding["path"],
                        "owner": "@security-owner",
                        "reason": "Temporary fixture accepted by the security owner.",
                        "expires_on": "2999-12-31",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = _run_gate(
        repo,
        "--allowlist-file",
        str(allowlist),
        "--tree",
        "HEAD",
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_one_exact_allowlist_entry_consumes_same_line_multi_match(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    payload = (
        "primary=postgresql://service:k7@db.example.invalid/app "
        "fallback=mysql://service:m9@db.example.invalid/app\n"
    )
    (repo / "settings.toml").write_text(payload, encoding="utf-8")
    _commit_all(repo, "add same-line duplicate-fingerprint dsns")
    initial_findings = _json_lines(_run_gate(repo, "--tree", "HEAD").stdout)
    assert len(initial_findings) == 1
    finding = initial_findings[0]
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps(
            {
                "schema_version": "public_repo_security_allowlist_v1",
                "entries": [
                    {
                        "fingerprint": finding["fingerprint"],
                        "rule": finding["rule"],
                        "path": finding["path"],
                        "owner": "@security-owner",
                        "reason": "Temporary fixture accepted by the security owner.",
                        "expires_on": "2999-12-31",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = _run_gate(
        repo,
        "--allowlist-file",
        str(allowlist),
        "--tree",
        "HEAD",
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_omitted_allowlist_argument_uses_repository_versioned_allowlist(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "snapshot.dump").write_text("fixture", encoding="utf-8")
    _commit_all(repo, "add dump before default allowlist")
    finding = _json_lines(_run_gate(repo, "--tree", "HEAD").stdout)[0]
    (repo / ".github" / "public-repo-security-allowlist.json").write_text(
        json.dumps(
            {
                "schema_version": "public_repo_security_allowlist_v1",
                "entries": [
                    {
                        "fingerprint": finding["fingerprint"],
                        "rule": finding["rule"],
                        "path": finding["path"],
                        "owner": "@security-owner",
                        "reason": "Temporary fixture accepted by the security owner.",
                        "expires_on": "2999-12-31",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _commit_all(repo, "add default allowlist entry")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_allowlist_unknown_top_level_field_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    _commit_all(repo, "add safe content")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps(
            {
                "schema_version": "public_repo_security_allowlist_v1",
                "entries": [],
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )

    completed = _run_gate(
        repo,
        "--allowlist-file",
        str(allowlist),
        "--tree",
        "HEAD",
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "[public-repo-security-gate][ERROR] scan failed closed\n"


def test_allowlist_entry_requires_exact_field_set(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "snapshot.dump").write_text("fixture", encoding="utf-8")
    _commit_all(repo, "add finding")
    finding = _json_lines(_run_gate(repo, "--tree", "HEAD").stdout)[0]
    base_entry = {
        "fingerprint": finding["fingerprint"],
        "rule": finding["rule"],
        "path": finding["path"],
        "owner": "@security-owner",
        "reason": "Temporary fixture accepted by the security owner.",
        "expires_on": "2999-12-31",
    }
    entries = []
    entry_with_unknown_field = dict(base_entry, unexpected=True)
    entries.append(entry_with_unknown_field)
    entry_with_missing_field = dict(base_entry)
    del entry_with_missing_field["reason"]
    entries.append(entry_with_missing_field)

    for index, entry in enumerate(entries):
        allowlist = tmp_path / f"allowlist-{index}.json"
        allowlist.write_text(
            json.dumps(
                {
                    "schema_version": "public_repo_security_allowlist_v1",
                    "entries": [entry],
                }
            ),
            encoding="utf-8",
        )
        completed = _run_gate(
            repo,
            "--allowlist-file",
            str(allowlist),
            "--tree",
            "HEAD",
        )

        assert completed.returncode == 2
        assert completed.stdout == ""
        assert completed.stderr == (
            "[public-repo-security-gate][ERROR] scan failed closed\n"
        )


def test_allowlist_rejects_invalid_entry_values_and_glob_paths(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "snapshot.dump").write_text("fixture", encoding="utf-8")
    _commit_all(repo, "add finding")
    finding = _json_lines(_run_gate(repo, "--tree", "HEAD").stdout)[0]
    base_entry = {
        "fingerprint": finding["fingerprint"],
        "rule": finding["rule"],
        "path": finding["path"],
        "owner": "@security-owner",
        "reason": "Temporary fixture accepted by the security owner.",
        "expires_on": "2999-12-31",
    }
    invalid_values = (
        ("fingerprint", "sha256:not-a-digest"),
        ("rule", "unknown_rule"),
        ("path", "*.dump"),
        ("path", "/snapshot.dump"),
        ("path", "archive/../snapshot.dump"),
        ("owner", "security-owner"),
        ("reason", "   "),
        ("reason", 7),
        ("expires_on", "2999-1-1"),
    )

    for index, (field, invalid_value) in enumerate(invalid_values):
        entry = dict(base_entry)
        entry[field] = invalid_value
        allowlist = tmp_path / f"allowlist-invalid-{index}.json"
        allowlist.write_text(
            json.dumps(
                {
                    "schema_version": "public_repo_security_allowlist_v1",
                    "entries": [entry],
                }
            ),
            encoding="utf-8",
        )
        completed = _run_gate(
            repo,
            "--allowlist-file",
            str(allowlist),
            "--tree",
            "HEAD",
        )

        assert completed.returncode == 2, (field, invalid_value)
        assert completed.stdout == ""
        assert completed.stderr == (
            "[public-repo-security-gate][ERROR] scan failed closed\n"
        )


def test_allowlist_rejects_expired_entry(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "snapshot.dump").write_text("fixture", encoding="utf-8")
    _commit_all(repo, "add finding")
    finding = _json_lines(_run_gate(repo, "--tree", "HEAD").stdout)[0]
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps(
            {
                "schema_version": "public_repo_security_allowlist_v1",
                "entries": [
                    {
                        "fingerprint": finding["fingerprint"],
                        "rule": finding["rule"],
                        "path": finding["path"],
                        "owner": "@security-owner",
                        "reason": "Expired fixture approval.",
                        "expires_on": "2000-01-01",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = _run_gate(
        repo,
        "--allowlist-file",
        str(allowlist),
        "--tree",
        "HEAD",
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "[public-repo-security-gate][ERROR] scan failed closed\n"


def test_allowlist_rejects_duplicate_fingerprint_entries(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "snapshot.dump").write_text("fixture", encoding="utf-8")
    _commit_all(repo, "add finding")
    finding = _json_lines(_run_gate(repo, "--tree", "HEAD").stdout)[0]
    entry = {
        "fingerprint": finding["fingerprint"],
        "rule": finding["rule"],
        "path": finding["path"],
        "owner": "@security-owner",
        "reason": "Duplicate fixture approval.",
        "expires_on": "2999-12-31",
    }
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps(
            {
                "schema_version": "public_repo_security_allowlist_v1",
                "entries": [entry, entry],
            }
        ),
        encoding="utf-8",
    )

    completed = _run_gate(
        repo,
        "--allowlist-file",
        str(allowlist),
        "--tree",
        "HEAD",
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "[public-repo-security-gate][ERROR] scan failed closed\n"


def test_allowlist_rejects_unused_entry(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    _commit_all(repo, "add safe content")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps(
            {
                "schema_version": "public_repo_security_allowlist_v1",
                "entries": [
                    {
                        "fingerprint": "sha256:" + "0" * 64,
                        "rule": "tracked_database_artifact",
                        "path": "snapshot.dump",
                        "owner": "@security-owner",
                        "reason": "Entry must correspond to a current finding.",
                        "expires_on": "2999-12-31",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = _run_gate(
        repo,
        "--allowlist-file",
        str(allowlist),
        "--tree",
        "HEAD",
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr == "[public-repo-security-gate][ERROR] scan failed closed\n"


def test_allowlist_fingerprint_cannot_cross_rule_or_path_scope(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "snapshot.dump").write_text("fixture", encoding="utf-8")
    _commit_all(repo, "add finding")
    finding = _json_lines(_run_gate(repo, "--tree", "HEAD").stdout)[0]
    scope_mismatches = (
        ("provider_token", finding["path"]),
        (finding["rule"], "different.dump"),
    )

    for index, (rule, path) in enumerate(scope_mismatches):
        allowlist = tmp_path / f"allowlist-scope-{index}.json"
        allowlist.write_text(
            json.dumps(
                {
                    "schema_version": "public_repo_security_allowlist_v1",
                    "entries": [
                        {
                            "fingerprint": finding["fingerprint"],
                            "rule": rule,
                            "path": path,
                            "owner": "@security-owner",
                            "reason": "A fingerprint must not cross its original scope.",
                            "expires_on": "2999-12-31",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        completed = _run_gate(
            repo,
            "--allowlist-file",
            str(allowlist),
            "--tree",
            "HEAD",
        )

        assert completed.returncode == 2
        assert completed.stdout == ""
        assert completed.stderr == (
            "[public-repo-security-gate][ERROR] scan failed closed\n"
        )


def test_staged_mode_scans_the_complete_pending_tree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    _commit_all(repo, "base")

    token = "AK" + "IA" + "Q7W9E2R4T6Y8U1I3"
    (repo / "pending.env").write_text(f"TOKEN={token}\n", encoding="utf-8")
    _git(repo, "add", "pending.env")

    head_scan = _run_gate(repo, "--tree", "HEAD")
    staged_scan = _run_gate(repo, "--staged")

    assert head_scan.returncode == 0
    assert staged_scan.returncode == 1
    assert token not in staged_scan.stdout
    assert token not in staged_scan.stderr
    assert [finding["path"] for finding in _json_lines(staged_scan.stdout)] == [
        "pending.env"
    ]


def test_safe_lookalikes_remain_clean(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    safe_lines = [
        "dsn=postgresql://service@db.example.invalid/app",
        "key_header=-----BEGIN PUBLIC KEY-----",
        "provider_token=sk-example-short",
        "unsigned_token=eyJheader.eyJpayload",
    ]
    (repo / "safe-fixtures.txt").write_text("\n".join(safe_lines), encoding="utf-8")
    _commit_all(repo, "add safe lookalikes")

    completed = _run_gate(repo, "--tree", "HEAD")

    assert completed.returncode == 0
    assert completed.stdout == ""


def test_history_dsn_replacement_removes_credential_userinfo_shape() -> None:
    first_rule = HISTORY_REPLACEMENTS.read_text(encoding="utf-8").splitlines()[0]
    assert first_rule.startswith("regex:")
    expression, replacement = first_rule.removeprefix("regex:").split("==>", 1)
    schemes = (
        "postgres",
        "postgresql",
        "mysql",
        "mariadb",
        "mongodb",
        "mongodb+srv",
        "redis",
        "amqp",
        "amqps",
    )
    samples = [
        (
            f"before[{scheme}://synthetic-user:synthetic-password@"
            "db.example.invalid:6543/application?tls=required]after"
        ).encode("utf-8")
        for scheme in schemes
    ]
    payload = b"\n".join(samples)
    scanner = runpy.run_path(str(GATE), run_name="public_repo_security_gate_test")[
        "EMBEDDED_CREDENTIAL_DSN"
    ]
    assert sum(1 for _match in scanner.finditer(payload)) == len(samples)

    rewritten = re.sub(
        expression.encode("utf-8"),
        replacement.encode("utf-8"),
        payload,
    )

    assert sum(1 for _match in scanner.finditer(rewritten)) == 0
    for scheme in schemes:
        expected = (
            f"before[{scheme}://redacted@"
            "db.example.invalid:6543/application?tls=required]after"
        ).encode("utf-8")
        assert expected in rewritten


def test_history_replacement_policy_removes_supported_secret_shapes() -> None:
    scheme = "postgres" + "ql"
    password = "V9q2SensitiveHistoryPassword"
    dsn = f"{scheme}://service:{password}@db.example.invalid/app"
    provider = "gh" + "p_" + "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5"
    jwt = ".".join(
        (
            "ey" + "JhbGciOiJIUzI1NiJ9",
            "ey" + "JzdWIiOiJzZXJ2aWNlIn0",
            "Q7w9E2r4T6y8U1i3O5p7A9s2D4f6G8h1",
        )
    )
    payload = f"dsn={dsn}\nprovider={provider}\njwt={jwt}\n".encode("utf-8")

    for line in HISTORY_REPLACEMENTS.read_text(encoding="utf-8").splitlines():
        assert line.startswith("regex:")
        expression, replacement = line.removeprefix("regex:").split("==>", 1)
        payload = re.sub(expression.encode("utf-8"), replacement.encode("utf-8"), payload)

    assert password.encode("utf-8") not in payload
    assert provider.encode("utf-8") not in payload
    assert jwt.encode("utf-8") not in payload
    assert b"postgresql://redacted@db.example.invalid/app" in payload


def test_invalid_revision_fails_closed_without_echoing_revision(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("safe\n", encoding="utf-8")
    _commit_all(repo, "base")
    canary = "missing-canary-ref"

    completed = _run_gate(repo, "--tree", canary)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert canary not in completed.stderr
    assert completed.stderr == "[public-repo-security-gate][ERROR] scan failed closed\n"


def test_pre_commit_runs_native_gate_before_optional_gitleaks() -> None:
    source = PRE_COMMIT.read_text(encoding="utf-8")
    native_invocation = (
        'python3 "$REPO_ROOT/helper_scripts/maintenance_scripts/'
        'public_repo_security_gate.py" --repo-root "$REPO_ROOT" --staged'
    )

    assert native_invocation in source
    assert source.index(native_invocation) < source.index(
        "if ! command -v gitleaks >/dev/null 2>&1; then"
    )
    assert "repo-native public repository hygiene gate failed closed" in source

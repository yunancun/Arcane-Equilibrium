#!/usr/bin/env python3
"""Deterministic tracked-tree public repository hygiene gate."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Iterator, Sequence


DATABASE_ARTIFACT_SUFFIXES = (
    ".bak",
    ".backup",
    ".db",
    ".dump",
    ".sqlite",
    ".sqlite3",
)
POSTGRES_DUMP_MAGIC = b"PG" + b"DMP"
SQLITE_DATABASE_MAGIC = b"SQLite " + b"format 3" + b"\x00"
PRIVATE_KEY_HEADER = re.compile(br"-{5}BEGIN [A-Z0-9 ]*" + br"PRIVATE KEY-{5}")
EMBEDDED_CREDENTIAL_DSN = re.compile(
    br"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqps?)"
    br"://[^\s:/?#]{1,128}:(?P<password>[^\s/@?#]{1,256})@"
)
# 下列變體 pattern 的關鍵 token 以 bytes 串接拆開（同 POSTGRES_DUMP_MAGIC 手法），
# 避免 gate 掃描含本檔的完整 tree 時，源碼 raw bytes 自身成為可匹配形。
# 變體一：URI query 參數形——同一 scheme 集，憑證放在 query key 而非授權段；
# (?:ssl)? 同時涵蓋 ssl 前綴 query key。量詞全部有界、中段非貪婪，維持線性掃描。
EMBEDDED_CREDENTIAL_DSN_QUERY = re.compile(
    br"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqps?)"
    br"://[^\s#]{1,512}?[?&](?:ssl)?pass" + br"word=(?P<password>[^&#\s]{1,256})"
)
# 變體二/三：libpq keyword conninfo 形——password token 與至少一個錨 keyword
# token 同行、空白分隔；兩個方向（錨在前 / password token 在前）各一支 pattern。
# 負回顧擋 `PGPASSWORD`、`FOO_password` 這類前綴 token；值排除逗號/分號，讓
# Python kwarg（帶逗號）出界；量詞全部有界，避免嵌套量詞回溯。
_LIBPQ_ANCHOR_TOKEN = br"(?<![A-Za-z0-9_])(?:hostaddr|host|port|dbname|user)=[^\s,;]{1,256}"
_LIBPQ_PASSWORD_TOKEN = br"(?<![A-Za-z0-9_])pass" + br"word=(?P<password>[^\s,;]{1,256})"
_LIBPQ_TOKEN_SEPARATOR = br"(?:[ \t]+[A-Za-z0-9_]{1,32}=[^\s,;]{1,256}){0,16}[ \t]+"
EMBEDDED_CREDENTIAL_DSN_KEYWORD_FORWARD = re.compile(
    _LIBPQ_ANCHOR_TOKEN + _LIBPQ_TOKEN_SEPARATOR + _LIBPQ_PASSWORD_TOKEN
)
EMBEDDED_CREDENTIAL_DSN_KEYWORD_REVERSE = re.compile(
    _LIBPQ_PASSWORD_TOKEN + _LIBPQ_TOKEN_SEPARATOR + _LIBPQ_ANCHOR_TOKEN
)
EMBEDDED_CREDENTIAL_DSN_VARIANTS = (
    EMBEDDED_CREDENTIAL_DSN_QUERY,
    EMBEDDED_CREDENTIAL_DSN_KEYWORD_FORWARD,
    EMBEDDED_CREDENTIAL_DSN_KEYWORD_REVERSE,
)
# sanctioned ephemeral CI 憑證對：與 .github/workflows/ci.yml service env 的
# POSTGRES_USER / POSTGRES_PASSWORD 同值明文，是 CI 容器一次性、非機密憑證。
# carve-out 語義＝「password 捕獲值 + match 起點同行 user token」的 exact 配對
# 豁免，非 secrecy 鬆綁；僅適用 query / keyword 兩類新變體，authority 形無
# carve-out。除此 exact 對外一律 shape-based 拒絕（逐 match 檢查 password 值，
# 同一行的第二個非 sanctioned DSN 仍拒）。兩常數必須分行，不得相鄰拼成可匹配形。
SANCTIONED_CI_PASSWORD_VALUE = b"contract_pass"
SANCTIONED_CI_USER_TOKEN = b"user=contract_user"
PROVIDER_TOKEN = re.compile(
    br"(?:"
    br"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"
    br"|\bgithub_pat_[A-Za-z0-9_]{60,255}\b"
    br"|\bAKIA[A-Z0-9]{16}\b"
    br"|\bAIza[A-Za-z0-9_-]{35,80}\b"
    br"|\bsk-[A-Za-z0-9]{32,255}\b"
    br"|\bsk-ant-[A-Za-z0-9_-]{20,255}\b"
    br"|\bxox[baprs]-[A-Za-z0-9-]{20,255}\b"
    br")"
)
JWT_TOKEN = re.compile(
    br"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}\b"
)
REVISION_EXPRESSION = re.compile(r"[A-Za-z0-9_./^~{}:+-]+")
OBJECT_OID = re.compile(br"(?:[0-9a-f]{40}|[0-9a-f]{64})")
ALLOWLIST_SCHEMA_VERSION = "public_repo_security_allowlist_v1"
DEFAULT_ALLOWLIST_FILE = Path(".github/public-repo-security-allowlist.json")
ALLOWLIST_ENTRY_FIELDS = frozenset(
    {"fingerprint", "rule", "path", "owner", "reason", "expires_on"}
)
ALLOWLIST_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
ALLOWLIST_OWNER = re.compile(r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
ALLOWLIST_RULES = frozenset(
    {
        "embedded_credential_dsn",
        "jwt_token",
        "postgres_dump_magic",
        "private_key_header",
        "provider_token",
        "sqlite_database_magic",
        "tracked_database_artifact",
    }
)
GLOB_META_CHARACTERS = frozenset("*?[]{}")


class GateError(RuntimeError):
    """可預期的 fail-closed 掃描錯誤；不得攜帶 blob 內容。"""


def _validate_allowlist_entry(entry: dict[str, Any]) -> None:
    if any(not isinstance(entry[field], str) for field in ALLOWLIST_ENTRY_FIELDS):
        raise GateError("allowlist_entry_value_type_invalid")
    if ALLOWLIST_FINGERPRINT.fullmatch(entry["fingerprint"]) is None:
        raise GateError("allowlist_fingerprint_invalid")
    if entry["rule"] not in ALLOWLIST_RULES:
        raise GateError("allowlist_rule_invalid")

    path = entry["path"]
    parsed_path = PurePosixPath(path)
    if (
        not path
        or len(path) > 4096
        or path.startswith("/")
        or "\\" in path
        or any(character in path for character in GLOB_META_CHARACTERS)
        or parsed_path.as_posix() != path
        or any(part in {"", ".", ".."} for part in parsed_path.parts)
    ):
        raise GateError("allowlist_path_invalid")
    if ALLOWLIST_OWNER.fullmatch(entry["owner"]) is None:
        raise GateError("allowlist_owner_invalid")

    reason = entry["reason"]
    if (
        not reason
        or len(reason) > 1000
        or reason.strip() != reason
        or not reason.isprintable()
    ):
        raise GateError("allowlist_reason_invalid")
    try:
        expires_on = date.fromisoformat(entry["expires_on"])
    except ValueError as exc:
        raise GateError("allowlist_expiry_invalid") from exc
    if expires_on.isoformat() != entry["expires_on"]:
        raise GateError("allowlist_expiry_invalid")
    if expires_on < date.today():
        raise GateError("allowlist_entry_expired")


def _git(repo_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise GateError("git_command_failed")
    return completed.stdout


def _tree_entries(repo_root: Path, treeish: str) -> list[tuple[str, str]]:
    if treeish.startswith("-") or REVISION_EXPRESSION.fullmatch(treeish) is None:
        raise GateError("invalid_revision_expression")
    output = _git(repo_root, "ls-tree", "-r", "-z", "--full-tree", treeish, "--")
    entries: list[tuple[str, str]] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            _mode, object_type, raw_oid = metadata.split(b" ", 2)
            path = raw_path.decode("utf-8")
            oid = raw_oid.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise GateError("tree_entry_parse_failed") from exc
        if object_type == b"blob":
            entries.append((path, oid))
    return entries


def _range_entries(repo_root: Path, revision_range: str) -> list[tuple[str, str]]:
    if revision_range.startswith("-") or REVISION_EXPRESSION.fullmatch(revision_range) is None:
        raise GateError("invalid_revision_expression")
    commits = _git(
        repo_root,
        "rev-list",
        "--reverse",
        "--topo-order",
        revision_range,
        "--",
    ).splitlines()
    entries: list[tuple[str, str]] = []
    for raw_commit in commits:
        try:
            commit = raw_commit.decode("ascii")
        except UnicodeDecodeError as exc:
            raise GateError("commit_oid_parse_failed") from exc
        entries.extend(_tree_entries(repo_root, commit))
    return entries


def _history_entries(repo_root: Path, refs: Sequence[str]) -> list[tuple[str, str]]:
    for ref in refs:
        if ref.startswith("-") or REVISION_EXPRESSION.fullmatch(ref) is None:
            raise GateError("invalid_revision_expression")
    raw_commits = _git(
        repo_root,
        "rev-list",
        "--reverse",
        "--topo-order",
        *refs,
        "--",
    ).splitlines()
    entries: set[tuple[str, str]] = set()
    for raw_commit in raw_commits:
        if OBJECT_OID.fullmatch(raw_commit) is None:
            raise GateError("history_commit_oid_parse_failed")
        entries.update(_tree_entries(repo_root, raw_commit.decode("ascii")))
    return sorted(entries)


def _history_ref_inventory(
    repo_root: Path,
    explicit_refs: Sequence[str],
    refs_file: Path | None,
    expected_ref_count: int | None,
) -> list[str]:
    refs = list(explicit_refs)
    if refs_file is not None:
        inventory_path = refs_file if refs_file.is_absolute() else repo_root / refs_file
        try:
            lines = inventory_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise GateError("history_ref_inventory_read_failed") from exc
        if any(not line or line != line.strip() for line in lines):
            raise GateError("history_ref_inventory_parse_failed")
        refs.extend(lines)

    unique_refs = set(refs)
    if (
        expected_ref_count is None
        or expected_ref_count < 1
        or len(refs) != expected_ref_count
        or len(unique_refs) != expected_ref_count
    ):
        raise GateError("history_ref_inventory_incomplete")
    return sorted(unique_refs)


def _staged_entries(repo_root: Path) -> list[tuple[str, str]]:
    output = _git(repo_root, "ls-files", "--cached", "--stage", "-z")
    entries: list[tuple[str, str]] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            _mode, raw_oid, raw_stage = metadata.split(b" ", 2)
            path = raw_path.decode("utf-8")
            oid = raw_oid.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise GateError("index_entry_parse_failed") from exc
        if raw_stage != b"0":
            raise GateError("unmerged_index_entry")
        entries.append((path, oid))
    return entries


def _fingerprint(rule: str, path: str, blob_oid: str, line: int | None) -> str:
    canonical = f"{rule}\0{path}\0{blob_oid}\0{line or 0}".encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _finding(
    *, rule: str, path: str, blob_oid: str, line: int | None = None
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "rule": rule,
        "path": path,
        "blob_oid": blob_oid,
        "fingerprint": _fingerprint(rule, path, blob_oid, line),
    }
    if line is not None:
        finding["line"] = line
    return finding


def _line_number(payload: bytes, offset: int) -> int:
    return payload.count(b"\n", 0, offset) + 1


def _is_sanctioned_ci_credential(payload: bytes, match: re.Match[bytes]) -> bool:
    """僅當 password 捕獲值與 match 起點所在行的 user token 都 exact 命中
    sanctioned ephemeral CI 憑證對時才豁免；其餘一律維持 shape-based 拒絕。"""
    if match.group("password") != SANCTIONED_CI_PASSWORD_VALUE:
        return False
    line_start = payload.rfind(b"\n", 0, match.start()) + 1
    line_end = payload.find(b"\n", match.end())
    if line_end == -1:
        line_end = len(payload)
    return SANCTIONED_CI_USER_TOKEN in payload[line_start:line_end]


def _load_allowlist(repo_root: Path, allowlist_file: Path) -> list[dict[str, Any]]:
    path = allowlist_file if allowlist_file.is_absolute() else repo_root / allowlist_file
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError("allowlist_read_failed") from exc
    if not isinstance(payload, dict):
        raise GateError("allowlist_schema_invalid")
    if set(payload) != {"schema_version", "entries"}:
        raise GateError("allowlist_top_level_fields_invalid")
    if payload.get("schema_version") != ALLOWLIST_SCHEMA_VERSION:
        raise GateError("allowlist_schema_version_invalid")
    entries = payload.get("entries")
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise GateError("allowlist_entries_invalid")
    if any(set(entry) != ALLOWLIST_ENTRY_FIELDS for entry in entries):
        raise GateError("allowlist_entry_fields_invalid")
    for entry in entries:
        _validate_allowlist_entry(entry)
    fingerprints = [entry["fingerprint"] for entry in entries]
    if len(fingerprints) != len(set(fingerprints)):
        raise GateError("allowlist_duplicate_fingerprint")
    return entries


def _apply_allowlist(
    findings: Sequence[dict[str, Any]], entries: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    remaining = list(findings)
    for entry in entries:
        for index, finding in enumerate(remaining):
            if all(entry.get(field) == finding.get(field) for field in ("fingerprint", "rule", "path")):
                remaining.pop(index)
                break
        else:
            raise GateError("allowlist_entry_unused_or_scope_mismatch")
    return remaining


def _blob_payloads(
    repo_root: Path, blob_oids: Sequence[str]
) -> Iterator[tuple[str, bytes]]:
    """以單一 batch process 讀 blob，避免完整 tree 產生數千個 subprocess。"""

    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if process.stdin is None or process.stdout is None:
        raise GateError("cat_file_pipe_unavailable")
    try:
        for oid in blob_oids:
            process.stdin.write(oid.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline()
            try:
                reported_oid, object_type, raw_size = header.rstrip(b"\n").split(b" ")
                size = int(raw_size)
            except (TypeError, ValueError) as exc:
                raise GateError("cat_file_header_parse_failed") from exc
            if reported_oid.decode("ascii") != oid or object_type != b"blob" or size < 0:
                raise GateError("cat_file_object_mismatch")
            payload = process.stdout.read(size)
            terminator = process.stdout.read(1)
            if len(payload) != size or terminator != b"\n":
                raise GateError("cat_file_payload_truncated")
            yield oid, payload
    finally:
        process.stdin.close()
        process.stdout.close()
        return_code = process.wait()
    if return_code != 0:
        raise GateError("cat_file_batch_failed")


def scan_entries(
    repo_root: Path, entries: Sequence[tuple[str, str]]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    paths_by_oid: dict[str, list[str]] = {}
    for path, blob_oid in sorted(set(entries)):
        paths_by_oid.setdefault(blob_oid, []).append(path)
        if path.casefold().endswith(DATABASE_ARTIFACT_SUFFIXES):
            findings.append(
                _finding(
                    rule="tracked_database_artifact",
                    path=path,
                    blob_oid=blob_oid,
                )
            )

    for blob_oid, payload in _blob_payloads(repo_root, sorted(paths_by_oid)):
        for path in paths_by_oid[blob_oid]:
            for magic, rule in (
                (POSTGRES_DUMP_MAGIC, "postgres_dump_magic"),
                (SQLITE_DATABASE_MAGIC, "sqlite_database_magic"),
            ):
                if payload.startswith(magic):
                    findings.append(
                        _finding(rule=rule, path=path, blob_oid=blob_oid, line=1)
                    )
            for pattern, rule in (
                (PRIVATE_KEY_HEADER, "private_key_header"),
                (PROVIDER_TOKEN, "provider_token"),
                (JWT_TOKEN, "jwt_token"),
            ):
                for match in pattern.finditer(payload):
                    findings.append(
                        _finding(
                            rule=rule,
                            path=path,
                            blob_oid=blob_oid,
                            line=_line_number(payload, match.start()),
                        )
                    )
            for match in EMBEDDED_CREDENTIAL_DSN.finditer(payload):
                findings.append(
                    _finding(
                        rule="embedded_credential_dsn",
                        path=path,
                        blob_oid=blob_oid,
                        line=_line_number(payload, match.start()),
                    )
                )
            # query / keyword 兩類新變體沿用同一 rule 名；每個 match 先過
            # sanctioned CI 憑證對 carve-out 再 emit（authority 形無 carve-out）。
            for variant in EMBEDDED_CREDENTIAL_DSN_VARIANTS:
                for match in variant.finditer(payload):
                    if _is_sanctioned_ci_credential(payload, match):
                        continue
                    findings.append(
                        _finding(
                            rule="embedded_credential_dsn",
                            path=path,
                            blob_oid=blob_oid,
                            line=_line_number(payload, match.start()),
                        )
                    )
    ordered_findings = sorted(
        findings,
        key=lambda finding: (
            str(finding["path"]),
            int(finding.get("line", 0)),
            str(finding["rule"]),
            str(finding["blob_oid"]),
        ),
    )
    unique_findings: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()
    for finding in ordered_findings:
        fingerprint = str(finding["fingerprint"])
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)
        unique_findings.append(finding)
    return unique_findings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--tree", action="append", default=[])
    parser.add_argument("--range", dest="revision_ranges", action="append", default=[])
    parser.add_argument("--history-ref", action="append", default=[])
    parser.add_argument("--history-refs-file", type=Path)
    parser.add_argument("--expected-ref-count", type=int)
    parser.add_argument("--allowlist-file", type=Path)
    parser.add_argument("--staged", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if (
        not args.tree
        and not args.revision_ranges
        and not args.history_ref
        and args.history_refs_file is None
        and not args.staged
    ):
        print("[public-repo-security-gate][ERROR] scan mode required", file=sys.stderr)
        return 2
    try:
        repo_root = args.repo_root.resolve(strict=True)
        entries: list[tuple[str, str]] = []
        for treeish in args.tree:
            entries.extend(_tree_entries(repo_root, treeish))
        for revision_range in args.revision_ranges:
            entries.extend(_range_entries(repo_root, revision_range))
        if args.history_ref or args.history_refs_file is not None:
            history_refs = _history_ref_inventory(
                repo_root,
                args.history_ref,
                args.history_refs_file,
                args.expected_ref_count,
            )
            entries.extend(_history_entries(repo_root, history_refs))
        elif args.expected_ref_count is not None:
            raise GateError("history_ref_inventory_missing")
        if args.staged:
            entries.extend(_staged_entries(repo_root))
        findings = scan_entries(repo_root, entries)
        allowlist_file = args.allowlist_file or DEFAULT_ALLOWLIST_FILE
        findings = _apply_allowlist(
            findings,
            _load_allowlist(repo_root, allowlist_file),
        )
    except (GateError, OSError):
        print("[public-repo-security-gate][ERROR] scan failed closed", file=sys.stderr)
        return 2

    for finding in findings:
        print(json.dumps(finding, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Fail-closed guard for already-applied SQL migration bytes.

用途：
  - 用 repo 內 manifest 鎖住已套用到 runtime 的 V### migration SHA-384。
  - CI / pre-commit 若偵測到已鎖定 migration bytes 或舊 manifest 條目被改，直接失敗。

邊界：
  - 純本地檔案 / git metadata 檢查；不連 DB、不讀 secret、不執行 migration。
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


MIGRATION_RE = re.compile(r"^V(?P<version>\d{3})__(?P<description>.+)\.sql$")
DEFAULT_MANIFEST = Path("sql/migrations/applied_checksums.sha384")
DEFAULT_MIGRATIONS_DIR = Path("sql/migrations")


@dataclasses.dataclass(frozen=True)
class ManifestEntry:
    version: int
    file_name: str
    sha384: str


@dataclasses.dataclass(frozen=True)
class ChangedRecord:
    status: str
    paths: tuple[str, ...]


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def migration_version(file_name: str) -> int | None:
    match = MIGRATION_RE.match(Path(file_name).name)
    if not match:
        return None
    return int(match.group("version"))


def sha384_file(path: Path) -> str:
    h = hashlib.sha384()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def list_migration_files(migrations_dir: Path) -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for path in migrations_dir.iterdir():
        if not path.is_file():
            continue
        version = migration_version(path.name)
        if version is None:
            continue
        out.append((version, path))
    out.sort(key=lambda item: (item[0], item[1].name))
    return out


def parse_manifest_text(text: str, source: str) -> tuple[int, dict[int, ManifestEntry]]:
    entries: dict[int, ManifestEntry] = {}
    max_applied_version: int | None = None
    seen_files: set[str] = set()

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("# max_applied_version="):
                value = line.split("=", 1)[1]
                try:
                    max_applied_version = int(value)
                except ValueError as exc:
                    raise ValueError(
                        f"{source}:{lineno}: invalid max_applied_version {value!r}"
                    ) from exc
            continue

        parts = raw_line.split("\t")
        if len(parts) != 3:
            raise ValueError(f"{source}:{lineno}: expected 3 tab-separated fields")
        sha, version_s, file_name = parts
        if not re.fullmatch(r"[0-9a-f]{96}", sha):
            raise ValueError(f"{source}:{lineno}: invalid sha384 hex")
        try:
            version = int(version_s)
        except ValueError as exc:
            raise ValueError(f"{source}:{lineno}: invalid version {version_s!r}") from exc
        actual_version = migration_version(file_name)
        if actual_version != version:
            raise ValueError(
                f"{source}:{lineno}: file {file_name!r} does not match version {version}"
            )
        if version in entries:
            raise ValueError(f"{source}:{lineno}: duplicate version {version}")
        if file_name in seen_files:
            raise ValueError(f"{source}:{lineno}: duplicate file {file_name}")
        seen_files.add(file_name)
        entries[version] = ManifestEntry(version=version, file_name=file_name, sha384=sha)

    if max_applied_version is None:
        if not entries:
            raise ValueError(f"{source}: empty manifest")
        max_applied_version = max(entries)
    if entries and max(entries) > max_applied_version:
        raise ValueError(
            f"{source}: manifest contains V{max(entries):03d} above "
            f"max_applied_version V{max_applied_version:03d}"
        )
    return max_applied_version, entries


def load_manifest(path: Path) -> tuple[int, dict[int, ManifestEntry]]:
    return parse_manifest_text(path.read_text(encoding="utf-8"), str(path))


def render_manifest(entries: Iterable[ManifestEntry], max_applied_version: int) -> str:
    lines = [
        "# OpenClaw applied SQL migration checksum lock v1",
        "# 此檔鎖定已套用到 runtime 的 migration bytes；已鎖定檔案不得再改 header/comment/body。",
        "# 若需要更正，新增下一個 V### migration 或先走 operator-approved DB ledger repair。",
        f"# max_applied_version={max_applied_version}",
        "# sha384\tversion\tfile_name",
    ]
    for entry in sorted(entries, key=lambda e: (e.version, e.file_name)):
        lines.append(f"{entry.sha384}\t{entry.version}\t{entry.file_name}")
    return "\n".join(lines) + "\n"


def write_manifest(manifest: Path, migrations_dir: Path, max_version: int) -> None:
    entries: list[ManifestEntry] = []
    seen_versions: dict[int, str] = {}
    for version, path in list_migration_files(migrations_dir):
        if version > max_version:
            continue
        if version in seen_versions:
            raise SystemExit(
                f"FAIL: duplicate migration version V{version:03d}: "
                f"{seen_versions[version]} and {path.name}"
            )
        seen_versions[version] = path.name
        entries.append(ManifestEntry(version=version, file_name=path.name, sha384=sha384_file(path)))

    if not entries:
        raise SystemExit("FAIL: no migration files found for manifest")
    manifest.write_text(render_manifest(entries, max_version), encoding="utf-8")
    print(f"OK: wrote {manifest} with {len(entries)} locked migrations up to V{max_version:03d}")


def check_manifest(manifest: Path, migrations_dir: Path) -> list[str]:
    max_version, entries = load_manifest(manifest)
    failures: list[str] = []

    seen_versions: dict[int, str] = {}
    for version, path in list_migration_files(migrations_dir):
        if version > max_version:
            continue
        if version in seen_versions:
            failures.append(
                f"duplicate migration version V{version:03d}: {seen_versions[version]} and {path.name}"
            )
        seen_versions[version] = path.name
        if version not in entries:
            failures.append(
                f"V{version:03d} {path.name} is <= manifest max V{max_version:03d} but is not locked"
            )

    for version, entry in sorted(entries.items()):
        path = migrations_dir / entry.file_name
        if not path.exists():
            failures.append(f"V{version:03d} locked file missing: {entry.file_name}")
            continue
        actual = sha384_file(path)
        if actual != entry.sha384:
            failures.append(
                f"V{version:03d} {entry.file_name} checksum drift: "
                f"manifest={entry.sha384} actual={actual}"
            )

    return failures


def run_git(repo_root: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_text(repo_root: Path, spec: str) -> str:
    cp = run_git(repo_root, ["show", spec])
    return cp.stdout


def git_manifest(repo_root: Path, ref: str, manifest_rel: str) -> tuple[int, dict[int, ManifestEntry]]:
    text = git_text(repo_root, f"{ref}:{manifest_rel}")
    return parse_manifest_text(text, f"{ref}:{manifest_rel}")


def git_manifest_or_empty(
    repo_root: Path, ref: str, manifest_rel: str
) -> tuple[int, dict[int, ManifestEntry]]:
    cp = run_git(repo_root, ["show", f"{ref}:{manifest_rel}"], check=False)
    if cp.returncode != 0:
        return 0, {}
    return parse_manifest_text(cp.stdout, f"{ref}:{manifest_rel}")


def merge_base(repo_root: Path, ref: str) -> str:
    cp = run_git(repo_root, ["merge-base", ref, "HEAD"])
    return cp.stdout.strip()


def parse_name_status_z(raw: str) -> list[ChangedRecord]:
    parts = raw.split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    out: list[ChangedRecord] = []
    i = 0
    while i < len(parts):
        status = parts[i]
        i += 1
        if status.startswith(("R", "C")):
            if i + 1 >= len(parts):
                raise ValueError("malformed git name-status -z output")
            out.append(ChangedRecord(status=status, paths=(parts[i], parts[i + 1])))
            i += 2
        else:
            if i >= len(parts):
                raise ValueError("malformed git name-status -z output")
            out.append(ChangedRecord(status=status, paths=(parts[i],)))
            i += 1
    return out


def changed_records_since(repo_root: Path, base_ref: str) -> tuple[str, list[ChangedRecord]]:
    base = merge_base(repo_root, base_ref)
    cp = run_git(
        repo_root,
        ["diff", "--name-status", "--find-renames", "-z", f"{base}..HEAD", "--", "sql/migrations"],
    )
    return base, parse_name_status_z(cp.stdout)


def staged_records(repo_root: Path) -> list[ChangedRecord]:
    cp = run_git(
        repo_root,
        ["diff", "--cached", "--name-status", "--find-renames", "-z", "--", "sql/migrations"],
    )
    return parse_name_status_z(cp.stdout)


def staged_manifest(repo_root: Path, manifest_rel: str) -> tuple[int, dict[int, ManifestEntry]] | None:
    cp = run_git(repo_root, ["show", f":{manifest_rel}"], check=False)
    if cp.returncode != 0:
        return None
    return parse_manifest_text(cp.stdout, f":{manifest_rel}")


def diff_guard_failures(
    records: Iterable[ChangedRecord],
    old_max_version: int,
    old_entries: dict[int, ManifestEntry],
    new_entries: dict[int, ManifestEntry] | None,
    manifest_rel: str,
) -> list[str]:
    failures: list[str] = []
    old_locked_paths = {f"sql/migrations/{entry.file_name}" for entry in old_entries.values()}

    for record in records:
        for path in record.paths:
            if path == manifest_rel:
                continue
            if not path.startswith("sql/migrations/"):
                continue
            version = migration_version(path)
            if version is None:
                continue
            if path in old_locked_paths or version <= old_max_version:
                failures.append(
                    f"{record.status} changes locked/applied migration {path} "
                    f"(V{version:03d} <= locked max V{old_max_version:03d})"
                )

    if new_entries is not None:
        for version, old_entry in sorted(old_entries.items()):
            new_entry = new_entries.get(version)
            if new_entry is None:
                failures.append(f"manifest removed locked V{version:03d} {old_entry.file_name}")
                continue
            if new_entry != old_entry:
                failures.append(
                    f"manifest changed locked V{version:03d}: "
                    f"{old_entry.file_name}/{old_entry.sha384} -> "
                    f"{new_entry.file_name}/{new_entry.sha384}"
                )
    return failures


def print_failures(failures: list[str]) -> int:
    if not failures:
        print("OK: applied migration checksum guard passed")
        return 0
    print("FAIL: applied migration checksum guard blocked drift", file=sys.stderr)
    for failure in failures:
        print(f" - {failure}", file=sys.stderr)
    print(
        "\n已套用 migration bytes 不可再改。需要修正時請新增下一個 V### migration；"
        "若是既有事故修復，必須先有 operator-approved repair_migration_checksum 流程。",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--migrations-dir", default=str(DEFAULT_MIGRATIONS_DIR))
    parser.add_argument("--write", action="store_true", help="rewrite manifest from current files")
    parser.add_argument("--max-version", type=int, help="required with --write")
    parser.add_argument("--git-diff-base", help="fail if this branch changes already-locked migrations")
    parser.add_argument("--staged", action="store_true", help="fail on staged changes to locked migrations")
    args = parser.parse_args(argv)

    repo_root = repo_root_from_script()
    manifest = (repo_root / args.manifest).resolve()
    migrations_dir = (repo_root / args.migrations_dir).resolve()
    manifest_rel = os.path.relpath(manifest, repo_root)

    if args.write:
        if args.max_version is None:
            raise SystemExit("--write requires --max-version")
        write_manifest(manifest, migrations_dir, args.max_version)
        return 0

    failures = check_manifest(manifest, migrations_dir)

    if args.git_diff_base:
        try:
            base, records = changed_records_since(repo_root, args.git_diff_base)
            old_max, old_entries = git_manifest_or_empty(repo_root, base, manifest_rel)
            _, new_entries = load_manifest(manifest)
            failures.extend(
                diff_guard_failures(records, old_max, old_entries, new_entries, manifest_rel)
            )
        except Exception as exc:  # fail closed for git/manifest ambiguity
            failures.append(f"git diff guard failed closed: {exc}")

    if args.staged:
        try:
            records = staged_records(repo_root)
            old_max, old_entries = git_manifest_or_empty(repo_root, "HEAD", manifest_rel)
            staged = staged_manifest(repo_root, manifest_rel)
            new_entries = staged[1] if staged is not None else None
            failures.extend(
                diff_guard_failures(records, old_max, old_entries, new_entries, manifest_rel)
            )
        except Exception as exc:
            failures.append(f"staged guard failed closed: {exc}")

    return print_failures(failures)


if __name__ == "__main__":
    raise SystemExit(main())

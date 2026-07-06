from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_applied_migration_checksums.py")
SPEC = importlib.util.spec_from_file_location("check_applied_migration_checksums", SCRIPT)
guard = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = guard
SPEC.loader.exec_module(guard)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return cp.stdout.strip()


def _init_git_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Migration Guard Test")


def _write_lock(repo: Path, max_version: int) -> None:
    guard.write_manifest(
        repo / "sql/migrations/applied_checksums.sha384",
        repo / "sql/migrations",
        max_version,
    )


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _diff_failures(repo: Path, base: str) -> list[str]:
    compare_base, records = guard.changed_records_since(repo, base)
    old_max, old_entries = guard.git_manifest(
        repo, compare_base, "sql/migrations/applied_checksums.sha384"
    )
    _, new_entries = guard.load_manifest(repo / "sql/migrations/applied_checksums.sha384")
    return guard.diff_guard_failures(
        records,
        old_max,
        old_entries,
        new_entries,
        "sql/migrations/applied_checksums.sha384",
    )


def test_manifest_check_blocks_comment_only_byte_drift(tmp_path: Path) -> None:
    migrations = tmp_path / "sql/migrations"
    manifest = migrations / "applied_checksums.sha384"
    _write(migrations / "V001__create_schemas.sql", "CREATE SCHEMA IF NOT EXISTS market;\n")
    _write_lock(tmp_path, 1)

    assert guard.check_manifest(manifest, migrations) == []

    with (migrations / "V001__create_schemas.sql").open("a", encoding="utf-8") as f:
        f.write("-- comment-only drift still changes sqlx checksum\n")

    failures = guard.check_manifest(manifest, migrations)
    assert any("checksum drift" in item for item in failures)


def test_git_diff_guard_blocks_locked_file_even_if_manifest_is_updated(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    migrations = repo / "sql/migrations"
    _write(migrations / "V001__create_schemas.sql", "CREATE SCHEMA IF NOT EXISTS market;\n")
    _write_lock(repo, 1)
    base = _commit_all(repo, "initial lock")

    with (migrations / "V001__create_schemas.sql").open("a", encoding="utf-8") as f:
        f.write("-- forbidden header tweak\n")
    _write_lock(repo, 1)
    _commit_all(repo, "bad migration edit")

    failures = _diff_failures(repo, base)
    assert any("locked/applied migration" in item for item in failures)
    assert any("manifest changed locked V001" in item for item in failures)


def test_git_diff_guard_allows_new_future_migration_and_new_lock_entry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    migrations = repo / "sql/migrations"
    _write(migrations / "V001__create_schemas.sql", "CREATE SCHEMA IF NOT EXISTS market;\n")
    _write_lock(repo, 1)
    base = _commit_all(repo, "initial lock")

    _write(migrations / "V002__future_additive.sql", "CREATE TABLE market.future(id BIGINT);\n")
    _write_lock(repo, 2)
    _commit_all(repo, "add future migration")

    assert guard.check_manifest(migrations / "applied_checksums.sha384", migrations) == []
    assert _diff_failures(repo, base) == []


def test_staged_guard_blocks_staged_locked_migration(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    migrations = repo / "sql/migrations"
    _write(migrations / "V001__create_schemas.sql", "CREATE SCHEMA IF NOT EXISTS market;\n")
    _write_lock(repo, 1)
    _commit_all(repo, "initial lock")

    with (migrations / "V001__create_schemas.sql").open("a", encoding="utf-8") as f:
        f.write("-- staged forbidden drift\n")
    _git(repo, "add", "sql/migrations/V001__create_schemas.sql")

    records = guard.staged_records(repo)
    old_max, old_entries = guard.git_manifest(
        repo, "HEAD", "sql/migrations/applied_checksums.sha384"
    )
    failures = guard.diff_guard_failures(
        records,
        old_max,
        old_entries,
        None,
        "sql/migrations/applied_checksums.sha384",
    )
    assert any("locked/applied migration" in item for item in failures)

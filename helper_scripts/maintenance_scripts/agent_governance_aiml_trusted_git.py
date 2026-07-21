"""Bounded immutable-Git verification for S0.3 Program adoption."""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from agent_governance_aiml_trusted_common import DIGEST_RE, HEAD_RE


REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_EXECUTABLE = "/usr/bin/git"
MAX_MANIFEST_PATHS = 512
MAX_BLOB_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_GIT_METADATA_BYTES = 1024 * 1024
MAX_GIT_STDERR_BYTES = 64 * 1024


class GitRunner(Protocol):
    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[bytes]: ...


class GitSourceManifestVerifier:
    """Verify ancestry and exact manifest bytes from an immutable Git tree."""

    def __init__(
        self,
        repo: Path = REPO_ROOT,
        *,
        runner: GitRunner | None = None,
    ) -> None:
        self.repo = repo.resolve(strict=True)
        self._runner = runner or self._run_git

    def _run_git(self, argv: list[str]) -> subprocess.CompletedProcess[bytes]:
        env = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
        }
        command = [
            GIT_EXECUTABLE,
            "-c", "core.fsmonitor=false",
            "-c", "core.hooksPath=/dev/null",
            *argv,
        ]
        # File-backed capture keeps a malformed or oversized object from being
        # allocated without bound before the caller can enforce its byte cap.
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            completed = subprocess.run(
                command,
                cwd=self.repo,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=15,
                check=False,
            )
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read(MAX_BLOB_BYTES + 1)
            stderr = stderr_file.read(MAX_GIT_STDERR_BYTES + 1)
        return subprocess.CompletedProcess(
            args=command,
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    @staticmethod
    def _safe_path(value: Any) -> str:
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise ValueError("manifest path is invalid")
        if (
            value.startswith(":")
            or "\\" in value
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("manifest path is unsafe")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("manifest path is unsafe")
        return value

    def _ok(
        self,
        argv: list[str],
        *,
        empty: bool = False,
        max_bytes: int = MAX_GIT_METADATA_BYTES,
    ) -> bytes:
        result = self._runner(argv)
        if result.returncode != 0:
            raise ValueError("trusted Git command failed")
        if len(result.stdout) > max_bytes:
            raise ValueError("trusted Git command output exceeds size limit")
        if empty and result.stdout.strip():
            raise ValueError("trusted Git repository has forbidden state")
        return result.stdout

    def _repository_safety(self) -> None:
        top_level = self._ok(["rev-parse", "--show-toplevel"]).decode().strip()
        if Path(top_level).resolve(strict=True) != self.repo:
            raise ValueError("trusted Git repository root mismatch")
        if self._ok(["rev-parse", "--is-shallow-repository"]).strip() != b"false":
            raise ValueError("shallow repositories are not trusted for adoption")
        self._ok(["replace", "-l"], empty=True)
        for pattern in (r"^remote\..*\.promisor$", r"^extensions\.partialClone$"):
            result = self._runner(["config", "--get-regexp", pattern])
            if result.returncode == 0 and result.stdout.strip():
                raise ValueError("partial/promisor repositories are not trusted")
            if result.returncode not in {0, 1}:
                raise ValueError("trusted Git config inspection failed")
        for relative in ("info/grafts", "objects/info/alternates"):
            raw_path = self._ok(["rev-parse", "--git-path", relative]).decode().strip()
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = self.repo / candidate
            if candidate.is_symlink():
                raise ValueError("trusted Git repository has grafts or alternates")
            if candidate.exists() and candidate.stat().st_size:
                raise ValueError("trusted Git repository has grafts or alternates")

    def _verify(
        self,
        reviewed_head: str,
        merge_head: str,
        manifest: dict[str, str],
    ) -> None:
        if not HEAD_RE.fullmatch(reviewed_head) or not HEAD_RE.fullmatch(merge_head):
            raise ValueError("source heads must be exact commit ids")
        if not isinstance(manifest, dict) or not manifest or len(manifest) > MAX_MANIFEST_PATHS:
            raise ValueError("source manifest cardinality is invalid")
        self._repository_safety()
        self._ok(["cat-file", "-e", f"{reviewed_head}^{{commit}}"])
        self._ok(["cat-file", "-e", f"{merge_head}^{{commit}}"])
        ancestor = self._runner(["merge-base", "--is-ancestor", reviewed_head, merge_head])
        if ancestor.returncode != 0:
            raise ValueError("reviewed head is not an ancestor of merge head")

        total = 0
        for raw_path, expected_digest in sorted(manifest.items()):
            path = self._safe_path(raw_path)
            if not DIGEST_RE.fullmatch(str(expected_digest)):
                raise ValueError("source manifest digest is invalid")
            listing = self._ok(["ls-tree", "-z", merge_head, "--", path])
            records = [item for item in listing.split(b"\0") if item]
            if len(records) != 1:
                raise ValueError("source manifest path does not resolve exactly once")
            try:
                metadata, returned_path = records[0].split(b"\t", 1)
                mode, object_type, object_id = metadata.split(b" ", 2)
            except ValueError as error:
                raise ValueError("source manifest tree record is invalid") from error
            if returned_path.decode("utf-8") != path:
                raise ValueError("source manifest tree path mismatch")
            if mode not in {b"100644", b"100755"} or object_type != b"blob":
                raise ValueError("source manifest path is not a regular blob")
            object_name = object_id.decode("ascii")
            size_raw = self._ok(["cat-file", "-s", object_name]).strip()
            try:
                blob_size = int(size_raw)
            except ValueError as error:
                raise ValueError("source manifest blob size is invalid") from error
            if blob_size < 0 or blob_size > MAX_BLOB_BYTES:
                raise ValueError("source manifest blobs exceed size limit")
            total += blob_size
            if total > MAX_MANIFEST_BYTES:
                raise ValueError("source manifest blobs exceed size limit")
            blob = self._ok(
                ["cat-file", "blob", object_name], max_bytes=blob_size
            )
            if len(blob) != blob_size:
                raise ValueError("source manifest blob size changed")
            actual = "sha256:" + hashlib.sha256(blob).hexdigest()
            if not hmac.compare_digest(actual, str(expected_digest)):
                raise ValueError("source manifest blob digest mismatch")

    def __call__(
        self,
        reviewed_head: str,
        merge_head: str,
        manifest: dict[str, str],
    ) -> bool:
        try:
            self._verify(reviewed_head, merge_head, manifest)
            return True
        except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
            return False

"""Receipt-free, repository-only source readiness for one S2E wave.

``SOURCE_READY`` means only that every manifest path is a regular blob in one
exact commit tree.  It is deliberately disconnected from launch receipts,
external attestation, package landing, closure, authority, and effects.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import subprocess
import unicodedata
from typing import Any, Literal, Sequence

from aiml_gate_receipt_schema_core import git_argv, git_subprocess_env


_COMMIT_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_REGULAR_BLOB_MODES = frozenset({"100644", "100755"})


class S2EWaveSourceReadinessStatus(str, Enum):
    SOURCE_READY = "SOURCE_READY"
    SOURCE_INCOMPLETE = "SOURCE_INCOMPLETE"


class S2EWaveSourceDiagnosticCode(str, Enum):
    INVALID_REPO_ROOT = "INVALID_REPO_ROOT"
    REPO_ROOT_NOT_TOP_LEVEL = "REPO_ROOT_NOT_TOP_LEVEL"
    INVALID_WAVE = "INVALID_WAVE"
    EMPTY_MANIFEST = "EMPTY_MANIFEST"
    INVALID_MANIFEST_ENTRY = "INVALID_MANIFEST_ENTRY"
    INVALID_GENERATION = "INVALID_GENERATION"
    MIXED_GENERATION = "MIXED_GENERATION"
    INVALID_PATH = "INVALID_PATH"
    DUPLICATE_PATH = "DUPLICATE_PATH"
    INVALID_COMMIT = "INVALID_COMMIT"
    GIT_TREE_UNREADABLE = "GIT_TREE_UNREADABLE"
    MISSING_PATH = "MISSING_PATH"
    NON_REGULAR_BLOB = "NON_REGULAR_BLOB"
    UNREADABLE_BLOB = "UNREADABLE_BLOB"


@dataclass(frozen=True)
class S2EWaveOwnedSource:
    path: str
    expected_generation: str


@dataclass(frozen=True)
class S2EWaveSourceDiagnostic:
    code: S2EWaveSourceDiagnosticCode
    path: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class S2EWaveSourceReadiness:
    status: S2EWaveSourceReadinessStatus
    wave: str
    generation: str | None
    owned_paths: tuple[str, ...]
    diagnostics: tuple[S2EWaveSourceDiagnostic, ...]

    @property
    def external_attested(self) -> Literal[False]:
        """This source-only predicate can never attest an external fact."""

        return False


def _diagnostic_key(
    diagnostic: S2EWaveSourceDiagnostic,
) -> tuple[str, str, str]:
    return (
        diagnostic.code.value,
        diagnostic.path or "",
        diagnostic.detail or "",
    )


def _result(
    *,
    wave: Any,
    generation: str | None,
    owned_paths: Sequence[str],
    diagnostics: Sequence[S2EWaveSourceDiagnostic],
) -> S2EWaveSourceReadiness:
    ordered = tuple(sorted(set(diagnostics), key=_diagnostic_key))
    return S2EWaveSourceReadiness(
        status=(
            S2EWaveSourceReadinessStatus.SOURCE_INCOMPLETE
            if ordered
            else S2EWaveSourceReadinessStatus.SOURCE_READY
        ),
        wave=wave if isinstance(wave, str) else "",
        generation=generation,
        owned_paths=tuple(sorted(set(owned_paths))),
        diagnostics=ordered,
    )


def _git_env() -> dict[str, str]:
    environment = git_subprocess_env()
    environment["GIT_NO_LAZY_FETCH"] = "1"
    return environment


def _git(
    repo_root: Path, *arguments: str, text: bool = True
) -> subprocess.CompletedProcess[Any] | None:
    try:
        return subprocess.run(
            git_argv(repo_root, *arguments),
            capture_output=True,
            env=_git_env(),
            text=text,
            timeout=60,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _canonical_owned_path(path: Any) -> bool:
    if not isinstance(path, str) or not path or "\\" in path:
        return False
    if unicodedata.normalize("NFC", path) != path:
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        return False
    if path.startswith("/") or ":" in path.split("/", 1)[0]:
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _resolved_top_level(
    repo_root: Any,
) -> tuple[Path | None, S2EWaveSourceDiagnostic | None]:
    try:
        root = Path(repo_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return None, S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.INVALID_REPO_ROOT
        )
    if not root.is_dir():
        return None, S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.INVALID_REPO_ROOT
        )
    probe = _git(root, "rev-parse", "--show-toplevel")
    if probe is None or probe.returncode != 0:
        return None, S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.INVALID_REPO_ROOT
        )
    try:
        top_level = Path(probe.stdout.strip()).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None, S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.INVALID_REPO_ROOT
        )
    if top_level != root:
        return None, S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.REPO_ROOT_NOT_TOP_LEVEL
        )
    return root, None


def s2e_wave_source_readiness_v1(
    *,
    repo_root: Path,
    wave: str,
    owned_source_manifest: Sequence[S2EWaveOwnedSource],
) -> S2EWaveSourceReadiness:
    """Classify structural source existence at one exact commit generation."""

    diagnostics: list[S2EWaveSourceDiagnostic] = []
    if not isinstance(wave, str) or not wave.strip() or wave != wave.strip():
        diagnostics.append(S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.INVALID_WAVE
        ))

    try:
        entries = tuple(owned_source_manifest)
    except TypeError:
        entries = ()
        diagnostics.append(S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.INVALID_MANIFEST_ENTRY
        ))
    if not entries:
        diagnostics.append(S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.EMPTY_MANIFEST
        ))

    paths: list[str] = []
    generations: list[str] = []
    for entry in entries:
        if not isinstance(entry, S2EWaveOwnedSource):
            diagnostics.append(S2EWaveSourceDiagnostic(
                S2EWaveSourceDiagnosticCode.INVALID_MANIFEST_ENTRY
            ))
            continue
        if isinstance(entry.path, str):
            paths.append(entry.path)
        if not _canonical_owned_path(entry.path):
            diagnostics.append(S2EWaveSourceDiagnostic(
                S2EWaveSourceDiagnosticCode.INVALID_PATH,
                path=entry.path if isinstance(entry.path, str) else None,
            ))
        if not isinstance(entry.expected_generation, str) or not _COMMIT_RE.fullmatch(
            entry.expected_generation
        ):
            diagnostics.append(S2EWaveSourceDiagnostic(
                S2EWaveSourceDiagnosticCode.INVALID_GENERATION,
                path=entry.path if isinstance(entry.path, str) else None,
            ))
        else:
            generations.append(entry.expected_generation)

    duplicate_paths = sorted(
        path for path, count in Counter(paths).items() if count > 1
    )
    diagnostics.extend(
        S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.DUPLICATE_PATH, path=path
        )
        for path in duplicate_paths
    )
    distinct_generations = sorted(set(generations))
    if len(distinct_generations) > 1:
        diagnostics.append(S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.MIXED_GENERATION,
            detail=",".join(distinct_generations),
        ))
    generation = distinct_generations[0] if len(distinct_generations) == 1 else None

    root, root_error = _resolved_top_level(repo_root)
    if root_error is not None:
        diagnostics.append(root_error)
    if diagnostics or root is None or generation is None:
        return _result(
            wave=wave,
            generation=generation,
            owned_paths=paths,
            diagnostics=diagnostics,
        )

    commit_probe = _git(root, "cat-file", "-t", generation)
    if (
        commit_probe is None
        or commit_probe.returncode != 0
        or commit_probe.stdout.strip() != "commit"
    ):
        diagnostics.append(S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.INVALID_COMMIT
        ))
        return _result(
            wave=wave,
            generation=generation,
            owned_paths=paths,
            diagnostics=diagnostics,
        )

    tree_probe = _git(
        root,
        "ls-tree",
        "-z",
        "--full-tree",
        generation,
        "--",
        *sorted(paths),
        text=False,
    )
    if tree_probe is None or tree_probe.returncode != 0:
        diagnostics.append(S2EWaveSourceDiagnostic(
            S2EWaveSourceDiagnosticCode.GIT_TREE_UNREADABLE
        ))
        return _result(
            wave=wave,
            generation=generation,
            owned_paths=paths,
            diagnostics=diagnostics,
        )

    tree_entries: dict[str, tuple[str, str, str]] = {}
    for record in tree_probe.stdout.split(b"\0"):
        if not record:
            continue
        header, separator, raw_path = record.partition(b"\t")
        fields = header.decode("ascii", "replace").split()
        if not separator or len(fields) != 3:
            diagnostics.append(S2EWaveSourceDiagnostic(
                S2EWaveSourceDiagnosticCode.GIT_TREE_UNREADABLE
            ))
            continue
        decoded_path = raw_path.decode("utf-8", "surrogateescape")
        tree_entries[decoded_path] = (fields[0], fields[1], fields[2])

    for path in sorted(paths):
        tree_entry = tree_entries.get(path)
        if tree_entry is None:
            diagnostics.append(S2EWaveSourceDiagnostic(
                S2EWaveSourceDiagnosticCode.MISSING_PATH, path=path
            ))
            continue
        mode, object_type, object_id = tree_entry
        if mode not in _REGULAR_BLOB_MODES or object_type != "blob":
            diagnostics.append(S2EWaveSourceDiagnostic(
                S2EWaveSourceDiagnosticCode.NON_REGULAR_BLOB,
                path=path,
                detail=f"mode={mode} type={object_type}",
            ))
            continue
        blob_probe = _git(root, "cat-file", "blob", object_id, text=False)
        if blob_probe is None or blob_probe.returncode != 0:
            diagnostics.append(S2EWaveSourceDiagnostic(
                S2EWaveSourceDiagnosticCode.UNREADABLE_BLOB, path=path
            ))

    return _result(
        wave=wave,
        generation=generation,
        owned_paths=paths,
        diagnostics=diagnostics,
    )

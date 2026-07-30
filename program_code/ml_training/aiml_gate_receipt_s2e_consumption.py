"""Durable consume-once state for S2E launch predecessor receipts."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import _load_schema, canonical_digest


LAUNCH_ID = "S2E-LW1-LW5"
LAUNCH_WAVES = ("S2E-LW1", "S2E-LW2", "S2E-LW3", "S2E-LW4", "S2E-LW5")
LEDGER_SCHEMA = "s2e_launch_predecessor_consumption_ledger_v1"
ENTRY_SCHEMA = "s2e_launch_predecessor_consumption_entry_v1"
STATE_BASENAME = "codex-s2e-launch-consumption-v1.json"
LOCK_BASENAME = "codex-s2e-launch-consumption-v1.lock"
MAX_STATE_BYTES = 512 * 1024


def _without_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def s2e_launch_consumption_entry_digest(entry: dict[str, Any]) -> str:
    return canonical_digest(_without_digest(entry, "entry_digest"))


def s2e_launch_consumption_ledger_digest(ledger: dict[str, Any]) -> str:
    return canonical_digest(_without_digest(ledger, "ledger_digest"))


def _timestamp(value: str | datetime) -> str:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("consumption timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def validate_s2e_launch_consumption_ledger(ledger: Any) -> list[str]:
    schema = _load_schema(LEDGER_SCHEMA)
    errors = schema_subset_errors(ledger, schema)
    if errors or not isinstance(ledger, dict):
        return errors
    if ledger.get("ledger_digest") != s2e_launch_consumption_ledger_digest(
        ledger
    ):
        errors.append("S2E launch consumption ledger digest is invalid")
    entries = ledger.get("entries", [])
    predecessor_digests: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if entry.get("sequence") != index + 1:
            errors.append("S2E launch consumption sequence is not contiguous")
        expected_previous = (
            None if index == 0 else entries[index - 1].get("entry_digest")
        )
        if entry.get("previous_entry_digest") != expected_previous:
            errors.append("S2E launch consumption hash chain is broken")
        if entry.get("entry_digest") != s2e_launch_consumption_entry_digest(
            entry
        ):
            errors.append("S2E launch consumption entry digest is invalid")
        predecessor = str(entry.get("predecessor_payload_digest", ""))
        if predecessor in predecessor_digests:
            errors.append("S2E launch predecessor was consumed more than once")
        predecessor_digests.add(predecessor)
        if entry.get("successor_wave") != LAUNCH_WAVES[index]:
            errors.append("S2E launch consumption wave order is not canonical")
        try:
            _timestamp(entry.get("consumed_at"))
        except (TypeError, ValueError) as error:
            errors.append(f"S2E launch consumption timestamp is invalid: {error}")
    return sorted(set(errors))


def validate_s2e_launch_consumption_entry(
    entry: Any,
    *,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    acceptance_review_bundle_digest: str,
) -> list[str]:
    errors = validate_s2e_launch_consumption_entry_structure(entry)
    if errors or not isinstance(entry, dict):
        return errors
    for field, expected in (
        ("launch_id", LAUNCH_ID),
        (
            "predecessor_payload_digest",
            predecessor_receipt.get("payload_digest"),
        ),
        ("successor_candidate_payload_digest", candidate.get("payload_digest")),
        ("successor_wave", candidate.get("wave")),
        ("successor_source_head", candidate.get("source_head")),
        (
            "acceptance_review_bundle_digest",
            acceptance_review_bundle_digest,
        ),
        ("side_effect_class", "LOCAL_SOURCE_CONTROL_STATE"),
        ("production_effect", False),
    ):
        if entry.get(field) != expected:
            errors.append(f"S2E launch consumption {field} binding differs")
    return sorted(set(errors))


def validate_s2e_launch_consumption_entry_structure(entry: Any) -> list[str]:
    """Validate the self-contained portion before a predecessor is supplied."""

    schema = _load_schema(LEDGER_SCHEMA)
    errors = schema_subset_errors(
        entry, schema["$defs"]["entry"], root_schema=schema
    )
    if errors or not isinstance(entry, dict):
        return errors
    if entry.get("entry_digest") != s2e_launch_consumption_entry_digest(entry):
        errors.append("S2E launch consumption entry digest is invalid")
    try:
        _timestamp(entry.get("consumed_at"))
    except (TypeError, ValueError) as error:
        errors.append(f"S2E launch consumption timestamp is invalid: {error}")
    return sorted(set(errors))


def _empty_ledger() -> dict[str, Any]:
    ledger = {
        "schema_version": LEDGER_SCHEMA,
        "launch_id": LAUNCH_ID,
        "entries": [],
    }
    ledger["ledger_digest"] = s2e_launch_consumption_ledger_digest(ledger)
    return ledger


def _git_common_dir(repo_root: Path) -> Path:
    raw = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    path = Path(raw)
    return (path if path.is_absolute() else repo_root / path).resolve(strict=True)


def _private_regular_file(descriptor: int, *, label: str) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ValueError(f"{label} must be one owner-only regular file")


class FileS2ELaunchConsumptionStore:
    """Atomic JSON ledger in Git's common directory."""

    def __init__(self, repo_root: Path) -> None:
        self.common_dir = _git_common_dir(repo_root)
        self.state_path = self.common_dir / STATE_BASENAME
        self.lock_path = self.common_dir / LOCK_BASENAME

    def read(self) -> dict[str, Any]:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(self.state_path, flags)
        except FileNotFoundError:
            return _empty_ledger()
        try:
            metadata = os.fstat(descriptor)
            _private_regular_file(descriptor, label="consumption ledger")
            if metadata.st_size > MAX_STATE_BYTES:
                raise ValueError(
                    "S2E launch consumption ledger exceeds size limit"
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_STATE_BYTES:
                    raise ValueError(
                        "S2E launch consumption ledger exceeds size limit"
                    )
                chunks.append(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
        try:
            ledger = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"S2E launch consumption ledger is unreadable: {error}"
            ) from error
        errors = validate_s2e_launch_consumption_ledger(ledger)
        if errors:
            raise ValueError("; ".join(errors))
        return ledger

    def update(
        self, mutation: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> dict[str, Any]:
        lock_flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        lock_fd = os.open(self.lock_path, lock_flags, 0o600)
        try:
            os.fchmod(lock_fd, 0o600)
            _private_regular_file(lock_fd, label="consumption ledger lock")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current = self.read()
            candidate = mutation(current)
            errors = validate_s2e_launch_consumption_ledger(candidate)
            if errors:
                raise ValueError("; ".join(errors))
            if candidate == current:
                return current
            fd, temporary_name = tempfile.mkstemp(
                prefix=f"{STATE_BASENAME}.", suffix=".tmp", dir=self.common_dir
            )
            temporary = Path(temporary_name)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(
                        candidate, handle, ensure_ascii=False, sort_keys=True
                    )
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.state_path)
                parent_fd = os.open(
                    self.common_dir,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
            finally:
                temporary.unlink(missing_ok=True)
            if self.read() != candidate:
                raise ValueError("S2E launch consumption durable readback differs")
            return candidate
        finally:
            os.close(lock_fd)


def consume_s2e_launch_predecessor(
    *,
    repo_root: Path,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    acceptance_review_bundle_digest: str,
    now: str | datetime,
) -> dict[str, Any]:
    """Consume one predecessor atomically; exact retries are idempotent."""

    store = FileS2ELaunchConsumptionStore(repo_root)
    selected: dict[str, Any] = {}
    status = "CONSUMED"

    def mutation(ledger: dict[str, Any]) -> dict[str, Any]:
        nonlocal selected, status
        matching = [
            entry
            for entry in ledger["entries"]
            if entry["predecessor_payload_digest"]
            == predecessor_receipt.get("payload_digest")
        ]
        if matching:
            errors = validate_s2e_launch_consumption_entry(
                matching[0],
                candidate=candidate,
                predecessor_receipt=predecessor_receipt,
                acceptance_review_bundle_digest=acceptance_review_bundle_digest,
            )
            if errors:
                raise ValueError(
                    "S2E launch predecessor already consumed by another "
                    "successor: " + "; ".join(errors)
                )
            selected = matching[0]
            status = "IDEMPOTENT_REPLAY"
            return ledger
        entries = list(ledger["entries"])
        entry = {
            "schema_version": ENTRY_SCHEMA,
            "sequence": len(entries) + 1,
            "previous_entry_digest": (
                entries[-1]["entry_digest"] if entries else None
            ),
            "launch_id": LAUNCH_ID,
            "predecessor_payload_digest": predecessor_receipt.get(
                "payload_digest"
            ),
            "successor_candidate_payload_digest": candidate.get(
                "payload_digest"
            ),
            "successor_wave": candidate.get("wave"),
            "successor_source_head": candidate.get("source_head"),
            "acceptance_review_bundle_digest": acceptance_review_bundle_digest,
            "consumed_at": _timestamp(now),
            "side_effect_class": "LOCAL_SOURCE_CONTROL_STATE",
            "production_effect": False,
        }
        entry["entry_digest"] = s2e_launch_consumption_entry_digest(entry)
        entries.append(entry)
        updated = {
            "schema_version": LEDGER_SCHEMA,
            "launch_id": LAUNCH_ID,
            "entries": entries,
        }
        updated["ledger_digest"] = s2e_launch_consumption_ledger_digest(updated)
        selected = entry
        return updated

    ledger = store.update(mutation)
    result = {
        "schema_version": "s2e_launch_predecessor_consumption_result_v1",
        "status": status,
        "entry": selected,
        "ledger_digest": ledger["ledger_digest"],
        "state_location_class": "GIT_COMMON_DIRECTORY",
        "file_fsynced": True,
        "parent_directory_fsynced": True,
        "mutation_performed": status == "CONSUMED",
        "production_effect": False,
    }
    result["result_digest"] = canonical_digest(result)
    return result

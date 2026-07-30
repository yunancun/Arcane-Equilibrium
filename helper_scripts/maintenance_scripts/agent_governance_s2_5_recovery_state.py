#!/usr/bin/env python3
"""Source-only S2.5 recovery-controller state and host-capture admission."""

from __future__ import annotations

import copy
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
if str(ML_TRAINING_DIR) not in sys.path:
    sys.path.insert(0, str(ML_TRAINING_DIR))

import aiml_gate_receipt_s2_5_host_capture as host_capture_leaf  # noqa: E402
import aiml_gate_receipt_validator as central_validator  # noqa: E402


_LATCH_LEDGER_DIRECTORY = ".s2-5-recovery-latches"
_LATCH_LEDGER_SCHEMA = "s2_5_recovery_latch_ledger_v1"
_LATCH_ENTRY_SCHEMA = "s2_5_recovery_latch_entry_v1"
_MAX_LATCH_LEDGER_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _RecoveryConstructionBinding:
    """Immutable construction-time admission anchor."""

    state_root: Path
    host_capture_bytes: bytes
    host_capture_digest: str
    host_identity: str
    root_id: str
    binding_digest: str


def _binding_digest(
    *,
    state_root: Path,
    host_capture_digest: str,
    host_identity: str,
    root_id: str,
) -> str:
    return central_validator.canonical_digest({
        "schema_version": "s2_5_recovery_controller_binding_v1",
        "canonical_state_root": str(state_root),
        "host_capture_digest": host_capture_digest,
        "host_identity": host_identity,
        "root_id": root_id,
    })


def _latch_ledger_path(binding: _RecoveryConstructionBinding) -> Path:
    digest = binding.root_id.removeprefix("sha256:")
    return binding.state_root.parent / _LATCH_LEDGER_DIRECTORY / f"{digest}.json"


def _secure_read_ledger(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        directory_stat = path.parent.lstat()
    except FileNotFoundError:
        return None, []
    except OSError as error:
        return None, [f"S2.5 durable recovery ledger directory is unreadable: {type(error).__name__}"]
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or stat.S_ISLNK(directory_stat.st_mode)
        or directory_stat.st_uid != os.geteuid()
        or stat.S_IMODE(directory_stat.st_mode) != 0o700
    ):
        return None, ["S2.5 durable recovery ledger directory ownership or mode is unsafe"]
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None, []
    except OSError as error:
        return None, [f"S2.5 durable recovery ledger cannot be opened safely: {type(error).__name__}"]
    try:
        file_stat = os.fstat(fd)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_nlink != 1
            or file_stat.st_uid != os.geteuid()
            or stat.S_IMODE(file_stat.st_mode) != 0o600
            or file_stat.st_size > _MAX_LATCH_LEDGER_BYTES
        ):
            return None, ["S2.5 durable recovery ledger ownership, links, mode, or size is unsafe"]
        chunks: list[bytes] = []
        remaining = _MAX_LATCH_LEDGER_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > _MAX_LATCH_LEDGER_BYTES:
            return None, ["S2.5 durable recovery ledger exceeds the bounded read limit"]
    finally:
        os.close(fd)
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        return None, ["S2.5 durable recovery ledger is malformed"]
    if not isinstance(payload, dict):
        return None, ["S2.5 durable recovery ledger is not an object"]
    return payload, []


def _latch_ledger_errors(
    payload: dict[str, Any],
    *,
    binding: _RecoveryConstructionBinding,
) -> list[str]:
    errors: list[str] = []
    if set(payload) != {
        "schema_version",
        "root_id",
        "canonical_state_root",
        "host_identity",
        "entries",
        "self_digest",
    }:
        errors.append("S2.5 durable recovery ledger fields are not closed")
    if payload.get("schema_version") != _LATCH_LEDGER_SCHEMA:
        errors.append("S2.5 durable recovery ledger schema is invalid")
    if payload.get("root_id") != binding.root_id:
        errors.append("S2.5 durable recovery ledger root identity differs")
    if payload.get("canonical_state_root") != str(binding.state_root):
        errors.append("S2.5 durable recovery ledger canonical path differs")
    if payload.get("host_identity") != binding.host_identity:
        errors.append("S2.5 durable recovery ledger host identity differs")
    if payload.get("self_digest") != central_validator.artifact_self_digest(payload):
        errors.append("S2.5 durable recovery ledger self digest is invalid")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("S2.5 durable recovery ledger has no append history")
        return errors
    previous: str | None = None
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {
            "schema_version",
            "sequence",
            "previous_entry_digest",
            "status",
            "generation",
            "previous_root_digest",
            "unresolved",
            "consumed_authorization_ids",
            "side_effect_class",
            "production_effect",
            "production_authority",
            "entry_digest",
        }:
            errors.append(f"S2.5 durable recovery ledger entry {index} fields are invalid")
            continue
        if (
            entry.get("schema_version") != _LATCH_ENTRY_SCHEMA
            or entry.get("sequence") != index
            or entry.get("previous_entry_digest") != previous
            or entry.get("status") not in {"UNRESOLVED", "RESOLVED_TOMBSTONE"}
            or not isinstance(entry.get("generation"), int)
            or entry.get("generation", 0) <= 0
            or not isinstance(entry.get("previous_root_digest"), str)
            or entry.get("side_effect_class") != "DISPOSABLE_TEST"
            or entry.get("production_effect") is not False
            or entry.get("production_authority") is not False
        ):
            errors.append(f"S2.5 durable recovery ledger entry {index} binding is invalid")
        consumed = entry.get("consumed_authorization_ids")
        if (
            not isinstance(consumed, list)
            or consumed != sorted(set(consumed))
            or not all(isinstance(item, str) and item for item in consumed)
        ):
            errors.append(f"S2.5 durable recovery ledger entry {index} consumption set is invalid")
        unresolved = entry.get("unresolved")
        if entry.get("status") == "UNRESOLVED":
            if not isinstance(unresolved, dict):
                errors.append(f"S2.5 durable recovery ledger entry {index} lost its latch")
            elif unresolved.get("unresolved_state_digest") != central_validator.canonical_digest({
                key: value for key, value in unresolved.items()
                if key != "unresolved_state_digest"
            }):
                errors.append(f"S2.5 durable recovery ledger entry {index} latch digest is invalid")
        elif unresolved is not None:
            errors.append(f"S2.5 durable recovery ledger entry {index} tombstone retained a latch")
        expected_entry_digest = central_validator.canonical_digest({
            key: value for key, value in entry.items() if key != "entry_digest"
        })
        if entry.get("entry_digest") != expected_entry_digest:
            errors.append(f"S2.5 durable recovery ledger entry {index} digest is invalid")
        previous = entry.get("entry_digest")
    return errors


class S2_5RecoveryState:
    """Recovery latch bound to one signed host capture and canonical state root."""

    __slots__ = (
        "_binding",
        "unresolved",
        "_consumed_authorization_ids",
        "_recorded_unresolved_digest",
        "_generation",
        "_previous_root_digest",
        "_durable_ledger_digest",
        "_durable_errors",
        "__weakref__",
    )

    _BOUND_CONTROLLERS: dict[str, "S2_5RecoveryState"] = {}

    def __init__(
        self, *, state_root: Path | str, host_capture: dict[str, Any], now: Any
    ) -> None:
        canonical_root = Path(state_root).resolve(strict=False)
        capture_errors = host_capture_leaf.validate_s2_5_recovery_host_capture(
            host_capture, now=now
        )
        capture_root = (
            host_capture.get("boot_manager_facts", {}).get("canonical_state_root")
            if isinstance(host_capture, dict) else None
        )
        if capture_root != str(canonical_root):
            capture_errors.append(
                "recovery host capture is bound to a different canonical state_root"
            )
        if capture_errors:
            raise ValueError("; ".join(capture_errors))
        host_capture_digest = host_capture["self_digest"]
        host_identity = (
            host_capture_leaf.derive_s2_5_recovery_host_identity(host_capture)
        )
        root_id = central_validator.canonical_digest({
            "schema_version": "s2_5_state_root_identity_v1",
            "stable_host_identity": host_identity,
            "canonical_path": str(canonical_root),
        })
        object.__setattr__(self, "_binding", _RecoveryConstructionBinding(
            state_root=canonical_root,
            host_capture_bytes=central_validator._canonical_bytes(host_capture),
            host_capture_digest=host_capture_digest,
            host_identity=host_identity,
            root_id=root_id,
            binding_digest=_binding_digest(
                state_root=canonical_root,
                host_capture_digest=host_capture_digest,
                host_identity=host_identity,
                root_id=root_id,
            ),
        ))
        self.unresolved: dict[str, Any] | None = None
        self._consumed_authorization_ids: set[str] = set()
        self._recorded_unresolved_digest: str | None = None
        self._generation = 0
        self._previous_root_digest = central_validator.canonical_digest({
            "schema_version": "s2_5_state_root_genesis_v1",
            "root_id": root_id,
        })
        self._durable_ledger_digest: str | None = None
        self._durable_errors: tuple[str, ...] = ()
        self._reload_durable_state()

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_binding" and hasattr(self, "_binding"):
            raise AttributeError("S2.5 construction binding is immutable")
        object.__setattr__(self, name, value)

    @property
    def state_root(self) -> Path:
        return self._binding.state_root

    @property
    def host_capture(self) -> dict[str, Any]:
        return copy.deepcopy(json.loads(self._binding.host_capture_bytes))

    @property
    def host_capture_digest(self) -> str:
        return self._binding.host_capture_digest

    @property
    def host_identity(self) -> str:
        return self._binding.host_identity

    @property
    def root_id(self) -> str:
        return self._binding.root_id

    def _reload_durable_state(self) -> None:
        payload, errors = _secure_read_ledger(_latch_ledger_path(self._binding))
        if payload is None:
            if self._durable_ledger_digest is not None and not errors:
                errors.append("S2.5 durable recovery ledger disappeared after admission")
            self._durable_errors = tuple(errors)
            return
        errors.extend(_latch_ledger_errors(payload, binding=self._binding))
        if errors:
            self._durable_errors = tuple(errors)
            return
        latest = payload["entries"][-1]
        self._generation = latest["generation"]
        self._previous_root_digest = latest["previous_root_digest"]
        self._consumed_authorization_ids = set(
            latest["consumed_authorization_ids"]
        )
        self.unresolved = copy.deepcopy(latest["unresolved"])
        self._recorded_unresolved_digest = (
            self.unresolved["unresolved_state_digest"]
            if self.unresolved is not None else None
        )
        self._durable_ledger_digest = payload["self_digest"]
        self._durable_errors = ()

    def _persist_durable_state(
        self,
        *,
        status: str,
        generation: int,
        previous_root_digest: str,
        unresolved: dict[str, Any] | None,
        consumed_authorization_ids: set[str],
    ) -> str:
        path = _latch_ledger_path(self._binding)
        existing, errors = _secure_read_ledger(path)
        entries: list[dict[str, Any]] = []
        if existing is not None:
            errors.extend(_latch_ledger_errors(existing, binding=self._binding))
            if (
                self._durable_ledger_digest is not None
                and existing.get("self_digest") != self._durable_ledger_digest
            ):
                errors.append("S2.5 durable recovery ledger changed concurrently")
            entries = copy.deepcopy(existing.get("entries", []))
        elif self._durable_ledger_digest is not None and not errors:
            errors.append("S2.5 durable recovery ledger disappeared before update")
        if errors:
            raise ValueError("; ".join(errors))
        entry = {
            "schema_version": _LATCH_ENTRY_SCHEMA,
            "sequence": len(entries),
            "previous_entry_digest": (
                entries[-1]["entry_digest"] if entries else None
            ),
            "status": status,
            "generation": generation,
            "previous_root_digest": previous_root_digest,
            "unresolved": copy.deepcopy(unresolved),
            "consumed_authorization_ids": sorted(consumed_authorization_ids),
            "side_effect_class": "DISPOSABLE_TEST",
            "production_effect": False,
            "production_authority": False,
        }
        entry["entry_digest"] = central_validator.canonical_digest(entry)
        payload = {
            "schema_version": _LATCH_LEDGER_SCHEMA,
            "root_id": self.root_id,
            "canonical_state_root": str(self.state_root),
            "host_identity": self.host_identity,
            "entries": entries + [entry],
        }
        payload["self_digest"] = central_validator.artifact_self_digest(payload)
        from agent_governance_s2_5_wal import _durable_write_json

        _durable_write_json(path, payload)
        readback, readback_errors = _secure_read_ledger(path)
        if readback is None:
            raise ValueError("; ".join(
                readback_errors or ["S2.5 durable recovery ledger readback is absent"]
            ))
        readback_errors.extend(
            _latch_ledger_errors(readback, binding=self._binding)
        )
        if readback.get("self_digest") != payload["self_digest"]:
            readback_errors.append("S2.5 durable recovery ledger readback differs")
        if readback_errors:
            raise ValueError("; ".join(readback_errors))
        return payload["self_digest"]

    def _binding_errors(self) -> tuple[list[str], dict[str, Any]]:
        binding = self._binding
        errors: list[str] = []
        try:
            capture = json.loads(binding.host_capture_bytes)
        except (TypeError, ValueError, UnicodeDecodeError):
            return ["recovery construction binding capture bytes are invalid"], {}
        if not isinstance(capture, dict):
            return ["recovery construction binding capture is not an object"], {}
        if central_validator._canonical_bytes(capture) != binding.host_capture_bytes:
            errors.append("recovery construction binding capture is not canonical")
        if capture.get("self_digest") != binding.host_capture_digest:
            errors.append("recovery construction binding capture digest differs")
        if capture.get("host_identity") != binding.host_identity:
            errors.append("recovery construction binding host identity differs")
        boot_manager_facts = capture.get("boot_manager_facts")
        if (
            not isinstance(boot_manager_facts, dict)
            or boot_manager_facts.get("canonical_state_root") != str(binding.state_root)
        ):
            errors.append("recovery construction binding state root differs")
        expected_root_id = central_validator.canonical_digest({
            "schema_version": "s2_5_state_root_identity_v1",
            "stable_host_identity": binding.host_identity,
            "canonical_path": str(binding.state_root),
        })
        if binding.root_id != expected_root_id:
            errors.append("recovery construction binding root identity differs")
        if binding.binding_digest != _binding_digest(
            state_root=binding.state_root,
            host_capture_digest=binding.host_capture_digest,
            host_identity=binding.host_identity,
            root_id=binding.root_id,
        ):
            errors.append("recovery construction binding digest differs")
        return errors, capture

    def admission_errors(self, state_root: Path | str | None) -> list[str]:
        """Bind exactly one controller object to one canonical state root."""

        errors, _capture = self._binding_errors()
        cached_state = (
            copy.deepcopy(self.unresolved),
            self._recorded_unresolved_digest,
            self._generation,
            self._previous_root_digest,
            set(self._consumed_authorization_ids),
        )
        self._reload_durable_state()
        errors.extend(self._durable_errors)
        if (
            self._durable_ledger_digest is not None
            and cached_state != (
                self.unresolved,
                self._recorded_unresolved_digest,
                self._generation,
                self._previous_root_digest,
                self._consumed_authorization_ids,
            )
            and cached_state[2] != 0
        ):
            errors.append(
                "S2.5 cached recovery state differs from the durable latch ledger"
            )
        if state_root is None:
            errors.append("S2.5 recovery controller cannot bind an absent state_root")
            return errors
        candidate = Path(state_root).resolve(strict=False)
        if candidate != self._binding.state_root:
            errors.append(
                "S2.5 recovery controller is bound to a different canonical state_root"
            )
            return errors
        key = str(candidate)
        existing = self._BOUND_CONTROLLERS.get(key)
        if existing is not None and existing is not self:
            errors.append(
                "S2.5 recovery controller substitution is forbidden for an already-bound "
                "canonical state_root"
            )
            return errors
        self._BOUND_CONTROLLERS[key] = self
        if self.unresolved is not None:
            current = central_validator.canonical_digest({
                key: value for key, value in self.unresolved.items()
                if key != "unresolved_state_digest"
            })
            if (
                current != self.unresolved.get("unresolved_state_digest")
                or current != self._recorded_unresolved_digest
            ):
                errors.append(
                    "S2.5 unresolved recovery latch was mutated after failure capture"
                )
        return errors

    def operation_errors(self, *, now: Any, intent_source_head: Any) -> list[str]:
        """Revalidate the full capture at effect admission time."""

        binding = self._binding
        errors, capture = self._binding_errors()
        errors.extend(host_capture_leaf.validate_s2_5_recovery_host_capture(
            capture, now=now
        ))
        if capture.get("self_digest") != binding.host_capture_digest:
            errors.append("recovery host capture differs from the controller-bound capture")
        if capture.get("host_identity") != binding.host_identity:
            errors.append("recovery host identity differs from the controller binding")
        boot_manager_facts = capture.get("boot_manager_facts")
        if (
            not isinstance(boot_manager_facts, dict)
            or boot_manager_facts.get("canonical_state_root") != str(binding.state_root)
        ):
            errors.append("recovery host capture state root differs from the controller")
        if capture.get("source_head") != intent_source_head:
            errors.append(
                "recovery host capture source_head differs from current intent core"
            )
        return errors

    def record(
        self,
        *,
        start_id: str | None,
        reasons: list[str],
        task_digest: str,
        journal_set: dict[str, Any],
        replay_ledger_head: dict[str, Any],
        pre_state: dict[str, Any],
        source_head: str,
        root_digest: str,
    ) -> None:
        """Capture the exact failure generation; an unresolved latch is never overwritten."""

        binding_errors, host_capture = self._binding_errors()
        if binding_errors:
            raise ValueError("; ".join(binding_errors))
        if source_head != host_capture.get("source_head"):
            raise ValueError("recovery failure source_head differs from signed host capture")
        self._reload_durable_state()
        if self._durable_errors:
            raise ValueError("; ".join(self._durable_errors))
        if self.unresolved is not None:
            raise ValueError("an unresolved S2.5 recovery latch already exists")
        next_generation = self._generation + 1
        unresolved = {
            "start_id": start_id,
            "reasons": list(reasons),
            "task_digest": task_digest,
            "state_root_identity": {
                "root_id": self.root_id,
                "root_digest": root_digest,
                "generation": next_generation,
                "previous_root_digest": self._previous_root_digest,
            },
            "journal_set": dict(journal_set),
            "replay_ledger_head": dict(replay_ledger_head),
            "pre_state": dict(pre_state),
            "source_head": source_head,
            "host_identity": self._binding.host_identity,
            "host_capture": copy.deepcopy(host_capture),
            "host_capture_digest": self._binding.host_capture_digest,
            "side_effect_class": "DISPOSABLE_TEST",
            "production_effect": False,
            "production_authority": False,
            "target_class": "disposable_systemd",
        }
        unresolved["unresolved_state_digest"] = (
            central_validator.canonical_digest(unresolved)
        )
        ledger_digest = self._persist_durable_state(
            status="UNRESOLVED",
            generation=next_generation,
            previous_root_digest=root_digest,
            unresolved=unresolved,
            consumed_authorization_ids=self._consumed_authorization_ids,
        )
        self._generation = next_generation
        self.unresolved = unresolved
        self._recorded_unresolved_digest = unresolved["unresolved_state_digest"]
        self._previous_root_digest = root_digest
        self._durable_ledger_digest = ledger_digest

    def resolve(
        self,
        *,
        recovery_result: dict[str, Any],
        independent_postcheck: dict[str, Any],
        now: Any,
    ) -> dict[str, Any]:
        """Apply the sole legal unresolved-to-clear transition."""

        import agent_governance_s2_5_recovery as recovery

        errors = self.admission_errors(self._binding.state_root)
        if now is None:
            errors.append("recovery resolution requires an explicit trusted current time")
        errors.extend(central_validator.validate_aiml_artifact(
            recovery_result, now=now
        ))
        errors.extend(central_validator.validate_aiml_artifact(
            independent_postcheck, now=now
        ))
        if not errors:
            errors.extend(recovery.validate_recovery_transition(
                unresolved_state=self.unresolved,
                recovery_result=recovery_result,
                independent_postcheck=independent_postcheck,
                consumed_authorization_ids=self._consumed_authorization_ids,
                now=now,
            ))
        if errors:
            raise ValueError("; ".join(errors))
        assert self.unresolved is not None
        resolved = self.unresolved
        authorization_id = recovery_result["recovery_binding"]["authorization"][
            "authorization_id"
        ]
        consumed = set(self._consumed_authorization_ids)
        consumed.add(authorization_id)
        ledger_digest = self._persist_durable_state(
            status="RESOLVED_TOMBSTONE",
            generation=self._generation,
            previous_root_digest=self._previous_root_digest,
            unresolved=None,
            consumed_authorization_ids=consumed,
        )
        self._consumed_authorization_ids = consumed
        self.unresolved = None
        self._recorded_unresolved_digest = None
        self._durable_ledger_digest = ledger_digest
        return resolved

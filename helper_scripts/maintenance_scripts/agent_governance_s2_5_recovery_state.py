#!/usr/bin/env python3
"""Source-only S2.5 recovery-controller state and host-capture admission."""

from __future__ import annotations

import copy
import json
import sys
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
if str(ML_TRAINING_DIR) not in sys.path:
    sys.path.insert(0, str(ML_TRAINING_DIR))

import aiml_gate_receipt_s2_5_host_capture as host_capture_leaf  # noqa: E402
import aiml_gate_receipt_validator as central_validator  # noqa: E402


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


class S2_5RecoveryState:
    """Recovery latch bound to one signed host capture and canonical state root."""

    __slots__ = (
        "_binding",
        "unresolved",
        "_consumed_authorization_ids",
        "_recorded_unresolved_digest",
        "_generation",
        "_previous_root_digest",
        "__weakref__",
    )

    _BOUND_CONTROLLERS: weakref.WeakValueDictionary[
        str, "S2_5RecoveryState"
    ] = weakref.WeakValueDictionary()

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
        if capture.get("boot_manager_facts", {}).get(
            "canonical_state_root"
        ) != str(binding.state_root):
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
        if capture.get("boot_manager_facts", {}).get(
            "canonical_state_root"
        ) != str(binding.state_root):
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
        if self.unresolved is not None:
            raise ValueError("an unresolved S2.5 recovery latch already exists")
        if source_head != host_capture.get("source_head"):
            raise ValueError("recovery failure source_head differs from signed host capture")
        self._generation += 1
        unresolved = {
            "start_id": start_id,
            "reasons": list(reasons),
            "task_digest": task_digest,
            "state_root_identity": {
                "root_id": self.root_id,
                "root_digest": root_digest,
                "generation": self._generation,
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
        self.unresolved = unresolved
        self._recorded_unresolved_digest = unresolved["unresolved_state_digest"]
        self._previous_root_digest = root_digest

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
        self._consumed_authorization_ids.add(authorization_id)
        self.unresolved = None
        self._recorded_unresolved_digest = None
        return resolved

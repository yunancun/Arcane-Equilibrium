from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
MAINTENANCE = ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING = ROOT / "program_code" / "ml_training"
for candidate in (MAINTENANCE, ML_TRAINING):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_5_recovery_lock as recovery_lock  # noqa: E402


def lock_outcome(*, source_head: str, released: bool) -> dict[str, Any]:
    intent = recovery_lock._intent(
        source_head,
        session_class="FIXED_POSIX_RECOVERY_SESSION",
    )
    result = recovery_lock._result(
        intent,
        status=recovery_lock.STATUS_ACQUIRED,
        s2_4_acquired=True,
        s2_5_acquired=True,
        first_released=False,
        driver_engaged=True,
        failure_code=None,
        session_class="FIXED_POSIX_RECOVERY_SESSION",
    )
    postcheck = recovery_lock._postcheck(
        result,
        chain_digest=recovery_lock._chain_digest(intent, result),
        session_class="FIXED_POSIX_RECOVERY_SESSION",
        both_locks_held=True,
        failure_code=None,
    )
    rollback = recovery_lock._rollback(
        intent,
        result,
        status="RELEASED" if released else "NOT_REQUIRED",
        s2_5_attempted=released,
        s2_5_released=released,
        s2_4_attempted=released,
        s2_4_released=released,
        session_closed=released,
        failure_code=None,
    )
    return {
        "status": recovery_lock.STATUS_ACQUIRED,
        "intent": intent,
        "result": result,
        "postcheck": postcheck,
        "rollback": rollback,
    }


class FixedManifestEffectSession:
    def __init__(
        self,
        *,
        source_head: str,
        observation: Callable[..., dict[str, Any]],
        guard_error: Exception | None = None,
    ) -> None:
        self.source_head = source_head
        self.observation = observation
        self.guard_error = guard_error
        self.failure_code = None
        self.active = True
        self.lock_outcome = lock_outcome(
            source_head=source_head,
            released=False,
        )

    def observe(self) -> dict[str, Any]:
        return self.observation(source_head=self.source_head)

    def guard_effect(
        self, *, expected_observation: dict[str, Any]
    ) -> None:
        assert expected_observation["manifest"] is not None
        if self.guard_error is not None:
            raise self.guard_error

    def close(self) -> dict[str, Any]:
        self.active = False
        self.lock_outcome = lock_outcome(
            source_head=self.source_head,
            released=True,
        )
        return self.lock_outcome

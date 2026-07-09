from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ml_training.alr_retention_guardian import (
    AlrRetentionGuardianError,
    decide_retention_action,
)


NOW = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)


def _entry(*, state: str = "ACTIVE", quarantined_at: datetime | None = None) -> dict:
    return {
        "cache_key": "scanner-features:example",
        "cache_artifact_hash": "a" * 64,
        "cache_kind": "scanner_statistical_features_v1",
        "owner_scope": "ALR_OWNED_REBUILDABLE",
        "rebuildable": True,
        "cache_state": state,
        "created_at": NOW - timedelta(days=2),
        "quarantined_at": quarantined_at,
    }


def test_unreferenced_active_cache_is_quarantined_before_any_sweep() -> None:
    decision = decide_retention_action(
        _entry(),
        referenced_artifact_hashes=set(),
        now=NOW,
        grace_seconds=3600,
    )

    assert decision.action == "QUARANTINE"
    assert decision.delete_cache is False
    assert decision.next_state == "QUARANTINED"
    assert decision.authority_counters == {"derived_cache_delete_count": 0}


def test_quarantined_unreferenced_cache_sweeps_only_after_grace_recheck() -> None:
    decision = decide_retention_action(
        _entry(state="QUARANTINED", quarantined_at=NOW - timedelta(hours=2)),
        referenced_artifact_hashes=set(),
        now=NOW,
        grace_seconds=3600,
    )

    assert decision.action == "SWEEP"
    assert decision.delete_cache is True
    assert decision.next_state is None
    assert decision.authority_counters == {"derived_cache_delete_count": 1}


def test_reference_recheck_restores_quarantined_cache_and_prevents_sweep() -> None:
    decision = decide_retention_action(
        _entry(state="QUARANTINED", quarantined_at=NOW - timedelta(hours=2)),
        referenced_artifact_hashes={"a" * 64},
        now=NOW,
        grace_seconds=3600,
    )

    assert decision.action == "RESTORE_REFERENCE"
    assert decision.delete_cache is False
    assert decision.next_state == "ACTIVE"


def test_rejects_non_rebuildable_or_non_alr_entries() -> None:
    non_rebuildable = _entry()
    non_rebuildable["rebuildable"] = False
    with pytest.raises(AlrRetentionGuardianError, match="cache_rebuildable_required"):
        decide_retention_action(
            non_rebuildable,
            referenced_artifact_hashes=set(),
            now=NOW,
            grace_seconds=3600,
        )

    foreign = _entry()
    foreign["owner_scope"] = "FOREIGN"
    with pytest.raises(AlrRetentionGuardianError, match="cache_owner_scope_invalid"):
        decide_retention_action(
            foreign,
            referenced_artifact_hashes=set(),
            now=NOW,
            grace_seconds=3600,
        )

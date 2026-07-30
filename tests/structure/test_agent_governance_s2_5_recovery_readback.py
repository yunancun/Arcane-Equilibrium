"""S2E.LW1 fresh-challenge recovery current-readback Adapter boundary."""

from __future__ import annotations

import inspect
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_5_recovery as recovery  # noqa: E402
import agent_governance_s2_5_recovery_readback as adapter  # noqa: E402


NOW = datetime.fromisoformat("2026-07-30T12:00:00+00:00")


@pytest.fixture
def deterministic_adapter(monkeypatch):
    counter = [0]

    def nonce():
        counter[0] += 1
        return "s2-5-readback-challenge-" + f"{counter[0]:064x}"

    def exchange(request_bytes):
        request = json.loads(request_bytes)
        return {
            "query_digest": request["self_digest"],
            "challenge_nonce": request["challenge_nonce"],
            "store_id": request["store_id"],
            "anchor_scope_id": request["anchor_scope_id"],
        }

    monkeypatch.setattr(adapter, "_trusted_now", lambda: NOW)
    monkeypatch.setattr(adapter, "_fresh_challenge_nonce", nonce)
    monkeypatch.setattr(adapter, "_fixed_transport_exchange", exchange)


def test_adapter_emits_typed_read_only_chain(deterministic_adapter):
    first = adapter._query_current_anchor_readback(
        anchor_scope_id="off-root:host-governance",
    )
    second = adapter._query_current_anchor_readback(
        anchor_scope_id="off-root:host-governance",
    )
    assert adapter.validate_current_readback_chain(first) == []
    assert first["status"] == "OBSERVED_UNVERIFIED_SIGNATURE"
    assert first["intent"]["challenge_nonce"] != second["intent"][
        "challenge_nonce"
    ]
    for artifact in (
        first,
        first["intent"],
        first["result"],
        first["postcheck"],
        first["rollback"],
    ):
        assert artifact["side_effect_class"] == "DISPOSABLE_TEST"
        assert artifact["effect_class"] == "READ_ONLY_EXTERNAL_ATTESTATION"
        assert artifact["production_effect"] is False
        assert artifact["production_authority"] is False
        assert artifact["production_runtime_effect_performed"] is False
    assert first["rollback"]["status"] == "NOT_REQUIRED_READ_ONLY"
    assert first["rollback"]["mutation_performed"] is False


def test_transport_unavailable_is_a_typed_fail_closed_chain(
    deterministic_adapter,
    monkeypatch,
):
    def unavailable(_request_bytes):
        raise adapter.RecoveryAnchorReadbackError(
            "readback_query_transport_unavailable"
        )

    monkeypatch.setattr(adapter, "_fixed_transport_exchange", unavailable)
    chain = adapter._query_current_anchor_readback(
        anchor_scope_id="off-root:host-governance",
    )
    assert adapter.validate_current_readback_chain(chain) == []
    assert chain["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert chain["result"]["failure_code"] == (
        "readback_query_transport_unavailable"
    )
    assert chain["rollback"]["status"] == "NOT_REQUIRED_READ_ONLY"


def test_current_floor_has_no_replaceable_local_file_or_caller_transport():
    assert not hasattr(recovery, "RECOVERY_ANCHOR_CURRENT_READBACK_PATH")
    assert not hasattr(recovery, "_read_fixed_recovery_current_readback")
    assert set(inspect.signature(
        adapter._query_current_anchor_readback
    ).parameters) == {"anchor_scope_id"}
    source = inspect.getsource(adapter._fixed_transport_exchange)
    assert "socket.AF_UNIX" in source
    assert "FIXED_ATTESTOR_SOCKET_PATH" in source
    assert "environ" not in source

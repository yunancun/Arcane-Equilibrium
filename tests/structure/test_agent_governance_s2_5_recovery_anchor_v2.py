from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MAINTENANCE = ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING = ROOT / "program_code" / "ml_training"
STRUCTURE_TESTS = ROOT / "tests" / "structure"
for candidate in (MAINTENANCE, ML_TRAINING, STRUCTURE_TESTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_5_recovery_anchor_v2 as anchor_v2  # noqa: E402
from s2_5_recovery_anchor_test_support import (  # noqa: E402
    FixedManifestEffectSession,
)
import test_agent_governance_s2_5_recovery_controller as cases  # noqa: E402


@pytest.fixture(autouse=True)
def _fixed_capture_trust_root(tmp_path, monkeypatch):
    kit = __import__("s2_5_testkit")
    private_key, public_key, fingerprint = kit.mint_key(
        tmp_path, "s2-5-controller-host-capture"
    )
    monkeypatch.setattr(
        cases.host_capture,
        "_load_recovery_host_capture_trust_root_public_key",
        lambda: public_key,
    )
    monkeypatch.setattr(
        cases.host_capture,
        "RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT",
        fingerprint,
    )
    cases._SIGNING_PROFILE = (private_key, public_key, fingerprint)
    yield
    cases._SIGNING_PROFILE = None


def test_controller_anchor_root_replacement_at_dispatch_never_appends(
    monkeypatch,
):
    _transition, outbox, _state, manifest = cases._genesis()
    clock = cases._ControllerAnchorClock(
        "2030-01-01T00:25:00+00:00"
    )
    observation = cases._FixedManifestObservation(manifest)
    session = FixedManifestEffectSession(
        source_head=cases.HEAD,
        observation=observation,
        guard_error=anchor_v2.ControllerAnchorEffectError(
            "anchor_effect_state_root_replaced"
        ),
    )
    writer = cases._ControllerAnchorWriter(outbox=outbox, clock=clock)
    monkeypatch.setattr(anchor_v2, "_trusted_now", clock.now)
    monkeypatch.setattr(
        anchor_v2, "_fixed_manifest_observation", observation
    )
    monkeypatch.setattr(
        anchor_v2,
        "_open_fixed_effect_session",
        lambda *, source_head: session,
        raising=False,
    )
    adapter = anchor_v2.ControllerAnchorEffectAdapter(
        writer=writer,
        reader=cases._ControllerAnchorReader(writer),
        verifier=cases._ControllerAnchorVerifier(),
    )

    chain = adapter.execute_fixed_profile(source_head=cases.HEAD)

    assert writer.requests == []
    assert session.active is False
    assert observation.calls == 2
    assert chain["status"] == "PRECHECK_REJECTED"
    assert chain["failure_code"] == "anchor_effect_state_root_replaced"
    assert chain["session_lock"]["rollback"]["status"] == "RELEASED"
    assert anchor_v2.validate_effect_chain(chain) == []

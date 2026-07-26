"""S2.4(WP4·W3a)typed host capability probe 的 focused 測試(§8.3 / §10.5 #36/#38/#39)。

證明:
- source lane(``driver=None``)回 typed ``EXTERNAL_VERIFICATION_PENDING`` 且**零變更、零
  driver 接觸**——鏡 S2.0 ``apply_observer_bootstrap``;
- §10.5 #38 route-surface:probe 請求攜帶 builder/install 權限(forbidden surface 為真、
  builder effect class、install/prepare/pg profile 授權)於節點注入前即拒;transient probe
  unit 永不寫任何持久 unit 狀態;
- §10.5 #36 scope/digest/host/property 替換:兩 scope 的屬性 digest 與 probe_id 必不同、
  跨 scope 輸入夾帶被拒、PREPARE_SANDBOX attestation 不能滿足 INSTALLED_UNIT 消費者(反之
  亦然),且 final-unit attestation **永非** W6A 前置;
- §10.5 #39 fault injection:每一個 D-Bus / journal transition 之前與之後崩潰、執行中授權
  過期(過期後只剩 exact cleanup 權限)、InvocationID/cgroup/property 不符,以及
  「recovery 未解不得起新 probe」。
"""
from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_probe as probe  # noqa: E402
import agent_governance_s2_4_render as render  # noqa: E402
import aiml_gate_receipt_schema_core as schema_core  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

# 凍結時鐘錨點:每一次呼叫都顯式傳 now/clock,故本檔與 wall clock 完全無關(無日期腐化)。
_ANCHOR = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_ISSUED = _ANCHOR.isoformat()
_NOW = (_ANCHOR + timedelta(minutes=2)).isoformat()
_EXPIRES = (_ANCHOR + timedelta(minutes=10)).isoformat()
_MIRROR = ["203.0.113.0/24"]
_HOST = "trade-core"
_CGROUP_ROOT = "/sys/fs/cgroup/system.slice"
_INVOCATION = "a" * 32
_CAPTURE_DIGEST = "sha256:" + "7" * 64
_UNIT_FIELDS = {
    "source_head": "0" * 40,
    "learning_runtime_digest": "sha256:" + "0" * 64,
    "learning_runtime_digest_v2": "sha256:" + "1" * 64,
    "application_bundle_digest": "sha256:" + "2" * 64,
    "launch_bundle_digest": "sha256:" + "3" * 64,
}
_SIGN_SEQ = [0]


# ── fixtures ────────────────────────────────────────────────────────────────────
def _rendered_unit() -> str:
    return render.render_engine_scanner_unit(dict(_UNIT_FIELDS))


def _core(scope: str = "PREPARE_SANDBOX"):
    scope_inputs = (
        {"artifact_mirror_allowlist": list(_MIRROR)}
        if scope == "PREPARE_SANDBOX"
        else {"rendered_unit": _rendered_unit()}
    )
    return probe.build_capability_probe_core(
        scope=scope,
        host=_HOST,
        cgroup_manager_scope="system_manager",
        cgroup_root_pattern=_CGROUP_ROOT,
        source_head="0" * 40,
        target_host=_HOST,
        created_at=_ISSUED,
        max_cleanup_seconds=30,
        max_cgroup_drain_seconds=10,
        **scope_inputs,
    )


def _intent(scope: str = "PREPARE_SANDBOX"):
    return probe.build_capability_probe_intent(
        _core(scope), expires_at=_EXPIRES, max_ttl_seconds=600
    )


def _scope_kwargs(scope: str) -> dict:
    if scope == "PREPARE_SANDBOX":
        return {"artifact_mirror_allowlist": list(_MIRROR)}
    return {"rendered_unit": _rendered_unit()}


def _mint_key(tmp_path, name="probe-operator"):
    private_key = tmp_path / name
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True
    )
    parts = private_key.with_suffix(".pub").read_text(encoding="ascii").split()
    public_key = " ".join(parts[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    return private_key, public_key, fingerprint


def _install_pinned_key(monkeypatch, public_key, fingerprint) -> None:
    # 注入丟棄式信任根到 resolve_facade() 實際回傳的那一份 facade(top-level / package 形皆命中)。
    facade = schema_core.resolve_facade()
    monkeypatch.setattr(facade, "S2_4_OPERATOR_TRUST_ROOT_PUBLIC_KEY", public_key)
    monkeypatch.setattr(facade, "S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT", fingerprint)


def _sign(private_key, artifact, *, namespace):
    signed = validator._s2_4_operator_authorization_signed_bytes(artifact)
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"probe-auth-{_SIGN_SEQ[0]}.bin"
    message.write_bytes(signed)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n", namespace, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    artifact["sshsig_armored"] = message.with_name(message.name + ".sig").read_text(encoding="ascii")
    artifact["self_digest"] = validator.artifact_self_digest(artifact)
    return artifact


def _authorization(private_key, *, profile_key="capability_probe", expires_at=_EXPIRES):
    profile = validator.S2_4_AUTHORIZATION_PROFILES[profile_key]
    artifact = {
        "schema_version": "s2_4_operator_authorization_v1",
        "profile_identity": profile["profile_identity"],
        "signature_namespace": profile["signature_namespace"],
        "authorization_id": "sha256:" + "1" * 64,
        "payload_fields": list(profile["payload_fields"]),
        "issued_at": _ISSUED,
        "expires_at": expires_at,
        "sshsig_armored": "-----BEGIN SSH SIGNATURE-----\nAAAA\n-----END SSH SIGNATURE-----\n",
        "self_digest": "sha256:" + "0" * 64,
    }
    return _sign(private_key, artifact, namespace=profile["signature_namespace"])


def _replay_ledger(consumed=()):
    entries = []
    previous = None
    for index, item in enumerate(
        [
            {
                "authorization_id": "sha256:" + "9" * 64,
                "authorization_digest": "sha256:" + "8" * 64,
                "profile_identity": "aiml-s2-capability-probe-operator-v1",
            },
            *consumed,
        ]
    ):
        entry = {
            "seq": index,
            "prev_entry_digest": previous,
            "authorization_id": item["authorization_id"],
            "authorization_digest": item["authorization_digest"],
            "profile_identity": item["profile_identity"],
            "consumed_at": _ISSUED,
            "fsynced": True,
        }
        entry["entry_digest"] = validator.canonical_digest(entry)
        previous = entry["entry_digest"]
        entries.append(entry)
    ledger = {
        "schema_version": "s2_4_authorization_replay_ledger_v1",
        "ledger_path": "/var/lib/arcane-equilibrium/aiml/install/s2_4/replay-ledger.json",
        "entries": entries,
        "append_only": True,
    }
    ledger["self_digest"] = validator.artifact_self_digest(ledger)
    return ledger


class _FakeProbeDriver:
    """注入式測試 driver:只記錄固定操作,絕不觸碰任何主機(W3b 才有真 driver)。"""

    # in-memory fixture 絕不冒充平台背書(W3 review E2 P1-1 / E3 P2-6)。
    evidence_class = "STRUCTURAL_ONLY"

    def __init__(
        self,
        *,
        property_digest,
        invocation_id=_INVOCATION,
        cgroup_root=_CGROUP_ROOT,
        network_isolation_verified=True,
        residue=None,
        verifier_node="s2-4-probe-verifier",
        postcheck_flags=None,
    ):
        self.calls: list[str] = []
        self.journal: list[dict] = []
        self.property_digest = property_digest
        self.invocation_id = invocation_id
        self.cgroup_root = cgroup_root
        self.network_isolation_verified = network_isolation_verified
        self.residue = residue or {
            "unit_absent": True,
            "cgroup_absent": True,
            "process_absent": True,
            "task_files_absent": True,
        }
        self.verifier_node = verifier_node
        self.postcheck_flags = postcheck_flags or {}

    def journal_transition(self, *, entry):
        self.calls.append("journal:" + entry["state"])
        self.journal.append(dict(entry))

    def start_transient_unit(self, *, unit_name, scope, properties):
        self.calls.append("start_transient_unit")
        self.unit_name = unit_name
        self.started_properties = properties
        return self.invocation_id

    def read_unit_properties(self, *, unit_name):
        self.calls.append("read_unit_properties")
        return {
            "invocation_id": self.invocation_id,
            "cgroup": f"{self.cgroup_root}/{unit_name}",
            "property_digest": self.property_digest,
        }

    def observe_egress(self, *, unit_name, scope):
        self.calls.append("observe_egress")
        return {
            "host_systemd_cgroup_versions": {
                "kernel": "6.1.0", "systemd": "252", "cgroup": "v2"
            },
            "egress_observations": {"allow": "127.0.0.1/32", "deny": "any"},
            "network_isolation_verified": self.network_isolation_verified,
        }

    def stop_transient_unit(self, *, unit_name, max_drain_seconds):
        self.calls.append("stop_transient_unit")

    def reset_failed(self, *, unit_name):
        self.calls.append("reset_failed")

    def remove_transient_unit(self, *, unit_name):
        self.calls.append("remove_transient_unit")

    def sweep_residue(self, *, unit_name):
        self.calls.append("sweep_residue")
        return dict(self.residue)

    def independent_cleanup_postcheck(self, *, unit_name, probe_id, probe_core_digest):
        self.calls.append("independent_cleanup_postcheck")
        flags = {
            "stopped_confirmed": True,
            "reset_failed_confirmed": True,
            "removed_confirmed": True,
            "no_surviving_unit": True,
            "no_surviving_cgroup": True,
            "no_surviving_process": True,
        }
        flags.update(self.postcheck_flags)
        return {
            "verifier_node": self.verifier_node,
            "verifier_capture_digest": _CAPTURE_DIGEST,
            **flags,
        }

    def trusted_host_time(self):
        self.calls.append("trusted_host_time")
        return _NOW


def _frozen_clock(offset_minutes: float = 3.0):
    return lambda: _ANCHOR + timedelta(minutes=offset_minutes)


def _run(intent, authorization, driver, *, scope="PREPARE_SANDBOX", **kwargs):
    kwargs.setdefault("now", _NOW)
    kwargs.setdefault("clock", _frozen_clock())
    kwargs.setdefault("replay_ledger", _replay_ledger())
    kwargs.update(_scope_kwargs(scope))
    return probe.run_s2_4_capability_probe(intent, authorization, driver, **kwargs)


# ── source lane:driver=None → typed pending,零變更 ─────────────────────────────
def test_source_lane_driver_none_is_pending_with_zero_mutation(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    verdict = _run(_intent(), _authorization(private_key), None)
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert verdict["mutation_performed"] is False
    assert verdict["driver_engaged"] is False
    assert verdict["blocks_next_phase"] is True
    assert verdict["effect_receipt"] is None and verdict["attestation"] is None
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_missing_authorization_or_ledger_is_typed_rejection_before_any_driver() -> None:
    driver = _FakeProbeDriver(property_digest=_core()["transient_unit_property_digest"])
    verdict = _run(_intent(), None, driver)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert verdict["driver_engaged"] is False and driver.calls == []
    verdict = _run(_intent(), None, driver, replay_ledger=None)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("replay" in reason for reason in verdict["reasons"])
    assert driver.calls == []


# ── §10.5 #38 route surface ─────────────────────────────────────────────────────
@pytest.mark.parametrize("surface", ["pg", "secret", "credential_install", "host_identity",
                                     "persistent_unit_write", "persistent_unit_enable",
                                     "persistent_unit_start", "daemon_reload", "migration",
                                     "broker_or_order"])
def test_probe_request_carrying_builder_or_install_authority_is_rejected(surface) -> None:
    forged = _intent()
    forged["forbidden_surfaces"][surface] = True
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert probe.derive_probe_route_surface_status(forged)["status"] == (
        "PROBE_ROUTE_SURFACE_REJECTED"
    )
    driver = _FakeProbeDriver(property_digest=_core()["transient_unit_property_digest"])
    verdict = _run(forged, None, driver)
    # closed schema(const false)先擋;無論哪一道,皆在節點注入前 typed 拒且零 driver 接觸。
    assert verdict["status"] == "PROBE_REQUEST_REJECTED"
    assert driver.calls == [] and verdict["mutation_performed"] is False


def test_probe_request_with_builder_effect_class_or_service_is_rejected() -> None:
    for key, value in (
        ("required_effect_class", "LEARNING_RUNTIME_PREPARE"),
        ("service", "arcane-equilibrium-aiml-engine-scanner.service"),
    ):
        forged = _intent()
        forged["route_surface"][key] = value
        forged["self_digest"] = validator.artifact_self_digest(forged)
        assert probe.derive_probe_route_surface_status(forged)["status"] == (
            "PROBE_ROUTE_SURFACE_REJECTED"
        )


@pytest.mark.parametrize("profile_key", ["prepare", "apply_aggregate", "pg_migration"])
def test_builder_install_profile_authorization_cannot_authorize_a_probe(
    tmp_path, monkeypatch, profile_key
) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    driver = _FakeProbeDriver(property_digest=_core()["transient_unit_property_digest"])
    verdict = _run(_intent(), _authorization(private_key, profile_key=profile_key), driver)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("capability-probe profile" in reason for reason in verdict["reasons"])
    assert driver.calls == []


def test_transient_probe_driver_surface_has_no_persistent_unit_capability(tmp_path, monkeypatch) -> None:
    """§10.5 #38 下半:transient probe unit 不可能存活或寫任何持久 unit 狀態。"""
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    driver = _FakeProbeDriver(property_digest=_core()["transient_unit_property_digest"])
    verdict = _run(_intent(), _authorization(private_key), driver)
    assert verdict["status"] == "TERMINAL_CLEAN"
    # driver protocol 上沒有任何 enable/daemon-reload/持久 unit 寫入操作。
    protocol_methods = {
        name for name in dir(probe.CapabilityProbeDriver) if not name.startswith("__")
    }
    assert not any(
        token in name
        for name in protocol_methods
        for token in ("enable", "daemon_reload", "install_unit", "persistent")
    )
    # 實際被呼叫的操作全在 transient 允許集合內,且 unit 名恆為 task-bound transient 名。
    allowed = {
        "start_transient_unit", "read_unit_properties", "observe_egress",
        "stop_transient_unit", "reset_failed", "remove_transient_unit",
        "sweep_residue", "independent_cleanup_postcheck", "trusted_host_time",
    }
    assert {call for call in driver.calls if not call.startswith("journal:")} <= allowed
    assert driver.unit_name.startswith("arcane-aiml-s2-4-probe-")
    assert driver.unit_name.endswith(".service")
    assert verdict["effect_receipt"]["derived_unit_name"] == driver.unit_name


# ── §10.5 #36 scope 替換 ────────────────────────────────────────────────────────
def test_two_scopes_have_distinct_property_digests_and_probe_ids() -> None:
    prepare_core, installed_core = _core("PREPARE_SANDBOX"), _core("INSTALLED_UNIT")
    assert prepare_core["transient_unit_property_digest"] != (
        installed_core["transient_unit_property_digest"]
    )
    assert probe.probe_id_for_core(prepare_core) != probe.probe_id_for_core(installed_core)
    # 跨 scope 的輸入夾帶一律 typed 拒(scope 替換的第一道閘)。
    with pytest.raises(probe.ProbeContractError):
        probe.capability_probe_property_digest("PREPARE_SANDBOX", rendered_unit=_rendered_unit())
    with pytest.raises(probe.ProbeContractError):
        probe.capability_probe_property_digest(
            "INSTALLED_UNIT", artifact_mirror_allowlist=list(_MIRROR)
        )


def test_scope_substitution_in_the_core_is_rejected_at_derivation() -> None:
    forged = _core("PREPARE_SANDBOX")
    forged["probe_scope"] = "INSTALLED_UNIT"          # scope 換了、property digest 沒換
    errors = probe.verify_probe_core_scope_binding(forged, rendered_unit=_rendered_unit())
    assert errors and "substitution rejected" in errors[0]
    driver = _FakeProbeDriver(property_digest=forged["transient_unit_property_digest"])
    intent = probe.build_capability_probe_intent(forged, expires_at=_EXPIRES, max_ttl_seconds=600)
    verdict = _run(intent, None, driver, scope="INSTALLED_UNIT")
    assert verdict["status"] == "PROBE_REQUEST_REJECTED" and driver.calls == []


def test_installed_unit_scope_requires_the_exact_rendered_unit() -> None:
    driver = _FakeProbeDriver(property_digest=_core("INSTALLED_UNIT")["transient_unit_property_digest"])
    verdict = probe.run_s2_4_capability_probe(
        _intent("INSTALLED_UNIT"), None, driver, now=_NOW, replay_ledger=_replay_ledger()
    )
    assert verdict["status"] == "PROBE_REQUEST_REJECTED"
    assert any("rendered unit" in reason for reason in verdict["reasons"])
    assert driver.calls == []
    # 被削弱的 unit(移除 IPAddressDeny)不可能換到 INSTALLED_UNIT 的 property digest。
    weakened = _rendered_unit().replace("IPAddressDeny=any\n", "")
    with pytest.raises(probe.ProbeContractError):
        probe.capability_probe_property_digest("INSTALLED_UNIT", rendered_unit=weakened)


def _terminal_pair(tmp_path, monkeypatch, scope):
    tmp_path.mkdir(parents=True, exist_ok=True)
    private_key, public_key, fingerprint = _mint_key(tmp_path, f"op-{scope}")
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    core = _core(scope)
    driver = _FakeProbeDriver(property_digest=core["transient_unit_property_digest"])
    verdict = _run(_intent(scope), _authorization(private_key), driver, scope=scope)
    assert verdict["status"] == "TERMINAL_CLEAN", verdict["reasons"]
    return verdict["attestation"], verdict["effect_receipt"]


def test_scope_attestations_are_not_interchangeable(tmp_path, monkeypatch) -> None:
    prepare = _terminal_pair(tmp_path / "prepare", monkeypatch, "PREPARE_SANDBOX")
    installed = _terminal_pair(tmp_path / "installed", monkeypatch, "INSTALLED_UNIT")
    for pair, own_scope, other_scope in (
        (prepare, "PREPARE_SANDBOX", "INSTALLED_UNIT"),
        (installed, "INSTALLED_UNIT", "PREPARE_SANDBOX"),
    ):
        attestation, receipt = pair
        assert probe.derive_scoped_capability_attestation_status(
            attestation, receipt, required_scope=own_scope, now=_NOW
        ) == {"status": "SCOPE_SATISFIED", "reasons": []}
        rejected = probe.derive_scoped_capability_attestation_status(
            attestation, receipt, required_scope=other_scope, now=_NOW
        )
        assert rejected["status"] == "SCOPE_SUBSTITUTION_REJECTED"
        assert any("never satisfies the other" in reason for reason in rejected["reasons"])


def test_final_unit_attestation_is_never_a_w6a_prerequisite(tmp_path, monkeypatch) -> None:
    prepare_attestation, prepare_receipt = _terminal_pair(
        tmp_path / "prepare", monkeypatch, "PREPARE_SANDBOX"
    )
    installed_attestation, installed_receipt = _terminal_pair(
        tmp_path / "installed", monkeypatch, "INSTALLED_UNIT"
    )
    prepare_only = {
        "PREPARE_SANDBOX": {
            "attestation": prepare_attestation, "effect_receipt": prepare_receipt
        }
    }
    # W6A:只有 PREPARE_SANDBOX 也 SATISFIED —— 無 output-derived admission cycle。
    w6a = probe.derive_probe_phase_prerequisite_status("W6A", prepare_only, now=_NOW)
    assert w6a["status"] == "PROBE_PREREQUISITE_SATISFIED"
    assert w6a["required_scopes"] == ["PREPARE_SANDBOX"]
    assert "INSTALLED_UNIT" not in probe.W6A_PREREQUISITE_PROBE_SCOPES
    # 只給 INSTALLED_UNIT 無法替代 W6A 的 PREPARE_SANDBOX 前置。
    installed_only = {
        "INSTALLED_UNIT": {
            "attestation": installed_attestation, "effect_receipt": installed_receipt
        }
    }
    assert probe.derive_probe_phase_prerequisite_status("W6A", installed_only, now=_NOW)[
        "status"
    ] == "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"
    # W6B 兩個 scope 都要。
    assert probe.derive_probe_phase_prerequisite_status("W6B", prepare_only, now=_NOW)[
        "status"
    ] == "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"
    assert probe.derive_probe_phase_prerequisite_status(
        "W6B", {**prepare_only, **installed_only}, now=_NOW
    )["status"] == "PROBE_PREREQUISITE_SATISFIED"


def test_attestation_without_its_terminal_receipt_is_unusable(tmp_path, monkeypatch) -> None:
    attestation, receipt = _terminal_pair(tmp_path, monkeypatch, "PREPARE_SANDBOX")
    orphan = deepcopy(receipt)
    orphan["network_sandbox_capability_attestation_digest"] = "sha256:" + "e" * 64
    orphan["self_digest"] = validator.artifact_self_digest(orphan)
    verdict = probe.derive_scoped_capability_attestation_status(
        attestation, orphan, required_scope="PREPARE_SANDBOX", now=_NOW
    )
    assert verdict["status"] == "SCOPE_SUBSTITUTION_REJECTED"
    assert any("terminal effect receipt is unusable" in r for r in verdict["reasons"])


# ── clean run / capability unsatisfied ──────────────────────────────────────────
def test_clean_probe_run_emits_terminal_receipt_with_zero_residue(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    core = _core()
    driver = _FakeProbeDriver(property_digest=core["transient_unit_property_digest"])
    verdict = _run(_intent(), _authorization(private_key), driver)
    assert verdict["status"] == "TERMINAL_CLEAN", verdict["reasons"]
    receipt = verdict["effect_receipt"]
    assert receipt["terminal_status"] == "TERMINAL_CLEAN"
    assert receipt["transient_unit_lifecycle"] == {
        "invocation_id": _INVOCATION,
        "unit_created": True,
        "unit_observed": True,
        "stopped_after_grace": True,
        "reset_failed": True,
        "removed": True,
        "zero_residue_verified": True,
    }
    assert receipt["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }
    # 每一件產物都過中央閘;receipt 綁 journal/postcheck/rollback/attestation 的 self_digest。
    for artifact in (
        receipt, verdict["attestation"], verdict["journal"],
        verdict["postcheck"], verdict["rollback"],
    ):
        assert validator.validate_aiml_artifact(artifact) == []
    assert receipt["journal_digest"] == verdict["journal"]["self_digest"]
    assert receipt["postcheck_digest"] == verdict["postcheck"]["self_digest"]
    assert receipt["rollback_digest"] == verdict["rollback"]["self_digest"]
    assert receipt["network_sandbox_capability_attestation_digest"] == (
        verdict["attestation"]["self_digest"]
    )
    assert verdict["rollback"]["status"] == "CLEANED_EXACT"
    assert verdict["postcheck"]["verifier_node"] != verdict["postcheck"]["applier_node"]
    # WAL:APPLYING 必為第一筆,且終端 journal 帶 VERIFIED。
    states = [entry["state"] for entry in verdict["journal"]["entries"]]
    assert states[0] == "APPLYING" and states[-1] == "VERIFIED"
    assert verdict["journal"]["terminal"] is True
    assert verdict["journal"]["cleanup_rollback_digest"] == validator.canonical_digest(
        probe.capability_probe_cleanup_contract(
            probe_id=receipt["probe_id"],
            derived_unit_name=receipt["derived_unit_name"],
            cleanup_budget=core["cleanup_budget"],
        )
    )


def test_unverified_isolation_returns_typed_capability_unsatisfied(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    core = _core()
    driver = _FakeProbeDriver(
        property_digest=core["transient_unit_property_digest"],
        network_isolation_verified=False,
    )
    verdict = _run(_intent(), _authorization(private_key), driver)
    assert verdict["status"] == "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"
    assert verdict["effect_receipt"]["terminal_status"] == "TERMINAL_FAILED"
    assert verdict["rollback"]["status"] == "CLEANED_EXACT"      # 清理仍然是精確的
    # 這份 attestation 不能滿足任何 scope 消費者。
    assert probe.derive_scoped_capability_attestation_status(
        verdict["attestation"], verdict["effect_receipt"],
        required_scope="PREPARE_SANDBOX", now=_NOW,
    )["status"] == "SCOPE_SUBSTITUTION_REJECTED"


def test_consumed_replay_id_cannot_authorize_a_second_probe(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    authorization = _authorization(private_key)
    ledger = _replay_ledger([
        {
            "authorization_id": authorization["authorization_id"],
            "authorization_digest": authorization["self_digest"],
            "profile_identity": authorization["profile_identity"],
        }
    ])
    driver = _FakeProbeDriver(property_digest=_core()["transient_unit_property_digest"])
    verdict = _run(_intent(), authorization, driver, replay_ledger=ledger)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("already consumed" in reason for reason in verdict["reasons"])
    assert driver.calls == []


# ── §10.5 #39 fault injection matrix ────────────────────────────────────────────
_FAULT_LABELS = [
    "pre_journal_applying", "post_journal_applying",
    "pre_start_unit", "post_start_unit",
    "pre_journal_applied", "post_journal_applied",
    "pre_read_properties", "post_read_properties",
    "pre_journal_verifying", "post_journal_verifying",
    "pre_observe_egress", "post_observe_egress",
    "pre_stop", "post_stop",
    "pre_reset_failed", "post_reset_failed",
    "pre_remove", "post_remove",
    "pre_sweep", "post_sweep",
]


@pytest.mark.parametrize("label", _FAULT_LABELS)
def test_crash_before_and_after_every_dbus_and_journal_transition(
    tmp_path, monkeypatch, label
) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    core = _core()
    driver = _FakeProbeDriver(property_digest=core["transient_unit_property_digest"])
    latch = probe.ProbeRecoveryState()

    def fault(seen: str) -> None:
        if seen == label:
            raise RuntimeError(f"injected crash at {label}")

    verdict = _run(
        _intent(), _authorization(private_key), driver,
        fault=fault, recovery_state=latch,
    )
    assert verdict["status"] != "TERMINAL_CLEAN"
    if label == "pre_journal_applying":
        # WAL 未記 APPLYING:沒有任何 D-Bus 呼叫,無殘留可談。
        assert verdict["status"] == "TERMINAL_FAILED"
        assert verdict["mutation_performed"] is False
        assert driver.calls == []
        assert latch.unresolved is None
    else:
        # 一旦 APPLYING 入 WAL,任何失敗都必須走 cleanup 並閂住 recovery。
        assert verdict["status"] == "RECOVERY_REQUIRED"
        assert latch.unresolved is not None
        assert latch.unresolved["derived_unit_name"] == verdict["derived_unit_name"]
        # cleanup 要嘛真跑過(stop 被呼叫),要嘛正是被注入的崩潰點打斷 → typed 記為未完成。
        assert "stop_transient_unit" in driver.calls or any(
            "cleanup did not complete" in reason for reason in verdict["reasons"]
        )
    assert verdict["blocks_next_phase"] is True
    assert verdict["effect_receipt"] is None


def test_no_new_probe_starts_while_recovery_is_unresolved(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    core = _core()
    latch = probe.ProbeRecoveryState()
    broken = _FakeProbeDriver(
        property_digest=core["transient_unit_property_digest"],
        residue={"unit_absent": False, "cgroup_absent": False,
                 "process_absent": False, "task_files_absent": False},
    )
    first = _run(_intent(), _authorization(private_key), broken, recovery_state=latch)
    assert first["status"] == "RECOVERY_REQUIRED" and latch.unresolved is not None
    # 第二次:即使一切正常,recovery 未解就不得起新 probe(零 driver 接觸)。
    healthy = _FakeProbeDriver(property_digest=core["transient_unit_property_digest"])
    second = _run(_intent(), _authorization(private_key), healthy, recovery_state=latch)
    assert second["status"] == "RECOVERY_REQUIRED"
    assert any("no new probe may start" in reason for reason in second["reasons"])
    assert healthy.calls == []
    # 錯的 probe_id 不能解閂;正確解閂後才可再跑。
    with pytest.raises(probe.ProbeContractError):
        latch.resolve(probe_id="s2-4-probe-" + "0" * 64, resolution_note="wrong")
    latch.resolve(probe_id=first["probe_id"], resolution_note="operator cleaned the residue")
    assert latch.unresolved is None
    third = _run(_intent(), _authorization(private_key), healthy, recovery_state=latch)
    assert third["status"] == "TERMINAL_CLEAN"


def test_authorization_expiry_during_execution_leaves_only_cleanup_authority(
    tmp_path, monkeypatch
) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    core = _core()
    driver = _FakeProbeDriver(property_digest=core["transient_unit_property_digest"])
    latch = probe.ProbeRecoveryState()
    ticks = iter([
        _ANCHOR + timedelta(minutes=3),    # APPLYING journal
        _ANCHOR + timedelta(minutes=3),    # _require_live(create)
        _ANCHOR + timedelta(minutes=3),    # APPLIED journal
        _ANCHOR + timedelta(minutes=30),   # _require_live(observe) → 已過期
    ])
    last = [_ANCHOR + timedelta(minutes=30)]

    def clock():
        try:
            value = next(ticks)
        except StopIteration:
            value = last[0]
        return value

    verdict = _run(
        _intent(), _authorization(private_key), driver,
        clock=clock, recovery_state=latch,
    )
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert any("only the exact cleanup authority remained" in r for r in verdict["reasons"])
    # 過期後只剩 exact cleanup 權限:沒有新的建立/觀測,egress 與屬性讀取都不曾發生。
    assert "observe_egress" not in driver.calls
    assert "read_unit_properties" not in driver.calls
    assert driver.calls.count("start_transient_unit") == 1
    after_expiry = driver.calls[driver.calls.index("journal:APPLIED") + 1:]
    assert [call for call in after_expiry if not call.startswith("journal:")] == [
        "stop_transient_unit", "reset_failed", "remove_transient_unit", "sweep_residue"
    ]
    assert verdict["rollback"]["status"] == "CLEANED_EXACT"
    assert latch.unresolved is not None


@pytest.mark.parametrize("mutation", ["invocation_id", "cgroup", "property_digest"])
def test_mismatched_invocation_cgroup_or_property_state_is_recovery_required(
    tmp_path, monkeypatch, mutation
) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    core = _core()
    kwargs = {"property_digest": core["transient_unit_property_digest"]}
    if mutation == "invocation_id":
        driver = _FakeProbeDriver(**kwargs)
        driver.read_unit_properties = lambda *, unit_name: {
            "invocation_id": "b" * 32,
            "cgroup": f"{_CGROUP_ROOT}/{unit_name}",
            "property_digest": core["transient_unit_property_digest"],
        }
    elif mutation == "cgroup":
        driver = _FakeProbeDriver(cgroup_root="/sys/fs/cgroup/user.slice", **kwargs)
    else:
        driver = _FakeProbeDriver(property_digest="sha256:" + "d" * 64)
    latch = probe.ProbeRecoveryState()
    verdict = _run(_intent(), _authorization(private_key), driver, recovery_state=latch)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert latch.unresolved is not None
    assert "observe_egress" not in driver.calls


def test_applier_cannot_be_its_own_cleanup_verifier(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    core = _core()
    driver = _FakeProbeDriver(
        property_digest=core["transient_unit_property_digest"],
        verifier_node="s2-4-probe-applier",
    )
    verdict = _run(_intent(), _authorization(private_key), driver)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert any("must differ from the applier" in reason for reason in verdict["reasons"])


def test_probe_never_declares_a_production_or_running_claim(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = _mint_key(tmp_path)
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    core = _core()
    driver = _FakeProbeDriver(property_digest=core["transient_unit_property_digest"])
    verdict = _run(_intent(), _authorization(private_key), driver)
    assert verdict["attestation"]["production_posture"] == {
        "is_runtime_production_pass": False,
        "production_apply_performed": False,
        "running_attested": False,
        "nine_authorities_false": True,
    }
    assert verdict["status"] in probe.PROBE_TYPED_STATUSES

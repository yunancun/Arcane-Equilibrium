from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "deploy_intent_adapter.py"
)


def _load_adapter():
    spec = importlib.util.spec_from_file_location("deploy_intent_adapter", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _intent(environment_identity: str) -> dict:
    head = "a" * 40
    return {
        "schema_version": "deployment_intent_v1",
        "intent_id": "deploy-env-0001",
        "target_host": "trade-core-runtime",
        "target_environment": "demo",
        "expected_source_head": head,
        "expected_deploy_script_sha256": "sha256:" + "b" * 64,
        "expected_runtime_environment_identity_digest": environment_identity,
        "require_clean_tree": True,
        "approved_by": "operator",
        "approved_at": "2026-07-11T10:00:00Z",
        "expires_at": "2026-07-11T12:00:00Z",
        "typed_confirm": f"deploy:trade-core-runtime:{head}:deploy-env-0001",
        "hard_stops": [
            "no live/mainnet authority expansion",
            "no risk/cost-gate/decision-lease bypass",
        ],
    }


def test_demo_label_cannot_authorize_a_mainnet_runtime_attestation() -> None:
    adapter = _load_adapter()
    attestation = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_mainnet",
        allow_mainnet=True,
        runtime_mode="mainnet",
        authorization_scope="mainnet",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at="2026-07-11T10:10:00Z",
        expires_at="2026-07-11T10:20:00Z",
    )
    intent = _intent(attestation["environment_identity_digest"])

    errors = adapter.validate_runtime_attestation_for_intent(
        attestation,
        intent,
        phase="preflight",
        now="2026-07-11T10:15:00Z",
    )

    assert any("mainnet" in error or "safe runtime" in error for error in errors)


def test_safe_demo_attestation_is_fresh_self_hashed_and_intent_bound() -> None:
    adapter = _load_adapter()
    attestation = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="demo",
        authorization_scope="demo_only",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at="2026-07-11T10:10:00Z",
        expires_at="2026-07-11T10:20:00Z",
    )
    intent = _intent(attestation["environment_identity_digest"])

    assert adapter.validate_runtime_attestation_for_intent(
        attestation,
        intent,
        phase="preflight",
        now="2026-07-11T10:15:00Z",
    ) == []
    assert adapter.validate_intent(
        intent,
        supplied_intent_digest="sha256:" + "e" * 64,
        actual_intent_digest="sha256:" + "e" * 64,
        actual_source_head="a" * 40,
        tree_clean=True,
        actual_host="trade-core-runtime",
        deploy_script_digest="sha256:" + "b" * 64,
        now="2026-07-11T10:15:00Z",
    ) == []


def test_actual_apply_stays_disabled_without_a_reproducible_local_probe(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    adapter = _load_adapter()
    now = datetime.now(timezone.utc)
    observed = now - timedelta(minutes=1)
    attestation = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="demo",
        authorization_scope="demo_only",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at=observed.isoformat(),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
    )
    intent = _intent(attestation["environment_identity_digest"])
    intent["approved_at"] = (now - timedelta(minutes=2)).isoformat()
    intent["expires_at"] = (now + timedelta(hours=1)).isoformat()
    intent["expected_deploy_script_sha256"] = adapter.sha256_bytes(
        adapter.DEPLOY_COMPONENT.read_bytes()
    )
    intent_path = tmp_path / "intent.json"
    attestation_path = tmp_path / "runtime-attestation.json"
    intent_bytes = json.dumps(intent, sort_keys=True, separators=(",", ":")).encode()
    intent_path.write_bytes(intent_bytes)
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")

    monkeypatch.setattr(
        adapter,
        "git_text",
        lambda *args: "a" * 40 if args == ("rev-parse", "HEAD") else "",
    )
    monkeypatch.setattr(adapter.socket, "gethostname", lambda: "trade-core-runtime")
    intent_only_exit = adapter.main(
        [
            "--intent",
            str(intent_path),
            "--intent-sha256",
            adapter.sha256_bytes(intent_bytes),
        ]
    )
    intent_only_status = json.loads(capsys.readouterr().out)
    assert intent_only_exit == 0
    assert intent_only_status["status"] == "INTENT_VALIDATED_APPLY_DISABLED"
    assert intent_only_status["apply_executable"] is False

    monkeypatch.setenv("OPENCLAW_DEPLOY_ADAPTER_APPLY", "1")

    def forbidden_component(*_args, **_kwargs):
        raise AssertionError("deploy component must not run without a local probe")

    monkeypatch.setattr(adapter.subprocess, "run", forbidden_component)
    exit_code = adapter.main(
        [
            "--intent",
            str(intent_path),
            "--intent-sha256",
            adapter.sha256_bytes(intent_bytes),
            "--runtime-attestation",
            str(attestation_path),
            "--apply",
        ]
    )

    assert exit_code != 0


def test_effect_receipt_binds_pre_and_post_runtime_identity() -> None:
    adapter = _load_adapter()
    preflight = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="demo",
        authorization_scope="demo_only",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at="2026-07-11T10:10:00Z",
        expires_at="2026-07-11T10:20:00Z",
    )
    postcheck = adapter.build_runtime_environment_attestation(
        phase="postcheck",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="demo",
        authorization_scope="demo_only",
        process_identity_digest="sha256:" + "e" * 64,
        observed_at="2026-07-11T10:16:00Z",
        expires_at="2026-07-11T10:26:00Z",
    )
    intent = _intent(preflight["environment_identity_digest"])
    receipt = adapter.build_effect_receipt(
        intent,
        intent_digest="sha256:" + "f" * 64,
        component_exit_code=0,
        component_stdout=(
            b">>> DEPLOY-ATOMIC-VERIFIED: NEW_PID=123 POST_SHA=" + b"e" * 64 + b"\n"
        ),
        component_stderr=b"",
        started_at="2026-07-11T10:12:00Z",
        completed_at="2026-07-11T10:15:00Z",
        pre_runtime_attestation=preflight,
        post_runtime_attestation=postcheck,
    )

    assert receipt["effect_status"] == "APPLIED_VERIFIED"
    assert receipt["runtime_environment_identity_digest"] == intent[
        "expected_runtime_environment_identity_digest"
    ]
    assert receipt["pre_runtime_attestation"] == preflight
    assert receipt["post_runtime_attestation"] == postcheck
    assert adapter.parse_time(receipt["evidence_expires_at"]) == adapter.parse_time(
        postcheck["expires_at"]
    )
    assert adapter.validate_effect_receipt(receipt, require_success=True) == []

    ops_postcheck = adapter.build_ops_evidence(
        receipt,
        phase="postcheck",
        observed_at=postcheck["observed_at"],
        evidence_id="ev-ops-post",
        expiry=postcheck["expires_at"],
        running_binary_sha256=receipt["deployed_binary_sha256"],
    )
    operation_receipt = ops_postcheck["operation_receipt"]
    assert operation_receipt["runtime_environment_identity_digest"] == postcheck[
        "environment_identity_digest"
    ]
    assert operation_receipt["runtime_attestation_digest"] == postcheck[
        "attestation_digest"
    ]
    assert operation_receipt["actual_endpoint_class"] == "bybit_demo"
    assert operation_receipt["allow_mainnet"] is False
    assert operation_receipt["running_binary_sha256"] == postcheck[
        "process_identity_digest"
    ]
    receipt_schema = json.loads(
        (ROOT / ".codex/schemas/effect_adapter_result_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt_schema["properties"]["pre_runtime_attestation"] == {
        "$ref": "#/$defs/runtimeAttestation"
    }
    assert receipt_schema["properties"]["post_runtime_attestation"] == {
        "$ref": "#/$defs/runtimeAttestation"
    }
    runtime_schema = json.loads(
        (ROOT / ".codex/schemas/runtime_environment_attestation_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt_schema["$defs"]["runtimeAttestation"] == {
        key: runtime_schema[key]
        for key in ("type", "additionalProperties", "required", "properties")
    }

    with pytest.raises(ValueError, match="must match runtime attestation"):
        adapter.build_ops_evidence(
            receipt,
            phase="postcheck",
            observed_at=postcheck["observed_at"],
            evidence_id="ev-ops-post-relabelled",
            expiry="2026-07-11T10:30:00Z",
            running_binary_sha256=receipt["deployed_binary_sha256"],
        )


def test_postdeploy_mainnet_drift_cannot_produce_a_success_receipt() -> None:
    adapter = _load_adapter()
    preflight = adapter.build_runtime_environment_attestation(
        phase="preflight",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_demo",
        allow_mainnet=False,
        runtime_mode="demo",
        authorization_scope="demo_only",
        process_identity_digest="sha256:" + "d" * 64,
        observed_at="2026-07-11T10:10:00Z",
        expires_at="2026-07-11T10:20:00Z",
    )
    unsafe_postcheck = adapter.build_runtime_environment_attestation(
        phase="postcheck",
        host="trade-core-runtime",
        source_head="a" * 40,
        config_identity_digest="sha256:" + "c" * 64,
        actual_endpoint_class="bybit_mainnet",
        allow_mainnet=True,
        runtime_mode="mainnet",
        authorization_scope="mainnet",
        process_identity_digest="sha256:" + "e" * 64,
        observed_at="2026-07-11T10:16:00Z",
        expires_at="2026-07-11T10:26:00Z",
    )
    intent = _intent(preflight["environment_identity_digest"])
    receipt = adapter.build_effect_receipt(
        intent,
        intent_digest="sha256:" + "f" * 64,
        component_exit_code=0,
        component_stdout=(
            b">>> DEPLOY-ATOMIC-VERIFIED: NEW_PID=123 POST_SHA=" + b"e" * 64 + b"\n"
        ),
        component_stderr=b"",
        started_at="2026-07-11T10:12:00Z",
        completed_at="2026-07-11T10:15:00Z",
        pre_runtime_attestation=preflight,
        post_runtime_attestation=unsafe_postcheck,
    )

    assert receipt["effect_status"] == "FAILED"
    assert adapter.validate_effect_receipt(receipt, require_success=True)

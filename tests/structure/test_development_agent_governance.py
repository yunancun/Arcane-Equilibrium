from __future__ import annotations

import importlib.util
import hashlib
import json
import re
import subprocess
try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 runner
    import tomli as tomllib  # type: ignore[no-redef]
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_FILE_LINES = 2_000


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "agent_governance.py"
)
DEPLOY_ADAPTER_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "deploy_intent_adapter.py"
)
SCHEMA_VALIDATOR_PATH = (
    ROOT / "helper_scripts" / "maintenance_scripts" / "agent_governance_schema.py"
)
CONTEXT_ARTIFACT_FIXTURES = {
    "current diff": "tests/fixtures/agent_governance/context/current-diff.json",
    "direct interfaces": "tests/fixtures/agent_governance/context/direct-interfaces.json",
    "direct callers": "tests/fixtures/agent_governance/context/direct-callers.json",
    "focused acceptance tests": (
        "tests/fixtures/agent_governance/context/focused-acceptance-tests.json"
    ),
}


def _load_module():
    spec = importlib.util.spec_from_file_location("agent_governance", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_deploy_adapter():
    spec = importlib.util.spec_from_file_location("deploy_intent_adapter", DEPLOY_ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_schema_validator():
    spec = importlib.util.spec_from_file_location(
        "agent_governance_schema_for_test", SCHEMA_VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_digest(value) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _test_execution_attestation_verifier(packet: dict):
    """Simulate host-held anchors; never derive these inside production closure."""

    context = packet["dispatch"]["context_artifact"]
    anchors = {("context_artifact_v1", context["artifact_digest"])}
    for evidence in packet.get("evidence", []):
        kind = evidence.get("kind")
        artifact = evidence.get("artifact")
        if kind == "workflow_wave_record_v1" and isinstance(artifact, dict):
            anchors.add((kind, artifact.get("record_digest")))
        elif kind == "effect_adapter_result_v1" and isinstance(
            evidence.get("receipt"), dict
        ):
            anchors.add((kind, evidence["receipt"].get("receipt_digest")))
        elif isinstance(artifact, dict) and artifact.get("schema_version") in {
            "runtime_observation_receipt_v1", "business_outcome_receipt_v1",
        }:
            anchors.add((artifact["schema_version"], artifact.get("receipt_digest")))
        elif (
            kind == "telemetry_record_v1"
            and isinstance(artifact, dict)
            and artifact.get("trust_tier") == "PLATFORM_OR_EXTERNAL_ATTESTED"
        ):
            anchors.add((kind, artifact.get("record_digest")))

    return lambda kind, digest, _artifact: (kind, digest) in anchors


def _bind_demo_runtime_attestations(
    adapter,
    intent: dict,
    *,
    deployed_digest: str,
    pre_observed_at: str,
    pre_expires_at: str,
    post_observed_at: str,
    post_expires_at: str,
) -> tuple[dict, dict]:
    common = {
        "host": intent["target_host"],
        "source_head": intent["expected_source_head"],
        "config_identity_digest": "sha256:" + "6" * 64,
        "actual_endpoint_class": "bybit_demo",
        "allow_mainnet": False,
        "runtime_mode": "demo",
        "authorization_scope": "demo_only",
    }
    preflight = adapter.build_runtime_environment_attestation(
        phase="preflight",
        process_identity_digest="sha256:" + "5" * 64,
        observed_at=pre_observed_at,
        expires_at=pre_expires_at,
        **common,
    )
    intent["expected_runtime_environment_identity_digest"] = preflight[
        "environment_identity_digest"
    ]
    postcheck = adapter.build_runtime_environment_attestation(
        phase="postcheck",
        process_identity_digest=deployed_digest,
        observed_at=post_observed_at,
        expires_at=post_expires_at,
        **common,
    )
    return preflight, postcheck


def test_registry_is_single_valid_interface_and_views_are_current(tmp_path: Path) -> None:
    governance = _load_module()
    registry = governance.load_registry()

    assert governance.validate_registry(registry, ROOT) == []
    assert {"OPS", "IB"}.issubset(registry["roles"])
    assert registry["context_evidence_schema_path"] == (
        ".codex/schemas/context_evidence_artifact_v1.schema.json"
    )

    rendered = governance.render_views(registry, ROOT)
    assert rendered
    assert all(path.read_text(encoding="utf-8") == content for path, content in rendered.items())
    assert all(
        "`agent_governance.py authorize-command" not in content
        for content in rendered.values()
    )
    assert "`agent_governance.py render --check`" not in rendered[ROOT / ".codex/agents/INDEX.md"]
    assert "fragment for PM to merge" not in rendered[ROOT / ".claude/agents/PM.md"]
    assert "single final closure packet" in rendered[ROOT / ".claude/agents/PM.md"]
    native_paths = {
        path for path in rendered
        if path.parent == ROOT / ".codex/agents" and path.suffix == ".toml"
    }
    expected_native_names = (
        set(registry["roles"]) - {"PA", "E4"}
    ) | {"PA-design-writer", "PA-investigator", "E4-writer", "E4-verifier"}
    assert {path.stem for path in native_paths} == expected_native_names
    claude_paths = {
        path for path in rendered
        if path.parent == ROOT / ".claude/agents" and path.suffix == ".md"
    }
    assert {path.stem for path in claude_paths} == expected_native_names
    for path in native_paths:
        native = tomllib.loads(rendered[path])
        assert native["name"] == path.stem
        assert native["description"]
        assert native["developer_instructions"]
        assert native["model_reasoning_effort"] == "high"
        assert native["sandbox_mode"] in {"read-only", "workspace-write"}
        assert "model" not in native
        if native["sandbox_mode"] == "read-only":
            assert not re.search(
                r"\b(writes?|writer|implementation owner)\b",
                native["description"],
                re.IGNORECASE,
            )
            owns = native["developer_instructions"].split("Own:\n", 1)[1].split(
                "\n\nRefuse:", 1
            )[0]
            assert not re.search(
                r"\b(writes?|writer|implementation)\b", owns, re.IGNORECASE
            )
    assert tomllib.loads(rendered[ROOT / ".codex/agents/E4-writer.toml"])[
        "sandbox_mode"
    ] == "workspace-write"
    assert tomllib.loads(rendered[ROOT / ".codex/agents/E4-verifier.toml"])[
        "sandbox_mode"
    ] == "read-only"
    assert tomllib.loads(rendered[ROOT / ".codex/agents/PA-design-writer.toml"])[
        "sandbox_mode"
    ] == "workspace-write"
    assert tomllib.loads(rendered[ROOT / ".codex/agents/PA-investigator.toml"])[
        "sandbox_mode"
    ] == "read-only"
    assert ROOT / ".codex/agents/E4.toml" not in rendered
    assert ROOT / ".codex/agents/PA.toml" not in rendered
    assert ROOT / ".claude/agents/E4.md" not in rendered
    assert ROOT / ".claude/agents/PA.md" not in rendered
    pa_investigator = rendered[ROOT / ".claude/agents/PA-investigator.md"]
    e4_verifier = rendered[ROOT / ".claude/agents/E4-verifier.md"]
    for name, content in (
        ("PA-investigator", pa_investigator),
        ("E4-verifier", e4_verifier),
    ):
        frontmatter = content.split("---", 2)[1]
        assert f"name: {name}" in frontmatter
        tools_line = next(
            line for line in frontmatter.splitlines() if line.startswith("tools:")
        )
        assert all(tool not in tools_line for tool in ("Edit", "Write", "NotebookEdit"))
        assert "Permission profile: `read_only`" in content
        assert f"capture-command --native-agent {name}" in content
        assert "--node-id <admitted-node-id>" in content
    assert "Permission profile: `design_writer`" in rendered[
        ROOT / ".claude/agents/PA-design-writer.md"
    ]
    assert "Permission profile: `test_writer`" in rendered[
        ROOT / ".claude/agents/E4-writer.md"
    ]
    assert ROOT / ".codex/config.toml" not in rendered
    assert ".codex/agents/<NATIVE_AGENT>.toml" in registry["generated_views"]
    assert ".claude/agents/<NATIVE_AGENT>.md" in registry["generated_views"]
    assert "Native Codex TOML" in rendered[ROOT / ".codex/agents/INDEX.md"]
    skill_index = rendered[ROOT / ".codex/skills/INDEX.md"]
    for role, spec in registry["roles"].items():
        for skill in spec["skills"]:
            row = next(line for line in skill_index.splitlines() if line.startswith(f"| `{skill}` |"))
            assert f"`{role}`" in row
    assert "on-demand: explicit full/cold audit" in skill_index

    ghost = tmp_path / ".codex/agents/OLD.md"
    ghost.parent.mkdir(parents=True)
    ghost.write_text("stale generated role", encoding="utf-8")
    assert ".codex/agents/OLD.md" in governance.render_all(registry, tmp_path, check=True)
    ghost_native = tmp_path / ".codex/agents/OLD.toml"
    ghost_native.write_text('name = "OLD"\n', encoding="utf-8")
    assert ".codex/agents/OLD.toml" in governance.render_all(registry, tmp_path, check=True)

    implementation_files = list(
        (ROOT / "helper_scripts/maintenance_scripts").glob("agent_governance*.py")
    ) + [DEPLOY_ADAPTER_PATH]
    assert implementation_files
    for path in implementation_files:
        assert len(path.read_text(encoding="utf-8").splitlines()) <= MAX_FILE_LINES, path

    adapters = registry["effect_adapters"]
    assert adapters["deploy_adapter_v1"]["implementation_paths"] == [
        "helper_scripts/maintenance_scripts/deploy_intent_adapter.py",
        "helper_scripts/maintenance_scripts/runtime_environment_probe.py",
        "helper_scripts/maintenance_scripts/agent_governance_effects.py",
        "helper_scripts/maintenance_scripts/agent_governance_execution_attestation.py",
    ]
    assert adapters["deploy_adapter_v1"]["status"] == (
        "declared_apply_disabled_until_recovery_controls_bound"
    )
    assert adapters["deploy_adapter_v1"]["component_paths"] == [
        "helper_scripts/build_then_restart_atomic.sh"
    ]
    assert adapters["deploy_adapter_v1"]["receipt_schema_path"] == (
        ".codex/schemas/effect_adapter_result_v1.schema.json"
    )
    assert adapters["report_sink_v1"]["implementation_paths"] == [
        "helper_scripts/maintenance_scripts/agent_governance.py"
    ]
    assert adapters["broker_probe_adapter_v1"]["implementations"]["bybit"]["status"] == (
        "runtime_owned_no_development_agent_entrypoint"
    )
    for adapter in adapters.values():
        for path in adapter.get("implementation_paths", []):
            assert (ROOT / path).is_file(), path
        for path in adapter.get("component_paths", []):
            assert (ROOT / path).is_file(), path
        for implementation in adapter.get("implementations", {}).values():
            for path in implementation.get("paths", []):
                assert (ROOT / path).is_file(), path

    full_audit_contract = registry["workflow_contracts"]["full_audit_v3"]
    audit_source = (ROOT / ".claude/workflows/openclaw-full-audit.js").read_text(
        encoding="utf-8"
    )
    axis_literal = re.search(r"const ALL_AXES = \[(.*?)\]", audit_source)
    assert axis_literal
    workflow_axes = re.findall(r"'([^']+)'", axis_literal.group(1))
    assert workflow_axes == full_audit_contract["axes"]


def test_native_agents_bind_one_call_capture_and_effect_boundaries() -> None:
    governance = _load_module()
    registry = governance.load_registry()
    rendered = governance.render_views(registry, ROOT)
    role_by_native = {
        adapter["name"]: role
        for role, adapters in registry["native_agent_adapters"].items()
        for adapter in adapters
    }
    role_by_native.update({
        role: role for role in registry["roles"]
        if role not in registry["native_agent_adapters"]
    })

    for native_name, role in role_by_native.items():
        native = tomllib.loads(
            rendered[ROOT / f".codex/agents/{native_name}.toml"]
        )
        instructions = native["developer_instructions"]
        assert "private/authenticated" in instructions
        tools = registry["roles"][role]["tools"]
        if {"WebSearch", "WebFetch"}.intersection(tools):
            assert "Web tools require public_web_read in the task_contract" in instructions
            assert "external_evidence_capture_v1" in instructions
        else:
            assert "no admitted public-web tool" in instructions
        if native["sandbox_mode"] == "read-only":
            assert (
                "python3 helper_scripts/maintenance_scripts/agent_governance.py "
                f"capture-command --native-agent {native_name} "
                "--node-id <admitted-node-id> --context-artifact @<context.json> -- <argv...>"
            ) in instructions
            assert "never run the argv separately" in instructions
            assert "effect boundary is repository_policy_only" in instructions


def test_web_tools_are_sparse_and_high_cost_skills_are_on_demand() -> None:
    governance = _load_module()
    registry = governance.load_registry()
    web_roles = {
        role for role, spec in registry["roles"].items()
        if {"WebSearch", "WebFetch"}.intersection(spec["tools"])
    }
    assert web_roles == {"AI-E", "BB", "E3", "IB", "MIT", "QC"}
    assert all(
        {"WebSearch", "WebFetch"}.issubset(registry["roles"][role]["tools"])
        for role in web_roles
    )
    assert registry["on_demand_skills"]["architecture-depth-review"]["owners"] == ["PA"]
    assert set(registry["on_demand_skills"]["16-root-principles-checklist"]["owners"]) == {
        "CC", "PA", "PM",
    }
    assert all(
        "16-root-principles-checklist" not in spec["skills"]
        for spec in registry["roles"].values()
    )
    rendered = governance.render_views(registry, ROOT)
    for role in ("PM", "CC"):
        assert "never preload" in rendered[ROOT / f".codex/agents/{role}.toml"]
    pa = rendered[ROOT / ".codex/agents/PA-investigator.toml"]
    assert "`.agents/skills/architecture-depth-review/SKILL.md`" in pa
    assert registry["on_demand_skills"]["architecture-depth-review"]["activation"] in pa
    assert not any(
        re.search(r"(?m)^skills:\s*$", content)
        for path, content in rendered.items()
        if path.parent == ROOT / ".claude/agents"
    )


def test_deploy_adapter_binds_intent_head_host_expiry_and_component_bytes() -> None:
    adapter = _load_deploy_adapter()

    head = "a" * 40
    component_digest = "sha256:" + "b" * 64
    intent = {
        "schema_version": "deployment_intent_v1",
        "intent_id": "deploy-0001",
        "target_host": "trade-core-runtime",
        "target_environment": "demo",
        "expected_source_head": head,
        "expected_deploy_script_sha256": component_digest,
        "require_clean_tree": True,
        "approved_by": "operator",
        "approved_at": "2026-07-10T12:00:00Z",
        "expires_at": "2026-07-10T14:00:00Z",
        "typed_confirm": f"deploy:trade-core-runtime:{head}:deploy-0001",
        "hard_stops": [
            "no live/mainnet authority expansion",
            "no risk/cost-gate/decision-lease bypass",
        ],
    }
    preflight_attestation, postcheck_attestation = _bind_demo_runtime_attestations(
        adapter,
        intent,
        deployed_digest="sha256:" + "d" * 64,
        pre_observed_at="2026-07-10T13:00:00Z",
        pre_expires_at="2026-07-10T13:10:00Z",
        post_observed_at="2026-07-10T13:03:00Z",
        post_expires_at="2026-07-10T13:13:00Z",
    )
    facts = {
        "supplied_intent_digest": "sha256:" + "c" * 64,
        "actual_intent_digest": "sha256:" + "c" * 64,
        "actual_source_head": head,
        "tree_clean": True,
        "actual_host": "trade-core-runtime",
        "deploy_script_digest": component_digest,
        "now": "2026-07-10T13:00:00Z",
    }
    assert adapter.validate_intent(intent, **facts) == []

    invalid_intent = deepcopy(intent)
    invalid_intent["hard_stops"].append("")
    assert any(
        "deployment intent schema violation" in error and "minLength" in error
        for error in adapter.validate_intent(invalid_intent, **facts)
    )

    for field, changed in (
        ("actual_intent_digest", "sha256:" + "d" * 64),
        ("actual_source_head", "e" * 40),
        ("tree_clean", False),
        ("actual_host", "wrong-host"),
        ("deploy_script_digest", "sha256:" + "f" * 64),
        ("now", "2026-07-10T15:00:00Z"),
    ):
        invalid = dict(facts)
        invalid[field] = changed
        assert adapter.validate_intent(intent, **invalid), field

    receipt = adapter.build_effect_receipt(
        intent,
        intent_digest=facts["actual_intent_digest"],
        component_exit_code=0,
        component_stdout=(
            b"phase\n>>> DEPLOY-ATOMIC-VERIFIED: NEW_PID=123 POST_SHA="
            + b"d" * 64
            + b"\n"
        ),
        component_stderr=b"",
        started_at="2026-07-10T13:01:00Z",
        completed_at="2026-07-10T13:02:00Z",
        pre_runtime_attestation=preflight_attestation,
        post_runtime_attestation=postcheck_attestation,
    )
    assert receipt["schema_version"] == "effect_adapter_result_v1"
    assert receipt["effect_status"] == "APPLIED_VERIFIED"
    assert receipt["deployed_binary_sha256"] == "sha256:" + "d" * 64
    assert receipt["runtime_environment_identity_digest"] == preflight_attestation[
        "environment_identity_digest"
    ]
    assert receipt["post_runtime_attestation"]["actual_endpoint_class"] == "bybit_demo"
    assert adapter.validate_effect_receipt(receipt, require_success=True) == []
    assert receipt["receipt_digest"] == adapter.effect_receipt_digest(receipt)
    assert adapter.effect_receipt_digest(dict(reversed(list(receipt.items())))) == receipt[
        "receipt_digest"
    ]
    receipt_schema = json.loads(
        (ROOT / ".codex/schemas/effect_adapter_result_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(receipt_schema["required"]) == set(receipt)

    tampered = deepcopy(receipt)
    tampered["target_host"] = "forged-host"
    assert "receipt_digest does not match canonical receipt" in adapter.validate_effect_receipt(
        tampered, require_success=True
    )

    schema_drift_attack = deepcopy(receipt)
    schema_drift_attack["hard_stops"].append("")
    schema_drift_attack["receipt_digest"] = adapter.effect_receipt_digest(
        schema_drift_attack
    )
    assert any(
        "schema violation" in error and "minLength" in error
        for error in adapter.validate_effect_receipt(
            schema_drift_attack, require_success=True
        )
    )

    missing_marker = adapter.build_effect_receipt(
        intent,
        intent_digest=facts["actual_intent_digest"],
        component_exit_code=0,
        component_stdout=b"component returned zero without proof marker\n",
        component_stderr=b"",
        started_at="2026-07-10T13:01:00Z",
        completed_at="2026-07-10T13:02:00Z",
        pre_runtime_attestation=preflight_attestation,
        post_runtime_attestation=postcheck_attestation,
    )
    assert missing_marker["effect_status"] == "FAILED"
    assert adapter.validate_effect_receipt(missing_marker, require_success=True)

    invalid_generated = deepcopy(receipt)
    invalid_generated["hard_stops"].append("")
    invalid_generated["receipt_digest"] = adapter.effect_receipt_digest(invalid_generated)
    receipt_exit, receipt_errors = adapter.generated_receipt_result(invalid_generated)
    assert receipt_exit == 3
    assert receipt_errors

    adapter_source = DEPLOY_ADAPTER_PATH.read_text(encoding="utf-8")
    assert "generated_receipt_result(receipt)" in adapter_source
    assert "FAILED_RECEIPT_VALIDATION" in adapter_source

    assert "OPENCLAW_DEPLOY_ADAPTER_APPLY" in adapter_source


def test_hybrid_dag_keeps_hard_edges_but_skips_unneeded_ceremony() -> None:
    governance = _load_module()
    def route(facts: dict) -> dict:
        return governance.route_task({
            "task_prompt": "routing contract fixture",
            "uncertainty": "low",
            **facts,
        })

    narrow = route(
        {
            "task_shape": "implementation",
            "surfaces": ["python"],
            "risk": "low",
            "dirty_scope": ["src/narrow.py"],
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert narrow["roles"] == ["PM", "E1", "E2", "E4", "PM"]
    assert narrow["budget_envelope"] == "narrow"
    assert "PA" not in narrow["roles"]
    assert "QA" not in narrow["roles"]

    critical = route(
        {
            "task_shape": "deploy",
            "surfaces": ["rust", "authority", "bybit"],
            "risk": "critical",
            "runtime_claim": True,
            "end_to_end_claim": True,
        }
    )
    assert critical["roles"] == [
        "PM",
        "PA",
        "CC",
        "E3",
        "BB",
        "OPS",
        "PM",
        "OPS",
        "QA",
        "PM",
    ]
    assert [node["id"] for node in critical["nodes"] if node["kind"] == "effect_adapter"] == [
        "deploy_adapter_v1"
    ]
    assert critical["nodes"][-2]["role"] == "QA"

    ibkr = route(
        {
            "task_shape": "review",
            "surfaces": ["ibkr"],
            "risk": "high",
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert "IB" in ibkr["roles"]
    assert "BB" not in ibkr["roles"]

    broker_session = route(
        {
            "task_shape": "review",
            "surfaces": ["broker_session"],
            "risk": "medium",
            "uncertainty": "low",
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert "IB" in broker_session["roles"]
    assert "broker_ibkr" in governance.compile_context(
        "IB",
        {
            "task_shape": "review",
            "surfaces": ["broker_session"],
            "risk": "medium",
            "uncertainty": "low",
            "objective": "review broker session contract",
            "scope": ["IBKR"],
            "acceptance_criteria": ["typed denial remains closed"],
            "hard_stops": ["no contact"],
            "baseline": {"head": "abc"},
            "direct_interfaces": ["TWS"],
            "previous_failure": "none",
        },
    )["selected_packs"]

    multi_gate = route(
        {
            "task_shape": "review",
            "surfaces": ["authority", "bybit"],
            "risk": "high",
            "runtime_claim": False,
            "end_to_end_claim": True,
        }
    )
    by_id = {node["id"]: node for node in multi_gate["nodes"]}
    assert set(by_id["gate_join"]["requires"]) == {
        "constitutional_gate",
        "security_gate",
        "broker_bybit_gate",
    }
    assert by_id["business_acceptance"]["requires"] == ["gate_join"]
    assert all(item["owner"] == "PM" for item in multi_gate["skipped"])
    assert all(item["residual_risk"] != "none identified" for item in multi_gate["skipped"])

    for malformed in (
        {"task_shape": "review", "surfaces": "bybit", "risk": "low"},
        {"task_shape": "review", "surfaces": ["bybit"], "risk": "low", "runtime_claim": "false"},
        {"task_shape": "teleport", "surfaces": [], "risk": "low"},
        {"task_shape": "review", "surfaces": ["runtim"], "risk": "low"},
        {"task_shape": "review", "surfaces": ["runtime"], "risk": "low", "e2e_required": True},
    ):
        try:
            route(malformed)
        except ValueError as exc:
            assert "task facts" in str(exc)
        else:
            raise AssertionError("malformed task facts must fail closed")

    normalized = route(
        {
            "task_shape": " refactor ",
            "surfaces": [" bybit ", " python "],
            "risk": " low ",
            "dirty_scope": ["src/normalized.py"],
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert {"E1", "E2", "E4", "BB"}.issubset(normalized["roles"])
    assert normalized["task_facts"]["task_shape"] == "refactor"
    assert normalized["task_facts"]["surfaces"] == ["bybit", "python"]

    docs_route = route(
        {
            "task_shape": "docs",
            "surfaces": ["docs", "index"],
            "risk": "low",
            "dirty_scope": ["docs/index.md"],
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert docs_route["roles"] == ["PM", "TW", "R4", "PM"]

    tests_route = route(
        {
            "task_shape": "test",
            "surfaces": ["python"],
            "risk": "low",
            "dirty_scope": ["tests/test_contract.py"],
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert tests_route["roles"] == ["PM", "E4", "E2", "PM"]

    source_review = route(
        {
            "task_shape": "review",
            "surfaces": ["python"],
            "risk": "medium",
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert source_review["roles"] == ["PM", "E2", "PM"]

    investigation = route(
        {
            "task_shape": "audit",
            "surfaces": [],
            "risk": "medium",
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert investigation["roles"] == ["PM", "PA", "PM"]

    operations = route(
        {
            "task_shape": "review",
            "surfaces": ["service"],
            "risk": "medium",
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert {"E3", "OPS"}.issubset(operations["roles"])
    assert operations["roles"].count("OPS") == 2

    source_only_runtime = route(
        {
            "task_shape": "implementation",
            "surfaces": ["python", "runtime"],
            "risk": "medium",
            "dirty_scope": ["src/runtime_source.py"],
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert "OPS" not in source_only_runtime["roles"]

    runtime_source_review = route(
        {
            "task_shape": "review",
            "surfaces": ["runtime"],
            "risk": "medium",
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert "E2" in runtime_source_review["roles"]
    assert "OPS" not in runtime_source_review["roles"]

    specialist_route = route(
        {
            "task_shape": "review",
            "surfaces": ["functional", "performance", "gui"],
            "risk": "medium",
            "runtime_claim": False,
            "end_to_end_claim": False,
        }
    )
    assert {"FA", "E5", "A3"}.issubset(specialist_route["roles"])


def test_context_compiler_uses_elastic_envelope_without_truncating_mandatory_facts() -> None:
    governance = _load_module()
    baseline = governance.capture_repository_baseline()
    oversized_objective = "完整保留" * 20_000
    facts = {
        "task_shape": "review",
        "surfaces": ["authority", "rust"],
        "risk": "medium",
        "uncertainty": "low",
        "objective": oversized_objective,
        "scope": ["rust/openclaw_engine"],
        "acceptance_criteria": ["hard boundary remains fail-closed"],
        "hard_stops": ["never live/mainnet"],
        "baseline": baseline,
        "direct_interfaces": ["RiskConfig", "DecisionLease"],
        "previous_failure": "review found an unresolved authority conflict",
    }

    plan = governance.compile_context("CC", facts)

    assert plan["mandatory_content"]["objective"] == oversized_objective
    assert plan["mandatory_content"]["acceptance_criteria"] == facts["acceptance_criteria"]
    assert plan["mandatory_content"]["hard_stops"] == facts["hard_stops"]
    assert plan["omitted_mandatory"] == []
    assert plan["budget"]["action"] == "split_or_escalate"
    assert plan["budget"]["mandatory_truncated"] is False
    assert plan["context_digest"].startswith("sha256:")

    full_audit = governance.compile_context(
        "AI-E",
        {
            **facts,
            "objective": "full audit",
            "risk": "unknown",
            "surfaces": ["full_audit", "agent_workflow"],
        },
    )
    assert full_audit["budget"]["envelope"] == "full_audit"
    assert full_audit["budget"]["target_context_tokens"] > plan["budget"]["target_context_tokens"]

    small_facts = {
        "task_shape": "review",
        "surfaces": ["python"],
        "risk": "medium",
        "uncertainty": "low",
        "objective": "review one local parser change",
        "scope": ["helper_scripts/maintenance_scripts/agent_governance_execution.py"],
        "dirty_scope": [
            "helper_scripts/maintenance_scripts/agent_governance_execution.py"
        ],
        "acceptance_criteria": ["invalid input fails closed"],
        "hard_stops": ["no runtime effect"],
        "baseline": governance.capture_repository_baseline(),
        "direct_interfaces": ["compile_context"],
        "previous_failure": "none",
    }
    small = governance.compile_context("E2", small_facts)
    assert small["budget"]["action"] in {"within_target", "use_quality_reserve"}
    assert small["unresolved_sources"] == []
    assert small["budget"]["pass_allowed"] is True
    artifact = governance.materialize_context_artifact(small)
    assert governance.validate_context_artifact(
        artifact, expected_task_facts=small_facts
    )["errors"] == []

    stale_baseline = deepcopy(small_facts)
    stale_baseline["baseline"] = {
        **baseline,
        "dirty_diff_hash": "sha256:" + "f" * 64,
    }
    rejected = governance.compile_context("E2", stale_baseline)
    assert rejected["baseline_errors"]
    assert "task contract baseline" in rejected["unresolved_sources"]
    assert rejected["budget"]["pass_allowed"] is False

    tampered_plan = deepcopy(small)
    original_digest = tampered_plan["context_digest"]
    tampered_plan["budget"]["pass_allowed"] = False
    assert governance.context_plan_digest(tampered_plan) != original_digest
    assert governance.context_plan_digest(small) == original_digest


def test_query_context_preserves_explicit_empty_direct_interfaces() -> None:
    governance = _load_module()
    facts = {
        "task_shape": "query",
        "surfaces": ["governance"],
        "risk": "low",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "none",
        "objective": "answer one effect-free governance query",
        "scope": ["helper_scripts/maintenance_scripts/agent_governance_execution.py"],
        "acceptance_criteria": ["the query Context is eligible for a source-only verdict"],
        "hard_stops": ["do not grant write or runtime authority"],
        "baseline": governance.capture_repository_baseline(),
        "direct_interfaces": [],
        "previous_failure": "an explicit empty query interface list was treated as omitted",
    }
    route = governance.route_task(facts)

    plan = governance.compile_context("PM", route["task_facts"])

    assert plan["mandatory_content"]["direct_interfaces"] == []
    assert "direct_interfaces" not in plan["omitted_mandatory"]
    assert plan["budget"]["claim_pass_eligible"] is True
    artifact = governance.materialize_context_artifact(plan)
    assert governance.validate_context_artifact(
        artifact, expected_task_facts=route["task_facts"]
    )["errors"] == []


def test_query_context_keeps_missing_direct_interfaces_ineligible() -> None:
    governance = _load_module()
    facts = {
        "task_shape": "query",
        "surfaces": ["governance"],
        "risk": "low",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "none",
        "objective": "answer one effect-free governance query",
        "scope": ["helper_scripts/maintenance_scripts/agent_governance_execution.py"],
        "acceptance_criteria": ["the query Context remains fail-closed when incomplete"],
        "hard_stops": ["do not grant write or runtime authority"],
        "baseline": governance.capture_repository_baseline(),
        "previous_failure": "missing mandatory content was accepted",
    }
    route = governance.route_task(facts)

    plan = governance.compile_context("PM", route["task_facts"])

    assert "direct_interfaces" not in plan["mandatory_content"]
    assert "direct_interfaces" in plan["omitted_mandatory"]
    assert plan["budget"]["call_allowed"] is False
    assert plan["budget"]["claim_pass_eligible"] is False
    try:
        governance.materialize_context_artifact(plan)
    except ValueError as exc:
        assert "not call_allowed" in str(exc)
    else:
        raise AssertionError("missing query direct_interfaces must not materialize")


def test_non_query_context_keeps_empty_direct_interfaces_ineligible() -> None:
    governance = _load_module()
    facts = {
        "task_shape": "review",
        "surfaces": ["governance"],
        "risk": "low",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "none",
        "objective": "review one governance contract",
        "scope": ["helper_scripts/maintenance_scripts/agent_governance_execution.py"],
        "acceptance_criteria": ["non-query Context remains explicit about interfaces"],
        "hard_stops": ["do not grant write or runtime authority"],
        "baseline": governance.capture_repository_baseline(),
        "direct_interfaces": [],
        "previous_failure": "an arbitrary empty interface list was accepted",
    }
    route = governance.route_task(facts)

    plan = governance.compile_context("PM", route["task_facts"])

    assert "direct_interfaces" not in plan["mandatory_content"]
    assert "direct_interfaces" in plan["omitted_mandatory"]
    assert plan["budget"]["claim_pass_eligible"] is False
    try:
        governance.materialize_context_artifact(plan)
    except ValueError as exc:
        assert "not call_allowed" in str(exc)
    else:
        raise AssertionError("non-query empty direct_interfaces must not materialize")


def test_query_context_keeps_other_empty_mandatory_values_ineligible() -> None:
    governance = _load_module()
    base_facts = {
        "task_shape": "query",
        "surfaces": ["governance"],
        "risk": "low",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "none",
        "objective": "answer one effect-free governance query",
        "scope": ["helper_scripts/maintenance_scripts/agent_governance_execution.py"],
        "acceptance_criteria": ["all mandatory Context remains explicit"],
        "hard_stops": ["do not grant write or runtime authority"],
        "baseline": governance.capture_repository_baseline(),
        "direct_interfaces": [],
        "previous_failure": "empty mandatory content was accepted",
    }

    for field, empty_value in (
        ("acceptance_criteria", []),
        ("hard_stops", []),
        ("baseline", {}),
        ("previous_failure", ""),
    ):
        route = governance.route_task({**base_facts, field: empty_value})
        plan = governance.compile_context("PM", route["task_facts"])

        assert field not in plan["mandatory_content"]
        assert field in plan["omitted_mandatory"]
        assert plan["budget"]["claim_pass_eligible"] is False
        try:
            governance.materialize_context_artifact(plan)
        except ValueError as exc:
            assert "not call_allowed" in str(exc)
        else:
            raise AssertionError(f"empty mandatory {field} must not materialize")

    for field, empty_value in (("objective", ""), ("scope", [])):
        try:
            governance.compile_context("PM", {**base_facts, field: empty_value})
        except ValueError as exc:
            assert field in str(exc)
        else:
            raise AssertionError(f"invalid empty mandatory {field} must fail validation")


def test_context_provenance_is_byte_backed_and_rejects_path_substitution(
    tmp_path: Path,
) -> None:
    governance = _load_module()
    root = tmp_path / "repo"
    root.mkdir()
    (root / "local.md").write_text("local authority\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Governance Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "local.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (root / "escape.md").symlink_to(outside)

    registry = deepcopy(governance.load_registry())
    registry["context_packs"]["test"] = ["local.md", "virtual source", "current diff"]
    registry["roles"]["E2"]["context_packs"] = ["test"]
    baseline = governance.capture_repository_baseline(root)
    facts = {
        "task_shape": "review",
        "surfaces": ["comments"],
        "risk": "low",
        "uncertainty": "low",
        "objective": "prove byte-backed context provenance",
        "scope": ["local.md"],
        "acceptance_criteria": ["caller assertions cannot replace bytes"],
        "hard_stops": ["no runtime effect"],
        "baseline": baseline,
        "direct_interfaces": ["compile_context"],
        "previous_failure": "digest override exploit",
    }
    initial = governance.compile_context("E2", facts, registry, root)
    local_record = next(item for item in initial["sources"] if item["source"] == "local.md")

    attacked = deepcopy(facts)
    attacked["evidence_state"] = {
        "local.md": {
            "digest": "sha256:" + "f" * 64,
            "planned_tokens": 0,
            "observed_at": "2026-07-10T12:00:00Z",
        },
        "virtual source": {
            "artifact_path": "escape.md",
        },
        "current diff": {
            "digest": "sha256:" + "e" * 64,
            "planned_tokens": 0,
        },
    }
    result = governance.compile_context("E2", attacked, registry, root)
    by_source = {item["source"]: item for item in result["sources"]}
    assert by_source["local.md"]["status"] == "local_digest_mismatch"
    assert by_source["local.md"]["digest"] == local_record["digest"]
    assert by_source["local.md"]["planned_tokens"] == local_record["planned_tokens"]
    assert by_source["virtual source"]["status"] == "unbacked_evidence_state"
    assert "symlink" in by_source["virtual source"]["artifact_error"]
    assert by_source["current diff"]["status"] == "trusted_producer_override_rejected"
    assert result["budget"]["pass_allowed"] is False

    verified = deepcopy(facts)
    verified["evidence_state"] = {
        "local.md": {
            "digest": local_record["digest"],
            "observed_at": "2026-07-10T12:00:00Z",
        }
    }
    verified_result = governance.compile_context("E2", verified, registry, root)
    verified_by_source = {item["source"]: item for item in verified_result["sources"]}
    assert verified_by_source["local.md"]["status"] == "pinned_verified"
    assert verified_by_source["local.md"]["planned_tokens"] > 0
    assert verified_by_source["current diff"]["status"] == "trusted_producer"

    unknown = deepcopy(facts)
    unknown["evidence_state"] = {"typo source": {"artifact_path": "local.md"}}
    try:
        governance.compile_context("E2", unknown, registry, root)
    except ValueError as exc:
        assert "unselected sources" in str(exc)
    else:
        raise AssertionError("unknown evidence_state keys must fail closed")


def test_agent_wave_executes_only_verified_inline_context_and_reuses_exact_retry_bytes() -> None:
    governance = _load_module()
    baseline = governance.capture_repository_baseline()
    facts = {
        "task_shape": "review",
        "surfaces": ["python"],
        "risk": "medium",
        "uncertainty": "low",
        "objective": "exercise inline context admission",
        "scope": ["helper_scripts/maintenance_scripts/agent_governance_execution.py"],
        "acceptance_criteria": ["no path substitution reaches an agent"],
        "hard_stops": ["no runtime effect"],
        "baseline": baseline,
        "direct_interfaces": ["compile_context", "agent-wave"],
        "previous_failure": "contextPath bytes were not verified",
        "task_prompt": "Review the bound context only.",
    }
    context_plan = governance.compile_context("E2", facts)
    assert context_plan["budget"]["pass_allowed"] is True
    context_artifact = governance.materialize_context_artifact(context_plan)
    wave_args = {
        "tasks": [
            {
                "node_id": "independent_review",
                "requires": [],
                "payload_kind": "review_fragment_v1",
                "agentType": "E2",
                "native_agent": "E2",
                "node_class": "verification",
                "permission": "read_only",
                "prompt": "Review the bound context only.",
                "description": "inline-context-harness",
                "contextArtifact": context_artifact,
            }
        ],
        "dag_digest": _canonical_digest(
            {
                "schema_version": "agent_wave_execution_dag_v1",
                "nodes": [
                    {
                        "node_id": "independent_review", "role": "E2",
                        "native_agent": "E2",
                        "requires": [], "node_class": "verification",
                        "permission": "read_only",
                    }
                ],
            }
        ),
        "budget": {
            "max_unique_nodes": context_plan["budget"]["authority"]["max_unique_nodes"],
            "max_call_attempts": context_plan["budget"]["authority"]["max_call_attempts"],
            "retry_budget": context_plan["budget"]["authority"]["retry_budget"],
            "max_workflow_planned_input_tokens": context_plan["budget"]["authority"]["max_workflow_planned_input_tokens"],
            "authority_digest": context_plan["budget"]["authority_digest"],
        },
    }
    script = r"""
const fs = require('node:fs');
if (!globalThis.crypto) globalThis.crypto = require('node:crypto').webcrypto;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = fs.readFileSync(__WORKFLOW__, 'utf8').replace('export const meta =', 'const meta =');
const runner = new AsyncFunction('args', 'phase', 'log', 'parallel', 'agent', source);
const baseArgs = __ARGS__;
const fragment = {
  work_status: 'DONE', gate_verdict: 'PASS', classification: 'FACT',
  confidence: 'high', summary: 'reviewed', evidence_refs: ['ev-1'], concerns: [],
  next_action: { owner: 'PM', action: 'integrate' },
  payload: {},
};
const parallel = async jobs => Promise.all(jobs.map(job => job()));
async function execute(input, nullFirst = false) {
  const prompts = []; const options = []; let calls = 0;
  const agent = async (prompt, option) => {
    calls += 1; prompts.push(prompt); options.push(option);
    if (nullFirst && calls === 1) return null;
    return fragment;
  };
  try {
    const result = await runner(input, () => {}, () => {}, parallel, agent);
    return { ok: true, result, prompts, options, calls };
  } catch (error) {
    return { ok: false, error: String(error.message || error), prompts, options, calls };
  }
}
(async () => {
  const valid = await execute(JSON.parse(JSON.stringify(baseArgs)));
  const mutated = JSON.parse(JSON.stringify(baseArgs));
  mutated.tasks[0].contextArtifact.canonical_plan = mutated.tasks[0].contextArtifact.canonical_plan.replace('"pass_allowed":true', '"pass_allowed":false');
  const mutation = await execute(mutated);
  const legacy = JSON.parse(JSON.stringify(baseArgs));
  legacy.tasks[0].contextPath = 'README.md';
  const pathSubstitution = await execute(legacy);
  const retry = await execute(JSON.parse(JSON.stringify(baseArgs)), true);
  const retryDigest = retry.ok ? Object.values(retry.result.context_artifact_digests)[0] : null;
  console.log(JSON.stringify({
    valid: {
      ok: valid.ok, calls: valid.calls,
      raw_path_forwarded: valid.options.some(option => Object.prototype.hasOwnProperty.call(option, 'contextPath')),
    },
    mutation: { ok: mutation.ok, calls: mutation.calls, error: mutation.error },
    path_substitution: { ok: pathSubstitution.ok, calls: pathSubstitution.calls, error: pathSubstitution.error },
    retry: {
      ok: retry.ok, calls: retry.calls,
      same_verified_digest: retry.prompts.length === 2 && retry.prompts.every(prompt => prompt.includes(retryDigest)),
    },
  }));
})().catch(error => { console.error(error); process.exit(1); });
""".replace("__WORKFLOW__", json.dumps(str(ROOT / ".claude/workflows/agent-wave.js"))).replace(
        "__ARGS__", json.dumps(wave_args)
    )
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["valid"] == {"ok": True, "calls": 1, "raw_path_forwarded": False}
    assert result["mutation"]["ok"] is False and result["mutation"]["calls"] == 0
    assert "digest does not match" in result["mutation"]["error"]
    assert result["path_substitution"]["ok"] is False
    assert result["path_substitution"]["calls"] == 0
    assert "raw contextPath" in result["path_substitution"]["error"]
    assert result["retry"] == {"ok": True, "calls": 2, "same_verified_digest": True}


def test_closure_schema_binds_role_producers_and_typed_capture_refs() -> None:
    governance = _load_module()
    assert governance.TRUST_TIERS == {
        governance.LOCAL_REPRODUCIBLE,
        governance.ORCHESTRATOR_BOUND,
        governance.PLATFORM_OR_EXTERNAL_ATTESTED,
    }
    for public_capture_api in (
        "capture_repository",
        "capture_command",
        "capture_repository_change",
        "build_controller_workflow_call_record",
        "build_workflow_call_manifest",
        "build_workflow_wave_record",
        "build_unsigned_telemetry_record",
        "canonical_digest",
        "validate_repository_capture",
        "validate_repository_change_record",
        "validate_command_capture",
        "validate_telemetry_record",
        "validate_workflow_call_record",
        "validate_workflow_call_manifest",
        "validate_workflow_wave_record",
            "validate_role_fragment_producer",
            "validate_external_evidence_capture",
    ):
        assert public_capture_api in governance.__all__
        assert callable(getattr(governance, public_capture_api))

    schema = json.loads(
        (ROOT / ".codex/schemas/closure_packet_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validate = _load_schema_validator().schema_subset_errors
    digest = "sha256:" + "a" * 64
    timestamp = "2026-07-11T12:00:00Z"

    fragment = {
        "schema_version": "role_fragment_v1",
        "id": "fragment:review",
        "node_id": "independent_review",
        "role": "E2",
        "task_contract_digest": digest,
        "context_artifact_digest": digest,
        "producer_call_ref": "agent-wave:independent_review:attempt:1",
        "producer_call_receipt_digest": digest,
        "producer_record_kind": "workflow_call_record_v1",
        "work_status": "DONE",
        "gate_verdict": "PASS",
        "classification": "FACT",
        "confidence": "high",
        "summary": "controller-bound review passed",
        "evidence_refs": ["capture:repository"],
        "concerns": [],
        "next_action": {"owner": "PM", "action": "adjudicate"},
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "trusted telemetry was not exposed",
        },
        "payload_kind": "review_fragment_v1",
        "payload": {},
    }
    fragment_schema = schema["properties"]["role_fragments"]["items"]
    assert validate(fragment, fragment_schema, schema) == []
    for required_ref in (
        "context_artifact_digest",
        "producer_call_ref",
        "producer_call_receipt_digest",
        "producer_record_kind",
    ):
        missing = deepcopy(fragment)
        del missing[required_ref]
        assert validate(missing, fragment_schema, schema), required_ref

    authority = {
        "class": "normative_policy",
        "subject": "demo_only",
        "value": {"allowed": True},
        "source": "CLAUDE.md#Hard Boundaries",
        "digest": digest,
        "claim_digest": digest,
        "source_ref": "capture:repository",
        "observed_at": timestamp,
        "scope": "repo",
        "strength": "direct",
        "expiry": None,
    }
    authority_schema = schema["properties"]["authority_refs"]["items"]
    assert validate(authority, authority_schema, schema) == []
    missing_authority_capture = deepcopy(authority)
    del missing_authority_capture["source_ref"]
    assert validate(missing_authority_capture, authority_schema, schema)

    check_schema = schema["properties"]["checks"]["items"]
    executed_check = {
        "id": "check:pytest",
        "status": "EXECUTED",
        "command": "pytest -q",
        "signature": digest,
        "evidence_ref": "capture:command",
        "command_capture_ref": "capture:command",
    }
    assert validate(executed_check, check_schema, schema) == []
    missing_command_capture = deepcopy(executed_check)
    del missing_command_capture["command_capture_ref"]
    assert validate(missing_command_capture, check_schema, schema)
    reused_check = deepcopy(executed_check)
    reused_check["status"] = "REUSED"
    assert validate(reused_check, check_schema, schema) == []
    missing_reused_capture = deepcopy(reused_check)
    del missing_reused_capture["command_capture_ref"]
    assert validate(missing_reused_capture, check_schema, schema)
    empty_reused_capture = deepcopy(reused_check)
    empty_reused_capture["command_capture_ref"] = ""
    assert validate(empty_reused_capture, check_schema, schema)

    consumption_schema = schema["properties"]["consumption"]
    measured_consumption = {
        "measurement_status": "measured",
        "telemetry_ref": "capture:telemetry",
        "measurement_source": "platform_telemetry",
        "telemetry_digest": digest,
        "input_tokens": 1,
        "output_tokens": 1,
    }
    assert validate(measured_consumption, consumption_schema, schema) == []
    missing_telemetry_capture = deepcopy(measured_consumption)
    del missing_telemetry_capture["telemetry_ref"]
    assert validate(missing_telemetry_capture, consumption_schema, schema)
    measured_wave_only = deepcopy(missing_telemetry_capture)
    measured_wave_only["wave_record_refs"] = ["capture:wave"]
    assert validate(measured_wave_only, consumption_schema, schema)

    partial_orchestrator = {
        "measurement_status": "partial",
        "measurement_source": "orchestrator_receipt",
        "wave_record_refs": ["capture:wave"],
        "planned_tokens": 100,
        "retry_count": 1,
        "fan_out": 2,
        "missing_metrics": ["model output tokens"],
    }
    assert validate(partial_orchestrator, consumption_schema, schema) == []
    missing_wave_ledger = deepcopy(partial_orchestrator)
    del missing_wave_ledger["wave_record_refs"]
    assert validate(missing_wave_ledger, consumption_schema, schema)
    duplicate_wave_ledger = deepcopy(partial_orchestrator)
    duplicate_wave_ledger["wave_record_refs"] = ["capture:wave", "capture:wave"]
    assert validate(duplicate_wave_ledger, consumption_schema, schema)
    missing_partial_source = deepcopy(partial_orchestrator)
    del missing_partial_source["measurement_source"]
    assert validate(missing_partial_source, consumption_schema, schema)

    partial_platform = {
        "measurement_status": "partial",
        "measurement_source": "provider_usage_api",
        "telemetry_ref": "capture:telemetry",
        "telemetry_digest": digest,
        "input_tokens": 1,
        "missing_metrics": ["cache read tokens"],
    }
    assert validate(partial_platform, consumption_schema, schema) == []
    missing_partial_telemetry = deepcopy(partial_platform)
    del missing_partial_telemetry["telemetry_ref"]
    assert validate(missing_partial_telemetry, consumption_schema, schema)

    role_partial = deepcopy(fragment)
    role_partial["consumption"] = {
        "measurement_status": "partial",
        "measurement_source": "orchestrator_receipt",
        "missing_metrics": ["output tokens"],
    }
    assert validate(role_partial, fragment_schema, schema)
    role_partial["consumption"]["telemetry_ref"] = "capture:telemetry"
    assert validate(role_partial, fragment_schema, schema) == []

    empty_bytes_digest = "sha256:" + hashlib.sha256(b"").hexdigest()
    empty_manifest_digest = _canonical_digest([])
    repository_capture = {
        "schema_version": "repository_capture_v1",
        "trust_tier": "LOCAL_REPRODUCIBLE",
        "scope": ["CLAUDE.md"],
        "source_head": "b" * 40,
        "tracked_diff": {
            "encoding": "base64",
            "content": "",
            "bytes": 0,
            "digest": empty_bytes_digest,
        },
        "tracked_paths": [],
        "untracked": [],
        "changed_paths": [],
        "change_manifest_digest": empty_manifest_digest,
        "untracked_manifest_digest": empty_manifest_digest,
        "observed_at": timestamp,
        "record_digest": digest,
    }
    repository_evidence = {
        "id": "capture:repository",
        "scope": "source",
        "kind": "repository_capture_v1",
        "digest": digest,
        "artifact": repository_capture,
    }
    evidence_schema = schema["$defs"]["evidence"]
    assert validate(repository_evidence, evidence_schema, schema) == []
    missing_capture_artifact = deepcopy(repository_evidence)
    del missing_capture_artifact["artifact"]
    assert validate(missing_capture_artifact, evidence_schema, schema)

    repository_change = {
        "schema_version": "repository_change_record_v1",
        "trust_tier": "LOCAL_REPRODUCIBLE",
        "task_contract_digest": digest,
        "node_id": "implementation",
        "role_id": "E1",
        "scope": ["CLAUDE.md"],
        "before": deepcopy(repository_capture),
        "after": deepcopy(repository_capture),
        "before_generation_digest": digest,
        "after_generation_digest": digest,
        "owned_before": deepcopy(repository_capture),
        "owned_after": deepcopy(repository_capture),
        "owned_before_generation_digest": digest,
        "owned_after_generation_digest": digest,
        "mutation_observed": False,
        "affected_paths": [],
        "record_digest": digest,
    }
    repository_change_evidence = {
        "id": "capture:repository-change",
        "scope": "source",
        "kind": "repository_change_record_v1",
        "digest": digest,
        "artifact": repository_change,
    }
    assert validate(repository_change_evidence, evidence_schema, schema) == []
    missing_change_generation = deepcopy(repository_change_evidence)
    del missing_change_generation["artifact"]["after_generation_digest"]
    assert validate(missing_change_generation, evidence_schema, schema)
    duplicate_change_scope = deepcopy(repository_change_evidence)
    duplicate_change_scope["artifact"]["scope"] = ["CLAUDE.md", "CLAUDE.md"]
    assert validate(duplicate_change_scope, evidence_schema, schema)
    invalid_affected_path = deepcopy(repository_change_evidence)
    invalid_affected_path["artifact"]["affected_paths"] = [""]
    assert validate(invalid_affected_path, evidence_schema, schema)
    wrong_change_tier = deepcopy(repository_change_evidence)
    wrong_change_tier["artifact"]["trust_tier"] = "ORCHESTRATOR_BOUND"
    assert validate(wrong_change_tier, evidence_schema, schema)

    full_audit_control = {
        "schema_version": "full_audit_control_v1",
        "workflow_contract_digest": digest,
        "call_manifest_digest": digest,
        "workflow_wave_record_digest": digest,
        "baseline": {
            "source_head": "b" * 40,
            "dirty_diff_hash": digest,
            "untracked_relevant_hash": digest,
            "runtime_head": None,
            "runtime_observed_at": None,
        },
        "scheduler": "full",
        "selection_surfaces": ["agent_workflow"],
        "run_sequence": 1,
        "adaptive_recall_approved": False,
        "adaptive_recall_authority_digest": None,
        "expected_axes": ["E2"],
        "admitted_axes": ["E2"],
        "deferred_axes": [],
        "axis_bindings": [],
        "axis_fragment_digests": {},
        "coverage_debt": [],
        "coverage_holes": [],
        "assumption_count": 0,
        "disputed_count": 0,
        "decision_changing_findings": 0,
        "seam_present": True,
        "seam_result": {},
        "seam_result_digest": digest,
        "seam_call_ref": "full-audit:seam:attempt:1",
        "seam_call_receipt_digest": digest,
        "pass_eligible": True,
        "unverified_projection": [],
    }
    full_audit_schema = schema["$defs"]["fullAuditControl"]
    assert validate(full_audit_control, full_audit_schema, schema) == []
    for required_receipt_field in (
        "workflow_contract_digest",
        "call_manifest_digest",
        "workflow_wave_record_digest",
        "seam_call_ref",
        "seam_call_receipt_digest",
    ):
        missing_receipt = deepcopy(full_audit_control)
        del missing_receipt[required_receipt_field]
        assert validate(missing_receipt, full_audit_schema, schema)
    empty_seam_ref = deepcopy(full_audit_control)
    empty_seam_ref["seam_call_ref"] = ""
    assert validate(empty_seam_ref, full_audit_schema, schema)

    rich_call = {
        "schema_version": "workflow_call_record_v1",
        "workflow_contract_digest": digest,
        "logical_call_id": "agent-wave:independent_review:attempt:1",
        "node_id": "independent_review",
        "payload_kind": "review_fragment_v1",
        "attempt": 1,
        "retry_parent_call_id": None,
        "phase": "Wave",
        "label": "independent_review",
        "requested": {
            "logical_role": "E2", "platform": "claude_saved_workflow",
            "platform_requested_agent": "E2",
            "native_binding": {"logical_role": "E2", "native_agent": "E2", "node_class": "verification", "permission": "read_only"},
            "model": None,
            "effort": None,
            "isolation": None,
            "node_class": "verification",
            "permission": "read_only",
        },
        "dag_digest": digest,
        "requires": [],
        "topological_wave": 0,
        "producer_generation": {},
        "prompt_digest": digest,
        "context_artifact_digest": digest,
        "task_contract_digest": digest,
        "dirty_scope_digest": digest,
        "focus_digest": digest,
        "compiler_input_tokens_lower_bound": 1,
        "admitted_input_tokens_lower_bound": 1,
        "response_schema_digest": digest,
        "started_at": timestamp,
        "ended_at": timestamp,
        "returned_null": False,
        "parsed_result_digest": digest,
        "record_digest": digest,
    }
    call_evidence = {
        "id": "capture:call",
        "scope": "data",
        "kind": "workflow_call_record_v1",
        "digest": digest,
        "artifact": rich_call,
    }
    assert validate(call_evidence, evidence_schema, schema) == []
    non_wave_call = deepcopy(call_evidence)
    non_wave_call["artifact"]["phase"] = "Evidence"
    assert validate(non_wave_call, evidence_schema, schema) == []
    simplified_call = deepcopy(call_evidence)
    simplified_call["artifact"] = {
        "schema_version": "workflow_call_record_v1",
        "call_id": "independent_review",
        "record_digest": digest,
    }
    assert validate(simplified_call, evidence_schema, schema)

    wrapper_defs = {
        "repository_capture_v1": "repositoryCapture",
        "repository_change_record_v1": "repositoryChangeRecord",
        "command_capture_v1": "commandCapture",
        "command_capture_v2": "commandCaptureV2",
        "workflow_call_record_v1": "workflowCallRecord",
        "workflow_call_manifest_v1": "workflowCallManifest",
        "workflow_wave_record_v1": "workflowWaveRecord",
            "telemetry_record_v1": "telemetryRecord",
            "external_evidence_capture_v1": "externalEvidenceCapture",
            "program_adoption_receipt_v1": "programAdoptionBundle",
    }
    artifact_refs = {
        clause["if"]["properties"]["kind"].get("const"): clause["then"][
            "properties"
        ]["artifact"]["$ref"]
        for clause in evidence_schema["allOf"]
        if "artifact" in clause.get("then", {}).get("properties", {})
    }
    assert artifact_refs == {
        kind: f"#/$defs/{definition}" for kind, definition in wrapper_defs.items()
    }


def _refresh_standard_workflow_lineage(governance, packet: dict) -> None:
    artifact = packet["dispatch"]["context_artifact"]
    plan = json.loads(artifact["canonical_plan"])
    contract = plan["task_contract"]
    task_digest = plan["task_contract_digest"]
    context_digest = artifact["artifact_digest"]
    workflow_digest = _canonical_digest(
        {"schema_version": "test_standard_workflow_v1", "task": task_digest}
    )
    schema_digest = _canonical_digest({"schema": "standard_judgment_v1"})
    task_specs, projection_errors = governance.delegated_execution_projection(
        packet["dispatch"]["required_role_nodes"],
        packet["dispatch"]["admitted_role_nodes"],
        excluded_nodes=governance.non_call_controller_node_ids(
            packet["dispatch"]["task_facts"]
        ),
    )
    assert projection_errors == [], projection_errors
    execution_waves, topology_errors = governance.topological_waves(task_specs)
    assert topology_errors == [], topology_errors
    dag_digest = governance.execution_dag_digest(task_specs)
    packet["dispatch"]["dag_digest"] = dag_digest
    task_by_node = {task["node_id"]: task for task in task_specs}
    fragment_by_node = {
        fragment["node_id"]: fragment for fragment in packet["role_fragments"]
    }
    calls = []
    built_calls = {}
    for wave_index, wave_nodes in enumerate(execution_waves):
      for node_id in wave_nodes:
        fragment = fragment_by_node[node_id]
        task_spec = task_by_node[node_id]
        judgment = {
            field: deepcopy(fragment[field])
            for field in (
                "work_status", "gate_verdict", "classification", "confidence",
                "summary", "evidence_refs", "concerns", "next_action", "payload",
            )
        }
        call_id = f"test-standard:{node_id}:attempt:1"
        call = governance.build_controller_workflow_call_record(
            workflow_contract_digest=workflow_digest,
            logical_call_id=call_id,
            node_id=fragment["node_id"],
            payload_kind=fragment["payload_kind"],
            attempt=1,
            retry_parent_call_id=None,
            phase="Wave",
            label=node_id,
            requested={
                "logical_role": fragment["role"],
                "platform": "claude_saved_workflow",
                "platform_requested_agent": task_spec["native_agent"],
                "native_binding": {
                    "logical_role": fragment["role"],
                    "native_agent": task_spec["native_agent"],
                    "node_class": task_spec["node_class"],
                    "permission": task_spec["permission"],
                },
                "model": None,
                "effort": None, "isolation": None,
                "node_class": task_spec["node_class"],
                "permission": task_spec["permission"],
            },
            prompt_digest=_canonical_digest({"node": node_id}),
            context_artifact_digest=context_digest,
            task_contract_digest=task_digest,
            dirty_scope_digest=_canonical_digest(contract["dirty_scope"]),
            focus_digest=_canonical_digest(contract["focus"]),
            compiler_input_tokens_lower_bound=1,
            admitted_input_tokens_lower_bound=1,
            response_schema_digest=schema_digest,
            started_at=packet["adjudicated_at"],
            ended_at=packet["adjudicated_at"],
            returned_null=False,
            parsed_result_digest=_canonical_digest(judgment),
            dag_digest=dag_digest,
            requires=task_spec["requires"],
            topological_wave=wave_index,
            producer_generation={
                required: built_calls[required]["record_digest"]
                for required in task_spec["requires"]
            },
        )
        fragment.update(
            context_artifact_digest=context_digest,
            producer_record_kind="workflow_call_record_v1",
            producer_call_ref=call_id,
            producer_call_receipt_digest=call["record_digest"],
        )
        calls.append(call)
        built_calls[node_id] = call
    call_by_node = {call["node_id"]: call for call in calls}
    admitted_tasks = [
        {
            "node_id": task_spec["node_id"], "role": task_spec["role"],
            "native_agent": task_spec["native_agent"],
            "requires": task_spec["requires"],
            "node_class": task_spec["node_class"],
            "permission": task_spec["permission"],
            "payload_kind": fragment_by_node[task_spec["node_id"]]["payload_kind"],
            "task_contract_digest": task_digest,
            "context_artifact_digest": context_digest,
            "description_digest": _canonical_digest(
                fragment_by_node[task_spec["node_id"]]["summary"]
            ),
            "base_prompt_digest": call_by_node[task_spec["node_id"]]["prompt_digest"],
            "requested": deepcopy(call_by_node[task_spec["node_id"]]["requested"]),
            "dirty_scope": sorted(contract["dirty_scope"]),
            "dirty_scope_digest": _canonical_digest(sorted(contract["dirty_scope"])),
            "focus": contract["focus"],
            "focus_digest": _canonical_digest(contract["focus"]),
            "compiler_estimated_input_tokens": 1,
            "admitted_input_tokens_lower_bound": 1,
        }
        for task_spec in task_specs
    ]
    manifest = governance.build_workflow_call_manifest(
        calls, workflow_contract_digest=workflow_digest
    )
    budget_authority_value = json.loads(artifact["budget_authority_canonical"])
    wave = governance.build_workflow_wave_record(
        manifest=manifest,
        admitted_tasks=admitted_tasks,
        budget_authority={
            "authority_digest": artifact["budget_authority_digest"],
            "authority_canonical": artifact["budget_authority_canonical"],
            "admitted_caps": {
                field: budget_authority_value[field]
                for field in (
                    "max_context_tokens_per_call", "max_prompt_utf8_bytes_per_call",
                    "max_workflow_planned_input_tokens",
                    "max_unique_nodes", "max_call_attempts", "retry_budget",
                )
            },
        },
        result_fragment_digests={
            fragment["node_id"]: _canonical_digest(fragment)
            for fragment in packet["role_fragments"]
        },
    )
    packet["evidence"] = [
        item for item in packet["evidence"]
        if item.get("kind") not in {
            "workflow_call_manifest_v1", "workflow_wave_record_v1"
        }
    ] + [
        {
            "id": "ev-standard-call-manifest", "scope": "data",
            "kind": "workflow_call_manifest_v1",
            "digest": manifest["manifest_digest"], "artifact": manifest,
        },
        {
            "id": "ev-standard-wave", "scope": "data",
            "kind": "workflow_wave_record_v1",
            "digest": wave["record_digest"], "artifact": wave,
        },
    ]
    packet["consumption"] = {
        "measurement_status": "partial",
        "measurement_source": "orchestrator_receipt",
        "wave_record_refs": ["ev-standard-wave"],
        "planned_tokens": wave["scheduled_call_admitted_input_tokens_lower_bound"],
        "retry_count": wave["retry_call_count"],
        "fan_out": len(wave["admitted_tasks"]),
        "quality_reserve_used": (
            wave["scheduled_call_admitted_input_tokens_lower_bound"]
            > plan["budget"]["target_context_tokens"]
        ),
        "missing_metrics": [
            "input_tokens", "output_tokens", "cache_read_tokens", "tool_calls",
            "wall_time_ms", "accepted_findings", "rework_count",
        ],
        "unavailable_reason": "platform usage and controller overhead were not exposed",
    }


def _valid_failed_review_closure() -> dict:
    governance = _load_module()
    source_baseline = governance.capture_repository_baseline()
    criterion = "hard boundary remains fail-closed"
    scope = ["CLAUDE.md", "helper_scripts/maintenance_scripts/agent_governance_closure.py"]
    task_facts = {
        "task_shape": "review",
        "surfaces": ["hard_boundary"],
        "risk": "medium",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "side_effect_class": "none",
        "objective": "review an authority-sensitive change",
        "scope": scope,
        "acceptance_criteria": [criterion],
        "hard_stops": ["never expand live/mainnet authority"],
        "baseline": source_baseline,
        "direct_interfaces": ["closure_packet_v1"],
        "previous_failure": "authority drift remained unresolved",
    }
    route = governance.route_task(task_facts)
    context_plan = governance.compile_context("PM", route["task_facts"])
    assert context_plan["budget"]["pass_allowed"] is True
    context_artifact = governance.materialize_context_artifact(context_plan)
    adjudicated = datetime.now(timezone.utc) + timedelta(seconds=2)
    observed = adjudicated - timedelta(seconds=1)
    observed_at = observed.isoformat().replace("+00:00", "Z")
    adjudicated_at = adjudicated.isoformat().replace("+00:00", "Z")
    baseline = {
        **source_baseline,
        "runtime_head": None,
        "runtime_observed_at": None,
    }
    source_receipt = governance.build_source_review_receipt(
        producer_role="E2",
        command="review authority-sensitive closure",
        baseline=baseline,
        criteria=[criterion],
        observed_at=observed_at,
        exit_code=0,
        stdout=b"review completed with a gate finding",
        stderr=b"",
    )
    repository_capture = governance.capture_repository(scope)
    authority_source = next(
        item for item in context_plan["sources"]
        if item["source"].startswith("CLAUDE.md")
    )
    authority = governance.build_authority_claim(
        authority_class="normative_policy",
        subject="development_agent_live_authority",
        value=authority_source["content"],
        source=authority_source["source"],
        source_ref=f"context:{authority_source['source']}",
        source_digest=authority_source["content_digest"],
        observed_at=authority_source["observed_at"],
        scope="repo",
        strength="direct",
        expiry=None,
    )
    packet = {
        "schema_version": "closure_packet_v1",
        "task_id": "agent-governance-review",
        "human_summary": {
            "objective": "review an authority-sensitive change",
            "scope": scope,
            "outcome": "review completed; target failed the gate",
        },
        "work_status": "DONE",
        "gate_verdict": "FAIL",
        "disposition": "NO_CHANGE_NEEDED",
        "confidence": "high",
        "adjudicated_at": adjudicated_at,
        "baseline": baseline,
        "dispatch": {
            "task_facts": route["task_facts"],
            "context_artifact": context_artifact,
            "dag_digest": route["dag_digest"],
            "required_role_nodes": route["required_role_nodes"],
            "admitted_role_nodes": [],
        },
        "authority_refs": [authority],
        "acceptance": [
            {
                "criterion": criterion,
                "status": "FAIL",
                "evidence_refs": ["ev-repository"],
            }
        ],
        "evidence": [
            {
                "id": "ev-source-1",
                "scope": "source",
                "kind": "source_review_receipt_v1",
                "digest": source_receipt["receipt_digest"],
                "observed_at": observed_at,
                "artifact": source_receipt,
            },
            {
                "id": "ev-repository",
                "scope": "source",
                "kind": "repository_capture_v1",
                "digest": repository_capture["record_digest"],
                "observed_at": repository_capture["observed_at"],
                "artifact": repository_capture,
            },
        ],
        "role_fragments": [
            {
                "schema_version": "role_fragment_v1",
                "id": "frag-cc-1",
                "node_id": "constitutional_gate",
                "role": "CC",
                "work_status": "DONE",
                "gate_verdict": "FAIL",
                "classification": "FACT",
                "confidence": "high",
                "summary": "hard boundary failed",
                "task_contract_digest": context_plan["task_contract_digest"],
                "context_artifact_digest": context_artifact["artifact_digest"],
                "producer_call_ref": "call:constitutional_gate:attempt:1",
                "producer_call_receipt_digest": "sha256:" + "d" * 64,
                "producer_record_kind": "workflow_call_record_v1",
                "evidence_refs": ["ev-repository"],
                "concerns": ["authority drift"],
                "next_action": {"owner": "E1", "action": "repair authority drift"},
                "consumption": {
                    "measurement_status": "unavailable",
                    "unavailable_reason": "platform telemetry unavailable",
                },
                "payload_kind": "gate_fragment_v1",
                "payload": {"finding": "runtime claim conflicts with policy"},
            }
        ],
        "checks": [],
        "side_effects": {
            "repo_mutation": False,
            "runtime_contact": False,
            "private_external_contact": False,
            "broker_effect": False,
        },
        "unverified": [],
        "skipped_roles": route["skipped"],
        "consumption": {
            "measurement_status": "unavailable",
            "unavailable_reason": "platform usage telemetry was not exposed",
        },
        "next_action": {"owner": "E1", "action": "fix the failed authority gate"},
    }
    _refresh_standard_workflow_lineage(governance, packet)
    return packet


def test_closure_packet_separates_work_completion_from_gate_verdict() -> None:
    governance = _load_module()
    schema = json.loads(
        (ROOT / ".codex/schemas/closure_packet_v1.schema.json").read_text(encoding="utf-8")
    )
    assert schema["title"] == "closure_packet_v1"

    failed = _valid_failed_review_closure()
    assert governance.validate_closure(failed) == []

    impossible = deepcopy(failed)
    impossible["work_status"] = "BLOCKED"
    impossible["gate_verdict"] = "PASS"
    assert "blocked or no-delta closure cannot carry PASS" in governance.validate_closure(
        impossible
    )

    hidden_dissent = deepcopy(failed)
    hidden_dissent["gate_verdict"] = "PASS"
    assert "hard-gate fragment FAIL cannot be overridden by closure PASS" in (
        governance.validate_closure(hidden_dissent)
    )

    passing = deepcopy(failed)
    passing["gate_verdict"] = "PASS"
    passing["acceptance"][0]["status"] = "PASS"
    passing["role_fragments"][0].update(gate_verdict="PASS", concerns=[])
    _refresh_standard_workflow_lineage(governance, passing)
    assert any(
        "lacks out-of-band execution attestation" in error
        for error in governance.validate_closure(passing)
    )
    assert governance.validate_closure(
        passing,
        execution_attestation_verifier=_test_execution_attestation_verifier(passing),
    ) == []

    empty_acceptance = deepcopy(passing)
    empty_acceptance["acceptance"] = []
    assert "acceptance must not be empty" in governance.validate_closure(
        empty_acceptance
    )

    conditional_gate = deepcopy(passing)
    conditional_gate["role_fragments"][0]["gate_verdict"] = "CONDITIONAL"
    assert "hard-gate fragment must be PASS or NOT_APPLICABLE for closure PASS" in (
        governance.validate_closure(conditional_gate)
    )

    failed_check = deepcopy(passing)
    failed_check["checks"] = [
        {
            "id": "check-1",
            "status": "FAILED",
            "command": "pytest",
            "signature": "sha256:" + "f" * 64,
            "evidence_ref": "ev-source-1",
        }
    ]
    assert "closure PASS cannot contain FAILED checks" in governance.validate_closure(
        failed_check
    )

    generic_evidence = deepcopy(passing)
    repository_index = next(
        index for index, item in enumerate(generic_evidence["evidence"])
        if item["id"] == "ev-repository"
    )
    generic_evidence["evidence"][repository_index] = {
        "id": "ev-repository",
        "scope": "source",
        "kind": "diff_review",
        "digest": "sha256:" + "d" * 64,
        "observed_at": passing["adjudicated_at"],
    }
    assert "acceptance[0] PASS requires a typed content-addressed receipt" in (
        governance.validate_closure(generic_evidence)
    )

    tampered_context = deepcopy(passing)
    tampered_context["dispatch"]["context_artifact"]["canonical_plan"] += " "
    assert any(
        "dispatch context artifact invalid" in error
        for error in governance.validate_closure(tampered_context)
    )

    wrong_contract = deepcopy(passing)
    wrong_contract["role_fragments"][0]["task_contract_digest"] = (
        "sha256:" + "0" * 64
    )
    assert "role_fragments[0] task contract digest is not dispatch-bound" in (
        governance.validate_closure(wrong_contract)
    )

    unproven_effect = deepcopy(passing)
    unproven_effect["side_effects"]["runtime_contact"] = True
    effect_errors = governance.validate_closure(unproven_effect)
    assert "side_effect_class=none contradicts recorded effects" in effect_errors
    assert "runtime contact requires a typed runtime/effect receipt" in effect_errors

    stale_runtime = deepcopy(passing)
    stale_runtime["evidence"][0] = {
        "id": "ev-source-1",
        "scope": "runtime",
        "kind": "healthcheck",
        "digest": "sha256:" + "d" * 64,
    }
    runtime_errors = governance.validate_closure(stale_runtime)
    assert "runtime evidence requires host, environment, observed_at, and expiry" in (
        runtime_errors
    )
    assert runtime_errors

    route = governance.route_task(passing["dispatch"]["task_facts"])
    admitted = deepcopy(passing)
    admitted_node = {
        "node_id": "pm_admitted_secondary_review",
        "role": "E2",
        **governance.native_agent_binding("E2", "verification"),
        "node_class": "verification",
        "requires": ["constitutional_gate"],
        "path_scope": [],
        "reason": "independent second thought",
        "result_binding": "role_fragment",
    }
    admitted["dispatch"]["admitted_role_nodes"] = [admitted_node]
    admitted["skipped_roles"] = [
        item for item in route["skipped"] if item["role"] != "E2"
    ]
    extra_fragment = deepcopy(admitted["role_fragments"][0])
    extra_fragment.update(
        id="frag-pm-admitted-secondary-review",
        node_id="pm_admitted_secondary_review",
        role="E2",
        payload_kind=governance.load_registry()["roles"]["E2"]["payload_kind"],
        gate_verdict="PASS",
        summary="independent second thought passed",
        concerns=[],
    )
    admitted["role_fragments"].append(extra_fragment)
    _refresh_standard_workflow_lineage(governance, admitted)
    assert governance.validate_closure(
        admitted,
        execution_attestation_verifier=_test_execution_attestation_verifier(admitted),
    ) == []

    admitted_dissent = deepcopy(admitted)
    admitted_dissent["role_fragments"][-1]["gate_verdict"] = "FAIL"
    assert "admitted verification node pm_admitted_secondary_review requires PASS" in (
        governance.validate_closure(admitted_dissent)
    )

    omitted_admitted = deepcopy(admitted)
    omitted_admitted["role_fragments"].pop()
    assert "closure PASS missing admitted node fragment pm_admitted_secondary_review:E2" in (
        governance.validate_closure(omitted_admitted)
    )

    schema_invalid_packets = []
    empty_task_id = deepcopy(passing)
    empty_task_id["task_id"] = ""
    schema_invalid_packets.append(empty_task_id)
    missing_next_action = deepcopy(passing)
    del missing_next_action["next_action"]["action"]
    schema_invalid_packets.append(missing_next_action)
    nested_extra = deepcopy(passing)
    nested_extra["side_effects"]["surprise"] = False
    schema_invalid_packets.append(nested_extra)
    negative_consumption = deepcopy(passing)
    negative_consumption["consumption"] = {
        "measurement_status": "measured",
        "input_tokens": -1,
    }
    schema_invalid_packets.append(negative_consumption)
    for packet in schema_invalid_packets:
        assert governance.validate_closure(packet), packet


def test_closure_pass_cannot_hide_a_scope_admitted_review_blocker() -> None:
    governance = _load_module()
    packet = _valid_failed_review_closure()
    packet["gate_verdict"] = "PASS"
    packet["acceptance"][0]["status"] = "PASS"
    fragment = packet["role_fragments"][0]
    fragment.update(gate_verdict="PASS", concerns=[])
    generation = {
        field: packet["baseline"][field]
        for field in (
            "source_head", "dirty_diff_hash", "untracked_relevant_hash"
        )
    }
    criterion = packet["acceptance"][0]["criterion"]
    fragment["payload"] = {
        "review_control": {
            "schema_version": "review_control_v1",
            "task_contract_digest": governance.review_task_contract_digest(
                packet["dispatch"]["task_facts"]
            ),
            "non_goals": ["expand beyond the admitted authority review"],
            "final_generation": generation,
            "reviewers": [
                {
                    "node_id": fragment["node_id"],
                    "rounds": [
                        {
                            "round": 1,
                            "kind": "initial",
                            "reviewed_generation": generation,
                            "findings": [
                                {
                                    "id": "hidden-authority-blocker",
                                    "classification": "in_scope_blocker",
                                    "severity": "P3",
                                    "summary": "admitted hard boundary remains open",
                                    "paths": ["CLAUDE.md"],
                                    "evidence_refs": ["ev-repository"],
                                    "acceptance_criterion": criterion,
                                    "introduced_by_current_diff": False,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    }
    _refresh_standard_workflow_lineage(governance, packet)

    errors = governance.validate_closure(
        packet,
        execution_attestation_verifier=_test_execution_attestation_verifier(packet),
    )

    assert any("typed blockers cannot support PASS" in error for error in errors)

    forged_generation = deepcopy(packet)
    review = forged_generation["role_fragments"][0]["payload"]["review_control"]
    review["final_generation"]["source_head"] = "9" * 40
    review["reviewers"][0]["rounds"][0]["reviewed_generation"] = deepcopy(
        review["final_generation"]
    )
    review["reviewers"][0]["rounds"][0]["findings"] = []
    _refresh_standard_workflow_lineage(governance, forged_generation)

    errors = governance.validate_closure(
        forged_generation,
        execution_attestation_verifier=_test_execution_attestation_verifier(
            forged_generation
        ),
    )

    assert any("differs from trusted repository generation" in error for error in errors)


def test_terminal_closure_does_not_invent_next_work_and_no_delta_never_passes() -> None:
    governance = _load_module()

    completed = _valid_failed_review_closure()
    completed["next_action"] = None
    assert governance.validate_closure(completed) == []

    no_delta = deepcopy(completed)
    no_delta["work_status"] = "BLOCKED_NO_DELTA"
    assert governance.validate_closure(no_delta) == []

    false_pass = deepcopy(no_delta)
    false_pass["gate_verdict"] = "PASS"
    assert any(
        "no-delta closure cannot carry PASS" in error
        for error in governance.validate_closure(false_pass)
    )

    invented = deepcopy(no_delta)
    invented["next_action"] = {"owner": "PM", "action": "try the same work again"}
    assert any(
        "BLOCKED_NO_DELTA must have next_action=null" in error
        for error in governance.validate_closure(invented)
    )

    waiting_without_owner = deepcopy(completed)
    waiting_without_owner["work_status"] = "BLOCKED"
    assert any(
        "require an owned next_action" in error
        for error in governance.validate_closure(waiting_without_owner)
    )


def test_terminal_role_fragment_may_omit_action_but_blocked_fragment_may_not() -> None:
    governance = _load_module()
    packet = _valid_failed_review_closure()
    fragment = packet["role_fragments"][0]
    fragment["work_status"] = "DONE_WITH_CONCERNS"
    fragment["next_action"] = None
    _refresh_standard_workflow_lineage(governance, packet)
    assert governance.validate_closure(packet) == []

    fragment["work_status"] = "BLOCKED"
    _refresh_standard_workflow_lineage(governance, packet)
    assert any(
        "BLOCKED/NEEDS_CONTEXT require an owned next_action" in error
        for error in governance.validate_closure(packet)
    )


def test_full_audit_control_cannot_hide_axis_debt_or_omit_admitted_fragments() -> None:
    support_path = ROOT / "tests/structure/test_agent_governance_full_audit_adversarial.py"
    spec = importlib.util.spec_from_file_location(
        "agent_governance_full_audit_test_support", support_path
    )
    assert spec is not None and spec.loader is not None
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    governance, contract, packet = support._clean_packet()
    assert "E2" in contract["axes"]

    controller = support._controller(packet, contract)
    axis = contract["axes"][0]
    hidden_hole = deepcopy(packet)
    hidden_controller = support._controller(hidden_hole, contract)
    hidden_controller["payload"].update(
        coverage_holes=[axis],
        pass_eligible=False,
        unverified_projection=[
            "full_audit_hole:" + json.dumps(
                {"axis": axis}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        ],
    )
    hidden_controller["gate_verdict"] = "UNVERIFIED"
    hidden_controller["concerns"] = hidden_controller["payload"]["unverified_projection"]
    hidden_hole.update(
        work_status="DONE_WITH_CONCERNS",
        gate_verdict="UNVERIFIED",
        unverified=hidden_controller["payload"]["unverified_projection"],
    )
    assert f"full audit coverage hole {axis} lacks canonical coverage debt" in (
        governance.validate_closure(hidden_hole)
    )

    omitted = deepcopy(packet)
    omitted["role_fragments"] = [
        fragment
        for fragment in omitted["role_fragments"]
        if fragment["node_id"] != f"audit:{axis}"
    ]
    omitted_errors = governance.validate_closure(omitted)
    assert f"closure PASS missing admitted node fragment audit:{axis}:{axis}" in (
        omitted_errors
    )
    assert f"full audit admitted axis {axis} is missing its bound fragment" in (
        omitted_errors
    )

    substituted = deepcopy(packet)
    target = next(
        fragment
        for fragment in substituted["role_fragments"]
        if fragment["node_id"] == f"audit:{axis}"
    )
    target["summary"] = "content changed after controller binding"
    assert f"full audit axis {axis} fragment digest does not match controller" in (
        governance.validate_closure(substituted)
    )


def test_report_sink_projects_one_deterministic_closure_without_hiding_dissent() -> None:
    governance = _load_module()
    packet = _valid_failed_review_closure()

    first = governance.project_closure(packet)
    second = governance.project_closure(deepcopy(packet))

    assert first == second
    assert "# Closure: agent-governance-review" in first
    assert "Work status | `DONE`" in first
    assert "Gate verdict | `FAIL`" in first
    assert "CC" in first
    assert "frag-cc-1" in first
    assert "ev-source-1" in first
    assert "authority drift" in first
    assert "gate_fragment_v1" in first
    assert "| Payload kind | Payload | Evidence |" in first
    assert '{"finding":"runtime claim conflicts with policy"}' in first
    assert '"gate_verdict": "FAIL"' in first

    invalid = deepcopy(packet)
    invalid["gate_verdict"] = "PASS"
    try:
        governance.project_closure(invalid)
    except ValueError as exc:
        assert "hard-gate fragment FAIL" in str(exc)
    else:
        raise AssertionError("invalid closure projection must fail closed")


def test_typed_authority_matrix_preserves_cross_class_conflict() -> None:
    governance = _load_module()
    normative = governance.build_authority_claim(
        authority_class="normative_policy",
        subject="ibkr.live_allowed",
        value=False,
        source="CLAUDE.md#Product Boundary",
        source_ref="capture:normative-policy",
        source_digest="sha256:" + "a" * 64,
        observed_at="2026-07-10T10:00:00Z",
        scope="ibkr:live",
        strength="direct",
        expiry=None,
    )
    runtime = governance.build_authority_claim(
        authority_class="runtime_observation",
        subject="ibkr.live_allowed",
        value=True,
        source="trade-core env",
        source_ref="capture:runtime-observation",
        source_digest="sha256:" + "b" * 64,
        observed_at="2026-07-10T10:55:00Z",
        scope="ibkr:live",
        strength="direct",
        expiry="2026-07-10T11:10:00Z",
    )
    claims = [normative, runtime]
    decision = governance.resolve_authority_claims(
        claims, adjudicated_at="2026-07-10T11:00:00Z"
    )
    assert decision["status"] == "CONFLICT"
    assert decision["gate_verdict"] == "BLOCKED"
    assert decision["claims"] == claims
    assert decision["winner"] is None

    def runtime_claim(value: bool, observed_at: str, expiry: str) -> dict:
        return governance.build_authority_claim(
            authority_class="runtime_observation",
            subject="ibkr.live_allowed",
            value=value,
            source="trade-core env",
            source_ref="capture:runtime-observation",
            source_digest="sha256:" + "b" * 64,
            observed_at=observed_at,
            scope="ibkr:live",
            strength="direct",
            expiry=expiry,
        )

    runtime_only = governance.resolve_authority_claims(
        [
            runtime_claim(False, "2026-07-10T10:55:00Z", "2026-07-10T11:10:00Z"),
            runtime_claim(True, "2026-07-10T11:00:00Z", "2026-07-10T11:15:00Z"),
        ],
        adjudicated_at="2026-07-10T11:05:00Z",
    )
    assert runtime_only["status"] == "FRESHEST_WITHIN_CLASS"
    assert runtime_only["winner"]["value"] is True

    timezone_ordered = governance.resolve_authority_claims(
        [
            runtime_claim(
                False,
                "2026-07-10T10:59:00+02:00",
                "2026-07-10T11:14:00+02:00",
            ),
            runtime_claim(True, "2026-07-10T09:00:00Z", "2026-07-10T09:15:00Z"),
        ],
        adjudicated_at="2026-07-10T09:05:00Z",
    )
    assert timezone_ordered["winner"]["value"] is True

    tied_conflict = governance.resolve_authority_claims(
        [
            runtime_claim(False, "2026-07-10T09:00:00Z", "2026-07-10T09:15:00Z"),
            runtime_claim(
                True,
                "2026-07-10T09:00:00+00:00",
                "2026-07-10T09:15:00+00:00",
            ),
        ],
        adjudicated_at="2026-07-10T09:05:00Z",
    )
    assert tied_conflict["status"] == "CONFLICT_WITHIN_CLASS"
    assert tied_conflict["gate_verdict"] == "BLOCKED"


def test_test_evidence_reuse_is_content_addressed_and_fail_closed() -> None:
    governance = _load_module()
    facts = {
        "source_head": "a" * 40,
        "dirty_diff_hash": "sha256:" + "b" * 64,
        "untracked_relevant_hash": "sha256:" + "c" * 64,
        "command": "python3 -m pytest tests/structure/test_x.py -q",
        "selected_tests": ["test_x"],
        "toolchain": "python-3.10.14/pytest-9.0.3",
        "dependency_lock_hash": "sha256:" + "d" * 64,
        "os": "macOS",
        "arch": "arm64",
        "env_mode": "source-only-no-secrets",
        "config_hash": "sha256:" + "e" * 64,
        "runtime_head": None,
        "authorization_hash": None,
    }
    signature = governance.test_evidence_signature(facts)
    assert signature.startswith("sha256:")

    for field in facts:
        changed = deepcopy(facts)
        changed[field] = ["changed"] if field == "selected_tests" else f"changed-{field}"
        assert governance.test_evidence_signature(changed) != signature

    try:
        governance.test_evidence_signature(
            {**facts, "unbound_future_input": "ignored-before-fix"}
        )
    except ValueError as exc:
        assert "unsigned fields" in str(exc)
    else:
        raise AssertionError("unsigned test-affecting fields must fail closed")

    execution = governance.build_test_execution_receipt(
        facts,
        executor_role="E4",
        started_at="2026-07-11T10:00:00Z",
        completed_at="2026-07-11T10:01:00Z",
        exit_code=0,
        result="PASS",
        evidence_digest="sha256:" + "f" * 64,
        output_digest="sha256:" + "1" * 64,
    )
    capsule = {
        "schema_version": "test_evidence_capsule_v2",
        "signature": signature,
        "status": "PASS",
        "created_at": execution["completed_at"],
        "expires_at": "2026-07-11T14:00:00Z",
        "critical": False,
        "flaky": False,
        "execution_receipt": execution,
        "independent_recheck_receipt": None,
    }
    reuse_receipt = governance.assess_test_evidence_reuse(
        capsule, facts, now="2026-07-11T12:00:00Z"
    )
    assert reuse_receipt["status"] == "REUSED"
    assert reuse_receipt["execution_receipt_digest"] == execution["receipt_digest"]
    assert reuse_receipt["execution_evidence_digest"] == execution["evidence_digest"]
    assert governance.validate_test_evidence_reuse_receipt(
        reuse_receipt,
        check_signature=signature,
        evidence_digest=execution["evidence_digest"],
        reused_from=execution["completed_at"],
        adjudicated_at="2026-07-11T12:30:00Z",
    ) == []

    legacy = deepcopy(capsule)
    legacy.pop("execution_receipt")
    legacy["execution_evidence_digest"] = execution["evidence_digest"]
    assert governance.assess_test_evidence_reuse(
        legacy, facts, now="2026-07-11T12:00:00Z"
    )["eligible"] is False

    expired = deepcopy(capsule)
    expired["expires_at"] = "2026-07-11T11:00:00Z"
    assert governance.assess_test_evidence_reuse(
        expired, facts, now="2026-07-11T12:00:00Z"
    )["eligible"] is False

    flaky = deepcopy(capsule)
    flaky["flaky"] = True
    assert governance.assess_test_evidence_reuse(
        flaky, facts, now="2026-07-11T12:00:00Z"
    )["eligible"] is False

    critical = deepcopy(capsule)
    critical["critical"] = True
    assert governance.assess_test_evidence_reuse(
        critical, facts, now="2026-07-11T12:00:00Z"
    )["eligible"] is False
    critical["independent_recheck_receipt"] = governance.build_test_recheck_receipt(
        execution,
        reviewer_role="E2",
        observed_at="2026-07-11T11:30:00Z",
        result="PASS",
        evidence_digest="sha256:" + "2" * 64,
    )
    assert governance.assess_test_evidence_reuse(
        critical, facts, now="2026-07-11T12:00:00Z"
    )["eligible"] is True

    overlong = deepcopy(capsule)
    overlong["expires_at"] = "2026-07-12T10:02:00Z"
    assert governance.assess_test_evidence_reuse(
        overlong, facts, now="2026-07-11T12:00:00Z"
    )["eligible"] is False


def test_read_only_bash_policy_denies_effects_and_allows_declared_probes() -> None:
    governance = _load_module()

    assert governance.authorize_command("E2", "git diff -- rust/openclaw_engine")["allowed"] is True
    assert governance.authorize_command("E2", "python3 -m pytest tests/structure/test_x.py -q")["allowed"] is True
    assert governance.authorize_command(
        "OPS", "ssh trade-core 'systemctl --user is-active openclaw-trading-api.service'"
    )["allowed"] is True
    assert governance.authorize_command(
        "OPS",
        "ssh trade-core 'systemctl --user show openclaw-trading-api.service --property=ActiveState,SubState,MainPID,ExecMainStatus --no-pager'",
    )["allowed"] is True
    assert governance.authorize_command(
        "OPS", "ssh trade-core 'ps -eo pid,ppid,stat,etime,comm'"
    )["allowed"] is True
    assert governance.authorize_command(
        "OPS", "ssh trade-core 'psql -X -c \"SELECT now();\"'"
    )["allowed"] is False
    assert governance.authorize_command(
        "QA", "ssh trade-core 'curl --fail --silent http://localhost:8000/api/v1/health'"
    )["allowed"] is True
    assert governance.authorize_command(
        "R4",
        "python3 helper_scripts/maintenance_scripts/agent_governance.py render --check",
    )["allowed"] is True
    assert governance.authorize_command(
        "E2",
        "python3 helper_scripts/maintenance_scripts/agent_governance.py context --role E2 @task_facts.json",
    )["allowed"] is True

    denied = [
        ("E2", "git add rust/openclaw_engine"),
        ("E2", "sed -i '' 's/a/b/' file.py"),
        ("E2", "sed -n '1e echo forbidden' AGENTS.md"),
        ("OPS", "ssh trade-core 'systemctl --user restart openclaw-trading-api.service'"),
        ("OPS", "ssh trade-core 'systemctl --user status openclaw-trading-api.service'"),
        ("OPS", "ssh trade-core 'systemctl --user show openclaw-trading-api.service --property=Environment'"),
        ("OPS", "ssh trade-core 'journalctl --user -u openclaw-trading-api.service --lines 20'"),
        ("OPS", "ssh trade-core 'ps auxe'"),
        ("OPS", "ssh trade-core 'psql -c \"UPDATE risk SET enabled=true;\"'"),
        ("IB", "curl -X POST http://127.0.0.1:7497/v1/orders"),
        ("QA", "ssh trade-core 'curl -X POST http://localhost:8000/api/v1/operator/restart'"),
        ("CC", "echo PASS > docs/CCAgentWorkSpace/CC/memory.md"),
        ("E2", "git diff -- rust; python3 -c 'open(\"owned\", \"w\").write(\"x\")'"),
        ("E2", "rg TODO $(touch owned)"),
        ("E2", "find . -exec sh -c 'touch owned' \\;"),
        ("E2", "cargo fmt"),
        ("OPS", "ssh trade-core 'ps; kill -9 1'"),
        ("OPS", "ssh trade-core 'journalctl --rotate'"),
        ("OPS", "ssh trade-core 'fuser -k 8000/tcp'"),
        ("R4", "python3 helper_scripts/maintenance_scripts/agent_governance.py render"),
        ("R4", "python3 helper_scripts/maintenance_scripts/agent_governance.py context --role R4 @/etc/passwd"),
        ("R4", "head ~/.ssh/id_rsa"),
        ("R4", "find /"),
        ("E2", "rg PATTERN /Users/ncyu"),
        ("E2", "sed -n '1,20p' ../outside"),
        ("OPS", "ssh trade-core 'cat ~/.ssh/id_rsa'"),
        ("OPS", "ssh trade-core 'curl -o /tmp/governance-write http://localhost:8000/api/v1/health'"),
        ("QA", "ssh trade-core 'curl https://example.com http://localhost:8000/api/v1/health'"),
        ("OPS", "ssh trade-core 'psql -c \"SELECT pg_terminate_backend(123);\"'"),
    ]
    for role, command in denied:
        decision = governance.authorize_command(role, command)
        assert decision["allowed"] is False, (role, command, decision)

    assert governance.authorize_command("E2", "cargo fmt --check")["allowed"] is True


def test_authorize_command_cli_does_not_collide_with_subcommand_name() -> None:
    allow = subprocess.run(
        [
            "python3",
            str(MODULE_PATH),
            "authorize-command",
            "--role",
            "E2",
            "--command",
            "git diff -- AGENTS.md",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert allow.returncode == 0, allow.stderr
    assert json.loads(allow.stdout)["allowed"] is True

    deny = subprocess.run(
        [
            "python3",
            str(MODULE_PATH),
            "authorize-command",
            "--role",
            "E2",
            "--command",
            "git add AGENTS.md",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert deny.returncode == 2, deny.stderr
    assert json.loads(deny.stdout)["allowed"] is False


def test_authorize_command_cli_resolves_exact_native_identity_fail_closed() -> None:
    cases = [
        ("PA-investigator", "rg -n Interface CONTEXT.md"),
        ("E4-verifier", "python3 -m pytest tests/structure/test_agent_governance_node_permissions.py -q"),
    ]
    for native_agent, command in cases:
        completed = subprocess.run(
            [
                "python3", str(MODULE_PATH), "authorize-command",
                "--native-agent", native_agent, "--command", command,
            ],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert completed.returncode == 0, (native_agent, completed.stderr)
        decision = json.loads(completed.stdout)
        assert decision["allowed"] is True
        assert decision["native_agent"] == native_agent
        assert decision["node_class"] == "verification"
        assert decision["effective_permission"] == "read_only"

    for unknown in ("PA", "E4", "E4-verifier-forged", "UNKNOWN"):
        denied = subprocess.run(
            [
                "python3", str(MODULE_PATH), "authorize-command",
                "--native-agent", unknown, "--command", "git status",
            ],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert denied.returncode == 2
        assert json.loads(denied.stdout)["allowed"] is False


def test_authoritative_docs_route_to_one_governance_module_without_fixed_budget_drift() -> None:
    authority_paths = [
        "AGENTS.md",
        "CLAUDE.md",
        ".codex/AGENT_DISPATCH_PROTOCOL.md",
        ".codex/SUBAGENT_EXECUTION_RULES.md",
        "docs/agents/context-loading.md",
        "docs/agents/role-profile-memory-standard.md",
    ]
    texts = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in authority_paths
    }
    for path, text in texts.items():
        assert ".codex/agent_registry_v1.json" in text, path

    combined = "\n".join(texts.values())
    assert "PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM" not in combined
    assert "4,000 per task" not in combined
    assert "30,000 per session" not in combined
    assert "shared context only paid once" not in combined
    assert "共享 context 只付一次" not in combined

    assert (
        len(
            (ROOT / ".codex/MEMORY.md")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        <= MAX_FILE_LINES
    )
    root_skill = (ROOT / ".claude/skills/16-root-principles-checklist/SKILL.md").read_text(encoding="utf-8")
    assert "runtime RiskConfig TOML > Rust schema" not in root_skill
    regression = (ROOT / ".claude/skills/regression-testing-protocol/SKILL.md").read_text(encoding="utf-8")
    assert "ssh trade-core" not in regression
    assert "第二次同樣綠才算" not in regression

    skill_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / ".claude/skills").rglob("*.md")
    )
    assert "權威序：runtime RiskConfig TOML > Rust schema" not in skill_text
    assert "report_path" not in skill_text
    assert "E1→E2→E4→QA→PM 不可跳" not in skill_text
    assert "E2 失敗 → E1 修 → 重 E2 → E4，任何情況不可跳" not in skill_text
    assert not re.search(
        r"immutable `(design|finding|gate|patch|review|test|operation_review|docs)_fragment_v1`",
        skill_text,
    )

    assert (ROOT / "docs/agents/development-agent-governance.md").is_file()
    assert (ROOT / "docs/adr/0050-development-agent-governance.md").is_file()

    register = (ROOT / "docs/governance_dev/SPECIFICATION_REGISTER.md").read_text(encoding="utf-8")
    for path in (ROOT / "docs/adr").glob("[0-9][0-9][0-9][0-9]-*.md"):
        number = int(path.name[:4])
        if number >= 34:
            assert f"ADR-{number:04d}" in register, path
            assert f"docs/adr/{path.name}" in register, path


def test_saved_workflows_expose_closure_and_consumption_envelopes() -> None:
    wave = (ROOT / ".claude/workflows/agent-wave.js").read_text(encoding="utf-8")
    audit = (ROOT / ".claude/workflows/openclaw-full-audit.js").read_text(encoding="utf-8")

    assert "role_fragment_v1" in wave
    assert "closure_fragment_v1" not in wave
    assert "CLOSURE_FRAGMENT_SCHEMA" not in wave
    assert "summary: { type: 'string', minLength: 1 }" in wave
    assert "items: { type: 'string', minLength: 1 }" in wave
    assert "owner: { type: 'string', minLength: 1 }" in wave
    assert "action: { type: 'string', minLength: 1 }" in wave
    assert "task node_id values must be unique" in wave
    assert "legacy task arrays are unverified and rejected" in wave
    assert "contextArtifact.schema_version !== 'context_artifact_v1'" in wave
    assert "verifiedContextBytes.map(sha256Bytes)" in wave
    assert "digest !== contextCapsules[index].artifact_digest" in wave
    assert "contextBudget.pass_allowed !== true" in wave
    assert "contextArtifact.blocking_sources.length" in wave
    assert "contextPath: task.contextPath" not in wave
    assert "JSON.stringify(task.contextPlan)" not in wave
    assert "const verifiedContextBytes = contextCapsules.map(artifact => artifact.canonical_plan)" in wave
    assert "verifiedContextBytes" in wave
    assert "identity_coverage_debt" in wave
    assert "task_contract_digest" in wave
    assert "const JUDGMENT_SCHEMA" in wave
    assert "schema: JUDGMENT_SCHEMA" in wave
    assert "workflow_call_record_v1" in wave
    assert "workflow_call_manifest_v1" in wave
    assert "workflow_wave_record_v1" in wave
    assert "context_artifact_digest" in wave
    assert "producer_call_ref" in wave
    assert "producer_call_receipt_digest" in wave
    assert "producer_record_kind" in wave
    assert "parsed_result_digest" in wave
    assert "max_unique_nodes" in wave
    assert "max_call_attempts" in wave
    assert "retry_budget" in wave
    assert "measurement_status" in wave
    assert "共享 context 只付一次" not in wave

    for token in (
        "max_unique_nodes",
        "max_call_attempts",
        "max_context_tokens_per_call",
        "max_verification_calls",
        "max_workflow_planned_input_tokens",
        "retry_budget",
        "adaptive_shadow",
        "coverage_debt",
        "pass_eligible",
        "decision_changing_findings",
    ):
        assert token in audit
    assert "report_path" not in audit
    assert "memory BASELINE" not in audit
    assert "baseline is required" in audit
    assert "baseline must be a structured object" in audit
    assert "baseline.runtime_head is required for runtime-claim surfaces" in audit
    assert "baselineIdentity" in audit
    assert "JSON.stringify(baseline)" in audit
    assert "axis !== 'E4'" not in audit
    assert "axis !== 'TW'" not in audit
    assert "configured subset omitted a full-audit backstop axis" in audit
    assert "seam critic missing" in audit
    assert "kind: 'assumption'" in audit
    assert "?? 9" in audit
    assert "|| 9" not in audit
    assert "actual model output/cache/tool/controller telemetry is unavailable" in audit
    assert "wave_record_refs: [waveRecord.record_digest]" in audit
    assert "role_fragment_v1" in audit
    assert "role_fragments: [controlFragment, ...roleFragments]" in audit
    assert "full_audit_control_v1" in audit
    assert "closure_admissions: closureAdmissions" in audit
    assert "unverified_projection" in audit
    assert "adaptive_recall_authority_digest" in audit
    assert "selection_surfaces" in audit
    assert "run_sequence: runSequence" in audit
    assert "seam_result_digest: seamResultDigest" in audit
    assert "verification_outcomes: verificationOutcomes" in audit
    assert "axis_fragment_digests: axisFragmentDigests" in audit
    assert "full_audit_debt:${canonicalJson" in audit
    assert "estimated_seam_tokens" in audit
    assert "estimated_fix_tokens" in audit
    assert "estimated_review_tokens" in audit
    assert "estimated_regression_tokens" in audit
    assert "retryBudget * auditCallTokens" in audit
    assert "const fixReserveNodes = 3" in audit
    assert "fixCallTokens + reviewCallTokens + regressionCallTokens" in audit
    assert "regressionReserved" in audit

    profit = (ROOT / ".claude/workflows/profit-diagnosis.js").read_text(encoding="utf-8")
    assert "report_path" not in profit
    assert "max_unique_nodes" in profit
    assert "max_call_attempts" in profit
    assert "max_workflow_planned_input_tokens" in profit
    assert "retry_budget" in profit
    assert "coverage_debt" in profit
    assert "priors_digest" in profit
    assert "agentType: 'IB'" in profit
    assert "agentType: 'OPS'" in profit
    assert "opportunities: { type: 'array', minItems: 1" not in profit
    assert "addCoverageDebt('map', 'PA'" in profit
    assert "baseline_digest: baselineDigest" in profit
    assert "planned_input_tokens: plannedTokens" in profit
    assert "mapResult.work_status === 'DONE'" in profit
    assert "actual model output/cache/tool/controller telemetry is unavailable" in profit
    assert "wave_record_refs: [waveRecord.record_digest]" in profit
    assert "role_fragment_v1" in profit
    assert "role_fragments: [controlFragment, ...roleFragments]" in profit


def test_active_governance_vocabulary_and_dispatch_template_use_one_fragment_and_hybrid_dag() -> None:
    registry_text = (ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8")
    subagent_rules = (ROOT / ".codex/SUBAGENT_EXECUTION_RULES.md").read_text(encoding="utf-8")
    hygiene = (ROOT / "docs/agents/sub-agent-hygiene-sop.md").read_text(encoding="utf-8")
    context = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    ledger = (ROOT / ".codex/DISPATCH_LEDGER.md").read_text(encoding="utf-8")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    governance_doc = (ROOT / "docs/agents/development-agent-governance.md").read_text(encoding="utf-8")

    assert "closure_fragment" not in registry_text
    assert "closure fragment" not in subagent_rules.lower()
    assert "closure fragment" not in hygiene.lower()
    assert "closure fragment" not in context.lower()
    assert "PM -> PA(default) -> E1(worker) -> E2(explorer) -> PM" not in ledger
    assert "DAG digest" in ledger
    assert "required node" in ledger
    assert "Within one authority class" in claude
    assert "No development-agent broker" in agents
    assert "unsupported-effect blocker" in agents
    assert "repository policy and command preflight, not an OS/platform sandbox" in agents
    assert "not an OS/platform sandbox" in governance_doc

    registry = json.loads(registry_text)
    assert registry["permission_enforcement"] == {
        "scope": "repository_policy_and_command_preflight",
        "not_a_sandbox": True,
        "platform_tools_may_be_broader": True,
    }

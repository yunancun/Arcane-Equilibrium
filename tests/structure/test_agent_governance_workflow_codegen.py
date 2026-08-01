"""Drift and loader checks for generated standalone workflow Context blocks."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_workflow_codegen import (  # noqa: E402
    BEGIN,
    SHADOW_RE,
    WORKFLOWS,
    render_context_admission_block,
    workflow_context_codegen_errors,
)
import agent_governance_workflow_codegen as codegen  # noqa: E402
from agent_governance_registry import load_registry  # noqa: E402
from agent_governance_execution_dag import execution_node_core  # noqa: E402
from agent_governance_routing import (  # noqa: E402
    P0B_CLAIM_KEYS_BY_PHASE,
    S2_CLAIM_KEYS_BY_STEP,
    S2_EFFECT_STEPS,
    p0b_effect_selection_digest,
    route_task,
    s2_effect_selection_digest,
    task_contract_projection,
)
from agent_governance_aiml_adoption import (  # noqa: E402
    AIML_PROGRAM_ADOPTION_CLAIM_KEYS,
    AIML_PROGRAM_ADOPTION_PREDECESSOR_DIGESTS,
    AIML_PROGRAM_ADOPTION_SELECTOR_DIGEST,
)


def _async_function_syntax(source: str) -> subprocess.CompletedProcess[str]:
    wrapper = (
        "const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;"
        "new AsyncFunction('args','phase','log','parallel','pipeline','agent',"
        + json.dumps(source.replace("export const meta =", "const meta ="))
        + ");"
    )
    return subprocess.run(
        ["node", "-e", wrapper], cwd=ROOT, text=True, capture_output=True,
        check=False,
    )


def test_context_codegen_block_is_exact_used_and_standalone_parseable() -> None:
    assert workflow_context_codegen_errors() == []
    expected = render_context_admission_block()
    for path in WORKFLOWS:
        source = path.read_text(encoding="utf-8")
        assert expected in source
        assert "+// BEGIN GENERATED" not in source
        assert source.count("contextPrefixV1(") >= 1
        assert _async_function_syntax(source).returncode == 0


def test_codegen_guards_have_negative_controls() -> None:
    assert SHADOW_RE.search("const budgetFields = []")
    source = WORKFLOWS[0].read_text(encoding="utf-8")
    leaked_patch_marker = source.replace(BEGIN, "+" + BEGIN, 1)
    assert _async_function_syntax(leaked_patch_marker).returncode != 0

    with pytest.raises(ValueError, match="Registry must be a non-empty object"):
        render_context_admission_block({})


def test_generated_path_canonicalization_matches_python_unicode_order(
    tmp_path: Path,
) -> None:
    block = render_context_admission_block()
    script = "\n".join((
        "const canonicalJson = value => JSON.stringify(value);",
        block,
        "const expected = ['unicode/\\uE000.py', 'unicode/😀.py'];",
        "const reversed = [...expected].reverse();",
        "console.log(JSON.stringify({",
        "  sorted: [...reversed].sort(unicodeCodePointCompareV1),",
        "  valid: validRepositoryScopeV1(expected),",
        "  verificationAlias: validVerificationScopeV1(expected),",
        "  reversed: validRepositoryScopeV1(reversed),",
        "  tilde: validRepositoryPathV1('~/escape.py'),",
        "  backslash: validRepositoryPathV1('windows\\\\style.py'),",
        "  lone: validRepositoryPathV1('bad\\ud800.py'),",
        "}));",
    ))
    script_path = tmp_path / "generated-path-canonicalization.js"
    script_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(script_path)], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "sorted": ["unicode/\ue000.py", "unicode/😀.py"],
        "valid": True,
        "verificationAlias": True,
        "reversed": False,
        "tilde": False,
        "backslash": False,
        "lone": False,
    }
    agent_wave = WORKFLOWS[0].read_text(encoding="utf-8")
    assert "!validRepositoryScopeV1(contract.dirty_scope)" in agent_wave
    assert (
        "Object.keys(value).sort(unicodeCodePointCompareV1)" in agent_wave
    )
    for workflow in WORKFLOWS[1:]:
        source = workflow.read_text(encoding="utf-8")
        assert "!validRepositoryScopeV1(value)" in source
        assert (
            "Object.keys(value).sort(unicodeCodePointCompareV1)" in source
        )


def test_generated_generic_route_core_matches_python_corpus(
    tmp_path: Path,
) -> None:
    digest = "sha256:" + "a" * 64
    base = {
        "risk": "low",
        "uncertainty": "low",
        "runtime_claim": False,
        "end_to_end_claim": False,
        "scope": ["AGENTS.md"],
        "dirty_scope": [],
        "verification_scope": [],
        "direct_interfaces": [],
        "claim_inputs": {},
        "task_prompt": "exercise canonical generic route projection",
    }
    aiml_claims = {key: digest for key in AIML_PROGRAM_ADOPTION_CLAIM_KEYS}
    aiml_claims["aiml_program_adoption_selection"] = (
        AIML_PROGRAM_ADOPTION_SELECTOR_DIGEST
    )
    aiml_claims.update(AIML_PROGRAM_ADOPTION_PREDECESSOR_DIGESTS)
    s2_claims = {key: digest for key in S2_CLAIM_KEYS_BY_STEP["S2_0_APPLY"]}
    s2_claims["s2_effect_adapter_selection"] = s2_effect_selection_digest(
        "S2_0_APPLY"
    )
    p0b_claims = {key: digest for key in P0B_CLAIM_KEYS_BY_PHASE["stage"]}
    p0b_claims["p0b_effect_adapter_selection"] = p0b_effect_selection_digest(
        "stage"
    )
    facts_corpus = [
        {**base, "task_shape": "query", "surfaces": ["comments"]},
        {
            **base, "task_shape": "implementation", "surfaces": ["python"],
            "scope": ["src/server.py"], "dirty_scope": ["src/server.py"],
        },
        {
            **base, "task_shape": "implementation", "surfaces": ["gui", "python"],
            "scope": ["control_api_v1/static/app.js", "src/server.py"],
            "dirty_scope": ["control_api_v1/static/app.js", "src/server.py"],
        },
        {
            **base, "task_shape": "implementation", "surfaces": ["gui", "python"],
            "scope": [".md", "gui/src/App.tsx"],
            "dirty_scope": [".md", "gui/src/App.tsx"],
        },
        {
            **base, "task_shape": "docs", "surfaces": ["docs"],
            "scope": ["docs/guide.md"], "dirty_scope": ["docs/guide.md"],
        },
        {
            **base, "task_shape": "test", "surfaces": ["python"],
            "scope": ["tests/test_route.py"],
            "dirty_scope": ["tests/test_route.py"],
        },
        {**base, "task_shape": "review", "surfaces": []},
        {
            **base, "task_shape": "analysis", "surfaces": ["architecture"],
            "risk": "high",
        },
        {
            **base, "task_shape": "review", "surfaces": ["service"],
            "runtime_claim": True, "risk": "high",
        },
        {**base, "task_shape": "review", "surfaces": ["bybit"]},
        {**base, "task_shape": "review", "surfaces": ["ibkr"]},
        {**base, "task_shape": "research", "surfaces": ["public_web_read"]},
        {
            **base, "task_shape": "review", "surfaces": ["functional"],
            "end_to_end_claim": True,
        },
        {
            **base, "task_shape": "deploy",
            "surfaces": ["authority", "deploy", "runtime_effect", "service"],
            "risk": "high", "runtime_claim": True,
        },
        {
            **base, "task_shape": "review", "surfaces": ["runtime_effect"],
            "risk": "high", "runtime_claim": True,
            "side_effect_class": "target_host_probe",
        },
        {
            **base, "task_shape": "review", "surfaces": ["pg"],
            "risk": "high", "runtime_claim": True,
            "side_effect_class": "pg_observer_bootstrap",
        },
        {
            **base, "task_shape": "review",
            "surfaces": ["bybit", "private_external_contact"],
            "risk": "high", "side_effect_class": "broker_probe",
        },
        {
            **base, "task_shape": "review", "surfaces": ["runtime_effect"],
            "risk": "high", "runtime_claim": True,
            "side_effect_class": "s2_4_prepare_intent",
        },
        {
            **base, "task_shape": "query", "risk": "high",
            "surfaces": [
                "acceptance", "authority", "closure", "governance",
                "ml_data", "policy", "schema",
            ],
            "claim_inputs": aiml_claims,
        },
        {
            **base, "task_shape": "review",
            "surfaces": ["authority", "pg", "runtime_effect"],
            "risk": "high", "runtime_claim": True,
            "side_effect_class": "pg_observer_bootstrap",
            "claim_inputs": s2_claims,
        },
        {
            **base, "task_shape": "deploy",
            "surfaces": ["authority", "deploy", "runtime_effect", "service"],
            "risk": "high", "runtime_claim": True,
            "claim_inputs": p0b_claims,
        },
        {
            **base, "task_shape": "review", "surfaces": ["python"],
            "claim_inputs": {"generic_source_task": digest},
        },
    ]
    gate_surfaces = [
        "functional", "authority", "security", "quant", "ml", "ai",
        "performance", "ux", "governance", "bybit", "ibkr", "service",
    ]
    facts_corpus.extend(
        {**base, "task_shape": "review", "surfaces": [surface]}
        for surface in gate_surfaces
    )
    facts_corpus.extend([
        {
            **base, "task_shape": "review", "surfaces": ["python"],
            "continuation_mode": "operator_loop",
            "task_prompt": "/loop\nreview the bounded source scope",
        },
        {
            **base, "task_shape": "review",
            "surfaces": ["authority", "functional", "ml", "service"],
            "risk": "unknown", "uncertainty": "unknown",
            "runtime_claim": True, "end_to_end_claim": True,
        },
        {
            **base, "task_shape": "review",
            "surfaces": ["private_external_contact", "stock_etf_cash"],
            "risk": "high", "side_effect_class": "broker_private_effect",
        },
        {
            **base, "task_shape": "review",
            "surfaces": ["private_external_contact"],
            "risk": "high", "side_effect_class": "private_external_contact",
        },
        {
            **base, "task_shape": "review", "surfaces": ["runtime_effect"],
            "risk": "high", "runtime_claim": True,
            "side_effect_class": "quiesce_fence",
        },
        {
            **base, "task_shape": "review", "surfaces": ["runtime_effect"],
            "risk": "high", "runtime_claim": True,
            "side_effect_class": "s2_4_capability_probe_intent",
        },
        {
            **base, "task_shape": "review",
            "surfaces": ["pg", "runtime_effect", "secret", "service"],
            "risk": "critical", "runtime_claim": True,
            "side_effect_class": "s2_4_install_plan",
        },
        {
            **base, "task_shape": "review", "surfaces": ["runtime_effect"],
            "risk": "high", "runtime_claim": True,
            "side_effect_class": "s2_5_start_intent",
        },
        {
            **base, "task_shape": "review", "surfaces": ["pg"],
            "risk": "high", "runtime_claim": True,
            "side_effect_class": "s2_2b_ingestion_check_intent",
        },
    ])
    for phase in sorted(P0B_CLAIM_KEYS_BY_PHASE):
        claims = {key: digest for key in P0B_CLAIM_KEYS_BY_PHASE[phase]}
        claims["p0b_effect_adapter_selection"] = p0b_effect_selection_digest(phase)
        facts_corpus.append({
            **base, "task_shape": "deploy",
            "surfaces": ["authority", "deploy", "runtime_effect", "service"],
            "risk": "high", "runtime_claim": True, "claim_inputs": claims,
        })
    for step, claim_keys in sorted(S2_CLAIM_KEYS_BY_STEP.items()):
        effect = S2_EFFECT_STEPS[step]["side_effect_class"]
        if effect == "s2_4_install_plan":
            surfaces = ["authority", "pg", "runtime_effect", "secret", "service"]
            risk = "critical"
        elif effect in {"pg_observer_bootstrap", "s2_2b_ingestion_check_intent"}:
            surfaces = ["authority", "pg", "runtime_effect"]
            risk = "high"
        else:
            surfaces = ["authority", "runtime_effect"]
            risk = "high"
        claims = {key: digest for key in claim_keys}
        claims["s2_effect_adapter_selection"] = s2_effect_selection_digest(step)
        facts_corpus.append({
            **base, "task_shape": "review", "surfaces": surfaces,
            "risk": risk, "runtime_claim": True,
            "side_effect_class": effect, "claim_inputs": claims,
        })
    contracts = []
    expected = []
    for facts in facts_corpus:
        routed = route_task(facts)
        contracts.append(task_contract_projection(routed["task_facts"]))
        expected.append([
            execution_node_core(node) for node in routed["required_role_nodes"]
        ])
    hidden_extension_only_frontend = deepcopy(contracts[2])
    hidden_extension_only_frontend["dirty_scope"] = [".tsx", "api/server.py"]
    noncanonical_focus = deepcopy(contracts[5])
    noncanonical_focus["focus"] = " bounded "
    script = "\n".join((
        "const canonicalJson = value => JSON.stringify(value);",
        render_context_admission_block(),
        f"const contracts = {json.dumps(contracts, ensure_ascii=False)};",
        f"const hidden = {json.dumps(hidden_extension_only_frontend, ensure_ascii=False)};",
        f"const focus = {json.dumps(noncanonical_focus, ensure_ascii=False)};",
        "console.log(JSON.stringify({projected: contracts.map(contract => canonicalRouteCallNodesV1(null, contract)), hidden: canonicalRouteCallNodesV1(null, hidden), focus: canonicalRouteCallNodesV1(null, focus)}));",
    ))
    script_path = tmp_path / "generic-route-parity.js"
    script_path.write_text(script, encoding="utf-8")
    completed = subprocess.run(
        ["node", str(script_path)], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["projected"] == expected
    assert result["hidden"] is None
    assert result["focus"] is None


def test_codegen_checker_detects_embedded_and_registry_projection_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = tmp_path / "workflow.js"
    original = WORKFLOWS[0].read_text(encoding="utf-8")
    workflow.write_text(original, encoding="utf-8")
    monkeypatch.setattr(codegen, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(codegen, "WORKFLOWS", (workflow,))

    embedded_mutation = original.replace(
        '"execution_surface_profile_v1"',
        '"execution_surface_profile_v1_mutated"',
        1,
    )
    assert embedded_mutation != original
    assert _async_function_syntax(embedded_mutation).returncode == 0
    workflow.write_text(embedded_mutation, encoding="utf-8")
    assert workflow_context_codegen_errors() == [
        "workflow.js shared Context block drift"
    ]

    workflow.write_text(original, encoding="utf-8")
    registry = deepcopy(load_registry())
    registry["budget_envelopes"]["full_audit"]["max_concurrent_calls"] += 1
    assert workflow_context_codegen_errors(registry) == [
        "workflow.js shared Context block drift"
    ]

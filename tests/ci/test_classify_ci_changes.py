from __future__ import annotations

import subprocess
import sys

from helper_scripts.ci.classify_ci_changes import GATES, classify_paths


def test_alr_strict_default_checkpoint_keeps_expensive_gates_off() -> None:
    result = classify_paths(
        [
            "helper_scripts/research/cost_gate_learning_lane/outcome_review.py",
            "helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py",
            "helper_scripts/research/tests/test_candidate_board_v2_lineage.py",
            "helper_scripts/research/tests/test_cost_gate_evidence_methodology.py",
            "helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py",
            "helper_scripts/research/tests/"
            "test_cost_gate_sealed_horizon_learning_evidence.py",
        ]
    )
    assert result == {gate: False for gate in GATES}


def test_ci_control_plane_change_forces_every_gate() -> None:
    for path in (
        ".github/workflows/ci.yml",
        "helper_scripts/ci/classify_ci_changes.py",
    ):
        assert all(classify_paths([path]).values())


def test_categories_are_narrow_but_cover_their_own_contracts() -> None:
    result = classify_paths(
        [
            ".codex/SUBAGENT_EXECUTION_RULES.md",
            "helper_scripts/maintenance_scripts/git_loop_guard.py",
            "rust/openclaw_alr_fit_verifier/src/main.rs",
            "sql/migrations/V160__alr_atomic_fit_consumption.sql",
            "program_code/exchange_connectors/bybit_connector/"
            "control_api_v1/tests/test_stock_etf_route_static_guard.py",
        ]
    )
    assert result == {
        "governance": True,
        "alr_fit_verifier": True,
        "rust": True,
        "schema": True,
        "stock_etf": True,
    }


def test_stock_etf_gate_covers_ibkr_and_rust_lane_sources() -> None:
    # 純 structure-test 前綴：只點亮 stock_etf gate（不誤點 rust/governance/schema），
    # 讓純 rust/純 structure-test 的 PR 也能觸發 hosted CI 的 stock_etf 靜態守衛 job。
    for path in (
        "tests/structure/test_stock_etf_ipc_handler_split_static.py",
        "tests/structure/test_ibkr_tws_session_state_source_static.py",
    ):
        result = classify_paths([path])
        assert result["stock_etf"] is True, path
        assert all(
            enabled is False for gate, enabled in result.items() if gate != "stock_etf"
        ), path

    # rust lane 來源前綴：點亮 stock_etf（同時本就會點亮 rust / schema）。
    for path in (
        "rust/openclaw_engine/src/ipc_server/handlers/stock_etf_risk_policy.rs",
        "rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs",
        "rust/openclaw_engine/src/ipc_server/tests/stock_etf/"
        "foundation_status_fixtures.rs",
        "rust/openclaw_types/src/ibkr_tws_session_state.rs",
        "rust/openclaw_types/src/stock_etf_paper_order_request/fixtures.rs",
    ):
        assert classify_paths([path])["stock_etf"] is True, path


def test_stock_etf_gate_covers_ibkr_ci_audit_scripts() -> None:
    # W5-S0(R8 審計洞①):三個 nm 審計腳本自身被改的 PR 必須觸發 rust-ibkr-tests
    # (只點亮 stock_etf,不誤點其他 gate)——否則掏空審計可靜默 merge。
    for path in (
        "helper_scripts/ci/ibkr_g4_symbol_audit.sh",
        "helper_scripts/ci/ibkr_fake_tws_absence_audit.sh",
        "helper_scripts/ci/ibkr_driver_absence_audit.sh",
    ):
        result = classify_paths([path])
        assert result["stock_etf"] is True, path
        assert all(
            enabled is False for gate, enabled in result.items() if gate != "stock_etf"
        ), path


def test_governance_gate_covers_direct_policy_and_adapter_inputs() -> None:
    for path in (
        "helper_scripts/maintenance_scripts/deploy_intent_adapter.py",
        "docs/adr/0050-development-agent-governance.md",
        ".agents/skills/16-root-principles-checklist/SKILL.md",
        "CONTEXT.md",
        "docs/governance_dev/SPECIFICATION_REGISTER.md",
        "docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/"
        "2026-07-09--scanner_driven_alr/startup_prompt.md",
    ):
        result = classify_paths([path])
        assert result["governance"] is True
        assert all(
            enabled is False
            for gate, enabled in result.items()
            if gate != "governance"
        )


def test_cli_writes_nul_safe_github_outputs(tmp_path) -> None:
    output = tmp_path / "github-output"
    completed = subprocess.run(
        [
            sys.executable,
            "helper_scripts/ci/classify_ci_changes.py",
            "--null",
            "--github-output",
            str(output),
        ],
        input=b"rust/openclaw_engine/src/main.rs\0",
        check=False,
    )
    assert completed.returncode == 0
    assert output.read_text(encoding="utf-8").splitlines() == [
        "governance=false",
        "alr_fit_verifier=false",
        "rust=true",
        "schema=true",
        "stock_etf=false",
    ]

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from helper_scripts.ci.classify_ci_changes import GATES, classify_paths  # noqa: E402


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


def test_governance_shard_selector_and_contract_test_trigger_governance() -> None:
    for path in (
        "helper_scripts/ci/select_pytest_shard.py",
        "helper_scripts/ci/verify_pytest_shards.py",
        "tests/ci/test_select_pytest_shard.py",
        "tests/ci/test_verify_pytest_shards.py",
    ):
        result = classify_paths([path])
        assert result["governance"] is True, path
        assert all(
            enabled is False for gate, enabled in result.items()
            if gate != "governance"), path


def test_categories_are_narrow_but_cover_their_own_contracts() -> None:
    result = classify_paths(
        [
            ".codex/SUBAGENT_EXECUTION_RULES.md",
            "helper_scripts/maintenance_scripts/git_loop_guard.py",
            "rust/openclaw_alr_fit_verifier/src/main.rs",
            "sql/migrations/V160__alr_atomic_fit_consumption.sql",
            "program_code/exchange_connectors/bybit_connector/"
            "control_api_v1/tests/test_stock_etf_route_static_guard.py",
            "requirements-ml.lock",
            "helper_scripts/replay/replay_local.py",
        ]
    )
    assert result == {
        "governance": True,
        "alr_fit_verifier": True,
        "rust": True,
        "schema": True,
        "stock_etf": True,
        "sealed_build": True,
        "replay": True,
    }


def test_sealed_build_gate_covers_its_own_contract_surface() -> None:
    # AIML LR2 / S2.3：鎖、spec、verifier 模組與兩張 receipt schema 都應觸發 sealed_build
    # 昂貴安裝 job；且不誤點其他昂貴 gate（governance 由 maintenance_scripts / test_agent_governance_
    # 前綴另行觸發,屬預期,見下方 verifier-module case）。
    lock_only_paths = (
        "requirements-ml.lock",
        "requirements-ml.txt",
        "program_code/ml_training/schemas/aiml_gate_receipts/sealed_build_receipt_v1.schema.json",
        "program_code/ml_training/schemas/aiml_gate_receipts/expected_identity_receipt_v1.schema.json",
        "program_code/ml_training/schemas/aiml_gate_receipts/learning_runtime_choice_receipt_v1.schema.json",
        "tests/fixtures/sealed_build/hermetic_closure.lock",
        "docs/execution_plan/ai_ml_landing/receipts/S2.3-sealed-build-receipt-v1.json",
        "docs/execution_plan/ai_ml_landing/receipts/S2.3-expected-identity-receipt-v1.json",
    )
    for path in lock_only_paths:
        result = classify_paths([path])
        assert result["sealed_build"] is True, path
        assert all(
            enabled is False for gate, enabled in result.items() if gate != "sealed_build"
        ), path

    # verifier 模組與其結構/離線測試同時觸發 sealed_build 與 governance（兩者皆須跑）。
    for path in (
        "helper_scripts/maintenance_scripts/agent_governance_sealed_build.py",
        "tests/structure/test_agent_governance_sealed_build.py",
        "tests/structure/test_agent_governance_sealed_build_offline.py",
    ):
        result = classify_paths([path])
        assert result["sealed_build"] is True, path
        assert result["governance"] is True, path
        assert result["alr_fit_verifier"] is False, path
        assert result["rust"] is False, path
        assert result["schema"] is False, path
        assert result["stock_etf"] is False, path


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
        assert all(enabled is False for gate, enabled in result.items()
                   if gate != "governance")


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
        "sealed_build=false",
        "replay=false",
    ]


def test_replay_gate_covers_sources_tools_and_future_test_files() -> None:
    control = "program_code/exchange_connectors/bybit_connector/control_api_v1/"
    for path in (
        "rust/openclaw_engine/src/replay/stage1.rs",
        "rust/openclaw_engine/src/bin/replay_runner.rs",
        "rust/openclaw_engine/src/bin/replay_runner/nested.rs",
        "rust/openclaw_engine/tests/replay_future_acceptance.rs",
        "rust/openclaw_engine/tests/m3_emitter_replay_forbidden.rs",
        "helper_scripts/replay/replay_local.py",
        control + "replay/offline_analytics.py",
        control + "replay/offline_manifest.py",
        control + "tests/replay/test_stage1_future.py",
        # 階段 1 工具與測試直接載入的模組、共用 conftest 與 Demo 設定檔
        control + "replay/__init__.py",
        control + "replay/experiment_registry.py",
        control + "replay/full_chain_fixture.py",
        control + "replay/manifest_signer.py",
        control + "replay/report_analytics.py",
        control + "replay/route_helpers.py",
        control + "tests/conftest.py",
        # 目前不存在；一旦新增，pytest 會對這組測試自動載入
        control + "tests/replay/conftest.py",
        # 共用 conftest 在匯入期就載入的模組
        control + "app/__init__.py",
        control + "app/db_pool.py",
        control + "app/error_sanitize.py",
        "pytest.ini",
        "settings/strategy_params_demo.toml",
        "settings/risk_control_rules/risk_config_demo.toml",
        "settings/risk_control_rules/scanner_config.toml",
        "rust/Cargo.toml",
        "rust/Cargo.lock",
        "rust/openclaw_engine/Cargo.toml",
    ):
        assert classify_paths([path])["replay"] is True, path


def test_replay_gate_does_not_select_unrelated_paths() -> None:
    control = "program_code/exchange_connectors/bybit_connector/control_api_v1/"
    for path in (
        "docs/replay.md",
        "rust/openclaw_engine/src/main.rs",
        "rust/openclaw_engine/src/bin/replay_runner_extra.rs",
        "rust/openclaw_engine/tests/other_replay.rs",
        "helper_scripts/ci/replay_runner_symbol_audit.sh",
        control + "replay/live.py",
        control + "replay/run_route.py",
        control + "tests/replay/test_other.py",
        control + "app/main.py",
        "settings/strategy_params_live.toml",
        "settings/risk_control_rules/risk_config_live.toml",
    ):
        assert classify_paths([path])["replay"] is False, path


def test_replay_gate_tracks_same_package_imports_of_the_offline_tools() -> None:
    # 防止清單漂移：離線工具新增同套件相依卻沒有列進關卡時，這條測試會失敗。
    import ast

    control = "program_code/exchange_connectors/bybit_connector/control_api_v1/"
    checked = 0
    for name in ("offline_analytics.py", "offline_manifest.py"):
        source = (REPO_ROOT / control / "replay" / name).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.ImportFrom) or node.level != 1:
                continue
            modules = [node.module] if node.module else [alias.name for alias in node.names]
            for module in modules:
                path = control + "replay/" + module.split(".")[0] + ".py"
                assert classify_paths([path])["replay"] is True, path
                checked += 1
    assert checked >= 5


def test_replay_gate_preserves_other_gate_decisions() -> None:
    assert classify_paths(["helper_scripts/replay/replay_local.py"]) == {
        gate: gate == "replay" for gate in GATES
    }
    assert all(classify_paths([], force_all=True).values())

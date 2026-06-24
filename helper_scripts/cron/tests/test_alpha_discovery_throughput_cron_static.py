"""Static contract tests for alpha_discovery_throughput_cron.sh."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CRON_DIR = Path(__file__).resolve().parents[1]
WRAPPER = CRON_DIR / "alpha_discovery_throughput_cron.sh"


def _src() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def _module_command_block(src: str, module: str) -> str:
    start = src.index(f'"$PYBIN" -m {module}')
    end = src.index(") >", start)
    return src[start:end]


def _module_redirection(src: str, module: str) -> str:
    start = src.index(f'"$PYBIN" -m {module}')
    redirect_start = src.index(") >", start)
    redirect_end = src.index("\n", redirect_start)
    return src[redirect_start:redirect_end]


def test_bash_syntax_ok() -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(["bash", "-n", str(WRAPPER)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_wrapper_refreshes_activation_packet_before_alpha_runner() -> None:
    src = _src()
    assert "set -euo pipefail" in src
    assert "demo_learning_stack_activation_packet.py" in src
    assert "demo_learning_stack_activation_packet_latest.json" in src
    assert "demo_learning_stack_activation_packet_stdout.json" in src
    assert "demo_learning_stack_dry_run_review.py" in src
    assert "demo_learning_stack_dry_run_review_latest.json" in src
    assert "demo_learning_stack_dry_run_review_stdout.json" in src
    assert "cost_gate_learning_lane.sealed_horizon_operator_review" in src
    assert "sealed_horizon_operator_review_latest.json" in src
    assert "sealed_horizon_operator_review_latest.md" in src
    assert "sealed_horizon_operator_review_stdout.json" in src
    assert "sealed_horizon_probe_preflight_cron.sh" in src
    assert "sealed_horizon_probe_preflight_refresh rc=" in src
    assert "false_negative_bounded_probe_preflight_latest.json" in src
    assert "OPENCLAW_ALPHA_BOUNDED_PROBE_PREFLIGHT_JSON" in src
    assert "BOUNDED_PROBE_PREFLIGHT_JSON" in src
    assert "OPENCLAW_ALPHA_REFRESH_BOUNDED_PROBE_REVIEW_CHAIN" in src
    assert "OPENCLAW_ALPHA_ORDER_TO_FILL_GAP_AUDIT_JSON" in src
    assert "demo_order_to_fill_gap_latest.json" in src
    assert "cost_gate_learning_lane.bounded_probe_touchability_preflight" in src
    assert "cost_gate_learning_lane.bounded_probe_placement_repair_plan" in src
    assert "cost_gate_learning_lane.bounded_probe_authority_patch_readiness" in src
    assert "cost_gate_learning_lane.bounded_probe_operator_authorization_cli" in src
    assert "cost_gate_learning_lane.bounded_probe_shadow_placement_impact" in src
    assert "alpha_discovery_throughput.mm_current_fee_confirmation" in src
    assert "mm_current_fee_confirmation_latest.json" in src
    assert "mm_current_fee_confirmation_latest.md" in src
    assert "mm_current_fee_confirmation_stdout.json" in src
    assert "mm_current_fee_confirmation_refresh rc=" in src
    assert "alpha_discovery_throughput.mm_motif_amplification" in src
    assert "mm_motif_amplification_latest.json" in src
    assert "mm_motif_amplification_latest.md" in src
    assert "mm_motif_amplification_stdout.json" in src
    assert "mm_motif_amplification_refresh rc=" in src
    assert "bounded_probe_touchability_preflight_latest.json" in src
    assert "bounded_probe_placement_repair_plan_latest.json" in src
    assert "bounded_probe_authority_patch_readiness_latest.json" in src
    assert "bounded_probe_operator_authorization_latest.json" in src
    assert "bounded_probe_shadow_placement_impact_latest.json" in src
    assert "bounded_probe_touchability_preflight_refresh rc=" in src
    assert "bounded_probe_placement_repair_plan_refresh rc=" in src
    assert "bounded_probe_authority_patch_readiness_refresh rc=" in src
    assert "bounded_probe_operator_authorization_refresh rc=" in src
    assert "bounded_probe_shadow_placement_impact_refresh rc=" in src
    assert "--order-to-fill-gap-json" in src
    assert '--preflight-json "$BOUNDED_PROBE_PREFLIGHT_JSON"' in src
    assert "--placement-repair-plan-json" in src
    assert "--authority-patch-readiness-json" in src
    assert "canonical_or_latest_matching_path()" in src
    assert '"$DATA"/cost_gate_learning_lane/sealed_horizon_learning_evidence_latest.json' in src
    assert '"$DATA"/cost_gate_learning_lane/horizon_specific_sealed_replay_latest.json' in src
    assert "--sealed-horizon-learning-evidence-json" in src
    assert "--sealed-horizon-operator-review-json" in src
    assert "OPENCLAW_SEALED_HORIZON_LEARNING_EVIDENCE_JSON" in src
    assert "OPENCLAW_SEALED_HORIZON_OPERATOR_REVIEW_JSON" in src
    assert "OPENCLAW_SEALED_HORIZON_DECISION_PACKET_JSON" in src
    assert "--decision defer" in src
    assert "alpha_discovery_throughput.profitability_path_scorecard" in src
    assert "profitability_path_scorecard_latest.json" in src
    assert "profitability_path_scorecard_latest.md" in src
    assert "--cost-gate-counterfactual-json" in src
    assert "--profit-learning-packet-json" in src
    assert "--demo-learning-stack-activation-packet-json" in src
    assert "--demo-learning-stack-dry-run-review-json" in src
    assert "--sealed-horizon-probe-preflight-json" in src
    assert "--bounded-probe-preflight-json" in src
    assert "--bounded-probe-operator-authorization-json" in src
    assert "--bounded-probe-result-review-json" in src
    assert "--bounded-probe-execution-realism-review-json" in src
    assert "--json-output" in src
    assert "activation_packet_refresh rc=" in src
    assert "dry_run_review_refresh rc=" in src
    assert "sealed_horizon_operator_review_refresh rc=" in src
    assert "profitability_path_scorecard_refresh rc=" in src
    assert "alpha_discovery_throughput.runtime_runner" in src
    assert src.index("demo_learning_stack_activation_packet.py") < src.index(
        "demo_learning_stack_dry_run_review.py"
    )
    assert src.index("demo_learning_stack_dry_run_review.py") < src.index(
        "cost_gate_learning_lane.sealed_horizon_operator_review"
    )
    assert src.index("sealed_horizon_operator_review_refresh rc=") < src.index(
        "sealed_horizon_probe_preflight_refresh rc="
    )
    assert src.index("sealed_horizon_probe_preflight_refresh rc=") < src.index(
        "cost_gate_learning_lane.bounded_probe_touchability_preflight"
    )
    assert src.index("FALSE_NEGATIVE_BOUNDED_PREFLIGHT_JSON") < src.index(
        "cost_gate_learning_lane.bounded_probe_touchability_preflight"
    )
    assert src.index("cost_gate_learning_lane.bounded_probe_touchability_preflight") < src.index(
        "cost_gate_learning_lane.bounded_probe_placement_repair_plan"
    )
    assert src.index("cost_gate_learning_lane.bounded_probe_placement_repair_plan") < src.index(
        "cost_gate_learning_lane.bounded_probe_authority_patch_readiness"
    )
    assert src.index("cost_gate_learning_lane.bounded_probe_authority_patch_readiness") < src.index(
        "cost_gate_learning_lane.bounded_probe_operator_authorization_cli"
    )
    assert src.index("cost_gate_learning_lane.bounded_probe_operator_authorization_cli") < src.index(
        "cost_gate_learning_lane.bounded_probe_shadow_placement_impact"
    )
    assert src.index("bounded_probe_shadow_placement_impact_refresh rc=") < src.index(
        "alpha_discovery_throughput.mm_current_fee_confirmation"
    )
    assert src.index("alpha_discovery_throughput.mm_current_fee_confirmation") < src.index(
        "alpha_discovery_throughput.mm_motif_amplification"
    )
    assert src.index("alpha_discovery_throughput.mm_motif_amplification") < src.index(
        "alpha_discovery_throughput.profitability_path_scorecard"
    )
    assert src.index("alpha_discovery_throughput.profitability_path_scorecard") < src.index(
        "alpha_discovery_throughput.runtime_runner"
    )


def test_bounded_shadow_placement_consumes_same_cycle_authority_readiness() -> None:
    src = _src()
    block = _module_command_block(
        src, "cost_gate_learning_lane.bounded_probe_shadow_placement_impact"
    )
    assert '--placement-repair-plan-json "$BOUNDED_PROBE_PLACEMENT_REPAIR_PLAN_OUT"' in block
    assert (
        '--authority-patch-readiness-json "$BOUNDED_PROBE_AUTHORITY_PATCH_READINESS_OUT"'
        in block
    )
    assert block.index("--placement-repair-plan-json") < block.index(
        "--authority-patch-readiness-json"
    )
    assert block.index("--authority-patch-readiness-json") < block.index(
        "--max-artifact-age-hours"
    )


def test_mm_motif_amplification_refresh_uses_canonical_history_artifact() -> None:
    src = _src()
    block = _module_command_block(src, "alpha_discovery_throughput.mm_motif_amplification")
    redirection = _module_redirection(
        src, "alpha_discovery_throughput.mm_motif_amplification"
    )
    assert (
        '--fillsim-history-json "$DATA/research/fillsim/fillsim_history_scorecard.json"'
        in block
    )
    assert '--json-output "$MM_MOTIF_AMPLIFICATION_JSON"' in block
    assert '--output "$MM_MOTIF_AMPLIFICATION_MD"' in block
    assert redirection == (
        ') > "$MM_MOTIF_AMPLIFICATION_STDOUT" 2>> "$LOG" || '
        "mm_motif_amplification_rc=$?"
    )
    assert (
        'echo "[$(ts)] mm_motif_amplification_refresh rc=${mm_motif_amplification_rc}"'
        in src
    )


def test_runtime_runner_receives_expected_head_from_cron_contract() -> None:
    src = _src()
    runtime_start = src.index('"$PYBIN" -m alpha_discovery_throughput.runtime_runner')
    expected_head_start = src.index("EXPECTED_SOURCE_HEAD=")
    assert expected_head_start < runtime_start
    assert (
        'EXPECTED_SOURCE_HEAD="${OPENCLAW_EXPECTED_SOURCE_HEAD:-'
        "${OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD:-"
        '${OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD:-}}}"'
        in src
    )
    assert '--expected-head "$EXPECTED_SOURCE_HEAD"' in src
    assert src.index('--expected-head "$EXPECTED_SOURCE_HEAD"') > runtime_start


def test_runtime_runner_expected_head_wrapper_executes_with_empty_and_demo_env(
    tmp_path: Path,
) -> None:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    base = tmp_path / "srv"
    data = tmp_path / "data"
    (base / "helper_scripts" / "research" / "alpha_discovery_throughput").mkdir(
        parents=True
    )
    fake_python = tmp_path / "fake_python.sh"
    args_log = tmp_path / "fake_python_args.log"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_PY_ARGS_LOG\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    def run_wrapper(expected_head: str | None) -> list[str]:
        args_log.unlink(missing_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "OPENCLAW_BASE_DIR": str(base),
                "OPENCLAW_DATA_DIR": str(data),
                "OPENCLAW_PYTHON_BIN": str(fake_python),
                "FAKE_PY_ARGS_LOG": str(args_log),
                "OPENCLAW_ALPHA_REFRESH_BOUNDED_PROBE_REVIEW_CHAIN": "0",
            }
        )
        for name in (
            "OPENCLAW_EXPECTED_SOURCE_HEAD",
            "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD",
            "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD",
        ):
            env.pop(name, None)
        if expected_head is not None:
            env["OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD"] = expected_head
        proc = subprocess.run(
            ["bash", str(WRAPPER)],
            env=env,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        return args_log.read_text(encoding="utf-8").splitlines()

    no_expected_lines = run_wrapper(None)
    no_expected_runtime = [
        line for line in no_expected_lines if "alpha_discovery_throughput.runtime_runner" in line
    ]
    assert no_expected_runtime
    assert all("--expected-head" not in line for line in no_expected_runtime)

    demo_expected_lines = run_wrapper("demo-head")
    demo_expected_runtime = [
        line for line in demo_expected_lines if "alpha_discovery_throughput.runtime_runner" in line
    ]
    assert demo_expected_runtime
    assert any("--expected-head demo-head" in line for line in demo_expected_runtime)


def test_wrapper_keeps_refresh_artifact_only() -> None:
    src = _src()
    assert "OPENCLAW_DATA_DIR" in src
    assert "OPENCLAW_BASE_DIR" in src
    assert "crontab -" not in src
    assert "git pull" not in src
    assert "git reset" not in src
    assert "restart_all.sh" not in src
    assert "systemctl" not in src
    assert "OPENCLAW_ALLOW_MAINNET" not in src
    assert "authorization.json" not in src
    assert "place_order" not in src
    assert "cancel_order" not in src

"""PM O-5 封閉裁定的機械投影(2026-07-28):phase→class 映射任何一側漂移即紅。

裁定原文:S2.5A＋S2.5B 是**單一 ``WATCHDOG_ROLLBACK_TEST`` effect lineage 的兩個 phase
step**(鏡 S2.4 aggregate 形制);classifier v3 新增兩 class(``ENGINE_SCANNER_SERVICE_START``
＝S2.5A component-level、``WATCHDOG_ROLLBACK_TEST``＝S2.5B 兼 lineage 名);PROGRESS S2.5
session row 的 Required effect 欄**不改名**。本檔把三側(leaf 常量、intent schema 的 allOf
綁定、PROGRESS ledger row)釘成等值。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_s2_5 as leaf  # noqa: E402

_SCHEMA_DIR = ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"


def test_phase_to_class_mapping_is_the_exact_pm_o5_ruling():
    assert leaf.S2_5_PHASE_EFFECT_CLASS == {
        "S2_5A_START": "ENGINE_SCANNER_SERVICE_START",
        "S2_5B_FINAL": "WATCHDOG_ROLLBACK_TEST",
    }
    assert leaf.S2_5_EFFECT_LINEAGE == "WATCHDOG_ROLLBACK_TEST"
    # lineage 名就是 S2.5B 的 class 名(一行 ledger、兩個 phase step)。
    assert leaf.S2_5_PHASE_EFFECT_CLASS["S2_5B_FINAL"] == leaf.S2_5_EFFECT_LINEAGE
    # v3 矩陣恰兩行,行名 = 兩個 class。
    assert sorted(leaf.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3) == sorted(
        leaf.S2_5_PHASE_EFFECT_CLASS.values()
    )


def test_intent_schema_binds_each_phase_to_its_exact_class():
    schema = json.loads(
        (_SCHEMA_DIR / "s2_5_start_intent_v1.schema.json").read_text(encoding="utf-8")
    )
    bindings: dict[str, str] = {}
    for clause in schema["allOf"]:
        phase = clause["if"]["properties"]["core"]["properties"]["phase"]["const"]
        effect_class = clause["then"]["properties"]["route_surface"]["properties"][
            "required_effect_class"
        ]["const"]
        bindings[phase] = effect_class
    assert bindings == leaf.S2_5_PHASE_EFFECT_CLASS
    # route_surface 的 lineage const 也必須是裁定的 lineage 名。
    assert schema["properties"]["route_surface"]["properties"]["effect_lineage"][
        "const"
    ] == leaf.S2_5_EFFECT_LINEAGE


def test_progress_s2_5_row_required_effect_column_is_not_renamed():
    progress = (
        ROOT / "docs/execution_plan/ai_ml_landing/PROGRESS.md"
    ).read_text(encoding="utf-8")
    # 以「S2.5 row 帶 WATCHDOG_ROLLBACK_TEST」的存在性釘住(欄位不改名)。
    assert any(
        "S2.5" in line and "WATCHDOG_ROLLBACK_TEST" in line
        for line in progress.splitlines()
    ), "PROGRESS S2.5 session row no longer names WATCHDOG_ROLLBACK_TEST (PM O-5 forbids the rename)"
    # 且 PROGRESS 不得把 S2.5 row 的 Required effect 改成 component-level class 名。
    for line in progress.splitlines():
        if "| S2.5 " in line and "Required" not in line:
            assert "ENGINE_SCANNER_SERVICE_START" not in line, (
                "the PROGRESS S2.5 row must keep WATCHDOG_ROLLBACK_TEST as its Required "
                "effect name (ENGINE_SCANNER_SERVICE_START is the v3 component-level "
                "class, not the ledger name)"
            )


def test_v3_matrix_rows_carry_the_exact_o5_table():
    matrix = leaf.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V3
    start = matrix["ENGINE_SCANNER_SERVICE_START"]
    assert start["adapter_id"] == "s2_5_runtime_start_adapter_v1"
    assert start["actor_node_id"] == "s2_5_host_service_actor"
    assert start["independent_postcheck_node_id"] == "s2_5_running_postcheck_v1"
    assert start["recovery_contract"] == (
        "s2_5_rollback_drill_receipt_v1(kind=ROLLBACK_TO_DISABLED)"
    )
    final = matrix["WATCHDOG_ROLLBACK_TEST"]
    assert final["adapter_id"] == "s2_5_final_attestation_adapter_v1"
    assert final["actor_node_id"] == "s2_5_host_service_actor"
    assert final["independent_postcheck_node_id"] == "s2_5_final_postcheck_v1"
    assert final["recovery_contract"] == (
        "s2_5_rollback_drill_receipt_v1(kind=WATCHDOG_RESET_LAST)"
    )

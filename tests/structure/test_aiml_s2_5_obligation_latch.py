"""§9.3 雙向 latch:`S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST` 帳本 ↔ fixtures 事實面(PM O-1)。

W5 兩次「honesty latch 被句法代理騙過」的教訓:latch 讀 **subject 本體**——fixtures 檔的
AST 函式定義、design 目錄的 glob、活 ABI row 的 typed_status——不讀註釋/命名/文案。

方向 1:fixtures 檔存在且非空 ⇒ 活 ABI 該行 `typed_status != OUT_OF_WP4_SCOPE`(「fixtures
在而帳本說不在」不得存活)。
方向 2:該行已標 `CLOSED_BY_S2_5_SOURCE` ⇒ fixtures 檔存在、§8.1 五個場景的測試 id 齊在、
且 design 正本在位(「帳本說關了而事實面缺席」不得存活)。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for _candidate in (HELPERS, ML_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as validator  # noqa: E402

_FIXTURES_PATH = ROOT / "tests/structure/test_agent_governance_s2_5_lifecycle_fixtures.py"
_DESIGN_DIR = ROOT / "docs/execution_plan/ai_ml_landing/design"
# §8.1 五個場景的測試 id(subject 本體;改名/刪除任一場景即紅)。
_SCENARIO_TEST_IDS = frozenset({
    "test_enable_now_happy_path_full_chain_source_simulation_pass",
    "test_enabled_and_reboot_persistence_source_half",
    "test_each_running_dimension_failure_fails_the_whole_attestation",
    "test_rollback_to_disabled_restores_the_exact_s2_4_prestate",
    "test_watchdog_reset_last_supervening_restart_blocks_reset_clean",
})


def _ledger_row() -> dict:
    return next(
        row
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
        if row["obligation_id"] == "S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST"
    )


def _fixture_function_names() -> set[str]:
    tree = ast.parse(_FIXTURES_PATH.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_latch_direction_1_fixtures_present_forbid_out_of_wp4_scope():
    if not (_FIXTURES_PATH.is_file() and _FIXTURES_PATH.read_text(encoding="utf-8").strip()):
        return  # 方向 1 的前件不成立(fixtures 缺席由方向 2 裁)。
    assert _ledger_row()["typed_status"] != "OUT_OF_WP4_SCOPE", (
        "the S2.5 lifecycle fixtures exist but the live ABI still records the obligation "
        "as OUT_OF_WP4_SCOPE; the ledger is carrying a statement that has stopped being true"
    )


def test_latch_direction_2_closed_status_requires_the_facts():
    row = _ledger_row()
    if row["typed_status"] != "CLOSED_BY_S2_5_SOURCE":
        return  # 方向 2 的前件不成立(未標 CLOSED 由方向 1/wave_w5 臂裁)。
    assert _FIXTURES_PATH.is_file() and _FIXTURES_PATH.read_text(encoding="utf-8").strip(), (
        "the ledger claims CLOSED_BY_S2_5_SOURCE but the fixtures file is absent/empty"
    )
    missing = sorted(_SCENARIO_TEST_IDS - _fixture_function_names())
    assert not missing, {
        "closed_status": row["typed_status"],
        "missing_scenario_test_ids": missing,
        "hint": "§8.1 的五個場景 id 是關閉事實面的 subject;改名請同步本 latch 與 PM 溝通",
    }
    assert sorted(path.name for path in _DESIGN_DIR.glob("S2.5-*.md")), (
        "the ledger claims CLOSED_BY_S2_5_SOURCE but no S2.5 design document exists"
    )


def test_latch_is_two_sided_not_vacuous():
    """空對照:兩個方向的前件至少一個成立(row 一定在、fixtures 檔一定可判)。"""

    row = _ledger_row()
    assert row["typed_status"] in {"OUT_OF_WP4_SCOPE", "CLOSED_BY_S2_5_SOURCE"}, (
        "the obligation row carries an unrecognized typed_status; both latch arms would "
        "be vacuously green (fail-closed)"
    )

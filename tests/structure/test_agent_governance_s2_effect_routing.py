"""S2E.1:六段 S2 effect DAG 的 claim-gated governance routing 測試。

鏡 ``test_agent_governance_p0b_effect_adapter.py`` 的兩段式 claim-selector 先例:

* selector 缺席 → 現行 source route(零 effect 節點注入;registry invariant 行為),
  既有 per-step routing 測試檔保持原樣作 source-lane 回歸錨;
* selector 在場 → exact-match 恰一 step + exact claim-key set + side_effect_class 互鎖,
  任何不符 typed ValueError,絕不靜默回落 source route;
* S2.2B 為 identity-only 註冊(registry 條目 + route class),可執行 runtime
  observer/attestor 屬 S2E.4。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))


S2_2B_ADAPTER_ID = "s2_2b_ingestion_compatibility_adapter_v1"


def test_registry_carries_identity_only_s2_2b_adapter_fail_closed() -> None:
    registry = json.loads(
        (ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8")
    )
    entry = registry["effect_adapters"][S2_2B_ADAPTER_ID]
    assert entry["status"] == (
        "declared_runtime_done_fail_closed_until_s2e4_observer_attestor"
    )
    assert entry["owner_session"] == "S2.2B"
    invariant = entry["invariant"]
    # 五個 invariant 子句(設計 §C):fail-closed / 九 authority false / EFFECT session 前
    # 不注入 / S2.5B 唯一合法上游 / runtime-attestor 執行與驗證屬 S2E.4。
    for clause in (
        "fail-closed EXTERNAL_VERIFICATION_PENDING",
        "nine authorities stay false",
        "no route_task effect node or closure effect binding is injected "
        "before the S2.2B EFFECT session",
        "only s2_5_final_attestation_v1 is the legal upstream of the S2.2B runtime-DONE",
        "execution/verification is S2E.4",
    ):
        assert clause in invariant, clause
    assert entry["implementation_paths"] == [
        "helper_scripts/maintenance_scripts/agent_governance_s2_2b.py"
    ]
    assert entry["component_paths"] == [
        "program_code/ml_training/aiml_gate_receipt_s2_2b.py"
    ]
    assert entry["receipt_schema_path"] == (
        "program_code/ml_training/schemas/aiml_gate_receipts/"
        "ingestion_compatibility_receipt_v1.schema.json"
    )
    for path in (
        *entry["implementation_paths"],
        *entry["component_paths"],
        entry["receipt_schema_path"],
    ):
        assert (ROOT / path).is_file(), path

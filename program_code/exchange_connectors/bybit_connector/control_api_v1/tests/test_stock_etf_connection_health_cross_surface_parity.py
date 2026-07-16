"""Cross-surface parity：W4 connection-health Rust emitter 契約 ⊗ Python normalizer 欄位集。

fail-closed 機制 #3（設計 §3）：emitter 契約欄位集 ⊗ normalizer 欄位集由本 parity 測試鎖死,
漂移即紅。若 Rust emitter 新增欄位而 normalizer 未 guard（或反之）,或 fixture 與 Rust 契約
脫鉤,本測試轉紅——避免自宣告 payload 繞過負空間。
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_connection_health,
)

# normalizer 的負空間 guard 欄位集（直接自被測模組匯入,避免手抄漂移）。
import sys

_control_api_app = Path(__file__).resolve().parents[1] / "app"
if str(_control_api_app.parent) not in sys.path:
    sys.path.insert(0, str(_control_api_app.parent))

from app.stock_etf_connection_health_normalizers import (  # noqa: E402
    _ENTITLEMENT_STATE_DOMAIN,
    _HALT_REASON_DOMAIN,
    _HEALTH_HARD_SAFETY_FIELDS,
    _HEALTH_PACING_ACTIVITY_FIELDS,
    _OPERATIONAL_SCALAR_FIELDS,
    _SESSION_STATE_DOMAIN,
)

SRV_ROOT = Path(__file__).resolve().parents[5]
RUST_CONTRACT = (
    SRV_ROOT / "rust/openclaw_types/src/ibkr_tws_connection_health.rs"
)
RUST_SESSION_STATE_CONTRACT = (
    SRV_ROOT / "rust/openclaw_types/src/ibkr_tws_session_state.rs"
)

# telemetry allowlist：**唯一**豁免 guard 的 operational 型欄（inactive governor 滿桶為
# 誠實基線,非 liveness 訊號——見 normalizer 模組註解）。擴充此集＝有意識的審查決策。
_TELEMETRY_ALLOWLIST = frozenset({"main_tokens_available"})

# 契約 metadata 欄（識別/版本/資訊字串,非 operational 真值）——不需負空間 guard。
# 逐欄 pin 現值型別（E3 NOTE-3）:任何型別漂移（尤其改成 bool/枚舉）即紅,防「操作真值
# 改名/改型藏進 metadata 豁免」。
_CONTRACT_METADATA_FIELD_TYPES = {
    "contract_id": "String",
    "source_version": "u32",
    "pending_reason": "String",
}
_CONTRACT_METADATA_FIELDS = frozenset(_CONTRACT_METADATA_FIELD_TYPES)


def _rust_struct_fields_with_types() -> dict[str, str]:
    """自 Rust `IbkrConnectionHealthReportV1` struct 抽出 `pub <name>: <type>` 欄名→型別。"""
    source = RUST_CONTRACT.read_text(encoding="utf-8")
    start = source.index("pub struct IbkrConnectionHealthReportV1")
    brace = source.index("{", start)
    depth = 0
    end = brace
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    body = source[brace:end]
    # 抽取面防逃逸（E2 MUT-B）：regex 只匹配 `pub <name>`,`pub(crate)`/`pub(super)`
    # 欄位會靜默逃出 superset 掃描面——契約 struct 禁受限可見度欄位,出現即紅。
    assert "pub(" not in body, (
        "IbkrConnectionHealthReportV1 不得含 pub(crate)/pub(super) 欄位"
        "（會逃出 parity 抽取面）"
    )
    return dict(
        re.findall(r"pub\s+([a-z_][a-z0-9_]*)\s*:\s*([A-Za-z0-9_:<>]+)", body)
    )


def _rust_enum_variants_snake_case(source_path: Path, enum_name: str) -> tuple[str, ...]:
    """自 Rust 契約檔抽出 `pub enum <enum_name>` 的變體名並轉 serde snake_case 投影
    （兩契約 enum 均標 `#[serde(rename_all = "snake_case")]`）。"""
    source = source_path.read_text(encoding="utf-8")
    start = source.index(f"pub enum {enum_name}")
    brace = source.index("{", start)
    depth = 0
    end = brace
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    body = source[brace:end]
    variants = re.findall(r"^\s{4}([A-Z][A-Za-z0-9]*),$", body, flags=re.MULTILINE)
    assert variants, f"enum {enum_name} 變體抽取為空（抽取面失效,fail-closed）"
    return tuple(
        re.sub(r"(?<!^)(?=[A-Z])", "_", variant).lower() for variant in variants
    )


def _rust_struct_field_names() -> set[str]:
    """自 Rust `IbkrConnectionHealthReportV1` struct 抽出 `pub <name>:` 欄名。"""
    return set(_rust_struct_fields_with_types())


def test_rust_emitter_fields_are_all_carried_by_python_fixture() -> None:
    # emitter 契約每一欄（serde flatten 入 IPC payload）都須是 fixture（emitter 鏡像）的 key。
    struct_fields = _rust_struct_field_names()
    fixture_keys = set(_valid_connection_health().keys())
    missing = struct_fields - fixture_keys
    assert missing == set(), f"fixture 缺 Rust emitter 欄位: {sorted(missing)}"


def test_normalizer_guarded_fields_are_subset_of_emitter_contract() -> None:
    # normalizer 負空間 guard 的每一欄都須存在於 emitter 契約——否則 guard 一個不存在的欄
    # ＝死 guard（假安全）。db_apply_performed 屬 emitter 附加束（非 struct 欄）。
    struct_fields = _rust_struct_field_names()
    emitter_carried = struct_fields | {"db_apply_performed"}

    for field in _HEALTH_HARD_SAFETY_FIELDS:
        assert field in emitter_carried, f"hard-safety guard 欄不在 emitter 契約: {field}"
    for field in _HEALTH_PACING_ACTIVITY_FIELDS:
        assert field in struct_fields, f"pacing-activity guard 欄不在 emitter 契約: {field}"
    for field in _OPERATIONAL_SCALAR_FIELDS:
        assert field in struct_fields, f"operational guard 欄不在 emitter 契約: {field}"

    # main_tokens_available 是 emitter 契約欄,但**刻意不**在任一 guard 集（telemetry）。
    assert "main_tokens_available" in struct_fields
    assert "main_tokens_available" not in _HEALTH_PACING_ACTIVITY_FIELDS
    assert "main_tokens_available" not in _HEALTH_HARD_SAFETY_FIELDS


def test_non_telemetry_struct_fields_must_belong_to_a_guard_set() -> None:
    """superset 斷言（W5-S0）：契約 struct 的每一欄——除 telemetry allowlist 與契約
    metadata——**必屬**某 normalizer guard 集。未來 emitter 加 operational 欄而 normalizer
    忘 guard → 本測試即紅（parity 既有方向鎖 guard⊆contract,此為反向 contract⊆guard）。"""
    fields = _rust_struct_fields_with_types()
    guarded = (
        set(_HEALTH_HARD_SAFETY_FIELDS)
        | set(_HEALTH_PACING_ACTIVITY_FIELDS)
        | set(_OPERATIONAL_SCALAR_FIELDS)
    )
    for name, rust_type in fields.items():
        # bool 型欄零豁免（任何布林都是信任/活動「宣稱」,必 guard）。
        if rust_type == "bool":
            assert name in guarded, f"契約 bool 欄未被 normalizer guard: {name}"
            continue
        if name in _TELEMETRY_ALLOWLIST or name in _CONTRACT_METADATA_FIELDS:
            continue
        assert name in guarded, (
            f"契約 operational 欄未被 normalizer guard（也不在 telemetry/metadata "
            f"allowlist）: {name}: {rust_type}"
        )

    # allowlist 衛生：豁免欄必真實存在於契約（防 stale allowlist 假豁免）且互斥。
    struct_fields = set(fields)
    assert _TELEMETRY_ALLOWLIST <= struct_fields
    assert _CONTRACT_METADATA_FIELDS <= struct_fields
    assert _TELEMETRY_ALLOWLIST.isdisjoint(_CONTRACT_METADATA_FIELDS)
    # metadata 集型別衛生（E3 NOTE-3）：逐欄 pin 現值型別——改型（尤其 bool/枚舉）即紅。
    for name, expected_type in _CONTRACT_METADATA_FIELD_TYPES.items():
        assert fields[name] == expected_type, (
            f"metadata 欄 {name} 型別漂移: {fields[name]}（pin={expected_type}）"
        )


def test_normalizer_enum_domains_match_rust_contract_variants() -> None:
    """契約枚舉域 lockstep（E2 MEDIUM-2 / E3 NOTE-1 閉合件）：normalizer 三個封閉值域
    tuple 必須與 Rust enum 變體的 serde snake_case 投影**逐一相等**——Rust 側加/刪/改名
    變體而 Python 域未同步 → 本測試紅（防域清單手抄漂移成 fail-always 或 fail-open）。"""
    assert _SESSION_STATE_DOMAIN == _rust_enum_variants_snake_case(
        RUST_SESSION_STATE_CONTRACT, "IbkrTwsSessionStateV1"
    )
    assert _HALT_REASON_DOMAIN == _rust_enum_variants_snake_case(
        RUST_CONTRACT, "IbkrConnectionHealthHaltReasonV1"
    )
    assert _ENTITLEMENT_STATE_DOMAIN == _rust_enum_variants_snake_case(
        RUST_CONTRACT, "IbkrConnectionHealthEntitlementStateV1"
    )
    # 域欄位對應的 struct 型別衛生：三欄在契約 struct 內確為對應 enum 型（防欄改型後
    # 域檢查失去對象）。
    fields = _rust_struct_fields_with_types()
    assert fields["session_state"] == "IbkrTwsSessionStateV1"
    assert fields["halt_reason"] == "IbkrConnectionHealthHaltReasonV1"
    assert fields["entitlement_state"] == "IbkrConnectionHealthEntitlementStateV1"


def test_emitter_fixture_through_route_is_clean_inactive_baseline() -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=_valid_connection_health())
    client = _make_client_with_ipc(fake_ipc)
    try:
        response = client.get("/api/v1/stock-etf/connection-health")
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert response.status_code == 200
    data = response.json()["data"]
    # inactive 誠實基線：零 violation、external_verification_pending、lineage 未放行（第 3 層不可達）。
    assert data["contract_violations"] == []
    assert data["connection_health_state"] == "external_verification_pending"
    assert data["lineage_present"] is False
    assert data["phase2_gate_status"] == "BLOCKED"

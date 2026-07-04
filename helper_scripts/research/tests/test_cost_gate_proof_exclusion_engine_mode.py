"""F10(E4 2026-07-04 補審):engine_mode 正規化跨語言對稱性測試。

Rust 側(bounded_probe_active_order.rs)`order_link_engine_mode_tag` /
`learning_probe_admission_is_demo_only` 對 engine_mode 一律 trim +
to_ascii_lowercase;`candidate_matched_active_bounded_probe_proof_key` 另要求
trim-stable(前後空白直接拒絕)。Python 鏡像 proof_exclusion.py 原為
exact-match dict/set,大小寫或空白輸入會與 Rust 判定分裂(drift-source)。
本檔釘住修復後的對稱語義:大小寫變體同判、未 trim-stable 的 proof key 拒絕。
"""

from __future__ import annotations

from cost_gate_learning_lane.proof_exclusion import (
    _candidate_bound_active_order_link_id_is_valid,
    proof_exclusion_reasons,
)


SIDE_CELL = "ma_crossover|BTCUSDT|Sell"
SIGNAL_TS_MS = 1_700_000_000_001
CONTEXT_ID = "ctx-demo-ma_crossover-BTCUSDT-1700000000001"
SIGNAL_ID = "sig-demo-ma_crossover-BTCUSDT-1700000000001"
ACTIVE_HASH_MOD = 101_559_956_668_416
ACTIVE_HASH_LEN = 9


def _to_base36(value: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out = ""
    while value > 0:
        value, idx = divmod(value, 36)
        out = digits[idx] + out
    return out


def _candidate_hash(side_cell_key: str, context_id: str, signal_id: str) -> str:
    # 獨立重算 FNV-1a lineage hash(不 import 模組私有函數),模組側演算法漂移時本測試同樣會紅。
    hash_value = 0xCBF2_9CE4_8422_2325
    payload = (
        side_cell_key.encode()
        + bytes([0x1E])
        + context_id.encode()
        + bytes([0x1F])
        + signal_id.encode()
    )
    for byte in payload:
        hash_value ^= byte
        hash_value = (hash_value * 0x0000_0100_0000_01B3) & 0xFFFF_FFFF_FFFF_FFFF
    return _to_base36(hash_value % ACTIVE_HASH_MOD).rjust(ACTIVE_HASH_LEN, "0")


def _valid_order_link_id(seq: int = 1) -> str:
    return (
        f"oc_dm_{SIGNAL_TS_MS}_{_to_base36(seq)}_"
        f"{_candidate_hash(SIDE_CELL, CONTEXT_ID, SIGNAL_ID)}"
    )


def _active_fill_backed_row(engine_mode: str) -> dict:
    order_link_id = _valid_order_link_id()
    return {
        "record_type": "probe_outcome",
        "attempt_id": "attempt-1",
        "side_cell_key": SIDE_CELL,
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "realized_net_bps": 2.0,
        "gross_bps": 6.0,
        "outcome_source": "candidate_matched_demo_fill",
        "reference_source": "bounded_probe_active_near_touch",
        "order_link_id": order_link_id,
        "order_id": "bybit-order-1",
        "exec_id": "exec-1",
        "intent_id": "intent-1",
        "risk_verdict": "APPROVED_BY_BOUNDED_DEMO_PROBE",
        "fee_bps": 2.0,
        "slippage_bps": 0.25,
        "close_state": "CLOSED_AT_HORIZON",
        "source_artifact_path": "artifacts/probe/fill-1.json",
        "active_bounded_probe_proof_key": {
            "side_cell_key": SIDE_CELL,
            "engine_mode": engine_mode,
            "signal_ts_ms": SIGNAL_TS_MS,
            "context_id": CONTEXT_ID,
            "signal_id": SIGNAL_ID,
            "order_link_id": order_link_id,
            "decision_lease_id": "lease-demo-1",
            "reference_source": "bounded_probe_active_near_touch",
        },
    }


def test_order_link_id_validator_normalizes_engine_mode_like_rust() -> None:
    # 鏡像 Rust order_link_engine_mode_tag(trim+to_ascii_lowercase):
    # "Demo"/" demo " 與 "demo" 必須同判為有效(id 內 mode tag 仍必須是 "dm")。
    order_link_id = _valid_order_link_id()
    for engine_mode in ("demo", "Demo", "DEMO", " demo ", "\tdemo\n", "Live_Demo"):
        expected_tag = "dm" if "demo" == engine_mode.strip().lower() else "ld"
        candidate = order_link_id if expected_tag == "dm" else None
        if candidate is None:
            # live_demo 變體:期望 tag "ld","dm" 開頭的 id 必須被拒 → 驗不對稱不放行
            assert not _candidate_bound_active_order_link_id_is_valid(
                order_link_id,
                engine_mode,
                SIGNAL_TS_MS,
                SIDE_CELL,
                CONTEXT_ID,
                SIGNAL_ID,
            )
            continue
        assert _candidate_bound_active_order_link_id_is_valid(
            candidate,
            engine_mode,
            SIGNAL_TS_MS,
            SIDE_CELL,
            CONTEXT_ID,
            SIGNAL_ID,
        ), f"engine_mode={engine_mode!r} 應與 'demo' 同判有效"


def test_order_link_id_validator_still_rejects_non_demo_modes() -> None:
    order_link_id = _valid_order_link_id()
    for engine_mode in ("live", "Live", "paper", "", "  ", "demo x", "live-demo"):
        assert not _candidate_bound_active_order_link_id_is_valid(
            order_link_id,
            engine_mode,
            SIGNAL_TS_MS,
            SIDE_CELL,
            CONTEXT_ID,
            SIGNAL_ID,
        ), f"engine_mode={engine_mode!r} 不在 demo-only 集,必須拒絕"


def test_proof_key_engine_mode_case_variant_counts_after_normalization() -> None:
    # trim-stable 的大小寫變體(如 "Demo")鏡像 Rust 輸入側判定:接受。
    for engine_mode in ("demo", "Demo", "DEMO"):
        row = _active_fill_backed_row(engine_mode)
        reasons = proof_exclusion_reasons(row)
        assert "active_bounded_probe_proof_key_missing_or_invalid" not in reasons, (
            f"engine_mode={engine_mode!r} 正規化後應為有效 proof key,實得 {reasons}"
        )


def test_proof_key_engine_mode_untrimmed_is_rejected_like_rust_trim_stable() -> None:
    # 鏡像 Rust candidate_matched_active_bounded_probe_proof_key(:273):
    # engine_mode 未 trim-stable 一律拒絕(fail-closed,不靜默修剪)。
    for engine_mode in (" demo ", "demo ", " demo", "\tdemo"):
        row = _active_fill_backed_row(engine_mode)
        reasons = proof_exclusion_reasons(row)
        assert "active_bounded_probe_proof_key_missing_or_invalid" in reasons, (
            f"engine_mode={engine_mode!r} 未 trim-stable 應拒絕,實得 {reasons}"
        )


def test_proof_key_non_demo_engine_mode_still_rejected() -> None:
    for engine_mode in ("live", "Live", "paper", ""):
        row = _active_fill_backed_row(engine_mode)
        reasons = proof_exclusion_reasons(row)
        assert "active_bounded_probe_proof_key_missing_or_invalid" in reasons

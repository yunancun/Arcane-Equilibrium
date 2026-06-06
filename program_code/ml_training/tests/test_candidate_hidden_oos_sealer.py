"""hidden_oos sealer 測試：核心是 sealer 輸出**同時通過** source_contract 兩個 gate。"""

from __future__ import annotations

from program_code.ml_training.candidate_evidence_source_contract import (
    _load_hidden_oos_state_snapshot,
    _validate_durable_hidden_oos_state_snapshot,
)
from program_code.ml_training.candidate_hidden_oos_sealer import (
    HIDDEN_OOS_SEALED_STATE,
    build_hidden_oos_state,
    hidden_oos_source_row_fields,
)


def _state(**over):
    params = dict(
        family_id="grid_trading",
        calibration_window=("2026-04-01T00:00:00+00:00", "2026-05-01T00:00:00+00:00"),
        candidate_window=("2026-05-01T00:00:00+00:00", "2026-05-20T00:00:00+00:00"),
        oos_window=("2026-05-21T00:00:00+00:00", "2026-06-01T00:00:00+00:00"),
        embargo_seconds=14400,
        total_candidates_k=10,
        residual_report_hash="b" * 64,
    )
    params.update(over)
    return build_hidden_oos_state(**params)


def test_sealed_state_passes_manifest_and_durable_gates():
    state = _state()
    source_row = dict(hidden_oos_source_row_fields(state))
    # gate 1：migration-free manifest producer gate
    out_state, err = _load_hidden_oos_state_snapshot(source_row)
    assert err is None
    assert out_state is not None
    # gate 2：durable gate（body sha256 須與 manifest 內 hidden_oos_state 一致）
    durable_err = _validate_durable_hidden_oos_state_snapshot(
        source_row=source_row, hidden_oos_state=out_state
    )
    assert durable_err is None


def test_state_is_sealed_unopened():
    state = _state()
    assert state["state"] == HIDDEN_OOS_SEALED_STATE
    assert state["open_count"] == 0
    assert state["opened_for_iteration"] is False
    assert state["consumed"] is False
    assert state["invalidated"] is False
    # split_hash hex64
    assert len(state["split_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in state["split_hash"])
    # OOS 窗對外 = window_start/end
    assert state["window_start"] == state["oos_window"]["start"]
    assert state["window_end"] == state["oos_window"]["end"]


def test_flat_window_keys_match_nested_and_split_hash_frozen():
    """T1（PART 2 §2）：flat key 純加性補齊 + split_hash byte-identical 凍結。

    為什麼：experiment_registry `_extract`/`_persist` 只認 flat
    calibration_train_*/candidate_* 而非 nested（FACT 3 schema mismatch）；
    補 flat key 必須與 nested 對應值一致，且**不得**改變 split_hash（flat key
    不在 compute_split_hash payload，故補齊前後 split_hash 必 byte-identical）。
    """
    state = _state()
    # 4 個新 flat key 等於其 nested 對應值
    assert state["calibration_train_window_start"] == state["calibration_window"]["start"]
    assert state["calibration_train_window_end"] == state["calibration_window"]["end"]
    assert state["candidate_window_start"] == state["candidate_window"]["start"]
    assert state["candidate_window_end"] == state["candidate_window"]["end"]
    # 既有 OOS flat key 仍對齊 nested
    assert state["window_start"] == state["oos_window"]["start"]
    assert state["window_end"] == state["oos_window"]["end"]
    # nested key 仍保留（durable gate canonical sha256 比對需同物件）
    assert "calibration_window" in state
    assert "candidate_window" in state
    assert "oos_window" in state
    # split_hash 凍結值（補 flat key 前後 byte-identical；payload 不含 flat key）
    assert (
        state["split_hash"]
        == "ebbb4000fb6d315e0d68075fdc82afbd8c5a8e3e9e3ac0c3a3c9a989af53135e"
    )


def test_window_mismatch_is_rejected():
    state = _state()
    fields = dict(hidden_oos_source_row_fields(state))
    # 竄改 registry commitment 窗 → manifest gate 應以 window_mismatch 拒
    fields["replay_registry_oos_label_window_end"] = "2026-07-01T00:00:00+00:00"
    out_state, err = _load_hidden_oos_state_snapshot(fields)
    assert out_state is None
    assert err is not None and "window_mismatch" in err[0]


def test_unsealed_state_rejected():
    state = _state()
    state = dict(state)
    state["state"] = "open"  # 未封存
    fields = dict(hidden_oos_source_row_fields(state))
    out_state, err = _load_hidden_oos_state_snapshot(fields)
    assert out_state is None
    assert err is not None and "not_sealed" in err[0]

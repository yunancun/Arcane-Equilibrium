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

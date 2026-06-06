"""Residual PART 2 bridge 測試（T2-T9，PART 2 §6）。

涵蓋：sealer→registry `_extract` 接受（FACT 3 修復）、leak carve-out 微分證明、
三窗衍生 + V132 約束、embargo 對賬、manifest 合法、e2e 誠實 defer、flag-OFF 零寫
入、manifest_hash 含 hidden_oos_state。全 pure-core（mock conn + 注入 register_fn /
FakeCursor 直驅 register_experiment），無真 PG（真 V132 CHECK 撞屬 PART 3 Linux）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.experiment_registry import (  # noqa: E501
    REGISTRY_RESIDUAL_ALPHA_HASH_FIELD,
    ReplayExperimentRegisterRequest,
    _extract_alpha_hidden_oos_v049_fields,
    register_experiment,
)
from program_code.ml_training.candidate_evidence_source_contract import (
    DURABLE_HIDDEN_OOS_STATE_FIELD,
    DURABLE_HIDDEN_OOS_STATE_JSONB_FIELD,
    DURABLE_RESIDUAL_ALPHA_HASH_FIELD,
    DURABLE_RESIDUAL_ALPHA_REPORT_FIELD,
    _load_hidden_oos_state_snapshot,
    _validate_durable_hidden_oos_state_snapshot,
    build_live_candidate_evidence_from_source,
)
from program_code.ml_training.candidate_evidence_manifest import PENDING_SCHEMA
from program_code.ml_training.candidate_hidden_oos_sealer import build_hidden_oos_state
from program_code.ml_training.residual_alpha_cycle import (
    RESIDUAL_PRODUCER_ENV,
    evaluate_cell,
)
from program_code.ml_training.residual_alpha_producer_db import (
    DEFAULT_BUCKET_SEC,
    bucket_floor,
    bucket_round_trips_by_exit,
)
from program_code.ml_training.residual_alpha_report_contract import (
    RESIDUAL_ALPHA_REPORT_FIELD,
)
from program_code.ml_training import residual_hidden_oos_bridge as bridge


# ─── 共用 fixtures / helpers ───────────────────────────────────────────

_H = 3600.0
_BUCKET = DEFAULT_BUCKET_SEC  # 4h = 14400s
# OOS 窗起點：選一個遠在 round-trip 之後的整 4h 邊界。
_OOS_START_EPOCH = 100.0 * _BUCKET  # 1,440,000
_OOS_START = datetime.fromtimestamp(_OOS_START_EPOCH, tz=timezone.utc)
_DATA_END = datetime.fromtimestamp(_OOS_START_EPOCH + 30 * _BUCKET, tz=timezone.utc)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()


def _passing_residual_report(**overrides) -> dict:
    """通過 validate_demo_residual_alpha_report 的合成 report（e2e 用）。

    為什麼合成而非用 bridge 真 report：單配置 demo report 必 passes=False/
    verdict=defer_data（QC 對的，honest defer），會卡在 source_contract 第一道
    residual validator；e2e 要證的是「hidden-OOS lineage 全接好、唯一缺口是
    drar」，故餵一份通過 report 讓流程跑到 durable-residual gate。
    """
    report = {
        "passes": True,
        "verdict": "pass",
        "reasons": [],
        "raw_mean_bps": 2.0,
        "residual_mean_bps": 1.4,
        "r_beta_retention": 0.7,
        "beta_edge_share": 0.3,
        "psr_raw": 0.97,
        "psr_residual": 0.98,
        "dsr_raw": 0.96,
        "dsr_residual": 0.97,
        "pbo_raw": 0.20,
        "pbo_residual": 0.10,
        "factor_panel_hash": "sha256:factor-panel",
        "fit_window": {"train_end": 79, "eval_start": 80},
        "coverage": {"train": 0.90, "eval": 0.85},
    }
    report.update(overrides)
    return report


def _operator_actor() -> Any:
    class _Actor:
        actor_id = "alice"

    return _Actor()


class _FakeCursor:
    """捕捉 register_experiment 兩個 INSERT 的 (sql, params)；fetchone 腳本化。"""

    def __init__(self, fetchone_returns: list):
        self.records: list[tuple[str, tuple]] = []
        self._fetchone_iter = iter(fetchone_returns)

    def execute(self, sql: str, params: Any = ()) -> None:
        text = str(sql)
        if "SET LOCAL" in text:
            return
        if "pg_try_advisory_xact_lock" in text:
            # advisory lock：register 對無 idempotency_key 不會呼到，留作保險。
            return
        self.records.append((text, tuple(params) if params else ()))

    def fetchone(self) -> Any:
        # advisory lock 路徑（無 idempotency_key 時不觸發）回 None 即可。
        try:
            return next(self._fetchone_iter)
        except StopIteration:
            return None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


# 封存態的三窗（epoch 邊界 → ISO；全程同一條 epoch 軸、嚴格遞增 calib<cand<oos，
# 與 T3 round-trip 資料尺度一致，避免 1970/2026 混用造成的窗序不一致）。
_CALIB_START = datetime.fromtimestamp(10.0 * _BUCKET, tz=timezone.utc)
_CALIB_END = datetime.fromtimestamp(40.0 * _BUCKET, tz=timezone.utc)
_CAND_START = datetime.fromtimestamp(40.0 * _BUCKET, tz=timezone.utc)
_CAND_END = datetime.fromtimestamp(90.0 * _BUCKET, tz=timezone.utc)


def _alpha_state(**overrides) -> dict:
    """sealed hidden_oos_state（含 STEP 1 flat key）。三窗嚴格遞增；oos 窗
    對齊 body data_window（_OOS_START/_DATA_END）。"""
    state = build_hidden_oos_state(
        family_id="family-alpha",
        calibration_window=(_CALIB_START.isoformat(), _CALIB_END.isoformat()),
        candidate_window=(_CAND_START.isoformat(), _CAND_END.isoformat()),
        oos_window=(_OOS_START.isoformat(), _DATA_END.isoformat()),
        embargo_seconds=int(round((1 + 0.5) * _BUCKET)),  # 21600
        total_candidates_k=12,
        residual_report_hash="c" * 64,
    )
    state.update(overrides)
    return state


# ─── T2：sealer → registry _extract 接受（直擊 FACT 3 修復）────────────


def test_t2_sealer_state_accepted_by_registry_extract():
    report = _passing_residual_report()
    residual_hash = _canonical_sha256(report)
    embargo_seconds = int(round((1 + 0.5) * _BUCKET))  # 21600
    state = _alpha_state(residual_report_hash=residual_hash)
    manifest = {
        "hidden_oos_state": state,
        REGISTRY_RESIDUAL_ALPHA_HASH_FIELD: residual_hash,
    }
    body = ReplayExperimentRegisterRequest(
        symbol="BTCUSDT",
        strategy="grid_trading",
        timeframe="4h",
        data_tier="S3",
        data_window_start=_OOS_START,
        data_window_end=_DATA_END,
        strategy_config_sha256="a" * 64,
        risk_config_sha256="b" * 64,
        half_life_days=7.0,
        embargo_days=embargo_seconds / 86400.0,
        manifest_jsonb=manifest,
        signature_hex=None,
    )
    fields, err = _extract_alpha_hidden_oos_v049_fields(
        manifest_jsonb=manifest, body=body
    )
    # 補了 flat key 後不再以 *_missing 拒（FACT 3 修復）。
    assert err is None, err
    assert fields["calibration_train_window_start"].isoformat() == (
        _CALIB_START.isoformat()
    )
    assert fields["candidate_window_end"].isoformat() == _CAND_END.isoformat()
    assert fields["oos_embargo_seconds"] == embargo_seconds
    assert fields["total_candidates_k"] == 12


# ─── T3：carve-out leak（核心，bite 微分證明）──────────────────────────


def _in_oos_round_trips() -> list[dict]:
    """非 OOS round-trip：跨多個 4h 桶，產生足夠 aligned bucket。"""
    rts = []
    base = 10.0 * _BUCKET
    for i in range(10):
        exit_ = base + i * _BUCKET + 600.0  # 落在第 i 桶內
        rts.append({"entry_ts": exit_ - 300.0, "exit_ts": exit_, "net_bps": 1.0})
    return rts


def _btc_klines_4h() -> list[dict]:
    """覆蓋非 OOS + OOS 區的 4h BTC bars。"""
    bars = []
    base = 9.0 * _BUCKET
    price = 100.0
    for i in range(130):
        ts = base + i * _BUCKET
        bars.append({"ts": ts, "open": price, "close": price * 1.001})
        price *= 1.001
    return bars


def test_t3_partition_strictness():
    rts = [
        {"entry_ts": 0.0, "exit_ts": _OOS_START_EPOCH - 1.0, "net_bps": 1.0},
        {"entry_ts": 0.0, "exit_ts": _OOS_START_EPOCH, "net_bps": 9999.0},
        {"entry_ts": 0.0, "exit_ts": _OOS_START_EPOCH + 1.0, "net_bps": 9999.0},
    ]
    non_oos, oos = bridge.partition_round_trips_by_oos(rts, _OOS_START_EPOCH)
    assert all(rt["exit_ts"] < _OOS_START_EPOCH for rt in non_oos)
    assert len(non_oos) == 1
    # exit==oos_start 與 exit>oos_start 都歸 OOS（嚴格 <）。
    assert len(oos) == 2
    assert sorted(rt["exit_ts"] for rt in oos) == [
        _OOS_START_EPOCH,
        _OOS_START_EPOCH + 1.0,
    ]


def test_t3_oos_buckets_absent_from_non_oos_bucketing():
    in_rts = _in_oos_round_trips()
    out_rts = [
        {"entry_ts": _OOS_START_EPOCH, "exit_ts": _OOS_START_EPOCH + 600.0, "net_bps": 9999.0},
        {"entry_ts": _OOS_START_EPOCH + _BUCKET, "exit_ts": _OOS_START_EPOCH + _BUCKET + 600.0, "net_bps": 9999.0},
    ]
    non_oos, _ = bridge.partition_round_trips_by_oos(in_rts + out_rts, _OOS_START_EPOCH)
    non_oos_buckets, _ = bucket_round_trips_by_exit(non_oos, _BUCKET)
    oos_floor = bucket_floor(_OOS_START_EPOCH, _BUCKET)
    # 非 OOS bucketing 不得含任何 >= OOS 起桶的 bucket。
    assert all(b < oos_floor for b in non_oos_buckets)


def test_t3_bite_extreme_out_trips_do_not_change_report():
    """bite：out-trip 給極端 net_bps，evaluate_cell(non_oos) report 不變。"""
    in_rts = _in_oos_round_trips()
    btc = _btc_klines_4h()
    out_rts = [
        {"entry_ts": _OOS_START_EPOCH, "exit_ts": _OOS_START_EPOCH + 600.0, "net_bps": 9999.0},
        {"entry_ts": _OOS_START_EPOCH + _BUCKET, "exit_ts": _OOS_START_EPOCH + _BUCKET + 600.0, "net_bps": -9999.0},
    ]
    non_oos_only, _ = bridge.partition_round_trips_by_oos(in_rts, _OOS_START_EPOCH)
    non_oos_with_out, _ = bridge.partition_round_trips_by_oos(
        in_rts + out_rts, _OOS_START_EPOCH
    )
    r1 = evaluate_cell(
        "grid::BTCUSDT", non_oos_only, btc,
        n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
    )
    r2 = evaluate_cell(
        "grid::BTCUSDT", non_oos_with_out, btc,
        n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
    )
    # carve-out 排除 out-trip → 兩 report 完全相同（report 對 out-trip 不敏感）。
    assert r1.report == r2.report


def test_t3_btc_klines_load_bounded_below_oos_start():
    """factor 範圍夾止：傳給 load_btc_klines 的 end_ts < oos_start（mock 捕參）。"""
    captured: dict[str, Any] = {}

    class _Conn:
        pass

    def _fake_load_round_trips(conn, strategy, *, engine_mode, since):
        return _in_oos_round_trips() + [
            {"entry_ts": _OOS_START_EPOCH, "exit_ts": _OOS_START_EPOCH + 600.0, "net_bps": 9999.0},
        ]

    def _fake_load_btc_klines(conn, *, start_ts, end_ts, timeframe):
        captured["start_ts"] = start_ts
        captured["end_ts"] = end_ts
        return _btc_klines_4h()

    def _fake_register_fn(get_pg_conn_fn, actor, body, *, manifest_signer_module=None):
        return {"experiment_id": "x"}, None

    monkey_restore = (bridge.load_round_trips, bridge.load_btc_klines)
    bridge.load_round_trips = _fake_load_round_trips
    bridge.load_btc_klines = _fake_load_btc_klines
    try:
        import os

        os.environ[RESIDUAL_PRODUCER_ENV] = "1"
        try:
            bridge.register_residual_candidate_experiment(
                _Conn(),
                strategy="grid_trading", symbol="BTCUSDT", timeframe="4h",
                family_id="family-alpha",
                since=datetime.fromtimestamp(0.0, tz=timezone.utc),
                oos_start=_OOS_START, data_end=_DATA_END,
                n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
                actor=_operator_actor(),
                strategy_config_sha256="a" * 64, risk_config_sha256="b" * 64,
                get_pg_conn_fn=lambda: None,
                register_fn=_fake_register_fn,
            )
        finally:
            os.environ.pop(RESIDUAL_PRODUCER_ENV, None)
    finally:
        bridge.load_round_trips, bridge.load_btc_klines = monkey_restore

    end_epoch = captured["end_ts"].timestamp()
    assert end_epoch < _OOS_START_EPOCH, (end_epoch, _OOS_START_EPOCH)


# ─── T4：三窗衍生 + V132 約束 ──────────────────────────────────────────


def test_t4_windows_strictly_increasing_and_iso_round_trip():
    # 三窗首尾相接嚴格遞增（calib → candidate → oos）。
    cw = ("2026-03-01T00:00:00+00:00", "2026-03-31T00:00:00+00:00")
    nw = ("2026-04-01T00:00:00+00:00", "2026-04-20T00:00:00+00:00")
    ow = ("2026-05-01T00:00:00+00:00", "2026-05-20T00:00:00+00:00")
    assert bridge._windows_strictly_increasing(cw, nw, ow) is True
    # epoch→ISO 往返：bridge._epoch_to_iso 可被 fromisoformat 解回同 instant。
    iso = bridge._epoch_to_iso(_OOS_START_EPOCH)
    assert datetime.fromisoformat(iso).timestamp() == _OOS_START_EPOCH
    # 交叉窗（cand_end > oos_start）→ 非遞增。
    bad = ("2026-04-01T00:00:00+00:00", "3000-01-01T00:00:00+00:00")
    assert bridge._windows_strictly_increasing(cw, bad, ow) is False
    # 單窗 start>=end（calib 反序）→ 非遞增。
    assert bridge._windows_strictly_increasing((nw[1], nw[0]), nw, ow) is False


def test_t4_embargo_zero_fail_closed_no_check_hit():
    """embargo_buckets=0 → embargo_seconds=0（MED-3 對齊 evaluate_cell：eb=0 purge
    0 秒）→ 須 fail-closed 在送進 V132 CHECK 之前；register_fn spy 證 0-embargo
    路徑不寫入。

    MED-3 前 bridge 用無條件 ``(eb+0.5)*bs``，bucket_sec=4h 時 eb=0 → 7200s（與
    evaluate_cell 的 0 purge 不符且會誤述封存 embargo）。對齊後 eb=0 ⇒ 0 ⇒
    fail-closed，與 bucket_sec 無關；此處沿用 bucket_sec=1.0 一併夾住。
    """
    import os

    calls = {"n": 0}

    def _fake_register_fn(get_pg_conn_fn, actor, body, *, manifest_signer_module=None):
        calls["n"] += 1
        return {"experiment_id": "x"}, None

    def _fake_load_round_trips(conn, strategy, *, engine_mode, since):
        return _in_oos_round_trips()

    def _fake_load_btc_klines(conn, *, start_ts, end_ts, timeframe):
        return _btc_klines_4h()

    restore = (bridge.load_round_trips, bridge.load_btc_klines)
    bridge.load_round_trips = _fake_load_round_trips
    bridge.load_btc_klines = _fake_load_btc_klines
    os.environ[RESIDUAL_PRODUCER_ENV] = "1"
    try:
        # bucket_sec=1.0, embargo_buckets=0 → embargo_seconds=int(round(0.5))=0
        # → V132 STRICT 違反 → bridge fail-closed，不送 register_fn。
        result, err = bridge.register_residual_candidate_experiment(
            object(),
            strategy="grid_trading", symbol="BTCUSDT", timeframe="4h",
            family_id="family-alpha",
            since=datetime.fromtimestamp(0.0, tz=timezone.utc),
            oos_start=_OOS_START, data_end=_DATA_END,
            n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
            actor=_operator_actor(),
            strategy_config_sha256="a" * 64, risk_config_sha256="b" * 64,
            get_pg_conn_fn=lambda: None,
            register_fn=_fake_register_fn,
            embargo_buckets=0, bucket_sec=1.0,
        )
    finally:
        os.environ.pop(RESIDUAL_PRODUCER_ENV, None)
        bridge.load_round_trips, bridge.load_btc_klines = restore

    assert result is None
    assert err == "embargo_seconds_non_positive"
    assert calls["n"] == 0  # 零寫入，未撞 CHECK


# ─── T5：embargo days↔seconds 對賬 ─────────────────────────────────────


@pytest.mark.parametrize(
    "bucket_sec,embargo_buckets",
    [
        (14400.0, 1),   # 4h, 1 → 21600s → 0.25d
        (14400.0, 2),   # 4h, 2 → 36000s
        (3600.0, 1),    # 1h, 1 → 5400s
        (86400.0, 1),   # 1d, 1 → 129600s
        (900.0, 3),     # 15m, 3 → 50400... → 3150s
    ],
)
def test_t5_embargo_days_seconds_round_trip(bucket_sec, embargo_buckets):
    embargo_seconds = int(round((embargo_buckets + 0.5) * bucket_sec))
    embargo_days = embargo_seconds / 86400.0
    # experiment_registry `_extract` 的對賬式：必 byte-精確相等（夾 float 抖動）。
    assert int(round(embargo_days * 86400)) == embargo_seconds
    assert embargo_seconds > 0


# ─── T6：manifest 組裝合法 ─────────────────────────────────────────────


def test_t6_manifest_assembly_legal():
    """組一個 manifest 跑 ReplayExperimentRegisterRequest 驗證（無 _ 前綴、
    含三組必要欄位、runtime 欄位與 body 一致）。"""
    report = _passing_residual_report()
    residual_hash = _canonical_sha256(report)
    state = _alpha_state(residual_report_hash=residual_hash)
    manifest = {
        "symbol": "BTCUSDT",
        "strategy": "grid_trading",
        "timeframe": "4h",
        "data_tier": "S3",
        "hidden_oos_state": state,
        REGISTRY_RESIDUAL_ALPHA_HASH_FIELD: residual_hash,
        RESIDUAL_ALPHA_REPORT_FIELD: report,
    }
    # 無 "_"-prefix key（register validator M-4 會拒）。
    assert not any(k.startswith("_") for k in manifest)
    # 三組必要欄位群。
    assert "hidden_oos_state" in manifest
    assert REGISTRY_RESIDUAL_ALPHA_HASH_FIELD in manifest
    assert manifest["symbol"] == "BTCUSDT" and manifest["data_tier"] == "S3"
    # Pydantic 驗證通過（含 M-4 _no_reserved_prefix_keys + size cap）。
    body = ReplayExperimentRegisterRequest(
        symbol="BTCUSDT", strategy="grid_trading", timeframe="4h", data_tier="S3",
        data_window_start=_OOS_START, data_window_end=_DATA_END,
        strategy_config_sha256="a" * 64, risk_config_sha256="b" * 64,
        half_life_days=7.0, embargo_days=0.25,
        manifest_jsonb=manifest, signature_hex=None,
    )
    # runtime 欄位與 body 同名欄位字串相等（避免 register manifest_runtime_field_mismatch）。
    assert str(body.manifest_jsonb["symbol"]) == str(body.symbol)
    assert str(body.manifest_jsonb["timeframe"]) == str(body.timeframe)


# ─── T7：e2e source_contract 誠實 defer（CRITICAL，gate ordering）───────


def _register_and_capture(report: dict) -> tuple[_FakeCursor, str, str, dict]:
    """直驅 register_experiment（FakeCursor 捕兩個 INSERT），回 (cursor, exp_id,
    manifest_hash_hex, manifest_to_persist)。embargo_days 對齊 state.embargo_seconds。"""
    import os

    residual_hash = _canonical_sha256(report)
    embargo_seconds = int(round((1 + 0.5) * _BUCKET))  # 21600
    state = _alpha_state(residual_report_hash=residual_hash)
    manifest = {
        "symbol": "BTCUSDT", "strategy": "grid_trading", "timeframe": "4h",
        "data_tier": "S3",
        "hidden_oos_state": state,
        REGISTRY_RESIDUAL_ALPHA_HASH_FIELD: residual_hash,
        RESIDUAL_ALPHA_REPORT_FIELD: report,
    }
    body = ReplayExperimentRegisterRequest(
        symbol="BTCUSDT", strategy="grid_trading", timeframe="4h", data_tier="S3",
        data_window_start=_OOS_START, data_window_end=_DATA_END,
        strategy_config_sha256="a" * 64, risk_config_sha256="b" * 64,
        half_life_days=7.0, embargo_days=embargo_seconds / 86400.0,
        manifest_jsonb=manifest, signature_hex=None,
    )
    ts = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
    cur = _FakeCursor([("33333333-3333-3333-3333-333333333333", ts)])
    # mac_dev runtime 避開 linux engine-sha fail-closed gate。
    os.environ["OPENCLAW_REPLAY_RUNTIME_ENV"] = "mac_dev_smoke_test_only"
    try:
        result, err = register_experiment(cur, _operator_actor(), body)
    finally:
        os.environ.pop("OPENCLAW_REPLAY_RUNTIME_ENV", None)
    assert err is None, err
    return cur, result["experiment_id"], result["manifest_hash"], body.manifest_jsonb


def _source_row_from_inserts(report: dict) -> dict:
    """從 register_experiment 兩個 INSERT 重建 source_row（鍵名對齊 JOIN AS 別名）。

    drar 兩欄（durable_residual_alpha_*）**故意留缺**——PART 2 不寫 drar，這正是
    e2e 誠實 defer 的點。"""
    cur, exp_id, manifest_hash_hex, manifest = _register_and_capture(report)
    exp_insert = next(
        p for s, p in cur.records if "INSERT INTO replay.experiments" in s
    )
    hos_insert = next(
        p for s, p in cur.records
        if "INSERT INTO learning.hidden_oos_state_registry" in s
    )
    # replay.experiments INSERT 參數位（見 experiment_registry register VALUES）：
    #   p[14]=oos_label_window_start, p[15]=oos_label_window_end,
    #   p[16]=oos_embargo_seconds, p[17]=total_candidates_K, p[18]=manifest_jsonb(json)
    manifest_jsonb_persisted = json.loads(exp_insert[18])
    oos_start = manifest["hidden_oos_state"]["window_start"]
    oos_end = manifest["hidden_oos_state"]["window_end"]
    embargo_seconds = manifest["hidden_oos_state"]["embargo_seconds"]
    total_k = manifest["hidden_oos_state"]["total_candidates_k"]
    # hidden_oos_state_registry INSERT：p[13]=state_jsonb（durable state）。
    durable_state_jsonb = json.loads(hos_insert[13])
    return {
        "evidence_source_tier": "calibrated_replay",
        "replay_experiment_id": exp_id,
        "manifest_hash": manifest_hash_hex,
        "replay_registry_manifest_hash": manifest_hash_hex,
        "replay_registry_status": "completed",
        "replay_registry_expires_at": "2999-01-01T00:00:00+00:00",
        "replay_registry_manifest_jsonb": manifest_jsonb_persisted,
        "replay_registry_oos_label_window_start": oos_start,
        "replay_registry_oos_label_window_end": oos_end,
        "replay_registry_oos_embargo_seconds": embargo_seconds,
        "replay_registry_total_candidates_k": total_k,
        DURABLE_HIDDEN_OOS_STATE_FIELD: "sealed",
        DURABLE_HIDDEN_OOS_STATE_JSONB_FIELD: durable_state_jsonb,
        RESIDUAL_ALPHA_REPORT_FIELD: report,
        # drar 兩欄故意缺（PART 2 外）→ honest defer 的點。
    }


def test_t7a_hidden_oos_gates_pass_directly():
    """(a) 直接呼兩個 hidden-OOS gate 證明 PASS（全流程因更早 defer 看不到）。"""
    report = _passing_residual_report()
    source_row = _source_row_from_inserts(report)
    state, err = _load_hidden_oos_state_snapshot(source_row)
    assert err is None, err
    assert state is not None
    durable_err = _validate_durable_hidden_oos_state_snapshot(
        source_row=source_row, hidden_oos_state=state
    )
    assert durable_err is None, durable_err


def test_t7b_full_flow_honest_defer_on_missing_drar():
    """(b) 全流程在缺 drar 時誠實 defer = PENDING_SCHEMA /
    durable_residual_alpha_report_hash_missing。

    這是 EXPECTED honest defer（PA §5.2），**不是 bug**：hidden-OOS lineage 已端
    到端接好，唯一缺口是 durable residual registry（drar），屬 PART 3 範圍。
    """
    report = _passing_residual_report()
    source_row = _source_row_from_inserts(report)
    build = build_live_candidate_evidence_from_source(source_row)
    assert build.validation.promotion_ready is False
    assert build.validation.verdict == PENDING_SCHEMA
    assert "durable_residual_alpha_report_hash_missing" in build.validation.reason


# ─── T8：flag-OFF 零寫入 ───────────────────────────────────────────────


def test_t8_flag_off_no_write():
    import os

    calls = {"n": 0}

    def _spy_register_fn(get_pg_conn_fn, actor, body, *, manifest_signer_module=None):
        calls["n"] += 1
        return {"experiment_id": "x"}, None

    os.environ.pop(RESIDUAL_PRODUCER_ENV, None)  # 確保未設 → 預設 OFF
    result, err = bridge.register_residual_candidate_experiment(
        object(),
        strategy="grid_trading", symbol="BTCUSDT", timeframe="4h",
        family_id="family-alpha",
        since=datetime.fromtimestamp(0.0, tz=timezone.utc),
        oos_start=_OOS_START, data_end=_DATA_END,
        n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
        actor=_operator_actor(),
        strategy_config_sha256="a" * 64, risk_config_sha256="b" * 64,
        get_pg_conn_fn=lambda: None,
        register_fn=_spy_register_fn,
    )
    assert result is None
    assert err == "disabled"
    assert calls["n"] == 0


# ─── T9：manifest_hash 含 hidden_oos_state ─────────────────────────────


def test_t9_manifest_hash_includes_hidden_oos_state():
    """同一 manifest 有 vs 無 hidden_oos_state → manifest_hash 不同（證 state 被
    hash 進 manifest_hash；operator handoff (a)）。"""
    from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.experiment_registry import (  # noqa: E501
        compute_manifest_hash,
    )

    report = _passing_residual_report()
    residual_hash = _canonical_sha256(report)
    state = _alpha_state(residual_report_hash=residual_hash)
    base = {
        "symbol": "BTCUSDT", "strategy": "grid_trading", "timeframe": "4h",
        "data_tier": "S3",
        REGISTRY_RESIDUAL_ALPHA_HASH_FIELD: residual_hash,
    }
    without_state = dict(base)
    with_state = dict(base)
    with_state["hidden_oos_state"] = state
    assert compute_manifest_hash(without_state) != compute_manifest_hash(with_state)


# ─── MED-1/MED-2/MED-3 整合測（驅動 FULL bridge → 真 register_experiment）────
#
# 為什麼這組與 T3/T4 不同：T3 的 bite 在呼 evaluate_cell 之前**手動** partition，
# 測的是 partition_round_trips_by_oos 純函數，**不**測 bridge 把 rts_non_oos 餵進
# evaluate_cell 的接線（mutation rts_non_oos→rts_all 在 T3 下仍全綠）。以下三測
# 一律驅動整個 register_residual_candidate_experiment（真 load→partition→
# evaluate_cell→window→manifest→register），register_fn 包**真**
# register_experiment（FakeCursor 捕兩個 INSERT），故 bridge 自身的 _canonical_sha256
# 被 registry residual-hash gate 路徑實際驅動（非 test-local copy）。


def _drive_full_bridge_capture_manifest(
    *,
    loaded_round_trips: list[dict],
    btc_klines: list[dict],
    oos_start=_OOS_START,
    data_end=_DATA_END,
    embargo_buckets: int = 1,
    bucket_sec: float = _BUCKET,
) -> dict:
    """驅動 FULL bridge，register_fn 包真 register_experiment（FakeCursor），回
    register 實際持久化的 ``manifest_to_persist``（= body.manifest_jsonb 經 register
    可能 inject runtime 欄位後的版本）。

    為什麼經真 register：MED-1 要證 registry residual-hash gate 驅動的是 bridge
    自己的 _canonical_sha256（report→manifest[demo_residual_alpha_report_hash]），
    非測試本地 hash。klines 由 caller 注入（mock 不受 MED-2 clamp 影響），故可放
    超集涵蓋 OOS 區，使「若 carve-out 失效則洩漏」可被 report 變化捕捉。
    """
    import os

    captured: dict[str, Any] = {}

    def _fake_load_round_trips(conn, strategy, *, engine_mode, since):
        return [dict(rt) for rt in loaded_round_trips]

    def _fake_load_btc_klines(conn, *, start_ts, end_ts, timeframe):
        captured["klines_end_ts"] = end_ts
        return [dict(b) for b in btc_klines]

    def _real_register_fn(get_pg_conn_fn, actor, body, *, manifest_signer_module=None):
        # 捕 register 持久化的 manifest（含 register 對 unsigned 的 runtime inject）。
        ts = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        cur = _FakeCursor([("44444444-4444-4444-4444-444444444444", ts)])
        os.environ["OPENCLAW_REPLAY_RUNTIME_ENV"] = "mac_dev_smoke_test_only"
        try:
            result, err = register_experiment(cur, actor, body)
        finally:
            os.environ.pop("OPENCLAW_REPLAY_RUNTIME_ENV", None)
        captured["register_err"] = err
        if err is None:
            exp_insert = next(
                p for s, p in cur.records if "INSERT INTO replay.experiments" in s
            )
            captured["manifest_persisted"] = json.loads(exp_insert[18])
        return result, err

    restore = (bridge.load_round_trips, bridge.load_btc_klines)
    bridge.load_round_trips = _fake_load_round_trips
    bridge.load_btc_klines = _fake_load_btc_klines
    os.environ[RESIDUAL_PRODUCER_ENV] = "1"
    try:
        result, err = bridge.register_residual_candidate_experiment(
            object(),
            strategy="grid_trading", symbol="BTCUSDT", timeframe="4h",
            family_id="family-alpha",
            since=datetime.fromtimestamp(0.0, tz=timezone.utc),
            oos_start=oos_start, data_end=data_end,
            n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
            actor=_operator_actor(),
            strategy_config_sha256="a" * 64, risk_config_sha256="b" * 64,
            get_pg_conn_fn=lambda: None,
            register_fn=_real_register_fn,
            embargo_buckets=embargo_buckets, bucket_sec=bucket_sec,
        )
    finally:
        os.environ.pop(RESIDUAL_PRODUCER_ENV, None)
        bridge.load_round_trips, bridge.load_btc_klines = restore
    captured["bridge_result"] = result
    captured["bridge_err"] = err
    return captured


def test_t10_med1_integration_carveout_hash_byte_identical_to_non_oos_only():
    """MED-1（leak 軸整合 bite）：驅動 FULL bridge 兩次——

    run A：load_round_trips = 非 OOS-only。
    run B：load_round_trips = 非 OOS + **極端 net_bps 的 out-trip**（exit>=oos_start，
           且其桶在注入的 klines factor 覆蓋內 → 若洩漏則 report 必變）。

    斷言：兩次經真 register 持久化的 manifest[demo_residual_alpha_report_hash]
    **byte-identical**。bridge 正確 carve-out → out-trip 不進 residual → 兩 hash 相等。
    若 bridge 把 rts_all 餵進 evaluate_cell / 窗口 bucketing（E2 指定的 mutation），
    run B 的 report 含極端值 → hash 改變 → 本測 FAIL（T3 抓不到此 mutation）。
    """
    in_rts = _in_oos_round_trips()
    btc = _btc_klines_4h()  # 覆蓋非 OOS（桶~10-19）+ OOS 區（桶 100/101）
    out_rts = [
        # exit>=oos_start，桶 floor=100*BUCKET / 101*BUCKET，皆在 btc factor 覆蓋內。
        {"entry_ts": _OOS_START_EPOCH, "exit_ts": _OOS_START_EPOCH + 600.0, "net_bps": 9999.0},
        {"entry_ts": _OOS_START_EPOCH + _BUCKET, "exit_ts": _OOS_START_EPOCH + _BUCKET + 600.0, "net_bps": -9999.0},
    ]
    cap_a = _drive_full_bridge_capture_manifest(loaded_round_trips=in_rts, btc_klines=btc)
    cap_b = _drive_full_bridge_capture_manifest(loaded_round_trips=in_rts + out_rts, btc_klines=btc)

    assert cap_a["register_err"] is None, cap_a["register_err"]
    assert cap_b["register_err"] is None, cap_b["register_err"]
    hash_a = cap_a["manifest_persisted"][REGISTRY_RESIDUAL_ALPHA_HASH_FIELD]
    hash_b = cap_b["manifest_persisted"][REGISTRY_RESIDUAL_ALPHA_HASH_FIELD]
    # 載入含極端 out-trip 不改變註冊的 residual hash（carve-out 真正生效）。
    assert hash_a == hash_b, (hash_a, hash_b)
    # 並夾死「該 hash 確為非 OOS-only report 的 canonical sha256」（byte-identical
    # 到由非 OOS trip 算出的 report，經 bridge 自己的 _canonical_sha256）。
    expected = bridge._canonical_sha256(
        cap_a["manifest_persisted"][RESIDUAL_ALPHA_REPORT_FIELD]
    )
    assert hash_a == expected, (hash_a, expected)


def test_t11_med2_non_bucket_aligned_oos_start_no_overlap_and_klines_clamped():
    """MED-2（factor-side 邊界洩漏）：oos_start **非 4h 桶對齊**時——

    (1) 傳給 load_btc_klines 的 end_ts <= oos_start（klines 載入 strictly 夾止）。
    (2) aligned 集無任何桶 b 滿足 b+bucket_sec>oos_start——以註冊的
        candidate_window_end（= eval_buckets[-1]+bucket_sec，aligned 最大桶的尾端）
        <= oos_start 證明（sorted aligned 的最大桶滿足 ⇒ 全部滿足）。

    構造：一筆 in-trip exit 落在邊界桶 100（< oos_start 仍屬非 OOS，carve-out 保留），
    但桶 100 的尾端 101*BUCKET > oos_start → MED-2 part-(b) 必把桶 100 逐出 aligned，
    故 candidate_window_end <= oos_start（= 100*BUCKET，桶 99 尾端）。
    """
    oos_start_epoch = 100.0 * _BUCKET + 5000.0  # 非 4h 對齊（5000s into 桶 100）
    oos_start = datetime.fromtimestamp(oos_start_epoch, tz=timezone.utc)
    data_end = datetime.fromtimestamp(oos_start_epoch + 30 * _BUCKET, tz=timezone.utc)
    # in-trips 跨桶 10..19 + 一筆落在邊界桶 100（exit<oos_start，非 OOS）。
    in_rts = _in_oos_round_trips()
    in_rts.append(
        {"entry_ts": 100.0 * _BUCKET + 500.0, "exit_ts": 100.0 * _BUCKET + 1000.0, "net_bps": 1.0}
    )
    btc = _btc_klines_4h()  # 覆蓋桶 ~9..138（含桶 100/101 factor）

    cap = _drive_full_bridge_capture_manifest(
        loaded_round_trips=in_rts, btc_klines=btc,
        oos_start=oos_start, data_end=data_end,
    )
    assert cap["register_err"] is None, cap["register_err"]
    # (1) klines 載入終點夾到 <= oos_start。
    end_epoch = cap["klines_end_ts"].timestamp()
    assert end_epoch <= oos_start_epoch, (end_epoch, oos_start_epoch)
    # (2) aligned 最大桶尾端（candidate_window_end）<= oos_start → 無桶跨 OOS。
    cand_end_iso = cap["manifest_persisted"]["hidden_oos_state"]["candidate_window_end"]
    cand_end_epoch = datetime.fromisoformat(cand_end_iso).timestamp()
    assert cand_end_epoch <= oos_start_epoch, (cand_end_epoch, oos_start_epoch)
    # 邊界桶 100（尾端 101*BUCKET>oos_start）確被逐出 → 不可能落在 [oos_start 前一桶] 之後。
    assert cand_end_epoch <= 100.0 * _BUCKET, cand_end_epoch


def test_t11b_med2_filter_emptying_aligned_fails_closed():
    """MED-2 fail-closed：若桶過濾把 aligned 清空（全部桶尾端跨 OOS）→ 不註冊，
    回 insufficient_aligned_buckets（不送非法/洩漏窗去撞 register）。

    構造：所有 in-trip 都落在 oos_start 前同一桶內、且該桶尾端跨 OOS（oos_start
    非桶對齊，桶 floor 在 oos_start 前但 floor+bucket_sec>oos_start）→ 過濾後空。
    """
    oos_start_epoch = 50.0 * _BUCKET + 3000.0  # 非對齊；桶 floor=50*BUCKET
    oos_start = datetime.fromtimestamp(oos_start_epoch, tz=timezone.utc)
    data_end = datetime.fromtimestamp(oos_start_epoch + 30 * _BUCKET, tz=timezone.utc)
    # 全部 in-trip exit 落在桶 50 內（< oos_start），桶 50 尾端 51*BUCKET>oos_start。
    in_rts = [
        {"entry_ts": 50.0 * _BUCKET + 100.0, "exit_ts": 50.0 * _BUCKET + 200.0 + i, "net_bps": 1.0}
        for i in range(5)
    ]
    btc = _btc_klines_4h()
    cap = _drive_full_bridge_capture_manifest(
        loaded_round_trips=in_rts, btc_klines=btc,
        oos_start=oos_start, data_end=data_end,
    )
    # bridge fail-closed（過濾後 aligned 空），register 從未被呼到。
    assert cap["bridge_result"] is None
    assert cap["bridge_err"] == "insufficient_aligned_buckets"
    assert "manifest_persisted" not in cap


def test_t12_med3_sealed_embargo_equals_evaluate_cell_purge():
    """MED-3（embargo 對齊）：封存進 manifest 的 embargo_seconds == evaluate_cell
    residual 計算實際用的 embargo_gap（兩邊各自獨立 derive，斷言相等），eb>=1。

    bridge 與 evaluate_cell 公式對齊後（eb>0 → (eb+0.5)*bs；eb=0 → 0），任一 eb>=1
    下兩者必相等。逐 eb 驗。
    """
    in_rts = _in_oos_round_trips()
    btc = _btc_klines_4h()
    for eb in (1, 2, 3):
        cap = _drive_full_bridge_capture_manifest(
            loaded_round_trips=in_rts, btc_klines=btc, embargo_buckets=eb,
        )
        assert cap["register_err"] is None, (eb, cap["register_err"])
        sealed_embargo = cap["manifest_persisted"]["hidden_oos_state"]["embargo_seconds"]
        # evaluate_cell 實際 purge（與 build_bucketed_residual_report :365 同源）：
        purge_used = int(round((eb + 0.5) * _BUCKET)) if eb > 0 else 0
        # 注：sealed 值是 int(round(...))；evaluate_cell 的 embargo_gap 在 R-1 內以
        # 浮點 (eb+0.5)*bs 使用，兩者描述同一 purge；此處比對封存整數秒 == 由相同
        # 公式 derive 的整數秒（MED-3 要求兩邊 byte-精確相等的對賬量）。
        assert sealed_embargo == purge_used, (eb, sealed_embargo, purge_used)

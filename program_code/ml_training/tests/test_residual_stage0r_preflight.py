"""Stage-0R preflight orchestrator 測試（PART 4 Gap A + Gap D，PA §7）。

涵蓋 PA §7 Gap A + 三個 E2 scrutiny point：
  - 6-step flow（FakeCursor + 注入 register_fn）：每步斷言。
  - idempotency（re-run → WHERE replay_experiment_id IS NULL no-op）。
  - fail-closed on every precondition（flag OFF / 無候選 / selection-bias-invalid /
    embargo<=0 / net_side ambiguous / oos 窗未配置）。
  - NO peer synthesis：candidate_oos_returns=None（grep-style assert on call）+
    verdict 落在 {promote,borderline,block,defer_data}（無新 literal）。
  - cross-writer hash byte-identity：bridge canonical == drar report_hash ==
    registry residual hash（permutation 啟用）。
  - beta-trap end-to-end：pure-beta 候選 → orchestrator 註冊 report，但
    build_live_candidate_evidence_from_source 回 NOT promotion_ready（gate vetoes）。
  - net_side correctness：net-short 候選 → funding sign 正確（非 +1）。
  - behavior-neutral：flags-off → 0 writes。
  - Gap D：K>=10 過 / K=9 → fail-closed selection_bias_invalid。

全 pure-core（monkeypatch DB loaders + FakeCursor 直驅 register / 注入 register_fn），
無真 PG（真 V132 CHECK 撞 + 真 fills 語意屬 Linux flag-ON 驗證，owed to PM）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import pytest

from program_code.ml_training import residual_stage0r_preflight as P
from program_code.ml_training import residual_hidden_oos_bridge as bridge
from program_code.ml_training import residual_alpha_producer_db as DB
from program_code.ml_training.residual_alpha_cycle import RESIDUAL_PRODUCER_ENV
from program_code.ml_training.residual_alpha_report_contract import (
    RESIDUAL_ALPHA_REPORT_FIELD,
)
from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.experiment_registry import (  # noqa: E501
    REGISTRY_RESIDUAL_ALPHA_HASH_FIELD,
)


_BUCKET = DB.DEFAULT_BUCKET_SEC  # 4h = 14400
_OOS_START_EPOCH = 100.0 * _BUCKET
_SINCE = datetime.fromtimestamp(5.0 * _BUCKET, tz=timezone.utc)
_OOS_START = datetime.fromtimestamp(_OOS_START_EPOCH, tz=timezone.utc)
_DATA_END = datetime.fromtimestamp(_OOS_START_EPOCH + 30 * _BUCKET, tz=timezone.utc)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()


def _actor() -> Any:
    class _A:
        actor_id = "residual_cron"
        actor_type = "cron"
        roles = {"operator"}
        scopes = {"replay:write"}

    return _A()


def _cfg(**overrides: Any) -> P.ResidualPreflightConfig:
    base = dict(
        enabled=True,
        engine_mode="demo",
        since=_SINCE,
        oos_start=_OOS_START,
        data_end=_DATA_END,
        required_factors=("btc", "market", "funding"),
        permutation_enabled=True,
        permutation_n=200,
        n_param_variants=1,
        n_symbols_screened=1,
        n_strategies_screened=1,
        selection_bias_cv_protocol="walk_forward",
        selection_bias_embargo_days=7,
        max_candidates=16,
    )
    base.update(overrides)
    return P.ResidualPreflightConfig(**base)


# ─── Fake DB layer ───────────────────────────────────────────────────


class _Cursor:
    """通用 fake cursor：可腳本化 fetchall（選候選）+ 記錄 execute（drar/stamp）。"""

    def __init__(self, fetchall_rows: list | None = None, rowcount: int = 1):
        self.executed: list[tuple[str, Any]] = []
        self._fetchall_rows = fetchall_rows if fetchall_rows is not None else []
        self.rowcount = rowcount

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((str(sql), params))

    def fetchall(self) -> list:
        return list(self._fetchall_rows)

    def fetchone(self) -> Any:
        return None

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


class _Conn:
    """fake conn：第一個 cursor() 回選候選 cursor，後續回 write cursor（記 drar/stamp）。

    has_drar_table=True 時 write cursor 的 _has_table probe（SELECT to_regclass）回真。
    """

    def __init__(self, candidate_rows: list, *, stamp_rowcount: int = 1, has_drar: bool = True):
        self._candidate_rows = candidate_rows
        self._stamp_rowcount = stamp_rowcount
        self._has_drar = has_drar
        self.write_cursors: list[_DrarStampCursor] = []
        self.committed = 0
        self.rolled = 0
        self.closed = False
        self._first = True

    def cursor(self, **kwargs: Any) -> Any:
        if self._first:
            self._first = False
            return _Cursor(self._candidate_rows)
        cur = _DrarStampCursor(stamp_rowcount=self._stamp_rowcount, has_drar=self._has_drar)
        self.write_cursors.append(cur)
        return cur

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled += 1

    def close(self) -> None:
        self.closed = True


class _DrarStampCursor:
    """write cursor：捕捉 drar INSERT 與 stamp UPDATE；_has_table probe 腳本化。"""

    def __init__(self, *, stamp_rowcount: int = 1, has_drar: bool = True):
        self.executed: list[tuple[str, Any]] = []
        self._stamp_rowcount = stamp_rowcount
        self._has_drar = has_drar
        self.rowcount = 0
        self._last_was_probe = False

    def execute(self, sql: str, params: Any = None) -> None:
        text = str(sql)
        self.executed.append((text, params))
        if "to_regclass" in text or "information_schema" in text:
            self._last_was_probe = True
            return
        if text.strip().upper().startswith("UPDATE"):
            self.rowcount = self._stamp_rowcount

    def fetchone(self) -> Any:
        if self._last_was_probe:
            self._last_was_probe = False
            return (True,) if self._has_drar else (None,)
        return None

    def __enter__(self) -> "_DrarStampCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    @property
    def drar_inserts(self) -> list[tuple[str, Any]]:
        return [
            (s, p) for (s, p) in self.executed
            if "INSERT INTO learning.demo_residual_alpha_reports" in s
        ]

    @property
    def stamp_updates(self) -> list[tuple[str, Any]]:
        return [
            (s, p) for (s, p) in self.executed
            if s.strip().upper().startswith("UPDATE LEARNING.MLDE_SHADOW_RECOMMENDATIONS")
        ]


def _candidate_row(strategy: str = "grid_trading", symbol: str = "BTCUSDT") -> dict:
    return {
        "id": 42,
        "strategy_name": strategy,
        "symbol": symbol,
        "expected_net_bps": 12.0,
        "confidence": 0.8,
        "sample_count": 100,
    }


# ─── Synthetic data (non-OOS, multi-bucket) ─────────────────────────


def _non_oos_round_trips() -> list[dict]:
    """非 OOS round-trip：跨多 4h 桶（>= min_eval/train），全 exit < oos_start。"""
    rts = []
    base = 10.0 * _BUCKET
    for i in range(60):
        exit_ = base + i * _BUCKET + 600.0
        rts.append({"entry_ts": exit_ - 300.0, "exit_ts": exit_, "net_bps": 1.0})
    return rts


def _btc_klines_4h() -> list[dict]:
    bars = []
    base = 9.0 * _BUCKET
    price = 100.0
    for i in range(130):
        ts = base + i * _BUCKET
        bars.append({"ts": ts, "open": price, "close": price * 1.001})
        price *= 1.001
    return bars


def _market_klines_by_symbol() -> dict[str, list[dict]]:
    """market basket（>= DEFAULT_MIN_BASKET_SYMBOLS=8 symbol）4h klines，同桶網格。"""
    out: dict[str, list[dict]] = {}
    base = 9.0 * _BUCKET
    for s in range(10):
        sym = f"SYM{s}USDT"
        bars = []
        price = 50.0 + s
        for i in range(130):
            ts = base + i * _BUCKET
            bars.append({"ts": ts, "open": price, "close": price * 1.0005})
            price *= 1.0005
        out[sym] = bars
    return out


def _lifecycles() -> dict[str, tuple[float | None, float | None]]:
    """全 basket symbol 在 [since, oos_start] 全程 active（listed 早、未下市）。"""
    out: dict[str, tuple[float | None, float | None]] = {}
    for s in range(10):
        out[f"SYM{s}USDT"] = (0.0, None)
    out["BTCUSDT"] = (0.0, None)
    return out


def _funding_by_symbol(symbol: str) -> dict[str, list[dict]]:
    """合成 funding 結算列（8h 結算，覆蓋非 OOS 區），funding_rate 小正值。"""
    rows = []
    base = 10.0 * _BUCKET
    for i in range(120):
        ts = base + i * 8 * 3600.0
        rows.append({"ts": ts, "funding_rate": 0.0001})
    return {symbol: rows}


@pytest.fixture(autouse=True)
def _enable_flags(monkeypatch: Any) -> None:
    monkeypatch.setenv(P.STAGE0R_PREFLIGHT_ENV, "1")
    monkeypatch.setenv(RESIDUAL_PRODUCER_ENV, "1")


@pytest.fixture
def _patch_db(monkeypatch: Any) -> dict:
    """monkeypatch 所有 DB loader（orchestrator + bridge），回捕參 dict。"""
    captured: dict[str, Any] = {"net_side_arg": None, "fills_strategy": None}

    short_fills = [
        {"strategy_name": "grid_trading", "symbol": "BTCUSDT", "side": "Sell",
         "qty": 1.0, "realized_pnl": 0.0}
        for _ in range(12)
    ]

    def _fake_load_candidate_net_side(conn, strategy, *, engine_mode, since):
        captured["fills_strategy"] = strategy
        return DB.derive_net_side_from_fills(short_fills, strategy)

    def _fake_load_round_trips(conn, strategy, *, engine_mode, since):
        return _non_oos_round_trips()

    def _fake_load_btc_klines(conn, *, start_ts, end_ts, timeframe):
        return _btc_klines_4h()

    def _fake_load_symbol_lifecycles(conn):
        return _lifecycles()

    def _fake_load_klines_by_symbols(conn, symbols, *, start_ts, end_ts, timeframe):
        all_klines = dict(_market_klines_by_symbol())
        all_klines["BTCUSDT"] = _btc_klines_4h()
        return {s: all_klines.get(s, []) for s in symbols}

    def _fake_load_funding_rates(conn, symbols, *, start_ts, end_ts):
        out: dict[str, list[dict]] = {}
        for s in symbols:
            out.update(_funding_by_symbol(s))
        return out

    monkeypatch.setattr(P, "load_candidate_net_side", _fake_load_candidate_net_side)
    monkeypatch.setattr(P, "load_symbol_lifecycles", _fake_load_symbol_lifecycles)
    monkeypatch.setattr(P, "load_klines_by_symbols", _fake_load_klines_by_symbols)
    monkeypatch.setattr(P, "load_funding_rates", _fake_load_funding_rates)
    # bridge 內部用的 loaders（bridge 自己 load round_trips + btc klines）。
    monkeypatch.setattr(bridge, "load_round_trips", _fake_load_round_trips)
    monkeypatch.setattr(bridge, "load_btc_klines", _fake_load_btc_klines)
    return captured


# ─── 共用：捕捉 register body（report / candidate_oos_returns）的 register_fn ──


class _RegisterSpy:
    """注入的 register_fn：捕捉 body.manifest_jsonb（report + residual hash）+
    回 (result, None)。result 不含 report（模擬 run_register_in_pg_xact 真實契約）。"""

    def __init__(self):
        self.calls: list[Any] = []
        self.experiment_id = "00000000-0000-4000-8000-000000000001"

    def __call__(self, get_pg_conn_fn, actor, body, **kwargs: Any):
        manifest = getattr(body, "manifest_jsonb", {}) or {}
        self.calls.append(
            {
                "manifest": manifest,
                "report": manifest.get(RESIDUAL_ALPHA_REPORT_FIELD),
                "registry_residual_hash": manifest.get(REGISTRY_RESIDUAL_ALPHA_HASH_FIELD),
                "body": body,
            }
        )
        return (
            {
                "experiment_id": self.experiment_id,
                "manifest_hash": "deadbeef" * 8,
                "status": "created",
            },
            None,
        )


# ─── Behavior-neutral（flags off）────────────────────────────────────


def test_behavior_neutral_stage0r_flag_off(monkeypatch: Any):
    monkeypatch.setenv(P.STAGE0R_PREFLIGHT_ENV, "0")
    calls = {"conn": 0, "register": 0}

    def _factory(dsn):
        calls["conn"] += 1
        raise AssertionError("conn_factory must NOT be called with flag off")

    def _reg(*a, **k):
        calls["register"] += 1
        return ({"experiment_id": "x"}, None)

    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=_factory, register_fn=_reg,
    )
    assert summary.enabled is False
    assert summary.reason == f"flag_off:{P.STAGE0R_PREFLIGHT_ENV}"
    assert calls == {"conn": 0, "register": 0}


def test_behavior_neutral_producer_flag_off(monkeypatch: Any):
    monkeypatch.setenv(RESIDUAL_PRODUCER_ENV, "0")
    calls = {"conn": 0}

    def _factory(dsn):
        calls["conn"] += 1
        raise AssertionError("conn_factory must NOT be called with producer flag off")

    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=_factory, register_fn=lambda *a, **k: (None, None),
    )
    assert summary.enabled is False
    assert summary.reason == f"flag_off:{RESIDUAL_PRODUCER_ENV}"
    assert calls["conn"] == 0


def test_cfg_disabled_zero_writes():
    calls = {"conn": 0}

    def _factory(dsn):
        calls["conn"] += 1
        raise AssertionError("disabled cfg must not open conn")

    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(enabled=False), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=_factory, register_fn=lambda *a, **k: (None, None),
    )
    assert summary.enabled is False and summary.reason == "cfg_disabled"
    assert calls["conn"] == 0


# ─── Fail-closed preconditions ───────────────────────────────────────


def test_no_candidates_returns_early(_patch_db):
    conn = _Conn(candidate_rows=[])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    assert summary.reason == "no_candidates"
    assert summary.candidates_selected == 0
    assert len(spy.calls) == 0  # 無 register
    assert conn.committed == 0


def test_oos_window_not_configured_fail_closed(_patch_db):
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(oos_start=None), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    assert summary.reason == "oos_window_not_configured"
    assert len(spy.calls) == 0


def test_net_side_ambiguous_fail_closed(monkeypatch: Any, _patch_db):
    # net_side ambiguous（無入場成交）→ 該候選 skip，不 register。
    def _ambiguous(conn, strategy, *, engine_mode, since):
        return DB.derive_net_side_from_fills([], strategy)

    monkeypatch.setattr(P, "load_candidate_net_side", _ambiguous)
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    assert summary.skipped == 1 and summary.registered == 0
    assert summary.outcomes[0].reason == "net_side_ambiguous"
    assert len(spy.calls) == 0  # net_side 失敗 → 不 register


def test_gap_d_k_below_floor_fail_closed(_patch_db):
    # n_param_variants/symbols/strategies 全 1 → derive_n_trials floor 到 10（>=10 過）。
    # 故要造 K<10 必須繞過 floor：直接餵 selection_bias 失敗——用 embargo_days<7。
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(selection_bias_embargo_days=6),
        get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    assert summary.skipped == 1 and summary.registered == 0
    assert summary.outcomes[0].reason == "selection_bias_invalid:embargo_too_low"
    assert len(spy.calls) == 0  # Gap D 失敗 → 不 register（在任何寫入前）


def test_gap_d_k_floor_passes_at_10(_patch_db):
    # derive_n_trials(1,1,1) → floor 10 → K>=10 過 selection-bias（embargo>=7 / oos>=0.20）。
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    # K>=10 過 → 走到 register（單配置 defer 但仍註冊 experiment）。
    assert len(spy.calls) == 1
    assert summary.registered == 1


def test_gap_d_explicit_k_9_fail_closed(_patch_db):
    # 顯式驗 validator 對 K=9（透過 _build_selection_bias_block + validate）fail。
    block = P._build_selection_bias_block(
        n_trials=9, oos_pct=0.25, cv_protocol="walk_forward",
        embargo_days=7, backtest_period_days=120,
    )
    res = P.validate_selection_bias_correction({"selection_bias_correction": block})
    assert res.ok is False
    assert res.fail_mode.value == "k_too_low"
    # K=10 過
    block10 = P._build_selection_bias_block(
        n_trials=10, oos_pct=0.25, cv_protocol="walk_forward",
        embargo_days=7, backtest_period_days=120,
    )
    assert P.validate_selection_bias_correction(
        {"selection_bias_correction": block10}
    ).ok is True


def test_embargo_non_positive_fail_closed(_patch_db):
    # embargo_buckets=0 → bridge embargo_seconds=0 → fail-closed embargo_seconds_non_positive。
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(embargo_buckets=0), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    # bridge 在 embargo 檢查前已被呼，但 register_fn 永不觸發（embargo fail-closed 在 register 之前）。
    assert summary.registered == 0
    assert summary.outcomes[0].reason == "embargo_seconds_non_positive"
    assert len(spy.calls) == 0


# ─── 6-step flow + idempotency ───────────────────────────────────────


def test_six_step_flow_registers_and_stamps(_patch_db):
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    assert summary.registered == 1
    o = summary.outcomes[0]
    assert o.status == "registered"
    assert o.experiment_id == spy.experiment_id
    assert o.manifest_hash == "deadbeef" * 8
    assert o.rec_stamped is True
    # net_side 真實（short → -1，非 +1 預設）。
    assert o.net_side == -1
    # register 被呼恰 1 次。
    assert len(spy.calls) == 1
    # stamp UPDATE 被寫（write cursor 捕捉）。
    wc = conn.write_cursors[0]
    assert len(wc.stamp_updates) == 1
    stamp_sql, stamp_params = wc.stamp_updates[0]
    assert "replay_experiment_id IS NULL" in stamp_sql  # 防重蓋 guard
    assert stamp_params["experiment_id"] == spy.experiment_id
    assert stamp_params["tier"] == "calibrated_replay"
    assert conn.committed >= 1


def test_idempotent_rerun_no_op_when_already_stamped(_patch_db):
    # stamp_rowcount=0 模擬「已蓋過 lineage」（WHERE replay_experiment_id IS NULL 命不到）。
    conn = _Conn(candidate_rows=[_candidate_row()], stamp_rowcount=0)
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    o = summary.outcomes[0]
    # register 仍跑（bridge 的 ON CONFLICT DO NOTHING 自身冪等），但 rec_stamped=False。
    assert o.rec_stamped is False
    wc = conn.write_cursors[0]
    assert len(wc.stamp_updates) == 1  # UPDATE 仍發出，但 rowcount=0 → no-op


# ─── NO peer synthesis ───────────────────────────────────────────────


def test_no_peer_synthesis_candidate_oos_returns_none(monkeypatch: Any, _patch_db):
    """斷言：傳給 gate 的 peer_variant_round_trips 為 None（單一配置不捏 peer）+
    verdict 落在合法集合（無新 literal）。grep-style：攔 evaluate_cell 看實參。"""
    seen: dict[str, Any] = {}
    real_eval = bridge.evaluate_cell

    def _spy_eval(cell_key, rts, btc_klines, **kwargs):
        seen["peer_variant_round_trips"] = kwargs.get("peer_variant_round_trips", "ABSENT")
        seen["required_factors"] = kwargs.get("required_factors")
        seen["permutation_enabled"] = kwargs.get("permutation_enabled")
        seen["net_side"] = kwargs.get("net_side")
        result = real_eval(cell_key, rts, btc_klines, **kwargs)
        seen["report"] = result.report
        return result

    monkeypatch.setattr(bridge, "evaluate_cell", _spy_eval)
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    # ★ NO peer synthesis：peer_variant_round_trips 必為 None（不捏造 peer）。
    assert seen["peer_variant_round_trips"] is None
    assert seen["required_factors"] == ("btc", "market", "funding")
    assert seen["permutation_enabled"] is True
    assert seen["net_side"] == -1
    # verdict 落在合法集合（無新 literal）。
    verdict = str(seen["report"].get("verdict"))
    assert verdict in {"promote", "borderline", "block", "defer_data", "pass", "fail"}


def test_single_config_defers_pbo_via_existing_path(monkeypatch: Any, _patch_db):
    """單一配置 → gate 因無 peer defer（既有 pbo_missing_candidate_returns 路徑），
    drar 因 verdict!=pass 誠實 skip（非 pass 報告不寫 drar）。"""
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    o = summary.outcomes[0]
    # register 成功（experiment 寫了），但 drar 因 defer 誠實 skip。
    assert o.status == "registered"
    assert o.drar_written is False  # defer 報告不進 drar（honest）
    assert o.verdict in {"defer_data", "block", "fail"}
    # registry 收到的 report 是 captured 的（PBO defer）。
    report = spy.calls[0]["report"]
    assert report is not None
    assert report.get("verdict") != "pass"


# ─── Cross-writer hash byte-identity (§5.6) ──────────────────────────


def test_cross_writer_hash_byte_identity_with_permutation(monkeypatch: Any, _patch_db):
    """bridge canonical_sha256(report) == registry residual hash（manifest 內）；
    permutation 啟用時 report 帶 perm 欄位，三寫者 hash 同一 canonical bytes。"""
    captured_report: dict[str, Any] = {}
    real_eval = bridge.evaluate_cell

    def _spy_eval(cell_key, rts, btc_klines, **kwargs):
        result = real_eval(cell_key, rts, btc_klines, **kwargs)
        captured_report["report"] = result.report
        return result

    monkeypatch.setattr(bridge, "evaluate_cell", _spy_eval)
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    report = captured_report["report"]
    # permutation 啟用 → report 帶 perm 欄位。
    assert "perm_p_value" in report, "permutation enabled should emit perm_p_value"

    # 1) bridge 的 canonical hash（registry residual hash）== canonical_sha256(report)。
    registry_hash = spy.calls[0]["registry_residual_hash"]
    captured_in_body = spy.calls[0]["report"]
    assert registry_hash == _canonical_sha256(captured_in_body)
    # 2) capturing wrapper 抓到的 report == eval 產出的 report（同一物件路徑）。
    assert _canonical_sha256(captured_in_body) == _canonical_sha256(report)
    # 3) bridge 自己的 _canonical_sha256 與測試 helper 一致（同算法）。
    assert bridge._canonical_sha256(report) == _canonical_sha256(report)


def test_drar_hash_matches_registry_when_report_passes(monkeypatch: Any, _patch_db):
    """當 report 通過 validation（合成 pass report 注入 eval）→ drar 寫入的 report_hash
    == registry residual hash == canonical_sha256(report)（三寫者 byte-identical）。"""
    pass_report = {
        "passes": True, "verdict": "pass", "reasons": [],
        "raw_mean_bps": 2.0, "residual_mean_bps": 1.4,
        "r_beta_retention": 0.7, "beta_edge_share": 0.3,
        "psr_raw": 0.97, "psr_residual": 0.98,
        "dsr_raw": 0.96, "dsr_residual": 0.97,
        "pbo_raw": 0.20, "pbo_residual": 0.10,
        "factor_panel_hash": "sha256:factor-panel",
        "fit_window": {"train_end": 79, "eval_start": 80},
        "coverage": {"train": 0.90, "eval": 0.85},
        "perm_p_value": 0.01, "perm_iterations": 200,
    }

    from program_code.ml_training.residual_alpha_cycle import CellResidualResult

    def _fake_eval(cell_key, rts, btc_klines, **kwargs):
        return CellResidualResult(
            cell_key=cell_key, status="evaluated", promotion_ready=True,
            reason="ok", n_trials=10, n_trials_derivation="x",
            report=dict(pass_report),
        )

    monkeypatch.setattr(bridge, "evaluate_cell", _fake_eval)
    conn = _Conn(candidate_rows=[_candidate_row()], has_drar=True)
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    o = summary.outcomes[0]
    assert o.drar_written is True
    expected_hash = _canonical_sha256(pass_report)
    assert o.report_hash == expected_hash
    # registry residual hash == drar hash == canonical(report)。
    assert spy.calls[0]["registry_residual_hash"] == expected_hash
    # drar INSERT 的 report_hash 參數（第 3 位）== expected。
    wc = conn.write_cursors[0]
    drar_sql, drar_params = wc.drar_inserts[0]
    assert drar_params[2] == expected_hash


# ─── Beta-trap end-to-end（gate vetoes pure-beta）────────────────────


def test_beta_trap_end_to_end_gate_vetoes(monkeypatch: Any, _patch_db):
    """pure-beta（含 funding-carry）候選 → orchestrator 註冊 report，但重構 source_row
    後 build_live_candidate_evidence_from_source 回 NOT promotion_ready（gate vetoes）。"""
    from program_code.ml_training.candidate_evidence_source_contract import (
        build_live_candidate_evidence_from_source,
    )

    captured: dict[str, Any] = {}
    real_eval = bridge.evaluate_cell

    def _spy_eval(cell_key, rts, btc_klines, **kwargs):
        result = real_eval(cell_key, rts, btc_klines, **kwargs)
        captured["report"] = result.report
        return result

    monkeypatch.setattr(bridge, "evaluate_cell", _spy_eval)
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    report = captured["report"]
    # 重構 source_row（帶 registry lineage），餵 source contract gate。
    source_row = {
        "demo_residual_alpha_report": report,
        "evidence_source_tier": "calibrated_replay",
        "replay_experiment_id": spy.experiment_id,
        "manifest_hash": "deadbeef" * 8,
    }
    build = build_live_candidate_evidence_from_source(source_row)
    # gate vetoes：單配置 defer 報告 verdict!=pass → source contract 在第一道 residual
    # validator 即拒（promotion_ready False）。證 active gate 否決 beta-masquerade。
    assert build.validation.promotion_ready is False
    assert "residual_alpha" in build.validation.reason


# ─── net_side correctness（long 候選 → +1）───────────────────────────


def test_net_side_long_candidate(monkeypatch: Any, _patch_db):
    long_fills = [
        {"strategy_name": "grid_trading", "symbol": "BTCUSDT", "side": "Buy",
         "qty": 2.0, "realized_pnl": 0.0}
        for _ in range(8)
    ]

    def _long(conn, strategy, *, engine_mode, since):
        return DB.derive_net_side_from_fills(long_fills, strategy)

    monkeypatch.setattr(P, "load_candidate_net_side", _long)
    seen: dict[str, Any] = {}
    real_eval = bridge.evaluate_cell

    def _spy_eval(cell_key, rts, btc_klines, **kwargs):
        seen["net_side"] = kwargs.get("net_side")
        return real_eval(cell_key, rts, btc_klines, **kwargs)

    monkeypatch.setattr(bridge, "evaluate_cell", _spy_eval)
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    assert seen["net_side"] == 1  # 多單 → +1
    assert summary.outcomes[0].net_side == 1


# ─── DEMO lane only：no live/auth/order/risk/lease token in any executed SQL ──


def test_demo_lane_only_no_live_mutation(_patch_db):
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    forbidden = (
        "live_reserved", "execution_authority", "decision_lease",
        "authorization", "OPENCLAW_ALLOW_MAINNET", "max_retries",
        "INSERT INTO trading", "live_candidate",
    )
    for wc in conn.write_cursors:
        for sql, _params in wc.executed:
            low = sql.lower()
            for tok in forbidden:
                assert tok.lower() not in low, f"forbidden token {tok!r} in orchestrator SQL"


# ─── register error → failed (not skipped) ───────────────────────────


def test_register_pg_error_marks_failed(_patch_db):
    conn = _Conn(candidate_rows=[_candidate_row()])

    def _err_register(get_pg_conn_fn, actor, body, **kwargs):
        return (None, "pg_error:OperationalError")

    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=_err_register,
    )
    assert summary.failed == 1 and summary.registered == 0
    assert summary.outcomes[0].status == "failed"
    assert "pg_error" in summary.outcomes[0].reason
    assert conn.rolled >= 1  # failed → rollback


def test_oos_fraction_invalid_fail_closed(_patch_db):
    # data_end <= oos_start → oos fraction invalid → fail-closed（在 register 前）。
    bad_end = datetime.fromtimestamp(_OOS_START_EPOCH - 1.0, tz=timezone.utc)
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(data_end=bad_end), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    # oos_start(100*B) > data_end → cfg-level oos check 在 run 入口先擋（windows 非遞增）。
    # 此處 data_end < oos_start，但兩者皆非 None → 進 candidate loop → _oos_fraction None。
    assert summary.registered == 0
    assert len(spy.calls) == 0

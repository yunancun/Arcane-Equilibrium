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

    def _fake_load_candidate_net_side(conn, strategy, *, symbol=None, engine_mode, since):
        captured["fills_strategy"] = strategy
        return DB.derive_net_side_from_fills(short_fills, strategy, symbol)

    def _fake_load_round_trips(conn, strategy, *, engine_mode, since):
        return _non_oos_round_trips()

    def _fake_load_btc_klines(conn, *, start_ts, end_ts, timeframe):
        return _btc_klines_4h()

    def _fake_load_symbol_lifecycles(conn):
        return _lifecycles()

    def _fake_load_liquid_basket_symbols(
        conn, candidate_symbols, *, start_ts, end_ts, timeframe, limit
    ):
        # 模擬流動性選取：從 PIT-active candidate 中挑「窗內有 klines」者（=合成
        # market basket 的 SYM*USDT + BTCUSDT），按 limit 截斷。回有資料的 symbol。
        with_data = set(_market_klines_by_symbol().keys()) | {"BTCUSDT"}
        picked = [s for s in candidate_symbols if s in with_data]
        return picked[: int(limit)]

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
    monkeypatch.setattr(P, "load_liquid_basket_symbols", _fake_load_liquid_basket_symbols)
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
    def _ambiguous(conn, strategy, *, symbol=None, engine_mode, since):
        return DB.derive_net_side_from_fills([], strategy, symbol)

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
    # ★ HIGH-1：同一 stamp UPDATE 必把 report 寫進 payload.demo_residual_alpha_report
    #   （否則下游 source contract 第一道死在 not_dict = defer-by-absence）。
    assert "jsonb_set" in stamp_sql
    assert "demo_residual_alpha_report" in stamp_sql
    assert "report_jsonb" in stamp_params
    # payload 寫入的 report == bridge 送進 registry 的同一份（hash byte-identity）。
    written_report = json.loads(stamp_params["report_jsonb"])
    assert written_report == spy.calls[0]["report"]
    assert _canonical_sha256(written_report) == spy.calls[0]["registry_residual_hash"]
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


def _production_shape_source_row(
    *,
    payload: dict[str, Any],
    experiment_id: str = "00000000-0000-4000-8000-000000000001",
    manifest_hash: str = "deadbeef" * 8,
) -> dict[str, Any]:
    """重建 production fetch（mlde_demo_applier_evidence_filter.fetch_pending_sql_and_params）
    SELECT 出來的 row shape：lineage 欄 + payload（**無** top-level demo_residual_alpha_report
    欄；production SELECT 根本沒有該欄，report 只能從 payload 取）。

    為什麼這是 HIGH-1 的真實證明：先前測試在 top-level 手放 report，遮蔽了「orchestrator
    從沒寫 payload」這個真 bug。改用 production shape 後，report 必須來自 orchestrator
    實際寫的 payload，gate 的判據才是 report 的 math（非手放的假象）。
    drar / hidden_oos / registry snapshot 等下游欄全留 None（缺 → 下游各 gate fail-closed），
    但本 e2e 只證**第一道** residual validator 的反應（not_dict vs 真 math reason）。
    """
    return {
        "id": 42,
        "engine_mode": "demo",
        "strategy_name": "grid_trading",
        "symbol": "BTCUSDT",
        "expected_net_bps": 12.0,
        "confidence": 0.8,
        "sample_count": 100,
        "evidence_source_tier": "calibrated_replay",
        "replay_experiment_id": experiment_id,
        "manifest_hash": manifest_hash,
        # 下游 registry / durable / hidden_oos snapshot 欄（production LEFT JOIN，
        # drar/registry 未 populate 時為 None）——本 e2e 不驗下游，留 None。
        "replay_registry_manifest_hash": None,
        "replay_registry_status": None,
        "replay_registry_expires_at": None,
        "replay_registry_manifest_jsonb": None,
        "durable_residual_alpha_report_hash": None,
        "durable_residual_alpha_report_jsonb": None,
        "durable_hidden_oos_state": None,
        "durable_hidden_oos_state_jsonb": None,
        "payload": payload,
    }


def test_beta_trap_end_to_end_gate_vetoes(monkeypatch: Any, _patch_db):
    """HIGH-1 的真實證明：pure-beta（單配置 defer）候選 → orchestrator 把 report 寫進
    **payload**（非 top-level）→ production-shape source_row 餵 source contract → 第一道
    residual validator 回真實 **math reason**（passes_not_true，因 defer report passes=False），
    **非** not_dict（=defer-by-absence 換名）。並對照「若 payload 不帶 report」→ not_dict，
    證 math 才是 deciding factor。"""
    from program_code.ml_training.candidate_evidence_source_contract import (
        build_live_candidate_evidence_from_source,
    )

    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    o = summary.outcomes[0]
    assert o.status == "registered"
    # ★ 取 orchestrator **實際寫進 payload 的 report**（stamp UPDATE 的 report_jsonb 參數），
    #   非手放。這是 production 路徑：orchestrator UPDATE payload → fetch 讀回 → source contract。
    wc = conn.write_cursors[0]
    stamp_sql, stamp_params = wc.stamp_updates[0]
    # 綁定：stamp SQL 必真把 report 寫進 payload（否則 production 的 fetch 取不到 report，
    # 本 e2e 讀 params 會給假象）。jsonb_set 缺失 → 此 e2e 也紅（與 six-step 同向 bite）。
    assert "jsonb_set" in stamp_sql and "demo_residual_alpha_report" in stamp_sql
    written_report = json.loads(stamp_params["report_jsonb"])
    # 該 report 是真實單配置 defer（passes=False；PBO 無 peer → defer_data）。
    assert written_report.get("passes") is False
    assert written_report.get("verdict") in {"defer_data", "block", "fail"}

    # (A) production shape：report 在 payload（orchestrator 寫的那份）。
    row_with_payload = _production_shape_source_row(
        payload={RESIDUAL_ALPHA_REPORT_FIELD: written_report},
    )
    build = build_live_candidate_evidence_from_source(row_with_payload)
    assert build.validation.promotion_ready is False
    # ★ 關鍵斷言：reason 是 report math（passes_not_true），**非** not_dict（absence）。
    #   驗 math 是 deciding factor，beta-masquerade 被真實 verdict 否決（非缺席默拒）。
    assert build.validation.reason == "residual_alpha:passes_not_true"
    assert build.validation.reason != "residual_alpha:not_dict"

    # (B) 對照組：payload **不帶** report（=HIGH-1 修復前 orchestrator 的真實狀態）→
    #     source contract 死在 not_dict（defer-by-absence）。證 (A) 的差異全來自 payload
    #     是否帶 report，亦即修復確實把判據從「缺席」改成「math verdict」。
    row_no_report = _production_shape_source_row(payload={})
    build_absent = build_live_candidate_evidence_from_source(row_no_report)
    assert build_absent.validation.promotion_ready is False
    assert build_absent.validation.reason == "residual_alpha:not_dict"


def test_pass_report_in_payload_passes_first_gate(monkeypatch: Any, _patch_db):
    """PASS 候選：orchestrator 把 PASS report 寫進 payload → production-shape source_row
    過 source contract 的**第一道** residual validator（不再卡 residual_alpha:*）→ 推進到
    下游 lineage gate。證修復後 PASS 候選的 math 確實能成為 deciding factor（durable/
    hidden_oos gate 可達），而非一律死在第一道。"""
    from program_code.ml_training.candidate_evidence_source_contract import (
        build_live_candidate_evidence_from_source,
    )
    from program_code.ml_training.residual_alpha_cycle import CellResidualResult

    # 合成一份「過第一道 validator」的 PASS report（math 全達標 + permutation）。
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
    assert o.status == "registered"
    assert o.drar_written is True  # PASS report → drar 寫入
    # 取 orchestrator 寫進 payload 的 PASS report。
    wc = conn.write_cursors[0]
    stamp_sql, stamp_params = wc.stamp_updates[0]
    assert "jsonb_set" in stamp_sql and "demo_residual_alpha_report" in stamp_sql
    written_report = json.loads(stamp_params["report_jsonb"])
    assert written_report.get("verdict") == "pass"

    row = _production_shape_source_row(
        payload={RESIDUAL_ALPHA_REPORT_FIELD: written_report},
    )
    build = build_live_candidate_evidence_from_source(row)
    # 仍 NOT promotion_ready（下游 registry/hidden_oos snapshot 在本 e2e 未 populate），
    # 但**關鍵**：reason 已**不是** residual_alpha:*（第一道過了），推進到下游 lineage gate。
    assert build.validation.promotion_ready is False
    assert not build.validation.reason.startswith("residual_alpha:"), (
        f"PASS report should clear first residual gate, got {build.validation.reason!r}"
    )
    # 下游卡點是 registry snapshot（manifest_hash 對得上但 registry_manifest_hash None）。
    assert build.validation.reason.startswith(
        ("replay_registry", "source_replay", "evidence_source_tier")
    ), build.validation.reason


def test_low3_deterministic_idempotency_key_set_on_body(_patch_db):
    """LOW-3：register body 帶 deterministic idempotency_key（從 family_id + split_hash
    衍生），縮小 crash-retry 重複 replay.experiments 窗。同候選同窗 → 同 key（穩定）。"""
    conn = _Conn(candidate_rows=[_candidate_row()])
    spy = _RegisterSpy()
    P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    body = spy.calls[0]["body"]
    key = getattr(body, "idempotency_key", None)
    assert key, "register body must carry a deterministic idempotency_key (LOW-3)"
    assert key.startswith("residual_stage0r:grid_trading::BTCUSDT:")
    assert len(key) <= 128
    # 穩定性：再跑一次同候選同 cfg → 同 key（split_hash 由窗決定，確定性）。
    conn2 = _Conn(candidate_rows=[_candidate_row()])
    spy2 = _RegisterSpy()
    P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn2, register_fn=spy2,
    )
    assert getattr(spy2.calls[0]["body"], "idempotency_key", None) == key


# ─── net_side correctness（long 候選 → +1）───────────────────────────


def test_net_side_long_candidate(monkeypatch: Any, _patch_db):
    long_fills = [
        {"strategy_name": "grid_trading", "symbol": "BTCUSDT", "side": "Buy",
         "qty": 2.0, "realized_pnl": 0.0}
        for _ in range(8)
    ]

    def _long(conn, strategy, *, symbol=None, engine_mode, since):
        return DB.derive_net_side_from_fills(long_fills, strategy, symbol)

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


# ─── HIGH-2：net_side 必須逐 (strategy, symbol)（funding sign 反號修復）──────


def test_net_side_per_symbol_overrides_strategy_wide_short():
    """★ MIT HIGH-2：策略整體淨 short、但候選 symbol 上淨 long → 必須回 per-symbol
    的 +1，**不是** strategy-wide 的 -1。

    重現 MIT 實測的 RAVEUSDT 發散：grid_trading 全域淨 short（BTCUSDT 大量 Sell），
    但 RAVEUSDT 上淨 long（Buy）。若 net_side 只按 strategy_name 跨全 symbol 聚合 →
    給 grid_trading::RAVEUSDT 候選 -1，而真實曝險是 +1 → funding factor 反號 → carry
    被放大（= 本功能要消滅的 false-promote 向量）。傳 symbol=RAVEUSDT 後必回 +1。
    """
    fills = [
        # BTCUSDT：大量 Sell（讓 strategy-wide 淨 short）。
        *[
            {"strategy_name": "grid_trading", "symbol": "BTCUSDT", "side": "Sell",
             "qty": 10.0, "realized_pnl": 0.0}
            for _ in range(20)
        ],
        # RAVEUSDT：淨 Buy（per-symbol 淨 long）。
        *[
            {"strategy_name": "grid_trading", "symbol": "RAVEUSDT", "side": "Buy",
             "qty": 3.0, "realized_pnl": 0.0}
            for _ in range(5)
        ],
    ]

    # strategy-wide（symbol=None）：BTCUSDT 大量 Sell 主導 → 淨 short。
    side_all, diag_all = DB.derive_net_side_from_fills(fills, "grid_trading")
    assert side_all == -1
    assert diag_all["ambiguous"] == 0.0

    # per-symbol（symbol=RAVEUSDT）：只算 RAVEUSDT 的 Buy → 淨 long（+1，非 -1）。
    side_sym, diag_sym = DB.derive_net_side_from_fills(
        fills, "grid_trading", "RAVEUSDT"
    )
    assert side_sym == 1  # ★ HIGH-2：per-symbol +1，反轉 strategy-wide -1
    assert diag_sym["entry_fills"] == 5.0  # 只數該 symbol 的入場成交
    assert diag_sym["net_signed_qty"] == 15.0  # 5 × Buy 3.0

    # mutation 守門：若退回 strategy-wide（忽略 symbol）→ 兩者相等 → 此斷言 FAIL。
    assert side_sym != side_all


def test_net_side_per_symbol_no_fills_for_symbol_is_ambiguous():
    """候選 symbol 上無相符入場成交 → ambiguous（fail-closed），不沿用 strategy-wide。

    避免「策略在別的 symbol 有成交、但這個 symbol 沒有」時誤用其他 symbol 的方向。
    """
    fills = [
        {"strategy_name": "grid_trading", "symbol": "BTCUSDT", "side": "Buy",
         "qty": 1.0, "realized_pnl": 0.0}
        for _ in range(8)
    ]
    side, diag = DB.derive_net_side_from_fills(fills, "grid_trading", "RAVEUSDT")
    assert diag["ambiguous"] == 1.0  # 該 symbol 無入場成交 → 不可判
    assert diag["entry_fills"] == 0.0


def test_orchestrator_threads_candidate_symbol_into_net_side(monkeypatch: Any, _patch_db):
    """★ HIGH-2 e2e：orchestrator 必須把候選的 symbol 傳進 load_candidate_net_side，
    使 per-symbol 方向（非 strategy-wide）流到 evaluate_cell 的 net_side。

    候選是 grid_trading::RAVEUSDT；同一批 fills 中 BTCUSDT 淨 short、RAVEUSDT 淨 long。
    斷言 (1) load_candidate_net_side 收到 symbol=RAVEUSDT，(2) 最終 net_side=+1（per-
    symbol），證明若 orchestrator 漏傳 symbol（退回 strategy-wide）會得到 -1 → 此測試紅。
    """
    fills = [
        *[
            {"strategy_name": "grid_trading", "symbol": "BTCUSDT", "side": "Sell",
             "qty": 10.0, "realized_pnl": 0.0}
            for _ in range(20)
        ],
        *[
            {"strategy_name": "grid_trading", "symbol": "RAVEUSDT", "side": "Buy",
             "qty": 3.0, "realized_pnl": 0.0}
            for _ in range(5)
        ],
    ]
    seen_symbol: dict[str, Any] = {}

    def _fake_net_side(conn, strategy, *, symbol=None, engine_mode, since):
        seen_symbol["symbol"] = symbol
        return DB.derive_net_side_from_fills(fills, strategy, symbol)

    monkeypatch.setattr(P, "load_candidate_net_side", _fake_net_side)
    seen: dict[str, Any] = {}
    real_eval = bridge.evaluate_cell

    def _spy_eval(cell_key, rts, btc_klines, **kwargs):
        seen["net_side"] = kwargs.get("net_side")
        return real_eval(cell_key, rts, btc_klines, **kwargs)

    monkeypatch.setattr(bridge, "evaluate_cell", _spy_eval)
    conn = _Conn(candidate_rows=[_candidate_row(symbol="RAVEUSDT")])
    spy = _RegisterSpy()
    summary = P.run_residual_stage0r_preflight(
        "dsn", cfg=_cfg(), get_pg_conn_fn=lambda: None, actor=_actor(),
        conn_factory=lambda dsn: conn, register_fn=spy,
    )
    assert seen_symbol["symbol"] == "RAVEUSDT"  # orchestrator 傳了候選 symbol
    assert seen["net_side"] == 1  # ★ per-symbol +1（漏傳 symbol → strategy-wide -1 → 紅）
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


# ─── Gap A basket selection bug regression（orchestrator 層）─────────────


class _OrchCountCursor:
    """模擬 market.klines GROUP BY count(*) 查詢（_load_multi_factor_inputs 用）。
    只回窗內有 bar 的 symbol（真實 PG GROUP BY 不回 0-bar symbol）。"""

    def __init__(self, bar_counts):
        self._bar_counts = bar_counts

    def execute(self, query, params=None):
        requested = list(params["symbols"])
        limit = int(params["limit"])
        present = [(s, self._bar_counts[s]) for s in requested if s in self._bar_counts]
        present.sort(key=lambda kv: (-kv[1], kv[0]))
        self._last = [{"symbol": s, "bar_count": c} for s, c in present[:limit]]

    def fetchall(self):
        return self._last

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _OrchCountConn:
    def __init__(self, bar_counts):
        self._bar_counts = bar_counts

    def cursor(self, **kw):
        return _OrchCountCursor(self._bar_counts)


def test_load_multi_factor_inputs_selects_data_bearing_not_alphabetical(monkeypatch: Any):
    """★ Gap A bug e2e（orchestrator 真正選取路徑）：當字母序最前的 PIT-active symbol
    無 klines、流動 symbol 有資料時，``_load_multi_factor_inputs`` 必須把**有資料**者
    放進 klines_by_symbol，**絕不**是字母序前綴（舊 ``sorted(active)[:N]`` 會選空 symbol）。

    這條測試**不** patch load_liquid_basket_symbols（與 _patch_db 不同）——刻意走**真**
    選取 seam，否則就是當初漏掉 bug 的同一個盲點（合成注入繞過 DB 選取）。lifecycles 讓
    字母序前綴 symbol 全 PIT-active（舊碼必選它們），但 count 查詢只回流動者 → 證明選取
    已改按資料可得性。
    """
    # 字母序最前 = 冷門無資料 symbol（PIT-active 但 0 bar）；流動者有資料。
    alpha_first_empty = ["0GUSDT", "1000000BABYDOGEUSDT", "1000000CHEEMSUSDT"]
    liquid_bar_counts = {"BTCUSDT": 300, "ETHUSDT": 280, "SOLUSDT": 200}
    # lifecycles：全部（含空 symbol）在 [since, oos_start] 全程 PIT-active（listed 早、未下市）。
    all_syms = alpha_first_empty + list(liquid_bar_counts.keys())
    lifecycles = {s: (0.0, None) for s in all_syms}

    def _fake_lifecycles(conn):
        return lifecycles

    def _fake_klines_by_symbols(conn, symbols, *, start_ts, end_ts, timeframe):
        # 只有流動 symbol 真有 bar；空 symbol 即便被查也回空 list。
        bars = [{"ts": float(i) * _BUCKET, "open": 100.0, "close": 100.1} for i in range(5)]
        return {s: (bars if s in liquid_bar_counts else []) for s in symbols}

    def _fake_funding(conn, symbols, *, start_ts, end_ts):
        return {s: [] for s in symbols}

    monkeypatch.setattr(P, "load_symbol_lifecycles", _fake_lifecycles)
    monkeypatch.setattr(P, "load_klines_by_symbols", _fake_klines_by_symbols)
    monkeypatch.setattr(P, "load_funding_rates", _fake_funding)
    # 注意：**不** patch load_liquid_basket_symbols → 走真選取邏輯。

    conn = _OrchCountConn(liquid_bar_counts)
    inputs = P._load_multi_factor_inputs(conn, symbol="BTCUSDT", cfg=_cfg(max_basket_symbols=60))

    kbs = inputs["klines_by_symbol"]
    assert kbs is not None
    # 核心：選到的 basket = 有資料的流動 symbol，字母序前綴空 symbol 一個都不在。
    assert set(kbs.keys()) == set(liquid_bar_counts.keys())
    for empty_sym in alpha_first_empty:
        assert empty_sym not in kbs
    # 每個入選 symbol 都真有 bar（bars>0）——這正是修復前 market_buckets=0 的根因被消除。
    for sym in liquid_bar_counts:
        assert len(kbs[sym]) > 0
    assert inputs["lifecycles"] == lifecycles
    assert inputs["position_symbols"] == ["BTCUSDT"]

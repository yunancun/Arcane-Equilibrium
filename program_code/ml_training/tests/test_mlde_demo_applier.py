from __future__ import annotations

import pytest

from ml_training.mlde_demo_applier import (
    DemoApplierConfig,
    _ATTRIBUTION_STRATEGY_KEYS,
    _LIVE_CANDIDATE_EVAL_SCHEMA_VERSION,
    _R_META_MIN_SAMPLE_PER_STRATEGY,
    _R_META_WINDOW_DAYS,
    _already_applied,
    _build_live_candidate_payload,
    _compute_attribution_chain_ratio_by_strategy,
    _compute_attribution_sample_count_by_strategy,
    _compute_demo_cost_baseline,
    _compute_demo_realized_window,
    _compute_demo_sample_count_strategy_cell,
    _execute_read_fail_soft,
    _insert_live_candidate,
    _noop_audit_payload,
    _record_application,
    _record_noop_audit,
    build_risk_patch,
    build_strategy_patch,
    should_create_live_candidate,
)
from ml_training.live_candidate_lineage import (
    LIVE_CANDIDATE_LINEAGE_SCHEMA_VERSION,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0)


class _ScriptedCursor:
    """Programmable cursor for LG-5 helper tests.

    Each `execute()` peels one entry from `responses`. Entries are tuples
    that get yielded by subsequent `fetchone()` / `fetchall()` calls. Use
    `None` for queries that ignore their result.

    供 LG-5 helper 測試使用：每次 `execute()` 從 `responses` 取下一筆，
    `fetchone()` / `fetchall()` 回傳該筆內容；不關心回傳結果的查詢用 None。
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self._current = None
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        self._current = self._responses.pop(0) if self._responses else None

    def fetchone(self):
        return self._current

    def fetchall(self):
        # Allow caller to pass a list-of-rows tuple under the same slot.
        # 允許同一 slot 攜帶 list-of-rows，供 fetchall 使用。
        if isinstance(self._current, list):
            return self._current
        return [self._current] if self._current is not None else []


class _RealishPsycopgCursor:
    """Cursor shaped like psycopg2 enough to exercise SAVEPOINT behavior."""

    def __init__(self):
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if "SELECT broken_read" in sql:
            raise RuntimeError("simulated pg read failure")


_RealishPsycopgCursor.__module__ = "psycopg2.extras"


def test_execute_read_fail_soft_rolls_back_to_savepoint_for_real_pg_cursor():
    cur = _RealishPsycopgCursor()

    with pytest.raises(RuntimeError, match="simulated pg read failure"):
        _execute_read_fail_soft(cur, "SELECT broken_read", ())

    executed_sql = [sql for sql, _params in cur.executed]
    assert executed_sql[0].startswith("SAVEPOINT mlde_demo_read_")
    assert executed_sql[1] == "SELECT broken_read"
    assert executed_sql[2].startswith("ROLLBACK TO SAVEPOINT mlde_demo_read_")
    assert executed_sql[3].startswith("RELEASE SAVEPOINT mlde_demo_read_")


def test_grid_dream_spacing_maps_to_bounded_runtime_params():
    cfg = DemoApplierConfig(max_param_delta_pct=0.20)
    patch = build_strategy_patch(
        strategy_name="grid_trading",
        recommendation_type="parameter_proposal",
        payload={
            "param_name": "grid_spacing_bps",
            "suggested_change_pct": 0.50,
            "direction": "widen",
        },
        current_params={"cooldown_ms": 120_000, "max_cooldown_boost": 2.0},
        param_ranges=[
            {
                "name": "cooldown_ms",
                "min": 30_000,
                "max": 600_000,
                "step": 30_000,
                "agent_adjustable": True,
            },
            {
                "name": "max_cooldown_boost",
                "min": 0.0,
                "max": 10.0,
                "step": 0.5,
                "agent_adjustable": True,
            },
        ],
        cfg=cfg,
    )

    assert patch == {"cooldown_ms": 144_000, "max_cooldown_boost": pytest.approx(2.4)}


def test_veto_reduces_conf_scale_without_param_range():
    cfg = DemoApplierConfig(veto_conf_scale_step_pct=0.10, max_param_delta_pct=0.20)
    patch = build_strategy_patch(
        strategy_name="ma_crossover",
        recommendation_type="veto",
        payload={},
        current_params={"conf_scale": 1.0},
        param_ranges=[],
        cfg=cfg,
    )

    assert patch == {"conf_scale": pytest.approx(0.9)}


def test_overtrading_regret_reduces_demo_risk_and_leverage():
    cfg = DemoApplierConfig(max_risk_delta_pct=0.10)
    patch = build_risk_patch(
        payload={"net_regret_direction": "overtrading"},
        current_risk_config={
            "limits": {
                "per_trade_risk_pct": 0.02,
                "leverage_max": 10.0,
                "open_positions_max": 5,
            }
        },
        recommendation_type="regret_summary",
        cfg=cfg,
    )

    assert patch["limits"]["per_trade_risk_pct"] == pytest.approx(0.018)
    assert patch["limits"]["leverage_max"] == pytest.approx(9.0)
    assert patch["limits"]["open_positions_max"] == 4


def test_explicit_risk_patch_is_delta_bounded():
    cfg = DemoApplierConfig(max_risk_delta_pct=0.10)
    patch = build_risk_patch(
        payload={"risk_patch": {"limits": {"leverage_max": 50.0}}},
        current_risk_config={"limits": {"leverage_max": 10.0}},
        recommendation_type="regret_summary",
        cfg=cfg,
    )

    assert patch == {"limits": {"leverage_max": pytest.approx(11.0)}}


def test_live_candidate_requires_strong_demo_evidence():
    cfg = DemoApplierConfig(
        live_candidate_min_net_bps=5.0,
        live_candidate_min_confidence=0.65,
        live_candidate_min_samples=30,
    )

    assert should_create_live_candidate(
        {"expected_net_bps": 7.0, "confidence": 0.8, "sample_count": 40},
        cfg,
    )
    assert not should_create_live_candidate(
        {"expected_net_bps": 7.0, "confidence": 0.6, "sample_count": 40},
        cfg,
    )


def test_noop_audit_payload_reports_threshold_context():
    cfg = DemoApplierConfig(
        lookback_hours=72,
        min_confidence=0.4,
        min_samples=8,
        max_recommendations=12,
    )
    cur = _Cursor([(10, 4, 0)])

    payload = _noop_audit_payload(cur, cfg)

    assert payload["reason"] == "no_eligible_recommendations"
    assert payload["lookback_hours"] == 72
    assert payload["min_confidence"] == pytest.approx(0.4)
    assert payload["min_samples"] == 8
    assert payload["max_recommendations"] == 12
    assert payload["lookback_recommendations"] == 10
    assert payload["demo_recommendations"] == 4
    assert payload["eligible_recommendations"] == 0


def test_record_noop_audit_writes_deduped_skipped_row(monkeypatch):
    cfg = DemoApplierConfig()
    cur = _Cursor([(3, 3, 0)])
    recorded = {}

    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._already_applied",
        lambda _cur, _fp, _cfg: False,
    )

    def fake_record_application(cur, **kwargs):
        recorded.update(kwargs)
        return 123

    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._record_application",
        fake_record_application,
    )

    result = _record_noop_audit(cur, cfg)

    assert result == {
        "status": "skipped",
        "reason": "no_eligible_recommendations",
        "target": "mlde_demo_applier",
        "eligible_recommendations": 0,
    }
    assert recorded["application_type"] == "strategy_params"
    assert recorded["target_name"] == "mlde_demo_applier"
    assert recorded["status"] == "skipped"
    assert recorded["reason"] == "no_eligible_recommendations"
    assert recorded["payload"]["fingerprint"]


def test_record_noop_audit_dedupes_recent_fingerprint(monkeypatch):
    cfg = DemoApplierConfig()
    cur = _Cursor([(3, 3, 0)])
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._already_applied",
        lambda _cur, _fp, _cfg: True,
    )

    result = _record_noop_audit(cur, cfg)

    assert result["status"] == "skipped"
    assert result["reason"] == "no_eligible_recommendations_deduped"


def test_already_applied_dedupe_includes_skipped_rows():
    cfg = DemoApplierConfig()
    cur = _Cursor([(False,)])

    assert not _already_applied(cur, "abc", cfg)

    sql = cur.executed[0][0]
    assert "status IN ('applied', 'dry_run', 'skipped')" in sql


# ────────────────────────────────────────────────────────────────────────────
# LG-5 RFC v2 §2.1 producer-side helper tests.
# 驗：(a) 4 helper 回 well-formed dict / int；
#     (b) attribution dict 5 keys 全在；
#     (c) `_insert_live_candidate` 寫的 payload 含 schema_version + 4 新 sub-key。
# ────────────────────────────────────────────────────────────────────────────


def test_lg5_helpers_return_well_formed_dicts_with_deterministic_data():
    """4 helper 回 well-formed dict + per-strategy 5 keys 全在。"""
    # Scripted cursor responses sequenced exactly as the helpers query:
    #   1) cost baseline maker block: (total, maker_like, avg_fee_rate)
    #   2) view_exists check for net_bps block: (True,)
    #   3) net_bps + slippage avg row
    #   4) realized_window n_fills row
    #   5) attribution view_exists check
    #   6) attribution per-strategy fetchall — passed as list of rows
    #   7) sample_count_strategy_cell view_exists
    #   8) sample_count_strategy_cell row
    cursor = _ScriptedCursor(
        responses=[
            (200, 50, 0.00040),                # 25% maker_like, fee = 4bps
            (True,),
            (3.5, 1.2),                        # avg_net_bps_7d, avg_slip_bps_7d
            (350,),                            # n_fills
            (True,),
            [
                ("grid_trading", 100, 80),    # 80% ok
                ("ma_crossover", 50, 25),     # 50% ok
                ("bb_breakout", 40, 20),      # 50% ok
                # bb_reversion + funding_arb absent → must default 0.0
            ],
            (True,),
            (140,),                            # strategy_cell sample_count
        ]
    )

    baseline = _compute_demo_cost_baseline(cursor)
    assert baseline["engine_mode"] == "demo"
    assert "as_of_ts" in baseline
    assert baseline["sample_count"] == 200
    assert baseline["maker_fill_rate_7d"] == pytest.approx(0.25)
    assert baseline["avg_realized_fee_bps_7d"] == pytest.approx(4.0)
    # fee_drop = (5.5 - 4.0) / 5.5 ≈ 0.2727
    assert baseline["fee_drop_only_7d"] == pytest.approx(
        (0.00055 - 0.00040) / 0.00055
    )
    assert baseline["avg_realized_net_bps_7d"] == pytest.approx(3.5)
    assert baseline["avg_realized_slippage_bps_7d"] == pytest.approx(1.2)
    assert baseline["source_healthchecks"] == ["[33]", "[40]"]
    maker_sql = cursor.executed[0][0]
    assert "f.entry_context_id IS NULL" in maker_sql
    assert "f.exit_reason IS NULL" in maker_sql
    assert "f.order_id NOT LIKE 'oc_risk_" in maker_sql

    # No strategy_name → n_strategy_fills 0（helper short-circuits, no DB hit）
    # 不傳 strategy_name → n_strategy_fills 0（helper 不查 DB），cursor 序列不被消耗。
    window = _compute_demo_realized_window(cursor)
    assert window["window_days"] == 7
    assert window["n_fills"] == 350
    assert "start_ts" in window and "end_ts" in window
    assert window["n_strategy_fills"] == 0

    ratios = _compute_attribution_chain_ratio_by_strategy(cursor)
    # 5 hardcoded keys 全在
    assert set(ratios.keys()) == set(_ATTRIBUTION_STRATEGY_KEYS)
    assert ratios["grid_trading"] == pytest.approx(0.80)
    assert ratios["ma_crossover"] == pytest.approx(0.50)
    assert ratios["bb_breakout"] == pytest.approx(0.50)
    # 缺資料 → 0.0
    assert ratios["bb_reversion"] == 0.0
    assert ratios["funding_arb"] == 0.0

    cell_count = _compute_demo_sample_count_strategy_cell(cursor, "grid_trading")
    assert cell_count == 140


def test_lg5_helpers_fail_soft_on_missing_view():
    """View 不存在時 fail-soft 回 0.0 / 0 / well-formed dict。"""
    # Cost baseline maker block ok; net_bps view missing.
    # cost block + (False,) view_exists → 0 net_bps.
    cursor = _ScriptedCursor(
        responses=[
            (0, 0, 0.00055),  # 0 fills
            (False,),         # view missing for net_bps block
        ]
    )
    baseline = _compute_demo_cost_baseline(cursor)
    assert baseline["sample_count"] == 0
    assert baseline["avg_realized_net_bps_7d"] == 0.0
    assert baseline["maker_fill_rate_7d"] == 0.0

    # attribution view missing → 5 keys 全 0.0
    cur2 = _ScriptedCursor(responses=[(False,)])
    ratios = _compute_attribution_chain_ratio_by_strategy(cur2)
    assert set(ratios.keys()) == set(_ATTRIBUTION_STRATEGY_KEYS)
    assert all(v == 0.0 for v in ratios.values())

    # sample_count helper：view missing → 0
    cur3 = _ScriptedCursor(responses=[(False,)])
    assert _compute_demo_sample_count_strategy_cell(cur3, "grid_trading") == 0

    # 空 strategy_name → 0（不查 DB）
    cur4 = _ScriptedCursor(responses=[])
    assert _compute_demo_sample_count_strategy_cell(cur4, None) == 0
    assert _compute_demo_sample_count_strategy_cell(cur4, "") == 0


def test_insert_live_candidate_payload_carries_schema_version_and_lg5_subkeys(
    monkeypatch,
):
    """`_insert_live_candidate` 寫的 payload 含 schema_version + 4 LG-5 sub-key。"""
    # Stub helpers to deterministic dicts so we can inspect the payload
    # written without mocking SQL flow.
    # Stub 4 helper 為固定值，專注驗 payload 結構。
    fake_baseline = {
        "as_of_ts": "2026-05-02T12:00:00+00:00",
        "engine_mode": "demo",
        "maker_fill_rate_7d": 0.30,
        "fee_drop_only_7d": 0.50,
        "avg_realized_net_bps_7d": 4.5,
        "avg_realized_fee_bps_7d": 2.75,
        "avg_realized_slippage_bps_7d": 1.0,
        "sample_count": 250,
        "source_healthchecks": ["[33]", "[40]"],
    }
    fake_window = {
        "start_ts": "2026-04-25T12:00:00+00:00",
        "end_ts": "2026-05-02T12:00:00+00:00",
        "n_fills": 250,
        "n_strategy_fills": 0,
        "window_days": 7,
    }
    fake_attribution = {
        "grid_trading": 0.80,
        "ma_crossover": 0.65,
        "bb_breakout": 0.55,
        "bb_reversion": 0.40,
        "funding_arb": 0.50,
    }
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_cost_baseline",
        lambda _cur: fake_baseline,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_realized_window",
        lambda _cur, _strategy=None: fake_window,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_attribution_chain_ratio_by_strategy",
        lambda _cur: fake_attribution,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_sample_count_strategy_cell",
        lambda _cur, _strategy: 175,
    )

    captured: dict = {}

    class _CaptureCursor:
        def execute(self, sql, params=()):
            captured["sql"] = sql
            captured["params"] = params

    # `Json` wraps the payload at INSERT-time; unwrap for assertion.
    # `Json` 會包 payload；測試端解包還原 dict。
    from psycopg2.extras import Json  # type: ignore

    source_row = {
        "id": 42,
        "symbol": "BTCUSDT",
        "strategy_name": "grid_trading",
        "expected_net_bps": 6.5,
        "confidence": 0.78,
        "sample_count": 50,
    }
    _insert_live_candidate(
        _CaptureCursor(),
        source_row=source_row,
        application_id=999,
        application_type="strategy_params",
        patch={"cooldown_ms": 144_000},
    )

    assert "learning.verify_replay_evidence_and_insert" in captured["sql"]
    # params: (symbol, strategy_name, expected_net_bps, confidence,
    #          sample_count, Json(payload))
    payload_param = captured["params"][-1]
    assert isinstance(payload_param, Json)
    payload = payload_param.adapted

    # schema_version + LG-5 §2.1 sub-keys 必含
    assert payload["schema_version"] == _LIVE_CANDIDATE_EVAL_SCHEMA_VERSION
    assert payload["policy"] == "live_governed_promotion_candidate"
    assert payload["source_demo_recommendation_id"] == 42
    assert payload["source_demo_application_id"] == 999
    assert payload["application_type"] == "strategy_params"
    assert payload["patch"] == {"cooldown_ms": 144_000}
    assert payload["requires"] == ["GovernanceHub", "DecisionLease", "live_gates"]

    assert payload["demo_cost_baseline"] == fake_baseline
    assert payload["demo_realized_window"] == fake_window
    # MIT MF-M2：dict 不是 scalar，5 keys 全在。
    assert payload["demo_attribution_chain_ratio_by_strategy"] == fake_attribution
    assert set(payload["demo_attribution_chain_ratio_by_strategy"].keys()) == set(
        _ATTRIBUTION_STRATEGY_KEYS
    )
    assert payload["demo_sample_count_strategy_cell"] == 175


# ────────────────────────────────────────────────────────────────────────────
# LG-5 IMPL-1 round 2 — CRITICAL spec drift fix tests.
# Round 1 placed 5 new sub-keys only on the `mlde_shadow_recommendations`
# writer; consumer (RFC v2 §2.2 line 140) reads `mlde_param_applications`,
# whose payload was bare 2-key → consumer defers/rejects all candidates.
# Round 2 introduces `_build_live_candidate_payload` as single SoT; both
# writers share it. Tests below pin the contract.
#
# LG-5 IMPL-1 round 2 — CRITICAL spec drift 修復測試。
# Round 1 只把 5 個新 sub-key 寫到 `mlde_shadow_recommendations`；consumer
# 真正讀 `mlde_param_applications`（RFC v2 §2.2 line 140），其 payload 只
# 有 bare 2-key → consumer 對所有 candidate defer/reject。Round 2 用
# `_build_live_candidate_payload` 作 SoT，兩處 writer 共用同一 payload。
# ────────────────────────────────────────────────────────────────────────────


class _RaisingCursor:
    """Cursor that raises on first execute() call.
    第一次 execute() 即拋例外的 cursor，模擬 SQL 異常。
    """

    def __init__(self):
        self.calls = 0
        self.executed = []

    def execute(self, sql, params=()):
        self.calls += 1
        self.executed.append((sql, params))
        raise RuntimeError("simulated SQL exception on first SELECT")

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def test_cost_baseline_fail_soft_on_block1_sql_exception():
    """First SELECT raises → baseline returns well-formed dict, no raise.
    第一個 SELECT 拋異常 → baseline 回 well-formed dict 全 0 + 不拋。
    """
    cur = _RaisingCursor()

    # Must not raise — fail-soft contract.
    # 不可拋 — fail-soft 契約。
    baseline = _compute_demo_cost_baseline(cur)

    # Well-formed dict shape preserved.
    # well-formed dict shape 必須保留。
    assert baseline["engine_mode"] == "demo"
    assert "as_of_ts" in baseline
    assert baseline["sample_count"] == 0
    assert baseline["maker_fill_rate_7d"] == 0.0
    assert baseline["fee_drop_only_7d"] == 0.0
    assert baseline["avg_realized_fee_bps_7d"] == 0.0
    # net_bps block also fails-soft to 0.0 (raising cursor too).
    assert baseline["avg_realized_net_bps_7d"] == 0.0
    assert baseline["avg_realized_slippage_bps_7d"] == 0.0
    assert baseline["source_healthchecks"] == ["[33]", "[40]"]


def test_record_application_payload_matches_lg5_contract(monkeypatch):
    """`_record_application(...)` row payload carries LG-5 §2.1 5-key contract.
    `_record_application(...)` row 的 payload 必含 LG-5 §2.1 5-key contract。

    Producer two-writer alignment: this test mirrors the
    ``_apply_one`` live_promotion_candidate path — payload built via
    ``_build_live_candidate_payload`` shared helper → handed to
    ``_record_application(payload=...)`` writing
    ``learning.mlde_param_applications``. Asserts schema_version + 5
    sub-keys present in that table's payload column.

    Producer 兩 writer 對齊：本測模擬 ``_apply_one`` live_promotion_candidate
    路徑 — payload 透過 ``_build_live_candidate_payload`` 共用 helper 建構，
    交給 ``_record_application(payload=...)`` 寫入
    ``learning.mlde_param_applications``，驗該表 payload column 含
    schema_version + 5 sub-key。
    """
    fake_baseline = {
        "as_of_ts": "2026-05-02T12:00:00+00:00",
        "engine_mode": "demo",
        "maker_fill_rate_7d": 0.30,
        "fee_drop_only_7d": 0.50,
        "avg_realized_net_bps_7d": 4.0,
        "avg_realized_fee_bps_7d": 2.5,
        "avg_realized_slippage_bps_7d": 1.0,
        "sample_count": 250,
        "source_healthchecks": ["[33]", "[40]"],
    }
    fake_window = {
        "start_ts": "2026-04-25T12:00:00+00:00",
        "end_ts": "2026-05-02T12:00:00+00:00",
        "n_fills": 250,
        "n_strategy_fills": 145,    # round 2 fix: must be populated
        "window_days": 7,
    }
    fake_attribution = {k: 0.6 for k in _ATTRIBUTION_STRATEGY_KEYS}
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_cost_baseline",
        lambda _cur: fake_baseline,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_realized_window",
        lambda _cur, _strategy=None: fake_window,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_attribution_chain_ratio_by_strategy",
        lambda _cur: fake_attribution,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_sample_count_strategy_cell",
        lambda _cur, _strategy: 145,
    )

    captured: dict = {}

    class _CaptureCursor:
        def execute(self, sql, params=()):
            captured["sql"] = sql
            captured["params"] = params

        def fetchone(self):
            # _record_application does RETURNING id → return synthetic id
            return (777,)

    source_row = {
        "id": 99,
        "engine_mode": "demo",
        "symbol": "BTCUSDT",
        "strategy_name": "grid_trading",
    }
    payload_dict = _build_live_candidate_payload(
        _CaptureCursor(),  # not used since helpers are monkeypatched
        source_row=source_row,
        application_id=555,
        application_type="strategy_params",
        patch={"cooldown_ms": 144_000},
        strategy_name="grid_trading",
    )

    # Now write through _record_application as _apply_one does.
    # 透過 _record_application 寫入，模擬 _apply_one 路徑。
    cur = _CaptureCursor()
    new_id = _record_application(
        cur,
        row={**source_row, "engine_mode": "live"},
        application_type="live_promotion_candidate",
        target_name="grid_trading",
        patch={"cooldown_ms": 144_000},
        prev_snapshot={},
        ipc_response={},
        status="candidate",
        reason="positive_demo_evidence_governed_live_candidate",
        requires_governance=True,
        payload=payload_dict,
    )
    assert new_id == 777

    # SQL writes to mlde_param_applications (consumer's table).
    # SQL 寫入 mlde_param_applications（consumer 讀的表）。
    assert "INSERT INTO learning.mlde_param_applications" in captured["sql"]
    assert "engine_mode" in captured["sql"]
    assert "application_type" in captured["sql"]
    assert "status" in captured["sql"]

    from psycopg2.extras import Json  # type: ignore
    # Locate Json-wrapped payload in params.
    # 從 params 找 Json 包的 payload。
    params = captured["params"]
    json_params = [p for p in params if isinstance(p, Json)]
    assert len(json_params) >= 1
    # payload is the last Json arg per _record_application INSERT order
    # (patch, prev_snapshot, ipc_response, payload).
    # _record_application INSERT 順序最後一個 Json 即為 payload。
    written_payload = json_params[-1].adapted

    # CRITICAL: schema_version + 5 LG-5 §2.1 sub-keys present.
    # CRITICAL：schema_version + 5 個 LG-5 §2.1 sub-key 必含。
    assert written_payload["schema_version"] == _LIVE_CANDIDATE_EVAL_SCHEMA_VERSION
    assert written_payload["policy"] == "live_governed_promotion_candidate"
    assert written_payload["source_demo_recommendation_id"] == 99
    assert written_payload["source_demo_application_id"] == 555
    assert written_payload["application_type"] == "strategy_params"
    assert written_payload["patch"] == {"cooldown_ms": 144_000}
    assert written_payload["demo_cost_baseline"] == fake_baseline
    assert written_payload["demo_realized_window"] == fake_window
    # Round 2 fix: n_strategy_fills must be populated, not 0
    # Round 2 fix：n_strategy_fills 必須被填寫，不可 0
    assert written_payload["demo_realized_window"]["n_strategy_fills"] == 145
    assert written_payload["demo_attribution_chain_ratio_by_strategy"] == fake_attribution
    assert set(
        written_payload["demo_attribution_chain_ratio_by_strategy"].keys()
    ) == set(_ATTRIBUTION_STRATEGY_KEYS)
    assert written_payload["demo_sample_count_strategy_cell"] == 145


def test_lg5_contract_round_trip_param_applications_table(monkeypatch):
    """Round-trip: producer writes payload → simulated consumer reads it.
    Round-trip：producer 寫 payload → 模擬 consumer 讀回 → schema_version match。

    模擬 consumer 端 ``GovernanceHub.review_live_candidate`` 從
    ``mlde_param_applications`` 讀 row → 取 payload JSONB → 對比
    ``_LIVE_CANDIDATE_EVAL_SCHEMA_VERSION`` 是否相符。若不符 consumer 將
    fail-closed (defer / reject ``schema_unknown``)。
    """
    fake_baseline = {
        "as_of_ts": "2026-05-02T12:00:00+00:00",
        "engine_mode": "demo",
        "maker_fill_rate_7d": 0.31,
        "fee_drop_only_7d": 0.49,
        "avg_realized_net_bps_7d": 5.5,
        "avg_realized_fee_bps_7d": 2.8,
        "avg_realized_slippage_bps_7d": 0.9,
        "sample_count": 300,
        "source_healthchecks": ["[33]", "[40]"],
    }
    fake_window = {
        "start_ts": "2026-04-25T12:00:00+00:00",
        "end_ts": "2026-05-02T12:00:00+00:00",
        "n_fills": 300,
        "n_strategy_fills": 120,
        "window_days": 7,
    }
    fake_attribution = {k: 0.7 for k in _ATTRIBUTION_STRATEGY_KEYS}
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_cost_baseline",
        lambda _cur: fake_baseline,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_realized_window",
        lambda _cur, _strategy=None: fake_window,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_attribution_chain_ratio_by_strategy",
        lambda _cur: fake_attribution,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_sample_count_strategy_cell",
        lambda _cur, _strategy: 120,
    )

    # === Producer side ===
    # 模擬 _apply_one 寫 candidate row 到 mlde_param_applications。
    captured_payload: dict = {}

    class _ProducerCursor:
        def execute(self, sql, params=()):
            from psycopg2.extras import Json  # type: ignore
            json_args = [p for p in params if isinstance(p, Json)]
            if "INSERT INTO learning.mlde_param_applications" in sql:
                # payload is last Json arg
                # payload 為最後一個 Json 參數
                captured_payload["row_payload"] = json_args[-1].adapted
                captured_payload["status"] = params[7]
                captured_payload["application_type"] = params[2]
                captured_payload["engine_mode"] = params[0]

        def fetchone(self):
            return (888,)

    source_row = {
        "id": 11,
        "engine_mode": "demo",
        "symbol": "ETHUSDT",
        "strategy_name": "ma_crossover",
    }
    payload = _build_live_candidate_payload(
        _ProducerCursor(),
        source_row=source_row,
        application_id=222,
        application_type="strategy_params",
        patch={"sma_fast": 7},
        strategy_name="ma_crossover",
    )
    _record_application(
        _ProducerCursor(),
        row={**source_row, "engine_mode": "live"},
        application_type="live_promotion_candidate",
        target_name="ma_crossover",
        patch={"sma_fast": 7},
        prev_snapshot={},
        ipc_response={},
        status="candidate",
        reason="positive_demo_evidence_governed_live_candidate",
        requires_governance=True,
        payload=payload,
    )

    # === Simulated consumer side ===
    # 模擬 GovernanceHub.review_live_candidate 從表讀 row。
    # Consumer filter: engine_mode='live' AND status='candidate' AND
    # application_type='live_promotion_candidate' (RFC v2 §2.2 line 140).
    assert captured_payload["engine_mode"] == "live"
    assert captured_payload["status"] == "candidate"
    assert captured_payload["application_type"] == "live_promotion_candidate"

    consumer_payload = captured_payload["row_payload"]

    # Schema version match → consumer accepts (else fail-closed).
    # Schema version 相符 → consumer 接受（否則 fail-closed defer/reject）。
    assert (
        consumer_payload.get("schema_version")
        == _LIVE_CANDIDATE_EVAL_SCHEMA_VERSION
    )

    # All 5 LG-5 §2.1 sub-keys present (consumer R-meta / R3 reads these).
    # 5 個 LG-5 §2.1 sub-key 全在（consumer R-meta / R3 讀此判 promote/defer）。
    assert "demo_cost_baseline" in consumer_payload
    assert "demo_realized_window" in consumer_payload
    assert "demo_attribution_chain_ratio_by_strategy" in consumer_payload
    assert "demo_sample_count_strategy_cell" in consumer_payload
    # source linkage so consumer can trace back to demo evidence row.
    # source_demo_* 用於 consumer 反查 demo 證據 row。
    assert "source_demo_recommendation_id" in consumer_payload
    assert "source_demo_application_id" in consumer_payload

    # MIT MF-M2 / RFC §3 R-meta gate: per-strategy attribution dict 5 keys.
    # MIT MF-M2 / RFC §3 R-meta gate：per-strategy attribution dict 必 5 keys。
    assert set(
        consumer_payload["demo_attribution_chain_ratio_by_strategy"].keys()
    ) == set(_ATTRIBUTION_STRATEGY_KEYS)

    # RFC §3 R3 gate: n_strategy_fills must be readable (not 0 from drift).
    # RFC §3 R3 gate：n_strategy_fills 須可讀（非 round 1 那種硬編 0）。
    assert (
        consumer_payload["demo_realized_window"]["n_strategy_fills"] == 120
    )


# ────────────────────────────────────────────────────────────────────────────
# LG-5 W3 FUP-2 Fix 2 IMPL-1 + IMPL-2 tests (PA RFC 2026-05-02)
#   IMPL-1: Producer SQL window 7d → 3d for R-meta attribution ratio
#   IMPL-2: Payload sub-keys `demo_attribution_window_days` (=3) +
#           `demo_attribution_sample_count_by_strategy` (per-strategy n)
#           plus `_compute_attribution_sample_count_by_strategy` helper.
#
# LG-5 W3 FUP-2 Fix 2 IMPL-1 + IMPL-2 測試（PA RFC 2026-05-02）：
#   IMPL-1：producer R-meta ratio SQL window 7d → 3d
#   IMPL-2：payload 加 `demo_attribution_window_days` (=3) +
#           `demo_attribution_sample_count_by_strategy`，並新增
#           `_compute_attribution_sample_count_by_strategy` helper。
# ────────────────────────────────────────────────────────────────────────────


def test_attribution_ratio_uses_3d_window():
    """IMPL-1：ratio helper SQL 必綁 _R_META_WINDOW_DAYS (=3)，非 7d。"""
    # Capture executed SQL params to confirm 3d binding.
    # 截獲 SQL 執行參數以驗證綁的是 3 天。
    cur = _ScriptedCursor(
        responses=[
            (True,),  # view exists
            [],       # GROUP BY rows (empty list → fetchall returns [])
        ]
    )

    ratios = _compute_attribution_chain_ratio_by_strategy(cur)

    # 5 keys 全在（fail-soft 預設 0.0）
    assert set(ratios.keys()) == set(_ATTRIBUTION_STRATEGY_KEYS)
    assert all(v == 0.0 for v in ratios.values())

    # 第二次 execute 是 GROUP BY query；params[0] 必須是 _R_META_WINDOW_DAYS=3。
    # 2nd execute is GROUP BY; params[0] must be _R_META_WINDOW_DAYS=3.
    assert len(cur.executed) == 2
    group_by_sql, group_by_params = cur.executed[1]
    assert "GROUP BY strategy_name" in group_by_sql
    assert "net_bps_after_fee IS NOT NULL" in group_by_sql
    assert group_by_params[0] == _R_META_WINDOW_DAYS == 3
    # 確保不是 7（即未誤用 _DEMO_BASELINE_WINDOW_DAYS）
    # Confirm not 7 (i.e., did not regress to _DEMO_BASELINE_WINDOW_DAYS).
    assert group_by_params[0] != 7


def test_compute_sample_count_by_strategy_5_keys_default_zero():
    """IMPL-2：sample_count helper 5 key dict + missing strategy → 0 fail-soft。"""
    # 部分 strategy 有資料，bb_reversion / funding_arb 缺 → 0
    # Some strategies have rows; bb_reversion / funding_arb missing → 0
    cur = _ScriptedCursor(
        responses=[
            (True,),  # view exists
            [
                ("grid_trading", 42),
                ("ma_crossover", 17),
                ("bb_breakout", 8),
            ],
        ]
    )

    counts = _compute_attribution_sample_count_by_strategy(cur)

    # 5 個 key 必全在
    assert set(counts.keys()) == set(_ATTRIBUTION_STRATEGY_KEYS)
    assert counts["grid_trading"] == 42
    assert counts["ma_crossover"] == 17
    assert counts["bb_breakout"] == 8
    # missing → default 0
    assert counts["bb_reversion"] == 0
    assert counts["funding_arb"] == 0

    # SQL 必綁 3d window + 5 key list
    # SQL must bind 3d window + 5 strategy keyset list
    group_by_sql, group_by_params = cur.executed[1]
    assert "GROUP BY strategy_name" in group_by_sql
    assert "net_bps_after_fee IS NOT NULL" in group_by_sql
    assert group_by_params[0] == _R_META_WINDOW_DAYS == 3
    assert sorted(group_by_params[1]) == sorted(_ATTRIBUTION_STRATEGY_KEYS)

    # View missing → 全 0 fail-soft（不拋）
    # View missing → all 0 fail-soft (no raise).
    cur_missing = _ScriptedCursor(responses=[(False,)])
    counts_missing = _compute_attribution_sample_count_by_strategy(cur_missing)
    assert set(counts_missing.keys()) == set(_ATTRIBUTION_STRATEGY_KEYS)
    assert all(v == 0 for v in counts_missing.values())


def test_payload_includes_attribution_window_days(monkeypatch):
    """IMPL-2：payload 必含 demo_attribution_window_days == 3。"""
    fake_baseline = {
        "as_of_ts": "2026-05-02T12:00:00+00:00",
        "engine_mode": "demo",
        "maker_fill_rate_7d": 0.30,
        "fee_drop_only_7d": 0.50,
        "avg_realized_net_bps_7d": 4.0,
        "avg_realized_fee_bps_7d": 2.5,
        "avg_realized_slippage_bps_7d": 1.0,
        "sample_count": 200,
        "source_healthchecks": ["[33]", "[40]"],
    }
    fake_window = {
        "start_ts": "2026-04-25T12:00:00+00:00",
        "end_ts": "2026-05-02T12:00:00+00:00",
        "n_fills": 200,
        "n_strategy_fills": 80,
        "window_days": 7,
    }
    fake_attribution = {k: 0.55 for k in _ATTRIBUTION_STRATEGY_KEYS}
    fake_sample_counts = {k: 25 for k in _ATTRIBUTION_STRATEGY_KEYS}
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_cost_baseline",
        lambda _cur: fake_baseline,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_realized_window",
        lambda _cur, _strategy=None: fake_window,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_attribution_chain_ratio_by_strategy",
        lambda _cur: fake_attribution,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_attribution_sample_count_by_strategy",
        lambda _cur: fake_sample_counts,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_sample_count_strategy_cell",
        lambda _cur, _strategy: 80,
    )

    class _NoopCursor:
        def execute(self, sql, params=()):
            pass

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    payload = _build_live_candidate_payload(
        _NoopCursor(),
        source_row={"id": 11, "symbol": "BTCUSDT", "strategy_name": "grid_trading"},
        application_id=222,
        application_type="strategy_params",
        patch={"cooldown_ms": 144_000},
        strategy_name="grid_trading",
    )

    # IMPL-2 必含的 R-meta window key
    # IMPL-2 mandatory R-meta window key
    assert "demo_attribution_window_days" in payload
    assert payload["demo_attribution_window_days"] == _R_META_WINDOW_DAYS == 3
    # 7 != 3 — 防 regression 回 _DEMO_BASELINE_WINDOW_DAYS
    # Guard against regression to _DEMO_BASELINE_WINDOW_DAYS.
    assert payload["demo_attribution_window_days"] != 7

    # backward compat: schema_version 不 bump
    # backward compat: schema_version unchanged (stays v1)
    assert payload["schema_version"] == _LIVE_CANDIDATE_EVAL_SCHEMA_VERSION


def test_payload_includes_per_strategy_sample_count(monkeypatch):
    """IMPL-2：payload 必含 demo_attribution_sample_count_by_strategy 5-key dict。"""
    fake_baseline = {
        "as_of_ts": "2026-05-02T12:00:00+00:00",
        "engine_mode": "demo",
        "maker_fill_rate_7d": 0.30,
        "fee_drop_only_7d": 0.50,
        "avg_realized_net_bps_7d": 4.0,
        "avg_realized_fee_bps_7d": 2.5,
        "avg_realized_slippage_bps_7d": 1.0,
        "sample_count": 200,
        "source_healthchecks": ["[33]", "[40]"],
    }
    fake_window = {
        "start_ts": "2026-04-25T12:00:00+00:00",
        "end_ts": "2026-05-02T12:00:00+00:00",
        "n_fills": 200,
        "n_strategy_fills": 80,
        "window_days": 7,
    }
    fake_attribution = {k: 0.55 for k in _ATTRIBUTION_STRATEGY_KEYS}
    # Mix above + below _R_META_MIN_SAMPLE_PER_STRATEGY (=10) so consumer
    # tests can exercise the low-sample defer branch downstream.
    # 混合 above / below _R_META_MIN_SAMPLE_PER_STRATEGY (=10)，給下游
    # consumer 測試 defer_attribution_chain_low_sample 分支有素材。
    fake_sample_counts = {
        "grid_trading": 42,
        "ma_crossover": 25,
        "bb_breakout": 13,      # 邊界 above 10
        "bb_reversion": 3,      # below threshold → consumer 應 defer low_sample
        "funding_arb": 0,       # 缺資料
    }
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_cost_baseline",
        lambda _cur: fake_baseline,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_realized_window",
        lambda _cur, _strategy=None: fake_window,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_attribution_chain_ratio_by_strategy",
        lambda _cur: fake_attribution,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_attribution_sample_count_by_strategy",
        lambda _cur: fake_sample_counts,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_sample_count_strategy_cell",
        lambda _cur, _strategy: 80,
    )

    class _NoopCursor:
        def execute(self, sql, params=()):
            pass

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    payload = _build_live_candidate_payload(
        _NoopCursor(),
        source_row={"id": 12, "symbol": "ETHUSDT", "strategy_name": "ma_crossover"},
        application_id=333,
        application_type="strategy_params",
        patch={"sma_fast": 7},
        strategy_name="ma_crossover",
    )

    # 必有 sample_count by strategy 5-key dict
    # Must contain per-strategy sample_count 5-key dict.
    assert "demo_attribution_sample_count_by_strategy" in payload
    sample_dict = payload["demo_attribution_sample_count_by_strategy"]
    assert set(sample_dict.keys()) == set(_ATTRIBUTION_STRATEGY_KEYS)
    assert sample_dict["grid_trading"] == 42
    assert sample_dict["ma_crossover"] == 25
    assert sample_dict["bb_breakout"] == 13
    assert sample_dict["bb_reversion"] == 3
    assert sample_dict["funding_arb"] == 0

    # Sanity：sample_count dict 與 ratio dict 同 keyset 對齊
    # Sanity: sample_count dict shares keyset with ratio dict (consumer
    # joins them by strategy name).
    assert set(sample_dict.keys()) == set(
        payload["demo_attribution_chain_ratio_by_strategy"].keys()
    )

    # constants exposed for downstream consumer tests
    # 對下游 consumer 測試暴露的常數
    assert _R_META_MIN_SAMPLE_PER_STRATEGY == 10


def test_payload_includes_live_candidate_lineage(monkeypatch):
    """Live candidate payload carries Hypothesis/Experiment lineage refs."""
    fake_baseline = {
        "as_of_ts": "2026-05-02T12:00:00+00:00",
        "engine_mode": "demo",
        "maker_fill_rate_7d": 0.30,
        "fee_drop_only_7d": 0.50,
        "avg_realized_net_bps_7d": 4.0,
        "avg_realized_fee_bps_7d": 2.5,
        "avg_realized_slippage_bps_7d": 1.0,
        "sample_count": 200,
        "source_healthchecks": ["[33]", "[40]"],
    }
    fake_window = {
        "start_ts": "2026-04-25T12:00:00+00:00",
        "end_ts": "2026-05-02T12:00:00+00:00",
        "n_fills": 200,
        "n_strategy_fills": 80,
        "window_days": 7,
    }
    fake_attribution = {k: 0.55 for k in _ATTRIBUTION_STRATEGY_KEYS}
    fake_sample_counts = {k: 25 for k in _ATTRIBUTION_STRATEGY_KEYS}
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_cost_baseline",
        lambda _cur: fake_baseline,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_realized_window",
        lambda _cur, _strategy=None: fake_window,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_attribution_chain_ratio_by_strategy",
        lambda _cur: fake_attribution,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_attribution_sample_count_by_strategy",
        lambda _cur: fake_sample_counts,
    )
    monkeypatch.setattr(
        "ml_training.mlde_demo_applier._compute_demo_sample_count_strategy_cell",
        lambda _cur, _strategy: 80,
    )

    class _NoopCursor:
        def execute(self, sql, params=()):
            pass

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    payload = _build_live_candidate_payload(
        _NoopCursor(),
        source_row={
            "id": 12,
            "symbol": "ETHUSDT",
            "strategy_name": "ma_crossover",
            "source": "ml_shadow",
            "recommendation_type": "parameter_proposal",
            "context_id": "ctx-1",
            "intent_id": "intent-1",
            "replay_experiment_id": "replay-1",
            "manifest_hash": "manifest-a",
            "payload": {
                "originating_hypothesis_id": "hyp-alpha-1",
                "experiment_id": "exp-alpha-1",
                "alpha_source_id": "alpha:carry",
            },
        },
        application_id=333,
        application_type="strategy_params",
        patch={"sma_fast": 7, "sma_slow": 21},
        strategy_name="ma_crossover",
    )

    lineage = payload["lineage"]
    assert lineage["schema_version"] == LIVE_CANDIDATE_LINEAGE_SCHEMA_VERSION
    assert lineage["lineage_source"] == "producer_payload"
    assert lineage["originating_hypothesis_id"] == "hyp-alpha-1"
    assert lineage["originating_experiment_id"] == "exp-alpha-1"
    assert lineage["replay_experiment_id"] == "replay-1"
    assert lineage["manifest_hash"] == "manifest-a"
    assert lineage["alpha_source_id"] == "alpha:carry"
    assert lineage["source_demo_recommendation_id"] == 12
    assert lineage["source_demo_application_id"] == 333
    assert lineage["patch_keys"] == ["sma_fast", "sma_slow"]

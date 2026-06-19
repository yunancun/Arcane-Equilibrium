"""
Adaptive Demo Profit Engine runner / reward_source / ipc_lever 單元測試。

涵蓋誠實鐵則 + demo 沙盒硬邊界：
  - engine_mode 硬鎖 demo（非 demo cycle 被拒）。
  - reward_source SQL 只 demo-scope、含 attribution / post-fee、0 forbidden token。
  - 全負 EV → desired 全 dormant（歸零，不硬湊正）。
  - ipc_lever 冪等 diff（現態==期望態 0 IPC）+ fail-safe（未知不誤關）+ 失敗不 hidden retry。
  - kill switch snapshot + restore 還原 active 態。
  - dry-run 默認不發 IPC。

防 prod 污染：autouse _no_real_db；reward_source live 路徑用 fake _connect 注入，
不連真 PG；所有隨機 seeded。
"""

from __future__ import annotations

import json
import random

import pytest

from program_code.ml_training.adaptive_demo_profit_engine.ipc_lever import StrategyLever
from program_code.ml_training.adaptive_demo_profit_engine.reward_source import (
    fetch_demo_arm_rewards,
    map_view_regime_to_alloc_regime,
)
from program_code.ml_training.adaptive_demo_profit_engine.runner import (
    AdpeRunner,
    AdpeRunnerConfig,
    fetch_recent_advisory_strategy_scores,
    load_runner_config,
)
from program_code.ml_training.regime_bandit_allocator import (
    FILL_TIER_TAKER_REAL,
    AllocatorConfig,
    ArmReward,
    make_arm_id,
)


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    """攔真 psycopg2.connect：縱深防禦，避免未來 IO 誤連真 PG。"""
    try:
        import psycopg2  # noqa: PLC0415

        def _blocked(*_a, **_k):
            raise AssertionError("測試禁止真 psycopg2.connect（_no_real_db 鐵閘）")

        monkeypatch.setattr(psycopg2, "connect", _blocked)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# fake IPC / fake cursor 工具
# ---------------------------------------------------------------------------


class _FakeCur:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self.cur = _FakeCur(rows)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self.cur


def _make_fake_connect(rows):
    captured = {}

    def _connect(dsn, connect_timeout=None):
        captured["dsn"] = dsn
        captured["conn"] = _FakeConn(rows)
        return captured["conn"]

    return _connect, captured


class _ScriptedCur(_FakeCur):
    def __init__(self, rowsets):
        super().__init__([])
        self._rowsets = list(rowsets)

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if not sql.lstrip().upper().startswith("SET"):
            self._rows = self._rowsets.pop(0) if self._rowsets else []


class _ScriptedConn(_FakeConn):
    def __init__(self, rowsets):
        self.cur = _ScriptedCur(rowsets)


def _make_fake_connect_scripted(rowsets):
    captured = {}

    def _connect(dsn, connect_timeout=None):
        captured["dsn"] = dsn
        captured["conn"] = _ScriptedConn(rowsets)
        return captured["conn"]

    return _connect, captured


# ---------------------------------------------------------------------------
# config loader
# ---------------------------------------------------------------------------


def test_load_runner_config_defaults_demo_and_dry_run():
    rc, ac = load_runner_config()
    assert rc.engine_mode == "demo"
    assert rc.dry_run_default is True
    assert ac.trust_track == "transferable_only"


def test_load_runner_config_missing_file_fail_soft():
    rc, ac = load_runner_config(path="/nonexistent/adaptive_demo_profit.toml")
    # 缺檔 → 內建預設（fail-soft，不 raise）。
    assert rc.engine_mode == "demo"
    assert isinstance(ac, AllocatorConfig)


def test_repo_config_enables_controlled_experiment_and_excludes_retired_funding_arb():
    rc, _ac = load_runner_config()
    assert rc.controlled_experiment_enabled is True
    assert rc.require_advisory_for_explore is True
    assert rc.use_edge_snapshot_for_explore_evidence is True
    assert rc.require_cost_viable_edge_for_explore_when_available is True
    assert "funding_arb" in rc.retired_strategy_blocklist
    assert "funding_arb" not in rc.candidate_strategies
    assert rc.max_active_explore_strategies == 2


# ---------------------------------------------------------------------------
# reward_source：demo-scope SQL + regime mapping
# ---------------------------------------------------------------------------


def test_regime_mapping_view_to_alloc():
    assert map_view_regime_to_alloc_regime("trending") == "high-vol"
    assert map_view_regime_to_alloc_regime("mean_reverting") == "range"
    assert map_view_regime_to_alloc_regime("random_walk") == "chop"
    # 未知 / None → insufficient_context（誠實降級，不 cherry-pick）。
    assert map_view_regime_to_alloc_regime("garbage") == "insufficient_context"
    assert map_view_regime_to_alloc_regime(None) == "insufficient_context"


def test_reward_source_sql_is_demo_scoped_and_attribution_gated():
    # 真 schema：view 的 linucb_arm_id 嵌 view 詞彙 regime（V031:326
    # `regime_norm || '__' || strategy_name_norm`，regime_norm ∈
    # {trending, mean_reverting, random_walk}）。本測試刻意用真 view 詞彙，
    # 不再手造 allocator 詞彙 arm_id（那是 E2 抓的 vacuous 寫法）。
    rows = [
        ("mean_reverting__grid_trading", "grid_trading", "mean_reverting", 12.5, 1000.0),
        ("random_walk__ma_crossover", "ma_crossover", "random_walk", -8.0, 1001.0),
    ]
    connect, captured = _make_fake_connect(rows)
    out = fetch_demo_arm_rewards("FAKE_DSN", _connect=connect)
    assert len(out) == 2
    assert out[0].fill_realism_tier == FILL_TIER_TAKER_REAL
    # regime 經映射到 allocator 詞彙。
    assert out[0].regime == "range"  # mean_reverting -> range
    assert out[1].regime == "chop"   # random_walk -> chop
    # arm_id 用 allocator make_arm_id 重建 → regime 段 == allocator 詞彙（非 view 詞彙）。
    assert out[0].arm_id == make_arm_id("range", "grid_trading")
    assert out[1].arm_id == make_arm_id("chop", "ma_crossover")
    # arm_id 內嵌 regime 段必與 ArmReward.regime 一致（內部自洽）。
    assert out[0].arm_id == f"{out[0].regime}__grid_trading"

    sql, params = captured["conn"].cur.executed[-1]
    # demo-scope 硬鎖：engine_modes 參數只含 demo。
    assert params[0] == ["demo"]
    assert "engine_mode = ANY" in sql
    # 效能修法後直查 base 表，attribution 由「結構性條件」取代 view 的
    # attribution_chain_ok 旗標（MIT RCA 2026-06-14；demo label-present row 等價）：
    #   signal_id / context_id 非空 + df.label_net_edge_bps 存在。
    assert "label_net_edge_bps IS NOT NULL" in sql
    assert "i.signal_id IS NOT NULL" in sql
    assert "i.context_id IS NOT NULL" in sql
    # post-fee reward 欄（直查 base 表時以 net_bps_after_fee 別名輸出）。
    assert "net_bps_after_fee" in sql


def test_reward_source_sql_no_forbidden_tokens():
    rows = []
    connect, captured = _make_fake_connect(rows)
    fetch_demo_arm_rewards("FAKE_DSN", _connect=connect)
    sql, _ = captured["conn"].cur.executed[-1]
    # 不可走 decision_outcomes（NULL bug）/ 不可洩 live。
    assert "decision_outcomes" not in sql
    assert "outcome_net_bps" not in sql
    assert "'live'" not in sql


def test_reward_source_sql_drops_signals_lateral_queries_base_tables():
    """效能修法 regression-lock（MIT RCA 2026-06-14）。

    為什麼鎖死：view 的 trading.signals signal_id-only LATERAL 在壓縮 chunk 上
    per-outer-row bulk-decompress，30d demo 實測 3827s（64 分）。修法砍掉它、直查
    base 表（intents JOIN decision_features）並保留走 PK 的 decision_context_snapshots
    lateral 取 regime（962ms / ~3975x，行為等價）。本測試固定這個查詢形狀，防後人
    退回 view 或重新引入 signals 讀取。
    """
    connect, captured = _make_fake_connect([])
    fetch_demo_arm_rewards("FAKE_DSN", _connect=connect)
    sql, params = captured["conn"].cur.executed[-1]
    # 砍 signals lateral：不得再讀 trading.signals，也不得走 view。
    assert "trading.signals" not in sql
    assert "mlde_edge_training_rows" not in sql
    # 直查 base 表 + 走 PK 的 dcs lateral。
    assert "trading.intents" in sql
    assert "learning.decision_features" in sql
    assert "trading.decision_context_snapshots" in sql
    # 參數簽名不變（engine_modes, max_age_days, max_age_days）= 3 個。
    assert len(params) == 3
    assert params[0] == ["demo"]
    assert params[1] == params[2] == 30  # 預設 max_age_days


def test_reward_source_skips_null_arm_id():
    rows = [
        (None, "x", "trending", 5.0, 1.0),
        ("mean_reverting__grid_trading", "grid_trading", "mean_reverting", 1.0, 2.0),
    ]
    connect, _ = _make_fake_connect(rows)
    out = fetch_demo_arm_rewards("FAKE_DSN", _connect=connect)
    assert len(out) == 1
    # arm_id 用 allocator 詞彙重建：mean_reverting -> range。
    assert out[0].arm_id == make_arm_id("range", "grid_trading")


def test_advisory_strategy_scores_sql_is_demo_readonly_positive_evidence():
    rows = [("grid_trading", 4.25)]
    connect, captured = _make_fake_connect(rows)
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        controlled_experiment_enabled=True,
        require_advisory_for_explore=True,
        advisory_sources=["ml_shadow", "dream_engine"],
        advisory_min_confidence=0.5,
        advisory_min_expected_net_bps=0.0,
        advisory_min_sample_count=10,
        advisory_allow_requires_governance=False,
    )
    out = fetch_recent_advisory_strategy_scores("FAKE_DSN", cfg, _connect=connect)
    assert out == {"grid_trading": 4.25}

    executed = captured["conn"].cur.executed
    sql, params = next(
        (s, p) for s, p in executed if "FROM learning.mlde_shadow_recommendations" in s
    )
    assert "FROM learning.mlde_shadow_recommendations" in sql
    assert "recommendation_type IN ('rank', 'parameter_proposal')" in sql
    assert "NOT COALESCE(requires_governance, false)" in sql
    assert params[0] == "demo"
    assert params[2] == ["dream_engine", "ml_shadow"]
    lessons_sql, lessons_params = next(
        (s, p) for s, p in executed if "FROM agent.lessons" in s
    )
    assert "source = 'ml_advisory'" in lessons_sql
    assert "lesson_type = 'hypothesize'" in lessons_sql
    assert "content LIKE %s" in lessons_sql
    assert lessons_params == (48, "ml_advisory:hypothesize:%")


def test_advisory_strategy_scores_reads_only_math_gate_pass_lessons():
    def _lesson(strategy, verdict="pass", engine_mode="demo"):
        body = {
            "ml_advisory_mode": "hypothesize",
            "engine_mode": engine_mode,
            "strategy_name": strategy,
            "advisory": {
                "gate_verdict": verdict,
                "math_gate": {"verdict": verdict},
            },
        }
        return "ml_advisory:hypothesize: " + json.dumps(body)

    rowsets = [
        [("grid_trading", 4.25)],  # learning.mlde_shadow_recommendations
        [
            (_lesson("ma_crossover", "pass"),),
            (_lesson("bb_reversion", "DEFER"),),
            (_lesson("grid_trading", "pass"),),  # mlde score should remain max.
            (_lesson("bb_breakout", "pass", engine_mode="live"),),
            ("ml_advisory:diagnose_leak: {}",),
            ("ml_advisory:hypothesize: {bad json",),
        ],
    ]
    connect, _captured = _make_fake_connect_scripted(rowsets)
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        controlled_experiment_enabled=True,
        require_advisory_for_explore=True,
        advisory_sources=["dream_engine"],
    )

    out = fetch_recent_advisory_strategy_scores("FAKE_DSN", cfg, _connect=connect)

    assert out == {
        "grid_trading": 4.25,
        "ma_crossover": 1.0,
    }


# ---------------------------------------------------------------------------
# 非 vacuous 端到端 vocab 連通整合測試（修 E2 RETURN 的核心證據）
#
# E2 抓的缺陷：reward_source 真路徑產出的 arm_id（view 詞彙）與 allocator
# allocate() 期望的 candidate_arm 詞彙從未驗證一致 → 真路徑上 arm 可能被靜默
# 丟棄 → 永遠 flat。本節用「符合 mlde_edge_training_rows 真 schema 的 fake DB row
# （view 詞彙 linucb_arm_id）→ reward_source.fetch_demo_arm_rewards → allocator.ingest
# → allocate(regime, candidate_arms) → 斷言該 arm 真的拿到權重」證明 vocab 在真路徑連通。
# 全程走 reward_source 真輸出格式 + 真 runner discover/allocate，不手造 allocator 詞彙
# arm_id、不繞過任何 seam。
# ---------------------------------------------------------------------------


# V031:326 的真 view 列形狀：
#   (linucb_arm_id, strategy_name, regime, net_bps_after_fee, ts_secs)
#   linucb_arm_id = regime_norm || '__' || strategy_name_norm（view 詞彙 regime）
#   regime        = regime_norm（同 view 詞彙）
# 注意：linucb_arm_id 的 regime 段是 'mean_reverting'（view 詞彙），**不是** allocator
# 詞彙的 'range'——這正是真路徑與舊 vacuous 測試的分歧點。
def _real_schema_view_row(view_regime, strategy, net_bps, ts_secs):
    return (f"{view_regime}__{strategy}", strategy, view_regime, net_bps, ts_secs)


def test_e2e_real_view_vocab_arm_reaches_allocator_weight_not_dropped():
    # 60 筆強正 PnL 的 grid_trading round-trip，view regime = mean_reverting
    # （→ allocator 詞彙 'range'）。樣本足夠跨過 explore_budget 並讓歸零閘放行。
    rows = [
        _real_schema_view_row("mean_reverting", "grid_trading", 45.0, float(i))
        for i in range(60)
    ]
    connect, _ = _make_fake_connect(rows)

    # rewards_fn 走真 reward_source（不手造 ArmReward）：這是「真路徑」的入口。
    def _rewards():
        return fetch_demo_arm_rewards("FAKE_DSN", _connect=connect)

    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],   # mean_reverting 映射後的 allocator regime
        candidate_strategies=[],       # 不顯式補候選 → 候選只能來自 reward 真路徑
        include_demo_maker_arm=False,  # 隔離：只測 view 路徑的 arm 連通
        rng_seed=11,
    )
    lever, calls = _record_lever({"grid_trading": False})
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=_rewards)

    report = runner.run_cycle(dry_run=False)

    # (1) reward 真的被 ingest（非 0 → 沒在 fetch / ingest 階段被丟）。
    assert report.n_rewards_ingested == 60
    # (2) 該 arm 真的拿到權重、成為 active winner（非被靜默丟棄、非永遠 flat）。
    #     若 vocab 不連通（舊 bug：arm_id 嵌 'mean_reverting' 不在 VALID_REGIMES），
    #     _discover_candidate_arms 會丟掉它 → desired 為空 → 此斷言紅。
    assert report.desired_active.get("grid_trading") is True
    assert report.all_regimes_flat is False
    # (3) 真發一筆 IPC 把該策略開啟（端到端落地，非空轉）。
    assert ("grid_trading", True) in calls
    # (4) 該 arm 確實出現在某 regime 的候選決策裡且權重 > 0（直接證 allocate 沒丟）。
    winner_decisions = [
        d for d in report.candidate_decisions
        if d.strategy == "grid_trading" and d.weight > 0.0
    ]
    assert winner_decisions, "grid_trading arm 應在 allocate 後拿到正權重，卻被丟棄"
    # 候選 arm_id 的 regime 段必是 allocator 詞彙（range），證 reconstructed vocab 一致。
    assert winner_decisions[0].arm_id == make_arm_id("range", "grid_trading")


def test_e2e_vacuous_guard_view_vocab_arm_id_in_candidates():
    # 直接在 reward_source ↔ runner._discover_candidate_arms 邊界證 vocab 連通：
    # 真路徑產出的 arm_id 必能被 runner 解析回 allocator candidate_regime 並入候選桶。
    # 這是「vocab 端到端一致」的最小可分離斷言（不依賴 Thompson 抽樣結果）。
    rows = [_real_schema_view_row("random_walk", "ma_crossover", 10.0, 1.0)]
    connect, _ = _make_fake_connect(rows)
    rewards = fetch_demo_arm_rewards("FAKE_DSN", _connect=connect)
    assert len(rewards) == 1
    r = rewards[0]
    # random_walk -> chop；arm_id 重建為 allocator 詞彙。
    assert r.regime == "chop"
    assert r.arm_id == make_arm_id("chop", "ma_crossover")

    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["chop"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        rng_seed=1,
    )
    lever, _calls = _record_lever({})
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: rewards)
    # 走真 discover（不繞過）：reward arm_id 必落進 'chop' 候選桶（非被丟棄）。
    by_regime = runner._discover_candidate_arms({r.arm_id})
    assert r.arm_id in by_regime.get("chop", []), (
        "reward_source 真輸出的 arm_id 未進 allocator candidate 桶 = vocab 斷鏈"
    )


def test_e2e_mutation_raw_view_arm_id_would_be_dropped():
    # Mutation bite：證若 reward_source 退回「原樣沿用 view linucb_arm_id」（舊 bug），
    # 該 arm 會被 runner._discover_candidate_arms 靜默丟棄 → 真路徑永遠 flat。
    # 這條測試固定了「為什麼必須 reconstruct」的反事實，防後人退回舊寫法。
    view_arm_id = "mean_reverting__grid_trading"  # 舊 bug：view 詞彙原樣當 arm_id
    raw_reward = ArmReward(
        arm_id=view_arm_id,            # 模擬退回 raw view arm_id
        regime="range",               # regime 欄仍對齊（與舊 bug 一致：自相矛盾）
        realized_pnl_bps=45.0,
        ts=1.0,
        fill_realism_tier=FILL_TIER_TAKER_REAL,
    )
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        rng_seed=1,
    )
    lever, _calls = _record_lever({})
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: [raw_reward])
    by_regime = runner._discover_candidate_arms({raw_reward.arm_id})
    # 'mean_reverting' 不在 VALID_REGIMES → arm 被丟，'range' 桶空（證舊 bug 真會 flat）。
    assert view_arm_id not in by_regime.get("range", [])
    assert by_regime.get("range", []) == []


# ---------------------------------------------------------------------------
# ipc_lever：冪等 diff / fail-safe / 失敗不重試
# ---------------------------------------------------------------------------


def _record_lever(current):
    calls = []

    def _set(s, a):
        calls.append((s, a))
        return {"ok": True}

    def _read():
        return dict(current)

    return StrategyLever(set_active_fn=_set, read_states_fn=_read), calls


def test_lever_idempotent_diff_only_fires_on_change():
    lever, calls = _record_lever({"A": True, "B": False, "C": True})
    res = lever.apply_desired(
        {"A": True, "B": True, "C": False}, dry_run=False
    )
    # A 現態==期望 → 不發；B / C 變更 → 發。
    assert ("A", True) not in calls
    assert ("B", True) in calls
    assert ("C", False) in calls
    assert res.applied_count == 2


def test_lever_fail_safe_unknown_current_want_off_skipped():
    lever, calls = _record_lever({})  # snapshot 空（引擎未跑）
    res = lever.apply_desired({"D": False}, dry_run=False)
    # 現態未知 + 想關 → fail-safe 不主動關。
    assert calls == []
    assert res.changes[0].status == "skipped_unknown"


def test_lever_fail_safe_unknown_current_want_on_applies():
    lever, calls = _record_lever({})
    res = lever.apply_desired({"E": True}, dry_run=False)
    # 現態未知 + 想開 → 發（開是安全方向）。
    assert ("E", True) in calls
    assert res.applied_count == 1


def test_lever_dry_run_does_not_fire_ipc():
    lever, calls = _record_lever({"A": False})
    res = lever.apply_desired({"A": True}, dry_run=True)
    assert calls == []
    assert res.changes[0].status == "dry_run"


def test_lever_ipc_failure_no_hidden_retry():
    def _failset(s, a):
        raise ConnectionError("engine down")

    lever = StrategyLever(set_active_fn=_failset, read_states_fn=lambda: {"X": False})
    res = lever.apply_desired({"X": True}, dry_run=False)
    # 失敗只記 failed，無重試（changes 只 1 筆）。
    assert len(res.changes) == 1
    assert res.changes[0].status == "failed"
    assert res.failed_count == 1


def test_default_set_active_wire_carries_engine_demo(monkeypatch):
    """Phase 0 AUTH-1 re-review MED 回歸：_default_set_active 的 production wire 必帶
    engine="demo"。set_strategy_active 屬 LIVE_WRITE_METHODS，省 engine 會在 true-live
    primary 引擎被解析成 live → fail-closed 拒（demo lever 失效）+ 潛在 demo→live 誤投。
    """
    from program_code.ml_training.adaptive_demo_profit_engine import ipc_lever as _lever

    captured: dict[str, object] = {}

    def _fake_sync_ipc_call(method, params):
        captured["method"] = method
        captured["params"] = dict(params)
        return {"ok": True}

    # 攔截 lazy-import 的 sync_ipc_call（直接 patch 其源模組屬性）。
    import program_code.exchange_connectors.bybit_connector.control_api_v1.app.ipc_client_sync as _ics  # noqa: E501

    monkeypatch.setattr(_ics, "sync_ipc_call", _fake_sync_ipc_call)

    resp = _lever._default_set_active("grid_trading", True)

    assert resp == {"ok": True}
    assert captured["method"] == "set_strategy_active"
    assert captured["params"].get("engine") == "demo"
    assert captured["params"]["strategy_name"] == "grid_trading"
    assert captured["params"]["active"] is True


# ---------------------------------------------------------------------------
# runner：engine_mode 硬鎖 / 全負歸零 / dry-run / 贏家活化
# ---------------------------------------------------------------------------


def _runner(engine_mode="demo", rewards=None, current_state=None, seed=7):
    cfg = AdpeRunnerConfig(
        engine_mode=engine_mode,
        candidate_regimes=["range", "chop"],
        candidate_strategies=[],
        rng_seed=seed,
    )
    lever, calls = _record_lever(current_state or {})
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: list(rewards or []))
    return runner, calls


def test_runner_engine_mode_hard_lock_rejects_non_demo():
    runner, _ = _runner(engine_mode="live")
    with pytest.raises(RuntimeError, match="demo"):
        runner.run_cycle()


def test_runner_engine_mode_hard_lock_rejects_mainnet_like():
    runner, _ = _runner(engine_mode="paper")
    with pytest.raises(RuntimeError):
        runner.run_cycle()


def test_runner_all_negative_ev_converges_to_dormant():
    neg_arm = make_arm_id("range", "bb_reversion")
    rewards = [
        ArmReward(neg_arm, "range", -30.0, float(i), FILL_TIER_TAKER_REAL)
        for i in range(60)
    ]
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,  # 隔離：只測純負 arm
        rng_seed=3,
    )
    lever, calls = _record_lever({"bb_reversion": True})
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: rewards)
    report = runner.run_cycle(dry_run=False)
    # 全負 EV → 該策略 desired=False（歸零）。
    assert report.desired_active.get("bb_reversion") is False
    assert report.all_regimes_flat is True
    # 現態 True → 真發一筆關。
    assert ("bb_reversion", False) in calls


def test_runner_positive_arm_becomes_active_winner():
    pos_arm = make_arm_id("range", "grid_trading")
    rewards = [
        ArmReward(pos_arm, "range", 45.0, float(i), FILL_TIER_TAKER_REAL)
        for i in range(60)
    ]
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        rng_seed=5,
    )
    lever, calls = _record_lever({"grid_trading": False})
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: rewards)
    report = runner.run_cycle(dry_run=False)
    assert report.desired_active.get("grid_trading") is True
    assert report.all_regimes_flat is False
    assert ("grid_trading", True) in calls


def test_runner_dry_run_default_no_ipc():
    pos_arm = make_arm_id("range", "grid_trading")
    rewards = [
        ArmReward(pos_arm, "range", 45.0, float(i), FILL_TIER_TAKER_REAL)
        for i in range(60)
    ]
    runner, calls = _runner(rewards=rewards, current_state={"grid_trading": False})
    report = runner.run_cycle(dry_run=True)
    assert calls == []
    assert report.dry_run is True


def test_runner_demo_maker_arm_saw_artifact_isolated():
    # demo-maker artifact ingest → transferable_only 不吸收、all_fills 標 saw_artifact。
    runner, _ = _runner(rewards=[], current_state={})
    runner.ingest_demo_maker_outcome(80.0, 100.0)
    from program_code.ml_training.adaptive_demo_profit_engine.demo_maker_arm import (
        DEMO_MAKER_ARM,
    )

    diag_tr = runner.allocator.arm_diagnostics(
        DEMO_MAKER_ARM.arm_id, track="transferable_only"
    )
    diag_all = runner.allocator.arm_diagnostics(
        DEMO_MAKER_ARM.arm_id, track="all_fills"
    )
    assert diag_tr["n_trials"] == 0
    assert diag_all["saw_artifact"] is True


# ---------------------------------------------------------------------------
# explore-eligible 保活（修 ADPE 活化缺口）
#
# 缺口：build_desired_active 原本只把 winner→active、其餘→dormant；rich-signal 下
# all-flat 會把全策略停用 → 無單 → demo explore-gate 永不觸發 → 學習器饑餓。
# 修：enable_explore_sink=True 時，desired = winners ∪ explore-eligible（任一 arm
# explore_budget_remaining>0）。有界：explore_remaining=0 不保活。explore 關→純 winner。
# ---------------------------------------------------------------------------


def test_explore_keeps_undersampled_strategy_active_when_all_flat():
    # all-flat（負 EV → winner 全空）但該 arm explore 額度未耗盡（n_trials 少 < 30）：
    # 開 explore_sink → 策略仍保 active（供 explore-gate 放行）。
    neg_arm = make_arm_id("range", "grid_trading")
    # 少量負樣本：n_trials 遠小於 explore_budget=30 → explore_budget_remaining>0。
    rewards = [
        ArmReward(neg_arm, "range", -30.0, float(i), FILL_TIER_TAKER_REAL)
        for i in range(3)
    ]
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        enable_explore_sink=True,  # 開 explore 保活
        rng_seed=3,
    )
    lever, calls = _record_lever({"grid_trading": False})
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: rewards)
    # 前置確認：該 arm 真的還在探索期（讀真實 allocator 信號，非寫死）。
    for r in rewards:
        runner.allocator.ingest_arm_outcome(
            arm_id=r.arm_id, regime=r.regime,
            realized_pnl_bps=r.realized_pnl_bps, ts=r.ts,
            fill_realism_tier=r.fill_realism_tier,
        )
    assert runner.allocator.explore_budget_remaining(neg_arm) > 0
    # 重建 runner（上面 ingest 只為斷言前置，避免雙重 ingest 污染 cycle）。
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: rewards)

    report = runner.run_cycle(dry_run=False)
    # winner 視角仍 all-flat（負 EV），但 explore 保活 → 策略 desired=True。
    assert report.all_regimes_flat is True
    assert report.desired_active.get("grid_trading") is True
    # 現態 False → 真發一筆開（讓它產單供 explore-gate 放行）。
    assert ("grid_trading", True) in calls


def test_explore_exhausted_arm_not_kept_active_bounded():
    # 有界：explore 額度耗盡（n_trials >= explore_budget=30 → remaining==0）且負 EV：
    # 即使開 explore_sink 也不保活（耗盡即停，非全放行）。
    neg_arm = make_arm_id("range", "bb_reversion")
    # 60 筆 >> explore_budget=30 → explore_budget_remaining==0。
    rewards = [
        ArmReward(neg_arm, "range", -30.0, float(i), FILL_TIER_TAKER_REAL)
        for i in range(60)
    ]
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        enable_explore_sink=True,
        rng_seed=3,
    )
    lever, calls = _record_lever({"bb_reversion": True})
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: rewards)
    report = runner.run_cycle(dry_run=False)
    # 探索額度耗盡 + 負 EV → 不保活（歸零）。
    assert report.desired_active.get("bb_reversion") is False
    assert report.all_regimes_flat is True
    # 證額度真的耗盡（讀真實信號）。
    assert runner.allocator.explore_budget_remaining(neg_arm) == 0
    # 現態 True → 真發一筆關。
    assert ("bb_reversion", False) in calls


def test_explore_disabled_pure_winner_behavior_unchanged():
    # explore 關（預設）：under-sampled 負 EV arm 不保活 → 純 winner 行為不變。
    neg_arm = make_arm_id("range", "grid_trading")
    rewards = [
        ArmReward(neg_arm, "range", -30.0, float(i), FILL_TIER_TAKER_REAL)
        for i in range(3)  # under-sampled，但 explore 關
    ]
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        enable_explore_sink=False,  # explore 關
        rng_seed=3,
    )
    lever, _calls = _record_lever({"grid_trading": True})
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: rewards)
    report = runner.run_cycle(dry_run=False)
    # explore 關 → 即使 under-sampled 也不保活（負 EV 歸零）。
    assert report.desired_active.get("grid_trading") is False
    assert report.all_regimes_flat is True


def test_controlled_experiment_requires_advisory_before_explore_keepalive():
    neg_arm = make_arm_id("range", "grid_trading")
    rewards = [
        ArmReward(neg_arm, "range", -30.0, float(i), FILL_TIER_TAKER_REAL)
        for i in range(3)
    ]
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        enable_explore_sink=True,
        controlled_experiment_enabled=True,
        require_advisory_for_explore=True,
        rng_seed=3,
    )
    lever, calls = _record_lever({"grid_trading": True})
    runner = AdpeRunner(
        cfg,
        lever=lever,
        rewards_fn=lambda: rewards,
        advisory_fn=lambda: {},  # no L2 / multi-agent positive evidence
    )

    report = runner.run_cycle(dry_run=False)

    assert report.all_regimes_flat is True
    assert report.desired_active.get("grid_trading") is False
    assert ("grid_trading", False) in calls
    assert report.experiment_policy["selected_explore"] == []
    assert (
        report.experiment_policy["rejected_explore"]["grid_trading"]
        == "missing_positive_advisory_evidence"
    )


def test_controlled_experiment_caps_explore_and_blocks_retired_strategy():
    grid_arm = make_arm_id("range", "grid_trading")
    ma_arm = make_arm_id("range", "ma_crossover")
    funding_arm = make_arm_id("range", "funding_arb")
    rewards = []
    for i, arm in enumerate([grid_arm, ma_arm, funding_arm]):
        rewards.extend(
            ArmReward(arm, "range", -20.0, float(i * 10 + j), FILL_TIER_TAKER_REAL)
            for j in range(3)
        )
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        enable_explore_sink=True,
        controlled_experiment_enabled=True,
        require_advisory_for_explore=True,
        retired_strategy_blocklist=["funding_arb"],
        explore_strategy_allowlist=["grid_trading", "ma_crossover", "funding_arb"],
        max_active_explore_strategies=1,
        rng_seed=4,
    )
    lever, calls = _record_lever(
        {"grid_trading": False, "ma_crossover": False, "funding_arb": True}
    )
    runner = AdpeRunner(
        cfg,
        lever=lever,
        rewards_fn=lambda: rewards,
        advisory_fn=lambda: {
            "grid_trading": 6.0,
            "ma_crossover": 3.0,
            "funding_arb": 99.0,  # even strongest evidence cannot revive retired strategy
        },
    )

    report = runner.run_cycle(dry_run=False)

    assert report.all_regimes_flat is True
    assert report.desired_active["grid_trading"] is True
    assert report.desired_active["ma_crossover"] is False
    assert report.desired_active["funding_arb"] is False
    assert ("grid_trading", True) in calls
    assert ("funding_arb", False) in calls
    assert report.experiment_policy["selected_explore"] == ["grid_trading"]
    assert (
        report.experiment_policy["rejected_explore"]["ma_crossover"]
        == "max_active_explore_strategies_cap"
    )
    assert (
        report.experiment_policy["rejected_explore"]["funding_arb"]
        == "retired_strategy_blocklist"
    )
    assert report.experiment_policy["forced_dormant"] == ["funding_arb"]


def test_side_edge_evidence_keeps_ma_alive_and_drops_advisory_only_grid(tmp_path):
    grid_arm = make_arm_id("range", "grid_trading")
    ma_arm = make_arm_id("range", "ma_crossover")
    rewards = []
    for i, arm in enumerate([grid_arm, ma_arm]):
        rewards.extend(
            ArmReward(arm, "range", -20.0, float(i * 10 + j), FILL_TIER_TAKER_REAL)
            for j in range(3)
        )
    edge_path = tmp_path / "edge_estimates.json"
    edge_path.write_text(
        json.dumps(
            {
                "ma_crossover::UNIUSDT::Buy": {
                    "runtime_bps": 32.0,
                    "win_rate": 1.0,
                    "n": 1,
                },
                # Rust demo gate blocks low-sample grid even if the side mean is
                # positive, so ADPE must not treat it as cost-viable keepalive.
                "grid_trading::XRPUSDT::Buy": {
                    "runtime_bps": 50.0,
                    "win_rate": 1.0,
                    "n": 3,
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        enable_explore_sink=True,
        controlled_experiment_enabled=True,
        require_advisory_for_explore=True,
        use_edge_snapshot_for_explore_evidence=True,
        require_cost_viable_edge_for_explore_when_available=True,
        explore_strategy_allowlist=["grid_trading", "ma_crossover"],
        max_active_explore_strategies=2,
        rng_seed=5,
    )
    lever, calls = _record_lever({"grid_trading": True, "ma_crossover": False})
    runner = AdpeRunner(
        cfg,
        lever=lever,
        rewards_fn=lambda: rewards,
        advisory_fn=lambda: {"grid_trading": 9.0},
        edge_estimates_path=str(edge_path),
    )

    report = runner.run_cycle(dry_run=False)

    assert report.all_regimes_flat is True
    assert report.desired_active["ma_crossover"] is True
    assert report.desired_active["grid_trading"] is False
    assert ("ma_crossover", True) in calls
    assert ("grid_trading", False) in calls
    assert report.experiment_policy["selected_explore"] == ["ma_crossover"]
    assert (
        report.experiment_policy["rejected_explore"]["grid_trading"]
        == "missing_cost_viable_edge_evidence"
    )
    assert report.experiment_policy["edge_evidence_scores"]["ma_crossover"] == pytest.approx(
        17.7,
        abs=1e-6,
    )


def test_under_cost_side_edge_is_not_positive_explore_evidence(tmp_path):
    ma_arm = make_arm_id("range", "ma_crossover")
    rewards = [
        ArmReward(ma_arm, "range", -20.0, float(i), FILL_TIER_TAKER_REAL)
        for i in range(3)
    ]
    edge_path = tmp_path / "edge_estimates.json"
    edge_path.write_text(
        json.dumps(
            {
                "ma_crossover::DOTUSDT::Sell": {
                    "runtime_bps": 16.0,
                    "win_rate": 2.0 / 3.0,
                    "n": 3,
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = AdpeRunnerConfig(
        engine_mode="demo",
        candidate_regimes=["range"],
        candidate_strategies=[],
        include_demo_maker_arm=False,
        enable_explore_sink=True,
        controlled_experiment_enabled=True,
        require_advisory_for_explore=True,
        use_edge_snapshot_for_explore_evidence=True,
        explore_strategy_allowlist=["ma_crossover"],
        max_active_explore_strategies=2,
        rng_seed=6,
    )
    lever, calls = _record_lever({"ma_crossover": True})
    runner = AdpeRunner(
        cfg,
        lever=lever,
        rewards_fn=lambda: rewards,
        advisory_fn=lambda: {},
        edge_estimates_path=str(edge_path),
    )

    report = runner.run_cycle(dry_run=False)

    assert report.all_regimes_flat is True
    assert report.desired_active["ma_crossover"] is False
    assert ("ma_crossover", False) in calls
    assert report.experiment_policy["edge_evidence_scores"] == {}
    assert (
        report.experiment_policy["rejected_explore"]["ma_crossover"]
        == "missing_positive_advisory_evidence"
    )


def test_explore_mutation_bite_winner_only_drops_undersampled():
    # Mutation bite：直接在 build_desired_active 邊界對比。同一 under-sampled
    # 負 EV arm，explore 開→保活、explore 關→不保活，鎖死修復語義（防後人退回純 winner）。
    neg_arm = make_arm_id("range", "ma_crossover")
    rewards = [
        ArmReward(neg_arm, "range", -25.0, float(i), FILL_TIER_TAKER_REAL)
        for i in range(2)
    ]

    def _build(explore_on):
        cfg = AdpeRunnerConfig(
            engine_mode="demo",
            candidate_regimes=["range"],
            candidate_strategies=[],
            include_demo_maker_arm=False,
            enable_explore_sink=explore_on,
            rng_seed=9,
        )
        lever, _c = _record_lever({})
        runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: rewards)
        for r in rewards:
            runner.allocator.ingest_arm_outcome(
                arm_id=r.arm_id, regime=r.regime,
                realized_pnl_bps=r.realized_pnl_bps, ts=r.ts,
                fill_realism_tier=r.fill_realism_tier,
            )
        by_regime = runner._discover_candidate_arms({neg_arm})
        desired, _d, _f = runner.build_desired_active(by_regime)
        return desired

    desired_on = _build(True)
    desired_off = _build(False)
    # explore 開：under-sampled arm 保活；關：不保活。差異 = 修復生效證據。
    assert desired_on.get("ma_crossover") is True
    assert desired_off.get("ma_crossover") is False


# ---------------------------------------------------------------------------
# kill switch
# ---------------------------------------------------------------------------


def test_kill_switch_snapshot_and_restore():
    state = {"A": True, "B": False}

    def _read():
        return dict(state)

    def _set(s, a):
        state[s] = a
        return {"ok": True}

    lever = StrategyLever(set_active_fn=_set, read_states_fn=_read)
    cfg = AdpeRunnerConfig(engine_mode="demo")
    runner = AdpeRunner(cfg, lever=lever, rewards_fn=lambda: [])

    snap = runner.kill_switch_snapshot()
    assert snap == {"A": True, "B": False}

    # 模擬 runner 改動 active 態。
    state["A"] = False
    state["B"] = True
    state["C"] = True

    runner.kill_switch(snap, dry_run=False)
    # A / B 還原成快照；C 不在快照不碰。
    assert state["A"] is True
    assert state["B"] is False
    assert state["C"] is True


def test_kill_switch_dry_run_does_not_mutate():
    state = {"A": True}

    def _read():
        return dict(state)

    def _set(s, a):
        state[s] = a
        return {"ok": True}

    lever = StrategyLever(set_active_fn=_set, read_states_fn=_read)
    runner = AdpeRunner(AdpeRunnerConfig(engine_mode="demo"), lever=lever, rewards_fn=lambda: [])
    snap = runner.kill_switch_snapshot()
    state["A"] = False  # 偏離快照
    runner.kill_switch(snap, dry_run=True)
    # dry-run 不真發 → state 不被還原。
    assert state["A"] is False

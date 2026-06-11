"""alpha_wealth_refund_reconciler 單元測試（P4 E1-C）。

隔離鐵則（PA §8.2，承 2026-06-10 prod 污染 RCA）：
  - conn 全 fake 注入；0 真 DSN / 0 fallback 連線；不經 main()。
  - A 線 controller（learning_engine.alpha_wealth_controller）以 sys.modules
    dual-patch stub（模組在 A 線分支，本分支尚無檔；fake 鏡像真值表 = 真實
    上游 boundary 不變量）。
  - round_trip_loader 注入縫（不 monkeypatch 命名空間）。
  - dead_mode 的 retrieve_lessons 真查（pg_trgm）標註 owed-E4 Linux，
    不放單元測試（INSERT 成功不算數的驗收在 E4 段）。
"""

from __future__ import annotations

import math
import sys
import types
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# repo 路徑：tests → ml_training → program_code → srv root。
_REPO_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(_REPO_ROOT), str(_REPO_ROOT / "program_code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from program_code.ml_training import alpha_wealth_refund_reconciler as rec  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fake A 線 controller（鏡像 demo_confirm_verdict 真值表 = 上游 boundary 不變量）
# ─────────────────────────────────────────────────────────────────────────────

def _fake_demo_confirm_verdict(*, n_trades, stage0r_green, demo_net_bps, forward_oos_days):
    if n_trades < 30:
        return "pending"
    if not stage0r_green:
        return "failed"
    if not math.isfinite(demo_net_bps):
        return "pending"
    if demo_net_bps < 0.0:
        return "failed"
    if forward_oos_days >= 21:
        return "confirmed"
    return "pending"


def _make_fake_controller() -> types.ModuleType:
    mod = types.ModuleType("alpha_wealth_controller")
    mod.PHI_REFUND = 1.0
    mod.MIN_FORWARD_OOS_DAYS = 21
    mod.REFUND_MIN_TRADES = 30
    mod.demo_confirm_verdict = _fake_demo_confirm_verdict
    mod.refund_amount = lambda alpha_debited, phi=1.0: phi * alpha_debited
    return mod


@pytest.fixture()
def fake_controller(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """dual-patch sys.modules + package attr（`from PKG import SUB` 慣例教訓）。"""
    mod = _make_fake_controller()
    import program_code.learning_engine as le_pkg

    monkeypatch.setitem(
        sys.modules, "program_code.learning_engine.alpha_wealth_controller", mod
    )
    monkeypatch.setitem(sys.modules, "learning_engine.alpha_wealth_controller", mod)
    monkeypatch.setattr(le_pkg, "alpha_wealth_controller", mod, raising=False)
    le_alias = sys.modules.get("learning_engine")
    if le_alias is not None:
        monkeypatch.setattr(le_alias, "alpha_wealth_controller", mod, raising=False)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# Fake conn / cursor：SQL 子串路由 → 腳本化回應；全程記錄 execute。
# ─────────────────────────────────────────────────────────────────────────────

class _FakeCursor:
    def __init__(self, owner: "_FakeConn"):
        self._owner = owner
        self._pending_result: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql: str, params=None):
        self._owner.executed.append((sql, params))
        text = " ".join(sql.split())
        for key, responder in self._owner.routes:
            if key in text:
                out = responder(params) if callable(responder) else responder
                self._pending_result = list(out or [])
                return
        self._pending_result = []

    def fetchone(self):
        return self._pending_result[0] if self._pending_result else None

    def fetchall(self):
        return list(self._pending_result)

    @property
    def rowcount(self) -> int:
        return len(self._pending_result) if self._pending_result else 1


class _FakeConn:
    """routes = [(sql 子串, rows | callable(params)->rows)]，首配優先。"""

    def __init__(self, routes):
        self.routes = routes
        self.executed: list[tuple] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **_kw):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    # 便利斷言
    def inserts(self, table_token: str) -> list[tuple]:
        return [
            (sql, params) for sql, params in self.executed
            if "INSERT INTO " + table_token in " ".join(sql.split())
        ]


_NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
_DEPLOYED = _NOW - timedelta(days=30)

_DEBIT_ROW = (
    "dbt-1",                      # debit_id
    "ml_advisory:funding",        # family_id
    7,                            # pre_reg_id
    Decimal("0.0005000000"),      # alpha_i
    3,                            # n_eff
    _DEPLOYED - timedelta(days=2),  # debited_at
    "ml_advisory",                # capability_id
    "funding",                    # signal_axis
    Decimal("-0.0005000000"),     # amount
)


def _routes(
    *,
    deployed: bool = True,
    pending=( _DEBIT_ROW, ),
    binding=("grid_trading", "BTCUSDT", _DEPLOYED),
    stage0r=("pass",),
    fresh_amount=Decimal("-0.0005000000"),
    statement=("Funding extreme predicts next-day reversal",),
):
    # 首配優先：INSERT 路由置頂（INSERT SQL 的欄位列含 SELECT 路由的子串，
    # 序錯會誤路由）。
    return [
        ("INSERT INTO research.alpha_wealth_ledger", [(1,)]),
        ("INSERT INTO agent.lessons", [(1,)]),
        ("to_regclass", [(deployed,)]),
        ("FROM research.alpha_wealth_debit_state", list(pending)),
        (
            "SELECT demo_strategy, demo_symbol, demo_deployed_at FROM",
            [binding] if binding else [],
        ),
        ("mlde_shadow_recommendations", [stage0r] if stage0r else []),
        (
            "WHERE debit_id = %(debit_id)s AND event_type = 'debit'",
            [(fresh_amount, "ml_advisory:funding", "ml_advisory", "funding", 7)],
        ),
        ("FROM research.pre_registered_hypotheses", [statement] if statement else []),
        ("SAVEPOINT", []),
        ("RELEASE", []),
        ("ROLLBACK TO", []),
    ]


def _trips(n: int, net: float) -> list[dict[str, float]]:
    return [{"entry_ts": 1.0, "exit_ts": 2.0, "net_bps": net} for _ in range(n)]


# ─────────────────────────────────────────────────────────────────────────────
# 測試
# ─────────────────────────────────────────────────────────────────────────────

def test_fdr_tables_absent_skips_everything(fake_controller):
    conn = _FakeConn(_routes(deployed=False))
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=True, round_trip_loader=lambda *a, **k: [],
    )
    assert out["skipped"] == "fdr_tables_not_deployed"
    assert conn.inserts("research.alpha_wealth_ledger") == []
    assert conn.rollbacks == 1  # dry_run 結尾 rollback（零寫入 belt）


def test_no_binding_stays_pending(fake_controller):
    conn = _FakeConn(_routes(binding=None))
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=False, round_trip_loader=lambda *a, **k: [],
    )
    assert out["no_binding"] == 1
    assert conn.inserts("research.alpha_wealth_ledger") == []


def test_stage0r_verdict_missing_stays_pending(fake_controller):
    """preflight 還沒跑 ≠ falsified：不渲染結論、不鑄 dead-mode（QC FIX-1.3 語義）。"""
    conn = _FakeConn(_routes(stage0r=None))
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=False, round_trip_loader=lambda *a, **k: _trips(40, 5.0),
    )
    assert out["stage0r_verdict_missing"] == 1
    assert conn.inserts("research.alpha_wealth_ledger") == []
    assert conn.inserts("agent.lessons") == []


def test_under_min_trades_stays_pending(fake_controller):
    conn = _FakeConn(_routes())
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=False, round_trip_loader=lambda *a, **k: _trips(10, 5.0),
    )
    assert out["still_pending"] == 1
    assert conn.inserts("research.alpha_wealth_ledger") == []


def test_confirmed_inserts_refund_with_phi_amount(fake_controller):
    conn = _FakeConn(_routes())
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=False, round_trip_loader=lambda *a, **k: _trips(40, 5.0),
    )
    assert out["confirmed"] == 1
    inserts = conn.inserts("research.alpha_wealth_ledger")
    assert len(inserts) == 1
    params = inserts[0][1]
    assert params["event_type"] == "refund"
    # φ=1.0：refund 金額恰 = |debit|（Decimal 精確）。
    assert params["amount"] == Decimal("0.0005000000")
    assert params["debit_id"] == "dbt-1"
    assert params["actor_id"] == rec.RECONCILER_ACTOR
    assert '"verdict": "confirmed"' in params["evidence"]
    assert conn.commits == 1


def test_confirmed_dry_run_writes_nothing(fake_controller):
    conn = _FakeConn(_routes())
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=True, round_trip_loader=lambda *a, **k: _trips(40, 5.0),
    )
    assert out["confirmed"] == 1
    assert out["planned_events"] == [
        {"event_type": "refund", "debit_id": "dbt-1", "amount": "0.0005000000"}
    ]
    assert conn.inserts("research.alpha_wealth_ledger") == []
    assert conn.rollbacks == 1
    assert conn.commits == 0


def test_n3_bite_fresh_amount_tamper_aborts(fake_controller):
    """N-3 mutation bite：回查的庫內 debit 金額與掃描快照不符 → abort 該筆，0 INSERT。"""
    conn = _FakeConn(_routes(fresh_amount=Decimal("-0.0009000000")))
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=False, round_trip_loader=lambda *a, **k: _trips(40, 5.0),
    )
    assert out["n3_aborted"] == 1
    assert out["confirmed"] == 0
    assert conn.inserts("research.alpha_wealth_ledger") == []


def test_failed_inserts_debit_failed_and_mints_dead_mode_lesson(fake_controller):
    conn = _FakeConn(_routes())
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=False, round_trip_loader=lambda *a, **k: _trips(40, -8.0),
    )
    assert out["failed"] == 1
    ledger = conn.inserts("research.alpha_wealth_ledger")
    assert len(ledger) == 1
    assert ledger[0][1]["event_type"] == "debit_failed"
    assert ledger[0][1]["amount"] == Decimal("0")

    lessons = conn.inserts("agent.lessons")
    assert len(lessons) == 1
    lp = lessons[0][1]
    # 鏡像 seed_dead_mode_lessons 檢索鏈常數（A5 sentinel whitelist 內）。
    assert lp["source"] == "dead_mode_seed"
    assert lp["symbol"] == "ml_advisory"
    assert lp["lesson_type"] == "dead_mode"
    assert lp["context_id"] == "awl:dbt-1"
    # content 英文主幹（pg_trgm trigram 可檢索）+ 假說本文進 content。
    assert lp["content"].startswith("DEAD MODE [ml_advisory:funding]:")
    assert "Funding extreme predicts next-day reversal" in lp["content"]
    assert "net -8.00 bps < 0" in lp["content"]
    # 冪等錨點：INSERT … WHERE NOT EXISTS（source+context_id）。
    sql = " ".join(lessons[0][0].split())
    assert "WHERE NOT EXISTS" in sql
    assert out["lessons_minted"] == 1


@pytest.mark.parametrize("verdict", ["defer_data", "fail"])
def test_stage0r_non_pass_verdict_stays_pending_zero_dead_mode(fake_controller, verdict):
    """PM 裁決（E2 RETURN 輪）：verdict 非 pass = 證據不足非證偽 → pending。

    gate 字彙 {pass, fail, defer_data}（residual_alpha_gate.py:34）；單配置
    preflight 誠實 defer 下 defer_data 是常態。非 pass 不餵 A 線真值表 False
    臂——否則 demo 表現尚可（net=+5bps）也被鑄 dead-mode lesson，以非結論性
    結果汙染 novelty 庫。斷言：pending（跳過）+ 0 帳本事件 + 0 dead-mode。
    """
    conn = _FakeConn(_routes(stage0r=(verdict,)))
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=False, round_trip_loader=lambda *a, **k: _trips(40, 5.0),
    )
    assert out["stage0r_not_pass"] == 1
    assert out["failed"] == 0
    assert out["confirmed"] == 0
    assert conn.inserts("research.alpha_wealth_ledger") == []
    assert conn.inserts("agent.lessons") == []


def test_failed_only_reachable_via_negative_net(fake_controller):
    """failed 唯一可達路徑 = stage0r pass + demo net<0（PM 裁決閉環斷言）。

    與上測互補：dead-mode lesson 的 why 必為 net<0（stage0r-not-green 文案
    在新映射下結構性不可達——demo_confirm_verdict 只在 green=True 時被呼）。
    """
    conn = _FakeConn(_routes(stage0r=("pass",)))
    out = rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=False, round_trip_loader=lambda *a, **k: _trips(40, -8.0),
    )
    assert out["failed"] == 1
    content = conn.inserts("agent.lessons")[0][1]["content"]
    assert "net -8.00 bps < 0" in content
    assert "stage0r replay preflight not green" not in content


def test_loader_receives_cell_attribution(fake_controller):
    """attribution 紀律：loader 必收 binding 的 strategy + symbol + since=deployed_at。"""
    calls: list[dict] = []

    def loader(conn, strategy, *, engine_mode, since, symbol):
        calls.append({
            "strategy": strategy, "engine_mode": engine_mode,
            "since": since, "symbol": symbol,
        })
        return _trips(40, 5.0)

    conn = _FakeConn(_routes())
    rec.run_alpha_wealth_refund_reconciler(
        conn, now=_NOW, dry_run=True, round_trip_loader=loader,
    )
    assert calls == [{
        "strategy": "grid_trading", "engine_mode": "demo",
        "since": _DEPLOYED, "symbol": "BTCUSDT",
    }]


def test_calendar_days_is_utc_date_diff(fake_controller):
    # 23:50 部署、次日 00:10 觀察 → 1 日曆天（非滿 24h 週期）。
    deployed = datetime(2026, 7, 1, 23, 50, tzinfo=timezone.utc)
    now = datetime(2026, 7, 2, 0, 10, tzinfo=timezone.utc)
    assert rec._calendar_days(now, deployed) == 1
    assert rec._calendar_days(deployed, deployed) == 0


def test_reconciler_enabled_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(rec.RECONCILER_ENV, raising=False)
    assert rec.reconciler_enabled() is False
    monkeypatch.setenv(rec.RECONCILER_ENV, "1")
    assert rec.reconciler_enabled() is True
    monkeypatch.setenv(rec.RECONCILER_ENV, "0")
    assert rec.reconciler_enabled() is False


def test_mean_net_bps_handles_empty_and_nan(fake_controller):
    assert rec._mean_net_bps([]) == 0.0
    assert rec._mean_net_bps(_trips(4, 2.0)) == pytest.approx(2.0)
    assert math.isnan(rec._mean_net_bps([{"net_bps": float("nan")}]))


def test_hard_boundary_fingerprints_zero_hits():
    """grep 指紋 AC（PA §13）：新模組 0 hits on 硬邊界 token。"""
    import re

    forbidden = re.compile(
        r"promote_tier|acquire_lease|IntentProcessor|submit_intent"
        r"|live_execution_allowed|execution_authority|system_mode"
        r"|OPENCLAW_ALLOW_MAINNET|authorization\.json"
    )
    targets = [
        Path(rec.__file__),
        _REPO_ROOT / "helper_scripts" / "db" / "passive_wait_healthcheck"
        / "checks_alpha_wealth_fdr.py",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert not forbidden.search(text), f"hard-boundary token in {path}"
        assert "/home/ncyu" not in text and "/Users/" not in text


def test_load_round_trips_symbol_filter_bites(monkeypatch: pytest.MonkeyPatch):
    """residual_alpha_producer_db.load_round_trips 的 optional symbol 篩選真生效。

    HIGH-2 同款歸因縫：無 symbol → 全 symbol；有 symbol → 只該 cell。
    fake _pair_round_trips（純函數縫），fills 查詢經 fake cursor 空轉。
    """
    from types import SimpleNamespace

    from program_code.ml_training import realized_edge_stats as res_mod
    from program_code.ml_training import residual_alpha_producer_db as db_mod

    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    recs = [
        SimpleNamespace(
            strategy_name="grid_trading", symbol="BTCUSDT",
            entry_ts=base, exit_ts=base + timedelta(hours=1), net_pnl_bps=4.0,
        ),
        SimpleNamespace(
            strategy_name="grid_trading", symbol="ETHUSDT",
            entry_ts=base, exit_ts=base + timedelta(hours=2), net_pnl_bps=-3.0,
        ),
    ]
    monkeypatch.setattr(res_mod, "_pair_round_trips", lambda fills: list(recs))

    class _Cur:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            return None

        def fetchall(self):
            return []

    class _Conn:
        def cursor(self, **_kw):
            return _Cur()

    all_trips = db_mod.load_round_trips(
        _Conn(), "grid_trading", engine_mode="demo", since=base,
    )
    assert len(all_trips) == 2  # 既有 caller 行為不變（None = 全 symbol）

    btc_only = db_mod.load_round_trips(
        _Conn(), "grid_trading", engine_mode="demo", since=base, symbol="BTCUSDT",
    )
    assert len(btc_only) == 1
    assert btc_only[0]["net_bps"] == 4.0

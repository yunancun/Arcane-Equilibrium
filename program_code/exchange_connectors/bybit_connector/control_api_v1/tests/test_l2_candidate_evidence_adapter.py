"""L2 P3b owed ③ — l2_candidate_evidence_adapter（evidence v1 → math_gate_inputs）測試。

覆蓋（對映 PA 2026-06-10 §B/§E E1-B 測試清單）：
  - 缺值矩陣：每缺一鍵 → 對應 math gate stage 的誠實 DEFER（餵真 _run_math_gate 驗 verdict）。
  - regime row 選擇：多行無顯式 → regime_ambiguous_no_selection；顯式命中 / 顯式 miss。
  - bps→fraction 正規化；未知 return_unit → None。
  - ★ 禁捏造斷言：無 daily_returns → candidate_returns is None；adapter 真碼（剝註解/字串）
    無 mean_daily_bps / net_bps token（標量→序列合成路徑不存在）。
  - M3 typing：leak flag 僅當 source_class 一致才採信。
  - reindex seam：E1-A 介面凍結（mock 之）；unavailable → temporal key 留置 + reason。
  - FactorBundle loader（注入 fake conn / fake fnd2 loader）：BTC returns / down-mask
    ordinal round-trip（date-key 直餵會得空 mask 的實證偏差修）/ altcap producer / 全 fail-soft。

測試隔離鐵則（0ce45a09 教訓）：autouse _no_real_db 把 adapter 模組引用的 db_pool.get_pg_conn
換成 MagicMock（邏輯全真走、只攔真連線）；需斷言 DB 參數的測試顯式注入 conn_provider。
"""

from __future__ import annotations

import datetime as dt
import io
import sys
import tokenize
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# program_code / helper_scripts 跨 package import（math gate stage + altcap producer 用）。
_SRV_ROOT = Path(__file__).resolve().parents[5]
if str(_SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRV_ROOT))

from app import l2_candidate_evidence_adapter as ADP
from app import l2_ml_advisory_executor as EXEC


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch):
    """連線層隔離（鐵則）：攔 adapter 模組的 db_pool.get_pg_conn 真連線；邏輯不被掩蓋。"""
    fake_conn_cm = MagicMock()
    monkeypatch.setattr(ADP.db_pool, "get_pg_conn", lambda: fake_conn_cm)
    return fake_conn_cm


# ═══════════════════════════════════════════════════════════════════════════════
# 測試輔助（evidence 樣板 / fake reindex / fake FactorBundle）
# ═══════════════════════════════════════════════════════════════════════════════


def _evidence(**overrides) -> dict[str, Any]:
    """合法 evidence v1 樣板（PA §B.2）；overrides 覆寫/刪鍵（值=...刪除哨兵 None 保留）。"""
    base: dict[str, Any] = {
        "evidence_schema": ADP.EVIDENCE_SCHEMA_V1,
        "candidate_id": "cand-1",
        "run_id": "run-1",
        "strategy_family": "listing_fade",
        "regime_rows": [
            {
                "regime": "all",
                "n_independent": 80,
                "oos_sharpe": 1.1,
                "k_trials": 12,
            }
        ],
        "selected_regime": "all",
        "daily_returns": {
            (dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat(): 0.001 * ((-1) ** i)
            for i in range(120)
        },
        "return_unit": "fraction",
        "cpcv_oos_returns_per_split": None,
        "leak_producers": {
            "shift1_compliance": {"source_class": "shift1_compliance", "leak_free": True},
            "is_oos_gap": {"source_class": "is_oos_gap", "leak_free": True},
        },
        "window_start": "2026-01-01",
        "window_end": "2026-05-01",
        "bull_only": False,
    }
    for k, v in overrides.items():
        if v is _DEL:
            base.pop(k, None)
        else:
            base[k] = v
    return base


_DEL = object()  # overrides 刪鍵哨兵


def _fake_bundle(**overrides) -> ADP.FactorBundle:
    """date-key 因子 bundle（與 evidence 樣板同窗；交集 ≥ 90 bars）。"""
    days = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(120)]
    base = dict(
        btc_returns={d: 0.0005 * ((-1) ** i) for i, d in enumerate(days)},
        altcap_returns={d: 0.0007 * ((-1) ** i) for i, d in enumerate(days)},
        down_market_mask={d: (i % 3 == 0) for i, d in enumerate(days)},
        reasons=[],
    )
    base.update(overrides)
    return ADP.FactorBundle(**base)


def _fake_reindex_fn(calls: list[dict[str, Any]] | None = None):
    """E1-A reindex 介面 mock（PA §D.2 凍結簽名）：date/ISO key → 交集 ordinal-offset int。"""

    def _norm(k: Any) -> dt.date | None:
        if isinstance(k, dt.datetime):
            return k.date()
        if isinstance(k, dt.date):
            return k
        if isinstance(k, str):
            try:
                return dt.date.fromisoformat(k[:10])
            except ValueError:
                return None
        return None

    def _reindex(candidate, btc, altcap, mask, *, bar="daily"):
        if calls is not None:
            calls.append({"candidate": candidate, "btc": btc, "altcap": altcap,
                          "mask": mask, "bar": bar})
        series = {"candidate": candidate, "btc": btc, "altcap": altcap}
        normed = {
            name: ({_norm(k): v for k, v in s.items()} if s is not None else None)
            for name, s in series.items()
        }
        non_none = [set(s.keys()) for s in normed.values() if s is not None]
        common = sorted(set.intersection(*non_none)) if non_none else []
        if not common:
            return SimpleNamespace(candidate=None, btc=None, altcap=None, mask=None,
                                   index_map={}, n_bars=0, reasons=["empty_intersection"])
        d0 = common[0].toordinal()
        idx = {d: d.toordinal() - d0 for d in common}
        out = {
            name: ({idx[d]: s[d] for d in common} if s is not None else None)
            for name, s in normed.items()
        }
        m = None
        if mask is not None:
            mn = {_norm(k): bool(v) for k, v in mask.items()}
            m = {idx[d]: mn.get(d, False) for d in common}
        return SimpleNamespace(
            candidate=out["candidate"], btc=out["btc"], altcap=out["altcap"], mask=m,
            index_map={i: d for d, i in idx.items()}, n_bars=len(common), reasons=[],
        )

    return _reindex


@pytest.fixture
def _with_fake_reindex(monkeypatch):
    """注入 E1-A reindex mock（模組尚未落地，介面已凍結 per PA §D.2）。"""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(ADP, "_resolve_reindex", lambda: _fake_reindex_fn(calls))
    return calls


# ═══════════════════════════════════════════════════════════════════════════════
# 純函數層 — 映射表（PA §B.3）
# ═══════════════════════════════════════════════════════════════════════════════


class TestMappingTable:
    def test_full_evidence_maps_all_keys(self, _with_fake_reindex):
        """完整 evidence + factors → 映射表全鍵就位（n_independent/oos_sharpe/k_trials）。"""
        ctx, reasons = ADP.build_math_gate_context(_evidence(), factors=_fake_bundle())
        gi = ctx["math_gate_inputs"]
        assert gi["n_trades_oos"] == 80          # ← n_independent（非 n_days）
        assert gi["observed_sharpe"] == 1.1       # ← oos_sharpe（非 annualized_net_sharpe）
        assert gi["n_trials"] == 12               # ← k_trials
        assert gi["bar"] == "daily"
        assert gi["shift1_compliance_leak_free"] is True
        assert gi["is_oos_gap_leak_free"] is True
        # reindex 後全 int key（B1 int-bar-index 契約）。
        assert ctx["candidate_returns"] and all(
            isinstance(k, int) for k in ctx["candidate_returns"]
        )
        assert gi["btc_returns"] and all(isinstance(k, int) for k in gi["btc_returns"])
        assert gi["down_market_mask"] and all(
            isinstance(k, int) for k in gi["down_market_mask"]
        )

    def test_bps_unit_normalized_to_fraction(self, _with_fake_reindex):
        """return_unit=bps → ÷1e4 正規化。"""
        ev = _evidence(
            daily_returns={"2026-01-01": 10.0, "2026-01-02": -5.0}, return_unit="bps"
        )
        ctx, _ = ADP.build_math_gate_context(ev, factors=None)
        vals = sorted(ctx["candidate_returns"].values())
        assert vals == [pytest.approx(-0.0005), pytest.approx(0.001)]

    def test_unknown_return_unit_is_none_not_guessed(self):
        """未知 return_unit → candidate None + reason（不猜單位）。"""
        ev = _evidence(return_unit="percent")
        ctx, reasons = ADP.build_math_gate_context(ev, factors=None)
        assert ctx["candidate_returns"] is None
        assert any(r.startswith("return_unit_unknown") for r in reasons)

    def test_unparseable_return_value_fails_whole_series(self):
        """任一 value 非有限數 → 整條 None（fail-loud，不部分靜默丟 row）。"""
        ev = _evidence(daily_returns={"2026-01-01": 0.001, "2026-01-02": "oops"})
        ctx, reasons = ADP.build_math_gate_context(ev, factors=None)
        assert ctx["candidate_returns"] is None
        assert "daily_returns_unparseable_b1_defer" in reasons

    def test_unsupported_schema_all_none(self):
        """未知 evidence_schema → 全 None（不信任任何欄）。"""
        ctx, reasons = ADP.build_math_gate_context(
            _evidence(evidence_schema="aeg.v999"), factors=_fake_bundle()
        )
        assert ctx["candidate_returns"] is None
        gi = ctx["math_gate_inputs"]
        assert all(gi[k] is None for k in (
            "n_trades_oos", "observed_sharpe", "n_trials", "btc_returns",
        ))
        assert any(r.startswith("evidence_schema_unsupported") for r in reasons)


class TestRegimeSelection:
    def test_multi_rows_without_selection_defers(self):
        """多 regime row 無顯式 selected_regime → 標量全 None + 防 cherry-pick reason。"""
        ev = _evidence(
            regime_rows=[
                {"regime": "all", "n_independent": 80, "oos_sharpe": 1.1, "k_trials": 12},
                {"regime": "bull", "n_independent": 60, "oos_sharpe": 2.5, "k_trials": 12},
            ],
            selected_regime=_DEL,
        )
        ctx, reasons = ADP.build_math_gate_context(ev, factors=None)
        gi = ctx["math_gate_inputs"]
        assert gi["n_trades_oos"] is None and gi["observed_sharpe"] is None
        assert "regime_ambiguous_no_selection" in reasons

    def test_single_row_without_selection_used(self):
        """缺省且恰一行 → 用之（無歧義）。"""
        ev = _evidence(selected_regime=_DEL)
        ctx, _ = ADP.build_math_gate_context(ev, factors=None)
        assert ctx["math_gate_inputs"]["n_trades_oos"] == 80

    def test_explicit_selection_not_in_rows_defers(self):
        """顯式指定但 rows 無此 regime → None + reason（不退而求其次）。"""
        ev = _evidence(selected_regime="bear")
        ctx, reasons = ADP.build_math_gate_context(ev, factors=None)
        assert ctx["math_gate_inputs"]["n_trades_oos"] is None
        assert any(r.startswith("selected_regime_not_in_rows") for r in reasons)

    def test_missing_rows_defers(self):
        ev = _evidence(regime_rows=_DEL)
        ctx, reasons = ADP.build_math_gate_context(ev, factors=None)
        assert ctx["math_gate_inputs"]["n_trades_oos"] is None
        assert "regime_rows_missing" in reasons


class TestNoFabrication:
    """★ 捏造禁令（E2 重點審查 1）：標量永不合成序列。"""

    def test_missing_daily_returns_yields_none_even_with_scalars(self):
        """row 帶 mean_daily_bps 類標量、無 daily_returns → candidate_returns 必為 None。"""
        ev = _evidence(daily_returns=_DEL)
        ev["regime_rows"][0]["mean_daily_bps"] = 4.2  # 標量在場也不得合成序列
        ev["regime_rows"][0]["net_bps"] = 300.0
        ctx, reasons = ADP.build_math_gate_context(ev, factors=_fake_bundle())
        assert ctx["candidate_returns"] is None
        assert "daily_returns_missing_b1_defer" in reasons

    def test_source_has_no_scalar_to_series_path(self):
        """adapter 真碼（剝註解/docstring）不含 mean_daily_bps / net_bps token——
        標量→序列合成路徑「結構性」不存在（禁令只活在註釋）。"""
        src = Path(ADP.__file__).read_text(encoding="utf-8")
        code_tokens: list[str] = []
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            code_tokens.append(tok.string)
        code = " ".join(code_tokens)
        assert "mean_daily_bps" not in code
        assert "net_bps" not in code
        # 原始 source 必須含禁令註釋（MODULE_NOTE grep target）。
        assert "捏造禁令" in src

    def test_missing_returns_flows_to_b1_defer_via_real_math_gate(self, _with_fake_reindex):
        """串真 math gate：無 daily_returns → B1 stage DEFER b1_inputs_missing_defer，
        overall 至多 DEFER（誠實，不偽 pass）。"""
        ev = _evidence(daily_returns=_DEL)
        ctx, _ = ADP.build_math_gate_context(ev, factors=_fake_bundle())
        res = EXEC._run_math_gate({}, ctx, novelty="novel")
        assert res["stage_verdicts"]["beta_neutral"] == "DEFER"
        assert "b1_inputs_missing_defer" in res["reasons"]
        assert res["verdict"] in ("DEFER", "fail")


class TestLeakTyping:
    def test_mismatched_source_class_not_trusted(self):
        """M3 typing：source_class 不符 → flag None（report 自稱 leak-free 不算）。"""
        ev = _evidence(leak_producers={
            "shift1_compliance": {"source_class": "self_reported", "leak_free": True},
            "is_oos_gap": {"source_class": "is_oos_gap", "leak_free": True},
        })
        ctx, reasons = ADP.build_math_gate_context(ev, factors=None)
        gi = ctx["math_gate_inputs"]
        assert gi["shift1_compliance_leak_free"] is None
        assert gi["is_oos_gap_leak_free"] is True
        assert "leak_producer_source_class_mismatch:shift1_compliance" in reasons

    def test_absent_producers_defer_leak_stage(self):
        """兩 producer 皆缺 → 雙鍵 None → 真 leak stage DEFER（no producer ⇒ no claim）。"""
        ev = _evidence(leak_producers=_DEL)
        ctx, _ = ADP.build_math_gate_context(ev, factors=None)
        gi = ctx["math_gate_inputs"]
        assert gi["shift1_compliance_leak_free"] is None
        assert gi["is_oos_gap_leak_free"] is None
        leak = EXEC._run_leak_stage(gi)
        assert leak["verdict"] == "DEFER"
        assert "leak_precondition_unmet_no_producer" in leak["reasons"]

    def test_explicit_leak_false_fails_stage(self):
        """producer 明確 leak_free=False → 真 leak stage fail（結構性 leak）。"""
        ev = _evidence(leak_producers={
            "shift1_compliance": {"source_class": "shift1_compliance", "leak_free": False},
            "is_oos_gap": {"source_class": "is_oos_gap", "leak_free": False},
        })
        ctx, _ = ADP.build_math_gate_context(ev, factors=None)
        leak = EXEC._run_leak_stage(ctx["math_gate_inputs"])
        assert leak["verdict"] == "fail"


class TestMissingValueMatrix:
    """缺值矩陣 → 真 math gate 對應 stage 誠實 DEFER（PA §B.3 表逐行）。"""

    def test_missing_n_independent_q1_defer(self, _with_fake_reindex):
        ev = _evidence()
        del ev["regime_rows"][0]["n_independent"]
        ctx, _ = ADP.build_math_gate_context(ev, factors=_fake_bundle())
        res = EXEC._run_math_gate({}, ctx, novelty="novel")
        assert res["stage_verdicts"]["q1"] == "DEFER"
        assert "q1_trades_oos_below_50" in res["reasons"]

    def test_missing_oos_sharpe_dsr_defer(self, _with_fake_reindex):
        ev = _evidence()
        del ev["regime_rows"][0]["oos_sharpe"]
        ctx, _ = ADP.build_math_gate_context(ev, factors=_fake_bundle())
        res = EXEC._run_math_gate({}, ctx, novelty="novel")
        assert res["stage_verdicts"]["dsr"] == "DEFER"
        assert "dsr_inputs_missing" in res["reasons"]

    def test_cpcv_absent_pbo_honest_defer(self, _with_fake_reindex):
        """單配置（cpcv 缺）→ PBO honest-DEFER（不捏造 peer，承 Gap-A）。"""
        ctx, reasons = ADP.build_math_gate_context(_evidence(), factors=_fake_bundle())
        assert ctx["math_gate_inputs"]["cpcv_oos_returns_per_split"] is None
        assert "cpcv_absent_pbo_honest_defer" in reasons
        res = EXEC._run_math_gate({}, ctx, novelty="novel")
        assert res["stage_verdicts"]["pbo"] == "DEFER"
        assert "pbo_single_config_honest_defer" in res["reasons"]

    def test_factor_bundle_missing_b1_defer(self):
        """factors=None → btc None → 真 B1 stage DEFER（因子由系統載入，缺則不估）。"""
        ctx, reasons = ADP.build_math_gate_context(_evidence(), factors=None)
        assert ctx["math_gate_inputs"]["btc_returns"] is None
        assert "factor_bundle_missing_b1_defer" in reasons
        res = EXEC._run_math_gate({}, ctx, novelty="novel")
        assert res["stage_verdicts"]["beta_neutral"] == "DEFER"

    def test_altcap_none_flows_to_b1_internal_defer(self, _with_fake_reindex):
        """altcap=None（producer 缺）→ 真 beta_neutral_check 內部雙因子強制 DEFER。"""
        ctx, _ = ADP.build_math_gate_context(
            _evidence(), factors=_fake_bundle(altcap_returns=None)
        )
        res = EXEC._run_math_gate({}, ctx, novelty="novel")
        assert res["stage_verdicts"]["beta_neutral"] == "DEFER"
        assert "b1_altcap_missing_btc_only_defer" in res["reasons"]


class TestReindexSeam:
    def test_reindex_receives_all_four_series(self, _with_fake_reindex):
        """reindex 收到 candidate/btc/altcap/mask 四 series + bar=daily（介面凍結）。"""
        ADP.build_math_gate_context(_evidence(), factors=_fake_bundle())
        assert len(_with_fake_reindex) == 1
        call = _with_fake_reindex[0]
        assert call["bar"] == "daily"
        assert call["candidate"] is not None and call["btc"] is not None
        assert call["altcap"] is not None and call["mask"] is not None

    def test_reindex_unavailable_leaves_temporal_keys_with_reason(self, monkeypatch):
        """E1-A 模組未落地 → temporal key 留置 + reason（B1 入口 fail-loud DEFER 兜底，
        非靜默）。"""
        monkeypatch.setattr(ADP, "_resolve_reindex", lambda: None)
        ctx, reasons = ADP.build_math_gate_context(_evidence(), factors=_fake_bundle())
        assert "bar_index_reindex_unavailable_temporal_keys_left" in reasons
        # key 未被轉 int（仍 ISO 字串）→ B1 入口顯式 DEFER（executor 串接時）。
        assert all(isinstance(k, str) for k in ctx["candidate_returns"])

    def test_reindex_exception_all_none(self, monkeypatch):
        """reindex 例外 → 全 None + reason（fail-soft；誠實 DEFER 不冒例外進 dispatch）。"""
        def _boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(ADP, "_resolve_reindex", lambda: _boom)
        ctx, reasons = ADP.build_math_gate_context(_evidence(), factors=_fake_bundle())
        assert ctx["candidate_returns"] is None
        assert ctx["math_gate_inputs"]["btc_returns"] is None
        assert "bar_index_reindex_error_all_none" in reasons


# ═══════════════════════════════════════════════════════════════════════════════
# DB 層 — FactorBundle loader（fake conn / fake fnd2 loader 注入）
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed: list[tuple[str, Any]] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self.cursor_obj = _FakeCursor(rows)

    def cursor(self):
        return self.cursor_obj


_NO_CONN_SENTINEL = object()  # 區分「未指定 conn（用預設 _FakeConn）」vs「顯式 conn=None（模擬 DB 不可用）」


class _FakeConnProvider:
    """模擬 db_pool.get_pg_conn 的 context-manager provider。

    conn 參數語意：未傳 → 預設 _FakeConn(rows)；顯式傳 None → __enter__ 回 None
    （對齊 db_pool.get_pg_conn 在池不可用時 yield None 的契約，驗 unavailable 分支）。
    """

    def __init__(self, rows=None, conn=_NO_CONN_SENTINEL):
        self._conn = _FakeConn(rows or []) if conn is _NO_CONN_SENTINEL else conn

    def __call__(self):
        provider = self

        class _CM:
            def __enter__(self):
                return provider._conn

            def __exit__(self, *a):
                return False

        return _CM()


def _kline_rows(symbols: list[str], start: dt.date, n: int, *, slope: float = -1.0):
    """n 根 1d kline（價格線性走勢；slope<0 = 下跌 → down-mask 有 True bar）。"""
    rows = []
    for sym in symbols:
        for i in range(n):
            d = start + dt.timedelta(days=i)
            ts = dt.datetime.combine(d, dt.time.min, tzinfo=dt.timezone.utc)
            rows.append((sym, ts, 1000.0 + slope * i))
    return rows


def _fnd2_rows(symbols: list[str], af: str, at: str):
    return [
        {"symbol": s, "included": True, "alive_from_utc": af, "alive_to_utc": at}
        for s in symbols
    ]


class TestFactorBundleLoader:
    _WS = dt.date(2026, 2, 1)
    _WE = dt.date(2026, 5, 1)

    def _bundle(self, rows, fnd2):
        return ADP.load_factor_bundle(
            self._WS, self._WE,
            conn_provider=_FakeConnProvider(rows=rows),
            fnd2_rows_loader=lambda *a, **k: fnd2,
        )

    def test_btc_returns_and_mask_built_date_keyed(self):
        """BTC returns 正確（相鄰 bar 比值）且 mask 為 date key + 下跌窗有 down bar。

        ★ 偏差修實證：compute_down_market_mask 直餵 date key 會回「空 mask」（±inf 解析
        靜默吞）；loader 的 ordinal round-trip 必須回非空 date-key mask。
        """
        start = self._WS - dt.timedelta(days=45)
        rows = _kline_rows(["BTCUSDT", "ETHUSDT", "SOLUSDT"], start, 130, slope=-5.0)
        fb = self._bundle(rows, _fnd2_rows(["ETHUSDT", "SOLUSDT"], "2025-01-01", "2026-12-31"))
        assert fb.btc_returns and len(fb.btc_returns) >= 100
        assert all(isinstance(k, dt.date) for k in fb.btc_returns)
        # 線性下跌：r_t = -5/(1000-5(i-1)) < 0。
        assert all(v < 0 for v in fb.btc_returns.values())
        assert fb.down_market_mask is not None and len(fb.down_market_mask) > 0
        assert all(isinstance(k, dt.date) for k in fb.down_market_mask)
        # 持續下跌 → 後段必有 down bar（30d-dd>8% 或 7d<-5% 至少一軸觸發）。
        assert sum(fb.down_market_mask.values()) > 0

    def test_altcap_producer_reused_and_nonempty(self):
        """altcap producer（零改動 reuse）對 in-scope alive 成分出 non-empty returns。"""
        start = self._WS - dt.timedelta(days=45)
        rows = _kline_rows(["BTCUSDT", "ETHUSDT", "SOLUSDT"], start, 130, slope=2.0)
        fb = self._bundle(rows, _fnd2_rows(["ETHUSDT", "SOLUSDT"], "2025-01-01", "2026-12-31"))
        assert fb.altcap_returns and len(fb.altcap_returns) > 0

    def test_empty_klines_all_none_failsoft(self):
        """klines 空 → btc/mask/altcap 全 None + reasons（fail-soft，B1 DEFER 兜底）。"""
        fb = self._bundle([], _fnd2_rows(["ETHUSDT"], "2025-01-01", "2026-12-31"))
        assert fb.btc_returns is None
        assert fb.down_market_mask is None
        assert fb.altcap_returns is None
        assert "btc_klines_insufficient" in fb.reasons

    def test_conn_unavailable_failsoft(self):
        """conn=None（池降級）→ 全 None + klines_db_unavailable（不 raise）。"""
        fb = ADP.load_factor_bundle(
            self._WS, self._WE,
            conn_provider=_FakeConnProvider(conn=None),
            fnd2_rows_loader=lambda *a, **k: [],
        )
        assert fb.btc_returns is None and fb.altcap_returns is None
        assert "klines_db_unavailable" in fb.reasons

    def test_fnd2_loader_raises_altcap_none_failsoft(self):
        """FND-2 loader 例外 → altcap None + reason；BTC 軸不受影響。"""
        start = self._WS - dt.timedelta(days=45)
        rows = _kline_rows(["BTCUSDT"], start, 130)

        def _boom(*a, **k):
            raise RuntimeError("fnd2 down")

        fb = ADP.load_factor_bundle(
            self._WS, self._WE,
            conn_provider=_FakeConnProvider(rows=rows),
            fnd2_rows_loader=_boom,
        )
        assert fb.btc_returns is not None
        assert fb.altcap_returns is None
        assert "altcap_producer_failed" in fb.reasons

    def test_window_unparseable_all_none(self):
        fb = ADP.load_factor_bundle("not-a-date", "also-bad")
        assert fb.btc_returns is None and fb.down_market_mask is None
        assert fb.reasons == ["factor_window_unparseable"]

    def test_query_parameterized_and_readonly(self):
        """SELECT 參數化（symbol 列表/窗邊界綁定）且唯讀（無 INSERT/UPDATE/DELETE）。"""
        provider = _FakeConnProvider(rows=[])
        ADP.load_factor_bundle(
            self._WS, self._WE, conn_provider=provider,
            fnd2_rows_loader=lambda *a, **k: [],
        )
        executed = provider._conn.cursor_obj.executed
        assert len(executed) == 1
        sql, params = executed[0]
        up = sql.upper()
        assert "SELECT" in up and all(w not in up for w in ("INSERT", "UPDATE", "DELETE"))
        assert "%s" in sql and isinstance(params, tuple)
        assert "BTCUSDT" in params[0]


class TestBuildContextFromEvidence:
    def test_window_missing_skips_factor_loading(self, monkeypatch):
        """window 缺 → 不載因子（loader 不被呼）+ reason；context 仍可組（B1 DEFER）。"""
        called = []
        ctx, reasons = ADP.build_context_from_evidence(
            _evidence(window_start=_DEL),
            factor_loader=lambda *a, **k: called.append(1) or _fake_bundle(),
        )
        assert not called
        assert "window_missing_factors_not_loaded" in reasons
        assert ctx["math_gate_inputs"]["btc_returns"] is None

    def test_window_present_loads_factors_with_window(self, _with_fake_reindex):
        """window 在 → loader 收正確 date 窗，factors 進映射。"""
        seen: list[tuple] = []

        def _loader(ws, we, **kwargs):
            seen.append((ws, we))
            return _fake_bundle()

        ctx, _ = ADP.build_context_from_evidence(_evidence(), factor_loader=_loader)
        assert seen == [(dt.date(2026, 1, 1), dt.date(2026, 5, 1))]
        assert ctx["math_gate_inputs"]["btc_returns"] is not None

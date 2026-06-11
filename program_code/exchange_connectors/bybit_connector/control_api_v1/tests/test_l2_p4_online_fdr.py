"""
L2 P4 online-FDR — E1-B 段 2 binding AC 測試（executor 守門 / adapter seam / guard F /
contract v2 / orchestrator tier_provider）。

逐條對映 binding AC：
  - MIT #3：debit 條件 = overall ∈ {pass,fail} OR stage_verdicts["dsr"] ∈ {pass,fail}；
    純輸入缺失 DEFER 不扣。golden (b)：dsr=pass ∧ overall=DEFER ⇒ 必有 debit。
  - MIT §5a FIX-3.1：①precheck 在 α_i 指派前；②value-invariance；③total skip（無 dsr
    verdict）；④golden (a) skip ⇒ 無 debit ∧ 無 dsr verdict、(c) value-invariance mutation。
  - QC FIX-2.1b：區間算術（window_end+1d ≤ oos_start）；`==` off-by-one 必 DEFER；
    非午夜 straddle 必 DEFER；無 sealed row 不阻；多 row 任一重疊即 DEFER。
  - QC FIX-1.3：math gate fail 鑄 dead-mode lesson（冪等 / 英文主幹 / 三欄）。
  - MIT #2 Option B：threshold 真咬合（同 fixture 0.95 pass、~1 fail）+ threshold=1.0
    fail-soft DEFER。
  - M2 N_eff seam：variant_returns → n_eff 注入；缺/壞 → raw k_trials + reason。
  - P4 §6 tier_provider：fail-closed 默認 L1 byte-identical；投影 L3+flag 解鎖；raise 退 L1。
  - 鐵則：P3a 路徑零波及；硬邊界 grep 指紋；hidden_oos_state_registry 0 寫點。

全部 fake conn / monkeypatch import 點，0 真連線、0 真 learning_engine 依賴
（A 線檔於 merge 後由 E4 全鏈驗）。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import io
import random
import sys
import tokenize
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# program_code.learning_engine 跨 package import（dsr_gate 真模組；srv root = parents[5]）。
_SRV_ROOT = Path(__file__).resolve().parents[5]
if str(_SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRV_ROOT))

from app import l2_advisory_orchestrator as ORCH
from app import l2_alpha_wealth_store as STORE
from app import l2_candidate_evidence_adapter as ADAPTER
from app import l2_ml_advisory_executor as EXEC
from app import l2_out_of_bound_guard as GUARD
from app import l2_prompt_contract_registry as CONTRACTS
from app.learning_tier_gate import LearningTier


def _run(coro):
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════════
# fakes：wealth controller（A 線契約簽名）/ store 捕捉 / sealed flag
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeAwc:
    """E1-A alpha_wealth_controller 契約 fake（PA §2.2 六簽名）。"""

    ALPHA_TARGET_DEFAULT = 0.05
    W0_GAMMA = 0.10
    PHI_REFUND = 1.0
    MIN_BATCH_SIZE_DEFAULT = 10
    SPEND_FRACTION_DEFAULT = 0.10

    @staticmethod
    def init_family_wealth(alpha_target: float = 0.05, gamma: float = 0.10) -> float:
        return gamma * alpha_target

    @staticmethod
    def assign_alpha_i(balance, *, alpha_target, min_batch_size, spend_fraction):
        cap = alpha_target / float(min_batch_size)
        alpha_i = min(spend_fraction * balance, cap)
        return None if alpha_i < 1e-6 else alpha_i

    @staticmethod
    def can_test(balance, alpha_i):
        return (balance - alpha_i) > 0.0

    # 默認回 floor（DSR 行為與 P3b 基線一致）；threshold 咬合另測。
    @staticmethod
    def dsr_threshold_for(alpha_i, *, floor: float = 0.95) -> float:
        return floor


@pytest.fixture
def fdr(monkeypatch):
    """wealth/pre-reg/sealed 注入；回捕捉 dict。"""
    captured: dict[str, Any] = {"debits": [], "preregs": [], "order": []}
    monkeypatch.setattr(EXEC, "_resolve_wealth_controller", lambda: _FakeAwc)
    monkeypatch.setattr(
        EXEC, "_check_sealed_boundary",
        lambda strategy, symbol, we, conn: (False, ["no_sealed_split_for_cell"]),
    )

    def _fake_prereg(**kw):
        captured["preregs"].append(kw)
        captured["order"].append("prereg")
        return STORE.PreRegistrationOutcome(ok=True, pre_reg_id=11, spec_sha256="cd" * 32)

    def _fake_debit(**kw):
        captured["debits"].append(kw)
        captured["order"].append("debit")
        return STORE.DebitOutcome(ok=True, debit_id=kw["debit_id"])

    monkeypatch.setattr(STORE, "register_pre_registration", _fake_prereg)
    monkeypatch.setattr(STORE, "ensure_family_initialized", lambda *a, **kw: None)
    monkeypatch.setattr(STORE, "get_family_balance", lambda *a, **kw: 0.005)
    monkeypatch.setattr(STORE, "record_debit", _fake_debit)
    return captured


def _guard_out() -> dict[str, Any]:
    """guard-passed hypothesize 輸出（v2 形）。"""
    return {
        "mode": "hypothesize",
        "signal_axes_used": ["funding_rate"],
        "feature_hypotheses": [
            {
                "hid": "h1",
                "statement": "funding skew predicts reversion",
                "mechanism": "crowded longs pay funding",
                "falsification_test": {
                    "null_hypothesis": "no predictive power",
                    "test_statistic": "deflated Sharpe",
                    "reject_condition": "DSR below threshold",
                },
                "primary_axis": "funding_rate",
                "signal_axes_used": ["funding_rate"],
            }
        ],
    }


def _gate_context(*, with_cpcv: bool = True, leak: bool | None = True) -> dict[str, Any]:
    """gate 可達的 context（int key、span≥180、樣本足）。leak=None ⇒ 兩 producer 皆缺。"""
    import numpy as np

    random.seed(7)
    n = 250
    btc = {i: random.gauss(0, 0.02) for i in range(n)}
    alt = {i: random.gauss(0, 0.02) for i in range(n)}
    cand = {i: 0.0003 + random.gauss(0, 0.003) for i in range(n)}
    mask = {i: (btc[i] < -0.01) for i in range(n)}
    gi: dict[str, Any] = {
        "btc_returns": btc, "altcap_returns": alt, "down_market_mask": mask,
        "n_trades_oos": 200, "observed_sharpe": 3.0, "n_trials": 5, "bar": "daily",
    }
    if leak is not None:
        gi["shift1_compliance_leak_free"] = leak
    if with_cpcv:
        np.random.seed(1)
        gi["cpcv_oos_returns_per_split"] = [
            np.random.normal(0.5, 1.0, 200),
            np.random.normal(0.0, 1.0, 200),
            np.random.normal(0.0, 1.0, 200),
        ]
    return {
        "candidate_returns": cand,
        "math_gate_inputs": gi,
        "evidence_window": {"window_start": "2025-01-01", "window_end": "2025-09-30"},
    }


async def _run_stage(context, *, capability_id="ml_advisory.hypothesize", novelty="novel"):
    return await EXEC._run_wealth_gated_math_stage(
        capability_id=capability_id, guard_out=_guard_out(), context=context,
        novelty=novelty, symbol="BTCUSDT", strategy_name="grid_trading",
        sink_conn_provider=None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MIT #3 — debit 條件（golden）
# ═══════════════════════════════════════════════════════════════════════════════


class TestMit3DebitCondition:
    def test_golden_b_dsr_pass_overall_defer_must_debit(self, fdr):
        """golden (b)：dsr=pass ∧ overall=DEFER（single-config PBO honest-DEFER）⇒ 必有 debit。"""
        res = _run(_run_stage(_gate_context(with_cpcv=False)))
        assert res["stage_verdicts"]["dsr"] == "pass"
        assert res["verdict"] == "DEFER"
        assert len(fdr["debits"]) == 1
        assert res["fdr"]["debit"] == "debited"

    def test_pure_input_missing_dsr_defer_no_debit(self, fdr):
        """純輸入缺失（observed_sharpe=None → dsr 自身 DEFER）⇒ 不扣（資料稀缺不破產）。"""
        ctx = _gate_context()
        ctx["math_gate_inputs"]["observed_sharpe"] = None
        res = _run(_run_stage(ctx))
        assert res["stage_verdicts"]["dsr"] == "DEFER"
        assert res["verdict"] == "DEFER"
        assert fdr["debits"] == []
        assert res["fdr"]["debit"] == "deferred_no_debit"

    def test_overall_fail_without_dsr_render_still_debits(self, fdr):
        """overall 結論性（leak=False → fail）即便 dsr 自身 DEFER ⇒ 仍扣（conducted-test-pays）。"""
        ctx = _gate_context(leak=False)
        ctx["math_gate_inputs"]["observed_sharpe"] = None  # dsr inputs missing
        ctx["math_gate_inputs"]["n_trials"] = None  # K 亦缺 → ledger n_eff 記 1（審計欄佔位）
        res = _run(_run_stage(ctx))
        assert res["verdict"] == "fail"
        assert res["stage_verdicts"]["dsr"] == "DEFER"
        assert len(fdr["debits"]) == 1
        # dsr 未渲染且 n_trials 缺 → ledger n_eff 記 1（非 deflation 消費，evidence 標 absent）。
        assert fdr["debits"][0]["n_eff"] == 1
        assert fdr["debits"][0]["evidence"]["n_eff_source"] == "absent_default_1"

    def test_overall_pass_debits_once_with_n_eff_equals_n_trials(self, fdr):
        res = _run(_run_stage(_gate_context()))
        assert res["verdict"] == "pass"
        assert len(fdr["debits"]) == 1
        # M2 單 debit 合約：ledger n_eff = DSR 消費的 n_trials 同值同源。
        assert fdr["debits"][0]["n_eff"] == 5

    def test_debit_id_deterministic_from_prereg_and_window(self, fdr):
        """MIT N-4：debit_id = hash(pre_reg_id, window)——同窗重放恆同 id。"""
        r1 = _run(_run_stage(_gate_context()))
        r2 = _run(_run_stage(_gate_context()))
        assert r1["fdr"]["debit_id"] == r2["fdr"]["debit_id"]
        assert r1["fdr"]["debit_id"] == STORE.deterministic_debit_id(
            11, "2025-01-01", "2025-09-30"
        )

    def test_debit_write_failure_forces_defer(self, fdr, monkeypatch):
        """debit 寫失敗 ⇒ verdict 強制 DEFER（未付費 test 不得鑄 discovery；fail-closed）。"""
        monkeypatch.setattr(
            STORE, "record_debit",
            lambda **kw: STORE.DebitOutcome(ok=False, debit_id=kw["debit_id"], error="boom"),
        )
        res = _run(_run_stage(_gate_context()))
        assert res["verdict"] == "DEFER"
        assert "alpha_wealth_debit_write_failed" in res["reasons"]
        assert res["fdr"]["debit"] == "debit_write_failed"


# ═══════════════════════════════════════════════════════════════════════════════
# MIT §5a FIX-3.1 — precheck（golden a / c + 次序）
# ═══════════════════════════════════════════════════════════════════════════════


class TestFix31Precheck:
    @pytest.mark.parametrize(
        "mutate",
        [
            lambda c: c.update(candidate_returns=None),
            lambda c: c["math_gate_inputs"].update(altcap_returns=None),
            lambda c: c["math_gate_inputs"].update(btc_returns=None),
            lambda c: c["math_gate_inputs"].update(
                shift1_compliance_leak_free=None, is_oos_gap_leak_free=None
            ),
            lambda c: c.update(evidence_window={"window_start": None, "window_end": None}),
        ],
    )
    def test_golden_a_skip_no_debit_no_dsr_verdict(self, fdr, mutate):
        """golden (a)：B1/leak 輸入存在性注定 DEFER ⇒ 免費 skip——無 debit ∧ 無 dsr verdict。"""
        ctx = _gate_context(leak=True)
        mutate(ctx)
        res = _run(_run_stage(ctx))
        assert res["verdict"] == "DEFER"
        assert "precheck_input_unavailable" in res["reasons"]
        assert "dsr" not in res["stage_verdicts"]  # total skip：DSR 未渲染
        assert fdr["debits"] == []
        assert fdr["preregs"] == []  # α_i 指派 / pre-reg 全未發生（在 STAGE 3.6/3.7 之前）

    def test_aligned_history_span_below_180d_skips(self, fdr):
        """value-free 蘊含：aligned candidate 歷史日曆 span < 180d ⇒ B1 注定 DEFER ⇒ skip。"""
        ctx = _gate_context()
        n = 120  # span 119 < 180
        ctx["candidate_returns"] = {i: 0.001 for i in range(n)}
        ctx["math_gate_inputs"]["btc_returns"] = {i: 0.0 for i in range(n)}
        res = _run(_run_stage(ctx))
        assert res["verdict"] == "DEFER"
        assert "precheck_input_unavailable" in res["reasons"]
        assert any("aligned_history_span_lt" in r for r in res["reasons"])
        assert fdr["debits"] == []

    def test_golden_c_value_invariance_mutation(self):
        """golden (c)：固定 timestamps/存在性，擾動任何 returns 數值 ⇒ 謂詞真值不變。"""
        rng = random.Random(13)
        base = _gate_context()
        doomed_base, _ = EXEC._run_doomed_input_precheck(base)
        # 擾動全部數值（key 集合不動）。
        perturbed = _gate_context()
        for series_key in ("candidate_returns",):
            perturbed[series_key] = {
                k: v + rng.gauss(0, 10.0) for k, v in perturbed[series_key].items()
            }
        gi = perturbed["math_gate_inputs"]
        for f in ("btc_returns", "altcap_returns"):
            gi[f] = {k: v + rng.gauss(0, 10.0) for k, v in gi[f].items()}
        gi["observed_sharpe"] = -99.0  # 統計量值翻轉也不得影響謂詞
        doomed_perturbed, _ = EXEC._run_doomed_input_precheck(perturbed)
        assert doomed_base == doomed_perturbed is False
        # doomed 側同樣不變：砍 altcap 後，再怎麼擾動數值都 doomed。
        doomed_ctx = _gate_context()
        doomed_ctx["math_gate_inputs"]["altcap_returns"] = None
        d1, _ = EXEC._run_doomed_input_precheck(doomed_ctx)
        doomed_ctx["candidate_returns"] = {
            k: v * -1000.0 for k, v in doomed_ctx["candidate_returns"].items()
        }
        d2, _ = EXEC._run_doomed_input_precheck(doomed_ctx)
        assert d1 == d2 is True

    def test_precheck_source_reads_no_value_functions(self):
        """value-invariance 源碼面：謂詞不得呼叫任何統計/數值函數（np/mean/std/sharpe）。"""
        src = inspect.getsource(EXEC._run_doomed_input_precheck) + inspect.getsource(
            EXEC._aligned_history_span_days
        )
        code = " ".join(
            t.string
            for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)
        )
        for forbidden in ("np.", "numpy", "mean", "std(", "sharpe", ".values()"):
            assert forbidden not in code, f"precheck 謂詞引用了值函數面：{forbidden}"


# ═══════════════════════════════════════════════════════════════════════════════
# QC FIX-2.1b — sealed boundary（區間算術 golden）
# ═══════════════════════════════════════════════════════════════════════════════


class _SealedConn:
    """fake conn：固定回 sealed rows（window_start datetime 列表）。"""

    def __init__(self, rows: list[tuple], raise_on_execute: bool = False):
        self._rows = rows
        self._raise = raise_on_execute
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        if self._raise:
            raise RuntimeError("db down")
        self.sql = " ".join(sql.split())
        self.params = params

    def fetchall(self):
        return self._rows


def _sealed_provider(rows, **kw):
    def _p():
        return _SealedConn(rows, **kw)

    return _p


_UTC = dt.timezone.utc


class TestFix21bSealedBoundary:
    def test_equal_date_off_by_one_must_defer(self):
        """golden：window_end == oos_start 當日（午夜對齊）⇒ 末 bar [end, end+1d) 進 OOS ⇒ DEFER。"""
        rows = [(dt.datetime(2025, 10, 1, 0, 0, tzinfo=_UTC),)]
        flag, reasons = ADAPTER.load_sealed_boundary_flag(
            "grid_trading", "BTCUSDT", dt.date(2025, 10, 1),
            conn_provider=_sealed_provider(rows),
        )
        assert flag is True
        assert "sealed_holdout_overlap" in reasons

    def test_day_before_midnight_aligned_passes(self):
        rows = [(dt.datetime(2025, 10, 1, 0, 0, tzinfo=_UTC),)]
        flag, reasons = ADAPTER.load_sealed_boundary_flag(
            "grid_trading", "BTCUSDT", dt.date(2025, 9, 30),
            conn_provider=_sealed_provider(rows),
        )
        assert flag is False
        assert "sealed_holdout_overlap" not in reasons

    def test_non_midnight_straddle_must_defer(self):
        """golden：oos_start 非午夜（12:00Z）；window_end == 同日 ⇒ bar 延伸至次日午夜跨界 ⇒ DEFER
        （點比較 `>`/`≥` 會漏此 case——區間算術才是正確代表元）。"""
        rows = [(dt.datetime(2025, 10, 1, 12, 0, tzinfo=_UTC),)]
        flag, reasons = ADAPTER.load_sealed_boundary_flag(
            "grid_trading", "BTCUSDT", dt.date(2025, 10, 1),
            conn_provider=_sealed_provider(rows),
        )
        assert flag is True
        assert "sealed_holdout_overlap" in reasons

    def test_non_midnight_prior_day_passes(self):
        rows = [(dt.datetime(2025, 10, 1, 12, 0, tzinfo=_UTC),)]
        flag, _ = ADAPTER.load_sealed_boundary_flag(
            "grid_trading", "BTCUSDT", dt.date(2025, 9, 30),
            conn_provider=_sealed_provider(rows),
        )
        assert flag is False

    def test_no_sealed_row_not_blocking(self):
        flag, reasons = ADAPTER.load_sealed_boundary_flag(
            "grid_trading", "BTCUSDT", dt.date(2025, 10, 1),
            conn_provider=_sealed_provider([]),
        )
        assert flag is False
        assert "no_sealed_split_for_cell" in reasons

    def test_multiple_rows_any_overlap_defers_with_min_start(self):
        rows = [
            (dt.datetime(2026, 1, 1, tzinfo=_UTC),),  # 不重疊
            (dt.datetime(2025, 8, 1, tzinfo=_UTC),),  # 重疊（較早）
            (dt.datetime(2025, 9, 1, tzinfo=_UTC),),  # 重疊
        ]
        flag, reasons = ADAPTER.load_sealed_boundary_flag(
            "grid_trading", "BTCUSDT", dt.date(2025, 9, 30),
            conn_provider=_sealed_provider(rows),
        )
        assert flag is True
        assert any("2025-08-01" in r for r in reasons)  # min(window_start)

    def test_query_failure_fail_closed(self):
        flag, reasons = ADAPTER.load_sealed_boundary_flag(
            "grid_trading", "BTCUSDT", dt.date(2025, 9, 30),
            conn_provider=_sealed_provider([], raise_on_execute=True),
        )
        assert flag is True
        assert "sealed_registry_check_failed" in reasons

    def test_no_cell_not_applicable(self):
        flag, reasons = ADAPTER.load_sealed_boundary_flag(
            None, None, dt.date(2025, 9, 30), conn_provider=_sealed_provider([])
        )
        assert flag is None

    def test_query_selects_boundary_metadata_only(self):
        """§9.4(a) 盲視：只 SELECT window_start 邊界元資料 + family/state 過濾，0 series 欄。"""
        conn = _SealedConn([])
        ADAPTER.load_sealed_boundary_flag(
            "grid_trading", "BTCUSDT", dt.date(2025, 9, 30), conn_provider=lambda: conn
        )
        assert "SELECT window_start" in conn.sql
        assert "state = 'sealed'" in conn.sql
        assert conn.params == ("grid_trading::BTCUSDT",)

    def test_executor_short_circuits_on_overlap_no_dsr_no_debit(self, fdr, monkeypatch):
        """executor 端：sealed overlap ⇒ 渲染前短路（無 dsr verdict、無 debit、無 pre-reg）。"""
        monkeypatch.setattr(
            EXEC, "_check_sealed_boundary",
            lambda strategy, symbol, we, conn: (True, ["sealed_holdout_overlap"]),
        )
        res = _run(_run_stage(_gate_context()))
        assert res["verdict"] == "DEFER"
        assert "sealed_holdout_overlap" in res["reasons"]
        assert "dsr" not in res["stage_verdicts"]
        assert fdr["debits"] == [] and fdr["preregs"] == []

    def test_math_gate_defense_in_depth_stage(self):
        """gate 防禦縱深：gate_inputs 帶 sealed_holdout_overlap=True ⇒ stage DEFER；
        False ⇒ pass stage；無鍵 ⇒ 無 sealed stage（legacy 路徑零波及）。"""
        ctx = _gate_context()
        ctx["math_gate_inputs"]["sealed_holdout_overlap"] = True
        res = EXEC._run_math_gate(_guard_out(), ctx, novelty="novel")
        assert res["stage_verdicts"]["sealed_boundary"] == "DEFER"
        assert "sealed_holdout_overlap" in res["reasons"]
        ctx["math_gate_inputs"]["sealed_holdout_overlap"] = False
        res2 = EXEC._run_math_gate(_guard_out(), ctx, novelty="novel")
        assert res2["stage_verdicts"]["sealed_boundary"] == "pass"
        ctx["math_gate_inputs"].pop("sealed_holdout_overlap")
        res3 = EXEC._run_math_gate(_guard_out(), ctx, novelty="novel")
        assert "sealed_boundary" not in res3["stage_verdicts"]


# ═══════════════════════════════════════════════════════════════════════════════
# MIT #2 Option B — threshold 咬合 + 邊界
# ═══════════════════════════════════════════════════════════════════════════════


class TestOptionBThreshold:
    def test_threshold_bites_through_real_compute_dsr(self):
        """同 fixture（marginal sharpe 1.5）：默認（0.95）pass、threshold→1−1e-9 fail ⇒
        注入經真 compute_dsr 生效非裝飾（mutation 對照）。"""
        ctx = _gate_context()
        ctx["math_gate_inputs"]["observed_sharpe"] = 1.5  # 0.95 與 1−1e-9 之間的 marginal 點
        res_default = EXEC._run_math_gate(_guard_out(), ctx, novelty="novel")
        assert res_default["stage_verdicts"]["dsr"] == "pass"
        res_tight = EXEC._run_math_gate(
            _guard_out(), ctx, novelty="novel", dsr_threshold=1 - 1e-9
        )
        assert res_tight["stage_verdicts"]["dsr"] == "fail"

    def test_threshold_one_fails_soft_to_defer(self):
        """α_i 下溢 → threshold=1.0 → compute_dsr 域檢 raise → DEFER（收縮不 crash，勿 clamp）。"""
        out = EXEC._run_dsr_stage(3.0, 5, 200, threshold=1.0)
        assert out["verdict"] == "DEFER"
        assert "dsr_compute_error" in out["reasons"]

    def test_stage_threads_threshold_from_controller(self, fdr, monkeypatch):
        """STAGE 4 的 threshold 來自 dsr_threshold_for(α_i)（捕捉傳遞值）。"""
        seen: dict[str, Any] = {}

        class _Awc(_FakeAwc):
            @staticmethod
            def dsr_threshold_for(alpha_i, *, floor: float = 0.95) -> float:
                seen["alpha_i"] = alpha_i
                return 0.97

        monkeypatch.setattr(EXEC, "_resolve_wealth_controller", lambda: _Awc)
        res = _run(_run_stage(_gate_context()))
        assert res["fdr"]["dsr_threshold"] == 0.97
        # α_i = min(0.10·0.005, 0.005) = 5e-4（fake balance 0.005）。
        assert seen["alpha_i"] == pytest.approx(5e-4)


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 3.6/3.7 — pre-reg 次序 / wealth admission 收縮向
# ═══════════════════════════════════════════════════════════════════════════════


class TestWealthAdmission:
    def test_prereg_before_gate_render(self, fdr, monkeypatch):
        """FIX-1.2：hash/pre-reg 先於一切統計渲染（呼叫序 prereg → gate）。"""
        original_gate = EXEC._run_math_gate

        def _spy_gate(*a, **kw):
            fdr["order"].append("gate")
            return original_gate(*a, **kw)

        monkeypatch.setattr(EXEC, "_run_math_gate", _spy_gate)
        _run(_run_stage(_gate_context()))
        assert fdr["order"].index("prereg") < fdr["order"].index("gate")

    def test_prereg_defer_reasons_propagate(self, fdr, monkeypatch):
        for reason in ("pre_registration_superseded", "pre_registration_mismatch"):
            monkeypatch.setattr(
                STORE, "register_pre_registration",
                lambda __r=reason, **kw: STORE.PreRegistrationOutcome(
                    ok=False, defer_reason=__r
                ),
            )
            res = _run(_run_stage(_gate_context()))
            assert res["verdict"] == "DEFER"
            assert reason in res["reasons"]
            assert "dsr" not in res["stage_verdicts"]  # 未渲染
            assert fdr["debits"] == []

    def test_store_unreachable_defers(self, fdr, monkeypatch):
        def _boom(**kw):
            raise STORE.AlphaWealthStoreError("down")

        monkeypatch.setattr(STORE, "register_pre_registration", _boom)
        res = _run(_run_stage(_gate_context()))
        assert res["verdict"] == "DEFER"
        assert "alpha_wealth_store_unavailable" in res["reasons"]
        assert fdr["debits"] == []

    def test_controller_unavailable_defers(self, fdr, monkeypatch):
        monkeypatch.setattr(EXEC, "_resolve_wealth_controller", lambda: None)
        res = _run(_run_stage(_gate_context()))
        assert res["verdict"] == "DEFER"
        assert "alpha_wealth_store_unavailable" in res["reasons"]

    def test_wealth_exhausted_defers_without_render(self, fdr, monkeypatch):
        monkeypatch.setattr(STORE, "get_family_balance", lambda *a, **kw: 0.0)
        res = _run(_run_stage(_gate_context()))
        assert res["verdict"] == "DEFER"
        assert "alpha_wealth_exhausted" in res["reasons"]
        assert "dsr" not in res["stage_verdicts"]
        assert fdr["debits"] == []

    def test_family_id_is_capability_primary_axis(self, fdr):
        res = _run(_run_stage(_gate_context()))
        assert res["fdr"]["family_id"] == "ml_advisory.hypothesize:funding_rate"
        assert fdr["preregs"][0]["signal_axis"] == "funding_rate"
        # FIX-1.2：spec 內含 evidence 窗（入 hash payload）。
        spec = fdr["preregs"][0]["spec_jsonb"]
        assert spec["evidence_window"] == {
            "window_start": "2025-01-01", "window_end": "2025-09-30"
        }
        # falsification 三欄入 spec（V137 CHECK 形）。
        assert set(spec["falsification_test"]) == {
            "null_hypothesis", "test_statistic", "reject_condition"
        }


# ═══════════════════════════════════════════════════════════════════════════════
# QC FIX-1.3 — dead-mode lesson（直測 mint helper；cascade 面在 P3b b1_fail 測）
# ═══════════════════════════════════════════════════════════════════════════════


class _MintConn:
    def __init__(self, store: list):
        self._store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self._store.append({"sql": " ".join(sql.split()), "params": params})

    def commit(self):
        pass


class TestFix13DeadModeMint:
    def _spec(self):
        return {
            "statement": "funding skew predicts reversion",
            "mechanism": "crowded longs pay funding",
            "primary_axis": "funding_rate",
            "falsification_test": {
                "null_hypothesis": "no predictive power",
                "test_statistic": "deflated Sharpe",
                "reject_condition": "DSR below threshold",
            },
        }

    def test_mint_idempotent_namespace_and_english_content(self):
        store: list = []
        ok = EXEC._mint_dead_mode_lesson(
            spec=self._spec(), spec_sha256="ab" * 32, symbol="BTCUSDT",
            trigger="manual", math_reasons=["b1_down_beta"],
            conn_provider=lambda: _MintConn(store),
        )
        assert ok is True
        row = store[0]
        assert "INSERT INTO agent.lessons" in row["sql"]
        assert "WHERE NOT EXISTS" in row["sql"]  # 冪等（seed 腳本同款）
        p = row["params"]
        assert p["source"] == "dead_mode_seed"
        # 冪等錨點：deadmode:<spec_sha256 前 16 hex>（確定性，重鑄同 id 被 NOT EXISTS 擋）。
        assert p["context_id"] == "deadmode:" + ("ab" * 32)[:16]
        content = p["content"]
        assert content.startswith("DEAD MODE [funding_rate]")
        for token in ("null_hypothesis=", "test_statistic=", "reject_condition="):
            assert token in content
        assert "'dead_mode'" in row["sql"]  # lesson_type = novelty 檢索鍵

    def test_mint_fail_soft_on_db_down(self):
        class _Down:
            def __enter__(self):
                raise RuntimeError("down")

            def __exit__(self, *a):
                return False

        ok = EXEC._mint_dead_mode_lesson(
            spec=self._spec(), spec_sha256="cd" * 32, symbol=None,
            trigger="manual", math_reasons=["x"], conn_provider=lambda: _Down(),
        )
        assert ok is False


# ═══════════════════════════════════════════════════════════════════════════════
# M2 — N_eff seam（adapter）
# ═══════════════════════════════════════════════════════════════════════════════


def _evidence(**over) -> dict[str, Any]:
    body: dict[str, Any] = {
        "evidence_schema": ADAPTER.EVIDENCE_SCHEMA_V1,
        "window_start": "2025-01-01",
        "window_end": "2025-09-30",
        "regime_rows": [
            {"regime": "all", "n_independent": 200, "oos_sharpe": 1.2, "k_trials": 7}
        ],
        "return_unit": "fraction",
    }
    body.update(over)
    return body


class TestNEffSeam:
    def test_variant_returns_injects_n_eff(self, monkeypatch):
        captured: dict[str, Any] = {}

        def _fake_cluster(series_list, **kw):
            captured["series"] = series_list
            return SimpleNamespace(n_eff=3, clusters=[[0, 1], [2]], reasons=["r1"])

        monkeypatch.setattr(ADAPTER, "_resolve_n_eff_cluster", lambda: _fake_cluster)
        ev = _evidence(
            variant_returns=[
                {"2025-01-01": 0.001, "2025-01-02": 0.002},
                {"2025-01-01": 0.001, "2025-01-02": 0.002},
                {"2025-01-01": -0.001, "2025-01-02": 0.0},
            ]
        )
        ctx, reasons = ADAPTER.build_math_gate_context(ev, factors=None)
        gi = ctx["math_gate_inputs"]
        assert gi["n_trials"] == 3
        assert gi["n_eff_source"] == "avg_linkage_corr_gt_0p5"
        assert "n_eff_unavailable_raw_k_trials" not in reasons
        # 共享 ordinal int key（跨 variant 對齊；同日 → 同 key）。
        keys0 = set(captured["series"][0])
        keys1 = set(captured["series"][1])
        assert keys0 == keys1
        assert all(isinstance(k, int) for k in keys0)

    def test_absent_variants_raw_k_trials_fallback(self):
        ctx, reasons = ADAPTER.build_math_gate_context(_evidence(), factors=None)
        assert ctx["math_gate_inputs"]["n_trials"] == 7  # raw k_trials
        assert "n_eff_unavailable_raw_k_trials" in reasons

    def test_malformed_variant_member_falls_back(self, monkeypatch):
        monkeypatch.setattr(
            ADAPTER, "_resolve_n_eff_cluster",
            lambda: (lambda s, **kw: SimpleNamespace(n_eff=1, clusters=[], reasons=[])),
        )
        ev = _evidence(variant_returns=[{"2025-01-01": "not-a-number"}])
        ctx, reasons = ADAPTER.build_math_gate_context(ev, factors=None)
        assert ctx["math_gate_inputs"]["n_trials"] == 7
        assert any(r.startswith("variant_returns_member_invalid") for r in reasons)
        assert "n_eff_unavailable_raw_k_trials" in reasons

    def test_cluster_module_unavailable_falls_back(self, monkeypatch):
        monkeypatch.setattr(ADAPTER, "_resolve_n_eff_cluster", lambda: None)
        ev = _evidence(variant_returns=[{"2025-01-01": 0.001}])
        ctx, reasons = ADAPTER.build_math_gate_context(ev, factors=None)
        assert ctx["math_gate_inputs"]["n_trials"] == 7
        assert "n_eff_cluster_unavailable" in reasons

    def test_evidence_window_threaded_into_context(self):
        ctx, _ = ADAPTER.build_math_gate_context(_evidence(), factors=None)
        assert ctx["evidence_window"] == {
            "window_start": "2025-01-01", "window_end": "2025-09-30"
        }


# ═══════════════════════════════════════════════════════════════════════════════
# guard clause F + contract v2 三點同步
# ═══════════════════════════════════════════════════════════════════════════════


class TestGuardClauseF:
    def _ctx(self):
        return {"available_signal_axes": ["funding_rate", "adx_1h"]}

    def test_valid_v2_passes(self):
        res = GUARD.run_guard(_guard_out(), guard_ref="ml_advisory.guard.v1", context=self._ctx())
        assert res.verdict == "pass"

    def test_v1_free_text_falsification_rejected(self):
        out = _guard_out()
        out["feature_hypotheses"][0]["falsification_test"] = "permutation test"
        res = GUARD.run_guard(out, guard_ref="ml_advisory.guard.v1", context=self._ctx())
        assert res.verdict == "reject"
        assert any("falsification_not_structured" in k for k in res.kinds_hit)

    @pytest.mark.parametrize("fld", ["null_hypothesis", "test_statistic", "reject_condition"])
    def test_empty_falsification_field_rejected(self, fld):
        out = _guard_out()
        out["feature_hypotheses"][0]["falsification_test"][fld] = "  "
        res = GUARD.run_guard(out, guard_ref="ml_advisory.guard.v1", context=self._ctx())
        assert res.verdict == "reject"
        assert any(f"falsification_field_empty:{fld}" in k for k in res.kinds_hit)

    def test_primary_axis_missing_rejected(self):
        out = _guard_out()
        del out["feature_hypotheses"][0]["primary_axis"]
        res = GUARD.run_guard(out, guard_ref="ml_advisory.guard.v1", context=self._ctx())
        assert res.verdict == "reject"
        assert any("primary_axis_missing" in k for k in res.kinds_hit)

    def test_primary_axis_outside_axes_rejected(self):
        """MIT #4：primary_axis ∉ signal_axes_used = family 鑄幣攻擊面 → reject。"""
        out = _guard_out()
        out["feature_hypotheses"][0]["primary_axis"] = "adx_1h"  # 不在假說 axes（funding only）
        res = GUARD.run_guard(out, guard_ref="ml_advisory.guard.v1", context=self._ctx())
        assert res.verdict == "reject"
        assert any("primary_axis_not_in_signal_axes_used" in k for k in res.kinds_hit)

    def test_primary_axis_falls_back_to_top_level_axes(self):
        out = _guard_out()
        del out["feature_hypotheses"][0]["signal_axes_used"]  # 假說無自帶 → 退 top-level
        res = GUARD.run_guard(out, guard_ref="ml_advisory.guard.v1", context=self._ctx())
        assert res.verdict == "pass"

    def test_p3a_modes_unaffected_by_clause_f(self):
        diag = {
            "mode": "diagnose_leak",
            "leak_drift_diagnosis": {
                "suspected_cause": "x",
                "evidence": [{"claim": "c", "kind": "leak", "source_ref": "r",
                              "source_class": "name_pattern_check"}],
            },
        }
        res = GUARD.run_guard(diag, guard_ref="ml_advisory.guard.v1", context=self._ctx())
        assert res.verdict == "pass"


class TestContractV2Sync:
    def test_v2_registered_v1_retained(self):
        v1 = CONTRACTS.get_prompt_contract("ml_advisory.hypothesize.v1")
        v2 = CONTRACTS.get_prompt_contract("ml_advisory.hypothesize.v2")
        assert v1 is not None and v2 is not None  # v1 保留（D3 血緣不可變）
        assert v2.contract_ver == "ml_advisory_hypothesize.v2"
        for token in ("null_hypothesis", "test_statistic", "reject_condition", "primary_axis"):
            assert token in v2.template

    def test_three_point_sync_toml_executor_registry(self):
        """TOML stanza ref == executor _MODE_CONTRACT_REF == registry 註冊（同 commit 鐵則）。"""
        assert EXEC._MODE_CONTRACT_REF["hypothesize"] == "ml_advisory.hypothesize.v2"
        toml_path = _SRV_ROOT / "settings" / "l2_capability_registry.toml"
        text = toml_path.read_text(encoding="utf-8")
        assert 'prompt_contract_ref    = "ml_advisory.hypothesize.v2"' in text
        assert CONTRACTS.get_prompt_contract("ml_advisory.hypothesize.v2") is not None

    def test_resolve_contract_versions_v2(self):
        cv, sv = CONTRACTS.resolve_contract_versions(
            capability_id="ml_advisory.hypothesize",
            contract_ref="ml_advisory.hypothesize.v2",
        )
        assert cv == "ml_advisory_hypothesize.v2"
        assert sv == "ml_advisory_schema.v1"


# ═══════════════════════════════════════════════════════════════════════════════
# P4 §6 — orchestrator tier_provider（fail-closed L1）
# ═══════════════════════════════════════════════════════════════════════════════


def _hyp_cap(**over):
    import app.l2_capability_registry as REG

    body = {
        "capability_id": "ml_advisory.hypothesize",
        "enabled": True,
        "min_tier": "L3",
        "tier_capability_flag": "can_generate_hypotheses",
        "lane": "ml_backlog",
    }
    body.update(over)
    return REG.L2Capability(**body)


class _OkTracker:
    def check_daily_budget(self):
        return True, 2.0


def _orch(**kw):
    return ORCH.L2AdvisoryOrchestrator(cost_tracker=_OkTracker(), **kw)


class TestTierProvider:
    def test_default_none_byte_identical_tier_locked(self):
        o = _orch()
        d = o._admit(_hyp_cap(), coarse_subject="s", ts=1000.0)
        assert not d.admitted
        assert d.reason == "tier_locked"

    def test_provider_l3_with_flag_unlocks(self):
        o = _orch(tier_provider=lambda: (LearningTier.L3, {"can_generate_hypotheses": True}))
        d = o._admit(_hyp_cap(), coarse_subject="s", ts=1000.0)
        assert d.admitted, d.reason

    def test_provider_l3_flag_false_still_locked(self):
        o = _orch(tier_provider=lambda: (LearningTier.L3, {"can_generate_hypotheses": False}))
        d = o._admit(_hyp_cap(), coarse_subject="s", ts=1000.0)
        assert not d.admitted
        assert d.reason == "tier_locked"

    def test_provider_raise_fails_closed_to_l1(self):
        def _boom():
            raise RuntimeError("gate down")

        o = _orch(tier_provider=_boom)
        d = o._admit(_hyp_cap(), coarse_subject="s", ts=1000.0)
        assert not d.admitted
        assert d.reason == "tier_locked"

    def test_provider_garbage_fails_closed(self):
        o = _orch(tier_provider=lambda: ("L5", {"can_generate_hypotheses": True}))
        d = o._admit(_hyp_cap(), coarse_subject="s", ts=1000.0)
        assert not d.admitted

    def test_set_if_absent_idempotent(self):
        o = _orch()
        p1 = lambda: (LearningTier.L3, {})  # noqa: E731
        p2 = lambda: (LearningTier.L1, {})  # noqa: E731
        o.set_tier_provider_if_absent(p1)
        o.set_tier_provider_if_absent(p2)
        assert o._tier_provider is p1  # 不被第二次覆蓋

    def test_status_exposes_wiring_and_effective_tier(self, monkeypatch):
        o = _orch(
            tier_provider=lambda: (LearningTier.L2, {}),
            registry_loader=lambda: __import__(
                "app.l2_capability_registry", fromlist=["L2CapabilityRegistry"]
            ).L2CapabilityRegistry(),
        )
        st = o.status()
        assert st["tier_provider_wired"] is True
        assert st["effective_tier"] == "L2"
        assert st["current_tier"] == "L1"  # 構造默認不變（誠實：系統真值仍 L1）

    def test_routes_projection_reads_gate_lazily(self, monkeypatch):
        from app import layer2_routes as LR
        from app import paper_trading_wiring as PTW

        class _Caps:
            can_generate_hypotheses = True
            can_record_observations = True

        class _Gate:
            current_tier = LearningTier.L3
            capabilities = _Caps()

        monkeypatch.setattr(PTW, "LEARNING_TIER_GATE", _Gate(), raising=False)
        tier, flags = LR._governance_tier_projection()
        assert tier == LearningTier.L3
        assert flags["can_generate_hypotheses"] is True

    def test_routes_projection_raises_when_gate_unwired(self, monkeypatch):
        from app import layer2_routes as LR
        from app import paper_trading_wiring as PTW

        monkeypatch.setattr(PTW, "LEARNING_TIER_GATE", None, raising=False)
        with pytest.raises(RuntimeError):
            LR._governance_tier_projection()


# ═══════════════════════════════════════════════════════════════════════════════
# 鐵則：P3a 零波及 + 硬邊界指紋 + hidden_oos 0 寫點
# ═══════════════════════════════════════════════════════════════════════════════


class TestIronRules:
    def test_p3a_modes_never_touch_fdr_machinery(self, monkeypatch):
        """P3a diagnose/interpret 路徑 0 波及：wealth/pre-reg/sealed 全不被呼叫。"""
        touched = []
        monkeypatch.setattr(
            EXEC, "_resolve_wealth_controller", lambda: touched.append("awc")
        )
        monkeypatch.setattr(
            EXEC, "_check_sealed_boundary",
            lambda *a, **kw: touched.append("sealed") or (False, []),
        )

        class _Eng:
            class _T:
                def get_config(self):
                    return SimpleNamespace(default_provider="anthropic")

                def record_claude_cost(self, *a, **kw):
                    return 0.0

            _cost_tracker = _T()

            def _resolve_effective_provider(self, **kw):
                return "anthropic", "haiku"

            async def _provider_complete(self, **kw):
                return None  # cloud 不可用 → cascade 早退（仍走過 P3a 主幹）

        res = _run(EXEC.run_ml_advisory_cascade(
            capability_id="ml_advisory.diagnose_leak", mode="diagnose_leak",
            context={}, engine=_Eng(), contract_ver="x", schema_ver="y",
            calibration=EXEC.OllamaScreenCalibration(
                enabled=False, recall=None, threshold=0.85,
                benchmark_version="absent", reason="no benchmark",
            ),
        ))
        assert touched == []
        assert res.math_gate_verdict is None

    def test_hard_boundary_fingerprint_all_p4_touched_modules(self):
        for mod in (EXEC, ADAPTER, STORE, ORCH, GUARD, CONTRACTS):
            code = " ".join(
                t.string
                for t in tokenize.generate_tokens(
                    io.StringIO(inspect.getsource(mod)).readline
                )
                if t.type not in (tokenize.COMMENT, tokenize.STRING)
            )
            for token in (
                "promote_tier", "acquire_lease", "live_execution_allowed",
                "execution_authority", "system_mode", "OPENCLAW_ALLOW_MAINNET",
            ):
                assert token not in code, f"{token} in {mod.__name__}"

    def test_l2_modules_zero_writes_to_hidden_oos_registry(self):
        """§9.4/gate-5：l2_*.py 對 hidden_oos_state_registry 0 INSERT/UPDATE/DELETE 寫點。"""
        app_dir = PROJECT_ROOT / "app"
        for f in sorted(app_dir.glob("l2_*.py")):
            src = f.read_text(encoding="utf-8")
            if "hidden_oos_state_registry" not in src:
                continue
            for verb in ("INSERT INTO learning.hidden_oos_state_registry",
                         "UPDATE learning.hidden_oos_state_registry",
                         "DELETE FROM learning.hidden_oos_state_registry"):
                assert verb not in src, f"{f.name} 含 registry 寫點"

    def test_executor_docstring_no_longer_claims_short_circuit(self):
        """MIT N-8：_run_math_gate docstring 不得再宣稱 short-circuit（與實作不符）。"""
        doc = EXEC._run_math_gate.__doc__ or ""
        assert "短路" not in doc.split("無 short-circuit")[0]
        assert "無 short-circuit" in doc

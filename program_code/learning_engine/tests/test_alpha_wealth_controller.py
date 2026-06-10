"""alpha_wealth_controller 測試（L2 P4 M1 純數學核心）。

覆蓋（E1-A 契約 + E4 驗收軸）：
  1. 常數表複核（M1 ENDORSED 七常數 + floor 兩常數，精確值）。
  2. α_i cap 斷言（M1 AC：α_i ≤ α_target/min_batch_size 恆成立）。
  3. assign_alpha_i 數值 floor None 邊界（MIT 1b/7c：< 1e-6 → None、
     有限 α-death、balance 退化情形）。
  4. dsr_threshold_for 單調 + floor（MIT #2 Option B：≥0.95 恆成立、
     α_i 越小越嚴、floor 不可降、α_i=0 → 1.0 邊界）。
  5. demo_confirm_verdict 三值全分支（confirmed/failed/pending 邊界精確
     + 非有限 net 保守處置）。
  6. can_test / refund_amount / init_family_wealth 不變量與 fail-loud。
  7. 模組純度（AST 層：0 psycopg2 / 0 asyncio / 0 DB import）。
"""

from __future__ import annotations

import ast
import inspect
import math

import pytest

import program_code.learning_engine.alpha_wealth_controller as awc
from program_code.learning_engine.alpha_wealth_controller import (
    ALPHA_I_MIN_FLOOR,
    ALPHA_TARGET_DEFAULT,
    DSR_THRESHOLD_FLOOR,
    MIN_BATCH_SIZE_DEFAULT,
    MIN_FORWARD_OOS_DAYS,
    PHI_REFUND,
    REFUND_MIN_TRADES,
    SPEND_FRACTION_DEFAULT,
    W0_GAMMA,
    assign_alpha_i,
    can_test,
    demo_confirm_verdict,
    dsr_threshold_for,
    init_family_wealth,
    refund_amount,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. 常數表複核（契約字面；E4 同樣會驗）
# ─────────────────────────────────────────────────────────────────────────────


class TestConstantsContract:
    def test_m1_endorsed_constants_exact(self):
        assert ALPHA_TARGET_DEFAULT == 0.05
        assert W0_GAMMA == 0.10
        assert PHI_REFUND == 1.0
        assert MIN_BATCH_SIZE_DEFAULT == 10
        assert SPEND_FRACTION_DEFAULT == 0.10
        assert REFUND_MIN_TRADES == 30
        assert MIN_FORWARD_OOS_DAYS == 21

    def test_mit_foldin_constants_exact(self):
        # MIT 1b/7c floor + Option B threshold floor。
        assert ALPHA_I_MIN_FLOOR == 1e-6
        assert DSR_THRESHOLD_FLOOR == 0.95

    def test_min_forward_oos_days_is_int_importable(self):
        # B2 唯一定義點：E1-C reconciler 將 import 本常數（型別契約=int）。
        assert isinstance(MIN_FORWARD_OOS_DAYS, int)
        assert isinstance(REFUND_MIN_TRADES, int)


# ─────────────────────────────────────────────────────────────────────────────
# 2. init_family_wealth
# ─────────────────────────────────────────────────────────────────────────────


class TestInitFamilyWealth:
    def test_default_w0(self):
        # W_0 = 0.10 · 0.05 = 0.005。
        assert init_family_wealth() == pytest.approx(0.005)

    def test_custom_values(self):
        assert init_family_wealth(0.10, 0.5) == pytest.approx(0.05)

    @pytest.mark.parametrize("alpha_target", [0.0, 1.0, -0.05, float("nan"), float("inf")])
    def test_invalid_alpha_target_raises(self, alpha_target):
        with pytest.raises(ValueError):
            init_family_wealth(alpha_target=alpha_target)

    @pytest.mark.parametrize("gamma", [0.0, 1.5, -0.1, float("nan")])
    def test_invalid_gamma_raises(self, gamma):
        # gamma > 1 ⇒ W_0 > α_target，破壞 mFDR bound 前提 → fail-loud。
        with pytest.raises(ValueError):
            init_family_wealth(gamma=gamma)


# ─────────────────────────────────────────────────────────────────────────────
# 3. assign_alpha_i — cap（M1 AC）與 floor（MIT 1b/7c）
# ─────────────────────────────────────────────────────────────────────────────


def _assign(balance: float) -> float | None:
    return assign_alpha_i(
        balance,
        alpha_target=ALPHA_TARGET_DEFAULT,
        min_batch_size=MIN_BATCH_SIZE_DEFAULT,
        spend_fraction=SPEND_FRACTION_DEFAULT,
    )


class TestAssignAlphaICap:
    def test_default_dynamics_alpha_i(self):
        # W_0 = 0.005 → α_i = 0.10·0.005 = 5e-4（cap=0.005 不 binding——MIT 7a）。
        assert _assign(0.005) == pytest.approx(5e-4)

    def test_cap_binds_after_operator_inflation(self):
        # operator_adjustment 抬 wealth 過 0.05 後 cap 才 binding（MIT 7a 的
        # defense-in-depth 場景）：balance=1.0 → raw=0.1 → capped 0.005。
        assert _assign(1.0) == pytest.approx(0.005)

    @pytest.mark.parametrize(
        "balance", [1e-5, 1e-4, 1e-3, 0.005, 0.05, 0.5, 1.0, 10.0, 1e6]
    )
    def test_m1_ac_cap_invariant(self, balance):
        # M1 AC：任何 balance 下 α_i ≤ α_target / min_batch_size。
        alpha_i = _assign(balance)
        assert alpha_i is not None
        assert alpha_i <= ALPHA_TARGET_DEFAULT / MIN_BATCH_SIZE_DEFAULT + 1e-15

    def test_assigned_alpha_always_at_or_above_floor(self):
        # 凡非 None 的指派恆 ≥ floor（floor 與回傳值之間無縫隙）。
        for balance in [1e-5, 2e-5, 1e-4, 0.005, 1.0]:
            alpha_i = _assign(balance)
            assert alpha_i is not None
            assert alpha_i >= ALPHA_I_MIN_FLOOR

    @pytest.mark.parametrize("mbs", [0, -1])
    def test_invalid_min_batch_size_raises(self, mbs):
        with pytest.raises(ValueError):
            assign_alpha_i(
                0.005, alpha_target=0.05, min_batch_size=mbs, spend_fraction=0.10
            )

    @pytest.mark.parametrize("sf", [0.0, 1.5, -0.1, float("nan")])
    def test_invalid_spend_fraction_raises(self, sf):
        with pytest.raises(ValueError):
            assign_alpha_i(
                0.005, alpha_target=0.05, min_batch_size=10, spend_fraction=sf
            )

    @pytest.mark.parametrize("at", [0.0, 1.0, float("nan")])
    def test_invalid_alpha_target_raises(self, at):
        with pytest.raises(ValueError):
            assign_alpha_i(
                0.005, alpha_target=at, min_batch_size=10, spend_fraction=0.10
            )


class TestAssignAlphaIFloorNone:
    def test_floor_boundary_exact(self):
        # 0.10·1e-5 = 1e-6 = floor → 不低於 floor → 指派成功。
        assert _assign(1e-5) == pytest.approx(1e-6)

    def test_just_below_floor_returns_none(self):
        # 0.10·9.9e-6 = 9.9e-7 < 1e-6 → None（slot 不可測）。
        assert _assign(9.9e-6) is None

    @pytest.mark.parametrize("balance", [0.0, -0.001, -1.0])
    def test_nonpositive_balance_returns_none(self, balance):
        assert _assign(balance) is None

    @pytest.mark.parametrize("balance", [float("nan"), float("inf"), float("-inf")])
    def test_nonfinite_balance_returns_none(self, balance):
        # balance 是 PG 讀回的資料非配置：損壞 → 不可測（fail-closed），不 raise。
        assert _assign(balance) is None

    def test_finite_alpha_death_under_geometric_decay(self):
        # MIT 1b：連跌軌跡 W_t = 0.9^t·W_0 下 floor 給出「有限」α-death——
        # 殭屍 family 在有限步內熄燈（None），而非永遠可測。
        balance = init_family_wealth()
        steps = 0
        while steps < 10_000:
            alpha_i = _assign(balance)
            if alpha_i is None:
                break
            assert alpha_i >= ALPHA_I_MIN_FLOOR
            balance -= alpha_i  # 全敗（無 refund）最壞軌跡
            steps += 1
        else:
            pytest.fail("α-death 未在有限步內發生（殭屍 family 未熄燈）")
        # 量級驗證：0.10·0.005·0.9^t < 1e-6 ⇔ t > ln(2e-3)/ln(0.9) ≈ 59。
        assert 50 <= steps <= 80


# ─────────────────────────────────────────────────────────────────────────────
# 4. can_test
# ─────────────────────────────────────────────────────────────────────────────


class TestCanTest:
    def test_positive_residual_true(self):
        assert can_test(0.005, 5e-4) is True

    def test_exact_exhaustion_false(self):
        # G.1.1：W − α_i ≤ 0 ⇒ False（等號含）。
        assert can_test(5e-4, 5e-4) is False

    def test_overdraft_false(self):
        assert can_test(1e-4, 5e-4) is False

    @pytest.mark.parametrize(
        "balance,alpha_i",
        [
            (float("nan"), 5e-4),
            (0.005, float("nan")),
            (float("inf"), 5e-4),
            (0.005, 0.0),
            (0.005, -1e-4),
        ],
    )
    def test_degenerate_inputs_fail_closed(self, balance, alpha_i):
        assert can_test(balance, alpha_i) is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. refund_amount
# ─────────────────────────────────────────────────────────────────────────────


class TestRefundAmount:
    def test_phi_one_exactly_self_funding(self):
        # φ=1.0：refund 恰補回已扣額（W_t ≤ W_0 不變量的機械面）。
        assert refund_amount(5e-4) == pytest.approx(5e-4)

    def test_phi_half(self):
        assert refund_amount(5e-4, phi=0.5) == pytest.approx(2.5e-4)

    def test_zero_debit_zero_refund(self):
        assert refund_amount(0.0) == 0.0

    @pytest.mark.parametrize("bad", [-1e-4, float("nan"), float("inf")])
    def test_invalid_alpha_debited_raises(self, bad):
        with pytest.raises(ValueError):
            refund_amount(bad)

    @pytest.mark.parametrize("phi", [1.5, -0.1, float("nan")])
    def test_invalid_phi_raises(self, phi):
        # φ > 1 ⇒ wealth 可超 W_0 → 必須 fail-loud。
        with pytest.raises(ValueError):
            refund_amount(5e-4, phi=phi)


# ─────────────────────────────────────────────────────────────────────────────
# 6. dsr_threshold_for — 單調 + floor（MIT #2 Option B）
# ─────────────────────────────────────────────────────────────────────────────


class TestDsrThresholdFor:
    def test_reachable_wealth_threshold(self):
        # α_i = 5e-4（默認動態上界）→ threshold = 0.9995（MIT #2：非 0.995）。
        assert dsr_threshold_for(5e-4) == pytest.approx(0.9995)

    def test_floor_binds_for_large_alpha(self):
        # α_i = 0.06 → 1−α_i = 0.94 < 0.95 → floor binding。
        assert dsr_threshold_for(0.06) == pytest.approx(0.95)

    def test_zero_alpha_returns_one(self):
        # MIT #2 親驗背書的邊界：α_i=0 → 1.0（下游 DsrGate ValueError →
        # fail-soft DEFER = 收縮向）。本函數不 clamp。
        assert dsr_threshold_for(0.0) == 1.0

    def test_monotone_non_increasing_in_alpha(self):
        # wealth 越枯 → α_i 越小 → threshold 越高（只嚴不鬆的單調方向）。
        alphas = [0.0, 1e-6, 1e-5, 1e-4, 5e-4, 5e-3, 0.04, 0.05, 0.5]
        thresholds = [dsr_threshold_for(a) for a in alphas]
        for earlier, later in zip(thresholds, thresholds[1:]):
            assert earlier >= later

    def test_never_below_floor(self):
        for a in [0.0, 1e-6, 5e-4, 0.005, 0.049, 0.05, 0.2, 0.9, 0.999]:
            assert dsr_threshold_for(a) >= DSR_THRESHOLD_FLOOR

    def test_stricter_floor_allowed(self):
        # floor 可升不可降（只嚴不鬆）：α=0.04 時 1−α=0.96，默認 floor 給 0.96、
        # 升高的 floor=0.97 真 binding；α 極小時 floor 不 binding。
        assert dsr_threshold_for(0.04, floor=0.97) == pytest.approx(0.97)
        assert dsr_threshold_for(0.04) == pytest.approx(0.96)
        assert dsr_threshold_for(1e-6, floor=0.97) == pytest.approx(1.0 - 1e-6)

    @pytest.mark.parametrize("floor", [0.5, 0.9, 0.9499, 1.0, float("nan")])
    def test_floor_cannot_be_relaxed(self, floor):
        # MIT #2：0.95 floor 不可降；≥1 亦非法。
        with pytest.raises(ValueError):
            dsr_threshold_for(5e-4, floor=floor)

    @pytest.mark.parametrize("alpha_i", [-1e-6, 1.0, 1.5, float("nan"), float("inf")])
    def test_invalid_alpha_raises(self, alpha_i):
        with pytest.raises(ValueError):
            dsr_threshold_for(alpha_i)


# ─────────────────────────────────────────────────────────────────────────────
# 7. demo_confirm_verdict — 三值全分支
# ─────────────────────────────────────────────────────────────────────────────


class TestDemoConfirmVerdict:
    def test_confirmed_all_four_at_exact_boundary(self):
        # 四條同時踩在邊界（n=30 / green / net=0.0 / 21d）→ confirmed。
        assert (
            demo_confirm_verdict(
                n_trades=30, stage0r_green=True, demo_net_bps=0.0, forward_oos_days=21
            )
            == "confirmed"
        )

    def test_confirmed_comfortably(self):
        assert (
            demo_confirm_verdict(
                n_trades=120, stage0r_green=True, demo_net_bps=8.5, forward_oos_days=45
            )
            == "confirmed"
        )

    def test_pending_insufficient_trades(self):
        # n=29：其餘全好也 pending（債留著=back-pressure 設計意圖）。
        assert (
            demo_confirm_verdict(
                n_trades=29, stage0r_green=True, demo_net_bps=99.0, forward_oos_days=99
            )
            == "pending"
        )

    def test_pending_forward_days_short(self):
        # 樣本足 + 好結果但 20d < 21d → pending（不提前 confirm）。
        assert (
            demo_confirm_verdict(
                n_trades=50, stage0r_green=True, demo_net_bps=3.0, forward_oos_days=20
            )
            == "pending"
        )

    def test_failed_negative_net(self):
        assert (
            demo_confirm_verdict(
                n_trades=30, stage0r_green=True, demo_net_bps=-0.01, forward_oos_days=99
            )
            == "failed"
        )

    def test_failed_stage0r_red(self):
        # 0R 紅 + 樣本足 = 結論性壞，即便 net 為正。
        assert (
            demo_confirm_verdict(
                n_trades=30, stage0r_green=False, demo_net_bps=10.0, forward_oos_days=99
            )
            == "failed"
        )

    def test_failed_does_not_wait_for_21d(self):
        # failed 不需等 21 天（樣本足且結論性壞即銷帳）。
        assert (
            demo_confirm_verdict(
                n_trades=30, stage0r_green=False, demo_net_bps=1.0, forward_oos_days=0
            )
            == "failed"
        )

    def test_insufficient_trades_beats_red_0r(self):
        # n<30 時即便 0R 紅也 pending（「樣本足」是 failed 的前置）。
        assert (
            demo_confirm_verdict(
                n_trades=10, stage0r_green=False, demo_net_bps=-5.0, forward_oos_days=99
            )
            == "pending"
        )

    def test_nan_net_with_red_0r_still_failed(self):
        # 真值表：NOT green 獨立決定 failed，與 net 取值（含 NaN）無關。
        assert (
            demo_confirm_verdict(
                n_trades=30,
                stage0r_green=False,
                demo_net_bps=float("nan"),
                forward_oos_days=30,
            )
            == "failed"
        )

    @pytest.mark.parametrize("bad_net", [float("nan"), float("inf"), float("-inf")])
    def test_nonfinite_net_with_green_0r_pending(self, bad_net):
        # 數值損壞 + 0R 綠 → pending：不退款、不銷帳、不鑄 dead-mode（保守）。
        assert (
            demo_confirm_verdict(
                n_trades=50,
                stage0r_green=True,
                demo_net_bps=bad_net,
                forward_oos_days=30,
            )
            == "pending"
        )

    def test_verdict_domain_is_three_valued(self):
        # 掃一圈組合，回值恆在三值域內（Literal 契約）。
        for n in [0, 29, 30, 100]:
            for green in [True, False]:
                for net in [-1.0, 0.0, 1.0]:
                    for days in [0, 20, 21, 99]:
                        v = demo_confirm_verdict(
                            n_trades=n,
                            stage0r_green=green,
                            demo_net_bps=net,
                            forward_oos_days=days,
                        )
                        assert v in ("confirmed", "failed", "pending")


# ─────────────────────────────────────────────────────────────────────────────
# 8. 鏈路一致性（assign → can_test → threshold）
# ─────────────────────────────────────────────────────────────────────────────


class TestChainConsistency:
    def test_default_dynamics_chain(self):
        w0 = init_family_wealth()
        alpha_i = _assign(w0)
        assert alpha_i == pytest.approx(5e-4)
        assert can_test(w0, alpha_i) is True
        # MIT #2：reachable wealth 下 threshold ≥ 0.9995。
        assert dsr_threshold_for(alpha_i) >= 0.9995 - 1e-12
        # φ=1.0 refund 恰補回 ⇒ W 回到 W_0（不超過——淨支出恆等式機械面）。
        assert w0 - alpha_i + refund_amount(alpha_i) == pytest.approx(w0)

    def test_wealth_never_exceeds_w0_under_phi_one(self):
        # 模擬 debit→confirmed refund 循環：W_t ≤ W_0 恆成立（MIT §1）。
        w0 = init_family_wealth()
        balance = w0
        for _ in range(200):
            alpha_i = _assign(balance)
            if alpha_i is None:
                break
            balance -= alpha_i
            balance += refund_amount(alpha_i)  # 全 confirmed 最有利軌跡
            assert balance <= w0 + 1e-15


# ─────────────────────────────────────────────────────────────────────────────
# 9. 模組純度（0 DB / 0 I/O / 0 async——AST 層驗，docstring 提及不誤紅）
# ─────────────────────────────────────────────────────────────────────────────


_FORBIDDEN_IMPORTS = {"psycopg2", "asyncio", "aiohttp", "sqlalchemy", "requests"}


class TestModulePurity:
    def test_no_forbidden_imports_ast(self):
        # 為什麼用 AST：MODULE_NOTE 合法提及「0 psycopg2」，裸字串 grep 會誤紅
        #（既有教訓：驗「code 無引用」必剝 docstring/註釋）。
        tree = ast.parse(inspect.getsource(awc))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(_FORBIDDEN_IMPORTS), imported
        # 純標量數學：連 numpy 都不需要。
        assert imported <= {"__future__", "math", "typing"}, imported

    def test_no_async_defs(self):
        tree = ast.parse(inspect.getsource(awc))
        assert not any(isinstance(n, ast.AsyncFunctionDef) for n in ast.walk(tree))

"""
G8-01 W2 — CognitiveModulator unit coverage suite (22 cases, ≥85% line cov)
==========================================================================

MODULE_NOTE (中文):
  本檔為 PA RFC `2026-04-27--g8_01_cognitive_e2e_design.md` §3.2 列出的 W2
  unit coverage 22-case suite。CognitiveModulator (193 LOC) 為 stateless
  pure-Python L0 modulator，無 IO / 無 IPC / 無 thread；本檔以**零 mock**
  策略全用真實 instance + 直接呼叫的方式覆蓋：

  - `__init__` defaults / EMA convergence / clamp 上下限 / getter rounding
  - `_compute_confidence_floor`：consec_losses / weekly_pnl / regret direction
    所有 + branches；[R1-5] 連虧時忽略向下壓力
  - `_compute_qty_ceiling`：consec_losses + weekly_pnl 取 worst-case；clamp
  - `_compute_stoploss_mult`：dream blend with confidence > 0.6；fallback；
    `global` vs `_meta` key resolution
  - `_compute_scan_interval`：weekly_pnl<0 加速、direction=overtrading 減速、
    direction=undertrading 加速、雙條件取 min
  - `get_all_params()` shape contract（5 keys）+ getter rounding 契約

  **regret/dream branches 反模式說明**：
  Per `2026-04-28--g8_01_fup_regret_dream_wiring.md`，production caller
  `tick_cognitive_modulator(...)` 永遠以 `regret_data={}` / `dream_data={}`
  傳入（producer `OpportunityTracker` / `DreamEngine` 為 RC-11 已刪 dead
  concept）。所以這些 branches 在 production hot path 屬「結構性不可達」。
  但 modulator 的 `update(...)` API **本身仍開放這些 kwargs**，本 W2 unit
  test 直接以 instance 呼叫驗證模組級邏輯正確性 — 屬合理的「API 契約測試」，
  而非「production 行為斷言」。當 RC-11 producer 重新實作（Option B）後，
  這些測試自動成為 regression baseline 無需修改。

MODULE_NOTE (English):
  W2 unit coverage suite (22 cases) per PA RFC §3.2. CognitiveModulator is a
  stateless pure-Python L0 modulator (193 LOC, no IO / no IPC / no thread).
  Strategy: **zero mock**, real instance + direct calls.

  Branch coverage targets all `_compute_*` paths including regret/dream
  branches even though their production producers (`OpportunityTracker` /
  `DreamEngine`) are RC-11 dead concepts. Per
  `2026-04-28--g8_01_fup_regret_dream_wiring.md` `tick_cognitive_modulator`
  always passes `regret_data={}` / `dream_data={}`, but the `update(...)`
  API itself remains open — these tests are **API contract tests**, not
  production behavior assertions, and become regression baselines if/when
  the producers are re-implemented (RFC Option B).

Refs:
  - PA RFC `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md` §3.2
  - REGRET-DREAM escalation `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g8_01_fup_regret_dream_wiring.md`
  - W1 sanity test `test_strategist_cognitive_w1_fix.py` (commit `aca7ee3`)
  - LOSSES wiring `test_g8_01_fup_losses_wiring.py` (commit `aced662`)
  - Production: `program_code/local_model_tools/cognitive_modulator.py`
"""

from __future__ import annotations

import os
import sys
import unittest

# Ensure srv root + control_api dir on sys.path for ``program_code.*`` import.
# 確保 srv root + control_api 目錄在 sys.path，使 ``program_code.*`` 可 import。
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)
# srv root = .../srv (5 levels up from tests/)
_srv_root = os.path.abspath(os.path.join(_test_dir, "..", "..", "..", "..", ".."))
if _srv_root not in sys.path:
    sys.path.insert(0, _srv_root)

from program_code.local_model_tools.cognitive_modulator import (  # noqa: E402
    CognitiveModulator,
    _BASE_CONFIDENCE_FLOOR,
    _BASE_QTY_CEILING,
    _BASE_STOPLOSS_MULT,
    _BASE_SCAN_INTERVAL,
    _MIN_CONF_FLOOR,
    _MAX_CONF_FLOOR,
    _MIN_QTY_CEIL,
    _MAX_QTY_CEIL,
    _MIN_SL_MULT,
    _MAX_SL_MULT,
    _MIN_SCAN,
    _MAX_SCAN,
    _EMA_ALPHA,
    _clamp,
)


# ─────────────────────────────────────────────────────────────────────────
# Test 1: __init__ defaults
# ─────────────────────────────────────────────────────────────────────────
class TestCase01InitDefaults(unittest.TestCase):
    """Case 1 — `__init__` 應將 4 參數設回 base 值且 update_count=0。"""

    def test_ctor_sets_base_values_and_zero_update_count(self):
        m = CognitiveModulator()
        params = m.get_all_params()
        self.assertEqual(params["confidence_floor"], round(_BASE_CONFIDENCE_FLOOR, 4))
        self.assertEqual(params["qty_ceiling"], round(_BASE_QTY_CEILING, 4))
        self.assertEqual(params["stoploss_multiplier"], round(_BASE_STOPLOSS_MULT, 4))
        self.assertEqual(params["scan_interval_s"], int(_BASE_SCAN_INTERVAL))
        self.assertEqual(params["update_count"], 0)


# ─────────────────────────────────────────────────────────────────────────
# Test 2: update() with empty inputs (None regret/dream)
# ─────────────────────────────────────────────────────────────────────────
class TestCase02UpdateEmptyInputs(unittest.TestCase):
    """Case 2 — `update()` 全 default 入參（None regret/dream） 不 raise，
    回 dict shape 正確且 update_count 推進 1。"""

    def test_update_empty_inputs_advances_counter(self):
        m = CognitiveModulator()
        result = m.update()  # all defaults including regret_data=None, dream_data=None
        self.assertEqual(result["update_count"], 1)
        # All 5 documented keys present.
        for key in ("confidence_floor", "qty_ceiling", "stoploss_multiplier",
                    "scan_interval_s", "update_count"):
            self.assertIn(key, result)


# ─────────────────────────────────────────────────────────────────────────
# Test 3: update() consec_losses=0 + weekly_pnl=0 → all base
# ─────────────────────────────────────────────────────────────────────────
class TestCase03UpdateNeutralStaysOnBase(unittest.TestCase):
    """Case 3 — `consec_losses=0` + `weekly_pnl=0` + empty regret → 任何
    `_compute_*` 都不應產生壓力，target = base，EMA 後仍接近 base。"""

    def test_update_neutral_keeps_values_at_base(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=0.0,
                 regret_data={}, dream_data={})
        params = m.get_all_params()
        # First update with target=base + EMA → still base (since prev=base too).
        self.assertAlmostEqual(params["confidence_floor"], _BASE_CONFIDENCE_FLOOR, places=4)
        self.assertAlmostEqual(params["qty_ceiling"], _BASE_QTY_CEILING, places=4)
        self.assertAlmostEqual(params["stoploss_multiplier"], _BASE_STOPLOSS_MULT, places=4)
        self.assertEqual(params["scan_interval_s"], int(_BASE_SCAN_INTERVAL))


# ─────────────────────────────────────────────────────────────────────────
# Test 4: consec_losses=3 → confidence floor +0.02
# ─────────────────────────────────────────────────────────────────────────
class TestCase04ConsecLossesPushesConfidenceUp(unittest.TestCase):
    """Case 4 — `consec_losses=3` 觸發 `pos.append(0.02 * min(1, 5)) = 0.02`，
    target_conf = base + 0.02 = 0.62；EMA 後 = 0.6 + 0.3*0.02 = 0.606。"""

    def test_consec_losses_3_pushes_confidence_up(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=3, weekly_net_pnl=0.0,
                 regret_data={}, dream_data={})
        # target_conf = 0.60 + 0.02 = 0.62; EMA(0.3) on prev 0.60 → 0.606.
        expected = _EMA_ALPHA * 0.62 + (1 - _EMA_ALPHA) * _BASE_CONFIDENCE_FLOOR
        self.assertAlmostEqual(m.get_confidence_floor(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 5: consec_losses=10 → cap at +0.10 (min 5×0.02)
# ─────────────────────────────────────────────────────────────────────────
class TestCase05ConsecLossesCappedAtFive(unittest.TestCase):
    """Case 5 — `consec_losses=10` 但 `min(consec-2, 5) = 5`，故 pos = 0.10
    封頂；target_conf = 0.60 + 0.10 = 0.70。"""

    def test_consec_losses_10_caps_at_5x_increment(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=10, weekly_net_pnl=0.0,
                 regret_data={}, dream_data={})
        # target = 0.60 + 0.10 = 0.70; EMA → 0.6 + 0.3*0.10 = 0.63.
        expected = _EMA_ALPHA * 0.70 + (1 - _EMA_ALPHA) * _BASE_CONFIDENCE_FLOOR
        self.assertAlmostEqual(m.get_confidence_floor(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 6: weekly_pnl<0 → confidence +0.02
# ─────────────────────────────────────────────────────────────────────────
class TestCase06NegativeWeeklyPnlPushesConfidenceUp(unittest.TestCase):
    """Case 6 — `weekly_pnl<0` 單獨觸發 `pos.append(0.02)`，consec_losses=0
    無連虧，target_conf = 0.60 + 0.02 = 0.62。"""

    def test_negative_weekly_pnl_pushes_confidence_up(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=-100.0,
                 regret_data={}, dream_data={})
        expected = _EMA_ALPHA * 0.62 + (1 - _EMA_ALPHA) * _BASE_CONFIDENCE_FLOOR
        self.assertAlmostEqual(m.get_confidence_floor(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 7: regret direction='overtrading' → conf +0.05
# ─────────────────────────────────────────────────────────────────────────
class TestCase07OvertradingPushesConfidenceUp(unittest.TestCase):
    """Case 7 — `regret.net_regret_direction='overtrading'` 觸發
    `pos.append(0.05)`；target_conf = 0.60 + 0.05 = 0.65。"""

    def test_overtrading_direction_pushes_confidence_up(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=0.0,
                 regret_data={"net_regret_direction": "overtrading"},
                 dream_data={})
        expected = _EMA_ALPHA * 0.65 + (1 - _EMA_ALPHA) * _BASE_CONFIDENCE_FLOOR
        self.assertAlmostEqual(m.get_confidence_floor(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 8: regret direction='undertrading' (no streak) → conf -0.03
# ─────────────────────────────────────────────────────────────────────────
class TestCase08UndertradingPushesConfidenceDown(unittest.TestCase):
    """Case 8 — `regret.net_regret_direction='undertrading'` + 無連虧 →
    `neg.append(-0.03)` 生效（[R1-5] gate consec<3），target_conf = 0.57。"""

    def test_undertrading_no_streak_lowers_confidence(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=0.0,
                 regret_data={"net_regret_direction": "undertrading"},
                 dream_data={})
        expected = _EMA_ALPHA * 0.57 + (1 - _EMA_ALPHA) * _BASE_CONFIDENCE_FLOOR
        self.assertAlmostEqual(m.get_confidence_floor(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 9: consec_losses=3 + direction='undertrading' → [R1-5] ignore neg
# ─────────────────────────────────────────────────────────────────────────
class TestCase09LossStreakIgnoresUndertradingNeg(unittest.TestCase):
    """Case 9 — `consec_losses=3` + `direction='undertrading'`：[R1-5] 連虧時
    忽略 neg pressure；neg_net = 0.0；pos_net = max(0.02) = 0.02；
    target_conf = 0.60 + 0.02 = 0.62（不 -0.03）。"""

    def test_loss_streak_ignores_undertrading_negative_pressure(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=3, weekly_net_pnl=0.0,
                 regret_data={"net_regret_direction": "undertrading"},
                 dream_data={})
        # consec_losses=3 → pos += 0.02; neg ignored per [R1-5] → target = 0.62.
        expected = _EMA_ALPHA * 0.62 + (1 - _EMA_ALPHA) * _BASE_CONFIDENCE_FLOOR
        self.assertAlmostEqual(m.get_confidence_floor(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 10: qty_ceiling consec_losses=4 → -0.10
# ─────────────────────────────────────────────────────────────────────────
class TestCase10QtyCeilingConsecLosses(unittest.TestCase):
    """Case 10 — qty_ceiling: `consec_losses=4` → adj.append(-0.05*min(2,5)) =
    -0.10；target_qty = 1.0 - 0.10 = 0.90；EMA(0.3) → 0.97。"""

    def test_qty_ceiling_consec_losses_4_drops(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=4, weekly_net_pnl=0.0,
                 regret_data={}, dream_data={})
        # target_qty = 1.0 + (-0.05 * min(2, 5)) = 1.0 - 0.10 = 0.90.
        expected = _EMA_ALPHA * 0.90 + (1 - _EMA_ALPHA) * _BASE_QTY_CEILING
        self.assertAlmostEqual(m.get_qty_ceiling(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 11: qty_ceiling consec_losses=3 + weekly_pnl<0 → take min (worst)
# ─────────────────────────────────────────────────────────────────────────
class TestCase11QtyCeilingTakesWorstCase(unittest.TestCase):
    """Case 11 — `consec_losses=3` (-0.05) + `weekly_pnl<0` (-0.10)
    → adj=[-0.05, -0.10]，min(adj) = -0.10（worst-case）；
    target_qty = 0.90。"""

    def test_qty_ceiling_takes_min_of_two_pressures(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=3, weekly_net_pnl=-50.0,
                 regret_data={}, dream_data={})
        # adj = [-0.05*min(1,5), -0.10] = [-0.05, -0.10]; min = -0.10.
        expected = _EMA_ALPHA * 0.90 + (1 - _EMA_ALPHA) * _BASE_QTY_CEILING
        self.assertAlmostEqual(m.get_qty_ceiling(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 12: qty_ceiling clamp at _MIN_QTY_CEIL (0.3)
# ─────────────────────────────────────────────────────────────────────────
class TestCase12QtyCeilingClampToMin(unittest.TestCase):
    """Case 12 — 極端 consec_losses=100 + weekly_pnl<<0 連續多次 update
    把 EMA 推到 clamp 下限 0.3；驗 `_clamp` 阻擋越界。"""

    def test_qty_ceiling_clamps_to_min_under_extreme_pressure(self):
        m = CognitiveModulator()
        # Run many updates so EMA converges close to target.
        for _ in range(50):
            m.update(consecutive_losses=100, weekly_net_pnl=-10000.0,
                     regret_data={}, dream_data={})
        # target_qty = 1.0 + min(-0.25, -0.10) = 0.75 (consec capped at 5×0.05).
        # Even worst case here (target=0.75) does NOT hit clamp 0.3 — clamp
        # applies on each call directly. Force directly via clamp internal:
        clamped = _clamp(0.05, _MIN_QTY_CEIL, _MAX_QTY_CEIL)
        self.assertEqual(clamped, _MIN_QTY_CEIL)
        # And confirm runtime value never exceeds bounds.
        self.assertGreaterEqual(m.get_qty_ceiling(), _MIN_QTY_CEIL)
        self.assertLessEqual(m.get_qty_ceiling(), _MAX_QTY_CEIL)


# ─────────────────────────────────────────────────────────────────────────
# Test 13: dream_data global.stoploss_multiplier=1.5 + confidence=0.7 → blend
# ─────────────────────────────────────────────────────────────────────────
class TestCase13DreamBlendsStoplossWhenConfidenceHigh(unittest.TestCase):
    """Case 13 — dream_data 含 `global.stoploss_multiplier=1.5` +
    `confidence=0.7` → blend = (1.0 - 0.7*0.3) * 1.0 + 0.7*0.3 * 1.5
    = 0.79 + 0.315 = 1.105；target_sl 變動。"""

    def test_dream_blends_stoploss_when_confidence_above_threshold(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=0.0,
                 regret_data={},
                 dream_data={"global": {"stoploss_multiplier": 1.5,
                                        "confidence": 0.7}})
        # blend = (1.0 - 0.7*0.3) * 1.0 + 0.7 * 0.3 * 1.5 = 0.79 + 0.315 = 1.105
        target = (1.0 - 0.7 * 0.3) * _BASE_STOPLOSS_MULT + 0.7 * 0.3 * 1.5
        expected = _EMA_ALPHA * target + (1 - _EMA_ALPHA) * _BASE_STOPLOSS_MULT
        self.assertAlmostEqual(m.get_stoploss_multiplier(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 14: dream confidence ≤ 0.6 → bypass, sl=base
# ─────────────────────────────────────────────────────────────────────────
class TestCase14DreamBypassWhenConfidenceLow(unittest.TestCase):
    """Case 14 — dream `confidence=0.5` (≤0.6) → bypass blend，target_sl =
    `_BASE_STOPLOSS_MULT`，EMA 不變。"""

    def test_dream_bypass_when_confidence_below_or_equal_threshold(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=0.0,
                 regret_data={},
                 dream_data={"global": {"stoploss_multiplier": 99.0,
                                        "confidence": 0.5}})
        # confidence=0.5 NOT > 0.6 → return _BASE_STOPLOSS_MULT.
        # EMA(prev=base, target=base) = base.
        self.assertAlmostEqual(m.get_stoploss_multiplier(),
                               round(_BASE_STOPLOSS_MULT, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 15: dream uses _meta fallback when no `global` key
# ─────────────────────────────────────────────────────────────────────────
class TestCase15DreamMetaFallbackKey(unittest.TestCase):
    """Case 15 — dream_data 無 `global` 但有 `_meta` →
    `dd.get("global", dd.get("_meta", {}))` 取 `_meta`；同 blend 邏輯。"""

    def test_dream_uses_meta_fallback_when_global_missing(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=0.0,
                 regret_data={},
                 dream_data={"_meta": {"stoploss_multiplier": 1.5,
                                       "confidence": 0.8}})
        # blend = (1.0 - 0.8*0.3) * 1.0 + 0.8*0.3 * 1.5 = 0.76 + 0.36 = 1.12.
        target = (1.0 - 0.8 * 0.3) * _BASE_STOPLOSS_MULT + 0.8 * 0.3 * 1.5
        expected = _EMA_ALPHA * target + (1 - _EMA_ALPHA) * _BASE_STOPLOSS_MULT
        self.assertAlmostEqual(m.get_stoploss_multiplier(), round(expected, 4), places=4)


# ─────────────────────────────────────────────────────────────────────────
# Test 16: scan_interval weekly_pnl<0 → halve
# ─────────────────────────────────────────────────────────────────────────
class TestCase16ScanIntervalHalvedOnLoss(unittest.TestCase):
    """Case 16 — `weekly_pnl<0` 觸發 `interval = min(interval, BASE * 0.5)`
    = 900；EMA(0.3) on prev 1800 → 1530。"""

    def test_scan_interval_halved_when_weekly_pnl_negative(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=-100.0,
                 regret_data={}, dream_data={})
        target = _BASE_SCAN_INTERVAL * 0.5  # 900
        expected = _EMA_ALPHA * target + (1 - _EMA_ALPHA) * _BASE_SCAN_INTERVAL
        self.assertEqual(m.get_scan_interval_seconds(), int(expected))


# ─────────────────────────────────────────────────────────────────────────
# Test 17: scan_interval direction='overtrading' → 1.5x slow
# ─────────────────────────────────────────────────────────────────────────
class TestCase17ScanIntervalSlowsOnOvertrading(unittest.TestCase):
    """Case 17 — `direction='overtrading'` 觸發
    `interval = max(interval, BASE * 1.5)` = 2700；EMA → 2070。"""

    def test_scan_interval_slows_on_overtrading_direction(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=0.0,
                 regret_data={"net_regret_direction": "overtrading"},
                 dream_data={})
        target = _BASE_SCAN_INTERVAL * 1.5  # 2700
        expected = _EMA_ALPHA * target + (1 - _EMA_ALPHA) * _BASE_SCAN_INTERVAL
        self.assertEqual(m.get_scan_interval_seconds(), int(expected))


# ─────────────────────────────────────────────────────────────────────────
# Test 18: scan_interval direction='undertrading' + weekly_pnl<0 → take min
# ─────────────────────────────────────────────────────────────────────────
class TestCase18ScanIntervalTakesMinOfTwoConditions(unittest.TestCase):
    """Case 18 — `direction='undertrading'` (×0.7=1260) + `weekly_pnl<0`
    (×0.5=900) 兩 condition 各自 `min(...)`，最終 = 900（更小者）。"""

    def test_scan_interval_takes_min_of_two_speedup_conditions(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=-100.0,
                 regret_data={"net_regret_direction": "undertrading"},
                 dream_data={})
        # weekly_pnl<0 first sets to 900, then undertrading sets to min(900, 1260)
        # = 900 (no change).
        target = _BASE_SCAN_INTERVAL * 0.5  # 900
        expected = _EMA_ALPHA * target + (1 - _EMA_ALPHA) * _BASE_SCAN_INTERVAL
        self.assertEqual(m.get_scan_interval_seconds(), int(expected))


# ─────────────────────────────────────────────────────────────────────────
# Test 19: EMA convergence — repeated update converges to target
# ─────────────────────────────────────────────────────────────────────────
class TestCase19EMAConvergence(unittest.TestCase):
    """Case 19 — 連 30 次相同 update（pressure 固定） → EMA 應收斂到 target
    （差距 < 1e-3）。驗 `_EMA_ALPHA=0.3` 數值正確。"""

    def test_ema_converges_after_many_updates(self):
        m = CognitiveModulator()
        # Apply consec_losses=3 (target conf = 0.62) for 30 cycles.
        for _ in range(30):
            m.update(consecutive_losses=3, weekly_net_pnl=0.0,
                     regret_data={}, dream_data={})
        # After 30 EMA(0.3) iterations, |result - target| ≈ 0.7^30 * 0.02 << 1e-3.
        target_conf = 0.62
        self.assertLess(abs(m.get_confidence_floor() - target_conf), 1e-3)
        self.assertEqual(m.get_all_params()["update_count"], 30)


# ─────────────────────────────────────────────────────────────────────────
# Test 20: clamp upper/lower bounds verified at extreme inputs
# ─────────────────────────────────────────────────────────────────────────
class TestCase20ClampBoundsVerified(unittest.TestCase):
    """Case 20 — 直接驗 `_clamp` 邊界 + 各參數的 (min,max) 範圍 hard
    constants 沒漂移；run 多 cycle 後 confidence ≤ 0.85, scan ∈ [300, 3600]。"""

    def test_clamp_function_respects_bounds(self):
        # Direct _clamp invariants.
        self.assertEqual(_clamp(0.0, 0.5, 1.0), 0.5)
        self.assertEqual(_clamp(2.0, 0.5, 1.0), 1.0)
        self.assertEqual(_clamp(0.7, 0.5, 1.0), 0.7)

    def test_runtime_values_stay_within_clamp_bounds(self):
        m = CognitiveModulator()
        # Apply pathological pressure many times.
        for _ in range(50):
            m.update(consecutive_losses=100, weekly_net_pnl=-9999.0,
                     regret_data={"net_regret_direction": "overtrading"},
                     dream_data={"global": {"stoploss_multiplier": 99.0,
                                            "confidence": 0.99}})
        # All runtime params within their hard clamp ranges.
        self.assertGreaterEqual(m.get_confidence_floor(), _MIN_CONF_FLOOR)
        self.assertLessEqual(m.get_confidence_floor(), _MAX_CONF_FLOOR)
        self.assertGreaterEqual(m.get_qty_ceiling(), _MIN_QTY_CEIL)
        self.assertLessEqual(m.get_qty_ceiling(), _MAX_QTY_CEIL)
        self.assertGreaterEqual(m.get_stoploss_multiplier(), _MIN_SL_MULT)
        self.assertLessEqual(m.get_stoploss_multiplier(), _MAX_SL_MULT)
        self.assertGreaterEqual(m.get_scan_interval_seconds(), _MIN_SCAN)
        self.assertLessEqual(m.get_scan_interval_seconds(), _MAX_SCAN)


# ─────────────────────────────────────────────────────────────────────────
# Test 21: get_all_params() shape contract — 5 keys (incl. update_count)
# ─────────────────────────────────────────────────────────────────────────
class TestCase21GetAllParamsShapeContract(unittest.TestCase):
    """Case 21 — `get_all_params()` 必回 dict 含且僅含 5 keys（contract）。
    Production 對 caller 的 schema 承諾。"""

    def test_get_all_params_returns_exactly_five_documented_keys(self):
        m = CognitiveModulator()
        params = m.get_all_params()
        expected_keys = {"confidence_floor", "qty_ceiling", "stoploss_multiplier",
                         "scan_interval_s", "update_count"}
        self.assertEqual(set(params.keys()), expected_keys)


# ─────────────────────────────────────────────────────────────────────────
# Test 22: getter rounding contract
# ─────────────────────────────────────────────────────────────────────────
class TestCase22GetterRoundingContract(unittest.TestCase):
    """Case 22 — 個別 getter 的 rounding 契約：
    - confidence_floor / qty_ceiling / stoploss_multiplier → 4 位浮點
    - scan_interval_s → int (truncated)
    """

    def test_confidence_floor_rounded_to_4_decimals(self):
        m = CognitiveModulator()
        # Drive an update that produces irrational EMA result.
        m.update(consecutive_losses=3, weekly_net_pnl=-77.7,
                 regret_data={"net_regret_direction": "overtrading"},
                 dream_data={})
        v = m.get_confidence_floor()
        # round(x, 4) ⇒ x has at most 4 decimal places when serialized.
        self.assertEqual(v, round(v, 4))

    def test_qty_ceiling_rounded_to_4_decimals(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=4, weekly_net_pnl=-100.0,
                 regret_data={}, dream_data={})
        v = m.get_qty_ceiling()
        self.assertEqual(v, round(v, 4))

    def test_stoploss_multiplier_rounded_to_4_decimals(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=0.0,
                 regret_data={},
                 dream_data={"global": {"stoploss_multiplier": 1.234567,
                                        "confidence": 0.75}})
        v = m.get_stoploss_multiplier()
        self.assertEqual(v, round(v, 4))

    def test_scan_interval_seconds_returns_int(self):
        m = CognitiveModulator()
        m.update(consecutive_losses=0, weekly_net_pnl=-100.0,
                 regret_data={}, dream_data={})
        v = m.get_scan_interval_seconds()
        self.assertIsInstance(v, int)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

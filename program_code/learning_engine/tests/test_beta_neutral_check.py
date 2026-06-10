"""beta_neutral_check（B1）聚焦測試 — 驗 QC four numbers + masquerade kill（意圖非僅行為）。

覆蓋（對映 PA P3b §A + QC B1 spec §1）：
  - QC #1 雙因子強制：altcap=None → DEFER（never BTC-only 偽中性）。
  - QC #2 90d window：對齊 bar < 90 → DEFER。
  - QC #3 |β| ≥ 0.15 → fail（三 β 皆）。
  - QC #3c down-leg：<30 down-bars → DEFER；span<180d → DEFER。
  - QC #4 β_upper = |β| + 1.96·SE ≥ 0.20 → fail（殺「小但噪音大」偽中性）。
  - strictest-wins：fail dominate DEFER。
  - down-mask leak-free prior-only（前 30 bar False；絕對 scalar 非 percentile）。
  - DW < 1.5 → HAC escalation（used_hac=True）。
  - SE 計算正確（殺 noisy-small-β）。

Mac-tested（純數學，無 DB/model）。Linux E4 regression + QC sign-off owed。
"""

from __future__ import annotations

import datetime
import random

import pytest

from program_code.learning_engine.beta_neutral_check import (
    BETA_NEUTRAL_THRESHOLD,
    BETA_UPPER_CAP,
    DOWN_BARS_MIN,
    beta_neutral_check,
    compute_down_market_mask,
)


def _series(fn, n=200, seed=0):
    random.seed(seed)
    return {i: fn(i, random) for i in range(n)}


def _full_span_down_mask(btc: dict, threshold=-0.01) -> dict:
    """用自然 down bars（btc < threshold）做 mask，跨全 span（≥180d span + ≥30 bars）。"""
    return {i: (btc[i] < threshold) for i in btc}


# ═══════════════════════════════════════════════════════════════════════════════
# QC #1 — 雙因子強制（altcap=None → DEFER）
# ═══════════════════════════════════════════════════════════════════════════════


def test_qc1_altcap_none_defers_never_btc_only_neutral():
    """altcap 缺（producer absent）→ DEFER，reason altcap_missing_btc_only_defer。

    為什麼：BTC-only 模型會 by-construction 通過 masquerade（3/5 dead candidate 是 alt-down-beta）。
    """
    btc = _series(lambda i, r: r.gauss(0, 0.02), seed=1)
    cand = _series(lambda i, r: r.gauss(0.0005, 0.01), seed=2)
    res = beta_neutral_check(cand, btc, None, None, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert "altcap_missing_btc_only_defer" in res.reasons
    # 不偽造 β（BTC-only 不該回中性數值）。
    assert res.beta_btc is None and res.beta_alt is None


# ═══════════════════════════════════════════════════════════════════════════════
# QC #2 — 90d window（對齊 bar < 90 → DEFER）
# ═══════════════════════════════════════════════════════════════════════════════


def test_qc2_window_below_90d_defers():
    """對齊 bar < 90 → DEFER（資料窗不足，β 不可信）。"""
    btc = _series(lambda i, r: r.gauss(0, 0.02), n=60, seed=1)
    alt = _series(lambda i, r: r.gauss(0, 0.02), n=60, seed=3)
    cand = _series(lambda i, r: r.gauss(0.0005, 0.01), n=60, seed=2)
    res = beta_neutral_check(cand, btc, alt, None, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert "window_below_90d" in res.reasons


def test_qc2_unsupported_bar_1m_defers():
    """bar=1m 不接（attenuation）→ DEFER reason unsupported_bar。"""
    btc = _series(lambda i, r: r.gauss(0, 0.02), seed=1)
    alt = _series(lambda i, r: r.gauss(0, 0.02), seed=3)
    cand = _series(lambda i, r: r.gauss(0.0005, 0.01), seed=2)
    res = beta_neutral_check(cand, btc, alt, None, bar="1m", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert any("unsupported_bar" in r for r in res.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# QC #3 — |β| ≥ 0.15 → fail（masquerade kill）
# ═══════════════════════════════════════════════════════════════════════════════


def test_qc3_down_beta_masquerade_fails():
    """down-beta 候選（β_down 高）→ fail（masquerade kill；殺 5 個 dead candidate 的維度）。"""
    random.seed(2)
    N = 200
    btc = {i: random.gauss(-0.001, 0.025) for i in range(N)}
    alt = {i: btc[i] * 0.6 + random.gauss(0, 0.02) for i in range(N)}
    down_idx = set(i for i in range(N) if btc[i] < -0.01)
    # 候選在 down bar 強載 btc → down-beta masquerade。
    cand = {i: (0.8 * btc[i] if i in down_idx else 0.0005) for i in range(N)}
    mask = {i: (i in down_idx) for i in range(N)}
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "fail"
    assert "beta_down_above_threshold" in res.reasons or "beta_btc_above_threshold" in res.reasons
    assert res.beta_down is not None and abs(res.beta_down) >= BETA_NEUTRAL_THRESHOLD


def test_qc3_high_btc_beta_fails():
    """β_btc ≥ 0.15 → fail（pooled 因子載荷過高）。"""
    random.seed(5)
    N = 200
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    cand = {i: 0.5 * btc[i] + random.gauss(0, 0.002) for i in range(N)}  # 強 btc 載荷
    mask = _full_span_down_mask(btc)
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "fail"
    assert "beta_btc_above_threshold" in res.reasons


# ═══════════════════════════════════════════════════════════════════════════════
# QC #4 — β_upper = |β| + 1.96·SE ≥ 0.20 → fail（殺 noisy-small-β）
# ═══════════════════════════════════════════════════════════════════════════════


def test_qc4_noisy_small_beta_fails_on_upper_cap():
    """點估 |β| < 0.15 但 β_upper（|β|+1.96·SE）≥ 0.20 → fail（SE 殺「小但噪音大」偽中性）。

    為什麼這條最關鍵：沒有 SE，noisy down-beta 候選會以點估通過——正是 5-candidate 失敗模式。
    """
    random.seed(11)
    N = 120
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    # 構造：點估 β_btc ~0.10（< 0.15），但加大噪音使 SE 大 → β_upper ≥ 0.20。
    cand = {i: 0.10 * btc[i] + random.gauss(0, 0.05) for i in range(N)}
    mask = _full_span_down_mask(btc)
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    # 點估可能 < 0.15，但 β_upper ≥ 0.20 → fail。
    assert res.verdict == "fail"
    assert any("upper_above_cap" in r for r in res.reasons)
    # 驗 SE 確實算了（非 None）。
    assert res.se["btc"] is not None and res.se["btc"] > 0


def test_qc4_clean_neutral_candidate_passes():
    """真中性候選（低 β + 低 SE + 充分 down-bars）→ pass。"""
    random.seed(7)
    N = 250
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    # 候選與 btc/alt 幾乎正交，低噪音 → β≈0、SE 小。
    cand = {i: 0.0003 + random.gauss(0, 0.003) for i in range(N)}
    # down mask：自然 down bars 跨全 span（≥180d + ≥30 bars）。
    mask = _full_span_down_mask(btc)
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "pass", f"reasons={res.reasons} beta_btc={res.beta_btc} upper={res.beta_upper}"
    assert abs(res.beta_btc) < BETA_NEUTRAL_THRESHOLD
    assert all(u < BETA_UPPER_CAP for u in res.beta_upper.values() if u is not None)


# ═══════════════════════════════════════════════════════════════════════════════
# QC #3c — down-leg（<30 down-bars / span<180d → DEFER）
# ═══════════════════════════════════════════════════════════════════════════════


def test_qc3c_down_bars_below_30_defers():
    """down-bars < 30 → DEFER（β_down 不可信；runtime last-90d=23<30）。"""
    random.seed(7)
    N = 250
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    cand = {i: 0.0003 + random.gauss(0, 0.003) for i in range(N)}
    # 只標 20 個 down bar（< 30），跨全 span。
    down_subset = set(range(0, 200, 10))  # 20 bars
    mask = {i: (i in down_subset) for i in range(N)}
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert "down_bars_below_30_defer" in res.reasons


def test_qc3c_down_span_below_180d_defers():
    """down-bars ≥30 但抽樣窗 span < 180d（過度集中短期）→ DEFER（QC #3c-window span 要求）。"""
    random.seed(7)
    N = 250
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    cand = {i: 0.0003 + random.gauss(0, 0.003) for i in range(N)}
    # 35 個 down bar 全擠在 [0, 50)（span < 180）。
    mask = {i: (i < 35) for i in range(N)}
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert "down_subsample_span_below_180d_defer" in res.reasons


def test_qc3c_down_mask_missing_defers():
    """down_market_mask=None → DEFER（β_down 無法估，保守）。"""
    random.seed(7)
    N = 250
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    cand = {i: 0.0003 + random.gauss(0, 0.003) for i in range(N)}
    res = beta_neutral_check(cand, btc, alt, None, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert "down_mask_missing_defer" in res.reasons


# ═══════════════════════════════════════════════════════════════════════════════
# strictest-wins（fail dominate DEFER）
# ═══════════════════════════════════════════════════════════════════════════════


def test_strictest_wins_fail_dominates_defer():
    """既 |β|≥0.15（fail）又 down-bars<30（DEFER）→ overall fail（strictest-wins）。"""
    random.seed(5)
    N = 200
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    cand = {i: 0.5 * btc[i] + random.gauss(0, 0.002) for i in range(N)}  # β_btc 高 → fail
    # 只 10 down bars（< 30 → 該臂 DEFER），但 pooled β fail 必 dominate。
    mask = {i: (i % 20 == 0) for i in range(N)}
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "fail"  # fail > DEFER


# ═══════════════════════════════════════════════════════════════════════════════
# Q1 — N_trades_oos < 50 → DEFER
# ═══════════════════════════════════════════════════════════════════════════════


def test_q1_trades_oos_below_50_defers():
    """n_trades_oos < 50 → DEFER reason data_below_min_trades_oos。"""
    random.seed(7)
    N = 250
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    cand = {i: 0.0003 + random.gauss(0, 0.003) for i in range(N)}
    mask = _full_span_down_mask(btc)
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=30)
    assert res.verdict == "DEFER"
    assert "data_below_min_trades_oos" in res.reasons


# ═══════════════════════════════════════════════════════════════════════════════
# down-mask leak-free prior-only（§A.4 / QC #3c / MIT §3.5）
# ═══════════════════════════════════════════════════════════════════════════════


def test_down_mask_leak_free_prior_only():
    """down-mask 前 30 bar False（prior 窗不足）；用絕對 scalar（8%/5%）非 percentile。"""
    # 構造一個明確的 drawdown：前 30 bar 漲，第 31 bar 起跌 > 8%。
    closes = {}
    for i in range(31):
        closes[i] = 100.0 + i  # 漲到 130
    closes[31] = 100.0  # 從 prior-30 peak(129) 跌 > 8% → down
    mask = compute_down_market_mask(closes)
    # 前 30 bar：prior 窗不足 → False。
    assert all(mask[i] is False for i in range(30))
    # bar 31：30d drawdown > 8%（100 < 129×0.92=118.7）→ True。
    assert mask[31] is True


def test_down_mask_7d_return_threshold():
    """7d return < -5% → down（即使無 30d drawdown）。"""
    closes = {i: 100.0 for i in range(20)}
    closes[19] = 100.0
    # bar 14：close_7_ago=100，當前 94 → 7d return -6% < -5% → down。
    closes[14] = 94.0
    mask = compute_down_market_mask(closes)
    assert mask[14] is True


# ═══════════════════════════════════════════════════════════════════════════════
# HAC escalation（DW < 1.5 → used_hac=True）
# ═══════════════════════════════════════════════════════════════════════════════


def test_hac_escalation_on_autocorrelated_residuals():
    """殘差正自相關（DW < 1.5）→ used_hac=True（Newey-West SE）。"""
    # 構造殘差有強正自相關：candidate = AR(1)-like 噪音（連續相關）。
    N = 200
    btc = {i: 0.0 for i in range(N)}  # btc 全 0 → 候選殘差 = 候選本身
    alt = {i: 0.0 for i in range(N)}
    # AR(1) 序列（高正自相關 → DW 遠小於 2）。
    vals = [0.0]
    random.seed(3)
    for i in range(1, N):
        vals.append(0.9 * vals[-1] + random.gauss(0, 0.01))
    cand = {i: vals[i] for i in range(N)}
    mask = {i: (i % 4 == 0) for i in range(N)}  # 50 down bars 跨全 span
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    # DW 應 < 1.5（強正自相關）→ used_hac=True。
    assert res.durbin_watson is not None and res.durbin_watson < 1.5
    assert res.used_hac is True


# ═══════════════════════════════════════════════════════════════════════════════
# int-bar-index 契約（fail-LOUD；E4 real-smoke 抓到的 silent-drop 缺陷修補）
#
# 根因：本閘的 series 解析重用 residual_alpha_gate._parse_candidate_returns，後者用 ±inf
# fit-window 邊界（float('-inf') <= ts <= float('inf')）；date/datetime/str key 與 float 比較
# raise TypeError 被 _contains 吞成 False → 該 row 被「靜默」丟棄 → 空 series → 偽 universal
# DEFER（reason 看起來像 window_below_90d，實際是 0 row）。修補後：入口顯式偵測 key 形態，
# 任一非 int(bar-index) key → 顯式 DEFER（reason temporal_keys_unsupported_need_int_bar_index），
# 非靜默。下列測試斷言「顯式 reason」（非空-series 靜默）——移除入口 loud-detect → 退回
# window_below_90d 靜默 DEFER → 這些測試紅（mutation bite）。
# ═══════════════════════════════════════════════════════════════════════════════

_TEMPORAL_KEY_REASON = "temporal_keys_unsupported_need_int_bar_index"


def _date_series(fn, n=200, seed=0):
    """date-key series（模擬 market.klines 真實 date-key 形態）。"""
    random.seed(seed)
    base = datetime.date(2025, 1, 1)
    return {base + datetime.timedelta(days=i): fn(i, random) for i in range(n)}


def test_contract_date_key_explicit_defer_not_silent_empty():
    """date-key 輸入（真 market.klines 形態）→ 顯式 DEFER reason，非靜默空-series。

    為什麼這條是本 fix 的核心：unit test 全用 int key 故先前綠，但真 date-key 資料會被
    ±inf fit-window 靜默丟光 → 偽 universal DEFER（window_below_90d）。斷言顯式 reason +
    n_bars 未洩漏假窗不足訊號。移除入口 loud-detect → 退回 window_below_90d → 本條紅。
    """
    base = datetime.date(2025, 1, 1)
    dates = [base + datetime.timedelta(days=i) for i in range(200)]
    random.seed(1)
    btc = {d: random.gauss(0, 0.02) for d in dates}
    alt = {d: random.gauss(0, 0.02) for d in dates}
    cand = {d: random.gauss(0.0005, 0.01) for d in dates}
    mask = {d: (btc[d] < -0.01) for d in dates}
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    # 顯式契約 reason 必在（fail-loud）；不可只回 window_below_90d（靜默誤導）。
    assert _TEMPORAL_KEY_REASON in res.reasons
    assert "window_below_90d" not in res.reasons


def test_contract_datetime_key_explicit_defer():
    """datetime-key（含時分）同樣觸發顯式 DEFER（非 int bar index）。"""
    base = datetime.datetime(2025, 1, 1, 0, 0)
    stamps = [base + datetime.timedelta(days=i) for i in range(200)]
    random.seed(2)
    btc = {s: random.gauss(0, 0.02) for s in stamps}
    alt = {s: random.gauss(0, 0.02) for s in stamps}
    cand = {s: random.gauss(0.0005, 0.01) for s in stamps}
    mask = {s: (btc[s] < -0.01) for s in stamps}
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert _TEMPORAL_KEY_REASON in res.reasons


def test_contract_str_key_explicit_defer():
    """str-key（ISO 日期字串）同樣觸發顯式 DEFER（非 int bar index）。"""
    keys = [f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(200)]
    random.seed(3)
    btc = {k: random.gauss(0, 0.02) for k in keys}
    alt = {k: random.gauss(0, 0.02) for k in keys}
    cand = {k: random.gauss(0.0005, 0.01) for k in keys}
    mask = {k: (btc[k] < -0.01) for k in keys}
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert _TEMPORAL_KEY_REASON in res.reasons


def test_contract_mixed_int_and_date_key_explicit_defer():
    """mixed key（部分 int 部分 date）→ 顯式 DEFER（型別不一致也會靜默丟對齊 row）。

    為什麼 mixed 也算違規：int∩date 對齊會因型別不可比再次靜默丟 row；契約要求「共享」int
    bar index，任一非 int key 即違約。
    """
    random.seed(4)
    btc = {i: random.gauss(0, 0.02) for i in range(150)}
    alt = {i: random.gauss(0, 0.02) for i in range(150)}
    cand = {i: random.gauss(0.0005, 0.01) for i in range(150)}
    # 在 candidate 混入一個 date key → 違反「共享 int bar index」契約。
    cand[datetime.date(2025, 6, 1)] = 0.001
    mask = {i: False for i in range(150)}
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert _TEMPORAL_KEY_REASON in res.reasons


def test_contract_date_key_sequence_rows_explicit_defer():
    """Sequence-of-(date, val) row 形態同樣偵測 key（非僅 Mapping）。"""
    base = datetime.date(2025, 1, 1)
    random.seed(5)
    cand = [(base + datetime.timedelta(days=i), random.gauss(0.0005, 0.01)) for i in range(200)]
    btc = [(base + datetime.timedelta(days=i), random.gauss(0, 0.02)) for i in range(200)]
    alt = [(base + datetime.timedelta(days=i), random.gauss(0, 0.02)) for i in range(200)]
    res = beta_neutral_check(cand, btc, alt, None, bar="daily", n_trades_oos=200)
    assert res.verdict == "DEFER"
    assert _TEMPORAL_KEY_REASON in res.reasons


def test_contract_date_key_emits_warning(caplog):
    """date-key 觸發 logger.warning（fail-LOUD 的「loud」部分——接線錯誤 log 即可診斷）。"""
    import logging

    btc = _date_series(lambda i, r: r.gauss(0, 0.02), seed=6)
    alt = _date_series(lambda i, r: r.gauss(0, 0.02), seed=7)
    cand = _date_series(lambda i, r: r.gauss(0.0005, 0.01), seed=8)
    with caplog.at_level(logging.WARNING):
        beta_neutral_check(cand, btc, alt, None, bar="daily", n_trades_oos=200)
    assert any("int bar index" in rec.message for rec in caplog.records)


def test_contract_int_key_unaffected_passes():
    """int bar-index key（既有契約）不受影響：真中性候選仍 pass，無契約 reason。

    為什麼留這條：證明 loud-detect 只攔非 int key，不誤傷既有 int-key caller（46 既有綠）。
    """
    random.seed(7)
    N = 250
    btc = {i: random.gauss(0, 0.02) for i in range(N)}
    alt = {i: random.gauss(0, 0.02) for i in range(N)}
    cand = {i: 0.0003 + random.gauss(0, 0.003) for i in range(N)}
    mask = {i: (btc[i] < -0.01) for i in range(N)}
    res = beta_neutral_check(cand, btc, alt, mask, bar="daily", n_trades_oos=200)
    assert res.verdict == "pass"
    assert _TEMPORAL_KEY_REASON not in res.reasons

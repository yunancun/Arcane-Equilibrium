"""bar_index_reindex 聚焦測試 — 驗 date→int re-index 契約 + 缺 bar span 保真 + B1 串測。

覆蓋（對映 PA owed-conductor-wiring 設計 §D + §E E1-A 測試清單）：
  - key 矩陣：date / datetime / ISO-str（含 Z/時區）/ int passthrough / mixed / duplicate。
  - fail-loud：混型（單 series 內 + 跨輸入）/ 重複日 / 不可解析 / bar=4h / 未知 index_rule
    → reasons + 全 None（非靜默）。
  - **缺 bar span 保真（本模組的存在理由）**：dense 0..N-1 會把 calendar span 壓成 N−1
    （_span_days 對 int key 用 max−min 當天數）；ordinal-offset 保真。含 B1 down-leg 實際
    bite：同一資料 dense → span DEFER 誤殺、ordinal → pass。
  - mask gap 記帳：交集內缺 date → False + mask_gap_filled_false:<n>。
  - 串測：reindex 輸出餵 beta_neutral_check → 不觸 temporal_keys_unsupported_need_int_bar_index；
    synthetic 已知-β（β=0.5 注入 → fail；β=0 → pass）。

純函數 0 DB / 0 IO（synthetic only）——無連線層可觸，天然滿足測試隔離鐵則。
Mac-tested；Linux E4 regression owed。
"""

from __future__ import annotations

import datetime as dt
import random

from program_code.learning_engine.bar_index_reindex import (
    INDEX_RULE_DENSE,
    INDEX_RULE_ORDINAL_OFFSET,
    reindex_to_int_bar_index,
)
from program_code.learning_engine.beta_neutral_check import (
    _span_days,
    beta_neutral_check,
)

_TEMPORAL_KEY_REASON = "temporal_keys_unsupported_need_int_bar_index"
_BASE = dt.date(2025, 1, 1)


def _dates(n: int, step_days: int = 1) -> list[dt.date]:
    """連續（或每 step_days 一根 bar 的稀疏）date 序列。"""
    return [_BASE + dt.timedelta(days=i * step_days) for i in range(n)]


def _date_series(dates, fn, seed=0):
    random.seed(seed)
    return {d: fn(i, random) for i, d in enumerate(dates)}


def _assert_all_none(res):
    """fail-loud 指紋：四輸出全 None + n_bars=0 + index_map 空。"""
    assert res.candidate is None and res.btc is None
    assert res.altcap is None and res.mask is None
    assert res.n_bars == 0
    assert res.index_map == {}


# ═══════════════════════════════════════════════════════════════════════════════
# key 矩陣 — date / datetime / ISO-str / int passthrough
# ═══════════════════════════════════════════════════════════════════════════════


def test_date_key_contiguous_roundtrip_and_index_map():
    """連續 date：無缺 bar 時 ordinal-offset 恰為 0..N-1；index_map 可逆重建原 date。"""
    dates = _dates(120)
    cand = _date_series(dates, lambda i, r: r.gauss(0.0005, 0.01), seed=1)
    btc = _date_series(dates, lambda i, r: r.gauss(0, 0.02), seed=2)
    alt = _date_series(dates, lambda i, r: r.gauss(0, 0.02), seed=3)
    mask = {d: False for d in dates}
    res = reindex_to_int_bar_index(cand, btc, alt, mask)
    assert res.candidate is not None and res.btc is not None
    assert res.n_bars == 120
    # 無缺 bar → ordinal-offset 恰為 dense 0..N-1。
    assert sorted(res.candidate.keys()) == list(range(120))
    # 四輸出 key 域 = 同一 int 集合。
    assert set(res.candidate) == set(res.btc) == set(res.altcap) == set(res.mask)
    # index_map 審計可逆：idx → 原 date，值不漂移。
    for idx, d in res.index_map.items():
        assert res.candidate[idx] == cand[d]
        assert res.btc[idx] == btc[d]


def test_datetime_key_normalized_to_date():
    """datetime key（含時分）取 .date()，與 date key 同 idx 域。"""
    stamps = [dt.datetime(2025, 1, 1, 8, 30) + dt.timedelta(days=i) for i in range(100)]
    cand = {s: 0.001 for s in stamps}
    btc = {s: 0.002 for s in stamps}
    alt = {s: 0.003 for s in stamps}
    res = reindex_to_int_bar_index(cand, btc, alt, None)
    assert res.candidate is not None
    assert res.n_bars == 100
    assert sorted(res.candidate.keys()) == list(range(100))
    assert res.index_map[0] == dt.date(2025, 1, 1)


def test_iso_str_key_with_z_and_timezone():
    """ISO 字串 key：純 date / 帶 Z / 帶 +00:00 時區皆可解析（語意同 altcap_basket）。"""
    cand = {"2025-01-01": 0.001, "2025-01-02T00:00:00Z": 0.002, "2025-01-03T00:00:00+00:00": 0.003}
    btc = {dt.date(2025, 1, 1): 0.01, dt.date(2025, 1, 2): 0.02, dt.date(2025, 1, 3): 0.03}
    res = reindex_to_int_bar_index(cand, btc, None, None)
    assert res.candidate is not None
    assert res.n_bars == 3
    assert sorted(res.candidate.keys()) == [0, 1, 2]
    assert res.candidate[1] == 0.002  # "2025-01-02T00:00:00Z" → idx 1


def test_int_key_passthrough_unchanged():
    """全輸入已是 int bar index → pass-through 原樣回 + already_int_passthrough（不重編）。"""
    cand = {i: 0.001 * i for i in range(100)}
    btc = {i: 0.002 for i in range(100)}
    alt = {i: 0.003 for i in range(100)}
    mask = {i: (i % 3 == 0) for i in range(100)}
    res = reindex_to_int_bar_index(cand, btc, alt, mask)
    assert "already_int_passthrough" in res.reasons
    assert res.candidate == cand and res.btc == btc
    assert res.altcap == alt and res.mask == mask
    assert res.index_map == {}  # int key 無原 date 可審計
    assert res.n_bars == 100


# ═══════════════════════════════════════════════════════════════════════════════
# fail-loud 矩陣 — mixed / duplicate / unparseable / bar / index_rule / missing
# ═══════════════════════════════════════════════════════════════════════════════


def test_mixed_int_and_date_within_series_fail_loud():
    """單 series 內 int + date 混型 → 全 None + mixed reason（不靜默丟 row）。"""
    dates = _dates(50)
    cand = {d: 0.001 for d in dates}
    cand[7] = 0.002  # 混入 int key
    btc = {d: 0.01 for d in dates}
    res = reindex_to_int_bar_index(cand, btc, None, None)
    _assert_all_none(res)
    assert "mixed_int_and_temporal_keys" in res.reasons


def test_mixed_across_inputs_fail_loud():
    """跨輸入混型（candidate 全 int、btc 全 date）→ 全 None（int 無法 map 進 date 域）。"""
    cand = {i: 0.001 for i in range(50)}
    btc = {d: 0.01 for d in _dates(50)}
    res = reindex_to_int_bar_index(cand, btc, None, None)
    _assert_all_none(res)
    assert "mixed_int_and_temporal_keys" in res.reasons


def test_duplicate_date_after_normalize_fail_loud():
    """datetime 同日兩筆（正規化撞同 date）→ duplicate_date_after_normalize + 全 None。"""
    dates = _dates(50)
    cand = {d: 0.001 for d in dates}
    btc: dict = {dt.datetime(2025, 1, 1, 0, 0): 0.01, dt.datetime(2025, 1, 1, 12, 0): 0.02}
    for d in dates[1:]:
        btc[dt.datetime(d.year, d.month, d.day)] = 0.01
    res = reindex_to_int_bar_index(cand, btc, None, None)
    _assert_all_none(res)
    assert "duplicate_date_after_normalize" in res.reasons


def test_duplicate_str_and_date_same_day_fail_loud():
    """str "2025-01-01" 與 date(2025,1,1) 並存（dict 容雙 key，正規化撞日）→ fail-loud。"""
    cand: dict = {d: 0.001 for d in _dates(30)}
    cand["2025-01-01"] = 0.999  # 與 date(2025,1,1) 撞日
    btc = {d: 0.01 for d in _dates(30)}
    res = reindex_to_int_bar_index(cand, btc, None, None)
    _assert_all_none(res)
    assert "duplicate_date_after_normalize" in res.reasons


def test_unparseable_str_key_fail_loud():
    """不可解析字串 key → unparseable_temporal_key + 全 None（不猜測）。"""
    cand: dict = {d: 0.001 for d in _dates(30)}
    cand["not-a-date"] = 0.002
    btc = {d: 0.01 for d in _dates(30)}
    res = reindex_to_int_bar_index(cand, btc, None, None)
    _assert_all_none(res)
    assert "unparseable_temporal_key" in res.reasons


def test_bar_4h_explicitly_unsupported():
    """bar="4h" 顯式不支持 → bar_reindex_unsupported:4h + 全 None（toordinal 取日會撞 key）。"""
    dates = _dates(50)
    cand = {d: 0.001 for d in dates}
    btc = {d: 0.01 for d in dates}
    res = reindex_to_int_bar_index(cand, btc, None, None, bar="4h")
    _assert_all_none(res)
    assert "bar_reindex_unsupported:4h" in res.reasons


def test_unknown_index_rule_fail_loud_no_silent_fallback():
    """未知 index_rule → fail-loud（靜默 fallback 會無聲改變 span 語意）。"""
    dates = _dates(50)
    cand = {d: 0.001 for d in dates}
    btc = {d: 0.01 for d in dates}
    res = reindex_to_int_bar_index(cand, btc, None, None, index_rule="zigzag")
    _assert_all_none(res)
    assert "index_rule_unsupported:zigzag" in res.reasons


def test_missing_candidate_or_btc_fail_loud():
    """candidate/btc 任一 None（交集必要成員）→ 全 None + 對應 missing reason。"""
    dates = _dates(30)
    series = {d: 0.001 for d in dates}
    res1 = reindex_to_int_bar_index(None, series, None, None)
    _assert_all_none(res1)
    assert "candidate_returns_missing" in res1.reasons
    res2 = reindex_to_int_bar_index(series, None, None, None)
    _assert_all_none(res2)
    assert "btc_returns_missing" in res2.reasons


def test_emits_warning_on_fail_loud(caplog):
    """fail-loud 的「loud」：logger.warning 帶違規 key 型別/值（接線錯誤 log 即可診斷）。"""
    import logging

    cand: dict = {d: 0.001 for d in _dates(30)}
    cand["not-a-date"] = 0.002
    btc = {d: 0.01 for d in _dates(30)}
    with caplog.at_level(logging.WARNING):
        reindex_to_int_bar_index(cand, btc, None, None)
    assert any("not-a-date" in rec.getMessage() for rec in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════════
# 交集 / altcap=None / mask 語意
# ═══════════════════════════════════════════════════════════════════════════════


def test_intersection_excludes_unshared_dates():
    """共同 span = candidate ∩ btc ∩ altcap；各自多出的 date 不入輸出。"""
    cand = {d: 0.001 for d in _dates(100)}          # day 0..99
    btc = {d: 0.01 for d in _dates(110)}            # day 0..109
    alt = {_BASE + dt.timedelta(days=i): 0.02 for i in range(10, 105)}  # day 10..104
    res = reindex_to_int_bar_index(cand, btc, alt, None)
    assert res.candidate is not None
    assert res.n_bars == 90  # 交集 = day 10..99
    assert res.index_map[0] == _BASE + dt.timedelta(days=10)  # d0 = 交集最早 date
    assert set(res.candidate) == set(res.btc) == set(res.altcap)


def test_altcap_none_not_in_intersection_output_none():
    """altcap=None（producer 缺）→ 交集不含 altcap、輸出 altcap=None（B1 自己 DEFER）。"""
    dates = _dates(100)
    cand = {d: 0.001 for d in dates}
    btc = {d: 0.01 for d in dates}
    res = reindex_to_int_bar_index(cand, btc, None, None)
    assert res.candidate is not None and res.btc is not None
    assert res.altcap is None and res.mask is None
    assert res.n_bars == 100
    assert "altcap_missing" in res.reasons and "mask_missing" in res.reasons


def test_mask_gap_filled_false_with_accounting():
    """mask 不參與交集；交集內缺 date → 該 bar False + mask_gap_filled_false:<n> 顯式記帳。"""
    dates = _dates(100)
    cand = {d: 0.001 for d in dates}
    btc = {d: 0.01 for d in dates}
    alt = {d: 0.02 for d in dates}
    # mask 缺 3 個交集 date（day 5/6/7），其餘 True。
    missing = set(dates[5:8])
    mask = {d: True for d in dates if d not in missing}
    res = reindex_to_int_bar_index(cand, btc, alt, mask)
    assert res.mask is not None
    assert "mask_gap_filled_false:3" in res.reasons
    assert res.mask[5] is False and res.mask[6] is False and res.mask[7] is False
    assert res.mask[0] is True and res.mask[99] is True
    # mask 缺 date 不縮窗（交集仍 100）。
    assert res.n_bars == 100


def test_mask_superset_does_not_widen_intersection():
    """mask date 域 ⊇ btc 域（BTC closes 全集衍生）：超出交集的 mask date 不入輸出。"""
    dates = _dates(60)
    cand = {d: 0.001 for d in dates}
    btc = {d: 0.01 for d in dates}
    mask = {d: True for d in _dates(90)}  # 比交集多 30 天
    res = reindex_to_int_bar_index(cand, btc, None, mask)
    assert res.mask is not None
    assert len(res.mask) == 60  # mask 域 = 交集域
    assert res.n_bars == 60


def test_empty_intersection_honest_empty_output():
    """無共同 date → 空 dict + empty_date_intersection（非 None：下游 B1 自然 window DEFER）。"""
    cand = {d: 0.001 for d in _dates(30)}
    btc = {_BASE + dt.timedelta(days=100 + i): 0.01 for i in range(30)}  # 完全錯開
    res = reindex_to_int_bar_index(cand, btc, None, None)
    assert res.candidate == {} and res.btc == {}
    assert res.n_bars == 0
    assert "empty_date_intersection" in res.reasons


# ═══════════════════════════════════════════════════════════════════════════════
# 缺 bar span 保真 — ordinal-offset vs dense（本模組的存在理由）
# ═══════════════════════════════════════════════════════════════════════════════


def test_gap_span_fidelity_ordinal_preserves_dense_underestimates():
    """缺 bar 序列（每 3 天一根 bar）：dense 把 calendar span 壓成 N−1、ordinal-offset 保真。

    為什麼必測：B1 的 _span_days 對 int key 用 max−min 直接當天數；down-leg ≥180d span
    檢查語意是 calendar 跨度。dense 低估 → 真資料窗被無謂 DEFER 掉。
    """
    n = 100
    dates = _dates(n, step_days=3)  # 100 bars 跨 297 calendar 天
    true_span = (dates[-1] - dates[0]).days
    assert true_span == 297
    cand = {d: 0.001 for d in dates}
    btc = {d: 0.01 for d in dates}

    res_ord = reindex_to_int_bar_index(cand, btc, None, None, index_rule=INDEX_RULE_ORDINAL_OFFSET)
    res_dense = reindex_to_int_bar_index(cand, btc, None, None, index_rule=INDEX_RULE_DENSE)
    assert res_ord.candidate is not None and res_dense.candidate is not None

    # 與 beta_neutral_check._span_days 語意一致驗證（int key 走 max−min 當天數）。
    span_ord = _span_days(sorted(res_ord.candidate.keys()))
    span_dense = _span_days(sorted(res_dense.candidate.keys()))
    assert span_ord == float(true_span)      # ordinal-offset 保真 calendar 跨度
    assert span_dense == float(n - 1)        # dense 壓成 N−1 = 99，低估 297
    assert span_dense < span_ord


def test_no_gap_ordinal_equals_dense():
    """無缺 bar 時 ordinal-offset 與 dense 完全相同（恰為 0..N-1）——PA §D.3 的等價聲明。"""
    dates = _dates(100)
    cand = {d: 0.001 * i for i, d in enumerate(dates)}
    btc = {d: 0.01 for d in dates}
    res_ord = reindex_to_int_bar_index(cand, btc, None, None, index_rule=INDEX_RULE_ORDINAL_OFFSET)
    res_dense = reindex_to_int_bar_index(cand, btc, None, None, index_rule=INDEX_RULE_DENSE)
    assert res_ord.candidate == res_dense.candidate
    assert res_ord.index_map == res_dense.index_map


def test_b1_downleg_bite_dense_defers_ordinal_passes():
    """B1 down-leg 實際 bite：同一缺 bar 資料，dense → span<180d 誤殺 DEFER、ordinal → pass。

    構造：每 3 天一根 bar 共 130 bars（calendar 跨 387 天）。down bars 自然分散全 span
    （≥30 bars、ordinal span ≥180d 但 dense span = bars 位置差 < 180）。中性候選（β≈0）。
    """
    random.seed(7)
    n = 130
    dates = _dates(n, step_days=3)
    btc = {d: random.gauss(0, 0.02) for d in dates}
    alt = {d: random.gauss(0, 0.02) for d in dates}
    cand = {d: 0.0003 + random.gauss(0, 0.003) for d in dates}
    mask = {d: (btc[d] < -0.005) for d in dates}  # 自然 down bars 分散全 span

    res_ord = reindex_to_int_bar_index(cand, btc, alt, mask, index_rule=INDEX_RULE_ORDINAL_OFFSET)
    res_dense = reindex_to_int_bar_index(cand, btc, alt, mask, index_rule=INDEX_RULE_DENSE)
    assert res_ord.candidate is not None and res_dense.candidate is not None

    # down bars 充分（≥30）且真 calendar 跨度 ≥180d——資料本身合格。
    n_down = sum(1 for v in res_ord.mask.values() if v)
    assert n_down >= 30

    b1_ord = beta_neutral_check(
        res_ord.candidate, res_ord.btc, res_ord.altcap, res_ord.mask,
        bar="daily", n_trades_oos=200,
    )
    b1_dense = beta_neutral_check(
        res_dense.candidate, res_dense.btc, res_dense.altcap, res_dense.mask,
        bar="daily", n_trades_oos=200,
    )
    # ordinal-offset：span 保真 → 真中性候選 pass。
    assert b1_ord.verdict == "pass", f"reasons={b1_ord.reasons}"
    # dense：同一資料被壓 span（130 bars → max span 129 < 180）→ 誤殺 DEFER。
    assert b1_dense.verdict == "DEFER"
    assert "down_subsample_span_below_180d_defer" in b1_dense.reasons


# ═══════════════════════════════════════════════════════════════════════════════
# B1 串測 — reindex 輸出滿足 int-bar-index 契約 + 已知-β 真 verdict
# ═══════════════════════════════════════════════════════════════════════════════


def _chain_inputs(n=250, beta=0.0, seed=7):
    """date-key synthetic（連續日）：candidate = beta·btc + 噪音；mask = 自然 down bars。"""
    random.seed(seed)
    dates = _dates(n)
    btc = {d: random.gauss(0, 0.02) for d in dates}
    alt = {d: random.gauss(0, 0.02) for d in dates}
    cand = {d: beta * btc[d] + 0.0003 + random.gauss(0, 0.003) for d in dates}
    mask = {d: (btc[d] < -0.01) for d in dates}
    return cand, btc, alt, mask


def test_chain_reindex_output_satisfies_b1_contract():
    """date-key 經 reindex 餵 B1 → 不觸 temporal_keys_unsupported_need_int_bar_index。

    為什麼這條是 owed ① 的驗收核心：B1 對 date-key 顯式 DEFER（契約 fail-loud）；
    本模組就是契約的 producer-side 解——輸出必須讓 B1 走真回歸路徑。
    """
    cand, btc, alt, mask = _chain_inputs()
    res = reindex_to_int_bar_index(cand, btc, alt, mask)
    assert res.candidate is not None
    b1 = beta_neutral_check(
        res.candidate, res.btc, res.altcap, res.mask, bar="daily", n_trades_oos=200
    )
    assert _TEMPORAL_KEY_REASON not in b1.reasons
    assert b1.n_bars == 250  # 真資料窗無損傳遞


def test_chain_known_beta_injection_fails_b1():
    """synthetic β=0.5 注入 → B1 fail（beta_btc_above_threshold）：re-index 不洗掉因子載荷。"""
    cand, btc, alt, mask = _chain_inputs(beta=0.5, seed=5)
    res = reindex_to_int_bar_index(cand, btc, alt, mask)
    assert res.candidate is not None
    b1 = beta_neutral_check(
        res.candidate, res.btc, res.altcap, res.mask, bar="daily", n_trades_oos=200
    )
    assert b1.verdict == "fail"
    assert "beta_btc_above_threshold" in b1.reasons


def test_chain_neutral_candidate_passes_b1():
    """synthetic β=0 真中性 → B1 pass（down bars 自然分散全 span，無假 DEFER）。"""
    cand, btc, alt, mask = _chain_inputs(beta=0.0, seed=7)
    res = reindex_to_int_bar_index(cand, btc, alt, mask)
    assert res.candidate is not None
    b1 = beta_neutral_check(
        res.candidate, res.btc, res.altcap, res.mask, bar="daily", n_trades_oos=200
    )
    assert b1.verdict == "pass", f"reasons={b1.reasons}"

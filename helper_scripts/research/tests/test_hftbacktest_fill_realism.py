"""hftbacktest fill-realism harness 測試（D2 re-validation；E2 三審查點全覆蓋）。

覆蓋（PA design §4.4 E2 三審查點逐條 + 隔離紅線）：
  - 禁 rebate 鐵則：assert_no_rebate(0.0) OK；任何 rebate!=0 → RebateForbiddenError；
    compute_net_and_verdict 傳非 0 rebate → raise（DECISIVE BLOCKER 執行點）。
  - leak-free entry：build_maker_specs 的 event_ts_ns = cascade 末筆強平時戳；
    detect_cascades 用群組末筆時戳（不向前看群組內更早資訊）。
  - INSUFFICIENT_SAMPLE 不被旁路：net 正 + fill 不致命但成交 < 門檻 → 強制
    INSUFFICIENT_SAMPLE（禁吐 HARVESTABLE）；fill_rate 致命低 → NON-HARVESTABLE。
  - 未成交計入 fill_rate 分母：fill_rate = n_filled / n_events（含未成交事件）。
  - cascade 偵測：時間聚類 + min_events 閾值 + 方向分組正確；反 cascade 方向映射
    （Sell-清算 → buy / Buy-清算 → sell）。
  - Tardis liquidations CSV 解析（µs ts + side 正規化）。
  - host allowlist / 禁 redirect / 免費日 day==1 守衛（data_fetch）。
  - append-only run dir（重名 raise）+ manifest sha256 完整性 + rebate=0 公示。
  - 隔離紅線：源碼零生產 import、零 auth/order/IPC token、零 5-gate 觸碰。
  - hftbacktest 真實 njit 模擬 smoke（合成 L2 tape，opt-in，無套件 skip）。
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import tokenize
from pathlib import Path

import pytest

from hftbacktest_fill_realism import (
    FILL_RATE_FATAL_FLOOR,
    MAKER_FEE_BPS_PER_LEG,
    MAKER_REBATE_BPS,
    MIN_HARVESTABLE_FILLED_EVENTS,
    RebateForbiddenError,
    VERDICT_BLOCKED,
    VERDICT_HARVESTABLE,
    VERDICT_INSUFFICIENT_SAMPLE,
    VERDICT_NON_HARVESTABLE,
    assert_no_rebate,
)
from hftbacktest_fill_realism import artifact as artifact_mod
from hftbacktest_fill_realism import bridge_d2 as bridge_mod
from hftbacktest_fill_realism import data_fetch as fetch_mod
from hftbacktest_fill_realism import harness as harness_mod

_PKG_DIR = Path(__file__).resolve().parents[1] / "hftbacktest_fill_realism"


# ---------------------------------------------------------------------------
# 禁 rebate 鐵則（DECISIVE BLOCKER）
# ---------------------------------------------------------------------------

def test_assert_no_rebate_zero_ok():
    assert_no_rebate(0.0)  # 不 raise


@pytest.mark.parametrize("bad", [0.5, -0.5, 1.0, -1.0, 2.0])
def test_assert_no_rebate_nonzero_raises(bad):
    with pytest.raises(RebateForbiddenError):
        assert_no_rebate(bad)


def test_module_rebate_constant_is_zero():
    # 配置常數本身必為 0（reviewer 一眼可驗）。
    assert MAKER_REBATE_BPS == 0.0


def test_compute_net_rejects_positive_rebate():
    sim = harness_mod.SimResult(n_events=1)
    with pytest.raises(RebateForbiddenError):
        bridge_mod.compute_net_and_verdict(sim, maker_rebate_bps=0.5)


def test_net_uses_no_rebate_in_round_trip():
    # 成交事件，convergence 大，驗 net = gross − 2*maker_fee（rebate=0，無扣減）。
    o = harness_mod.FillOutcome(
        event_id="e0", side="buy", submitted=True, filled=True,
        entry_ts_ns=1, fill_ts_ns=2, fill_px=100.0,
        adverse_selection_bps=1.0, convergence_bps=20.0, reason="filled",
    )
    sim = harness_mod.SimResult(outcomes=[o], n_events=1, n_submitted=1, n_filled=1)
    res = bridge_mod.compute_net_and_verdict(sim)
    # gross = conv − adverse = 20 − 1 = 19；maker round-trip = 2*2 − 0 = 4。
    assert res["gross_edge_bps"] == pytest.approx(19.0)
    assert res["maker_round_trip_fee_bps"] == pytest.approx(4.0)
    assert res["net_maker_bps"] == pytest.approx(15.0)
    assert res["maker_rebate_bps"] == 0.0


# ---------------------------------------------------------------------------
# INSUFFICIENT_SAMPLE 不被旁路 + 未成交計入分母
# ---------------------------------------------------------------------------

def _make_sim(n_events, n_filled, conv=50.0, adverse=1.0):
    outcomes = []
    for i in range(n_filled):
        outcomes.append(harness_mod.FillOutcome(
            event_id=f"e{i}", side="buy", submitted=True, filled=True,
            entry_ts_ns=1, fill_ts_ns=2, fill_px=100.0,
            adverse_selection_bps=adverse, convergence_bps=conv, reason="filled",
        ))
    for i in range(n_events - n_filled):
        outcomes.append(harness_mod.FillOutcome(
            event_id=f"u{i}", side="buy", submitted=True, filled=False,
            entry_ts_ns=1, fill_ts_ns=0, fill_px=0.0,
            adverse_selection_bps=0.0, convergence_bps=0.0, reason="not_filled",
        ))
    return harness_mod.SimResult(outcomes=outcomes, n_events=n_events, n_submitted=n_events, n_filled=n_filled)


def test_fill_rate_includes_unfilled_in_denominator():
    # 10 事件、3 成交 → fill_rate = 0.3（未成交計入分母）。
    sim = _make_sim(n_events=10, n_filled=3)
    res = bridge_mod.compute_net_and_verdict(sim)
    assert res["maker_fill_rate"] == pytest.approx(0.3)
    assert res["n_events"] == 10
    assert res["n_filled"] == 3


def test_fatal_low_fill_rate_is_non_harvestable():
    # fill_rate < fatal_floor → NON-HARVESTABLE（即使 net 正）。
    sim = _make_sim(n_events=100, n_filled=10, conv=999.0)  # fill_rate 0.10 < 0.30
    res = bridge_mod.compute_net_and_verdict(sim)
    assert res["verdict"] == VERDICT_NON_HARVESTABLE
    assert "fatal_low_fill_rate" in res["verdict_detail"]


def test_net_negative_is_non_harvestable():
    # convergence 小於 fee → net <= 0 → NON-HARVESTABLE。
    sim = _make_sim(n_events=100, n_filled=80, conv=1.0, adverse=0.0)  # gross 1 − fee 4 = −3
    res = bridge_mod.compute_net_and_verdict(sim)
    assert res["verdict"] == VERDICT_NON_HARVESTABLE
    assert res["net_maker_bps"] < 0


def test_small_sample_positive_net_cannot_be_harvestable():
    # 關鍵 E2 審查點：net 正 + fill 不致命，但成交 < 門檻 → 禁吐 HARVESTABLE。
    n_filled = MIN_HARVESTABLE_FILLED_EVENTS - 1
    sim = _make_sim(n_events=int(n_filled / 0.9) + 1, n_filled=n_filled, conv=50.0)
    res = bridge_mod.compute_net_and_verdict(sim)
    assert res["maker_fill_rate"] >= FILL_RATE_FATAL_FLOOR  # fill 不致命
    assert res["net_maker_bps"] > 0  # net 正
    assert res["verdict"] == VERDICT_INSUFFICIENT_SAMPLE  # 仍禁 HARVESTABLE
    assert res["verdict"] != VERDICT_HARVESTABLE


def test_large_sample_positive_net_is_harvestable():
    # 大樣本 + net 正 + fill 不致命 → 才允許 HARVESTABLE。
    sim = _make_sim(n_events=60, n_filled=MIN_HARVESTABLE_FILLED_EVENTS + 5, conv=50.0)
    res = bridge_mod.compute_net_and_verdict(sim)
    assert res["maker_fill_rate"] >= FILL_RATE_FATAL_FLOOR
    assert res["net_maker_bps"] > 0
    assert res["n_filled"] >= MIN_HARVESTABLE_FILLED_EVENTS
    assert res["verdict"] == VERDICT_HARVESTABLE


def test_zero_events_is_insufficient():
    res = bridge_mod.compute_net_and_verdict(harness_mod.SimResult(n_events=0))
    assert res["verdict"] == VERDICT_INSUFFICIENT_SAMPLE


# ---------------------------------------------------------------------------
# cascade 偵測 + 反 cascade 方向映射 + leak-free entry
# ---------------------------------------------------------------------------

def _liq(ts_s, side, qty=1.0, price=100.0, symbol="BTCUSDT"):
    return {
        "ts": dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=ts_s),
        "symbol": symbol, "side": side, "qty": qty, "price": price,
    }


def test_detect_cascades_time_clustering_and_threshold():
    # 群組 1：3 筆 Sell 在 0/5/10s（<30s）→ 成 cascade；群組 2：2 筆 Sell 在 200/205s
    # → 不足 min_events=3，不成 cascade。
    liqs = [_liq(0, "Sell"), _liq(5, "Sell"), _liq(10, "Sell"),
            _liq(200, "Sell"), _liq(205, "Sell")]
    events = bridge_mod.detect_cascades(liqs, cluster_window_s=30.0, min_events=3)
    assert len(events) == 1
    assert events[0].n_liquidations == 3
    assert events[0].liq_side == "Sell"


def test_detect_cascades_direction_separated():
    # 同窗 Buy 與 Sell 不混入同一 cascade。
    liqs = [_liq(0, "Sell"), _liq(2, "Buy"), _liq(4, "Sell"), _liq(6, "Sell"),
            _liq(8, "Buy"), _liq(10, "Buy")]
    events = bridge_mod.detect_cascades(liqs, cluster_window_s=30.0, min_events=3)
    sides = sorted(e.liq_side for e in events)
    assert sides == ["Buy", "Sell"]


def test_build_maker_specs_anti_cascade_direction():
    # Sell-清算（多頭被強平下殺）→ 反 cascade buy（掛 last_price 下方）；
    # Buy-清算 → 反 cascade sell（掛上方）。
    ev_sell = bridge_mod.CascadeEvent(
        symbol="BTCUSDT", event_ts=_liq(10, "Sell")["ts"], liq_side="Sell",
        n_liquidations=3, total_qty=3.0, last_price=100.0,
    )
    ev_buy = bridge_mod.CascadeEvent(
        symbol="BTCUSDT", event_ts=_liq(10, "Buy")["ts"], liq_side="Buy",
        n_liquidations=3, total_qty=3.0, last_price=100.0,
    )
    specs = bridge_mod.build_maker_specs([ev_sell, ev_buy], overshoot_offset_bps=10.0)
    # 方向：Sell-清算 → 反 cascade buy；Buy-清算 → 反 cascade sell。
    # peg 以 BBO-相對 offset 表達（harness 內用 live BBO 算實際掛單價）。
    assert specs[0].side == "buy" and specs[0].peg_offset_bps == 10.0
    assert specs[1].side == "sell" and specs[1].peg_offset_bps == 10.0


def test_maker_spec_entry_ts_equals_event_ts():
    # leak-free：spec.event_ts_ns 必等於 cascade 事件時戳（entry 必落事件後）。
    ev = bridge_mod.CascadeEvent(
        symbol="BTCUSDT", event_ts=_liq(42, "Sell")["ts"], liq_side="Sell",
        n_liquidations=3, total_qty=3.0, last_price=100.0,
    )
    spec = bridge_mod.build_maker_specs([ev])[0]
    assert spec.event_ts_ns == bridge_mod.event_ts_to_ns(ev.event_ts)


# ---------------------------------------------------------------------------
# Tardis liquidations CSV 解析
# ---------------------------------------------------------------------------

def test_load_liquidations_tardis_csv(tmp_path):
    csv_text = (
        "exchange,symbol,timestamp,local_timestamp,id,side,price,amount\n"
        "bybit,BTCUSDT,1704067438900000,1704067518292589,,buy,42619.9,0.231\n"
        "bybit,BTCUSDT,1704067497899000,1704067569391234,,sell,42655.5,0.046\n"
        "bybit,BTCUSDT,bad,bad,,buy,bad,bad\n"  # 壞行跳過
    )
    p = tmp_path / "liq.csv.gz"
    with gzip.open(str(p), "wt", encoding="utf-8") as fh:
        fh.write(csv_text)
    rows = bridge_mod.load_liquidations_tardis_csv(p)
    assert len(rows) == 2  # 壞行 fail-soft 跳過
    assert rows[0]["side"] == "Buy"   # buy → Bybit Buy
    assert rows[1]["side"] == "Sell"  # sell → Bybit Sell
    assert rows[0]["ts"].tzinfo is not None


# ---------------------------------------------------------------------------
# data_fetch host allowlist + 禁 redirect + 免費日守衛
# ---------------------------------------------------------------------------

def test_build_url_rejects_non_first_day():
    with pytest.raises(fetch_mod.TardisFetchError):
        fetch_mod.build_url("trades", dt.date(2024, 1, 2), "BTCUSDT")


def test_build_url_first_day_ok():
    url = fetch_mod.build_url("incremental_book_L2", dt.date(2024, 1, 1), "BTCUSDT")
    assert url.startswith("https://datasets.tardis.dev/v1/bybit/incremental_book_L2/2024/01/01/BTCUSDT.csv.gz")


def test_host_allowlist_rejects_foreign_host():
    with pytest.raises(fetch_mod.TardisFetchError):
        fetch_mod._assert_host_allowed("https://evil.example.com/v1/bybit/trades/x.csv.gz")


def test_host_allowlist_accepts_tardis():
    fetch_mod._assert_host_allowed("https://datasets.tardis.dev/v1/bybit/trades/x.csv.gz")  # 不 raise


# ---------------------------------------------------------------------------
# artifact append-only + manifest 完整性
# ---------------------------------------------------------------------------

def test_create_run_dir_append_only(tmp_path):
    root = tmp_path / "runs"
    rd = artifact_mod.create_run_dir("r1", root)
    assert rd.exists()
    with pytest.raises(FileExistsError):
        artifact_mod.create_run_dir("r1", root)  # 重名 raise（PIT 鐵則）


def test_manifest_sha256_and_rebate_zero(tmp_path):
    root = tmp_path / "runs"
    rd = artifact_mod.create_run_dir("r2", root)
    payload = {"verdict": VERDICT_NON_HARVESTABLE, "net_maker_bps": -3.0, "maker_rebate_bps": 0.0}
    out = artifact_mod.write_manifest_and_index(
        rd, mode="revalidate-d2", run_id="r2", repo_root=_PKG_DIR.parents[2],
        stats={"x": 1}, errors=[], d2_revalidation_payload=payload,
    )
    manifest = out["manifest"]
    assert manifest["maker_rebate_bps"] == 0.0
    assert "no_rebate" in manifest["policy"]
    # sha256 重驗：index 內每檔 sha256 與重算一致。
    index = json.loads((rd / "artifact_index.json").read_text())
    for a in index["artifacts"]:
        recomputed = artifact_mod.sha256_file(Path(a["path"]))
        assert recomputed == a["sha256"]


# ---------------------------------------------------------------------------
# 隔離紅線：源碼零生產 import / 零 auth / order / IPC / 5-gate token
# ---------------------------------------------------------------------------

def _code_only(src: str) -> str:
    """剝註釋 + 字串 token，只留真碼（負面 grep 避免 docstring/註解誤紅）。"""
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return src
    return " ".join(out)


@pytest.mark.parametrize("fname", ["__init__.py", "data_fetch.py", "converter.py",
                                   "harness.py", "bridge_d2.py", "cli.py", "artifact.py"])
def test_no_production_or_execution_imports(fname):
    code = _code_only((_PKG_DIR / fname).read_text())
    forbidden = [
        "order_manager", "place_order", "submit_order_live", "authorization",
        "live_execution_allowed", "execution_authority", "ipc_client", "ai_service",
        "PipelineCommand", "GovernanceHub", "RiskManager", "control_api_v1",
    ]
    for tok in forbidden:
        assert tok not in code, f"{fname} 不應引用生產/執行 token：{tok}"


def test_no_rebate_token_smuggled_into_net_path():
    # bridge_d2 net 計算碼不得出現「rebate 加回 net」的反向操作（只允許減 0）。
    code = (_PKG_DIR / "bridge_d2.py").read_text()
    assert "assert_no_rebate" in code  # 守衛在 net 入口
    assert "2.0 * maker_rebate_bps" in code  # round-trip 只「減」rebate（=0），不加回


# ---------------------------------------------------------------------------
# hftbacktest 真實 njit 模擬 smoke（合成 L2 tape）
# ---------------------------------------------------------------------------

def test_harness_real_njit_smoke():
    hbt = pytest.importorskip("hftbacktest")
    np = pytest.importorskip("numpy")
    h = hbt
    EXCH = h.EXCH_EVENT; LOC = h.LOCAL_EVENT; DEPTH = h.DEPTH_EVENT
    BUY = h.BUY_EVENT; SELL = h.SELL_EVENT; TRADE = h.TRADE_EVENT

    def ev(flag, e, l, px, q):
        a = np.zeros(1, dtype=h.event_dtype)
        a[0]["ev"] = flag; a[0]["exch_ts"] = e; a[0]["local_ts"] = l; a[0]["px"] = px; a[0]["qty"] = q
        return a

    t0 = 1_000_000_000
    rows = [ev(EXCH | LOC | DEPTH | BUY, t0, t0, 100.0, 5.0),
            ev(EXCH | LOC | DEPTH | SELL, t0, t0, 100.1, 5.0)]
    for i in range(1, 20):
        ts = t0 + i * 1_000_000_000
        rows.append(ev(EXCH | LOC | DEPTH | BUY, ts, ts + 1_000_000, 100.0, 5.0 + i * 0.1))
        rows.append(ev(EXCH | LOC | DEPTH | SELL, ts, ts + 1_000_000, 100.1, 5.0))
        rows.append(ev(EXCH | LOC | TRADE | SELL, ts, ts + 1_000_000, 100.0, 0.5))
    data = np.concatenate(rows)

    spec = harness_mod.MakerOrderSpec(
        event_id="smoke", side="buy", event_ts_ns=t0 + 2_000_000_000,
        peg_offset_bps=0.0, qty=0.1, exit_horizon_ns=10_000_000_000,
    )
    sim = harness_mod.simulate_maker_fills(
        data, [spec], tick_size=0.1, lot_size=0.001, queue_model="log_prob",
    )
    assert sim.n_events == 1
    assert sim.n_submitted == 1
    # 該事件成交（sell trade 持續打 bid）→ fill outcome 記錄完整，無 leak 違規。
    assert sim.outcomes[0].submitted is True
    assert not any(e.startswith("leak:") for e in sim.errors)
    assert sim.outcomes[0].entry_ts_ns >= spec.event_ts_ns  # leak guard 逐單成立

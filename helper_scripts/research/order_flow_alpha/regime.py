#!/usr/bin/env python3
"""order_flow_alpha.regime — leak-free 波動 regime 偵測器（$0 唯讀，OFFLINE）。

MODULE_NOTE
模塊用途：
  把時間（建議 hourly bucket）分類成 calm / elevated / high_vol 三個 regime，供
  order_flow_alpha.analysis 的「regime-split 決定性 fee-wall test」使用。決定性問題：
  order-flow edge 是否在 HIGH-VOL regime（spread 變寬但 edge 可能更寬）超過成本牆？
  （calm regime 已證不過——見 analysis.py 既有 verdict。）本檔只做 leak-free regime
  標籤，不下單、不碰生產 code，最終 verdict 屬 QC。

  資料來源（兩條，互補）：
    (A) 長 backdrop：market.klines BTCUSDT 1h（自 2026-04-05，~73 天），算 24h trailing
        realized-vol（hourly log-return 的 RMS）+ |hourly return|，**shift(1) PIT**：t 的
        regime 標籤只用 < t 的 bar，永不含 current-bar（leak-free 鐵律）。percentile 門檻
        以**全部歷史**分佈算（point-in-time 的歷史百分位）。
    (B) 短粒度 spike：market.klines BTCUSDT 1m，算 60m trailing baseline 的 |r| z-score
        （同樣 PIT，ROWS 60 PRECEDING AND 1 PRECEDING，不含 current bar）→ 偵測 intraday
        vol-spike（單分鐘暴動）。

  regime 判定（三選一觸發即升級，取最嚴）：
    high_vol   = 24h trailing RV 在歷史 top quintile（>= p80）
                 OR |hourly return| > HIGH_ABS_RET_BP（預設 80bp，≈歷史 p93）
                 OR 該小時內 1m vol-spike z-score >= SPIKE_Z（預設 8.0，≈1m |r| p99.85 稀有尾端）
    elevated   = 24h trailing RV 在 p50..p80
                 OR |hourly return| > ELEVATED_ABS_RET_BP（預設 40bp，≈歷史 p79）
    calm       = 其餘（24h trailing RV < p50 且無 spike）

  為什麼 top quintile 當 high_vol：mandate 要的是「vol event」窗，top-20% RV 是穩健的
  「明顯高於常態」界線；單一 |hourly return| / z-score 的 OR 補抓「RV 還沒爬上來但瞬間暴動」
  的開場（RV 是 trailing 平均，對突發 spike 反應滯後）。

依賴（READ-ONLY 復用 sibling 的 microstructure 資料層，不改其檔）：
  - program_code.research.microstructure.data_loader.connect（read-only session）
  本檔只多讀 market.klines（kline backdrop），不改 sibling 任何檔。

硬邊界：
  - 純讀 PG（connect 已 set_session readonly=True）；0 寫、0 order、0 auth/lease/risk。
  - leak-free：所有 rolling 統計 shift(1)（ROWS ... 1 PRECEDING），禁 current-bar；
    percentile 門檻是「歷史分佈」的描述性界線，非用未來資料挑門檻。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import timezone

import numpy as np
import pandas as pd

# --- READ-ONLY 引入 sibling microstructure 資料層（不改其檔；加路徑供 import）---
_THIS = os.path.realpath(__file__)
_SRV_ROOT = os.path.abspath(os.path.join(_THIS, "..", "..", "..", ".."))
if _SRV_ROOT not in sys.path:
    sys.path.insert(0, _SRV_ROOT)

from program_code.research.microstructure import data_loader as ms_loader  # noqa: E402

BETA_SYM = "BTCUSDT"

# --- regime 門檻常數（report 內全部明列；非用未來資料挑選，是 mandate 指定的描述性界線）---
# 24h trailing RV 的歷史 quintile 界線：>= p80 = top quintile = high_vol。
RV_TOP_QUINTILE_PCTILE = 0.80
RV_ELEVATED_PCTILE = 0.50
# |hourly return| 絕對門檻（bp）：補抓 RV 滯後時的突發行情。
# 80bp ≈ BTC 歷史 1h |ret| p93；40bp ≈ p79（見 report STEP 0 經驗分佈）。
HIGH_ABS_RET_BP = 80.0
ELEVATED_ABS_RET_BP = 40.0
# intraday 1m vol-spike z-score（60m PIT baseline）：>=8.0 視為 high_vol spike。
# 為什麼 8.0 而非 4.0：z>=4.0 是 1m |r| 的 ~p99（BTC 1m 約 1099/106422 分鐘命中），
# 而每小時 ~60 分鐘 → 幾乎每小時都有一筆 z>=4 → 該 OR clause 會把 ~45% 小時誤標 high_vol，
# 違背「high_vol=明顯尾端」本意。z>=8.0 是 ~p99.85（155/106422，約 0.15% 分鐘）= 真正
# 「該小時內出現極端單分鐘暴動」的稀有事件，補抓「RV 還沒爬上來但瞬間崩/拉」的開場。
SPIKE_Z = 8.0
# trailing RV 視窗（小時數）。
RV_TRAIL_HOURS = 24
# 1m spike baseline 視窗（分鐘數）。
SPIKE_BASELINE_MIN = 60


@dataclass
class RegimeThresholds:
    """偵測到的 regime 門檻（描述性歷史界線 + 常數），report 內全文落地。"""
    rv_p50_bp: float
    rv_p80_bp: float
    rv_p90_bp: float
    rv_p95_bp: float
    rv_max_bp: float
    high_abs_ret_bp: float = HIGH_ABS_RET_BP
    elevated_abs_ret_bp: float = ELEVATED_ABS_RET_BP
    spike_z: float = SPIKE_Z
    rv_trail_hours: int = RV_TRAIL_HOURS
    spike_baseline_min: int = SPIKE_BASELINE_MIN
    n_hist_hours: int = 0


def _load_btc_klines(conn, timeframe: str) -> pd.DataFrame:
    """READ-ONLY 讀 BTCUSDT 指定 timeframe kline（ts, close）。

    為什麼直接 SQL：sibling data_loader 不含 kline loader（只 trades/ob_top/l1）；
    本檔只多讀 market.klines，仍走 sibling 的 read-only connect（結構性禁寫）。
    SQL 全參數化（timeframe 走 %s）。
    """
    q = ("SELECT ts, close FROM market.klines "
         "WHERE symbol = %s AND timeframe = %s ORDER BY ts")
    df = pd.read_sql(q, conn, params=[BETA_SYM, timeframe])
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["close"] = df["close"].astype(float)
    return df


def _hourly_rv_table(conn) -> tuple[pd.DataFrame, RegimeThresholds]:
    """從 BTC 1h kline 算 PIT 24h trailing RV + |hourly ret| + 歷史 percentile 門檻。

    leak-free：rv24_pit 用 shift(1) 的 rolling RMS（窗 = [t-24h, t-1h]，**不含 t**）；
    percentile 是「全部歷史 rv24_pit 分佈」的描述性界線（非用未來挑門檻）。
    回傳 (hourly_df, thresholds)；hourly_df 含 ts/ret/rv24_pit/rv_pctile。
    """
    h = _load_btc_klines(conn, "1h")
    if h.empty or len(h) < RV_TRAIL_HOURS + 5:
        raise RuntimeError("BTC 1h kline 不足以建 trailing-RV regime backdrop")
    h = h.sort_values("ts").reset_index(drop=True)
    h["ret"] = np.log(h["close"] / h["close"].shift(1))
    # 24h trailing RV（hourly log-ret 的 RMS），shift(1) PIT：只用過去 24 根（不含 current）。
    sq = (h["ret"] ** 2)
    h["rv24_pit"] = np.sqrt(
        sq.shift(1).rolling(RV_TRAIL_HOURS, min_periods=RV_TRAIL_HOURS // 2).mean()
    )
    valid = h.dropna(subset=["rv24_pit"]).copy()
    # 歷史 percentile（描述性，全歷史分佈）。
    thr = RegimeThresholds(
        rv_p50_bp=round(float(valid["rv24_pit"].quantile(0.50)) * 1e4, 2),
        rv_p80_bp=round(float(valid["rv24_pit"].quantile(0.80)) * 1e4, 2),
        rv_p90_bp=round(float(valid["rv24_pit"].quantile(0.90)) * 1e4, 2),
        rv_p95_bp=round(float(valid["rv24_pit"].quantile(0.95)) * 1e4, 2),
        rv_max_bp=round(float(valid["rv24_pit"].max()) * 1e4, 2),
        n_hist_hours=int(len(valid)),
    )
    # 每根 hour 的歷史 percentile rank（PIT 描述用：rv 在全歷史分佈的位置）。
    valid["rv_pctile"] = valid["rv24_pit"].rank(pct=True)
    return valid, thr


def _spike_hours(conn, spike_z: float = SPIKE_Z) -> set:
    """從 BTC 1m kline 找「該小時內出現 vol-spike」的小時集合（PIT z-score）。

    leak-free：baseline = 過去 60 分鐘 |r| 的 mean/sd（shift(1)，不含 current bar），
    z = (|r_t| - base_mean) / base_sd；該小時內任一分鐘 z >= spike_z → 該小時標 spike。
    回傳 set[pd.Timestamp（floor 到 hour, UTC）]。
    """
    m = _load_btc_klines(conn, "1m")
    if m.empty or len(m) < SPIKE_BASELINE_MIN + 5:
        return set()
    m = m.sort_values("ts").reset_index(drop=True)
    r = np.log(m["close"] / m["close"].shift(1))
    abs_r = r.abs()
    base_mean = abs_r.shift(1).rolling(SPIKE_BASELINE_MIN, min_periods=SPIKE_BASELINE_MIN // 2).mean()
    base_sd = abs_r.shift(1).rolling(SPIKE_BASELINE_MIN, min_periods=SPIKE_BASELINE_MIN // 2).std()
    z = (abs_r - base_mean) / base_sd.replace(0.0, np.nan)
    m = m.assign(z=z)
    hit = m.loc[m["z"] >= spike_z, "ts"]
    return set(t.floor("h") for t in hit)


def classify_hours(conn) -> tuple[pd.DataFrame, RegimeThresholds, set]:
    """產出每小時的 regime 標籤表（calm / elevated / high_vol），全 leak-free PIT。

    回傳 (labelled_df, thresholds, spike_hours_set)。labelled_df 欄位：
      ts, ret_bp, rv24_pit_bp, rv_pctile, has_spike, regime。
    判定見 MODULE_NOTE（三選一觸發升級，取最嚴）。
    """
    hourly, thr = _hourly_rv_table(conn)
    spike_set = _spike_hours(conn, thr.spike_z)
    rows = []
    for _, row in hourly.iterrows():
        ts = row["ts"]
        ret_bp = float(row["ret"]) * 1e4 if pd.notna(row["ret"]) else np.nan
        rv_bp = float(row["rv24_pit"]) * 1e4
        pctile = float(row["rv_pctile"])
        has_spike = ts.floor("h") in spike_set
        abs_ret = abs(ret_bp) if pd.notna(ret_bp) else 0.0
        # 三條件 OR，取最嚴（high > elevated > calm）。
        if (pctile >= RV_TOP_QUINTILE_PCTILE
                or abs_ret > thr.high_abs_ret_bp
                or has_spike):
            regime = "high_vol"
        elif (pctile >= RV_ELEVATED_PCTILE
              or abs_ret > thr.elevated_abs_ret_bp):
            regime = "elevated"
        else:
            regime = "calm"
        rows.append({
            "ts": ts, "ret_bp": round(ret_bp, 1) if pd.notna(ret_bp) else None,
            "rv24_pit_bp": round(rv_bp, 1), "rv_pctile": round(pctile, 3),
            "has_spike": has_spike, "regime": regime,
        })
    return pd.DataFrame(rows), thr, spike_set


def window_regime(conn, since_ts, until_ts) -> dict:
    """給定 [since_ts, until_ts) 窗，回傳該窗內各 regime 的小時覆蓋摘要。

    用於 current-state readout：tape 窗內 calm / elevated / high_vol 各幾小時，
    是否已捕捉到 high_vol 窗（若無，回報需要多大 BTC move 才觸發）。
    """
    labelled, thr, spike_set = classify_hours(conn)
    if since_ts is not None:
        labelled = labelled[labelled["ts"] >= pd.Timestamp(since_ts)]
    if until_ts is not None:
        labelled = labelled[labelled["ts"] < pd.Timestamp(until_ts)]
    counts = labelled["regime"].value_counts().to_dict()
    high_hours = labelled[labelled["regime"] == "high_vol"]["ts"].tolist()
    # 若窗內無 high_vol：報「要多大 hourly move 才觸發」。
    # 當前 trailing RV percentile 的最近值 → 若 < p80，補抓門檻就是 HIGH_ABS_RET_BP。
    trigger_note = None
    if not high_hours and len(labelled):
        last_rv_pctile = float(labelled["rv_pctile"].iloc[-1])
        trigger_note = {
            "current_rv_pctile": round(last_rv_pctile, 3),
            "rv_path_to_high": f"24h trailing RV 需爬到歷史 p{int(RV_TOP_QUINTILE_PCTILE*100)} "
                               f"(>= {thr.rv_p80_bp}bp)",
            "single_bar_trigger": f"或單一 |hourly return| > {thr.high_abs_ret_bp}bp "
                                  f"(≈BTC 歷史 1h |ret| 高百分位) 即立刻觸發 high_vol",
            "spike_trigger": f"或單分鐘 |r| z-score >= {thr.spike_z}（60m PIT baseline）",
        }
    return {
        "window_since": since_ts.isoformat() if since_ts else None,
        "window_until": until_ts.isoformat() if until_ts else None,
        "n_hours_in_window": int(len(labelled)),
        "regime_hour_counts": {k: int(v) for k, v in counts.items()},
        "high_vol_hours": [t.isoformat() for t in high_hours],
        "elevated_hours": [t.isoformat() for t in
                           labelled[labelled["regime"] == "elevated"]["ts"].tolist()],
        "has_high_vol_window": bool(high_hours),
        "trigger_note_if_no_high_vol": trigger_note,
        "labelled_hours": labelled.to_dict(orient="records"),
    }


def regime_for_timestamps(conn, ts_index: pd.DatetimeIndex) -> pd.Series:
    """把任意 tz-aware 時間戳序列映射到其所屬小時的 regime 標籤。

    為什麼按「該時間戳所屬的小時 regime」：regime 是以 hourly bucket 標的，tick/grid 級
    樣本繼承其 floor('h') 小時的標籤。回傳與 ts_index 對齊的 Series（值 ∈ calm/elevated/
    high_vol/unknown）。leak-free：小時標籤本身 PIT（shift(1) RV），tick 落在哪小時就拿那
    小時的標籤——標籤在該小時開始時即已用「過去資料」算定，不引用該小時內的未來。
    """
    labelled, _thr, _spike = classify_hours(conn)
    lut = {row["ts"]: row["regime"] for _, row in labelled.iterrows()}
    idx = pd.DatetimeIndex(ts_index)
    if idx.tz is None:
        idx = idx.tz_localize(timezone.utc)
    floored = idx.floor("h")
    return pd.Series([lut.get(t, "unknown") for t in floored], index=ts_index)

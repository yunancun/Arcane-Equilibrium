"""microstructure.core — leak-free 純函數核心（0 DB / 0 網路）。

MODULE_NOTE
模塊用途：
  Campaign-8 微結構 harness 的計算核心。把 campaign8b/sharpen_ofi.py 驗證過的
  leak-free 邏輯逐位元搬進 repo，作為純函數（input = 已載入的 trades / ob_top
  DataFrame，output = report dict）。所有反作弊 / leak guard 在此，且不得弱化。

主要函數：
  - clean_obtop：壞 tick 硬過濾（NON-NEGOTIABLE）+ mid / book_imb 衍生。
  - build_grid：固定 GRID_STEP_S 秒網格，cumsum signed/abs volume + asof mid/book_imb。
  - ofi / fwd：OFI(w) 與前向報酬 fwd(h)，stride = w//grid / h//grid。
  - fisher_t：Spearman IC 的 Fisher-z t-stat（非重疊 n）。
  - assemble_frames：per-symbol leak-free (ofi, book_imb_shift1, resid_ret)，含
    leak-free rolling 30min BTC-beta 殘差化。
  - nonoverlap_stride / pooled_ic_t / per_symbol_same_sign：非重疊 pooled IC/t + 穩定度。

硬邊界：純函數，0 IO；leak guard 與成本牆語意是 governance trail，改動必同步報告。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

# BTC 作為市場 beta 因子代表（殘差化去 down-beta 偽裝）。
BETA_SYM = "BTCUSDT"
# 時間網格步長（秒）：所有 OFI/前向窗以此為對齊與 stride 單位。
GRID_STEP_S = 5
# leak-free rolling beta 視窗（秒）= 30min，cov/var 各 shift(1) 防 look-ahead。
BETA_ROLL_S = 1800
# symbol 入選最低逐筆 trade 數（流動性下限，避免極稀疏 symbol 污染 pool）。
MIN_TRADES = 500


def clean_obtop(ob: pd.DataFrame) -> pd.DataFrame:
    """壞 tick 硬過濾 + mid / book_imb 衍生。

    為什麼 NON-NEGOTIABLE：交叉（best_ask<=best_bid）/ 鎖死 / 單邊空簿是壞 tick，
    拿去算 imbalance 會製造假信號（campaign-8 v1 ob_top 實測 14.7% 壞 tick）。
    這層過濾在每次計算都必須保留，下游所有 mid / book_imb 都建立在乾淨快照上。
    """
    good = (
        (ob["best_ask"] > ob["best_bid"])  # 非交叉、非鎖死
        & (ob["bid_size"] > 0)
        & (ob["ask_size"] > 0)
    )
    ob = ob.loc[good].copy()
    ob["mid"] = 0.5 * (ob["best_bid"] + ob["best_ask"])
    ob["book_imb"] = (ob["bid_size"] - ob["ask_size"]) / (ob["bid_size"] + ob["ask_size"])
    return ob


def build_grid(tr_s: pd.DataFrame, ob_s: pd.DataFrame, t0, t1) -> pd.DataFrame:
    """單 symbol 對齊到固定 GRID_STEP_S 秒網格。

    cumsum signed/abs volume：之後 OFI(w) = (cs_t - cs_{t-w})/(ca_t - ca_{t-w})，
    純差分等價於窗內 signed/abs 量之和（避免逐窗 O(n^2) 掃描）。
    mid / book_imb 用 merge_asof(direction="backward")=取「<= t 最後一筆乾淨快照」，
    本身 leak-free（不看未來）；book_imb 在 assemble 再 shift(1) 做雙保險。
    """
    tr_s = tr_s.sort_values("ts").reset_index(drop=True)
    g = pd.DataFrame({"ts": pd.date_range(t0, t1, freq=f"{GRID_STEP_S}s")})
    g["px"] = pd.merge_asof(g, tr_s[["ts", "price"]], on="ts", direction="backward")["price"].values
    tr_s = tr_s.copy()
    tr_s["cs"] = tr_s["sgn"].cumsum()
    tr_s["ca"] = tr_s["qty"].cumsum()
    ca = pd.merge_asof(g, tr_s[["ts", "cs", "ca"]], on="ts", direction="backward")
    g["cs"] = ca["cs"].values
    g["ca"] = ca["ca"].values
    if ob_s is not None and len(ob_s) > 10:
        obx = ob_s.sort_values("ts")
        g["mid"] = pd.merge_asof(g, obx[["ts", "mid"]], on="ts", direction="backward")["mid"].values
        # book_imb：取「<= t 最後一筆乾淨快照」（asof-backward leak-free）。
        g["book_imb"] = pd.merge_asof(
            g, obx[["ts", "book_imb"]], on="ts", direction="backward"
        )["book_imb"].values
    else:
        g["mid"] = np.nan
        g["book_imb"] = np.nan
    return g.set_index("ts")


def ofi(g: pd.DataFrame, w: int) -> pd.Series:
    """OFI(w)：[t-w, t) 內 signed/abs 量之比，∈ [-1,1] 失衡度。

    用 cumsum 差分實作：(cs_t - cs_{t-w}) / (ca_t - ca_{t-w})。
    窗內無量（分母 0）→ NaN（不偽造 0），下游 dropna。
    """
    st = w // GRID_STEP_S
    return (g["cs"] - g["cs"].shift(st)) / (g["ca"] - g["ca"].shift(st)).replace(0, np.nan)


def fwd(g: pd.DataFrame, h: int, col: str) -> pd.Series:
    """前向報酬 fwd(h) = log(col_{t+h}/col_t)，嚴格在特徵窗之後 [t, t+h)。"""
    st = h // GRID_STEP_S
    return np.log(g[col].shift(-st) / g[col])


def fisher_t(ic: float, n: int) -> float:
    """Spearman IC 的 Fisher-z t-stat（用非重疊 n）。

    為什麼 Fisher-z：IC 的抽樣分佈非常態，Fisher-z 變換後 SE=1/sqrt(n-3) 近似常態。
    |IC|>=0.999 或 n<=5 回 NaN（退化，t 無意義）。
    """
    if not (abs(ic) < 0.999) or n <= 5:
        return float("nan")
    z = 0.5 * np.log((1 + ic) / (1 - ic))
    se = 1.0 / np.sqrt(n - 3)
    return z / se


def nonoverlap_stride(w: int, h: int) -> int:
    """非重疊 stride（bar 數）= ceil(max(w,h)/grid)。

    為什麼：誠實 t-stat 要求保留樣本之間「特徵窗(w) 與 預測窗(h) 皆不重疊」，
    否則相鄰樣本共享資訊 → t 被邊界自相關灌水。取 max(w,h) 同時保證兩窗皆不重疊。
    """
    return max(int(math.ceil(max(w, h) / GRID_STEP_S)), 1)


def assemble_frames(tr: pd.DataFrame, ob: pd.DataFrame, syms_all, w: int, h: int, pxcol: str):
    """per-symbol leak-free (ofi, book_imb_shift1, resid_ret) frames。

    leak-free 殘差化（去 down-beta 偽裝）：
      resid = fwd_ret_sym - beta * fwd_ret_btc，
      beta = leak-free rolling 30min（cov/var 各 shift(1) → t 的 beta 只用 < t 資訊），
      clip(-5,5) 防極端，fillna(0) 退化時不污染。
    book_imb 再 shift(1)：asof-backward 已 leak-free，這是「上一根 bar end 已知值」的雙保險。

    回傳 (frames: dict[sym -> DataFrame[o,b,resid]], cross_symbols: list)。
    BTC grid 缺失 → RuntimeError（無法殘差化，fail-loud）。
    """
    t0, t1 = tr["ts"].min().ceil("s"), tr["ts"].max().floor("s")
    grids = {}
    for s in syms_all:
        sub = tr[tr["symbol"] == s]
        if len(sub) < MIN_TRADES:
            continue
        grids[s] = build_grid(sub, ob[ob["symbol"] == s], t0, t1)
    if BETA_SYM not in grids:
        raise RuntimeError("no BTC grid (BTCUSDT trades below MIN_TRADES or absent)")
    btc_ret = fwd(grids[BETA_SYM], h, pxcol)
    btc_px = grids[BETA_SYM]["px"]
    cross = [s for s in syms_all if s in grids and s != BETA_SYM]
    out = {}
    for s in cross:
        g = grids[s]
        if g[pxcol].notna().sum() < 100:
            continue
        o = ofi(g, w)
        # book_imb shifted(1) bar = 嚴格 < t（asof-backward 之上額外 leak guard）。
        b = g["book_imb"].shift(1)
        rt = fwd(g, h, pxcol)
        df = pd.DataFrame({"o": o, "b": b, "rt": rt, "btc": btc_ret.reindex(g.index)})
        # leak-free rolling beta（5s contemporaneous returns）。
        r5s = np.log(g["px"] / g["px"].shift(1)).reindex(df.index)
        r5b = np.log(btc_px / btc_px.shift(1)).reindex(df.index)
        roll = max(BETA_ROLL_S // GRID_STEP_S, 30)
        beta = (
            r5s.rolling(roll).cov(r5b).shift(1) / r5b.rolling(roll).var().shift(1)
        ).clip(-5, 5).fillna(0.0)
        df["resid"] = df["rt"] - beta * df["btc"]
        df = df[["o", "b", "resid"]].dropna()
        if len(df) < 50:
            continue
        out[s] = df
    return out, cross


def pooled_ic_t(frames, col: str, stride: int):
    """pool per-symbol 非重疊（stride）樣本 → Spearman IC + Fisher-z t。

    回傳 (ic, t, n)。n 為「非重疊」樣本數（誠實），t 用該 n 算 Fisher-z。
    """
    xs, ys = [], []
    for _s, df in frames.items():
        xs.append(df[col].values[::stride])
        ys.append(df["resid"].values[::stride])
    if not xs:
        return float("nan"), float("nan"), 0
    X = np.concatenate(xs)
    Y = np.concatenate(ys)
    ic, _ = stats.spearmanr(X, Y)
    ic = float(ic)
    return ic, fisher_t(ic, len(X)), int(len(X))


def per_symbol_same_sign(frames, col: str, pooled_sign: int, stride: int, meaningful_t: float = 1.5):
    """per-symbol 穩定度：同號 fraction + 「同號 AND |t|>=meaningful_t」fraction。

    為什麼用 |t|>=1.5 軟門檻：per-symbol 非重疊 n 很小（~60-200），不能用嚴格顯著性，
    1.5 只當「有意義 hint」軟標尺。回傳逐 symbol 明細 + 聚合 fraction。
    """
    per_sym = []
    for s, df in frames.items():
        x = df[col].values[::stride]
        r = df["resid"].values[::stride]
        n = len(r)
        ic, _ = stats.spearmanr(x, r)
        ic = float(ic)
        t = fisher_t(ic, n)
        per_sym.append({"symbol": s, "n_nonoverlap": int(n), "ic": round(ic, 4),
                        "t": round(float(t), 2)})
    per_sym.sort(key=lambda d: -d["ic"])
    nsym = len(per_sym)
    if nsym == 0:
        return {"n_symbols": 0, "same_sign_frac": None, "same_sign_count": 0,
                "meaningful_t1p5_frac": None, "meaningful_t1p5_count": 0, "per_symbol": []}
    same = [p for p in per_sym if np.sign(p["ic"]) == pooled_sign]
    meaning = [p for p in same if abs(p["t"]) >= meaningful_t]
    return {
        "n_symbols": nsym,
        "pooled_sign": int(pooled_sign),
        "same_sign_frac": round(len(same) / nsym, 3),
        "same_sign_count": len(same),
        "meaningful_t1p5_frac": round(len(meaning) / nsym, 3),
        "meaningful_t1p5_count": len(meaning),
        "per_symbol": per_sym,
    }

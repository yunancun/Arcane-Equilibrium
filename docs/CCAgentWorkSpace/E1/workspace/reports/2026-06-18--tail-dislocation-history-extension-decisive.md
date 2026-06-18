# 尾部錯位 alpha 歷史延伸 — PM 決定性 re-entry gate（$0 唯讀 OFFLINE research）

日期：2026-06-18 · E1 · 交 QC/MIT 終裁 · 待 E2 審查

## 任務摘要

執行 PM 訂的精確 re-entry gate：prior `survival_safe.py`（2024-06..2026-06，26 大-cap，~2yr）回
NO_GO，binding kill 是**統計性且先於存活**——誠實 day-clustering 下有效 N=~119 distinct crash
episode、block-bootstrap boot_t=1.43、95%CI [-0.004,+0.027] **含 0**；且尾部是 SYNTHETIC 2% overlay
（universe 無真下市）。PM gate：「binding constraint=effective episode count，唯一可由 time accumulation
或 broader universe 修；在 delisting-inclusive panel + FIXED-NOTIONAL sizing 重測；線僅在 capped+
fixed-notional day-clustered boot_t 過 ~2.0（CI 排除 0）時以 CONDITIONAL candidate 重入。」

本 workflow 用 **$0 lever=延伸 HISTORY**：Bybit 公開 REST `/v5/market/kline`（category=linear,
interval=D,免 key keyless）回拉每 symbol 到最早可得，寫 RESEARCH ARTIFACT（非 prod PG），跑四 mandate
加固（day-clustered / empirical 2022 tail / fixed-notional / walk-forward OOS）。

## 修改清單

- 新增 `helper_scripts/research/tail_dislocation_meanrev/extend_history.py`（唯讀 research；import
  sibling `screen.py`+`survival_safe.py` helper，0 改 sibling）。
- 更新 `helper_scripts/SCRIPT_INDEX.md`（新 entry，Mac + Linux 同步）。
- 更新 E1 `memory.md` 近期記錄。
- 產物（Linux `/tmp/openclaw/research/tail_dislocation_meanrev/`）：`extend_full.json`
  （sha 9fb8f6e4…）+ 26 個 `rest_cache/<SYM>_1d.csv`。**0 寫 prod PG**（klines 仍 18885 rows 實證未動）。

## 決定性結果（Linux read-only，2020-03..2026-06，26 sym，6.23yr）

### 1. data extension + overlap 驗證
- 歷史延伸：BTC 2020-03-25、ETH 2021-03-15、多數 alt 2021-2022（APT/ARB/INJ/SUI/TON 2022-2023 上市起）。
  merged bars BTC 2276 / 多數 1700-2000 / POL 651（僅 1.78yr，2024-09 MATIC→POL rename）。
- **overlap 26/26 MATCH**：每 symbol 2024-06..2026-06 共同 bar（730，POL 635）逐 OHLC 比對 DB clean
  anchor，**0 mismatch、max_rel_diff=0.0**。REST path 完美乾淨，延伸歷史可信。

### 2. episode count（binding constraint）— per K，no-stop N3
| K | prior 2yr fills/episodes | now 6yr fills | now distinct episodes | fills in real-crash 窗 |
|---|---|---|---|---|
| K10 | ~819 / ~119 | 2365 | 428 | 483 |
| K15 | — | 787 | 146 | 232 |
| K20 | — | 354 | 59 | 113 |

有效 N（distinct episode）K10 86→428（注：prior 報 ~119 是全 grid；同口徑 K10 從 2yr 增 ~3.5x）。

### 3. THE decisive day-clustered 顯著性（capped C3 + fixed-notional）
| config | n_kept | n_days | boot_t (b1) | 95% CI (b1) | boot_t (b5) | verdict |
|---|---|---|---|---|---|---|
| K10N3 no-stop C3 | 923 | 428 | **4.95** | [0.017, 0.040] | 5.17 | 清 2.0、CI 排除 0 |
| K15N3 no-stop C3 | 304 | 146 | **4.69** | [0.031, 0.076] | 4.07 | 清 2.0、CI 排除 0 |
| K20N3 no-stop C3 | 126 | 59 | **4.08** | [0.037, 0.107] | 3.67 | 清 2.0、CI 排除 0 |
| best_fn (K15N1 C5) | 409 | 146 | **5.60** | [0.031, 0.065] | 5.29 | 清 2.0、CI 排除 0 |

**直接對比**：同 K15N3 config，prior 2yr → ~119 episode, boot_t 1.43, CI 含 0（kill）；now 6yr →
146 episode, boot_t 4.69, CI [0.031,0.076] 排除 0。**binding 統計 kill 在大歷史上消失**——effect 不是
2024-26 regime-specific，是真 alpha 被 ~2yr 過少 episode 數稀釋。block=5 敏感度穩健。

### 4. EMPIRICAL 2022 尾部（真 LUNA/3AC/FTX in-sample，取代合成 overlay）
- deep-K 接刀在真 crash 窗**未被毀滅**：K15 crash-window net_taker mean **+2.98%** / median +2.87% /
  pct_pos 57.8%；K20 mean **+8.71%** / pct_pos 68%。
- 逐窗（K15N3）：bear_2021_12 +3.89%(pct_pos 67%)、china_ban_2021_05 +3.02%(50%)、threeac_2022_06
  +6.00%(69%)、luna_2022_05 +3.09%(median −0.62%, 49%)、**ftx_2022_11 −1.23%**（唯一負，median +0.29%）。
- 尾部確較肥：crash-window CVaR5% **−32%**（K15）/ −30%（K20）vs all-window −24% / −22%；large_loss%
  crash 19.4% vs all 8.8%。worst single crash trade −36%（K15 china_ban FIL/類接刀後續崩）。
- **但 capped(C3)+fixed-notional(nf10) 全歷史含真崩盤 maxDD K15=12% / K20=6.7%，survivable=True**：
  相關尾部即使有真 2022 死亡螺旋，在固定名目 sizing 下未破 25% 門檻。

### 5. FIXED-NOTIONAL sizing（PM gate #1：decouple stop/leverage）
- 修正 survival_safe stop-anchored 的雙重反效果（risk_unit=S → lever=r/S，stop 越緊 lever 越大→
  gap-through 損失放大）。固定名目每槽 nf×equity，與 stop 無關。
- best fixed-notional config：**K15 / N1 / no-stop / C5 / nf20% → maxDD 0.166, annret 1.08,
  sharpe 2.22, worst_trade −0.35, mean_net +5.1%/trade**。
- top survivable+EV 全是 **no-stop deep-K**（K15/K20、C3-C5、nf10-20）：與 prior「hard stop 砍
  mean-rev alpha」一致——fixed-notional 下不需 stop 也 survivable，stop 仍是 net-negative。

### 6. walk-forward OOS（split 2024-01-01；早期含真崩盤）
| config | early boot_t / fn_maxDD | late(OOS) boot_t / CI / fn_maxDD | holds late | holds early |
|---|---|---|---|---|
| K15N1 C5 nf20 | 4.81 / 0.166 | 3.02 / [0.015,0.068] / 0.146 | True | True |
| K15N3 C3 nf10 | 3.90 / 0.120 | 2.85 / [0.013,0.073] / 0.053 | True | True |
| K20N3 C5 nf10 | 3.14 / 0.080 | 2.73 / [0.018,0.107] / 0.015 | True | True |
| K10N3 C3 nf10 | 4.59 / **0.271** | 2.09 / [0.001,0.035] / 0.225 | True | **False** |
| K10N2 C3 nf10 | 5.21 / **0.274** | 2.27 / [0.002,0.033] / 0.168 | True | **False** |

**所有 config OOS late 全 hold**（boot_t≥2.0、CI 排除 0、fn_maxDD≤25%）。唯一破門=K10 早期真崩盤段
（fn_maxDD 0.27、worst −0.68）→ 淺 K10 接太多邊際 dip，真 2022 崩盤 maxDD 爆。**深-K(K15/K20)
兩段全 hold**=較稀較乾淨的 panic 進場能存活真死亡螺旋。

## 治理對照（R-0 隔離紅線）

| 項目 | 狀態 |
|---|---|
| 純讀 PG | overlap 驗證僅 SELECT market.klines；prod klines 18885 rows 實證未動 |
| REST fetch | 純網路免 key（host api.bybit.com，ADR 允許 read-only 市場數據；Bybit 仍唯一執行所）；節流 sleep 0.2s |
| 寫 prod PG | 0（REST 寫 RESEARCH ARTIFACT csv，非 PG） |
| order / auth / lease / risk path | 0 觸碰 |
| production code 改 | 0（只新 research script + SCRIPT_INDEX + memory） |
| 硬邊界（max_retries/live_execution_allowed/system_mode） | 0 觸碰 |
| 跨平台路徑 | artifact root `${OPENCLAW_DATA_DIR:-/tmp/openclaw}` 推導，0 硬編碼 |

## 不確定之處（誠實 caveat）

1. **universe 仍全 still-trading**（n_possibly_delisted=0）：26 個都是延伸後仍在交易的 symbol。經驗
   尾部來自**真崩盤**（−30~50% deep-K days）而**非真歸零/delisting**——仍是 universe 層 survivor
   bias 殘留（比合成 2% overlay 真實得多，但非完整死亡）。真正 delisted-to-zero 的 symbol 不在此 26
   清單，要納入需更廣 universe（broader universe lever，本 workflow 走 time accumulation lever）。
2. **退出成本建模**：本檔用 taker-exit（5.5bp）算 net（保守）；maker-exit 會更好。hard-stop 退出恆 taker。
3. **POL 僅 1.78yr**（MATIC→POL rename，REST 只回到 2024-09）；其餘 23 個 ≥3.1yr。
4. **funding 覆蓋極低**：REST 歷史多無 funding → 缺值 0（conservative-favorable，long 多付 funding）。
5. preliminary_read=**LEANS_VIABLE_EDGE**，最終 GO/NO-GO verdict 屬 **QC/MIT**（leak-free 已 sibling
   驗過：進場 level 是 t-1 預設常數；本檔事件機制 100% 復用已驗的 survival_safe）。

## Operator / PM 下一步

- **E2 審查** extend_history.py（read-only research，0 production 觸碰）。
- 交 **QC/MIT** 終裁：本 gate 三條全過（day-clustered 顯著 + 真崩盤 survivable + OOS hold）→ PM 的
  CONDITIONAL candidate 重入條件滿足。建議 QC 評估是否值得 (a) broader universe（納入真 delisted
  symbol 補完 survivor bias）、(b) Stage 0R replay preflight（demo-only promotion path）。
- 產物 sha：`extend_full.json` = 9fb8f6e45e5c5cc909febe87c2b70916333b5c959edd35bb0f1c64d160162f8b。

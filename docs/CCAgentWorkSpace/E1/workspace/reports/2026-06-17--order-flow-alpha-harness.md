# Order-Flow Alpha Research Harness + 初步信號檢測 — 2026-06-17

> **STATUS: DONE_WITH_CONCERNS**（harness 交付完整並 Linux 實證；初步信號全部不過成本牆，
> 但這是單 regime / 數十小時資料的**指標性**初讀，非決定性 edge 結論——最終 verdict 屬 QC，
> 多 regime 驗證需 1-2 週累積。）
>
> 角色：E1（後端開發／研究 harness 執行者）。$0 OFFLINE、READ-ONLY。不下單、不碰生產
> engine/risk/execution、不改 sibling 已 commit 的 microstructure 檔。

---

## 任務摘要

建新 order-flow-alpha 3 軸研究 harness + 跑初步信號檢測，並做決定性的**成本牆存活測試**。
READ-ONLY 復用平行 session（sibling）的 microstructure 資料層，harness 本身放獨立新目錄。

---

## 修改清單（footprint）

| 檔 | 動作 | 說明 |
|---|---|---|
| `helper_scripts/research/order_flow_alpha/analysis.py` | **新增** | 3 軸 harness（~450 行）。READ-ONLY import sibling `data_loader`/`core`。 |
| `helper_scripts/SCRIPT_INDEX.md` | 加 1 dated section + 1 row | 登記新 harness（CLAUDE §七 要求）。 |
| Linux runtime artifact `/tmp/ofa_report_6h.json`, `/tmp/ofa_report_30h.json` | 執行產物 | report JSON（非入庫，runtime tmp）。 |

**0 修改**：sibling 的 `microstructure/{fill_sim,mm_sizing_run,data_loader,core}.py`（只 import）、
任何 production engine/risk/execution code、PG（純讀）、auth/lease/risk、硬邊界欄位、migration。

---

## 協調邊界（COORDINATION BOUNDARY，嚴格遵守）

- **Sibling 擁有**：CP-3 fill-sim（queue-position adverse selection）、maker-close reprice、
  maker_markout instrumentation。其檔 `program_code/research/microstructure/{fill_sim,
  mm_sizing_run,data_loader,core}.py`。其結論：**maker FEE WALL 是 MM 的 binding constraint**。
- **本 harness 做的**：READ-ONLY import 其 `data_loader`（load_trades/load_obtop/liquid_symbols/
  resolve_window/connect）+ `core`（clean_obtop/build_grid/ofi/fwd/GRID_STEP_S/BETA_SYM/
  MIN_TRADES）。先讀全兩檔確認 exact API 才用。本 harness 與 fill-sim **正交**：fill-sim 測
  「能不能以 maker 成交且不被逆選擇吃光」，本 harness 測「order-flow 訊號本身存不存在 +
  能不能負擔 ACT 的成本」。boundary 已寫進 `analysis.py` 的 MODULE_NOTE。
- 本 session 0 觸碰 sibling 檔（只 import）。

---

## STEP 0 — 資料就緒度（真實數字，非投影）

查 Linux PG（`ssh trade-core`，read-only）：

| 表 | rows | min ts | max ts | 跨度 |
|---|---|---|---|---|
| `market.trades` | **31,951,651** | 2026-06-16 10:25:35 (+02) | 2026-06-17 23:26:48 (+02) | ~37h |
| `market.ob_top` | **9,919,295** | 2026-06-16 10:25:34 (+02) | 2026-06-17 23:26:48 (+02) | ~37h |

> 註：時區為 +02:00（UTC+2）。tape 自 2026-06-16 傍晚起記錄，**遠多於「數小時」**——已有
> ~1.5 天、近 3,200 萬筆 trade。

**Top liquid symbols（最近 6h 窗，>=500 trades = sibling liquid_symbols 門檻）**：42 個 symbol 入選。
前 15：BTCUSDT(900k)、XPLUSDT(815k)、ETHUSDT(794k)、HYPEUSDT(397k)、ESPORTSUSDT(356k)、
NEARUSDT(330k)、HUSDT(309k)、BEATUSDT(290k)、ENAUSDT(290k)、ZECUSDT(259k)、XRPUSDT(256k)、
WLDUSDT(243k)、ASTERUSDT(210k)、SOLUSDT(193k)、SPCXUSDT(182k)。

ob_top 同窗覆蓋足夠（BTC 74k / XPL 74k / ETH 71k ... 取樣 ~250ms）。**BTCUSDT 在內**（sibling
core 的 beta 殘差化 BETA_SYM 必須）。

**結論：資料充足，可做初步 OFI/microprice 檢測。** 不是「太薄」。但仍是**單 regime**
（窗內 BTC 無真崩盤、單一日波動），跨 regime 驗證須累積。

---

## STEP 1 — 3 軸初步結果（leak-free）

跑兩窗交叉驗證：**6h（5.8M trade rows, 15 symbol）** + **30h（17.0M rows, 12 symbol）**。

### Axis 1 — OFI 可預測性 + 持續性

**(a) OFI 自相關（self-exciting vs white noise）**：mild 正自相關，**非 white noise** 但弱。

| 窗 | OFI@5s lag1 | OFI@10s lag1 | OFI@30s lag1 |
|---|---|---|---|
| 6h | 0.067 | 0.088 | 0.123 |
| 30h | 0.065 | 0.067 | 0.097 |

lag2/lag3 遞減（如 OFI@10s 6h: 0.066/0.044）。隨窗變長 lag1 上升 = 弱 self-exciting，符合
order-flow clustering 直覺，但量級小。

**(b) decile-binned 前向 mid 報酬（OFI@10s 預測 next 5s/15s）**：long-short decile spread
**< 1bp 且非單調**。

- 6h `OFI@10s→fwd5s`：top decile +0.13bp / bottom −0.25bp / **spread +0.39bp**（n=27,646，
  per-bin 非單調：bin6 +0.63bp 但 bin7/8 ≈0，無乾淨 ranking = 噪音）。
- 6h `OFI@10s→fwd15s`：spread +0.24bp（per-bin 更亂，bin2 −1.4bp 離群）。
- 30h：fwd5s spread +0.47bp / fwd15s +0.83bp（仍 <1bp）。

> **誠實點**：OFI@10s 對前向 mid 的 decile spread 是 sub-bp、非單調 = 接近無方向預測力。
> 這對齊 memory 的 14-軸結構鐵律與 sibling 的「OFI@10s beta-clean lead 微弱」。

**leak-free dual-track（naive vs leakfree）**：leak-free 前向 spread +0.39bp vs naive **回溯**
（已實現過去報酬）spread +6.94bp（fwd5s）/ +13.15bp（fwd15s）。兩者量級差一個數量級 =
**前向計算未誤引用未來 bar**（若有前視污染，前向會鏡像回溯的大數字）。leak guard 乾淨。

### Axis 2 — aggressor-flow clustering

| 指標 | 6h pooled | 30h pooled |
|---|---|---|
| buy-initiated notional % | 51.64% | 50.33%（≈平衡，無系統性單邊） |
| mean run length | 12.95 | 13.55（連續同號 trade 串 ~13 筆 = 強 clustering） |
| sign-autocorr lag1 | **0.835** | 0.847 |
| sign-autocorr lag5 | 0.565 | 0.583 |
| sign-autocorr lag10 | 0.413 | 0.428 |

trade-sign autocorr 非常高（lag1 ~0.83）= 強 **continuation**（aggressor flow 自我延續，符合
order-splitting / iceberg 行為）。per-symbol buy% 介於 44%（NEAR/ENA）~52%（BTC），多數 ~50%。

> **誠實點**：強 sign-autocorr **本身不是 tradable edge**——它是 tape 的機械特性（大單拆小單）。
> 要 tradable，需配合「可預測的前向 mid move」（即 Axis 1/3），而 Axis 1 的前向預測力 sub-bp。
> 高 continuation + 低前向 mid 預測力 = flow 自我延續但不領先價格。

### Axis 3 — microprice informativeness（informative，但成本內）

microprice = (bid·ask_size + ask·bid_size)/(bid_size+ask_size)；tilt@t=(micro−mid)/mid。

| 指標 | 6h | 30h |
|---|---|---|
| leak-free lead-lag IC（avg） | **+0.189** | +0.183 |
| naive 同期 IC（avg） | −0.146 | −0.140 |
| tilt decile **gross** fwd spread（avg） | +7.00bp | +8.97bp |
| **net − 自身 full-spread**（avg） | **−5.43bp** | **−5.55bp** |
| net 正的 symbol 數 | **1/15**（ENA +0.12bp=噪音） | **0/12** |

leak-free lead-lag IC 顯著為正（pooled +0.19，per-symbol 最高 XRP +0.40），naive 同期 IC 強負
（−0.15）→ 兩者背離 = **microprice tilt 真領先 mid（mid 朝 microprice 移動），且無前視污染**。
這是三軸中唯一有「真訊號」的軸。

**但成本內**：gross +7~9bp 是 **mid-to-mid** move；要 ACT 必 cross spread，真實成本=該 symbol
自身的 full-spread。逐 symbol 對照（6h）：

| sym | gross bps | own full-spread bps | net bps | lf IC |
|---|---|---|---|---|
| XRPUSDT | 12.62 | 13.88 | **−1.27** | 0.402 |
| NEARUSDT | 7.87 | 12.68 | **−4.81** | 0.359 |
| ENAUSDT | 15.19 | 15.06 | +0.12 | 0.325 |
| XPLUSDT | 12.66 | 13.94 | **−1.27** | 0.279 |
| WLDUSDT | 13.42 | 21.62 | **−8.20** | 0.262 |
| ASTERUSDT | 9.65 | 20.57 | **−10.92** | 0.204 |
| ESPORTSUSDT | 14.31 | 28.13 | **−13.82** | 0.196 |
| ZECUSDT | 2.65 | 5.15 | **−2.50** | 0.170 |
| ... | ... | ... | (全負) | ... |
| ETHUSDT | 0.54 | 1.39 | **−0.85** | 0.076 |
| BTCUSDT | −0.22 | 0.63 | **−0.86** | −0.055 |

> **決定性誠實點**：gross 預測的 mid move 幾乎逐 symbol 等於該 symbol 的 spread——這是典型的
> **bid-ask bounce 假象**：microprice 朝大-size 對側傾斜，mid 在隨後幾個 tick 機械地朝它移動，
> 但**全程 mid 在 spread 內反彈**，沒有「跨出 spread 的真方向 move」。看起來 edge 最大的
> （ESPORTS +14bp、WLD/ASTER）恰恰是 spread 最寬、最不流動的 symbol。tight-spread 的 BTC/ETH
> 幾乎無 lead（IC ~0 / 負）。30h 窗 **0/12 symbol** net 正，6h 唯一「正」是 ENA +0.12bp（噪音）。

---

## STEP 2 — 成本牆存活測試（決定性，mandate-critical）

| 訊號 | gross 預測 bps | 成本基準 | 存活？ | verdict |
|---|---|---|---|---|
| OFI@10s decile（fwd5s） | +0.39bp（6h）/ +0.47bp（30h） | flat taker 6bp / maker 4bp | **否** | `DOES_NOT_SURVIVE_COST_WALL` |
| OFI@10s decile（fwd15s） | +0.24bp（6h）/ +0.83bp（30h） | flat taker 6bp / maker 4bp | **否** | `DOES_NOT_SURVIVE_COST_WALL` |
| microprice tilt decile | gross +7~9bp，**net −5.4~−5.6bp** | cross-spread = 自身 full-spread | **否** | `ARTIFACT_BELOW_OWN_SPREAD` |

**`any_survives_taker = false`，`any_survives_maker_fee = false`**（兩窗一致）。

> harness 初版用 flat 6bp taker 牆對 microprice，誤報「SURVIVES_TAKER」。我修正了 fee-wall test：
> microprice 是 **cross-spread 訊號**，正確成本是**自身 spread**（不是 flat 6bp，對寬-spread alt
> 是低估）。修正後 microprice = ARTIFACT。這是 harness 正確性修復，非 scope 擴張。

---

## 治理對照

| 約束 | 狀態 |
|---|---|
| $0 OFFLINE / READ-ONLY | ✅ sibling `connect()` set_session(readonly=True)；0 寫 PG / 0 order / 0 auth/lease/risk |
| 不碰硬邊界（max_retries/live_execution_allowed/execution_authority/system_mode） | ✅ 0 觸碰（純研究腳本） |
| 不改 sibling 已 commit 的 microstructure 檔 | ✅ 只 import data_loader/core，0 修改 |
| leak-free（PIT realized / 禁 current-bar rolling / naive-vs-leakfree 雙軌） | ✅ 前向 [t,t+h)、OFI [t-w,t)、book_imb shift(1)、dual-track 確認無前視 |
| 不實作交易 / 最終 verdict 屬 QC | ✅ harness only，本報告標明 verdict 交 QC |
| 跨平台（無硬編 /Users /home） | ✅ `os.path` 向上推 srv root，不硬編 |
| 新腳本登 SCRIPT_INDEX | ✅ 已加 dated section + row |
| 注釋中文優先 + MODULE_NOTE | ✅ MODULE_NOTE 含 purpose/函數/依賴/硬邊界/協調邊界 |
| 不新增 singleton / 不新增 migration | ✅ 無 |

---

## 不確定之處（誠實）

1. **單 regime / 數十小時**：窗內 BTC 無真崩盤、單一波動環境。**harness 本身是耐久交付物；
   數值是指標性**，不是「edge 不存在」的決定性證明。**多 regime 驗證需 1-2 週累積**（recorder
   持續寫入，可重跑 `--since/--until` 切不同 regime）。
2. **microprice net 是 spread proxy**：用 mean full-spread 對照（cross-spread 成本）。更精確的
   cost 應走 sibling 的 fill-sim（queue position / partial fill / adverse selection），那是
   sibling 範疇。本 harness 的 net 是「跨 spread 立即成交」上界估計，已足以判 ARTIFACT。
3. **未做 OFI 的 per-symbol Fisher-t / bootstrap CI**：本軸 decile spread sub-bp 已遠低於成本牆，
   不值得再算顯著性（會是「不顯著的負/零」）；若 QC 要 IC+t 可直接用 sibling 既有
   `program_code.research.microstructure.harness`（已有 resid-IC + 非重疊 Fisher-t）。
4. **未碰 funding / liquidation / OI 等另類軸**：本任務範圍是 OFI/aggressor/microprice 三軸 only。

---

## Operator / QC 下一步

1. **QC 裁定**（最終 verdict 屬 QC）：本初讀傾向「三軸在當前資料皆 sub-cost-wall——OFI 方向預測
   sub-bp、aggressor clustering 不領先價格、microprice lead 真實但 net-of-spread 為負（bid-ask
   bounce 假象）」。與 14-軸結構鐵律 + sibling「maker fee wall 是 MM binding constraint」一致：
   **taker 路徑下 order-flow 訊號過不了成本牆**。
2. **多 regime 累積後重跑**（1-2 週）：`python3 helper_scripts/research/order_flow_alpha/analysis.py
   --since <ISO> --until <ISO> --out <path>`，切高波動 / 崩盤 / 趨勢 regime 看 microprice net 是否
   有任何 regime 翻正（理論上高波動時 mid move 可能 > spread）。
3. **若要追 microprice 軸**：唯一可能存活路徑是 **maker 側**（post passive 賺 spread 而非 cross
   spread 付 spread）——但這正是 sibling fill-sim 在測的 maker fee wall + queue risk。本 harness
   的 net-of-spread 為負已說明：以 taker 捕捉 microprice = 必虧。**handoff 給 sibling 的 fill-sim
   做 maker-side 評估，不重複建。**
4. **E2 審查**：本報告 + `analysis.py`（純研究腳本，無生產接線，無 migration，無硬邊界觸碰）。

---

## 關鍵 diff（fee-wall test 正確性修復，load-bearing）

microprice 初版誤用 flat 6bp 牆→誤報 SURVIVES。修正為 cross-spread 訊號用自身 spread：

```python
# axis3_microprice：加自身 full-spread + net-of-spread
spread_full_bps = float(np.mean((ask - bid) / mid)) * 1e4
net_of_spread = round(spread_bps - spread_full_bps, 4)  # net<0 = bid-ask bounce 假象

# fee_wall_test：microprice 用 net 判存活，非 gross
if sig.get("is_cross_spread_signal"):
    survives = bool(net is not None and net > 0)
    verdict = "SURVIVES_OWN_SPREAD" if survives else "ARTIFACT_BELOW_OWN_SPREAD"
```

verdict 因此從 `SURVIVES_TAKER`（錯）→ `ARTIFACT_BELOW_OWN_SPREAD`（對）。

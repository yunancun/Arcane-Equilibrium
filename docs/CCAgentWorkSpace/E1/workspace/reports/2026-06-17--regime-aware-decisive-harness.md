# Regime-Aware 決定性 Order-Flow Harness — 2026-06-17

> **STATUS: DONE_WITH_CONCERNS**（apparatus 建成並 Linux 實證；窗末已捕捉到一個真 vol
> event（BTC −186.8bp/1h），高波動 regime 已有 6h/5.0M rows 非低樣本 → 跑出**初步**決定性
> 結果：order-flow edge 在 high_vol 仍不過成本牆。但這是**單一 6 小時 vol 事件**的指標性讀數，
> 非跨多次 vol 事件的最終 verdict——最終屬 QC。）
>
> 角色：E1（後端開發／研究 harness 執行者）。$0 OFFLINE、READ-ONLY。不下單、不碰生產
> engine/risk/execution、不改 sibling 已 commit 的 microstructure 檔（只 import）。

---

## 任務摘要

把 order-flow-alpha harness 擴成 **REGIME-AWARE 決定性測試模式**：把 tape 的每小時標
calm / elevated / high_vol（leak-free PIT），對每個 regime 子集分別重跑 3 軸 + fee-wall，
回答 mandate 的決定性問題：**order-flow edge 是否在 HIGH-VOL regime（spread 變寬但 edge
可能更寬）超過成本牆？**（calm 已證不過——見前報告。）並做 current-state readout：tape
迄今捕捉了多少各 regime 小時、是否已有 high_vol 窗。

---

## 修改清單（footprint）

| 檔 | 動作 | 說明 |
|---|---|---|
| `helper_scripts/research/order_flow_alpha/regime.py` | **新增**（257 行） | leak-free 波動 regime 偵測器。READ-ONLY 多讀 `market.klines`，走 sibling `data_loader.connect`（read-only session）。 |
| `helper_scripts/research/order_flow_alpha/analysis.py` | 擴充 | 加 `--regime-split` 模式（`regime_split_decisive` / `_filter_tape_by_regime`）+ 恆計算的 `regime_readout`；MODULE_NOTE 記錄 regime-test；import 同目錄 `regime`。 |
| `helper_scripts/SCRIPT_INDEX.md` | 更新 1 row + 加 1 row | analysis.py 行補 regime-aware；新增 regime.py row（CLAUDE §七 要求）。 |
| Linux runtime artifact `/tmp/ofa_regime_split.json` | 執行產物 | regime-split report JSON（非入庫，runtime tmp）。 |

**0 修改**：sibling `microstructure/{fill_sim,mm_sizing_run,data_loader,core}.py`（只 import）、
任何 production engine/risk/execution code、PG（純讀）、auth/lease/risk、硬邊界欄位、migration。

---

## 1) REGIME 判定準則（明列門檻，leak-free）

兩條互補資料來源，皆 **shift(1) PIT**（t 的標籤只用 < t 的 bar，永不含 current-bar）：

- **(A) 長 backdrop — BTC 1h kline**（自 2026-04-05，n=1760 有效小時）：
  - `rv24_pit` = 24h trailing realized-vol = 過去 24 根 hourly log-return 的 RMS，
    `sqrt(mean(r²))` 用 **`.shift(1).rolling(24)`**（窗 = [t−24h, t−1h]，不含 t）。
  - percentile 門檻取「全部歷史 rv24_pit 分佈」的描述性界線（非用未來挑門檻）。
- **(B) 短粒度 spike — BTC 1m kline**：60m PIT baseline 的 |r| z-score
  = `(|r_t| − base_mean) / base_sd`，base 用 **`.shift(1).rolling(60)`**（不含 current bar）。

**regime 三選一觸發即升級，取最嚴（high > elevated > calm）**：

| regime | 觸發條件（OR） |
|---|---|
| **high_vol** | 24h trailing RV ≥ 歷史 **p80**（top quintile）<br>OR \|hourly return\| > **80bp**（≈BTC 歷史 1h \|ret\| p93）<br>OR 該小時內 1m vol-spike z-score ≥ **8.0**（≈1m \|r\| p99.85 稀有尾端） |
| **elevated** | 24h trailing RV ∈ **p50..p80**<br>OR \|hourly return\| > **40bp**（≈p79） |
| **calm** | 其餘（RV < p50 且無 spike） |

**Linux 實測歷史門檻**（n=1760h）：RV p50=**36.9bp** / p80=**47.6bp** / p90=55.8bp /
p95=68.4bp / max=122.7bp。\|hourly ret\| p80=42bp / p90=64bp / p95=89bp / max=347bp。
全 history regime 分佈：calm 677 / elevated 548 / **high_vol 535**（~30%）。

> **校正紀錄（透明揭露）**：spike z 門檻原設 4.0，Linux 實測 z≥4.0 是 1m |r| 的 **p99**
> （1099/106422 分鐘命中），而每小時 ~60 分鐘 → 幾乎每小時都至少有一筆 z≥4 → 該 OR clause
> 把 **45% 的小時誤標 high_vol**（1046/1760），違背「high_vol = 明顯尾端」本意。改成
> **z≥8.0**（≈p99.85，155/106422，~0.15% 分鐘）→ 變成「該小時內出現極端單分鐘暴動」的真稀有
> 事件。校正後 regime 分佈合理（如上）。**這個 spike 門檻是描述性常數，非用未來資料挑選**；
> 全部門檻在 report 與 `regime.py` 常數段明列（可由 QC 調整）。

兩來源皆可從錄製 tape（`market.trades`/`market.ob_top` 對齊到 BTC kline 小時）與
`market.klines`（1d/intraday 長 backdrop）計算——backdrop 自 2026-04-05，提供 ~73 天
歷史分佈作 percentile 基準。

---

## 2) REGIME-SPLIT 決定性結果（Linux 實證，30h 窗，top-12 symbol 含 BTC）

把 tape 每小時標 regime → 對每 regime 子集（按 trade ts 所屬小時繼承標籤）重跑 3 軸 +
fee-wall。**窗末已捕捉到一個真 vol event**，故 high_vol 不是空的：

| regime | n_hours | n_trade_rows | status |
|---|---|---|---|
| calm | 12 | 7,211,384 | ok |
| elevated | 11 | 4,460,346 | ok |
| **high_vol** | **6** | **5,035,008** | **ok**（非 low-power） |

partition 乾淨：16.71M / 16.97M rows 入 regime，~262k unlabelled = 窗首/尾 partial-hour
邊界（正確排除非誤分）。

### 決定性 fee-wall（per regime，per signal）

| signal | calm | elevated | **high_vol** | verdict（全 regime 一致） |
|---|---|---|---|---|
| OFI@10s decile spread (fwd5s) | 0.42bp | 0.73bp | **0.51bp** | `DOES_NOT_SURVIVE_COST_WALL`（<1bp vs taker 6/maker 4） |
| OFI@10s decile spread (fwd15s) | 0.06bp | 0.89bp | **0.33bp** | `DOES_NOT_SURVIVE_COST_WALL` |
| microprice tilt decile (gross) | 9.38bp | 8.23bp | **8.93bp** | `ARTIFACT_BELOW_OWN_SPREAD`（cross-spread 訊號，淨負） |

**microprice own-spread 細節（cross-spread 訊號的真實成本）**：

| regime | lead_ic_lf | ic_naive（對照軌） | gross_bps | net−own_spread | n_net_positive |
|---|---|---|---|---|---|
| calm | +0.183 | −0.139 | 9.38 | **−4.95** | 1/12 |
| elevated | +0.173 | −0.131 | 8.23 | **−7.04** | 0/11 |
| **high_vol** | **+0.190** | **−0.143** | **8.93** | **−4.62** | **1/12** |

**決定性 verdict：`HIGH_VOL_NO_EDGE_SURVIVES`**。直接回答 mandate「spread 變寬但 edge
可能更寬」的假設：**在這個 vol 事件，edge 沒有比 spread 更寬**——

- microprice gross 在 high_vol（8.93bp）≈ calm（9.38bp），**未隨波動放大**（lead-lag IC
  也幾乎不動 +0.19）。換言之 microprice tilt 在高波動下依然只預測「自身 spread 內的機械反彈」，
  不是更大的真方向 move。
- 唯一 net 由負轉正的是 **ENAUSDT（high_vol +1.24bp vs calm −2.77bp）**，但根因是
  **own_spread 從 17.07bp 壓縮到 12.57bp**（高波動下這 symbol 反而 spread 收窄），**非 edge
  放大**（gross 14.30→13.81 還略降）。1/12 symbol net 正，pooled 仍 −4.62bp = artifact。
- OFI decile 三 regime 全 sub-1bp，遠不到 6bp taker / 4bp maker 牆。
- Axis 2（aggressor clustering）三 regime 幾乎不變（sign-autocorr lag1 ~0.845、mean_run ~13）
  = order-splitting 機械特性，本身非 tradable（前向預測 sub-bp）。

**leak-free 確認**：所有 regime 的 microprice naive 同期 IC 為**負**（−0.13~−0.14）而
leak-free 前向 IC 為**正**（+0.17~+0.19）= 兩者背離 → 前向計算未誤引用未來 bar（無前視污染）。

---

## 3) CURRENT-STATE READOUT（tape 迄今捕捉的 regime）

tape 跨 ~37h（2026-06-16 08:25 UTC → 2026-06-17 21:45 UTC），對齊到 BTC 小時 regime：

- **regime 小時覆蓋（30h 分析窗內）**：calm **12h** / elevated **11h** / **high_vol 6h**。
- **已捕捉到 high_vol 窗？是。** 不是「awaiting vol event」。
- **high_vol 小時**（UTC）：2026-06-17 08:00 / 14:00 / 15:00 / 18:00 / 19:00 / 20:00。
  觸發來源：
  - `19:00` BTC hourly return **−186.8bp**（> 80bp 門檻，遠超）+ `15:00` **+98.5bp**；
  - `14:00`/`18:00` 由 1m vol-spike z≥8.0 觸發（單分鐘極端暴動）；
  - `20:00` 由 24h trailing RV 爬到 **p88.9**（> p80 top quintile）觸發。
  - 最劇烈一刻：`2026-06-17 20:00`（+02）一根 1m bar 動 **99.7bp，z=23.6**（60m baseline）。

**tape 起點（06-16 傍晚起）的 calm-dominated 假設部分成立**：窗首 06-16 全程是 elevated
（24h RV 在 p57..p73 之間，沒到 top quintile，也沒大 single-bar move），到 06-17 傍晚才出現
真 high_vol 尖峰。所以「tape 早段偏 calm/elevated、晚段才捕捉到 vol event」。

> apparatus 不再只是「ready, awaiting」——它已對**一個真 vol 事件**跑出初步決定性結果。
> 但僅一次 6 小時事件、單一方向（一次崩跌），跨多次 vol 事件（含上行 squeeze、不同
> 流動性背景）的穩健 verdict 仍需累積，屬 QC 範疇。

---

## 治理對照

| 項目 | 狀態 |
|---|---|
| $0 / OFFLINE / READ-ONLY | ✅ 純讀 PG（`connect()` set_session readonly=True）；0 寫、0 order、0 auth/lease/risk |
| 不碰生產 engine/risk/execution | ✅ 只新增 research 檔 + 改 research harness |
| 不改 sibling microstructure 檔 | ✅ 只 import `data_loader.connect`；sibling 5 檔 0 觸碰 |
| leak-free / PIT | ✅ RV 用 `.shift(1).rolling`、spike baseline `1 PRECEDING`、前向報酬 [t,t+h)、naive-vs-leakfree 雙軌背離為證 |
| 禁 current-bar rolling max/min | ✅ 無 rolling max/min；只 trailing RMS + z-score 皆 shift(1) |
| 沿用 microprice own-spread 修正 | ✅ 復用既有 `axis3_microprice` 的 `net_edge_minus_own_spread`，未 regress 成 flat 6bp |
| 跨平台無硬編路徑 | ✅ grep `/home//Users` = 0；用 `Path` 推算 srv root + 同目錄 sibling import |
| 新檔 MODULE_NOTE + 中文註釋 | ✅ regime.py 有 MODULE_NOTE；analysis.py MODULE_NOTE 補 regime-test 段 |
| SCRIPT_INDEX 登記 | ✅ 已更新 |
| 不下單 / verdict 屬 QC | ✅ apparatus-prep only，verdict 交 QC |
| 硬邊界（max_retries/live/system_mode）| ✅ 0 觸碰 |

---

## 不確定之處 / 限制

1. **單一 vol 事件、單方向**：捕捉到的 high_vol 是一次崩跌（−186.8bp）。上行 squeeze、不同
   流動性背景的 vol 事件可能行為不同。6h/5.0M rows 足以給「初步」讀數（非 low-power），但不是
   多事件的最終 verdict。
2. **regime 標籤以 BTC 為市場代理**：所有 symbol 繼承 BTC 小時 regime（系統性風險的合理代理），
   個別 alt 自身可能有非與 BTC 同步的 idiosyncratic vol（未細分；保持與 sibling beta=BTC 一致）。
3. **spike z 門檻 8.0 是經驗校正**：基於 BTC 1m |r| p99.85 選定，描述性常數，QC 可調。p80 RV /
   80bp / 40bp 門檻同理。沒有用未來資料挑門檻（用全歷史分佈描述性界線），但門檻選擇本身是判斷。
4. **ENAUSDT 在 high_vol net 正**是 spread 壓縮（17→12.6bp）而非 edge 放大；單 symbol、可能
   是該事件特有的流動性條件，不可外推為「ENA 有 microprice alpha」。
5. **kline backdrop 起點 2026-04-05**：percentile 分佈基於 ~73 天 intraday（外加 1d 回溯
   2024-06）；不含 2024/2025 真崩盤期 intraday（與前 beta-decomp 報告同一資料 gap），故
   percentile 界線反映的是近 2.5 月波動環境。

---

## Operator / QC 下一步

1. **QC 接 verdict**：regime-split 初步結論 `HIGH_VOL_NO_EDGE_SURVIVES`（單一 vol 事件）；
   是否升級為「order-flow edge 跨 regime 結構性不過牆」需多次 vol 事件累積後復跑同一 harness。
2. **apparatus 已 ready 且已 fire 一次**：每當新 vol event 進 tape，直接
   `python3 helper_scripts/research/order_flow_alpha/analysis.py --hours N --top-n 12 --regime-split --out <path>`
   即重跑（high_vol 子集會自動隨新事件增厚）。建議累積 ≥3 次獨立 vol 事件（含上行）再下定論。
3. **E2 審查**：本報告 + `regime.py`（新）+ `analysis.py`（擴充）+ SCRIPT_INDEX → E2 → E4
   回歸 → PM 統一 commit（強制鏈，不可跳）。

---

**CLI**：
```
python3 helper_scripts/research/order_flow_alpha/analysis.py \
    --hours 30 --top-n 12 --regime-split --out /tmp/ofa_regime_split.json
```

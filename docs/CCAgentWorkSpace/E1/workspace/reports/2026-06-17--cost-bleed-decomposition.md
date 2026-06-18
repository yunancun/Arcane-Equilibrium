# demo round-trip 成本分解 — 找互補 lever（cost-bleed diagnosis）

**日期**：2026-06-17 | **執行**：E1（research analysis）| **性質**：$0 OFFLINE 唯讀實證
**承接**：axis (a)（`2026-06-17--beta-decomp-tail-dependence.md`）揭 demo book ~−12.5 bps/trade
結構性 bleed、BTC-beta R²≈0 → operator 決定攻成本。
**範圍**：把 bleed 分解成 component、定位集中處、找**不與 sibling 重疊**的最大 headroom lever。
**只做 DIAGNOSIS，不提/不實作 fix**（交 QC/operator 選 lever）。
**Sibling 邊界**：parallel session 已 commit `a90ffc7b`（maker-close toward-touch reprice ~3bp
+ maker-fill adverse-selection markout instrument，新欄 `trading.fills.maker_markout_bps` via
V145）。本報告**不重算 markout instrument、不碰 maker 執行**。

**Runtime**：Linux trade-core，PG `trading_ai`（唯讀 session），Python 3.12 / numpy。
**腳本**（新增，唯讀研究）：`helper_scripts/research/cost_bleed_decomposition/decompose.py`
（已登 SCRIPT_INDEX）。復用 `program_code.ml_training.realized_edge_stats` 的 FIFO 配對 +
funding 歸因 SSOT（不 fork、不 drift），額外建 per-fill `(symbol, ts) → cost-meta` overlay。

---

## STEP 1 — 可用成本欄位盤點（誠實，what can / cannot be measured）

`trading.fills`（V145 後）成本相關欄位與 demo 自 2026-01-01 起的**填充率**（n=5174 demo fills）：

| 欄位 | 型別 | demo 填充 | 可量測性 | 備註 |
|---|---|---|---|---|
| `fee` / `fee_rate` | real | 5174 / 5085 非零 | **可** | fee_rate×10000=bps；neg fee（maker rebate）僅 28 |
| `liquidity_role` | text | **2680 / 5174（51.8%）** | **部分** | maker 1321 / taker 1323 / NULL 2494（**前置欄、舊 fill 無**） |
| `slippage_bps` | double | 1321（=taker 全部） | **可（taker only）** | **signed adverse**：正=穿越劣勢 |
| `reference_price` / `reference_source` | — | 2642 | **可** | taker 主要 `dispatch_last_fallback`（=dispatch 時 last-traded，**非乾淨 arrival mid**） |
| `maker_markout_bps`（sibling） | double | **僅 11–18** | **幾乎不可** | a90ffc7b 前向採集剛起步；歷史**無法回填**（無 mid@submit 記錄） |
| `realized_pnl` | real | 5174 | **可** | gross PnL 來源（含真實成交價） |
| `close_maker_attempt` / `close_maker_fallback_reason` | bool/text | 275 attempts | **可** | 區分 sibling 已涉 vs 未涉 |
| `exit_reason` / `fill_latency_ms` | text/bigint | 多數 | **可** | exit_reason → maker-eligibility 分類 |
| funding（`trading.funding_settlements`） | — | demo 156 結算 | **可（PIT-safe）** | realized only（**非 funding cap**），半開區間歸因 |

**誠實限制（不可乾淨量測）**：
1. **`liquidity_role` 只覆蓋 51.8% demo fills**——舊 fill（前置欄部署前）`role=NULL`。maker/taker
   share 與 per-leg slippage 只能在有 role 的子集算（leg overlay n=3583）。
2. **taker reference 是 `dispatch_last_fallback`（last-traded@dispatch），不是 arrival mid/BBO**。
   故 `slippage_bps` 量的是「成交價 vs dispatch 時 last」，**不是教科書 spread-crossing cost**。
   真 spread-crossing 需 arrival BBO，現有資料無乾淨對齊（mid_at_submit 僅 3 筆）→ **component (2)
   無法乾淨量測，誠實標 PROXY-ONLY**。
3. **`maker_markout_bps`（sibling component 3）只有 11 個 populated**——instrument 剛上線、前向採集，
   歷史無法回填。**現在拿它做決策無 power**（n=11，mean −5.19 favorable，但無統計意義）。

---

## STEP 2 — per-trade 成本分解 + 對賬（demo round-trips，n=3,215）

**分解恆等式**（SSOT = `realized_edge_stats._pair_round_trips`，FIFO + winsorize + funding 歸因）：

```
net_pnl_bps = gross_pnl_bps − (entry_fee_bps + exit_fee_bps) + funding_bps
```

**關鍵誠實點**：`gross_pnl_bps` 由 DB `realized_pnl`（真實成交價）算 → **執行 slippage 與
adverse selection 已內含於 gross**。slippage_bps / maker_markout_bps 是**診斷 overlay**（描述
gross 在執行層被侵蝕在哪），**不是可從 net 另扣的 line item**；另扣會雙重計入。故可加 component
只有三項：fee（顯式）、funding、residual(=gross)。

### Pooled 分解（n=3,215，cost-meta 對齊全集；碰撞 0）

| component | mean bps | 佔 bleed 量級 | 性質 |
|---|---|---|---|
| **(1) explicit fee（entry+exit）** | **−7.88**（entry −3.35 / exit **−4.53**） | **~77%** | 最大負 component |
| (4) funding（realized） | **+0.006** | ~0% | **可忽略** |
| (5) residual = gross_pnl_bps | **−2.35** | ~23% | entry/exit timing PnL（非成本，本身微負） |
| **= net** | **−10.23** | 100% | |
| **reconciliation gap** | **−1.8e-15** | — | **機器 epsilon，恆等式精確成立** |

> 註：pooled net −10.23 bps 略異於 axis (a) 的 −12.21 bps，因 axis (a) 用 BTC-aligned 2,451
> 子集、本表用 cost-meta 對齊 3,215 全集；**同一 demo book，方向與量級一致**。

### component (2)/(3) overlay（診斷，非可加）
- **(2) taker slippage（PROXY，vs dispatch-last）**：n=1781，mean **−1.30 bps、median 0.0**
  → **負=favorable**，taker 執行**平均並未**因穿越 spread 而 bleed（甚至略優於 dispatch-last）。
  **spread-crossing 不是 bleed 來源**（在此 proxy 下）。
- **(3) maker markout（sibling instrument）**：n=11，mean −5.19 bps → **n 太小無 power**，不可解讀。

---

## STEP 3 — 切片（bleed 集中在哪）

### by strategy（mean net / fee / funding / gross-residual / total 貢獻）

| strategy | n | net bps | fee bps | funding bps | gross-resid bps | **total net bps（對總 bleed 貢獻）** |
|---|---|---|---|---|---|---|
| **grid_trading** | 2,082 | **−12.53** | −7.88 | +0.02 | −4.67 | **−26,095（85% of total bleed）** |
| ma_crossover | 893 | −3.95 | −7.30 | −0.001 | **+3.35** | −3,531 |
| funding_arb | 135 | **−20.55** | **−11.72** | −0.165 | −8.67 | −2,774 |
| bb_reversion | 64 | −13.70 | −8.69 | 0 | −5.01 | −877 |
| bb_breakout | 41 | **+9.46** | −6.77 | 0 | **+16.23** | +388（唯一正） |

**讀法**：
- **grid_trading 是 bleed 主體（85%）**：fee −7.88 + gross-residual −4.67。**fee 比 timing PnL 還大**。
- **ma_crossover：gross-residual 是正的（+3.35），但 fee −7.30 把它拖成淨負**——這條策略**有
  微弱 raw edge，純被 fee 吃掉**（最值得 fee lever 救的策略）。
- funding_arb：net 最差（−20.55），fee 最重（−11.72，turnover 高），且 gross-residual −8.67 真負
  → 結構壞 + 高成本，**fix 與 kill 都該考慮**（fee lever 救不回 −8.67 的負 raw edge）。
- **funding component 全策略可忽略**（最大 funding_arb 也只 −0.165 bps）→ **funding/holding 不是 lever**。

### by symbol（top bleeders，按 total_net 對總 bleed 貢獻排序）

| symbol | n | net bps | fee bps | gross-resid bps | total net bps |
|---|---|---|---|---|---|
| （多 grid 幣，fee ~10 bps）CHIPUSDT | 30 | −28.56 | 10.31 | −18.25 | −857 |
| GALAUSDT | 62 | −13.44 | 10.66 | −2.78 | −833 |
| ADAUSDT | 54 | −15.10 | 9.77 | −5.33 | −815 |
| DOGEUSDT | 91 | −8.89 | 9.03 | **+0.13** | −809 |
| INJUSDT / AXSUSDT / PIEVERSEUSDT | — | −26~−51 | 7–17 | −18~−33 | −710~−753 |

→ bleed **不集中單一 symbol**（grid 跑 85 symbol）；高 fee（~10 bps/RT）跨幣普遍。
PIEVERSEUSDT（fee 17.5 bps）= 高 turnover / 低流動性幣，per-symbol kill 候選。

### maker vs taker leg share（leg overlay n=3,583，role 已知子集）

| | maker | taker | share |
|---|---|---|---|
| 全 leg | 1,775 | 1,782 | ~50/50 |
| **entry leg** | **1,200（89%）** | 154 | entry 幾乎全 maker（2.10 bps cheap） |
| **exit leg** | 121（9%） | **1,169（91%）** | **exit 幾乎全 taker（6.00 bps expensive）** |

**這解釋了 entry_fee（−3.35）< exit_fee（−4.53）的非對稱**：**bleed 集中在 close 腿付 taker fee**。

---

## STEP 4 — 互補 lever 排名（不與 sibling maker-reprice/markout 重疊）

### Lever 1 — taker close 腿改走 maker 路由（**最大、但須誠實標 sibling 已覆蓋多數**）

**機制差異（與 sibling 不重疊的定義）**：sibling 修「**已嘗試** maker close 但 fill 失敗 →
toward-touch reprice」（close_maker_attempt=true 的 168 筆：139 timeout_taker + 29 postonly_reject）。
本 lever 看「**從未嘗試** maker、直接走 taker 的 close 腿」（close_maker_attempt=false）。

taker exit 腿（n=1169）拆解：

| 類別 | n | avg fee | 是否 addressable | 是否 sibling 已涉 |
|---|---|---|---|---|
| close_maker_attempt=**false**，exit_reason **maker-eligible** | **625** | 5.90 | **是（應掛 maker 卻走 taker）** | **否（互補 headroom）** |
| close_maker_attempt=false，market-only/其他 | 245 | 6.68 | 否（安全腿正確 taker） | 否 |
| close_maker_attempt=false，exit_reason=NULL | 131 | 5.86 | 不明 | 否 |
| close_maker_attempt=**true**（timeout/reject） | 168 | 5.50 | — | **是（sibling 領域）** |

**maker-eligible 白名單**（`maker_price.rs:104` 親讀）：grid_close_short/long、bb_mean_revert、
ma_reverse_cross、bw_squeeze、pctb_revert、phys_lock_gate4_giveback/stale_roc_neg。

**可尋址 bps 上限（理想，未計成交率折損）**：fee delta = median(taker 5.5 − maker 2.0) = **3.5 bps/leg**。
625 eligible legs / 3215 RT × 3.5 = **~0.68 bps/RT**（fee only；另省 taker 穿越，但 proxy 顯示
taker slippage 已 ~0，故 spread 增益小）。

**⚠️ 誠實降溫（決定性）**：這 625 **絕大多數是歷史 pre-feature backlog**。週分佈顯示 close-maker
feature 約 2026-05-18 上線後 `maker_eligible_taker_no_attempt` 由 ~170–220/週**驟降到 4–21/週**，
而 `maker_attempted` 同步上升（最新 06-15 週 83 attempted）。**556 / 625 在 feature 上線前**。
→ **forward 互補 headroom 遠小於 625 raw**：近 4 週合計僅 ~59 eligible-no-attempt。**sibling 的
maker-close 工作已是對的 lever 且已部署**；剩餘是小量 routing 殘餘（每週個位～雙位數），值得查
「為何近期仍有 eligible close 未 attempt maker」但**bps 量級小**。

### Lever 2 — ma_crossover fee-drag 救援（**真正的互補 headroom，sibling 未涉**）

ma_crossover **gross-residual = +3.35 bps（正 raw edge）**，被 **fee −7.30** 拖成 net −3.95。
這不是執行 reprice 問題（sibling 領域），是**策略級 turnover / 路由問題**：若能把 ma_crossover 的
fee 從 7.3 降到 maker-level（~4 bps 雙腿），net 可由 −3.95 翻正。
**可尋址 ~3 bps/RT × 893 RT**（n 不小）。**sibling 完全未涉**（sibling 只動執行層 reprice，不動
per-strategy 路由/turnover 策略）。**這是頭號真互補 lever**——前提是 ma 的 entry/exit 能耐 maker 延遲。

### Lever 3 — funding_arb / 高 fee 低 raw-edge symbol 的 kill-or-fix（互補，治理層）

funding_arb（net −20.55、fee −11.72、**gross-resid −8.67 真負**）與 PIEVERSEUSDT（fee 17.5）：
**fee lever 救不回負 raw edge**——這些是**結構性 cost-bleeder，kill 候選**而非 reprice 候選。
sibling 的執行優化對「raw edge 本身負 + 高 turnover」無能為力。**可尋址 = 停掉這些 cell 直接消除
其 total 貢獻**（funding_arb −2,774 / PIEVERSE −710 bps）。屬 QC/risk 治理決策。

### NOT levers（誠實排除）
- **funding / holding cost**：pooled +0.006 bps，全策略 |funding| < 0.17 bps。**不是 bleed 來源**，
  shorts 並未顯著付 funding into bleed（demo 52 paid / 51 received，近平衡）。
- **taker spread-crossing slippage**：proxy mean −1.30 bps（favorable）。**不是 bleed 來源**。
- **maker adverse-selection markout**：n=11 無 power；且這是 **sibling 的 instrument**，不重算。

---

## 綜合結論（交 QC/operator 選 lever）

1. **bleed 主成分 = 顯式 fee（−7.88 bps，~77%），集中在 close 腿付 taker（exit 91% taker @ 6 bps）**。
   timing PnL（gross-residual）只 −2.35 bps。funding ≈ 0。spread-crossing slippage 平均 favorable。
2. **sibling 的 maker-close 方向正確且已部署**：feature 上線後 eligible-but-taker close 驟降、
   maker_attempted 上升。Lever 1（taker→maker close 路由）的**大數字 625 是歷史 backlog，forward
   headroom 小**（近月個位～雙位數/週）。**這條 sibling 已在拉，互補空間有限**——誠實標明。
3. **真正的互補 headroom（sibling 未涉）= 策略級而非執行級**：
   - **Lever 2（頭號）**：ma_crossover **有正 raw edge（+3.35）被 fee 吃掉**，per-strategy fee/turnover
     優化可翻正，~3 bps/RT × 893 RT，sibling 不涉。
   - **Lever 3**：funding_arb / 高-fee-負-raw-edge symbol = **kill 候選**（fee lever 救不回負 raw
     edge），治理層決策。
4. **grid_trading 是 bleed 主體（85%）**：fee −7.88 + gross-residual −4.67 兩者都負。fee 部分與
   sibling close-maker 重疊；gross-residual −4.67 的負 raw edge 是**策略 alpha 問題**（非成本 lever
   可解），呼應 axis (a)「扣 BTC 後逐筆執行層系統性負」。

---

## 資料限制（明確）
- `liquidity_role` 僅覆蓋 51.8% demo fills（舊 fill role=NULL）→ maker/taker share 與 per-leg
  overlay 只在 role 已知子集（n=3583 legs）；NULL-role fill 不入 share 統計。
- taker slippage 是 vs `dispatch_last_fallback`（last-traded@dispatch）非 arrival mid/BBO →
  **component (2) spread-crossing 為 PROXY-ONLY**，不可當教科書 spread cost。
- `maker_markout_bps`（sibling component 3）n=11 無 power，歷史不可回填；本報告**不重算**（直接讀）。
- net −10.23（cost-meta 全集）vs axis (a) −12.21（BTC-aligned 子集）：同 book、子集差異，方向一致。
- Lever bps 估計皆為**fee-delta 上限**（未計 maker 成交率折損 / 策略對掛單延遲的耐受度）→ 實際
  增益 < 上限；交 QC 做 fill-rate-adjusted 與策略可行性評估。

---

## Operator 下一步（建議，非自行決策）
1. **交 QC 選 lever**：本報告排除 funding/spread-crossing/markout 作為 lever；推薦聚焦
   **Lever 2（ma_crossover fee-drag 翻正）** 為頭號互補 lever（sibling 未涉、n 充足、有正 raw edge）。
2. **明確標示給 PM**：Lever 1（taker→maker close 路由）的大數字是歷史 backlog，**sibling 已覆蓋此向
   且已部署**，forward 互補空間小——不應重複投入該向。
3. **Lever 3（kill-or-fix）**屬 risk/QC 治理：funding_arb / 高-fee-負-raw-edge symbol 的停用評估。
4. 若要量測真 spread-crossing（component 2 升級非 proxy），需採集 arrival BBO（與 sibling
   mid@submit instrument 同類，屬執行層採集，非本 axis）。

---
**產物**：
- 報告：本檔。
- 腳本：`helper_scripts/research/cost_bleed_decomposition/decompose.py`（唯讀，已登 SCRIPT_INDEX）。
- ephemeral artifact（Linux，非永久）：`trade-core:/tmp/openclaw/cost_bleed/decompose.json`。

# QC 取數報告 — Move 2：bb_reversion maker 化 fill_sim 重放（證據盤點）· 2026-07-10

**Agent**: QC（本輪角色=QC/MIT 混合取數員；只取數與盤點，不設計、不裁決）
**範圍**: (a) bb_reversion cell 現狀 30d/60d；(b) maker/taker markout 按策略分解；(c) fill_sim harness 與 L1 數據盤點；(d) bb_rev 信號可重建性與 L1 對齊率；(e) 費率經濟學親算。
**邊界**: 全程 read-only（Mac repo HEAD 1a3ecdd57 + `ssh trade-core` psql SELECT only）；唯一寫入=本報告檔。
**黑名單檢查**: 無方法提案，無黑名單觸碰。
**格式註**: 本報告為證據供數（非策略裁決），以任務 (a)-(e) 結構為主幹，8 節模板中「建議」節以 findings 清單代替 PROCEED/REJECT（裁決留 PM/operator）；此為 QC 自選之等價結構。

---

## 0. Executive Summary

1. **bb_reversion 的 gross 正是 30d-局部現象**：30d gross +8.86bps（29 closes，與 07-09 快照 +9.06/28 一致），但 31-60d back window 單獨為 **−7.07bps**（29 closes），60d 合併僅 +3.66bps。**maker 化算術在 60d 窗下即使 markout=0 也是負的（−0.34bps）**——「+0.3bps/RT」宣稱完全押注 30d 窗口的 gross 持續性。
2. **「maker markout −2.37bps (n=3)」需更正為 n=1**：30d bb_rev maker fills=3，其中僅 1 筆有非 NULL markout；且 DB `maker_markout_bps` 語義=fill 價 vs 提交時 reference（reference_source 異質），**不是 60s/300s post-fill markout**——後者在 DB 不存在，須從 L1 重算。
3. **重放可行性為正面事實**：`market.l1_events` 實際 332.4M 行（TimescaleDB hypertable 21 chunks/21GB；此前 n_live_tup 4.3M 是 stale stats）、覆蓋 2026-06-20→07-10、85 symbols；bb_rev 25 個信號 episodes **100% 對齊 L1（±60s）**；fill_sim `--horizons` 已支援任意秒數（60,300 免改碼）。
4. **樣本紀律乾淨但濃度高**：fills 無 F1 式偽複製（每日 closes==distinct entry_context_id）；但 top-day 2026-07-06 佔 30d gross 52%（E3 top-day≤50% 邊緣違反）、佔 60d gross 84%；25 episodes 經同分鐘跨 symbol 聚類後 ≈14 個獨立時間簇。

---

## (a) bb_reversion cell 現狀（30d / 60d / all-time）

### a.1 窗口彙總（FACT；查詢時點 2026-07-10 ~18:00+02）

| 窗 | closes | gross USDT | notional | gross bps | fees USDT (全腿) | net USDT | net bps | W/L | sign p(單邊,未修正) |
|---|---|---|---|---|---|---|---|---|---|
| 30d | 29 | +22.80 | 25,742 | **+8.86** | 27.32 (58 legs) | −4.52 | **−1.76** | 20/9 | 0.031 |
| 60d | 58 | +13.98 | 38,225 | **+3.66** | 41.51 (122 legs) | −27.53 | **−7.20** | 36/22 | 0.044 |
| 31-60d（差分） | 29 | −8.82 | 12,483 | **−7.07** | — | — | — | 16/13 | — |
| all-time | 67 | +13.85 | 38,644 | +3.58 | 42.49 (151 legs) | −28.64 | −7.41 | 37/30 | 0.232 |

- 與 07-09 MIT 快照（28 closes/+9.06/−1.54）一致（窗口滑動 +1 close）。
- **60d 窗把 gross 砍半以上；31-60d 單獨看是 gross 負**。gross 正不是該 cell 的穩態性質。
- fee 歸屬沿 MIT 同法（同窗全 fills fee 合計；窗口邊界 entry/close 錯配有小誤差，INFERENCE）。

可重跑：
```
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT count(*), sum(realized_pnl), sum(qty*price), sum(realized_pnl)/sum(qty*price)*1e4 FROM trading.fills WHERE strategy_name='bb_reversion' AND engine_mode IN ('demo','live_demo') AND ts>now()-interval '30 days' AND realized_pnl<>0\""
```

### a.2 Distinct-entry 紀律（R3 教訓前置檢查）— PASS（FACT）

60d 逐日：**每一天 closes 數 == distinct entry_context_id 數**（29 個交易日，單日最多 6 筆、最多 5 symbols）。無 NEAR-F1 式 ×2529 偽複製。60d 58 closes 全部成功 join 到唯一 entry（LEFT JOIN 無孤兒）。

### a.3 按日分佈與濃度（FACT）

- 60d 分佈於 29 個交易日；**2026-07-06 單日 +11.79 USDT = 30d gross 的 52% / 60d gross 的 84%**（4 closes、4 symbols 同日）。次極端 2026-06-08 = −12.41 USDT。
- **交易空窗 2026-06-20→07-02 零 close**（soak isolation 06-29 起可解釋後半；06-20→06-28 前半原因未查——open question）。

### a.4 Symbol 分佈（FACT）

- 30d：16 symbols / 29 closes，單 symbol 最多 3。正尾由小樣本 symbol 貢獻：FIL +41.85bps(n=2)、NEAR +34.86(n=2)、SUI +31.28(n=1)、DOGE +24.42(n=1)；負尾 APT −24.22(n=2)、ATOM −20.61(n=2)。
- 60d：20 symbols；12 正 8 負；OP −22.06(n=5)、XRP −35.16(n=1)。

### a.5 Win/Loss 不對稱（FACT）

| 窗 | avg win bps | avg loss bps | median bps | min | max |
|---|---|---|---|---|---|
| 30d | +20.53 | −17.42 | +6.52 | −62.80 | +68.63 |
| 31-60d | +11.00 | −20.04 | +1.78 | −142.98 | +46.40 |

31-60d 的 W/L 比不對稱翻向不利（贏小輸大 + 一筆 −142.98 尾損）——該 cell 的正 gross 依賴 30d 窗內的贏幅優勢，非結構性。

### a.6 其他 cell 屬性（FACT）

- 持倉時長（60d，entry→close）：p25 0.5 min / **p50 0.8 min** / p75 4.0 / p90 10.0 min → 60s/300s markout 窗與實際 RT horizon 同量級。
- Exit reason 60d：`phys_lock_gate4_giveback` 42/58（72%）、`bb_mean_revert` 11、`grid_close_short` 4（**在 bb_reversion strategy_name 下出現 grid 標籤，資料品質 INFO**）、stale_roc 1。
- Leg 結構 30d：entry 29 筆全 taker（fee 5.5bps/leg）；close 26 taker + 3 maker（2.0bps/leg）。實付 RT fee = 27.32/25,742 = **10.61bps/RT**。

---

## (b) maker vs taker markout 按策略分解

### b.1 ★ 語義更正（HIGH/HIGH，FACT）——DB 欄位不是 60s/300s markout

`trading.fills.maker_markout_bps` 由 Rust `split_markout_by_role`（`rust/openclaw_engine/src/event_consumer/execution_fill_helpers.rs:27-42`）寫入，= `adverse_slippage_bps(is_buy, fill_price, reference_price)`：**fill 價 vs 提交時 reference 的帶號差（正=劣於 reference）**，與 taker 的 `slippage_bps` 同一條公式、按 role 分流兩欄。reference 來源異質（60d demo/live_demo）：

| reference_source | role | n | avg markout | avg slippage |
|---|---|---|---|---|
| bbo_same_side | maker | 632 | −10.88 | — |
| dispatch_last_fallback | maker | 586 | −4.13 | — |
| mid_at_submit | maker | 17 | −1.98 | — |
| dispatch_last_fallback | taker | 795 | — | −0.29 |
| close_maker_fallback | taker | 310 | — | −1.37 |
| bbo_same_side | taker | 45 | — | −7.85 |

含義：(i) 負值主體是「fill 落在提交時參考價之下（買）/之上（賣）」= 掛單 offset + 成交前價格漂移的混合，**不能單獨解讀為 adverse selection 成本**（offset 部分是 spread 捕捉，漂移部分才是逆選擇）；(ii) 真 post-fill 60s/300s markout（fill 後 mid 走勢）**DB 無此欄**，必須從 `market.l1_events` 重算（fill_sim `measure_adverse_selection` 即為此，現行 default horizon 5/15/30s，`--horizons 60,300` CLI 直接支援）。此語義釘死後，Stage 2 (b) 的「per-strategy maker markout」各值應重新標註為「fill-vs-submit-reference 讀數」。

### b.2 Per-strategy 分解（demo+live_demo；FACT）

| strategy | 窗 | maker fills | **非NULL markout n** | mean | median |
|---|---|---|---|---|---|
| flash_dip_buy | 30d | 100 | 100 | −12.68 | −10.20 |
| grid_trading | 30d | 349 | 96 | −2.45 | −0.30 |
| funding_arb | 30d | 37 | 18 | −13.48 | −5.10 |
| ma_crossover | 30d | 72 | 17 | −1.34 | 0.00 |
| **bb_reversion** | 30d | **3** | **1** | **−2.37** | −2.37 |
| bb_breakout | 30d | 1 | 0 | — | — |
| grid/ma/bb_breakout/bb_rev | >30d 前 | 1,192/542/34/2 | **全 0** | — | — |

**n=3 的原始出處**：Stage 2 QC 報告表格的「bb_rev −2.37(n=3)」中 n=3 是 30d maker fill 筆數；非 NULL markout 只有 **1 筆**，−2.37 是單筆讀數。**更正：bb_rev maker markout 有效 n=1，非 n=3。**

**能擴到多少**：
- 從 realized fills 擴：不可能——bb_rev all-time maker fills 僅 5 筆（30d 3 + 更早 2，更早的 markout 全 NULL，V145 部署邊界）。
- 從 L1 重放擴（正解）：L1 窗內 bb_rev 有 16 個 realized round trips（兩腿決策時戳齊全）+ 25 個信號 episodes（見 (d)）+ 22,774 個信號分鐘可作 quote-trial 候選。fill_sim 可產生千級 quote-trials，但**證據單位必須按 episode 聚類（≈25，跨 symbol 同分鐘聚簇後 ≈14 獨立時間簇）**，per-trial 行數不是 n_eff（F1 教訓）。episode 累積速率 ~1.2/day → n_eff≥30 約需再錄 ~1 週。

### b.3 Taker 側（對照；30d bb_rev）

entry taker slippage mean −6.07bps（負=優於 reference）、close taker −1.77：**realized gross +8.86 已內嵌 taker 執行的有利價差**（買跌時市價單相對滯後 reference 成交在更低價）。maker 化後此利益不保留（fill-conditional），是 (e) 算術的結構性偏置來源之一。

---

## (c) fill_sim harness 盤點

### c.1 代碼位置（Mac repo；FACT）

`srv/program_code/research/microstructure/`：
- `fill_sim.py`（2,796 行）— 事件驅動 queue 狀態機 fill 模擬器。核心：`simulate_symbol()`（fill_sim.py:152，固定 cadence 兩側掛 BBO join 的 hypothetical 掛單，back-of-queue 保守預設，FILL/NO_FILL/ADVERSE_THROUGH 三態）、`measure_adverse_selection()`（fill_sim.py:361，beta-residual post-fill mid 移動）、`run()`（fill_sim.py:2464）。NET = half_spread − adverse − 2×maker_fee（MAKER_FEE_BPS=2.0 無 rebate）。內建：queue front/mid/back sweep、fee sensitivity grid（2.0/1.0/0.5/0.0/−0.5）、walk-forward holdout、MIN_FILLS_FOR_SIGNIF=30 顯著性抑制、crossed-row/ts-floor 兩段 fail-loud 過濾（`--clean-since` 預設 2026-06-17T14:25+02）。
- `data_loader.py` — read-only PG loader（set_session readonly；**硬邊界=只 SELECT market.trades/ob_top/l1_events**）。
- `core.py` — leak-free 純函數（beta rolling-30min shift(1)、GRID_STEP_S=5）。
- `harness.py` — CP-1/2/3 runner；`fill_sim_history.py` — 多窗 JSON reducer（跨 regime 重現性 scorecard）；`fee_path.py` — VIP fee ladder 情境 reducer（VIP0 2.0 → VIP1 1.8bps/side @$10M 30d volume）；`mm_sizing_run.py`。

### c.2 L1 數據位置與覆蓋（FACT）

- **表**：`market.l1_events`（TimescaleDB 2.26.1 hypertable，21 chunks，chunks 合計 **21GB**；parent pg_stat n_live_tup=4.3M 是 stale——count(*) 實測 **332,432,554 行**。記取：n_live_tup 不可靠鐵則再驗）。
- Schema：`ts, symbol, best_bid, bid_size, best_ask, ask_size, update_id, seq, is_snapshot`；PK `(symbol, ts, update_id)` + `ts DESC` idx。
- **覆蓋：2026-06-20 02:18+02 → 2026-07-10 17:54+02（~20.6 天），85 symbols**。maker-nogo 的「34M L1」= 兩個 run 窗（fast3h 1.84M + winA72h 31.99M）從本表讀出的切片，窗口（07-03→07-06）仍在現存留存內。
- `market.trades`：282,578,130 行，2026-06-16 10:25+02 → now（aggressor flow，queue 模擬必需）。
- bb_rev 15 個信號 symbols 全部在 85 之列，L1 行數 2.7M（ATOM）～26.1M（BTC）。
- Run artifacts（maker-nogo 原件仍在）：trade-core `/home/ncyu/qc_fillsim_run_20260706/fillsim_{fast3h,winA_recent72h}.json` + CSV + logs；repo `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--fillsim_*_per_symbol.csv`。

### c.3 「對 bb_rev 歷史信號做 PostOnly 重放」需要 harness 改什麼（盤點，不改）

| # | 現狀 | 需改 | 規模評估 |
|---|---|---|---|
| 1 | 掛單觸發=固定 cadence 網格（`place_ts=np.arange(t0,t1,step)`），兩側恆掛 | 改為外部 placement 清單（symbol, ts, side）驅動；建議走 `--placements <csv>` 輸入檔，由獨立 read-only SQL 從 trading.signals/fills 匯出——**維持 data_loader「只讀 market.*」契約不變** | 小-中（單函數入口改造） |
| 2 | side 恆雙側 | OpenLong→bid / OpenShort→ask 單側 | 小 |
| 3 | horizon 5/15/30s | `--horizons 60,300` **已支援，免改碼**（CLI 任意秒數） | 零 |
| 4 | 產出=per-quote NET（半價差−逆選−費），非策略 RT PnL | 若要 cell 級 maker 化裁決，需兩腿重放：entry 用信號 ts、exit 用 **realized close ts**（16 個 L1 窗內 RT 兩腿時戳齊全）。exit 政策 72% 是 phys_lock giveback（tick 級動態），**不可獨立再生**——重放定位=execution-counterfactual（同決策時點換執行方式），非 strategy-counterfactual | 中 |
| 5 | 顯著性單位=per-cell n_fills | 需加 episode/時間簇聚類（≈25 episodes/14 簇為 n_eff 單位；同分鐘跨 symbol 齊發視為 1 簇） | 小（reduce 層） |
| 6 | queue sweep、fee grid、walk-forward、crossed 過濾 | 原樣複用 | 零 |

---

## (d) bb_rev 信號可重建性與對齊率

### d.1 信號來源（FACT）

`trading.signals`：bb_reversion **24,665 行，2026-04-30→2026-07-10，24 symbols**（retention 未截斷，比 L1 長）。Schema：`ts, signal_id, symbol, strategy_name, timeframe(1m), signal_type(OpenLong/OpenShort), strength, context_id, details`。**details 全 NULL**——信號無價格/band 載荷，重放的價格錨必須取信號 ts 時的 L1 BBO（與 fill_sim 的 BBO-join 掛法天然一致）。blocked ledger（cost_gate probe_ledger / risk_verdicts）是另一路信號級母集（71,207 行 4 symbols 高度重複），與 signals 表近 1:1（FIL 3,556≈3,557、ARB 2,270≈2,271），非獨立來源。

### d.2 L1 窗內信號結構（ts ≥ 2026-06-20 02:19+02；FACT）

- 原始行：**22,774**（OpenLong 22,767/11 symbols + OpenShort 7/7 symbols）。極度偏斜：ETH 7,470、ATOM 5,334（單日）、OP 4,127、FIL 3,557、ARB 2,271 = 99.93%；其餘 10 symbols 各 1-4 行。分鐘級連發（條件持續即每分鐘 fire）。
- **Gap-dedup（30min 與 120min 同值）→ 25 episodes**：ETH 3、FIL 3、BTC 3、OP 2、ARB 2、APT 2、DOT 2、ATOM 1、其餘 7 symbols 各 1。
- **跨 symbol 同分鐘聚簇**：07-06 14:03-14:05（ATOM/OP/FIL/ARB 齊發）、07-06 23:12（DOGE/BNB/FIL）、07-08 03:39（ARB/OP/AVAX/FIL/DOT）→ **獨立時間簇 ≈14**。任何統計檢定的 cluster 單位應取此。
- OpenShort 全部出現於 07-06 之後（新行為）；短側任何推論須 down-beta/regime 標註（06-03 鐵則）。

### d.3 對齊率（FACT）

**25/25 episodes = 100%** 在 ±60s 內有同 symbol L1 事件（逐 episode EXISTS 實測）。fills 側：60d 58 個 RT 中 **16 個**（07-03→07-10）兩腿皆落 L1 窗內可重放；06-20 前的 42 個 RT 永久不可 L1 級重放。

可重跑（episode 對齊）：
```
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"WITH s AS (SELECT symbol, signal_type, ts, lag(ts) OVER (PARTITION BY symbol, signal_type ORDER BY ts) prev FROM trading.signals WHERE strategy_name='bb_reversion' AND ts >= '2026-06-20T02:19:00+02'), ep AS (SELECT symbol, signal_type, ts FROM s WHERE prev IS NULL OR ts-prev > interval '30 minutes') SELECT ep.*, EXISTS (SELECT 1 FROM market.l1_events e WHERE e.symbol=ep.symbol AND e.ts BETWEEN ep.ts-interval '60 seconds' AND ep.ts+interval '60 seconds') FROM ep ORDER BY ts\""
```

---

## (e) 費率經濟學親算（maker 化 net 的算術）

### e.1 「+0.3bps/RT」宣稱的成分分解（恒等式核驗）

Stage 2 的 maker RT 成本 ~8.7bps = 2×2.0（maker fee 兩腿）+ 2×2.37（markout 兩腿）= 8.74；net = 9.06 − 8.74 = **+0.32bps** ✓（算術成立）。但輸入端兩處不保守：markout −2.37 是 **n=1 單筆**、且語義是 fill-vs-submit-reference 非 post-fill 逆選擇成本（§b.1）。

### e.2 敏感性（markout 成本/腿 ∈ {0, 2.37, 7.57}；gross 三檔）

| gross 來源 | markout=0 | markout=2.37/leg | markout=7.57/leg（aggregate 讀數） |
|---|---|---|---|
| 30d 今值 +8.86 | **+4.86** | **+0.12** | −10.28 |
| 30d 07-09 快照 +9.06 | +5.06 | +0.32 | −10.08 |
| **60d +3.66** | **−0.34** | **−5.08** | −15.48 |

**關鍵讀數**：60d 窗下即使 markout=0（最樂觀）也是負——**maker 化把該 cell 推正的前提是 30d gross（+9bps 級）是真水平而非窗口運氣**；31-60d gross −7.07 直接反證持續性。30d 窗下 break-even 的 markout 預算 =（8.86−4.0)/2 = **2.43bps/leg（且假設 100% fill rate）**。

### e.3 未入模成本（重放才能量到）

1. **Fill rate**：上表全部隱含「同樣 29 個 RT 100% 以 maker 成交」。實測參照：grid demo close-maker fill ~34.8%、flash_dip 0%（07-06 wave）；skill 判準 fill rate <60% 時 missed-trade 機會成本反超省費。bb_rev 買跌掛 bid 屬 mean-revert 側（fill 率結構性較高），但數值必須由 fill_sim 出。
2. **Taker 執行利益消失**：realized gross 內嵌 entry taker −6.07bps 的有利成交（§b.3），maker 化後不保留。
3. **Fee-tier lever 幅度**：VIP1（$10M/30d volume）maker 1.8bps → RT 省 0.4bps；現 roster 30d notional ~$690k = 門檻 6.9%，**不可達**；maker-nogo 實測 break-even 需 maker ≤0.4bps/side（infra-tier 鎖）在本 cell 語境下的對應物=上表 markout 預算。

---

## Findings 全量清單（severity / confidence）

| # | severity | conf | finding |
|---|---|---|---|
| F-1 | HIGH | HIGH | `maker_markout_bps` 語義=fill vs submit-reference（異質 reference_source），非 post-fill 60s/300s markout；Stage 2 per-strategy「adverse selection」表應重新標註（FACT，file:line 見 §b.1） |
| F-2 | HIGH | HIGH | bb_rev maker markout 有效 n=**1**（非 n=3）；−2.37 是單筆讀數，任何以它定價的算術屬 ASSUMPTION |
| F-3 | HIGH | HIGH | 60d gross +3.66 / 31-60d −7.07：gross 正是 30d 局部現象；60d 窗 maker 化算術在 markout=0 下已負（−0.34） |
| F-4 | MEDIUM | HIGH | Top-day 濃度：07-06 佔 30d gross 52%（>50% 判準邊緣違反）、60d 84%；episodes 跨 symbol 聚簇後獨立時間簇 ≈14 |
| F-5 | POSITIVE | HIGH | fills 無偽複製（每日 closes==distinct entries）；58/58 RT join 唯一 entry |
| F-6 | POSITIVE | HIGH | 重放基建齊備：L1 332.4M 行/21GB/85 sym/06-20→07-10；信號 episodes 對齊率 100%；`--horizons 60,300` 免改碼；harness 需改僅 placement 觸發+單側+episode 聚類（§c.3） |
| F-7 | MEDIUM | MEDIUM | Exit 72% 為 phys_lock giveback（tick 級動態）→ 只能做 execution-counterfactual（沿用 realized exit ts），不能 strategy-counterfactual |
| F-8 | LOW | HIGH | 資料品質：bb_reversion closes 帶 `grid_close_short` exit_reason 4 筆（跨策略標籤混入候選，未裁定假陽性與否，判斷依據=同表 strategy_name 過濾） |
| F-9 | LOW | MEDIUM | pg_stat n_live_tup 對 hypertable 嚴重失真（4.3M vs 實 332M）——count(*) 鐵則再驗證 |
| F-10 | INFO | HIGH | signals.details 全 NULL：重放價格錨=信號 ts 的 L1 BBO；OpenShort 僅 07-06 起出現（7 episodes），短側推論需 down-beta 標註 |
| F-11 | INFO | HIGH | episode n_eff=25 <30 門檻；~1.2 episodes/day 累積 → 約 1 週後達 30（純等待，$0） |
| F-12 | INFO | MEDIUM | 06-20→07-02 bb_rev 零 close 空窗（soak isolation 僅解釋 06-29 後）——open question |

## Open Questions（留 PM/operator）

1. 06-20→06-28 bb_rev 零成交的原因（cost_gate/JS 或信號缺席）——影響「30d 窗代表性」判讀。
2. `grid_close_short` 出現在 bb_reversion closes 的歸屬（F-8）。
3. 重放判準是否沿用 2026-07-10 反事實預註冊的 dedup/n_eff/day-cluster 框架（QC 建議沿用，屬設計決策，本報告不裁）。

**QC 結論性一句話**（供數層面）：重放在數據與工具層面完全可行且成本 $0；但 60d 證據已顯示「+0.3bps/RT」的 gross 輸入端不穩，重放的首要產出應是（i）真 60s/300s post-fill markout 分佈與（ii）fill rate，而非急於複核 +0.3 這個點估計。

QC AUDIT DONE: docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-10--move2_evidence.md

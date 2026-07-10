# QC Event Study — 歷史極端 funding 結算窗漂移(|F|>30bps)· 2026-07-10

任務:R3 修復包 WP-B.4(charter 授權;QC/MIT 並行離線 event study,QC 線)。
範圍:`research.alpha_funding_rates_history`(2yr)× `market.klines`(1m/1d),全程 Linux PG read-only。
定性:**研究判讀,非策略上線提案**。判定:**REJECT(對「可交易 edge」的 claim;附翻案條件)+ 預註冊母集 SAMPLE_INSUFFICIENT**。

---

## 1. Executive Summary

**預註冊母集(|F|>30bps)在自有數據內不可檢定:2 年 × 20 symbols 僅 11 個事件,其中 10 個是同一結算瞬間(2025-10-11 00:00 UTC 清算瀑布),n_eff≈2 個獨立 episode;且 11 個事件全部早於 1m kline 留存起點(2026-04-05),分鐘級結算窗漂移無法測量。** 可測的替代解析度(1d)顯示符號跨 horizon 翻轉(+1d −75bps / +3d +1,323bps / +7d −401bps,全長方向),= 單一 episode 的 regime-bet,無推論價值。1m 解析度的中度 tier 敏感性分析(|F|>5bps,n=28)顯示:**逆 funding 方向漂移毛值即為負或近零,扣 23bps taker RT 後全 horizon 淨負(−18 ~ −47bps);且 |F| 幅度與漂移無劑量反應(Spearman ρ≈0)**。在現有證據下,「極端 funding 結算窗」不構成可論證的 edge;同時本結論**不是**「該 edge 不存在」的證明——是樣本結構性不足(母集稀有 + 極端事件集中於未捕捉的新上市/小市值宇宙 + 1m 留存過短 + cap 截尾)。

---

## 2. 資料範圍與樣本可用性(第一約束)

| 數據 | 覆蓋 | 事實 |
|---|---|---|
| `research.alpha_funding_rates_history` | 2024-06-03 → 2026-06-02,20 symbols(全 major),46,539 行 | 單一 run_id(一次性 backfill artifact);(symbol,funding_ts) 無重複;`funding_interval_minutes` 欄位為 NULL(未填充) |
| `market.klines` 1m | **2026-04-05** → 今,176 symbols | 與 funding 歷史重疊僅 2026-04-05 ~ 2026-06-02(≈2 個月) |
| `market.klines` 1d | 2024-06-02 → 2026-07-08,26 symbols | 覆蓋全部 11 個母集事件的 symbol |

**母集計數(可重跑)**:
```sql
SELECT count(*) FROM research.alpha_funding_rates_history WHERE abs(funding_rate)>0.003;
-- = 11;其中 funding_ts >= '2026-04-05' 的 = 0
```
- 11 事件全為**負** funding;10/11 = 2025-10-11 00:00 UTC 同一結算瞬間(ADA/APT/ARB/AVAX/DOGE/DOT/LINK/SOL/SUI/XRP);第 11 個 = APTUSDT 2025-11-07 08:00 UTC。
- **cluster by symbol-day**:11 obs → 11 symbol-day;但 10 個共享同一 market-wide 瞬間,保守 cluster 單位=UTC day → **G=2,df=1,任何 t 檢定無意義**。對照 QC 預註冊慣例(n_eff≥30 / days≥5 / top-day≤50%):top-day 集中度 10/11=91%,三項全 fail。
- **cap 截尾證據**:SOLUSDT 事件 F=−50.00bps=其 `lowerFundingRate`(−0.5%)精確值;APTUSDT F=−100.00bps=其 `lowerFundingRate`(−1%)精確值(2026-07-10 instruments-info 即時查;歷史 cap 可能有異,標註為一致性證據非史實斷言)。**極端端 |F| 是應力的下界(截尾),幅度-漂移劑量關係在 cap 端不可測。**

## 3. 方法(leak-free 設計)

- **F 的資訊時點**:Bybit funding rate F(t) 為結算前一 interval premium TWAP,於 t 鎖定;本研究以 F(t) 為信號、entry=結算瞬間後第一根 1m bar 的 open(t+0~t+1min 可執行),漂移全部取結算**後**窗——在「F(t) 在 t 時點已知」假設下 leak-free(charter 規格)。entry gap>60s 的事件剔除(實際 0 個被剔)。
- **方向約定**:signed drift = sign(−F)×return,即逆 funding 方向(F<0 做多收 funding+博反轉;F>0 做空)。母集與重疊窗內 |F|>2bps 事件 100% 為負 funding → signed=raw(long)。
- **成本**:23bps/RT taker 上界(charter 指定;不假設 maker,maker-nogo 已判)。日內窗 funding carry≈0(8h/4h interval 下 15m~240m 持倉不跨下一結算;240m 對 4h-interval symbol 是邊界貼合,不計入=保守)。多日窗 carry 用實際結算序列逐筆累加。
- **統計**:mean 的 CR1 cluster-robust SE(cluster=symbol-day 按 charter;另列 cluster=UTC day 作保守版),df=G−1;多重比較:tier(6)×horizon(4)=24 檢定,Bonferroni α_adj≈0.002。
- 復算入口:`scratchpad/analyze.py` 邏輯已在報告附錄 SQL 中可完全重建(lateral join 點查,PG read-only)。

## 4. Population A — 預註冊母集(|F|>30bps,n=11,1d 解析度)

1m 不可用(全部事件早於 1m 留存),以 1d bar 替代解析度呈現**點估計**(無推論):

| symbol | UTC 結算 | F(bps) | +1d(bps) | +3d(bps) | +7d(bps) | carry7d(bps) |
|---|---|---|---|---|---|---|
| ADAUSDT | 10-11 00:00 | −56.17 | −53.6 | +1478.3 | −162.3 | +1.0 |
| APTUSDT | 10-11 00:00 | −100.00(cap) | −95.3 | +683.6 | −1323.5 | +239.4 |
| ARBUSDT | 10-11 00:00 | −36.76 | +168.6 | +2084.3 | +239.5 | −6.1 |
| AVAXUSDT | 10-11 00:00 | −84.16 | +347.5 | +1487.4 | −375.9 | +14.5 |
| DOGEUSDT | 10-11 00:00 | −58.00 | −443.8 | +1026.3 | −474.7 | +5.3 |
| DOTUSDT | 10-11 00:00 | −63.95 | +186.8 | +1472.0 | −170.8 | +30.8 |
| LINKUSDT | 10-11 00:00 | −80.82 | −100.2 | +1423.0 | −444.0 | −6.8 |
| SOLUSDT | 10-11 00:00 | −50.00(cap) | −570.7 | +1094.0 | −328.2 | +57.3 |
| SUIUSDT | 10-11 00:00 | −51.31 | −230.4 | +1500.6 | −632.4 | −5.9 |
| XRPUSDT | 10-11 00:00 | −58.00 | +37.1 | +978.2 | −333.5 | +0.8 |
| APTUSDT | 11-07 08:00 | −51.88 | −265.7* | +423.8* | −771.7* | +104.5 |

\* APT 11-07 事件 entry 為次日 1d bar open(結算在 bar 中段,延遲 16h),僅供參考。

**匯總(10 個 cascade 事件=1 個瞬間)**:+1d mean −75.4bps(4/10 正);+3d mean +1,322.8bps(10/10 正);+7d mean −400.6bps(1/10 正)。
**判讀**:+3d 全正是**單次市場反彈的 10 份拷貝**(cross-section ρ≈1),不是 10 個證據——與 F1 偽複製教訓同構(n_eff≈1)。+1d/+7d 符號翻轉進一步排除穩定結構。G=2 day-cluster,df=1:**SAMPLE_INSUFFICIENT,不出任何顯著性聲明**。

## 5. Population B — 敏感性分析(探索性,非預註冊;1m 解析度,2026-04-05~06-02)

母集空 → 降 threshold 看劑量反應與成本可行性。全窗口 3,894 個結算事件全數提取(0 缺價、0 entry-gap):

**tier × horizon signed drift(bps,逆 funding 方向;cluster=symbol-day,CR1)**

| tier(bps) | n | 15m | 30m | 60m | 240m |
|---|---|---|---|---|---|
| >30 | 0 | — | — | — | — |
| 20-30 | 1 | +6.9(G<2) | +46.5(G<2) | +62.8(G<2) | +9.5(G<2) |
| 15-20 | 3 | −50.7(p=.07) | −35.3 | −35.8 | −33.1 |
| 10-15 | 3 | −8.4 | −7.5 | +11.9 | −15.2 |
| 5-10 | 21 | −11.2 | −0.7 | −8.0 | +12.8 |
| 2-5 | 111 | +3.4 | +1.8 | +2.4 | −2.3 |
| ≤2(IR-floor) | 3755 | +0.2 | +2.2(p=.005†) | +1.1 | +0.4 |

† **假陽性候選(全量列出,不自行剔除)**:IR-floor tier 30m cell,symbol-day cluster t=+2.79/p=0.005(G=1169),但 (a) 效應 +2.15bps 對 23bps 成本經濟意義為零;(b) 換保守 day-cluster 即 p=0.060;(c) Bonferroni α_adj=0.002 下不過;(d) 同 tier 相鄰 horizon(15m/60m/240m)全不顯著,無結構一致性。判斷依據齊備,裁決交 PM/operator,QC 傾向 false positive。

**|F|>5bps 子集匯總(n=28,13 days,16 symbol-days;day-cluster)**:

| horizon | gross mean | median | t(G=13) | p | win% | **net(−23bps taker RT)** |
|---|---|---|---|---|---|---|
| 15m | −14.5 | −5.7 | −1.31 | 0.21 | 39% | **−37.5** |
| 30m | −3.4 | −6.8 | −0.24 | 0.81 | 46% | **−26.4** |
| 60m | −6.3 | −11.0 | −0.47 | 0.64 | 43% | **−29.3** |
| 240m | +4.8 | +16.2 | +0.15 | 0.88 | 61% | **−18.2** |

**劑量反應:無。** Spearman(|F| vs 60m signed drift):全事件 ρ=+0.021(p=0.19);|F|>2bps 子集 ρ=**−0.091**(p=0.29,方向甚至相反)。240m 同樣平坦。
**集中度旗標**:|F|>5bps 子集 11/28 = DOTUSDT 04-12~04-16 單一週 episode;|F|>10bps 僅 7 事件/5 days。
**分布(|F|>5bps, 240m)**:p10 −183 / p50 +9.5 / p90 +174 bps——雙尾寬、中位近零,是 vol 不是 drift。

## 6. 成本後 net 判定

在 23bps/RT taker 上界下:**所有可測 tier × horizon 的 net 皆為負**(最好者 240m@|F|>5bps 為 −18.2bps)。即使把成本砍半(假想 maker 單邊,**不獲授權作主判**,maker-nogo 在案),gross +4.8bps(p=0.88)仍無可辯護的 edge。短端(15m)的負向點估計(−14.5 ~ −24.3bps gross)方向上是「funding 方向動量延續」而非反轉,但 |t|<2.2、G≤13,同樣不構成反向可交易聲明(且反向操作依然被 23bps 吃掉)。

## 7. Regime / Listing 標註(leak-free,僅用事件前資料)

| 事件/窗口 | BTC prior-30d ret | 30d vol(年化,×√365) | vs 90d-high DD | 標籤 |
|---|---|---|---|---|
| 2025-10-11 cascade | −1.0% | 40% | −9.5% | **清算瀑布日本身**(前日 BTC −7.3%);flat→crash |
| 2025-11-07 APT | −16.5% | 46% | −18.7% | bear 延續段 |
| Pop B 窗口(2026-04-05~06-02) | 窗端 −9.2%(BTC 窗內 −3.3%) | 27~40% | — | bear/盤整,中低波動 |

- **Population A = 100% 事件落在 crash/bear regime**;無任何 bull-premium 正 funding 極端事件入樣(2yr 內 20 majors 正側最大僅 +29.15bps,POL)。結論繼承 down-beta 紀律:任何「+3d 反彈」讀數是 cascade-rebound regime-bet。
- **Listing 標註**:20 個 symbol 全為 established majors,事件時點上市齡 ≥16 個月(POL 序列 2024-09-05 起=MATIC→POL 改名,非新上市)。**母集內零新上市事件**——而極端 funding 已知集中於新上市/小市值(`listing pump`),該宇宙不在 funding 捕捉範圍且 `research.listing_capture_events`=0 行(2026-07-09 EXT 掃描在案)。這是母集稀有性的結構原因,不是市場沒有極端 funding。

## 8. 統計顯著性與 n(charter 交付項)

- Population A:n=11,symbol-day clusters=11,**day clusters G=2,df=1** → 無有效檢定;預註冊三門檻(n_eff≥30/days≥5/top-day≤50%)全 fail → **SAMPLE_INSUFFICIENT**。
- Population B:各 tier n=1~21(>5bps 合計 28),day-cluster G≤13;全部 24 個 tier×horizon 檢定中 0 個通過 Bonferroni(α_adj≈0.002);唯一 nominal 顯著 cell 見 §5 假陽性候選。
- Power 註記:n=28、SE_day≈13~31bps 下,對 23bps 級 alpha 的檢定 power 遠低於 0.5——**「未拒絕 H0」不是「無 edge 證明」**,是證據不足;但「gross 點估計為負/近零 + 無劑量反應」使「有 edge 但測不到」的先驗同步下降。

## 9. 侷限與資料品質 findings(全量)

| # | severity | confidence | finding |
|---|---|---|---|
| 1 | HIGH(對本研究) | 確證 | 1m kline 留存僅自 2026-04-05:任何 2026-04 前的分鐘級 event study 結構性不可做;母集 11 事件全部無分鐘數據 |
| 2 | MEDIUM | 確證 | funding 歷史止於 2026-06-02(單 run_id 一次性 backfill,已 stale 38 天);無持續採集器 → 未來事件不會自動入庫 |
| 3 | MEDIUM | 高 | cap 截尾:SOL/APT 事件 F 精確等於現行 lowerFundingRate → 極端端幅度被截,dose-response 上端不可識別 |
| 4 | LOW | 確證 | `funding_interval_minutes` 欄全 NULL;carry 計算已改用實際結算間距,不受影響 |
| 5 | INFO | 確證 | 重疊窗內 |F|>2bps 事件 0 個正 funding(bear 窗)→ 正極端側(long-crowding 清洗)在兩個 population 中均無代表 |
| 6 | INFO | 判斷 | Population B 為探索性、後設 tier 劃分;其結論只用於敏感性,不可引為預註冊證據 |

## 10. 建議(REJECT + 翻案條件)

**判定:REJECT**(作為可交易 edge 的證據申請)。「極端 funding 結算窗漂移」在自有數據內:預註冊母集不可檢定(n_eff≈2、無分鐘數據、cap 截尾),可測的中度 tier 逆 funding 漂移毛值近零/為負、無劑量反應、扣 23bps taker 後全負。**net 負/不可證也是有效結論(charter 明示)**——本結論按證據走。

**翻案所需最小證據(不留死刑)**:
1. **樣本**:≥30 個獨立極端結算 episode(≥10 個 distinct UTC day、top-day ≤50%),含正負兩側 funding;來源二選一:(a) 前向捕捉——WP-B.1-3 的 Gate-B 新上市 capture(cap=5)+ 把 funding 採集器恢復為持續模式並擴宇宙至高 |F| 小市值 symbol;(b) 回補——Bybit REST `/v5/market/kline` 1m 歷史對 20+ symbol 回補 2024-06~2026-04($0,限流內可行),即可讓現有 11 事件進入分鐘級檢定(但 n_eff≈2 的 episode 結構不變,仍需 (a) 補獨立事件)。
2. **機制**:分鐘級數據下,逆 funding 漂移在 day-cluster t≥2、BH-FDR(q=0.10)過檢、且對 |F| 幅度呈單調劑量反應(cap-censored 端用 censored 回歸或分段處理)。
3. **成本**:net>0 須在 23bps taker RT 上界下成立;maker 假設不得作主判。

**順帶正向輸出**:本研究把「極端 funding 事件在 major 宇宙 2yr 僅 11 個、91% 集中單日、且全在分鐘數據留存前」量化落錘——為 WP-B.1-3(新上市 capture 授權)提供了直接的證據面理由:**這個 niche 的證據不會從現有數據長出來,只能前向捕捉。**

---

## 附錄:可重跑證據(全部 PG read-only)

```sql
-- 母集(=11)
SELECT symbol, funding_ts, round(funding_rate::numeric*10000,2)
FROM research.alpha_funding_rates_history WHERE abs(funding_rate)>0.003 ORDER BY funding_ts;

-- 覆蓋
SELECT count(*), min(funding_ts), max(funding_ts), count(DISTINCT run_id) FROM research.alpha_funding_rates_history;
SELECT timeframe, min(ts), max(ts), count(DISTINCT symbol) FROM market.klines GROUP BY 1;

-- Population A 1d 漂移+carry:lateral join(d0=首根 ts>=funding_ts 的 1d bar;+3d/+7d 取 d0.ts+2d/6d close;
-- carry = sum(-funding_rate) over (funding_ts, exit]),見本報告 §4 表格,由 2026-07-10 QC session 執行原文保存於 git 外 scratchpad,
-- SQL 全文可按 §4 欄位定義逐字重建。

-- Population B 提取(3,894 事件,1m lateral 點查):
-- entry = 首根 ts>=funding_ts 1m bar open;exit_H = ts<funding_ts+H 內最後一根 close,H∈{15,30,60,240}min。
-- 統計:CR1 cluster mean-t(cluster=symbol-day 與 UTC day 雙列),Spearman dose-response。
```
Bybit cap 佐證(2026-07-10):APTUSDT upper/lower=±1%、SOLUSDT=±0.5%、fundingInterval=480min(instruments-info)。

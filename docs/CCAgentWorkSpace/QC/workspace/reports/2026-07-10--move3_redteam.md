# QC 對抗紅隊審計 — Move 3 日級 XS Horizon Arbitrage 方法論預註冊 · 2026-07-10

- **性質**:對抗紅隊(read-only)。受審對象 = `2026-07-10--move3_methodology_prereg_draft.md`(PREREG-DRAFT v1,**未凍結**)+ 其輸入 EV/EXT 兩報告。目標 = 殺掉此線或逼出誠實邊界。
- **總判定:REVISE — 線不死,但六攻擊面中四個 SURVIVABLE_WITH_FIX;v1 凍結前必須吸收 FIX-1..FIX-7(全部 pre-outcome 合法,零成本窗口就在現在)。無 FATAL。**
- **一句話誠實邊界**:本線作為「$0 研究管線 + breadth 期權」成立;作為「近期 PnL 線」不成立——在 prereg 自己的成本/波動假設下,Stage A(26 名窗)的 GO 機率在任何 post-decay 可信 IC 下 ≤~15%,即使全部成功,淨值量級 = SR 0.2-0.6、+3~4%/yr、$100k book 下 ~$3-4k/yr。
- 黑名單體檢:受審 prereg 零觸碰(§2.3 已核);本報告亦不引入黑名單方法。
- 證據紀律:本報告新增數字全附推導式或可重跑命令;衍生算術標 [DERIVED],假設標 [ASSUMPTION]。

---

## 0. Executive Summary(六攻擊面裁決總表)

| # | 攻擊面 | 裁決 | 一句話 |
|---|---|---|---|
| ① | Survivorship(26 名=倖存贏家) | **SURVIVABLE_WITH_FIX** | 偏差可 $0 量化(本審計新事實:下架公告 REST 全檔可枚舉,in-window 398 則);單一缺席 short-leg 衰退幣 ≈ +0.8bps/day 動量低估 = 與全部淨 edge 同量級;方向對 primary(動量)保守故不殺線,但 Q/reversal 族與 vol/tail 通道未覆蓋 |
| ② | Breadth 25 名 × IC 估計誤差 | **SURVIVABLE_WITH_FIX** | prereg 功效表誠實但**沒把乘法做完**:G2(PSR demo gate)要求觀察 net SR≥1.40(修正 T 後),而 prereg 自己的表 P3 說 IC 0.07-0.08 只給 net SR 0.18-0.42 → P(GO)≈10-15%;coin-flip GO 需 IC≈0.18-0.21(超 CTREND 未衰減水準)。§5.10「IC≥0.07 功效 0.85+」混淆了 IC 檢定功效與 GO 閘鏈功效 |
| ③ | Regime 分層後 bear/chop 剩多少 | **SURVIVABLE_WITH_FIX** | bear 子窗 273d 內嵌 E26(54%),但 **episode 數=1**(單一 boom-bust 路徑);273d 對 SR-1.0 策略獨立裁決需 ~1,460d → G4 只能當符號檢查(prereg 已如此設計,誠實);缺 chop/dispersion 分層;「all-weather」語言在 n_bear_episodes=1 下必須禁用 |
| ④ | 多日持有 engine lane 成本 | **SURVIVABLE_WITH_FIX** | 「Engine 改動=近零」低估:XS book 需要目標權重批次 rebalance 執行器 + BTC hedge overlay + 停用 per-leg SL 的治理裁決(與根則 9 交換所側保護衝突)= 新執行範式;且 **demo-cell ≠ GO-cell**(primary h=14 被 `holding_hours_max=168h` 硬截) |
| ⑤ | 與 R2「搜索空間根因」的範疇邊界 | **DEFLECTED**(留文檔級修補) | R2 證偽的是 {1m-lane OHLCV+TA × 分鐘級 horizon × TS 方向 × taker 逐筆淨額};Move 3 檢驗的是 {日級 × XS demeaned 殘差空間 × 成本攤提 14× 不同的歸一化}——假設不相交,R2 數據無法裁決 Move 3 任一方向。殘餘重疊(同資訊集、同線性 IC 法)= 弱負先驗,應顯式併入 ×0.3-0.5 折減的論證 |
| ⑥ | Turnover 現實與 net 殘值 | **SURVIVABLE_WITH_FIX** | 算術本身誠實(月成本 h=14 banded ≈59bps/mo pair);缺的是結論句:**在 prereg 自己的 decay 先驗均值(IC 0.03-0.05)下 net = −0.8~0 bps/day(負)**;正 net 情境要求先驗分佈上端 1/3;$ 期望值必須進 §7/§8 供 operator 計價 |

**為何不 FATAL**:(a) $0 read-only、預設結局 INSUFFICIENT 已誠實;(b) survivorship 方向對 primary 保守(不會偽造 GO);(c) 外部同儕審查證據在此 horizon/構造真實存在;(d) prereg 的 MF1/MF2/MF6 已自我申報核心弱點——本紅隊主要是**把它自己的表格相乘**並補上一條 $0 量化路徑。

---

## 攻擊 ① Survivorship — 量化與可控性

### 1.1 兩條偏差通道(prereg 只標註了一條的方向)

**通道 A — 真下架(不可回補)**:EV F1 已確立(TON/MATIC REST 0 bars)。
**通道 B — roster churn(可回補!)**:26 名單=2026-06 roster 回投影,**不是** 2024-06 的 PIT top-26。2024 年高流動但其後衰退的幣(meme/敘事退潮)仍在交易、歷史可 $0 回補,只是不在面板裡:

- [FACT,本審計實測 2026-07-10] WIFUSDT / ORDIUSDT / 1000PEPEUSDT / SEIUSDT / TIAUSDT / JUPUSDT / SHIB1000USDT 全部 status=Trading(617 USDT perp 集合內);FTM→S、MATIC→POL 為遷移映射案例。重跑:`curl -s "https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000"` 過濾 status=Trading。
- ⇒ **Stage B retro top-100 回補能完整修復通道 B**(仍在交易的衰退幣歷史全數可得);殘餘不可修復偏差只剩通道 A。

### 1.2 新事實:通道 A 可 $0 枚舉(升級 prereg 的「僅能標註」為「可量化」)

[FACT,本審計實測] `GET /v5/announcements/index?locale=en-US&type=delistings` 提供**全歷史下架公告檔**:total=442 則;其中 2024-06-01→2026-07-10 窗內 **398 則**、title 含 Perpetual/Contract 的 **238 則**;9 個 REST page、$0、分鐘級。月度節奏峰值 = **2025-10(46 則,cascade 月)**。重跑:
```
for p in 1..9: curl -s "https://api.bybit.com/v5/announcements/index?locale=en-US&type=delistings&limit=50&page=$p"
```
(EV FACT B2「歷史下架名單不屬 $0 庫內可得」對 **庫內** 正確,但對 REST 可得性過悲觀——公告檔完整在線。)

### 1.3 偏差量級界 [DERIVED + ASSUMPTION]

單一缺席的 short-leg 衰退幣(假設:−65%/最後 180d ≈ −58bps/day;被 tercile 選中佔 short 側 1/9 slot ≈ 5.6% book gross;banding 使其滯留):
```
spread 低估 ≈ 0.056 × 58 ≈ +3.2 bps/day(衰退窗內)
面板攤薄 ≈ 3.2 × 180/730 ≈ +0.8 bps/day(全窗平均,每缺一名)
```
對照:primary 在 IC 0.07-0.08 下的全部期望淨 edge = +0.8~1.1 bps/day(§攻擊⑥)。**⇒ 偏差與 edge 同量級,是一階項不是噪音。** 方向:對動量=低估(GO 決策安全);對 reversal/Q 族=高估(retro 面板上的此類發現先驗可疑)。

### 1.4 prereg 未覆蓋的三個洞

1. **per-family 方向表缺失**:blanket 標註只寫「momentum 保守/reversal 樂觀」;V 族(低波)=保守、**Q1(−turnover)/Q2(+amihud)=樂觀**(低流動幣最貼近下架邊界)——Q 族正是無標註的樂觀族。
2. **二階通道(vol/tail)未提**:倖存面板系統性低估波動與尾部(死掉的路徑被刪)→ G5 bootstrap SR CI 與 maxDD 估計是**真風險的下界**;即使 mean 方向保守,SR 分母被壓小 → SR 點估計仍可偏樂觀。GO 報告必須對 G5/maxDD 附此標註。
3. **K1(KILL)在 P100 上的不對稱**:P100 retro 面板的通道 A 偏差最重(下架節奏見 1.2),動量被低估 → 「gross CI 上界壓不過成本線」的 K1 在被低估的面板上=**假 KILL 通道**。K1 必須先加 survivorship 敏感度修正(CI_upper + δ_attrition)再比成本線。

**裁決:SURVIVABLE_WITH_FIX**(FIX-2/FIX-3)。可控性成立:通道 B 由 Stage B 完整修復、通道 A 可枚舉且可界;但 v1 原文的「標註了事」不夠,要量化入 P0。

---

## 攻擊 ② Breadth 與可檢定性 — prereg 沒做完的乘法

### 2.1 dispatch 的天花板算術修正(prereg 已做,記錄)

naive「IR=IC×√25,IC 0.03→年化 ~2.4」高估 8-10×:N_eff≈8-12(PC1 主導,ASSUMPTION 待 P0-3 PCA)、TC≈0.6、h-重疊 → BR_eff=N_eff×365/h。IC 0.03、h=14:gross IR ≈ 0.6×0.03×√261 ≈ **0.29**,扣 drag 後淨 ≈ 0 或負。prereg 表 P3 已誠實。

### 2.2 IC 估計誤差確證 [DERIVED]

E26 修正長度(見 2.3)T≈504、h=14 → 非重疊有效樣本 ≈36;SE(IC̄) ≈ (1/√25)/√36 ≈ **0.033 > 0.03**——dispatch 的「IC 估計誤差 >> 0.03」在修正 T 下成立(prereg 的 T=765 給 0.027,勉強同量級)。單 cell 量測 IC 的 95% CI 寬 ≈ ±0.065:**無法區分「死」與「CTREND 級」**。80% 功效需真 IC ≈ 0.082。

### 2.3 [RT2, MEDIUM-HIGH] T 混同:功效表用面板長度 765d,但證據序列 E26 只有 ~504d

特徵 eligible 需 174 bars(§3.5-1)→ 首合格日 ≈2024-11-23;+90d 首個 WF train → 首個 OOS test 日 ≈2025-02-21;E26 = 2025-02-21→2026-07-09 ≈ **504d**(POL 至 2025-02-26 才 eligible,altcap-6 至 2024-12,早期 XS 寬度 <26)。後果:
- PSR(0)≥0.95 門檻:觀察 net SR_ann ≥ 1.645/√503×√365 ≈ **1.40**(非 1.14);
- 表 P1 通過率全體下修 [DERIVED,sd≈√(365/504)≈0.85]:true SR 0.5 → **0.145**(原 0.18);SR 1.0 → **0.32**(原 0.42);SR 1.5 → 0.55(原 0.70)。

### 2.4 [RT1, HIGH — 本紅隊核心 finding] GO 閘鏈功效 ≠ IC 檢定功效

§5.10 Stage A 寫「primary GO 證據(若複合 IC≥~0.07,功效 0.85+)」——0.85 是**表 P2 的 IC t 檢定功效**。但 GO=G1∧…∧G9,綁定閘是 **G2(net PSR≥0.95 ⇔ 觀察 net SR≥1.40)**。用 prereg 自己的表 P3:
```
IC 0.07-0.08 → gross IR 0.68-0.78 → 扣 drag(0.36-0.60 SR 單位)→ net SR 0.18-0.42
P(G2 通過 | net SR 0.18-0.42, T=504) ≈ 8-15%   [DERIVED: Φ((SR−1.40)/0.85)]
P(GO)=50% 所需真 IC:net SR=1.40 → gross IR≈1.76-2.0 → IC ≈ (1.76~2.0)/(0.6×16.16) ≈ 0.18-0.21
```
**⇒ Stage A 的 GO 在任何 post-decay 可信 IC(≤0.10)下機率 ≤~15%;coin-flip GO 需要超過 CTREND 未衰減水準一倍的效應。** 即使 pooled E100⊕E_fwd(N_eff~25):IC 0.08 → gross IR≈1.22 → net ~0.7-0.9 → P(G2)≈30-40%,仍低於 coin-flip。
這不推翻框架(default INSUFFICIENT 誠實、G2 高拒真已按 dispatch 顯式接受),但 §1/§5.10 的敘事讓 operator 以為「效應夠強就能 GO」——**在 26 名窗,沒有物理上可信的效應強度能過 G2**。Gate 雙向計價下 G2 在 Stage A 的定位必須改寫為:「Stage A 不產 demo admission;demo admission 的現實路徑只有 pooled E100⊕E_fwd」。誤殺成本核算(對 G2 有利的一面,誠實記錄):錯放 GO 的代價=engine lane 數週工程+demo 60d 佔用;錯殺 true-GO 的代價=推遲 ~$250-330/月($100k book, +3-4%/yr)——成本不對稱**支持**高拒真 gate,前提是價值主張誠實。

### 2.5 [RT7, MEDIUM] 序貫檢定與跨輪選擇洩漏(兩處)

1. §5.7 INSUFFICIENT(b)「每 30d 以凍結 spec 重跑」= 對同一組 G-gate 的重複 look,無 alpha-spending 登記。看點高度相關(共享全部歷史)→ 膨脹溫和但真實 [DERIVED 估計:24 個月度 look 下 null 越界率 5%→~8-12%]。修:登記 look 時點(如凍結+6mo/+12mo/Stage B 完成時)或 group-sequential 邊界。
2. **內部矛盾**:§3.3「BH-FDR 名單…驅動下一輪 prereg」 vs §5.7(e)「舊結果不得重用於新 spec 的選擇」——兩句不能同時成立。若 v2 primary 選自 v1 grid,則 v2 的 DSR 必須繼承累計 K(K_cum = K_v1+K_v2)或 v2 只在 v1 未用數據(E_fwd / P100 增量)上檢定。二選一,寫進 v1。

**裁決:SURVIVABLE_WITH_FIX**(FIX-1/FIX-6)。

---

## 攻擊 ③ Regime 分層 — bear/chop 子窗夠不夠獨立裁決

### 3.1 天數盤點 [DERIVED,基於 prereg §5.8 標籤]

| 子窗 | 面板天數 | E26 內天數(扣 warmup+首 train) |
|---|---|---|
| recovery 2024-06-02→09-30 | ~121d | **0d(全被燒掉)** |
| bull 2024-10-01→2025-09-30 | 365d | ~221d(44% of E26) |
| bear 2025-10-01→2026-06-30 | 273d | 273d(54% of E26) |
| current 2026-07-01→ | 9d | 9d |
| **chop/dispersion 分層** | **未定義** | — |

E26 實際上 bear 佔比過半(正面事實,非 bull-heavy);但 recovery 層歸零,「四子窗強制輸出」對 recovery 是空集——v1 應明寫。

### 3.2 獨立裁決能力:不夠,且 prereg 的設計選擇(符號檢查)已是誠實上限

- bear 子窗獨立確認 SR-1.0 策略需 T=(2/SR_d)²=4×365≈**1,460d**;273d 給期望 t≈0.86、功效 ~22% [DERIVED]。**273 天無法獨立裁決**,G4 用點估計符號檢查是唯一誠實用法(prereg 8.4 已自報,credit)。
- G4 的雙向誤差 [DERIVED]:真 all-weather SR-1.0 策略 P(bear 子窗均值>0)≈Φ(√273/√365)≈0.81 → ~19% 假 INSUFFICIENT;真 regime-fake(bear 期望=0)只被擋 50%。弱閘,但 fail→INSUFFICIENT 可逆,接受。

### 3.3 [RT5, MEDIUM] 真正的洞:episode 級 n=1

273 個 bear 日 ≠ 273 個獨立觀察,甚至 ≠ 19 個獨立 h-block:**它是一條 bear 路徑的一份拷貝**(單一 2025-10→2026-06 下行,含單一 2025-10-11 cascade)。day-cluster/HAC 修的是窗內相依,不修 episode 級——「在 bear 有效」的主張 n_episodes=**1**,與 F1 偽複製、WP-B.4「10/11 事件同一瞬間」教訓同構。同理 bull episode=1。
修:(i) GO 報告強制標 n_episodes per regime;(ii) 禁用「all-weather」表述直至 forward 累積 ≥2 個獨立 bear episode;(iii) 增加一個可解釋 chop/dispersion 分層(如 BTC 90d |累積報酬| 分位 或 XS 報酬 dispersion 分位,shift(1))——XS trend 的經典失血 regime(低 dispersion 鋸齒)目前完全無監測。

**裁決:SURVIVABLE_WITH_FIX**(FIX-4)。

---

## 攻擊 ④ 多日持有 engine lane — 實作成本誠實度

### 4.1 [RT6, HIGH] demo-cell ≠ GO-cell(MF3 嚴重度被低估)

- [FACT] `settings/risk_control_rules/risk_config_demo.toml:22` `holding_hours_max = 168.0`(7d);`rust/openclaw_engine/src/risk_checks.rs:389` `max_hours = limits.holding_hours_max * rm.time` — **regime multiplier 在非 NORMAL 態把 168h 再往下收**。
- primary = `M5|h14|EW`。h=14 tranche 在 demo 會被 time-stop 在第 7 天強平 → demo 執行的根本不是 GO cell:turnover ×2、成本/日 ×2(3.29→6.57 bps/day)、且 h=7 的 INVALID_COST 餘量本來就貼線(banded 14.4% vs 15%/yr)。MF3 的「demo 首發限 h=7」= 靜默換 cell,h=7 從未作為 primary 檢定過。
- 修(二選一,均 pre-outcome 合法因 v1 未凍結):(a) 把 TOML 決策(operator)列為 GO→demo 的**具名 blocking 前置**(SSOT=TOML,QC 只標記);(b) v1.1 把 primary 改凍結為 h=7 並重算功效/成本表。禁止第三條路(GO 於 h14、demo 於 h7、宣稱互為證據)。

### 4.2 [RT6 續, HIGH] 「Engine 改動=近零」低估了一個執行範式

現架構=per-signal intent(Buy/Sell)+ per-position 風控。XS book 需要:目標權重向量 → 每日批次 delta 下單(16-18 腿)+ banding/tranche 狀態機 + 常駐 BTC hedge overlay(非信號腿,現無此概念)+ **停用 per-leg 動態 TP/SL**。最後一項不是 P2 設計題那麼輕:根則 9 + DOC-01 §5.9 要求交易所側條件保護——per-leg 交易所停損在波動尖峰**不對稱觸發**會拆掉 β_book 中性(G9 的 live 對應面崩壞),保留則破壞 XS 構造。這需要 CC/PA 治理裁決,不是備註。量級類比:最近似前例(M12 自適應 router)被定為完整 workstream。另 `correlated_exposure_max_pct=65`(toml:16)對 8-9 腿同向相關 alt 的計算方式是否綁死 book 規模——**需核實**,應併入 EV F5 open-question 清單。
Credit:halt 交互已被 prereg 列為 demo enable 的 blocking 前置(風險#6/§8.3-3),此洞已自報。

### 4.3 隔夜/weekend 風險的誠實回答

24/7 perp 無 equity 意義的隔夜 gap;真項目=(i) funding(§4.2 已逐日入帳,設計正確);(ii) weekend 薄簿 cascade 暴露且日級 rebalance 無盤中出場——2025-10-11(週六)在窗內,樣本 n=1;(iii) 帳戶級 daily-loss halt 由**其他 lane 的虧損**觸發時對 14d 在倉 book 的處置(強平=計畫外 RT ×2 + 時點損失)——即 F5,維持 blocking。
另:demo 60d = h14 的 4.3 個獨立持有週期 → **demo 只能校準執行/成本/funding 記帳,不能供 alpha 證據**——prereg §5.11-4 的 realized-vs-expected 設計與此相容,但應明寫一句,防 60d demo 淨值被誤讀為 alpha 確認。

**裁決:SURVIVABLE_WITH_FIX**(FIX-5)。

---

## 攻擊 ⑤ 與 R2「搜索空間根因」的範疇邊界

### 5.1 R2 到底證偽了什麼(釘原文)

[FACT,memory topic `project_2026_06_13_profit_diagnosis_searchspace_reconfirm`]:「OHLCV+TA net alpha=0(n=159 萬),正 PnL=down-beta 副產品;cost_gate 拒 99.97% 全真負 0 誤殺」。測試域 = engine 1m lane 的 TA 特徵、分鐘-小時級 horizon、TS 方向性、taker 逐筆淨額。

### 5.2 為何 Move 3 不落同一範疇錯誤(邊界寫嚴)

被證偽假設 H_R2 與 Move 3 假設 H_M3 在三個軸上不相交:
1. **成本歸一化(最硬的軸)**:H_R2 的檢定門檻=每筆 23bps RT——分鐘級 horizon 下任何 edge 必須**單筆**蓋過 23bps;H_M3 的同一 23bps 攤提為 1.64-3.29 bps/day(pair 46/h)。門檻差 **~7-14×**:R2 的「net=0」與「日級 gross 2-3bps/day 存在」在數學上完全相容——R2 根本沒測量過 7-28d horizon 的報酬。
2. **投影空間**:H_R2 = TS 方向預測,信號要跟 PC1(BTC beta,50-70% 方差)的噪音對打;H_M3 = XS 雙 demean 後的殘差空間 spread——正交投影,TS IC=0 與 XS IC>0 可同時為真。
3. **外部先驗分佈**:H_M3 的 horizon/構造有同儕審查正刊證據鏈(CTREND/LTW/IRFA);H_R2 的域沒有任何可信文獻主張 alpha。R2 結果與文獻在各自域上一致——不矛盾。

### 5.3 必須誠實保留的殘餘重疊(不許用「不同域」一筆帶過)

- **同一資訊集**(同 26 symbols 的 OHLCV):若市場對這批液態幣的價格歷史在**所有** horizon 皆有效,Move 3 同死。R2 是這個總假設的弱貝葉斯負證據——應顯式寫入 ×0.3-0.5 折減的論證裡(現折減只引 decay 文獻),而非只出現在相容性聲明。
- **同一方法軸(線性/rank IC)**:R2 若深層教訓是「線性 IC 方法學本身不夠」,Move 3 沒有逃逸——此殘餘須在 v1 明示(06-14 mandate 的「各 lens 原生數學」對本線只兌現了 horizon/XS 半張)。

**裁決:DEFLECTED**——prereg §8.5/EXT §8.5 的邊界主張在實質上成立且成本反差已量化(EXT §4.2);修補為文檔級:v1 增一張「證偽範圍表」(H_R2 參數 vs H_M3 參數逐軸對照 + 上述兩條殘餘重疊)。

---

## 攻擊 ⑥ Turnover 現實 — 月成本與 net 殘值

### 6.1 月成本表 [DERIVED,基於 prereg §4.4 的 46bps/RT pair]

| h | bps/day(full TO) | **bps/月(full)** | **bps/月(banded ×0.6 期望)** |
|---|---|---|---|
| 7 | 6.57 | 197 | 118 |
| 14 | 3.29 | **99** | **59** |
| 28 | 1.64 | 49 | 30 |

疊加項:funding 橫斷面中位下兩腿大致對消(±2bps/5d 級);短腿落負-funding 尾(TRX 級 −4bps/day 佔 1/9 slot)最壞 ≈ −6.7bps/月 book 級;下架摩擦 50bps/事件(ASSUMPTION);bull premium 回歸時 long 腿 funding drag 重現(P0-1 回補前全部 net 標 provisional——prereg MF4 已列)。

### 6.2 net 殘值 [DERIVED,book vol 15%/yr ASSUMPTION 中值 → 日 vol ≈78.5bps]

| 情境(複合 IC) | gross bps/day | 成本(h14 banded)bps/day | **net bps/day** | net %/yr | net SR |
|---|---|---|---|---|---|
| prereg decay 先驗均值 0.03-0.05 | 1.2-2.0 | ~2.0 | **−0.8 ~ 0** | 負~0 | ≤0 |
| 先驗上端 0.07-0.08 | 2.8-3.1 | ~2.0 | **+0.8-1.1** | +2.9-4.0% | 0.2-0.4 |
| CTREND 無衰減 ~0.10 | ~3.9 | ~2.0 | +1.9 | +7% | ~0.5-0.6 |

**⇒ 「net 還剩什麼」的誠實答案:在 prereg 自己的先驗均值下,什麼都不剩(負);正 net 是先驗上端 1/3 的條件事件。** $ 換算:$100k book、上端情境 = ~$2.9-4.0k/yr。credit:turnover/INVALID_COST 上界已登記(§3.5-5)、表 P3 已承認單因子淨趨零——缺的是把 $-期望值與 P(GO)(攻擊②)放進 §7/§8 讓 operator 直接計價「這條線買的是管線+期權,不是近期 PnL」。

**裁決:SURVIVABLE_WITH_FIX**(FIX-1 經濟誠實條款)。

---

## Findings 全量表

| # | Severity | Confidence | 對應攻擊 | Finding |
|---|---|---|---|---|
| RT1 | HIGH | high(算術,可復算) | ② | §5.10 混淆 IC 檢定功效與 GO 閘鏈功效;用 prereg 自己的表 P3:IC 0.07-0.08 → net SR 0.18-0.42 → P(G2)≈8-15%;coin-flip GO 需 IC≈0.18-0.21;Stage A 實質不可 GO |
| RT2 | MEDIUM-HIGH | high(算術) | ② | 功效表 T=765(面板長)≠ E26≈504(174d warmup+90d 首 train);PSR 門檻 1.14→1.40,表 P1 全體下修(SR1.0: 0.42→0.32) |
| RT3 | MEDIUM-HIGH | high(可行性 FACT)/medium(量級) | ① | 下架公告 REST 全檔可枚舉($0,total 442/in-window 398/perp-titled 238);單缺席 short-leg 衰退幣 ≈ +0.8bps/day 動量低估=與淨 edge 同量級;roster-churn 通道(WIF/ORDI/PEPE 等仍在交易)可由 Stage B retro 完整修復 |
| RT4 | MEDIUM-HIGH | high | ① | per-family survivorship 方向表缺失(Q1/Q2=樂觀未標註);vol/tail 低估通道未覆蓋(G5/maxDD=真風險下界);K1 於 P100(偏差最重面板)有假-KILL 通道,需 attrition 敏感度修正 |
| RT5 | MEDIUM | high | ③ | regime episode n=1(單 boom-bust 路徑);273d bear 無獨立裁決力(需 ~1,460d);G4 雙向誤差(真 all-weather 19% 假 INSUFFICIENT/regime-fake 只擋 50%);缺 chop/dispersion 分層;recovery 層在 E26 = 0d |
| RT6 | HIGH | high(FACT file:line) | ④ | demo-cell≠GO-cell:h=14 被 holding_hours_max=168h(toml:22)×rm.time(risk_checks.rs:389)硬截;「engine 近零」低估(權重批次執行器+hedge overlay+per-leg SL 治理裁決=新執行範式);correlated_exposure_max_pct=65 交互需核實 |
| RT7 | MEDIUM | high | ② | 30d 重跑=未登記序貫 look(null 越界 5%→~8-12%);§3.3(BH 驅動 v2)與 §5.7(e)(舊結果不得選擇)內部矛盾,需累計-K 規則 |
| RT8 | LOW | high | ⑤ | R2 邊界實質成立(成本歸一化 7-14×、投影正交、外部先驗非空);殘餘重疊(同資訊集/同線性 IC 法)須顯式併入折減論證 |
| RT9 | LOW | high | ⑥ | net-$-期望值與 P(GO) 未進 §7/§8;prereg 先驗均值下 net 為負的結論句缺失 |
| RT10 | INFO | high | ① | funding 缺值規則(long 付 floor/short 收 0)保守方向正確;下架幣 funding(TON −7.36bps/day)顯示缺席名同時低估 short 腿 funding 收入——同為動量保守向 |
| RT11 | INFO | medium | ③ | 假陽性候選自查:3.1 的 E26 起點 2025-02-21 基於「eligible 174 bars + 90d train」的機械推演,若實作對 19 個早期 symbol 用較短 L 的信號先行,E26 可早至 2025-01;判斷依據=§3.5-1 eligible 規則按 L_max 統一;不改變 RT2 方向,量級 ±5% |

---

## FIX 清單(v1 凍結前吸收;全部 pre-outcome 合法)

| # | 綁定 | 內容 |
|---|---|---|
| FIX-1 | RT1/RT2/RT9 | 重算功效表於 T=E26 實長;新增 P(GO\|IC) 聯合行與 $-期望值表;§1/§5.10 敘事改寫:「Stage A 不產 demo admission;demo 路徑=pooled E100⊕E_fwd」;G2 高拒真的成本不對稱論證(錯放=數週工程 vs 錯殺=$250-330/月)入文 |
| FIX-2 | RT3/RT4 | 新增 P0-6:下架公告檔枚舉(9 REST pages)→ PIT tombstone 表 + 遷移映射(MATIC→POL/FTM→S/SHIB 命名變體)+ per-family 偏差方向×量級表;G5/maxDD 輸出強制附「倖存面板=風險下界」標註 |
| FIX-3 | RT4 | K1 增 survivorship 敏感度:KILL 前 CI_upper+δ_attrition 仍 < 成本線才成立;retro 面板上 reversal/Q 族任何 Bonferroni 發現自動標 SURVIVORSHIP_SUSPECT,待 forward 面板確認 |
| FIX-4 | RT5 | 增 chop/dispersion 分層(可解釋指標,shift(1));GO 報告強制標 n_episodes per regime;n_bear_episodes=1 下禁「all-weather」表述;recovery 層 E26=0d 明寫 |
| FIX-5 | RT6 | MF3 升格:TOML holding 決策=GO→demo 具名 blocking 前置(owner=operator),或 v1.1 重凍 primary=h7 並重算表;§8.3 engine 改動重新計價(權重批次執行器/hedge overlay/per-leg SL 治理裁決=CC/PA 具名工作項);correlated_exposure 交互入 F5 清單;明寫「demo 60d 只校準執行,不供 alpha 證據」 |
| FIX-6 | RT7 | 登記 look 時點表(或 group-sequential 邊界);解 §3.3 vs §5.7(e) 矛盾:v2 primary 若選自 v1 grid → DSR 繼承 K_cum,或 v2 只在 v1 未用數據上檢定 |
| FIX-7 | RT8 | 增「證偽範圍表」(H_R2 vs H_M3 逐軸)+ 同資訊集弱負先驗顯式併入 ×0.3-0.5 折減論證 |

## 建議(對應 QC 8 節式之第 8 節;1-7 節內容已分佈於攻擊①-⑥)

**REVISE**:v1 未凍結是唯一的零成本修補窗口——吸收 FIX-1..7 後凍結為 v1.1,可 PROCEED(設計層)。價值主張必須以修正後的形式呈交 operator:**買的是「已驗證的 XS 研究管線 + Stage B breadth 期權 + forward PIT 累積」,不是近期 PnL**;Stage A 預期結局 ≥85-90% INSUFFICIENT(即使效應真實存在),此為框架的誠實產物而非失敗。
**翻案條件(推翻本 REVISE、允許原樣凍結 v1 所需最小證據)**:證明 (i) E26 實長 ≥700d(即我對 warmup/train 燒窗的推演錯誤,按實作重算),且 (ii) G2 在 26 名窗對某可信 IC(≤0.10)的通過率 ≥50%(即我對表 P3 net SR 的換算錯誤)。兩者皆為機械可復算命題。

---
*QC 對抗紅隊 · 2026-07-10 · read-only;本報告新增 FACT:Bybit announcements REST 下架全檔(total 442)與 WIF/ORDI/PEPE/SHIB1000 等 Trading 狀態,2026-07-10 實測。Operator 副本未落(dispatch 唯一寫入=本檔),PM 如需請代複製。*

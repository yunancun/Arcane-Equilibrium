# QC 方法論預註冊草案 — Move 3:日級 Cross-Sectional Horizon Arbitrage · 2026-07-10

- **狀態**:PREREG-DRAFT v1(待 PM/operator 批准後按 §5.9 凍結;凍結前禁止任何 cell 的 outcome 統計)
- **性質**:方法論設計 + 預註冊草案。不實作、不取 outcome 數據、不改任何 config/gate/策略。
- **輸入**(引用編號沿用原報告):
  - 取數:`workspace/reports/2026-07-10--move3_evidence.md`(下稱 EV,FACT A1-E3 / F1-F11)
  - 外部:`workspace/reports/2026-07-10--move3_external.md`(下稱 EXT,§2-§8 / F1-F10)
- **Priors(已判定,不重打)**:maker-nogo 2026-07-06(1m 域,break-even 需 maker≤0.4bps);taker RT 19-23bps;07-10 誤殺假說落錘(gate=淨止損);roster 全鎖 1m 頻率;30d notional $690k=VIP1 的 6.9%(fee-tier 不動,按 VIP0 計)。
- **鐵則內建**:demeaned-β 中性(2026-06-03)、regime 分層與 bull-only=regime-bet/learning-only、全特徵 shift(1)(`feedback_indicator_lookahead_bias`)、E[cost] 與 tail 雙軌分離(2026-07-09 教訓)、engine_mode IN ('live','live_demo')、年化 ×365。

---

## 0. 預註冊有效性聲明(pre-outcome 證明)

1. 本草案撰寫時點,兩份輸入報告均**不含任何本地 XS 信號的 outcome 統計**(EV=純資料盤點;EXT=外部文獻)。因此 §3.4 的 primary endpoint 指定成立於任何本地 outcome 揭示之前——預註冊合法性成立。
2. 判定式(§5.7)全部為機械謂詞:給定 evidence series 與登記參數,任何執行者(MIT/E4)可無裁量復算出同一結論。
3. 凍結錨採「輸入身分 sha256 + 分類規則 + 計數斷言」三件套(承 2026-07-10 counterfactual prereg 教訓,QC memory)。

---

## 1. Executive Summary

**一句話**:對「液態層日級 XS 複合 trend/momentum(7-28d 持有,雙中性化,taker 成本上界)」建立一個 K=114 的預註冊 sweep + 單一 primary endpoint 的驗證框架;GO/KILL/INSUFFICIENT 三態機械判定;**預期最可能結局是 INSUFFICIENT→繼續累積**,GO 只有在效應落於外部先驗上端(複合 IC≥0.07 級)時才可達,KILL 必須等寬宇宙面板(功效論證 §5.10)。

三條誠實聲明(本框架的自我體檢,gate 雙向計價):

1. **PSR(0)≥0.95 demo gate(dispatch 指令)在本地 2.1yr 窗單獨執行時,對真 SR=0.5 的策略拒真率 ≈82%,對真 SR=1.0 仍 ≈58%**(§5.10 表 P1)。緩解=允許 pooled evidence(寬面板+forward shadow 追加)進 PSR、且 PSR 不過 → INSUFFICIENT 而非 KILL。此 gate 的語義=「只放行效應量異常強的候選進 demo」,誤殺成本被顯式接受並記帳。
2. **26 名 breadth 的 exploratory grid 在 Bonferroni(K=114)下對 IC=0.05、h=14 的功效僅 ≈7%**(表 P2)→ 26 名窗的 sweep 是描述性的;正式 discovery 主張只能來自 primary endpoint(K=1 免修正)或寬面板。
3. **26 名窗不可產生 KILL**:對 IC=0.03 的檢定功效僅 0.19-0.47,「測不到」≠「不存在」;family-level KILL 的最小證據=寬面板(N≥80×2yr)上 gross 效應 CI 上界壓不過成本線(§5.7 K1)。

**與既有 NO-GO 的相容性**:本線不觸 maker-nogo(1m 做市域)、不觸 Rank7/四軸 NO-GO(死因=線性 IC×OHLCV×taker 牆×分鐘級;本線改變 horizon 與構造,EXT §8.5)。成本結構的反差:h≥14d 使 taker 成本從「結構鎖死」降級為「可管理摩擦」,首要約束移到 IC×√breadth(EXT §4.2)。

---

## 2. 理論基礎

### 2.1 Alpha 來源歸類(8 來源 framework)
類別 **#1 行為偏差**(herding/underreaction 驅動的液態層日-週級延續)+ **#7 跨資產溢出**(BTC regime→alt 相對輪動的殘差部分)。外部證據鏈:LTW JF 2022(大幣動量更強)、CTREND JFQA 2024(複合 trend 扣費存活,top-100 net 2.45%/wk)、FMPM 2025(post-2020 衰減)——全標「外部類比」,先驗折減 ×0.3-0.5(EXT §2.5)。

### 2.2 半衰期
h=7-28d,落在 OpenClaw 適配窗(1-30d)。信號生命週期與 1d sampling 匹配,無 1m 域的 SNR 死結。

### 2.3 黑名單體檢(math-model-audit 正本)
- HMM / GARCH / VPIN / 單獨波動率均值回歸 / 獨立 Donchian:**均未觸碰**。
- 警示兌現:全部 MA/rolling 家族特徵 **shift(1) 強制 + 斷言測試**(§5.2);vol-managed sizing 用 realized vol 分位(可解釋 metric,非 GARCH)。
- Regime 標註用可解釋指標(BTC 季度價格路徑 + realized vol 分位),不用黑名單模型。

### 2.4 已 REJECT 子方向(承 EXT §8.2,不重審)
- h=1 液態層日級反轉:DOA(illiquidity artifact + 365RT/yr 成本牆)。翻案條件=EXT §8.2 原文。
- Long-only "liquid winners" 當中性 alpha:regime-bet/learning-only。翻案條件=demeaned-β 殘差後 alpha 仍顯著。
- 本 sweep 空間(§3)**不含**上述兩構造。

---

## 3. 數學模型 — 信號族、sweep 空間、XS 構造

### 3.1 面板與記號
- 基礎面板 P26:`market.klines` timeframe='1d',26 symbols,2024-06-02→凍結日(EV FACT A1;19,776 行 @2026-07-09)。**survivor-conditioned by construction**(EV F1),所有結果強制附方向標註:momentum 偏保守 / reversal 偏樂觀(EXT F8)。
- 擴展面板 P100(Stage B,§5.10):top-100 USDT perp 回補後同構造。
- 記 C_t(s)=symbol s 於 UTC 日 t 的收盤,O_t(s)=開盤;日報酬 r_t(s)=ln(O_{t+1}(s)/O_t(s)) 以執行時點對齊(見 §3.5 執行時序)。
- **執行時序(leak-free 錨)**:信號只用 ≤ close(t−1) 的資料;倉位於 day t 生效;報酬自 O_t 起算。feature 窗與 target 窗零重疊。

### 3.2 信號族 S(19 個,全部 shift(1) 定義;z90(·)=rolling 90d z-score, shift(1))

| ID | 定義(於 t−1 收盤計) | 家族 | 個數 |
|---|---|---|---|
| M1.L | r_L = ln(C_{t−1}/C_{t−1−L}),L∈{7,14,28,56,84} | 動量 | 5 |
| M2.L | magap_L = (C_{t−1} − MA_L(t−1))/MA_L(t−1),L∈{7,14,28,56} | 趨勢 | 4 |
| M3 | TREND_EW = mean_L z90(M2.L),L∈{7,14,28,56} | 複合趨勢 | 1 |
| M4 | TREND_IR = Σ_L w_L·z90(M2.L),w_L ∝ max(trailing-90d IC-IR of M2.L, 0)(WF 內估,§5.3) | 複合趨勢 | 1 |
| M5 | TREND_VC = M3 · 1{z90(turnover_usd_30d)_{t−1} > 0}(量能確認,無確認=0) | 複合趨勢×量 | 1 |
| V1/V2 | −rvol_30 / −rvol_90(30/90d 日報酬 std) | 低波動 | 2 |
| V3 | −ivol_60(對 BTC 60d rolling shrunk-β OLS 殘差 std) | 低 idio-vol | 1 |
| Q1 | −z90(turnover_usd_30d) | 量價 | 1 |
| Q2 | +amihud_30 = mean_30d(|r|/turnover_usd)(LOW prior,僅融合腿候選) | 量價 | 1 |
| X1 | z(M3) + z(V3) 等權 | 跨族複合 | 1 |
| X2 | z(M5) + z(V3) 等權 | 跨族複合 | 1 |

融合紀律:任何複合腿間 trailing ρ>0.7 → 該複合視為單信號記帳(quant-strategy-design 正本);M1/M2 家族內部高相關是預期的,跨族分散只認 M×V×Q(EXT §3.2 判讀)。

### 3.3 Sweep 空間與 K 記帳(dispatch (a))

```
K = |S| × |h| × |W| = 19 × 3 × 2 = 114
  S  = 19 信號(§3.2 枚舉)
  h  ∈ {7, 14, 28} 天(持有期)
  W  ∈ {EW-tercile, IVW-tercile}(§3.5 權重)
```

- **固定不入 K**(單一預註冊執行政策,不得事後在其上選擇):banding ON(§3.6)、daily 1/h tranche(§3.5-4)、雙中性化(§3.5)、taker+funding 成本(§4)。
- **Robustness 變體不入選擇集**(只報告、禁止用於挑 cell):full-every-h rebalance、banding OFF、maker 成本 scenario(§4.5)、quintile 化。
- **多重比較(dispatch 指令 Bonferroni;skill 建議 K≥20 用 BH——小決策:兩者並用,Bonferroni 決策性)**:
  - Primary endpoint(§3.4):K_conf=1,免修正;DSR 以 K=1 計(=PSR)。
  - Exploratory grid:任何 cell 要升格為 candidate,須過 **Bonferroni α = 0.05/114 = 4.39e-4**(day-cluster t ≥ 3.33);**BH-FDR q=0.10** 名單並列為描述性 discovery list(不具決策力,只驅動下一輪 prereg)。
  - 全 114 cells 的統計無論好壞**全量落盤**(反 file-drawer)。

### 3.4 Primary endpoint(唯一確證性假設,pre-outcome 指定)

```
P* = { signal=M5 (TREND_VC), h=14d, W=EW-tercile, banding ON,
       雙中性化(XS demean + shrunk-β 殘差化), taker 23bps/RT + funding 逐日 }
H1: P* 的 WF-OOS 淨(taker+funding)日均 pair spread > 0(單尾)
```
選擇理由(寫在 outcome 之前):EXT §8.1 首選=CTREND-lite 複合 trend×量能;h=14 為 IC 需求(§5.10 表 P3)與成本線(§4.4)的平衡點;EW 避免 IVW 對 vol 估計的二階依賴。

### 3.5 XS 構造(dispatch (b))

1. **eligible set**(PIT):於 day t,要求 symbol 有 ≥ L_max+90=174 根歷史、且該日未下架。TON 在 2026-06-15 後自然退出(§3.7)。
2. **中性化(雙 demean,06-03 鐵則 XS 版)**:
   - Step 1:score 於當日 XS demean(等價 rank 化後對中位數對稱);
   - Step 2:β 殘差化——β_s = 60d rolling OLS(r_s ~ r_BTC) 加 shrinkage(β̂ = 0.5·β_OLS + 0.5·1.0;Kristoufek 2025 依據,EXT §6.2),全 shift(1);book-level 再加 BTC perp 對沖腿使 β_book→0,對沖腿成本按 §4.1 同費率計(保守;BTC 實際更便宜)。
   - 報告強制並列 raw vs demeaned(down-beta 偽裝顯影);**只有 demeaned 版進判定式**。
3. **選股與權重**:long top-tercile / short bottom-tercile(N<60 用 tercile ≈8-9 幣/側;N≥60 用 quintile——機械規則:側容量 = max(5, ⌊N/5⌋) if N≥60 else ⌊N/3⌋)。W=EW(等權)或 IVW(側內按 1/rvol_30 加權,shift(1))。兩側各 0.5 gross,dollar-neutral。單幣 cap = 側內權重 ≤ 25%。
4. **Rebalance 頻率 × 持有期矩陣(canonical)**:h∈{7,14,28};canonical 執行 = **daily 1/h overlapping tranches**(Jegadeesh-Titman),即每日換 1/h 的 book——矩陣的「rebalance 頻率」維度由 tranche 機制吸收(期望 turnover 與 every-h full rebalance 相同,消 timing luck);full-every-h 為 robustness 變體(§3.3)。
5. **Turnover 上界(registered cap)**:
   - 結構上界:單向年化 turnover(pair,以 gross 為基)≤ 1.25 × 365/h(h=7/14/28 → 65.2/32.6/16.3);超出 → `INVALID_TURNOVER`(cell 不可 GO,仍全量報告)。
   - 經濟上界:realized 年化 pair 成本 drag(taker 軌)> 15%/yr → `INVALID_COST`(不可 GO;h=7 unbanded ≈24%/yr 預期自動觸此線,banding 後 ≈14.4% 貼線——這是把 h=7 留在 sweep 內但用機械線擋住其成本病的方式)。

### 3.6 Banding(hysteresis,固定 ON)
進場:rank 進入 top/bottom tercile;出場:rank 穿越中位數才平(band = tercile 邊界→median)。Novy-Marx-Velikov 慣例,期望 TO 削減 ~40%(EXT §7;實際削減以 realized 記帳,不用假設值入成本)。

### 3.7 特殊處理(機械,預註冊)
- **2026-06-27 全體缺日**(EV F6):若 P0 回補未完成,bridged 規則=該日不 rebalance,06-26→06-28 記 2 日報酬;回補完成則規則自動失效。
- **TON 下架**(唯一在庫下架樣本):2026-06-15 最後 bar 強制平倉,計 taker 單邊 11.5bps + **下架摩擦罰 50bps(ASSUMPTION,保守)**。
- **f32 精度**(EV F7):研究面板不吃 DB f32 鏈——由 REST/DB 重建為 **parquet f64**;P100 擴展選集排除 price<$0.005 的極小價 symbol(或個案標記)。

---

## 4. 成本分析(dispatch (d):taker 上界,不假設 maker)

### 4.1 E[cost] 軌(進判定式)
- **taker RT = 23 bps/腿(上界,dispatch 指令;= 2×5.5 fee + 2×6 slip,與 roster-alt q50 量級一致,EV FACT C2)**。記帳方式:每單向成交名義 × 11.5 bps。對沖腿(BTC)同費率。
- 不假設 maker、不假設限價改善、mean_signed −2.45 不得抵扣(EV F9;硬約束 4)。

### 4.2 Funding 逐日計價(進判定式)
- 每持倉日,per-symbol 實際結算現金流:long 付 F、short 收 F(F>0),以回補後的 2yr funding 史逐日累加(EV F4:回補為 P0 前置,~11 pages/symbol,$0)。
- 缺值保守規則:long 腿按 IR floor 計付 +1.095 bps/day,short 腿計收 0。
- 警告內建:momentum long 腿與高 premium 幣同向的「信號-funding 相關」由逐倉記帳自動捕捉(EXT §4.3),禁止用 cross-section 平均 funding 替代(EV FACT E3:短腿落 TRX 級負尾=−20bps/5d)。

### 4.3 Tail 軌(不入均值,入壓力報告)
- p10 slip −37.79bps prior、CVaR90 126.68bps(EV FACT C1)→ 以「全部成交吃 tail slip」情境重算淨值,列入 stress 附表;不參與 GO 判定,但 GO 報告必附。

### 4.4 成本線(pair,taker 軌;判定式 K1 使用)

| h | pair 成本 bps/day | 年化(full TO) | 年化(banding 實測 ≈×0.6 時) |
|---|---|---|---|
| 7 | 6.57 | 24.0% | 14.4% |
| 14 | 3.29 | 12.0% | 7.2% |
| 28 | 1.64 | 6.0% | 3.6% |

(46 bps/RT pair ÷ h;banding 欄以 realized TO 記帳,×0.6 僅為預期展示。)

### 4.5 Maker scenario = annex only
按 dispatch 指令,maker(~8.7bps RT,strategy-conditional)只作為敏感度附錄,**不進任何判定式**。若日後 Move 2 重放證實日級無 urgency 限價單的 AS 溫和,由新 prereg 修訂案引入,不得事後切換。

---

## 5. 回測驗證要求(protocol 本體;執行=MIT/E4,QC 出帶裁決)

### 5.1 資料品質前置檢定(step 1,記錄性)
對 pooled 日報酬面板與每個候選 cell 的淨值序列跑:ADF、KPSS、Ljung-Box、Jarque-Bera、ARCH-LM。預期:JB 必拒 normality、ARCH 顯著 → PSR 的 skew/kurt 修正與 block bootstrap 因此為強制而非選配。異常(如 ADF 不拒 unit root)→ 停下查資料而非上模型。

### 5.2 Leak-free 強制(dispatch (c))
- 全特徵 shift(1);z-score/normalization 只用 rolling(90d)或 expanding 統計,**禁全期 mean/std**。
- 實作要求:signal spec 層寫**斷言測試**——對每個特徵,驗證「將 t 日之後的資料全部置 NaN 不改變 t 日特徵值」(point-in-time invariance test),CI 級強制。
- Purge + embargo:任何 WF-fitted 元件(M4 權重、β、z 參數)train/test 邊界 purge h 日 + embargo h 日(機制正本 `time-series-cv-protocol`,MIT 主審)。
- 本框架無 ML 訓練(全 rank/線性構造);若後續加 ML 腿,MIT 主審 leakage,另立 prereg。

### 5.3 Walk-forward(rolling 90/30)
- Rolling 90d train / 30d test,滑動至面板末端。WF-fitted 元件清單(僅此三項,其餘無參數):M4 的 IR 權重、shrunk-β、z90 統計(天然因果)。
- **Evidence series E26 = 全部 test block 串接的日淨報酬**(taker+funding,demeaned)。所有判定統計只在 E26(或 E100/E_fwd)上計,**in-sample 表現不進任何判定**。

### 5.4 檢定
- **主檢定(信號層)**:daily Spearman IC(score_{t−1} vs r_{t→t+h}),重疊窗以 Newey-West(lag=h)或 h-block 修正;等效 day-cluster(同日 XS 觀察非獨立,G=交易日數)。
- **組合層**:E26 日均淨 spread 的 HAC t(lag=h)。
- **PSR(0)**:含 skew/kurt 修正(Bailey-LdP 2012);**DSR**:exploratory 用 K=114,primary 用 K=1。
- 多重比較:§3.3(Bonferroni 決策 + BH 描述)。
- 年化 ×365。

### 5.5 Block bootstrap CI(dispatch (c))
Stationary bootstrap(Politis-Romano),期望 block 長 = 2h 日,B=1,000,對 E26:SR_ann 95% CI、maxDD 95% CI。IID bootstrap 禁用。

### 5.6 PBO / CSCV
K=114 ≥ 10 → 強制。CSCV S=16 切分於 114-cell 收益矩陣;**PBO < 0.5** 為 GO 必要條件(機制正本 `time-series-cv-protocol`)。

### 5.7 GO / KILL / INSUFFICIENT 判定式(dispatch (g);全機械)

對象:primary cell P*(或任何過 Bonferroni 的 exploratory cell)。記 E = pooled evidence series(§5.11 定義的合併規則)。

**GO(demo)= G1∧G2∧…∧G9 全真:**

| # | 謂詞 | 閾值 |
|---|---|---|
| G1 | leak-audit 全過 | PIT invariance test 0 fail + 5.1 檢定已跑 |
| G2 | **PSR(0) on E ≥ 0.95**(dispatch demo gate) | ≥0.95 |
| G3 | DSR ≥ 0.95(primary K=1;exploratory K=114) | ≥0.95 |
| G4 | regime:bear 子窗(2025-10-01→2026-06-30)淨均值 | > 0 |
| G5 | block bootstrap SR_ann 95% CI 下界 | > 0 |
| G6 | PBO(CSCV S=16) | < 0.5 |
| G7 | 年化 E[cost]/年化 gross(cost_edge_ratio) | ≤ 0.8 硬線(CLAUDE 根則);同時報 ≤0.5 達標與否 |
| G8 | turnover ≤ 結構上界 且 非 INVALID_COST | §3.5-5 |
| G9 | β 殘留:E 期間日 β_book 均值絕對值 ≤0.10 且 95% 日 |β|≤0.25 | 雙條件 |

**KILL(family 級,僅對信號家族,非單 cell)= K1∨K2,且前置條件 PC 成立:**

- PC(功效前置):KILL 判定只允許在 **P100(N≥80、T≥2yr)** 面板可用後執行——26 名窗功效不足以支持 KILL(§5.10 表 P2,MF2)。
- K1:P100 上,該家族最佳 cell 的 **gross demeaned pair spread 95% CI 上界 < 對應 h 的成本線(46/h bps/day)**,對 h∈{7,14,28} 全部成立(連毛利都以 95% 信心蓋不過 taker 線 = 經濟死)。
- K2:P100 上,家族複合信號 IC 的 95% CI 上界 < 0.02(低於任何可用信號的下限)。
- **翻案條件(附於任何 KILL)**:出現以下之一即重開——(i) forward PIT 面板累積 ≥1yr 後同檢定翻正;(ii) 執行成本結構性下降(fee tier / RPI 級 taker 改善)使成本線下移 ≥40%;(iii) 新增正交數據軸使複合 IC 的可信先驗上移至 ≥0.08。

**INSUFFICIENT(默認結局)= 非 GO 非 KILL:**
機械動作清單:(a) forward PIT 累積繼續(daily cron 已在跑,零操作);(b) 每 30d 以凍結 spec 重跑一次(不得改 spec,只延長窗);(c) Stage B 擴張若未執行 → 升級為 blocking recommendation;(d) 153-sym 1h 輔助窗複製檢查(§5.11);(e) 任何 spec 修改 = 新 prereg 修訂案(v2),舊結果不得重用於新 spec 的選擇。

**判定順位**:INVALID_*(G8 類)→ 不可 GO 但不觸發 KILL;G2/G3 不過而 G5 過(CI 下界>0 但 PSR<0.95)→ INSUFFICIENT-POSITIVE 子標籤(效應同號但強度不足),優先續累積。

### 5.8 Regime 分層強制(dispatch (f))
- 標籤(BTC 1d 季度路徑,EV/EXT 已核,可重跑 SQL 在 EXT §5.8):`recovery` 2024-06-02→2024-09-30;`bull` 2024-10-01→2025-09-30(62.7k→126k);`bear` 2025-10-01→2026-06-30(126k→57.8k);`current` 2026-07-01→窗末。
- 每個候選 cell 強制輸出四子窗淨均值 + HAC SE。
- **bull-only 正(bear 子窗 ≤0)→ 自動標 `REGIME_BET_LEARNING_ONLY`,不可 GO**(G4 已機械化);此標籤結果仍全量保留(學習價值)。
- 正面事實記錄:本窗為完整 boom-bust mixed-regime,非 bull-heavy(EXT F7)——G4 是真檢驗而非空轉。

### 5.9 凍結機制(三件套)
1. **輸入身分**:凍結時點 P26 面板快照 sha256(生成規則:per-symbol (symbol, n_rows, min_ts, max_ts, sum(close::numeric)) 排序後串接雜湊)+ funding 回補表同構雜湊。
2. **規則**:本文件 §3-§5 全文 sha256(v1 凍結版)。
3. **計數斷言**:|S|=19、|h|=3、|W|=2、K=114、primary cell id = `M5|h14|EW`;執行第 0 步必須枚舉並斷言 114,不符即 abort。
凍結後任何修改 = v2 修訂案,須重新凍結且不得繼承 v1 的 outcome 用於選擇。

### 5.10 Power 誠實分析(dispatch (e))與宇宙擴張定位

近似框架(條件聲明:Spearman IC null std ≈ 1/√(N−1);重疊修正取 T/h 有效樣本;daily SR 估計 std ≈ 1/√T;iid 近似,fat-tail 下真實功效更低——以下數字視為**上界**):

**表 P1 — PSR(0)≥0.95 demo gate 在 2.1yr 窗(T≈765d)的通過率(= 1 − 拒真率):**

| 真 net SR_ann | 0.3 | 0.5 | 0.8 | 1.0 | 1.2 | 1.5 |
|---|---|---|---|---|---|---|
| P(pass) | 0.11 | 0.18 | 0.31 | 0.42 | 0.54 | 0.70 |

門檻換算:PSR(0)≥0.95 ⇔ 觀察 net SR_ann ≥ ~1.14(normal)/ ~1.16(skew −0.5, kurt 7)。**gate 語義=只放行上端效應;誤殺率被顯式接受(dispatch 指令),且 fail→INSUFFICIENT 不 KILL,誤殺不可逆性被移除。**

**表 P2 — IC 檢定功效(t_exp = IC·√(N−1)·√(T/h);單尾 α=0.05 / Bonferroni K=114):**

| N | h | IC=0.03 | IC=0.05 | IC=0.08 |
|---|---|---|---|---|
| 26 | 7 | 0.47 / 0.04 | 0.83 / 0.24 | 0.99 / 0.80 |
| 26 | 14 | 0.30 / 0.01 | 0.58 / 0.07 | 0.91 / 0.35 |
| 26 | 28 | 0.19 / 0.01 | 0.37 / 0.02 | 0.67 / 0.11 |
| 100 | 14 | 0.71 / 0.13 | 0.98 / 0.64 | 1.00 / 0.99 |
| 100 | 28 | 0.47 / 0.04 | 0.83 / 0.23 | 0.99 / 0.80 |

**表 P3 — Fundamental law 錨(TC=0.6,N_eff=10 @N=26,ASSUMPTION 待 P0 PCA):**
gross IR:h=14 → IC 0.03/0.05/0.08 = 0.29/0.48/0.78;成本 drag(§4.4,banding 後 7.2%/yr)在 book vol 12-20%/yr(ASSUMPTION,P0 測量)下折 SR ≈0.36-0.60 → **單因子 IC 0.03-0.05 在 taker 軌下淨效應趨近 0;只有複合 IC≥0.07-0.08 有淨空間**。這與 primary endpoint 指定複合信號一致。

**宇宙擴張=並行(不是前置,但 KILL 與 discovery 的前置):**
- **Stage A(立即,$0,無 gating)**:26 名面板凍結+執行。可產出:primary GO 證據(若複合 IC≥~0.07,功效 0.85+)、描述性 grid、INSUFFICIENT 累積起點。**不可產出**:單因子 discovery 主張、KILL。
- **Stage B(並行,$0,operator-gated `--apply`)**:top-100 回補(1 page/symbol,分鐘級)+ funding 2yr 回補 + PIT liquidity cutoff 定義(§8.2-3)。是 KILL(§5.7 PC)與 Bonferroni-級 discovery 的**最小充分證據面**。survivor 標註同 P26(方向:momentum 保守)。
- **Stage C(常開,零操作)**:forward daily cron PIT 累積(EV F1 唯一無偏路徑)+ 每 30d 凍結 spec 重跑。
- 誠實結論:26 名窗單獨「等時間」不解決功效(SR 檢定要 power 0.5 於 SR=0.5 需 ~10.8yr);**breadth 是唯一在合理時間內改變功效的槓桿**,故 Stage B 建議與 Stage A 同週啟動。

### 5.11 OOS 與驗證安排(dispatch (g) 後半)
1. **E26 = WF-OOS 串接**(§5.3)——第一級證據;無 sealed holdout(小決策:2.1yr 窗再封 20% 會把僅有的功效再砍,改用 (3) 的 forward shadow 作真 OOS;此取捨在此註明)。
2. **結構複製窗**:153-sym 1h 宇宙(2026-04-05 起,~96d;EXT F9)聚合為日級,對 primary 信號做**同號檢查**(方向一致性,非顯著性)——不進 GO 判定,但異號 → 強制寫入風險節。
3. **Forward shadow(真 OOS,$0)**:凍結日起,每日離線計算 P* 的信號與虛擬淨值(不下單、不進 engine)→ E_fwd。**Pooled E 規則(G2/G3 用)**:E = E100(若 Stage B 完成,取代 E26)⊕ E_fwd(時間不重疊串接);嚴禁同期窗重複計入。
4. **Demo(若 GO)**:Stage 0R replay preflight → Demo-only(硬邊界:Stage 1 alpha-bearing promotion 是 Demo-only);demo 預註冊評估=≥60d、realized vs expected(IC、成本、funding)cell-level 對比、PSR 併入 demo 淨值更新;demo 表現不等同 live edge(隔離原則)。

---

## 6. 風險分析(承 EXT §6,本地化增補)

1. **Momentum crash(HIGH)**:FMPM 2025 單週 −255%(年化尺度)級離散事件;本地 2025-10-11 cascade 在驗證窗內(可直接觀察 cell 行為)。緩解=vol-managed sizing(realized vol 分位,非黑名單)+ 既有 P0/P1;**禁止修剪 crash 樣本**。
2. **β 中性殘留(MEDIUM)**:G9 機械化;shrunk-β + book hedge;報告 β 時序分佈非點估計。
3. **Funding regime 轉換(MEDIUM)**:§4.2 逐倉記帳;bull premium 回歸時 long 腿 drag 自動顯影;per-symbol `upperFundingRate` SSOT 規則適用,禁 history-max 推 cap。
4. **小 breadth 集中(MEDIUM)**:tercile + 單幣 cap 25%;單幣事件(delist/hack/unlock)佔側 ≤25% 上限。
5. **Decay/crowding(HIGH,結構性)**:先驗均值=外部 gross ×0.3-0.5;INSUFFICIENT-POSITIVE 時不得用外部數字補證據。
6. **多日持倉 × daily-loss halt 交互(未閉,EV F5/D3)**:halt 期間持倉處置路徑未逐條核實——**demo enable 的 blocking 前置**(§8.3)。
7. **判定式自身風險(gate 雙向)**:G2 拒真率已計價(表 P1);K1 誤殺保險=翻案條件強制附帶;INVALID_COST 線(15%/yr)可能誤擋 gross 極強的 h=7 cell——接受,理由:taker 上界紀律優先於覆蓋率。

## 7. 容量估算

26 名液態 majors Bybit perp 名義 ADV $10⁸-10⁹/幣(ASSUMPTION,EXT §7);XS book gross $50k-$1M 下 square-root impact <1bps,**容量不 binding**。fee-tier 不因本線自身移動(h=14、$100k book 月增 ~$430k 成交額,合計仍 ~VIP1 門檻 11%),成本模型按 VIP0 保守計。市場影響重估觸發線:book gross > $2M 或單腿 > 0.5% 幣日成交額。

## 8. 建議(PROCEED / REVISE / REJECT)

### 8.1 總判定:**PROCEED(設計層)** — 批准本 prereg 後按序執行;真 GO/KILL 由 §5.7 在數據上機械產生。預期最可能結局=INSUFFICIENT(-POSITIVE)→ Stage B/C 累積,非一輪定生死。

### 8.2 P0 前置(outcome 統計之前必須完成,全 $0)
| # | 項 | 性質 | gating |
|---|---|---|---|
| P0-1 | funding 2yr REST 回補落庫(~11 pages/symbol×26) | 成本模型完整性(§4.2;EV F4) | 寫 DB,需 operator/E1 排程 |
| P0-2 | 2026-06-27 缺日回補(`--lookback-days 30` 一次重跑)或啟用 bridged 規則 | 資料完整 | operator-gated `--apply`;bridged 規則為無 gating 替代 |
| P0-3 | 26 名日報酬 PCA → N_eff 實測(取代 ASSUMPTION) + book vol 測量 | 校準表 P3 | 純讀,$0,無 gating |
| P0-4 | 面板重建為 parquet f64(繞 DB f32) | 精度(EV F7) | 研究側,無 gating |
| P0-5 | 凍結三件套執行(§5.9) | prereg 生效 | PM 批准後 |

### 8.3 若 GO → 實作面主張(dispatch (h);QC 主張,PA/E1 定案)
1. **離線 backtest 目錄結構(建議)**:
```
helper_scripts/research/xs_daily_lane/
  prereg/move3_prereg_v1.json        # 凍結三件套 + 判定閾值(機器可讀)
  data/build_panel.py                # market.klines 1d + funding → parquet f64
  signals/spec.py                    # §3.2 宣告式定義 + PIT invariance 斷言測試
  backtest/engine.py                 # tranche/banding/雙中性化/成本雙軌
  stats/gates.py                     # G1-G9/K1-K2/INSUFFICIENT → verdict JSON
  reports/                           # 全量 114-cell 落盤(反 file-drawer)
```
新腳本須登記 `helper_scripts/SCRIPT_INDEX.md`;實作歸 MIT/E1,QC 不寫碼。
2. **Engine 改動=近零,3 個例外**:(i) 信號/feature 走 DB 直讀 1d(flash_dip 前例,**不動 KlineManager**;EV FACT D4);(ii) **h=14/28 與 `holding_hours_max=168h`(7d)衝突**——demo 首發限 h=7,或 operator 批准 risk config 變更(SSOT=TOML,QC 只標記不改);(iii) 日級 lane 應**停用 per-leg 微觀動態 TP/SL**(會拆散 XS 構造),僅保留 P0/P1 硬防線——屬 P2 範圍設計題,交 PA。
3. **Demo 驗證路徑**:Stage 0R replay preflight(綠)→ Demo-only lane(硬邊界)→ §5.11-4 的 60d 預註冊評估;**blocking 前置**=關閉 EV F5 兩個 open question(halt 交互、擴宇宙接線)。
4. **PIT liquidity cutoff 提案(解 EV F2,供 MIT 覆核)**:retro Stage B 選集=「選集日 30d 中位日成交額 top-100 ∧ 上市 ≥180d ∧ price ≥$0.005」,明示 end-of-sample selection + 方向標註;forward 每月 PIT 快照重選,tombstone 保留、不回溯刪除。

### 8.4 Findings 全量(本方法論設計自身)
| # | Severity | Confidence | Finding |
|---|---|---|---|
| MF1 | HIGH | high(算術) | PSR(0)≥0.95 demo gate 於 2.1yr 窗單獨執行拒真率 82-89%(SR 0.3-0.5);已按 dispatch 保留,緩解=pooled E + fail→INSUFFICIENT;gate 淨貢獻依賴「誤殺可逆」設計 |
| MF2 | HIGH | high(算術) | 26 名 grid + Bonferroni114 功效 ≤0.35(IC≤0.08, h=14)→ 26 名窗禁 discovery 主張、禁 KILL;primary-endpoint 設計為必需品 |
| MF3 | MEDIUM | high | h=14/28 demo 實作與 holding_hours_max=168h 衝突;首發限 h=7 或 operator config 決策 |
| MF4 | MEDIUM | high | funding 2yr 未回補前,任何 net 統計標 provisional(P0-1) |
| MF5 | MEDIUM | medium | DB f32 鏈精度;parquet f64 重建為研究面標準(P0-4) |
| MF6 | LOW | high | 功效表建立於 IC-null std≈1/√(N−1)、T/h 有效樣本、iid 近似——真實(fat-tail/相關)功效更低,表列數字為上界;不改變任何結論方向 |
| MF7 | INFO | high | 全結果強制附 survivor 方向標註(momentum 保守/reversal 樂觀);forward 面板為唯一 PIT 無偏 |
| MF8 | INFO | high | 三個 ASSUMPTION 待 P0 替換:N_eff≈10、book vol 12-20%、TC=0.6;替換後表 P3 重算(不觸判定式結構) |

**假陽性候選**:MF6 本身即為「功效表可能過樂觀」的自我申報;另 G4(bear 子窗>0)以點估計判定,存在小樣本翻牌風險——判斷依據:bear 窗 ~9 個月 ≈270d,對 bps/day 級效應 SE 仍大;保留點估計判定(dispatch regime 鐵律的機械化),但 GO 報告須附 bear 子窗 CI 供 operator 目視。

### 8.5 與既有裁決相容性
不觸 maker-nogo(horizon 不同域,EXT §4.2 論證反差);不觸 Rank7/四軸 NO-GO(範式改變合規 06-14 mandate);funding cap 規則、demeaned-β 鐵則、engine_mode 隔離、×365 年化全內建;黑名單零觸碰(§2.3)。

---

## 附錄 A — 判定式速查(機械執行順序)
```
0. 斷言 K=114、primary=M5|h14|EW、輸入 sha256 匹配 → 否則 ABORT
1. P0-1..P0-5 完成檢查 → 未完成:僅允許 provisional 標註運行
2. 跑 5.1 資料品質 → 記錄
3. 建 E26(WF-OOS 串接;taker+funding;demeaned)
4. primary: G1..G9 逐謂詞 → 全真= GO(demo);記錄每謂詞值
5. exploratory: 114 cells 全量統計落盤;Bonferroni 4.39e-4 決策線;BH q=0.10 描述線
6. KILL 檢查:PC(P100 可用)不成立 → 跳過;成立 → K1/K2
7. 皆非 → INSUFFICIENT(-POSITIVE 若 G5 過)+ 機械動作清單
8. verdict JSON 落盤(全謂詞值 + 標籤 + regime 子窗表)
```

## 附錄 B — 本草案引用的可重跑錨
- 面板:`SELECT timeframe,count(*),count(DISTINCT symbol),min(ts)::date,max(ts)::date FROM market.klines GROUP BY timeframe;`(EV FACT A1)
- Regime:`SELECT date_trunc('quarter',ts)::date, min(low), max(high) FROM market.klines WHERE timeframe='1d' AND symbol='BTCUSDT' GROUP BY 1 ORDER BY 1;`(EXT §5.8)
- funding:EV 附錄 R4;slippage artifact:EV 附錄 R5
- 功效/門檻復算:標準正態近似,公式全在 §5.10(t_exp=IC·√(N−1)·√(T/h);PSR 門檻 1.645/√(T−1)·√365)

---
*QC · 2026-07-10 · 預註冊草案 v1(未凍結)。本文件不含任何本地 outcome 統計;凍結與執行排程交 PM。Operator 副本未落(本次 dispatch 唯一寫入=本檔),PM 如需請代複製。*

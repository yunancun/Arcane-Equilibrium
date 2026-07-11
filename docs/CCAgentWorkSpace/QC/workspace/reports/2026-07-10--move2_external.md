# QC EXT 外部情報 — bb_reversion maker 化 fill_sim 重放：方法論文獻掃描 · 2026-07-10

**Agent**: QC（EXT 外部情報員模式）
**範圍**: 純外部文獻/實務掃描（WebSearch/WebFetch），四條研究線：(a) maker 執行 adverse selection 度量、(b) crypto perp passive vs aggressive 實證（散戶量級）、(c) mean-reversion 信號 maker 化陷阱（adverse fill selection / non-execution bias）、(d) fill 模擬 queue 模型慣例。
**邊界**: 全程 read-only；唯一本地動作 = 讀既有報告 + 唯讀查看 `program_code/research/microstructure/fill_sim.py` fill 規則（對齊外部慣例用）。零代碼、零 config、零 runtime。
**證據紀律**: 本報告所有外部數字一律標 **[外部類比]**（≠本地證據；venue/期間/費率結構皆不同）。本地 priors 引自 2026-07-06 maker-nogo（SHA 5d1622994）與 2026-07-09 stage2 報告，不重打。
**黑名單檢查**: 無觸發。引用文獻中 DeLise(2024) 提及 Hawkes/GCHP（可觀測狀態 Markov chain）——Hawkes 不在黑名單（operator mandate 反而點名鼓勵）；HMM/GARCH/VPIN 均未被本報告推薦。無需 RETRACT。
**寫入範圍說明**（小決策自註）: 任務指令限「唯一允許的寫 = QC role workspace 報告檔」，較 role 完成序列的 Operator 副本更嚴格 → 本次不落 Operator 副本，由 PM 決定是否複製。

---

## 1. Executive Summary

外部文獻對「mean-reversion 信號 maker 化」的核心答案是：**任務所懼的 adverse fill selection / non-execution bias 不是 edge case，是已被理論證明 + live 實驗定量的一級效應**，且文獻給出了明確的度量與校正慣例。三個最硬的外部錨點：
1. **DeLise (2024, arXiv 2407.16527)**：limit order fill 與逆向價格移動 100% 掛鉤（實測 P(fill|逆向移動)=0.99），fill 後 midprice 平均逆向漂移 ≈ **0.45 tick ≈ 被動掛單理論半價差收益的 ~90% 被回吞**；1/3 掛單完全不成交且集中在「價格朝有利方向走」的（本應賺錢的）子樣本。[外部類比：10Y 美債期貨]
2. **Market Maker's Dilemma (arXiv 2502.18625)**：Binance BTC perp **散戶量級（最小單）live 實驗 232,897 筆 maker 單**——5s 後報酬為負的單 fill 率 ~90%、為正的單 fill 率 ~10%；queue 尾端 markout −0.775bp vs 頭端 −0.058bp。**「贏家不成交、輸家必成交」有 crypto perp 的直接實證。**[外部類比：Binance，有 rebate 語境]
3. **校正慣例已收斂**：fill-only 記帳 = 結構性樂觀（DeLise 對照：touch-based 100% fill 規則得 85% fill rate，真值 60%；adverse-fill 確定性規則 + 校準 Bernoulli 得 65%，PnL 最貼近 live 基準）。正確記帳 = **per-signal 無條件記帳**（fill / no-fill / reject 三態全入分母，no-fill 計 clean-up/機會成本）——Handa-Schwartz (1996) 起即為正本。

對本線的直接含義：**stage2 的「maker RT ~8.7bps」是樂觀上界**——外部證據說 maker 化唯一無條件拿到的節省是費率差（taker 5.5 → maker 2.0bps/side），半價差 + slippage 的節省大部分會被 negative drift 與 fill selection 回吞。bb_reversion +9.06bps gross（n=28，taker fill 母集）在 maker fill 子樣本上**不可假設保持**——這正是重放實驗要量測的主變數，且本地 `fill_sim` 的 3-case resolver（fill/adverse_through/no_fill）+ back-of-queue 保守 + beta-residual markout 架構**已對齊外部最嚴慣例**，缺的是信號條件化 + 無條件記帳 + 長 markout 窗三件事（§5）。

**判定：PROCEED（研究線繼續），附 §5 的 10 條綁定設計要求。** 本報告不裁決策略本身。

## 2. 理論基礎（外部機制綜述）

**(c) 線主風險的機制拆解**——文獻中同一現象有三個名字，對應三個分量：

- **Negative drift / mechanically-induced adverse fill**（DeLise 2024；Market Simulation under Adverse Selection, arXiv 2409.12721）：離散價格網格上，價格逆向移動一格 = 你的 limit level 被穿 = 必然成交（且成交在舊 touch = 新的劣勢側）。故「成交」事件與「逆向移動」事件不獨立——假設獨立（Poisson/exponential fill rate，Avellaneda-Stoikov 2008、Cartea et al. 2015 教科書模型）**必然**高估 PnL。這是確定性機制，不是統計偏差。
- **Adverse fill selection on the signal**（MM Dilemma 2025）：fill 機率與 post-fill 報酬**負相關**（90%/10% 不對稱）。對信號策略：信號正確（價格立即回轉）→ limit 不被觸及 → 不成交；信號錯誤（價格續跌穿）→ 必成交。**maker 化把交易母集換成「信號較差的子樣本」**——這是「信號變質」的形式化。
- **Non-execution bias**（Handa-Schwartz 1996, JF；Lo-MacKinlay-Zhang 2002, JFE）：limit order 策略兩風險 = 逆向資訊事件觸發不想要的成交 + 有利消息時想要的成交拿不到。評估必須**無條件**（含未成交結局），僅報 fill-conditional 統計 = selection bias。Lo et al. 進一步證明 **first-passage-time（touch-based）假想成交是實際 limit-order 成交的「very poor proxies」**（低估成交等待時間 = 樂觀），需 survival analysis 級別的建模。

**對 mean-reversion 的雙面性**（本線特有）：contrarian 信號的買方 limit 掛在正在下跌的價格路徑上——adverse fill 把 entry 推得更深，若 mean-reversion alpha 為真，更深 entry = 更好價格（**部分**對沖 fill selection）。但 DeLise §6 直接回應此論點：即使短期 alpha 信號與未來移動相關 15-25%，negative drift 仍「heavily affects」策略——**信號質量不豁免此成本，只能攤薄**。本地 n=3 的 bb_rev maker markout −2.37bps（全策略最溫和，vs flash_dip −12.68）方向上與此相容，但 n=3 = INFERENCE，不可承重。

## 3. 數學模型（度量與校正的形式化）

### 3.1 markout 度量慣例（(a) 線）

- **定義**（Databento microstructure guide）：markout = fill 事件前後某窗的價格變化；參考價慣例 mid-to-mid / fill-to-mid；多窗計算後平均成 **markout 曲線**（單點窗 = 不合格）。
- **窗選擇**：HFT MM 文獻用 1s（主）+5s（MM Dilemma）；實務 toxicity 窗「幾 μs 到 10 分鐘，按資產」（Multicoin 2026-02），原則 = **窗 ≥ 對沖/scratch 所需時間**；對信號策略應延伸到**持有 horizon**，短窗（AS 分量）與長窗（信號存活分量）分離報告。本地 fill_sim 的 5/15/30s 屬 MM 慣例窗，對 bb_reversion（1m 級信號、多分鐘持有）**只夠量 AS、不夠量信號存活**。
- **beta-residual 化**：本地 fill_sim 已做（30min rolling beta, shift(1)）——外部多數研究**未做**此步（用 raw mid 移動），本地慣例嚴於外部，保留。
- **queue position → AS 劑量反應**（MM Dilemma）：同一價位，隊尾 fill 的 markout（−0.775bp）系統性劣於隊頭（−0.058bp）[外部類比]——因隊尾 fill 更大機率來自 level 被穿而非自然輪轉。**度量含義：markout 必須按 queue 位置分層報告**，本地 fill_sim 的 front/mid/back sweep 已符合。

### 3.2 無條件記帳（(c) 線校正正本）

per-signal 三態結局，凈值恆等式：

```
E[net | maker 政策] = P(fill) · (gross_fill_subsample + price_improvement − AS − 2·fee_maker)
                    + P(no_fill) · clean_up
                    + P(reject) · clean_up_reject
其中 clean_up ∈ {0（放棄信號，計機會成本入政策對比）, taker fallback 實付成本}
```

關鍵：**gross_fill_subsample ≠ gross_all_signals**（=本地 +9.06bps 的母集）。兩者之差 = adverse fill selection 的直接量測，是本重放實驗的第一輸出量。對照政策必須同信號集三軌並列：taker-at-signal（基準）/ maker-skip / maker-with-timeout-fallback。

### 3.3 fill 模擬規則層級（(d) 線慣例）

外部工具收斂出的保守序（由樂觀到保守）：
1. **touch-based 100% fill**（價格觸及 = 成交）——DeLise 實測 fill rate 85% vs 真值 60%，PnL 完全失真；**僅可作上界**。
2. **exponential/Poisson fill rate**——inter-arrival 實際重尾（Pareto-like），校準後 fill rate 30% vs 真值 60%，且無 adverse-fill 邏輯 → PnL 仍樂觀。**不建議**。
3. **確定性 adverse fill + 校準非逆向 fill rate**（DeLise T3）——65% vs 60%，PnL 最貼近；load-bearing 的是 adverse-fill 確定性規則。
4. **queue 狀態機**（hftbacktest / NautilusTrader 慣例）：掛單時 snapshot 同側 depth = size_ahead；同側 trade at-or-through 遞減；價穿 level = 必成交。hftbacktest 最保守變體 = RiskAdverseQueueModel（僅 trade 推進隊列）；機率變體 ProbQueueModel f(x)=x^n，n∈[1,3] 越大越保守；L2 足夠 BBO 級研究、真 MM 需 L3。**共同假設 = 自單無市場衝擊**（最小單量級下標準，需明示）。
5. **through-print only**（僅價格實穿才算 fill）——最保守下界。

**本地 fill_sim 已在第 4 級**（queue 狀態機 + adverse_through 獨立結局 + no_fill 入分母 + back-of-queue 默認 + cancel 推進不觸發成交 + 窗截斷計 no_fill），與外部最嚴慣例同級或更嚴。維持雙規則帶（touch 上界 / through-print 下界）夾住真值即為完備。

### 3.4 PostOnly reject 進 net 估計（(a3) 線）

- Bybit 機制：PostOnly 若會立即吃單 → 拒單（官方 help center；Chase order 連續 5 次 reject → 策略取消）。reject 主因 = 報價延遲 × 短窗波動（quote 已 stale）。
- Oxford Albers-Cucuringu-Howison-Shestopaloff（Bybit+Binance 數百萬單 live 實驗）：marketable limit「failing-to-fill-immediately」機率可觀且**可用 parsimonious 參數模型估計後注入回測**——校正方向 = 把 reject/fail 機率建為（延遲、波動、spread 狀態）的函數，而非常數。
- 實務粗數（低可信度，見 §6 假陽性）：reject 率 0.5-2% + 「kill-rate 壓力測試」慣例 = 隨機殺 1-2% 委托觀察策略退化斜率——若結論翻轉 = 策略過擬合完美執行。
- **淨估計慣例**：reject = 一種 no_fill（同入分母），另加 resubmit 延遲成本；報告 reject 率敏感度帶（0/1/2/5%）而非單點。

## 4. 成本分析（外部數字對本地估計的修正方向）

| 分量 | stage2 隱含（maker RT ~8.7bps 假設） | 外部證據修正 | 可信度 |
|---|---|---|---|
| 費率差（5.5→2.0bps/side） | 全額節省 | **唯一無條件節省**（不依賴 fill 質量），entry 腿 3.5bps、雙腿 7bps | 高（費率表是硬事實） |
| 半價差捕獲（majors ~0.5-2.5bps） | 隱含全拿 | negative drift 回吞 ~90%（TY 類比）；本地 maker-nogo 已實測 pooled hs 0.74 < adv 0.85 | 高（雙源一致）[外部類比] |
| slippage 節省（taker E\|slip\|~6bps/leg） | 隱含全拿 | 部分真實（不吃單=不付衝擊），但被 **fill selection 換走母集**——省的是價差、換的是更逆向的子樣本 | 中 |
| 信號 gross +9.06bps | 隱含不變 | **不可假設保持**：90/10 fill 不對稱下 fill 子樣本 gross 可能顯著低於全信號 gross；mean-reversion 的「更深 entry」僅部分對沖 | 高（機制）/未知（幅度=實驗主變數） |
| 未成交機會成本 | 未計 | 1/3 量級不成交（TY 類比）且集中在贏家側；必入三軌對比 | 高（機制）[外部類比] |
| PostOnly reject | 未計 | 0.5-2% 級（低可信）+ 敏感度帶處理 | 低 |

**結論**：maker 化的誠實期望 = 「費率差 7bps RT 級的可靠節省 + 一個符號未知的（fill selection − 更深 entry）殘差」，而非 10.8bps 全額。cost_edge_ratio 以可靠分量重算：gross 9.06 vs maker RT 下界 ~12-15bps（8.7 + drift/selection 回吞 3-6bps 帶）→ ratio 仍 >1 的機率不低。**重放實驗的價值恰在把這個殘差從 ASSUMPTION 變成量測值**——外部文獻無法替量，只能給度量方法（§5）。

## 5. 回測驗證要求（fill_sim 重放的 10 條綁定設計要求，供預註冊）

1. **信號條件化**：hypothetical 掛單只在 bb_reversion 信號時點觸發（替換 fill_sim 固定節奏掛單），信號定義凍結 + shift(1) leak-free。
2. **per-signal 無條件記帳**：fill / adverse_through / no_fill / (reject) 全入分母；輸出 fill-only 與 unconditional 兩版並列，兩者之差 = selection bias 量測值（本實驗第一輸出）。
3. **三軌政策對比**（同信號集）：taker-at-signal（實測 19-23bps RT 基準）/ maker-skip / maker-timeout-fallback（timeout 承 2026-04-20 教訓 = 0.5-0.75× cooldown 起步，fallback 計 clean-up = 劣化價 + taker fee）。
4. **雙 fill 規則帶**：touch-based 上界 + through-print 下界並列；主報告用現行 queue 狀態機（back-of-queue 默認），前/中/後隊列劑量反應保留。
5. **markout 曲線延窗**：5/15/30s（AS 分量，beta-residual 保留）+ 60s/5m/持有全程（信號存活分量）；短窗與長窗分量分離報告，不得只報單窗。
6. **fill 率按信號結局分層**：P(fill | 信號事後為贏家) vs P(fill | 輸家)——直接檢驗 90/10 不對稱是否在本 venue/信號上重現。[MM Dilemma 度量複製]
7. **PostOnly reject 敏感度帶**：0/1/2/5% 隨機拒單 + resubmit 延遲，報退化斜率；斜率陡 = 結論不穩。
8. **樣本判準沿用預註冊紀律**：n_eff 去重（承 07-10 反事實預註冊三件套）、day-cluster、n_fills < 門檻不出顯著性宣稱（fill_sim 既有 honesty gate 保留）；bb_reversion n=28/30d 本身饑餓，任何正結論標 Conditional 直至 ≥200 signal events。
9. **regime 標註**：重放窗若落 bull-heavy 期 → 結果標 regime-bet/learning-only；短 bias 檢查 demeaned beta 中性（06-03 鐵則）；L1 留存 18 regime-days 的覆蓋面在報告中明示。
10. **無市場衝擊假設明示**：最小單量級下標準假設，但報告必須聲明（hftbacktest 同款免責），且不得外推到放大 size。

## 6. 風險分析（findings 全量 + 假陽性候選）

| # | Finding | Severity | Confidence |
|---|---|---|---|
| F-EXT-1 | adverse fill = 確定性機制（價穿必成交），fill-only 記帳結構性樂觀；重放若不三態記帳 → 結論無效 | HIGH | 高（理論證明+雙 venue 實證） |
| F-EXT-2 | fill 率與 post-fill 報酬負相關（90/10，Binance BTC perp 散戶量級 live）→ 贏家不成交偏差必須直接量測（§5-6） | HIGH | 高 [外部類比] |
| F-EXT-3 | stage2「maker RT ~8.7bps」為樂觀上界；可靠節省僅費率差 ~7bps RT，其餘為符號未知殘差 | MEDIUM | 高（機制）/中（幅度） |
| F-EXT-4 | 現行 5/15/30s markout 窗不足以支撐信號 horizon 級結論，需延窗至持有全程 | MEDIUM | 中 |
| F-EXT-5 | PostOnly reject 未進現行 net 估計；latency-conditional，常數化處理不當 | MEDIUM | 中 |
| F-EXT-6 | touch-based/exponential fill 規則的失真已被定量（85%/30% vs 60%）；本地工具已規避，列為回歸守門 | LOW | 高 [外部類比] |
| F-EXT-7 | 自單無衝擊假設（標準但須明示，禁 size 外推） | INFO | 高 |
| F-EXT-8 | mean-reversion 是 maker 化最不壞的信號類（本地 n=3 markout 最溫和 + 「更深 entry」部分對沖），但外部證據明言信號不豁免 negative drift——正面先驗僅 INFERENCE 級 | INFO | 低（n=3） |

**假陽性候選（列出不剔除，裁決交 PM/operator）**：
- 「PostOnly reject 0.5-2%」：Medium 練習者文章，無 venue/樣本說明，非 crypto 特定 → 僅作敏感度帶端點，不作點估計。
- 「Binance 零費率實驗使價差變寬」：來自搜尋摘要層，未溯源原文 → 引用時標未驗證。
- MM Dilemma 的 −0.3bp「net of rebate」：Binance 有 rebate 語境；Bybit VIP0 maker = +2bps 費用，同倉位本地更差 ~2.3bps/side——**方向對本線不利，非有利**。
- DeLise 數字全部來自 10Y 美債期貨（tick 制、單一 venue、TT 模擬器基準）——機制可移植、**幅度不可移植**，僅作結構類比。

## 7. 容量估算

本線為 demo 研究 + 最小單量級：majors touch 隊列深度 >> 自單 size，無衝擊假設成立帶內；容量不是本階段約束（與 stage2 §7 一致）。唯一容量相關外部提示：crypto perp spread 分佈（mean 15.3bps / median 7.5bps，994,088 symbol-hour）[外部類比，MDPI 期刊，中等可信] 說明跨 symbol 半價差異質性大——重放應保留 per-symbol 分層，禁 pooled 單值結論（maker-nogo「wide-spread 不救」已在本地確認同構結論）。

## 8. 建議

**PROCEED（研究線繼續）**：bb_reversion maker 化 fill_sim 重放值得做，且外部文獻把「怎麼做才不自欺」的度量學完整給出了。條件：§5 十條進預註冊，特別是 #2（無條件記帳）、#3（三軌對比）、#6（贏家/輸家 fill 率分層）三條為 go/no-go 判讀的承重牆。
**翻案條件預留**（若重放結論為 NO-GO）：(i) fill 子樣本 gross 顯著 < 全信號 gross 且費率差節省不足補 → 殺 maker 化但保留 taker 版 bb_reversion 的 horizon 延長研究；(ii) 若 fee tier 變動（VIP1+ 或 RPI taker 免費腿，見 07-09 EXT 掃描）→ 成本輸入重算，重放無需重跑（成本是後乘項）。

## Sources（外部，按線）

**(a) markout / AS 度量**：[Databento microstructure guide — markout](https://databento.com/microstructure/markout)；[QuestDB markout cookbook](https://questdb.com/docs/cookbook/sql/finance/markout/)；[The Market Maker's Dilemma (arXiv 2502.18625)](https://arxiv.org/html/2502.18625v2)；[Limit Order Strategic Placement with Adverse Selection Risk (Lehalle-Mounjid, arXiv 1610.00261)](https://arxiv.org/pdf/1610.00261)；[Multicoin — Adverse Selection Rules Everything Around Me](https://multicoin.capital/2026/02/17/adverse-selection-rules-everything-around-me/)
**(b) crypto perp passive vs aggressive（散戶量級）**：[MM Dilemma live 實驗（同上）](https://arxiv.org/html/2502.18625v2)；[The Good, the Bad, and Latency (Oxford ORA)](https://ora.ox.ac.uk/objects/uuid:cdab1de2-7576-42e2-abae-ab12371eba76)（[SSRN 4677989](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4677989) 403 未取全文）；[Temporal Dynamics of Crypto Perp Microstructure (MDPI)](https://www.mdpi.com/2227-7072/14/5/103)；[Adverse Selection in Cryptocurrency Markets (Tiniç-Sensoy)](https://nottingham-repository.worktribe.com/OutputFile/40584797)
**(c) mean-reversion maker 化陷阱**：[The Negative Drift of a Limit Order Fill (DeLise, arXiv 2407.16527)](https://arxiv.org/abs/2407.16527)（全文已抽取）；[Handa-Schwartz 1996 Limit Order Trading (JF)](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1996.tb05228.x)；[Lo-MacKinlay-Zhang 2002 Econometric Models of Limit-Order Executions (JFE)](http://web.mit.edu/Alo/www/Papers/JFE2002_Pub.pdf)；[Deep Learning Fill Probabilities (Columbia)](https://business.columbia.edu/sites/default/files-efs/citation_file_upload/deep-lob-2021.pdf)；[Market Simulation under Adverse Selection (arXiv 2409.12721)](https://arxiv.org/pdf/2409.12721)
**(d) queue 模型慣例**：[hftbacktest Order Fill docs](https://hftbacktest.readthedocs.io/en/latest/order_fill.html)；[hftbacktest Probability Queue Models](https://hftbacktest.readthedocs.io/en/latest/tutorials/Probability%20Queue%20Models.html)；[hftbacktest repo（Binance/Bybit 範例）](https://github.com/nkaz001/hftbacktest)；[NautilusTrader backtesting docs](https://nautilustrader.io/docs/latest/concepts/backtesting/)；[Moallemi-Yuan Queue Position Valuation](https://moallemi.com/ciamac/papers/queue-value-2016.pdf)；[Deep Learning Meets Queue-Reactive (arXiv 2501.08822)](https://arxiv.org/pdf/2501.08822)
**(a3) PostOnly/reject**：[Bybit Post-Only Order help](https://www.bybit.com/help-center/article/Post-Only-Order)；[Bybit Chase Limit Order（5 次 reject 取消）](https://www.bybit.com/en/help-center/article/Chase-Order)；[練習者 kill-rate 慣例（低可信）](https://lukasavi-34031.medium.com/why-90-of-profitable-backtests-are-useless-9c2a46603aff)

QC AUDIT DONE: docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-10--move2_external.md

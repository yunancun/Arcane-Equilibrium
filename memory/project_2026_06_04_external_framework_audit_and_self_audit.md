---
name: project_2026_06_04_external_framework_audit_and_self_audit
description: "外部 LLM-alpha 框架(RD-Agent(Q)/AlphaAgent/QuantaAlpha)+量化skill庫+RevolutX 借鑒評估,並對「我們自己」做代碼級對抗自審——揭露多處 overclaim;待決 P0 β-penalty"
metadata: 
  node_type: memory
  type: project
  originSessionId: 02609da3-dfb2-4b95-913a-0f995648f446
---

# 外部框架借鑒 + 代碼級自審 (2026-06-04) — 暫停於 usage limit,待重置接續

承 [[project_2026_06_03_v58_archive_audit_s2_design]] / [[project_2026_05_31_v58_alpha_pivot]]。operator 給兩篇知乎(Claude Code 挖 alpha 軟文 + FinceptTerminal 產品 pin),要求判斷對我們的幫助,進而**用查驗論文同等強度對抗自審我們自己的程序**(明令:勿盲信自研完整度、勿膜拜對方;對方=many-eyes open project,我們=solo)。並行評 RevolutX API/下單邏輯作基建借鑒。

## 暫停點 / RESUME ENTRY
乾淨停止:4 個自審 agent 全回、結論已綜合、**無 agent 在途**。**待 operator 拍 A/B**:
- (A) 出 **P0 設計 spec**(β 殘差化模組介面 + LG-5 `evaluate_r_beta` 接入 + CC invariant 守護),派 PA/QC 設計。
- (B) 先把本結論 + 記憶漂移修正寫進 memory(本檔已做一半),再開工。
- 我的建議:**先 P0**(最小、正中根因、順手修 overclaim)。重置後從這裡接。

## 驗證過的外部資產(真實存在)
- RD-Agent(Q): arXiv 2505.15155 + github microsoft/RD-Agent(建在 Qlib,NeurIPS2025,Co-STEER+2-arm MAB,<$10/2×ARR/省70%factor)。**驗證比我們弱**(無 DSR/PBO/embargo;在同一測試窗反覆選 beat-SOTA)。
- AlphaAgent: arXiv 2502.16789(AST 新穎度懲罰對抗 alpha decay)。**錯配**:治真 alpha 的擁擠,非我們的「假 alpha=beta」。Originality⊥Realness。
- QuantaAlpha: arXiv 2602.07085 + github QuantaAlpha/QuantaAlpha(DSL+trajectory 變異/交叉)。同樣無 DSR/permutation/embargo。知乎軟文(claudemax.shop 廣告,GPT-5.2 數冒充 Claude Code)。
- Skill 庫:VoltAgent(24k★,README 索引非可裝)、K-Dense 搬到 K-Dense-AI/scientific-agent-skills(27k★,我們已整合134)、jeremylongshore(2810 web3/DeFi 批量低質)、tradermonty(美股,但 edge-* 流水線可借**流程**:signal-postmortem regime-tagged / strategy-pivot-designer 的 cost_defeat 觸發器 / edge-strategy-reviewer C1-C8)。
- 3 個外部深挖 agent(可 SendMessage 續):RD-Agent=a6e544e37f753d34d / AlphaAgent(QC)=aab2932215f0874d5 / 庫=a10a62899efa78c53。

## 自審結果:我 overclaim 了(file:line 證據)
4 個自審 agent:MIT(驗證)=a543d86fc674e5782 / alpha-beta-features=a8cd85edfd141f9c0 / loops=a1e701dcb1c280355 / RevolutX=a37733b59955e54e0。

**核心糾正**:我說「我們驗證比論文嚴」——半對,真相=**上游(發現)弱、下游(治理/存活)強**。
- **最嚴重**:`beta_quant.py`/`cascade_fade_eval.py`/`dream_counterfactual.py` **不在倉內**,只在 `trade-core:/tmp/openclaw/monitor_12h/`(臨時、即蒸發),`beta_quant.py` **β 硬編碼=1.0 非回歸**。`−1.25bps t=−0.56` 只活在 MEMORY.md。**倉內無可複用 β_BTC 殘差化器**。最接近:funding_tilt_diagnostic/stats.py:209(PCA N_eff 濃度)、cost_model.py:115(carry_share 純度)、signals.py:154(離線截面 tertile rank)——都非 alpha-vs-beta 殘差化。
- 「嚴格驗證 alpha」=**假**。DSR(dsr_gate.py:227,257;governance_hub_live_candidate_review.py:253,1377=R4)/PBO(pbo_gate.py:217)/CPCV(cpcv_validator.py:171-189)數學**正確**,但 gate 的是 **ML 模型再訓練 + Demo→Live 晉升**,新策略候選**不經過**。R4-DSR 在 **K<5 pending 時整個 skip**(:1385)→平常 inert。PBO=advisory-only。CPCV=soft(reference-only)。
- **permutation test=完全不存在**(0 命中);**HAC/Newey=只在 research 一次性腳本**,零生產。walk-forward(edge_estimate_validation.py:116,126)purge 默認0、無 embargo。selection_bias_validator.py:203=DORMANT(0 caller)。
- 殘留洩漏:multiday_trend_diagnostic/data_loader.py:300 full-sample vol-tercile look-ahead **仍在**(funding_tilt fork :407-420 已修未回移植)。
- 策略清單:registry.rs:54-323 共 **9 個**,4 個 WIRED-LIVE 全 textbook-TA(ma:58/bb_reversion:88/bb_breakout:108 demo-only/grid:183);funding_arb:242/harvest:257/short_v2:278/**liquidation_cascade_fade:300** 全 dormant。cascade_fade 連 producer→slot 都沒 spawn(step_4_5_dispatch.rs:255)=雙重休眠。「實跑全是 alpha-deficient TA」**成立**。

## 好消息(我之前低估的)
**crypto-native 特徵面已建好、WIRED-LIVE、新鮮**(market_writer.rs):klines 1.9M(:243)、tickers 57M 含 mark/index/OI(:299)、funding(:525,live+730d backfill)、OI 179k+348k backfill(:553)、**liquidations 150k/14.7k日(:498)**、**orderbook depth 1.46M imbalance/depth(:412)**、long/short(:586)、**CVD/trade_agg 1.47M(:447)**。**只有 basis 薄(panel.basis_panel 6 天,V115)**;on-chain/cross-exchange 缺;btc_lead_lag_panel 0 行(paper-fenced)。→ 「得先建 ingestion」是**錯的**,非-OHLCV alpha 搜索**今天就能離線開跑**。

## 4 個可借閉環 vs 我們真碼
- **Loop1 cost_defeat NO-GO=PARTIAL**:cost_edge_advisor.py:239-327(env-OFF 默認 :123/:317)+R5(governance...:1053,bands:119-120)。**無 expectancy/profit_factor abandon 規則**(grep 空)。5 次 NO-GO 全手做。
- **Loop2 regime-tagged postmortem→權重=PARTIAL**:plumbing 健全(outcome_backfiller.rs NULL bug 已修 commit 5e2981d;linucb_trainer.py:253-303 真 post-fee bandit reward)。**缺 TP/FP/regime@entry-vs-exit 分類**;strategist_weights.py:116,179,182,216 只吃 LLM/pattern confidence、無 sample gate、fail-open=與 realized PnL 斷開。
- **Loop3 proposal-time 評分=HAVE(有一缺)**:lg5_review_consumer_scheduler.py(spawn main.py:544)自主跑 R1-R6,R4 DSR deflation(:995-1050)、R5 cost(:1053)。**但 grep beta=0——完全無 beta/market-neutral 懲罰**=殺你 5 次的維度沒接進這個自主閘。← **最高槓桿**。
- **Loop4 signal-as-code 閉環=PARTIAL(只到 param)**:replay_runner.rs(CLI,agent 可驅,但只 replay 既有命名策略 :346-367)+evolution_engine.py:215-249(對現有策略**只 grid search 調參**)。無「LLM 提新 signal→自動回測→迭代」。新候選全手寫一次性腳本。
- **DSL=MISSING**:strategy_params.rs 5 個固定 Rust struct(MaCrossover:23/BbReversion:211/BbBreakout:352/GridTrading:634/FundingArb:800),**無表達式求值器**→QuantaAlpha 式演化搜索在底座上無法表達=greenfield。

定位:**它們強在上游發現迴圈+factor DSL;我們強在下游治理(DSR deflation/PSR/cost band/hard veto/sample gate/Decision-Lease,它們都沒有)。我們缺口在上游,非下游。**

## RevolutX(基建借鑒)=幾乎沒得借
有正經多層 API(REST+FIX4.4+Ed25519+官方 TS SDK)但 spot/retail/REST-polling。我們 Bybit 棧幾乎每軸更成熟(WS fills/rate governor/incident SM/5-source reconciler/precision)。**唯一值得借~5 行**:強制 client-order-id auto-mint——我們 orderLinkId 在 order_manager.rs:387 是 optional,讓 place_order 在 None 時默認鑄一個,杜絕 ack-lost 重試重複單。Ed25519 非對稱簽名架構更佳但 Bybit 是 HMAC=不可移植,留給未來 venue。

## 榨乾後行動方案(ROI×根因)
- **P0**(小,最高 ROI):β 殘差化做成**倉內可複用模組** + 接進 LG-5 做 `evaluate_r_beta`。自動攔「beta 偽裝 edge」,修掉「無 β 殘差化器」overclaim。零件已在 funding_tilt_diagnostic。
- **P1**(中,離線):用**已 live 的非-OHLCV 特徵**跑 beta-中性截面 + net-of-cost 構造,先確認有無清成本的 dispersion alpha(N_eff≈2.0/PC1≈BTC 主導=截面薄,先驗統計力)。算法已在 funding_tilt_diagnostic/signals.py:154 原型化。**先確認有礦再說**。
- **P2**(中/小):Loop2 加 TP/FP/regime 分類層+sample-gated 權重;Loop1 寫 cost_defeat 自動 NO-GO。
- **P3**(大,有前提):factor DSL + signal-as-code 閉環=open project 核心優勢、我們最大 greenfield。**僅 P1 出綠燈才建**,前端借它們架構、後端用我們更強治理閘。
- 機會:RevolutX orderLinkId 默認鑄造(~5 行)。
- 邏輯:先修測量(β)→就緒特徵離線確認有礦(P1)→有礦才工業化(P3)。

## 待修記憶漂移(prep TODO,重置後做)
[[project_2026_06_03_blocked_signal_and_cascade_fade_nogo]] 末句「資產 dream_counterfactual.py+beta_quant.py+cascade_fade_eval.py」=**誤導**:那是 /tmp 臨時腳本(已蒸發)非倉內資產。MEMORY.md 已超 24.4KB 限,順手該 trim。**教訓再現:記憶把 ephemeral run artifact 當系統能力——operator 要求查真碼是對的**。


---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態)

- [外部框架借鑒+代碼級自審 (2026-06-04,暫停待 usage 重置)](project_2026_06_04_external_framework_audit_and_self_audit.md) — 評 RD-Agent(Q)/AlphaAgent/QuantaAlpha+量化skill庫+RevolutX,並對抗自審我們真碼→**揭露我多處 overclaim**:`beta_quant.py`等是 /tmp 蒸發腳本**非倉內資產**(β硬編=1.0)、「嚴驗 alpha」實=只 gate ML 再訓練+Demo→Live晉升(新策略不過 DSR/PBO,R4 在 K<5 skip)、permutation/HAC 不存在或只 research。定位=**上游發現弱、下游治理強**(LG-5 自主閘 R1-R6 有 DSR deflation 但 **grep beta=0=殺你5次的維度沒接進**)。好消息:非-OHLCV 特徵(funding/OI/liq150k/orderbook1.46M/CVD)已 live,今天可離線搜。**待 operator 拍 A/B,建議先 P0**(β殘差化模組+`evaluate_r_beta`)。RevolutX 僅借 orderLinkId 默認鑄造~5行。RESUME 見該檔

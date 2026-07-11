---
name: project_2026_07_09_profit_diagnosis_roi_map
description: 2026-07-09 ultracode 盈利研判第三輪:F1 偽複製推翻 NEAR 候選、30d true net −406 USDT fee-dominated、34 診斷+31 機會 → 11 條 ROI top_moves(反事實管線修復居首);conductor 三項親證
metadata: 
  node_type: memory
  type: project
  heat: 1
  originSessionId: 44dcb981-21bd-4402-aed2-973fd12f7f5f
---

# 2026-07-09 盈利研判第三輪(ultracode profit-diagnosis)— ROI 機會地圖

凍結 SHA `a71b5ed93`(三端一致);8 agents(Evidence MIT/AI-E → Probe QC/BB/MIT/AI-E/EXT → Map PA),1.16M tokens,read-only 全程遵守。承 [[project_2026_06_13_profit_diagnosis_searchspace_reconfirm]](第二輪)、[[project_2026_07_06_maker_first_nogo]]、[[project_2026_07_08_profit_first_autonomy_loop]]。

## Conductor 親證三錨(2026-07-09,可重跑)

1. **F1 偽複製(CRITICAL)**:NEAR 候選 5058 outcomes = 2 distinct entry_ts(×2614 +70.28bps / ×2444 +59.32bps),n_eff≈1-2,單日 episode regime-bet 非 edge。根因=`outcome_review.py` 無 per-(cell,entry_ts_ms) 去重。→ 詳見 profit-first loop topic 檔演變軌跡節。
2. **30d true net −406 USDT,fee-dominated**:demo 1011 筆 fee 254.68/gross −148.61;live_demo 44 筆 fee 0.71/gross −2.11;fee=gross 虧損 1.7×;per-fill gross p50=−1.17bps vs taker RT 成本牆 ~23bps。live fills 30d=0,無真金損失。
3. **L1 judge_edge 假死**:ollama 733 fail/15 success(98% 撞 8s timeout,`ollama_client.py:362` 硬編),~180 call/day ×8s ≈24min/day 純延遲稅,AI 對 gate 質量零貢獻。

## 結構判定(承前輪、本輪深化)

- 唯一 gross 正 cell:`bb_reversion` +9.06bps(n=28,16 symbols),扣費 −1.54bps——距 break-even 一個執行檔(maker 化 net≈+0.3bps/RT)非一個 alpha;adverse selection 實為 strategy-conditional(bb_rev markout −2.37 vs flash_dip −12.68),與 maker-nogo 不衝突。
- gate 拒單整體真負(無系統性誤殺)確認;唯一誤殺候選母集=「正 edge<threshold」49,388-71,207 筆,且 conservative_v1 成本 92.3bps ≈4-5× 實測 E[cost]——重算前誤殺項不可知。
- ML 雙死鎖:①標籤斷糧(soak isolation 10d+,realized_fill 7d=14 行);②promotion 死鎖(`decision_shadow_exits`=0 row,V021 writer 從未 spawn → 93/93 model 永鎖 shadow)——writer 通水前一切訓練投入盈利上限=0。
- AI 棧 $0 成本 $0 貢獻:L2 全史 0 call(治理前置本輪首次全齊,剩 operator 一鍵 E2E-1);sonnet-5 intro −33% 至 08-31 期限項。
- 唯一 spread>>fee population:30d 62 檔新上市(含 TradFi 股票 perp,median spread 14.8bps/尾部 115.8bps vs fee 2-5bps)——從未被 fill_sim maker-NO-GO 母體(mature perp 0.02-6bps)覆蓋,非重打舊戰場。
- fee-tier 距離惡化:30d notional $690k=VIP1 的 6.9%(06-19 為 8.4%);BTC funding 從 −1.73% 回正至 +6.77% APR(carry 前提移動中,spread venue 現死市)。

## Top moves(11 條,conductor 已裁決背書)

1. **[defend/FACT] 反事實證據管線修復**:outcome_review dedup+effective-n+實測 slippage 分位雙軌成本,重跑 71,207 母集+33 GROSS_EDGE_POSITIVE cells;**修復前凍結 order-capable dispatch**。E1+QC,$0 數據 ~1 sprint。
2. **[defend/INFERENCE] bb_reversion maker 化 fill_sim 重放**:34M L1 重放擴 markout 樣本 n=3→≥30,破 JS 負 shrinkage 自鎖。QC 判準+E1。
3. **[attack/paradigm] Horizon arbitrage**:日級 cross-sectional beta 中性 long-short,σ(1d) 攤薄成本牆(IC 0.03-0.05 即可跨);1d klines 26 symbols×2yr 在庫。QC 預註冊+E1 離線 backtest。
4. **[defend/FACT] 執行衛生包**:bboSideType BBO-peg PostOnly 消 35.9% postonly_reject+rpiTakerAccess 觀測欄;真省 ~2bps/腿。E1+BB。
5. **[unlock/FACT] 六監測包**:標籤供血/V021 shadow-exit writer 根因/loop n_eff gate/fee-tier/funding+spread venue/maker 費率。PM+BB+E1+operator。
6. **[attack/INFERENCE] TradFi 股票 perp × IBKR read-only anchor**:$0 PIT 偏離統計先導,Bybit 腿即採、IBKR 腿等 G4(ADR-0048 邊界)。
7. **[attack/FACT-基建] 新上市 niche 活化**:operator 授權未來 5 次自動 Gate-B capture(5 週 0 事件);並行極端 funding 結算窗離線 event study(DATAUSDT −1230% APR 親證)。
8. **[learn/ASSUMPTION] Token unlock 供給衝擊軸**:$0 雙時戳 PIT 採集,beta 中性寫進主規格。
9. **[defend/FACT] L1 timeout 校準+L0/L1 shadow A/B**:E1 小時級,AI ROI 首次可測。
10. **[learn/ASSUMPTION] AI 重定位**:方向判斷位→事件/波動解讀層餵 exit/sizing(左尾 p10 −45.65bps 是靶);依賴 #7 數據。
11. **[unlock/FACT] L2 解凍最短路徑**:E2E-1 一次真調用+ai_pricing.yaml sonnet-5 鍵(08-31 前)。operator 一鍵。

## 報告正本

Map:`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-09--profit_opportunity_map_roi_ranked.md`;Evidence×2(MIT/AI-E)+Probe×5(QC/BB/MIT/AI-E/EXT)同日期同目錄結構。evidence_gaps 13 項顯式列於各報告(411M 表未全掃/anthropic 賬單不可外證/L1 延遲右截斷等)。

## How to apply

下輪 priors 注入以本檔 top_moves+親證三錨為基準;#1 未落地前任何 loop 候選的 outcome_count 類統計一律先查 distinct entry;30d −406 USDT 是 demo lane 數字不可外推;attack 類全部要求 QC 預註冊(shift(1)/walk-forward/DSR/cluster-SE/taker 成本上界/beta demean)後才進 Sprint。

## 修復包交付(2026-07-10,operator 批 1/2/3 後)

**全部上線,三端同步 `1a3ecdd57`**。R3 commit 序列:`49049f84d`(WP-A dedup+雙軌成本)→`b7359b2cd`(Gate-B auto-capture)→`473706171`(sonnet-5 鍵)→`10dbfb10b`+`3541bb142`(docs/TODO v780)→收口 `bd582ff89`/`a76e1bc95`/`23c3e87ba`/`1a3ecdd57`(rerun 管線+mutation-biting+TODO v781+cron 接線)。

1. **71k 反事實重跑(預註冊 v1)裁決=`FALSE_KILL_HYPOTHESIS_HAMMERED`**:7/7 tested cells 全 VETO(mean_net_E −23~−67bps,cluster p≈1.0)、**0 翻正**、24 格 DATA_INTEGRITY_SUSPECT 排除(mean 全負同向);NEAR 候選 n_eff=1 `SAMPLE_INSUFFICIENT_AFTER_DEDUP`+`EXECUTION_REALISM_SUSPECT`。**gate 為淨止損,誤殺期望損失上界=0,候選榜=零合格**。conductor 親證 artifact state 欄。
2. **PROFIT-1 追認**:證實雙重扣成本(demo 19d 分支)但**不修 gates.rs**——重跑證明被拒者無統計可辯 edge,修=事實降門檻,硬邊界「Cost Gate 不降級」優先;QC lower-CI floor 重設計=獨立票待 operator 排期。
3. **E2E-1 真 model call 達成**:路徑 A(control API venv 裝 anthropic 0.116.0,修 2026-06-10 以來 latent SDK gap)後 `l2r:724ac38bc4fc` anthropic:sonnet $0.0149/17.8s/3401 字元真回應;TOML byte-identical 復原+12/12 worker enabled=[],**L2 維持全 disabled**。follow-up:executor 不剝 markdown fence→lessons sink 0 row(fence-parsing 票,PA 鏈)。
4. **Gate-B auto-capture 已活化**(AMD-2026-07-10-01):cron 兩行(30min 帶 flag+05:26 深掃 10 頁),smoke `enabled=True cap=5 remaining=5 IDLE`,cap 常量硬釘+持久化計數+audit jsonl。
5. **funding 結算窗 event study=REJECT**:|F|>30bps 2yr 僅 11 事件(10 個=2025-10-11 清算瀑布,n_eff≈2)SAMPLE_INSUFFICIENT;敏感性 3,894 事件扣 23bps 後全 tier×horizon 淨負;翻案條件=1m klines 回補 2024-06~2026-04。**top_moves #7 的 event study 腿死亡,capture 腿活**。
6. cron 主判已接 `--slippage-artifact`(實測 E[cost] 雙軌);E4 終態:tests/ 814/5/2/0、research 1591/1/4/0、canary 全綠,失敗全 pre-existing 逐字同名單。
7. 未竟 follow-up(全在 TODO v781):fence-parsing sink/QC prereg v2(24 排除格)/hygiene 三票/funding 歷史 stale 38d 採集決策。

教訓:headless `claude -p` 另開 session 需 CLI Keychain OAuth 有效(2026-06-01 已過期,`/login` 是互動式)——desktop 環境下等效方案=Workflow 隔離 subagent 群+conductor 零代碼參與+獨立核驗輪。

## #2/#3 研究輪裁決(2026-07-10,read-only 10 agents,不實作)

- **#2 bb_rev maker 化 → GO_WITH_CONDITIONS 僅作「$0 R1 重放量測儀器」,原敘事死**:60d cell 惡化(gross +3.66/net −7.20,31-60d 符號翻轉;top-day 07-06 佔 30d gross 52%)=「cell 拯救」死;maker markout 有效 **n=1**(且語義=fill-vs-submit-reference 非 post-fill,注釋是 aspiration);+0.3bps/RT 直接檢定需 n≈4,400≈10 年=永不可檢定;**bb_reversion 無 use_maker_entry knob**(僅 ma/bbb/grid @ registry.rs:144/242/272,conductor 親 grep)→ probe=sprint 級 Rust=經濟死;真的東西=entry 腿確定性費率省 3.5bps/RT;真宿主候選=grid_trading(有 knob+8× notional+408 attempts)。**R1 死線 2026-07-19**(l1_events 21d 滾動,錯過=06-28→07-02 episodes 永久蒸發);工作量 ≤1 sprint 純 research Python。
- **#3 日級 XS → GO_WITH_CONDITIONS 僅作 $0 研究管線,不作近期 PnL 線**:26 名窗 P(GO)≤~15%@可信 IC≤0.10(coin-flip GO 需 IC 0.18-0.21=物理不可信);先驗均值 IC 0.03-0.05 下 net 為**負**;上端情境 ~$3-4k/yr@$100k book;預期 ≥85-90% INSUFFICIENT;**breadth=唯一功效槓桿**→Stage B top-100 1d 回補是前置;survivorship 單缺席衰退幣≈全部淨 edge 量級;engine 多日 lane=3-5 sprint 新執行範式,GO verdict 前 0 授權;holding cap:demo=**168h**/live=72h(07-11 對抗核實 REFUTED conductor 早前「76h 校正」——76.0 在不被載入的 legacy risk_config.toml;dossier 原值對;h=14d=336h 仍被截,結論不變。教訓:grep 到值≠被載入,校正前先驗載入鏈)。
- dossier 正本:docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-10--move{2,3}_decision_dossier.md(+各 4 份 QC evidence/external/prereg/redteam);報告未 commit(研究輪 read-only,commit 留待 operator 裁決後)。
- operator 決策點:①R1 是否 07-19 前插隊(或先釘存 L1 切片解死線);②#3 Stage B 三個 --apply 授權;③#3 價值主張接受 vs PARK;④#2 grid_trading 宿主分支要不要 QC prereg v2;⑤registered look 時點表+forward shadow cron。
- **對抗核實 Tier-1 完成(07-10~11,三鏡 PG/代碼/統計,16 claims)**:9 CONFIRMED/6 WEAKENED/1 REFUTED,**兩線 GO_WITH_CONDITIONS 均不翻**。實質修訂:C3=bb_rev 有 `use_limit` maker-entry 別名(boot TOML,GAP-9 gating)→probe 經濟死判詞撤回,真理由=R1 前 premature;C4=「永不可檢定」改 σ-條件句(σ≤2bps 則 ~7.6 個月可檢),R1 首產出=實測 σ_Δ;C8=G8 引用 408 attempts 前先釘定義(三計數 287/1,189/408 不吻合+流 06-19 斷);C15=**move3 v1.1 新增 blocking 前置:H_TREND 邊界節**(NO-GO-TREND 2026-06-02 明文關閉含 XS momentum 的多日 trend 家族,move3 五文件零劃界,劃界失敗則 M 族=reopening 案);C10/C11 headline 點值改假設-條件句(N_eff/TC/slip/vol 未清償,方向結論全立);C12 方向詞更正=survivorship 使動量**低估**(GO-safe)。核實欄+終審綜合在 runbook §六:`PM/workspace/reports/2026-07-10--move23_final_adjudication_and_adversarial_runbook.md`。

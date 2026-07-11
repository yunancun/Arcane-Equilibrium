# #2/#3 研究終審結論 + 對抗核實 runbook(2026-07-10)

**性質**:conductor(主會話)終審結論的可否證存檔。每條結論=claim + 證據等級 + 可重跑錨點 + 否證條件;「核實」欄由獨立否證 wave 回填(見 §四)。本檔不含實作授權——operator 決策單見 §三。

**上游正本**:R3 機會地圖(`PA/workspace/reports/2026-07-09--profit_opportunity_map_roi_ranked.md`)→ 修復包報告(`PM/.../2026-07-10--r3_fix_package_report.md`)→ 兩線 dossier(`PA/.../2026-07-10--move{2,3}_decision_dossier.md`,各帶 evidence/external/prereg 草案/redteam 四底稿,QC workspace 同日)。

---

## 一、終審裁決(兩句話版)

- **#2 bb_reversion maker 化**:GO_WITH_CONDITIONS,**降維為「$0 R1 重放量測儀器」**——原「唯一正 cell 拯救」「maker markout 先驗」「+0.3bps/RT 可驗證」三敘事全死;活下來的是 entry 腿 3.5bps/RT 確定性費率省的量測價值(對 M12 執行路由層,KILL 也有淨值);真宿主候選=grid_trading。**R1 有 2026-07-19 數據死線**。
- **#3 日級 XS horizon arbitrage**:GO_WITH_CONDITIONS,**僅作 $0 研究管線,不是近期 PnL 線**——26 名倖存宇宙 P(GO)≤~15%,先驗 IC 下 net 為負,預期 85-90% INSUFFICIENT;買的是「已預註冊管線+breadth 期權+forward PIT 面板」;breadth(Stage B top-100 回補)是唯一功效槓桿;GO verdict 前 engine 側 0 授權。

## 二、可否證 claim 表

證據等級:FACT=可重跑命令直接驗;DERIVED=由 FACT 輸入推導(攻擊點=輸入與假設);INVENTORY=代碼/配置盤點。

### #2(move2)

| ID | Claim | 等級 | 可重跑錨點 | 否證條件 | 核實 |
|----|-------|------|-----------|----------|------|
| C1 | bb_rev cell 不穩定:30d gross +8.86/net −1.76(29 closes),60d gross +3.66/net −7.20,31-60d 區段符號翻轉,top-day 07-06 佔 30d gross 52% | FACT | `QC/.../2026-07-10--move2_evidence.md` §(a) 內 SQL(trading.fills 按窗聚合) | 重跑 SQL 得 60d net>0 或 top-day 佔比<30% | **CONFIRMED**(PG 鏡:SQL 逐字重跑零漂移;符號翻轉+top-day 51.7% 均在位) |
| C2 | maker markout 有效 n=1,且代碼語義=fill-vs-submit-reference 非 post-fill markout | FACT | `rust/openclaw_engine/src/execution_fill_helpers.rs:26-43` 讀語義;evidence §(b) SQL 數 n | 讀碼發現真 post-fill 窗口計算,或 SQL 數出 n≥5 有效 maker markout | **CONFIRMED**(代碼鏡:語義=fill-vs-submit-reference 屬實,n=1;錨點修正:實檔在 `event_consumer/execution_fill_helpers.rs:27-44`) |
| C3 | bb_reversion 無 `use_maker_entry` knob(僅 ma_crossover/bb_breakout/grid_trading @ registry.rs:144/242/272) | FACT | `grep -n use_maker_entry rust/openclaw_engine/src/strategies/registry.rs` | grep 出 bb_reversion 段有該 knob | **WEAKENED**(代碼鏡:字面成立,但 bb_rev 有**已接線 maker-entry 別名** `use_limit`+`limit_offset_bps`+`maker_price_buffer_ticks`→BBO-aware PostOnly(mod.rs:314-329,registry.rs:161-162 TOML boot 直賦;熱重載被 GAP-9 關閉)——「無 knob→probe 需 sprint 級 Rust」敘事被削弱,見 §六) |
| C4 | +0.3bps/RT 效應的直接統計檢定需 n≈4,400 episodes(≈10 年)=永不可檢定 | DERIVED | dossier §② 推導(σ_episode 輸入自 evidence §(e);MDE@n=30≈5.4bps) | σ 輸入錯一個量級,或存在合法 variance-reduction 設計使 n 降至 O(百) | **WEAKENED**(統計鏡兩驗:算術重現+配對差分已內建、covariate 無法再砍 97% 變異——設計面否證不成立;但 σ_Δ=8bps 是**未實測 ASSUMPTION** 且錨點誤引 evidence §(e)(該檔無 σ);σ=2 時 n≈275≈7.6 個月——「永不可檢定」改 **σ-條件句**,R1 實測 σ 後裁) |
| C5 | `market.l1_events` retention=21d 滾動 → R1 死線 2026-07-19(過期=06-28→07-02 episodes 永久蒸發);穩態可重放 episodes 恆 ≈25 | FACT | ssh trade-core 查 retention policy+`SELECT min(ts) FROM market.l1_events` | retention 實為更長/有歸檔副本;或 episodes 母集實質 >40 | **CONFIRMED**(PG 鏡:drop_after='21 days',episodes=25;07-19 死線算術成立;無歸檔指向證據) |
| C6 | entry 腿 maker 化=確定性費率節省 3.5bps/RT(算術非統計) | FACT | Bybit VIP0 taker 5.5bps/maker 2bps;evidence §(e) 分解 | 費率表不符(查 exchangeInfo/fee-rate API) | **CONFIRMED**(代碼鏡:fill_sim 2.0/5.5、paper_config 0.00055、實付 maker 2.07(n=573)/taker 5.74(n=474)三源吻合) |
| C7 | 單 cell 經濟封頂:宣稱效應 0.77 USDT/月、費率差全額上界 9.0、roster 理論天花板 116.7 | DERIVED | dossier key_numbers;輸入=30d cell notional×頻率 | notional/頻率輸入錯 >2×,或 roster 外推邏輯錯 | **CONFIRMED**(PG 鏡:25,761/29 entries 逐字吻合;roster 今值 346.6k(+4% 窗漂移),天花板 121.3 vs 116.7) |
| C8 | 若目標是可移植 maker lever,經濟正確宿主=grid_trading(現成 knob+~8× notional+408 close_maker attempts) | INVENTORY | C3 grep + evidence §(b) attempts 計數 SQL | grid notional/attempts 數字不符,或 grid 信號結構使 maker 化不可比 | **WEAKENED**(代碼鏡:knob ✓、notional 8.5× ✓;但 attempts 三計數互不吻合(fills 全期 287 / orders 30d PostOnly 1,189 / 底稿 408)且 attempt 流 2026-06-19 後斷——**G8 校準 gate 引用 408 母集前必先釘死 attempt 定義**) |

### #3(move3)

| ID | Claim | 等級 | 可重跑錨點 | 否證條件 | 核實 |
|----|-------|------|-----------|----------|------|
| C9 | 1d 面板=19,776 行/26 symbols/2024-06-02→2026-07-09,唯一缺日 2026-06-27 | FACT | `SELECT count(*),count(distinct symbol),min(ts),max(ts) FROM market.klines WHERE timeframe='1d'`+按日 gap 掃描 | 計數差 >1%,或缺日多於 1 天 | **CONFIRMED**(PG 鏡:19,776/26/2024-06-02→2026-07-09 逐格吻合;缺日恰 2026-06-27 一天) |
| C10 | 26 名 breadth 下 Stage A P(GO)≤~15%@任何可信 IC≤0.10;coin-flip GO 需 IC 0.18-0.21 | DERIVED | dossier §② 功效推導(E26 有效長度≈504d、PSR≥0.95⇔net SR≥1.40、N_eff≈8-12 待 PCA) | 推導鏈輸入錯(如有效長度/N_eff);或存在合法設計使 26 名功效大幅提升 | **WEAKENED**(統計鏡兩驗:推導鏈算術逐步重現、E26≈504d 穩健;但 headline 對 **N_eff≈8-12/TC=0.6 兩個未清償 ASSUMPTION 不穩健**——N_eff=20 → coin-flip IC≈0.129;IC=0.10+低 drag → P≈17.6%>15%。方向結論(Stage A 實質難 GO、breadth=唯一槓桿)全帶成立;點值 bound 改**假設-條件句**;合法功效路徑=pooled E100⊕E_fwd 已被 dossier 吸收) |
| C11 | 先驗均值 IC 0.03-0.05 → net −0.8~0 bps/day(負);上端 IC 0.07-0.08 → +0.8-1.1 bps/day ≈ $3-4k/yr@$100k | DERIVED | 成本線=taker 23bps/RT、h=14 pair 3.29bps/day、banded ≈59bps/月(evidence §(c) 算術) | 成本輸入錯 >30%(如實測 slippage 分位遠低),或 IC→bps 轉換錯 | **WEAKENED**(統計鏡:算術全重現、轉換式無代數錯;但「先驗均值→net 負」的**符號結論在自設否證帶內不穩**——global q50 slip → RT=17bps(−26%)時 IC=0.05 net 翻正 +0.54;mean_abs 軌反向強化負值=雙向不確定;book vol 15%/banded×0.6 未實測。點值改**輸入-條件句**,P0-3 實測 slippage/vol 後定) |
| C12 | survivorship:單一缺席 short-leg 衰退幣 ≈ +0.8bps/day 動量高估 = 與全部淨 edge 同量級;下架公告 REST 可枚舉(442 則) | DERIVED+FACT | redteam §1.2/1.3;公告 API 計數可重跑 | 缺席幣影響量化 <0.2bps/day,或下架清單不可恢復 | **WEAKENED**(統計鏡:量化鏈重現(−58bps/day×5.6% slot×攤薄≈+0.8)+442 則公告 refuter 親跑 live 復現;但**本表方向詞轉錄錯誤**——底稿(redteam §1.3/dossier N13)推導=survivorship 使動量 **低估**(GO-safe),高估通道屬 reversal/Q 族;修正案:「動量低估/reversal·Q 族高估,+0.8bps/day/缺席名」) |
| C13 | holding cap 實值:demo 76h / live 72h / paper 720h(**校正 dossier 記載的 168h**)→ h=14d 持有被硬截,demo-cell≠GO-cell 更強 | FACT | `grep holding_hours_max settings/risk_control_rules/*.toml`+`risk_checks.rs` rm.time | toml 值不同,或存在 per-strategy override 使 cap 不生效 | **REFUTED**(代碼鏡:demo TOML 實值=**168.0**(`risk_config_demo.toml:22`,startup/mod.rs:244-249 載入,缺檔 fail-closed 無 env override)——**conductor 的 76h「校正」本身是錯的**,76.0 在 legacy `risk_config.toml` 不被任何 engine 載入,dossier 原值 168h 才對;live=72h ✓/paper=720h ✓。下游結論不翻:168h×rm.time(0.8-1.5)=有效 134-252h,h=14d=336h 仍被硬截,demo-cell≠GO-cell 仍成立) |
| C14 | engine 多日 lane 若 GO=3-5 sprint 新執行範式(批次權重執行器/hedge overlay/per-leg SL 治理);pre-GO 研究管線 ≈2.5-3.5 sprint、0 熱檔 | INVENTORY | dossier §④ 觸碰面清單 vs 現 orchestrator/PipelineBridge 代碼 | 盤點漏了現成可復用 lane 使成本 <1 sprint | **CONFIRMED**(代碼鏡:主動搜尋 rebalance/target_weight/portfolio 執行器未命中;synthetic_spot=per-symbol paper-only 不可復用;pre-GO 觸碰面與 dossier §4.2 相符。caveat:sprint 絕對值屬估計,只背書盤點完整性不背書工時點估) |

### 跨線

| ID | Claim | 等級 | 錨點 | 否證條件 | 核實 |
|----|-------|------|------|----------|------|
| C15 | 兩線與既有 NO-GO 無衝突:#2 是 execution routing(≠maker-nogo 的 market-making quoting);#3 是 multi-day XS(≠R2 的 1m 方向性 taker 線性 IC) | 裁決 | maker-nogo topic/報告邊界節;R2 裁決文 | 任一 dossier 的檢定其實落回舊 NO-GO 同一母體同一測試 | **WEAKENED**(兩驗互補:具名兩邊界(maker-nogo/R2)成立——母體/統計量/成本結構三重不同,二驗 CONFIRMED;但**全稱句「與全部既有 NO-GO 無衝突」被一驗推翻**:`NO-GO-TREND`(2026-06-02,4-reviewer)明文關閉含 **cross-sectional momentum** 的多日 trend 家族,同一 market.klines 1d 面板、20/26 同名 symbols、窗重疊 ~95%,而 move3 凍結 primary M5=TREND_VC 落其母體,五份文件**零劃界**。處置=move3 v1.1 凍結新增 blocking 前置:增補 H_TREND 邊界節(逐軸差異:XS demean 後殘差空間 vs 其 TS 自相關論證/N_eff=2.087;Stage B breadth=其「backfill 救不了」未覆蓋的獨立-bet 槓桿)+殘餘重疊入 ×0.3-0.5 折減,或明文走 reopening 程序) |
| C16 | RT-13 外溢:risk_verdicts 30d 滾動使 71,207 反事實母集同步蒸發(影響未來複核,不影響已凍結 artifact sha d09bf86c) | FACT | `SELECT min(ts) FROM trading.risk_verdicts`+retention 設定 | retention 非 30d 或已有釘存 | **CONFIRMED**(PG 鏡:drop_after='30 days' 滾動、無釘存;71,207 凍結 SQL 逐字重跑吻合;母集自 ~07-20 起蒸發,已凍結 artifact sha d09bf86c 不受影響) |

## 三、operator 決策單(不動手,等點頭)

1. **#2 R1 排程 vs 先釘存 L1 切片**(死線 07-19;釘存=$0 幾分鐘,解除時間壓力)
2. **#2 grid_trading 宿主分支**:要不要 QC 出 prereg v2(不阻塞 R1)
3. **#3 Stage B 三個 `--apply`**(top-100 1d 回補/funding 2yr/2026-06-27 缺日;$0 冪等;不批=KILL/GO 永不可達)
4. **#3 價值主張**:接受「管線+期權+forward 面板」或改 PARK
5. **#3 forward shadow daily cron**(離線信號+虛擬淨值,不下單)+ registered look 時點表(凍結+6mo/+12mo/Stage B 完成)

## 四、對抗核實 runbook(怎麼攻擊本檔)

- **Tier 0(分鐘級,零 token)**:逐條跑 §二錨點欄的命令/SQL,對照否證條件。任何一條命中否證=該 claim 降級,回報 PM 重裁。
- **Tier 1(本檔已跑,結果在「核實」欄)**:三鏡頭獨立否證 wave——A=PG/runtime 鏡頭(FACT 類 SQL 重跑)、B=代碼/配置鏡頭(INVENTORY 類 grep/讀碼)、C=統計鏡頭(DERIVED 類從輸入重推導)。每個 refuter 的指令=「試圖否證,不確定即判 WEAKENED」,防確認偏誤。
- **Tier 2(盲重推,防敘事錨定)**:開新 session/agent,**不給結論只給問題**(「bb_rev cell 值不值得 maker 化?」「26 symbols 日級 XS 可不可檢定?」)+數據入口(PG recipe+dossier 底稿的 evidence 檔但抹去裁決節),獨立推導後與本檔 diff。分歧點=最值錢的審查發現。
- **Tier 3(全量重審)**:fresh freeze 後重跑 `profit-diagnosis` workflow,args.priors 注入本檔 claim 表——若新一輪 Probe 在同錨點得出矛盾,演變軌跡節記錄推翻。
- 紀律:被推翻的 claim 不原地改寫——在本檔追加「演變」節(日期+轉變+證據),與 memory 治理同構。

## 五、狀態

- 本檔與 10 份研究底稿同批 commit(docs,[skip ci]);實作零啟動;TODO 不動(等決策單)。
- Tier 1 否證 wave 結果回填見「核實」欄;跑於 2026-07-10(PG/統計首驗)+ 2026-07-11(代碼鏡+統計二驗,resume `wf_3726844b-b35`),凍結 HEAD `1a3ecdd57`。統計鏡跑了兩個獨立 pass(usage 中斷副作用),分歧按保守側合成——兩 pass 對算術重現一致,分歧全在「未實測 ASSUMPTION 輸入該不該給 CONFIRMED」,依 runbook 紀律(不確定=WEAKENED)取嚴。

## 六、Tier-1 終審綜合(2026-07-11,conductor 裁決)

**計分:9 CONFIRMED / 6 WEAKENED / 1 REFUTED。兩線 GO_WITH_CONDITIONS 裁決均不翻,但條件單有實質修訂。**

### 對 #2(move2)的修訂

1. **[C3] probe 經濟性判詞更正**:「bb_rev 無 maker knob→bounded probe 需 sprint 級 Rust=經濟死」不成立——`use_limit` 別名鏈=boot-time TOML 即可啟用 maker entry(GAP-9 治理 gating 仍在)。probe NO-GO 的真理由收斂為:**R1 量測前 premature**(cell 統計死+markout n=1),非工程成本。R1 若存活,probe 路徑成本 ≈TOML 翻轉+治理裁決,不是 Rust sprint。「grid_trading=唯一經濟宿主」的 open question 同步失力:bb_rev 自身 TOML-viable。
2. **[C4] 「永久放棄 +0.3bps 直接檢定」改 σ-條件句**:σ_Δ=8bps 是未實測假設(且底稿錨點誤引);R1 第一產出=實測 σ_Δ,若 σ≤2bps 則直接檢定 ≈275 episodes(~7.6 個月)可行,不是 10 年。
3. **[C8] G8 校準 gate 加前置**:attempt 三計數(287/1,189/408)互不吻合+attempt 流 06-19 斷——引用 408 母集前必先釘死 attempt 定義與斷流根因。
4. C1/C5/C6/C7 全 CONFIRMED:R1 儀器形態、07-19 死線、3.5bps 費率省、經濟封頂全部站得住。**R1 GO 維持,死線紀律不變。**

### 對 #3(move3)的修訂

5. **[C15] v1.1 凍結新增 blocking 前置(第 ⑥ 條)**:增補 **H_TREND 邊界節**,對 `NO-GO-TREND`(2026-06-02,4-reviewer,明文關閉含 XS momentum 的多日 trend 家族、同 1d 面板)逐軸劃界(XS demean 殘差空間 vs 其 TS 論證;Stage B breadth=其未覆蓋的獨立-bet 槓桿;CTREND 外部錨後於其入庫),殘餘重疊併入 ×0.3-0.5 折減——或明文走 reopening 程序。**未劃界前 M 族(含 primary M5=TREND_VC)結果不得出爐**,否則與一份未撤銷的 4-reviewer NO-GO 直接對撞。
6. **[C10/C11] headline 點值全部改假設-條件句**:「P(GO)≤~15%」「coin-flip 需 IC 0.18-0.21」「先驗均值 net 負」對 N_eff/TC=0.6/slippage 輸入/book vol 四個未清償 ASSUMPTION 不穩健(N_eff=20 → coin-flip IC≈0.129;q50 slip → 上端 net 翻正)。**方向結論不變**(26 名窗 Stage A 難 GO、breadth=唯一槓桿、非近期 PnL 線),P0-3(PCA/實測 slippage/vol)是清償路徑——這反而強化「先跑 $0 研究管線」的排序。
7. **[C12] 方向詞更正**:survivorship 使動量**低估**(對 GO 決策=保守/安全),高估通道屬 reversal/Q 族;本表原文轉錄與底稿相反,以本節為準。
8. **[C13] conductor 自我更正(REFUTED)**:demo holding cap=**168h**(dossier 原值對,我的 76h「校正」錯——76.0 在不被載入的 legacy toml)。下游結論不翻(有效 134-252h 仍截 336h)。**教訓:校正別人前先驗載入鏈,grep 到值≠被載入。**

### 決策單影響

§三決策單五項**維持原樣**,新增一項:
6. **#3 H_TREND 邊界節**(blocking,QC 出 v1.1 時一併交付;不需 operator 決策,屬執行紀律)——operator 僅需知悉:若劃界失敗,M 族收斂為 reopening 案,#3 剩 Q/carry 族+forward 面板。

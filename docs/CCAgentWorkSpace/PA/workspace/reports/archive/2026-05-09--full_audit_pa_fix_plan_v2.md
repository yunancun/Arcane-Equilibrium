# PA 全 Audit 修復計劃 v2 — 2026-05-09 自我對抗 + v2 整合

**作者**：PA（Project Architect）
**日期**：2026-05-09 (post `da2aba11` + W-AUDIT-8a SPEC PHASE + AMD-2026-05-09-03 land)
**前序文件**：
- `2026-05-08--full_audit_pa_fix_plan.md`（v1 fix plan / 88 finding / 7 wave / ~140h）
- `2026-05-09--full_loss_architectural_root_cause_redesign.md`（5 root cause + Alpha Surface 升級藍圖）
- `2026-05-09--audit_fix_verification_v2_summary.md`（12 agent v2 verification 整合）
- **`2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`**（operator 已採納 R-1 並啟動 SPEC PHASE）
- **`2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`**（4-agent FA/PA/QC/MIT consensus 22 fail-closed defaults 死循環論證 → graduated 5-stage canary supersedes binary fail-closed default）
**HEAD baseline**：`faf2d131`（v2 land 點）→ `da2aba11`（5 commits 後）+ CLAUDE.md §三 已加 W-AUDIT-8a row + §四 已加 executor_canary_stage AMD-03 reference
**性質**：對自寫 redesign 的 self-adversarial 6 點 push back + v2 verification 整合 + 是否需 reset 工作安排決策 + fix plan v2

---

## §0 Critical Update — operator 在 PA 撰報告同時拍板 W-AUDIT-8a + W-AUDIT-9

PA 在撰本 v2 fix plan 過程中發現 operator 已：
1. **將 PA redesign R-1 升級為 W-AUDIT-8a "Alpha Surface Foundation"**（CLAUDE.md §三 已加 row + `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` 已 land）— SPEC PHASE 2026-05-09 / Phase A-D × 4 sprint × ~40 person-day
2. **新建 W-AUDIT-9 "Graduated Canary Foundation"**（AMD-2026-05-09-03 起 / 1.5-2 sprint / 7 sub-task DAG / E1-A 至 E1-G）
3. **AMD-2026-05-09-03 supersedes AMD-2026-05-09-02 §2** 「shadow_mode binary fail-closed default」字面，引入 5-stage graduated canary（shadow / single-symbol-paper / single-symbol-demo / multi-symbol-demo / live-pending），每 stage 條件 fail-closed + auto-rollback 雙鎖
4. **4-agent 共識強度高於單 PA push back**：PA + FA + QC + MIT 共識指向 22 fail-closed defaults 累加 P(全 PASS) ≈ 0 死循環，FA「P0-EDGE-1 雞生蛋蛋生雞」論證採納 — `Π_{i=1..22} P(passi)` ≈ 1e-3 量級即 demo 環境 stationary fixed point 為「0 fill / 0 evidence / 0 edge / 0 promotion」

**對 fix plan v2 的影響**：
- §1 Push Back 1（Strategy Interface 偏差降一檔）**部分被推翻**：4-agent consensus + 死循環數學是更強論證；W-AUDIT-8a 已 SPEC，PA 不再有空間 push back R-1 範圍（仍可 push back 估算工時）
- §1 Push Back 4（W-AUDIT-4 是 R-3 prerequisite）**仍站得住**：AMD-03 §5.4 確認 W-AUDIT-4 ML 基座併入 R-3 Hypothesis Pipeline 的 wave 仍照原計劃
- §4 dual-track 決策**從「PA 提議」升級為「reflect operator 已啟動」**：Track A 不是新建議，是已 active SPEC + AMD landing；本 fix plan v2 改為**對齊 operator 既定路徑 + 補位（Track W 收尾 + W-AUDIT-9 並行 + W-AUDIT-8a SPEC→IMPL handoff）**
- **新加 W-AUDIT-9** 進 Track A：1.5-2 sprint / 7 sub-task / E1-A..E1-G 派發 / 與 W-AUDIT-3/-4/-5/-6/-7 全並行 / **必須在 W-AUDIT-8a IMPL 前完成**（5-stage 機制給未來 alpha source 用）

**自我對抗 verdict 修正**：原 §1 Push Back 1 過度保守。在 4-agent 共識 + 死循環數學論證下，「Strategy Interface 偏差」確實是 architectural 級 root cause，operator 已採納並起動 SPEC，PA 立場應降為「補位 IMPL guidance + 工時校正 + Stage Gate 設計」而非「降一檔 reframe」。其餘 5 個 push back（Root Cause 2/3/4/5 + Alpha Surface 工時校正）仍有效。

---

## §1 Self-adversarial — 對自寫 redesign 6 點 push back

### Push Back 1 — Root Cause 1「Strategy Interface 結構性偏差」是否被 PA 自證為弱?

**自寫定位**：「**最核心**根因」。

**自我對抗**：
PA report §1.1 line 28-30 自承 *「TickContext 形式上**已暴露** funding_rate / index_price / open_interest / orderbook L1」*，然後在 line 34 retreat 到 *「在 TickContext 結構下是「strategy 自己 buffer」而非 first-class field」*。這是把「symbol-local 字段已暴露」與「cross-section panel 未暴露」混在同一論證框中，**對「結構性偏差」的指控被自己論證稀釋**。

進一步核驗（grep `TickContext` `funding_rate` `index_price` `open_interest` 三字段都在 `tick_pipeline/mod.rs:681,684,689`）：funding_arb 已使用、grid 用 `best_bid/ask`、`indicators_5m: Option<&IndicatorSnapshot>` 已暴露多時框。**所謂「結構性偏差」的真實量級是「跨 symbol 截面 + microstructure deep state 沒暴露」**，不是「整個 alpha surface 都缺」。

**修正定位**：
Root Cause 1 應 reframe 為 **「Cross-section + microstructure surface 缺位 + 5 既存策略 100% symbol-local OHLCV-driven，使 Strategist 即使 wide_skill 也只能在 TA 維度微調」**。把「Strategy Interface 整體結構性偏差」這個過強敘事降一檔 — 它是**潛能受限**（5 策略不會去用 funding_curve / OI panel），不是**結構不可能**（TickContext 已能撐起 funding_arb v2 那種 single-symbol cross-product 策略）。

**對 R-1 影響**：R-1 的 AlphaSurface bundle 仍有效，但**首要 leverage point 不是「重做 TickContext」**而是 **「新增 cross-section 截面快照寫入 + 在 Strategist scope 加 alpha-source 提案能力」**。R-1 估算的 3 sprint 應拆 1 sprint Cross-section snapshot writer + 2 sprint AlphaSurface bundle bigger refactor。這給 PM 一個**漸進路徑**，不是 all-or-nothing 改 trait。

---

### Push Back 2 — Root Cause 2 是 spec 與 IMPL 不一致還是 spec 本身定義模糊?

**自寫定位**：「Strategist scope 是『調參器』非『策略發現器』」（line 50 引 EX-06 V1 line 159「自主孵化策略」字面）。

**自我對抗**：
EX-06 V1 line 242-244 寫 *「策略孵化流程：Analyst 提出新策略概念（基於 L2 模式發現）」* — **「自主孵化」的職責 spec 上是 Analyst 不是 Strategist**！PA report §1.2 line 50 引用「策略匹配（從 5 策略選最優 + 自主孵化策略）」是把 EX-06 line 159 *「策略匹配」* 誤讀成「策略孵化」。Spec 上 Strategist = 「從既有 strategy_set 選最優」，Analyst = 「孵化新策略」。

進一步：今天 commit `c2ab7b1a` 已給 Strategist 加 `wide_parameter_adjustment` skill（30%-50% 維度），證明 PM 對 Strategist 的真實期待**就是參數調整器**，不是 alpha 孵化器。

**修正定位**：
Root Cause 2 應 reframe 為 **「Strategist 已合 spec 工作（參數 + regime weight），但 Analyst 的孵化責任 0% IMPL，使 alpha discovery loop 無 owner」**。**真正的 root cause 是 Analyst L2-L5 dormant**（與原 Root Cause 3 是同一根因），不是 Strategist 越權空缺。Root Cause 2 與 Root Cause 3 應**合併**為「孵化 owner（Analyst）+ propose channel（Strategist→Analyst pattern_insight）+ 實驗 pipeline 三件齊缺」。

**對 R-2 影響**：R-2 不應 reframe Strategist 為「Alpha Source Orchestrator」（這違反 EX-06 spec）。應改為**「Analyst L3 hypothesis dispatcher + Strategist propose 通道」**接線。`_REGIME_STRATEGY_PREFERENCES` hardcoded 4×5 字典**不應移除**（它是 Strategist 工具），改為「動態 Sharpe-by-regime 加上 hardcoded 為 prior」是合理改進，但不是「scope reframe」。

---

### Push Back 3 — Root Cause 3 是否要 reverse 一個剛拍板 ADR?

**自寫定位**：「Analyst L2-L5 進化階梯 100% dormant 是 alpha discovery loop 死的真實位置 + ADR-0020 把 Layer 2 永久標 manual + supervisor-only **by design**」。

**自我對抗**：
ADR-0020（Layer2 manual+supervisor-only）是 **2026-05-09 同日 operator + AMD-2026-05-09-02 §4 拍板的決定**。原報告 §1.3 line 79 寫 *「ADR-0020 把它的解封路徑進一步推遲」* — 這是把 operator 政策決策 framing 為「架構 root cause」，**等同要 reverse 一個 day-old ADR**。如果 PA 推翻 ADR-0020 = 違反 §五 治理 +  造成「PA vs operator 拉鋸」反模式。

但同樣不能簡單接受「Layer 2 dormant by design = Analyst 進化 loop 不需要 IMPL」。Analyst L2-L5 的 IMPL **不依賴 Layer 2 雲端 LLM** — L1 統計、L2 跨交易模式發現、L3 hypothesis 生成都可在 L0+L1 Ollama 跑（13B 模型對「找模式 / 列假設」夠用）；**Layer 2 是「複雜 / 跨 strategy 級認知」的 escalation 路徑**，不是 Analyst 進化引擎的必要條件。

**修正定位**：
Root Cause 3 reframe 為 **「Analyst L2-L5 IMPL 0%，這獨立於 ADR-0020 Layer 2 manual-only 決定。L0+L1 已足夠跑 L2-L4 的 95% workload」**。ADR-0020 影響的是 **L4 跨 strategy 戰略級進化** + **L5 元學習** 的部分 cloud reasoning，**不影響** Analyst 主體的 hypothesis pipeline。

**對 R-3 影響**：R-3 Hypothesis Pipeline 仍是 first-class object，但要明確 **不 require Layer 2 解封作前置**。Hypothesis state machine + Analyst L2-L3 IMPL 在 L0+L1 完成；只有「跨 strategy 戰略提案 / 政策變更建議」階段才 escalate Layer 2 manual。這保 ADR-0020 + 解 Analyst dormant **互不衝突**。

---

### Push Back 4 — Root Cause 4 ML 0.5% 是否能 reframe?

**自寫定位**：原 report 沒有「Root Cause 4 ML 0.5%」，operator 提示在 v2 verification §6 P1 列為剩餘 gap。redesign report 把它放在 Cluster B「Learning loop dormant ~15-20 finding」中。

**自我對抗**：
v2 verification line 17 + line 20 + line 23 揭示：
- 24h ai cost $0；ai_invocations Δ 0
- attribution_chain_ok 24h 0.0188% → 0.5041%
- 「denominator artifact，ok_n only +47%」

「denominator artifact」表示**分子分母都有問題**：
- 分子：ok_n（成功歸因 row）只 +47% 增長
- 分母：總 row 數同步漲

換言之 attribution_chain_ok 從 0.018% → 0.504% 看起來「+25 倍」實際是**統計上沒有意義的改變**（仍 99.5% rows 歸因失敗）。

進一步看 W-AUDIT-4 v2 verification line 39：*「row count 仍 0；cron 仍 not installed」* — V068/V070/V071 reclassification 實質上是 COMMENT-ONLY，**真實 INSERT path 沒搭起來**。今 `da2aba11` 修了 cron scope（F-08 的 5 個 ML 腳本納入 ml_training_maintenance.py）但 `crontab -e` runtime 安裝**仍未執行**。

**這不是 ML pipeline bug，是「writer 0 caller / cron 0 active」**：
1. mlde_demo_applier filter 對 NULL context_id 的 row 直接 drop（writer 上游）
2. 6 表（feature_baselines / drift_events 等）0 INSERT path 接線（writer 中段）
3. 5 ML 訓練腳本 cron 0 install（trainer 0 schedule）

**修正定位**：
Root Cause 4 reframe 為 **「ML/Learning 平面 writer chain + cron install 三段全斷，attribution 0.5% 是斷裂下游症狀，不是 attribution 算法 bug」**。

**對 R-3 影響**：R-3 Hypothesis Pipeline 之前必須**先補 W-AUDIT-4 6 表 INSERT path + cron install**，否則 hypothesis 即使設計完美仍無 evidence 餵。**W-AUDIT-4 不應「併入」R-3，應作 R-3 的 prerequisite wave**。原 redesign report 第 437 行「W-AUDIT-4 應併入 R-3」**錯**，正確順序是 **W-AUDIT-4 → R-3**。

---

### Push Back 5 — Root Cause 5 是什麼?是否真實?

**自寫定位**：原 report 5 個 root cause:
1. Strategy Interface 結構性偏差
2. Strategist 是調參器
3. Analyst L2-L5 dormant
4. 風控側鐵血 vs alpha 側放羊
5. Conductor + 5-Agent 是否 over-engineered

PA 自看：Root Cause 5 是 **「5-Agent 拆分本身正確，但靈魂沒裝」**（line 125-127）。

**自我對抗**：
這個 root cause **不是 root cause，是「結論」**。「5-Agent 是骨架，但靈魂沒裝」實際上 = Root Cause 2（Strategist scope 問題）+ Root Cause 3（Analyst dormant）+ Layer 2 dormant 三者**現象集合**。它不增加新信息。

**真正缺的 Root Cause 5 應該是**：
**「Spec / Runtime / Doc 三套 SoT 持續漂移，operator 必須親自 verify runtime 才能 trust spec」**。證據：
- v2 verification §3 P0-DECISION-AUDIT 5/5 拍板過程 — 5 個都需要 operator 拍板才能 close drift
- v2 §6 outstanding：W-AUDIT-3 runtime restart fail-closed metrics 未驗（spec 寫了但無法核實）
- v2 §6：DSR/PBO promotion gate source/test closed 但 runtime evidence 0
- v2 §6：W-AUDIT-4 6 表 0 INSERT + cron not installed = source claim 與 runtime fact 漂移

**這是 Cluster C「治理 drift」的根因 + 與其他 4 個 root cause 平行的獨立 cause**：架構**沒有 forcing function 自動驗 spec→runtime 一致性**。

**修正定位**：
Root Cause 5 reframe 為 **「Spec-Runtime drift 自動偵測缺位，所有 audit 必須 PA/operator 手動 verify runtime 才知 spec 是否落地」**。配 R-5 Spec-as-Code 工作。原 redesign 把 5-Agent 拆分當 root cause **無新意**，浪費一個 root cause 槽位。

---

### Push Back 6 — Alpha Surface Bundle 升級藍圖是否經 BB / E5 核驗 LOC budget?

**自寫定位**：R-1 Alpha Surface Bundle estimate 3 sprint，沒寫 BB Bybit 可行性核驗 + E5 LOC budget。

**自我對抗**：
**Bybit 可行性**（BB 視角應驗）：
- `funding_curve`（25 symbols funding panel）：Bybit V5 `/v5/market/funding/history` per-symbol fetch；25 symbols × hourly = 600 calls/day，**需 batch 或 WebSocket subscription**。Bybit 沒有「all symbols funding snapshot」endpoint，BB 應 push back「不是 first-class API support」
- `oi_delta_panel`：`/v5/market/open-interest` per-symbol，類似限制
- `orderflow / liquidation_pulse`：Bybit V5 `/v5/market/recent-trade` 有大單 tape，但 **不含 microprice 計算**（需 client 從 `bookticker` 自算）。`liquidation` WS topic 可訂閱
- **結論**：BB 視角會 push back「3 個 first-class field 中 2 個需 client-side aggregation，Bybit 沒原生 API；只有 funding curve 可較直接落地」

**E5 LOC budget**（性能視角）：
- AlphaSurface struct 加 8 新 Optional reference 字段 → 每 tick 8× pointer deref，hot path 微影響
- IndicatorEngine 已 1466 LOC（v2 已修）；新增 cross-section snapshot writer 可能再加 500-800 LOC
- runner.rs 剛從 2467→1167 拆完，**再加 cross-section infra 容易 reflate**

**修正定位**：
R-1 estimate 從 3 sprint **校正為 4-5 sprint**：
- Sprint 1：BB push back 確認 + Bybit API survey + 截面快照 writer 設計
- Sprint 2：funding_curve writer + 1 demo 策略消費（先驗證 alpha 真存在）
- Sprint 3：OI delta panel + 1 demo 策略
- Sprint 4：orderflow / liquidation_pulse（需自建 microprice）
- Sprint 5：Strategy trait `declared_alpha_sources()` 接線 + 5 既存策略 backward compat migration

如果 Sprint 2 funding_curve 策略不顯示 alpha，**整個 R-1 應 abort**（避免堆 cross-section 結構但無策略消費）。新增 **Stage Gate**：每個 cross-section field add 後必須跑 1 個 demo 策略 N=200 觀察 7d，才 commit 下一 field。

---

### Push Back 6.1 — redesign 結語是否過於斷言?

原 report 結語 line 460-464：
*「architectural verdict：當前 5 策略不是『需要更好參數』，是站在已無 alpha 的 territory」*

**自我對抗**：
這個論斷沒 controlled 對照。5 策略 7d demo gross -26.44 USDT 中 funding_arb -15.43 + grid -11.15 占 ~100%；ma +0.2 / bb -0.06 **接近 zero**。如果只看 ma + bb_breakout（純 TA），它們的 7d gross 是 ~zero（噪聲區間）— **「TA territory 無 alpha」是用 funding_arb + grid 的虧損證明的，邏輯瑕疵**。

更精確說法：**「funding_arb 在當前 demo 下無 alpha + grid 在當前 demo 下實際是 fee 出血，純 TA (ma/bb) 在低 sample 下 indistinguishable from zero」**。

**修正結語**：
不是「5 策略全在無 alpha territory」，是 **「2 個有負 alpha 證據 (funding_arb 已 retire / grid 限 ORDIUSDT)、3 個樣本不夠下結論」**。R-1 升 alpha source 的 motivation 應是 **「拓寬 candidate pool」而非「現有 5 個全無救」**。

---

### §1 結論

| Root Cause | 原 PA 定位 | 自我對抗後修正 |
|---|---|---|
| 1 Strategy Interface 偏差 | **最核心** | **降一檔**：Cross-section + microstructure 缺位（不是整個 surface 缺）|
| 2 Strategist 調參器 | 結構問題 | **錯歸因**：Strategist 合 spec；責任在 Analyst |
| 3 Analyst dormant | + ADR-0020 阻 | 修正：Analyst dormant 獨立於 ADR-0020；L0+L1 可跑 L2-L3 |
| 4 ML 0.5% (operator 加) | denominator artifact | reframe：writer chain + cron 三段斷；W-AUDIT-4 是 R-3 prerequisite，不是合併 |
| 5 5-Agent 拆分 | 「靈魂沒裝」 | **無新意**；replace 為 「Spec-Runtime drift 自動偵測缺位」|
| Alpha Surface 升級 | 3 sprint | **校正 4-5 sprint** + BB/E5 核驗 + Stage Gate |
| 結語「territory 無 alpha」 | 強斷言 | **修正**：證據只支持 funding+grid 負 alpha，TA 樣本不足下結論 |

**自我對抗總結**：原 redesign 50% 結構性內容仍站得住（Cross-section + Analyst hypothesis + Spec-as-Code），50% 過度斷言或誤歸因（Strategy Interface 偏差程度、Strategist scope 越權、5-Agent root cause）。Fix plan v2 應**保留 R-1 + R-3 + R-5 主體 + 修正 R-2 為 Analyst hypothesis 接線 + 不動 R-4 提到 supervised-live promotion 仍須**，但**降低過熱主張**（不是「88 finding 都是症狀」，是「~50 個 finding 是症狀，~38 個確實獨立必修」）。

---

## §2 12 v2 verification 殘留 outstanding（按 wave 整合）

不重複 v3 對 5 commits 核實的內容。專注 v2 揭示但 5 commits 未動的 outstanding。

### W-AUDIT-3 fake-live 殘留（HIGH）
- **engine restart fail-closed metrics 未驗**（v2 §2 W-AUDIT-3 verdict）：F-01 lambda 真移除是 source-level；engine 是否在 provider unavailable 真 fail-closed metrics 0 觀察點
- **F-15 lease writer e2e DB row 仍 opt-in**（v2 §2 partial）：lease audit channel writer wire 完成（v2 W-AUDIT-2 source）+ 22,790 row（已 disputed F-06），但 E2E test 要 opt-in flag

### W-AUDIT-4 ML 基座（CRITICAL，5 commits 未根治）
- **6 表 0 INSERT 仍 0**（v2 §6 P1-5）：feature_baselines / drift_events / scorer_training_features / mlde_edge_training_rows / 等 6 表 row count = 0
- **F-08 5 ML cron 仍 not installed**（v2 §2 W-AUDIT-4 + §6 P1-10）：今 `da2aba11` 修了 scope 把 thompson/optuna/cpcv/dl3/weekly_report 納入 `ml_training_maintenance.py`，但 `crontab -e` runtime 0 install
- **attribution_chain_ok 24h 0.5041%**（v2 §1）：denominator artifact（ok_n only +47%）；本質是 writer chain + cron 三段斷
- **V077 columnstore fallback** + Dream Engine Foundation only（v2 §5 MIT 3 條）

### W-AUDIT-6 策略 + 量化（5 commits 未動子項）
- **bb_reversion verdict 仍未動**（v2 §6 P1-8）：AMD-2026-05-09-02 §3 寫「pair with MA」但 IMPL 0；TODO §13 標 SOURCE/TEST CLOSED 是其他 4 策略部分
- **DSR/PBO evidence 自動化 push 鏈** source/test closed by `48227607` (V079)，但 **runtime V079 apply + rebuild + restart 仍未執行**
- **trial_sharpes 持久化** source/test closed by V079，**runtime evidence 仍 0**
- **portfolio_var min_observations=200**（v2 §5 QC NEW-ISSUE-5 MEDIUM）：sampling unit review 缺；可能卡 promotion gate `defer_data` verdict

### W-AUDIT-7 GUI/AI（A3 18 ❌ 中 5 commits 0 進展）
- **A3 v2 18 ❌ 中 0 進展**（v2 §1 A3 row）：v1 20 → v2 18，僅 2 條 close（openConfirmModal a11y 補 + GUI work-rate 下降是 self-rate）；剩 18 ❌ 5 commits 未碰
- **AI-E Cloud L2 0 流量**（v2 §1 AI-E）：24h ai cost $0；ai_invocations Δ 0；**ContextDistiller source added 但 production caller 0**；F-07 operator GUI ANTHROPIC_API_KEY + Layer2 manual trigger 仍未做
- **F-cea-env CostEdgeAdvisor env**：仍未 set + restart

### W-AUDIT-1/2 治理 / docs（v2 已 closed 5/5 CRITICAL，殘留低嚴重度）
- **R4 v2-N1 殭屍引用**（v2 §5 #4）：`archive/2026-05-09--w_audit_verified_closed_archive.md` 在 docs/README + TODO + summary 三處引用，檔案不存在 — operator 應 5min 補檔或刪引用
- **TW worklogs 12 天斷層**仍存（v2 §5 #6）
- **docs/README.md 仍缺 `Last Updated` header**（v2 §5 #5）

### W-AUDIT-5 性能 / 平台（5 commits 未動）
- **W-AUDIT-5b 部分 deferred**：deepcopy 10 處改 frozen / orjson / ai_budget RwLock / event_consumer 拆 — 5 commits 0 進展（按計劃推遲）

### Outstanding 總計矩陣
| Wave | v2 outstanding | 5 commits 是否覆蓋 | 性質 |
|---|---|---|---|
| W-AUDIT-3 | engine restart fail-closed 驗 + F-15 e2e | ❌ 0 進展 | runtime smoke + test |
| W-AUDIT-4 | 6 表 0 INSERT + F-08 cron install + V077 + Dream | ❌ 0 進展 | infra IMPL + ops |
| W-AUDIT-6 | bb_reversion + V079 runtime + portfolio_var min_obs | ⚠️ source/test 部分 closed by 48227607（V079）| runtime apply 待 |
| W-AUDIT-7 | A3 18 ❌ + AI-E L2 0 流量 + F-07 + cea-env | ❌ 0 進展 | UX + operator action |
| W-AUDIT-1 | R4 殭屍引用 + worklogs + Last Updated header | ❌ 0 進展 | docs hygiene |
| W-AUDIT-5b | deepcopy / orjson / RwLock / event_consumer 拆 | ❌ 0 進展（按 plan deferred）| performance |

**總 outstanding 工時**（粗估 5 commits 後）：~80h（W-AUDIT-3: 8h + W-AUDIT-4: 30h + W-AUDIT-6 runtime: 4h + W-AUDIT-7: 25h + W-AUDIT-1 cleanup: 2h + W-AUDIT-5b: 17h），**比 v1 plan 140h 收斂 43%**。

---

## §3 5 commits cover 確認（v3 補位）

| Commit | 對應 finding | source/test/runtime 狀態 | PA 復驗 |
|---|---|---|---|
| `ad14db07` bb breakout donchian guard | P0-V2-NEW-1 (QC v2-NEW-4 HIGH) | source/test closed; **無 rebuild/reload** | ✅ verified — `donchian_prior()` 接線 + bb_breakout 5m hard-gate test 加 81 行 regression；engine 仍跑舊 binary |
| `c2ab7b1a` strategist wide adjustment skill | P0-V2-NEW-2 (FA v2-NEW-1) | source/test closed; **無 rebuild/restart** | ✅ verified — Rust evaluate.rs +81 行 send `wide_skill_range` payload；Python ai_service_dispatch.py +86 行 render normal_range / wide_skill_range；3 risk_config TOML 已對齊 0.50 |
| `48227607` learning push promotion evidence | P0-V2-NEW-3 (QC §6.1 (a)(c) HIGH) | source/test closed; **V079 未 apply / 無 rebuild / 無 cron** | ✅ verified — V079 migration + promotion_evidence.py 558 行 + edge_estimator_scheduler.py +126 行 demo-only push；**runtime V079 apply + rebuild 未執行** |
| `c081029d` blocked symbol freeze | P2-AUDIT-VERIFY-5 | source/test closed; freeze JSON + audit helper added | ✅ verified — `docs/governance_dev/strategy_blocked_symbols_freeze.json` 52 行 + `helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py` 247 行；**靜態 guard test 已 added，runtime evidence 5 commits 後 0 row** |
| `da2aba11` audit f08 ml cron scope | F-08 / W-AUDIT-4 partial 修正 | source/test closed; **crontab 仍未 install** | ✅ verified — `ml_training_maintenance.py` +511 行包 thompson/optuna/cpcv/dl3/weekly_report；TODO 標 W-AUDIT-4 PARTIAL 而非 ACTIVE；**runtime cron 0 install** |

**5 commits 共 cover**：
- ✅ P0-V2-NEW-1 / -2 / -3 source/test
- ✅ selection bias 治理（blocked symbols freeze）
- ✅ cron scope 修正（F-08 5 ML 腳本納入 maintenance script）

**5 commits 未 cover**：
- ❌ runtime cron install（needs operator `crontab -e`）
- ❌ V079 DB apply + rebuild（needs operator + ops）
- ❌ engine restart fail-closed metrics 驗
- ❌ W-AUDIT-4 6 表 INSERT path 接線（需新 IMPL，不只 cron）
- ❌ A3 18 ❌（GUI/UX backlog）
- ❌ AI-E F-07 + cea-env（operator action）
- ❌ bb_reversion verdict IMPL（pair with MA）

**結論**：5 commits 把 **3 個 source/test gap 填了**（DSR/PBO + Donchian + Strategist wide skill），加 1 個 governance 收口（blocked symbols）+ 1 個 audit 校正（cron scope）。**沒有 runtime apply 路徑**，所以 W-AUDIT-4 結構性 gap 0 移動。

---

## §4 是否需要重新做工作安排?

### 決策樹評估

| 條件 | 是否成立 | 證據 |
|---|---|---|
| (A) 5 commits + redesign 提案合理 + outstanding 是已知 P0/P1 | **部分成立** | 5 commits 合理但 redesign 自我對抗後 50% 內容需修正；outstanding 80h 確實已知 |
| (B) Redesign 顯示根本性架構問題 + 原 7 wave 治標不治本 | **部分成立** | Cross-section + Hypothesis + Spec-as-Code 是真 gap；但 W-AUDIT-2/-3/-4/-5 仍是必須做的 baseline |
| (C) 中間方案：dual-track（W-AUDIT 收尾 + ARCH 新 wave 同時推進）| **最符合現況** | W-AUDIT-3/-4/-7 + W-AUDIT-1 cleanup + W-AUDIT-5b ~80h 6-8 weeks 線性可完成；ARCH wave 4-5 sprint 並行可開 |

### PA 決策：**DUAL-TRACK**

**不重 plan 全 reset**（B 過度）；**不純增量** continue W-AUDIT-1..7（A 不足）；**並行 dual-track**：

- **Track W**（W-AUDIT 收尾，~80h 6-8 weeks）：W-AUDIT-3 fake-live runtime smoke + W-AUDIT-4 functional fix + W-AUDIT-6 runtime apply + W-AUDIT-7 GUI/AI + W-AUDIT-1 cleanup + W-AUDIT-5b deferred performance
- **Track A**（ARCH 新 wave，4-5 sprint 並行）：W-ARCH-1 Cross-section snapshot writer + 1 demo 策略消費；W-ARCH-2 Hypothesis Pipeline 一等對象（Analyst L2-L3 IMPL）；W-ARCH-3 Spec-as-Code（替原 R-5）；推遲 W-ARCH-4/5 至 W-ARCH-1 demo 策略產出 alpha 證據

**Track 邊界明確**：
- Track W 不阻 supervised live；Track W 完成 = supervised live 正式可放權的「合規 / 安全 / 可觀測」三件配齊
- Track A 不阻 Track W；Track A 是「未來 alpha 拓寬」工作，**不前置**到 supervised live 規劃帶（6/15 / 6/30 / 7/15）內
- Stage Gate：Track A W-ARCH-1 first cross-section 策略需在 demo 跑 7d 顯 alpha 才 commit W-ARCH-2/-3

### 為何 dual-track 而非 reset?

1. **Reset 風險高**：重 plan 7 wave 為 5 個 ARCH wave 等於拋棄 W-AUDIT-2/-3/-5 已 source closed 進度（v2 verification 122/259 = 47%）。**沉沒成本失誤**反而造成 6/15 supervised live 規劃帶崩盤
2. **Reset 的 marginal value**：原 7 wave 中 4 個（W-AUDIT-2/-3/-5/-6）是 supervised live baseline；reset 只能影響 W-AUDIT-4/-7（已是部分 dormant），收益有限
3. **Track A 真實 leverage**：5 commits 顯示 operator 已自動處理 P0-V2-NEW 3 條（無需 PA 額外 plan），**operator 工作節奏在「漸進補完 W-AUDIT 7 wave」而非「等 PA 完整 architectural redesign」**。Dual-track 配合此節奏
4. **Stage Gate 控制 Track A 風險**：W-ARCH-1 first cross-section 策略 7d demo 觀察是「便宜驗證」（不破現有 5 策略 + 不卡 supervised live），失敗即 abort

---

## §5 Fix plan v2 — 增量 wave structure

### Track W — 既存 W-AUDIT 收尾（v2 verification + 5 commits 後 outstanding）

| Wave | Owner | 工時 | Agents | 依賴 | 並行/串行 | Session |
|---|---|---:|---|---|---|---:|
| W-AUDIT-3b runtime | E1 + E2 + E4 + ops | ~8h | E1×2 + E2 + E4 + ops | engine restart 視窗 | 串行（restart 等視窗）| 1 |
| W-AUDIT-4b functional | E1 + MIT + E2 + E4 + ops | ~30h | E1×4 + MIT + E2 + E4 + ops | crontab 安裝授權 | 並行 sub | 2-3 |
| W-AUDIT-6c runtime | E1 + ops | ~4h | E1 + ops | V079 apply + rebuild | 串行 | 1 |
| W-AUDIT-6d bb_reversion + portfolio_var review | QC + E1 + E2 | ~6h | QC + E1 + E2 | W-AUDIT-6 PM 拍板 | 並行 | 1 |
| W-AUDIT-7c GUI/AI | E1 + A3 + AI-E + E2 | ~25h | E1×3 + A3 + AI-E + E2 | F-07 operator action | 並行 | 2 |
| W-AUDIT-1d cleanup | TW + R4 + PM | ~2h | TW + R4 + PM | 無 | 並行 | 1 |
| W-AUDIT-5b deferred | E1 + E5 + E2 + E4 | ~17h | E1×4 + E5 + E2 + E4 | W-AUDIT-3b 完成 | 並行 sub | 2 |
| **Track W 總計** | | **~92h** | 平行可達 ~12 sub-agent | | | **9-11 session** |

### Track A — operator 已 active 的 ARCH wave（W-AUDIT-8a + W-AUDIT-9 + 後續 8b/c/d/e/f/g）

**重要修正**：原 fix plan v2 §0 已揭示 operator 在 PA 撰報告同時已採納 R-1 並啟動 W-AUDIT-8a SPEC PHASE + 新建 W-AUDIT-9。Track A 不是 PA 新提議，是反映 operator 既定路徑 + PA 補位。

| Wave | Owner | 工時 | Agents | 依賴 | Stage Gate | Session |
|---|---|---:|---|---|---|---:|
| **W-AUDIT-8a** Alpha Surface Foundation Spec→IMPL（已 SPEC PHASE 2026-05-09）| PA → E1 + E2 + E4 + MIT/QC/CC/BB | ~40 person-day（Phase A-D × 4 sprint，AMD-03 估算 base on operator land 的 spec doc）| PA + E1×6 + E2 + E4 + MIT + QC + CC + BB | W-AUDIT-9 必先 IMPL（5-stage 機制）| Phase B-D 各 phase 完成有 e2e replay byte-identical baseline 驗證 | 8-12 |
| **W-AUDIT-9** Graduated Canary Foundation（AMD-2026-05-09-03 新建）| PA → E1×7 + E2 + E4 + ops | ~1.5-2 sprint（PA estimate base on §4 IMPL items size）| E1-A 至 E1-G + E2 + E4 + ops | 可獨立啟動，與 W-AUDIT-3/-4/-5/-6/-7 並行 | T1+T2+T3+T6 4-way parallel；T4+T5 待 T2/T1；T7 final | 4-6 |
| **W-AUDIT-8b** alpha source candidate A funding skew spread IMPL（候選 A）| QC + E1 + E4 | ~20h | QC + E1×2 + E4 | W-AUDIT-8a Phase B (Tier 2 panel) 完 + W-AUDIT-9 Stage 1 ready | **Stage 1 = 1 strategy×1 symbol paper 7d**；Stage 2 = single-symbol-demo 14d gross > 0 才 commit | 2 |
| **W-AUDIT-8c** alpha source candidate B liquidation cluster IMPL | QC + E1 + E4 | ~20h | QC + E1×2 + E4 | W-AUDIT-8a Phase C (Tier 3) 完 + W-AUDIT-9 ready | 同 -8b graduated canary 5-stage | 2 |
| **W-AUDIT-8d** alpha source candidate C BTC→Alt lead-lag IMPL | QC + E1 + E4 | ~20h | QC + E1×2 + E4 | W-AUDIT-8a Phase B+D (cross-symbol + Tier 4 regime) 完 + W-AUDIT-9 ready | graduated canary | 2 |
| **W-AUDIT-8e** Strategist 重定義（R-2，§1 Push Back 2 修正後 = Analyst L2-L3 propose 通道）| E1 + AI-E + PA | ~15h | E1×2 + AI-E + PA | W-AUDIT-8a Phase A 完 | 不需 Stage Gate（infra） | 1-2 |
| **W-AUDIT-8f** Hypothesis Pipeline first-class object（R-3）| E1 + MIT + PA + E2 + E4 | ~40h | E1×4 + MIT + PA + E2 + E4 | **W-AUDIT-4b 必先完成**（writer chain + cron） | 不需 Stage Gate（infra） | 3-4 |
| **W-AUDIT-8g** Per-alpha-source Live Promotion Gate（R-4）| QC + E1 + PA + GovernanceHub team | ~30h | QC + E1×3 + PA + Guardian | W-AUDIT-8a + W-AUDIT-8e + W-AUDIT-8f 完 | structural（可累加 LG-X baseline） | 2-3 |
| **W-ARCH-3** Spec-as-Code（CLAUDE.md §三 cron + Module Lifecycle SM）| E1 + PA + TW + E2 | ~15h | E1×2 + PA + TW + E2 | 無 | 不需 Stage Gate（治理） | 1-2 |
| **Track A 總計**（含全 W-AUDIT-8x + W-AUDIT-9 + ARCH-3） | | **~270-330h**（含 W-AUDIT-8a 40 person-day）| 平行可達 ~15 sub-agent | | graduated canary 多次 abort 可能 | **23-32 session** |

**注意**：
- Track A 工時遠超原 redesign R-1..R-5 ~140h 估算（PA 撰報告時尚未看到 operator land 的 W-AUDIT-8a spec doc 的 Phase A-D 細節）
- Track A 受 graduated canary（W-AUDIT-9）保護，**單筆 fail 不全廢**：每個 alpha source 走自己的 5-stage canary，stage 失敗 auto-rollback 不影響其他 candidates
- Track A 真實風險：W-AUDIT-8a 4 sprint × ~40 person-day 是大型 IMPL 工作；如 spec phase 延期 2 weeks，Sprint N+0 → N+2，所有後續 8b/c/d slip
- Stage Gate 升級：原 fix plan v2 用「7d demo gross > 0」做 Stage Gate；AMD-03 §3 graduated canary 提供更精細的 5-stage 機制（Stage 1 paper / Stage 2 single-symbol-demo / Stage 3 multi-symbol-demo / Stage 4 live-pending），Track A 的所有 alpha source 走 W-AUDIT-9 5-stage 而非 PA 自定 7d gate

### 整合視圖：6-12 weeks roadmap（修正後反映 W-AUDIT-8a/9 已 active）

| Week | Track W focus | Track A focus | 並行 sub-agent 上限 |
|---|---|---|---|
| Week 1 | W-AUDIT-3b runtime + W-AUDIT-1d cleanup | W-AUDIT-9 T1+T2 並行（Rust schema + V### migration） | ~10 |
| Week 2 | W-AUDIT-4b INSERT path × 6 表 | W-AUDIT-9 T3+T6 並行 + W-AUDIT-8a Phase A SPEC review | ~12 |
| Week 3 | W-AUDIT-4b 收尾 + W-AUDIT-6c runtime apply | W-AUDIT-9 T4+T5 + W-AUDIT-8a Phase A IMPL start | ~12 |
| Week 4 | W-AUDIT-7c GUI/AI 大半 | **W-AUDIT-9 T7 regression + IMPL land** + W-AUDIT-8a Phase A 收尾 | ~12 |
| Week 5 | W-AUDIT-7c 收尾 + W-AUDIT-5b deferred | W-AUDIT-9 Stage 1 開觀察（取代 binary fail-closed）+ W-AUDIT-8a Phase B Tier 2 cross-section panel | ~12 |
| Week 6 | W-AUDIT-5b 收尾 + W-AUDIT-6d bb_reversion | W-AUDIT-8a Phase B 收尾 + W-AUDIT-8b candidate A funding skew start（走 Stage 1 paper）| ~12 |
| Week 7-8 | Track W 全 closed → supervised live 規劃帶 6/15-7/15 重新評估 | W-AUDIT-8a Phase C/D + W-AUDIT-8b Stage 1 7d 觀察 | ~12 |
| Week 9-12 | （Track W done） | W-AUDIT-8b Stage 2/3 demo + W-AUDIT-8c/d candidate B/C + W-AUDIT-8e Strategist + W-AUDIT-8f Hypothesis Pipeline | ~15 |

**Track W 完成判定**：~92h / 9-11 session 內完成 = 6/15 樂觀帶可達；遇 W-AUDIT-4b INSERT path 卡（10+h 估算 risk）= 6/30 中位帶
**Track A 完成判定**（多階段）：
- **W-AUDIT-9 IMPL land**（1.5-2 sprint = 3-4 weeks）= P0-EDGE-1 雞蛋死循環解開 → realized edge 證據 collection 路徑首次真實 active
- **W-AUDIT-8a Phase A-D 全 land**（4 sprint = 8 weeks）= alpha source candidates 8b/c/d 可走 graduated canary
- **W-AUDIT-8b/c/d 至少 1 candidate Stage 2 PASS**（額外 2-4 weeks per candidate）= 第一個 alpha-bearing 策略真實 demo evidence；可能仍需 8-12 weeks 才有第一個正向 alpha source

### Track 衝突風險（修正反映 W-AUDIT-9 加入後）

| 風險 | 機率 | mitigation |
|---|---|---|
| Track A W-AUDIT-8f Hypothesis Pipeline 與 Track W W-AUDIT-4b 同碰 ML schema | 高 | W-AUDIT-8f 必後於 W-AUDIT-4b PASS 才開（已串行 per AMD-03 §5.4）|
| Track A W-AUDIT-9 T3 `executor_config_cache.py` 與 Track W W-AUDIT-3b ExecutorAgent runtime 衝突 | **中-高** | T3 改 `_read_shadow_mode` stage-aware；Track W W-AUDIT-3b 是 runtime smoke 不改 source；協調 commit 順序：W-AUDIT-9 T3 land 前 W-AUDIT-3b 完 |
| W-AUDIT-9 IMPL 期間 Rust schema 升級觸發 IPC schema break | 中 | AMD-03 §5.5 已備 dual-field fallback（保留 binary + 新增 canary_stage 並列）|
| W-AUDIT-8a Phase A SPEC delay 2+ weeks → 後續 8b/c/d slip | **高** | Phase A 是 spec doc 已 land，IMPL Phase A 是接口升級不是業務 IMPL；E1×6 並行可控 |
| Stage Gate W-AUDIT-8b candidate fail 但已花 20h | 低 | graduated canary 5-stage 自帶 auto-rollback + 不影響其他 candidate；20h 投資中 ~50% 是可重用 infra（Tier 2/3 collector）|
| operator 工時 fragmentation（Track W ops action + Track A graduated canary stage promotion lease 動作）| **中** | W-AUDIT-9 T6 `LeaseScope::CanaryStagePromotion` 是 manual operator GUI 動作；每 stage promotion ≤ 5min；TTL 60s |

---

## §6 PA verdict + PM push back 5 點

### 6.1 整體 verdict

**Conditional CONTINUE on dual-track**。
- 5 commits 真實處理 v2 P0-V2-NEW 3 條 + 1 governance + 1 audit 校正，**source/test level credible**；runtime apply 仍 outstanding
- 自我對抗後 redesign 有 50% 過度斷言但**主軸（Cross-section + Hypothesis Pipeline + Spec-as-Code）正確**；不 reset 既有 7 wave，並行開 ARCH 3 wave
- W-AUDIT-3b/4b/6c/7c 4 個 runtime/functional 缺口是 supervised live 真正 blocker，不是 architectural 升級
- ARCH track 是 **alpha territory 拓寬投資**，不前置到 supervised live 規劃帶

**最早 supervised live 重新評估**：
- 6/15 樂觀：Track W ~92h / 9-11 session 全 close + W-AUDIT-4b INSERT path 順利
- 6/30 中位：Track W INSERT path 卡 1-2 sprint
- 7/15 悲觀：W-AUDIT-4b 揭新 schema 設計問題；或 Track A W-ARCH-1b Stage Gate fail 引 PM 重議優先序
- **8/15 極悲觀**：Track W 收尾 + Track A 都被推遲

### 6.2 對 PM push back 5 點（修正後反映 W-AUDIT-8a/9 既已 active）

| # | 決策點 | PA 立場 | 期望 PM sign-off |
|---|---|---|---|
| **1** | **W-AUDIT-9 與 Track W W-AUDIT-3b ExecutorAgent 改動衝突協調** AMD-03 §5.3 W-AUDIT-9-T3 改 `executor_config_cache.py` + `_read_shadow_mode` stage-aware；Track W W-AUDIT-3b 也碰 ExecutorAgent runtime smoke；commit 序衝突風險中-高 | **W-AUDIT-9 T3 land 前 W-AUDIT-3b 必先完成 runtime smoke**；T3 不可 land 前 ExecutorAgent 已被 P0-V2-NEW-1 lambda 移除動過 | 拍板 commit 順序：W-AUDIT-3b 先 → W-AUDIT-9 T3 後；T3 PR 必 rebase 過 W-AUDIT-3b |
| **2** | **Redesign Root Cause 2/5 修正影響 W-AUDIT-8e 範圍** R-2 = W-AUDIT-8e Strategist 重定義；§1 Push Back 2 修正後 = Strategist 不越權，Strategist→Analyst propose 通道 + Analyst L2-L3 IMPL；不該把 Strategist reframe 為 「Alpha Source Orchestrator」 | **接受修正**：合 EX-06 spec；不違 P0-V2-NEW-2 wide_parameter_adjustment skill | 拍板 W-AUDIT-8e scope = 「Strategist→Analyst propose 通道 + Analyst L2-L3 hypothesis IMPL」；Strategist scope 不動 |
| **3** | **W-AUDIT-4b 6 表 INSERT path × cron install 是 W-AUDIT-8f Hypothesis Pipeline prerequisite** AMD-03 §5.4 已確認 W-AUDIT-4 ML 基座併入 R-3 Hypothesis Pipeline 的 wave 仍照原計劃；不修 attribution writer chain 永遠是 ML 信號 0 | **必先 W-AUDIT-4b 後 W-AUDIT-8f**；不可在 ML 平面無 evidence 餵的環境下開 hypothesis pipeline | 接受串行；W-AUDIT-8f 必鎖在 W-AUDIT-4b PASS 後 |
| **4** | **Redesign 結語修正 + W-AUDIT-6 ma/bb_breakout 5m 是否前置到 W-AUDIT-8b** §1 Push Back 6.1 修正：5 策略不是「全無 alpha territory」，是「2 個有負 alpha 證據 + 3 個樣本不足」；W-AUDIT-6 ma_crossover REVISE / bb_breakout 5m REDESIGN 是否走 W-AUDIT-9 graduated canary Stage 1 入場 | **W-AUDIT-6 IMPL 後新策略**（如 bb_breakout 5m redesign）**必走 Stage 1 入場**（per AMD-03 §5.4）；不需特別前置或推遲 | 接受 AMD-03 §5.4：W-AUDIT-6 redesign 策略走 Stage 1 paper / Stage 2 single-symbol-demo 14d 入 |
| **5** | **Layer 2 ADR-0020 與 W-AUDIT-8e 中 Analyst L2-L5 IMPL 解耦** Analyst L2-L3 IMPL 不需 ADR-0020 reverse；L0+L1 Ollama 13B 模型可跑「找模式 / 列假設」95% workload；只 L4 跨 strategy 戰略提案 escalate Layer 2 manual | **保 ADR-0020 + 解 Analyst dormant 並行不衝突** | 拍板：W-AUDIT-8e Hypothesis pipeline 用 L0+L1，Layer 2 escalation 仍 manual+supervisor-only by ADR-0020；不重新 reverse |

### 6.3 期望 PM 簽收的 5 條 hard truth（修正後反映 W-AUDIT-8a/9 既已 active）

1. **5 commits 是 source/test level 進展不是 runtime success**：W-AUDIT-4 6 表仍 0 INSERT；F-08 cron 仍 not installed；V079 仍未 DB apply；engine 仍跑 5/8 binary。**不 runtime apply 等於沒做**
2. **Redesign self-adversarial 結果 mixed**：50% 內容仍站得住（Cross-section + Hypothesis Pipeline + Spec-as-Code），但 §0 揭示 operator 已採納 R-1 升級 W-AUDIT-8a SPEC PHASE + AMD-03 4-agent consensus + 22 fail-closed defaults dead loop math 證明「Strategy Interface 偏差」確是 architectural 級 root cause；§1 Push Back 1 (Strategy Interface 降一檔) 部分被 4-agent consensus 推翻，但其他 5 個 push back 仍有效
3. **W-AUDIT-9 graduated canary 是 P0-EDGE-1 雞蛋死循環的解套**：22 fail-closed defaults 累加 P(全 PASS) ≈ 0 是 demo 環境 stationary fixed point；7d demo gross -26.44 USDT 不是策略 negative alpha 是 sampling artifact；W-AUDIT-9 IMPL land + Stage 1 開觀察 ≥ 7d 是 P0-EDGE-1 evidence collection 的**新路徑**
4. **Track A 完整 IMPL 是 8-12+ weeks 投資不是 6/15 supervised live 前置**：W-AUDIT-9 1.5-2 sprint + W-AUDIT-8a 4 sprint + W-AUDIT-8b/c/d 各自 graduated canary stage 觀察 = 整 Track A 8-12+ weeks；不阻塞 Track W supervised live 規劃帶；但 W-AUDIT-9 IMPL land 後 P0-EDGE-1 evidence collection 才真實 active
5. **Track W 收尾還剩 ~92h**：W-AUDIT-4b 是最大不確定（INSERT path 涉新 schema 設計可能再翻 +20h）；6/15 樂觀帶機率 ~40%（v2 verification 結論 6/30 樂觀帶 ~40%）；W-AUDIT-9 加入後 supervised live 評估改變：第一個真實 demo evidence path 取決於 W-AUDIT-9 land 後 Stage 1 7d 觀察結果

---

## §7 PA AUDIT v2 PLAN DONE

- Self-adversarial 對自寫 redesign 6 點 push back，**50% 內容仍站得住**（Cross-section + Hypothesis Pipeline + Spec-as-Code 主軸）；§0 揭示 operator 已採納 R-1 啟動 W-AUDIT-8a SPEC PHASE + 新建 W-AUDIT-9 graduated canary + AMD-03 4-agent consensus 推翻 Push Back 1 「Strategy Interface 偏差降一檔」立場
- 12 v2 verification 殘留 outstanding 整合（按 wave）：~92h Track W + Track A 已由 operator land 為 W-AUDIT-8a/9 + 後續 8b-8g
- 5 commits cover：3 個 source/test gap + 1 governance + 1 audit 校正；runtime apply 全 outstanding
- 是否重 plan：**DUAL-TRACK**（Track W 收尾 ~92h 6-8 weeks + Track A operator 已啟動 W-AUDIT-8a SPEC PHASE + W-AUDIT-9 IMPL ~270-330h with graduated canary 5-stage protection）
- 新 wave structure：
  - Track W: W-AUDIT-3b/4b/6c/6d/7c/1d/5b（7 個增量 wave，~92h）
  - Track A（operator 已啟動）: W-AUDIT-8a/8b/8c/8d/8e/8f/8g + W-AUDIT-9 + W-ARCH-3（9 個 ARCH wave，~270-330h，含 graduated canary stage gate）
- PM push back 5 點：W-AUDIT-9 與 W-AUDIT-3b commit 衝突協調 / W-AUDIT-8e R-2 修正（Strategist 不越權）/ W-AUDIT-4b 串行先於 W-AUDIT-8f / W-AUDIT-6 redesign 策略走 Stage 1 入場 / Layer 2 解耦
- 預估總工時：Track W ~92h + Track A ~270-330h（含 W-AUDIT-8a 40 person-day spec phase + IMPL）= ~360-420h 6-12 weeks roadmap

**最早 supervised live 規劃帶**：6/15 樂觀（~40%） / 6/30 中位（~40%） / 7/15 悲觀（~20%）；W-AUDIT-9 IMPL land 後 P0-EDGE-1 evidence collection 才有真實 active 路徑（取代「等 binary flip」死路徑），W-AUDIT-9 1.5-2 sprint = ~3-4 weeks，與 supervised live 規劃帶 overlap，**為樂觀帶提供新可信度**；但仍需 W-AUDIT-9 Stage 1 至少 7d 觀察才有 evidence。

---

**報告路徑**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md`

# FA Audit Fix Verification v3 — 2026-05-09 第三輪對抗性核實 + PA Redesign Cross-Check

審計員：FA · 對應 v2 baseline `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--audit_fix_verification_v2.md`
基準範圍：`faf2d131..da2aba11`（5 commits 第三輪）
對偶輸入：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`

**Tally：✅ 4 / ⚠️ 5 / ❌ 6 / 🆕 1 · 業務鏈 ~63% · PA redesign verdict: AGREE**

## §0 5 commits 速覽

| commit | message | scope | runtime |
|---|---|---|---|
| `ad14db07` | strategy: guard bb breakout donchian snapshots | source/test | NIL |
| `c2ab7b1a` | strategist: teach wide adjustment skill | source/test | NIL |
| `48227607` | learning: push promotion evidence from edge cycle | source/test | NIL（"No cron install, V079 DB apply, rebuild, restart"）|
| `c081029d` | governance: freeze blocked symbol lists | source/test | NIL |
| `da2aba11` | audit: correct f08 ml cron scope | source/test | NIL（"crontab installation pending"）|

**結構性觀察**：5/5 commits **source/test only**，**0 runtime restart / 0 deploy / 0 DB apply / 0 cron install / 0 live auth mutation**。延續 v2 後置「打 source 不打 deploy」模式。

## §1 任務 A：5 commits 對 v2 outstanding 6 項覆蓋

### A.1 v2-NEW-1 strategist cap 30%→50% → c2ab7b1a

c2ab7b1a 實際做了：
- ✅ Rust 加 strategist_skill.name="wide_parameter_adjustment" payload
- ✅ Python prompt 暴露 normal_range (≤30%) + wide_skill_range (30-50%)
- ❌ **明確拒絕加 supervised gate**：原文「Rust still enforces the configured maximum envelope. **It does not add a new supervised gate**」
- ❌ **無 ADR**（grep `docs/adr/0021*` 0 hit）

**FA verdict**：⚠️ **PARTIAL（治理路徑分歧而非閉環）** — operator 選「freedom not gate」路徑；50% 偏離通過 max envelope clip 進入 live；無 staged rollout。

### A.2 NEW-ISSUE-3 cron not installed → da2aba11

da2aba11 實際：
- ✅ source 修正：ml_training_maintenance.py 區分「operational 5 jobs」vs「audit 5 jobs」
- ✅ audit jobs 真實 IMPL：thompson_sampling 真讀 trading.fills 寫 learning.bayesian_posteriors 等 4 表
- ❌ **cron 仍 NOT installed**

**FA verdict**：⚠️ **PARTIAL（source open, runtime NOT installed）** — IMPL 真寫比 v2 預期高，但 v2 outstanding 是「cron not installed」未 install。學習 +1%。

### A.3 6 表 0 INSERT → 48227607

48227607 實際修的是「DSR/PBO promotion evidence 連線」，**不是** v2 ❌#6（feature_baselines / drift_events / scorer_predictions / cost_edge_advisor_log）的 INSERT path。

**FA verdict**：❌ **NOT COVERED**（DSR/PBO 是 promotion gate，不是 6 表 INSERT path）

### A.4 Verified runtime restart / deploy → ❌ 0 commits

5 commits 全 source/test；W-AUDIT-3 fail-closed shadow→submit metrics **仍未從 runtime 驗證**。

### A.5 H-8 PerceptionPlane / H-9 H0_GATE → ❌ 0 commits

5 commits 0 處觸碰；17 天 0 動作；W-AUDIT-5 next pass sunset ticket 也未開。

### A.6 W-AUDIT-4 reclassification 標籤明確化 → ❌ 0 commits

TODO v17 標 W-AUDIT-4「❌ 仍降級」但 6 表分別開 INSERT path P1/P2 ticket 缺。

### A.7 covered 矩陣

| v2 outstanding | v3 verdict |
|---|---|
| F-01 runtime 未 deploy | ❌ 未動 |
| W-AUDIT-4 reclassification 降級 | ❌ 未動 |
| 6 表 0 INSERT | ❌ 未動 |
| cron not installed | ⚠️ source 真進步，runtime 0 |
| H-8 H-9 17 天 0 動作 | ❌ 未動 |
| v2-NEW-1 strategist cap | ⚠️ 治理路徑分歧 |

**真實覆蓋率：0 完整 cover / 2 partial / 4 untouched**

## §2 任務 B：PA redesign cross-check（FA functional spec 視角）

### B.1 PA 5 root cause 是否真實存在 spec 層

| PA 根因 | spec 證據 | FA 核實 |
|---|---|---|
| 1 Strategy Interface alpha-poverty | EX-06 §4.1 + DOC-02 scanner OHLCV-centric | ✅ **真實存在**（TickContext 部分準備但 first-class object 缺）|
| 2 Strategist scope 縮在「調 5 策略」| EX-06 §4.1.155-165 + `_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded | ⚠️ **部分 disagree**：EX-06 §4.1.159 字面寫「自主孵化策略」— spec 列了但 IMPL 0%。**這是 spec 與 IMPL gap，不是 spec 缺** |
| 3 Analyst L2-L5 dormant + ADR-0020 | EX-06 §6.2 + ADR-0020 | ⚠️ **PA 解讀有 nuance**：ADR-0020 禁的是「Layer2 autonomous trading loop」，不是「Layer 2 alpha-source proposal」。PA §3.2 R-2 自己也認。**不衝突** |
| 4 風控鐵血 vs alpha 放羊 | DOC-01 §5.1-5.16 risk-side dense + 4 risk_config × 4 環境 vs 1 strategy_params × 4 環境 | ✅ **真實存在**：spec 不對稱性 verifiable |
| 5 5-Agent 拆分骨架對但靈魂沒裝 | EX-06 5-Agent spec 完整 vs runtime 4 空殼 | ✅ **真實存在** |

**FA verdict**：5 根因中 **3 完全 verified（1/4/5）/ 1 spec 與 IMPL gap（2）/ 1 不衝突而互補（3）**

### B.2 EX-06「自主孵化」字面在哪？

**FA 直查 EX-06**：
- **第 159 行**（§4.1）：「策略匹配（MA Crossover / Grid / Funding Arb / BB Breakout / **自主孵化策略**）」
- **第 228-263 行**（§6 Analyst）：完整列五層 L1-L5 + §6.3 5 步策略孵化流程；步驟 4「**自动进入 live（不需要 Operator 预批准）**」是非常激進的 spec 條文，與所有 supervised gate 設計強烈不一致

**FA verdict**：✅ **PA claim 不是引申，是 spec 字面**

**FA 加值發現（Spec drift）**：SPECIFICATION_REGISTER.md 第 43 行對 EX-06 描述為「**Agent Conflict Arbitration** / multi_agent_framework.py」— **完全沒提「策略孵化」職責**。Register summary 漂移於 EX-06 V1 source-of-truth。FA 開新 ticket P2-DOC-DRIFT-1。

### B.3 ADR-0020 vs PA「Strategist alpha-source orchestrator」是否衝突？

✅ **不衝突**。ADR-0020 禁「autonomous trading loop」；PA Strategist alpha-source orchestrator 是「propose alpha-source hypothesis」（產出 Hypothesis 對象，非 TradeIntent）。PA 自己已 acknowledge ADR-0020 合理性。

**驗收**：propose_alpha_source() 產出 Hypothesis → Hypothesis Pipeline governance → 不直接生成 TradeIntent。

### B.4 PA「architecture 系統性產生 alpha-deficient 策略」是否符合實證？

✅ **完全符合 PG 直查實證**：demo 7d gross -26.44 USDT (funding_arb -15.43 / grid -11.15 / ma +0.20 / bb -0.06)。不是「策略需要更好參數」，是「5 策略架構性吃同一個 alpha source（TA），互相 cannibalize」。

### B.5 PA Cluster A-G 對 W-AUDIT-1..7 的批判

PA Layer 4 主張：
- W-AUDIT-2 / -5 純維護必做
- W-AUDIT-4 應併入 R-3 Hypothesis Pipeline
- W-AUDIT-7 Layer 2 部分換成 R-2 Strategist alpha-source proposal
- W-AUDIT-6 戰略 ROI 低，建議只做 minimum

**FA verdict**：⚠️ **AGREE on direction, partial DISAGREE on sequencing**
- W-AUDIT-6 戰略 ROI 低 ≠ 不做：v2 已實證 W-AUDIT-6 部分 IMPL（DSR/PBO + Kelly RiskConfig + funding_arb retire）對「治理機制完備」有 governance 價值
- W-AUDIT-4 併入 R-3 風險：scope creep 高
- PA Sprint N+5「First per-alpha-source supervised live promotion」**過樂觀**：FA 估 8-10 sprint 而非 6-8

## §3 對抗性 Push Back（5 條）

### #1（最關鍵）：5 commits 全 source-only 是「敏捷錯覺」
5 commits 連續延續 v2「打 source 不打 deploy」模式。看似生產力高，實際業務鏈 0 增量。**FA 要求**：每 5 commits 至少 1 次 deploy。當前 v2→v3 5 commits = 業務鏈 +1%。

### #2：v2-NEW-1 strategist cap 治理方向 operator 已決，但**仍欠 ADR**
**FA 要求**：補 `docs/adr/0021--strategist-wide-adjustment-skill.md`，記錄：(1) 為何選 freedom-not-gate；(2) 與 SM-05 Option A 張力處理；(3) live_reserved 階段是否仍允許 50%；(4) 監測指標。

### #3：6 表 0 INSERT 已是 18 天無變動的結構性 gap
v2 ❌ → v3 ❌（含 v1 → v2 → v3 = 3 輪 0 進度）。**FA 要求**：把 6 表逐一升 P1，每表開獨立 ticket（owner agent → INSERT writer 真實接通 callsite → runtime 24h fire 驗）；E5/MIT/E1 共擔。

### #4：H-8 / H-9 17 天 0 動作 sunset 決策必須執行
W-AUDIT-5 next pass 內**強制**做：補 caller OR 開 sunset ADR；17 天再不決策成永久戰略迷霧。

### #5：PA W-AUDIT-6 ROI 評估觸碰 governance 議題
W-AUDIT-6 已 IMPL 13+ commits，其中**機制價值**（DSR/PBO promotion gate / Kelly RiskConfig / per_trade_risk_pct SSOT）與 alpha 收益正交。**FA 立場**：AGREE 不升優先 + maintenance only；DISAGREE「W-AUDIT-6 不應做」。真正陷阱是「operator 對 5 個 TA 策略持續微調 RFC」的時間。

## §4 與 PA fix plan §6 wave closure 對齊（v3）

| Wave | TODO v17 自報 | FA v3 真實 verdict |
|---|---|---|
| W-AUDIT-1 docs sync | ✅ 真 close | ✅ 維持 |
| W-AUDIT-2 security | ✅ runtime verified | ✅ 維持 |
| W-AUDIT-3 ExecutorAgent | ⚠️ partial | ⚠️ 維持（runtime fail-closed metrics 仍未驗） |
| W-AUDIT-4 ML 基座 | ❌ 仍降級 | ❌ 維持（cron 仍未 install + 6 表 0 INSERT 18 天 0 進度） |
| W-AUDIT-5 性能 | ⚠️ partial | ⚠️ 維持（H-8/H-9 17 天 0 動作） |
| W-AUDIT-6 策略 | ✅ source/test closed | ⚠️ governance 機制 close ✅ / alpha 收益 close ❌ |
| W-AUDIT-7 GUI/AI | ⚠️ partial + 🆕 治理矛盾 | ⚠️ 維持（c2ab7b1a 改 frame skill not gate；無 ADR） |

**v2 → v3 wave 變化矩陣**：W-AUDIT-3/-4/-5/-7 全部「維持 v2 verdict」。實質 wave 進度 0。

## §5 業務鏈完整度（v2 ~62% → v3 ~63%）

```
自動掃描 95% / 策略選擇 56% (+1% c2ab7b1a) / AI 風控 80% / 下單 35% / 止損 95% /
學習 31% (+1% da2aba11 audit jobs IMPL source path) / 進化 35% / 觀察 85%
加權平均 ≈ 63% (+1%)
```

**對抗性結論**：5 commits 24h sprint 是 **source path refinement sprint**，非 functional progress sprint。+1% 是 generous estimate。

## §6 PA Redesign Verdict：**AGREE**

**AGREE 理由**：
1. 5 根因中 3 完全 verified / 1 spec-IMPL gap / 1 互補非衝突
2. 88 finding 5-7 cluster 抽取準確
3. 「先修完 88 不會盈利」結論支持實證
4. EX-06 §4.1 + §6 strategy incubation 字面 spec 確實存在但 IMPL 0%
5. 5 策略 7d demo -26.44 USDT 與 PG 直查吻合
6. R-1 R-2 R-3 R-4 R-5 設計順序合理

**保留 / 不完全 AGREE**：
1. PA Sprint N+5「First per-alpha-source supervised live promotion」過樂觀（FA 估 8-10 sprint）
2. W-AUDIT-4 併入 R-3 風險（scope creep）
3. W-AUDIT-6 戰略 ROI 低 ≠ 不做：governance 機制 close 仍有價值
4. R-1 R-2 對「TickContext 升級」的 backward compat 評估略樂觀

**FA 加值補充**：
- SPECIFICATION_REGISTER 對 EX-06 描述漂移 → 開 P2-DOC-DRIFT-1
- EX-06 §6.3 步驟 4「自动进入 live（不需要 Operator 预批准）」與所有 supervised gate 強烈不一致 — 必須在 ADR / EX-06 V2 中 reconcile
- PA R-3 對 attribution_chain_ok 0.5% 修法精準：「沒有 hypothesis 哪來歸因 chain」是 FA v2 沒看出的關鍵 root cause

## §7 24h 最緊要 actions

1. operator 把 c2ab7b1a 補 ADR-0021（freedom-not-gate rationale + 與 SM-05 張力 + 50% 偏離監測指標）
2. PA 把 6 表升 P1 + 開 owner-agent ticket
3. operator 授權 `crontab -e` 安裝 da2aba11 5 audit jobs cron
4. operator 拍板 R-1 spec phase 啟動：W-AUDIT 8a「Alpha Surface Foundation」
5. W-AUDIT-5 next pass 強制 H-8/H-9 sunset 決策
6. SPECIFICATION_REGISTER 對 EX-06 描述補 §4.1 + §6 strategy incubation

---

**FA VERIFICATION v3 DONE** · ✅ 4 / ⚠️ 5 / ❌ 6 / 🆕 1 · 業務鏈 ~63% · PA redesign verdict: AGREE

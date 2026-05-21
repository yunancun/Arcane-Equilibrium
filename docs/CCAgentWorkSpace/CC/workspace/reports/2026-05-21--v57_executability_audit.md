# v5.7 Dispatch-Safe Patch 執行性審核 — CC 視角
**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.7 修對 6 條 engineering precision 漂移，但 §4 Earn stake 觸碰原則 1（單一寫入口）、原則 3（Decision Lease 實作未具體化）、9 安全不變量未覆蓋 redeem fail-closed；Sprint 1A 派 PA 前必先補 5 個 must-fix 規格細節。

## 0. 16 根原則逐條對照

| # | 原則 | 狀態 | 理由 |
|---|---|---|---|
| 1 | 單一受控寫入口 | **WARN** | §4 Earn stake = 新資產寫入操作。v5.7 寫「same risk envelope as trading operations」「Decision Lease pattern」但未說明 stake intent 是否走既有 `IntentProcessor` / `submit_intent` 統一入口，還是新建 EarnIntent 第二入口。**規格不足以保證原則 1**。 |
| 2 | 讀寫分離 | PASS | §4 第 1 條 APR query 是讀;stake/redeem 是寫;§5 macro/on-chain Y1 為 read-only logging 明確隔離。 |
| 3 | AI 輸出 ≠ 命令 | **WARN** | §4 第 2 條「Decision Lease pattern: stake intent → guardian → execute → audit log」是 pattern 描述，非實作規格。誰 emit stake intent？AI（Allocator）？操作員？「Manual rebalance initially (first 3 months); auto after proven」—— auto 後是否走 Decision Lease 完整鏈條未明。 |
| 4 | 策略不繞風控 | PASS | §4 第 2 條明示 Guardian-checked + same risk envelope；§5 counterfactual logging 不觸發 strategy triggers。 |
| 5 | 生存 > 利潤 | PASS | §9 Kill Criteria（v5.6 §9 繼承 v5.7 未改）涵蓋 D2 hard stop $3,000 + Bybit Earn 產品撤回 auto-redeem；§1 honest 估算放棄 macro/on-chain alpha 屬保守。 |
| 6 | 失敗默認收縮 | **WARN** | §4 第 2 條「Auto-redeem trigger: trading margin headroom < 30%」是收縮觸發，但 Earn API 超時或 retCode != 0 時的 fail-closed 行為**未規格**。9 不變量 #7（Bybit retCode != 0 → fail-closed）未在 Earn 路徑覆蓋。 |
| 7 | 學習 ≠ 改寫 Live | PASS | §5 Y1 counterfactual logging 明示「NOT applied to actual strategy triggers in Y1 production」「Counted as ZERO income」；Y2 enable 需 verification + 應走獨立 governance（隱含但 v5.7 未明示路徑）。 |
| 8 | 交易可解釋 | PASS | §4 第 3 條 `learning.earn_movement_log` 表記錄 amount / direction / APR / governance approval；§3 V103/V104 schema 含 `trading.fills.track` column。 |
| 9 | 災難保護雙重防線 | **WARN** | §4 Earn 路徑無交易所側 conditional 對應物（Earn 不是 perp，無 conditional order 概念）；但「Auto-redeem trigger: margin < 30%」是本地單一防線。若 Earn API 失靈導致 redeem 失敗 → 交易主帳 margin 進一步下滑 → 風控連環失效路徑**未討論**。 |
| 10 | 認知誠實 | PASS | §1 Honest Y1 + §2 Honest Y2 明確區分 verified / unverified；§5 counterfactual 不計入 alpha。reviewer §2 修正 v5.6 overoptimistic 是事實層誠實的典範。 |
| 11 | Agent 最大自主（P0/P1 內） | PASS | §7 Advisory Allocator Sprint 7-10 為 advisory，Auto-Allocator gate 至 Y2 + 80% approval rate；Agent 不繞 P0/P1 邊界。 |
| 12 | 持續進化 | PASS | §5 counterfactual evaluation 末端「If overlay 真 alpha → Y2 enable / If null → retire layer」是 evidence-based evolution；§3 hypothesis_preregistration 表是進化骨架。 |
| 13 | AI 成本感知 | **WARN** | §5 counterfactual logging 引入持續性 macro/on-chain 計算成本（70-95 hr 開發 + 持續運行）但 v5.7 未對 counterfactual 自身做 cost_edge_ratio 評估。「null/marginal → retire layer」是 alpha gate，非 cost gate。 |
| 14 | 零外部成本可運行 | PASS | §3-§5 macro feed / on-chain signals 走 free tier（Glassnode free / Etherscan public / DeFiLlama）；v5.6 §3 提及 paid tier 需 operator approve before upgrade。 |
| 15 | 多 Agent 協作 | PASS | §7 Advisory Allocator = operator approves via Console + Decision Lease + Guardian + Stage gate；Allocator 不是第六交易 agent，是 advisory tool。 |
| 16 | 組合級風險 | PASS | §8 Portfolio Stress Test（v5.6 繼承）5 scenarios + correlation 1.3-1.5x；§4 Earn + 主帳整體餘額互動於 Scenario 3（Bybit halt）已涵蓋。 |

**統計**：PASS 11 / WARN 5 / FAIL 0 → 16/16 無硬違反；5 條 WARN 主因 Earn 路徑規格不足。

## 0.5 9 安全不變量

| # | 不變量 | 狀態 | 理由 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | PASS | §12 Stage Gate 鏈含 STAGE_0R_REPLAY_PREFLIGHT；§3 hypothesis_preregistration 為 pre-trade 證據 |
| 2 | Lease 必在執行前 acquired | **WARN** | §4 第 2 條提 Decision Lease pattern 但 Earn 路徑是否獨立 lease type 還是復用 trading lease 未明 |
| 3 | 執行回報必落 fills 表 | PASS | §4 第 3 條 learning.earn_movement_log（Earn 不屬 fills 但有獨立審計表）；§3 trading.fills.track column 對 trading fills |
| 4 | 風控降級 → engine 自動止血 | PASS | §9 Kill Criteria（v5.6 繼承）含 portfolio cum loss > $3,000 hard stop；Bybit Earn 產品撤回 auto-redeem |
| 5 | Authorization 過期/失效 → cancel_token shutdown | **WARN** | v5.7 未討論 authorization.json 對 Earn 操作的覆蓋範圍。Earn API 是否在 5-gate 邊界內未明 |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | PASS | §12 Stage Gate STAGE_4_LIVE_PENDING 含「5-gate boundary」（隱含完整） |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | **WARN** | §4 Earn API 路徑未明 retCode 處理；v5.6/v5.7 都沒涵蓋 Earn API 失敗模式（CLAUDE.md §四明訂「Bybit API timeout or nonzero retCode fails closed」適用 ALL Bybit-facing 路徑） |
| 8 | Reconciler 對賬差異 → 自動降級 paper | **WARN** | §4 第 3 條「Daily reconciliation with Bybit account balance」存在但對賬失敗時行為**未規格**。Earn ≠ paper（CLAUDE.md §四明示 paper not active），所以「降級 paper」邏輯需替換為「降級到 manual mode」之類 |
| 9 | Operator 角色 + live_reserved 缺一即拒 | **WARN** | Earn stake 是否需 Operator role auth + live_reserved 邊界內？v5.7 未明示。若視為「asset write = trading-grade」必須適用 |

**9 不變量統計**：PASS 4 / WARN 5 / FAIL 0 → Earn 路徑 5 個 WARN 都集中在「Earn 是否 inherit Live trading 級別的所有 fail-closed 行為」這個未明示假設。

## 1. Top 3 執行性風險（排序）

### Risk 1：Earn stake/redeem 寫入路徑規格不足（觸碰原則 1 + 9 安全不變量 #2/#5/#7/#8/#9）
- 嚴重度：**HIGH**
- 位置：v5.7 §4 第 2 條 + 第 4 條
- 描述：
  - v5.7 §4 寫「Decision Lease pattern」「Guardian-checked」「audit log」屬目標性描述，非實作規格
  - 未說明：（a）stake intent 是否走既有 `IntentProcessor` 還是新建 EarnIntent 入口（原則 1）；（b）Decision Lease 是新 lease_type=earn_stake 還是復用 trading lease（不變量 #2）；（c）Earn API retCode != 0 時的 fail-closed 行為（不變量 #7）；（d）daily reconciliation 失敗時降級路徑（不變量 #8）；（e）authorization.json 是否覆蓋 Earn（不變量 #5/#9）
  - Engineering 估 45 hr（API 15 + Governance 20 + Audit 10）是合理 ceiling 但前提是 reuse existing IntentProcessor + GovernanceHub
- 為何屬「執行性」（非邏輯）：
  - v5.7 §4 thesis 正確（Earn = asset write = trading-grade governance），但執行細節缺失意味著 PA 派發後 E1 設計時可能走偏（例如建第二寫入口）
  - 屬於「策略對、戰術未明」的執行性 gap
- Must-fix 建議：
  - Sprint 1A 派 PA 前補一份 `2026-05-21--earn_governance_spec.md`，明確：
    - Stake intent 復用 `IntentProcessor.submit_intent(intent_type='earn_stake')`，**不**新建寫入口
    - Decision Lease 復用既有 lease 框架，新增 `lease_type='earn_stake'` 和 `lease_type='earn_redeem'`
    - Earn API 失敗 → fail-closed → 不重試（同 CLAUDE.md §四 Bybit API rule）
    - Daily reconciliation 失敗 → 自動 disable Earn stake/redeem until manual review（非「降級 paper」，paper not active）
    - Earn 操作受 5-gate 邊界保護（live_reserved + Operator role + OPENCLAW_ALLOW_MAINNET + secret slot + authorization.json）
    - 對應 ADR-0030（Earn asset movement Guardian policy）需在 PA 前 draft

### Risk 2：counterfactual logging 自身 cost_edge_ratio 未評估（觸碰原則 13）
- 嚴重度：MEDIUM
- 位置：v5.7 §5 + §9
- 描述：
  - §5 macro/on-chain counterfactual 70-95 hr 開發 + 持續運行成本（feed polling、計算、storage）
  - v5.7 把 Y1 macro/on-chain alpha 計為 $0，但 counterfactual 自身的「研發 + 運行成本」未對沖入 honest income
  - 若 Y1 末 counterfactual 顯示「null/marginal」，70-95 hr engineering 是 sunk cost
  - 原則 13「AI calls have cost and must justify expected edge」延伸：counterfactual layer 也有 cost
- 為何屬「執行性」（非邏輯）：
  - 邏輯上 counterfactual-only 是正確的方法（reviewer §5 fix 對）
  - 執行性 gap = 沒有 Y1 末 evaluation 標準明示 retire threshold（counterfactual A/B 顯示多少 alpha 才算 verified？v5.7 §5 寫「+2%+ on strategies → Y2 enable」但這個 +2% 的統計顯著性測試方法未明）
- Must-fix 建議：
  - Sprint 1A 階段同時定義 Y1 末 counterfactual evaluation 模板（hypothesis_preregistration 表 schema 應包含）
  - 「+2%+」需附 t-stat 閾值（建議 ≥ 1.5 同 §6 evidence ranking）和 minimum sample（建議 30+ macro events / 60+ on-chain signals）
  - 若不滿足顯著性 → retire layer + memorialize counterfactual evidence；engineering 視為 R&D cost
  - v5.7 §9 Kill Criteria 已有「Macro overlay false positives > 3/month」和「On-chain signals 0 actionable alpha after Sprint 6」，但 Sprint 6 = W23，counterfactual-only mode 是否適用提前 retire 邏輯未明

### Risk 3：Migration V103/V104 placeholder 與 V101/V102 race（觸碰原則 8 + §七 Code rule）
- 嚴重度：MEDIUM
- 位置：v5.7 §3 + §8 Sprint 1A
- 描述：
  - v5.7 §3 明示 V101/V102 已被 Track schema 預留（12 表 attribution）
  - v5.7 placeholder V103/V104 + 「PA dispatch finalizes」= 派發時才定 final number
  - Linux DB 當前 head 在 dispatch time 是 race-aware sequencing 變量
  - V103/V104 schema 對應 `learning.hypotheses` + `learning.hypothesis_preregistration` + `trading.fills.track` —— 若 Track 12 表 attribution 在 Sprint 1A 平行展開，**V103 可能變 V105 或更高**
  - Sprint 1A engineering 60-80 hr 預算未明示是否含 migration 號碼最終化的 buffer
  - 同時 `srv/docs/agents/context-loading.md` 提到 V### migration PG dry-run mandatory（feedback_v_migration_pg_dry_run），v5.7 §3 未明示 Sprint 1A 派發前是否需要 Linux PG empirical dry-run
- 為何屬「執行性」（非邏輯）：
  - 邏輯上 V103/V104 名字不重要，重要的是內容
  - 執行性風險 = PA 派發時若隔壁有 in-flight migration 未提及，可能產生 schema race
- Must-fix 建議：
  - Sprint 1A 派發 prompt 必含「執行前 `ssh trade-core 'cd ~/srv && psql ... SELECT max(version) FROM _sqlx_migrations'`」確認 head
  - V103/V104 邏輯內容（CREATE TABLE 結構、column 名）在 spec 內 lock，只有 V### 號碼可變
  - PA 派發後若決定號碼變動，需 update v5.7 § 3 + ADR-0029
  - PG empirical dry-run（per feedback_v_migration_pg_dry_run 2026-05-05 教訓）必在 E1 IMPL 設計前完成

## 2. Hours sanity check（合規工時 vs estimate）

| Sprint | Focus | v5.7 Hours | Compliance 工時意見 |
|---|---|---|---|
| 1A | Governance + Migration + Sensors | 60-80 | **保守 LOW** — 加 Earn governance spec draft（10 hr）+ ADR-0030 draft（5 hr）+ PG dry-run（5 hr）= 80-100 hr 更現實 |
| 1B | C10 + Earn live + Tournament prep | 50-70 | **OK** — 前提是 Earn 路徑復用 IntentProcessor + GovernanceHub。若需新 lease_type，加 15 hr。實際 65-85 hr |
| 2 | Alpha Tournament + Microstructure + On-chain counterfactual setup | 110-150 | **OK** — counterfactual 走 free tier API + read-only logging 是 lower bound 合理 |
| 3-10 | 後續 sprints | 各 70-210 | 未深入審 — Sprint 1A/1B 是 dispatch 入口，後續 sprints 在 1A/1B 結果後重估 |

**整體 1,190-1,590 hr 39 weeks 工時**：
- vs v5.6 1,180-1,570 hr 大致 same，但「reallocated」說法合理（liquidation healthcheck 省 15-20 hr，Earn governance + 35 hr，macro/on-chain counterfactual -10 hr）
- 工時 buffer **無**對 reviewer rounds 16+ 可能新發現問題的緩衝
- 建議 Sprint 1A 80-100 hr（不是 60-80）

## 3. 未識別的依賴 / 阻塞（governance）

1. **ADR-0030 草案缺失**：v5.7 §12 列 ADR-0030（Bybit Earn asset movement Guardian policy）為「proposed」，Sprint 1A 派發前需 draft；ADR proposed → accepted 走標準流程
2. **AMD-2026-05-15-01 對 Earn 的覆蓋**：AMD-01 明示「Stage 1 Demo-only after green Stage 0R replay preflight」——Earn 不屬交易策略，但 Earn 是否需要走 Stage gate？v5.7 未對齊
3. **CLAUDE.md §四 5-gate boundary 對 Earn 的覆蓋**：硬邊界明示適用「true live」trading；Earn 是 asset write 但非 trading order；5-gate 是否 ALL 適用需 PM/operator 明示
4. **`docs/agents/todo-maintenance.md` 對 v5.7 dispatch 的 TODO 更新**：派發前需 TODO.md 新增 Sprint 1A 條目 + runtime evidence anchor（healthcheck id 或採集命令）
5. **`SPECIFICATION_REGISTER.md` 更新**：ADR-0028/0029/0030 proposed 狀態需在 register 內登記
6. **Bybit Earn API 速率限制與 secret slot 結構**：v5.7 §4 第 1 條 「Bybit API query for current tiered APR」需確認 secret slot 是否需新增 Earn-specific scopes，還是復用 trading API key（後者風險：API key compromise 影響面擴大）

## 4. 對 PA+FA 匯總的必收 top 3

1. **Earn governance spec（Risk 1 must-fix）**：FA 視角審 22 份治理文件 Gap 對 Earn 路徑的覆蓋；PA 視角拆 Sprint 1A 任務時必含 spec draft 為 sub-task；建議獨立 ADR-0030 + earn_governance_spec.md
2. **V103/V104 邏輯內容 lock（Risk 3 must-fix）**：PA 派發前需 Linux PG empirical dry-run；FA 視角確認 V101/V102 Track schema 工作有無 in-flight；建議 `docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` 寫定 schema 細節（不含號碼）
3. **counterfactual evaluation 模板（Risk 2 must-fix）**：FA 視角確認 hypothesis_preregistration 表 schema 需含 t-stat 預期 / minimum sample；PA 視角加 Sprint 1A sub-task：定義 macro/on-chain Y1 末 evaluation 統計顯著性閾值

## 5. Sprint 1A 派發前 must-fix（CC 強制 fail-closed 項目）

以下 5 項缺一即 CC 拒批 Sprint 1A 派 PA：

1. **Earn governance spec 完成**（含 stake 走 IntentProcessor / lease_type / 5-gate 適用範圍）— 對應 ADR-0030 draft
2. **9 安全不變量 #7（Bybit retCode != 0 fail-closed）延伸到 Earn API 路徑明示** — 在 Earn governance spec 內第 X 條
3. **counterfactual evaluation 統計閾值定義**（t-stat ≥ 1.5 + minimum sample 30+/60+）— 對應 v5.7 §5 補充段或新 spec
4. **V103/V104 schema 邏輯內容 lock**（CREATE TABLE 結構、column 名、index）— 對應 `2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
5. **Sprint 1A 派發 prompt 含 Linux PG empirical dry-run 步驟**（per feedback_v_migration_pg_dry_run 2026-05-05）

## 6. Sprint 1B-3 should-fix

- **Sprint 1B**：Earn 首次 manual stake $200-400 需先走完整 Decision Lease 走查（即便是 manual，鏈條完整性需驗）；建議 Sprint 1B 加入「first stake operation governance walkthrough」sub-task
- **Sprint 2**：on-chain signals 走 free tier，但 Glassnode rate limit / Etherscan public API rate limit 需在 Sprint 1A 末 ping test 驗證可行性；否則 Sprint 2 才發現 rate limit 不足造成延誤
- **Sprint 3**：Top-1 build 期間 macro overlay activation（v5.6 §7 Sprint 3 內容）—— v5.7 已將 macro 移到 counterfactual-only，但 Sprint 3 是否仍需 macro overlay activation 步驟需確認；可能 Sprint 3 純做 Top-1 + counterfactual feed 即可

## 7. 可優化 / 拆分 / 並行

1. **Sprint 1A 拆 1A-gov + 1A-sensor 並行**：
   - 1A-gov：ADR-0030 + Earn governance spec + V103/V104 schema spec + counterfactual evaluation 統計閾值（25-30 hr，1 週）
   - 1A-sensor：existing market.liquidations healthcheck + options recorder + Tokenomist + macro feed + Binance WS + APR recorder（35-50 hr，1-1.5 週）
   - 兩條並行可壓 Sprint 1A 從 1.5 週到 1 週
2. **counterfactual logger 與 strategy live 並行解耦**：v5.7 §5 已暗示但未明示——Sprint 2 setup + Sprint 3+ logger 持續運行，與 strategy build 完全解耦，可由不同 agent owner（如 AI-E + DA）
3. **Earn governance spec 與 hypothesis_preregistration schema 共用 audit log 設計**：兩者都需 append-only JSONL + governance approval column；建議 PA 拆 sub-task 時讓兩者共用 schema helper（DOC-06 Change Audit Log 風格）
4. **V103/V104 placeholder 在 dispatch 時可能變 V105/V106**：若 V101/V102 Track schema 已 in-flight，Sprint 1A 不要急 V103/V104，先做 sensor 部分，等 Linux head update 後 finalize 號碼
5. **Reviewer rounds 16+ 緩衝**：v5.7 是 rounds 1-15 收斂結果，但 v5.6 → v5.7 揭露 6 個 verified issues 說明 reviewer audit 仍可發現問題；建議 v5.7 dispatch 前再開 1 輪 reviewer round 16 對 §4 Earn 路徑深審（CC 視角已標 5 個 WARN 集中在此）

---

**CC AUDIT DONE: GO-WITH-CONDITIONS**

**核心結論**：
- v5.7 vs v5.6 的 6 條 engineering precision 修正全部正確且合規
- 但 §4 Earn 路徑是 v5.7 引入的 governance 新面，5 條原則 WARN + 5 條安全不變量 WARN 集中於此
- Sprint 1A 派 PA 必須先補 5 個 must-fix（Earn governance spec + 9不變量#7延伸 + counterfactual統計閾值 + V103/V104 schema lock + PG dry-run prompt）
- 工時 Sprint 1A 60-80 hr 偏低，建議 80-100 hr 含 governance draft buffer
- 5 條 WARN 不升 BLOCKER 的原因：thesis 對、目標性描述正確，只是執行性規格不足；補 spec 即可放 GO

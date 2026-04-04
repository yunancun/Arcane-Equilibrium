# Comprehensive Audit Template v1
# 全面審查模版 v1
# Last updated: 2026-04-04

## Trigger Levels / 觸發級別

| Level | When / 觸發時機 | Roles / 喚醒角色 |
|-------|----------------|-----------------|
| **L1 Light** | Single Phase/Wave done | E2 + E4 + E5 |
| **L2 Standard** | Strategy/model changes | E2 + E4 + E5 + QA Audit |
| **L3 Full** | Major milestone (multi-Phase) | PA + PM + FA + QC + CC + E2 + E3 + E4 + E5 |

## L3 Full Audit: 5 Parallel Agent Groups / 5 路並行分組

| Agent | Roles | Focus | Output |
|-------|-------|-------|--------|
| 1 | PA + PM | Architecture + Project Mgmt | Design gaps / scope creep / risks / timeline |
| 2 | FA + QC | Functional + Quantitative | E2E trace / formula verify / param sanity |
| 3 | CC + E3 | Compliance + Security | 16 principles / SQL injection / creds / perms |
| 4 | E2 + E5 | Code Review + Optimization | Per-file review / perf / dead code / style |
| 5 | E4 | Regression Testing | Full suite + engine health + DB health |

## Conditional Add-on Roles / 條件性附加角色

| Condition / 條件 | Add Role / 附加角色 | Focus / 焦點 |
|------------------|--------------------|----|
| DL/Learning/ML changes | **MIT (ML/DL Expert)** | Model architecture, training pipeline, data leakage, overfitting, feature engineering, loss function, evaluation metrics, deployment safety |
| Database changes | **E5 (DB Performance)** | Query plans (EXPLAIN ANALYZE), index effectiveness, partition strategy, compression ratio, connection pooling, vacuum settings, write amplification |

### MIT (ML/DL Expert / 機器學習專家) — DL/Learning 專項
1. Model architecture — appropriate for the task? Over/under-parameterized?
   模型架構 — 是否適合任務？參數過多/過少？
2. Training pipeline — data split, cross-validation, early stopping
   訓練管線 — 數據切分、交叉驗證、早停
3. Data leakage — feature engineering uses future info? Target leakage?
   數據洩漏 — 特徵工程是否使用了未來信息？標籤洩漏？
4. Overfitting risk — regularization, dropout, ensemble diversity
   過擬合風險 — 正則化、dropout、集成多樣性
5. Evaluation metrics — calibration, AUC, Brier score, bootstrap CI
   評估指標 — 校準、AUC、Brier 分數、bootstrap 置信區間
6. Deployment safety — ONNX export correctness, inference latency, fallback chain
   部署安全 — ONNX 導出正確性、推理延遲、降級鏈
7. Echo chamber prevention — scorer not trained on its own predictions
   回聲室防護 — scorer 不在自身預測上訓練

### E5-DB (Database Performance / 數據庫性能) — DB 專項
1. Query plans — EXPLAIN ANALYZE on critical queries
   查詢計劃 — 關鍵查詢的 EXPLAIN ANALYZE
2. Index effectiveness — unused indexes? Missing indexes for common queries?
   索引有效性 — 未使用的索引？常用查詢缺少索引？
3. Partition/chunk strategy — TimescaleDB chunk intervals appropriate?
   分區策略 — 分塊間隔是否合適？
4. Compression ratio — actual compression achieved?
   壓縮比 — 實際壓縮效果？
5. Connection pooling — pgbouncer needed? Max connections?
   連接池 — 是否需要 pgbouncer？最大連接數？
6. Write amplification — batch INSERT vs single INSERT?
   寫放大 — 批量 INSERT vs 單條 INSERT？
7. Vacuum/analyze — autovacuum settings appropriate for write pattern?
   清理/分析 — autovacuum 設置是否適合寫入模式？

## Per-Role Checklists / 各角色審查清單

### PA (Project Architect / 項目架構師)
1. Architecture consistency — does new code align with CLAUDE.md?
   架構一致性 — 新代碼是否符合 CLAUDE.md？
2. Abstraction quality — clean traits/interfaces, no leaky abstractions?
   抽象質量 — trait/interface 是否乾淨？
3. Dependency direction — core ← engine ← main respected?
   依賴方向 — 是否遵循正確方向？
4. Design gaps — gap between built vs next Phase needs?
   設計缺口 — 已建與下一 Phase 需求之間？
5. Dead abstractions — built but will never have consumers?
   死抽象 — 建了但永遠不會被使用？
6. Scalability — IPC/DB/API support target scale?
   可擴展性 — 能否支撐目標規模？
7. Cross-platform — grep `/home/ncyu` in new code
   跨平台 — 新代碼有無硬編碼路徑？

### PM (Project Manager / 項目經理)
1. Scope creep — any changes beyond original requirements?
   範圍蔓延 — 是否超出原始需求？
2. Timeline — ahead/behind/on schedule?
   時間線 — 提前/延遲/準時？
3. Prerequisites — all blockers for next Phase cleared?
   前置條件 — 下一 Phase blocker 是否已清除？
4. Risk register — top 3 risks + mitigation
   風險登記 — Top 3 風險 + 緩解方案
5. Estimate calibration — actual vs estimated effort
   估計校準 — 實際 vs 預估偏差

### FA (Functional Auditor / 功能審計師)
1. End-to-end trace — full path from data source to output for each feature
   端到端追蹤 — 每個功能的完整數據路徑
2. FAKE/DEAD scan — claimed but unreachable features
   FAKE/DEAD 掃描 — 聲稱實現但不可達的功能
3. Feature gap list — all CONDITIONAL/stub/placeholder features
   功能缺口清單 — 所有 CONDITIONAL/stub/placeholder
4. Test coverage — at least 2 tests per new feature?
   測試覆蓋 — 每個新功能至少 2 個測試？
5. Python V2 comparison — does new code actually surpass old?
   與 Python V2 對照 — 是否真正超越？

### QC (Quantitative Consultant / 量化顧問)
1. Formula correctness — all indicator/strategy/pricing formulas
   公式正確性 — 所有指標/策略/定價公式
2. Parameter defaults — reasonable for crypto markets?
   參數默認值 — 是否符合加密市場特性？
3. Numerical stability — div-by-zero/NaN/overflow guards
   數值穩定性 — 除零/NaN/溢出防護
4. Statistical methods — sampling/window/decay correct?
   統計方法 — 採樣/窗口/衰減是否正確？
5. Backtest bias — look-ahead/survivorship bias risk?
   回測偏差 — 前視偏差/生存偏差風險？

### CC (Compliance Checker / 合規檢查)
1. 16 principles — check against each, especially #4 #8 #10
   16 原則逐條對照 — 特別是 #4(風控) #8(可解釋) #10(誠實)
2. Bilingual comments — sample 5+ new functions
   雙語注釋 — 抽查 5+ 新函數
3. File size — 800 line warning / 1200 line hard limit
   文件大小 — 800 行警告 / 1200 行硬限
4. Workflow compliance — E2+E4 executed for every batch?
   工作鏈合規 — 每批都執行了 E2+E4？
5. Commit norms — CHANGELOG synced?
   commit 規範 — CHANGELOG 是否同步？

### E2 (Code Reviewer / 代碼審查)
1. Logic correctness — read every modified file
   邏輯正確性 — 逐文件閱讀
2. Edge cases — None/empty/zero/negative handling
   邊界條件 — None/空/零/負數處理
3. Naming consistency — variable/function/type naming style
   命名一致性 — 命名風格
4. Dead code/imports — unused imports, unreachable branches
   死代碼 — 未使用的導入和不可達分支
5. Duplicate code — cross-file copy-paste
   重複代碼 — 跨文件複製

### E3 (Security Auditor / 安全審計)
1. SQL injection — all DB operations parameterized?
   SQL 注入 — 所有 DB 操作是否參數化？
2. Credential exposure — passwords only in env/secrets?
   憑證暴露 — 密碼是否只在安全位置？
3. File permissions — IPC files, config files
   文件權限 — IPC 文件/配置文件
4. Network exposure — Docker ports restricted?
   網絡暴露 — Docker 端口是否限制？
5. Dependency security — new deps have known CVEs?
   依賴安全 — 新依賴有無已知漏洞？

### E4 (Test Engineer / 測試工程師)
1. Full suite — Python + Rust + Canary
   全量測試 — 三套測試全跑
2. Baseline comparison — delta from previous baseline
   基準線對比 — 與上次的 delta
3. Compilation warnings — target 0 warnings
   編譯警告 — 目標 0 warnings
4. Engine health — watchdog status + RSS memory
   引擎健康 — watchdog + 記憶體
5. DB health — table/hypertable/policy counts
   DB 健康 — 表數/hypertable/policy

### E5 (Optimization Reviewer / 優化審查)
1. Algorithm complexity — O(n) on hot paths?
   算法複雜度 — 熱路徑上的 O(n) 操作？
2. Memory allocation — clone/alloc on high-frequency paths?
   內存分配 — 高頻路徑上的 clone？
3. I/O efficiency — file/DB write frequency
   I/O 效率 — 文件/DB 寫入頻率
4. Serialization overhead — JSON/Serde size estimate
   序列化開銷 — JSON 大小估算
5. Resource leaks — file descriptors, connections, threads
   資源洩漏 — fd/連接/線程

## Output Format / 輸出格式

Each finding: `SEVERITY (CRITICAL/HIGH/MEDIUM/LOW) | ROLE-ID | Description | Recommendation`

Final summary table:
| Severity | Count | Key Items |
|----------|-------|-----------|
| CRITICAL | N | ... |
| HIGH | N | ... |
| MEDIUM | N | ... |
| LOW | N | ... |

Overall verdict: **PASS** / **CONDITIONAL PASS** / **FAIL**

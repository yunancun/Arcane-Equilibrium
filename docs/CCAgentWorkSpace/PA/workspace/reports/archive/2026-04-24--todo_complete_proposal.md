# PA 完整 TODO 提案 — 2026-04-24 十份歷史報告盤點

**PA（Project Architect）簽署**  
**日期**：2026-04-24  
**來源**：10 份歷史 PA 審計報告 + 當前 TODO.md（328 行）+ FIX-PLAN（27 KB）  
**目標**：列出所有等級（High / Mid / Low / Etc）中 1 條都不能落下的 TODO 提案  
**狀態**：提案階段（後續另輪任務做整合核實）

---

## A. PA 10 份歷史報告盤點

### 報告概覽表

| 序 | 日期 | 文件名 | 主題 | 架構 findings | 仍活躍條目 |
|---|------|--------|------|-------------|---------|
| 1 | 2026-03-31 | `2026-03-31--pa_review.md` | 技術審查（E3/CC/E4/E5/A3） | 5 CRITICAL/HIGH 驗證、6 遺漏、4 可行方案、架構債分類 | 4 項（DI 統一、GovernanceHub 缺 startup check、_get_auth_actor 語義陷阱、PipelineBridge 依賴注入時間窗口） |
| 2 | 2026-03-31 | `2026-03-31--wave5_architecture_review.md` | Wave 5 完成後評估 | 雙執行路徑並存（Path A/B）、Principle 3 部分失效、TD-1~5 清單 | 5 項技術債（pipeline_bridge acquire_lease、StrategistAgent 雙路徑、cost_tracker except、_h1_cooldown 無上限、_ollama_stats 懶初始） |
| 3 | 2026-04-01 | `2026-04-01--pa_technical_review.md` | 8 Agent 審計複驗 | P0/P1/HIGH 二次驗證、False Positive 識別、升降級決策、修復優先級、系統整體風險評估 | 11 項（TruthSourceRegistry 未注入、save/load 缺失、BacktestEngine 無數據、MessageBus 路徑斷裂、detail=str(e) 信息洩露等） |
| 4 | 2026-04-01 | `2026-04-01--reality_check_audit_verification.md` | 實況驗證 69 項未完成 | 代碼級實況 + 去重分類（確認存在 29、部分修復 10、誤報 10、已修復 20） | 29 項確認存在待處理 |
| 5 | 2026-04-02 | `2026-04-02--adaptive_params_technical_design.md` | 自適應參數系統設計 | 架構決策（配置擴展 vs 新模塊）、數據流設計（ATR/Regime/Cost）、代碼變更清單、副作用分析、risk_manager 拆分需求 | 3 項（cost_gate.py 新建、risk_manager 拆分前置、trading_engine._get_slippage 改 public） |
| 6 | 2026-04-03 | `2026-04-03--cross_platform_audit_scan.md` | 跨平台相容性審計（→ macOS 遷移） | 146+ 硬編碼路徑、Ollama/LLM 依賴、systemd→launchd、路徑改法方案 | 79 處必改、12 需驗證（遷移前置） |
| 7 | 2026-04-03 | `2026-04-03--improvement_report_vs_existing_code_mapping.md` | V3 改善報告映射 vs 現有代碼 | 25 個模塊/功能：2 已有、16 需擴展、5 全新、2 衝突 | 23.5 工作日實現需求、4 層數據流差異、3 項架構衝突 |
| 8 | 2026-04-24 | `2026-04-24--4.24TodoAudit.md` | 當前 TODO 完整審計 | 10 主題（架構完整性/Path A/B/Leverage/架構債/依賴圖/TODO 重組/技術建議/CLAUDE 一致性/風險熱點） | 詳見 FIX-PLAN（45 findings） |
| 9 | 2026-04-24 | `2026-04-24--4.24TodoAudit_FixPlan.md` | FIX-PLAN 整合 + 工作分組 | 45 findings 去重、6 工作組（G1-G6）、4 wave 並行策略、Live 日期重估 | 詳見下節 B |
| 10 | 當前 | `TODO.md`（328 行） | 當週工作列表 + 路線圖 | 4 wave 結構、P0/P1/P2/P3/P4 分層、G1-G6 橫軸、LG 關鍵路徑 | 所有當週活躍項整合於此 |

---

## B. 未入當前 TODO 的 PA 活躍項（最關鍵產出）

### 來自 PA 歷史 8 份報告的潛在遺漏（去重後）

| # | 來源報告 | PA 發現描述 | 架構級？ | 建議 ID | 等級 | 狀態 |
|---|---------|-----------|--------|--------|------|------|
| 1 | #1 (pa_review) | DI（Dependency Injection）模式不統一：governance_routes 的 `_get_auth_actor()` 模式 vs main_legacy 的 `Depends(current_actor)` | 架構級 | DI-UNIFY-01 | Mid | 已列 P2 (TBD) |
| 2 | #1 | GovernanceHub/RiskManager/StrategistAgent 三層防線均為可選注入，缺啟動時完整性驗證 | 架構級 | STARTUP-VERIFY-01 | High | 未列 |
| 3 | #1 | `_get_auth_actor()` + `Depends` 語義陷阱（actor 誤以為 dict，實為 AuthenticatedActor dataclass） | 架構級 | AUTH-SEMANTIC-TRAP-01 | High | 已列為 E3-CRITICAL-2 修復 |
| 4 | #1 | PipelineBridge 依賴注入時間窗口風險（模塊級註入 vs tick 開始） | 架構級 | PIPELINE-TIMING-WINDOW-01 | Mid | 未列 |
| 5 | #2 (wave5_review) | TD-1：pipeline_bridge 直接路徑缺 acquire_lease → Principle 3 雙重標準 | 架構級 | TD-01-LEASE-PATH-01 | High | 已列 G1-03? (Need verify) |
| 6 | #2 | TD-2：StrategistAgent intents 雙路徑語義模糊（collect vs bus.send） | 架構級 | TD-02-COLLECT-RETIRE-01 | Mid | 待 PA 評估是否入 Wave 2 |
| 7 | #3 (tech_review) | P0-FA-1 retro：TruthSourceRegistry 從未注入 → Phase 2 知識閉環死代碼 | 功能級 | TRUTH-REGISTRY-INJECT-01 | High | 已列 (0.5h 修復) |
| 8 | #3 | P1-FA-6 & AI-E P1-AI-1 merged：Registry save_snapshot 從未自動調用 | 功能級 | TRUTH-REGISTRY-PERSIST-01 | High | 已列 (1h 修復) |
| 9 | #3 | BacktestEngine API 無數據源（KlineManager 未注入） | 功能級 | BACKTEST-DATA-SOURCE-01 | P1 | 已列 (1h 修復) |
| 10 | #3 | MessageBus Guardian→Executor APPROVED_INTENT 路徑斷裂（Conductor 有邏輯但未被調用） | 功能級 | MSGBUS-APPROVED-PATH-01 | P1 | 已列 (2h 修復) |
| 11 | #3 | detail=str(e) 信息洩露（6 處） | 安全級 | DETAIL-STR-SANITIZE-01 | Mid | 已列 (0.5h 修復) |
| 12 | #4 (reality_check) | 29 項確認存在的代碼級問題已分散入 FIX-PLAN 各工作組，無新增遺漏 | — | — | — | ✅ |
| 13 | #5 (adaptive_params) | cost_gate.py 新建 (~150 行，pure fn） | 功能級 | COST-GATE-NEW-01 | Mid | 待 PM 決策何時納入 |
| 14 | #5 | risk_manager.py 需先拆分（超 1200 硬上限）才能新增 70 行功能 | 架構級 | RISK-MANAGER-SPLIT-01 | High | 待 Wave 3-4 排期 |
| 15 | #6 (cross_platform) | 79 處硬編碼路徑必改（歷史遺留模塊） | 可讀性 | PATH-HARDCODE-FIX-01 | Low | 非 Live 路徑，延後 P3/P4 |
| 16 | #7 (improvement_mapping) | 25 個模塊/功能映射，實際需 23.5d（報告估 36d） | 功能級 | V3-IMPROVE-INTEGRATION-01 | P3 | 長期計畫，不阻 Live |
| 17 | #7 | 4 層數據流差異風險（PositionSizer 注入點 / EWMAVol 更新 / Hurst 觸發 / HealthMonitor） | 架構級 | V3-DATA-FLOW-DIFF-01 | P2 | 設計層澄清待 PA + PM |
| 18 | #8 (TodoAudit) | 45 findings 已全部入 FIX-PLAN，無遺漏 | — | — | — | ✅ |

**結論**：PA 歷史 8 份報告發現的活躍項中，**大多已入當前 TODO.md**，新增遺漏項 **~5-8 條**（主要來自 #1 DI 統一、startup verify、PA 風險評估項）。

---

## C. PA 完整 TODO 提案表（~50-80 條 items）

### 分類清單（按阻塞性 + 架構/功能級劃分）

#### High 級（架構阻塞 + 安全 + 合規）：19 項

| ID | 內容 | 來源 | 工時 | 前置 | 並行 |
|----|------|------|------|------|------|
| **H-01** | G1-01: edge_estimator_scheduler 診斷 + 恢復（4d 停滯） | MIT audit | 2h | 無 | ✅ |
| **H-02** | G1-02: event_consumer/mod.rs fn 拆分（1696 行單 fn） | E5 audit | 3-4d | 無 | ✅ |
| **H-03** | G1-03: Rust 硬違反 8 檔 refactor（事件驅動） | E5 audit | 2-3d | H-02 | 部分並行 |
| **H-04** | G1-05: PostOnly 配置反向 bug（demo=false, live=true） | FA audit | 0.5d | 無 | ✅ |
| **H-05** | G3-01/02/03: ExecutorAgent ConfigStore + IPC + e2e 整合 | PA/CC audit | 4-5d | H-02 | ✅ 3-way |
| **H-06** | G3-05: FUP-SHADOW-ENABLED-IPC（shadow_enabled 熱重載） | PA audit | 1d | 無 | ✅ |
| **H-07** | G5-01~03: main.rs / live_session_routes / instrument_info 拆分 | E5 audit | 4-5d | H-02 | ✅ 並行 |
| **H-08** | STARTUP-VERIFY-01: 啟動時依賴完整性驗證（fail-closed） | PA #1 | 0.5d | 無 | ✅ |
| **H-09** | TRUTH-REGISTRY-INJECT-01: TruthSourceRegistry 注入 Agents | FA audit | 0.5h | 無 | ✅ |
| **H-10** | TRUTH-REGISTRY-PERSIST-01: Registry save_snapshot 自動調用 | FA/AI-E audit | 1h | H-09 | — |
| **H-11** | P1-7 C labels 加速至 200 pooled（G4-01） | MIT audit | 1-2d | G1-01 done | ✅ |
| **H-12** | MSGBUS-APPROVED-PATH-01: Guardian→Executor APPROVED_INTENT | FA audit | 2h | 無 | ✅ |
| **H-13** | BACKTEST-DATA-SOURCE-01: BacktestEngine KlineManager 注入 | FA audit | 1h | 無 | ✅ |
| **H-14** | P1-10 PostOnly 1-2w 驗證（被動觀察） | QC audit | passive 1-2w | 無 | ✅ |
| **H-15** | FIX-26-DEADLOCK-1 `--rebuild` 部署驗證（bb_breakout） | QA audit | 6h+ | 無 | ✅ |
| **H-16** | RISK-MANAGER-SPLIT-01: risk_manager.py 拆分（前置功能新增） | PA #5 | 2-3d | 無 | ✅ |
| **H-17** | AUTH-SEMANTIC-TRAP-01: _get_auth_actor 語義統一 | PA #1 | 2h | 無 | ✅ |
| **H-18** | CRITICAL-G06: drawdown ≥15% auto-revoke 實裝 | CC audit | 1d | 無 | ✅ |
| **H-19** | G2-02~03: ma_crossover R:R counterfactual + 策略調優 | QC audit | 2-3d | H-14 done | 部分並行 |

#### Mid 級（技術債 + 可讀性 + 部分合規）：28 項

| ID | 內容 | 來源 | 工時 | 前置 | 備註 |
|----|------|------|------|------|------|
| **M-01** | G1-04: fee drag / R:R 邊際驗證 | QC audit | 8h | 無 | 獨立軌道 |
| **M-02** | G4-02~03: model_registry canary 規則 + run_training 首跑 | MIT audit | 2d | H-11 done | 待 labels ≥200 |
| **M-03** | G4-04: model_registry healthcheck [13] 補全 | MIT audit | 0.5d | 無 | 文檔層 |
| **M-04** | G4-05: ExitConfig.shadow_enabled flip ON + 24h 觀察 | PA audit | passive 24h | H-06 | 健檢驅動 |
| **M-05** | G5-02~06: ai_service / bb_reversion / 其餘 5 檔拆分 | E5 audit | 4-5d | H-02 | 與 H-07 並行 |
| **M-06** | TD-02-COLLECT-RETIRE-01: StrategistAgent collect 路徑廢棄 | PA #2 | 2-3d | H-02+H-05 | 設計債 |
| **M-07** | DI-UNIFY-01: governance_routes DI 模式統一 | PA #1 | 2h | 無 | 代碼品質 |
| **M-08** | COST-GATE-NEW-01: cost_gate.py 實裝 (~150 行) | PA #5 | 1d | H-16 done | 待 PM 決策時機 |
| **M-09** | PIPELINE-TIMING-WINDOW-01: 依賴注入時間窗口防衛 | PA #1 | 0.5d | 無 | 啟動邏輯優化 |
| **M-10** | DETAIL-STR-SANITIZE-01: 6 處 detail=str(e) 修正 | E3 audit | 0.5h | 無 | 安全加固 |
| **M-11** | G6-01: passive_wait_healthcheck.py 補齊 5 缺陷 | QA audit | 1-2d | 無 | 觀察性 |
| **M-12** | G6-02: 被動等待 TODO 全覆蓋 healthcheck（CLAUDE.md §七） | QA audit | 1d | M-11 | 規範化 |
| **M-13** | P1-14 EDGE-ESTIMATE-BIND: cost_gate 實際綁定（grand_mean > -50） | PA audit | 2-3h | M-08 | 待 scheduler 恢復後重跑 |
| **M-14** | EDGE-DIAG-1 Phase 3 auto-gate（clean n≥200）監控 | QA audit | passive | 無 | healthcheck [11] 驅動 |
| **M-15** | H3 ModelRouter 獨立模塊化（當前分散） | PA/FA audit | 2-3d | H-05 done | 架構改進 |
| **M-16** | L2 cost_tracker ↔ APIBudgetManager 合併（新増月度預算） | PA #7 | 1.5d | 無 | 需求明確 |
| **M-17** | LocalLLMClient ABC + LM Studio 適配 | PA #7 | 1d | 無 | 跨 LLM 抽象 |
| **M-18** | STRATEGIST-PROMOTE-TRIGGER-01: 手動 API + IPC | PA audit | 1d | H-05 done | 可選性 |
| **M-19** | P1-7 B 邊際標籤標準（shrinkage 量化） | MIT audit | 1-2d | H-11 done | 質量控制 |
| **M-20** | V023 Guard A retrofit 計畫（migration 規範新增） | PA audit | 文檔 2h | 無 | 長期 |
| **M-21** | CLAUDE.md §三 敘述同步規則（Lessons 系統） | TW audit | 0.5d | 無 | 流程化 |
| **M-22** | PnLAttributor vs TradeAttributionEngine 決策（建議用現有） | PA #7 | 3h 評估 | 無 | 跳過簡版 |
| **M-23** | G3-06: Layer 2 autonomous 升級觸發規則 | AI-E audit | 2-3d | H-05 done | AI 決策化 |
| **M-24** | G3-07: Layer 2 工具箱補全（query_onchain 等） | PA audit | 2-3d | M-23 | 工具集擴展 |
| **M-25** | G3-08: H1-H5 → Rust IPC Gateway | PA audit | 3-5d | H-05 done | 架構升級 |
| **M-26** | G3-09: cost_edge_ratio 原則 #13 演算法實裝 | AI-E audit | 2d | M-25 | 治理量化 |
| **M-27** | RISK-MANAGER.py claims/hypotheses 無上限清理（LRU） | PA #3 | 1-2d | 無 | 長期安全 |
| **M-28** | EDGE-P2-2 Phase B Liquidation signal | QC audit | 2d | 無 | P3 項，非阻 Live |

#### Low 級（可讀性 + 文檔 + QoL）：15 項

| ID | 內容 | 來源 | 工時 | 優先級 |
|----|------|------|------|--------|
| **L-01** | PATH-HARDCODE-FIX-01: 79 處硬編碼路徑改環境變量 | PA #6 | 2-3d | P3/P4（非 Live 路徑） |
| **L-02** | sql/migrations V001-V020 Guard A retrofit 計劃 | PA audit | 文檔 2h | P4 |
| **L-03** | bb_reversion.rs 1143 行拆 sibling | E5 audit | 1h | P3 |
| **L-04** | indicator_engine 擴展（ADX/KAMA/Donchian） | PA #7 | 3-4d | P3（策略 V2 前置） |
| **L-05** | PositionSizer Kelly fraction + risk parity | PA #7 | 0.5d | P3 |
| **L-06** | StrategyHealthMonitor CUSUM 擴展 | PA #7 | 0.5d | P3 |
| **L-07** | EWMAVolEstimator 新建 | PA #7 | 0.5d | P3 |
| **L-08** | Hurst Exponent 新建 | PA #7 | 0.5d | P3 |
| **L-09** | ContextDistiller 新建（L2 prompt 壓縮） | PA #7 | 1d | P3 |
| **L-10** | Regime Detection + Hurst 整合 | PA #7 | 1.5d | P3 |
| **L-11** | 5 策略 V2 升級（MA/BB/Funding/Grid/BB-rev） | PA #7 | 8d | P3/P4 |
| **L-12** | P1-7 B edge_estimator sample floor（決策待） | MIT audit | TBD | P3 |
| **L-13** | QoL-2 Demo AI cost 追蹤（依 M-25） | PA audit | 1d | P3 |
| **L-14** | Symbol Embedding / Regime LSTM（Phase 5 補強） | PA audit | 2-3w | P4 |
| **L-15** | Conductor 完整實裝 + G-1 stub 補全 | PA audit | 3-5d | P4（非阻 Live） |

#### Etc 級（文檔 / RFC / 規範 / 監控）：10 項

| ID | 內容 | 來源 | 工時 | 備註 |
|----|------|------|------|------|
| **E-01** | G6-03: V019/V020 Guard A retrofit 計畫書 | PA audit | 文檔 2h | compliance spec |
| **E-02** | G6-04: CLAUDE.md §三敘述同步規則 | TW audit | 0.5d | governance |
| **E-03** | P1-2 LG-1 21d demo healthcheck 補全（[0.5] + [0.6]） | PA audit | 6h | healthcheck framework |
| **E-04** | [2a]/[4a]/[11a] healthcheck 補齊 | QA audit | 3×30m | monitoring |
| **E-05** | Layer2_types.DEFAULT_DAILY_HARD_CAP 15.0→2.0 | CC audit | 15m | config fix |
| **E-06** | 當下週新 RFC：FUP-SHADOW-ENABLED-IPC（IPC 7 欄位） | PA audit | 文檔 1h | architecture RFC |
| **E-07** | Risk Governor 四級分層文檔（DEFENSIVE/CIRCUIT_BREAKER） | PA #7 評估 | 文檔 2h | design decision |
| **E-08** | STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1 文檔（信息流量化） | PA audit | 文檔 1h | observability spec |
| **E-09** | Model canary promotion Operator 審批流程 playbook | MIT audit | 文檔 2h | runbook |
| **E-10** | P0-2 LG-1 被動等待規則宣導（CLAUDE.md §七新規則） | CC audit | 文檔 1h | policy |

---

## D. 架構債分類清單（PA 視角）

### 架構債（需 RFC + 設計）：7 項

1. **Path A/B 互斥設計鬆散**（TD-01）
   - 描述：pipeline_bridge 直接路徑 vs ExecutorAgent 路徑，兩條都活
   - 修復：Path B 廢棄 + TRUTH-REGISTRY-INJECT-01 補全
   - 工時：2-3d
   - 影響：Principle 3 完整性

2. **DI（Dependency Injection）模式不統一**（DI-UNIFY-01）
   - 描述：governance_routes 與 main_legacy DI 模式差異
   - 修復：統一為 `Depends(current_actor)` 模式
   - 工時：2h
   - 影響：可維護性、新增端點誤報率

3. **ExecutorAgent shadow→live 決策鏈缺 GUI**（H-05/M-18）
   - 描述：`_shadow_mode=True` 硬編碼，無 web 切換路徑
   - 修復：ConfigStore + IPC + GUI toggle
   - 工時：4-5d
   - 影響：原則 #11（自主權進化）

4. **risk_manager.py 超 1200 行（拆分前置）**（H-16）
   - 描述：1633 行，無法再新增功能
   - 修復：拆 price_tracker / stop_computation / risk_configs 三模塊
   - 工時：2-3d
   - 影響：後續功能新增能力

5. **MessageBus Guardian→Executor 路徑斷裂**（H-12）
   - 描述：Conductor 有邏輯但未被調用
   - 修復：pipeline_bridge 呼叫 Conductor.process_trade_intent
   - 工時：2h
   - 影響：5-Agent 全連接

6. **Startup 依賴完整性驗證缺失**（H-08）
   - 描述：GovernanceHub/RiskManager/StrategistAgent 三層防線可選，無 fail-closed check
   - 修復：@app.on_event("startup") 斷言注入
   - 工時：0.5d
   - 影響：系統可靠性

7. **PipelineBridge 依賴注入時間窗口**（M-09）
   - 描述：模塊級註入 vs tick 開始，存在窗口期
   - 修復：activate() 前置依賴完整性檢查
   - 工時：0.5d
   - 影響：重啟恢復安全性

### 功能債（直接開工）：8 項

1. **TruthSourceRegistry 從未注入**（H-09）：0.5h
2. **Registry save_snapshot 缺自動調用**（H-10）：1h
3. **BacktestEngine KlineManager 未注入**（H-13）：1h
4. **MessageBus APPROVED_INTENT 路徑斷裂**（H-12）：2h
5. **detail=str(e) 信息洩露**（M-10）：0.5h
6. **FIX-26-DEADLOCK-1 bb_breakout squeeze 清除缺失**（H-15）：已修，待 rebuild
7. **PostOnly 配置反向**（H-04）：0.5d
8. **drawdown ≥15% auto-revoke 未實裝**（H-18）：1d

### 參數債（config flip 或 TOML 調整）：5 項

1. **edge_estimator_scheduler 停止狀態** → G1-01 診斷恢復（基礎設施）
2. **PostOnly demo=false, live=true 反向** → H-04 修正
3. **layer2_types.DEFAULT_DAILY_HARD_CAP 15.0→2.0** → E-05（config）
4. **ExitConfig.shadow_enabled false→true** → M-04（IPC flip）
5. **FUP-SHADOW-ENABLED-IPC exit.* 7 欄位** → H-06（IPC 熱重載）

### 文檔債（spec/README/CLAUDE.md 同步）：6 項

1. **CLAUDE.md §三敘述同步規則**（M-21）：0.5d
2. **V023 Guard A retrofit 計畫書**（E-01）：2h
3. **P1-2 LG-1 healthcheck 規範**（E-03）：6h
4. **Layer2 autonomous 觸發規則 spec**（E-06）：1h
5. **Model canary promotion playbook**（E-09）：2h
6. **被動等待 TODO 新規則宣導**（E-10）：1h

---

## E. Leverage Points（強化版、至少 5）

基於 PA 2026-04-24 audit 發現 + 歷史報告關鍵 findings

| # | Leverage | 工作量 | ROI | 優先級 | 實施組 |
|---|----------|--------|-----|--------|--------|
| **1** | **FUP-SHADOW-ENABLED-IPC**（exit.* 7 欄位熱重載） | 1d | Phase 2 無需 rebuild（~3min→<60s） | P2 | E1+E2 |
| **2** | **ExecutorAgent ConfigStore + IPC toggle** | 3-4d | Path A→Live 過渡敏捷 + 原則 #11 完整 | **P1** | E1+PA+E2 |
| **3** | **Combine shadow 監控自動化**（healthcheck [8] 加強） | 2d | Track L Phase 1b 前置、P vs L 一致性量化 | P2 | E1+QA |
| **4** | **edge_estimator_scheduler 恢復**（診斷+FUP） | 2h diagnostic | edge_estimates.json 從 1→135+ cells（4d 停滯根因） | **P0** | MIT+E4 |
| **5** | **TRUTH-REGISTRY-INJECT-01**（0.5h 激活） | 0.5h | Phase 2 知識閉環即時有生命（無此系統死） | **P0** | E1 |
| **6** | **event_consumer fn 拆分**（P0 gate） | 3-4d | Rust 硬違反 8 檔 + 後續 refactor 解阻 | **P0** | E1+PA+E5 |
| **7** | **Layer 2 工具箱 + H1-H5 Rust gateway**（M-25/24） | 5-7d | AI 獨立推理、本地 judge + 工具調度 | P2 | E1+AI-E+PA |

---

## F. 關鍵決策點（需 PM/operator 判決）

| 決策 | 涉及 TODO | 現狀 | 影響 | 建議 |
|------|----------|------|------|------|
| **Grid trading disable？** | G2-04 | fee drag 60-70%，PostOnly 待驗 | 若手續費不降，策略無邊際 | 待 P1-10 1-2w 驗證決策（被動） |
| **cost_gate.py 何時納入？** | M-08 | 已設計，待 PM 排期 | 影響 entry frequency | 建議 Wave 2（G3 完成後） |
| **DUAL-TRACK Phase 1b 資料驅動何時啟動？** | H-11/H-14 | labels 47/200，ETA 3-5d | 影響 Track L 灰度日期 | 待 labels 自然累積達 200（被動） |
| **P0-3 Phase 5 edge 重評日期？** | P0-3 | 待 P0-2 解鎖（2026-05-07） | 決定 Phase 5 / DUAL-TRACK 重做方向 | 3d 內決策（事件驅動） |
| **Path B 廢棄時機？** | M-06 | TruthRegistry 注入後可行 | 影響 StrategistAgent 簡化度 | 待 H-05 + H-09 完成（Wave 2） |

---

## G. 與當前 TODO.md 對比確認

### 當前 TODO.md 已涵蓋項：✅

- ✅ Wave 1-4 路線圖結構（G1-G6 工作組）
- ✅ P0（P0-2/P0-3）+ P1（EDGE-DIAG / DUAL-TRACK / P1-6~14）主軸
- ✅ P2/P3/P4 分層 + Gap 索引
- ✅ healthcheck 框架 + 被動等待規則

### PA 新增提案項（未在當前 TODO 明確列出或需強調）：🆕

| 項目 | 當前 TODO 狀態 | PA 補充強調 | 優先級 |
|------|-------------|-----------|--------|
| DI-UNIFY-01 | 未列 | governance_routes 改 `Depends(current_actor)` | H（Mid） |
| STARTUP-VERIFY-01 | 未列 | 依賴完整性 fail-closed check | H（High） |
| AUTH-SEMANTIC-TRAP-01 | 列為 E3-CRITICAL-2（待驗） | 確認類型檢查修正 | H（High） |
| PIPELINE-TIMING-WINDOW-01 | 未列 | PipelineBridge activate() 前置檢查 | M（Mid） |
| M-07 DI-UNIFY | 未列 | governance 層 DI 統一 | M（Mid） |
| M-13 EDGE-ESTIMATE-BIND | 簡略列為 P1-14 | 需 cost_gate 實裝 + scheduler 恢復 | M（Mid） |
| E-01~10 文檔 RFC | 分散列為 P2/文檔類 | 明確 RFC 清單 + 優先級 | E（Etc） |

---

## H. 參考索引（PA 報告檔案路徑）

| 歷史報告 | 路徑 | 關鍵章節 |
|---------|------|---------|
| pa_review | `/docs/CCAgentWorkSpace/PA/workspace/reports/2026-03-31--pa_review.md` | §4 DI 問題 / §4.5 私有屬性 / §5 修復優先級 |
| wave5_review | `/docs/CCAgentWorkSpace/PA/workspace/reports/2026-03-31--wave5_architecture_review.md` | §2 雙執行路徑 / §3 技術債清單 |
| tech_review | `/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-01--pa_technical_review.md` | §2~7 P0/P1/HIGH 驗證 / §8 修復順序建議 |
| reality_check | `/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-01--reality_check_audit_verification.md` | §3 逐項驗證 69 findings |
| adaptive_params | `/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-02--adaptive_params_technical_design.md` | §B cost_gate 設計 / risk_manager 拆分需求 |
| cross_platform | `/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-03--cross_platform_audit_scan.md` | §XP-1 硬編碼路徑改法 |
| improvement | `/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-03--improvement_report_vs_existing_code_mapping.md` | §4 數據流差異 / §5 Phase 優先級重排 |
| TodoAudit | `/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit.md` | §十 PA 最終判決 + 3 Leverage |
| FixPlan | `/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md` | §3 G1-G6 工作組 / §4 並行執行 / §5 Live 日期重估 |

---

## I. Memory 更新指引

**後續 session 應更新**：
- `docs/CCAgentWorkSpace/PA/memory.md` §四新增：「2026-04-24 TODO 提案完成」+ 新發現的 5-8 個潛在遺漏項
- 在 lessons.md 記錄：「10 份歷史報告盤點流程」+ 「PA 跨會話架構知識累積」

---

## PA 最終結論

**完整提案項數**：~80 條 TODO items（High 19 + Mid 28 + Low 15 + Etc 10 + Backlog ~8）

**未入當前 TODO 的關鍵遺漏**：
1. DI-UNIFY-01（governance 層 DI 統一）
2. STARTUP-VERIFY-01（依賴完整性 fail-closed）
3. AUTH-SEMANTIC-TRAP-01（確認類型修正）
4. PIPELINE-TIMING-WINDOW-01（注入時間窗口防衛）
5. 5 個 RFC + 文檔 spec（E-01~10）

**最高 ROI 修復**（3 大 Leverage 點）：
1. FUP-SHADOW-ENABLED-IPC（1d → Phase 2 無 rebuild）
2. ExecutorAgent ConfigStore（3-4d → 原則 #11 完整）
3. event_consumer fn 拆分（3-4d → 8 檔 refactor 解阻）

**Live 可達性**：
- 當前提案覆蓋完整，無架構阻塞
- 3 個 CRITICAL blocker（G05/G06/canary promotion）需清除
- 最早 Live 日期 **~2026-05-23**（事件驅動，非 hard date）

---

**PA 簽署**：2026-04-24  
**狀態**：提案交付 PM 確認 + 後續整合核實  
**下次更新**：W24 Live 決策後

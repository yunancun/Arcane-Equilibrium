# PA 統一整改計劃 — 12 份審計報告合併分析
# PA Consolidated Remediation Plan — 12 Audit Reports Cross-Reference

**角色：** PA (Project Architect)
**日期：** 2026-04-05
**輸入：** FA / AI-E / E5 / E4 / E3 / CC / QC / MIT / BB / TW / R4 / A3 共 12 份審計報告
**方法：** 交叉比對 → 去重 → 源碼驗證 → 優先級排序 → 分組打包 → 排程

---

## 一、主問題追蹤表（Master Issue Tracker）

### P0 — 阻塞級（必須在 Exchange 模式啟用前或下一 Sprint 內修復）

| ID | 問題 | 嚴重性 | 來源報告 | 驗證狀態 | 工作包 |
|----|------|--------|---------|---------|--------|
| **I-01** | `process_gates_only()` 缺少 Cost Gate (Gate 3) | P0 | FA-GAP1, E3-SEC01, CC-§10 | **已確認** — L396 後直接返回，無 Gate 3 | WP-A |
| **I-02** | IPC Unix Socket 無認證/授權 | P0 | E3-SEC08 | **已確認** — ipc_server.rs 接受所有連接 | WP-B |
| **I-03** | stress_integration.rs 編譯失敗（29 個極端場景測試不可用） | P0 | E4-P0-1 | **已確認** — process() 簽名 3→4 參數未同步 | WP-C |
| **I-04** | test_grafana_data_writer 20 個測試失敗 | P0 | E4-P0-2 | **待驗證** — 需確認是接口變更還是邏輯錯誤 | WP-C |
| **I-05** | test_label_generator 2 個測試失敗 | P0 | E4-P0-3 | **待驗證** — ML 標籤管線基礎 | WP-C |
| **I-06** | `market_data_client.rs` 1422 行超 1200 硬上限 | P0 | E5-§1, CC-§4.2 | **已確認** — wc -l = 1422 | WP-D |
| **I-07** | DDL V001-V007 未執行 — 所有 DB 寫入器空轉 | P0 | MIT-§1, MIT-§2 | **已確認** — DDL 標記 "not yet executed" | WP-E |

### P1 — 重要級（本週或下一 Sprint 修復）

| ID | 問題 | 嚴重性 | 來源報告 | 驗證狀態 | 工作包 |
|----|------|--------|---------|---------|--------|
| **I-08** | StopRequest channel 未接入 `set_trading_stop` — 雙軌止損名存實亡 | P1 | CC-§10 | **已確認** — event_consumer.rs:215 僅記錄日誌 | WP-A |
| **I-09** | IPC 風控參數無邊界驗證（`.clamp()`） | P1 | E3-SEC18 | **已確認** — 除 p1_risk_pct 外均無 clamp | WP-B |
| **I-10** | Cookie `secure=False` | P1 | E3-SEC21 | **已確認** — legacy_routes.py L382 TODO 標記 | WP-B |
| **I-11** | GUI innerHTML 潛在 XSS | P1 | E3-SEC05 | **已確認** — 多處 innerHTML 使用 | WP-F |
| **I-12** | GUI 輸入框被 15 秒自動刷新覆蓋 | P1 | A3-AH06 | **已確認** — loadRiskConfig() 每 15s 覆寫 input | WP-F |
| **I-13** | AI 建議 Apply 按鈕雙重 display:none 永不可見 | P1 | A3-D05 | **已確認** — 父 div + 按鈕雙重 hidden | WP-F |
| **I-14** | Delete 策略/Danger Zone 操作無確認彈窗 | P1 | A3-D09, A3-UX01, A3-UX02 | **已確認** | WP-F |
| **I-15** | Feed/Demo/Scanner 快捷按鈕無功能但看似可操作 | P1 | A3-D02/D03/D04, A3-AH04 | **已確認** — 只彈 toast | WP-F |
| **I-16** | Provider Key 保存靜默失敗 + runEvolution 調用方式錯誤 | P1 | A3-D10, A3-D11 | **已確認** | WP-F |
| **I-17** | 5 個高風險硬編碼值應配置化 | P1 | QC-HC-S1/S2/S3/CG1/CG2 | **已確認** — 止損和成本門檻核心參數 | WP-G |
| **I-18** | Regime 乘數（12 個值）硬編碼在 match 語句 | P1 | QC-§13.5, FA-GAP2 | **已確認** — risk/config.rs:100-128 | WP-G |
| **I-19** | Scorer 未接入 tick_pipeline | P1 | FA-GAP5, AI-E-§3.2, MIT-§5 | **已確認** — tick_pipeline.rs 無 scorer 引用 | WP-H |
| **I-20** | `record_trade()` 未被調用 → Kelly 無真實數據 | P1 | FA-GAP6, AI-E-§3.1 | **已確認** | WP-H |
| **I-21** | PositionSnapshot DB 消息從未發射 | P1 | FA-GAP7, MIT-§2 | **已確認** — tick_pipeline 無發射代碼 | WP-H |
| **I-22** | event_consumer.rs 957 行零測試 | P1 | E4-§3.2 | **已確認** — 核心事件分發無驗證 | WP-C |
| **I-23** | ort crate 未整合 — ONNX 推理路徑不通 | P1 | AI-E-§4, MIT-§5, MIT-§6 | **已確認** — predict() 返回 None | WP-H |
| **I-24** | docs/README.md 索引停更（25 項遺漏） | P1 | TW-§4, R4-§1.1 | **已確認** — 04-02 後停更 | WP-I |
| **I-25** | helper_scripts/SCRIPT_INDEX.md 不存在 | P1 | R4-§5.1 | **已確認** | WP-I |
| **I-26** | 04-05 工作日誌未合併（6 碎片） | P1 | TW-§7.3 | **已確認** | WP-I |
| **I-27** | 5 個 Rust 編譯器警告 | P1 | E5-§2 | **已確認** — W1-W5 | WP-D |
| **I-28** | Python 5 檔超 1200 行硬上限 | P1 | E5-§1, CC-§4.2 | **已確認** — 多數標記 DEPRECATED | WP-D |

### P2 — 改善級（下一 Sprint 或 Phase 4）

| ID | 問題 | 嚴重性 | 來源報告 | 工作包 |
|----|------|--------|---------|--------|
| **I-29** | `correlated_exposure_pct` 硬編碼 0.0 | P2 | FA-GAP3, CC-§1-原則16, QC-§1.1 | WP-G |
| **I-30** | Kelly ATR% placeholder 0.02 | P2 | FA-GAP4, QC-HC-K1 | WP-G |
| **I-31** | cost_ratio + regime placeholder（0.0 / "ranging"） | P2 | FA-GAP2 | WP-G |
| **I-32** | Thompson Sampling 無 PG 持久化 → 重啟丟失 | P2 | MIT-§13 | WP-E |
| **I-33** | drift_detector 未接入 PG 數據讀取 | P2 | MIT-§10 | WP-E |
| **I-34** | 無端到端 ML 訓練腳本 | P2 | MIT-§4, AI-E-§5.3 | WP-H |
| **I-35** | scorer_trainer 使用簡單 80/20 split 而非 CPCV | P2 | MIT-§4 | WP-H |
| **I-36** | ETL ASOF JOIN 類型不匹配（BIGINT vs TIMESTAMPTZ） | P2 | MIT-§8 | WP-E |
| **I-37** | 缺少 requirements-ml.txt | P2 | MIT-§4 | WP-H |
| **I-38** | intent_processor gate 邏輯重複 ~120 行 | P2 | E5-F1 | WP-D |
| **I-39** | on_tick() 550 行過長 | P2 | E5-S1 | WP-D |
| **I-40** | exec_id 去重 O(n) 線性掃描 | P2 | E5-P1 | WP-D |
| **I-41** | 14 組完全重複文件（audit/ vs CCAgentWorkSpace/） | P2 | TW-§3.1 | WP-I |
| **I-42** | docs/audit/ vs docs/audits/ 命名混亂 | P2 | TW-§4.3, R4-§8.1 | WP-I |
| **I-43** | 18 個審計報告命名不符規範 | P2 | TW-§6.1 | WP-I |
| **I-44** | 8 個 .DS_Store 文件 | P2 | TW-§6.2 | WP-I |
| **I-45** | CLAUDE_CHANGELOG 遺漏 RRC-1 條目 | P2 | R4-§4.2 | WP-I |
| **I-46** | Optuna EV_net 手續費建模簡化（PnL-based vs notional-based） | P2 | QC-§9.1 | WP-G |
| **I-47** | ATR 命名誤導（Average Absolute Return 非 Wilder ATR） | P2 | QC-§5.1 | WP-G |
| **I-48** | 學習產出無明確審批門禁（原則 #7） | P2 | CC-§1-原則7 | WP-A |
| **I-49** | operator_risk_config.json 與 Rust 默認值差異大 | P2 | CC-附錄A | WP-G |
| **I-50** | 缺限流主動延遲機制 | P2 | BB-§8.3 | WP-J |
| **I-51** | Python GET 簽名未排序 query string | P2 | BB-§10.1 | WP-J |
| **I-52** | WS 僅配置 Linear URL，多品類需擴展 | P2 | BB-§7 | WP-J |
| **I-53** | 部分 TimescaleDB 表缺壓縮策略 | P2 | MIT-§9 | WP-E |

### P3 — 建議級（可延後）

| ID | 問題 | 來源報告 | 工作包 |
|----|------|---------|--------|
| **I-54** | IPC evaluate_strategy/get_risk_check 仍為 stub | FA-GAP8 | WP-A |
| **I-55** | 限價單模擬未實現 | FA-GAP9 | WP-A |
| **I-56** | provider pricing table 未實現 | FA-GAP10 | WP-A |
| **I-57** | latency_us u32 截斷 | E3-SEC13 | WP-D |
| **I-58** | API Token JSON body 明文返回 | E3-SEC06 | WP-B |
| **I-59** | GUI 舊版 index.html 殘留 | A3-D06/D07 | WP-F |
| **I-60** | GUI 術語不一致（Demo/Paper/測試/模擬多名） | A3-UX07/08/09 | WP-F |
| **I-61** | 特徵缺失值用 0.0 非 NaN | QC-§12 | WP-H |
| **I-62** | Legacy Python AI 子系統（~100 文件）未清理 | AI-E-§11.3 | WP-K |
| **I-63** | Decision Lease 在 Rust 快速路徑被繞過 | AI-E-§7.2, CC-§1-原則3 | WP-A |

---

## 二、交叉報告重疊分析（Cross-Report Overlap Matrix）

### 2.1 高頻重疊問題（3+ 報告同時指出）

| 問題主題 | FA | AI-E | E5 | E4 | E3 | CC | QC | MIT | BB | TW | R4 | A3 | 合計 |
|---------|----|----|----|----|----|----|----|----|----|----|----|----|------|
| Exchange 模式缺 Cost Gate (I-01) | **GAP1** | | | | **SEC01** | **§10** | | | | | | | **3** |
| Scorer 未接入 tick_pipeline (I-19) | **GAP5** | **§3.2** | | | | | | **§5** | | | | | **3** |
| ONNX/ort 未整合 (I-23) | | **§4** | | | | | | **§5,§6** | | | | | **3**（含 AI-E 多節）|
| 文件大小超限 (I-06/I-28) | | | **§1** | | | **§4.2** | | | | | | | **2** |
| correlated_exposure 硬編碼 0.0 (I-29) | **GAP3** | | | | | **§1-#16** | **§1.1** | | | | | | **3** |
| DDL 未執行 → 數據空轉 (I-07) | | | | | | | | **§1,§2** | | | | | **2**（MIT 多節）|
| record_trade 未調用 (I-20) | **GAP6** | **§3.1** | | | | | | | | | | | **2** |
| 硬編碼值需配置化 (I-17) | | | | | | | **§15** | | | | | | **1**（QC 專項）|
| docs/README 索引停更 (I-24) | | | | | | | | | | **§4** | **§1.1** | | **2** |
| PositionSnapshot 未發射 (I-21) | **GAP7** | | | | | | | **§2** | | | | | **2** |

### 2.2 單報告獨家發現（但重要）

| 問題 | 獨家報告 | 重要性 |
|------|---------|--------|
| IPC 無認證 (I-02) | E3 | P0 — 安全關鍵 |
| stress_integration 編譯壞 (I-03) | E4 | P0 — 29 個安全網測試不可用 |
| GUI 輸入框被覆蓋 (I-12) | A3 | P1 — 嚴重影響日常操作 |
| Thompson Sampling 無持久化 (I-32) | MIT | P2 — 重啟丟失後驗 |
| StopRequest 未接入 (I-08) | CC | P1 — 雙軌止損失效 |
| H0Gate shadow_mode IPC 繞過 (E3-SEC02) | E3 | 已知設計，加審計日誌即可 |

### 2.3 假陽性排查（False Positive Check）

| 報告發現 | 驗證結果 | 判定 |
|---------|---------|------|
| CC: tick_pipeline.rs 1209 行超 1200 | 含測試代碼；核心邏輯 ~900 行 | **邊界** — 標記為警告級而非硬違規 |
| CC: signal_generator.py 1452 行超限 | Python local_model_tools 模組，已非主路徑 | **已確認** 但為遺留代碼 |
| E5: funding_arb 整模組 dead_code | 明確標記等待 R-06，保留合理 | **非問題** — 設計意圖 |
| A3: D-08 trading.html 獨立架構 | iframe 嵌入設計，認證由 cookie 統一 | **低風險** — P2 改善 |
| BB: Python GET 未排序 query string | Bybit 對順序容忍度高，目前無問題 | **已確認但低風險** |

---

## 三、工作包定義（Work Packages）

### WP-A：Exchange 模式就緒 + 風控完善（預估 2 天）

**包含問題：** I-01, I-08, I-48, I-54, I-55, I-63

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| `process_gates_only()` 添加 Gate 3 Cost Gate | P0 | 1h | intent_processor.rs |
| StopRequest channel 接入 `set_trading_stop()` | P1 | 2h | event_consumer.rs, position_manager.rs |
| `UpdateStrategyParams` 增加 GovernanceCore 授權檢查（exchange 模式） | P2 | 1h | event_consumer.rs |
| 提取 gate 共享邏輯消除 process/process_gates_only 重複 | P2 | 1h | intent_processor.rs |

**依賴：** 無
**E2+E4 審查：** 強制

---

### WP-B：安全加固（預估 1.5 天）

**包含問題：** I-02, I-09, I-10, I-58

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| IPC socket 設置 0o600 權限 | P0 | 30min | main.rs / ipc_server.rs |
| IPC 風控 setter 加入 `.clamp()` 邊界 | P1 | 1h | event_consumer.rs |
| H0Gate shadow_mode 切換加入審計日誌 | P1 | 30min | h0_gate.rs |
| secure cookie 配置項（根據環境自動切換） | P1 | 30min | legacy_routes.py |
| 登入 JSON body 不返回 token（改用 cookie-only） | P3 | 15min | legacy_routes.py |

**依賴：** 無
**E3+E4 審查：** 強制

---

### WP-C：測試修復與覆蓋補充（預估 1.5 天）

**包含問題：** I-03, I-04, I-05, I-22

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| 修復 stress_integration.rs process() 4 參數 | P0 | 15min | tests/stress_integration.rs |
| 修復 test_grafana_data_writer 20 個回歸 | P0 | 30min | tests/test_grafana_data_writer.py |
| 修復 test_label_generator 2 個回歸 | P0 | 15min | ml_training/tests/test_label_generator.py |
| 為 event_consumer.rs 補充 +15 個測試 | P1 | 3h | 新建 tests/test_event_consumer.rs |
| 為 strategies/mod.rs 補充 +5 個測試 | P2 | 1h | tests/ |

**依賴：** WP-A（若修改了 process 簽名）
**E4 自驗：** 強制

---

### WP-D：代碼品質與合規（預估 2 天）

**包含問題：** I-06, I-27, I-28, I-38, I-39, I-40, I-57

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| market_data_client.rs 拆分為 + market_data_types.rs | P0 | 1h | market_data_client.rs |
| 修復 5 個 Rust 編譯器警告（W1-W5） | P1 | 15min | 多文件 |
| tick_pipeline ring buffer 提取 `push_ring` helper | P2 | 30min | tick_pipeline.rs |
| tick_pipeline ID 生成函數提取 | P2 | 30min | tick_pipeline.rs |
| on_tick() 拆分為 5 個私有方法 | P2 | 2h | tick_pipeline.rs |
| exec_id 去重改用 HashSet + VecDeque 雙容器 | P2 | 30min | event_consumer.rs |
| latency_us 改用 u64 | P3 | 5min | h0_gate.rs |
| Python 超限文件評估（多數 DEPRECATED，標記計劃清理時間線） | P1 | 1h | 多文件 |

**依賴：** 無
**E2+E5 審查：** 強制

---

### WP-E：資料庫上線（預估 2 天）

**包含問題：** I-07, I-32, I-33, I-36, I-53

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| 執行 DDL V001-V007 到生產 PG | P0 | 1h | db_migrations/ |
| 驗證所有 6 個寫入器開始入庫 | P0 | 1h | 運行時驗證 |
| Thompson Sampling PG 持久化（read on startup, write on update） | P2 | 2h | thompson_sampling.py |
| drift_detector 接入 PG 讀取 | P2 | 2h | drift_detector.rs |
| ETL ASOF JOIN 類型轉換修復 | P2 | 1h | parquet_etl.py |
| 補齊缺失的 TimescaleDB 壓縮策略 | P2 | 30min | V006 DDL |

**依賴：** PG 實例可用
**E4+MIT 審查：** 強制

---

### WP-F：GUI 修復（預估 2 天）

**包含問題：** I-11, I-12, I-13, I-14, I-15, I-16, I-59, I-60

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| innerHTML 替換為 textContent（防 XSS） | P1 | 1h | tab-strategy/trading/risk.html |
| 輸入框防覆蓋（focused 時跳過刷新） | P1 | 1h | tab-risk.html JS |
| AI Apply 按鈕修復（移除父 div display:none） | P1 | 15min | tab-risk.html |
| Delete 策略 + Danger Zone 加確認彈窗 | P1 | 30min | tab-strategy.html, tab-risk.html |
| Feed/Demo/Scanner 改為只讀狀態指示器 | P1 | 30min | tab-system.html |
| Provider Key 保存 + runEvolution 調用修復 | P1 | 30min | tab-ai.html |
| 三個保存按鈕拆分或加 diff 確認 | P2 | 1h | tab-risk.html |
| 舊版 index.html 重定向到 /console | P2 | 15min | main.py |

**依賴：** 無
**A3+E4 審查：** 強制

---

### WP-G：風控參數配置化（預估 2 天）

**包含問題：** I-17, I-18, I-29, I-30, I-31, I-46, I-47, I-49

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| HC-S1/S2/S3 止損乘數配置化（移入 StopConfig） | P1 | 1h | risk/stops.rs, risk/checks.rs |
| HC-CG1/CG2 Cost Gate 閾值配置化 | P1 | 30min | intent_processor.rs |
| Regime 乘數提取為可配置結構 | P1 | 1h | risk/config.rs |
| Guardian risk score 加權配置化 | P2 | 1h | guardian.rs |
| Kelly ATR 參考值 + clamp 配置化 | P2 | 30min | kelly_sizer.rs |
| Black Swan 4 個閾值配置化 | P2 | 30min | black_swan_detector.rs |
| CostGate COST_TIERS 配置化 | P2 | 1h | cost_gate.rs |
| ATR 命名澄清（文檔+代碼注釋） | P2 | 15min | price_tracker.rs |
| operator_risk_config.json 與 Rust 默認值對齊審查 | P2 | 30min | 配置文件 |

**依賴：** 無
**QC+E2 審查：** 強制

---

### WP-H：ML 管線接線（預估 3 天）

**包含問題：** I-19, I-20, I-21, I-23, I-34, I-35, I-37, I-61

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| Scorer 接入 tick_pipeline（信號後、intent 前調用 score()） | P1 | 1d | tick_pipeline.rs |
| record_trade() 在成交回調中調用 | P1 | 1h | tick_pipeline.rs |
| PositionSnapshot 定期發射（每 30s 快照一次） | P1 | 1h | tick_pipeline.rs |
| ort crate 整合 + model_manager predict() 實現 | P1 | 2d | Cargo.toml, model_manager.rs |
| 端到端 ML 訓練腳本（ETL→label→train→CPCV→export） | P2 | 1d | ml_training/ |
| scorer_trainer 接入 cpcv_validator（替代 80/20 split） | P2 | 2h | scorer_trainer.py |
| 創建 requirements-ml.txt | P2 | 15min | 根目錄 |
| 特徵缺失值考慮 NaN 標記 | P3 | 1h | feature_collector.rs |

**依賴：** WP-E（DDL 執行後才有訓練數據）
**AI-E+MIT+E4 審查：** 強制

---

### WP-I：文檔清理（預估 1 天）

**包含問題：** I-24, I-25, I-26, I-41, I-42, I-43, I-44, I-45

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| 04-05 工作日誌合併（6 碎片→daily_summary） | P1 | 20min | docs/worklogs/ |
| docs/README.md 補充 25 項遺漏 | P1 | 30min | docs/README.md |
| 創建 helper_scripts/SCRIPT_INDEX.md | P1 | 20min | helper_scripts/ |
| CLAUDE_CHANGELOG 補充 RRC-1 條目 | P2 | 10min | docs/CLAUDE_CHANGELOG.md |
| 14 組重複文件去重（保留 CCAgentWorkSpace，audit/ 改 symlink 或刪除） | P2 | 30min | docs/audit/ |
| docs/audit/ 合併到 docs/audits/ | P2 | 15min | docs/ |
| .DS_Store git rm + .gitignore | P2 | 5min | .gitignore |
| 18 個審計報告重命名為 YYYY-MM-DD-- 格式 | P2 | 30min | docs/audit/ |

**依賴：** 無
**TW+R4 審查：** 建議

---

### WP-J：Bybit API 強化（預估 0.5 天）

**包含問題：** I-50, I-51, I-52

| 任務 | 優先級 | 預估 | 文件 |
|------|--------|------|------|
| 限流接近上限時自動延遲/跳過非關鍵請求 | P2 | 2h | bybit_rest_client.rs |
| Python GET 簽名排序 query string | P2 | 30min | bybit_demo_connector.py |
| 多品類 WS URL 支持文檔化（設計備忘） | P2 | 15min | docs/ |

**依賴：** 無
**BB 審查：** 建議

---

### WP-K：Legacy 清理（預估持續，Phase 4+）

**包含問題：** I-62

| 任務 | 優先級 | 預估 |
|------|--------|------|
| 審計 `ai_agents/bybit_thought_gate/`（~55 文件）調用者 | P3 | 2h |
| 審計 `trade_executor/bybit_decision_lease/`（~45 文件）調用者 | P3 | 2h |
| 制定 Python 降級/清理時間線（按 IPC-05 計劃） | P3 | 1h |

**依賴：** R-07 灰度通過
**PA 審查：** 建議

---

## 四、執行排程（Execution Schedule）

### 第一優先波（立即 — P0 全部 + 高影響 P1）

```
Day 1:  WP-C（測試修復） → 恢復 29+20+2 個壞測試
        WP-B（安全加固） → IPC socket 0o600 + clamp 邊界
Day 2:  WP-A（Exchange 就緒） → Cost Gate + StopRequest 接入
        WP-D-部分（market_data_client 拆分 + 編譯器警告修復）
```

**產出：** 所有 P0 清零 · stress_integration 29 測試恢復 · IPC 安全加固

### 第二優先波（本週 — P1 核心）

```
Day 3:  WP-F（GUI 修復） → XSS + 輸入框覆蓋 + 確認彈窗 + 死按鈕
Day 4:  WP-G（參數配置化） → 5 高風險硬編碼 + regime 乘數
        WP-I（文檔清理） → 日誌合併 + README 更新 + SCRIPT_INDEX
```

**產出：** GUI 可用性大幅提升 · 風控參數運行時可調 · 文檔索引恢復

### 第三優先波（下週 — P1 完善 + P2 開始）

```
Day 5-6: WP-E（DB 上線） → DDL 執行 + 驗證寫入器
Day 7-8: WP-H-部分（ML 接線） → Scorer 接入 + record_trade + PositionSnapshot
Day 9:   WP-D-剩餘（代碼品質） → on_tick 拆分 + ring buffer 提取
```

**產出：** 數據開始入庫 · ML Scorer Tier 2 上線 · 代碼可讀性改善

### 第四優先波（Phase 4 初期 — P1/P2 完善）

```
Week 3:  WP-H-剩餘（ort 整合 + 端到端訓練腳本）
         WP-J（Bybit 強化）
Week 4+: WP-K（Legacy 清理）
         WP-G-剩餘（低風險配置化）
```

---

## 五、跨切面主題分析（Cross-Cutting Themes）

### 5.1 Exchange 模式就緒度

**當前狀態：未就緒** — 以下 6 項必須在 `TradingMode::Exchange` 啟用前完成：

1. I-01 process_gates_only 缺 Cost Gate → **未修復**
2. I-08 StopRequest 未接入 set_trading_stop → **未修復**
3. I-02 IPC 無認證 → **未修復**
4. I-09 IPC 參數無邊界驗證 → **未修復**
5. I-48 學習產出無審批門禁 → **未修復**
6. I-17 止損核心硬編碼 → **未修復**

**結論：** WP-A + WP-B + WP-G 必須全部完成後才能啟用 Exchange 模式。

### 5.2 ML 管線就緒度

**當前狀態：代碼完備但未運行**（AI-E 評分 42/100、MIT 評分 52/100）

阻塞鏈：
```
DDL 未執行 (I-07)
  → 寫入器空轉 → 零數據入庫
    → 無訓練數據 → ML 訓練無法啟動
      → 無 ONNX 模型 → Scorer Tier 1 不可用
        → ort 未整合 (I-23) → 即使有模型也無法推理
```

**關鍵路徑：** I-07 → (等待 7-14 天數據) → I-34 → I-23 → I-19
**最短時間：** ~4 週（含不可壓縮的數據累積期）

### 5.3 文件大小合規

**違規清單：**
- Rust 硬違規：market_data_client.rs (1422) — **必須立即拆分**
- Rust 邊界：tick_pipeline.rs (1209) — 拆分 on_tick 後可降至 <1000
- Python 硬違規（8 個文件 >1200 行）— 多數 DEPRECATED，制定清理時間線即可
- Rust 警告級（14 個 >800 行）— 標記 E2 監控，不阻塞

### 5.4 文檔債務

**核心問題：** docs/README.md 自 04-02 停更，25 個文件未索引。
**次要問題：** 14 組重複文件、命名不規範、.DS_Store。
**影響：** 新 session 接手時無法快速找到文件。
**修復成本：** ~1 天（WP-I）。

### 5.5 硬編碼值

QC 報告識別出 **43 個硬編碼值**：
- 5 個高風險（直接影響止損/成本門檻） — P1 配置化
- 14 個中風險（Guardian/Kelly/BlackSwan 閾值） — P2 配置化
- 24 個低風險（窗口大小/先驗強度/bootstrap 參數） — 可保持硬編碼

---

## 六、報告覆蓋度統計

| 報告 | 角色 | 發現數 | P0 | P1 | P2 | P3 | 主要貢獻 |
|------|------|--------|----|----|----|----|---------|
| FA | 功能審計 | 10 GAP | 0 | 1 | 6 | 3 | 門禁鏈完整性、ML 未接線、PositionSnapshot |
| AI-E | AI 效果評估 | 7 Gap | 0 | 2 | 3 | 2 | Rust/Python 分裂、ONNX 空缺、AI 就緒度 42/100 |
| E5 | 優化工程 | 18 項 | 2 | 8 | 6 | 2 | 文件大小、代碼重複、性能、編譯器警告 |
| E4 | 測試工程 | 25+ 項 | 3 | 6 | 12+ | 0 | 壞測試、零測試模組、覆蓋缺口 |
| E3 | 安全審計 | 12 項 | 2 | 5 | 5 | 0 | Cost Gate 繞過、IPC 無認證、XSS、fail-open |
| CC | 合規檢查 | 6 項 | 1 | 2 | 3 | 0 | 文件大小硬違規、雙軌止損、原則 #7/#16 |
| QC | 量化顧問 | 43 HC | 0 | 5 | 14 | 24 | 43 個硬編碼值、公式正確性確認 |
| MIT | DB/ML 審計 | 13 項 | 2 | 4 | 7 | 0 | DDL 未執行、ort 未整合、持久化缺失 |
| BB | Bybit API | 3 項 | 0 | 0 | 3 | 0 | 限流延遲、簽名排序、多品類 WS |
| TW | 文檔盤點 | 13 項 | 3 | 7 | 3 | 0 | 重複文件、索引停更、日誌未合併 |
| R4 | 索引驗證 | 8 項 | 0 | 2 | 4 | 2 | 25 項 README 遺漏、SCRIPT_INDEX 缺失 |
| A3 | GUI 可用性 | 30+ 項 | 1 | 10 | 10+ | 5+ | 死按鈕、輸入覆蓋、確認缺失、術語混亂 |

---

## 七、結論

12 份審計報告共發現 **63 個獨立問題**（去重後），分佈為：

- **P0：7 個** — 1 安全門禁繞過 + 1 IPC 無認證 + 3 壞測試 + 1 文件超限 + 1 DDL 未執行
- **P1：21 個** — 安全加固 + GUI 修復 + 參數配置化 + ML 接線 + 文檔更新
- **P2：25 個** — 代碼品質 + DB 完善 + ML 訓練管線 + 文檔清理
- **P3：10 個** — Legacy 清理 + 建議性改善

**系統整體評價：**
- **架構設計：優秀** — 16 條原則 14/16 合規，fail-closed 8/8 覆蓋，門禁鏈 7/7 完整
- **代碼品質：良好** — 數學正確（QC 確認）、API 兼容（BB 確認）、4700+ 測試
- **運行就緒：中等** — L0 確定性層運行穩定，但 ML/AI 層未接線（AI-E 42/100）
- **文檔健康：需改善** — 索引脫節、重複文件、日誌未合併

**建議立即行動：**
1. 修復 7 個 P0（~2 天） — 恢復測試基線 + 安全門禁 + 文件合規
2. 執行 DDL（~0.5 天） — 解鎖整條 ML 管線
3. GUI P1 修復（~1 天） — 日常操作體驗大幅改善
4. 參數配置化（~1 天） — 風控核心參數可運行時調整

**預計全部 P0+P1 清零時間：** ~8 個工作日（含 E2+E4 審查）

---

*PA 統一整改計劃完成。本報告驅動所有後續修復工作的優先級和排程。*
*生成日期：2026-04-05 · 基於 12 份並行審計報告交叉分析 · 63 個獨立問題 · 11 個工作包*

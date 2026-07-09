# PM 修正路線圖：Rust 遷移
# Revised Roadmap: Rust Migration

**日期**: 2026-04-03
**版本**: V3-REVISED（基於 PA/FA/QC/E5 四角色審計數據修正）
**Operator 指令**: 不計成本做到最優解
**前置**: Phase 0-3（7 週）+ Alpha 驗證（2 週）= Week 0 起算為 Phase 3 完成後

---

## 一、修正後量化基準 / Revised Quantitative Baseline

| 項目 | 原方案 V2 | FA 審計修正後 |
|------|----------|-------------|
| Rust 新增行數 | ~13,530 | ~14,330（+indicators 800 行修正） |
| Python 完整刪除 | ~12,000 行 / 未知文件數 | ~13,690 行 / +11 文件 |
| Python 部分瘦身 | ~4,500 行 | ~6,488 行 / +3 文件 |
| 新增 Python | ~800 行 / 2 文件 | ~1,000 行 / 3 文件（+shared_types.py） |
| 受影響測試文件 | 未量化 | **53 個**（pipeline_bridge 28, kline_manager 23 為極高風險） |
| 依賴斷裂修復 | 未量化 | **16 處**（§3.1 + §3.2） |
| 總工期 | 10 週 | **14 週**（含 2 週灰度 + 2 週穩定觀察） |

**PA 計算 Rust 等效行數 ~35,000 行**（含測試、配置、CI、文檔）。14 週 = 2,500 行/週，合理。

---

## 二、修正週級路線圖 / Week-Level Roadmap (14 Weeks)

### Pre-Week：與 Phase 0-3 並行可提前開始的工作（Week -4 to -1）

| 並行任務 | 何時開始 | 前置條件 | 交付物 |
|----------|---------|---------|--------|
| Cargo workspace + CI 搭建 | Phase 1 第 1 天（Week -6） | 無 | `rust/Cargo.toml` + GitHub Actions `cargo test` |
| `openclaw_types` 完整定義 | Phase 1 第 3 天 | Cargo workspace | types crate 全部編譯通過 |
| **接口凍結** | **Phase 2 結束（Week -2）** | Phase 2 策略 V2 穩定 | 凍結文件清單簽核 |
| engine.toml 完整 SPEC 定稿 | Phase 2 結束 | 認知 SPEC V1.1 定稿 | 見附錄修正 |
| IPC 協議 echo 驗證 | Phase 3 第 1 天（Week -1） | types crate | 雙進程 ping-pong 通過 |

```
Phase 0 (W-7)     Phase 1 (W-6~W-5)    Phase 2 (W-4~W-2)    Phase 3 (W-2~W0)
  |                  |-- Cargo+CI          |-- IF FREEZE          |-- IPC echo
  |                  |-- types crate       |-- engine.toml spec   |-- Alpha 結束
  |                  |                     |                      |
  v                  v                     v                      v
  =================== Phase 0-3 (7 weeks) =======================
                                                                  |
                                                                  v  Week 1 START
```

### Week 1-2：基礎設施 + IPC + 類型

| 交付物 | Go/No-Go 門控 |
|--------|-------------|
| IPC 雙端完整實現（ipc_server.rs + ai_service.py + ipc_client.py） | 1000 msg/s 壓力測試通過 |
| `shared_types.py`（FA 建議的枚舉共享模組） | Python/Rust 枚舉值 1:1 對齊驗證 |
| engine/main.rs 骨架 + WS 連接 | 能接收 Bybit testnet WS 數據 |
| **Checkpoint 1（Week 2 結束）** | **IPC 通信穩定 + WS 連接穩定 = Go** |

### Week 3-4：openclaw_core 上半（感知 + 認知 + 風控）

| 交付物 | Go/No-Go 門控 |
|--------|-------------|
| indicators.rs — **全部 13 指標**（FA 修正：含 8 個獨立指標文件 1,272 行） | 與 Python 輸出逐值對比 < 1e-6 |
| signals.rs（8 規則）+ klines.rs | 單元測試全通過 |
| h0_gate.rs + risk.rs + attention.rs | 門控邏輯與 Python 100% 一致 |
| cognitive.rs + opportunity.rs + dream.rs（認知三模組） | QC 數學修正全部納入（Q1-Q6 + R1-1~R1-10） |
| **Checkpoint 2（Week 4 結束）** | **core 上半 100% 單元測試 + Python 對比 0 diff = Go** |

### Week 5-6：openclaw_core 下半 + engine 骨架

| 交付物 | Go/No-Go 門控 |
|--------|-------------|
| 4 狀態機（sm_auth/lease/risk_gov/oms） | 狀態轉換矩陣與 Python 完全一致 |
| guardian.rs + stop_manager.rs + portfolio.rs | 風控數值計算 < 1e-6 diff |
| execution.rs + order_match.rs + state_compute.rs | Paper Trading 訂單匹配正確 |
| backtest.rs + attribution.rs + message_bus.rs | 回測 150k 輪/s 達標 |
| engine: ws_client.rs + dispatcher.rs + fast_track.rs | WS → 注意力節流 → tick 分發 |
| **Checkpoint 3（Week 6 結束）** | **core 100% 完成 + engine 能接收 WS 做計算 = Go** |

### Week 7-8：engine 完整交易路徑（關鍵路徑，難度最高）

| 交付物 | Go/No-Go 門控 |
|--------|-------------|
| tick_pipeline.rs + intent_processor.rs（pipeline_bridge 替代，**最高風險**） | 端到端 tick→signal→intent→order 通過 |
| 5 策略 Rust 實現 + strategies/base.py 替代（FA 修正：+2 文件） | 每策略 vs Python 回測 PnL < 0.1% 偏差 |
| orchestrator.rs + governance.rs + paper_state.rs | Paper Trading 完整生命週期 |
| persistence.rs + audit.rs + config.rs | 持久化正確 + 審計日誌完整 |
| cost_gate 遷移（FA 修正：Batch 9A 新增的入場門檻） | 成本門檻邏輯一致 |
| **Checkpoint 4（Week 8 結束）** | **Rust Engine 能獨立跑完整 Paper Trading = Go/No-Go 決策點** |

> **Week 8 是硬決策點**：如果 Engine 無法獨立跑 Paper Trading，啟動 Plan B（見風險緩解 §四）。

### Week 9-10：Python 改造 + 16 處依賴斷裂修復

| 交付物 | Go/No-Go 門控 |
|--------|-------------|
| 16 處依賴斷裂修復（FA §3.1 + §3.2 全部） | 所有保留 Python 文件 import 正常 |
| phase2_strategy_routes 改 IPC 轉發 | GUI 所有頁面可用 |
| 53 個受影響測試重寫/改造（30 Rust + 15 IPC + 8 mock） | 測試總數 >= 3700 |
| runtime_bridge.py 改 IPC 讀取（FA 修正） | 狀態讀取延遲 < 5ms |
| **Checkpoint 5（Week 10 結束）** | **Python + Rust 雙進程正常運行 + 測試全通過 = Go 灰度** |

### Week 11-12：灰度驗證（雙寫雙算）

| 交付物 | Go/No-Go 門控 |
|--------|-------------|
| 影子進程搭建（Python 只算不下單） | 雙進程同時運行穩定 |
| 每 tick 對比（嚴格一致 5 bool + 浮點 < 1e-6） | 連續 7 天 CRITICAL = 0, WARNING < 10 |
| pipeline_bridge 重點驗證（28 個測試場景覆蓋） | 所有場景通過 |
| **Checkpoint 6（Week 12 結束）** | **灰度 7 天清潔 = Go 切換；CRITICAL > 0 = 延長灰度** |

### Week 13-14：穩定觀察 + 清理

| 交付物 | Go/No-Go 門控 |
|--------|-------------|
| 關閉影子進程，Rust Engine 為主 | 無回歸 |
| 冗餘 Python 代碼標記（保留 4 週後刪除） | git tag "pre-rust-cleanup" |
| 性能驗證：tick < 0.3ms, 回測 > 150k/s | 達標 |
| systemd 去硬編碼（見附錄修正） | 環境變量替代所有路徑 |

---

## 三、關鍵路徑分析 / Critical Path

```
Types → Core 上半 → Core 下半 → Engine 交易路徑 → Python 改造 → 灰度
 W1      W3-4        W5-6          W7-8              W9-10        W11-12

關鍵路徑上的 7 個難度 4-5 文件（佔 60%+ 工作量）：
  1. tick_pipeline.rs（替代 pipeline_bridge.py 2,512 行，28 測試依賴）
  2. sm_oms.rs（11 狀態 OMS，最複雜狀態機）
  3. 5 策略 Rust 實現（各含 V2 升級邏輯）
  4. intent_processor.rs（意圖→訂單完整流程）
  5. execution.rs + order_match.rs（Paper Trading 核心）
  6. cognitive.rs（QC 6 項數學修正 + R1 10 項審計修正）
  7. backtest.rs（需達 150k 輪/s）
```

---

## 四、風險矩陣 + 緩解增強 / Risk Matrix + Mitigation

| 風險 | 概率 | 影響 | 緩解方案 |
|------|------|------|---------|
| **pipeline_bridge 替代失敗** | 中 | **極高** | Week 5 開始寫 tick_pipeline.rs 原型；Week 7 前完成 smoke test |
| Rust/Python 計算不一致 | 中 | 高 | 每個 core 模組完成即跑 Python 對比，不等到灰度 |
| 53 個測試重寫工期超 | 中 | 高 | Week 3 起每寫一個 core 模組同步寫 Rust 測試，不堆到 Week 9 |
| IPC 延遲/丟失 | 中 | 高 | TTL + 超時降級 L0 + 每 5s 重連 |
| 開發超期 | 中 | 中 | **每 2 週 checkpoint（見下）** + Plan B |
| Engine 崩潰 | 低 | 高 | watchdog + 自動回退（見下） |
| 16 處依賴斷裂遺漏 | 低 | 中 | FA 審計已窮舉，Week 9 再跑一次全量 import 掃描 |

### Code Freeze 窗口設計

```
Phase 2 結束（Week -2）：接口凍結
  - 凍結對象：所有「完整刪除」和「部分瘦身」文件的公開接口（函數簽名、枚舉值、數據結構）
  - 允許：bug fix、性能優化（不改接口）
  - 違反處理：需 PM + PA 雙簽批准

Week 7 開始：Python 交易路徑 code freeze
  - 凍結對象：pipeline_bridge.py、paper_trading_engine.py、所有策略文件
  - 原因：灰度對比需要 Python 側穩定
  - 允許：純 GUI/AI/學習模組仍可開發
```

### Watchdog + 自動回退方案

```
openclaw-watchdog.service（systemd timer，每 30s）：
  1. 檢查 openclaw-engine 進程存活
  2. 檢查 /tmp/openclaw_engine.sock 可連
  3. 檢查最後 state_update 時間戳 < 60s
  4. 任一失敗 → 重啟 Engine
  5. 3 次連續重啟失敗 → 切換到 Python-only 模式（啟動影子進程為主進程）
  6. 發 Telegram 告警

自動回退觸發條件（灰度期）：
  - CRITICAL diff > 0 持續 5 分鐘 → 暫停 Rust Engine，Python 接管
  - Rust Engine OOM / segfault → 自動切回 Python
  - 手動：Operator 發 /rollback 指令
```

### 每 2 週 Checkpoint 驗收標準

| Checkpoint | 時間 | 驗收標準 | 失敗動作 |
|-----------|------|---------|---------|
| CP1 | Week 2 | IPC 1000 msg/s + WS 連接穩定 | 排查 IPC 設計，最多延 1 週 |
| CP2 | Week 4 | Core 上半 100% 測試 + Python 0 diff | 暫停 engine，先修 core |
| CP3 | Week 6 | Core 100% + engine 基礎 IO | 評估是否需要延期 Week 7-8 |
| CP4 | Week 8 | **Engine 獨立 Paper Trading** | **Plan B：縮小範圍到 core-only（PyO3 包裝），放棄獨立 Engine** |
| CP5 | Week 10 | 雙進程 + 53 測試全通過 | 延長 Python 改造 1 週 |
| CP6 | Week 12 | 灰度 7 天清潔 | 延長灰度（最多 +2 週） |

---

## 五、附錄修正 / Appendix Corrections

### A4：systemd 去硬編碼

原方案附錄 B 有 3 處硬編碼路徑，違反 CLAUDE.md 跨平台準則：

```ini
# 修正前（違規）：
ExecStart=/usr/local/bin/openclaw_engine --config /home/ncyu/BybitOpenClaw/srv/settings/engine.toml
WorkingDirectory=/home/ncyu/BybitOpenClaw/srv/program_code/...

# 修正後：
ExecStart=${OPENCLAW_BIN_DIR}/openclaw_engine --config ${OPENCLAW_BASE_DIR}/settings/engine.toml
WorkingDirectory=${OPENCLAW_BASE_DIR}/program_code/exchange_connectors/bybit_connector/control_api_v1
EnvironmentFile=/etc/openclaw/env.conf
# env.conf 內容：
#   OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv
#   OPENCLAW_BIN_DIR=/usr/local/bin
#   OPENCLAW_ENGINE_SOCKET=/tmp/openclaw_engine.sock
```

macOS 遷移：`helper_scripts/deploy/` 下提供 launchd plist 模板，讀相同 env 文件。

### A5：engine.toml 補全認知 SPEC 參數

原方案 `[cognitive]` 區塊只有 4 個基礎參數。根據認知 SPEC V1.1（含 QC Q1-Q6 + R1 修正），需補全：

```toml
[cognitive]
# 基礎參數（原有）
base_confidence_floor = 0.60
base_qty_ceiling = 1.0
base_stoploss_multiplier = 1.0
base_scan_interval_s = 1800

# V1.1 補全：CognitiveModulator
ema_alpha = 0.3                      # [Q6] EMA 平滑係數
max_stoploss_multiplier = 1.5        # 止損倍率上限
min_scan_interval_s = 300            # 掃描間隔下限
max_scan_interval_s = 7200           # 掃描間隔上限

# V1.1 補全：OpportunityTracker
max_tracked_opportunities = 100      # 最大追蹤機會數
opportunity_ttl_hours = 168          # 機會 TTL（7 天）
virtual_stoploss_pct = 5.0           # 虛擬止損
virtual_takeprofit_pct = 10.0        # 虛擬止盈
estimated_fee_pct = 0.075            # [Q2][R1-9] 預估單邊費率（含滑點）

# V1.1 補全：DreamEngine
dream.candle_window_days = 7         # 已有
dream.cycles_per_batch = 100         # 已有
dream.max_cycles_per_idle = 10000    # 已有
dream.min_simulations_per_param = 30 # [Q4] 每參數最少模擬輪數
dream.binomial_confidence = 0.95     # [Q5] 統計檢驗信心水平
dream.seed = 0                       # [R1-10] 0=隨機，>0=可重現
```

---

## 六、總結 / Summary

- **總工期 14 週**（原 10 週 + 4 週用於 FA 發現的 36 個遺漏文件 + 16 處依賴斷裂 + 53 個測試重寫）
- **可並行提前 4-6 週**（Cargo+CI+types 在 Phase 1 即可開始）
- **淨新增時間 8-10 週**（扣除並行部分）
- **關鍵決策點 Week 8**：Engine 能否獨立 Paper Trading 決定是否堅持一步到位還是降級 PyO3
- **6 個 checkpoint**，每個有明確驗收標準和失敗動作
- **自動回退機制**確保任何時刻可退回 Python-only 運行

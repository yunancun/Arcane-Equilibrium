# OpenClaw Bybit — Rust 遷移方案 V2.5 整合版

**日期**: 2026-04-03
**版本**: V2.5-CONSOLIDATED（V2 + 四角色審查 + 六路缺口解決方案整合）
**待辦**: 嚴格論證通過後升級為 V3-FINAL

---

# 修訂總覽（V2 → V2.5 全部修正）

## 量化修正

| 項目 | V2 原值 | V2.5 修正值 | 修正來源 |
|------|---------|------------|---------|
| Python 待遷移總行數 | ~12,000 | **22,850** | PA 逐文件實測 |
| Rust 行數預算 | 13,530 | **35,000**（含測試+FFI） | PA 1:1.7 比 + E5 校驗 |
| 遺漏文件 | 0 | **23 個 / 5,514 行** | FA 全量盤點 |
| 依賴斷裂點 | 0 | **22 個**（12 IPC + 9 shared_types + 1 部分瘦身） | FA 依賴分析 |
| 受影響測試 | 未量化 | **53 個文件 / 32 個直接 import** | E4 測試審計 |
| Lock 數量 | 16+ | **52 個**（tick 路徑 8-11 個） | E5 全量 grep |
| tick 延遲現狀 | 15-60ms | **0.3-1ms P50 / 2-5ms P99** | E5 調用鏈追蹤 |
| 工期 | 10 週 | **14 週**（+4 週提前並行） | PM 重排 |

---

# §1 最終目標架構（V2 不變，補充 GovernanceCore 設計）

> V2 §1 的進程模型和設計原則不變。新增以下補充：

## 1.6 GovernanceHub 切分方案（PA 設計，解決 B2）

**核心決策：4 SM 全部放 Rust，級聯在進程內完成。**

### Rust（GovernanceCore）
- `is_authorized()` — 熱路徑，每 tick 調用
- `acquire_lease()` / `release_lease()` — 熱路徑
- `_on_risk_escalation()` — 純確定性級聯：risk→auth→lease→mode
- `_on_auth_frozen()` — 純確定性：collect lease→revoke all
- `_on_reconciliation_mismatch()` — 純確定性：severity→risk mapping
- `check_risk_and_act()` / `get_risk_level()` / `get_status()` — 只讀

### Python（GovernanceHub 瘦身版）
- `grant_paper_authorization()` — 冷路徑，含多步業務策略
- `request_de_escalation()` — 含 LearningTierGate（未來接 AI）
- `handle_incident_auth_action()` — IncidentPolicy 觸發
- Telegram alerter / ChangeAuditLog 寫入 — I/O 密集

### IPC 協議：State Snapshot Batch（1 輪 RPC 替代 3-4 輪）
```
Python startup → init_state(4 SM) → Rust 載入
tick 期間 → Rust 進程內直接判斷，0 IPC
級聯事件 → Python 發 1 次 risk_upgrade RPC → Rust 內部完成整條鏈
         → 返回 CascadeResult（含所有變更）
         → Python 收到後寫審計+推 Telegram（非阻塞）
GUI 讀取 → get_governance_snapshot() 單次 RPC 取全部快照
```

## 1.7 Lock 策略（PA 設計，解決 B3）

**核心決策：Single-owner actor 模式，52 個 RLock → tick 路徑 0 鎖。**

```
Tick Thread (tokio task) ─── single-owner，無鎖直接讀寫 SM states
    │ mpsc channel
Cascade Worker (single) ─── 串行處理所有級聯事件
    │ broadcast channel
Snapshot (ArcSwap) ─────── GUI/IPC 讀取零阻塞（atomic pointer swap）
```

| 路徑 | 機制 | 鎖數 |
|------|------|------|
| Tick 熱路徑 | Single-owner actor | 0 |
| 級聯事件 | mpsc channel 序列化 | 0 |
| GUI/IPC 讀取 | ArcSwap atomic | 0 |
| Python IPC 寫入 | mpsc→actor→oneshot | 0 |

---

# §2 遷移完整清單（V2 + FA 補全 23 個遺漏）

> V2 §2.1-§2.3 保留，以下為修正：

## 2.1 行數修正表（PA 實測）

| 源文件 | V2 估計 | 實測行數 | 偏差 | 難度 |
|--------|---------|---------|------|------|
| pipeline_bridge.py | ~1,000 | **2,512** | 2.5x | 5 |
| paper_trading_engine.py | ~830 | **2,243** | 2.7x | 5 |
| governance_hub.py | ~350 | **1,903** | 5.4x | 4 |
| risk_manager.py | ~400 | **1,633** | 4.1x | 4 |
| signal_generator.py | ~300 | **1,212** | 4.0x | 3 |
| backtest_engine.py | ~450 | **1,352** | 3.0x | 4 |
| multi_agent_framework.py | ~350 | **1,104** | 3.2x | 4 |
| kline_manager.py | ~200 | **1,055** | 5.3x | 3 |
| trade_attribution.py | ~220 | **958** | 4.4x | 3 |
| 其餘文件 | 各見 PA 報告 | | | |

## 2.4 文件歸屬修正（V2 + FA 補全）

### 完整刪除（V2 原有 + FA 補 11 個）
```
V2 原有：pipeline_bridge.py · market_data_dispatcher.py · bybit_public_ws_listener.py
  h0_gate.py · 4 個狀態機 · indicator_engine.py · signal_generator.py
  kline_manager.py · stop_manager.py · strategy_orchestrator.py · strategies/*.py(5個)

FA 補全：indicators/__init__.py · indicators/base.py · indicators/atr.py
  indicators/bollinger_bands.py · indicators/macd.py · indicators/moving_averages.py
  indicators/rsi.py · indicators/stochastic.py · strategies/__init__.py
  strategies/base.py · cost_gate.py
```

### 部分瘦身（V2 原有 + FA 補 3 個）
```
V2 原有：risk_manager.py · guardian_agent.py · paper_trading_engine.py
  multi_agent_framework.py · portfolio_risk_control.py · governance_hub.py
  trade_attribution.py · backtest_engine.py

FA 補全：lease_ttl_config.py（TTL 數值遷 Rust）
  market_regime.py（regime 計算遷 Rust，歷史查詢留 AI）
  strategy_auto_deployer.py（策略實例化改 IPC 指令）
```

### 完全保留（V2 原有 + FA 補 8 個）
```
FA 補全：__init__.py · _path_setup.py · main_legacy.py · main_snapshot_stable.py
  paper_trading_metrics.py · strategist_models.py · evolution_engine.py · market_scanner.py
```

### 修改 Python（V2 原有 + FA 補 1 個）
```
FA 補全：runtime_bridge.py（改為 IPC 讀取 Rust 狀態）
```

### 新增 Python（V2 + FA 建議）
```
V2：ai_service.py (~500 行) · ipc_client.py (~300 行)
FA：shared_types.py (~120 行) — 4 enum + 5 dataclass
```

---

# §3 依賴斷裂修復方案（新增，FA 設計）

## 3.1 修復方案總表

| 保留文件 | 斷裂 import | 修復方案 |
|----------|------------|---------|
| governance_hub.py | AuthorizationSM, DecisionLeaseSM | IPC 替代 |
| governance_hub.py | RiskLevel, RiskInitiator | shared_types |
| governance_hub.py | OrderState, OrderInitiator | shared_types |
| governance_routes.py | RiskLevel, RiskInitiator | shared_types |
| paper_trading_engine.py | OMSStateMachine | IPC 替代 |
| paper_trading_engine.py | OrderState, OrderInitiator | shared_types |
| paper_trading_routes.py | MarketDataDispatcher, H0Gate | IPC 替代 |
| paper_trading_routes.py | H0GateConfig | shared_types |
| paper_trading_routes.py | OrderState, OrderInitiator | shared_types |
| phase2_strategy_routes.py | PipelineBridge, 全部 lmt 模組 | IPC 替代 |
| phase2_strategy_routes.py | StopConfig | shared_types |
| risk_manager.py | H0GateRiskSnapshot | shared_types |
| backtest_routes.py | BacktestEngine, BacktestConfig | IPC 替代 |
| strategy_auto_deployer.py | strategies/* 實例化 | IPC 部署指令 |

**統計：22 個斷裂 → 12 IPC + 9 shared_types + 1 部分瘦身**

## 3.2 shared_types.py 設計（~120 行）

| 類型 | 種類 | 來源 |
|------|------|------|
| RiskLevel | IntEnum | risk_governor_state_machine.py |
| RiskInitiator | str Enum | risk_governor_state_machine.py |
| OrderState | str Enum | oms_state_machine.py |
| OrderInitiator | str Enum | oms_state_machine.py |
| H0GateRiskSnapshot | dataclass | h0_gate.py |
| H0GateConfig | dataclass | h0_gate.py |
| H0GateCheckResult | dataclass | h0_gate.py |
| H0GateHealthSnapshot | dataclass | h0_gate.py |
| StopConfig | dataclass | stop_manager.py |

**與 Rust `openclaw_types` crate 嚴格 1:1 對齊。**

---

# §4 IPC 協議（V2 §4 不變）

---

# §5 灰度驗證（V2 §5 + QC 浮點容差修正）

## 5.4 浮點容差分級標準（QC 設計，替代 V2 的 1e-6）

| 類別 | 容差 | 類型 | 數學理由 |
|------|------|------|----------|
| 簡單聚合指標（SMA/BB/ATR/Donchian/VolumeRatio） | 相對 1e-10 | 相對誤差 | N=200 累加 ≈ 2.2e-14 |
| 遞歸指標（EMA/MACD/RSI/KAMA/ADX/EWMA Vol） | 相對 1e-8 | 相對誤差 | N=200 連乘累積 ≈ 4e-12 |
| Hurst 指數 | 絕對 1e-6 | 絕對誤差 | log + 線性回歸 |
| 信號方向（long/short/hold） | **嚴格一致 + 閾值 ±0.1% 邊界豁免區** | — | 邊界處翻轉是數學必然 |
| 止損/止盈價格 | 相對 1e-8 或絕對 0.01 USD 取寬者 | 混合 | ATR 乘法 + 低價幣保護 |
| PnL 計算 | 絕對 0.01 USD | 絕對誤差 | 交易所結算精度 |
| H0 Gate 5 bool | **嚴格一致** | — | 安全門控 P0 |
| 狀態機轉換 | **嚴格一致** | — | 離散系統無近似 |

**邊界豁免區規則**：信號閾值 ±0.1% 帶內允許不一致並標記 `BOUNDARY_DIVERGENCE`。帶外必須嚴格一致。若因邊界導致 H0 Gate bool 翻轉，以 Python（保守側）為準。

**實作建議**：Rust SMA 使用 Kahan 補償求和，EMA 使用相同 α 常數。

## 5.5 Golden Dataset 規格（QC 設計）

| 數據組 | 內容 | 數量 | 用途 |
|--------|------|------|------|
| 穩態 | BTCUSDT 1m K 線 | 2000 根 (~33h) | 遞歸指標收斂驗證 |
| 極端 | 含閃崩/插針歷史段 | 500 根 | 數值穩定性 |
| 邊界 | 人工構造閾值命中 ±1e-9 | 50 根 | 邊界豁免區測試 |

**格式**：JSONL，每行含 ts_ms/kline/indicators/signals/h0_gate/pnl_cumulative。
**產出**：Phase 1 Paper Trading 自動寫出，零額外成本。
**對比**：Comparator 獨立進程逐行 diff → FAIL>0 阻斷放權。

---

# §6 修正後路線圖（PM 設計，14 週 + 4 週提前並行）

## 提前並行（Phase 0-3 期間）
| 任務 | 時間 | 交付物 |
|------|------|--------|
| Cargo workspace + CI | Phase 1 Day 1 | rust/Cargo.toml + cargo test CI |
| openclaw_types crate | Phase 1 Day 3 | 全部類型編譯通過 |
| 接口凍結 | Phase 2 結束 | 凍結文件清單簽核 |
| IPC echo 驗證 | Phase 3 Day 1 | 雙進程 ping-pong 通過 |

## 14 週主計劃
| 週 | 交付物 | Go/No-Go |
|----|--------|----------|
| W1-2 | IPC 雙端 + shared_types + WS 連接 | IPC 1000 msg/s 壓測通過 |
| W3-4 | core 上半：indicators(13) + signals(8) + klines + h0_gate + risk + attention + cognitive + opportunity + dream | Golden Dataset 對比全部 PASS |
| W5-6 | core 下半：guardian + execution + order_match + state_compute + portfolio + stop_manager + 4 SM + message_bus + attribution + backtest | SM 轉換窮舉測試通過 |
| W7-8 | engine：tick_pipeline + intent_processor + orchestrator + strategies(5) + governance + paper_state + persistence + audit | **Week 8 硬決策點：Engine 能獨立跑 Paper → Go；否則降級為 PyO3** |
| W9-10 | Python 改造 + IPC 集成 + 測試遷移 | IPC 集成測試 60 個全 PASS |
| W11-12 | 灰度驗證（雙寫雙算 7 天） | CRITICAL=0 且 WARNING<10 連續 7 天 |
| W13-14 | 穩定觀察 + 冗餘清理 | 關閉影子進程，tag pre-rust-cleanup |

## Week 8 硬決策點
- **Go**：Rust Engine 能獨立接收 WS → 計算指標 → 產生信號 → 下 Paper 單 → 止損 → 持久化
- **No-Go**：降級為 PyO3 漸進式方案，僅遷移 indicators + signals + klines 到 Rust 模組

---

# §7 風險矩陣（V2 + PM/E5 增強）

| 風險 | 概率 | 影響 | 緩解措施 |
|------|------|------|----------|
| Rust/Python 計算不一致 | 中 | 高 | QC 分級容差 + 7 天灰度 + Golden Dataset |
| IPC 延遲/丟失 | 中 | 高 | TTL + 超時降級 L0 + watchdog 30s 心跳 |
| 策略行為差異 | 中 | 高 | 灰度逐信號對比 + 邊界豁免區 |
| Engine 崩潰 | 低 | 高 | systemd RestartSec=2 + watchdog 3-strike 自動回退 Python |
| 開發超期 | 中 | 中 | Week 8 硬決策點 + 每 2 週 checkpoint |
| Python 代碼持續演進 | 中 | 中 | 接口凍結（Phase 2 結束）+ code freeze（Week 7） |
| 依賴斷裂未覆蓋 | 低 | 中 | FA 22 點修復方案 + shared_types 對齊 |
| 測試基準線回退 | 中 | 中 | CI 門檻：Python≥3500 + cargo test 0 fail + 灰度 diff=0 |

---

# §8 修正後量化總結（E5 設計）

## 8.1 代碼量

| Crate | 對應 Python | Rust 行（預估） |
|-------|------------|----------------|
| openclaw_types | state_models + SM enum/struct | 4,500 |
| openclaw_core | h0_gate + risk + governance + SM | 8,700 |
| openclaw_engine | pipeline + kline + indicator + signal + strategies | 13,800 |
| openclaw_ffi | PyO3 橋接（備選） | 2,500 |
| 測試代碼 | — | 5,500 |
| **總計** | | **35,000** |

## 8.2 性能（實測基準修正）

| 指標 | Python 現狀（E5 實測） | Rust 目標 | 提升 | 依據 |
|------|----------------------|-----------|------|------|
| tick P50 | 0.3-0.5ms | 5-15μs | 30-50x | 消除 GIL + deepcopy + Lock |
| tick P99 | 2-5ms（kline close） | 50-120μs | 30-40x | SIMD 批量指標計算 |
| tick P99.9 | 5-15ms（極端） | 200-500μs | 20-30x | 含 state compile + risk |
| deepcopy 消除 | 0.8-2ms（37 處） | 10-30μs（Arc/CoW） | 50-80x | 零拷貝讀 |
| state persist | 3-8ms 阻塞 | 0（異步 mmap） | ∞ | 後台線程 |
| Lock 競爭 | 52 個 Lock | actor 模式 0 鎖 | — | Single-owner |
| 記憶體 | ~200-400MB | ~40-80MB | 4-5x | struct 緊湊佈局 |
| **[新]** 快速通道 | 不存在 | tick-to-order <50μs | — | H0→Execute Rust fast-path |
| **[新]** Python 降級容錯 | 不存在 | Rust core 獨立運行 | — | Python 崩潰保持止損 |

## 8.3 時間投入
```
提前並行：4-6 週（Phase 1-3 期間）
主開發：14 週
風險緩衝：+3 週（20%）
總計：17 週壁鐘（扣除提前並行 = 淨新增 11-13 週）
```

---

# §9 測試遷移計劃（新增，E4 設計）

## 9.1 四層測試架構

| 層級 | 數量 | 工具 | 覆蓋範圍 |
|------|------|------|----------|
| Rust 單元測試 | ~400 | `#[test]` + proptest | 每個 .rs 模組的確定性邏輯 |
| Rust 集成測試 | ~80 | `tests/` | 端到端 tick + SM 窮舉 + 策略邊界 |
| Python↔Rust IPC | ~60 | pytest | AI 往返 + 控制指令 + 斷連恢復 |
| 灰度對比 | ~20 場景 | JSONL diff | 自動化容差判定 |

## 9.2 現有測試處置

| 處置 | 文件數 | 說明 |
|------|--------|------|
| 直接刪除 | ~8 | 純測試 Python 內部實現 |
| 改為 IPC 測試 | ~14 | 數據源變為 Rust Engine |
| 保留不動 | ~10 | Python 側邏輯（Agent/學習/路由） |

## 9.3 基準線維護
```
遷移前：3,703 Python
遷移後：~3,513 Python + ~480 Rust + 灰度框架 = ~3,993 total
CI 門檻：Python pytest ≥ 3,500 + cargo test 0 fail + 灰度 diff = 0
```

---

# 附錄修正

## 附錄 B：systemd（去硬編碼，A4 修正）
```ini
# 使用 EnvironmentFile 替代硬編碼路徑
[Service]
EnvironmentFile=/etc/openclaw/env
ExecStart=${OPENCLAW_BASE_DIR}/rust/target/release/openclaw_engine --config ${OPENCLAW_BASE_DIR}/settings/engine.toml
User=${OPENCLAW_USER}
```

## 附錄 C：engine.toml（補全認知 SPEC 參數，A5 修正）
```toml
[cognitive]
base_confidence_floor = 0.60
base_qty_ceiling = 1.0
base_stoploss_multiplier = 1.0
base_scan_interval_s = 1800
max_confidence_floor = 0.85
min_confidence_floor = 0.45
min_qty_ceiling = 0.3
max_stoploss_multiplier = 2.0
min_scan_interval_s = 300
max_scan_interval_s = 3600
ema_alpha = 0.3

[opportunity_tracker]
max_tracked = 100
ttl_days = 7
virtual_stoploss_pct = 5.0
virtual_takeprofit_pct = 10.0
estimated_fee_pct = 0.075
min_samples_for_direction = 5

[dream]
candle_window_days = 7
cycles_per_batch = 300
max_cycles_per_idle = 10000
min_cycles_for_confidence = 200
param_grid_size = 10
min_samples_per_param = 30
```

---

# 支撐文件

| 文件 | 內容 |
|------|------|
| `docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-03--rust_migration_file_coverage_audit.md` | FA 全量文件盤點 + 依賴斷裂分析 |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-03--rust_migration_revised_roadmap.md` | PM 修正路線圖 + 風險矩陣 |
| `docs/references/2026-04-03--rust_migration_master_plan_v2.md` | V2 原始方案（歸檔） |

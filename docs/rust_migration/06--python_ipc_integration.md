# Phase R-06：Python IPC 改造（Week 9-10）

**週期**：Rust 主開發 Week 9-10
**工時**：~2 週
**前置**：`05--week8_decision_gate.md` → Go
**下一階段**：`07--canary_validation.md`

---

## 上下文導航

```
源文件：V3-FINAL §3（依賴斷裂修復）+ §9（測試遷移）
前置完成：Rust Engine 獨立跑 Paper Trading · Week 8 Go 決策
本階段目標：Python GUI/routes 全部改為 IPC 讀取 Rust Engine
```

---

## 具體任務

### Route 文件 IPC 改造（7 個文件）

### [ ] R06-1：phase2_strategy_routes.py
- PipelineBridge → IPC · KlineManager/IndicatorEngine/SignalEngine/StrategyOrchestrator → IPC
- StopConfig → shared_types · strategies 實例化 → IPC 部署指令

### [ ] R06-2：paper_trading_routes.py
- MarketDataDispatcher/H0Gate → IPC · OMSStateMachine → IPC
- H0GateConfig/OrderState → shared_types

### [ ] R06-3：governance_routes.py
- RiskLevel/RiskInitiator → shared_types（已在 R01-5 準備）
- GovernanceHub 讀取 → 保留（瘦身版直接讀 IPC snapshot）

### [ ] R06-4：backtest_routes.py
- BacktestEngine → IPC 發送回測請求

### [ ] R06-5：legacy_routes.py [V3-FA-3]
- PIPELINE_BRIDGE → IPC · _latest_prices → IPC state_update

### [ ] R06-6：risk_routes.py [V3-FA-3]
- RISK_MANAGER 間接依賴 → 改為 IPC 讀取

### [ ] R06-7：runtime_bridge.py
- 文件讀取 → IPC 從 Rust Engine 讀取狀態

### Python 側其他改造

### [ ] R06-8：governance_hub.py 瘦身
- 刪除已遷 Rust 的確定性邏輯（is_authorized/級聯等）
- 保留：grant_paper_authorization / de_escalation / Telegram / audit 寫入
- 新增：IPC 調用 GovernanceCore 的包裝方法

### [ ] R06-9：paper_trading_engine.py 瘦身
- 刪除 tick()/mutate() 計算邏輯（已在 Rust）
- 保留：PaperStateStore I/O 的 Python 側兼容（灰度期影子進程需要）

### [ ] R06-10：strategy_auto_deployer.py 瘦身
- 策略實例化 → IPC 部署指令
- 保留：部署決策邏輯 · 停用判斷

### [ ] R06-11：conftest.py 最終改造 [V3-FA-4]
- SM 類 → IPC mock fixture（啟動 Rust Engine 子進程 or MagicMock with IPC behavior）
- 確保所有 15 處斷裂完全修復

### 測試

### [ ] R06-12：IPC 集成測試 60 個
- AI 請求/回覆往返 ~15
- Operator 控制指令 ~15
- 斷連/重連/超時 ~15
- 序列化 fuzz ~15

### [ ] R06-13：回滾計劃預演 [V3-PM-7]
- 模擬 Rust Engine 崩潰 → watchdog 3-strike → Python fallback
- 驗證 runtime 回滾 SLA < 30 秒
- 記錄完全回滾步驟 + 計時

---

## Go/No-Go 門控

- [ ] 7 個 route 文件全部 IPC 改造完成
- [ ] IPC 集成測試 60 個全 PASS
- [ ] Python pytest ≥ 3,500 pass（基準線不回退）
- [ ] 回滾預演 SLA < 30 秒
- [ ] conftest 15 處斷裂全部修復

---

## 進度追蹤

| 任務 | 狀態 | 完成日期 | commit |
|------|------|---------|--------|
| R06-1~7 Route 改造 | [ ] | | |
| R06-8~10 Python 瘦身 | [ ] | | |
| R06-11 conftest | [ ] | | |
| R06-12 IPC 測試 | [ ] | | |
| R06-13 回滾預演 | [ ] | | |

---

## 問題與變更

（空）

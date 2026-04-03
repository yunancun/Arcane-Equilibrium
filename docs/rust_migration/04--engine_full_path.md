# Phase R-04：Engine 完整交易路徑（Week 7-8）

**週期**：Rust 主開發 Week 7-8
**工時**：~2 週
**前置**：`03--core_lower.md` Go
**下一階段**：`05--week8_decision_gate.md`（硬決策點）

---

## 上下文導航

```
源文件：V3-FINAL §1.1（進程模型）+ §6.3 W7-8
前置完成：openclaw_core 全部通過 · 極端組 PASS · SM 窮舉 PASS
本階段目標：Rust Engine 能獨立運行完整 Paper Trading
★ Week 8 結束觸發硬決策點——見 05--week8_decision_gate.md
```

---

## 具體任務

### [ ] R04-1：engine/tick_pipeline.rs — on_tick 4 步編排（2,512 行源碼核心）
- WS event → kline 聚合 → 策略 dispatch → risk check → stats update
- Tick actor sole-owner 模式：mpsc drain 在 tick 間隙 [V3-PA-1]

### [ ] R04-2：engine/intent_processor.rs — 意圖處理流程
- Guardian 檢查 → GovernanceCore lease → OMS 提交
- 快速通道分流 [fast_track]

### [ ] R04-3：engine/fast_track.rs — 快速通道
- Risk Governor ≥ DEFENSIVE → 預定義規則直接執行
- 閃崩/保證金危機 → 立即平倉

### [ ] R04-4：engine/orchestrator.rs — 策略調度
### [ ] R04-5：engine/strategies/*.rs — 5 策略 on_tick
- ma_crossover · grid_trading · bb_reversion · bb_breakout · funding_arb

### [ ] R04-6：engine/governance.rs — GovernanceCore 運行時整合
### [ ] R04-7：engine/paper_state.rs — 狀態管理 + 持久化
- [V3-E5-1] 持久化在獨立線程（crossbeam channel），tick actor 不觸碰 mmap

### [ ] R04-8：engine/persistence.rs + engine/audit.rs — 基礎設施
- JSON debounced write（5s 間隔）
- JSONL append-only 審計

### [ ] R04-9：端到端集成測試
- WS JSON 消息 → 指標 → 信號 → H0 → 級聯 → 執行 → PnL → 持久化
- 至少 20 個場景

### [ ] R04-10：Engine 獨立運行 Paper Trading 驗證
- 連接 Bybit testnet WS
- 跑 24 小時無崩潰
- 產出至少 5 筆 Paper 交易
- tick P50 < 100μs（放寬目標，正式目標 5-15μs 在灰度期校準）

---

## Go/No-Go（觸發 Week 8 硬決策點）

- [ ] Engine 獨立運行 24h 無崩潰
- [ ] 至少 5 筆 Paper 交易正確記錄
- [ ] tick P50 < 100μs
- [ ] 快速通道觸發正確（模擬 DEFENSIVE 場景）

**以上全部滿足 → 進入 `05--week8_decision_gate.md` 決策。**

---

## 進度追蹤

| 任務 | 狀態 | 完成日期 | commit |
|------|------|---------|--------|
| R04-1 tick_pipeline | [ ] | | |
| R04-2 intent_processor | [ ] | | |
| R04-3 fast_track | [ ] | | |
| R04-4~5 strategies | [ ] | | |
| R04-6~8 governance+infra | [ ] | | |
| R04-9 集成測試 | [ ] | | |
| R04-10 24h 獨立運行 | [ ] | | |

---

## 問題與變更

（空）

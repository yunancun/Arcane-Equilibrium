# Phase 3a — update_params() 改造 = AGT-1（W9-10，6/05-6/18，10 工作日）

> 前置：Phase 2 完成
> DoD：10 個 update_params()（Python 5 + Rust 5）· 50+ 新 tests · Python-Rust 行為一致 · 全量全綠

## Rust 與 Python 完全並行

### Day 1: ���口設計
- 3a-01: Python StrategyBase.update_params() 抽象接口 + Pydantic 參數 model (PA+E1-A)
- 3a-02: Rust Strategy trait `fn update_params(&mut self, params: &ParamSet) -> Result<()>` (E1-B)

### Day 2-5: 10 策略實現（5 ��並行）
**Python 側（E1-C/D/E → E1-A/B）：**
- 3a-03: MACrossoverStrategy.update_params()
- 3a-04: BBReversionStrategy.update_params()
- 3a-05: BBBreakoutStrategy.update_params()
- 3a-06: FundingArbStrategy.update_params()
- 3a-07: GridTradingStrategy.update_params()（含 OU 參數聯動）

**Rust 側（同時，E1 另外分配）：**
- 3a-08: MACrossover::update_params()
- 3a-09: BBReversion::update_params()
- 3a-10: BBBreakout::update_params()
- 3a-11: FundingArb::update_params()
- 3a-12: GridTrading::update_params()

### Day 6-8: 測試
- 3a-13: Python 5 策略 tests（per strategy 5+ tests × 5 = 25+）
- 3a-14: Rust 5 策略 tests（同上）
- 3a-15: Python-Rust 交叉一致性（同參數 → 同行為）

### Day 9-10: 審查
- 3a-16: **E2 代碼審查**
- 3a-17: **E4 全量回歸**

## 線程安全

- Python：用 `_intent_lock` (RLock) 保護 update_params + on_signal 互斥
- Rust：tick pipeline sole-owner `&mut self`，天然安全（不需要 Arc/Mutex）
- Grid 特殊：update_params 需要同步重算 grid levels（OU 參數聯動）

# Session Progress — 2026-04-03 Session 6（Phase R-03 完成）

## 已完成項

### Phase R-03：core 下半 — SM + 執行 + 回測

**Batch 1（4 SM 狀態機，並行）：**
- `sm/auth.rs`（601 行）：8 狀態 Authorization SM + 16 遷移 + 7 禁止 + 5 守衛（15 tests）
- `sm/lease.rs`（538 行）：9 狀態 Decision Lease SM + 18 遷移 + 12 禁止（14 tests）
- `sm/risk_gov.rs`（583 行）：6 級風控 + 23 遷移 + 自動升級/受控降級 + min hold time（14 tests）
- `sm/oms.rs`（548 行）：11 態 OMS 生命週期 + 16 遷移 + 對賬流程（11 tests）

**Batch 2（GovernanceCore 級聯）：**
- `governance_core.rs`（490 行）：all-or-nothing risk→auth→lease 級聯 + evaluate_and_cascade（12 tests）

**Batch 3（確定性檢查 + 執行）：**
- `guardian.rs`（270 行）：4 項確定性風控（方向衝突+持倉數+槓桿+回撤）（7 tests）
- `execution.rs`（262 行）：5 層滑點 + 成交價 + 手續費 + 損益計算（16 tests）
- `order_match.rs`（267 行）：限價單匹配 + 部分成交率（10 tests）

**Batch 4（組合 + 止損 + 消息 + 歸因）：**
- `portfolio.rs`（331 行）：Pearson 相關 + 儲備/集中度/相關性 3 層（7 tests）
- `stop_manager.rs`（325 行）：hard/trailing/time + ATR 倉位計算（14 tests）
- `message_bus.rs`（257 行）：6 Agent 消息路由 + 優先級衝突解決（6 tests）
- `attribution.rs`（235 行）：6 因子 PnL 分解（9 tests）

**Batch 5（回測引擎）：**
- `backtest.rs`（438 行）：逐 K 線回放 + SignalGenerator trait + Sharpe/drawdown（9 tests）

**Batch 6（極端組）：**
- `tests/golden_extreme.rs`（287 行）：19 個極端場景測試

**E2 PASS · E4 零回歸 · E5 清理完成**

---

## 測試基準線
```
Python: 3703 passed / 24 failed / 17 errors（pre-existing，零回歸）
Rust:   468 passed / 0 failed
  core:    376 lib + 8 golden + 19 extreme = 403
  engine:  29
  types:   36
Schema:  10 types validated
```

## 關鍵決策
1. **SM 拆為子目錄 sm/**：mod.rs + 4 SM 文件，共用 TransitionRecord/SmError
2. **GovernanceCore 擁有 4 SM**：sole-owned，無鎖（V3-PA-1）
3. **級聯 all-or-nothing**：snapshot → execute → commit/rollback（V3-PA-3）
4. **state_compute 併入 governance_core**：GovernanceCore.status() 提供派生狀態
5. **message_bus 精簡**：只遷移路由核心（257 行），Conductor 編排留 Python
6. **backtest 用 SignalGenerator trait**：策略可插拔

## Rust Workspace 結構
```
rust/
  openclaw_core/
    src/
      sm/            — 4 SM: auth, lease, risk_gov, oms + mod (54 tests)
      governance_core — all-or-nothing cascade (12 tests)
      guardian       — 4 deterministic checks (7 tests)
      execution      — slippage + fill + fee (16 tests)
      order_match    — limit order matching (10 tests)
      portfolio      — correlation + concentration (7 tests)
      stop_manager   — hard/trailing/time + ATR (14 tests)
      message_bus    — 6-role routing (6 tests)
      attribution    — 6-factor PnL (9 tests)
      backtest       — bar-by-bar replay (9 tests)
      [R-02 modules] — attention, cognitive, cost_gate, dream, h0_gate,
                        indicators/, klines, opportunity, risk/, signals/
    tests/
      golden_dataset    — R-02 cross-validation (8 tests)
      golden_extreme    — R-03 extreme scenarios (19 tests)
```

## 下一步指引
1. Phase R-03 全部完成 ✅
2. 下一步：**R-04 engine 完整交易路徑**
3. R-04 入口：`docs/rust_migration/04--engine_full_path.md`
4. R-04 內容：tick actor + 完整交易管線 + IPC handler wiring

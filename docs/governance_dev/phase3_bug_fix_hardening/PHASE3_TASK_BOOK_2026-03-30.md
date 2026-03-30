# Phase 3 任務書：缺陷修復與強化（Bug Fix & Hardening）
# Phase 3 Task Book: Bug Fix & Hardening

**版本：** V1.0
**日期：** 2026-03-30
**作者：** PM (via Cowork PM)
**前置條件：** Phase 2 PASSED（1761 tests, 2 pre-existing failures）
**Phase 完成標準：** 2 個 P0 測試修復 + 保護性訂單觸發在位 + ScannerRateLimiter 注入 + 審計擴展 + 0 test failures

---

## FA 審計來源

基於 `PHASE_3_GAP_AUDIT_REPORT.md`（2026-03-30），識別 7 個治理缺口。

---

## 任務總覽

| Task ID | 任務名稱 | 優先級 | 工作量 | 依賴 | 對應 GAP |
|---------|---------|--------|--------|------|---------|
| T3.01 | Session Drawdown Halt 修復 | P0 | M | 無 | GAP-P3-001 |
| T3.02 | Daily Loss Pre-Order Check 修復 | P0 | M | 無 | GAP-P3-002 |
| T3.03 | ProtectiveOrderManager.check_triggers() 接入 tick | P1 | S | T2.03 | GAP-P3-003 |
| T3.04 | Daily Loss Session Halt 行為一致性 | P1 | S | T3.02 | GAP-P3-005 |
| T3.05 | ScannerRateLimiter 注入 PipelineBridge | P2 | S | T2.07 | GAP-P3-004 |
| T3.06 | ChangeAuditLog 擴展記錄範圍 | P2 | M | T2.04 | GAP-P3-006 |
| T3.07 | Phase 3 回歸測試 + 修復測試驗證 | P0 | S | T3.01-T3.06 | 測試 |

---

## 任務詳情

### T3.01 — Session Drawdown Halt 修復（P0 阻塞）

**優先級：** P0 | **工作量：** M | **依賴：** 無

#### 問題
`test_session_drawdown_halts` 失敗。Root cause：`_recompute_pnl()` 在 tick 開始時（line 1311）被調用，它重算 `current_paper_balance_usdt`（line 1418-1420）並同時更新 `peak_balance_usdt`（line 1424-1426）。問題是重算公式可能未正確反映已實現虧損。

測試流程：
1. 初始餘額 10000
2. Buy 0.1 BTC @ 60000（margin = 6000/1 = 6000）
3. Sell 0.1 BTC @ 55000（realized loss = -500）
4. tick(55000) — 期望 drawdown = 500/10000 = 5% > 2% → session_halted=True
5. 實際：session_halted 未設定

#### 具體修改

**文件：** `app/paper_trading_engine.py`

1. **調試第一步：** 在 `_recompute_pnl()` 末尾（line 1426 後），加入日誌：
   ```python
   logger.debug("_recompute_pnl: initial=%s, realized=%s, fees=%s, current=%s, peak=%s",
       initial, realized, total_fees,
       state["session"]["current_paper_balance_usdt"],
       state["session"].get("peak_balance_usdt"))
   ```

2. **檢查 `_recompute_pnl()` 計算公式（line 1418-1420）：**
   ```python
   current = initial + realized_pnl - total_fees
   ```
   這裡 `realized_pnl` 包含 `closed_position_pnl`（line 1382），確認 sell at loss 後 `closed_position_pnl` 正確包含 -500。

3. **確認 peak 追蹤邏輯（line 1424-1426）：**
   peak 只在 `current > peak` 時更新（新高）。如果重算後 current < peak，peak 應保持 10000。確認沒有其他路徑覆蓋 peak。

4. **修復方案 A（最可能）：** `closed_position_pnl` 在 sell 後未正確累加。檢查 `project_position_after_fill()` 返回的 `close_pnl` 是否正確寫入 state。

5. **修復方案 B：** Drawdown 檢查時機問題。確保 tick mutator 中 `_recompute_pnl(state)`（line 1311）更新 balance 後，drawdown 檢查（line 1352-1361）讀取的是更新後的值。

#### 驗收標準
1. `test_session_drawdown_halts` PASS
2. 不影響其他已通過測試

---

### T3.02 — Daily Loss Pre-Order Check 修復（P0 阻塞）

**優先級：** P0 | **工作量：** M | **依賴：** 無

#### 問題
`test_daily_loss_blocks_and_closes` 失敗。Daily loss check（risk_manager.py line 642-645）條件是：
```python
if stored_date == today_str and daily_start > 0 and balance_now < daily_start:
```

可能原因：
1. `daily_start_date` 未在 session start 時設置（沒有 stored_date 匹配 today）
2. `daily_start_balance_usdt` 未初始化
3. 重算 PnL 後 balance 覆蓋了 `project_balance_after_fill` 的結果

#### 具體修改

**文件 1：** `app/paper_trading_engine.py`
- 在 `start_session()` 中（line 708-728），確保初始化：
  ```python
  state["session"]["daily_start_balance_usdt"] = initial_balance
  state["session"]["daily_start_date"] = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
  ```

**文件 2：** `app/risk_manager.py`
- 在 `check_order_allowed()` 的 daily loss check（line 637-645），加入調試日誌
- 確認 `stored_date == today_str` 條件在測試環境下為 True

#### 驗收標準
1. `test_daily_loss_blocks_and_closes` PASS
2. Daily loss > max → 新開倉被拒
3. 允許減倉/平倉

---

### T3.03 — ProtectiveOrderManager.check_triggers() 接入 tick

**優先級：** P1 | **工作量：** S | **依賴：** T2.03

#### 問題
`ProtectiveOrderManager` 已注入 Engine，但 `check_triggers()` 從未在 tick 中被調用。保護性訂單（包括 HARD_STOP_LOSS）永遠不會觸發。

#### 具體修改

**文件：** `app/paper_trading_engine.py`

在 tick mutator 的風控檢查之後（line 1350 後、drawdown check 之前），添加：
```python
# T3.03: Check protective orders on tick (last line of defense)
if self._protective_order_manager:
    try:
        market_state = {sym: {"price": p} for sym, p in market_prices.items()}
        pom_result = self._protective_order_manager.check_triggers(market_state)
        if pom_result and pom_result.triggered_orders:
            for trig_order in pom_result.triggered_orders:
                self._audit(state, "protective_order_triggered",
                    f"{trig_order.symbol} type={trig_order.order_type.value} trigger_price={trig_order.trigger_price}")
    except Exception as e:
        logger.error(f"ProtectiveOrderManager check_triggers error: {e} (non-fatal)")
```

#### 驗收標準
1. tick 時 check_triggers 被調用
2. 硬止損觸發產生審計記錄
3. 不影響現有測試

---

### T3.04 — Daily Loss Session Halt 行為一致性

**優先級：** P1 | **工作量：** S | **依賴：** T3.02

#### 問題
Daily loss auto-close（risk_manager.py line 969）平倉但不 halt session。Pre-order check（line 642-645）阻止新開倉。兩者行為不一致。

#### 具體修改

**文件：** `app/risk_manager.py`
在 daily loss 自動平倉後（line 969-978），添加 session halt 標記：
```python
# After force-closing positions for daily loss, halt session
sess["session_halted"] = True
sess["session_halt_reason"] = f"daily_loss_{daily_loss_pct:.1f}pct"
```

這確保 daily loss 既平倉又阻止後續交易。

#### 驗收標準
1. Daily loss 超限 → 平倉 + session_halted=True
2. 與 drawdown halt 行為一致

---

### T3.05 — ScannerRateLimiter 注入 PipelineBridge

**優先級：** P2 | **工作量：** S | **依賴：** T2.07

#### 問題
`SCANNER_RATE_LIMITER` 已在 `paper_trading_routes.py` 創建，`PipelineBridge` 已有 `set_scanner_rate_limiter()` 方法和 `can_scan()` 調用，但 `phase2_strategy_routes.py` 缺少注入調用。

#### 具體修改

**文件：** `app/phase2_strategy_routes.py`
在 PerceptionPlane 注入之後（line 225 後），添加：
```python
# --- T3.05: ScannerRateLimiter injection ---
try:
    from .paper_trading_routes import SCANNER_RATE_LIMITER as _SCANNER_RATE_LIMITER_REF
    if PIPELINE_BRIDGE is not None and _SCANNER_RATE_LIMITER_REF is not None:
        PIPELINE_BRIDGE.set_scanner_rate_limiter(_SCANNER_RATE_LIMITER_REF)
        logger.info("ScannerRateLimiter injected into PipelineBridge / 掃描限速器已注入管線橋接器")
except ImportError as e:
    logger.warning("Could not import SCANNER_RATE_LIMITER: %s", e)
```

#### 驗收標準
1. PipelineBridge._scanner_rate_limiter is not None
2. 掃描間隔 < 5min 被阻止

---

### T3.06 — ChangeAuditLog 擴展記錄範圍

**優先級：** P2 | **工作量：** M | **依賴：** T2.04

#### 問題
ChangeAuditLog 目前只記錄 2 個事件（GovernanceHub cascade）。重要治理事件未記錄。

#### 具體修改

**文件 1：** `app/risk_manager.py`
- 在 `update_global_config()` 中記錄配置變更
- 在 session halt 時記錄

**文件 2：** `app/paper_trading_engine.py`
- 在 session halt（drawdown/daily loss）時記錄

**注意：** 使用 try/except 包裝所有 ChangeAuditLog 調用，non-fatal。

#### 驗收標準
1. 配置變更產生 ChangeRecord
2. Session halt 產生 ChangeRecord
3. 不影響現有邏輯

---

### T3.07 — Phase 3 回歸測試 + 修復驗證

**優先級：** P0 | **工作量：** S | **依賴：** T3.01-T3.06

#### 驗收標準
1. `test_session_drawdown_halts` PASS
2. `test_daily_loss_blocks_and_closes` PASS
3. 全套測試 0 failures（排除已知非 Phase 3 問題）
4. Phase 2 集成測試（23 用例）繼續 PASS

---

## 工作流編排

Phase 3 全部使用 **單一 Worker-Alpha 順序執行**（避免 Phase 2 的並行推送衝突）。

### 執行順序

```
T3.01 (P0) → T3.02 (P0) → T3.03 (P1) → T3.04 (P1) → T3.05 (P2) → T3.06 (P2) → T3.07 (回歸)
```

每個任務完成後立即 commit + push + 驗證。

---

*Phase 3 任務書由 PM（via Cowork PM）於 2026-03-30 產出*

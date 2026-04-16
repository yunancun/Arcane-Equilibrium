# SCANNER-GATE Death Loop Fix — 2026-04-17

## 問題

策略在 scanner 輪替出的 symbol 上反復開倉 → orphan_handler A4 強平 → 策略再開 → 無限死循環。
BASEDUSDT 為首例但影響 20+ symbols（ENJUSDT 45 筆、CLUSDT 28 筆、AAVEUSDT 23 筆等，共 228 筆 `ipc_close_symbol` fills）。

### 根因

1. **orphan_handler A4 語義錯誤**：把「scanner 輪替掉的持倉」當作 orphan 強平。但 orphan 應只指「重啟/故障後遺留的舊倉位」
2. **新開倉無 scanner gate**：tick_pipeline 策略 Open dispatch 不檢查 symbol 是否在 scanner 活躍集合，所以被輪替出的 symbol 照常開倉
3. **FUP race condition**：REST 下單到 WS Fill 回報之間的空窗期，reconciler 讀 mirror 看不到新倉 → 誤判為 orphan

### DB 證據

```sql
-- 228 筆 ipc_close_symbol fills across 20+ symbols
SELECT symbol, COUNT(*) FROM trading.fills
WHERE strategy = 'ipc_close_symbol' AND ts >= NOW() - INTERVAL '24h'
GROUP BY symbol ORDER BY count DESC;

-- engine_events 顯示 hard_safety_not_in_universe 和 soft_conservative stages
SELECT payload->>'stage', COUNT(*)
FROM observability.engine_events
WHERE event_type = 'orphan_handled'
GROUP BY 1;
```

## 修復（三部分）

### Fix 1: SCANNER-GATE — tick_pipeline 新開倉門控
- `tick_pipeline/mod.rs`: 新增 `symbol_registry: Option<Arc<SymbolRegistry>>` 字段 + `set_symbol_registry()` setter + `with_balance()` init
- `on_tick.rs`: strategy Open dispatch 前加 `reg.is_active(symbol)` 檢查，非活躍 symbol `continue`
- `event_consumer/mod.rs`: bootstrap 時 wire `Arc::clone(reg)` 到 pipeline

### Fix 2: FUP-RACE — proactive mirror insert
- `paper_state.rs`: 新增 `proactive_mirror_insert(&self, symbol, is_long)` — 寫 mirror 不動 positions
- `on_tick.rs`: exchange OrderDispatchRequest 發送後立即呼叫，彌合 REST→WS 空窗

### Fix 3: A4 移除 — orphan 定義修正
- `orphan_handler.rs`: Stage A4 邏輯刪除（enum 變體 `HardSafetyNotInUniverse` 保留 DB backward compat）
- 模組文檔 + 2 個 A4 測試更新為驗證 fall-through 到 SoftConservative
- orphan 定義回歸正確語義：僅指重啟後遺留舊倉位

## 改動檔案

| 文件 | 改動 |
|---|---|
| `tick_pipeline/mod.rs` | +field `symbol_registry` +setter +init |
| `tick_pipeline/on_tick.rs` | +scanner gate (Open前) +proactive mirror (OrderDispatch後) |
| `paper_state.rs` | +`proactive_mirror_insert()` |
| `orphan_handler.rs` | -A4 logic +doc update +2 test updates |
| `event_consumer/mod.rs` | +registry wiring |
| `TODO.md` | +P0-10 條目 + test baseline 1342→1351 |

## 測試

- engine lib: **1351 passed / 0 failed** (was 1342 — 增 9 tests from prior P0-5 deploy batch)
- orphan_handler: 17/17 passed（含 2 個更新的 A4 測試）
- core: 380 passed

## 部署

`restart_all.sh --rebuild` 於 2026-04-17 執行。

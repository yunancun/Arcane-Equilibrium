# Session 13 Pre-Compact Snapshot

日期：2026-04-06（Session 12 之後接續）
最後 commit：`0d52577`（已 push）
測試基準線：**471 engine + 413 core + 35 ml_training + 11 control_api smoke** · 0 failures

## Session 13 完成項（時間順序）

| # | 工作 | Commit | Δ Tests |
|---|---|---|---|
| 1 | I-22 event_consumer/mod.rs 802 → 628（dispatch.rs + setup.rs 提取）| `e69191d` | — |
| 2 | FA-GAP-2/4: cost_ratio 接線 + Kelly ATR% 接線（殺 placeholder）| `b8562d1` | — |
| 3 | per-symbol 真實費率（AccountManager Arc plumb 到 intent_processor）| `6e94c11` | — |
| 4 | refresh task 加固（cancel-aware + 6h interval + 12h staleness 監控 + V008 fills.fee_rate）| `d2b630c` | — |
| 5 | SEC-11 cost gate ATR=0 改 fail-closed | `40dd189` | engine +1 |
| 6 | GAP-8/9: IPC stub 全刪 + bb_reversion use_limit 從 ranges 移除並強制 false | `402f646` | engine -3 |
| 7 | Idle writer #3 liquidations dead infra 全刪 | `0d52577` | engine -1 |

**Push 範圍**：`e69191d..0d52577`（7 commits 全部 push）
**測試淨變**：engine 474 → **471**（-3 = 1 SEC-11 新測試 + 4 dead test 刪除）· core 413 不變

## 關鍵決策

1. **GAP-2 cost_ratio 公式**：`200 × fee_rate / pnl_pct`，pnl ≤ 0 時跳過。fee=0.055% 時 pnl 跌到 ~0.14% 會觸發鎖利平倉
2. **GAP-4 Kelly ATR%**：用 on_tick 已傳入的真實 `atr` 參數計算 `atr/price`，不再用 paper_state.latest_turnover 的 placeholder
3. **REFERENCE_ATR_PCT = 0.02 不是 magic number**：是 vol-multiplier 歸一化錨點（典型 perp 5m ATR 1-4% 區間，2% 設為穩態 1.0），加 const + doc 解釋
4. **fee_rate 三層 fallback**：`AccountManager.taker_fee(symbol)` → legacy 單一 rate → `DEFAULT_TAKER_FEE_RATE` 常量（cold-boot 不可消除，是 Bybit 公開協議值）
5. **SEC-11 fail-closed 而非 fail-open**：cold start 由 PNL-3 boot cooldown 接住，runtime ATR=0 是異常狀態應拒絕
6. **GAP-8 兩個 IPC stub 直接刪光**：Python `ipc_client.py` 有 wrapper 但 0 caller，wrapper 寫的是 `strategist_evaluate`（跟 Rust 那邊名字都對不上），純 dead code
7. **GAP-9 雙保險**：bb_reversion `use_limit` 從 `param_ranges` 移除（agent 看不到）+ `update_params` 強制 coerce false（防 stale config / 直接構造 path）+ field 保留向後相容
8. **idle writer #3 直接刪掉而非保留**：market.liquidations 表無下游 consumer，writer 也無 producer，topic 訂閱會 poison WS。表保留，writer/Msg/topic 函數全刪

## 文件變更摘要（Session 13）

**新建：**
- `rust/openclaw_engine/src/event_consumer/dispatch.rs`（I-22 拆分）
- `rust/openclaw_engine/src/event_consumer/setup.rs`（I-22 拆分）
- `sql/migrations/V008__fills_fee_rate.sql`（fee_rate 列）
- `docs/worklogs/2026-04-06--session13_precompact.md`（本文件）

**修改：**
- `rust/openclaw_engine/src/event_consumer/mod.rs` 802 → 628 行（I-22）
- `rust/openclaw_engine/src/event_consumer/types.rs`（+account_manager 欄位）
- `rust/openclaw_engine/src/intent_processor.rs`（+account_manager / fee_rate(symbol) / SEC-11 fail-closed × 2 處 / GAP-4 atr 接線 × 2 處）
- `rust/openclaw_engine/src/tick_pipeline.rs`（GAP-2 cost_ratio + set_account_manager forwarder + 3 個 Fill emit 加 fee_rate）
- `rust/openclaw_core/src/risk/checks.rs`（無，cost_ratio 計算移到 caller）
- `rust/openclaw_engine/src/account_manager.rs`（+last_fee_refresh_ms atomic + getter + stamp on success）
- `rust/openclaw_engine/src/main.rs`（Arc<AccountManager> 保活 + 6h cancel-aware refresh task + 12h staleness monitor + extended_subscription_list 改 full_subscription_list）
- `rust/openclaw_engine/src/database/mod.rs`（-Liquidation variant + Fill +fee_rate）
- `rust/openclaw_engine/src/database/market_writer.rs`（-flush_liquidations + 分發）
- `rust/openclaw_engine/src/database/trading_writer.rs`（INSERT 加 fee_rate）
- `rust/openclaw_engine/src/multi_interval_ws.rs`（-3 個 dead topic 函數 + -3 個 enum variants + -extended_subscription_list）
- `rust/openclaw_engine/src/ipc_server.rs`（-handle_evaluate_strategy + -handle_get_risk_check + -3 TTL constants + -3 dead tests）
- `rust/openclaw_engine/src/ml/kelly_sizer.rs`（REFERENCE_ATR_PCT/VOL_MULT_FLOOR/CEIL 命名常量 + doc）
- `rust/openclaw_engine/src/strategies/bb_reversion.rs`（GAP-9 lock）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py`（-evaluate_strategy + -get_risk_check 兩個 dead wrapper）
- `docs/references/2026-04-04--bybit_api_reference.md`（liquidation 函數標記為已刪除）
- `TODO.md`（R3 backlog 標完成）
- `CLAUDE.md`（§三 Session 13 摘要 + §十一 一句話狀態）
- `README.md`（當前狀態 + 測試基準線 + 下一步）

**Memory cleanup（同期執行）：**
- 刪除：`project_agent_strategy_gap.md` / `project_20260327_session.md` / `project_test_debt_zero.md` / `project_fa_gap_audit.md`
- 更新：`project_rust_migration_status.md`（R-07 PASS）
- 新增：`feedback_pushback.md`（主動指出 operator 錯誤，協作者非執行者）

## DB 變動（live 已 apply）

```
trading.fills.fee_rate REAL DEFAULT 0  ✓ ALTER TABLE 已執行
```

新 binary 部署後：fills 開始記錄真實 per-symbol fee_rate（V008 即時生效）

## R3 Backlog 終態

| 類別 | 狀態 |
|---|---|
| FA GAP-1/2/3/4/5/6/7 | ✅ 已完成（GAP-2/4 在 Session 13 完成）|
| FA GAP-8/9 | ✅ Session 13 已刪/已 lock |
| FA GAP-10 LLM pricing table | ⏸ Phase 4（等 LLM cost tracking 真實啟用）|
| SEC-11 cost gate ATR=0 | ✅ Session 13 fail-closed |
| SEC-05 GUI XSS 16/133 | ⏸ live-prep（架構性大改）|
| SEC-09/17/21 | ⏸ live-prep / by-design |
| Idle writer #1/#2/#3/#5/#6 | ✅ 全部已調查 + 處理 |
| I-22 event_consumer 精簡 | ✅ 802 → 628 |
| WP-E4/T-P1-1 殘餘 | ⏸ 獨立 sprint |
| WP backlog 223 子項 | ⏸ 填空可選 |

**R3 排除 WP / SEC live-prep / Phase 4 後全部清空。**

## 下一步候選（按優先度）

1. **Phase 4 啟動** — Claude Teacher + LinUCB + News + DL-3（W13-15 規模）
2. **WP backlog 填空** — 223 子項，可分批處理
3. **SEC live-prep** — 等 live 時程確定後再動

## Compact 後接手指引

1. 讀 `TODO.md` 找下一個 `[ ]`（R3 已清空，建議直接看 Phase 4 段）
2. 確認當前 commit 是 `0d52577`：`git log --oneline -1`
3. 確認測試基準線：`cd rust && cargo test -p openclaw_engine -p openclaw_core 2>&1 | grep "test result"`
4. 如需歷史細節：本文件 + `docs/worklogs/2026-04-06--session12_precompact.md`
5. **重要**：CLAUDE.md §三 + §十一 已同步 / TODO.md 已標完成 / README.md 已更新 / 無孤兒狀態
6. **新 memory 注意**：`feedback_pushback.md` — 接手後請主動指出 operator 錯誤，不當應聲蟲

# E1 — F4 trading_writer LIVE WS fills audit + ML pipeline filter

任務日：2026-04-26（branch / commit 落地時間） · 報告寫成於 2026-04-27

Branch: `e1-f4-trading-writer-live-isolated`（commit `53973ef`，已 push）
Worktree: `/Users/ncyu/Projects/worktree-e1-f4-isolated`
PA design: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--three_p0_fixes_design.md` § F4

---

## 1. 任務摘要

Operator 意圖：今天 (2026-04-26) MIT + E5 跨表 audit 揭發 P0 silent regression — engine.log 在 16:00 UTC 顯示 3 條真 LIVE WS fills（ETHUSDT / DOGEUSDT / SOLUSDT，maker rebate negative fee），但 `trading.fills` 過去 7d **0 條 live / 0 條 live_demo**。WS 進來了但 writer 沒寫 = silent regression。PA design 揭真實 drop 點不在 trading_writer（writer 對 engine_mode 無 filter），而在更上游 `event_consumer/loop_handlers.rs:555-560` 的 `else { warn!(); }` branch — 未匹配 PendingOrder 的 WS fill 被 silent return。

Fix：F4-1 對 unmatched fill 落 `unattributed:bybit_auto` audit row（live/live_demo/demo only，paper 排除）+ F4-2 ML pipeline `WHERE strategy_name NOT LIKE 'unattributed:%'` 過濾 + F4-3 unit + integration test。

完成狀態：F4-1 + F4-2 + F4-3 三子任務全落地；branch pushed；Mac cargo debug + Linux cargo release + Linux pytest 三方驗證綠。等待 E2 review → E4 regression → PM commit + push fast-forward merge。

---

## 2. 修改清單

| Path | 動作 | 行數 | 一句話說明 |
|---|---|---|---|
| `rust/openclaw_engine/src/event_consumer/loop_handlers.rs` | 修改 | +160 / -2 | F4-1 主 fix：抽 `try_emit_unattributed_fill` 共用 fn + `engine_mode_emits_unattributed_audit` allowlist；555-560 else branch 從 silent warn 改為 audit row emit。 |
| `rust/openclaw_engine/src/event_consumer/tests/mod.rs` | 修改 | +3 | 註冊新 sibling 測試模組 `unattributed_fill_tests`。 |
| `rust/openclaw_engine/src/event_consumer/tests/unattributed_fill_tests.rs` | 新增 | +388 | F4-3 Rust unit tests 15 個（engine_mode allowlist × 6 + emit positive × 3 + emit negative × 5 + ML filter prefix × 1）。 |
| `program_code/ml_training/realized_edge_stats.py` | 修改 | +8 | F4-2 `_FILLS_QUERY` 加 `strategy_name NOT LIKE 'unattributed:%%'` filter。 |
| `program_code/ml_training/edge_label_backfill.py` | 修改 | +28 | F4-2 `_BACKFILL_INCLUDED_SQL` 3 個 JOIN 處 + `_BACKFILL_EXCLUDED_SQL` close-side 全加 audit filter。 |
| `program_code/ml_training/parquet_etl.py` | 修改 | +7 | F4-2 `extract_training_data` fills_query DuckDB SQL 加單 `%` filter。 |
| `program_code/ml_training/dl3_ab_runner.py` | 修改 | +4 | F4-2 docstring schema-assumption 加 audit filter（fetch_training_dataset 為 stub，留契約）。 |
| `program_code/audit/counterfactual_exit_audit.py` | 修改 | +7 | F4-2 `_FILLS_QUERY` 同樣加 audit filter（隔壁 audit 模組讀 trading.fills 算 PnL）。 |
| `program_code/ml_training/tests/test_unattributed_filter.py` | 新增 | +277 | F4-3 Python tests 7 個（4 SQL string assertions + 1 docstring contract + 1 NULL tolerance + 1 integration mock end-to-end）。 |

合計：9 檔 / +882 / -2

---

## 3. 關鍵 diff

### 3.1 F4-1 主 fix（loop_handlers.rs:555 else branch）

修前：
```rust
} else {
    tracing::warn!(
        symbol = %exec.symbol, side = %exec.side,
        "exchange fill has no matching pending order / 交易所成交無匹配的待處理訂單"
    );
}
```

修後（節錄）：
```rust
} else {
    // F4-1 (2026-04-26): unmatched WS fill audit row.
    // Pre-fix: silent `warn!()` + drop. LIVE/LiveDemo Bybit auto-actions
    // (funding payment / dust scrub / auto-补单) reach here because
    // ExecutorAgent shadow_mode=true emits 0 SubmitOrder → 0 PendingOrder
    // → 100% unmatched. Result: 0 rows in trading.fills for live/live_demo
    // over 7d while engine.log shows real fills.
    let em = pipeline.effective_engine_mode();
    let emitted = try_emit_unattributed_fill(
        em, &exec.exec_id, exec_ts, &exec.order_id, &exec.symbol,
        &exec.side, exec_qty, exec_price, exec_fee, order_tx,
    );
    tracing::warn!(
        symbol = %exec.symbol, side = %exec.side, exec_id = %exec.exec_id,
        engine_mode = %em, audit_emitted = emitted,
        "F4-1: exchange fill has no matching pending order — \
         audit row {} / 交易所成交無匹配 pending order — audit row {}",
        if emitted { "emitted" } else { "skipped (paper/test)" },
        if emitted { "已落" } else { "已跳過（paper/test）" }
    );
}
```

### 3.2 F4-1 共用 helper

```rust
/// Engine modes that should emit an `unattributed:bybit_auto` audit row.
#[inline]
pub(super) fn engine_mode_emits_unattributed_audit(em: &str) -> bool {
    matches!(em, "live" | "live_demo" | "demo")
}

#[allow(clippy::too_many_arguments)]
pub(super) fn try_emit_unattributed_fill(
    engine_mode: &str,
    exec_id: &str,
    exec_ts_ms: u64,
    order_id: &str,
    symbol: &str,
    side: &str,
    qty: f64,
    price: f64,
    fee: f64,
    order_tx: Option<&tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
) -> bool {
    if !engine_mode_emits_unattributed_audit(engine_mode) {
        return false;
    }
    let tx = match order_tx { Some(t) => t, None => return false };
    let msg = crate::database::TradingMsg::Fill {
        fill_id: format!("unattrib-{}", exec_id),
        ts_ms: exec_ts_ms,
        order_id: order_id.to_string(),
        symbol: symbol.to_string(),
        side: side.to_string(),
        qty, price, fee,
        fee_rate: 0.0,
        realized_pnl: 0.0,
        strategy_name: "unattributed:bybit_auto".to_string(),
        context_id: format!("unattrib-{}-{}", exec_id, exec_ts_ms),
        entry_context_id: String::new(),
        engine_mode: engine_mode.to_string(),
        exit_source: None,
    };
    tx.try_send(msg).is_ok()
}
```

### 3.3 F4-2 SQL filter（realized_edge_stats）

```sql
FROM trading.fills f
WHERE f.ts >= %(since)s
  AND f.engine_mode = %(engine_mode)s
  -- F4-2 (2026-04-26): exclude `unattributed:bybit_auto` audit rows
  AND (f.strategy_name IS NULL OR f.strategy_name NOT LIKE 'unattributed:%%')
ORDER BY f.symbol, f.ts ASC
```

`%%` 是 psycopg2 pyformat (`%(name)s` paramstyle) 對字面 `%` 的轉義。同模式套用 edge_label_backfill 3 處 JOIN + counterfactual_exit_audit 1 處。parquet_etl 用 DuckDB SQL 不需要 escape。

---

## 4. 治理對照

涉及的 16 原則：

| 原則 | F4 影響 |
|---|---|
| #1 單一寫入口 | ✅ unattrib row 經 trading_writer 唯一寫入路徑 |
| #2 讀寫分離 | ✅ ML reader 純加 filter，無新寫入路徑 |
| #4 策略不繞風控 | ✅ unattrib 不算 strategy（不經 Guardian / IntentProcessor）|
| #5 生存 > 利潤 | ✅ 強化（從前 silent drop → 現有 audit trail 可重建 LIVE 流量）|
| #6 失敗默認收縮 | ✅ engine_mode allowlist + None tx + try_send 飽和 = fail-soft；audit 無法寫不阻塞主路徑 |
| #7 學習 ≠ 改寫 Live | ✅ ML filter 阻止 Bybit 自主動作污染訓練資料；live trading 完全不受影響 |
| #8 交易可解釋 | ✅ unattrib row 可重建（fill_id `unattrib-{exec_id}` + context_id 唯一 + Bybit 自主動作有日期/symbol/side/qty/price/fee）|
| #10 認知誠實 | ✅ 不掩蓋根本問題：strategy_name = `unattributed:` 顯式標記源頭；後續 ExecutorAgent shadow→live (G3-02) 是另一獨立 ticket |

不觸碰 §四 5 項 live 硬邊界（`live_execution_allowed` / `max_retries` / Mainnet env / authorization.json / Operator auth）。

文件規範：

- ✅ MODULE_NOTE 雙語 / 函數 docstring 中英對照（CLAUDE.md §七）
- ✅ 所有新 fn / 新 test 文件 / 新 SQL filter 都帶中英 inline 注釋（fail-closed 路徑明示）
- ✅ §七「不可改硬邊界」清單未觸碰
- 觸發 §九 文件大小限制？loop_handlers.rs 由 1108 → 1268 行，**已超 1200 硬上限 60 行**。注意：該檔已經在 F3 動到（status arm region ~line 1108），且這是 deeply private file 持續累積 fix；split 是另一個 refactor ticket（G5-07 已拆 1298→1012 是 mod.rs，本檔是 sibling）。**E2 必裁定**：是否本 PR 順手 split 還是留 follow-up ticket。

---

## 5. 不確定之處

1. **檔案大小越過 1200 上限**：`loop_handlers.rs` 被 F4-1 拉到 1268 行（事前 1108）。CLAUDE.md §九「1200 行硬上限不允許 merge」。但本 PR scope 不擴張，split 屬重構工作另設 ticket（同 G5-07 模式）。E2 拍板。
2. **`live_testnet` 是否也應 emit**：PA design § 2.2.1 + §2.4.1 明示 `live | live_demo | demo` 三項，testnet 排除（"no real flow runs on testnet today"）。我跟 PA design。若未來 testnet 啟流量，加一行 enum match 即可；所有 unit test 已預測該行為（`test_no_emit_for_live_testnet_engine_mode`）。
3. **`fee` 為負（maker rebate）的精度**：unit test `test_emit_for_live_engine_mode_writes_audit_row` 驗 fee=-0.001 原樣保留；但 trading_writer L305 `b.push_bind(sanitize_f64_or_zero(*fee) as f32)` 把 f64 cast 到 f32，精度損失 ~7 位有效數位。Bybit fee 量級 ~$0.0001-$1.0，f32 仍有 6-7 位精度，足夠 audit purpose。**E2 確認**：是否需要為 audit row 開 f64 列（trading.fills 既有 schema 是 REAL = f32，改 schema 是 V025+ migration scope，不在 F4 範圍）。
4. **與 F3 / F6 cohesive deploy**：F4-1 改 555-560 else branch；F3-3 改 ~line 354 status arm reaper；F6 改 main_boot_tasks.rs。三者 PA design 預期同 wave 一起 land，但目前 F3 / F6 在不同 isolated worktree branch。E2 / PM 排序：是先 merge F4 → 後 cohesive merge F3 / F6，還是 一起 fast-forward merge 一個 cumulative branch。
5. **歷史 LIVE WS fills 回填**：PA design § 2.2.1 範圍外（"P3 backlog"）— engine.log 16:00 UTC 已有 3 條真 fills 但 DB 0 行。F4-1 上線後**只**修未來流量，過去 7d 的 3 條仍漏。Operator 是否要派 BB / MIT 寫 grep + 手動 INSERT 腳本？

---

## 6. Operator 下一步

### 審查重點

1. **E2 必查**：(a) `engine_mode_emits_unattributed_audit` allowlist 與 §三 engine_mode_tag schema 對齊（live/live_demo/demo/paper/live_testnet 五種）(b) ML filter 不漏任何 trading.fills consumer — 我已檢過 `program_code/ml_training/*` + `program_code/audit/*` + `helper_scripts/db/passive_wait_healthcheck/*` + `helper_scripts/research/ma_crossover_counterfactual_replay.py` + `helper_scripts/db/counterfactual_exit_replay.py`，剩 GUI route（live_session_account_routes / paper_trading_routes / paper_trading_metrics / strategy_ai_routes / strategist_history_routes / strategy_read_routes）— **GUI 不算 ML pipeline，不在 F4 範圍**，但 E2 確認 (c) `loop_handlers.rs` 1268 行超 1200 上限是否本 PR 處理。
2. **E2 對抗性審查**：grep `unattrib-` 確保 fill_id collision 與 Bybit 合法 fill_id 不衝突（已檢：無）；grep `'unattributed:%'` 在所有 trading.fills 讀者驗 filter 完備。
3. **E4 regression**：cargo test --release lib（已驗 Linux 2227/0 fail）+ pytest（30 tests passed Linux）+ healthcheck dry-run 確認既有 19 check 仍綠（未動 healthcheck，但 SQL 改動後 cron 6h 後可看到 trading.fills `unattrib-` rows）。

### Mac CC 透過 SSH bridge 已做的驗證

1. **Mac cargo test --lib**: `2227 passed / 0 failed`（baseline 2161 + 15 new F4-1 tests + 51 from main since branch）。
2. **Linux cargo test --release --lib**: 同 `2227 passed / 0 failed`（透過 `ssh trade-core` worktree 隔離跑，drop 後清理）。
3. **Linux pytest**: 30 passed（test_unattributed_filter 7 + test_realized_edge_stats_mode 6 + test_edge_label_backfill 13 + test_counterfactual_exit_audit 4）— 全綠。
4. **Mac pytest**: 同 30 個 tests 全綠（Mac dev 環境 numpy 缺失導致 `test_dl3_ab_runner.py::test_run_ab_test_sklearn_unavailable_fail_soft` pre-existing fail，已 git stash 驗證與 F4 無關）。
5. **Branch push**: `git push -u origin e1-f4-trading-writer-live-isolated` 成功，origin synced。

### 若需 operator 親自動手

1. **PM commit + push fast-forward merge**：等 E2 review pass + E4 regression 綠後，PM merge `e1-f4-trading-writer-live-isolated` → main fast-forward。
2. **`restart_all.sh --rebuild` 部署**：F4-1 是 Rust binary 改動，**需重 build 才生效**；F4-2 SQL filter 是 Python 改動，uvicorn worker 自動 reload（routes 走 `--reload` flag 時）但 ML 訓練 pipeline 是離線命令，下次 `python -m program_code.ml_training.run_training_pipeline` 自動 pick 新 SQL。
3. **驗證 24h 後**：cron 6h healthcheck 觀察是否有新 `unattrib-*` rows 出現在 `trading.fills`（live_demo engine_mode）；7d 內 funding payment 應產生 ~3 條/天 × 1+ symbol = ~21+ rows。若 0 rows = drop 復發或 Bybit auto-action 暫停，需 grep engine.log 找 `F4-1: exchange fill has no matching` warn 條目。
4. **歷史回填決策**：engine.log 16:00 UTC 的 3 條真 LIVE WS fills（ETHUSDT/DOGEUSDT/SOLUSDT）已永久 drop（log only），是否要派 BB / MIT 寫腳本掃 engine.log 反向回填 trading.fills `unattrib-` rows？PA design 標 P3 backlog，operator 決定。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--f4_trading_writer_live.md`，branch `e1-f4-trading-writer-live-isolated` commit `53973ef` pushed）

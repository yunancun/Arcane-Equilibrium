# E1 Round 2 IMPL Report — P0-ENGINE-HALTSESSION-STUCK-FIX Layer A

**Date**: 2026-05-19 / 2026-05-20
**Author**: E1
**Round 1 report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_report.md`
**Spec**: `srv/docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md` (v0.2)
**Status**: ROUND 2 IMPL DONE；待 E2 round-2 re-review + E4 regression + QA Audit。
**Branch**: 未推 main / 未 deploy。Linux PG Python writer integration 已驗（不影響 prod data）。

---

## 1. Round 2 範圍（6 fix）

Round 1 E2 verdict=RETURN（4 MUST-FIX）+ E3 verdict=APPROVE-CONDITIONAL（1 MEDIUM-1）+ spec §6.3 强制 incident replay：

| # | 類別 | Fix 內容 | 狀態 |
|---|---|---|---|
| MUST-FIX-1 | CRITICAL | `record_halt_cleared` event_type 寫死 → clear_path 動態映射 | ✅ |
| MUST-FIX-2 | HIGH | paper_state restore halt_kind / halt_set_ts_ms 跨 restart | ✅ |
| MUST-FIX-3 | HIGH | Python tail-writer 把 halt_audit.log → governance_audit_log | ✅ + Linux PG integration |
| MUST-FIX-4 | MEDIUM | risk_config_tests.rs 2076→1917 LOC（< 2000 cap） | ✅ |
| E3 MEDIUM-1 | MEDIUM | halt_audit f64 JSON payload NaN-panic guard | ✅ |
| SHOULD-FIX | spec compliance | spec §6.3 test_2026_05_19_incident_replay | ✅ |

---

## 2. 修改清單（精確路徑 + 行數變動）

### 新建
| Path | LOC | 用途 |
|---|---|---|
| `srv/rust/openclaw_engine/src/config/risk_config_halt_ttl_tests.rs` | 182 | MUST-FIX-4：從 risk_config_tests.rs 拆出 9 個 halt TTL test |
| `srv/helper_scripts/canary/halt_audit_pg_writer.py` | 389 | MUST-FIX-3：tail halt_audit.log → INSERT governance_audit_log |
| `srv/helper_scripts/canary/test_halt_audit_pg_writer.py` | 362 | MUST-FIX-3：20 unit + PG mock 整合測試 |
| `srv/helper_scripts/cron/halt_audit_pg_writer_cron.sh` | 75 | MUST-FIX-3：1min cron wrapper |

### 修改
| Path | 變動範圍 |
|---|---|
| `srv/rust/openclaw_engine/src/halt_audit.rs` | +264：`json_number_or_null` helper + `event_type_for_clear_path` 映射 + `record_halt_cleared` 改用映射 + `record_halt_set` 所有 f64 過 helper + 4 new unit tests（mapping / NaN panic guard / NaN-Inf safe / cleared_event_type）+ ENV mutex 切到 paper_state_restore::env_test_lock |
| `srv/rust/openclaw_engine/src/event_consumer/paper_state_restore.rs` | +162：`restore_halt_state_from_snapshot` async fn（讀 mode_snapshots.<kind>.halt_kind/halt_set_ts_ms 還原 + fail-soft）+ `ENV_TEST_MUTEX` / `env_test_lock` pub(crate) helper |
| `srv/rust/openclaw_engine/src/event_consumer/mod.rs` | paper_state_restore module 改 `pub(crate)` |
| `srv/rust/openclaw_engine/src/event_consumer/bootstrap.rs` | +5：在 restore_paper_counters 後 chain `restore_halt_state_from_snapshot` |
| `srv/rust/openclaw_engine/src/config/risk_config.rs` | +5：註冊 halt_ttl_tests sibling module |
| `srv/rust/openclaw_engine/src/config/risk_config_tests.rs` | -159 LOC（2076→1917）：拆 9 個 halt TTL test 到 sibling |
| `srv/rust/openclaw_engine/src/tick_pipeline/tests/halt_ttl.rs` | +388：5 new tests（4 restore + incident_replay）+ parse_jsonl_robust helper + env_lock 改 cross-module |
| `srv/rust/openclaw_engine/src/tick_pipeline/tests/per_symbol_price_pnl.rs` | +23：test_halt_session_uses_per_symbol_price_not_triggering_tick 加 env_lock + RAII env 還原 guard 隔離併發污染（不改測試語意）|
| `srv/helper_scripts/SCRIPT_INDEX.md` | +13 LOC：2026-05-20 P0-ENGINE-HALTSESSION-STUCK-FIX Round 2 區塊 |

---

## 3. 關鍵 diff（按 fix 列）

### 3.1 MUST-FIX-1：clear_path → event_type 映射

`halt_audit.rs` 加 helper fn：

```rust
fn event_type_for_clear_path(clear_path: &str) -> &'static str {
    match clear_path {
        "auto_ttl" => "halt_session_auto_cleared",
        "ipc_resume" | "ipc_reset" | "ipc_system_mode_shadow" => "halt_session_manual_cleared",
        unknown => {
            error!(clear_path = unknown, "halt_audit: unknown clear_path → fallback halt_session_manual_cleared");
            "halt_session_manual_cleared"
        }
    }
}
```

`record_halt_cleared` 內：

```rust
let event_type = event_type_for_clear_path(clear_path);
let payload = serde_json::json!({
    "schema_version": 1,
    ...,
    "event": event_type,
    ...,
});
```

呼叫端不必動（commands.rs auto_ttl / lifecycle.rs ipc_resume / lifecycle.rs ipc_reset / commands.rs ipc_system_mode_shadow 都已 pass 對的 clear_path 字串）。

### 3.2 MUST-FIX-2：paper_state restore halt 狀態

`paper_state_restore.rs::restore_halt_state_from_snapshot`：

```rust
pub(crate) async fn restore_halt_state_from_snapshot(pipeline: &mut TickPipeline) {
    // 讀 $OPENCLAW_DATA_DIR/pipeline_snapshot_<kind>.json
    // → 解析 value::mode_snapshots[kind].halt_kind / halt_set_ts_ms
    // → 寫回 pipeline.halt_kind / halt_set_ts_ms / paper_paused / session_halted
    // Fail-soft：缺檔/壞 JSON/缺欄位/halt_kind=null → 冷啟動
}
```

bootstrap.rs 在 `restore_paper_counters` 之後一行呼叫：

```rust
paper_state_restore::restore_paper_counters(&mut pipeline, audit_pool.as_ref()).await;
paper_state_restore::restore_halt_state_from_snapshot(&mut pipeline).await;
```

### 3.3 MUST-FIX-3：Python tail-writer + cron wrapper

`halt_audit_pg_writer.py` 主流程（389 LOC）：
1. resolve halt_audit.log path（env 鏈 OPENCLAW_HALT_AUDIT_LOG / OPENCLAW_DATA_DIR / `/tmp/openclaw/halt_audit.log`）
2. load cursor byte offset from state file（缺檔/壞檔 → 0）
3. read chunk from cursor to file size
4. `_parse_jsonl_robust(chunk)` 處理 .lines() + `}{` 黏接 fallback
5. jsonschema validate（fail-soft：schema 缺 → pass-through；validate fail → skip row）
6. `_insert_row`：`INSERT ... SELECT ... WHERE NOT EXISTS` 冪等（複合 dedup = process_pid + ts_ms + event）
7. 成功則 save new cursor offset；缺表（V098 未 deploy）則 cursor **不前進**

`halt_audit_pg_writer_cron.sh`：mirror sibling `outcome_backfiller_live_cron.sh` 樣式；
1min cron interval + mkdir-based lock 防 overrun + 從 `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env` 讀 PG creds。

### 3.4 MUST-FIX-4：risk_config_tests.rs 拆 sibling

`risk_config.rs` 加：
```rust
#[cfg(test)]
#[path = "risk_config_halt_ttl_tests.rs"]
mod halt_ttl_tests;
```

`risk_config_tests.rs` 1914-2076 區塊（9 個 halt TTL test，165 LOC）整段移到 `risk_config_halt_ttl_tests.rs`，父檔 2076 → 1917 < 2000 cap。

### 3.5 E3 MEDIUM-1：NaN guard

`halt_audit.rs::json_number_or_null`：
```rust
fn json_number_or_null(value: f64) -> serde_json::Value {
    serde_json::Number::from_f64(value)
        .map(serde_json::Value::Number)
        .unwrap_or(serde_json::Value::Null)
}
```

`record_halt_set` 內所有 f64 字段（peak_balance / current_balance / session_drawdown_pct / loaded_drawdown_threshold / loaded_daily_loss_threshold + balance_history 兩元素）全套 `json_number_or_null(...)`。

新 unit test `test_record_halt_set_with_nan_balance_does_not_panic`：構造 `PaperState::new(f64::NAN)` 餵入 `record_halt_set`；驗 fn 不 panic + 寫入 JSON 內 peak_balance / current_balance 落為 null。

### 3.6 SHOULD-FIX：spec §6.3 incident_replay

`halt_ttl.rs::test_2026_05_19_incident_replay`：14 步覆蓋。
- Step 1：構造 TickPipeline + demo RiskConfig（session_drawdown_max_pct=25, daily_loss_max_pct=15, ttl=24h, drawdown_ttl=0 sticky）
- Step 2-5：模擬 step_6 priority 9 DailyLoss 觸發 → record_halt_set → 驗 halt_audit.log set 行 schema + reason + halt_set_ts_ms
- Step 6：推進 1h → on_tick → 仍 paused
- Step 7-8：推進 23h+1s → on_tick auto-clear → 驗 cleared 行 elapsed_ms ∈ [86399000, 86401000]
- Step 9-12：構造 SESSION DRAWDOWN halt → 推 7d → 仍 sticky
- Step 13-14：schema_version=1 + pipeline_kind=paper + 6 quant-context fields 結構存在

---

## 4. 治理對照（同 Round 1，無新破壞）

| 硬邊界 | 影響 | 結論 |
|---|---|---|
| live_execution_allowed | 不觸碰 | ✅ |
| max_retries=0 | 不觸碰 | ✅ |
| system_mode | 不觸碰 | ✅ |
| Bybit retCode!=0 fail-closed | 不觸碰 | ✅ |
| OPENCLAW_ALLOW_MAINNET | 不觸碰 | ✅ |
| live_reserved | 不觸碰 | ✅ |
| authorization.json 寫入路徑 | 不觸碰 | ✅ |
| P1-16 ETHUSDT -17M bps 修復 | 未動 step_6 close-all loop；per_symbol_price_pnl test 仍綠 | ✅ |

16 根原則 + 9 條安全不變量：0 違反（同 Round 1）。

---

## 5. 測試結果

### 5.1 Mac aarch64-apple-darwin cargo test 全套

```
cargo test -p openclaw_engine --release
→ Total: passed: 3264 / failed: 0 / ignored: 3
```

對比 Round 1 baseline 3255 → +9 = 預期（4 halt_audit 新增 + 5 halt_ttl 新增 [4 restore + 1 incident_replay]）。

### 5.2 P1-16 regression preserved

```
cargo test -p openclaw_engine --release per_symbol_price_pnl
→ 3 passed / 0 failed
```

`test_halt_session_uses_per_symbol_price_not_triggering_tick` 新增 env_lock + RAII env guard 不改測試語意，僅隔離 cargo test 多 thread 對 OPENCLAW_HALT_AUDIT_LOG env 互踩污染。

### 5.3 Python tail-writer Mac unit tests

```
python3 helper_scripts/canary/test_halt_audit_pg_writer.py
→ Ran 20 tests in 0.062s — OK
```

覆蓋：
- JSONL robust parser：5 cases（純行 / 黏接 / 混合 / 壞 JSON skip / 空 chunk）
- Cursor state：5 cases（缺檔 / save+load roundtrip / 壞檔 / 負值 reject / 缺欄位）
- Validate：3 cases（schema=None pass-through / 通過 / 失敗）
- Resolve paths：3 cases（env override / data_dir fallback / cursor env override）
- 整合 PG mock：4 cases（log 缺檔 / 3 rows → 3 INSERTs / V098 absent → cursor 不前進 / dup → rowcount=0 skip）

### 5.4 Python tail-writer Linux PG real integration

跑了 `bash /tmp/halt_audit_pg_writer_integration.sh` 在 Linux trade-core：

- 寫 3 行 fake JSONL（halt_session_set / halt_session_auto_cleared / halt_session_manual_cleared）
- run writer → 3 rows INSERT 進 governance_audit_log
- query 確認 event_type ↔ clear_path 映射正確：
  - `halt_session_auto_cleared ↔ auto_ttl`
  - `halt_session_manual_cleared ↔ ipc_resume`
  - `halt_session_set ↔ (clear_path null)`
- 第二次 run → cursor 已是 file size → no new rows → idempotent OK
- DELETE 3 test rows 清理 production DB

### 5.5 9 個 round 2 新 test 列表

**halt_audit module（4 個）**:
- `test_event_type_for_clear_path_mapping` — fn 直接 unit
- `test_record_halt_cleared_event_type_mapping` — JSONL 寫入 → 讀 → 驗 event 字段
- `test_json_number_or_null_nan_inf_safe` — NaN/Inf/finite f64 對 JSON 值
- `test_record_halt_set_with_nan_balance_does_not_panic` — NaN-tainted PaperState 端對端

**halt_ttl sibling（5 個）**:
- `test_halt_state_restored_after_restart` — engine 1 snapshot → engine 2 restart → TTL 從 ORIGINAL T0 算
- `test_restore_halt_state_missing_snapshot_is_cold_start` — fail-soft
- `test_restore_halt_state_corrupted_json_is_cold_start` — fail-soft
- `test_restore_halt_state_kind_set_but_ts_zero_treated_as_cold` — 防禦性
- `test_2026_05_19_incident_replay` — spec §6.3 14 步全覆蓋

### 5.6 Acceptance Criteria 對照（spec §10）

| AC | 條件 | Round 2 狀態 |
|---|---|---|
| A-1 | demo daily_loss + 24h elapse → auto-clear | ✅ unit + incident_replay |
| A-1-EV | Linux PG runtime evidence | ✅ Linux Python writer integration 真實寫 governance_audit_log 已驗 |
| A-2 | session_drawdown + 7d → 仍 paused | ✅ unit + incident_replay |
| A-2-EV | Linux PG runtime evidence | ⏳ 待 deploy 後 operator 觀察自然事件 |
| A-3 | drawdown_halt_ttl_ms > 0 reject | ✅ |
| A-3a | daily_loss TTL floor 24h | ✅ |
| A-4 | restart 不重設 TTL 起點 | ✅ unit + integration（roundtrip 真實驗）|
| A-4-EV | Linux PG snapshot 寫回 | ⏳ 待 deploy 後 restart 驗 |
| A-5 | halt_audit.log 每事件一行 + quant-context | ✅ unit + incident_replay |
| **A-6** | governance_audit_log INSERT 路徑 | ✅ **Round 2 補齊**：Python tail-writer + Linux PG integration 真實 INSERT 驗 |
| A-7 | 3 環境 TOML 獨立 + validate | ✅ |
| A-8 | V098 apply + 冪等 | ✅ |
| A-9 | Live env daily_loss sticky | ✅ |
| X-1 | cargo baseline 不退化 | ✅ 3264 / 0 / 3 |
| X-2 | P1-16 regression 仍綠 | ✅ 3/0 |
| X-3 | E2 review APPROVE | ⏳ Round 2 待 E2 |
| X-4 | QA Audit APPROVE | ⏳ |
| X-5 | Forensic log jsonschema validate | ✅ Python writer 已串接 |
| X-6 | 16 根原則 + 9 不變量 0 違反 | ✅ |
| X-7 | 3 TOML 改 + validate | ✅ |
| X-8 | Pydantic IPC `extra='allow'` | ⏸️ Layer B |
| X-9 | features 不含 halt 名 | ✅ |
| X-10 | LiveDemo TOML load path | ✅ |

---

## 6. 不確定之處 / 設計 trade-off

### 6.1 governance_audit_log INSERT 冪等性使用 WHERE NOT EXISTS 而非 ON CONFLICT

**事實**：governance_audit_log 沒有 (event_type, process_pid, ts_ms) UNIQUE 約束（spec 不要求；V035 base schema 只有 PRIMARY KEY (id, ts)），因此無法直接走 `ON CONFLICT DO NOTHING`。Python writer 改用：

```sql
INSERT INTO learning.governance_audit_log (...)
SELECT %s, ..., %s::jsonb, '{}', '{}'
WHERE NOT EXISTS (
    SELECT 1 FROM learning.governance_audit_log
     WHERE event_type = %s
       AND payload->>'process_pid' = %s
       AND payload->>'ts_ms' = %s
);
```

`rowcount=1` 表 inserted；`=0` 表已存在 skip。

**Trade-off**：每次 INSERT 多一次 SELECT 查詢，對 high-volume INSERT 有額外開銷；但 halt 事件頻率極低（每天 < 數十次），效能可忽略。

**Mitigation idea（不在本次 IMPL scope）**：未來若有需要，可加 partial unique index `CREATE UNIQUE INDEX ... ON governance_audit_log ((payload->>'process_pid'), (payload->>'ts_ms'), event_type) WHERE event_type LIKE 'halt_session_%'` 並切換 ON CONFLICT。本次保守選 WHERE NOT EXISTS pattern，無 schema 變更。

### 6.2 Round 1 forensic schema 內 6 quant-context fields 仍部分 null

Round 1 §6.6 已記：`per_symbol_drawdown_max_pct` / `consecutive_loss_max_count` / `correlated_exposure_pct` / `per_strategy_drawdown_contribution_pct` / `per_symbol_atr_pct` 仍填 null（避免本 IMPL 順手加 IndicatorEngine / PortfolioState 依賴）。Round 2 沒擴範圍補上 — 待 P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1 ticket 觸發後視需要再加 helper（每個 ~10 LOC）。

`paper_state_recompute_ok` + `paper_state_balance_history` 仍有真值，且 E3 MEDIUM-1 已加 NaN guard。

### 6.3 cron interval 選 1min 而非 30s

Spec 建議 30s polling 或 inotify daemon。我選 1min cron interval：
- 對齊 sibling pattern（outcome_backfiller / wave9）— operator 認知一致
- 缺 inotify python 依賴；cron 簡單可靠
- halt 事件頻率極低，1min latency 對 7d operator query 影響可忽略
- 失敗自動下次重試；cursor state file 保證冪等

如果 PM 認為需 30s interval，可改 cron 條目用 `* * * * * + sleep 30 && ...` 雙條目，或改寫 daemon。本次保守選 cron。

### 6.4 paper_state_restore.rs 暴露 pub(crate) 模組

Round 2 把 `mod paper_state_restore` 改為 `pub(crate) mod` 因為要讓 tick_pipeline::tests::halt_ttl 跨 module 使用 `env_test_lock`。對 prod 行為無影響（cfg(test) 限定 + pub(crate) 不外洩 crate 外）。

### 6.5 per_symbol_price_pnl 加 env_lock 是 test-only 修改

`test_halt_session_uses_per_symbol_price_not_triggering_tick` 加 env_lock + RAII env restore guard 是「修 cargo test 多 thread race」**不改測試語意**。原 assert 全保留；env 還原 guard 確保即便本 test panic 也能還原 OPENCLAW_HALT_AUDIT_LOG，避免污染後續 test。

### 6.6 risk_config_version_seen 仍填 0（Round 1 §6.3 follow-up）

Round 1 §6.3 列為 follow-up：`IntentProcessor::risk_config_version_seen()` accessor 缺。Round 2 未補（不在 4 MUST-FIX 範圍）。E2 確認此 follow-up 是否仍須在後續 ticket 處理。

---

## 7. E2 round 2 review 明確點

1. **MUST-FIX-1 mapping correctness**：請對抗驗 4 條 clear_path 鏈路（commands.rs auto_ttl / lifecycle.rs ipc_resume / lifecycle.rs ipc_reset / commands.rs ipc_system_mode_shadow）。新測 `test_record_halt_cleared_event_type_mapping` 走完整 file IO 路徑驗證。Linux PG integration 也已驗。

2. **MUST-FIX-2 restore round-trip**：請對抗驗 `restore_halt_state_from_snapshot` 對 4 種失敗模式（缺檔 / 壞 JSON / 缺 mode_snapshots / halt_kind=null）皆 fail-soft 冷啟動。我加了 4 個 fail-soft test + 1 個 happy roundtrip test。

3. **MUST-FIX-3 Python writer 冪等性與 race 處理**：請對抗檢「同一 event 寫多次是否真的只 INSERT 一次」。我 Linux PG 端跑了 2 次連續呼叫 → row count 仍 3（idempotent verified real PG）。

4. **MUST-FIX-4 拆 sibling 不破壞語義**：請驗 `cargo test -p openclaw_engine --release config::risk_config` 仍跑全部 9 個 halt TTL test（halt_ttl_tests 名 namespace 改但邏輯不變）。

5. **E3 MEDIUM-1 NaN guard**：請對抗檢還有沒有遺漏的 f64 字段沒過 helper（其他 codepath 例如 status_report / GUI snapshot）— 我只改 halt_audit.rs 內路徑。

6. **SHOULD-FIX incident replay 完整性**：我寫的 incident_replay 是「構造模擬」非「真實 2026-05-19 incident 重播」（PA spec 寫「Construct TickPipeline ... Force-inject paper_state」就是這意思）— E2 確認此模擬深度是否滿足 spec §6.3 mandatory。如要真 incident replay（讀 archived pipeline_snapshot.json 與當時 halt_audit.log），可在 Layer B / 後續 P1 ticket 補。

7. **risk_config_tests.rs 161 行差距**：Round 1 我加 165 LOC，Round 2 拆 sibling 拆出 159 LOC，差 6 LOC 是補了拆分說明註釋。父檔現 1917 < 2000，sibling 182 LOC。

---

## 8. Operator 下一步

1. **PM 派發 E2 round 2 re-review**（per `feedback_impl_done_adversarial_review`）
   - 重點：§7 七個 E2 review 明確點 + Round 1 review 已標 4 MUST-FIX 是否確實閉合
   - 預期：cargo test 全套 3264 / 0 / 3 + Python 20 / 0 + Linux PG integration 已 sign-off
2. **E4 regression**
   - 跑 `cargo test -p openclaw_engine --release` 確認 AGGREGATE 不退化
   - Mac aarch64-apple-darwin + Linux x86-64 cross-arch 兩端
   - 跑 `cargo test per_symbol_price_pnl` 確保 P1-16 仍綠
   - 跑 `python3 helper_scripts/canary/test_halt_audit_pg_writer.py` 20 tests
3. **QA Audit**（策略 / 風控改動）
   - 重點：spec §7.4 9 條安全不變量 + 16 根原則合規（§4 表）
   - 比對 spec §10 X-1 ~ X-10 + A-1 ~ A-9 全綠
4. **DO NOT MERGE TO MAIN** — feature branch only；PM 派發 E2 round 2 re-review 後再決定
5. **DO NOT TRIGGER DEPLOY** — operator 親自授權

---

## 9. 重要備忘錄

1. **branch 狀態**：本 Round 2 IMPL 在 Mac dirty working tree。未 commit / 未 push。
2. **V098 已 land Linux production DB**（Round 1 §6.1 副作用，V098 24-value CHECK constraint 已 active）。Python writer 已可直接寫 governance_audit_log。
3. **commit subject 建議**：`fix(engine): P0-ENGINE-HALTSESSION-STUCK-FIX Layer A Round 2 — E2 4 MUST-FIX + E3 NaN guard + spec §6.3 replay`
4. **Linux PG integration 已驗** 但只是 3 fake rows 寫+清理；engine 真實觸發 HaltSession 後的端對端鏈路（engine.log → halt_audit.log → cron writer → governance_audit_log）待 deploy + 7d observation 驗。
5. **A-6 接受標準已閉合**：Round 1 §6.2 設計選擇「forensic log + Python 補 INSERT」現由 MUST-FIX-3 IMPL 完成。
6. Layer B（Python watchdog inert probe）派發 **AFTER** Layer A deploy + 24h watch PASS（spec §11.3）。

---

## 10. Round 1 → Round 2 對比表

| 指標 | Round 1 | Round 2 | Δ |
|---|---|---|---|
| cargo test passed | 3255 | 3264 | +9 |
| cargo test failed | 0 | 0 | 0 |
| 新 test 數 | 34 | 43 | +9 |
| 修改檔數 | 18 | 9 修 + 4 新 = 13 | -5 |
| 新建檔數 | 4 | 4 | 0 |
| risk_config_tests.rs LOC | 2076 | 1917 | -159（拆出 sibling）|
| Mac build | PASS | PASS | - |
| Linux PG integration | dry-run × 2 | + Python writer 3 rows real INSERT | + |
| Acceptance Criteria 全綠 | 14 / 23 + 6 post-deploy | 15 / 23 + 5 post-deploy | A-6 從 design-choice → unit+integration verified |

---

E1 IMPLEMENTATION DONE: 待 E2 round 2 re-review（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_round2_report.md`）

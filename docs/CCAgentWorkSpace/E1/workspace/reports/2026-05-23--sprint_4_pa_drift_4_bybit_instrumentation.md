---
report: Sprint 4+ Wave A PA-DRIFT-4 — bybit_rest_client + bybit_private_ws instrumentation
date: 2026-05-23
author: E1 (Backend Developer, Rust)
phase: Sprint 4+ first Live Wave A — PA-DRIFT-4 carry-over closure
status: IMPL DONE — 待 E2 round 1 review
parent dispatch:
  - PM Sprint 4+ Wave A PA-DRIFT-4 dispatch (operator prompt 2026-05-22)
  - PA Sprint 2 dispatch packet `docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` §1.2 + §5.1 prerequisite + §5.5 反模式
  - PA Sprint 2 design spec amend report Track D HIGH-3 (PA-DRIFT-4 entry)
  - E1 Sprint 2 Wave 2 Track D scaffold report 2026-05-22 §4 carry-over item 1+2
runtime: Mac development (Rust cargo build + cargo test)
production engine: 未碰
---

# E1 PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation — 2026-05-23

## §1. 5 工作項實作 LOC + 字面 diff

### 1.1 RestLatencyHistogram（bybit_rest_client.rs:296-454）

新增 struct `RestLatencyHistogram` + 4 public method：

| 項目 | 位置 | 說明 |
|---|---|---|
| struct | `bybit_rest_client.rs:343-347` | `samples: Mutex<Vec<(Instant, u64)>>`（thread-safe + 60s rolling） |
| `new()` | `bybit_rest_client.rs:356-360` | 空 histogram；samples 預配 256 capacity |
| `record_latency(latency_ms: u64)` | `bybit_rest_client.rs:360-381` | hot path：push 樣本；達 cap 8192 retain expired + truncate to half |
| `percentile_triple() -> (u32, u32, u32)` | `bybit_rest_client.rs:391-419` | 60s window 樣本 → sort_unstable → nearest-rank p50/p95/p99；空樣本返 (0,0,0) |
| `sample_count() -> usize` | `bybit_rest_client.rs:422-432` | test/debug 用；返 60s 內樣本數 |

關鍵設計：
- **sort-based nearest-rank percentile**（避 hdrhistogram 新 dep；對齊 Prometheus 行業慣例）：`((q * n).ceil() as usize).saturating_sub(1).min(n - 1)` 取 sorted[idx]
- **60s rolling window**：lazy expire（讀取時走 retain）；`now.checked_sub(Duration::from_secs(60)).unwrap_or(now)` 對 `Instant` 無 saturating_sub 的 fallback
- **buffer cap 8192**（60s × 假設 100 call/s = 6000 上限 + 30% headroom）：cap 觸發走 retain + truncate 防 unbounded

`get()` / `post()` 端 hot path wrap（`bybit_rest_client.rs:998-1042` + `1054-1094`）：
```rust
// PA-DRIFT-4 工作項 (1)：REST latency 計時起點。
let call_start = Instant::now();
let resp = self.client.get(&url)...send().await?;
self.update_rate_limit(&resp);
let body = resp.text().await?;
let parsed: BybitResponse = serde_json::from_str(&body)?;
let elapsed_ms = call_start.elapsed().as_millis().min(u64::MAX as u128) as u64;
self.latency_histogram.record_latency(elapsed_ms);
Ok(parsed)
```

### 1.2 RetCodeCounter（bybit_rest_client.rs:456-559）

新增 struct `RetCodeCounter` + 6 public method：

| 項目 | 位置 | 說明 |
|---|---|---|
| struct | `bybit_rest_client.rs:466-470` | 雙 Mutex<Vec<Instant>>（4xx + 5xx 分桶） |
| `new()` | `bybit_rest_client.rs:480-485` | 空 counter；各預配 64 capacity |
| `record_4xx() / record_5xx()` | `bybit_rest_client.rs:488-509` | hot path：push 時間戳；cap 8192 prune |
| `count_4xx() / count_5xx()` | `bybit_rest_client.rs:512-534` | 60s window 樣本數；返 u32（cap u32::MAX） |
| `record_for_error(&BybitApiError)` | `bybit_rest_client.rs:545-558` | helper：對映 retCode → 4xx / 5xx |
| `is_client_fault_retcode(ret_code: i64) -> bool` | `bybit_rest_client.rs:570-572` | 對映規則：10001/10002/10003/10004/10005/10006/10010 屬 4xx；其他 110xxx 屬 5xx |

對映規則（per packet §1.2 工作項 (2) + §5.5 反模式 (d) multi-venue gate）：
- `BybitApiError::Business { ret_code: 10001 InvalidParam / 10002 InvalidRequest / 10003 ApiKeyInvalid / 10004 SignError / 10005 PermissionDenied / 10006 IpRateLimit / 10010 UnmatchedIp }` → 4xx（client fault）
- `BybitApiError::Business` 其他 retCode（110xxx 業務碼）→ 5xx（venue fault）
- `BybitApiError::Transport / JsonParse / NoCredentials / SigningError` → 不計入（wrapper 層 fault；非 venue / client API fault）

`get_checked() / post_checked()` 端 wrap（`bybit_rest_client.rs:1098-1116`）：
```rust
pub async fn get_checked(&self, path: &str, params: &[(&str, &str)]) -> BybitResult<BybitResponse> {
    let result = self.get(path, params).await?.into_result();
    if let Err(ref err) = result {
        self.ret_code_counter.record_for_error(err);
    }
    result
}
```

### 1.3 WsDropoutCounter + WsRttHistogram（bybit_private_ws.rs:25-258）

新增 2 struct + 8 public method：

| 項目 | 位置 | 說明 |
|---|---|---|
| `WsRttHistogram` struct | `bybit_private_ws.rs:69-72` | `samples: Mutex<Vec<(Instant, u64)>>` |
| `WsRttHistogram::record_rtt(rtt_ms)` | `bybit_private_ws.rs:127-141` | hot path |
| `WsRttHistogram::percentile_pair() -> (u32, u32)` | `bybit_private_ws.rs:151-175` | p50/p99；空返 (0,0) |
| `WsRttHistogram::sample_count() -> usize` | `bybit_private_ws.rs:178-189` | test/debug 用 |
| `WsDropoutCounter` struct | `bybit_private_ws.rs:213-216` | `samples: Mutex<Vec<Instant>>` |
| `WsDropoutCounter::record_dropout()` | `bybit_private_ws.rs:227-240` | hot path：cap 256 prune |
| `WsDropoutCounter::count() -> u32` | `bybit_private_ws.rs:243-256` | 60s window 計數 |

WS dropout 接點（6 處，per packet §1.2 工作項 (3)）：
| 行 | 場景 | 計入 dropout？ |
|---|---|---|
| `bybit_private_ws.rs:584` | auth send failure | ✅ venue/網路 fault |
| `bybit_private_ws.rs:614` | cancel during auth wait | ❌ 主動 cancel |
| `bybit_private_ws.rs:649-651` | auth fail / timeout / stream end | ✅ venue/網路 fault |
| `bybit_private_ws.rs:670` | subscribe send failure | ✅ venue/網路 fault |
| `bybit_private_ws.rs:697` | shutdown requested in main loop | ❌ 主動 cancel |
| `bybit_private_ws.rs:739-744` | G9-02 force-reconnect | ✅ unknown topic guard 觸發 = venue 異常 |
| `bybit_private_ws.rs:798-800` | main loop exit (ping fail / read error / server close / stream end) | ✅ venue/網路 fault |
| `bybit_private_ws.rs:807-810` | connect_async failure | ✅ venue/網路 fault |

**主動 cancel 排除 dropout** 對齊 ADR-0042 Decision 3 cascade gate 預警語意（venue fault only；operator shutdown 不該升 cascade）。

WS RTT 計算（`bybit_private_ws.rs:702-731`）走 main loop 內 local `Option<Instant>` ping_at：
```rust
let mut last_ping_at: Option<Instant> = None;
// ping_timer.tick 後：
last_ping_at = Some(Instant::now());
// 收到 text msg：peek "op":"pong" 子串
if last_ping_at.is_some() && text.contains("\"op\":\"pong\"") {
    if let Some(ping_at) = last_ping_at.take() {
        let rtt_ms = ping_at.elapsed().as_millis()... as u64;
        self.rtt_histogram.record_rtt(rtt_ms);
    }
}
```

為什麼 local Option 而非 self Mutex：ping send + pong arrival 都在同 tokio::select! task 串行；run loop 退出（reconnect）即重置；不會跨重連污染；0 lock 開銷 + 0 Arc clone。

### 1.4 RealApiLatencySourceProbe（health/domains/api_latency_probe_impl.rs 新 204 LOC）

| 項目 | 位置 | 說明 |
|---|---|---|
| MODULE_NOTE | `api_latency_probe_impl.rs:1-26` | 用途 / 主類 / 依賴 / 硬邊界 4 段 |
| struct | `api_latency_probe_impl.rs:46-51` | 持 4 個 Arc<instrumentation>（rest_latency / ret_code_counter / ws_dropout / ws_rtt） |
| `new()` | `api_latency_probe_impl.rs:67-78` | 4 Arc 注入；含使用範例 doc |
| `impl ApiLatencySourceProbe` 8 method | `api_latency_probe_impl.rs:81-129` | 8 trait method 對應 instrumentation accessor |
| inline test `test_probe_reflects_instrumentation_state` | `api_latency_probe_impl.rs:140-185` | 注入樣本 → 8 method 對齊 |
| inline test `test_probe_empty_returns_zero` | `api_latency_probe_impl.rs:188-204` | empty probe 8 method 全返 0（OK band fail-soft） |

主 register（`health/domains/mod.rs:55`）：
```rust
pub mod api_latency_probe_impl;
```

8 trait method → instrumentation accessor 一對一映射：
| trait method | instrumentation call |
|---|---|
| `current_rest_p50_ms_60s_window` | `rest_latency.percentile_triple().0` |
| `current_rest_p95_ms_60s_window` | `rest_latency.percentile_triple().1` |
| `current_rest_p99_ms_60s_window` | `rest_latency.percentile_triple().2` |
| `current_ws_rtt_p50_ms_60s_window` | `ws_rtt.percentile_pair().0` |
| `current_ws_rtt_p99_ms_60s_window` | `ws_rtt.percentile_pair().1` |
| `current_ret_code_4xx_count_60s_window` | `ret_code_counter.count_4xx()` |
| `current_ret_code_5xx_count_60s_window` | `ret_code_counter.count_5xx()` |
| `current_ws_dropout_count_60s_window` | `ws_dropout.count()` |

### 1.5 Integration test（tests/api_latency_probe_real_impl.rs 新 350 LOC）

15 test 覆蓋：

| # | test name | 用途 |
|---|---|---|
| 1 | `test_rest_latency_p50_p95_p99_after_1000_calls` | 1000 uniform [1..=1000] sample → p50=500 / p95=950 / p99=990 對齊 nearest-rank 公式 |
| 2 | `test_rest_latency_empty_returns_zero_triple` | 空 histogram (0,0,0) fail-soft |
| 3 | `test_rest_latency_sample_count_matches` | sample_count == record 次數 |
| 4 | `test_ret_code_counter_4xx_5xx_classify` | retCode 10001/10003/10004/10006 → 4xx；110001/110007/110049 → 5xx |
| 5 | `test_ret_code_counter_skips_non_business_errors` | Transport/JsonParse/NoCredentials/SigningError 不計入 |
| 6 | `test_ret_code_counter_direct_record` | record_4xx/record_5xx low-level API |
| 7 | `test_ws_dropout_counter_basic` | record × 5 → count == 5 |
| 8 | `test_ws_dropout_counter_empty_returns_zero` | empty 0 |
| 9 | `test_ws_rtt_histogram_after_samples` | [10,20,30,40,50,100] → p50=30 / p99=100 |
| 10 | `test_ws_rtt_histogram_empty_returns_zero_pair` | empty (0,0) |
| 11 | `test_real_probe_through_api_latency_emitter` | RealProbe → ApiLatencyEmitter.sample_now() → 8 field 對齊 |
| 12 | `test_real_probe_empty_emitter_returns_all_zero` | empty probe 經 emitter 全 0 |
| 13 | `test_multiple_probes_share_instrumentation_arc` | 多 probe 共享 Arc<instrumentation>；一端 record 全 probe 看見 |
| 14 | `test_rest_latency_hot_path_cap_bounded` | 20000 record → cap 8192 不 panic / 不 unbounded |
| 15 | `test_ret_code_counter_hot_path_cap_bounded` | 20000 record → cap 8192 |

**為什麼不接真實 Bybit endpoint**：CI/Mac 無外網依賴；end-to-end REST/WS 接線驗證由 Wave B main.rs scheduler + Phase 3c QA Linux runtime AC-1b real PG empirical 走。

## §2. cargo test result

| Verify | Command | Result |
|---|---|---|
| **本 round 新 integration test** | `cargo test --release --test api_latency_probe_real_impl` | **15/15 PASS** |
| **全 lib unit test** | `cargo test --release --lib` | **3170 passed / 0 failed / 1 ignored pre-existing** |
| **health:: lib unit** | `cargo test --release --lib health::` | **105/105 PASS**（含本 round 新 api_latency_probe_impl 2 inline test） |
| Track A regression | `cargo test --release --test sprint2_track_a_engine_runtime` | **9/9 PASS** |
| Track B regression | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5/5 PASS** |
| Track C regression | `cargo test --release --test sprint2_track_c_database_pool` | **8/8 PASS** |
| Track D regression | `cargo test --release --test sprint2_track_d_api_latency` | **7/7 PASS** |
| Track E regression | `cargo test --release --test sprint2_track_e_strategy_quality` | **11/11 PASS** |
| Track F regression | `cargo test --release --test sprint2_track_f_risk_envelope` | **8/8 PASS** |
| Spike regression | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3/3 PASS** — spike default false invariant 守住 |
| bybit_rest_client lib | `cargo test --release --lib bybit_rest_client` | **29/29 PASS** — 包含 9 個 manual struct constructor test 對齊 |
| bybit_private_ws lib | `cargo test --release --lib bybit_private_ws` | **31/31 PASS** |
| **AC-5 nm symbol scan** | `nm target/release/openclaw-engine \| grep -cE "(mock_instant\|tokio::time::pause\|spike)"` | **0** hit ✓ — production binary 0 mock time 滲透 |
| Release build | `cargo build --release` | **PASS** — 27.42s clean；3 pre-existing warning + 1 binary warning；本 round 0 new warning |

**累計**：15 new + 9+5+8+7+11+8+3 sprint2 integration regression + 3170 lib full + 3 spike = **3239 PASS / 0 fail / 1 ignored pre-existing**。

## §3. ApiLatencySourceProbe 8 method 真實 hook 對齊

### 3.1 4xx/5xx 對映規則確認

對齊 dispatch packet §1.2 工作項 (2) + §5.5 反模式 (d) multi-venue gate 預留：

| Bybit retCode | 對映桶 | rationale |
|---|---|---|
| 10001 InvalidParam | 4xx | 請求格式錯（wrapper bug） |
| 10002 InvalidRequest | 4xx | 同上 |
| 10003 ApiKeyInvalid | 4xx | 認證錯（憑證配置 bug） |
| 10004 SignError | 4xx | 簽名錯（簽算邏輯 bug） |
| 10005 PermissionDenied | 4xx | 權限不足（key 配置錯） |
| 10006 IpRateLimit | 4xx | IP 限流（client 端超頻） |
| 10010 UnmatchedIp | 4xx | IP 漂移（client 端 IP 變） |
| 110xxx（balance / position / order lifecycle / instrument filter） | 5xx | venue-side state；非 client fault；保守對映 |
| `BybitApiError::Transport` | 不計入 | network fault；emitter 不負責 |
| `BybitApiError::JsonParse` | 不計入 | protocol parse 錯；wrapper bug 而非 venue/client API |
| `BybitApiError::NoCredentials` / `SigningError` | 不計入 | wrapper 層 fault |

**為什麼 110xxx 全算 5xx 而非細分**：dispatch packet §5.5 反模式 (d) 要求 multi-venue 預留；Bybit retCode 110001 OrderNotFound、110004 WalletInsufficient 等業務碼 semantically 跨 venue 完全不同；emitter 只看 transport-level class（4xx = client fault / 5xx = venue fault）；細分由 caller 端後續 review（per BB 端後續 hook 對映表 review）。

### 3.2 WS dropout 60s window 接點覆蓋

| 接點 | 場景 | record_dropout? |
|---|---|---|
| `bybit_private_ws.rs:584` auth send failure | venue/網路端異常 → 連線斷 | ✅ |
| `bybit_private_ws.rs:614` cancel during auth | operator 主動 cancel | ❌ |
| `bybit_private_ws.rs:649-651` auth fail / timeout | venue/網路端異常 | ✅ |
| `bybit_private_ws.rs:670` subscribe send failure | 連線在 auth 後即斷 | ✅ |
| `bybit_private_ws.rs:697` shutdown in main loop | operator 主動 cancel | ❌ |
| `bybit_private_ws.rs:739-744` G9-02 force-reconnect | unknown topic guard 觸發（venue 異常） | ✅ |
| `bybit_private_ws.rs:798-800` main loop exit | ping fail / read error / server close / stream end | ✅ |
| `bybit_private_ws.rs:807-810` connect_async failure | DNS / TLS / venue 拒連 | ✅ |

**6/8 接點計入 dropout**；2/8 主動 cancel 排除（per ADR-0042 cascade gate = venue fault only）。

### 3.3 WS RTT ping/pong 對齊

`bybit_private_ws.rs:711-731` main loop 內 local `Option<Instant>` ping_at：
- ping send 後 `last_ping_at = Some(Instant::now())`
- 任何 text msg 收到時 peek `"\"op\":\"pong\""` 子串 + `last_ping_at.is_some()` 雙重 guard
- 計算 elapsed → `rtt_histogram.record_rtt(rtt_ms)`
- record 後 take() clear `last_ping_at` 避一個 ping 對應多 RTT sample

**為什麼 contains 而非重新 parse**：pong response payload 簡單（`{"op":"pong","args":["1700..."]}`）；contains 子串 + ping_at guard 雙重保險；false positive 在 order/execution data payload 中罕見且 record extra RTT sample 不致命（極端情況下 RTT 偏低）。

## §4. PA-DRIFT-4 closure verdict + Wave B unblock 條件

### 4.1 closure verdict

**PA-DRIFT-4 IMPL DONE** — 5/5 工作項全 land：

| 工作項 | 狀態 | 證明 |
|---|---|---|
| (1) RestLatencyHistogram | ✅ | bybit_rest_client.rs +176 LOC + 3 integration test |
| (2) RetCodeCounter | ✅ | 同檔 +104 LOC + 3 integration test + retCode 對映 helper |
| (3) WsDropoutCounter + WsRttHistogram | ✅ | bybit_private_ws.rs +281 LOC + 4 integration test + 6 dropout 接點 |
| (4) RealApiLatencySourceProbe | ✅ | 新檔 204 LOC + 2 inline test + 2 integration test |
| (5) Integration test | ✅ | 新檔 350 LOC + 15 test PASS |

### 4.2 Wave B unblock 條件

main.rs Wave B 接 scheduler 前置：
1. **`MetricEmitterScheduler::run` 接 Track A scaffold start** — 已 land sprint 2 Track A
2. **`ApiLatencyEmitter` 構造時注入 `RealApiLatencySourceProbe`** — 本 round 已 land probe impl；Wave B caller 端：
   ```rust
   // main.rs Wave B 範例
   let rest_client = Arc::new(BybitRestClient::new(env, None, None)?);
   let ws_client = BybitPrivateWs::new(api_key, api_secret, env, cancel, event_tx);

   let probe = RealApiLatencySourceProbe::new(
       rest_client.latency_histogram_handle(),
       rest_client.ret_code_counter_handle(),
       ws_client.dropout_counter_handle(),
       ws_client.rtt_histogram_handle(),
   );
   let api_emitter = ApiLatencyEmitter::new(probe);
   scheduler.register_emitter(Box::new(api_emitter));
   ```
3. **Linux runtime `--rebuild` 啟用 scheduler** — Wave B 完成後做
4. **≥ 30 min 樣本累積** — Phase 3c QA AC-1b real PG empirical 前置

### 4.3 AC-1b 前置 unblock 進度

per PA Sprint 2 overall acceptance §AC-1b：
- ✅ Wave 2 Track D scaffold (trait 抽象) — 2026-05-22 IMPL DONE + E2 round 2 APPROVE-WITH-CONDITIONS
- ✅ **PA-DRIFT-4 instrumentation 4-6 hr IMPL — 本 round IMPL DONE**
- ⏳ PA-DRIFT-5（risk_envelope source probe 補位）— PARALLEL Wave A IMPL 中（隔壁 E1 sub-agent）
- ⏳ main.rs Wave B scheduler 接線 — 等 PA-DRIFT-4 + PA-DRIFT-5 全 closed 後
- ⏳ Linux runtime `--rebuild` — Wave B 完成後
- ⏳ ≥ 30 min 樣本累積 + 真實 PG empirical — Phase 3c QA

**AC-1b unblock 進度 1/5（PA-DRIFT-4）已完成**；PA-DRIFT-5 並行進行中；剩 main.rs Wave B + Linux deploy + 30min wait + Phase 3c QA。

## §5. 修改清單（字面 diff 摘要）

| File | 性質 | 改動 LOC | 摘要 |
|---|---|---|---|
| `rust/openclaw_engine/src/bybit_rest_client.rs` | extend | 936→1272 (+336) | 加 RestLatencyHistogram + RetCodeCounter 兩 pub struct + 14 method；BybitRestClient struct 加 2 field + 2 accessor；get/post 加 latency wrap；get_checked/post_checked 加 retCode 對映 |
| `rust/openclaw_engine/src/bybit_rest_client_tests.rs` | atomic edit | +20 LOC | 9 個 manual struct constructor 加 latency_histogram + ret_code_counter 兩字段（replace_all batch） |
| `rust/openclaw_engine/src/bybit_private_ws.rs` | extend | 1413→1693 (+280) | 加 WsDropoutCounter + WsRttHistogram 兩 pub struct + 8 method；BybitPrivateWs struct 加 2 field + 2 accessor；run loop 加 6 處 dropout 接點 + ping/pong RTT |
| `rust/openclaw_engine/src/health/domains/api_latency_probe_impl.rs` | **新建** | 204 | MODULE_NOTE + RealApiLatencySourceProbe struct + 8 trait method impl + 2 inline test |
| `rust/openclaw_engine/src/health/domains/mod.rs` | atomic edit | +1 LOC + 4 行 doc | 加 `pub mod api_latency_probe_impl;` + module doc 對應段落 |
| `rust/openclaw_engine/tests/api_latency_probe_real_impl.rs` | **新建** | 350 | MODULE_NOTE + 15 integration test 覆 6 反模式守 |

**不動 file**：
- `health/mod.rs` / `writer.rs` / `event_bus.rs` / `domains/api_latency.rs`（不修 trait 簽名 / emitter struct / sample shape）
- `metric_emitter/mod.rs` / `main.rs`（per scope 不擴大；Wave B 工作）
- `domains/risk_envelope*` / `strategy_quality.rs`（並行 PA-DRIFT-5 + Sprint 2 Track E/F 文件）
- 不引 V### SQL / spike feature / GUI

## §6. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine / trading_ai DB / V### SQL |
| **§七 Code And Docs Rules** | 新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；新 module MODULE_NOTE 完整（用途 / 主類函數 / 依賴 / 硬邊界 4 段）；觸及 bilingual block 不主動清；無 emoji |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 round 1 review；不自行 commit；不派下游 sub-agent；本 round 走 PM Sprint 4+ Wave A dispatch / Phase 3e §4.1 item 3 carry-over |
| **§九 Code Structure Guardrails** | bybit_rest_client.rs 1272 LOC > 800 警告但 < 2000 hard cap；bybit_private_ws.rs 1693 LOC > 800 警告但 < 2000；新 api_latency_probe_impl.rs 204 LOC OK；test file 不計 cap |
| **§Data, Migrations, And Validation** | 本 round 不新增 V###；本 round 純 Rust IMPL；不觸 PG dry-run（per `feedback_v_migration_pg_dry_run` 適用範圍是 V### migration with PG reflection；本 round 不觸） |
| **cross-platform** | 純 Rust 邏輯；不引平台特異 path；不寫 `cfg(target_os = "linux")`；`Instant::checked_sub` Mac+Linux 共通；hdrhistogram 雖在 workspace 但本 round 0 新 dep（用 sort-based percentile 避新編譯時間 + 跨平台 0 風險） |
| **AC-5 production binary 0 mock time 滲透** | nm 0 hit 守住；本 round 0 spike feature gate |
| **`feedback_impl_done_adversarial_review`** | 本 round 改動 = 2 extend file（共 +616 LOC）+ 1 新 impl file（204 LOC）+ 1 新 test（350 LOC）+ 1 atomic edit mod.rs；屬「IPC 邊界擴大 + 共用 helper」邊緣場景（4 新 public Arc handle 對外暴露）；E2 round 1 review 應確認 |
| **多角色 adversarial review 原則** | 15 integration test 覆 6 反模式守（hot path cap / multi-probe Arc 共享 / retCode 對映 / wrapper layer error skip / empty fail-soft / sample count 不退化） |
| **反模式對齊（per packet §5.5）** | (a) 不修 bybit_rest_client get/post 既有 REST call 邏輯 ✓（只加 latency wrap）/ (b) 不修 bybit_private_ws reconnect 邏輯 ✓（只加 dropout / RTT record）/ (c) emitter 不直接 import bybit client struct ✓（probe 走 Arc<dyn> trait 抽象）/ (d) ret_code 用 HTTP 標準語意（4xx/5xx）預留 multi-venue per ADR-0040 ✓ / (e) 不引 V### / spike / 跨進程 IPC ✓ |

## §7. 不確定 / Carry-over

1. **`bybit_rest_client.rs` 1272 LOC > 800 警告**：本 round 加 +336 LOC（含 RestLatencyHistogram + RetCodeCounter 兩 pub struct + 14 method）；< 2000 hard cap。是否需 G1-03 階段二 split（移 RestLatencyHistogram + RetCodeCounter 到獨立 sub-module 如 `bybit_rest_client/instrumentation.rs`）？建議**不切**：兩 struct 與 client 強耦合（client struct 直接持 Arc），split 反而需要在 wrapper 端跨檔 import + Arc handle method 散落；現狀 file split 已走過 Wave 1 G1-03（935 → 後續加碼到 1272）；E2 round 1 應確認。
2. **`bybit_private_ws.rs` 1693 LOC > 800 警告**：本 round 加 +280 LOC；< 2000 hard cap。同上理由；E2 round 1 應確認是否需切（WsRttHistogram + WsDropoutCounter 可移獨立 sub-module）。
3. **WS RTT contains 子串 false positive 風險**：`text.contains("\"op\":\"pong\"")` 可能在 order/execution data payload 中出現（極罕見）。實際影響 = 一次 RTT sample 偏低；emitter 60s rolling window 內樣本數量大時可吸收；E2 round 1 應確認此 trade-off 可接受 vs 需重新 parse JSON peek `op` 字段（後者 lock + 重 parse 增 latency）。我選 contains。
4. **retCode 對映規則 BB review 預警**：本 round 把 6 個 client fault retCode (10001-10006, 10010) + 110xxx 全 5xx 走保守對映；BB（exchange-facing role）端可能後續 review 細分 110xxx 中部分屬 client fault（如 110001 OrderNotFound 屬 strategy bug 非 venue fault）。本 round 對齊 packet §5.5 反模式 (d) multi-venue 預留設計；BB 端後續 review 細分由 Wave B+ 走。
5. **dropout 6/8 接點計入 vs 8/8 全計入**：本 round 排除 2 個 operator cancel 接點；E2 round 1 應確認此區分對齊 ADR-0042 cascade gate 預警語意；BB / FA 端後續 review 可能需 細化（如 cancel during auth wait 可能也是 venue 拒連觸發 cancel）。
6. **`Instant` 沒 `saturating_sub`**：第一次 build 12 個 E0599 error；Rust std `Instant` 只暴露 `checked_sub`。本 round 全改 `now.checked_sub(...).unwrap_or(now)` fallback 模式；早期啟動時 cutoff = now 等於不過濾，所有樣本 in window；隨啟動時間增長 cutoff 自然 60s 後正常工作；不影響功能。
7. **手動 struct constructor cascade**：BybitRestClient 加 2 field 後 bybit_rest_client_tests.rs 9 個 manual constructor 全 E0063 missing；replace_all batch fix 對齊「Rust API 變更 cascade 應一次性 sweep」教訓；本 round 已 closed。
8. **並行 Wave A PA-DRIFT-5**：隔壁 E1 sub-agent 並行 IMPL PA-DRIFT-5（risk_envelope source probe 補位）；本 round atomic edit `domains/mod.rs` 已 land `pub mod api_latency_probe_impl;` + 對應 doc；對方 add `pub mod risk_envelope_probe_impl;` + doc；兩條目和平共存（merge clean；無 conflict）。

## §8. Operator 下一步

1. **PM 派 E2 round 1 review**（focus on）：
   - LOC 警告 ≥ 800 是否需切 file（bybit_rest_client.rs 1272 / bybit_private_ws.rs 1693）
   - WS RTT contains 子串 false positive 評估
   - retCode 對映規則 110xxx 全 5xx 是否需 BB review 細分（per packet §5.5 反模式 (d)）
   - dropout 6/8 接點計入排除 2 個 operator cancel 是否對齊 ADR-0042 cascade gate
   - `Instant.checked_sub.unwrap_or(now)` 早期啟動行為（cutoff = now → 全樣本 in window）是否需顯式注釋
   - 15 integration test 覆蓋是否充分（特別是 cap prune + multi-probe Arc 共享）
   - 反模式 (a)-(e) 5 條對齊是否完整

2. **A3 review 路徑**：本 round 不動 GUI / IPC / 寫操作 trading hot path（只加觀測 instrumentation）；不主動派 A3。若 E2 round 1 認定 4 個新 Arc handle method 屬「IPC 邊界擴大」（per `feedback_impl_done_adversarial_review`），可派 A3 對抗性核驗；本 round 不主動派下游。

3. **PA Sprint 2 overall acceptance §AC-1b unblock 進度更新**：本 round closure 後，PA acceptance §AC-1b 進度 1/5 完成（PA-DRIFT-4）；建議 PM 在 Sprint 2 overall acceptance report 標註 unblock 1 條 + 等待 PA-DRIFT-5 並行 closure + Wave B main.rs 接線 dispatch。

4. **Wave B main.rs 接線 dispatch 預警**：本 round 完成後 Wave B PM 可 dispatch：
   - main.rs 構造 `RealApiLatencySourceProbe::new(rest.latency_histogram_handle(), rest.ret_code_counter_handle(), ws.dropout_counter_handle(), ws.rtt_histogram_handle())`
   - 注入 `ApiLatencyEmitter::new(probe)` 到 `MetricEmitterScheduler`
   - 並行 PA-DRIFT-5 完成後同步注入 `RealRiskEnvelopeSourceProbe`

5. **BB review 預警**：retCode 對映規則（client fault 6 個 + venue fault 110xxx）BB 端可能後續 review 細分；本 round 走保守對映 + ADR-0040 multi-venue 預留 + packet §5.5 反模式 (d) 對齊；E2 round 1 不阻 BB review；BB 端後續細分由 Wave B+ 走。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 1 review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_pa_drift_4_bybit_instrumentation.md`）**

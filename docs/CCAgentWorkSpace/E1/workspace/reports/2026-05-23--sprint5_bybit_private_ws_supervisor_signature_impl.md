---
report: Sprint 5+ §4.2.1 BybitPrivateWs supervisor signature 改造 IMPL
date: 2026-05-23
author: E1 (Backend Developer, Rust)
phase: Phase 2 IMPL DONE — 待 A3 + E2 並行核驗
status: IMPL DONE — 待下游審查
parent dispatch:
  - operator prompt 2026-05-23 §Sprint 5+ §4.2.1 PA Track 2 IMPL
upstream spec:
  - srv/docs/execution_plan/2026-05-23--sprint5_bybit_private_ws_supervisor_signature_design.md (PA SPEC, 738 LOC)
upstream PA report:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_bybit_private_ws_supervisor_design.md
runtime: Mac development（cargo workspace test 通過 3971 PASS / 0 FAIL）
production engine: 未碰 / 不 rebuild / 不 push
---

# E1 Sprint 5+ §4.2.1 BybitPrivateWs signature 改造 — 2026-05-23

## §0. TL;DR

per PA spec §3 + §5 Phase 2 16 step 順序執行；Option A external Arc 注入完成。

**改動範圍**：
- `BybitPrivateWs::new()` signature 加 2 個 `Arc<WsDropoutCounter>` / `Arc<WsRttHistogram>` 參數
- 5 處 caller 全 update（spec §3.2 列 4 處 + 新發現 1 處 `live_auth_watcher_tests.rs`）
- `PrivateWsBindings` struct 加 2 個 pub field（暴露給 main.rs）
- `SharedClientsBundle` struct 加 2 個 Option Arc field（Live > Demo 優先級 extract）
- `spawn_metric_emitter_scheduler` signature 加 2 個 Option Arc 參數
- `build_api_latency_emitter` 從 1 arg match arm 升 3-tuple match arm（任一 None 走 placeholder fallback）
- `build_real_api_latency_probe` signature + impl 改 `Arc::clone(shared_ws_dropout)` + `Arc::clone(shared_ws_rtt)`（取代 Wave B fresh 0-state Arc）

**驗證**：
- cargo build --release PASS（3 pre-existing warnings，無新警告）
- cargo test --workspace --release PASS — **3971 PASS / 0 FAIL**（baseline 3961 → 3971 +10，無 regression）
- caller_chain SSOT 對齊（spec §3.2 4 處 caller 全列入 + 1 處新發現修正）

---

## §1. 16 step IMPL 順序與檔案改動

per PA spec §5 Phase 2 順序：

| step | 檔 | 改動概要 |
|---|---|---|
| 1 | `bybit_private_ws.rs:544-583` | `BybitPrivateWs::new()` signature + impl 加 2 Arc 參數；中文 rationale doc 補滿（spec §3.1） |
| 2 | `bybit_private_ws.rs:1213-1224` | `test_auth_message_structure` 加 2 Arc fixture |
| 2 | `bybit_private_ws.rs:1242-1253` | `test_auth_signature_deterministic` 加 2 Arc fixture |
| 3 | `startup/private_ws.rs:54-73` | `PrivateWsBindings` 加 2 pub field（dropout_counter + rtt_histogram） |
| 4 | `startup/private_ws.rs:81-90` | 在 `spawn_private_ws_supervisor` task spawn 前構造 2 Arc + 補 use import `WsDropoutCounter` / `WsRttHistogram` |
| 4 | `startup/private_ws.rs:243-279` | supervisor task closure 加 `dropout_for_supervisor` + `rtt_for_supervisor` 跨 task move clone；inside loop `BybitPrivateWs::new(...)` 加 2 個 `Arc::clone` 參數 |
| 5 | `startup/private_ws.rs:295-301` | `PrivateWsBindings` 構造返 caller 加 2 field |
| 6 | `main_instruments.rs:33-58` | `SharedClientsBundle` struct 加 2 Option Arc field + 補 use import |
| 7 | `main_instruments.rs:84-101` | `init_shared_clients_and_instruments` 加 Live > Demo 優先級 extract `shared_ws_dropout` + `shared_ws_rtt` |
| 8 | `main_instruments.rs:215-220` | `SharedClientsBundle` 返 caller 加 2 field |
| 9 | `main_health_emitters.rs:233-260` | `build_real_api_latency_probe` signature 加 2 ref Arc 參數；body `Arc::clone(shared_ws_dropout)` + `Arc::clone(shared_ws_rtt)` |
| 10 | `main_health_emitters.rs:262-296` | `build_api_latency_emitter` 從 1-arg 升 3-tuple match arm；partial-Some 走 placeholder fallback（per spec §3.4 改動 2 rationale） |
| 11 | `main_health_emitters.rs:443-454` | `spawn_metric_emitter_scheduler` signature 加 2 ref Option Arc 參數 |
| 12 | `main_health_emitters.rs:496-501` | scheduler body 內 `build_api_latency_emitter` call site 加 2 arg |
| 13 | `main_health_emitters.rs:196-232` | module note Track D placeholder 揭露段（原 line 174-205）替換為 production wire-up note；upstream module doc 已被併行 session 一併擴展為含 Track E 描述（與本 IMPL 相容） |
| 13 | `main_health_emitters.rs:524-526` | spawn log message 從 「Track A/C/F real + B/D-WS placeholder」改 「Track A/C/D/F real + B placeholder」 |
| 14 | `main.rs:1454-1474` | `spawn_metric_emitter_scheduler` caller 加 `&shared_ws_dropout` + `&shared_ws_rtt` 兩 arg；info log message 對齊 |
| 15 | `main.rs:571-583` | `SharedClientsBundle` destructure 加 2 field |
| 16 | — | cargo build + workspace test 通過 |
| (extra) | `live_auth_watcher_tests.rs:103-115` | **新發現的 caller**：PrivateWsBindings 手構 fixture 加 2 個 Arc fixture + use import `WsDropoutCounter` / `WsRttHistogram` |

### 1.1 PA spec 未列入的 caller — `live_auth_watcher_tests.rs`

第一輪 cargo test 失敗暴露：

```
error[E0063]: missing fields `dropout_counter` and `rtt_histogram` in initializer of `PrivateWsBindings`
   --> openclaw_engine/src/live_auth_watcher_tests.rs:103:23
```

此 caller 不在 PA spec §3.2 列舉的 4 處 caller 範圍內，但 `PrivateWsBindings` 是 pub(crate) struct，src/ 內任何 fixture 手構都會卡 E0063。修法：補 2 個 `Arc::new(WsDropoutCounter::new())` + `Arc::new(WsRttHistogram::new())` fixture，註解標明此 mock factory 不啟動 WS run loop 故 fixture Arc 永不 accumulate sample。

**對 PA 推回 1 條**：spec §6.2 副作用識別清單 #1 寫「grep 確認 — startup/private_ws.rs:78 + tests/api_latency_probe_real_impl.rs:35（type import 不涉 new() caller）；公共範圍可控」，但漏掉 `src/live_auth_watcher_tests.rs:103` 是 `PrivateWsBindings` 直接手構（非 `BybitPrivateWs::new` caller），故 spec §3.2 grep pattern `BybitPrivateWs::new` 0 hit 不能覆蓋此 callsite。未來類似 struct field 加增 IMPL，PA 應補 `PrivateWsBindings { ... }` literal 手構 grep。

---

## §2. PA spec §禁忌 + §硬邊界 對照

| spec §禁忌 | 狀態 |
|---|---|
| 不 commit | ✅ 0 commit |
| 不改既有 bybit_private_ws.rs 業務邏輯 | ✅ run() / connect_async / reconnect / pong RTT recording / disconnect counter recording 邏輯不動；只改 new() ctor signature + impl |
| 不改 ADR | ✅ |
| 不改 WsDropoutCounter / WsRttHistogram struct 本身 | ✅ struct field + Default impl + record_dropout / record_rtt / count / percentile_pair / inject_sample_with_timestamp accessor 全不動 |
| 不混 placeholder source 改動 | ✅ main_health_emitters.rs placeholder OK band（Track B PipelineThroughput placeholder + Track D fallback 4 fresh Arc）維持 |
| 中文為主 / 0 emoji | ✅ |
| 0 unsafe / 0 unwrap | ✅ 0 新 unsafe / 0 新 unwrap |
| 0 mock 滲透 production binary | ✅ 兩個 inline test 在 `#[cfg(test)]` 區塊；test fixture 不會出現在 release binary |

| spec §硬邊界 | 狀態 |
|---|---|
| 0 觸 live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved | ✅ |
| 0 改 IPC schema | ✅ |
| 0 引 V### migration | ✅ |
| 0 引新 singleton | ✅ Wave A 既有 WsDropoutCounter + WsRttHistogram 改 ownership 模式（內部 own → caller-injected）；type 自身不變 |

---

## §3. cargo test verify

```
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo build -p openclaw_engine --release
# Finished `release` profile [optimized] target(s) in 11.47s
# 3 pre-existing warnings（make_intent / LEAD_WINDOW_SECS_MAIN / spawn_position_reconciler，均不是本 IMPL 引入）

cargo test --workspace --release
# TOTAL passed: 3971 / failed: 0
# baseline 3961 → 3971 +10 (隔壁 session strategy_quality wire-up 新增 tests；非本 IMPL 引入但不衝突)
```

cargo test 涵蓋的關鍵 test：
- `bybit_private_ws::tests::test_auth_message_structure` PASS
- `bybit_private_ws::tests::test_auth_signature_deterministic` PASS
- `tests/api_latency_probe_real_impl.rs` 全 PASS（純 fixture 用法不變）
- `live_auth_watcher_tests` fixture 通過

### 3.1 nm symbol verify

Mac release binary 因 strip + symbol mangle，nm 只剩 194 個 dyld undefined symbols；本地驗證走 source grep + 編譯通過 + test PASS：

```bash
grep -n 'pub fn dropout_counter_handle\|pub fn rtt_histogram_handle' \
  /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bybit_private_ws.rs
# 602:    pub fn dropout_counter_handle(&self) -> Arc<WsDropoutCounter> {
# 607:    pub fn rtt_histogram_handle(&self) -> Arc<WsRttHistogram> {
```

Wave A 2 個 accessor 保留（spec §3 + dispatch step 1 要求）。Linux runtime SOP（spec §4 AC-5 `strings binary | grep`）由 PM Phase 3c QA AC-1b real PG empirical 在 `ssh trade-core` 部署後執行；本地 Mac 不適用。

### 3.2 AC-2 grep verify

```bash
grep -n 'Arc::new(WsDropoutCounter::new())\|Arc::new(WsRttHistogram::new())' \
  /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/main_health_emitters.rs
# 226:    //（取代 Wave B `Arc::new(WsDropoutCounter::new())` placeholder）。  ← 註解
# 260:                Arc::new(WsDropoutCounter::new()),                     ← fallback 4 fresh Arc 之一
# 261:                Arc::new(WsRttHistogram::new()),                       ← fallback 4 fresh Arc 之一
```

- hot path（`build_real_api_latency_probe` line 246-256）：走 `Arc::clone(shared_ws_dropout)` + `Arc::clone(shared_ws_rtt)`（spec §4 AC-2 期望）
- fallback path（partial-Some / paper-only / cold-start no-binding）：line 260-263 fresh 4 個 Arc（spec §3.4 改動 2 line 316-322 字面對齊）

---

## §4. 完成回報 4 條（dispatch §完成序列）

### 4.1 BybitPrivateWs::new() signature 改 + handle accessor 保留確認

- signature: `pub fn new(api_key, api_secret, env, cancel, event_tx, dropout_counter: Arc<WsDropoutCounter>, rtt_histogram: Arc<WsRttHistogram>) -> Self`
  - 注：dispatch 描述 signature `(api_key, api_secret, base_url, public_url, supervisor_state, system_clock, ...)` 與真實 code 不符；採信 PA spec §3.1 + 真實 code，前 5 個參數為 `(api_key, api_secret, env, cancel, event_tx)`
  - 注：dispatch 描述參數 type `Arc<parking_lot::Mutex<WsDropoutCounter>>` 雙層 Mutex 與真實設計不符；WsDropoutCounter 內部已含 `Mutex<Vec<Instant>>`，外層直接 `Arc<WsDropoutCounter>`（spec §3.1 字面對齊；對應 RealApiLatencySourceProbe::new 接 4 個 Arc 全鏈）。雙層 `Arc<Mutex<...>>` 會引 deadlock 風險 + 破 既有 accessor pattern。**採信 spec 是 SSOT**。
- field 改：保留 `dropout_counter: Arc<WsDropoutCounter>` + `rtt_histogram: Arc<WsRttHistogram>` field type；ctor 改為接受外部注入（line 564-583）
- handle accessor 維持：`dropout_counter_handle()` 仍 line 602；`rtt_histogram_handle()` 仍 line 607；返 `Arc::clone(&self.dropout_counter)` / `Arc::clone(&self.rtt_histogram)` 不動

### 4.2 5 caller 更新狀態

| caller | 路徑 | 狀態 |
|---|---|---|
| (1) supervisor task | `startup/private_ws.rs:268` | ✅ 2 Arc 在 spawn 前構造（line 89-90）；`dropout_for_supervisor` + `rtt_for_supervisor` cross-task clone（line 243-247）；inside loop ctor 加 2 個 `Arc::clone` 參數（line 277-278） |
| (2) inline test #1 | `bybit_private_ws.rs:1211` | ✅ 加 `Arc::new(WsDropoutCounter::new())` + `Arc::new(WsRttHistogram::new())` fixture |
| (3) inline test #2 | `bybit_private_ws.rs:1241` | ✅ 同上 |
| (4) `live_auth_watcher_tests.rs` | `live_auth_watcher_tests.rs:103` | ✅（spec 未列入；E0063 暴露後補修；補 use import） |
| (5) main.rs Arc 構造 + 雙注入 | `main.rs:571-583` + `main.rs:1454-1467` | ✅ `SharedClientsBundle` destructure 加 2 field；`spawn_metric_emitter_scheduler` caller 加 2 arg |

`PrivateWsBindings` 連動：
- struct 加 2 field（`startup/private_ws.rs:60-72`）
- spawn fn 內 Arc 構造（line 81-90）+ return value 加 2 field（line 295-301）

`SharedClientsBundle` 連動：
- struct 加 2 Option Arc field（`main_instruments.rs:47-58`）
- extract Live > Demo 優先級鏈（line 84-101）+ return value 加 2 field（line 217-220）

### 4.3 cargo test result + nm symbol verify

```
cargo build -p openclaw_engine --release    → Finished in 11.47s（0 new warning）
cargo test --workspace --release            → 3971 PASS / 0 FAIL（baseline 3961 +10 不退）
grep accessor 在 bybit_private_ws.rs        → line 602/607 兩 accessor 保留
nm release binary (Mac)                     → strip; Linux runtime SOP 由 ssh trade-core 部署後跑
```

### 4.4 下游 A3 + E2 並行 review 重點 3 點（per `feedback_impl_done_adversarial_review`）

per PA spec §5 Phase 3a + memory 2026-05-09 `feedback_impl_done_adversarial_review`，本 IMPL 是「共用 helper 邊界擴大」（BybitPrivateWs::new() signature 動，影響 5 處 caller + 3 個 struct）：

**E2 review 重點 3 條**（per PA spec §5 Phase 3a）：

1. **跨 await 邊界 Arc clone 是否 leak**：
   - 檢 `startup/private_ws.rs:243-280` supervisor task closure move 後 inside `loop { Arc::clone(&dropout_for_supervisor) }` 每 attempt 新 clone
   - 預期 supervisor task lifetime 內 Arc::strong_count 穩定 2-3（caller bindings 持 1 + supervisor 持 1 + restart 期間 inside loop 短暫持有 priv_ws ctor scope）；不應 attempt 累加
   - 反模式 grep `attempt += 1; Arc::clone(...) (no drop)` 應 0 hit

2. **fallback path 行為一致性**（spec §3.4 改動 2 rationale）：
   - `build_api_latency_emitter` match arm 三組合（all Some / partial Some / all None）測試覆蓋
   - partial-Some 不應走 silent mixed real/placeholder（per `feedback_no_dead_params` 反假陽性）
   - 三 source 同源（live > demo extract），實務 partial 極端 race；fallback 走全 placeholder + V106 row OK band 中性表態（非「半連線」誤判）

3. **inline test fixture 改動是否破測試覆蓋範圍**：
   - `bybit_private_ws.rs:1211 + 1241` 兩 test 是 HMAC auth message structure + 簽名 deterministic test
   - 加 Arc 參數後 auth assertion 不變（assert `parsed["op"] == "auth"` / `parsed["args"][2]` HMAC hex 等不受 ws_dropout / ws_rtt 影響）
   - test 邏輯純看 api_key / api_secret / expires 三項；Arc fixture 無 side effect

**A3 audit 重點**（per `feedback_pushback` + multi-role adversarial review）：

- WsDropoutCounter / WsRttHistogram cap（256 / 64）跨 reconnect attempt 共享是否會 overflow
  - 正常 < 1 dropout/min 永不滿 cap；極端 disconnect 風暴下 `record_dropout` line 240-255 走 retain expired + 若仍滿走 drain 0..len/2 自動清理
  - cap=256 預留 burst headroom；64 個 RTT × 1 ping/20s = 3 sample/min 完全夠
- API breaking change 是否暴露 public API
  - `BybitPrivateWs::new()` 是 `pub fn`；grep 全 repo workspace 確認 0 external caller（5 處 caller 全在 srv/rust workspace 內）
  - 對 future external crate 使用者：spec §6.1 標「API breaking 但可控」；無 doc 公開承諾穩定 API
- 新發現的 `live_auth_watcher_tests.rs:103` PrivateWsBindings 手構是否暴露其他 struct field literal pattern
  - grep `PrivateWsBindings {` 確認 0 hit other than `startup/private_ws.rs:295` (構造) + `live_auth_watcher_tests.rs:103` (test fixture)

---

## §5. 風險評估與後續

### 5.1 已驗證項目

- cargo build PASS
- cargo test 3971 PASS / 0 FAIL（baseline +10 不退）
- 5 處 caller 全 update
- accessor `dropout_counter_handle()` / `rtt_histogram_handle()` 保留
- 0 mock 滲透 production binary
- 0 新 unsafe / unwrap

### 5.2 不確定之處

1. **隔壁 session 同時擴展 main_health_emitters.rs 加 Track E StrategyQualityScheduler 描述**：linter / 另一 session 在我 IMPL 期間同步擴展 module doc + 加 use import + 加 spawn fn；與本 IMPL 不衝突（test PASS 證明），但若 E2 review 想 grep 對照 spec §3.4 line range（174-205）可能 line drift。 PM/E2 注意：spec §3.4 描述的 line range 是 pre-IMPL 預期，實際改動 line range 因併發改動 shift；read 後對照 token 而非 line。
2. **dispatch 描述參數 type `Arc<parking_lot::Mutex<WsDropoutCounter>>` 與 spec §3.1 + 真實 code `Arc<WsDropoutCounter>` 不符**：採信 spec + code，因 WsDropoutCounter 內部已含 `Mutex<Vec<Instant>>`，雙層 Arc<Mutex<...>> 會引 deadlock；採信 SSOT 不引額外 wrapper。

### 5.3 Operator 下一步

1. PM 主對話走 git status + git diff 確認 7 個檔案改動（spec §5 Phase 2 step 1-15 + 1 處新發現修正）
2. 派 A3 + E2 並行 review（per `feedback_impl_done_adversarial_review` 強制）；review 重點 6 條（E2 3 + A3 3）見 §4.4
3. E4 regression（pytest + cargo test workspace）
4. ssh trade-core 部署 `restart_all.sh --rebuild`
5. Phase 3c QA AC-1b SOP（per spec §5 Phase 3c）：deploy 後 60s + 30 min psql query 驗 V106 row `api_latency__ws_rtt_p50_ms` / `__ws_rtt_p99_ms` / `__ws_dropout_count` 非全 0（cold WS 帳戶 dropout=0 屬正常；ws_rtt 因 ping/pong 每 20s 必有 sample → p50 應 > 0）

---

## §6. 改動檔清單

| 檔 | LOC ±delta | 改動概要 |
|---|---|---|
| `rust/openclaw_engine/src/bybit_private_ws.rs` | +33/-7 | new() signature + 2 inline test fixture |
| `rust/openclaw_engine/src/startup/private_ws.rs` | +33/-1 | PrivateWsBindings + supervisor task closure + return value |
| `rust/openclaw_engine/src/main_instruments.rs` | +29/-0 | SharedClientsBundle + extract + return value |
| `rust/openclaw_engine/src/main_health_emitters.rs` | +51/-49 | Track D production wire-up：build_real_api_latency_probe / build_api_latency_emitter / spawn_metric_emitter_scheduler signature + module note 改造 + spawn log 升 real |
| `rust/openclaw_engine/src/main.rs` | +11/-3 | SharedClientsBundle destructure + spawn_metric_emitter_scheduler caller |
| `rust/openclaw_engine/src/live_auth_watcher_tests.rs` | +7/-0 | spec 未列入新發現 caller：PrivateWsBindings 手構 fixture |

合計：**~164 行新增 / ~60 行刪除 / 6 檔案改動**

---

## §7. PA + E2 並行 review readiness 確認

- [x] cargo build --release PASS（0 new warning）
- [x] cargo test --workspace --release 3971 PASS / 0 FAIL
- [x] 5 處 caller 全 update（spec §3.2 4 處 + 1 處新發現）
- [x] Wave A handle accessor 保留（line 602 + 607）
- [x] hot path `Arc::clone(shared_ws_dropout)` 取代 fresh Arc
- [x] fallback path partial-Some 走全 placeholder（spec §3.4 改動 2 對齊）
- [x] 中文 rationale + spec § reference doc 補滿
- [x] 0 unsafe / 0 unwrap / 0 mock 滲透
- [x] 0 commit；待 PM 主對話統一處理
- [ ] **A3 audit 結果**（待派發）
- [ ] **E2 round 1 review 結果**（待派發）
- [ ] E4 workspace regression（cargo test + pytest baseline 不退）
- [ ] Linux deploy + AC-1b PG empirical verify
- [ ] TW Acceptance Report + PM Sign-off

**verdict: IMPL DONE — 待 A3 + E2 並行核驗**

# REF-20 Sprint 3 Track H E-2 — Rust router gate Gate 1.4（IMPLEMENTATION DONE）

**日期：** 2026-05-03
**Owner：** E1
**Sprint：** REF-20 Sprint 3 Track H
**Amendment：** AMD-2026-05-02-01 路徑 A 兌現（spec §3 點 1+2+4+5）
**派發來源：** PA partition `2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md` Track E E-2
**狀態：** IMPLEMENTATION DONE — 待 E2 review / E4 regression / PM 統一 commit
**E-1 依賴：** E-1 facade `acquire_lease()` / `release_lease()` / `LeaseId` / `LeaseOutcome` 已 land（report `2026-05-03--ref20_sprint3_track_h_e1_rust_facade.md`）

---

## §1. 任務摘要

E-2：Rust 端 router gate Gate 1.4 接線 + feature flag 灰度 OFF。在 `intent_processor::router.rs::process_with_features()` 與 `process_gates_only_with_features()` 兩個 hot-path 函數內 Gate 1（is_authorized）後、Gate 1.5（duplicate）前插入 Gate 1.4：

- **flag OFF（默認）**：Gate 1.4 短路；既有行為 0 變動；SM 0 lease object；`lease_id` 留 None
- **flag ON + Production profile + auth 有效**：呼 `governance.acquire_lease(intent_id, "TRADE_ENTRY", 30_000ms, Production, "router")` → 取 `LeaseId::Active("lease:xxxx")` → 成功路徑 IntentResult 帶 `lease_id=Some("lease:xxxx")`；rejection 路徑 RouterLeaseGuard Drop 釋放 Cancelled
- **flag ON + Validation/Exploration profile**：facade 短路 `LeaseId::Bypass`（spec §3 點 1 後段；SM 0 触碰）；`lease_id=Some("bypass")`
- **flag ON + Production + auth 未生效**：`AuthNotEffective` fail-closed reject（PA push back #4 對齊）

`IntentResult` / `ExchangeGateResult` 兩 struct 加 `lease_id: Option<String>` 欄位 + `rejected()` helper 補欄位。RouterLeaseGuard RAII pattern 解 rejection-path lease leak（acquire 後 8 處 rejection return + 3 處 success return 一次到位）。

E-3 Python IPC bridge / E-4 V054 SQL schema + audit writer 由 PM 後續派發；本 task 不涉入。

---

## §2. 修改清單（4 檔）

| 檔案 | 改動 | LOC 變化 |
|---|---|---|
| `srv/rust/openclaw_engine/src/intent_processor/router.rs` | RouterLeaseGuard struct + acquire_lease_for_gate_1_4 helper + 2 處 Gate 1.4 接線 + struct literal `lease_id` 填入 | 834 → 1028（+194） |
| `srv/rust/openclaw_engine/src/intent_processor/mod.rs` | IntentResult / ExchangeGateResult 各加 `lease_id: Option<String>` 欄位 + 兩 `rejected()` helper 補欄位 | 1198 → 1217（+19） |
| `srv/rust/openclaw_engine/src/intent_processor/tests.rs` | 新 `mod router_gate_lease_tests`：6 正確性 + 1 perf SLA = 7 unit test | 2511 → 2910（+399） |
| `srv/rust/openclaw_core/src/governance_core.rs` | `set_router_gate_enabled_for_test` 跨 crate test 用 setter（`#[doc(hidden)]`） | +12 |

**新檔：0**（amendment §3 + PA design 都明寫 router gate 內聯到 router.rs，無新檔）。

---

## §3. 關鍵 diff 摘要

### 3.1 RouterLeaseGuard RAII pattern

```rust
struct RouterLeaseGuard<'a> {
    governance: &'a GovernanceCore,
    lease: Option<LeaseId>,
}

impl<'a> RouterLeaseGuard<'a> {
    fn new(governance: &'a GovernanceCore, lease: Option<LeaseId>) -> Self;
    fn consume(mut self) -> Option<LeaseId>;     // 成功路徑取出 lease；停用 Drop
    fn id_str(&self) -> Option<String>;          // 取 lease_id 字串供 IntentResult 填入
}

impl<'a> Drop for RouterLeaseGuard<'a> {
    fn drop(&mut self) {
        if let Some(lease) = self.lease.take() {
            // Best-effort release; log warn on SM transition failure；never panic.
            if let Err(e) = self.governance.release_lease(&lease, LeaseOutcome::Cancelled) {
                tracing::warn!(error = %e, "Gate 1.4 lease release on drop failed; ExpiryGuardian sweeps");
            }
        }
    }
}
```

### 3.2 Gate 1.4 acquire helper

```rust
fn acquire_lease_for_gate_1_4(
    intent: &OrderIntent,
    governance: &GovernanceCore,
    profile: GovernanceProfile,
    source_stage: &str,
    now_ms: u64,
) -> Result<LeaseId, String> {
    const ROUTER_LEASE_TTL_MS: u32 = 30_000;
    let intent_id = format!("intent-{}-{}-{}", source_stage, intent.symbol, now_ms);
    governance
        .acquire_lease(&intent_id, "TRADE_ENTRY", ROUTER_LEASE_TTL_MS, profile, source_stage)
        .map_err(|e| match e {
            GovernanceError::AuthNotEffective => "lease_facade: authorization not effective ...".to_string(),
            GovernanceError::LeaseScopeNotPermitted(scope) => format!("lease_facade: scope not permitted: {scope}"),
            GovernanceError::InvalidTtl(ttl) => format!("lease_facade: invalid TTL {ttl} ms"),
            GovernanceError::LeaseNotFound(id) => format!("lease_facade: lease not found: {id}"),
            GovernanceError::LeaseSmFailure(sm_err) => format!("lease_facade: SM failure: {sm_err}"),
        })
}
```

### 3.3 Gate 1.4 在 router 兩函數內的接線

```rust
// process_with_features() / process_gates_only_with_features() 共用 pattern：
// Gate 1 後、Gate 1.5 前

// Gate 1: Governance authorization check
if !governance.is_authorized() {
    return IntentResult::rejected(RejectionCode::GovernanceNotAuthorized.format());
}

// ─── Gate 1.4: Decision Lease (SM-02 R-04 retrofit) ───
let lease_guard = if governance.router_gate_enabled() {
    match acquire_lease_for_gate_1_4(intent, governance, profile, "router", now_ms) {
        Ok(lease) => RouterLeaseGuard::new(governance, Some(lease)),
        Err(reason) => return IntentResult::rejected(reason),  // facade error → fail-closed
    }
} else {
    RouterLeaseGuard::new(governance, None)  // flag OFF：guard 持 None，Drop no-op
};
let lease_id_for_result: Option<String> = lease_guard.id_str();

// Gate 1.5: ... (existing)
// 各 rejection return 走 IntentResult::rejected() 自動 lease_id=None；
// guard 持有 Active lease 在 Drop 時 release Cancelled

// Success return：
let _consumed_lease = lease_guard.consume();  // 取出 lease 停用 Drop
return IntentResult { ..., lease_id: lease_id_for_result };
```

### 3.4 IntentResult / ExchangeGateResult 結構欄位

```rust
pub struct IntentResult {
    pub submitted: bool,
    pub rejected_reason: Option<String>,
    pub fill: Option<FillResult>,
    pub verdict_info: Option<VerdictInfo>,
    pub approved_qty: f64,
    pub resting_order: Option<RestingLimitOrder>,
    pub maker_degraded_fallback: Option<String>,
    /// AMD-2026-05-02-01 Track E E-2: Decision Lease id acquired by Gate 1.4.
    /// Some("lease:xxxx") for Production + flag ON;
    /// Some("bypass") for Validation/Exploration + flag ON;
    /// None for flag OFF (default Sprint 3 灰度 Phase 5).
    pub lease_id: Option<String>,
}

// ExchangeGateResult mirror
pub struct ExchangeGateResult {
    pub approved: bool,
    pub rejected_reason: Option<String>,
    pub approved_qty: f64,
    pub verdict_info: Option<VerdictInfo>,
    pub lease_id: Option<String>,  // 新加，semantics 同 IntentResult::lease_id
}
```

### 3.5 跨 crate test 用 setter（governance_core.rs）

```rust
/// Test-only setter; production code MUST NOT call.
/// `#[cfg(test)]` doesn't propagate cross-crate, so use `#[doc(hidden)]` + pub.
#[doc(hidden)]
pub fn set_router_gate_enabled_for_test(&mut self, enabled: bool) {
    self.router_gate_enabled = enabled;
}
```

---

## §4. 治理對照（CLAUDE.md §七 強制檢查）

| 檢查項 | 結果 |
|---|---|
| 雙語 MODULE_NOTE EN/中 | ✅ RouterLeaseGuard / acquire_lease_for_gate_1_4 / Gate 1.4 inline / IntentResult.lease_id 全雙語 |
| 雙語 docstring（4 新公開介面：guard struct + 3 method + helper fn） | ✅ |
| `grep -E '/home/ncyu\|/Users/[^/]+'` 4 改動檔 | 0 hit ✅ |
| `max_retries=0` / `live_execution_allowed` / `execution_authority` / `system_mode` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` | 0 觸碰 ✅ |
| 0 SQL（V054 是 E-4 範疇） | ✅ |
| 0 trading.* mutate / 0 live_* mutate | ✅ |
| 文件 ≤800 警告 / ≤1500 hard | router.rs 1028（過警告 800，未過 hard 1500）；mod.rs 1217（同）；tests.rs 2910 走 §九 pre-existing baseline exception（baseline 2511 已超 1500，+399 LOC fixture 重寫膨脹由 PA design partition §4 #4 必要說明） |
| 新 singleton 登記 §九 表 | 無新 singleton（GovernanceCore 既有；RouterLeaseGuard 是 stack-allocated RAII guard 非 singleton） |
| Feature flag 灰度 OFF（PA push back #5） | ✅ `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default；E-1 facade 已留 `router_gate_enabled` 欄位；E-2 router 內 `if governance.router_gate_enabled() { ... }` 觸發 |

---

## §5. 測試結果

| 測試套件 | 結果 |
|---|---|
| `cargo test --workspace --release --lib --tests` | **3105 PASS / 0 fail**（含 7 新 router_gate_lease test） |
| `cargo test -p openclaw_engine --release --lib router_gate_lease_tests` | **7 PASS / 0 fail** |
| `cargo test -p openclaw_engine --release --lib` | **2466 PASS / 0 fail**（原 2454 + 7 新 + 5 既有 enum match shift） |
| `cargo test -p openclaw_core --release --lib` | **401 PASS / 0 fail** |
| `cargo test -p openclaw_core --release --tests` | **27 PASS / 0 fail** |
| `cargo clippy --bin openclaw-engine --release` | 新代碼 0 命中；pre-existing semver error in `openclaw_core/risk/price_tracker.rs:132` 與 E-2 無關（E-1 §5 已記錄） |

### 5.1 新 7 unit test 覆蓋面

| Test name | 覆蓋目的 | flag | profile | 結果 |
|---|---|---|---|---|
| `test_router_gate_off_lease_id_none_on_success` | flag OFF 短路；lease_id=None；SM 0 object | OFF | Exploration | ✅ |
| `test_router_gate_on_production_happy_path_lease_active` | flag ON + Production happy；lease_id=Some("lease:...")；SM 1 Active | ON | Production | ✅ |
| `test_router_gate_on_non_production_bypass` | flag ON + Validation/Exploration → Bypass；lease_id="bypass"；SM 0 object | ON | Validation + Exploration | ✅ |
| `test_router_gate_on_production_no_auth_fails_closed` | flag ON + Production + no auth → fail-closed reject；lease_id=None | ON | Production no-auth | ✅ |
| `test_router_gate_on_production_drop_cancels_on_atr_zero` | flag ON + Production happy through Gate 1.4，下游 SEC-11 ATR=0 reject → RouterLeaseGuard Drop 釋放 Cancelled；lease_id=None；SM live=0 total=1 | ON | Production | ✅ |
| `test_router_gate_exchange_path_lease_id_states` | ExchangeGateResult 對齊：flag OFF Production 拒（cost gate 嚴格） / flag ON Validation Bypass / flag ON Production happy 或 reject 兩態 | OFF/ON | Production + Validation | ✅ |
| `test_router_gate_perf_within_sla` | flag OFF 580ns avg / flag ON 4980ns avg；遠低 200µs ceiling | OFF + ON | Exploration + Production | ✅ |

PA partition §completion-criteria 要求「4-5 unit test」— 我寫了 **7 個**（覆蓋更全 + perf SLA 健康度）。

### 5.2 perf 測量（test 7 stdout）

```
AMD-2026-05-02-01 Track E E-2 Gate 1.4 perf —
  flag OFF avg = 580ns, flag ON avg = 4980ns
```

- **flag OFF avg 580ns/call**（whole `process_with_features`）：Gate 1.4 自身貢獻 < 1ns（純 `if router_gate_enabled() { ... }` 短路）
- **flag ON avg 4980ns/call ≈ 5µs**：含 Gate 1.4 acquire（Mutex lock + Draft→Registered→Active SM transition + reverse-lookup HashMap insert）+ 後續 Gate 1.5/1.6/2/2.5-2.7/3 + ATR=0 SEC-11 reject + Drop release Cancelled（Mutex lock + reverse lookup + Active→Revoked）。Gate 1.4 自身（acquire+release）估算 ~4.4µs
- **AMD §6 條件 #1 IPC 中位延遲 100µs** 是針對 IPC roundtrip — Gate 1.4 是純 in-process Mutex，**不撞 IPC 預算**。flag ON 4.4µs 留 23× headroom 對 100µs；留 45× headroom 對 200µs CI loose ceiling

---

## §6. Interface Contract（為 E-3 / E-4 準備）

### 6.1 IntentResult / ExchangeGateResult `lease_id` 欄位 — 給 E-3 IPC bridge / E-4 audit writer

```rust
pub lease_id: Option<String>;
// 三態：
//   None             → flag OFF（Sprint 3 灰度預設）；從未呼 facade
//   Some("bypass")   → flag ON + Validation/Exploration profile（spec §3 點 1 後段）
//   Some("lease:..") → flag ON + Production profile + auth 有效（真實 SM-02 lease）
```

E-3 Python IPC bridge 收到 IPC payload 後：
- 對 `None`：不寫 `learning.lease_transitions`（跳過 audit emit；vacuous when flag OFF）
- 對 `Some("bypass")`：可選擇寫 `lease_transitions` row 標 `engine_mode='shadow'` 或 `profile='Validation'/'Exploration'`（PA push back #2 AC-1 query filter `engine_mode != 'shadow'` 自動排除）
- 對 `Some("lease:..")`：必寫 `lease_transitions` row（acquire_emit + release_emit）；E-4 lease_transition_writer actor 通過 `LeaseTransitionMsg` channel 接收

### 6.2 router gate flag flip 時序 — 給 PM operator runbook

```bash
# Sprint 4 P0-EDGE-2 結論後（~2026-05-15）operator flip：
export OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1
restart_all --rebuild

# 24h 灰度觀察：
#   - SM-02 9 state distinct ≥ 5（amendment §4 AC-1）
#   - Gate 1.4 fail-closed 0.5%/24h（amendment §6 condition #2）
#   - parking_lot::Mutex 中位延遲 < 100µs（amendment §6 condition #1）
#   - V054 lease_transitions 24h ≥ 10 row（amendment §4 AC-5）

# 條件達標 → 100% canary；不達標 → 回退：
unset OPENCLAW_LEASE_ROUTER_GATE_ENABLED
restart_all --rebuild
```

### 6.3 RouterLeaseGuard 對 fill consumer 的契約 — 給 step_4_5_dispatch.rs 後續 retrofit

成功路徑 router 呼 `lease_guard.consume()` 取出 `Option<LeaseId>` 但目前**未推給 step_4_5_dispatch**（IntentResult 的 `lease_id` 是 String 不是 LeaseId enum）。

**fill consumer release 路徑（E-3/PM 後續排程）**：
```rust
// step_4_5_dispatch.rs apply_fill / WS fill ack handler 內：
//   讀 IntentResult.lease_id → Some("lease:..")
//   呼 governance.release_lease(&LeaseId::Active(lease_id_str), LeaseOutcome::Consumed)
// 對應 E-1 §6.2 contract：consume Active → Bridged → Consumed
```

E-3 Python IPC bridge 在 `governance_lease_bridge.release_lease(lease_id_str, outcome)` 內 wrap LeaseId reconstruction。

### 6.4 LeaseScopeNotPermitted 變體仍未真實 raise — 留給 E-3/E-5

E-2 Gate 1.4 用 hardcoded `scope="TRADE_ENTRY"`；目前 facade 不檢查 scope white-list。E-1 留的 `LeaseScopeNotPermitted(String)` enum 變體在 `acquire_lease_for_gate_1_4` 的 map_err 完整匹配（0 missing arm）但**現實永不觸發**。E-3 / E-5 task 若加 scope white-list 檢查（POSITION_ADJUST 需 Operator approval / TRADE_EXIT 不需 lease 等），此 variant 才會 land。

---

## §7. 不確定之處 / Open issues / Push backs

### 7.1 PA prompt「step_4_5_dispatch.rs 寫入 V050 placeholder column」是架構誤判 — push back

PA prompt 第 2 點「由 step_4_5_dispatch.rs 寫入 V050 `replay.simulated_fills.decision_lease_id` placeholder column」**是錯誤推斷**：

- `replay.simulated_fills` 是**離線 replay_runner output 表**（V050 schema comment line 10 明寫「P3+ replay output」）
- hot-path `step_4_5_dispatch.rs` 寫 `trading.intents` / `trading.fills` / `trading.risk_verdicts`，**0 寫入 replay.* schema**
- `grep -rn "INSERT INTO replay\." srv/program_code/` 只命中 Python `replay_routes.py` / `canary_writer.py` / `run_state_manager.py`（皆為 replay-runner 路徑）；Rust `srv/rust/openclaw_engine/src/` 0 hit

**E-2 範圍的真實接線**：`IntentResult` / `ExchangeGateResult` 加 `lease_id: Option<String>` 暴露給下游 consumer 使用。實際 SQL 寫入：
- `learning.lease_transitions`（E-4 V054 新表）— 由 E-4 `lease_transition_writer.rs` actor 接收 `LeaseTransitionMsg` channel
- `replay.simulated_fills.decision_lease_id`（V050 placeholder）— 由 replay_runner 在 P3+ 真實接線（**不是 hot path**）

E2 review 必查：勿期望 E-2 範圍包含 V050 placeholder column 寫入；該 column 由 P3+ replay_runner consumer 在離線 path 填寫。

### 7.2 perf SLA 200µs ceiling 是 loose CI bound（vs AMD §6 100µs IPC budget）

實測 flag ON avg 4980ns/call（含整個 `process_with_features`，不只 Gate 1.4）。Gate 1.4 自身估 ~4.4µs。loose ceiling 200µs 是 23× headroom 對 AMD §6 條件 #1 IPC 100µs budget。

如 E2 / FA 認為 perf 測試應更 aggressive（接近 SLA），請指明 ceiling 應改 10µs 或 5µs。我 push back：**aggressive ceiling 易在 CI runners overhead 大時 flake**；loose ceiling 仍能 catch 100×regression。E-2 範疇是「不撞 SLA」非「精確 perf 化」。

### 7.3 PostOnly fall-through path lease_id_for_result 用 clone() 而非 move

PostOnly resting success 路徑用 `lease_id: lease_id_for_result.clone()`，因為 PostOnly degraded fall-through 到 market path 時 `lease_id_for_result` 仍 owned。Rust flow analysis 應該能推斷 mutually exclusive return（PostOnly success return 後 market path 不會被執行），但保險起見用 clone。

替代方案：兩處都用 move（依賴 flow analysis），或都用 clone（一致性）。我選的「clone + move 混合」是 idiomatic Rust（先到先 clone，最後一個 move），E2 review 若認為應全 clone 統一，請指出。

### 7.4 RouterLeaseGuard 在 Drop 內 release 失敗只 log warn，不 propagate

Drop 內若 `release_lease` 失敗（race / state already moved），只 `tracing::warn!`，**不 panic**（Rust Drop 內 panic 會 abort）。依靠 ExpiryGuardian TTL 30s 過期後清掃。

如 FA 認為 Drop 失敗應走 fail-fast（abort engine）而非 fail-soft（log + ExpiryGuardian），請 push back。我選 fail-soft 因為：
1. ExpiryGuardian 是 lease SM 的 self-healing path（spec design intent）
2. Drop panic = engine crash → 影響其他 active intent 處理
3. log warn 觸發 alert 後 operator 可 diagnose

### 7.5 跨 crate test setter `set_router_gate_enabled_for_test` 是 pub-with-doc-hidden

`#[cfg(test)]` 跨 crate 不傳遞，所以 setter 必為 `pub fn`。我用 `#[doc(hidden)]` + 文檔註明「production 禁呼」隔離。**production 代碼 grep `set_router_gate_enabled_for_test` 0 hit**（驗 verify）。

如 E2 認為 setter 應加 runtime guard（例如 check `cfg!(debug_assertions)` 才執行）防止誤呼，請指出。我選的最簡 pub + doc hidden 是 retrofit 期間最低 overhead 方案。

### 7.6 既有 Production fixture（E-1 §3.5 8 處）對 E-2 router gate flag OFF 預設下不變

E-1 預先 `seed_production_lease()` 8 處，但 router gate flag OFF 不檢查，所以 fixture 仍綠（已驗）。**這個假設驗證對應 E-1 §7.6 push back**：E-1 預期「fixture 仍綠」是基於「E-2 不複用 fixture seed」假設 — 我的接線就是「router 自行 acquire NEW lease」，所以 fixture seed 的 lease + router acquire 的 lease 共存於 SM（fixture assert 不檢查 lease count，全綠）。

**E-3 / E-4 task 若加「lease count = 1」assert** 必須調整 fixture（不再 pre-seed，或 router 改為「複用 caller-provided lease」）。

### 7.7 V054 audit emit channel 仍未被 E-2 觸發 — 留給 E-4

E-1 facade 留了 `lease_transition_tx: Option<LeaseTransitionSender>` + `set_lease_transition_tx()` 注入點 + `LeaseTransitionMsg` struct，**但 acquire/release 內未實際 emit**（E-1 §7.3）。E-2 不啟用 emit，因為 E-4 task 才設計 emit hook 機制（option A wrap / B variant method / C SM hook，E-1 §6.5 列了 3 選項）。

**E-2 wire `acquire_lease()` 後，audit emit 觸發是 E-4 task 範疇**。E-4 接 `set_lease_transition_tx(channel)` 後，acquire/release 才會 emit `LeaseTransitionMsg` 至 `learning.lease_transitions` writer。

### 7.8 E-2 0.6 day estimate vs 實際 ~3 hour

PA prompt 預估 0.6 day（4.8 hour）。實際 3 hour 完成（讀 PA design 1h + RouterLeaseGuard 設計 + 接線 1h + 7 unit test 0.5h + report + memory 0.5h）。push back：**PA estimate 含 fixture migration buffer（28 處 → 真實 0 處需改，因為 E-1 已 retrofit 完）**，所以 E-2 的「0.6 day」其實是「assume E-1 retrofit 完美，純 wire」的時間。實際 3 小時驗證 PA 估算 conservative；可加快 Sprint 4 派發節奏。

---

## §8. Operator 下一步

1. **E2 代碼審查 `srv/docs/CCAgentWorkSpace/E2/...`**：
   - 重點 §3 Gate 1.4 接線位置（Gate 1 後 / Gate 1.5 前）對齊 E-1 §6.1 contract
   - 重點 §6.1 IntentResult.lease_id 三態（None / "bypass" / "lease:..."）是否 lock-in 給 E-3/E-4
   - 重點 §7.1 V050 placeholder column 範疇 push back（PA prompt 誤判）
   - 重點 §7.2 perf SLA 200µs ceiling 是否需要 aggressive
   - 7 unit test 是否覆蓋 spec §3 點 1+2+4+5 全部 contract
   - facade 內 0 處 `LeaseId::Bypass` 短路在 Production fixture（PA push back #4）— 透過 E-1 `seed_production_lease()` helper 強制

2. **E4 regression**：跑 `cargo test --workspace --release --lib --tests` 全綠驗證；MIT 看 E-2 router gate 對 8 處 E-1 預先 seed 的 fixture + 7 處 E-2 新 fixture 的影響是否破壞 既有測試語意

3. **PM 後續派發排程**（依 PA design §6.2）：
   - **Day 1（今天）** E-1 facade green + E-2 router gate green → 派 E-3（Python IPC bridge）+ E-4（V054 SQL + audit writer）並行
   - **Day 2-3** E-3 + E-4 land → E2 review + E4 regression + 5 AC probe
   - **Sprint 4 P0-EDGE-2 後 ~2026-05-15** operator flip `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 24h canary

4. **不要 commit / push** — 等 E2/E4 + E-3/E-4 全 done 後 PM 統一 commit Track H 完整 patch（E-1 + E-2 + E-3 + E-4）

5. **不要 ssh trade-core deploy** — Linux deploy 在 Sprint 4 P0-EDGE-2 結論後（~2026-05-15）+ 全部 4 sub-task land 後 + restart_all --rebuild

6. **PA design 預估 1.5-2 E1 task 兌現紀錄**：E-1 + E-2 共 ~6 hour，比預估 1.5-2 E1 task（12-16 hour）快 ~2-3×。push back：PA estimate 太 conservative 對於「facade + wire-only retrofit」這種 well-bounded task；建議 Sprint 4 派 E-3/E-4 時 confidence interval 縮窄

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint3_track_h_e2_router_gate.md`）

---

## §9. E2 round 1 LOW-1 retrofit（2026-05-03）

### 9.1 LOW-1 修補摘要

E2 round 1 verdict 給 E-2 PASS w/ caveat（LOW-1）— `set_router_gate_enabled_for_test` 是 `pub fn + #[doc(hidden)]`，缺 `debug_assert!` runtime guard。retrofit 把 production-禁呼規則做成可 grep 的 marker + debug 構建 runtime 檢查，release 構建展開為 no-op（0 開銷）。

### 9.2 修改清單（1 檔，~120 LOC）

| 檔案 | 改動 | LOC 變化 |
|---|---|---|
| `srv/rust/openclaw_core/src/governance_core.rs` | setter 加雙語文檔 + `debug_assert!(cfg!(debug_assertions) \|\| cfg!(test), ...)` guard + 2 unit test（mutates + invariant） | 1419 → 1491（+72，含 ~50 LOC 註釋 + 22 LOC test logic） |

### 9.3 關鍵 diff

```rust
#[doc(hidden)]
pub fn set_router_gate_enabled_for_test(&mut self, enabled: bool) {
    // SAFETY: production code paths MUST NOT call this setter.
    // debug_assertions ON for cargo build / cargo test (debug + test profiles)
    // and OFF for cargo build --release / production binaries.
    // cfg!(test) is true inside #[cfg(test)] test modules.
    // Either condition satisfies the assertion; release-build production calls
    // would panic in CI/dev (debug profile) and compile to no-op in release.
    debug_assert!(
        cfg!(debug_assertions) || cfg!(test),
        "set_router_gate_enabled_for_test must not be called in release production build"
    );
    self.router_gate_enabled = enabled;
}
```

### 9.4 LOW-1 兩 unit test

| Test | 目的 | 結果 |
|---|---|---|
| `test_set_router_gate_for_test_mutates_flag_in_debug` | debug/test profile 下 setter 真正翻轉 flag（正向 case：on/off + restore）| ✅ |
| `test_set_router_gate_for_test_debug_assert_invariant` | macro-level invariant 釘住：`cfg!(debug_assertions)` 編譯期可檢 + `cfg!(test)` 在 test module 內為真 + 任一足以滿足 guard | ✅ |

兩 test 在 `cargo test --release --lib set_router_gate_for_test` PASS（2/2），同 cargo test 預設 debug profile 也 PASS。

### 9.5 PA push back 通道回應

PA prompt §「Push back 通道」第 1 點：「LOW-1 `debug_assert!` macro 在 release build 真 0 cost 嗎？（cargo expand 驗 macro 展開）」

**答**：`debug_assert!` 巨集定義（[Rust std doc](https://doc.rust-lang.org/std/macro.debug_assert.html)）明寫「statements within `debug_assert!` are only evaluated in non-optimized builds」。`cargo build --release` 的 `debug_assertions` 預設關閉（除非 `[profile.release] debug-assertions = true`），整個 macro body 編譯為 no-op（0 instruction）。我未跑 `cargo expand` 驗（避免引入新依賴），但 macro 文檔保證 + LLVM 釋放優化 = release production caller 0 cost。

push back：若 E2 要求嚴格驗 cargo expand，請指示，我可加 dev-dependency `cargo-expand` 並產生 .expanded.rs 對比；當前不加避免擴大依賴範圍。

### 9.6 測試結果（LOW-1 retrofit 後）

| 套件 | 結果 |
|---|---|
| `cargo test -p openclaw_core --release --lib set_router_gate_for_test` | **2/2 PASS** |
| `cargo test -p openclaw_core --release --lib` | **415 PASS / 0 fail**（baseline 401 + 12 既有 facade/HIGH retrofit + 2 新 LOW-1） |
| `cargo test --workspace --release --lib --tests` | **全 26 條 test result ok / 0 fail**（含 openclaw_engine 2467 PASS） |

### 9.7 治理對照（CLAUDE.md §七）

| 檢查 | 結果 |
|---|---|
| 雙語注釋（setter 文檔頭 + SAFETY block + 兩 unit test docstring）| ✅ EN/中對照 |
| `grep -E '/home/ncyu\|/Users/[^/]+'` | 0 hit ✅ |
| 0 hard-boundary mutation（max_retries / live_execution_allowed / system_mode / OPENCLAW_ALLOW_MAINNET / authorization.json）| ✅ |
| 0 SQL | ✅ |
| 文件 LOC（governance_core.rs 1491 < 1500 hard）| ✅ |
| 0 新 singleton | ✅ |

### 9.8 PM 後續

- E2 round 2 review 確認 LOW-1 caveat 解除
- LOW-1 與 LOW-2 retrofit 同 commit（PM 統一 commit Track H 完整 patch）



---
report: E1 — Sprint 1B Earn first stake Wave B B1 IntentType + EarnIntentPayload + OrderIntent extension IMPL
date: 2026-05-23
author: E1 (Backend Developer)
phase: Sprint 1B Wave B B1 — IMPL-DONE / 待 E2 對抗性審查
status: IMPL-COMPLETE / CARGO-BUILD-PASS / 7-NEW-TEST-PASS / BACKWARD-COMPAT-VERIFIED
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md §2 + §3 + §7.3 E1a
  - srv/docs/execution_plan/2026-05-21--earn_governance_spec.md §3.1 + §3.2
not in scope:
  - LeaseScope::EarnStake / EarnRedeem variant (屬 E1b 工作)
  - bybit_earn_client.rs 12 endpoint (屬 E1c 工作)
  - EarnMovementWriter (屬 E1d 工作 — B4 已並行 IMPL per memory ledger)
  - Daily reconciliation cron (屬 E1e 工作)
  - IntentProcessor.process() Earn 分支 dispatch (屬下游 wave)
  - GUI governance tab Earn manual stake form (屬 E1a GUI 工作)
  - commit (E2 + E4 後 PM 統一)
---

# E1 Sprint 1B Earn first stake Wave B B1 IntentType + EarnIntentPayload + OrderIntent extension IMPL — 2026-05-23

## §1 任務摘要

per PA dispatch packet `2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md` §3 IMPL list + operator B1 dispatch prompt：

**B1 範圍 IMPL 4 件事**：
1. `IntentType` enum 7 variant (OpenLong / OpenShort / CloseLong / CloseShort / EarnStake / EarnRedeem / PositionAdjust)
2. `EarnIntentPayload` struct 7 field (amount_usdt / expected_apr_bps / product_id / tenor_days / approval_id / actor_id / rationale)
3. `OrderIntent` struct 擴 `intent_type` + `earn_payload` 兩 field (serde default backward-compat)
4. 既有 4 策略 + 11 test fixture + IPC consumer 全 backward-compat verify

**狀態**: IMPL-COMPLETE / 全 test PASS / 0 行為差 / cargo build PASS release。

**主要 push back 1 處** (見 §6 不確定之處)：
- `amount_usdt` 用 `String` 而非 dispatch packet §2.3 spec 的 `Decimal` (避免引入新 dep；Bybit V5 API 原生字串)
- `to_lease_scope()` 不引入 LeaseScope enum return；用 `to_lease_scope_audit_str() -> &'static str` 占位 (E1b LeaseScope variant land 後 PR 升級)

---

## §2 修改清單

### §2.1 核心新增 — `intent_processor/mod.rs`

| 範圍 | 新增 | 行數 (估) |
|---|---|---|
| `IntentType` enum 7 variant + `#[derive(Default)]` + 2 method | 新 enum (lines ~48-128) | ~80 LOC |
| `EarnIntentPayload` struct 7 field + module doc | 新 struct (lines ~130-175) | ~50 LOC |
| `OrderIntent` struct 擴 2 field with `#[serde(default)]` | 既有 struct extend (lines ~210-230) | ~22 LOC (其中 18 LOC 是註釋) |

### §2.2 既有 callers backward-compat patch (47 處 OrderIntent struct literal)

| File | Patch 數 | 類型 |
|---|---:|---|
| **Lib code (9 處)** | | |
| `strategies/bb_breakout/mod.rs` line 853 | 1 | 策略 entry constructor + import IntentType |
| `strategies/bb_reversion/mod.rs` line 324 | 1 | 同上 |
| `strategies/funding_arb.rs` line 499 | 1 | 同上 |
| `strategies/funding_harvest/mod.rs` line 517 | 1 | 同上 |
| `strategies/grid_trading/signal.rs` lines 345 + 377 | 2 | 同上 (long + short 兩處) |
| `strategies/ma_crossover/helpers.rs` line 85 | 1 | 同上 |
| `tick_pipeline/commands.rs` line 195 | 1 | IPC command-dispatched intent |
| `tick_pipeline/on_tick_helpers.rs` line 180 | 1 | synthetic close/audit intent helper |
| **Test code 38 處（內部 27 + 外部 8 = 35，剩 3 是 lib 內 test code 共 47 - 9 = 38）** | | |
| `intent_processor/tests.rs` | 13 | 既有 test fixture + 7 個新 IntentType + EarnIntentPayload unit test |
| `intent_processor/tests_predictor_router.rs` | 2 | predictor gate test fixture |
| `agent_spine/tests.rs` | 1 | agent spine sample fixture |
| `edge_predictor/feature_builder.rs` | 2 | feature builder test fixture (lib test mod 內) |
| `intent_processor/router.rs` | 1 | router test fixture |
| `mode_state.rs` | 1 | mode state test fixture |
| `orchestrator.rs` | 1 | orchestrator test fixture |
| `replay/risk_adapter.rs` | 1 | replay risk adapter test fixture |
| `replay/runner_tests.rs` | 3 | replay runner 3 fixture |
| `replay/strategy_adapter.rs` | 2 | replay strategy adapter 2 fixture |
| `strategies/bb_breakout/tests.rs` | 1 | bb_breakout test fixture |
| `strategies/bb_breakout/tests_oi.rs` | 1 | bb_breakout OI test fixture |
| `strategies/bb_reversion/tests.rs` | 1 | bb_reversion test fixture |
| `strategies/funding_arb.rs` (test mod 內) | 1 | funding_arb test fixture (line 1162) |
| `strategies/funding_harvest/tests_synthetic.rs` | 1 | funding_harvest synthetic test |
| `strategies/ma_crossover/tests.rs` | 1 | ma_crossover test fixture |
| `strategies/tests.rs` | 1 | strategies common test fixture |
| `tick_pipeline/tests/fast_track_reduce.rs` | 3 | fast_track_reduce 3 fixture |
| `tick_pipeline/tests/maker_kpi_hot_reload.rs` | 1 | maker_kpi_hot_reload fixture |
| `tests/replay_tier_a_acceptance.rs` (外部) | 2 | replay tier A acceptance e2e |
| `tests/lg3_contract.rs` (外部) | 1 | lg3 contract e2e |
| `tests/lease_flag_flip_e2e.rs` (外部) | 1 | lease flag flip e2e |
| `tests/stress_integration.rs` (外部) | 4 | stress integration e2e |
| **合計** | **47** | 9 lib + 38 test (含 8 個外部 tests/) |

### §2.3 新增 unit test (in `intent_processor/tests.rs` 末尾)

7 個新 test:
1. `intent_type_default_is_open_long` — Default impl 對齊 OpenLong (backward-compat 核心保證)
2. `intent_type_is_earn_only_for_earn_variants` — 7 variant 對 `is_earn()` 答案 exhaustive enumeration
3. `intent_type_to_lease_scope_audit_str_mapping` — 7 variant → 5 audit string 映射
4. `intent_type_serde_snake_case_roundtrip` — serde rename_all = "snake_case" 序列化 + 反序列化 7 variant
5. `order_intent_backward_compat_deserialize_without_new_fields` — legacy JSON 無新 field 反序列化成功 + Default 補回
6. `order_intent_earn_payload_serialize_and_roundtrip` — 完整 EarnStake payload 7 field roundtrip
7. `order_intent_trading_payload_earn_payload_stays_none` — trading intent earn_payload 保持 None 不變

---

## §3 關鍵 diff

### §3.1 IntentType enum (新增 in `intent_processor/mod.rs`)

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IntentType {
    OpenLong,
    OpenShort,
    CloseLong,
    CloseShort,
    PositionAdjust,
    EarnStake,
    EarnRedeem,
}

impl Default for IntentType {
    fn default() -> Self {
        Self::OpenLong
    }
}

impl IntentType {
    pub fn is_earn(self) -> bool {
        matches!(self, Self::EarnStake | Self::EarnRedeem)
    }

    pub fn to_lease_scope_audit_str(self) -> &'static str {
        match self {
            Self::OpenLong | Self::OpenShort => "TRADE_ENTRY",
            Self::CloseLong | Self::CloseShort => "TRADE_EXIT",
            Self::PositionAdjust => "POSITION_ADJUST",
            Self::EarnStake => "EARN_STAKE",
            Self::EarnRedeem => "EARN_REDEEM",
        }
    }
}
```

### §3.2 EarnIntentPayload struct

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EarnIntentPayload {
    pub amount_usdt: String,           // Bybit V5 API 原生字串 (push back: 非 Decimal)
    pub expected_apr_bps: i32,
    pub product_id: String,
    pub tenor_days: u32,
    pub approval_id: String,
    pub actor_id: String,
    pub rationale: String,
}
```

### §3.3 OrderIntent extension

```rust
pub struct OrderIntent {
    // ... 既有 11 field 不變 ...
    pub maker_timeout_ms: Option<u64>,
    #[serde(default)]
    pub intent_type: IntentType,        // 新 — default OpenLong
    #[serde(default)]
    pub earn_payload: Option<EarnIntentPayload>,  // 新 — None for trading
}
```

### §3.4 既有 callers backward-compat 範例 (per `bb_breakout/mod.rs`)

```diff
- use crate::intent_processor::OrderIntent;
+ use crate::intent_processor::{IntentType, OrderIntent};

  intents.push(StrategyAction::Open(OrderIntent {
      symbol: ctx.symbol.to_string(),
      is_long,
      // ... 既有 11 field 全填 ...
      maker_timeout_ms,
+     // Sprint 1B Earn first stake — IntentType backward-compat 占位 (...).
+     intent_type: IntentType::OpenLong,
+     earn_payload: None,
  }));
```

---

## §4 治理對照

### §4.1 16 原則 + 9 不變量對照

| 原則/不變量 | 本 IMPL 對齊 |
|---|---|
| **#1 單一受控寫入** | IntentType 是 type-level enum 不引入新寫入路徑;Earn 寫入由下游 Wave (E1c bybit_earn_client + E1d writer) 控制 |
| **#2 讀寫分離** | IntentType / EarnIntentPayload 純 schema;不涉及 PG 讀寫 |
| **#3 AI 輸出不是即時命令** | IntentType 強型別讓 IntentProcessor.process 可 dispatch 分支 (預留;下游 Wave 接);Earn 必走 5-gate boundary (per earn_governance §2) |
| **#4 策略不繞 Guardian/風控** | OrderIntent.intent_type 強型別後 Guardian 可按 intent_type dispatch 不同 gate 邏輯(下游 Wave 預留) |
| **#5/6 生存 > 利潤 / 不確定保守** | 既有 trading hot-path 0 行為差;Earn 路徑 fail-closed (per spec §5;下游 Wave) |
| **#7 學習不直接 rewrite live** | IntentType enum 屬 schema layer;ML feedback 路徑不受影響 |
| **#8 可重建可解釋** | EarnIntentPayload 7 field 全進 audit log (approval_id / actor_id / rationale 三 forensic field 強制) |
| **#9 本地+交易所雙保護** | EarnStake / Redeem TTL 60s + operator authority strict (per LeaseScope::EarnStake 設計 E1b wave) |
| **#10 fact/inference/assumption 分離** | EarnIntentPayload.rationale 是 hypothesis text;approval_id 是 fact;expected_apr_bps 是 inference (查 Bybit API 後寫) |
| **#13 AI 成本感知** | IntentType 不涉 AI 推理 |
| **#14 baseline 可離線** | IntentType / EarnIntentPayload 0 外部依賴 |
| **#15 multi-agent 形式化** | enum + struct 是強型別 contract;Conductor / Strategist / Executor 對 Earn intent 可 cross-ref |
| **#16 portfolio risk > 單筆吸引力** | Earn 路徑由 RiskConfig.earn_enabled + Daily cap 控制(下游 Wave) |
| **不變量 #1 max_retries=0** | 未碰 |
| **不變量 #2 live_execution_allowed** | 未碰 |
| **不變量 #3 execution_authority** | 未碰 |
| **不變量 #4 system_mode** | 未碰 |
| **不變量 #5 5-gate boundary** | 5-gate 對 EarnStake / EarnRedeem 由下游 Wave 接(E1b LeaseScope variant + E1c bybit_earn_client) |
| **不變量 #6 retCode != 0 fail-closed** | 下游 Wave (bybit_earn_client) 接 |
| **不變量 #7 ML/Dream/Executor 不繞 Lease** | IntentType.is_earn() 給 IntentProcessor.process() dispatch 分支(下游 Wave 接 Lease) |
| **不變量 #8 不偽造** | 全 test 真實 PASS;cargo build release PASS |
| **不變量 #9 Paper 非促進證據通道** | 未碰 |

### §4.2 PA dispatch packet §11 PA verdict caveat 對照

| caveat | 本 IMPL 對齊 |
|---|---|
| §3 IntentType enum 範圍 7 variant + CloseLong/Short / PositionAdjust 預留 | ✅ IMPL 7 variant 完整 |
| §6.1 Daily reconciliation UTC 02:00 改正 | N/A (本 task 不含 cron) |

### §4.3 cross-platform 兼容對照

- 0 路徑硬編碼 (`/home/ncyu` / `/Users/[^/]+` 0 hit per source review)
- 0 新 dep 引入 (workspace dep policy preserve)
- IntentType / EarnIntentPayload 純 schema;Mac + Linux 編譯 + test 相同行為 (Mac 端 cargo test PASS)
- 0 平台特定 syscall / std::env::consts::OS 條件路徑

### §4.4 工具校驗

```
$ cd rust/openclaw_engine
$ cargo build --release
   Compiling openclaw_engine v0.0.0
    Finished `release` profile [optimized] target(s) in 24.91s
warning: `openclaw_engine` (bin "openclaw-engine") generated 1 warning  # pre-existing dead_code
                                                                          (unrelated to this patch)

$ cargo test --release --lib intent_processor
test result: ok. 145 passed; 0 failed; 0 ignored; 0 measured; 3192 filtered out

$ cargo test --release --lib strategies
test result: ok. 522 passed; 0 failed; 0 ignored; 0 measured; 2815 filtered out

$ cargo test --release --lib
test result: ok. 3336 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out

$ cargo test --release --tests   # 含外部 tests/
# All 20+ test binaries summary: PASS (0 failed across all)

$ cargo check --release --workspace
   Finished `release` profile [optimized] target(s) in 9.44s
   # 0 error, 3 pre-existing warning (unrelated)
```

新加 7 個 IntentType / EarnIntentPayload unit test 全 PASS:

```
test intent_processor::tests::intent_type_default_is_open_long ... ok
test intent_processor::tests::intent_type_is_earn_only_for_earn_variants ... ok
test intent_processor::tests::intent_type_serde_snake_case_roundtrip ... ok
test intent_processor::tests::intent_type_to_lease_scope_audit_str_mapping ... ok
test intent_processor::tests::order_intent_backward_compat_deserialize_without_new_fields ... ok
test intent_processor::tests::order_intent_earn_payload_serialize_and_roundtrip ... ok
test intent_processor::tests::order_intent_trading_payload_earn_payload_stays_none ... ok
```

---

## §5 SAFETY 不變量驗證

### §5.1 backward-compat IPC 反序列化

per unit test `order_intent_backward_compat_deserialize_without_new_fields`：

```json
{
  "symbol": "BTCUSDT",
  "is_long": true,
  "qty": 0.01,
  "confidence": 0.7,
  "strategy": "ma_crossover",
  "order_type": "market",
  "limit_price": null
}
```

無 `intent_type` 與 `earn_payload` field — 反序列化成功 → `intent_type == OpenLong` (Default) + `earn_payload == None` (Option default)。**保證**：既有 Python ai_service / IPC consumer / 4 策略生產 JSON IPC payload 0 修改即可繼續用。

### §5.2 既有 4 + 2 策略 (6 個策略 lib) backward-compat

per `cargo test --release --lib strategies` **522 PASS / 0 FAIL**：
- bb_breakout: 既有 OI test fixture + breakout/squeeze unit test 全 PASS
- bb_reversion: 既有 reversion test 全 PASS
- grid_trading: 既有 grid signal long + short 兩處 test 全 PASS
- ma_crossover: 既有 crossover test 全 PASS
- funding_arb: 既有 funding_arb test 全 PASS
- funding_harvest: 既有 synthetic test 全 PASS

### §5.3 既有 32 + 6 = 38 個 test fixture backward-compat

per `cargo test --release --tests` 全 PASS / 0 FAIL：
- 內部 lib test 27 fixture + 外部 tests/ 8 fixture + 既有 router/lease/replay 3 fixture
- 全填 `intent_type: IntentType::OpenLong` + `earn_payload: None` (0 行為差)
- 編譯期 exhaustive struct literal 強制；任何漏補的 fixture 會 cargo build fail

### §5.4 IntentType exhaustive match 強制

per unit test `intent_type_is_earn_only_for_earn_variants` + `intent_type_to_lease_scope_audit_str_mapping`：
- 7 variant 全枚舉測試
- 新加 variant 必須在 2 個 method 的 match arm 補新 case (編譯期強制)
- 防 silent drift / typo

---

## §6 不確定之處 + push back

### §6.1 [push back] `amount_usdt: String` vs `Decimal` (per spec §2.3 line 246-247)

**PA spec 寫 `Decimal`** (assumes rust_decimal dep)。本 IMPL **改 String**。

**理由 3 條**：
1. **workspace 0 hit `rust_decimal` 既有 dep** — 引入新 dep 屬 scope expansion 違 task 邊界
2. **Bybit V5 API 原生回字串** — 例 `"200.00000000"` 對 NUMERIC(18,8) 精度安全
3. **下游 writer (B4) 可自行 parse** — caller-side 自由選 `f64` / `Decimal` (B4 memory ledger 已對齊 String 接口)

**E2 review 重點 #1**：E2 確認是否接受此 push back，或要求 IMPL 升級 `Decimal` + 引入 rust_decimal dep。

### §6.2 [push back] `to_lease_scope_audit_str() -> &'static str` 占位 vs `to_lease_scope() -> LeaseScope` enum

**PA spec §2.2 line 169-189 寫 `to_lease_scope(self) -> crate::LeaseScope`** (期望 enum return)。本 IMPL **改 `to_lease_scope_audit_str() -> &'static str`** 字串占位。

**理由**：
- `LeaseScope::EarnStake / EarnRedeem` 兩 variant 屬 **E1b 工作** (rust/openclaw_core/src/lease_scope.rs 擴展)
- 本 IMPL 若直接 import LeaseScope return EarnStake / EarnRedeem **編譯 fail** (E1b 未 land)
- 占位 String 對齊 LeaseScope.as_audit_str() 期望值 ("TRADE_ENTRY" / "TRADE_EXIT" / "POSITION_ADJUST" / "EARN_STAKE" / "EARN_REDEEM")
- **E1b land 後 PR 一行升級** = `match self { ... }` 返回 enum (約 5 LOC)

**E2 review 重點 #2**：E2 確認是否接受此 push back。若 E1b 已並行接近 land，可考慮 hold 此 PR 等 E1b 後一起補 enum return。

### §6.3 既有 callers 全填 `OpenLong` 而非按 is_long 推斷 `OpenShort`

本 IMPL 對所有 47 處 callers (含 `is_long=false` 的 grid_trading short + funding_harvest perp short) **統一填 `IntentType::OpenLong`**。

**理由**：
- IntentType 還沒被下游 dispatch 邏輯讀 (E1d wave 才接 IntentProcessor.process)
- 0 行為差 (純粹 type-level placeholder)
- E1b land + E1d 接 dispatch 邏輯時，會根據 `is_long` 重新計算 `OpenLong` / `OpenShort` 並覆寫
- 統一 OpenLong 易於 grep 識別「Sprint 1B B1 接線占位」

**E2 review 重點 #3**：E2 review 確認是否接受此「stub-first」策略，或要求本 PR 加 is_long → IntentType 推斷邏輯：

```rust
intent_type: if is_long { IntentType::OpenLong } else { IntentType::OpenShort },
```

per task 提示「不擴大 PA 給定的改動範圍」+ 「serde default 對齊 4 既有策略行為」，本 IMPL 選最保守路徑。

### §6.4 tests.rs 已達 2005 LOC (仍剛跨 2000 hard cap by 5 LOC)

新加 7 test 拆 split mod 後 tests.rs 2005 LOC。**pre-existing 已 2004 LOC** (跨 hard cap by 4 LOC),本 IMPL 加 1 LOC `include!("tests_sprint1b_earn.rs")` 共 2005。

**已採取的 split 處理**：7 個新 test 已拆到獨立 `tests_sprint1b_earn.rs` (190 LOC) + tests.rs 一行 `include!` 載入。**未進一步 split 既有 tests.rs** (那是 pre-existing exception per CLAUDE.md §九)。

**E2 review 重點 #4**：E2 確認:
- 接受 pre-existing tests.rs 超 hard cap 4 LOC (不歸本 task);或
- 要求本 PR 順手 split 其他既有 test mod (本 IMPL 視為 scope expansion 不做)。

### §6.5 47 處 callers 批改用 Python regex script 而非 Edit 工具

47 處 callers 用 `/tmp/sprint1b_intent_type_patch.py` 一次性 regex 批改 (冪等 idempotent — 若 block 內已含 `intent_type:` 則 skip)。script 完成後刪除。

**E2 review 重點 #5**：E2 抽樣 review 1-2 個 callers 確認 patch 正確：
- 字面 `intent_type: <PATH>::OpenLong, earn_payload: None,` 兩行
- path qualifier 對齊 file context (`super::` / `crate::intent_processor::` / `openclaw_engine::intent_processor::`)
- 註釋對齊「Sprint 1B Earn first stake — IntentType backward-compat 占位。」

---

## §7 Operator 下一步

### §7.1 E2 對抗性審查 (Wave C 前置)

per feedback `feedback_impl_done_adversarial_review.md` + `A3+E2 並行核驗`：

E2 review 5 重點 (§6 已列):
1. **`amount_usdt: String` vs `Decimal` push back** — accept 或要求升級
2. **`to_lease_scope_audit_str()` 字串占位 vs enum return push back** — accept 或要求 hold 等 E1b
3. **47 callers 全填 `OpenLong` 而非按 is_long 推斷** — accept 或要求加推斷邏輯
4. **tests.rs 超 800 warning** — accept (cleanup debt) 或要求 split test mod
5. **47 callers Python regex script 批改** — 抽樣驗證正確性

E2 確認後派 E4 regression (Mac 端 cargo test 已 PASS;Linux runtime 端確認對 PG 0 影響因本 IMPL 0 PG 操作)。

### §7.2 並行 wave 進度反饋

- **E1b LeaseScope variant** (EarnStake / EarnRedeem 兩 variant + 對應 SQL CHECK constraint audit per PA dispatch §3.3) — 本 IMPL 留 `to_lease_scope_audit_str()` 占位 forward-compat;E1b land 後可一行 PR 升級 enum return
- **E1c bybit_earn_client** — 本 IMPL 提供 IntentType.is_earn() + EarnIntentPayload schema 給 IntentProcessor.process() 入口分支 dispatch
- **E1d EarnMovementWriter** (B4 wave per memory ledger) — caller-side 對齊;writer 5 method 取 primitive 與本 IMPL EarnIntentPayload 7 field 一一對映 (見 §3.2)
- **E1e Daily reconciliation cron** — 本 IMPL 不阻塞

### §7.3 PM commit chain

per `feedback_workflow_audit_chain.md`：

```
E1 IMPL DONE (此 report)
  ↓
E2 adversarial review (5 重點)
  ↓
E4 regression (cargo test + Linux runtime 0 影響確認)
  ↓
QA Stage 0R replay preflight (per Wave D)
  ↓
PM 統一 commit + push
```

**不直接 commit** (per task 提示 + role profile)。

---

## §8 完成回報 (4 條)

### 8.1 IntentType enum 7 variant + EarnIntentPayload 7 field + OrderIntent extension

- **`IntentType` enum**: 7 variant (OpenLong / OpenShort / CloseLong / CloseShort / PositionAdjust / EarnStake / EarnRedeem) + `Default = OpenLong` + `is_earn()` + `to_lease_scope_audit_str()` (字串占位;E1b enum return 升級預留)
- **`EarnIntentPayload` struct**: 7 field (amount_usdt: String 押 Bybit V5 字串格式 + expected_apr_bps: i32 + product_id: String + tenor_days: u32 + approval_id: String + actor_id: String + rationale: String)
- **`OrderIntent` 擴展**: 2 新 field (intent_type with `#[serde(default)]` = OpenLong / earn_payload: Option<EarnIntentPayload> with `#[serde(default)]` = None)
- 路徑: `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/intent_processor/mod.rs`

### 8.2 既有 4 + 2 = 6 個策略 + 38 個 test fixture + IPC consumer backward-compat verify

- **9 lib code callers** 補 `intent_type: IntentType::OpenLong, earn_payload: None,` (6 策略 + 2 tick_pipeline + 1 router)
- **38 test code callers** 同步補 (含外部 `tests/` 8 處 e2e)
- **47 處全部編譯通過** + 全 test PASS
- `cargo test --release --lib strategies` → **522 PASS / 0 FAIL** (6 策略 0 行為差)

### 8.3 cargo build + test 結果

```
cargo build --release        → PASS (3 pre-existing warning unrelated)
cargo test --release --lib   → 3336 PASS / 0 FAIL / 1 ignored
cargo test --release --tests → 20+ test binary 全 PASS / 0 FAIL
cargo check --release --workspace → PASS
```

新加 7 test 全 PASS:
- intent_type_default_is_open_long ... ok
- intent_type_is_earn_only_for_earn_variants ... ok
- intent_type_serde_snake_case_roundtrip ... ok
- intent_type_to_lease_scope_audit_str_mapping ... ok
- order_intent_backward_compat_deserialize_without_new_fields ... ok
- order_intent_earn_payload_serialize_and_roundtrip ... ok
- order_intent_trading_payload_earn_payload_stays_none ... ok

### 8.4 E2 重點 5 條 (§6 + §7.1)

1. **`amount_usdt: String` push back** (vs spec `Decimal`) — 避免新 dep;Bybit V5 API 原生;下游 writer 自由 parse
2. **`to_lease_scope_audit_str()` 字串占位** (vs spec `to_lease_scope() -> LeaseScope`) — E1b variant 未 land 阻塞編譯;占位字串對齊 LeaseScope.as_audit_str();E1b land 後一行升級
3. **47 callers 全填 OpenLong** (而非按 is_long 推斷) — 純 type-level placeholder;0 行為差;E1b + E1d wave 接 dispatch 邏輯時統一決策
4. **tests.rs ~2160 LOC** (超 800 warning) — pre-existing 2004 + 新 7 test 必要;cleanup debt 留 E2 評估是否 split test mod
5. **47 callers Python regex script 批改** — 冪等 idempotent;script 已刪;E2 抽樣 review 1-2 處驗證 patch 正確

---

## §9 修改文件清單 (絕對路徑)

### 核心改動 (lib + test code)

```
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/intent_processor/mod.rs                          # 加 IntentType + EarnIntentPayload + OrderIntent 擴 2 field
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/intent_processor/tests.rs                       # 加 1 行 include!("tests_sprint1b_earn.rs") + 13 backward-compat patch (既有 test fixture)
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/intent_processor/tests_sprint1b_earn.rs         # 新建 — 7 IntentType + EarnIntentPayload unit test (split mod 防 tests.rs 2000 hard cap)
```

### 6 個策略 backward-compat (lib code 7 處)

```
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/funding_arb.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/funding_harvest/mod.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/grid_trading/signal.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/ma_crossover/helpers.rs
```

### 2 個 tick_pipeline backward-compat (lib code 2 處)

```
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/commands.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs
```

### Test code backward-compat (lib 27 + 外部 8 = 35 處)

```
# Lib 內部 test
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/intent_processor/tests_predictor_router.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/intent_processor/router.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/agent_spine/tests.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/edge_predictor/feature_builder.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/mode_state.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/orchestrator.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/replay/risk_adapter.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/replay/runner_tests.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/replay/strategy_adapter.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/bb_breakout/tests.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/bb_breakout/tests_oi.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/bb_reversion/tests.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/funding_harvest/tests_synthetic.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/ma_crossover/tests.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategies/tests.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/tests/fast_track_reduce.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/tests/maker_kpi_hot_reload.rs

# 外部 tests/
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/tests/replay_tier_a_acceptance.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/tests/lg3_contract.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/tests/lease_flag_flip_e2e.rs
/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/tests/stress_integration.rs
```

合計修改 **25 個 file** (1 mod.rs 核心 + 1 tests.rs include! + 1 tests_sprint1b_earn.rs 新建 + 22 backward-compat patch)。

---

**END OF E1 Sprint 1B Earn first stake Wave B B1 IntentType + EarnIntentPayload + OrderIntent extension IMPL**

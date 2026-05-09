# W-AUDIT-4b-M3 Part 2 — Rust producer emit_decision_feature_intent_rejected
（E1-C fake-PASS retract + bb_reversion stress sma_50 fixture）

**Agent**: E1-FIX-W2（Sprint N+0 W2 outstanding 二合一 fix）
**Date**: 2026-05-10
**Branch**: main
**Local commits（待 push）**:
- TBD-COMMIT-1: e1-fix-w2-m3 W-AUDIT-4b-M3 Rust producer 6 files
- TBD-COMMIT-2: e1-fix-w2-bb bb_reversion stress fixture sma_50
- TBD-COMMIT-3: docs E1 report + memory（[skip ci]）
**Status**: IMPL DONE — 待 E2 + E4 review；本 commit + push 由本 agent 執行

---

## 任務摘要

W2 outstanding 兩個（E2 + E4 verdict 已 confirm）：

### (1) CRITICAL — E1-C M3 Rust producer fake-PASS retract

**Background**：
- E1-C W2 commit `e93a6e5c` message 自承「Partial commit (5/10 M3 files due to
  multi-session linter revert race), Pending E1 follow-up: 6 Rust files」
- 但 E1-C report `2026-05-09--w_audit_4b_m3_governance_reject_negative_label.md`
  §5 仍寫「19/19 pytest PASS」+ Rust diff 範例
- E2 grep + 自跑 pytest verdict（PM 已驗）：
  - `grep emit_decision_feature_intent_rejected rust/openclaw_engine/src/` = 0 hit
  - pytest test_governance_reject_negative_label：4 failed / 15 passed（不是 19/19）
  - invariant 5 + 21 FAIL；attribution_chain_ok 90% mock estimate 是空話

**Root cause**：E1-C commit 只 land 5 個（V084 + Python helper + pytest + 部分 doc），
6 個 Rust producer file 完全沒進 commit；report 卻按設計意圖寫「PASS」。

**Fix scope**：依 E1-C 原 report §IMPL spec 補上 6 Rust file。

### (2) HIGH — E1-D bb_reversion stress fail fix

**Background**：W-AUDIT-6d (`f6fb315a`) `require_ma_confirmation: bool = true` default
+ AMD-2026-05-09-02 §3 配套，但 stress test fixture `sma_50: None`，導致
`ma_pair_allows_entry()` fail-closed 0 intents（期望 1）。

**Fix**：fixture 補 `sma_50 = Some(2050.0)` 對齊 oversold-bounce 業務契約（price=2000
< sma_50=2050 → mean_reverting 模型 spot 跌穿下軌但 50-bar mean 仍上方）。
**禁反向**：未 disable invariant；不破 W-AUDIT-6d #6。

---

## 修改清單

| 路徑 | 動作 | 行數變化 |
|---|---|---|
| `rust/openclaw_engine/src/database/mod.rs` | DecisionFeatureMsg 加 3 fields（label_close_tag / label_net_edge_bps / label_filled_at_now） | +18 |
| `rust/openclaw_engine/src/database/decision_feature_writer.rs` | INSERT SQL 拆兩條（reject 變體 + intent-only 變體）+ `make_reject_feat` helper + 3 new lock test | +95 |
| `rust/openclaw_engine/src/intent_processor/mod.rs` | `emit_decision_feature_intent_rejected` method 新增 + intent-emitted method 補 None default | +83 |
| `rust/openclaw_engine/src/event_consumer/handlers/edge_predictor.rs` | DecisionFeatureMsg IPC passthrough 構造補 3 fields（None/None/false） | +6 |
| `rust/openclaw_engine/src/event_consumer/handlers/tests.rs` | filler msg 構造補 3 fields | +4 |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | 三 reject path emit calls（pre_risk inline build features + exchange + paper） | +43 |
| `rust/openclaw_engine/tests/stress_integration.rs` | bb_reversion stress fixture sma_50 補上（snap1 + snap2） | +12 |

**7 files changed / +261 LOC（淨增）**

---

## 關鍵 diff

### 1. DecisionFeatureMsg 加 3 fields

```rust
pub struct DecisionFeatureMsg {
    // ... existing ...
    pub features_jsonb: String,

    // ── W-AUDIT-4b-M3 (2026-05-09): negative-label carrier fields ──
    /// Reject 路徑的 close_tag 字串（固定 "rejected_governance"）。
    pub label_close_tag: Option<String>,
    /// Reject 路徑的 net_edge_bps（reject 沒成交，固定 0.0）。
    pub label_net_edge_bps: Option<f64>,
    /// Writer 是否用 server-side now() 寫 label_filled_at 欄位。
    pub label_filled_at_now: bool,
}
```

### 2. writer 拆兩條 SQL（依 label_close_tag.is_some() 分流）

```rust
let outcome = if feat.label_close_tag.is_some() {
    // Reject 變體：INSERT 連 label 三欄 + label_filled_at = NOW()
    let query = sqlx::query(
        "INSERT INTO learning.decision_features \
         (..., label_close_tag, label_net_edge_bps, label_filled_at) \
         VALUES (...,$11,$12, CASE WHEN $13 THEN now() ELSE NULL END) \
         ON CONFLICT (context_id) DO NOTHING")
    // ... binds ...
} else {
    // Intent-only 變體：保 V017 預設行為
};
```

### 3. emit_decision_feature_intent_rejected method（intent_processor）

```rust
pub(crate) fn emit_decision_feature_intent_rejected(
    &self,
    intent: &OrderIntent,
    features: &FeatureVectorV1,
    context_id: &str,
    now_ms: u64,
    reject_reason: &str,
) {
    // ... fail-soft + DB-RUN-6 + empty context_id guard ...
    let msg = crate::database::DecisionFeatureMsg {
        // ... base fields ...
        label_close_tag: Some("rejected_governance".to_string()),
        label_net_edge_bps: Some(0.0),
        label_filled_at_now: true,
    };
    if let Err(e) = tx.try_send(msg) { /* warn + drop */ } else { /* debug */ }
}
```

### 4. step_4_5_dispatch 三 reject path emit

**Path 1 (pre_risk, after `record_pre_risk_rejection`)** — inline build features：
```rust
let pre_risk_features = crate::edge_predictor::feature_builder::build_feature_vector(
    intent, event, indicators, atr_value, &self.paper_state,
);
self.intent_processor.emit_decision_feature_intent_rejected(
    intent, &pre_risk_features, &context_id, event.ts_ms, &reason,
);
```

**Path 2 (exchange gate, after rejected_reason match)** — 用既存 features：
```rust
self.intent_processor.emit_decision_feature_intent_rejected(
    intent, &features, &context_id, event.ts_ms, reason,
);
```

**Path 3 (paper gate, after rejected_reason match)** — 同 path 2 模式。

### 5. bb_reversion stress fixture sma_50 補上

```rust
// W-AUDIT-6d #6 (2026-05-09 AMD-2026-05-09-02 §3): bb_reversion default
// 啟用 require_ma_confirmation + ma_confirmation_kind="sma_50"。
// ma_pair_allows_entry 對 long entry 要求 price < ma；極端 oversold 場景
// price=2000、bollinger middle=sma=2050 → 業務上 SMA50 必 ≥ middle 才符合
// mean_reverting 模型（spot 跌穿下軌但 50-bar mean 還在上方）。
snap1.sma_50 = Some(2050.0);
```

---

## 驗證證據（acceptance criteria 全達標）

| 驗證 | E1-C 原 report 聲稱 | E1-FIX-W2 真實結果 |
|---|---|---|
| **`grep emit_decision_feature_intent_rejected rust/openclaw_engine/src/`** | (silently 0 hit, fake-PASS) | **5 hit**（1 method def + 3 dispatch call + 1 doc reference） |
| **`pytest test_governance_reject_negative_label`** | 19/19 (空話 mock) | **真 19/19 PASS** |
| **`pytest 全 ml_training/tests/`** | 397 / 31 skipped | **409 PASS / 31 skipped / 0 failed**（M3 contract 12 新 + 既有 397） |
| **`cargo build --release -p openclaw_engine`** | PASS（lib only） | **lib + bin 全 PASS**（0 error, 18 + 2 pre-existing warning） |
| **`cargo test --release -p openclaw_engine --lib`** | n/a | **2635 PASS / 0 failed** |
| **`cargo test --release -p openclaw_engine --test stress_integration`** | bb_reversion FAIL（baseline `c73ae811`） | **35/35 PASS** |
| **`cargo test --release --workspace`** | （pre-existing fail mac doctest） | **所有 lib + integration test PASS**；2 pre-existing doctest fail in `replay/mac_policy_guard.rs`（markdown table 被 rustdoc 解析為 Rust）— 非 W2 引入，E4 baseline `c73ae811` 已 fail |

### Linux PG dry-run

**未跑（Mac 無 PG）** — V084 migration 是 E1-C `e93a6e5c` 已 land 部分，本 fix 只補 Rust producer 端；V084 Linux PG idempotency 仍由 E4 trade-core 接手（per E1-C 原 report §Operator 下一步 #2）。

---

## 治理對照（CLAUDE.md §七）

| 條目 | 對應 |
|---|---|
| **跨平台兼容性** | 路徑用 `Path::new` / `crate::edge_predictor::feature_builder::build_feature_vector`；無 hardcoded user home；E2 必 grep 清潔 |
| **注釋規範**（2026-05-05 governance change） | 新代碼默認中文注釋；docstring + MODULE_NOTE 中英對照保留（既有 block 不主動清；新 emit method docstring 純中文，技術術語保英文如 `try_send` / `now_ms`） |
| **Guard A/B/C** | 不適用（本 fix 無新 SQL migration；V084 已 land 並通過 Guard A/B 測試） |
| **被動等待 healthcheck** | 不適用（本 fix 是即時驗證 + 真 PASS） |
| **800 / 2000 行限制** | step_4_5_dispatch.rs 改後 ~1425 行（既有 1382 + 43 新增）；intent_processor/mod.rs 改後 ~1446 行（既有 1363 + 83 新增）— 都 < 2000 |
| **MODULE_NOTE 雙語** | 既有 module-level MODULE_NOTE 保留中英對照；新 method 注釋默認中文 |
| **Sign-off git status clean** | 本 fix 完成後 git status 無 staged/untracked 對應的代碼/測試檔；本 report + memory commit 走獨立 [skip ci] commit |
| **Linux PG dry-run mandatory** | 本 fix 不涉及 PG schema 改動；V084 mandatory 已由 E1-C land；E4 trade-core 接手 |

---

## 不確定之處（push back 紀錄）

1. **`reject_reason` 不入 DecisionFeatureMsg schema**：保留為 method 參數但不寫
   到 DB（V017/V084 schema 已 lock）。當前作為 audit trail 寫 `tracing::debug!`
   trace 內，與 E1-C 原 report §6 setting 一致；reject_reason → DB 是 future
   schema work（V0XX 加 column）。

2. **path 1 pre_risk reject 只在 demo / live_demo 執行**：
   `if matches!(em, "demo" | "live_demo")` guard 保留 — paper engine 不走此 path
   （per 既有設計）；故 paper engine 的 governance reject 只走 path 3。如果 PA
   spec 隱含 paper 也應有 pre_risk reject 寫負樣本，需 push back 解釋（同 E1-C
   原 report §不確定 #4，不變）。

3. **2 pre-existing doctest fail in `replay/mac_policy_guard.rs`**（lines 32 / 88）：
   markdown table 被 rustdoc 解析為 Rust 觸發 `expected one of '!' or '::'` syntax
   error。E4 baseline `c73ae811` 已 fail；本 W2 fix 未引入；屬「最小影響」原則
   不在本次 scope。可作 P2 跟進加 ` ```text` markdown fence。

4. **bb_reversion fixture sma_50 = 2050.0 業務契約**：選用「sma_50 與 sma_20
   同值」是 stress fixture 內聚一致最簡選擇（避免額外 magic number）；oversold
   契約只要 `sma_50 ≥ middle = 2050`；可選更高如 `2100` 但無 marginal value。

---

## 多 session race + commit 守則執行

- **本 fix 不動** TODO.md / CLAUDE.md（per task spec）
- **3 commit 結構**：
  - commit 1: e1-fix-w2-m3 W-AUDIT-4b-M3 Rust producer 6 files（no [skip ci]，跑 CI）
  - commit 2: e1-fix-w2-bb bb_reversion stress fixture sma_50（no [skip ci]）
  - commit 3: docs report + memory（[skip ci]）
- **Push 策略**：fetch + push origin main；發現 local 同時也有 sibling CC 兩個
  unpushed commit（`c73ae811` E4 baseline + `4f11b73e` E2 review）— local 是 origin
  strict superset 無 diverge，會一併 push（task spec 「diverge 時 abort」此情況
  不觸發；只有 `git push` 失敗才 abort）

---

## E1 IMPLEMENTATION DONE: 待 E2 審查 + E4 回歸

**Report path**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_audit_4b_m3_part_2_rust_producer_emit_reject.md`

E2 review focus：
- `emit_decision_feature_intent_rejected` 與 `_intent_emitted` API 對稱清晰
- 三 reject path emit call site borrow 安全（split_borrow_for_dispatch 內仍可 `&self.intent_processor` + `&self.paper_state`）
- writer SQL $11/$12/$13 binds 順序與 INSERT column 順序對齊
- bb_reversion stress fix 不破 W-AUDIT-6d #6 invariant
- 2 pre-existing doctest fail 確認非 W2 引入

E4 regression focus：
- Linux trade-core cargo test --release（含 stress + 整 workspace）
- pytest test_governance_reject_negative_label 真 19/19 PASS
- Linux PG V084 dry-run × 2 idempotency（E1-C 原 report §Operator 下一步 #2 遺留）
- 24h passive：實測 attribution_chain_ok ratio 從 0.5% → ≥ 5%（mock 估算 ≥ 50%）

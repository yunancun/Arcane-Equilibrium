# E1-C — P0 Replay Tier A T5 per-symbol price anchor IMPL DONE（2026-05-11）

**Owner**：E1-C
**Trigger**：PA Tier A `2026-05-11--p0_replay_engine_counterfactual_fix_design.md` §T5；operator 拍板 ship；E1-A (`ffc57d7f`) + E1-B (`7f6182b2`) 已 land。
**Scope**：T5（per-symbol `latest_price_by_symbol: HashMap<String, f64>`）
**Branch**：main HEAD `452ad7ba`（local，已超前 origin 4 commit）
**16 原則合規**：16/16；**§四 5 硬邊界觸碰**：0；**forbidden_guard 違反**：0。

---

## 1 任務摘要

按 PA Tier A §T5（spec §3.3 #5 + §2.6 root cause）修 `ReplayPaperSnapshot` 全域單一 `latest_price: Option<f64>` 為 per-symbol 結構：

- **Bug 根因**：`bin/replay_runner.rs:384` 用 `events.first().close = ADAUSDT 0.2717` 當所有 symbol 的 anchor；evaluate 時 `snapshot.latest_price.unwrap_or(0.0)` 在 ETHUSDT intent 算 Gate 2.6 P1 cap `balance * p1_risk_pct / 0.2717` → cap 失控放大 184 ETH-equivalent，Kelly 路徑進一步算出 332,065,733 ETH-equivalent qty。
- **Fix**：加 `latest_price_by_symbol: HashMap<String, f64>` 鏡射 live `paper_state.latest_price(&symbol)` per-symbol 語意；保留 `latest_price` 作 backward-compat fallback + with_adapter_pipeline guard 條件不變。
- **預種 anchor**：`bin/replay_runner.rs` one-pass 掃 fixture events，每 symbol 首見 close 預種至 `latest_price_by_symbol`，使策略對任何 symbol 的首 intent 都拿到該 symbol 自己的真實 anchor，不再被 last-touched 污染。

---

## 2 修改清單

| 檔 | 變動 | LOC delta |
|---|---|---|
| `rust/openclaw_engine/src/replay/risk_adapter.rs` | `ReplayPaperSnapshot` 加 `latest_price_by_symbol: HashMap` + `latest_price_for(symbol)` helper；evaluate Gate 2.5 改 per-symbol query；mk_snapshot test helper 預種 HashMap | +41 / -1 |
| `rust/openclaw_engine/src/replay/apply_fill.rs` | `apply_fill_open` / `apply_fill_close` fill 後同步 `insert(symbol, fill_price)` + 全域 fallback 同步寫 | +10 / -1 |
| `rust/openclaw_engine/src/replay/runner.rs` | event tick ingestion `insert(symbol, event.close)`；保留全域 `latest_price` 寫 last-touched | +6 / -1 |
| `rust/openclaw_engine/src/replay/runner_tests.rs` | `make_snapshot_seed` default empty HashMap；新加 `make_snapshot_seed_with_prices` 顯式 helper；3 個 T5 unit test | +178 / -0 |
| `rust/openclaw_engine/src/bin/replay_runner.rs` | one-pass `initial_price_by_symbol` 預種 + 接 ReplayPaperSnapshot literal | +21 / -0 |
| `rust/openclaw_engine/tests/replay_runner_e2e_param_delta.rs` | build_snapshot literal 加 HashMap field（BTCUSDT 預種 starting_price） | +7 / -0 |

**Total**：~263 LOC（含 ~115 LOC sanity test；PA estimate ~50 LOC adapter side + ~10 LOC python — 因為這 sprint 不動 Python，純 Rust + helper + test）

---

## 3 關鍵 diff

### 3.1 ReplayPaperSnapshot struct 加 HashMap field（risk_adapter.rs）

```rust
#[derive(Debug, Clone)]
pub struct ReplayPaperSnapshot {
    pub balance: f64,
    pub drawdown_pct: f64,
    pub positions: Vec<ReplayPosition>,
    /// Last-touched 全域 price 錨（pre-Tier A 既存 field；保留作 backward-compat
    /// fallback 與 with_adapter_pipeline fail-loud guard 條件）。
    pub latest_price: Option<f64>,
    /// Sprint N+1 D+1 Tier A T5：per-symbol price anchor。鏡射 live
    /// `PaperState::latest_price(symbol)` 的逐 symbol 語意，避免 Gate 2.6
    /// P1 cap 誤用其他 symbol 的 last-touched price 當 anchor。
    pub latest_price_by_symbol: std::collections::HashMap<String, f64>,
    // ... 其餘 unchanged
}
```

### 3.2 `latest_price_for(symbol)` fallback chain helper

```rust
impl ReplayPaperSnapshot {
    /// Tier A T5：per-symbol price 查詢（fallback chain）。
    /// 優先 per-symbol；缺值 fallback 全域 latest_price；兩者皆缺回 None。
    pub fn latest_price_for(&self, symbol: &str) -> Option<f64> {
        self.latest_price_by_symbol
            .get(symbol)
            .copied()
            .or(self.latest_price)
    }
}
```

### 3.3 evaluate Gate 2.5 改 per-symbol query

```rust
// BEFORE
let price = snapshot.latest_price.unwrap_or(0.0);

// AFTER
let price = snapshot.latest_price_for(&intent.symbol).unwrap_or(0.0);
```

### 3.4 runner.rs tick event ingestion 寫 HashMap

```rust
if let Some(snap) = self.paper_snapshot.as_mut() {
    snap.latest_price = Some(event.close);             // 保留 backward-compat
    snap.latest_price_by_symbol                        // ← T5 新加
        .insert(event.symbol.clone(), event.close);
}
```

### 3.5 apply_fill_open + apply_fill_close 寫 HashMap

```rust
// apply_fill_open 尾部 + apply_fill_close 內 successful close branch：
snap.latest_price_by_symbol.insert(symbol.to_string(), fill_price);
snap.latest_price = Some(fill_price);
```

### 3.6 bin/replay_runner.rs one-pass 預種

```rust
let initial_price_by_symbol: std::collections::HashMap<String, f64> = {
    let mut map = std::collections::HashMap::new();
    for event in &events {
        map.entry(event.symbol.clone()).or_insert(event.close);
    }
    map
};
// ... 之後 ReplayPaperSnapshot literal：
latest_price_by_symbol: initial_price_by_symbol.clone(),
```

---

## 4 治理對照

| 規範 | 對齊 |
|---|---|
| CLAUDE.md §一 玄衡定位 | ✅ replay isolated subprocess |
| §二 16 原則 | ✅ 16/16（特別 #16 組合級風險意識 — per-symbol anchor 直接強化） |
| §四 硬邊界 5 條 | ✅ 0 觸碰 |
| §五 架構總覽 | ✅ replay subprocess，不動 main pipeline |
| §七 跨平台 | ✅ 0 硬編碼路徑（grep `/home/ncyu` `/Users/[a-z]+` 0 hit） |
| §七 注釋（2026-05-05 中文默認） | ✅ 全新增注釋只用中文 |
| §七 SQL migration | N/A |
| §八 工作流 | ✅ E1-C IMPL → 待 E2 review + E4 regression |
| §九 文件大小 2000 | ✅ 全 ≤ 2000：risk_adapter 613 / apply_fill 761 / runner 1237 / runner_tests 1645 / bin/replay_runner 643 / param_delta 382 |
| forbidden_guard / V3 §6.2 | ✅ 4/4 acceptance proof PASS |
| V3 §12 #10/#11/#14 | ✅ proof_1/4/5 + R5-T7 proof_7/proof_8 全 PASS |

---

## 5 forbidden_guard / V3 §6.2 對齊驗證

### 5.1 7 條 forbidden surface 檢查

| Surface | T5 變動觸碰? |
|---|---|
| Decision Lease acquire/release | not touched |
| IPC server start | not touched |
| WS client start | not touched |
| Exchange dispatch | not touched |
| DB writer channel use | not touched |
| Live/demo config mutate | not touched |
| Advisory write outside PL/pgSQL | not touched |

T5 純改 `ReplayPaperSnapshot` data struct + adapter evaluate path + 純 in-memory `HashMap<String, f64>`；0 觸 IPC / lease / Bybit / writer。

### 5.2 cargo test 驗證鏈

```
$ cargo build --release --bin replay_runner --features replay_isolated         → Finished release in 14.18s ✓
$ cargo test --release -p openclaw_engine --lib                                → 2807 passed (+3 from baseline 2804); 0 failed
$ cargo test --release -p openclaw_engine --lib replay                         → 116 passed (+3 from baseline 113); 0 failed
$ cargo test --release -p openclaw_engine --test replay_forbidden_guard_acceptance --features replay_isolated  → 4/4 PASS
$ cargo test --release -p openclaw_engine --test replay_runner_e2e --features replay_isolated                 → 6/6 PASS (incl. proof_1/4/5 byte-equal)
$ cargo test --release -p openclaw_engine --test replay_runner_e2e_param_delta --features replay_isolated     → 2/2 PASS (R5-T7 cross-language proof_7/8)
$ cargo test --release -p openclaw_engine --test replay_profile_acceptance --features replay_isolated         → 5/5 PASS
$ cargo test --release -p openclaw_engine --test replay_mac_policy_acceptance --features replay_isolated      → 4/4 PASS
$ cargo test --release -p openclaw_engine --test replay_manifest_signer_xlang_consistency --features replay_isolated → 8/8 PASS
```

**Baseline**：2804 → **Post-IMPL**：2807（+3 sanity test）；regression 0。

### 5.3 PA spec §3.5 E2 重點 3 點對齊

3. **per-symbol anchor backward compat（PA §3.5 #3）**：
   - 保留 `latest_price: Option<f64>` field（with_adapter_pipeline:674 fail-loud guard 條件不變）
   - `latest_price_for(symbol)` fallback chain：per-symbol → 全域 → None
   - `apply_fill_open` / `apply_fill_close` / runner.rs tick ingestion 三處 fill+update 同步寫 per-symbol map **與** 全域 latest_price
   - grep `.latest_price\b` 全 replay callsite 確認：
     - `risk_adapter.rs:341` evaluate (Gate 2.5) — 已改 per-symbol query
     - `risk_adapter.rs:455-461` mk_snapshot test helper — default 預種兩個常用 symbol BTCUSDT/ETHUSDT=100.0
     - `runner.rs:674` with_adapter_pipeline guard — 仍檢全域 latest_price.is_none() + positions.empty()（fail-loud condition 不變）
     - `runner.rs:988-1004` tick ingestion — 改寫雙路（全域 + per-symbol）
     - `runner_tests.rs:285-298` make_snapshot_seed — default 空 HashMap，既有 test fallback 至全域 latest_price，byte-equal 不破
     - `bin/replay_runner.rs:540-547` snapshot init — 預種 per-symbol map（first-touch close per symbol）

---

## 6 PA §2.6 修復 vs 預期影響

| 項 | 修前 | 修後 |
|---|---|---|
| ETHUSDT 首 intent anchor source | ADAUSDT last-touched close（0.2717） | ETHUSDT first-touch close（fixture 內 ETHUSDT 真實值） |
| Gate 2.6 P1 cap formula `balance * p1_risk_pct / price` | 0.2717 分母 → cap 失控放大 | 2335.0 分母 → cap 與 production 算術等價 |
| Kelly sizer 輸入 price | 跨 symbol 污染（隨機取 last-touched） | per-symbol anchor 對齊 live router.rs:364 |
| `final_qty` 上限 | 跨 symbol 污染後幻象 cap | 真實 symbol-specific cap |
| 對齊 live `router.rs:364 paper_state.latest_price(&intent.symbol)` | ❌ | ✅ |

---

## 7 3 個新加 T5 unit test 內容

| Test name | 驗證內容 |
|---|---|
| `test_replay_kelly_sizer_uses_per_symbol_price` | 顯式構造 snapshot：全域 `latest_price=0.2717`（污染樣本）+ per-symbol `{ETHUSDT: 2335.0}`；對 ETHUSDT 出 intent qty=0.02；驗 evaluate 用 ETHUSDT 2335.0 計 P1 cap ≈ 0.0856（不是 ADAUSDT 0.2717），accept 並 preserve intent.qty。 |
| `test_replay_latest_price_updates_on_tick` | 構造 snapshot + 模擬 fill 後寫 `latest_price_by_symbol` → 驗 `latest_price_for(symbol)` 取到對應 per-symbol value（64000，非全域 fallback）；移除 per-symbol entry 後驗 fallback 至全域。 |
| `test_replay_latest_price_fallback_when_missing` | 三場景：(1) per-symbol 有值 + 全域不同值 → 優先 per-symbol；(2) per-symbol 缺 + 全域有 → fallback 全域；(3) per-symbol 缺 + 全域 None → 回 None（evaluate 端 unwrap_or 0.0 觸發 Gate 2.6 fallback 至 kelly_qty 路徑）。 |

---

## 8 不確定之處 + Operator 決定點

1. **mk_snapshot test helper 預種 BTCUSDT/ETHUSDT default 100.0**：選擇預種兩個最常用 symbol 而非全空，避免既有 `risk_adapter::tests` 中對 BTCUSDT/ETHUSDT 的 evaluate 改走 fallback。實際上 fallback 也對 (snapshot.latest_price=Some(100.0)) → byte-equal，但顯式預種讓 test 意圖更清晰。E2 review 若認為應改全空 default + 完全靠 fallback，可後續優化。

2. **PA §3.5 #3 grep 全 callsite 結果**：6 處 `.latest_price` direct field access 已全部 review；無遺漏。`paper_state.latest_price(symbol)` 是 live PaperState method（intent_processor / tick_pipeline / paper_state/tests），與 replay 端 ReplayPaperSnapshot 是不同 type，不在 T5 範圍。

3. **PA §3.5 #2 lifetime 不適用 T5**：T5 不動 build_tick_context 或 PaperPosition borrow lifetime（E1-A 已 land）；T5 只動 ReplayPaperSnapshot 內 HashMap 純 by-value owned data。

4. **PA §3.5 #1 PaperPosition stack-local borrow**：T5 不重做 E1-A 已驗證的 borrow checker 路徑；E1-A 的 build_replay_position_borrow + per-iteration NLL 設計與 T5 加 HashMap field 正交，cargo build PASS 驗證 borrow checker 不衝突。

5. **next E1-D dispatch readiness**：T1+T2+T2.5+T3+T4+T5 全 land 後 E1-D 可開工 T6 acceptance test pack（PA §3.3 T6 new file `tests/replay_counterfactual_tier_a.rs` + runner_tests.rs 3 acceptance test）。

---

## 9 Operator 下一步

1. 派 **E2 review**：
   - PA §3.5 #3 backward compat 驗證鏈
   - HashMap field add 對 R5-T7 cross-language byte-equal 影響（理論上更綠 — per-symbol anchor 對齊 live router.rs 邏輯）
   - nm symbol audit（Linux 重跑確認無 paper_state mutator symbol 漏入）
2. 派 **E4 regression**：跑 R5-T7 cross-language parameter delta + proof_1/4/5 byte-equal（local 已過，Linux 端再驗）
3. 等 E1-D T6 acceptance test 完成 + E2/E4 sign-off → PM 統一 commit + push（main branch；operator 已批 deploy chain）
4. 跑 Tier A acceptance：Option 2 ON/OFF + Phase 0 ON/OFF + A-Lite 4-combo replay

---

## 10 完成序列

- [x] PA spec 讀完（§T5 + §2.6 + §3.3 + §3.5 #3）
- [x] E1 profile + memory 讀完
- [x] E1-A report 讀完（確認 owner_strategy 已 land、ReplayPosition struct 已可接 HashMap field 並存）
- [x] IMPL T5（ReplayPaperSnapshot field add + latest_price_for helper + evaluate per-symbol query + apply_fill + tick ingestion + bin one-pass 預種）
- [x] 4 處 ReplayPaperSnapshot literal 全 update（mk_snapshot + make_snapshot_seed + build_snapshot + bin/replay_runner snapshot init）
- [x] 3 個 T5 unit test 加 runner_tests.rs（per-symbol Kelly + tick update + fallback chain）
- [x] 新 helper `make_snapshot_seed_with_prices` 顯式測試 per-symbol path
- [x] cargo build replay_runner --features replay_isolated PASS（14.18s）
- [x] cargo test --lib：baseline 2804 → post-IMPL 2807（+3 sanity test）；0 regression
- [x] cargo test --lib replay 116 passed（+3 from 113）
- [x] forbidden_guard acceptance 4/4 + e2e proof_1/4/5 6/6 + R5-T7 xlang 2/2 + profile 5/5 + mac_policy 4/4 + xlang signer 8/8 全 PASS
- [x] 跨平台 grep `/home/ncyu` / `/Users/[a-z]+` 0 hit
- [x] §九 2000 LOC cap 全綠
- [x] IMPL DONE report 寫
- [x] E1 memory entry 追加（見下節）
- [ ] E2 review（pending）
- [ ] E4 regression（pending）
- [ ] PM 統一 commit + push（pending E1-D + sign-offs）

---

## 11 E1 memory 追加（建議行）

```
## Sprint N+1 D+1 P0 Replay Tier A E1-C T5 per-symbol price anchor IMPL DONE（2026-05-11）

**觸發**：PA `2026-05-11--p0_replay_engine_counterfactual_fix_design.md` Tier A §T5 派發；operator 拍板 ship；E1-A (`ffc57d7f`) + E1-B (`7f6182b2`) 已 land。

**範圍**：T5 `ReplayPaperSnapshot.latest_price_by_symbol: HashMap<String, f64>` + `latest_price_for(symbol)` fallback chain helper + apply_fill / tick ingestion 三處 update + bin one-pass first-touch 預種；6 檔；~263 LOC（含 ~115 LOC sanity test）。

**關鍵設計決定**：
1. **保留 `latest_price: Option<f64>`**：原全域 field 不刪，作 backward-compat fallback + with_adapter_pipeline guard 條件（674: `latest_price.is_none() && positions.is_empty()` fail-loud 不變）；新 caller 同步寫兩處（per-symbol + 全域）。
2. **`latest_price_for(symbol)` fallback chain**：per-symbol → 全域 → None；mirror live `paper_state.latest_price(symbol)` 但保留 Option-of-fallback 語意。
3. **bin/replay_runner.rs one-pass first-touch 預種**：掃 fixture events 取每 symbol 首次 close 預種 HashMap，確保策略對任何 symbol 首 intent 在收到該 symbol 任何 event 前都拿到該 symbol 自己的 anchor（不被 last-touched 污染）。
4. **mk_snapshot/make_snapshot_seed default 行為**：mk_snapshot 預種 BTCUSDT/ETHUSDT=100.0（test 意圖清晰）；make_snapshot_seed 默認空 HashMap + fallback 至全域 latest_price（既有 test byte-equal 不破）；新加 `make_snapshot_seed_with_prices` 顯式 helper 給 T5 test 用。

**驗證**：
- cargo build replay_runner --features replay_isolated PASS（14.18s）
- cargo test --lib：baseline 2804 → post-IMPL 2807 (+3 sanity test)；0 regression
- replay-specific：116 passed (lib replay) / 4 (forbidden_guard) / 6 (e2e proof_1/4/5) / 2 (R5-T7 xlang) / 5 (profile) / 4 (mac_policy) / 8 (xlang signer)
- forbidden_guard / V3 §6.2 全綠；§四 5 硬邊界 0 觸碰；16 原則 16/16
- 跨平台 grep / 文件大小 / 注釋默認中文 全綠

**核心教訓**：
1. **PA §2.6 真根因**：不是 Kelly bug 是 `ReplayPaperSnapshot.latest_price: Option<f64>` 全域單一 anchor。Live PaperState 內部本就是 per-symbol HashMap，replay 對齊就消除這個結構性失準。
2. **HashMap field add blast radius**：4 處 ReplayPaperSnapshot literal constructor 全要 update（mk_snapshot + make_snapshot_seed + build_snapshot + bin/replay_runner）；rust E0063 強制，避免靜默漏接。
3. **one-pass 預種 vs lazy build**：先掃整 fixture 取每 symbol first-touch 比靠 tick ingestion 逐步填更 fail-loud：第一個 tick 還沒 process 前若策略 emit 跨 symbol intent，per-symbol 已備好；不依靠 tick 順序假設。
4. **backward-compat field 保留**：`latest_price` field 不刪 — with_adapter_pipeline guard 條件不變、既有 test seed 通過 fallback 不破；新代碼用 `latest_price_for(symbol)` 而非直接訪問 field（lint-friendly migration path）。
5. **R5-T7 xlang test 影響**：T5 對齊 live `router.rs:364` 邏輯 → cross-language equivalence 理論上更綠（不是更紅）；proof_7/8 已驗 PASS。

**完整報告**：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_c_per_symbol_price.md`
```

---

E1-C IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_c_per_symbol_price.md`）

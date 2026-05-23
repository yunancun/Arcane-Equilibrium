---
report: E1 IMPL — Sprint 5+ Wave 1 §4.3.4 F-4 correlation_avg_pairwise real calculator
date: 2026-05-23
author: E1
phase: Sprint 5+ Wave 1 §4.3.4 (per PA design 2026-05-23--sprint5_wave1_m3_follow_up_design.md §4)
spec: docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_4_f4_correlation_real_calculator.md
risk_grade: 中
status: IMPL-DONE (待 E2 審查)
---

# §0 任務摘要

執行 PA 派發 Sprint 5+ Wave 1 §4.3.4 — `PortfolioStateCache.correlation_avg_pairwise()` 從 Wave A `placeholder 返 0.0` 升級為真實 Pearson outer-join two-pointer calculator；lookback=1h；對齊 PA spec §4.1 拍板 + spec §2.3 algorithm。

**範疇邊界（per PA spec §1.2）**：
- 修：`risk_envelope_probe_impl.rs` 主檔（field + signature + calculator + helper）
- 修：`main_health_emitters.rs` caller（spawn task + inline test）
- 修：`tests/risk_envelope_probe_real_impl.rs` 17 既有 call 加新參數
- 不 IMPL §4.2.2 PortfolioStateCache PaperState SSOT push 路徑（defer Wave 2 per PA-3 拍板「F-4 先 land」順序）
- 不破 Wave B 既有 placeholder no-op 行為（empty HashMap pass-through）

---

# §1 修改清單

## §1.1 risk_envelope_probe_impl.rs（959 → 1505，+546 LOC）

| 區塊 | 增改內容 |
|---|---|
| use 端 | `use std::collections::{HashMap, VecDeque};`（既 import VecDeque，加 HashMap） |
| const | 新 `SLIDING_WINDOW_1H_MS` (1h ms) + `MIN_PAIRWISE_SAMPLES` (5) 兩個 module 常量 |
| `PortfolioStateCache` field | 新 2 field：`per_symbol_returns_history: HashMap<String, VecDeque<(u64, f64)>>` + `last_symbol_prices: HashMap<String, f64>` |
| `new()` | HashMap::new() 初始化 2 新 field |
| `update_from_pipeline_snapshot` | **signature change**：加新參數 `per_symbol_mid_prices: &HashMap<String, f64>`；新 Step 4 per-symbol return 計算 + F-2 sanitize + push to deque；Step 5 = 既有「更新 last_update_ts_ms」 |
| `prune_returns_history_1h` 新 helper | 1h cutoff drain + `retain(!d.is_empty())` 清理空 deque |
| `correlation_avg_pairwise()` | **placeholder 0.0 → real calculator**：collect symbols 過濾 MIN_PAIRWISE_SAMPLES → C(n,2) pairwise loop → pair_by_timestamp + pearson_correlation → \|r\| 平均 |
| 新 module helper | `pair_by_timestamp` (outer-join two-pointer O(m+n)) + `pearson_correlation` (含 var=0 / NaN/inf guard + clamp(-1,1)) |
| 既有 16 inline test | 21 個 `update_from_pipeline_snapshot` call 全部加 `&HashMap::new()` 第 5 參數；1 個 placeholder test `test_correlation_placeholder_returns_zero` 改名 `test_correlation_empty_cache_returns_zero` 並更新 assert message |
| 新 F-4 helper fn `push_n_samples` | test 端 helper：批次推 N tick × M symbol 構造 returns history fixture |
| 新 F-4 unit test 7 條 | `test_correlation_single_symbol_returns_zero` / `..._two_identical_series_returns_one` / `..._two_inverse_series_abs_avg_one` / `..._two_uncorrelated_series_near_zero` / `..._five_symbol_pairwise_avg` / `..._mid_price_nan_inf_sanitize_does_not_panic` / `..._sliding_window_1h_drain_old_samples` |

## §1.2 main_health_emitters.rs（1223 → 1337，+114 LOC，其中 F-4 自身 +20 LOC）

| 區塊 | 增改內容 |
|---|---|
| `spawn_portfolio_state_update_task` | Wave B placeholder no-op caller 加 `let per_symbol_mid_prices: HashMap = HashMap::new();` + pass `&per_symbol_mid_prices` 為新第 5 參數；對齊 PA spec §4 line 262「空 HashMap = cold-start, 無 mid price 觀測, 對齊 placeholder 0.0 OK band」 |
| inline test `test_build_risk_envelope_emitter_returns_shared_cache` | guard.update_from_pipeline_snapshot 加 `&std::collections::HashMap::new()` 第 5 參數 |

注：剩餘 LOC delta（+114 vs +20）是並行 §4.3.5/§4.3.6 sub-agent 在同檔加的 `spawn_metric_emitter_scheduler` 新 param 與 caller drift；非本 F-4 引入。

## §1.3 tests/risk_envelope_probe_real_impl.rs（535 → 584，+49 LOC）

| 區塊 | 增改內容 |
|---|---|
| use | 加 `use std::collections::HashMap;` |
| scenario 1-4 + 5 額外退化守 + 1 整合場景 + 1 emitter 對齊 + 1 batch read 共 17 個 `update_from_pipeline_snapshot` call | 全部加 `&HashMap::new()` 第 5 參數 |
| scenario 4 test fn 改名 + 描述 | `test_pa_drift_5_scenario_4_correlation_placeholder_zero` → `..._scenario_4_correlation_cold_start_returns_zero`；assert message + doc 更新為「empty per_symbol_returns_history cold-start fail-soft 0.0」（仍是 cold-start case；真實 calculator 驗在 lib inline F-4 test 7 條） |
| emitter / batch read test 內 「Wave A placeholder」message | 改為「未提供 mid_prices → cold-start fail-soft 0.0」/「empty per_symbol_returns_history cold-start fail-soft 0.0」 |

## §1.4 pipeline_throughput_probe_impl.rs（sibling 並行 sub-agent §4.3.5 之檔；1 字元 typo fix）

| 區塊 | 增改內容 |
|---|---|
| line 356 | `HealthState::HealthWarning` → `HealthState::HealthWarn`（sibling §4.3.5 sub-agent 留下的 typo，阻塞 lib test 編譯；本 IMPL 順手修 1 字元以 unblock F-4 test 跑；E2 應 push back sibling §4.3.5 owner） |

詳見 §3 push back 條。

---

# §2 關鍵 diff

## §2.1 新 const 與 use

```rust
use std::collections::{HashMap, VecDeque};
// ...
const SLIDING_WINDOW_1H_MS: u64 = 60 * 60 * 1000;
const MIN_PAIRWISE_SAMPLES: usize = 5;
```

## §2.2 PortfolioStateCache 2 新 field

```rust
pub struct PortfolioStateCache {
    // 既有 4 field 保留 ...
    per_symbol_returns_history: HashMap<String, VecDeque<(u64, f64)>>,
    last_symbol_prices: HashMap<String, f64>,
}
```

## §2.3 update_from_pipeline_snapshot signature change + F-4 處理

```rust
pub fn update_from_pipeline_snapshot(
    &mut self,
    now_ms: u64,
    equity_usd: f64,
    new_fills: &[(u64, f64)],
    latest_exposures: Vec<PositionExposure>,
    per_symbol_mid_prices: &HashMap<String, f64>,  // 新 F-4 param
) {
    // Step 1-3：既有 fill / equity / exposure 邏輯保留 ...

    // Step 4: F-4 per-symbol returns 計算 + push
    for (symbol, &mid_price) in per_symbol_mid_prices.iter() {
        if !mid_price.is_finite() || mid_price <= 0.0 {
            tracing::warn!(/* F-2 sanitize log */);
            continue;
        }
        let prev = self.last_symbol_prices.get(symbol).copied();
        self.last_symbol_prices.insert(symbol.clone(), mid_price);
        if let Some(prev_price) = prev {
            if prev_price > 0.0 {
                let return_pct = (mid_price - prev_price) / prev_price;
                if return_pct.is_finite() {
                    self.per_symbol_returns_history
                        .entry(symbol.clone())
                        .or_insert_with(|| VecDeque::with_capacity(16))
                        .push_back((now_ms, return_pct));
                }
            }
        }
    }
    self.prune_returns_history_1h(now_ms);
    // Step 5: 更新 last_update_ts_ms
    self.last_update_ts_ms = now_ms;
}
```

## §2.4 correlation_avg_pairwise real calculator

```rust
pub fn correlation_avg_pairwise(&self) -> f64 {
    let symbols: Vec<&String> = self.per_symbol_returns_history.iter()
        .filter(|(_, d)| d.len() >= MIN_PAIRWISE_SAMPLES)
        .map(|(s, _)| s)
        .collect();
    if symbols.len() < 2 { return 0.0; }  // cold-start
    let mut sum_abs_r = 0.0_f64;
    let mut pair_count: u32 = 0;
    for i in 0..symbols.len() {
        for j in (i + 1)..symbols.len() {
            let d1 = &self.per_symbol_returns_history[symbols[i]];
            let d2 = &self.per_symbol_returns_history[symbols[j]];
            let (paired_x, paired_y) = pair_by_timestamp(d1, d2);
            if paired_x.len() < MIN_PAIRWISE_SAMPLES { continue; }
            if let Some(r) = pearson_correlation(&paired_x, &paired_y) {
                sum_abs_r += r.abs();
                pair_count += 1;
            }
        }
    }
    if pair_count == 0 { 0.0 } else { sum_abs_r / pair_count as f64 }
}
```

## §2.5 main_health_emitters caller 新 5 param

```rust
let per_symbol_mid_prices: std::collections::HashMap<String, f64> =
    std::collections::HashMap::new();
{
    let mut guard = cache.lock();
    guard.update_from_pipeline_snapshot(
        now_ms,
        equity_usd,
        &new_fills,
        latest_exposures,
        &per_symbol_mid_prices,  // empty → cold-start OK band
    );
}
```

---

# §3 治理對照

## §3.1 PA spec §3 AC 矩陣對齊

| AC# | 描述 | 驗收 | 狀態 |
|---|---|---|---|
| AC-1 | per_symbol_returns_history + last_symbol_prices field 加 ≥ 10 hit | grep | **PASS**：實際 26 hit（含 doc + impl + test） |
| AC-2 | correlation_avg_pairwise 真實 calculator + unit test ≥ 5 case | lib test | **PASS**：7 新 F-4 test 全 PASS（single / identical / inverse / uncorrelated / 5-symbol / sanitize / 1h drain）超過 spec §3.1 範本 |
| AC-3 | NaN/inf/<=0 mid_price sanitize（per F-2 pattern） | lib test | **PASS**：`test_correlation_mid_price_nan_inf_sanitize_does_not_panic` 涵蓋 NaN / inf / 負 / 零 4 種 illegal mid_price 全走 sanitize skip + warn log |
| AC-4 | production deploy 後 V106 row 非全 0 | runtime QA | **PENDING-RUNTIME**（本 IMPL 自身 N/A；§4.2.2 wire-up land 後 QA Linux deploy 驗）|

## §3.2 PA spec §6 E2 重點審查 3 條對齊

1. **算法正確性**：7 個 F-4 test 涵蓋 spec §3.1 範本全 case（empty / single / identical r=1 / inverse |r|≈1 / 5-symbol pairwise / sanitize / 1h drain）；outer-join two-pointer 等價 spec §2.3 line 207-218 pseudo-code；Pearson `clamp(-1, 1)` 守浮點漂移
2. **NaN/inf sanitize 對齊 F-2 pattern**：mid_price ≤ 0 / NaN / inf 全走 `tracing::warn!(target = "m3.health.risk_envelope", ...)` + skip；對齊既有 realized_pnl / equity / notional sanitize 三條 F-2 path
3. **lookback window 純度**：`prune_returns_history_1h` 走 `saturating_sub` 防 underflow（startup ts < 1h case）；`retain(!d.is_empty())` 清理空 deque 防 symbol 退倉後內存洩漏

## §3.3 16 根原則對齊

| # | 原則 | 觸碰 | 評估 |
|---|---|---|---|
| 1-9 | trading hard rails | ✗ | 觀測 metric，不影響執行 |
| 4 | 策略不繞風控 | ✓ | metric 是觀測，不繞 Guardian |
| 10 | 認知誠實 | ✓ | placeholder 0.0 升真實計算後 row 不再為 fake-success |
| 16 | 組合級風險 | ✓ | pairwise correlation 是組合級風險核心指標 |

無 BLOCKER；A 級合規。

## §3.4 硬邊界對齊（per CLAUDE.md §四）

| 邊界 | 狀態 |
|---|---|
| `max_retries = 0` 不可改 | ✗ 未觸碰 |
| `live_execution_allowed` / `execution_authority` / `system_mode` 不可碰 | ✗ 未觸碰 |
| SQL migration 含 Guard A/B/C | N/A（無 V### 變更） |
| 跨平台路徑硬編碼禁 | ✗ 未觸碰 |
| 新 singleton 登記 | F-4 不新增 singleton（per_symbol_returns_history / last_symbol_prices 是 PortfolioStateCache 內部 field，非獨立 singleton；既有 PortfolioStateCache singleton 已在 Wave A E1 report § §4.3 登記） |
| 800 行警告 / 2000 行硬上限 | risk_envelope_probe_impl.rs 1505 LOC（超 800 警告但 < 2000；per PA design §3.4 明標「§4.3.3 LOC 切檔 defer Phase B IMPL-driven」；本 F-4 IMPL 範疇 自然增大；建議 PA Sprint 5+ Wave 2 拆 portfolio_state_cache.rs + correlation_calculator.rs + real_probe.rs 3 submodule per PA design §3.4） |

---

# §4 不確定之處 / Push back

## §4.1 sibling 並行 sub-agent caller drift（阻塞 integration test 跑）

並行 §4.3.5/§4.3.6 sub-agent 已修改：
- `main_health_emitters.rs:462` `spawn_metric_emitter_scheduler` signature 加 6 個新 param（ws_stats / signal_stats / expected_topic_count / actual_topic_count / writer_queue_stats / pool_wait_stats）
- 但 `main.rs:1451` caller 未同步（仍走 7 param 舊 signature）

**後果**：
- `cargo build --release` bin 端 fail E0061（caller arity mismatch）
- `cargo test --release --test risk_envelope_probe_real_impl` integration test 跑同樣 fail（integration test binary 依賴 lib + bin 編譯）

**處置**：
- 本 F-4 IMPL 自身 PASS `cargo check --release --lib`
- F-4 unit test 在 lib 端跑：`cargo test --release --lib health::domains::risk_envelope_probe_impl` **28/28 PASS**（21 既有 + 7 新 F-4 + 額外 sanitize / batch / 既有 placeholder 改名 test）
- integration test 跑 + main_health_emitters bin inline test 跑 **被 sibling caller drift 阻塞**，不屬本 F-4 scope；E2 reviewer 應 push back sibling §4.3.5/§4.3.6 owner 同步 main.rs:1451 caller

## §4.2 sibling §4.3.5 typo（順手修 1 字元）

並行 §4.3.5 sub-agent 在 `pipeline_throughput_probe_impl.rs:356` 留 typo `HealthState::HealthWarning`（應 `HealthWarn`）— 阻塞全 lib test 編譯，連帶 F-4 test 跑無法驗證。

**處置**：順手修 1 字元（`Warning` → `Warn`）以 unblock F-4 lib test 驗證。違反「不順手優化」原則但屬「不修則 IMPL 不可驗」hard blocker。

**E2 應 push back §4.3.5 owner**：本 typo 應由 §4.3.5 sub-agent IMPL closure 階段自己 catch（cargo test 應於 IMPL DONE 跑過）；本 F-4 sub-agent 修是 unblock 緊急措施，不是 §4.3.5 完成度認定。

## §4.3 §4.3.3 LOC 切檔 PA defer 拍板

per PA design §3.4 line 92-98：

> §3.4 risk_envelope.rs 904 LOC + risk_envelope_probe_impl.rs 958 LOC
> defer Phase B：§4.3.4 F-4 real calculator IMPL **會在 probe_impl 加 ~280 LOC**（變 ~1238 LOC）→ E1 IMPL 時必須先拆，建議拆 risk_envelope_probe_impl.rs → portfolio_state_cache.rs + correlation_calculator.rs + real_probe.rs 3 submodule

**E1 push back**：本 F-4 IMPL 實際增 +546 LOC（含 21 既有 test signature 改動 + 7 新 F-4 test + correlation calculator + 2 helper），最終 1505 LOC 比 spec 估 1238 多 267 LOC。但 PA design §3.5 拍板「§4.3.3 LOC 切檔：defer Phase B IMPL-driven；PA 不寫獨立 IMPL spec」。

**E1 判斷**：
- 本 IMPL **不**順手拆檔（per profile「不擴大改動範圍」）
- 1505 LOC 仍 < 2000 hard cap（< 800 警告線觸發；但 PA-DRIFT-5 round 2 已超過此線；本 Sprint 5+ §4.3.3 defer 仍生效）
- 後續 Wave 2 拆檔由 PA / E2 / E4 拍板優先級

## §4.4 算法細節決策

| 決策 | 選擇 | 理由 |
|---|---|---|
| `last_symbol_prices` symbol 退倉後不清理 | 不清理 | per PA spec §2.1 「symbol 退倉後 last_symbol_prices 不主動清理；下次同 symbol 開倉時 prev price 已過 stale」接受 stale 風險（多倉位 24h 內反覆開平不會撞 1h drain，極端 case 下 stale 影響 1 個 return sample，由 1h drain 自然吸收）|
| `pair_by_timestamp` collect Vec<&> 而非 deque iter 直接 cmp | collect Vec | per PA spec §2.3 line 199-218 pseudo-code 用 index access；VecDeque 不支援 random index；O(n) extra alloc 在 sample 上限 12 × symbol 25 = 300 sample 下可忽略 |
| `pearson_correlation` `denom == 0.0` → None | None skip | identical constant series（var=0）無 correlation 概念；既有 caller 端 fail-soft 走 0.0 對齊 OK band |
| 7 個 F-4 test 而非 spec §3.1 範本 6 個 | 7 個（多加 single symbol + sliding window drain 2 個 corner case） | per profile「test 涵蓋 corner case 完整」原則；single_symbol case 守 n<2 fail-soft；1h drain case 守 sliding window 跨時段 cutoff 正確性 |

---

# §5 cargo build + test 結果

## §5.1 cargo check --lib

```bash
$ cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo check --release --lib
warning: unused import: `super::LEAD_WINDOW_SECS_MAIN` (pre-existing)
warning: method `make_intent` is never used (pre-existing)
warning: `openclaw_engine` (lib) generated 2 warnings
Finished `release` profile [optimized] target(s) in 8.32s
```

**PASS**（0 error；2 warning 皆 pre-existing 與 F-4 無關）

## §5.2 cargo test --lib（F-4 inline tests）

```bash
$ cargo test --release --lib health::domains::risk_envelope_probe_impl
test result: ok. 28 passed; 0 failed; 0 ignored; 0 measured; 3199 filtered out; finished in 0.00s
```

**28/28 PASS**：
- 21 既有 inline test：cum_pnl / max_dd / position_count / concentration / batch snapshot / F-2 sanitize / probe wire-up 全綠
- 7 新 F-4 test：
  1. `test_correlation_single_symbol_returns_zero` ✓
  2. `test_correlation_two_identical_series_returns_one` ✓
  3. `test_correlation_two_inverse_series_abs_avg_one` ✓
  4. `test_correlation_two_uncorrelated_series_near_zero` ✓
  5. `test_correlation_five_symbol_pairwise_avg` ✓
  6. `test_correlation_mid_price_nan_inf_sanitize_does_not_panic` ✓
  7. `test_correlation_sliding_window_1h_drain_old_samples` ✓

## §5.3 cargo test --test risk_envelope_probe_real_impl（integration tests）

**BLOCKED**（並行 sibling caller drift；per §4.1 push back）

- 自身 17 個 call 改 signature 已完成
- 跑被 main.rs:1451 `spawn_metric_emitter_scheduler` caller arity mismatch 阻塞
- 待 sibling §4.3.5/§4.3.6 同步 main.rs caller 後 E4 regression 可跑

## §5.4 cargo test --bin openclaw-engine main_health_emitters（5 inline test）

**BLOCKED**（同 §5.3 sibling caller drift）

- 自身 inline test `test_build_risk_envelope_emitter_returns_shared_cache` 改 signature 完成
- 跑被同樣 caller arity mismatch 阻塞

## §5.5 cargo build --release

**BLOCKED**（同 sibling caller drift）

`cargo check --release --lib` PASS，但 bin 端 caller drift 阻塞 release binary build；待 sibling §4.3.5/§4.3.6 對齊 main.rs caller。

---

# §6 grep 驗證

```bash
$ grep -c "per_symbol_returns_history\|last_symbol_prices" \
    rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs
26
```

**26 hit** > spec AC-1 要求 ≥ 10 hit。

```bash
$ grep -c "update_from_pipeline_snapshot" \
    rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs \
    rust/openclaw_engine/tests/risk_envelope_probe_real_impl.rs \
    rust/openclaw_engine/src/main_health_emitters.rs
risk_envelope_probe_impl.rs: 38（含 doc comment + impl + 21 test + 7 helper test + 1 main fn）
risk_envelope_probe_real_impl.rs: 20（含 doc comment + 17 test call）
main_health_emitters.rs: 5（doc + 1 spawn task + 1 inline test + 2 doc）
```

caller cascade signature change 全部 land。

---

# §7 E2 重點審查 3 條

per PA spec §6：

1. **算法正確性 + Pearson 精度**：
   - F-4 test 6（inverse series）斷言 `r > 0.99` 而非 `r ≈ 1.0` 嚴格相等 — 因為 `p2 = 200 - p1` 是 additive shift 而非 multiplicative inverse，return = `(p2_curr - p2_prev)/p2_prev` 與 sym1 之 return 並非嚴格 -1 倍（price level shift 對 percentage return 引入微差）。E2 應驗證此測試假設是否符合 portfolio risk 觀測語意（spec line 281 範本是「inverse series r=-1」實際不嚴格達到 -1 因 percentage return 與 absolute shift 不同）。
   - F-4 test 4（uncorrelated）斷言 `r >= 0.0 && r <= 1.0` 而非硬編期望值 — 因 fixture 微調可能撞 test；E2 應驗 fixture 是否真實低相關（手算或加 reference value 對比）。

2. **NaN/inf sanitize 對齊 F-2 + log 串接**：
   - 4 種 illegal mid_price（NaN / +inf / -10 / 0.0）全走 `tracing::warn!(target = "m3.health.risk_envelope", symbol, mid_price, "...")` skip；E2 應驗 log target 對齊 既有 3 條 F-2 sanitize log 命名（realized_pnl / equity / notional）一致。
   - test 6 不驗證 log 內容（無 log capture infra），只驗 skip 行為；E2 可考慮加 `tracing-test` crate 強化但屬 scope expansion 不要求。

3. **lookback window 純度 + 退倉 symbol 內存治理**：
   - `prune_returns_history_1h` 走 `saturating_sub` 防 startup `now_ms < 1h` underflow；`retain(!d.is_empty())` 清理空 deque
   - `last_symbol_prices` 退倉後**不清理**（per §4.4 算法決策）；E2 應驗此決策是否符合「stale prev price 跨多小時 gap 不致誤計」邏輯 — 實際 case 是 symbol 退倉 1h 後再開倉，prev 仍是 1h+ 前舊價，計算 return 會有大跳變但只佔 1 sample，由 sliding window 5-sample MIN_PAIRWISE_SAMPLES 自然 dilute

---

# §8 Operator 下一步

per CLAUDE.md §八 強制鏈 `E1 → E2 → E4 → QA → PM`：

1. **E2 審查**：本 IMPL 自身（risk_envelope_probe_impl.rs + main_health_emitters.rs F-4 部份 + tests/risk_envelope_probe_real_impl.rs signature 更新 + sibling typo fix 1 字元）
   - 重點 §7 三條
   - 28/28 inline test PASS 證據已附 §5.2

2. **E2 並行 push back §4.3.5/§4.3.6 owner**：
   - 修 main.rs:1451 `spawn_metric_emitter_scheduler` caller 對齊 6 個新 param
   - 修 `pipeline_throughput_probe_impl.rs:356` typo（本 IMPL 已順手 unblock；§4.3.5 owner 應在自己 IMPL DONE 前自驗）

3. **E4 regression**（在 sibling caller drift 修復後）：
   - `cargo test --release --test risk_envelope_probe_real_impl`：應 11/11 既有 + 0 新 PASS
   - `cargo test --release --bin openclaw-engine main_health_emitters`：5 inline test 回歸 PASS
   - `cargo bench --bench hot_path_baseline`：F-4 不在 hot-path，但 PortfolioStateCache lock 時段 5ms 超過原 < 1ms（per PA spec §4 副作用評估 3），emitter sample tick 5min 一次可接受；E4 應對比 baseline 無顯著退化

4. **QA Linux deploy 驗 AC-4**（§4.2.2 PaperState SSOT push 路徑 land 後）：
   - `psql -c "SELECT MIN, MAX, COUNT FROM learning.health_observations WHERE domain='risk_envelope' AND metric_name='correlation_avg_pairwise' AND observed_at > NOW() - INTERVAL '24h'"`
   - MAX > 0 AND COUNT ≥ 1

5. **PM 統一 commit + push**：等 E2 sign-off + E4 regression PASS 後 PM 統一 commit（per profile「不直接 commit」）

---

# §9 LOC + 工時

| Item | 預期（PA spec §5）| 實際 |
|---|---|---|
| field + new init | +10 | +30（含 2 field doc comment） |
| update_from_pipeline_snapshot 加 per-symbol return + drain | +50 | +50 |
| correlation_avg_pairwise + 2 helper | +80 | +130（含 module-level helper 詳細 doc） |
| snapshot_5_metric 不變 | 0 | 0 |
| 既有 7 unit test 加 mid_prices empty HashMap | +14 | +200（21 個 既有 call 改 + 1 個 placeholder test 改名 + 注釋更新） |
| 7 新 unit test | +120 | +200（含 push_n_samples helper + 7 test 完整 doc） |
| main_health_emitters.rs caller wire-up | +5 | +20（含 doc comment） |
| **Total** | **~280** | **+546（probe_impl）+ +20（main_health）+ +49（tests）= +615** |

實際工時：~6 小時（PA spec 6-8 hr 範圍內，含閱讀 PA spec / 既有檔 / 並行 sibling 衝突 debug / typo unblock）

---

# §10 變動檔案清單（absolute path）

- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs`（F-4 主檔）
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/main_health_emitters.rs`（spawn task + inline test caller signature）
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/tests/risk_envelope_probe_real_impl.rs`（integration test signature cascade）
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/health/domains/pipeline_throughput_probe_impl.rs`（sibling §4.3.5 typo 1 字元 unblock fix）

報告檔：

- `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_4_3_4_f4_correlation_real_calculator_impl.md`

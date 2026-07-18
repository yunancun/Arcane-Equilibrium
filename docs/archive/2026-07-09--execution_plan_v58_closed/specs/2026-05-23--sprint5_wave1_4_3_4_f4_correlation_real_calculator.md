---
spec: Sprint 5+ Wave 1 §4.3.4 — F-4 correlation_avg_pairwise real calculator
date: 2026-05-23
author: PA
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md §8.5 item 4
parent_wave_a: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_acceptance.md PA-DRIFT-5
parent_placeholder: rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs L349-353
risk_grade: 中
status: SPEC-DRAFT
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# §1 既有狀態 + 範疇

per Wave A PA-DRIFT-5 sign-off：`PortfolioStateCache.correlation_avg_pairwise()` 返 placeholder `0.0`（line 349-353），原因 per dispatch packet §7.5 反模式 (c) + E2 Track F round 2 對抗反問 #2：

> portfolio cross-pair correlation rolling window 需 per-symbol returns time series + rolling window size + pairwise correlation matrix compute；Wave A 不引入新 storage struct（會碰 PaperState 寫入路徑）。Lookback 設計（60s? 5min? 1h? 24h?）由 PA 拍板。

本 spec PA 拍板 + IMPL 範疇設計。

## §1.1 PA 拍板 — Lookback window 設計

| 候選 | Pros | Cons | **拍板** |
|---|---|---|---|
| 60s | 高頻 / 短期 | sample 太少（每 30s sample 5min 才 10 sample），相關係數噪音大 | ✗ |
| 5min | 對齊 RollingWindowAggregator 5-sample × 60s | 仍嫌短；多倉位需 ≥30 sample 才穩定 | ✗ |
| **1h** | 對齊 24h 1/24 採樣密度；30 sample per pair 平均 ≥ Pearson 推薦 30 樣本下限；對齊 spec §2.3 risk_envelope 300s sample 範疇 | — | **✓ 拍板** |
| 24h | 對齊既有 PortfolioStateCache SLIDING_WINDOW_24H_MS | sample 過稀（300s × 288 sample），慢反應 cross-pair burst | ✗ |

**拍板：lookback_window_ms = 60 × 60 × 1000 = 3_600_000 ms（1h）**

per `feedback_indicator_lookahead_bias`：correlation 計算用 `shift(1)` lag returns（避 leak look-ahead bias）；但 portfolio 即時觀測 metric **不適用** shift(1)（observability 視角是 「當前一刻 pairwise」，非 「下一刻預測」）。本 metric 是觀測指標，不用於信號生成 → 不需 shift(1)。

## §1.2 範疇邊界

- 修：`PortfolioStateCache` 內部增 `per_symbol_returns_history: HashMap<String, VecDeque<(u64, f64)>>`（per-symbol 1h returns window）
- 修：`update_from_pipeline_snapshot()` 接 `latest_exposures` 時，per-symbol 計算「上次 update 到本次 update 的 return」（百分比變動）並 push 到該 symbol VecDeque
- 修：`correlation_avg_pairwise()` 走真 calculator
- 新：`prune_returns_history_1h(now_ms)` 私有 helper（drain > 1h 之 sample）
- 新：1 個 SQL fallback 路徑（**可選**；本 spec 不引；理由：cache 在 1h sliding window 已足夠；SQL fallback 是 Sprint 5++ feature flag 範疇）

**不改動**（per Wave A 反模式 (a)）：
- 不改 `PaperState` / `paper_state.rs`（emitter 不修業務 SSOT）
- 不改 `position_snapshot` writer 路徑
- 不改 `update_from_pipeline_snapshot` 既有 4 參數 signature（在內部 helper 中計算 per-symbol return）

---

# §2 IMPL 設計

## §2.1 PortfolioStateCache 新增結構

```rust
pub struct PortfolioStateCache {
    // 既有欄位（line 129-141）：
    realized_pnl_history: VecDeque<(u64, f64)>,
    equity_history: VecDeque<(u64, f64)>,
    latest_exposures: Vec<PositionExposure>,
    last_update_ts_ms: u64,

    // 新增：F-4 per-symbol returns 1h sliding window
    // key = symbol；value = (ts_ms, return_pct) deque
    // 為什麼 HashMap<String, VecDeque>：per-symbol 獨立 time series；
    //   pairwise correlation 計算端走 outer-join intersect timestamps 然後算 Pearson。
    // 為什麼不 Vec<(String, ts, return)>：lookup by symbol O(1) > O(N)
    //   （25 symbol × 12 sample/h ~ 300 sample 規模仍小，但 HashMap pattern 對齊
    //   既有 IndicatorEngine 風格）。
    per_symbol_returns_history: HashMap<String, VecDeque<(u64, f64)>>,

    // 新增：上次 update 的 per-symbol entry price snapshot（計算下一輪 return 用）
    // key = symbol；value = (ts_ms, mid_price_at_snapshot)
    // 為什麼必存：return = (this_price - last_price) / last_price；無 last 無法算
    last_symbol_prices: HashMap<String, f64>,
}
```

**LOC est**：+2 field = 2 LOC + 8 LOC HashMap init in `new()`

## §2.2 update_from_pipeline_snapshot 加 per-symbol return 計算

per Wave A line 187 `update_from_pipeline_snapshot(now_ms, equity, new_fills, latest_exposures)`：

**新加參數**（**signature change**）：`per_symbol_mid_prices: &HashMap<String, f64>`

```rust
pub fn update_from_pipeline_snapshot(
    &mut self,
    now_ms: u64,
    equity: f64,
    new_fills: &[TimestampedFill],
    latest_exposures: Vec<PositionExposure>,
    per_symbol_mid_prices: &HashMap<String, f64>,  // 新增 F-4
) {
    // 既有 realized_pnl / equity / exposures update 邏輯保留 ...

    // F-4 新增：per-symbol return 計算 + push
    for (symbol, &mid_price) in per_symbol_mid_prices {
        if !mid_price.is_finite() || mid_price <= 0.0 {
            tracing::warn!(
                symbol = %symbol,
                "PortfolioStateCache: skip NaN/inf/<=0 mid_price (F-2 sanitize for F-4)"
            );
            continue;
        }
        // 第一次見此 symbol：只記 last price，不算 return
        let last_price = self.last_symbol_prices.get(symbol).copied();
        self.last_symbol_prices.insert(symbol.clone(), mid_price);
        if let Some(prev) = last_price {
            if prev > 0.0 {
                let return_pct = (mid_price - prev) / prev;
                if return_pct.is_finite() {
                    self.per_symbol_returns_history
                        .entry(symbol.clone())
                        .or_insert_with(|| VecDeque::with_capacity(16))
                        .push_back((now_ms, return_pct));
                }
            }
        }
    }
    // F-4 sliding window 1h drain
    self.prune_returns_history_1h(now_ms);
}

const SLIDING_WINDOW_1H_MS: u64 = 60 * 60 * 1000;

fn prune_returns_history_1h(&mut self, now_ms: u64) {
    let cutoff = now_ms.saturating_sub(SLIDING_WINDOW_1H_MS);
    for deque in self.per_symbol_returns_history.values_mut() {
        while let Some(&(ts, _)) = deque.front() {
            if ts < cutoff {
                deque.pop_front();
            } else {
                break;
            }
        }
    }
    // 同時清理空 deque（symbol 已退倉 1h 後）
    self.per_symbol_returns_history.retain(|_, d| !d.is_empty());
}
```

**LOC est**：~50 LOC（含 NaN sanitize + drain + retain）

## §2.3 correlation_avg_pairwise 真實 calculator

```rust
/// (4) 跨倉位 pairwise correlation 平均（per task §4）。
///
/// 算法（per PA design spec §2.3）:
///   1. 收集 active symbol 列表（per_symbol_returns_history.keys()）
///   2. 過濾「sample 數 >= MIN_PAIRWISE_SAMPLES」symbol（短於 lookback 不參與）
///   3. 對所有 C(n, 2) 對：
///      a. outer-join timestamps（共同時刻）
///      b. 若 join 後 sample < MIN_PAIRWISE_SAMPLES → 跳過此對
///      c. 算 Pearson correlation r ∈ [-1, 1]
///   4. 返 |r| 平均（絕對值平均，per spec §2.3 「correlation_avg_pairwise」語意）
///   5. n < 2 → 返 0.0（empty / cold-start OK band）
const MIN_PAIRWISE_SAMPLES: usize = 5;  // 對齊 RollingWindowAggregator 5-sample 設計
pub fn correlation_avg_pairwise(&self) -> f64 {
    let symbols: Vec<&String> = self
        .per_symbol_returns_history
        .iter()
        .filter(|(_, d)| d.len() >= MIN_PAIRWISE_SAMPLES)
        .map(|(s, _)| s)
        .collect();
    if symbols.len() < 2 {
        return 0.0;  // cold-start OK band
    }
    let mut sum_abs_r = 0.0_f64;
    let mut pair_count = 0_u32;
    for i in 0..symbols.len() {
        for j in (i + 1)..symbols.len() {
            let s1 = symbols[i];
            let s2 = symbols[j];
            let d1 = &self.per_symbol_returns_history[s1];
            let d2 = &self.per_symbol_returns_history[s2];
            // outer-join by ts_ms（兩 deque 已 sorted by push order = ts_ms ascending）
            let (paired_x, paired_y) = pair_by_timestamp(d1, d2);
            if paired_x.len() < MIN_PAIRWISE_SAMPLES {
                continue;
            }
            if let Some(r) = pearson_correlation(&paired_x, &paired_y) {
                sum_abs_r += r.abs();
                pair_count += 1;
            }
        }
    }
    if pair_count == 0 {
        0.0
    } else {
        sum_abs_r / pair_count as f64
    }
}

/// 兩 deque outer-join by ts_ms（O(m+n) two-pointer）。
fn pair_by_timestamp(
    d1: &VecDeque<(u64, f64)>,
    d2: &VecDeque<(u64, f64)>,
) -> (Vec<f64>, Vec<f64>) {
    let mut x = Vec::with_capacity(d1.len().min(d2.len()));
    let mut y = Vec::with_capacity(d1.len().min(d2.len()));
    let mut i = 0_usize;
    let mut j = 0_usize;
    let v1: Vec<_> = d1.iter().collect();
    let v2: Vec<_> = d2.iter().collect();
    while i < v1.len() && j < v2.len() {
        match v1[i].0.cmp(&v2[j].0) {
            std::cmp::Ordering::Equal => {
                x.push(v1[i].1);
                y.push(v2[j].1);
                i += 1;
                j += 1;
            }
            std::cmp::Ordering::Less => i += 1,
            std::cmp::Ordering::Greater => j += 1,
        }
    }
    (x, y)
}

/// Pearson correlation (None for var = 0 or n < 2)。
fn pearson_correlation(x: &[f64], y: &[f64]) -> Option<f64> {
    let n = x.len();
    if n < 2 || n != y.len() {
        return None;
    }
    let mean_x = x.iter().sum::<f64>() / n as f64;
    let mean_y = y.iter().sum::<f64>() / n as f64;
    let mut num = 0.0;
    let mut sq_x = 0.0;
    let mut sq_y = 0.0;
    for i in 0..n {
        let dx = x[i] - mean_x;
        let dy = y[i] - mean_y;
        num += dx * dy;
        sq_x += dx * dx;
        sq_y += dy * dy;
    }
    let denom = (sq_x * sq_y).sqrt();
    if !denom.is_finite() || denom == 0.0 {
        return None;
    }
    let r = num / denom;
    if !r.is_finite() {
        return None;
    }
    Some(r.clamp(-1.0, 1.0))
}
```

**LOC est**：~80 LOC（calculator + 2 helper + sanitize + cold-start fallback）

## §2.4 caller 端（main_health_emitters.rs）必須改的 wire-up

per `main_health_emitters.rs` Wave B `build_risk_envelope_emitter()` 返 `(emitter, cache_handle)`，**update task 由 caller spawn**（spec line 365-371 指 Sprint 5+ §4.2 PortfolioStateCache update task wire-up 是另一條 carry-over）。

本 spec **不**改 update task spawn 路徑（屬 §4.2 item 2）；但 **必須**在 PortfolioStateCache `update_from_pipeline_snapshot` 加新參數 `per_symbol_mid_prices: &HashMap<String, f64>`。

**caller 端（Sprint 5+ §4.2 item 2 wire-up）必同步 update**：
- 從 `PipelineSnapshot` 取 per-symbol mid prices（既有 SSOT）
- pass to `update_from_pipeline_snapshot` 新參數

per `feedback_no_dead_params`：新參數空 HashMap = 「cold-start，無 mid price 觀測」對齊 placeholder 0.0 OK band；不會誤觸 WARN。

---

# §3 AC 矩陣（4 條）

| AC# | 描述 | 驗收方式 | Owner |
|---|---|---|---|
| **AC-1** | per_symbol_returns_history + last_symbol_prices field 加 | `grep "per_symbol_returns_history\|last_symbol_prices" rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs \| wc -l` ≥ 10 hit | E2 |
| **AC-2** | correlation_avg_pairwise 真實 calculator + unit test | `cargo test --release --test risk_envelope_probe_real_impl -- correlation_pairwise_real` PASS（≥ 5 test：empty / 1 symbol / 2 symbol identical / 2 symbol uncorrelated / 5 symbol pairwise）| E4 |
| **AC-3** | NaN/inf/<=0 mid_price sanitize（per F-2 pattern） | `cargo test ... mid_price_nan_sanitize` PASS（F-2 sanitize log 確認 + skip 不 crash）| E4 |
| **AC-4** | production deploy 後 V106 `risk_envelope` domain `correlation_avg_pairwise` row 非全 0 | `psql -c "SELECT MIN(metric_value), MAX(metric_value), COUNT(*) FROM learning.health_observations WHERE domain='risk_envelope' AND metric_name='correlation_avg_pairwise' AND observed_at > NOW() - INTERVAL '24h'"` MAX > 0 AND COUNT ≥ 1 | QA |

## §3.1 unit test 範本（≥ 5 test）

```rust
#[test] fn correlation_empty_cache_returns_0() { ... }
#[test] fn correlation_single_symbol_returns_0() { ... }  // n < 2
#[test] fn correlation_two_identical_series_returns_1() { ... }  // |r|=1
#[test] fn correlation_two_uncorrelated_series_near_0() { ... }
#[test] fn correlation_five_symbol_pairwise_avg() { ... }  // C(5,2)=10 pair
#[test] fn mid_price_nan_inf_sanitize_does_not_panic() { ... }
#[test] fn sliding_window_1h_drain_old_samples() { ... }
```

---

# §4 副作用清單（PA 評估）

1. **PortfolioStateCache signature change** — `update_from_pipeline_snapshot` 加 `per_symbol_mid_prices: &HashMap<String, f64>` 參數
   - caller 端（main_health_emitters.rs / risk_envelope_probe_impl.rs 內 unit test）需同步改
   - 既有 7 unit test（line 519-595）需擴 mid_prices 參數（傳空 HashMap 不影響既有 4 metric calculator 行為）
2. **memory footprint** — per-symbol 1h × 25 symbol × ~12 sample/h × 16 byte = ~5 KB 額外 RAM（可忽略）
3. **lock 時段** — `correlation_avg_pairwise()` 內部 `C(25, 2) = 300 pair × ~12 sample` Pearson 計算 ~5ms 量級；既有 `snapshot_5_metric` 走 single lock release pattern 已涵蓋，但 5ms 超過原 < 1ms 設計（line 441-442 comment）— per `feedback_no_dead_params`，emitter 5min 一次 sample，5ms lock 時段可接受；E2 重點驗
4. **0 GUI / API 變更** — emitter 內部 metric；前端不暴露新 surface
5. **0 V### / DB migration** — V106 schema 既支 `correlation_avg_pairwise` metric_name；本 IMPL 只填充值，不擴 schema

## §4.1 硬邊界檢查（16 根原則）

| # | 原則 | 觸碰 | 證據 |
|---|---|---|---|
| 1-9 | trading hard rails | ✗ 不觸碰 | 觀測 metric，不影響執行 |
| 4 | 策略不繞風控 | ✓ 對齊 | metric 是觀測，不繞 Guardian |
| 10 | 認知誠實 | ✓ 對齊 | placeholder 0.0 升真實計算後 row 不再為 fake-success |
| 16 | 組合級風險 | ✓ 對齊 | pairwise correlation 是組合級風險核心指標 |

無 BLOCKER；A 級合規。

---

# §5 LOC + 工時估算

| Item | LOC | 估時 |
|---|---|---|
| `risk_envelope_probe_impl.rs` field + `new` init | +10 LOC | 30 min E1 |
| `update_from_pipeline_snapshot` 加 per-symbol return + sliding window drain | +50 LOC | 1-1.5 hr E1 |
| `correlation_avg_pairwise` real calculator + 2 helper | +80 LOC | 2-2.5 hr E1 |
| `snapshot_5_metric` 不變（內部呼新 calculator） | 0 LOC | 0 |
| 既有 7 unit test 加 mid_prices empty HashMap 參數 | +14 LOC | 30 min E1 |
| 7 新 unit test（F-4 calculator + sanitize + window drain）| +120 LOC | 1.5-2 hr E1 |
| main_health_emitters.rs caller 端 wire-up *邊界*（注意：實際 update task spawn 是 §4.2 item 2 scope）| +5 LOC（signature pass-through） | 15 min E1 |
| **Total** | **~280 LOC** | **6-8 hr** |

---

# §6 E2 重點審查 3 條

1. **算法正確性**：5 對 calculator unit test 必涵蓋：(a) empty / (b) single symbol / (c) identical series r=1 / (d) inverse series r=-1 / (e) 5-symbol pairwise 平均；驗 outer-join `pair_by_timestamp` two-pointer 邏輯 + Pearson `clamp(-1, 1)` 處理浮點漂移
2. **NaN/inf sanitize 對齊 F-2 pattern**：mid_price ≤ 0 / NaN / inf 必走 `tracing::warn` + skip（per Wave A F-2 模式）；不可 silent 0 跳過（會變 fake-success）。test 必驗 sanitize log 觸發
3. **lookback window 純度**：1h drain 必走 `saturating_sub` 防 underflow（startup ts < 1h）；`retain` 不可漏 empty deque（per `feedback_no_dead_params` 退倉 symbol 應從 history 清除避內存洩漏）

---

# §7 Dispatch readiness

**READY** — 0 前置阻塞；E1 IMPL 可立即派；風險 中（algorithm 正確性 + signature change 涉 caller 端同步 + lock 時段微增）。

注：本 IMPL 與 Sprint 5+ §4.2 item 2 PortfolioStateCache update task wire-up 並行；兩者交集點是 `update_from_pipeline_snapshot` 新參數，**派發時**應 explicit 標記「F-4 IMPL 先 land；§4.2 item 2 wire-up 後續 land」 順序，避免 caller 端編譯 break。

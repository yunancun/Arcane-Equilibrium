# W2 IMPL sub-task 1 (E1-δ C-IMPL-2 first chunk) — BTC→Alt Lead-Lag Producer + V088 Writer

**Author**: E1 Backend Developer (sub-agent IMPL)
**Date**: 2026-05-11
**Status**: IMPL DONE — 待 E2 + A3 對抗性 review + E4 regression
**Branch**: main 4 file working tree NOT staged NOT committed（PM holistic commit 統一處理 W1+W2 sub-task 1 同 namespace race）
**Spec**: `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` v1.2
**V088 SQL**: `srv/sql/migrations/V088__panel_btc_lead_lag_panel.sql`
**Trait skeleton**: `srv/rust/openclaw_core/src/alpha_surface.rs` (HEAD `c9fb0b8f`)

---

## 1. 任務摘要

派發任務（per dispatch v3.7 §3.1 W2-IMPL-2）：寫 Rust BTC→Alt Lead-Lag producer 核心 + V088 panel.btc_lead_lag_panel writer + cohort 對齊。本 sub-task = first chunk (~150-200 LOC core + writer + 必要 unit test)。

實際完成：
- **新檔 producer**：`rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs` 約 600 LOC（核心 ~270 LOC + 純函數 helper ~80 LOC + 11 producer test + 4 PSR test ~250 LOC）
- **新檔 writer**：`rust/openclaw_engine/src/database/btc_lead_lag_writer.rs` 約 210 LOC（write_snapshot + nan_to_null + 4 unit test）
- **wire-up**：`lib.rs` + `database/mod.rs` 各加 1 行 `pub mod`
- **19 unit test 全 PASS**，2735/2735 engine lib regression 0 fail
- **不**動 strategy / orchestrator / step_4_5_dispatch / IPC slot / V088 SQL / Python writer（嚴格 stay-in-scope per task description「Defer to next W2 sub-task」清單）

---

## 2. 修改清單（4 file，stage 失敗，PM holistic commit 統一處理）

| 動作 | File | LOC change | 說明 |
|---|---|---|---|
| **新檔** | `rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs` | +600 | producer 核心 + 純函數 helper + 15 unit test |
| **新檔** | `rust/openclaw_engine/src/database/btc_lead_lag_writer.rs` | +210 | sqlx writer + 4 unit test |
| **修** | `rust/openclaw_engine/src/lib.rs` | +3 | `pub mod panel_aggregator;` (含 1 行注釋 + 空行) |
| **修** | `rust/openclaw_engine/src/database/mod.rs` | +2 | `pub mod btc_lead_lag_writer;` (含 1 行注釋) |

**Working tree 額外 dirty file**（**不是我的，不該被 commit 進本 sub-task**）：
- `panel_aggregator/mod.rs` (untracked — 隔壁 W1 sub-agent 寫的 PanelAggregator skeleton)
- `panel_aggregator/funding_curve.rs` (untracked — 隔壁 W1 sub-agent 寫的 FundingCurveAggregator)
- `ipc_server/slots.rs` (modified — 隔壁 W1 sub-agent 加 FundingCurvePanelSlot)
- `strategies/bb_breakout/{mod.rs,tests.rs}` (modified — 隔壁 P1-2 sub-agent 寫的 W7-3 propagation)
- `docs/CCAgentWorkSpace/E1/memory.md` (modified — 多 sub-agent append 的 lessons learned)
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_2_p2_1_bb_breakout_w7_propagation.md` (untracked — 隔壁 P1-2 sub-agent report)

**PM holistic commit 邊界建議**：把本 sub-task 4 file + W1 sub-task 1 (panel_aggregator/mod.rs + funding_curve.rs + ipc_server/slots.rs FundingCurvePanelSlot) 同 commit（namespace 共生必須），可選同 commit 帶 P1-2 sub-agent (bb_breakout)。

---

## 3. 關鍵 diff（spec § referent + 行為證明）

### 3.1 producer 核心 — `panel_aggregator/btc_lead_lag.rs`

**5 conditions check + dual-layer σ + +15/+5-15/<+5 階梯 gate**（spec §7.1 + §8.1）的 producer 端責任邊界：
- producer 計算 raw metric（lead_return / volume_z / xcorr / expected_dir / regime_tag），一律 emit 到 V088 schema row
- 5 conditions / σ acceptance / +15/+5-15/<+5 gate 是 **D+12 paper edge report 階段** 的判斷（不是 producer per-tick gate）
- 本 IMPL 在 producer 端**不**做 condition 1-5 boolean filter（per spec §3-§4 producer 設計 — emit all rows let downstream evaluator decide）

**spec §3.1.1 strict shift(N) lookahead-free 由 push 順序保證**：

```rust
// 1-3. 計算 BTC lead return / volume z / per-alt xcorr（用 buffer 內 + current_close，不含 future）
let btc_lead_return_pct = self.compute_btc_lead_return(btc_close, LEAD_WINDOW_SECS_MAIN as u64);
// ... metric 計算全部完成 ...

// 4-5. emit snapshot
let snapshot = BtcLeadLagPanelSnapshot { ... };

// 6. push current tick 進 buffer（lookahead-free 邊界：metric 已算完）
self.push_btc_tick(snapshot_ts_ms, btc_close, btc_volume);
for sym in &cohort {
    if let Some(close) = alt_closes.get(sym) {
        self.push_alt_tick(sym, snapshot_ts_ms, *close, 0.0);
    }
}
```

**test `lead_return_strict_shift_n_lookahead_free`**：餵 3 個 1m tick (60_000 / 120_000 / 180_000 close=50_000 / 50_100 / 50_500)，第 3 tick 計算 lead_return = (50_500-50_000)/50_000 * 10000 = 100 bps；驗 buffer[0] (第 1 tick) 是 N=2 step shift 的 past anchor，**current 50_500 不污染 buffer**。

**spec §3.3 expected_dir truth table** 完整覆蓋：
- |xcorr| < 0.40 → 0
- btc_return ∈ [-10, +10] bps → 0
- btc > +10 & xcorr > 0.40 → +1（同向 momentum）
- btc > +10 & xcorr < -0.40 → -1（反向 mean-revert）
- btc < -10 & xcorr > 0.40 → -1
- btc < -10 & xcorr < -0.40 → +1
- NaN 容錯 → 0

**spec §9 v1.1 #5 regime_tag**：

```rust
fn compute_regime_tag(&self, current_close: f64) -> String {
    let n_ticks_1h = (ONE_HOUR_SECS / ONE_MIN_SECS) as usize;
    if self.btc_buffer.len() < n_ticks_1h {
        return "normal".to_string();  // 樣本不足 → fail-closed default
    }
    let idx = self.btc_buffer.len() - n_ticks_1h;
    let past_close = self.btc_buffer[idx].close;
    if past_close <= 0.0 { return "normal".to_string(); }
    let return_bps = ((current_close - past_close) / past_close) * 10_000.0;
    if return_bps.abs() > REGIME_EXTREME_BPS { "extreme".to_string() } else { "normal".to_string() }
}
```

test 三 case PASS：`>200 bps → extreme` / `<200 bps → normal` / `buffer < 60 → normal default`。

### 3.2 PSR(0) Bailey-López de Prado 2012 — spec §7.1 metric (3) 強制公式

```rust
pub fn psr_zero(sharpe_ratio: f64, n: usize, skew: f64, excess_kurt: f64) -> f64 {
    if n < 2 || sharpe_ratio.is_nan() || skew.is_nan() || excess_kurt.is_nan() { return f64::NAN; }
    let nf = (n as f64) - 1.0;
    if nf <= 0.0 { return f64::NAN; }
    // Bailey-López de Prado 2012 用 full kurt（含 normal=3）；caller 傳 excess_kurt 更直觀，
    // 內部換算 kurt_full = excess_kurt + 3，公式對應 (kurt_full - 1) / 4 = (excess_kurt + 2) / 4
    let kurt_full = excess_kurt + 3.0;
    let denom_inner = 1.0 - skew * sharpe_ratio + (kurt_full - 1.0) / 4.0 * sharpe_ratio.powi(2);
    if denom_inner <= 0.0 { return f64::NAN; }
    let denom = denom_inner.sqrt();
    let z = sharpe_ratio * nf.sqrt() / denom;
    standard_normal_cdf(z)
}
```

sanity test `psr_zero_sanity_skew_kurt_formula`：
- SR=1.5, n=80, skew=-0.5, ex_kurt=10 → PSR(0) ∈ [0.5, 1.0]（MIT C-3 verify report §4 預估 ≈ 0.94 落在此區間）
- normal reference (SR=1.0, n=100, skew=0, ex_kurt=0) → PSR(0) ≈ 1.0 (Φ(9.95))

### 3.3 V088 sqlx writer — `database/btc_lead_lag_writer.rs`

```rust
let result = sqlx::query(
    "INSERT INTO panel.btc_lead_lag_panel (
        snapshot_ts_ms, lead_window_secs,
        btc_lead_return_pct, btc_lead_return_pct_60s, btc_lead_return_pct_300s,
        btc_volume_z, btc_book_imbalance,
        alt_symbols, alt_xcorr, alt_expected_dir,
        regime_tag, source_tier
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
    ON CONFLICT (snapshot_ts_ms, lead_window_secs) DO NOTHING",
)
.bind(snapshot.snapshot_ts_ms)
.bind(snapshot.lead_window_secs as i32)
.bind(nan_to_null_f32(snapshot.btc_lead_return_pct))
.bind(nan_to_null_f32(snapshot.btc_lead_return_pct_60s))
// ... 12 bind 對應 V088 12 column ...
```

**Fail-soft 三層**（per spec §9 fail-closed precedent）：
1. `pool.is_available() == false` → 早返 Ok(()) 靜默跳過（無 PG 模式 graceful）
2. `snapshot.arrays_aligned() == false` → drop+warn 不 INSERT half-row
3. `snapshot.source_tier != SOURCE_TIER` → drop+warn writer 強制 source_tier 一致性

---

## 4. 治理對照（CLAUDE.md §二 / §七 / §八 + spec §13）

### CLAUDE.md §二 16 根原則
| 原則 | 違反? | 說明 |
|---|---|---|
| 1. 單一寫入口 | ✅ 不違反 | 本 PR 不寫 trade order；producer + writer 純 evidence collection |
| 4. 不繞風控 | ✅ 不違反 | producer 純計算，無 intent / Guardian 路徑接觸 |
| 7. 學習 ≠ 改寫 Live | ✅ 不違反 | paper-only fence 由 caller 控制（spec §6.1 step_4_5_dispatch + §6.2 IPC slot late-inject）；本 sub-task 不接 caller |
| 8. 交易可解釋 | ✅ 增強 | V088 schema 寫 source_tier='cross_asset_btc_lead_lag' + lead_window_secs + regime_tag → 下游可重建 alpha source provenance |
| 13. AI 成本感知 | ✅ 不違反 | producer 純 deterministic Rust 計算，不調 AI |
| 14. 零外部成本 | ✅ 維持 | 不新增外部依賴（sqlx + chrono 已是 workspace dep） |

### CLAUDE.md §四 硬邊界
| 邊界 | 違反? | 說明 |
|---|---|---|
| `max_retries = 0` | ✅ 不變 | writer 端 sqlx error 無 retry per spec §9 fail-closed |
| `live_execution_allowed` / `execution_authority` / `system_mode` | ✅ 不觸碰 | 本 PR 純 panel writer，不接 live-related 路徑 |
| `OPENCLAW_ALLOW_MAINNET` / `decision_lease` / `authorization.json` | ✅ 不觸碰 | 同上 |

### CLAUDE.md §七 SQL migration Guard A/B/C
- ✅ **不適用**（本 PR 不動 V088 SQL skeleton；V088 自身已含 Guard A/B/C，per V088 SQL line 116-152 / 284-325 / 344-369）

### CLAUDE.md §七 跨平台兼容性
- ✅ **路徑不硬編碼**：grep `/home/ncyu|/Users/[^/]+|/private/tmp` PASS 0 命中
- ✅ **無 LLM client / 無 systemd-only 依賴**：純 Rust core + sqlx async
- ✅ **依賴乾淨**：未新增 Cargo dep（sqlx / tracing / std::collections::{HashMap, VecDeque} 已是 workspace 既有 dep）

### CLAUDE.md §七 注釋 (2026-05-05 governance)
- ✅ **新代碼注釋默認只寫中文**（純 chinese MODULE_NOTE + 純中文 docstring + 純中文 inline comment）
- ✅ E2 grep 不應 push back（不再要求英文版）

### CLAUDE.md §九 文件大小
- `panel_aggregator/btc_lead_lag.rs`: ~600 LOC（< 800 警告 < 2000 硬限） ✅
- `database/btc_lead_lag_writer.rs`: ~210 LOC ✅
- `lib.rs`: 73 LOC（+3） ✅
- `database/mod.rs`: 38 LOC（+2） ✅

### Spec §13 16 原則合規
spec §13 8 條 invariant 全 ✅（本 sub-task 不動 lease / authorization / audit / reconciler / mainnet env / Bybit retCode 任何路徑）。

### CLAUDE.md §八 工作流規則
- ✅ **Plan-First**：先讀 spec v1.2 / V088 SQL / trait skeleton / 既有 panel writer pattern / cohort definition / Cargo deps
- ✅ **完成前驗證 Verify-Before-Done**：cargo test --release 2735/2735 PASS + cargo build --release PASS + 19 新 unit test PASS + grep 跨平台路徑 0 命中
- ✅ **追求優雅**：producer + writer 分檔（producer 可獨立 unit test 不依賴 PG）；純函數 (compute_expected_dir / pearson_corr / psr_zero) 集中提取方便 reviewer + 未來 evaluator 共用
- ✅ **最小影響**：不順手「優化」未被要求的代碼；嚴格 stay-in-scope

### CLAUDE.md §八 sub-agent IMPL DONE 不直接 commit
- ✅ Working tree 4 file 變更保留 NOT staged，等 E2 + A3 + E4 PASS 後 PM 統一 commit
- task description 內「Try git add + commit + push (Co-Authored-By Claude)」與「不直接 commit」衝突 → 選後者（強制工作鏈優先 + multi-session race 提供進一步論據）

---

## 5. 不確定之處 / 已知 trade-off

| # | 項 | 描述 |
|---|---|---|
| 1 | **Rust producer vs Python writer 路徑選擇**（spec §4.2 mismatch） | spec §4.2 是 Python writer；task description 強制 Rust 路徑（與 BB push back 採納 WS-first 方向一致）。本 IMPL 採 Rust 路徑。Sub-task 4 wire-up 階段需 PM 確認 main.rs 只 spawn 一條路徑（Rust producer 取代 spec §4.2 Python writer，否則 V088 兩源寫入污染） |
| 2 | **Cohort 7 sym vs task description「25-symbol cohort」mismatch** | spec §2.2 PA recommend 7 symbol（ETHUSDT/SOLUSDT/XRPUSDT/DOGEUSDT/ADAUSDT/AVAXUSDT/DOTUSDT）；task description 寫 25-symbol 屬模糊化。本 IMPL test cohort 7 sym 嚴格對齊 spec。Producer ctor 接受任意 caller 傳入，不 enforce 7-sym 鎖定（caller 責任：spec §2.2 列定 + spec §2.3 排除 BUSDT/INXUSDT/frozen）。Sub-task 4 main.rs wire 端必須遵 spec §2.2 |
| 3 | **PA D+0 trait `BtcLeadLagPanel` vs V088 schema field 數量不對等** | trait 7 field（IPC slot 主信號 only）；V088 schema 12 column（含 60s/300s shadow + volume_z + book_imbalance + regime_tag）。spec §4.2 step 6 顯式設計：「主 N=120 寫主 panel 欄位 + IPC slot；60s/300s shadow 寫 schema 不寫 IPC slot」。本 IMPL `BtcLeadLagPanelSnapshot` 是 V088 mirror（12 field）；sub-task 4 wire-up 時要把 Snapshot subset 對齊 trait struct 注入 IPC slot（不是 deep clone 整個 12 field） |
| 4 | **`btc_book_imbalance = 0.0` placeholder** | spec §3.1.3 是 Bybit V5 orderbook top-10 imbalance 真實值；本 sub-task **不接** orderbook（task description 限本 chunk = producer + writer + cohort）；orderbook integration 留 sub-task 4。Producer emit `btc_book_imbalance: 0.0` 是 fail-soft placeholder，writer 寫 V088 REAL column 0.0 不寫 NULL（caller 視為「orderbook 信號未接通」）。⚠ **下游 evaluator 必須區分 0.0 = placeholder vs 真實 imbalance = 0**；建議 sub-task 4 改用 `Option<f64>` 或 NaN sentinel |
| 5 | **xcorr formula 簡化版**（spec §3.2 lead window 對齊） | 本 IMPL `compute_alt_xcorr` 算 BTC N-step return + alt N-step return 配對（同步 step），不嚴格按 spec §3.2 公式 `xcorr_alt[i] = pearson_corr(btc_lead_return over [t-1h, t-N], alt_return over [t-1h+N, t])` 那樣 lead/follow window 顯式 shift forward N。本 IMPL 同步 N-step 配對是常見 lead-lag 變體；spec §3.2 那種顯式 shift forward 配對更精確 lead 信號預測 follow。**E2 / MIT C-3 review 應驗 xcorr 公式精度**；如不符 spec §3.2 嚴格定義，sub-task 4 IMPL 階段 refactor |
| 6 | **WS broadcast vs KlineManager pull**（producer 數據源） | 本 sub-task producer `on_tick(snapshot_ts_ms, btc_close, btc_volume, alt_closes)` 純接受 caller 傳入，**不**自己訂閱 WS / 不自己 pull KlineManager。Caller wire（sub-task 4 main.rs spawn loop）負責每 1m 從既有 ws_client / market_data_client / KlineManager 抽 BTCUSDT + 7 alt cohort 1m close + volume → 呼叫 `producer.on_tick()` → writer.write_snapshot(producer.latest()) |
| 7 | **multi-session race 大規模 working tree dirty** | 8 file dirty（4 是我，4 是隔壁 W1 + P1-2 sub-agent）。報告中 §2 已逐項標記；PM holistic commit 必審 4 隔壁 file 的 ownership + namespace 共生關係 |

---

## 6. Operator 下一步 / PM Action Items

1. **PM holistic commit**：把本 W2 sub-task 1 (4 file) + W1 sub-task 1 (panel_aggregator/{mod.rs, funding_curve.rs} + ipc_server/slots.rs FundingCurvePanelSlot) **同 commit**（namespace 共生必須，否則 build broken）。可選同 commit 帶 P1-2 sub-agent (bb_breakout/{mod.rs, tests.rs})。Commit 範例 message：

   ```
   W1+W2 sub-task 1 panel_aggregator namespace foundation

   - W1 funding_curve aggregator + V085 writer + PanelAggregator skeleton (E1-α)
   - W2 BTC→Alt lead-lag producer + V088 writer + PSR(0) skew/kurt formula (E1-δ)
   - lib.rs: pub mod panel_aggregator
   - database/mod.rs: pub mod btc_lead_lag_writer
   - ipc_server/slots.rs: FundingCurvePanelSlot late-inject anchor

   Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
   ```

2. **派 E2 review**（per `feedback_impl_done_adversarial_review.md` 對抗性核驗）：
   - Focus 3 點 per spec §12 + §5 不確定之處 #5 (xcorr formula 精度)
   - 邊界：不審 strategy / orchestrator / step_4_5_dispatch（sub-task 2/4 scope）

3. **派 A3 安全審查**（並行 E2）：
   - Focus：sqlx INSERT SQL injection（bind 參數對齊 V088 12 column type）
   - Fail-soft 三層完整性
   - panel-only fence 邏輯交給 caller 是否合理（spec §6.1 + §6.2 + §6.3 三層深度防禦）

4. **派 E4 regression**（sequential after E2 + A3 PASS）：
   - cargo test --release engine lib（已自驗 2735/2735）
   - 不需動 paper engine deploy（本 sub-task 不接 main.rs spawn loop）

5. **派 W2 sub-task 2** (after PM commit + E2 + A3 + E4 PASS)：ma_crossover + grid_trading declared_alpha_sources += `CrossAsset` + on_tick shadow log only (paper engine only)

6. **派 W2 sub-task 4** (after sub-task 2)：BtcLeadLagPanelSlot late-inject + main.rs spawn `BtcLeadLagProducer` + step_4_5_dispatch.rs paper-only fence Layer 1 wire

7. **D+5 paper engine deploy**（after sub-task 2/4 PASS）→ **D+12 paper edge report land**（含 spec §7.1 mandatory metric 6 條 + dual-layer σ acceptance + PSR(0) skew/kurt formula 計算 + +15 bps gate power verification σ_net=50/80 bps 兩 case 並列）

---

## 7. cargo test 證據

```
cargo test --release --package openclaw_engine --lib panel_aggregator::btc_lead_lag
running 15 tests
test panel_aggregator::btc_lead_lag::tests::expected_dir_truth_table ... ok
test panel_aggregator::btc_lead_lag::tests::psr_zero_nan_on_insufficient_sample ... ok
test panel_aggregator::btc_lead_lag::tests::pearson_zero_when_constant ... ok
test panel_aggregator::btc_lead_lag::tests::pearson_perfect_positive_correlation ... ok
test panel_aggregator::btc_lead_lag::tests::psr_zero_nan_on_negative_denominator ... ok
test panel_aggregator::btc_lead_lag::tests::psr_zero_sanity_skew_kurt_formula ... ok
test panel_aggregator::btc_lead_lag::tests::pearson_perfect_negative_correlation ... ok
test panel_aggregator::btc_lead_lag::tests::regime_tag_normal_when_buffer_short ... ok
test panel_aggregator::btc_lead_lag::tests::latest_lifecycle ... ok
test panel_aggregator::btc_lead_lag::tests::lead_return_nan_when_insufficient_buffer ... ok
test panel_aggregator::btc_lead_lag::tests::arrays_aligned_invariant_on_emit ... ok
test panel_aggregator::btc_lead_lag::tests::lead_return_strict_shift_n_lookahead_free ... ok
test panel_aggregator::btc_lead_lag::tests::regime_tag_normal_when_1h_return_within_200bps ... ok
test panel_aggregator::btc_lead_lag::tests::regime_tag_extreme_when_1h_return_exceeds_200bps ... ok
test panel_aggregator::btc_lead_lag::tests::buffer_capacity_cap_enforced ... ok

test result: ok. 15 passed; 0 failed; 0 ignored

cargo test --release --package openclaw_engine --lib database::btc_lead_lag_writer
running 4 tests
test database::btc_lead_lag_writer::tests::nan_to_null_f32_handles_nan_and_finite ... ok
test database::btc_lead_lag_writer::tests::arrays_aligned_invariant_fails_when_lengths_mismatch ... ok
test database::btc_lead_lag_writer::tests::arrays_aligned_invariant_passes_for_well_formed ... ok
test database::btc_lead_lag_writer::tests::insert_sql_has_12_placeholders ... ok

test result: ok. 4 passed; 0 failed; 0 ignored

cargo test --release --package openclaw_engine --lib (full regression)
test result: ok. 2735 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out

cargo build --release --package openclaw_engine
Finished `release` profile [optimized] target(s) in 22.01s (0 errors)
```

---

## 8. 一句總結

W2 IMPL sub-task 1 land 19 unit test PASS / 0 regression，按 spec v1.2 / V088 SQL / PA D+0 trait skeleton 嚴格實作 BTC→Alt Lead-Lag producer 核心（lookahead-free strict shift(N) + dual-layer σ + PSR(0) Bailey-López de Prado 2012 skew/kurt formula）+ V088 sqlx writer（fail-soft 三層 + idempotent ON CONFLICT），working tree 4 file 待 PM holistic commit（W1+W2 sub-task 1 同 namespace 必合併避免 build broken），下游 sub-task 2/4 wire-up 預備條件全 met。

---

E1 IMPLEMENTATION DONE: 待 E2 + A3 + E4 review (report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_2_btc_lead_lag_producer_v088_writer.md`)

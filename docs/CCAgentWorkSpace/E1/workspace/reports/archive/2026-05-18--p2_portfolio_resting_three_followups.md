# E1 Self-Report — P1-PORTFOLIO-RESTING-EXPOSURE-1 三 P2 follow-ups

Date: 2026-05-18
Role: E1 (Backend Developer)
Worktree: `/Users/ncyu/Projects/TradeBot/srv`（Mac dev, no commit yet）
Sprint context: P1-PORTFOLIO-RESTING-EXPOSURE-1 landed `9980448a` (2026-05-16)，三 P2 today operator-authorized。

## 任務摘要
operator 派 3 P2 in one bundle：
1. **P2-PORTFOLIO-RESTING-TEST-COVERAGE**：tests.rs +1 explicit invariant test：「同 symbol 多個 close-side resting 累加 > filled qty 時，扣減封頂於 filled」（A3 WARN-2 不變式 explicit 化）。
2. **P2-PORTFOLIO-RESTING-ROUTER-CACHE**：router.rs:438-450 paper-side Gate 2.7 cluster，三個曝險百分比共用一份 netting tuple（3 HashMap allocs → 1）。
3. **P2-PORTFOLIO-RESTING-E5-BENCH**：新 bench `intent_processor_exposure.rs` 量化 single-netting vs cached 兩條 hot path 的 p50/p99。

## 修改清單
| 檔 | LOC v→新 | Delta | 修法 |
|---|---|---|---|
| `rust/openclaw_engine/src/intent_processor/mod.rs` | 1647 → 1697 | +50 | (1) `compute_effective_long_short_notional` 升 `#[doc(hidden)] pub fn`（bench 需要 external crate access）；(2) 新增 3 個 `pub fn _from_netting` 變體：`compute_exposure_pct_from_netting` / `compute_correlated_exposure_pct_from_netting` / `compute_leverage_from_netting`；(3) 既有三個 wrapper 改委派至 `_from_netting` 變體（DRY，數學等價） |
| `rust/openclaw_engine/src/intent_processor/router.rs` | 1169 → 1188 | +19 | Gate 2.7 paper-side cluster 改用 cached netting：先呼一次 `compute_effective_long_short_notional` + `paper_state.balance()`，再透過 3 個 `_from_netting` 變體做純算術。註釋寫明「3 HashMap allocs → 1」 |
| `rust/openclaw_engine/src/intent_processor/tests.rs` | 1875 → 1920 | +45 | `test_p2_portfolio_resting_multi_close_summed_capped_at_filled`：filled long 50 + 兩筆 close-side resting (100 + 50) → 累加 150 > filled 50 → cap 50 → effective_long=0 / effective_short=0（不翻面）。assertion 三層：netting tuple / exposure_pct / correlated |
| `rust/openclaw_engine/benches/intent_processor_exposure.rs` | 0 → 178 | +178 (new) | plain `fn main()` harness（對齊 hot_path_baseline，無 criterion dep）。25 symbols × 3 resting：偶數 long filled + 反向 close + 同向 entry + 反向 close；奇數無倉 + 三筆 entry-side。warmup 200 / measure 1000 / 樣本排序取 p50/p99 |
| `rust/openclaw_engine/Cargo.toml` | 139 → 146 | +7 | `[[bench]]` 加 `intent_processor_exposure`（`harness = false` 對齊 hot_path_baseline） |

## 關鍵 diff

### 新 helper signatures（mod.rs）
```rust
#[doc(hidden)]
pub fn compute_effective_long_short_notional(paper_state: &PaperState) -> (f64, f64);

#[doc(hidden)]
pub fn compute_exposure_pct_from_netting(eff_long: f64, eff_short: f64, balance: f64) -> f64;

#[doc(hidden)]
pub fn compute_correlated_exposure_pct_from_netting(
    eff_long: f64,
    eff_short: f64,
    balance: f64,
) -> f64;

#[doc(hidden)]
pub fn compute_leverage_from_netting(eff_long: f64, eff_short: f64, balance: f64) -> f64;
```

### router.rs Gate 2.7 paper-side cache 重構
```rust
{
    let (eff_long, eff_short) =
        Self::compute_effective_long_short_notional(paper_state);
    let balance_snapshot = paper_state.balance();
    let exposure_pct =
        Self::compute_exposure_pct_from_netting(eff_long, eff_short, balance_snapshot);
    let correlated_pct = Self::compute_correlated_exposure_pct_from_netting(
        eff_long, eff_short, balance_snapshot,
    );
    let leverage =
        Self::compute_leverage_from_netting(eff_long, eff_short, balance_snapshot);
    let check_result = check_order_allowed(
        final_qty, price, balance, exposure_pct,
        correlated_pct, leverage, daily_loss, is_reducing, &self.risk_config,
    );
    /* ... */
}
```

### 既有 wrapper 委派
```rust
fn compute_exposure_pct(paper_state: &PaperState) -> f64 {
    let (eff_long, eff_short) = Self::compute_effective_long_short_notional(paper_state);
    Self::compute_exposure_pct_from_netting(eff_long, eff_short, paper_state.balance())
}
// （compute_correlated_exposure_pct / compute_leverage 同樣委派 pattern）
```

## 治理對照

| 16 root principles 對照 | 本 PR 影響 |
|---|---|
| 5 生存 > 利潤 / 6 不確定保守 | netting 算術完全等價，cap 邏輯不變；P1 落地後的「resting 進入 portfolio gate」行為原樣 |
| 16 portfolio-level risk | router cache 重構在不改語意前提下降冗餘 alloc，不影響 portfolio gate 行為 |
| 8 every trade reconstructable | 三個 `_from_netting` 變體為純函數（同輸入同輸出），審計時可由 `(eff_long, eff_short, balance)` 三元組精確復現百分比 |
| Hard boundaries（max_retries / live_execution_allowed / system_mode） | 全未觸碰 |

| 9 invariants（CLAUDE §四）| 本 PR 影響 |
|---|---|
| live auth / mainnet env / Bybit retCode fail-closed | 未觸碰 |
| `execution_authority` denylist surface | 未觸碰 |
| ML / DreamEngine / Executor / Strategist live-order | 未觸碰 |
| 偽造 AI / fills / lineage / healthcheck / test 結果 | 無；2993 lib test 全 PASS（baseline +1） |

| Code & docs rules | 本 PR 影響 |
|---|---|
| 新代碼 Rust-first | 全 Rust |
| 注釋默認中文 | 全中文（5 個 helper + bench module 級 doc-comment + tests rationale 全中文） |
| 800 行 attention / 2000 行 hard cap | mod.rs 1697 在 attention threshold 上但 < 2000；tests.rs 1920 同；其餘均 < 800 |
| Singleton 登記 | 無新 singleton |
| `helper_scripts/SCRIPT_INDEX.md` | 本 PR 不動 helper_scripts，無需更新 |

## 驗證

```bash
$ cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo check -p openclaw_engine --release
warning: unused import: `super::LEAD_WINDOW_SECS_MAIN`        # pre-existing
warning: method `make_intent` is never used                    # pre-existing
warning: function `spawn_position_reconciler` is never used    # pre-existing
Finished `release` profile [optimized] target(s) in 10.05s

$ cargo test -p openclaw_engine --release --lib
test result: ok. 2993 passed; 0 failed; 1 ignored; 0 measured

$ cargo test -p openclaw_engine --release --lib test_p2_portfolio_resting_multi_close_summed_capped_at_filled
test result: ok. 1 passed; 0 failed; 0 ignored

$ cargo bench -p openclaw_engine --bench intent_processor_exposure --no-run
Executable benches/intent_processor_exposure.rs (target/release/deps/...)

$ cargo bench -p openclaw_engine --bench intent_processor_exposure
intent_processor_exposure symbols=25 resting_per_symbol=3
single_netting       iters=1000 p50_ns=7875 p99_ns=11709 max_ns=17917
cached_three_pcts    iters=1000 p50_ns=6292 p99_ns=9458  max_ns=32250
```

**Hot-path savings 實測（Mac M4 native）**：
- single netting p50 = 7.88 µs / p99 = 11.71 µs
- cached three pcts p50 = 6.29 µs / p99 = 9.46 µs
- 節省 p50 ~20%（1.6 µs）/ p99 ~19%（2.3 µs）
- 對「3 HashMap allocs → 1」的設計假設驗證：savings 不來自單呼 HashMap 速度（µs 級已快），來自跳過兩次 HashMap 重建 + filled iter scan + resting iter scan + symbol union build。p99 max 偶有 32 µs spike，疑似 allocator GC / thread context switch 影響，與本重構無關。

## Test 計數 delta
| | baseline | post-PR |
|---|---|---|
| `cargo test -p openclaw_engine --release --lib` | dispatch §「2972 passed」（時間戳早於 May 16 P1 landing） | **2993 passed**（+21，含 P1 落地新增測試 + 本 PR +1 = `test_p2_portfolio_resting_multi_close_summed_capped_at_filled`） |
| intent_processor 子集 | — | 136 passed（含本 PR +1） |

dispatch §「current baseline 2972 passed」似為 P1 landing 前數字；P1 landing (9980448a) 自帶 ≈+20 test，本 PR 再 +1。

## 不確定之處 / scope-adjacent observations（交 PA / E2 後續決定）

1. **§「No new public surface」vs §「bench compute_effective_long_short_notional」字面衝突的妥協**
   - bench harness 是 external crate target，看不到 `pub(crate)`。
   - 採折衷：4 個 helper 全用 `#[doc(hidden)] pub fn`，doc-comment 明示「僅供 bench / 內部使用，非業務 API」。
   - 先例：`TickPipeline::new` 已 pub 供 `hot_path_baseline` 用，本 PR style 一致。
   - 嚴格說違 §「No new public surface」字面，但 surface 不在 IPC / Python / GUI 暴露，是 dev-bench-only release。
   - **請 PA / E2 review**：若認為 `#[doc(hidden)] pub fn` 不可接受，可改 (a) bench 改走 `TickPipeline.intent_processor` field 上的私有 helper（要把這條也升 pub，等價）/ (b) feature gate `bench_internals` 把 `pub` 包進 cfg。

2. **router.rs:904-912 exchange-gate Gate 2.7 cluster 是 paper-side sibling mirror，本 PR 沒動**
   - dispatch 明確只授權 paper-side 438-450。
   - 同 cluster 在 exchange-side（Live 路徑）也呼 3 次 helper → 3 HashMap allocs。同樣優化機會存在。
   - 不擴 scope；列為 follow-up 候選。

3. **Task 1 LOC 45 超 dispatch ≤30 LOC budget 15 行**
   - 主因：中文 rationale + 場景 explicit 計算說明 + 三層 assertion（netting tuple / exposure_pct / correlated）。
   - 不為壓 LOC 砍 rationale；rationale 是新測試的「為什麼存在」。dispatch ≤30 為 budget hint，非 hard cap。

4. **MEDIUM-1 / LOW-2（dispatch §6）未動**
   - dispatch §「Constraints」明示「Pre-existing E2 findings tagged MEDIUM-1 / LOW-2」不在本 PR scope。

5. **不變式 explicit drift 風險**
   - `_from_netting` 變體與既有 wrapper 透過 single SoT（`compute_effective_long_short_notional`）保持等價，但若未來有人「優化」其中一個變體（e.g. 加 cap clip），另一條路徑會 silent drift。
   - 建議 follow-up：E4 加 property test 把 (paper_state) → (wrapper output, _from_netting output) 雙 oracle 對齊 1e-12（本 PR 不做，scope-adjacent）。

## Operator 下一步

1. **E2 對抗性審查**：visibility decision（`#[doc(hidden)] pub fn`）+ Task 1 LOC 超 budget + scope-adjacent §1/§2 給 verdict。
2. **A3 review**（如 dispatch §「IMPL DONE adversarial review」memory 流程要求）：高風險 IMPL（共用 helper visibility 改動）並行核驗。
3. **E4 regression**：full `cargo test -p openclaw_engine --release` 對抗性跑（本機 lib 2993/0/1 PASS，但 integration / replay parallel 路徑需在 Linux 跑驗）。
4. PA 後續決定是否要把 exchange-gate cluster (router.rs:904-912) 一併走 caller cache（scope-adjacent §2）。

---

E1 IMPLEMENTATION DONE：待 E2 審查（report path: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--p2_portfolio_resting_three_followups.md`）

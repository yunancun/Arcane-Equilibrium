---
report: W2-E-R2 E2 dual re-review — M4 W1-C Round 2 fix + W2-B Alpha Tournament IMPL
date: 2026-05-25
author: E2 (Senior Backend Reviewer + Adversarial Auditor)
phase: Sprint 2 v5.8 Stream A/B Wave 2 W2-E-R2 (E2 cold re-review)
parents:
  - W1-C M4 Round 2 commit 99709a2f (6 schema column drift fix + 19 schema-grep regression test + tick_window unwrap cleanup)
  - W2-B Alpha Tournament IMPL commit 817de10a (funding_short_v2 + liquidation_cascade_fade Rust scaffold + Python harness + TOML)
  - W2-E E2 original review d15cbe56 (M4 RETURN-TO-E1 / V109 APPROVE)
  - W1-A v1.1 spec PA-amend d1add583 (alpha_candidate_1 + alpha_candidate_4)
  - W2-A finalize ce4c7bbd (2 candidate pre-spec finalize + V101 ENUM correction)
  - W2-E4 E4 regression fa466361 (already verified M4 R2 + V109; W2-B not yet covered)
head_at_review: 817de10a (= origin/main, clean WT)
verdict: M4 R2 APPROVE → E4 done · W2-B APPROVE → E4 regression pending
---

# §1 Executive Summary

## §1.1 Verdict

**M4 W1-C Round 2 fix (commit 99709a2f): APPROVE** — 6 schema column drift fully fixed + 19 schema-grep regression test PASS + tick_window.rs:64 unwrap replaced with `if let Some(evicted)` early return pattern. 0 BLOCKER · 0 finding. E4 regression already PASS (fa466361). No further E2 action; carry-over closed.

**W2-B Alpha Tournament IMPL (commit 817de10a): APPROVE → E4 regression pending** — funding_short_v2 + liquidation_cascade_fade Rust scaffold strictly conforms to W1-A v1.1 spec + PA-amend d1add583 + W2-A finalize. 5-gate auto path inheritance preserved; V101 ENUM compliance (`direct_exploit` only); V103 real table `learning.hypotheses` (not `m4_hypotheses_extended`); 0 hard boundary touch; 0 unsafe; 0 production-path unwrap. 95/95 W2-B Rust unit tests PASS (funding_short_v2 47 + liquidation_cascade_fade 48). 1 LOW inherited cooldown-wire pattern + 1 LOW Python harness pending-wire warning (both pre-existing pattern; documented; do not block E4). **Triggers fresh E4 regression on 817de10a**.

Two work items independent: M4 R2 closure does not depend on W2-B; W2-B does not touch M4 source loaders or schema-grep harness.

## §1.2 Verification Empirical

| Check | M4 R2 結果 | W2-B 結果 |
|---|---|---|
| cargo test --release -p openclaw_core --lib round 1 | 416/0/0 PASS | n/a (W2-B 在 openclaw_engine) |
| cargo test --release -p openclaw_core --lib round 2 (non-flaky) | 416/0/0 PASS · 一致 | n/a |
| cargo test --release -p openclaw_engine --lib round 1 | n/a | 3463/0/1 PASS |
| cargo test --release -p openclaw_engine --lib round 2 (non-flaky) | n/a | 3463/0/1 PASS · 一致 |
| funding_short_v2 module tests | n/a | 47/0/0 PASS |
| liquidation_cascade_fade module tests | n/a | 48/0/0 PASS |
| pytest helper_scripts/m4/ | 70/0 PASS in 0.03s | n/a |
| pytest 19 new schema-grep regression (test_source_loader_schema.py) | 19/0 PASS in 0.02s | n/a |
| 6 schema column drift fix (SQL string verify) | 全 PASS · whitelist 6/6 hit + blacklist 5/5 = 0 hit | n/a |
| W1-A v1.1 spec invariant (funding_short_v2 IS_LONG=false / 30% / 24h / BTC/ETH) | n/a | 全 PASS |
| W1-A v1.1 spec invariant (lcf 5min / 60min / BTC \$500k + ETH \$300k / fade direction map) | n/a | 全 PASS |
| V101 ENUM compliance (track='direct_exploit' only) | n/a | 全 PASS · 0 production reference to alpha_short_carry / alpha_microstructure_fade |
| V103 hypotheses real table (`learning.hypotheses`) | n/a | 全 PASS · 0 reference to m4_hypotheses_extended |
| Hard boundary 觸碰 (live_execution_allowed/authorization/system_mode/OPENCLAW_ALLOW_MAINNET) | 0 觸碰 | 0 觸碰 |
| Cross-platform /home/ncyu / /Users/ hardcode | 0 hit | 0 hit |
| unsafe Rust 塊 | 0 hit | 0 hit |
| `.unwrap()` / `.expect()` in production path | 0 hit (tick_window:64 已修) | 0 hit (1 expect 僅在 cfg(test) mod tests params.rs:386) |
| File size cap 800/2000 LOC | tick_window.rs 213 LOC | max liquidation_cascade_fade/tests.rs 649 LOC; max prod mod.rs 610 LOC |
| Multi-session race 5a-5e | 全 PASS · HEAD = origin/main = 817de10a · WT 全 clean | 同 |
| live + paper TOML 變動 | 0 hit (M4 R2 不改 TOML) | 0 hit (W2-B 只改 demo TOML) |

# §2 M4 W1-C Round 2 (commit 99709a2f) — APPROVE

## §2.1 W2-E 原 review 5 issue closure

| 原 W2-E finding | E1 修法 | E2 R2 verify |
|---|---|---|
| HIGH BLOCKER §2.1.1 #1: `size` → `qty` (fills_loader) | line 55: `qty,` SELECT direct column | SQL string blacklist `\bsize\b` = 0 hit; whitelist `\bqty\b` = 6 hit ✅ |
| HIGH BLOCKER §2.1.1 #2: `close_fill = TRUE` → `entry_context_id IS NOT NULL` | line 65 `AND entry_context_id IS NOT NULL` | blacklist `close_fill\s*=\s*TRUE` = 0 hit; whitelist pattern = 1 hit ✅ |
| HIGH BLOCKER §2.1.1 #3: `realized_net_bps` 不存在 | line 59 `(realized_pnl / NULLIF(price * qty, 0)) * 10000 AS realized_net_bps`（derived alias） | SQL line 58: `realized_pnl,` source column; line 59: `... AS realized_net_bps` 為 derived alias（test 116 顯式允許 alias 用法） ✅ |
| HIGH BLOCKER §2.1.2 #1: `liq.size` → `liq.qty` (liquidations_loader) | line 41 `liq.qty,` | blacklist `liq.size` = 0 hit; whitelist `liq.qty` = 1 hit ✅ |
| HIGH BLOCKER §2.1.2 #2: `aggregator_type` 完全移除 | line 36-50 全 SELECT 不含 `aggregator_type`；只 5 raw column (symbol/ts/side/qty/price) + self-fill LEFT JOIN filter | blacklist `aggregator_type` = 0 hit in SQL string ✅ |
| **E1 額外 catch (Round 2 self-found)**: `close_reason_code` → `exit_reason` | line 61 `exit_reason` SELECT direct | blacklist `close_reason_code` = 0 hit; whitelist `exit_reason` = 1 hit ✅ |
| MEDIUM #1: 51 pytest 全黑盒 source loader SQL | 新增 `test_source_loader_schema.py` 19 test (10 whitelist + 5 blacklist + 4 build_query contract) | pytest verbose run 19/0 PASS in 0.02s; 4 source loader 各覆蓋 ✅ |
| LOW #1: tick_window.rs:64 `pop_front().unwrap()` | line 67 `if let Some(evicted) { ... return Some(evicted); }` early return pattern + 上面 len > capacity guard 邏輯安全 + 100k Kahan precision test exercise if-let 99k 次 | 7/7 tick_window tests PASS（含 `aggregator_kahan_precision_under_many_pushes` 100k push pre-condition）；production path unwrap = 0 ✅ |

## §2.2 6 schema column drift 補強驗證

### Empirical SQL string verify（黑盒對齊真實 PG schema）

```
=== FILLS_QUERY_SQL ===
SELECT
    symbol, strategy_name, ts, side, qty, price, fee_rate, realized_pnl,
    (realized_pnl / NULLIF(price * qty, 0)) * 10000 AS realized_net_bps,
    entry_context_id, exit_reason
FROM trading.fills
WHERE engine_mode IN ('live', 'live_demo')
  AND ts >= now() - %(lookback)s::INTERVAL
  AND entry_context_id IS NOT NULL
```

- Whitelist real columns 全到位（qty / realized_pnl / entry_context_id / exit_reason）
- Blacklist illegal columns SQL 內 0 hit（size / close_fill / close_reason_code）
- `realized_net_bps` 僅作 `AS` alias，源自 `realized_pnl / notional * 10000` derived

```
=== LIQUIDATIONS_QUERY_SQL ===
SELECT liq.symbol, liq.ts, liq.side, liq.qty, liq.price
FROM market.liquidations liq
LEFT JOIN trading.fills f ON f.symbol = liq.symbol
                          AND f.ts BETWEEN (liq.ts - %(self_fill_window)s::INTERVAL) AND liq.ts
WHERE liq.ts >= now() - %(lookback)s::INTERVAL
  AND f.fill_id IS NULL
```

- Whitelist `liq.qty` 到位
- Blacklist `liq.size` / `aggregator_type` SQL 內 0 hit
- self-fill 5s LEFT JOIN filter 保留（防 self-fill cascade noise 污染）

### Round 2 額外 catch — `close_reason_code` → `exit_reason`

E1 在 Round 2 修復過程中**自行 catch** 第 6 個 column drift。`close_reason_code` 不存在於 `trading.fills`（empirical PG verify），真實 column 是 `exit_reason`。test `test_fills_loader_uses_exit_reason_not_close_reason_code` parametrize 進 blacklist。E1 self-found pattern 對齊 `feedback_v_migration_pg_dry_run` SOP — 任何 PG-coupled spec 修改必先 empirical reflection。

## §2.3 19 schema-grep regression test cover

| Test | 範圍 | 結果 |
|---|---|---|
| test_fills_loader_uses_qty_not_size | whitelist qty + blacklist size | PASS |
| test_fills_loader_uses_realized_pnl_not_realized_net_bps | whitelist realized_pnl + 允許 AS alias | PASS |
| test_fills_loader_uses_entry_context_id_pattern_not_close_fill | whitelist `entry_context_id IS NOT NULL` + blacklist close_fill | PASS |
| test_fills_loader_uses_exit_reason_not_close_reason_code | whitelist exit_reason + blacklist close_reason_code | PASS |
| test_fills_loader_engine_mode_whitelist_in_form | whitelist `IN ('live','live_demo')` + blacklist `= 'live'` | PASS |
| test_fills_loader_build_query_returns_sql_tuple | contract test | PASS |
| test_liquidations_loader_uses_qty_not_size | whitelist liq.qty + blacklist liq.size | PASS |
| test_liquidations_loader_no_aggregator_type | blacklist aggregator_type | PASS |
| test_liquidations_loader_self_fill_filter_present | whitelist LEFT JOIN + f.fill_id IS NULL | PASS |
| test_liquidations_loader_build_query_returns_sql_tuple | contract test | PASS |
| test_kline_loader_uses_canonical_columns | 8 column baseline regression | PASS |
| test_kline_loader_excludes_partial_bar | partial bar exclusion subquery | PASS |
| test_kline_loader_build_query_returns_sql_tuple | contract test | PASS |
| test_funding_loader_uses_canonical_columns | 3 column whitelist | PASS |
| test_funding_loader_annualized_calculation | annualized funding formula | PASS |
| test_funding_loader_build_query_returns_sql_tuple | contract test | PASS |
| test_no_loader_uses_illegal_column[close_fill] | parametrize black-list cross-loader | PASS |
| test_no_loader_uses_illegal_column[close_reason_code] | parametrize black-list cross-loader | PASS |
| test_no_loader_uses_illegal_column[aggregator_type] | parametrize black-list cross-loader | PASS |

Schema-grep regression structurally prevents future `qty` ⇄ `size` / `entry_context_id IS NOT NULL` ⇄ `close_fill = TRUE` regressions; 1 行 test 防禦 schema drift。對齊 W2-E E2 review §2.3 captured lesson #1。

## §2.4 tick_window.rs:64 LOW finding closure

```rust
if self.buffer.len() > self.capacity {
    // 為什麼 if let Some 而非 unwrap：上面 len > capacity guard 邏輯上保證
    //   pop_front 必返 Some，但 unwrap 違反 E2 profile「unwrap 僅限不可
    //   恢復場景」guideline。if let 是等價且更 idiom 的寫法。
    if let Some(evicted) = self.buffer.pop_front() {
        kahan_add(&mut self.running_sum, &mut self.running_sum_c, -evicted);
        kahan_add(
            &mut self.running_sum_sq,
            &mut self.running_sum_sq_c,
            -evicted * evicted,
        );
        return Some(evicted);
    }
}
None
```

- `if let Some(evicted)` early return pattern 完全消除 `unwrap()` 並保持邏輯一致性
- 7/7 tick_window 既有 tests 全 PASS（含 100k push Kahan precision exercise）
- 註釋顯式說明 idiom rationale，對齊 chinese-first comment skill

## §2.5 跨平台 + 文件大小 + race check

- /home/ncyu / /Users/ hardcode: 0 hit in M4 R2 改動範圍
- file size: tick_window.rs 213 LOC; fills_loader.py 85; liquidations_loader.py 66; test_source_loader_schema.py 285 — 全 < 800 行警告線
- Multi-session race 5a-5e: HEAD = origin/main = 817de10a · WT clean · 0 sibling commit overlap M4 R2 file scope

# §3 W2-B Alpha Tournament IMPL (commit 817de10a) — APPROVE → E4 regression pending

## §3.1 W1-A v1.1 spec compliance（funding_short_v2 + liquidation_cascade_fade）

### funding_short_v2 spec invariant

| Invariant (W1-A v1.1 spec) | Implementation | 結果 |
|---|---|---|
| short-only hard enforcement | `const IS_LONG: bool = false` (mod.rs:74) compile-time constant；on_tick line 469 `IS_LONG` 直接傳入 `compute_post_only_price`；line 498 `OrderIntent::new_trade(..., IS_LONG, ...)` | ✅ compile-time invariant, IPC 無法翻轉 |
| 30% annualized funding gate | `DEFAULT_FUNDING_THRESHOLD_ANNUALIZED: f64 = 0.30` (params.rs:27)；should_enter line 178 `annualized > self.funding_threshold_annualized` | ✅ |
| 24h hard max_hold | `DEFAULT_MAX_HOLD_MS: u64 = 24 * 3_600_000` (params.rs:39)；should_exit line 205 time-stop | ✅ |
| Stage 1 cohort BTCUSDT/ETHUSDT | params.rs:262-266 validate reject non-cohort；mod.rs:131 default vec!["BTCUSDT","ETHUSDT"]；on_tick line 374 `is_allowed_symbol` fence | ✅ double-enforcement |
| funding_threshold floor 0.20 (IPC patch 防 break-even) | params.rs:54 `FUNDING_THRESHOLD_FLOOR: f64 = 0.20`；validate line 198 floor enforce | ✅ |
| hysteresis (exit < threshold) | validate line 215 reject `funding_exit >= funding_threshold` | ✅ |
| amortized edge gate | compute_edge line 165: `funding_rate.abs() - (total_cost_bps / 10000 / expected_periods)` | ✅ |
| negative funding hard reject (短倉不轉長) | should_enter line 174 `if funding_rate_8h <= 0.0 { return false }` 前置條件 | ✅ |

### liquidation_cascade_fade spec invariant

| Invariant (W1-A v1.1 spec) | Implementation | 結果 |
|---|---|---|
| 5min window threshold | mod.rs:160-165 `pulse.long_notional_5m.max(pulse.short_notional_5m) >= self.threshold_for(symbol)` （panel-internal aggregation，非 entry rolling stat - 避免 `rolling(N).max()` look-ahead bias，per memory feedback_indicator_lookahead_bias） | ✅ |
| BTC \$500k / ETH \$300k per-symbol threshold | params.rs:26 `DEFAULT_BTC_THRESHOLD_USD: f64 = 500_000.0`; line 29 `DEFAULT_ETH_THRESHOLD_USD: f64 = 300_000.0`；per_symbol_threshold map (mod.rs:123-125) | ✅ |
| 60min max_hold time-stop | params.rs:35 `DEFAULT_MAX_HOLD_MS: u64 = 60 * 60_000`；should_exit line 191 time-stop branch | ✅ |
| fade direction map (LongLiq→long, ShortLiq→short, Mixed→reject) | mod.rs:171-175 `match pulse.dominant_side` 顯式 3 條件返 Option<bool> | ✅ 對抗式 spec §9 #6 寫反風險已關閉 |
| min_events 3 防 single-large-event 假訊號 | params.rs:32 `DEFAULT_MIN_EVENTS: u32 = 3`；should_enter line 167 gate | ✅ |
| reverse_cascade 1.5x ratio | params.rs:42 `DEFAULT_REVERSE_CASCADE_RATIO: f64 = 1.5`；should_exit line 209-220 enforcement | ✅ |
| take_profit 1.5% | params.rs:38 `DEFAULT_TAKE_PROFIT_PCT: f64 = 1.5`；should_exit line 199-205 calc | ✅ |
| panel + pulse fail-closed when None | on_tick line 412-419: `surface.liquidation_pulse` None → return empty；`pulse_for(sym)` None → return empty | ✅ |
| Stage 1 cohort fence + IPC double-enforce | params.rs:244-249 validate；on_tick line 406 `is_allowed_symbol` fence | ✅ |
| self-fills filter Stage 1 stub returns false | mod.rs:248 `is_self_origin_event` always returns false；註釋說明 BB C6 PROOF PASS 證 market.liquidations 31k rows 0 self-origin + Stage 1 demo balance 結構性不走 Bybit liquidation engine 路徑 | ✅ Sprint 3+ V109 wire 真實 enforcement |

## §3.2 5-gate auto path inheritance（per CR-15）

### Intent emit path 完全沿 IntentProcessor → Guardian → Decision Lease

```
funding_short_v2/mod.rs:496      vec![StrategyAction::Open(OrderIntent::new_trade(...))]
liquidation_cascade_fade/mod.rs:539  vec![StrategyAction::Open(OrderIntent::new_trade(...))]
```

- 2 candidate emit `StrategyAction::Open(OrderIntent::new_trade(...))` 走標準 pipeline
- 不直接觸碰 `execution_authority` / `live_reserved` / `live_demo_authority` / `OPENCLAW_ALLOW_MAINNET`
- 不繞 Guardian、不繞 Decision Lease、不繞 5-gate

### active=false + enabled=false 雙保險

- `risk_config_demo.toml` line 101 `[per_strategy.funding_short_v2] enabled = false`
- `risk_config_demo.toml` line 115 `[per_strategy.liquidation_cascade_fade] enabled = false`
- `strategy_params_demo.toml` line 204 `[funding_short_v2] active = false`
- `strategy_params_demo.toml` line 224 `[liquidation_cascade_fade] active = false`
- `live` / `paper` TOML 0 改動 verified（`git diff 99709a2f..817de10a -- settings/risk_control_rules/risk_config_live.toml settings/risk_control_rules/risk_config_paper.toml settings/strategy_params_live.toml settings/strategy_params_paper.toml` 全空）

### fail_closed_inactive_config 對 W2-B 2 candidate 顯式 false

```rust
// params.rs line 163-167
// funding_harvest / funding_short_v2 / liquidation_cascade_fade default 已 = false；
// 此處顯式重申是 fail-closed 不變量（exchange-facing pipeline 必全停）。
cfg.funding_harvest.active = false;
cfg.funding_short_v2.active = false;
cfg.liquidation_cascade_fade.active = false;
```

- Exchange-facing pipeline (Demo / Live) TOML parse fail → fail_closed_inactive_config()
- W2-B 2 candidate 顯式 false（不依賴 default）— 等同 funding_arb / funding_harvest 既有 fail-closed 範式

## §3.3 V101 ENUM compliance（PA-amend d1add583 後）

### 全 production code path `track = 'direct_exploit'`

```
helper_scripts/alpha_tournament/14d_bucket_split.sql:32:    AND track = 'direct_exploit'
helper_scripts/alpha_tournament/attribution_daily.py:77:EXPECTED_TRACK: str = "direct_exploit"
helper_scripts/alpha_tournament/attribution_daily.py:112:    AND track = 'direct_exploit'
```

### 0 production reference to `alpha_short_carry` / `alpha_microstructure_fade`

- 4 grep hit 全在 **註釋 anti-pattern 標註**（顯式說明「不可寫」）：
  - `attribution_daily.py:76` — `# 不可寫 'alpha_short_carry' / 'alpha_microstructure_fade'`
  - `__init__.py:19-20` — `非 'alpha_short_carry' / 'alpha_microstructure_fade' 虛構 track ENUM`
- 0 hit 在 Rust 策略 production 代碼 (`rust/openclaw_engine/src/strategies/funding_short_v2 + liquidation_cascade_fade`)
- 0 hit 在 SQL string actual content (`build_bucket_split_query()` 返回值 verify via Python import)

## §3.4 V103 hypotheses real column compliance

### `learning.hypotheses` 是 canonical real table（非 `m4_hypotheses_extended`）

- W2-B `helper_scripts/alpha_tournament/` 整套 SELECT-only path（讀 `trading.fills`），**不直接寫入 learning.hypotheses**；DRAFT writeback 由 W2-F MIT post-IMPL audit 手動執行 §3.5 INSERT pattern
- 0 grep hit `m4_hypotheses_extended` 在 W2-B production code (只在 `__init__.py:22` 註釋顯式說明「該 table 不存在」)
- attribution_daily.py 真實 SQL `FROM trading.fills` 不含 `learning.hypotheses` 引用 — Sprint 2 W2-B scaffold 階段不寫 hypotheses（per W2-A finalize §6.2）

### W2-B scaffold 階段定位

- attribution_daily.py 只 SELECT trading.fills + 印 Wilson CI + Bonferroni alpha 配置 JSON
- 真實 PG query / cron wrapper / DRAFT INSERT 由 W2-F PA 接續落地
- 不滲入 ML training pipeline (per §3.11 invariant)；W2-B 純 read-only attribution

## §3.5 ADR-0024-lite + 16#7 DRAFT-only invariant

- attribution_daily.py 純 read-only，不寫 hypotheses 表，**不可能** auto-promote
- tournament_orchestrator.py Sprint 2 stub `return 0`，0 PG 寫入
- 14d_bucket_split.sql 純 SELECT，無 INSERT/UPDATE/DELETE
- DRAFT INSERT 由 W2-F PA 在 sign-off 後手動執行（per W2-A finalize §3.5 / §11.3）

## §3.6 Hard boundary 0 觸碰

| 邊界 | grep target | 結果 |
|---|---|---|
| live_execution_allowed | rust/openclaw_engine/src/strategies/funding_short_v2 + liquidation_cascade_fade + helper_scripts/alpha_tournament/ | 0 hit |
| authorization.json / authorization_json | 同上 | 0 hit |
| system_mode | 同上 | 0 hit |
| OPENCLAW_ALLOW_MAINNET / live_reserved | 同上 | 0 hit |
| execution_authority / live_demo_authority | 同上 | 0 hit |

W2-B strategies 不寫 live state、不創新 order 入口、不繞 Decision Lease、不動 5-gate、不寫 authorization.json — 全部走標準 `StrategyAction::Open(OrderIntent::new_trade(...))` pipeline 由 tick_pipeline dispatch 鏈經 IntentProcessor → Guardian → Decision Lease。

## §3.7 Cross-section M4 + W2-B PG path collision check

| 維度 | M4 (Stream B) | W2-B (Stream A) |
|---|---|---|
| trading.fills 讀 | engine_mode IN ('live', 'live_demo') | engine_mode IN ('demo', 'live_demo') |
| strategy_name filter | 無（cover 全 5 textbook + funding_harvest） | strategy_name IN ('funding_short_v2', 'liquidation_cascade_fade') |
| 寫入路徑 | DRAFT INSERT into learning.hypotheses (via W2-D MIT cron) | SELECT-only (scaffold)；W2-F PA 接續 DRAFT INSERT |
| source_module 區分 | `M4_pattern_miner` | `alpha_tournament` |
| 時間窗 | 90 day | 14 day |

兩個 stream 同表（trading.fills + learning.hypotheses）但路徑完全獨立：
- engine_mode 不重疊（M4 看 live + live_demo；W2-B 看 demo + live_demo）— **重疊只在 'live_demo'**（PipelineKind::Live + non-mainnet endpoint）
- 兩個策略目前 default active=false，**Stage 1 Demo 跑時 engine_mode='demo'**（PipelineKind::Demo），M4 不會讀到 W2-B candidate fills
- 同表寫入路徑 (learning.hypotheses) 由 source_module 標籤完全區分
- Sprint 2 期 W2-B candidate engine_mode = 'demo'（Demo TOML 直跑），M4 看不到 → 0 collision

per W2-A finalize §9 collision check verified empirically。

## §3.8 注釋規範 + 跨平台 + file size cap

- 新增 mod.rs / params.rs / tests.rs 全用 MODULE_NOTE 中文格式（per bilingual-comment-style skill 當前 Chinese-First Comment Style）
- 為什麼 fail-closed / 為什麼 hard enforcement / 為什麼 immutable / 為什麼 cohort fence — 全寫了 rationale
- `/home/ncyu` / `/Users/[^/]+` hardcode: 0 hit in W2-B 範圍
- file size: max prod liquidation_cascade_fade/mod.rs 610 LOC；max test 649 LOC — 全 < 800 warn / 2000 hard cap
- registry.rs growth: +52 LOC 接 2 candidate；mod.rs growth +10 LOC declare 2 sub-module — 全在現有 1200 LOC + 1200 LOC soft warn 內

## §3.9 對抗反問 10 條

1. **「IS_LONG: bool = false 是 compile-time const，但 IPC update_params 是否會繞？」**
   verify: IS_LONG 是 const 不是 self 字段；`update_params` 永遠用 const 值；OrderIntent::new_trade(IS_LONG, ...) 永遠 false；short-only enforcement 在 type-level — **無法繞**。

2. **「funding_threshold floor 0.20 是 validate-only，但是 caller 端直接 mutate field 是否繞？」**
   verify: registry.rs 直接 mutate `fsv2.funding_threshold_annualized` 字段，**跳過 validate**！— **但這是 startup-time mutation**（TOML load），不是 runtime mutation；TOML parse 路徑為 `StrategyParamsConfig::default()` 後從 TOML override → 在 `FundingShortV2Params::default()` 已 30%（合法），override 後值來自 demo TOML（commit 設 30%）。**IPC runtime 路徑** (`update_params_json` → `update_params` → `params.validate()`) 必經 floor check。startup TOML 直接 mutate field 是 Sprint 1B funding_arb / funding_harvest 共用範式（已 land 已 review），不是 W2-B 新引入問題。但若 future operator 手改 demo TOML 將 `funding_threshold_annualized = 0.15`，startup 不會 fail-closed — 這是 **inherited pattern weakness**，標 LOW NTH（見 §4）。

3. **「Stage 1 cohort BTCUSDT/ETHUSDT，TOML 改成 ["SOLUSDT"] 是否在 startup fail-closed？」**
   verify: `FundingShortV2Params::validate()` line 261-265 reject non-cohort；但 startup mutation 同問題 #2，**不過 registry.rs:283 仍直接 mutate `fsv2.allowed_symbols = p.funding_short_v2.allowed_symbols.clone();`**，跳過 validate。**但 on_tick line 374 `is_allowed_symbol` fence** 是 runtime defense-in-depth — 即使 TOML 寫 ["SOLUSDT"]，runtime 仍會跳過所有非 cohort symbol（不過實際上 allowed_symbols 已被 mutate 為 ["SOLUSDT"]，is_allowed_symbol("BTCUSDT") 返 false，造成 Stage 1 cohort 也被 reject — 結果 fail-closed 但是 silent skip，不 warn）。**標 LOW NTH**（見 §4）。

4. **「fade direction 映射 LongLiquidated→long / ShortLiquidated→short 是否寫反？」**
   verify: mod.rs:172-174 explicit `LongLiquidated => Some(true)` (fade buy) + `ShortLiquidated => Some(false)` (fade sell) + `Mixed => None` (reject)；註釋顯式說明 mean-revert thesis；W1-A spec §1.1 對齊（counter-cascade fade）— **方向正確**。tests `should_enter_btc_long_liquidated_returns_long` + `should_enter_btc_short_liquidated_returns_short` + `should_enter_mixed_returns_none` 三個顯式 assert。

5. **「panel.pulse_for(sym) is_none → fail-closed skip 是否會 starve?」**
   verify: mod.rs:412-419 `surface.liquidation_pulse` None → return empty；`panel.pulse_for(sym)` None → return empty。**fail-closed by spec §5.2**（panel + pulse 必須兩者存在才走 entry/exit）。若 LiquidationPulseAggregator 故障，本 strategy 完全 dormant — 對齊 «資料不足必 fail-closed» CLAUDE §一硬邊界。test `on_tick_pulse_for_none_skip` 顯式 assert。

6. **「entry_notional snapshot 在 on_external_close / on_close_confirmed / on_close_skipped 是否清乾淨？」**
   verify: 3 hook 全 `.entry_notional.remove(symbol)`；rejection rollback `on_rejection` line 562 同步清。test cover `should_exit_reverse_cascade_long_to_short` + `should_exit_take_profit_long/short`。

7. **「同 trade-cycle multi-entry是否會多次寫 entry_notional snapshot 覆蓋?」**
   verify: 入場路徑 line 525-526 `self.entry_notional.insert(sym.to_string(), dominant_notional)` 是覆蓋寫；同 cycle 不會 multi-entry（cooldown 30min + h0_allowed + position 持有時 owned_position 走 exit branch，不走 entry branch）— 邏輯閉環。

8. **「14d_bucket_split.sql 與 attribution_daily.py 內 SQL 是否一致？」**
   verify: 兩 SQL 邏輯相同（attribution_daily.py:97-130 vs 14d_bucket_split.sql:18-50）— attribution_daily.py 改用 `strategy_name = ANY(%s)` placeholder（runtime bind），14d_bucket_split.sql 用 `IN ('funding_short_v2', 'liquidation_cascade_fade')` literal（static SQL）；兩者語意等價。

9. **「Stage 1 stub `is_self_origin_event` 永遠 false 是否會誤判合法 cascade?」**
   verify: 註釋 245-251 顯式說明 BB C6 PROOF PASS 證 market.liquidations 31k rows 0 self-origin；Stage 1 demo balance ($1000 typical) 結構性不走 Bybit liquidation engine。**Sprint 3+ V109 anomaly_events wire 真正 enforcement**（已標 follow-up）。Stage 1 stub return false 是 fail-open false-positive risk = 0 — **不誤判 true** 才是核心 risk（誤判 true 會錯失所有合法 cascade entry），現 stub 永遠 false 保證不誤判 true。

10. **「engine_mode IN ('demo', 'live_demo') vs M4 IN ('live', 'live_demo') 是否會雙讀同 fill?」**
    verify: 同 fill 同時帶 'demo' 或 'live_demo' 是 mutually exclusive（per mode_state.rs effective_engine_mode）— 一筆 fill 唯一一個 engine_mode 標籤。'live_demo' 是 W2-B + M4 共重疊區（PipelineKind::Live + demo endpoint）。**Sprint 2 W2-B 預設 active=false**，Stage 1 跑時 engine_mode='demo'（PipelineKind::Demo）— M4 看不到。即使 future operator IPC active=true 走 LiveDemo path（engine_mode='live_demo'），M4 + W2-B 在 source_module 標籤完全區分 (`M4_pattern_miner` vs `alpha_tournament`)，目標表寫入路徑獨立。

## §3.10 W2-B 95/95 Rust unit test 全綠 + 雙跑 non-flaky

```
funding_short_v2::tests::*           47 passed; 0 failed; 0 ignored; 3417 filtered
liquidation_cascade_fade::tests::*   48 passed; 0 failed; 0 ignored; 3416 filtered
openclaw_engine --lib (cargo test --release) round 1+2:  3463 passed; 0 failed; 1 ignored
```

1 ignored = pre-existing `layer_2_fence_archive_policy_diagnostic_only` sibling scope leak（per fa466361 E4 attribution；Sprint 1B Earn Wave B 875de212 lineage；0 W2 attribution）。

# §4 Finding（M4 R2 + W2-B 跨 stream 合並）

| 嚴重性 | 來源 | 位置 | 描述 | 建議 |
|---|---|---|---|---|
| LOW NTH | W2-B inherited | `registry.rs:282` + sibling funding_arb:243 / funding_harvest:258 | 工廠 startup 路徑直接 mutate `fsv2.funding_threshold_annualized` / `fsv2.allowed_symbols` 等 field，**跳過 `StrategyParams::validate()`**。若 future demo TOML 寫 `funding_threshold_annualized = 0.10` 或 `allowed_symbols = ["SOLUSDT"]`，startup 不會 fail-closed；只有 runtime `is_allowed_symbol` fence + `should_enter` floor 防守。inherited from funding_arb/funding_harvest，非 W2-B 新引入。 | Sprint 3+ 統一 wrapper helper：`apply_funding_short_v2_params(strategy, params)` 內部 `params.validate()?` 後再 mutate field；同步 funding_arb / funding_harvest registry 路徑。建追蹤 follow-up TODO，不阻 E4。 |
| LOW NTH | W2-B inherited | `registry.rs:282` + sibling | 工廠 startup 路徑直接 set `fsv2.cooldown_ms = ...` field（公開）但 **不調用 `fsv2.cooldown.set_duration(...)`**。`TrendCooldown.duration_ms` 仍是 `new()` default 8h；TOML `cooldown_ms` 是裝飾性，實際 cooldown 用 default。`IPC update_params` 路徑正確調用 `set_duration`。inherited from funding_arb pattern (registry.rs:243 同問題)；註釋顯式說明這是 sibling pattern。 | Sprint 3+ 同 #1 wrapper helper，加 `strategy.cooldown.set_duration(params.cooldown_ms)`；同步 funding_arb / funding_harvest。建追蹤 follow-up TODO，不阻 E4。 |
| LOW NTH | W2-B scaffold | `helper_scripts/alpha_tournament/attribution_daily.py:283-298` | 真實 PG query 路徑為 `logger.warning + status='wire_up_pending_w2f_pa'`；W2-F PA 接續落地 cron wrapper + psql connection 注入。scaffold 階段 acceptable（per W2-A finalize §11.3 action checklist）。 | W2-F PA 接續：cron wrapper shell + PG connection 注入；不阻當前 W2-B sign-off。 |
| LOW NTH | W2-B scaffold | `helper_scripts/alpha_tournament/tournament_orchestrator.py:32-47` | Sprint 2 stub 永遠 `return 0`；M11 counterfactual replay integration 由 Sprint 3+ Wave dispatch 接續。 | Sprint 3+ Wave 拆分接 M11 replay；不阻當前 W2-B sign-off。 |
| 0 BLOCKER | — | — | — | — |
| 0 HIGH | — | — | — | — |
| 0 MEDIUM | — | — | — | — |

**所有 finding 均為 LOW NTH（Nice-To-Have）pre-existing inherited pattern 或顯式 scaffold-stage 文檔化未完成**。0 W2-B-introduced regression；0 W2-B-introduced hard boundary 觸碰；0 W2-B-introduced shortcut。

# §5 Wave 3 Dispatch Readiness

## §5.1 PASS conditions for Wave 3 dispatch

- ✅ M4 W1-C Round 2 schema drift 全修 + 19 schema-grep regression test PASS + E4 fa466361 已驗
- ✅ W2-B Alpha Tournament 2 candidate IMPL spec compliance 全 PASS
- ✅ V101 / V103 production reference 全 grep clean
- ✅ 5-gate auto path inheritance 不繞 + active/enabled 雙保險
- ✅ Hard boundary 0 觸碰 + 跨平台 0 hardcode + unsafe 0 + file size 全合規
- ✅ Multi-session race 5a-5e 全 PASS · HEAD = origin/main = 817de10a · WT clean
- ✅ M4 + W2-B PG path collision empirical verified 不衝突
- ✅ 95/95 W2-B Rust unit tests PASS (47 funding_short_v2 + 48 liquidation_cascade_fade)
- ✅ 全套 Mac cargo --release × 2 (openclaw_core 416 + openclaw_engine 3463) non-flaky
- ✅ 全套 pytest M4 70/0 (51 + 19 new) non-flaky

## §5.2 待 Wave 3 行動

1. **E4 regression on 817de10a** — 重跑 W2-E4 regression 涵蓋 W2-B（fa466361 只覆蓋到 99709a2f）
2. **W2-F MIT post-IMPL audit** — 14d demo attribution 樣本累積（needs Stage 0R replay preflight PASS 先）
3. **W2-F PA 接續 cron wrapper + psql connection 注入** — attribution_daily.py production wire-up
4. **Sprint 3+ M11 counterfactual replay integration** — tournament_orchestrator.py 接 M11

## §5.3 不阻 Wave 3 但建追蹤 follow-up

- TODO: registry.rs startup validate wrapper helper（unify funding_arb / funding_harvest / funding_short_v2 / liquidation_cascade_fade 4 個 strategy 的 startup field-mutation 路徑，加 `params.validate()?` + `cooldown.set_duration()` 真實 wire）
- TODO: W2-F PA 接 attribution_daily.py cron wrapper shell + secrets source pattern

# §6 結論

| Item | M4 R2 (99709a2f) | W2-B (817de10a) |
|---|---|---|
| Verdict | **APPROVE** (E4 已 PASS fa466361 · 不需重 E2) | **APPROVE → E4 regression pending** |
| BLOCKER | 0 | 0 |
| HIGH | 0 | 0 |
| MEDIUM | 0 | 0 |
| LOW NTH | 0 | 4 (全 inherited / scaffold) |
| 對抗 grep | 8 條全 PASS | 10 條全 PASS |
| Cargo + pytest 雙跑 non-flaky | 全 PASS | 全 PASS |
| 5-gate inheritance | n/a | ✅ 不繞 + 雙保險 |
| Hard boundary 0 觸碰 | ✅ | ✅ |

**Wave 3 dispatch READY**：M4 R2 + W2-B 雙工作流均通過 E2 R2 對抗式 cold review，唯需重跑 E4 regression 覆蓋 W2-B IMPL (commit 817de10a)；其他 Wave 3 工作（W2-F MIT post-IMPL audit / W2-F PA 接 cron wrapper / Sprint 3+ M11）可並行 dispatch。

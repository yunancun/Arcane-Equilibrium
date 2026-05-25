# W1-C Round 2 — M4 Source Loader Schema Drift Fix（per W2-E E2 RETURN-TO-E1）

**Date**: 2026-05-25
**Role**: E1 (Backend Developer)
**Phase**: Sprint 2 v5.8 Stream B Wave 1 W1-C Round 2 (post W2-E E2 review)
**Parent verdict**: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-25--w2e_m4_v109_dual_adversarial_review.md` (commit d15cbe56)
**Status**: IMPL DONE — awaiting E2 re-review

---

## 1. 任務摘要

W2-E E2 cold review catch M4 IMPL 5 個 schema-incorrect column（HIGH BLOCKER）+ 1 source loader test cover gap（MEDIUM-1）+ 1 production-path unwrap（LOW-1）→ RETURN-TO-E1。

**Round 2 修復範圍**：
- 5 schema column 對齊真實 trading.fills + market.liquidations
- 19 test 補 schema-grep regression（覆蓋 4 source loader）
- tick_window.rs:64 unwrap → if let Some 早返

---

## 2. 修改清單

### 2.1 修改 file（3 個）

| File | 改動 | 行數變化 |
|---|---|---|
| `helper_scripts/m4/sources/fills_loader.py` | 5 column 對齊真實 schema + MODULE_NOTE 補 schema 對齊節 | 62 → 87 |
| `helper_scripts/m4/sources/liquidations_loader.py` | 2 column 對齊 + 移除 aggregator_type filter + MODULE_NOTE 補 schema 對齊節 | 54 → 67 |
| `rust/openclaw_core/src/m4_miner/tick_window.rs` | line 64 `pop_front().unwrap()` → `if let Some(evicted)` early return | 邏輯等價 |

### 2.2 新建 file（1 個）

| File | LOC | Purpose |
|---|---|---|
| `helper_scripts/m4/tests/test_source_loader_schema.py` | 234 | 19 個 schema-grep regression test 覆蓋 4 source loader |

---

## 3. 關鍵 diff

### 3.1 fills_loader.py 5 column 對齊

**Before** (W1-C Round 1, E2 catch):
```sql
SELECT symbol, strategy_name, ts, side, size, price, fee_rate,
       realized_net_bps, entry_context_id, close_reason_code
FROM trading.fills
WHERE engine_mode IN ('live', 'live_demo')
  AND ts >= now() - %(lookback)s::INTERVAL
  AND close_fill = TRUE
```

**After** (Round 2 fix):
```sql
SELECT symbol, strategy_name, ts, side, qty, price, fee_rate,
       realized_pnl,
       (realized_pnl / NULLIF(price * qty, 0)) * 10000 AS realized_net_bps,
       entry_context_id, exit_reason
FROM trading.fills
WHERE engine_mode IN ('live', 'live_demo')
  AND ts >= now() - %(lookback)s::INTERVAL
  AND entry_context_id IS NOT NULL
```

**對齊根據**（empirical `\d trading.fills` 2026-05-25）：
- `size` → `qty`（V003 `qty REAL NOT NULL`；trading_writer.rs:459 INSERT 用 qty）
- `realized_net_bps` → `realized_pnl` source + AS alias `(realized_pnl / NULLIF(price * qty, 0)) * 10000`（empirical 0 realized_net_bps column；canonical bps formula = pnl / notional × 10000）
- `close_fill = TRUE` → `entry_context_id IS NOT NULL`（canonical per program_code/ml_training/edge_label_backfill.py:417/513/624）
- `close_reason_code` → `exit_reason`（empirical existing column per V### + V094）

### 3.2 liquidations_loader.py 2 column 對齊 + filter 移除

**Before** (W1-C Round 1):
```sql
SELECT liq.symbol, liq.ts, liq.side, liq.size, liq.price, liq.aggregator_type
FROM market.liquidations liq
LEFT JOIN trading.fills f ...
WHERE liq.ts >= ...
  AND liq.aggregator_type IN ('top_liq_30s', 'cascade_5min')
  AND f.fill_id IS NULL
```

**After** (Round 2 fix):
```sql
SELECT liq.symbol, liq.ts, liq.side, liq.qty, liq.price
FROM market.liquidations liq
LEFT JOIN trading.fills f ...
WHERE liq.ts >= ...
  AND f.fill_id IS NULL
```

**對齊根據**（empirical `\d market.liquidations` 2026-05-25）：
- 真實 column = `(ts, symbol, side, qty, price)` 5 個
- `aggregator_type` 在任何 V### migration 0 hit；spec §1.3 列出的是 PA 草稿期 illustrative pseudo-schema
- cascade detection 走 caller-side `algorithms/event_window.detect_liquidation_cascade_events` 5min rolling，不依賴 source column

### 3.3 tick_window.rs:64 unwrap fix

**Before**:
```rust
if self.buffer.len() > self.capacity {
    let evicted = self.buffer.pop_front().unwrap();
    kahan_add(&mut self.running_sum, &mut self.running_sum_c, -evicted);
    ...
}
```

**After**:
```rust
if self.buffer.len() > self.capacity {
    if let Some(evicted) = self.buffer.pop_front() {
        kahan_add(&mut self.running_sum, &mut self.running_sum_c, -evicted);
        ...
        return Some(evicted);
    }
}
None
```

邏輯等價（上面 `len > capacity` 已保證 pop_front 必返 Some），但符合 E2 profile「unwrap 僅限不可恢復場景」guideline。

---

## 4. 治理對照（W2-E E2 verdict §2.4 退回清單）

| Verdict 點 | 修復狀態 |
|---|---|
| fills_loader.py size → qty | ✅ |
| fills_loader.py realized_net_bps → realized_pnl + AS alias | ✅ |
| fills_loader.py close_fill = TRUE → entry_context_id IS NOT NULL | ✅ |
| liquidations_loader.py liq.size → liq.qty | ✅ |
| liquidations_loader.py aggregator_type 移除（cascade 走 caller-side） | ✅ |
| Source loader schema-grep regression test 補強（MED-1） | ✅ 19 test |
| tick_window.rs:64 unwrap → if let Some（LOW-1） | ✅ |

---

## 5. Mac SSOT verify

### 5.1 cargo test --release -p openclaw_core --lib
```
test result: ok. 416 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```
baseline 不退 — m4_miner 46 + 全 lib 416 與 W2-E Round 2 一致

### 5.2 pytest helper_scripts/m4/
```
70 passed in 0.05s
```
51 existing PASS + 19 new schema-grep regression PASS

### 5.3 tick_window unit test（單獨驗 unwrap fix）
```
test m4_miner::tick_window::tests::aggregator_capacity_zero_disabled ... ok
test m4_miner::tick_window::tests::aggregator_evicts_oldest_on_overflow ... ok
test m4_miner::tick_window::tests::aggregator_full_returns_correct_mean ... ok
test m4_miner::tick_window::tests::aggregator_std_ddof_zero ... ok
test m4_miner::tick_window::tests::aggregator_std_population_calculation ... ok
test m4_miner::tick_window::tests::aggregator_unfull_returns_none ... ok
test m4_miner::tick_window::tests::aggregator_kahan_precision_under_many_pushes ... ok
test result: ok. 7 passed; 0 failed
```
含 `aggregator_evicts_oldest_on_overflow`（驗 evict path）+ `aggregator_kahan_precision_under_many_pushes`（100k push 跑 if let Some early return path 99k 次）。

### 5.4 5 schema self-grep 驗證

| Token | fills_loader SQL | liquidations_loader SQL | 結果 |
|---|---|---|---|
| `\bsize\b` | 0 hit（含 SELECT/WHERE） | 0 hit | ✅ |
| `close_fill` | 0 hit（在 SQL 中） | n/a | ✅ |
| `realized_net_bps` 作為 source ref | 0 hit（只 AS alias 出現） | n/a | ✅ |
| `\bsize\b` | n/a | 0 hit | ✅ |
| `aggregator_type` | n/a | 0 hit | ✅ |

Comment 中 `size / close_fill / realized_net_bps / aggregator_type` 出現是 traceability 設計（解釋為何 fix）— 非 SQL code hit。

### 5.5 Linux PG empirical SQL verify（per Step 6）

```bash
ssh trade-core "psql ... -c '<FILLS_QUERY_SQL with bind subst> LIMIT 3;'"
```
3 row return ✅：
```
1000PEPEUSDT | bb_reversion  | 2026-05-11 | Sell | 6900 | 0.004284 | 0.00055 | -0.0138 | -4.6685 bps | ctx-... | ma_reverse_cross
1000PEPEUSDT | grid_trading  | 2026-04-29 | Sell | 2300 | 0.00379  | 0.00055 | -0.0023 | -2.6385 bps | ctx-... | grid_close_long
1000PEPEUSDT | grid_trading  | 2026-04-29 | Buy  | 5500 | 0.003799 | 0.00055 | -0.0275 | -13.16 bps  | ctx-... | grid_close_short
```

```bash
ssh trade-core "psql ... -c '<LIQUIDATIONS_QUERY_SQL with bind subst> LIMIT 3;'"
```
3 row return ✅：
```
1000PEPEUSDT | 2026-05-18 | Buy | 339200    | 0.003693
1000PEPEUSDT | 2026-05-18 | Buy | 47400     | 0.003682
1000PEPEUSDT | 2026-05-18 | Buy | 1.0209e+6 | 0.003676
```

0 ERROR；schema 對齊 production PG runtime。

---

## 6. 設計決策

### 6.1 為什麼 derived realized_net_bps 而非完全棄用 column

W1-B spec §3.1 6 attribute 計算 + algorithms/effect_size.py 對 bps 需要 forward return 維度的對照。realized_pnl 是 USD 量，不可直接喂 effect size；保留 `AS realized_net_bps` 別名讓 caller dataframe 拿到 bps form 是最小衝擊（不改 algorithm 層）。

NULLIF(price * qty, 0) 防除零 + realized_pnl 為 NULL 時 caller dropna 處理 — SQL 層不過濾以保留樣本。

### 6.2 為什麼 aggregator_type 完全移除而非 stub default

market.liquidations 是 raw event 表（5 column 純結構）。Spec §1.3 illustrative SQL 是 PA 草稿期 pseudo-schema；empirical 0 V### migration ADD COLUMN aggregator_type。

cascade detection（top_liq_30s / cascade_5min）是 algorithm 層職責，已在 `algorithms/event_window.detect_liquidation_cascade_events` 用 5min rolling 實裝；source 層 stub default 反而會誤導 caller 期待 column 存在。

### 6.3 為什麼 close-fill 判定走 entry_context_id IS NOT NULL

canonical per program_code/ml_training/edge_label_backfill.py:417/513/624 — entry 行 entry_context_id IS NULL（entry 自身），close 行 entry_context_id 指向 entry 的 context_id。

W-AUDIT-4b-M2 (2026-05-09) 已 backfill 38% → 95% close fills 的 entry_context_id；M4 用此 pattern 可繼承既有 audit chain 強度。

### 6.4 schema-grep regression test 設計

19 test 分 5 組：
- §1 fills_loader 6 test：qty / realized_pnl / entry_context_id pattern / exit_reason / engine_mode IN / build tuple
- §2 liquidations_loader 4 test：qty / no aggregator_type / self-fill filter / build tuple
- §3 kline_loader 3 test：canonical column / partial bar exclude / build tuple
- §4 funding_loader 3 test：canonical column / annualized formula / build tuple
- §5 跨 loader black-list 3 test (parametrize)：close_fill / close_reason_code / aggregator_type 0 hit

使用 `\b` whole-word grep 避免 substring 誤匹（如 `cascade_size` 不匹 `size`）。

---

## 7. 不確定 / Sprint 3 follow-up

1. **realized_pnl NULL ratio empirical**：trading.fills realized_pnl DEFAULT 0；歷史 row 是否含 NULL（pre-V### migration era）影響 caller dropna 後 sample size。W2-D MIT 接 cron 前需收集 baseline。
2. **close-fill ratio 對 M4 sample size 影響**：W-AUDIT-4b-M2 backfill 95% 對 90d 65k row 級別假設 — Sprint 3 cron 跑第一週收集 empirical preregistered hypothesis count K_hyp 仲裁。
3. **W1-B spec § amend 建議**（per E2 verdict §2.4 #4）：spec line 97-99 + line 117-118 列 size/close_fill/realized_net_bps/aggregator_type 是 illustrative pseudo-schema，建議 PA / MIT amend spec 加 empirical column 列表附錄；避免未來 spec consumer 重蹈 W1-C Round 1 教訓。

---

## 8. Operator 下一步

1. **主會話派 E2 re-review**（per chain）：
   - 5 column 對齊驗（grep SQL string + schema）
   - 19 schema-grep regression test 跑（pytest test_source_loader_schema.py）
   - tick_window unwrap fix 跑（cargo test m4_miner::tick_window）
   - baseline 不退（cargo test --release -p openclaw_core --lib：416/0）

2. **主會話派 E4 regression**（per chain）：
   - pytest helper_scripts/m4/ 全套 70 PASS
   - cargo test --workspace 不退
   - Linux PG empirical SQL run（兩個 query 3 row return）

3. **PM commit + push**（per chain E1→E2→E4→QA→PM）：
   ```
   fix(m4-w1c-round-2): 5 schema-incorrect column drift fix + schema-grep regression + unwrap cleanup

   per W2-E E2 review (commit d15cbe56) HIGH BLOCKER catch:
   - fills_loader.py: size→qty, close_fill→entry_context_id IS NOT NULL, realized_net_bps→derived AS alias, close_reason_code→exit_reason
   - liquidations_loader.py: liq.size→liq.qty, aggregator_type IN(...) filter → 移除（cascade 走 caller-side）
   - tests/test_source_loader_schema.py 新 19 schema-grep regression cover 4 source loader
   - tick_window.rs:64 unwrap → if let Some 早返

   Mac cargo verify baseline 416/0 不退 + pytest 70/0 + Linux PG empirical SQL valid（fills 3 row + liq 3 row）
   per feedback_v_migration_pg_dry_run SOP 補位（source loader 不可繞 schema empirical）
   ```

4. **W1-B spec follow-up**（不阻 Round 2 closure）：建議 PA / MIT 在 spec §1.2 / §1.3 加 empirical column 列表附錄。

---

**E1 IMPL Round 2 DONE** — 待 E2 re-review；report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--w1c_round_2_m4_schema_drift_fix.md`

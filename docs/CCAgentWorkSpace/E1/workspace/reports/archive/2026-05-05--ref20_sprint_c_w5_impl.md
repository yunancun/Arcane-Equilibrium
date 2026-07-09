# REF-20 Sprint C R6 W5 — R6-T8 4-strategy reproducibility smoke (E1 IMPL Sign-off)

- **Date (UTC)**：2026-05-05 18:38Z
- **Agent**：E1
- **Branch**：main（Mac 工作樹，本地 commit pending PM 統一處理）
- **Base HEAD**：`7a04d2f4`（Sprint C R6 W4 closure；Mac/Linux/origin synced）
- **Files touched**：`rust/openclaw_engine/src/replay/calibration_label.rs`（+270 LOC，純 `#[cfg(test)] mod tests` 擴充）
- **PA dispatch path**：「REF-20 Sprint C R6 W5 — R6-T8 4-strategy reproducibility smoke test (per QC §1.1)」
- **QC spec ref**：`srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-05--ref20_r6_calibration_label_spec.md`（§1.1 reproducibility 表 + §10 對抗反問 5 條）

## §1 — 5 reproducibility test 設計

對 QC §1.1 表 5 strategy fixture 各加一 reproducibility test，證明 `derive_execution_confidence(fills, now) -> CalibrationResult` 是 pure stateless 函數：同 input → 9 個 field 字節級相同 output。

| Test | Strategy | n | freshness 區間 | fee pattern | 預期 label | 額外 assert |
|---|---|---:|---|---|---|---|
| `test_r6t8_grid_trading_reproducibility` | grid_trading | 1162 | 1d..6d | Stable(0.0002) | Calibrated | ttl=7d；連跑 3 次同字節 |
| `test_r6t8_ma_crossover_reproducibility` | ma_crossover | 635 | 2d..6.5d | Bimodal(0.0002, 0.00055) | Limited 或 Calibrated | label != None |
| `test_r6t8_funding_arb_reproducibility` | funding_arb | 99 | 1d..5d | Stable(0.0002) | Limited 或 None | label != Calibrated（n<200 必非 calibrated） |
| `test_r6t8_bb_breakout_reproducibility` | bb_breakout | 34 | 10d..13d | Stable(0.0002) | （limited / none 邊界） | label != Calibrated |
| `test_r6t8_bb_reversion_reproducibility` | bb_reversion | 7 | 1d..3d | Stable(0.0002) | None | ttl=zero |

每 test 構同 fixture 跑兩次，呼叫 `assert_calibration_eq(&r1, &r2)` 對 9 欄做字節級比對。

實際 runtime 結果（cargo test 顯示）—— 所有 5 reproducibility test PASS，confirms label stable per QC §1.1 預期：
- grid_trading 1162 → Calibrated（ttl=7d, MAD=0）
- ma_crossover 635 + bimodal → Limited 或 Calibrated（spec 容許）
- funding_arb 99 → Limited 或 None（n<200 強制非 calibrated）
- bb_breakout 34 + 10d age → Limited 或 None（n<200, age<14d）
- bb_reversion 7 → None（n<30 強制）

## §2 — `build_fixture` helper 設計

新加 helper（`#[cfg(test)] mod tests` 內，不污染 production surface）：

```rust
enum FeePattern {
    Stable(f64),                  // 全 fill 同 fee_rate
    Bimodal(f64, f64),            // 偶數 idx maker / 奇數 idx taker
}

fn build_fixture(
    now: DateTime<Utc>,
    n: usize,
    last_fill_age_days: f64,      // 最新 fill 距 now（最小 age）
    oldest_fill_age_days: f64,    // 最舊 fill 距 now（最大 age）
    fee_pattern: &FeePattern,
    entry: f64,
    exit_offset: f64,
) -> Vec<FillRecord>
```

**Deterministic 設計**（無 RNG）：
- age 線性插值於 `[oldest, last]` 端點：`age_i = oldest + (last - oldest) * i / (n-1)`
- fee_pattern = `Stable(rate)` 全等；`Bimodal(maker, taker)` 用 `i % 2` 雙模分配
- entry_price 恆定，exit_price = entry + exit_offset
- 同參數兩次呼叫 → 兩 `Vec<FillRecord>` byte-equal（無 hash / 無 RNG / 無 system clock 依賴 —— `now` 經參數注入）

LOC：~50 行（含 enum + fn + helper 共用）。

## §3 — Determinism 設計與不變式

**「reproducibility」= 純函數契約**：`derive_execution_confidence(fills, now) -> CalibrationResult` 是 stateless 純函數，不依 RNG / clock / mutable global / I/O；輸入決定輸出。

**測試方式**：
- 同 input 構造兩次 → `derive_*` 跑兩次 → `assert_calibration_eq` 比 9 field
- `assert_calibration_eq` 對 NaN 用 `f64::to_bits()` bit-level 等同（繞過 NaN != NaN）
- grid_trading test 額外連跑 3 次（r1 / r2 / r3）三方互比

**未引 RNG seed**：刻意；本函數不使用 RNG（empirical percentile / MAD / IQR / TTL 全 deterministic 算術）。Reproducibility = 函數 deterministic property，與 RNG 無關。PA dispatch §2.5 提到「fixed RNG seed」設想針對「fee_rate distribution generation」—— 本 IMPL 改用 `Stable / Bimodal` deterministic pattern 取代 RNG distribution，效果等同（無 RNG → 必 reproducible）且更簡。

## §4 — Mac cargo test 結果

### Baseline（本 W5 改動前）
```
running 19 tests
test result: ok. 19 passed; 0 failed; 0 ignored; 0 measured; 2490 filtered out; finished in 0.00s
```

### W5 改動後（5 R6-T8 test 加入）
```
running 24 tests
test replay::calibration_label::tests::test_r6t8_grid_trading_reproducibility ... ok
test replay::calibration_label::tests::test_r6t8_ma_crossover_reproducibility ... ok
test replay::calibration_label::tests::test_r6t8_funding_arb_reproducibility ... ok
test replay::calibration_label::tests::test_r6t8_bb_breakout_reproducibility ... ok
test replay::calibration_label::tests::test_r6t8_bb_reversion_reproducibility ... ok
（含 19 baseline test）
test result: ok. 24 passed; 0 failed; 0 ignored; 0 measured; 2490 filtered out; finished in 0.00s
```

### Full lib regression
```
test result: ok. 2514 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.55s
```

從 PA dispatch §1 預期 (2509 → 2514) 完全對齊。

## §5 — LOC compliance

- `calibration_label.rs`：826 → 1096（+270 LOC，純 `#[cfg(test)] mod tests` 擴充）
- 新增結構：5 reproducibility test（~210 LOC）+ `assert_calibration_eq` helper（~30 LOC）+ `FeePattern` enum + `build_fixture` helper（~50 LOC）
- 文件 LOC 1096 < 2000 hard cap（CLAUDE.md §九 governance change 1500→2000，2026-05-05）
- 警告線 800：本檔 baseline 826 已破（pre-existing），本 W5 純 test mod 擴充未影響 production hot-path 行
- production surface 0 改動（純擴 `#[cfg(test)]` block）

## §6 — git status / forbidden surface check

```bash
$ git status --porcelain
 M rust/openclaw_engine/src/replay/calibration_label.rs

$ git diff --stat HEAD
.../src/replay/calibration_label.rs | 270 +++++++++++++++++++++
1 file changed, 270 insertions(+)

$ grep -nE "paper_state|canary_writer|ipc_server|governance_hub|live_authorization|decision_lease" calibration_label.rs
58://!     - 0 引用 `paper_state` / `canary_writer` / `database` /
59://!       `ipc_server` / `governance_hub` / `live_authorization` /
60://!       `decision_lease` / `bybit_*` / `intent_processor::router`。
（僅 MODULE_NOTE 文字提及，0 use ::path 真實引用）

$ grep -nE "/home/ncyu|/Users/[^/]+" calibration_label.rs
（無命中）
```

- forbidden surface：0 真實 use ::path 引用（V3 §6.2 forbidden_surface_audit 必綠）
- cross-platform path：0 命中（CLAUDE.md §七 跨平台合規）
- 0 V### migration / 0 PG schema 改動 / 0 manifest_signer canonical_bytes 改動 / xlang_consistency 13/13 不破
- bilingual MODULE_NOTE：default 中文（per 2026-05-05 governance commit `47922a4c`）；新增 R6-T8 註解全中文

## §7 — 待 PM commit + Linux verify + W6

E1 W5 IMPL DONE。等 PM:

1. **Commit + push**：純測試擴充（PA dispatch §3「skip E2 per minimal-loop pattern」）
2. **Linux verify**：`ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && cd rust && cargo test --release --features replay_isolated -p openclaw_engine --lib calibration_label"` 驗 24 PASS
3. **R6 W5 closed → W6 R6-T9 final review**（E2/E4 + Sprint C1 closure）

## §8 — 不確定之處

1. **PA dispatch §2.5 fixed RNG seed**：dispatch 文字提到「設 fixed RNG seed for fee_rate distribution generation」—— 本 IMPL 因 `derive_execution_confidence` 不引 RNG，採 deterministic `Stable / Bimodal` pattern 取代 RNG seed，效果等同（無 RNG → 函數本身已 deterministic）。若 PM 期望不同實作（例如顯式調用 `rand::SeedableRng`），請通知 retrofit。建議：本 deterministic pattern 更簡潔、無 `rand` 依賴、reproducibility 證更直接。
2. **bb_breakout 預期 label**：QC §1.1 表寫「none or limited」；本 test 用 freshness 10d + n=34 → 結果 Limited（age ≤ 14d + MAD=0 + n ≥ 30）。assert 用 `!= Calibrated`（容許 None or Limited），與 spec 容許範圍一致。
3. **funding_arb 預期 label**：QC §1.1 表寫「none (n<200 OR stale freshness)」；本 test fixture freshness OK + MAD=0 → 走 Limited 路徑（n=99 ≥ 30 + age 1-5d ≤ 14d + MAD=0 < 8）。assert 容許 `Limited or None`（PA dispatch §2.3 funding_arb 段亦允「若 freshness OK + MAD OK 可進 limited」）。

## §9 — Operator 下一步

E1 W5 SIGN-OFF 完成；交 PM：
- review 本 report
- commit + push（建議 message：`test(ref20): Sprint C R6 W5 — R6-T8 5-strategy reproducibility smoke (calibration_label)`）
- Linux pull + cargo test 驗 24/24 PASS
- 若 PASS → R6 W6 派發 R6-T9 (E2/E4 final review + C1 closure)；本 W5 純 test 擴充 + PA dispatch 已 skip E2，W6 final review 仍跑 E2 +E4 對 R6 整體 (W1-W5 累積) 把關

---

E1 W5 IMPLEMENTATION DONE: 待 PM commit + Linux verify (report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_w5_impl.md`)

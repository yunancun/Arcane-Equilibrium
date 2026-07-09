# W1-C M4 Pattern Miner Stage 1 — Rust+Python Hybrid IMPL Scaffold

**Date**: 2026-05-25
**Role**: E1 (Backend Developer)
**Phase**: v5.8 Sprint 2 Stream B Wave 1 W1-B (MIT spec) → **W1-C (E1 IMPL)** scaffold
**Parent spec**: `srv/docs/execution_plan/2026-05-25--m4_pattern_miner_stage_1_algorithm_spec.md` (907 lines, commit `7eab15e0`)
**Status**: IMPL DONE — awaiting E2 cold review (per chain E1→E2→E4→QA→PM)

---

## 1. 任務摘要

接 W1-B MIT algorithm spec 為 dispatch packet，IMPL M4 Pattern Miner Stage 1 的 Rust crate sub-module + Python helper + DRAFT writeback contract（V100 base + V103 EXTEND 6 column）。

**5 hard invariant 必守**（per W1-B spec §0）：
- I-1 rolling stat 強制 `.shift(1)` leak-free（per memory `feedback_indicator_lookahead_bias` 2026-04-24 P1-11 F3 RETRACT）
- I-2 黑名單 method 禁用：HMM / Markov-switching / GARCH（per ADR-0036）
- I-3 Bonferroni K_total=2500，α_corrected=2e-5
- I-4 Event-window N≥30 硬 gate
- I-5 DRAFT writeback ≠ live order，不 auto-promote past 'preregistered'（per 16 原則 #7 + AMD-2026-05-21-01 protected scope (a)）

**Scope**: scaffold 階段 IMPL — algorithm correctness + invariant verify + unit test。Cron wire-up + 真實 PG INSERT 由 Sprint 2 末 W2-D MIT 接續，default disabled。

---

## 2. 修改清單

### 2.1 新建 file（Rust sub-module 8 file, 1511 LOC）

| File | LOC | Purpose |
|---|---|---|
| `rust/openclaw_core/src/m4_miner/mod.rs` | 54 | Public API + module re-exports + hardware constraint NOTE |
| `rust/openclaw_core/src/m4_miner/types.rs` | 290 | PatternDraft / StatisticalResult / EventWindowResult / ForwardWindow / EventType enum |
| `rust/openclaw_core/src/m4_miner/feature_engineering.rs` | 262 | `shift1_rolling_mean` / `shift1_rolling_std` / `shift1_rolling_pct_change` + `validate_leak_free_pattern` |
| `rust/openclaw_core/src/m4_miner/cross_correlation.rs` | 248 | Pearson / Spearman + `rolling_pearson_corr` + `corr_to_p_value` (A&S 7.1.26 erf approx) |
| `rust/openclaw_core/src/m4_miner/event_window.rs` | 344 | 3 detector (funding_flip / liquidation_cascade / large_funding_spike) + `event_window_forward_shift` + `event_window_sample_gate` |
| `rust/openclaw_core/src/m4_miner/bonferroni.rs` | 103 | `BONFERRONI_K_TOTAL = 2500` const + `ALPHA_CORRECTED` + `correct_p_value` + `is_significant_after_correction` |
| `rust/openclaw_core/src/m4_miner/tick_window.rs` | 210 | `TickWindowAggregator` O(1) Kahan-compensated sliding window mean/std |

### 2.2 新建 file（Python helper_scripts/m4/ 14 file, ~1900 LOC）

| File | LOC | Purpose |
|---|---|---|
| `helper_scripts/m4/__init__.py` | 26 | MODULE_NOTE + invariant 概述 |
| `helper_scripts/m4/pattern_miner_stage_1.py` | 154 | 主 entry (cron callable) + `--dry-run` CLI |
| `helper_scripts/m4/attribute_enforcer.py` | 77 | 6 attribute gate + `determine_hypothesis_status` + `is_promotable` |
| `helper_scripts/m4/draft_writer.py` | 199 | V103 EXTEND DRAFT INSERT SQL + `DraftWritebackPayload` + `GovernanceHubInterface` (stub) |
| `helper_scripts/m4/feature_engineering_validator.py` | 156 | `is_leaky_sql` / `is_leaky_pandas` regex + `validate_shift1_pattern` + pure Python shift(1) rolling |
| `helper_scripts/m4/sources/__init__.py` | 10 | |
| `helper_scripts/m4/sources/kline_loader.py` | 85 | market.klines SQL + freshness gate |
| `helper_scripts/m4/sources/fills_loader.py` | 62 | trading.fills SQL with `engine_mode IN ('live','live_demo')` filter + `is_engine_mode_valid` |
| `helper_scripts/m4/sources/liquidations_loader.py` | 54 | market.liquidations SQL + self-fill 5s filter |
| `helper_scripts/m4/sources/funding_loader.py` | 35 | market.funding_rates SQL |
| `helper_scripts/m4/sources/token_unlocks_stub.py` | 39 | Sprint 3+ stub raising `TokenUnlocksNotImplementedError` |
| `helper_scripts/m4/algorithms/__init__.py` | 8 | |
| `helper_scripts/m4/algorithms/bonferroni.py` | 45 | `BONFERRONI_K_TOTAL = 2500` (Python SSOT 對齊 Rust) |
| `helper_scripts/m4/algorithms/cross_correlation.py` | 124 | Pearson / Spearman / `rolling_pearson_corr` / `corr_to_p_value` (對齊 Rust) |
| `helper_scripts/m4/algorithms/event_window.py` | 119 | 3 detector + `event_window_forward_shift` + `event_window_sample_gate` (對齊 Rust) |
| `helper_scripts/m4/algorithms/effect_size.py` | 51 | `cohens_d` + `passes_cohens_d_gate` |
| `helper_scripts/m4/tests/__init__.py` | 1 | |
| `helper_scripts/m4/tests/test_m4_leakage_regression.py` | 677 | 51 pytest cases — leakage regression + Bonferroni + cross-correlation + event-window + attribute enforcer + writeback contract |
| `helper_scripts/m4/fixtures/README.md` | 4 | Reserved 目錄供 W2-D MIT fixture parquet |

### 2.3 修改 existing file（1 file，1 處改動）

| File | 改動 | Purpose |
|---|---|---|
| `rust/openclaw_core/src/lib.rs` | 註冊 `pub mod m4_miner` (含 1 段 6 行 MODULE_NOTE 中文) | 將新 sub-module 接入 openclaw_core crate |

**0 existing module logic 改動** — 所有改動為 additive。

---

## 3. 關鍵 diff（核心 invariant 編碼點）

### 3.1 I-3 Bonferroni K=2500 hard-coded（Rust）

```rust
// rust/openclaw_core/src/m4_miner/bonferroni.rs
pub const BONFERRONI_K_TOTAL: usize = 2500;
pub const ALPHA_CORRECTED: f64 = 0.05 / BONFERRONI_K_TOTAL as f64;

pub fn is_significant_after_correction(raw_p: f64) -> bool {
    // Bonferroni K=2500 — 不可改為 0.05 / 100 或其他 K（per W1-B spec §0 I-3）。
    raw_p < ALPHA_CORRECTED
}
```

### 3.2 I-1 shift(1) leak-free 命名強制（Rust）

```rust
// rust/openclaw_core/src/m4_miner/feature_engineering.rs
pub fn shift1_rolling_mean(values: &[f64], window: usize) -> Vec<Option<f64>> {
    // ... for i in 0..values.len():
        if i < window {
            out.push(None);  // 樣本不足 fail-closed
        } else {
            let slice = &values[i - window..i]; // 不含 values[i] 本身 — 即 shift(1)。
            // ...
        }
    // ...
}
```

### 3.3 I-5 不 auto-promote past 'preregistered'（Rust + Python 雙端）

```rust
// rust/openclaw_core/src/m4_miner/types.rs
impl PatternDraft {
    pub fn new(..., status_candidate: String, ...) -> Result<Self, String> {
        match status_candidate.as_str() {
            "draft" | "exploratory" | "preregistered" => {}
            other => return Err(format!(
                "PatternDraft.status_candidate 非法值 '{}'...",
                other
            )),
        }
        // ...
    }
}
```

```python
# helper_scripts/m4/draft_writer.py
def build_writeback_payload(...status_candidate: str, decision_lease_draft_id: Optional[uuid.UUID] = None, ...):
    if status_candidate not in ("draft", "exploratory", "preregistered"):
        raise ValueError(
            f"M4 DRAFT writeback 不能 promote past 'preregistered'，"
            f"got status_candidate='{status_candidate}'"
        )
    if decision_lease_draft_id is None:
        raise ValueError(
            "decision_lease_draft_id 必 non-NULL — Lease backref 是 audit chain 必要條件"
        )
```

### 3.4 engine_mode IN ('live','live_demo') 強制（Python SQL）

```python
# helper_scripts/m4/sources/fills_loader.py
FILLS_QUERY_SQL: str = """
SELECT ...
FROM trading.fills
WHERE engine_mode IN ('live', 'live_demo')  -- 不可單獨 ='live'
  AND ts >= now() - %(lookback)s::INTERVAL
  AND close_fill = TRUE
ORDER BY symbol, strategy_name, ts
"""
```

---

## 4. 治理對照（W1-B spec § 對照表）

| W1-B spec § | 編碼點 | Status |
|---|---|---|
| §1.1 kline source 24h freshness gate | `kline_loader.is_stale` | DONE |
| §1.2 trading.fills `engine_mode IN ('live','live_demo')` | `fills_loader.FILLS_QUERY_SQL` SQL hard-code | DONE |
| §1.3 liquidations self-fill filter 5s | `liquidations_loader` LEFT JOIN ... IS NULL | DONE |
| §1.4 funding_rates | `funding_loader` | DONE |
| §1.5 token unlocks Sprint 3+ stub | `token_unlocks_stub.TokenUnlocksNotImplementedError` | DONE (fail-loud raise) |
| §2.1 Pearson + rolling shift(1) | `cross_correlation::pearson_corr` + `rolling_pearson_corr` | DONE |
| §2.1 Spearman | `cross_correlation::spearman_corr` | DONE |
| §2.2 3 event detector | `event_window::{detect_funding_flip,detect_liquidation_cascade,detect_large_funding_spike}_events` | DONE |
| §2.2.2 pre/post window forward shift 排除 event bar | `event_window_forward_shift` | DONE |
| §2.2.3 N>=30 硬 gate | `event_window_sample_gate` | DONE |
| §2.2.4 merge close events | `merge_close_events` | DONE |
| §2.3 黑名單 HMM/Markov/GARCH | 5 對抗 grep 0 production hit | DONE |
| §3.1 6 attribute 計算 | `attribute_enforcer.determine_hypothesis_status` | DONE |
| §3.2 hypothesis_status verdict | preregistered / exploratory return path | DONE |
| §3.3 leakage scan | `feature_engineering_validator.validate_shift1_pattern` | DONE (smoke + sanity) |
| §4.1 INSERT contract | `draft_writer.DRAFT_INSERT_SQL` | DONE |
| §4.2 V103 EXTEND 6 column mapping | `DraftWritebackPayload` + payload_to_params | DONE |
| §4.3 replicability_score formula stub | Sprint 2 baseline 簡化（Q3 待 QC review） | PARTIAL |
| §5.1 Rust m4_miner module placement | `rust/openclaw_core/src/m4_miner/` 8 file | DONE |
| §5.2 Python helper_scripts/m4 placement | `helper_scripts/m4/` 14 file | DONE |
| §5.3 cross-language 1e-4 對齊 | Python pure vs pandas-mimic 對齊 test pass | PARTIAL (Rust 對齊由 W2-D MIT fixture 跑) |
| AC-S2-B-1 5 source 4 接通 + 1 stub | dry-run 4 source query built + stub raise | DONE |
| AC-S2-B-2 5 sub-algorithm IMPL DONE | cross-corr × 2 + event-window × 3 都實裝 | DONE |
| AC-S2-B-3 leak-free regression test | `test_rolling_corr_shift1_vs_leak_pump_dump_pattern` + 4 個 leak/clean SQL regex test | DONE |
| AC-S2-B-4 30 event N gate | `event_window_sample_gate` + `determine_hypothesis_status` | DONE |
| AC-S2-B-5 V103 EXTEND DRAFT writeback 6 attribute | `DraftWritebackPayload` + `payload_to_params` 必填 13 字段驗 | DONE |

---

## 5. Mac SSOT Verify

### 5.1 cargo test -p openclaw_core --lib

```
test result: ok. 416 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

含 m4_miner 46 test：
- bonferroni::* 5 tests
- cross_correlation::* 9 tests
- event_window::* 11 tests
- feature_engineering::* 7 tests
- tick_window::* 7 tests
- types::* 5 tests
- 加 mod.rs 內 doc + module re-export 隱含 verify

### 5.2 pytest helper_scripts/m4/

```
============================== 51 passed in 0.02s ==============================
```

包含類別：
- 8 leak-free shift(1) regression（含 P1-11 F3 RETRACT 教訓 test）
- 4 SQL / pandas pattern regex test
- 4 Bonferroni K=2500 test
- 6 cross-correlation Pearson / Spearman test
- 9 event-window 3 detector + forward shift + sample gate + merge test
- 3 Cohen's d effect size test
- 9 attribute enforcer 6 attribute gate test
- 3 source loader (engine_mode whitelist + freshness + token unlocks stub raise)
- 7 DRAFT writeback contract test（含 reject live status + reject missing lease + INSERT SQL 必含 'M4_AUTO' 字符串）

### 5.3 主 entry dry-run smoke

```
$ python3 -m helper_scripts.m4.pattern_miner_stage_1 --dry-run --symbols BTCUSDT,ETHUSDT --lookback-days 30 -v
M4 Stage 1 start: dry_run=True symbols=('BTCUSDT', 'ETHUSDT') lookback=30d
Source query built: 4 PG queries (kline/fills/liquidations/funding) + 1 stub (token_unlocks)
token_unlocks stub correctly raised NotImplementedError (Sprint 3+ defer)
M4 Stage 1 complete: {'n_source_queries_built': 4, 'n_source_stubs': 1, ...}
```

### 5.4 Pre-existing baseline failure 確認

`openclaw_engine::layer_2_fence_archive_policy_diagnostic_only` 1 test failed —  與本改動完全無關（驗 `git stash` 後仍 fail）。屬於 baseline 既存問題，不在 W1-C scope。

---

## 6. 5 對抗式 grep 自驗（W1-B spec §9）

| Grep | 結果 | 驗證 |
|---|---|---|
| 1: rolling 沒 shift(1) | Python hit 2 處全在 test fixture 標 leaky/clean 對照；Rust hit 全在 `shift1_rolling_*` 命名函式內 + comment | PASS |
| 2: HMM/Markov/GARCH 黑名單 | 0 production import；4 處 hit 全在 comment 標「禁用」 | PASS |
| 3: K_TOTAL / BONFERRONI_K | Rust `BONFERRONI_K_TOTAL=2500` 常數 + Python 同；`ALPHA_CORRECTED=2e-5` 對齊 | PASS |
| 4: engine_mode IN ('live','live_demo') | 0 單獨 `='live'`；fills_loader SQL 強制 IN 形式 | PASS |
| 5: state='live' / promote past | 雙端白名單 reject test pass | PASS |

---

## 7. 設計決策 + 與 spec 偏離

### 7.1 不引 polars / sqlx / rayon / statrs（W1-B spec §5.1 列為 dep）

**原因**：scaffold 階段 keep dep clean。
- polars hot-path optimization 推遲到 Sprint 3 cron wire-up 後 benchmark-driven 評估
- sqlx PG query 留給 Python 端（spec 也說 `DRAFT writeback 在 Python 端`）
- rayon 平行化推遲到 batch >= 1M row 後評估
- statrs 經典 stat 函數（erf approx / t-distribution）已用 Abramowitz & Stegun 7.1.26 manual 實裝，精度 < 1.5e-7 過 1e-4 對齊要求

**影響**：Rust crate dep 改動 = 0；build cost 0；cargo test compile 時間不變。

### 7.2 不引 PyO3 binding

**原因**：scaffold 階段 Rust + Python 各自獨立實裝同算法 — 兩端 SSOT 對齊由 unit test + 跨語言 fixture 1e-4 對齊 verify。
- Rust 算法是 type-safe + fast verify path
- Python 算法是 production cron 主路徑（per W1-B spec §5.2「不直接寫 rolling stat 走 Rust binding」原意是 hot-path 1M+ row 才需要）
- Sprint 3 接 cron + 1M+ row 真實 batch 時可加 PyO3，無 ABI break

### 7.3 GovernanceHubInterface 是 stub

**原因**：Mac scaffold 階段不能呼 Linux runtime GovernanceHub IPC（per CLAUDE.md §六）。
- `LEASE_TYPE = 'M4_DRAFT_WRITEBACK'` 常數已定 + test 驗
- `DEFAULT_LEASE_TTL_SECONDS = 300` (5 min) 已定 + test 驗
- 真實 ai_service.py JSON-RPC over Unix domain socket 接通由 Sprint 3 W2-D MIT IMPL（per W1-B spec §12 dispatch readiness checklist）

### 7.4 replicability_score formula partial（W1-B spec §4.3 Open Q3 待 QC review）

**原因**：spec line 488 "QC review pending: formula coefficients 0.3/0.4/0.3 是 baseline"。
- scaffold 階段 `replicability_score` 字段在 DraftWritebackPayload 提供 Optional 通道（None / 0.0-1.0 都接受）
- 真實 formula 計算由 Sprint 3 cron 接通時 + QC 仲裁 baseline coefficients 後填入

---

## 8. 不確定之處 / Sprint 3 follow-up（不阻 W1-C closure）

1. **W1-B §7 PG empirical verify SQL** — V100 base + V103 EXTEND 6 column reflection + 4 source freshness verify SQL 由主會話 ssh trade-core 跑（Mac scaffold 不執行，per `feedback_v_migration_pg_dry_run`）。
2. **GovernanceHub `M4_DRAFT_WRITEBACK` lease type 真實註冊** — 走 ai_service.py IPC，Sprint 3 W2-D MIT IMPL 接通時驗。
3. **Cron schedule wire-up** — Sprint 2 末週 land (default disabled) per W1-B spec §12。
4. **Cross-language 1e-4 對齊 fixture parquet** — `srv/tests/test_m4_cross_language_fixture.py` 由 Sprint 2 末 W2-D MIT 接 cron 後跑（per spec §5.3）。
5. **Bonferroni K_hyp = 500 empirical reflection** — Sprint 2 IMPL 第一週 cron 跑後收集 empirical K_hyp，Sprint 3 PA + MIT + QC 三角仲裁（per spec Open Q1）。

---

## 9. Operator 下一步

1. **主會話派 E2 cold review**：
   - W1-B spec §9 5 對抗 grep 重跑（建議 grep 帶 `--include='*.rs' --include='*.py'` 雙端）
   - V103 EXTEND 6 column mapping vs `DRAFT_INSERT_SQL` SQL string 對齊驗
   - Rust m4_miner / Python helper_scripts/m4 中文註釋規範（per `feedback_chinese_only_comments`）
   - 文件數 + LOC 與 800/2000 line cap 對照（最大 file `event_window.rs` 344 LOC，未超）

2. **主會話派 E4 regression**：
   - `cargo test --workspace --release -p openclaw_core` Mac SSOT 跑（per M-4 hygiene 禁 trade-core）
   - `pytest helper_scripts/m4/tests/ -v` 全套
   - 既有 pre-existing baseline failure (engine layer_2_fence_archive_policy) 驗未引新 regression

3. **主會話派 QA / W2-F MIT post-IMPL audit**：
   - W1-B spec §9 5 對抗 grep 雙端驗
   - 16 root principles compliance（per spec §11.6 #1/#3/#6/#7/#8/#10/#11/#12）
   - V103 EXTEND 6 column INSERT 必填字段 100% verify

4. **PA 補 PG empirical verify**（W1-B §7）— 主會話 ssh trade-core 跑 5 reflection SQL：
   - V100 base table 存在性
   - V103 EXTEND 6 column 存在性 + DEFAULT 對齊
   - 3 hot-path index 存在性
   - 4 source table freshness（24h kline / 6h fills / 1h liquidations / 12h funding）
   - GovernanceHub `acquire_lease(lease_type='M4_DRAFT_WRITEBACK', ...)` 接口可呼

5. **PM commit + push**（per chain E1→E2→E4→QA→PM）：
   - feat(m4-stage-1): Rust+Python hybrid pattern miner scaffold + DRAFT writeback V103
   - 不 commit until E2 + E4 + QA closure

---

**E1 IMPL DONE** — 待 E2 cold review；report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--w1c_m4_pattern_miner_stage_1_scaffold.md`

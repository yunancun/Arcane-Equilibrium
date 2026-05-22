# E1 Sprint 1B Early IMPL #4 — AC-7 cross-language Rust binding 最小版 · 2026-05-22

## 0. TL;DR

**IMPL DONE** — AC-7 spec §AC-7 字面要求 Rust ↔ Python 1e-4 容差對齊 `engine_cpu_pct` 5 sample window mean / sigma：
- Rust 端新增 `compute_window_stats()` helper（`#[cfg(any(test, feature = "spike"))]` 隔絕；0 production code path 污染）
- Rust 端新整合 test `tests/m3_cross_lang_window_fixture.rs`（`#![cfg(feature = "spike")]` gate；輸出 `RUST_FIXTURE_JSON` marker）
- Python 端新 test `tests/test_spike_cross_lang_rust_binding.py`（subprocess + JSON marker parse）
- Cross-lang diff 實測：mean diff = **0.0** / sigma diff = **0.0**（bit-perfect；同源 two-pass 算法 IEEE 754 deterministic）；遠遠 <1e-4 tolerance
- AC-7 verdict：**PARTIAL PASS (PoC) → FULL PASS**

## 1. Design choice — Option A vs Option B

Per dispatch packet §Step 1 兩條技術路線：

| 維度 | Option A (subprocess + JSON) | Option B (PyO3 binding) |
|---|---|---|
| 新 dep | 0 | maturin + pyo3 crate |
| Build chain 複雜度 | 0 (純 cargo + python) | 高 (.so build + import 路徑) |
| Spike scope 「最小 binding」契合 | ✅ | ❌ (屬 H-18 全套範圍) |
| 跨平台 (Mac / Linux) | 自然支援 | 需平台特化 maturin build |
| Runtime overhead | 高 (subprocess + cargo) | 低 (in-process call) |
| Sprint 1B 2-3 hr 預算 | ✅ 符合 | ❌ 通常 1-2 day |

**選 Option A**。Option B 屬 Sprint 2+ carry-over per spec §5.3 H-18「全套 cross-language fixture harness」。

決策依據：
- Phase 3b E4 報告 §5.4 已預期 Sprint 1B 「Rust binding 對驗」分兩步：先 algorithm contract（Phase 3b done），後 Rust ↔ Python 1e-4 對齊（本 task）。Option A 是最小可驗 binding。
- spike PoC 階段 runtime overhead 不是 gate，正確性才是。subprocess + JSON 是業界標準 cross-language 對齊路徑（簡單、零 build chain 改動、輸出可審計）。

## 2. Rust IMPL

### 2.1 Helper `compute_window_stats` (mod.rs)

| 位置 | LOC 增量 |
|---|---|
| `srv/rust/openclaw_engine/src/health/mod.rs` (行 471 附近) | +37 LOC (含 doc 注釋) |

```rust
#[cfg(any(test, feature = "spike"))]
pub fn compute_window_stats(samples: &[f64]) -> Option<(f64, f64)> {
    let n = samples.len();
    if n < 2 {
        return None;  // ddof=1 要求 N-1 > 0
    }
    let n_f = n as f64;
    let mean = samples.iter().sum::<f64>() / n_f;
    let variance = samples.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (n_f - 1.0);
    Some((mean, variance.sqrt()))
}
```

設計選擇：
- **two-pass 而非 Welford**：Phase 3b PoC 已證 naive two-pass / Welford / numpy 三者 1e-4 內等價；spike 階段 two-pass 簡單、易讀、與 Python `python_naive_mean_sigma` 1:1 對齊。Sprint 5+ 接 hot-path 真實 health writer 時可換 Welford incremental update。
- **`#[cfg(any(test, feature = "spike"))]` gate**：production build (cargo build --release 不帶 spike) 完全不編譯本 helper；0 production code path 污染（per Phase 3b E4 報告 §6 規範與 `amp_cap_entry_count` 同 gate 模式）。
- **`Option<(f64, f64)>` 而非 `Result`**：fail-closed 對 caller 端友善（N<2 直接 None，caller pattern match 即可）；不引入新 error variant。
- **`Option<...>` semantics**：N<2 → None (`amp_cap_24h_count` 同模式)；任何 NaN/Inf 自然 propagate（caller 決定如何處理）。

### 2.2 Unit test (mod.rs `mod tests`)

3 個新 unit test：
- `test_compute_window_stats_spec_sample` — spec §AC-7 sample `[10, 20, 30, 25, 15]`，mean=20.0 / sigma=sqrt(62.5)
- `test_compute_window_stats_constant_edge_case` — 5 個相同 sample，variance=0 / sigma=0
- `test_compute_window_stats_insufficient_samples` — N=0/1 → None；N=2 → mean=15 / sigma=sqrt(50)

| 維度 | LOC 增量 |
|---|---|
| `mod tests` (行 678-720 附近) | +43 LOC |

cargo test 結果：
```
test health::tests::test_compute_window_stats_constant_edge_case ... ok
test health::tests::test_compute_window_stats_insufficient_samples ... ok
test health::tests::test_compute_window_stats_spec_sample ... ok

test result: ok. 3 passed; 0 failed
```

### 2.3 Integration test (`tests/m3_cross_lang_window_fixture.rs`)

新檔，比照 `tests/m3_amp_cap_24h_fire.rs` 模式：

| 維度 | LOC |
|---|---|
| 檔案 LOC | 70 |
| Test 函數 | 1 (`test_window_stats_fixture_json`) |

關鍵 output：
```
RUST_FIXTURE_JSON: {"mean": 20, "sigma": 7.905694150420948}
```

注意 Rust f64 Display 對整數值省 `.0`（`20` 而非 `20.0`）；JSON spec 允許，Python `json.loads` parse 為 `int`，Python 端用 `float(raw["mean"])` cast。

cargo test 結果：
```
running 1 test
test test_window_stats_fixture_json ... ok

test result: ok. 1 passed; 0 failed
```

## 3. Python IMPL — Cross-lang binding

### 3.1 新檔 `tests/test_spike_cross_lang_rust_binding.py`

| 維度 | LOC |
|---|---|
| 檔案 LOC | 165 (含 MODULE_NOTE + 5 test) |
| Test 數 | 5 (mean / sigma / combined / parametric mean / parametric sigma) |

關鍵設計：
- **`_srv_root()` 走 `Path(__file__).resolve().parents[1]`**：跨平台合規，不硬編 `/Users/ncyu/...` 或 `/home/ncyu/...`（per E1 hard constraint 與 §六 跨平台部署目標）
- **`subprocess.run` 帶 `timeout=300`**：防 cargo cold-build 超時
- **`re.search(r"RUST_FIXTURE_JSON: (\{[^}]+\})", stdout)`**：精確抓 marker，non-greedy + 限定 brace pair
- **`float(raw["mean"])` cast**：處理 Rust f64 Display 整數值省 `.0` 邊角

5 個 test 結果：
```
tests/test_spike_cross_lang_rust_binding.py::test_rust_python_cross_lang_fixture_mean_1e_4 PASSED [ 20%]
tests/test_spike_cross_lang_rust_binding.py::test_rust_python_cross_lang_fixture_sigma_1e_4 PASSED [ 40%]
tests/test_spike_cross_lang_rust_binding.py::test_rust_python_cross_lang_fixture_combined PASSED [ 60%]
tests/test_spike_cross_lang_rust_binding.py::test_rust_python_cross_lang_fixture_parametric[mean-20.0] PASSED [ 80%]
tests/test_spike_cross_lang_rust_binding.py::test_rust_python_cross_lang_fixture_parametric[sigma-7.905694150420948] PASSED [100%]

============================== 5 passed in 31.29s ==============================
```

## 4. Cross-lang 1e-4 verify result

### 4.1 數值對齊實證

| 維度 | Rust 端 | Python 端 expected | diff | 容差 | 結論 |
|---|---|---|---|---|---|
| mean | `20.0` | `20.0` | **0.00e+00** | 1e-04 | ✅ FULL PASS |
| sigma (ddof=1) | `7.905694150420948` | `7.905694150420948` | **0.00e+00** | 1e-04 | ✅ FULL PASS |

實證來源：直接呼 cargo test + Python parse JSON 對齊。Rust f64 sum + variance 計算與 Python `python_naive_mean_sigma()` 同 two-pass 算法 + 同 input，IEEE 754 deterministic → bit-perfect 0 diff。

### 4.2 為什麼 0 diff（非「巧合」）

- 同 input `[10.0, 20.0, 30.0, 25.0, 15.0]`（exact 表示 in f64）
- 同 algorithm：`mean = sum/n`，`var = sum((x-mean)^2)/(n-1)`
- Python 與 Rust 都用 IEEE 754 double 算術 + 相同求和順序（從 left to right iteration）
- 雖然浮點 sum 不滿足結合律，但同順序 sum + 同算法 → bit-perfect 一致

如果未來 Sprint 5 Rust 端改 Welford incremental，diff 可能 ~1e-15（floating-point round-off），仍遠 <1e-4 容差。

## 5. Regression — cargo test 全 PASS

| Test 集 | Pass / Fail |
|---|---|
| `cargo test --release --lib health::` (新 helper unit + 既有 12) | **15 / 0** |
| `cargo test --release --features spike --test m3_amp_cap_24h_fire` (regression spike integration) | **3 / 0** |
| `cargo test --release --features spike --test m3_cross_lang_window_fixture` (新 cross-lang integration) | **1 / 0** |
| `python3 -m pytest tests/test_spike_cross_lang_rust_binding.py` | **5 / 0** |

`cargo check --release`（**production build 無 spike**）：clean 0 error / 1 pre-existing dead_code warn (`spawn_position_reconciler`，與 spike 0 觸碰，per Phase 3b E4 §1.5)。

## 6. AC-7 closure

### 6.1 PARTIAL PASS → FULL PASS verdict

Phase 3b E4 報告 §4 line 141 AC-7 結論：
> **PARTIAL PASS** (PoC; Rust binding 未驗)

Sprint 1B 補對齊後：
> **FULL PASS** — Rust binding 真實對齊 Python expected 1e-4 容差（實測 diff 0.0）

### 6.2 對齊 spec §AC-7

| spec literal | 實際結果 | 對齊 |
|---|---|---|
| `engine_cpu_pct` 5 sample window mean Rust ↔ Python 1e-4 | Rust mean 20.0 / Python expected 20.0 / diff 0.0 < 1e-4 | ✅ |
| `engine_cpu_pct` 5 sample window sigma Rust ↔ Python 1e-4 | Rust sigma 7.9057... / Python expected 7.9057... / diff 0.0 < 1e-4 | ✅ |

### 6.3 Sprint 2+ carry-over (per spec §5.3 H-18)

Option B (PyO3 全套 binding) 屬 H-18 「全套 cross-language fixture harness」範圍：
- in-process call (subprocess overhead 0)
- 多 fixture / multi-metric 共用 import (subprocess 每次 spawn cargo 浪費 ~5s)
- 跨平台 maturin build chain 標準化
- 為什麼延：本 spike 階段 1 fixture × 1 metric，subprocess overhead 可接受；H-18 全套手 expand fixture 數量後 PyO3 才有 ROI

## 7. 規範與 governance

| 維度 | 結果 |
|---|---|
| 0 emoji 跨 3 新檔 + 本 report | ✅ |
| 0 hardcoded path | ✅ (`Path(__file__).resolve().parents[1]` 推算 srv root) |
| 中文注釋 default | ✅ (3 新檔全中文 MODULE_NOTE + 中文 doc comment) |
| File size | ✅ mod.rs 717 < 800 warn / fixture rs 70 / py 165 全 < 800 |
| 0 production code 觸碰 | ✅ helper + 2 test 全 `#[cfg(any(test, feature = "spike"))]` 或 `#![cfg(feature = "spike")]` gate |
| 0 mock 業務邏輯 | ✅ 純算術 |
| spike feature default false invariant | ✅ `cargo check --release` (無 spike) clean |
| 不改既有 health/state machine 邏輯 | ✅ 只加 standalone helper + 新 test 檔 |
| 不引 PyO3 dep | ✅ (Sprint 2+ carry-over) |
| 不重啟 production engine | ✅ |
| 不 commit | ✅ (待 E2 審查 + E4 regression + PM 收口) |

## 8. Sub-agent / multi-session race

E1 本次 single-thread；無派下游 sub-agent；無 commit；git status dirty 預期範圍：

E1 本次新加：
- `M srv/rust/openclaw_engine/src/health/mod.rs`（+37 helper + 43 unit test = 約 +80 LOC）
- `?? srv/rust/openclaw_engine/tests/m3_cross_lang_window_fixture.rs`（70 LOC）
- `?? srv/tests/test_spike_cross_lang_rust_binding.py`（165 LOC）
- `?? srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1b_ac7_rust_binding.md`（本 report）

PM commit 範圍：上述 4 條（mod.rs M + 3 個新檔）+ memory append 1 條（E1 完成序列）。

## 9. 不確定之處 (Push back / Open question)

| # | 項目 | Notes |
|---|---|---|
| 1 | Rust f64 Display 整數值省 `.0` 行為 (`20` 而非 `20.0`) | 已在 Python `_parse_rust_json` 用 `float()` cast 處理；未來新 fixture 若 metric 期 `int` 注意此語意 |
| 2 | `cargo test` cold build 首次 ~25s, warm ~0.1s | Python test 取 warm path normally (本 IMPL 已 build) ；CI 環境第一次跑可能耗 ~30s |
| 3 | spike feature `compute_window_stats` 公開 (`pub fn`) | 與 `amp_cap_entry_count` 同模式；test 必須 `pub` 才能 cross-crate 用；production binary 不含此 fn |
| 4 | 未驗 Linux trade-core 端 | 本 IMPL Mac 端驗證；Linux release binary cross-check 屬 E4 regression scope |
| 5 | Rust integration test 無 numpy 等價對驗 | Phase 3b PoC Python 已用 naive + Welford + numpy 三者互驗；Rust 端只有 two-pass + Python ground truth；若未來 Rust 改 Welford 仍可接此 fixture 驗 |

## 10. Operator 下一步

| Action | Owner | Priority |
|---|---|---|
| E2 對抗性審查（IMPL DONE 後高風險 IPC + 共用 helper 觸發 `feedback_impl_done_adversarial_review`） | E2 | P0 |
| E4 regression（全 workspace cargo test + pytest non-flaky two passes，Mac + Linux release） | E4 | P0 (E2 PASS 後) |
| PM commit + memory append | PM | P0 (E4 PASS 後) |
| Sprint 2+ carry-over 註記 H-18 PyO3 全套 binding | PA | P3 (Sprint 2 規劃時) |

---

**E1 IMPLEMENTATION DONE**: 待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1b_ac7_rust_binding.md`）

# E1 IMPL -- WP-03 OU Sigma Estimation Fix (QC P1)

**日期**：2026-05-16
**Agent**：E1 (Backend Developer)
**任務來源**：PM WP-03 派發（QC P1）
**對應檔案**：`rust/openclaw_engine/src/strategies/grid_helpers.rs`

---

## 1. 任務摘要

修正 `compute_ou_step_with_cost_floor()` 中 line 140 的 sigma 估計。舊公式
`sqrt(sum(dx^2)/n)` 把 mean-reversion drift `theta(mu - x_{t-1})` 混入
白噪聲 innovation sigma，導致 sigma 偏高，grid spacing `sigma * sqrt(2/theta)`
過寬。新公式先用 OLS 殘差扣掉 drift，再取 n-2 自由度的標準差。

---

## 2. 修改清單

| 檔案 | LOC delta | 內容 |
|---|---|---|
| `rust/openclaw_engine/src/strategies/grid_helpers.rs` | +170 / -1 | L140: 舊 raw sigma 替換為 OLS 殘差 sigma (n-2 dof) + 5 個新 WP-03 測試 |

檔案總行數 809（超 800 警告線，低於 2000 硬上限；增量主要是測試）。

---

## 3. 關鍵 diff

### 修正（line 140 區域）
```rust
// 舊：
let sigma = (changes.iter().map(|c| c * c).sum::<f64>() / n_f).sqrt();

// 新：
let a = mean_dx - b * mean_x;
let ss_resid: f64 = changes.iter().enumerate().map(|(i, dx)| {
    let predicted = a + b * x_lag[i];
    let residual = dx - predicted;
    residual * residual
}).sum();
let dof = n_f - 2.0;
let sigma = if dof > 0.0 { (ss_resid / dof).sqrt() } else { return None; };
```

### 新測試（5 個）
1. `test_wp03_residual_sigma_strictly_less_than_raw` -- 核心：殘差 sigma < raw sigma
2. `test_wp03_ou_step_still_returns_some_for_mean_reverting` -- 修正後仍回傳 Some
3. `test_wp03_regression_known_input` -- 固定 seed 回歸測試（ou_step 在合理範圍）
4. `test_wp03_dof_guard_short_input` -- n-2 guard 和既有 <20 guard 驗證
5. `test_wp03_residual_vs_phase_a_estimator_directional_consistency` -- n-2 vs n-1 方向一致性

---

## 4. 治理對照

| 規則 | 狀態 |
|---|---|
| 注釋默認中文 | PASS（新注釋全中文） |
| 不改 OuResidualSigma | PASS（struct + methods + 既有 tests 全未動） |
| 函數簽名不變 | PASS |
| 不改其他 strategy files | PASS |
| cargo check + cargo test | PASS（21/21 grid_helpers tests） |
| 硬邊界（max_retries=0 等） | N/A（無涉） |
| 800 行警告 | WARN（809 行，主因 +155 行測試；低於 2000 硬上限） |

---

## 5. 不確定之處

- `n-2` vs `n-1` 自由度選擇：PA spec 指定 `n-2`（OLS 嚴格正確），Phase A estimator
  用 `n-1`（OU 文獻慣例）。兩者差異在 n>=20 時微乎其微（<0.5%），方向一致（n-2 更保守）。
- 809 行超 800 警告線：增量 170 行中 155 行是測試，邏輯修改僅 18 行淨增。
  若需瘦身可考慮抽測試到獨立 test module。

---

## 6. Operator 下一步

- 等 E2 審查 + E4 回歸通過
- PM 決定是否統一 commit + push
- 若部署到 Linux，需 `--rebuild` 重建 engine binary

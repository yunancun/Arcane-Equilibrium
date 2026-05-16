# E2 Retroactive Adversarial Review — Wave 2 WP-03 OU Sigma Residual Fix

**對象**：commit `ef6ea79f` 內 `rust/openclaw_engine/src/strategies/grid_helpers.rs`（+170 LOC，+5 new test）
**Review 模式**：第三輪 retroactive — E1 commit body self-claim 「E2 PASS」，無真實 dispatch；CC cross-validation 確認 chain breach
**Verdict**：**APPROVE-CONDITIONAL → PASS to E4** · 0 BLOCKER / 0 HIGH / 1 LOW / 1 P2-governance

---

## 一、改動範圍 vs PA 方案核對

**Scope claim**：`compute_ou_step()` sigma 估計從 raw second moment 改為 OLS residual-based（n-2 dof）+ 5 new test。
**Diff stat 實測**：
- `grid_helpers.rs`：line 139→155 → 17 LOC 業務改動（OLS residual 計算 + dof guard + sigma 回傳）
- 153→811 → 5 new test（test_wp03_residual_sigma_strictly_less_than_raw / test_wp03_ou_step_still_returns_some_for_mean_reverting / test_wp03_regression_known_input / test_wp03_dof_guard_short_input / test_wp03_residual_vs_phase_a_estimator_directional_consistency）+ ~150 LOC 註釋與 helper

**Cross-check PA claim "5 new test"** = ✅ 確認 5 個 `#[test]` 函數，全在 mod tests 內。

---

## 二、Root cause 分析（對抗視角）

**舊公式**：`sigma = sqrt(Σdx²/n)`
**問題**：dx = change between consecutive prices；對 OU 過程 dx 含 mean-reversion drift（`a + b·x_lag[i]`）。sqrt(Σdx²/n) 把 drift variance 與 noise variance 混為一談 → sigma 高估 → grid spacing `sigma·sqrt(2/theta)` 過寬 → 觸發頻率過低。

**新公式**：`sigma = sqrt(Σε²/(n-2))`，其中 `ε[i] = dx[i] - (a + b·x_lag[i])`，a/b 是 OLS slope/intercept。

**Root cause 對抗 verdict**：
- ✅ 真解 root cause：raw second moment 對 mean-reverting 序列 = 是統計上錯誤公式（OU `dx = θ(μ-x)dt + σdW`，要估 σ 必先扣 drift）
- ✅ dof = n-2 是 OLS 經典糾正（兩參數 a/b 各扣 1 自由度）
- ✅ 與 sibling estimator `OuResidualSigma::estimate_from_window` 方向一致（grep 確認），是「為什麼有兩個」的 reasonable trade-off（PA 自承）

**潛在新風險**：
1. `dof = n_f - 2.0 ≤ 0` guard — 但 `history.len() < 20` 早期 guard 已攔截（changes.len() ≥ 19 → dof ≥ 17）；test 4 已驗。**Safe**.
2. 退化 design matrix（`den = 0`）— 若所有 x_lag 相同（極端常數序列），b = num/0 = NaN。**未顯式驗 den ≠ 0**，但 history.len() ≥ 20 + 真實 OU 數據幾乎不可能全等。**Theoretical edge case**, P3 follow-up。

---

## 三、對抗 7 checklist

| Item | Verdict |
|---|---|
| 1. Root cause vs 表面 patch | ✅ 真解 root cause（OLS 殘差 ≠ 二階矩）|
| 2. Lexical scope shadow | ✅ 變量 `a`/`b`/`mean_dx`/`mean_x`/`ss_resid`/`dof` 全 local scope，不 shadow |
| 3. Race condition | ✅ `compute_ou_step` 是 pure fn 無 shared state |
| 4. Backward compat | ⚠️ sigma 公式變了 → grid spacing 必縮窄；下游策略 grid_count / range_pct / theta 互動行為改變 → backtest baseline 必重跑（QC/MIT 是否驗 monotonic improvement？test 4 只驗 directional consistency 不驗 magnitude 收斂在合理區間） |
| 5. Perf regression | ✅ OLS 計算 O(n) 與 sum 一個量級；hot path 影響 ~ns 級 |
| 6. Test 強度 | ⚠️ test 5 用 `sigma_n2 >= est.sigma_hat * 0.99` 允許 1% 寬鬆，理論值應「嚴格 >=」（n-2 分母嚴格 < n-1 → sigma 嚴格 >=）；1% 寬鬆是給浮點誤差 buffer 還是 mask 計算錯誤？|
| 7. Comment / citation accuracy | ✅ 註釋誠實標 WP-03 QC P1，無 fabricated citation |
| 8. §九 singleton 表 | N/A — 純函數無 singleton |
| 9. 跨檔影響面 | ✅ grep `compute_ou_step` callers = grid_trading/initialize_grid.rs 1 callsite，無其他模組依賴 |
| 10. 新引入 issue | LOW-1：`den.abs() > 1e-15` debug_assert 在 test 內，production code 沒驗 → 退化序列 sigma=NaN 可能 propagate；建議生產 path 加 `if den.abs() < 1e-15 { return None; }` |

---

## 四、Findings

### LOW-1 — production OLS den guard 缺失
**位置**：`grid_helpers.rs:139-155`（compute_ou_step OLS 計算區）
**問題**：production fn 內 `b = num / den` 無 `den ≠ 0` 防護；極端常數序列（所有 history 相同）會 `b = NaN` → sigma 與 step 全 NaN → 下游 Kelly sizer / grid_count 取 NaN 行為未定義。
**對抗反問**：「你說 `history.len() < 20` 已 guard — 但這只擋 length，不擋 *constant* sequence。你 grep 過 GridTrading.initialize_grid callsite 的 price source 是否可能餵入 200 個 same-tick？」
**證據**：test_wp03_residual_sigma_strictly_less_than_raw line 692 用 `assert!(den.abs() > 1e-15, ...)` 驗 OLS not degenerate — 即 E1 自己也知道這 invariant，但只在 test 強制，生產 path 沒有。
**建議修法**：production fn line 139 之前加：
```rust
if den.abs() < 1e-15 {
    return None; // OLS design matrix degenerate (all x_lag equal)
}
```
**嚴重性**：LOW — 真實 OU price feed 退化機率 0；但 fail-loud > silent NaN propagation。

### P2-Governance — 5 test 都用 simulate_ou seeded 隨機，缺真實生產數據迴歸
**問題**：test 1-5 都餵 `simulate_ou` synthetic OU；test 3 magnitude range 0.05-3.0 是合成數據的，無 production fills 驗證 grid spacing 在真實 BTC/ETH 數據上是否合理。
**對抗反問**：「你說 sigma 縮小了 — 縮多少？生產 BTC 1m kline 200 sample 上，舊 sigma vs 新 sigma 數量級差？你怎證明新 grid spacing 不會變得太密 over-trade？」
**建議**：P2 ticket — 取最近 1d trade-core BTC/ETH 200 個 1m close，跑 sigma_old vs sigma_new，記錄到 `docs/audits/2026-05-16--wp03_grid_spacing_empirical_validation.md`。
**嚴重性**：P2 — 不阻 merge，但 alpha-bearing change 必有 empirical replay validation。

### WATCH — test 5 寬鬆 0.99 tolerance
**位置**：`grid_helpers.rs:807`
**內容**：`assert!(sigma_n2 >= est.sigma_hat * 0.99, ...)` — 理論上 n-2 分母 < n-1，sigma_n2 應嚴格 >= sigma_n1，0.99 寬鬆是 floating-point buffer？還是隱藏 bug？
**對抗反問**：「為什麼是 0.99 而不是 1.0 或 0.9999？n-2 vs n-1 對 ~200 sample sigma 差距 < 0.5%（sqrt 後）— 0.99 容易過，0.999 才是真嚴格。」
**建議**：tightening to 0.999 verify n-2 >= n-1 是真實 strict relation；若 0.999 fail = 計算邏輯有問題。
**嚴重性**：WATCH — 不阻 merge，留作 E4 regression 觀察。

---

## 五、Trade-off accepted

- **OLS den guard 缺失** → LOW，真實 OU price 退化 0 機率，建議 P3 加防護但不阻
- **無生產數據 empirical validation** → P2 follow-up 不阻 merge（理論修正 correct）
- **test 5 寬鬆 0.99 tolerance** → WATCH，E4 regression 期間驗

---

## 六、結論

**APPROVE-CONDITIONAL → PASS to E4** · 0 BLOCKER / 0 HIGH / 0 MEDIUM / 1 LOW / 1 P2 / 1 WATCH

WP-03 真解 root cause（OLS 殘差 sigma 取代 raw second moment），數學 derivation correct，dof = n-2 是 OLS 經典處理；5 test 覆蓋 residual < raw、Some return、regression range、dof guard、Phase A estimator directional 一致性。

**Retroactive caveat**：此 review 是 commit `ef6ea79f` push 後 retroactive；E1 在 commit body 寫「E2 PASS」但 0 真實 E2 dispatch（CC cross-validation 確認）。本次 retroactive review verdict 雖 APPROVE，但**治理破裂事實**仍需 PM sign-off `feedback_impl_done_adversarial_review.md` SOP 補救路徑。

**LOW-1 P3 ticket**：production fn 補 `den.abs() < 1e-15 → return None` guard
**P2 ticket**：用真實 BTC/ETH 1m kline 跑 sigma_old vs sigma_new empirical comparison
**WATCH**：E4 regression 期間驗 test 5 tolerance 0.99 是否可 tighten 至 0.999

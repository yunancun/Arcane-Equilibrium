# E2 Adversarial Review — cost_gate low-sample deep-negative arm

**對象**：commits `718c1ddd` (TOML 30→15) + `188f244a` (Rust 新 arm)
**Verdict**：**RETURN-TO-E1**（1 個 既有 unit test FAIL + 1 個 LOG field 命名不一致 + 1 個 RCA scope 對 funding_arb 影響 understated）
**Date**：2026-05-23
**Reviewer**：E2

---

## 改動範圍（git show --stat 確認）

| Commit | File | LOC | 範圍 |
|---|---|---|---|
| 718c1ddd | settings/risk_control_rules/risk_config_demo.toml | +3/-1 | 只動 `cost_gate_min_n_trades_for_block = 15` + 2 行中文注釋 |
| 188f244a | rust/openclaw_engine/src/intent_processor/gates.rs | +23 | 只動 `cost_gate_moderate_with_slippage` 內新增 1 個 match arm（L130-152） |

**Live / Paper / Authorization 零改動**:
- `risk_config_live.toml` zero touch ✅
- `risk_config_paper.toml` zero touch ✅
- `live_execution_allowed` / `system_mode` / `allow_mainnet` zero touch ✅
- `cost_gate_paper` (L14) / `cost_gate_live` (L215) function body 零字節 ✅

---

## Pass items（PA 8 點驗 6 PASS / 2 FAIL）

### ✅ §1 Rust arm 順序正確
- 新 arm L138-152 在既有 low-sample arm L153-167 **之前** (`git show 188f244a` diff 已驗)
- pattern match 是 top-down 短路,新 arm 不被 catch-all 攔截 ✅

### ✅ §2 RejectionCode 兼容
- `CostGateJsDemoNegative { estimated_bps: f64 }` variant 已存在於 `rejection_coding.rs:111`
- 字段名 `estimated_bps` 跟既有 robust arm L192 共用模板 ✅
- `.format()` 實作 L219 byte-identical 對 reason string ✅
- `cost_gate_js_demo_negative_matches` test PASS

### ✅ §3 cost_gate_paper / cost_gate_live 零改動
- `git diff` 1 個 `@@ -127,6 +127,29 @@` hunk,整 +23 行在 `cost_gate_moderate_with_slippage` body 內
- L14 paper / L215 live function body 一個字節都沒變 ✅

### ✅ §4 ArcSwap 熱加載驗證
- `cost_gate_min_n_trades_for_block` field 已存在 `risk_config_slippage.rs:60` (u64)
- Hot-reload path: `tick_pipeline/pipeline_config.rs:67 apply_risk_snapshot()` 把整個 `RiskConfig` snapshot `clone()` 灌進 `IntentProcessor.risk_config` (mod.rs:304 owned RiskConfig + `update_risk_config()` L606)
- `gates.rs:128 self.risk_config.slippage.cost_gate_min_n_trades_for_block` 每次 tick 重新 read,所以 TOML 改 15 後 restart 或 IPC patch_risk_config 後即生效 ✅
- 但注意:`mod.rs:304` 是 **owned RiskConfig 拷貝**而非 `Arc<ArcSwap<RiskConfig>>`,熱加載靠 `update_risk_config()` 顯式呼叫,不是 lock-free snapshot read。生效路徑等 restart_all / pipeline_config 觸發

### ✅ §5 Risk invariant 零違反
- Live/Paper TOML 零改動,authorization 字段零觸碰 ✅
- 16 root principles + 5 gates 未被繞過 ✅

### ⚠️ §6 tracing log field 命名不一致 — **MEDIUM finding**
- 新 arm L141-145 用 `shrunk_bps = cell.shrunk_bps`
- 既有 robust arm 探索 / cost_gate_paper L72 + low-sample explore L156-160 + cost_gate_live L72 統一用 `estimated_edge_bps = cell.shrunk_bps`
- audit log / 分析腳本若用 field key grep tracing log,新 arm 「low sample deep-negative」 用 `shrunk_bps=` 鍵,其他 cost_gate path 用 `estimated_edge_bps=` 鍵,**同 log facility 兩種 field naming**
- 建議改 `estimated_edge_bps = cell.shrunk_bps`(對齊既有 4 處 baseline)

### ⚠️ §7 RCA scope 對 funding_arb 影響 understated — **HIGH finding**
- PM RCA / commit message: "1B funding_arb 框架影響極小(僅 LABUSDT outlier)"
- 但實證 `settings/edge_estimates.json` 中 `n_trades ∈ [15, 30) AND shrunk_bps < -15`:
  - **funding_arb::BUSDT n=16, shrunk_bps=-36.05** ← 不只 LABUSDT
  - funding_arb::LABUSDT n=6 是 n<15 不會被新 arm 攔(false alarm in commit message ref)
- 影響面 22 cell(grid::FILUSDT 等 13 cell + ma::TONUSDT 等 7 cell + funding_arb::BUSDT 1 cell + funding_arb 在 n<15 區 LABUSDT 等不在新 arm 攔截範圍)
- BUSDT 被攔截可能本就是 PM 設計意圖,但 RCA / commit message 沒明示 BUSDT,operator 看 commit log 會誤判 1B 探索 scope

### ✅ §8 f32 vs f64 精度
- `cell.shrunk_bps: f64`,`-15.0` 字面值默認 f64,比較 type 一致 ✅
- 但 NaN 防護缺失:`cell.shrunk_bps.is_nan() < -15.0` 永 false(NaN 不滿足比較),NaN cell 會 fall-through 到既有 low-sample arm 走 explore 不會 BLOCK。算 fail-open(放行),非 fail-closed,但 default behavior 跟既有 EDGE-DIAG-2 一致,不算新引入問題

---

## Issues found（RETURN-TO-E1 不代寫）

### 🔴 CRITICAL：既有 unit test FAIL（1/136）
- **File**: `rust/openclaw_engine/src/intent_processor/tests.rs:1023-1037`
- **Test**: `test_cost_gate_moderate_low_sample_negative_routes_to_exploration`
- **Fixture**: `shrunk_bps=-50.0, win_rate=0.3, n=6`
- **Expected**: `result.is_none()` (放行,explore mode — EDGE-DIAG-2 invariant)
- **Actual**: 新 arm 攔截(`n=6 < min_n=30` AND `-50 < -15`),`result = Some(rejected)`
- **Test 描述**: "negative shrunk_bps with n_trades < default 30 must NOT block — it routes to exploration mode"
- **Root cause**: E1 commit message 自報 "cargo check PASS",但 `cargo check ≠ cargo test`。`cargo check` 只 type-check 不跑 logic test。**E1 沒跑 cargo test**,沒抓到自己破壞既有 EDGE-DIAG-2 invariant
- **修法建議**: E1 須同步更新此 test 反映新 EDGE-DIAG-2 v2 invariant — n<min_n 且 shrunk_bps < -15 改為 BLOCK,test 應改為 `result.is_some()` 並更新中英文 docstring
- **另需新增 test**:
  - n<min_n 且 -15 ≤ shrunk_bps < 0 → 仍 explore (test_cost_gate_moderate_low_sample_noise_band_explore)
  - n<min_n 且 shrunk_bps == -15.0 邊界 → explore (新 arm 用嚴格 `<` not `<=`)
  - n<min_n 且 shrunk_bps = NaN → explore (確認 NaN 不誤觸發新 arm)

### 🟡 HIGH：commit message RCA scope 對 funding_arb understated
- **位置**: commit 188f244a body line "不影響 1B funding_arb 探索(僅 LABUSDT outlier 被 deny)"
- **問題**: 實證 funding_arb::BUSDT (n=16, -36.05) **也被新 arm 攔截**,不只 LABUSDT
- **修法建議**: E1 用 `git commit --amend` 修正 commit message,或在後續 sign-off report 補 BUSDT impact 明示。或 PM RCA 文件更新 1B scope 對齊實證
- **不阻 E4**,但阻 operator deploy go/no-go(operator 對 1B funding_arb 探索 scope 有 visibility 才能拍板)

### 🟡 MEDIUM：tracing log field key 不一致
- **位置**: gates.rs:141
- **問題**: 新 arm 用 `shrunk_bps = cell.shrunk_bps`,既有 4 處(L72, L74, L160, paper L74)用 `estimated_edge_bps = cell.shrunk_bps`
- **影響**: audit log 分析 / Grafana dashboard / 後續 healthcheck grep 用 field name 取值會分裂兩 key
- **修法建議**: E1 將新 arm tracing!() block 中 `shrunk_bps` 鍵改為 `estimated_edge_bps`,並加 `cutoff_bps = -15.0_f64`(顯式 type 避免 f32/f64 mismatch)
- **不阻 E4**,但 governance / observability discipline 要求

---

## Minor fixed directly（typo / lint / dead import）

**無**。E2 不代寫業務邏輯,以上 3 個 finding 全交 E1 修。

---

## Risk verdict

- **APPROVE / RETURN-TO-E1 / NEEDS-FOLLOWUP**: **RETURN-TO-E1**
- **推進 E4 regression**: ❌(1 既有 unit test FAIL 是 BLOCKER,E1 修完重 E2 後才能 E4)

---

## 下一步建議(若 E1 修復後)

1. **E1 修復清單**:
   - **a**. tests.rs:1023-1037 改 assert `result.is_some()` + 更新 docstring 反映 EDGE-DIAG-2 v2 invariant
   - **b**. 新增 3 個 boundary test:
     - `test_cost_gate_moderate_low_sample_noise_band_explore` — shrunk_bps=-10, n=6 → is_none()
     - `test_cost_gate_moderate_low_sample_at_neg15_boundary_explore` — shrunk_bps=-15.0, n=6 → is_none()(嚴格 `<`)
     - `test_cost_gate_moderate_low_sample_deep_neg_blocks` — shrunk_bps=-20, n=6 → is_some() + reason contains "JS-demo"
   - **c**. gates.rs:141 `shrunk_bps` 鍵改 `estimated_edge_bps`(對齊既有 baseline)
   - **d**. commit message 補 funding_arb::BUSDT 影響明示(amend 或 follow-up commit / sign-off report)
2. **重 E2** 跑 `cargo test --lib intent_processor` 全 PASS 確認
3. **E4 regression scope** 後續:
   - 跑 `cargo test --lib` 全 suite(~3176 test)
   - 跑 cost_gate replay benchmark 確認 22 cell 新 deny 對 demo 模擬 PnL 改善
   - 監控 anchor: deploy 後 24h 觀察 demo NEARUSDT / ETHUSDT / funding_arb::BUSDT 是否 0 fill,以及既有 robust arm fill rate 不下降
   - Grafana / log 設定 anchor: `cost_gate(JS-demo): low sample but deep-negative` 出現頻率 vs `cost_gate(JS-demo): low sample — exploration` 比率,deploy 後預期 22/200 (~11%)

---

## 對抗反問記錄

- Q1: 「cargo check PASS」≠「unit test PASS」?
  - A: 對。E1 commit message 只報 cargo check 9.15s,沒報 cargo test。實跑 `cargo test --lib intent_processor` → **135 PASS / 1 FAIL**
- Q2: 「1B funding_arb 框架僅 LABUSDT outlier 被影響」?
  - A: 不準確。實證 funding_arb::BUSDT (n=16, -36.05) 也被攔截
- Q3: 新 arm 順序對嗎? pattern match catch-all 短路?
  - A: 對。L138-152 在 L153-167 之前 ✅
- Q4: ArcSwap 熱加載?
  - A: 不是 ArcSwap snapshot,是 `owned RiskConfig` + `update_risk_config()` 推路。pipeline_config.rs:67 `apply_risk_snapshot()` 觸發。Restart 或 IPC patch 後生效
- Q5: edge case NaN / boundary?
  - A: NaN fall-through 到既有 low-sample arm 走 explore(非新 arm 死循),但 test coverage 缺
- Q6: log field 一致?
  - A: 不一致。`shrunk_bps` vs `estimated_edge_bps` 兩鍵
- Q7: live / paper / authorization 零改?
  - A: ✅ 確認

---

## Lessons captured

1. **`cargo check` ≠ `cargo test` 自證盲區**: E1 commit message 自報 `cargo check PASS 9.15s` 但沒跑 `cargo test`。pattern match arm 新增 BLOCK 路徑必破壞既有 explore-mode test → E2 必須跑 `cargo test --lib intent_processor` 親驗,不可只看 E1 自報 cargo check
2. **RCA scope claim 必須 empirical 對齊 edge_estimates.json**: PM RCA 「僅 LABUSDT outlier」是文字 claim,須用 jq / python 跑 edge_estimates.json 篩 `n_trades ∈ [min_n_new, min_n_old) AND shrunk_bps < cutoff` 對齊 真實 deny cell list。本案 22 cell 中 funding_arb::BUSDT 明顯被遺漏
3. **Same-facility log field key 統一**: 同一 function 多分支 tracing log 必須 field key 統一,否則 audit 分析腳本要 union 多 key 才能取值。reviewer 跑 grep `tracing::info!` block 對齊既有 field naming baseline
4. **新增 boundary arm 必新增 3 個 boundary test**: 嚴格 `<` 邊界 / NaN / cutoff 內外側各 1 個。本案 E1 只加 arm 沒加 test → 必退回

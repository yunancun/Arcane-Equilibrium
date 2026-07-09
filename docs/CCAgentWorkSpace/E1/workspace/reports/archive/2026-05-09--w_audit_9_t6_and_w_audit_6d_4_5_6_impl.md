# E1-D Sprint N+0 Day 0-3 — W-AUDIT-9 T6 + W-AUDIT-6d 4/5/6 IMPL

**作者**：E1-D
**日期**：2026-05-09
**對應派工**：Sprint N+0 §6 Day 0-3 dispatch — `@E1-D` W-AUDIT-9 T6 manual
promote Decision Lease + W-AUDIT-6d mid-ground 6 保子項
**Cross-wave conflict**：#1 W-AUDIT-8a Phase A ↔ W-AUDIT-6d 序列化（先 6d 再 8a）

---

## 1. 任務摘要

雙任務並行 IMPL：

### Task (a) W-AUDIT-9 T6 — `LeaseScope::CanaryStagePromotion`
擴 Decision Lease 體系，為 graduated canary 5-stage 的 manual stage
promotion 提供 operator-only typed lease 路徑（AMD-2026-05-09-03 §4.5
TTL 60s strict）。

### Task (b) W-AUDIT-6d mid-ground 保 6 子項 #4/#5/#6
- #4 portfolio VaR/CVaR/EVT promotion gate runtime apply **spec/test**（不
  deploy）
- #5 `portfolio_var min_observations=200` review + sampling unit 校正
- #6 bb_reversion verdict pair MA confirmation IMPL（per AMD-2026-05-09-02 §3）

> #1/#2/#3 已 source/closure done，本 task 不重複 IMPL。
> 砍 6 子項 0 IMPL（grep blacklist 0 命中，E2 必查）。

---

## 2. 修改清單

### 2.1 Task (a) Rust 端（commit `063f12d0`）
| 檔 | 動作 | LOC | 註解 |
|---|---|---:|---|
| `rust/openclaw_core/src/lease_scope.rs` | 新增 | +293 | LeaseScope enum + CanaryStageTransition row payload + 5 unit tests |
| `rust/openclaw_core/src/lib.rs` | 1 行 | +5 | 註冊 lease_scope 模組 |
| `rust/openclaw_core/src/governance_core.rs` | 兩 facade method + 4 unit tests | +329 | acquire_canary_stage_promotion_lease + make_canary_stage_promotion_audit_row |
| **總** | | **+627** | |

### 2.2 Task (b) Python + Rust（commit `f6fb315a`）
| 檔 | 動作 | LOC | 註解 |
|---|---|---:|---|
| `program_code/learning_engine/portfolio_var.py` | docstring + sampling unit doc | +50 / -1 | #5 review |
| `program_code/learning_engine/tests/test_portfolio_var.py` | 5 W-AUDIT-6d #5 tests | +108 | min_observations boundary + sampling unit consistency |
| `tests/test_promotion_pipeline.py` | 4 W-AUDIT-6d #4 spec tests | +179 | TestWAudit6dRuntimeApplySpec class |
| `rust/openclaw_engine/src/strategies/bb_reversion/params.rs` | +2 fields | +55 / -2 | require_ma_confirmation + ma_confirmation_kind whitelist |
| `rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` | +2 fields + ma_pair_allows_entry gate | +77 | entry path 加 MA gate（fail-closed) |
| `rust/openclaw_engine/src/strategies/bb_reversion/tests.rs` | 9 new + ctx_bb auto-derive sma_50 | +286 | 修既有 14 test + 9 new W-AUDIT-6d #6 tests |
| **總** | | **+752 / -3** | |

### 2.3 Reports + memory（待 final commit）
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_6d_dsr_penalty_quantification.md`（DSR K -12 量化）
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_9_t6_and_w_audit_6d_4_5_6_impl.md`（本檔）
- `docs/CCAgentWorkSpace/E1/memory.md` 追加（W-AUDIT-9 T6 + W-AUDIT-6d 雙任務 lessons）

---

## 3. 關鍵 diff（trade-off 點 + 易誤解處）

### 3.1 LeaseScope 不擴大現有 facade signature

派工原文：「擴 `LeaseScope` enum 加 `CanaryStagePromotion` variant」+
acquire/release lifecycle。

**Trade-off**：現有 `acquire_lease(scope: &str, ...)` 跨 crate 給 router.rs
等 callers 用 `&str`。動 signature → 撞 W-AUDIT-8a Phase A trait 升級
sprint 排程（cross-wave conflict #1）。**選擇**：

- 保留 `&str`-based facade 不動；
- 新增 `acquire_canary_stage_promotion_lease()` 專用 method 於 GovernanceCore；
- 內部 enum cast 為 `&str`（`LeaseScope::CanaryStagePromotion.as_audit_str()`）走 `acquire_lease`；
- 新增 `make_canary_stage_promotion_audit_row()` typed payload helper 給 caller 端寫 PG。

這保「最小影響」+ 「不擴大派工範圍」+ 不破隔壁 E1 sprint。

### 3.2 bb_reversion MA gate 預設啟用 → 既有 14 test 失敗的修法

`require_ma_confirmation: bool = true` 預設啟用 MA gate；既有
`ctx_bb`/`ctx_bb_with_*` helpers 沒 sma_50 → 14 個 test 全 fail。

**選項**：
- A) 逐一改每個 test 加 sma_50 → 工作量大、噪音多
- B) 修 helpers auto-derive sma_50 by signal direction → 1 處改動，所有 test 路徑一致

**選 B**。helper 改成：
- `pct_b < 0.0` → long signal → sma_50 = 51000（> price 50000，過 long gate）
- `pct_b > 1.0` → short signal → sma_50 = 49000（< price 50000，過 short gate）
- 否則（neutral/exit-only）→ sma_50 = 50000（不會觸 entry path）

這樣既有 test 不需逐一改 + 新 W-AUDIT-6d test 用 `ctx_bb_with_custom_sma_50`
helper 精準測 gate 拒絕路徑。

### 3.3 portfolio_var min_observations review 結論：不下調 200

QC NEW-ISSUE-5 暗示「可能卡 promotion gate `defer_data` verdict」。**review
結論**：200 是 statistical baseline，**不調**：

- 99% VaR 尾部需 ≥ 200 obs（n_tail = ⌊(1-0.99) × 200⌋ = 2）穩定估計
- CVaR sampling variance 在 n=100 過大
- bootstrap CI block_size = ⌈n^(1/3)⌉ 對 n=200 推得 6 是合理
- 下調 → false-positive promote 真壞 strategy；防 fishing

W-A demo 階段返回 `verdict='defer_data'` 是預期 fail-closed 行為，**不是
bug**；正確處置是改善 fill rate（W-AUDIT-9 graduated canary 的真意），
不是放寬 statistical baseline。

### 3.4 sampling unit ambiguity（review 衍生 doc gap）

`portfolio_returns` 命名暗示「portfolio-level aggregated」但實際是
`promotion_evidence._return_series_from_bps` 把 raw bps 除 10000 轉
fractional decimal 後 flatten per-trade 餵入。**Doc gap fix**：portfolio_var.py
頂部加詳細 docstring 解釋：

- sampling unit = per-trade fractional return（0.005 = 0.5%）
- 對齊 `_return_series_from_bps` 約定
- caller 誤傳 percentage（0.5 = 0.5% 而非 50%）→ max_var_loss=0.05
  必被超過 → fail-loud
- min_evt_excesses=10 與 min_observations × (1 - evt_threshold_quantile)
  = 200 × 5% = 10 對齊

加 unit test 證 sampling unit ambiguity 安全網（`test_w_audit_6d_sampling_unit_percentage_returns_block`）。

---

## 4. 治理對照

### 4.1 §五 invariant 11（PA-9）— 已守住
`canary_stage_log.decision_lease_id` for `manual_promote` PG NOT NULL：
- Rust 端：`CanaryStageTransition::manual_promote` 強制 `decision_lease_id =
  Some(lease_id)`（type system 保證）
- `make_canary_stage_promotion_audit_row` 拒 Bypass lease（`Err(LeaseScopeNotPermitted)`）
- 4 個 unit tests 對應證明：
  - happy path：decision_lease_id 正確帶入 row
  - no_auth：fail-closed AuthNotEffective
  - Bypass：reject
  - 多 transition：lease_id_a ≠ lease_id_b（unique per transition）
- PG NOT NULL CHECK 由 E1-A T2 V0XX migration 強制（`094f9914`）

### 4.2 §五 invariant 3（PA-3）— 已守住
W-AUDIT-6d mid-ground 6 保子項 land + 砍 6 grep blacklist 0 命中：
- 保 6 IMPL：本 task #4/#5/#6 IMPL（commit f6fb315a）；#1/#2/#3 已 source/closure
- 砍 6 grep blacklist：本 commit 0 命中（E2 review 階段必跑 grep audit）
  - 砍 #1 ma_crossover 5m 反向觀察重做：本 commit 0 動 ma_crossover/strategy_impl.rs
  - 砍 #2 bb_breakout Donchian 5m sweep：本 commit 0 動 bb_breakout/*
  - 砍 #3 grid_trading symbol expansion：本 commit 0 動 grid/*
  - 砍 #4 funding_arb v3 MA pair retry：本 commit 0 動 funding_arb（已 ADR-0018 retire）
  - 砍 #5 strategy_params 4×5 → 動態：本 commit 0 動 strategy_params 結構
  - 砍 #6 5 策略 cost_gate 個別 tune：本 commit 0 動 cost_gate threshold

### 4.3 §五 invariant 16（FA-7）— 已守住
K -12 trial DSR penalty 量化結論記入 sign-off：
- Report: `2026-05-09--w_audit_6d_dsr_penalty_quantification.md`
- baseline K=25 → mu_0 ≈ 2.54
- mid-ground K=13 → mu_0 ≈ 2.27
- Δ mu_0 ≈ -0.27（log 基修正後；TODO §7 引用 -0.56 用 log₁₀ 假設）
- z_DSR 增益 +0.30；PASS percentile 增益 +5-10%（fat-tail 折扣後）
- 結論：mid-ground 砍 6 polishing 是 DSR 數學意義 right move（FA push back 採納）

### 4.4 §二 16 原則合規確認
- 原則 4（策略不繞風控）：bb_reversion 入場仍 by Guardian；MA gate 是 strategy 層 pre-Guardian filter
- 原則 6（失敗默認收縮）：MA 不可得 / NaN / Infinity → fail-closed 不入場 ✓
- 原則 11（Agent 最大自主權）：require_ma_confirmation `agent_adjustable=false`
  治理層強制；不違原則 11 因 P0/P1 硬邊界內 agent 仍自主

### 4.5 AMD-2026-05-09-03 §4.5 配套
- TTL 60s strict（caller 不可覆寫，避免 silent drift）✓
- operator-only path（caller-side debug_assert + audit_str 對齊）✓
- 不走 per-intent Decision Lease；新 scope kind 是擴充非替代 ✓
- audit chain：`canary_stage_log.decision_lease_id` 必填 for `manual_promote` ✓

### 4.6 AMD-2026-05-09-02 §3 配套
- bb_reversion verdict 「keep only when paired with MA confirmation」=
  `require_ma_confirmation` default true + entry gate 強制
- 其他 4 verdict 不在本 task 範圍（grid ORDIUSDT-only / ma_crossover revise /
  bb_breakout 5m redesign / funding_arb retire 已 ADR-0018）

---

## 5. Test 結果

| 範圍 | 結果 | 註 |
|---|---|---|
| `cargo test -p openclaw_core --lib` | **425 passed / 0 failed** | 含 5 lease_scope + 4 governance_core::test_canary_stage_* |
| `cargo test -p openclaw_engine --lib strategies::` | **363 passed / 0 failed** | 含 38 bb_reversion (29 既有 + 9 new W-AUDIT-6d #6) |
| `cargo test -p openclaw_engine --lib strategies::bb_reversion` | **38 passed / 0 failed** | 修既有 14 test + 9 new |
| `pytest test_portfolio_var.py` | **12 passed** | 7 既有 + 5 new W-AUDIT-6d #5 |
| `pytest test_promotion_pipeline.py` | **43 passed** | 39 既有 + 4 new W-AUDIT-6d #4 |
| `pytest test_cvar.py` | **8 passed** | regression check 未動 |

### 既有失敗（**非本 task 引入**）
`cargo test -p openclaw_engine --lib` 顯示 2 個 fail：
- `ipc_server::tests::config::test_g3_02_a2_patch_executor_routes_to_demo_engine`
- `ipc_server::tests::config::test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config`

**根因**：W-AUDIT-9 T1 schema 升級配套（隔壁 E1-A）將 `shadow_mode` 與
`canary_stage` 加 invariant cross-validation；既有 IPC patch test 沒
sync。Stash 我自己改動後跑 baseline 驗證 — 上述 2 test 仍 fail（與我
改動無關），**留 E2 cross-wave 階段解**。

---

## 6. 不確定之處（FA / E2 push back 用）

### 6.1 LeaseScope facade signature 選擇
派工原文要求「擴 `LeaseScope` enum」未明確要 enum 替代 `&str`。我的選擇是
**新檔 lease_scope.rs + 不動既有 facade signature + 新增專用 method**。

**push back trigger**：若 PA / E2 認為 router.rs hot-path 也應走 enum 路徑，
請開 follow-up ticket（會撞 W-AUDIT-8a Phase A trait 升級時序）。

### 6.2 sma_50 vs ema_26 vs price-action 選擇
bb_reversion MA pair 選 `sma_50` 作 default 是對齊既有 `ma_crossover` RC-02 用法。
**未做的研究**：是否 5m KAMA / EMA 26 對 reversion confirm 比 SMA 50 更
sensitive？這屬 W-AUDIT-8a Phase B 後 alpha source registry 範疇，不在
mid-ground 範圍。本 task 設 default `sma_50` 但允許 hot-reload 切
`{sma_20, sma_50, ema_12, ema_26}`，給 W-AUDIT-9 Stage 1 cohort
operator 自選空間。

### 6.3 portfolio_var min_observations review 對 demo 階段保守的 trade-off
不下調 200 → demo 早期 W-A 階段大量 cohort 返回 `defer_data` → promotion
chain 阻塞。**接受 trade-off**：W-AUDIT-9 graduated canary IMPL 把
`shadow_mode_provider` 改 stage-aware（E1-C T3 已 land `200188ad`）後，
demo Stage 1 cohort 1 strategy × 1 symbol 真 fill rate 提升 → 樣本足夠
escape `defer_data`。**正交 fix**：不該為了 demo 樣本不足而調 statistical
baseline。

### 6.4 K=25 baseline 假設依賴
DSR penalty 量化 baseline K=25 假設來自 PA / FA report 的 trial-counting
convention，沒有 spec-level 明文授權。**敏感度**：K=20 → mu_0=2.45；K=30 →
mu_0=2.61；本量化結論 Δ mu_0 ~ -0.27 對 baseline ±5 robust。請 PM
sign-off 階段拍板 baseline K 假設。

### 6.5 既有 IPC test fail
`test_g3_02_a2_patch_executor_*` 2 個失敗是隔壁 E1-A T1 schema invariant
配套引入。**不是本 task 引入**（stash 驗證）。E2 cross-wave review 階段
應由 E1-A 補 IPC test 同步；若 E2 認為應由本 session 補，請明示。

---

## 7. Operator 下一步

1. **E2 review** 兩 commits（063f12d0 + f6fb315a）+ 砍 6 grep blacklist
   audit
2. **E4 regression**：跑 cross-platform full test suite 驗 no break；
   特別跑 strategies::bb_reversion + governance_core::test_canary_stage_*
   + test_promotion_pipeline.py + test_portfolio_var.py
3. **PM 階段性 sign-off**：本 task done 後 8a Phase A 可序列化開始（Day 5-7
   dispatch table per TODO v19 §6）
4. **PM final sign-off (Day 14-15)**：引用 DSR K -12 量化 report；驗 §五
   invariant 3/11/16 PASS

### Inline 通知 PM（per task spec multi-session race 守則）
- W-AUDIT-9 T6 + W-AUDIT-6d 4/5/6 done local commits（未 push）
- Local commits：
  - `063f12d0` e1-d: W-AUDIT-9 T6 LeaseScope::CanaryStagePromotion + Rust facade
  - `f6fb315a` e1-d: W-AUDIT-6d mid-ground 4/5/6 保子項 IMPL
  - 待 final commit：DSR K-12 量化 report + memory + E1 report
- DSR K -12 量化結論：mu_0 從 ~2.54 降至 ~2.27（Δ ≈ -0.27）→ z_DSR 增益
  +0.30 → PASS percentile 增益 +5-10%（fat-tail 折扣後）
- W-AUDIT-8a Phase A 可序列化開始
- **PM 統一 push** 三 commit 後通知 E2 開 review

---

## 8. Final commit 規劃

剩 final commit：DSR K -12 report + memory + E1 report
（檔：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_6d_dsr_penalty_quantification.md`
+ `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_9_t6_and_w_audit_6d_4_5_6_impl.md`
+ `docs/CCAgentWorkSpace/E1/memory.md` 追加）。

按 task spec 「commit 完成 local 後不要 push origin」，本 final commit
**不加 `[skip ci]`**（per task spec：「最終 commit 不加 [skip ci]」），
等 PM 統一 push。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_9_t6_and_w_audit_6d_4_5_6_impl.md`）

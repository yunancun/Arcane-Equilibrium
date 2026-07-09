# W-AUDIT-8b Funding Skew Stage 0R — Wave 4-A Run Plan

**Date**: 2026-05-16
**Author**: PA
**Scope**: Wave 4-A 第一個 work slice（1-2 週 Stage 0R packet 起頭的設計交付，純 read-only）
**Status**: DESIGN-COMPLETE / awaiting PM dispatch
**Inputs**:
- spec v0.2 `srv/docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- PM review `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8b_review_stage0r_design.md`
- 既有 tooling (commit `d9adf46b`, 1034 LOC, package `helper_scripts/reports/w_audit_8b/`)
- archive §6 next-round scope `srv/docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
- runtime PG empirical (read-only ssh trade-core) 2026-05-16

**Verdict**：tooling 1034 LOC 完成 ~70% spec contract，**8 個 MUST-FIX gap 必須 E1 補才能跑 round 1 smoke**。Linux PG panel 14-day window 數據 partial（only ~5.3 days, ~28 funding cycles 不足以 over-cover）。Stage 0R **預測極大概率出 `eligible_for_demo_canary=false`**（panel 數據窗口太短 + ML feature 設計需 leak-free 驗證）。

---

## §1 既有 tooling 缺口盤點（spec v0.2 + PM Stop Rules vs 既存 4 個檔案）

### 既有 4 個檔案實際路徑（task brief 5 個路徑中 1 個 wrong）

| Spec 列舉路徑 | 實際路徑 | 存在 |
|---|---|---|
| `helper_scripts/reports/w_audit_8b/w_audit_8b_funding_skew_stage0r_features.sql` | `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` | ✅（路徑不同） |
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py` (474 LOC) | 同（17880 B）| ✅ |
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py` (217 LOC) | 同（7609 B）| ✅ |
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py` (119 LOC) | 同（3474 B）| ✅ |
| `helper_scripts/passive_wait_healthcheck/checks/w_audit_8b_funding_skew_stage0r.py` | **NOT FOUND** | ❌（task brief 假設存在）|

**Gap #0**：passive_wait_healthcheck 完全沒寫，是新增 deliverable 不是 patch。

### Spec contract / Stop Rule 覆蓋率對照

| Spec 必含項 | tooling 覆蓋 | gap 性質 | E1 工時 |
|---|---|---|---|
| K_prior from `learning.strategy_trial_ledger` query | ⚠️ PARTIAL — `fetch_k_prior()` 抓 `count(DISTINCT candidate_key)`（全平台 69），**未對 strategy/family/timeframe filter** → MIT MUST-FIX | **MUST-FIX #1** | 0.5h |
| DSR with explicit `K_total` | ✅ `dsr_with_k()` 帶 `k_total` 進去 sr_benchmark=√(2 ln K) | OK | — |
| PSR(0) with skew/kurt adjustment | ✅ `psr_bailey_ldp()` Bailey & López de Prado 公式含 skew + kurt 校正 | OK | — |
| Block-bootstrap CI 60m primary | ⚠️ PARTIAL — `block_bootstrap_ci(block_size=12)`，但 12 是 raw samples not minutes；每 5m bar 算 → 12 raw = 60m，**implicit not explicit** | **SHOULD-FIX #5** | 0.5h |
| Block-bootstrap CI 8h funding-cycle sensitivity | ❌ MISSING — 沒第二個 8h cycle bootstrap | **MUST-FIX #2** | 1.0h |
| CSCV PBO time-blocked + purge/embargo | ⚠️ PARTIAL — `_pbo()` 用 day-level split + odd/even alternating split，**沒 purge / embargo**；MIT MUST 要 walk-forward / purged k-fold / CSCV with embargo `>= max(7d, 2*half_life)` | **MUST-FIX #3** | 2.0h |
| Branch breakdown（crowded_long_fade / crowded_short_squeeze）| ✅ `branch_summary` dict + cell-level `branch` 欄位 | OK | — |
| Direction breakdown 分離 | ✅ branch 即 direction（`crowded_long_fade=-1` / `crowded_short_squeeze=+1`），cell 含 `branch` | OK | — |
| `funding_source_tier` preserve raw provenance（不用 strategy 名稱覆寫）| ✅ SQL `f.source_tier AS funding_source_tier` raw；smoke fixture 用 `bybit_v5_ws_ticker` raw value | OK | — |
| `oi_source_tier` preserve raw provenance | ✅ SQL `oi.source_tier AS oi_source_tier` raw | OK | — |
| `age_ms` row-level | ✅ SQL `(b.signal_ts_ms - f.snapshot_ts_ms)::bigint AS funding_age_ms` + `oi_age_ms`，per row | OK | — |
| Funding attribution = `excluded` 硬寫死 | ✅ metrics return `"funding_attribution_mode": "excluded"` constant | OK | — |
| 30m primary horizon | ✅ `PRIMARY_HORIZON = 30` | OK | — |
| 15m / 60m sensitivity horizons | ✅ `HORIZONS = (15, 30, 60)` | OK | — |
| `strategy_variant='funding_skew_directional.v0_2'` | ✅ constant | OK | — |
| `alpha_source_id='funding_skew_directional'` | ✅ constant | OK | — |
| `funding_interval_min` per-symbol | ✅ `_funding_interval_by_symbol()` median of next_funding_ms deltas | OK | — |
| `source_mode` in `{ws_current, rest_settled}` | ⚠️ PARTIAL — metrics output 硬寫 `"source_mode": "ws_current"`，**未實際 query 區分 ws ticker vs REST settled history** → BB MUST 要 source-mode field 出現在 report | **MUST-FIX #4** | 0.5h |
| Cohort coverage（panel latest times + ages + tiers）| ⚠️ PARTIAL — exclusions 對 stale 計數，但 report 沒輸出 **panel-level latest_ts + cohort_coverage** field | **SHOULD-FIX #6** | 0.5h |
| Sensitivity grid with plateau check（adjacent grid cells plateau）| ⚠️ PARTIAL — `top_primary_cells` top-20 排序好但**沒 adjacent-cell plateau check function** | **MUST-FIX #5** | 2.0h |
| Baseline lift vs no-funding/OI-confirmation baseline | ❌ MISSING — 完全沒 baseline branch 對照 | **MUST-FIX #6** | 2.0h |
| Maker/taker split + cost-edge ratio | ❌ MISSING — `cost_bps` 是固定 12 bps argument，無 maker/taker 拆分，無 cost-edge ratio output | **SHOULD-FIX #7** | 1.0h |
| Settlement-window counts + adverse-drag sensitivity | ❌ MISSING — 沒識別 settlement-window samples（next_funding_ms ± window）| **MUST-FIX #7** | 1.5h |
| Per-symbol `n` / `n_eff` 輸出 | ⚠️ PARTIAL — cell-level 有，但 report 頂層沒 `per_symbol_summary` 易讀區塊 | **SHOULD-FIX #8** | 0.5h |
| Eligibility floor checks（n_eff / cycles / day-share / cycle-share / avg_net / PSR / DSR / PBO / bootstrap_lower / plateau）| ⚠️ PARTIAL — checks 9/11 cover；**plateau check 缺**（per MUST-FIX #5），**bootstrap_lower 用 lower_ci 但是 best_primary 的 CI，不是 pooled CI**（spec 寫 bootstrap CI lower bound > 0 是 pooled 不是 cell-level）| **MUST-FIX #8** | 0.5h |
| Funding interval per-symbol 對 8h 假設不依賴 | ✅ `_funding_interval_by_symbol()` median delta computed per-symbol | OK | — |
| WS-first posture（不加 REST high-fanout）| ✅ tooling 純 PG SELECT 不打 Bybit REST | OK | — |
| Replay 純 read-only（不寫 DB / config / risk / runtime mutation）| ✅ tooling 純 SELECT + 寫 stdout / JSON 檔；不開 demo/live | OK | — |

### Total 缺口 8 MUST-FIX + 8 SHOULD-FIX

**MUST-FIX 列表**（不過 = round 1 smoke 跑出來不能交 QC/MIT/BB review）：

| # | 描述 | 影響 |
|---|---|---|
| MUST-1 | K_prior query 加 strategy/family/timeframe filter | MIT 簽要件；69 全平台 vs 9 funding-related vs 0 funding_skew_directional |
| MUST-2 | Block-bootstrap CI 8h funding-cycle sensitivity（第二 block）| Spec §"Replay-First Validation" 必含 |
| MUST-3 | CSCV PBO with explicit purge + embargo | MIT V0.2 §"CV / replay controls" 必含 |
| MUST-4 | source_mode field 實際從 SQL query 區分 `ws_current` vs `rest_settled` | BB 必簽 |
| MUST-5 | adjacent-cell plateau check function | Spec §"Stage 0R promotion floor" 必含 |
| MUST-6 | Baseline lift vs no-funding/OI-confirmation baseline | Spec §"Mandatory report fields" 必含 |
| MUST-7 | Settlement-window exclusion counts + adverse-drag sensitivity | Spec §"Mandatory report fields" + MIT §"Eligibility funding attribution mode is excluded" 衍生 |
| MUST-8 | bootstrap_lower 用 pooled CI 不是 cell-level（修 eligibility checks）| Spec §"Stage 0R promotion floor: 95% block-bootstrap lower bound > 0" |

**SHOULD-FIX 列表**（report 質量 / governance hygiene，不過會被 QC push back）：

| # | 描述 |
|---|---|
| SHOULD-1 | passive_wait_healthcheck `[68]` 新增 `w_audit_8b_funding_skew_stage0r.py` |
| SHOULD-2 | Cohort coverage field（latest_ts + funding_age_ms + oi_age_ms + per-symbol coverage 表）|
| SHOULD-3 | Maker/taker split + cost-edge ratio explicit |
| SHOULD-4 | Per-symbol summary top-block in JSON |
| SHOULD-5 | block_size unit clarify（minutes 不是 raw samples）|
| SHOULD-6 | report.py 加 `--seed` argument 確保 deterministic bootstrap |
| SHOULD-7 | smoke.py 加 K_prior 邏輯測試（empty ledger 0 vs filtered N）|
| SHOULD-8 | smoke.py 加 leak-free shift(1) detection 測試（synthesize forward-leak row 確認 fail）|

### E1 估算總工時

**MUST-FIX**：~10h（包括測試）
**SHOULD-FIX**：~6h
**Total**：~16h（1.5-2 E1-day）

---

## §2 Linux PG 真實 panel 資料盤點（read-only 2026-05-16）

### `panel.funding_rates_panel`（14d window）

| 指標 | 值 |
|---|---|
| Total rows | **179,126** |
| Time span | 2026-05-11 01:30:15+02 → 2026-05-16 03:39:14+02 |
| Span days | **~5.3 days**（不是 14 days）|
| Distinct symbols | 25 |
| `source_tier` distinct | `{bybit_v5_ws_tickers}`（uniform 一個 tier） |

**Critical finding**：funding panel 只有 **5.3 days 數據窗**，spec 要 14 funding cycles ≈ 4.67 days minimum 但 PM 又要 sample span ≥ 14 cycles，**目前 28 distinct `next_funding_ms` 值**（28 cycles available）：

```
cycle_n=28, min_cycle=2026-05-11 02:00 UTC+2, max_cycle=2026-05-16 10:00 UTC+2
```

28 cycles ÷ 3 cycles/day (8h interval) ≈ 9.3 days of forward funding cycle coverage（注意 `next_funding_ms` 是「下一個 settlement」，所以 28 distinct 對應 28 future settlements；歷史 snapshot 中只能用 settlement that has already passed 做 attribution，要看 settlement-window count）。**round 1 grid 跑 OK，但 sample 可能不夠多 distinct cycles 過 MAX_DAY_OR_CYCLE_SHARE=25% gate**。

### `panel.oi_delta_panel`（14d window）

| 指標 | 值 |
|---|---|
| Total rows | **179,871** |
| Time span | 2026-05-11 01:30:15+02 → 2026-05-16 03:39:14+02 |
| Span days | ~5.3 days |
| Distinct symbols | 25 |
| `source_tier` distinct | `{bybit_v5_ws_open_interest}` |

### Overlap

**Panel 雙交集 symbols = 25**（所有 funding symbols 都有對應 OI symbols）

### `learning.strategy_trial_ledger`

| 指標 | 值 |
|---|---|
| Exists | ✅ TRUE |
| Total rows | **17,335** |
| K_prior all（distinct candidate_key 全部）| **69** |
| K_prior funding-related（LIKE '%funding%')| **9** |
| Strategy names | `{bb_breakout, funding_arb, grid_trading, ma_crossover}` |

**Schema**: `trial_id bigint / ts tstz / strategy_name text / engine_mode text / trial_family text / candidate_key text / observed_sharpe float8 / n_observations int / mean_return float8 / source text / evidence jsonb`

**MIT MUST-FIX #1 確認**：existing `fetch_k_prior()` 抓 `count(DISTINCT candidate_key) FROM ... WHERE candidate_key IS NOT NULL` 回 69 — **錯**，因為混入了 4 不相關 strategy。MIT 要求是 funding-skew-comparable 的 K_prior，**正確查詢應該是**：

```sql
SELECT count(DISTINCT candidate_key)::int
FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (strategy_name ILIKE 'funding%' OR trial_family ILIKE 'funding%')
```

對應結果 **funding-related K_prior = 9**。但 **MIT 必須最終 sign 這個 SQL 語意**，不能 PA 單方面決定。

### 5m klines（14d window）

| Symbol | rows | span |
|---|---|---|
| ETHUSDT | 4015 | 2026-05-02 → 2026-05-16 |
| BTCUSDT | 4015 | 2026-05-02 → 2026-05-16 |
| ZECUSDT | 3007 | 2026-05-02 → 2026-05-16 |
| DOGEUSDT | 2915 | 2026-05-02 → 2026-05-16 |
| SUIUSDT | 2845 | 2026-05-04 → 2026-05-16 |

**Klines 數據窗 14d 完整**（4015 rows = 14d × 288 5m bars/day），所以 panel 5.3d 是 **bottleneck**。

### `[66]` panel freshness（latest 2026-05-15 22:13 CEST）

PM review 確認 `funding=PASS(20929ms)` / `oi=PASS(20969ms)`。**panel.panel_aggregator_health table 不存在**，所以 PM 引用的是 healthcheck script `[66] panel_aggregator_health` 跑出的結果 — 由 W1-1 BB WS-first refactor 寫到 `[66]` 對應 status JSON。

### §2 結論

| 結論 | 影響 round 1 設計 |
|---|---|
| panel 數據窗 ~5.3 天（非 14 天）| Window-days argument 跑 `--window-days 5` 較實際；7-day 預設可能會空 row |
| 28 distinct funding cycles in 5.3d | 樣本足夠 grid replay；MAX_DAY_OR_CYCLE_SHARE=25% gate 可能踩線（5.3d 中如果有單一 cycle 主導）|
| 25 symbols × 4050 cells = 25 × 162 = 4050 grid OK | `K_new_min` spec 公式對得上 |
| funding_arb K_prior 為 9（funding-related）| MIT 必確認，K_total 跨 strategy family 還是 strict funding-skew comparable |
| panel 5d 窗口 + 30m primary horizon + cycles 25% gate | 「pooled n_eff ≥ 300」可能不過；建議跑 round 1 即可知道 |

---

## §3 Wave 4-A Run Plan（step-by-step）

| Step | Owner | Description | Output | Dependency | Estimate |
|---|---|---|---|---|---|
| **0** | PA | 本 Run Plan + spec gap log | 本 .md | — | DONE |
| **1** | PA | 補 spec v0.2 → v0.3 patch（8 MUST + 8 SHOULD reflected as gap log）+ `K_prior` SQL exact spec + plateau check 數學定義 + baseline 對照分支設計 | spec v0.3 + this Run Plan §1 reference table | Step 0 | 0.5d / PA |
| **2** | E1 | 補 tooling MUST-FIX #1-8 + SHOULD-FIX #1-2 + #5-#7 | code patch + smoke pass | Step 1 | 1.5d / E1 |
| **2a** | E2 + A3 | 對抗審 tool 補丁邏輯 + DSR/PBO/PSR/bootstrap 公式正確性 + leak-free shift(1) compliance | E2 verdict + A3 verdict | Step 2 | 0.5d / 並行 |
| **2b** | E4 | smoke regression（含新 K_prior 邏輯 + plateau check + baseline lift）+ leakage detection 測試 | E4 verdict（含 PASS / FAIL 數）| Step 2a APPROVE | 0.5d / E4 |
| **2c** | E1 | 跑 round 1 Linux PG smoke（`--window-days 5 --cost-bps 12`）→ `output/2026-05-16_round1_smoke.json` + `.log` | round 1 JSON + log | Step 2b PASS | 0.5d / E1 |
| **3** | PA + QC + MIT + BB | 並行 review round 1 report → 決定 round 2 grid 範圍（zoom-in / preserve / 擴）| PA decision report + 3 agent verdicts | Step 2c | 0.5d / 並行 |
| **4** | E1 | 跑 full grid（4050 cells minimum，視 panel symbols 實際 → 可能 25 × 162 不變）+ output JSON + CSV | round 2 full grid JSON | Step 3 | 0.5d / E1 |
| **4a** | A3 + E2 | round 2 結果對抗審（同 Step 2a 視角）| 對抗審 verdicts | Step 4 | 0.5d / 並行 |
| **5** | PA | 寫 Stage 0R Verdict Report（emit `eligible_for_demo_canary=true/false` + 觸發 stop rule 列舉 + Stage 1 demo canary 候選 strategy×symbol×branch 列舉 如 eligible）| `docs/CCAgentWorkSpace/PA/workspace/reports/...stage0r_verdict.md` | Step 4a | 0.5d / PA |
| **6** | PM | sign-off + push to `Operator/`copy | PM sign-off report | Step 5 | 0.5d / PM |

**Total 估時**：~5.5-6 worker-days；calendar **1-2 週**（依 round 1 結論決定 round 2 grid 範圍，部分串行）。

**Wave 4-A scope 限制**：本 Wave 結束時 **不啟動 Stage 1 demo canary**；無論 `eligible_for_demo_canary=true/false`，本 Wave 只交付 verdict report，Stage 1 啟動由 PM + operator 另開 Wave。

---

## §4 Stop / Reject 觸發明細（PM review §"Stop Rules" 10 點具體化）

| # | Stop 條件 | 觸發 condition | 偵測方式 | 負責 catch | 觸發後動作 |
|---|---|---|---|---|---|
| S1 | pooled-only pass with no eligible `strategy × symbol × branch` | `eligible_for_demo_canary=true` AND `best_primary_cell.n_eff < SYMBOL_N_EFF_FLOOR(100)` OR `branch n_eff < 50` | report JSON inspect — PA Step 5 必驗 | PA + QC | report 加 `pooled_only_pass=true` flag + 強制翻 false |
| S2 | 含糊 / 低估 K_total | round 1 K_prior=0 OR K_prior 未含 funding-comparable filter | grep `k_prior` value vs MIT signed SQL | MIT Step 3 | E1 修 query + 重跑 round 1 |
| S3 | 缺失 / 不足 power PBO 被當 waiver | `pbo=null` OR `pbo > 0.20` AND `eligible_for_demo_canary=true` | `eligibility_fail_reasons` 必含 `PBO missing or > 0.20` | QC Step 3 | report 強制 false |
| S4 | `DSR < 0.95` | best_primary_cell.dsr < 0.95 AND `eligible_for_demo_canary=true` | `eligibility_fail_reasons` 必含 `DSR < 0.95` | QC Step 3 | report 強制 false |
| S5 | 正 funding income counted without ledger-verified attribution | report `funding_attribution_mode != 'excluded'` | grep JSON | MIT Step 3 | 立即 reject + E1 重跑 |
| S6 | stale panel rows included in eligibility | `exclusions.funding_stale_excluded > 0` OR `oi_stale_excluded > 0` 但 best cell n_eff 計算未排除 | code path inspect — Step 2a E2 必驗 `_signal_rows()` 對 `funding_age > EXCLUDE_AGE_MS` 的 continue | E2 Step 2a | E1 修 `_signal_rows()` |
| S7 | post-hoc threshold expansion | round 2 grid 擴大 z_hi / p_hi / oi_min 超出 round 1 範圍 → 必加進 K_new | PA + QC Step 3 review | PA + QC | 加進 K_total + 重算 DSR |
| S8 | 復用 retired `funding_arb` code semantics | grep `from .*funding_arb` import / 直接 reuse Strategy class | E2 grep guard | E2 Step 2a | reject + 重寫 |
| S9 | production config / risk / sizing / demo / live / true-live mutation before future approval | grep diff for `risk_config*.toml` / `OPENCLAW_*` / strategy enable in TOML / authorization | E2 + E3 grep guard | E2 Step 2a | reject + Operator override required |
| S10 | carry-arbitrage framing leakage | report or code 提到 「funding income capture」「basis trade」「spot leg」「cash-and-carry」 | grep keywords | MIT Step 3 + PA Step 5 | reject + spec patch |

### 額外運行期 stop（per spec §"Promotion floor"）

| S11 | `n_eff >= 100` per symbol (active) | code 已含 check |
| S12 | `n_eff >= 50` per branch | code 已含 check |
| S13 | `pooled n_eff >= 300` | code 已含 check |
| S14 | 至少 14 funding cycles | code 已含 check |
| S15 | 單日 / 單 cycle ≤ 25% eligible rows | code 已含 check |
| S16 | `avg_net_bps >= +15` | code 已含 check |
| S17 | PSR(0) >= 0.95 | code 已含 check |
| S18 | bootstrap 95% lower bound > 0 | code 含 check 但 **MUST-FIX #8 修為 pooled CI lower bound 不是 cell-level**|
| S19 | adjacent grid cells plateau | code **MUST-FIX #5 缺**|
| S20 | no positive edge depends on unverified funding settlement income | code 已硬寫 `funding_attribution_mode = 'excluded'` |

**Stop fast-fail 策略**：round 1 smoke 跑出來 `eligible_for_demo_canary=false` + reason 5+ 個是預期；目標是看 round 2 grid 是否能 zoom-in 找到綠 cell（極大概率仍 false）。Stage 0R verdict **不是 strategy promotion 也不是 fail-strategy 結論**，僅是 design-pass / design-blocked 判定。

---

## §5 強制工作鏈（PA→E1→E2→E4→QA→PM）

### 每 step 對應 sub-agent

| Step | 強制工作鏈 | sub-agent |
|---|---|---|
| 1 PA spec patch | PA solo | `@PA`（本 session） |
| 2 E1 IMPL tool patch | PA→E1 | `@E1`（A 個 worktree 5-8 LOC chunks 因為 E1 sub-agent 可 IMPL writes per `feedback_subagent_code_writing_refusal.md`）|
| 2a E2 + A3 對抗審 | E1→E2 + A3 並行 | `@E2`（tool 邏輯 + leak compliance）+ `@A3`（DSR/PBO/PSR 數學審）+ E4 不能取代 per `feedback_impl_done_adversarial_review.md` |
| 2b E4 regression | E2/A3 APPROVE→E4 | `@E4`（smoke pass + leak-free 反例測試）|
| 2c round 1 smoke | E4 PASS→E1 | `@E1`（runtime invoke）|
| 3 QC + MIT + BB review | E1 round 1→4 agent 並行 | `@QC`（DSR/PSR/sample floor 數學）+ `@MIT`（leakage/CV/as-of join/embargo/funding-attribution）+ `@BB`（funding interval/source_mode/rate-limit posture）+ PA reconcile |
| 4 E1 full grid | PA decision→E1 | `@E1` |
| 4a A3 + E2 對抗審 | E1 round 2→A3 + E2 | `@A3` + `@E2` |
| 5 PA verdict | 4a APPROVE→PA | `@PA` |
| 6 PM sign-off | PA→PM | PM solo（main session）|

### 對抗審強制覆蓋面

**E2 對抗審**（Step 2a）：
1. K_prior SQL 語意（funding-comparable filter 正確性）
2. CSCV PBO purge + embargo 實作（time-blocked + embargo windows）
3. Block-bootstrap 60m + 8h 兩 block 公式（block_size unit + iterations）
4. `_signal_rows()` stale exclusion 邏輯（age > EXCLUDE_AGE_MS → continue）
5. Plateau check function（adjacent cells distance + tolerance）
6. Baseline lift branch（no-funding/OI-confirmation baseline 計算法）
7. Settlement-window exclusion（next_funding_ms ± window 樣本識別）
8. shift(1) leak-free（per `feedback_indicator_lookahead_bias.md`）：SQL `rolling().max()` 含 current 是已知 measurement bias；目前 metrics.py 用 `prior_5m_return_bps` source from SQL 預先計算（過去 5m close-open 區間，不含 current 5m signal_ts_ms），**設計 leak-free**；E2 必驗 SQL 中 `prior_5m_return_bps` 對應 `k.open` and `k.close` 對應 same bar with `close_ts_ms <= signal_ts_ms - 5m` boundary 邏輯（目前 SQL 是 `b.open_ts_ms / b.signal_ts_ms` same bar — **需要 E2 確認** prior return 是「signal_ts_ms 之前已 closed 的 5m bar 的 return」不是「同一個 5m bar 自身 return」）

**A3 對抗審**（Step 2a）：
1. PSR(0) Bailey-LdP 公式正確性（含 skew + kurt）
2. DSR with explicit K_total（sr_benchmark = √(2 ln K)）
3. PBO 算法（CSCV time-blocked）
4. 樣本 floor 對統計 power 影響（n_eff=100 是否足以 stable DSR）
5. cohort 25-sym cross-sectional zscore 在 5d 5.3d 數據下穩定性

**E4 regression**（Step 2b）：
1. smoke fixture PASS（既有 360 ts × 3 symbols 跑通）
2. 新增 K_prior 邏輯測試（empty ledger / 9 funding rows / 69 全平台）
3. 新增 leakage detection 測試（synthesize 一個 forward-leak row 確認被 catch）
4. plateau check 測試（fixture 含 3 cells 有 plateau / 3 cells 無 plateau，verify 對結果不同 verdict）
5. baseline lift 測試（baseline branch return = 0 verify lift = avg_net 自身）

**QC adversarial**（Step 3）：DSR/PBO/sample floor 數學審

**MIT 審**（Step 3）：
1. raw `panel.funding_rates_panel` + `panel.oi_delta_panel` as-of join 正確性（SQL LATERAL `snapshot_ts_ms <= signal_ts_ms ORDER BY DESC LIMIT 1`，**符合**）
2. funding-attribution `excluded` 嚴格性
3. CV protocol（walk-forward / purged k-fold / CSCV with embargo ≥ max(7d, 2×half_life)）
4. Purge & embargo 是 MUST-FIX #3 IMPL 必驗
5. K_prior query 簽 OFF SQL semantic

**BB 審**（Step 3）：
1. funding semantics 正負方向（positive funding = longs pay shorts）
2. funding interval per-symbol（不假設 8h；目前 SQL 從 next_funding_ms 推 ok）
3. ws_current vs rest_settled 區分（MUST-FIX #4）
4. rate-limit posture 維持 WS-first（tooling 純 PG SELECT 不打 REST，OK）

### Adversarial review 不可跳

per `feedback_impl_done_adversarial_review.md` — **E4 regression 不能取代 E2 + A3 對抗審**。Round 1 smoke 跑前必 E2 + A3 APPROVE，否則退回 E1 修。

---

## §6 Round 1 smoke 預期報告長相（JSON skeleton）

E1 寫 `helper_scripts/reports/w_audit_8b/output/2026-05-16_round1_smoke.json`：

```json
{
  "strategy_variant": "funding_skew_directional.v0_2",
  "alpha_source_id": "funding_skew_directional",
  "funding_attribution_mode": "excluded",
  "source_mode": "ws_current",
  "cost_bps": 12.0,
  "window_days": 5,
  "generated_at_utc": "2026-05-16T...:00Z",
  "panel_freshness": {
    "funding_latest_ts": "2026-05-16T01:39:14Z",
    "funding_age_at_run_ms": 12345,
    "funding_source_tier": "bybit_v5_ws_tickers",
    "oi_latest_ts": "2026-05-16T01:39:14Z",
    "oi_age_at_run_ms": 12345,
    "oi_source_tier": "bybit_v5_ws_open_interest"
  },
  "cohort_coverage": {
    "symbols": ["BTCUSDT", "ETHUSDT", ...],
    "symbol_count": 25,
    "funding_cycles_distinct": 28,
    "row_count": 179126,
    "by_symbol_coverage": {
      "BTCUSDT": {"funding_rows": 7165, "oi_rows": 7185, "kline_5m_rows": 4015}
    }
  },
  "k": {
    "k_prior": 9,
    "k_prior_query": "SELECT count(DISTINCT candidate_key) FROM learning.strategy_trial_ledger WHERE candidate_key IS NOT NULL AND (strategy_name ILIKE 'funding%' OR trial_family ILIKE 'funding%')",
    "k_prior_signed_by": "MIT(pending)",
    "k_new": 4050,
    "k_total": 4059
  },
  "exclusions": {
    "funding_missing": 0,
    "funding_stale_excluded": 12,
    "funding_warn_age": 5,
    "oi_missing": 0,
    "oi_stale_excluded": 8,
    "oi_warn_age": 3,
    "settlement_window_exclusions": 245
  },
  "pooled_primary": {
    "n": 1280,
    "n_eff": 213,
    "avg_gross_bps": 2.5,
    "avg_net_bps": -9.5,
    "psr_0": 0.45,
    "dsr": 0.001,
    "bootstrap_ci_95_60m": [-15.2, 4.1],
    "bootstrap_ci_95_8h_funding_cycle": [-18.5, 6.2]
  },
  "branch_summary": {
    "crowded_long_fade": {"n": 640, "n_eff": 106, "avg_net_bps": -8.2},
    "crowded_short_squeeze": {"n": 640, "n_eff": 106, "avg_net_bps": -10.8}
  },
  "per_symbol_summary": [
    {"symbol": "BTCUSDT", "n": 64, "n_eff": 10, "avg_net_bps": -5.5, "best_branch": "crowded_long_fade"},
    {"symbol": "ETHUSDT", "n": 60, "n_eff": 10, "avg_net_bps": -12.0, "best_branch": "crowded_short_squeeze"}
  ],
  "pbo": 0.65,
  "best_primary_cell": {
    "candidate_key": "BTCUSDT|crowded_long_fade|z=2|p=0.95/0.05|oi=2|h=30",
    "symbol": "BTCUSDT",
    "branch": "crowded_long_fade",
    "z_hi": 2.0, "p_hi": 0.95, "p_lo": 0.05, "oi_min_pct": 2.0, "horizon_min": 30,
    "n": 12, "n_eff": 2,
    "avg_gross_bps": 8.5, "avg_net_bps": -3.5,
    "psr_0": 0.62, "dsr": 0.01,
    "bootstrap_ci_95_60m": [-12.0, 5.0],
    "funding_cycles": 5,
    "max_day_share": 0.42,
    "max_funding_cycle_share": 0.33,
    "funding_interval_min": 480
  },
  "top_primary_cells": [...],
  "plateau_check": {
    "best_cell_plateau_neighbors_count": 0,
    "plateau_threshold_neighbors_min": 2,
    "plateau_pass": false
  },
  "baseline_lift": {
    "baseline_branch": "no_funding_no_oi_confirmation",
    "baseline_avg_net_bps": -2.1,
    "best_lift_bps": -1.4,
    "lift_positive": false
  },
  "maker_taker_split": {
    "maker_pct": 0.0,
    "taker_pct": 1.0,
    "cost_edge_ratio": null,
    "note": "round1 conservative taker-only cost assumption"
  },
  "settlement_window_adverse_drag": {
    "samples_near_settlement_count": 240,
    "samples_far_from_settlement_count": 1040,
    "avg_net_near_settlement_bps": -22.0,
    "avg_net_far_settlement_bps": -7.5,
    "drag_estimate_bps": 14.5
  },
  "eligible_for_demo_canary": false,
  "eligibility_fail_reasons": [
    "symbol n_eff < 100",
    "branch n_eff < 50",
    "pooled n_eff < 300 (but check borderline)",
    "single-day share > 25%",
    "single funding-cycle share > 25%",
    "avg_net_bps < +15",
    "PSR(0) < 0.95",
    "DSR < 0.95",
    "PBO missing or > 0.20",
    "bootstrap lower bound <= 0",
    "plateau check fail"
  ],
  "verdict_meta": {
    "verdict_signed_at": null,
    "verdict_signed_by": null,
    "round": 1,
    "purpose": "smoke + decision input for round 2 grid"
  }
}
```

**核心 fields contract**（E1 不能缺）：`strategy_variant` / `alpha_source_id` / `funding_attribution_mode` / `source_mode` / `panel_freshness` / `cohort_coverage` / `k` (with `k_prior_query` 字串)/ `exclusions` / `pooled_primary` (含 60m + 8h CI two)/ `branch_summary` / `per_symbol_summary` / `pbo` / `best_primary_cell` / `plateau_check` / `baseline_lift` / `maker_taker_split` / `settlement_window_adverse_drag` / `eligible_for_demo_canary` / `eligibility_fail_reasons` / `verdict_meta`.

Round 1 預期 `eligible_for_demo_canary=false`（高概率），原因 listed above 6+ 個 fail；round 2 grid 仍極大概率 false（panel 數據窗 5.3d 不足以 hit n_eff 300 + 14 cycles + DSR 0.95 同時）。

---

## §7 風險識別

### R1 — Look-ahead bias（per `feedback_indicator_lookahead_bias.md`）

**現有 design 評估**：SQL 中 `prior_5m_return_bps` 用 `(k.close - k.open) / k.open`，**對應 same bar** with `close_ts_ms` 在 `signal_ts_ms` 上對齊 — 這意味著 signal_ts_ms = 該 5m bar 的 close_ts_ms。**RISK**：metrics.py 在 `_signal_rows()` 用 `prior <= 0` / `prior >= 0` 作為 signal-time 條件，但 SQL 邏輯是 `k.close_ts_ms` AS `signal_ts_ms` AND `prior_5m_return_bps` 是 same bar return。**這代表 signal 是在 5m bar close 那一刻發出**，prior return 是 _that_ bar 的 return，**不是 prior closed bar 的 return**。

- **如果 signal 是 bar close 的同一 tick 出**（intuition: "after close I see this bar's return is X, I now act on next bar's fwd_return_30m"），則 OK；
- **如果 signal 是 bar 內任意 tick 出**（intuition: "during this 5m I look at running return"），則含 partial bar **這是 leak**。

**Round 1 設計 lock**：`signal_ts_ms = k.close_ts_ms` AND `prior_5m_return_bps = same bar return`，**契約是「signal fired at bar close, using closed bar's return」**。E2 + MIT Step 3 **必明文簽**這個 boundary。

**Cross-check fwd_return windows**：
- `f15.close_ts_ms >= signal_ts_ms + 900000` ✓
- `f30.close_ts_ms >= signal_ts_ms + 1800000` ✓
- `f60.close_ts_ms >= signal_ts_ms + 3600000` ✓

forward windows 起點 ≥ signal_ts_ms + horizon, **leak-free**。

**E2 對抗審必加 leak-free 反例測試**（per §5）：synthesize 一個「signal_ts_ms 與 fwd close_ts_ms 重疊」row，確認 metrics catch。

### R2 — `[55]` partial fill ER 影響 cost-edge ratio

per CLAUDE.md §三 — `[55]` SOURCE-FIX VERIFIED 2026-05-15；partial chains 13 separate 計數，full-fill chain `chains_with_full_plan_fill=25`。

**Round 1 影響**：tooling 在 `_signal_rows()` cost 是 fixed `cost_bps=12.0`（taker-only conservative），**不從 `trading.fills` 抓真實 cost** — 所以 partial fill ER 對 round 1 cost-edge ratio **無直接影響**。但 SHOULD-FIX #3 (maker/taker split + cost-edge ratio) 如果未來 E1 從 fills 抓 cost histogram 時，**必排除 partial-fill chains**（per `[55]` invariant) 或單獨計算 partial vs full-fill cost。

**Round 1 lock**：cost 用 fixed 12 bps taker conservative + 標明 `note`；round 2 視需要 IMPL real-cost 抓取。

### R3 — Panel staleness > 60s WARN / > 300s FAIL in replay

spec 寫 `age_ms > 60s WARN/diagnostic`, `age_ms > 300s eligibility exclusion + runtime no-action`。**replay 階段如何處理 vs live 階段如何處理**有差：

- **live 階段** → strategy emit no-action（不下單）
- **replay 階段** → row exclusion from eligibility（不計入 n / n_eff / cells）

現有 `_signal_rows()` 邏輯：
```python
if funding_age > EXCLUDE_AGE_MS or oi_age > EXCLUDE_AGE_MS:
    continue
```
**正確** — replay 直接 skip stale row → exclusion count 上去 → 不污染 n。

WARN tier（60-300s）目前 **進入 cells** 計算但 counted in `funding_warn_age` / `oi_warn_age`，這是 informational 不 exclude。**E2 對抗審必確認** WARN tier 是否該進 cells（spec 沒明寫 WARN 是 diagnostic vs eligibility-excluded）。建議：WARN 進 cells + report 顯示，但 round 1 結果如果 best cell 含大量 WARN-tier samples 必降 confidence。

### R4 — 14 funding cycles 樣本是否充足（Bybit funding interval 通常 8h, 14×8h = 4.67 days）

實測 panel 28 distinct `next_funding_ms` 在 5.3d window → **形式上 28 cycles 過 14 cycle 門檻 2x 餘**。**但 `next_funding_ms` 是「下一 settlement」，多個 snapshot 共享同一 `next_funding_ms` 直到 settlement 過去**。
- 5.3 days × 3 cycles/day = ~16 完整 cycle interval
- 28 distinct `next_funding_ms` 包含 ~16 past settled + ~12 forward settling

**spec §"sample must span at least 14 funding cycles" 預設邏輯：14 distinct cycles in signal sample**。grid 觸發的 signal 數量會被 sample 散布在 cycles 範圍上，目前 metrics.py 用 `cycles = Counter(str(s.get("next_funding_ms")))` 計 cycle distribution，**這個邏輯對**。

**Round 1 預期 cycle_n in best cell**：5-12（5.3d window 不夠覆 14；眾多 cell 對應 single-cycle dominated）→ 觸發 `funding cycles < 14` fail reason 大概率出。

**降階 action**：給 round 1 spec 加 `WAITING_MORE_PANEL_DATA` flag — 不是 fail-strategy，是 panel 數據窗 partial → 延後 round 2 grid 至少 3-5 days 累積 data。

### R5 — strategy_trial_ledger K_prior funding-comparable filter

per §2 / MIT MUST-FIX #1：K_prior 9 (funding-related) vs 69 (全平台)。**MIT 必簽 SQL**。**Round 1 必須 explicitly 標明 SQL 字串 + signed by 在 JSON output 中**（per §6 schema）。否則 PBO/DSR 全失語意。

### R6 — Bybit demo endpoint silent degradation（per `feedback_demo_loose_live_strict_policy.md` + Bybit API ref §4.3#14）

**Round 1 不打 demo endpoint**，純 PG SELECT；不涉及。**Future Stage 1 啟動時必加 endpoint hardening**。

### R7 — Multi-session memory race（per `project_multi_session_memory_race.md`）

PA 改 memory + commit during multi-session Mac 可能被 revert。本 Run Plan + memory entry 同 commit + commit-first 規矩。

### R8 — Sub-agent 不能 spawn 二層

per Anthropic 限制：本 PA 不開 sub-agent。`@PA` 設計交付後由 main session 派 `@E1` `@E2` `@A3` `@E4` `@QC` `@MIT` `@BB`。

---

## §8 16-root-principles 對照（100% read-only verify）

本 packet 為 spec/design phase + read-only tool patch，不觸 §四硬邊界，不觸 16 原則任何一條。

| # | 原則 | 觸碰? | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ❌ 否 | tooling 純 SELECT，無 IntentProcessor 路徑 |
| 2 | 讀寫分離 | ❌ 否 | tooling 純 SELECT，無 _authorize_write 路徑 |
| 3 | AI 輸出 ≠ 命令 | ❌ 否 | tooling 純 metric 計算 + JSON 輸出，無 lease 路徑 |
| 4 | 策略不繞風控 | ❌ 否 | tooling 不下單，不經 Guardian |
| 5 | 生存 > 利潤 | ❌ 否 | tooling 不下單 |
| 6 | 失敗默認收縮 | ✅ 維持 | replay 階段 stale panel row 直接 exclude（fail-closed at sample level）|
| 7 | 學習 ≠ 改寫 Live | ❌ 否 | replay 輸出 JSON only；不寫 ML training table，evidence_source_tier 不適用 |
| 8 | 交易可解釋 | ❌ 否 | tooling 不下單 |
| 9 | 災難保護 | ❌ 否 | tooling 不下單 |
| 10 | 認知誠實 | ✅ 維持 | report 顯式區分 panel_freshness fact / k_prior 推斷 / eligible verdict 假設 |
| 11 | Agent 最大自主 | ❌ 否 | tooling 不涉 cognitive_modulator |
| 12 | 持續進化 | ✅ 維持 | round 1 → round 2 grid zoom 即進化路徑 |
| 13 | AI 成本感知 | ❌ 否 | tooling 純 PG query 0 AI 調用 |
| 14 | 零外部成本可運行 | ✅ 維持 | tooling 純 Linux PG，無 Ollama/Claude 依賴 |
| 15 | 多 Agent 協作 | ✅ 維持 | §5 強制工作鏈 6 agent 並行 |
| 16 | 組合級風險 | ❌ 否 | tooling 不影響 portfolio_risk |

### 硬邊界（CLAUDE.md §四）對照

| 硬邊界項 | 觸碰? |
|---|---|
| `live_execution_allowed` | ❌ 否 |
| `max_retries=0` | ❌ 否 |
| `system_mode` mutation | ❌ 否 |
| `execution_state` / `execution_authority` | ❌ 否 |
| `decision_lease_emitted` | ❌ 否 |
| `OPENCLAW_ALLOW_MAINNET` | ❌ 否 |
| `live_reserved` | ❌ 否 |
| `authorization.json` 改動 | ❌ 否 |
| Operator 角色繞過 | ❌ 否 |

### DOC-08 §12 9 條安全不變量對照

| # | 不變量 | 適用? | 觸碰? |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | 不適用（無 trade）| ❌ |
| 2 | Lease 必在執行前已 acquired | 不適用 | ❌ |
| 3 | 執行回報必落 fills 表 | 不適用 | ❌ |
| 4 | 風控降級 → engine 自動止血 | 不適用 | ❌ |
| 5 | Authorization 過期/失效 → cancel_token shutdown | 不適用 | ❌ |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | 不適用 | ❌ |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | 不適用 | ❌ |
| 8 | Reconciler 對賬差異 → 自動降級 paper | 不適用 | ❌ |
| 9 | Operator 角色與 live_reserved 缺一即拒 | 不適用 | ❌ |

### AMD-2026-05-15-01 canary rebase 對照

`eligible_for_demo_canary=true/false` 是本 Stage 0R **唯一輸出**（per AMD §核心契約）；本 Wave 4-A **不執行 Stage 1 demo micro-canary**，**不開** `Environment::Demo`，**不觸** OPENCLAW_ENABLE_PAPER（保持 0），**不開** authorization。

### 評級

| 評級 | 16/16 | 硬邊界 | DOC-08 |
|---|---|---|---|
| **A** | ✅ 16/16 完全合規 | ✅ 0 觸碰 | ✅ 0 觸碰（不適用項 9/9 N/A）|

---

## §9 BLOCKING risks / Open Questions

### B1（HIGH）— Panel 數據窗 5.3d 可能不夠

panel data 從 2026-05-11 才開始（5.3 days），spec floor 是「sample span ≥ 14 funding cycles」 即 ~4.67 days 8h × 14。形式上 28 cycles 過門檻 2x；但 best cell sample 可能集中在 5-12 cycles，**單一 cycle share > 25% gate 大概率 fail**。

**Mitigation**：round 1 跑下去看；如 cycle share > 25% 主導 → 推遲 round 2 至 panel 累積 8-10 天再跑 grid（即 D+3-5 calendar 延後）。

### B2（MEDIUM）— K_prior SQL semantic 未 MIT signed

`fetch_k_prior()` 目前用全平台 distinct candidate_key (69)。MIT 必簽 funding-comparable filter SQL。**Round 1 跑前必 MIT review** 不是 PA 單方面選一個 filter。

**Mitigation**：Step 1 PA spec patch 含 SQL draft → Step 3 MIT 簽 → 必要時 round 1 重跑 with revised SQL。

### B3（MEDIUM）— K_total 真實值依賴 ledger filter

如 K_prior=9，K_new=4050，K_total=4059 → `sr_benchmark = √(2 × ln(4059)) = √16.6 = 4.07`。**DSR threshold 0.95 對應 PSR(0) 在 sr_hat 約 5-6 才能 pass**。實際數據 sr_hat 大概率 < 1（5d 5.3d window 樣本 sharpe 估計 noise 大）→ DSR 大概率遠 < 0.95，`eligible_for_demo_canary=false` 是大概率結論。

**Mitigation**：這不是 packet 的 stop — 這是 packet 設計的 expected outcome（spec v0.2 顯式要 DSR ≥ 0.95 with K_total，這對 alpha source candidate 是強濾網）。Verdict 寫 `eligible_for_demo_canary=false` 是 design-pass 不是 design-fail。

### B4（LOW）— Settlement-window adverse drag 識別法 spec 未明寫

spec 寫 "settlement-window counts and adverse-drag sensitivity" 但**沒給定義**（next_funding_ms ± 多少 ms？next_funding_ms - 30m 至 +30m？）。

**Mitigation**：Step 1 PA spec patch 補 「signal_ts_ms 距 next_funding_ms < 30m 為 near-settlement，其餘 far-from-settlement」+ 加 sensitivity comparison。MIT 簽 OFF。

### B5（LOW）— funding_arb K_prior 是否 reuse-able for `funding_skew_directional`

`funding_arb` retired by ADR-0018，但 9 個 candidate_key 留在 ledger。**Reframe 後 K_prior 還算嗎？**

**Mitigation**：MIT 簽 — 嚴格 interpretation 是 `funding_skew_directional` 不繼承 `funding_arb` K_prior（不同 hypothesis 不同 candidate space）→ K_prior=0 + K_new=4050 → K_total=4050 → `sr_benchmark = √(2 ln 4050) = 4.07` 變動極小。或 conservative 加 9 → K_total=4059。Verdict report 必標明 MIT-signed choice。

### Open Questions（spec v0.2 §"Open Questions" 3 點，本 Run Plan 答覆）

| Q | Spec 問 | PA 答覆 |
|---|---|---|
| Q1 | v0.2 fixed 5m price-action 充足 vs 預註冊 narrower variants | **充足為 round 1**；preregistered variants 留 round 2 zoom-in（如 round 1 出 marginal cell）|
| Q2 | MIT exact K_prior query | per §2/B5：MIT 必 sign；建議 conservative K_prior=0（strict candidate space separation）+ 9 fallback 同 report 顯示 |
| Q3 | BB sign funding interval / source-mode fields | 本 Run Plan §1 MUST-FIX #4 IMPL；BB Step 3 必簽 |

---

## §10 Final Summary

**Run Plan status**: DESIGN-COMPLETE / waiting PM dispatch
**Wave 4-A scope**: 1-2 週；6 steps；6 owner roles
**Total estimate**: 5.5-6 worker-days
**Critical path**: Step 1 PA spec patch → Step 2 E1 IMPL 8 MUST-FIX → Step 2a E2+A3 對抗審 → Step 2b E4 regression → Step 2c round 1 smoke → Step 3 4-agent review → Step 4 round 2 full grid → Step 5 PA verdict → Step 6 PM sign-off
**Expected verdict**: `eligible_for_demo_canary=false` (high probability) — design-pass not strategy-promotion
**A 級 16 原則 + 硬邊界 0 觸碰 + DOC-08 不適用**

**Hand-off**: 主 session（PM）接收本 Run Plan → 派 Step 1 PA spec v0.3 patch（self-dispatch）+ Step 2 `@E1` MUST-FIX IMPL（並行）。

**Sign-off path**: PA self-sign Step 0/1/5 → 主 session PM Sign-off Step 6.

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_run_plan.md

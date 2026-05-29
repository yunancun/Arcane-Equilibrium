# A1/A2 Candidate Stage 0R Runner — IMPL Spec

**Date**: 2026-05-29
**Author**: PA (design only; read-only ssh SELECT/cat; no IMPL / no runtime / no IPC)
**Version**: **v2 — SUPERSEDES v1** (same-day rewrite after QC pre-check)
**Chain**: `PM -> PA(this) -> E1 IMPL -> QC stat review(必, 驗 A1 cohort gate 方向+統計) -> E2 adversarial -> E4 regression -> PM`
**Risk grade**: 中（純 offline analysis；不觸 Rust engine / IPC / 5-gate / Decision Lease；但 A1 需新 metrics + SQL，較 v1 大）
**標記法**: [FACT] cat/grep 直接觀測 / [INFER] 由 fact 推導 / [ASSUME] 待證實

---

## §0 為什麼 v2 取代 v1（QC 方向修正記錄 — 必讀）

v1 設計「A1 復用 8b harness」**結構性錯誤**，QC pre-check 三項裁決全部成立，本 PA 親自 cat 8b source 逐條核實（[FACT]）：

| QC finding | PA cat 核實 | 證據 |
|---|---|---|
| **#1 方向接反** | 成立 | v1 §6.4 #2 寫 A1 → 8b `crowded_short_squeeze`。但 8b `_signal_rows` line 388-394：`crowded_short_squeeze` gate = `z <= -z_hi and pct <= p_lo`（funding **負低側** → direction=+1 **做多**）。A1 = funding **正高** > 30% annualized → **做空 fade**，對映方向是 `crowded_long_fade`（line 380-387：`z >= z_hi` → direction=-1 short）。v1 接反 180°。 |
| **#2 本質不等價** | 成立 | 8b gate 全用 `funding_zscore_25sym`（cross-sectional z-score）+ `funding_percentile_25sym` + `oi_delta_15m_pct` + `prior_5m_return` 四維（`_signal_rows` line 372-394）。A1 gate = **絕對** funding_annualized > 30% + **basis_pct < 0.3%** + short-only + 動態 OR 出場（A1 spec §1.1-§1.2）。8b 無 absolute funding 閾值、無 basis 欄位、無動態出場、baseline 是 `prior_5m_direction`（line 448-451）非 basis。即使接對 branch 也是不同策略。 |
| **#3 2 vs 25 symbol 硬衝突** | 成立 | 8b `MIN_STAGE0R_SYMBOLS=25` 是 `_candidate_fail_reasons` line 1050 + `_sweep_branch_fail_reasons` line 1368 的 **hard fail**（`symbol_count < 25` → 永 ineligible）。且 z-score 由 SQL `PARTITION BY signal_ts_ms`（features.sql line 76-99 全 cohort median/std/percent_rank）算；BTC/ETH 2-symbol → 每 timestamp n=2，z-score = ±0.707 恒定（無統計意義）。 |
| **#4 leak-free 不可改** | 成立 | 8b/8c SQL forward-return（嚴格未來 bar）/ LATERAL as-of / cutoff 全 leak-free（[FACT] cat 直驗，見 §3）。**不改 8b/8c SQL 結構**。 |

**operator 拍板（2026-05-29）**：加 **A1 專屬 cohort 路徑**（忠實復現，非 proxy）。8b harness 對 A1 整體報廢；只復用 8b/8c 的**純統計原語**（PSR/DSR/PBO/bootstrap/Wilson/n_eff，direction-agnostic、leak-free、無 cohort 依賴）。

---

## §1 A1 與 A2 路徑決策（核心重設計）

| candidate | v1 設計 | v2 設計（修正後） | 為什麼 |
|---|---|---|---|
| **A1 funding_short_v2** | 復用 8b harness（錯）| **A1 專屬 metrics + 專屬 SQL（新 leak-free query）** | 8b 整個 signal gate / cohort stat / 25-symbol fail / baseline 全與 A1 不相容（QC #1#2#3）。只能新建。 |
| **A2 liquidation_cascade_fade** | 復用 8c harness | **復用 8c per-event 路徑 + candidate-cohort adapter（不新建 SQL）** | 8c 本就 per-event（無 cross-sectional cohort stat），方向與 A2 一致；只需 thin adapter 修 3 處（見 §2.4）。 |

**[FACT] 8c 同檢結論（QC 只深查 A1，PA 補查 8c）**：

1. **無 25-symbol cross-sectional cohort 污染**：8c 全程 per-event/per-bucket。`_extract_trigger_rows`（line 951-1082）+ `prepare_parsed_rows`（line 882-948）直接從 SQL row 取 `dominant_side` / `expected_dir`，**無 `PARTITION BY signal_ts_ms` median/std/z-score**。features.sql 唯一 `percent_rank()` 是 `PARTITION BY symbol`（line 209-213，per-symbol 24h 時序 rolling，非橫截面）→ 2-symbol 完全有效。
2. **方向與 A2 一致**：8c `expected_dir = +1 (long_liquidated → mean-revert UP)`（features.sql line 203-208）。A2 `entry_is_long = LongLiquidated → true`（A2 spec line 58-61）= fade long-liq → long entry。**語意完全一致**，無 v1 A1 的方向接反問題。
3. **無 `symbol_count < 25` hard RED**：8c `compute_stage0r` 的 `other_red_reasons`（line 1473-1511）**無** symbol-count gate（與 8b 不同）。25 的唯一出現 = `k_new = max(MIN_STAGE0R_SYMBOLS, n_symbols) * 11664`（line 1388）→ 純 DSR 多重比較 penalty inflation，**不阻塞 eligibility**。
4. **唯一 A2 fidelity gap（必須 adapter 修）**：
   - (a) **k_total trial-count 失真**：line 1388 把 k_new 釘成 `25 × 11664 = 291,600`（8c 研究 sweep 的 11664-cell grid）。A2 candidate run = 固定單一閾值（$500k/$300k）、不掃 11664 cell → 真實 trial count ≪ 291600。沿用會把 DSR benchmark `√(2 ln 291600) ≈ 5.0` 拉到不公平高位，A2 永 DSR fail。**adapter 必須以 candidate 真實 trial count override k_total**（2 symbol × 2 direction × 1 threshold-set × 1 horizon ≈ 4，外加保守 prior；見 §4.3）。
   - (b) **動態出場 vs 固定 horizon**：8c forward-return 用固定 `horizon_min` mark（features.sql CTE 4 `bucket_end + quiet + horizon` 之後第一根 1m open）。A2 真實出場 = OR(TP 1.5% / SL 2% / 1h time-stop / reverse-cascade)（A2 spec line 73-83）。8c 固定 60min-mark 是 A2 的**保守 proxy**（持滿 horizon 不提前 TP/SL）。

**A2 結論**：8c per-event SQL + leak-free 結構**可沿用、不新建 SQL**。但 8c 固定 horizon ≠ A2 動態出場 → 屬「**忠實度部分缺口**」。兩個選項，本 spec 取 **B（誠實標 proxy）**，A 留待 Sprint 3：

- **A（完全忠實）**：新建 A2 dynamic-exit SQL（在 8c trigger row 上加 path-dependent TP/SL/time-stop/reverse 掃描）。LOC +120-180 SQL，複雜度高，且 reverse-cascade 需 join 後續 pulse window。
- **B（本 spec 採用）**：沿用 8c 固定 horizon=60m（= A2 max_hold default），**adapter packet 明文標 `exit_model: "fixed_horizon_60m_conservative_proxy"`** + `dynamic_exit_not_modeled: ["TP_1.5pct","SL_2pct","reverse_cascade"]`，QC review 記 waiver。固定 horizon 不含 TP（少賺）也不含 SL（多虧），方向上 **保守偏低估** alpha → 若 proxy 已 PASS，真實動態出場只會更好；若 proxy fail，需 A 路徑或更多樣本判別，標 `observe_more` 不 reject。

> A2 cohort + 閾值 pin 也是 candidate-specific（BTC $500k / ETH $300k，per-symbol notional floor，非 8c sweep grid），故 A2 走 adapter 而非直呼 8c CLI。

---

## §2 模塊放置 + 接線

```
helper_scripts/reports/alpha_candidate_stage0r/
  __init__.py                          (new, ~3 LOC)
  candidate_stage0r_runner.py          (new, ~180-240 LOC — argparse + 雙 candidate 配置 + verdict 映射 + JSON/md render)
  a1_funding_short_metrics.py          (new, ~220-300 LOC — A1 專屬 signal gate + 復用統計原語)
  a2_cascade_adapter.py                (new, ~90-140 LOC — 8c per-event 路徑 + candidate-cohort override)
helper_scripts/reports/alpha_candidate_stage0r.py   (new shim, ~15 LOC — 委派 package)
sql/queries/
  alpha_candidate_a1_funding_short_features.sql      (new, ~70-90 LOC — A1 leak-free 專屬 query)
```

**復用（不重造、不改）**：
- A1 統計：`from ...w_audit_8b.funding_skew_stage0r_metrics import psr_bailey_ldp, dsr_with_k, block_bootstrap_ci, wilson_ci_95, _pbo, _n_eff`（direction-agnostic、純函數、leak-free）。
- A2 trigger 提取 + 8c metrics：`from ...w_audit_8c.liquidation_cluster_stage0r_metrics import compute_stage0r, prepare_parsed_rows`（8c per-event `compute_stage0r` 直接可呼，只需傳 candidate 參數 + override k_total）。
- A2 SQL：沿用 `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`（**不動**），symbols 綁 `["BTCUSDT","ETHUSDT"]`、floor_usd 綁 per-symbol。
- conn / read_sql 範式：mirror 8b/8c report wrapper `_get_conn` (psycopg2 read-only + statement_timeout) + `_repo_root()` env 解析（跨平台，CLAUDE §六）。
- **必更新** `helper_scripts/SCRIPT_INDEX.md`（CLAUDE §七 hard rule）。

---

## §3 A1 專屬 cohort 路徑（核心 IMPL — leak-free 硬要求）

### §3.1 A1 SQL（新建 `alpha_candidate_a1_funding_short_features.sql`）

**沿用 8b features.sql 的 leak-free 結構模板，但移除 cohort stat、加 absolute funding + basis**：

| 項目 | A1 SQL 設計 | leak-free 不變量（沿用 8b pattern） |
|---|---|---|
| 來源 | `panel.funding_rates_panel`（funding）+ `panel.basis_panel`（basis；見 §3.4 [ASSUME] 待 E1 ssh 驗表名）+ `market.klines 5m`（fwd return）| 同 8b：LATERAL as-of |
| signal 取值 | LATERAL `snapshot_ts_ms <= signal_ts_ms ORDER BY DESC LIMIT 1`（point-in-time，**不含 future**）| **直接複製 8b line 47-62 LATERAL 模式** |
| **funding 閾值** | `funding_rate_8h_annualized > 0.30` 直接比較（`funding_rate_bps` 換算 annualized）；**無 z-score、無 cohort median/std** | 直接閾值比較，**無 rolling-extreme breach**（per memory `feedback_indicator_lookahead_bias`）|
| **side 強制** | `funding_rate_bps > 0`（positive → short receives）| 確定性 gate |
| **basis gate** | `basis_pct < 0.003`（A1 spec §1.1 #3：0.5% × 0.6）| point-in-time basis snapshot（LATERAL as-of，同 funding）|
| fwd return | `signal_ts_ms + 3600000` 之未來 5m kline（60m horizon = A1 1.5-cycle hold proxy；sensitivity 30m/8h）| **直接複製 8b line 63-74 future-bar join** |
| cutoff | `close_ts_ms <= now - 3600000`（無 partial-bar）| 同 8b line 20 |
| cohort | `symbol = ANY(%(symbols)s)` = `["BTCUSDT","ETHUSDT"]` | **無 `PARTITION BY signal_ts_ms`**（A1 是 per-symbol 絕對閾值，不需橫截面）|

**E1 硬約束**：A1 SQL 不得引入任何 `PARTITION BY signal_ts_ms` median/std/percent_rank（那是 8b cohort 污染源）；不得用 `rolling(N).max()` 或含-current-bar breach。funding/basis 均 LATERAL as-of，fwd return 嚴格未來 bar。**這是新 SQL，必走 V### 等級的 leak-free 設計 review（QC + E2），但因純 SELECT 無 DDL 不需 migration**。

### §3.2 A1 signal gate（`a1_funding_short_metrics.py`）

純 Python，對 A1 SQL row 逐 row 套 A1 entry gate（忠實復現 A1 spec §1.1 5 條件中可離線重建的 4 條；cooldown 第 5 條在 entry-event dedup 處理）：

```
A1 signal（per row, leak-free — 全部用 signal_ts_ms 當下或 as-of 值）:
  funding_ann   = annualize(funding_rate_bps)        # 絕對, 非 z-score
  gate = (funding_ann > 0.30)                          # #1 absolute funding
         and (funding_rate_bps > 0)                    # #2 short-only side
         and (basis_pct < 0.003)                        # #3 basis gate
         and (compute_edge(funding_rate_bps) > 0)       # #4 per-cycle edge > 0
  if gate:
      direction = -1   # SHORT ONLY (hard; 永不 long)
      gross_bps = direction * fwd_return_bps            # short → 跌賺
      net_bps   = gross_bps - cost_bps(22.0)            # A1 per-cycle cost model
      + per-symbol 8h cooldown dedup（同 funding cycle 不重入；mirror 8b next_funding settlement dedup 概念）
```

- `compute_edge` / `cost_bps=22.0` / per-cycle amortize 全照 A1 spec §1.1 #4 + cost model（line 87-101），E1 直接照搬 A1 spec 公式，**不自創**。
- cooldown dedup：A1 spec 8h per-symbol cooldown → 同一 funding cycle（8h）內只取首個 trigger，避免同 cycle 重複計入膨脹 n（mirror 8b `settlement_window` / funding-cycle Counter 概念，line 710-712）。

### §3.3 A1 統計（復用 8b 原語，無新算法）

對 A1 signal 的 `net_bps` 序列直接餵 8b 純統計函數：
- `psr_bailey_ldp(net)` → PSR(0)
- `dsr_with_k(net, k_total)` → DSR（k_total = A1 candidate trial count，見 §4.3）
- `block_bootstrap_ci(net, block_size=12)` + `block_size=96`（8h funding-cycle）→ 60m + 8h bootstrap lower
- `_n_eff(n, 60)` → horizon-overlap n_eff
- concentration：A1 自算 `max_day_share` / `max_funding_cycle_share`（mirror 8b line 711-712，用 funding cycle key）
- PBO：A1 是固定單閾值非 sweep → 用 **time-block CSCV**（見 §4.2），不用 8b 的 symbol×cell CSCV。

### §3.4 [ASSUME] 待 E1 ssh 驗（基礎設施前置）

1. **`panel.basis_panel`（或同義 basis snapshot 表）存在且新鮮**：A1 spec basis gate 需 point-in-time basis_pct。8b SQL **無 basis 欄位** → A1 SQL 必須有 basis 源。E1 IMPL 第一步 ssh `trade-core` 查：`\dt panel.*` + basis 表 schema + `select max(snapshot_ts_ms) from panel.<basis>`。**若 basis snapshot 不存在 → A1 路徑 BLOCKED**，runner 對 A1 輸出 `verdict=draft_only, fail_reason="basis_panel_missing"`（誠實標 infra gap，非 signal failure），不阻 A2。
2. `panel.funding_rates_panel` 含 BTC/ETH 14d 窗資料（8b [FACT] 已用此表，funding n=1728 16:30 UTC 新鮮）。

> **這是 v2 相對 v1 最大的新增工作 + 最大風險點**：A1 basis 源是否存在決定 A1 路徑可行性。E1 第一個 ssh probe 必須是 basis 表確認，PA/PM 在 dispatch 前可先 ssh 預驗以縮短 E1 阻塞。

---

## §4 6 Sanity Check 接線 + 2-symbol 統計可行性 + 輸出格式

權威定義 = AMD-2026-05-15-01 §3.2/§3.3（6 check：leak/lookahead / bias-selection / DSR-PSR / PBO-bootstrap / concentration / governance）。

### §4.1 6 check 逐條對 A1 / A2 跑什麼

| # | Check | A1（專屬路徑）| A2（8c adapter）| verdict 型態 |
|---|---|---|---|---|
| **1** | **Leak / Lookahead** | A1 SQL：funding/basis LATERAL as-of + fwd 嚴格未來 bar + 直接閾值（無 rolling-breach）；E2 grep A1 SQL 0 `PARTITION BY signal_ts_ms` + 0 `rolling().max()` | 8c SQL 不變（已 leak-free）；E2 grep A2 adapter 不改 SQL | `ATTEST` → E2 grep confirm |
| **2** | **Bias / Selection** | cohort BTC/ETH 固定（非事後挑）；`max_day_share ≤ 0.25` + `max_funding_cycle_share ≤ 0.25` | 8c `_single_day_concentration_check`(0.25) + `_single_symbol_concentration_check`(0.30) | `PASS/FAIL` |
| **3** | **DSR / PSR** | `psr_0 ≥ 0.95` + `dsr ≥ 0.95`（k_total = A1 trial count §4.3）| 8c `psr_value`/`dsr_value`（**k_total override** §4.3）| `PASS/FAIL` |
| **4** | **PBO / Bootstrap** | time-block CSCV `pbo ≤ 0.20`（§4.2）+ 60m & 8h bootstrap lower > 0 | 8c `_pbo` + 60m & 4h bootstrap lower > 0；2-symbol PBO 見 §4.2 | `PASS/FAIL` |
| **5** | **Replay data tier** | source = `panel.funding_rates_panel` + `panel.basis_panel` + `market.klines`（self-hosted PG，ADR-0038）；無 synthetic/paper row | source = `market.liquidations` + `market.klines`（self-hosted）| `ATTEST` |
| **6** | **Governance boundary** | runner + packet 0 hit `live_reserved\|max_retries\|live_execution_allowed\|OPENCLAW_ALLOW_MAINNET\|authorization\.json\|execution_authority\|decision_lease_emitted`；packet 只 `eligible_for_demo_canary`，**絕不** `Stage 1 PASS`/`auto_promote`/`to_stage`/order/fill/TOML mutation（AMD §3.2）| 同 A1 | `ATTEST` → E2 grep confirm |

> check 1/5/6 = governance/grep `ATTEST`，**權威 PASS 由 E2 grep proof 給**（PA profile：P0/P1 leak/lookahead/selection finding 必附 call-path grep）。`ATTEST ≠ PASS`。

### §4.2 2-symbol 統計可行性（核心新設計 — QC 必驗點）

2-symbol cohort 下，8b/8c 的 symbol-cross-section CSCV（`_pbo` 需 ≥10 candidate keys，line 557/766）**無法成立**（A1/A2 各 1 個固定 cell，非 sweep grid）。重設計如下：

| 統計 | 8b/8c 原法（不適用 2-sym）| v2 candidate 法 |
|---|---|---|
| **PBO** | symbol×cell CSCV，≥10 cells + ≥4 days | **time-block CSCV**：把樣本按 calendar-day 切 day-block，對「該 candidate 唯一 cell」做 day train/test split（best-in-train vs test-median）。仍用 8b `_pbo` 機制但 candidate key = 單一 cell 的多個 day-block 子序列（需 ≥4 distinct days）。若 days < 4 → `pbo=None` + `verdict=observe_more`（sample insufficient，非 fail）。 |
| **DSR k_total** | 25×branch×grid 巨大 | candidate 真實 trial count（§4.3）|
| **n_eff** | per-symbol/branch/pooled floor | 2-symbol pooled n_eff floor **降級為診斷指標**（見 §4.4 honest boundary），不作 reject gate；標 sample-sufficiency |
| **bootstrap** | block bootstrap（抗自相關）| 不變（block bootstrap 對 n 小仍有效，但 n < block_size(12) → None → observe_more）|

**QC 必確認**：(a) time-block CSCV 在 2-symbol + 14d（≈14 day-block）下 usable_splits 是否 ≥ 最小有效數；(b) 若 14d 不足以撐 PBO，sensitivity 擴 21/28d 是否合理；(c) 2-symbol pooled n_eff 降級為診斷而非 reject gate 的統計正當性（避免「樣本不足」被誤判為「策略無效」）。

### §4.3 candidate trial-count k_total（DSR benchmark 修正）

DSR benchmark `√(2 ln k_total)` 必須反映 candidate 真實嘗試的參數組合數，**不是研究 sweep 的 11664/巨大 grid**：

- A1 candidate trial count `k_new ≈ len(symbols)[2] × len(direction)[1, short-only] × len(threshold-set)[1, 固定30%] × len(horizon)[1 primary] = 2`；加 `k_prior`（先前 funding 研究嘗試數，保守取 SSOT/8b 既有 k_prior 值，E1 從 SSOT 讀，不自創）。
- A2 `k_new ≈ 2(symbol) × 2(direction) × 1(threshold-set) × 1(horizon) = 4`；**override 8c line 1388 的 `25×11664`**（adapter 傳 `k_prior` 並阻止 8c 內部 inflate；若 8c API 不允許 override k_total，adapter 在 `compute_stage0r` 回傳後**重算 dsr**：用 `dsr_with_k(net_values, candidate_k_total)` 蓋過）。

> 這修正使 DSR 對 candidate 公平（不被研究 grid 的多重比較 penalty 拖死），同時仍誠實計入 candidate 自身的小 trial count + prior。QC 驗 k_prior 取值正當性。

### §4.4 輸出格式（per-candidate verdict + 整體 stage0_ready）

```jsonc
{
  "runner_version": "candidate_stage0r.v2",
  "supersedes": "candidate_stage0r.v1 (8b harness reuse — QC direction error)",
  "generated_at_utc": "2026-...",
  "window_days": 14,
  "cohort": ["BTCUSDT", "ETHUSDT"],
  "candidates": {
    "A1_funding_short_v2": {
      "alpha_source_id": "funding_short_v2",
      "path": "dedicated_a1_cohort",
      "candidate_thresholds": {"funding_annualized_min": 0.30, "basis_pct_max": 0.003, "branch": "short_only"},
      "exit_model": "fixed_horizon_60m_proxy_for_1.5cycle_hold",
      "k_total": {"k_prior": "<from SSOT>", "k_new": 2, "basis": "2sym x short x 1thr x 1horizon"},
      "stats": {"psr_0": 0.xx, "dsr": 0.xx, "pbo": 0.xx, "bootstrap_ci_95_60m_lower": 0.x, "bootstrap_ci_95_8h_lower": 0.x,
                "avg_net_bps": 0.x, "n": 0, "n_eff": 0, "max_day_share": 0.xx, "max_funding_cycle_share": 0.xx},
      "six_check": {
        "1_leak_lookahead":   {"verdict": "ATTEST", "evidence": "funding/basis LATERAL as-of + fwd future-bar + no PARTITION-BY-signal_ts cohort + no rolling-breach", "e2_grep_required": true},
        "2_bias_selection":   {"verdict": "PASS|FAIL", "max_day_share": 0.xx, "max_funding_cycle_share": 0.xx, "cap": 0.25},
        "3_dsr_psr":          {"verdict": "PASS|FAIL", "psr_0": 0.xx, "dsr": 0.xx, "threshold": 0.95},
        "4_pbo_bootstrap":    {"verdict": "PASS|FAIL|INSUFFICIENT", "pbo": 0.xx, "pbo_method": "time_block_cscv", "pbo_max": 0.20, "ci_60m_lower": 0.x, "ci_8h_lower": 0.x},
        "5_data_tier":        {"verdict": "ATTEST", "source_tables": ["panel.funding_rates_panel","panel.basis_panel","market.klines"], "synthetic_excluded": true},
        "6_governance":       {"verdict": "ATTEST", "emits_only": "eligible_for_demo_canary", "forbidden_output_present": false, "e2_grep_required": true}
      },
      "eligible_for_demo_canary": false,
      "sample_sufficiency": {"n_eff": 0, "floor_diagnostic": 300, "days": 0, "min_days_for_pbo": 4, "sufficient": false},
      "fail_reasons": ["..."],
      "stage0_ready_candidate": false
    },
    "A2_liquidation_cascade_fade": {
      "alpha_source_id": "liquidation_cascade_fade",
      "path": "8c_per_event_adapter",
      "candidate_thresholds": {"btc_threshold_usd": 500000.0, "eth_threshold_usd": 300000.0},
      "exit_model": "fixed_horizon_60m_conservative_proxy",
      "dynamic_exit_not_modeled": ["TP_1.5pct","SL_2.0pct","reverse_cascade_flip"],
      "k_total": {"k_prior": "<from SSOT>", "k_new": 4, "override_8c_25x11664": true},
      "packet": { /* 8c compute_stage0r() 4-value verdict packet（k_total overridden）*/ },
      "six_check": { /* 同結構；check 2 含 max_symbol_share */ },
      "eligible_for_demo_canary": false,
      "sample_sufficiency": {"...": "..."},
      "fail_reasons": ["..."],
      "stage0_ready_candidate": false
    }
  },
  "verdict": "observe_more",         // 整體 SSOT §6 lane
  "stage0_ready": false,
  "verdict_basis": "..."
}
```

- per-check verdict 三態：`PASS`/`FAIL`（stat 2/3/4）、`INSUFFICIENT`（2/4 因 sample 不足，→ observe_more 非 fail）、`ATTEST`（governance 1/5/6，待 E2 grep）。
- candidate `eligible_for_demo_canary`：A1 用 A1 metrics 自算（floor 對齊 §5.1）；A2 直接 passthrough 8c packet `pass`（4-value）映射（PASS-BOTH/LONG-ONLY/SHORT-ONLY → eligible；RED → not）。

---

## §5 Acceptance Gate + 誠實邊界

### §5.1 per-candidate `eligible_for_demo_canary=true` 判據

| 判據 | 閾值 | A1 來源 | A2 來源 |
|---|---|---|---|
| PSR(0) | ≥ 0.95 | 8b 原語 | 8c |
| DSR | ≥ 0.95 | 8b 原語 + candidate k_total | 8c + override k_total |
| PBO | ≤ 0.20（time-block CSCV）| §4.2 | 8c |
| bootstrap 95% lower（60m + 8h/4h）| > 0 | 8b 原語 | 8c |
| avg_net_bps | ≥ +15 | A1 metrics | 8c `AVG_NET_FLOOR_BPS` |
| concentration | max_day_share ≤ 0.25；A2 max_symbol_share ≤ 0.30 | A1 自算 | 8c |
| 0 leak / governance | E2 grep 0 hit | check 1/6 | check 1/6 |
| sample sufficiency | n_eff ≥ diagnostic floor **且** days ≥ 4 | §5.3 | §5.3 |

### §5.2 整體 `stage0_ready` 映射（SSOT §6 四 lane）

| 整體 verdict | 條件 | next step |
|---|---|---|
| `stage0_ready` | ≥1 candidate `eligible=true` **且** 6/6（stat PASS + E2-grep-confirmed ATTEST）**且** sample sufficient | PA 出 Stage 0 dispatch；operator approve 進 demo canary |
| `observe_more` | candidate 方向正但 sample 不足（n_eff < floor / days < 4 / bootstrap None / PBO INSUFFICIENT）| 擴 window 21/28d 或等更多 demo 累積；**非 signal failure** |
| `draft_only` | 結構合理但 1+ stat check FAIL（非 sample 問題）；或 A1 basis infra 缺（§3.4）| 維持 DRAFT；不啟動 |
| `reject` | leak hit / governance hit / 全 candidate 確證 negative net（sample 足下仍負）| archive |

### §5.3 誠實邊界（per QC #5 + 架構教訓 29）

- **2-symbol + demo 短窗 + candidate active=false → n_eff 預期遠低 floor → 預期 verdict 多落 `observe_more`（sample insufficient），不是 `reject`**。runner 必在 `sample_sufficiency` 欄位並列 `n_eff` / `days` / `min_days_for_pbo`，**明文區分 `sample_insufficient` vs `signal_failure`**：
  - `sample_insufficient`：n 太小，PSR/DSR/PBO 無法可靠估計（None 或寬 CI）→ `observe_more`。
  - `signal_failure`：n 足夠（n_eff ≥ floor + days ≥ 4）但 avg_net 確證負 / bootstrap lower < 0 → `draft_only`/`reject`。
- A1 basis infra 缺（§3.4）→ `draft_only` + `fail_reason="basis_panel_missing"`，**標 infra gap 非 signal failure**。
- A2 fixed-horizon proxy（§1 B）→ packet 標 `exit_model` + `dynamic_exit_not_modeled`；proxy fail 不等於 A2 fail，標 `observe_more`（需 A 路徑或更多樣本）。
- **RED/FAIL 不自動 = reject**；早期結果預期 `observe_more` 為主。

---

## §6 硬邊界（per CLAUDE §四 + 16 原則 #3/#7 + DOC-08 §12 + AMD §3.2）

- **純 offline replay**：read-only PG SELECT；不下單、不碰 live、不寫 trading/panel/market、不調 Rust、不碰 authorization/lease/paper/mainnet。
- **AMD §3.2 forbidden output（極高敏感 — E2 必 grep）**：runner packet **絕不** emit `Stage 1 PASS` / `auto_promote` / `canary_stage_log.to_stage` / order / fill / TOML mutation。只 `eligible_for_demo_canary`（true/false）。`ATTEST ≠ PASS`，governance 由 E2 grep 給權威。
- **不解鎖 candidate**：`stage0_ready=true` 只是證據；candidate active=true 由 operator/PM gate（runner 絕不改 TOML / 絕不 auto_promote）。
- runner 是 gate-1（Stage 0R sanity）解鎖件；gate-1 green → operator approve → demo fills → AC-S2-A-3 evidence。

---

## §7 副作用清單

1. **[risk 中 / A1 新 SQL leak surface]**：A1 SQL 是**新**查詢，非復用 → 必走 leak-free 設計 review（QC stat + E2 grep）。最大風險 = 誤引入 `PARTITION BY signal_ts_ms` cohort stat（重蹈 8b）或 basis/funding 取到 future snapshot。E2 必逐行核 LATERAL as-of `<=` + fwd `+3600000` 嚴格未來。
2. **[risk 中 / A1 basis infra]**：basis_panel 表存在性未證（§3.4 [ASSUME]）→ E1 第一步 ssh probe；缺則 A1 BLOCKED（draft_only）。PA/PM 可 dispatch 前預驗。
3. **[risk 中 / A2 k_total override]**：8c line 1388 k_new inflation 必須被 adapter override，否則 A2 永 DSR fail（silent 統計錯，mock test 不抓）。QC + E2 雙確認 override 正確且 k_prior 取值有據。
4. **[risk 低 / 復用 8b/8c 原語]**：runner import 8b/8c 純統計函數（無下游 production import 8b/8c；[INFER] 待 E2 grep confirm caller 範圍）。不改 8b/8c 行為。
5. **[硬邊界 / governance]**：check 6 forbidden output — 本 spec 唯一極高敏感點，E2 必 grep。
6. **[risk 低 / DB fail 路徑]**：mirror 8b/8c fail-closed exit code（DB connect fail=2 / query fail=1）；runner propagate 不吞錯。

---

## §8 LOC Budget + 工時 + E1 Chain

### §8.1 LOC budget（v2 修正 — 較 v1 大，因 A1 需新 metrics + SQL）

| 物件 | LOC | 說明 |
|---|---|---|
| `candidate_stage0r_runner.py` | 180-240 | argparse + 雙 candidate 配置 + verdict 映射 + JSON/md render |
| `a1_funding_short_metrics.py` | 220-300 | A1 signal gate + cooldown dedup + 復用 8b 原語 + time-block PBO 接線 |
| `a2_cascade_adapter.py` | 90-140 | 8c per-event 呼叫 + candidate cohort/threshold pin + k_total override |
| `alpha_candidate_a1_funding_short_features.sql` | 70-90 | A1 leak-free 專屬 query（funding+basis LATERAL + fwd future-bar，無 cohort stat）|
| `__init__.py` + 頂層 shim | 18 | mirror 8b/8c |
| smoke test `candidate_stage0r_smoke.py` | 160-220 | mock A1 row + 8c packet → verify gate / 6-check / verdict / 0 forbidden output；不連 PG |
| SCRIPT_INDEX.md | ~4 行 | hard rule |
| **合計** | **~740-1010** | 單檔均 < 800（最大 a1_metrics ~300）；無 Rust；無改 8b/8c SQL/metrics |

### §8.2 工時

| 階段 | hr | 內容 |
|---|---|---|
| E1 IMPL | 14-20 | A1 SQL（含 ssh basis probe）+ A1 metrics（signal gate + cooldown + k_total）+ A2 adapter（8c override）+ runner + smoke test + SCRIPT_INDEX |
| **QC stat review（必）** | 3-4 | (1) A1 gate 方向 short-only + absolute funding > 30% + basis 正確（**不重蹈 v1 方向錯**）(2) 2-symbol PBO time-block CSCV 統計可行性 + n_eff floor 降診斷正當性 (3) DSR k_total candidate trial count + k_prior 取值 (4) A2 8c override 正確 + fixed-horizon proxy waiver |
| E2 adversarial | 3-4 | check 1 grep（A1 SQL 0 `PARTITION BY signal_ts_ms` + 0 rolling-breach + LATERAL as-of `<=`）+ check 6 grep（0 forbidden output）+ A2 不改 8c SQL + k_total override leak surface |
| E4 regression | 2-3 | smoke PASS + Linux ssh PG 實跑 1 次（A1 + A2，empirical 非 mock）確認 packet 結構 + exit code + basis 表實在 |
| **合計** | **22-31 hr** | active engineering（不含 evidence 累積等待）|

### §8.3 E1 dispatch chain（並行性）

- **可拆 2 並行 E1**（檔案不重疊）：
  - **E1a**：A1 路徑（`a1_funding_short_metrics.py` + `alpha_candidate_a1_funding_short_features.sql`）— 含 ssh basis probe（先行，因 basis 缺則阻塞）。
  - **E1b**：A2 adapter（`a2_cascade_adapter.py`）+ runner 殼（`candidate_stage0r_runner.py` + `__init__` + shim + smoke + SCRIPT_INDEX）。runner 殼先用 A1/A2 stub 對接，E1a 完成後接線。
- E1a / E1b 完成 → **強制 A3+E2 並行核驗**（per memory `feedback_impl_done_adversarial_review`：新 SQL + 共用 helper + grep-sensitive → 不接受單獨 sign-off）+ **QC stat review（chain 必經）並行**。
- **QC stat review 是 chain hard gate**（task brief 強制）：驗 A1 cohort gate 方向 + 2-symbol 統計可行性，**不通過不進 E2 sign-off**。
- E4（Linux ssh PG 實跑）**不能取代** E2 grep proof（check 1/6）+ QC stat review。

### §8.4 E1 避坑

1. **不改 8b/8c SQL / metrics**：A1 新建獨立 SQL + metrics；A2 只在 adapter 層 pin + override，不碰 8c SQL/compute_stage0r 內部。
2. **A1 方向**：short-only（direction=-1 永遠）+ absolute funding_ann > 0.30 + basis < 0.003。**禁用 8b z-score / branch / cohort stat**（v1 方向錯根因）。
3. **A1 SQL 0 cohort stat**：不得有 `PARTITION BY signal_ts_ms` median/std/percent_rank。
4. **A2 k_total override**：必修 8c line 1388 inflation，否則 DSR 永 fail。
5. **basis probe 先行**：E1a 第一個動作 = ssh 查 basis 表；缺則回 BLOCKED 標 draft_only，不硬編造。
6. `ATTEST ≠ PASS`：check 1/5/6 待 E2 grep。
7. 跨平台：用 8b `_repo_root()` env 解析 + DSN env，不硬編碼 home path。

---

## §9 E2 必查 3 點（高風險警告）

1. **check 6 governance grep**：runner + packet 0 hit `live_reserved|max_retries|live_execution_allowed|OPENCLAW_ALLOW_MAINNET|authorization\.json|execution_authority|decision_lease_emitted`；packet 0 `Stage 1 PASS|auto_promote|to_stage`，只 `eligible_for_demo_canary`。
2. **check 1 A1 SQL leak-free**：A1 新 SQL 逐行核 — funding/basis LATERAL `snapshot_ts_ms <= signal_ts_ms`（as-of，不含 future）+ fwd `+3600000` 嚴格未來 bar + cutoff `<= now-3600000` + **0 `PARTITION BY signal_ts_ms`** + 0 `rolling().max()`。
3. **A1 方向 + A2 k_total = silent 統計錯（最易漏，mock 不抓）**：A1 gate short-only + absolute >30% + basis（**非** 8b z-score branch，**非** v1 接反方向）；A2 adapter k_total override 8c 25×11664 inflation。E2 + QC 雙確認。

---

## §10 References

- 8b harness（A1 只復用統計原語，整體報廢）：`helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py`（cohort gate line 372-394 / 25-sym fail line 1050,1368）+ `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql`（cohort stat line 76-99）
- 8c harness（A2 復用 per-event 路徑）：`helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py`（per-event line 951-1082 / k_total inflation line 1388 / 4-value verdict line 1213-1252）+ `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`（per-event leak-free，不動）
- A1 spec: `docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md`（gate §1.1 / exit §1.2 / cohort line 149 / cost §1.1 #4）
- A2 spec: `docs/execution_plan/2026-05-25--alpha_candidate_4_liquidation_cascade_fade_spec.md`（fade direction line 58-61 / threshold line 99-100 / exit line 73-83）
- SSOT: `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`（§5 gates line 140-145 / §6 lanes line 158-167）
- 6 sanity + forbidden output: `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md` §3.2 line 87-90 / §3.3 line 100-103
- v1（superseded）: 本檔 v1（git history）

---

**Spec v2 END — E1 IMPL-ready**

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/specs/2026-05-29--a1a2-stage0r-candidate-runner-spec.md`

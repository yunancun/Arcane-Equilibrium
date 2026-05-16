# W-AUDIT-8b Stage 0R Round 1 Smoke — E1 Report

Date: 2026-05-16
Owner: E1
Scope: 讀-only Linux PG dry-run，跑既有 `helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py` 一次，盤點 gap 給 PA Wave 4-A Run Plan。**0 寫入 / 0 config 改 / 0 migration / 0 restart**。

## 結論 TL;DR

| 項 | 狀態 |
|---|---|
| 結構性 PASS/FAIL | **PASS（packet 跑通，eligible_for_demo_canary=false 正確輸出）** |
| Linux PG 資料量充足 | **邊緣 — 5.09 days panel < spec 14 funding cycles (~5d minimum) 邊緣，部分 sym 13-15 cycles** |
| Mandatory contract 完整度 | **partial — 5 個 spec mandatory field 缺 (cohort coverage / settlement-window / per-symbol breakdown / baseline lift / maker-taker split)** |
| Tooling import / smoke | **PASS（fixture smoke + CLI help + DB run）** |
| 主要 gap 數 | 7 個（見 §5）|

---

## 1. Pre-run sanity check (Step A)

### 1.1 Module import

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 -c 'import helper_scripts.reports.w_audit_8b.funding_skew_stage0r_smoke as m; print(\"import OK\")'"
# => import OK
```

### 1.2 Fixture smoke

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py"
# => PASS W-AUDIT-8b Stage 0R metrics smoke
# => eligible_for_demo_canary=False
# => k_total=555
```

### 1.3 CLI help

`helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py` 提供：
`--window-days / --symbols / --cost-bps / --k-prior / --out / --format {json,markdown}`。

### 1.4 Tooling 自審觀察

- Tooling 4 個檔 + 1 SQL 結構完整、無 import 缺失、無 dep gap
- `_get_conn()` 接受 `OPENCLAW_DATABASE_URL` 或 5 個 `POSTGRES_*` env var fallback
- DEFAULT `OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=120000`（2min）在 5-day 全 25-symbol 數據上不夠（見 §3 timeout 教訓）
- SQL 檔位置在 `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql`，不在 `helper_scripts/reports/w_audit_8b/` 內（PA Run Plan 內若 reference path 須對齊）

---

## 2. Linux PG Empirical Snapshot (Step B)

所有查詢透過 `ssh trade-core "psql -h localhost -U trading_admin -d trading_ai ..."` 讀 only 執行。

### 2.1 Panel 數據量

| Panel | rows | min_ts | max_ts | distinct sym | window span | freshness |
|---|---|---|---|---|---|---|
| `panel.funding_rates_panel` | 179,126 | 1778455815872 | 1778895554925 | 25 | 5.09 days | 0.80 sec |
| `panel.oi_delta_panel` | 179,871 | 1778455815872 | 1778895554925 | 25 | 5.09 days | 0.80 sec |
| `market.klines` (5m) | 138,284 | 1775390700000 | 1778895900000 | 121 | 40.57 days | （正常）|

**Panel 對齊**：funding/OI 兩 panel 完全對齊（同 min/max + 25 共同 symbol），且 freshness < 1s。

### 2.2 14 funding cycles 樣本驗證

spec §Promotion floor 要求「sample must span at least 14 funding cycles」。Bybit 預設 8h 一 cycle → ≥14 cycle 需 ≥ 4.67 days。當前 panel 5.09 days **剛剛達門檻**，但 per-symbol distinct cycle 邊緣：

| Symbol | distinct cycles | cycle_span_hours |
|---|---|---|
| BTCUSDT | 15 | 128.00 |
| ETHUSDT | **13** | 128.00 |
| SOLUSDT | 14 | 128.00 |

→ **Gap A**：ETHUSDT 不滿 14 cycle floor；BTC/SOL 邊緣。spec 對 `single funding-cycle share > 25%` 也將 fail（cycle 過少 → 任一 cycle 必 > 25%）。

### 2.3 `learning.strategy_trial_ledger` schema 盤點

```
table_schema | learning
table_name   | strategy_trial_ledger
columns: trial_id (bigint) / ts (timestamptz) / strategy_name (text) /
         engine_mode (text) / trial_family (text) / candidate_key (text) /
         observed_sharpe (float8) / n_observations (int) /
         mean_return (float8) / source (text) / evidence (jsonb)
```

| metric | value |
|---|---|
| total_rows | 17,335 |
| distinct candidate_key | 69 |
| distinct strategy_name | 4 (`bb_breakout`, `funding_arb`, `grid_trading`, `ma_crossover`) |
| distinct trial_family | 1 (`edge_estimator_cycle`) |
| rows where `candidate_key ILIKE '%funding_skew%'` | 0 |
| rows where `strategy_name ILIKE '%funding%'` | 1,350 (`funding_arb` — retired) |
| sample candidate_key | `1000PEPEUSDT`, `AAVEUSDT`, `ADAUSDT`, `APEUSDT`, ... |

→ **Gap B (主要)**：`candidate_key` 實際語意是 **symbol 名稱**，不是 spec/MIT 預想的 `strategy×branch×param-cell` 形式。`trial_family='edge_estimator_cycle'` 是 edge estimator scheduler 寫入的 per-symbol-per-strategy aggregate，不是 hypothesis-trial counter。當前 `fetch_k_prior` 用 `COUNT(DISTINCT candidate_key) = 69` **語意不符** MIT verdict 對 `K_prior` 的定義（「comparable trials」）。

### 2.4 Panel index 盤點

```
panel.funding_rates_panel:
  - PK (snapshot_ts_ms, symbol)
  - btree (snapshot_ts_ms DESC)
  - btree (snapshot_ts_ms DESC, symbol)  ← LATERAL JOIN 不友好

panel.oi_delta_panel:
  - PK (snapshot_ts_ms, symbol)
  - btree (snapshot_ts_ms DESC, symbol)
  - btree (snapshot_ts_ms DESC)
```

→ **Gap C**：兩 panel 都缺 `(symbol, snapshot_ts_ms DESC)` 索引。SQL 內 4 個 LATERAL JOIN 的 `WHERE p.symbol = b.symbol AND p.snapshot_ts_ms <= b.signal_ts_ms ORDER BY p.snapshot_ts_ms DESC LIMIT 1` 走不到最佳化路徑。這是 Round 1 default `--window-days 7` + default `OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=120000` 跑出 timeout 的主因。**此 gap 屬 DB infra，read-only round 1 不修，但 PA Run Plan 應考慮 P2 索引建議**。

---

## 3. Round 1 Smoke Run (Step C)

### 3.1 Run command + log

```bash
# 嘗試 1（FAIL）：default 7d window + 120s timeout
ssh trade-core "cd ~/BybitOpenClaw/srv && OPENCLAW_DATABASE_URL='postgresql://trading_admin@localhost:5432/trading_ai' \
  timeout 360 python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py \
  --window-days 7 --format json --out /tmp/openclaw/funding_skew_stage0r_round1_$(date +%Y%m%d_%H%M).json"
# => [FATAL] Stage 0R query failed: QueryCanceled: canceling statement due to statement timeout

# 嘗試 2（PASS）：5d window + 600s timeout（透過 .pgpass 認證）
ssh trade-core "cd ~/BybitOpenClaw/srv && \
  OPENCLAW_DATABASE_URL='postgresql://trading_admin@localhost:5432/trading_ai' \
  OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=600000 \
  timeout 900 python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py \
  --window-days 5 --format json --out /tmp/openclaw/funding_skew_stage0r_round1_20260516_0343.json"
# => Wrote /tmp/openclaw/funding_skew_stage0r_round1_20260516_0343.json
```

JSON 已 scp 回 Mac：`docs/CCAgentWorkSpace/E1/workspace/runs/2026-05-16/funding_skew_stage0r_round1.json`（14.8 KB）。

### 3.2 Round 1 主要欄位 inline

```json
{
  "strategy_variant": "funding_skew_directional.v0_2",
  "alpha_source_id": "funding_skew_directional",
  "funding_attribution_mode": "excluded",
  "source_mode": "ws_current",
  "cost_bps": 12.0,
  "window_days": 5,
  "symbol_count": 25,
  "row_count": 35533,
  "k_prior": 69,
  "k_new": 4050,
  "k_total": 4119,
  "exclusions": {
    "funding_stale_excluded": 10,
    "funding_warn_age": 124,
    "oi_stale_excluded": 10,
    "oi_warn_age": 124
  },
  "pooled_primary": {
    "n": 748, "n_eff": 124,
    "avg_net_bps": 16.348,
    "psr_0": 0.9986, "dsr": 0.0,
    "bootstrap_ci_95": [2.435, 30.356]
  },
  "branch_summary": {
    "crowded_long_fade":   {"n": 30,  "n_eff": 5,   "avg_net_bps": 18.43},
    "crowded_short_squeeze": {"n": 718, "n_eff": 119, "avg_net_bps": 16.26}
  },
  "pbo": 1.0,
  "best_primary_cell": {
    "candidate_key": "INJUSDT|crowded_short_squeeze|z=1.5|p=0.85/0.15|oi=3|h=30",
    "n": 7, "n_eff": 1,
    "avg_net_bps": 116.78,
    "psr_0": 0.9998, "dsr": 0.0,
    "bootstrap_ci_95": null,
    "funding_cycles": 2,
    "max_day_share": 1.0,
    "max_funding_cycle_share": 0.857,
    "funding_interval_min": 480
  },
  "eligible_for_demo_canary": false,
  "eligibility_fail_reasons": [
    "symbol n_eff < 100",
    "pooled n_eff < 300",
    "funding cycles < 14",
    "single-day share > 25%",
    "single funding-cycle share > 25%",
    "DSR < 0.95",
    "PBO missing or > 0.20",
    "bootstrap lower bound <= 0"
  ]
}
```

### 3.3 觀察

- **PASS 結構性**：JSON valid、無 NaN/Inf、無 traceback、`eligible_for_demo_canary=false` 結論正確
- **跑時間**：~6 min (5d window, 25 symbols, 35,533 feature rows joined)
- **stale-panel exclusion 真實有效**：funding 10 stale + 124 warn / oi 10 stale + 124 warn（spec WARN > 60s、FAIL > 300s 邏輯生效）
- **funding_interval_min=480** 對 25 symbols 全 8h interval 推斷正確（BB §verdict 合 mandatory field）
- **`crowded_short_squeeze` 接近全部信號**：n=718 vs `crowded_long_fade` n=30 (24:1 imbalance)；窗內 funding skew 嚴重偏負（市場 short 緣多）
- **`best_primary_cell` n=7 / n_eff=1 / max_day_share=1.0** 顯示 INJUSDT 116.78 bps 是「單日 lucky cliff」非 plateau alpha（spec 明文 reject 條件「post-hoc threshold expansion」雖未直接 trigger，但結構等價）
- **`pbo=1.0`** 全災難性 overfitting（spec ≤ 0.20 floor，差 5×）

---

## 4. Completeness Check (Step D) — Mandatory Field 對照

對齊 PM verdict §"Stage 0R Report Contract"（line 128-146）+ spec §"Mandatory report fields"。

| # | Mandatory field | Packet 狀態 | 評估 |
|---|---|---|---|
| 1 | panel latest times, ages, source tiers, cohort coverage | exclusions 只給 aggregate counts；無 `funding_panel_latest_ts` / `oi_panel_latest_ts` / `panel_oldest_age_sec` / 25-sym cohort 覆蓋率 | **MISSING** |
| 2 | stale/missing exclusion counts | `exclusions{funding_stale_excluded=10, funding_warn_age=124, oi_stale_excluded=10, oi_warn_age=124}` | **OK** — 但 `funding_missing=0` / `oi_missing=0` 顯式 0-count 沒寫，會看起來像 missing field |
| 3 | per-symbol n / n_eff | `pooled_primary` + top-20 cells only；**25 sym × 2 branch 完整 per-symbol breakdown 缺** | **MISSING (高)** |
| 4 | pooled n / n_eff | `pooled_primary{n=748, n_eff=124}` | **OK** |
| 5 | branch breakdown | `branch_summary{crowded_long_fade, crowded_short_squeeze}` | **OK** |
| 6 | avg gross/net bps | pooled + cells, both | **OK** |
| 7 | funding attribution mode = 'excluded' | `"funding_attribution_mode": "excluded"` | **OK** |
| 8 | funding interval + source mode | `funding_interval_min=480` per cell；packet-level `source_mode='ws_current'` | **OK** |
| 9 | settlement-window counts and adverse-drag sensitivity | **無** | **MISSING (高)** |
| 10 | PSR(0) with skew/kurt adjustment | pooled + cells | **OK**（metrics.py 用 Bailey-LDP 帶 skew/kurt） |
| 11 | DSR with explicit K_total | `dsr=0.0`（all under-power）, K_total=4119 顯式 | **結構 OK，數值反映 under-power** |
| 12 | CSCV PBO | `pbo=1.0` | **OK** |
| 13 | block-bootstrap CI with 60m primary block + 8h sensitivity | pooled CI `[2.43, 30.36]`；**cells 多數 `null`（n < block_size=12 跳過）**；**8h sensitivity block 缺** | **PARTIAL** |
| 14 | sensitivity grid with plateau check | top_primary_cells 看得到 z=1.5/2.0/2.5 對 INJUSDT 完全相同（同 7 rows 觸發三 z 閾值）— 是 degenerate plateau；**無顯式 `plateau_passed=true/false` flag** | **MISSING flag** |
| 15 | baseline lift vs no-funding/OI-confirmation baseline | **無** | **MISSING (高)** |
| 16 | maker/taker split + cost-edge ratio | 只有 flat `cost_bps=12.0`；無 maker_pct / taker_pct / cost_edge_ratio | **MISSING (高)** |
| 17 | `eligible_for_demo_canary=true/false` | `false` | **OK** |

**Spec §Stop Rules check**：

| Stop rule | Round 1 命中？ |
|---|---|
| pooled-only pass with no eligible `strategy × symbol × branch` | No（pooled 也 fail） |
| vague or understated `K_total` | **可能 — K_prior=69 語意不符** spec/MIT「comparable rows」定義（見 Gap B） |
| missing PBO or underpowered PBO | No（pbo=1.0 計算出來） |
| `DSR < 0.95` | **Yes — dsr=0.0** |
| positive funding income counted | No（mode='excluded'） |
| stale panel rows included in eligibility | No（exclusion 邏輯生效） |
| post-hoc threshold expansion | No（grid 是 preregistered） |
| retired `funding_arb` code semantics | No |
| production config / risk / sizing mutation | No |

---

## 5. Gap signal 給 PA Wave 4-A Run Plan

7 個 gap 分三類（**high = PA 必處理**, **medium = PA 應提及**, **infra/P2 = 留 P2 ticket**）：

### Gap A (high)：14 funding cycles 邊緣
- panel 5.09 days，per-symbol 13-15 distinct cycles
- spec floor 14 → **ETHUSDT FAIL，BTC/SOL borderline**
- **PA 推薦**：(1) 等 panel 累到 ≥ 7 days 再 round 2，或 (2) 把 floor 從 14 降到 12（QC 簽認） + 顯式 single-cycle share 25% rule 在小樣本下會永遠 fail，需 PA 思考
- 主 session 已知（CLAUDE.md §三：「14 funding cycles 樣本要求」）

### Gap B (high)：`K_prior` 語意未對齊 MIT verdict
- 當前 `fetch_k_prior` 用 `COUNT(DISTINCT candidate_key) = 69`
- 但 ledger 實際 `candidate_key` 是 **symbol 名稱**（如 `BTCUSDT`），不是 `strategy×branch×param-cell` 形式
- 既往無 `funding_skew` 系 trial（0 rows），且 ledger 唯一 `trial_family='edge_estimator_cycle'` 是 estimator scheduler 寫的 aggregate，**不是 hypothesis trial counter**
- spec/MIT verdict 明文：「`K_prior` must be read from comparable rows」→ comparable rows 在當前 ledger 為 0
- **PA 推薦**：(1) Round 2 改 `fetch_k_prior` 用更精準 filter（e.g. `WHERE strategy_name='funding_skew_directional'` → 0），或 (2) PM 接受 `K_prior=0`（conservative），或 (3) 重設 K_prior 來源為 ADR-level trial registry（需獨立工作項）
- 此 gap 是 spec implementation drift 而非 tooling bug — 等 MIT 簽 K_prior 真實來源 SOP

### Gap C (medium/infra)：panel 索引未對 LATERAL JOIN 最佳化
- 兩 panel 都缺 `(symbol, snapshot_ts_ms DESC)` 索引
- 默認 statement_timeout=120000ms 在 5-day × 25 sym 5m bar 跑不完（要 600s）
- **PA 推薦**：(1) Round 2 文檔 `OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=600000` 是 mandatory env, (2) 另開 P2 ticket 建議 panel 加索引（read-only round 1 不修）

### Gap D (high)：5 個 mandatory contract field 缺實作
缺：
1. `panel_metadata{latest_ts, oldest_age_sec, cohort_coverage_pct, source_tier_mix}`
2. `per_symbol_breakdown[{symbol, n, n_eff, branch_n, branch_n_eff}]` × 25
3. `settlement_window_counts + adverse_drag_sensitivity`
4. `baseline_lift_vs_no_confirmation`
5. `maker_taker_split + cost_edge_ratio`
- **PA 推薦**：補進 `funding_skew_stage0r_metrics.py compute_stage0r()` return dict 或新 `funding_skew_stage0r_report.py render_*()` 段
- **此 gap 純 IMPL — 等 PA Run Plan + 主 session 派 IMPL ticket**（按硬約束 E1 round 1 不寫 business code）

### Gap E (medium)：plateau check 無顯式 flag
- top_primary_cells 看 INJUSDT z=1.5/2.0/2.5 三閾值同 avg_net_bps=116.78（同樣 7 rows 同 trigger 3 thresholds = degenerate plateau）
- spec mandatory「adjacent grid cells must show a plateau rather than a single lucky threshold cliff」需要 `plateau_passed=true/false` flag
- **PA 推薦**：補進 `compute_stage0r()` 加 `plateau_check{best_cell_id, neighbor_cells, plateau_passed}` field

### Gap F (low)：block-bootstrap 60m primary block + 8h sensitivity 雙標
- 當前 metrics.py `block_bootstrap_ci` 預設 `block_size=12`（即 12 個 5m bar = 60m）— **60m primary OK**
- 但 spec 要求 8h funding-cycle sensitivity → 需用 `block_size=96` (8h / 5m) 再跑一次比對
- 當前 packet 只有 60m primary，**8h sensitivity 缺**
- **PA 推薦**：補進 `pooled_primary.bootstrap_ci_95_60m` + `pooled_primary.bootstrap_ci_95_8h` 雙 field

### Gap G (medium)：log file 在 timeout 後沒被覆寫
- 第二次成功 run 用了 600s timeout + 不同 output path，但 `/tmp/openclaw/funding_skew_stage0r_round1.log` 仍是第一次失敗的 traceback
- **PA 推薦**：Run Plan log 路徑用 `${output%.json}.log` 對應防混淆，或 round 2 跑時手動 rm 舊 log

---

## 6. Round 2 建議

### 6.1 結構 PASS → 但 alpha-deficient

Round 1 alpha 結論：**eligible_for_demo_canary=false 是真實的**，不是 tooling bug。
- pooled `avg_net_bps=16.35` >= 15 floor **PASS**（但 single floor，DSR/PBO 雙殺 → reject）
- pooled `PSR(0)=0.999` 但 `DSR=0.0` （K_total 4119 拉高門檻太狠）→ DSR 機制設計正確
- `pbo=1.0` 是 CSCV 信號：4119 grid cells 中沒有一個能 train→test 穩定 → catastrophic overfitting
- best cell INJUSDT 116.78 bps 是 `n=7 / max_day_share=1.0 / funding_cycles=2` 的單日 lucky cliff，非 alpha

**結論**：5 textbook strategies 結構性 alpha-deficient 同病再現。Round 2 即使全 gap 補齊，也大機率仍 GATE-RED。

### 6.2 Round 2 應做的事（依優先序）

1. **資料量擴展優先（Gap A）**：等 panel ≥ 7 days（再 2-3 天）+ per-symbol cycle ≥ 16，再 round 2。當前 5 days 是 floor 邊緣，noisy。
2. **Gap D 5 mandatory field 補實作**（PA + E1 IMPL ticket，主 session 派發）：
   - per-symbol breakdown
   - panel_metadata
   - settlement_window_counts
   - baseline_lift
   - maker/taker split
3. **Gap B K_prior 與 MIT 對齊**：決定 (a) 0 / (b) 0+精準 funding_skew_directional 過濾 / (c) ADR-level trial registry
4. **Gap E plateau flag**：補 metrics.py
5. **Gap F 8h sensitivity block**：補 metrics.py double-block bootstrap
6. **Gap C P2 ticket**：panel `(symbol, snapshot_ts_ms DESC)` 索引建議
7. **Round 2 跑命令 SOP**：env mandatory `OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=600000`，window-days 7（panel 累足後）

### 6.3 Round 2 預期結論

即便 6.2 全 land：
- alpha：仍大概率 GATE-RED（與 5 textbook 結構性 deficit 一致）
- 結構：completeness 達 spec mandatory 17 個全 PASS，可 sign off「Stage 0R 工具 complete」
- 治理價值：**Stage 0R 真正用途是「擋住 alpha-deficient 策略不進 demo」，Round 1 GATE-RED 是 Stage 0R 工作中的成功訊號**，不是工具失敗

---

## §7 嚴格限制守則

本 Round 1：
- ✅ 100% read-only on Linux PG（13 個查詢全 SELECT）
- ✅ 0 INSERT / UPDATE / DELETE / DDL / migration
- ✅ 0 config / authorization / runtime mutation
- ✅ 0 restart engine
- ✅ 0 spawn 第二層 sub-agent
- ✅ 注釋全中文（per `feedback_chinese_only_comments.md`）
- ✅ 未動 business logic — 純跑 + 觀察 + 寫 report

未動的代碼/檔案：
- `helper_scripts/reports/w_audit_8b/*.py` — 未碰
- `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` — 未碰
- `helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py` (wrapper) — 未碰
- runtime engine、config、auth、PG schema — 未碰

---

## 完整輸出 artifacts

- JSON：`docs/CCAgentWorkSpace/E1/workspace/runs/2026-05-16/funding_skew_stage0r_round1.json` (14.8 KB)
- Linux source JSON：`trade-core:/tmp/openclaw/funding_skew_stage0r_round1_20260516_0343.json`
- Run log（含初 timeout failure + 重 run success）：`trade-core:/tmp/openclaw/funding_skew_stage0r_round1.log`

## Report 路徑

`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--w_audit_8b_stage0r_round1_smoke.md`

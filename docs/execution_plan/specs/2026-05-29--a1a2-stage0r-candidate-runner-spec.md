# A1/A2 Candidate Stage 0R Runner — IMPL Spec

**Date**: 2026-05-29
**Author**: PA (design only; read-only ssh SELECT/cat; no IMPL / no runtime / no IPC)
**Trigger**: PM dispatch — Track B Sprint 2 Stage 0R preflight 共同缺件 = 把 8b/8c 研究 harness 收斂成「讀 A1/A2 candidate cohort 跑 Stage 0R」的 runner
**Chain**: `PM -> PA(this) -> E1 IMPL -> QC stat review -> E2 adversarial -> E4 regression -> PM`
**Risk grade**: 中（純 offline analysis script，復用既有 8b/8c 統計核；不觸 Rust engine / IPC / 5-gate / Decision Lease）
**標記法**: [FACT] cat/grep 直接觀測 / [INFER] 由 fact 推導 / [ASSUME] 待證實

> **依賴前置（已 [FACT] 確認）**：8b/8c metrics + report wrapper + SQL 全 land 且 leak-free；
> 統計核（PSR/DSR/PBO/bootstrap/concentration/cluster-aware n_eff）齊全可直接餵 candidate panel。
> 本 spec 唯一新增 = candidate-cohort 接線層，不重造統計。
> 對齊 readiness 報告 `2026-05-29--sprint2_stage0r_preflight_readiness.md` §2.1 結論。

---

## §0 TL;DR（給 E1 一句話）

新建一個薄 wrapper CLI `helper_scripts/reports/alpha_candidate_stage0r/candidate_stage0r_runner.py`，
把 A1（funding_short_v2）與 A2（liquidation_cascade_fade）的**命名 cohort + candidate 專屬閾值**
釘進既有 8b/8c harness，跑出 per-candidate 6-sanity evidence packet + 合併
`stage0_ready` verdict。**不改 8b/8c metrics / SQL / report**（surgical），只新增 candidate 接線層。
LOC ~280-360；IMPL 12-18 hr 含 test。

---

## §1 Runner 形態：薄 wrapper（復用，不重造）— DECISION + 理由

### §1.1 決策

**選擇 = 新建薄 wrapper `candidate_stage0r_runner.py`，委派既有 8b/8c report wrapper + metrics，
NOT 擴 8b/8c 既有 script 加 candidate 模式。**

### §1.2 理由（3 點）

1. **8b/8c 統計核已是 candidate runner 的引擎**：[FACT] `funding_skew_stage0r_metrics.compute_stage0r()`
   與 `liquidation_cluster_stage0r_metrics.compute_stage0r_sweep()` 已輸出 `eligible_for_demo_canary`
   verdict + 6 check 全部 evidence（PSR/DSR line 124-147 / PBO line 554 / bootstrap line 150-205 /
   concentration max_day_share line 711 + max_symbol_share 8c line 540 / baseline_lift / n_eff）。
   candidate runner 不需要任何新統計函數。
2. **8b/8c report wrapper 已是 SQL→packet 範式**：[FACT] `funding_skew_stage0r_report.py`
   `_get_conn()` (psycopg2 read-only, statement_timeout) → `_read_sql()` → `fetch_feature_rows()`
   → `compute_stage0r()` → JSON/markdown packet（line 33-330）。candidate runner 只需在此之上
   **pin cohort + threshold + 組合雙 candidate verdict**。
3. **避免污染研究 harness**：8b/8c 是 W-AUDIT 通用研究 sweep（25-symbol grid，掃 z-grid /
   density-floor grid）。candidate runner 是 **窄 cohort 固定參數** preflight（BTC/ETH only +
   A1 30% annualized / A2 $500k/$300k）。把 candidate 模式塞進研究 sweep 會混淆兩種用途的
   verdict semantic（research sweep 找最佳 cell vs candidate preflight 驗單一已定策略）。
   薄 wrapper 隔離乾淨，符合 CLAUDE Operating Style §2 simplicity / §3 surgical。

### §1.3 模塊放置

```
helper_scripts/reports/alpha_candidate_stage0r/
  __init__.py                       (new, ~3 LOC，mirror 8b __init__)
  candidate_stage0r_runner.py       (new, ~280-360 LOC — 本 spec 唯一 IMPL 物)
```
- 委派 import：`from helper_scripts.reports.w_audit_8b.funding_skew_stage0r_report import ...`
  與 `from helper_scripts.reports.w_audit_8c.liquidation_cluster_stage0r_report import ...`
  （8b/8c wrapper 既有 try/except relative-vs-absolute import，runner 比照）。
- 頂層 shim（mirror `reports/w_audit_8c_liquidation_cluster_stage0r.py` 範式）：
  `helper_scripts/reports/alpha_candidate_stage0r.py`（~15 LOC，委派至 package；
  per SCRIPT_INDEX 既有頂層 shim 慣例）。
- **必更新** `helper_scripts/SCRIPT_INDEX.md`（CLAUDE §七 hard rule：新 script 必登記）。

---

## §2 Candidate Cohort 資料來源 + Leak-Free（硬要求）

### §2.1 data source（per candidate）

| Candidate | 復用 harness | SQL source | cohort（pin） | candidate 專屬閾值（pin） |
|---|---|---|---|---|
| **A1 funding_short_v2** | 8b `funding_skew_stage0r_*` | `panel.funding_rates_panel` + `panel.oi_delta_panel` LATERAL + `market.klines 5m` fwd return（`sql/queries/w_audit_8b_funding_skew_stage0r_features.sql`）| `["BTCUSDT","ETHUSDT"]`（A1 spec line 149 hard constraint）| funding > 30% annualized（A1 spec line 41 / 182）；short-only branch = `crowded_short_squeeze` 對映（見 §2.3）|
| **A2 liquidation_cascade_fade** | 8c `liquidation_cluster_stage0r_*` | `market.liquidations` + `market.klines` fwd return（`sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`）| `["BTCUSDT","ETHUSDT"]`（A2 spec line 188）| BTC $500k / ETH $300k 5m cluster notional（A2 spec line 99-100 / 220-221）|

> **[INFER] 修正 readiness 報告措辭**：8b 真正消費 source = `panel.funding_rates_panel` /
> `panel.oi_delta_panel`（point-in-time snapshot 表），**不是** `market.funding_rates`。
> `market.funding_rates` 16:30 UTC 新鮮 [FACT] 是上游 writer 餵 panel 的證明，但 runner SQL
> 讀的是 panel 表。E1 IMPL 須用 8b 既有 SQL（panel.* 表），不要改讀 market.funding_rates。
> 8c 確實直查 `market.liquidations`（8c wrapper line 165-176 [FACT]）。

### §2.2 時間窗

- **預設 `--window-days 14`**（對齊 AC-S2-A-3 14d demo accumulation 語意；8b/8c default 是 7，
  runner override 為 14 使 replay 窗對齊 demo evidence 窗）。
- **sensitivity 跑 7 / 21 / 28**（per 8c spec v0.3 §6 預測 21-30d minimum；若 14d 樣本不足
  須能擴窗。runner 暴露 `--window-days` passthrough 至 8b/8c wrapper）。
- 源 panel 新鮮度 [FACT] 16:30 UTC（funding_rates n=1728 / liquidations n=82470），14d 窗有資料。

### §2.3 Leak-Free 結構性論證（硬要求 — per memory `feedback_indicator_lookahead_bias`）

**8b/8c 既有 SQL 已是 leak-free（[FACT] cat 直驗），candidate runner 繼承之，不引入新 leak surface**：

| 防線 | 8b SQL 證據 | 8c SQL 證據 |
|---|---|---|
| Forward return 嚴格取未來 bar | `signal_ts_ms + 900000/1800000/3600000` 之 future kline（features.sql line 63-74）| `bucket_end_ts + quiet_window + horizon` 之後第一根 kline open（SQL header「嚴格 as-of join」line 14-17）|
| Point-in-time signal（不含 future） | LATERAL `snapshot_ts_ms <= signal_ts_ms ORDER BY DESC LIMIT 1`（line 47-62）| `bucket_5m_epoch` 唯一鍵 + `max(ts)` 桶內最後事件為 quiet 起算（SQL header line 19-21）|
| 無 partial-bar | `close_ts_ms <= now - 3600000`（line 20）| entry/exit 都取 bar 的 open，避免 1m bar 內混未來 close（SQL header line 14-17）|
| 無 rolling-extreme breach | A1 用「直接 funding > 30% 閾值比較」非 `rolling(N).max()`（A1 spec §5.1 line 264）| A2 用 LiquidationPulsePanel 5m window strict trim 非 rolling breach（A2 spec §1.5 line 140-146）|

**E1 IMPL 不可改 8b/8c SQL 的 forward-return / LATERAL / cutoff 邏輯**（那會破 leak-free 不變量）。
runner 只 pin cohort（`%(symbols)s` = BTC/ETH）+ window + threshold filter，SQL 結構不動。

> **shift(1) 並列要求**：8b/8c metrics 內已用 funding-cycle / 60min block bootstrap 處理時序自相關
> （非 naive i.i.d.）；A1/A2 spec §5 各有結構性 leak-free 論證。runner 輸出 packet 須在
> `leak_free_attestation` 欄位**明文標注**「forward-return 取嚴格未來 bar + signal 取 as-of
> point-in-time + 無 rolling-extreme breach」三項，供 QC/E2 核（見 §3 check 1）。
> 此為**結構性 grep + 設計核對 check**，不是 runtime stat。candidate 走直接閾值比較故無
> rolling-breach；E2 須 grep candidate Rust strategy diff 確認 0 `rolling(N).max()` hit（§3 check 1）。

---

## §3 6 Sanity Check 接線 + 輸出格式

### §3.1 6 check 逐條對 A1/A2 跑什麼

權威定義 = AMD-2026-05-15-01 §3.3。對映既有 8b/8c 實作：

| # | Check | runner 對 A1 / A2 跑什麼 | 已有實作（復用）| runner 新增 |
|---|---|---|---|---|
| **1** | **Leak / Lookahead** | structural attestation + leak-free 三項標注（§2.3）；E2 grep candidate Rust diff 0 rolling-breach hit | 8b/8c SQL leak-free + spec §5 論證 | `leak_free_attestation` packet 欄位 + E2 grep 鉤子 |
| **2** | **Bias / Selection** | A1: 8b `max_day_share` / `max_funding_cycle_share` ≤ 0.25（line 711-712 + fail reason line 1066-1069）；A2: 8c `max_day_share` ≤ 0.25 + `max_symbol_share` ≤ 0.30 guard（line 490-585）| 8b/8c concentration guard | runner pin cohort BTC/ETH（固定非事後挑）+ 把 guard result 拉進 candidate packet |
| **3** | **DSR / PSR** | A1/A2 candidate cell `psr_0` + `dsr` ≥ 0.95 | `psr_bailey_ldp()` + `dsr_with_k()`（8b line 124-147 / 8c line 261-298）；`PSR/DSR_THRESHOLD=0.95` | 純接線（餵 candidate panel）|
| **4** | **PBO / Bootstrap** | A1/A2 `pbo` ≤ 0.20 + bootstrap 95% lower > 0 | `_pbo()`（8b line 554 / 8c line 758）+ `block_bootstrap_ci()`；`PBO_THRESHOLD=0.20` | 純接線 |
| **5** | **Replay data tier** | candidate evidence query 限 `engine_mode IN ('demo','live_demo')`；排除 synthetic / paper / smoke fixture row；source = self-hosted PG panel（ADR-0038）| 8b/8c SQL 源是 panel/market 真實表（非 synthetic）| `data_tier_attestation` 欄位：標注 source table + 「無 synthetic row」斷言 |
| **6** | **Runtime boundary** | grep runner + packet 0 hit：`live_reserved` / `max_retries` / `live_execution_allowed` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` / `execution_authority` / `decision_lease_emitted`；packet output 只 `eligible_for_demo_canary`，**絕不** emit `Stage 1 PASS` / `auto_promote` / order / fill / TOML mutation（AMD §3.2）| 8b/8c output 只 `eligible_for_demo_canary`（非 Stage 1 PASS）| `runtime_boundary_attestation` 欄位 + E2 grep 鉤子 |

> **check 1 + 6 = governance/grep 斷言**（非 stat）。runner 在 packet 內寫 attestation 欄位，
> 但**權威 PASS 由 E2 grep proof 給**（per PA profile：P0/P1 leak/look-ahead/selection finding
> 必附 call-path grep）。runner 只負責「結構性論證 + attestation 字串」，不自證 PASS。

### §3.2 輸出格式（JSON + per-check verdict + 整體 stage0_ready）

runner 輸出單一 JSON packet（`--format markdown` 亦支援，mirror 8b）：

```jsonc
{
  "runner_version": "candidate_stage0r.v1",
  "generated_at_utc": "2026-...",
  "window_days": 14,
  "cohort": ["BTCUSDT", "ETHUSDT"],
  "candidates": {
    "A1_funding_short_v2": {
      "alpha_source_id": "funding_short_v2",
      "candidate_thresholds": {"funding_threshold_annualized": 0.30, "branch": "short_only"},
      "harness": "w_audit_8b",
      "packet": { /* 8b compute_stage0r() 完整 packet（含 pooled_primary / psr/dsr/pbo/bootstrap/baseline_lift/concentration）*/ },
      "six_check": {
        "1_leak_lookahead":   {"verdict": "ATTEST", "evidence": "fwd-return future-bar + as-of point-in-time + no rolling-breach", "e2_grep_required": true},
        "2_bias_selection":   {"verdict": "PASS|FAIL", "max_day_share": 0.xx, "max_funding_cycle_share": 0.xx, "cap": 0.25},
        "3_dsr_psr":          {"verdict": "PASS|FAIL", "psr_0": 0.xx, "dsr": 0.xx, "threshold": 0.95},
        "4_pbo_bootstrap":    {"verdict": "PASS|FAIL", "pbo": 0.xx, "pbo_max": 0.20, "bootstrap_ci_95_60m_lower": 0.x, "bootstrap_ci_95_8h_lower": 0.x},
        "5_data_tier":        {"verdict": "ATTEST", "source_tables": ["panel.funding_rates_panel","panel.oi_delta_panel","market.klines"], "engine_mode_filter": "demo,live_demo", "synthetic_excluded": true},
        "6_runtime_boundary": {"verdict": "ATTEST", "emits_only": "eligible_for_demo_canary", "forbidden_output_present": false, "e2_grep_required": true}
      },
      "eligible_for_demo_canary": false,
      "fail_reasons": ["..."],     // 8b compute_stage0r() eligibility_fail_reasons passthrough
      "stage0_ready_candidate": false
    },
    "A2_liquidation_cascade_fade": {
      "alpha_source_id": "liquidation_cascade_fade",
      "candidate_thresholds": {"btc_threshold_usd": 500000.0, "eth_threshold_usd": 300000.0},
      "harness": "w_audit_8c",
      "packet": { /* 8c compute_stage0r_sweep() packet（含 per-tier × per-direction 4-value verdict）*/ },
      "six_check": { /* 同結構；check 2 加 max_symbol_share */ },
      "eligible_for_demo_canary": false,
      "fail_reasons": ["..."],
      "stage0_ready_candidate": false
    }
  },
  "verdict": "draft_only",          // 整體：reject / draft_only / observe_more / stage0_ready（per SSOT §6）
  "stage0_ready": false,            // bool：≥1 candidate 6/6 全 PASS/ATTEST 且 sample 足
  "verdict_basis": "..."
}
```

- **per-check verdict 三態**：`PASS` / `FAIL`（stat check 3/4，部分 2）、`ATTEST`（governance check 1/5/6，
  待 E2 grep 確認）。`ATTEST` 不等於 `PASS`：整體 `stage0_ready` 需 E2 grep proof 把 ATTEST → confirmed。
- **不引入新 verdict 規則**：candidate `eligible_for_demo_canary` 直接 passthrough 8b/8c packet 既有值
  （E2 8c round-1 HIGH-4 教訓：不自製 panel-level verdict 與 harness 衝突）。runner 整體
  `verdict` 用 SSOT §6 四 lane 映射（見 §4）。

---

## §4 Acceptance Gate（Stage 0R green 判據）

### §4.1 per-candidate `eligible_for_demo_canary=true` 判據（8b/8c 既有，runner 不改）

對齊 8b/8c `_candidate_fail_reasons`（8b line 1033-1099）+ A1/A2 spec + SSOT §5：

| 判據 | 閾值 | 來源 |
|---|---|---|
| PSR(0) | ≥ 0.95 | 8b/8c `PSR_THRESHOLD` |
| DSR | ≥ 0.95 | 8b/8c `DSR_THRESHOLD` |
| PBO | ≤ 0.20 | 8b/8c `PBO_THRESHOLD` |
| bootstrap 95% lower（60m + 8h/4h） | > 0 | 8b/8c bootstrap |
| avg_net_bps | ≥ +15 | 8b/8c `AVG_NET_FLOOR_BPS` |
| baseline lift | > 0 | 8b/8c `BASELINE_LIFT_FLOOR_BPS` |
| cost_edge_ratio | < 0.80 (8b) / < 0.60 (8c) | 8b/8c（cost gate；對齊 SSOT fee gate）|
| concentration | max_day_share ≤ 0.25；A2 max_symbol_share ≤ 0.30 | check 2 |
| n_eff floor | pooled ≥ 300 / symbol ≥ 100 / branch ≥ 50 | 8b/8c |
| 0 leak / runtime-boundary | E2 grep 0 hit | check 1/6 |

### §4.2 整體 `stage0_ready` 映射（SSOT §6 四 lane）

| 整體 verdict | 條件 | next step |
|---|---|---|
| `stage0_ready` | ≥1 candidate `eligible_for_demo_canary=true` **且** 6/6 check（stat PASS + governance E2-grep-confirmed ATTEST）| PA 出 Stage 0 dispatch；operator approve 進 demo canary（解鎖 AC-S2-A-3 evidence）|
| `observe_more` | candidate stat 方向正但 sample 不足（n_eff < floor / window 不足）| 擴 window（21/28d）或等更多 panel；非 signal failure |
| `draft_only` | candidate 結構合理但 1+ check FAIL（非 sample 問題）| 維持 DRAFT；不啟動 |
| `reject` | leak hit / runtime-boundary hit / 全 candidate negative net | archive |

> **誠實邊界（per 架構教訓 29 — readiness §4.3）**：8b round 1 RED 因 strategy gate self-imposed
> scarcity（primary n=7 vs baseline n=39,181）。runner 須在 packet 並列 candidate n_eff vs baseline
> 採樣率，QC review 時區分「sample insufficient → observe_more」與「signal failure → draft_only/reject」。
> **RED/FAIL 不自動 = reject**；多數早期結果預期落 `observe_more`（candidate active=false，replay 窗短）。

---

## §5 與後續 Chain（runner 在大圖的位置）

```
[本 runner land + 跑] → per-candidate 6-check packet
   │
   ├─ stage0_ready=true (≥1 candidate)
   │     → PA 出 Stage 0 dispatch recommendation（SSOT §6）
   │     → operator/PM gate：approve A1/A2 進 Stage 1 demo micro-canary
   │           (AMD §4.1 + §7 pre-launch gate；解鎖 candidate active=true)
   │     → candidate 開始累積 demo fills
   │     → AC-S2-A-3 evidence（14d demo avg_net>5bps + Wilson lower>0 + n≥30）~2026-06-11
   │     → W2-F MIT attribution_chain_ok 100%
   │     → W3-C TW + PM sign-off → Wave 3 stage0_ready 出口
   │
   ├─ observe_more → 擴 window 重跑（runner 可重入；不阻）
   └─ draft_only/reject → 寫 learning.hypotheses DRAFT；不啟動
```

**runner 硬邊界（per CLAUDE §四 + 16 原則 #3/#7 + DOC-08 §12）**：
- **純 offline replay 分析**：read-only PG SELECT，不下單、不碰 live、不寫 trading.* / panel.* /
  market.*、不調 Rust、不碰 authorization / lease / paper / mainnet enablement。
- **不解鎖 candidate**：`stage0_ready=true` 只是**證據**，candidate active=true 由 operator/PM gate 決定
  （runner 絕不改 TOML / 絕不 emit auto_promote）。
- runner 是 **gate 1（Stage 0R sanity）的解鎖件**，gate 1 解鎖才能談 gate 5 evidence 累積
  （雞蛋次序：Stage 0R green → operator approve → demo fills → AC-S2-A-3）。

---

## §6 LOC Budget + 工時估 + E1 Chain

### §6.1 LOC budget

| 物件 | LOC | 說明 |
|---|---|---|
| `candidate_stage0r_runner.py` | 280-360 | argparse + 2 candidate 配置 dict + 委派 8b/8c wrapper + 組 6-check packet + verdict 映射 + JSON/markdown render |
| `alpha_candidate_stage0r/__init__.py` | 3 | mirror 8b |
| 頂層 shim `reports/alpha_candidate_stage0r.py` | 15 | 委派 package（mirror 8c shim 慣例）|
| smoke test `candidate_stage0r_smoke.py` | 120-180 | mock 8b/8c packet → verify 6-check 組裝 + verdict 映射 + 0 forbidden output；不連 PG（mirror 8c smoke_cli 範式）|
| SCRIPT_INDEX.md 更新 | ~3 行 | hard rule |
| **合計** | **~420-560** | 全在 800 LOC 警戒線下；無單檔 > 800 |

> **無 SQL 新增**（復用 8b/8c features.sql）。**無 Rust 觸碰**（runner 純 Python offline）。
> **無 metrics 改動**（復用既有統計核）。surgical scope。

### §6.2 工時估

| 階段 | hr | 內容 |
|---|---|---|
| E1 IMPL | 8-12 | runner + __init__ + shim + smoke test + SCRIPT_INDEX；主工 = candidate cohort/threshold pin + 6-check packet 組裝 + verdict 映射；統計核複用故無新算法 |
| QC stat review | 2-3 | 確認 PSR/DSR/PBO/bootstrap 閾值對 candidate 語意正確；A1 short-only branch 對映 8b `crowded_short_squeeze`（funding 正 + price overshoot 的 fade）語意正確；sample sufficiency 判據 |
| E2 adversarial | 2-3 | check 1/6 grep proof（runner + candidate Rust diff 0 rolling-breach / 0 runtime-boundary hit）；確認 0 forbidden output；leak surface review |
| E4 regression | 1-2 | smoke test 跑 PASS + Linux ssh 連 PG 實跑 1 次 candidate runner（empirical，非 mock）確認 packet 結構 + exit code |
| **合計** | **12-18 hr** | active engineering hr（不含 evidence 累積等待）|

### §6.3 E1 dispatch chain（並行性）

- **單 E1 串行即可**（單檔 runner，無多檔並行收益；smoke test 同 E1 一併出）。
- E1 IMPL DONE → **強制 A3+E2 並行核驗**（per memory `feedback_impl_done_adversarial_review`：
  IMPL 涉共用 helper / 寫 packet / grep-sensitive → 不接受單獨 sign-off）+ QC stat review 並行。
- E4 regression（Linux ssh PG 實跑）**不能取代** E2 grep proof（check 1/6 governance）。

### §6.4 E1 IMPL 注意事項（避坑）

1. **不改 8b/8c SQL / metrics**：只在 runner 層 pin 參數。改 SQL = 破 leak-free 不變量。
2. **A1 branch 對映**：A1 short-only = 8b `crowded_short_squeeze` branch（funding 正高 + short
   收 funding + mean-revert）。但 8b branch gate 含 `z <= -z_hi`（funding **低**側 squeeze）—
   E1 + QC 須確認 A1「funding > 30% annualized 正側 → short fade」與 8b branch 方向語意一致；
   **若不一致，runner 須用 8b `funding > 30% annualized` 對映正確 branch / 或 QC waiver 記錄**。
   （這是 §6.2 QC review 2-3 hr 的核心驗點，E1 不可自行假設。）
3. **packet `ATTEST` ≠ `PASS`**：check 1/5/6 標 ATTEST，整體 `stage0_ready` 須 E2 grep confirm 後
   才可由 PA/PM 升 confirmed。runner 不自證 governance PASS。
4. **cargo race 教訓**（PA memory line 6087）：E4 ssh PG 實跑 runner 是 read-only SELECT，不觸
   engine restart / cargo test，無 binary inode 覆蓋風險；但 E4 dispatch 仍避免在 engine
   startup 後 ~8s 內觸 cargo（本任務不需 cargo，僅 PG SELECT）。
5. **跨平台**（CLAUDE §六 + memory cross_platform）：runner 用 8b 既有 `_repo_root()`
   （`OPENCLAW_BASE_DIR` env 或 `Path(__file__).parents[N]`），不硬編碼 `/home/ncyu` /
   `/Users/ncyu`；DSN 走 env（mirror 8b `_get_conn` line 36-43）。

---

## §7 副作用清單（per PA profile）

1. **[risk 低] 復用 8b/8c wrapper import**：runner import 8b/8c report wrapper 的 public 函數
   （`_get_conn` / `fetch_feature_rows` / `compute_stage0r` / `compute_stage0r_sweep`）。8b/8c
   是研究 script 非 production hot path，無下游 import 8b/8c 的 production 模塊（[INFER] 待 E2 grep
   confirm `from helper_scripts.reports.w_audit_8` 的 caller 範圍）。runner 加 import 不改 8b/8c 行為。
2. **[risk 低] packet schema 下游消費**：若未來 GUI Stage 0R status row / earn preflight 範式
   讀 runner packet，須對齊既有 Stage 0R JSON 防偽範式（age + 可選 hash，per earn_routes.py）。
   Sprint 2 無此下游，標 future note。
3. **[risk 中 / governance] verdict 誤判**：observe_more vs draft_only/reject 須由 QC 區分
   sample-insufficient vs signal-failure（§4.2 誠實邊界）。runner 並列 baseline 採樣率輔助判斷。
4. **[硬邊界] check 6**：runner packet 絕不 emit `Stage 1 PASS` / `auto_promote` /
   `canary_stage_log.to_stage=1` / order / fill / TOML mutation（AMD §3.2 forbidden output）。
   E2 review 必 grep。**這是本 spec 唯一極高敏感點**。
5. **[risk 低] 8b/8c wrapper DB connect 失敗路徑**：8b wrapper line 273-277 fail-closed
   exit code 2（DB connect fail）/ exit 1（query fail）。runner 須 propagate（不吞錯）。

---

## §8 E2 必查 3 點（高風險警告 — per PA profile 輸出標準）

1. **check 6 runtime-boundary grep**：runner source + 輸出 packet 0 hit
   `live_reserved|max_retries|live_execution_allowed|OPENCLAW_ALLOW_MAINNET|authorization\.json|execution_authority|decision_lease_emitted`；
   packet 只含 `eligible_for_demo_canary` 不含 `Stage 1 PASS|auto_promote|to_stage`。
2. **check 1 leak-free grep**：runner 不改 8b/8c SQL forward-return / LATERAL / cutoff；
   candidate Rust strategy diff（funding_short_v2 + liquidation_cascade_fade）0 `rolling(N).max()`
   含-current-bar breach pattern（per memory `feedback_indicator_lookahead_bias`）。
3. **A1 branch 對映正確性**：8b `crowded_short_squeeze` branch gate 方向與 A1「funding > 30%
   annualized → short fade」thesis 一致（§6.4 #2）；若不一致是 silent 統計錯（最易漏，
   mock test 不抓語意），E2 + QC 雙確認。

---

## §9 References

- 8b harness: `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_{metrics,report}.py` + `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql`
- 8c harness: `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_{metrics,report}.py` + `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`
- A1 spec: `docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md`（cohort line 149 / 30% gate line 41,182 / leak §5）
- A2 spec: `docs/execution_plan/2026-05-25--alpha_candidate_4_liquidation_cascade_fade_spec.md`（cohort line 188 / $500k/$300k line 99-100,220-221 / leak §1.5）
- SSOT: `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`（§5 minimum gates / §6 output lanes / §8 chain）
- 6 sanity def: AMD-2026-05-15-01 §3.3
- readiness: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--sprint2_stage0r_preflight_readiness.md`

---

**Spec END — E1 IMPL-ready**

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/specs/2026-05-29--a1a2-stage0r-candidate-runner-spec.md`

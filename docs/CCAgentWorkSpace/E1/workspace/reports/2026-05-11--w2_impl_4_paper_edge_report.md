# W2-IMPL-4 — D+12 paper edge report 工具鏈 IMPL DONE

**Author**: E1
**Date**: 2026-05-11
**Sub-task**: PA W2 IMPL v1.2 chain sub-agent 4 / 5（D+12 paper edge report 工具鏈）
**Spec**: `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` v1.2
**Dispatch**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w2_impl_v12_dispatch_plan.md` §1 §3.4
**Working dir HEAD**: `21ed6d3e`

---

## §1 任務摘要

W2-IMPL-4 scope：D+12 paper engine 跑 7d evidence 收集後的 paper edge report 工具鏈。包含：
1. 離線 counterfactual SQL（從 V088 panel + trading.fills + trading.klines 三方拉資料，算三方向 expected_dir +1/-1/0 counterfactual net edge bps）
2. Python 工具：跑 SQL + 算 spec v1.2 §7.1 mandatory 6 metric + 渲染 markdown
3. 6 mandatory metric：
   - pooled + per-symbol breakdown（n≥100+t>2.0 gate）
   - DSR K=95 deflate（mu_0=√(2 ln 95)=3.0179）
   - PSR(0) Bailey-López de Prado 2012 skew/kurt-aware formula（**禁 normal z-test**）
   - Alpha decay R²(N=60/120/300) regime test
   - Block-bootstrap 95% CI（block_size=60min, 1000 iter）
   - Per-cohort counterfactual delta（LONG/SHORT/no-signal 三方向）
4. dual-layer σ acceptance（raw market σ_60=4.54 / σ_120=6.28 / σ_300=10.08 bps + net edge σ=50-80 bps）
5. spec v1.2 §8.1 +15 / +5~+15 / <+5 三檔 step gate verdict
6. 3 mock case smoke-test（plus15 / plus5_15 / minus5）

W2 IMPL v1.2 chain 0 file 重疊 — 與 W2-IMPL-1/2/3 並行（per dispatch §0.2 + §4）。

---

## §2 修改清單

| File | 性質 | LOC | 用途 |
|---|---|---|---|
| `srv/sql/queries/w2_btc_alt_lead_lag_counterfactual.sql` | 新檔 | 279 | spec §7.2 三方向 counterfactual SQL + UNNEST WITH ORDINALITY + LEAD() 60s/120s/300s forward return |
| `srv/helper_scripts/reports/w2_paper_edge_report.py` | 新檔 | 1257 | spec §7.1 6 mandatory metric + dual-layer σ + PSR(0) Bailey-LdP 2012 + 三檔 step gate verdict + 3 mock smoke-test |
| `srv/helper_scripts/SCRIPT_INDEX.md` | 修改 | +1 | 加入 reports/w2_paper_edge_report.py 索引行 |

**0 file 重疊**：與 W2-IMPL-1 (panel_aggregator/btc_lead_lag.rs 接 orderbook) / W2-IMPL-2 (main.rs env-gate + spec amendment + cross_asset/mod.rs MODULE_NOTE) / W2-IMPL-3 (passive_wait_healthcheck/checks_btc_lead_lag.py [57]) 完全並行。

---

## §3 6 Mandatory Metric 實作對齊（per dispatch §3.4 acceptance criteria）

| Metric | 公式對齊 | File:line |
|---|---|---|
| 1. Pooled + per-symbol breakdown（n≥100+t>2.0 gate）| `compute_per_symbol_metrics` 對 cohort 內每 symbol 算 avg_net / stdev / t-stat / sample_n + group_by symbol；`compute_pooled_metrics` 為 cross-symbol aggregate；`step_gate_verdict` 對 (n, t-stat) 階段判 promote-eligible | `w2_paper_edge_report.py:467-575`（pooled）/ `:357-465`（per-symbol） |
| 2. DSR K=95 deflate | mu_0 = √(2 ln 95) = 3.0179；DSR = PSR(mu_0)（per Bailey-LdP 2014 §4.2）| `w2_paper_edge_report.py:283-300` (`compute_dsr_with_k_deflate`) |
| 3. PSR(0) Bailey-LdP 2012 strict | `Φ((SR_hat - 0) × √(n-1) / √(1 - skew·SR + ((kurt-1)/4)·SR²))`；禁 normal z-test；denom_sq ≤ 0 → None fail-closed；skew + kurt 用 7d empirical | `w2_paper_edge_report.py:230-280` (`compute_psr_bailey_lopez_de_prado_2012`) |
| 4. Alpha decay R²(N=60/120/300)| OLS regression：β₁ = Cov(x,y)/Var(x)；R² = 1 - SS_res/SS_tot；三檔 N 對應 `btc_lead_return_pct_60s` / `btc_lead_return_pct` (N=120 主) / `btc_lead_return_pct_300s` × `alt_forward_return_*` | `w2_paper_edge_report.py:332-373` (`compute_alpha_decay_r_squared`) |
| 5. Block-bootstrap 95% CI | block_size=60min, 1000 iter, deterministic seed=20260512；moving-block bootstrap (Künsch 1989) | `w2_paper_edge_report.py:303-330` (`compute_block_bootstrap_ci`) |
| 6. Per-cohort counterfactual delta | LONG/SHORT/no-signal 三方向 group + `cf_long_avg` / `cf_short_avg` / `cf_no_sig_baseline`；對齊 SQL CASE WHEN expected_dir = -1/0/+1 三 branch | `w2_paper_edge_report.py:436-461`（per-symbol 整合）；SQL `:189-227`（CASE WHEN） |

---

## §4 PSR(0) Formula 引用（per dispatch §3.4 E2 review point 2）

**Reference**: Bailey, D. H., & López de Prado, M. (2012). "The Sharpe Ratio Efficient Frontier". *Journal of Risk*, 15(2), 13-44.

**Formula** (per spec v1.2 §7.1 metric (3) 強制條件):
```
PSR(SR*) = Φ((SR_hat - SR*) × √(n - 1) /
              √(1 - skew·SR_hat + ((kurt - 1) / 4)·SR_hat²))
```

- Φ = standard normal CDF（用 `math.erf` cross-platform 實作，無 scipy 依賴）
- SR_hat = sample (non-annualized) Sharpe = mean / stdev
- n = sample size
- skew + kurt = 7d empirical biased moment estimator
- threshold ≥ 0.95（per spec §7.1 metric (3)）
- PSR(0) = PSR with SR* = 0（H0 benchmark）
- DSR = PSR with SR* = mu_0 = √(2 ln K)（K=95 active strategy×symbol cell 總數，per Bailey-LdP 2014 §4.2）

**設計 invariant**：
- denom_sq ≤ 0（極端 skew + 高 SR 組合）→ 函數回 None，spec acceptance 視為 fail（fail-closed，禁假樂觀）
- skew, kurt 計算需 n ≥ 4 sample；資料不足 → None
- σ = 0（全相同樣本）→ None

**spec v1.2 §7.1 metric (3) 強制**：`crypto JB normality 必拒（5d block resampling 已 verify per MIT C-3 §7）→ 禁用 normal SR z-test → 強制 B-LdP 2012 formula`。本實作完全對齊（驗 `inspect.getsource` 含 `skew + kurt + _normal_cdf`）。

---

## §5 Smoke-test 3 Mock Case PASS（per dispatch §3.4 E4 regression）

跑 `python3 helper_scripts/reports/w2_paper_edge_report.py --smoke-test`：

```
=== W2 paper edge report smoke test ===
(per dispatch §3.4 E4 regression：plus15 / plus5_15 / minus5)

Case 1: plus15 (gross +20 bps, n=150, expected promote N+2)
  ETHUSDT: n=150 avg_net=19.87 t=86.454 verdict=plus15
  pooled: avg_net=19.87 verdict=plus15

Case 2: plus5_15 (gross +8 bps, n=150, expected extend 14d)
  ETHUSDT: n=150 avg_net=7.91 t=34.436 verdict=plus5_15
  pooled: avg_net=7.91 verdict=plus5_15

Case 3: minus5 (gross -3 bps, n=150, expected revise/archive)
  ETHUSDT: n=150 avg_net=-2.99 t=-12.933 verdict=minus5
  pooled: avg_net=-2.99 verdict=minus5

  PSR(0) case 1 = 1.0000 ≥ 0.95 ✅ (Bailey-LdP 2012 formula)
  DSR(K=95) case 1 = 1.0000 (mu_0=√(2 ln 95)=3.018)

  Case 1 95% CI = [19.628, 20.174] (block_size=60, 1000 iter)

  Alpha decay R²(60/120/300) case 1: 0.0094 / 0.0094 / 0.0094

==================================================
ALL PASS — 3 mock case + PSR(0) + DSR + CI + R²(N) 公式驗證通過
```

**Exit code = 0**（E4 regression gate PASS）。

---

## §6 SQL 設計重點（per dispatch §3.4 E2 review point 1 + 2）

### SQL 三方向 counterfactual 對齊 expected_dir +1 / -1 / 0

```sql
CASE
    WHEN pe.expected_dir = 0 OR ak.close_current IS NULL OR ak.close_current = 0
          OR ak.close_forward_120s IS NULL
        THEN NULL
    ELSE (pe.expected_dir::REAL *
          ((ak.close_forward_120s - ak.close_current) / ak.close_current * 10000))::REAL
END AS cf_net_edge_120s_bps
```

- `expected_dir = +1` → cf_net_edge = +1 × alt_forward_return (LONG entry)
- `expected_dir = -1` → cf_net_edge = -1 × alt_forward_return (SHORT entry)
- `expected_dir = 0`  → NULL（無信號 baseline，不計入 net edge avg）
- 60s / 120s / 300s 三 forward window 並列（spec §7.1 metric 4 R²(N) decay curve evidence）

### Strict shift(N) lookahead-free

- writer 端寫 BTC lead = past N 秒前的 close
- SQL reader 端 LEAD() 取 alt forward = future 1/2/5 bar 的 close
- 兩端時序合在 panel.snapshot_ts_ms 對齊 1m bucket（無 current bar leak）

### regime extreme filter

- SQL 不在 WHERE 排除 regime_tag='extreme'，保留分流給 Python 端 decisional FILTER
- Python `compute_per_symbol_metrics` / `compute_pooled_metrics` 內走 `normal_rows = [r for r in sym_rows if r.get("regime_tag") == "normal"]`（per spec §7.2 + §9 condition #5）
- markdown 報告分 §3 列出 extreme regime n（reviewer 透明可查）

### 純 READ-ONLY 不變式

regex sanity check 確認：
- 5 CTE（params / panel_window / panel_expanded / alt_klines / paper_fills_bucketed）
- 7 psycopg2 `%(...)` placeholder
- 0 `INSERT INTO` / 0 `UPDATE SET` / 0 `DELETE FROM` / 0 DDL（CREATE/ALTER/DROP/TRUNCATE）

---

## §7 治理對照

### §7.1 16 根原則合規

| 原則 | 觸碰？ | 對應 |
|---|---|---|
| 1 單一寫入口 | 無 | 純 READ-ONLY 工具，不寫任何 trade order 路徑 |
| 4 不繞風控 | 無 | 純 READ-ONLY 工具，不觸碰 SM-04 Guardian |
| 7 學習 ≠ 改寫 Live | 無 | paper engine evidence collection 純後驗，不改 live |
| 8 交易可解釋 | 強化 | per-cohort counterfactual delta + per-symbol breakdown 強化 reconstruct alpha source |
| 13 AI 成本感知 | 無 | 純 Python 統計，無 LLM 調用 |
| 14 零外部成本 | 維持 | 工具用本機 PG，無外部依賴 |

### §7.2 DOC-08 §12 + 硬邊界 5 項

- `live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `decision_lease` / `authorization.json` — **0 觸碰**（純後驗工具）
- DOC-08 §12 9 條安全不變量 — **0 觸碰**（不動 lease / authorization / audit / reconciler / mainnet env / Bybit retCode）

### §7.3 跨平台兼容性（CLAUDE.md §七 ★★ 強制）

- 路徑不硬編碼：用 `os.environ.get("OPENCLAW_BASE_DIR")` fallback 到 `Path(__file__).resolve().parent.parent.parent`
- 純 stdlib（math / random / statistics）：無 scipy / numpy / pandas 依賴 → Mac dev + Linux runtime 同 binary 跑
- psycopg2 lazy-import 進 `_get_conn()`：smoke-test 不需 PG（per CLAUDE.md §七 hygiene rule）
- `Φ` standard normal CDF 用 `math.erf` 替代 `scipy.stats.norm.cdf` → 跨平台 zero-dep

### §7.4 注釋規範（2026-05-05 governance：默認中文）

- MODULE_NOTE 雙語對照（中為主，英文 reference 段保留）— per 用戶在 task 中明示「中文輸出 + 中文注釋」
- 統計 helper docstring 中文 + 公式英文 reference（學術 reference 不譯）
- 純中文 inline 註釋（per `feedback_chinese_only_comments.md` 修改既有時移除英文保留中文）

---

## §8 不確定之處 / 待 E2 + E4 review 確認

1. **Python 1257 LOC > 800 警告線**（per CLAUDE.md §九 ⚠️ E2 必標記）
   - 拆分提案（如 E2 push back）：
     - `w2_paper_edge_metrics.py`（統計公式 + step_gate_verdict）~ 300 LOC
     - `w2_paper_edge_render.py`（markdown render）~ 300 LOC
     - `w2_paper_edge_smoke.py`（3 mock fixture + run_smoke_test）~ 300 LOC
     - 主 `w2_paper_edge_report.py`（CLI + PG conn + 整合）~ 350 LOC
   - 取捨：single-file 對 operator 一鍵跑 + 部署 + report copy 簡單；4-file 結構解耦但增加 import + cross-module ref 複雜度
   - E2 / PM 拍板決定

2. **Linux PG empirical dry-run**（per `feedback_v_migration_pg_dry_run.md` 強制 + dispatch §3.4 E4 mandatory）
   - Mac 上 ssh trade-core 不可達（~/.ssh/config 無 entry，當前 Mac dev workflow 走 git push + Linux pull pattern）
   - 屬 E4 regression gate 範圍：跑 `psql -f sql/queries/w2_btc_alt_lead_lag_counterfactual.sql` 驗
     - schema correctness（V088 已 deployed verified）
     - row count plausibility（D+0 預期 0 row paper 還未跑；D+5 paper engine deploy 後才有真實 row）
     - EXPLAIN ANALYZE 驗 hot-path index `idx_btc_lead_lag_panel_ts_window` 命中
   - E4 端要做、不在 W2-IMPL-4 IMPL DONE 範圍內

3. **PSR(0) sample SR 是否 annualize**（spec v1.2 §7.1 解讀）
   - 本實作 SR_hat = mean(bps) / stdev(bps) sample SR（per-fill 單位）
   - spec power calculation 用 net edge σ_net = 50-80 bps + μ=15 bps → SE=σ_net/√N → t-stat
   - 這對應 **per-sample** SR 而非 annualized；若 spec 強制 annualized SR（× √(252×24×60) 等）需告知（W2-IMPL-4 IMPL 認為 sample-SR 直接對齊 §8.1 power table）
   - E2 / PM 確認對齊 spec power table 公式

4. **block_size=60min 對 1m grain 樣本的 sample-unit 對應**
   - 本實作 `block_size=60 sample`（60 個 1m grain sample 對齊 60min wall-clock）
   - 假設 SQL 出來的 row 在 panel.snapshot_ts_ms 1m grain（V088 spec §4.1 強制）
   - 若 paper engine 1m 中有缺失（e.g. WS reconnect 漏 row）→ block_size 60 sample 不嚴格對應 60min wall-clock
   - spec §7.1 metric (5) 沒明指 sample-unit vs wall-clock 但常規 statistical sense 用 wall-clock；E2 可考慮對 missing row 補 forward-fill 或標 None；本實作不補（passing pure raw data through）

5. **mock fixture R²(N) = 0.0094 偏低**（per smoke-test output）
   - mock 構造的 BTC lead jitter (±3 bps) 與 alt forward return 無真實 linear 關係 → R²(N) ~ 0 預期
   - 實 paper engine 跑 7d 後 BTC lead vs alt forward 有 microstructure literature 預估 R² 0.06-0.10
   - 不影響 verdict 邏輯，只是 smoke-test 不 cover「R²(N) > 0.04 PASS」case；可未來補 mock case 4 (high-correlation fixture)
   - 不阻 W2-IMPL-4 IMPL DONE，但 E4 regression test pack 可考慮補

---

## §9 Operator 下一步

1. **E2 對抗審查**（per CLAUDE.md §八「強制工作鏈 E1→E2→E4→PM」+ dispatch §3.4 重點）：
   - SQL 對齊 expected_dir +1/-1/0 三方向（counterfactual 三方向 verdict）— **預期 PASS**（SQL §5 三 CASE WHEN 對齊）
   - PSR(0) 禁 normal z-test，必用 Bailey-LdP 2012 formula — **預期 PASS**（`compute_psr_bailey_lopez_de_prado_2012` `inspect.getsource` 含 skew + kurt + Φ-CDF）
   - block-bootstrap 95% CI 抽樣方式正確 — **預期 PASS**（moving-block bootstrap, deterministic seed, 1000 iter）
   - 1257 LOC 超 800 警告 — 需 E2 拍板拆 file 或維持 single-file（建議 single-file，operator 一鍵跑簡單）

2. **E4 regression**（per dispatch §3.4 + `feedback_v_migration_pg_dry_run.md`）：
   - 3 mock case smoke-test 已 ALL PASS（Mac 端跑 + 待 E4 在 Linux 重跑驗無 platform-specific drift）
   - **Linux PG dry-run mandatory**：
     - `ssh trade-core "cd ~/BybitOpenClaw/srv && psql ... -f sql/queries/w2_btc_alt_lead_lag_counterfactual.sql -v window_days=7 -v cohort_symbols='{ETHUSDT,SOLUSDT,...}'"` 驗 SQL 對 V088 + trading.fills + trading.klines 三方真實 schema 跑得對
     - D+0 預期 panel.btc_lead_lag_panel 0 row（producer 還未 deploy）→ SQL 出來 0 row 是正常；Python 端對 0-sample 退化 verdict=no_signal
     - 後續 D+5 paper engine deploy + 7d 跑後（D+12）才有真實 row 跑完整 report

3. **PM 整合 sign-off**（per dispatch §1）：
   - W2-IMPL-4 land 後 等 W2-IMPL-1 + W2-IMPL-2 + W2-IMPL-3 並行完成（4 並行 sub-agent）
   - W2-IMPL-5 rebase IMPL-1 + IMPL-2 head 後跑 E2 fence 對抗 + E4 regression
   - D+5 deploy paper engine 開始 7d evidence collection
   - D+12 跑 `python3 helper_scripts/reports/w2_paper_edge_report.py` 產 paper edge report
   - PA + QC + MIT 三角 sign-off 決定 N+2 promote / extend / archive

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_4_paper_edge_report.md`）

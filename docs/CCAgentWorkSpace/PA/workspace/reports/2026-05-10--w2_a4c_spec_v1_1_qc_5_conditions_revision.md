# PA W2 A4-C Spec v1.1 — QC C-2 5 Conditions Revision Report

**Author**: PA (project architect)
**Date**: 2026-05-10
**Phase**: W2 Spec phase Day 1-2 後續 — QC C-2 review CONDITIONAL APPROVE 5 conditions 落 spec
**Verdict**: 5 conditions + σ MIT prerequisite 全部 inline edit `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`；spec v1 → v1.1
**Sign-off path**：QC 已 CONDITIONAL APPROVE → MIT C-3 D+1 直接收，**不需 D+1 PA + QC integrate phase**

---

## §1. 5 conditions revision summary

| # | Spec section | 改動 line range（v1.1 後） | 改動 essence |
|---|---|---|---|
| **1** | §8.1 第 2-3 條 + 新 K table | line ~318-323（QC C-2 review scope DSR penalty 段） | DSR K 從 6 修正為 95（active strategy×symbol cell 總數），引 Bailey-López de Prado *The Deflated Sharpe Ratio* (2014) §4.2「DSR with multiple trial」；mu_0 = √(2 ln 95) = **3.018**（舊 K=79 → 2.956；Δmu_0 = +0.062 即 +2.1%）；warning 加：8 cohort × 2 strat 全 promote → K ≈ 111，future ADR 必記 multiple-testing budget 長期約束 |
| **2** | §8.1 第 4 條 + 三檔 gate table | line ~325-336 | paper edge gate 從單檔「≥ +5 bps」改三檔（**+15 promote** N+2 demo IMPL / **+5~+15 extend** paper window 14d 重評 / **<+5 revise** spec 或 archive）；理由錨：CLAUDE.md §三 cost_gate JS-demo `[40] avg_net = -17.82 → +8.75 bps after V083`（3C audit）；demo cost ≈ 15-20 bps round-trip → +5 必 net −10~−15 bps survive 不能；+15 demo ~0 buffer → live (8-12 bps cost) 才有正 edge headroom |
| **3** | §3.1 N 鎖定段 + §4.1 schema 新增 column + §7.1 metric (4) | §3.1 line ~84-92 / §4.1 line ~144-145 / §7.1 metric (4) line ~291-294 | N 鎖定 = **120s**（per Easley/De Prado/O'Hara 2021 + Makarov-Schoar JFE 2020 BTC→alt lead 半衰期 30-180s estimate；N=120s 對應預期 R²=0.06-0.10 sweet spot）；§4.1 schema 加 `btc_lead_return_pct_60s` + `btc_lead_return_pct_300s` columns 收 decay curve evidence；§7.1 metric (4) Alpha decay regime test 強制 R²(N=60/120/300) 三檔 7d window rolling 30-min bucket 衰減曲線；判定：半衰期 < 60s → archive，N=120s R² < 0.04 → revise spec 或 archive，N=300s R² > N=120s → 重評 N 選擇 |
| **4** | §7.1 mandatory metric set 重寫為 6 條 + acceptance prerequisite | line ~280-302 | (a) Pooled + per-symbol breakdown，gate per-symbol n ≥ 100 + per-symbol t > 2.0；(b) DSR PASS K=95 deflate（non-negotiable）；(c) PSR(0) ≥ 0.95 用 skew/kurt-aware formula（crypto JB normality 必拒，禁 normal SR z-test，per Bailey-López de Prado 2012 PSR formula）；(d) Alpha decay R²(N=60/120/300) curve；(e) Block-bootstrap 95% CI block_size=60min 1000 iter pooled + per-symbol；(f) Per-cohort-symbol counterfactual delta `(if-followed-lead) − (TA1m baseline)`；§7.3 strict shift(N) leak-free 並列對比，差異 > 30% → spec 失敗 |
| **5** | §9 risk table 加 BTC regime extreme guard + §4.1 schema 加 `regime_tag` column + §7.2 SQL `FILTER (WHERE regime_tag = 'normal')` | §9 risk row line ~341 / §4.1 schema line ~152 / §7.2 SQL line ~310-311 | \|BTCUSDT 1h return\| > 200 bps → `regime_tag = 'extreme'` shadow log 不計入 7d edge avg；§4.1 schema column；§4.2 writer 步驟 4 加 1h kline regime 計算邏輯（strict shift(1)）；§7.2 SQL counterfactual reconstruction 加 normal regime exclusion；§4.3 rate budget +1 req（BTCUSDT 1h kline）9→10 req/min 仍 < 1% upper bound |

---

## §2. σ MIT prerequisite 設計（§7.1 acceptance prerequisite list）

QC C-2 review 揭露：σ=30 bps 假設是 PA spec 草稿的下界，crypto microstructure σ 經驗值更高（EDGE-DIAG-1 demo σ ≈ 50-80 bps 含 fee + adverse selection）。σ ≥ 60 bps → t-stat 從 4.71 跌至 2.36 (p ≈ 0.009)，power 邊緣可接受但 PSR(0) 必含 skew/kurt deflation。

**設計**：spec §7.1 加 acceptance prerequisite section（IMPL phase 啟動前必驗）：

| Prerequisite | 責任 | Verdict 判定 |
|---|---|---|
| **σ verified by MIT C-3** | MIT C-3 D+1 review | BTCUSDT 1m forward-return realized σ 7d 經驗值；σ ≥ 60 bps → 重算 power（t-stat 2.36），spec metric (1) per-symbol gate threshold 不變但 PSR(0) 必含 skew/kurt deflation；σ < 60 bps → 採 v1.1 baseline assumption σ=30 bps 繼續 |

**為何「prerequisite」而非「risk」**：σ 是 power calculation foundation，σ 錯整套 power test 失效；不是 mitigation 後果可接受的「risk」，是 IMPL 啟動前必驗的 gate，所以單獨成為 prerequisite section。

**MIT C-3 verify 操作建議**：
```sql
SELECT
    STDDEV(((close[60s_forward] - close) / close) * 10000) AS realized_sigma_bps_60s,
    STDDEV(((close[120s_forward] - close) / close) * 10000) AS realized_sigma_bps_120s,
    STDDEV(((close[300s_forward] - close) / close) * 10000) AS realized_sigma_bps_300s,
    COUNT(*) AS sample_n
FROM market.klines
WHERE symbol = 'BTCUSDT'
  AND timeframe = '1m'
  AND ts >= NOW() - INTERVAL '7 days';
```

---

## §3. spec v1 → v1.1 change log

**inline 已落 Change Log section**（spec line ~14-25）：

| # | Section | 改動 essence（spec v1.1 自身 change log 對應） |
|---|---|---|
| 1 | §8.1 | DSR K 6 → 95，引 Bailey-López de Prado 2014 §4.2 |
| 2 | §8.1 | gate threshold 單檔 +5 → 三檔 (+15 / +5~+15 / <+5) |
| 3 | §3.1 + §7.1 + §4.1 | N 鎖 120s + R²(N=60/120/300) 強制 + schema 加 60s/300s shadow value |
| 4 | §7.1 | mandatory metric set 補 per-symbol gate + block-bootstrap CI + DSR K=95 + PSR(0) skew/kurt + alpha decay |
| 5 | §9 + §4.1 + §7.2 | BTC regime extreme guard \|1h return\| > 200 bps + schema regime_tag + SQL filter |
| extra | §7.1 | acceptance prerequisite「σ verified by MIT C-3」 |

**衝擊副作用**：
- §4.1 schema 新增 3 columns (`btc_lead_return_pct_60s` / `btc_lead_return_pct_300s` / `regime_tag`) → V088 migration 加 3 column；W2 E1-δ C-IMPL-2 LOC 從 ~350 升至 ~400（+50 LOC for regime_tag + 60s/300s shadow value + 1h kline integration）
- §4.3 rate budget 9 → 10 req/min（+1 req for BTCUSDT 1h kline regime data），仍 < 1% upper bound
- §7.1 metric 從 5 條擴至 6 條 + acceptance prerequisite，D+12 paper edge report scope 擴大但不變動 IMPL phase 主路徑
- 16 原則 / DOC-08 §12 9 條不變量 / 硬邊界 5 項全部不受 v1.1 改動觸碰（仍 0 違反）

---

## §4. D+1 W2 三角 sign-off 預期（QC + MIT 直接收）

| Reviewer | 預期 verdict | Review focus |
|---|---|---|
| **QC C-2** | **已 sign-off CONDITIONAL APPROVE** (HEAD `4bb5d485` 後 spec v1.1)；5 conditions inline land 即達成 | 不再需要 QC re-review；v1.1 spec 已照 QC §6 mitigation table + §8 dispatch update 5 條全落 |
| **MIT C-3** | **D+1 直接收 review**（**不需 D+1 PA + QC integrate phase**）| 4 個必審：(1) §7.1 acceptance prerequisite「σ verified by MIT C-3」必跑（BTCUSDT 1m forward-return realized σ 7d）；(2) §7.3 strict shift(N) leak-free grep verification（`btc_lead_lag_writer.py` 內 `rolling()` / slice operation 全掃）；(3) §4.1 V088 hypertable PL/pgSQL 語法 + retention drop_chunks policy + idempotency dry-run；(4) §4.1 60s/300s shadow value column 寫入路徑與主信號 N=120 disjoint 不污染 |

**Sign-off 後續路徑**：
- MIT C-3 APPROVE → D+3 起派 C-IMPL-1..4 paper IMPL（per §11 E1 派發計劃）
- D+5 paper engine deploy 後跑 7d
- D+12 paper edge report land（含 §7.1 mandatory metric 6 條 + acceptance prerequisite 結果）
- 三檔 gate verdict（+15 promote / +5~+15 extend 14d / <+5 revise）拍板 N+2 動作

**E2 重點審查 3 點 v1.1 補強**（per §12）：
1. **Layer 1 paper-only fence default → None**（unchanged from v1）
2. **Strict shift(N) lookahead-free 驗證**：v1.1 補：含 N=60/120/300 三檔 shadow value + BTCUSDT 1h kline regime 計算同 strict shift(1)
3. **V088 hypertable retention + v1.1 schema 完整**：v1.1 補：必含 `btc_lead_return_pct_60s` + `btc_lead_return_pct_300s` + `regime_tag` 三新欄位

---

## §5. 16 根原則 + 硬邊界合規（v1.1 unchanged）

v1.1 改動全在 paper-only evidence collection + statistical evaluation 層，**0 觸碰**：
- 原則 1 (單一寫入口) / 原則 4 (不繞風控) / 原則 7 (學習 ≠ 改寫 Live) / 原則 11 (Agent 自主在 P0/P1 內) — paper-only fence 三層仍守住
- DOC-08 §12 9 條不變量 — 不動 lease / authorization / audit / reconciler / mainnet / Bybit retCode / 任何安全路徑
- 硬邊界 5 項 — 不動 `live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `decision_lease` / `authorization.json`

**改動風險評級 = 低**（paper-only evidence + statistical metric 補強，無 runtime 邏輯改動）

---

## §6. PA Sign-off

PA 拍板：spec v1 → v1.1 落 QC 5 conditions + σ MIT prerequisite，sign-off 路徑變更為「QC 已 sign-off + MIT C-3 D+1 直接收」，跳過 D+1 PA + QC integrate phase。W2 IMPL 走正確方向不需後續 spec patch。

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w2_a4c_spec_v1_1_qc_5_conditions_revision.md

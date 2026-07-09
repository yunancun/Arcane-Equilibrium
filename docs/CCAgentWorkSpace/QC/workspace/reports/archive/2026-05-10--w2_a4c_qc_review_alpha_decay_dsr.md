# QC C-2 Review — A4-C BTC→Alt Lead-Lag Spec

**日期**：2026-05-10
**性質**：Sprint N+1 W2 C-2 QC review 預跑（D+1 W2 三角 review 直接收）
**前置依據**：PA W2 A4-C spec `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` (HEAD `4bb5d485`)

---

## 判定：**CONDITIONAL APPROVE — 5 conditions**

spec 黑名單未觸碰、alpha source 結構性合理、但 paper edge gate threshold + cohort sample power + alpha decay 實證都需 PA 補強再 sign-off。

## Q1. Alpha decay 半衰期 + 最佳 N 推薦

**文獻錨點**：Easley/López de Prado/O'Hara *Microstructure in the Age of Machine Learning* (2021) + Makarov & Schoar *Trading and Arbitrage in Cryptocurrency Markets* (JFE 2020) + Tauchen-style HF cross-asset transmission 估計：BTC → high-cap alt 的 informational lead 半衰期落在 **30-180 秒**，超過 5 min 後 R² 衰減至 0.02 以下（noise-dominated）。

| N | 預期 R² (forward 60s alt return) | 半衰期估計 | 風險 |
|---|---|---|---|
| 60s | 0.04-0.08 | ~45s | noise 大；單 BTC tick noise 主導 |
| **120s** | **0.06-0.10** | **~90s** | **折衷 sweet spot** |
| 300s | 0.02-0.04 | ~150s | trend-continuation 已被 arbitrage，predictive power 衰減 |

**推薦 N=120s（與 PA 預設一致）**。理由：half-life ≈ N → forward predictive 還在「half power」段，符合 trade-off。但**強制要求**：D+12 paper edge report 必含 R²(N=60/120/300) decay curve，若實測 N=120s R² < 0.04 → revise spec 改 N=60s 或 archive A4-C。

## Q2. DSR penalty K 量化

**重算**（Bailey-López de Prado DSR formula 中 best-of-K Sharpe expected max）：

- 舊 K=79 → mu_0 = √(2 ln 79) = **2.956**
- 新 K=95 (79 + 8 cohort × 2 strat = +16) → mu_0 = √(2 ln 95) = **3.018**
- Δmu_0 = **+0.062**（+2.1%）

**對既有 5 策略 cells 的 DSR PASS 影響**：log scale 下 multiple-testing penalty 對個別 cell DSR threshold 的 shift **可忽略**（< 1 σ 空間）。但 **PA spec §8.1 寫「K=6」是錯**：應為 active strategy×symbol cell 總數（K=95），不是策略 family 數（=6）。**Condition #1**：spec §8.1 文字必修為 K=95，並引 Bailey-López de Prado (2014) §4.2「DSR with multiple trial」。

**警報**：若 8 cohort × 2 strat 全 promote demo IMPL → K 會繼續膨脹至 ~111；future ADR 必須記錄 K 累積增長對 multiple-testing budget 的長期約束。

## Q3. Paper edge gate statistical power

**重算**：n=800 (8 symbol × 100 fills), assume avg_net=+5 bps, σ=30 bps:
- t-stat = 5 × √800 / 30 = **4.71**
- p-value (one-sided H0: μ ≤ 0) ≈ **1.24×10⁻⁶**
- power vs SR=0 ≈ **>0.99**

**警報 — 變異數假設不可信**：
- crypto microstructure σ=30 bps 是 **下界**；參考 EDGE-DIAG-1 demo σ ≈ 50-80 bps（含 fee + adverse selection）。**Condition #2**：σ=30 是 PA 假設未 verified；MIT C-3 必跑 BTCUSDT 1m forward-return realized σ 7d 經驗值，若 σ ≥ 60 bps → t-stat 跌至 2.36 (p ≈ 0.009)，power 邊緣可接受但 PSR(0) 須重算 (含 skew/kurt deflation)。
- **per-symbol n=100 在 SR=0.17 下 power ≈ 0.87**（marginal），8 symbol 合計 n=800 power 高，但**單 symbol promote 決策**會被 underpowered。

**Condition #3**：D+12 evaluation 必同時報 (a) overall pooled t-stat（n=800），(b) per-symbol t-stat（n=100），（c）block-bootstrap 95% CI for both。Promote demo gate 加附 per-symbol n ≥ 100 + per-symbol t > 2.0（不只 overall）。

## Q4. Counterfactual backtest 設計

**Mandatory metric set**（D+12 paper edge report 必含）：

1. **Pooled + per-symbol** avg_net_bps + std + Sharpe + sample n
2. **DSR PASS** with K=95 deflate（**non-negotiable** — Q2 condition）
3. **PSR(0)** ≥ 0.95，用 skew/kurt-aware formula（crypto JB 必拒 normality；不能用 normal SR z-test）
4. **Alpha decay regime test**：lead signal predictive R²(N=60/120/300) 隨 7d window rolling 30-min bucket 的衰減曲線（Q1 condition）
5. **Block-bootstrap CI**（block size = 60 min 對齊 BTC autocorr scale，1000 iter）
6. **Per-cohort-symbol counterfactual delta**：`(if-followed-lead net_edge) − (TA1m baseline net_edge)`

**leak-free shift(N) 對比**（**Condition #4**）：counterfactual backtest 必並列 strict `shift(N)` 版 vs naive `[t-N..t]` 版，差異 > 30% → spec 失敗（log 內含 current bar leak）。對照 `feedback_indicator_lookahead_bias.md` Donchian RETRACT 教訓。

## Q5. Paper edge gate threshold 拍板

**+5 bps 是否合理 — REJECT-AS-IS，提替代**：

對照 demo 環境成本基線（CLAUDE.md §三 cost_gate JS-demo `[40] avg_net = -17.82 → +8.75 bps after V083`，3C audit）：
- demo 5 策略當前 cost burden ≈ **15-20 bps round-trip**（fee + slippage + adverse selection）
- Live 環境降至 ≈ 8-12 bps（PostOnly maker rebate）

**+5 bps gross paper edge** 在 demo cost 下 → net **−10 to −15 bps** → 不可能 promote。

**替代提案 — 階梯 gate（Condition #5）**：
| Threshold | 動作 |
|---|---|
| paper avg_net_bps ≥ **+15 bps** | promote N+2 demo IMPL（fast track） |
| +5 ≤ paper avg_net_bps < +15 | extend paper window 至 14d，重評（marginal） |
| paper avg_net_bps < +5 | revise spec 或 archive |

**理由**：+5 bps 在 demo cost 下無 net edge survive；+15 bps 才在 demo 環境留 ~0 net edge buffer，promote 後 live 環境（cost 降至 8-12 bps）才有正 edge headroom。**請 PM 在 dispatch v3.4 把 §8.1 gate threshold 改為三檔**。

## Q6. 風險評估 + Mitigation

| 風險 | QC 評估 | Mitigation |
|---|---|---|
| **self-fulfilling bias** | 低（5 策略 paper engine 流量極小，無法移動 BTC global liquidity）| PA 已 §9 處理 |
| **alpha decay quick (half-life < N)** | **中-高** | Q1 強制 R²(N) decay curve；半衰期 < 60s → archive |
| **BTC pump 時 lead signal saturate** | **中** | xcorr threshold_Y ≥ 0.40 + return threshold_X clamp ≤ 50 bps（避 outlier 主導）；新 condition：BTCUSDT 1h |return| > 200 bps 視為 regime extreme，shadow log 標 `regime=extreme` 不計入 7d edge avg |
| **σ=30 bps 假設過度樂觀** | **高** | Q3 Condition #2 — MIT C-3 verify |
| **per-symbol n=100 underpowered** | **中** | Q3 Condition #3 — per-symbol gate |
| **K=95 deflate 漏算** | **中** | Q2 Condition #1 — spec §8.1 文字修正 |
| **leak-free 含 current bar** | **極高** | Q4 Condition #4 + MIT C-3 strict shift grep |
| **+5 bps gate 太鬆無法 survive demo cost** | **極高** | Q5 Condition #5 — 階梯 gate |

## W2 Dispatch v3.4 Update 建議

**5 條 sub-agent IMPL 前必落地的 spec 修正**：

1. **§8.1 K 修正為 95**（不是 6），引 Bailey-López de Prado 2014
2. **§8.1 gate threshold 改三檔**（+15 promote / +5~+15 extend 14d / <+5 revise）
3. **§3.1 N 鎖 120s 但 §7.1 evaluate 必含 R²(N=60/120/300) 三檔 decay curve**
4. **§7.1 mandatory metric set 加 per-symbol breakdown + block-bootstrap CI + DSR with K=95**
5. **§9 加 BTC regime extreme guard（|1h return| > 200 bps shadow-only）**

無黑名單觸碰（無 HMM / GARCH / VPIN / Donchian rolling-max-含 current bar），alpha source 屬類別 7（跨資產溢出）+ 類別 4（資訊不對稱），有結構性根據。Spec 整體骨架健康，5 條 condition 修補後即可進 paper IMPL。

---

**Reference**:
- W2 spec: `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`
- DSR baseline: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-09--db_ml_verification_v3.md` (K=79)
- demo cost burden: `CLAUDE.md §三 [40] realized edge 7d audit`
- leak-free 反模式: `~/.claude/projects/.../memory/feedback_indicator_lookahead_bias.md`

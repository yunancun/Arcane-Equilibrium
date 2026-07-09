# QC 對抗性核實報告 v3 — 5 commits + PA redesign cross-check · 2026-05-09

baseline `faf2d131..da2aba11`（5 commits）。對應 v2 audit 11/20 修復率。

**Tally：✅ 3 / ⚠️ 2 / ❌ 0 / 🆕 4 · PA redesign verdict: PARTIAL · 5 策略 7d gross delta: ≈0**

## §1 Executive Summary

5 commits 是真工程，**但只覆蓋 v2 push back 中 hygiene 部分，未動 alpha source 或 architectural root cause**。修復率 3/5 全達成 + 2/5 partial。但**單顆 commit 邊際 alpha 影響為 0**：
- ad14db07 是 measurement bias 修，**不是 edge 修**（leak-free shift(1) 已在 indicator engine 用 `donchian_prior`）
- c2ab7b1a 教 strategist wide adjustment 但 cap=0.50 三環境統一違反 live fail-closed
- 48227607 promotion evidence push 鏈完整 wire + DSR/PBO trial_sharpes 持久化機制真實
- c081029d freeze blocked symbols 是治理 + counterfactual 真跑（17+4 cells freeze）
- da2aba11 F-08 cron 修了 scope mismatch 但 cron 仍未 install

**5 策略 7d gross delta**：sub-agent 不能 ssh trade-core；引用 §三 [40] 2026-05-09：demo avg_net=-17.82bps 維持，這 5 commits **0 個直接動 alpha**。

**PA redesign verdict**：**PARTIAL AGREE** — 架構診斷正確，但 alpha source 之 1 個（**basis_curve**）在 Bybit demo 無法 incubate（同 ADR-0018 funding_arb 退役限制）。R-1 R-2 R-3 排序正確但 sprint estimate 6-8 sprint 樂觀。

## §2 5 Commits 對抗性核實

| # | Commit | 實況 | QC verdict |
|---|---|---|---|
| 1 | ad14db07 | `IndicatorSnapshot.donchian = donchian_prior(...)` 已 leak-free；bb_breakout `&ind.donchian` 自動拿 leak-free 版本；`donchian()` legacy 函數仍存在但 indicator engine 已不用 | ✅ **REAL FIX** — 但是 hygiene fix（measurement bias），不是 alpha fix |
| 2 | c2ab7b1a | `evaluate.rs:416 wide_parameter_adjustment` 注入 LLM eval payload；strategist_skill normal=0.30 / max=0.50；真實閥門是 `validate_recommendation()` cap，**三 RiskConfig.toml 全部 max_param_delta_pct=0.50** | ⚠️ **PARTIAL** — LLM 真學了 hint ✅；**但 Live env 也是 ±50% cap = 違反 `feedback_demo_loose_live_strict_policy.md` 政策** |
| 3 | 48227607 | edge_estimator_scheduler.py:600 _run_promotion_evidence_push() 接 demo-only gate；trial_sharpes 真持久化（Per-symbol Sharpe）；fail-open + DB persistence | ✅ **REAL FIX** — v2 NEW-ISSUE-1 + push back 6.1(c) 完全解決 |
| 4 | c081029d | strategy_blocked_symbols_freeze.json 17 grid + 4 ma cells frozen；blocked_symbols_7d_counterfactual.py 跑 7d 真讀 trading.fills | ✅ **REAL FIX (治標)** — selection bias 進一步擴張被擋；**但治本要 dynamic_block_threshold + 自動冷卻復活**未做；17 個已 blocked symbol 多數 0 fills 0 rejected_outcomes = 「無 counterfactual power」 |
| 5 | da2aba11 | ml_training_maintenance.py CORE_JOBS (5 ops) + AUDIT_JOBS (5 thompson/optuna/cpcv/dl3/weekly) 合併為 10 jobs；real paths 接到 4 個 learning 表 | ⚠️ **PARTIAL** — source scope mismatch 修了 ✅；**但 Runtime impact still requires operator-authorized crontab installation** |

## §3 PA redesign cross-check（QC alpha 視角）

### 3.1 PA 5 root cause 評估

| # | PA 診斷 | QC verdict |
|---|---|---|
| 1 | Strategy Interface 結構性偏差 | ✅ AGREE — 5 策略都吃 IndicatorSnapshot 13 個 TA 指標 |
| 2 | Strategist scope = 「調參器」 | ✅ AGREE — `_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded weight |
| 3 | Analyst L2-L5 100% dormant | ✅ AGREE — ADR-0020 永久標 Layer 2 manual+supervisor-only |
| 4 | ML attribution_chain 0.5% 死 | ✅ AGREE（但治標）— 即使 attribution 100%，5 TA 策略 alpha 仍為 0 |
| 5 | 風控側鐵血 vs alpha 側放羊 | ✅ AGREE — 5 層 SM-04 + 4 risk_config TOML + Guardian + Cost Gate vs 1 Strategist + Ollama |

### 3.2 PA Alpha Surface Bundle 5 sources feasibility

| Alpha Source | Bybit demo 可行嗎？ | 半衰期 | QC verdict |
|---|---|---|---|
| **funding_curve** (cross-section) | ✅ Bybit perp WS tickers.fundingRate | ~1-7d | ✅ FEASIBLE |
| **basis_curve** (perp - spot) | ❌ Bybit demo 無 spot lending（同 ADR-0018）| ~7-30d | ❌ INFEASIBLE on demo |
| **oi_delta_panel** | ✅ Bybit v5 /v5/market/open-interest | ~1-7d | ✅ FEASIBLE |
| **orderflow_features** | ⚠️ demo private WS only；microprice 需 mainnet L2 | <1d | ⚠️ FEASIBLE on mainnet, 半衰期短 |
| **liquidation_pulse** | ✅ Bybit WS allLiquidation public stream | ~1-30min | ⚠️ FEASIBLE 但 1m sampling 抓不到 cascade window |

**PA 5 alpha sources 中**：2 個真結構性可行 + 1 個 demo 不可行 + 2 個半衰期 mismatch。

**對 R-1 評估**：alpha source registry 應前置 capability check（demo/live env × spot/derivatives / latency requirements）以免重蹈 funding_arb 覆轍。

### 3.3 PA「architectural failure」對 alpha 衰退理論評估

5 策略對應 published anomalies：grid（短期均回）/ ma（動量）/ bb_breakout（突破）/ bb_reversion（短期均回）/ funding_arb（結構性，已退）。

按 McLean-Pontiff (2016) post-publication decay 50%+ + crypto 24/7 efficient pricing 加速 → **gross-negative 是 statistical inevitability**。**修參數無法挽救已被 arbitrage 掉的 alpha**。

### 3.4 R-1 + R-2 + R-3 sprint estimate

PA 估 6-8 sprint **過樂觀**：
- R-1 5 alpha source IMPL + 25 symbol cross-section data plane + 5 既存策略 migration ≈ 5-7 sprint
- R-2 AlphaSourceRegistry + Strategist rewrite ≈ 3-4 sprint
- R-3 Hypothesis state machine + Analyst L3 rewrite + ML attribution refactor ≈ 4-6 sprint
- **合計實際 12-17 sprint**（未含 R-4 R-5）

## §4 NEW-ISSUE v3

### 🆕 NEW-ISSUE-V3-1 (HIGH)：Live env max_param_delta_pct=0.50 違反 fail-closed 政策

W-AUDIT-7 F-strategist-cap **三環境統一**升級 = risk_config_{paper,demo,live}.toml 全部 0.50。memory `feedback_demo_loose_live_strict_policy.md`「Live 永遠 fail-closed」+ `feedback_env_config_independence.md`「三環境風控 config 故意分開禁純衛生合併」明示禁此模式。

**建議**：`risk_config_live.toml max_param_delta_pct = 0.20`（或 0.10），paper/demo 維持 0.50。

### 🆕 NEW-ISSUE-V3-2 (MEDIUM)：DSR/PBO「per-symbol Sharpe as trial」非典範

`promotion_evidence.py:161 trial_sharpes = (candidate.sharpe for ... per-symbol)` 把「同 strategy 跑 25 symbol = 25 trials」當 PBO multiple-testing。但 PBO 嚴格定義是「N 個 strategy variant in K-fold time-split swap」，**不是「同 strategy 不同 symbol」**。

**影響**：對「strategy 是否真有 alpha」是合理測試；但對「我從 100 個 strategy variant 挑這個是不是過擬合」**沒有回答**。

**建議**：(a) 重命名為 `cross_section_sharpes`；(b) 真正 PBO 等待 R-3 hypothesis pipeline IMPL。

### 🆕 NEW-ISSUE-V3-3 (HIGH)：`donchian()` legacy 函數仍 export

`indicators/mod.rs:39 pub use trend::{donchian, donchian_prior, ...}`。`donchian()` legacy 仍 public API，新策略可能誤 import。

**建議**：(a) `donchian()` 改 `pub(crate)` 或加 `#[deprecated]`；(b) lint test。

### 🆕 NEW-ISSUE-V3-4 (MEDIUM)：blocked_symbols freeze 完成但「dormant cell 永久不可復活」缺機制

counterfactual 報告自承「current rejected blocked_symbols rows have decision_outcomes=0, so the system cannot yet claim true future counterfactual PnL」— **17+4 cells 進入永久 dormant**。

**建議**：補 `dynamic_unblock_check`：每 30d 對 blocked symbols 跑 V050 calibrated_replay counterfactual，positive edge 證據可解封。

## §5 對抗性 Push Back

### 5.1 5 commits 「修了 v2 4 個 high-priority」是真，但都是 hygiene 不是 alpha
v2 4 個 highest priority 全達成 ✅；**但 5 commits 0 個動 alpha 來源**。預期 7d gross delta ≈ 0。

### 5.2 PA report 「先修完 88 不會盈利」是對的，但「R-1 R-2 R-3 6-8 sprint」樂觀
QC 估算實際 12-17 sprint。**operator 應預期 architectural redesign 帶來 alpha 的 ETA 是 3-4 個月而非 1-2 月**。

### 5.3 PA「Strategist redefine」需先解決 Layer 2 dormant 死結
ADR-0020 永久標 Layer 2 manual+supervisor-only — 即使 PA Strategist redefine 完成，**alpha-source proposal 仍需人工 supervisor 批每一條**。alpha source registry 滿載時間從 6-12 個月延長到 2-5 年。

**建議**：PA R-2 補 `Layer 2 supervised-batch mode`：把 hypothesis batch 化（每週 supervisor review 5-10 個）而非 per-hypothesis approval。

### 5.4 funding_arb ADR-0018 RETIRE + PA「funding skew」存在內在張力
- ADR-0018 funding_arb = cash-and-carry（spot + perp 兩腿，demo 不可行）
- PA funding_curve = perp-only directional bet on funding mean-reversion（demo 可行）

**建議**：PA report §3.1 加 disclaimer 防誤讀。

### 5.5 5 策略 architectural failure verdict 與 W-AUDIT-6「修 5 策略」是對立目標
**operator 應決策**：W-AUDIT-6 是「最小化收尾」而非「全力修 5 策略」。5 策略只 keep core hygiene + retire 計畫。

## §6 5 策略 verdict 拍板狀態（v3 update）

| 策略 | v3 5-commit 後 | 實際生效 |
|---|---|---|
| grid_trading | freeze + counterfactual ✅ | ⚠️ 仍對非 blocked 全部開倉，**未限 ORDIUSDT-only**；blocked freeze 防擴大但 17 cell 永久 dormant |
| ma_crossover | unchanged | W/L 不對稱實證仍待 7-14d demo 觀察 |
| funding_arb | unchanged | dormant by design |
| bb_breakout | leak-free 已在 IndicatorEngine 用 donchian_prior ✅ | 5m demo active=true 現在**安全於 leak-bias 條件下**；W-AUDIT-6 收口可推進 |
| bb_reversion | unchanged | ❌ **仍 outstanding gap** |

`P0-DECISION-AUDIT-4` 距離 PENDING-OPERATOR → CLOSED 又進一步：**bb_breakout Donchian leak-bias 已修**。剩 bb_reversion outstanding。

## §7 結論 + 建議

5 commits 是真實 hygiene wave。**3/5 ✅ + 2/5 ⚠️ + 0/5 ❌ + 4 NEW-ISSUE**。

**PA redesign verdict：PARTIAL AGREE**：
- 5 root cause 診斷 100% 對 ✅
- Alpha Surface 5 sources 中 3 真可行 + 1 demo 不可行 + 1 半衰期 mismatch
- R-1 R-2 R-3 排序對但 sprint estimate 樂觀 2x（12-17 sprint 而非 6-8）
- Layer 2 dormant 死結未解 = alpha-discovery cadence 仍 10x 慢

**最高優先（不需 operator 拍板）**：
1. **NEW-ISSUE-V3-1 HIGH**：risk_config_live.toml max_param_delta_pct = 0.20（從 0.50 降）
2. **NEW-ISSUE-V3-3 HIGH**：donchian() legacy export 加 #[deprecated] + lint test
3. **NEW-ISSUE-V3-4 MEDIUM**：補 dynamic_unblock_check 30d cycle
4. **NEW-ISSUE-V3-2 MEDIUM**：rename trial_sharpes → cross_section_sharpes

**需 operator 拍板**：
5. **PA redesign R-1 R-2 R-3 是否啟動**（QC endorse + 並行 W-AUDIT-2/-5；接受 sprint 12-17）
6. **W-AUDIT-6「修 5 策略」最小化收尾 vs 全力修**（QC endorse 最小化收尾）
7. **Layer 2 ADR-0020 是否補 supervised-batch mode**（QC 建議是）
8. **bb_reversion outstanding verdict**（v1/v2/v3 連續 3 audit 未動）

**真實 gross 轉正 ETA**：3-4 個月（PA R-1 R-2 R-3 落地後）。

---

**QC VERIFICATION v3 DONE** · ✅ 3 / ⚠️ 2 / ❌ 0 / 🆕 4 · PA redesign verdict: PARTIAL · 5 策略 demo avg_net=-17.82bps 維持

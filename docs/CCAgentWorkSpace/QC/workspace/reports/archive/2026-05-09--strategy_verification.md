# QC 對抗性核實報告 — 2026-05-09 strategy verification

對應 audit baseline `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-08--strategy_risk_math_audit.md`
基準範圍：`72f05aa0..7fccad06` (28 commits)

**Tally：✅ 0 / ⚠️ 1 / ❌ 19 / 🆕 3**

## §1 Executive Summary

**核實判定**：20 量化問題 24h 修復率 = **0/20 = 0%**。`b91487f2` 與 `2567b973` 兩個 commit **與 QC 5/8 audit 的 20 量化問題完全無關**：前者是 scanner would-block evidence advisory（`[41]` healthcheck 改 WARN 不再 hard FAIL）；後者是 V072 feature_baselines contract guard（W-AUDIT-4 範圍，鎖死 34-dim 對 17-dim 不可混用）。**QC P0/P1/P2 量化發現一條都沒進入 IMPL**。

**根因**：W-AUDIT-6 全部排在 `P0-DECISION-AUDIT-4`「5 策略 verdict」operator 拍板之後（TODO.md L131 + L222），而該決策仍 `PENDING-OPERATOR` 未拍板。系統在等 operator 拿主意，IMPL 隊列被鎖在門前，並非工程怠工。

**5 策略 7d gross**（PA 5/8 PG 直查，§2 fix plan K-5 L82 引用）：
- demo: **-26.44 USDT**（funding_arb 殘倉 -15.43 / grid -11.15 / ma +0.20 / bb -0.06）
- live_demo: **+0.43 USDT**（grid -0.95 / ma +1.38 / bb 0）
- **合計 ~-26 USDT**，與 QC 5/8 audit -26.80 一致，**仍 net negative**

**DSR/PBO promotion gate 接線狀態**：**dormant**。`learning_engine/{dsr_gate,pbo_gate}.py` module 存在，但 grep 全 srv 確認 **0 個 production caller**，唯一 import 來自自家 tests。`promotion_pipeline.py` 內部 `DEMO_GRADUATION_GATES` 只有 sharpe ≥ 0.8 / drawdown ≤ 8% / API reliability ≥ 0.95，**沒有 DSR/PBO/CPCV blocker**。

## §2 20 量化問題逐條核實

| # | 嚴重度 | 問題 | 24h 修復狀態 | 對抗性證據 |
|---|---|---|---|---|
| 1 | 🔴 P0 | DSR/PBO/CPCV advisory only | ❌ NOT FIXED | learning_engine/{dsr_gate,pbo_gate}.py 存在但 0 production caller；promotion_pipeline.py grep 'DSR\|PSR\|PBO' = 0 命中 |
| 2 | 🔴 P0 | per_trade_risk_pct 雙 SSOT | ❌ NOT FIXED | kelly_sizer.rs:109 risk_pct: 0.03 仍 hardcoded default |
| 3 | 🔴 P0 | bb_breakout 1m + Donchian look-ahead | ❌ NOT FIXED | TOML 未禁用、未升 5m；無 5m 檔案；docs grep「5m bb_breakout RFC」0 命中 |
| 4 | 🔴 P0 | funding_arb dormant slot 未完全移除 | ❌ NOT FIXED | 4 個 TOML 仍含 [per_strategy.funding_arb] schema 段，僅 enabled = false |
| 5 | 🟠 P1 | grid_trading OU σ biased high | ❌ NOT FIXED | 無 OuResidualSigma Phase B wire commit |
| 6 | 🟠 P1 | bb_breakout cooldown 600k vs 300k | ❌ NOT FIXED | bb_breakout/mod.rs:192-193 cooldown=600_000 vs params.rs:257 cooldown_ms=300_000 仍分歧 |
| 7 | 🟠 P1 | Kelly tier 8/6/4 hardcoded | ❌ NOT FIXED | kelly_sizer.rs:198-204 三個分母仍 magic literal；TOML [kelly] 段只有 young_threshold/mature_threshold，**無 fraction config** |
| 8 | 🟠 P1 | fast_track 15%/5%+3σ hardcoded | ❌ NOT FIXED | fast_track.rs:74/89/135/141 全部仍 literal |
| 9 | 🟠 P1 | grid blocked_symbols selection bias | ⚠️ **WORSENED** | 5/8 P1-EDGE-1 commit 又**追加** LABUSDT 到 ma_crossover blocked_symbols（4 TOML 同步）— selection bias 持續加劇而非 freeze |
| 10 | 🟠 P1 | ma_crossover R:R 結構不對稱 | ❌ NOT FIXED | TOML [per_strategy.ma_crossover] 4 個 SL/TP override 全注釋；trailing/take_profit 公式無 commit |
| 11 | 🟠 P1 | 無 production VaR/CVaR/EVT | ❌ NOT FIXED | regime_controller.py 唯一檔案但只是 Kupiec POF 框架不是 production VaR backtest；W-AUDIT-6c 排 P2 backlog |
| 12-18 | 🟡 P2 | block bootstrap / plateau / min_trades / bb_reversion / stress test / Effective N / grand_mean | ❌ NOT FIXED | 全無 commit |
| 19-20 | 🟢 P3 | OI signal noise / cost_floor 不對稱 | ❌ NOT FIXED | — |

**統計**：✅ 0 / ⚠️ 1（worsened）/ ❌ 19 / 🆕 0

## §3 5 策略 verdict 拍板狀態

| 策略 | QC 5/8 verdict | TODO.md 狀態 | TOML 對應 | 實際生效 |
|---|---|---|---|---|
| grid_trading | CONDITIONAL（限 ORDIUSDT） | PENDING-OPERATOR | [per_strategy.grid_trading] 段缺，所有 25 symbol 仍可開倉 | ❌ 無 ORDIUSDT-only 限制 |
| ma_crossover | REVISE（R:R 重寫） | PENDING-OPERATOR | enabled=true；blocked_symbols 加 LABUSDT；R:R override 全注釋 | ❌ 沿用負 Kelly 形態 |
| funding_arb | RETIRE（schema 全清） | PENDING-OPERATOR | enabled=false 但 schema 段全保留 | ⚠️ 半 RETIRE |
| bb_breakout | REJECT 1m → REVISE 5m | PENDING-OPERATOR | TOML 無禁用、無 5m migration；mod.rs 仍 1m kline | ❌ 1m 仍 active |
| bb_reversion | REJECT 單獨 / pair 配 ma | PENDING-OPERATOR | 無 RETIRE / 無 pair config | ❌ 沿用 |

`P0-DECISION-AUDIT-4` 仍 `PENDING-OPERATOR`。Operator 至 5/9 為止未拍板。W-AUDIT-6 整套 IMPL 全卡。

## §4 NEW-ISSUE

### 🆕 NEW-ISSUE-1 (HIGH)：grid blocked_symbols selection bias 加劇而非凍結

5/8 P1-EDGE-1 commit 加 LABUSDT 到 blocked_symbols（4 TOML 同步）。QC 5/8 audit §2.1 已點名這是 selection bias，但 24h 內**持續加劇**。建議：(1) 凍結當前 blocked_symbols 列表，新加入需走 RFC + DSR/PBO 計算；(2) blocked_symbols 改寫為 dynamic_block_threshold + 顯式 freeze 時點；(3) 計算 4 個 blocked symbol 「未來 7d 真實 PnL」做 counterfactual。

### 🆕 NEW-ISSUE-2 (MEDIUM)：QC 5/8 funding_arb -5.96 vs PA 直查 -15.43 不一致

差 ~9.47 USDT。可能 QC 取 close_fills，PA 取 fills 全集。**這個差距足以改變「funding_arb dormant slot 是否有歷史殘差繼續流失」的判斷**。建議下次 audit 強制定義「PnL 計算的 SQL canonical query」並落入 `helper_scripts/db/audit/canonical_pnl.sql`。

### 🆕 NEW-ISSUE-3 (LOW)：promotion_pipeline.py demo gate min_sharpe = 0.8 但無 PSR/DSR 校正

無 sample size N 要求 + 無 PSR/DSR deflate。當前 5 策略樣本 cell 平均 n=8.9，在 N<30 場景下可被白噪音穿越。建議至少加 `min_trades_for_sharpe = 30`。

## §5 對抗性 Push Back

### 5.1 工作流綑綁設計反 push

`P0-DECISION-AUDIT-4` 排 W-AUDIT-6 全 IMPL 上游，但 5 策略 verdict 是 7-option matrix，operator 在缺乏「DSR/PBO 真實計算 + 5 策略各自 walk-forward OOS Sharpe」的證據下難以拍板。**形成循環依賴**：DSR/PBO 必須 IMPL 才能算出真值，但 IMPL 又被「等 operator 拍板」鎖住。

**建議**：把 W-AUDIT-6 拆兩半：
- **6A（前置基礎設施）**：DSR/PBO/CPCV 計算 module + Kelly tier config + 跑 5 策略 DSR 報告 — 不影響 risk config 不影響開倉，純 advisory，**不需 operator 拍板**
- **6B（risk config 變更）**：bb_breakout 1m→5m / ma_crossover R:R / funding_arb schema 完全清 — 才需要 operator 拍板

### 5.2 funding_arb 「半 RETIRE」push

funding_arb enabled=false 但 schema 段全保留 4 TOML，且 demo 還保留 `stop_loss_max_pct_override = 3.0`。dormant slot anti-pattern：(1) hot-reload 誤觸 enabled=true → 立即激活 + 3% SL override；(2) schema 存在 = 將來誤以為「待重啟動」；(3) 5/8 PA 直查 funding_arb 7d 仍 -15.43 USDT，殘倉/wind-down 還在虧。**1h 工作量，不需 operator 拍板（enabled=false 已是事實）**。

### 5.3 §三 「-26.44」無 healthcheck id push

CLAUDE.md §三 L83 採納 PA 5/8 -26.44 USDT 但**沒有對應的 healthcheck id**，違反 CLAUDE.md §七 自家規則。建議掛 `[40]` realized edge healthcheck，每 24h 自動重算。

### 5.4 grid_trading「唯一正 cell」push

QC 5/8 §2.1 給 grid CONDITIONAL，因 7d demo +4.98 USDT。但 PA 5/8 直查 grid 7d demo **-11.15 USDT** + live_demo **-0.95 USDT**，淨 -12.10。可能 QC +4.98 取 ORDIUSDT only cell；PA 取整 grid_trading 全 25 symbol。`[per_strategy.grid_trading]` TOML 段不存在，runtime 仍對所有非 blocked symbol 開倉。**QC 5/8 CONDITIONAL 在當前 runtime 下實質為 REJECT**。

### 5.5 「DSR/PBO module 已落地 = audit pass」push

QC 5/8 audit §6 把 DSR/PBO/CPCV 標 ✅ Implemented，但同表 Gap 1 寫「全是 advisory，未進 production blocker」。**「Implemented」與「Wired」是兩個概念**。當前 DSR=0.99 與 DSR=0.02 對任何策略 promotion 結果無影響。對 operator 而言這是 **fake-positive 治理**。建議下次 audit 把「Implemented」/「Wired」/「Production-Blocker」三層區分。

## §6 結論

24h 內 0/20 量化問題 IMPL，根因不是工程怠工，而是工作流綑綁設計 + operator 決策延遲。最高優先動作（不需 operator 拍板，可立即派）：

1. **funding_arb schema 4 TOML 完全清除** — 1h
2. **Kelly tier 8/6/4 → RiskConfig.kelly.{young/mature/established}_fraction**（W-AUDIT-6 stand-alone，不依賴 5 策略 verdict）— 3h
3. **bb_breakout cooldown 600k vs 300k 統一**（trivial fix）— 0.3h
4. **DSR/PBO production caller 加進 promotion_pipeline.py demo gate**（advisory 模式）— 8h
5. **CLAUDE.md §三 -26.44 加掛 healthcheck id** — 0.5h

需 operator 拍板才動的：5 策略 verdict 採納 / VaR/CVaR/EVT 是否啟動。

---

**QC VERIFICATION DONE** · ✅ 0 / ⚠️ 1 / ❌ 19 / 🆕 3 · 5 策略 7d gross: demo -26.44 / live_demo +0.43 · DSR/PBO promotion gate: dormant

# QC 全倉數學審計 — srv/ full repo · 2026-07-03

Bound role: QC（外部量化顧問）。Mode: READ-ONLY（僅本報告 + memory 落盤；Linux 證據僅 ssh trade-core 唯讀）。
Baseline: 本地 HEAD `d68a13298`；runtime 證據時戳 2026-07-03（edge_estimates mtime 10:43:52Z）。
範圍：rust engine / control_api / GUI(API 語意層) / helper_scripts / settings TOML / .claude skills / 治理文檔，QC lens（策略數學、風控統計、回測方法論、gate 雙向體檢）。

## 1. Executive Summary

判定：**FINDINGS（無 CRITICAL；2 HIGH、5 MEDIUM、5 LOW、3 INFO）**。

工程面數學品質相比 4-5 月大幅提升：前兩輪 QC audit 的 P0/P1（donchian look-ahead、OU σ 偏差、Kelly 硬編碼、fast_track/slippage/cost_gate 硬編碼、confluence DB-load guard、Sharpe 量綱）**已全部修復**，且 edge estimator 已內建 walk-forward + PSR/DSR/bootstrap 驗證 gate。系統對「當前無已驗證 edge」的自我報告是誠實的（113 real cells、0 過驗證、101/113 EV 為負、median n=6）。

本輪兩個 HIGH 都在「進化回路」而非交易路徑：
1. **cost-gate 學習面 blocked-signal 反事實 markout 的樂觀成交假設**（以 signal price 全額成交 + 平價 4bps 成本），與同 cell 已實現 edge 直接矛盾（ATOMUSDT|Sell 反事實 +75bps cushion vs 實現 −16.8bps）——整條 false-negative 敘事的量化根基不保守。
2. **standing envelope refresh 死循環是教科書級負淨貢獻 gate**（v710-v738 拒真率 100%、保護價值≈0、demo soak 凍結 ≥5 天）——判準側已由 `d0eeafb41` 修復，TTL 側殘留。

## 2. 前輪 open findings 復核（結案表）

| 前輪 finding（2026-04-24 / 05-30） | 現狀 | 證據 |
|---|---|---|
| Donchian current-bar look-ahead（HIGH） | **FIXED** | `openclaw_core/src/indicators/trend.rs:184-228` `donchian_prior()` 排 current bar，舊函數 `#[deprecated]`；production 路徑 `indicators/mod.rs:152` 用 prior 版 |
| grid OU σ raw second-moment 偏差 | **FIXED** | `grid_helpers.rs:139-158` OLS 殘差 σ、dof=n−2（WP-03 QC P1 註記） |
| Kelly tier 50/200 與分母硬編碼 | **FIXED+超額** | `ml/kelly_sizer.rs` 全 config 化 + Wilson LB shrinkage（KELLY-SIG-1）+ 負 Kelly→0（FIX-27）+ R haircut |
| fast_track 15%/5%/3σ 硬編碼 | **FIXED** | `risk_config_demo.toml [fast_track]`（W-AUDIT-6） |
| SLIPPAGE_TIERS / cost_gate 1.3 硬編碼 | **FIXED** | `[slippage]` tiers + `cost_gate_safety_multiplier`（G7-07） |
| confluence weight-sum 僅 construction-time 驗證（P2） | **FIXED** | `strategy_params.rs:144-172` build 時 validate 失敗回退 default + warn |
| bb_breakout cooldown ctor/default 分歧 | **FIXED** | mod.rs:256 / params.rs:270 均 `DEFAULT_COOLDOWN_MS` |
| Guardian 裁決權重硬編碼 | **RESOLVED-BY-REFACTOR**（med conf） | 舊 leverage_ratio 評分碼已不存在；E-Merge-4 後 GuardianConfig 為 RiskConfig 純派生視圖（`pipeline_config.rs:86-95`） |
| ewma_vol `w[0]>0` guard 缺失（LOW） | **仍 OPEN** | 見 F9 |
| maker_rejection 常數硬編碼（P3） | **仍 OPEN** | 見 F10 |

## 3. HIGH findings

### F1 — blocked-signal 反事實 markout：fill-at-signal-price + 平價 4bps，成本假設非保守，且與實現 edge 矛盾
- 分類：FACT（機制）+ INFERENCE（影響）· severity HIGH · confidence high（機制）/ med（影響量級）
- 證據：
  - `helper_scripts/research/cost_gate_learning_lane/outcome_writer.py:275` entry = `event.entry_price or price or last_price`（被擋信號視為在 signal price 全額成交）；`:292-293` `gross = side_sign·(exit−entry)/entry·1e4; net = gross − cfg.cost_bps`；`:26` `cost_bps: float = 4.0`（≈ maker RT fee，無滑點/spread/adverse selection/funding）。
  - 無 fill-probability 模型。同期 touchability 審計（2026-06-24 QC audit）：33/33 reviewed PostOnly orders deep-passive-no-touch（gap 987-1821bps）——實際掛單根本不成交。
  - 交叉驗證（runtime `settings/edge_estimates.json`, 2026-07-03T10:43Z）：top false-negative `grid_trading::ATOMUSDT::Sell` 實現 EV **−16.76bps**（n=18, win_rate 5.6%）vs 反事實 cushion **+75.07bps**；現任 soak 候選 `grid_trading::ETHUSDT::Buy` 實現 EV **−9.21bps**（n=15, wr 20%）。兩 lane 同 cell 方向相反。
  - false-negative review（`outcome_review.py:222` cushion = avg_net − min_avg_net_bps）**不含**與 edge_estimates 實現 cell 的矛盾比對。
- 影響：整條 false-negative / sealed-horizon 敘事（16 候選、top cushion 75bps、sealed 31.87bps@240m）的量化根基違反 QC 硬約束 #4（滑點取上限、手續費不打折）。目前僅 review/proposal 無下單權（影響有界），但它決定 operator review 排序、bounded probe 候選選擇與未來 cost-gate 調整論證——樂觀方向的系統性偏差會把 probe 預算與 operator 注意力導向不可實現的 cell。
- 條件聲明：在「maker 成交、零 adverse selection、60m 固定 horizon、mid 出場」假設下 cushion 數字才成立；touchability 證據直接否定第一個假設。
- Fix 方向：(a) touch-based fill 模擬（沿用 2026-04-20 QC paper 協議：tick==limit 50% / 穿越 100%、queue 折扣）；(b) cost 模型分腿型（taker RT 11bps + [slippage] tier）雙列 optimistic/conservative；(c) false_negative packet 強制附同 cell realized EV 矛盾標記；(d) horizon > funding 結算週期時計 funding drag。
- defect_type: [replay-misuse, math-error, test-blindspot]；symbol_anchor: `ProbeOutcomeConfig.cost_bps`；root_anchor: `outcome_writer.py::_build_markout_outcome_records`

### F4 — standing envelope refresh 死循環：負淨貢獻 gate（判準側已修，TTL 側殘留）
- 分類：FACT（循環史）+ INFERENCE（殘留風險）· severity HIGH（evolution-blocker 計價）· confidence high
- 證據：
  - TODO.md v731-v738：exact-sha final source drift check 在 codex 高頻 commit 下拒真率 **100%**（v731 兩次 ROTATED；v733 三 head 過期；v738 `bfbbd343` v6 獲 E3/BB 雙批後仍因 `origin/main` 前進而 ROTATED）。v731 記錄 envelope 剩 `80.38s` 時到期。
  - runtime standing auth 2026-07-01T17:16:05Z 過期，至 v738（07-02T19:14Z）仍未刷新（>26h 無授權窗）；lane 歷史 `NO_PROBE_OUTCOMES_RECORDED`、strict scan 34,574 rows 零 candidate-matched fill——soak 候選凍結 ≥5 天。
  - 被 gate「保護」的下行本已被 envelope 自身鎖死：demo-only、≤2 probe orders、cap 954.19 USDT、SL 受 P1/P2 約束 → 避免虧損 ≈ 0；凍結成本 = operator 首要目標（demo 自主盈利迴路推進）的全部吞吐。淨貢獻顯著為負。
  - 修復：`d0eeafb41`（post-approval drift gate：docs/tests/.codex 豁免、EXEMPT 時從 approved-head clean detached worktree 執行）設計正確（執行錨定已批 head，後續 docs 變更不影響已批代碼路徑）。
- 殘留：TTL=12h（`standing_demo_loss_control_envelope_review.py:52` `DEFAULT_AUTHORIZATION_TTL_HOURS=12`）vs E3/BB exact-packet 週期（多小時-跨日）仍可能在批准中途過期（v731 實例）。v739 尚未實走驗證。
- Fix 方向：TTL ≥ 2× p95 refresh-cycle 時長（或 24h 上限內動態）；envelope 有效性錨定 candidate+cap+policy-hash 而非 wall-clock 短 TTL × source-HEAD 雙敏感；v739 實走後復核拒真率。
- defect_type: [over-gate, evolution-blocker]；symbol_anchor: `DEFAULT_AUTHORIZATION_TTL_HOURS`；root_anchor: `standing_envelope_post_approval_drift_gate.py`（已修側）

## 4. MEDIUM findings

### F2 — 學習面 best-of-K 選擇無多重比較控制
- FACT · MEDIUM · high conf。43 side-cells ×多 horizon（60/240m…）掃描後取 best（blocked_outcome_review top、sealed replay "best avg net 31.87bps / stability best 108.18bps"），sealed gate 僅點估計 floor（`horizon_specific_sealed_replay.py:211-300`：sample≥100、avg_net>floor、hit_rate>floor），無 K 記錄、無 BH-FDR/DSR。系統內已有先例可複用（`bb_breakout_threshold_sweep.py` 有 Bonferroni；edge_estimates validation 有 PSR/DSR）。影響：headline 數字上偏（E[max of K noisy cells] > 0 under null），operator review 排序被噪音污染。Fix：packet 記錄 K + expected-max-under-null 或對 cell 選擇跑 BH（FDR=0.10）+ 對 sealed avg 跑 DSR。
- defect_type: [test-blindspot, math-error]；symbol_anchor: `_wrongful_block_score` / `horizon_stability_scorecard`

### F3 — bounded probe 預算 n=2/cell：對 cushion 假設檢定功效 ≈ 8%
- INFERENCE · MEDIUM · high conf（數學）。`demo_learning_lane.rs:44` `min_failed_outcomes_to_disable=2`、per-cell `max_probe_orders=2`。在 σ≈200bps（1h markout, crypto）下檢出 Δ=75bps：n=2 → power ≈ Φ(75/(200/√2)−1.96) ≈ **7.6%**；80% power 需 n≈56。n=2 只能偵測「粗執行 realism 落差」（fill price vs 假設），不能確認/否證 cushion。若 lane 定位是統計驗證 → evidence ladder 結構性 stall（永遠 insufficient n）；若定位僅執行 realism 取樣 → 文檔應明示，避免把 2 筆 outcome 當 edge 證據。Fix：packet 內明示 power；或提高 per-cell 預算至 n≥30（單筆 cap 收緊對沖風險）。
- defect_type: [test-blindspot, evolution-blocker]；symbol_anchor: `AdmissionConfig.min_failed_outcomes_to_disable`

### F5 — per_trade_risk_pct 單位語意混雜 + 4 處 survival-floor 註解低估 5 倍
- FACT · MEDIUM · high conf。同一 `[limits]` 區塊內 `per_trade_risk_pct=0.1` 是 **fraction**（=10%，`risk_config.rs:432-437` 文檔 "0.03 = 3%"、validate 範圍 [0.001,0.20]），而 `position_size_max_pct=25.0` 是 **percent**。此混雜已造成：GUI「10 USDT vs 10%」saga（TODO v651+ 多輪修復）、memory 條目誤讀（0.05-0.20 被讀作 0.05%-0.20%）、以及 4 處 stale 註解把 survival floor 寫成 "per_trade_risk_pct(2%)" 而實際 demo=10%/live=5%：`risk_config.rs:495`、`flash_dip_buy/mod.rs:31`、`flash_dip_buy/params.rs:50`、`risk_config_demo.toml:48`。另 `fast_track.rs:78-80` 註解 "leverage_max=100, total_exposure=200" 與實際 demo 50/150、live 15/80 不符。影響：治理/E3/BB review 引用 survival floor 文字時低估實際單筆風險敞口 5 倍；agent 每輪讀改此檔都要重新考證單位（重複 token 稅）。Fix：註解全量更正 + 欄位文檔加單位表；長期改名 `per_trade_risk_frac`（breaking，需遷移 gate）。
- defect_type: [schema-issue, doc-stale, readability-debt]；symbol_anchor: `per_trade_risk_pct`

### F6 — dynamic_sizing band 與 per_trade_risk_pct 無交叉驗證：靜默 2 倍 sizing 不連續
- FACT（機制）/ INFERENCE（runtime 顯現）· MEDIUM · high/med conf。demo TOML `[dynamic_sizing] enabled=true, min_pct=0.01, max_pct=0.05` 而 `per_trade_risk_pct=0.1`。`DynamicRiskSizer::new` 把 base clamp 進 [0.01,0.05]（`dynamic_risk_sizer.rs:199`），但 `apply_risk_snapshot` 同時把未 clamp 的 0.1 推入 IntentProcessor（`pipeline_config.rs:76-84`）→ 暖機期 10%，累積 50 筆平倉後 sizer 發布 ≤5%，有效 P1 風險靜默腰斬且無 operator 決策點。反向結構風險：若 per_trade < min_pct，sizer 會把風險**抬高**到 min_pct 之上（fail-open 方向，當前值未觸發）。`RiskConfig::validate()` 僅各自驗證（`risk_config.rs:287`），無 `min_pct ≤ per_trade_risk_pct ≤ max_pct` 交叉檢查。Fix：validate() 加交叉檢查（enabled 時 reject 或 warn+clamp 記錄）；runtime 側查 sizer status 確認當前 current_pct。
- defect_type: [missing-gate, schema-issue, drift-source-runtime]；symbol_anchor: `dynamic_sizing.max_pct`；root_anchor: `pipeline_config.rs::apply_risk_snapshot`

### F7 — ADPE cost-viability 篩選 slippage=0.0：違反保守成本硬約束
- FACT · MEDIUM · high conf（機制）/ med（影響）。`settings/adaptive_demo_profit.toml:60-63` `edge_evidence_slippage = 0.0`（fee 0.00055 + safety 1.3 有，但滑點歸零）。該篩選決定 explore keepalive 的「cost-viable side edge」判定；零滑點使門檻鬆於 Rust cost gate 真實成本（demo 實測 risk-close taker slippage 有 −37bps 級樣本），explore 保活可能反覆保住會被 Rust cost gate 擋掉的 cell（正是該 config 註解自述要避免的迴圈）。demo explore-only、無下單權 → MEDIUM 下緣。Fix：改用 `[slippage]` tier 或 taker slippage 上分位。
- defect_type: [hardcoded-config, math-error]；symbol_anchor: `edge_evidence_slippage`

## 5. LOW / INFO findings

- **F8（LOW, FACT）** funding_harvest 年化寫死 8h×3×365（`funding_harvest/mod.rs:137-138` `funding_rate_8h * 3.0 * 365.0`），未讀 per-symbol `fundingInterval`。現 dormant + Stage1 BTCUSDT-only（8h）→ 良性；Stage 2+ 擴 symbol 時 APR 與攤銷分母可錯 2-8 倍。Fix：instruments-info fundingInterval 參數化。defect: [bybit-incompat, hardcoded-config]；anchor `annualized_funding`。
- **F9（LOW, FACT）** `openclaw_core/src/indicators/volatility.rs:278` ewma_vol log-return 無 `w[0]>0` guard（同檔 hurst :154 有 filter）。K 線 close 恆正下殘留風險極小；零成本補齊一致性。defect: [math-error]；anchor `ewma_vol`。
- **F10（LOW, FACT, 前輪 P3 延續）** `maker_rejection.rs:39-51` close-maker backoff/cascade 6 常數仍硬編碼（1s/60s/300s/10symbols/60s/300s），無 TOML/IPC 路徑。live 校準需重編譯。defect: [hardcoded-config]；anchor `CLOSE_MAKER_BACKOFF_INITIAL_MS`。
- **F11（LOW, FACT）** git 內 `settings/edge_estimates.json` 為 2026-04-20 化石（n_cells=1, grand_mean −45.73）而 runtime 同名檔 2026-07-03（221 keys, grand_mean −9.43）——runtime-mutated 資料檔入 git 造成 dev 側誤讀（2026-04-24 audit 即踩過）。Fix：改 fixture 標記（`_meta.source`）或退出版本控制、加 CI staleness 警示。defect: [drift-source-runtime, lineage-gap]；anchor `settings/edge_estimates.json`。
- **F12（INFO, FACT）** `false_negative_evidence_floor_ranking.py:282-304` `_rank_score` 混量綱加總（bps + (pct−50)/2 + log10(n)·5 + 1000/100/50/40 tier bonus − 0.01·rank）。Tier bonus 實質字典序，設計可接受，但常數敏感性未文檔化。defect: [readability-debt]。
- **F13（INFO, FACT low-conf 語意）** runtime edge_estimates `_meta.n_cells=45` vs 實際 221 keys（113 real + 108 proxy）——`n_cells` 語意（疑為過門檻 real cells）未在 meta 自述，下游讀 meta 者易誤判覆蓋率。defect: [schema-issue]。
- **F15（INFO, FACT — 系統態勢非缺陷）** edge 態勢：113 real cells 中 0 個 `validation_passed`（WF 90/30/30 + min_oos_n 30 + PSR/DSR/bootstrap gate）、101/113 EV<0、median n=6、正 EV cells 全部 n≤19。系統誠實自報「無已驗證 edge」；與 2026-06-13 搜索空間結論一致。樣本饑餓（median n=6 « 30）仍是 edge 統計的第一約束。

## 6. 黑名單體檢

無違規。HMM/GARCH/VPIN 僅以「禁用聲明」形式出現（`m4_miner/mod.rs:22`、`funding_short_v2/mod.rs:34`、`liquidation_cascade_fade/mod.rs:41` — ADR-0036 合規註記）。年化 ×365 紀律已測試固化（`test_multiday_trend_diagnostic.py:490`）。

## 7. 對抗性反問（自檢）

1. Q: F1 的矛盾會不會只是 horizon/exit-policy 差異（60m mid 出場 vs 真實策略 stop/fast_track 出場）而非成交假設？A: 兩者皆貢獻；但 touchability 33/33 no-touch 直接證明「掛單價不成交」，成交假設偏差是第一階項。exit-policy 差異是第二個（也應修：counterfactual 應模擬同款 exit 規則）。
2. Q: F4 severity 是否高估——demo 無真錢？A: 按 operator 裁決座標（over-gate 以被凍結進化價值計），demo 自主迴路是當前唯一 alpha 證據生產線，凍結 5 天 = 全吞吐損失，HIGH 成立；若按工程風險計則僅 MEDIUM。
3. Q: F6 若 sizer 從未累滿 50 筆平倉，是否無實際影響？A: 是——故 runtime 顯現標 INFERENCE/med；但 validate 缺口是 FACT，且 fail-open 反向（per_trade<min_pct 抬風險）結構存在。
4. Q: 樣本翻倍後 F1 矛盾會變強還是弱？A: 反事實 n 增大只會更精確地估計「不可實現的量」；矛盾不隨 n 消失，必須改機制。

## 8. 建議（PROCEED / REVISE / REJECT）

- 學習面（cost-gate lane）：**REVISE**（F1/F2/F3 為修復順序；F1 先行，改動小——outcome_writer 成本模型 + packet 矛盾標記）。
- envelope/refresh 治理：**PROCEED with v739 驗證**（d0eeafb41 方向正確）+ TTL 重設計（F4 殘留）。
- 風控 config 衛生：**REVISE**（F5 註解更正 + F6 交叉驗證，皆低成本）。
- 交易核心數學（indicators/Kelly/OU/cost gate/fast_track）：**PROCEED**——本輪未發現新的交易路徑數學缺陷。
- 翻案條件（對 F1 的 REJECT-of-evidence）：若 bounded probe 以修正後 touch-based 模型仍測得 cushion>0 且 n≥30 per cell、fill realism gap <20%，則 false-negative 敘事可恢復。

## 附錄 A — 復算記錄

| 項 | 報告值 | QC 復算 | 結論 |
|---|---|---|---|
| GUI P1 cap | 954.18759458 USDT | equity 9541.876×0.10=954.188 | 一致（fraction 語意確證） |
| probe power n=2 @Δ75bps σ200bps | 未報告 | ≈7.6%（Φ(0.53−1.96)） | F3 依據 |
| 80% power 所需 n | 未報告 | ((1.96+0.84)·200/75)²≈56 | F3 依據 |
| ATOM Sell cushion vs realized | +75.07bps / — | edge_estimates −16.76bps n=18 | F1 矛盾確證 |

## 附錄 B — 盲區（negative space，交 PA re-probe）

見 StructuredOutput assumptions；重點：Rust 端 counterfactual replay 生成器未溯源、PG 樣本層未重驗、mlde/claude_teacher applier 統計未深審、IBKR lane 未審、dynamic sizer runtime 實際 current_pct 未取數。

---
QC · 2026-07-03 · read-only audit（無代碼/config/runtime 變更）

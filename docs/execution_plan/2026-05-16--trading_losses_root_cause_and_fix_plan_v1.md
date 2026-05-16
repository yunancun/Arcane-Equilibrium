# Trading Losses — Root Cause + Complete Fix Plan v1

**Date**: 2026-05-16
**Scope**: 補存第三方 3-round audit 收斂後的完整修復方案（之前散在 chat + 多份 verdict，本檔整合為 single SoT）
**SoT cross-ref**: Round 1 archive `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md` / TODO §11.4 P0-MICRO-PROFIT / 3+4-agent verdicts under `docs/CCAgentWorkSpace/*/workspace/reports/2026-05-15--*`

---

## §1 經 3-round 第三方審核 + 主會話對抗收斂的事實

| 事實 | 數據 |
|---|---|
| 30d demo net | **-110.43 USDT**（5 textbook 策略合計）|
| 30d live_demo net | **-27.31 USDT** |
| demo grid 7d active taker close | 203 筆全 taker；distribution: grid_close_short 97 / phys_lock_gate4_giveback 49 / bb_mean_revert 21 / grid_close_long 17 / phys_lock Sell 12 / bb_mean_revert Sell 4 / 其他 3 |
| live_demo grid 7d active taker close | 155 筆，**100% 策略級**（grid_close_short 115 / bb_mean_revert 28 / grid_close_long 11 / ma_reverse_cross 1），**0 真風控** |
| entry maker | 已實裝（demo+live_demo 7d 100% maker，avg latency 5-14s, max 50s） |
| close path | `commands.rs:792-797` hard-coded `order_type:"market"` with comment「Close path stays Market (EDGE-P2-3 Phase 1a entry-only scope)」 |
| phys_lock_gate4 | profit-protection 4-gate（edge floor → hold age → peak ATR → giveback / stale ROC），非 §5.9 hard-stop（FA verified；exit_features/v2.rs:286-288 Lock decision）|
| phys_lock live 7d 0 fires | by design：`risk_config_live.toml` 無 `missing_edge_fallback_bps` override → Rust default -10.0 < floor 5.0 → Gate 1 永遠 Hold |
| Phase 1B-4.2 resting_orders.rs | paper-only，與 exchange close path 正交（**0 依賴**）|

### 第 1 審錯誤（已 archive）

1. 把 `side='Sell'` 當「賣出平倉」（perpetual 裡 Sell 也可開空 entry）
2. 「Grid 84% 平倉零 PnL」基於上述錯誤；真實 active taker close 中 zero_pnl = 3.6-6.3%
3. 「Grid 入場 82.7% taker」錯誤；真實 entry 100% maker（已實裝），close 100% taker
4. 「Grid step 22 bps 不夠」方向對，但 22 bps 已是 `min_grid_step_bps` + `cost_floor_multiplier=2x` 配置（per `strategy_params_demo.toml:120-121`）

### 第 2 審補正（採納）

- 用 `entry_context_id != ''` 識別 paired close；正確 30d net 計算
- spec §4.3 phys_lock TP/SL/trailing per-strategy override 已存在（`risk_config_demo.toml:62-68`）

### 第 3 審補正（部分採納）

- 確認 entry 已 maker，問題在 exit；但**仍誤判** schema：`entry_context_id IS NULL` 不是「entry」，是「passive maker fill」（grid level limit 成交，可開可平）；`linked taker = active close`
- bb_breakout +2.29 demo 30d 由 BILLUSDT 2 筆主導（n=27 樣本不足，不能對照）

### 主會話最終對抗結論（取代前三審）

- **Entry 100% maker 已生效**（`use_maker_entry=true` per 3 TOML；DB verify 100% maker fills）→ 「修 maker entry」是幻覺
- **真正 bleed 在 exit**：active close 100% taker。`live_demo grid 7d 100% close 是策略級（不是真風控）`
- **phys_lock 是 profit-protection 不是 risk control**（QC verified via v2.rs:286-288 Lock decision；不是 hard-stop）
- **bb_mean_revert 是 same-strategy exit**（per `cross_strategy_attribution_integrity.rs:13` post-Option-A-Lite filter，不是跨策略信號）

---

## §2 Root Cause 分層

per QC 2026-05-11 + 第三方審核 + 主會話對抗收斂：

| # | Root Cause | 占比估計 | 治理 lane |
|---|---|---|---|
| 1 | **Alpha 結構性缺失** — 5 textbook 策略 post-publication decay | **~60%** | W-AUDIT-8a/8b/8c/8d/8e/8f（多月）|
| 2 | **Account size × 0.1% TOML 物理上限** — $591 × 0.1% = $0.59/trade 設計上限 | ~20% | sizing config（待 alpha 轉正後動）|
| 3 | **Fee drag** — close path 100% taker + PostOnly missed-trade | **~10%** | **EDGE-P2-3 Phase 1b close-maker-first**（本輪重點）|
| 4 | **Signal target tight** — grid 22 bps / bb 1-2σ / ma sub-1ATR | ~5% | replay sweep（W-AUDIT-8a Phase B/C）|
| 5 | **Slippage + queue position adverse selection** | ~5% | execution-quality micro-optimization（W-AUDIT-8a Phase C/D microstructure）|

**判決**: **Phase 1b close-maker-first 對 root cause #3 治療（~10% 占比），不解 root cause #1（~60%）**。真實治癒 trading losses 必走 alpha source 軸 W-AUDIT-8a/8b/8c。

---

## §3 完整修復方案 P0/P1/P2

### P0（1-3 天）— Quick wins（已部分執行）

| 動作 | Owner | 狀態 | 對應實現 |
|---|---|---|---|
| MA KAMA fallback gate（debug! → warn! + skip entry）| E1 | ✅ DONE | commit `9df44183` + test `34aa7086` + E4 `b608faaf` |
| Maker fill rate empirical baseline 查 | PA | ✅ DONE | commit `b98706d5`：fee saving 4.5 → 0.5-2.0 bps net |
| F-FA-2 portfolio_var SoT verify | PA | ✅ DONE | commit `96995b61`：MAINTAIN（close path 不觸 portfolio gate）|
| F-FA-3 W-C Caveat 2 guard tests 設計 | PA | ✅ DONE | commit `a5a7107c` |

### P1（1-3 週）— Execution-quality 軸（Phase 1b）

| 動作 | Owner | 狀態 | 對應實現 |
|---|---|---|---|
| EDGE-P2-3 Phase 1b close-maker-first spec finalize | PA | ✅ DONE v1.3 | `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` |
| AMD-2026-05-15-02 land | PM/PA | ✅ DONE v0.4 | `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` |
| V094 hybrid schema migration spec | PA | ✅ DONE | `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` |
| reject_cooldown entry/close split | E1 | ✅ DONE | commit `27f02a07` + E4 `8321b4b7` |
| Phase 1b IMPL Worktree A（V094 SQL + writer payload）| Sibling E1 | ✅ DONE | dirty Rust + sibling self-report |
| Phase 1b IMPL Worktree C（dynamic backoff state machine）| Sibling E1 | ✅ DONE | dirty Rust + sibling self-report |
| Phase 1b IMPL Worktree D（healthcheck [62][63][64][65]）| Sibling E1 | ✅ DONE | dirty Python + sibling self-report |
| **Phase 1b IMPL Worktree B（close path classifier + compute_close_limit_price + dispatch wire）** | E1 | ❌ **MISSING - CRITICAL** | E2 RETURN per `2026-05-16--phase_1b_b2_b3_sibling_e2_review.md` |
| Phase 1b IMPL Worktree E（tests + integration）| Sibling E1 | 🟡 PARTIAL | included in A/C/D worktrees |
| P1-PORTFOLIO-RESTING-EXPOSURE-1（entry-side resting maker exposure fix）| E1 | ✅ DONE | commit `9980448a` + supplement test `ad5e609e` |
| 4-agent (QC+FA+BB+MIT) round 2 review on AMD v0.2 | 4 agents | ✅ DONE | reports `2026-05-15--amd_2026_05_15_02_4agent_review_*.md` |
| Wave 3a 4-agent short re-review on v0.3+v1.2 | 4 agents | ✅ DONE | reports `2026-05-15--amd_v0_3_spec_v1_2_*_short_re_review.md` |
| Wave 3b BB 字典手冊 6 處更新 | BB | ✅ DONE | commit `28c571c7` |
| Wave 3.5 Linux V091/V092/V093 backlog apply | operator + PM | ✅ DONE | per CLAUDE.md §三 line 70 v39 closure |
| E3 ML invariant grep guard rule | main session | ✅ DONE | commit `197ca14d` |
| MIT-AC-19 stratification healthcheck SQL | MIT | ✅ DONE plan | `2026-05-16--mit_ac_19_close_maker_stratification_plan.md` |
| phys_lock live enable AMD draft | PA | ✅ DONE v0.2 | `docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md` |
| 4-agent review on phys_lock AMD v0.1 | 4 agents | ✅ DONE | reports `2026-05-16--phys_lock_live_enable_amd_*_review.md` |
| AMD v0.1 → v0.2 23 items consolidated | PA | ✅ DONE | commit `6c589f2f` |
| **P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP**（spec §5.4 full dynamic backoff state machine）| E1 | ⏳ pending Phase 2a PASS | Phase 1b initial IMPL 取 per-symbol 5min fixed |
| **Edge estimator pipeline 修復** | PA/E1 | ⏳ pending | `learning.edge_estimate_snapshots` 2026-05-07 後 validation_passed=0；獨立 ticket 待開 |

### P2（1-3 月）— Alpha Source 軸（真治癒 root cause #1）

| 動作 | Owner | 狀態 | 對應實現 |
|---|---|---|---|
| **W-AUDIT-8b Funding Skew Directional**（A4-A）| PA → E1 | 🟡 Round 1 RED, spec v0.3 land, Round 2 ETA 2026-05-18 00:30 UTC | spec `2026-05-15--w_audit_8b_funding_skew_directional_spec.md` v0.3 |
| W-AUDIT-8a C1 Liquidation Topic Probe | operator | 🟡 v2 24h proof IN_FLIGHT PID 377531, ETA 2026-05-17T14:56:16Z | `helper_scripts/bybit/liquidation_topic_probe.py` |
| **W-AUDIT-8c Liquidation Cluster Reaction**（A4-B 新策略）| PA → E1 | ✅ spec done, ⏳ IMPL pending C1 PASS | `docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md` |
| W-AUDIT-8a Phase B/C/D Alpha Surface infrastructure | PA → E1 | ✅ spec done, ⏳ IMPL 4-6 sprint | `docs/execution_plan/2026-05-16--w_audit_8a_phase_b_c_d_infrastructure_spec.md` |
| W-AUDIT-8d BTC→Alt Lead-Lag（A4-C）| — | ⛔ **ARCHIVED 2026-05-15 no-revive** | per CLAUDE.md §三；same feature shape 禁 |
| W-AUDIT-8e Strategist Alpha Source Orchestrator（R-2）| PA → E1 | ⛔ DEFER Sprint N+4-N+5 | per TODO §4.1 row 19 |
| W-AUDIT-8f Hypothesis Pipeline + W-AUDIT-4 ML 併入（R-3）| PA → E1 | ⛔ DEFER Sprint N+5 | per TODO §4.1 row 20 |

### P3（多月）— Sizing + Live Promotion

| 動作 | 狀態 | 阻塞 |
|---|---|---|
| Account size × 0.1% TOML 上限 | ⏳ pending | 等 alpha 轉正後動 |
| Phase 2a Demo 14d observation | ⏳ pending | Phase 1b Worktree B 完成後啟動 |
| Phase 2b LiveDemo 7d observation | ⏳ pending | Phase 2a PASS 後 |
| Phase 3 Mainnet enable | ⏳ pending | operator + AMD live carve-out + 3-gate solve |
| phys_lock live enable | ⏳ pending | Phase 2b PASS + QC counterfactual + operator sign-off |
| W-AUDIT-8g Per-alpha-source Live Promotion Gate（R-4）| ⛔ DEFER Sprint N+7+ | per TODO §4.1 row 21 |

---

## §4 真實進度交叉表

### IMPL Prereq 6 條件（per AMD v0.4 §8）

| # | Condition | Status |
|---|---|---|
| 1 | PA spec finalize（v1.3）| ✅ |
| 2 | AMD v0.4 + spec v1.3 4-agent re-review | ✅ |
| 3 | 三閘（P0-EDGE-1 / W-AUDIT-8b Stage 0R / W-AUDIT-8a C1）| ❌ **PENDING（外部依賴）** |
| 4 | 強制工作鏈 PA→E1×5→E2→E4→QA→PM IMPL | 🟡 **A+C+D done, B MISSING, E partial** |
| 5 | F-FA-1/2/3 pre-IMPL | ✅ |
| 6 | reject_cooldown entry/close 拆分 | ✅ |

### 3-Gate 真實狀態

| Gate | 狀態 | 預期 |
|---|---|---|
| P0-EDGE-1 [40] negative realized edge | ❌ ACTIVE | 等 alpha 轉正（W-AUDIT-8b/8c）|
| W-AUDIT-8b Stage 0R | ❌ Round 1 RED | Round 2 rerun 2026-05-18 00:30 UTC |
| W-AUDIT-8a C1 BB/MIT sign-off | 🟡 v2 24h proof IN_FLIGHT | 完成 2026-05-17T14:56:16Z + BB/MIT review |

---

## §5 不做清單 + 理由（per 第 1/2/3 審 + 主會話最終對抗）

| 不做 | 理由 |
|---|---|
| ❌ 修 maker entry | entry 100% maker 已生效（DB verify）；前 3 審「entry 是 taker」全錯 |
| ❌ Grid step 35-45 bps 直接調 | 22 bps 已是 min_grid_step_bps + 2x cost_floor_multiplier；單面 step 改大不解 close 100% taker bleed |
| ❌ 把 phys_lock 列為「不可改 risk control」 | phys_lock 是 profit-protection 4-gate Lock decision；可改 maker-first |
| ❌ 把 bb_mean_revert 列為「跨策略 risk close」 | same-strategy exit per Option A-Lite filter；可改 maker-first |
| ❌ bb_breakout +2.29 root cause 對照分析 | 樣本 27 / BILLUSDT 2 筆主導 / 統計無意義 |
| ❌ 5 textbook 策略參數調整 / sizing | 已 dead per archive；structural alpha deficit 非參數問題 |
| ❌ 啟 paper 任何動作 | per AMD-2026-05-15-01 BLOCKED |
| ❌ Mainnet live 啟用 | 3-gate 未解 + Phase 2b PASS 未到 |
| ❌ phys_lock live 啟用 risk_config_live.toml 修改 | pure DRAFT v0.2，pending Phase 2b PASS + QC counterfactual + operator sign-off |
| ❌ 訂閱 production WS allLiquidation.* topic | C1 PASS 前禁 |
| ❌ A4-C BTC→Alt Lead-Lag 重啟同 feature shape | per CLAUDE.md §三 tombstone no-revive |
| ❌ 修 funding_arb | per ADR-0018 已 retire |

---

## §6 預期改善量化

### Phase 1b close-maker-first（root cause #3 治療）

per Wave 1 Track E3 empirical baseline（commit `b98706d5`）+ AMD v0.4 §1 footnote：

| 估算 | 值 |
|---|---|
| Fee saving per close attempt（best/median/conservative）| 3.31 / 0.95 / 0.66 bps net |
| 全年估算 | **$50-$200 fee saving** |
| 30d demo 虧損 | -$110.43（年化 ~$1300）|
| 30d live_demo 虧損 | -$27.31（年化 ~$330）|
| **Fee saving / total loss ratio** | **~5-15%**（剩 85-95% 來自 alpha gap）|

**結論**: Phase 1b 是 marginal fee 優化，**不能單獨解 trading losses**。

### Alpha source 軸（root cause #1 治癒，60% 主因）

| 候選 | 狀態 | 預期觸發 |
|---|---|---|
| W-AUDIT-8b Funding Skew | Round 1 RED, Round 2 pending | best case 4-6 週 demo evidence |
| W-AUDIT-8c Liquidation Cluster | 等 C1 PASS | 8-12 週 IMPL + demo |
| W-AUDIT-8a Phase D Tier 4 | 21-30 days spec ready | 12-16 週 |
| Total ETA to alpha-positive | — | **樂觀 4-6 週 / 悲觀 12-16 週** |

---

## §7 Cross-Reference Index

| 主題 | 文件 |
|---|---|
| 真實 3-round audit narrative | `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md` §2 |
| Phase 1b spec v1.3 | `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` |
| AMD-2026-05-15-02 v0.4 | `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` |
| V094 schema spec | `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` |
| W-AUDIT-8b spec v0.3 | `docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md` |
| W-AUDIT-8c spec | `docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md` |
| W-AUDIT-8a Phase B/C/D spec | `docs/execution_plan/2026-05-16--w_audit_8a_phase_b_c_d_infrastructure_spec.md` |
| phys_lock live AMD v0.2 | `docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md` |
| W-AUDIT-8b RED RCA | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_red_rca_and_next_step.md` |
| precompact snapshot | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--precompact_session_state_snapshot.md` |
| QC P0-MICRO-PROFIT 5 root cause | `TODO.md` §11.4 |
| 4-agent verdicts | `docs/CCAgentWorkSpace/{QC,FA,BB,MIT}/workspace/reports/2026-05-15..2026-05-16--*` |

---

## §8 變更歷史

| 日期 | 版本 | 變更 | 作者 |
|---|---|---|---|
| 2026-05-16 | v1.0 | 補存第三方 3-round audit + 主會話對抗收斂後的完整修復方案 single SoT；之前散在 chat + verdict reports 未整合 | Main session post-precompact |

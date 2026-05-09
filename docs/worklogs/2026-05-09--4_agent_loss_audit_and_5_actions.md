# 2026-05-09 — 4-Agent 虧損根因 audit + 5 立即行動

## 背景

Operator 提問「研究虧損的原因 + 一勞永逸的全面提升思路」（拒絕 disable / block / 縮頻）。
PM dispatch 4 個獨立 sub-agent 並行做 root cause + 升級藍圖：

- **QC**：alpha source / replication crisis / microstructure 視角
- **MIT**：ML pipeline / data contamination / feature engineering 視角
- **PA**：system architect 視角（接口契約 / 5-Agent scope / 治理張力）
- **FA**：dormant alpha 功能盤點 + fail-closed 累加效應

四 agent 互不互通起點，各寫獨立 report：

- `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-09--full_loss_root_cause_alpha_upgrade.md`（QC inline，未落 .md，本 worklog 為主要紀錄）
- `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-09--full_loss_data_ml_upgrade_blueprint.md`（同上 inline）
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`（PA 已落 .md）
- `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_loss_dormant_alpha_features_inventory.md`（FA 落 .md）

## Cross-agent 共識（PM 整合）

四 agent 完美 converge：**5 textbook 策略不是「需要更好參數」，是站在已無 alpha 的 territory**。
Demo 7d gross −26.44 USDT 不是策略 bug、不是 fee 太高、不是 cron 沒裝 ——
是 **alpha source 從未在 (Bybit perp + 1m + 標準 TA + retail flow) 這個交集存在**。

### 三層共識根因

1. **架構層**（PA）：Strategy Interface 結構性偏向 TA — `TickContext` 已暴露 funding/OI/orderbook
   但 `IndicatorEngine` 中央化使 TA 是高速公路、其他是泥路；`Strategist` scope = 4×5
   hardcoded regime preferences + ±50% 參數調，**沒有 alpha discovery 代碼路徑**
2. **業務鏈層**（FA）：22 fail-closed default 累加 = 期望 alpha = 0 — 5-Agent 鏈下單真值率 0%
   × Layer 2 escalation 0% × Promotion Pipeline trigger 0% × cost_edge_advisor 0% = pathway 期望 0%；
   **P0-EDGE-1 雞生蛋蛋生雞死循環**：解 P0-EDGE-1 需要 5-Agent 真實下單樣本，但 5-Agent 鏈被
   shadow=true 鎖死等 P0-EDGE-1 解
3. **ML pipeline 層**（MIT，PG 直查證據）：99.47% chain failure 是 `E_no_label_yet`；
   `decision_features` 24h 38,547 row 中 38,284 是 orphan（99.32%）= ML 學的是「scanner 候選池」；
   Fill writer 24h 175 fills 只 67 有 `entry_context_id`（38%）→ backfill EXISTS join 永斷；
   Governance reject 0 negative label → 訓練集 67 vs 應有 12,500+

### Cross-agent fact-check 校正

| Finding | 整合 verdict |
|---|---|
| QC v2-NEW-4 「Donchian shift(1) 未進 runtime」 | **QC 錯誤** — `mod.rs:150` `donchian_prior` 自 75741eff (2026-04-28) 已 wire 11 天，QC 漏看 callsite |
| `promotion_pipeline.py` LIVE | **MIT/FA 對** — commit message 誤導，0 production caller 實證 |
| 5 策略結構性無 alpha | **3 agent 共識** — first-principle + 樣本 + 架構視角各自證實 |
| 修 88 finding 是足夠路徑 | **3 agent 共識：不夠** — PA「先修 88 是錯的順序」 |

## Operator 拍板（2026-05-09）

對 PM 整合報告的 5 立即行動 + 3 governance decision，operator 回應：
> 「1-5 按照你的想法做掉，其餘部分把需要 plan 的列出來。」

### 1-5 立即執行（auto mode）

**A1 · 5 ML cron install** — 5min ops
- 既有 `helper_scripts/cron/ml_training_maintenance_cron.sh` 已包 5 ML scripts
  (thompson_sampling / optuna_optimizer / cpcv_validator / dl3_foundation / weekly_report_generator)
  + 5 既有 (linucb_trainer / mlde_shadow_advisor / mlde_demo_applier / scorer_trainer / quantile_trainer)
- Install 一行：`17 3 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/ml_training_maintenance_cron.sh`
- 預期：feature_baselines / drift_events / model_performance 從 dormant 變 alive；不直接拉 attribution

**A2 · cost_edge_advisor env flag ON** — 0.5h ops
- `restart_all.sh` engine + API 兩 block 加 `OPENCLAW_COST_EDGE_ADVISOR` 讀取 + inject
- `secrets/environment_files/basic_system_services.env` 加 `OPENCLAW_COST_EDGE_ADVISOR=1`
- restart engine + API（`--keep-auth`）
- 預期：防 LLM cost 吃掉策略 alpha；長期省 5-15 USDT/month

**A3 · Donchian belief 撤銷**
- TODO.md NEW-ISSUE-1 entry 補述 cross-agent fact-check：runtime 已 leak-free 11 天
- 撤銷 QC v2-NEW-4 contaminated push 帶出的 stale belief

**A4（即 Decision-1）· AMD-2026-05-09-03 graduated canary default amendment**
- 派 PA background：撰寫 `docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`
- 修訂 AMD-2026-05-09-02 §2 Option A `shadow_mode = fail-closed default` →
  5-stage graduated canary（Stage 0 shadow → 1 paper canary → 2 demo single → 3 demo full → 4 LIVE_PENDING）
- 不適用範圍：DOC-08 §12 9 不變量 / SM-04 CIRCUIT_BREAKER / Live boundary 5-gate（仍 fail-closed）
- 適用範圍：alpha-bearing pathway（5-Agent 真實下單流 / Layer 2 / Promotion Pipeline / cost_edge_advisor / 新 alpha source）

**A5（即 R-1）· W-AUDIT-8a Alpha Surface Foundation 開 wave + spec phase**
- 派 PA background：撰寫 `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
- 升 `Strategy::on_tick(ctx)` → `on_tick(ctx, alpha_surface)`
- 4 Tier AlphaSurface struct（TA / 跨資產截面 / Microstructure / Information flow）
- AlphaSourceTag enum
- 5 既存策略 explicit declare（保 backward compat）
- 4 phase × 1 sprint = 4 sprint deliverable

## 其餘需要 plan 的部分（給 operator decide）

| ID | 主題 | 推薦 owner | 預估 sprint |
|---|---|---|---|
| **A4-strategy** | BTC→Alt Lead-Lag 新策略 IMPL（QC 候選 C，最高 impact） | PA spec → E1 IMPL | 1.5 |
| **A4-funding** | Funding Skew Directional 新策略 IMPL（QC 候選 A） | PA spec → E1 IMPL | 1 |
| **A4-liquidation** | Liquidation Cluster Reaction 新策略 IMPL（QC 候選 B） | PA spec → E1 IMPL | 1.5 |
| **A5-MIT** | decision_features producer redesign（intent-only emit + fill writer entry_context_id trigger + governance reject negative label） | MIT spec → E1 IMPL | 2 |
| **A6** | DSR/PBO/CPCV evidence pipeline 自動化 + trial_sharpes 持久化 | E1 IMPL（spec 已在 W-AUDIT-6c 報告） | 1 |
| **R-2** | Strategist 重定義為 Alpha Source Orchestrator（替 4×5 hardcoded） | PA spec → E1 IMPL | 2-3 |
| **R-3** | Hypothesis Pipeline first-class governance object（含 W-AUDIT-4 ML 基座併入） | PA spec → E1 IMPL | 2-3 |
| **R-4** | Per-alpha-source Live Promotion Gate（替「整 system live_reserved」） | PA spec → E1 IMPL | 2 |
| **R-5** | Spec-as-Code + Module Lifecycle SM | PA spec → E1 IMPL | 1-2 |
| **Decision-2** | W-AUDIT-6 戰略性收斂（砍 ma 重寫 + bb 5m sweep + micro-param sweep，留 funding_arb retire + DSR/PBO + Kelly config） | operator | n/a |
| **Decision-3** | W-AUDIT-4 併入 R-3 Hypothesis Pipeline（ML 基座 IMPL 不分兩條線） | operator | n/a |

## 風險預期

- A2 restart 引入短暫 (~10s) API 暫停；engine restart 不影響 LiveDemo signed authorization (`--keep-auth`)
- A4 amendment 寫好需 operator review + sign-off 才生效
- A5 spec 寫好後仍需 operator 批准 sprint resource 才 dispatch E1 IMPL

## 後續 healthcheck 觀察

- `[40] realized edge`：A2 後預期 demo gross 緩慢改善（cost_edge_advisor 防虧）
- 新增 `[Xc] ml_training_cron_active`：監控 5 ML cron job 真實 fire（待 IMPL）
- 新增 `[58] graduated_canary_stage_invariant`：AMD-2026-05-09-03 配套（待 IMPL）

# 2026-04-22 Step 0 衍生新 TODO 項批次歸檔

本檔案歸檔 DUAL-TRACK-EXIT-1 Step 0 衍生新 TODO 項章節（原 `TODO.md` §Step 0）全部 5 項。2026-04-22 TICK-PIPELINE-MOD-SPLIT-1 收尾後全章節 ✅，從 `TODO.md` 主文件移出避免膨脹。詳細 commit 敘述保留於 `docs/CLAUDE_CHANGELOG.md`；本檔僅列「TODO 項 → commit ref → 一句話結論」。

章節背景：Step 0（W23 Day 1-3）為 DUAL-TRACK-EXIT-1 feasibility probe；Linux audit / Track P / EXIT-FEATURES 等不得不立即做的衍生項在主章節外另列，避免 Phase 1 排程混亂。所有項陸續於 2026-04-18 ~ 2026-04-22 結案。

---

## 1. MARKET-KLINES-STALE-1 ✅ 2026-04-18 commit `65acde6`

- **原問題**：Step 0 feasibility 雙管探針揭露 paper/demo/live 三引擎共用單一 `market_data_tx` channel，kline 寫入高延遲 + 丟訊；`trading.klines_1m` demo/live 分布 4:1 偏差
- **修復**：三引擎 `market_data_tx` 並行化，各自獨立 channel；DB kline 寫入恢復至各引擎獨立追上掃描進度
- **驗證**：klines_1m 24h 窗口 demo 22k / live 20k 平衡；無訊框丟失；無跨引擎 mutex 競爭

## 2. EXIT-FEATURES-TABLE-1 ✅ 2026-04-19 commits `6ea643e` · `c7171b2` · `35808e9`

- **原問題**：DUAL-TRACK-EXIT-1 Phase 1b 需要 `learning.exit_features` 表承載 close-time 7 維衍生特徵；Step 0 feasibility audit 揭露表不存在 + Rust close handler 無寫入路徑
- **修復**：Phase 1b 全部接線（schema + migration + Rust writer + validate_and_close path）+ GAP-1 `apply_confirmed_fill` 補接線（避免 close-without-fill 情境 exit_features 漏寫）+ R1 驗收 coverage=1.000 / 8 of 8 demo 平倉全 row 化
- **FUP 註記**：**若未來 Track P T4 PHYS-LOCK 接線**需重跑驗收 SQL 確認不漏接 `Physical` exit_source — ✅ 已在 TRACK-P-T4-WIRING-1（見 §3）達成

## 3. 2026-04-21 批次結案（14 項，另檔歸檔 `docs/archive/2026-04-21--completed_todo_batch.md`）

- **內容**：DECISION-OUTCOMES-* 三連 · TRACK-P-T4-WIRING-1（主軸解阻塞 `e95c779` + runtime deploy）· DUAL-TRACK Phase 1b Track P v2 pure fn（`aee96b9`）· GATE1-REVERSAL-1 hotfix A（`d0f0c21`）· EDGE-P2-3 Phase 2+ (b) bb + ma PostOnly · EXIT-FEATURES-SPLIT-1（`3a9b988`）· ON-TICK-SPLIT-1（`bfedb56`，sub-agent）· AI-SERVICE-CLIENT-ENV-RACE-1（`580304a`）· CANARY-WRITER-ENV-RACE-1（`d454c17`，sub-agent）· TICK-PIPELINE-MOD-UNUSED-IMPORTS-1（`c164cb6`，sub-agent）· 20:44 CEST `restart_all.sh --rebuild` 部署（engine PID 3954769）
- **詳細**：見 `docs/archive/2026-04-21--completed_todo_batch.md`

## 4. TRACK-P-V2-SWAP-1 ✅ 2026-04-22 commit `306993e`

- **原問題**：TRACK-P-T4-WIRING-1 接線後 Priority 6 仍呼 v1 `physical_micro_profit_lock` + 線性 `PhysLockConfig`（`giveback_atr_norm_threshold=0.7` 固定閾值），與 v2 non-linear `ExitConfig`（`aee96b9`）未接
- **修復**：Priority 6 由 v1 線性 → v2 非線性 `base - slope × peak_atr_norm`（floor 保底）；`RiskConfig.phys_lock: PhysLockConfig` → `RiskConfig.exit: ExitConfig`（`#[serde(alias = "phys_lock")]` 保 TOML 相容）；ArcSwap 熱重載沿用既有 `Arc<ArcSwap<RiskConfig>>`；v1 pure fn + `PhysLockConfig` struct + 8 v1 直測整塊退役（v2 有等值 25 單測於 `exit_features/v2.rs`）
- **驗證**：Mac debug + Linux release `cargo test -p openclaw_engine --lib` 均 **1835 passed / 0 failed**（1843 baseline − 8 退役 v1 直測；精確對帳）；淨 LOC −260
- **部署**：runtime 未部署（operator 指示先不部署），engine PID 3954769 仍跑 v1 linear；下次 `--rebuild` 後 v2 non-linear giveback 生效
- **memory**：`project_track_p_runtime_dead.md` supersede 為 `project_track_p_runtime_live.md`
- **詳細**：`.claude_reports/20260422_200623_track_p_v2_swap.md` + `docs/CLAUDE_CHANGELOG.md`

## 5. TICK-PIPELINE-MOD-SPLIT-1 ✅ 2026-04-22 commit `3d67a99`

- **原問題**：ON-TICK-SPLIT-1（`bfedb56` 2026-04-21）後 `tick_pipeline/mod.rs` 仍 2274 行違反 §七 1200 行硬上限；`impl TickPipeline` 巨塊 L906-2178 ~1272 行（ctor/config sync/exit helpers/channel setters 交織）
- **修復**：sub-agent 執行機械 split，拆為 3 sibling child-module 檔（`impl super::TickPipeline { ... }`）：
  - `pipeline_ctor.rs` (422)：ctor + 基本 setters/getters
  - `pipeline_config.rs` (300)：config sync（risk/budget/maker_kpi/news/fee/account）
  - `pipeline_helpers.rs` (654)：close + exit features + channel setters + misc
  - mod.rs **1012 行**（降 55.5%，進 1200 硬上限）；3 新檔皆 under 800 soft warn
- **Visibility 升級**：8 個被 on_tick/ 跨檔呼的私有 fn 從 `fn` 升 `pub(super) fn`（sync_risk_config_if_changed / sync_maker_kpi_config_if_changed / current_cost_edge_max_ratio / current_min_profit_to_close_pct / close_position_at_symbol_market / emit_close_fill / should_persist_signal / derive_regime）；`apply_risk_snapshot` + `build_exit_feature_row` 同檔 caller 保持私有
- **驗證**：Mac debug + Linux release `cargo test -p openclaw_engine --lib` 均 **1835 passed / 0 failed**（純 refactor，測試數不變）；淨 LOC +114（+1376 新檔 −1273 mod.rs 刪 +11 mod.rs 加）
- **詳細**：`.claude_reports/20260422_204237_tick_pipeline_mod_split.md`

---

## 章節結案

- Step 0 衍生新 TODO 項全章節 ✅（5/5）於 2026-04-22
- 相關 Phase 1 前置工作（EXIT-FEATURES / Track P / DECISION-OUTCOMES / refactor hygiene）代碼層面全 live
- 下游阻塞解除：`TRACK-P-V2-SWAP-1` 完成後，Phase 1b Track P 待部署（operator 決定時機）+ counterfactual audit 校準 `ExitConfig` 3 個非線性 giveback 參數（base/slope/floor）

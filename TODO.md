# OpenClaw TODO — 工作清單（v4 · 精簡版 · 2026-05-01）

**版本**：v4（2026-05-01 精簡清理；Wave 1-3 + Backlog 完成項歸檔）
**歸檔索引**：
- 62-finding Batch A-F：[docs/archive/2026-04-29--62finding-batch-A-to-F.md](docs/archive/2026-04-29--62finding-batch-A-to-F.md)
- STRKUSDT P0 Wave：[docs/archive/2026-04-29--strkusdt-p0-wave.md](docs/archive/2026-04-29--strkusdt-p0-wave.md)
- Wave A-H 完整敘述：[docs/archive/2026-04-29--wave-A-to-H-narrative.md](docs/archive/2026-04-29--wave-A-to-H-narrative.md)
- Wave 1-3 完成表格 + Backlog 完成項：[docs/archive/2026-05-01--completed_waves_1_2_3_and_backlog.md](docs/archive/2026-05-01--completed_waves_1_2_3_and_backlog.md)
- Pre-trim TODO snapshot（2026-04-29 前）：[docs/archive/2026-04-29--TODO-pre-trim-snapshot.md](docs/archive/2026-04-29--TODO-pre-trim-snapshot.md)

**Runtime（2026-04-30 23:11 CEST · runtime checkpoint a9fce24）**：engine PID 1529433 / API 1591455 / watchdog alive；demo/live active，paper inactive by design；latest healthcheck SUMMARY **WARN** exit 0。
**測試基準**：Mac Rust lib **2381/0** · Python maker/attribution **9/0** · MLDE pytest **63/0**
**21d demo 時鐘**：2026-04-16 22:16 → 解鎖 **2026-05-07**

---

## 此刻該做什麼（2026-05-01 · passive observation phase）

**當前狀態**：Strategy Edge Models + Dust Residual Prevention deployed & proven。MLDE demo autonomy active。
下一個需要 implementation 的 wave 是 Wave 4（等 P0-3 ~05-15 決策後啟動）。
目前主要工作是：觀察、時間等待、3 個時間點的決策。

### 時間驅動里程碑

| 日期 | 觸發點 | 動作 |
|------|-------|------|
| **~05-03** | G2-02：1w post-G7-09 demo 數據累積完成 | 跑 `ma_crossover_counterfactual_replay.py`；若結論支持 → 派 G2-03-FUP-CALLER-WIRE P1 |
| **~05-07** | P0-2 21d demo 解鎖 + G2-01 PostOnly 1-2w 驗收 | 若 [33] fee_drop ≥60% → PASS；否則 G2-04 grid disable 決策會 |
| **~05-10** | EDGE-P1b：per-strategy ≥200 rows（grid 1030 / ma 493 READY）| 跑 `exit_threshold_calibrator.py`；manual approve flow |
| **~05-15** | P0-3 邊評決策會 | PM+FA+PA+QC：edge positive/mixed/still negative → LG-2/3/4/5 or dual-track |
| **~05-22+** | Wave 4 實裝 | 依 P0-3 決策路徑啟動 LG-2/3/4/5 |
| **~05-30±7d** | Live target | PM W2 sign-off 目標 |

### Active Observation Gates

| Gate | 現況（2026-04-30 23:11 CEST） | 目標 | 結論時間 |
|------|------------------------------|------|---------|
| [33] maker_fill_rate | 7d rolling 25.6%；post-reload slice 73.23%（diluted by pre-reload）| ≥60% fee_drop | ~05-07/08 |
| [38] grid lifecycle drift | live_demo p50 1.7min vs demo 4.8min（REAL SIGNAL）；grid_levels 10→7 + blocked_symbols 已部署 2026-04-29 | lifetime ≥0.5x | ~05-06 再看 |
| [40] realized edge acceptance | post-cutoff rows=0（太少不能判讀）| net_bps_after_fee>0 | 等累積 |
| [11] counterfactual clean window | n=864/200 PASS；replay JSON 17.2h stale | fresh replay + 3d PASS streak | 本週 |

### G3-09 Phase C（deferred）

PA RFC `2026-04-28--g3_09_cost_edge_advisor_phase_c_rfc.md` ready；operator 決定「等時間長一些」；Phase B observation period 與 Phase C 綁定。

### Maintenance backlog（P4，機會性清理）

- G3-08-FUP-MAF-SPLIT-CLEANUP-A P4：lazy re-export 已接受設計，掃 Scout 首入場 risk 後可清
- SINGLETON-POLLUTION-PHASE2-ROUTES P4（Mac-only）

---

## 背景線程（獨立持續，每 6h cron 監控）

| 項目 | 狀態 | 解鎖條件 |
|------|------|---------|
| P0-2 21d demo 時鐘 | 進行中 | 2026-05-07 |
| [33] PostOnly 驗收（G2-01）| 累積中 | ~05-07/08 出結果 |
| EDGE-P1b exit_features 累積 | grid/ma READY | ~05-10 calibrator |
| EDGE-P3 clean window freshness | sample OK，replay JSON stale | fresh replay + 3d PASS |
| G2-03 binding | 等 G2-02 結論 | ~05-03 觸發 |
| EDGE-P2-flip | 等 EDGE-P1b | ~05-10+ |
| GRID-LIFECYCLE-DRIFT | real signal FAIL；RFC deployed，觀察 14d rolling | ~05-06 再評 |

**規則**：任何背景項連續 3 次 healthcheck FAIL = 中止被動等待，轉人工介入。

---

## Wave 4（6/12→6/23，P0-3 決策後啟動）

### P0-3 Phase 5 Edge 重評

| ID | Tag | 項目 | 前置 |
|----|-----|------|------|
| **P0-3-01** | P0 | counterfactual_exit_replay 完整分析報告 | G2 完成 + MLDE dataset |
| **P0-3-02** | P0 | Edge 重評決策會（A 翻正/B 仍負/C 部分改善） | P0-3-01 |

**outcome 分支**：A. edge 翻正 → LG-2~5 推進 · B. edge 仍負 → DUAL-TRACK + 策略重做 · C. 結構性改善 → Phase 5 部分接線

### ML/Dream Live Governed Boundary

| ID | Tag | 項目 |
|----|-----|------|
| **MLDE-6** | live-governed | Live promotion contract：advisory→proposal→demo patch→live candidate；live 仍需 GovernanceHub + Decision Lease |

### Live Gates（5 項，P0-3 後）

| ID | Tag | 項目 |
|----|-----|------|
| **LG-2** | P0 | H0 Gate blocking 驗證（shadow→blocking） |
| **LG-3** | P0 | Provider pricing table 正式綁定 |
| **LG-4** | P0 | M 章 Supervised Live Gate |
| **LG-5** | P0 | N 章 Constrained Autonomous Live |
| **G-4** | P2 | Cookie secure=True（HTTPS 部署後）|

---

## Backlog（條件觸發，非當前 Wave）

| # | 項目 | 觸發條件 | Tag |
|---|------|---------|-----|
| **G2-03-FUP-CALLER-WIRE** | wire step_6_risk_checks caller chain，真實啟用 SL/TP override | G2-02 ~05-03 後 | P1 |
| **G2-04** | Grid disable 決策會 | G2-01 若 fee_drop <60% | P0 |
| **G8-03** | 灰度驗收自動化（shadow metrics）| EDGE-P2 flip 後 | P1 |
| **G8-05** | AI cost ROI 監控面板 | G3-09 | P2 |
| **EDGE-P2-flip** | combine layer shadow flip | EDGE-P1b + 7d ≥95% agree | P1 |
| **G2-03 binding** | ma_crossover SL/TP 真實啟用 | G2-02 結論 + G2-03-FUP-CALLER-WIRE | P1 |
| **G7-03-Phase-B-FUP-grid** | grid_trading HysteresisDetector 遷移 | parallel WIP merge 後 | deferred |
| **G7-01 wiring** | Kelly router callsites | G4 labels work | deferred |
| **G9-02-FUP-COOLDOWN** | WS force reconnect cooldown 評估 | DEFAULT-ON 後 1-2w passive | LOW |
| **G8-01-FUP-REGRET-DREAM-DEFERRED** | OpportunityTracker + DreamEngine rebuild（per V1.1+R1 SPEC §3+4）| 長期未定 | P3 |
| **G2-FUP-FUNDING-ARB-PAPER-SYNC-LOW-1** | TW memory.md 補 commit msg 一致性 | 下次 TW 接手 | P3 |
| **T6-FUP-PA-MEMORY-INDEX-SYNC** | PA Track 3 dust audit memory.md 條目補錄 | 下次 PA 接手 | LOW |
| **G5-09-FUP-TYPO** | commit `a5b6f17` commit msg test count typo | 下次 commit msg edit cycle | P3 |
| **TIER4-MIT-AUDIT-GREP-SNIPPET** | MIT EXIT-FEATURES audit H1 補 grep snippet 嚴謹度 | 下次 audit | P3 |
| **OC-4** | MCP PostgreSQL 自然語言查詢 | Phase 5+ | P4 |
| **4-Conditional** | PairsTrading/Beta/Kalman/Jump detection | post-live | P4 |
| **G-6/G-7/G-8/G-10** | Edge JS retrain / ClaudeTeacher / cost_gate credibility / isotonic | P1-7B / 21d+G-3 | P4 |
| **LEARNING-COCKPIT-NO-IPC** | Learning 8 端點走 Python state_store | G-7/G-10 後 | P2 |
| **QoL-2** | Demo AI cost 追蹤 GUI（硬編碼 N/A）| G3-08 | P2 |
| **G7-05** | cost_gate grand_mean bind | grand_mean>-50bps ∧ eligible cells>0 ∧ ≥2 strategy shrunk>0 | P1 passive |
| **G-2 FundingArb 重評** | 三參數重評 | R-02 Strategist 在線 | P3 |

---

## Healthcheck 清單（`passive_wait_healthcheck.py` 已實裝）

**Ground truth**：cron-wrapper output，最近一次 2026-04-30 23:11 CEST，checks [1]-[40]（skip [17]，含 [Xa]/[Xb]）。

| # | 項目 | 對應 |
|---|------|------|
| [1] | close_fills_24h | P0-2 engine 活性 |
| [2] | label_backfill | P1-7 C labels |
| [3] | exit_features_writer | EDGE-P1b 寫入面 |
| [4] | phys_lock_runtime | TRACK-P-V2 |
| [6] | trailing_stop_fire | — |
| [7] | edge_estimates_freshness | G1-01 / G4-04 |
| [8] | shadow_exits_24h | EDGE-P2-flip 前 baseline |
| [9] | model_registry_freshness | G4-03 |
| [10] | intents_writer_ratio | G2-01 |
| [11] | counterfactual_clean_window_growth | EDGE-P3 |
| [12] | bb_breakout_post_deadlock_fix | G2-06 disabled → PASS skip |
| [13] | edge_estimator_scheduler_fresh | G1-01 |
| [14] | exit_features_accumulation_rate | EDGE-P1b per-strategy |
| [15] | shadow_exit_agreement_phase2 | EDGE-P2 flip |
| [16] | strategist_cycle_fresh | G3 Strategist runtime |
| [18] | disabled_strategy_inventory | G2-06 drift 防線 |
| [19] | observer_pipeline_alive | G9-04 |
| [20] | h_state_gateway_freshness | G3-08 |
| [21] | paper_state_dust_inventory | Dust prevention |
| [22] | trading_pipeline_silent_gap | F7 |
| [23] | orders_fills_consistency | F7 |
| [24] | signals_writer_freshness | F7 |
| [25] | dust_qty_distribution | F7 |
| [26] | dust_spiral_noise_in_ef | EXIT-FEATURES fix |
| [27] | intents_counter_freeze | F7 |
| [28] | phantom_fills_attribution | F7 |
| [29] | reconciler_paper_state_divergence | deferred Rust handler |
| [30] | cost_edge_advisor_status | G3-09 Phase B |
| [31] | edge_diag_2_strategy_diversity | EDGE-DIAG-2 |
| [32] | maker_entry_intent_drift | G2-01 guard |
| [33] | maker_fill_rate | G2-01 PostOnly target ≥60% |
| [34] | intent_signal_attribution | STRATEGY-EDGE-REPAIR |
| [35] | MLDE data contract | MLDE demo autonomy |
| [36] | MLDE advisory/live lease boundary | MLDE demo autonomy |
| [37] | MLDE demo applier audit | MLDE demo autonomy |
| [38] | grid_trading_lifecycle_drift | GRID-LIFECYCLE-DRIFT |
| [39] | strategy_name_cardinality_drift | STRATEGY-NAME-ATTRIBUTION |
| [40] | realized_edge_acceptance | post-deploy edge observation |
| [Xa] | leader_election_health | G1-01 |
| [Xb] | pipeline_triangulation | G6-01 |

---

## 接手三連檢查

```bash
git status && git log --oneline -5
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py"
```

---

## 工作流程速查

```
角色鏈：E1/E1a 並行（≤5）→ E2（強制）→ E4（強制）→ PM 確認 → commit + push
```

部署：`ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"`

---

**簽核鏈**：PA 核實 → PM Sign-off → commit/push → Linux pull
**下一決策點**：~05-03 G2-02 ma_crossover 數據可用

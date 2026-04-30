# 已完成工作歸檔 — Wave 1/2/3 + Backlog 完成項

**歸檔日期**：2026-05-01  
**歸檔範圍**：Wave 1（G1/G6）、Wave 2（G3/G4/G5/G6-FUP/G7）、Wave 3 派發完成記錄（G2/G8/EDGE/G9）、Backlog 全部 ~~struck-through~~ 完成項  
**注意**：本文件為靜態歸檔，不更新。當前工作狀態見 `srv/TODO.md`（v4）。

---

## 前一輪狀態快照（2026-04-29 20:42 CEST）

62-finding remediation Batch A-F 全部完成、push、Linux rebuild/redeploy；Items 1-6 follow-through commit `53bff07` 已推送、Linux fast-forward、release rebuild + restart。MLDE gap fix `67b1160` 已部署：demo-only Shadow/Dream min_samples 預設 3、live_demo/live 保持 5，LinUCB trainer 回寫 `learning.linucb_state.cumulative_reward`。

**本輪 STRATEGY-NAME-ATTRIBUTION wave**（操 user 觀察 GUI Learning tab 24h LiveDemo 499 / Demo 290 不對稱觸發；PA 報告 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md`）：
- Phase 1 `554d3e0`：GUI 文案修正（影子/真倉 → Demo 引擎/LiveDemo 引擎成交）+ backend `engine_mode_fills_summary` alias + healthcheck `[38] grid_trading_lifecycle_drift` MIT 設計落地
- Phase 2A `45bbe4d`：W1-T1 schema scaffolding，V033 ADD COLUMN `exit_reason TEXT NULL` + Guard A/B；helper `build_close_tags()` + 4 unit tests 拆 sibling `helpers_close_tags.rs`；`[38]` 首跑揭發真信號 FAIL — Live grid p50 lifetime 1.6min vs Demo 9.1min（5.7x 短）
- Phase 2B-1 `f89b463`：W1-T3 Python normalized strategy_name + 7 新 pytest；W1-T4 新 `[39] strategy_name_cardinality_drift`
- W1-T2 deferred：16 close-path emit points sub-agent stalled 600s，worktree discarded
- **W1-T2 producer-side gap 已完成**（`5895579` + hotfix `854cae1`）：close helper / confirmed fill / external command fill 全寫 normalized strategy_name + exit_reason

**Grid risk-policy first wave deployed**（2026-04-29 21:44 UTC）：commit `6fdcc91` 把 `settings/strategy_params_live.toml` 的 `grid_trading.grid_levels` **10→7**，並同步 demo robust-negative `blocked_symbols` 11 個到 live/live_demo。engine PID `794012`、API PID `794081`。

---

## Wave 1（G1 Edge 危機根源修復 + G6 合規 + 觀察性）

**狀態**：✅ 10/11 全完成（G1-01/02/03/05/06 + G6-01/02/03/04/05）

### G1 完成表

| ID | Tag | 完成摘要 |
|---|---|---|
| G1-01 | ✅完成+驗證 | `edge_estimator_scheduler` 診斷 + 恢復。operator commits `f32629c`+`abc85c0`；cells **199** / age 16min；healthcheck [13] PASS。[report](.claude_reports/20260424_122700_g1_01_scheduler_recovery.md) |
| G1-02 | ✅完成+驗證 | `event_consumer/mod.rs` 1762→**225**（<1200）；Linux release 1992/0。[reports](.claude_reports/20260424_14*) |
| G1-03 | ✅7/7 完成 | Rust 硬違反 7 檔全 <1200：resting_orders / risk_config / startup / instrument_info / bybit_rest_client / order_manager / main。1992/0 failed。|
| G1-04 | ✅ as-of compute 2026-04-30 | fee drag / R:R baseline。post-reload slice n=665 maker_like **73.23%** / fee_drop **59.32%**；R:R mixed。[report](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--todo_followthrough_g1_g8_mlhygiene.md) |
| G1-05 | ✅完成 | PostOnly 配置驗證；[design intent doc](docs/references/2026-04-24--postonly_design_intent.md) commit `0da10c0` |
| G1-06 | ✅完成 | Drawdown auto-revoke `drawdown_revoke.rs` 343 行 + 10 unit tests。commit `d1cdd49` |

### G6 完成表

| ID | Tag | 完成摘要 |
|---|---|---|
| G6-01 | ✅完成 | `passive_wait_healthcheck.py` 補齊 5 QA 缺陷 + [Xb] FUP。commits `1cf7ad9`+`9120af7` |
| G6-02 | ✅完成 | healthcheck [13-15] 新增（edge_fresh / exit_feat_rate / shadow_agree）。commit `a0a4981` |
| G6-03 | ✅完成 | V019/V020 retrofit Guard A（V024 migration）；`_sqlx_migrations` row 24 success=t。commits `ff5bf1f`+`309d5b1`+revert `55ed449` |
| G6-04 | ✅完成 | CLAUDE.md §三 敘述同步規則；`docs/lessons.md:30` + §七 drift 防線。commit `d60ad45` |
| G6-05 | ✅完成 | retired-check audit — NO ZOMBIES DETECTED；17 checks 分類清晰。[audit](.claude_reports/20260424_225536_g6_05_retired_check_audit.md) |

### Wave 1 完成標準 Go/No-Go

- [x] G1-01 scheduler cells 199 / [13] PASS
- [x] G1-02 event_consumer <1200 + engine lib 1992/0
- [x] G1-05 PostOnly design intent doc 存檔
- [x] G6-01+02 所有被動等待項附 healthcheck
- [x] G6-03 V024 auto_migrate apply 成功
- [x] G6-04 CLAUDE.md §三 drift 規則已登
- [x] G6-05 retired-check audit NO ZOMBIES

### Wave 1 收尾 Commits

| Commit | 任務 |
|---|---|
| `040a02a` | Wave 1 收尾 TODO 更新 |
| `a0a4981` | G6-02 [13-15] new checks |
| `309d5b1` | G6-03 FUP test fixtures |
| `9120af7` | G6-01 FUP [Xb] cross-validation |
| `1cf7ad9` | G6-01 healthcheck 5 fix |
| `d1cdd49` | G1-06 drawdown auto-revoke |
| `0da10c0` | G1-05 PostOnly doc |
| `ff5bf1f` | G6-03 V019/V020 Guard A |
| `d60ad45` | G6-04 §三 drift rule |
| `357a1e7` | G1-03 main.rs split |

---

## Wave 2（G3 AI 接線 + G4 ML + G5 架構 + G6-FUP + G7 量化）

**狀態**：✅ 主軸完成

### G3 AI 多 Agent 接線

| ID | 完成摘要 |
|---|---|
| G3-01 ✅ | ExecutorAgent ConfigStore + IPC RFC；PA 755 行 RFC。commit `4d24f48` |
| G3-02 Phase A ✅ | ExecutorConfig schema + IPC e2e；`RiskConfig.executor` sub-struct。commits `16c97c1`+`03acedb` |
| G3-03 Phase B ✅ | Python ExecutorConfig cache + ExecutorAgent rewire；`shadow_mode_provider` lambda。commit `51608fe` |
| G3-02 Phase C ✅ | Operator API shadow-toggle 5-gate live auth chain。commit `325582f` |
| G3-03（Rust IPC）✅ | 由既有 `patch_risk_config` IPC 路徑覆蓋（Phase A e2e `03acedb` 已驗）|
| G3-04 ✅ | ExecutorAgent shadow→live e2e 整合測試 5 class / 8 case；Linux pytest 74/0。commit `852da0f` |
| G3-05 ✅ | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC；exit.shadow_enabled IPC hot-reload regression。commits `e710026`+`491b045` |
| G3-06 Phase A ✅（Phase B deferred）| Python Layer 2 escalation rules；`EscalationTier` enum；DEFAULT-OFF env-gated。commit `82ef8e1`。Phase B Rust integration deferred — 在 v4 TODO backlog 追蹤 `G3-06 Phase B` |
| G3-07 ✅ | Layer 2 工具箱補全；591 行 sibling + 36 unit tests；Linux pytest 136/0。commits `ac6c09a`+`31fa96c` |
| G3-08 PA+Phase 1A+B ✅ | h_state_cache 5 new Rust files + Python invalidator/query_handler；env-gate `OPENCLAW_H_STATE_GATEWAY`。commits `7564d07`+`aa287c4`+`1c7b20e`+`deac4bc` |
| G3-09 cost_edge_ratio PA design ✅ | PA RFC NEW cost_edge_advisor；Phase A→B→C path。commit `642c34c` |
| G3-09 Phase A schema impl ✅ | cost_edge_advisor ~1338 LOC Rust；cargo lib 2252→2290/0；env-gate dual safeguard。commit `00682ef` |
| G3-10 ✅ | STRATEGIST-PROMOTE-TRIGGER-1 POST /api/v1/strategist/promote。commit `f800aaa` |
| G3-11 ✅ | STRATEGIST-CYCLE-OBSERVABILITY-1 Rust CycleCounters + IPC emit + Python DB sink。commit `58a289e` |
| G3-08-PHASE-1C-WIRING ✅ | strategy_wiring.py condition spawn `_H_STATE_INVALIDATOR` + healthcheck [20]。commits `5943337`+`deee78e` |
| G3-08-PHASE-2-H1-H3 ✅ | h1_thought_gate + model_router H-state snapshots；+61 pytest。commits `9120948`+`f2ed286` |
| G3-08-PHASE-3 all sub-tasks ✅ | H2/H4/H5 全 wired（commits `8cd257e`+`71faf4c`+`d1a2252`）；Phase 3 COMPLETE |
| G3-08-PHASE-4 all ✅ | Strategist 1200→792 + CostTracker 930→540（splits + impl）；commits `6fac0ca`+`afce487`+`73c1f3d`+`c077e8c` |
| G3-08-PHASE-4-5AGENT ✅ | ALL 5 sub-task E1+E2+E4 全鏈 PASS；10-bucket envelope live。commits `c8a4a55`→`b67b0a8` |
| G3-09-PHASE-A-DAEMON-INTEGRATION-TEST ✅ | 6 cases / 5 proofs；Mac+Linux 6/0。commit `af66ac1` |
| G3-09-PHASE-B-FUP-STICKY-TS ✅ | daemon sticky_triggered_at_ms；Design A。commit `9303a3b` |
| G3-09-PHASE-B-FUP-SPAWN-TEST ✅ | 3 cases A/B/C；+357 LOC tests。commit `22c57dc` |

### G4 ML 管線

| ID | 完成摘要 |
|---|---|
| G4-01 ✅ | Labels pooled 加速；`PipelineConfig.symbol Optional[str]`。commit `dc06b88` |
| G4-02 ✅ | `run_training_pipeline.py` import path fix；首個 ONNX artifact。commit `2c970bb` |
| G4-03 Phase A ✅ | Canary auto-promote evaluator；DEFAULT-OFF env-gate。commits `1164ede`+`01fe46c` |

### G5 架構 / 可讀性債務

| ID | 完成摘要 |
|---|---|
| G5-01 ✅ | `main.rs` 2062→1162（G1-03 commit `357a1e7` + doc calibration 2026-04-30）|
| G5-02 ✅ | `live_session_routes.py` 1449→706+436+439；pytest 117/0。commit `e0d02b2` |
| G5-03 ✅ | `instrument_info.rs` 1975→1008（G1-03 commit `1127f38`）|
| G5-04 ✅ | `ai_service.py` 1318→242+813+373；Linux pytest 50/0。commit `37172b0` |
| G5-05 ✅ | `bb_reversion.rs` 1143→433+287+460；20+35 全綠。commit `8523946` |
| G5-06 ✅ | 原 5 檔全 <1200；bybit_private_ws.rs/tick_pipeline/commands.rs 列為 dedicated wave |
| G5-07 ✅ | `event_consumer/tests.rs` 1298→6 sibling；Linux release 1992/0。commit `913b536` |
| G5-08 PA design ✅ | strategist_scheduler split 設計。commit `2063386` |
| G5-08 E1 impl ✅ | `strategist_scheduler/mod.rs` 1819→426；targeted 32/0。（2026-04-29 maintenance）|
| G5-09 ✅ | `tick_pipeline/tests.rs` 3524→11 sibling；126 tests PASS。commits `a5b6f17`+`35b9d5f` |
| G5-FUP-PASSIVE-HEALTH split ✅ | `passive_wait_healthcheck.py` 2294→9 modules；19 check cron PASS。commit `cc4c2d2` |
| G5-FUP-IPC-MOD-SPLIT ✅ | `mod.rs` 1251→138 + 6 sibling；Mac+Linux 2166/0。commit `bd5ce56` |

### G6-FUP Wave 2

| ID | 完成摘要 |
|---|---|
| G6-FUP-NEWS-HALT-DEDUP-1 ✅ | guardian halt 30min TTL auto-clear；6 unit tests。commit `b980986` |
| G6-FUP-TICK-PIPELINE-DEAD-1 ✅ | tick pipeline boot deadlock RCA + fix（IPC fan-out → tokio::spawn）。commit `b980986` |

### G7 量化配置化

| ID | 完成摘要 |
|---|---|
| G7-01 ✅ surface | Kelly tier boundaries 參數化；wiring deferred。commits `42758e7`+`e4b63b4` |
| G7-02 ✅ | EWMA Vol lambda per-timeframe；Linux 2023/0。commit `6b7246d` |
| G7-03 Phase A+B 3/4 ✅ | Hurst + HysteresisDetector；grid_trading deferred（G7-03-Phase-B-FUP-grid）|
| G7-04 Phase A ✅ | CUSUM schema landing；Linux 2030/0。commit `1628cb6` |
| G7-06 ✅ | Grid OU residual σ estimator；gated dormant；Linux 2046/0。commit `67a8261` |
| G7-07 ✅ | Slippage / confluence hardcode → SlippageConfig；Linux 2039/0。commit `92e65af` |
| G7-08 ✅ | outcome_backfiller SQL 484x speedup（V025 partial index）。commit `743cfa9` |
| G7-09 ✅ | FIX-FEE-POSTONLY-1；Linux 1995/0；deploy 23:41 CEST。commit `872478a` |
| G7-09b ✅ | `trading.orders.order_type` mirror PendingOrder。commit `7f0e793` |
| G7-09c Phase 1 ✅ | BBO-aware PostOnly maker price 4 策略。commit `ac70862` |

### Wave 2 完成標準

- [x] G3-01~04 ExecutorAgent shadow→live e2e pass
- [x] G4-02 第一個 ONNX artifact 進 registry
- [x] G4-03 canary auto-promote evaluator Phase A
- [x] G5-01~07 listed refactor rows complete/recalibrated
- [x] G7 量化配置化 9/10（G7-05 passive wait Post-G7-09）
- [x] 雙 P0 RCA 修復（G6-FUP-NEWS-HALT + G6-FUP-TICK-PIPELINE）

---

## Wave 3（EDGE + G2 策略驗證 + G8 測試 + G9 Bybit API）

**狀態**：✅ 派發層面 100% 完成（5 波 6 commits c1142d2→df882ad）

### Wave 3 派發完成記錄

| 波 | commit | 內容 |
|---|---|---|
| W1 | c1142d2 | 4-agent audit + G2-02 counterfactual + G8-02 parity + TODO EDGE-P3 (c) bug 修 + G8-04 降 backlog |
| W1.5 | 8946e47 | grid_trading G7-09c Phase 2 + 18-agent runtime memory |
| W3 | 55801fe | G2-06 bb_breakout disable + PA 3 RFC（EDGE-P1b/P2-flip/G2-03）|
| W4 | 60fdf74 | EDGE-P1b 4/4 + EDGE-P2-flip T1+T3 + G2-03 4/4 schema staging |
| W5 | 9cfdd52 | EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX |
| Sign-off | df882ad | PM Wave 3 Final Sign-off + rebuild 部署成功 |

### G2 策略驗證 完成項

| ID | 完成摘要 |
|---|---|
| G2-02 ✅ tool landed | `ma_crossover_counterfactual_replay.py` 822 行；等 ~05-03 真實 1w 數據 |
| G2-03 ✅ schema staging | `risk_config_per_strategy.rs` StrategyOverride + risk_checks helpers + 3 TOML + bind SOP；等 G2-02 結論 |
| G2-05 ✅ | bb_breakout FIX-26-DEADLOCK-1 rebuild 驗證 → 結構性 dormancy CONFIRMED，觸發 G2-06 |
| G2-06 ✅ | bb_breakout 永久 disable（PA RFC 選 C）；三環境 TOML active=false；[12] disabled-skip；[18] inventory |
| STRATEGY-NAME-ATTRIBUTION-W1-T2 ✅ | `5895579`+hotfix `854cae1`；close helper + confirmed fill + external command fill 寫 normalized strategy_name + exit_reason |

### G8 測試 / Healthcheck 完成項

| ID | 完成摘要 |
|---|---|
| G8-01 ✅ | CognitiveModulator e2e 40/0；coverage 76/81 (93.8%)。2026-04-30 |
| G8-02 ✅ | Python↔Rust parity 70 case agree=70/70 (100%)。commit `c1142d2` |

### G9 Bybit API 精進

| ID | 完成摘要 |
|---|---|
| G9-01 ✅ | Bybit API 字典 confirm-mmr 路徑修正。commit `0cda2d9` |
| G9-02 ✅ | WS unknown-handler force reconnect；DEFAULT-OFF；engine lib 2176/0。commit `6990668` |
| G9-02-FUP-WS-CLIENT-SPLIT ✅ | ws_client.rs 1227→6 sibling；cargo lib 2176/0。commit `eb65e1e` |
| G9-03 ✅ | `bybit_public_connectivity_check.py` env 化。commit `405c05b` |
| G9-04 ✅ | smoke_test v1 刪除 -164 lines；揭發 OBSERVER-PIPELINE cleanup。commit `c7d7179` |
| G9-05 ✅ | L-2~5 字典補錄 push-back；確認無 drift |
| OBSERVER-PIPELINE-POST-F42FACE-CLEANUP ✅ | -228/+679；[19] observer_pipeline_alive；首次揭露 silent fail ok=1/5。commit `c53c3f9` |

### EDGE 系列 完成項

| ID | 完成摘要 |
|---|---|
| EDGE-P1b schema ✅ | calibrator 1067 行 + summary 825 行 + IPC restore + [14] per-strategy；等資料 ~05-10 |
| EDGE-P2-flip tooling ✅ | dry-run 829 行 + SOP shell + [15] per-strategy + breakdown tool；等 EDGE-P1b 觸發 |
| EDGE-P1b-FUP-STALE-PEAK-IPC ✅ | exit_stale_peak_ms 第 8 維 + deep-merge regression；cargo 2162/0。commit `c2ca032` |
| EDGE-P1b-FUP-NEGATIVE-GUARD ✅ | negative-value guard + 6 unit tests。commit `d8385e6` |
| G1-FUP-CALIBRATOR-WARNING ✅ | banner 移除；commits `92ea90b`+`f633a5a` |

### Wave 3 4-agent audit 報告索引

- PA：[2026-04-26--wave3_dispatch_research.md](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--wave3_dispatch_research.md)
- MIT：[2026-04-26--wave3_data_audit.md](docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-26--wave3_data_audit.md)
- QC：[2026-04-26--wave3_strategy_audit.md](docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-26--wave3_strategy_audit.md)
- FA：[2026-04-26--wave3_spec_readiness.md](docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-26--wave3_spec_readiness.md)
- PM 派發整合：[2026-04-26--wave3_dispatch_signoff.md](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-26--wave3_dispatch_signoff.md)

---

## Backlog 已完成項（struck-through from v3 TODO）

| ID | 完成摘要 |
|---|---|
| G2-FUP-FUNDING-ARB-PAPER-SYNC ✅ | paper TOML active=true→false；三環境 grep 驗。commit `df1d629` |
| G2-FUP-IPC-LEGACY-MS-FIX ✅ | `ipc_client.py:786` ms→s + 3 unit test PASS。commit `9cfdd52` |
| EDGE-P1b-FUP-STALE-PEAK-IPC ✅ | exit_stale_peak_ms IPC schema + regression test；cargo 2162/0。commit `c2ca032` |
| G5-FUP-IPC-MOD-SPLIT ✅ | mod.rs 1251→138 + 6 sibling。commit `bd5ce56` |
| G1-FUP-CALIBRATOR-WARNING ✅ | banner 移除。commits `92ea90b`+`f633a5a` |
| LLM-ABC-MIGRATION-1 ✅ | 2026-04-20 完成，FA 驗 |
| DUST-EVICTION GUI ✅ | tab-live + tab-demo `<details>` 摺疊面板。commit `bd55df1` |
| STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1 ✅ | Python prompt ±30% cap + int-ness fix；e2e 驗收首行落表。commits `d8f5560`+`e47b1e9`+`5538e52` |
| STRATEGIST-TUNE-TARGET-CONFIG-1 ✅ | `RiskConfig.strategist.max_param_delta_pct` + StrategistConfig；Mac 2094/0。commit `e388065` |
| STRATEGIST-HISTORY GUI ✅ | tab-strategy.html 折疊 sub-panel + cycle_metrics footer |
| G5-08 PA design ✅ | strategist_scheduler split 設計。commit `2063386` |
| G5-08 E1 impl ✅ | mod.rs 1819→426；targeted 32/0。（2026-04-29）|
| G5-09 tick_pipeline tests split ✅ | 3524→11 sibling；126 tests PASS。commits `a5b6f17`+`35b9d5f` |
| G5-FUP-PASSIVE-HEALTH split ✅ | 2294→9 modules Python package。commit `cc4c2d2` |
| EXIT-FEATURES-WRITER-BUG-1 ✅ | RCA-A ft_dust_qty_floor_usd + RCA-B is_partial_reduce_tag；engine lib +12。commits `af48ee1`+`83456e5`+`00a9679` |
| EXIT-FEATURES-WRITER-BUG-1-FIX（同上）| 見上 |
| EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT ✅ | tick_pipeline/on_tick/helpers.rs 1411→336；PHYS-LOCK tests sibling。（2026-04-30）|
| EDGE-P1b-FUP-NEGATIVE-GUARD ✅ | negative-value guard + 6 unit tests。commit `d8385e6` |
| AGENT-HEARTBEAT-SCOUT-WIRE ✅ | `_scan_and_produce_intel()` 兩條 path 呼 `ScoutAgent.record_scan()`；2 hermetic tests。commit `f8a245c` |
| CHECKS-STRATEGY-SUBSPLIT ✅ | `checks_strategy.py` 1239→924 + 2 sibling。（2026-04-29 maintenance）|
| CHECKS-ENGINE-SUBSPLIT ✅ | `checks_engine.py` 1206→1143 + `checks_engine_reconciler.py` 78。（2026-04-29）|
| VERIFY-IPC-TOKEN-EMPTY-SECRET ✅ | fail-closed empty secret + regression test；5/0。（2026-04-29）|
| G3-08-FUP-MAF-SPLIT ✅ | multi_agent_framework.py 1190→966 + scout_agent.py NEW 297；PEP 562 lazy re-export。commits `b8b5150`+`d190acb` |
| G3-09-PHASE-A-DAEMON-INTEGRATION-TEST ✅ | 6 cases / 5 proofs。commit `af66ac1` |
| G8-01 W1 CognitiveModulator dead-path fix ✅ | BUG-A method rename + BUG-B update caller；6 sanity tests；171 strategist regression 全綠。commit `aca7ee3` |
| G8-01 W2 ≥85% line cov ✅ | 26 unit cases；Wave B sign-off 記錄 W2 100% cov |
| G8-01 W3 StrategistAgent integration ✅ | 8 integration scenarios（超過 min 5）|
| G8-01-FUP-LOSSES-WIRING ✅ | Hybrid Option 1；Analyst.set_strategist_loss_callback + Strategist.record_trade_outcome；Mac 86 + Linux 199 全綠。commit `aced662` |
| G3-09-PHASE-B-FUP-STICKY-TS ✅ | daemon sticky_triggered_at_ms Design A。commit `9303a3b` |
| G3-09-PHASE-B-FUP-SPAWN-TEST ✅ | 3 cases A/B/C +357 LOC。commit `22c57dc` |
| G3-08-FUP-MAF-SPLIT-CLEANUP ✅ | Recalibrated 2026-04-30；lazy re-export 接受設計 |
| G3-09-DAEMON-TEST-SPLIT ✅ | daemon tests 拆為 3 檔；全 <800。（2026-04-30）|
| G3-09-FUP-CASE-D-H5-WAIT ✅ | H5 timeout warning lifted to constant；1/0。（2026-04-29）|
| G8-01-FUP-REGRET-DREAM-WIRING ✅ | Escalated → Option C deferred。PA report `2026-04-28--g8_01_fup_regret_dream_wiring.md` |
| G3-09-PA-DOCSTRING-CLARIFY ✅ | lambda capture comment 修正。（2026-04-29）|
| G3-08-FUP-ANALYST-SPLIT ✅ | `analyst_agent.py` 764 LOC (<800)；2026-04-30 cleanup |
| G3-08-FUP-HSQ-SPLIT ✅ | `h_state_query_handler.py` 452 LOC；stale row 已歸檔 |
| G3-08-FUP-STRATEGIST-DELEGATOR-SLIM ✅ | `strategist_agent.py` 797 LOC (<800)；2026-04-30 cleanup |
| G3-08-FUP-EXECUTOR-EARLY-RETURN-LOW1 ✅ | early returns fire h_state invalidation；3 regression tests。（2026-04-29）|
| G3-09-PHASE-A-PA-RFC-SLOT-UPDATE ✅ | PA RFC §6.2 healthcheck slot [30] 同步 |
| G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN PA design ✅ | Option B 推薦。commit `306b549` |
| G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN E1 impl ✅ | Rust H3RouteStats rename + 3 fields；cargo 2212。commit `4b30f5e` |
| T7-FUP-DUST-SQL-DEVIATION-DOC ✅ | RFC §7.4 amend + §13 Deviation Log。commit `79a808a` |
| T8-FUP-RFC-TYPO-FIX ✅ | RFC §7.2 1 word fix。commit `642c34c` |
| G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE ✅ | Closed by G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE |
| PAPER-STATE-DUST-RESTORE-AUDIT ✅ | [21] paper_state_dust_inventory 三態；14 unit tests；Linux cron LIVE PASS。commit `8241133` |
| PAPER-STATE-DUST-INVENTORY-MONITOR ✅ | 同上 |
| ML-TRAINING-DATA-HYGIENE-1 ✅ | dust spiral noise 2.01% < 5%；no backfill needed。（2026-04-30）|
| MICRO-PROFIT-FIX-1-HEALTHCHECK ✅ | Superseded by [21] paper_state_dust_inventory |
| TIER4-OBSERVER-LOW-1 ✅ | aggregate-exit log 保留 OBSERVER_RC + BRIDGE_RC。commit `d8385e6` |
| T6-FUP-WARN-ZONE-FILES-SPLIT ✅ | checks_derived.py 990→444 + 3 sibling；ipc_client.py 901→749 + 2 sibling。（2026-04-30）|
| TIER4-AI-SERVICE-DISPATCH-SPLIT ✅ | `ai_service_dispatch.py` 868→727 + guardian sibling 169。（2026-04-30）|
| STRK-FUP-LOOP-HANDLERS-SPLIT ✅ | `loop_handlers.rs` 1481→1188 + 2 sibling。（2026-04-29）|
| STRK-FUP-MEMORY-CONFLICT-RESOLVED ✅ | E1/memory.md merge conflict resolved。（2026-04-27）|
| STRK-FUP-BASELINE-UPDATE ✅ | TODO + CLAUDE.md §十一 baseline 2161→2252 updated |
| STRK-FUP-F7-CRON-CD-CHECK ✅ | cron wrapper grep [22]-[29] self-check；Linux exit=0 驗。commits `030ef2d`+`0e9e257`+`f0d21b9`+`af9d552` |
| STRK-FUP-HEALTHCHECK-PRE-EXISTING ✅ | latest [3]/[19]/[23]/[24]/[26]/[27] PASS；2026-04-30 runtime observation |
| LIVE-RECONCILER-STALE-CMD-TX ✅ | reconciler per-dispatch LiveCmdSenderSlot snapshot；Batch A/SW-002 |
| G2-01-FUP-MAKER-FILL-CHECK ✅ | [33] maker_fill_rate 7d dedicated check + unit tests。commits `030ef2d`+`0e9e257`+`f0d21b9`+`af9d552` |
| G3-08-PHASE-1C-FUP-CHECK20-SYNC ✅ | [20] Phase 2 expected value + set diff WARN 邏輯。commit `d8385e6` |
| G3-07-FUP-ENV-NAMESPACE ✅ | `bybit_public_base_url()` 對齊 production file-based env；targeted pytest PASS。（2026-04-30）|
| G3-07-FUP-PYTEST-MARK ✅ | `conftest.py` slow + e2e markers + e2e decorator。commit `d8385e6` |
| 4-06/MLDE-2 ✅ | Demo/read-only LinUCB intent-arm/reward loop landed under MLDE-2 |
| MLDE-0 ✅ | GovernanceHub live-autonomy boundary documented/enforced。report `2026-04-29--mlde_demo_autonomous_applier.md` |
| MLDE-1 ✅ | Learning Data Contract + [35] PASS；7d MLDE rows 2464。commit `ece31b6` |
| MLDE-2 ✅ | LinUCB intent-arm/reward loop for demo/read-only。report `2026-04-29--ml_dream_edge_unblock_completion.md` |
| MLDE-3 ✅ | ML shadow advisor/scorer advisory path + [36] PASS；24h advisory rows 525 |
| MLDE-4 ✅ | DreamEngine + OpportunityTracker read-only producers integrated |
| MLDE-5 ✅ | Demo A/B bounded applier + [37] PASS；24h rows 172, demo_applied 18 |
| G9-01 ✅ | Bybit API 字典 confirm-mmr 修正。commit `0cda2d9` |
| G9-02 ✅ | WS unknown-handler force reconnect；engine lib 2176/0。commit `6990668` |
| G9-03 ✅ | `bybit_public_connectivity_check.py` env 化。commit `405c05b` |
| G9-04 ✅ | smoke_test v1 刪除；揭發 OBSERVER-PIPELINE cleanup。commit `c7d7179` |
| G9-05 ✅ | L-2~5 字典補錄；確認無 drift |
| G9-02-FUP-WS-CLIENT-SPLIT ✅ | ws_client.rs 1227→6 sibling。commit `eb65e1e` |
| OBSERVER-PIPELINE-POST-F42FACE-CLEANUP ✅ | [19] observer_pipeline_alive + opt-out。commit `c53c3f9` |

---

## 已完成歸檔索引（截至 2026-04-30）

| 日期 | 歸檔 | 內容 |
|---|---|---|
| 2026-04-29 | `docs/archive/2026-04-29--62finding-batch-A-to-F.md` | 62-finding Batch A-F |
| 2026-04-29 | `docs/archive/2026-04-29--strkusdt-p0-wave.md` | STRKUSDT P0 Wave |
| 2026-04-29 | `docs/archive/2026-04-29--wave-A-to-H-narrative.md` | Wave A-H 完整敘述 |
| 2026-04-29 | `docs/archive/2026-04-29--TODO-pre-trim-snapshot.md` | 817 行 pre-trim snapshot |
| 2026-04-30 | `docs/archive/2026-04-30--TODO-pre-cleanup-snapshot.md` | 2026-04-30 前 snapshot |
| 2026-04-30 | `docs/archive/2026-04-30--CLAUDE-pre-cleanup-snapshot.md` | CLAUDE.md pre-cleanup |
| 2026-04-30 | `docs/archive/2026-04-30--README-pre-cleanup-snapshot.md` | README.md pre-cleanup |
| 2026-04-30 | `docs/archive/2026-04-30--active_docs_cleanup_archive.md` | active docs cleanup summary |
| 2026-04-24 | `docs/archive/2026-04-24--todo_v2_dual_axis_snapshot.md` | TODO v2 458 行 |
| 2026-04-24 | `docs/archive/2026-04-24--todo_v1_refactor_snapshot.md` | TODO v1 328 行 |
| 2026-04-24 | `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md` | TODO v0 700 行 |

# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）

---

## 一、項目定位

長期進化型 AI Agent 自動交易系統。OpenClaw 為中樞、**Bybit 為唯一交易所**（專攻）。

> Agent 自主完成交易決策與執行，對成本與收益有清晰感知，能感知自身狀態，能持續學習，在嚴格風控框架下逐步贏得更高自主權。

人類 Operator 角色：不定時檢查、審閱、矯正、批准關鍵步驟、推動策略演進。

**交易所決策（2026-04-03）：** 早期規劃含 Binance 雙平台，現已明確專攻 Bybit。Binance 僅作為超長期可能方向保留，當前開發、設計、架構決策均不需考慮 Binance 兼容性。

**系統管線：** 市場數據 → H0 本地判斷 → H1-H5 AI 治理 → I Decision Lease → 執行適配層 → 學習/歸因

---

## 二、16 條根原則（DOC-01 項目憲法 §5.1–§5.16，不可違背）

1. **單一寫入口** — 所有訂單/執行動作通過唯一受控入口
2. **讀寫分離** — 研究/GUI/學習：只讀。寫入權限極度受限、可審計、可鎖定
3. **AI 輸出 ≠ 即時命令** — AI → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行
4. **策略不能繞過風控** — 所有交易意圖必須經 Guardian 審批
5. **生存 > 利潤** — 先判斷「不會螺旋崩潰」，再判斷「能否盈利」
6. **失敗默認收縮** — 不確定時默認保守：不開新倉、降頻率、降風險
7. **學習 ≠ 改寫 Live** — 學習平面與 Live 平面隔離
8. **交易可解釋** — 每筆交易必須可重建：為什麼、何時、風控審批、授權、執行、結果
9. **交易所災難保護** — 本地止損 + 交易所條件單雙重防線
10. **認知誠實** — 所有結論區分事實 / 推斷 / 假設
11. **Agent 最大自主權** — P0/P1 硬邊界內，Agent 完全自主決定：幣種、策略、參數、時機
12. **持續進化** — 系統必須從交易行為中自動學習（當前 demo 階段：Paper 驗證→參數進化，live 自動部署待 Phase 3 放權框架）
13. **AI 資源成本感知** — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉
14. **零外部成本可運行** — 基礎運營僅需 L0+L1（Ollama + 免費搜索）
15. **多 Agent 協作** — 5 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ Conductor 編排，正式對象通信
16. **組合級風險意識** — 監控關聯曝險、策略重疊持倉、資金分配合理性

**優先級序：** 帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化

**實施準則（從根原則衍生，非憲法級但強制遵守）：**
- **認知調製 ≠ 能力限制** — Agent 壓力下更審慎的方式是提高決策門檻，不是關閉能力。虛擬稀缺性（能量/積分/內部貨幣）被明確否決。（衍生自原則 #11，見 `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`）

---

## 三、當前系統狀態摘要

**Runtime**：`Live_Ready` ⚠️（2026-04-23 21:13 CEST `--rebuild` 部署 WS listener Rust takeover + INFRA-PREBUILD-1 Part A/B 後刷新）— LIVE-P0/P1/P2 代碼完整、單測 **1939 / 0 failed**（Mac + Linux release；post-rebuild operator 續加 `662c707` P0 audit followups → 1926 + `ffd2a4d` P2 Phase 3 PG integration + schema_hash → 1939），**仍 0 真實 live 流量**。**本次 rebuild 帶入 runtime live**：engine PID **764820**（上一 158918 → 213144 → 764820 由 21:13 `--rebuild` 替換）· uvicorn PID **764878** · binary mtime **2026-04-23 21:13**（baseline HEAD `f42face`）· **WS-RETIRE-1（Python `bybit_private_ws_listener.py` 退役完成）**：Rust `bybit_private_ws_status_writer.rs` 每 5s 產 `bybit_private_ws_listener_status_latest.json`（`listener_version: "rust-v1"` / `engine_mode: "demo"` / `auth_ok_count: 1` / 4 topics live）取代原 Python listener（3 檔 340 行已刪）；readonly_observer_pipeline `bybit_build_ws_runtime_facts.py` 讀取無感（`listener_health: healthy` / `business_signal_state: active` 即時驗證通過）· **INFRA-PREBUILD-1 Part A（Combine Layer shadow）dormant**：`shadow_exit_writer.rs` wire 完 + `ExitConfig.shadow_enabled=false` → 0 emit / 0 row（flip TOML 即啟，無須再 rebuild）· **INFRA-PREBUILD-1 Part B（Model Registry）dormant**：`learning.model_registry` hypertable 空 + 5 `/api/v1/ml/*` routes 回 404 直到 P1-7 C labels 滿 200 自動填入 · **先前 2026-04-22 23:35 rebuild 引入的仍 live**：P0-13 ATR scale（`kline_manager.get_ohlcv("1m",20) + indicators::atr(14)` 持倉期 Wilder's ATR ~0.05-0.5%，舊 per-tick `compute_atr_pct` `#[deprecated]` 保留 fast_track 用）· P0-14 A Gate 1 fallback（`ExitConfig.missing_edge_fallback_bps = -10.0`；**本 commit EDGE-DIAG-1-FUP-IPC 前無 IPC 路徑**，TOML 編輯需引擎重啟才生效，本 commit 新增 7 個 `exit.*` 欄位的 IPC 熱重載路徑 + TOML persist，Phase 3 部署後可 <60s 回滾）· P0-14 B JS proxy cells（Python `_inject_sync_label_proxy_cells` 從 43→**135 cells**，+4 sync-label strategies × 23 symbols = 92 proxy cells）· Priority 6 每 tick 呼 `physical_micro_profit_lock_v2` + `ExitConfig`，healthcheck [7] 135/135 PASS 即時驗證 + `phys_lock_*` fire 1-10/day + DB `learning.exit_features.giveback_atr_norm` avg 從 364 → ~0.3-3.0 + `atr_pct` avg 從 0.003 → ~0.05-0.5 觀察中。詳 `docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md` + `2026-04-22--p0_13_14_execution_resume_plan.md` + `.claude_reports/20260423_202943_dedup_fresh_audit_BC_ws_retire.md`。**真實 live 門控**（Rust 可驗證 4 項 / 全部 5 項，詳 §四）：(1) Python `live_reserved` global mode (2) Python Operator 角色 auth (3) `OPENCLAW_ALLOW_MAINNET=1` env（僅 Mainnet）(4) secret slot 有 api_key + api_secret (5) `authorization.json` HMAC 簽名+未過期+env_allowed 匹配。`execution_authority` 在 Rust 僅為 P0/P1 denylist 字串常量（`claude_teacher/applier.rs:226`），非真實授權邏輯。Live 縮倉監控 5min 輪詢（代碼已寫、e2e 測試綠，**從未真實觸發**）。

**權威原則**：Rust `openclaw_engine` = paper/demo/live 三引擎並行唯一引擎（ARCH-RC1 1C-4 + 3E-ARCH）。Rust ConfigStore 為所有交易/風控/學習/預算參數權威，4 IPC 寫入面 → tick-level hot-reload。**禁止 restart-to-apply**。Guardian = RiskConfig 純派生視圖。Python 無交易邏輯（DEAD-PY-2 清除 ~4500 行後）。**2026-04-23 audit 更正**：Wave A-D 拆分**已完成**，54 routes 已分至 5 個 sibling（auth 128 / gui 81 / system 303 / learning 553 / control 493 行），由 `main_legacy.py:464-468` `register_*_legacy_routes(app)` 5 行聚合註冊。`main_legacy.py` 瘦至 **468 行**（原 ~5265 行瘦身 91.1%），只剩 4 singleton（settings/STORE/app/limiter）+ 3 helpers（envelope_response/get_latest_snapshot/current_actor）+ 4 middleware。總和 **2026 行**（main 468 + sibling 1558）。Tier B 實質閉環；進一步拆 singleton/改名屬 cosmetic 非必要（下游 28 檔 `_base.xxx()` 動態查找為 main.py monkey-patch + test reload 契約）。先前 2026-04-16 audit「共 1630 行 · 此層拆分未完成」敘述過期。

**進行中/阻塞**（已完成 ≤2 日的項目 + 仍活躍的 gap；2026-04-21 刷新）：
- **LEARNING-PIPELINE-DORMANT-1（P1，2026-04-16 audit · 2026-04-19 半解 · 2026-04-21 刷新）**：學習管線已部分解凍 — `edge_estimator_scheduler.py` daemon 隨 uvicorn 運作（2026-04-19 `23b14ef`），`settings/edge_estimates.json` 每小時自動刷新（mtime 2026-04-21 20:45 驗證）。**剩餘 gap**：bind cost_gate 門檻 grand_mean > −50 bps 且 ≥2 策略 shrunk_bps>0 尚未滿足（受 P1-10 結構性 fee-drag / R:R 不對稱壓制）；ONNX 訓練 pipeline 工具鏈綠但資料量不足（最大切片 `demo grid_trading BLURUSDT` 47/200 labels，ETA ~3-5d 自然累積過 200）；`experiment_ledger_snapshot.json` 結構異常；21 個 learning schema 表仍無 consumer。TODO §P1-7 / §P1-14。
- **Phase 5 PAUSED**（2026-04-12 reframe）— PNL-FIX-1/2 清理後所有活躍策略 gross edge 為負；cost_gate/DL/JS 機械已接線但需真實正 edge。**下一步**：21d demo 穩定期過後（最早 2026-05-07）P0-3 重評，若仍負則轉 EDGE-P3-1 / EDGE-P2 接管。詳見 `memory/project_phase5_promotion_edge_crisis.md`。
- **P1-6 DEMO-BYBIT-SYNC-ORPHAN-1**：6 個 `bybit_sync` 倉位策略動不了；P1-8 FUP `retriage_synthetic_owner` tick-level 自主接管中，觀察一週（起算 2026-04-17）。TODO §P1-6。
- **P1-10 STRATEGY-ASYMMETRY-1**：grid 過度交易 + ma_crossover R:R 不對稱；2026-04-20 R1 驗收結論 = grid fee drag 主導（結構性，非 cadence）+ ma_crossover win rate 64% → 37.8% 崩；EDGE-P2-3 PostOnly runtime 已 2026-04-21 20:44 部署（demo/paper=true），預期 fee 降 5.5 bps → ~1 bps/side，待 ≥1w demo 資料驗正效果。TODO §P1-10。
- **非阻塞留尾**：W1 event_consumer 拆分；D-02 PriceEvent metadata HashMap 移除；IP-DEDUP-1（等 P0-3 判決）。

**已完成里程碑索引**（完整敘述 + commit + 測試數保留於 `docs/archive/2026-04-15--claude_md_section3_snapshot.md`）：

| 日期 | 里程碑 |
|---|---|
| 2026-04-08 | ARCH-RC1 1C-4 WRAP ✅ |
| 2026-04-09 | StrategyAction Enum ✅ · Rust 市場掃描器 Phase A-D + QC/FA + P2 ✅ |
| 2026-04-10 | DEAD-PY-1/2 · A2 NewsPipeline · LIVE-P0/P1/P2 · Live GUI Phase 4/5/6 + 平倉按鈕 · SEC-05 XSS · SM-1 治理統一 · Signal Diamond Fix · Phase 6 Reconciler 自動降級 · W20 ✅ |
| 2026-04-11 | 3E-ARCH 三引擎並行 · Multi-Symbol Position Tracking · W21 6-04~08 ✅ |
| 2026-04-12 | E5 Performance Optimization（23 項） ✅ |
| 2026-04-13 | G-SR-1 Signal Tightening · OC-5 FundingArb · Edge 數據 engine_mode 隔離 ✅ |
| 2026-04-14 | ORPHAN-ADOPT-1 Phase 1 · QoL-1/3 · ENGINE-HEAL 4 Fix · WP-F/UX-07~10 術語統一 ✅ |
| 2026-04-15 | EDGE-P3-1 ML-MIT #26 Lane A · FA-PHANTOM-2 spec · ORPHAN-ADOPT-1 Phase 2A · engine_watchdog systemd unit ✅ |
| 2026-04-16 | P0-4 R1 STRATEGY-CLOSE-TAG-FIX · P0-0 RECONCILER-BURST-FIX · P0-5 PHANTOM-2-FUP · PAPER-DISABLE-1 · DEDUP-PY-RUST Tier A · EDGE-P3-1 Phase B #3 + Step 7b/7c · G-2 daemon option D ✅ |
| 2026-04-17 | P0-10 SCANNER-GATE · P0-5 PHANTOM-2-FUP · P1-8 DUST-EVICTION-GAP-1 E1/E4 · MICRO-PROFIT-FIX-1 ✅（詳 `docs/archive/2026-04-20--claude_md_section3_snapshot.md`） |
| 2026-04-18 | LIVE-GATE-BINDING-1 · E5-P0 Refactor Wave · P1-16 HALT-SESSION CROSS-SYMBOL PRICE CORRUPTION ✅（詳 `docs/archive/2026-04-20--claude_md_section3_snapshot.md`） |
| 2026-04-19 | PIPELINE-SLOT-1 Phase 1-4 · E5-P1 Refactor Wave 1 · E5-P2 Refactor Wave 2 · FILL-CONTEXT-LINKAGE-1 · EXIT-FEATURES-TABLE-1 Phase 1b FUP · E5-FN Functional Defects Wave ✅（詳 `docs/archive/2026-04-21--claude_md_section3_snapshot.md`） |
| 2026-04-20 | **EDGE-P2-2 Phase A** ✅ `381c542`（OI confluence signal for `bb_breakout` — 3 新參數 `enable_oi_signal`/`oi_buffer_window_ms`/`oi_confluence_bonus`/`oi_min_delta_pct` + 3 env TOML；E2 對抗性審查 7 findings 全修（#1 buffer dedup / #2 on_rejection preserve / #3 noise floor / #4 validate_oi factory mirror / #5 hot-reload smoke / #6 ts regression guard / #7 unit coverage）；engine lib 1770→**1791** passed；Phase B Liquidation signal 待做） · **LLM-ABC-MIGRATION-1** ✅（5 call-site 切 `local_llm_factory.get_local_llm_client()` — `ai_service.py` / `strategy_wiring.py` / `layer2_engine.py` / `layer2_routes.py` / `layer2_tools.py`；新 `app/local_llm_factory.py` + `LMStudioShimClient` 暴露 OllamaClient-shape 介面回 `OllamaResponse`，call-site parsing 零變動；`LOCAL_LLM_PROVIDER` env 切 `ollama`(default)/`lm_studio`，未知值 fallback Ollama；17 pytest 新測 + 11 既有 patch-target 更新 + 1 訊息文案對齊；business code 0 `import OllamaClient`；**Mac operator 設 `LOCAL_LLM_PROVIDER=lm_studio`+`LM_STUDIO_BASE_URL` 即可不裝 Ollama 跑 Layer 2**；閉合 CLAUDE.md §七「LocalLLMClient 抽象乾淨」既有技術債） |
| 2026-04-21 | **主軸** `TRACK-P-T4-WIRING-1` ✅ `e95c779`（Priority 6 T4 closure 接線 + `build_exit_features_for_tick` pure fn；engine lib 1827→1839；20:44 CEST `--rebuild` runtime 部署）· **DUAL-TRACK-EXIT-1 Phase 1b Track P v2 pure fn** ✅ `aee96b9` · **GATE1-REVERSAL-1 hotfix A** ✅ `d0f0c21` · **EDGE-P2-3 Phase 2+ (b) bb + ma PostOnly entry** ✅ merges `f5f4dc2`+`8280132`（demo/paper=true, live=false）· **outcome_backfiller wiring fix** ✅ `5e2981d`（timeframe `'1'→'1m'` + engine_mode INSERT；歷史回填 ~267k rows）· refactor split 系列 `3a9b988` / `580304a` / `bfedb56` / `d454c17` / `c164cb6` — 全 14 項詳見 `docs/archive/2026-04-21--completed_todo_batch.md` |
| 2026-04-22 | **TICK-PIPELINE-MOD-SPLIT-1** ✅ `3d67a99`（`tick_pipeline/mod.rs` 2274→**1012** 行進 §七 1200 硬上限；impl 拆 3 sibling `pipeline_ctor/pipeline_config/pipeline_helpers`；engine lib 1835 / 0 failed 零變）· **TRACK-P-V2-SWAP-1** ✅ `306993e`（Priority 6 v1 linear → v2 non-linear；`RiskConfig.phys_lock`→`RiskConfig.exit` + `ExitConfig` 熱重載；v1 pure fn + 8 v1 直測整塊退役；20:55 CEST `--rebuild` 部署 engine PID 158918）· Step 0 衍生新 TODO 章節 5/5 ✅ 歸檔 `docs/archive/2026-04-22--step_0_derived_todo_batch.md` |
| 2026-04-23 | **DEDUP-PY-RUST Tier A 收尾 + Tier B Wave A-D 閉環確認** ✅ commits `b4d6a56` + `d39d1b4` + 本 commit（A+B pre-work：刪 `cleanup_legacy_ai_env.py` 95 行 + 裁 `replay_runner.py` 4 個無人用 `_serialize_*` helpers，共減 ~145 行 dead code；Tier A 10 steps 由 subagent 逐檔驗證**全部已 stub**（主 commit `d41f72a` + follow-up `d1e171c` + stub-shape fix `2215bee`，2026-04-16~17），`test_stub_contracts.py` 59 tests 採 RUNNING_OK 模式全綠，contract_check 已清除，`dedup_cleanup_plan.md` header 從「計劃級（尚未動工）」更新為「✅ 已完成」+ 實測效益 ~6700 行淨減；Tier B 盤點發現先前 §三「共 1630 行 · 拆分未完成」敘述**過期**——Wave A-D 實際已將 54 routes 拆至 5 個 sibling legacy_routes，`main_legacy.py` 僅 468 行純基礎設施（singleton + helpers + middleware + 5 行 register_*() 聚合），Tier B 實質閉環；進一步拆 singleton/改名屬 cosmetic 非必要，下游 28 檔 `_base.xxx()` 動態查找為 main.py monkey-patch + 3 個 `importlib.reload(main_legacy)` 測試之契約 — 選 α 結案；純 doc 改動無 Rust/Python 邏輯變更，engine lib baseline 1835 不變） · **INFRA-PREBUILD-1 Part B（Model Registry + Canary 骨架）** ✅ 5 commits `3c3a030`/`91288f1`/`9f6d4c5`/`061cb19`/`01085a6`（B1 V023 migration `learning.model_registry` hypertable + 4 indexes（唯一鍵 + production-latest partial + canary_status + train_date freshness）+ auto-touch trigger；B2 Python `model_registry.py` ~295 LOC + 11 unit tests（`register_model` + `register_quantile_trio_from_onnx_out` wrapper + `transition_canary_status` state machine validator；ON CONFLICT 保 canary_status 不退 shadow + 11 test `test_model_registry.py` 全綠）+ `run_training_pipeline.py` stage 5.5 hook；B3 Rust `ml::registry` 讀 helper + 5 unit tests（`ModelSlot` Hash/Eq + `resolve_latest_production_artifact` async fn + `symlink_filename` 命名對齊 Python + `log_registry_failure` warn-log wrapper；OnnxModelManager 不動，Phase 3+ 整合）；B4 IPC SKIP（Rust 端無 live consumer，Python 直查 DB 更乾淨）；B5 `/api/v1/ml/{model_registry|model_info|model_promote}` routes（list + single-slot resolver + Operator-gate 狀態機 promote，irreversible 轉移需 `confirm:true` + `retirement_reason`）；B6 canary rules draft `docs/references/2026-04-23--model_canary_promotion_rules_draft.md`（狀態機 + 每 Phase 晉升閾值 + Operator playbook + Phase 4 auto-promote cron 延後）；B7 healthcheck [9] `check_model_registry_freshness`（per-slot oldest train_date 30d/60d 閾值 + Phase 1a/2 empty PASS note）；Phase 1a runtime 零影響（registry 空；所有 routes 回 404 / rows=0 直到訓練 pipeline 寫入第一行，P1-7 C labels 47/200 還在累積）；engine lib **1910 passed**（Part A 1905 + B3 5 registry tests）；operator 下一步 = labels 滿 200 跑 `run_training_pipeline.py` 觀察 registry 自動填入 → 人工評估 → `POST /model_promote` 狀態推進） · **INFRA-PREBUILD-1 Part A（Combine Layer shadow 骨架）** ✅ 5 commits `6226b38`/`419bd34`/`83ece53`/`66b061f`/`74b678a`（A1 V021 migration：`trading.fills.exit_source` 欄位 + partial index + `learning.decision_shadow_exits` hypertable 4 indexes；A2 `shadow_exit_writer.rs` + `ShadowExitMsg` + tasks.rs 8-tuple + main.rs 3× EventConsumerDeps 接線 + pipeline setter/accessor；A3 `combine_layer::build_ml_inference_shadow` mock producer + `helpers::emit_shadow_exit_observation` sibling fn 走 combine_exit_decision 兩次比對 disagreed + try_send shadow exit msg；A4 `TradingMsg::Fill.exit_source Option<String>` + trading_writer INSERT V017→V021 欄位升 + 6 construction sites + emit_close_fill 從 close_tag 經 `strip_phys_lock_prefix` 推 Physical tag（避 RUST-DOUBLE-PREFIX-1 regression）；A5 `ExitConfig.shadow_enabled` bool flag + 3 env TOML；A6 passive_wait_healthcheck [8] `check_shadow_exit_ratio` silent-dead guard，Phase 1a dormant 與 Phase 2+ silent-dead 藉 row count/rowcount breakdown 三角檢；Phase 1a runtime 全 dormant（flag OFF → 0 emit、0 row、fills.exit_source 除 PHYS-LOCK 外全 NULL）；Phase 2 啟動 = operator 改 TOML 或 IPC patch_risk_config flip `shadow_enabled=true`，無須 rebuild；engine lib **1905 passed**（+70 vs 1835 baseline）；後續 Part B = Model Registry + Canary deployment 基礎設施） · **DEDUP-PY-RUST 獨立重審全鏈閉環 A+B+C+D** ✅ 5 commits（A 刪 `program_code/governance/` 7 檔 284 行 `87e3ecf` · B docs-only canonical path note 清理 `16acb64` · C 前半 Rust `bybit_private_ws_status_writer.rs` +664 行含 11 單測 + `ExecutionListener.stats_arc()` 曝露 + `spawn_private_ws_supervisor` Demo/LiveDemo 條件 spawn `b9b0a57` · C 後半 Python `bybit_private_ws_listener.py` + 2 `_ctl.sh` 共 3 檔 340 行刪除 `b5cf59e` · D 刪 `helper_scripts/maintenance_scripts/bybit_connector/` 53 個 legacy H/I/J/K-chain 修復 shell + `program_code/.../scripts/` 45 個對應 shim wrapper 共 98 檔 `f42face`）；3 並行 Explore sub-agent 獨立核實 + 主會話交叉驗證修正 Agent 1 對 `local_model_tools/` 19 個 singleton-contract stub 的誤刪判斷 + Agent C「Rust never spawned」誤判（實際 `startup.rs:872` 已 spawn）；2026-04-23 21:13 CEST `--rebuild` 後 Rust writer 接管 status JSON 產生（`listener_version: "rust-v1"`）、`pkill -f bybit_private_ws_listener.py` exit=1（Python 進程早已不跑）、observer pipeline smoke 通過；SCRIPT_INDEX.md + LOGICAL_SCRIPT_CATEGORY_MAP.md + `helper_scripts/SCRIPT_INDEX.md` 同步更新；engine lib 本 session 我貢獻 +11（writer tests），與 operator Part A/B 合計達 **1910 passed**；淨減行數 Rust +685 / Python/shell -12.8k（98 shells + 3 retire + 7 governance 合計）；報告 `.claude_reports/20260423_200043_dedup_fresh_audit_A_governance_delete.md` + `.claude_reports/20260423_202943_dedup_fresh_audit_BC_ws_retire.md`） |

**歷史細節指針**（不要重複載入）：
- §三 2026-04-16 STABILITY-1/LIVE-GUARD-1 + 2026-04-19 完整敘述 → `docs/archive/2026-04-21--claude_md_section3_snapshot.md`
- §三 2026-04-17/18 完整敘述 → `docs/archive/2026-04-20--claude_md_section3_snapshot.md`
- §三 2026-04-15 之前完整敘述 → `docs/archive/2026-04-15--claude_md_section3_snapshot.md`
- 1A→1C-4 commit 敘事 → `docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`
- Phase 0-4 Sprint/Wave → `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`
- 逐 commit 行數 → `docs/CLAUDE_CHANGELOG.md`
- 1C-3/1C-4 narrative → `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

---

## 四、硬邊界（永遠不能違背）

```python
# ── Live_Ready 真實狀態 ──
# LIVE-P0/P1/P2 代碼完整（SM-01/02/04 + Reconciler + 3E-ARCH），0 真實 live 流量
# （歷史 43k 條 engine_mode="live" 實為 LiveDemo）。

# 真實 live 門控（Rust 端可驗證 = 4 項 / 全部 = 5 項）：
#   1. Python `live_reserved` global mode           （Python 側，重啟會丟）
#   2. Python Operator 角色 auth                    （Python 側）
#   3. OPENCLAW_ALLOW_MAINNET=1 env var             （Rust 側，僅 Mainnet）
#   4. secret slot 有 api_key + api_secret          （Rust 側，憑證空 → Err；
#        Mainnet env-var fallback 封閉，來源優先級見 bybit_rest_client.rs:386-497）
#   5. authorization.json 簽名+未過期+env_allowed 匹配  （Rust 側，HMAC-SHA256）
#        路徑：$OPENCLAW_SECRETS_DIR/live/authorization.json
#        檢查點：build_exchange_pipeline 啟動 + main.rs 每 5 min re-verify
#        失效 → engine 優雅 shutdown（cancel_token）
#        涵蓋 LiveDemo + Mainnet（LiveDemo 不因 api-demo endpoint 降級）
#        **必經** Python renew/approve 路由 `_write_signed_live_authorization()`，不可手動寫

# execution_authority：Rust 僅為 P0/P1 denylist 字串常量
# （claude_teacher/applier.rs:226），非真實授權邏輯；「auto_granted_on_start」屬 Python 概念。
decision_lease_emitted  = False
max_retries             = 0

# 永不允許的硬錯誤：
# - 繞過 Operator 角色認證或 live_reserved 直接啟動 live session
# - 自動修改 engine trading_mode 為 live（需 operator 顯式配置）
# - Bybit API timeout / retCode != 0 → fail-closed，不重試
# - should_call_ai=true 但 invocation 沒發生；偽造 AI 調用或交易活動
# - Mainnet 下無 OPENCLAW_ALLOW_MAINNET=1，或用 env var 當唯一憑證來源
# - Live（含 LiveDemo）下無有效 authorization.json 即 spawn pipeline
```

---

## 五、架構總覽

```
[數據與觀察層]           Bybit REST + WS → Postgres + Observer
[H0 本地判斷內核]        freshness / health / eligibility / risk envelope（<1ms SLA）
[GovernanceHub]          SM-01 授權 + SM-04 風控 + SM-02 租約 + EX-04 對賬
[H1-H5 AI 治理層]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 209 /api/v1 + 11 non-api 路由（2026-04-16 audit 實測）
[GUI + Learning]         11-Tab 控制台 + Learning Cockpit + Paper Trading Dashboard
[Rust openclaw_engine]   paper / demo / live 三模式唯一引擎（1C-3-F 後）
                         tick pipeline + IntentProcessor + paper_state + governance + stop_manager
[Layer 2 AI 推理]        L0 確定性 → L1 Ollama → L2 Claude
[風控框架]               P0/P1/P2 三層 + 對抗性止損 + AI 注意力稅
[策略工具包]             KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator
[管線橋接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate
[止損管理器]             StopManager: Hard/Trailing/Time Stop + ATR 動態倉位
```

---

## 六、路徑與啟動

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作樹:   由 $OPENCLAW_BASE_DIR 決定（repo 任意絕對路徑皆可）
                Linux 預設: $HOME/BybitOpenClaw/srv（/home/ncyu/srv ← symlink, legacy）
                Mac   範例: /Users/ncyu/Documents/Projects/TradeBot（或 $HOME/BybitOpenClaw/srv）
本地-only：     settings/（secrets）  trading_services/（runtime）
```

### 跨平台 Runtime 路徑（Mac/Linux 共用）
**Mac dev 必設**（Linux 上可選，默認 `/tmp/openclaw` + `$HOME/BybitOpenClaw/`）：
```bash
# Repo 位置（任意路徑皆可，例如 /Users/ncyu/Documents/Projects/TradeBot）
export OPENCLAW_BASE_DIR="/Users/ncyu/Documents/Projects/TradeBot"

# Runtime / socket / log 目錄（Mac /tmp 是 /private/tmp symlink，必須顯式設）
export OPENCLAW_DATA_DIR="$HOME/.openclaw_runtime"

# Secrets 根目錄（含 environment_files/ + secret_files/）
export OPENCLAW_SECRETS_ROOT="$HOME/.openclaw_secrets"

# Bybit slot base（Rust/Python 專用，= $SECRETS_ROOT/secret_files/bybit）
export OPENCLAW_SECRETS_DIR="$HOME/.openclaw_secrets/secret_files/bybit"

# 歸檔目錄（clean_restart / fresh_start 寫入）
export OPENCLAW_ARCHIVE_DIR="$HOME/.openclaw_archive"

mkdir -p "$OPENCLAW_DATA_DIR" "$OPENCLAW_SECRETS_ROOT/environment_files" \
         "$OPENCLAW_SECRETS_ROOT/secret_files/bybit" "$OPENCLAW_ARCHIVE_DIR"
```
原因：Mac `/tmp` 是 `/private/tmp` symlink 且 LaunchAgents 看到不同路徑；Mac 上跑 pytest、`restart_all.sh`、IPC socket 都必須走 `$OPENCLAW_DATA_DIR`。Linux 上不設時 fallback 到 `/tmp/openclaw` + `$HOME/BybitOpenClaw/{secrets,archive}`，行為不變。

**env var 語義速查**：
| env var | 指向 | 誰在讀 |
|---|---|---|
| `OPENCLAW_BASE_DIR` | repo 根（srv） | Rust `startup.rs` / `strategies` · Python 多處 · `start_paper_trading.sh` |
| `OPENCLAW_DATA_DIR` | runtime（sockets / logs / flags / snapshot） | Rust engine · API · scripts |
| `OPENCLAW_SECRETS_ROOT` | secrets/ 根（含 env_files + secret_files） | shell scripts（restart/clean/fresh） |
| `OPENCLAW_SECRETS_DIR` | secrets/secret_files/bybit（slot base） | Rust `bybit_rest_client` · Python `bybit_rest_client.py` · live_auth |
| `OPENCLAW_ARCHIVE_DIR` | archive（damaged_/fresh_start_ dumps） | clean_restart / fresh_start |
| `OPENCLAW_SRV_ROOT` | ⚠️ legacy alias，同 `OPENCLAW_BASE_DIR` | `bybit_path_policy.py` + 115 歷史 maintenance scripts — **新代碼請用 `OPENCLAW_BASE_DIR`**，兩者互不 fallback，Mac 部署時建議 `export` 同值 |

**Mac 差異注意**：`$HOME/.openclaw_runtime` **不會**在開機時被清（Linux `/tmp` 每次重啟清空），因此：
- `engine_maintenance.flag` 若上次異常留下會阻塞 watchdog → 開工前先 `rm -f "$OPENCLAW_DATA_DIR/engine_maintenance.flag"`
- 舊 socket 檔（`engine.sock` / `ai_service.sock`）殘留會讓新 process 拒綁 → 啟動前清或讓腳本 unlink 舊 socket
- 建議 Mac `.zshrc` 加 `alias oc-clean-runtime='rm -f "$OPENCLAW_DATA_DIR"/{*.sock,engine_maintenance.flag}'`

### 啟動檢查（每次 session 起點）

**Linux 端（trade-core 本地 session）**：
```bash
git status && git log --oneline -5
python3 helper_scripts/canary/engine_watchdog.py --data-dir "$OPENCLAW_DATA_DIR" --stale-threshold 45 --grace-period 120 --status
```

**Mac 端（SSH bridge workflow，2026-04-21 起）**：
```bash
git status && git log --oneline -5                                    # Mac 本地 repo 狀態
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -5"       # Linux repo 狀態（可能領先）
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status"  # engine 真實狀態
```
Mac 本地跑 watchdog 永遠回 `engine_alive: false`（engine 只跑 Linux，見 `memory/project_dev_runtime_split.md`）；必須透過 ssh 查。Mac 接手三連 = git status + ssh Linux git log + ssh Linux watchdog。

R-07 Go/No-Go 已 PASS（見 `memory/archive/project_rust_migration_status.md`）。watchdog 回 `engine_alive: false` 代表引擎沒在跑，按 TODO.md 重啟指引處理（Mac 端：`ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"`）。

### TODO.md 強制規則（每次接手必須遵守）

**接手時：** 必須讀 `TODO.md` 確認當前工作狀態，找第一個 `[ ]` 未完成項作為起點。用戶有明確指令時以用戶為準。

**發現新問題時：** 立即追加到 TODO.md，不等會話結束。

**修復完成後：** `[ ]` → `[x]`，追加完成 commit 號，更新測試基準線。

---

## 七、代碼與文檔規範

### ★★ 跨平台兼容性（強制，所有開發必須遵守）

**大前提：項目必須隨時可以部署在 macOS 上運行。**

1. **路徑不硬編碼** — 所有路徑使用環境變量或 config，禁止任何 user-home 絕對路徑字面值（`/home/ncyu/`、`/Users/ncyu/`、`/Users/<name>/…/TradeBot` 等）。
   用 `os.environ.get("OPENCLAW_BASE_DIR", ...)`、docker-compose 相對路徑（`../../settings/...`），或 `Path(__file__).parent` 相對路徑。
   E2 必查：`grep -E '(/home/ncyu|/Users/[^/]+)' <diff>` 新代碼命中 → 打回（歷史 worklog / dated snapshot / 政策反例引用不在此限）。

2. **LocalLLMClient 抽象乾淨** — 不洩漏 Ollama-specific 細節。
   所有 LLM 調用通過 `LocalLLMClient` ABC 接口（Phase 1 任務 1.8）。
   禁止在業務邏輯中直接調用 Ollama HTTP endpoint。

3. **服務部署可遷移** — systemd → launchd 遷移路徑清晰。
   服務配置邏輯寫成文檔或腳本（`helper_scripts/deploy/`）。
   不依賴 systemd-specific 特性（如 `sd_notify`）。

4. **依賴管理乾淨** — `requirements.txt` 保持更新，禁止隱式依賴。
   新增 `import` 時同步更新 requirements。E2 必查。
   避免 Linux-only 依賴（如 `psutil` 的 Linux 特定 API），需要時加平台守衛。

### 雙語注釋（強制）
每個新建/修改的函數、類、模塊必須中英對照注釋（MODULE_NOTE / docstring / inline / fail-closed 路徑 / 安全代碼）。E2 必查。

### 新 SQL migration 規範（強制，2026-04-24 V023 postmortem 新增）

**背景**：2026-04-23 `V023__model_registry.sql` 入 repo 但在 Linux 上**靜默 no-op** —— V004 早已預建了缺 `canary_status/verdict` 的 legacy `learning.model_registry` stub；`CREATE TABLE IF NOT EXISTS` 看到表存在就跳過，下游 Rust 讀 `canary_status` 全空。`helper_scripts/db/audit_migrations.py` 事後才能抓到。**更好的防線是 migration 內的 DO block guard，對 legacy drift 主動 RAISE**。

**規則**（4 條，E2 必查）：
1. **Guard A 強制**：任何 `CREATE TABLE IF NOT EXISTS schema.table (...)` **前必加**一個 DO block，驗表若已存在則必要欄位俱在；缺 ≥1 即 `RAISE EXCEPTION`。模板見 `sql/migrations/templates/schema_guard_template.sql § Guard A`。
2. **Guard B 強制（型別 matters 時）**：`ALTER TABLE ... ADD COLUMN IF NOT EXISTS col TYPE` 前，若該 column 類型錯會讓下游 writer 失敗，**必加** Guard B 驗 `information_schema.columns.data_type`；型別不符即 RAISE。模板同檔 § Guard B。
3. **Guard C（hot-path 索引選用）**：`CREATE INDEX IF NOT EXISTS` 若索引欄位組合關鍵（production 熱查詢依賴），加 Guard C 比對 `pg_get_indexdef()`；純 audit / 低頻索引可略。
4. **Idempotency 驗證**：每個新 migration 本地跑兩次 `psql -f V<NNN>__<desc>.sql`，第二次必須**不 RAISE**（shape 已正確時 guard no-op）。違反 = E2 打回。
5. **範例** retrofit：`sql/migrations/V023__model_registry.sql`（Guard A `learning.model_registry`）+ `sql/migrations/V021__fills_exit_source.sql`（Guard A `learning.decision_shadow_exits` + Guard B `trading.fills.exit_source` + Guard B `learning.decision_shadow_exits.ts`）。新 migration 以此兩檔為 reference。

**測試**：`sql/migrations/tests/test_schema_guards.sql` 提供 9 個單測（3 guard × {pass / fail / no-op}），無 pgTAP infra 下直接 `psql -d <test_db> -f` 跑；grep NOTICE 無 `FAIL` 即綠。

### Engine 自動遷移（opt-in，2026-04-24 Phase 2 新增）

**背景**：V023/V019/V021 silent-noop postmortem 顯示 100% 手動 `psql < V*.sql` 會漏套用。Phase 2 在 `openclaw_engine` 啟動時加一條 opt-in 自動遷移管線，**預設關**，operator 逐步驗證後再開。

**兩條套用路徑並存**：
- **手動（預設）**：`bash helper_scripts/linux_bootstrap_db.sh --apply` — 既有流程不動，此 Phase 不移除。
- **自動（opt-in）**：環境變數 `OPENCLAW_AUTO_MIGRATE=1` 時，engine 啟動在 DbPool 連線後、writer 啟動前呼叫 `openclaw_engine::database::migrations::MigrationRunner::run_if_enabled()`：
  1. 自刻 parser 讀 `sql/migrations/V###__*.sql`（sqlx 內建 parser 不吃 Flyway 格式）；`V017_rollback.sql` / `V999__*.sql` 依檔名過濾。
  2. 若 `_sqlx_migrations` 空且 `learning.model_registry` 存在（V023 canary），seed V001-V023 為「已套用」狀態 — 符合 2026-04-24 postmortem 後的 live DB 狀態。
  3. 跑 `Migrator::run_direct` 套用 pending（目前無，V024+ 時才會有）；checksum 比對失敗 / 曖昧狀態 / canary 不成立 → 中止啟動（`exit 1`），**不靜默吞**。
- **安全準則**：ambiguous state（有 app schema 但無 V023 canary）= 硬性 RAISE，不自動猜測；operator 跑 `helper_scripts/db/audit_migrations.py` 後人工介入。

**Rollback path（engine refuse to start）**：若 `OPENCLAW_AUTO_MIGRATE=1` 打開後 engine 不肯啟動，operator 立即：
1. Stop engine（`restart_all.sh --stop`）。
2. 關 env：`unset OPENCLAW_AUTO_MIGRATE` 或 env file 改回空。
3. 回到手動流程 `bash helper_scripts/linux_bootstrap_db.sh --apply` 補任何 pending migration。
4. 重啟 engine（`--rebuild` 非必要，除非改了 Rust 碼）。

**測試**：`rust/openclaw_engine/src/database/migrations.rs` 15 個 unit tests（純解析 / 無 DB）+ `rust/openclaw_engine/tests/migrations_test.rs` 5 個整合測試（需 `OPENCLAW_TEST_PG` 連線字串；無則自動跳過；`fresh_db_applies_all_migrations_end_to_end` 另需 `OPENCLAW_TEST_PG_DESTRUCTIVE=1` ack）。

### 被動等待 TODO 必附 healthcheck（強制，2026-04-23 新增）

**背景**：2026-04-22 P0-13 ATR scale + P0-14 edge miss 雙 bug 經「被動等待 24h observation」流程放行；後續 review 才發現 7d `phys_lock` 0 fire 其實是 silent-dead，observation window 本身無法偵測。結論：**任何「被動等待 Nd / Nw」的 TODO 必須同步附一條可執行 healthcheck**，由 cron 或 operator 手動間隔跑，確認被動等待的前提（pipeline 活著 / 信號流通 / fires 發生中）仍成立。缺此項 = 無法區分「沒事所以沒動」vs「壞了所以沒動」。

**規則**（4 條，E2 必查）：
1. **登記門檻**：TODO 新增「被動等待 Nd / Nw」類條目時，必須同時：(a) 在 `helper_scripts/db/passive_wait_healthcheck.py` 加一個 `check_*()` function（通常 1 SQL or 1 oneliner）;(b) TODO 文本引用該 check id。
2. **檢查語意**：check 回 `"PASS" / "WARN" / "FAIL"`，**Exit 1 = silent-dead 自動偵測** — 不是「沒資料」就 PASS。若被動等待假設「每 N 小時該有 ≥1 次 fire」，check 就要驗 fire count ≥ 1 and ts > now() - N hours。
3. **節奏建議**：operator 每 6h cron 跑 `passive_wait_healthcheck.py`，任一 FAIL 即檢查該 TODO 的前提是否仍成立。本檔已有 7 個 check（close_fills / label_backfill / exit_features_writer / phys_lock / micro_profit / trailing_stop / edge_estimates freshness），新增按此樣式追加即可。
4. **違規處理**：新增被動等待 TODO 未附 healthcheck = E2 審查打回；已有被動等待 TODO 若對應 pipeline 沒 healthcheck 覆蓋 = 下一輪維護週期必補。

**觸發情境例**：
- 「等 21d demo 穩定」→ check：demo engine_alive last 24h + 0 engine_crash 次數
- 「等 7d counterfactual replay」→ check：replay 結果檔存在且 mtime > script last run
- 「等 1w PostOnly fee 驗證」→ check：maker fill rate > X% 且 demo fee 降幅達標

### 強制同步規則
- **Sprint/Wave 完成**：更新 §三 + §十一 + `docs/CLAUDE_CHANGELOG.md` + README，與生產代碼同 commit
- **§三 衛生規則（強制）**：§三 只記載「現況/活躍狀態」+「過去 ≤2 天的完成里程碑」。**任何完成里程碑當天 +2 日（以 `currentDate` 為準）必須在 commit 同次操作中歸檔到 `docs/archive/YYYY-MM-DD--claude_md_section3_*.md`** 並從 §三 刪除，僅在「已完成里程碑索引」表保留 1 行條目。違反 = §三 膨脹回 ~10K tokens、context 提早撞 compact。
- **Commit 時**：摘要追加到 `docs/CLAUDE_CHANGELOG.md` 頂部，格式 `### 標題（YYYY-MM-DD · commit XXXXXXX）`
- **Context ≥90%**：立即寫 `docs/worklogs/YYYY-MM-DD--session_progress_N.md`（已完成/進行中/未完成/決策/下一步）
- **每日整合**：當天 worklog 碎片合併為 `YYYY-MM-DD--daily_summary.md`，刪碎片
- **新腳本**：MODULE_NOTE 雙語 + latest+dated 輸出 + contract check + 更新 SCRIPT_INDEX.md
- **docs/**：分類目錄 + `YYYY-MM-DD--描述.md` + 更新 `docs/README.md` 索引

### 本地 LLM 審核協作（Mac 環境，強制）

Operator 在 Mac 並行跑 Qwen3.6-35B（LM Studio）做代碼審核。CC 每完成一個任務，必寫結構化報告至：

    .claude_reports/YYYYMMDD_HHMMSS_<短描述>.md

（`.claude_reports/` 在 `.gitignore`，僅本機留存；供本地 LLM 審核 + 開發編年史 — 與 `docs/worklogs/` 職能互補：worklog 是會話時序流水，claude_report 是單任務審核單位）

**6 節必備**（中文，繁簡皆可）：
1. **任務摘要** — operator 意圖白話重述 + 完成狀態
2. **修改清單** — 逐檔 `path | 新增/修改/刪除 | 行數 | 一句話說明`
3. **關鍵 diff** — 最能說明變更的片段（非全量）
4. **治理對照** — 涉及的 DOC/SM/EX/P0 編號 + 符合 / 違反 / 未規範 / 建議修改文件
5. **不確定之處** — 未確認假設 / 跨平台風險（對照 §七.★★）/ 測試覆蓋判斷
6. **Operator 下一步** — 審查重點 / Mac CC 透過 SSH bridge 已做的驗證（cargo test / psql / engine log）/ 若需 operator 親自動手的步驟（high-risk per-case 授權項 / Linux 端 interactive 操作）

**Git 自動化（強制，2026-04-21 operator 加嚴：所有 commit 必 push）**：
- CC 每完成一個**合理可交付單位**（任務完成 + 本節 report 已寫 + 無跑不過的測試）→ 自動 `git add` + `git commit` + **`git push origin main`**（三者同 Bash 鏈內完成，不允許 commit 後留著沒 push 就結束回合）
- **無例外**：Mac CC / Linux CC 都遵守「commit 即 push」；維持 Mac / Linux / origin 三處 state 一致性
- **Session 接手三連 sync**（所有 CC 起手必做）：`git fetch --prune origin` + 若 local 落後 `git pull --ff-only` + 若 local 超前（前 session 漏 push）`git push origin main` —— 例行自動做，不待 operator 提醒
- **Mac CC 觸發 Linux 驗證前**：push 完接 `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"` 同步 Linux 工作樹
- **ff-only pull 失敗（divergent branches）**：報告 operator，不擅自 merge/rebase（CC 本地規則仍禁這 3 op）
- 詳 memory `project_ssh_bridge_workflow.md`「硬規則：commit 完必 push」章節
- **CC 絕不執行**：`pull` / `merge` / `checkout` / `reset` / `rebase`（狀態變更操作留給 operator）

### Mac dev-only 模式（環境檢測 + 操作細節）

**環境檢測**：CC 從 system prompt `Platform:` 讀取，**不分大小寫**做子串比對：含 `darwin` → Mac dev-only · 含 `linux` → trade-core 生產（Linux session 實測回 `Linux`，Mac 回 `darwin`）。下面 4 條僅在 Mac 端生效，**不必詢問 operator**。

1. **pytest 必從 srv root 跑** — 部分測試用絕對 import `from program_code.…`，從 `control_api_v1/` 內跑會 `ImportError: No module named 'program_code'`（例：`test_earned_trust_engine.py`）。
2. **整合測試打真實 Bybit 會 fail —— by design** — 3 個 secret slot 已 rename 為 `*.dev_disabled_*`（避免與 Linux trade-core 撞單；還原見 README § Mac dev-only 模式）。任何 connect 真實 Bybit 的 test 拿不到 credentials → fail-closed。Mock-based unit test 不受影響。**Reproduce release 基準**（engine lib 1827 / 0 failed 等）現可 `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"` 直驗，不需要離開 Mac session。
3. **Sub-agent (E1) 寫碼若 refuse** — Linux 端 2026-04-19「第 3 次驗證解除」refuse pattern，但跨平台/跨 session 仍偶發。Workaround：主 session 直接寫。
4. **Mac↔Linux SSH bridge workflow（2026-04-21 採納，取代原「同步單向」）** — 詳 memory `project_ssh_bridge_workflow.md`。核心：Mac CC 為 SSOT，透過 `ssh trade-core`（Tailscale + key auth，免密碼）遠端觸發 Linux runtime 任務（cargo test / psql / restart_all / git 操作 / engine log）。
   - ✅ **Mac 本地 git 放寬**：允許 `git fetch` + `git pull --ff-only`（純 fast-forward，衝突時 abort 不破壞 state）；**仍禁** `git merge <branch>` / `rebase` / `reset --hard` / `checkout <branch>`
   - ✅ **SSH 允許**：ssh trade-core 跑 cargo/psql/git pull&push/restart_all/tail log/watchdog/rm tmp sentinel
   - 🚫 **SSH 需 operator per-case 授權**：觸及 live API/authorization.json/secrets、刪 remote branch（本 session 已試 trigger guardrail 成功擋住）、刪 worktree、DROP/TRUNCATE table 資料、改 risk_config TOML
   - **工作流**：Mac 寫碼 → `git add/commit/push` → `ssh trade-core "git pull --ff-only && cargo test --release"` → 看結果 → 綠就完成，紅就回頭 fix。**不再派 Linux CC 做寫 prompt 的 round-trip**（除非需要 interactive rebase/amend 等 Mac CC 禁做的動作）。
   - **Linux CC 剩餘職能**：24h 守夜監控、interactive git 操作、operator 急令 hotfix、Mac CC 離線時兜底。

---

## 八、工作流編排、16 Agent 角色與自我改進循環

### ★ 工作流編排 6 條 + 3 底線（2026-04-22 operator 指令融合）

1. **規劃優先 Plan-First**：非平凡任務（≥3 步 / 涉架構決策）先進規劃模式再動手；前期寫詳細 spec 減歧義；過程遇阻即停重規劃，**禁強推**；驗證階段同樣套規劃節點。Auto mode 下放寬「開工前 operator confirm」，但規劃思考仍要做。
2. **Sub-agent 卸載**：研究/探索/並行分析一律派 sub-agent 保主上下文整潔；一 agent 一任務精準執行；複雜問題投更多算力。詳 memory `feedback_subagent_first.md`。
3. **自我改進循環**：operator 任何糾正 → 抽模式寫 `docs/lessons.md`（場景 / 錯誤模式 / 預防規則 / 相關檔案）；會話起手掃近期相關條目；對錯誤率無情迭代。lessons.md = 可 grep 技術/流程錯誤庫，與 auto-memory `feedback_*.md`（跨 session 偏好）互補不重複。
4. **完成前驗證 Verify-Before-Done**：永不先標 done；跑測試 / 查 log / 對比 main 分支行為差 / 自問「senior engineer + FA 會 approve 嗎？」。強化既有 E2/E4 + memory `feedback_working_principles.md` 原則 3 對抗性驗證。
5. **追求優雅（平衡）**：非平凡修改前停問「有更優雅方式嗎？」；修復像 patch 就重做「基於現在所知一切實作優雅解」；**簡單/明顯修復跳過本條禁過度設計**。
6. **自主 bug 修復**：收到 bug 直接修；指 log/錯誤/失敗測試再解；CI 紅直接修不等手把手；operator 零上下文切換。詳 memory `feedback_minimal_confirmation.md`。

**3 條核心底線**：**簡單優先**（只動必要代碼，禁無關重構） · **不偷懶**（找 root cause，禁臨時 patch，senior/FA 標準） · **最小影響**（變更只觸必要部分，禁引 bug）。

**會話任務管理 6 步**（與 §六 TODO.md 強制規則同體，流程化版）：1) TODO.md 先寫 checkbox 計畫 → 2) 開工前 operator confirm（auto mode 跳過）→ 3) 逐步勾選進度 → 4) 每步高階摘要 → 5) TODO.md 結尾補 Review 章節 → 6) 任何糾正後寫入 `docs/lessons.md`。

### 16 Agent 角色體系與強制工作鏈

**強制**：所有任務按角色派發，主會話 = PM+Conductor。完整角色定義/激活矩陣見 `docs/CLAUDE_REFERENCE.md`。

**標準鏈**：PM+FA → PA 派發 → E1/E1a 並行 → **E2 代碼審查 → E4 測試回歸**（兩者絕不可跳）→ E5 優化（每 Phase/Wave/≥3 E1 任務強制）→ QA → PM 確認。E3/CC/A3/R4/TW 按需。
**P0 快速通道**：PA → E1 並行（≤5）→ E2 → E4 → PM。

**Bybit API 強制**：所有 Bybit 相關開發（REST/WS/IPC）先查字典手冊 `docs/references/2026-04-04--bybit_api_reference.md`，新增端點同步更新手冊，E2 必查。審計：`docs/audits/2026-04-04--bybit_api_infra_audit.md`。

---

## 九、代碼結構約定

### 文件大小限制
- **800 行** ⚠️ 警告線（E2 必須標記）
- **1200 行** 🛑 硬上限（不允許 merge）

### 模塊依賴方向（禁止循環 import）
```
state_models ← state_compiler ← state_store ← main_legacy ← main.py
其他 route 文件 ← main_legacy（通過 from . import main_legacy as base）
```

### Monkey-patch 安全
被 main.py patch 的函數（compile_state / STORE / envelope_response 等），新模塊必須通過 `main_legacy` 命名空間間接引用，不可直接 import 原始版本。

### Singleton 管理
| Singleton | 創建位置 | 導入方式 |
|-----------|---------|---------|
| `settings` | main_legacy.py | `base.settings` |
| `STORE` | main_legacy.py（main.py 重建） | `base.STORE` |
| `app` | main_legacy.py | `base.app` |
| `limiter` | main_legacy.py | `base.limiter` |
| `_pool` | db_pool.py | `from .db_pool import get_conn` |
| `DEFAULT_LEASE_TTL_CONFIG` | lease_ttl_config.py | `from .lease_ttl_config import DEFAULT_LEASE_TTL_CONFIG` |
| `_backtest_engine` | backtest_routes.py | 內部懶加載 `_get_backtest_engine()` |
| `_scheduler` | evolution_auto_scheduler.py | 內部懶加載 `start_scheduler()` |
| `_evolution_engine` | evolution_routes.py | 內部懶加載 `get_evolution_engine()` |
| `_ledger` | experiment_routes.py | 內部懶加載 `get_experiment_ledger()` |
| `LeaseTTLConfigManager._instance` | lease_ttl_config.py | `LeaseTTLConfigManager.get_instance()` |
| `_BYBIT_CLIENT` / `_BYBIT_CLIENT_AVAILABLE` | strategy_ai_routes.py | 內部懶加載 `_get_rust_client()`（PYO3-ELIMINATE-1 Phase 2 後指向 `app.bybit_rest_client.BybitClient` 純 httpx；函數名為 grep-stability 保留） |
| `KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` 等 12+ | strategy_wiring.py | 模組級全局，import 時初始化 |
| `_SHARED_IPC_SLOTS` / `_SHARED_SLOT_LOCK` | ipc_dispatch.py | 內部懶加載 `get_or_connect_shared_client(slot_key)`（E5-P1-5） |
| `_<AGENT>_AUDIT_CB` / `_GOV_HUB_FOR_<AGENT>` × 5（Scout/Strategist/Guardian/Analyst/Executor） | strategy_wiring.py | 模組級，由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造；各 agent ctor 注入 `audit_callback`（E5-FN-3 Analyst pilot + FN-3-FUP-a~d 4 agents 補接線）。ImportError 時 GOV_HUB=None → bridge fail-open 靜默丟事件。`agent_audit_bridge` 本身無狀態工廠（不持 singleton） |
| `_scheduler` / `_scheduler_lock` | edge_estimator_scheduler.py | 內部懶加載 `start_scheduler()`（P1-7 B JS estimator，每小時 cycle）。QC-3 audit FUP 補登（2026-04-23） |
| `_LEADER_LOCK_FD` / `_LEADER_LOCK_PATH` | edge_estimator_scheduler.py | 模組級全局；`_acquire_leader_lock()` 取得 flock fd 後寫入，OS 進程退出自動釋放（含 SIGKILL）。uvicorn --workers 4 leader election sentinel。測試用 `_reset_for_tests()` 釋放。EDGE-SCHEDULER-LEADER-1（2026-04-23 `f32629c`）|

新增 singleton 必須在此表登記。禁止子模塊創建未登記的全局可變狀態。

### 其他
- Route Handler 只做 parse → call → format，不含業務邏輯
- 新 Pydantic model 放 `*_models.py` 或所屬模塊，不加入 main_legacy.py

---

## 十、下一步工作指針

**當前焦點**：活躍任務與週次排期以 `TODO.md` 為準（P0/P1/P2/P3/P4 分層）。CLAUDE.md 不重複列週。

**關鍵路徑（2026-04-16 夜 audit 刷新 v3，P0-9 停電 RCA 後）**：
`P0-0 ✅ → P0-4 R1 ✅ → ~~LIVE-GUARD-1 Rust fail-safe~~ ✅ → ~~P0-9 STABILITY-1~~ ✅（停電基礎設施事件，非 code bug）→ P0-6 intent write gap → P0-7 order submit gap → P0-3 Phase 5 edge 2w 重評 + P0-2 LG-1 21d demo → P1-7 LEARNING-PIPELINE-DORMANT-1 → LG-4/5 → Live`
- P0-1 G-2（funding_arb 子集驗證）與 P0-5 PHANTOM-2-FUP 均**不在主路徑**
- P0-6/P0-7 若揭露架構級 DB write path 斷裂，Live 日期可能延後
- P1-7 LEARNING-PIPELINE-DORMANT-1 不阻 live 但阻 Phase 5 edge 收斂
- **最早 Live 日期**：**W24 末（～2026-05-23）**（P0-9 停電 RCA 後不延後，不重置 21d 時鐘）

**路線圖**：Phase 0-5 ✅ · Live GUI ✅ · Phase 6 ✅ · **AI 治理層 (W22-W23) 🟡 部分 live**（**2026-04-23 audit 更正**：H1-H5 AI middleware 與 5-Agent 代碼**並非 stub** — `h1_thought_gate.py` 185 行 / `model_router.py` 292 行 / `h4_validator.py` 103 行 / `layer2_{engine,routes,tools,cost_tracker,types}.py` 全實作。5-Agent 總計 ~4552 行（strategist 1170 / guardian 587 / analyst 834 / executor 630 / scout 194 / multi_agent_framework 1137）+ 完整 batch7/8/9/11 + audit_wiring 測試套件。runtime 狀態：StrategistAgent `shadow=False`（Sprint 5a live，`strategy_wiring.py:243`）、GuardianAgent / AnalystAgent 已 subscribe MessageBus、**ExecutorAgent `_shadow_mode=True` 默認未覆蓋**（`executor_agent.py:482` + `strategy_wiring.py:467` `ExecutorConfig()`）→ 產出 shadow intent log 不發 SubmitOrder IPC 到 Rust（設計上避免 Path A/B 倉位衝突，`executor_agent.py:382` 註解）。Linux uvicorn PID 720867（4 workers，2026-04-23 19:36 start）+ `/api/v1/paper/shadow/decisions` 持續被 GUI 查詢。**真正 gap**（待 G-1 展開）：(a) ExecutorAgent shadow→live 切換流程 + Rust IPC `SubmitOrder` 接收 Python intent 的整合契約 (b) Layer 2 自主推理循環（新聞搜索 / 宏觀判斷 / 工具箱 / 推理鏈記錄，見 `memory/project_layer2_agent_design.md`）。先前敘述「H1-H5 AI agent 目前全 stub」過期）。

**Live 前置**：~~G-3 / G-5 / Phase 6~~ ✅ · ~~LIVE-GUARD-1 Rust fail-safe 補回~~ ✅（2026-04-16 深夜，三重 Mainnet 硬鎖，見 §三/§四） · ~~LIVE-GATE-BINDING-1 Python↔Rust 簽名授權綁定~~ ✅（2026-04-18，HMAC `authorization.json` + 5 min re-verify，見 §四 Gate #5） · ~~P0-9 STABILITY-1~~ ✅（停電基礎設施事件 RCA 完成，非 code bug，不重置 21d 時鐘） · demo ≥21d 穩定（P0-2，時鐘從 **2026-04-16 22:16 local** 起算 = P0-9 STABILITY-1 RCA 穩定點；PID 已多次輪替，當前 engine PID `3954769` 於 **2026-04-21 20:44 CEST** `restart_all.sh --rebuild` restart 起（commit `f128af5` baseline，累積 TRACK-P-T4-WIRING-1 + EDGE-P2-3 PostOnly + DECISION-OUTCOMES fix + 所有 split 系列 refactor 首次進 runtime），計劃性 rebuild/deploy 不重置時鐘，僅 crash/hang 才重置）· provider pricing 綁定（LG-3）· API key 填入 ≠ 即可上線（Rust 側 4 項可驗證硬鎖 + Python 側 2 項門控共 5 項，全綠才真實 live）。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-23 21:40 CEST：engine lib **1939 / 0 failed** + bin 38 · pytest **2996 / 0 fail / 1 skipped** · **Live_Ready ⚠️**（5 門控，Rust 可驗證 4）· **Phase 5 PAUSED**（demo 2w 後 P0-3 重評）· WS-RETIRE-1 / DEDUP-PY-RUST A+B+C+D / INFRA-PREBUILD-1 A+B 於 2026-04-23 `--rebuild` 後 runtime；TRACK-P v2 + T4 + V2-SWAP 自 2026-04-22 起 runtime live · **主路徑**：P0-2 21d demo（~2026-05-07 解鎖）→ P0-3 Phase 5 edge 重評 → LG-2/3/4/5 → Live（最早 W24 末 ~2026-05-23）。活躍細節 → §三 · 里程碑敘述 → 索引表 + `docs/archive/`。

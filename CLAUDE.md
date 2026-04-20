# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-16

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

**Runtime**：`Live_Ready` ⚠️（2026-04-16 audit 修正：原宣告不準確）— LIVE-P0/P1/P2 代碼完整、單測綠，但 **0 真實 live 流量**（歷史 43k 條 `engine_mode="live"` 實為 LiveDemo）。**真實 live 門控**：(1) Python `live_reserved` global mode、(2) Python Operator 角色 auth、(3) secret slot 有 `BYBIT_API_KEY/SECRET` 或 `settings/secret_files/bybit/live/{api_key,api_secret}`。`execution_authority` 在 Rust 僅為 P0/P1 denylist 字串常量（`claude_teacher/applier.rs:226`），非真實授權邏輯；「auto_granted_on_start」屬 Python 概念。Live 縮倉監控：5min 輪詢，≥5% 警告，≥15% 自動撤權+平倉+凍結 GovernanceHub（代碼已寫、e2e 測試綠，**從未真實觸發**）。

**權威原則**：Rust `openclaw_engine` = paper/demo/live 三引擎並行唯一引擎（ARCH-RC1 1C-4 + 3E-ARCH）。Rust ConfigStore 為所有交易/風控/學習/預算參數權威，4 IPC 寫入面 → tick-level hot-reload。**禁止 restart-to-apply**。Guardian = RiskConfig 純派生視圖。Python 無交易邏輯（DEAD-PY-2 清除 ~4500 行後）。**2026-04-16 audit 更正**：`legacy_routes.py + main_legacy.py` 共 1630 行**仍是活躍主承載**（main_legacy.py:450-451 `register_legacy_routes(app)` 注冊 54 路由），覆蓋 auth/login/gui/console/`/api/v1/system/*`/`/api/v1/health/db`/`/api/v1/learning/*`——原「已隔離不執行」敘述錯誤，此層拆分未完成。

**進行中/阻塞**：
- **STABILITY-1 ✅ RCA 完成（2026-04-16 深夜，operator 確認停電原因）**：當日 30 次 crash（初報 5，深撈後 30）**全部為單次停電斷網基礎設施事件，非代碼 bug**。operator 筆電 10:00-16:00 local 停電 ~6h，第一次 crash 10:45 local（停電 45min 後電池/路由器失電）；watchdog 13:16-18:03 local 完全靜默（硬斷電，post-gap `snapshot age=17313.5s` = 4.81h 陳舊鐵證）；engine log 全部為 `Temporary failure in name resolution` DNS 失敗 + HTTP transport error，**零 panic、零 assertion、零 rust backtrace**，純屬 REST/WS 連不上 Bybit 的合理 fail-closed。當前 PID 1364222 於 22:16 local 穩定。**P0-2 LG-1 21d demo 時鐘不重置**——基礎設施事件 ≠ 引擎不穩定，否則每次停電都重置永遠達不到。Nice-to-have：watchdog 加 DNS-loss 分類（連續 N 次 DNS failure → `network_outage`，不計 stability strike），不急。TODO §P0-9 已歸檔。
- **LEARNING-PIPELINE-DORMANT-1（P1-HIGH，2026-04-16 audit 新增 · 2026-04-18 refine v2）**：學習管線不是空殼是**半殼**——`learning.decision_features` 已累積 **1.65M rows**（live 1.07M / live_demo 576k / demo 800），`trading.risk_verdicts` 已累積 1.54M 24h，但：(1) `settings/edge_estimates.json` demo `grand_mean=-2214 bps` 真正元兇 **已由 B RCA L1 confirmed 為 P1-16 halt_session cross-symbol price corruption**（ETHUSDT $2357.94 被蓋到 DOT/HIGH/IP/AAVEUSDT，pairer `entry_notional=$0.13` 小分母放大成 `-17,617,373 bps`）——**P1-15 清 phantom cells + P1-17 Winsorize ±5000 bps 後 demo grand_mean 降至 -78 bps**，但這是下游 safety net 而非根因修復；live_demo 7d 乾淨 baseline `grand_mean=-14.97 bps` ≈ fee-neutral 仍為首個乾淨 baseline；**writer/reader 鏈通但屬手動 run**：無 cron/timer/scheduler，hot-reload 未接（僅 engine startup 讀一次，`set_edge_estimates()` 啟動後不再調用），bind cost_gate 門檻改為 grand_mean > −50 bps 且 ≥2 策略 shrunk_bps>0（詳 TODO §P1-14）；(2) `experiment_ledger_snapshot.json` top-level 是 list 非 dict（結構異常）；(3) 21 個 learning schema 表（bayesian_posteriors/linucb_state/teacher_directives/james_stein_estimates/model_registry/promotion_pipeline/rl_transitions 等）存在但無訓練任務消費；(4) **EDGE-P3-1 Phase B #3 ONNX loader 宣稱部署但 0 artifact 產出**。真正 gap：數據累積層 ✅、edge_estimates writer/reader 鏈 ✅（手動，非自動化）、canonical intent 審計表 ❌、scheduler+hot-reload ❌、下游訓練/Teacher 指令 ❌、~~P1-16 上游 halt_session price corruption 未修 ❌~~ **→ 2026-04-18 P1-16 雙軌修復完成（commit `fef688e`，上游 Rust `on_tick.rs::HaltSession` 改用 `close_position_at_symbol_market` helper + 下游 pairer price-jump gate & 分母保護；archived 6616 fills empirical 245× cleaner，-2214 → -9.02 bps）✅**。TODO §P1-7 + §P1-14 + ~~§P1-16~~ + §P1-17。
- **LIVE-GUARD-1 ✅ 2026-04-16 深夜**：Rust 端 Mainnet 三重硬鎖回補（TODO §P0-8，E2 5/5 APPROVED，+7 新單測，engine lib 1342 passed）。Gate #1 `OPENCLAW_ALLOW_MAINNET=1` exact match · Gate #2 Mainnet 禁用 `BYBIT_API_KEY/SECRET` env var fallback（封閉 env 繞 slot 攻擊面）· Gate #3 憑證空時構造即 `Err`（不再 warn!+401）。Demo/Testnet/LiveDemo 零回歸。真實 live 門控從 1 項 Rust-verifiable 升為 **3 項**（見 §四表更新）。
- **INTENT-WRITE-GAP-1（P0-CRITICAL，2026-04-16 refine）**：`trading.risk_verdicts` 24h 內 live/live_demo Approved **154 萬條**（每條含 `intent_id`），`learning.decision_features` 同期 live/live_demo **165 萬 rows**，但 `trading.intents` 對 live/live_demo 同期 **0 條**。→ 改釐清為「canonical `trading.intents` 斷鏈 vs Rust 側影子路徑寫入」：Rust 分析/風控 path 照跑、canonical intent 持久化被 DEDUP-PY-RUST Tier A stub 掉 Python 端後未補 Rust 接線。下游 Phase 5/experiment_ledger 讀 `trading.intents` 查不到；讀 `decision_features` 可以。TODO §P0-6。
- **ORDER-SUBMIT-GAP-1（P0-CRITICAL，2026-04-16 新增）**：live_demo Approved verdict 持續但 `trading.fills` live/live_demo = 0。意味 Guardian 在跑、Approved verdict 寫入 DB，但 order submit path 被跳過（可能 OMSProxy 是 noop、或 trading_mode/live_reserved 未啟）。「Live_Ready」下真實下單能力 0%。TODO §P0-7。
- **Phase 5 PAUSED**（2026-04-12 reframe）— PNL-FIX-1/2 清理後所有活躍策略 gross edge 為負（net -$2775）；cost_gate/DL/JS 機械已接線但需真實正 edge。**下一步**：乾淨 demo 2 週後 P0-3 重評，若仍負則轉 EDGE-P3-1/EDGE-P2 接管。詳見 `memory/project_phase5_promotion_edge_crisis.md`。
- **P0-10 SCANNER-GATE ✅ 2026-04-17**：策略在 scanner 輪替出的 symbol 上反復開→平死循環（BASEDUSDT 等 20+ symbols，228 筆 ipc_close_symbol fills）。三部分修復：(1) tick_pipeline 新增 SymbolRegistry gate 阻止非活躍 symbol 開倉 (2) paper_state proactive_mirror_insert 彌合 REST→WS 空窗 (3) orphan_handler A4 移除（orphan=重啟遺留，非 scanner 輪替）。engine lib 1351 passed / 0 failed。
- **P0-5 PHANTOM-2-FUP ✅**：A+C 方案實作完成（HashMap+60s cooldown + clear 條件只在 Normal 時觸發）+5 新單測。已隨 P0-10 一起 `--rebuild` 部署。
- **P1 audit 衍生**：DEMO-REBOOT-PNL-RESET-1（重啟洗歷史 drawdown）、DEMO-BYBIT-SYNC-ORPHAN-1（6 個 bybit_sync 倉位策略動不了）— 詳 TODO §P1-5/P1-6。
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
| 2026-04-19 | **PIPELINE-SLOT-1** ✅（Phase 1-4；commits `3005fc0` Phase 1 · `e28f3d8` Phase 2 · `d92f25d` Phase 3；Phase 4 Python-only：`_trigger_live_auth_recheck_fire_and_forget` offload 到 daemon thread 讓 HTTP handler 立即回應 + 8 新 pytest `test_live_auth_recheck_trigger.py`（4 contract + 3 call-site integration + 1 HTTP failure isolation）+ ADR `docs/decisions/2026-04-19--pipeline_slot_1_auth_fail_scoping.md`（D1-D4 決策 + 4 替代路徑拒絕理由）；auth-fail scope 從 engine-wide 收斂到 live-only（demo + paper 不再被 auth 過期拉下）；live respawn TTR ≤5s（watcher poll）或 <100ms（IPC fast path）；restart_kind sentinel 區分 manual vs unattended；2026-04-14 Fix 3 panic→engine-wide cancel 語義保留；Rust side NO governance state persistence（見 ADR D4）；engine lib 1629 / bin 38 保持；Phase 4 僅 Python changes，零 Rust 變動） · **E5-P1 Refactor Wave 1** ✅（8 P1 並行 sub-agent + 6 delivered / 2 evidence-based cancel + 6× E2 並行審查 6/6 APPROVE + 全 cherry-pick clean auto-merge；P1-1 `paper_state.rs` 2380→8 submodules（ba8cd2c，+3 bit-exact f64 oracle）· P1-3 `event_consumer/handlers.rs` + `ipc_server/handlers.rs` by-domain split（76cd793，26 PipelineCommand arms + 22 IPC methods 1:1）· P1-4 Python `BaseAgent` + `llm_call_wrapper`（b0dc6b6，5 agents 共用 ~80 行抽取）· P1-5 JSON-RPC cross-layer helpers（c220375，4 orphan modules + 4 proof-of-adoption；`ipc_error_handler`/`ipc_dispatch`/`param_extractor`/`supervised_spawn`；+17 tests；`_SHARED_IPC_SLOTS` 登記進 §九）· P1-8 `rejection_coding.rs`（d6f7572，15 variants byte-identity + 18 call sites + 16 tests）· P1-9+P2-5 `governance_hub.py` Mixin 拆分（1b72f90，1052→1005；5 handlers 移動 + 5 methods `@deprecated`）；**cancel**：P1-6 gate_pipeline（h0_gate vs paper_live_gate 0 lines 真實共用 + 架構差異 1ms SLA vs FSM operator approval）· P1-7 command_dispatch（任務前提過時，dispatch-match 已在 prior pass 移至 `event_consumer/handlers`）；engine lib 1498→**1533** passed（+35）/ pytest 2511 passed / 2 pre-existing DYNAMIC-RISK fails；sub-agent 寫碼 refuse pattern 穩定解除（第 3 次驗證） · **E5-P2 Refactor Wave 2** ✅（5 P2 並行 sub-agent + 2 delivered / 3 evidence-based CANCEL + 2× E2 並行審查 2/2 APPROVE_WITH_NITS 非阻塞 + 全 cherry-pick clean；P2-3 `multi_interval_ws.rs` → `multi_interval_topics.rs`（11dedbf，+2 contract tests，移除零 caller `configure_multi_interval` 斷 WsClient 耦合）· P2-4 strategies magic numbers → config（822f799，7 literals：bb_breakout hurst_regime_boost/4 exit bonuses/1 exit penalty + grid_trading cooldown_ms；+9 bit-exact default tests；順帶封死 GridTrading.cooldown_ms TOML 不可達漏洞）；**CANCEL**：P2-2 onnx_inference（優化前提已由 EDGE-P3-1 Phase B Step 7b `OrtPredictor.input_name: String` load-time cache 滿足）· P2-7 directive_handler（applier.rs 560 LOC prod/1068 含 tests 已 FIX-08 拆出 fixtures，denylist+helper+apply_* 1-to-1 耦合 R6 cohesion invariant）· P2-8 Python `learning_batch_writer`（control_api 唯 1 個 `INSERT INTO learning.*` 在 `ai_service_feedback.py:105`，ml_training 11 個 writer 各寫不同 schema 無共用 row shape）；**defer**：P2-1 enum reorg + P2-6 fill_context_builder（`tick_pipeline/mod.rs` EXIT-FEATURES-TABLE-1 pre-existing WIP +45 行衝突；WIP 落地後再評）；engine lib 1533→**1560** passed（+27，含 pre-existing WIP 測試；E5-P2 貢獻 +11）/ 2 pre-existing WIP fail（`test_exit_feature_row_*` EXIT-FEATURES-TABLE-1，非 E5 regression）；發 `E5-P2-4b` follow-up（bb_breakout 1265 / grid_trading 1434 / strategies/mod.rs 1442 均超 §九 1200 硬上限，非 Wave 2 新增） · **FILL-CONTEXT-LINKAGE-1** ✅（commit `bd45e90`）：P1-7 C ML 訓練 0 標籤的根因修復 — `learning.decision_features` 3.36M rows 與 `trading.fills.entry_context_id` 3514 rows 0 JOIN overlap；root cause = decision_features.context_id 訊號時刻用 `event.ts_ms`，exchange-confirmed fill 用 WS `exec_ts`（漂移 100-500ms），同 `make_context_id(em,sym,ts_ms)` formula 不同 ts_ms → 不同字串。修復 = 端到端傳遞訊號時刻 id：`OrderDispatchRequest.context_id` + `PendingOrder.context_id` 新欄位 → `apply_confirmed_fill(...,signal_context_id:&str,...)` 新參數，body 用 param 取代 exec_ts 重算（empty 時 fallback exec-time 保留 orphan/shadow 舊行為）；3 close-dispatch sites 帶 `paper_state.get_entry_context_id(symbol)`；+2 regression tests（`apply_confirmed_fill_preserves_signal_context_id` 斷言訊號 id `-1000` 寫入且 exec id `-2000` 絕不出現 / `_falls_back_when_signal_id_empty` 驗 fallback）；engine lib 1560→**1564** passed；P1-7 C 從「結構性斷鏈」狀態解除為「等部署 + 累積流量」 · **EXIT-FEATURES-TABLE-1 Phase 1b FUP** ✅（commit `c7171b2`）：Phase 1b producer wiring（`6ea643e`）覆蓋 `emit_close_fill` 主路徑但漏 2 個 close-fill paths — `process_external_fill`（IPC 外部 fill 報告）+ `ipc_close_symbol` paper 分支（operator `/close_symbol` API + dust eviction + orphan_handler→Paper 模式）；抽出 `try_emit_exit_feature_row` `pub(crate)` helper，2 paths 接線 emit ExitFeatureRow，identical fail-soft 語義；+3 tests（`test_ipc_close_symbol_paper_emits_exit_feature_row` / `test_try_emit_exit_feature_row_helper_direct_call` / `test_try_emit_exit_feature_row_fail_soft`）；engine lib 1564→**1567** passed（pre-existing WIP 5 個 `test_exit_feature_row_*` 全綠）· **E5-FN Functional Defects Wave** ✅（3 派發 → 1 CANCEL + 2 delivered，2× E2 並行審查 2/2 APPROVE_WITH_NITS 非阻塞；**FN-1 CANCEL**：audit §七.7.1「live_authorization.verify_*() 同步但 main.rs spawn 後 5 min 才首次 re-verify，中間有窗口」聲稱不成立 — `startup.rs:467-494` `build_exchange_pipeline` 構造 pipeline 前已同步 `load_and_verify(env)` 驗證，失敗即 `return None`；5 min ticker 只是 mid-session revoke detector，非首次驗證 gate；0 lines changed · **FN-2 ai_budget request_id dedup（Plan N 重設計）** ✅（commit `f0f11c0`，原 `fd480ba` 已 revert `87b7653`）：`learning.ai_usage_log` PK `(time, scope, request_id)` 用 `time=NOW()`，retry 拿到新 NOW() → PK 不 dedup → 同 AI 調用可雙重扣費。**原 V018 partial UNIQUE `WHERE request_id <> ''` 設計失敗** — TimescaleDB hypertable 要求 UNIQUE index 必須含 partitioning column `time`（empirical error `cannot create a unique index without the column "time"`），直接 revert 重設計。**Plan N** 改用**既有 hypertable PK `(time, scope, request_id)`** 做 `ON CONFLICT DO NOTHING RETURNING 1`（零 schema 改動、零 migration）：(1) `make_request_id(scope) -> (String, i64)` 回 `(rid, ts_ms)` tuple — caller 重試**必須**傳同 tuple (2) `usage_io::insert_usage` 新 `event_time_ms: i64` 參數 + bind `$1::timestamptz` + `RETURNING 1` → `Ok(bool)`（`false`=dedup） (3) `tracker::record_usage` 新 `event_time_ms` 參數 + `if inserted` 才累進 MTD cache (4) `claude_teacher/mod.rs` 改用 `make_request_id("teacher")` tuple (5) IPC `handle_record_ai_usage` 收 Python 傳入 `(request_id, event_time_ms)` 或本地鑄造 — 封閉 `fd480ba` 原本會引入的 `"py-sync"` literal PK 碰撞（所有 Python caller 共用同 id 會全被 PK 折疊掉）。+4 Plan N 測試（format / 同 ms 唯一 / cold-start cache 累進 / distinct tuples 分別累進）；engine lib 1567→**1571**；**部署無約束**：直接 `restart_all.sh --rebuild` · **FN-3 agent_audit_bridge**（commit `19f3d85`）：audit §七.7.3 聲稱 5-Agent（Scout/Strategist/Guardian/Analyst/Executor）19 個 `_audit()` call-site 無一寫入 `change_audit_log` — 違反 Root Principle #8「交易可解釋」。RCA 驗證聲稱成立（`strategy_wiring.py` 4 agent 建構時均未傳 `audit_callback=`）。新 `agent_audit_bridge.py` stateless 工廠 + **AnalystAgent pilot wiring**（Batch 9/10 兩 call sites）+ 12 tests；fail-open 3 層守護；`_ANALYST_AUDIT_CB`/`_GOV_HUB_FOR_ANALYST` 登記進 §九；**APPROVE_PARTIAL** 延後 4 agent wiring（Strategist:172 / Guardian:215 / Executor:345 / Scout:114+framework ctor）→ TODO §E5-FN-3-FUP；pytest **2820 passed** / 2 pre-existing DYNAMIC-RISK fail / 14 skipped）|
| 2026-04-20 | **EDGE-P2-2 Phase A** ✅ `381c542`（OI confluence signal for `bb_breakout` — 3 新參數 `enable_oi_signal`/`oi_buffer_window_ms`/`oi_confluence_bonus`/`oi_min_delta_pct` + 3 env TOML；E2 對抗性審查 7 findings 全修（#1 buffer dedup / #2 on_rejection preserve / #3 noise floor / #4 validate_oi factory mirror / #5 hot-reload smoke / #6 ts regression guard / #7 unit coverage）；engine lib 1770→**1791** passed；Phase B Liquidation signal 待做） |

**歷史細節指針**（不要重複載入）：
- §三 2026-04-17/18 完整敘述 → `docs/archive/2026-04-20--claude_md_section3_snapshot.md`
- §三 2026-04-15 之前完整敘述 → `docs/archive/2026-04-15--claude_md_section3_snapshot.md`
- 1A→1C-4 commit 敘事 → `docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`
- Phase 0-4 Sprint/Wave → `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`
- 逐 commit 行數 → `docs/CLAUDE_CHANGELOG.md`
- 1C-3/1C-4 narrative → `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

---

## 四、硬邊界（永遠不能違背）

```python
# ── Live_Ready 真實狀態（2026-04-18 LIVE-GATE-BINDING-1 ✅ 後更新）──
# LIVE-P0/P1/P2 基礎設施代碼完整（SM-01/02/04 + Reconciler + 3E-ARCH）
# 單測綠但 0 真實 live 流量（歷史 43k 條 "live" 實為 LiveDemo）。
#
# 當前真實 live 門控（Rust 端可驗證 = 4 項 / 全部 = 5 項）：
#   1. Python `live_reserved` global mode          （Python 狀態，重啟會丟）
#   2. Python Operator 角色 auth                   （Python 側）
#   3. OPENCLAW_ALLOW_MAINNET=1 env var            （Rust 側，LIVE-GUARD-1，僅 Mainnet）
#   4. secret slot 有 api_key + api_secret         （Rust 側，LIVE-GUARD-1，憑證空 → Err）
#        來源優先級（bybit_rest_client.rs:386-497）：
#          Mainnet:  a. 顯式參數 → b. slot file（env var 回退已封閉）
#          Demo/Testnet: a. 顯式參數 → b. env var → c. slot file
#   5. authorization.json 簽名+未過期+env_allowed 匹配  （Rust 側，LIVE-GATE-BINDING-1，新）
#        路徑：$OPENCLAW_SECRETS_DIR/live/authorization.json
#        驗證：canonical_payload HMAC-SHA256（key=OPENCLAW_IPC_SECRET）
#        檢查點：build_exchange_pipeline 啟動 + main.rs 每 5 min re-verify
#        失效 → engine 優雅 shutdown（cancel_token）
#        涵蓋 LiveDemo + Mainnet（LiveDemo 不因 api-demo endpoint 降級）
#
# ✅ LIVE-GATE-BINDING-1（TODO §P0-11，2026-04-18）：
#   - Python EarnedTrust renew/approve 路由寫出 signed authorization.json（0o600 + atomic rename）
#   - Revoke 路徑刪 authorization.json → Rust 下個 5 min re-verify 即 shutdown
#   - canonical payload byte-for-byte Python↔Rust 雙端對齊（sort+dedup envs）
#   - Rust 15 新單測 / Python 10 新單測 / engine lib 1452 passed
#   - 閉合「Operator 未 renew 即 Live 自拉」旁通漏洞
#
# ✅ LIVE-GUARD-1（TODO §P0-8，2026-04-16 深夜）：
#   - Gate #3: 恢復 OPENCLAW_ALLOW_MAINNET=1（SEC-17 回退）
#   - Gate #4a: Mainnet 禁用 BYBIT_API_KEY/SECRET env var fallback（封閉繞 slot 攻擊面）
#   - Gate #4b: 憑證空時構造 Err（不再 warn!+signing-stage 401）
#   - 7 新單測 + E2 對抗性審查 5/5 APPROVED
#
# execution_authority：Rust 僅為 P0/P1 denylist 字串常量
#                      （claude_teacher/applier.rs:226）非真實授權邏輯
#                      「auto_granted_on_start」= Python 概念
decision_lease_emitted  = False
max_retries             = 0

# 永不允許的硬錯誤（2026-04-18 LIVE-GATE-BINDING-1 後修正）：
# - 繞過 Operator 角色認證或 live_reserved global mode 直接啟動 live session
# - 自動修改 engine trading_mode 為 live（需 operator 顯式配置）
# - Bybit API timeout / retCode != 0 → fail-closed，不重試
# - should_call_ai=true 但 invocation 沒發生
# - 偽造 AI 調用或交易活動
# - Mainnet 下無 OPENCLAW_ALLOW_MAINNET=1 env var（LIVE-GUARD-1）
# - Mainnet 下試圖用 BYBIT_API_KEY/SECRET env var 作為唯一憑證來源（LIVE-GUARD-1）
# - Live（含 LiveDemo）下沒有有效 authorization.json 即 spawn pipeline（LIVE-GATE-BINDING-1）
#   LiveDemo 不因使用 api-demo endpoint 而降級任何 live-level 門控
# - 不經 _write_signed_live_authorization() 手動寫 authorization.json
#   必經 Python renew/approve 路由簽章寫入
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

### 啟動檢查
```bash
git status && git log --oneline -5
```

### ★ 灰度驗證檢查（每次啟動必做，直到 R-07 Go/No-Go 通過）
Rust 引擎灰度驗證正在後台運行。**每次 session 啟動時先跑以下命令確認引擎健康：**
```bash
# 引擎存活？+ canary 記錄數 + 崩潰數 + 最新狀態
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status
wc -l /tmp/openclaw/engine_results.jsonl
grep -c "ENGINE_CRASH" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"
```
詳細操作指南見 TODO.md 頂部「灰度驗證檢查」段。如引擎掛了按 TODO.md 指引重啟。

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

### 強制同步規則
- **Sprint/Wave 完成**：更新 §三 + §十一 + `docs/CLAUDE_CHANGELOG.md` + README，與生產代碼同 commit
- **§三 衛生規則（強制）**：§三 只記載「現況/活躍狀態」+「過去 ≤2 天的完成里程碑」。**任何完成里程碑當天 +2 日（以 `currentDate` 為準）必須在 commit 同次操作中歸檔到 `docs/archive/YYYY-MM-DD--claude_md_section3_*.md`** 並從 §三 刪除，僅在「已完成里程碑索引」表保留 1 行條目。違反 = §三 膨脹回 ~10K tokens、context 提早撞 compact。
- **Commit 時**：摘要追加到 `docs/CLAUDE_CHANGELOG.md` 頂部，格式 `### 標題（YYYY-MM-DD · commit XXXXXXX）`
- **Context ≥90%**：立即寫 `docs/worklogs/YYYY-MM-DD--session_progress_N.md`（已完成/進行中/未完成/決策/下一步）
- **每日整合**：當天 worklog 碎片合併為 `YYYY-MM-DD--daily_summary.md`，刪碎片
- **新腳本**：MODULE_NOTE 雙語 + latest+dated 輸出 + contract check + 更新 SCRIPT_INDEX.md
- **docs/**：分類目錄 + `YYYY-MM-DD--描述.md` + 更新 `docs/README.md` 索引

---

## 八、16 Agent 角色體系與強制工作鏈

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
| `_ANALYST_AUDIT_CB` / `_GOV_HUB_FOR_ANALYST` | strategy_wiring.py | 模組級，由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造；AnalystAgent 建構時注入 `audit_callback`（E5-FN-3）。`agent_audit_bridge` 本身為無狀態工廠模組（不持有 singleton） |
| `_STRATEGIST_AUDIT_CB` / `_GOV_HUB_FOR_STRATEGIST` | strategy_wiring.py | 模組級，由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造；StrategistAgent 建構時注入 `audit_callback`（E5-FN-3-FUP-a）。ImportError 時 `_GOV_HUB_FOR_STRATEGIST=None` → bridge fail-open 靜默丟棄 |
| `_GUARDIAN_AUDIT_CB` / `_GOV_HUB_FOR_GUARDIAN` | strategy_wiring.py | 模組級（Batch 8），由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造；GuardianAgent 建構時注入 `audit_callback`（E5-FN-3-FUP-b）。`_GOV_HUB_FOR_GUARDIAN` 於 Batch 8 既存，E5-FN-3-FUP-b 補登記；ImportError 時為 None → bridge fail-open |
| `_EXECUTOR_AUDIT_CB` / `_GOV_HUB_FOR_EXECUTOR` | strategy_wiring.py | 模組級（Batch 11 try 區塊內），由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造；ExecutorAgent 建構時注入 `audit_callback`（E5-FN-3-FUP-c）。fail-open：GOV_HUB 不可用時 bridge 靜默丟事件 |
| `_SCOUT_AUDIT_CB` / `_GOV_HUB_FOR_SCOUT` | strategy_wiring.py | 模組級（Plan A2 Scout 區塊內），由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造；ScoutAgent 建構時注入 `audit_callback`（E5-FN-3-FUP-d）。ScoutAgent ctor 新增 keyword-only `audit_callback` 參數並接線 produce_intel / produce_event_alert 兩個 `_audit()` 呼叫點；ImportError 時 `_GOV_HUB_FOR_SCOUT=None` → bridge fail-open 靜默丟棄 |

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

**路線圖**：Phase 0-5 ✅ · Live GUI ✅ · Phase 6 ✅ · **AI 治理層 (W22-W23) ⬜**（H1-H5 AI agent 目前全 stub，待 G-1 R-06 展開）。

**Live 前置**：~~G-3 / G-5 / Phase 6~~ ✅ · ~~LIVE-GUARD-1 Rust fail-safe 補回~~ ✅（2026-04-16 深夜，三重 Mainnet 硬鎖，見 §三/§四） · ~~LIVE-GATE-BINDING-1 Python↔Rust 簽名授權綁定~~ ✅（2026-04-18，HMAC `authorization.json` + 5 min re-verify，見 §四 Gate #5） · ~~P0-9 STABILITY-1~~ ✅（停電基礎設施事件 RCA 完成，非 code bug，不重置 21d 時鐘） · demo ≥21d 穩定（P0-2，當前 PID 1364222 於 22:16 local 啟動，時鐘從此起算）· provider pricing 綁定（LG-3）· API key 填入 ≠ 即可上線（Rust 側 4 項可驗證硬鎖 + Python 側 2 項門控共 5 項，全綠才真實 live）。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-20：tests engine lib **1791 passed / 0 failed** + bin **38 passed** + core **392** + e2e **35** + reconciler_e2e **19** + micro_profit_fix_integration **7** · pytest 全量 **2866 passed / 0 pre-existing fail / 14 skipped**（+8 PIPELINE-SLOT-1 Phase 4 + 2 DYNAMIC-RISK-STATUS-TEST-SIG-1 修復 `83a0475` + 16 WATCHDOG-DNS-CLASSIFY-1 新測） · **EDGE-P2-2 Phase A ✅**（commit `381c542`；OI confluence signal for `bb_breakout`，3 新參數 `enable_oi_signal`/`oi_buffer_window_ms`/`oi_confluence_bonus`/`oi_min_delta_pct` + 3 env TOML；E2 對抗性審查 7 findings 全修 #1-#7；engine lib 1770→**1791** passed；Phase B Liquidation signal 待做）· **PIPELINE-SLOT-1 Phases 1-4 ✅**（`3005fc0` + `e28f3d8` + `d92f25d` + Phase 4 Python-only：daemon-thread trigger offload + 8 pytest + ADR `docs/decisions/2026-04-19--pipeline_slot_1_auth_fail_scoping.md`；auth-fail scope engine-wide → live-only，live respawn TTR ≤5s / <100ms，demo+paper 不再連坐） · **E5-FN Functional Defects Wave ✅**（3 派發 → 1 CANCEL（FN-1 evidence-based：`startup.rs:467-494` 已同步驗 authorization）+ 2 delivered；FN-2 **Plan N 重設計** `f0f11c0` ai_budget request_id dedup — 原 V018 partial UNIQUE 無法 apply on TimescaleDB hypertable（`cannot create a unique index without the column "time"`），revert fd480ba 改用既有 hypertable PK `(time, scope, request_id)` + `ON CONFLICT DO NOTHING RETURNING 1`，零 schema 改動、零 migration；`make_request_id(scope) -> (String, i64)` tuple + `record_usage(...,event_time_ms)` + IPC handler 本地鑄造封閉 `py-sync` PK 碰撞；FN-3 `19f3d85` agent_audit_bridge + AnalystAgent pilot + 12 tests + 4-agent follow-up；兩者 E2 2/2 APPROVE_WITH_NITS）· **FILL-CONTEXT-LINKAGE-1 ✅**（commit `bd45e90`） · **EXIT-FEATURES-TABLE-1 Phase 1b FUP ✅**（commit `c7171b2`） · **E5-P2 Refactor Wave 2 ✅**（commits **11dedbf** · **822f799**；E5-P2-4b follow-up：bb_breakout 1265 / grid_trading 1434 / strategies/mod.rs 1442 均超 §九 1200 硬上限） · **E5-P1 Refactor Wave 1 ✅**（6 delivered + 2 cancel） · **P1-16 HALT-SESSION CROSS-SYMBOL PRICE CORRUPTION ✅**（commit `fef688e`；mean -9.02 bps vs 修前 -2214 bps，245× cleaner）· **E5-P0 Refactor Wave ✅** · **LIVE-GATE-BINDING-1 ✅** · **MICRO-PROFIT-FIX-1 ✅** · **P1-8 DUST-EVICTION-GAP-1 E1/E4 ✅** · **P0-10 SCANNER-GATE ✅ 部署** · **P0-5 PHANTOM-2-FUP ✅ 部署** · **P0-9 STABILITY-1 ✅ RCA** · **LIVE-GUARD-1 ✅** · **Phase 5 PAUSED** · **Live_Ready ⚠️** · **下一步**：restart_all.sh --rebuild 整合部署 E5-FN + FILL-CONTEXT + EXIT-FEATURES + E5-P1/P2（Plan N 零 migration，直接 rebuild）→ 累積流量後 P1-7 C 首跑 ONNX artifact · E5-FN-3-FUP（Strategist:172 / Guardian:215 / Executor:345 / Scout:114 audit_callback wiring）· E5-P2-4b 策略檔拆解排期 · P0-2 LG-1 21d demo 觀察 → P0-3 edge 重評 · P0-6 intent write / Demo 死循環打破 · **P1-7 LEARNING-PIPELINE-DORMANT-1** · Phase 2B Strategist 等 G-1 R-02。

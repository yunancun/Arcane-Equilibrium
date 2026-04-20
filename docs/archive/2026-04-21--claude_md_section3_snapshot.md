# CLAUDE.md §三 Section-3 Snapshot Archive — 2026-04-21

> 從 `CLAUDE.md` §三 按衛生規則（milestone 日期 +2 日歸檔）遷出的完整敘述。
> 歸檔範圍：
> - **2026-04-16** 進行中/阻塞 bullet 列表殘留的已完成項（STABILITY-1 RCA · LIVE-GUARD-1）—— 上一輪歸檔漏遷
> - **2026-04-19** 里程碑索引表完整條目（PIPELINE-SLOT-1 · E5-P1/P2 Refactor Wave · FILL-CONTEXT-LINKAGE-1 · EXIT-FEATURES-TABLE-1 Phase 1b FUP · E5-FN Functional Defects Wave）
>
> 上一輪歸檔：`docs/archive/2026-04-20--claude_md_section3_snapshot.md`（2026-04-17 / 2026-04-18）

---

## 2026-04-16（進行中/阻塞 bullet 清理）

### STABILITY-1 ✅ RCA 完成（深夜，operator 確認停電原因）
當日 30 次 crash（初報 5，深撈後 30）**全部為單次停電斷網基礎設施事件，非代碼 bug**。operator 筆電 10:00-16:00 local 停電 ~6h，第一次 crash 10:45 local（停電 45min 後電池/路由器失電）；watchdog 13:16-18:03 local 完全靜默（硬斷電，post-gap `snapshot age=17313.5s` = 4.81h 陳舊鐵證）；engine log 全部為 `Temporary failure in name resolution` DNS 失敗 + HTTP transport error，**零 panic、零 assertion、零 rust backtrace**，純屬 REST/WS 連不上 Bybit 的合理 fail-closed。當前 PID 1364222 於 22:16 local 穩定。**P0-2 LG-1 21d demo 時鐘不重置** —— 基礎設施事件 ≠ 引擎不穩定，否則每次停電都重置永遠達不到。Nice-to-have：watchdog 加 DNS-loss 分類（連續 N 次 DNS failure → `network_outage`，不計 stability strike），不急。TODO §P0-9 已歸檔。

### LIVE-GUARD-1 ✅ 深夜
Rust 端 Mainnet 三重硬鎖回補（TODO §P0-8，E2 5/5 APPROVED，+7 新單測，engine lib 1342 passed）。
- Gate #1 `OPENCLAW_ALLOW_MAINNET=1` exact match
- Gate #2 Mainnet 禁用 `BYBIT_API_KEY/SECRET` env var fallback（封閉 env 繞 slot 攻擊面）
- Gate #3 憑證空時構造即 `Err`（不再 warn!+401）

Demo/Testnet/LiveDemo 零回歸。真實 live 門控從 1 項 Rust-verifiable 升為 **3 項**（見 §四表更新）。

---

## 2026-04-19

### PIPELINE-SLOT-1 Phase 1-4 ✅
Commits `3005fc0` Phase 1 · `e28f3d8` Phase 2 · `d92f25d` Phase 3；Phase 4 Python-only：`_trigger_live_auth_recheck_fire_and_forget` offload 到 daemon thread 讓 HTTP handler 立即回應 + 8 新 pytest `test_live_auth_recheck_trigger.py`（4 contract + 3 call-site integration + 1 HTTP failure isolation）+ ADR `docs/decisions/2026-04-19--pipeline_slot_1_auth_fail_scoping.md`（D1-D4 決策 + 4 替代路徑拒絕理由）。

**關鍵語義變更**：
- auth-fail scope 從 engine-wide 收斂到 live-only（demo + paper 不再被 auth 過期拉下）
- live respawn TTR ≤5s（watcher poll）或 <100ms（IPC fast path）
- `restart_kind` sentinel 區分 manual vs unattended
- 2026-04-14 Fix 3 panic→engine-wide cancel 語義保留
- Rust side NO governance state persistence（見 ADR D4）

engine lib **1629** / bin **38** 保持；Phase 4 僅 Python changes，零 Rust 變動。

### E5-P1 Refactor Wave 1 ✅
8 P1 並行 sub-agent + 6 delivered / 2 evidence-based cancel + 6× E2 並行審查 6/6 APPROVE + 全 cherry-pick clean auto-merge。

**Delivered**：
- **P1-1** `paper_state.rs` 2380→8 submodules（`ba8cd2c`，+3 bit-exact f64 oracle）
- **P1-3** `event_consumer/handlers.rs` + `ipc_server/handlers.rs` by-domain split（`76cd793`，26 PipelineCommand arms + 22 IPC methods 1:1）
- **P1-4** Python `BaseAgent` + `llm_call_wrapper`（`b0dc6b6`，5 agents 共用 ~80 行抽取）
- **P1-5** JSON-RPC cross-layer helpers（`c220375`，4 orphan modules + 4 proof-of-adoption；`ipc_error_handler`/`ipc_dispatch`/`param_extractor`/`supervised_spawn`；+17 tests；`_SHARED_IPC_SLOTS` 登記進 §九）
- **P1-8** `rejection_coding.rs`（`d6f7572`，15 variants byte-identity + 18 call sites + 16 tests）
- **P1-9+P2-5** `governance_hub.py` Mixin 拆分（`1b72f90`，1052→1005；5 handlers 移動 + 5 methods `@deprecated`）

**Cancel**：P1-6 gate_pipeline（h0_gate vs paper_live_gate 0 lines 真實共用 + 架構差異 1ms SLA vs FSM operator approval）· P1-7 command_dispatch（任務前提過時，dispatch-match 已在 prior pass 移至 `event_consumer/handlers`）。

engine lib 1498→**1533** passed（+35）/ pytest 2511 passed / 2 pre-existing DYNAMIC-RISK fails；sub-agent 寫碼 refuse pattern 穩定解除（第 3 次驗證）。

### E5-P2 Refactor Wave 2 ✅
5 P2 並行 sub-agent + 2 delivered / 3 evidence-based CANCEL + 2× E2 並行審查 2/2 APPROVE_WITH_NITS 非阻塞 + 全 cherry-pick clean。

**Delivered**：
- **P2-3** `multi_interval_ws.rs` → `multi_interval_topics.rs`（`11dedbf`，+2 contract tests，移除零 caller `configure_multi_interval` 斷 WsClient 耦合）
- **P2-4** strategies magic numbers → config（`822f799`，7 literals：bb_breakout hurst_regime_boost/4 exit bonuses/1 exit penalty + grid_trading cooldown_ms；+9 bit-exact default tests；順帶封死 GridTrading.cooldown_ms TOML 不可達漏洞）

**CANCEL**：
- P2-2 onnx_inference（優化前提已由 EDGE-P3-1 Phase B Step 7b `OrtPredictor.input_name: String` load-time cache 滿足）
- P2-7 directive_handler（applier.rs 560 LOC prod/1068 含 tests 已 FIX-08 拆出 fixtures，denylist+helper+apply_* 1-to-1 耦合 R6 cohesion invariant）
- P2-8 Python `learning_batch_writer`（control_api 唯 1 個 `INSERT INTO learning.*` 在 `ai_service_feedback.py:105`，ml_training 11 個 writer 各寫不同 schema 無共用 row shape）

**Defer**：P2-1 enum reorg + P2-6 fill_context_builder（`tick_pipeline/mod.rs` EXIT-FEATURES-TABLE-1 pre-existing WIP +45 行衝突；WIP 落地後再評）。

engine lib 1533→**1560** passed（+27，含 pre-existing WIP 測試；E5-P2 貢獻 +11）/ 2 pre-existing WIP fail（`test_exit_feature_row_*` EXIT-FEATURES-TABLE-1，非 E5 regression）。

**Follow-up `E5-P2-4b`**：bb_breakout 1265 / grid_trading 1434 / strategies/mod.rs 1442 均超 §九 1200 硬上限，非 Wave 2 新增。

### FILL-CONTEXT-LINKAGE-1 ✅（commit `bd45e90`）
P1-7 C ML 訓練 0 標籤的根因修復 —— `learning.decision_features` 3.36M rows 與 `trading.fills.entry_context_id` 3514 rows 0 JOIN overlap。

**Root cause**：`decision_features.context_id` 訊號時刻用 `event.ts_ms`，exchange-confirmed fill 用 WS `exec_ts`（漂移 100-500ms），同 `make_context_id(em,sym,ts_ms)` formula 不同 ts_ms → 不同字串。

**修復** = 端到端傳遞訊號時刻 id：`OrderDispatchRequest.context_id` + `PendingOrder.context_id` 新欄位 → `apply_confirmed_fill(...,signal_context_id:&str,...)` 新參數，body 用 param 取代 exec_ts 重算（empty 時 fallback exec-time 保留 orphan/shadow 舊行為）；3 close-dispatch sites 帶 `paper_state.get_entry_context_id(symbol)`；+2 regression tests（`apply_confirmed_fill_preserves_signal_context_id` 斷言訊號 id `-1000` 寫入且 exec id `-2000` 絕不出現 / `_falls_back_when_signal_id_empty` 驗 fallback）。

engine lib 1560→**1564** passed；P1-7 C 從「結構性斷鏈」狀態解除為「等部署 + 累積流量」。

### EXIT-FEATURES-TABLE-1 Phase 1b FUP ✅（commit `c7171b2`）
Phase 1b producer wiring（`6ea643e`）覆蓋 `emit_close_fill` 主路徑但漏 2 個 close-fill paths：
- `process_external_fill`（IPC 外部 fill 報告）
- `ipc_close_symbol` paper 分支（operator `/close_symbol` API + dust eviction + orphan_handler→Paper 模式）

抽出 `try_emit_exit_feature_row` `pub(crate)` helper，2 paths 接線 emit ExitFeatureRow，identical fail-soft 語義；+3 tests（`test_ipc_close_symbol_paper_emits_exit_feature_row` / `test_try_emit_exit_feature_row_helper_direct_call` / `test_try_emit_exit_feature_row_fail_soft`）。

engine lib 1564→**1567** passed（pre-existing WIP 5 個 `test_exit_feature_row_*` 全綠）。

### E5-FN Functional Defects Wave ✅
3 派發 → 1 CANCEL + 2 delivered；2× E2 並行審查 2/2 APPROVE_WITH_NITS 非阻塞。

**FN-1 CANCEL**：audit §七.7.1「live_authorization.verify_*() 同步但 main.rs spawn 後 5 min 才首次 re-verify，中間有窗口」聲稱不成立 —— `startup.rs:467-494` `build_exchange_pipeline` 構造 pipeline 前已同步 `load_and_verify(env)` 驗證，失敗即 `return None`；5 min ticker 只是 mid-session revoke detector，非首次驗證 gate；0 lines changed。

**FN-2 ai_budget request_id dedup（Plan N 重設計）** ✅（commit `f0f11c0`，原 `fd480ba` 已 revert `87b7653`）
- `learning.ai_usage_log` PK `(time, scope, request_id)` 用 `time=NOW()`，retry 拿到新 NOW() → PK 不 dedup → 同 AI 調用可雙重扣費
- **原 V018 partial UNIQUE `WHERE request_id <> ''` 設計失敗** —— TimescaleDB hypertable 要求 UNIQUE index 必須含 partitioning column `time`（empirical error `cannot create a unique index without the column "time"`），直接 revert 重設計
- **Plan N** 改用**既有 hypertable PK `(time, scope, request_id)`** 做 `ON CONFLICT DO NOTHING RETURNING 1`（零 schema 改動、零 migration）：
  1. `make_request_id(scope) -> (String, i64)` 回 `(rid, ts_ms)` tuple —— caller 重試**必須**傳同 tuple
  2. `usage_io::insert_usage` 新 `event_time_ms: i64` 參數 + bind `$1::timestamptz` + `RETURNING 1` → `Ok(bool)`（`false`=dedup）
  3. `tracker::record_usage` 新 `event_time_ms` 參數 + `if inserted` 才累進 MTD cache
  4. `claude_teacher/mod.rs` 改用 `make_request_id("teacher")` tuple
  5. IPC `handle_record_ai_usage` 收 Python 傳入 `(request_id, event_time_ms)` 或本地鑄造 —— 封閉 `fd480ba` 原本會引入的 `"py-sync"` literal PK 碰撞（所有 Python caller 共用同 id 會全被 PK 折疊掉）
- +4 Plan N 測試（format / 同 ms 唯一 / cold-start cache 累進 / distinct tuples 分別累進）；engine lib 1567→**1571**
- **部署無約束**：直接 `restart_all.sh --rebuild`

**FN-3 agent_audit_bridge**（commit `19f3d85`）
audit §七.7.3 聲稱 5-Agent（Scout/Strategist/Guardian/Analyst/Executor）19 個 `_audit()` call-site 無一寫入 `change_audit_log` —— 違反 Root Principle #8「交易可解釋」。RCA 驗證聲稱成立（`strategy_wiring.py` 4 agent 建構時均未傳 `audit_callback=`）。新 `agent_audit_bridge.py` stateless 工廠 + **AnalystAgent pilot wiring**（Batch 9/10 兩 call sites）+ 12 tests；fail-open 3 層守護；`_ANALYST_AUDIT_CB`/`_GOV_HUB_FOR_ANALYST` 登記進 §九。

**APPROVE_PARTIAL** 延後 4 agent wiring（Strategist:172 / Guardian:215 / Executor:345 / Scout:114+framework ctor）→ TODO §E5-FN-3-FUP。

pytest **2820 passed** / 2 pre-existing DYNAMIC-RISK fail / 14 skipped。

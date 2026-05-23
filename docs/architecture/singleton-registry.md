# OpenClaw Mutable Singleton Registry

Date: 2026-05-23
Status: Active — Singleton Registry SSOT (NEW location post 2026-05-02 CLAUDE.md trim)
Authority Source:
- `CLAUDE.md` §七 "New mutable singletons must be registered in the singleton table's current authority location before merge"
- `CLAUDE.md` §九 "New mutable singletons must be registered in the current singleton authority before merge"
- Sprint 4+ Wave B E2 round 2 MEDIUM-1 escalate (2026-05-23) — PA SSOT establishment finding

Cross-references:
- `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` §九 Singleton 表（pre-trim 完整快照；Python H_STATE_INVALIDATOR / MARKET_SCANNER / HStateCacheSlot / CostEdgeAdvisorDbSlot 4 條尚未 re-ingest 進本 SSOT — 見 §6 carry-over）
- `docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md`（同類 ongoing inventory pattern）
- ADR-0042 M3 Health Monitoring（Wave A/B 6 singleton 治理 source）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pm_phase_3e_signoff.md` §4.1（Sprint 4+ Wave B 派發來源）

---

## §1 Purpose

本 doc = OpenClaw 全項目 mutable singleton 登記表 SSOT。CLAUDE.md §七 + §九 兩條 rule 規定「新 mutable singletons 合併前必登記在 singleton table 當前權威位置」；2026-05-02 CLAUDE.md trim 期間原 §九 inline table 被 archive 但未搬到新位置，造成 governance gap（pre-trim snapshot 仍存於 `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` 但不再是 active SSOT）。本 doc 是 trim 後新權威位置。

### §1.1 範圍邊界（in scope）

- **In scope**：Rust `openclaw_engine` + Python `control_api_v1` 內 process-global 可變狀態（module-level `static`、`Arc<Mutex<...>>`、`Arc<RwLock<...>>`、`Arc<broadcast::Sender<...>>`、Python 模組級可變 binding 等）。
- **In scope**：跨 thread / 跨 tokio task 共享的可變 state container（多 task 並發 read-write 必需鎖或 channel）。

### §1.2 不屬本表範圍（out of scope）

- 純 function（無 mutable state，如 `is_live_release_profile()` / `table_present()`）。
- module-private sentinel `object()`（純 identity comparison，無 mutable state；如 strategist_singleton_pollution_fix_review 2026-04-28 確認）。
- struct-internal `Arc`（caller 端 own / inject pattern；非 process-global）。
- 編譯期常數 / `const` / `pub const`（如 `HEALTH_EVENT_CHANNEL_CAPACITY: usize = 256`）。
- 純 caller-injected 但全進程只構造一次的 `Arc<dyn ...>` trait object（除非該物件本身含 mutable state）。

### §1.3 登記欄位定義

對每 singleton 必登：

| 欄位 | 說明 |
|---|---|
| name | Singleton type / binding 名稱（精確 case） |
| type_signature | 完整 type signature（含 Arc / Mutex / 容器） |
| location | `file:line` 定義位置（struct/binding decl）；Rust 採 absolute repo-relative path |
| owner_lifecycle | 構造端 / 銷毀端（engine boot / engine shutdown / supervisor scope） |
| cross_task_pattern | 跨 task / thread 訪問 pattern（hot path push / scheduled emit / cascade subscribe …） |
| lock_primitive | std::sync::Mutex / parking_lot::Mutex / RwLock / tokio::broadcast / AtomicXxx 等 |
| visibility | `pub` / `pub(crate)` / `pub(super)` / private |
| caller_chain | 生產調用端列表（callsite file:line） |
| health_monitoring | 是否被 M3 health emitter 觀測（per ADR-0042 6 domain） |
| registered_date | 進本 SSOT 日期 |
| governance_authority | 所屬 ADR / spec / amend 來源 |
| migration_plan | 是否計劃改造（Sprint 5+ 升級 / 替換 / 拆分） |

---

## §2 Registered Singletons（active）

### §2.1 Sprint 4+ Wave A — Bybit Instrumentation（PA-DRIFT-4 IMPL closure 2026-05-23）

per Sprint 4+ first Live carry-over §4.1 item 3（PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 補位）；commit chain 5acd36e6 + 4c84d1bb；Sprint 4+ Wave B 接線 commit 245216d1 + 4d4ff99f。

#### 2.1.1 RestLatencyHistogram

| 欄位 | 值 |
|---|---|
| name | `RestLatencyHistogram` |
| type_signature | `pub struct { samples: std::sync::Mutex<Vec<(Instant, u64)>> }` |
| location | `rust/openclaw_engine/src/bybit_rest_client.rs:335-339` |
| owner_lifecycle | `BybitRestClient::new()` 構造（rust/openclaw_engine/src/bybit_rest_client.rs:978）；engine shutdown 隨 Arc drop |
| cross_task_pattern | REST hot path 多 task 並發 `record_latency()` push；emitter 端 `RealApiLatencySourceProbe::current_rest_latency_*_60s_window()` 同步 read（60s sample 一次） |
| lock_primitive | `std::sync::Mutex<Vec<(Instant, u64)>>`；cap 8192；60s rolling window |
| visibility | `pub`（含 `#[doc(hidden)]` `inject_sample_with_timestamp` test helper） |
| caller_chain | producer: `BybitRestClient::request_with_retry()` REST hot path（get/post 路徑 record_latency 呼叫）；consumer: `RealApiLatencySourceProbe` Track D emitter probe；handle exposer: `BybitRestClient::latency_histogram_handle()`（rust/openclaw_engine/src/bybit_rest_client.rs:989） |
| health_monitoring | YES — ADR-0042 Decision 3 `api_latency` domain；V106 row `api_latency__rest_p50_ms` / `__rest_p95_ms` / `__rest_p99_ms` |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 M3 Health Monitoring + PA-DRIFT-4 carry-over Sprint 2 §4.1 |
| migration_plan | 0 — Sprint 4+ first Live 標準配置；無計劃改造 |

#### 2.1.2 RetCodeCounter

| 欄位 | 值 |
|---|---|
| name | `RetCodeCounter` |
| type_signature | `pub struct { samples_4xx: std::sync::Mutex<Vec<Instant>>, samples_5xx: std::sync::Mutex<Vec<Instant>> }` |
| location | `rust/openclaw_engine/src/bybit_rest_client.rs:479-484` |
| owner_lifecycle | `BybitRestClient::new()` 構造（rust/openclaw_engine/src/bybit_rest_client.rs:979）；engine shutdown 隨 Arc drop |
| cross_task_pattern | REST 業務錯誤 hot path push（4xx client fault / 5xx venue fault 雙桶）；emitter probe 端 60s sample read |
| lock_primitive | 雙 `std::sync::Mutex<Vec<Instant>>`；cap 8192；60s rolling window |
| visibility | `pub` |
| caller_chain | producer: `BybitRestClient::request_with_retry()` 業務錯誤分類 `BybitApiError::Business` retCode 對映 4xx/5xx；consumer: `RealApiLatencySourceProbe` Track D emitter probe；handle exposer: `BybitRestClient::ret_code_counter_handle()`（rust/openclaw_engine/src/bybit_rest_client.rs:994） |
| health_monitoring | YES — ADR-0042 Decision 3 `api_latency` domain；V106 row `api_latency__ret_4xx_count` / `__ret_5xx_count` |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 + PA-DRIFT-4 carry-over + ADR-0040 multi-venue gate 預留（4xx/5xx 分桶為 multi-venue 共通 transport-level 語意） |
| migration_plan | 0 — multi-venue 預埋；無近期改造計劃 |

#### 2.1.3 WsRttHistogram

| 欄位 | 值 |
|---|---|
| name | `WsRttHistogram` |
| type_signature | `pub struct { samples: std::sync::Mutex<Vec<(Instant, u64)>> }` |
| location | `rust/openclaw_engine/src/bybit_private_ws.rs:102-105` |
| owner_lifecycle | `BybitPrivateWs::new()` 內部構造（rust/openclaw_engine/src/bybit_private_ws.rs:564）；每次 supervisor reconnect attempt 新 Arc；engine shutdown 隨 supervisor 終結 drop |
| cross_task_pattern | WS main loop `"op":"pong"` 接收端 `record_rtt()` push；emitter probe 端 60s sample read（per Wave B status: production 端尚未透過外部 Arc 注入接通；本 round Wave B 走 placeholder fresh 0-state Arc — 見 §2.1.3.a） |
| lock_primitive | `std::sync::Mutex<Vec<(Instant, u64)>>`；cap 64（60s × 1 ping/20s ≈ 3 sample 上限預留 headroom） |
| visibility | `pub`（含 `#[doc(hidden)]` `inject_sample_with_timestamp` test helper） |
| caller_chain | producer: `BybitPrivateWs::run()` main loop pong handler；handle exposer: `BybitPrivateWs::rtt_histogram_handle()`（rust/openclaw_engine/src/bybit_private_ws.rs:577-585，Wave A 已實裝但 main_health_emitters.rs Wave B placeholder 未接） |
| health_monitoring | YES — V106 row `api_latency__ws_rtt_p50_ms` / `__ws_rtt_p99_ms`；BUT Wave B 階段 emit chain placeholder disconnected from production supervisor（見 §2.1.3.a） |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 + PA-DRIFT-4 carry-over |
| migration_plan | Sprint 5+ Wave C：BybitPrivateWs supervisor signature 改造為「caller 注入 external Arc」pattern；main.rs Wave 接時拿 supervisor handle clone 替換 placeholder fresh Arc（per `rust/openclaw_engine/src/main_health_emitters.rs:174-205` 誠實揭露） |

##### §2.1.3.a Wave B placeholder 半實裝陷阱

per main_health_emitters.rs:206-220 + module note line 174-205（PA-DRIFT-4 round 2 MEDIUM-2 fix 揭露）：

- bybit_private_ws.rs:577-585 Wave A 已實裝 `rtt_histogram_handle()` expose accessor
- 但 main_health_emitters.rs:218-219 `build_real_api_latency_probe` 不呼叫 expose；每次走 `Arc::new(WsRttHistogram::new())` 0-state instance
- 後果：V106 `api_latency__ws_rtt_*` 30 天「全 0」染色不代表「WS 健康無 latency」，而是 emit chain 從 production supervisor disconnect
- Wave B 走 (a) doc 補注 + Sprint 5+ carry-over；本 round 不接 supervisor handle（needs `BybitPrivateWs::new()` signature 改造）

#### 2.1.4 WsDropoutCounter

| 欄位 | 值 |
|---|---|
| name | `WsDropoutCounter` |
| type_signature | `pub struct { samples: std::sync::Mutex<Vec<Instant>> }` |
| location | `rust/openclaw_engine/src/bybit_private_ws.rs:216-218` |
| owner_lifecycle | `BybitPrivateWs::new()` 內部構造（同 WsRttHistogram pattern）；每次 supervisor reconnect attempt 新 Arc |
| cross_task_pattern | WS run loop 6 接點 `record_dropout()` push（panic / disconnect / cancel 入口進 reconnect）；emitter probe 端 60s sample read（Wave B placeholder fresh Arc - 見 §2.1.4.a） |
| lock_primitive | `std::sync::Mutex<Vec<Instant>>`；cap 256；60s rolling window |
| visibility | `pub` |
| caller_chain | producer: `BybitPrivateWs::run()` 6 reconnect 入口；handle exposer: `BybitPrivateWs::dropout_counter_handle()`（rust/openclaw_engine/src/bybit_private_ws.rs:577-585，Wave A 已實裝但 main_health_emitters.rs Wave B placeholder 未接） |
| health_monitoring | YES — V106 row `api_latency__ws_dropout_count`；BUT Wave B 同 §2.1.3.a placeholder 半實裝 |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 Decision 3 cascade gate 預警（dropout > 5 / 60s 升 CRITICAL）+ PA-DRIFT-4 carry-over |
| migration_plan | Sprint 5+ Wave C 同 WsRttHistogram supervisor handle 改造（見 §2.1.4.a） |

##### §2.1.4.a Wave B placeholder 半實裝陷阱

同 §2.1.3.a；30 天 V106 `api_latency__ws_dropout_count` 全 0 是 emit chain disconnect 副作用，非 production WS 健康指標反映「無 dropout」。

### §2.2 Sprint 4+ Wave B — Health Emitter Cache + Bus（2026-05-23 接線完成）

per Sprint 4+ Wave B IMPL（commit 245216d1 + 4d4ff99f + 82351b61），main.rs scheduler wire-up 完整接線。

#### 2.2.1 PortfolioStateCache

| 欄位 | 值 |
|---|---|
| name | `PortfolioStateCache` |
| type_signature | 包在 `Arc<parking_lot::Mutex<PortfolioStateCache>>`；內部 `{ realized_pnl_history: VecDeque<(u64, f64)>, equity_history: VecDeque<(u64, f64)>, latest_exposures: Vec<PositionExposure>, last_update_ts_ms: u64 }` |
| location | `rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs:129-141` |
| owner_lifecycle | `build_risk_envelope_emitter()` 內 `Arc::new(ParkingMutex::new(PortfolioStateCache::new()))` 構造（rust/openclaw_engine/src/main_health_emitters.rs:326）；返 cache handle 給 `spawn_metric_emitter_scheduler` caller；engine shutdown 隨 Arc drop |
| cross_task_pattern | producer: 300s tick task `spawn_portfolio_state_update_task` 呼 `update_from_pipeline_snapshot`（push fill realized_pnl + equity + position notional）；consumer: `RealRiskEnvelopeSourceProbe::sample_now()` 端 emitter 300s sample read 5 calculator |
| lock_primitive | `parking_lot::Mutex<PortfolioStateCache>`；lock 時段 < 1ms（5 calculator 純讀）；不走 tokio::sync::Mutex（cache update task 是 sync block；avoid await-on-lock pattern） |
| visibility | `pub`（PositionExposure / new / update_from_pipeline_snapshot / cum_pnl_24h_usd / max_dd_pct_24h / position_count_active / correlation_avg_pairwise / concentration_top1_pct） |
| caller_chain | producer: `spawn_portfolio_state_update_task`（rust/openclaw_engine/src/main_health_emitters.rs ~line 519，目前 Wave B placeholder no-op tick；Wave C / Sprint 5+ 接 PaperState SSOT）；consumer: `RealRiskEnvelopeSourceProbe::{current_portfolio_cum_pnl_24h_usd, current_portfolio_max_dd_pct, current_position_count_active, current_correlation_avg_pairwise, current_concentration_top1_pct}` |
| health_monitoring | YES — ADR-0042 Decision 3 `risk_envelope` domain；V106 row `risk_envelope__cum_pnl_24h_usd` / `__max_dd_pct` / `__position_count_active` / `__correlation_avg_pairwise` / `__concentration_top1_pct` |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 + Sprint 2 Wave 2 Track F + PA-DRIFT-5 carry-over Sprint 2 §4.1 item 4 |
| migration_plan | Sprint 5+ Wave C：update task no-op → 接 PaperState SSOT；correlation calculator 接既有 `crate::scanner::scorer` correlation lookup 或新 rolling-window calculator（per risk_envelope_probe_impl.rs:101-105 doc）；可能加顯式 cap follow-up（per file line 113-128 burst 防禦留 caller throttle） |

##### §2.2.1.a F-2 NaN/inf sanitize（PA-DRIFT-5 round 2 P1）

cache update 端 `update_from_pipeline_snapshot` 對 NaN/inf realized_pnl / equity / notional fail-loud warn + skip push（rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs:201/217/235）；避 NaN 污染 24h sliding window sum 破壞 emitter classify ladder。

##### §2.2.1.b 三 mode (live/demo/paper) 共享 vs 獨立

per main_health_emitters.rs:305-316 — Wave B 採「engine-wide single cache」；既有 risk_verdict_ledger / position_snapshot 計算端是 per-engine 獨立但 emitter `risk_envelope__*` 共用 anomaly_id space（per spec §6.2）；Sprint 5+ PM 若拍板獨立 cache，本 fn 構造可加 mode 參數並各自 spawn update task。

#### 2.2.2 HealthEventBus

| 欄位 | 值 |
|---|---|
| name | `HealthEventBus` |
| type_signature | `pub struct { sender: tokio::sync::broadcast::Sender<HealthStateChangeEvent> }` |
| location | `rust/openclaw_engine/src/health/event_bus.rs:80-82` |
| owner_lifecycle | `spawn_metric_emitter_scheduler` 內 `Arc::new(HealthEventBus::new())` 構造（rust/openclaw_engine/src/main_health_emitters.rs:394）；返 event_bus handle 給 caller；engine shutdown 隨 Arc drop |
| cross_task_pattern | producer: M3 emitter scheduler / 6 DomainEmitter 內部 state transition fire `publish(event)`；consumer: Sprint 5 cascade subscriber（LAL Tier 降階 / Strategy reparam halt / alert routing；本 round 0 subscriber） |
| lock_primitive | `tokio::sync::broadcast::Sender` + capacity 256（per `HEALTH_EVENT_CHANNEL_CAPACITY`）；fail-soft publish — channel lagged 不算 fire fail（per spec §4.1 註） |
| visibility | `pub`（HealthStateChangeEvent / HealthEventBus / HealthEventSubscriber / new / with_capacity / publish / subscribe / receiver_count） |
| caller_chain | producer: M3 emitter 6 DomainEmitter `observe_classified` state transition 後 `publish`（per spec §4.1 step 5）；consumer: 本 round 0 production subscriber，仍 reserve subscribe interface 預埋 Sprint 5 cascade IMPL |
| health_monitoring | NO — bus 自身非 metric target；發布的 event 載荷是 6 domain transition（per HealthStateChangeEvent `domain` field 對應 ADR-0042 Decision 3 6 domain） |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 Decision 5（cascade subscriber 上限 8） + Sprint 2 Wave 1 Track A scaffold + spec §4.1 + §3.1 step 5 |
| migration_plan | Sprint 5+ cascade IMPL：接 4-8 subscriber（LAL Tier / Strategy halt / Alert router / GUI）；per ADR-0042 Decision 5；本 round 不接 cross-process channel；Sprint 5 才接 |

---

## §3 Registration Rules

### §3.1 新登記前必做（PA / E1 / E2 共同）

1. **grep verify name + signature 0 conflict**：repo 內未有同名 type / module-level binding
2. **caller_chain 必列舉 ≥ 1 producer + ≥ 1 consumer**（純 producer 無 consumer 屬 dead code，FAIL）
3. **health_monitoring 欄位必明示 YES/NO**：YES 必 link ADR-0042 6 domain 之一
4. **migration_plan**：明示 Sprint N+ 是否計劃改造；無計劃寫 `0`

### §3.2 E2 review 必檢條目

per `feedback_impl_done_adversarial_review` 2026-05-09 + `feedback_no_dead_params`：

1. caller_chain 真實 — grep production 端真實有 caller，不是「Wave N+ 接線時補」的承諾
2. lock_primitive 跨 await 邊界檢（async lock held across await 是 Track A round 1 MEDIUM-1 反模式）
3. fail-soft / fail-loud 是否與 spec 對齊（PortfolioStateCache F-2 NaN sanitize 是 fail-loud + skip；HealthEventBus publish 是 fail-soft；兩者非互換）
4. test-only helper（`inject_sample_with_timestamp`）走 `pub` + `#[doc(hidden)]` 而非 `#[cfg(test)]` 必註明原因（integration test crate visibility）

### §3.3 PA dispatch packet 必含

dispatch packet 中若 E1 IMPL 將引新 mutable singleton：

1. dispatch packet §X 條目「新 singleton 預登記」必列入：name / type_signature / location / cross_task_pattern
2. E1 IMPL DONE 後 PA / E2 / PM 收口任一方提示「補登 SSOT」task — 不能 skip 等下一輪 E2 catch（MEDIUM-1 escalate pattern）

### §3.4 反模式（禁忌）

per memory + 既往 E2 finding：

- **「struct-internal Arc 不需登記」誤判**：caller 端 own + inject pattern 雖然非 module-level static，但若 caller 構造的 Arc 跨 task 共享、engine 全週期 1 個 Arc instance、含 mutable state，仍登記（避「概念漏網」）
- **「placeholder fresh 0-state 等同接通 production」誤判**：WsRttHistogram / WsDropoutCounter Wave B 半實裝 — 30 天全 0 V106 row 不代表真實 production WS 健康（per §2.1.3.a / §2.1.4.a）；caller chain 必如實揭露「placeholder 未接 supervisor」
- **「test fixture mock 等同 production caller」誤判**：bybit_rest_client_tests.rs 內多處 `RestLatencyHistogram::new()` 是 mock fixture；caller_chain 必區分 mock 與 production
- **「ADR amend 必為單向 grow」誤判**：trim 是合理 governance 動作；但 trim 期間 SSOT 沒搬走 = 真實 gap（本 PA SSOT 建立修補此 gap）

---

## §4 Cross-reference with CLAUDE.md

### §4.1 CLAUDE.md §七 reference

CLAUDE.md `§七 Code And Docs Rules` line 165：

> New mutable singletons must be registered in the singleton table's current authority location before merge.

「current authority location」= 本 doc `docs/architecture/singleton-registry.md`（2026-05-23 PA 建立 SSOT 後）。

### §4.2 CLAUDE.md §九 reference

CLAUDE.md `§九 Code Structure Guardrails` line 196：

> New mutable singletons must be registered in the current singleton authority before merge.

「current singleton authority」= 本 doc。

### §4.3 是否修改 CLAUDE.md

**本 task PA verdict：不修改 CLAUDE.md inline**。理由：

1. CLAUDE.md trim 設計目標是「memory file 保持輕量 + 路由到 docs」；inline restore singleton 違 trim 意圖
2. 既有 §七 + §九 兩條 rule line literal 已含「current authority location」抽象表述；不依賴具體 path，加 cross-ref 後 path 變更不需動 CLAUDE.md
3. 替代 — `docs/README.md` index entry 增本 SSOT path（per docs governance R4 docs index sweep rule）= 路徑可達

### §4.4 path 變更需提醒處

未來如 SSOT 搬位（不建議；但若必），需同步更新：

- `docs/README.md` index entry
- 本檔 §4.1 + §4.2 path literal
- CLAUDE_CHANGELOG.md 記錄變更
- 若涉及 governance authority shift，補 ADR

---

## §5 Lessons Learned（本 PA SSOT 建立期間揭露）

### §5.1 CLAUDE.md trim 反模式

2026-05-02 trim 期間 §九 Singleton 表「收成單行」實際操作 = **整段 table 刪除沒搬位**。CLAUDE.md 保留 line 165 + 196 兩條 abstract rule 但 SSOT 0 hit。governance gap 維持 21 天才被 Sprint 4+ Wave B E2 round 2 MEDIUM-1 catch + escalate。

修法：trim 任何 inline reference table 時，**必同時**：

1. 建新 SSOT location（或選既有 location）
2. CLAUDE.md rule line 不變或加 cross-ref
3. CHANGELOG 明記「table moved to X」
4. archive snapshot 必註「new SSOT location = X」（archive 純被動快照不夠）

### §5.2 MEDIUM-1 不應在 E2 round 1 後才被 catch

E2 Wave B round 1 catch MEDIUM-1「6 new singleton 未登記」是合理；但根因「SSOT 0 hit」應在 dispatch packet 階段 PA 預判（per §3.3 規則 — PA dispatch packet 必含新 singleton 預登記條目）。Sprint 2 Wave 1+2 dispatch packet（2026-05-22）未含此項，是 PA gap。修法：本 SSOT 建立後 dispatch packet 模板必加「新 singleton 預登記」section（per §3.3）。

### §5.3 半實裝陷阱誠實揭露的價值

Wave B PA-DRIFT-4 round 2 揭露 WsRttHistogram / WsDropoutCounter placeholder 半實裝（§2.1.3.a / §2.1.4.a）— 不掩飾「V106 全 0」是 placeholder 副作用，不是真實 WS 健康。誠實揭露對 Wave C / Sprint 5+ wire-up scope 拍板極關鍵；caller_chain 欄位必反映此狀態。

---

## §6 Carry-over to Sprint 5+

### §6.1 Re-ingest archive 4 條 Python singleton

`docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` §九 line 77-80 4 條 Python singleton 仍在 production 跑：

1. `_H_STATE_INVALIDATOR` / `_LOCK` — h_state_invalidator.py（G3-08 Phase 1C 條件 spawn）
2. `MARKET_SCANNER` / `AUTO_DEPLOYER` / `_SCOUT_WORKER` — strategy_wiring_scanner.py
3. `HStateCacheSlot` — rust/openclaw_engine/src/ipc_server/slots.rs（Rust late-injected slot）
4. `CostEdgeAdvisorDbSlot` — rust/openclaw_engine/src/cost_edge_advisor_boot.rs（Rust late-injected slot）

本 task scope 嚴守 Wave A/B 6 新 singleton 登記；archive 4 條 re-ingest 屬 Sprint 5+ doc clean-up follow-up。建議 task：

- Owner: TW + PA
- Priority: P2 LOW（governance hygiene；non-blocker）
- Est: 1-2 hr（盤點 4 條當前 production state + 補 §1.3 完整欄位）
- 觸發條件: Sprint 5+ cascade IMPL 期間 docs/ doc-index sweep 順手

### §6.2 dispatch packet 模板補「新 singleton 預登記」section

本 task §5.2 + §3.3 邏輯衍生：dispatch packet 模板（docs/execution_plan/* / docs/agents/* 範本端）必加 section「新 mutable singleton 預登記」；E1 IMPL 前 PA 已明示。

- Owner: PA
- Priority: P2 (governance template hygiene)
- Est: 30 min (dispatch packet 模板 .md skeleton patch + 1 個 worked example)
- 觸發條件: 下次 Sprint dispatch packet 起草前

### §6.3 BybitPrivateWs supervisor signature 改造

per §2.1.3.a + §2.1.4.a Wave B 半實裝陷阱；Sprint 5+ Wave C 必：

1. `BybitPrivateWs::new()` signature 改 caller 注入 `Arc<WsDropoutCounter>` + `Arc<WsRttHistogram>`（替代當前內部 own）
2. main_health_emitters.rs `build_real_api_latency_probe` 從 supervisor handle clone Arc 替換 placeholder fresh Arc
3. 30 天 V106 `api_latency__ws_*` row 開始反映 production WS metric

- Owner: E1（Rust）+ E2（review）
- Priority: P1（unblocks 真實 WS health observability）
- Est: 4-6 hr E1 + 1 hr E2
- 觸發條件: Sprint 5+ cascade IMPL dispatch

### §6.4 PortfolioStateCache update task wire-up

per §2.2.1.b — Wave B placeholder no-op tick；Sprint 5+ Wave C 接 PaperState SSOT。

- Owner: E1 + PA
- Priority: P1（unblocks 真實 portfolio risk envelope V106 emit；當前 5 metric 全 0/baseline）
- Est: 4-6 hr E1 + 1 hr E2 + 0.5 hr PA spec amend（per-mode vs single cache 拍板）
- 觸發條件: Sprint 5+ cascade IMPL dispatch

---

## §7 Maintenance

- 新 singleton merge 前必 update 本 doc（per §3.1-§3.4 規則）
- E2 review 必檢條目（per §3.2）
- 每季度 PA 走一輪 audit：grep `pub struct.*Mutex|pub static\|lazy_static!\|once_cell::sync` 對齊本 doc list
- archive snapshot 不 reinstall（per §4.4）；歷史變遷追 git history + CLAUDE_CHANGELOG
- 路徑變更須同步 §4.4 4 處

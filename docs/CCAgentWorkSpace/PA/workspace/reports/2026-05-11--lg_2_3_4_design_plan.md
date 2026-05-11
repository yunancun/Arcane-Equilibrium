# PA Master Tech Plan — P0-LG-1 + P0-LG-2 + P0-LG-3 (LG-2 / LG-3 / LG-4 RFC IMPL)

Date: 2026-05-11
Owner: PA
Wave: Sprint N+1 Wave 1 D-prep
Status: Ready for PM dispatch (Wave 2 E1 × N)

---

## 0. 任務性質聲明

post W-D MAG-084 closure 後 critical path 推進。三個 ticket 對應 PA 2026-05-01 RFC v1：

| TODO ID | RFC v1 (2026-05-01) | 文件 |
|---|---|---|
| P0-LG-1 | LG-2 H0 Blocking Verification | `2026-05-01--lg2_h0_blocking_verification_rfc.md` |
| P0-LG-2 | LG-3 Provider Pricing Table Binding | `2026-05-01--lg3_provider_pricing_binding_rfc.md` |
| P0-LG-3 | LG-4 Supervised Live Gate | `2026-05-01--lg4_supervised_live_gate_rfc.md` |

本 tech plan **不重寫 RFC**，而是基於 2026-05-11 的代碼真實狀態，**識別 RFC 與 production 之間的 gap**、**設計 IMPL 任務並行拆分**、**識別副作用**、**為 PM Wave 2 派發提供 ready 規格**。

關鍵狀態（2026-05-11）：

- H0 Gate (Rust) 已完整接 hot path step_0_5。Demo + LiveDemo runtime 已 `h0_shadow_mode=false`（hard-block）；paper 仍 shadow。
- AccountManager fee runtime + IntentProcessor::fee_rate_for_intent 已完整；hourly refresh task spawning。Healthcheck `[45]` 已存在（PA 2026-05-05 ship per LG-3 RFC T2）。
- LiveAuthorization HMAC + LiveAuthWatcher (5s respawn) + DrawdownRevoke + EarnedTrustEngine T0-T3 + live_trust_routes / live_session_routes / live_session_endpoints 已完整。

LG-2/3/4 真正的剩餘工作 = **驗證 + 收口 + 規範化 + audit mirror + E2E acceptance + 防衛性增強**，不是「從零建構」。

---

## 1. Plan LG-1 ──── H0 Blocking Production Caller

### 1.1 現狀分析（基於 2026-05-11 代碼）

| 維度 | 狀態 | 證據 |
|---|---|---|
| H0 Gate 實作 | ✅ 完整 1073 LOC | `rust/openclaw_core/src/h0_gate.rs` |
| 5 sub-checks | ✅ freshness / health / eligibility / risk_envelope / cooldown | h0_gate.rs:269-312 |
| Hot-path SLA | ✅ <1ms 設計，stats.max_latency_us 追蹤 | h0_gate.rs:269 + GateStats |
| Production wiring | ✅ tick_pipeline/on_tick/step_0_5_h0_gate.rs | step_0_5:41 `h0_gate.check()` |
| Hard-block semantics | ✅ ControlFlow::Break → stops only → 早退 | step_0_5_h0_gate.rs:43-94 |
| Shadow-mode toggle | ✅ runtime IPC `patch_risk_config` 帶 `h0_shadow_mode` 欄位 | risk.rs:313, ipc_client.py:480 |
| Demo TOML 預設 | ✅ `h0_shadow_mode = false` (hard-block) | risk_config_demo.toml:171 |
| Live TOML 預設 | ✅ `h0_shadow_mode = false` (hard-block) | risk_config_live.toml:188 |
| Paper TOML 預設 | ✅ `h0_shadow_mode = true` (shadow only) | risk_config_paper.toml:187 |
| ctor 預設 | ⚠️ `shadow_mode: true` | pipeline_ctor.rs:75-76 (RRC-1-A3) |
| Hot-reload | ✅ pipeline_config.rs RMW 保留 shadow_mode 欄位 | pipeline_config.rs:105-109 |
| Metrics — stats clone | ✅ `pipeline.h0_gate.get_stats()` 在 CanaryRecord | commands.rs:1281 |
| Metrics — prometheus | ❌ 未接 `/metrics` endpoint | grep 結果 0 |
| E2E acceptance test | ❌ 未存在 `tests/h0_blocking.rs` | RFC LG-2 T1 待做 |
| Operator verification query | ❌ 未 ship 形式化 SQL/SOP | RFC LG-2 T2 待做 |
| Flip/rollback SOP | ❌ 未 ship 形式化文檔 | RFC LG-2 T3 待做 |
| 24h passive observation gate | ❌ healthcheck 未存在 | 新增 `[59] h0_block_acceptance` |

### 1.2 Target State

LG-1 完成 = 下列 5 同時成立：

1. **E2E proof**：Rust integration test 證明 `h0_shadow_mode=false` + 觸發 5 sub-check 任一 → `ControlFlow::Break` + 0 intent + 0 lease + 0 exchange dispatch
2. **24h passive acceptance**：demo + live_demo 各跑 24h，0 confirmed false-block / 0 open-order leakage / 0 lease consumed by H0-blocked intent / p99 H0 latency < 1ms / fail-closed proof 3+ 個 synthetic cases
3. **Metrics surface**：`GateStats` + 加上 5 個 per-sub-check block counters 鋪到 healthcheck `[59]`（passive_wait_healthcheck `check_h0_block_acceptance()`）+ 簡易 SQL 查詢（read `canary_records` join）
4. **Flip/rollback SOP**：documented operator command（`patch_risk_config` 帶 `runtime.h0_shadow_mode`）+ E2 confirm IPC handler 已 hot-reload + ctor `shadow_mode: true` 改為「ctor 內 default 由 TOML 載入路徑覆蓋」（避免「啟動瞬窗 shadow→demo TOML 載入 hard-block」的窗）
5. **Fail-closed semantic 文檔化**：H0 unhealthy → reject intent，下游 stops 仍處理；不允許 H0 死掉 → fully halt（這會 break stops 自我保護）

### 1.3 Hot Path SLA Maintenance

H0 check 在 step_0_5 已是首選 step，<1ms 設計成立。**LG-1 不引入新的 hot path 開銷**：

- Metrics fold 在 stats clone（已存在 `commands.rs:1281`），periodic snapshot 從 IPC 拉
- Prometheus endpoint 不在 hot path（IPC pull-mode，~5s 週期 OK）
- 5 個 per-sub-check counter 已在 `GateStats`（fields `blocked_freshness/health/eligibility/envelope/cooldown`），無需新增 atomic

### 1.4 E1 任務拆分（4 個並行可行）

| Task | Surface | Files | Owner Skill | 並行性 |
|---|---|---|---|---|
| **LG1-T1 E2E integration test** | Rust | `rust/openclaw_engine/src/tick_pipeline/tests/h0_blocking.rs` (新 ~300 LOC) | E1 (Rust + test) | ✅ 並行（單檔，0 conflict） |
| **LG1-T2 Healthcheck `[59]` h0_block_acceptance** | Python | `helper_scripts/db/passive_wait_healthcheck/checks_h0_block_acceptance.py` (新 ~200 LOC) + `runner.py` register | E1 (Python + SQL) | ✅ 並行（新 module） |
| **LG1-T3 SOP / runbook + ctor 預設修正** | Mix | `docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md` (新) + `pipeline_ctor.rs:75-76` 註釋更新 + E2 verify TOML 載入路徑 always 覆蓋 ctor default | E1 (docs + Rust ~10 LOC) | ✅ 並行（不同 surface） |
| **LG1-T4 Operator verification SQL** | Python | extend `risk_view_client.py` or `risk_routes.py` 新增 `GET /api/v1/risk/h0_block_summary` (新 ~120 LOC) | E1 (Python read-only route) | ✅ 並行 |

**E1 並行能力**：4 並行（T1 Rust / T2 Python healthcheck / T3 docs+ctor / T4 Python route），檔重疊 = 0。

**順序依賴**：T1 IMPL 完成 → T2 healthcheck 可在 production 拿到觀察樣本（依賴 24h 觀察期），但 T1+T2+T3+T4 可同次並行 ship；24h passive observation 是 ship 後事件。

### 1.5 Risk + Mitigation

| Risk | 嚴重度 | Mitigation |
|---|---|---|
| ctor `shadow_mode:true` 預設 vs demo TOML `=false` 啟動瞬窗（1-3s）內 H0 shadow → 漏 block | **中** | T3 改 ctor 預設 `shadow_mode: false`，並驗 TOML 載入路徑 always 覆蓋；E2 必審 hot-reload 邏輯 |
| 24h passive observation 期內出現「H0 block 但 lease 已 acquire」（lease 是 pre-H0 拉？） | **低** | RFC §Required Metrics 已預期：H0 是 pre-lease，lease consumption 必 0；T1 E2E test 即斷言此不變式 |
| H0 block 統計只有 stats clone（canary record 帶），無法跨 process 持久化 | **中** | T2 healthcheck 讀 canary_records 與 trading.fills 對 join；不需新增 PG 表 |
| Hard-block 改成 default 後策略 backtest 行為 drift | **低** | demo + live_demo TOML 已 hard-block 多月（per `risk_config_*.toml` git history）；行為已穩定 |
| H0 stats.max_latency_us 在 release build 是否仍 <1ms（無 instrumented build profile） | **中** | T1 E2E test 加 perf assertion p99 < 1ms（10k iter loop）；E4 regression 覆蓋 |

---

## 2. Plan LG-2 ──── Provider Pricing Binding

### 2.1 現狀分析（基於 2026-05-11 代碼）

| 維度 | 狀態 | 證據 |
|---|---|---|
| AccountManager fee cache | ✅ in-memory RwLock<HashMap<symbol, FeeRate>> | account_manager.rs:148 |
| Bybit fee-rate refresh | ✅ `GET /v5/account/fee-rate?category=linear` | account_manager.rs `refresh_fee_rates` |
| last_fee_refresh_ms tracking | ✅ AtomicU64 | account_manager.rs:154 |
| Hourly refresh task | ✅ `tasks::spawn_fee_rate_tasks` | RFC LG-3 §1 引用 |
| TIF-driven maker/taker | ✅ `IntentProcessor::fee_rate_for_intent` | RFC LG-3 §Pricing Sources |
| Conservative default seeding | ✅ `DEFAULT_TAKER_FEE 0.00055 / DEFAULT_MAKER_FEE 0.0002` | account_manager.rs:136-138 |
| Healthcheck `[45]` pricing_binding | ✅ DONE Sprint C R6-T7 (2026-05-05) | `checks_pricing_binding.py` |
| Healthcheck source 推斷 | ✅ seed_default / bybit_v5 / cold_default | checks_pricing_binding.py:42-47 |
| Healthcheck fail-closed rules | ✅ live + seed_default → FAIL / stale ≥24h → FAIL / 0 fills + engine >30min → WARN | checks_pricing_binding.py:55-62 |
| Contract test T1 (Rust) | ❌ Bybit fee parser + maker/taker dispatch + fallback unit-level test 未集中 ship | `tests/lg3_contract.rs` 待新建 |
| Startup assertion T3 | ❌ live spawn 前 `last_fee_refresh_ms` 檢查未存在 | LG-3 RFC §T3 待做 |
| Source marker enum/string | ⚠️ proxy via fee_rate 分佈推斷，無 explicit `FeeSource` enum | LG-3 RFC §T2 推薦加 enum |
| Category map | ⚠️ hardcoded `linear`，無 explicit map (spot/inverse 未來) | LG-3 RFC §Category |
| Stale threshold config 位置 | ⚠️ 未在 RiskConfig / BudgetConfig / 獨立 PricingConfig 明定 | LG-3 RFC §Open Questions |

### 2.2 Target State

LG-2 完成 = 下列 5 同時成立：

1. **Contract test pinning current behavior**：Rust unit test cover (a) Bybit fee-rate response parsing (b) PostOnly → maker / GTC → taker (c) demo unsupported endpoint fallback (d) mainnet unsupported endpoint refusal (e) hourly refresh task scheduling
2. **Startup assertion**：Rust engine 啟動 `build_exchange_pipeline` 前，live (mainnet + LiveDemo) spawn 必檢：(a) `last_fee_refresh_ms > 0` (b) `fee_rate_count() ≥ 25 active symbols` (c) live/mainnet source != `seed_default`；任一 fail → 拒 spawn + 寫 audit
3. **Source marker explicit enum**：`AccountManager::fee_source(symbol) -> FeeSource { BybitApi, DemoConservativeDefault, ColdDefault }` 公開 API；healthcheck `[45]` 同時讀 enum + 既有 PG proxy 雙寫對賬（任一 disagree → WARN 升 FAIL）
4. **Category map**：`account_manager.rs` 新增 `pub const ACTIVE_CATEGORY: &str = "linear"`；任何 fee 操作 first check category，misuse fail-closed
5. **Stale threshold config**：在 RiskConfig 新增 `[pricing]` section（`max_age_warn_minutes`, `max_age_fail_minutes`, `cold_default_acceptable_modes`），與 RiskConfig hot-reload 同走 ArcSwap

### 2.3 接入點 grep

```bash
# pricing-binding caller hot paths
grep -rn 'account_manager\.maker_fee\|account_manager\.taker_fee\|fee_rate_for_intent' /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ | head -20
# pipeline spawn pre-checks
grep -rn 'build_exchange_pipeline\|spawn_live_pipeline\|live_authorization::load_and_verify' /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ | head -20
# RiskConfig add new section
grep -rn 'RiskConfigRuntime\|pub runtime: RiskConfig' /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_types/src/ /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/config/ | head -10
```

### 2.4 E1 任務拆分（4 個並行可行）

| Task | Surface | Files | Owner Skill | 並行性 |
|---|---|---|---|---|
| **LG2-T1 Contract tests (Rust)** | Rust | `rust/openclaw_engine/src/account_manager_tests.rs` 擴展 + `tests/lg3_contract.rs` 新 (~400 LOC) | E1 (Rust + test) | ✅ 並行 |
| **LG2-T2 Startup assertion** | Rust | `bybit_rest_client.rs::build_exchange_pipeline` 加 pre-check (~80 LOC) + `live_authorization.rs` cross-ref | E1 (Rust hot path) | ⚠️ 需 LG2-T3 FeeSource enum 先 land（或同 PR 寫） |
| **LG2-T3 FeeSource enum + healthcheck cross-check** | Mix | `account_manager.rs` 加 enum + getter (~50 LOC) + `checks_pricing_binding.py` 加 IPC dual-source compare (~80 LOC) + 新增 `query_fee_source` IPC route (~60 LOC) | E1 (Rust + Python) | ⚠️ 與 T2 序列化（T3 先，T2 後） |
| **LG2-T4 RiskConfig [pricing] section + hot-reload** | Mix | `rust/openclaw_types/src/risk.rs` 加 `PricingConfig` struct + `risk_config*.toml` × 4 加 `[pricing]` section + `pipeline_config.rs` RMW 保留 | E1 (Rust config) | ✅ 並行（與 T1 不衝突；與 T2/T3 在 risk.rs 可能 conflict → merge order 先 T4） |

**E1 並行能力**：3 並行（T1 // (T3 → T2) // T4），但建議**序列化 LG2-T4 → LG2-T1 + LG2-T3 → LG2-T2** 以減少 risk.rs / account_manager.rs / RiskConfigRuntime 衝突。

**現實派工**：
- E1-A：LG2-T4（RiskConfig [pricing] section + TOML × 4）
- E1-B：LG2-T1（contract tests，等 T4 land 後跑）
- E1-C：LG2-T3 → LG2-T2 序列（同一 E1 連做）

### 2.5 Risk + Mitigation

| Risk | 嚴重度 | Mitigation |
|---|---|---|
| Bybit fee endpoint demo/live_demo 不支援，回 `seed_default` 被 startup assertion 誤判 → block live | **高** | RFC §Pricing Sources 已說明：demo + live_demo 可接受 `seed_default`，只 mainnet 不可；T2 startup assertion 必 check `BybitEnvironment::Mainnet` 才 enforce |
| Startup assertion timing race：fee_rate task spawn 後 ~10s 才首次 refresh，期間 spawn live pipeline 漏抓 | **中** | T2 加 `wait_for_first_refresh_or_timeout(30s)`；30s timeout → 拒 spawn live |
| RiskConfig [pricing] 加入 schema 變更，影響既有 4 TOML hot-reload | **中** | T4 ArcSwap RMW 路徑保留 read-modify-write 默認，向後相容；舊 TOML 無 [pricing] → fallback hardcoded RFC §Refresh Cadence 數值 |
| Healthcheck `[45]` dual-source 對賬若 disagree 噪音多 | **低** | 首階段 WARN 不 FAIL；2 週觀察期後升 FAIL；E2 必 review |
| FeeSource enum 變更需 cross-lang serialize | **中** | 用 string enum `"bybit_api" / "demo_conservative_default" / "cold_default"`（與 healthcheck `[45]` source 字串對齊），不引入新 JSON shape |

---

## 3. Plan LG-3 ──── Supervised-Live State Machine

### 3.1 現狀分析（基於 2026-05-11 代碼）

| 維度 | 狀態 | 證據 |
|---|---|---|
| Live authorization HMAC | ✅ LiveAuthorization + canonical_payload + sig | live_authorization.rs:1-715 |
| EarnedTrust T0-T3 | ✅ TIER_TTL_HOURS / TrustTier enum | earned_trust_engine.py:51, 817 LOC |
| Operator role auth | ✅ live_session_routes / live_trust_routes / live_session_endpoints | 共 2262 LOC |
| live_reserved global mode | ✅ Python side enforcement | CLAUDE.md §四 |
| OPENCLAW_ALLOW_MAINNET | ✅ Rust side | bybit_rest_client.rs |
| LiveAuthWatcher 5s respawn | ✅ Phase 3 state-machine watcher | live_auth_watcher.rs:1-970 |
| Drawdown auto-revoke | ✅ should_revoke + revoke_live_authorization | drawdown_revoke.rs:1-441 |
| 5-min re-verify | ✅ main.rs periodic | CLAUDE.md §四 |
| Decision Lease (path A) | ✅ Sprint 3 Track H+I retrofit + W-C evidence mode | CLAUDE.md §五 |
| GovernanceHub.acquire_lease | ✅ SM-02 path A | learning.lease_transitions V054 |
| **State machine 完整 IMPL** | ⚠️ **未完整**：draft_request → operator_review → supervised_live_candidate → signed_authorization → live_reserved_session → lease_bound_live_action → closed_or_revoked 7 狀態 SM 散落多檔，未集中表達 | LG-4 RFC §Proposed State Machine |
| **Approval RPC schema** | ⚠️ **未實作**：scope (symbols/strategies/max_duration_minutes) + risk_limits override + operator_reason + expires_at | LG-4 RFC §Approval RPC Schema |
| **Session-scoped override** | ❌ **未實作**：lease-bound `risk_limits` 動態 override（不寫永久 TOML）；Effective limit = min(P1 hard ceiling, session override, strategy/risk config) | LG-4 RFC §Risk Limit Override Flow |
| **Kill switch dual path** | ⚠️ API path: drawdown_revoke 已可 / IPC path: `trigger_live_auth_recheck` 已可；但**未集中表達為「kill switch」概念** | LG-4 RFC §Kill Switch |
| **Audit mirror SM-04 style** | ❌ event_id/ts/operator_id/request_id/decision_lease_id/engine_mode/symbols/strategies/risk_limits/action/result/reason 11 欄 append-only table 未存在 | LG-4 RFC §Audit Mirror |
| **State machine tests** | ⚠️ 個別狀態轉換有 unit test，**端對端 7-state walk-through** 未存在 | LG-4 RFC §Acceptance Tests |

### 3.2 Gap 分析

當前已有 5 個 gate (CLAUDE.md §四) 是 **single-flat-gate-list**，**不是 stateful SM**：

- 每次 spawn 檢 5 gate；spawn 成功 → 跑直到 watcher poll 失敗 → teardown
- 沒有「draft_request → operator_review」流程（operator 直接 POST renew 寫 authorization.json）
- 沒有「supervised_live_candidate」中間狀態（一旦 authorization.json 有效就直接 live_reserved）
- 沒有 lease-bound 風控 override（每筆 intent 各自 lease，但 lease 不附 session-scoped risk_limits）

LG-3 要建的 = **將 5 個 flat gate + EarnedTrust ladder + Decision Lease + drawdown + kill switch 統一表達為 7-state SM + Approval RPC + session override + audit mirror**。

### 3.3 Target State

LG-3 完成 = 下列 7 同時成立：

1. **SupervisedLiveStateMachine 集中表達**：新 module `supervised_live_sm.rs` (Rust) + `supervised_live_state.py` (Python) 雙端持狀態；state transition 透過 IPC + audit row 同步
2. **Approval RPC `/api/v1/live/supervised/approve`**：Python route 接收 LG-4 RFC §Approval RPC Schema 13 欄 JSON；驗 operator + live_reserved + expires_at 短期 + scope explicit + risk_limits ≤ P1 hard ceiling
3. **Session-scoped risk_limits override**：lease binding 帶 `session_override` field，Rust IntentProcessor 在 Guardian check 時取 `min(P1, session_override, strategy_config)`；不寫永久 TOML
4. **Kill switch dual-path 集中 API**：(a) API `POST /api/v1/live/supervised/kill?session_id=...` (b) IPC `trigger_kill_switch` cmd；兩者寫同一 audit event + 同時撤 authorization.json + revoke 所有 active leases
5. **Audit mirror table**：新 PG migration `V09x__supervised_live_audit.sql` 11 欄 append-only；writer 接 audit_writer task；read endpoint 給 GUI tab
6. **End-to-end SM walk-through test**：LG-4 RFC §Acceptance Tests 10 條 → Rust + Python integration test cover
7. **GUI surface**：13-tab console 新加「Supervised Live」sub-section in `live` tab（或新建 14-th tab，視 A3 verdict）

### 3.4 與既有元件整合

| 既有 | 整合方式 |
|---|---|
| LiveAuthorization HMAC | SM `signed_authorization` state 入口；signed_at_ms 記入 audit |
| EarnedTrust T0-T3 ladder | SM `operator_review → supervised_live_candidate` 階段 check tier；T0 cap 1 strategy / T3 cap 5 strategy |
| LiveAuthWatcher | SM external observer，watch authorization.json 變化 → 推 SM state transition |
| Decision Lease (SM-02) | SM `lease_bound_live_action` state；lease 帶 session_override |
| drawdown_revoke | SM `closed_or_revoked` 觸發路徑之一；audit reason="drawdown_session_halt" |
| Existing 5 gate (CLAUDE.md §四) | 每個 SM state transition 都跑 5 gate；fail 任一 → 拒 transition |

### 3.5 Per-AlphaSurface (W-AUDIT-8a Phase B) 整合

W-AUDIT-8a Phase A 已 land trait skeleton；R-4 per-alpha-source live promotion 是 **W-AUDIT-8g (DEFER N+7+)**。

**LG-3 與 W-AUDIT-8g 的關係**：

- LG-3 SM 在 N+1 ship 是 **session-scoped supervised live** (whole system promotion)，**不是 per-alpha-source**
- 後續 W-AUDIT-8g 會在 LG-3 SM 之上加 `LiveBudget(alpha_source_id, slice)` 維度
- LG-3 SM design 必須 **extensible**：state machine 加新 transition 不破舊；audit table 加 `alpha_source_id` column 為 nullable（N+7+ migration 才 backfill）

**Spec phase 不再為 LG-3 強加 per-alpha-source 限制**（per W-AUDIT-8g defer 至 N+7+）。

### 3.6 E1 任務拆分（複雜，建議分 Phase）

#### Phase 3.6.1 — Spec phase（PA 主導，0.5 sprint）

LG-3 是 P0-LG 三項中最複雜的（複雜度估 LG-1 的 4 倍、LG-2 的 2.5 倍）。PA 在 IMPL 派發前需 ship **detailed SM spec doc**（state diagram + transition table + IPC schema + audit mirror schema + GUI mock）。

| Spec deliverable | Owner | 工期 |
|---|---|---|
| `docs/execution_plan/2026-05-1x--lg3_supervised_live_sm_spec.md` (~2000 LOC) | PA | 1-1.5d |
| QC + BB + MIT review (PG schema + Bybit endpoint constraints + ML/audit interface) | parallel | 1d |

#### Phase 3.6.2 — IMPL phase（5 E1 並行）

| Task | Surface | Files | Owner | 並行性 |
|---|---|---|---|---|
| **LG3-T1 Rust SM state struct + transition fn** | Rust | `rust/openclaw_engine/src/supervised_live_sm/{mod,state,transition,tests}.rs` 新 (~1500 LOC) | E1 (Rust SM core) | ✅ 並行（新 module） |
| **LG3-T2 Python SM mirror + state persistence** | Python | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/supervised_live_state.py` 新 (~600 LOC) + JSON disk persistence pattern (mirror earned_trust_state.json) | E1 (Python SM mirror) | ✅ 並行 |
| **LG3-T3 Approval RPC route + validation** | Python | `live_session_routes.py` 擴展 (~250 LOC) + Pydantic models | E1 (Python route) | ⚠️ 依 LG3-T2 SM state import |
| **LG3-T4 Audit mirror PG migration + writer** | Mix | `sql/migrations/V09x__supervised_live_audit.sql` 新 + `rust/openclaw_engine/src/database/supervised_live_audit_writer.rs` 新 (~400 LOC) + healthcheck `[60]` | E1 (PG + Rust writer) | ✅ 並行 |
| **LG3-T5 Kill switch dual-path + session override + lease binding** | Mix | `live_session_routes.py` 加 kill route (~100 LOC) + `rust/openclaw_engine/src/ipc_server/handlers/supervised_kill.rs` 新 (~150 LOC) + `intent_processor` 改 `compute_effective_limits()` (~80 LOC) | E1 (Rust + Python) | ⚠️ 依 LG3-T1 SM state import |
| **LG3-T6 E2E acceptance tests (10 condition)** | Mix | Rust + Python integration tests cover LG-4 RFC §Acceptance Tests 10 條 | E1 (test) | ⚠️ 依 LG3-T1 + LG3-T2 + LG3-T3 ship 後 |
| **LG3-T7 GUI surface in live tab** | Frontend | `static/live-tab.js` extend (~300 LOC) + new SSE feed | E1a (frontend) | ✅ 並行（不依 T1-T6） |

**E1 並行能力**：5 並行（T1 // T2 // T4 // T7 // (T3+T5 依 T1+T2 後)），T6 是 ship 後事件。

### 3.7 Risk + Mitigation

| Risk | 嚴重度 | Mitigation |
|---|---|---|
| Rust+Python 雙端 SM 同步不一致（split-brain） | **高** | T1 + T2 雙端共用同一 state transition list（generate from spec doc）；audit table = SoT，雙端 state 都 reconcile from audit |
| Session override 繞過永久 TOML 變相寫 live 參數（違背 CLAUDE.md §四） | **極高** | T5 `compute_effective_limits = min(P1, session_override, strategy_config)`；session override 只能 tighten，不能 loosen；E2 + QC 必 review |
| Approval RPC 沒做完前 LiveAuthWatcher 既有路徑被誤導 | **中** | T3 + T1 land 後再 cutover；過渡期 dual-write authorization.json + SM state，兩者 disagree → fail-closed |
| Audit mirror table 寫入失敗導致 SM transition lost | **中** | T4 audit writer 用 outbox pattern（V050+/lease writer 既有）；SM transition 之 commit 必先 audit row INSERT success |
| GUI surface (T7) 同時打開「整 session 強制 close」按鈕 → operator 誤操作 | **高** | T7 加 5s countdown confirm modal（per W-AUDIT-7 F-system-mode-confirm 模式）；A3 review GUI |
| 7-state SM bypass paths（例：drawdown_revoke 直接刪 file，未經 SM transition）→ state desync | **高** | T1 加「external observer reconcile loop」：SM 每 30s 觀察 authorization.json + lease table + audit table，與內部 state 對賬，disagree → 強制設 `closed_or_revoked` |
| Spec doc 複雜度導致 PA 1-1.5d 寫不完 | **中** | 若超時，fallback「先 ship T4 audit mirror + T6 E2E test、T1+T2+T3+T5 留 N+2」分階段 |
| Per-AlphaSurface (R-4) 未來整合衝突 | **低** | 設計時加 `alpha_source_id NULL`-able；不為 R-4 強寫 schema 鎖死 |

---

## 4. 跨 Plan 整合

### 4.1 依賴順序

```
LG-1 (H0 production caller verify)  ──┐
                                      ├─→ 並行 IMPL（無強依賴）
LG-2 (Provider pricing binding)     ──┤
                                      │
LG-3 (Supervised live SM)            ──┘ 但 LG-3 IMPL 需先 spec phase
```

**理由**：
- LG-1 是 「驗證 + 規範化 已存在的 hard-block」，不改 H0 邏輯；安全可單獨 ship
- LG-2 是 「formalize 已存在的 fee runtime」+ 加 startup assertion；不改 fee 計算
- LG-3 是「集中表達 5 gate + EarnedTrust + Decision Lease + drawdown + kill switch 為 SM」；建在 LG-1 + LG-2 之上會更乾淨，但**強依賴**只在 spec 整合層（spec doc 引用 LG-1 H0 healthcheck + LG-2 pricing assertion）

### 4.2 W-AUDIT-9 Graduated Canary 前置關係

- **W-AUDIT-9 T1-T7 (Sprint N+0 已 DONE)** + **Stage 1 cohort 待 N+1 W6+W7 後啟動**
- LG-3 SM 與 W-AUDIT-9 SM **互補不衝突**：
  - W-AUDIT-9 SM = per-cohort canary stage (Stage 0/1/2/3/4)，決定 「shadow_mode_provider 對該 cohort 回什麼值」
  - LG-3 SM = per-session supervised live state，決定 「真 live 訂單能不能下」
- LG-3 SM `lease_bound_live_action` state 在 W-AUDIT-9 進到 Stage 3 以上才開放（policy gate，不是 SM 結構衝突）

### 4.3 W-AUDIT-8a (AlphaSurface) 並行衝突

- W-AUDIT-8a Phase B Tier 2 panel collector 在 N+1 W1（Rust panel_aggregator WS-first）
- 不與 LG-1/2/3 文件重疊：W-AUDIT-8a 改 `rust/openclaw_core/src/alpha_surface.rs` + 新 `panel_aggregator.rs`；LG-1 改 `tick_pipeline/tests/`、LG-2 改 `account_manager.rs` + `bybit_rest_client.rs`、LG-3 新 `supervised_live_sm/`
- 唯一可能衝突：LG-2 RiskConfig 加 `[pricing]` section 時，若 W-AUDIT-8a 同時改 RiskConfig schema → merge race。**Mitigation**：LG-2-T4 與 W-AUDIT-8a Phase B 在同一 sprint 內 PM 必序列化 risk.rs commit。

### 4.4 與 R-1/R-2/R-3/R-4 retire/reframe 不衝突

- R-1 → W-AUDIT-8a (active)
- R-2 → W-AUDIT-8e (DEFER N+4+)
- R-3 → W-AUDIT-8f (DEFER N+5+)
- R-4 → W-AUDIT-8g (DEFER N+7+)

LG-3 SM 是 LG-2/3/4/5 線性放權的**第一砖**，不替代 R-4 per-alpha-source；R-4 在 N+7+ 啟動時會在 LG-3 SM 之上加 alpha_source_id 維度（如 §3.5 已預告）。

### 4.5 整體 E1 Capacity 估計

per §0 Sprint Milestone Banner table，N+1 capacity = 4-6 E1（含 1 stand-by）。**LG-1 + LG-2 + LG-3** 在 N+1 全跑會擠爆 capacity（4 + 4 + 5+1 spec = 14 E1-week），建議分階段：

| Sprint | LG-1 | LG-2 | LG-3 | E1 用量 |
|---|---|---|---|---|
| N+1 W3-W4 | T1 / T2 / T3 / T4 (4 並行 ~1 sprint) | T4 → T1+T3 → T2 (3 並行 ~1 sprint) | **Spec phase** (PA 1-1.5d) | 4 + 3 = 7 E1-week-equivalent |
| N+2 W5-W6 | (24h passive observation) | (24h passive observation) | T1 / T2 / T4 / T7 並行 (~1.5 sprint) | 4 E1-week |
| N+3 W7-W8 | LG-1 sign-off | LG-2 sign-off | T3 / T5 / T6 (~1 sprint) → SM sign-off | 3 E1-week |

**N+1 capacity stress 點**：4-6 E1 cap；7 E1-week 在 W3-W4 = OK（2 週 × 4 E1 = 8 E1-week budget），無需 stand-by。

---

## 5. 最大 Risk 排序（PA 視角）

1. **LG-3 SM bypass paths split-brain (極高)** — Rust + Python + authorization.json + lease table + audit 5 個 SoT 可能 desync；external observer reconcile loop 是 critical defense
2. **LG-3 Session override 變相突破 P1 (極高)** — `compute_effective_limits` 必 `min`-only，不能 `max`；E2 + QC + MIT 三角 review
3. **LG-2 Startup assertion timing race (高)** — fee_rate task 首次 refresh 之前 spawn live → 漏抓；`wait_for_first_refresh_or_timeout` 是 critical
4. **LG-1 ctor `shadow_mode:true` 預設啟動瞬窗 (中)** — TOML 載入路徑 always 覆蓋 ctor default 必驗
5. **LG-3 GUI 強制 kill button 誤操作 (高)** — 5s countdown + A3 review

---

## 6. PM Wave 2 Dispatch 建議

### 6.1 Wave 2.1（PA spec finalize）

| 任務 | Agent | 工期 |
|---|---|---|
| LG-3 SupervisedLiveStateMachine spec doc | PA (本人) | 1-1.5d |
| QC + BB + MIT parallel review | parallel | 1d |
| PA spec v2 final | PA | 0.5d |

### 6.2 Wave 2.2（LG-1 + LG-2 IMPL 並行）

| 任務 | Agent | 工期 |
|---|---|---|
| LG1-T1 + LG1-T2 + LG1-T3 + LG1-T4 | E1 × 4 並行 | 2-3d |
| LG2-T4 → LG2-T1 + LG2-T3 → LG2-T2 | E1 × 3 序列 | 3-4d |
| E2 + E4 + A3 review | parallel | 1d |

### 6.3 Wave 2.3（24h passive observation）

| 任務 | 工期 |
|---|---|
| LG-1 + LG-2 24h passive observation (healthcheck [59] + [45] 升級驗) | 24h+24h = 48h elapsed |

### 6.4 Wave 2.4（LG-3 IMPL 並行）

| 任務 | Agent | 工期 |
|---|---|---|
| LG3-T1 + LG3-T2 + LG3-T4 + LG3-T7 | E1 × 4 並行 | 4-5d |
| LG3-T3 + LG3-T5 (依 T1+T2) | E1 × 2 序列 | 2-3d |
| LG3-T6 E2E test (依 T1-T5) | E1 × 1 | 2d |
| E2 + E4 + A3 + QC review | parallel | 1.5d |

### 6.5 Wave 2.5（Sign-off + audit）

LG-1 + LG-2 + LG-3 三方 sign-off + QA + PM 收口；audit row first batch land；GUI tab live。

---

## 7. PA 不做事項聲明（per profile.md）

- ❌ 本文件不寫 feature code，所有代碼示例為「接口 sketch」非 IMPL
- ❌ 不啟動 E1（PM 派發）
- ❌ 不發 commit
- ❌ 不改 TODO.md / CLAUDE.md（PM 收口）
- ❌ 不擴大 scope（R-1/R-2/R-3/R-4 R-5 留 W-AUDIT-8x wave）

---

## 8. 16 原則 Compliance Check

| # | 原則 | LG-1 | LG-2 | LG-3 |
|---|---|---|---|---|
| 1 | 單一寫入口 | ✅ 不新增 writer | ✅ AccountManager 維持唯一 fee writer | ⚠️ 新 SM transition writer，需經 audit_writer outbox (T4) |
| 3 | AI ≠ command | ✅ H0 pre-lease | ✅ N/A | ✅ SM `lease_bound_live_action` 強制 lease 在前 |
| 4 | 策略不繞風控 | ✅ 強化 H0 hard-block 證明 | ✅ stale pricing → cost gate 阻 open | ✅ session override 只能 tighten（T5 critical） |
| 5 | 生存 > 利潤 | ✅ Block 後 stops only | ✅ Mainnet 必 fresh pricing | ✅ drawdown_revoke 整合進 SM |
| 6 | 失敗默認收縮 | ✅ fail-closed reject intent | ✅ stale → block new opens / closes ok | ✅ Approval validation fail → reject + audit |
| 8 | 可解釋 | ✅ healthcheck [59] + SQL summary | ✅ healthcheck [45] dual-source | ✅ audit mirror 11 欄 reconstruct join |
| 11 | Agent 最大自主 | ✅ 不削 agent 能力 | ✅ N/A | ✅ Approval RPC 是 operator path，agent 自主仍走 lease |
| 13 | 成本感知 | ✅ N/A | ✅ Maker/taker explicit | ✅ N/A |

無原則破壞。

---

## 9. 完成序列

per PA 完成序列（CLAUDE.md profile.md）：

- ✅ 本報告存：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md`
- ⏳ 結論性報告複製到 `docs/CCAgentWorkSpace/Operator/`（PM 決定後做，不在本 PA tech plan scope）
- ⏳ memory.md 追加（本 session 結束時做）

---

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md`

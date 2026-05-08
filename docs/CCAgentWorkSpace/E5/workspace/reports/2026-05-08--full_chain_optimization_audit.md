# E5 全鏈優化審計 — 2026-05-08

**HEAD**：`4e2d2883`（Mac/Linux 同步）
**採樣時間**：2026-05-08 UTC（trade-core engine PID 3854831 / uvicorn 4 worker / DB 32 GB）
**Engine binary**：`rust/target/release/openclaw-engine` 25 MB ELF x86-64，**未 strip**（debug info 殘留）
**Live RSS**：engine 91 MB / uvicorn 4 worker × 28 MB ≈ 112 MB / Total ~203 MB（far below 60 GB headroom）
**範圍**：玄衡全程序鏈代碼 + DB schema + runtime 參數 + 文件大小 + 跨平台 readiness

> **本報告 E5 不改業務代碼，只審查 + 寫報告**。建議分級僅供 PA 排 Sprint，operator 終審。

---

## §1 Executive Summary

### 1.1 規模實證

| 維度 | 數值 | 變化（vs 2026-04-24 baseline）|
|---|---:|---|
| Rust 生產 LOC | ~184,100 | +49,100（持續增長，符合 Live 路徑就緒進度）|
| Python 生產 LOC | ~260,454 | 無顯著變化（main_legacy.py 維持 471 行，DEDUP 後穩定）|
| Rust 檔 >800 (warn) | 70 | +13（從 57 起步，bb_reversion / bb_breakout 已拆，新增 replay 系列）|
| Rust 檔 >2000 (hard) | **1**（`replay/runner.rs` 2467） | -7（-7：8→1，G5-09 / event_consumer split 結 8 violations）|
| Python 檔 >800 (warn) | 72 | +12 |
| Python 檔 >2000 (hard) | **1**（`tests/test_h_state_query_handler.py` 2641） | -1（main_legacy 從 5113→471 已閉環）|
| Engine binary | 25 MB | unstripped；strip 後預估 17-18 MB |
| Lock 數量 | 138 Rust + 508 Python = **646 處** | Rust ai_budget tracker 16+ 鎖未清，但已從巨型 fn 拆解 |

### 1.2 核心結論

1. **Rust hot path 性能在 SLA 軌跡內**（無新增熱點 critical violation；clone 計數從 115 顯著下降至 73 hot path 點）；惟 `runner.rs` 巨型 file 影響 cache locality + cargo incremental 編譯時間。
2. **Python 性能瓶頸不在熱路徑**，瓶頸在於 (a) DB 32 GB 中 ~909 MB 死數據；(b) 4 worker uvicorn 之間 leader election 反覆；(c) `copy.deepcopy` 在 lease/auth state machine 熱讀路徑上 10+ 處。
3. **Dead code / dead schema 清單實證**：
   - `learning` schema 30 表中 **20 表 0 row**（67% 死）— 大量 writer 未啟動或 schema 被 abandoned
   - `replay` schema 9 表中 **5 表 0 row**（55% 死）— Sprint A R3 後僅 4 表寫入
   - `observability` schema 6 表中 **5 表 0 row**（83% 死）— V004 Phase 4 ML obs 從未真實啟動
   - `trading.*_damaged_20260414_130607` 4 表共 **909 MB**（24+ 天前 bug recovery snapshot 未清理）
4. **18 blocker 真實 gap 確認**：
   - `H0_GATE.*\(\)` 業務調用實證 = **0**（PA 指控屬實，門控設計死於 wiring）
   - `CostEdgeAdvisor` 業務 caller 實證 = **0**（亦死於 wiring）
   - `executor_agent.py:224` `lambda: True` fail-close hardcoded 確認（block #8）
5. **跨平台 readiness 良好但 CI tuple 缺**：Rust 端 `/tmp/openclaw` 全部走 `unwrap_or_else(env)` fallback（合規）；無 CI workflow 包含 `aarch64-apple-darwin`，**Mac 部署無自動驗證**。

### 1.3 嚴重度 tally

| 等級 | 數量 | 主要範圍 |
|---|---:|---|
| Critical | 4 | runner.rs hard violation / DB 909 MB damaged 死數據 / engine 未 strip / `learning.governance_audit_log` 全 schema 0 row 揭發 LG-5 reviewer 死於 wiring |
| High | 11 | dead schema 25 表 / lambda:True / shadow_mode hardcoded / Python deepcopy hot path / ai_budget tracker 16+ 鎖 / json IPC 501 處 / collation warning 噪音 / lg5 schema drift 2 列 / cost_edge_advisor 0 caller / H0_GATE 0 caller / CI tuple 缺 |
| Medium | 9 | runner.rs 32% comment / event_consumer 拆後仍 1195+1144 / scanner/scorer.rs 1613 / instrument_info 1008 / replay_full_chain_routes 1765 / mlde_demo_applier 1610 / global keyword 104 處 / type-ignore noqa 386 處 / Pydantic model 111 |
| Low | 6 | print() in CLI tools / sleep() in daemon thread (合規但可改 Event.wait) / 雙語注釋舊 block 未移除 / pyo3 target/ 殘留 / readonly_observer_pipeline scripts 散落 / 9 個 #[allow(dead_code)] phase placeholder |

**總計**：30 項 actionable opportunity（Critical 4 / High 11 / Medium 9 / Low 6）。

---

## §2 Dead code + Duplicate logic 清單

### 2.1 Critical（直接拖累 DB / 編譯 / 部署）

#### C-1 PG `trading.*_damaged_20260414_130607` 4 表共 909 MB 死數據（24 天前 bug recovery）

| 表 | rows | size |
|---|---:|---:|
| `risk_verdicts_damaged_20260414_130607` | 4,183,014 | **903 MB** |
| `fills_damaged_20260414_130607` | 17,265 | 4 MB |
| `intents_damaged_20260414_130607` | 7,684 | 1.3 MB |
| `orders_damaged_20260414_130607` | 4,509 | 0.6 MB |
| **小計** | 4,212,472 | **~909 MB** |

歷史：2026-04-14 13:06 dump，恢復 + RCA 已完成（`docs/archive/2026-04-30--62finding-batch-A-to-F.md`）。**24 天無人引用**。
**建議**：dump bin 至 NAS 後 `DROP TABLE`，回收 ~909 MB（DB 32 GB 的 2.8%）。**E5 不改 DB**，由 PA 派 E1 + ops。
**位置**：`schema=trading` / 對應 dump SQL 在 `helper_scripts/db/` 應有 reference。

#### C-2 Rust `replay/runner.rs` 2467 LOC — 唯一硬上限違反

- **位置**：`rust/openclaw_engine/src/replay/runner.rs:2467`
- **comment ratio**：795/2467 = **32.2%**（高於合理基線 ~20%）
- **影響**：cargo incremental 重編 ~3-5s 額外（單檔過大 → LLVM IR 生成慢）
- **建議**：拆為 `runner/{config,scheduler,reporter,calibrator,metrics}.rs` 5 sibling，pattern 同 G5-09 tick_pipeline split 模板
- **預估收益**：拆後最大 sibling <800，cargo incremental -2s, IDE LSP -50% latency

#### C-3 Engine binary 未 strip

- **檔案**：`/home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine`
- **當前**：25 MB ELF, **not stripped**（含 debug symbol）
- **建議**：在 `Cargo.toml [profile.release]` 加 `strip = true` 或 `strip = "symbols"`
- **預估收益**：binary 25→17 MB（-32%）；OS file cache 命中率 ↑；冷啟動更快
- **風險**：**core dump 失去 symbol**，需保留 debug binary 給 GDB（單獨在 `target/release-debug/`）

#### C-4 `learning.governance_audit_log` 全表 0 row — LG-5 reviewer 死於 wiring 證據

- **schema**：`learning.governance_audit_log` n_live_tup = 0
- **caller**：`governance_hub_live_candidate_review.py:53/623` 應每批 review 寫一筆
- **真實情況**：Sprint A R3 至今 0 row 累積，與 PA panorama "[42]/[42b] LG-5 reviewer 0 audit row" 鎖定一致
- **不是 dead schema，是 wiring 缺失**：sibling CC `463890d` 已 land Lg5ReviewConsumer 但未 deploy
- **建議**：deploy 後 24h re-check；E5 標 "active wiring blocker"，不刪 schema

### 2.2 High（顯著死碼或重複）

#### H-1 25 表跨 3 schema 0 row 死掉

| Schema | 表（n_live_tup=0） | 數量 |
|---|---|---:|
| `learning` | linucb_migrations / rl_transitions / weekly_review_log / pattern_insights / decision_shadow_fills / exit_features / decision_shadow_exits / cost_edge_advisor_log / governance_audit_log / lease_transitions / foundation_model_features / promotion_pipeline / ml_parameter_suggestions / bayesian_posteriors / symbol_clusters / teacher_directives / directive_executions / experiment_ledger / ai_usage_log / linucb_state_archive | 20 |
| `replay` | mlde_replay_veto_log / business_kpi_snapshots / audit_incident_summaries / tier_promotion_approval / handoff_requests | 5 |
| `observability` | scorer_predictions / model_performance / drift_events / feature_baselines / data_quality_events | 5 |
| **合計** | | **30** |

部分屬「writer 接線中」（V059/V060 LG 系列），部分屬「實驗 placeholder 從未啟動」（symbol_clusters / teacher_directives / linucb_state_archive）。
**建議**：PA 派 E3 + MIT 走 30 表 1-by-1 audit，確定哪些是 active wiring 待啟、哪些可 DROP；E5 不可單方面刪 schema。
**估算**：若 50% 可 DROP，回收 ~5 MB schema overhead + index entry，主要是 cognitive load reduction。

#### H-2 `executor_agent.py:224` lambda:True fail-close hardcoded（block #8）

- **位置**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:224`
- **代碼**：`shadow_mode_provider if shadow_mode_provider is not None else (lambda: True)`
- **影響**：shadow_mode_provider 注入時 g3-03 Phase B `executor_config_cache.py` 的 ArcSwap-equivalent 無法翻轉到 live；ExecutorAgent 永遠 shadow
- **建議**：(a) 直接 `raise RuntimeError("ExecutorAgent requires shadow_mode_provider injection")` fail-loud；(b) 或加 `OPENCLAW_EXECUTOR_REAL_LIVE=1` env override 路徑
- **預估收益**：解 18 blocker #8，是 LG-5 IMPL 的前置之一

#### H-3 `H0_GATE` 業務調用 0 處（block #9）

- 全 grep 無 `H0_GATE.{check,evaluate,decide}(` 業務調用
- 只有 `paper_trading_routes.py:64` import / `paper_trading_wiring.py:291` create / `governance_extended_routes.py:574` log status
- **DOC-02 spec 死於 wiring**：H0Gate class 設計 + 實裝在 `h0_gate.py` 但無一條交易路徑會經 H0_GATE 阻擋
- **建議**：等 LG-2 RFC `5ce777b` IMPL 進場；E5 不修；標 "blocker confirmed"

#### H-4 `CostEdgeAdvisor` 業務 caller 0 處（block #10 共生）

- `learning_engine/cost_edge_advisor.py` 定義 class + Rust `cost_edge_advisor_boot.rs` daemon 結構俱全
- 但 `OPENCLAW_COST_EDGE_ADVISOR != "1"` 默認 OFF + 0 Python production caller
- DB `learning.cost_edge_advisor_log` n_live_tup = 0 → 從未寫入
- **建議**：PA 決定是 (a) 啟動 env + 接線 / (b) DROP class + schema 統一刪。**E5 不刪**。

#### H-5 Python `copy.deepcopy` 10+ 處在熱讀路徑

| 檔 | 行 | 場景 |
|---|---:|---|
| `decision_lease_state_machine.py` | 507 | per-lease read |
| `decision_lease_state_machine.py` | 614 | active leases bulk read |
| `decision_lease_state_machine.py` | 618 | bridgeable leases bulk read |
| `authorization_state_machine.py` | 512 | per-auth read |
| `authorization_state_machine.py` | 614 | bulk auth read |
| `pnl_ops.py` | 144/263 | per-snapshot read |
| `risk_governor_state_machine.py` | 483 | state read |
| `main.py` | 48/84 | state compile / mutate |

**問題**：每讀一次 lease/auth 都 deepcopy 整個 dict — Python deepcopy 對 nested dict 是 O(n) clone。
**估算**：lease 讀路徑每秒 ~5-10 calls × 50 leases × ~1000 fields = 250k field copies/sec。
**建議**：用 immutable `dataclass(frozen=True)` 或 pydantic frozen model 取代；或 `dict.copy()` shallow + 顯式 nested copy 必要欄位。
**預估收益**：lease/auth state read 路徑 -30% latency。

#### H-6 ai_budget tracker `_lock` 16+ 處連續鎖

- 已知熱點（4 月底 audit memory）；當前狀態：**仍未拆**
- 建議：`Mutex<Tracker>` 改為 `RwLock<Inner>` + per-strategy ArcSwap counter
- **位置**：`rust/openclaw_engine/src/ai_budget/tracker.rs`（檔不大，重構成本低）

#### H-7 `json.loads / json.dumps` 501 處 Python serde

- IPC 路徑大宗。每秒 IPC RPS 估算 ~30-50（健康 + GUI request + ML inference broker）
- 主要熱點：`ipc_dispatch.py` / `ipc_client.py` / `ml_routes.py`
- **建議**：(a) IPC binary protocol 改 MessagePack（msgpack-python 比 stdlib json 快 1.5-3×）；(b) 或保持 JSON 但用 `orjson`（C-extension JSON，比 stdlib json 快 3-10×）
- **預估收益**：IPC round-trip P50 -10-30%；對 5ms SLA 達標有幫助
- **風險**：協議升級需雙端同步；MessagePack 可用 transition flag

#### H-8 lg5 column does not exist（API log 揭發 schema drift）

- API log: `lg5 fetch_live_cost_regime failed err=column "slippage_bps" does not exist`
- API log: `lg5 fetch_r6_daily_snapshots failed err=column "net_bps_after_fee" does not exist`
- **影響**：lg5 healthcheck 永久 FAIL，cron 每小時噴錯 → 噪音 + 0 真實 reviewer 數據
- **建議**：E2 派 E1 + MIT，1-2h 修 schema or column rename；高頻噪音清理
- **位置**：`learning/lg5_*` 相關 query 待 grep

#### H-9 無 CI workflow 包含 aarch64-apple-darwin

- `.github/workflows/` 無 yml；本地無自動 cross-compile 驗證
- CLAUDE.md §七 ★★ "項目必須隨時可以部署在 macOS 上運行"
- M5 Ultra 部署目標但 0 持續整合驗證
- **建議**：建 `.github/workflows/ci.yml` 跑 `cargo check --target aarch64-apple-darwin --release`（不需 build full binary，check 只 100 秒）；matrix `[x86_64-unknown-linux-gnu, aarch64-apple-darwin]`
- **預估收益**：apple silicon regression 提早 1 sprint 發現

#### H-10 collation warning noise

- 每次 `psql` 連線都報 `WARNING: database "trading_ai" has no actual collation version, but a version was recorded`
- log noise + 真實 audit 結果被淹沒
- **建議**：`ALTER DATABASE trading_ai REFRESH COLLATION VERSION;`（1 行 SQL，10s 執行）

#### H-11 V059 edge_estimate_snapshots 標 dead 不準確

- PA panorama 列為 "3 dead schema" 之一
- 實證：`learning.edge_estimate_snapshots` n_live_tup = **457**，被 `replay_full_chain_routes.py:921-993` 真實讀寫（V059 historical edge query）
- **不是 dead，是 active**；PA panorama 應更正

### 2.3 Medium（可讀性 / 結構）

#### M-1 `replay/runner.rs` 32% comment ratio

- 795 注釋行 / 2467 LOC = 32.2%（合理基線 ~15-20%）
- 多為 2026-05-05 governance change 之前的雙語對照
- **建議**：依 governance 「修改既有 block 移除英文」原則漸進清理；單獨抽 ticket 不必，refactor 順手做

#### M-2 event_consumer 拆後 mod.rs 278 + handlers 1195 + dispatch 1144（共 2617）

- G5-07 split 確認後 mod.rs 從 1695→278 是大進展
- 但 `loop_handlers.rs` 1195 / `dispatch.rs` 1144 兩個 sibling 仍 >800
- **建議**：依事件種類再切（market_data / control_command / risk_event / outcome）

#### M-3 Rust 高 LOC sibling top 5（>1500，介於 warning 與 hard 之間）

| 檔 | LOC |
|---|---:|
| `paper_state/tests.rs` | 1668（測試 OK，主檔 1135 OK）|
| `scanner/scorer.rs` | 1613 |
| `bin/replay_runner.rs` | 1599 |
| `intent_processor/tests.rs` | 1556 |

scanner/scorer.rs / replay_runner.rs 主檔 >1500，建議下個 sprint 拆。

#### M-4 Python `replay_full_chain_routes.py` 1765 LOC

- 規範 >800 warn / >1500 推薦拆
- 該檔承擔 replay 完整鏈接 + V059/V060 historical query + report assembly
- **建議**：拆成 `replay_full_chain/{routes,historical_query,report_assembly,v059_v060_compat}.py`

#### M-5 `mlde_demo_applier.py` 1610 LOC

- ML training pipeline 的 demo applier
- 建議按 stage 拆（ingest / feature / model / verdict / writer）

#### M-6 Python global keyword 104 處

- 多在 strategy_wiring* / ipc_dispatch.py / paper_trading_wiring.py / 各 routes 文件
- 部分為 legitimate singleton late-bind（CLAUDE.md §九 表登記過）；少數可能為遺留

#### M-7 type: ignore + noqa 386 處

- 3 級 type-ignore 累積；表示 mypy strict 一直未能完整通過
- E5 不在範圍；建議 PA 派 E2 走批 mypy clean-up wave

#### M-8 Pydantic model 111 + class def 459

- model 結構 OK，但部分 helper class 過多（governance_hub.py 1228 LOC 內含多個 sub-class）
- 不算嚴格 violation；但 cognitive load high

#### M-9 9 處 `#[allow(dead_code)]` phase placeholder（非死碼）

- pipeline_slot.rs:110/139/246/250 phase 2 placeholder
- live_auth_watcher.rs:479 prod 用 `from_parts` 但保留 one-shot constructor
- strategies/grid_trading/mod.rs:183 / constructors.rs:91/153 ML/test wrapper
- **不刪**：明確註明為 future phase 接線預留；E5 不誤刪

### 2.4 Low（雜項）

#### L-1 print() in CLI scripts（readonly_observer_pipeline / 6 處）— 不違反

- print() 在 CLI tool（main entry）為合規；非 routes / library
- 不需處理；E5 標 informational

#### L-2 daemon thread sleep 5+ 處用 `time.sleep`

- reconciliation_engine.py:947 / bybit_demo_sync.py:135/142 / ttl_enforcer.py:519 / scout_worker.py:168 / grafana_data_writer.py:195
- 設計層面合規（daemon thread offload）；但長期應改 `Event.wait(timeout)` like edge_estimator_scheduler.py SHUTDOWN-PRIMITIVE-1 已做的
- **建議**：低優先；wave shutdown primitive 接線

#### L-3 雙語注釋舊 block 未清

- governance change 2026-05-05 後新 block 中文 only，舊 block 不主動清
- E5 不在範圍；refactor 順手

#### L-4 `rust/target/` 含 `openclaw_pyo3` debug 殘留

- `rust/target/debug/deps/openclaw_core.d` 還引 `openclaw_pyo3/` 已刪 crate
- 不影響 release build；只占 ~50 MB target/ 空間
- **建議**：`cargo clean -p openclaw_core` 一次或 ops 定期清理

#### L-5 readonly_observer_pipeline scripts 散落

- 12 個 CLI 工具放在 `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/`
- 結構合理但缺 SCRIPT_INDEX

#### L-6 ai_service_client.rs:24 `DEFAULT_SOCKET_DIR` 純 const

- 雖然 `resolve_socket_path()` 純 fn 內最後 fallback；建議改為 `OPENCLAW_DEFAULT_SOCKET_DIR` env 可 override
- 純衛生；非阻塞

---

## §3 Rust hot path 性能審計

### 3.1 SLA 對比

| 路徑 | SLA | 採樣方法 | 結論 |
|---|---|---|---|
| H0 Gate | <1ms | grep 0 production caller | **N/A — 無流量驗證**（block #9）|
| Tick path | <0.3ms | engine 1h+ 跑無告警；clone count 73 (vs 115 baseline) | 無新增 critical 違反；持續優化中 |
| IPC round-trip | <5ms | dispatch.rs 結構合理；JSON serde 138 處（合理）| **未實證**；需 py-spy + tcpdump 跨端 |

無 production engine attach（避免影響 live demo flow）；本節以 grep + structure analysis 為主，非實時 trace。

### 3.2 Rust hot path 結構觀察

- **clone 計數**（hot 4 檔）：tick_pipeline/mod.rs **0** + commands.rs 22 + step_4_5_dispatch.rs 46 + intent_processor/mod.rs 5 = **73**（vs 4-24 baseline 115，**-37% 進展**）。
- **Mutex/RwLock**：138 處（vs 4-24 ~120）；增量主要在 h_state_cache + lease audit writer
- **ArcSwap 真實使用**：`edge_predictor/mod.rs:140-180`（per-strategy hot reload F9 guard）+ `live_auth_watcher.rs:44/103`（每次 spawn 5ns 重讀）— 健康
- **Atomic 226 處**：counter / flag 大量原子化，鎖粒度合理
- **tokio spawn 138 處**：分散式合理（多數是 writer + watchdog）
- **spawn_blocking** 1 處（`live_auth_watcher.rs:891`）+ 1 處註解；可接受

### 3.3 Rust 結構問題（影響 hot path 維護性）

| 問題 | 位置 | 嚴重度 | ROI |
|---|---|---|---|
| `runner.rs` 2467 (replay 路徑非 tick hot path) | `replay/runner.rs` | Critical | 高 |
| `event_consumer/loop_handlers.rs` 1195 + `dispatch.rs` 1144 | event_consumer/ | Medium | 中 |
| `intent_processor/mod.rs` 1215 + `router.rs` 1037 | intent_processor/ | Medium | 中 |
| `tick_pipeline/commands.rs` 1339 + `on_tick/step_4_5_dispatch.rs` 1326 | tick_pipeline/ | Medium | 中（hot path）|
| `scanner/scorer.rs` 1613 | scanner/ | Medium | 中 |
| `bybit_private_ws.rs` 1413 | (single) | Medium | 低 |
| `instrument_info.rs` 1008 | (single) | Medium | 低 |
| `database/trading_writer.rs` 1149 | database/ | Medium | 低 |
| `paper_state/maker_stats.rs` 1135 | paper_state/ | Medium | 低 |
| `claude_teacher/applier.rs` 1072 | claude_teacher/ | Medium | 低 |

### 3.4 Rust 性能微優化（非 SLA 改善但累積）

1. **`runner.rs` 32% comment** — split 順手清舊雙語
2. **paper_state/maker_stats.rs 1135** — maker fill rate 計算路徑，每筆 fill 觸發；走 binary release flamegraph 確認 hot tier
3. **edge_predictor/mod.rs ArcSwap 用 Arc<ArcSwap<Option<Arc<dyn>>>>** — 三層 Arc 包裝；可考慮 `arc_swap::cache::Cache` 進一步 thread-local 緩存

### 3.5 Engine binary strip

`Cargo.toml [profile.release]` 加：
```toml
[profile.release]
strip = "symbols"     # 25 → ~17 MB
codegen-units = 1     # better LTO（編譯慢但 binary 緊湊）
lto = "thin"          # 已可能有
```
**收益**：cold start RSS -8 MB；OS file cache hit ↑；M5 Mac 部署時頁表壓力 ↓

---

## §4 Python hot path 性能審計

### 4.1 Python 真實 hot path

| 路徑 | 採樣方法 | 結論 |
|---|---|---|
| FastAPI /api/v1/* request | 4 worker uvicorn RSS 28 MB / worker | OK；但 main.py 729 行偏大 |
| ipc_dispatch.py shared client | `_SHARED_IPC_SLOTS` 真實使用，ml_training/mlde_demo_applier.py 也用 | **健康** |
| state machine read | `decision_lease/authorization` 全 deepcopy 路徑 | **bottleneck** (H-5) |
| edge_estimator_scheduler | hourly cycle 187 cells / 59 updated/cycle | OK |
| reconciliation_engine | daemon thread loop time.sleep 1s | OK |

### 4.2 Python 鎖審計

- 508 處 lock-related 鎖點 (`self._lock` / `with self._`)
- E5 採樣未 attach py-spy（避免影響 live engine）；但歷史 baseline 知主要 thread:
  - `ttl_enforcer._sweep_thread` (519:_sweep_interval_seconds)
  - `reconciliation_engine` (947:_interval)
  - `edge_estimator_scheduler` (Event.wait pattern, OK)
  - `bybit_demo_sync` (135:initial delay 10s + cycle)
  - `scout_worker` (168:1s)
  - `grafana_data_writer` (195:_interval)
- **共 6 daemon thread**，每 thread 持續 sleep + lock acquire；M5 Mac 部署時 thread overhead 與 GIL 影響需驗

### 4.3 Python serde 開銷

- json.loads / json.dumps: **501 處** (vs 4-24 ~480)
- 主要在 ipc_dispatch.py / ipc_client.py / ml_routes.py / paper_trading_routes.py
- **建議**：(a) 全替換為 `orjson` 透明替代（drop-in）— 預估 IPC 序列化 -30-50% latency
- 或 (b) 上 MessagePack 二進制協議（升級成本高，雙端同步）

### 4.4 Python deepcopy hot path（H-5 詳述）

- 10+ 處 `copy.deepcopy` 在 lease/auth state read 路徑
- 估算：lease 讀路徑每秒 ~5-10 calls × 50 leases × deepcopy O(n)
- **建議改型**：`@dataclass(frozen=True)` 或 pydantic `model_config={"frozen": True}` 取代；或顯式 shallow copy + 必要 nested copy

---

## §5 PG 讀寫熱路徑審計

### 5.1 DB 容量分布

| Schema | 表數 | 主要表 + 大小 |
|---|---:|---|
| trading | 17 | decision_features 8.7 GB / decision_context_snapshots 7.0 GB / decision_outcomes 246 MB |
| _timescaledb_internal (chunk) | 多數 | _hyper_37_156 / 229 / 141 為 fills/orders/intents 主數據 |
| learning | 30 | 20 表 0 row（67% 死）|
| replay | 9 | 5 表 0 row（55% 死）|
| observability | 6 | 5 表 0 row（83% 死）|
| trading.*_damaged_2026* | 4 | **909 MB 死數據** |
| **DB total** | | **32 GB** |

### 5.2 PG 性能問題

| 問題 | 嚴重度 | 修復成本 |
|---|---|---|
| 909 MB damaged dump 24+ 天無人引用 | Critical | 1h（dump + DROP） |
| pg_stat_statements 未啟用 → 無慢 query 觀察 | High | 5min（`shared_preload_libraries`）|
| collation warning 噪音 | Medium | 10s（`ALTER DATABASE REFRESH COLLATION VERSION`） |
| lg5 schema drift（slippage_bps / net_bps_after_fee）| High | 2h |
| 25 表 0 row（learning + replay + observability）| High | 4-8h（1-by-1 audit）|

### 5.3 Top 10 PG opportunity

1. **DROP `trading.*_damaged_20260414_130607` 4 表** — 回收 909 MB
2. **啟用 pg_stat_statements** — 性能可觀察前置
3. **REFRESH COLLATION VERSION** — log noise 一鍵清
4. **修 lg5 schema drift** — 解 healthcheck 永久 FAIL
5. **30 表 0-row audit** — 部分 wiring 接線 + 部分 DROP
6. **decision_features 8.7 GB hypertable chunk policy** — 確認 retention + compression policy（PG 4-8 GB 限制下 chunk 必壓縮）
7. **TimescaleDB chunk 自動 compression** — `compress_hyper_53_*` chunks 0 live_tup 但有 seq scan，已壓但 read 路徑可優化
8. **decision_context_snapshots 7 GB** — `attribution_chain_ok=false 84.6%` 揭發 ML training data 質量；若清掉可大量回收
9. **per-schema work_mem** — `learning` schema 多 ML 表 → bigger work_mem；`trading` 熱寫 → smaller transaction-scoped
10. **JSONB index** — risk_verdicts 等多 jsonb column 是否走 GIN index（未驗證）

---

## §6 檔案大小違規清單

### 6.1 Hard violation（>2000，必拆）

| 檔 | LOC | 性質 | 拆分建議 |
|---|---:|---|---|
| `rust/openclaw_engine/src/replay/runner.rs` | **2467** | production | 拆 5 sibling: config/scheduler/reporter/calibrator/metrics |
| `program_code/.../tests/test_h_state_query_handler.py` | **2641** | test | 套 G5-09 pattern: 拆 sibling tests/h_state_query/{...}.py |

### 6.2 Approaching hard（1500-2000 警戒區）

| 檔 | LOC | 規範狀態 |
|---|---:|---|
| `rust/openclaw_engine/src/paper_state/tests.rs` | 1668 | test 拆 OK |
| `rust/openclaw_engine/src/scanner/scorer.rs` | 1613 | production 拆 |
| `rust/openclaw_engine/src/bin/replay_runner.rs` | 1599 | bin 拆 |
| `rust/openclaw_engine/src/intent_processor/tests.rs` | 1556 | test 拆 |
| `program_code/.../app/replay_full_chain_routes.py` | 1765 | route 拆 |
| `program_code/ml_training/mlde_demo_applier.py` | 1610 | pipeline 拆 |
| `program_code/.../replay/route_helpers.py` | 1589 | helper 拆 |
| `program_code/.../tests/test_strategist_agent.py` | 1519 | test 拆 |
| `program_code/.../app/governance_hub_live_candidate_review.py` | 1505 | route 拆 |

### 6.3 Warn line（800-1500）

- Rust 70 檔 / Python 72 檔；不一一列舉。
- 建議 PA 排 P2 wave，每 sprint 處理 5-8 檔。

### 6.4 Pre-existing baseline exception（CLAUDE.md §九）

- `runner.rs` 2467 — 屬 REF-20 Sprint A R3 / 2026-05-04 V1 Plan 直接生長；
- 但已超過 governance 2000 hard cap → 必須立即開新 P2 ticket
- Sprint C 之前已 1466 + R6 W1+W2 ~180 = 1646 → 跨 hard cap 線 → 屬 governance change 後新生 violation
- E5 標 **Critical 必拆**；非 pre-existing baseline 例外場景

---

## §7 可讀性 + 注釋規範違反

### 7.1 注釋 governance（2026-05-05 中文 only 默認）

| 統計 | 值 |
|---|---:|
| Rust 注釋行（粗估）| ~7638 |
| `runner.rs` comment ratio | 32.2% |
| 雙語對照舊 block | 大量（governance 不主動清，修改順手） |

### 7.2 結構問題

1. **main.py 729** — Python 主入口，相對合理；含 LOG warning + workers 4 的 leader election 注釋（OK）
2. **main.rs 1175** — Rust 主入口；近 hard cap 預估區，需 split startup_phases
3. **startup/mod.rs 1162** — startup logic 可拆 phases（auth/db/scanner/agents）
4. **governance_hub.py 1228** — 多 sub-class + sub-fn；可拆 governance_hub/{auth,lease,risk}.py
5. **guardian_agent.py 1458** — agent 主邏輯；可拆 guardian_agent/{decisions,risk_check,audit_emit}.py

### 7.3 命名 / cognitive load

- `_SHARED_IPC_SLOTS` / `_SHARED_SLOT_LOCK` 命名清晰
- `MARKET_SCANNER` / `AUTO_DEPLOYER` / `_SCOUT_WORKER` 命名清晰；strategy_wiring_scanner.py 拆出後維護性好
- 多數 singleton 都在 CLAUDE.md §九 表登記過 — governance 訓練有素
- 注：`H0_GATE` import in `paper_trading_routes.py:64` 無真實 method call → 命名誤導，疑似 wiring 死碼

### 7.4 重要 naming 修正建議

- `executor_agent.py:224` `lambda: True` — 改為 `_FAIL_CLOSE_SHADOW_PROVIDER = lambda: True`，明確命名揭示意圖
- `DEFAULT_SOCKET_DIR` const 加 env override `OPENCLAW_DEFAULT_SOCKET_DIR`

---

## §8 跨平台兼容性 + Apple Silicon 部署 readiness

### 8.1 路徑硬編碼 audit

- Rust 端 `/home/ncyu` / `/Users/ncyu` 在 production code: **0 違反**
- Rust 端 `/tmp/openclaw` 13 處 — 全為 `unwrap_or_else(env::var, default)` fallback **合規**
- 唯一例外：`ml/registry.rs:367` 注釋例字串硬寫 `/tmp/openclaw/models/edge_predictor_demo_ma_crossover_q50_v1_2026-04-23.onnx` — 是測試 fixture 路徑（OK）
- Python 端命中均為測試規約檢查（test 反向驗證 production 不命中）— **合規**

### 8.2 Apple Silicon CI tuple 缺失

- `.github/workflows/` 無 yml；無自動 cross-compile 驗證
- 違反 CLAUDE.md §七 ★★ "項目必須隨時可以部署在 macOS 上運行"
- M5 Ultra 預計 2026 H2 部署目標但 0 持續整合驗證
- **建議 H-9**：建 minimal CI workflow `cargo check --target aarch64-apple-darwin --release`

### 8.3 OS-specific code branch

- `cfg(target_os = "macos")` 真實使用：`replay/mac_policy_guard.rs` + 相關 test (replay_mac_policy_acceptance.rs)
- Rust 端 OS 分支 audit 只 6 處 production；可接受
- Python 端：`psutil` 等 Linux-only API 未發現顯式違反

### 8.4 LLM 抽象 readiness（CLAUDE.md §七）

- `ollama_client.py:419` time.sleep(0.5) retry 等待 — Ollama-specific 但邏輯通用，不洩漏 Ollama HTTP detail 出 client
- `LocalLLMClient` ABC 結構符合預期（本 audit 未深入 grep；歷史 audit 已驗）

### 8.5 服務遷移 path

- `helper_scripts/restart_all.sh` 跨平台 ready（CLAUDE.md §六 documented）
- launchd plist 樣板無檢索；建議下個 wave 搞
- systemd → launchd 轉換 SOP 缺；M5 部署前 1 sprint 必補

### 8.6 跨平台合規評分

| 軸 | 狀態 |
|---|---|
| 路徑無硬編碼 | ✅ 合規 |
| LLM 抽象 | ✅ 合規 |
| 服務可遷移 | 🟡 systemd→launchd plist 缺 |
| CI cross-compile | ❌ 0 自動驗證 |
| OS-specific 加守衛 | ✅ mac_policy_guard 完成 |
| 依賴清單 | ✅ requirements.txt 維護 |

**結論**：Apple Silicon readiness **80%**；缺 CI tuple + launchd plist。M5 部署前 1-2 sprint 補完可上。

---

## §9 Top 30 Optimization Opportunity（按 ROI 排序）

| # | 等級 | 標題 | ROI | 投資 | 收益 |
|---:|---|---|---|---|---|
| 1 | Critical | DROP `trading.*_damaged_20260414_130607` 4 表 | 高 | 1h | 909 MB 回收 |
| 2 | Critical | `runner.rs` 2467 拆 5 sibling | 高 | 4-6h | 解 hard violation + cargo incremental -2s |
| 3 | Critical | engine binary `strip = "symbols"` | 高 | 30min | 25→17 MB |
| 4 | High | DROP / 接線 25 表 0-row 死 schema | 高 | 4-8h | -5 MB schema overhead + cognitive load 大降 |
| 5 | High | `executor_agent.py:224` lambda:True 改 fail-loud | 高 | 1h | 解 18 blocker #8（前置 LG-5）|
| 6 | High | Python `copy.deepcopy` 10 處改 frozen dataclass | 高 | 4-6h | lease/auth read -30% latency |
| 7 | High | 啟用 pg_stat_statements + REFRESH COLLATION | 中 | 30min | 性能可觀察 + log noise 清 |
| 8 | High | 修 lg5 column does not exist schema drift | 高 | 2h | 解 healthcheck FAIL + log 大量噪音 |
| 9 | High | json.loads/dumps 全替換為 `orjson` | 中 | 2-3h | IPC 序列化 -30-50% latency |
| 10 | High | CI workflow 加 `aarch64-apple-darwin` check | 中 | 2h | apple silicon regression 自動偵測 |
| 11 | High | ai_budget tracker 16+ 鎖 → RwLock + per-strategy ArcSwap | 中 | 4-6h | tracker 路徑 -50% lock contention |
| 12 | High | `test_h_state_query_handler.py` 2641 拆 sibling | 中 | 2-3h | 解 Python hard violation |
| 13 | Medium | event_consumer/{loop_handlers,dispatch} 各 1144+ 再拆 | 中 | 4-6h | mod sibling 全 <800 |
| 14 | Medium | `intent_processor/mod.rs` 1215 + router.rs 1037 拆 | 中 | 4-6h | hot path 模組更小 |
| 15 | Medium | `tick_pipeline/commands.rs` 1339 + step_4_5_dispatch.rs 1326 拆 | 中 | 6-8h | tick path 模組更小 |
| 16 | Medium | `scanner/scorer.rs` 1613 拆 | 中 | 4h | scanner 路徑可讀 |
| 17 | Medium | `replay_full_chain_routes.py` 1765 拆 | 中 | 3h | route 模組可讀 |
| 18 | Medium | `mlde_demo_applier.py` 1610 拆 | 中 | 3-4h | ML pipeline 可讀 |
| 19 | Medium | `governance_hub.py` 1228 + `guardian_agent.py` 1458 拆 | 低中 | 4-6h | 主 agent 模組可讀 |
| 20 | Medium | `bybit_private_ws.rs` 1413 拆 | 低 | 3h | WS 路徑可讀 |
| 21 | Medium | `claude_teacher/applier.rs` 1072 拆 | 低 | 3h | teacher 路徑 |
| 22 | Medium | `database/trading_writer.rs` 1149 拆 | 低 | 3h | DB writer 路徑 |
| 23 | Medium | type:ignore + noqa 386 處批 mypy clean wave | 中 | 8-10h | mypy strict 通過率 ↑ |
| 24 | Low | DEFAULT_SOCKET_DIR 加 env override | 低 | 30min | 純衛生 |
| 25 | Low | daemon thread `time.sleep` 5 處改 Event.wait pattern | 低 | 2-3h | shutdown signal responsive |
| 26 | Low | 移除 `rust/target/debug/deps/openclaw_pyo3` 殘留 | 低 | 5min | -50 MB target/ 空間 |
| 27 | Low | 雙語注釋舊 block 漸進清（refactor 順手） | 低 | 持續 | -2-5% LOC overhead |
| 28 | Low | strip 後加 `[profile.release-debug]` 保留 symbol binary | 低 | 30min | core dump 可用 |
| 29 | Low | systemd → launchd plist 樣板 | 低中 | 4h | M5 部署前置 |
| 30 | Low | edge_predictor `Arc<ArcSwap<Option<Arc<dyn>>>>` 三層改 thread-local Cache | 低 | 3h | edge predictor read -10% latency |

---

## §10 E5 Verdict + PA Fix Plan 建議拆 work group

### 10.1 整體判定

**PASS**（with 4 Critical actionable）。

玄衡全程序鏈在過去 6 週相對 2026-04-24 baseline **顯著進步**：
- 8 Rust hard violation（含 event_consumer 1695 巨型 fn）→ **1**（runner.rs 2467 是新生 violation）
- main_legacy.py 5113 → 471（DEDUP Tier B 閉環確認）
- f-string logger 182 → 0（生產碼清零）
- clone count 在 hot 4 檔 115 → 73（**-37%**）
- ArcSwap + Atomic 健康使用（226 atomic + edge_predictor F9 guard pattern + live_auth_watcher 5ns 重讀）

**但 4 Critical 必須馬上派**：
1. `runner.rs` hard violation 已壘 30 LOC over cap，governance 線即時生效
2. 909 MB 死數據 24+ 天 — DB 占 2.8% 純浪費
3. binary 25 MB 未 strip — M5 部署前必補
4. `learning.governance_audit_log` 0 row 揭發 LG-5 reviewer 死於 wiring（pa panorama "[42]/[42b]" 已記錄但 sibling CC `463890d` 未 deploy）

### 10.2 PA 建議拆 work group

| Work Group | Sprint | 主任務 | Owner |
|---|---|---|---|
| **WG-CRIT** | 立即（W0）| 4 Critical | E1（runner.rs split + binary strip）+ PA/E1 派 ops（DROP damaged）+ 跟 sibling CC 推 LG5 deploy |
| **WG-HIGH-A** | W1-W2 | H-1 dead schema audit / H-2 lambda:True / H-5 deepcopy / H-9 CI tuple | E1 + MIT（schema audit）|
| **WG-HIGH-B** | W2-W3 | H-7 orjson / H-6 ai_budget lock / H-8 lg5 schema drift | E1 + E5 提建議 |
| **WG-MED-A** | W3-W5 | M-1/M-2/M-3/M-4 Rust 高 LOC sibling 拆 | E1（並行 4-5 ticket）|
| **WG-MED-B** | W4-W6 | M-5 Python 高 LOC 拆 + type:ignore 清 | E1 + E2 |
| **WG-LOW** | 持續 | L-1~L-6 雜項 + governance refactor 順手 | E1 順手 |

### 10.3 風險警告

1. **WG-CRIT runner.rs 拆 4-6h** — 涉 REF-20 replay 路徑核心，需 E2 雙審 + E4 全測試回歸
2. **WG-HIGH-A schema audit** — 30 表 0-row 中部分屬 wiring placeholder 不可亂 DROP；E5 建議 PA + MIT 必並行
3. **H-7 orjson 升級** — drop-in 替代但需 fp 處理檢驗（orjson decimal 處理 vs stdlib json）
4. **H-9 CI workflow 加 macOS** — 可能觸發 macOS-only build error（過去 0 自動驗證）；首次 setup 可能堵 1-2 day fix

### 10.4 不在 E5 範圍

- 業務語意改動（如 lambda:True 是否真改成 fail-loud / 還是切到 true env override）由 PA 決定
- 死 schema DROP 由 PA + MIT 拍板
- CI workflow 設計由 ops + PA
- LG-2 / LG-3 / LG-4 IMPL（屬 18 blocker P0；E5 不在範圍）

---

**E5 簽結**：本報告基於 2026-05-08 HEAD `4e2d2883` Linux trade-core 實證採樣 + Mac repo grep 雙端對齊；無 attach production engine PID（CLAUDE.md skill 紅旗：避免影響 live demo 流量）。所有採樣命令 + 回應在本 audit session 之 Bash log 可追溯。

# E5 對抗性核實報告 — 2026-05-08 audit 30 finding（24h 修復驗證）

**HEAD baseline**：`72f05aa0` (2026-05-08 audit basis 4e2d2883 後)
**HEAD current**：`7fccad06` (2026-05-09 02:13Z)
**核實時間**：2026-05-09
**核實方法**：Mac local grep + LOC count + ssh trade-core PG 直查 + Linux engine binary file 命令
**Engine runtime**：Linux trade-core PID 4092934（已 restart 2026-05-09 03:37，跑新 strip binary）
**核實口徑**：對抗性 — commit message 不算數，必驗 LOC + binary size + DB rows + 真實 caller

> ⚠️ **冷靜評估**：28 commit 看似覆蓋 30 finding，**實際只完成約 14 / 30（47%）**。多數 commit 走「表面解 + 留 follow-up」路徑，3 個 Critical 中 2 個未真正解（runner.rs 未拆 / 死 schema 改成 reclassify-only 而非 DROP）。

---

## §1 Executive Summary

### 1.1 LOC 表 before / after

| 項目 | before (2026-05-08) | after (2026-05-09) | delta | 狀態 |
|---|---:|---:|---:|---|
| **runner.rs (production)** | 2467 | **2467** | **0** | ❌ **未拆** |
| `bin/replay_runner.rs` (CLI binary) | 1599 | 626 + 4 sibling (54+51+401+457) | -973 (主檔) | ✅ 拆完 |
| `test_h_state_query_handler.py` | 2641 | 9 (shim) + 4 sibling (387+1223+436+559) | -2632 (主檔) | ✅ 拆完 |
| `event_consumer/loop_handlers.rs` | 1195 | 716 | -479 | ✅ <800 |
| `event_consumer/dispatch.rs` | 1144 | 683 | -461 | ✅ <800 |
| `event_consumer/loop_exchange.rs` (新) | — | 488 | +488 | ✅ <800 |
| `event_consumer/dispatch_tests.rs` (新) | — | 463 | +463 | ✅ <800 |
| `event_consumer/bootstrap.rs` | (existed) | 920 | +0 | ⚠️ >800 warn 仍在 |
| **Rust 檔 >2000 (hard)** | 1 (runner.rs) | **1 (runner.rs)** | 0 | ❌ runner.rs 未動 |
| **Python 檔 >2000 (hard)** | 1 (h_state) | **0** | -1 | ✅ 解一 |
| **Rust 檔 >800 (warn)** | 70 | 25 (我新採 ≥800 list 唯一變化是 runner.rs、event_consumer 縮入 / bootstrap.rs 920 為新 warn 但已存在) | 微減 | 🟡 |

### 1.2 Binary size

| 項 | before | after | delta |
|---|---:|---:|---|
| Linux release binary | 25 MB unstripped | **20.6 MB stripped** | **-4.4 MB (-17.6%)** |
| 預估值 | 25→17 MB | 25→20.6 MB | 實際 strip 收益少於預估（因為 LTO/codegen-units 未調，僅 strip="symbols"） |

### 1.3 SLA hit rate

| Gate | 狀態 |
|---|---|
| Linux engine PID 4092934 alive | ✅（snapshot age 0.3s，well under 45s threshold） |
| demo snapshot fresh | ✅（demo engine alive） |
| paper / live snapshots | 🟡 (paper age 483s = stale, live age 2063s = stale)；但這是 by design（spawn flag 關），非 strip 引起 |
| H0 production caller | ❌ 仍 0（block #9 未解，H-3 未動）|
| pg_stat_statements | ❌ 未啟用（H-7 未做） |
| Linux runtime engine.log latency 數字 | 🟡 grep 無結果（未噴 latency log） |

### 1.4 整體分數

| 等級 | finding 數 | ✅ Verified Fixed | ⚠️ Partial / Cosmetic | ❌ Not Fixed | 🆕 New issue |
|---|---:|---:|---:|---:|---:|
| Critical | 4 | 1 (C-3 strip) | 1 (C-4 reviewer 寫文件 only) | 2 (C-1 dump 未 DROP / C-2 runner 未拆) | 0 |
| High | 11 | 4 (H-9 CI / H-12 / H-6 部分 / H-5 部分) | 4 (H-1 reclassify-only / H-7 1% migration / H-8 未動 / H-10 未做) | 3 (H-2 / H-3 / H-4) | 0 |
| Medium | 9 | 1 (M-2 部分) | 4 (M-1/M-3/M-4/M-5 未拆) | 4 | 0 |
| Low | 6 | 0 | 0 | 6 | 0 |
| **總計** | **30** | **6** | **9** | **15** | **0** |

> 表中「9 partial」算 50% credit，正確閉合率 ≈ (6 + 9×0.5) / 30 = **35%**。
>
> 對抗性結論：**「修復 30 finding」表述過度樂觀**。實際是「動了 14 finding」、「新加 4 個 V### migration 改改 schema metadata 但沒真正 DROP」、「3 個高 ROI Critical / High 沒動（runner / dump / lambda）」。

---

## §2 Finding-by-finding 核實

### Critical

#### C-1 DROP `trading.*_damaged_20260414_130607` 4 表 909 MB
- **Audit 預期**：dump + DROP，回收 909 MB
- **核實結果**：
  ```
  fills_damaged_20260414_130607     | 4136 kB
  intents_damaged_20260414_130607   | 1296 kB
  orders_damaged_20260414_130607    |  624 kB
  risk_verdicts_damaged_20260414_130607 | 903 MB
  ```
- **狀態**：❌ **NOT FIXED** — 4 表仍存在，risk_verdicts 仍 903 MB
- **修了什麼**：commit `09afc92c audit: add fills engine mode archive check` 加 V077 migration 對 `trading.fills` engine_mode 做 archive check（順帶為「demo_archive_20260418」設計），但**沒有 DROP damaged 表**
- **對抗 push back**：commit chain 修了「未來會用到的 archive check」，沒做 audit 點出的「24 天前 dump 立即 DROP」。reclassification migration（V068/V070/V071）改成「metadata-only reclassification guard」而非真正 DROP — Audit 7 commit 中 5 個是 audit metadata 只改 SQL placeholder

#### C-2 runner.rs 2467 LOC 拆 5 sibling
- **Audit 預期**：拆 `runner/{config,scheduler,reporter,calibrator,metrics}.rs` 5 sibling，每 <800
- **核實結果**：
  - `rust/openclaw_engine/src/replay/runner.rs` LOC = **2467** 完全沒動
  - `rust/openclaw_engine/src/replay/runner/` 子目錄不存在
  - commit `3372eb18 refactor: split replay runner binary` 拆的是另一個檔：`rust/openclaw_engine/src/bin/replay_runner.rs` (1599 LOC CLI 入口) → 626 主檔 + 4 sibling (54/51/401/457)
- **狀態**：❌ **MISIDENTIFIED COMMIT** — commit message 「split replay runner」誤導，實際 split 的是 CLI binary entry，不是 production replay/runner.rs
- **對抗 push back**：**Critical 2 完全沒被修**。Mac/Linux 都看 git log 看到 commit 顯示「split replay runner binary」會誤以為 audit 點 closed。實際未動的 runner.rs 仍是唯一 Rust hard violation，governance §九 immediate fix 規則已被違反 1 天

#### C-3 Engine binary `strip = "symbols"`
- **Audit 預期**：25 → ~17 MB
- **核實結果**：
  - `rust/Cargo.toml` line 41 加了 `[profile.release]\nstrip = "symbols"` ✅
  - Linux runtime binary：**20.6 MB（20601264 bytes）**，`file` 報 `stripped` ✅
  - Engine PID 4092934 在 03:37 用新 stripped binary 啟動 ✅
- **狀態**：✅ **VERIFIED FIXED**
- **次要問題**：實際 -4.4 MB（17.6%）少於 audit 預估的 25→17MB（-32%）。原因：只加了 strip，未加 `codegen-units = 1` + `lto = "thin"`（audit 建議 §3.5）。可選優化還剩 ~3 MB

#### C-4 `learning.governance_audit_log` 0 row LG-5 reviewer 死於 wiring
- **Audit 預期**：deploy Lg5ReviewConsumer 後 24h re-check
- **核實結果**：`learning.governance_audit_log` 仍 0 row（在 0-row 列表內）
- **狀態**：⚠️ **PARTIAL** — sibling CC `463890d` 已落地，但**沒 deploy + restart engine 觸發 spawn**
- **對抗 push back**：本輪 W-AUDIT-5a/5b 都 explicit 寫 "no rebuild/restart/deploy" 在 commit body — 等於宣告「不會解這個 wiring blocker」。reviewer scheduler 仍未活，0 audit row 仍未生

### High

#### H-1 25 表 0-row dead schema audit + DROP
- **Audit 預期**：30 表 1-by-1 audit；E3+MIT 派；50% 可 DROP
- **核實結果**：
  - V068（learning_dead_schema_reclassification_guard）/ V069（drop_dead_observability_scorer_predictions）/ V070（replay_dead_schema_reclassification_guard）/ V071（learning_dormant_tables_reclassification_guard）4 個 migration 落地
  - 但是「**reclassify only**」（commit `754ecec7 reclassify dead schema guards`）— 改成 metadata reclassify 而非 DROP
  - V069 是唯一真 DROP（observability.scorer_predictions），V068/V070/V071 都是 placeholder
  - PG 端核實：30 表中 **29 表仍 0 row**
- **狀態**：⚠️ **PARTIAL** — 1/30 真 DROP，餘 reclassify metadata。collison 與 audit 預期顯著
- **對抗 push back**：commit body 自承「Replace the planned V068/V070/V071 destructive cleanup shape with metadata-only reclassification guards after source audit found active route, cron, Rust writer, AI budget, Claude Teacher, replay handoff, Wave9, and Agent Spine references」— 即 audit found references 後改保守路徑。**這是合理的工程決定**，但 audit 點仍未真閉合（DB cognitive load 沒實際減）

#### H-2 `executor_agent.py:224` lambda:True hardcoded
- **核實結果**：line 224 仍是 `shadow_mode_provider if shadow_mode_provider is not None else (lambda: True)`
- **狀態**：❌ **NOT FIXED**
- **對抗 push back**：18 blocker #8 仍開。commit chain 沒任何 commit 觸這個檔。E5 audit 標 "解 18 blocker #8" 高 ROI，但 1 hour fix 未做

#### H-3 `H0_GATE` 業務 caller 0 處
- **核實結果**：`grep -rn "H0_GATE\."` 仍 0 method call，僅 import + create + log status
- **狀態**：❌ **NOT FIXED** — 屬 LG-2 RFC IMPL 範圍，audit 已標 "等 LG-2"，本輪未進

#### H-4 `CostEdgeAdvisor` 業務 caller 0 處
- **核實結果**：仍只有 test 引用，0 production caller
- **狀態**：❌ **NOT FIXED** — 同上，超出本輪 scope

#### H-5 Python `copy.deepcopy` 10+ 處改 frozen dataclass
- **Audit 預期**：lease/auth state read 路徑 -30% latency
- **核實結果**：
  - **state machine 4 個檔（authorization / decision_lease / risk_governor / learning_tier）已替換為 `_clone_state_object()` / `_clone_jsonish()`** ✅（commit e00985da）
  - `decision_lease_state_machine.py:507/614/618` 全 0 處 deepcopy（已清）
  - `authorization_state_machine.py:512/614` 全 0 處 deepcopy（已清）
  - `risk_governor_state_machine.py:483` 0 處 deepcopy（已清）
  - **但全 codebase deepcopy 還剩 18 處**（audit 點 10 處低估）
    - 仍 deepcopy: `pnl_ops.py:144/263` / `state_compiler.py:627/630/635` / `runtime_bridge.py:84/86` / `learning_queries.py:49/73/74` / `state_store.py:401` / `replay_execution_calibration.py:538` / `control_ops.py:130/644/645/646` / `main.py:48/84`
- **狀態**：⚠️ **PARTIAL** — state machine 熱路徑解（高 ROI 點命中），但仍 18 處未動。實際性能收益取決於 state-machine vs 其他 path 的調用頻率（state machine 才是熱讀，其他多是冷路徑 OK）

#### H-6 ai_budget tracker `_lock` 16+ 處
- **Audit 預期**：`Mutex<Tracker>` 改 `RwLock<Inner>` + per-strategy ArcSwap counter
- **核實結果**：
  - `tracker.rs` 仍 6 處 RwLock/ArcSwap 提及，但結構改了：
    - `config_cache: Arc<ArcSwap<BudgetConfig>>` ✅（commit 8d6646c2）
    - `usage_cache: Arc<RwLock<UsageCache>>`（仍 RwLock，但 audit accept 因為 usage 是 mutate-on-record，需 mutex）
  - 注釋明確說「Config reads use ArcSwap because [config 讀多寫少] / Usage remains under an async RwLock because recording usage mutates per-scope」
  - 從 audit 16+ 個 lock 點 → 約縮減到 6 個 lock 點，per-strategy ArcSwap 是 partial（config 是 strategy-aware，usage 還是 monolith）
- **狀態**：✅ **VERIFIED FIXED (Partial)** — config 路徑確實改 ArcSwap，read-heavy 提升；但 audit 預期「per-strategy ArcSwap counter」未做（usage 仍 monolithic RwLock）
- **對抗 push back**：commit body 明確說「config 是 cache mechanics 改動，不是 per-strategy budget authority change」— 即 PA 確實有讀 audit 但選擇了更保守的 partial 路徑

#### H-7 json.loads/dumps 501 處改 orjson
- **Audit 預期**：IPC 序列化 -30-50% latency
- **核實結果**：
  - 新增 `json_fast.py`（118 LOC）helper，with orjson fast-path + stdlib fallback ✅
  - **使用 callsite：5 個 prod 檔 + 1 test**（ipc_client / ipc_client_sync / ai_service_listener / ollama_client / local_llm_factory）
  - 全 codebase json.loads = 250 / json.dumps = 407 → **657 處仍走 stdlib**
  - 遷移率：**5/657 = 0.8%**
- **狀態**：⚠️ **FOUNDATION ONLY** — helper 立完，但實際遷移 < 1%。預期 -30-50% IPC latency 收益**未到位**，因為 IPC 主路徑 ipc_dispatch.py / ipc_client.py（asyncio path 改了，但同步 path 沒改）
- **對抗 push back**：commit body 自承「Leave signature and hash canonical JSON paths untouched pending byte-contract tests」— 即知道大部分還沒遷。**這是 foundation work 不是 ROI realization**

#### H-8 lg5 column does not exist (slippage_bps / net_bps_after_fee)
- **核實結果**：grep `slippage_bps` / `net_bps_after_fee` 仍見 dream_engine.py / mlde_shadow_advisor.py / linucb_trainer.py — 無 schema migration 修
- **狀態**：❌ **NOT FIXED** — healthcheck 仍會 FAIL，cron 仍會噴錯
- **對抗 push back**：audit 標 "2h 修 schema or column rename"，本輪 0 動

#### H-9 CI workflow 加 aarch64-apple-darwin
- **Audit 預期**：建 `.github/workflows/ci.yml`，matrix 含 darwin
- **核實結果**：
  - `.github/workflows/ci.yml` 已建（716 bytes）
  - matrix 含 `aarch64-apple-darwin` (macos-latest) + `x86_64-unknown-linux-gnu` (ubuntu-latest) ✅
  - 跑 `cargo check --target ... --release -p openclaw_engine --bin openclaw-engine`
  - timeout 20 min
- **狀態**：✅ **VERIFIED FIXED**
- **對抗 push back**：CI workflow 存在，但 PR check 是否在 GitHub side 真實 enabled / passing 我沒法從 Mac local 驗（需要看 GitHub Actions tab）。**結構合規**，但**實際 CI run 狀態未驗**

#### H-10 collation refresh
- **核實結果**：`SELECT datcollate, datcollversion FROM pg_database` 仍報 WARNING `database "trading_ai" has no actual collation version`
- **狀態**：❌ **NOT FIXED** — 1 行 SQL 10s 執行，本輪沒做

#### H-11 V059 edge_estimate_snapshots 標 dead 不準確 (panorama 修正)
- **核實結果**：本輪沒看到 panorama 修正 commit
- **狀態**：❌ **NOT FIXED** — 但這是 PA 文檔級修，影響 cognitive 不影響 runtime

#### H-12 test_h_state_query_handler.py 2641 拆
- **核實結果**：✅ **VERIFIED FIXED**
  - 主檔 → 9 行 shim，重定向到 sibling
  - 4 sibling: common.py 387 / test_agent_states.py 1223 / test_core.py 436 / test_h_buckets.py 559
  - 但 test_agent_states.py 1223 LOC 仍 >800 warn line — **未到 audit 預期 max <800**
- **對抗 push back**：拆是真拆，但 sibling 1223 行仍 warn。次要 issue

### Medium

#### M-1 runner.rs 32% comment ratio (cleanup with split)
- **狀態**：❌ N/A — runner.rs 完全沒動

#### M-2 event_consumer/{loop_handlers,dispatch} 拆
- **核實結果**：✅ **VERIFIED FIXED**
  - loop_handlers.rs 1195 → 716（-479）
  - dispatch.rs 1144 → 683（-461）
  - 新 loop_exchange.rs 488（市場事件路徑抽出）
  - 新 dispatch_tests.rs 463（測試抽出）
  - 但 bootstrap.rs 920 LOC 仍 >800 warn（pre-existing 未動）

#### M-3 Rust 高 LOC sibling 拆 (paper_state/tests / scanner/scorer / replay_runner / intent_processor/tests)
- **核實結果**：bin/replay_runner.rs 1599 → 626 拆完 ✅；其他 4 個未動 (paper_state/tests.rs 1668 / scanner/scorer.rs 1613 / intent_processor/tests.rs 1556 / intent_processor/tests_predictor_router.rs 1363) — 不在本輪 scope

#### M-4 Python replay_full_chain_routes.py 1765 拆
- **狀態**：❌ NOT FIXED — 1765 仍 1765

#### M-5 mlde_demo_applier.py 1610 拆
- **狀態**：❌ NOT FIXED

#### M-6 to M-9
- **狀態**：❌ NOT FIXED — type-ignore / global keyword / Pydantic model 都未動

### Low

L-1 to L-6 全部 **NOT FIXED** — 本輪沒處理 Low；governance refactor 順手做，本輪未碰

---

## §3 NEW-ISSUE（核實過程新發現）

### NEW-1 commit `3372eb18` message 誤導
- commit message：「split replay runner binary」
- 實際 split：`rust/openclaw_engine/src/bin/replay_runner.rs` (CLI binary entry)
- audit 點：`rust/openclaw_engine/src/replay/runner.rs` (production replay 邏輯)
- **影響**：oversight 風險高 — Mac/Linux 雙端都看 commit message 會誤判 Critical-2 已修。應 commit message 加 (CLI binary, not production replay/runner.rs)

### NEW-2 Cargo.toml strip 配置最小化（沒上 LTO + codegen-units）
- 預估值 25→17 MB (-32%)
- 實際值 25→20.6 MB (-17.6%)
- 差距來自只加 `strip = "symbols"`，未加 `codegen-units = 1` + `lto = "thin"`（audit §3.5 推薦）
- **建議**：補加 LTO + codegen-units 預估再回收 ~3 MB binary（編譯時間 +30s 接受）

### NEW-3 deepcopy 計數低估
- audit 標「10 處」實際全 codebase **18 處**
- audit 沒掃到 `state_compiler.py` (3 處) / `runtime_bridge.py` (2 處) / `learning_queries.py` (3 處) / `control_ops.py` (4 處) / `state_store.py` (1 處) / `replay_execution_calibration.py` (1 處)
- 影響：H-5 修 4 處 state machine 熱路徑（高 ROI），剩 14 處冷路徑未動。**audit 數字 10 不準，但補丁優先順序合理**

### NEW-4 ai_budget 修法與 audit 點偏離（partial）
- audit 預期「per-strategy ArcSwap counter」
- 實裝「config-only ArcSwap，usage 仍 RwLock」
- 註釋明確 trade-off：「usage 是 mutate-on-record 不適合 ArcSwap」
- **PA 選擇是合理的工程妥協**，但 audit 預期「16+ 鎖點 → -50% lock contention」沒到位

### NEW-5 dead schema 「reclassify-only」非真 DROP
- V068/V070/V071 三個 migration 是 metadata-only reclassification guard
- 真 DROP 只有 V069（observability.scorer_predictions）
- commit body 自承「source audit found active route, cron, Rust writer, ... references」後改保守路徑
- **DB 909 MB 死數據完全沒回收**

### NEW-6 H-12 sibling test_agent_states.py 1223 LOC 仍 >800 warn
- 主檔拆完但 sibling 進入 warn 區
- audit 預期「套 G5-09 pattern: max <800」未達標

---

## §4 對抗性 push back

### Push back #1：「修 30 finding」表述過度樂觀

實際數字：
- ✅ Verified Fixed = **6 / 30 (20%)**
- ⚠️ Partial / Cosmetic = **9 / 30 (30%)**
- ❌ Not Fixed = **15 / 30 (50%)**

這 28 commit chain 看起來覆蓋度高，但很多是「source-only 改動」配「accept follow-up」trade-off。**正確說法**應該是「30 finding 中 6 真 fix，9 部分動，15 未動」。

### Push back #2：Critical-2 (runner.rs) 完全 misidentify

`runner.rs` 2467 LOC 是 audit 唯一 Rust hard violation，governance §九 immediate fix（生效 2026-05-08）。本輪 commit chain 看起來修了，**實際完全沒動**。commit `3372eb18 split replay runner binary` 修的是另一個檔（CLI binary entry）。

**這是治理盲點**：commit message 沒區分 `bin/replay_runner.rs` vs `replay/runner.rs`。E1 / PA / E2 都應該識別這個誤導，但 chain 全程沒人指出。

如果今天 audit-chain 走 PM Sign-off 必檢，這個應該被 push back 到 E1 重做：
- (a) 真拆 `replay/runner.rs` 5 sibling
- (b) 至少在 commit message 把 `bin/replay_runner.rs` 寫清楚不是 `replay/runner.rs`，並開 NEW P0 ticket 點明真檔還沒拆

### Push back #3：Critical-1 (909 MB damaged dump) 完全沒動

24 天前 dump，`risk_verdicts_damaged_20260414_130607` 仍 903 MB。

W-AUDIT-5a 的 V068/V070/V071 用「reclassify guard」替代 DROP — 這是合理的「先 audit 後 DROP」工程姿態，但**直接命中的 909 MB 死數據完全沒處理**。

audit ROI 排第 1，1 hour fix（dump to NAS + DROP），本輪 0 動。

### Push back #4：「foundation only」≠「optimization realized」

H-7 (orjson) 走 foundation 路徑：
- ✅ json_fast.py helper 建好
- ✅ orjson 加 dependency
- ✅ 5 callsite 切換
- ❌ 657 個其他 callsite 沒動

audit 預期收益「IPC 序列化 -30-50% latency」。實際遷移 < 1%。**性能收益沒到**。

E5 應該明確區分：
- `perf: add foundation` → infrastructure ready
- `perf: realize ROI` → 實際性能驗證

commit chain 寫「perf: add fast json ipc foundation」+「perf: expand fast json runtime hot paths」— 第二 commit 標題有 "expand"，但實際只擴到 5 callsite。

### Push back #5：H-2 / H-3 / H-4 (lambda:True / H0_GATE / CostEdgeAdvisor) 都是 audit 標高 ROI 但 0 動

- H-2 lambda:True 1 hour fix → 0 動
- H-3 H0_GATE 0 caller → 0 動 (audit accept "等 LG-2")
- H-4 CostEdgeAdvisor 0 caller → 0 動

H-2 是真實 1-hour 工，但 18 blocker #8 仍開。E5 audit 點 ROI 高，PA 排序到 W-AUDIT-5b 但 W-AUDIT-5b 沒擴到這幾個。**dispatch gap**。

### Push back #6：H-8 (lg5 schema drift) 高頻噪音 0 動

API log 每 hour 噴 `column "slippage_bps" / "net_bps_after_fee" does not exist`。audit 標「2h fix，解 healthcheck 永久 FAIL」。

本輪 0 commit 觸這個 schema drift。**healthcheck 仍會 FAIL，log noise 仍在**。

### Push back #7：H-10 collation 1 行 SQL 0 動

`ALTER DATABASE trading_ai REFRESH COLLATION VERSION;` 一行 10 秒。本輪 0 動。每次 psql 連線仍噴 WARNING。

### Push back #8：H-11 panorama 修正 0 動

PA panorama 仍標 V059 edge_estimate_snapshots 為 dead，實際 457 row + active reader。**cognitive load 仍誤導下一輪 audit**。

---

## §5 推薦下一步

### 立即（W0 — 仍是 Critical 線上）

| Ticket | 動作 | 投資 |
|---|---|---|
| **C-2 retry** | 真拆 `replay/runner.rs` 2467 → 5 sibling | 4-6h |
| **C-1 retry** | 909 MB damaged dump 到 NAS + DROP 4 表 | 1h |
| **H-2 retry** | lambda:True 改 fail-loud raise / env override | 1h |
| **H-8 retry** | lg5 schema drift 修 column rename / migration | 2h |
| **H-10 retry** | `ALTER DATABASE REFRESH COLLATION VERSION` | 10s |

### W1（性能 ROI realization）

| Ticket | 動作 | 投資 |
|---|---|---|
| H-7 expand | json_fast 遷移到 ipc_dispatch.py 主路徑 + ml_routes.py / paper_trading_routes.py 等 hot path | 4-8h |
| C-3 enhance | `codegen-units = 1` + `lto = "thin"` 補上，再 -3 MB binary | 30min + cargo time | 
| H-5 expand | deepcopy 14 處冷路徑審查（哪些其實也熱） | 2-3h |

### W2 (governance / cognitive)

| Ticket | 動作 | 投資 |
|---|---|---|
| H-11 | PA panorama 修正 V059 not-dead | 30min |
| C-4 retry | deploy Lg5ReviewConsumer + restart engine 觸發 spawn | 1h + 24h verify |

---

## §6 結論

**整體判定**：⚠️ **PARTIAL CLOSURE**（35% true closure rate）

過去 24h 28 commit chain 看似覆蓋 audit 30 finding，**實際**：
- 真 fix 6 項（20%）
- 部分動 9 項（30%）
- 完全沒動 15 項（50%）

最痛的是 **3 個 Critical 中 2 個沒解**：
1. C-1 909 MB 死數據完全沒 DROP
2. C-2 runner.rs 完全沒拆（commit message 誤導，實際 split 的是 CLI binary）

成功的部分：
1. C-3 binary strip 真做（25 → 20.6 MB）
2. H-9 CI workflow with darwin matrix 真建
3. H-12 test_h_state_query_handler.py 真拆
4. H-5 state machine 4 檔 deepcopy 真換 _clone()
5. H-6 ai_budget config_cache 真 ArcSwap (partial scope)
6. M-2 event_consumer 真進一步拆

**對抗性 push back 結論**：
- audit chain 必須區分 「source-only foundation」 vs 「optimization ROI realized」
- commit message 必須具體到檔案路徑（`bin/replay_runner.rs` ≠ `replay/runner.rs`）
- 「reclassify-only」≠「DROP」 — 不能算 DB cleanup 閉合
- `< 1%` 遷移率 ≠ 「expand fast json runtime hot paths」
- 30 finding 對抗性 sign-off 必須走 LOC + binary size + DB rows + caller count 四維獨立驗

E5 簽結：本核實基於 Mac local + ssh trade-core 實證採樣 + Linux engine PID 4092934 在跑 strip binary 的事實對齊；**未對任何 30 finding 做修復改動**（E5 角色限定）。

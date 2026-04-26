# E2 Tier 4 Batch Review — 6 commits (eb65e1e..4689fc8) · 2026-04-26

**Audit 範圍**：6 commits + 1 MIT audit（PM 代落檔）+ 1 PM merge
**Audit Methodology**：8-axis（A-H）per CLAUDE.md §八 強制工作鏈 + §九 既有 checklist + OpenClaw §3 9 條
**E2 立場**：對抗審核 — 不寫業務代碼，只 typo/lint 範圍直修
**Pre-conditions**：Mac repo HEAD 4689fc8，Linux runtime 同步

---

## Executive Summary

| 項 | 狀態 |
|---|---|
| 6 commits 結構性結論 | 5 PASS / 1 PASS (merge commit `4689fc8` accept union strategy) |
| MIT EXIT-FEATURES-WRITER-BUG-1 audit | ACCEPT |
| PM merge intervention | ACCEPT |
| Findings | 1 LOW (ai_service_dispatch.py 868 進警告區) + 1 LOW (BRIDGE_RC overshadow OBSERVER_RC at exit) + 1 LOW (RCA-A H1 reject 證據鏈未 in-report) |
| Critical findings | 0 |
| 退回 E1 項 | 0 |
| 結論 | **PASS to QA** |

---

## §1 commit-by-commit 結論

### 1.1 commit `eb65e1e` — G9-02-FUP-WS-CLIENT-SPLIT (1227 → 6 sibling, max 355) 【PASS】

**Owner**: E5 · **Diff**: 7 files / +1335 / −1227

| 檢查項 | 結論 |
|---|---|
| Sibling layout | mod 142 / connection 52 / parsers 355 / dispatch 161 / run_loop 271 / tests 354 — **6/6 < 800 警告線** |
| 5 hot-path byte-identical | (1) WS-TIMEOUT 15s connect ✅ run_loop.rs:66-70 / (2) subscribe HashSet O(1) dedup + 10-batch + 500ms gap ✅ run_loop.rs:97-103,156-169 / (3) process_message + ShouldReconnect::No,Yes ✅ dispatch.rs:135-147 / (4) BackoffConfig 3-60s 雙路徑 FA-1 risk #2 順序 ✅ run_loop.rs:78-86 (after-incr) + L247-251 (before-incr) / (5) ProcessOutcome::ForceReconnect close-frame + break + outer reconnect ✅ run_loop.rs:200 |
| 外部 caller 路徑 | `openclaw_engine::ws_client::{WsClient, WsTopicChange}` 不變 — main_ws.rs:21 + scanner/runner.rs:30 ✅ |
| Cross-module visibility | `pub(super)` 對 sibling 內互通 / `pub use connection::WsState` 維持外部 surface |
| 雙語 MODULE_NOTE | 6 sibling 全部中英對照齊全 |
| Auth phase 不啟 force reconnect | dispatch.rs:128-149 force reconnect logic 在 `else` branch（topic 不匹配 prefix），auth handshake 不觸發 ✅ |
| Test coverage | `tests.rs` 354 行 unit tests（parsers + backoff + state display），`cargo test --release -p openclaw_engine --lib` 2198/0 fail 對齊 commit message claim 2176 baseline + 22 h_state |
| §九 1200 cap | 6/6 sibling 全部 < 800 ✅ |

**結論**：PASS to E4. 0 production semantic delta 屬實 — 5 hot-path byte-identical 經 grep 對照 + 雙路徑 FA-1 ordering 保留。

### 1.2 commit `1c7b20e` — G3-08 Phase 1 Sub-task B Python 【PASS】

**Owner**: E1 · **Diff**: 6 files / +1222 / −0

| 檢查項 | 結論 |
|---|---|
| 新檔位置 | h_state_invalidator.py 385 / h_state_query_handler.py 180 / 2 unit tests 啟動於 `program_code/exchange_connectors/bybit_connector/control_api_v1/{app,tests}/` |
| 雙語 MODULE_NOTE | 兩 production module 中英對照齊全（invalidator: top-level docstring + MODULE_NOTE EN/中；query_handler: 同 + Schema 表格 + 設計意圖中文） |
| DEFAULT-OFF 嚴格 "1" | `is_gateway_enabled()` 對齊 Rust `std::env::var(...).as_deref() == Ok("1")` byte-identical strict comparison |
| threading.Thread daemon=True | invalidator.py:180-184 ✅ |
| asyncio.new_event_loop fire-and-forget | invalidator.py:197 ✅（daemon thread 內無 loop → 可安全 new_event_loop + run_until_complete） |
| 三層 try/except 吞 IPC error | outer guard:351 / inner thread:201 / IPC close:215+239 — fail-closed per CLAUDE.md §二 #6 ✅ |
| query_h_state_full IPC route 註冊 | ai_service_dispatch.py:120 (`_register_handlers()`) — 永遠註冊（per PA §10.1）env=0 也回 empty shell ✅ |
| HANDLER_TTLS=2.0s | ai_service.py:92 — 5ms reverse-pull SLA target，2s = poll-loop deadlock guard（per PA §G2 註解）✅ |
| Lazy import h_state_query_handler | ai_service_dispatch.py:832 + `# noqa: PLC0415` 防 bootstrap cycle ✅ |
| 範圍嚴守（avoid Sub-task C scope） | strategy_wiring.py / CLAUDE.md / passive_wait_healthcheck/* 0 modify ✅ |
| Test coverage | 35 pytest passed (Mac + Linux) — 13 invalidator + 22 query_handler ✅ |
| §九 8 條 checklist | 0 except:pass / 0 detail=str(e) / threading.Lock 在 sync API（非 asyncio route）/ HTTPException 順序 N/A（無 raise）✅ |

**結論**：PASS to E4. Sub-task B 完整 fire-and-forget pattern + 嚴格 env-gate + 永遠 callable route 設計與 PA §4/§5/§7/§10.1 100% 對齊。

### 1.3 commit `deac4bc` — G3-08 Phase 1 Sub-task B docs 【PASS】

**Owner**: E1 · **Diff**: 2 files / +159 / −0

純 doc commit（E1 memory.md + workspace report）。對應 Sub-task B commit `1c7b20e`。

| 檢查項 | 結論 |
|---|---|
| 跨平台 grep | 0 hit |
| Memory drift | report-index row 對齊 / 6 條教訓內容 contextual + actionable |
| 範圍 | 0 production code 改動 ✅ |

**結論**：PASS（accompanying docs commit）.

### 1.4 commit `c53c3f9` — OBSERVER-PIPELINE-POST-F42FACE-CLEANUP 【PASS-with-LOW】

**Owner**: E1 · **Diff**: 9 files / +679 / −272 / -228 net Python deletes

| 檢查項 | 結論 |
|---|---|
| cron wrapper noise pattern 完全移除 | `if ... ; then ... else echo "non-fatal" ; fi` 已替換為顯式 `OBSERVER_RC=$?` + `BRIDGE_RC=$?` 捕捉 + 任一非零 wrapper exit 1 ✅ cron_observer_cycle.sh:48-79 |
| cron-time env var 陷阱修復 | `export OPENCLAW_SRV_ROOT="$REPO"` line 37 — fixes cron cwd $HOME 導致 fallback `.` 把 cycle JSON 寫到 $HOME/docker_projects/ 陷阱 ✅ |
| cycle JSON 路徑優先級 | `OPENCLAW_SRV_ROOT > OPENCLAW_BASE_DIR > Path.home()/BybitOpenClaw/srv` checks_derived.py:493-499 ✅ |
| [19] healthcheck 雙軸三態 | age (≤1h PASS / 1-24h WARN / >24h FAIL) × ok ratio (≥75% PASS / 50-75% WARN / <50% FAIL) + JSON parse error → FAIL + schema drift → WARN ✅ checks_derived.py:580-594 |
| OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1 opt-out | 雙語 docstring + Mac dev / fresh node 可 PASS-skip ✅ |
| `set -uo pipefail` 移除 `set -e` | 故意設計（observer fail 不應阻塞 bridge），但 RC 仍 propagate ✅ |
| v2 + dead caller 刪除合理性 | grep 確認 `bybit_private_ws_smoke_test_v2` + `bybit_ws_smoke_to_postgres` 0 真實 caller（除自我引用）✅ |
| run_bybit_observer_cycle.py 留尾合理 | 同目錄 wrapper 0 上游 caller，孤立 entrypoint，按最小影響原則 defer to BB-M-3 ✅ |
| Linux verify 19 → 20 check | runner.py [19] invocation post-cursor-close（純 filesystem，不需 cursor）+ docstring/description 從 19 → 20 + cron pipeline 跑出 20 行 ✅ |
| §九 800/1200 | 244 / 594 / 60 / 868 — checks_derived 594 < 800 ✅；ai_service_dispatch.py 868 預先存在但未在本 commit 動 |

**LOW finding L-1**：cron_observer_cycle.sh 行 76-79 的 exit-code aggregation 邏輯是「OBSERVER_RC ≠ 0 → exit OBSERVER_RC（忽略 BRIDGE_RC）」+「OBSERVER_RC = 0 → exit BRIDGE_RC」。當 OBSERVER 與 BRIDGE 都失敗時 BRIDGE_RC 在 cron daemon `/var/log/cron` 中只有 log 行不會反映在 wrapper exit code（雖然 log 行有資訊）。**P3 cosmetic** — cron 看到 wrapper non-zero 已足，BRIDGE 細節可從 log 找。建議未來改 `exit $((OBSERVER_RC + BRIDGE_RC))` 或 `[ $OBSERVER_RC -ne 0 -o $BRIDGE_RC -ne 0 ] && exit 1`，**不退回 E1**。

**結論**：PASS to E4. 結構性閉環 silent-fail 漏洞 + healthcheck 加固。1 LOW 屬 cosmetic future polish。

### 1.5 commit `aa287c4` — G3-08 Phase 1 Sub-task A Rust h_state_cache 【PASS】

**Owner**: E1 (worktree-agent-a2e662b283f719faf, isolation per PA §13.1) · **Diff**: 22 files / +1791 / −13

| 檢查項 | 結論 |
|---|---|
| 新檔位置 | h_state_cache/{mod,types,poller,tests}.rs 4 sibling 在 `rust/openclaw_engine/src/`；ipc_server/handlers/h_state.rs 加新 handler 模組 |
| 雙語 MODULE_NOTE | 5 new file 全部中英對照（mod.rs MODULE_NOTE EN+中 / types.rs IMPORTANT 不影響交易聲明 / poller.rs Phase 1 boundary 細描述 / tests.rs 三檔測試覆蓋說明 / handlers/h_state.rs gateway_disabled 設計細節） |
| DEFAULT-OFF 嚴格 "1" | `pub fn is_gateway_enabled() -> bool { std::env::var(ENV_GATEWAY_FLAG).as_deref() == Ok("1") }` ✅ mod.rs:253-255 |
| StubHStateFetcher Phase 1 stub | poller.rs:LCKW `RealHStateFetcher` 暫存於此 — `Ok(default snapshot)` until Sub-task B+C 接通 Python reverse-IPC client；env=1 端對端可觀測（cargo test 綠 / IPC handler live）但讀回空 dict — 即 Phase 1 acceptance ✅ |
| 10s poll daemon | `DEFAULT_POLL_INTERVAL = 10s`（poller.rs:60）+ `tokio::time::interval` + `MissedTickBehavior::Delay`（避免追補積壓 tick）✅ |
| tokio::sync::watch dedup | `make_invalidation_channel()` 用 `watch::channel(0u64)` + `send_modify(\|v\| v.wrapping_add(1))` push + `mark_unchanged()` consume — N back-to-back push 自然合併為單次 `.changed()` event ✅ poller.rs:92-140 |
| Race 風險 (PA §14.1 Top 3) | `tokio::select!` `biased` 順序 cancel→ticker→invalidation；select 是單 task 同時 select 一個 branch，不可能 reentrant `run_one_poll` → race=0 ✅ |
| Cancel token cleanup | `cancel.cancelled() => break;` 乾淨退出 + `info!("h_state_poller exited")` ✅ |
| dispatch.rs 45 site mechanical extension | `+empty_h_state_cache_slot()` + `None` for invalidation_tx — 必要的測試契約一致性 propagation，不擴範圍 ✅ |
| HStateCacheSlot 鏡射 G3-03 ExecutorConfigCache pattern | `pub type HStateCacheSlot = Arc<RwLock<Option<Arc<HStateCache>>>>` 對齊 BudgetTrackerSlot pattern ✅ slots.rs:119 |
| main.rs spawn 順序 | `spawn_h_state_poller_if_enabled` 在 `ipc_server.run()` detach 前（因為 `set_h_state_invalidation_sender` 需 `&mut self`）✅ main.rs:545-549 |
| ipc_server 三 handler 行為 | `query_h_state_full` / `get_h_state_status` / `invalidate_h_state` — slot=None 時回 structured `gateway_disabled` payload（NOT error）✅ handlers/h_state.rs |
| ipc_server/dispatch.rs 行數 | 590 → < 800 ✅ |
| ipc_server/mod.rs 行數 | 139 + facade re-export HStateCacheSlot ✅ |
| Test coverage | 22 unit tests 涵蓋 cache lookup / staleness / poller smoke / invalidation dedup / DEFAULT-OFF strict env compare / boundary cases / gateway_disabled handler responses / 100-stress invalidate / concurrent read+writer ✅ |
| Cargo lib | **2198 / 0 failed** = baseline 2176 + 22 h_state tests，對齊 commit message claim ✅ |

**結論**：PASS to E4. Phase 1A 完整 daemon 管線 + DEFAULT-OFF 嚴格閘 + StubHStateFetcher 中載入路徑 + race-free select! biased 設計 + cancel token cleanup 完整。

### 1.6 commit `4689fc8` — PM merge (Sub-task A from worktree) 【PASS — union strategy ACCEPT】

**Owner**: PM · **Diff**: docs/CCAgentWorkSpace/E1/memory.md only

| 檢查項 | 結論 |
|---|---|
| Conflict resolved by union | parent 1 (main `0765d0a`) 含 Sub-task B + OBSERVER 條目；parent 2 (worktree `fbfb56f`) 含 Sub-task A 條目；merge result `87fccdb` 兩條「報告檔位置」line **並列保留**（worktree 用「直接傳給 parent agent」+ main 用「`.claude_reports/<ts>...`」雙引兩段） |
| Sub-task A 條目保留 | ✅ Phase 1 Sub-task A 完整段（959 行 SSOT 對齊 / 2198 lib tests / pattern 鏡射 G3-03 / 跨平台 0 風險 / 報告檔位置）|
| Sub-task B 條目保留 | ✅ Phase 1 Sub-task B 完整段（report-index row + 6 條教訓） |
| OBSERVER 條目保留 | ✅ OBSERVER-PIPELINE-POST-F42FACE-CLEANUP 完整段（5 改動 + 7 條教訓） |
| Cargo test post-merge | 2198 / 0 failed，**baseline 不破壞** ✅ |
| Merge commit message | 「merge: G3-08 Phase 1 Sub-task A Rust h_state_cache (commit aa287c4 from isolation worktree)」清楚標明來源 worktree ✅ |
| Mac ff-pull | HEAD 4689fc8 同步成功 ✅ |

**結論**：ACCEPT — union 策略 0 條目丟失，merge message reasonable，post-merge baseline 不變。Multi-session memory race 教訓記入 PM 流程中（per memory `project_multi_session_memory_race`）。

---

## §2 8-Axis Audit Result

### A. 跨平台兼容性（§七 ★★ 強制）— 【PASS】

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && for c in eb65e1e 1c7b20e deac4bc c53c3f9 aa287c4; do git diff $c^..$c | grep -E '(/home/ncyu|/Users/[^/]+)'; done"
```
- 4/5 commit 0 hit 生產代碼
- 1/5（c53c3f9）2 hit：(a) `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--observer_pipeline_post_f42face_cleanup.md` 中 `ssh trade-core "stat -c '%y %n' /home/ncyu/BybitOpenClaw/srv/..."` 為復現 SSH command 字面值（屬「政策反例引用」白名單）+ (b) `docs/CCAgentWorkSpace/E1/memory.md` 中提及「`OPENCLAW_DATA_DIR=/Users/ncyu/...`」為 Mac dev env 範例值（屬 memory 教訓引用，非生產代碼）
- **生產 .py / .rs / .sh 0 hit** ✅

### B. 雙語注釋（§七 強制）— 【PASS】

| 範疇 | 結論 |
|---|---|
| G3-08 Phase 1A Rust 5 new files | mod.rs / types.rs / poller.rs / tests.rs / handlers/h_state.rs 全部 MODULE_NOTE 中英對照齊全 |
| G3-08 Phase 1B Python 4 new files | invalidator.py / query_handler.py 含 top-level docstring + MODULE_NOTE EN + MODULE_NOTE 中；2 test files 文件頭 EN-only（測試文件較寬鬆，可接受） |
| G9-02-FUP 6 sibling | mod / connection / dispatch / parsers / run_loop / tests 6/6 中英 MODULE_NOTE 對照齊全 |
| OBSERVER cleanup 5 修改檔 | cron_observer_cycle.sh 雙語 / checks_derived.py docstring 含 [19] 完整中英 / runner.py inline 中英 / __init__.py export 簡單 / observer_cycle.py 雙語 |

### C. 範圍嚴守（最小影響原則）— 【PASS】

| commit | 範圍評估 |
|---|---|
| eb65e1e G9-02-FUP | refactor 1227→6 sibling 全部 byte-identical 拆分；外部 caller 路徑 `openclaw_engine::ws_client::*` 保持不變；範圍 = 8 files surgical |
| 1c7b20e G3-08 Sub-task B | strategy_wiring.py / CLAUDE.md §九 / passive_wait_healthcheck/* (Sub-task C 範疇) 0 modify；嚴守 PA §10.1 範圍 |
| c53c3f9 OBSERVER cleanup | run_bybit_observer_cycle.py + bybit_load_ws_jsonl_to_postgres.py（孤立 entrypoint）defer to BB-M-3，不擴範圍 ✅ |
| aa287c4 G3-08 Sub-task A | dispatch_request 45 site 機械擴 args（empty_h_state_cache_slot + None for invalidation_tx）= 必要的測試契約一致性 propagation，不算擴範圍 |

### D. SQL Guard（§七 V023 postmortem）— 【PASS】

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --since=2026-04-26 --diff-filter=A --name-only --pretty=format: -- 'sql/migrations/*'"
```
- 0 new V### migration in batch ✅

### E. Hot-path 保留 + Architecture 合理性 — 【PASS】

#### G3-08 Phase 1A 重點驗證
- DEFAULT-OFF env-gate 嚴格 "1" — Rust `std::env::var(ENV_GATEWAY_FLAG).as_deref() == Ok("1")` 對齊 Python `os.environ.get(_GATEWAY_ENV_VAR) == _GATEWAY_ENABLED_VALUE`，4 env case unit test（missing/"1"/"0"/"true"/""）覆蓋
- StubHStateFetcher Phase 1 stub — `Ok(default snapshot version=0)` 設計合理（Sub-task C 替換）
- 10s poll daemon + tokio::sync::watch dedup — `MissedTickBehavior::Delay` + `mark_unchanged()` consume + `wrapping_add` push 完整
- cancel token cleanup — `cancel.cancelled() => break;` + `info!("h_state_poller exited")`
- **Race risk = 0**（PA §14.1 Top 3 風險 #1 反駁）— `tokio::select!` 是單 task 同時只 select 一個 branch；`run_one_poll` 是 sequential await，同 task 內不可能 reentrant；timer + invalidation 觸發 race 不存在
- dispatch_request 45 site mechanical extension — 必要的測試契約一致性 propagation
- HStateCacheSlot 鏡射 G3-03 ExecutorConfigCache pattern — `Arc<RwLock<Option<Arc<HStateCache>>>>` 對齊 BudgetTrackerSlot ✅

#### G3-08 Phase 1B 重點驗證
- threading.Thread daemon=True / asyncio.new_event_loop fire-and-forget — daemon thread 內無 caller 的 loop → `asyncio.new_event_loop()` 無 RuntimeError 風險
- 三層 try/except 吞 IPC error — outer guard:351 / inner thread:201 / IPC close:215+239 fail-closed
- DEFAULT-OFF env=0 — singleton 不 init / invalidate_async no-op
- query_h_state_full IPC route 註冊位置 — ai_service_dispatch.py:120（`_register_handlers()` `self._handlers` dict）；route 永遠註冊（PA §10.1）env=0 也回 empty shell
- 5ms reverse-pull SLA — HANDLER_TTLS=2.0 是 deadlock guard（per PA §G2 註解）
- Lazy import h_state_query_handler — defer 防 bootstrap cycle

#### G9-02-FUP 5 hot-path byte-identical 驗證
- (1) WebSocket connect/handshake 15s timeout (WS-TIMEOUT FA-1 risk #2 ordering preserved) ✅ run_loop.rs:66-70
- (2) subscribe/heartbeat HashSet O(1) dedup + 10-batch + 500ms gap ✅ run_loop.rs:97-103,156-169
- (3) process_message + G9-02 unknown-handler dispatch (ShouldReconnect::No,Yes) ✅ dispatch.rs:135-147
- (4) BackoffConfig 3-60s 退避雙路徑非對稱性（timeout-path 之 sleep→after-incr / main-exit-path 之 before-incr→delay）✅ run_loop.rs:78-86 + L247-251
- (5) G9-02 force reconnect path (ProcessOutcome::ForceReconnect close-frame write + break + outer reconnect with cached subscriptions) ✅ run_loop.rs:200

#### OBSERVER cleanup 重點
- cron wrapper noise pattern 完全移除（`if ... ; then ... else echo "non-fatal" ; fi`）✅
- cron-time env var 陷阱（`export OPENCLAW_SRV_ROOT="$REPO"`）✅
- cycle JSON 路徑解析優先級（OPENCLAW_SRV_ROOT > OPENCLAW_BASE_DIR > Path.home() fallback）✅
- [19] healthcheck 雙軸三態（age × ok ratio）+ OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1 opt-out ✅

### F. 測試覆蓋 — 【PASS】

| Tier | 結論 |
|---|---|
| engine lib baseline | 2176 → **2198 / 0 failed**（+22 h_state tests），post-merge Linux verified ✅ |
| pytest h_state_invalidator + h_state_query_handler | **35 passed / 0 failed** in 0.10s ✅ |
| pytest layer2 chain | 136 passed / 1 warning（@pytest.mark.slow PytestUnknownMarkWarning 既存、無阻塞）— baseline 不變 ✅ |
| healthcheck cron | 19 → 20 check（[19] observer_pipeline_alive 加入），Linux 跑出 20 行 ✅ |
| 0 production regression | cargo test 與 G9-02-FUP commit 後 baseline 一致 ✅ |

### G. PM merge 介入風險 — 【ACCEPT】

詳見 §1.6.

(a) E1 memory.md union resolve 是否丟掉任何條目：**0 丟失**（Sub-task A / Sub-task B / OBSERVER 三段全保留，僅「報告檔位置」line 並列雙引）
(b) merge commit message reasonable：✅
(c) cargo test post-merge 仍 2198/0：✅

### H. MIT EXIT-FEATURES-WRITER-BUG-1 audit findings — 【ACCEPT】

| 檢查項 | 結論 |
|---|---|
| 5 hypothesis 對比完整 | H1 builder 對無 close 也寫 → REJECTED（`build_exit_features_for_tick` 不寫 DB）/ H2 partial close 漏 → PARTIAL / H3 retry 重複 → REJECTED（`ON CONFLICT DO UPDATE`）/ H4 healthcheck SQL bug → PARTIAL（SQL 對但 1:1 假設不成立）/ H5 engine_mode mismatch → REJECTED（兩邊 100% 'demo'）— 涵蓋 5 合理假設 ✅ |
| 雙因 RCA-A + RCA-B 推論證據鏈成立 | RCA-A：`step_0_fast_track.rs:315-340` MICRO-PROFIT-FIX-1 fail-open 在 `entry_notional <= 0.0` legacy/restored dust → return true → 37 halvings spiral；獨立 grep 確認證據鏈 ✅ |
| | RCA-B：`pipeline_helpers.rs:217 try_emit_exit_feature_row` 在 `emit_close_fill` 內被呼，partial reduce 也寫 EF row；獨立 grep step_0_fast_track.rs:379+489 確認 emit_close_fill 路徑 ✅ |
| STRKUSDT dust spiral 7d position lineage | 7d timeline 清楚：entry → close → 2-day gap → 37 halvings 60s 等距 spiral ✅ |
| 3 修復路徑 trade-off 分析 | 路徑 1 (A1/A2/A3 dust eviction) + 路徑 2 (B1/B2/B3 EF semantics fix) + 路徑 3（不推薦單獨用，遮蓋訊號）— 分析合理 ✅ |
| PM 推薦 1+2 cohesive PR | RCA-A + RCA-B 獨立成立 → 修一邊治標不治本 → 1+2 cohesive 合理 ✅ |

**LOW finding L-3**：報告中 H1 拒絕（`build_exit_features_for_tick` 不寫 DB）的證據鏈僅引用文字結論，未提供 grep 復現。E2 獨立 grep 驗證屬實，但建議 MIT 報告下次補一個 grep snippet 證據（與 §7 smoking gun SQL 同等地位）。**不 RETURN**，accept findings as-is.

**結論**：ACCEPT — 5 hypothesis 完整 + 雙因 RCA 證據鏈成立 + 修復路徑 trade-off 合理 + 推薦 1+2 cohesive PR 對齊 RCA 結構。

---

## §3 §九 既有 8 條 checklist + OpenClaw 9 條 §3 checklist

### §九 8 條（每條皆 PASS）
- [x] 改動範圍與 PA 方案一致（每 commit verified per §1）
- [x] 沒有 except:pass 或靜默吞異常（grep 0 hit；invalidator 用 `# noqa: BLE001` 明確標記 fire-and-forget）
- [x] 日誌使用 %s 格式（非 f-string）— ai_service_dispatch.py 那兩處 f-string 是 LLM prompt building 字串拼接，非 logging
- [x] 新 API 端點有 `_require_operator_role()` — N/A（IPC reverse route 非 HTTP API）
- [x] except HTTPException: raise 在 except Exception 之前 — N/A（無 raise）
- [x] detail=str(e) 已改為 "Internal server error" — 0 hit
- [x] asyncio 路由中沒有 blocking threading.Lock 調用 — invalidator 是 sync API（singleton init lock），不在 asyncio route handler 內
- [x] 沒有私有屬性穿透（._xxx）— 0 hit

### OpenClaw §3 9 條
- [x] 跨平台 grep（生產代碼 0 hit）
- [x] 雙語注釋（per §B）
- [x] Rust unsafe 零容忍（0 unsafe block 在新代碼）/ unwrap 限不可恢復場景 / panic 不在交易路徑
- [x] 跨語言 IPC schema 一致（h_state_query_handler.py response shape ↔ Rust HStateSnapshot serde(default) 對齊 PA §5.1/§4.2.1） + serde 型別安全
- [x] Migration Guard A/B/C — N/A（0 new migration）
- [x] healthcheck 配對 — c53c3f9 加 [19] 配對 OBSERVER 修復 ✅
- [x] Singleton 登記 §九 表 — Sub-task C 範圍（per E1 memory），本批次未動 §九 表
- [x] 文件大小（800/1200 行）— 6/6 sibling < 600，dispatch.rs 590 < 800；ai_service_dispatch.py 868 進警告區（pre-existing baseline ~813 + G3-08 +55 = 868）→ **LOW finding L-2**（P3 split ticket future）
- [x] Bybit API 改動先查字典手冊 — N/A（0 Bybit API change）

---

## §4 對抗反問結果

1. **「你說『5 hot-path byte-identical』— 哪些 hot-path？哪幾行對照？」**
   E1/E5 答：5 path 全列（connect / subscribe / process_message / backoff / force-reconnect）
   E2 結論：grep 全 5 hot-path 對應實際 line（66-70 / 97-103,156-169 / 135-147 / 78-86,247-251 / 200）byte-identical with 之前 ws_client.rs 1227 line 內嵌實作 ✅

2. **「你說『race 不可能』— Phase 1A poller 兩 worker 同時 timer + invalidation 怎證明？」**
   E1 答：`tokio::select! { biased; cancel; ticker; invalidation }` + `run_one_poll` sequential await
   E2 結論：select! 同一 task 同時只取一個 branch；await 點之間 task 不可中斷；race=0 ✅

3. **「你說『DEFAULT-OFF strict "1"』— 4 env case test？」**
   E1 答：missing/"1"/"0"/"true"/"" 5 case
   E2 結論：Rust + Python 兩邊 strict 比對 byte-identical (`std::env::var(...).as_deref() == Ok("1")` 對齊 `os.environ.get(...) == "1"`) ✅

4. **「你說『MIT 5 hypothesis 完整』— H1 證據鏈？」**
   MIT 答：`build_exit_features_for_tick` 不寫 DB（只供 4-Gate 決策）
   E2 結論：獨立 grep 確認 — `try_emit_exit_feature_row` 是 EF row 唯一寫 DB 路徑（被 emit_close_fill 呼），`build_exit_features_for_tick` 確實是純 read for Gate 4 ✅。但 MIT 報告下次補 grep snippet evidence。

5. **「PM merge union strategy — 真的零丟失？」**
   PM 答：python regex union（worktree 短條目放前 + main 整段 OBSERVER 放後）
   E2 結論：3 條目（Sub-task A / Sub-task B / OBSERVER）全在 merge commit `4689fc8` 中；只是「報告檔位置」line 雙引並列（兩 parent 各一段，未 deduplicate）— 教訓 OK，**不 RETURN**.

6. **「OBSERVER cleanup 範圍嚴守 — run_bybit_observer_cycle.py 留尾真的合理？」**
   E1 答：孤立 entrypoint 0 上游 caller，按最小影響 defer to BB-M-3
   E2 結論：grep 確認 0 caller，留尾屬正確最小影響範圍嚴守 ✅

7. **「ai_service_dispatch.py 868 進警告區 — 該退回拆嗎？」**
   E2 答：868 < 800 警告 + 1200 hard cap 仍有 332 行 buffer；G3-08 +55 incremental contributor，pre-existing baseline ~813；未來 split ticket 應對齊（per G5 refactor wave 收尾），**LOW non-blocking**.

---

## §5 退回項清單（給 PM）

**0 退回 E1**（無 BLOCKER, 無 HIGH, 無 MEDIUM）

**3 LOW** finding（皆 P3 future polish，**不退回 E1**）：

| ID | 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|---|
| L-1 | LOW | helper_scripts/cron_observer_cycle.sh:76-79 | OBSERVER_RC ≠ 0 時 `exit OBSERVER_RC` 直接 return，BRIDGE_RC 細節不在 wrapper exit code（log 行有資訊） | 未來改 `[ $OBSERVER_RC -ne 0 -o $BRIDGE_RC -ne 0 ] && exit 1`（cosmetic）|
| L-2 | LOW | program_code/.../ai_service_dispatch.py 868 行 | 進入 §九 800 警告區（pre-existing ~813 + G3-08 +55） | 未來 split ticket 對齊 G5 refactor wave 收尾（不阻塞當前合入）|
| L-3 | LOW | docs/CCAgentWorkSpace/MIT/.../2026-04-26--exit_features_writer_bug_audit.md H1 reject | 「`build_exit_features_for_tick` 不寫 DB」結論未在報告中給 grep snippet 證據（E2 獨立驗證屬實） | MIT 下次報告補 grep snippet 對齊 §7 smoking gun SQL 同等證據地位 |

**E2 直修項目**：0（無 typo / lint / dead import 命中本批次）

---

## §6 PM Sign-off 推薦

**結論**：**PASS to QA**（強制工作鏈下一步）

| 項 | 結論 | 派發建議 |
|---|---|---|
| 6 commit 結構性 | 5 PASS + 1 PASS（merge accept union） | — |
| MIT findings | ACCEPT | PM 開 EXIT-FEATURES-WRITER-BUG-1-FIX 派 E1（cohesive 1+2 修，3-5h）|
| PM merge | ACCEPT（union 0 丟失 + cargo 2198/0 不破壞） | — |
| 退回項 | 0 BLOCKER / 0 HIGH / 0 MEDIUM | — |
| 3 LOW | 全 P3 future polish | (L-1) cron wrapper polish ticket / (L-2) ai_service_dispatch.py split ticket 對齊 G5 refactor wave / (L-3) MIT 報告補 grep snippet 教訓記入 MIT memory |

**強制工作鏈下一步**：QA 接手；QA pass 後 PM Sign-off commit。

**派發建議（PM 後續）**：
1. 立即可派 EXIT-FEATURES-WRITER-BUG-1-FIX（P1，E1 owner，3-5h）— 路徑 1 (A1+A3) + 路徑 2 (B1) cohesive PR；待 [3] healthcheck 自動 PASS
2. P2 batch 收尾 wave：BB-M-3（OBSERVER 留尾）+ ai_service_dispatch.py split + cron wrapper polish + MIT 報告 grep snippet 補
3. PA 派 PAPER-STATE-DUST-RESTORE-AUDIT（P2，0.5-1d）— `paper_state::restore_from_db` dust handling
4. ML training data hygiene wave（P2，1-2d）— 全期 EF dust spiral noise 比例量化 + 補回填

---

## §7 E2 簽核

**Audit Methodology**：8-axis（A-H）獨立執行 + 對抗反問 7 條 + 跨平台 grep + 雙語 grep + 範圍 verify + cargo test 2198/0 + pytest 35/0 + layer2 136/0 + healthcheck 20 line cron pipeline + PM merge 3 axis verify

**E2 立場聲明**：
- 不寫業務邏輯 ✅
- 不修典型 typo / lint / dead import 範圍 ✅（本批次 0 命中）
- 對抗式驗證每個聲稱 — 不接受 happy-path 答案 ✅
- 嚴格範圍 verify — 不擴範圍到非 Tier 4 commits ✅

**E2 REVIEW DONE**: PASS to QA · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-26--tier4_batch_review.md`

# E5 全倉 read-only 優化審計 — srv/ 全域 · 2026-07-03

**Baseline commit**: `d68a13298` (local HEAD, dirty multi-session tree — memory/ 檔案有未提交改動, 未觸碰)
**範圍**: rust engine / control_api / GUI / helper_scripts / .claude 配置 / 治理文檔 / Linux runtime read-only 證據 (ssh trade-core)
**硬邊界遵守**: 0 修復 / 0 功能改動 / 0 部署 / 0 重啟 / 0 DB mutation / 0 auth 觸碰。Linux 證據全部 read-only（ps / /proc / psql SELECT+SHOW）。
**Verdict**: FINDINGS — 15 項（5 HIGH / 4 MEDIUM / 3 LOW / 3 INFO），其中 2 項為正面確認（前輪 finding 已修）。

對照前輪: `2026-06-14--full_repo_optimization_audit.md`（commit 976d420e）。本輪距前輪 1219 commits（Codex 5.5 主駕時代）。

---

## 摘要表

| # | 等級 | 位置 | 當前問題 | 建議改法 | 預估收益 | 回滾成本 |
|---|---|---|---|---|---|---|
| F1 | HIGH | step_1_2_klines_indicators.rs:~117 | 1m 指標每 tick 無條件重算（PERF-1 只做了 5m 半邊） | epoch cache 同 5m gate 模式 | ~28μs/tick × ~320 tick/s ≈ 9ms/s CPU（引擎現 41-47% 單核） | 低（有 5m gate 既成模式+回歸測試模板） |
| F2 | HIGH | Linux PG runtime config | shared_buffers=128MB/work_mem=4MB 出廠默認，385GB 庫 cache hit 62.38% | ALTER SYSTEM 調 4-8GB 預算內（需 E3/operator） | cache hit 62%→95%+，klines 查詢延遲大幅降 | 低（config-only，可回調） |
| F3 | HIGH | TODO.md | 233 行卻 59,562 tokens，超 Read 25k cap，每 agent 啟動必讀 | §0 歷史 row 歸檔、SHA 改連結 | 每 agent-session 省 ~35-50k tokens × 高頻 | 零（純搬移） |
| F4 | HIGH | 13 檔 >2000 硬限 | 06-14 審計 0 檔破限 → 現 13 檔，無 documented exception | 按 G5-07/09 sibling 拆分模式分批 | token 稅 + review 可行性恢復 | 低（純機械搬移有既成模式） |
| F5 | HIGH | helper_scripts/research/cost_gate_learning_lane/ | 87 檔 63.6k LOC，_utc_now×81/_read_json×74/_authority_preserved×32 複製貼上 | 抽 lane_common 共享模組 + invariant test | 每輪 loop 開發省數千 token；消 authority 判準 silent drift 面 | 中（86 檔 import 改動需回歸） |
| F6 | MEDIUM | step_4_5_dispatch.rs:452-489 | 每 tick 深拷貝 4 個 panel snapshot（含 HashMap<String,..>），panel 60s 才更新 | slot 改存 Arc<Panel>，clone Arc | ~2-8μs/tick + allocator 壓力 | 低 |
| F7 | MEDIUM | 6 檔 `_percentile` | 同名異契約（5× q∈[0,1] vs 1× p∈[0,100]）+ NaN 過濾不一致 | 共享 helper + 契約鎖定測試 | 消 silent math drift 面 | 低 |
| F8 | MEDIUM | app/layer2_tools.py:613/674/729 | 3/4 SearchProvider 在 async def 內同步阻塞（subprocess 30s / urlopen 60s / DDGS） | to_thread 包裹（照 main.py:803 模式） | latent：接線後防 event loop 凍結 60s | 低 |
| F9 | MEDIUM | helper_scripts/research/ | 356 py 檔 / 184.8k LOC 一次性 evidence 腳本無歸檔策略 | stale 腳本歸檔規約（對齊 TODO non-consumable 標記） | 降 grep/glob 噪音 + agent 誤讀 stale 面 | 零 |
| F10 | LOW | cost_gate_learning_lane_cron.sh | 1980 行 bash 僅 6 函數，逼近 2000 硬限 | 邏輯下沉 Python，bash 留 orchestration | 可維護性 | 中 |
| F11 | LOW | app/ipc_client.py:140 | 單連線 + asyncio.Lock 串行全部 engine IPC | 保持現狀或連接池（僅在 GUI 併發實測超標後） | 現負載下無收益，記錄 ceiling | — |
| F12 | LOW | Linux PG | pg_stat_statements 未裝 | CREATE EXTENSION（E3 action） | F2 調參可證據驅動 | 零 |
| F13 | INFO | 根目錄大 md | AE_INVENTORY_CONSOLIDATED.md 422KB / CLAUDE_CHANGELOG.md 1.4MB | 已標歷史快照，維持；勿全文讀 | — | — |
| F14 | INFO | （正面）前輪 F2/F3 + PERF-1 5m + drift gate | 均已修/已落地 | v739 實走驗證 drift gate | — | — |
| F15 | INFO | Linux engine 運行基線 | 41-47% 單核 / RSS 2.1GB / 71 threads | 記錄基線供下輪對比 | — | — |

---

## F1 — 1m 指標每 tick 無條件重算（PERF-1 Phase 2 未做）[HIGH / FACT / high confidence]

**Evidence**:
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_1_2_klines_indicators.rs` — `let mut indicators = self.compute_indicators(sym);` 每 tick 無條件執行（無 epoch gate）。
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs:645` — `cached_or_recompute_indicators_5m` 已實作 epoch cache（PERF-1, 2026-06-14），**只覆蓋 5m 路徑**；1m 路徑維持前輪狀態。
- 前輪 microbench（E5 memory 2026-06-14 深掘）: `compute_all_with_lambda` = 28.0μs/call（release, 100 bars）。
- Linux runtime（本輪實測, ssh read-only）: engine PID 2368227, `/proc/stat` delta 5s = 40.8% 單核瞬時；ps 累計 47.3%；uptime 10h24m。

**Impact**: 以 demo tick rate ~320 tick/s（前輪 h0_checks 推算）計，1m 重算 ≈ 9ms/s CPU ≈ 引擎單核佔用的顯著成分。5m gate 已證明同 bar 內輸出 bit-identical，1m 同理（輸入=closed bars）。
**Caveat（前輪已識別）**: 1m 路徑 compute 後有 `apply_hurst_regime_label_for`（有狀態滯回）；本輪查證 source `settings/risk_control_rules/risk_config_demo.toml` `[hurst] enabled = false`（Phase A dormant）→ 滯回語意風險當前為零，但 gate 實作仍應把 hurst push 一併 gate 並走 E2（runtime TOML 為權威，本輪未逐一 ssh 驗 runtime 副本值）。
**Fix 方向**: 複製 5m epoch-cache 模式（key = 1m last closed `open_time_ms` + lambda），`latest_indicators` map 仍每 closed-bar 刷新（step_6/commands ATR 讀該 map）。fix_spec 已在 E5 memory 2026-06-14 條目，caller_check 已做過。

## F2 — Linux PG 全默認配置，違背 4-8GB 預算 [HIGH / FACT(config)+INFERENCE(影響) / high confidence]

**Evidence**（ssh trade-core read-only, 2026-07-03）:
- `SHOW shared_buffers` = **128MB**（PG 出廠默認）；`SHOW work_mem` = 4MB；`SHOW effective_cache_size` = 4GB。
- `pg_database_size('trading_ai')` = **385 GB**。
- `pg_stat_database` cache hit ratio = **62.38%**（blks_read 累計 15.3B）。健康 OLTP 期望 >99%。
- `pg_stat_user_tables`: `compress_hyper_51_2224_chunk`（屬 **klines** hypertable, `_timescaledb_catalog.hypertable WHERE compressed_hypertable_id=51` 查證）seq_scan = **41,863,163** 次 vs idx_scan 15,543；多個 compress chunk 各 3.4M+ seq scans。
- 主機 `free -g`: 124GB 總量 / 115GB available / 85GB buff-cache → OS page cache 兜底中，headroom 充足。
- CLAUDE.md 硬件 memory（`project_hardware_constraints`）: PG 預算 4-8GB。

**Impact**: 128MB shared_buffers 對 385GB 庫 = 持續 buffer eviction churn；62% hit ratio 表示大量讀走 OS cache 雙重拷貝路徑；klines 壓縮 chunk 被高頻輪詢=每次付解壓成本。OS cache 掩蓋了最壞延遲，但 CPU/拷貝稅持續繳。
**Fix 方向**（E3/operator action，超出本輪 read-only 邊界）: `ALTER SYSTEM SET shared_buffers='4GB'`（需重啟）、`work_mem='32-64MB'`、`effective_cache_size='48GB'`（reload 即可）；並先裝 pg_stat_statements（F12）定位 41.8M seq scan 的 caller 再調 klines 壓縮策略（近期 chunk 延後壓縮）。
**注意**: 涉 PG restart → 本輪僅報告，不執行（read-only 硬邊界）。

## F3 — TODO.md token 質量 59.6k，超工具讀取 cap [HIGH / FACT / high confidence]

**Evidence**: `wc -c TODO.md` = 129,772 bytes / 233 行；Read tool 自報 **59,562 tokens（cap 25,000，強制截斷）**；awk 查有 3 行 >2000 字元、表格 row 普遍 1000-6000 字元（v596→v738 全歷史 evidence SHA 內嵌正文）。§0 多個 row 自標 "historical evidence only" / "superseded"。
**治理依據**: `docs/agents/todo-maintenance.md` + CLAUDE.md §十: "Reports are linked, not pasted" / "DONE detail should be archived"。行數治理（800/2000）被超長行繞過——按行計 233 行合規，按 token 計是全倉最重讀取稅。
**Impact**（token 稅軸: 頻率×體量×壽命）: context-loading 路由令每個 agent 啟動讀 TODO.md；每 session 一次 ≈ 25k tokens（截斷後）且**讀不到完整 dispatch queue**（operational 危害：agent 只看得到前 58 行，§1 Active Queue 在截斷區外）。全 role × 每日多 session → 全倉最高單檔年金化成本。
**Fix 方向**: §0 rows 中已 superseded/historical 者移 `docs/archive/` 或 PM report，正文只留 pointer+sha 短鏈；活 row 壓縮到 ≤250 字元/行（對齊 MEMORY.md 索引規約）。

## F4 — 13 個 git-tracked 源檔破 2000 行硬限 [HIGH / FACT / high confidence]

06-14 前輪審計「0 檔破 2000 硬限」→ 本輪 13 檔（全部 wc -l 實測，git ls-files 過濾）:

| 檔 | 行數 | 性質 |
|---|---|---|
| helper_scripts/research/tests/test_alpha_discovery_throughput.py | 6798 | 測試 |
| helper_scripts/research/alpha_discovery_throughput/discovery_loop.py | 5954 | loop 熱檔 |
| helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py | 4639 | 測試 |
| helper_scripts/research/alpha_discovery_throughput/runtime_runner.py | 4500 | loop 熱檔 |
| helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py | 3789 | loop 熱檔 |
| program_code/research/microstructure/fill_sim.py | 2796 | research |
| rust/openclaw_engine/src/intent_processor/tests.rs | 2785 | 測試 |
| helper_scripts/canary/engine_watchdog.py | 2412 | **prod 關鍵 watchdog** |
| rust/openclaw_engine/src/tick_pipeline/commands.rs | 2266 | prod |
| helper_scripts/research/cost_gate_learning_lane/status.py | 2238 | loop 熱檔 |
| rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs | 2193 | **tick 熱路徑 prod** |
| rust/openclaw_engine/src/config/risk_config_tests.rs | 2040 | 測試（前輪 1812 已 WARN, 繼續長） |
| rust/openclaw_engine/src/intent_processor/mod.rs | 2032 | prod |

**查證**: grep TODO.md + docs/agents/*.md 無 documented exception；操作面正在拆別的檔（c6f21fd57 event_consumer 拆分）但上表未列入。d68a13298 裁決確認 800=軟警告/2000=硬限（E5 正本）。
**Impact**: 熱檔（step_4_5_dispatch / discovery_loop / runtime_runner / status.py 每 loop 版本被讀改）token 稅最高；硬限本意「不許 merge」已被 Codex 時代事實繞過 = 治理 drift。
**Fix 方向**: 按 E5 memory 教訓 16（G5-07/09 sibling tests 拆分, 0 production touched）分批；優先序=熱檔（discovery_loop / runtime_runner / status / step_4_5_dispatch）> 測試檔。step_4_5_dispatch 註明 borrow-check 邊界（mod.rs 文檔）——策略迭代塊不可拆，但 helper/tests 可外移。

## F5 — cost_gate_learning_lane 87 檔 63.6k LOC 複製貼上叢 [HIGH / FACT / high confidence]

**Evidence**（同名函數重複計數, grep 實測）: `_utc_now` ×81、`main` ×80、`_read_json` ×74、`_build_parser` ×74、`render_markdown` ×66、`_write_json` ×58、`_write_text` ×50、`_parse_dt` ×43、`_truthy` ×35、**`_authority_preserved` ×32**、`_sha256` ×20、`_candidate_identity` ×21。80/87 檔各自 argparse 獨立腳本。
**Impact**:
1. **Token 稅**: 這是全倉最熱開發面（TODO 顯示 v596→v738 每版本新增/複製腳本），每輪 PM/E2/E3/BB 讀寫；63.6k LOC 中估 15-25% 是重複 boilerplate。
2. **Silent drift 風險**（E5 memory 教訓 15）: `_authority_preserved` 是 authority 汙染判準——32 份字面複製，任何一份單獨演化 = 治理判準分裂，審計工具查不出。同理 `_candidate_identity`/`_truthy_authority`（×12）。
**Fix 方向**: 抽 `cost_gate_learning_lane/lane_common.py`（utc_now/read_json/write_json/sha256/parse_dt/truthy + authority invariant 一份）+ cross-module invariant test；新腳本強制 import。不動已消費的歷史腳本（audit 證據鏈完整性）——只改仍活躍者 + 新增規約。

## F6 — 每 tick 深拷貝 4 個 panel snapshot [MEDIUM / FACT(代碼)+INFERENCE(量級) / med confidence]

**Evidence**: `step_4_5_dispatch.rs:452-489` — `try_clone_panel_snapshot`（:100, `guard.clone()` 深拷貝）每 tick 對 funding_curve / oi_delta / liquidation_pulse（+paper 模式 btc_lead_lag）執行；`LiquidationPulsePanel`（openclaw_core/src/alpha_surface.rs:437）含 `HashMap<String, LiquidationPulse>` + `String source_tier` → 每 tick 數十次 String/HashMap 配置。Panel 由 aggregator 60s flush 一次 → 「輸入更新頻率 vs 消費頻率」落差（同 F1 模式）。另 `cached_or_recompute_indicators_5m` 命中路徑每 tick `IndicatorSnapshot.clone()`（含 `HurstResult.regime: String` 配置——與前輪 F5 symbol interning 重疊，引不重論）。
**Impact**: 估 2-8μs/tick + allocator 壓力；tick 熱路徑非 SLA 違規（H0 gate 通過），屬浪費類。
**Fix 方向**: slot 型別 `Arc<TokioRwLock<Option<T>>>` → `Arc<TokioRwLock<Option<Arc<T>>>>`，consumer clone Arc（O(1)），surface borrow 語意不變；或按 panel snapshot_ts_ms 做 epoch cache。改動面 = slots.rs + 4 consumer 點 + writer 端 wrap。

## F7 — `_percentile` 同名異契約 ×6 [MEDIUM / FACT / high confidence]

**Evidence**: 6 份實作——`execution_spine.py:30`（q∈[0,1], NaN 過濾）、`tail_dislocation_meanrev/screen.py:203` + `shallow_retune_execution_realism.py:99`（q∈[0,1], **無** NaN 過濾）、`aeg_s3_event_execution_realism/builder.py:126`（q∈[0,1], NaN 過濾）、`app/replay_execution_calibration.py:632`（q∈[0,1], 無過濾）、`replay/calibration_label.py:368`（**p∈[0,100]**, Type-7, byte-equal Rust 契約）。
**Impact**: 前輪已標的 hazard 持續存在且新增（execution_spine 是 Codex 期新檔）。同名異契約跨檔複製比純複製更危險——移植代碼時單位錯 100×。NaN 混入無過濾版本 → sorted() 順序未定義 → 統計靜默錯誤。
**Fix 方向**: 共享 stats helper（research 面一份 + control_api 面一份）+ 命名區分（percentile_frac vs percentile_pct）+ 契約鎖定測試。calibration_label 的 byte-equal-Rust 版本不動（有明確設計意圖）。

## F8 — layer2_tools 3/4 SearchProvider 阻塞 event loop（latent）[MEDIUM / FACT(代碼)+ASSUMPTION(觸發面) / med confidence]

**Evidence**: `app/layer2_tools.py` — `LocalLLMWebSearchProvider.search`（async def :608 內 `subprocess.run(..., timeout=30)` :613）；`LocalLLMSearchProvider.search`（:670 內同步 `client.generate(..., timeout=60)` :674 → 底層 urlopen）；`WebPilotSearchProvider.search`（:723 內同步 `DDGS().text()`）。僅 `PerplexitySearchProvider` 用 `httpx.AsyncClient`（:529）正確。
**觸發面查證**: `search_with_degradation` 全倉 grep **0 個 production caller**（僅 tests/test_layer2.py）→ L2 mesh dormant（設計意圖，不建議刪）。對照正確模式: `main.py:803`（to_thread）、`system_legacy_routes.py:281`（to_thread）、`ollama_client.is_available_async`（to_thread）。
**Impact**: latent——L2 tool 接線後單次 web search 可凍結整個 uvicorn event loop 30-60s（違反 main.py:393 自家守則）。前輪 F3 修了 layer2_routes 同類問題但未掃 sibling。
**Fix 方向**: 三處包 `asyncio.to_thread`（各 1-3 LOC，不改語意）。
**假陽性候選附判斷**: `local_llm_factory.py:296` urlopen 在 sync `_chat_completion`（:265）內、`ollama_client.py` generate/list_models 均 sync def、strategist_agent 在 MessageBus 同步 on_tick 回調/背景線程呼叫（:456-460 顯式 L2 走 background thread）→ 均非 event-loop 阻塞，**不列 finding**。

## F9 — helper_scripts/research 356 檔 / 184.8k LOC 無歸檔策略 [MEDIUM / FACT(體量)+INFERENCE(稅) / med confidence]

**Evidence**: find+wc 實測。cost_gate_learning_lane 87 檔 / alpha_discovery_throughput 17 檔 19.8k LOC / 其餘 250+ 檔散佈 20+ 子目錄。TODO.md 大量標注 "do not consume stale packets"，但生成這些 packet 的一次性腳本無界定 active/stale 的機制。
**Impact**: agent grep/glob 命中大量 stale 腳本 → 誤讀誤引風險 + 搜索噪音稅；184.8k LOC 已超 rust prod 面體量。
**Fix 方向**: research 面建 `archive/` 子目錄規約（對齊 docs/archive 模式）；SCRIPT_INDEX.md（現 1588 行）分節標 active/historical。

## F10 — cost_gate_learning_lane_cron.sh 1980 行 bash [LOW / FACT / high confidence]

**Evidence**: wc -l = 1980（距硬限 <1%——按 E5 memory 教訓 6 屬必警示帶）；`grep -c '^[a-z_]*() {'` = 僅 6 函數 → 大體線性內聯 bash。
**Impact**: bash 無測試框架保護的 2k 行 orchestration；下一次追加即破硬限。
**Fix 方向**: 步驟邏輯下沉為 Python 子命令（lane 內已全是 Python 腳本），bash 只留 env/lock/heartbeat（FD 教訓已修的部分保留）。

## F11 — ipc_client 單連線鎖串行 [LOW / FACT(設計)+INFERENCE(上限) / med confidence]

**Evidence**: `app/ipc_client.py:140` `asyncio.Lock` 串行所有併發 IPC 調用（檔頭自述設計意圖）。
**Impact**: 吞吐上限 ≈ 1/RTT（<5ms SLA → ~200 req/s）；GUI 多 panel 併發刷新時 head-of-line blocking。現量級（本地單 operator console）遠未觸頂 → 不建議現在動，記錄 ceiling 供 GUI 併發增長時參考。有設計意圖（fail-closed 簡單性），非缺陷。

## F12 — pg_stat_statements 未安裝 [LOW / FACT / high confidence]

**Evidence**: `SELECT count(*) FROM pg_stat_statements` → `ERROR: relation does not exist`；pg_extension 無此 ext。
**Impact**: F2 的 41.8M seq scan 無法歸因到 query/caller；PG 調參無法證據驅動（違 E5 workflow「baseline 先行」）。
**Fix 方向**: E3 action——`shared_preload_libraries` 加載（需重啟, 可與 F2 調參同批）。

## F13 — 根目錄歷史大 md [INFO / FACT]

`AE_INVENTORY_CONSOLIDATED.md` 422KB/3922 行（已標「2026-04-25 歷史快照+06-10 校準」）；`docs/CLAUDE_CHANGELOG.md` 1.4MB（append-only 版本日誌）。兩者有明確定位標注，Read cap 天然防全文讀。維持現狀；唯一建議：確保無 agent 流程要求全文讀。

## F14 — 前輪 finding 修復確認（正面）[INFO / FACT]

- 前輪 F2（release profile）: `rust/Cargo.toml:69-70` `lto="thin"` + `codegen-units=1` 已落地（commit 471c1811b）。
- 前輪 F3（layer2_routes urlopen）: 已改 async httpx（layer2_routes.py:528 注釋自證）。
- 前輪 F1 之 5m 半邊: PERF-1 epoch cache 已落地且質量高——只快取 Some/lambda 入 key/remove_symbol 清快取/專屬回歸測試檔 `tests/perf1_indicators_5m_cache.rs`（bit-identical 並列對比測試）。
- drift-gate 死循環（v710-v738 批准即 stale）: `d0eeafb41`（2026-07-03）post-approval drift gate 取代 exact-sha final check，docs/tests/.codex 豁免 + deny-by-default；**source 側已解，v739 實走待驗**——本輪不重複立 finding，僅注記 E5 視角：該 over-gate 在 06-27~07-02 間消耗 8+ 個 PM 版本零 fill 產出（commit 速率 111-258/day vs exact-sha quiet window 結構性不可滿足），修復方向正確。

## F15 — Linux runtime 基線記錄 [INFO / FACT]

engine PID 2368227（10h24m uptime）: 瞬時 CPU 40.8% 單核（/proc 5s delta）、RSS 2.1GB、71 threads；主機 load 0.74/32 cores、RAM 124GB 總/115GB available。uvicorn 5 workers 各 ~200MB。F1 落地後預期 CPU 顯著下降——留作 before/after 對照點。

---

## 假陽性候選匯總（附判斷依據，裁決交 PM/operator）

1. `main.py:803` / `system_legacy_routes.py:281` urlopen — 已 to_thread 包裹，非阻塞。
2. `ollama_client.py` 同步 urlopen/time.sleep — sync def + 呼叫方在線程上下文（strategist L2 顯式 background thread）；retry 分支自標 dead-code by design。
3. `.venv` 出現在 program_code 樹內（93MB）— git check-ignore 證實 IGNORED，非 repo bloat；僅污染本地 find 掃描。
4. `ollama_client` retry `time.sleep(0.5)` — max_retries=0 默認 dormant，設計意圖注釋在檔。

## 盲區（negative space，見 StructuredOutput assumptions）

未跑 profiler（flamegraph/py-spy/memray）、未 cargo bench/bloat、IPC RTT 未實測、41.8M seq scan caller 未定位、鎖持有時長未測、runtime TOML 未逐檔驗、tests 套件時長未測、.codex 讀頻未知。

---

E5 OPTIMIZATION REPORT: report path: docs/CCAgentWorkSpace/E5/workspace/reports/2026-07-03--full_repo_optimization_audit.md

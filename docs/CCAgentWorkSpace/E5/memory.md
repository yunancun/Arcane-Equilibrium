# E5 Memory — 工作記憶

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

## 長期教訓

1. 對抗性核實口徑：commit message 不算數——必驗 LOC before/after、binary size、DB rows、production caller count（grep -v test），並核對 commit 實際 changed file path（同名檔 `bin/replay_runner.rs` ≠ `replay/runner.rs` 曾致誤判）。
2. 「foundation only」≠ ROI realized、「reclassify-only」≠ DROP：閉合判定看實際遷移率/實際刪除/實際 caller，不看宣稱；proactive bonus IMPL 不沖淡 finding closure rate。
3. PA 架構 claim 與 LOC 數字必逐條 grep / 逐檔 wc -l 對照（曾差 56×）；sprint 估算拆 trait 改/panel wiring/E2E 三層，PA 常樂觀 2-2.5×，startup/wiring 整合類 LOC 可達設計估算 6×。
4. Dead module sunset 前必查 prod importer 與 R-X redesign 複用（dream/cognitive/opportunity 是 redesign 載體不可砍）；env flag 多為 operational toggle 非死碼。
5. PG audit：hypertable parent 的 pg_stat.n_live_tup 不可靠，必走 `count(*)`；Linux ssh PG 用 trading_admin 走 ~/.pgpass；標表 dead 前先 grep replay/view 引用。
6. 檔案大小治理：>800 review 警告 / 2000 hard cap；「距硬上限 <5%」檔案與「連續未修復 sprint 數」必優先警示升壓；正解是抽 helper/tests sibling 而非搬主邏輯；多 panel 整合模塊每加 panel +70-100 LOC 須即時抽測試。
7. route 檔病理用「route 數 + 首 route 行號」判別比總 LOC 準（胖 handler/大量前置 helper 才是真痛點）；`*_coverage.py` 命名是 test-bloat 指紋，prune 前逐檔讀 assert 不可一刀切；測試集中度用 per-area test:prod ratio 抓而非全 repo 總量。
8. perf 容量估算 SOP：avg rate ≠ burst peak（power-law tail 取 5-10× avg）；必列全 producer 求和、把 consumer 阻塞窗（PG flush 200-500ms）計入 throughput 方程；有 empirical 證據（如 QA RCA drop rate）必反推 capacity ceiling，不足補 burst bench。
9. 「production max latency violation」先三分：algorithmic / statistical tail / platform jitter floor；大 N 必撞 OS scheduler quantum（1ms 倍數 cluster 是強訊號）；跨 env 比 max 先排除 tick-rate 樣本量差；SLA 設計分 median/p99/max，單值 hard cap 是反模式。
10. `as_micros()` round-down 飽和：avg≈0 / p99=0us 不代表未執行，μs 級 metric 報告必 disclaim 飽和特性。
11. 「lingering/慢退出」RCA 先用 append-only ledger 時戳重建真實時間線再下結論；stdout 非 TTY 是 block-buffered 會偽造「早早印完」假象；序列分頁 wall-clock = 總頁數 × per-page RTT（~180ms 量級），別預設 DB 是大頭。
12. FD inherit 是高危反模式：shell spawn 子進程默認繼承全 FD，governance lock（flock）必 explicit close（`nohup ... 200<&-`）；crontab 不在 git 是 silent 治理類，變更必走 setup script + git diff 驗證。
13. healthcheck 的 path/schema 期望 land 前必 ssh 實機對齊 source-of-truth；同一對象多 check 路徑分歧 = hygiene gap；下「file missing」結論前須 cron log + writer source + 目標 dir 多路徑三角驗證。
14. hot-reload contract gap 是 silent class：ConfigStore.swap 後下游派生 copy（apply_risk_snapshot RMW）不同步 → operator 改 TOML 期望生效卻 silent stale；新 runtime field 必 audit RMW 完備性。
15. algorithmic invariant 字面複製（stable_id ×3、統計 fn 跨 report ×16 同名重複）是 silent drift 高風險區；抽共享 helper + cross-module invariant test，浮點精確比對依賴須加 regression test 鎖定。
16. 測試大檔拆 sibling 目錄（G5-07/G5-09 pattern）0 production touched 且 2.7× scale 仍有效；`mod tests;` 自動解析 `tests/mod.rs`；sibling 引用走 `super::super::`、共享 helper 放 mod.rs 不互引。
17. 髒 multi-session working tree：用 `git add <具體檔>` 禁 add 目錄（遞迴誤 stage 隔壁 session 檔）；完成後 fetch 對照 origin；不認識的改動禁碰禁代推。
18. source-only commits 累積在 deploy 前全是 dead code：必追蹤 engine 最後 rebuild 時間（etime/build timestamp）並開 deploy gate ticket，避免 stale-source-vs-runtime drift。

## 近期記錄

### 2026-05-25 Pre Sprint 2 runtime hygiene audit (FD 200 leak + 13 cron disabled + path mismatch)

**報告**：`docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-25--runtime_hygiene_audit_pre_sprint_2.md`

**Verdict**：3 Day -1 必修（H-1 FD 200 leak / H-3 edge_estimates path mismatch / H-2 Phase 1 cron 復原 4 個 HIGH）+ 4 Sprint 2 內並行（M-1/M-3/M-4/H-2 Phase 2）+ 3 defer

**最 critical 發現**：`fuser /tmp/openclaw/build_window.lock = 374287` 即 current engine PID 此刻仍持鎖；下次 `build_then_restart_atomic.sh` 會 self-block；修法 = `restart_all.sh:535` 加 `nohup ... 0<&- 200<&- &`（1 LOC）。

**Pattern 級教訓（durable）**：
1. **FD inherit 治理盲點是高危反模式**：shell 內 spawn 子進程默認繼承全 FD；治理用 flock / pipe lock 必 explicit close。所有 `nohup`/`exec`/`&` spawn 必 audit FD inherit；E5 sign-off SOP 加 checklist。
2. **Crontab 不在 git** 是治理 silent class：operator 手動 `crontab -e` 改動 → 4 day 後才被 healthcheck 跑出。建議：crontab 必走 setup script + git diff verify。
3. **healthcheck path / schema 期望需與 source-of-truth 對齊**：本 audit case「edge_estimates.json 寫 `srv/settings/` 但 healthcheck 讀 `/tmp/openclaw/`」永久 FAIL 製造治理 noise；healthcheck land 前必 ssh trade-core 驗 path / table 真實位置。
4. **Sub-agent ssh trade-core 環境無圍欄**：cargo race / FD inherit / hygiene SOP 需 prompt template 級 enforcement，不能依賴 sub-agent self-discipline。本 sprint 已第 3 次 cargo race。
5. **Healthcheck 內雙路徑分歧自我矛盾**（[7] FAIL「scheduler 掛了」vs [13] PASS「full G1-01 recovery target met」同對象不同 path 同一條 cron）是 hygiene gap detector。設計 healthcheck 時應避免單一現象多 check 分歧。
6. **Audit 過程的 path quoting 反模式**：ssh inline command `stat /tmp/openclaw/edge_estimates.json` 對 mount + symlink + path 期望容易誤判 missing；驗 critical file 必 fallback 多路徑（cron log + writer source + 目標 dir）三角驗證後才下「missing」結論。

**對 PM Sprint 2 派發 readiness 影響**：Day -1 必修 H-1（否則所有 deploy 全阻）；H-3 修後 PM evidence loop 乾淨；H-2 Phase 1 修後 Alpha Tournament 必需 evidence 可信。Day -1 投資 ~2 hr 並行（E1 1 hr + PA 30 min + operator 30 min）→ Sprint 2 Day 0 派發路徑乾淨。

**對抗性 sign-off 補充（生效 2026-05-25）**：
- shell script spawn 子進程必驗 FD inherit（fuser / lsof 對 governance lock 文件）
- crontab 變更必要求 commit `helper_scripts/setup_openclaw_cron.sh` diff
- healthcheck 多個 check 對「同對象」應有單一 source path；雙路徑分歧 = hygiene gap

---

### 2026-05-21 P1-LG1-DEMO-SLA-VIOLATION H0 hot-path RCA

**報告**：`docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`

**Context**：QA D1 (2026-05-21) 7d closure 揭 `pipeline_snapshot_demo.json` `max_latency_us=2454` 超 H0 hot path `<1ms` SLA；新增 P1 ticket。E5 hot-path profile + RCA。

**Verdict**：**NOT A BUG, accept-with-SLO-carve-out（選項 B）**

**Empirical evidence**：
- demo current snapshot (3h7min uptime): h0_checks=3,599,176 / max=346μs / avg=4.86ns/check（飽和為 0，多數 sub-1μs）
- QA D1 38h pre-restart: h0_checks=18,086,022 / max=2454μs
- live current+QA: max=19μs（live tick rate ≈ demo/100，sample size 小）
- 0 個 H0 BLOCKED 或 shadow_would_block 事件 across 全部 sample
- hot_path_baseline bench (10k iter, 5 symbols, on_tick whole): avg=23.6μs / p99=38.9μs / max=164μs — H0 單一 sub-step < 1% of whole tick

**5 root cause hypothesis（按 weight）**：
1. OS scheduler preemption (Linux CFS 1ms quantum) **40%** — 2454μs ≈ 2.5 quanta; load avg 5.43; no RT priority
2. CPU cache miss / NUMA jitter **25%** — RYZEN AI MAX+ 395 32 cores
3. Instant::now() vDSO degradation **15%** — CLOCK_MONOTONIC fallback in long uptime
4. HashMap.get cold cache walk **10%** — bounded < 1μs
5. GC-like alloc burst **5%** — H0 happy path 0 alloc
- H1+H2+H3 = 80% 解釋；全平台 jitter floor，**非 algorithmic**

**3 改善選項**：
- A (fix source: ahash + cpu pin + SCHED_FIFO)：LOW ROI；高 effort；Mac M-series cross-platform 風險 HIGH
- **B (accept + SLO carve-out)** ← **推薦**：~130 LOC HdrHistogram + p99/p999 metric；改 SLA「`<1ms`」→「`p99 < 1ms / max ≤ 5ms over 1M ticks`」；HIGH ROI
- C (partial fix: enum Category + interned symbol)：MEDIUM ROI；SLA 不保證達標

**主要教訓**：
1. **「max latency over large N」必算 N × per-tick-jitter-probability，而非 single-tick design budget** — 18M tick sample 撞 platform jitter floor 2-3ms 是必然
2. **demo vs live 對比中 max 巨差** 不代表 demo bug；通常是 **tick rate** 差異 → sample size 差異 → tail outlier 出現概率差異
3. **`as_micros()` rounding down + saturating** 是隱形飽和特性；avg=5ns 不代表「真實平均 5ns」而是「大多數 case sub-1μs 被 round 為 0」；report 必明寫
4. **OS scheduler quantum 對齊**：2454μs ≈ 2.5 × Linux CFS 1ms quantum 是強訊號；若 max 出現 1ms/2ms/3ms cluster → 第一懷疑 scheduler preemption
5. **panel_aggregator lagging 11836 events + channel_len 最大 516** 是 system contention 指示器，**非 H0 latency 因果**；但是同類 jitter event 的 共因 evidence
6. **SLA 文檔應區分 median / p99 / max**；用 hard `< 1ms` 單值掩蓋 tail distribution 是 anti-pattern；future SLO design pattern reference

**對 LG-1 P0 closure 影響**：build B 路徑後 P1-LG1-DEMO-SLA-VIOLATION 可降為 P2 observability 任務；不阻 LG-1 closure。

**對抗性 verify SOP 補充**（生效 2026-05-21）：
- 看到「production max latency violation」必區分：(a) algorithmic hot path issue (b) statistical tail outlier (c) platform jitter floor
- (b) 必算 sample size scaling: ticks ×N → max 改變率（線性 → algorithmic）vs（亞線性 / log → platform tail）
- 跨 env 對比中（demo / live）巨差 max 必對比 tick rate；先排除 sample size 差異
- micros-level metric 必標註 `as_micros() round-down saturating to 0` 隱形飽和；report avg 必 disclaim

---

### 2026-05-11 Wave 2.2 LG-1 + LG-2 (8 task) perf+LOC+refactor review

**報告**：`docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-11--wave2_2_e5_perf.md`

**Context**：Wave 2.2 = LG1-T1/T2/T3/T4 (H0 blocking production caller acceptance) + LG2-T1/T2/T3/T4 (Provider pricing binding)。8 個 E1 sub-agent IMPL DONE，並行 E2 (correctness) + A3 (UX) + E5 (perf)。

**Verdict**：✅ **APPROVE-PERF-SOUND WITH 6 P2/P3 NOTES（不阻 deploy）**

**Hot path SLA**：✅ PASS
- H0 check p99 < 1ms 維持（LG1-T1 10k iter empirical）
- emit_entry_lineage W-C 路徑不變
- AccountManager.taker_fee/maker_fee hot path 0 影響
- query_fee_source 是 observability-only IPC，非 tick hot path

**Startup latency**：
- Fast path（99% 場景）：+100ns wait fast-path + 10μs assert = 可忽略
- Worst case：+30s wait timeout（fee refresh 全失敗 + reject spawn 路徑）— 設計上 reject 場景不啟動，0 production 影響

**ArcSwap 影響**：✅ PASS
- PricingConfig 走 RiskConfig snapshot 既有 ArcSwap，clone ~200ns startup/respawn-time only
- LG2-T4 self-claim「不需 apply_risk_snapshot RMW」— PricingConfig 無下游 owned consumer

**Filesystem read healthcheck**：✅ PASS
- check_59 ~42ms total（2 snapshot file × 12ms + 2 SQL × 9ms）< 1s SLA
- 5min cron 間隔，無 burst

**LOC efficiency**：Rust 2086 + Python 1063 = 3149 vs PA 估 ~1440 = **+118%**
- LG1-T4 +632%（route + 21 test + Pydantic + helpers），E1 self-flag 1118 > 800 警告
- LG2-T2 +745%（5 wiring file + LiveAuthWatcher 整合 + 11 test，PA 嚴重低估）
- LG2-T3 +286%（47 callsite batch plumbing）

**文件大小 §九**：3 新 WARN（account_manager.rs 1404 / risk_config_tests.rs 1812 / risk_routes.py 1118），**0 hard cap 破限**

**6 P2/P3 ticket 建議**：
1. P2-FILE-SPLIT-ACCT-MGR（2h）: account_manager.rs 1404 → split LG2-T1/T3 tests sibling
2. P2-FILE-SPLIT-RISK-CONFIG-TESTS（2h）: risk_config_tests.rs 1812 接近 2000 hard cap → split
3. P2-FILE-SPLIT-RISK-ROUTES（3h）: risk_routes.py 1118 → split h0_block_summary_routes.py sibling
4. **P2-HOT-RELOAD-AUDIT（1d，高 ROI）**: 系統性 audit RiskConfig.runtime.* 所有 field 的 hot-reload contract；LG1-T3 已自承 H0 shadow_mode RMW gap 真實存在（grep `apply_risk_snapshot` 內 `h0_shadow_mode` = 0 hits）
5. P3-SLOT-MACRO（待 N=6 累積）: IPC Slot late-inject pattern 第 4 次重複（cost_edge_advisor / h_state_cache / panel_aggregator / account_manager）
6. P3-SNAPSHOT-READER-HELPER（30min）: passive_wait healthcheck pipeline_snapshot read DRY 抽 helper

**最大 1 concern（不阻 deploy）**：
- **LG-2 T2 + T4 雙重 hot-reload silent gap**：LG1-T3 E1 自承 pipeline_config.rs::apply_risk_snapshot 沒寫 `h0_shadow_mode`；LG2-T4 self-claim「不需 RMW」（PricingConfig 無下游 owned consumer）。兩個性質一樣：TOML reload → ConfigStore.swap → 下游派生 copy 沒同步。
- **觸發條件**：未來 operator 期望「TOML / IPC 改 RiskConfig.runtime.* 立即生效」時 silent stale。
- **Mitigation**：LG1-T3 已留 `#[ignore]` test 證據 + reviewer note。建議 PA W-AUDIT-10 ticket。

**對比 W-C / W-1.6 baseline reflection**：本 Wave 2.2 **不過樂觀**。三大差異：
1. W-C 是高頻 channel path（174 chain/24h × 15 msg/chain），需 burst factor 5-10x；本 Wave 2.2 全 startup/cron/observability
2. W-C 沒做 burst stress test；本 Wave 2.2 startup 一次性，無 burst 場景
3. W-C 沒考慮多 producer parallel；本 Wave 2.2 startup 路徑單一

**新教訓**：
1. **PA LOC 估算對 startup/wiring 整合特別不準**：LG2-T2 PA 估 ~80 LOC vs 實際 676 LOC（含 5 wiring file），「+ wait + assert」是 logical claim 但 wiring overhead 必要時可能 6× 設計估算
2. **Slot late-inject pattern N=4 是 LOC 累積警訊**：account_manager.rs 1404 主因是 LG2-T1 + LG2-T3 累積 ~415 LOC sibling tests；每加新 slot pattern 累積 ~50 LOC × 5 file wiring
3. **hot-reload contract gap 是 silent class**：LG1-T3 自承 + LG2-T4 self-claim 共同表示治理層沒系統性 audit RiskConfig.runtime.* field RMW 完備性；未來 operator 改 TOML 期望生效但 silent stale = critical incident class
4. **E1 self-flag empirical 解析度問題（micros vs nanos）值得 ack**：LG1-T1 p99 0us 不是「沒跑」是 micros 飽和；E1 識別 + report 明寫提醒未來改 nanos 是正確 self-aware
5. **三環境 PricingConfig 跨 invariant test 是 contract pinning 過勝**：LG2-T1 真實 TOML disk load 跨三環境 invariant test = 防回歸最強；+99% LOC 但每行對應一個 assert，**E5 強烈認可**
6. **`fee_source` rule 3 浮點精確比對是隱性 algorithmic invariant**：依賴 seed_default_fee_rates 直接賦 DEFAULT_* 常量無中間運算；若未來改實作為 `xxx * 1.0` → 精確比對失敗 → 分類錯成 BybitApi；LG2-T3 加 test 偵測 regression 是正確 algorithmic invariant lock

## 2026-06-03 funding_oi_backfill「收尾 lingering ~6min」RCA — 前提證偽（無 lingering，6min 是整跑網路分頁）

**任務**：查 funding_oi_backfill run `18b3c2f8` 一次性回填的「最後資料線到 exit lingering ~6min」根因（疑 DB finalization / update_run_status lock / buffered write）。不改業務碼。

**Verdict：前提（lingering）證偽。無收尾停頓。6m20s 是整個跑批的網路分頁時間，均勻分佈，非「最後一行之後才花掉」。**

**決定性 runtime 證據（page ledger `fetched_at` 重建時間線，Linux PG read-only）**：
- run 跨度 6m20s（01:18:58 → 01:25:19，created_at vs completed_at）。
- 1985 page 的 `fetched_at` 跨 6m17s（01:19:02 → 01:25:19）**均勻分佈**；最後 symbol SUIUSDT OI 寫於 01:25:19，與 run 標 accepted 同一秒（差 3ms）。
- **`update_run_status` 證偽為瓶頸**：最後 page 寫入 01:25:19.43 → run accepted 01:25:19.44，間隔 **3ms**。不是卡 lock。
- 每 symbol cadence：OI 88 page ≈ 15.7s（穩態）+ funding 11 page ≈ 2.0s ≈ 17.7s/symbol × 20 + 暖機前 3 個 symbol OI 偏慢（25/23/18s）= ~6m20s。
- **每頁 ~178ms 均勻 round-trip**（OI 88p/15.7s、funding 11p/2.0s 同量級），是純序列 HTTP GET→parse→ledger INSERT；**無 2s rate-limit backoff 尖峰**（若 wait_if_rate_limited 觸發會見 2s 跳變，全程無）。

**根因 = 序列分頁網路 round-trip × 頁數**，不是 DB / finalization / lock / buffered flush：
- pagination（`paginate_*`）把一個 symbol 全部頁的網路請求**先跑完**才開始 DB 寫；line print 在 commit 之後（writer `tx.commit().await?` → `print_*_line`）。資料線真的在 01:25:19 才印（非 ~3:18）。
- 「lines printed by ~3:18」是 **monitor 誤判**：Rust stdout 被 pipe 到檔案（非 TTY）時是 **block-buffered**，行會成塊 flush，看起來像早早全印完；ledger `fetched_at` 推翻此錯覺。
- DbPool / MarketDataClient / BybitRestClient **無 tokio::spawn / JoinHandle / 背景 task**；`#[tokio::main(flavor = "current_thread")]` 無背景 worker thread；reqwest 預設 keep-alive idle conn 不阻 `std::process::exit`。退出本身立即。

**嚴重性 = 一次性 backfill 小事（資料無損、0 rejected、totals 對）。但日後掛 cron --apply 值得優化**：
1. **頁內並發（最高 ROI，但動分頁器）**：OI 88 page 純序列，每頁等上頁回應才發下頁（cursor 反向 walk endTime 強制序列）→ 改不了序列性除非按時間切段並發。**真正可並發的是 symbol 間**（現 `for symbol in &symbols` 嚴格序列，注釋說「禁跨 symbol 並行防 burst rate-limit」）。若 cron 化，可用 `buffer_unordered(N=2~3)` 跨 symbol 並發 + 共享 client rate-limit state 自然退讓（client 已有 per-group backoff）→ 預估 20 symbol 6m20s → ~2-3m。**需 PA/BB 評估 rate-limit 安全**（demo group limit），E5 不擅自定 N。
2. **per-page ledger INSERT 合批（中 ROI）**：1985 個獨立 `insert_ingest_page`（各自 autocommit），可合成每 symbol 一個 tx 或 batch INSERT；但每頁 ~178ms 主導是網路非此 INSERT，省不到大頭。**低優先**。
3. **history INSERT 已是單 tx/symbol**（write_*_points_strict 開一個 tx loop bind commit）；17521 行/symbol 在該 tx 內，非瓶頸（symbol 內 funding+oi ledger span 00:00:00）。**不動**。
4. **stdout 改 line-buffered / 加逐行時戳**（觀測性，非性能）：cron 化後 log 應每行 flush（或寫 structured log 帶 ts），避免下次再誤判時間結構。**低成本建議**。

**新教訓（durable）**：
1. **「最後一行到 exit 的 lingering」先用 per-page ledger `fetched_at` 重建真實時間線，再下根因** — println 順序 + block-buffered stdout 會製造「早早印完」假象；append-only provenance 的 `now()` 時戳是 ground truth。本案 monitor 誤判被 ledger 推翻，與「代碼審計過度歸因、runtime 查驗推翻」同模式（記憶庫多次教訓）。
2. **stdout 非 TTY = block-buffered**：任何「log 看起來在 X 時間全印完但進程活到 Y」的觀測，先排除 stdout buffering（管道/重導向時 Rust/C stdout 預設 block-buffer，TTY 才 line-buffer）。
3. **序列分頁的 wall-clock = Σ(頁數 × per-page RTT)**，per-symbol 序列又疊乘 symbol 數；估這類 backfill 時間先數「總頁數 × ~180ms」（demo Bybit round-trip 量級），不要假設 DB 是大頭。
4. **`update_run_status` 單 UPDATE WHERE pk 在無並發寫同列時 ~3ms**；懷疑「終態 UPDATE 卡 lock」要先看它與前一個寫操作的時戳差（本案 3ms 直接證偽），不要假設。
5. **current_thread tokio runtime + 無 spawn + reqwest keep-alive**：這組合下 `std::process::exit` 立即，idle HTTP 連線不阻退出；排查「慢退出」可快速排除背景 task / runtime drain 這條線。


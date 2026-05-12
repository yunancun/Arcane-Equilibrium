# E5 Memory — 工作記憶

## 項目上下文（2026-04-24）

- 當前 Phase：Live_Ready ⚠️（5 門控 Rust 可驗證 4；真實 live 流量 0）
- 測試基準：engine lib 1980 / 0 failed + bin 38（2026-04-24 P1-11 audit 收尾）；pytest 2996
- 系統模式：demo（21d 穩定期 2026-04-16 起算，最早 2026-05-07 解鎖 P0-3 重評）
- 代碼規模大幅變化：Python `main_legacy.py` 5113 → **468 行**（DEDUP Tier B 已閉環）；Rust engine 代碼持續增長至 ~49k 行

## 工作記憶

### 2026-04-24 全程序優化審計

**報告位置：** `docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-24--full_chain_optimization_audit.md`

**關鍵發現：**
- P0 硬違反：8 項 Rust 檔 ≥1200 行，其中 `event_consumer/mod.rs::run_event_consumer` **1695 行單 async fn**（項目史上最大單 fn）
- P1 性能：tick_pipeline 115 處 clone、`ai_budget/tracker.rs` 16 處鎖、startup 串行 await 可並行化
- P2 可讀性：bb_reversion 1143、ws_client 1136、ipc_server/mod.rs 1192（距硬上限 8 行）

**相對 2026-04-01 的進展：**
| 指標 | 2026-04-01 | 2026-04-24 | 變化 |
|------|----------|----------|------|
| Python main_legacy.py | 5,113 | 468 | ✅ -4,645 |
| Python f-string logger（生產碼） | 182 | ~1 | ✅ 清零 |
| int(time.time()*1000) 內聯 | 156 | 30（ai_agents/） | ✅ -126 |
| Rust tick_pipeline/mod.rs | — | 1035 | ✅ 拆分完成 |
| Rust ≥1200 硬違反 | 未統計 | **8 檔** | ⚠️ 新發現 |
| Rust 最大單 fn | (_process_pending_intents 462) | **run_event_consumer 1695** | ⚠️ 惡化 |

**2026-04-12 Wave 閉環確認：**
- `push_capped<T>`, `now_ms()`, `is_stale()`, `clamp_confidence()`, `build_intent()` 均已實裝且未回彈
- `TickContext<'a>` zero-copy 保留
- parallel DB flush (tokio::join! 7 tables) 保留

**建議路線：**
- 先清 8 項 Rust P0（2-3 週）→ P1 性能（1-2 週）→ P2 可讀性持續
- 與 P0-2 21d demo 穩定期（至 ~2026-05-07）並行，不影響 Live gate

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-01 | 全程序優化審計 v2 | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-01--optimization_audit.md` |
| 2026-04-12 | E5 Performance Optimization Wave 最終報告 | `docs/CCAgentWorkSpace/E5/2026-04-12--e5_optimization_final_report.md` |
| 2026-04-24 | 全程序鏈優化審計（P0 Rust 硬違反焦點） | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-24--full_chain_optimization_audit.md` |
| 2026-05-08 | 全程序鏈優化審計（HEAD 4e2d2883；30 opportunity）| `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-08--full_chain_optimization_audit.md` |
| 2026-05-09 | 對抗性核實 2026-05-08 audit 30 finding 24h 修復結果（HEAD 7fccad06）| `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-09--optimization_verification.md` |
| 2026-05-09 v2 | 對抗性核實 v2（baseline 455d796e → HEAD 1bd55689；34 commits 48h）| `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-09--optimization_verification_v2.md` |
| 2026-05-09 v3 | 對抗性核實 v3（baseline faf2d131 → HEAD da2aba11；5 commits）+ PA redesign architectural cross-check | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-09--optimization_verification_v3.md` |
| 2026-05-10 | W-C Caveat 1+2+3 fix Rust+Python perf+LOC+refactor review | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-10--w_c_fix_e5_perf_review.md` |
| 2026-05-11 | Wave 1.6 P1-FILL-LINEAGE-DROP perf re-audit | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-11--p1_fill_lineage_drop_e5_perf.md` |
| 2026-05-11 | Wave 2.2 LG-1 + LG-2 (8 task) perf+LOC+refactor review | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-11--wave2_2_e5_perf.md` |

## 2026-05-10 W-C Caveat 1+2+3 fix perf review 教訓

**任務**：2 E1 sub-agent 並行 IMPL DONE（Rust 877 LOC + Python 254 LOC），與 E2 並行 senior code review；E5 獨立 perf + LOC + refactor 視角。

**Verdict**：✅ **APPROVE WITH 3 P2 OPTIMIZATION SUGGESTIONS（不阻 deploy）**

**Empirical 量測（Linux PG live data）**：
- EXPLAIN ANALYZE execution time = **3.93ms**（新 LEFT JOIN 100% index hit on `idx_agent_decision_edges_from` + `decision_objects_pkey`）
- check_55 end-to-end cold/warm: 20.13/6.62/8.21ms（p50/p95），遠 < 1s SLA
- mpsc channel buffer 1024 / chain msg 15（+50% 修前 10）/ 24h 174 chain 遠低於 1024 capacity
- Engine binary 20.06 MB / cargo build release 24.52s（baseline 同範圍）
- 7 主檔 LOC 全 < 800 警告線（runtime_shadow.rs 657）；2 pre-existing 警告檔（tests.rs 1063, step_4_5_dispatch.rs 1557）仍 < 2000 hard cap

**3 P2 refactor opportunities（按 ROI 排）**：
1. **D-1 高 ROI**：`stable_id` 算法字面複製 3 處（step_4_5_dispatch.rs vs runtime_shadow.rs vs paper shadow path）— 抽 `compute_spine_ids()` helper 避免未來 id drift bug
2. **D-2 中 ROI**：emit_entry_lineage 內 5 String clone 重排（ns 級 perf，可讀性微提升）
3. **D-3 低 ROI**：`tx.expect("checked Some")` 改 `let Some(tx) = tx else` early return（pure idiom）
4. **D-5/D-6 P2**：tests.rs 1063 + step_4_5_dispatch.rs 1557 pre-existing > 800 警告，仿 G5-09 pattern 拆

**最大 concern**（不阻 deploy）：**stable_id 算法字面複製是「algorithmic invariant drift risk」非 perf SLA 影響**。未來改 hash 算法必同步 3 處否則 stub report 與 real-fill report id 不對齊 = audit chain 斷。E1 IMPL self-flagged C-1，已用中文注釋警示 + unit test invariant lock；E5 建議 P2 抽 helper + cross-module invariant test 補強。

**LOC efficiency 判斷**：
- Rust 877 vs PA 估 260-370 = +137%（5 unit test 比 PA spec 3 多 2 / 8 處 fixture 連動 / 175 注釋）— **不破限**但偏 verbose
- Python 254 vs PA 估 80-120 = +112%（SQL extension 80 LOC + state_changes helper + isolation import workaround）— **合理**

**E5 vs E2 視角分工**：E5 純看 hot path latency / LOC ratio / refactor opportunity；E2 看安全 + 對抗 + 業務邏輯。重複領域 minimal。

**新教訓**：
1. **Rust hot path 估算 vs 實測**：try_send 50-200ns + struct alloc 2-5μs 主導；5 transitions ~3-6μs 增量遠 < 0.3ms tick SLA budget — 設計時 PA 估 ≤1ms 偏保守，實際 ~6μs 級
2. **mpsc capacity 1024 / chain 15 msg = 68 chain in-flight 容量**充裕，但理論未來高頻策略 (>100 intent/s) 會觸 fail-soft warn — P3 監控 ticket
3. **PG hypertable + LEFT JOIN 規模**：1 年外推 ~317k object / 254k edge 仍 < 50ms warm query；hypertable chunk drop 機制 + index 設計足夠
4. **stable_id 字面複製**：跨檔 invariant 改 stable_id 算法必同步 N 處，是 silent drift 高風險區；E5 識別「algorithmic invariant 字面複製」應加入 audit checklist
5. **「pre-existing baseline exception clause」適用 step_4_5_dispatch.rs 1557**：本 PR + 56 LOC 不破限；不擾動拆檔節奏

## 2026-05-09 v3 verification 教訓

**任務 A 5 commits 結論**：✅ STRUCTURAL CLEAN（0 hard cap 2000 引入）；hot path 性能淨 0；`ad14db07` Donchian guard 修真實 logical leak-bias（bb_breakout `is_long && price < dc.upper` 含 current bar → Hard mode 永不通過 = 反業務 bug）。1 NEW 800 warn = `helper_scripts/cron/ml_training_maintenance.py` 430→935 (+118%)，5 EXTENDED_JOBS spec only。**5 commits 全 source-only**（v2 lesson #4 持續），engine 跑 5/9 14:02 build (etime 2:58:24)。

**任務 B PA redesign 結論**：⚠️ PARTIAL AGREE
- ✅ 5 root cause 結構診斷 4/5 證據成立（Strategy interface alpha-poverty + Strategist scope = 調參器 + Analyst L2-L5 dormant + 風控鐵血 vs alpha 放羊 全部 grep 證據成立）
- ❌ strategist_agent.py LOC：PA 引「45000」實際 **799 LOC**（差 56×）— PA 引 CLAUDE.md §三 錯讀
- ⚠️ Sprint 估計樂觀 2×：R-1 PA 估 3-4 sprint vs E5 真估 8-9（含 5 panel wiring + 5 既存 migration + E2E）；R-1+R-2+R-3 總 PA 8-10 vs E5 17-19 sprint
- ⚠️ TA 高速公路隱喻過度：TickContext 已含 funding_rate/index_price/best_bid/ask/OI 5 cross-asset field（first-class），真 friction = cross-section panel + orderflow + sentiment（PA 沒區分）
- 🟡 9 dead modules sunset 判定過度：dream 936 / cognitive 524 / opportunity 861 是 R-3 Hypothesis Pipeline + R-1 factor library 候選 IMPL 載體（4468 LOC dead production-wise 但其中 ~1900 LOC 是 R-X redesign 候選載體，不應 sunset）
- ✅ Hypothesis Pipeline first-class（R-3）+ AlphaSurface（R-1）+ Per-alpha-source live promotion（R-4）= 真實 leverage point；E5 強烈認可

**對 W-AUDIT-8a Alpha Surface Foundation 影響**：CLAUDE.md §三 已加 SPEC PHASE，spec `2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`。E5 估算 R-1 真實 8-9 sprint，與 spec 估計需對照 reconcile。

**新教訓**：
1. **PA architectural claim 必逐條 grep 證據對照** — PA「45000 LOC」明顯誤；架構級 audit 比 hot path optimization 更易引入抽象斷言
2. **PA LOC 數字必逐檔 wc -l 對照** — 56× 差距足以 derail 重構估算
3. **Sprint 估計拆三層**：(a) trait 改 (b) panel wiring (c) E2E + treat acceptance；PA 樂觀 2.5× 因只算 (a)
4. **Dead module sunset 必查 R-X redesign 是否複用** — 避免砍 dream/cognitive/opportunity 後 R-3 沒了候選載體
5. **TickContext 已含 cross-asset 5 field（funding_rate/index_price/best_bid/ask/OI）**：PA「TA 高速公路 vs 其他泥路」二分法過度，真 friction 是「cross-section panel + microstructure + sentiment」需要中央化 panel maintainer 而非 strategy own buffer
6. **Donchian leak-bias 修法是教科書** — `donchian_prior` = `donchian(&high[..n-1], ...)` slice borrow O(1) + 同 N 元素 max/min = 0 性能成本 + 修真實業務 logical bug；對抗 lookahead bias 反模式（memory `feedback_indicator_lookahead_bias.md`）

**對抗性 sign-off SOP v3 補充**：
- PA architectural claim 必逐條 grep 證據對照
- PA LOC 數字必逐檔 wc -l 對照
- Sprint 估計必拆「直接 trait / 間接 panel wiring / E2E」三層
- Dead module sunset 必查 R-X redesign 是否複用
- 5 commits 後 source-only Rust 累積必標 → deploy gate ticket

## 2026-05-09 v2 verification 教訓

**runner.rs misidentification 反轉真修**：v1 標 C-2 ❌ MISIDENTIFIED（commit `3372eb18` split 的是 bin/replay_runner.rs 不是 replay/runner.rs）。v2 commit `477b5cc0`（5/9 15:39）真實修復：runner.rs 2467 → 1167 LOC，把 1322 行 tests 抽到 sibling runner_tests.rs（1299 LOC），加 static regression `test_replay_runner_split_static.py` 永久守護。**E5 v1 對抗性 push back 採信生效**。

**結果**：closure rate 35% → 43%（+8%）。30 finding 中：
- ✅ 9 真 fix（v1=6；新加 H-2 lambda + C-2 runner.rs + H-5 state machine 升級）
- ⚠️ 8 partial（v1=9）
- ❌ 13 not fixed（v1=15）

**3 治理紅旗（連續 48h+ 0 動）**：
1. C-1 909 MB damaged dump 連續 48h 0 動（最大失能）
2. H-8 lg5 schema drift / H-10 collation refresh 兩個 1-hour fix 連續 48h 0 動
3. H-7 orjson 遷移率連續 2 輪 < 1%（ipc_dispatch.py 主路徑仍 0 json_fast）

**新教訓**：
1. **拆法 ≠ audit 預期結構但達 LOC 目標也算 ✅**：runner.rs 拆是 test extraction 而非 audit §C-2 預期 5 sibling structural split，但 LOC 達 §九 hard cap 內，static regression 永久守護，結果合格
2. **commit message 用詞精確化**：v2 commit `477b5cc0` 用 "true replay runner" 顯式區分 v1 標的 bin/，治理層誤判 lesson 真實 commit 內反映
3. **proactive scientific IMPL bonus 不沖淡 closure rate**：W-AUDIT-6c portfolio tail risk gate（cc6476dd 1028 LOC，VaR/CVaR/EVT/GPD/stationary bootstrap/3 stress scenarios）是高質量 IMPL 但**不在 30 finding 範圍**，bonus 計入但不算入 30/30 閉合
4. **Source-only commits 累積風險**：v2 期間 8 個 "source-only / no rebuild" commit（risk/strategy/learning），engine 仍跑 14:02 build 37min etime，**這些改動 deploy 前都是 dead code**，需 deploy gate ticket 避免 stale-source-vs-runtime drift

**對抗性 sign-off SOP v2 補充**：
- 必驗 LOC（before/after diff）
- 必驗 binary size delta（OS file 命令）
- 必驗 DB rows delta（PG n_live_tup / size）
- 必驗 production caller count（grep -v test）
- commit message 與實際 changed file path 必對齊核實
- **新加**：source-only commits 累積追蹤（engine etime + last rebuild timestamp）
- **新加**：proactive scientific IMPL bonus 標記（不沖淡 finding closure rate）

## 2026-05-09 對抗性核實要點

**核實口徑**：commit message 不算數，必驗 LOC + binary size + DB rows + 真實 caller。

**結果**：30 finding 中 ✅ 6 真 fix / ⚠️ 9 partial / ❌ 15 not fixed (35% true closure rate)。

**3 Critical 中 2 未解**：
1. C-1 909 MB damaged dump 完全沒 DROP（risk_verdicts_damaged 仍 903 MB on Linux PG）
2. C-2 `replay/runner.rs` 2467 LOC **完全沒拆** — commit `3372eb18 split replay runner binary` 誤導，實際 split 的是 `bin/replay_runner.rs` (CLI binary 1599→626) 不是 `replay/runner.rs` (production 2467)
3. C-3 binary strip 真做：25 MB → 20.6 MB（-17.6%；少於預估 -32% 因 LTO/codegen-units 未調）

**重要新教訓**：
1. **commit message disambiguation 必查**：`bin/replay_runner.rs` ≠ `replay/runner.rs` 兩檔同名易誤讀；E5 audit/verification 必逐 commit 對照具體檔案路徑
2. **Audit 數字校驗**：deepcopy audit 標 10 處實際 18 處（沒掃 state_compiler/runtime_bridge/learning_queries/control_ops）；E5 audit count 必含這些 cold path
3. **「foundation only」≠「ROI realized」**：H-7 orjson 加 helper + 5 callsite 切換是 foundation；657 stdlib json 仍未動 = <1% 遷移；commit 用 "expand" 但 expand 範圍僅 5 檔
4. **「reclassify-only」≠ DROP**：W-AUDIT-5a 用 V068/V070/V071 reclassify guard 替代真 DROP（commit body 自承找到 active references 改保守路徑）— 合理工程妥協但 audit 點不算閉合
5. **partial scope ArcSwap**：ai_budget config_cache 真改 ArcSwap，usage_cache 仍 RwLock（mutate-on-record 不適合 ArcSwap）— PA 妥協明確標注 trade-off
6. **0 動 high ROI 1-hour fix**：H-2 lambda:True / H-8 lg5 column drift / H-10 collation refresh — 都是 audit 標高 ROI low cost 但本輪 0 commit 觸

**對抗性 sign-off SOP** (生效 2026-05-09)：
- 必驗 LOC（before/after diff）
- 必驗 binary size delta（OS file 命令）
- 必驗 DB rows delta（PG 直查 n_live_tup / size）
- 必驗 production caller count（grep -v test）
- commit message 與實際 changed file path 必對齊核實

## 2026-05-08 全程序鏈審計 key findings

- 規模演進：Rust 184k LOC（+49k vs 4-24）/ Python 260k LOC
- Rust >800 warn = 70 / >2000 hard = **1**（runner.rs 2467；唯一 hard violation；REF-20 Sprint A R3 直接生長）
- Python >800 warn = 72 / >2000 hard = **1**（test_h_state_query_handler.py 2641）
- Engine binary 25 MB **未 strip**（debug info 殘留）— `Cargo.toml [profile.release] strip = "symbols"` 可一鍵 -8 MB
- **Hot path clone count -37%** vs 2026-04-24（115 → 73 in tick_pipeline 4 檔）— 性能優化軌道正確
- **DB 32 GB 中 909 MB 純 24 天前 damaged dump 死數據**（risk_verdicts_damaged 903 MB single-handed）— 必 DROP
- Dead schema 大批揭發：learning 30 表 67% 0-row / replay 9 表 55% 0-row / observability 6 表 83% 0-row
- 18 blocker 確認：H0_GATE 業務 caller = 0 (block #9) / CostEdgeAdvisor caller = 0 (block #10) / executor_agent.py:224 lambda:True hardcoded (block #8)
- LG-5 reviewer 死於 wiring 揭發：`learning.governance_audit_log` n_live_tup = 0
- **無 CI workflow 包含 aarch64-apple-darwin** — M5 部署前必補
- API log 揭發 lg5 schema drift 2 列 (slippage_bps / net_bps_after_fee 不存在) → healthcheck 永久 FAIL
- 30 opportunity 拆：4 Critical / 11 High / 9 Medium / 6 Low
- Python `copy.deepcopy` 10+ 處在 lease/auth state read 路徑 — 非熱點 critical 但 measurable -30% latency 機會

教訓：
1. PA panorama 列 V059 edge_estimate_snapshots 為 dead 不準確（實際 457 row + replay_full_chain_routes 在用）— 標 dead 前先 grep replay_full_chain_routes/V059 references
2. PG `n_live_tup` 在 timescale parent 顯示 0 但 hypertable chunk 有真數據（trading.fills 13018 rows but parent stat shows 0）— audit 必走 `count(*) FROM <hypertable>` 而非只看 pg_stat_user_tables.n_live_tup
3. Linux ssh PG 需用 `trading_admin` 走 `~/.pgpass`，非 `trading_user`

## 2026-04-24 TODO.md Audit 發現

**執行時間**：2026-04-24 04:00-05:30 CEST (E5 self-audit)  
**方法**：自動檔案行數驗證 + 手工複雜度分析 + 規範檢查  
**報告**：`docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-24--4.24TodoAudit.md`

### 關鍵發現

**P0 警報**：
- Rust 8 個檔超硬上限（1200 行）；Python 2 個檔超硬上限
  - 最嚴峻：`event_consumer/mod.rs::run_event_consumer()` 單 async fn 1696 行
  - 次嚴峻：main.rs 2062 行；instrument_info.rs 1975 行
- **生效日期**：即刻（W24 前必須解決，否則違反 CLAUDE.md §九）

**拆分驗證結果**：
- ✅ TICK-PIPELINE-MOD-SPLIT-1：`mod.rs` 1035 < 1200，通過
- ✅ ma_crossover split：6 sibling，max 536 < 800，優秀；可作 bb_reversion 拆分範本
- ✅ IPC-SERVER-TESTS-SPLIT-1：11 sibling，max 343，完美
- ✅ main_legacy.py：468 + 5 sibling 1558 = 2026，瘦身 60%；Tier B 閉環確認
- ⚠️ bb_breakout/grid_trading：宣稱與實際不完全同步；需補審

**可讀性 pain points**：
1. event_consumer fn 1696 行（P0 優先）
2. main.rs async_main 邏輯雜糅（P1）
3. bb_reversion 1143 行未拆分（P2）
4. Python governance 3600 行邊界模糊（P2）
5. ipc_server/mod.rs 1192 行距硬限 8 行（P2）

**Singleton 表**：完整；QC-3 audit FUP 已補登 _scheduler/_scheduler_lock/_LEADER_LOCK_*

**Dead code**：無 orphan；全有標記（E5-P1 FUP 已執行 call_ollama_timed/from_guardian_review 清理）

### 執行計畫

| Phase | Timeline | 主要任務 | 投資 |
|-------|----------|---------|------|
| A | W0 即刻 | event_consumer fn 拆分 | 2-3d |
| B | W1-2 | main.rs / instrument_info.rs / live_session_routes.py | 4-5d |
| C | W3-4 | 其餘 5 Rust 硬違反 | 4-5d |
| D | 長期 | 策略層拆分 / governance 重構 / monkeypatch 遷移評估 | TBD |

**推薦開工**：立即 W0（不延遲；無前置依賴）

### 2026-04-26 G5-09 tick_pipeline/tests.rs 拆分（commit `a5b6f17`）

**Ticket**：G5-09（P1，新編號）— PM 2026-04-26 ground-truth audit 揪出 `tick_pipeline/tests.rs` 3524 行（§九 1200 上限的 194%，repo 最大檔）

**Pattern**：套用 G5-07（commit `913b536`，event_consumer/tests.rs split）

**結果**：
- 拆 11 sibling + mod.rs 聚合，全 < 800（§九 警告線），最大 maker_kpi_hot_reload.rs 652 行
- 0 production file touched（純測試重組）
- 90 個 test fn 字節級保留（除 import path super:: → super::super::）
- shared helpers `make_event` / `make_signal` 移到 mod.rs，sibling 透過 `super::make_event(...)` 引用
- Linux release `cargo test --release -p openclaw_engine --lib` = **2162 passed / 0 failed**

**Sibling 列表**：
| Sibling | Lines | Tests |
|---|---|---|
| mod.rs | 52 | 0（only helpers）|
| pipeline_kind_governance | 173 | 13 |
| fanout_canary | 103 | 6 |
| dual_rail_dispatch | 199 | 7 |
| emit_close_fill | 507 | 11 |
| signal_throttle | 221 | 12 |
| risk_governance_hot_reload | 347 | 14 |
| engine_event_snapshot | 150 | 11 |
| per_symbol_price_pnl | 248 | 3 |
| fast_track_reduce | 434 | 14 |
| exit_features | 543 | 12 |
| maker_kpi_hot_reload | 652 | 13 |

**經驗教訓 / 教訓**：
1. **`mod tests;` 自動找 `tests/` 目錄** — 原 `tick_pipeline/mod.rs:975-976` 的 `#[cfg(test)] mod tests;` 不需動，Rust 路徑優先級會自動解析為 `tests/mod.rs`（單檔 `tests.rs` 或目錄 `tests/mod.rs` 二擇一），不需要 production 接線改動
2. **Sibling 內 import path = `super::super::xxx`** — 多一層因 sibling 在子目錄。如果未來需要去 helpers 複用 across siblings，放 mod.rs 即可，不要 sibling 互引（避免依賴方向蛛網）
3. **`git add <directory>/` 是遞迴危險** — Mac local 有 untracked 隔壁 session 檔（`helper_scripts/db/passive_wait_healthcheck/`），`git add helper_scripts/...` 會誤把它們 staged。教訓：複雜 working tree 用 `git add <specific_files>` 而非 `git add <dir>/`，或先 `git status --short` 看清楚再 stage
4. **Multi-session race 偵察**：完成後 `git fetch + git log origin/main` 看是否別 session 推了新 commit。Mac local 看到 `cc4c2d2`（healthcheck split）但 origin 沒有 = 隔壁 session 漏 push。E5 不擅自代推（CLAUDE.md 多 session memory race 教訓 = 不認識的改動禁碰）
5. **G5-07 pattern 在 2.7× scale 上仍有效** — event_consumer 1298 vs tick_pipeline 3524 都 0 production touched，pattern scalable

**剩餘 §九 violations 已知（非本次 scope）**：
- `event_consumer/mod.rs::run_event_consumer` 1695 行單 async fn（P0，G5-07 split 後 mod.rs 仍含此巨型 fn）
- `tick_pipeline/on_tick/helpers.rs` 1182 行（接近 1200 警告，非本次 scope）
- 其餘 Rust 6 檔 ≥ 1200（per 2026-04-24 audit）

**報告**：`docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-26--g5_09_tick_pipeline_tests_split.md`

---

### 2026-05-11 Wave 1.6 P1-FILL-LINEAGE-DROP perf re-audit（QA RCA empirical 25.8% drop fix）

**報告**：`docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-11--p1_fill_lineage_drop_e5_perf.md`

**Context**：QA RCA 2026-05-11 證實 W-C E5 baseline estimate（1024 channel cap / 68 chain in-flight）過樂觀，empirical 25.8% silent drop rate。E1 完成 Option F4 hybrid fix（cap 1024→8192 + try_send_with_background_retry + 3 AtomicU64 metric counter）。E5 re-audit perf 視角。

**Verdict**：APPROVE WITH 3 P3 NOTES（不阻 deploy）
- ✅ Hot path SLA PASS：emit_entry_lineage +<30ns / 0.3ms = <0.01%
- ✅ Spawn cost 可忽略：24h 86 event × ~40μs worst = 3.4ms 累積（per E1 self-claim）
- ✅ Channel memory PASS：worst 6.5 MB / 128 GB unified = 0.005%
- ✅ 預測新 drop rate at cap 8192：24h 0.1% - 1%（對 Stage 3+ promotion gate 1% 對齊）
- ⚠️ 3 P3 minor concerns：counter cache-line false sharing / runtime_shadow.rs 828 LOC（超 800 警告 28 LOC）/ 缺 emit path bench

**F 反思（E5 過樂觀根因）**：
1. 用 24h avg rate 推 burst peak（線性外推沒考慮 power-law tail；avg 7.25 chain/h ≠ peak 270 msg burst）
2. 忽略 PG INSERT 200-500ms flush 期間 rx 阻塞 → producer 仍寫，msg 累積
3. 沒模擬 6 producer parallel（grid + ma + bb_reversion × demo + live_demo）
4. 沒做真實 burst stress test bench harness（hot_path_baseline 只測 tick）

**未來 perf review SOP**（**E5 必加 checklist**）：
- [ ] 列出所有 producer 並算 sum throughput
- [ ] 列出所有 consumer/flush 阻塞時段（PG INSERT latency × 2 加入累積 window）
- [ ] 用 burst factor 5-10x avg rate 估上界
- [ ] 多 producer parallel 必納 producer count multiplier
- [ ] 有 empirical evidence（QA RCA drop rate）必反推 capacity ceiling
- [ ] 不足時補 bench harness 跑 burst stress test 至 cap

**P3 ticket 建議**：
1. P3-COUNTER-CACHELINE-PADDING（3 AtomicU64 加 `#[repr(align(64))]` padding 避免 false sharing；< 200ns/event 影響非 SLA）
2. P3-RUNTIME-SHADOW-SPLIT（runtime_shadow.rs 828 → `lineage_emit.rs` + `channel_helpers.rs`）
3. P3-AGENT-SPINE-BENCH（補 emit_entry_lineage + emit_fill_completion bench harness）

E1 P1-FILL-LINEAGE-MONITOR follow-up（接 counter 到 IPC + healthcheck [55]/[N] SLO 監測）**E5 同意 P1（fix 部署後 0 SLO 監測等於盲飛）**。

**經驗教訓**：
1. **Avg rate ≠ burst peak**：power-law tail 在 multi-producer + 阻塞 consumer 下放大 5-10x
2. **rx 消費阻塞時段 必入 throughput equation**：PG INSERT batch flush 200-500ms 是 producer 累積窗口
3. **empirical evidence > theoretical capacity**：當有真實 runtime 證據（QA RCA empirical 25.8% drop）必反推 capacity ceiling
4. **false sharing pattern**：連續 static AtomicU64 宣告會撞同 cache line；多 thread 並發 fetch_add 互相 invalidate → 50-200ns extra latency / contention（cosmetic 非 SLA）

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



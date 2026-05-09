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


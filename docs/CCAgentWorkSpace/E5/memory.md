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


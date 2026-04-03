# Session Progress — 2026-04-03 Session 10（R-05 Go + R-06 IPC Integration）

## 已完成項

### R-05 Conditional Go 簽核

- 6/6 決策矩陣評估（5 PASS + 1 部分達標）
- Operator 簽核 Conditional Go（2026-04-03）
- 附帶條件：R-06 期間 24h soak test 並行驗證 3 項風險
- 決策文件更新：`docs/rust_migration/05--week8_decision_gate.md`

### Known Issues 全面整理

- 掃描全部日誌/報告/審計/源碼 TODO（4 個並行 Agent）
- 識別 50+ 個問題，經代碼驗證 20+ 已修復
- 新建 `docs/KNOWN_ISSUES.md`：14 個 OPEN 問題，分 5 類
- TODO.md 加指針

### 3 個 Quick Fix（P0 快速通道）

| 修復 | 文件 | commit |
|------|------|--------|
| SEC-1: detail=str(exc) 信息洩露 | legacy_routes.py | a500d4e |
| SEC-2: 對賬虛假告警 | reconciliation_engine.py | a500d4e |
| TRADE-3: Kelly 未實現 PnL 偏差 | position_sizer.py | a500d4e |
| 附帶：registry 測試對齊 linear priority | test_symbol_category_registry.py | a500d4e |

### R06-A：Rust IPC Server 真實狀態接通（commit `efff09e`）

**5 角色分析（PM/PA/FA/E5/QC）→ 關鍵決策：**
- PM：file-read approach（讀 pipeline_snapshot.json，不用 Arc<RwLock>）
- QC HIGH：unrealized_pnl 永遠 0.0 bug → 修復
- E5：提取 handler helper，DRY 三個 handler

**改動：**
- `paper_state.rs`：export_state() 即時計算 unrealized_pnl
- `tick_pipeline.rs`：新增 PipelineSnapshot + snapshot() + latest_prices() getter
- `ipc_server.rs`：3 個新 RPC 方法（get_paper_state/get_latest_prices/get_tick_stats）+ handle_snapshot_field helper + 4 新測試
- `main.rs`：新增 snapshot_writer（5s debounce，寫 pipeline_snapshot.json）
- `ipc_client.py`：3 個新 async 方法

### R06-B1：Python Route IPC 接入（commit `189840a`）

- 新建 `ipc_state_reader.py`（RustSnapshotReader + 模組單例，2s cache TTL）
- paper_trading_routes.py：4 端點 Rust-first（session/status, positions, pnl, order/submit 價格）
- legacy_routes.py：2 個價格讀取塊改造

### R06-B2：Risk + Phase2 Route 接入（commit `7a39022`）

- risk_routes.py：GET /status 回撤計算從 Rust paper_state
- phase2_strategy_routes.py：GET /pipeline/stats 從 Rust tick stats

---

## 測試基準線

```
Python: 3266 passed / 26 failed / 1 skipped（零新回歸）
Rust:   552 passed / 0 failed / 0 warnings
  core:     376 lib + 8 golden + 19 extreme = 403
  engine:   84 unit + 29 stress = 113（+4 IPC 測試）
  types:    36
```

## Commits（本 session）

- `a500d4e` fix: resolve 3 known issues + R-05 Conditional Go
- `efff09e` feat(R06-A): wire IPC server to real pipeline state + fix unrealized PnL
- `189840a` feat(R06-B1): add RustSnapshotReader + wire 4 paper routes + 2 legacy price reads
- `7a39022` feat(R06-B2): wire risk_routes drawdown + phase2 pipeline stats to Rust engine

## R06 進度

```
R06-A  ✅ Rust IPC server 3 方法 + unrealized_pnl fix + snapshot_writer
R06-B1 ✅ Python reader + 6 端點改造（paper_trading + legacy）
R06-B2 ✅ 2 端點改造（risk + phase2）
R06-C  [ ] Python 瘦身（governance_hub, paper_trading_engine, strategy_auto_deployer）
R06-D  [ ] conftest IPC mock（15 breakpoints）
R06-E  [ ] 60 IPC integration tests
R06-F  [ ] Rollback rehearsal < 30s
```

## 關鍵決策

1. **File-read > Arc<RwLock>**：PM 勝出，IPC handler 讀文件而非共享內存
2. **unrealized_pnl 即時計算**：QC HIGH 修復，export_state() 用 latest_prices 計算
3. **Source tag**：所有 Rust 源數據含 `source: "rust_engine"` 標識
4. **governance_routes 暫不改**：GovernanceHub SM 完全 Python-side，等 R-07 灰度再決定
5. **Monitoring only**：R06 只做 read-path，write-path（strategy deploy 等）留 R06-C+

## 下一步

1. R06-C：Python 瘦身（刪除已遷 Rust 的確定性邏輯）
2. R06-D：conftest IPC mock（15 處斷裂）
3. R06-E：60 IPC 集成測試
4. R06-F：Rollback rehearsal
5. R06 Go/No-Go 門控

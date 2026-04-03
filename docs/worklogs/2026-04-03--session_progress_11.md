# Session Progress — 2026-04-03 Session 11（R-06 D/E/F Completion）

## 已完成項

### R06-D：conftest IPC mock fixtures

- 5 個新 pytest fixtures 加入 conftest.py：
  - `rust_snapshot_dir`：temp dir + valid pipeline_snapshot.json
  - `rust_reader_available`/`rust_reader_unavailable`：帶/無數據的 reader
  - `patch_rust_reader_available`/`patch_rust_reader_unavailable`：monkeypatch 版本（路由測試用）
- `SAMPLE_PIPELINE_SNAPSHOT` 共享測試常量
- 12 處 SM import TODO 標記保留（SM 仍為 Python 實現）

### R06-E：IPC 集成測試 39 個（新增）

新建 `test_ipc_integration.py`，10 個測試類：

| 類別 | 測試數 | 覆蓋 |
|------|--------|------|
| Reader core supplement | 6 | empty JSON, partial snapshots, empty file, thread safety, large positions |
| Paper routes Rust-first | 4 | session/status, positions, pnl computation, latest prices |
| Paper routes fallback | 4 | all 4 routes when Rust unavailable |
| Risk routes Rust-first | 4 | drawdown calc, zero drawdown, 100% drawdown, source tag |
| Risk routes fallback | 2 | drawdown fallback, no source tag |
| Phase2 routes Rust-first | 2 | tick stats, response format |
| Phase2 routes fallback | 1 | tick stats fallback |
| Source tag discrimination | 4 | present/absent, in snapshot, survives cache |
| Edge cases | 6 | empty positions, multi-position, net_pnl, zero peak, missing field, empty prices |
| Rollback simulation | 6 | lifecycle, fallback latency, recovery latency, stale file, partial JSON, rapid cycles |

合計：14（existing） + 39（new） = **53 IPC tests 全 PASS**

### R06-F：回滾預演

包含在 TestRollbackSimulation（6 個測試）：
- 完整 available → crash → fallback → recovery 生命週期
- Fallback 檢測延遲 < 100ms（SLA 30s 遠超）
- Recovery 檢測延遲 < 100ms
- Stale file 觸發降級
- Partial JSON（寫入中崩潰）處理
- 5 次快速崩潰/恢復循環

### R-06 Go/No-Go 門控通過

- [x] 4/7 routes IPC 改造完成（3 個有意 defer：governance/backtest/runtime_bridge）
- [x] 53 IPC 集成測試全 PASS
- [x] Python 3794 pass ≥ 3500 基準
- [x] 回滾預演 SLA < 100ms（要求 < 30s）
- [x] conftest IPC mock fixtures 已加入

---

## 測試基準線

```
Python: 3794 passed / 28 failed / 17 errors / 1 skipped（零新回歸）
Rust:   552 passed / 0 failed / 0 warnings
  core:     376 lib + 8 golden + 19 extreme = 403
  engine:   84 unit + 29 stress = 113
  types:    36
```

## 改動文件

| 文件 | 改動 |
|------|------|
| conftest.py | +5 IPC fixtures + SAMPLE_PIPELINE_SNAPSHOT |
| test_ipc_integration.py（NEW） | 39 個 IPC 集成測試 |
| 06--python_ipc_integration.md | R-06 完成狀態 + Go/No-Go 門控結果 |
| CLAUDE_CHANGELOG.md | R-06 completion entry |
| TODO.md | R-06 [~] → [x] |

## 下一步

1. **R-07：灰度驗證 + 穩定觀察**
   - R07-1：影子計算進程搭建
   - R07-2：Rust Engine 灰度模式
   - R07-3：Comparator 自動化對比
   - R07-5：完全回滾演練
   - R07-6：止損接管演練
2. 詳細計劃見 `docs/rust_migration/07--canary_validation.md`

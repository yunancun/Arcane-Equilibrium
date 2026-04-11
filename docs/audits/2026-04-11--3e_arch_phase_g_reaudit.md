# 3E-ARCH Phase G — 9 角色並行 E2 重審報告

**審查日期**：2026-04-11  
**審查範圍**：3E-E2 Fix Rounds Phase A-F 修復後重審  
**審查方式**：9 個角色並行獨立審查（E2/FA/PA/QC/BB/MIT/E3/E4/E5）  
**基線 commit**：`26b9926`（Phase F 完成後）  
**測試基線**：929 engine lib + 366 core + 18 e2e = **1313 passed / 0 failed / 0 ignored**

---

## 0. 核心結論

**9/9 PASS — 0 BLOCKER — 4 MAJOR — 10 MINOR**

原審計發現的 **10 BLOCKER + 7 MAJOR + MEGA-BLOCKER-0** 全部確認修復。  
Phase A-F 修復有效，3E-ARCH 通過驗收。

---

## 1. 角色審查一覽

| 角色 | 結論 | BLOCKER | MAJOR | MINOR |
|------|------|---------|-------|-------|
| E2 | ✅ PASS | 0 | 2 | 2 |
| FA | ✅ PASS | 0 | 1 | 1 |
| PA | ✅ PASS | 0 | 0 | 1 |
| QC | ✅ PASS | 0 | 0 | 0 |
| BB | ✅ PASS | 0 | 0 | 2 |
| MIT | ✅ PASS | 0 | 1 | 1 |
| E3 | ✅ PASS | 0 | 0 | 1 |
| E4 | ✅ PASS | 0 | 0 | 0 |
| E5 | ✅ PASS | 0 | 0 | 3 |

---

## 2. 4 MAJOR（均非阻塞，記錄追蹤）

### M-1 (E2): `handlers.rs` 1195 行，距 1200 硬上限 5 行
- **文件**：`ipc_server/handlers.rs`
- **影響**：下次新增 handler 必先拆分（提取 `handle_get_*` 到 `handlers_read.rs`）
- **處置**：記錄到 backlog，下次改 handler 前強制拆分

### M-2 (E2): `on_tick.rs` 1172 行，距上限 28 行
- **文件**：`tick_pipeline/on_tick.rs`
- **影響**：較不緊急，監控即可
- **處置**：按需拆分 `compute_indicators()` 或 canary 邏輯

### M-3 (FA): GovernanceProfile hardcoded
- **文件**：`on_tick.rs:497,616`
- **問題**：Demo pipeline 使用 `Production` cost_gate（嚴格）而非 `Validation`（中等）
- **影響**：Demo 偏保守非偏寬鬆，安全方向偏差
- **處置**：已有 TODO(3E-2b) 標記，一行修復，W22 處理

### M-4 (MIT): 無 catch_unwind 包裹 pipeline task
- **文件**：`main.rs` pipeline spawn
- **問題**：panic 會繞過 health tracking + EngineEvent::Crashed 廣播
- **影響**：合作式退出路徑覆蓋，但真正 panic 不會
- **處置**：Live 前必修（加 `catch_unwind` + 強制 Crashed 廣播）

---

## 3. 10 MINOR

| ID | 來源 | 描述 |
|----|------|------|
| m-1 | E2 | `handle_get_state()` 讀 `pipeline_snapshot.json` 兩次（應讀一次） |
| m-2 | E2 | `std::ptr::eq` 比較 `&Option<Sender>` 脆弱 |
| m-3 | FA | `determine_primary_kind()` 被調用 3 次（應調 1 次共享結果） |
| m-4 | PA | TODO.md `3E-E4` 仍標 `[ ]`，Phase E 已完成 |
| m-5 | BB | `main.rs:833-835` 三個 `.unwrap()` 應改 `.expect()` |
| m-6 | BB | `news/router.rs:265` test-only mock 用 `std::sync::Mutex::lock().unwrap()` |
| m-7 | MIT | `main.rs:901` `let _ = event_handle.await` 吞掉 JoinError |
| m-8 | E3 | `AuditWriter` 未設 chmod 0600（StateWriter 有設） |
| m-9 | E5 | `on_tick.rs` 重複 `event.symbol.clone()` |
| m-10 | E5 | `format!()` 在 hot path 分配 ID 字串（當前量級可接受） |

---

## 4. 原審計 17 項確認修復

| 原 ID | 描述 | 狀態 |
|-------|------|------|
| MEGA-BLOCKER-0 | TradingMode/primary_kind 刪除 | ✅ 確認修復 |
| BLOCKER-1 (D19) | DB 去重 | ✅ 確認修復 |
| BLOCKER-2 (D6) | 三級故障收縮 + EngineEvent | ✅ 確認修復 |
| BLOCKER-3 (D15) | 全局名義值上限 | ✅ 確認修復 |
| BLOCKER-4 (D17) | Live 獨立 runtime | ✅ 確認修復 |
| BLOCKER-5 | hmac.compare_digest | ✅ 確認修復 |
| BLOCKER-6 (D12) | parking_lot 遷移 | ✅ 確認修復 |
| BLOCKER-7 | API key lock 串行 | ✅ 確認修復 |
| BLOCKER-8 | Per-engine TOML params | ✅ 確認修復 |
| BLOCKER-9 | 5 超限文件拆分 | ✅ 確認修復 |
| BLOCKER-10 | 25 blocker tests | ✅ 確認修復 |
| MAJOR-1 | chmod 0600 | ✅ 確認修復 |
| MAJOR-2 | 啟動競態 | ✅ 確認修復 |
| MAJOR-3 | shutdown 順序 | ✅ 確認修復 |
| MAJOR-4 | TradingMode 清除 | ✅ 確認修復 |
| MAJOR-5 | IPC audit log | ✅ 確認修復 |
| MAJOR-7 | snapshot version | ✅ 確認修復 |

---

## 5. E4 測試回歸

| 套件 | 預期 | 實際 | 狀態 |
|------|------|------|------|
| `openclaw_engine --lib` | 929 | **929 pass / 0 fail / 0 ignored** | ✅ |
| `openclaw_core --lib` | 366 | **366 pass / 0 fail / 0 ignored** | ✅ |
| `reconciler_e2e` | 18 | **18 pass / 0 fail / 0 ignored** | ✅ |

`#[ignore]` 審計：整個 Rust codebase 零 `#[ignore]` 標記。無隱藏失敗。

---

## 6. 下一步

1. 更新 TODO.md：Phase G `[x]`，3E-E2 + 3E-E4 標記完成
2. 4 MAJOR 記入 backlog：M-1/M-2 下次改 handler/on_tick 前拆分，M-3 W22，M-4 Live 前
3. 更新 CLAUDE.md §三 + docs/CLAUDE_CHANGELOG.md

# Phase R-00：提前並行準備
# Rust Migration Parallel Preparation (during Phase 1-3)

**週期**：Phase 1 Day 1 開始，Phase 3 結束時完成
**工時**：~2 天（分散在 Phase 1-3 的間隙）
**前置**：無（零依賴）
**下一階段**：`01--ipc_shared_types_ws.md`

---

## 上下文導航（Agent 接手必讀）

```
源文件：docs/references/2026-04-03--rust_migration_v3_final.md（V3-FINAL §6.2）
認知 SPEC：docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md
當前積壓：TODO.md Phase 0-3
本階段位置：Rust 遷移第 0 階段（與 Phase 0-3 完全並行，不阻塞任何現有工作）
```

**關鍵約束**：
- 本階段只做零依賴任務，不做 IPC echo（推遲到 W1，避免 E1 語言切換負擔）[V3-PM-1]
- Phase 1 的 1.10/1.11/1.12 認知三模組是 Python 開發，與本階段的 Rust 準備互不干擾
- SMA 計算改用 math.fsum() 在 Phase 1 Python 代碼中同步完成 [V3-QC-2]

---

## 具體任務

### [x] R00-1：Cargo workspace 初始化
- **E1 指派**：E1-Alpha（Phase 1 間隙）
- **操作**：
  ```
  mkdir -p ~/BybitOpenClaw/rust
  cd ~/BybitOpenClaw/rust
  cargo init --name openclaw_engine
  # 轉為 workspace
  ```
- **交付**：`rust/Cargo.toml`（workspace）+ `rust/openclaw_types/` + `rust/openclaw_core/` + `rust/openclaw_engine/` 三個 crate 骨架
- **驗收**：`cargo build` 零錯誤

### [x] R00-2：CI pipeline（GitHub Actions）
- **E1 指派**：E1-Alpha
- **操作**：`.github/workflows/rust.yml` — `cargo test` + `cargo clippy` + `cargo fmt --check`
- **交付**：PR 自動跑 Rust CI
- **驗收**：空 crate 的 CI 綠色

### [x] R00-3：openclaw_types crate 完整定義
- **E1 指派**：E1-Beta（Phase 1 Day 3+）
- **操作**：根據 V3 §2.2，實現全部類型：
  - `types/price.rs`：PriceEvent, Kline, OHLCV
  - `types/intent.rs`：TradeIntent, OrderIntent, RiskVerdict
  - `types/agent.rs`：AgentRole, MessageType, AgentMessage
  - `types/state.rs`：GovernanceMode, AgentState, OmsState
  - `types/risk.rs`：RiskConfig, H0CheckResult, GuardianConfig
  - `types/cognitive.rs`：CognitiveParams, RegretSummary, DreamInsight
  - `types/config.rs`：EngineConfig（含冷/熱參數標記 [V3-PA-5]）
- **交付**：~4,500 行 Rust，全部 `#[derive(Serialize, Deserialize, Clone, Debug)]`
- **驗收**：`cargo test -p openclaw_types` 通過 + serde 序列化/反序列化測試

### [ ] R00-4：L1 接口凍結簽核（Phase 2 結束時）
- **PM 主導**
- **凍結範圍**：indicator_engine / signal_generator / h0_gate / strategies 的 Python 接口
- **操作**：列出凍結文件清單 + git tag `l1-interface-freeze`
- **注意**：GovernanceHub 接口不在此凍結（Phase 3 放權框架可能修改）[V3-PM-2]

### [ ] R00-5：L2 接口凍結簽核（Phase 3 結束時）
- **PM 主導**
- **凍結範圍**：governance_hub / 4 SM / authorization 相關接口
- **操作**：git tag `l2-interface-freeze`

### [x] R00-6：Python SMA 改用 math.fsum() [V3-QC-2]（Phase 1 task 1-5 已完成）
- **E1 指派**：E1-Gamma（Phase 1 開發 indicator 時同步完成）
- **操作**：indicator_engine.py / indicators/moving_averages.py 的 sum() → math.fsum()
- **驗收**：現有測試全部通過 + 數值差異 < 1e-14

### [ ] R00-7：Paper Trading 自動監控告警 bot [V3-PM-6]
- **E1 指派**：E1-Delta（Phase 0 期間）
- **操作**：Telegram bot 自動推送異常（連虧 5+、回撤 >3%、系統離線）
- **目的**：Rust 開發期間運維負擔 <15min/天

---

## Go/No-Go 門控

全部滿足後方可進入 01 階段：
- [x] Cargo workspace + 3 crate 骨架編譯通過（2026-04-03）
- [x] CI pipeline 綠色（2026-04-03，.github/workflows/rust.yml）
- [x] openclaw_types 全部類型定義 + serde 測試通過（30 tests, 2026-04-03）
- [ ] L1 接口凍結 tag 已打（Phase 2 結束時）
- [ ] L2 接口凍結 tag 已打（Phase 3 結束後）
- [x] Python SMA fsum() 已替換（Phase 1 task 1-5 已完成）
- [ ] Paper Trading 告警 bot 運行中（延後至 Phase 2 末尾）

---

## 與現有 Phase 0-3 的交叉

| 現有任務 | 交叉點 | 處理方式 |
|----------|--------|---------|
| Phase 1 1.10-1.12 認知三模組 | 同期開發，Python 實現 | 互不干擾，types crate 的 CognitiveParams 提前定義 |
| Phase 1 1.5 Indicator 擴展 | SMA fsum() 在此同步 | R00-6 與 1.5 合併 commit |
| Phase 2 策略 V2 | L1 凍結前必須完成策略接口 | Phase 2 完成 → R00-4 簽核 |
| Phase 3 放權框架 | L2 凍結前必須完成治理接口 | Phase 3 完成 → R00-5 簽核 |

---

## 進度追蹤

| 任務 | 狀態 | 完成日期 | commit |
|------|------|---------|--------|
| R00-1 Cargo workspace | [x] | 2026-04-03 | pending |
| R00-2 CI pipeline | [x] | 2026-04-03 | pending |
| R00-3 types crate | [x] | 2026-04-03 | pending |
| R00-4 L1 凍結 | [ ] | | Phase 2 結束時 |
| R00-5 L2 凍結 | [ ] | | Phase 3 結束時 |
| R00-6 fsum() | [x] | 2026-04-03 | Phase 1 task 1-5 已完成 |
| R00-7 告警 bot | [ ] | | 延後至 Phase 2 末尾 |

---

## 問題與變更（執行期間發現的問題記錄於此）

### 2026-04-03
- types crate 實際 1,242 行（vs 預估 4,500 行）：骨架已完整涵蓋 V3 §3.2 全部 10 個 shared_types + 認知/配置類型。剩餘行數將在 R-01 的 IPC 消息定義 + 更細粒度的策略/指標類型中補充。
- E2 審查 P2 建議：intent.rs/cognitive.rs 的 direction/side/order_type 等 String 字段應改為 enum，計劃 R-01 IPC 對齊時統一處理。
- R00-7 Telegram bot 延後：需外部 bot token 配置，不在關鍵路徑。
